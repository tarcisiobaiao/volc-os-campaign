-- GAQL extraídas VERBATIM (sintaxe gaarf: AS alias, :campo aninhado, ~N, {macro}).
-- Data 2026-10-14. Conferência: catálogo do servidor v25 do VOLC (volc_ads/google_ads_api/catalogo_gaql_v25.json).
-- O catálogo NÃO tem selectable_with: compatibilidade campo×FROM só se prova com validate_only (pesquisador A).

-- ===== ORIGEM: google-marketing-solutions/ads-policy-monitor@7d313aead8aa49f2bdfe459cf112a9dfc8e12cf7:cloud_functions/ads_policy_monitor/gaql/ad_policy_data.sql:14-41
-- campos fora do catálogo v25: nenhum
SELECT
  {{ today }} AS event_date,
  customer.id,
  customer.descriptive_name,
  campaign.id,
  campaign.name,
  campaign.status,
  campaign.primary_status,
  ad_group.id,
  ad_group.name,
  ad_group.status,
  ad_group_ad.ad.id,
  ad_group_ad.status,
  ad_group_ad.policy_summary.approval_status,
  ad_group_ad.policy_summary.policy_topic_entries:topic AS ad_group_ad_policy_summary_policy_topic_entries,
  ad_group_ad.policy_summary.review_status,
  metrics.impressions AS impressions,
  metrics.clicks AS clicks
FROM
  ad_group_ad
WHERE
  customer.status = 'ENABLED'
  AND campaign.status = 'ENABLED'
  AND campaign.primary_status != 'ENDED'
  AND ad_group.status = 'ENABLED'
  AND ad_group_ad.status != 'REMOVED'
  AND ad_group_ad.policy_summary.approval_status != 'APPROVED'
  AND segments.date DURING LAST_30_DAYS

-- ===== ORIGEM: google-marketing-solutions/ads-policy-monitor@7d313aead8aa49f2bdfe459cf112a9dfc8e12cf7:cloud_functions/ads_policy_monitor/gaql/ad_group_asset.sql:14-37
-- campos fora do catálogo v25: nenhum
SELECT 
  {{ today }} AS event_date,
  customer.id,
  customer.descriptive_name,
  asset.id,
  asset.source,
  asset.type,
  asset.policy_summary.review_status,
  asset.policy_summary.policy_topic_entries:topic AS asset_policy_summary_policy_topic_entries_topics,
  asset.policy_summary.approval_status,
  campaign.id,
  campaign.status,
  campaign.primary_status,
  ad_group.id,
  ad_group.status
FROM
  ad_group_asset
WHERE
  customer.status = 'ENABLED'
  AND asset.policy_summary.approval_status != 'APPROVED'
  AND campaign.status = 'ENABLED'
  AND campaign.primary_status != 'ENDED'
  AND ad_group.status = 'ENABLED'
  AND segments.date DURING LAST_30_DAYS

-- ===== ORIGEM: google-marketing-solutions/ads-policy-monitor@7d313aead8aa49f2bdfe459cf112a9dfc8e12cf7:cloud_functions/ads_policy_monitor/gaql/campaign_asset.sql:14-34
-- campos fora do catálogo v25: nenhum
SELECT 
  {{ today }} AS event_date,
  customer.id,
  customer.descriptive_name,
  asset.id,
  asset.source,
  asset.type,
  asset.policy_summary.review_status,
  asset.policy_summary.policy_topic_entries:topic AS asset_policy_summary_policy_topic_entries_topics,
  asset.policy_summary.approval_status,
  campaign.id,
  campaign.status,
  campaign.primary_status
FROM
  campaign_asset
WHERE
  customer.status = 'ENABLED'
  AND asset.policy_summary.approval_status != 'APPROVED'
  AND campaign.status = 'ENABLED'
  AND campaign.primary_status != 'ENDED'
  AND segments.date DURING LAST_30_DAYS

-- ===== ORIGEM: google-marketing-solutions/ads-policy-monitor@7d313aead8aa49f2bdfe459cf112a9dfc8e12cf7:cloud_functions/ads_policy_monitor/gaql/customer_asset.sql:14-29
-- campos fora do catálogo v25: nenhum
SELECT
  {{ today }} AS event_date,
  customer.id,
  customer.descriptive_name,
  asset.id,
  asset.source,
  asset.type,
  asset.policy_summary.review_status,
  asset.policy_summary.policy_topic_entries:topic AS asset_policy_summary_policy_topic_entries_topics,
  asset.policy_summary.approval_status
FROM
  customer_asset
WHERE
  customer.status = 'ENABLED'
  AND asset.policy_summary.approval_status != 'APPROVED'
  AND segments.date DURING LAST_30_DAYS

