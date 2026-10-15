-- =============================================================================
-- v20_02_rollback.sql — desfaz v20_02_ledger_linha_de_base.sql
--
-- Remove as duas linhas que a v20_02 inseriu. O log é append-only por gatilho;
-- só o dono da tabela pode suspender a guarda, e só dentro desta transação.
-- Recusa se o ledger já registrar outras migrations: a linha de base é a âncora
-- delas. Idempotente.
-- =============================================================================
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $$
DECLARE n int;
BEGIN
  IF to_regclass('volc_ops.migracao_evento') IS NULL THEN
    RAISE NOTICE 'v20_02_rollback: ledger ausente — nada a fazer';
    RETURN;
  END IF;
  SELECT count(*) INTO n FROM volc_ops.migracao_evento
   WHERE versao NOT IN ('v20_02_ledger_linha_de_base', 'linha_de_base_producao_20261015',
                        'v20_01_ledger_migrations');
  IF n > 0 THEN
    RAISE EXCEPTION 'v20_02_rollback: % evento(s) de outras migrations dependem da linha de base — recusado', n
      USING ERRCODE = 'P0001';
  END IF;
  ALTER TABLE volc_ops.migracao_evento DISABLE TRIGGER migracao_evento_guarda;
  DELETE FROM volc_ops.migracao_evento
   WHERE versao IN ('linha_de_base_producao_20261015', 'v20_01_ledger_migrations');
  ALTER TABLE volc_ops.migracao_evento ENABLE TRIGGER migracao_evento_guarda;
END $$;

COMMIT;
