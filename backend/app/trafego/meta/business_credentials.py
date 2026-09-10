"""Durable Meta credentials: owner-bound ciphertext, explicit connection selection."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException
import httpx

from app.config import get_settings
from app.services.supabase_service import SupabaseService
from app.seguranca.segredo import cifrar, decifrar, CofreSemChave, SegredoCorrompido
from app.trafego.meta.configuracao_local import CredencialLocal

TABLE = "meta_business_credentials"
SELECTION = "meta_business_selection"
PUBLIC_COLUMNS = "id,business_id,name,enabled,verified_at,updated_at"


def repository():
    service = SupabaseService(get_settings())
    if service.base != "https://database.agenciavolc.com.br" or not service.enabled:
        raise HTTPException(503, "O cofre oficial não está disponível neste servidor.")
    return service


def seal(owner: str, business: str, token: str) -> str:
    return cifrar(json.dumps({"v": 1, "owner": owner, "business": business, "token": token}))


def unseal(row: dict, owner: str) -> str:
    try:
        body = json.loads(decifrar(row["ciphertext"]) or "null")
        if (row["owner_id"] != owner or body["v"] != 1 or body["owner"] != owner
                or body["business"] != row["business_id"] or not isinstance(body["token"], str)
                or not body["token"] or not row["enabled"]):
            raise ValueError()
        return body["token"]
    except (CofreSemChave, SegredoCorrompido, ValueError, KeyError, TypeError):
        raise HTTPException(409, "Esta conexão precisa ser recadastrada antes do uso.") from None


async def owned(repo, owner: str, connection: str):
    rows = await repo.select(TABLE, {"select": "*", "owner_id": f"eq.{owner}", "id": f"eq.{connection}", "limit": 1})
    if not rows:
        raise HTTPException(404, "Conexão não encontrada.")
    return rows[0]


async def upsert(repo, table: str, conflict: str, body: dict):
    return await repo._request("POST", table, params={"on_conflict": conflict},
        headers=repo._headers("resolution=merge-duplicates,return=minimal"), json=body)


async def credencial_operacional(quem, *, legado):
    # Rollout switch prevents legacy/test environments unexpectedly reaching DB.
    if not get_settings().meta_business_credentials_enabled:
        return legado(quem)
    try:
        repo = repository()
        selections = await repo.select(SELECTION, {"select": "credential_id", "owner_id": f"eq.{quem.sub}", "limit": 1})
        if not selections:
            raise HTTPException(409, "Selecione uma conexão em Integrações › Meta Ads.")
        row = await owned(repo, quem.sub, selections[0]["credential_id"])
        return CredencialLocal.agora(unseal(row, quem.sub))
    except httpx.HTTPError:
        raise HTTPException(503, "Não foi possível acessar o cofre. Nenhuma credencial alternativa foi usada.") from None


def now():
    return datetime.now(timezone.utc).isoformat()
