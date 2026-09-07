"""API autenticada do Assistente de Criativos Meta.

As rotas criam estratégia e briefs; nenhuma delas chama Meta Ads, gera mídia,
faz upload ou publica campanha.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.config import Settings, get_settings
from app.criativo.agente.contrato import (
    ElementoCongelado,
    EntradaNovaOperacao,
    PedidoDeContinuacao,
    PedidoDeDecisao,
    PedidoDoAgente,
    SaidaDoAgente,
)
from app.criativo.agente.caminhos import CaminhoInvalido, resolver as resolver_caminho
from app.criativo.agente.orquestrador import AgenteCriativoMeta, RespostaDoModeloInvalida
from app.criativo.agente.persistencia import NaoEncontrado, RepositorioAgenteCriativo
from app.criativo.studio import AutorizacaoDeGasto, PedidoDeGeracao, PlanoDeGeracao
from app.llm.gemini import GeminiClient
from app.seguranca.identidade import Identidade, exigir_usuario
from app.services.supabase_service import SupabaseService


router = APIRouter(prefix="/api/criativos/meta/agente", tags=["criativos-meta-agente"])
ProjectRef = Annotated[str, Path(pattern=r"^crproj_[a-f0-9]{24}$")]
RunRef = Annotated[str, Path(pattern=r"^crrun_[a-f0-9]{24}$")]

#: Quanto uma run pode ficar `RUNNING` sem sinal antes de ser retomável.
#: Duas tentativas de modelo com retry cabem folgadamente aqui; abaixo disso
#: uma execução saudável e lenta seria roubada por um segundo clique.
LEASE_DE_EXECUCAO_S = 600


def _ref(prefixo: str) -> str:
    return prefixo + secrets.token_hex(12)


def _erro(codigo: str, mensagem: str, http_status: int) -> HTTPException:
    return HTTPException(http_status, detail={"codigo": codigo, "mensagem": mensagem})


def obter_repositorio(settings: Settings = Depends(get_settings)) -> RepositorioAgenteCriativo:
    try:
        return RepositorioAgenteCriativo(SupabaseService(settings))
    except RuntimeError as exc:
        raise _erro("CRIATIVO_AGENTE_SEM_BANCO", str(exc), 503) from exc


def obter_agente(settings: Settings = Depends(get_settings)) -> AgenteCriativoMeta:
    if not settings.resolved_gemini_key:
        raise _erro(
            "CRIATIVO_AGENTE_SEM_MODELO",
            "O Assistente está sem credencial de modelo; nenhum conteúdo fictício foi usado.",
            503,
        )
    model = getattr(settings, "criativo_meta_gemini_model", None) or "gemini-3.8-flash"
    # Menor que a descoberta do Pautador: aqui a criatividade acontece dentro
    # de um schema e de uma matriz; 0.9 aumenta variação sintática e custo de
    # retry sem dar autoridade nova ao modelo.
    return AgenteCriativoMeta(GeminiClient(settings, model=model, temperature=0.35))


def _hash_valor(valor: Any) -> str:
    cru = json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(cru.encode("utf-8")).hexdigest()


def _decisoes_efetivas(decisoes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """A última decisão de cada caminho é a que vale.

    `listar_decisoes` devolve em ordem crescente de `created_at`, então a
    reatribuição por caminho deixa a mais recente. Reprovar depois de aprovar
    desfaz o congelamento sem apagar a trilha append-only — que é o ponto de a
    tabela não ter UPDATE.
    """
    return {d["path"]: d for d in decisoes}


def _aprovados_validos(
    output: Any, efetivas: dict[str, dict[str, Any]]
) -> frozenset[str]:
    """As aprovações que ainda descrevem ESTE conteúdo.

    Uma decisão guarda `path` + `snapshot_sha256`. O caminho é estável por
    construção (`caminhos.py` endereça por `ref`, nunca por índice), então ele
    sobrevive à run seguinte — mas o CONTEÚDO naquele caminho não precisa
    sobreviver: refinar uma peça mantém a ref e troca o texto.

    Conferir só o caminho, como fazíamos, herdava a aprovação da versão
    anterior: o operador aprovava a peça A, pedia refinamento, e o botão que
    gasta liberava a peça A' que ninguém leu. Reconferir o hash é o que
    transforma "esta ref foi aprovada um dia" em "este conteúdo foi aprovado".

    Uma aprovação cujo caminho sumiu do lote também não conta — não há o que
    autorizar.
    """
    validos: set[str] = set()
    for caminho, d in efetivas.items():
        if d.get("decisao") != "APROVADO":
            continue
        try:
            atual = resolver_caminho(output, caminho)
        except CaminhoInvalido:
            continue
        if _hash_valor(atual) == d.get("snapshot_sha256"):
            validos.add(caminho)
    return frozenset(validos)


def _decisao_para_json(d: dict[str, Any]) -> dict[str, Any]:
    """O que a tela precisa para redesenhar a revisão — e nada além disso.

    O `snapshot` inteiro fica de fora de propósito: ele é uma cópia da peça que
    a própria run já devolve, e mandá-lo de novo dobraria a resposta sem
    acrescentar informação. O `snapshot_sha256` basta para explicar por que uma
    aprovação antiga deixou de valer.
    """
    return {
        "decision_ref": d.get("decision_ref"),
        "run_ref": d.get("run_ref"),
        "path": d.get("path"),
        "decisao": d.get("decisao"),
        "scope": d.get("scope"),
        "snapshot_sha256": d.get("snapshot_sha256"),
        "feedback": d.get("feedback"),
        "created_at": d.get("created_at"),
    }


async def _executar_e_persistir(
    *,
    pedido: PedidoDoAgente,
    run_ref: str,
    identidade: Identidade,
    repo: RepositorioAgenteCriativo,
    agente: AgenteCriativoMeta,
) -> dict[str, Any]:
    async def registrar_falha_sem_mascarar(error: dict[str, Any]) -> None:
        # O recibo de falha é best-effort. Uma indisponibilidade do banco neste
        # segundo ato não pode trocar um erro de contrato/modelo por outro erro
        # incidental e apagar o diagnóstico original devolvido ao operador.
        try:
            await repo.falhar_run(run_ref, identidade.sub, error=error)
        except Exception:
            return

    try:
        resultado = await agente.executar(pedido)
        row = await repo.concluir_run(
            run_ref,
            identidade.sub,
            output=resultado.saida.model_dump(mode="json"),
            model=resultado.modelo,
            tentativas=resultado.tentativas,
            request_sha256=resultado.request_sha256,
            knowledge_sha256=resultado.knowledge_sha256,
        )
    except RespostaDoModeloInvalida as exc:
        await registrar_falha_sem_mascarar(
            {"codigo": "CRIATIVO_AGENTE_OUTPUT_INVALIDO", "erros": exc.erros[:20]}
        )
        raise _erro(
            "CRIATIVO_AGENTE_OUTPUT_INVALIDO",
            "O modelo não produziu um lote que passasse no contrato após duas tentativas.",
            422,
        ) from exc
    except Exception as exc:
        await registrar_falha_sem_mascarar(
            {"codigo": "CRIATIVO_AGENTE_FALHOU", "tipo": type(exc).__name__}
        )
        raise _erro(
            "CRIATIVO_AGENTE_FALHOU",
            "A execução falhou e foi registrada; nenhum lote parcial foi promovido.",
            502,
        ) from exc
    return {"run_ref": run_ref, "status": row["status"], "output": row["output"]}


@router.get("/operacoes")
async def listar_operacoes(
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
    limite: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """O histórico do dono. Sem esta rota não existe retomada.

    Devolve o suficiente para a lista decidir — ref, nome, status, quando mudou —
    e NÃO devolve `input` nem `output`: um lote inteiro por linha transformaria
    uma listagem de 20 itens em megabytes, e a tela de histórico não desenha
    peça nenhuma. Quem abre a operação busca o detalhe pela rota de leitura.
    """
    linhas = await repo.listar_operacoes(identidade.sub, limite=limite, offset=offset)
    return {
        "operacoes": [
            {
                "project_ref": linha["project_ref"],
                "nome_da_operacao": (linha.get("input") or {}).get("nome_da_operacao"),
                "status": linha.get("status"),
                "latest_run_ref": linha.get("latest_run_ref"),
                "created_at": linha.get("created_at"),
                "updated_at": linha.get("updated_at"),
            }
            for linha in linhas
        ],
        "limite": limite,
        "offset": offset,
    }


@router.post("/operacoes", status_code=status.HTTP_201_CREATED)
async def criar_operacao(
    entrada: EntradaNovaOperacao,
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
) -> dict[str, Any]:
    """Cria a operação e enfileira a primeira run. NÃO chama o modelo.

    ## Por que criar e executar são dois atos

    A versão anterior chamava o LLM DENTRO deste POST. Duas gerações de ~40s
    encadeadas passam de qualquer timeout de proxy, e quem recarregava a página
    não tinha como saber se a run existia: o `run_ref` só nascia na resposta que
    nunca chegava. O mesmo defeito que `criativo/execucao.py` já tinha
    documentado e resolvido para imagem — "não faça o request HTTP esperar o
    render terminar" — valia aqui e não tinha sido aplicado.

    Agora o 201 sai com `project_ref` e `run_ref` já gravados e `QUEUED`. Se a
    conexão cair no segundo seguinte, a operação está no histórico e a run está
    na fila, retomável. Executar é a rota seguinte, e é um clique próprio.

    ⚠️ `obter_agente` NÃO é dependência aqui de propósito: montar a página ou
    criar o rascunho não pode exigir credencial de modelo nem testá-la. A falta
    de modelo aparece ao executar, que é quando ela de fato impede algo.
    """
    project_ref = _ref("crproj_")
    run_ref = _ref("crrun_")
    pedido = PedidoDoAgente(
        **entrada.model_dump(mode="python"),
        project_ref=project_ref,
        fase="NOVA_OPERACAO",
    )
    await repo.criar_operacao(
        {
            "project_ref": project_ref,
            "owner_id": identidade.sub,
            "status": "RUNNING",
            "input": entrada.model_dump(mode="json"),
        }
    )
    await repo.criar_run(
        {
            "run_ref": run_ref,
            "project_ref": project_ref,
            "owner_id": identidade.sub,
            "status": "QUEUED",
            "phase": pedido.fase.value,
            "input": pedido.model_dump(mode="json"),
        }
    )
    return {
        "project_ref": project_ref,
        "run_ref": run_ref,
        "status": "QUEUED",
        "proximo_ato": "executar",
    }


@router.post("/operacoes/{project_ref}/runs", status_code=status.HTTP_201_CREATED)
async def continuar_operacao(
    project_ref: ProjectRef,
    continuacao: PedidoDeContinuacao,
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
) -> dict[str, Any]:
    """Enfileira a run seguinte com o lote anterior em mãos. NÃO chama o modelo."""
    try:
        operacao = await repo.obter_operacao(project_ref, identidade.sub)
        decisoes = await repo.listar_decisoes(project_ref, identidade.sub)
    except NaoEncontrado as exc:
        raise _erro("CRIATIVO_AGENTE_OPERACAO_INEXISTENTE", "Operação não encontrada.", 404) from exc
    entrada = dict(operacao["input"])
    if continuacao.quantidade_de_pecas is not None:
        entrada["quantidade_de_pecas"] = continuacao.quantidade_de_pecas
    if continuacao.formatos_permitidos is not None:
        entrada["formatos_permitidos"] = continuacao.formatos_permitidos
    # A decisão mais recente por caminho é a efetiva. Uma reprovação posterior
    # desfaz o congelamento sem apagar a história append-only.
    por_caminho = {d["path"]: d for d in decisoes}
    aprovacoes = [d for d in por_caminho.values() if d["decisao"] == "APROVADO"]
    congelados = [
        ElementoCongelado(
            ref=f"frozen_{d['decision_ref'].removeprefix('crdec_')}",
            caminho=d["path"],
            valor=json.dumps(
                d["snapshot"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
            aprovado_em=d["created_at"],
        )
        for d in aprovacoes
    ]
    # A saída da última run CONCLUÍDA é o que está sendo criticado. Sem ela o
    # modelo recebia briefing + feedback e refazia do zero: "troque o hook da
    # peça do público frio" não tinha peça nenhuma a que se referir, e o lote
    # novo só coincidia com o anterior nos pontos congelados. Carregá-la é o que
    # transforma "gerar de novo" em "refinar".
    runs = await repo.listar_runs(project_ref, identidade.sub)
    concluidas = [r for r in runs if r.get("status") == "COMPLETED" and r.get("output")]
    saida_anterior = concluidas[0]["output"] if concluidas else None

    pedido = PedidoDoAgente(
        **entrada,
        project_ref=project_ref,
        fase=continuacao.fase,
        elementos_congelados=congelados,
        feedback=continuacao.feedback,
        feedback_escopo=continuacao.feedback_escopo,
        saida_anterior=saida_anterior,
    )
    run_ref = _ref("crrun_")
    await repo.criar_run(
        {
            "run_ref": run_ref,
            "project_ref": project_ref,
            "owner_id": identidade.sub,
            "status": "QUEUED",
            "phase": pedido.fase.value,
            "input": pedido.model_dump(mode="json"),
        }
    )
    return {"run_ref": run_ref, "status": "QUEUED", "proximo_ato": "executar"}


@router.post("/operacoes/{project_ref}/runs/{run_ref}/executar")
async def executar_run(
    project_ref: ProjectRef,
    run_ref: RunRef,
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
    agente: AgenteCriativoMeta = Depends(obter_agente),
) -> dict[str, Any]:
    """Executa uma run já enfileirada. É aqui — e só aqui — que o modelo roda.

    ## As três respostas que não geram nada

    - run já `COMPLETED`: devolve a saída que existe. Reabrir a aba, reconectar
      ou clicar duas vezes NÃO paga uma segunda geração, e esta é a única
      leitura de idempotência que interessa ao operador.
    - run `RUNNING` com dono vivo: 409. Duas abas não disputam o mesmo lote.
    - run `FAILED`: 409 com o caminho certo, que é enfileirar outra run. Reusar
      a ref de uma execução falha apagaria o registro do próprio defeito.

    ⚠️ `obter_agente` é dependência e roda ANTES do corpo, de propósito: sem
    credencial de modelo a resposta é 503 e a run continua `QUEUED`, em vez de
    ser reivindicada por uma execução que nunca poderia acontecer.
    """
    try:
        await repo.obter_operacao(project_ref, identidade.sub)
        run = await repo.obter_run(run_ref, identidade.sub)
    except NaoEncontrado as exc:
        raise _erro("CRIATIVO_AGENTE_ALVO_INEXISTENTE", "Operação ou run não encontrada.", 404) from exc

    if run.get("project_ref") != project_ref:
        raise _erro("CRIATIVO_AGENTE_ALVO_INVALIDO", "A run não pertence a esta operação.", 409)

    if run.get("status") == "COMPLETED":
        return {"run_ref": run_ref, "status": "COMPLETED", "output": run["output"], "reexecutado": False}
    if run.get("status") == "FAILED":
        raise _erro(
            "CRIATIVO_AGENTE_RUN_FALHOU",
            "Esta execução falhou e fica no histórico; enfileire uma nova run para tentar de novo.",
            409,
        )

    reivindicada = await repo.reivindicar_run(run_ref, identidade.sub)
    if reivindicada is None:
        reivindicada = await repo.reivindicar_run_abandonada(
            run_ref, identidade.sub, lease_s=LEASE_DE_EXECUCAO_S
        )
    if reivindicada is None:
        raise _erro(
            "CRIATIVO_AGENTE_RUN_EM_EXECUCAO",
            "Esta run já está sendo executada; acompanhe pela leitura da operação.",
            409,
        )

    pedido = PedidoDoAgente.model_validate(run["input"])
    return await _executar_e_persistir(
        pedido=pedido, run_ref=run_ref, identidade=identidade, repo=repo, agente=agente
    )


@router.get("/operacoes/{project_ref}")
async def ler_operacao(
    project_ref: ProjectRef,
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
) -> dict[str, Any]:
    try:
        operacao = await repo.obter_operacao(project_ref, identidade.sub)
    except NaoEncontrado as exc:
        raise _erro("CRIATIVO_AGENTE_OPERACAO_INEXISTENTE", "Operação não encontrada.", 404) from exc
    runs = await repo.listar_runs(project_ref, identidade.sub)
    decisoes = await repo.listar_decisoes(project_ref, identidade.sub)
    efetivas = _decisoes_efetivas(decisoes)

    # Sem esta projeção o reload perdia a revisão: a tela guardava as aprovações
    # só em estado de sessão, então recarregar mostrava um lote inteiro como não
    # aprovado enquanto o servidor — que é quem manda — já tinha as decisões
    # gravadas. O operador reaprovava por engano, ou achava que tinha perdido o
    # trabalho.
    #
    # A validade é recalculada AQUI, por run, contra o conteúdo de cada run. A
    # tela não pode decidir isso: ela não tem o hash aprovado nem autoridade
    # para comparar.
    aprovacoes_validas = {
        run["run_ref"]: sorted(_aprovados_validos(run.get("output"), efetivas))
        for run in runs
        if run.get("status") == "COMPLETED" and run.get("output")
    }
    return {
        "operacao": operacao,
        "runs": runs,
        "decisoes": [_decisao_para_json(d) for d in efetivas.values()],
        "aprovacoes_validas": aprovacoes_validas,
    }


async def _lote_e_aprovados(
    project_ref: str,
    run_ref: str,
    identidade: Identidade,
    repo: RepositorioAgenteCriativo,
) -> tuple[dict[str, Any], SaidaDoAgente, frozenset[str]]:
    """A operação, o lote concluído e o que uma PESSOA aprovou nele."""
    try:
        operacao = await repo.obter_operacao(project_ref, identidade.sub)
        run = await repo.obter_run(run_ref, identidade.sub)
        decisoes = await repo.listar_decisoes(project_ref, identidade.sub)
    except NaoEncontrado as exc:
        raise _erro("CRIATIVO_AGENTE_ALVO_INEXISTENTE", "Operação ou run não encontrada.", 404) from exc

    if run.get("project_ref") != project_ref or run.get("status") != "COMPLETED":
        raise _erro(
            "CRIATIVO_AGENTE_ALVO_INVALIDO",
            "A geração precisa apontar para uma run concluída desta operação.",
            409,
        )

    # A decisão mais recente por caminho é a efetiva — uma reprovação posterior
    # desfaz o congelamento sem apagar a história — e ela só vale se o conteúdo
    # naquele caminho ainda for o que foi aprovado. Conferir apenas o caminho
    # deixava uma peça refinada herdar a aprovação da versão anterior.
    aprovados = _aprovados_validos(run["output"], _decisoes_efetivas(decisoes))
    return operacao, SaidaDoAgente.model_validate(run["output"]), aprovados


def _identidade_do_motor() -> dict[str, Any]:
    """Qual motor de imagem ESTE processo usaria, sem chamar nada e sem chave.

    A tela precisa nomear o modelo antes do clique — "gerar" sem dizer com o quê
    é pedir autorização em branco. Construir o motor só lê o ambiente; nenhuma
    requisição sai daqui.

    Devolve `modelo: None` quando o pacote do motor nem existe no ambiente, em
    vez de derrubar a rota de PLANO: planejar precisa continuar funcionando para
    mostrar o bloqueio, e um plano que não abre esconde a causa.
    """
    try:
        from app.routers.criativos import obter_motor  # noqa: PLC0415

        motor = obter_motor()
    except Exception:  # noqa: BLE001
        return {"modelo": None, "configurado": False}
    return {
        "modelo": getattr(motor, "nome", None),
        "configurado": bool(getattr(motor, "configurado", False)),
    }


def _conferir_autorizacao(
    autorizacao: AutorizacaoDeGasto | None, plano: PlanoDeGeracao, motor: Any
) -> None:
    """A confirmação humana do gasto, reconferida contra o que o servidor mediu.

    ## Por que não basta o plano

    O plano já é recalculado no servidor, mas ele responde "o que aconteceria",
    não "alguém autorizou que acontecesse". Sem esta porta, qualquer cliente que
    montasse o POST — uma aba antiga, um script, um duplo clique num botão que
    mudou de significado desde que a tela foi desenhada — despacharia renders
    pagos sem ninguém ter lido um número.

    ## O que é exigido, e por quê cada um

    - `modelo`: o operador autoriza um motor específico. Se o servidor trocou de
      modelo entre a tela e o clique, o consentimento não cobre o que rodaria.
    - `total_de_renders`: é o único limite que o servidor impõe com EXATIDÃO,
      porque conta chamadas, e chamada é a unidade que se paga. Divergiu do que
      a tela mostrou, recusa — a seleção mudou debaixo do operador.
    - `teto_custo_usd`: opcional, e conferido contra a ESTIMATIVA. Quando o
      custo é desconhecido não há o que comparar, e o servidor não finge que o
      teto foi respeitado: ele diz que o limite efetivo é a contagem.

    Nada foi criado quando esta função levanta — ela roda antes do primeiro job.
    """
    if autorizacao is None:
        raise HTTPException(
            409,
            detail={
                "codigo": "CRIATIVO_STUDIO_SEM_AUTORIZACAO_DE_GASTO",
                "mensagem": (
                    "Gerar imagem gasta. Confirme o modelo, a quantidade e o teto "
                    "antes de despachar."
                ),
                "modelo_de_imagem": getattr(motor, "nome", None),
                "total_de_renders": plano.total_de_renders,
                "custo_estimado_usd": plano.custo_estimado_usd,
                "custo_e_estimado": True,
                "nada_foi_criado": True,
            },
        )

    nome_do_motor = getattr(motor, "nome", None)
    if nome_do_motor and autorizacao.modelo != nome_do_motor:
        raise HTTPException(
            409,
            detail={
                "codigo": "CRIATIVO_STUDIO_MODELO_DIVERGENTE",
                "mensagem": (
                    "A autorização é para outro modelo; confira o plano e confirme de novo."
                ),
                "autorizado": autorizacao.modelo,
                "modelo_de_imagem": nome_do_motor,
                "nada_foi_criado": True,
            },
        )

    if autorizacao.total_de_renders != plano.total_de_renders:
        raise HTTPException(
            409,
            detail={
                "codigo": "CRIATIVO_STUDIO_TOTAL_DIVERGENTE",
                "mensagem": (
                    "A seleção mudou depois da confirmação: "
                    f"autorizou {autorizacao.total_de_renders} imagem(ns) e este "
                    f"pedido produz {plano.total_de_renders}."
                ),
                "autorizado": autorizacao.total_de_renders,
                "total_de_renders": plano.total_de_renders,
                "nada_foi_criado": True,
            },
        )

    teto = autorizacao.teto_custo_usd
    estimado = plano.custo_estimado_usd
    if teto is not None and estimado is not None and estimado > teto:
        raise HTTPException(
            409,
            detail={
                "codigo": "CRIATIVO_STUDIO_TETO_DE_CUSTO",
                "mensagem": (
                    f"A estimativa de US$ {estimado:.2f} passa do teto autorizado de "
                    f"US$ {teto:.2f}."
                ),
                "custo_estimado_usd": estimado,
                "teto_custo_usd": teto,
                "custo_e_estimado": True,
                "nada_foi_criado": True,
            },
        )


def _plano_para_json(plano: PlanoDeGeracao) -> dict[str, Any]:
    motor = _identidade_do_motor()
    return {
        "conceitos": plano.conceitos,
        "formatos": plano.formatos,
        "total_de_renders": plano.total_de_renders,
        "teto": plano.teto,
        "custo_estimado_usd": plano.custo_estimado_usd,
        # O custo é SEMPRE derivado de tabela de referência do provider, que
        # cobra por token e não publica dólar por chamada. Marcar a estimativa
        # como estimativa é o que impede a tela de escrever um número como se
        # fosse fatura — e `null` continua significando "não sei", nunca zero.
        "custo_e_estimado": True,
        "modelo_de_imagem": motor["modelo"],
        "motor_configurado": motor["configurado"],
        "pode_executar": plano.pode_executar,
        "bloqueios": [b.model_dump() for b in plano.bloqueios],
        "briefings": [
            {
                "creative_ref": b.linhagem.creative_ref,
                "formato_slot": b.formato_slot,
                "texto_na_arte": b.texto_na_arte,
            }
            for b in plano.briefings
        ],
    }


@router.post("/operacoes/{project_ref}/geracoes/plano")
async def planejar_geracao(
    project_ref: ProjectRef,
    pedido: PedidoDeGeracao,
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
) -> dict[str, Any]:
    """Calcula N×M, custo e recusas. NÃO grava, NÃO despacha, NÃO gasta.

    Existe como rota própria porque a tela precisa mostrar o tamanho e o preço
    do lote ANTES de o botão de gerar ficar disponível — e porque uma recusa
    (peça não aprovada, formato inexistente, teto estourado) é informação que o
    operador tem direito de ver sem arriscar um clique.
    """
    from app.criativo.studio.adaptador import montar_plano  # noqa: PLC0415

    operacao, saida, aprovados = await _lote_e_aprovados(
        project_ref, pedido.run_ref, identidade, repo
    )
    entrada = operacao.get("input") or {}
    plano = montar_plano(
        saida=saida,
        pedido=pedido,
        caminhos_aprovados=aprovados,
        contexto_do_publico=entrada.get("contexto_do_publico") or "Público não declarado.",
        objetivo=entrada.get("objetivo_meta") or "OUTCOME_TRAFFIC",
    )
    return _plano_para_json(plano)


@router.post("/operacoes/{project_ref}/geracoes", status_code=status.HTTP_201_CREATED)
async def gerar_imagens(
    project_ref: ProjectRef,
    pedido: PedidoDeGeracao,
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
) -> dict[str, Any]:
    """Manda produzir as imagens das peças aprovadas. É o ato que gasta.

    ## A ordem importa, e é esta

    1. o plano é RECALCULADO no servidor — o que o cliente mandou como plano é
       ignorado, porque um teto conferido no browser não é um teto;
    2. qualquer bloqueio recusa aqui, antes de existir job;
    3. a falta de motor recusa aqui, antes de existir job: aceitar trabalho que
       vai falhar por credencial deixaria lixo na biblioteca e faria o operador
       esperar por nada;
    4. só então um job por conceito é criado, com os M formatos dele dentro.

    ## O que NÃO acontece aqui

    Nenhuma campanha é criada, nenhuma mídia sobe para a Meta e nenhuma API de
    anúncios é chamada. Produzir arquivo e usar arquivo em campanha são atos
    diferentes, e este é o primeiro.
    """
    from app.criativo.studio.adaptador import montar_plano  # noqa: PLC0415

    operacao, saida, aprovados = await _lote_e_aprovados(
        project_ref, pedido.run_ref, identidade, repo
    )
    entrada = operacao.get("input") or {}
    plano = montar_plano(
        saida=saida,
        pedido=pedido,
        caminhos_aprovados=aprovados,
        contexto_do_publico=entrada.get("contexto_do_publico") or "Público não declarado.",
        objetivo=entrada.get("objetivo_meta") or "OUTCOME_TRAFFIC",
    )
    if not plano.pode_executar:
        raise HTTPException(
            409,
            detail={
                "codigo": "CRIATIVO_STUDIO_PEDIDO_BLOQUEADO",
                "mensagem": "Este pedido não pode virar imagem ainda.",
                "bloqueios": [b.model_dump() for b in plano.bloqueios],
                "nada_foi_criado": True,
            },
        )

    from app.criativo.studio.adaptador import pedido_de_job  # noqa: PLC0415
    from app.routers.criativos import obter_executor, obter_motor  # noqa: PLC0415

    motor = obter_motor()
    if not getattr(motor, "configurado", False):
        raise _erro(
            "CRIATIVO_STUDIO_MOTOR_SEM_CREDENCIAL",
            "O motor de imagem não está configurado neste servidor; nada foi criado.",
            503,
        )

    _conferir_autorizacao(pedido.autorizacao, plano, motor)

    # O executor do processo, com a trava de concorrência compartilhada — a
    # mesma que impede dois disparos do mesmo job pagarem duas vezes.
    from app.routers.criativos import obter_assinador, obter_repo  # noqa: PLC0415

    executor = obter_executor(obter_repo(get_settings()), obter_assinador())

    por_conceito: dict[str, list[Any]] = {}
    for briefing in plano.briefings:
        por_conceito.setdefault(briefing.linhagem.creative_ref, []).append(briefing)

    criados: list[dict[str, Any]] = []
    for creative_ref, briefings in por_conceito.items():
        # Reenviar o mesmo pedido não paga de novo: a ponte é única por
        # (run_ref, creative_ref) e responde antes de o executor ser chamado.
        ja = await repo.ponte_por_peca(pedido.run_ref, creative_ref, identidade.sub)
        if ja is not None:
            criados.append(
                {
                    "creative_ref": creative_ref,
                    "job_id": ja["job_id"],
                    "slots": ja.get("slots") or [],
                    "criado_agora": False,
                }
            )
            continue

        job, criado = await executor.criar_job_de_imagem(
            pedido_de_job(
                briefings,
                nome_da_operacao=entrada.get("nome_da_operacao") or "Operação sem nome",
            ),
            identidade.sub,
        )
        linhagem = briefings[0].linhagem
        await repo.registrar_ponte(
            {
                "ponte_ref": _ref("crpj_"),
                "owner_id": identidade.sub,
                "project_ref": project_ref,
                "run_ref": pedido.run_ref,
                "creative_ref": linhagem.creative_ref,
                "group_ref": linhagem.group_ref,
                "copy_ref": linhagem.copy_ref,
                "state_ref": linhagem.state_ref,
                "job_id": str(job["id"]),
                "slots": [b.formato_slot for b in briefings],
                "fato_refs": list(linhagem.fato_refs),
                "rule_refs": list(linhagem.rule_refs),
            }
        )
        executor.disparar(str(job["id"]))
        criados.append(
            {
                "creative_ref": creative_ref,
                "job_id": str(job["id"]),
                "slots": [b.formato_slot for b in briefings],
                "criado_agora": criado,
            }
        )

    return {
        "geracoes": criados,
        "total_de_renders": plano.total_de_renders,
        "custo_estimado_usd": plano.custo_estimado_usd,
    }


@router.get("/operacoes/{project_ref}/geracoes")
async def listar_geracoes(
    project_ref: ProjectRef,
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
) -> dict[str, Any]:
    """A procedência: quais peças aprovadas viraram job de mídia, e quando."""
    try:
        await repo.obter_operacao(project_ref, identidade.sub)
    except NaoEncontrado as exc:
        raise _erro("CRIATIVO_AGENTE_OPERACAO_INEXISTENTE", "Operação não encontrada.", 404) from exc
    pontes = await repo.listar_pontes(project_ref, identidade.sub)
    return {
        "geracoes": [
            {
                "ponte_ref": p.get("ponte_ref"),
                "creative_ref": p.get("creative_ref"),
                "group_ref": p.get("group_ref"),
                "run_ref": p.get("run_ref"),
                "job_id": p.get("job_id"),
                "slots": p.get("slots") or [],
                "created_at": p.get("created_at"),
            }
            for p in pontes
        ]
    }


@router.post("/operacoes/{project_ref}/decisoes", status_code=status.HTTP_201_CREATED)
async def decidir(
    project_ref: ProjectRef,
    pedido: PedidoDeDecisao,
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
) -> dict[str, Any]:
    try:
        await repo.obter_operacao(project_ref, identidade.sub)
        run = await repo.obter_run(pedido.run_ref, identidade.sub)
    except NaoEncontrado as exc:
        raise _erro("CRIATIVO_AGENTE_ALVO_INEXISTENTE", "Operação ou run não encontrada.", 404) from exc
    if run.get("project_ref") != project_ref or run.get("status") != "COMPLETED":
        raise _erro("CRIATIVO_AGENTE_ALVO_INVALIDO", "A decisão não aponta para uma run concluída desta operação.", 409)
    try:
        snapshot = resolver_caminho(run["output"], pedido.caminho)
    except CaminhoInvalido as exc:
        raise _erro(
            "CRIATIVO_AGENTE_CAMINHO_INVALIDO",
            f"O caminho não endereça nada estável na saída escolhida: {exc.motivo}.",
            422,
        ) from exc
    row = await repo.registrar_decisao(
        {
            "decision_ref": _ref("crdec_"),
            "project_ref": project_ref,
            "run_ref": pedido.run_ref,
            "owner_id": identidade.sub,
            "decisao": pedido.decisao,
            "scope": pedido.escopo.value,
            "path": pedido.caminho,
            "snapshot": snapshot,
            "snapshot_sha256": _hash_valor(snapshot),
            "feedback": pedido.feedback,
        }
    )
    return {"decision_ref": row["decision_ref"], "decisao": row["decisao"], "snapshot_sha256": row["snapshot_sha256"]}
