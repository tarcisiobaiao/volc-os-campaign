"""HTTP da publicacao organica. Adaptacao de entrada e saida, e nada mais.

Regra em `dominio.py`, orquestracao em `aplicacao.py`, persistencia em
`infraestrutura.py`, mundo externo em `adaptadores/`. Este arquivo converte
request em chamada e resultado em resposta.

## Os codigos, e por que cada um

`200` leitura ou reenvio reconhecido · `201` operacao nova · `400` pedido
invalido · `401` sem sessao · `403` sem papel ou de outro dono · `404` nao
existe (ou nao e seu — de proposito, a mesma resposta) · `409` conflito de
estado, de chave ou de lease · `502` o control plane recusou · `503` publicacao
indisponivel.

O par 200/201 e o que torna a idempotencia VISIVEL: quem recebe 200 com
`X-Publicacao-Idempotente: replay` sabe que nada novo foi produzido.

## ⚠️ Por que o corpo e lido CRU e validado a mao

O mesmo defeito que o Cofre mediu em 01/09/2026: o handler padrao de
`RequestValidationError` serializa `exc.errors()`, e cada erro do Pydantic v2
carrega o campo `input` — o VALOR rejeitado. Um `POST` com um token no campo
errado voltaria com o token no corpo do 422. Handlers de excecao no FastAPI sao
de APP, entao consertar por router nao da: este modulo le o corpo cru e monta a
mensagem a partir de `loc` e `msg`, NUNCA de `input`.

## O dono nao e filtro opcional

Toda rota recebe `Identidade` como PARAMETRO (e nao so como `dependencies=[...]`)
e propaga `identidade.sub` ate a funcao governada. Uma rota que declarasse o
portao sem usar a identidade passaria no teste de "toda rota mutante tem
portao" e ainda assim publicaria a peca de outro dono.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings, get_settings
from app.publicacao_organica import dominio as dom
from app.publicacao_organica.aplicacao import (
    Autor,
    CasosDeUso,
    JobNaoEncontrado,
    OperacaoRecusada,
    PublicacaoIndisponivel,
)
from app.publicacao_organica.infraestrutura import RepositorioSupabase
from app.publicacao_organica.portas import PortaDePublicacao
from app.seguranca.identidade import Identidade, exigir_admin

log = logging.getLogger("volc.publicacao_organica.http")

router = APIRouter(
    prefix="/api/publicacao-organica",
    tags=["publicacao-organica"],
    dependencies=[Depends(exigir_admin)],
)


def _falha(codigo: str, mensagem: str, status: int) -> HTTPException:
    """Erro com forma estavel. O frontend le `detail.mensagem` e mostra."""
    return HTTPException(status_code=status, detail={"codigo": codigo, "mensagem": mensagem})


# ---------------------------------------------------------------------------
# Modelos de entrada — todos `extra="forbid"`
# ---------------------------------------------------------------------------
# ⚠️ `forbid` e nao `ignore` porque a alternativa e silencio. Alguem manda
# `{"texto":"...", "password":"..."}` e a API responde 201 sem gravar a senha —
# mas tambem sem dizer que a recusou. A pessoa acha que guardou.


class DestinoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ativo_id: str = Field(min_length=3, max_length=180)
    plataforma: Literal[dom.PLATAFORMAS]  # type: ignore[valid-type]
    identidade_logica: str = Field(min_length=1, max_length=120)
    provedor: Literal["postiz", "multipost"] = "postiz"
    referencia_externa: Optional[str] = Field(default=None, max_length=200)
    adapter_apto: bool = False
    motivo_inapto: Optional[str] = Field(default=None, max_length=400)
    timezone_padrao: str = "America/Sao_Paulo"


class JobEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    peca_id: str
    peca_versao: int = Field(ge=1)
    autorizacao_id: str
    destino_id: str
    modo: Literal["draft", "schedule", "now"]
    timezone: str = "America/Sao_Paulo"
    horario_local: Optional[str] = None
    texto: str = Field(default="", max_length=8000)
    imagens: list[str] = Field(default_factory=list, max_length=10)
    #: ⚠️ O SIM EXPLICITO. Ele nao tem default `True` em lugar nenhum, e o campo
    #: e nomeado para que ninguem o marque por engano ao copiar um exemplo.
    confirmo_publicacao_imediata: bool = False


class CancelamentoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    motivo: str = Field(min_length=3, max_length=400)


# ---------------------------------------------------------------------------
# Injecao
# ---------------------------------------------------------------------------


def _porta(settings: Settings) -> PortaDePublicacao | None:
    """Constroi o adaptador real, ou None quando o ambiente nao o configurou.

    ⚠️ None nao e um adaptador que nao faz nada: `CasosDeUso._exigir_porta`
    responde 503 e diz que nao ha control plane. Um adaptador silencioso faria a
    tela mostrar "despachado" sobre nada.
    """
    token = getattr(settings, "postiz_api_token", None)
    base = getattr(settings, "postiz_base_url", None)
    if not token or not base:
        return None
    from app.publicacao_organica.adaptadores.postiz import AdaptadorPostiz  # noqa: PLC0415

    try:
        return AdaptadorPostiz(
            base_url=base, token=token,
            permitir_rede_interna=bool(getattr(settings, "postiz_permitir_rede_interna", False)),
        )
    except Exception as exc:  # noqa: BLE001 — configuracao ruim nao derruba o app
        log.error("publicacao organica: adaptador nao pode ser construido: %s",
                  dom.sanitizar_erro(str(exc)))
        return None


async def _casos(settings: Settings = Depends(get_settings)) -> CasosDeUso:
    from app.services.supabase_service import SupabaseService  # noqa: PLC0415

    return CasosDeUso(RepositorioSupabase(SupabaseService(settings)), _porta(settings))


Casos = Annotated[CasosDeUso, Depends(_casos)]


def _autor(quem: Identidade) -> Autor:
    return Autor(sub=quem.sub, email=quem.email or quem.sub)


def _traduzir(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, dom.PedidoRecusado):
        return _falha(exc.codigo, str(exc), 400)
    if isinstance(exc, JobNaoEncontrado):
        return _falha("nao_encontrado", "Esse job de publicacao nao existe.", 404)
    if isinstance(exc, OperacaoRecusada):
        return _falha(exc.codigo, str(exc), exc.status)
    if isinstance(exc, PublicacaoIndisponivel):
        # 503 e nao 200 com lista vazia: a tela precisa distinguir "nao ha jobs"
        # de "nao sei se ha jobs".
        return _falha("publicacao_indisponivel", str(exc), 503)
    log.exception("publicacao organica: falha nao prevista")
    return _falha("falha_interna", "A publicacao nao conseguiu concluir esta operacao.", 500)


async def _validado(modelo: type[BaseModel], requisicao: Request) -> Any:
    """Le o corpo cru e valida a mao. Ver o docstring do modulo."""
    try:
        bruto = await requisicao.json()
    except Exception:  # noqa: BLE001
        raise _falha("corpo_invalido", "O corpo precisa ser um objeto JSON.", 400) from None
    if not isinstance(bruto, dict):
        raise _falha("corpo_invalido", "O corpo precisa ser um objeto JSON.", 400)
    try:
        return modelo.model_validate(bruto)
    except ValidationError as exc:
        # ⚠️ `loc` e `msg` apenas. `input` NUNCA — e ele que carrega o valor.
        problemas = "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg', '')}"
            for e in exc.errors()[:5]
        )
        raise _falha("pedido_invalido", f"O pedido nao respeita o contrato ({problemas}).", 400) from None


def _responder(recibo: dict[str, Any], resposta: Response) -> dict[str, Any]:
    """201 para operacao nova, 200 para replay — e o header que diz qual foi."""
    replay = bool(recibo.get("idempotente"))
    resposta.status_code = 200 if replay else 201
    resposta.headers["X-Publicacao-Idempotente"] = "replay" if replay else "novo"
    return recibo


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


@router.get("/destinos")
async def listar_destinos(casos: Casos,
                          quem: Identidade = Depends(exigir_admin)) -> dict[str, Any]:
    try:
        return await casos.destinos(_autor(quem))
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.get("/jobs")
async def listar_jobs(
    casos: Casos,
    quem: Identidade = Depends(exigir_admin),
    estado: Optional[str] = Query(default=None),
    limite: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    if estado is not None and estado not in dom.ESTADOS:
        raise _falha("estado_desconhecido",
                     f"'{estado}' nao e um estado desta versao do contrato.", 400)
    try:
        return await casos.jobs(_autor(quem), estado=estado, limite=limite)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.get("/jobs/{job_id}")
async def detalhar_job(job_id: str, casos: Casos,
                       quem: Identidade = Depends(exigir_admin)) -> dict[str, Any]:
    try:
        return await casos.job(job_id, _autor(quem))
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.get("/prontidao")
async def prontidao(casos: Casos) -> dict[str, Any]:
    """Sonda do control plane. Nunca levanta — indisponivel e uma RESPOSTA."""
    return await casos.prontidao()


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------


@router.post("/destinos")
async def registrar_destino(requisicao: Request, resposta: Response, casos: Casos,
                            quem: Identidade = Depends(exigir_admin)) -> dict[str, Any]:
    corpo: DestinoEntrada = await _validado(DestinoEntrada, requisicao)
    payload = corpo.model_dump(exclude_none=True)
    try:
        return _responder(await casos.registrar_destino(payload, _autor(quem)), resposta)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.post("/jobs")
async def criar_job(requisicao: Request, resposta: Response, casos: Casos,
                    quem: Identidade = Depends(exigir_admin)) -> dict[str, Any]:
    """Cria a INTENCAO. Nada sai daqui para o control plane.

    ⚠️ Criar nao despacha, e essa separacao e o contrato: `gerar != aprovar !=
    publicar`. Uma rota que criasse e despachasse na mesma requisicao tiraria o
    unico ponto de intervencao entre a peca ficar pronta e ela ir para o destino
    — que foi exatamente o defeito do Redator (`publicar=True` literal).
    """
    corpo: JobEntrada = await _validado(JobEntrada, requisicao)
    try:
        pedido = dom.montar_pedido(
            peca_id=corpo.peca_id,
            peca_versao=corpo.peca_versao,
            autorizacao_id=corpo.autorizacao_id,
            destino_id=corpo.destino_id,
            modo=corpo.modo,
            timezone=corpo.timezone,
            horario_local=corpo.horario_local,
            corpo={"texto": corpo.texto, "imagens": corpo.imagens},
            consentimento_agora=corpo.confirmo_publicacao_imediata,
        )
        return _responder(await casos.criar_job(pedido, _autor(quem)), resposta)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.post("/jobs/{job_id}/liberar")
async def liberar(job_id: str, casos: Casos,
                  quem: Identidade = Depends(exigir_admin)) -> dict[str, Any]:
    try:
        return await casos.liberar(job_id, _autor(quem))
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.post("/jobs/{job_id}/despachar")
async def despachar(job_id: str, casos: Casos,
                    quem: Identidade = Depends(exigir_admin)) -> dict[str, Any]:
    """O unico passo que fala com o control plane."""
    try:
        return await casos.despachar(job_id, _autor(quem))
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.post("/jobs/{job_id}/reconciliar")
async def reconciliar(job_id: str, casos: Casos,
                      quem: Identidade = Depends(exigir_admin)) -> dict[str, Any]:
    try:
        return await casos.reconciliar(job_id, _autor(quem))
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.post("/jobs/{job_id}/cancelar")
async def cancelar(job_id: str, requisicao: Request, casos: Casos,
                   quem: Identidade = Depends(exigir_admin)) -> dict[str, Any]:
    corpo: CancelamentoEntrada = await _validado(CancelamentoEntrada, requisicao)
    try:
        return await casos.cancelar(job_id, corpo.motivo, _autor(quem))
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc
