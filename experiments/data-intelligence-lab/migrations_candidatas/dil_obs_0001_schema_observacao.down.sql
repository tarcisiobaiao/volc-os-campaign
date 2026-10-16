-- =============================================================================
-- dil_obs_0001 — ROLLBACK de dil_obs_0001_schema_observacao.sql
-- MIGRATION CANDIDATA. NÃO APLICADA EM NENHUM BANCO OPERACIONAL.
-- ⚠️ DESTRÓI o histórico append-only inteiro (DROP não dispara os triggers de append-only).
--    Num banco com dado real, exportar dil_obs.* antes. Idempotente: rodar duas vezes não falha.
-- Papéis: removidos só se não restar dependência em OUTRO banco do cluster; senão ficam (NOTICE).
-- =============================================================================

BEGIN;

DROP SCHEMA IF EXISTS dil_obs CASCADE;

DO $$
DECLARE r text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'dil_obs_dono') THEN
    -- remove default ACL e o que sobrar do dono NESTE banco (o papel é dedicado a este schema)
    EXECUTE 'DROP OWNED BY dil_obs_dono';
  END IF;
  FOREACH r IN ARRAY ARRAY['dil_obs_escritor', 'dil_obs_leitor', 'dil_obs_dono'] LOOP
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = r) THEN
      BEGIN
        EXECUTE format('DROP ROLE %I', r);
      EXCEPTION WHEN dependent_objects_still_exist THEN
        RAISE NOTICE 'papel % mantido: ainda há dependências em outro banco do cluster', r;
      END;
    END IF;
  END LOOP;
END $$;

COMMIT;
