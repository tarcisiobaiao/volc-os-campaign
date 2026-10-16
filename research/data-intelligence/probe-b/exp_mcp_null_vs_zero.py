# Experimento hermético: sem credencial, sem rede. Linha fabricada sem métricas.
import json, importlib
from google.ads.googleads.v23.services.types.google_ads_service import GoogleAdsRow
from ads_mcp import utils
row = GoogleAdsRow()
row.campaign.id = 123
paths = ["campaign.id", "metrics.impressions", "metrics.cost_micros", "ad_group_criterion.quality_info.quality_score"]
out = utils.format_output_row(row, paths)
print(json.dumps({"saida_mcp": out, "impressions_presente_no_proto": "impressions" in row.metrics, "quality_score_presente": "quality_score" in row.ad_group_criterion.quality_info}))
