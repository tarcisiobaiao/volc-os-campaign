\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT string_agg(column_name||':'||data_type, ', ' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='public' AND table_name='raw_events';
SELECT pg_get_indexdef(indexrelid) FROM pg_index WHERE indrelid='public.raw_events'::regclass;
ROLLBACK;
