"""Configuracao provisoria e leitura minima da Meta, somente em localhost.

Estas rotas nao substituem o Cofre oficial. Elas existem para destravar a
integracao no Mac do operador, exigem papel ADMIN e nunca oferecem mutate.
"""
from __future__ import annotations

import sys
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr

from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta import dominio as dom
from app.trafego.meta.adaptador import AdaptadorMetaSomenteLeitura, ErroDeLeituraMeta
from app.trafego.meta.configuracao_local import (
    ChaveiroMacOS,
    ConfiguracaoLocalIndisponivel,
    CredencialLocal,
    SegredoLocalNaoEncontrado,
    nome_da_conta_local,
)
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta.persistencia import RepositorioMetaEmMemoria


router = APIRouter(prefix="/api/trafego/meta/local", tags=["meta-local"])
GRAPH_BASE = "https://graph.facebook.com/v26.0"
TIMEOUT_META = 15.0
HOSTS_LOCAIS = {"127.0.0.1", "::1", "localhost", "testclient"}
_REPOSITORIO_PREVIEW = RepositorioMetaEmMemoria()


class PedidoDeToken(BaseModel):
    token: SecretStr = Field(min_length=20, max_length=4096)


class PedidoPorReferencia(BaseModel):
    referencia_opaca: str = Field(min_length=12, max_length=80)


def _exigir_host_local(request: Request) -> None:
    cliente = request.client.host if request.client else ""
    host_bruto = (request.headers.get("host") or "").strip().lower()
    if host_bruto.startswith("["):
        host = host_bruto[1:].split("]", 1)[0]
    else:
        host = host_bruto.rsplit(":", 1)[0] if ":" in host_bruto else host_bruto
    if sys.platform != "darwin" or cliente not in HOSTS_LOCAIS or host not in HOSTS_LOCAIS:
        raise HTTPException(
            status_code=404,
            detail="Configuracao provisoria Meta existe somente no backend local do macOS.",
        )


def _chaveiro() -> ChaveiroMacOS:
    try:
        return ChaveiroMacOS()
    except ConfiguracaoLocalIndisponivel as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


def _mascarar_id(valor: Any) -> str | None:
    return dom.mascarar_id(valor)


def _erro_meta(corpo: Any, status: int) -> HTTPException:
    codigo = None
    if isinstance(corpo, dict) and isinstance(corpo.get("error"), dict):
        codigo = corpo["error"].get("code")
    if status in {400, 401} or codigo == 190:
        mensagem = "A Meta recusou o token. Gere um token de usuário de sistema válido."
    elif status == 403:
        mensagem = "O token é válido, mas não possui as permissões de leitura necessárias."
    elif status == 429:
        mensagem = "A Meta limitou temporariamente a consulta. Tente novamente em alguns minutos."
    else:
        mensagem = "Não foi possível validar a integração Meta agora."
    return HTTPException(status_code=422 if status < 500 else 502, detail=mensagem)


async def _descobrir_contas_com_token(token: str) -> list[dom.ContaMetaDescoberta]:
    async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
        adaptador = AdaptadorMetaSomenteLeitura(cliente, limite_por_pagina=100, max_paginas_por_edge=20)
        return list(await adaptador.descobrir_contas(SegredoEfemero(token)))


async def _preflight_com_token(token: str, referencia_opaca: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
        adaptador = AdaptadorMetaSomenteLeitura(cliente, limite_por_pagina=100, max_paginas_por_edge=20)
        try:
            return dict(await adaptador.preflight_conta(referencia_opaca, SegredoEfemero(token)))
        except dom.ContratoMetaInvalido as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except ErroDeLeituraMeta as exc:
            raise HTTPException(status_code=502, detail=exc.mensagem_segura) from None


async def _testar_token(token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
            identidade = await cliente.get(
                f"{GRAPH_BASE}/me", params={"fields": "id,name"}, headers=headers)
            if identidade.status_code >= 400:
                try:
                    corpo = identidade.json()
                except ValueError:
                    corpo = None
                raise _erro_meta(corpo, identidade.status_code)
    except HTTPException:
        raise
    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail="Não foi possível alcançar a Meta para validar o token.",
        ) from None

    try:
        ator = identidade.json()
        contas = await _descobrir_contas_com_token(token)
    except (AttributeError, ValueError):
        raise HTTPException(status_code=502, detail="A Meta devolveu uma resposta inesperada.") from None
    except ErroDeLeituraMeta as exc:
        raise HTTPException(status_code=502, detail=exc.mensagem_segura) from None
    return {
        "ok": True,
        "api_version": "v26.0",
        "ator": {
            "nome": str(ator.get("name") or "Usuário de sistema"),
            "id_mascarado": _mascarar_id(ator.get("id")),
        },
        "contas": [dict(conta.publico()) for conta in contas],
        "contas_acessiveis": len(contas),
    }


def _credencial_salva(quem: Identidade) -> CredencialLocal:
    try:
        return CredencialLocal.de(_chaveiro().ler(nome_da_conta_local(quem.sub)))
    except SegredoLocalNaoEncontrado:
        raise HTTPException(status_code=409, detail="Nenhum token Meta está salvo neste Mac.") from None


@router.get("/configuracao")
async def estado_da_configuracao(
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    try:
        credencial = CredencialLocal.de(_chaveiro().ler(nome_da_conta_local(quem.sub)))
    except SegredoLocalNaoEncontrado:
        return {"configurado": False, "armazenamento": "macOS Keychain", "api_version": "v26.0"}
    return {
        "configurado": True,
        "armazenamento": "macOS Keychain",
        "api_version": "v26.0",
        "salvo_em": credencial.salvo_em,
    }


@router.post("/configuracao")
async def salvar_e_testar(
    payload: PedidoDeToken,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    token = payload.token.get_secret_value().strip()
    if not token or any(char.isspace() for char in token):
        raise HTTPException(status_code=422, detail="Token Meta malformado.")
    # Primeiro valida. Token recusado nunca ganha persistencia local.
    resultado = await _testar_token(token)
    credencial = CredencialLocal.agora(token)
    try:
        _chaveiro().salvar(nome_da_conta_local(quem.sub), credencial.serializar())
    except ConfiguracaoLocalIndisponivel as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {**resultado, "configurado": True, "salvo_em": credencial.salvo_em}


@router.post("/testar")
async def testar_salvo(
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    credencial = _credencial_salva(quem)
    return await _testar_token(credencial.token)


@router.get("/contas")
async def descobrir_contas(
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    credencial = _credencial_salva(quem)
    try:
        contas = await _descobrir_contas_com_token(credencial.token)
    except ErroDeLeituraMeta as exc:
        raise HTTPException(status_code=502, detail=exc.mensagem_segura) from None
    return {
        "ok": True,
        "api_version": "v26.0",
        "armazenamento": "macOS Keychain",
        "contas": [dict(conta.publico()) for conta in contas],
        "contas_acessiveis": len(contas),
        "proxima_acao": "preflight_somente_leitura",
    }


@router.post("/preflight")
async def preflight_somente_leitura(
    payload: PedidoPorReferencia,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    credencial = _credencial_salva(quem)
    return await _preflight_com_token(credencial.token, payload.referencia_opaca)


@router.post("/sincronizacao/preparar")
async def preparar_sincronizacao(
    payload: PedidoPorReferencia,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    credencial = _credencial_salva(quem)
    contas = await _descobrir_contas_com_token(credencial.token)
    try:
        conta = AdaptadorMetaSomenteLeitura.resolver_referencia_opaca(tuple(contas), payload.referencia_opaca)
    except dom.ContratoMetaInvalido as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {
        "ok": True,
        "modo": "PREVIEW_ONLY_NO_PERSISTENCE",
        "persistencia": "BLOQUEADA_ATE_AUTORIZACAO_DE_MIGRATION_E_SUPABASE_WRITE",
        "referencia_opaca": conta.referencia_opaca,
        "conta": conta.publico(),
        "capacidades_disponiveis": ["META_REAL_READ_PREVIEW"],
        "capacidades_bloqueadas": ["META_PERSIST_SYNC", "META_CREATE_PAUSED", "META_ENABLE"],
        "proxima_acao": "autorizar_migration_e_supabase_write_em_missao_separada",
    }


@router.get("/recibo/ultimo")
async def ultimo_recibo(
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    del quem
    _exigir_host_local(request)
    recibo = await _REPOSITORIO_PREVIEW.ultimo_recibo()
    if recibo is None:
        return {"ok": True, "recibo": None, "persistencia": "NAO_EXECUTADA"}
    return {
        "ok": True,
        "recibo": {
            "run_id": recibo.run_id,
            "resultado": recibo.resultado,
            "conta_mascarada": _mascarar_id(recibo.conta_externa),
            "contagens": dict(recibo.contagens),
            "paginas_lidas": recibo.paginas_lidas,
            "erro_codigo": recibo.erro_codigo,
            "erro_mensagem": recibo.erro_mensagem,
        },
    }


@router.delete("/configuracao")
async def remover_configuracao(
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, bool]:
    _exigir_host_local(request)
    try:
        removido = _chaveiro().remover(nome_da_conta_local(quem.sub))
    except ConfiguracaoLocalIndisponivel as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"removido": removido}
