from __future__ import annotations

import json
from datetime import date, datetime, timezone

from google.ads.googleads.v25.common.types.policy import PolicyTopicEntry
from google.ads.googleads.v25.enums.types.ad_group_ad_primary_status import AdGroupAdPrimaryStatusEnum
from google.ads.googleads.v25.enums.types.ad_group_criterion_approval_status import (
    AdGroupCriterionApprovalStatusEnum,
)
from google.ads.googleads.v25.enums.types.asset_group_primary_status import AssetGroupPrimaryStatusEnum
from google.ads.googleads.v25.enums.types.campaign_primary_status import CampaignPrimaryStatusEnum
from google.ads.googleads.v25.enums.types.campaign_primary_status_reason import (
    CampaignPrimaryStatusReasonEnum,
)
from google.ads.googleads.v25.enums.types.policy_approval_status import PolicyApprovalStatusEnum
from google.ads.googleads.v25.enums.types.policy_review_status import PolicyReviewStatusEnum
from google.ads.googleads.v25.enums.types.policy_topic_entry_type import PolicyTopicEntryTypeEnum
from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow

from volc_ads.coleta.contrato import Contexto
from volc_ads.coleta.familias import todas
from volc_ads.coleta.familias.estado import FAMILIA, GAQLS
from volc_ads.gads import catalogo

CTX = Contexto(customer_id="5478096539", login_customer_id="4904074301", origem_janela="D0",
               data_inicio=date(2026, 10, 8), data_fim=date(2026, 10, 8),
               fuso="America/Sao_Paulo", moeda="BRL",
               colhida_em=datetime(2026, 10, 8, 20, 0, tzinfo=timezone.utc))
TIPOS = {"campaign", "ad_group", "ad_group_ad", "asset_group", "asset_group_asset", "keyword",
         "campaign_asset"}
CHAVES = {"entidade_tipo", "entidade_id", "campaign_id", "status", "primary_status",
          "primary_status_reasons", "aprovacao", "revisao", "topicos_politica", "observado_em"}
ENABLED, PAUSED = 2, 3


def _campanha() -> GoogleAdsRow:
    r = GoogleAdsRow()
    r.campaign.id = 23518009650
    r.campaign.status = PAUSED
    r.campaign.primary_status = CampaignPrimaryStatusEnum.CampaignPrimaryStatus.PAUSED
    r.campaign.primary_status_reasons.append(
        CampaignPrimaryStatusReasonEnum.CampaignPrimaryStatusReason.CAMPAIGN_PAUSED)
    return r


def _anuncio() -> GoogleAdsRow:
    r = GoogleAdsRow()
    r.campaign.id = 24278665189
    r.ad_group.id = 190000000001
    a = r.ad_group_ad
    a.resource_name = "customers/5478096539/adGroupAds/190000000001~780000000001"
    a.status = ENABLED
    a.primary_status = AdGroupAdPrimaryStatusEnum.AdGroupAdPrimaryStatus.ELIGIBLE
    a.policy_summary.approval_status = PolicyApprovalStatusEnum.PolicyApprovalStatus.APPROVED_LIMITED
    a.policy_summary.review_status = PolicyReviewStatusEnum.PolicyReviewStatus.REVIEWED
    a.policy_summary.policy_topic_entries.append(PolicyTopicEntry(
        topic="TRADEMARKS_IN_AD_TEXT", type_=PolicyTopicEntryTypeEnum.PolicyTopicEntryType.LIMITED))
    return r


def _keyword() -> GoogleAdsRow:
    r = GoogleAdsRow()
    r.campaign.id = 23518009650
    r.ad_group.id = 193210441352
    k = r.ad_group_criterion
    k.resource_name = "customers/5478096539/adGroupCriteria/193210441352~2432033692024"
    k.criterion_id = 2432033692024
    k.status = ENABLED
    k.approval_status = AdGroupCriterionApprovalStatusEnum.AdGroupCriterionApprovalStatus.APPROVED
    return r


def _asset_group() -> GoogleAdsRow:
    r = GoogleAdsRow()
    r.campaign.id = 24000000000
    r.asset_group.id = 6500000001
    r.asset_group.status = ENABLED
    r.asset_group.primary_status = AssetGroupPrimaryStatusEnum.AssetGroupPrimaryStatus.LIMITED
    return r


def _asset_group_asset() -> GoogleAdsRow:
    r = _asset_group()
    aga = r.asset_group_asset
    aga.resource_name = "customers/5478096539/assetGroupAssets/6500000001~123~HEADLINE"
    aga.status = ENABLED
    aga.primary_status = 4
    aga.policy_summary.approval_status = PolicyApprovalStatusEnum.PolicyApprovalStatus.APPROVED
    return r


def _campaign_asset() -> GoogleAdsRow:
    r = GoogleAdsRow()
    r.campaign.id = 24278665189
    r.campaign_asset.resource_name = "customers/5478096539/campaignAssets/24278665189~456~SITELINK"
    r.campaign_asset.status = ENABLED
    return r


def _ad_group() -> GoogleAdsRow:
    r = GoogleAdsRow()
    r.campaign.id = 24278665189
    r.ad_group.id = 190000000001
    r.ad_group.status = ENABLED
    return r


def teste_familia_registrada_com_nome_e_rpc():
    assert todas()["estado"] is FAMILIA
    assert FAMILIA.rpc == "volc_registrar_gads_fatos"


def teste_uma_gaql_por_entidade_sem_data_e_sem_removido():
    consultas = FAMILIA.gaql(CTX)
    assert isinstance(consultas, list) and len(consultas) == len(GAQLS) == 7
    assert set(GAQLS) == TIPOS
    for g in consultas:
        assert catalogo.invalidos(g) == (), g
        assert "segments.date" not in g
        assert "!= 'REMOVED'" in g
    assert "ad_group_criterion.type = 'KEYWORD'" in GAQLS["keyword"]


def teste_cada_entidade_e_reconhecida_pela_linha():
    casos = {
        "campaign": (_campanha(), "23518009650"),
        "ad_group": (_ad_group(), "190000000001"),
        "ad_group_ad": (_anuncio(), "190000000001~780000000001"),
        "keyword": (_keyword(), "193210441352~2432033692024"),
        "asset_group": (_asset_group(), "6500000001"),
        "asset_group_asset": (_asset_group_asset(), "6500000001~123~HEADLINE"),
        "campaign_asset": (_campaign_asset(), "24278665189~456~SITELINK"),
    }
    for tipo, (row, entidade_id) in casos.items():
        l = FAMILIA.normalizar(row, CTX)
        assert set(l) == CHAVES, tipo
        assert (l["entidade_tipo"], l["entidade_id"]) == (tipo, entidade_id)
        assert l["entidade_tipo"] in TIPOS
        assert isinstance(l["campaign_id"], str) and l["campaign_id"].isdigit()
        assert l["observado_em"] == CTX.colhida_iso
        assert json.loads(json.dumps(l)) == l


def teste_campanha_motivos_sao_nomes_e_sem_politica_vira_none():
    l = FAMILIA.normalizar(_campanha(), CTX)
    assert (l["status"], l["primary_status"]) == ("PAUSED", "PAUSED")
    assert l["primary_status_reasons"] == ["CAMPAIGN_PAUSED"]
    assert l["aprovacao"] is None and l["revisao"] is None and l["topicos_politica"] == []


def teste_anuncio_traz_politica():
    l = FAMILIA.normalizar(_anuncio(), CTX)
    assert (l["aprovacao"], l["revisao"]) == ("APPROVED_LIMITED", "REVIEWED")
    assert l["topicos_politica"] == [{"topic": "TRADEMARKS_IN_AD_TEXT", "type": "LIMITED"}]
    assert l["primary_status_reasons"] == []


def teste_keyword_aprovacao_e_tipos():
    l = FAMILIA.normalizar(_keyword(), CTX)
    assert (l["status"], l["aprovacao"], l["revisao"]) == ("ENABLED", "APPROVED", None)
    for k in CHAVES - {"primary_status_reasons", "topicos_politica"}:
        assert l[k] is None or isinstance(l[k], str), k
    assert all(isinstance(m, str) for m in l["primary_status_reasons"])


def teste_linha_sem_entidade_e_descartada():
    assert FAMILIA.normalizar(GoogleAdsRow(), CTX) is None
