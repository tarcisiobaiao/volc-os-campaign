-- =============================================================================
-- v26_01 — Meta: a projecao corrente do insight prefere a revisao COMPLETA (W15)
-- =============================================================================
-- ⚠️ MIGRATION CANDIDATA. NAO APLICADA. Provada so em PostgreSQL 16 descartavel
--    (backend/tests/test_meta_v26_01_latest_completa.py) e pela suite
--    tools/freedom-lab/db/suites/v26_w15.sh, que roda no lab.sh do Mac.
--
-- DEPENDE DE (nesta ordem): v13_01 → v15_01 → v15_02 →
--   20260907210000_meta_read_model_consistency.sql (cria a view) →
--   20260908000000_meta_insights_escopo.sql. Se 20260908120000 (financeiro
--   conjunto-dia) ja estiver aplicada, as duas views dela continuam de pe: o
--   CREATE OR REPLACE mantem nome, colunas e tipos, e com isso os dependentes.
-- ROLLBACK: v26_01_rollback.sql (devolve a ordem de 20260907210000, so por
--   observado_em).
--
-- O DEFEITO. `vw_trafego_meta_insight_latest` escolhia a revisao mais NOVA do
-- grao, completa ou nao. O D-1 grava o dia completo; uma releitura posterior
-- truncada (pagina acima do teto, conta que caiu no meio) grava revisao nova com
-- `completo = false` — e ela passava a ser "o numero corrente", tirando do
-- painel e do financeiro conjunto-dia o valor completo que ja existia. A
-- recoleta da janela madura (W15, `n8n/volc_meta_insights_dia_recoleta.json`)
-- rele cada dia ate 7 vezes, multiplicando essa chance. Por isso esta migration
-- e PRE-CONDICAO para ligar a recoleta.
--
-- A REGRA. Por grao: a completa mais recente; sem nenhuma completa, a
-- incompleta mais recente (que continua dizendo `completo = false`). Nada e
-- apagado nem somado; a tabela base nao muda.
--
-- O QUE ELA NAO FAZ. Nao trata revisao COMPLETA mais nova que traga uma metrica
-- NULL onde a anterior tinha numero: completa vence, e NULL continua NULL
-- (ausencia nunca vira o numero antigo nem zero). Nao muda grants: os mesmos
-- REVOKE/GRANT de 20260907210000 sao reafirmados, por nome.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
DECLARE
  v_def text;
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'v26_01 deve rodar como postgres ou supabase_admin; atual: %', current_user;
  END IF;
  IF to_regclass('public.vw_trafego_meta_insight_latest') IS NULL THEN
    RAISE EXCEPTION 'v26_01 depende de public.vw_trafego_meta_insight_latest (20260907210000)';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'public' AND table_name = 'trafego_meta_insight_daily'
                    AND column_name = 'completo') THEN
    RAISE EXCEPTION 'v26_01 depende de trafego_meta_insight_daily.completo (20260907210000)';
  END IF;
  v_def := pg_get_viewdef('public.vw_trafego_meta_insight_latest'::regclass, true);
  IF v_def ~* 'completo\s+DESC' THEN
    RAISE EXCEPTION 'v26_01 ja parece aplicada; rode v26_01_rollback.sql antes de reaplicar';
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
  -- v26_01 (W15): revisao COMPLETA vence revisao incompleta do mesmo grao,
  -- mesmo mais nova. So sem nenhuma completa a incompleta mais nova aparece
  -- (e carrega `completo = false` para quem le).
  d.completo DESC,
  d.observado_em DESC;

COMMENT ON VIEW public.vw_trafego_meta_insight_latest IS
  'UMA linha corrente por grao verdadeiro do insight (sem observado_em na identidade). Entre as revisoes do grao vence a COMPLETA mais recente; so sem nenhuma completa vence a incompleta mais recente, com completo=false (v26_01). As revisoes anteriores continuam na tabela base; esta view existe para que somar spend nao conte o mesmo dia duas vezes. ⚠️ reach, frequency, cpm, cpc e ctr continuam NAO ADITIVAS entre linhas.';

REVOKE ALL ON public.vw_trafego_meta_insight_latest FROM PUBLIC;
REVOKE ALL ON public.vw_trafego_meta_insight_latest FROM anon;
REVOKE ALL ON public.vw_trafego_meta_insight_latest FROM authenticated;
REVOKE ALL ON public.vw_trafego_meta_insight_latest FROM service_role;
GRANT SELECT ON public.vw_trafego_meta_insight_latest TO service_role;

COMMIT;
