"""Núcleo isolado e estritamente read-only para observabilidade de Performance Max (PMax).

Orquestra montagem de consultas GAQL v25, projeção determinística de payloads brutos
e diagnósticos estruturais de integridade de assets, sem autorizar criação ou efetuar mutação.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from volc_ads.observabilidade_pmax.coverage import (
    OBSERVABILITY_DISCLAIMER,
    PMaxAssetGroupCoverageReport,
    PMaxCampaignCoverageReport,
    evaluate_asset_group_coverage,
    evaluate_campaign_coverage,
)
from volc_ads.observabilidade_pmax.projector import (
    assemble_pmax_bundle,
    project_asset_group_asset_row,
    project_asset_group_row,
    project_asset_row,
    project_campaign_row,
)
from volc_ads.observabilidade_pmax.queries import (
    build_pmax_asset_group_assets_query,
    build_pmax_asset_group_signals_query,
    build_pmax_asset_groups_query,
    build_pmax_assets_query,
    build_pmax_campaigns_query,
    build_pmax_observability_bundle_queries,
)
from volc_ads.observabilidade_pmax.types import (
    CollectionEnvelope,
    CollectionState,
    PMaxAssetDTO,
    PMaxAssetGroupAssetDTO,
    PMaxAssetGroupDTO,
    PMaxCampaignDTO,
    PMaxDiagnosisOutcome,
    PMaxRawSnapshot,
)


class PMaxObservabilityKernel:
    """Kernel de observabilidade read-only para Performance Max.

    Este componente:
    1. Gera consultas GAQL v25 puramente de leitura.
    2. Projeta dados brutos de amostragem em DTOs tipados e imutáveis.
    3. Analisa cobertura e diagnóstico estrutural sem efeitos colaterais.
    4. Proíbe qualquer mutação, validate_only ou escrita.
    """

    def __init__(self, stale_threshold_seconds: Optional[int] = 3600) -> None:
        self._stale_threshold_seconds = stale_threshold_seconds

    @property
    def disclaimer(self) -> str:
        """Aviso de isenção de paridade oficial e declaração de read-only."""
        return OBSERVABILITY_DISCLAIMER

    def get_bundle_queries(
        self, customer_id: str, campaign_id: Optional[str] = None
    ) -> dict[str, str]:
        """Gera o conjunto completo de queries GAQL para inspeção de PMax."""
        return build_pmax_observability_bundle_queries(
            customer_id=customer_id, campaign_id=campaign_id
        )

    def get_campaigns_query(
        self,
        campaign_ids: Optional[Sequence[str]] = None,
        status_filter: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
    ) -> str:
        """Gera query GAQL de campanhas PMax."""
        return build_pmax_campaigns_query(
            campaign_ids=campaign_ids,
            status_filter=status_filter,
            limit=limit,
        )

    def get_asset_groups_query(
        self,
        campaign_ids: Optional[Sequence[str]] = None,
        asset_group_ids: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
    ) -> str:
        """Gera query GAQL de Asset Groups."""
        return build_pmax_asset_groups_query(
            campaign_ids=campaign_ids,
            asset_group_ids=asset_group_ids,
            limit=limit,
        )

    def get_asset_group_assets_query(
        self,
        customer_id: str,
        campaign_ids: Optional[Sequence[str]] = None,
        asset_group_ids: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
    ) -> str:
        """Gera query GAQL de vínculos AssetGroupAsset."""
        return build_pmax_asset_group_assets_query(
            customer_id=customer_id,
            campaign_ids=campaign_ids,
            asset_group_ids=asset_group_ids,
            limit=limit,
        )

    def get_assets_query(
        self,
        asset_ids: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
    ) -> str:
        """Gera query GAQL de detalhes de Assets."""
        return build_pmax_assets_query(
            asset_ids=asset_ids,
            limit=limit,
        )

    def get_signals_query(
        self,
        customer_id: str,
        asset_group_ids: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
    ) -> str:
        """Gera query GAQL de sinais de Asset Group."""
        return build_pmax_asset_group_signals_query(
            customer_id=customer_id,
            asset_group_ids=asset_group_ids,
            limit=limit,
        )

    def project_raw_bundle(
        self,
        snapshot: PMaxRawSnapshot,
        collected_at: Optional[datetime] = None,
    ) -> CollectionEnvelope[PMaxCampaignDTO]:
        """Projeta somente snapshot completo; coleta ausente/falha/stale bloqueia."""
        blocked = snapshot.blocking_state
        if blocked is not None:
            blocked_sources = tuple(
                envelope.source
                for envelope in (
                    snapshot.campaign_rows,
                    snapshot.asset_group_rows,
                    snapshot.asset_group_asset_rows,
                    snapshot.asset_rows,
                    snapshot.signal_rows,
                    snapshot.campaign_asset_rows,
                )
                if not envelope.can_diagnose
            )
            return CollectionEnvelope(
                items=(),
                state=blocked,
                source=",".join(blocked_sources),
                collected_at=collected_at,
                error_message="Diagnóstico bloqueado: snapshot incompleto ou não atual.",
            )
        try:
            campaigns = assemble_pmax_bundle(
                campaign_rows=list(snapshot.campaign_rows.items),
                asset_group_rows=list(snapshot.asset_group_rows.items),
                asset_group_asset_rows=list(snapshot.asset_group_asset_rows.items),
                asset_rows=list(snapshot.asset_rows.items),
                signal_rows=list(snapshot.signal_rows.items),
                campaign_asset_rows=list(snapshot.campaign_asset_rows.items),
                collected_at=collected_at,
                stale_threshold_seconds=self._stale_threshold_seconds,
            )
        except (TypeError, ValueError, KeyError) as exc:
            return CollectionEnvelope(
                items=(),
                state=CollectionState.COLLECTION_FAILED,
                source="pmax_projection",
                collected_at=collected_at,
                error_message=f"Projection failed closed ({type(exc).__name__}).",
            )
        return CollectionEnvelope.measured(campaigns, source="pmax_projection", collected_at=collected_at)

    def diagnose_campaign(
        self,
        campaign: PMaxCampaignDTO,
        evaluated_at: Optional[datetime] = None,
    ) -> PMaxCampaignCoverageReport:
        """Realiza diagnóstico estrutural de cobertura e integridade de uma campanha PMax."""
        return evaluate_campaign_coverage(campaign, evaluated_at=evaluated_at)

    def diagnose_asset_group(
        self,
        asset_group: PMaxAssetGroupDTO,
    ) -> PMaxAssetGroupCoverageReport:
        """Realiza diagnóstico estrutural de cobertura de um Asset Group isolado."""
        return evaluate_asset_group_coverage(asset_group)

    def inspect_and_diagnose(
        self,
        snapshot: PMaxRawSnapshot,
        collected_at: Optional[datetime] = None,
    ) -> PMaxDiagnosisOutcome:
        """Fluxo fail-closed: nunca transforma falha, stale ou não coletado em gap."""
        campaigns = self.project_raw_bundle(snapshot=snapshot, collected_at=collected_at)
        if not campaigns.can_diagnose:
            return PMaxDiagnosisOutcome(
                state=campaigns.state,
                results=(),
                blocked_sources=tuple(filter(None, campaigns.source.split(","))),
            )
        results = []
        for camp in campaigns.items:
            report = self.diagnose_campaign(camp, evaluated_at=collected_at)
            results.append((camp, report))
        return PMaxDiagnosisOutcome(state=campaigns.state, results=tuple(results))
