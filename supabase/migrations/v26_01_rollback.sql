-- =============================================================================
-- v26_01_rollback — devolve a ordem de 20260907210000 (so observado_em DESC)
-- =============================================================================
-- Idempotente: sobre a view ja revertida (ou nunca migrada) ela reescreve a
-- mesma definicao. Mantem nome, colunas e tipos, e por isso os dependentes de
-- 20260908120000 continuam de pe.
--
-- So a definicao volta. Dono, grants e COMMENT ficam como estao (o CREATE OR
-- REPLACE VIEW os mantem, e nem a v26_01 nem este rollback os tocam). Assim o
-- rollback devolve o estado exato de antes, com ou sem COMMENT: em producao a
-- view nao tem COMMENT e o repositorio tem. A guarda recusa rodar se reloptions
-- nao forem exatamente security_invoker=true, que o WITH reescreveria.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'v26_01_rollback deve rodar como postgres ou supabase_admin; atual: %', current_user;
  END IF;
  IF to_regclass('public.vw_trafego_meta_insight_latest') IS NULL THEN
    RAISE EXCEPTION 'v26_01_rollback: public.vw_trafego_meta_insight_latest nao existe';
  END IF;
  IF (SELECT coalesce(array_to_string(reloptions, ','), '') FROM pg_class
       WHERE oid = 'public.vw_trafego_meta_insight_latest'::regclass) <> 'security_invoker=true' THEN
    RAISE EXCEPTION '%: reloptions da view nao sao exatamente security_invoker=true; o WITH desta migration as reescreveria',
      'v26_01_rollback';
  END IF;
END
$guarda$;

CREATE OR REPLACE VIEW public.vw_trafego_meta_insight_latest
WITH (security_invoker = true) AS
SELECT DISTINCT ON (
    d.ad_account_ativo_id, d.nivel, d.objeto_externo,
    d.periodo_inicio, d.periodo_fim, d.janela_atribuicao, d.breakdown,
    d.time_increment, d.action_report_time)
  d.meta_insight_daily_id,
  d.ad_account_ativo_id,
  d.provider,
  d.conta_externa,
  d.nivel,
  d.objeto_externo,
  d.periodo_inicio,
  d.periodo_fim,
  d.janela_atribuicao,
  d.breakdown,
  d.time_increment,
  d.action_report_time,
  d.account_timezone,
  d.currency,
  d.completo,
  d.observado_em,
  d.spend,
  d.impressions,
  d.reach,
  d.frequency,
  d.clicks,
  d.inline_link_clicks,
  d.landing_page_views,
  d.cpm,
  d.cpc,
  d.ctr
FROM public.trafego_meta_insight_daily d
ORDER BY
  d.ad_account_ativo_id, d.nivel, d.objeto_externo,
  d.periodo_inicio, d.periodo_fim, d.janela_atribuicao, d.breakdown,
  d.time_increment, d.action_report_time,
  d.observado_em DESC;

COMMIT;
