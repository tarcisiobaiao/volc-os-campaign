\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT n.nspname||'.'||p.proname||'('||pg_get_function_identity_arguments(p.oid)||')' fn, p.prosecdef secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE p.proname ~* '(google_ads|joinads|collection_run|reaper|abandon|coleta)' AND n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1;
SELECT conrelid::regclass, conname, pg_get_constraintdef(oid) FROM pg_constraint
 WHERE conrelid::regclass::text IN ('google_ads_collection_run','joinads_collection_run','google_ads_observation','joinads_observation','google_ads_raw_batch','joinads_raw_batch') AND contype IN ('c','u','f') ORDER BY 1,2;
SELECT table_name, column_name, is_nullable, column_default FROM information_schema.columns
 WHERE table_schema='public' AND table_name IN ('google_ads_collection_run','joinads_collection_run','google_ads_observation','joinads_observation') AND (column_default IS NOT NULL OR is_nullable='NO') ORDER BY 1, ordinal_position;
SELECT tgrelid::regclass, tgname, pg_get_triggerdef(oid) FROM pg_trigger WHERE NOT tgisinternal AND tgrelid::regclass::text IN ('google_ads_collection_run','joinads_collection_run') ;
ROLLBACK;
