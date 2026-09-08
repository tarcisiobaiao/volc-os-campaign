"""Leitura financeira Meta + GAM no grão CONJUNTO/DIA, sem escrever nada.

⚠️ ESTE MÓDULO MUDOU DE GRÃO EM 08/09/2026, E A MUDANÇA É O CONSERTO.

A versão anterior declarava, no próprio docstring, "GAM.utm_campaign_value =
Meta campaign_id (decisão do operador 2026-09-07)" e filtrava `gam_metrics` por
esse igual. A operação real nunca foi assim: os anúncios que rodaram carregam
`utm_campaign={{adset.id}}`, então a coluna `utm_campaign_value` do GAM guarda
um id de CONJUNTO. O join por campanha casava zero linhas contra o dado real e
a tela mostrava receita `—` para sempre — sem errar uma conta, porque não
chegava a fazer nenhuma.

A prova que fechou a questão: 64 linhas campanha/dia de operação real, 62 com
receita atribuída via conjunto e 2 sem UTM de conjunto no GAM (ambas sem
entrega). R$ 1.029,41 investidos, R$ 1.140,73 de receita, ROAS ~1,108. Está
versionada, sanitizada, em `backend/tests/goldens/atribuicao-meta-adset-v1.json`.

## O que este módulo faz agora

1. resolve os CONJUNTOS filhos da campanha, no read model, dentro da conta;
2. lê o gasto no nível `adset`, um dia por linha;
3. lê a receita do GAM por `utm_campaign_value IN (<ids dos conjuntos>)`;
4. monta o grão conjunto/dia e deixa `atribuicao.totalizar` somar;
5. lê o nível `campaign` SÓ para reconciliar, e nunca o soma ao resultado.

O passo 5 é a diferença entre reconciliar e dobrar o gasto: as duas leituras
medem a MESMA despesa por caminhos diferentes. `atribuicao` recusa a soma com
nome próprio (`META_ESCOPOS_MISTURADOS`) para que o erro não possa ser cometido
por descuido em outro lugar.

Nada aqui resolve por NOME. O id bruto é resolvido no servidor; projeto e conta
GAM vêm de vínculos persistidos; moeda e fuso são confirmados nas duas pontas.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import atribuicao as atr
from . import dominio as dom

#: Teto de conjuntos por campanha numa única leitura financeira.
#:
#: Não é medo de campanha grande: é a recusa de transformar o teto do PostgREST
#: em "campanha sem conjuntos". Estourar o teto devolve leitura INCOMPLETA com
#: nome próprio, nunca uma lista curta que parece completa.
_TETO_DE_CONJUNTOS = 200

#: 92 dias × 200 conjuntos não cabem numa página. O limite pedido acompanha o
#: tamanho real do recorte, e a resposta é conferida contra ele.
_TETO_DE_LINHAS = 4000


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


def _chave_insight(row: Mapping[str, Any]) -> tuple[str, str]:
    return (str(row.get("objeto_externo")), str(row.get("periodo_inicio")))


async def ler_financeiro(repo: Any, referencia: str, conta_ref: str,
                         inicio: date | None, fim: date | None) -> dict:
    vazio: dict[str, Any] = {
        "ok": True, "provider": "META_ADS", "conta_ref": conta_ref,
        "campanha_ref": referencia, "estado": "SEM_SNAPSHOT",
        "grao": atr.ESCOPO_CONJUNTO, "contrato": atr.VERSAO_DA_ATRIBUICAO,
        "currency": None, "timezone": None, "periodo_inicio": None,
        "periodo_fim": None, "provisorio": False, "frescor": None,
        "spend": None, "revenue": None, "revenue_original": None,
        "profit_gross": None, "roas_ratio": None, "retorno_excedente_pct": None,
        "impressions": None, "clicks": None, "ctr": None, "cpc": None,
        "gam_impressions": None, "gam_clicks": None,
        "spend_completo": False, "revenue_completo": False,
        "conjuntos": [], "razao": None, "reconciliacao": None,
        "fontes": {"spend": "Meta Insights · adset · latest",
                   "revenue": "GAM · utm_campaign_value = adset_id",
                   "rollup": "campanha = SOMA dos conjuntos filhos"},
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
    vazio.update(periodo_inicio=inicio.isoformat(), periodo_fim=fim.isoformat(),
                 provisorio=fim == hoje)

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

    # -----------------------------------------------------------------------
    # Os CONJUNTOS filhos. Eles são o grão; sem eles não há leitura financeira.
    # -----------------------------------------------------------------------
    filhos, pronto = await repo._select_seguro("trafego_meta_adset", {
        "select": "external_id", "meta_campaign_id": f"eq.{campanha['meta_campaign_id']}",
        "order": "external_id.asc", "limit": _TETO_DE_CONJUNTOS + 1})
    if not pronto:
        return bloquear("SCHEMA_DE_CONJUNTOS_NAO_APLICADO")
    if len(filhos) > _TETO_DE_CONJUNTOS:
        return bloquear("CONJUNTOS_DA_CAMPANHA_TRUNCADOS")
    conjuntos = sorted({str(r.get("external_id")) for r in filhos
                        if atr.id_meta_valido(str(r.get("external_id", "")))})
    if len(conjuntos) != len(filhos):
        # Um `external_id` fora da gramática de id é dado corrompido no read
        # model, não um conjunto a ignorar em silêncio.
        return bloquear("CONJUNTO_COM_IDENTIDADE_INVALIDA")
    if not conjuntos:
        # Campanha sem conjunto conhecido continua DISTINGUÍVEL: ela não é uma
        # campanha com gasto zero, é uma campanha cujo grão não foi lido.
        vazio["estado"] = "SEM_CONJUNTOS_NO_READ_MODEL"
        return bloquear("CAMPANHA_SEM_CONJUNTOS_CONHECIDOS")
    vazio["conjuntos_conhecidos"] = len(conjuntos)

    # -----------------------------------------------------------------------
    # Gasto por conjunto/dia. Uma única semântica de relatório: não somar
    # `default` e `7d_click` do mesmo dia, nem duas revisões da mesma leitura.
    # -----------------------------------------------------------------------
    insights, pronto = await repo._select_seguro("vw_trafego_meta_insight_latest", {
        "select": "*", "ad_account_ativo_id": f"eq.{contexto['ativo_id']}",
        "provider": "eq.META_ADS", "nivel": "eq.adset",
        "objeto_externo": "in.(" + ",".join(conjuntos) + ")",
        "breakdown": "eq.none", "time_increment": "eq.1", "action_report_time": "eq.impression",
        "janela_atribuicao": "eq.default", "periodo_inicio": f"gte.{inicio}",
        "periodo_fim": f"lte.{fim}", "order": "periodo_inicio.asc",
        "limit": _TETO_DE_LINHAS})
    if not pronto:
        return bloquear("SCHEMA_DE_INSIGHTS_NAO_APLICADO")
    if len(insights) >= _TETO_DE_LINHAS:
        return bloquear("INSIGHTS_TRUNCADOS_PELO_TETO")

    por_grao: dict[tuple[str, str], Mapping[str, Any]] = {}
    for linha in insights:
        chave = _chave_insight(linha)
        if chave in por_grao:
            # A view `latest` já devolve uma linha por grão. Duas aqui são
            # schema divergente do esperado, e somá-las dobraria o dia.
            return bloquear("INSIGHT_DUPLICADO_NO_MESMO_GRAO")
        por_grao[chave] = linha

    esperadas = {(c, d) for c in conjuntos for d in dias}
    # Um dia sem linha é um dia NÃO MEDIDO, e é isso que ele vai ser: a linha
    # nasce com spend/impressions/clicks None. Ausência não vira zero.
    completo_meta = (
        bool(vazio["currency"])
        and set(por_grao) <= esperadas
        and all(str(r.get("periodo_fim")) == str(r.get("periodo_inicio"))
                and r.get("completo") is True
                and r.get("currency") == vazio["currency"]
                and r.get("account_timezone") == vazio["timezone"]
                for r in insights))
    if not completo_meta:
        bloquear("INSIGHTS_DIARIOS_AUSENTES_PARCIAIS_OU_INCOMPATIVEIS")
    vazio["estado"] = "COM_SNAPSHOT" if insights else "SEM_SNAPSHOT"

    # -----------------------------------------------------------------------
    # Receita. Escopo: projeto vinculado -> conta GAM única -> contrato de
    # moeda/fuso/coluna confirmado. Sem vínculo não existe fallback por nome.
    # -----------------------------------------------------------------------
    receita_por_grao: dict[tuple[str, str], Mapping[str, Any]] = {}
    gam_disponivel = False
    project_id: int | None = None

    bindings, pronto = await repo._select_seguro("trafego_meta_project_binding", {
        "select": "project_id", "ad_account_ativo_id": f"eq.{contexto['ativo_id']}",
        "desfeito_em": "is.null", "limit": 2})
    if not pronto or len(bindings) != 1:
        bloquear("VINCULO_PROJETO_META_NAO_CONFIRMADO")
    else:
        bruto = bindings[0].get("project_id")
        if not isinstance(bruto, int) or isinstance(bruto, bool) or bruto < 1:
            bloquear("VINCULO_PROJETO_META_INVALIDO")
        else:
            project_id = bruto

    cfg: dict | None = None
    if project_id is not None:
        contas_gam, pronto = await repo._select_seguro("gam_accounts", {
            "select": "id", "project_id": f"eq.{project_id}", "limit": 2})
        if not pronto or len(contas_gam) != 1 or not str(contas_gam[0].get("id", "")).isdigit():
            bloquear("CONTA_GAM_DO_PROJETO_NAO_UNIVOCA")
        else:
            gam_id = str(contas_gam[0]["id"])
            cfg = _contrato_gam(gam_id)
            if cfg is None:
                bloquear("MOEDA_FUSO_COLUNA_GAM_NAO_CONFIRMADOS")
            elif cfg["currency"] != vazio["currency"] or cfg["timezone"] != vazio["timezone"]:
                cfg = None
                bloquear("GAM_META_MOEDA_OU_FUSO_DIVERGENTE")
            else:
                # O coletor legado GAM não grava rede compradora. Uma colisão de
                # namespace entre Google e Meta no mesmo id impede atribuir
                # (não adivinhar de quem é a receita). A conferência agora é
                # sobre os CONJUNTOS, que são as chaves que o GAM realmente usa.
                google, pronto = await repo._select_seguro("campaigns", {
                    "select": "id",
                    "google_ads_campaign_id": "in.(" + ",".join(conjuntos) + ")",
                    "limit": 1})
                if not pronto or google:
                    cfg = None
                    bloquear("ADSET_ID_GAM_COM_NAMESPACE_NAO_UNIVOCO")

    if cfg is not None:
        receita, pronto = await repo._select_seguro("gam_metrics", {
            "select": f"date,utm_campaign_value,revenue,{cfg['revenue_column']},updated_at",
            "gam_accounts_id": f"eq.{gam_id}",
            "utm_campaign_value": "in.(" + ",".join(conjuntos) + ")",
            "and": f"(date.gte.{inicio},date.lte.{fim})",
            "order": "date.asc", "limit": _TETO_DE_LINHAS})
        if not pronto:
            bloquear("RECEITA_GAM_INDISPONIVEL")
        elif len(receita) >= _TETO_DE_LINHAS:
            bloquear("RECEITA_GAM_TRUNCADA_PELO_TETO")
        else:
            duplicada = False
            for linha in receita:
                chave = (str(linha.get("utm_campaign_value")), str(linha.get("date")))
                if chave in receita_por_grao:
                    duplicada = True
                    break
                receita_por_grao[chave] = linha
            if duplicada:
                receita_por_grao = {}
                bloquear("RECEITA_GAM_DUPLICADA_NO_MESMO_GRAO")
            else:
                gam_disponivel = True

    # -----------------------------------------------------------------------
    # O grão. Uma linha por conjunto/dia, com as duas fontes já resolvidas.
    # -----------------------------------------------------------------------
    linhas: list[atr.LinhaAtribuicao] = []
    for conjunto in conjuntos:
        for dia in sorted(dias):
            insight = por_grao.get((conjunto, dia))
            bruta = receita_por_grao.get((conjunto, dia))
            gam = None
            if bruta is not None:
                gam = {
                    "revenue": bruta.get("revenue"),
                    "revenue_converted": bruta.get(cfg["revenue_column"]) if cfg else None,
                    "updated_at": bruta.get("updated_at"),
                }
            linhas.append(atr.linha_de_conjunto_dia(
                account_ref=conta_ref, campaign_id=campaign_id, adset_id=conjunto,
                date=date.fromisoformat(dia), insight=insight, receita_gam=gam,
                gam_disponivel=gam_disponivel, project_id=project_id,
                currency=vazio["currency"], timezone=vazio["timezone"],
                completo=completo_meta))

    total = atr.totalizar(linhas)
    vazio.update(
        spend=total.spend, revenue=total.revenue_brl,
        revenue_original=total.revenue_original,
        profit_gross=total.profit_gross, roas_ratio=total.roas_ratio,
        retorno_excedente_pct=total.retorno_excedente_pct,
        impressions=total.impressions, clicks=total.clicks,
        ctr=total.ctr, cpc=total.cpc,
        gam_impressions=total.gam_impressions, gam_clicks=total.gam_clicks,
        spend_completo=total.razao.spend_completo,
        revenue_completo=total.razao.revenue_completo,
        razao=total.razao.publico(),
        frescor=total.source_freshness, receita_frescor=total.revenue_freshness)

    # Por conjunto, para o drill-down. Receita aparece SÓ no grão em que foi
    # medida: nada desce para anúncio ou criativo a partir daqui.
    por_conjunto = atr.agregar_conjunto_periodo(linhas)
    vazio["conjuntos"] = [
        {"adset_ref": dom.referencia_opaca_objeto(
             str(contexto["conta_externa"]), "adset", conjunto),
         "id_mascarado": dom.mascarar_id(conjunto),
         **t.publico()}
        for conjunto, t in por_conjunto.items()]

    # -----------------------------------------------------------------------
    # Reconciliação com a leitura campaign-level. DIAGNÓSTICO, nunca parcela.
    # -----------------------------------------------------------------------
    nivel_campanha, pronto = await repo._select_seguro("vw_trafego_meta_insight_latest", {
        "select": "spend,periodo_inicio", "ad_account_ativo_id": f"eq.{contexto['ativo_id']}",
        "provider": "eq.META_ADS", "nivel": "eq.campaign", "objeto_externo": f"eq.{campaign_id}",
        "breakdown": "eq.none", "time_increment": "eq.1", "action_report_time": "eq.impression",
        "janela_atribuicao": "eq.default", "periodo_inicio": f"gte.{inicio}",
        "periodo_fim": f"lte.{fim}", "order": "periodo_inicio.asc", "limit": 94})
    leitura_campanha = None
    if pronto and nivel_campanha and {str(r.get("periodo_inicio")) for r in nivel_campanha} == dias:
        soma = Decimal(0)
        for r in nivel_campanha:
            parcela = r.get("spend")
            if parcela is None:
                soma = None  # type: ignore[assignment]
                break
            soma += Decimal(str(parcela))
        if soma is not None:
            leitura_campanha = {"spend": soma}
    vazio["reconciliacao"] = atr.reconciliar_com_campaign_level(total, leitura_campanha)
    return vazio
