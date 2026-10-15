"""Confere GAQLs propostas contra volc_ads/google_ads_api/catalogo_gaql_v25.json (offline).

Replica a regra de volc_ads/gads/catalogo.invalidos(): todo campo do SELECT tem de
existir no catálogo e ser selecionável. NÃO prova compatibilidade entre recursos
(o catálogo não traz `selectable_with`); a compatibilidade foi conferida nas páginas
públicas /fields/v25/<recurso> (ver campos_compativeis_v25.out.json).

Reprodução (raiz do checkout):
  python3 -I .claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-A-apis/experimentos/validar_gaql_propostas.py \
      volc_ads/google_ads_api/catalogo_gaql_v25.json
"""
import json, re, sys

CAMPOS = json.load(open(sys.argv[1], encoding="utf-8"))["campos"]
SEL = re.compile(r"\bSELECT\s+(.*?)\s+FROM\s+([a-z_]+)", re.S | re.I)

Q = {
 "placements_display_dg_video_por_canal": """SELECT campaign.id, campaign.advertising_channel_type, ad_group.id,
   group_placement_view.placement, group_placement_view.placement_type, group_placement_view.display_name,
   group_placement_view.target_url, segments.date, metrics.impressions, metrics.clicks, metrics.cost_micros,
   metrics.conversions, metrics.conversions_value
   FROM group_placement_view WHERE segments.date DURING LAST_30_DAYS AND metrics.impressions > 0""",
 "placements_detail_por_canal": """SELECT campaign.id, campaign.advertising_channel_type, ad_group.id,
   detail_placement_view.placement, detail_placement_view.placement_type, detail_placement_view.target_url,
   detail_placement_view.group_placement_target_url, segments.date, metrics.impressions, metrics.clicks,
   metrics.cost_micros, metrics.conversions
   FROM detail_placement_view WHERE segments.date DURING LAST_7_DAYS AND metrics.impressions > 0""",
 "placements_pmax_so_impressoes": """SELECT campaign.id, performance_max_placement_view.placement,
   performance_max_placement_view.placement_type, performance_max_placement_view.target_url,
   performance_max_placement_view.display_name, segments.ad_network_type, metrics.impressions
   FROM performance_max_placement_view WHERE segments.date DURING LAST_30_DAYS""",
 "placements_adequacao_conteudo": """SELECT campaign.id, campaign.advertising_channel_type,
   detail_content_suitability_placement_view.placement, detail_content_suitability_placement_view.placement_type,
   detail_content_suitability_placement_view.target_url, segments.date, metrics.impressions
   FROM detail_content_suitability_placement_view WHERE segments.date DURING LAST_7_DAYS""",
 "exclusoes_conta": """SELECT customer_negative_criterion.id, customer_negative_criterion.type,
   customer_negative_criterion.placement.url, customer_negative_criterion.youtube_channel.channel_id,
   customer_negative_criterion.youtube_video.video_id, customer_negative_criterion.mobile_application.app_id,
   customer_negative_criterion.placement_list.shared_set, customer_negative_criterion.ip_block.ip_address
   FROM customer_negative_criterion""",
 "listas_negativas_placement": """SELECT shared_set.id, shared_set.name, shared_set.type, shared_set.status,
   shared_set.member_count FROM shared_set WHERE shared_set.type = 'NEGATIVE_PLACEMENTS'""",
 "tcpa_efetivo_por_grupo": """SELECT campaign.id, campaign.advertising_channel_type, campaign.bidding_strategy_type,
   campaign.bidding_strategy, ad_group.id, ad_group.target_cpa_micros, ad_group.effective_target_cpa_micros,
   ad_group.effective_target_cpa_source, ad_group.target_roas, ad_group.effective_target_roas,
   ad_group.effective_target_roas_source FROM ad_group WHERE ad_group.status != 'REMOVED'""",
 "qs_snapshot_e_historico": """SELECT campaign.id, ad_group.id, ad_group_criterion.criterion_id,
   ad_group_criterion.keyword.text, ad_group_criterion.quality_info.quality_score,
   ad_group_criterion.quality_info.creative_quality_score, ad_group_criterion.quality_info.post_click_quality_score,
   ad_group_criterion.quality_info.search_predicted_ctr, metrics.historical_quality_score,
   metrics.historical_creative_quality_score, metrics.historical_landing_page_quality_score,
   metrics.historical_search_predicted_ctr, segments.date, metrics.impressions
   FROM keyword_view WHERE segments.date DURING LAST_30_DAYS AND metrics.impressions > 0""",
 "rsa_ativos_politica_metricas": """SELECT campaign.id, ad_group.id, ad_group_ad.ad.id, asset.id,
   asset.text_asset.text, ad_group_ad_asset_view.field_type, ad_group_ad_asset_view.pinned_field,
   ad_group_ad_asset_view.enabled, ad_group_ad_asset_view.source, ad_group_ad_asset_view.policy_summary,
   segments.date, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
   FROM ad_group_ad_asset_view WHERE segments.date DURING LAST_30_DAYS""",
 "pmax_ativos_status_politica": """SELECT campaign.id, asset_group.id, asset.id, asset_group_asset.field_type,
   asset_group_asset.status, asset_group_asset.primary_status, asset_group_asset.primary_status_reasons,
   asset_group_asset.policy_summary.approval_status, asset_group_asset.policy_summary.review_status
   FROM asset_group_asset WHERE asset_group_asset.status != 'REMOVED'""",
 "pmax_top_combinacoes": """SELECT asset_group_top_combination_view.asset_group_top_combinations
   FROM asset_group_top_combination_view""",
 "sazonalidade_e_exclusoes": """SELECT bidding_seasonality_adjustment.resource_name, bidding_seasonality_adjustment.scope,
   bidding_seasonality_adjustment.status, bidding_seasonality_adjustment.start_date_time,
   bidding_seasonality_adjustment.end_date_time, bidding_seasonality_adjustment.conversion_rate_modifier,
   bidding_seasonality_adjustment.campaigns, bidding_seasonality_adjustment.advertising_channel_types,
   bidding_seasonality_adjustment.devices FROM bidding_seasonality_adjustment""",
 "experimentos": """SELECT experiment.resource_name, experiment.name, experiment.type, experiment.status,
   experiment.start_date, experiment.end_date, experiment.promote_status, experiment.suffix FROM experiment""",
 "bracos_de_experimento": """SELECT experiment_arm.resource_name, experiment_arm.experiment, experiment_arm.control,
   experiment_arm.traffic_split, experiment_arm.campaigns, experiment_arm.in_design_campaigns FROM experiment_arm""",
 "regras_de_valor": """SELECT conversion_value_rule.id, conversion_value_rule.status, conversion_value_rule.action.operation,
   conversion_value_rule.action.value, conversion_value_rule.owner_customer FROM conversion_value_rule""",
 "NEGATIVO_asset_group_asset_performance_label": """SELECT asset_group_asset.performance_label FROM asset_group_asset""",
}

rc = 0
for nome, q in Q.items():
    m = SEL.search(q)
    campos = [c.strip() for c in m.group(1).split(",") if c.strip()]
    ruins = [c for c in campos if c not in CAMPOS or not CAMPOS[c][1]]
    print(("OK  " if not ruins else "FALHA ") + nome + (f"  inválidos={ruins}" if ruins else f"  ({len(campos)} campos, FROM {m.group(2)})"))
    if ruins and not nome.startswith("NEGATIVO"):
        rc = 1
sys.exit(rc)
