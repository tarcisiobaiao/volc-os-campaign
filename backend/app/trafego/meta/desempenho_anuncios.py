"""Métricas observadas por anúncio, nunca rateio de gasto/receita do conjunto.

Chamado somente após resolver campanha dentro da conta. A cadeia persistida
campanha -> conjunto -> anúncio limita a consulta; nomes não são identidade.
Uma janela sem todos os dias medidos permanece indisponível, não zero.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from . import dominio as dom

_PAGINA = 500  # abaixo do teto real de 1000 do PostgREST
_MAX_PAGINAS = 20
_METRICAS = ("spend", "impressions", "clicks", "ctr", "cpc", "cpm")


def indisponivel(codigo: str) -> dict:
    return {"anuncios": [], "anuncios_completo": False,
            "anuncios_impedimentos": [codigo]}


def _numero(valor: Any, *, inteiro: bool = False) -> Decimal:
    if valor is None or isinstance(valor, bool):
        raise ValueError("métrica ausente")
    numero = Decimal(str(valor))
    if not numero.is_finite() or numero < 0 or (inteiro and numero != numero.to_integral_value()):
        raise ValueError("métrica inválida")
    return numero


async def ler_desempenho_anuncios(repo: Any, contexto: dict, campanha_id: str,
                                  inicio: date, fim: date) -> dict:
    conjuntos, pronto = await repo._select_seguro("trafego_meta_adset", {
        "select": "meta_adset_id,meta_campaign_id,external_id",
        "meta_campaign_id": f"eq.{campanha_id}", "order": "meta_adset_id.asc", "limit": 201})
    if not pronto or len(conjuntos) > 200:
        return indisponivel("ANUNCIOS_ESCOPO_DE_CONJUNTOS_INCOMPLETO")
    pais = {}
    externos = set()
    for row in conjuntos:
        pk, externo = str(row.get("meta_adset_id", "")), str(row.get("external_id", ""))
        if (row.get("meta_campaign_id") != campanha_id or not re.fullmatch(r"[\w-]+", pk)
                or not re.fullmatch(r"\d{1,40}", externo) or pk in pais or externo in externos):
            return indisponivel("ANUNCIOS_PARENTESCO_INVALIDO")
        pais[pk] = externo
        externos.add(externo)
    if not pais:
        return indisponivel("ANUNCIOS_SEM_CONJUNTOS_CONHECIDOS")
    anuncios, pronto = await repo._select_seguro("trafego_meta_ad", {
        "select": "meta_ad_id,meta_adset_id,external_id",
        "meta_adset_id": "in.(" + ",".join(sorted(pais)) + ")",
        "order": "meta_ad_id.asc", "limit": 501})
    if not pronto or len(anuncios) > 500:
        return indisponivel("ANUNCIOS_INVENTARIO_INCOMPLETO")
    ads, ids = {}, set()
    for row in anuncios:
        externo, pk = str(row.get("external_id", "")), row.get("meta_ad_id")
        if (row.get("meta_adset_id") not in pais or not pk or pk in ids
                or not re.fullmatch(r"\d{1,40}", externo) or externo in ads):
            return indisponivel("ANUNCIOS_PARENTESCO_INVALIDO")
        ads[externo] = row
        ids.add(pk)
    if not ads:
        return indisponivel("ANUNCIOS_SEM_INVENTARIO")

    por_grao = {}
    leitura_completa = False
    falhas = set()
    for pagina in range(_MAX_PAGINAS):
        params = {
            "select": "*", "ad_account_ativo_id": f"eq.{contexto['ativo_id']}",
            "provider": "eq.META_ADS", "nivel": "eq.ad",
            "objeto_externo": "in.(" + ",".join(sorted(ads)) + ")",
            "breakdown": "eq.none", "time_increment": "eq.1",
            "action_report_time": "eq.impression", "janela_atribuicao": "eq.default",
            "periodo_inicio": f"gte.{inicio}", "periodo_fim": f"lte.{fim}",
            "order": "objeto_externo.asc,periodo_inicio.asc,meta_insight_daily_id.asc",
            "limit": _PAGINA,
        }
        if pagina:
            params["offset"] = pagina * _PAGINA
        linhas, pronto = await repo._select_seguro("vw_trafego_meta_insight_latest", params)
        if not pronto:
            falhas.add("ANUNCIOS_LEITURA_INDISPONIVEL")
            break
        for row in linhas:
            externo, dia = str(row.get("objeto_externo")), str(row.get("periodo_inicio"))
            # Defesa adicional contra view/schema incorretos, mesmo com filtros.
            if (externo not in ads or row.get("ad_account_ativo_id") != contexto['ativo_id']
                    or row.get("provider") != "META_ADS" or row.get("nivel") != "ad"
                    or not inicio.isoformat() <= dia <= fim.isoformat()
                    or row.get("periodo_fim") != dia or row.get("breakdown") != "none"
                    or str(row.get("time_increment")) != "1"
                    or row.get("action_report_time") != "impression"
                    or row.get("janela_atribuicao") != "default"):
                return indisponivel("ANUNCIOS_GRAO_FORA_DO_ESCOPO")
            chave = externo, dia
            if chave in por_grao:
                return indisponivel("ANUNCIOS_INSIGHT_DUPLICADO")
            por_grao[chave] = row
        if len(linhas) < _PAGINA:
            leitura_completa = True
            break
    if not leitura_completa and not falhas:
        falhas.add("ANUNCIOS_INSIGHTS_TRUNCADOS")

    dias = [(inicio + timedelta(days=n)).isoformat() for n in range((fim - inicio).days + 1)]
    resultado = []
    for externo, ad in sorted(ads.items()):
        item = {"ad_ref": dom.referencia_opaca_objeto(contexto['conta_externa'], "ad", externo),
                "adset_ref": dom.referencia_opaca_objeto(contexto['conta_externa'], "adset", pais[ad['meta_adset_id']]),
                **dict.fromkeys(_METRICAS), "source_freshness": None, "completo": False}
        linhas = [por_grao.get((externo, dia)) for dia in dias]
        if (not leitura_completa or not contexto.get("moeda") or not contexto.get("fuso")
                or any(r is None or r.get("completo") is not True
                       or r.get("currency") != contexto['moeda']
                       or r.get("account_timezone") != contexto['fuso'] for r in linhas)):
            falhas.add("ANUNCIOS_DIAS_AUSENTES_PARCIAIS_OU_INCOMPATIVEIS")
        else:
            try:
                spend = sum((_numero(r.get("spend")) for r in linhas), Decimal(0))
                imp = sum((_numero(r.get("impressions"), inteiro=True) for r in linhas), Decimal(0))
                clicks = sum((_numero(r.get("clicks"), inteiro=True) for r in linhas), Decimal(0))
                observacoes = [datetime.fromisoformat(str(r.get("observado_em")).replace("Z", "+00:00")) for r in linhas]
                if any(d.tzinfo is None for d in observacoes):
                    raise ValueError("frescor sem fuso")
                item.update(spend=str(spend), impressions=int(imp), clicks=int(clicks),
                            ctr=str(clicks / imp * 100) if imp else None,
                            cpc=str(spend / clicks) if clicks else None,
                            cpm=str(spend / imp * 1000) if imp else None,
                            source_freshness=min(observacoes).astimezone(timezone.utc).isoformat(), completo=True)
            except (ValueError, InvalidOperation, TypeError, OverflowError):
                falhas.add("ANUNCIOS_METRICAS_OU_FRESCOR_INVALIDOS")
        resultado.append(item)
    return {"anuncios": resultado, "anuncios_completo": not falhas and all(r['completo'] for r in resultado),
            "anuncios_impedimentos": sorted(falhas)}
