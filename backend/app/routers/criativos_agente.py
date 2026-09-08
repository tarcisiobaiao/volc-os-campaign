"""API autenticada do Assistente de Criativos Meta.

As rotas criam estratégia, briefs e, mediante autorização de gasto, imagens.
Nenhuma delas chama Meta Ads ou publica campanha. Exportar copy é só leitura.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

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
from app.criativo.studio.contrato import MAX_RENDERS_POR_PEDIDO
from app.criativo.studio.autorizacao import (
    SeloInvalido,
    assinatura_do_plano,
    conferir_selo,
    emitir_selo,
)
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


@router.get("/capacidades")
async def capacidades(
    identidade: Identidade = Depends(exigir_usuario),
) -> dict[str, Any]:
    """O catálogo de formatos e a identidade do motor. UMA autoridade, no servidor.

    ## O defeito que esta rota fecha

    O catálogo vivia em TRÊS lugares: `app/criativo/dominio.py::FORMATOS` (4
    slots, a verdade do motor), `src/types/criativos.ts::FORMATOS_DE_IMAGEM`
    (espelhado e conferido por teste) e
    `src/features/creative-studio/api.ts::FORMATOS_DO_MOTOR` — uma terceira
    cópia, escrita à mão, com **três** slots. O Assistente Criativo nunca
    ofereceu o `1.91x1` porque a lista dele estava desatualizada, e nada quebrava:
    uma constante a menos não falha teste nenhum, ela só some da tela.

    Um catálogo que o frontend BUSCA não pode divergir, porque não existe segunda
    cópia para divergir. É por isso que esta rota existe, e é por isso que a
    constante do `api.ts` foi apagada em vez de corrigida.

    ## O que cada formato declara, e por que

    `canvas_nativo` e `transformacao_final` são a resposta honesta a "esta peça
    foi composta neste formato ou recortada de outro?". O `gpt-image-2` não
    aceita 1080x1350 (as bordas precisam ser múltiplas de 16), então TODA peça
    passa por um canvas nativo e uma normalização — esconder isso faria a tela
    prometer uma composição nativa que não existe.

    Nada aqui gasta, chama provider ou lê banco: é o contrato do processo.
    """
    from app.criativo import dominio  # noqa: PLC0415

    motor = _motor_ou_none()
    identidade_do_motor = _identidade_do_motor()
    envelope = _envelope_do_motor(motor)

    formatos = []
    for formato in dominio.FORMATOS:
        canvas = envelope(formato.largura, formato.altura) if envelope else None
        formatos.append(
            {
                "slot": formato.slot,
                "rotulo": formato.rotulo,
                "proporcao": formato.proporcao,
                "largura": formato.largura,
                "altura": formato.altura,
                "descricao": formato.descricao,
                "destinos_tipicos": list(formato.destinos_tipicos),
                "canvas_nativo": (
                    None
                    if canvas is None
                    else {
                        "largura": canvas.largura,
                        "altura": canvas.altura,
                        # ⚠️ Derivado da RAZÃO, e não de `canvas.derivado`.
                        # `derivado` responde "o canvas foi calculado ou é um
                        # nomeado?", que é outra pergunta: para 1200x628 ele é
                        # `True` e a razão NÃO bate (1,9189 contra 1,9108), ou
                        # seja, o único slot que recorta era o que dizia
                        # "proporção preservada".
                        "proporcao_preservada": _mesma_razao(canvas, formato),
                        "observacao": canvas.motivo or None,
                    }
                ),
                "transformacao_final": _transformacao_final(canvas, formato),
                "aceita_fotografia_real": True,
            }
        )

    return {
        "formatos": formatos,
        "teto_de_renders_por_pedido": MAX_RENDERS_POR_PEDIDO,
        "motor": {
            "modelo": identidade_do_motor["modelo"],
            "qualidade": identidade_do_motor["qualidade"],
            "configurado": identidade_do_motor["configurado"],
            "publica_preco_por_imagem": (
                getattr(motor, "preco_referencia_usd_por_imagem", None) is not None
            ),
        },
        "modos_de_composicao": [
            {
                "id": "sem_foto",
                "rotulo": "Gerar a arte inteira",
                "descricao": (
                    "O modelo compõe a peça toda a partir da direção aprovada. "
                    "Nenhuma fotografia é usada."
                ),
                "preserva_pixels_da_foto": False,
            },
            {
                "id": "hibrido",
                "rotulo": "Compor com a fotografia",
                "descricao": (
                    "A fotografia entra nos pixels finais sem ser regerada; o modelo "
                    "produz o entorno e um compositor determinístico junta os dois."
                ),
                "preserva_pixels_da_foto": True,
            },
            {
                "id": "reinterpretado",
                "rotulo": "Reinterpretar com IA",
                "descricao": (
                    "A fotografia entra como referência e o modelo redesenha a cena. "
                    "Semelhança, rosto e detalhes podem mudar."
                ),
                "preserva_pixels_da_foto": False,
            },
        ],
    }


def _mesma_razao(canvas: Any, formato: Any) -> bool:
    """A proporção do canvas é a do formato, dentro da tolerância?"""
    alvo = formato.largura / formato.altura
    return abs((canvas.largura / canvas.altura) - alvo) / alvo <= 1e-6


def _transformacao_final(canvas: Any, formato: Any) -> str | None:
    """O que acontece com os pixels DEPOIS do provider, dito com o sinal certo.

    ⚠️ Este campo publicava `reducao_e_recorte_centralizado` para 100% do
    catálogo, e estava errado nas quatro linhas. Os quatro canvases nativos são
    MENORES que a medida final (1024x1024, 1024x1280, 864x1536, 1136x592), então
    a normalização AMPLIA — e em três deles a razão bate exatamente, ou seja,
    não há recorte nenhum.

    O campo existe para responder "esta peça foi composta neste formato ou
    recortada de outro?". Uma resposta que diz "reduzida e recortada" quando
    houve ampliação sem recorte é pior que campo nenhum: ela parece conferida.
    """
    if canvas is None:
        return None
    if (canvas.largura, canvas.altura) == (formato.largura, formato.altura):
        return "nenhuma"
    sentido = "ampliacao" if canvas.largura < formato.largura else "reducao"
    if _mesma_razao(canvas, formato):
        return f"{sentido}_proporcional"
    return f"{sentido}_e_recorte_centralizado"


def _envelope_do_motor(motor: Any):
    """A função de canvas nativo do motor, quando ele tem uma.

    Cada provider tem o seu envelope: o `gpt-image-2` aceita dimensão arbitrária
    sob quatro regras aritméticas, e o Gemini aceita uma lista fechada de
    proporções. Um `if` por provider aqui recriaria, no router, a decisão que já
    mora no motor — então o router pergunta ao motor e aceita `None` como
    resposta.
    """
    if motor is None:
        return None
    if getattr(motor, "slug", "") == "openai-gpt-image-2":
        from services.creative_engine.envelope_openai import (  # noqa: PLC0415
            canvas_para,
        )

        return canvas_para
    return None


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
    if len(decisoes) >= 1000:
        raise _erro(
            "CRIATIVO_AGENTE_DECISOES_INCOMPLETAS",
            "O histórico de decisões atingiu o limite de leitura. Não é seguro reutilizar aprovações.",
            409,
        )
    aprovados = _aprovados_validos(run["output"], _decisoes_efetivas(decisoes))
    return operacao, SaidaDoAgente.model_validate(run["output"]), aprovados


@router.get("/operacoes/{project_ref}/runs/{run_ref}/copy-de-campanha/{creative_ref}")
async def copy_de_campanha(
    project_ref: ProjectRef,
    run_ref: RunRef,
    creative_ref: Annotated[str, Path(pattern=r"^creative_[a-z0-9_-]{3,64}$")],
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
) -> dict[str, Any]:
    """Projeção de copy aprovada para um rascunho, não permissão de publicação.

    O navegador fornece referências, nunca texto a certificar. A aprovação é
    conferida novamente no servidor. Texto na arte não vira texto de anúncio.
    O hash identifica o snapshot lido; não é assinatura nem aprovação de mídia.
    """
    _, lote, aprovados = await _lote_e_aprovados(project_ref, run_ref, identidade, repo)
    if lote.project_ref != project_ref or not lote.recibo.valido:
        raise _erro("CRIATIVO_COPY_LOTE_INVALIDO", "O lote não tem validação de contrato válida.", 409)
    pecas = [p for p in lote.pecas if p.ref == creative_ref]
    if len(pecas) != 1:
        raise _erro("CRIATIVO_COPY_PECA_INVALIDA", "A peça não é identificável neste lote.", 409)
    peca = pecas[0]
    copies = [c for c in lote.copies_compartilhadas if c.ref == peca.shared_copy_ref]
    if len(copies) != 1 or copies[0].group_ref != peca.group_ref:
        raise _erro("CRIATIVO_COPY_VINCULO_INVALIDO", "A copy não corresponde à direção desta peça.", 409)
    copy = copies[0]
    # The strategist supports DOWNLOAD, but our campaign recipe does not.
    # Consult its canonical validator instead of silently changing the CTA.
    from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta, VariacaoEstaticaMeta
    try:
        VariacaoEstaticaMeta(
            variation_key="copy-check", creative_name="Copy", ad_name="Copy",
            asset_ref="copy-validation-only", message=copy.texto_principal,
            headline=copy.titulo, description=copy.descricao, call_to_action_type=copy.cta_nativa,
        )
    except ErroDeNascimentoMeta as exc:
        raise _erro("CRIATIVO_COPY_RECEITA_INCOMPATIVEL", "O texto ou botão não é compatível com o contrato da campanha. Ajuste e aprove novamente.", 409) from exc
    if not {f"/pecas/{peca.ref}", f"/copies_compartilhadas/{copy.ref}"}.issubset(aprovados):
        raise _erro(
            "CRIATIVO_COPY_APROVACAO_PENDENTE",
            "Aprove a peça e o texto do anúncio antes de usá-los no rascunho.",
            409,
        )
    snapshot = {
        "project_ref": project_ref, "run_ref": run_ref,
        "creative_ref": peca.ref, "copy_ref": copy.ref,
        "copy_sha256": _hash_valor(copy.model_dump(mode="json")),
        "message": copy.texto_principal, "headline": copy.titulo,
        "description": copy.descricao, "cta": copy.cta_nativa,
    }
    return {
        **snapshot, "snapshot_sha256": _hash_valor(snapshot),
        "scope": "DRAFT_COPY_ONLY", "launch_authorized": False,
        "media_registered": False,
    }


def _identidade_do_motor() -> dict[str, Any]:
    """Qual motor de imagem ESTE processo usaria, sem chamar nada e sem chave.

    A tela precisa nomear o modelo antes do clique — "gerar" sem dizer com o quê
    é pedir autorização em branco. Construir o motor só lê o ambiente; nenhuma
    requisição sai daqui.

    Devolve `modelo: None` quando o pacote do motor nem existe no ambiente, em
    vez de derrubar a rota de PLANO: planejar precisa continuar funcionando para
    mostrar o bloqueio, e um plano que não abre esconde a causa.
    """
    motor = _motor_ou_none()
    if motor is None:
        return {"modelo": None, "qualidade": None, "configurado": False}
    return {
        "modelo": getattr(motor, "nome", None),
        "qualidade": getattr(motor, "qualidade", None),
        "configurado": bool(getattr(motor, "configurado", False)),
    }


def _motor_ou_none() -> Any:
    """O motor de imagem deste processo, ou `None` quando não dá para construí-lo.

    `None` em vez de exceção porque PLANEJAR precisa continuar funcionando: um
    plano que não abre esconde a causa, e a causa é exatamente o que a tela
    precisa mostrar como bloqueio.
    """
    try:
        from app.routers.criativos import obter_motor  # noqa: PLC0415

        return obter_motor()
    except Exception:  # noqa: BLE001
        return None


def _segredo_do_selo() -> str:
    """O segredo que sela o plano. Sem ele, não há autorização a emitir.

    É o MESMO segredo que assina os links de arquivo (`segredo_de_assinatura`),
    porque os dois protegem atos do mesmo servidor e um segundo segredo seria
    mais uma chave para rotacionar sem ganho de isolamento.
    """
    from app.criativo.armazenamento import segredo_de_assinatura  # noqa: PLC0415

    return segredo_de_assinatura()


async def _anexo_do_pedido(
    pedido: PedidoDeGeracao,
    project_ref: str,
    identidade: Identidade,
    repo: RepositorioAgenteCriativo,
) -> dict[str, Any] | None:
    """A fotografia deste pedido, conferida contra o DONO e contra a operação.

    Ref opaca não é autorização. O filtro de dono viaja no `where` de
    `obter_anexo`, e a operação é conferida aqui: um anexo válido de OUTRA
    operação do mesmo dono continua sendo material que esta operação não pediu.

    `None` quando não há foto ou quando ela não resolve — e `montar_plano`
    transforma esse `None` em bloqueio visível, em vez de produzir uma peça
    diferente da pedida.
    """
    if not pedido.anexo_ref:
        return None
    linha = await repo.obter_anexo(pedido.anexo_ref, identidade.sub)
    if linha is None or linha.get("project_ref") != project_ref:
        return None
    return linha


def _assinatura_do_plano(
    pedido: PedidoDeGeracao, plano: PlanoDeGeracao, motor: Any
) -> str:
    """A identidade do CONTEÚDO do plano, recalculada do zero no servidor.

    Recalcular é o ponto: o cliente devolve um selo, não uma assinatura. Se o
    servidor aceitasse a assinatura que o cliente mandou, ela provaria apenas que
    o cliente sabe digitar 64 caracteres.
    """
    return assinatura_do_plano(
        run_ref=pedido.run_ref,
        creative_refs=pedido.selected_creative_refs,
        format_ids=pedido.format_ids,
        modelo=getattr(motor, "nome", None),
        qualidade=getattr(motor, "qualidade", None),
        total_de_renders=plano.total_de_renders,
        custo_estimado_usd=plano.custo_estimado_usd,
        anexo_sha256=plano.anexo_sha256,
        modo_de_composicao=plano.modo_de_composicao,
    )


def _conferir_autorizacao(
    autorizacao: AutorizacaoDeGasto | None,
    plano: PlanoDeGeracao,
    motor: Any,
    assinatura_do_plano_atual: str,
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
    - `selo_do_plano`: amarra o consentimento ao CONTEÚDO exato do plano e lhe dá
      prazo. Sem ele, autorizar {peça A, peça B} × {1x1} e produzir
      {peça C, peça D} × {1x1} passava nas três conferências acima — modelo
      igual, total igual —, e o lote que rodava não era o que a pessoa leu.

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
    # ⚠️ `not nome_do_motor` recusa, e isso é conserto. Antes a conferência era
    # `if nome_do_motor and ...`: um motor que não se nomeia — um adaptador novo,
    # um dublê que escapasse para produção — transformava "não sei qual motor vai
    # rodar" em "autorizado". Um motor anônimo não pode receber consentimento
    # nominal.
    if not nome_do_motor or autorizacao.modelo != nome_do_motor:
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

    # ⚠️ Estimativa ausente com teto declarado era ignorada em silêncio, e o
    # `gpt-image-2` fez disso a regra e não a exceção: a OpenAI cobra por token e
    # não publica dólar por imagem, então `custo_estimado_usd` é SEMPRE `None`
    # para ele. O operador digitava um teto, o servidor não tinha o que comparar,
    # e o lote inteiro rodava com o teto na tela parecendo respeitado.
    #
    # Agora a ausência é dita: ou a pessoa marca que aceita gastar sem estimativa,
    # ou o pedido é recusado. Nada é criado nos dois casos.
    if estimado is None and not autorizacao.aceito_sem_estimativa:
        raise HTTPException(
            409,
            detail={
                "codigo": "CRIATIVO_STUDIO_SEM_ESTIMATIVA_DE_CUSTO",
                "mensagem": (
                    "Este motor não publica preço por imagem, então não há estimativa "
                    "a conferir contra um teto. Confirme que aceita produzir "
                    f"{plano.total_de_renders} imagem(ns) sem estimativa de custo."
                ),
                "modelo_de_imagem": nome_do_motor,
                "total_de_renders": plano.total_de_renders,
                "custo_estimado_usd": None,
                "teto_custo_usd": teto,
                "limite_efetivo": "quantidade_de_imagens",
                "nada_foi_criado": True,
            },
        )

    # O selo é a última porta, e é a que amarra tudo o que veio antes ao CONTEÚDO
    # do plano. As conferências acima olham três números; esta olha o pedido
    # inteiro, e é a única que recusa "mesmo modelo, mesmo total, outras peças".
    try:
        selada = conferir_selo(autorizacao.selo_do_plano, segredo=_segredo_do_selo())
    except SeloInvalido as e:
        raise HTTPException(
            409,
            detail={
                "codigo": "CRIATIVO_STUDIO_AUTORIZACAO_VENCIDA",
                "mensagem": (
                    "A conferência deste plano não vale mais. Confira o pedido de "
                    "novo antes de autorizar."
                ),
                "nada_foi_criado": True,
            },
        ) from e
    except (RuntimeError, ValueError) as e:
        raise HTTPException(
            503,
            detail={
                "codigo": "CRIATIVO_STUDIO_SEM_SEGREDO_DE_ASSINATURA",
                "mensagem": (
                    "O Estúdio está indisponível: o servidor está sem chave de "
                    "assinatura para selar a autorização."
                ),
                "nada_foi_criado": True,
            },
        ) from e

    if selada != assinatura_do_plano_atual:
        raise HTTPException(
            409,
            detail={
                "codigo": "CRIATIVO_STUDIO_PLANO_DIVERGENTE",
                "mensagem": (
                    "O que foi autorizado não é o que este pedido produz. Confira o "
                    "plano de novo e confirme."
                ),
                "nada_foi_criado": True,
            },
        )


def _plano_para_json(plano: PlanoDeGeracao, selo: str | None = None) -> dict[str, Any]:
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
        # `false` quando o motor não publica preço por imagem. A tela usa isto
        # para pedir o consentimento explícito de gastar sem estimativa, em vez
        # de desenhar um campo de teto que o servidor não teria como honrar.
        "custo_tem_estimativa": plano.custo_estimado_usd is not None,
        "modo_de_composicao": plano.modo_de_composicao,
        "anexo_sha256": plano.anexo_sha256,
        "modelo_de_imagem": motor["modelo"],
        "qualidade_de_imagem": motor["qualidade"],
        "motor_configurado": motor["configurado"],
        "pode_executar": plano.pode_executar,
        "bloqueios": [b.model_dump() for b in plano.bloqueios],
        # O selo que a autorização precisa devolver. Ausente quando o plano não
        # pode executar: não há o que autorizar, e emitir um selo para um plano
        # bloqueado convidaria o cliente a tentar mesmo assim.
        "selo_do_plano": selo,
        "briefings": [
            {
                "creative_ref": b.linhagem.creative_ref,
                "formato_slot": b.formato_slot,
                "texto_na_arte": b.texto_na_arte,
                "direcao_visual": b.direcao_visual,
            }
            for b in plano.briefings
        ],
    }


def _selo_do_plano(pedido: PedidoDeGeracao, plano: PlanoDeGeracao, motor: Any) -> str | None:
    """Emite o selo, ou `None` quando não há o que selar.

    Um plano bloqueado não recebe selo: emitir um convidaria o cliente a mandar
    o POST de geração mesmo assim, e a recusa aconteceria mais tarde, com mais
    caminho percorrido, para dizer a mesma coisa que o bloqueio já dizia.

    Falta de segredo também devolve `None` em vez de derrubar o PLANO: planejar
    precisa continuar respondendo para que a tela mostre o motivo.
    """
    if not plano.pode_executar:
        return None
    try:
        return emitir_selo(
            _assinatura_do_plano(pedido, plano, motor), segredo=_segredo_do_selo()
        )
    except (RuntimeError, ValueError):
        return None


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
    # O motor entra no plano porque o PREÇO é dele. Antes o custo vinha de uma
    # constante do motor Gemini importada direto, e um plano de outro provider
    # exibia o preço de um motor que não seria chamado.
    motor = _motor_ou_none()
    anexo = await _anexo_do_pedido(pedido, project_ref, identidade, repo)
    plano = montar_plano(
        saida=saida,
        pedido=pedido,
        caminhos_aprovados=aprovados,
        contexto_do_publico=entrada.get("contexto_do_publico") or "Público não declarado.",
        objetivo=entrada.get("objetivo_meta") or "OUTCOME_TRAFFIC",
        motor=motor,
        anexo=anexo,
    )
    return _plano_para_json(plano, _selo_do_plano(pedido, plano, motor))


@router.post("/operacoes/{project_ref}/geracoes", status_code=status.HTTP_201_CREATED)
async def gerar_imagens(
    project_ref: ProjectRef,
    pedido: PedidoDeGeracao,
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
) -> dict[str, Any]:
    """Preserva uma resposta JSON/CORS segura para falhas de persistencia.

    Um lote pode falhar DEPOIS de registrar ou despachar uma peca. Nao afirmar
    ausencia de efeito nem sugerir retry automatico sem consultar os jobs.
    """
    from app.criativo.persistencia import ErroDePersistencia

    try:
        return await _gerar_imagens_autorizadas(project_ref, pedido, identidade, repo)
    except ErroDePersistencia:
        raise _erro(
            "CRIATIVO_STUDIO_PERSISTENCIA_INDISPONIVEL",
            "O banco não conseguiu registrar a geração. Confira a aba Criativos "
            "antes de reenviar; um trabalho pode ter sido registrado.",
            503,
        ) from None


async def _gerar_imagens_autorizadas(
    project_ref: str,
    pedido: PedidoDeGeracao,
    identidade: Identidade,
    repo: RepositorioAgenteCriativo,
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

    from app.criativo.studio.adaptador import pedido_de_job  # noqa: PLC0415
    from app.routers.criativos import obter_executor, obter_motor  # noqa: PLC0415

    # ⚠️ O motor é CONSTRUÍDO antes do plano porque o preço e a identidade dele
    # entram no plano e na assinatura que a autorização confere. Montar o plano
    # sem o motor produziria uma assinatura sobre um modelo vazio, que nunca
    # bateria com a que a rota de plano emitiu.
    #
    # Mas a CREDENCIAL só é exigida depois dos bloqueios: uma peça não aprovada
    # é uma recusa mais útil que "o servidor está sem chave", e trocar a ordem
    # esconderia o motivo verdadeiro atrás de um problema de configuração.
    motor = obter_motor()

    entrada = operacao.get("input") or {}
    anexo = await _anexo_do_pedido(pedido, project_ref, identidade, repo)
    plano = montar_plano(
        saida=saida,
        pedido=pedido,
        caminhos_aprovados=aprovados,
        contexto_do_publico=entrada.get("contexto_do_publico") or "Público não declarado.",
        objetivo=entrada.get("objetivo_meta") or "OUTCOME_TRAFFIC",
        motor=motor,
        anexo=anexo,
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

    if not getattr(motor, "configurado", False):
        raise _erro(
            "CRIATIVO_STUDIO_MOTOR_SEM_CREDENCIAL",
            "O motor de imagem não está configurado neste servidor; nada foi criado.",
            503,
        )

    assinatura_atual = _assinatura_do_plano(pedido, plano, motor)
    _conferir_autorizacao(pedido.autorizacao, plano, motor, assinatura_atual)

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
                modo_de_composicao=pedido.modo_de_composicao,
                anexo=anexo,
                plano_sha256=assinatura_atual,
                teto_custo_usd=(
                    pedido.autorizacao.teto_custo_usd if pedido.autorizacao else None
                ),
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
        # `disparar` é SÍNCRONO até o fim: ele enfileira e roda o render, que
        # leva ~11s por peça. Chamá-lo direto de dentro da corrotina congelava o
        # event loop inteiro pela duração do lote — /health, listagem e qualquer
        # outra aba paravam de responder enquanto a primeira geração acontecia.
        # `to_thread` mantém a mesma semântica (a resposta só sai quando o
        # trabalho tem estado terminal) e devolve o loop ao resto do processo.
        await asyncio.to_thread(executor.disparar, str(job["id"]))
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


# ═══════════════════════════════════════════════════════════════════════════
# ANEXOS — a fotografia real, opcional, do operador
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/operacoes/{project_ref}/anexos", status_code=status.HTTP_201_CREATED
)
async def anexar_fotografia(
    project_ref: ProjectRef,
    request: Request,
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
) -> dict[str, Any]:
    """Recebe a fotografia, valida NOS BYTES e devolve uma referência opaca.

    ## Por que a foto não viaja em base64 pelo resto do fluxo

    Porque um base64 no estado da tela atravessa o `localStorage`, aparece em
    todo log de requisição que registre corpo, e reaparece num projeto novo se
    alguém esquecer de limpar. A referência opaca é curta, não é adivinhável, e
    a autorização de gasto é assinada contra o HASH dos bytes normalizados — de
    modo que trocar a foto depois de conferir o plano invalida a autorização em
    vez de passar despercebido.

    ## O que a validação cobre, e por que ela é toda server-side

    MIME por assinatura de bytes (o `Content-Type` do multipart é escrito pelo
    cliente), teto de bytes, teto de PIXELS antes de decodificar — que é a
    decompression bomb —, decodificação completa contra arquivo truncado, lado
    mínimo, e remoção do EXIF com a orientação aplicada aos pixels.

    ⚠️ O consentimento é exigido AQUI e não na composição: uma fotografia de
    pessoa real armazenada sem declaração é um problema no instante em que ela é
    gravada. O banco também exige, por CHECK — um `if` de rota some no dia em
    que alguém acrescentar um segundo caminho de upload.

    Nada aqui chama provider, gera imagem ou gasta.
    """
    from app.criativo.armazenamento import armazenamento_padrao  # noqa: PLC0415
    from app.criativo.studio import anexo as politica  # noqa: PLC0415

    try:
        await repo.obter_operacao(project_ref, identidade.sub)
    except NaoEncontrado as exc:
        raise _erro("CRIATIVO_AGENTE_ALVO_INEXISTENTE", "Operação não encontrada.", 404) from exc

    arquivo, mime_declarado, consentiu = await _parte_de_imagem(request)
    if not consentiu:
        raise _erro(
            "CRIATIVO_STUDIO_ANEXO_SEM_CONSENTIMENTO",
            "Confirme que você tem autorização para usar esta imagem antes de enviá-la.",
            400,
        )

    try:
        normalizado = politica.normalizar(arquivo, mime_declarado=mime_declarado)
    except politica.AnexoRecusado as exc:
        # A mensagem de `AnexoRecusado` é escrita para o operador e não cita
        # caminho de disco, biblioteca nem traceback.
        raise _erro("CRIATIVO_STUDIO_ANEXO_RECUSADO", str(exc), 400) from exc

    chave = politica.chave_de_anexo(
        identidade.sub, normalizado.ref, normalizado.extensao
    )
    try:
        armazenamento_padrao().guardar(chave, normalizado.conteudo, normalizado.mime)
    except Exception as exc:  # noqa: BLE001
        raise _erro(
            "CRIATIVO_STUDIO_ANEXO_NAO_ARMAZENADO",
            "Não foi possível guardar a imagem agora. Tente novamente.",
            503,
        ) from exc

    linha = await repo.registrar_anexo(
        {
            "anexo_ref": normalizado.ref,
            "owner_id": identidade.sub,
            "project_ref": project_ref,
            "storage_chave": chave,
            "mime": normalizado.mime,
            "largura": normalizado.largura,
            "altura": normalizado.altura,
            "bytes_totais": len(normalizado.conteudo),
            "content_sha256": normalizado.content_sha256,
            "exif_removido": normalizado.exif_removido,
            "consentimento": True,
        }
    )
    return _anexo_para_json(linha)


@router.get("/operacoes/{project_ref}/anexos")
async def listar_anexos(
    project_ref: ProjectRef,
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
) -> dict[str, Any]:
    """As fotografias vivas desta operação. Só as do dono, só as não removidas."""
    try:
        await repo.obter_operacao(project_ref, identidade.sub)
    except NaoEncontrado as exc:
        raise _erro("CRIATIVO_AGENTE_ALVO_INEXISTENTE", "Operação não encontrada.", 404) from exc
    linhas = await repo.listar_anexos(project_ref, identidade.sub)
    return {"anexos": [_anexo_para_json(linha) for linha in linhas]}


@router.delete("/operacoes/{project_ref}/anexos/{anexo_ref}")
async def remover_anexo(
    project_ref: ProjectRef,
    anexo_ref: Annotated[str, Path(pattern=r"^crimg_[a-f0-9]{24}$")],
    identidade: Identidade = Depends(exigir_usuario),
    repo: RepositorioAgenteCriativo = Depends(obter_repositorio),
) -> dict[str, Any]:
    """Tira a foto de circulação SEM apagar a linha.

    Apagar quebraria a procedência de um job que já a usou: a peça continuaria
    existindo e "de qual imagem ela saiu?" perderia a resposta. Trocar a foto é
    um ato do operador; apagar a história não é.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    removeu = await repo.remover_anexo(
        anexo_ref, identidade.sub, em=datetime.now(timezone.utc).isoformat()
    )
    if not removeu:
        # 404 idêntico para "não existe" e "não é seu": distinguir os dois
        # transforma a rota num oráculo de existência de anexo alheio.
        raise _erro(
            "CRIATIVO_STUDIO_ANEXO_INEXISTENTE", "Anexo não encontrado.", 404
        )
    return {"anexo_ref": anexo_ref, "removido": True}


def _anexo_para_json(linha: dict[str, Any]) -> dict[str, Any]:
    """O que a tela precisa. A chave de storage NÃO vai junto.

    Ela é caminho interno: publicá-la ensina o formato do bucket a quem só
    precisa saber que a foto existe, e `design.md` proíbe expor nome de tabela e
    caminho interno ao operador pelo mesmo motivo.
    """
    return {
        "anexo_ref": linha.get("anexo_ref"),
        "mime": linha.get("mime"),
        "largura": linha.get("largura"),
        "altura": linha.get("altura"),
        "bytes_totais": linha.get("bytes_totais"),
        "content_sha256": linha.get("content_sha256"),
        "exif_removido": linha.get("exif_removido"),
        "criado_em": linha.get("criado_em"),
    }


#: Teto de corpo do upload, com folga para os cabeçalhos do multipart.
#:
#: O teto de CONTEÚDO é o de `studio/anexo.py` (25 MB). Este é maior de
#: propósito: recusar aqui um corpo que caberia depois do envelope trocaria uma
#: mensagem sobre a imagem por uma mensagem sobre protocolo.
_TETO_DO_CORPO = 27 * 1024 * 1024


async def _parte_de_imagem(request: Request) -> tuple[bytes, str | None, bool]:
    """Lê o `multipart/form-data` à mão, e a razão é declarada.

    `python-multipart` NÃO está instalado neste backend e não está em
    `requirements.txt`. O FastAPI levanta ao MONTAR uma rota com `File(...)` ou
    `Form(...)` sem ele — o backend inteiro deixaria de subir por causa desta
    rota. É o mesmo motivo, com as mesmas palavras, que `criativos_importacao.py`
    já documenta; o leitor dele é reusado aqui em vez de duplicado.

    Devolve `(bytes, mime declarado, consentimento)`. O MIME declarado é o que o
    cliente escreveu e serve APENAS para ser conferido contra a assinatura dos
    bytes; ele nunca decide nada sozinho.
    """
    from app.routers.criativos_importacao import _ler_multipart  # noqa: PLC0415

    tipo = request.headers.get("content-type", "")
    if "multipart/form-data" not in tipo.lower():
        raise _erro(
            "CRIATIVO_STUDIO_ANEXO_PEDIDO_INVALIDO",
            "Envie a imagem como multipart/form-data.",
            400,
        )
    corpo = await request.body()
    if len(corpo) > _TETO_DO_CORPO:
        raise _erro(
            "CRIATIVO_STUDIO_ANEXO_GRANDE_DEMAIS",
            "O envio passa do tamanho que este servidor aceita.",
            413,
        )

    try:
        partes = _ler_multipart(corpo, tipo)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _erro(
            "CRIATIVO_STUDIO_ANEXO_PEDIDO_INVALIDO",
            "Envie a imagem como multipart/form-data.",
            400,
        ) from exc

    dados: bytes | None = None
    consentiu = False
    for parte in partes:
        if parte.arquivo is not None and dados is None:
            dados = parte.conteudo
        elif parte.nome == "consentimento":
            consentiu = parte.conteudo.strip().lower() in (b"1", b"true", b"sim", b"on")

    if not dados:
        raise _erro(
            "CRIATIVO_STUDIO_ANEXO_AUSENTE", "Nenhuma imagem foi enviada.", 400
        )
    # ⚠️ O MIME declarado sai como `None` DE PROPÓSITO, e não porque foi
    # esquecido. `_ler_multipart` guarda nome, arquivo e conteúdo, e descarta os
    # cabeçalhos de cada parte — então não há `Content-Type` de parte para
    # conferir. A alternativa seria adivinhar pelo sufixo do nome do arquivo, e
    # adivinhar seria PIOR que não conferir: uma foto legítima renomeada de
    # `.jpeg` para `.png` viraria recusa, e a extensão não é evidência de
    # conteúdo nenhum.
    #
    # A guarda real é a assinatura de bytes, que `anexo.normalizar` aplica
    # sozinha por allowlist. A conferência declarado-contra-bytes continua viva
    # no módulo, para quem chame com um `Content-Type` de verdade.
    return dados, None, consentiu
