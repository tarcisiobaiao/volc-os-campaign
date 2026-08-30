-- Rollback v12_01. Destrutivo: exportar as tres tabelas antes de executar.
BEGIN;
DROP FUNCTION IF EXISTS public.volc_registrar_google_inteligencia(jsonb);
DROP TABLE IF EXISTS public.trafego_google_inteligencia_metrica;
DROP TABLE IF EXISTS public.trafego_google_inteligencia_item;
DROP TABLE IF EXISTS public.trafego_google_inteligencia_coleta;
DROP FUNCTION IF EXISTS public.trafego_google_inteligencia_append_only();
NOTIFY pgrst, 'reload schema';
COMMIT;
