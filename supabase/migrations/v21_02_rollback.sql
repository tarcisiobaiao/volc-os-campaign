-- =============================================================================
-- v21_02_rollback — desfaz v6_01..v6_05 + v21_02 (PROPOSTA, NÃO APLICADA)
-- =============================================================================
-- Só derruba se vínculos, comissões e payouts estiverem VAZIOS: são dado de
-- negócio (quem opera o quê e quanto recebe). campaign_roles só tem o
-- catálogo semeado pela v6_01 e cai junto. Rodar com `psql -1 -v ON_ERROR_STOP=1`.
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
