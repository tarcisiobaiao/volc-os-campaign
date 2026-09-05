-- Rollback da autoridade duravel do nascimento Meta PAUSED.
--
-- ⚠️ Inverso EXATO do apply, e a ordem importa duas vezes:
--   1. funcoes antes das tabelas, porque `trafego_meta_exigir_service_role` e
--      chamada por todas as outras;
--   2. `trafego_meta_create_step` antes de `trafego_meta_create_approval`, e
--      `trafego_meta_create_approval` antes de
--      `trafego_meta_validation_receipt` — cada uma referencia a seguinte com
--      ON DELETE RESTRICT, entao dropar fora de ordem falha.
--
-- Cada `DROP FUNCTION` cita a assinatura COMPLETA de proposito: `trafego_meta_
-- create_approve` mudou de aridade quando ganhou o vinculo com o recibo de
-- validacao, e um DROP por nome so mascararia um dia em que existissem duas
-- sobrecargas.
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
DROP FUNCTION IF EXISTS public.trafego_meta_create_approval_manifest(uuid);
DROP FUNCTION IF EXISTS public.trafego_meta_create_validation_lookup(uuid);
DROP FUNCTION IF EXISTS public.trafego_meta_create_flag_readback(uuid,text);
DROP FUNCTION IF EXISTS public.trafego_meta_create_resolve_absent(uuid,text,integer);
DROP FUNCTION IF EXISTS public.trafego_meta_create_fail_step(uuid,text);
DROP FUNCTION IF EXISTS public.trafego_meta_create_mark_ambiguous(uuid);
DROP FUNCTION IF EXISTS public.trafego_meta_create_close_step(uuid,text);
DROP FUNCTION IF EXISTS public.trafego_meta_create_prepare_step(text,uuid,text,text,text);
DROP FUNCTION IF EXISTS public.trafego_meta_create_approve(text,text,text,bigint,text,timestamptz,text[],uuid,integer,boolean,jsonb);
DROP FUNCTION IF EXISTS public.trafego_meta_create_record_validation(text,text,text,text,text[],text[],integer,integer);
DROP FUNCTION IF EXISTS public.trafego_meta_exigir_service_role();
DROP TABLE IF EXISTS public.trafego_meta_create_step;
DROP TABLE IF EXISTS public.trafego_meta_create_approval;
DROP TABLE IF EXISTS public.trafego_meta_validation_receipt;

COMMIT;
