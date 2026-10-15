-- =============================================================================
-- v21_pacote_reverter — desfaz o v21_pacote_aplicar (PROPOSTA, NÃO APLICADA)
-- GERADO por scripts/montar-pacote-v21.sh. NÃO EDITAR: edite as partes e rode
-- o gerador; `scripts/montar-pacote-v21.sh --check` acusa pacote defasado.
--
-- Uma transação só. Aplicar com:
--   psql -X -v ON_ERROR_STOP=1 -f supabase/migrations/v21_pacote_reverter.sql
-- Qualquer erro desfaz o pacote inteiro; nenhuma outra sessão vê estado
-- intermediário. NÃO aplicar as partes uma a uma (ver v21_01/v21_02).
--
-- Partes (sha256 no momento da montagem):
--   770ae191d2bc312ab161dd46b27fb05dd0ce458b861becd16e5e7d0318f43a68  supabase/migrations/v21_02_rollback.sql
--   505f1b317c0f808650de6c1762ef28fbab7d4e6e445fa51a7b77ff49c72126ea  supabase/migrations/v21_01_rollback.sql
-- =============================================================================
\set ON_ERROR_STOP on
BEGIN;

-- >>>>> início da parte: supabase/migrations/v21_02_rollback.sql
-- =============================================================================
-- v21_02_rollback — desfaz v6_01..v6_05 + v21_02 (PROPOSTA, NÃO APLICADA)
-- =============================================================================
-- Só derruba se vínculos, comissões e payouts estiverem VAZIOS: são dado de
-- negócio (quem opera o quê e quanto recebe). campaign_roles só tem o
-- catálogo semeado pela v6_01 e cai junto. PARTE de
-- `supabase/migrations/v21_pacote_reverter.sql` (transação única, antes do
-- v21_01_rollback). Não rodar sozinho.
-- =============================================================================

DO $guarda$
DECLARE
  tabela text;
  n bigint;
BEGIN
  FOREACH tabela IN ARRAY ARRAY['campaign_members', 'campaign_commissions', 'daily_campaign_member_payouts'] LOOP
    IF to_regclass('public.' || tabela) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM public.%I', tabela) INTO n;
      IF n > 0 THEN
        RAISE EXCEPTION 'v21_02_rollback: % tem % linha(s); exporte antes de derrubar', tabela, n;
      END IF;
    END IF;
  END LOOP;
END
$guarda$;

DROP FUNCTION IF EXISTS public.v6_populate_member_payouts_for_range(date, date);
DROP FUNCTION IF EXISTS public.v6_populate_member_payouts_for_date(date);
DROP FUNCTION IF EXISTS public.v6_calculate_member_commission(numeric, numeric, numeric, date);
DROP FUNCTION IF EXISTS public.v6_get_active_commission_rate(uuid, varchar, date);

DROP TABLE IF EXISTS public.daily_campaign_member_payouts;
DROP TABLE IF EXISTS public.campaign_commissions;
DROP TABLE IF EXISTS public.campaign_members;
DROP TABLE IF EXISTS public.campaign_roles;

NOTIFY pgrst, 'reload schema';

-- <<<<< fim da parte: supabase/migrations/v21_02_rollback.sql

-- >>>>> início da parte: supabase/migrations/v21_01_rollback.sql
-- =============================================================================
-- v21_01_rollback — desfaz v7_13 + v21_01 (PROPOSTA, NÃO APLICADA)
-- =============================================================================
-- Só derruba a tabela se ela estiver VAZIA: uma linha ali é um site cadastrado
-- com token da Meta, e apagá-la sem querer desliga o rastreamento daquele site.
-- `set_pautador_updated_at()` já existia em produção antes da v7_13 e fica.
-- PARTE de `supabase/migrations/v21_pacote_reverter.sql` (transação única,
-- depois do v21_02_rollback). Não rodar sozinho.
-- =============================================================================

DO $guarda$
DECLARE
  n bigint;
BEGIN
  IF to_regclass('public.meta_capi_sites') IS NULL THEN
    RAISE NOTICE 'v21_01_rollback: meta_capi_sites já não existe; nada a fazer';
    RETURN;
  END IF;
  EXECUTE 'SELECT count(*) FROM public.meta_capi_sites' INTO n;
  IF n > 0 THEN
    RAISE EXCEPTION 'v21_01_rollback: meta_capi_sites tem % linha(s); exporte antes de derrubar', n;
  END IF;
  EXECUTE 'DROP TABLE public.meta_capi_sites';
END
$guarda$;

NOTIFY pgrst, 'reload schema';

-- <<<<< fim da parte: supabase/migrations/v21_01_rollback.sql

-- Pós-checagem: ou some tudo, ou nada é confirmado. Se o v21_01_rollback recusar
-- (site cadastrado), o v21_02_rollback que já rodou acima também é desfeito.
DO $pos$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['meta_capi_sites', 'campaign_roles', 'campaign_members',
                           'campaign_commissions', 'daily_campaign_member_payouts'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      RAISE EXCEPTION 'v21_pacote_reverter: public.% ainda existe', t;
    END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_proc WHERE pronamespace = 'public'::regnamespace AND proname LIKE 'v6\_%') THEN
    RAISE EXCEPTION 'v21_pacote_reverter: funções v6_* ainda existem';
  END IF;
END
$pos$;

COMMIT;
