"""Introspecção OFFLINE dos tipos do SDK google-ads (v25). Sem cliente, sem credenciais, sem rede.

Reprodução (a partir da raiz do checkout):
  backend/.venv/bin/python -I .claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-A-apis/experimentos/introspeccao_sdk_v25.py \
     > .claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-A-apis/experimentos/introspeccao_sdk_v25.out.txt
"""
import importlib, importlib.metadata as md, inspect, json, sys

V = "google.ads.googleads.v25"
out = {"google-ads": md.version("google-ads"), "python": sys.version.split()[0]}

def campos(mod, nome):
    m = importlib.import_module(f"{V}.{mod}")
    cls = getattr(m, nome)
    return list(cls.meta.fields.keys())

def enum_vals(modulo, classe, interno):
    m = importlib.import_module(f"{V}.enums.types.{modulo}")
    e = getattr(getattr(m, classe), interno)
    return [x.name for x in e]

def err_vals(modulo, classe, interno):
    m = importlib.import_module(f"{V}.errors.types.{modulo}")
    e = getattr(getattr(m, classe), interno)
    return [x.name for x in e]

def metodos(svc_pkg, client_cls):
    m = importlib.import_module(f"{V}.services.services.{svc_pkg}")
    c = getattr(m, client_cls)
    return sorted(n for n, _ in inspect.getmembers(c, inspect.isfunction) if not n.startswith("_") and n not in {"from_service_account_file","from_service_account_info","from_service_account_json","get_mtls_endpoint_and_cert_source"} and not n.endswith("_path") and not n.startswith("parse_") and not n.startswith("common_"))

T = {}
def tenta(chave, fn):
    try: T[chave] = fn()
    except Exception as e: T[chave] = f"ERRO {type(e).__name__}: {e}"

S = "services.types"
R = "resources.types"
C = "common.types"
# Q1 atomicidade
tenta("MutateGoogleAdsRequest", lambda: campos(f"{S}.google_ads_service", "MutateGoogleAdsRequest"))
tenta("MutateGoogleAdsResponse", lambda: campos(f"{S}.google_ads_service", "MutateGoogleAdsResponse"))
tenta("BatchJobService.metodos", lambda: metodos("batch_job_service", "BatchJobServiceClient"))
tenta("AddBatchJobOperationsRequest", lambda: campos(f"{S}.batch_job_service", "AddBatchJobOperationsRequest"))
tenta("RunBatchJobRequest", lambda: campos(f"{S}.batch_job_service", "RunBatchJobRequest"))
tenta("BatchJob.campos", lambda: campos(f"{R}.batch_job", "BatchJob"))
tenta("DatabaseError", lambda: err_vals("database_error", "DatabaseErrorEnum", "DatabaseError"))
tenta("MutateError", lambda: err_vals("mutate_error", "MutateErrorEnum", "MutateError"))
tenta("QuotaError", lambda: err_vals("quota_error", "QuotaErrorEnum", "QuotaError"))
tenta("RequestError(contém TOO_MANY_MUTATE_OPERATIONS?)", lambda: [x for x in err_vals("request_error", "RequestErrorEnum", "RequestError") if "TOO" in x or "SIZE" in x or "LIMIT" in x])
tenta("BatchJobError", lambda: err_vals("batch_job_error", "BatchJobErrorEnum", "BatchJobError"))
# Q2/Q3 conversões
tenta("ConversionUploadService.metodos", lambda: metodos("conversion_upload_service", "ConversionUploadServiceClient"))
tenta("ClickConversion", lambda: campos(f"{S}.conversion_upload_service", "ClickConversion"))
tenta("UploadClickConversionsRequest", lambda: campos(f"{S}.conversion_upload_service", "UploadClickConversionsRequest"))
tenta("ConversionAdjustmentUploadService.metodos", lambda: metodos("conversion_adjustment_upload_service", "ConversionAdjustmentUploadServiceClient"))
tenta("ConversionAdjustment", lambda: campos(f"{S}.conversion_adjustment_upload_service", "ConversionAdjustment"))
tenta("GclidDateTimePair", lambda: campos(f"{S}.conversion_adjustment_upload_service", "GclidDateTimePair"))
tenta("RestatementValue", lambda: campos(f"{S}.conversion_adjustment_upload_service", "RestatementValue"))
tenta("UploadConversionAdjustmentsRequest", lambda: campos(f"{S}.conversion_adjustment_upload_service", "UploadConversionAdjustmentsRequest"))
tenta("ConversionAdjustmentType", lambda: enum_vals("conversion_adjustment_type", "ConversionAdjustmentTypeEnum", "ConversionAdjustmentType"))
tenta("ConversionAdjustmentUploadError", lambda: err_vals("conversion_adjustment_upload_error", "ConversionAdjustmentUploadErrorEnum", "ConversionAdjustmentUploadError"))
tenta("ConversionUploadError", lambda: err_vals("conversion_upload_error", "ConversionUploadErrorEnum", "ConversionUploadError"))
tenta("OfflineUserDataJobService.metodos", lambda: metodos("offline_user_data_job_service", "OfflineUserDataJobServiceClient"))
tenta("OfflineUserDataJobType", lambda: enum_vals("offline_user_data_job_type", "OfflineUserDataJobTypeEnum", "OfflineUserDataJobType"))
# Q4 sazonalidade
tenta("BiddingSeasonalityAdjustment", lambda: campos(f"{R}.bidding_seasonality_adjustment", "BiddingSeasonalityAdjustment"))
tenta("BiddingDataExclusion", lambda: campos(f"{R}.bidding_data_exclusion", "BiddingDataExclusion"))
tenta("SeasonalityEventScope", lambda: enum_vals("seasonality_event_scope", "SeasonalityEventScopeEnum", "SeasonalityEventScope"))
tenta("BiddingSeasonalityAdjustmentService.metodos", lambda: metodos("bidding_seasonality_adjustment_service", "BiddingSeasonalityAdjustmentServiceClient"))
tenta("MutateBiddingSeasonalityAdjustmentsRequest", lambda: campos(f"{S}.bidding_seasonality_adjustment_service", "MutateBiddingSeasonalityAdjustmentsRequest"))
# Q5 experimentos
tenta("ExperimentService.metodos", lambda: metodos("experiment_service", "ExperimentServiceClient"))
tenta("ExperimentArmService.metodos", lambda: metodos("experiment_arm_service", "ExperimentArmServiceClient"))
tenta("Experiment", lambda: campos(f"{R}.experiment", "Experiment"))
tenta("ExperimentArm", lambda: campos(f"{R}.experiment_arm", "ExperimentArm"))
tenta("ExperimentType", lambda: enum_vals("experiment_type", "ExperimentTypeEnum", "ExperimentType"))
tenta("ScheduleExperimentRequest", lambda: campos(f"{S}.experiment_service", "ScheduleExperimentRequest"))
tenta("PromoteExperimentRequest", lambda: campos(f"{S}.experiment_service", "PromoteExperimentRequest"))
tenta("GraduateExperimentRequest", lambda: campos(f"{S}.experiment_service", "GraduateExperimentRequest"))
tenta("EndExperimentRequest", lambda: campos(f"{S}.experiment_service", "EndExperimentRequest"))
tenta("ExperimentStatus", lambda: enum_vals("experiment_status", "ExperimentStatusEnum", "ExperimentStatus"))
# Q6 QS
tenta("AdGroupCriterion.QualityInfo", lambda: list(importlib.import_module(f"{V}.{R}.ad_group_criterion").AdGroupCriterion.QualityInfo.meta.fields.keys()))
tenta("QualityScoreBucket", lambda: enum_vals("quality_score_bucket", "QualityScoreBucketEnum", "QualityScoreBucket"))
# Q7 assets
tenta("AdGroupAdAssetView", lambda: campos(f"{R}.ad_group_ad_asset_view", "AdGroupAdAssetView"))
tenta("AssetPerformanceLabel", lambda: enum_vals("asset_performance_label", "AssetPerformanceLabelEnum", "AssetPerformanceLabel"))
tenta("AssetGroupAsset", lambda: campos(f"{R}.asset_group_asset", "AssetGroupAsset"))
tenta("AdTextAsset", lambda: campos(f"{C}.ad_asset", "AdTextAsset"))
tenta("ResponsiveSearchAdInfo", lambda: campos(f"{C}.ad_type_infos", "ResponsiveSearchAdInfo"))
tenta("AdService.metodos", lambda: metodos("ad_service", "AdServiceClient"))
tenta("AdOperation", lambda: campos(f"{S}.ad_service", "AdOperation"))
tenta("AdGroupAdOperation", lambda: campos(f"{S}.ad_group_ad_service", "AdGroupAdOperation"))
tenta("AdGroupAd", lambda: campos(f"{R}.ad_group_ad", "AdGroupAd"))
tenta("CampaignAsset", lambda: campos(f"{R}.campaign_asset", "CampaignAsset"))
# Q8 placements
tenta("PerformanceMaxPlacementView", lambda: campos(f"{R}.performance_max_placement_view", "PerformanceMaxPlacementView"))
tenta("PlacementType", lambda: enum_vals("placement_type", "PlacementTypeEnum", "PlacementType"))
tenta("CustomerNegativeCriterion", lambda: campos(f"{R}.customer_negative_criterion", "CustomerNegativeCriterion"))
tenta("CampaignCriterion", lambda: campos(f"{R}.campaign_criterion", "CampaignCriterion"))
tenta("SharedSetType", lambda: enum_vals("shared_set_type", "SharedSetTypeEnum", "SharedSetType"))
tenta("SharedCriterion", lambda: campos(f"{R}.shared_criterion", "SharedCriterion"))
tenta("PlacementInfo", lambda: campos(f"{C}.criteria", "PlacementInfo"))
tenta("CriterionType", lambda: enum_vals("criterion_type", "CriterionTypeEnum", "CriterionType"))
tenta("CampaignCriterionError(placement)", lambda: [x for x in err_vals("campaign_criterion_error", "CampaignCriterionErrorEnum", "CampaignCriterionError") if any(k in x for k in ("PLACEMENT","PERFORMANCE_MAX","IP","EXCLU","NEGATIVE"))])
tenta("CustomerNegativeCriterion criterion oneof", lambda: [f for f in campos(f"{R}.customer_negative_criterion", "CustomerNegativeCriterion")])
# Q9 tCPA por grupo
tenta("AdGroup(lances)", lambda: [f for f in campos(f"{R}.ad_group", "AdGroup") if any(k in f for k in ("target","cpa","roas","bid","cpc","cpm","cpv","effective","percent"))])
tenta("MaximizeConversions", lambda: campos(f"{C}.bidding", "MaximizeConversions"))
tenta("BiddingSource", lambda: enum_vals("bidding_source", "BiddingSourceEnum", "BiddingSource"))
# Q10
tenta("AdGroupBidModifier", lambda: campos(f"{R}.ad_group_bid_modifier", "AdGroupBidModifier"))
tenta("CampaignBidModifier", lambda: campos(f"{R}.campaign_bid_modifier", "CampaignBidModifier"))
tenta("IpBlockInfo", lambda: campos(f"{C}.criteria", "IpBlockInfo"))
tenta("ConversionValueRule", lambda: campos(f"{R}.conversion_value_rule", "ConversionValueRule"))
tenta("ConversionValueRule.ValueRuleAction", lambda: list(importlib.import_module(f"{V}.{R}.conversion_value_rule").ConversionValueRule.ValueRuleAction.meta.fields.keys()))
tenta("ValueRuleOperation", lambda: enum_vals("value_rule_operation", "ValueRuleOperationEnum", "ValueRuleOperation"))
tenta("ConversionValueRuleSet", lambda: campos(f"{R}.conversion_value_rule_set", "ConversionValueRuleSet"))
tenta("ValueRuleSetDimension", lambda: enum_vals("value_rule_set_dimension", "ValueRuleSetDimensionEnum", "ValueRuleSetDimension"))
tenta("ConversionValueRuleError", lambda: err_vals("conversion_value_rule_error", "ConversionValueRuleErrorEnum", "ConversionValueRuleError"))

out["tipos"] = T
print(json.dumps(out, ensure_ascii=False, indent=1))
