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
)
from app.criativo.agente.caminhos import CaminhoInvalido, resolver as resolver_caminho
from app.criativo.agente.orquestrador import AgenteCriativoMeta, RespostaDoModeloInvalida
from app.criativo.agente.persistencia import NaoEncontrado, RepositorioAgenteCriativo
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
    return {"operacao": operacao, "runs": runs}


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
