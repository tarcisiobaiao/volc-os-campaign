"""Read-only reuse catalog. Historical use is not a verification attestation.

The caller explicitly chooses an opaque account-bound pair; raw identities
remain server-side and are freshly resolved before compilation.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Any

import httpx

from app.trafego.meta.adaptador import AdaptadorMetaSomenteLeitura
from app.trafego.meta.credenciais import SegredoEfemero
from .contrato import ErroDeNascimentoMeta
from .publicos import _conta_externa


def reference(account: str, beneficiary: str, payer: str) -> str:
    return "metareg_" + hashlib.sha256(
        f"{account}:BRAZIL_REGULATION:{beneficiary}:{payer}".encode()
    ).hexdigest()[:32]


async def catalogo(cliente: httpx.AsyncClient, account_ref: str,
                   segredo: SegredoEfemero) -> dict[str, dict[str, Any]]:
    account = await _conta_externa(AdaptadorMetaSomenteLeitura(cliente), account_ref, segredo)
    params = {"fields": "name,regional_regulated_categories,regional_regulation_identities", "limit": "100"}
    result: dict[str, dict[str, Any]] = {}
    cursors: set[str] = set()
    for _ in range(10):
        try:
            response = await cliente.get(
                f"https://graph.facebook.com/v26.0/act_{account}/adsets",
                params=params, headers={"Authorization": segredo.cabecalho_bearer()},
            )
        except httpx.HTTPError:
            raise ErroDeNascimentoMeta("META_REGULATORY_CATALOG_UNAVAILABLE",
                "A leitura de anunciantes não respondeu. Tente novamente sem alterar a seleção.") from None
        if response.status_code != 200:
            raise ErroDeNascimentoMeta("META_REGULATORY_CATALOG_UNAVAILABLE",
                "Não foi possível ler os anunciantes já usados nesta conta. Confira o acesso na Meta.")
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise ErroDeNascimentoMeta("META_REGULATORY_CATALOG_INVALID", "A Meta devolveu um catálogo de anunciantes inválido.")
        for row in body["data"]:
            if not isinstance(row, dict):
                continue
            categories = row.get("regional_regulated_categories") or []
            identities = row.get("regional_regulation_identities")
            if not isinstance(categories, list) or "BRAZIL_REGULATION" not in categories or not isinstance(identities, dict):
                continue
            beneficiary = identities.get("universal_beneficiary")
            payer = identities.get("universal_payer")
            if not all(isinstance(value, str) and re.fullmatch(r"[0-9]{1,40}", value)
                       for value in (beneficiary, payer)):
                continue
            ref = reference(account, beneficiary, payer)
            item = result.setdefault(ref, {"reference": ref,
                "label": "Anunciante já usado nesta conta",
                "source_names": [], "category": "BRAZIL_REGULATION",
                "identities": {"universal_beneficiary": beneficiary, "universal_payer": payer}})
            name = str(row.get("name") or "Conjunto sem nome")[:400]
            if name not in item["source_names"]:
                item["source_names"].append(name)
        paging = body.get("paging") or {}
        if not isinstance(paging, dict):
            break
        if not paging.get("next"):
            return result
        page_cursors = paging.get("cursors") or {}
        cursor = page_cursors.get("after") if isinstance(page_cursors, dict) else None
        if not isinstance(cursor, str) or not cursor or cursor in cursors:
            break
        cursors.add(cursor)
        params["after"] = cursor
    raise ErroDeNascimentoMeta("META_REGULATORY_CATALOG_INCOMPLETE",
        "A leitura de anunciantes não chegou ao fim. Nenhuma identidade foi selecionada automaticamente.")


def publico(items: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # Explicit allowlist: neither raw IDs nor unrelated campaign/adset names
    # belong to the operator's advertiser confirmation.
    result = []
    for ref, item in items.items():
        beneficiary = item.get("beneficiary_name")
        payer = item.get("payer_name")
        label = beneficiary or "Anunciante com nome indisponível"
        if payer and payer != beneficiary:
            label += " · Pagador: " + payer
        if len(items) > 1:
            label += " · " + ref[-6:]
        result.append({"reference": ref, "label": label,
                       "category": item["category"], "beneficiary_name": beneficiary,
                       "payer_name": payer, "names_available": bool(beneficiary and payer)})
    return {"items": result, "complete": True}


async def consultar_publico(cliente: httpx.AsyncClient, account_ref: str,
                            segredo: SegredoEfemero) -> dict[str, Any]:
    items = await catalogo(cliente, account_ref, segredo)
    # Resolve the identity objects themselves, not the names of source adsets
    # or the Business (which may be different from the beneficiary/payer).
    ids = sorted({value for item in items.values() for value in item["identities"].values()})
    semaphore = asyncio.Semaphore(4)
    async def name(identity: str) -> tuple[str, str | None]:
        async with semaphore:
            try:
                response = await cliente.get(f"https://graph.facebook.com/v26.0/{identity}",
                    params={"fields": "name"}, headers={"Authorization": segredo.cabecalho_bearer()}, timeout=10)
                data = response.json() if response.status_code == 200 else {}
                value = data.get("name") if isinstance(data, dict) else None
                if isinstance(value, str) and value.strip():
                    return identity, " ".join(value.split())[:200]
            except (httpx.HTTPError, ValueError):
                pass
            return identity, None
    # Name lookup is enrichment, never a new source of permission or a launch
    # gate. Bound requests when an account has many historical identities.
    names = dict(await asyncio.gather(*(name(identity) for identity in ids[:20])))
    for item in items.values():
        item["beneficiary_name"] = names.get(item["identities"]["universal_beneficiary"])
        item["payer_name"] = names.get(item["identities"]["universal_payer"])
    return publico(items)
