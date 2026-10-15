"""Extrai GAQL de repositórios Google clonados (texto VERBATIM por faixa de linhas)
e confere cada campo contra o catálogo v25 do VOLC (somente leitura).

Uso: python3 -I extrair_queries.py <dir_clones> <catalogo_gaql_v25.json> <dir_saida>
Não executa código dos repositórios: só lê arquivos como texto.
"""
import json, re, subprocess, sys
from pathlib import Path

CL, CAT, OUT = Path(sys.argv[1]), json.load(open(sys.argv[2]))["campos"], Path(sys.argv[3])

# (grupo, repo, arquivo, linha_ini, linha_fim)  — faixas conferidas à mão com cat -n
FONTES = [
 ("policy", "ads-policy-monitor", "cloud_functions/ads_policy_monitor/gaql/ad_policy_data.sql", 14, 41),
 ("policy", "ads-policy-monitor", "cloud_functions/ads_policy_monitor/gaql/ad_group_asset.sql", 14, 37),
 ("policy", "ads-policy-monitor", "cloud_functions/ads_policy_monitor/gaql/campaign_asset.sql", 14, 34),
 ("policy", "ads-policy-monitor", "cloud_functions/ads_policy_monitor/gaql/customer_asset.sql", 14, 29),
 ("placements", "ads_placement_guardian", "libs/ads_housekeeper/googleads_housekeeper/domain/placement_handler/entities.py", 50, 72),
 ("placements", "ads_placement_guardian", "libs/ads_housekeeper/googleads_housekeeper/domain/placement_handler/entities.py", 247, 264),
 ("placements", "ads_placement_guardian", "libs/ads_housekeeper/googleads_housekeeper/domain/placement_handler/entities.py", 343, 355),
 ("placements", "video-exclusion-toolbox", "src/gads_channel_report_fetcher/main.py", 86, 110),
 ("placements", "video-exclusion-toolbox", "src/gads_video_report_fetcher/main.py", 86, 116),
 ("placements", "pmax_best_practices_dashboard", "google_ads_queries/pmax_placement_view.sql", 15, 32),
 ("qs", "arba", "queries/ads/keyword_performance.sql", 1, 40),
 ("qs", "arba", "queries/ads/speed_score.sql", 1, 40),
 ("assets", "dgpulse", "google_ads_queries/adgroupad_asset_view.sql", 21, 40),
 ("assets", "dgpulse", "google_ads_queries/ad_group_ad.sql", 20, 45),
 ("assets", "pmax_best_practices_dashboard", "google_ads_queries/assetgroupsignal.sql", 15, 22),
 ("assets", "pmax_best_practices_dashboard", "google_ads_queries/ad_group_asset.sql", 15, 21),
 ("negativas", "negative_keyword_cleaner", "src/utils/gaarf_queries.py", 43, 190),
]
CAMPO = re.compile(r"\b((?:ad_group_ad_asset_view|ad_group_ad|ad_group_asset|ad_group_criterion|ad_group|asset_group_asset|asset_group_signal|asset_group|asset|campaign_asset|campaign_criterion|campaign|customer_asset|customer_client|customer_negative_criterion|customer|detail_placement_view|group_placement_view|performance_max_placement_view|keyword_view|landing_page_view|metrics|segments|shared_criterion|shared_set)\.[a-z_][a-z0-9_.]*)")

def sha(repo):
    return subprocess.run(["git", "-C", str(CL / repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

res = []
por_grupo = {}
for grupo, repo, arq, a, b in FONTES:
    linhas = (CL / repo / arq).read_text(encoding="utf-8").splitlines()
    b = min(b, len(linhas))
    texto = "\n".join(linhas[a - 1:b])
    campos = sorted({m.rstrip(".") for m in CAMPO.findall(texto)})
    # `{placement_level_granularity}`/`{criterion_resource_name}` são templates do APG
    conferencia = {}
    for c in campos:
        base = c.split(":")[0]
        if base.endswith(".type"):
            pass
        info = CAT.get(base)
        conferencia[base] = ("ausente_no_catalogo_v25" if info is None else
                             f"{info[0]}|selecionavel={info[1]}|filtravel={info[2]}")
    origem = f"google-marketing-solutions/{repo}@{sha(repo)}:{arq}:{a}-{b}"
    res.append({"grupo": grupo, "origem": origem, "campos_catalogo_v25": conferencia,
                "ausentes": [k for k, v in conferencia.items() if v.startswith("ausente")]})
    por_grupo.setdefault(grupo, []).append((origem, texto, conferencia))

OUT.mkdir(parents=True, exist_ok=True)
for grupo, itens in por_grupo.items():
    with open(OUT / f"{grupo}-extraidas.sql", "w", encoding="utf-8") as f:
        f.write(f"-- GAQL extraídas VERBATIM (sintaxe gaarf: AS alias, :campo aninhado, ~N, {{macro}}).\n"
                f"-- Data 2026-10-14. Conferência: catálogo do servidor v25 do VOLC (volc_ads/google_ads_api/catalogo_gaql_v25.json).\n"
                f"-- O catálogo NÃO tem selectable_with: compatibilidade campo×FROM só se prova com validate_only (pesquisador A).\n\n")
        for origem, texto, conf in itens:
            f.write(f"-- ===== ORIGEM: {origem}\n")
            ruins = [k for k, v in conf.items() if v.startswith("ausente")]
            f.write(f"-- campos fora do catálogo v25: {ruins or 'nenhum'}\n")
            f.write(texto + "\n\n")
json.dump(res, open(OUT / "conferencia_catalogo_v25.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps([{k: r[k] for k in ("grupo", "origem", "ausentes")} for r in res], ensure_ascii=False, indent=1))
