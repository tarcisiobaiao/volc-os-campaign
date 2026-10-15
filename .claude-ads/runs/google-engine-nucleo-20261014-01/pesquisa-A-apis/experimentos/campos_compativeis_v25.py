"""Extrai, das páginas públicas de referência GAQL v25, os segmentos e métricas que podem
ser selecionados quando o recurso está no FROM (bloco "Yes, it is").
Sem credenciais. Lê HTML baixado previamente (não executa nada dele).

Reprodução:
  D=/caminho/scratch/fields; mkdir -p $D
  for r in performance_max_placement_view detail_placement_view group_placement_view \
           detail_content_suitability_placement_view group_content_suitability_placement_view \
           managed_placement_view ad_group_ad_asset_view asset_group_asset asset_group_top_combination_view \
           campaign_asset ad_group_asset keyword_view bidding_seasonality_adjustment experiment; do
     curl -s -o $D/$r.html https://developers.google.com/google-ads/api/fields/v25/$r; done
  python3 -I campos_compativeis_v25.py $D
"""
import html, json, re, sys
from pathlib import Path

d = Path(sys.argv[1])
saida = {}
for f in sorted(d.glob("*.html")):
    r = f.stem
    s = f.read_text(encoding="utf-8", errors="replace")
    i = s.find("<article")
    t = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s[i:])))
    m = re.search(r"info_outline(.*?)" + re.escape(r) + r"\.\w+ Field description", t)
    if not m:
        saida[r] = "BLOCO NAO ENCONTRADO"; continue
    bloco = m.group(1)
    seg = re.search(r"Segments (.*?) show_chart", bloco)
    met = re.search(r"Metrics (.*)$", bloco)
    rf = re.search(r"Resource fields (.*?) layers", bloco)
    desc = re.search(r"Proto definition (.*?) Attributed resources", t)
    saida[r] = {
        "descricao": desc.group(1).strip() if desc else None,
        "campos": rf.group(1).split() if rf else [],
        "segmentos": seg.group(1).split() if seg else [],
        "metricas": met.group(1).split() if met else [],
    }
print(json.dumps(saida, ensure_ascii=False, indent=1))
