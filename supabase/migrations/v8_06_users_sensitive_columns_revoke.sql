-- =============================================================================
-- v8_06 — Revoga SELECT das colunas sensiveis de public.users
-- SPRINT 1A / FRENTE 2 — CONTENCAO DE SEGURANCA. ARQUIVO. NAO APLICADO.
-- =============================================================================
-- >>> ESTE ARQUIVO QUEBRA O FRONTEND SE APLICADO CEDO DEMAIS. LEIA A PRE-CONDICAO.
--
-- APLICAR COMO: supabase_admin
--   -- (comando de aplicacao: ver runbook privado de infraestrutura)
--     -- (comando de aplicacao: ver runbook privado de infraestrutura)
--
-- DEPENDE DE: v8_04 (grants reescritos) e v8_05 (view substituta existe)
--
-- -----------------------------------------------------------------------------
-- PRE-CONDICAO DE PRODUTO — NAO E OPCIONAL
-- -----------------------------------------------------------------------------
-- Depois deste arquivo, `authenticated` deixa de ter SELECT de tabela em
-- public.users e passa a ter SELECT apenas nas 9 colunas nao sensiveis.
-- Consequencia direta: toda consulta com `select('*')` sobre a tabela `users`
-- feita com a chave do browser passa a devolver
--   42501: permission denied for column password_hash
--
-- Ocorrencias medidas no repositorio, ambas no mesmo hook:
--   src/hooks/useUserProfile.ts:62  -> supabase.from('users').select('*').eq('id', user.id)
--   src/hooks/useUserProfile.ts:72  -> supabase.from('users').select('*').eq('email', user.email)
--
-- Trocar essas duas chamadas por public.users_safe (v8_05), ou por lista
-- nominal de colunas, e propriedade da Frente 1/3. So aplique v8_06 depois que
-- a mudanca estiver em producao. A guarda abaixo NAO consegue verificar isso —
-- e uma decisao humana de sequenciamento.
--
-- Se aplicar por engano: o rollback deste passo e UMA linha, sem perda de dado.
--   GRANT SELECT ON TABLE public.users TO authenticated;
--
-- -----------------------------------------------------------------------------
-- ESTADO MEDIDO E O QUE MUDA
-- -----------------------------------------------------------------------------
-- Antes de v8_04: anon E authenticated tinham SELECT, INSERT, UPDATE e
-- REFERENCES em password_hash, token_primeiro_acesso e token_expiracao
-- (information_schema.column_privileges, 2026-08-24).
-- v8_04 tirou anon por inteiro e tirou INSERT/UPDATE de authenticated.
-- v8_06 tira o ultimo pedaco: o SELECT de authenticated nessas tres colunas.
--
-- Conteudo hoje: as tres colunas sao 100% NULL na unica linha existente.
-- Nada e apagado, nada e movido. So o privilegio muda. A migracao dos campos
-- para um armazenamento proprio (fora de public.users) e PROPOSTA no README,
-- NAO executada aqui.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guard$
DECLARE
  v_owner text;
BEGIN
  SELECT pg_get_userbyid(c.relowner) INTO v_owner
  FROM pg_class c WHERE c.oid = 'public.users'::regclass;
  IF NOT pg_has_role(current_user, v_owner, 'USAGE') THEN
    RAISE EXCEPTION 'v8_06 exige o dono de public.users (%)', v_owner;
  END IF;

  IF to_regclass('public.users_safe') IS NULL THEN
    RAISE EXCEPTION
      'v8_06 ABORTADA: public.users_safe nao existe. Aplique v8_05 antes — '
      'nao se tira o acesso sem entregar o substituto.';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.role_table_grants
    WHERE table_schema='public' AND table_name='users' AND grantee='anon'
  ) THEN
    RAISE EXCEPTION 'v8_06 ABORTADA: anon ainda tem grants em public.users. Aplique v8_04 antes.';
  END IF;
END
$guard$;

-- Derruba o SELECT de tabela (que cobre toda coluna, presente e futura)...
REVOKE SELECT ON TABLE public.users FROM authenticated;

-- ...e devolve nominalmente as 9 colunas nao sensiveis.
-- Coluna nova criada no futuro NAO entra aqui automaticamente: passa a ser
-- decisao explicita de uma migration futura. E o comportamento desejado.
GRANT SELECT (
  id,
  name,
  email,
  role,
  first_login,
  needs_password_change,
  commission_percentage,
  created_at,
  updated_at
) ON TABLE public.users TO authenticated;

DO $verify$
DECLARE
  v_vaz int;
BEGIN
  SELECT count(*) INTO v_vaz
  FROM information_schema.column_privileges
  WHERE table_schema='public' AND table_name='users'
    AND grantee IN ('anon','authenticated')
    AND column_name IN ('password_hash','token_primeiro_acesso','token_expiracao');
  IF v_vaz > 0 THEN
    RAISE EXCEPTION
      'v8_06 falhou: % privilegio(s) de anon/authenticated restam nas colunas '
      'sensiveis', v_vaz;
  END IF;
  RAISE NOTICE 'v8_06: colunas sensiveis sem privilegio algum de anon e authenticated';
END
$verify$;

COMMIT;

-- =============================================================================
-- VERIFICACAO POS-APLICACAO (somente leitura)
-- =============================================================================
-- SELECT grantee, column_name, privilege_type FROM information_schema.column_privileges
--  WHERE table_schema='public' AND table_name='users' AND grantee='authenticated'
--  ORDER BY column_name, privilege_type;
--   -- password_hash, token_primeiro_acesso e token_expiracao NAO podem aparecer
