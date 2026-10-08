"""Família `mudanca`: histórico de alterações da conta (`change_event`).

A API só guarda 30 dias de `change_event` e recusa a consulta sem filtro de
`change_date_time` e sem LIMIT. O banco (`google_ads_mudanca`) é append-only
por `change_event_rn`: reler a mesma janela não duplica evento.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from google.protobuf import json_format

from ..contrato import Contexto, enum_nome

LIMITE = 10000
OPERACOES = ("CREATE", "UPDATE", "REMOVE")

CAMPOS = (
    "change_event.resource_name",
    "change_event.change_date_time",
    "change_event.change_resource_type",
    "change_event.change_resource_name",
    "change_event.resource_change_operation",
    "change_event.client_type",
    "change_event.user_email",
    "change_event.changed_fields",
    "change_event.old_resource",
    "change_event.new_resource",
    "change_event.campaign",
    "change_event.ad_group",
)

_CAMPANHA = re.compile(r"/campaigns/(\d+)")
_GRUPO = re.compile(r"/adGroups/(\d+)")
# adGroupAds, adGroupCriteria, adGroupAssets e adGroupBidModifiers carregam o
# grupo como primeiro componente do id composto (`{ad_group_id}~...`).
_GRUPO_COMPOSTO = re.compile(r"/adGroup(?:Ads|Criteria|Assets|BidModifiers)/(\d+)~")


def _id(padroes: tuple[re.Pattern, ...], *nomes: str) -> str | None:
    for nome in nomes:
        if not nome:
            continue
        for p in padroes:
            m = p.search(nome)
            if m:
                return m.group(1)
    return None


def _instante(texto: str, fuso: str) -> str | None:
    # A API devolve "AAAA-MM-DD HH:MM:SS[.ffffff]" no fuso da conta, sem offset.
    if not texto:
        return None
    formato = "%Y-%m-%d %H:%M:%S.%f" if "." in texto else "%Y-%m-%d %H:%M:%S"
    return datetime.strptime(texto, formato).replace(tzinfo=ZoneInfo(fuso)).isoformat()


def _recurso(mudado: Any) -> dict | None:
    """O sub-recurso preenchido de um `ChangedResource`, como dict JSON.

    Só um dos campos (campaign, ad_group, ad…) vem preenchido; CREATE não tem
    `old_resource` e REMOVE não tem `new_resource` — aí vale None.
    """
    if mudado is None:
        return None
    pb = type(mudado).pb(mudado)
    preenchidos = pb.ListFields()
    if not preenchidos:
        return None
    _, sub = preenchidos[0]
    return json_format.MessageToDict(sub, preserving_proto_field_name=True)


class _Mudanca:
    nome = "mudanca"
    rpc = "volc_registrar_gads_fatos"
    limite = LIMITE

    def gaql(self, ctx: Contexto) -> str:
        ini = f"{ctx.data_inicio.isoformat()} 00:00:00"
        fim = f"{ctx.data_fim.isoformat()} 23:59:59"
        return (f"SELECT {', '.join(CAMPOS)} FROM change_event "
                f"WHERE change_event.change_date_time >= '{ini}' "
                f"AND change_event.change_date_time <= '{fim}' "
                f"ORDER BY change_event.change_date_time "
                f"LIMIT {LIMITE}")

    def normalizar(self, row: Any, ctx: Contexto) -> dict | None:
        ev = row.change_event
        if not ev.resource_name:
            return None
        operacao = enum_nome(ev.resource_change_operation)
        recurso = ev.change_resource_name or None
        return {
            "change_event_rn": ev.resource_name,
            "ocorrido_em": _instante(ev.change_date_time, ctx.fuso),
            "tipo_recurso": enum_nome(ev.change_resource_type),
            "recurso_alterado": recurso,
            "operacao": operacao if operacao in OPERACOES else "UNKNOWN",
            "campaign_id": _id((_CAMPANHA,), ev.campaign, recurso),
            "ad_group_id": _id((_GRUPO, _GRUPO_COMPOSTO), ev.ad_group, recurso),
            "cliente": enum_nome(ev.client_type),
            "usuario": ev.user_email or None,
            "campos_alterados": list(ev.changed_fields.paths),
            "antes": _recurso(ev.old_resource),
            "depois": _recurso(ev.new_resource),
            "colhida_em": ctx.colhida_iso,
        }


FAMILIA = _Mudanca()
