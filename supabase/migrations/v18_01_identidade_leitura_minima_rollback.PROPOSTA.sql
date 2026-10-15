-- =============================================================================
-- v18_01_rollback.sql — desfaz v18_01_identidade_leitura_minima.sql
-- Reversível por inteiro: a v18_01 não cria dado, só papéis, grants e policies.
-- Idempotente: rodar sem a v18_01 aplicada é no-op.
-- =============================================================================
BEGIN;

DO $$
DECLARE r record;
BEGIN
  IF to_regrole('volc_leitura') IS NULL THEN
    RAISE NOTICE 'v18_01_rollback: volc_leitura ausente — nada a desfazer';
    RETURN;
  END IF;

  -- Recusa se alguém transformou o papel de leitura em DONO de algo.
  IF EXISTS (SELECT 1 FROM pg_class WHERE relowner IN ('volc_leitura'::regrole::oid, coalesce(to_regrole('volc_leitura_agente')::oid, 0::oid)))
  OR EXISTS (SELECT 1 FROM pg_proc  WHERE proowner IN ('volc_leitura'::regrole::oid, coalesce(to_regrole('volc_leitura_agente')::oid, 0::oid))) THEN
    RAISE EXCEPTION 'v18_01_rollback: o papel de leitura é dono de objeto — investigue antes de remover';
  END IF;

  -- Recusa se alguém além da identidade de leitura entrou no grupo: remover o
  -- papel derrubaria a membership alheia em silêncio.
  IF EXISTS (SELECT 1 FROM pg_auth_members am
              WHERE am.roleid = 'volc_leitura'::regrole
                AND am.member <> coalesce(to_regrole('volc_leitura_agente')::oid, 0::oid)) THEN
    RAISE EXCEPTION 'v18_01_rollback: volc_leitura tem membros além de volc_leitura_agente — investigue antes de remover';
  END IF;

  -- Só a policy que a v18_01 criou: mesmo nome, SÓ para volc_leitura, USING (true).
  FOR r IN SELECT n.nspname, c.relname FROM pg_policy p
             JOIN pg_class c ON c.oid = p.polrelid JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE p.polname = 'volc_leitura_le'
              AND p.polroles = ARRAY['volc_leitura'::regrole::oid]
              AND p.polcmd = 'r'
              AND pg_get_expr(p.polqual, p.polrelid) = 'true' LOOP
    EXECUTE format('DROP POLICY volc_leitura_le ON %I.%I', r.nspname, r.relname);
  END LOOP;
END $$;

-- Revogação explícita, não DROP OWNED: na imagem Supabase o papel que aplica
-- (postgres) NÃO é superusuário, e DROP OWNED BY de outro papel falha com
-- "permission denied to drop objects" (medido no lab 15.8.1.085 em 15/10/2026;
-- o lab PG16 com postgres superusuário escondia isso).
DO $$
DECLARE r record;
BEGIN
  IF to_regrole('volc_leitura') IS NULL THEN RETURN; END IF;
  FOR r IN SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname NOT IN ('pg_catalog','information_schema')
              AND c.relkind IN ('r','p','v','m','f')
              AND has_table_privilege('volc_leitura', c.oid, 'SELECT')
              AND EXISTS (SELECT 1 FROM aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a
                           WHERE a.grantee = 'volc_leitura'::regrole) LOOP
    EXECUTE format('REVOKE ALL ON %I.%I FROM volc_leitura', r.nspname, r.relname);
  END LOOP;
  REVOKE ALL ON SCHEMA public FROM volc_leitura;
  REVOKE CONNECT ON DATABASE postgres FROM volc_leitura;
  IF to_regrole('volc_leitura_agente') IS NOT NULL THEN
    EXECUTE 'DROP ROLE volc_leitura_agente';
  END IF;
  EXECUTE 'DROP ROLE volc_leitura';
END $$;

COMMIT;
