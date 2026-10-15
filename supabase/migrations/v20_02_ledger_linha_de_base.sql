-- =============================================================================
-- v20_02_ledger_linha_de_base.sql — CANDIDATA, NÃO APLICADA
--
-- Backfill do ledger (v20_01): registra o estado ATUAL do banco como linha de
-- base, sem reaplicar nada. Não executa DDL fora de volc_ops e não toca dado de
-- negócio: só insere duas linhas no log.
--
--   1. linha_de_base_producao_20261015 — "tudo que existe em public + app_auth
--      no fingerprint 695e913a4373efd1c2265cdd5ac87251 é o ponto de partida".
--      Medido em produção em 15/10/2026 ~10:55Z, sessão read-only
--      (handoffs/freedom-lab-20261015/fingerprint-prod.out,
--       sha256 fbd623d78b4d21267251599fa8d80855c33dd80cc0e176b29c69d6212b77d170;
--       B-banco.md §0). 236 relações, 235 funções, 120 gatilhos, 29 policies.
--   2. v20_01_ledger_migrations — o próprio ledger, que não pôde se registrar
--      porque não existia antes de existir.
--
-- ÂNCORA: a migration mede volc_ops.fingerprint_schema() AGORA e recusa se o
-- _TOTAL não for 695e913a…. Se qualquer DDL em public/app_auth acontecer entre a
-- medição e a aplicação (inclusive v18_01, v19_*), esta migration falha fechada
-- e a linha de base precisa ser remedida — nunca "registrada mesmo assim".
--
-- Deliberadamente NÃO registra as migrations que o README diz aplicadas, uma a
-- uma: o README é declaração humana sem verificação (ex.: v12_04 aparece com
-- dois sha256 diferentes, l.36 e l.1250). A linha de base cobre todas pelo
-- fingerprint; o que vier depois entra pelo protocolo, com hash.
--
-- O aprovador entra pelo protocolo (scripts/migracao-protocolo.sh), que faz
--   set_config('volc_ops.aprovador', <nome>, true)
-- na mesma transação. Rodada fora do protocolo, sem aprovador, ela recusa.
--
-- Rollback: v20_02_rollback.sql.
-- =============================================================================
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $$
DECLARE
  esperado   constant text := '695e913a4373efd1c2265cdd5ac87251';
  medido     text;
  aprovador  text := nullif(btrim(current_setting('volc_ops.aprovador', true)), '');
  aprov_em   date := nullif(current_setting('volc_ops.aprovado_em', true), '')::date;
BEGIN
  IF to_regclass('volc_ops.migracao_evento') IS NULL THEN
    RAISE EXCEPTION 'v20_02: ledger ausente — aplique v20_01 antes' USING ERRCODE = 'P0001';
  END IF;
  IF aprovador IS NULL THEN
    RAISE EXCEPTION 'v20_02: sem aprovador (volc_ops.aprovador) — aplique pelo protocolo'
      USING ERRCODE = 'P0001';
  END IF;

  SELECT f.md5 INTO medido FROM volc_ops.fingerprint_schema() f WHERE f.categoria = '_TOTAL';
  IF medido IS DISTINCT FROM esperado THEN
    RAISE EXCEPTION 'v20_02: fingerprint de public+app_auth é %, a linha de base aprovada é % — o schema mudou desde a medição; remeça antes de registrar',
      medido, esperado USING ERRCODE = 'P0001';
  END IF;

  INSERT INTO volc_ops.migracao_evento
    (versao, operacao, arquivo, sha256, aprovador, aprovado_em, fingerprint, evidencia)
  VALUES
    ('linha_de_base_producao_20261015', 'linha_de_base',
     'tools/freedom-lab/db/fingerprint_schema.sql',
     '0f6c05509466e9bc92474465d4427cf5fe426a477d15fc50a31871317e30d2c7',
     aprovador, aprov_em, medido,
     'fingerprint-prod.out sha256 fbd623d78b4d21267251599fa8d80855c33dd80cc0e176b29c69d6212b77d170 (handoffs/freedom-lab-20261015, B-banco.md §0); estado anterior aplicado à mão, registro histórico em supabase/migrations/README.md');

  INSERT INTO volc_ops.migracao_evento
    (versao, operacao, arquivo, sha256, rollback_arquivo, rollback_sha256,
     aprovador, aprovado_em, fingerprint, evidencia)
  VALUES
    ('v20_01_ledger_migrations', 'aplicar',
     'supabase/migrations/v20_01_ledger_migrations.sql',
     '5727f27d5941b06d671a7d1946a9107eae43363fdc486799cd66fe52767df0c8',
     'supabase/migrations/v20_01_rollback.sql',
     '3146e96ec8643ee0de1775a83a961274c49af74dffb38a5e3aa8b1f02da28a4b',
     aprovador, aprov_em, medido,
     'registrada retroativamente pela v20_02 (o ledger não existia antes de si mesmo)');
END $$;

COMMIT;
