-- GAQL extraídas VERBATIM (sintaxe gaarf: AS alias, :campo aninhado, ~N, {macro}).
-- Data 2026-10-14. Conferência: catálogo do servidor v25 do VOLC (volc_ads/google_ads_api/catalogo_gaql_v25.json).
-- O catálogo NÃO tem selectable_with: compatibilidade campo×FROM só se prova com validate_only (pesquisador A).

-- ===== ORIGEM: google-marketing-solutions/arba@72c5661a6e6633d6fcb20428369253bc42ca1d83:queries/ads/keyword_performance.sql:1-40
-- campos fora do catálogo v25: nenhum
-- Copyright 2025 Google LLC
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     https://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

-- Extracts keyword specific metrics by day.

-- @param start_date First date of the period for keyword performance.
-- @param end_date Last date of the period for keyword performance.

SELECT
  segments.date AS date,
  ad_group.id AS ad_group_id,
  ad_group_criterion.criterion_id AS keyword_id,
  metrics.cost_micros / 1e6 AS cost,
  metrics.impressions AS impressions,
  metrics.clicks AS clicks,
  metrics.conversions AS conversions,
  metrics.conversions_value AS conversions_values,
  metrics.historical_quality_score AS quality_score,
  metrics.historical_landing_page_quality_score AS landing_page_experience,
  metrics.historical_creative_quality_score AS ad_relevance,
  metrics.historical_search_predicted_ctr AS expected_ctr,
  metrics.search_budget_lost_absolute_top_impression_share
    AS search_budget_lost_absolute_top_impression_share,
  metrics.search_rank_lost_impression_share AS search_rank_lost_impression_share,
  metrics.search_impression_share AS search_impression_share,
  metrics.search_absolute_top_impression_share AS search_absolute_top_impression_share,
  metrics.search_top_impression_share AS search_top_impression_share
FROM  keyword_view
WHERE

-- ===== ORIGEM: google-marketing-solutions/arba@72c5661a6e6633d6fcb20428369253bc42ca1d83:queries/ads/speed_score.sql:1-21
-- campos fora do catálogo v25: nenhum
-- Copyright 2026 Google LLC
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     https://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

-- Extracts speed score for each landing page.

SELECT
  campaign.id AS campaign_id,
  landing_page_view.unexpanded_final_url AS url,
  metrics.speed_score AS speed_score
FROM landing_page_view

