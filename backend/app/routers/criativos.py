"""HTTP do Estúdio Criativo. Adaptação de entrada e saída, e nada mais.

Regra mora em `app/criativo/dominio.py`, orquestração em `execucao.py`,
persistência em `persistencia.py`, tradução para o browser em `apresentacao.py`.
Este arquivo só converte request em chamada e resultado em resposta, e é o lugar
onde os códigos HTTP são decididos.

## Os códigos, e por que cada um

`201` job novo · `200` reenvio reconhecido (idempotência) · `400` pedido
inválido do cliente · `403` sem permissão ou token de arquivo inválido ·
`404` não existe · `409` transição impossível no estado atual ·
`503` servidor sem configuração.

O par 200/201 é o que torna a idempotência visível: um cliente que recebe 200
com `X-Criativo-Idempotente: replay` sabe que nada novo foi produzido e que
nada foi cobrado de novo.

## Por que a autenticação do stream é por header, e não por token na URL

`EventSource` não manda header, e a saída fácil para isso é pendurar o token de
sessão na query string. Uma URL com token entra em log de proxy, em histórico e
em qualquer print de tela, e o token de sessão do Supabase vale para a API
inteira. Aqui o stream exige o mesmo `Authorization` das outras rotas e o
frontend consome com `fetch` + `ReadableStream`, que aceita header.

O único token que viaja em URL é o de ARQUIVO, e ele é de outra espécie: assina
UMA chave de storage, expira em minutos e não autoriza mais nada.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.criativo import apresentacao, dominio, parque, video_observado, video_ponte
from app.criativo.armazenamento import (
    ArquivoRecusado,
    Assinador,
    ObjetoNaoEncontrado,
    TokenInvalido,
    armazenamento_padrao,
    segredo_de_assinatura,
)
from app.criativo.execucao import Executor, JobNaoEncontrado, TransicaoInvalida
from app.criativo.persistencia import (
    ConflitoDeChave,
    ErroDePersistencia,
    ReferenciaInvalida,
    Repositorio,
    agora,
)
from app.seguranca.identidade import Identidade, exigir_admin, exigir_usuario
from app.seguranca.link_assinado import exigir_link_assinado

log = logging.getLogger("volc.criativo.http")

router = APIRouter(prefix="/api/criativos", tags=["criativos"])


# ─────────────────────────────────────────────────────────────────────────────
# Composição
# ─────────────────────────────────────────────────────────────────────────────


def _falha(codigo: str, mensagem: str, status: int) -> HTTPException:
    """Erro com forma estável. O frontend lê `detail.mensagem` e mostra."""
    return HTTPException(status_code=status, detail={"codigo": codigo, "mensagem": mensagem})


# Os estados de REVISÃO que a biblioteca sabe filtrar. `aguardando` não é uma
# decisão: é a ausência dela, e por isso não vem de `DecisaoDeAprovacao`.
_ESTADOS_DE_REVISAO = frozenset(
    {"aguardando", "aprovado", "ajuste_solicitado", "rejeitado"}
)

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _uuid_ou_404(valor: str, o_que: str) -> str:
    """Recusa id malformado ANTES de perguntar ao banco.

    ⚠️ Sem isto, `GET /assets/observado:short_odete` (id que a própria rota de
    vídeo emite) chegava ao PostgREST, voltava `22P02 invalid input syntax for
    type uuid`, era classificado como `ErroDePersistencia` e virava **503 "o
    Estúdio está fora do ar"**. O operador ia procurar defeito de infraestrutura
    onde a resposta certa era "isto não existe".
    """
    if not _UUID.match(valor or ""):
        raise _falha(f"ESTUDIO.{o_que}_inexistente", "Este item não existe.", 404)
    return valor


def obter_repo(settings: Settings = Depends(get_settings)) -> Repositorio:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise _falha(
            "ESTUDIO.sem_configuracao",
            "O Estúdio está indisponível: o servidor está sem configuração de banco.",
            503,
        )
    return Repositorio(settings.supabase_url, settings.supabase_service_role_key)


def obter_assinador() -> Assinador:
    try:
        return Assinador(segredo_de_assinatura())
    except (RuntimeError, ValueError) as e:
        raise _falha(
            "ESTUDIO.sem_configuracao",
            "O Estúdio está indisponível: o servidor está sem chave de assinatura.",
            503,
        ) from e


_motor_cache: Any = None


def obter_motor() -> Any:
    """O motor de imagem do processo.

    Importado tarde, dentro da função, pelo mesmo motivo documentado em
    `main.py` para o router de Tráfego: o pacote puxa dependências que um
    ambiente mínimo pode não ter, e importá-lo no topo faria o backend inteiro
    deixar de subir por causa de um módulo opcional.
    """
    global _motor_cache
    if _motor_cache is None:
        from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem

        _motor_cache = MotorGeminiImagem()
    return _motor_cache


_executor_cache: dict[str, Executor] = {}


def obter_executor(
    repo: Repositorio = Depends(obter_repo),
    assinador: Assinador = Depends(obter_assinador),
) -> Executor:
    """UM executor por processo, e isso é conserto, não otimização.

    ⚠️ Antes ele era construído a cada request. `Executor._em_voo` e
    `Executor._trava` nasciam vazios em toda chamada, então a trava que existe
    para impedir dois disparos do mesmo job NUNCA via o disparo da requisição
    vizinha. Duas chamadas simultâneas a `POST /jobs/{id}/retry` passavam as
    duas pelo `pode_retentar`, disparavam os dois laços, e o mesmo slot era
    gerado e COBRADO duas vezes.

    O banco ainda barra a duplicata de master, mas ele barra depois da chamada
    paga. A trava só serve se for a mesma trava.
    """
    chave = f"{repo.base}"
    existente = _executor_cache.get(chave)
    if existente is None:
        existente = Executor(repo, armazenamento_padrao(), obter_motor(), assinador)
        _executor_cache[chave] = existente
    else:
        # O repositório e o assinador são recriados por request (dependem de
        # `settings`); o ESTADO de concorrência é que precisa sobreviver.
        existente.repo = repo
        existente.assinador = assinador
        # O Resolvedor segura a propria referencia ao repositorio; sem esta
        # linha ele ficaria preso ao da PRIMEIRA requisicao do processo.
        existente._resolvedor.usar(repo)
    return existente


# ─────────────────────────────────────────────────────────────────────────────
# Entrada
# ─────────────────────────────────────────────────────────────────────────────


class PedidoDeJobDeImagem(BaseModel):
    projetoTitulo: str = Field(min_length=1, max_length=200)
    objetivo: str = Field(default="", max_length=2000)
    mensagem: str = Field(min_length=1, max_length=2000)
    audiencia: Optional[str] = Field(default=None, max_length=500)
    brandPackId: Optional[str] = None
    modo: str = "full_llm"
    slots: list[str] = Field(min_length=1, max_length=6)
    destinosPretendidos: list[str] = Field(default_factory=list, max_length=12)


class PedidoDeAprovacao(BaseModel):
    decisao: str
    finalidade: str = Field(default="interno", max_length=64)
    motivo: Optional[str] = Field(default=None, max_length=1000)


# ─────────────────────────────────────────────────────────────────────────────
# Catálogo e resumo
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/formatos")
async def formatos(_: Identidade = Depends(exigir_usuario)) -> dict[str, Any]:
    return {
        "formatos": [
            {
                "slot": f.slot,
                "rotulo": f.rotulo,
                "proporcao": f.proporcao,
                "largura": f.largura,
                "altura": f.altura,
                "descricao": f.descricao,
                "destinosTipicos": list(f.destinos_tipicos),
            }
            for f in dominio.FORMATOS
        ],
        "motorConfigurado": bool(getattr(obter_motor(), "configurado", False)),
    }


@router.get("/parque")
async def parque_criativo(
    _: Identidade = Depends(exigir_usuario),
    repo: Repositorio = Depends(obter_repo),
) -> dict[str, Any]:
    """O catálogo que o banco arbitra: motores, modos, formatos, skins, vozes, gates.

    ⚠️ **Esta rota não substitui `GET /formatos`, e isso é deliberado.**

    `/formatos` serve `dominio.FORMATOS` — os 4 slots que o executor sabe produzir.
    Esta rota serve os 7 que o banco declara. Trocar uma pela outra faria a tela
    oferecer `16x9`, `3x4` e `video-9x16` para o motor recusar depois do clique, com
    `SlotDesconhecido` → 400. Trocar "não vejo um formato que existe" por "escolhi um
    formato que falha" é piorar.

    A diferença sai em `divergencias`, com nome e dimensão dos dois lados. Quem alinhar
    as pontas vê a lista esvaziar; enquanto ela tiver linha, a linha está na tela.
    """
    leitura = await parque.Parque(repo).ler()
    return apresentacao.parque_dto(leitura)


@router.get("/brand-packs")
async def brand_packs(
    _: Identidade = Depends(exigir_usuario), repo: Repositorio = Depends(obter_repo)
) -> dict[str, Any]:
    linhas = await _ou_503(repo.listar_brand_packs())
    return {"brandPacks": [apresentacao.brand_pack_dto(l) for l in linhas]}


@router.get("/resumo")
async def resumo(
    _: Identidade = Depends(exigir_usuario),
    repo: Repositorio = Depends(obter_repo),
    assinador: Assinador = Depends(obter_assinador),
) -> dict[str, Any]:
    em_andamento = await _ou_503(repo.listar_jobs(estados=["queued", "running"], limite=8))
    falhas = await _ou_503(repo.listar_jobs(estados=["failed", "partial"], limite=8))
    aguardando = await _ou_503(repo.masters_aguardando_revisao(limite=8))
    aprovados = await _ou_503(repo.masters_aprovados_recentes(limite=6))
    contagem = await _ou_503(repo.contar_jobs_por_estado())
    total = await _ou_503(repo.contar_assets())
    packs = await _ou_503(repo.listar_brand_packs())

    # ⚠️ A decisão vigente viaja junto, e isso é conserto de uma tela que mentia.
    #
    # Sem isto, `master_dto` era chamado sem `aprovacao` e devolvia
    # `aprovacaoVigente: null` para TODO mundo. O efeito na Home era direto: o
    # bloco "Aprovados recentemente" listava a peça certa e a carimbava com o
    # selo "aguardando revisão". A lista dizia uma coisa e o selo dizia o
    # contrário, na mesma linha.
    vigentes = await _ou_503(
        repo.aprovacoes_vigentes_de(
            [str(m["id"]) for m in aguardando] + [str(m["id"]) for m in aprovados]
        )
    )

    procedencias = await _ou_503(
        repo.procedencia_dos_jobs(
            [str(m["job_id"]) for m in aguardando] + [str(m["job_id"]) for m in aprovados]
        )
    )

    def _com_decisao(m: dict[str, Any]) -> dict[str, Any]:
        linha = vigentes.get(str(m["id"]))
        return apresentacao.master_dto(
            m,
            assinador,
            aprovacao=apresentacao.aprovacao_dto(linha) if linha else None,
            procedencia_execucao=procedencias.get(str(m["job_id"])),
        )

    return {
        "emAndamento": [await _job_dto(repo, assinador, j) for j in em_andamento],
        "falhas": [await _job_dto(repo, assinador, j) for j in falhas],
        "aguardandoRevisao": [_com_decisao(m) for m in aguardando],
        "aprovadosRecentes": [_com_decisao(m) for m in aprovados],
        "contagemPorEstado": contagem,
        "totalAssets": total,
        "brandPacks": len(packs),
        "motorConfigurado": bool(getattr(obter_motor(), "configurado", False)),
        "videoDisponivel": video_observado.disponivel(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/jobs")
async def criar_job(
    pedido: PedidoDeJobDeImagem,
    resposta: Response,
    # ⚠️ `exigir_admin` e não `exigir_usuario`: esta rota GASTA DINHEIRO.
    #
    # Cada peça é uma chamada paga ao provider, e não há teto de custo, cota nem
    # limite de tentativas nesta fatia. `POST /api/trafego/subir` e
    # `/api/trafego/remover` já exigem admin pelo mesmo motivo; deixar a
    # geração atrás de "qualquer sessão válida" (inclusive uma com papel vazio)
    # seria a rota mais barata da casa para queimar a fatura de um provedor.
    #
    # Quando houver orçamento por operador, isto pode voltar a `exigir_usuario`.
    # Antes disso, não.
    identidade: Identidade = Depends(exigir_admin),
    repo: Repositorio = Depends(obter_repo),
    assinador: Assinador = Depends(obter_assinador),
    executor: Executor = Depends(obter_executor),
) -> dict[str, Any]:
    motor = obter_motor()
    if not getattr(motor, "configurado", False):
        # Recusar ANTES de gravar: aceitar um job que vai falhar por falta de
        # credencial deixaria lixo na biblioteca e faria o operador esperar por
        # nada. A SPEC §16 pede que "nunca executado" explique o que falta.
        raise _falha(
            "ESTUDIO.motor_sem_credencial",
            "O motor de imagem não está configurado neste servidor. "
            "Peça a um administrador para configurar a credencial do provedor.",
            503,
        )
    if pedido.modo != "full_llm":
        raise _falha(
            "ESTUDIO.modo_indisponivel",
            f"O modo '{pedido.modo}' ainda não está disponível. "
            "Nesta versão o Estúdio produz por geração completa do modelo.",
            400,
        )
    try:
        job, criado = await executor.criar_job_de_imagem(
            {
                "projeto_titulo": pedido.projetoTitulo,
                "objetivo": pedido.objetivo,
                "mensagem": pedido.mensagem,
                "audiencia": pedido.audiencia,
                "brand_pack_id": pedido.brandPackId,
                "modo": pedido.modo,
                "slots": pedido.slots,
                "destinos_pretendidos": pedido.destinosPretendidos,
            },
            identidade.sub,
        )
    except dominio.SlotDesconhecido as e:
        raise _falha("ESTUDIO.formato_invalido", str(e), 400) from e
    except ReferenciaInvalida as e:
        # Violação de chave estrangeira: `brandPackId` que não existe. Erro do
        # CLIENTE, e antes disso escapava do `try` e virava 500 — o servidor se
        # acusando de um defeito que era do pedido.
        raise _falha(
            "ESTUDIO.referencia_invalida",
            "Um item citado no pedido não existe. Recarregue a página e tente de novo.",
            400,
        ) from e
    except ValueError as e:
        raise _falha("ESTUDIO.pedido_invalido", str(e), 400) from e
    except ErroDePersistencia as e:
        log.error("falha ao criar job: %s", e)
        raise _falha(
            "ESTUDIO.indisponivel", "Não foi possível registrar o pedido agora.", 503
        ) from e

    if criado:
        resposta.status_code = 201
        # ⚠️ `to_thread`, e nao chamada direta. `criar_job` e `async def`, logo roda
        # NA THREAD DO EVENT LOOP, e `disparar` e sincrono ate o fim do render —
        # o despachante local declara `sincrono = True` de proposito, porque o
        # request espera. Mas esperar nao pode significar CONGELAR o loop: com a
        # chamada direta, nenhuma outra requisicao do processo era atendida
        # durante toda a producao. E o mesmo defeito que a rota da bancada tinha
        # e que `criativos_execucao._despachar` ja fechou; aqui ele ficou.
        await asyncio.to_thread(executor.disparar, str(job["id"]))
    else:
        resposta.status_code = 200
        resposta.headers["X-Criativo-Idempotente"] = "replay"
    return await _job_dto(repo, assinador, job)


@router.get("/jobs")
async def listar_jobs(
    _: Identidade = Depends(exigir_usuario),
    repo: Repositorio = Depends(obter_repo),
    assinador: Assinador = Depends(obter_assinador),
    estado: Optional[str] = None,
    limite: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    estados = [e for e in (estado or "").split(",") if e] or None
    linhas = await _ou_503(repo.listar_jobs(estados=estados, limite=limite))
    return {"jobs": [await _job_dto(repo, assinador, j) for j in linhas]}


@router.get("/jobs/{job_id}")
async def obter_job(
    job_id: str,
    _: Identidade = Depends(exigir_usuario),
    repo: Repositorio = Depends(obter_repo),
    assinador: Assinador = Depends(obter_assinador),
) -> dict[str, Any]:
    job = await _ou_503(repo.buscar_job(_uuid_ou_404(job_id, "job")))
    if job is None:
        raise _falha("ESTUDIO.job_inexistente", "Este trabalho não existe.", 404)
    return await _job_dto(repo, assinador, job)


@router.post("/jobs/{job_id}/retry")
async def retentar(
    job_id: str,
    # Retry também gasta: ele chama o provider para as peças que faltaram.
    _: Identidade = Depends(exigir_admin),
    repo: Repositorio = Depends(obter_repo),
    assinador: Assinador = Depends(obter_assinador),
    executor: Executor = Depends(obter_executor),
) -> dict[str, Any]:
    try:
        job = await executor.retentar(job_id)
    except JobNaoEncontrado as e:
        raise _falha("ESTUDIO.job_inexistente", "Este trabalho não existe.", 404) from e
    except TransicaoInvalida as e:
        raise _falha("ESTUDIO.transicao_invalida", str(e), 409) from e
    return await _job_dto(repo, assinador, job)


@router.post("/jobs/{job_id}/cancel")
async def cancelar(
    job_id: str,
    # ⚠️ `exigir_admin`. Cancelar DESTROI trabalho pago: o executor abandona as
    # peças que faltam e o dinheiro já gasto não volta. `exigir_usuario` devolve
    # `Identidade` com `papel=""` quando não há linha em `app_auth.user_roles`
    # (é o que `test_sem_linha_de_autorizacao_nao_e_admin` fixa), então qualquer
    # conta em `auth.users` interrompia a produção de outro operador.
    _: Identidade = Depends(exigir_admin),
    repo: Repositorio = Depends(obter_repo),
    assinador: Assinador = Depends(obter_assinador),
    executor: Executor = Depends(obter_executor),
) -> dict[str, Any]:
    try:
        job = await executor.cancelar(job_id)
    except JobNaoEncontrado as e:
        raise _falha("ESTUDIO.job_inexistente", "Este trabalho não existe.", 404) from e
    except TransicaoInvalida as e:
        raise _falha("ESTUDIO.transicao_invalida", str(e), 409) from e
    return await _job_dto(repo, assinador, job)


@router.get("/jobs/{job_id}/eventos")
async def eventos(
    job_id: str,
    request: Request,
    _: Identidade = Depends(exigir_usuario),
    repo: Repositorio = Depends(obter_repo),
    assinador: Assinador = Depends(obter_assinador),
    desde: int = Query(default=0, ge=0),
) -> StreamingResponse:
    """Stream de eventos a partir de um cursor.

    `desde` é a última `seq` que o cliente JÁ VIU. A reconexão manda esse número
    e recebe só o que veio depois: nem repetição, nem buraco. Um cursor por
    tempo não conseguiria a mesma coisa, porque dois eventos no mesmo
    milissegundo empatam e a ordem entre eles deixa de ser total.
    """
    job = await _ou_503(repo.buscar_job(_uuid_ou_404(job_id, "job")))
    if job is None:
        raise _falha("ESTUDIO.job_inexistente", "Este trabalho não existe.", 404)

    async def gerar():
        cursor = desde
        estado_anterior: str | None = None
        ocioso = 0
        try:
            while True:
                if await request.is_disconnected():
                    return

                novos = await repo.eventos_desde(job_id, cursor)
                for linha in novos:
                    cursor = int(linha["seq"])
                    yield _sse("evento", apresentacao.evento_dto(linha))

                atual = await repo.buscar_job(job_id)
                if atual is None:
                    return
                if atual["estado"] != estado_anterior:
                    estado_anterior = atual["estado"]
                    yield _sse("job", await _job_dto(repo, assinador, atual, cursor=cursor))

                if atual["estado"] in dominio.ESTADOS_TERMINAIS and not novos:
                    yield _sse("fim", {"estado": atual["estado"]})
                    return

                # Teto de segurança: um job preso em `running` porque o processo
                # que o executava morreu não pode manter uma conexão aberta para
                # sempre. Dez minutos sem evento fecha o stream; o cliente
                # reabre a partir do cursor e nada se perde.
                ocioso = 0 if novos else ocioso + 1
                if ocioso > 600:
                    yield _sse("fim", {"estado": atual["estado"]})
                    return
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:  # cliente foi embora
            raise
        except Exception:  # noqa: BLE001
            log.exception("stream do job %s caiu", job_id)
            yield _sse("fim", {"estado": "desconhecido"})

    return StreamingResponse(
        gerar(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # Sem isto, um proxy com buffer segura os eventos e entrega tudo no
            # fim, o que faz o stream parecer travado até o job terminar.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _sse(evento: str, dados: dict[str, Any]) -> str:
    return f"event: {evento}\ndata: {json.dumps(dados, default=str, ensure_ascii=False)}\n\n"


# ─────────────────────────────────────────────────────────────────────────────
# Assets
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/assets")
async def listar_assets(
    _: Identidade = Depends(exigir_usuario),
    repo: Repositorio = Depends(obter_repo),
    assinador: Assinador = Depends(obter_assinador),
    busca: Optional[str] = None,
    kind: Optional[str] = None,
    estado: Optional[str] = None,
    destino: Optional[str] = None,
    brandPack: Optional[str] = None,
    desde: Optional[str] = None,
    ate: Optional[str] = None,
    limite: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    # ⚠️ `estado` e `destino` são DECLARADOS aqui, e isso é conserto de um
    # defeito crítico medido em 28/08/2026.
    #
    # O cliente já os enviava; o FastAPI descarta query param não declarado,
    # sem erro. O efeito na fila de aprovação era o pior possível: ela consulta
    # com `estado=aguardando`, recebia os ativos mais recentes da biblioteca
    # INTEIRA — aprovados e rejeitados inclusive —, cada um com botão "Decidir",
    # sob o título "Aguardando revisão" e a frase "N peças aguardam decisão".
    # A tela afirmava governança que ninguém havia consultado.
    if estado is not None and estado not in _ESTADOS_DE_REVISAO:
        raise _falha(
            "ESTUDIO.filtro_invalido",
            "Estado de revisão não reconhecido.",
            400,
        )
    linhas, total, universo = await _ou_503(
        repo.listar_masters(
            busca=busca, kind=kind, brand_pack_id=brandPack,
            desde=desde, ate=ate,
            # O filtro por estado é aplicado DEPOIS da leitura, porque a decisão
            # vive noutra tabela; por isso a página é lida com folga.
            limite=limite if estado is None else max(limite * 4, 120),
            offset=offset if estado is None else 0,
        )
    )
    vigentes = await _ou_503(
        repo.aprovacoes_vigentes_de([str(m["id"]) for m in linhas])
    )
    if estado is not None:
        def _estado_de(m: dict[str, Any]) -> str:
            decisao = vigentes.get(str(m["id"]))
            return decisao["decisao"] if decisao else "aguardando"

        linhas = [m for m in linhas if _estado_de(m) == estado]
        # `total` passa a descrever o RECORTE de fato, e não a biblioteca.
        total = len(linhas)
        linhas = linhas[offset : offset + limite]
    if destino is not None:
        # `destino` ainda não é filtrável: a compatibilidade de destino depende
        # de validação de formato e contrato, que é C2. Recusar é honesto;
        # aceitar e ignorar era o defeito.
        raise _falha(
            "ESTUDIO.filtro_indisponivel",
            "Ainda não é possível filtrar por destino. "
            "A compatibilidade de destino depende de uma validação que não existe nesta versão.",
            400,
        )
    procedencias = await _ou_503(
        repo.procedencia_dos_jobs([str(m["job_id"]) for m in linhas])
    )
    return {
        "assets": [
            apresentacao.master_dto(
                m,
                assinador,
                aprovacao=(
                    apresentacao.aprovacao_dto(vigentes[str(m["id"])])
                    if str(m["id"]) in vigentes
                    else None
                ),
                procedencia_execucao=procedencias.get(str(m["job_id"])),
            )
            for m in linhas
        ],
        "total": total,
        "universo": universo,
    }


@router.get("/assets/{asset_id}")
async def obter_asset(
    asset_id: str,
    _: Identidade = Depends(exigir_usuario),
    repo: Repositorio = Depends(obter_repo),
    assinador: Assinador = Depends(obter_assinador),
) -> dict[str, Any]:
    asset_id = _uuid_ou_404(asset_id, "asset")
    master = await _ou_503(repo.buscar_master(asset_id))
    if master is None:
        raise _falha("ESTUDIO.asset_inexistente", "Este ativo não existe.", 404)

    aprovacoes = await _ou_503(repo.aprovacoes_de("master", asset_id))
    vigente = next((a for a in aprovacoes if not a.get("revogada_em")), None)
    raiz = str(master.get("raiz_id") or master["id"])
    versoes = await _ou_503(repo.versoes_do_master(raiz))
    job = await _ou_503(repo.buscar_job(str(master["job_id"])))

    return {
        "asset": apresentacao.master_dto(
            master,
            assinador,
            aprovacao=apresentacao.aprovacao_dto(vigente) if vigente else None,
            # Sem `or "volc_os"`: coalesce sobre procedencia e como afirmar
            # autoria por falta de leitura. `None` viaja como `None`.
            procedencia_execucao=(job or {}).get("procedencia_execucao"),
        ),
        "versoes": [
            apresentacao.master_dto(
                v, assinador,
                procedencia_execucao=(job or {}).get("procedencia_execucao"),
            )
            for v in versoes
        ],
        "aprovacoes": [apresentacao.aprovacao_dto(a) for a in aprovacoes],
        "job": await _job_dto(repo, assinador, job) if job else None,
    }


@router.post("/assets/{asset_id}/aprovacoes")
async def aprovar(
    asset_id: str,
    pedido: PedidoDeAprovacao,
    # ⚠️ `exigir_admin`. Esta é a decisão humana da SPEC §5, e ela é gravada com
    # `ator_id = identidade.sub`. Uma sessão sem papel registrava a decisão como
    # ator desconhecido, e uma reprovação trancava o ativo (o índice de vigência
    # é único por versão e finalidade).
    identidade: Identidade = Depends(exigir_admin),
    repo: Repositorio = Depends(obter_repo),
) -> dict[str, Any]:
    if pedido.decisao not in ("aprovado", "ajuste_solicitado", "rejeitado"):
        raise _falha("ESTUDIO.decisao_invalida", "Decisão não reconhecida.", 400)
    if pedido.decisao != "aprovado" and not (pedido.motivo or "").strip():
        raise _falha(
            "ESTUDIO.motivo_obrigatorio",
            "Diga o motivo: reprovar sem motivo devolve o trabalho sem direção.",
            400,
        )

    asset_id = _uuid_ou_404(asset_id, "asset")
    master = await _ou_503(repo.buscar_master(asset_id))
    if master is None:
        raise _falha("ESTUDIO.asset_inexistente", "Este ativo não existe.", 404)

    try:
        linha = await repo.criar_aprovacao(
            {
                "subject_tipo": "master",
                "subject_id": asset_id,
                "versao": int(master.get("versao") or 1),
                "finalidade": pedido.finalidade or "interno",
                # ⚠️ Resolve, e NÃO valida. Uma finalidade que não existe no
                # registro grava `finalidade_id = NULL` e segue: a coluna texto
                # continua sendo a chave do índice de vigência, e recusar a
                # decisão humana porque o catálogo não tem a linha seria deixar
                # o operador refém de uma tabela de apoio. O nulo aqui é o sinal
                # de "esta finalidade ainda não está no registro", legível depois.
                "finalidade_id": await parque.Resolvedor(repo).finalidade(
                    pedido.finalidade or "interno"
                ),
                "decisao": pedido.decisao,
                "ator_id": identidade.sub,
                "motivo": pedido.motivo,
                "decidido_em": agora(),
            }
        )
    except ConflitoDeChave as e:
        # O índice parcial `criativo_aprovacao_vigente_ux` recusa uma segunda
        # decisão VIGENTE para o mesmo (ativo, versão, finalidade). Isso não é
        # defeito: é a regra funcionando. Sem este `except`, o conflito subia
        # como exceção não tratada e virava 500 — o backend acusando a si mesmo
        # de um erro que na verdade era uma regra de negócio sendo aplicada.
        raise _falha(
            "ESTUDIO.decisao_duplicada",
            "Já existe uma decisão vigente para esta versão e finalidade. "
            "Revogue a decisão atual antes de registrar outra.",
            409,
        ) from e
    except ErroDePersistencia as e:
        # O gatilho `criativo_aprovacao_peca_pronta_tg` recusa aprovar um ativo
        # de job falho ou sem peça pronta. A mensagem do banco cita tabela e
        # constraint, então ela NÃO sobe: vira uma frase de operador.
        texto = str(e)
        if "rendition pronta" in texto or "nao produz ativo aprovavel" in texto:
            raise _falha(
                "ESTUDIO.ativo_nao_aprovavel",
                "Este ativo não pode ser aprovado: a peça não ficou pronta.",
                409,
            ) from e
        if "23505" in texto or "duplicate" in texto.lower():
            raise _falha(
                "ESTUDIO.decisao_duplicada",
                "Já existe uma decisão vigente para esta versão e finalidade.",
                409,
            ) from e
        log.error("falha ao registrar aprovação: %s", e)
        raise _falha(
            "ESTUDIO.indisponivel", "Não foi possível registrar a decisão agora.", 503
        ) from e

    return apresentacao.aprovacao_dto(linha, nome=identidade.email or None)


@router.post("/assets/{asset_id}/aprovacoes/{aprovacao_id}/revogar")
async def revogar_aprovacao(
    asset_id: str,
    aprovacao_id: str,
    identidade: Identidade = Depends(exigir_admin),
    repo: Repositorio = Depends(obter_repo),
) -> dict[str, Any]:
    """Revoga a decisão vigente, liberando o lugar para outra.

    ⚠️ Esta rota é conserto de um beco sem saída medido em 28/08/2026. O 409 de
    decisão duplicada instruía "Revogue a decisão atual antes de registrar
    outra" — e **essa revogação não existia em lugar nenhum**. `revogada_em` só
    aparecia em leitura. Como `master.versao` é fixa em 1, a tupla do índice de
    vigência nunca mudava: uma reprovação trancava o ativo para sempre, e a
    única saída era SQL direto no banco de produção.

    Revogar NÃO apaga: a linha continua no histórico com `revogada_em` e
    `revogada_por`. O histórico de decisões é append-only por desenho.
    """
    asset_id = _uuid_ou_404(asset_id, "asset")
    aprovacao_id = _uuid_ou_404(aprovacao_id, "aprovacao")

    aprovacoes = await _ou_503(repo.aprovacoes_de("master", asset_id))
    alvo = next((a for a in aprovacoes if str(a["id"]) == aprovacao_id), None)
    if alvo is None:
        raise _falha(
            "ESTUDIO.aprovacao_inexistente",
            "Esta decisão não existe para este ativo.",
            404,
        )
    if alvo.get("revogada_em"):
        raise _falha(
            "ESTUDIO.aprovacao_ja_revogada", "Esta decisão já foi revogada.", 409
        )

    linha = await _ou_503(
        repo.revogar_aprovacao(aprovacao_id, identidade.sub)
    )
    return apresentacao.aprovacao_dto(linha or alvo, nome=identidade.email or None)


# ─────────────────────────────────────────────────────────────────────────────
# Vídeo observado
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/video/{slug}")
async def video(
    slug: str,
    _: Identidade = Depends(exigir_usuario),
    assinador: Assinador = Depends(obter_assinador),
) -> dict[str, Any]:
    if not video_observado.disponivel():
        raise _falha(
            "ESTUDIO.video_indisponivel",
            "Nenhum build de vídeo está acessível a partir deste servidor.",
            404,
        )
    try:
        build = video_observado.ler_build(slug)
    except video_observado.BuildNaoEncontrado as e:
        raise _falha("ESTUDIO.video_inexistente", "Este build não existe.", 404) from e

    # `FabricaIndisponivel` não é o mesmo que "build inexistente": um diz que a
    # fonte inteira sumiu, o outro que aquele item não está nela. A interface
    # precisa dizer coisas diferentes, então o backend não os colapsa.
    if isinstance(build, video_observado.FabricaIndisponivel):
        raise _falha(
            "ESTUDIO.video_indisponivel",
            "A fonte dos builds de vídeo não está acessível a partir deste servidor.",
            503,
        )
    return video_ponte.montar_resposta(build, assinador)


@router.get("/videos")
async def listar_videos(_: Identidade = Depends(exigir_usuario)) -> dict[str, Any]:
    if not video_observado.disponivel():
        return {"builds": [], "disponivel": False}
    return {"builds": video_observado.listar_builds(), "disponivel": True}


# ─────────────────────────────────────────────────────────────────────────────
# Arquivo assinado
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/arquivo/{token}")
async def arquivo(
    request: Request,
    chave: str = Depends(exigir_link_assinado),
) -> Response:
    """Serve os bytes de UMA chave, autorizado pelo portão de link assinado.

    O portão é uma DEPENDÊNCIA declarada, e não uma checagem no corpo da função.
    A diferença importa: `tests/test_seguranca_hub.py` inspeciona as dependências
    de cada rota para provar que nenhuma leitura fica sem guarda, e uma
    verificação escondida no corpo passaria nesse teste sem estar declarada em
    lugar nenhum, que é exatamente o tipo de proteção invisível que a auditoria
    de 24/08/2026 procurava.

    `exigir_usuario` não serve aqui: `<img src>` e `<video src>` não mandam
    header. Ver `app/seguranca/link_assinado.py` para por que isto é um portão
    de outra espécie e não uma exceção à regra.
    """
    if chave.startswith("fabrica/"):
        return _servir_da_fabrica(chave, request)

    loja = armazenamento_padrao()
    try:
        dados = loja.ler(chave)
    except ObjetoNaoEncontrado as e:
        raise _falha("ESTUDIO.arquivo_ausente", "O arquivo não está mais disponível.", 404) from e
    except ArquivoRecusado as e:
        raise _falha("ESTUDIO.link_invalido", "Este link não é válido.", 403) from e

    return Response(
        content=dados,
        media_type=_mime_por_extensao(chave),
        headers={
            "Cache-Control": "private, max-age=300",
            # O arquivo é servido de um domínio que também serve API: sem
            # `nosniff`, um navegador pode interpretar bytes como HTML e
            # executar script a partir de um ativo enviado por alguém.
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


def _servir_da_fabrica(chave: str, request: Request) -> Response:
    """Streaming de um artefato observado, com suporte a range.

    O MP4 do build tem ~39 MB. Carregá-lo inteiro por request custaria memória
    do servidor e impediria o navegador de buscar o meio do vídeo, que é o que
    todo player faz ao arrastar a barra.
    """
    caminho = video_ponte.caminho_da_chave(chave)
    if caminho is None or not caminho.is_file():
        raise _falha("ESTUDIO.arquivo_ausente", "O arquivo não está disponível.", 404)

    tamanho = caminho.stat().st_size
    mime = _mime_por_extensao(chave)
    faixa = request.headers.get("range")

    def ler(inicio: int, fim: int, bloco: int = 1024 * 512):
        with caminho.open("rb") as f:
            f.seek(inicio)
            restante = fim - inicio + 1
            while restante > 0:
                pedaco = f.read(min(bloco, restante))
                if not pedaco:
                    return
                restante -= len(pedaco)
                yield pedaco

    cabecalhos = {
        "Accept-Ranges": "bytes",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=300",
    }
    if faixa and faixa.startswith("bytes="):
        try:
            cru = faixa.split("=", 1)[1].split(",")[0]
            inicio_txt, _, fim_txt = cru.partition("-")
            if not inicio_txt:
                # `bytes=-500` é o SUFIXO: os últimos 500 bytes, não os
                # primeiros. Um player que lê o `moov` pelo fim do arquivo
                # recebia o cabeçalho e um 206 dizendo que estava tudo certo.
                sufixo = int(fim_txt or 0)
                inicio = max(0, tamanho - sufixo) if sufixo else 0
                fim = tamanho - 1
            else:
                inicio = int(inicio_txt)
                fim = int(fim_txt) if fim_txt else tamanho - 1
        except ValueError:
            inicio, fim = 0, tamanho - 1
        inicio = max(0, min(inicio, tamanho - 1))
        fim = max(inicio, min(fim, tamanho - 1))
        cabecalhos["Content-Range"] = f"bytes {inicio}-{fim}/{tamanho}"
        cabecalhos["Content-Length"] = str(fim - inicio + 1)
        return StreamingResponse(
            ler(inicio, fim), status_code=206, media_type=mime, headers=cabecalhos
        )

    cabecalhos["Content-Length"] = str(tamanho)
    return StreamingResponse(
        ler(0, tamanho - 1), media_type=mime, headers=cabecalhos
    )


_MIME_POR_EXT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "mp4": "video/mp4",
}


def _mime_por_extensao(chave: str) -> str:
    return _MIME_POR_EXT.get(chave.rsplit(".", 1)[-1].lower(), "application/octet-stream")


# ─────────────────────────────────────────────────────────────────────────────
# Auxiliares
# ─────────────────────────────────────────────────────────────────────────────


async def _ou_503(coro):
    try:
        return await coro
    except ErroDePersistencia as e:
        log.error("banco indisponível: %s", e)
        raise _falha(
            "ESTUDIO.indisponivel",
            "Não foi possível ler os dados do Estúdio agora.",
            503,
        ) from e


async def _job_dto(
    repo: Repositorio, assinador: Assinador, job: dict[str, Any], *, cursor: int | None = None
) -> dict[str, Any]:
    renditions = await _ou_503(repo.renditions_do_job(str(job["id"])))
    seq = cursor if cursor is not None else await _ou_503(repo.ultimo_seq(str(job["id"])))
    briefing = await _ou_503(repo.buscar_briefing(str(job["briefing_id"])))
    projeto_titulo = ""
    projeto_id = ""
    tipo, modo = "imagem", "full_llm"
    if briefing:
        projeto_id = str(briefing.get("projeto_id") or "")
        tipo = briefing.get("tipo") or tipo
        modo = briefing.get("modo") or modo
        if projeto_id:
            projeto = await _ou_503(repo.buscar_projeto(projeto_id))
            projeto_titulo = (projeto or {}).get("titulo") or ""
    dto = apresentacao.job_dto(
        {**job, "projeto_id": projeto_id},
        renditions,
        assinador,
        projeto_titulo=projeto_titulo,
        tipo=tipo,
        modo=modo,
        cursor=seq,
    )
    return dto
