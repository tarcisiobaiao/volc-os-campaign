-- v23_01 rollback — devolve o schema de antes da v23_01 (W12)
--
-- Rode pelo DONO das tabelas (em produção, supabase_admin): DROP TRIGGER
-- exige dono. A pré-checagem recusa antes de tocar em qualquer coisa.
--
-- RECUSA, sem apagar nada, quando já existe dado de negócio que só a v23_01
-- guarda: versões de receita além da carga inicial, ou cotação com as_of
-- (coletada ou manual gravada depois da v23_01, inclusive par que não seja
-- USD/BRL, que o leitor legado leria como dólar). Exporte antes
-- (receita_observacao e exchange_rate_history WHERE as_of IS NOT NULL) e
-- apague à mão, com autorização, se o descarte for a decisão.
-- Idempotente: rodar de novo depois de revertido não faz nada.

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $pre$
DECLARE
  n bigint;
  faltando text;
BEGIN
  SELECT string_agg(t, ', ') INTO faltando
    FROM unnest(ARRAY['public.exchange_rate_history', 'public.joinads_metrics', 'public.gam_metrics']) t
   WHERE to_regclass(t) IS NOT NULL
     AND NOT pg_has_role(current_user, (SELECT relowner FROM pg_class WHERE oid = t::regclass), 'USAGE');
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'v23_01 rollback recusado: % não é dono de % (reverta pelo dono, em produção supabase_admin)',
      current_user, faltando;
  END IF;
  IF to_regclass('public.receita_observacao') IS NOT NULL THEN
    SELECT count(*) INTO n FROM public.receita_observacao WHERE operacao <> 'CARGA';
    IF n > 0 THEN
      RAISE EXCEPTION 'v23_01 rollback recusado: receita_observacao tem % versões além da carga inicial', n;
    END IF;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = 'exchange_rate_history' AND column_name = 'as_of') THEN
    EXECUTE 'SELECT count(*) FROM public.exchange_rate_history WHERE as_of IS NOT NULL OR par <> ''USD/BRL''' INTO n;
    IF n > 0 THEN
      RAISE EXCEPTION 'v23_01 rollback recusado: exchange_rate_history tem % cotações versionadas', n;
    END IF;
  END IF;
END
$pre$;

-- Devolve a escrita que anon/authenticated tinham no câmbio antes da v23_01.
DO $acl$
DECLARE
  r record;
BEGIN
  IF to_regclass('public.v23_01_acl_anterior') IS NOT NULL THEN
    FOR r IN SELECT papel, privilegio FROM public.v23_01_acl_anterior LOOP
      EXECUTE format('GRANT %s ON TABLE public.exchange_rate_history TO %s', r.privilegio,
                     CASE WHEN r.papel = 'PUBLIC' THEN 'PUBLIC' ELSE quote_ident(r.papel) END);
    END LOOP;
  END IF;
END
$acl$;
DROP TABLE IF EXISTS public.v23_01_acl_anterior;

DROP TRIGGER IF EXISTS zz_receita_observacao ON public.joinads_metrics;
DROP TRIGGER IF EXISTS zz_receita_observacao ON public.gam_metrics;
DROP TRIGGER IF EXISTS zz_receita_observacao_truncate ON public.joinads_metrics;
DROP TRIGGER IF EXISTS zz_receita_observacao_truncate ON public.gam_metrics;
DROP VIEW IF EXISTS public.vw_receita_vigente;
DROP FUNCTION IF EXISTS public.receita_as_of(timestamptz, text);
DROP FUNCTION IF EXISTS public.receita_registrar_observacao();
DROP FUNCTION IF EXISTS public.receita_registrar_truncate();
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
