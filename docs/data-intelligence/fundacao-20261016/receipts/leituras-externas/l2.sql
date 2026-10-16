SELECT tgrelid::regclass AS tabela, tgname, tgenabled FROM pg_trigger WHERE NOT tgisinternal AND tgrelid::regclass::text IN ('joinads_metrics','gam_metrics','google_ads_observation','google_ads_raw_batch','joinads_observation','joinads_raw_batch','raw_events','daily_campaign_metrics','google_ads_collection_run','joinads_collection_run') ORDER BY 1,2;
SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='raw_events' ORDER BY ordinal_position;
SELECT indexrelid::regclass, pg_get_indexdef(indexrelid) FROM pg_index WHERE indrelid='public.raw_events'::regclass;
SELECT * FROM public.google_ads_collection_health;
SELECT collector, collector_version, status, count(*), max(started_at) FROM public.joinads_collection_run GROUP BY 1,2,3 ORDER BY 1,2,3;
SELECT status, count(*), max(started_at) FROM public.google_ads_collection_run GROUP BY 1 ORDER BY 1;
SELECT count(*) AS presos FROM public.google_ads_collection_run WHERE status='running' AND started_at < now()-interval '30 minutes';
SELECT * FROM volc_ops.migracao_evento ORDER BY 1 DESC LIMIT 15;
