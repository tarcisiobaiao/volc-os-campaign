-- =============================================================================
-- v8_04 — Revogacao dos grants de public.users e grants minimos
-- SPRINT 1A / FRENTE 2 — CONTENCAO DE SEGURANCA. ARQUIVO. NAO APLICADO.
-- =============================================================================
-- APLICAR COMO: supabase_admin  (dono de public.users; os grants de postgres
--   na tabela tem is_grantable = NO, entao postgres nao consegue revogar)
--   -- (comando de aplicacao: ver runbook privado de infraestrutura)
--     -- (comando de aplicacao: ver runbook privado de infraestrutura)
--
-- DEPENDE DE: v8_01, v8_02 (obrigatorio — ver guarda), v8_03
--
-- -----------------------------------------------------------------------------
-- ESTADO REAL MEDIDO EM 2026-08-24 — information_schema.role_table_grants
-- -----------------------------------------------------------------------------
-- public.users tem, para CADA um de anon, authenticated, postgres e service_role,
-- os SETE privilegios: SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES,
-- TRIGGER (28 linhas). is_grantable = NO em todas.
--
-- information_schema.column_privileges confirma o mesmo nas colunas sensiveis:
--   password_hash          -> anon e authenticated com SELECT, INSERT, UPDATE, REFERENCES
--   token_primeiro_acesso  -> idem
--   token_expiracao        -> idem
--   role                   -> idem  (este e o vetor de autopromocao)
--
-- Ou seja: com a anon key que vai no bundle do browser
-- (src/lib/supabase.ts:10, VITE_SUPABASE_ANON_KEY), sem nenhum login,
-- era possivel ler o hash de senha e os tokens de primeiro acesso de todos,
-- e escrever role='ADMIN' em qualquer linha. RLS estava desligada (v8_03/M1),
-- entao nao havia nada entre o grant e a tabela.
--
-- A origem disso e estrutural, nao um GRANT esquecido: pg_default_acl concede
-- arwdDxt em toda tabela nova de public para anon, authenticated e service_role
-- (dois donos: postgres e supabase_admin). Toda tabela criada em public nasce
-- assim. Ver v8_07 (opcional) para a correcao de raiz.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO FAZ, E O QUE DELIBERADAMENTE NAO FAZ
-- -----------------------------------------------------------------------------
-- FAZ agora:
--   - anon perde TUDO em public.users. anon nao e usuario; e portador de chave.
--   - authenticated perde os privilegios amplos e recebe grants por coluna
--     para INSERT e UPDATE. password_hash, token_primeiro_acesso e
--     token_expiracao ficam SEM INSERT e SEM UPDATE — o vetor de ESCRITA nas
--     colunas sensiveis fecha aqui, junto com a RLS de v8_03.
--   - TRUNCATE, REFERENCES e TRIGGER saem de anon e authenticated.
--
-- NAO FAZ agora, de proposito:
--   - NAO revoga SELECT amplo de authenticated. Isso e v8_06, e quebra o
--     frontend enquanto ele usar `select('*')` (src/hooks/useUserProfile.ts:62
--     e :72). Fazer aqui derrubaria o carregamento de perfil. Sequencia
--     documentada no README.
--   - NAO mexe em service_role. RLS e grants nao contem service_role
--     (rolbypassrls = t) e o backend depende dele. Fechar os endpoints que
--     usam a service key sem autenticacao e Frente 1/3.
--   - NAO apaga coluna nem dado.
--
-- RISCO RESIDUAL ACEITO NESTE PASSO, medido e nomeado: entre v8_04 e v8_06, um
-- usuario autenticado nao-admin consegue LER as tres colunas sensiveis DA
-- PROPRIA LINHA (a RLS de v8_03 impede ver a de outros). Hoje isso e vazio:
-- count(password_hash) = count(token_primeiro_acesso) = count(token_expiracao)
-- = 0 nas 1 linha existente. O prejuizo real do intervalo e nulo; a pressa
-- pertence a revogacao de anon, que este arquivo executa.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- --- Guardas de pre-condicao ------------------------------------------------
DO $guard$
DECLARE
  v_owner  text;
  v_quebra int;
BEGIN
  SELECT pg_get_userbyid(c.relowner) INTO v_owner
  FROM pg_class c WHERE c.oid = 'public.users'::regclass;

  IF NOT pg_has_role(current_user, v_owner, 'USAGE') THEN
    RAISE EXCEPTION
      'v8_04 exige o dono de public.users (%). current_user = %.',
      v_owner, current_user;
  END IF;

  -- Sem v8_02, revogar SELECT quebraria as policies do Pautador, que leem
  -- public.users com os privilegios do chamador.
  SELECT count(*) INTO v_quebra
  FROM pg_policies
  WHERE schemaname = 'public'
    AND tablename <> 'users'
    AND (coalesce(qual, '') ~ 'FROM users'
      OR coalesce(with_check, '') ~ 'FROM users');
  IF v_quebra > 0 THEN
    RAISE EXCEPTION
      'v8_04 ABORTADA: % policy(ies) fora de public.users ainda leem '
      'public.users na expressao. Aplique v8_02 antes ou elas passam a falhar '
      'com "permission denied for table users".', v_quebra;
  END IF;

  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid='public.users'::regclass) THEN
    RAISE EXCEPTION
      'v8_04 ABORTADA: RLS desligada em public.users. Aplique v8_03 antes — '
      'revogar grants sem policies deixaria ate o ADMIN sem acesso.';
  END IF;
END
$guard$;

-- =============================================================================
-- 1. anon — zero acesso
-- =============================================================================
REVOKE ALL PRIVILEGES ON TABLE public.users FROM anon;

-- =============================================================================
-- 2. authenticated — reseta e reconcede o minimo
-- =============================================================================
-- REVOKE ALL limpa tambem os privilegios de coluna, entao a lista abaixo passa
-- a ser a definicao completa do que authenticated pode fazer.
REVOKE ALL PRIVILEGES ON TABLE public.users FROM authenticated;

-- SELECT: amplo NESTE PASSO. Fica assim ate v8_06 (ver cabecalho).
GRANT SELECT ON TABLE public.users TO authenticated;

-- INSERT: so as colunas de perfil. Sem password_hash, sem token_*.
-- A policy users_insert_admin (v8_03) ainda exige ADMIN para a linha passar.
GRANT INSERT (
  id,
  name,
  email,
  role,
  first_login,
  needs_password_change,
  commission_percentage
) ON TABLE public.users TO authenticated;

-- UPDATE: so as colunas de perfil. Sem password_hash, sem token_*.
-- role e commission_percentage entram na lista porque a tela de admin edita
-- ambas; quem valida a AUTORIDADE dessa edicao e o gatilho
-- app_auth.tg_users_guard_privileged_columns (v8_01/v8_03), nao o grant.
GRANT UPDATE (
  name,
  email,
  role,
  first_login,
  needs_password_change,
  commission_percentage,
  updated_at
) ON TABLE public.users TO authenticated;

-- DELETE: linha inteira, filtrada por users_delete_admin (v8_03) e barrada
-- pelo gatilho de ultimo ADMIN.
GRANT DELETE ON TABLE public.users TO authenticated;

-- TRUNCATE, REFERENCES e TRIGGER ficam de fora de proposito: TRUNCATE ignora
-- policies de DELETE e apagaria a tabela inteira sob RLS.

-- =============================================================================
-- 3. Verificacao dentro da propria transacao — falha fechada
-- =============================================================================
DO $verify$
DECLARE
  v_anon int;
  v_col  int;
BEGIN
  SELECT count(*) INTO v_anon
  FROM information_schema.role_table_grants
  WHERE table_schema = 'public' AND table_name = 'users' AND grantee = 'anon';
  IF v_anon > 0 THEN
    RAISE EXCEPTION 'v8_04 falhou: anon ainda tem % privilegio(s) em public.users', v_anon;
  END IF;

  SELECT count(*) INTO v_col
  FROM information_schema.column_privileges
  WHERE table_schema = 'public' AND table_name = 'users'
    AND grantee IN ('anon', 'authenticated')
    AND column_name IN ('password_hash', 'token_primeiro_acesso', 'token_expiracao')
    AND privilege_type IN ('INSERT', 'UPDATE');
  IF v_col > 0 THEN
    RAISE EXCEPTION
      'v8_04 falhou: ainda existe INSERT/UPDATE de anon/authenticated em '
      'coluna sensivel (% ocorrencias)', v_col;
  END IF;

  RAISE NOTICE 'v8_04: anon zerado; escrita em colunas sensiveis fechada para '
               'anon e authenticated. SELECT amplo de authenticated segue ate v8_06.';
END
$verify$;

COMMIT;

-- =============================================================================
-- ACHADO MEDIDO, FORA DO ESCOPO DESTE ARQUIVO (registrado, nao alterado)
-- =============================================================================
-- public.user_campaigns e public.user_projects tem RLS DESLIGADA e os mesmos
-- 7 privilegios para anon e authenticated. Sao a fonte de escopo do OPERATOR
-- (quais campanhas/projetos ele ve). Conter as duas exige desenhar as policies
-- de escopo junto, senao as telas de operador quebram. Sprint 1B — ver README.
--
-- VERIFICACAO POS-APLICACAO (somente leitura)
-- SELECT grantee, privilege_type FROM information_schema.role_table_grants
--  WHERE table_schema='public' AND table_name='users' ORDER BY 1,2;
-- SELECT grantee, column_name, privilege_type FROM information_schema.column_privileges
--  WHERE table_schema='public' AND table_name='users'
--    AND column_name IN ('password_hash','token_primeiro_acesso','token_expiracao')
--  ORDER BY 1,2,3;
