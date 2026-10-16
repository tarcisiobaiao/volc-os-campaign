SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='joinads_observation_latest' ORDER BY ordinal_position;
SELECT endpoint, grain, custom_key, count(*), min(metric_date), max(metric_date) FROM public.joinads_observation GROUP BY 1,2,3 ORDER BY 1,2,3;
