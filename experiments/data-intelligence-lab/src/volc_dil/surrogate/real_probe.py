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
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .feasibility import Feature, LinhaRotulada


def _d1(dia: date) -> datetime:
    """Disponibilidade DECLARADA (não medida) de relatório diário de mídia: fim do dia + 1 dia."""
    return datetime(dia.year, dia.month, dia.day, tzinfo=timezone.utc) + timedelta(days=2)

SENAC = Path("backend/app/trafego/shadow_experimentos/senac-shadow-20261015/transformacao.csv")
GOLDEN_META = Path("backend/tests/goldens/atribuicao-meta-adset-v1.json")


def carregar_senac(raiz: Path) -> list[LinhaRotulada]:
    linhas = []
    with open(raiz / SENAC, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            reconciliado = r["estado"] == "reconciliado" and r["maduro"] == "True"
            bruto = r["revenue_usd"]
            rot = float(Decimal(bruto)) if reconciliado and bruto not in ("", "None") else None
            # A fonte JoinAds legada tem `revenue DEFAULT 0`: 0,00 não distingue "medido zero" de
            # "não veio" (o próprio resultado.json da fonte avisa). Zero vira ambíguo, não rótulo (F1-11).
            zero_ambiguo = rot == 0.0
            if zero_ambiguo:
                rot = None
            def num(v):  # null != 0: campo vazio vira None, não 0
                return None if v in ("", "None", None) else float(Decimal(v))
            dia = date.fromisoformat(r["date"])
            linhas.append(LinhaRotulada(
                unidade_id="senac-campanha-1", periodo=dia, grao="campaign_day",
                rotulo=rot, rotulo_maduro=r["maduro"] == "True", origem_rotulo="joinads",
                features={
                    "clicks": Feature(num(r["clicks"]), "google_ads", _d1(dia)),
                    "custo": Feature(num(r["custo_brl"]), "google_ads", _d1(dia)),
                    "valor_conversao_google": Feature(num(r["valor_conversao_google"]), "google_ads_conversion", _d1(dia)),
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
        # null != 0: um nulo torna a soma desconhecida (F1-11)
        for campo, chave in (("gam_impressions", "gam_imp"), ("gam_clicks", "gam_clicks")):
            if l[campo] is None or a[chave] is None:
                a[chave] = None
            else:
                a[chave] += l[campo]
        if l["gam_revenue_original"] is None:
            a["rev_nulo"] = True
        else:
            a["rev"] += Decimal(l["gam_revenue_original"])
        if l["status_origem"] != "FATURAMENTO_ATRIBUIDO_VIA_ADSET":
            a["sem_utm"] = True
    linhas = []
    for (cid, dia), a in sorted(acc.items()):
        rot = None if (a["rev_nulo"] or a["sem_utm"]) else float(a["rev"])
        d = date.fromisoformat(dia)
        linhas.append(LinhaRotulada(
            unidade_id=cid, periodo=d, grao="campaign_day", rotulo=rot,
            # o golden não declara maturidade por linha: assumimos maduro (otimista para o veredito)
            rotulo_maduro=True, origem_rotulo="gam",
            features={
                "meta_spend": Feature(float(a["spend"]), "meta", _d1(d)),
                "meta_impressions": Feature(float(a["impressions"]), "meta", _d1(d)),
                "meta_clicks": Feature(float(a["clicks"]), "meta", _d1(d)),
                # mesma fonte da receita: circulares
                "gam_impressions": Feature(None if a["gam_imp"] is None else float(a["gam_imp"]), "gam", _d1(d)),
                "gam_clicks": Feature(None if a["gam_clicks"] is None else float(a["gam_clicks"]), "gam", _d1(d)),
            },
        ))
    return linhas


def contar_zeros_ambiguos_senac(raiz: Path) -> int:
    """Dias reconciliados e maduros com receita 0,00 — ambíguos por causa do DEFAULT 0 da fonte."""
    with open(raiz / SENAC, newline="", encoding="utf-8") as f:
        return sum(1 for r in csv.DictReader(f)
                   if r["estado"] == "reconciliado" and r["maduro"] == "True"
                   and r["revenue_usd"] not in ("", "None") and Decimal(r["revenue_usd"]) == 0)
