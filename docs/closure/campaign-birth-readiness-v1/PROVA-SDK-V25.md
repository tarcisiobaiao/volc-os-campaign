# Contraprova executável — descritores reais do SDK v25 (01/09/2026)
Rodado em backend/.venv (google-ads v25), sem rede, sem conta.

## Recursos de meta efetiva — EXISTEM, com estes campos e nenhum outro
CustomerConversionGoal        : biddable, category, origin, resource_name
CampaignConversionGoal        : biddable, campaign, category, origin, resource_name
ConversionGoalCampaignConfig  : campaign, custom_conversion_goal, goal_config_level, resource_name

⚠️ CustomerConversionGoal NÃO tem `campaign`. É de conta, e por isso a meta efetiva
   exige DUAS leituras + o nível — nunca uma só.

GoalConfigLevel = UNSPECIFIED | UNKNOWN | CUSTOMER | CAMPAIGN
⚠️ UNSPECIFIED e UNKNOWN existem e NÃO são CUSTOMER. Tratá-los como CUSTOMER seria
   inventar herança onde a API não afirmou nada.

## ConversionAction — identidade e dono
Campos (22): app_id, attribution_model_settings, category, click_through_lookback_window_days,
counting_type, firebase_settings, google_analytics_4_settings, id, include_in_conversions_metric,
mobile_app_vendor, name, origin, owner_customer, phone_call_duration_seconds, primary_for_goal,
resource_name, status, tag_snippets, third_party_app_analytics_settings, type_, value_settings,
view_through_lookback_window_days

⚠️ `owner_customer` EXISTE — é ele que resolve o dono da ação (aceite 3 e 6).
⚠️ O campo Python é `type_`, o proto é `type`. Em GAQL selecionar `conversion_action.type`.
⚠️ `include_in_conversions_metric` continua presente em v25 (depreciado em favor de
   primary_for_goal, não removido). Ler os dois e NÃO colapsar.

ConversionActionStatus  = UNSPECIFIED | UNKNOWN | ENABLED | REMOVED | HIDDEN
  ⚠️ HIDDEN existe. `status != REMOVED` inclui HIDDEN; `status = ENABLED` exclui.
ConversionActionCategory (24) inclui PURCHASE, DOWNLOAD, DEFAULT, PAGE_VIEW, SIGNUP, ...
ConversionOrigin = UNSPECIFIED | UNKNOWN | WEBSITE | GOOGLE_HOSTED | APP | CALL_FROM_ADS
                 | STORE | YOUTUBE_HOSTED | LOCAL_SERVICES_ADS
ConversionActionType inclui WEBPAGE, UPLOAD_CLICKS, STORE_SALES (destinos Data Manager),
  além de WEBPAGE_CODELESS, UPLOAD_CALLS, STORE_SALES_DIRECT_UPLOAD e 40+ outros.

## Customer.conversion_tracking_setting — campos reais
accepted_customer_data_terms, conversion_tracking_id, conversion_tracking_status,
cross_account_conversion_tracking_id, enhanced_conversions_for_leads_enabled,
google_ads_conversion_customer

⚠️ `google_ads_conversion_customer` é QUEM é o dono do tracking (a conta que centraliza).
customer.auto_tagging_enabled e customer.remarketing_setting existem.
