"""Projetor determinístico de linhas da Google Ads API v25 para DTOs PMax imutáveis.

Preserva com precisão os estados epistêmicos dos campos:
- Valores presentes permanecem PRESENT
- Zeros numéricos legítimos são marcados como MEASURED_ZERO
- Campos nulos ou ausentes são marcados como FIELD_ABSENT
- Campos não coletados são marcados como NOT_COLLECTED
- Erros de parsing são isolados no campo afetado como COLLECTION_FAILED
- Dados com timestamp expirado são marcados como STALE
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Optional, TypeVar

from volc_ads.observabilidade_pmax.types import (
    ObservationState,
    ObservedValue,
    PMaxAdStrength,
    PMaxAssetDTO,
    PMaxAssetFieldType,
    PMaxAssetGroupAssetDTO,
    PMaxAssetGroupDTO,
    PMaxAssetGroupPrimaryStatus,
    PMaxAssetGroupSignalDTO,
    PMaxAssetGroupStatus,
    PMaxAssetPolicyApprovalStatus,
    PMaxBiddingStrategyType,
    PMaxCampaignDTO,
    PMaxCampaignAssetDTO,
    PMaxCampaignMetricsDTO,
    PMaxCampaignServingStatus,
    PMaxCampaignStatus,
)

T = TypeVar("T")


def extract_nested_path(data: dict[str, Any], path: str) -> tuple[bool, Any]:
    """Navega recursivamente em um dicionário via notação pontilhada ou chave direta.

    Suporta tanto formato aninhado ({"campaign": {"id": 123}})
    quanto formato plano com ponto ({"campaign.id": 123}).
    """
    if path in data:
        return True, data[path]

    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


_extract_path = extract_nested_path


def extract_observed(
    data: dict[str, Any],
    path: str,
    parser: Optional[Callable[[Any], T]] = None,
    collected_at: Optional[datetime] = None,
    stale_threshold_seconds: Optional[int] = None,
) -> ObservedValue[T]:
    """Extrai um campo com preservação estrita do estado de observação."""
    exists, raw_val = _extract_path(data, path)

    if not exists or raw_val is None:
        return ObservedValue.field_absent(source_path=path, collected_at=collected_at)

    # Verifica se o dado é stale
    is_stale = False
    if collected_at is not None and stale_threshold_seconds is not None:
        now = datetime.now(timezone.utc)
        tz_collected = (
            collected_at
            if collected_at.tzinfo is not None
            else collected_at.replace(tzinfo=timezone.utc)
        )
        age = (now - tz_collected).total_seconds()
        if age > stale_threshold_seconds:
            is_stale = True

    try:
        parsed_val: Any = parser(raw_val) if parser is not None else raw_val
    except Exception as err:
        return ObservedValue.collection_failed(
            error_message=f"Failed to parse '{path}' with value {raw_val!r}: {err}",
            source_path=path,
            collected_at=collected_at,
        )

    if is_stale:
        return ObservedValue.stale(
            value=parsed_val,
            source_path=path,
            collected_at=collected_at,
        )

    # Diferenciação estrita de zero medido para tipos numéricos
    if isinstance(parsed_val, (int, float)) and not isinstance(parsed_val, bool):
        if parsed_val == 0:
            return ObservedValue.measured_zero(
                value=parsed_val,
                source_path=path,
                collected_at=collected_at,
            )

    return ObservedValue.present(
        value=parsed_val,
        source_path=path,
        collected_at=collected_at,
    )


def _safe_str(val: Any) -> str:
    return str(val).strip()


def _safe_int(val: Any) -> int:
    return int(val)


def _safe_float(val: Any) -> float:
    return float(val)


def _safe_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)


def _safe_enum(enum_cls: type[T], val: Any) -> T:
    if isinstance(val, enum_cls):
        return val
    normalized = str(val).upper().strip()
    try:
        return enum_cls[normalized]  # type: ignore[index]
    except KeyError:
        # Fallback para enum desconhecido se existir UNKNOWN, senão falha
        if hasattr(enum_cls, "UNKNOWN"):
            return getattr(enum_cls, "UNKNOWN")
        raise ValueError(f"Value '{val}' is not a valid {enum_cls.__name__}")


def extract_resource_id(resource_name_or_id: str) -> str:
    """Extrai o ID numérico/identificador final de um resource_name do Google Ads.

    Exemplo: 'customers/123/campaigns/456' -> '456'
    """
    cleaned = str(resource_name_or_id).strip()
    if "/" in cleaned:
        return cleaned.split("/")[-1]
    return cleaned


def project_asset_row(
    row: dict[str, Any],
    collected_at: Optional[datetime] = None,
    stale_threshold_seconds: Optional[int] = None,
) -> PMaxAssetDTO:
    """Projeta um registro de recurso Asset."""
    # Resource name ou ID
    exists_rn, raw_rn = _extract_path(row, "asset.resource_name")
    exists_id, raw_id = _extract_path(row, "asset.id")

    if exists_rn and raw_rn:
        resource_name = str(raw_rn)
        asset_id = extract_resource_id(resource_name)
    elif exists_id and raw_id:
        raise ValueError("Asset row has id but no real 'asset.resource_name'")
    else:
        raise ValueError("Asset row missing both 'asset.resource_name' and 'asset.id'")

    name_obs = extract_observed(
        row,
        "asset.name",
        _safe_str,
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    _, raw_type = _extract_path(row, "asset.type")
    asset_type = str(raw_type) if raw_type is not None else "UNKNOWN"

    text_obs = extract_observed(
        row,
        "asset.text_asset.text",
        _safe_str,
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    yt_id_obs = extract_observed(
        row,
        "asset.youtube_video_asset.youtube_video_id",
        _safe_str,
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    yt_title_obs = extract_observed(
        row,
        "asset.youtube_video_asset.youtube_video_title",
        _safe_str,
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    image_url_obs = extract_observed(
        row,
        "asset.image_asset.full_size.url",
        _safe_str,
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    policy_status_obs = extract_observed(
        row,
        "asset.policy_summary.approval_status",
        lambda v: _safe_enum(PMaxAssetPolicyApprovalStatus, v),
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    _, raw_topics = _extract_path(row, "asset.policy_summary.policy_topic_entries")
    policy_topics: tuple[str, ...] = ()
    if isinstance(raw_topics, list):
        policy_topics = tuple(str(t.get("topic", t) if isinstance(t, dict) else t) for t in raw_topics)

    # Hash determinístico do payload para auditoria
    payload_hash = hashlib.sha256(
        json.dumps(row, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    return PMaxAssetDTO(
        resource_name=resource_name,
        id=asset_id,
        name=name_obs,
        asset_type=asset_type,
        text_content=text_obs,
        youtube_video_id=yt_id_obs,
        youtube_video_title=yt_title_obs,
        image_url=image_url_obs,
        policy_approval_status=policy_status_obs,
        policy_topic_entries=policy_topics,
        source_payload_hash=payload_hash,
    )


def project_asset_group_asset_row(
    row: dict[str, Any],
    asset_lookup: Optional[dict[str, PMaxAssetDTO]] = None,
    collected_at: Optional[datetime] = None,
    stale_threshold_seconds: Optional[int] = None,
) -> PMaxAssetGroupAssetDTO:
    """Projeta um registro de vínculo AssetGroupAsset."""
    exists_ag, raw_ag = _extract_path(row, "asset_group_asset.asset_group")
    exists_a, raw_a = _extract_path(row, "asset_group_asset.asset")

    if not exists_ag or not raw_ag:
        raise ValueError("AssetGroupAsset row missing 'asset_group_asset.asset_group'")
    if not exists_a or not raw_a:
        raise ValueError("AssetGroupAsset row missing 'asset_group_asset.asset'")

    asset_group_id = extract_resource_id(str(raw_ag))
    asset_id = extract_resource_id(str(raw_a))
    exists_rn, raw_rn = _extract_path(row, "asset_group_asset.resource_name")
    if not exists_rn or not raw_rn:
        raise ValueError("AssetGroupAsset row missing real resource_name")
    resource_name = str(raw_rn)

    _, raw_field_type = _extract_path(row, "asset_group_asset.field_type")
    field_type = (
        _safe_enum(PMaxAssetFieldType, raw_field_type)
        if raw_field_type is not None
        else PMaxAssetFieldType.UNKNOWN
    )

    _, raw_status = _extract_path(row, "asset_group_asset.status")
    status = str(raw_status) if raw_status is not None else "UNKNOWN"

    primary_status_obs = extract_observed(
        row,
        "asset_group_asset.primary_status",
        _safe_str,
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    _, raw_primary_reasons = _extract_path(row, "asset_group_asset.primary_status_reasons")
    primary_reasons = tuple(str(v) for v in raw_primary_reasons) if isinstance(raw_primary_reasons, list) else ()
    _, raw_primary_details = _extract_path(row, "asset_group_asset.primary_status_details")
    primary_details = tuple(v for v in raw_primary_details if isinstance(v, dict)) if isinstance(raw_primary_details, list) else ()
    source_obs = extract_observed(
        row, "asset_group_asset.source", _safe_str,
        collected_at=collected_at, stale_threshold_seconds=stale_threshold_seconds,
    )

    policy_status_obs = extract_observed(
        row,
        "asset_group_asset.policy_summary.approval_status",
        lambda v: _safe_enum(PMaxAssetPolicyApprovalStatus, v),
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    _, raw_topics = _extract_path(
        row, "asset_group_asset.policy_summary.policy_topic_entries"
    )
    policy_reasons: tuple[str, ...] = ()
    if isinstance(raw_topics, list):
        policy_reasons = tuple(
            str(t.get("topic", t) if isinstance(t, dict) else t) for t in raw_topics
        )

    asset_details = None
    if asset_lookup and asset_id in asset_lookup:
        asset_details = asset_lookup[asset_id]
    elif asset_lookup and str(raw_a) in asset_lookup:
        asset_details = asset_lookup[str(raw_a)]

    return PMaxAssetGroupAssetDTO(
        resource_name=resource_name,
        asset_group_id=asset_group_id,
        asset_id=asset_id,
        field_type=field_type,
        status=status,
        primary_status=primary_status_obs,
        primary_status_reasons=primary_reasons,
        primary_status_details=primary_details,
        source=source_obs,
        policy_approval_status=policy_status_obs,
        policy_summary_reasons=policy_reasons,
        asset_details=asset_details,
    )


def project_asset_group_signal_row(
    row: dict[str, Any],
    collected_at: Optional[datetime] = None,
    stale_threshold_seconds: Optional[int] = None,
) -> PMaxAssetGroupSignalDTO:
    """Projeta um registro de AssetGroupSignal."""
    exists_rn, raw_rn = _extract_path(row, "asset_group_signal.resource_name")
    exists_ag, raw_ag = _extract_path(row, "asset_group_signal.asset_group")

    if not exists_rn or not raw_rn or not exists_ag or not raw_ag:
        raise ValueError("AssetGroupSignal row missing real resource_name/asset_group")
    resource_name = str(raw_rn)
    asset_group_id = extract_resource_id(str(raw_ag))

    _, raw_aud = _extract_path(row, "asset_group_signal.audience.audience")
    _, raw_theme = _extract_path(row, "asset_group_signal.search_theme.text")

    if raw_theme is not None:
        signal_type = "SEARCH_THEME"
        display_name_obs = extract_observed(
            row,
            "asset_group_signal.search_theme.text",
            _safe_str,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        )
    elif raw_aud is not None:
        signal_type = "AUDIENCE"
        display_name_obs = extract_observed(
            row,
            "asset_group_signal.audience.audience",
            _safe_str,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        )
    else:
        signal_type = "UNKNOWN"
        display_name_obs = ObservedValue.not_collected(
            source_path="asset_group_signal"
        )

    return PMaxAssetGroupSignalDTO(
        resource_name=resource_name,
        asset_group_id=asset_group_id,
        signal_type=signal_type,
        display_name=display_name_obs,
        signal_payload=row.get("asset_group_signal", {}),
    )


def project_campaign_asset_row(
    row: dict[str, Any],
    asset_lookup: Optional[dict[str, PMaxAssetDTO]] = None,
    collected_at: Optional[datetime] = None,
    stale_threshold_seconds: Optional[int] = None,
) -> PMaxCampaignAssetDTO:
    """Projeta BUSINESS_NAME/LOGO no nível CampaignAsset sem inventar vínculo."""
    exists_rn, raw_rn = _extract_path(row, "campaign_asset.resource_name")
    exists_campaign, raw_campaign = _extract_path(row, "campaign_asset.campaign")
    exists_asset, raw_asset = _extract_path(row, "campaign_asset.asset")
    if not (exists_rn and raw_rn and exists_campaign and raw_campaign and exists_asset and raw_asset):
        raise ValueError("CampaignAsset row missing real resource_name/campaign/asset")
    asset_id = extract_resource_id(str(raw_asset))
    _, raw_field_type = _extract_path(row, "campaign_asset.field_type")
    _, raw_status = _extract_path(row, "campaign_asset.status")
    _, raw_reasons = _extract_path(row, "campaign_asset.primary_status_reasons")
    _, raw_details = _extract_path(row, "campaign_asset.primary_status_details")
    return PMaxCampaignAssetDTO(
        resource_name=str(raw_rn),
        campaign_id=extract_resource_id(str(raw_campaign)),
        asset_id=asset_id,
        field_type=_safe_enum(PMaxAssetFieldType, raw_field_type) if raw_field_type else PMaxAssetFieldType.UNKNOWN,
        status=str(raw_status) if raw_status is not None else "UNKNOWN",
        primary_status=extract_observed(
            row, "campaign_asset.primary_status", _safe_str,
            collected_at=collected_at, stale_threshold_seconds=stale_threshold_seconds,
        ),
        primary_status_reasons=tuple(str(v) for v in raw_reasons) if isinstance(raw_reasons, list) else (),
        primary_status_details=tuple(v for v in raw_details if isinstance(v, dict)) if isinstance(raw_details, list) else (),
        source=extract_observed(
            row, "campaign_asset.source", _safe_str,
            collected_at=collected_at, stale_threshold_seconds=stale_threshold_seconds,
        ),
        asset_details=(asset_lookup or {}).get(asset_id) or (asset_lookup or {}).get(str(raw_asset)),
    )


def project_asset_group_row(
    row: dict[str, Any],
    assets: tuple[PMaxAssetGroupAssetDTO, ...] = (),
    signals: tuple[PMaxAssetGroupSignalDTO, ...] = (),
    collected_at: Optional[datetime] = None,
    stale_threshold_seconds: Optional[int] = None,
) -> PMaxAssetGroupDTO:
    """Projeta um Asset Group com seus vínculos e sinais anexados."""
    exists_id, raw_id = _extract_path(row, "asset_group.id")
    exists_rn, raw_rn = _extract_path(row, "asset_group.resource_name")

    if exists_id and raw_id:
        ag_id = str(raw_id)
        if not exists_rn or not raw_rn:
            raise ValueError("AssetGroup row has id but no real 'asset_group.resource_name'")
        resource_name = str(raw_rn)
    elif exists_rn and raw_rn:
        resource_name = str(raw_rn)
        ag_id = extract_resource_id(resource_name)
    else:
        raise ValueError("AssetGroup row missing both 'asset_group.id' and 'asset_group.resource_name'")

    _, raw_name = _extract_path(row, "asset_group.name")
    name = str(raw_name) if raw_name is not None else ""

    _, raw_camp = _extract_path(row, "asset_group.campaign")
    campaign_id = extract_resource_id(str(raw_camp)) if raw_camp is not None else ""

    _, raw_status = _extract_path(row, "asset_group.status")
    status = (
        _safe_enum(PMaxAssetGroupStatus, raw_status)
        if raw_status is not None
        else PMaxAssetGroupStatus.UNKNOWN
    )

    primary_status_obs = extract_observed(
        row,
        "asset_group.primary_status",
        lambda v: _safe_enum(PMaxAssetGroupPrimaryStatus, v),
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    _, raw_reasons = _extract_path(row, "asset_group.primary_status_reasons")
    primary_reasons: tuple[str, ...] = ()
    if isinstance(raw_reasons, list):
        primary_reasons = tuple(str(r) for r in raw_reasons)

    ad_strength_obs = extract_observed(
        row,
        "asset_group.ad_strength",
        lambda v: _safe_enum(PMaxAdStrength, v),
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )
    asset_coverage_obs = extract_observed(
        row,
        "asset_group.asset_coverage",
        lambda v: v if isinstance(v, dict) else {"raw": v},
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    _, raw_furls = _extract_path(row, "asset_group.final_urls")
    final_urls: tuple[str, ...] = tuple(str(u) for u in raw_furls) if isinstance(raw_furls, list) else ()

    _, raw_mfurls = _extract_path(row, "asset_group.final_mobile_urls")
    final_mobile_urls: tuple[str, ...] = (
        tuple(str(u) for u in raw_mfurls) if isinstance(raw_mfurls, list) else ()
    )

    path1_obs = extract_observed(
        row,
        "asset_group.path1",
        _safe_str,
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    path2_obs = extract_observed(
        row,
        "asset_group.path2",
        _safe_str,
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    return PMaxAssetGroupDTO(
        resource_name=resource_name,
        id=ag_id,
        campaign_id=campaign_id,
        name=name,
        status=status,
        primary_status=primary_status_obs,
        primary_status_reasons=primary_reasons,
        ad_strength=ad_strength_obs,
        asset_coverage=asset_coverage_obs,
        final_urls=final_urls,
        final_mobile_urls=final_mobile_urls,
        path1=path1_obs,
        path2=path2_obs,
        assets=assets,
        signals=signals,
    )


def project_campaign_metrics(
    row: dict[str, Any],
    collected_at: Optional[datetime] = None,
    stale_threshold_seconds: Optional[int] = None,
) -> PMaxCampaignMetricsDTO:
    """Projeta métricas de campanha com preservação de zero vs ausência."""
    return PMaxCampaignMetricsDTO(
        impressions=extract_observed(
            row,
            "metrics.impressions",
            _safe_int,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        ),
        clicks=extract_observed(
            row,
            "metrics.clicks",
            _safe_int,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        ),
        cost_micros=extract_observed(
            row,
            "metrics.cost_micros",
            _safe_int,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        ),
        conversions=extract_observed(
            row,
            "metrics.conversions",
            _safe_float,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        ),
        conversions_value=extract_observed(
            row,
            "metrics.conversions_value",
            _safe_float,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        ),
        ctr=extract_observed(
            row,
            "metrics.ctr",
            _safe_float,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        ),
        average_cpc=extract_observed(
            row,
            "metrics.average_cpc",
            _safe_float,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        ),
    )


def project_campaign_row(
    row: dict[str, Any],
    asset_groups: tuple[PMaxAssetGroupDTO, ...] = (),
    campaign_assets: tuple[PMaxCampaignAssetDTO, ...] = (),
    collected_at: Optional[datetime] = None,
    stale_threshold_seconds: Optional[int] = None,
) -> PMaxCampaignDTO:
    """Projeta uma linha de campanha PMax."""
    exists_id, raw_id = _extract_path(row, "campaign.id")
    exists_rn, raw_rn = _extract_path(row, "campaign.resource_name")

    if exists_id and raw_id:
        campaign_id = str(raw_id)
        resource_name = (
            str(raw_rn)
            if exists_rn and raw_rn
            else None
        )
        if resource_name is None:
            raise ValueError("Campaign row has id but no real 'campaign.resource_name'")
    elif exists_rn and raw_rn:
        resource_name = str(raw_rn)
        campaign_id = extract_resource_id(resource_name)
    else:
        raise ValueError("Campaign row missing both 'campaign.id' and 'campaign.resource_name'")

    _, raw_name = _extract_path(row, "campaign.name")
    name = str(raw_name) if raw_name is not None else ""

    _, raw_status = _extract_path(row, "campaign.status")
    status = (
        _safe_enum(PMaxCampaignStatus, raw_status)
        if raw_status is not None
        else PMaxCampaignStatus.UNKNOWN
    )

    serving_status_obs = extract_observed(
        row,
        "campaign.serving_status",
        lambda v: _safe_enum(PMaxCampaignServingStatus, v),
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    _, raw_channel = _extract_path(row, "campaign.advertising_channel_type")
    advertising_channel_type = str(raw_channel) if raw_channel is not None else "PERFORMANCE_MAX"

    budget_obs = extract_observed(
        row,
        "campaign_budget.amount_micros",
        _safe_int,
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    bidding_type_obs = extract_observed(
        row,
        "campaign.bidding_strategy_type",
        lambda v: _safe_enum(PMaxBiddingStrategyType, v),
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    target_cpa_obs = extract_observed(
        row,
        "campaign.maximize_conversions.target_cpa_micros",
        _safe_int,
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    target_roas_obs = extract_observed(
        row,
        "campaign.maximize_conversion_value.target_roas",
        _safe_float,
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    brand_guidelines_obs = extract_observed(
        row,
        "campaign.brand_guidelines_enabled",
        _safe_bool,
        collected_at=collected_at,
        stale_threshold_seconds=stale_threshold_seconds,
    )

    # Métricas são projetadas se houver qualquer campo metrics no row
    has_metrics = any(
        k.startswith("metrics.") or (k == "metrics" and isinstance(v, dict))
        for k, v in row.items()
    )
    metrics_dto = (
        project_campaign_metrics(
            row,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        )
        if has_metrics
        else None
    )

    obs_timestamp = collected_at or datetime.now(timezone.utc)

    return PMaxCampaignDTO(
        resource_name=resource_name,
        id=campaign_id,
        name=name,
        status=status,
        serving_status=serving_status_obs,
        advertising_channel_type=advertising_channel_type,
        budget_amount_micros=budget_obs,
        bidding_strategy_type=bidding_type_obs,
        target_cpa_micros=target_cpa_obs,
        target_roas=target_roas_obs,
        brand_guidelines_enabled=brand_guidelines_obs,
        campaign_assets=campaign_assets,
        asset_groups=asset_groups,
        metrics=metrics_dto,
        observed_at=obs_timestamp,
    )


def assemble_pmax_bundle(
    campaign_rows: list[dict[str, Any]],
    asset_group_rows: list[dict[str, Any]],
    asset_group_asset_rows: list[dict[str, Any]],
    asset_rows: list[dict[str, Any]],
    signal_rows: list[dict[str, Any]],
    campaign_asset_rows: Optional[list[dict[str, Any]]] = None,
    collected_at: Optional[datetime] = None,
    stale_threshold_seconds: Optional[int] = None,
) -> list[PMaxCampaignDTO]:
    """Agrega e projeta todas as entidades de um snapshot em DTOs PMax hierárquicos."""
    # 1. Indexar assets por ID e resource_name
    asset_map: dict[str, PMaxAssetDTO] = {}
    for a_row in asset_rows:
        asset_dto = project_asset_row(
            a_row,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        )
        asset_map[asset_dto.id] = asset_dto
        asset_map[asset_dto.resource_name] = asset_dto

    campaign_asset_map: dict[str, list[PMaxCampaignAssetDTO]] = {}
    for campaign_asset_row in campaign_asset_rows or []:
        campaign_asset = project_campaign_asset_row(
            campaign_asset_row,
            asset_lookup=asset_map,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        )
        campaign_asset_map.setdefault(campaign_asset.campaign_id, []).append(campaign_asset)

    # 2. Indexar asset group assets por asset_group_id
    aga_map: dict[str, list[PMaxAssetGroupAssetDTO]] = {}
    for aga_row in asset_group_asset_rows:
        aga_dto = project_asset_group_asset_row(
            aga_row,
            asset_lookup=asset_map,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        )
        aga_map.setdefault(aga_dto.asset_group_id, []).append(aga_dto)

    # 3. Indexar signals por asset_group_id
    signal_map: dict[str, list[PMaxAssetGroupSignalDTO]] = {}
    for sig_row in signal_rows:
        sig_dto = project_asset_group_signal_row(
            sig_row,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        )
        signal_map.setdefault(sig_dto.asset_group_id, []).append(sig_dto)

    # 4. Indexar asset groups por campaign_id
    ag_by_campaign: dict[str, list[PMaxAssetGroupDTO]] = {}
    for ag_row in asset_group_rows:
        # Extrair temporariamente o ID do asset group
        exists_id, raw_id = _extract_path(ag_row, "asset_group.id")
        exists_rn, raw_rn = _extract_path(ag_row, "asset_group.resource_name")
        ag_id = (
            str(raw_id)
            if exists_id and raw_id
            else extract_resource_id(str(raw_rn))
        )

        ag_assets = tuple(aga_map.get(ag_id, []))
        ag_signals = tuple(signal_map.get(ag_id, []))

        ag_dto = project_asset_group_row(
            ag_row,
            assets=ag_assets,
            signals=ag_signals,
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        )
        ag_by_campaign.setdefault(ag_dto.campaign_id, []).append(ag_dto)

    # 5. Projetar campanhas completas
    campaigns: list[PMaxCampaignDTO] = []
    for c_row in campaign_rows:
        exists_id, raw_id = _extract_path(c_row, "campaign.id")
        exists_rn, raw_rn = _extract_path(c_row, "campaign.resource_name")
        cid = (
            str(raw_id)
            if exists_id and raw_id
            else extract_resource_id(str(raw_rn))
        )

        matched_ags = tuple(ag_by_campaign.get(cid, []))
        camp_dto = project_campaign_row(
            c_row,
            asset_groups=matched_ags,
            campaign_assets=tuple(campaign_asset_map.get(cid, [])),
            collected_at=collected_at,
            stale_threshold_seconds=stale_threshold_seconds,
        )
        campaigns.append(camp_dto)

    return campaigns
