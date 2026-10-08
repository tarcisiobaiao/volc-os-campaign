"""As CHECKs de `google_ads_fato_granular` (v17_01) em Python, para os testes.

Cópia deliberada e mínima do schema: se a migration mudar, estes testes têm
que ser lidos de novo — é o ponto.
"""
from __future__ import annotations

import re
from datetime import date

DIMENSOES = {
    "hora_dispositivo": ("hora", "dispositivo", "rede", "fuso"),
    "url": ("url", "url_tipo"),
    "geo": ("geo_constant", "geo_nivel", "local_tipo"),
    "placement": ("placement", "placement_tipo", "placement_view", "placement_nome"),
    "termo": ("termo", "termo_match", "termo_status"),
    "keyword": ("criterion_id", "keyword_texto", "keyword_match", "quality_score",
                "qs_anuncio", "qs_pagina", "qs_ctr_previsto"),
    "asset": ("asset_id", "asset_campo", "asset_contexto", "asset_contexto_id", "asset_rotulo"),
}
INTEIRAS = ("impressoes", "cliques", "interacoes", "custo_micros")
DECIMAIS = ("conversoes", "todas_conversoes", "valor_conversoes", "valor_todas_conversoes")
_ID = re.compile(r"^[0-9]{1,20}$")


def _vazio(texto) -> bool:
    return texto is None or not str(texto).strip()


def violacoes(familia: str, linha: dict) -> list[str]:
    erros = []
    g = linha.get
    if not isinstance(g("campaign_id"), str) or not _ID.match(g("campaign_id")):
        erros.append("campaign_id")
    try:
        date.fromisoformat(g("metric_date"))
    except (TypeError, ValueError):
        erros.append("metric_date")
    if not re.match(r"^[A-Z]{3}$", g("currency_code") or ""):
        erros.append("currency_code")
    if not g("colhida_em"):
        erros.append("colhida_em")
    for c in INTEIRAS:
        v = g(c)
        if v is not None and (type(v) is not int or v < 0):
            erros.append(c)
    for c in DECIMAIS:
        v = g(c)
        if v is not None and (type(v) not in (int, float) or v < 0):
            erros.append(c)
    if not isinstance(g("metricas_extras", {}), dict):
        erros.append("metricas_extras")
    for outra, colunas in DIMENSOES.items():
        if outra != familia:
            erros += [f"{c} (alheia)" for c in colunas if g(c) is not None]
    if g("ad_group_id") is not None and (familia not in ("termo", "keyword") or not _ID.match(g("ad_group_id"))):
        erros.append("ad_group_id")

    if familia == "hora_dispositivo":
        hora = g("hora")
        if (type(hora) is not int or not 0 <= hora <= 23
                or any(g(c) is None for c in ("dispositivo", "rede", "fuso"))):
            erros.append("dim_hora")
    elif familia == "url":
        if _vazio(g("url")) or g("url_tipo") not in ("final", "expandida"):
            erros.append("dim_url")
    elif familia == "geo":
        if (not re.fullmatch(r"geoTargetConstants/[0-9]+", g("geo_constant") or "")
                or g("local_tipo") not in ("area_de_interesse", "localizacao_fisica")):
            erros.append("dim_geo")
    elif familia == "placement":
        if _vazio(g("placement")) or g("placement_view") not in ("detail", "group", "pmax"):
            erros.append("dim_placement")
    elif familia == "termo":
        if _vazio(g("termo")):
            erros.append("dim_termo")
    elif familia == "keyword":
        qs = g("quality_score")
        if (not _ID.match(g("ad_group_id") or "") or not _ID.match(g("criterion_id") or "")
                or g("keyword_texto") is None
                or (qs is not None and (type(qs) is not int or not 1 <= qs <= 10))):
            erros.append("dim_keyword")
    elif familia == "asset":
        if (not _ID.match(g("asset_id") or "") or g("asset_campo") is None
                or g("asset_contexto") not in ("ad_group", "asset_group", "campanha")
                or g("asset_contexto_id") is None):
            erros.append("dim_asset")
    return erros
