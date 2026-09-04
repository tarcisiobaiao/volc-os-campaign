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
from app.trafego.meta.configuracao_local import (
    ChaveiroMacOS,
    ConfiguracaoLocalIndisponivel,
    CredencialLocal,
    SegredoLocalNaoEncontrado,
    nome_da_conta_local,
)


router = APIRouter(prefix="/api/trafego/meta/local", tags=["meta-local"])
GRAPH_BASE = "https://graph.facebook.com/v26.0"
TIMEOUT_META = 15.0
HOSTS_LOCAIS = {"127.0.0.1", "::1", "localhost", "testclient"}


class PedidoDeToken(BaseModel):
    token: SecretStr = Field(min_length=20, max_length=4096)


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
    texto = str(valor or "").removeprefix("act_")
    if not texto:
        return None
    return f"••••{texto[-4:]}"


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
            contas = await cliente.get(
                f"{GRAPH_BASE}/me/adaccounts",
                params={
                    "fields": "id,name,account_status,currency,timezone_name,business{id,name}",
                    "limit": 100,
                },
                headers=headers,
            )
            if contas.status_code >= 400:
                try:
                    corpo = contas.json()
                except ValueError:
                    corpo = None
                raise _erro_meta(corpo, contas.status_code)
    except HTTPException:
        raise
    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail="Não foi possível alcançar a Meta para validar o token.",
        ) from None

    try:
        ator = identidade.json()
        linhas = contas.json().get("data", [])
    except (AttributeError, ValueError):
        raise HTTPException(status_code=502, detail="A Meta devolveu uma resposta inesperada.") from None
    if not isinstance(linhas, list):
        raise HTTPException(status_code=502, detail="A Meta devolveu uma resposta inesperada.")
    return {
        "ok": True,
        "api_version": "v26.0",
        "ator": {
            "nome": str(ator.get("name") or "Usuário de sistema"),
            "id_mascarado": _mascarar_id(ator.get("id")),
        },
        "contas": [
            {
                "nome": str(linha.get("name") or "Conta sem nome"),
                "id_mascarado": _mascarar_id(linha.get("id")),
                "status": linha.get("account_status"),
                "moeda": linha.get("currency"),
                "fuso": linha.get("timezone_name"),
            }
            for linha in linhas
            if isinstance(linha, dict)
        ],
        "contas_acessiveis": len(linhas),
    }


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
    try:
        credencial = CredencialLocal.de(_chaveiro().ler(nome_da_conta_local(quem.sub)))
    except SegredoLocalNaoEncontrado:
        raise HTTPException(status_code=409, detail="Nenhum token Meta está salvo neste Mac.") from None
    return await _testar_token(credencial.token)


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
