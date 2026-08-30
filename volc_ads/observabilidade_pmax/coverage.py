"""Módulo de diagnóstico estrutural e cobertura observável de assets para PMax.

Baseado nas especificações estruturais públicas da Google Ads API v25.
Fornece diagnóstico puramente observacional e descritivo das contagens e estados de assets,
sem inventar métricas, sem afirmar paridade de recomendação oficial e sem capacidade de mutação.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping, Optional

from volc_ads.observabilidade_pmax.types import (
    ObservedValue,
    PMaxAdStrength,
    PMaxAssetDTO,
    PMaxAssetFieldType,
    PMaxAssetGroupAssetDTO,
    PMaxAssetGroupDTO,
    PMaxAssetGroupPrimaryStatus,
    PMaxAssetGroupStatus,
    PMaxAssetPolicyApprovalStatus,
    PMaxCampaignDTO,
    PMaxCampaignServingStatus,
    PMaxCampaignStatus,
    PMaxCampaignAssetDTO,
)

OBSERVABILITY_DISCLAIMER = (
    "Diagnóstico observacional puramente descritivo e estrutural baseado na "
    "documentação pública da Google Ads API v25. Não constitui recomendação oficial "
    "do Google Ads, garantia de veiculação ou autorização para mutação/criação."
)


@dataclass(frozen=True)
class AssetFieldRequirement:
    """Requisito estrutural de contagem para um tipo de campo de asset no PMax."""

    field_type: PMaxAssetFieldType
    min_count: int
    max_count: int
    is_mandatory: bool
    description: str


# Regras estruturais documentadas da Google Ads API v25 para PMax Asset Groups
PMAX_FIELD_REQUIREMENTS: Mapping[PMaxAssetFieldType, AssetFieldRequirement] = {
    PMaxAssetFieldType.HEADLINE: AssetFieldRequirement(
        field_type=PMaxAssetFieldType.HEADLINE,
        min_count=3,
        max_count=15,
        is_mandatory=True,
        description="Títulos curtos (3 a 15)",
    ),
    PMaxAssetFieldType.LONG_HEADLINE: AssetFieldRequirement(
        field_type=PMaxAssetFieldType.LONG_HEADLINE,
        min_count=1,
        max_count=5,
        is_mandatory=True,
        description="Títulos longos (1 a 5)",
    ),
    PMaxAssetFieldType.DESCRIPTION: AssetFieldRequirement(
        field_type=PMaxAssetFieldType.DESCRIPTION,
        min_count=2,
        max_count=5,
        is_mandatory=True,
        description="Descrições (2 a 5)",
    ),
    PMaxAssetFieldType.BUSINESS_NAME: AssetFieldRequirement(
        field_type=PMaxAssetFieldType.BUSINESS_NAME,
        min_count=1,
        max_count=1,
        is_mandatory=True,
        description="Nome da empresa (exatamente 1)",
    ),
    PMaxAssetFieldType.MARKETING_IMAGE: AssetFieldRequirement(
        field_type=PMaxAssetFieldType.MARKETING_IMAGE,
        min_count=1,
        max_count=20,
        is_mandatory=True,
        description="Imagens retangulares horizontais 1.91:1 (1 a 20)",
    ),
    PMaxAssetFieldType.SQUARE_MARKETING_IMAGE: AssetFieldRequirement(
        field_type=PMaxAssetFieldType.SQUARE_MARKETING_IMAGE,
        min_count=1,
        max_count=20,
        is_mandatory=True,
        description="Imagens quadradas 1:1 (1 a 20)",
    ),
    PMaxAssetFieldType.PORTRAIT_MARKETING_IMAGE: AssetFieldRequirement(
        field_type=PMaxAssetFieldType.PORTRAIT_MARKETING_IMAGE,
        min_count=0,
        max_count=20,
        is_mandatory=False,
        description="Imagens verticais 4:5 (opcional, até 20)",
    ),
    PMaxAssetFieldType.LOGO: AssetFieldRequirement(
        field_type=PMaxAssetFieldType.LOGO,
        min_count=1,
        max_count=5,
        is_mandatory=True,
        description="Logotipos quadrados 1:1 (1 a 5)",
    ),
    PMaxAssetFieldType.LANDSCAPE_LOGO: AssetFieldRequirement(
        field_type=PMaxAssetFieldType.LANDSCAPE_LOGO,
        min_count=0,
        max_count=20,
        is_mandatory=False,
        description="Logotipos retangulares 4:1 (opcional, até 20)",
    ),
    PMaxAssetFieldType.CALL_TO_ACTION_SELECTION: AssetFieldRequirement(
        field_type=PMaxAssetFieldType.CALL_TO_ACTION_SELECTION,
        min_count=0,
        max_count=1,
        is_mandatory=False,
        description="Call to action selection (opcional, até 1)",
    ),
    PMaxAssetFieldType.YOUTUBE_VIDEO: AssetFieldRequirement(
        field_type=PMaxAssetFieldType.YOUTUBE_VIDEO,
        min_count=0,
        max_count=15,
        is_mandatory=False,
        description="Vídeos do YouTube (opcional/recomendado, até 15)",
    ),
    PMaxAssetFieldType.MEDIA_BUNDLE: AssetFieldRequirement(
        field_type=PMaxAssetFieldType.MEDIA_BUNDLE,
        min_count=0,
        max_count=1,
        is_mandatory=False,
        description="HTML5 media bundle (opcional, até 1)",
    ),
}


class CoverageVerdict(str, Enum):
    COMPLETE = "COMPLETE"
    GAPS = "GAPS"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class AssetFieldCoverageStatus:
    """Diagnóstico observável de cobertura para um tipo específico de asset."""

    field_type: PMaxAssetFieldType
    actual_count: int
    min_required: int
    max_allowed: int
    is_mandatory: bool
    is_min_satisfied: bool
    is_max_exceeded: bool
    primary_status_counts: Mapping[str, int]
    policy_approval_counts: Mapping[str, int]
    evidence_complete: bool
    observations: tuple[str, ...]


@dataclass(frozen=True)
class PMaxAssetGroupCoverageReport:
    """Relatório estrutural de observabilidade para um Asset Group."""

    asset_group_id: str
    asset_group_name: str
    status: str
    ad_strength: ObservedValue[PMaxAdStrength]
    total_assets: int
    field_coverages: tuple[AssetFieldCoverageStatus, ...]
    verdict: CoverageVerdict
    is_structurally_complete: Optional[bool]
    structural_gaps: tuple[str, ...]
    warnings: tuple[str, ...]
    signals_count: int
    disclaimer: str = OBSERVABILITY_DISCLAIMER


@dataclass(frozen=True)
class PMaxCampaignCoverageReport:
    """Relatório estrutural agregado de observabilidade para uma campanha PMax."""

    campaign_id: str
    campaign_name: str
    campaign_status: PMaxCampaignStatus
    serving_status: ObservedValue[PMaxCampaignServingStatus]
    total_asset_groups: int
    historical_asset_groups: int
    eligible_asset_groups: Optional[int]
    asset_group_reports: tuple[PMaxAssetGroupCoverageReport, ...]
    verdict: CoverageVerdict
    all_asset_groups_complete: Optional[bool]
    summary_observations: tuple[str, ...]
    evaluated_at: datetime
    disclaimer: str = OBSERVABILITY_DISCLAIMER


def evaluate_asset_field_coverage(
    field_type: PMaxAssetFieldType,
    assets: tuple[PMaxAssetGroupAssetDTO, ...],
) -> AssetFieldCoverageStatus:
    """Avalia a cobertura e distribuição de um tipo específico de asset."""
    req = PMAX_FIELD_REQUIREMENTS.get(
        field_type,
        AssetFieldRequirement(
            field_type=field_type,
            min_count=0,
            max_count=999,
            is_mandatory=False,
            description="Tipo de campo sem regra específica",
        ),
    )

    matching_assets = [
        a for a in assets
        if a.field_type == field_type and a.status.upper() == "ENABLED"
    ]
    actual_count = len(matching_assets)

    primary_counts: dict[str, int] = {}
    policy_counts: dict[str, int] = {}
    obs_list: list[str] = []

    for a in matching_assets:
        if a.primary_status.is_present and a.primary_status.value is not None:
            pl_key = str(a.primary_status.value)
        else:
            pl_key = str(a.primary_status.state.value)
        primary_counts[pl_key] = primary_counts.get(pl_key, 0) + 1

        # Policy approval status
        if a.policy_approval_status.is_present and a.policy_approval_status.value is not None:
            pol_key = str(a.policy_approval_status.value.value)
        else:
            pol_key = str(a.policy_approval_status.state.value)
        policy_counts[pol_key] = policy_counts.get(pol_key, 0) + 1

    is_min_satisfied = actual_count >= req.min_count
    is_max_exceeded = actual_count > req.max_count

    if req.is_mandatory and actual_count < req.min_count:
        obs_list.append(
            f"Mandatory requirement not met: expected at least {req.min_count}, found {actual_count}."
        )
    elif not req.is_mandatory and actual_count < req.min_count:
        obs_list.append(
            f"Optional minimum not met: expected {req.min_count}, found {actual_count}."
        )

    if is_max_exceeded:
        obs_list.append(
            f"Maximum exceeded: limit is {req.max_count}, found {actual_count}."
        )

    if policy_counts.get(PMaxAssetPolicyApprovalStatus.DISAPPROVED.value, 0) > 0:
        disapproved_num = policy_counts[PMaxAssetPolicyApprovalStatus.DISAPPROVED.value]
        obs_list.append(f"{disapproved_num} asset(s) marked as DISAPPROVED by policy.")

    evidence_complete = True
    if field_type == PMaxAssetFieldType.DESCRIPTION and actual_count >= req.min_count:
        texts = []
        for link in matching_assets:
            if link.asset_details is None or not link.asset_details.text_content.is_present:
                evidence_complete = False
                continue
            texts.append(link.asset_details.text_content.value or "")
        if evidence_complete and not any(len(text) <= 60 for text in texts):
            obs_list.append("At least one DESCRIPTION must have 60 characters or fewer.")
        elif not evidence_complete:
            obs_list.append("Description text was not collected; <=60 character rule is indeterminate.")

    return AssetFieldCoverageStatus(
        field_type=field_type,
        actual_count=actual_count,
        min_required=req.min_count,
        max_allowed=req.max_count,
        is_mandatory=req.is_mandatory,
        is_min_satisfied=is_min_satisfied,
        is_max_exceeded=is_max_exceeded,
        primary_status_counts=primary_counts,
        policy_approval_counts=policy_counts,
        evidence_complete=evidence_complete,
        observations=tuple(obs_list),
    )


def evaluate_asset_group_coverage(
    asset_group: PMaxAssetGroupDTO,
    brand_guidelines_enabled: Optional[bool] = None,
) -> PMaxAssetGroupCoverageReport:
    """Gera diagnóstico estrutural detalhado de um Asset Group."""
    field_coverages: list[AssetFieldCoverageStatus] = []
    structural_gaps: list[str] = []
    warnings: list[str] = []

    # Avaliar todos os tipos de campos padronizados
    if brand_guidelines_enabled is None:
        warnings.append("Brand Guidelines state is absent; branding coverage is indeterminate.")

    field_types = tuple(
        ft for ft in PMAX_FIELD_REQUIREMENTS
        if not (brand_guidelines_enabled is True and ft in (PMaxAssetFieldType.BUSINESS_NAME, PMaxAssetFieldType.LOGO))
    )
    evidence_complete = brand_guidelines_enabled is not None
    for field_type in field_types:
        cov = evaluate_asset_field_coverage(field_type, asset_group.assets)
        field_coverages.append(cov)

        if cov.is_mandatory and not cov.is_min_satisfied:
            structural_gaps.append(
                f"Field '{field_type.value}' has {cov.actual_count} items (minimum required: {cov.min_required})."
            )
        if cov.is_max_exceeded:
            structural_gaps.append(
                f"Field '{field_type.value}' has {cov.actual_count} items (maximum allowed: {cov.max_allowed})."
            )
        if field_type == PMaxAssetFieldType.DESCRIPTION and any(
            "60 characters or fewer" in observation for observation in cov.observations
        ):
            structural_gaps.append("DESCRIPTION requires at least one text with 60 characters or fewer.")
        if not cov.evidence_complete:
            evidence_complete = False

    # Identificar se há assets com tipos desconhecidos ou não mapeados
    mapped_types = set(PMAX_FIELD_REQUIREMENTS.keys())
    for a in asset_group.assets:
        if a.field_type not in mapped_types and a.field_type != PMaxAssetFieldType.UNSPECIFIED:
            warnings.append(
                f"Asset {a.asset_id} has unmapped field type '{a.field_type.value}'."
            )

    # Verificar ausência de URLs finais
    if not asset_group.final_urls:
        structural_gaps.append("Asset group has no final_urls defined.")

    # Verificar Ad Strength
    if asset_group.ad_strength.is_present and asset_group.ad_strength.value == PMaxAdStrength.POOR:
        warnings.append("Ad strength observed as POOR.")

    if not evidence_complete:
        verdict = CoverageVerdict.INDETERMINATE
        is_complete: Optional[bool] = None
    elif structural_gaps:
        verdict = CoverageVerdict.GAPS
        is_complete = False
    else:
        verdict = CoverageVerdict.COMPLETE
        is_complete = True

    return PMaxAssetGroupCoverageReport(
        asset_group_id=asset_group.id,
        asset_group_name=asset_group.name,
        status=asset_group.status.value,
        ad_strength=asset_group.ad_strength,
        total_assets=sum(1 for a in asset_group.assets if a.status.upper() == "ENABLED"),
        field_coverages=tuple(field_coverages),
        verdict=verdict,
        is_structurally_complete=is_complete,
        structural_gaps=tuple(structural_gaps),
        warnings=tuple(warnings),
        signals_count=len(asset_group.signals),
    )


def evaluate_campaign_coverage(
    campaign: PMaxCampaignDTO,
    evaluated_at: Optional[datetime] = None,
) -> PMaxCampaignCoverageReport:
    """Gera diagnóstico estrutural consolidado de uma campanha PMax."""
    eval_ts = evaluated_at or datetime.now(timezone.utc)
    ag_reports: list[PMaxAssetGroupCoverageReport] = []
    summary_obs: list[str] = []

    operational_groups = tuple(ag for ag in campaign.asset_groups if ag.status != PMaxAssetGroupStatus.REMOVED)
    historical_count = len(campaign.asset_groups) - len(operational_groups)
    brand_state = campaign.brand_guidelines_enabled
    brand_enabled = brand_state.value if brand_state.is_present else None
    eligible_count = 0
    eligibility_complete = True
    for ag in operational_groups:
        rep = evaluate_asset_group_coverage(ag, brand_guidelines_enabled=brand_enabled)
        ag_reports.append(rep)
        if not ag.primary_status.is_present:
            eligibility_complete = False
        elif ag.primary_status.value == PMaxAssetGroupPrimaryStatus.ELIGIBLE:
            eligible_count += 1

    total_ags = len(operational_groups)
    if total_ags == 0:
        summary_obs.append("Campaign has no asset groups associated.")

    incomplete_ags = [r for r in ag_reports if r.verdict == CoverageVerdict.GAPS]
    indeterminate_ags = [r for r in ag_reports if r.verdict == CoverageVerdict.INDETERMINATE]
    if incomplete_ags:
        summary_obs.append(
            f"{len(incomplete_ags)} of {total_ags} asset group(s) have structural gaps."
        )

    brand_gaps: list[str] = []
    if brand_enabled is True:
        active_campaign_assets = [a for a in campaign.campaign_assets if a.status.upper() == "ENABLED"]
        for field_type, minimum in ((PMaxAssetFieldType.BUSINESS_NAME, 1), (PMaxAssetFieldType.LOGO, 1)):
            count = sum(1 for a in active_campaign_assets if a.field_type == field_type)
            if count < minimum:
                brand_gaps.append(f"CampaignAsset '{field_type.value}' has {count} items (minimum required: {minimum}).")
        summary_obs.extend(brand_gaps)

    if brand_enabled is None or indeterminate_ags or not eligibility_complete:
        verdict = CoverageVerdict.INDETERMINATE
        all_complete: Optional[bool] = None
    elif total_ags == 0 or incomplete_ags or brand_gaps:
        verdict = CoverageVerdict.GAPS
        all_complete = False
    else:
        verdict = CoverageVerdict.COMPLETE
        all_complete = True

    return PMaxCampaignCoverageReport(
        campaign_id=campaign.id,
        campaign_name=campaign.name,
        campaign_status=campaign.status,
        serving_status=campaign.serving_status,
        total_asset_groups=total_ags,
        historical_asset_groups=historical_count,
        eligible_asset_groups=eligible_count if eligibility_complete else None,
        asset_group_reports=tuple(ag_reports),
        verdict=verdict,
        all_asset_groups_complete=all_complete,
        summary_observations=tuple(summary_obs),
        evaluated_at=eval_ts,
    )
