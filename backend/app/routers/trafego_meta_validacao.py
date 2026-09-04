"""Safe control plane for compiling and remotely validating the Meta P0 plan.

This router has no create, approval or persistence endpoint. It can only read
account-scoped assets, compile a deterministic plan and, behind an independent
flag plus an explicit click, call Meta with ``execution_options=validate_only``.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.routers.meta_local import _credencial_salva, _exigir_host_local
from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao.ativos import ResolvedorAtivosMeta
from app.trafego.meta_execucao.compilador import PlanoCompiladoMeta, compilar_plano_pausado
from app.trafego.meta_execucao.contrato import (
    AutorizacaoMeta,
    ErroDeNascimentoMeta,
    PlanoMetaPausado,
)
from app.trafego.meta_execucao.executor import ErroRemotoMeta, ExecutorMetaPausado


router = APIRouter(prefix="/api/trafego/meta/local/criacao", tags=["meta-validate-paused"])
TIMEOUT_META = 20.0


class PedidoPlanoMetaPausado(BaseModel):
    account_ref: str = Field(min_length=8, max_length=180)
    page_ref: str = Field(min_length=8, max_length=180)
    asset_ref: str = Field(min_length=8, max_length=180)
    campaign_name: str = Field(min_length=1, max_length=400)
    adset_name: str = Field(min_length=1, max_length=400)
    creative_name: str = Field(min_length=1, max_length=400)
    ad_name: str = Field(min_length=1, max_length=400)
    destination_url: str = Field(min_length=10, max_length=2000)
    message: str = Field(min_length=1, max_length=2200)
    headline: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=255)
    daily_budget_minor: int = Field(gt=0, le=10_000_000)
    start_time: datetime
    special_ad_categories: list[str] = Field(default_factory=list, max_length=6)
    special_categories_confirmed: bool
    call_to_action_type: str = Field(default="LEARN_MORE", min_length=3, max_length=40)


class PedidoValidarMeta(BaseModel):
    plano: PedidoPlanoMetaPausado
    confirmar_validate_only: bool


def _erro(exc: Exception) -> HTTPException:
    if isinstance(exc, ErroDeNascimentoMeta):
        return HTTPException(status_code=409, detail={"codigo": exc.codigo, "mensagem": str(exc)})
    if isinstance(exc, ErroRemotoMeta):
        return HTTPException(status_code=422, detail={
            "codigo": exc.codigo,
            "mensagem": str(exc),
            "retry_permitido": exc.retryable,
        })
    return HTTPException(status_code=500, detail="Falha interna no controle Meta.")


def _plano(payload: PedidoPlanoMetaPausado) -> PlanoMetaPausado:
    return PlanoMetaPausado(
        account_ref=payload.account_ref,
        campaign_name=payload.campaign_name,
        adset_name=payload.adset_name,
        creative_name=payload.creative_name,
        ad_name=payload.ad_name,
        destination_url=payload.destination_url,
        page_ref=payload.page_ref,
        asset_ref=payload.asset_ref,
        message=payload.message,
        headline=payload.headline,
        description=payload.description,
        daily_budget_minor=payload.daily_budget_minor,
        start_time=payload.start_time,
        special_ad_categories=tuple(payload.special_ad_categories),
        special_categories_confirmed=payload.special_categories_confirmed,
        call_to_action_type=payload.call_to_action_type,
    )


async def _compilar(
    payload: PedidoPlanoMetaPausado,
    segredo: SegredoEfemero,
) -> PlanoCompiladoMeta:
    async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
        referencias = await ResolvedorAtivosMeta(cliente).resolver(
            account_ref=payload.account_ref,
            page_ref=payload.page_ref,
            asset_ref=payload.asset_ref,
            segredo=segredo,
        )
    return compilar_plano_pausado(_plano(payload), referencias)


@router.get("/capacidades")
async def capacidades(
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    del quem
    return {
        "ok": True,
        "api_version": "v26.0",
        "receita": "OUTCOME_TRAFFIC_WEBSITE_LPV_STATIC_PAUSED",
        "read_assets": "AVAILABLE_WITH_LOCAL_KEYCHAIN",
        "validate_only": (
            "ENABLED" if os.environ.get("META_VALIDATE_ONLY_ENABLED") == "1"
            else "BLOCKED_BY_SERVER_FLAG"
        ),
        "create_paused": "NOT_MOUNTED",
        "activation": "NOT_IMPLEMENTED",
    }


@router.get("/ativos")
async def ativos(
    request: Request,
    account_ref: str = Query(min_length=8, max_length=180),
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    segredo = SegredoEfemero(_credencial_salva(quem).token)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
            return dict(await ResolvedorAtivosMeta(cliente).inventariar(account_ref, segredo))
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None


@router.post("/compilar")
async def compilar(
    payload: PedidoPlanoMetaPausado,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    try:
        compilado = await _compilar(payload, SegredoEfemero(_credencial_salva(quem).token))
        return {"ok": True, "plano": compilado.publico(), "efeito_externo": "NENHUM"}
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None


@router.post("/validar")
async def validar(
    payload: PedidoValidarMeta,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    if not payload.confirmar_validate_only:
        raise HTTPException(status_code=409, detail={
            "codigo": "META_VALIDATE_ONLY_NOT_CONFIRMED",
            "mensagem": "confirme explicitamente a validacao remota",
        })
    if os.environ.get("META_VALIDATE_ONLY_ENABLED") != "1":
        raise HTTPException(status_code=409, detail={
            "codigo": "META_VALIDATE_ONLY_BLOCKED",
            "mensagem": "validate_only Meta permanece fechado neste servidor",
        })
    segredo = SegredoEfemero(_credencial_salva(quem).token)
    try:
        plano = await _compilar(payload.plano, segredo)
        autorizacao = AutorizacaoMeta(
            plano_sha256=plano.plano_sha256,
            ator=quem.sub,
            approval_id=f"validation_{uuid.uuid4()}",
            permitir_validate_only=True,
        )
        async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
            resultado = await ExecutorMetaPausado(cliente).validar_raizes(
                plano, segredo, autorizacao)
        return {
            "ok": resultado.aceito,
            "cobertura": resultado.cobertura,
            "operacoes_validadas": list(resultado.operacoes_validadas),
            "operacoes_dependentes_pendentes": list(resultado.operacoes_dependentes_pendentes),
            "plano_sha256": resultado.plano_sha256,
            "objetos_criados": 0,
        }
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None
