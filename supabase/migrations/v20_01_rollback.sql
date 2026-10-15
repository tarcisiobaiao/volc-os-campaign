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
  -- objetos de outro schema que dependam do ledger também barram o DROP (o
  -- CASCADE os levaria junto). Só dependências normais/automáticas: a TOAST da
  -- tabela (pg_toast, interna) é do próprio ledger. O schema de regra (view),
  -- constraint (FK) e gatilho é o da relação que os carrega.
  SELECT count(*) INTO n
    FROM pg_depend d
   WHERE d.deptype IN ('n','a')
     AND ((d.refclassid = 'pg_class'::regclass
           AND d.refobjid IN (SELECT oid FROM pg_class WHERE relnamespace = 'volc_ops'::regnamespace))
       OR (d.refclassid = 'pg_proc'::regclass
           AND d.refobjid IN (SELECT oid FROM pg_proc WHERE pronamespace = 'volc_ops'::regnamespace)))
     AND CASE d.classid
           WHEN 'pg_class'::regclass      THEN (SELECT relnamespace FROM pg_class WHERE oid = d.objid)
           WHEN 'pg_rewrite'::regclass    THEN (SELECT c.relnamespace FROM pg_rewrite r JOIN pg_class c ON c.oid = r.ev_class WHERE r.oid = d.objid)
           WHEN 'pg_constraint'::regclass THEN (SELECT connamespace FROM pg_constraint WHERE oid = d.objid)
           WHEN 'pg_trigger'::regclass    THEN (SELECT c.relnamespace FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid WHERE t.oid = d.objid)
           WHEN 'pg_proc'::regclass       THEN (SELECT pronamespace FROM pg_proc WHERE oid = d.objid)
           WHEN 'pg_type'::regclass       THEN (SELECT typnamespace FROM pg_type WHERE oid = d.objid)
           WHEN 'pg_attrdef'::regclass    THEN (SELECT c.relnamespace FROM pg_attrdef a JOIN pg_class c ON c.oid = a.adrelid WHERE a.oid = d.objid)
           WHEN 'pg_policy'::regclass     THEN (SELECT c.relnamespace FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid WHERE p.oid = d.objid)
         END IS DISTINCT FROM 'volc_ops'::regnamespace;
  IF n > 0 THEN
    RAISE EXCEPTION 'v20_01_rollback: % objeto(s) fora de volc_ops dependem do ledger — recusado', n
      USING ERRCODE = 'P0001';
  END IF;
  DROP SCHEMA volc_ops CASCADE;
END $$;

COMMIT;
