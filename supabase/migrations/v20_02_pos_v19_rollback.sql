-- =============================================================================
-- v20_02_pos_v19_rollback.sql — desfaz v20_02_ledger_linha_de_base_pos_v19.sql
-- (a v20_02 gerada do recibo do passo 1 do W4 por scripts/ledger_recibo_incidente.py)
--
-- Remove, em ordem inversa de inserção, só o que aquela migration inseriu: a linha
-- de base pré-v19, os 5 eventos "aplicar" do backfill da v19 e o registro
-- retroativo da v20_01. NÃO desfaz a v19 no banco: só o registro dela no ledger.
--
-- Recusa (P0001, nada removido) se:
--   · existir evento de qualquer outra versão (alguém já se ancorou nesta base);
--   · alguma versão do conjunto tiver mais de um evento (ex.: v8_06 importada,
--     reverter importado): houve história depois do backfill;
--   · o conjunto não estiver completo (rollback de outra coisa, ou já rodado).
-- O log é append-only por gatilho; só o dono da tabela suspende a guarda, e só
-- dentro desta transação. O protocolo registra o "reverter" desta versão.
-- =============================================================================
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $$
DECLARE
  conjunto constant text[] := ARRAY[
    'linha_de_base_producao_20261015',
    'v19_00_users_gatilho_papel_real', 'v8_03_users_rls_policies', 'v19_01_anon_fecha_public',
    'v8_05_users_safe_view', 'v19_02_default_acl_public_sem_anon',
    'v20_01_ledger_migrations'];
  propria  constant text := 'v20_02_ledger_linha_de_base_pos_v19';
  n int;
  r record;
BEGIN
  IF to_regclass('volc_ops.migracao_evento') IS NULL THEN
    RAISE EXCEPTION 'v20_02_pos_v19_rollback: ledger ausente' USING ERRCODE = 'P0001';
  END IF;

  SELECT count(*) INTO n FROM volc_ops.migracao_evento
   WHERE versao <> ALL (conjunto) AND versao <> propria;
  IF n > 0 THEN
    RAISE EXCEPTION 'v20_02_pos_v19_rollback: % evento(s) de outras versões dependem da linha de base — recusado', n
      USING ERRCODE = 'P0001';
  END IF;

  SELECT count(*) INTO n FROM (
    SELECT versao FROM volc_ops.migracao_evento WHERE versao = ANY (conjunto)
     GROUP BY versao HAVING count(*) > 1) x;
  IF n > 0 THEN
    RAISE EXCEPTION 'v20_02_pos_v19_rollback: % versão(ões) do backfill têm eventos posteriores — recusado', n
      USING ERRCODE = 'P0001';
  END IF;

  SELECT count(*) INTO n FROM volc_ops.migracao_evento
   WHERE versao = ANY (conjunto)
     AND operacao = CASE WHEN versao = 'linha_de_base_producao_20261015' THEN 'linha_de_base' ELSE 'aplicar' END;
  IF n <> array_length(conjunto, 1) THEN
    RAISE EXCEPTION 'v20_02_pos_v19_rollback: backfill incompleto (% de % eventos) — nada a desfazer ou ledger inesperado',
      n, array_length(conjunto, 1) USING ERRCODE = 'P0001';
  END IF;

  ALTER TABLE volc_ops.migracao_evento DISABLE TRIGGER migracao_evento_guarda;
  FOR r IN SELECT id, versao FROM volc_ops.migracao_evento WHERE versao = ANY (conjunto) ORDER BY id DESC LOOP
    DELETE FROM volc_ops.migracao_evento WHERE id = r.id;
    RAISE NOTICE 'v20_02_pos_v19_rollback: removido evento % (%)', r.id, r.versao;
  END LOOP;
  ALTER TABLE volc_ops.migracao_evento ENABLE TRIGGER migracao_evento_guarda;
END $$;

COMMIT;
