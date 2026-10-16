-- =============================================================================
-- dq_02 — Views candidatas de qualidade sobre o schema genérico dil_obs (thread G)
-- DEPENDE DE: migrations_candidatas/dil_obs_0001_schema_observacao.sql (thread A).
-- MIGRATION CANDIDATA. NÃO APLICADA EM NENHUM BANCO OPERACIONAL. Testada só em PG 16 descartável.
-- Rollback: dq_02_views_dil_obs.down.sql. Independente de dq_01 (pode ser aplicada sem v21/JoinAds).
-- Insumos sugeridos por A: status/motivo, dead_letter, run_coleta, ingested_at − available_at.
-- Leitura: papel dil_obs_leitor (o mesmo que já lê dil_obs). security_invoker em todas.
-- =============================================================================

BEGIN;

DO $$
BEGIN
  IF to_regclass('dil_obs.observacao') IS NULL OR to_regclass('dil_obs.run_coleta') IS NULL
     OR to_regclass('dil_obs.dead_letter') IS NULL OR to_regclass('dil_obs.lote') IS NULL
     OR to_regprocedure('dil_obs.observacao_as_of(timestamptz)') IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = '42P01', MESSAGE = 'dq_02: schema dil_obs (dil_obs_0001) é pré-requisito';
  END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS dil_qualidade;
REVOKE ALL ON SCHEMA dil_qualidade FROM PUBLIC;

CREATE OR REPLACE FUNCTION dil_qualidade.agora() RETURNS timestamptz
LANGUAGE sql STABLE
SET search_path = pg_catalog
AS $$
  SELECT coalesce(nullif(current_setting('dil_qualidade.agora', true), '')::timestamptz, now())
$$;

-- dq:view dq_obs_latencia_ingestao
-- available_at -> ingested_at (e observed_at -> available_at) por fonte × coletor, janela de 14 dias.
CREATE VIEW dil_qualidade.dq_obs_latencia_ingestao WITH (security_invoker = true) AS
WITH l_ag AS (SELECT dil_qualidade.agora() AS agora)
SELECT o.fonte, o.coletor_nome, count(*) AS n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM o.ingested_at - o.available_at)) AS p50_s,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM o.ingested_at - o.available_at)) AS p95_s,
       max(extract(epoch FROM o.ingested_at - o.available_at)) AS max_s,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM o.available_at - o.observed_at))
         AS p95_publicacao_s,
       CASE WHEN percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM o.ingested_at - o.available_at)) > 3600
            THEN 'aviso' ELSE 'ok' END AS severidade
FROM dil_obs.observacao o CROSS JOIN l_ag
WHERE o.ingested_at > l_ag.agora - interval '14 days' AND o.ingested_at <= l_ag.agora
GROUP BY o.fonte, o.coletor_nome;
-- dq:fim

-- dq:view dq_obs_dead_letter
-- Por run finalizado (R2-G6): conta os dead letters REGISTRADOS na tabela, não só o contador do fechamento.
-- Run com dead letters e n_lidas = 0 (taxa indefinida) é alto — NULL não é ok; dead letter registrado depois
-- do fechamento (registrados > n_dead_letter) também é alto.
CREATE VIEW dil_qualidade.dq_obs_dead_letter WITH (security_invoker = true) AS
WITH dl_ag AS (SELECT dil_qualidade.agora() AS agora),
dl_mot AS (
  SELECT run_id, sum(n)::bigint AS n, jsonb_object_agg(motivo, n) AS motivos
  FROM (SELECT run_id, motivo, count(*) AS n FROM dil_obs.dead_letter GROUP BY 1, 2) z GROUP BY run_id
),
dl_run AS (
  SELECT r.run_id, r.fonte, r.coletor_nome, r.status, r.iniciado_em, r.n_lidas, r.n_dead_letter,
         coalesce(m.n, 0) AS dead_letter_registrados, coalesce(m.motivos, '{}'::jsonb) AS motivos,
         GREATEST(coalesce(r.n_dead_letter, 0), coalesce(m.n, 0)) AS dl
  FROM dil_obs.run_coleta r
  CROSS JOIN dl_ag
  LEFT JOIN dl_mot m ON m.run_id = r.run_id
  WHERE r.status <> 'running' AND r.iniciado_em > dl_ag.agora - interval '14 days' AND r.iniciado_em <= dl_ag.agora
),
dl_cls AS (
  SELECT d.*,
         CASE WHEN d.n_lidas > 0 THEN round(d.dl::numeric / d.n_lidas, 4) END AS taxa,
         CASE WHEN d.dead_letter_registrados > coalesce(d.n_dead_letter, 0) THEN 'dead_letter_apos_fechamento'
              WHEN d.dl > 0 AND coalesce(d.n_lidas, 0) = 0 THEN 'so_dead_letter'
              WHEN d.n_lidas > 0 AND d.dl::numeric / d.n_lidas > 0.05 THEN 'taxa_alta'
              ELSE 'ok' END AS classe
  FROM dl_run d
)
SELECT c.run_id, c.fonte, c.coletor_nome, c.status, c.iniciado_em, c.n_lidas, c.n_dead_letter,
       c.dead_letter_registrados, c.taxa, c.motivos, c.classe,
       CASE WHEN c.classe = 'ok' THEN 'ok' ELSE 'alto' END AS severidade
FROM dl_cls c;
-- dq:fim

-- dq:view dq_obs_status
-- Distribuição do estado VIGENTE (R2-G7): dil_obs.observacao_as_of(agora) — uma linha por fato, a versão
-- conhecida em `agora`; versões superadas (ex.: partial seguido do fechamento) não contam.
CREATE VIEW dil_qualidade.dq_obs_status WITH (security_invoker = true) AS
WITH st_ag AS (SELECT dil_qualidade.agora() AS agora)
SELECT o.fonte, o.metrica, (o.janela_inicio AT TIME ZONE o.timezone)::date AS dia_local, o.status,
       coalesce(o.motivo, '') AS motivo, count(*) AS n,
       CASE WHEN o.status IN ('invalid') THEN 'alto'
            WHEN o.status IN ('unavailable', 'missing', 'late') THEN 'aviso'
            WHEN o.status = 'partial' THEN 'info' ELSE 'ok' END AS severidade
FROM st_ag CROSS JOIN LATERAL dil_obs.observacao_as_of(st_ag.agora) o
WHERE o.janela_inicio > st_ag.agora - interval '14 days'
GROUP BY 1, 2, 3, 4, 5;
-- dq:fim

-- dq:view dq_obs_runs_orfaos
CREATE VIEW dil_qualidade.dq_obs_runs_orfaos WITH (security_invoker = true) AS
WITH ro_ag AS (SELECT dil_qualidade.agora() AS agora)
SELECT r.run_id, r.fonte, r.coletor_nome, r.iniciado_em,
       (SELECT max(l.registrado_em) FROM dil_obs.lote l WHERE l.run_id = r.run_id) AS ultimo_sinal,
       ro_ag.agora - r.iniciado_em AS idade, 'alto'::text AS severidade
FROM dil_obs.run_coleta r CROSS JOIN ro_ag
WHERE r.status = 'running' AND r.iniciado_em <= ro_ag.agora AND r.iniciado_em < ro_ag.agora - interval '30 minutes'
  AND coalesce((SELECT max(l.registrado_em) FROM dil_obs.lote l WHERE l.run_id = r.run_id), r.iniciado_em)
      < ro_ag.agora - interval '30 minutes';
-- dq:fim

REVOKE ALL ON dil_qualidade.dq_obs_latencia_ingestao, dil_qualidade.dq_obs_dead_letter,
              dil_qualidade.dq_obs_status, dil_qualidade.dq_obs_runs_orfaos FROM PUBLIC;
REVOKE ALL ON FUNCTION dil_qualidade.agora() FROM PUBLIC;
DO $$
DECLARE papel text;
BEGIN
  FOREACH papel IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = papel) THEN
      EXECUTE format('REVOKE ALL ON SCHEMA dil_qualidade FROM %I', papel);
      EXECUTE format('REVOKE ALL ON dil_qualidade.dq_obs_latencia_ingestao, dil_qualidade.dq_obs_dead_letter, '
                     'dil_qualidade.dq_obs_status, dil_qualidade.dq_obs_runs_orfaos FROM %I', papel);
      EXECUTE format('REVOKE ALL ON FUNCTION dil_qualidade.agora() FROM %I', papel);
    END IF;
  END LOOP;
END $$;
GRANT USAGE ON SCHEMA dil_qualidade TO dil_obs_leitor;
GRANT EXECUTE ON FUNCTION dil_qualidade.agora() TO dil_obs_leitor;
GRANT SELECT ON dil_qualidade.dq_obs_latencia_ingestao, dil_qualidade.dq_obs_dead_letter,
                dil_qualidade.dq_obs_status, dil_qualidade.dq_obs_runs_orfaos TO dil_obs_leitor;

COMMIT;
