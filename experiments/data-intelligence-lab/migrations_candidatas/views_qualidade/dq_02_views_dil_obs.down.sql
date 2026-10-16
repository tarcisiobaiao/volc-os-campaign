-- Rollback de dq_02_views_dil_obs.sql (thread G). Não toca em dil_obs.
BEGIN;

DROP VIEW IF EXISTS dil_qualidade.dq_obs_runs_orfaos;
DROP VIEW IF EXISTS dil_qualidade.dq_obs_status;
DROP VIEW IF EXISTS dil_qualidade.dq_obs_dead_letter;
DROP VIEW IF EXISTS dil_qualidade.dq_obs_latencia_ingestao;

DO $$
BEGIN
  IF to_regnamespace('dil_qualidade') IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'dil_obs_leitor') THEN
      REVOKE ALL ON SCHEMA dil_qualidade FROM dil_obs_leitor;
      IF to_regprocedure('dil_qualidade.agora()') IS NOT NULL THEN
        REVOKE ALL ON FUNCTION dil_qualidade.agora() FROM dil_obs_leitor;
      END IF;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class WHERE relnamespace = 'dil_qualidade'::regnamespace) THEN
      DROP FUNCTION IF EXISTS dil_qualidade.agora();
      DROP SCHEMA dil_qualidade;
    END IF;
  END IF;
END $$;

COMMIT;
