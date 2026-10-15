"""garf: campo ausente vira 0 ou None? (contrato VOLC: métrica ausente = None, nunca 0).
GoogleAdsRow fabricada sem quality_score e sem metrics.impressions; sem credencial/rede."""
import importlib, json, warnings
warnings.simplefilter("ignore")
from garf.community.google.ads import query_editor, parsers
q = ("SELECT ad_group_criterion.criterion_id, ad_group_criterion.quality_info.quality_score AS qs, "
     "metrics.impressions AS imp, metrics.historical_quality_score AS hqs FROM keyword_view")
spec = query_editor.GoogleAdsApiQuery(text=q).generate()
gas = importlib.import_module("google.ads.googleads.v25.services.types.google_ads_service")
row = gas.GoogleAdsRow(); row.ad_group_criterion.criterion_id = 7  # nada mais preenchido
linha = parsers.GoogleAdsRowParser(spec).parse_row(row)
volc = {"qs": None, "imp": None, "hqs": None}
print(json.dumps({"colunas": spec.column_names, "garf": linha,
                  "presenca_proto": {"quality_score": "quality_score" in row.ad_group_criterion.quality_info,
                                     "impressions": "impressions" in row.metrics},
                  "volc_contrato_esperado": volc}, default=str))
