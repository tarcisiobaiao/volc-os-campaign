-- Rollback da autoridade duravel do nascimento Meta PAUSED.
\set ON_ERROR_STOP on
BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'rollback meta_create_paused_executor deve rodar como postgres ou supabase_admin';
  END IF;
END
$guarda$;

DROP FUNCTION IF EXISTS public.trafego_meta_create_receipt(uuid);
DROP FUNCTION IF EXISTS public.trafego_meta_create_fail_step(uuid,text);
DROP FUNCTION IF EXISTS public.trafego_meta_create_mark_ambiguous(uuid);
DROP FUNCTION IF EXISTS public.trafego_meta_create_close_step(uuid,text);
DROP FUNCTION IF EXISTS public.trafego_meta_create_prepare_step(text,uuid,text,text,text);
DROP FUNCTION IF EXISTS public.trafego_meta_create_approve(text,text,text,bigint,timestamptz,text[]);
DROP FUNCTION IF EXISTS public.trafego_meta_exigir_service_role();
DROP TABLE IF EXISTS public.trafego_meta_create_step;
DROP TABLE IF EXISTS public.trafego_meta_create_approval;

COMMIT;
