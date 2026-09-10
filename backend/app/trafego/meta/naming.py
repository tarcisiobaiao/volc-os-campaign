"""Account-wide naming reservations; campaign names are read, never changed."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import re

import httpx

from .adaptador import AdaptadorMetaSomenteLeitura, ErroDeLeituraMeta
from . import dominio as dom

MAX_NUMBER = 2147483647


@dataclass(frozen=True)
class CampaignHistory:
    maximum: int
    count: int
    complete: bool = True


def number_from_name(name: str) -> int | None:
    # Two supported historical naming families, always anchored at the start.
    match = re.match(r"^\s*(?:CP([0-9]+)(?=$|[\s_·|/–—-])|([0-9]{4,})\s*[-–—])", name, re.I)
    if not match:
        return None
    digits = match.group(1) or match.group(2)
    if len(digits.lstrip('0')) > 10:
        raise ErroDeLeituraMeta('META_NAMING_RANGE_EXHAUSTED', 'O histórico excede a faixa de numeração suportada.')
    number = int(digits.lstrip('0') or '0')
    if number >= MAX_NUMBER:
        raise ErroDeLeituraMeta('META_NAMING_RANGE_EXHAUSTED', 'O histórico excede a faixa de numeração suportada.')
    return number


async def resolve_account(adapter, account_ref: str, secret):
    """Resolve the opaque handle ONLY among accounts available to this token."""
    accounts = await adapter.descobrir_contas(secret)
    try:
        return adapter.resolver_referencia_opaca(accounts, account_ref)
    except dom.ContratoMetaInvalido:
        raise ErroDeLeituraMeta('META_NAMING_ACCOUNT_UNAVAILABLE', 'A conta do rascunho não está disponível nesta conexão.') from None


async def read_campaign_history(adapter, account_id: str, secret) -> CampaignHistory:
    # Reuse transport restrictions/cursor loop detection/page ceiling. The
    # account id MUST already be resolved, never received from the browser.
    account_id = dom.conta_canonica(account_id)
    rows, _ = await adapter._listar_url(
        f'{adapter._base}/{adapter._versao}/act_{account_id}/campaigns', secret,
        fields='id,name', limite=100,
        parametros_extra={'effective_status': json.dumps(['ACTIVE', 'PAUSED', 'ARCHIVED', 'DELETED'])})
    seen, maximum = set(), 0
    for row in rows:
        if (not isinstance(row, dict) or not re.fullmatch(r'\d{1,40}', str(row.get('id', '')))
                or not isinstance(row.get('name'), str) or str(row['id']) in seen):
            raise ErroDeLeituraMeta('META_NAMING_HISTORY_INVALID', 'O histórico de campanhas não pôde ser conferido integralmente.')
        seen.add(str(row['id']))
        maximum = max(maximum, number_from_name(row['name']) or 0)
    return CampaignHistory(maximum=maximum, count=len(rows))


async def resolved_history(account_ref, secret, *, client=None):
    async def read(http):
        adapter = AdaptadorMetaSomenteLeitura(http, limite_por_pagina=100, max_paginas_por_edge=100)
        account = await resolve_account(adapter, account_ref, secret)
        return account, await read_campaign_history(adapter, account.id_externo, secret)
    if client is not None:
        return await asyncio.wait_for(read(client), timeout=90)
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as http:
        return await asyncio.wait_for(read(http), timeout=90)
