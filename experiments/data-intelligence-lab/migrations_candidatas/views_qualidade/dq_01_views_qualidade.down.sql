-- Rollback de dq_01_views_qualidade.sql (thread G). Só remove views/função criadas por ela;
-- não toca nas tabelas-base. O schema só cai se ficar vazio (dq_02 pode ainda estar aplicada).
BEGIN;

DROP VIEW IF EXISTS dil_qualidade.dq_substituicao_fonte;
DROP VIEW IF EXISTS dil_qualidade.dq_esquema_joinads;
DROP VIEW IF EXISTS dil_qualidade.dq_cobertura_atribuicao_sensor;
DROP VIEW IF EXISTS dil_qualidade.dq_reconciliacao_custo_d0_d1;
DROP VIEW IF EXISTS dil_qualidade.dq_reconciliacao_joinads;
DROP VIEW IF EXISTS dil_qualidade.dq_zero_sintetizado;
DROP VIEW IF EXISTS dil_qualidade.dq_duplicacao;
DROP VIEW IF EXISTS dil_qualidade.dq_falha_silenciosa;
DROP VIEW IF EXISTS dil_qualidade.dq_runs_orfaos;
DROP VIEW IF EXISTS dil_qualidade.dq_completude_hora;
DROP VIEW IF EXISTS dil_qualidade.dq_freshness;
DROP VIEW IF EXISTS dil_qualidade.dq_slots;
DROP VIEW IF EXISTS dil_qualidade.dq_runs;
DROP VIEW IF EXISTS dil_qualidade.dq_parametros_limiares;
DROP VIEW IF EXISTS dil_qualidade.dq_parametros_sla;

DO $$
BEGIN
  IF to_regnamespace('dil_qualidade') IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_class WHERE relnamespace = 'dil_qualidade'::regnamespace) THEN
    DROP FUNCTION IF EXISTS dil_qualidade.agora();
    DROP SCHEMA dil_qualidade;
  END IF;
END $$;

COMMIT;
