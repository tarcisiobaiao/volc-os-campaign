-- v23_01 rollback — devolve o schema de antes da v23_01 (W12)
--
-- RECUSA, sem apagar nada, quando já existe dado de negócio que só a v23_01
-- guarda: versões de receita além da carga inicial, ou cotação coletada.
-- Exporte antes (receita_observacao e exchange_rate_history WHERE as_of IS
-- NOT NULL) e apague à mão, com autorização, se o descarte for a decisão.
-- Idempotente: rodar de novo depois de revertido não faz nada.

BEGIN;

DO $pre$
DECLARE
  n bigint;
BEGIN
  IF to_regclass('public.receita_observacao') IS NOT NULL THEN
    SELECT count(*) INTO n FROM public.receita_observacao WHERE operacao <> 'CARGA';
    IF n > 0 THEN
      RAISE EXCEPTION 'v23_01 rollback recusado: receita_observacao tem % versões além da carga inicial', n;
    END IF;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = 'exchange_rate_history' AND column_name = 'as_of') THEN
    EXECUTE 'SELECT count(*) FROM public.exchange_rate_history WHERE as_of IS NOT NULL' INTO n;
    IF n > 0 THEN
      RAISE EXCEPTION 'v23_01 rollback recusado: exchange_rate_history tem % cotações versionadas', n;
    END IF;
  END IF;
END
$pre$;

DROP TRIGGER IF EXISTS zz_receita_observacao ON public.joinads_metrics;
DROP TRIGGER IF EXISTS zz_receita_observacao ON public.gam_metrics;
DROP VIEW IF EXISTS public.vw_receita_vigente;
DROP FUNCTION IF EXISTS public.receita_as_of(timestamptz, text);
DROP FUNCTION IF EXISTS public.receita_registrar_observacao();
DROP FUNCTION IF EXISTS public.receita_observar(text, text, text, jsonb, text[], text, boolean, jsonb);
DROP TABLE IF EXISTS public.receita_observacao;
DROP FUNCTION IF EXISTS public.receita_observacao_imutavel();
DROP FUNCTION IF EXISTS public.cambio_resolver(date, text, integer, timestamptz);

DROP TRIGGER IF EXISTS cambio_versao_guarda ON public.exchange_rate_history;
DROP FUNCTION IF EXISTS public.cambio_versao_guarda();
DROP INDEX IF EXISTS public.exchange_rate_history_versao_uk;
ALTER TABLE public.exchange_rate_history
  DROP CONSTRAINT IF EXISTS exchange_rate_history_par_ck,
  DROP CONSTRAINT IF EXISTS exchange_rate_history_fonte_ck,
  DROP CONSTRAINT IF EXISTS exchange_rate_history_versao_ck,
  DROP CONSTRAINT IF EXISTS exchange_rate_history_taxa_ck,
  DROP COLUMN IF EXISTS proveniencia,
  DROP COLUMN IF EXISTS coletado_em,
  DROP COLUMN IF EXISTS as_of,
  DROP COLUMN IF EXISTS fonte,
  DROP COLUMN IF EXISTS par;

NOTIFY pgrst, 'reload schema';

COMMIT;
