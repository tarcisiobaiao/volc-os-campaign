\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname IN ('update_all_revenue_converted','trigger_new_revenue_conversion_daily_campaign','trigger_new_revenue_conversion_gam','sync_joinads_revenue_to_daily_metrics');
SELECT '##hist', effective_date, rate, created_at, left(coalesce(notes,''),60) FROM exchange_rate_history ORDER BY effective_date DESC, created_at DESC LIMIT 12;
SELECT '##hist_n', count(*), min(effective_date), max(effective_date) FROM exchange_rate_history;
SELECT '##settings', key, value, updated_at FROM system_settings WHERE key IN ('dollar_exchange_rate','usd_brl_rate');
SELECT '##cols_joinads_metrics', string_agg(column_name||':'||data_type, ', ' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='joinads_metrics';
ROLLBACK;
