-- =============================================================================
-- v8_01 — Schema privado de autorizacao (app_auth) + tabela de papeis
-- SPRINT 1A / FRENTE 2 — CONTENCAO DE SEGURANCA. ARQUIVO. NAO APLICADO.
-- =============================================================================
-- APLICAR COMO: postgres
--   -- (comando de aplicacao: ver runbook privado de infraestrutura)
--     -- (comando de aplicacao: ver runbook privado de infraestrutura)
--
-- ORDEM: v8_01 -> v8_02 -> v8_03 -> v8_04 -> v8_05 -> (v8_06 so depois da Frente 1/3)
-- ROLLBACK: supabase/migrations/v8_99_rollback.sql
--
-- -----------------------------------------------------------------------------
-- ESTADO REAL MEDIDO EM 2026-08-24 (SELECT no banco vivo, sem escrita)
-- -----------------------------------------------------------------------------
-- PostgreSQL 15.8. Supabase self-hosted, database.agenciavolc.com.br.
--
-- M1. NAO EXISTE tabela/view de papel ou autorizacao em nenhum schema de
--     aplicacao. Busca por nome ~* 'role|perm|grant|acl|auth|admin|member'
--     devolveu apenas auth.oauth_* (4 tabelas do GoTrue). Autoridade de papel
--     hoje = coluna public.users.role (text, CHECK ADMIN|OPERATOR|VIEWER).
--
-- M2. public.get_current_user_role() e SECURITY DEFINER e o corpo e:
--       SELECT current_setting('app.current_user_role', true) INTO user_role;
--       RETURN COALESCE(user_role, 'VIEWER');
--     Ninguem no repositorio define 'app.current_user_role' (grep em src/,
--     server/, api/, backend/ => 0 ocorrencias). Sempre devolve 'VIEWER'.
--     Nao e portao. Tambem nao e consumida por codigo nenhum (0 ocorrencias).
--
-- M3. pg_default_acl do schema public concede arwdDxt em TODA TABELA NOVA para
--     anon, authenticated e service_role (dois donos: postgres e supabase_admin).
--     E concede X (EXECUTE) em TODA FUNCAO NOVA para os mesmos tres papeis.
--     Consequencia: qualquer objeto criado em public nasce aberto ao browser.
--     Por isso este arquivo REVOGA explicitamente cada funcao nova de anon —
--     "REVOKE ... FROM PUBLIC" NAO remove esses grants, que sao nominais.
--
-- M4. PGRST_DB_SCHEMAS=public,storage,graphql_public (/root/supabase/docker/.env).
--     Um schema fora dessa lista nao tem rota no PostgREST para NENHUM papel,
--     nem service_role.
--
-- M5. public.users tem 1 linha, role='ADMIN'. auth.users tem 1 linha.
--     JOIN por id  => 0 linhas.  JOIN por lower(email) => 1 linha.
--     ou seja: public.users.id NAO e o auth.users.id. O vinculo real e o EMAIL.
--     Toda a Frente 2 depende desse fato; ver v8_03 (policy de self).
--
-- M6. postgres: rolsuper=f, rolbypassrls=t, NAO e membro de supabase_admin.
--     public.users e propriedade de supabase_admin => v8_03/v8_04/v8_06 exigem
--     supabase_admin. ESTE ARQUIVO TAMBEM: ele faz REVOKE e COMMENT em
--     public.get_current_user_role(), que e propriedade de supabase_admin, e
--     COMMENT ON FUNCTION exige SER DONO — privilegio nao basta.
--
--     CORRIGIDO em 24/08/2026 apos medicao em producao: a versao anterior desta
--     nota dizia "roda como postgres", e aplicar assim aborta a transacao
--     inteira na ultima secao do arquivo, com
--     'must be owner of function public.get_current_user_role'. O rollback e
--     completo (a guarda BEGIN/COMMIT segura), mas a nota mandava a pessoa
--     tentar do jeito que nao funciona.
--     postgres tem REFERENCES e SELECT em auth.users (has_table_privilege=t),
--     entao a FK abaixo e criavel.
--
-- M7. service_role tem rolbypassrls=t. RLS NAO CONTEM os endpoints de
--     api/supabase/{query,insert,update,rpc}.js nem server/index.js:165-403,
--     que usam SUPABASE_SERVICE_ROLE_KEY sem checagem de autenticacao.
--     Isso e trabalho da Frente 1/3. Esta frente contem anon e authenticated.
--
-- -----------------------------------------------------------------------------
-- DECISAO ARQUITETURAL (item 1 do escopo): SCHEMA PRIVADO, nao tabela em public
-- -----------------------------------------------------------------------------
-- Escolhido: schema privado `app_auth`, sem rota REST, acessivel apenas por
-- funcoes SECURITY DEFINER com EXECUTE nominal.
--
-- Justificativa, ponto a ponto contra a alternativa "tabela em public com RLS":
--
--   a) FALHA FECHADA POR CONSTRUCAO. Por M3, uma tabela criada em public nasce
--      com arwdDxt para anon. A protecao dependeria de lembrar de revogar em
--      TODA migration futura. Em app_auth nao existe default ACL nenhum: o
--      objeto nasce inacessivel e so abre por GRANT explicito.
--
--   b) SEM SUPERFICIE REST. Por M4, app_auth nao esta em PGRST_DB_SCHEMAS.
--      api/supabase/query.js:34 faz supabase.from(<tabela do request>) com a
--      service key; com a tabela em public, "app_auth_user_roles" seria um nome
--      de tabela valido para esse endpoint aberto. Em app_auth, o PostgREST
--      devolve 404 de schema mesmo com a service key. O buraco da Frente 1/3
--      nao alcanca a fonte de papel.
--
--   c) service_role tem BYPASSRLS (M7). RLS em tabela public NAO protegeria a
--      fonte de papel contra a service key vazada; ausencia de rota, sim.
--
--   d) O portao vira uma ASSINATURA DE FUNCAO, nao um ACL de tabela: quem pode
--      conceder papel e quem pode ler papel sao decisoes declaradas em
--      GRANT EXECUTE, auditaveis em uma consulta.
--
-- Custo aceito: o backend nao le a tabela por REST; usa as RPCs em public
-- (volc_grant_role / volc_revoke_role / volc_is_admin), com EXECUTE so para
-- service_role. E o preco de nao ter uma tabela de papel exposta.
--
-- NAO APAGA DADO: public.users.role permanece intacta. Este arquivo apenas LE
-- public.users para semear app_auth.user_roles. A migracao/limpeza da coluna
-- legada e PROPOSTA (ver README), nao executada.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- --- Guarda de pre-condicao -------------------------------------------------
DO $guard$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION
      'v8_01 exige postgres ou supabase_admin (current_user = %)', current_user;
  END IF;
  IF to_regclass('auth.users') IS NULL THEN
    RAISE EXCEPTION 'v8_01 abortada: auth.users nao existe neste banco';
  END IF;
  IF to_regclass('public.users') IS NULL THEN
    RAISE EXCEPTION 'v8_01 abortada: public.users nao existe neste banco';
  END IF;
END
$guard$;

-- =============================================================================
-- 1. SCHEMA PRIVADO
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS app_auth;

COMMENT ON SCHEMA app_auth IS
  'Fonte de verdade de autorizacao do VOLC O.S. Fora de PGRST_DB_SCHEMAS: '
  'sem rota REST para nenhum papel, inclusive service_role. Acesso apenas por '
  'funcoes SECURITY DEFINER em public. Criado em v8_01 (Sprint 1A / Frente 2).';

-- Fecha o schema. PUBLIC primeiro, depois cada papel nominalmente (ver M3:
-- REVOKE FROM PUBLIC nao remove grant nominal).
REVOKE ALL ON SCHEMA app_auth FROM PUBLIC;
REVOKE ALL ON SCHEMA app_auth FROM anon;
REVOKE ALL ON SCHEMA app_auth FROM authenticated;
REVOKE ALL ON SCHEMA app_auth FROM service_role;

-- Default privileges do proprio schema: nada para os papeis do PostgREST,
-- para que objetos futuros em app_auth tambem nasçam fechados.
ALTER DEFAULT PRIVILEGES IN SCHEMA app_auth
  REVOKE ALL ON TABLES FROM anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA app_auth
  REVOKE ALL ON FUNCTIONS FROM anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA app_auth
  REVOKE ALL ON SEQUENCES FROM anon, authenticated, service_role;

-- postgres precisa de USAGE caso este arquivo seja aplicado como supabase_admin
-- (o guarda acima aceita os dois). Redundante se aplicado como postgres.
GRANT USAGE ON SCHEMA app_auth TO postgres;

-- =============================================================================
-- 2. TABELA DE AUTORIZACAO — ligada a auth.users.id
-- =============================================================================
-- Chave = auth.users.id, que e exatamente o que auth.uid() devolve dentro de
-- uma policy. NAO usa public.users.id: por M5 esse id nao casa com auth.users.
CREATE TABLE IF NOT EXISTS app_auth.user_roles (
  auth_user_id  uuid        PRIMARY KEY
                            REFERENCES auth.users(id) ON DELETE CASCADE,
  role          text        NOT NULL,
  granted_by    uuid        NULL REFERENCES auth.users(id) ON DELETE SET NULL,
  granted_at    timestamptz NOT NULL DEFAULT now(),
  revoked_at    timestamptz NULL,
  note          text        NULL,
  CONSTRAINT user_roles_role_check
    CHECK (role IN ('ADMIN', 'OPERATOR', 'VIEWER')),
  CONSTRAINT user_roles_revoked_after_granted
    CHECK (revoked_at IS NULL OR revoked_at >= granted_at),
  CONSTRAINT user_roles_note_len
    CHECK (note IS NULL OR length(note) <= 500)
);

COMMENT ON TABLE app_auth.user_roles IS
  'Papel administrativo por identidade do Supabase Auth. Autoridade unica de '
  'papel server-side. public.users.role permanece como dado legado de UI e NAO '
  'e consultada por nenhuma policy a partir de v8_02.';
COMMENT ON COLUMN app_auth.user_roles.auth_user_id IS
  'auth.users.id — o mesmo valor devolvido por auth.uid(). Ver M5 no cabecalho.';
COMMENT ON COLUMN app_auth.user_roles.revoked_at IS
  'Revogacao logica. Linha revogada nunca autoriza. Preserva historico.';

-- Indices (item 5 do escopo)
-- Consulta quente das policies: "existe ADMIN ativo com este auth_user_id?".
-- A PK ja resolve o lookup por usuario; este parcial serve a contagem de
-- admins ativos (guarda de ultimo admin em v8_03) sem varrer a tabela.
CREATE INDEX IF NOT EXISTS idx_user_roles_active_role
  ON app_auth.user_roles (role)
  WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_user_roles_granted_by
  ON app_auth.user_roles (granted_by)
  WHERE granted_by IS NOT NULL;

-- Cinto e suspensorio: mesmo sem rota REST, a tabela nega por padrao.
-- FORCE aplica a RLS tambem ao dono. Papeis com BYPASSRLS (postgres,
-- service_role, supabase_admin) ainda passam — por isso o schema fechado
-- e a defesa primaria, e a RLS e a secundaria.
ALTER TABLE app_auth.user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_auth.user_roles FORCE ROW LEVEL SECURITY;
-- Zero policies, deliberadamente: deny-all.

REVOKE ALL ON TABLE app_auth.user_roles FROM PUBLIC;
REVOKE ALL ON TABLE app_auth.user_roles FROM anon;
REVOKE ALL ON TABLE app_auth.user_roles FROM authenticated;
REVOKE ALL ON TABLE app_auth.user_roles FROM service_role;

-- =============================================================================
-- 3. TRILHA DE AUDITORIA DE PAPEL
-- =============================================================================
CREATE TABLE IF NOT EXISTS app_auth.user_role_audit (
  id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at    timestamptz NOT NULL DEFAULT now(),
  auth_user_id   uuid        NULL,
  legacy_user_id uuid        NULL,
  old_role       text        NULL,
  new_role       text        NULL,
  actor_db_role  text        NOT NULL,
  actor_auth_uid uuid        NULL,
  source         text        NOT NULL,
  CONSTRAINT user_role_audit_source_len CHECK (length(source) <= 200)
);

COMMENT ON TABLE app_auth.user_role_audit IS
  'Toda mudanca de papel — em app_auth.user_roles ou em public.users.role — '
  'deixa linha aqui. Serve para detectar tentativa de autopromocao e para '
  'reconstruir quem concedeu o que.';

CREATE INDEX IF NOT EXISTS idx_user_role_audit_user_time
  ON app_auth.user_role_audit (auth_user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_role_audit_time
  ON app_auth.user_role_audit (occurred_at DESC);

ALTER TABLE app_auth.user_role_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_auth.user_role_audit FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE app_auth.user_role_audit FROM PUBLIC;
REVOKE ALL ON TABLE app_auth.user_role_audit FROM anon;
REVOKE ALL ON TABLE app_auth.user_role_audit FROM authenticated;
REVOKE ALL ON TABLE app_auth.user_role_audit FROM service_role;

-- =============================================================================
-- 4. FUNCOES DE LEITURA DE PAPEL (portao)
-- =============================================================================
-- Todas: SECURITY DEFINER, STABLE, search_path travado em '' (nomes sempre
-- qualificados) para nao ser sequestravel por search_path do chamador.
-- Todas falham FECHADO: sem auth.uid() e sem claim de email => false.
-- NENHUMA delas le user_metadata / raw_user_meta_data. O JWT so fornece
-- identidade (sub/email); o papel vem do banco.

CREATE OR REPLACE FUNCTION public.volc_current_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM app_auth.user_roles r
    WHERE r.auth_user_id = (SELECT auth.uid())
      AND r.revoked_at IS NULL
      AND r.role = 'ADMIN'
  );
$$;

COMMENT ON FUNCTION public.volc_current_admin() IS
  'true se o sub do JWT corrente tem ADMIN ativo em app_auth.user_roles. '
  'Falha fechada: auth.uid() NULL => false. Nao le user_metadata.';

CREATE OR REPLACE FUNCTION public.volc_current_role()
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT r.role
  FROM app_auth.user_roles r
  WHERE r.auth_user_id = (SELECT auth.uid())
    AND r.revoked_at IS NULL;
$$;

COMMENT ON FUNCTION public.volc_current_role() IS
  'Papel do sub do JWT corrente, ou NULL se nao houver papel ativo. '
  'NULL significa "sem papel" — nunca assuma um padrao permissivo.';

-- Substitui a checagem de "usuario conhecido" que as policies do pautador
-- faziam com EXISTS(SELECT 1 FROM users u WHERE lower(u.email) = ...).
-- Mesma semantica, mas SECURITY DEFINER: deixa de exigir que `authenticated`
-- tenha SELECT em public.users (pre-requisito de v8_04).
CREATE OR REPLACE FUNCTION public.volc_current_user_known()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.users u
    WHERE u.id = (SELECT auth.uid())
       OR lower(u.email) = lower(((SELECT auth.jwt()) ->> 'email'))
  );
$$;

COMMENT ON FUNCTION public.volc_current_user_known() IS
  'true se o JWT corrente corresponde a uma linha de public.users por id OU '
  'por email (ver M5: os ids nao casam com auth.users). Nao concede ADMIN.';

-- Consulta de papel por sub arbitrario: superficie de servico, nunca do browser.
CREATE OR REPLACE FUNCTION public.volc_is_admin(p_auth_user_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM app_auth.user_roles r
    WHERE r.auth_user_id = p_auth_user_id
      AND p_auth_user_id IS NOT NULL
      AND r.revoked_at IS NULL
      AND r.role = 'ADMIN'
  );
$$;

COMMENT ON FUNCTION public.volc_is_admin(uuid) IS
  'Checagem de papel por sub. EXECUTE apenas para service_role: o backend '
  'valida o JWT, extrai o sub e pergunta aqui. Nao exposta ao browser.';

-- =============================================================================
-- 5. FUNCOES DE ESCRITA DE PAPEL (unico caminho suportado)
-- =============================================================================
CREATE OR REPLACE FUNCTION public.volc_grant_role(
  p_auth_user_id uuid,
  p_role         text,
  p_note         text DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_caller uuid := (SELECT auth.uid());
  v_old    text;
BEGIN
  IF p_auth_user_id IS NULL THEN
    RAISE EXCEPTION 'volc_grant_role: p_auth_user_id obrigatorio';
  END IF;
  IF p_role NOT IN ('ADMIN', 'OPERATOR', 'VIEWER') THEN
    RAISE EXCEPTION 'volc_grant_role: papel invalido %', p_role;
  END IF;

  -- Portao: admin autenticado, ou identidade de servico/DBA.
  -- Falha FECHADA: qualquer outro caminho levanta excecao.
  IF NOT (
    public.volc_current_admin()
    OR current_user IN ('service_role', 'postgres', 'supabase_admin')
  ) THEN
    INSERT INTO app_auth.user_role_audit
      (auth_user_id, new_role, actor_db_role, actor_auth_uid, source)
    VALUES
      (p_auth_user_id, p_role, current_user, v_caller,
       'volc_grant_role NEGADO — chamador sem ADMIN');
    RAISE EXCEPTION 'volc_grant_role: nao autorizado';
  END IF;

  -- Autopromocao: um chamador nao pode conceder papel a si mesmo pela UI.
  -- (Um ADMIN ja e ADMIN; a proibicao existe para fechar o caso em que o
  --  portao acima venha a ser afrouxado no futuro.)
  IF v_caller IS NOT NULL AND v_caller = p_auth_user_id
     AND current_user NOT IN ('service_role', 'postgres', 'supabase_admin') THEN
    INSERT INTO app_auth.user_role_audit
      (auth_user_id, new_role, actor_db_role, actor_auth_uid, source)
    VALUES
      (p_auth_user_id, p_role, current_user, v_caller,
       'volc_grant_role NEGADO — autopromocao');
    RAISE EXCEPTION 'volc_grant_role: concessao de papel a si mesmo bloqueada';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM auth.users a WHERE a.id = p_auth_user_id) THEN
    RAISE EXCEPTION 'volc_grant_role: % nao existe em auth.users', p_auth_user_id;
  END IF;

  SELECT r.role INTO v_old
  FROM app_auth.user_roles r
  WHERE r.auth_user_id = p_auth_user_id AND r.revoked_at IS NULL;

  INSERT INTO app_auth.user_roles
    (auth_user_id, role, granted_by, granted_at, revoked_at, note)
  VALUES
    (p_auth_user_id, p_role, v_caller, now(), NULL, p_note)
  ON CONFLICT (auth_user_id) DO UPDATE
    SET role       = EXCLUDED.role,
        granted_by = EXCLUDED.granted_by,
        granted_at = now(),
        revoked_at = NULL,
        note       = EXCLUDED.note;

  INSERT INTO app_auth.user_role_audit
    (auth_user_id, old_role, new_role, actor_db_role, actor_auth_uid, source)
  VALUES
    (p_auth_user_id, v_old, p_role, current_user, v_caller, 'volc_grant_role');
END;
$$;

COMMENT ON FUNCTION public.volc_grant_role(uuid, text, text) IS
  'Unico caminho suportado para conceder papel. EXECUTE so para service_role. '
  'Bloqueia autopromocao e audita concessao e negativa.';

-- ─────────────────────────────────────────────────────────────────────────────
-- volc_role_of — a ÚNICA porta pela qual o backend descobre o papel de alguém.
--
-- Por que ela existe, e por que não é uma tabela REST: `app_auth.user_roles`
-- tem RLS forçada e ALL revogado de TODOS os papéis do Data API, inclusive
-- `service_role`. Isso é deliberado — expor a tabela de papéis como recurso
-- REST genérico devolveria ao Data API exatamente o poder que o Sprint 1A tirou
-- dos proxies. O backend pergunta "qual o papel deste sub?" e recebe uma
-- string; não navega, não filtra, não lista.
--
-- Propósito único, parâmetro tipado, e EXECUTE só para `service_role` (ver o
-- bloco de grants no fim do arquivo). `anon` e `authenticated` não a alcançam:
-- quem tem sessão usa `volc_current_role()`, que lê o próprio `auth.uid()` e
-- não aceita sub de terceiro.
--
-- Devolve '' (string vazia) quando não há papel ativo. NULL seria pior: em
-- PostgREST um NULL vira `null` no JSON e o cliente distraído o trata como
-- ausência de resposta, não como ausência de papel.
CREATE OR REPLACE FUNCTION public.volc_role_of(p_auth_user_id uuid)
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT COALESCE(
    (SELECT r.role
       FROM app_auth.user_roles r
      WHERE r.auth_user_id = p_auth_user_id
        AND p_auth_user_id IS NOT NULL
        AND r.revoked_at IS NULL
      ORDER BY r.granted_at DESC
      LIMIT 1),
    ''
  );
$$;

COMMENT ON FUNCTION public.volc_role_of(uuid) IS
  'Papel ativo de um sub. EXECUTE apenas para service_role. Consumida por '
  'backend/app/seguranca/identidade.py::_papel_do_sub. Revogacao vale no ato '
  'porque a consulta filtra revoked_at IS NULL a cada chamada.';

CREATE OR REPLACE FUNCTION public.volc_revoke_role(p_auth_user_id uuid)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_caller       uuid := (SELECT auth.uid());
  v_old          text;
  v_admins_ativos int;
BEGIN
  IF NOT (
    public.volc_current_admin()
    OR current_user IN ('service_role', 'postgres', 'supabase_admin')
  ) THEN
    RAISE EXCEPTION 'volc_revoke_role: nao autorizado';
  END IF;

  SELECT r.role INTO v_old
  FROM app_auth.user_roles r
  WHERE r.auth_user_id = p_auth_user_id AND r.revoked_at IS NULL;

  IF v_old IS NULL THEN
    RETURN;  -- idempotente
  END IF;

  IF v_old = 'ADMIN' THEN
    SELECT count(*) INTO v_admins_ativos
    FROM app_auth.user_roles r
    WHERE r.role = 'ADMIN' AND r.revoked_at IS NULL;
    IF v_admins_ativos <= 1 THEN
      RAISE EXCEPTION
        'volc_revoke_role: revogar o ultimo ADMIN ativo travaria o sistema';
    END IF;
  END IF;

  UPDATE app_auth.user_roles
     SET revoked_at = now()
   WHERE auth_user_id = p_auth_user_id AND revoked_at IS NULL;

  INSERT INTO app_auth.user_role_audit
    (auth_user_id, old_role, new_role, actor_db_role, actor_auth_uid, source)
  VALUES
    (p_auth_user_id, v_old, NULL, current_user, v_caller, 'volc_revoke_role');
END;
$$;

COMMENT ON FUNCTION public.volc_revoke_role(uuid) IS
  'Revogacao logica de papel. Recusa revogar o ultimo ADMIN ativo.';

-- =============================================================================
-- 6. FUNCOES DE GATILHO (criadas aqui; os triggers sao criados em v8_03,
--    que roda como supabase_admin por causa do dono de public.users)
-- =============================================================================
CREATE OR REPLACE FUNCTION app_auth.tg_users_guard_privileged_columns()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_caller uuid := (SELECT auth.uid());
BEGIN
  IF NEW.role IS DISTINCT FROM OLD.role
     OR NEW.commission_percentage IS DISTINCT FROM OLD.commission_percentage THEN

    IF NOT (
      public.volc_current_admin()
      OR current_user IN ('service_role', 'postgres', 'supabase_admin')
    ) THEN
      INSERT INTO app_auth.user_role_audit
        (legacy_user_id, old_role, new_role, actor_db_role, actor_auth_uid, source)
      VALUES
        (OLD.id, OLD.role, NEW.role, current_user, v_caller,
         'public.users UPDATE NEGADO — coluna privilegiada sem ADMIN');
      RAISE EXCEPTION
        'public.users: alterar role/commission_percentage exige ADMIN';
    END IF;

    INSERT INTO app_auth.user_role_audit
      (legacy_user_id, old_role, new_role, actor_db_role, actor_auth_uid, source)
    VALUES
      (OLD.id, OLD.role, NEW.role, current_user, v_caller,
       'public.users UPDATE de coluna privilegiada');
  END IF;

  RETURN NEW;
END;
$$;

COMMENT ON FUNCTION app_auth.tg_users_guard_privileged_columns() IS
  'RLS e por linha, nao por coluna, e WITH CHECK nao enxerga OLD. Este gatilho '
  'e o que impede um authenticated comum de virar ADMIN editando a propria '
  'linha (autopromocao). Tambem audita toda troca de papel legado.';

CREATE OR REPLACE FUNCTION app_auth.tg_users_block_last_admin_delete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_restantes int;
BEGIN
  IF OLD.role = 'ADMIN' THEN
    SELECT count(*) INTO v_restantes
    FROM public.users u
    WHERE u.role = 'ADMIN' AND u.id <> OLD.id;
    IF v_restantes = 0 THEN
      RAISE EXCEPTION
        'public.users: apagar o ultimo ADMIN travaria o sistema';
    END IF;
  END IF;
  RETURN OLD;
END;
$$;

COMMENT ON FUNCTION app_auth.tg_users_block_last_admin_delete() IS
  'Impede DELETE do ultimo ADMIN. src/services/usersService.ts:277 apaga '
  'direto na tabela; a regra equivalente que existe no cliente nao e portao.';

-- =============================================================================
-- 7. GRANTS DAS FUNCOES — nominais, porque pg_default_acl ja concedeu X a anon
-- =============================================================================
DO $grants$
DECLARE
  f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'public.volc_current_admin()',
    'public.volc_current_role()',
    'public.volc_current_user_known()',
    'public.volc_is_admin(uuid)',
    'public.volc_grant_role(uuid, text, text)',
    'public.volc_revoke_role(uuid)'
  ,
    'public.volc_role_of(uuid)'] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM anon', f);
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM authenticated', f);
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM service_role', f);
  END LOOP;
END
$grants$;

-- Portao do browser: so as tres leituras do proprio JWT.
GRANT EXECUTE ON FUNCTION public.volc_current_admin()      TO authenticated;
GRANT EXECUTE ON FUNCTION public.volc_current_role()       TO authenticated;
GRANT EXECUTE ON FUNCTION public.volc_current_user_known() TO authenticated;

-- Identidade de servico: leitura por sub + escrita de papel.
GRANT EXECUTE ON FUNCTION public.volc_current_admin()                TO service_role;
GRANT EXECUTE ON FUNCTION public.volc_current_role()                 TO service_role;
GRANT EXECUTE ON FUNCTION public.volc_current_user_known()           TO service_role;
GRANT EXECUTE ON FUNCTION public.volc_is_admin(uuid)                 TO service_role;
GRANT EXECUTE ON FUNCTION public.volc_role_of(uuid)                  TO service_role;
GRANT EXECUTE ON FUNCTION public.volc_grant_role(uuid, text, text)   TO service_role;
GRANT EXECUTE ON FUNCTION public.volc_revoke_role(uuid)              TO service_role;

-- anon: nada. Nem sequer descobrir o proprio papel — anon nao tem papel.
-- (as funcoes de gatilho ficam em app_auth e nao recebem EXECUTE de ninguem;
--  o disparo de trigger nao consulta privilegio de EXECUTE.)

-- =============================================================================
-- 8. APOSENTA O PORTAO FALSO
-- =============================================================================
-- M2: public.get_current_user_role() sempre devolve 'VIEWER' e nao e chamada
-- por codigo nenhum. NAO e removida (poderia haver consumidor fora do repo:
-- n8n, SQL ad hoc). E fechada e marcada.
DO $legacy$
BEGIN
  IF to_regprocedure('public.get_current_user_role()') IS NOT NULL THEN
    EXECUTE 'REVOKE ALL ON FUNCTION public.get_current_user_role() FROM PUBLIC';
    EXECUTE 'REVOKE ALL ON FUNCTION public.get_current_user_role() FROM anon';
    EXECUTE 'REVOKE ALL ON FUNCTION public.get_current_user_role() FROM authenticated';
    EXECUTE 'COMMENT ON FUNCTION public.get_current_user_role() IS '
         || quote_literal(
              'DEPRECADA (v8_01). Le current_setting(''app.current_user_role''), '
           || 'que ninguem define: sempre devolve VIEWER. Nunca foi portao. '
           || 'Substituida por public.volc_current_admin() / '
           || 'public.volc_current_role(). Mantida sem EXECUTE para anon e '
           || 'authenticated ate confirmar que nenhum consumidor externo '
           || '(n8n, SQL ad hoc) a chama.');
  END IF;
END
$legacy$;

-- =============================================================================
-- 9. SEMEADURA A PARTIR DO ESTADO LEGADO — nao destrutiva
-- =============================================================================
-- Ponte pelo EMAIL, nao pelo id (M5: JOIN por id devolve 0 linhas).
-- CTE para que a auditoria registre SO as linhas de fato inseridas — o arquivo
-- inteiro e idempotente e pode ser reaplicado sem inflar a trilha.
WITH semeadas AS (
  INSERT INTO app_auth.user_roles (auth_user_id, role, granted_at, note)
  SELECT au.id,
         pu.role,
         now(),
         'seed v8_01 a partir de public.users, casado por lower(email)'
  FROM auth.users au
  JOIN public.users pu ON lower(pu.email) = lower(au.email)
  WHERE pu.role IN ('ADMIN', 'OPERATOR', 'VIEWER')
  ON CONFLICT (auth_user_id) DO NOTHING
  RETURNING auth_user_id, role
)
INSERT INTO app_auth.user_role_audit
  (auth_user_id, old_role, new_role, actor_db_role, source)
SELECT s.auth_user_id, NULL, s.role, current_user, 'seed v8_01'
FROM semeadas s;

-- Falha FECHADA: sem ADMIN semeado, v8_03 trancaria todo mundo para fora.
-- Abortar aqui deixa o banco exatamente como estava.
DO $assert$
DECLARE
  v_admins  int;
  v_orfaos  int;
BEGIN
  SELECT count(*) INTO v_admins
  FROM app_auth.user_roles
  WHERE role = 'ADMIN' AND revoked_at IS NULL;

  IF v_admins = 0 THEN
    RAISE EXCEPTION
      'v8_01 ABORTADA: nenhum ADMIN ativo em app_auth.user_roles apos a '
      'semeadura. Aplicar v8_03 nessa condicao trancaria todos os usuarios '
      'para fora. Verifique o casamento por email entre public.users e '
      'auth.users antes de repetir.';
  END IF;

  SELECT count(*) INTO v_orfaos
  FROM public.users pu
  WHERE NOT EXISTS (
    SELECT 1 FROM auth.users au WHERE lower(au.email) = lower(pu.email)
  );

  RAISE NOTICE 'v8_01: % ADMIN(s) ativo(s) em app_auth.user_roles', v_admins;
  RAISE NOTICE 'v8_01: % linha(s) de public.users sem par em auth.users '
               '(nao recebem papel; entram pelo fluxo de criacao)', v_orfaos;
END
$assert$;

COMMIT;

-- =============================================================================
-- VERIFICACAO POS-APLICACAO (somente leitura)
-- =============================================================================
-- SELECT auth_user_id, role, granted_at, revoked_at FROM app_auth.user_roles;
-- SELECT has_schema_privilege('anon','app_auth','USAGE')          AS anon_usage_deve_ser_f,
--        has_schema_privilege('authenticated','app_auth','USAGE') AS authd_usage_deve_ser_f,
--        has_schema_privilege('service_role','app_auth','USAGE')  AS svc_usage_deve_ser_f;
-- SELECT p.proname,
--        has_function_privilege('anon', p.oid, 'EXECUTE') AS anon_deve_ser_f
--   FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--  WHERE n.nspname = 'public' AND p.proname LIKE 'volc\_%';
