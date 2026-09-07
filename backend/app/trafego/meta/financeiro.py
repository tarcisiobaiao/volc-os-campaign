"""Leitura financeira Meta + GAM, sem consultar provedores ou escrever dados.

GAM.utm_campaign_value = Meta campaign_id (decisão do operador 2026-09-07).
O ID bruto é resolvido no servidor; projeto/conta GAM vêm de vínculos persistidos.
Não somamos níveis, revisões, janelas de atribuição ou moedas diferentes.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import dominio as dom


def _numero(valor: Any) -> Decimal | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = Decimal(str(valor))
        return numero if numero.is_finite() else None
    except InvalidOperation:
        return None


def _soma_completa(rows: list[Mapping], campo: str) -> Decimal | None:
    valores = [_numero(r.get(campo)) for r in rows]
    if not valores or any(v is None or v < 0 for v in valores):
        return None
    return sum(valores, Decimal(0))


def _contrato_gam(gam_id: str) -> dict | None:
    """Metadados NÃO secretos, confirmados do relatório, nunca FX presumido.

    Ex.: META_GAM_REPORTING_CONTRACT_JSON={"<gam_accounts.id>":
      {"currency":"BRL","timezone":"America/Sao_Paulo",
       "revenue_column":"revenue_converted"}}
    Ausência mantém gasto disponível e receita explicitamente bloqueada.
    """
    try:
        cfg = json.loads(os.environ.get("META_GAM_REPORTING_CONTRACT_JSON", "{}"))[gam_id]
        if (not isinstance(cfg, dict)
                or not re.fullmatch(r"[A-Z]{3}", str(cfg.get("currency", "")))
                or cfg.get("revenue_column") not in {"revenue", "revenue_converted"}):
            return None
        ZoneInfo(cfg["timezone"])
        return cfg
    except (ValueError, TypeError, KeyError, ZoneInfoNotFoundError):
        return None


async def ler_financeiro(repo: Any, referencia: str, conta_ref: str,
                         inicio: date | None, fim: date | None) -> dict:
    vazio: dict[str, Any] = {
        "ok": True, "provider": "META_ADS", "conta_ref": conta_ref,
        "campanha_ref": referencia, "estado": "SEM_SNAPSHOT",
        "currency": None, "timezone": None, "periodo_inicio": None,
        "periodo_fim": None, "provisorio": False, "frescor": None,
        "spend": None, "revenue": None, "profit_gross": None,
        "roas_ratio": None, "retorno_excedente_pct": None,
        "impressions": None, "clicks": None, "ctr": None, "cpc": None,
        "spend_completo": False, "revenue_completo": False,
        "fontes": {"spend": "Meta Insights · campaign · latest",
                   "revenue": "GAM · utm_campaign_value = campaign_id"},
        "impedimentos": [],
    }

    def bloquear(codigo: str) -> dict:
        vazio["impedimentos"].append(codigo)
        return vazio

    if not getattr(repo._supa, "enabled", False):
        vazio["estado"] = "SEM_CONEXAO"
        return bloquear("SUPABASE_INDISPONIVEL")
    contexto = await repo._contexto_da_conta(conta_ref)
    if contexto is None:
        return bloquear("CONTA_NAO_RESOLVIDA")
    vazio.update(currency=contexto.get("moeda"), timezone=contexto.get("fuso"))
    try:
        hoje = dom.hoje_na_conta(contexto.get("fuso"))
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return bloquear("FUSO_META_NAO_CONFIRMADO")
    inicio, fim = inicio or hoje - timedelta(days=1), fim or hoje - timedelta(days=1)
    if fim < inicio or (fim - inicio).days > 91 or fim > hoje:
        raise dom.ContratoMetaInvalido("período deve conter de 1 a 92 dias, sem datas futuras")
    dias = {(inicio + timedelta(days=i)).isoformat() for i in range((fim - inicio).days + 1)}
    vazio.update(periodo_inicio=inicio.isoformat(), periodo_fim=fim.isoformat(), provisorio=fim == hoje)
    # Caminhada paginada em conta: não transformamos o teto HTTP de 500 em
    # "campanha inexistente". A referência nunca vira filtro externo arbitrário.
    cursor, campanha = None, None
    for _ in range(20):
        pagina = await repo.listar("campanhas", conta_ref, tamanho=500, cursor=cursor)
        item = next((r for r in pagina["items"]
                     if referencia in {r.get("entity_ref"), r.get("meta_campaign_id")}), None)
        if item:
            campanha = item
            break
        cursor = pagina.get("proximo_cursor")
        if not cursor:
            break
    if not campanha:
        return bloquear("CAMPANHA_NAO_RESOLVIDA_NO_ESCOPO")
    rows, pronto = await repo._select_seguro("trafego_meta_campaign", {
        "select": "external_id", "ad_account_ativo_id": f"eq.{contexto['ativo_id']}",
        "meta_campaign_id": f"eq.{campanha['meta_campaign_id']}", "limit": 2})
    if not pronto or len(rows) != 1 or not re.fullmatch(r"\d{1,40}", str(rows[0].get("external_id", ""))):
        return bloquear("IDENTIDADE_META_NAO_CONFIRMADA")
    campaign_id = str(rows[0]["external_id"])
    # Uma única semântica de relatório. Não somar default e 7d_click do mesmo dia.
    insights, pronto = await repo._select_seguro("vw_trafego_meta_insight_latest", {
        "select": "*", "ad_account_ativo_id": f"eq.{contexto['ativo_id']}",
        "provider": "eq.META_ADS", "nivel": "eq.campaign", "objeto_externo": f"eq.{campaign_id}",
        "breakdown": "eq.none", "time_increment": "eq.1", "action_report_time": "eq.impression",
        "janela_atribuicao": "eq.default", "periodo_inicio": f"gte.{inicio}",
        "periodo_fim": f"lte.{fim}", "order": "periodo_inicio.asc", "limit": 94})
    completo = (pronto and len(insights) == len(dias)
                and {str(r.get("periodo_inicio")) for r in insights} == dias
                and all(str(r.get("periodo_fim")) == str(r.get("periodo_inicio"))
                        and r.get("completo") is True and r.get("currency") == vazio["currency"]
                        and r.get("account_timezone") == vazio["timezone"] for r in insights)
                and bool(vazio["currency"]))
    if completo:
        vazio["spend_completo"] = True
        for campo in ("spend", "impressions", "clicks"):
            vazio[campo] = _soma_completa(insights, campo)
        if vazio["spend"] is None:
            vazio["spend_completo"] = False
            bloquear("SPEND_NULO_OU_INVALIDO")
        imp, clicks, spend = vazio["impressions"], vazio["clicks"], vazio["spend"]
        vazio["ctr"] = clicks / imp * 100 if imp and clicks is not None else None
        vazio["cpc"] = spend / clicks if clicks and spend is not None else None
        vazio["frescor"] = min(str(r.get("observado_em") or "") for r in insights) or None
    else:
        bloquear("INSIGHTS_DIARIOS_AUSENTES_PARCIAIS_OU_INCOMPATIVEIS")
    vazio["estado"] = "COM_SNAPSHOT" if insights else "SEM_SNAPSHOT"

    # GAM vem exclusivamente da conta GAM do projeto confirmado, nunca de
    # daily_campaign_metrics (tabela legada Google sem namespace Meta).
    bindings, pronto = await repo._select_seguro("trafego_meta_project_binding", {
        "select": "project_id", "ad_account_ativo_id": f"eq.{contexto['ativo_id']}",
        "desfeito_em": "is.null", "limit": 2})
    if not pronto or len(bindings) != 1:
        return bloquear("VINCULO_PROJETO_META_NAO_CONFIRMADO")
    project_id = bindings[0].get("project_id")
    if not isinstance(project_id, int) or isinstance(project_id, bool) or project_id < 1:
        return bloquear("VINCULO_PROJETO_META_INVALIDO")
    contas_gam, pronto = await repo._select_seguro("gam_accounts", {
        "select": "id", "project_id": f"eq.{project_id}", "limit": 2})
    if not pronto or len(contas_gam) != 1 or not str(contas_gam[0].get("id", "")).isdigit():
        return bloquear("CONTA_GAM_DO_PROJETO_NAO_UNIVOCA")
    gam_id = str(contas_gam[0]["id"])
    cfg = _contrato_gam(gam_id)
    if cfg is None:
        return bloquear("MOEDA_FUSO_COLUNA_GAM_NAO_CONFIRMADOS")
    if cfg["currency"] != vazio["currency"] or cfg["timezone"] != vazio["timezone"]:
        return bloquear("GAM_META_MOEDA_OU_FUSO_DIVERGENTE")
    # O coletor legado GAM não grava rede compradora. Colisão detectada ou
    # catálogo indisponível impede atribuição (não adivinhar Google vs Meta).
    google, pronto = await repo._select_seguro("campaigns", {
        "select": "id", "google_ads_campaign_id": f"eq.{campaign_id}", "limit": 1})
    if not pronto or google:
        return bloquear("CAMPAIGN_ID_GAM_COM_NAMESPACE_NAO_UNIVOCO")
    metas, pronto = await repo._select_seguro("trafego_meta_campaign", {
        "select": "meta_campaign_id", "external_id": f"eq.{campaign_id}", "limit": 2})
    if not pronto or len(metas) != 1:
        return bloquear("CAMPAIGN_ID_META_NAO_UNIVOCO")
    receita, pronto = await repo._select_seguro("gam_metrics", {
        "select": f"date,{cfg['revenue_column']},updated_at",
        "gam_accounts_id": f"eq.{gam_id}", "utm_campaign_value": f"eq.{campaign_id}",
        "and": f"(date.gte.{inicio},date.lte.{fim})", "order": "date.asc", "limit": 94})
    if not pronto or len(receita) != len(dias) or {str(r.get("date")) for r in receita} != dias:
        return bloquear("RECEITA_GAM_AUSENTE_PARCIAL_OU_DUPLICADA")
    revenue = _soma_completa(receita, cfg["revenue_column"])
    if revenue is None:
        return bloquear("RECEITA_GAM_NULA_OU_INVALIDA")
    vazio.update(revenue=revenue, revenue_completo=True,
                 receita_frescor=min(str(r.get("updated_at") or "") for r in receita) or None)
    spend = vazio["spend"]
    if spend is not None:
        vazio["profit_gross"] = revenue - spend
        if spend > 0:
            vazio["roas_ratio"] = revenue / spend
            vazio["retorno_excedente_pct"] = (revenue / spend - 1) * 100
    return vazio
