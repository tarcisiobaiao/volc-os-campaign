"""Família `estado`: status, status primário, motivos e política por entidade.

É o estado ATUAL (sem `segments.date`): a janela do contexto não entra na GAQL.
O banco só grava linha nova quando o `estado_hash` muda, então rodar várias
vezes ao dia custa leitura, não linha.
"""
from __future__ import annotations

from typing import Any

from ..contrato import Contexto, enum_nome

# Uma consulta por entidade. A ordem importa para `normalizar`: as linhas não
# dizem de qual GAQL vieram, e a entidade é deduzida pelo recurso mais
# específico presente (ad_group_ad também traz ad_group e campaign).
GAQLS = {
    "keyword": (
        "SELECT ad_group_criterion.resource_name, ad_group_criterion.criterion_id, "
        "ad_group_criterion.status, ad_group_criterion.primary_status, "
        "ad_group_criterion.primary_status_reasons, ad_group_criterion.approval_status, "
        "ad_group.id, campaign.id "
        "FROM ad_group_criterion "
        "WHERE ad_group_criterion.type = 'KEYWORD' "
        "AND ad_group_criterion.status != 'REMOVED' "
        "AND ad_group.status != 'REMOVED' AND campaign.status != 'REMOVED'"
    ),
    "asset_group_asset": (
        "SELECT asset_group_asset.resource_name, asset_group_asset.status, "
        "asset_group_asset.primary_status, asset_group_asset.primary_status_reasons, "
        "asset_group_asset.policy_summary.approval_status, "
        "asset_group_asset.policy_summary.review_status, "
        "asset_group_asset.policy_summary.policy_topic_entries, "
        "asset_group.id, campaign.id "
        "FROM asset_group_asset "
        "WHERE asset_group_asset.status != 'REMOVED' "
        "AND asset_group.status != 'REMOVED' AND campaign.status != 'REMOVED'"
    ),
    "campaign_asset": (
        "SELECT campaign_asset.resource_name, campaign_asset.status, "
        "campaign_asset.primary_status, campaign_asset.primary_status_reasons, campaign.id, "
        # Só aqui a API exige o campo do filtro no SELECT (EXPECTED_REFERENCED_FIELD_IN_SELECT_CLAUSE).
        "campaign.status "
        "FROM campaign_asset "
        "WHERE campaign_asset.status != 'REMOVED' AND campaign.status != 'REMOVED'"
    ),
    "ad_group_ad": (
        "SELECT ad_group_ad.resource_name, ad_group_ad.status, ad_group_ad.primary_status, "
        "ad_group_ad.primary_status_reasons, ad_group_ad.policy_summary.approval_status, "
        "ad_group_ad.policy_summary.review_status, "
        "ad_group_ad.policy_summary.policy_topic_entries, ad_group.id, campaign.id "
        "FROM ad_group_ad "
        "WHERE ad_group_ad.status != 'REMOVED' "
        "AND ad_group.status != 'REMOVED' AND campaign.status != 'REMOVED'"
    ),
    "asset_group": (
        "SELECT asset_group.id, asset_group.status, asset_group.primary_status, "
        "asset_group.primary_status_reasons, campaign.id "
        "FROM asset_group "
        "WHERE asset_group.status != 'REMOVED' AND campaign.status != 'REMOVED'"
    ),
    "ad_group": (
        "SELECT ad_group.id, ad_group.status, ad_group.primary_status, "
        "ad_group.primary_status_reasons, campaign.id "
        "FROM ad_group "
        "WHERE ad_group.status != 'REMOVED' AND campaign.status != 'REMOVED'"
    ),
    "campaign": (
        "SELECT campaign.id, campaign.status, campaign.primary_status, "
        "campaign.primary_status_reasons "
        "FROM campaign "
        "WHERE campaign.status != 'REMOVED'"
    ),
}

# Recurso da GoogleAdsRow que identifica cada entidade, do mais específico ao
# mais genérico.
_RECURSO = {
    "keyword": "ad_group_criterion",
    "asset_group_asset": "asset_group_asset",
    "campaign_asset": "campaign_asset",
    "ad_group_ad": "ad_group_ad",
    "asset_group": "asset_group",
    "ad_group": "ad_group",
    "campaign": "campaign",
}


def _entidade(row: Any) -> str | None:
    for tipo, recurso in _RECURSO.items():
        if recurso in row:
            return tipo
    return None


def _sufixo(resource_name: str) -> str | None:
    # O último segmento do resource name é o id composto estável
    # (`{ad_group_id}~{criterion_id}`, `{asset_group_id}~{asset_id}~{field_type}`…).
    if not resource_name:
        return None
    return resource_name.rsplit("/", 1)[-1] or None


def _motivos(repetido: Any) -> list[str]:
    return [enum_nome(m) for m in repetido]


def _topicos(politica: Any) -> list[dict]:
    return [{"topic": t.topic, "type": enum_nome(t.type_)} for t in politica.policy_topic_entries]


def _id_texto(valor: int) -> str | None:
    return str(valor) if valor else None


class _Estado:
    nome = "estado"
    rpc = "volc_registrar_gads_fatos"

    def gaql(self, ctx: Contexto) -> list[str]:
        return list(GAQLS.values())

    def normalizar(self, row: Any, ctx: Contexto) -> dict | None:
        tipo = _entidade(row)
        if tipo is None:
            return None
        msg = getattr(row, _RECURSO[tipo])
        if tipo in ("campaign", "ad_group", "asset_group"):
            entidade_id = _id_texto(msg.id)
        else:
            entidade_id = _sufixo(msg.resource_name)
        if entidade_id is None:
            return None

        aprovacao = revisao = None
        topicos: list[dict] = []
        if tipo in ("ad_group_ad", "asset_group_asset"):
            aprovacao = enum_nome(msg.policy_summary.approval_status)
            revisao = enum_nome(msg.policy_summary.review_status)
            topicos = _topicos(msg.policy_summary)
        elif tipo == "keyword":
            aprovacao = enum_nome(msg.approval_status)

        return {
            "entidade_tipo": tipo,
            "entidade_id": entidade_id,
            "campaign_id": _id_texto(row.campaign.id),
            "status": enum_nome(msg.status),
            "primary_status": enum_nome(msg.primary_status),
            "primary_status_reasons": _motivos(msg.primary_status_reasons),
            "aprovacao": aprovacao,
            "revisao": revisao,
            "topicos_politica": topicos,
            "observado_em": ctx.colhida_iso,
        }


FAMILIA = _Estado()
