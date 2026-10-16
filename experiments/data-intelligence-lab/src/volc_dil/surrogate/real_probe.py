"""Sonda somente leitura dos dois únicos conjuntos versionados com rótulo econômico real.

- Senac shadow (1 campanha Google × dia; custo Google + receita JoinAds);
- golden Meta×GAM (campanha/dia pseudonimizado; o conjunto/dia é RATEIO — volta-se
  ao grão campanha/dia somando o rateio, que preserva a soma exata por construção).

Nenhum valor monetário individual é impresso ou gravado: só contagens e métricas.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from .feasibility import Feature, LinhaRotulada

SENAC = Path("backend/app/trafego/shadow_experimentos/senac-shadow-20261015/transformacao.csv")
GOLDEN_META = Path("backend/tests/goldens/atribuicao-meta-adset-v1.json")


def carregar_senac(raiz: Path) -> list[LinhaRotulada]:
    linhas = []
    with open(raiz / SENAC, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            reconciliado = r["estado"] == "reconciliado" and r["maduro"] == "True"
            rot = float(Decimal(r["revenue_usd"])) if reconciliado and r["revenue_usd"] not in ("", "None") else None
            def num(v):  # null != 0: campo vazio vira None, não 0
                return None if v in ("", "None", None) else float(Decimal(v))
            linhas.append(LinhaRotulada(
                unidade_id="senac-campanha-1", periodo=date.fromisoformat(r["date"]), grao="campaign_day",
                rotulo=rot, rotulo_maduro=r["maduro"] == "True", origem_rotulo="joinads",
                features={
                    "clicks": Feature(num(r["clicks"]), "google_ads"),
                    "custo": Feature(num(r["custo_brl"]), "google_ads"),
                    "valor_conversao_google": Feature(num(r["valor_conversao_google"]), "google_ads_conversion"),
                },
            ))
    return linhas


def carregar_golden_meta(raiz: Path) -> list[LinhaRotulada]:
    d = json.loads((raiz / GOLDEN_META).read_text(encoding="utf-8"))
    acc: dict[tuple, dict] = defaultdict(lambda: {"spend": Decimal(0), "impressions": 0, "clicks": 0, "gam_imp": 0,
                                                   "gam_clicks": 0, "rev": Decimal(0), "rev_nulo": False,
                                                   "sem_utm": False})
    for l in d["linhas"]:
        k = (l["campaign_id"], l["date"])
        a = acc[k]
        a["spend"] += Decimal(l["spend"])
        a["impressions"] += l["impressions"]
        a["clicks"] += l["clicks"]
        a["gam_imp"] += l["gam_impressions"] or 0
        a["gam_clicks"] += l["gam_clicks"] or 0
        if l["gam_revenue_original"] is None:
            a["rev_nulo"] = True
        else:
            a["rev"] += Decimal(l["gam_revenue_original"])
        if l["status_origem"] != "FATURAMENTO_ATRIBUIDO_VIA_ADSET":
            a["sem_utm"] = True
    linhas = []
    for (cid, dia), a in sorted(acc.items()):
        rot = None if (a["rev_nulo"] or a["sem_utm"]) else float(a["rev"])
        linhas.append(LinhaRotulada(
            unidade_id=cid, periodo=date.fromisoformat(dia), grao="campaign_day", rotulo=rot,
            # o golden não declara maturidade por linha: assumimos maduro (otimista para o veredito)
            rotulo_maduro=True, origem_rotulo="gam",
            features={
                "meta_spend": Feature(float(a["spend"]), "meta"),
                "meta_impressions": Feature(float(a["impressions"]), "meta"),
                "meta_clicks": Feature(float(a["clicks"]), "meta"),
                "gam_impressions": Feature(float(a["gam_imp"]), "gam"),  # mesma fonte da receita
                "gam_clicks": Feature(float(a["gam_clicks"]), "gam"),
            },
        ))
    return linhas
