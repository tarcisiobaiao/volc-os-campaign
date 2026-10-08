-- Rollback da v17_01. Só remove o que a v17_01 criou; não toca v12_04 nem legado.
-- ⚠️ Recusa se houver fato gravado: apagar histórico medido não é rollback de schema.
BEGIN;
DO $$
BEGIN
  IF to_regclass('public.google_ads_fato_granular') IS NOT NULL
     AND (EXISTS (SELECT 1 FROM public.google_ads_fato_granular)
          OR EXISTS (SELECT 1 FROM public.google_ads_mudanca)
          OR EXISTS (SELECT 1 FROM public.google_ads_estado)) THEN
    RAISE EXCEPTION 'v17_01_rollback recusado: há fatos gravados; exporte antes de apagar';
  END IF;
END $$;
DROP VIEW IF EXISTS public.vw_gads_arbitragem_hora;
DROP VIEW IF EXISTS public.vw_gads_arbitragem_placement_dia;
DROP VIEW IF EXISTS public.vw_gads_arbitragem_campanha_dia;
DROP VIEW IF EXISTS public.vw_gads_campanha_dia;
DROP FUNCTION IF EXISTS public.volc_registrar_gads_fatos(jsonb);
DROP TABLE IF EXISTS public.google_ads_estado;
DROP TABLE IF EXISTS public.google_ads_mudanca;
DROP TABLE IF EXISTS public.google_ads_fato_granular;
DROP FUNCTION IF EXISTS public.google_ads_append_only();
DROP FUNCTION IF EXISTS public.volc_gads_num(jsonb, text);
DROP FUNCTION IF EXISTS public.volc_dominio(text);
DROP FUNCTION IF EXISTS public.volc_sha256(text);
NOTIFY pgrst, 'reload schema';
COMMIT;
