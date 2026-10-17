\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname IN ('get_current_dollar_rate','get_current_usd_brl_rate','get_dollar_exchange_rate','get_exchange_rate_for_date','calculate_revenue_converted','calculate_revenue_converted_by_date','sync_dollar_rates','record_exchange_rate_change','on_exchange_rate_change','trigger_update_revenue_conversions');
SELECT tgrelid::regclass, tgname, pg_get_triggerdef(oid) FROM pg_trigger WHERE NOT tgisinternal AND pg_get_triggerdef(oid) ~* '(revenue_conver|exchange|dollar)';
ROLLBACK;
