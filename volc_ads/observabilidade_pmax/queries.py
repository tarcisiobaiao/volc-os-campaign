"""Montador de consultas GAQL (Google Ads Query Language) estritamente read-only.

Compatível com Google Ads API v25 para recursos do ecossistema Performance Max (PMax).
Garante por construção e validação que nenhuma instrução mutável, validate_only
ou operação de escrita seja emitida.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

# Palavras-chave estritamente proibidas para assegurar read-only absoluto
FORBIDDEN_KEYWORDS = frozenset(
    {
        "MUTATE",
        "INSERT",
        "UPDATE",
        "DELETE",
        "CREATE",
        "DROP",
        "ALTER",
        "EXECUTE",
        "CALL",
        "VALIDATE_ONLY",
        "TRUNCATE",
        "MERGE",
        "UPSERT",
    }
)

IDENTIFIER_PATTERN = re.compile(r"^[0-9a-zA-Z_\-/]+$")


class GAQLSecurityError(ValueError):
    """Exceção levantada se uma consulta violar garantias de segurança read-only."""

    pass


class PMaxV25ContractError(RuntimeError):
    """O SDK local não confirma o campo que a consulta pretende selecionar."""


V25_DESCRIPTOR_FIELDS = {
    "campaign": frozenset(
        {
            "id", "name", "resource_name", "status", "serving_status",
            "advertising_channel_type", "bidding_strategy_type",
            "maximize_conversions", "maximize_conversion_value",
            "brand_guidelines_enabled",
        }
    ),
    "asset_group": frozenset(
        {
            "id", "resource_name", "name", "campaign", "status",
            "primary_status", "primary_status_reasons", "ad_strength",
            "asset_coverage", "final_urls", "final_mobile_urls", "path1", "path2",
        }
    ),
    "asset_group_asset": frozenset(
        {
            "resource_name", "asset_group", "asset", "field_type", "status",
            "primary_status", "primary_status_reasons", "primary_status_details",
            "policy_summary", "source",
        }
    ),
    "campaign_asset": frozenset(
        {
            "resource_name", "campaign", "asset", "field_type", "status",
            "primary_status", "primary_status_reasons", "primary_status_details", "source",
        }
    ),
}

V25_NESTED_DESCRIPTOR_PATHS = {
    "campaign": (
        "maximize_conversions.target_cpa_micros",
        "maximize_conversion_value.target_roas",
    ),
    "asset_group": (
        "asset_coverage.ad_strength_action_items.action_item_type",
        "asset_coverage.ad_strength_action_items.add_asset_details.asset_field_type",
        "asset_coverage.ad_strength_action_items.add_asset_details.asset_count",
        "asset_coverage.ad_strength_action_items.add_asset_details.video_aspect_ratio_requirement",
    ),
    "asset_group_asset": (
        "primary_status_details.status",
        "primary_status_details.reason",
        "primary_status_details.asset_disapproved.offline_evaluation_error_reasons",
    ),
    "campaign_asset": (
        "primary_status_details.status",
        "primary_status_details.reason",
        "primary_status_details.asset_disapproved.offline_evaluation_error_reasons",
    ),
}


def assert_v25_descriptor_contract() -> None:
    """Contraprova local contra descriptors do SDK v25; não usa rede."""
    try:
        from google.ads.googleads.v25.resources.types import (
            asset_group,
            asset_group_asset,
            campaign,
            campaign_asset,
        )
    except ImportError as exc:  # pragma: no cover - depende do ambiente de execução
        raise PMaxV25ContractError("Google Ads SDK v25 indisponível para validar o contrato") from exc

    descriptors = {
        "campaign": set(campaign.Campaign.meta.fields),
        "asset_group": set(asset_group.AssetGroup.meta.fields),
        "asset_group_asset": set(asset_group_asset.AssetGroupAsset.meta.fields),
        "campaign_asset": set(campaign_asset.CampaignAsset.meta.fields),
    }
    missing = {
        resource: sorted(fields - descriptors[resource])
        for resource, fields in V25_DESCRIPTOR_FIELDS.items()
        if fields - descriptors[resource]
    }
    if missing:
        raise PMaxV25ContractError(f"Campos ausentes nos descriptors v25: {missing}")

    roots = {
        "campaign": campaign.Campaign,
        "asset_group": asset_group.AssetGroup,
        "asset_group_asset": asset_group_asset.AssetGroupAsset,
        "campaign_asset": campaign_asset.CampaignAsset,
    }
    missing_paths: list[str] = []
    for resource, paths in V25_NESTED_DESCRIPTOR_PATHS.items():
        for path in paths:
            message = roots[resource]
            for part in path.split("."):
                field = message.meta.fields.get(part) or message.meta.fields.get(f"{part}_")
                if field is None:
                    missing_paths.append(f"{resource}.{path}")
                    break
                message = field.message
                if message is None and part != path.split(".")[-1]:
                    missing_paths.append(f"{resource}.{path}")
                    break
    if missing_paths:
        raise PMaxV25ContractError(f"Caminhos ausentes nos descriptors v25: {sorted(set(missing_paths))}")


def validate_customer_id(customer_id: str) -> str:
    """Normaliza e valida o Customer ID (10 dígitos com ou sem hífens)."""
    cleaned = customer_id.replace("-", "").strip()
    if not cleaned.isdigit() or len(cleaned) != 10:
        raise ValueError(
            f"Invalid Google Ads customer_id: '{customer_id}'. Expected 10 digits."
        )
    return cleaned


def validate_identifier(ident: str, field_name: str = "identifier") -> str:
    """Valida identificador alfanumérico seguro para GAQL."""
    cleaned = ident.strip()
    if not cleaned or not IDENTIFIER_PATTERN.match(cleaned):
        raise ValueError(
            f"Invalid {field_name}: '{ident}'. Contains forbidden characters."
        )
    return cleaned


def assert_read_only_gaql(query: str) -> None:
    """Valida que a consulta GAQL é estritamente uma operação SELECT de leitura."""
    normalized = query.strip()
    if not normalized.upper().startswith("SELECT"):
        raise GAQLSecurityError(
            f"Query must begin with 'SELECT'. Found: {normalized[:20]!r}"
        )

    # Identificar tokens para verificar palavras-chave proibidas
    tokens = set(re.findall(r"\b[A-Za-z_]+\b", normalized.upper()))
    intersection = tokens.intersection(FORBIDDEN_KEYWORDS)
    if intersection:
        raise GAQLSecurityError(
            f"Forbidden keywords detected in GAQL query: {sorted(list(intersection))}"
        )


def build_pmax_campaigns_query(
    campaign_ids: Optional[Iterable[str]] = None,
    status_filter: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> str:
    """Monta consulta GAQL para listar e observar campanhas PMax."""
    clauses = ["campaign.advertising_channel_type = 'PERFORMANCE_MAX'"]

    if campaign_ids:
        safe_ids = [validate_identifier(str(cid), "campaign_id") for cid in campaign_ids]
        if safe_ids:
            joined_ids = ", ".join(f"'{cid}'" for cid in safe_ids)
            clauses.append(f"campaign.id IN ({joined_ids})")

    if status_filter:
        safe_statuses = [
            validate_identifier(str(s).upper(), "campaign_status")
            for s in status_filter
        ]
        if safe_statuses:
            joined_statuses = ", ".join(f"'{s}'" for s in safe_statuses)
            clauses.append(f"campaign.status IN ({joined_statuses})")

    where_clause = " AND ".join(clauses)

    query = (
        "SELECT "
        "campaign.resource_name, "
        "campaign.id, "
        "campaign.name, "
        "campaign.status, "
        "campaign.serving_status, "
        "campaign.advertising_channel_type, "
        "campaign.bidding_strategy_type, "
        "campaign.maximize_conversions.target_cpa_micros, "
        "campaign.maximize_conversion_value.target_roas, "
        "campaign.brand_guidelines_enabled, "
        "campaign_budget.amount_micros, "
        "metrics.impressions, "
        "metrics.clicks, "
        "metrics.cost_micros, "
        "metrics.conversions, "
        "metrics.conversions_value, "
        "metrics.ctr, "
        "metrics.average_cpc "
        "FROM campaign "
        f"WHERE {where_clause}"
    )

    if limit is not None and limit > 0:
        query += f" LIMIT {int(limit)}"

    assert_read_only_gaql(query)
    return query


def build_pmax_asset_groups_query(
    campaign_ids: Optional[Iterable[str]] = None,
    asset_group_ids: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> str:
    """Monta consulta GAQL para observar Asset Groups de campanhas PMax."""
    clauses = ["campaign.advertising_channel_type = 'PERFORMANCE_MAX'"]

    if campaign_ids:
        safe_cids = [
            validate_identifier(str(cid), "campaign_id") for cid in campaign_ids
        ]
        if safe_cids:
            joined = ", ".join(f"'{cid}'" for cid in safe_cids)
            clauses.append(f"campaign.id IN ({joined})")

    if asset_group_ids:
        safe_agids = [
            validate_identifier(str(agid), "asset_group_id")
            for agid in asset_group_ids
        ]
        if safe_agids:
            joined = ", ".join(f"'{agid}'" for agid in safe_agids)
            clauses.append(f"asset_group.id IN ({joined})")

    where_clause = " AND ".join(clauses)

    query = (
        "SELECT "
        "asset_group.resource_name, "
        "asset_group.id, "
        "asset_group.name, "
        "asset_group.campaign, "
        "asset_group.status, "
        "asset_group.primary_status, "
        "asset_group.primary_status_reasons, "
        "asset_group.ad_strength, "
        "asset_group.asset_coverage.ad_strength_action_items.action_item_type, "
        "asset_group.asset_coverage.ad_strength_action_items.add_asset_details.asset_field_type, "
        "asset_group.asset_coverage.ad_strength_action_items.add_asset_details.asset_count, "
        "asset_group.asset_coverage.ad_strength_action_items.add_asset_details.video_aspect_ratio_requirement, "
        "asset_group.final_urls, "
        "asset_group.final_mobile_urls, "
        "asset_group.path1, "
        "asset_group.path2, "
        "campaign.id "
        "FROM asset_group "
        f"WHERE {where_clause}"
    )

    if limit is not None and limit > 0:
        query += f" LIMIT {int(limit)}"

    assert_read_only_gaql(query)
    return query


def build_pmax_asset_group_assets_query(
    customer_id: str,
    campaign_ids: Optional[Iterable[str]] = None,
    asset_group_ids: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> str:
    """Monta consulta GAQL para observar vínculos AssetGroupAsset de PMax."""
    safe_customer_id = validate_customer_id(customer_id)
    clauses = ["campaign.advertising_channel_type = 'PERFORMANCE_MAX'"]

    if campaign_ids:
        safe_cids = [
            validate_identifier(str(cid), "campaign_id") for cid in campaign_ids
        ]
        if safe_cids:
            joined = ", ".join(f"'{cid}'" for cid in safe_cids)
            clauses.append(f"campaign.id IN ({joined})")

    if asset_group_ids:
        safe_agids = [
            validate_identifier(str(agid), "asset_group_id")
            for agid in asset_group_ids
        ]
        if safe_agids:
            joined = ", ".join(
                f"'customers/{safe_customer_id}/assetGroups/{agid}'" for agid in safe_agids
            )
            # Para flexibilidade com resource names ou IDs
            clauses.append(f"asset_group_asset.asset_group IN ({joined})")

    where_clause = " AND ".join(clauses)

    query = (
        "SELECT "
        "asset_group_asset.resource_name, "
        "asset_group_asset.asset_group, "
        "asset_group_asset.asset, "
        "asset_group_asset.field_type, "
        "asset_group_asset.status, "
        "asset_group_asset.primary_status, "
        "asset_group_asset.primary_status_reasons, "
        "asset_group_asset.primary_status_details.status, "
        "asset_group_asset.primary_status_details.reason, "
        "asset_group_asset.primary_status_details.asset_disapproved.offline_evaluation_error_reasons, "
        "asset_group_asset.source, "
        "asset_group_asset.policy_summary.approval_status, "
        "asset_group_asset.policy_summary.policy_topic_entries, "
        "campaign.id "
        "FROM asset_group_asset "
        f"WHERE {where_clause}"
    )

    if limit is not None and limit > 0:
        query += f" LIMIT {int(limit)}"

    assert_read_only_gaql(query)
    return query


def build_pmax_assets_query(
    asset_ids: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> str:
    """Monta consulta GAQL para inspecionar detalhes de recursos Asset."""
    clauses = []
    if asset_ids:
        safe_aids = [validate_identifier(str(aid), "asset_id") for aid in asset_ids]
        if safe_aids:
            joined = ", ".join(f"'{aid}'" for aid in safe_aids)
            clauses.append(f"asset.id IN ({joined})")

    where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""

    query = (
        "SELECT "
        "asset.resource_name, "
        "asset.id, "
        "asset.name, "
        "asset.type, "
        "asset.text_asset.text, "
        "asset.youtube_video_asset.youtube_video_id, "
        "asset.youtube_video_asset.youtube_video_title, "
        "asset.image_asset.full_size.url, "
        "asset.policy_summary.approval_status, "
        "asset.policy_summary.policy_topic_entries "
        "FROM asset"
        f"{where_clause}"
    )

    if limit is not None and limit > 0:
        query += f" LIMIT {int(limit)}"

    assert_read_only_gaql(query)
    return query


def build_pmax_asset_group_signals_query(
    customer_id: str,
    asset_group_ids: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> str:
    """Monta consulta GAQL para observar sinais (Audiences / Search Themes) do Asset Group."""
    safe_customer_id = validate_customer_id(customer_id)
    clauses = []
    if asset_group_ids:
        safe_agids = [
            validate_identifier(str(agid), "asset_group_id")
            for agid in asset_group_ids
        ]
        if safe_agids:
            joined = ", ".join(
                f"'customers/{safe_customer_id}/assetGroups/{agid}'" for agid in safe_agids
            )
            clauses.append(f"asset_group_signal.asset_group IN ({joined})")

    where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""

    query = (
        "SELECT "
        "asset_group_signal.resource_name, "
        "asset_group_signal.asset_group, "
        "asset_group_signal.audience.audience, "
        "asset_group_signal.search_theme.text "
        "FROM asset_group_signal"
        f"{where_clause}"
    )

    if limit is not None and limit > 0:
        query += f" LIMIT {int(limit)}"

    assert_read_only_gaql(query)
    return query


def build_pmax_campaign_assets_query(
    campaign_ids: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> str:
    """Lê vínculos de marca que migram para CampaignAsset com Brand Guidelines."""
    clauses = ["campaign.advertising_channel_type = 'PERFORMANCE_MAX'"]
    if campaign_ids:
        safe_ids = [validate_identifier(str(cid), "campaign_id") for cid in campaign_ids]
        if safe_ids:
            clauses.append("campaign.id IN (" + ", ".join(f"'{cid}'" for cid in safe_ids) + ")")
    query = (
        "SELECT "
        "campaign_asset.resource_name, campaign_asset.campaign, campaign_asset.asset, "
        "campaign_asset.field_type, campaign_asset.status, campaign_asset.primary_status, "
        "campaign_asset.primary_status_reasons, campaign_asset.primary_status_details.status, "
        "campaign_asset.primary_status_details.reason, "
        "campaign_asset.primary_status_details.asset_disapproved.offline_evaluation_error_reasons, "
        "campaign_asset.source, campaign.id "
        "FROM campaign_asset WHERE " + " AND ".join(clauses)
    )
    if limit is not None and limit > 0:
        query += f" LIMIT {int(limit)}"
    assert_read_only_gaql(query)
    return query


def build_pmax_observability_bundle_queries(
    customer_id: str,
    campaign_id: Optional[str] = None,
) -> dict[str, str]:
    """Gera o conjunto completo de queries read-only para um snapshot de observabilidade."""
    safe_customer_id = validate_customer_id(customer_id)
    assert_v25_descriptor_contract()
    cids = [campaign_id] if campaign_id else None

    return {
        "campaigns": build_pmax_campaigns_query(campaign_ids=cids),
        "asset_groups": build_pmax_asset_groups_query(campaign_ids=cids),
        "asset_group_assets": build_pmax_asset_group_assets_query(safe_customer_id, campaign_ids=cids),
        "assets": build_pmax_assets_query(),
        "signals": build_pmax_asset_group_signals_query(safe_customer_id),
        "campaign_assets": build_pmax_campaign_assets_query(campaign_ids=cids),
    }
