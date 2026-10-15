-- PROPOSTAS (não aplicadas) de GAQL para o VOLC, derivadas das extrações + lacunas medidas.
-- Estilo do VOLC: estado ATUAL sem segments.date (sem o viés de linha-zero), resource_name como id.
-- Cada SELECT foi conferido com volc_ads.gads.catalogo.invalidos() (catálogo do SERVIDOR v25): ver
-- conferencia_propostas.json. O catálogo não tem selectable_with: compatibilidade campo×FROM e
-- aceitação do WHERE exigem validate_only (pesquisador A) antes de integrar.

-- P1 alvo volc_ads/coleta/familias/estado.py — política POR ASSET dentro do anúncio (RSA, RDA, Demand Gen).
-- Hoje o VOLC lê ad_group_ad_asset_view só na família asset (field_type/performance_label, com
-- metrics.impressions > 0): asset reprovado e sem impressão é invisível. policy_summary nunca é lido.
SELECT ad_group_ad_asset_view.resource_name, ad_group_ad_asset_view.field_type, ad_group_ad_asset_view.enabled, ad_group_ad_asset_view.policy_summary, ad_group.id, campaign.id FROM ad_group_ad_asset_view WHERE ad_group_ad_asset_view.enabled = TRUE AND ad_group.status != 'REMOVED' AND campaign.status != 'REMOVED';

-- P2 alvo estado.py — asset em nível de GRUPO (sitelink/callout/imagem de grupo) e de CONTA.
-- ads-policy-monitor lê os três vínculos (customer/campaign/ad_group_asset); o VOLC só lê campaign_asset
-- e sem a política do asset.
SELECT ad_group_asset.resource_name, ad_group_asset.status, ad_group_asset.primary_status, ad_group_asset.primary_status_reasons, ad_group_asset.primary_status_details, asset.policy_summary.approval_status, asset.policy_summary.review_status, asset.policy_summary.policy_topic_entries, ad_group.id, campaign.id FROM ad_group_asset WHERE ad_group_asset.status != 'REMOVED' AND ad_group.status != 'REMOVED' AND campaign.status != 'REMOVED';
SELECT customer_asset.resource_name, customer_asset.status, customer_asset.primary_status, customer_asset.primary_status_reasons, customer_asset.primary_status_details, asset.policy_summary.approval_status, asset.policy_summary.review_status, asset.policy_summary.policy_topic_entries FROM customer_asset WHERE customer_asset.status != 'REMOVED';

-- P3 alvo estado.py GAQLS["campaign_asset"] — acrescentar a política do asset vinculado + detalhes.
SELECT campaign_asset.resource_name, campaign_asset.status, campaign_asset.primary_status, campaign_asset.primary_status_reasons, campaign_asset.primary_status_details, asset.policy_summary.approval_status, asset.policy_summary.review_status, asset.policy_summary.policy_topic_entries, campaign.id, campaign.status FROM campaign_asset WHERE campaign_asset.status != 'REMOVED' AND campaign.status != 'REMOVED';

-- P4 alvo estado.py GAQLS["keyword"] — motivo de reprovação e "raramente veiculada".
SELECT ad_group_criterion.resource_name, ad_group_criterion.criterion_id, ad_group_criterion.status, ad_group_criterion.primary_status, ad_group_criterion.primary_status_reasons, ad_group_criterion.approval_status, ad_group_criterion.disapproval_reasons, ad_group_criterion.system_serving_status, ad_group.id, campaign.id FROM ad_group_criterion WHERE ad_group_criterion.type = 'KEYWORD' AND ad_group_criterion.status != 'REMOVED' AND ad_group.status != 'REMOVED' AND campaign.status != 'REMOVED';

-- P5 alvo estado.py (novo) ou observabilidade_pmax/queries.py — temas de pesquisa/sinais PMax reprovados.
SELECT asset_group_signal.resource_name, asset_group_signal.approval_status, asset_group_signal.disapproval_reasons, asset_group_signal.search_theme.text, asset_group.id, campaign.id FROM asset_group_signal WHERE asset_group.status != 'REMOVED' AND campaign.status != 'REMOVED';

-- P6 alvo volc_ads/coleta/familias/placement.py — tipo de canal da campanha na linha (hoje ausente; APG e
-- VET filtram por advertising_channel_type) e métricas de vídeo para YouTube (VET). Opcional; a junção com
-- trafego_inventario_campanha também resolve o canal sem custo de API.
SELECT campaign.id, campaign.advertising_channel_type, segments.date, group_placement_view.placement, group_placement_view.target_url, group_placement_view.placement_type, group_placement_view.display_name, metrics.impressions, metrics.clicks, metrics.interactions, metrics.cost_micros, metrics.conversions, metrics.all_conversions, metrics.conversions_value, metrics.all_conversions_value, metrics.video_trueview_views FROM group_placement_view WHERE segments.date DURING YESTERDAY AND metrics.impressions > 0;
