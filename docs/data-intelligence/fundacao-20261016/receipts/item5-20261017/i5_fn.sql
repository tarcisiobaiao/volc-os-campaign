\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_get_functiondef('public.volc_finish_google_ads_run(jsonb)'::regprocedure);
SELECT pg_get_functiondef('public.volc_ingest_google_ads_batch_auto(jsonb)'::regprocedure);
SELECT pg_get_functiondef('public.volc_ingest_google_ads_batch(jsonb)'::regprocedure);
SELECT pg_get_functiondef('public.joinads_guard_run_update()'::regprocedure);
SELECT grantee, privilege_type, table_name FROM information_schema.role_table_grants WHERE table_name IN ('joinads_collection_run','joinads_raw_batch','joinads_observation','google_ads_collection_run') AND grantee IN ('anon','authenticated','service_role') ORDER BY 3,1,2;
ROLLBACK;
