"""HTTP `/api/agent/*` da Bia. Adaptação de entrada e saída, e nada mais.

## Ordem dos portões (a mesma em toda rota)

1. flag `BIA_ENABLED=1` — sem ela, 404 antes de tocar no auth ou no Hermes;
2. `exigir_admin` — 401 sem/invalid token, 503 auth fora do ar, 403 sem papel.
   Na V1 a Bia é só ADMIN; o dono é o `sub` do token, nunca o corpo;
3. corpo lido CRU, limitado em bytes e validado com `extra="forbid"`; o 422
   devolve campo e motivo, nunca o valor recusado (mesmo defeito medido no
   Cofre em 01/09/2026: o handler padrão ecoa o `input`).

## Os códigos

`200` leitura ou repetição idempotente · `201` conversa nova · `202` envio
aceito (a execução segue em fundo) · `401`/`403`/`503` portão · `404` não
existe OU não é seu (mesma resposta, de propósito) · `409` conflito de
request_id, execução em andamento ou conversa com execução incerta · `413`
corpo grande · `422` corpo inválido · `429` limite por minuto · `503` ledger
ou Hermes indisponível.

## O que o corpo NÃO aceita

model, provider, profile, instructions/system prompt, session_id do Hermes,
tools, URL, SQL, tabela, tenant, user/dono. Não há campo para nenhum deles:
`extra="forbid"` transforma cada um em 422.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Literal, Optional, Type, TypeVar

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agente_bia import configuracao, dominio as dom
from app.agente_bia.aplicacao import (
    CasosDeUso,
    ContextoLido,
    ConversaNaoEncontrada,
    EnvioRecusado,
)
from app.agente_bia.gateway import contexto_campanha as ctxc
from app.agente_bia.gateway.catalogo import (
    Catalogo,
    CapacidadeDesconhecida,
    EntradaRecusada,
    PapelInsuficiente,
    erros_sem_valor,
)
from app.agente_bia.infra_hermes import HermesHttp
from app.agente_bia.infra_ledger import LedgerIndisponivel, LedgerSupabase
from app.agente_bia.portas import RESERVA_REPETIDA, Execucao
from app.config import Settings, get_settings
from app.seguranca.identidade import Identidade, exigir_admin

log = logging.getLogger("volc.agente_bia.http")

MAX_CORPO_BYTES = 32 * 1024


# ── portões e fábricas ──────────────────────────────────────────────────────

def configuracao_da_bia(settings: Settings = Depends(get_settings)) -> configuracao.ConfiguracaoDaBia:
    try:
        return configuracao.ler(settings)
    except configuracao.ConfiguracaoInvalida as exc:
        log.error("configuração da Bia inválida: %s", exc)
        raise HTTPException(status_code=503, detail={
            "codigo": "configuracao_invalida", "mensagem": "Bia mal configurada no servidor."})


def exigir_bia_ligada(cfg: configuracao.ConfiguracaoDaBia = Depends(configuracao_da_bia)) -> None:
    if not cfg.ligada:
        raise HTTPException(status_code=404, detail="Not Found")


def casos_de_uso(cfg: configuracao.ConfiguracaoDaBia = Depends(configuracao_da_bia),
                 settings: Settings = Depends(get_settings)) -> CasosDeUso:
    if not (settings.supabase_url and settings.supabase_service_role_key):
        raise HTTPException(status_code=503, detail={
            "codigo": "ledger_indisponivel", "mensagem": "Ledger da Bia sem configuração."})
    motor = (HermesHttp(cfg.hermes_base_url, cfg.hermes_chave, timeout_s=cfg.timeout_s)
             if cfg.motor_configurado else None)
    return CasosDeUso(LedgerSupabase(settings.supabase_url, settings.supabase_service_role_key),
                      motor, limite_por_minuto=cfg.limite_por_minuto,
                      max_caracteres=cfg.max_caracteres, timeout_motor_s=cfg.timeout_s)


def _fonte_real():
    from app.agente_bia.gateway.infra_contexto import FonteDoContextoSupabase
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_role_key):
        raise LedgerIndisponivel("supabase sem configuração")
    return FonteDoContextoSupabase(s.supabase_url, s.supabase_service_role_key)


_CATALOGO: Optional[Catalogo] = None


def catalogo() -> Catalogo:
    global _CATALOGO
    if _CATALOGO is None:
        c = Catalogo()
        c.registrar(ctxc.capacidade(_fonte_real))
        _CATALOGO = c
    return _CATALOGO


router = APIRouter(
    prefix="/api/agent",
    tags=["agente-bia"],
    # A flag vem ANTES do admin: desligada, a superfície não existe e nada é
    # perguntado ao Supabase.
    dependencies=[Depends(exigir_bia_ligada), Depends(exigir_admin)],
)


# ── contratos de entrada ────────────────────────────────────────────────────

class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CorpoNovaConversa(_Estrito):
    pass


class ContextoPedido(_Estrito):
    campaign_ref: str = Field(pattern=ctxc.PADRAO_REF)
    janela: Literal["ultimos_7_dias", "ultimos_14_dias", "ultimos_30_dias"] = "ultimos_7_dias"


class CorpoMensagem(_Estrito):
    request_id: uuid.UUID
    texto: str = Field(min_length=1, max_length=dom.MAX_ENTRADA_ABSOLUTO)
    contexto: Optional[ContextoPedido] = None


M = TypeVar("M", bound=BaseModel)


async def _corpo(request: Request, modelo: Type[M], *, vazio_permitido: bool = False) -> M:
    tamanho = request.headers.get("content-length")
    if tamanho and tamanho.isdigit() and int(tamanho) > MAX_CORPO_BYTES:
        raise HTTPException(status_code=413, detail={"codigo": "corpo_grande",
                                                     "mensagem": "Corpo acima do limite."})
    bruto = await request.body()
    if len(bruto) > MAX_CORPO_BYTES:
        raise HTTPException(status_code=413, detail={"codigo": "corpo_grande",
                                                     "mensagem": "Corpo acima do limite."})
    if not bruto.strip():
        if vazio_permitido:
            return modelo.model_validate({})
        raise HTTPException(status_code=422, detail={"codigo": "corpo_invalido",
                                                     "mensagem": "Corpo ausente.", "erros": []})
    try:
        dados = json.loads(bruto)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail={"codigo": "corpo_invalido",
                                                     "mensagem": "JSON inválido.", "erros": []})
    if not isinstance(dados, dict):
        raise HTTPException(status_code=422, detail={"codigo": "corpo_invalido",
                                                     "mensagem": "Corpo precisa ser objeto.",
                                                     "erros": []})
    try:
        return modelo.model_validate(dados)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail={"codigo": "corpo_invalido",
                                                     "mensagem": "Corpo recusado.",
                                                     "erros": erros_sem_valor(exc)})


def _uuid_ou_404(valor: str) -> str:
    try:
        return str(uuid.UUID(valor))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Não encontrado."})


def _indisponivel(exc: Exception) -> HTTPException:
    log.warning("ledger da Bia indisponível: %s", type(exc).__name__)
    return HTTPException(status_code=503, detail={"codigo": "ledger_indisponivel",
                                                  "mensagem": "Histórico da Bia indisponível."})


# ── projeções de saída ──────────────────────────────────────────────────────

def _recibo(e: Execucao) -> Dict[str, Any]:
    return {
        "id": e.id,
        "conversa_id": e.conversa_id,
        "request_id": e.request_id,
        "estado": e.estado,
        "entrada": e.entrada,
        "resposta": e.resposta,
        "erro": ({"codigo": e.erro_codigo, "mensagem": dom.mensagem_de_erro(e.erro_codigo)}
                 if e.erro_codigo else None),
        "contexto": e.contexto,
        "criada_em": e.criada_em,
        "terminada_em": e.terminada_em,
    }


def _conversa(c) -> Dict[str, Any]:
    return {"id": c.id, "titulo": c.titulo, "criada_em": c.criada_em,
            "atualizada_em": c.atualizada_em}


# ── rotas ───────────────────────────────────────────────────────────────────

@router.get("/estado")
async def estado(cfg: configuracao.ConfiguracaoDaBia = Depends(configuracao_da_bia),
                 cat: Catalogo = Depends(catalogo)) -> Dict[str, Any]:
    return {
        "modo": "consulta",
        "aviso": dom.AVISO_MODO_CONSULTA,
        "motor_configurado": cfg.motor_configurado,
        "limites": {"max_caracteres": cfg.max_caracteres,
                    "envios_por_minuto": cfg.limite_por_minuto},
        "capacidades": cat.nomes(),
    }


@router.post("/conversations", status_code=201)
async def nova_conversa(request: Request, identidade: Identidade = Depends(exigir_admin),
                        casos: CasosDeUso = Depends(casos_de_uso)) -> Dict[str, Any]:
    await _corpo(request, CorpoNovaConversa, vazio_permitido=True)
    try:
        c = await casos.criar_conversa(identidade.sub)
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    return {"conversa": _conversa(c)}


@router.get("/conversations")
async def conversas(identidade: Identidade = Depends(exigir_admin),
                    casos: CasosDeUso = Depends(casos_de_uso)) -> Dict[str, Any]:
    try:
        lista = await casos.listar_conversas(identidade.sub)
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    return {"conversas": [_conversa(c) for c in lista]}


@router.get("/conversations/{conversa_id}/messages")
async def historico(conversa_id: str, identidade: Identidade = Depends(exigir_admin),
                    casos: CasosDeUso = Depends(casos_de_uso)) -> Dict[str, Any]:
    cid = _uuid_ou_404(conversa_id)
    try:
        h = await casos.historico(identidade.sub, cid)
    except ConversaNaoEncontrada:
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Conversa não encontrada."})
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    return {"conversa": _conversa(h.conversa), "execucoes": [_recibo(e) for e in h.execucoes],
            "aviso": dom.AVISO_MODO_CONSULTA}


_RECUSAS = {
    "conflito": (409, "request_id_conflito", "Este request_id já foi usado com outro conteúdo."),
    "ocupado": (409, "execucao_em_andamento", "Há um envio seu em andamento. Aguarde a resposta."),
    "bloqueada_incerta": (409, "conversa_incerta",
                          "Esta conversa tem um envio de resultado incerto. Reconcilie ou abra "
                          "uma nova conversa; nada é reenviado automaticamente."),
    "limite": (429, "limite_por_minuto", "Limite de envios por minuto atingido."),
    "conversa_inexistente": (404, "nao_encontrado", "Conversa não encontrada."),
}


@router.post("/conversations/{conversa_id}/messages")
async def enviar(conversa_id: str, request: Request, response: Response,
                 tarefas: BackgroundTasks,
                 identidade: Identidade = Depends(exigir_admin),
                 cfg: configuracao.ConfiguracaoDaBia = Depends(configuracao_da_bia),
                 casos: CasosDeUso = Depends(casos_de_uso),
                 cat: Catalogo = Depends(catalogo)) -> Dict[str, Any]:
    cid = _uuid_ou_404(conversa_id)
    corpo = await _corpo(request, CorpoMensagem)
    if not cfg.motor_configurado:
        # Antes de reservar: sem motor, nada entra no ledger como se fosse sair.
        raise HTTPException(status_code=503, detail={"codigo": "hermes_indisponivel",
                                                     "mensagem": dom.mensagem_de_erro("hermes_indisponivel")})
    contexto = None
    if corpo.contexto is not None:
        try:
            contexto = cat.validar_entrada(ctxc.NOME, corpo.contexto.model_dump()).model_dump()
        except EntradaRecusada as exc:
            raise HTTPException(status_code=422, detail={"codigo": "contexto_invalido",
                                                         "mensagem": "Contexto recusado.",
                                                         "erros": exc.erros})
    try:
        reserva = await casos.reservar_envio(identidade.sub, cid, str(corpo.request_id),
                                             corpo.texto, contexto)
    except dom.EntradaInvalida as exc:
        raise HTTPException(status_code=422, detail={"codigo": "mensagem_invalida",
                                                     "mensagem": str(exc), "erros": []})
    except EnvioRecusado as exc:
        status, codigo, msg = _RECUSAS.get(exc.motivo, (409, exc.motivo, "Envio recusado."))
        raise HTTPException(status_code=status, detail={"codigo": codigo, "mensagem": msg})
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)

    assert reserva.execucao is not None
    if reserva.resultado == RESERVA_REPETIDA:
        # Mesmo request_id, mesmo conteúdo: o recibo existente, e NADA novo sai.
        response.status_code = 200
        response.headers["X-Bia-Idempotente"] = "replay"
        return {"execucao": _recibo(reserva.execucao), "aviso": dom.AVISO_MODO_CONSULTA}

    async def ler_contexto(ref: Dict[str, Any]) -> ContextoLido:
        dados = await cat.invocar(identidade, ctxc.NOME, ref)
        return ContextoLido(ferramenta=ctxc.NOME, dados=dados, resumo=ctxc.resumo_para_recibo(dados))

    tarefas.add_task(_executar_em_fundo, casos, identidade.sub, reserva.execucao.id, ler_contexto)
    response.status_code = 202
    return {"execucao": _recibo(reserva.execucao), "aviso": dom.AVISO_MODO_CONSULTA}


async def _executar_em_fundo(casos: CasosDeUso, dono: str, execucao_id: str, leitor) -> None:
    try:
        await casos.executar(dono, execucao_id, leitor)
    except Exception as exc:  # noqa: BLE001
        # O ledger caiu no meio. A execução fica onde estava (queued/running) e
        # `expirar` a rebaixa depois — para cancelled ou uncertain, nunca replay.
        log.error("execução %s interrompida no backend: %s", execucao_id, type(exc).__name__)


@router.get("/runs/{execucao_id}")
async def uma_execucao(execucao_id: str, identidade: Identidade = Depends(exigir_admin),
                       casos: CasosDeUso = Depends(casos_de_uso)) -> Dict[str, Any]:
    eid = _uuid_ou_404(execucao_id)
    try:
        e = await casos.execucao(identidade.sub, eid)
    except ConversaNaoEncontrada:
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Execução não encontrada."})
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    return {"execucao": _recibo(e)}


@router.post("/runs/{execucao_id}/reconcile")
async def reconciliar(execucao_id: str, request: Request,
                      identidade: Identidade = Depends(exigir_admin),
                      casos: CasosDeUso = Depends(casos_de_uso)) -> Dict[str, Any]:
    eid = _uuid_ou_404(execucao_id)
    await _corpo(request, CorpoNovaConversa, vazio_permitido=True)
    try:
        e = await casos.reconciliar(identidade.sub, eid)
    except ConversaNaoEncontrada:
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Execução incerta não encontrada."})
    except EnvioRecusado as exc:
        raise HTTPException(status_code=503, detail={"codigo": exc.motivo,
                                                     "mensagem": dom.mensagem_de_erro(exc.motivo)})
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    return {"execucao": _recibo(e)}


@router.get("/tools")
async def ferramentas(cat: Catalogo = Depends(catalogo)) -> Dict[str, Any]:
    return {"capacidades": cat.descrever(), "mutacoes": []}


@router.post("/tools/{nome}")
async def invocar_ferramenta(nome: str, request: Request,
                             identidade: Identidade = Depends(exigir_admin),
                             cat: Catalogo = Depends(catalogo)) -> Dict[str, Any]:
    if nome not in cat.nomes():
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Capacidade desconhecida."})
    bruto = await request.body()
    if len(bruto) > MAX_CORPO_BYTES:
        raise HTTPException(status_code=413, detail={"codigo": "corpo_grande",
                                                     "mensagem": "Corpo acima do limite."})
    try:
        args = json.loads(bruto or b"{}")
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail={"codigo": "corpo_invalido",
                                                     "mensagem": "JSON inválido.", "erros": []})
    if not isinstance(args, dict):
        raise HTTPException(status_code=422, detail={"codigo": "corpo_invalido",
                                                     "mensagem": "Corpo precisa ser objeto.",
                                                     "erros": []})
    try:
        return {"resultado": await cat.invocar(identidade, nome, args)}
    except EntradaRecusada as exc:
        raise HTTPException(status_code=422, detail={"codigo": "entrada_invalida",
                                                     "mensagem": "Entrada recusada.",
                                                     "erros": exc.erros})
    except PapelInsuficiente:
        raise HTTPException(status_code=403, detail="Esta operação exige papel administrativo.")
    except (CapacidadeDesconhecida, ctxc.CampanhaNaoEncontrada):
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Não encontrado."})
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    except Exception as exc:  # noqa: BLE001 — fonte canônica fora do ar não vira 500 com rastro
        log.warning("capacidade %s indisponível: %s", nome, type(exc).__name__)
        raise HTTPException(status_code=503, detail={"codigo": "contexto_indisponivel",
                                                     "mensagem": dom.mensagem_de_erro("contexto_indisponivel")})
