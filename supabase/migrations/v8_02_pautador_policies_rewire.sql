-- =============================================================================
-- v8_02 — Reescreve as 23 policies do Pautador para o portao de app_auth
-- SPRINT 1A / FRENTE 2 — CONTENCAO DE SEGURANCA. ARQUIVO. NAO APLICADO.
-- =============================================================================
-- APLICAR COMO: postgres  (as 12 tabelas pautador_* sao propriedade de postgres)
--   -- (comando de aplicacao: ver runbook privado de infraestrutura)
--     -- (comando de aplicacao: ver runbook privado de infraestrutura)
--
-- DEPENDE DE: v8_01 (funcoes public.volc_current_admin / volc_current_user_known)
-- PRE-REQUISITO DE: v8_04 — sem este arquivo, revogar SELECT de public.users
--                   quebra as 23 policies abaixo com "permission denied".
--
-- -----------------------------------------------------------------------------
-- POR QUE ESTE ARQUIVO EXISTE (nao e cosmetico)
-- -----------------------------------------------------------------------------
-- Estado medido em 2026-08-24: 23 policies em 12 tabelas public.pautador_*
-- avaliam autorizacao com esta subconsulta literal:
--
--   EXISTS (SELECT 1 FROM users u
--           WHERE lower(u.email) = lower(auth.jwt() ->> 'email')
--             AND u.role = 'ADMIN')
--
-- Duas consequencias medidas:
--
--   P1. Expressao de policy roda com os privilegios do papel que faz a consulta.
--       Como a expressao le public.users, o papel `authenticated` PRECISA ter
--       SELECT em public.users para que qualquer leitura do Pautador funcione.
--       O item 3 do escopo (revogar grants de public.users) quebraria as 12
--       telas do Pautador de uma vez. Trocar a subconsulta por uma funcao
--       SECURITY DEFINER remove essa dependencia de privilegio.
--
--   P2. A autoridade de papel dessas policies e public.users.role — a mesma
--       coluna que `authenticated` podia UPDATE (medido: grant UPDATE em
--       public.users.role para anon E authenticated). Ou seja: quem conseguisse
--       um UPDATE em public.users virava ADMIN do Pautador. A autoridade passa
--       para app_auth.user_roles, que nao tem rota REST (v8_01, decisao a/b).
--
-- -----------------------------------------------------------------------------
-- MUDANCA DE SEMANTICA — LEIA ANTES DE APLICAR
-- -----------------------------------------------------------------------------
-- ANTES: "ADMIN" = existe linha em public.users com este email e role='ADMIN'.
-- DEPOIS: "ADMIN" = existe linha ATIVA em app_auth.user_roles para o sub do JWT.
--
-- v8_01 semeia app_auth.user_roles a partir de public.users por email e ABORTA
-- se nenhum ADMIN sobreviver a semeadura. Para o unico usuario existente hoje
-- (1 linha, ADMIN) o resultado e identico.
--
-- CONSEQUENCIA OPERACIONAL: um ADMIN criado DEPOIS desta migration pelo caminho
-- legado (api/users/create.js:82 insere em public.users) NAO recebe papel em
-- app_auth e NAO tera acesso admin ao Pautador. O caminho suportado passa a ser
-- public.volc_grant_role(auth_user_id, 'ADMIN'), com EXECUTE apenas para
-- service_role. Ligar essa chamada ao fluxo de criacao e trabalho da Frente 1/3.
-- Deliberadamente NAO existe trigger espelhando public.users.role -> app_auth:
-- isso reabriria a escalada, porque server/index.js:251 (/api/supabase/update)
-- escreve em qualquer tabela com a service key e sem autenticacao.
--
-- "read auth" (usuario conhecido) mantem a semantica antiga por
-- public.volc_current_user_known(), que continua olhando public.users — mas
-- agora como DEFINER, sem exigir grant do chamador.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- --- Guardas de pre-condicao ------------------------------------------------
DO $guard$
BEGIN
  IF to_regprocedure('public.volc_current_admin()') IS NULL
     OR to_regprocedure('public.volc_current_user_known()') IS NULL THEN
    RAISE EXCEPTION
      'v8_02 abortada: aplique v8_01 antes (funcoes volc_* ausentes)';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM app_auth.user_roles
    WHERE role = 'ADMIN' AND revoked_at IS NULL
  ) THEN
    RAISE EXCEPTION
      'v8_02 abortada: nenhum ADMIN ativo em app_auth.user_roles — as policies '
      'reescritas deixariam o Pautador sem nenhum administrador';
  END IF;
END
$guard$;

-- =============================================================================
-- Reescrita. DROP + CREATE preservando NOME, TABELA, COMANDO e PAPEL de cada
-- policy, para que o rollback (v8_99) seja um espelho exato do estado medido.
-- =============================================================================

-- --- pautador_agent_logs (1 policy) -----------------------------------------
DROP POLICY IF EXISTS "pautador_logs admin read" ON public.pautador_agent_logs;
CREATE POLICY "pautador_logs admin read" ON public.pautador_agent_logs
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (public.volc_current_admin());

-- --- pautador_countries ------------------------------------------------------
DROP POLICY IF EXISTS "pautador_countries admin all" ON public.pautador_countries;
CREATE POLICY "pautador_countries admin all" ON public.pautador_countries
  AS PERMISSIVE FOR ALL TO authenticated
  USING (public.volc_current_admin())
  WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS "pautador_countries read auth" ON public.pautador_countries;
CREATE POLICY "pautador_countries read auth" ON public.pautador_countries
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (public.volc_current_user_known());

-- --- pautador_entities -------------------------------------------------------
DROP POLICY IF EXISTS "pautador_entities admin all" ON public.pautador_entities;
CREATE POLICY "pautador_entities admin all" ON public.pautador_entities
  AS PERMISSIVE FOR ALL TO authenticated
  USING (public.volc_current_admin())
  WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS "pautador_entities read auth" ON public.pautador_entities;
CREATE POLICY "pautador_entities read auth" ON public.pautador_entities
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (public.volc_current_user_known());

-- --- pautador_entity_funnel_hypotheses ---------------------------------------
DROP POLICY IF EXISTS "pautador_entity_funnel_hypotheses admin all"
  ON public.pautador_entity_funnel_hypotheses;
CREATE POLICY "pautador_entity_funnel_hypotheses admin all"
  ON public.pautador_entity_funnel_hypotheses
  AS PERMISSIVE FOR ALL TO authenticated
  USING (public.volc_current_admin())
  WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS "pautador_entity_funnel_hypotheses read auth"
  ON public.pautador_entity_funnel_hypotheses;
CREATE POLICY "pautador_entity_funnel_hypotheses read auth"
  ON public.pautador_entity_funnel_hypotheses
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (public.volc_current_user_known());

-- --- pautador_entity_opportunities -------------------------------------------
DROP POLICY IF EXISTS "pautador_entity_opportunities admin all"
  ON public.pautador_entity_opportunities;
CREATE POLICY "pautador_entity_opportunities admin all"
  ON public.pautador_entity_opportunities
  AS PERMISSIVE FOR ALL TO authenticated
  USING (public.volc_current_admin())
  WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS "pautador_entity_opportunities read auth"
  ON public.pautador_entity_opportunities;
CREATE POLICY "pautador_entity_opportunities read auth"
  ON public.pautador_entity_opportunities
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (public.volc_current_user_known());

-- --- pautador_entity_pains ---------------------------------------------------
DROP POLICY IF EXISTS "pautador_entity_pains admin all" ON public.pautador_entity_pains;
CREATE POLICY "pautador_entity_pains admin all" ON public.pautador_entity_pains
  AS PERMISSIVE FOR ALL TO authenticated
  USING (public.volc_current_admin())
  WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS "pautador_entity_pains read auth" ON public.pautador_entity_pains;
CREATE POLICY "pautador_entity_pains read auth" ON public.pautador_entity_pains
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (public.volc_current_user_known());

-- --- pautador_entity_seed_queries --------------------------------------------
DROP POLICY IF EXISTS "pautador_entity_seed_queries admin all"
  ON public.pautador_entity_seed_queries;
CREATE POLICY "pautador_entity_seed_queries admin all"
  ON public.pautador_entity_seed_queries
  AS PERMISSIVE FOR ALL TO authenticated
  USING (public.volc_current_admin())
  WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS "pautador_entity_seed_queries read auth"
  ON public.pautador_entity_seed_queries;
CREATE POLICY "pautador_entity_seed_queries read auth"
  ON public.pautador_entity_seed_queries
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (public.volc_current_user_known());

-- --- pautador_funnels --------------------------------------------------------
DROP POLICY IF EXISTS "pautador_funnels admin all" ON public.pautador_funnels;
CREATE POLICY "pautador_funnels admin all" ON public.pautador_funnels
  AS PERMISSIVE FOR ALL TO authenticated
  USING (public.volc_current_admin())
  WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS "pautador_funnels read auth" ON public.pautador_funnels;
CREATE POLICY "pautador_funnels read auth" ON public.pautador_funnels
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (public.volc_current_user_known());

-- --- pautador_keyword_clusters (nomes das policies dizem "clusters") ---------
DROP POLICY IF EXISTS "pautador_clusters admin all" ON public.pautador_keyword_clusters;
CREATE POLICY "pautador_clusters admin all" ON public.pautador_keyword_clusters
  AS PERMISSIVE FOR ALL TO authenticated
  USING (public.volc_current_admin())
  WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS "pautador_clusters read auth" ON public.pautador_keyword_clusters;
CREATE POLICY "pautador_clusters read auth" ON public.pautador_keyword_clusters
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (public.volc_current_user_known());

-- --- pautador_niches ---------------------------------------------------------
DROP POLICY IF EXISTS "pautador_niches admin all" ON public.pautador_niches;
CREATE POLICY "pautador_niches admin all" ON public.pautador_niches
  AS PERMISSIVE FOR ALL TO authenticated
  USING (public.volc_current_admin())
  WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS "pautador_niches read auth" ON public.pautador_niches;
CREATE POLICY "pautador_niches read auth" ON public.pautador_niches
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (public.volc_current_user_known());

-- --- pautador_opportunities --------------------------------------------------
DROP POLICY IF EXISTS "pautador_opportunities admin all" ON public.pautador_opportunities;
CREATE POLICY "pautador_opportunities admin all" ON public.pautador_opportunities
  AS PERMISSIVE FOR ALL TO authenticated
  USING (public.volc_current_admin())
  WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS "pautador_opportunities read auth" ON public.pautador_opportunities;
CREATE POLICY "pautador_opportunities read auth" ON public.pautador_opportunities
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (public.volc_current_user_known());

-- --- pautador_runs -----------------------------------------------------------
DROP POLICY IF EXISTS "pautador_runs admin all" ON public.pautador_runs;
CREATE POLICY "pautador_runs admin all" ON public.pautador_runs
  AS PERMISSIVE FOR ALL TO authenticated
  USING (public.volc_current_admin())
  WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS "pautador_runs read auth" ON public.pautador_runs;
CREATE POLICY "pautador_runs read auth" ON public.pautador_runs
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (public.volc_current_user_known());

-- --- Verificacao interna: nenhuma policy pautador_* pode ainda ler users -----
DO $verify$
DECLARE
  v_resto int;
BEGIN
  SELECT count(*) INTO v_resto
  FROM pg_policies
  WHERE schemaname = 'public'
    AND tablename LIKE 'pautador%'
    AND (coalesce(qual, '') ~ 'FROM users'
      OR coalesce(with_check, '') ~ 'FROM users');
  IF v_resto > 0 THEN
    RAISE EXCEPTION
      'v8_02 abortada: % policy(ies) pautador_* ainda leem public.users; '
      'v8_04 as quebraria', v_resto;
  END IF;
  RAISE NOTICE 'v8_02: 23 policies reescritas; nenhuma le mais public.users';
END
$verify$;

COMMIT;

-- =============================================================================
-- NOTA — tabelas pautador_* SEM policy (medido, fora do escopo desta migration)
-- =============================================================================
-- Com RLS ligada e ZERO policies (nega tudo para anon/authenticated; correto):
--   public.pautador_trafego_copy, public.project_wordpress
-- Com RLS DESLIGADA (grants plenos de anon valem; nao contido nesta frente):
--   public.pautador_entity_axes, public.pautador_question_choices,
--   public.pautador_validation_runs
-- Registrado no README como achado de Sprint 1B.
--
-- VERIFICACAO POS-APLICACAO (somente leitura)
-- SELECT tablename, policyname, qual FROM pg_policies
--  WHERE schemaname='public' AND tablename LIKE 'pautador%' ORDER BY 1,2;
