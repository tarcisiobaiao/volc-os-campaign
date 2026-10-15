-- =============================================================================
-- v21_02 — RLS e privilégios das tabelas v6 de RBAC (PROPOSTA, NÃO APLICADA)
-- =============================================================================
-- Contexto (15/10/2026): /settings/users é o ponto oficial de corte para o
-- modelo v6 (`src/pages/settings/UsersSettings.tsx`), mas campaign_roles,
-- campaign_members, campaign_commissions e daily_campaign_member_payouts não
-- existem em produção — as v6_01..v6_05 de `src/sql/` nunca foram aplicadas no
-- self-hosted. A página responde 404 nas três primeiras.
--
-- NÃO APLICAR SOZINHO. Este arquivo é PARTE de
-- `supabase/migrations/v21_pacote_aplicar.sql` (montado por
-- `scripts/montar-pacote-v21.sh`): v7_13 + v21_01 + v6_01..v6_05 + ESTE numa
-- transação só. Aplicadas uma por vez, as v6_0x confirmariam antes deste
-- arquivo, e nesse intervalo a anon leria, apagaria e truncaria as quatro
-- tabelas (sem RLS). Uso isolado só como remédio, sobre tabelas já existentes.
-- Os backfills v6_08/v6_09 ficam fora do pacote e são
-- opcionais: em 15/10 `user_campaigns` tem 0 linhas e nenhum usuário tem
-- `commission_percentage > 0`, então não inserem nada.
--
-- POR QUE ESTE ARQUIVO EXISTE: as v6_0x criam as tabelas SEM RLS, e o default
-- ACL de produção dá `arwdDxt` a anon e authenticated em toda tabela nova. Sem
-- isto, a chave anon (pública, no bundle) leria e reescreveria comissões.
--
-- Regra: admin (public.volc_current_admin(), papel em app_auth.user_roles)
-- lê e escreve; o próprio usuário lê os seus vínculos, comissões e payouts;
-- anon não vê nada. payouts só são escritos por função, nunca pelo cliente.
-- =============================================================================

DO $guarda$
BEGIN
  IF to_regclass('public.campaign_roles') IS NULL
     OR to_regclass('public.campaign_members') IS NULL
     OR to_regclass('public.campaign_commissions') IS NULL
     OR to_regclass('public.daily_campaign_member_payouts') IS NULL
     OR to_regprocedure('public.v6_populate_member_payouts_for_date(date)') IS NULL THEN
    RAISE EXCEPTION 'v21_02: aplique src/sql/v6_01..v6_05 antes';
  END IF;
  IF to_regprocedure('public.volc_current_admin()') IS NULL THEN
    RAISE EXCEPTION 'v21_02: public.volc_current_admin() ausente (v8_01)';
  END IF;
END
$guarda$;

-- 1. Fecha tudo, depois abre só o necessário ---------------------------------
REVOKE ALL ON TABLE
  public.campaign_roles, public.campaign_members,
  public.campaign_commissions, public.daily_campaign_member_payouts
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE
  public.campaign_roles_id_seq, public.campaign_members_id_seq,
  public.campaign_commissions_id_seq, public.daily_campaign_member_payouts_id_seq
  FROM PUBLIC, anon, authenticated;

GRANT SELECT ON TABLE public.campaign_roles TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.campaign_members, public.campaign_commissions TO authenticated;
GRANT SELECT ON TABLE public.daily_campaign_member_payouts TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.campaign_members_id_seq, public.campaign_commissions_id_seq TO authenticated;

GRANT ALL ON TABLE
  public.campaign_roles, public.campaign_members,
  public.campaign_commissions, public.daily_campaign_member_payouts
  TO service_role;
GRANT USAGE, SELECT ON SEQUENCE
  public.campaign_roles_id_seq, public.campaign_members_id_seq,
  public.campaign_commissions_id_seq, public.daily_campaign_member_payouts_id_seq
  TO service_role;

-- 2. RLS ---------------------------------------------------------------------
ALTER TABLE public.campaign_roles                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_members              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_commissions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_campaign_member_payouts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS campaign_roles_leitura ON public.campaign_roles;
CREATE POLICY campaign_roles_leitura ON public.campaign_roles
  FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS campaign_members_leitura ON public.campaign_members;
CREATE POLICY campaign_members_leitura ON public.campaign_members
  FOR SELECT TO authenticated
  USING (public.volc_current_admin() OR user_id = (SELECT auth.uid()));
DROP POLICY IF EXISTS campaign_members_escrita_admin ON public.campaign_members;
CREATE POLICY campaign_members_escrita_admin ON public.campaign_members
  FOR ALL TO authenticated
  USING (public.volc_current_admin()) WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS campaign_commissions_leitura ON public.campaign_commissions;
CREATE POLICY campaign_commissions_leitura ON public.campaign_commissions
  FOR SELECT TO authenticated
  USING (public.volc_current_admin() OR user_id = (SELECT auth.uid()));
DROP POLICY IF EXISTS campaign_commissions_escrita_admin ON public.campaign_commissions;
CREATE POLICY campaign_commissions_escrita_admin ON public.campaign_commissions
  FOR ALL TO authenticated
  USING (public.volc_current_admin()) WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS dcmp_leitura ON public.daily_campaign_member_payouts;
CREATE POLICY dcmp_leitura ON public.daily_campaign_member_payouts
  FOR SELECT TO authenticated
  USING (public.volc_current_admin() OR user_id = (SELECT auth.uid()));

-- 3. Funções v6: as de escrita ficam com service_role -------------------------
REVOKE ALL ON FUNCTION
  public.v6_get_active_commission_rate(uuid, varchar, date),
  public.v6_calculate_member_commission(numeric, numeric, numeric, date),
  public.v6_populate_member_payouts_for_date(date),
  public.v6_populate_member_payouts_for_range(date, date)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  public.v6_get_active_commission_rate(uuid, varchar, date),
  public.v6_calculate_member_commission(numeric, numeric, numeric, date)
  TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION
  public.v6_populate_member_payouts_for_date(date),
  public.v6_populate_member_payouts_for_range(date, date)
  TO service_role;

NOTIFY pgrst, 'reload schema';
