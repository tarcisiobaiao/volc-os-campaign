-- =============================================================================
-- 20260908120100_meta_financeiro_conjunto_dia_rollback.sql
--
-- Desfaz 20260908120000_meta_financeiro_conjunto_dia.sql.
--
-- O rollback e TOTAL e nao perde dado nenhum: a migration cria apenas VIEWS,
-- e view nao guarda linha. Todo o fato continua em
-- `public.trafego_meta_insight_daily`, intocada.
--
-- A ordem importa: `vw_..._campanha_dia` e `vw_..._conjunto_dia_gam` dependem de
-- `vw_..._conjunto_dia`. Derrubar a base primeiro exigiria CASCADE, e CASCADE
-- num rollback e um jeito de apagar mais do que se pretendia.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'rollback deve rodar como postgres ou supabase_admin; atual: %', current_user;
  END IF;
END
$guarda$;

DROP VIEW IF EXISTS public.vw_trafego_meta_financeiro_campanha_dia;
DROP VIEW IF EXISTS public.vw_trafego_meta_financeiro_conjunto_dia_gam;
DROP VIEW IF EXISTS public.vw_trafego_meta_financeiro_conjunto_dia;

DO $confere$
DECLARE v_sobrou int;
BEGIN
  SELECT count(*) INTO v_sobrou
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relname LIKE 'vw_trafego_meta_financeiro%';
  IF v_sobrou > 0 THEN
    RAISE EXCEPTION 'rollback incompleto: % view(s) financeira(s) sobraram', v_sobrou;
  END IF;
  IF to_regclass('public.trafego_meta_insight_daily') IS NULL THEN
    RAISE EXCEPTION 'rollback derrubou o fato — isto nunca pode acontecer';
  END IF;
  RAISE NOTICE 'meta_financeiro rollback OK: 0 views, fato preservado';
END
$confere$;

COMMIT;
