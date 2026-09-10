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
import asyncio
import os
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import atribuicao as atr
from . import dominio as dom
from .desempenho_anuncios import indisponivel, ler_desempenho_anuncios

#: Teto de conjuntos por campanha numa única leitura financeira.
#:
#: Não é medo de campanha grande: é a recusa de transformar o teto do PostgREST
#: em "campanha sem conjuntos". Estourar o teto devolve leitura INCOMPLETA com
#: nome próprio, nunca uma lista curta que parece completa.
_TETO_DE_CONJUNTOS = 200

#: O TETO REAL DE UMA PÁGINA DO POSTGREST, e não um número que a gente escolhe.
#:
#: ⚠️ ESTE VALOR JÁ ESTEVE ERRADO, E O ERRO ERA SILENCIOSO. A primeira versão
#: pedia `limit=4000` e conferia `len(linhas) >= 4000`. Só que o PostgREST do
#: Supabase corta toda resposta em `db-max-rows` (1000 neste projeto) e IGNORA
#: um `limit` maior — o próprio `SupabaseService` documenta isso em
#: `supabase_service.py:75-78`: "pedir limit=5000 devolve 1000 linhas sem erro
#: nenhum".
#:
#: Consequência medida no raciocínio do revisor adversarial: com 1.200 linhas
#: disponíveis, a leitura devolvia 1.000, a guarda NUNCA disparava, e as 200
#: linhas que não vieram eram classificadas como `SEM_UTM_ADSET_NO_GAM` — ou
#: seja, uma leitura truncada virava "este conjunto/dia não tem receita".
#: Exatamente o que a semântica de ausência deste contrato existe para impedir.
#:
#: Agora a guarda mora na fronteira VERDADEIRA: uma resposta que chega cheia é
#: uma resposta possivelmente truncada, e isso bloqueia o total com nome
#: próprio em vez de virar ausência inventada.
_TETO_DE_LINHAS = 1000


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
        **indisponivel("ANUNCIOS_ESCOPO_AINDA_NAO_RESOLVIDO"),
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
    # Grão independente: não soma ao financeiro e sua indisponibilidade não
    # derruba o total da campanha nem espalha receita do GAM pelos anúncios.
    try:
        vazio.update(await asyncio.wait_for(ler_desempenho_anuncios(
            repo, contexto, campanha["meta_campaign_id"], inicio, fim), timeout=20.0))
    except Exception:
        # Erro da fonte secundária não expõe IDs/URLs e não quebra a primária.
        vazio.update(indisponivel("ANUNCIOS_LEITURA_INDISPONIVEL"))

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
    if len(conjuntos) * len(dias) > _TETO_DE_LINHAS:
        # O recorte pedido é maior do que UMA página cabe. Mesmo que a resposta
        # tenha vindo curta, não dá para afirmar que ela é completa.
        return bloquear("RECORTE_MAIOR_QUE_UMA_PAGINA")

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
            # ⚠️ `impressions` e `clicks` entraram em 08/09/2026: o contrato
            # público já declarava `gam_impressions`/`gam_clicks`, a consulta
            # não os pedia e o grão os recebia sempre `None`. Um zero MEDIDO do
            # lado GAM virava ausência — o inverso exato do erro que este
            # contrato mais persegue.
            "select": (f"date,utm_campaign_value,revenue,{cfg['revenue_column']},"
                       "impressions,clicks,updated_at"),
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
                    "impressions": bruta.get("impressions"),
                    "clicks": bruta.get("clicks"),
                    "updated_at": bruta.get("updated_at"),
                }
            # ⚠️ MOEDA E FUSO VÊM DA PRÓPRIA LINHA, não da conta.
            #
            # Achado do revisor adversarial: carimbar aqui a moeda da CONTA
            # fazia `_exigir_homogeneidade` nunca enxergar a divergência —
            # todas as linhas saíam com o mesmo carimbo, e um insight em USD
            # somava com um em BRL produzindo um total "em BRL" que não era
            # nem uma coisa nem outra. Marcar `completo=False` não torna essa
            # soma válida; o total precisa ser RECUSADO.
            #
            # Com a moeda de cada insight na linha, moedas ou fusos diferentes
            # levantam META_MOEDAS_MISTURADAS / META_FUSOS_MISTURADOS antes de
            # qualquer número virar total.
            linhas.append(atr.linha_de_conjunto_dia(
                account_ref=conta_ref, campaign_id=campaign_id, adset_id=conjunto,
                date=date.fromisoformat(dia), insight=insight, receita_gam=gam,
                gam_disponivel=gam_disponivel, project_id=project_id,
                currency=(insight or {}).get("currency") or vazio["currency"],
                timezone=(insight or {}).get("account_timezone") or vazio["timezone"],
                completo=completo_meta))

    try:
        total = atr.totalizar(linhas)
    except atr.AtribuicaoMetaInvalida as erro:
        # Uma coleção que não pode virar total não vira total. O código da
        # recusa viaja para a tela em vez de um número inventado.
        vazio["estado"] = "GRAO_INCOERENTE"
        return bloquear(erro.codigo)
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
