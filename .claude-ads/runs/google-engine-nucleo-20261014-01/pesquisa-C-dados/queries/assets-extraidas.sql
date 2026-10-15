-- GAQL extraídas VERBATIM (sintaxe gaarf: AS alias, :campo aninhado, ~N, {macro}).
-- Data 2026-10-14. Conferência: catálogo do servidor v25 do VOLC (volc_ads/google_ads_api/catalogo_gaql_v25.json).
-- O catálogo NÃO tem selectable_with: compatibilidade campo×FROM só se prova com validate_only (pesquisador A).

-- ===== ORIGEM: google-marketing-solutions/dgpulse@9cbb9d4e36ebb6660ec7d3fa4dcf3d8678f8b0f2:google_ads_queries/adgroupad_asset_view.sql:21-40
-- campos fora do catálogo v25: nenhum
SELECT
    segments.date AS date,
    metrics.impressions AS impressions,
    metrics.conversions AS conversions,
    metrics.conversions_value AS conversions_value,
    metrics.clicks AS clicks,
    metrics.ctr AS ctr,
    metrics.cost_micros AS cost,
    campaign.id,
    campaign.name AS campaign_name,
    ad_group_ad_asset_view.resource_name AS asset_type_inferred,
    customer.id AS account_id,
    customer.descriptive_name AS account_name,
    asset.id,
    asset.image_asset.full_size.url AS image_url
  FROM ad_group_ad_asset_view
  WHERE segments.date >= "{start_date}"
  AND segments.date <= "{end_date}"
  AND campaign.advertising_channel_type = "DEMAND_GEN"
  AND metrics.cost_micros > 0

-- ===== ORIGEM: google-marketing-solutions/dgpulse@9cbb9d4e36ebb6660ec7d3fa4dcf3d8678f8b0f2:google_ads_queries/ad_group_ad.sql:20-45
-- campos fora do catálogo v25: nenhum
SELECT
  ad_group_ad.ad.id AS aga_id,
  ad_group_ad.ad.type AS aga_type,
  ad_group_ad.ad.demand_gen_multi_asset_ad.portrait_marketing_images:asset AS dmaa_portrait_mkt_imgs,
  ad_group_ad.ad.demand_gen_multi_asset_ad.square_marketing_images:asset AS dmaa_square_mkt_imgs,
  ad_group_ad.ad.demand_gen_multi_asset_ad.marketing_images:asset AS dmaa_mkt_imgs,
  ad_group_ad.ad.demand_gen_multi_asset_ad.logo_images:asset AS dmaa_logo_imgs,
  ad_group_ad.ad.demand_gen_multi_asset_ad.descriptions AS dmaa_descriptions,
  ad_group_ad.ad.demand_gen_multi_asset_ad.headlines AS aga_headlines,
  ad_group_ad.ad.demand_gen_video_responsive_ad.videos:asset AS dvra_videos,
  ad_group_ad.ad.demand_gen_video_responsive_ad.long_headlines AS dvra_long_headlines,
  ad_group_ad.ad.demand_gen_video_responsive_ad.logo_images AS dvra_logo_imgs,
  ad_group_ad.ad.demand_gen_video_responsive_ad.descriptions AS dvra_descriptions,
  ad_group_ad.ad.demand_gen_video_responsive_ad.headlines AS dvra_headlines,
  customer.id AS account_id,
  campaign.id AS campaign_id,
  ad_group.id AS ag_id,
  campaign.name AS campaign_name,
  ad_group.demand_gen_ad_group_settings.channel_controls.channel_config AS cc_config,
  ad_group.demand_gen_ad_group_settings.channel_controls.channel_strategy AS cc_strategy
FROM
  ad_group_ad
WHERE
  campaign.advertising_channel_type = 'DEMAND_GEN'
  AND campaign.status = 'ENABLED'
  AND ad_group_ad.status = 'ENABLED'

-- ===== ORIGEM: google-marketing-solutions/pmax_best_practices_dashboard@3dc6fa0dbc0bca7c791c98973f80bf6bdc150422:google_ads_queries/assetgroupsignal.sql:15-22
-- campos fora do catálogo v25: nenhum
SELECT 
    asset_group_signal.audience.audience AS audience_signals,
    campaign.id AS campaign_id,
    asset_group.id AS asset_group_id
FROM 
    asset_group_signal 
WHERE 
    asset_group_signal.audience.audience IS NOT NULL

-- ===== ORIGEM: google-marketing-solutions/pmax_best_practices_dashboard@3dc6fa0dbc0bca7c791c98973f80bf6bdc150422:google_ads_queries/ad_group_asset.sql:15-21
-- campos fora do catálogo v25: nenhum
SELECT
  asset.id AS asset_id,
  ad_group_asset.ad_group~0 AS ad_group_id,
  customer.id AS account_id,
  ad_group_asset.field_type AS asset_type
FROM
  ad_group_asset

