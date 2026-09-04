-- =============================================================================
-- v15_99 — rollback explicito do read model Meta Ads
-- =============================================================================
-- Destrutivo para os snapshots e recibos Meta; nao toca no Cofre nem em v9/v10.
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'v15_99 deve rodar como postgres ou supabase_admin; atual: %', current_user;
  END IF;
END
$guarda$;

DROP TRIGGER IF EXISTS trafego_meta_sync_run_sem_delete ON public.trafego_meta_sync_run;
DROP TRIGGER IF EXISTS trafego_meta_ad_creative_binding_sem_delete ON public.trafego_meta_ad_creative_binding;
DROP TRIGGER IF EXISTS trafego_meta_creative_sem_delete ON public.trafego_meta_creative;
DROP TRIGGER IF EXISTS trafego_meta_ad_sem_delete ON public.trafego_meta_ad;
DROP TRIGGER IF EXISTS trafego_meta_adset_sem_delete ON public.trafego_meta_adset;
DROP TRIGGER IF EXISTS trafego_meta_campaign_sem_delete ON public.trafego_meta_campaign;
DROP TRIGGER IF EXISTS trafego_meta_project_binding_sem_delete ON public.trafego_meta_project_binding;
DROP TRIGGER IF EXISTS trafego_meta_ad_account_sem_delete ON public.trafego_meta_ad_account;
DROP TRIGGER IF EXISTS trafego_meta_business_sem_delete ON public.trafego_meta_business;

DROP FUNCTION IF EXISTS public.trafego_meta_persistir_snapshot(jsonb);
DROP TABLE IF EXISTS public.trafego_meta_custom_measurement;
DROP TABLE IF EXISTS public.trafego_meta_insight_action;
DROP TABLE IF EXISTS public.trafego_meta_insight_daily;
DROP TABLE IF EXISTS public.trafego_meta_sync_run;
DROP TABLE IF EXISTS public.trafego_meta_ad_creative_binding;
DROP TABLE IF EXISTS public.trafego_meta_ad;
DROP TABLE IF EXISTS public.trafego_meta_creative;
DROP TABLE IF EXISTS public.trafego_meta_adset;
DROP TABLE IF EXISTS public.trafego_meta_campaign;
DROP TABLE IF EXISTS public.trafego_meta_project_binding;
DROP TABLE IF EXISTS public.trafego_meta_ad_account;
DROP TABLE IF EXISTS public.trafego_meta_business;
DROP FUNCTION IF EXISTS public.trafego_meta_recusa_delete();

COMMIT;
