"""Tipos, enums e DTOs imutáveis para observabilidade read-only do Performance Max (PMax).

Compatível com a especificação da Google Ads API v25.
Garante preservação estrita de semântica de ausência: ausência nunca é tratada como zero,
e zero medido nunca é tratado como ausência.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, Mapping, Optional, TypeVar

T = TypeVar("T")


class ObservationState(str, Enum):
    """Estado epistêmico de um campo observado."""

    PRESENT = "PRESENT"
    MEASURED_ZERO = "MEASURED_ZERO"
    FIELD_ABSENT = "FIELD_ABSENT"
    NOT_COLLECTED = "NOT_COLLECTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    COLLECTION_FAILED = "COLLECTION_FAILED"
    STALE = "STALE"


class CollectionState(str, Enum):
    """Estado de uma coleção GAQL; vazio medido não é coleta ausente."""

    PRESENT = "PRESENT"
    PRESENT_EMPTY = "PRESENT_EMPTY"
    NOT_COLLECTED = "NOT_COLLECTED"
    COLLECTION_FAILED = "COLLECTION_FAILED"
    STALE = "STALE"


@dataclass(frozen=True)
class CollectionEnvelope(Generic[T]):
    """Coleção observada com procedência e estado epistêmico obrigatório."""

    items: tuple[T, ...]
    state: CollectionState
    source: str
    collected_at: Optional[datetime] = None
    error_message: Optional[str] = None

    @property
    def can_diagnose(self) -> bool:
        return self.state in (CollectionState.PRESENT, CollectionState.PRESENT_EMPTY)

    @classmethod
    def measured(
        cls,
        items: tuple[T, ...] | list[T],
        source: str,
        collected_at: Optional[datetime] = None,
    ) -> CollectionEnvelope[T]:
        frozen = tuple(items)
        return cls(
            items=frozen,
            state=CollectionState.PRESENT if frozen else CollectionState.PRESENT_EMPTY,
            source=source,
            collected_at=collected_at,
        )

    @classmethod
    def not_collected(cls, source: str) -> CollectionEnvelope[T]:
        return cls((), CollectionState.NOT_COLLECTED, source)

    @classmethod
    def failed(cls, source: str, error_message: str) -> CollectionEnvelope[T]:
        return cls((), CollectionState.COLLECTION_FAILED, source, error_message=error_message)

    @classmethod
    def stale(
        cls,
        items: tuple[T, ...] | list[T],
        source: str,
        collected_at: Optional[datetime] = None,
    ) -> CollectionEnvelope[T]:
        return cls(tuple(items), CollectionState.STALE, source, collected_at=collected_at)


@dataclass(frozen=True)
class ObservedValue(Generic[T]):
    """Container imutável para valores observados com rastreabilidade de estado.

    Impede a coerção acidental de None para 0 ou vice-versa.
    """

    value: Optional[T]
    state: ObservationState
    source_path: Optional[str] = None
    collected_at: Optional[datetime] = None
    error_message: Optional[str] = None

    @property
    def is_present(self) -> bool:
        """Verifica se há um valor válido presente (incluindo zero medido)."""
        return self.state in (ObservationState.PRESENT, ObservationState.MEASURED_ZERO)

    @property
    def is_zero(self) -> bool:
        """Verifica se é explicitamente um zero medido."""
        return self.state == ObservationState.MEASURED_ZERO

    @property
    def is_absent(self) -> bool:
        """Verifica se o dado está ausente por qualquer motivo."""
        return self.state in (
            ObservationState.FIELD_ABSENT,
            ObservationState.NOT_COLLECTED,
            ObservationState.NOT_APPLICABLE,
        )

    def unwrap_or(self, default: T) -> T:
        """Retorna o valor se presente/medido, ou default se ausente."""
        if self.value is not None:
            return self.value
        return default

    @classmethod
    def present(
        cls,
        value: T,
        source_path: Optional[str] = None,
        collected_at: Optional[datetime] = None,
    ) -> ObservedValue[T]:
        return cls(
            value=value,
            state=ObservationState.PRESENT,
            source_path=source_path,
            collected_at=collected_at,
        )

    @classmethod
    def measured_zero(
        cls,
        value: T,
        source_path: Optional[str] = None,
        collected_at: Optional[datetime] = None,
    ) -> ObservedValue[T]:
        return cls(
            value=value,
            state=ObservationState.MEASURED_ZERO,
            source_path=source_path,
            collected_at=collected_at,
        )

    @classmethod
    def field_absent(
        cls,
        source_path: Optional[str] = None,
        collected_at: Optional[datetime] = None,
    ) -> ObservedValue[T]:
        return cls(
            value=None,
            state=ObservationState.FIELD_ABSENT,
            source_path=source_path,
            collected_at=collected_at,
        )

    @classmethod
    def not_collected(
        cls,
        source_path: Optional[str] = None,
    ) -> ObservedValue[T]:
        return cls(
            value=None,
            state=ObservationState.NOT_COLLECTED,
            source_path=source_path,
        )

    @classmethod
    def not_applicable(
        cls,
        source_path: Optional[str] = None,
    ) -> ObservedValue[T]:
        return cls(
            value=None,
            state=ObservationState.NOT_APPLICABLE,
            source_path=source_path,
        )

    @classmethod
    def collection_failed(
        cls,
        error_message: str,
        source_path: Optional[str] = None,
        collected_at: Optional[datetime] = None,
    ) -> ObservedValue[T]:
        return cls(
            value=None,
            state=ObservationState.COLLECTION_FAILED,
            source_path=source_path,
            collected_at=collected_at,
            error_message=error_message,
        )

    @classmethod
    def stale(
        cls,
        value: Optional[T],
        source_path: Optional[str] = None,
        collected_at: Optional[datetime] = None,
    ) -> ObservedValue[T]:
        return cls(
            value=value,
            state=ObservationState.STALE,
            source_path=source_path,
            collected_at=collected_at,
        )


class PMaxAssetFieldType(str, Enum):
    """Tipos de campos de assets no Performance Max conforme Google Ads API v25."""

    UNSPECIFIED = "UNSPECIFIED"
    UNKNOWN = "UNKNOWN"
    HEADLINE = "HEADLINE"
    LONG_HEADLINE = "LONG_HEADLINE"
    DESCRIPTION = "DESCRIPTION"
    BUSINESS_NAME = "BUSINESS_NAME"
    MARKETING_IMAGE = "MARKETING_IMAGE"
    SQUARE_MARKETING_IMAGE = "SQUARE_MARKETING_IMAGE"
    PORTRAIT_MARKETING_IMAGE = "PORTRAIT_MARKETING_IMAGE"
    LOGO = "LOGO"
    LANDSCAPE_LOGO = "LANDSCAPE_LOGO"
    CALL_TO_ACTION_SELECTION = "CALL_TO_ACTION_SELECTION"
    YOUTUBE_VIDEO = "YOUTUBE_VIDEO"
    MEDIA_BUNDLE = "MEDIA_BUNDLE"


class PMaxAssetPerformanceLabel(str, Enum):
    """Performance label de um asset em um Asset Group conforme Google Ads API v25."""

    UNSPECIFIED = "UNSPECIFIED"
    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    LEARNING = "LEARNING"
    LOW = "LOW"
    GOOD = "GOOD"
    BEST = "BEST"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PMaxAdStrength(str, Enum):
    """Força do anúncio (Ad Strength) do Asset Group conforme Google Ads API v25."""

    UNSPECIFIED = "UNSPECIFIED"
    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    NO_ADS = "NO_ADS"
    POOR = "POOR"
    AVERAGE = "AVERAGE"
    GOOD = "GOOD"
    EXCELLENT = "EXCELLENT"


class PMaxAssetGroupStatus(str, Enum):
    """Status operacional do Asset Group."""

    UNSPECIFIED = "UNSPECIFIED"
    UNKNOWN = "UNKNOWN"
    ENABLED = "ENABLED"
    PAUSED = "PAUSED"
    REMOVED = "REMOVED"


class PMaxAssetGroupPrimaryStatus(str, Enum):
    """Primary status do Asset Group conforme Google Ads API v25."""

    UNSPECIFIED = "UNSPECIFIED"
    UNKNOWN = "UNKNOWN"
    ELIGIBLE = "ELIGIBLE"
    PAUSED = "PAUSED"
    REMOVED = "REMOVED"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    LIMITED = "LIMITED"
    PENDING = "PENDING"


class PMaxAssetGroupPrimaryStatusReason(str, Enum):
    """Razões para o Primary status do Asset Group conforme Google Ads API v25."""

    UNSPECIFIED = "UNSPECIFIED"
    UNKNOWN = "UNKNOWN"
    ASSET_GROUP_PAUSED = "ASSET_GROUP_PAUSED"
    ASSET_GROUP_REMOVED = "ASSET_GROUP_REMOVED"
    CAMPAIGN_PAUSED = "CAMPAIGN_PAUSED"
    CAMPAIGN_REMOVED = "CAMPAIGN_REMOVED"
    CAMPAIGN_ENDED = "CAMPAIGN_ENDED"
    ASSET_GROUP_LIMITED = "ASSET_GROUP_LIMITED"
    ASSET_GROUP_DISAPPROVED = "ASSET_GROUP_DISAPPROVED"
    ASSET_GROUP_UNDER_REVIEW = "ASSET_GROUP_UNDER_REVIEW"


class PMaxCampaignStatus(str, Enum):
    """Status da campanha PMax."""

    UNSPECIFIED = "UNSPECIFIED"
    UNKNOWN = "UNKNOWN"
    ENABLED = "ENABLED"
    PAUSED = "PAUSED"
    REMOVED = "REMOVED"


class PMaxCampaignServingStatus(str, Enum):
    """Status de veiculação da campanha PMax."""

    UNSPECIFIED = "UNSPECIFIED"
    UNKNOWN = "UNKNOWN"
    SERVING = "SERVING"
    NONE = "NONE"
    ENDED = "ENDED"
    PENDING = "PENDING"
    SUSPENDED = "SUSPENDED"


class PMaxBiddingStrategyType(str, Enum):
    """Estratégia de lances suportada em PMax."""

    UNSPECIFIED = "UNSPECIFIED"
    UNKNOWN = "UNKNOWN"
    MAXIMIZE_CONVERSIONS = "MAXIMIZE_CONVERSIONS"
    MAXIMIZE_CONVERSION_VALUE = "MAXIMIZE_CONVERSION_VALUE"
    TARGET_CPA = "TARGET_CPA"
    TARGET_ROAS = "TARGET_ROAS"


class PMaxAssetPolicyApprovalStatus(str, Enum):
    """Status de aprovação de política do Asset conforme Google Ads API v25."""

    UNSPECIFIED = "UNSPECIFIED"
    UNKNOWN = "UNKNOWN"
    APPROVED = "APPROVED"
    APPROVED_LIMITED = "APPROVED_LIMITED"
    DISAPPROVED = "DISAPPROVED"
    AREA_OF_INTEREST_ONLY = "AREA_OF_INTEREST_ONLY"


@dataclass(frozen=True)
class PMaxAssetDTO:
    """DTO imutável representando um recurso Asset do Google Ads."""

    resource_name: str
    id: str
    name: ObservedValue[str]
    asset_type: str
    text_content: ObservedValue[str]
    youtube_video_id: ObservedValue[str]
    youtube_video_title: ObservedValue[str]
    image_url: ObservedValue[str]
    policy_approval_status: ObservedValue[PMaxAssetPolicyApprovalStatus]
    policy_topic_entries: tuple[str, ...]
    source_payload_hash: Optional[str] = None


@dataclass(frozen=True)
class PMaxAssetGroupAssetDTO:
    """DTO imutável do vínculo AssetGroupAsset."""

    resource_name: str
    asset_group_id: str
    asset_id: str
    field_type: PMaxAssetFieldType
    status: str
    primary_status: ObservedValue[str]
    primary_status_reasons: tuple[str, ...]
    primary_status_details: tuple[Mapping[str, Any], ...]
    source: ObservedValue[str]
    policy_approval_status: ObservedValue[PMaxAssetPolicyApprovalStatus]
    policy_summary_reasons: tuple[str, ...]
    asset_details: Optional[PMaxAssetDTO] = None


@dataclass(frozen=True)
class PMaxCampaignAssetDTO:
    """Vínculo de branding no nível CampaignAsset (Brand Guidelines)."""

    resource_name: str
    campaign_id: str
    asset_id: str
    field_type: PMaxAssetFieldType
    status: str
    primary_status: ObservedValue[str]
    primary_status_reasons: tuple[str, ...]
    primary_status_details: tuple[Mapping[str, Any], ...]
    source: ObservedValue[str]
    asset_details: Optional[PMaxAssetDTO] = None


@dataclass(frozen=True)
class PMaxAssetGroupSignalDTO:
    """DTO imutável de sinais de Asset Group (Audiências / Search Themes)."""

    resource_name: str
    asset_group_id: str
    signal_type: str
    display_name: ObservedValue[str]
    signal_payload: dict[str, Any]


@dataclass(frozen=True)
class PMaxAssetGroupDTO:
    """DTO imutável representando um Asset Group do Performance Max."""

    resource_name: str
    id: str
    campaign_id: str
    name: str
    status: PMaxAssetGroupStatus
    primary_status: ObservedValue[PMaxAssetGroupPrimaryStatus]
    primary_status_reasons: tuple[str, ...]
    ad_strength: ObservedValue[PMaxAdStrength]
    asset_coverage: ObservedValue[Mapping[str, Any]]
    final_urls: tuple[str, ...]
    final_mobile_urls: tuple[str, ...]
    path1: ObservedValue[str]
    path2: ObservedValue[str]
    assets: tuple[PMaxAssetGroupAssetDTO, ...]
    signals: tuple[PMaxAssetGroupSignalDTO, ...]


@dataclass(frozen=True)
class PMaxCampaignMetricsDTO:
    """DTO imutável para métricas observadas de campanha PMax."""

    impressions: ObservedValue[int]
    clicks: ObservedValue[int]
    cost_micros: ObservedValue[int]
    conversions: ObservedValue[float]
    conversions_value: ObservedValue[float]
    ctr: ObservedValue[float]
    average_cpc: ObservedValue[float]


@dataclass(frozen=True)
class PMaxCampaignDTO:
    """DTO imutável representando uma campanha Performance Max completa."""

    resource_name: str
    id: str
    name: str
    status: PMaxCampaignStatus
    serving_status: ObservedValue[PMaxCampaignServingStatus]
    advertising_channel_type: str
    budget_amount_micros: ObservedValue[int]
    bidding_strategy_type: ObservedValue[PMaxBiddingStrategyType]
    target_cpa_micros: ObservedValue[int]
    target_roas: ObservedValue[float]
    brand_guidelines_enabled: ObservedValue[bool]
    campaign_assets: tuple[PMaxCampaignAssetDTO, ...]
    asset_groups: tuple[PMaxAssetGroupDTO, ...]
    metrics: Optional[PMaxCampaignMetricsDTO]
    observed_at: datetime


@dataclass(frozen=True)
class PMaxRawSnapshot:
    """Entrada completa do kernel; nenhuma consulta pode desaparecer como `[]`."""

    campaign_rows: CollectionEnvelope[dict[str, Any]]
    asset_group_rows: CollectionEnvelope[dict[str, Any]]
    asset_group_asset_rows: CollectionEnvelope[dict[str, Any]]
    asset_rows: CollectionEnvelope[dict[str, Any]]
    signal_rows: CollectionEnvelope[dict[str, Any]]
    campaign_asset_rows: CollectionEnvelope[dict[str, Any]]

    @property
    def blocking_state(self) -> Optional[CollectionState]:
        states = tuple(
            envelope.state
            for envelope in (
                self.campaign_rows,
                self.asset_group_rows,
                self.asset_group_asset_rows,
                self.asset_rows,
                self.signal_rows,
                self.campaign_asset_rows,
            )
            if not envelope.can_diagnose
        )
        for priority in (
            CollectionState.COLLECTION_FAILED,
            CollectionState.NOT_COLLECTED,
            CollectionState.STALE,
        ):
            if priority in states:
                return priority
        return None


@dataclass(frozen=True)
class PMaxDiagnosisOutcome:
    """Resultado fail-closed: relatórios só existem quando todas as coleções são válidas."""

    state: CollectionState
    results: tuple[tuple[PMaxCampaignDTO, Any], ...]
    blocked_sources: tuple[str, ...] = ()
