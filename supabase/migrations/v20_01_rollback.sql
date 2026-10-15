-- =============================================================================
-- v20_01_rollback.sql — desfaz v20_01_ledger_migrations.sql
--
-- Recusa se o ledger registrar qualquer evento além da linha de base da v20_02
-- (o bootstrap do próprio ledger). Apagar um ledger que já registrou migrations
-- de verdade apagaria a única prova de quem aplicou o quê: reverta-as antes, ou
-- não reverta o ledger. Idempotente: sem volc_ops, não faz nada.
-- =============================================================================
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $$
DECLARE n int;
BEGIN
  IF to_regnamespace('volc_ops') IS NULL THEN
    RAISE NOTICE 'v20_01_rollback: volc_ops ausente — nada a fazer';
    RETURN;
  END IF;
  SELECT count(*) INTO n FROM volc_ops.migracao_evento
   WHERE versao NOT IN ('v20_02_ledger_linha_de_base', 'linha_de_base_producao_20261015',
                        'v20_01_ledger_migrations');
  IF n > 0 THEN
    RAISE EXCEPTION 'v20_01_rollback: o ledger registra % evento(s) de outras migrations — recusado', n
      USING ERRCODE = 'P0001';
  END IF;
  -- objetos de outro schema que dependam do ledger também barram o DROP
  SELECT count(*) INTO n FROM pg_depend d
    JOIN pg_class c ON c.oid = d.objid
   WHERE d.refobjid IN (SELECT oid FROM pg_class WHERE relnamespace = 'volc_ops'::regnamespace)
     AND c.relnamespace <> 'volc_ops'::regnamespace;
  IF n > 0 THEN
    RAISE EXCEPTION 'v20_01_rollback: % objeto(s) fora de volc_ops dependem do ledger — recusado', n
      USING ERRCODE = 'P0001';
  END IF;
  DROP SCHEMA volc_ops CASCADE;
END $$;

COMMIT;
