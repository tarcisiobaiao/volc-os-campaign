-- GAQL extraídas VERBATIM (sintaxe gaarf: AS alias, :campo aninhado, ~N, {macro}).
-- Data 2026-10-14. Conferência: catálogo do servidor v25 do VOLC (volc_ads/google_ads_api/catalogo_gaql_v25.json).
-- O catálogo NÃO tem selectable_with: compatibilidade campo×FROM só se prova com validate_only (pesquisador A).

-- ===== ORIGEM: google-marketing-solutions/ads_placement_guardian@294c4c37e1383af9ec639e3c2ccf79b7b25abba2:libs/ads_housekeeper/googleads_housekeeper/domain/placement_handler/entities.py:50-72
-- campos fora do catálogo v25: nenhum
  base_query_text = """
        SELECT
            customer.id AS customer_id,
            campaign.id AS campaign_id,
            campaign.advertising_channel_type AS campaign_type,
            ad_group.id AS ad_group_id,
            {extra_dimensions}
            {placement_level_granularity}.placement AS placement,
            {placement_level_granularity}.placement_type AS placement_type,
            {placement_level_granularity}.display_name AS name,
            {metrics}
        FROM {placement_level_granularity}
        WHERE segments.date >= "{start_date}"
            AND segments.date <= "{end_date}"
            AND {placement_level_granularity}.placement_type IN
                ("{placement_types}")
            AND {placement_level_granularity}.target_url NOT IN
                ("{non_excludable_placements}")
            AND campaign.advertising_channel_type IN ("{campaign_types}")
            AND {filters}
        ORDER BY metrics.cost_micros DESC
        {limit}
        """

-- ===== ORIGEM: google-marketing-solutions/ads_placement_guardian@294c4c37e1383af9ec639e3c2ccf79b7b25abba2:libs/ads_housekeeper/googleads_housekeeper/domain/placement_handler/entities.py:247-264
-- campos fora do catálogo v25: nenhum
  base_query_text = """
        SELECT
            campaign.advertising_channel_type AS campaign_type,
            ad_group.id AS ad_group_id,
            segments.conversion_action_name AS conversion_name,
            {placement_level_granularity}.placement_type AS placement_type,
            {placement_level_granularity}.placement AS placement,
            metrics.conversions AS conversions,
            metrics.all_conversions AS all_conversions
        FROM {placement_level_granularity}
        WHERE segments.date >= "{start_date}"
            AND segments.date <= "{end_date}"
            AND {placement_level_granularity}.placement_type IN
                ("{placement_types}")
            AND {placement_level_granularity}.target_url NOT IN
                ("{non_excludable_placements}")
            AND campaign.advertising_channel_type IN ("{campaign_types}")
    """

-- ===== ORIGEM: google-marketing-solutions/ads_placement_guardian@294c4c37e1383af9ec639e3c2ccf79b7b25abba2:libs/ads_housekeeper/googleads_housekeeper/domain/placement_handler/entities.py:343-355
-- campos fora do catálogo v25: nenhum
  base_query_text = """
        SELECT
            {level}.id AS level_id,
            {criterion_resource_name}.placement.url AS website_url,
            {criterion_resource_name}.mobile_application.app_id AS app_id,
            {criterion_resource_name}.youtube_video.video_id AS video_id,
            {criterion_resource_name}.youtube_channel.channel_id AS channel_id
        FROM {criterion_resource_name}
        WHERE {criterion_resource_name}.type IN ("{placement_types}")
        ORDER BY {criterion_resource_name}.youtube_video.video_id,
                 {criterion_resource_name}.youtube_channel.channel_id,
                 {criterion_resource_name}.mobile_application.app_id
    """

-- ===== ORIGEM: google-marketing-solutions/video-exclusion-toolbox@97d544876a1139688f07f84e51d1dbde5fc71641:src/gads_channel_report_fetcher/main.py:86-110
-- campos fora do catálogo v25: nenhum
        SELECT
            customer.id,
            campaign.id,
            campaign.name,
            group_placement_view.display_name,
            group_placement_view.placement,
            group_placement_view.placement_type,
            group_placement_view.target_url,
            metrics.impressions,
            metrics.cost_micros,
            metrics.conversions,
            metrics.video_trueview_views,
            metrics.video_trueview_view_rate,
            metrics.clicks,
            metrics.average_cpm,
            metrics.ctr,
            metrics.all_conversions_from_interactions_rate
        FROM
            group_placement_view
        WHERE group_placement_view.placement_type = "YOUTUBE_CHANNEL"
            AND campaign.advertising_channel_type IN ("VIDEO", "DEMAND_GEN")
            AND group_placement_view.display_name != ""
            AND group_placement_view.target_url != ""
            {where_query}
    """

-- ===== ORIGEM: google-marketing-solutions/video-exclusion-toolbox@97d544876a1139688f07f84e51d1dbde5fc71641:src/gads_video_report_fetcher/main.py:86-116
-- campos fora do catálogo v25: nenhum
        SELECT
            customer.id,
            campaign.id,
            campaign.name,
            ad_group.id,
            ad_group.name,
            detail_placement_view.display_name,
            detail_placement_view.group_placement_target_url,
            detail_placement_view.placement,
            detail_placement_view.placement_type,
            detail_placement_view.target_url,
            metrics.impressions,
            metrics.cost_micros,
            metrics.conversions,
            metrics.video_trueview_views,
            metrics.video_trueview_view_rate,
            metrics.clicks,
            metrics.average_cpm,
            metrics.ctr,
            metrics.all_conversions_from_interactions_rate,
            metrics.video_quartile_p25_rate,
            metrics.video_quartile_p50_rate,
            metrics.video_quartile_p75_rate,
            metrics.video_quartile_p100_rate
        FROM
            detail_placement_view
        WHERE detail_placement_view.placement_type = "YOUTUBE_VIDEO"
            AND campaign.advertising_channel_type = "VIDEO"
            AND detail_placement_view.display_name != ""
            {where_query}
    """

-- ===== ORIGEM: google-marketing-solutions/pmax_best_practices_dashboard@3dc6fa0dbc0bca7c791c98973f80bf6bdc150422:google_ads_queries/pmax_placement_view.sql:15-32
-- campos fora do catálogo v25: nenhum
SELECT
    segments.date AS date,
    campaign.advertising_channel_type AS campaign_type,
    campaign.status AS campaign_status,
    customer.id AS account_id,
    customer.descriptive_name AS account_name,
    campaign.id AS campaign_id,
    campaign.name AS campaign_name,
    performance_max_placement_view.display_name AS placement_name,
    performance_max_placement_view.placement AS placement,
    performance_max_placement_view.placement_type AS placement_type,
    performance_max_placement_view.target_url AS placement_target_url,
    metrics.impressions AS impressions
FROM performance_max_placement_view
WHERE campaign.advertising_channel_type = "PERFORMANCE_MAX"
    AND segments.date >= "{start_date}"
    AND segments.date <= "{end_date}"
    AND campaign.status = 'ENABLED'

