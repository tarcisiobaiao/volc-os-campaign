-- =============================================================================
-- dq_01 — Views candidatas de observabilidade e data quality (Fundação DIL, thread G)
-- MIGRATION CANDIDATA. NÃO APLICADA EM NENHUM BANCO OPERACIONAL.
-- Testada só em PostgreSQL 16 descartável (tests/data-intelligence/fundacao/test_qualidade_pg_views.py).
-- Rollback: dq_01_views_qualidade.down.sql
-- Leitura em produção SEM criar nada: selects_somente_leitura.sql (gerado deste arquivo).
-- Doc: docs/data-intelligence/fundacao-20261016/09-OBSERVABILIDADE.md
-- Espelho Python (mesma semântica, testado por equivalência): volc_dil.fundacao.qualidade
--
-- Tabelas reais lidas (DDL de referência):
--   Google Ads v21  043c77f5:supabase/migrations/v21_01_google_ads_coleta_canonica.sql (+ v21_02, v21_03)
--   JoinAds v2      192bc065 (wip/historico-joinads-20261015):
--                   supabase/migrations/20261015163704_joinads_collection_canonical.sql
--                   supabase/migrations/20261015170000_joinads_latest_collector_version_guard.sql
--   raw_events      DDL NÃO versionado (R8); usa só ts, event_name, payload (recibo L4)
--
-- Garantias (cada uma com teste):
--   * só views e uma função STABLE; nenhuma escrita, nenhum gatilho, nenhuma tabela;
--   * security_invoker = true em todas as views (quem lê precisa de SELECT nas tabelas-base);
--   * grants: só SELECT para service_role; PUBLIC/anon/authenticated sem nada;
--   * nenhuma view expõe sid/pid (cobertura do sensor é só agregado diário);
--   * "agora" vem de dil_qualidade.agora(): now(), ou o GUC dil_qualidade.agora (só para teste).
-- Marcadores "-- dq:view <nome>" / "-- dq:fim" são lidos pelo gerador de SELECTs; não remover.
-- =============================================================================

BEGIN;

DO $$
BEGIN
  IF to_regclass('public.google_ads_collection_run') IS NULL
     OR to_regclass('public.google_ads_raw_batch') IS NULL
     OR to_regclass('public.google_ads_observation') IS NULL
     OR to_regclass('public.joinads_collection_run') IS NULL
     OR to_regclass('public.joinads_raw_batch') IS NULL
     OR to_regclass('public.joinads_observation') IS NULL
     OR to_regclass('public.joinads_observation_latest') IS NULL
     OR to_regclass('public.raw_events') IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = '42P01',
      MESSAGE = 'dq_01: tabelas-base ausentes (v21 Google Ads, JoinAds v2 e raw_events são pré-requisito)';
  END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS dil_qualidade;
REVOKE ALL ON SCHEMA dil_qualidade FROM PUBLIC;
COMMENT ON SCHEMA dil_qualidade IS
  'Views candidatas de data quality (thread G, Fundação DIL). Somente leitura; security_invoker.';

CREATE OR REPLACE FUNCTION dil_qualidade.agora() RETURNS timestamptz
LANGUAGE sql STABLE
SET search_path = pg_catalog
AS $$
  SELECT coalesce(nullif(current_setting('dil_qualidade.agora', true), '')::timestamptz, now())
$$;
COMMENT ON FUNCTION dil_qualidade.agora() IS
  'now(), salvo se o GUC de sessão dil_qualidade.agora estiver definido (teste/replay determinístico).';

-- dq:view dq_parametros_sla
CREATE VIEW dil_qualidade.dq_parametros_sla WITH (security_invoker = true) AS
SELECT v.fonte, v.coletor_logico, v.grao, v.minuto, v.horas, v.tolerancia, v.timeout_running,
       v.min_linhas, v.folga, v.tz
FROM (VALUES
  ('google_ads'::text, 'n8n-google-ads-d0'::text, 'campaign_day'::text, 7,
   ARRAY[6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23], interval '30 minutes', interval '30 minutes',
   1, interval '10 minutes', 'America/Sao_Paulo'::text),
  ('google_ads', 'n8n-google-ads-d1', 'campaign_day', 17, ARRAY[6,14],
   interval '60 minutes', interval '30 minutes', 1, interval '10 minutes', 'America/Sao_Paulo'),
  ('google_ads', 'n8n-google-ads-terms-keywords', 'search_term_day', 23, ARRAY[0,4,8,12,16,20],
   interval '60 minutes', interval '60 minutes', 1, interval '10 minutes', 'America/Sao_Paulo'),
  ('joinads', 'n8n_joinads_v2:intraday', 'campaign_adunit_day', 15, ARRAY[6,8,10,12,14,16,18,20,22],
   interval '45 minutes', interval '30 minutes', 1, interval '10 minutes', 'America/Sao_Paulo'),
  ('joinads', 'n8n_joinads_v2:d1', 'campaign_adunit_day', 20, ARRAY[6],
   interval '120 minutes', interval '30 minutes', 1, interval '10 minutes', 'America/Sao_Paulo')
) AS v(fonte, coletor_logico, grao, minuto, horas, tolerancia, timeout_running, min_linhas, folga, tz);
-- dq:fim

-- dq:view dq_parametros_limiares
CREATE VIEW dil_qualidade.dq_parametros_limiares WITH (security_invoker = true) AS
SELECT v.nome, v.valor
FROM (VALUES
  ('frescor_slots_parado'::text, 3::numeric),
  ('zero_sintetizado_alto', 0.5),
  ('receita_cobertura_min', 0.90),
  ('receita_cobertura_max', 1.02),
  ('receita_cobertura_critica', 0.50),
  ('custo_d0_d1_tol', 0.05),
  ('custo_d0_d1_alto', 0.25),
  ('sensor_cobertura_min', 0.90),
  ('sensor_cobertura_alto', 0.50),
  ('sensor_amostra_min', 10),
  ('janela_leituras_dias', 14),
  ('janela_reconciliacao_dias', 14)
) AS v(nome, valor);
-- dq:fim

-- dq:view dq_runs
-- Runs unificados. JoinAds v2 usa o mesmo `collector` no intraday e no D-1: o papel sai da janela.
-- Último sinal de vida: v21 = último lote gravado; JoinAds = max(updated_at, último lote).
CREATE VIEW dil_qualidade.dq_runs WITH (security_invoker = true) AS
SELECT 'google_ads'::text AS fonte, r.collector AS coletor_logico, r.run_id::text AS run_id,
       r.collector AS coletor, r.collector_version::text AS versao_coletor, r.status, r.started_at,
       r.finished_at, r.rows_written::bigint AS linhas_escritas, r.batches_written::bigint AS lotes,
       r.window_start, r.window_end,
       (SELECT max(b.collected_at) FROM public.google_ads_raw_batch b WHERE b.run_id = r.run_id) AS ultimo_sinal
FROM public.google_ads_collection_run r
UNION ALL
SELECT 'joinads', r.collector || CASE WHEN r.window_end >= (r.started_at AT TIME ZONE r.timezone)::date
                                      THEN ':intraday' ELSE ':d1' END,
       r.run_key, r.collector, r.collector_version::text, r.status, r.started_at, r.finished_at,
       r.observations_written::bigint, r.batches_written::bigint, r.window_start, r.window_end,
       GREATEST(r.updated_at, (SELECT max(b.collected_at) FROM public.joinads_raw_batch b WHERE b.run_key = r.run_key))
FROM public.joinads_collection_run r;
-- dq:fim

-- dq:view dq_slots
-- Slots esperados em (agora-7d, agora], só nas horas da agenda e a partir do primeiro run do coletor.
CREATE VIEW dil_qualidade.dq_slots WITH (security_invoker = true) AS
WITH s_ag AS (SELECT dil_qualidade.agora() AS agora),
s_prim AS (
  SELECT r.coletor_logico, min(r.started_at) AS primeiro_run
  FROM dil_qualidade.dq_runs r, s_ag WHERE r.started_at <= s_ag.agora GROUP BY 1
)
SELECT p.fonte, p.coletor_logico, p.grao, p.tolerancia, p.folga, p.tz, x.slot,
       (x.slot AT TIME ZONE p.tz)::date AS dia_local,
       extract(hour FROM x.slot AT TIME ZONE p.tz)::int AS hora_local,
       (x.slot + p.tolerancia <= s_ag.agora) AS vencido, s_ag.agora
FROM dil_qualidade.dq_parametros_sla p
CROSS JOIN s_ag
LEFT JOIN s_prim ON s_prim.coletor_logico = p.coletor_logico
CROSS JOIN LATERAL (
  SELECT ((((s_ag.agora AT TIME ZONE p.tz)::date - k.k) + make_time(h.h, p.minuto, 0)) AT TIME ZONE p.tz) AS slot
  FROM generate_series(0, 8) AS k(k) CROSS JOIN unnest(p.horas) AS h(h)
) x
WHERE x.slot > s_ag.agora - interval '7 days' AND x.slot <= s_ag.agora
  AND (s_prim.primeiro_run IS NULL OR x.slot >= s_prim.primeiro_run - p.folga);
-- dq:fim

-- dq:view dq_freshness
CREATE VIEW dil_qualidade.dq_freshness WITH (security_invoker = true) AS
WITH f_ag AS (SELECT dil_qualidade.agora() AS agora),
f_suc AS (
  SELECT r.coletor_logico, max(r.started_at) AS ultimo_sucesso
  FROM dil_qualidade.dq_runs r, f_ag
  WHERE r.status IN ('completed', 'partial') AND r.started_at <= f_ag.agora
  GROUP BY 1
),
f_slot AS (
  SELECT s.coletor_logico,
         max(s.slot) FILTER (WHERE s.vencido) AS slot_referencia,
         count(*) FILTER (WHERE s.vencido AND (f_suc.ultimo_sucesso IS NULL
                                               OR s.slot > f_suc.ultimo_sucesso + s.folga)) AS slots_perdidos
  FROM dil_qualidade.dq_slots s LEFT JOIN f_suc USING (coletor_logico)
  GROUP BY 1
),
f_lim AS (SELECT valor AS parado FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'frescor_slots_parado')
SELECT p.fonte, p.coletor_logico, p.grao, f_suc.ultimo_sucesso, f_slot.slot_referencia,
       coalesce(f_slot.slots_perdidos, 0) AS slots_perdidos,
       f_ag.agora - f_suc.ultimo_sucesso AS idade,
       CASE WHEN f_suc.ultimo_sucesso IS NULL THEN 'sem_registro'
            WHEN coalesce(f_slot.slots_perdidos, 0) = 0 THEN 'fresco'
            WHEN f_slot.slots_perdidos < f_lim.parado THEN 'atrasado'
            ELSE 'parado' END AS estado,
       CASE WHEN f_suc.ultimo_sucesso IS NULL THEN 'critico'
            WHEN coalesce(f_slot.slots_perdidos, 0) = 0 THEN 'ok'
            WHEN f_slot.slots_perdidos < f_lim.parado THEN 'aviso'
            ELSE 'alto' END AS severidade
FROM dil_qualidade.dq_parametros_sla p
CROSS JOIN f_ag CROSS JOIN f_lim
LEFT JOIN f_suc ON f_suc.coletor_logico = p.coletor_logico
LEFT JOIN f_slot ON f_slot.coletor_logico = p.coletor_logico;
-- dq:fim

-- dq:view dq_completude_hora
-- Um registro por slot esperado: falha_declarada (o run registrou falha) ≠ ausente_silencioso
-- (nenhum registro); slot com prazo aberto é pendente, nunca buraco.
CREATE VIEW dil_qualidade.dq_completude_hora WITH (security_invoker = true) AS
SELECT c.fonte, c.coletor_logico, c.slot, c.dia_local, c.hora_local, c.n_runs, c.classe,
       CASE c.classe WHEN 'ok' THEN 'ok' WHEN 'pendente' THEN 'ok' WHEN 'parcial' THEN 'info'
                     WHEN 'em_execucao' THEN 'info' ELSE 'aviso' END AS severidade
FROM (
  SELECT s.fonte, s.coletor_logico, s.slot, s.dia_local, s.hora_local, count(r.run_id) AS n_runs,
         CASE WHEN bool_or(r.status = 'completed') THEN 'ok'
              WHEN bool_or(r.status = 'partial') THEN 'parcial'
              WHEN bool_or(r.status = 'running') THEN 'em_execucao'
              WHEN bool_or(r.status = 'failed') THEN 'falha_declarada'
              WHEN s.vencido THEN 'ausente_silencioso'
              ELSE 'pendente' END AS classe
  FROM dil_qualidade.dq_slots s
  LEFT JOIN dil_qualidade.dq_runs r
    ON r.coletor_logico = s.coletor_logico
   AND r.started_at >= s.slot - s.folga AND r.started_at < s.slot + s.tolerancia
   AND r.started_at <= s.agora
  GROUP BY s.fonte, s.coletor_logico, s.slot, s.dia_local, s.hora_local, s.vencido
) c;
-- dq:fim

-- dq:view dq_runs_orfaos
-- `running` além do timeout e sem sinal de vida dentro do timeout (os 3 de 15/10 11:48 são o 1º caso real).
CREATE VIEW dil_qualidade.dq_runs_orfaos WITH (security_invoker = true) AS
WITH o_ag AS (SELECT dil_qualidade.agora() AS agora)
SELECT r.fonte, r.coletor_logico, r.run_id, r.started_at, r.ultimo_sinal, r.lotes,
       o_ag.agora - r.started_at AS idade,
       coalesce(p.timeout_running, interval '30 minutes') AS timeout,
       'alto'::text AS severidade
FROM dil_qualidade.dq_runs r
CROSS JOIN o_ag
LEFT JOIN dil_qualidade.dq_parametros_sla p ON p.coletor_logico = r.coletor_logico
WHERE r.status = 'running'
  AND r.started_at <= o_ag.agora
  AND r.started_at < o_ag.agora - coalesce(p.timeout_running, interval '30 minutes')
  AND coalesce(r.ultimo_sinal, r.started_at) < o_ag.agora - coalesce(p.timeout_running, interval '30 minutes');
-- dq:fim

-- dq:view dq_falha_silenciosa
-- Run concluído (completed|partial) com 0 linhas onde o contrato espera > 0. NULL não dispara.
CREATE VIEW dil_qualidade.dq_falha_silenciosa WITH (security_invoker = true) AS
WITH fs_ag AS (SELECT dil_qualidade.agora() AS agora)
SELECT r.fonte, r.coletor_logico, r.run_id, r.status, r.started_at, r.finished_at, r.linhas_escritas,
       p.min_linhas, 'concluido_sem_linhas'::text AS classe, 'alto'::text AS severidade
FROM dil_qualidade.dq_runs r
JOIN dil_qualidade.dq_parametros_sla p ON p.coletor_logico = r.coletor_logico
CROSS JOIN fs_ag
WHERE r.status IN ('completed', 'partial') AND r.linhas_escritas = 0 AND p.min_linhas > 0
  AND r.started_at > fs_ag.agora - interval '7 days' AND r.started_at <= fs_ag.agora;
-- dq:fim

-- dq:view dq_duplicacao
-- no_run: mesma chave no mesmo run (conflito = payloads diferentes). entre_runs: mesma chave em
-- >= 2 runs; mesma coleta (collected_at) em runs diferentes = reingestão suspeita; o resto é
-- releitura esperada (idêntica ou com revisão/maturação).
CREATE VIEW dil_qualidade.dq_duplicacao WITH (security_invoker = true) AS
WITH d_ag AS (SELECT dil_qualidade.agora() AS agora),
d_lim AS (SELECT valor AS dias FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'janela_leituras_dias'),
d_leit AS (
  SELECT 'google_ads'::text AS fonte, o.grain AS grao, o.observation_key AS chave, o.run_id::text AS run_id,
         o.collected_at, md5(o.metrics::text) AS payload
  FROM public.google_ads_observation o
  UNION ALL
  SELECT 'joinads', o.grain,
         concat_ws('|', o.endpoint, o.grain, coalesce(o.metric_date::text, ''), coalesce(o.metric_hour::text, ''),
                   coalesce(o.domain, ''), coalesce(o.campaign_id, ''), coalesce(o.custom_key, ''),
                   coalesce(o.custom_value, ''), coalesce(o.post_id, ''), coalesce(o.land_uri, ''),
                   coalesce(o.ad_unit_name, ''), coalesce(o.country_iso, '')),
         o.run_key, o.collected_at,
         md5(jsonb_build_object(
           'revenue_gross', o.revenue_gross, 'revenue_client', o.revenue_client, 'impressions', o.impressions,
           'clicks', o.clicks, 'requests_served', o.requests_served, 'unfilled', o.unfilled,
           'active_view', o.active_view, 'pmr', o.pmr, 'ctr', o.ctr, 'ecpm_gross', o.ecpm_gross,
           'ecpm_client', o.ecpm_client, 'pageviews', o.pageviews, 'unique_views', o.unique_views,
           'first_views', o.first_views)::text)
  FROM public.joinads_observation o
),
d_jan AS (
  SELECT l.* FROM d_leit l, d_ag, d_lim
  WHERE l.collected_at > d_ag.agora - make_interval(days => d_lim.dias::int) AND l.collected_at <= d_ag.agora
),
d_no_run AS (
  SELECT fonte, grao, chave, 'no_run'::text AS escopo, run_id, count(*) AS n_leituras, 1::bigint AS n_runs,
         count(DISTINCT payload) AS n_payloads,
         CASE WHEN count(DISTINCT payload) > 1 THEN 'conflito_no_run' ELSE 'duplicata_exata_no_run' END AS classe
  FROM d_jan GROUP BY fonte, grao, chave, run_id HAVING count(*) > 1
),
d_coleta AS (
  SELECT fonte, grao, chave, max(n) AS max_runs_mesma_coleta
  FROM (SELECT fonte, grao, chave, collected_at, count(DISTINCT run_id) AS n
        FROM d_jan GROUP BY fonte, grao, chave, collected_at) z
  GROUP BY fonte, grao, chave
),
d_entre AS (
  SELECT j.fonte, j.grao, j.chave, 'entre_runs'::text AS escopo, NULL::text AS run_id, count(*) AS n_leituras,
         count(DISTINCT j.run_id) AS n_runs, count(DISTINCT j.payload) AS n_payloads,
         CASE WHEN max(c.max_runs_mesma_coleta) >= 2 THEN 'reingestao_suspeita'
              WHEN count(DISTINCT j.payload) = 1 THEN 'releitura_identica'
              ELSE 'releitura_com_revisao' END AS classe
  FROM d_jan j JOIN d_coleta c USING (fonte, grao, chave)
  GROUP BY j.fonte, j.grao, j.chave HAVING count(DISTINCT j.run_id) >= 2
)
SELECT u.*, CASE u.classe WHEN 'conflito_no_run' THEN 'critico' WHEN 'duplicata_exata_no_run' THEN 'aviso'
                          WHEN 'reingestao_suspeita' THEN 'aviso' ELSE 'info' END AS severidade
FROM (SELECT * FROM d_no_run UNION ALL SELECT * FROM d_entre) u;
-- dq:fim

-- dq:view dq_zero_sintetizado
-- R3: zero gravado para campanha listada sem linha de métrica (payload bruto `metrics = {}`).
-- Métrica ausente/não numérica = nulo (nunca zero). Zero com linha = zero com prova.
CREATE VIEW dil_qualidade.dq_zero_sintetizado WITH (security_invoker = true) AS
WITH z_ag AS (SELECT dil_qualidade.agora() AS agora),
z_lim AS (SELECT
  (SELECT valor FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'janela_leituras_dias') AS dias,
  (SELECT valor FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'zero_sintetizado_alto') AS alto),
z_cls AS (
  SELECT r.collector AS coletor, o.metric_date,
         CASE WHEN jsonb_typeof(o.metrics -> 'cost_micros') IS DISTINCT FROM 'number'
                OR jsonb_typeof(o.metrics -> 'impressions') IS DISTINCT FROM 'number' THEN 'nulo'
              WHEN (o.metrics ->> 'cost_micros')::numeric <> 0
                OR (o.metrics ->> 'impressions')::numeric <> 0 THEN 'com_valor'
              WHEN jsonb_typeof(b.payload -> 'metrics') = 'object' AND (b.payload -> 'metrics') <> '{}'::jsonb
                THEN 'zero_com_linha'
              WHEN jsonb_typeof(b.payload -> 'metrics') = 'object' THEN 'sintetizado'
              ELSE 'ambiguo' END AS classe
  FROM public.google_ads_observation o
  JOIN public.google_ads_raw_batch b ON b.batch_id = o.batch_id
  JOIN public.google_ads_collection_run r ON r.run_id = o.run_id
  CROSS JOIN z_ag CROSS JOIN z_lim
  WHERE o.grain = 'campaign_day'
    AND o.collected_at > z_ag.agora - make_interval(days => z_lim.dias::int) AND o.collected_at <= z_ag.agora
),
z_agg AS (
  SELECT coletor, metric_date, count(*) AS total,
         count(*) FILTER (WHERE classe IN ('zero_com_linha', 'sintetizado', 'ambiguo')) AS zeros,
         count(*) FILTER (WHERE classe = 'sintetizado') AS sintetizados,
         count(*) FILTER (WHERE classe = 'zero_com_linha') AS zeros_com_linha,
         count(*) FILTER (WHERE classe = 'ambiguo') AS ambiguos,
         count(*) FILTER (WHERE classe = 'nulo') AS nulos
  FROM z_cls GROUP BY coletor, metric_date
)
SELECT 'google_ads'::text AS fonte, a.coletor, 'campaign_day'::text AS grao, a.metric_date, a.total, a.zeros,
       a.sintetizados, a.zeros_com_linha, a.ambiguos, a.nulos,
       round(a.sintetizados::numeric / a.total, 4) AS proporcao_sintetizada,
       CASE WHEN round(a.sintetizados::numeric / a.total, 4) >= z_lim.alto THEN 'alto'
            WHEN a.sintetizados > 0 THEN 'aviso'
            WHEN a.ambiguos > 0 THEN 'info'
            ELSE 'ok' END AS severidade
FROM z_agg a CROSS JOIN z_lim;
-- dq:fim

-- dq:view dq_reconciliacao_joinads
-- Soma kv por campanha (campaign_id numérico) / earnings de domínio, por dia, sobre a view real
-- joinads_observation_latest. Referência real (L5): 97–100% em 08–16/10.
CREATE VIEW dil_qualidade.dq_reconciliacao_joinads WITH (security_invoker = true) AS
WITH r_ag AS (SELECT dil_qualidade.agora() AS agora),
r_lim AS (SELECT
  (SELECT valor FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'janela_reconciliacao_dias') AS dias,
  (SELECT valor FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'receita_cobertura_min') AS lo,
  (SELECT valor FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'receita_cobertura_max') AS hi,
  (SELECT valor FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'receita_cobertura_critica') AS crit),
r_dia AS (
  SELECT o.metric_date,
         sum(o.revenue_client) FILTER (WHERE o.endpoint = 'earnings') AS earnings,
         sum(o.revenue_client) FILTER (WHERE o.endpoint = 'key_value_campaign_adunit' AND o.campaign_id IS NOT NULL)
           AS receita_kv_campanha,
         sum(o.revenue_client) FILTER (WHERE o.endpoint = 'key_value_campaign_adunit' AND o.campaign_id IS NULL)
           AS receita_kv_sem_campanha,
         count(DISTINCT o.campaign_id) FILTER (WHERE o.endpoint = 'key_value_campaign_adunit') AS n_campanhas,
         count(DISTINCT o.currency_code) AS n_moedas
  FROM public.joinads_observation_latest o, r_ag, r_lim
  WHERE o.metric_date > (r_ag.agora AT TIME ZONE 'America/Sao_Paulo')::date - r_lim.dias::int
  GROUP BY o.metric_date
)
SELECT d.*,
       CASE WHEN d.earnings > 0 AND d.receita_kv_campanha IS NOT NULL
            THEN round(d.receita_kv_campanha / d.earnings, 4) END AS cobertura,
       CASE WHEN d.n_moedas > 1 THEN 'moeda_mista'
            WHEN d.earnings IS NULL OR d.earnings <= 0 THEN 'sem_base'
            WHEN d.receita_kv_campanha IS NULL THEN 'sem_receita_campanha'
            WHEN round(d.receita_kv_campanha / d.earnings, 4) < l.lo THEN 'cobertura_baixa'
            WHEN round(d.receita_kv_campanha / d.earnings, 4) > l.hi THEN 'excesso'
            ELSE 'ok' END AS estado,
       CASE WHEN d.n_moedas > 1 THEN 'alto'
            WHEN d.earnings IS NULL OR d.earnings <= 0 THEN 'info'
            WHEN d.receita_kv_campanha IS NULL THEN 'alto'
            WHEN round(d.receita_kv_campanha / d.earnings, 4) < l.crit THEN 'alto'
            WHEN round(d.receita_kv_campanha / d.earnings, 4) < l.lo THEN 'aviso'
            WHEN round(d.receita_kv_campanha / d.earnings, 4) > l.hi THEN 'alto'
            ELSE 'ok' END AS severidade
FROM r_dia d CROSS JOIN r_lim l;
-- dq:fim

-- dq:view dq_reconciliacao_custo_d0_d1
-- Último D0 bem-sucedido × D-1 fechado (lido em dia local > metric_date), por campanha-dia.
CREATE VIEW dil_qualidade.dq_reconciliacao_custo_d0_d1 WITH (security_invoker = true) AS
WITH c_ag AS (SELECT dil_qualidade.agora() AS agora),
c_lim AS (SELECT
  (SELECT valor FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'janela_reconciliacao_dias') AS dias,
  (SELECT valor FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'custo_d0_d1_tol') AS tol,
  (SELECT valor FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'custo_d0_d1_alto') AS alto),
c_base AS (
  SELECT r.collector, o.customer_id, o.campaign_id, o.metric_date, o.collected_at, o.metrics
  FROM public.google_ads_observation o
  JOIN public.google_ads_collection_run r ON r.run_id = o.run_id
  CROSS JOIN c_ag CROSS JOIN c_lim
  WHERE o.grain = 'campaign_day' AND o.metric_date IS NOT NULL AND r.status IN ('completed', 'partial')
    AND o.collected_at <= c_ag.agora
    AND o.metric_date > (c_ag.agora AT TIME ZONE 'America/Sao_Paulo')::date - c_lim.dias::int
),
c_d0 AS (
  SELECT DISTINCT ON (customer_id, campaign_id, metric_date) customer_id, campaign_id, metric_date, metrics
  FROM c_base WHERE collector = 'n8n-google-ads-d0'
  ORDER BY customer_id, campaign_id, metric_date, collected_at DESC
),
c_d1 AS (
  SELECT DISTINCT ON (customer_id, campaign_id, metric_date) customer_id, campaign_id, metric_date, metrics
  FROM c_base
  WHERE collector = 'n8n-google-ads-d1' AND (collected_at AT TIME ZONE 'America/Sao_Paulo')::date > metric_date
  ORDER BY customer_id, campaign_id, metric_date, collected_at DESC
),
c_par AS (
  SELECT coalesce(a.customer_id, b.customer_id) AS customer_id, coalesce(a.campaign_id, b.campaign_id) AS campaign_id,
         coalesce(a.metric_date, b.metric_date) AS metric_date, (a.customer_id IS NOT NULL) AS tem_d0,
         (b.customer_id IS NOT NULL) AS tem_d1,
         CASE WHEN jsonb_typeof(a.metrics -> 'cost_micros') = 'number' THEN (a.metrics ->> 'cost_micros')::numeric END AS custo_d0,
         CASE WHEN jsonb_typeof(b.metrics -> 'cost_micros') = 'number' THEN (b.metrics ->> 'cost_micros')::numeric END AS custo_d1
  FROM c_d0 a
  FULL JOIN c_d1 b ON a.customer_id = b.customer_id AND a.campaign_id IS NOT DISTINCT FROM b.campaign_id
                  AND a.metric_date = b.metric_date
),
c_dif AS (
  SELECT p.*, CASE WHEN p.custo_d0 IS NULL OR p.custo_d1 IS NULL THEN NULL
                   WHEN p.custo_d1 = 0 AND p.custo_d0 = 0 THEN 0
                   WHEN p.custo_d1 = 0 THEN NULL
                   ELSE round(abs(p.custo_d1 - p.custo_d0) / abs(p.custo_d1), 4) END AS diferenca_relativa,
         (p.custo_d1 = 0 AND p.custo_d0 <> 0) AS d1_zero_d0_nao
  FROM c_par p
)
SELECT d.*,
       CASE WHEN NOT d.tem_d1 AND d.metric_date >= (c_ag.agora AT TIME ZONE 'America/Sao_Paulo')::date THEN 'aguardando_d1'
            WHEN NOT d.tem_d1 THEN 'sem_d1'
            WHEN NOT d.tem_d0 THEN 'sem_d0'
            WHEN d.custo_d0 IS NULL OR d.custo_d1 IS NULL THEN 'valor_nulo'
            WHEN NOT d.d1_zero_d0_nao AND d.diferenca_relativa <= l.tol THEN 'ok'
            ELSE 'divergente' END AS estado,
       CASE WHEN NOT d.tem_d1 AND d.metric_date >= (c_ag.agora AT TIME ZONE 'America/Sao_Paulo')::date THEN 'ok'
            WHEN NOT d.tem_d1 OR NOT d.tem_d0 THEN 'info'
            WHEN d.custo_d0 IS NULL OR d.custo_d1 IS NULL THEN 'aviso'
            WHEN d.d1_zero_d0_nao THEN 'alto'
            WHEN d.diferenca_relativa <= l.tol THEN 'ok'
            WHEN d.diferenca_relativa <= l.alto THEN 'aviso'
            ELSE 'alto' END AS severidade
FROM c_dif d CROSS JOIN c_lim l CROSS JOIN c_ag;
-- dq:fim

-- dq:view dq_cobertura_atribuicao_sensor
-- R2: sessões pagas do sensor sem utm_campaign. SÓ agregado diário: nenhum sid/pid sai daqui.
CREATE VIEW dil_qualidade.dq_cobertura_atribuicao_sensor WITH (security_invoker = true) AS
WITH a_ag AS (SELECT dil_qualidade.agora() AS agora),
a_lim AS (SELECT
  (SELECT valor FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'sensor_cobertura_min') AS lo,
  (SELECT valor FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'sensor_cobertura_alto') AS alto,
  (SELECT valor FROM dil_qualidade.dq_parametros_limiares WHERE nome = 'sensor_amostra_min') AS amostra),
a_ev AS (
  SELECT (e.ts AT TIME ZONE 'America/Sao_Paulo')::date AS dia,
         coalesce(e.payload -> 'utm' ->> 'paid', '') IN ('1', 'true') AS paga,
         nullif(btrim(coalesce(e.payload -> 'utm' ->> 'campaign', '')), '') IS NOT NULL AS com_campanha,
         nullif(coalesce(e.payload -> 'utm' ->> 'source', ''), '') IS NOT NULL AS com_source
  FROM public.raw_events e CROSS JOIN a_ag
  WHERE e.event_name = 'volc_sensor_ready'
    AND e.ts > a_ag.agora - interval '14 days' AND e.ts <= a_ag.agora
),
a_dia AS (
  SELECT dia, count(*) AS sessoes_total, count(*) FILTER (WHERE paga) AS sessoes_pagas,
         count(*) FILTER (WHERE paga AND com_campanha) AS pagas_com_campanha,
         count(*) FILTER (WHERE paga AND com_source) AS pagas_com_source
  FROM a_ev GROUP BY dia
)
SELECT d.dia, d.sessoes_total, d.sessoes_pagas, d.pagas_com_campanha, d.pagas_com_source,
       CASE WHEN d.sessoes_pagas > 0 THEN round(d.pagas_com_campanha::numeric / d.sessoes_pagas, 4) END AS cobertura,
       CASE WHEN d.sessoes_pagas = 0 THEN 'sem_base'
            WHEN d.sessoes_pagas < l.amostra THEN 'amostra_insuficiente'
            WHEN round(d.pagas_com_campanha::numeric / d.sessoes_pagas, 4) < l.lo THEN 'cobertura_baixa'
            ELSE 'ok' END AS estado,
       CASE WHEN d.sessoes_pagas = 0 THEN 'ok'
            WHEN d.sessoes_pagas < l.amostra THEN 'info'
            WHEN round(d.pagas_com_campanha::numeric / d.sessoes_pagas, 4) < l.alto THEN 'alto'
            WHEN round(d.pagas_com_campanha::numeric / d.sessoes_pagas, 4) < l.lo THEN 'aviso'
            ELSE 'ok' END AS severidade
FROM a_dia d CROSS JOIN a_lim l;
-- dq:fim

-- dq:view dq_esquema_joinads
-- Mais de um schema_fingerprint (gatilho joinads_hash_raw_batch) por endpoint × versão do coletor,
-- em lotes HTTP 2xx com linhas = campo novo/sumido SEM troca de versão.
CREATE VIEW dil_qualidade.dq_esquema_joinads WITH (security_invoker = true) AS
WITH e_ag AS (SELECT dil_qualidade.agora() AS agora)
SELECT b.endpoint, r.collector, r.collector_version, count(DISTINCT b.schema_fingerprint) AS n_fingerprints,
       count(*) AS n_lotes, min(b.collected_at) AS primeira_coleta, max(b.collected_at) AS ultima_coleta,
       CASE WHEN count(DISTINCT b.schema_fingerprint) > 1 THEN 'deriva_sem_troca_de_versao' ELSE 'estavel' END AS classe,
       CASE WHEN count(DISTINCT b.schema_fingerprint) > 1 THEN 'aviso' ELSE 'ok' END AS severidade
FROM public.joinads_raw_batch b
JOIN public.joinads_collection_run r ON r.run_key = b.run_key
CROSS JOIN e_ag
WHERE b.http_status BETWEEN 200 AND 299 AND b.row_count > 0
  AND b.collected_at > e_ag.agora - interval '14 days' AND b.collected_at <= e_ag.agora
GROUP BY b.endpoint, r.collector, r.collector_version;
-- dq:fim

-- dq:view dq_substituicao_fonte
-- A fonte devolveu outra coisa que não a pedida.
CREATE VIEW dil_qualidade.dq_substituicao_fonte WITH (security_invoker = true) AS
SELECT 'joinads'::text AS fonte, 'custom_key_substituida'::text AS regra, r.run_key AS chave,
       count(*) AS n, jsonb_agg(DISTINCT w ->> 'received') AS evidencia, 'alto'::text AS severidade
FROM public.joinads_collection_run r
CROSS JOIN LATERAL jsonb_array_elements(
  CASE WHEN jsonb_typeof(r.receipt -> 'warnings') = 'array' THEN r.receipt -> 'warnings' ELSE '[]'::jsonb END) w
WHERE w ->> 'code' = 'custom_key_substituted'
GROUP BY r.run_key
UNION ALL
SELECT 'google_ads', 'campanha_mudou_de_conta', o.campaign_id, count(DISTINCT o.customer_id),
       jsonb_agg(DISTINCT o.customer_id), 'alto'
FROM public.google_ads_observation o
WHERE o.campaign_id IS NOT NULL
GROUP BY o.campaign_id HAVING count(DISTINCT o.customer_id) > 1
UNION ALL
SELECT 'google_ads', 'moeda_trocada', o.customer_id, count(DISTINCT o.currency_code),
       jsonb_agg(DISTINCT o.currency_code), 'alto'
FROM public.google_ads_observation o
WHERE o.currency_code IS NOT NULL
GROUP BY o.customer_id HAVING count(DISTINCT o.currency_code) > 1
UNION ALL
SELECT 'joinads', 'moeda_trocada', coalesce(o.domain, ''), count(DISTINCT o.currency_code),
       jsonb_agg(DISTINCT o.currency_code), 'alto'
FROM public.joinads_observation o
GROUP BY coalesce(o.domain, '') HAVING count(DISTINCT o.currency_code) > 1;
-- dq:fim

-- ---------------------------------------------------------------------------
-- Grants: só leitura para service_role; nada para PUBLIC/anon/authenticated
-- (o Supabase dá ALL por default ACL a anon/authenticated em objeto novo — revogado aqui).
-- ---------------------------------------------------------------------------
REVOKE ALL ON ALL TABLES IN SCHEMA dil_qualidade FROM PUBLIC;
REVOKE ALL ON FUNCTION dil_qualidade.agora() FROM PUBLIC;
DO $$
DECLARE papel text;
BEGIN
  FOREACH papel IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = papel) THEN
      EXECUTE format('REVOKE ALL ON SCHEMA dil_qualidade FROM %I', papel);
      EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA dil_qualidade FROM %I', papel);
      EXECUTE format('REVOKE ALL ON FUNCTION dil_qualidade.agora() FROM %I', papel);
    END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'service_role') THEN
    GRANT USAGE ON SCHEMA dil_qualidade TO service_role;
    GRANT SELECT ON ALL TABLES IN SCHEMA dil_qualidade TO service_role;
    GRANT EXECUTE ON FUNCTION dil_qualidade.agora() TO service_role;
  END IF;
END $$;

COMMIT;
