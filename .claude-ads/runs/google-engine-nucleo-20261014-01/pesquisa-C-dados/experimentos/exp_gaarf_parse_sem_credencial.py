"""Experimento C/gaarf: parse de GAQL com macros/templates e parse de GoogleAdsRow
FABRICADA (sem credencial, sem rede). Rodar com:
  HOME=<dir vazio> GOOGLE_ADS_CONFIGURATION_FILE_PATH=/nonexistent \
  venv-gaarf/bin/python -I exp_gaarf_parse_sem_credencial.py <catalogo_gaql_v25.json>
Não cria GoogleAdsClient; não lê google-ads.yaml.
"""
import json, sys, warnings, importlib, time
warnings.simplefilter("ignore")
t0 = time.perf_counter()
from garf.community.google.ads import query_editor, parsers  # noqa: E402
from garf.core import report  # noqa: E402
import google.ads.googleads.client as gc  # noqa: E402

cat = json.load(open(sys.argv[1]))["campos"]
out = {"google_ads_default_version_no_sdk": gc._DEFAULT_VERSION,
       "parser_module_version": parsers.__name__}

# 1) query de política do ads-policy-monitor (template {{ today }} + extrator :topic) e
#    query de placement com macro {start_date}/{end_date} no estilo do APG.
QUERIES = {
 "policy_ad": """SELECT
  '{{ today }}' AS event_date,
  customer.id,
  ad_group_ad.ad.id,
  ad_group_ad.policy_summary.approval_status AS approval,
  ad_group_ad.policy_summary.review_status AS review,
  ad_group_ad.policy_summary.policy_topic_entries:topic AS topics,
  metrics.impressions AS impressions
FROM ad_group_ad
WHERE ad_group_ad.policy_summary.approval_status != 'APPROVED'
  AND segments.date DURING LAST_30_DAYS""",
 "placement_macro": """SELECT
  campaign.id,
  campaign.advertising_channel_type AS campaign_type,
  group_placement_view.placement AS placement,
  group_placement_view.placement_type AS placement_type,
  metrics.cost_micros / 1e6 AS cost
FROM group_placement_view
WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
  AND metrics.impressions > 0""",
}
args = {"macro": {"start_date": ":YYYYMMDD-7", "end_date": ":YYYYMMDD-1"},
        "template": {"today": "2026-10-14"}}
specs = {}
for nome, q in QUERIES.items():
    spec = query_editor.GoogleAdsApiQuery(text=q, title=nome, args=args).generate()
    specs[nome] = spec
    campos = [f.replace(".type_", ".type") for f in spec.fields]
    out[nome] = {
        "gaql_enviada": spec.text,
        "fields": spec.fields,
        "column_names": spec.column_names,
        "customizers": {k: v.model_dump() if hasattr(v, "model_dump") else str(v) for k, v in spec.customizers.items()},
        "virtual_columns": {k: str(v) for k, v in spec.virtual_columns.items()},
        "campos_fora_do_catalogo_v25_volc": [c for c in campos if c not in cat or not cat[c][1]],
    }

# 2) GoogleAdsRow fabricada (v25) -> parser do garf -> GarfReport
gas = importlib.import_module("google.ads.googleads.v25.services.types.google_ads_service")
pol = importlib.import_module("google.ads.googleads.v25.common.types.policy")
en_app = importlib.import_module("google.ads.googleads.v25.enums.types.policy_approval_status")
en_rev = importlib.import_module("google.ads.googleads.v25.enums.types.policy_review_status")
en_tt = importlib.import_module("google.ads.googleads.v25.enums.types.policy_topic_entry_type")
row = gas.GoogleAdsRow()
row.customer.id = 1234567890
row.ad_group_ad.ad.id = 42
row.ad_group_ad.policy_summary.approval_status = en_app.PolicyApprovalStatusEnum.PolicyApprovalStatus.APPROVED_LIMITED
row.ad_group_ad.policy_summary.review_status = en_rev.PolicyReviewStatusEnum.PolicyReviewStatus.REVIEWED
e = pol.PolicyTopicEntry(topic="TRADEMARKS_IN_AD_TEXT", type_=en_tt.PolicyTopicEntryTypeEnum.PolicyTopicEntryType.LIMITED)
e.constraints.append(pol.PolicyTopicConstraint(country_constraint_list=pol.PolicyTopicConstraint.CountryConstraintList(total_targeted_countries=1)))
row.ad_group_ad.policy_summary.policy_topic_entries.append(e)
row.metrics.impressions = 0
spec = specs["policy_ad"]
try:
    p = parsers.GoogleAdsRowParser(spec)
    linhas = [p.parse_row(row)]
    rep = report.GarfReport(results=linhas, column_names=[c for c in spec.column_names if c != "_"], query_specification=spec)
    out["report_fabricado"] = {"colunas": rep.column_names, "linhas": [list(map(str, r)) for r in rep.results],
                               "observacao": "':topic' descarta type/constraints/evidences; só o tópico sobra"}
except Exception as ex:  # registro honesto
    out["report_fabricado_erro"] = f"{type(ex).__name__}: {ex}"
out["segundos"] = round(time.perf_counter() - t0, 2)
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
