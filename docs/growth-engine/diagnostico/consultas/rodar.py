#!/usr/bin/env python3
"""Runner de diagnóstico — SOMENTE LEITURA — da conta Crédito Up (8017851692).

Reproduz, sem nenhuma escrita, a evidência de `docs/growth-engine/diagnostico/`.

    PYTHONPATH=<raiz do repo> backend/.venv/bin/python \
        docs/growth-engine/diagnostico/consultas/rodar.py --saida evidencia.json

Garantias estruturais deste arquivo:

* toda consulta passa por `_exigir_select()` antes de sair da máquina — o que
  não começar em `SELECT`, ou trouxer `;`, não é enviado;
* só existe `search_stream`. Não há `mutate`, não há `validate_only`, e o módulo
  NÃO importa `volc_ads.gads.client.mutar` nem `volc_ads.gads.modo.destravar`;
* toda chamada viaja com `login_customer_id=6016739364` (o MCC da casa), como
  manda `backend/app/trafego/escopo.py`, e o escopo é exigido antes da rede;
* nenhum segredo é lido, impresso ou gravado. As credenciais ficam no
  `~/google-ads.yaml` que o SDK carrega sozinho.

Cada consulta roda no seu próprio `try`: uma que falhar vira um registro de erro
com a mensagem literal da API, e as outras continuam. "Não consegui ler" e "não
existe" são fatos opostos e o JSON de saída os mantém separados.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

from google.protobuf.json_format import MessageToDict

from volc_ads.gads.client import VERSAO_API, cliente
from volc_ads.gads import modo
from app.trafego.escopo import MCC_DA_CASA, exigir_escopo

CONTA_CREDITO_UP = "8017851692"

#: Janela padrão das métricas. Toda métrica no JSON de saída carrega a janela
#: que a produziu — número sem janela não é medição, é boato.
JANELA = "LAST_30_DAYS"


class NaoEhLeitura(RuntimeError):
    """Alguém tentou passar algo que não é `SELECT`. Nada foi enviado."""


def _exigir_select(gaql: str) -> str:
    limpo = " ".join(str(gaql or "").split())
    if not limpo.upper().startswith("SELECT"):
        raise NaoEhLeitura(f"não é leitura: {limpo[:80]!r}")
    if ";" in limpo:
        raise NaoEhLeitura("GAQL com `;`: comando encadeado não é executado.")
    return limpo


# ── catálogo de consultas ───────────────────────────────────────────────────
#
# A ordem importa só para a leitura humana do JSON. Cada entrada é
# `nome: (gaql, por_que)` — o "por quê" existe para o auditor não ter de
# adivinhar qual pergunta cada consulta responde.

CONSULTAS: Dict[str, tuple[str, str]] = {
    "conta": (
        """
        SELECT customer.id, customer.descriptive_name, customer.currency_code,
               customer.time_zone, customer.status, customer.manager,
               customer.test_account, customer.auto_tagging_enabled,
               customer.optimization_score, customer.tracking_url_template,
               customer.pay_per_conversion_eligibility_failure_reasons
        FROM customer
        """,
        "moeda, fuso e status da conta — uma conta SUSPENDED/CANCELED não veicula",
    ),
    "campanhas": (
        """
        SELECT campaign.id, campaign.name, campaign.status,
               campaign.serving_status, campaign.primary_status,
               campaign.primary_status_reasons,
               campaign.advertising_channel_type,
               campaign.advertising_channel_sub_type,
               campaign.bidding_strategy_type, campaign.bidding_strategy,
               campaign.manual_cpc.enhanced_cpc_enabled,
               campaign.target_spend.cpc_bid_ceiling_micros,
               campaign.target_spend.target_spend_micros,
               campaign.maximize_conversions.target_cpa_micros,
               campaign.maximize_conversion_value.target_roas,
               campaign.target_cpa.target_cpa_micros,
               campaign.target_roas.target_roas,
               campaign.start_date_time, campaign.end_date_time,
               campaign.bidding_strategy_system_status,
               campaign.ad_serving_optimization_status,
               campaign.optimization_score,
               campaign.experiment_type, campaign.payment_mode,
               campaign.network_settings.target_google_search,
               campaign.network_settings.target_search_network,
               campaign.network_settings.target_content_network,
               campaign.network_settings.target_partner_search_network,
               campaign.geo_target_type_setting.positive_geo_target_type,
               campaign.geo_target_type_setting.negative_geo_target_type,
               campaign.campaign_budget,
               campaign_budget.id, campaign_budget.name,
               campaign_budget.amount_micros,
               campaign_budget.total_amount_micros,
               campaign_budget.delivery_method, campaign_budget.status,
               campaign_budget.explicitly_shared,
               campaign_budget.has_recommended_budget,
               campaign_budget.recommended_budget_amount_micros,
               campaign_budget.period
        FROM campaign
        """,
        "o estado da campanha e o motivo que o PRÓPRIO Google dá (primary_status_reasons)",
    ),
    "grupos": (
        """
        SELECT campaign.id, campaign.name, ad_group.id, ad_group.name,
               ad_group.status, ad_group.primary_status,
               ad_group.primary_status_reasons, ad_group.type,
               ad_group.cpc_bid_micros, ad_group.cpm_bid_micros,
               ad_group.target_cpa_micros, ad_group.target_cpm_micros,
               ad_group.effective_target_cpa_micros,
               ad_group.effective_target_roas,
               ad_group.percent_cpc_bid_micros
        FROM ad_group
        """,
        "o lance vive aqui, não na campanha; e o primary_status do grupo",
    ),
    "anuncios": (
        """
        SELECT campaign.id, ad_group.id, ad_group_ad.ad.id,
               ad_group_ad.status, ad_group_ad.primary_status,
               ad_group_ad.primary_status_reasons,
               ad_group_ad.ad_strength, ad_group_ad.action_items,
               ad_group_ad.policy_summary.approval_status,
               ad_group_ad.policy_summary.review_status,
               ad_group_ad.policy_summary.policy_topic_entries,
               ad_group_ad.ad.type, ad_group_ad.ad.final_urls,
               ad_group_ad.ad.responsive_search_ad.headlines,
               ad_group_ad.ad.responsive_search_ad.descriptions,
               ad_group_ad.ad.responsive_search_ad.path1,
               ad_group_ad.ad.responsive_search_ad.path2
        FROM ad_group_ad
        """,
        "aprovação e política do anúncio — reprovado não entra em leilão nenhum",
    ),
    "keywords": (
        """
        SELECT campaign.id, ad_group.id, ad_group_criterion.criterion_id,
               ad_group_criterion.keyword.text,
               ad_group_criterion.keyword.match_type,
               ad_group_criterion.status,
               ad_group_criterion.primary_status,
               ad_group_criterion.primary_status_reasons,
               ad_group_criterion.approval_status,
               ad_group_criterion.disapproval_reasons,
               ad_group_criterion.system_serving_status,
               ad_group_criterion.negative,
               ad_group_criterion.cpc_bid_micros,
               ad_group_criterion.effective_cpc_bid_micros,
               ad_group_criterion.effective_cpc_bid_source,
               ad_group_criterion.quality_info.quality_score,
               ad_group_criterion.quality_info.creative_quality_score,
               ad_group_criterion.quality_info.post_click_quality_score,
               ad_group_criterion.quality_info.search_predicted_ctr,
               ad_group_criterion.final_urls
        FROM ad_group_criterion
        WHERE ad_group_criterion.type = 'KEYWORD'
        """,
        "status, aprovação, RARELY_SERVED, lance efetivo e Quality Score por keyword",
    ),
    "keywords_estimativas": (
        """
        SELECT campaign.id, ad_group.id, ad_group_criterion.criterion_id,
               ad_group_criterion.keyword.text,
               ad_group_criterion.position_estimates.first_page_cpc_micros,
               ad_group_criterion.position_estimates.top_of_page_cpc_micros,
               ad_group_criterion.position_estimates.first_position_cpc_micros,
               ad_group_criterion.position_estimates.estimated_add_clicks_at_first_position_cpc
        FROM ad_group_criterion
        WHERE ad_group_criterion.type = 'KEYWORD'
        """,
        "estimativa de primeira página/topo — v25 AINDA devolve; ⚠️ o join precisa "
        "de (ad_group, criterion_id): o criterion_id de uma keyword é COMPARTILHADO "
        "entre grupos, e juntar só por ele mistura campanha viva com removida",
    ),
    "keywords_metricas": (
        """
        SELECT campaign.id, ad_group.id, ad_group_criterion.criterion_id,
               ad_group_criterion.keyword.text,
               metrics.impressions, metrics.clicks, metrics.cost_micros,
               metrics.average_cpc, metrics.search_impression_share,
               metrics.search_rank_lost_impression_share
        FROM keyword_view
        WHERE segments.date DURING {janela}
        """,
        "quais keywords tiveram impressão na janela — e quais nunca apareceram",
    ),
    "metricas_campanha": (
        """
        SELECT campaign.id, campaign.name,
               metrics.impressions, metrics.clicks, metrics.cost_micros,
               metrics.average_cpc, metrics.ctr, metrics.conversions,
               metrics.all_conversions,
               metrics.search_impression_share,
               metrics.search_budget_lost_impression_share,
               metrics.search_rank_lost_impression_share,
               metrics.search_top_impression_share,
               metrics.search_absolute_top_impression_share,
               metrics.search_click_share,
               metrics.absolute_top_impression_percentage,
               metrics.top_impression_percentage,
               metrics.eligible_impressions_from_location_asset_store_reach
        FROM campaign
        WHERE segments.date DURING {janela}
        """,
        "entrega agregada e as parcelas de impressão perdidas — por lance ou por verba",
    ),
    "metricas_campanha_diaria": (
        """
        SELECT campaign.id, segments.date,
               metrics.impressions, metrics.clicks, metrics.cost_micros,
               metrics.average_cpc, metrics.search_impression_share,
               metrics.search_rank_lost_impression_share,
               metrics.search_budget_lost_impression_share
        FROM campaign
        WHERE segments.date DURING {janela}
        """,
        "pacing dia a dia — a agregada esconde o dia em que a campanha subiu",
    ),
    "metricas_grupo": (
        """
        SELECT campaign.id, ad_group.id,
               metrics.impressions, metrics.clicks, metrics.cost_micros,
               metrics.average_cpc,
               metrics.search_impression_share,
               metrics.search_rank_lost_impression_share
        FROM ad_group
        WHERE segments.date DURING {janela}
        """,
        "a mesma pergunta um nível abaixo",
    ),
    "listas_negativas": (
        """
        SELECT campaign.id, campaign_shared_set.shared_set,
               campaign_shared_set.status, shared_set.name, shared_set.type,
               shared_set.member_count, shared_set.status
        FROM campaign_shared_set
        """,
        "lista de negativas compartilhada bloqueia entrega inteira sem aparecer no criterion",
    ),
    "metricas_hoje": (
        """
        SELECT campaign.id, campaign.name,
               metrics.impressions, metrics.clicks, metrics.cost_micros
        FROM campaign WHERE segments.date DURING TODAY
        """,
        "LAST_30_DAYS NÃO inclui hoje; esta consulta fecha o buraco do dia corrente",
    ),
    "metricas_desde_o_lancamento": (
        """
        SELECT campaign.id, campaign.name,
               metrics.impressions, metrics.clicks, metrics.cost_micros,
               metrics.average_cpc,
               metrics.search_impression_share,
               metrics.search_budget_lost_impression_share,
               metrics.search_rank_lost_impression_share,
               metrics.search_top_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '2026-08-19' AND '2026-08-26'
        """,
        "a vida inteira das campanhas, com as DATAS EXPLÍCITAS em vez de um apelido",
    ),
    "criterios_campanha": (
        """
        SELECT campaign.id, campaign_criterion.criterion_id,
               campaign_criterion.type, campaign_criterion.status,
               campaign_criterion.negative,
               campaign_criterion.bid_modifier,
               campaign_criterion.location.geo_target_constant,
               campaign_criterion.language.language_constant,
               campaign_criterion.ad_schedule.day_of_week,
               campaign_criterion.ad_schedule.start_hour,
               campaign_criterion.ad_schedule.end_hour,
               campaign_criterion.keyword.text,
               campaign_criterion.keyword.match_type,
               campaign_criterion.display_name
        FROM campaign_criterion
        """,
        "geo, idioma, agendamento e negativas de campanha — segmentação que zera entrega",
    ),
    "geo_alvo": (
        """
        SELECT geo_target_constant.id, geo_target_constant.name,
               geo_target_constant.canonical_name,
               geo_target_constant.country_code, geo_target_constant.status,
               geo_target_constant.target_type
        FROM geo_target_constant
        WHERE geo_target_constant.resource_name = 'geoTargetConstants/2076'
        """,
        "traduz o id de localização usado pelas campanhas vivas",
    ),
    "conversoes": (
        """
        SELECT conversion_action.id, conversion_action.name,
               conversion_action.status, conversion_action.type,
               conversion_action.category,
               conversion_action.primary_for_goal,
               conversion_action.counting_type,
               conversion_action.include_in_conversions_metric,
               conversion_action.click_through_lookback_window_days,
               conversion_action.attribution_model_settings.attribution_model,
               conversion_action.origin
        FROM conversion_action
        """,
        "sem conversão registrada, Smart Bidding não tem do que aprender",
    ),
    "conversoes_metricas": (
        """
        SELECT conversion_action.id, conversion_action.name,
               metrics.all_conversions, metrics.all_conversions_value
        FROM conversion_action
        WHERE segments.date DURING {janela}
        """,
        "contagem recente por ação de conversão",
    ),
    "mudancas": (
        """
        SELECT change_event.change_date_time, change_event.change_resource_type,
               change_event.change_resource_name, change_event.client_type,
               change_event.user_email, change_event.resource_change_operation,
               change_event.changed_fields, change_event.campaign,
               change_event.ad_group, change_event.old_resource,
               change_event.new_resource
        FROM change_event
        WHERE change_event.change_date_time DURING LAST_14_DAYS
        ORDER BY change_event.change_date_time DESC
        LIMIT 500
        """,
        "quem mexeu, no quê e quando — janela máxima da API é 14 dias",
    ),
    "faturamento": (
        """
        SELECT billing_setup.id, billing_setup.status,
               billing_setup.payments_account,
               billing_setup.start_date_time, billing_setup.end_date_time
        FROM billing_setup
        """,
        "conta sem faturamento ativo não veicula, mesmo com tudo ENABLED",
    ),
    "termos_de_busca": (
        """
        SELECT campaign.id, search_term_view.search_term,
               search_term_view.status,
               metrics.impressions, metrics.clicks, metrics.cost_micros
        FROM search_term_view
        WHERE segments.date DURING {janela}
        """,
        "o que o usuário realmente digitou — vazio confirma ausência de leilão",
    ),
    "recomendacoes": (
        """
        SELECT recommendation.type, recommendation.campaign,
               recommendation.dismissed, recommendation.campaign_budget
        FROM recommendation
        """,
        "o que o Google sugere para esta conta — pista adicional, nunca prova",
    ),
}


def _linha_para_dict(row: Any) -> Dict[str, Any]:
    """Proto → dict, mantendo o nome de campo do GAQL (snake_case)."""
    return MessageToDict(
        row._pb,
        preserving_proto_field_name=True,
        always_print_fields_with_no_presence=False,
    )


def rodar(customer_id: str, janela: str, apenas: List[str] | None = None) -> Dict[str, Any]:
    cid, mid = exigir_escopo(customer_id, MCC_DA_CASA)

    c = cliente(mid)
    servico = c.get_service("GoogleAdsService")

    saida: Dict[str, Any] = {
        "_meta": {
            "lido_em_utc": datetime.now(timezone.utc).isoformat(),
            "customer_id": cid,
            "login_customer_id": mid,
            "versao_api": VERSAO_API,
            "janela_das_metricas": janela,
            "modo_de_escrita": modo.estado(),
            "somente_leitura": True,
        },
        "consultas": {},
    }

    for nome, (gaql_bruto, por_que) in CONSULTAS.items():
        if apenas and nome not in apenas:
            continue
        gaql = _exigir_select(gaql_bruto.format(janela=janela))
        registro: Dict[str, Any] = {
            "gaql": gaql,
            "por_que": por_que,
            "lido_em_utc": datetime.now(timezone.utc).isoformat(),
        }
        try:
            linhas: List[Dict[str, Any]] = []
            for lote in servico.search_stream(customer_id=cid, query=gaql):
                for r in lote.results:
                    linhas.append(_linha_para_dict(r))
            registro["ok"] = True
            registro["n"] = len(linhas)
            registro["linhas"] = linhas
        except Exception as exc:  # noqa: BLE001 — o erro literal É a evidência
            registro["ok"] = False
            registro["erro"] = f"{type(exc).__name__}: {exc}"[:4000]
        saida["consultas"][nome] = registro
        print(
            f"  {nome:26s} "
            + ("ok  n=%d" % registro["n"] if registro["ok"] else "FALHOU"),
            file=sys.stderr,
        )

    return saida


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--conta", default=CONTA_CREDITO_UP)
    p.add_argument("--janela", default=JANELA)
    p.add_argument("--saida", default="-")
    p.add_argument("--apenas", nargs="*", default=None)
    a = p.parse_args()

    dados = rodar(a.conta, a.janela, a.apenas)
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    if a.saida == "-":
        print(texto)
    else:
        with open(a.saida, "w", encoding="utf-8") as fh:
            fh.write(texto + "\n")
        print(f"gravado: {a.saida}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
