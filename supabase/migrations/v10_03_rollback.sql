-- =============================================================================
-- v10_03_rollback — desfaz a v10_03 e SO a v10_03
-- =============================================================================
--
-- A v10_01 continua de pe depois deste arquivo: nenhuma funcao dela foi
-- substituida (foi essa a razao de a v10_03 usar gatilhos NOVOS em vez de
-- `CREATE OR REPLACE` sobre os antigos — um rollback que precisa redigitar o
-- corpo de uma regra apaga tanto quanto a migration que ele desfaz).
--
-- ⚠️ O que este rollback CUSTA, dito antes de ser rodado: as colunas de
-- aprovacao saem junto. Se ja houver item aprovado, a memoria de QUEM autorizou
-- o que se perde. Faca a leitura abaixo antes:
--
--   SELECT item_id, idempotency_key, aprovado_por, aprovado_em, aprovacao_impressao
--     FROM public.trafego_lote_item WHERE aprovado_em IS NOT NULL;
--
-- Rodar este arquivo tambem reabre o defeito que a v10_03 fecha: dois recibos
-- em voo para o mesmo item voltam a ser aceitos.
-- =============================================================================

BEGIN;

DO $guarda$
BEGIN
  IF to_regclass('public.trafego_lote_item') IS NULL THEN
    RAISE EXCEPTION
      'v10_03_rollback abortado: trafego_lote_item nao existe. A v10_01 ja foi revertida e nao ha o que desfazer aqui.';
  END IF;
END
$guarda$;

DROP TRIGGER IF EXISTS trafego_recibo_um_voo_por_item   ON public.trafego_recibo;
DROP TRIGGER IF EXISTS trafego_item_aprovacao_vinculada ON public.trafego_lote_item;

DROP FUNCTION IF EXISTS public.trafego_recibo_um_voo_por_item();
DROP FUNCTION IF EXISTS public.trafego_item_aprovacao_vinculada();

DROP FUNCTION IF EXISTS public.trafego_ledger_abrir_lancamento(
  text,text,text,text,text,text,jsonb,text,text,text,text,text,jsonb,text,bigint,text,jsonb,integer,text,uuid,jsonb);
DROP FUNCTION IF EXISTS public.trafego_ledger_despachar(text,text,text,text,text,text,text,text,text,text);
DROP FUNCTION IF EXISTS public.trafego_ledger_fechar(uuid,text,text,text,text,text,text,jsonb,integer,text);
DROP FUNCTION IF EXISTS public.trafego_ledger_reconciliar(uuid,text,boolean,text,text,text,text,integer,text,text,jsonb);

ALTER TABLE public.trafego_lote_item
  DROP CONSTRAINT IF EXISTS trafego_item_aprovacao_vinculada_ao_plano,
  DROP CONSTRAINT IF EXISTS trafego_item_aprovacao_indivisivel,
  DROP CONSTRAINT IF EXISTS trafego_item_aprovacao_impressao_sha256,
  DROP CONSTRAINT IF EXISTS trafego_item_plano_impressao_sha256;

ALTER TABLE public.trafego_lote_item
  DROP COLUMN IF EXISTS aprovacao_impressao,
  DROP COLUMN IF EXISTS aprovado_em,
  DROP COLUMN IF EXISTS aprovado_por_sub,
  DROP COLUMN IF EXISTS aprovado_por,
  DROP COLUMN IF EXISTS plano_impressao;

DO $verifica$
DECLARE
  sobrou text;
BEGIN
  SELECT string_agg(p, ', ' ORDER BY p) INTO sobrou
    FROM unnest(ARRAY[
      'trafego_ledger_abrir_lancamento', 'trafego_ledger_despachar',
      'trafego_ledger_fechar', 'trafego_ledger_reconciliar',
      'trafego_recibo_um_voo_por_item', 'trafego_item_aprovacao_vinculada'
    ]) AS p
   WHERE EXISTS (SELECT 1 FROM pg_proc pr JOIN pg_namespace n ON n.oid = pr.pronamespace
                  WHERE n.nspname = 'public' AND pr.proname = p);
  IF sobrou IS NOT NULL THEN
    RAISE EXCEPTION 'v10_03_rollback: sobrou funcao: %', sobrou;
  END IF;

  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = 'trafego_lote_item'
                AND column_name IN ('plano_impressao','aprovado_por','aprovado_por_sub',
                                    'aprovado_em','aprovacao_impressao')) THEN
    RAISE EXCEPTION 'v10_03_rollback: sobrou coluna de aprovacao em trafego_lote_item';
  END IF;

  -- A v10_01 tem de continuar inteira.
  IF to_regclass('public.trafego_recibo') IS NULL
     OR NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trafego_item_estado_valido') THEN
    RAISE EXCEPTION
      'v10_03_rollback: a v10_01 foi danificada. Este rollback so pode derrubar o que a v10_03 criou.';
  END IF;

  RAISE NOTICE 'v10_03_rollback: verificacao interna passou';
END
$verifica$;

COMMIT;
