-- =============================================================================
-- v15_98 — rollback explicito do read model de insights Meta Ads
-- =============================================================================
-- Destrutivo para fatos/agregados de insights Meta. Nao toca no read model de
-- hierarquia v15_01 nem no Cofre.
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'v15_98 deve rodar como postgres ou supabase_admin; atual: %', current_user;
  END IF;
END
$guarda$;

DROP TABLE IF EXISTS public.trafego_meta_custom_measurement;
DROP TABLE IF EXISTS public.trafego_meta_insight_action;
DROP TABLE IF EXISTS public.trafego_meta_insight_daily;
DROP FUNCTION IF EXISTS public.trafego_meta_persistir_snapshot(jsonb);

COMMIT;
