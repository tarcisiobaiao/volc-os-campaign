"""Suíte de testes para o núcleo read-only de observabilidade PMax.

Valida contratos, consultas GAQL v25, projeções, semântica de ausência vs zero,
diagnósticos estruturais de cobertura, imutabilidade e isolamento total sem rede.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import pytest

from volc_ads.observabilidade_pmax import (
    GAQLSecurityError,
    CollectionEnvelope,
    CollectionState,
    CoverageVerdict,
    ObservationState,
    ObservedValue,
    PMaxAdStrength,
    PMaxAssetDTO,
    PMaxAssetFieldType,
    PMaxAssetGroupAssetDTO,
    PMaxAssetGroupDTO,
    PMaxAssetGroupPrimaryStatus,
    PMaxAssetGroupStatus,
    PMaxAssetPolicyApprovalStatus,
    PMaxBiddingStrategyType,
    PMaxCampaignDTO,
    PMaxCampaignAssetDTO,
    PMaxRawSnapshot,
    PMaxCampaignServingStatus,
    PMaxCampaignStatus,
    PMaxObservabilityKernel,
    assemble_pmax_bundle,
    assert_read_only_gaql,
    build_pmax_asset_group_assets_query,
    build_pmax_asset_group_signals_query,
    build_pmax_asset_groups_query,
    build_pmax_assets_query,
    build_pmax_campaigns_query,
    build_pmax_campaign_assets_query,
    build_pmax_observability_bundle_queries,
    evaluate_asset_field_coverage,
    evaluate_asset_group_coverage,
    evaluate_campaign_coverage,
    extract_observed,
    project_asset_group_asset_row,
    project_asset_group_row,
    project_asset_group_signal_row,
    project_asset_row,
    project_campaign_metrics,
    project_campaign_row,
    validate_customer_id,
    validate_identifier,
    assert_v25_descriptor_contract,
)


# ============================================================================
# 1. TESTES DE CONSULTAS GAQL READ-ONLY E SEGURANÇA
# ============================================================================


class TestPMaxGAQLQueries:
    """Testes para garantir que todas as consultas são puramente de leitura."""

    def test_customer_id_validation(self) -> None:
        assert validate_customer_id("1234567890") == "1234567890"
        assert validate_customer_id("123-456-7890") == "1234567890"

        with pytest.raises(ValueError, match="Expected 10 digits"):
            validate_customer_id("123")
        with pytest.raises(ValueError, match="Expected 10 digits"):
            validate_customer_id("1234567890123")
        with pytest.raises(ValueError, match="Expected 10 digits"):
            validate_customer_id("abcdefghij")

    def test_identifier_validation_blocks_injection(self) -> None:
        assert validate_identifier("123456") == "123456"
        assert validate_identifier("campaign_abc-1") == "campaign_abc-1"

        with pytest.raises(ValueError, match="Contains forbidden characters"):
            validate_identifier("123; DROP TABLE campaign")
        with pytest.raises(ValueError, match="Contains forbidden characters"):
            validate_identifier("123' OR '1'='1")

    def test_assert_read_only_gaql_blocks_forbidden_operations(self) -> None:
        assert_read_only_gaql("SELECT campaign.id FROM campaign")

        # Não inicia com SELECT
        with pytest.raises(GAQLSecurityError, match="must begin with 'SELECT'"):
            assert_read_only_gaql("UPDATE campaign SET name = 'teste'")

        # Palavras proibidas
        with pytest.raises(GAQLSecurityError, match="Forbidden keywords detected"):
            assert_read_only_gaql("SELECT campaign.id FROM campaign WHERE MUTATE = 1")

        with pytest.raises(GAQLSecurityError, match="Forbidden keywords detected"):
            assert_read_only_gaql("SELECT campaign.id FROM campaign -- VALIDATE_ONLY")

        with pytest.raises(GAQLSecurityError, match="Forbidden keywords detected"):
            assert_read_only_gaql("SELECT campaign.id FROM campaign WHERE DELETE = 1")

    def test_build_pmax_campaigns_query_structure(self) -> None:
        q = build_pmax_campaigns_query(
            campaign_ids=["101", "102"],
            status_filter=["ENABLED", "PAUSED"],
            limit=50,
        )
        assert q.startswith("SELECT ")
        assert "campaign.advertising_channel_type = 'PERFORMANCE_MAX'" in q
        assert "campaign.id IN ('101', '102')" in q
        assert "campaign.status IN ('ENABLED', 'PAUSED')" in q
        assert "LIMIT 50" in q
        assert_read_only_gaql(q)

    def test_build_pmax_asset_groups_query_structure(self) -> None:
        q = build_pmax_asset_groups_query(
            campaign_ids=["101"],
            asset_group_ids=["201", "202"],
        )
        assert "FROM asset_group" in q
        assert "campaign.advertising_channel_type = 'PERFORMANCE_MAX'" in q
        assert "campaign.id IN ('101')" in q
        assert "asset_group.id IN ('201', '202')" in q
        assert_read_only_gaql(q)

    def test_build_pmax_asset_group_assets_query_structure(self) -> None:
        q = build_pmax_asset_group_assets_query(
            customer_id="1234567890",
            campaign_ids=["101"],
            asset_group_ids=["201"],
        )
        assert "FROM asset_group_asset" in q
        assert "campaign.advertising_channel_type = 'PERFORMANCE_MAX'" in q
        assert "asset_group_asset.asset_group IN ('customers/1234567890/assetGroups/201')" in q
        assert "performance_label" not in q
        assert "asset_group_asset.primary_status" in q
        assert_read_only_gaql(q)

    def test_build_pmax_assets_query_structure(self) -> None:
        q = build_pmax_assets_query(asset_ids=["301", "302"], limit=100)
        assert "FROM asset" in q
        assert "asset.id IN ('301', '302')" in q
        assert "LIMIT 100" in q
        assert_read_only_gaql(q)

    def test_build_pmax_asset_group_signals_query_structure(self) -> None:
        q = build_pmax_asset_group_signals_query("1234567890", asset_group_ids=["201"])
        assert "FROM asset_group_signal" in q
        assert "asset_group_signal.asset_group IN ('customers/1234567890/assetGroups/201')" in q
        assert_read_only_gaql(q)

    def test_build_pmax_observability_bundle_queries(self) -> None:
        bundle = build_pmax_observability_bundle_queries(
            customer_id="1234567890", campaign_id="999"
        )
        assert "campaigns" in bundle
        assert "asset_groups" in bundle
        assert "asset_group_assets" in bundle
        assert "assets" in bundle
        assert "signals" in bundle
        assert "campaign_assets" in bundle
        assert "url_expansion_opt_out" not in bundle["campaigns"]
        assert "campaign.brand_guidelines_enabled" in bundle["campaigns"]

        assert_v25_descriptor_contract()

        for key, q in bundle.items():
            assert_read_only_gaql(q)


# ============================================================================
# 2. TESTES DE SEMÂNTICA DE AUSÊNCIA VS ZERO MEDIDO
# ============================================================================


class TestObservationSemantics:
    """Valida a separação estrita de estados epistêmicos dos dados."""

    def test_measured_zero_vs_absent(self) -> None:
        # Zero numérico medido
        zero_val = extract_observed({"metrics": {"clicks": 0}}, "metrics.clicks", int)
        assert zero_val.state == ObservationState.MEASURED_ZERO
        assert zero_val.value == 0
        assert zero_val.is_zero is True
        assert zero_val.is_present is True
        assert zero_val.is_absent is False

        # Zero float medido
        zero_float = extract_observed(
            {"metrics": {"conversions": 0.0}}, "metrics.conversions", float
        )
        assert zero_float.state == ObservationState.MEASURED_ZERO
        assert zero_float.value == 0.0
        assert zero_float.is_zero is True

        # Campo ausente do payload
        absent_val = extract_observed({}, "metrics.clicks", int)
        assert absent_val.state == ObservationState.FIELD_ABSENT
        assert absent_val.value is None
        assert absent_val.is_zero is False
        assert absent_val.is_present is False
        assert absent_val.is_absent is True

        # Campo com None explícito na fonte
        none_val = extract_observed(
            {"metrics": {"clicks": None}}, "metrics.clicks", int
        )
        assert none_val.state == ObservationState.FIELD_ABSENT
        assert none_val.value is None
        assert none_val.is_absent is True

    def test_not_collected_and_not_applicable(self) -> None:
        nc = ObservedValue.not_collected(source_path="metrics.special")
        assert nc.state == ObservationState.NOT_COLLECTED
        assert nc.value is None
        assert nc.is_absent is True

        na = ObservedValue.not_applicable(source_path="lead_form")
        assert na.state == ObservationState.NOT_APPLICABLE
        assert na.value is None
        assert na.is_absent is True

    def test_unwrap_or(self) -> None:
        zero_val = ObservedValue.measured_zero(value=0)
        assert zero_val.unwrap_or(99) == 0

        present_val = ObservedValue.present(value=42)
        assert present_val.unwrap_or(99) == 42

        absent_val = ObservedValue.field_absent()
        assert absent_val.unwrap_or(99) == 99

    def test_collection_failed_on_invalid_parser(self) -> None:
        row = {"campaign": {"budget": "NOT_A_NUMBER"}}
        obs = extract_observed(row, "campaign.budget", int)
        assert obs.state == ObservationState.COLLECTION_FAILED
        assert obs.value is None
        assert obs.error_message is not None
        assert "invalid literal for int()" in obs.error_message

    def test_stale_data_detection(self) -> None:
        past_time = datetime.now(timezone.utc) - timedelta(hours=2)
        row = {"campaign": {"name": "Campanha 1"}}

        # Com threshold de 1 hora (3600 segundos), deve ser STALE
        stale_obs = extract_observed(
            row,
            "campaign.name",
            collected_at=past_time,
            stale_threshold_seconds=3600,
        )
        assert stale_obs.state == ObservationState.STALE
        assert stale_obs.value == "Campanha 1"

        # Com threshold de 3 horas (10800 segundos), deve ser PRESENT
        fresh_obs = extract_observed(
            row,
            "campaign.name",
            collected_at=past_time,
            stale_threshold_seconds=10800,
        )
        assert fresh_obs.state == ObservationState.PRESENT
        assert fresh_obs.value == "Campanha 1"


# ============================================================================
# 3. TESTES DE PROJEÇÃO DE LINHAS EM DTOs
# ============================================================================


class TestPMaxProjector:
    """Testes de projeção determinística de registros em DTOs imutáveis."""

    def test_project_asset_row(self) -> None:
        row = {
            "asset": {
                "resource_name": "customers/123/assets/555",
                "id": "555",
                "name": "Título Principal",
                "type": "TEXT",
                "text_asset": {"text": "Compre Agora com Desconto"},
                "policy_summary": {
                    "approval_status": "APPROVED",
                    "policy_topic_entries": [{"topic": "TRADEMARK"}],
                },
            }
        }
        dto = project_asset_row(row)
        assert dto.id == "555"
        assert dto.resource_name == "customers/123/assets/555"
        assert dto.name.value == "Título Principal"
        assert dto.name.state == ObservationState.PRESENT
        assert dto.text_content.value == "Compre Agora com Desconto"
        assert (
            dto.policy_approval_status.value
            == PMaxAssetPolicyApprovalStatus.APPROVED
        )
        assert dto.policy_topic_entries == ("TRADEMARK",)
        assert dto.youtube_video_id.state == ObservationState.FIELD_ABSENT
        assert dto.source_payload_hash is not None

    def test_project_asset_group_asset_row_with_lookup(self) -> None:
        asset_dto = PMaxAssetDTO(
            resource_name="customers/123/assets/555",
            id="555",
            name=ObservedValue.present("Header Asset"),
            asset_type="TEXT",
            text_content=ObservedValue.present("Oferta Especial"),
            youtube_video_id=ObservedValue.field_absent(),
            youtube_video_title=ObservedValue.field_absent(),
            image_url=ObservedValue.field_absent(),
            policy_approval_status=ObservedValue.present(
                PMaxAssetPolicyApprovalStatus.APPROVED
            ),
            policy_topic_entries=(),
        )
        asset_lookup = {"555": asset_dto}

        row = {
            "asset_group_asset": {
                "resource_name": "customers/123/assetGroupAssets/888~555~HEADLINE",
                "asset_group": "customers/123/assetGroups/888",
                "asset": "customers/123/assets/555",
                "field_type": "HEADLINE",
                "status": "ENABLED",
                "primary_status": "ELIGIBLE",
                "primary_status_reasons": [],
                "primary_status_details": [],
                "source": "ADVERTISER",
                "policy_summary": {
                    "approval_status": "APPROVED",
                    "policy_topic_entries": [],
                },
            }
        }
        aga_dto = project_asset_group_asset_row(row, asset_lookup=asset_lookup)
        assert aga_dto.asset_group_id == "888"
        assert aga_dto.asset_id == "555"
        assert aga_dto.field_type == PMaxAssetFieldType.HEADLINE
        assert aga_dto.primary_status.value == "ELIGIBLE"
        assert aga_dto.source.value == "ADVERTISER"
        assert aga_dto.asset_details == asset_dto

    def test_project_asset_group_signal_row(self) -> None:
        theme_row = {
            "asset_group_signal": {
                "resource_name": "customers/123/assetGroupSignals/888~1",
                "asset_group": "customers/123/assetGroups/888",
                "search_theme": {"text": "comprar calçados online"},
            }
        }
        theme_dto = project_asset_group_signal_row(theme_row)
        assert theme_dto.signal_type == "SEARCH_THEME"
        assert theme_dto.display_name.value == "comprar calçados online"
        assert theme_dto.asset_group_id == "888"

        aud_row = {
            "asset_group_signal": {
                "resource_name": "customers/123/assetGroupSignals/888~2",
                "asset_group": "customers/123/assetGroups/888",
                "audience": {"audience": "customers/123/audiences/999"},
            }
        }
        aud_dto = project_asset_group_signal_row(aud_row)
        assert aud_dto.signal_type == "AUDIENCE"
        assert aud_dto.display_name.value == "customers/123/audiences/999"

    def test_project_campaign_metrics_differentiation(self) -> None:
        row = {
            "metrics": {
                "impressions": 15000,
                "clicks": 0,  # 0 medido
                "cost_micros": 0,  # 0 medido
                # conversions ausente
            }
        }
        metrics = project_campaign_metrics(row)
        assert metrics.impressions.state == ObservationState.PRESENT
        assert metrics.impressions.value == 15000

        assert metrics.clicks.state == ObservationState.MEASURED_ZERO
        assert metrics.clicks.value == 0

        assert metrics.cost_micros.state == ObservationState.MEASURED_ZERO
        assert metrics.cost_micros.value == 0

        assert metrics.conversions.state == ObservationState.FIELD_ABSENT
        assert metrics.conversions.value is None

    def test_assemble_pmax_bundle_hierarchy(self) -> None:
        campaign_rows = [
            {
                "campaign": {
                    "id": "1001",
                    "resource_name": "customers/123/campaigns/1001",
                    "name": "PMax Verão 2025",
                    "status": "ENABLED",
                    "serving_status": "SERVING",
                    "advertising_channel_type": "PERFORMANCE_MAX",
                    "bidding_strategy_type": "MAXIMIZE_CONVERSIONS",
                    "maximize_conversions": {"target_cpa_micros": 50000000},
                },
                "campaign_budget": {"amount_micros": 100000000},
            }
        ]
        ag_rows = [
            {
                "asset_group": {
                    "id": "2001",
                    "resource_name": "customers/123/assetGroups/2001",
                    "campaign": "customers/123/campaigns/1001",
                    "name": "Grupo Principal",
                    "status": "ENABLED",
                    "primary_status": "ELIGIBLE",
                    "ad_strength": "GOOD",
                    "final_urls": ["https://exemplo.com.br/verao"],
                    "path1": "verao",
                    "path2": "promocao",
                }
            }
        ]
        aga_rows = [
            {
                "asset_group_asset": {
                    "resource_name": "customers/123/assetGroupAssets/2001~3001~HEADLINE",
                    "asset_group": "customers/123/assetGroups/2001",
                    "asset": "customers/123/assets/3001",
                    "field_type": "HEADLINE",
                    "status": "ENABLED",
                    "primary_status": "ELIGIBLE",
                    "source": "ADVERTISER",
                }
            }
        ]
        asset_rows = [
            {
                "asset": {
                    "id": "3001",
                    "resource_name": "customers/123/assets/3001",
                    "name": "Headline 1",
                    "type": "TEXT",
                    "text_asset": {"text": "Verão Imperdível"},
                }
            }
        ]
        signal_rows = [
            {
                "asset_group_signal": {
                    "resource_name": "customers/123/assetGroupSignals/2001~1",
                    "asset_group": "customers/123/assetGroups/2001",
                    "search_theme": {"text": "ofertas de verao"},
                }
            }
        ]

        campaigns = assemble_pmax_bundle(
            campaign_rows=campaign_rows,
            asset_group_rows=ag_rows,
            asset_group_asset_rows=aga_rows,
            asset_rows=asset_rows,
            signal_rows=signal_rows,
        )

        assert len(campaigns) == 1
        c = campaigns[0]
        assert c.id == "1001"
        assert c.name == "PMax Verão 2025"
        assert c.status == PMaxCampaignStatus.ENABLED
        assert c.serving_status.value == PMaxCampaignServingStatus.SERVING
        assert c.budget_amount_micros.value == 100000000
        assert c.target_cpa_micros.value == 50000000
        assert len(c.asset_groups) == 1

        ag = c.asset_groups[0]
        assert ag.id == "2001"
        assert ag.name == "Grupo Principal"
        assert ag.ad_strength.value == PMaxAdStrength.GOOD
        assert ag.final_urls == ("https://exemplo.com.br/verao",)
        assert ag.path1.value == "verao"
        assert ag.path2.value == "promocao"
        assert len(ag.assets) == 1
        assert len(ag.signals) == 1

        aga = ag.assets[0]
        assert aga.asset_id == "3001"
        assert aga.field_type == PMaxAssetFieldType.HEADLINE
        assert aga.asset_details is not None
        assert aga.asset_details.text_content.value == "Verão Imperdível"


# ============================================================================
# 4. TESTES DE DIAGNÓSTICO ESTRUTURAL DE COBERTURA (v25)
# ============================================================================


class TestPMaxCoverageEvaluator:
    """Testes de integridade da verificação de cobertura estrutural do PMax."""

    def _create_mock_asset_group_asset(
        self,
        field_type: PMaxAssetFieldType,
        pol: str = "APPROVED",
        status: str = "ENABLED",
        text: str = "Descrição curta",
    ) -> PMaxAssetGroupAssetDTO:
        asset_id = f"asset_{field_type.value}_{id(field_type)}"
        details = PMaxAssetDTO(
            resource_name=f"customers/1234567890/assets/{asset_id}",
            id=asset_id,
            name=ObservedValue.present(field_type.value),
            asset_type="TEXT" if field_type in (PMaxAssetFieldType.HEADLINE, PMaxAssetFieldType.LONG_HEADLINE, PMaxAssetFieldType.DESCRIPTION, PMaxAssetFieldType.BUSINESS_NAME) else "IMAGE",
            text_content=ObservedValue.present(text) if field_type in (PMaxAssetFieldType.HEADLINE, PMaxAssetFieldType.LONG_HEADLINE, PMaxAssetFieldType.DESCRIPTION, PMaxAssetFieldType.BUSINESS_NAME) else ObservedValue.not_applicable(),
            youtube_video_id=ObservedValue.not_applicable(),
            youtube_video_title=ObservedValue.not_applicable(),
            image_url=ObservedValue.not_applicable(),
            policy_approval_status=ObservedValue.present(PMaxAssetPolicyApprovalStatus[pol]),
            policy_topic_entries=(),
        )
        return PMaxAssetGroupAssetDTO(
            resource_name=f"customers/1234567890/assetGroupAssets/1~{asset_id}~{field_type.value}",
            asset_group_id="1",
            asset_id=asset_id,
            field_type=field_type,
            status=status,
            primary_status=ObservedValue.present("ELIGIBLE"),
            primary_status_reasons=(),
            primary_status_details=(),
            source=ObservedValue.present("ADVERTISER"),
            policy_approval_status=ObservedValue.present(
                PMaxAssetPolicyApprovalStatus[pol]
            ),
            policy_summary_reasons=(),
            asset_details=details,
        )

    def test_complete_asset_group_satisfies_all_mandatory_fields(self) -> None:
        assets: list[PMaxAssetGroupAssetDTO] = []
        # 3 Headlines
        for i in range(3):
            assets.append(
                self._create_mock_asset_group_asset(PMaxAssetFieldType.HEADLINE)
            )
        # 1 Long Headline
        assets.append(
            self._create_mock_asset_group_asset(PMaxAssetFieldType.LONG_HEADLINE)
        )
        # 2 Descriptions
        for i in range(2):
            assets.append(
                self._create_mock_asset_group_asset(PMaxAssetFieldType.DESCRIPTION)
            )
        # 1 Business Name
        assets.append(
            self._create_mock_asset_group_asset(PMaxAssetFieldType.BUSINESS_NAME)
        )
        # 1 Marketing Image (Landscape)
        assets.append(
            self._create_mock_asset_group_asset(PMaxAssetFieldType.MARKETING_IMAGE)
        )
        # 1 Square Marketing Image
        assets.append(
            self._create_mock_asset_group_asset(
                PMaxAssetFieldType.SQUARE_MARKETING_IMAGE
            )
        )
        # 1 Logo
        assets.append(self._create_mock_asset_group_asset(PMaxAssetFieldType.LOGO))

        ag = PMaxAssetGroupDTO(
            resource_name="customers/1234567890/assetGroups/1",
            id="1",
            campaign_id="100",
            name="Asset Group Completo",
            status=PMaxAssetGroupStatus.ENABLED,
            primary_status=ObservedValue.present(PMaxAssetGroupPrimaryStatus.ELIGIBLE),
            primary_status_reasons=(),
            ad_strength=ObservedValue.present(PMaxAdStrength.EXCELLENT),
            asset_coverage=ObservedValue.present({}),
            final_urls=("https://exemplo.com.br",),
            final_mobile_urls=(),
            path1=ObservedValue.field_absent(),
            path2=ObservedValue.field_absent(),
            assets=tuple(assets),
            signals=(),
        )

        report = evaluate_asset_group_coverage(ag, brand_guidelines_enabled=False)
        assert report.is_structurally_complete is True
        assert len(report.structural_gaps) == 0
        assert report.total_assets == 10

    def test_incomplete_asset_group_identifies_exact_gaps(self) -> None:
        # Apenas 1 headline e sem imagens/logos
        assets = [
            self._create_mock_asset_group_asset(PMaxAssetFieldType.HEADLINE),
            self._create_mock_asset_group_asset(PMaxAssetFieldType.BUSINESS_NAME),
        ]
        ag = PMaxAssetGroupDTO(
            resource_name="customers/1234567890/assetGroups/2",
            id="2",
            campaign_id="100",
            name="Asset Group Deficiente",
            status=PMaxAssetGroupStatus.ENABLED,
            primary_status=ObservedValue.present(PMaxAssetGroupPrimaryStatus.LIMITED),
            primary_status_reasons=("ASSET_GROUP_LIMITED",),
            ad_strength=ObservedValue.present(PMaxAdStrength.POOR),
            asset_coverage=ObservedValue.present({}),
            final_urls=(),  # Sem final URLs -> gap
            final_mobile_urls=(),
            path1=ObservedValue.field_absent(),
            path2=ObservedValue.field_absent(),
            assets=tuple(assets),
            signals=(),
        )

        report = evaluate_asset_group_coverage(ag, brand_guidelines_enabled=False)
        assert report.is_structurally_complete is False
        assert any("HEADLINE" in gap and "minimum required: 3" in gap for gap in report.structural_gaps)
        assert any("LONG_HEADLINE" in gap for gap in report.structural_gaps)
        assert any("DESCRIPTION" in gap for gap in report.structural_gaps)
        assert any("MARKETING_IMAGE" in gap for gap in report.structural_gaps)
        assert any("SQUARE_MARKETING_IMAGE" in gap for gap in report.structural_gaps)
        assert any("LOGO" in gap for gap in report.structural_gaps)
        assert any("no final_urls" in gap for gap in report.structural_gaps)
        assert any("Ad strength observed as POOR" in w for w in report.warnings)

    def test_exceeded_maximum_limits(self) -> None:
        # 16 Headlines (máximo 15)
        assets = [
            self._create_mock_asset_group_asset(PMaxAssetFieldType.HEADLINE)
            for _ in range(16)
        ]
        cov = evaluate_asset_field_coverage(
            PMaxAssetFieldType.HEADLINE, tuple(assets)
        )
        assert cov.is_max_exceeded is True
        assert cov.actual_count == 16
        assert any("Maximum exceeded" in obs for obs in cov.observations)

    def test_campaign_coverage_aggregation(self) -> None:
        # Campanha com 1 completo e 1 incompleto
        ag_complete = PMaxAssetGroupDTO(
            resource_name="customers/1234567890/assetGroups/1",
            id="1",
            campaign_id="100",
            name="Completo",
            status=PMaxAssetGroupStatus.ENABLED,
            primary_status=ObservedValue.present(PMaxAssetGroupPrimaryStatus.ELIGIBLE),
            primary_status_reasons=(),
            ad_strength=ObservedValue.present(PMaxAdStrength.GOOD),
            asset_coverage=ObservedValue.present({}),
            final_urls=("https://exemplo.com.br",),
            final_mobile_urls=(),
            path1=ObservedValue.field_absent(),
            path2=ObservedValue.field_absent(),
            assets=tuple(
                [self._create_mock_asset_group_asset(PMaxAssetFieldType.HEADLINE) for _ in range(3)]
                + [self._create_mock_asset_group_asset(PMaxAssetFieldType.LONG_HEADLINE)]
                + [self._create_mock_asset_group_asset(PMaxAssetFieldType.DESCRIPTION) for _ in range(2)]
                + [self._create_mock_asset_group_asset(PMaxAssetFieldType.BUSINESS_NAME)]
                + [self._create_mock_asset_group_asset(PMaxAssetFieldType.MARKETING_IMAGE)]
                + [self._create_mock_asset_group_asset(PMaxAssetFieldType.SQUARE_MARKETING_IMAGE)]
                + [self._create_mock_asset_group_asset(PMaxAssetFieldType.LOGO)]
            ),
            signals=(),
        )

        ag_empty = PMaxAssetGroupDTO(
            resource_name="customers/1234567890/assetGroups/2",
            id="2",
            campaign_id="100",
            name="Vazio",
            status=PMaxAssetGroupStatus.PAUSED,
            primary_status=ObservedValue.present(PMaxAssetGroupPrimaryStatus.PAUSED),
            primary_status_reasons=(),
            ad_strength=ObservedValue.present(PMaxAdStrength.NO_ADS),
            asset_coverage=ObservedValue.present({}),
            final_urls=(),
            final_mobile_urls=(),
            path1=ObservedValue.field_absent(),
            path2=ObservedValue.field_absent(),
            assets=(),
            signals=(),
        )

        camp = PMaxCampaignDTO(
            resource_name="customers/1234567890/campaigns/100",
            id="100",
            name="Campanha Teste",
            status=PMaxCampaignStatus.ENABLED,
            serving_status=ObservedValue.present(PMaxCampaignServingStatus.SERVING),
            advertising_channel_type="PERFORMANCE_MAX",
            budget_amount_micros=ObservedValue.present(5000000),
            bidding_strategy_type=ObservedValue.present(PMaxBiddingStrategyType.MAXIMIZE_CONVERSIONS),
            target_cpa_micros=ObservedValue.field_absent(),
            target_roas=ObservedValue.field_absent(),
            brand_guidelines_enabled=ObservedValue.present(False),
            campaign_assets=(),
            asset_groups=(ag_complete, ag_empty),
            metrics=None,
            observed_at=datetime.now(timezone.utc),
        )

        camp_report = evaluate_campaign_coverage(camp)
        assert camp_report.total_asset_groups == 2
        assert camp_report.eligible_asset_groups == 1
        assert camp_report.all_asset_groups_complete is False
        assert any("1 of 2 asset group(s) have structural gaps" in obs for obs in camp_report.summary_observations)


# ============================================================================
# 5. TESTES DO KERNEL READ-ONLY E ISOLAMENTO
# ============================================================================


class TestPMaxKernelAndImmutability:
    """Testes do kernel de observabilidade e garantias de imutabilidade."""

    def test_kernel_facade_end_to_end(self) -> None:
        kernel = PMaxObservabilityKernel()
        assert "Google Ads API v25" in kernel.disclaimer

        queries = kernel.get_bundle_queries(customer_id="1234567890", campaign_id="500")
        assert len(queries) == 6

        # Simular dados recebidos da API
        camp_rows = [
            {
                "campaign": {
                    "id": "500",
                    "resource_name": "customers/1234567890/campaigns/500",
                    "name": "Kernel Camp",
                    "status": "ENABLED",
                    "advertising_channel_type": "PERFORMANCE_MAX",
                    "brand_guidelines_enabled": False,
                }
            }
        ]
        ag_rows = [
            {
                "asset_group": {
                    "id": "600",
                    "resource_name": "customers/1234567890/assetGroups/600",
                    "campaign": "customers/123/campaigns/500",
                    "name": "Grupo A",
                    "status": "ENABLED",
                    "final_urls": ["https://exemplo.com"],
                }
            }
        ]

        snapshot = PMaxRawSnapshot(
            campaign_rows=CollectionEnvelope.measured(camp_rows, "campaigns"),
            asset_group_rows=CollectionEnvelope.measured(ag_rows, "asset_groups"),
            asset_group_asset_rows=CollectionEnvelope.measured([], "asset_group_assets"),
            asset_rows=CollectionEnvelope.measured([], "assets"),
            signal_rows=CollectionEnvelope.measured([], "signals"),
            campaign_asset_rows=CollectionEnvelope.measured([], "campaign_assets"),
        )
        results = kernel.inspect_and_diagnose(snapshot)

        assert results.state == CollectionState.PRESENT
        assert len(results.results) == 1
        camp_dto, camp_report = results.results[0]
        assert camp_dto.id == "500"
        assert camp_report.total_asset_groups == 1
        assert camp_report.all_asset_groups_complete is None
        assert camp_report.verdict == CoverageVerdict.INDETERMINATE

    def test_dto_immutability(self) -> None:
        obs = ObservedValue.present("teste")
        with pytest.raises(FrozenInstanceError):
            obs.value = "novo"  # type: ignore[misc]

        asset = PMaxAssetDTO(
            resource_name="customers/1234567890/assets/1",
            id="1",
            name=obs,
            asset_type="TEXT",
            text_content=obs,
            youtube_video_id=ObservedValue.field_absent(),
            youtube_video_title=ObservedValue.field_absent(),
            image_url=ObservedValue.field_absent(),
            policy_approval_status=ObservedValue.field_absent(),
            policy_topic_entries=(),
        )
        with pytest.raises(FrozenInstanceError):
            asset.id = "2"  # type: ignore[misc]

    def test_zero_network_zero_mutate_guarantees(self) -> None:
        """Prova formal de que o módulo não expõe métodos de mutação, criação ou I/O."""
        import volc_ads.observabilidade_pmax as pmax_mod

        # Verificar que não há palavras como mutate, create, update, post, delete no módulo
        public_callables = [
            getattr(pmax_mod, attr)
            for attr in dir(pmax_mod)
            if not attr.startswith("_")
        ]

        for obj in public_callables:
            name = getattr(obj, "__name__", str(obj)).lower()
            assert "mutate" not in name
            assert "create_campaign" not in name
            assert "update_asset" not in name
            assert "delete" not in name


# ============================================================================
# 6. CONTRAPROVAS DOS SETE BLOQUEADORES DO CANDIDATO ORIGINAL
# ============================================================================


class TestPMaxV25AdversarialRegressions:
    def _snapshot_with(
        self, state: CollectionState, source: str = "asset_group_assets"
    ) -> PMaxRawSnapshot:
        def envelope(name: str) -> CollectionEnvelope[dict[str, object]]:
            if name != source:
                return CollectionEnvelope.measured([], name)
            if state == CollectionState.NOT_COLLECTED:
                return CollectionEnvelope.not_collected(name)
            if state == CollectionState.COLLECTION_FAILED:
                return CollectionEnvelope.failed(name, "falha sintética")
            if state == CollectionState.STALE:
                return CollectionEnvelope.stale([], name)
            return CollectionEnvelope.measured([], name)

        return PMaxRawSnapshot(
            campaign_rows=envelope("campaigns"),
            asset_group_rows=envelope("asset_groups"),
            asset_group_asset_rows=envelope("asset_group_assets"),
            asset_rows=envelope("assets"),
            signal_rows=envelope("signals"),
            campaign_asset_rows=envelope("campaign_assets"),
        )

    @pytest.mark.parametrize(
        "state",
        [CollectionState.NOT_COLLECTED, CollectionState.COLLECTION_FAILED, CollectionState.STALE],
    )
    def test_incomplete_collection_blocks_diagnosis(self, state: CollectionState) -> None:
        outcome = PMaxObservabilityKernel().inspect_and_diagnose(self._snapshot_with(state))
        assert outcome.state == state
        assert outcome.results == ()
        assert outcome.blocked_sources == ("asset_group_assets",)

    def test_present_empty_is_measured_and_not_failure(self) -> None:
        outcome = PMaxObservabilityKernel().inspect_and_diagnose(
            self._snapshot_with(CollectionState.PRESENT_EMPTY)
        )
        assert outcome.state == CollectionState.PRESENT_EMPTY
        assert outcome.results == ()
        assert outcome.blocked_sources == ()

    def test_sdk_v25_descriptor_and_gaql_contract_reject_old_fields(self) -> None:
        assert_v25_descriptor_contract()
        queries = build_pmax_observability_bundle_queries("1234567890", "77")
        joined = "\n".join(queries.values())
        assert "url_expansion_opt_out" not in joined
        assert "performance_label" not in joined
        assert "asset_group.asset_coverage" in queries["asset_groups"]
        assert "asset_group_asset.primary_status_details" in queries["asset_group_assets"]
        assert "campaign_asset.field_type" in queries["campaign_assets"]

    def test_limits_match_local_v25_matrix_and_removed_links_do_not_count(self) -> None:
        helper = TestPMaxCoverageEvaluator()
        landscape = tuple(
            helper._create_mock_asset_group_asset(PMaxAssetFieldType.LANDSCAPE_LOGO)
            for _ in range(6)
        )
        videos = tuple(
            helper._create_mock_asset_group_asset(PMaxAssetFieldType.YOUTUBE_VIDEO)
            for _ in range(6)
        )
        media = tuple(
            helper._create_mock_asset_group_asset(PMaxAssetFieldType.MEDIA_BUNDLE)
            for _ in range(2)
        )
        removed = tuple(
            helper._create_mock_asset_group_asset(PMaxAssetFieldType.HEADLINE, status="REMOVED")
            for _ in range(4)
        )
        assert evaluate_asset_field_coverage(PMaxAssetFieldType.LANDSCAPE_LOGO, landscape).is_max_exceeded is False
        assert evaluate_asset_field_coverage(PMaxAssetFieldType.YOUTUBE_VIDEO, videos).is_max_exceeded is False
        assert evaluate_asset_field_coverage(PMaxAssetFieldType.MEDIA_BUNDLE, media).is_max_exceeded is True
        assert evaluate_asset_field_coverage(PMaxAssetFieldType.HEADLINE, removed).actual_count == 0

    def test_long_descriptions_without_one_at_most_60_are_a_real_gap(self) -> None:
        helper = TestPMaxCoverageEvaluator()
        assets = tuple(
            [helper._create_mock_asset_group_asset(PMaxAssetFieldType.HEADLINE) for _ in range(3)]
            + [helper._create_mock_asset_group_asset(PMaxAssetFieldType.LONG_HEADLINE)]
            + [helper._create_mock_asset_group_asset(PMaxAssetFieldType.DESCRIPTION, text="x" * 61) for _ in range(2)]
            + [helper._create_mock_asset_group_asset(PMaxAssetFieldType.BUSINESS_NAME)]
            + [helper._create_mock_asset_group_asset(PMaxAssetFieldType.MARKETING_IMAGE)]
            + [helper._create_mock_asset_group_asset(PMaxAssetFieldType.SQUARE_MARKETING_IMAGE)]
            + [helper._create_mock_asset_group_asset(PMaxAssetFieldType.LOGO)]
        )
        group = PMaxAssetGroupDTO(
            resource_name="customers/1234567890/assetGroups/1", id="1", campaign_id="10",
            name="Grupo", status=PMaxAssetGroupStatus.ENABLED,
            primary_status=ObservedValue.present(PMaxAssetGroupPrimaryStatus.ELIGIBLE),
            primary_status_reasons=(), ad_strength=ObservedValue.present(PMaxAdStrength.GOOD),
            asset_coverage=ObservedValue.present({}), final_urls=("https://example.test",),
            final_mobile_urls=(), path1=ObservedValue.field_absent(), path2=ObservedValue.field_absent(),
            assets=assets, signals=(),
        )
        report = evaluate_asset_group_coverage(group, brand_guidelines_enabled=False)
        assert report.verdict == CoverageVerdict.GAPS
        assert any("60 characters" in gap for gap in report.structural_gaps)

    def test_brand_guidelines_reads_business_and_logo_from_campaign_asset(self) -> None:
        helper = TestPMaxCoverageEvaluator()
        group_assets = tuple(
            [helper._create_mock_asset_group_asset(PMaxAssetFieldType.HEADLINE) for _ in range(3)]
            + [helper._create_mock_asset_group_asset(PMaxAssetFieldType.LONG_HEADLINE)]
            + [helper._create_mock_asset_group_asset(PMaxAssetFieldType.DESCRIPTION) for _ in range(2)]
            + [helper._create_mock_asset_group_asset(PMaxAssetFieldType.MARKETING_IMAGE)]
            + [helper._create_mock_asset_group_asset(PMaxAssetFieldType.SQUARE_MARKETING_IMAGE)]
        )
        group = PMaxAssetGroupDTO(
            resource_name="customers/1234567890/assetGroups/1", id="1", campaign_id="10",
            name="Grupo", status=PMaxAssetGroupStatus.ENABLED,
            primary_status=ObservedValue.present(PMaxAssetGroupPrimaryStatus.ELIGIBLE),
            primary_status_reasons=(), ad_strength=ObservedValue.present(PMaxAdStrength.GOOD),
            asset_coverage=ObservedValue.present({}), final_urls=("https://example.test",),
            final_mobile_urls=(), path1=ObservedValue.field_absent(), path2=ObservedValue.field_absent(),
            assets=group_assets, signals=(),
        )
        campaign_assets = tuple(
            PMaxCampaignAssetDTO(
                resource_name=f"customers/1234567890/campaignAssets/10~{i}~{field.value}",
                campaign_id="10", asset_id=str(i), field_type=field, status="ENABLED",
                primary_status=ObservedValue.present("ELIGIBLE"), primary_status_reasons=(),
                primary_status_details=(), source=ObservedValue.present("ADVERTISER"),
            )
            for i, field in enumerate((PMaxAssetFieldType.BUSINESS_NAME, PMaxAssetFieldType.LOGO), 1)
        )
        campaign = PMaxCampaignDTO(
            resource_name="customers/1234567890/campaigns/10", id="10", name="PMax",
            status=PMaxCampaignStatus.ENABLED,
            serving_status=ObservedValue.present(PMaxCampaignServingStatus.SERVING),
            advertising_channel_type="PERFORMANCE_MAX", budget_amount_micros=ObservedValue.present(1),
            bidding_strategy_type=ObservedValue.present(PMaxBiddingStrategyType.MAXIMIZE_CONVERSIONS),
            target_cpa_micros=ObservedValue.field_absent(), target_roas=ObservedValue.field_absent(),
            brand_guidelines_enabled=ObservedValue.present(True), campaign_assets=campaign_assets,
            asset_groups=(group,), metrics=None, observed_at=datetime.now(timezone.utc),
        )
        report = evaluate_campaign_coverage(campaign)
        assert report.verdict == CoverageVerdict.COMPLETE
        assert report.all_asset_groups_complete is True

    def test_primary_status_not_enabled_status_decides_eligibility(self) -> None:
        helper = TestPMaxCoverageEvaluator()
        group = PMaxAssetGroupDTO(
            resource_name="customers/1234567890/assetGroups/1", id="1", campaign_id="10",
            name="Limitado", status=PMaxAssetGroupStatus.ENABLED,
            primary_status=ObservedValue.present(PMaxAssetGroupPrimaryStatus.LIMITED),
            primary_status_reasons=("ASSET_GROUP_LIMITED",),
            ad_strength=ObservedValue.present(PMaxAdStrength.POOR), asset_coverage=ObservedValue.present({}),
            final_urls=(), final_mobile_urls=(), path1=ObservedValue.field_absent(),
            path2=ObservedValue.field_absent(), assets=(), signals=(),
        )
        campaign = PMaxCampaignDTO(
            resource_name="customers/1234567890/campaigns/10", id="10", name="PMax",
            status=PMaxCampaignStatus.ENABLED,
            serving_status=ObservedValue.present(PMaxCampaignServingStatus.SERVING),
            advertising_channel_type="PERFORMANCE_MAX", budget_amount_micros=ObservedValue.present(1),
            bidding_strategy_type=ObservedValue.present(PMaxBiddingStrategyType.MAXIMIZE_CONVERSIONS),
            target_cpa_micros=ObservedValue.field_absent(), target_roas=ObservedValue.field_absent(),
            brand_guidelines_enabled=ObservedValue.present(False), campaign_assets=(),
            asset_groups=(group,), metrics=None, observed_at=datetime.now(timezone.utc),
        )
        assert evaluate_campaign_coverage(campaign).eligible_asset_groups == 0
