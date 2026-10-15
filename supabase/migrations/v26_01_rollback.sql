-- =============================================================================
-- v26_01_rollback — devolve a ordem de 20260907210000 (so observado_em DESC)
-- =============================================================================
-- Idempotente: sobre a view ja revertida (ou nunca migrada) ela reescreve a
-- mesma definicao. Mantem nome, colunas e tipos, e por isso os dependentes de
-- 20260908120000 continuam de pe. Grants reafirmados por nome.
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

COMMENT ON VIEW public.vw_trafego_meta_insight_latest IS
  'UMA linha corrente por grao verdadeiro do insight (sem observado_em na identidade). As revisoes anteriores continuam na tabela base; esta view existe para que somar spend nao conte o mesmo dia duas vezes. ⚠️ reach, frequency, cpm, cpc e ctr continuam NAO ADITIVAS entre linhas.';

REVOKE ALL ON public.vw_trafego_meta_insight_latest FROM PUBLIC;
REVOKE ALL ON public.vw_trafego_meta_insight_latest FROM anon;
REVOKE ALL ON public.vw_trafego_meta_insight_latest FROM authenticated;
REVOKE ALL ON public.vw_trafego_meta_insight_latest FROM service_role;
GRANT SELECT ON public.vw_trafego_meta_insight_latest TO service_role;

COMMIT;
