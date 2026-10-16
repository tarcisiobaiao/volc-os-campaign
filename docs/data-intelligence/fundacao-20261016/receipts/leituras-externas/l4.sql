SELECT k, count(*) FROM (SELECT jsonb_object_keys(payload) k FROM public.raw_events WHERE event_name='volc_sensor_ready' AND ts >= now()-interval '3 days') s GROUP BY 1 ORDER BY 2 DESC LIMIT 30;
SELECT jsonb_typeof(payload->'utm') t, count(*) FROM public.raw_events WHERE event_name='volc_sensor_ready' AND ts >= now()-interval '3 days' GROUP BY 1;
SELECT k, count(*) FROM (SELECT jsonb_object_keys(payload->'utm') k FROM public.raw_events WHERE event_name='volc_sensor_ready' AND ts >= now()-interval '3 days' AND jsonb_typeof(payload->'utm')='object') s GROUP BY 1 ORDER BY 2 DESC;
SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='google_ads_observation' ORDER BY ordinal_position;
