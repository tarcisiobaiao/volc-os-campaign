-- base_prod_prereqs.sql — preparo da imagem supabase/postgres:15.8.1.085 antes de restaurar
-- o dump --schema-only de produção (lab.sh base-prod). Origem: ensaio do W4, 15/10/2026.
-- 1. tira o default ACL de public que a IMAGEM traz: sem isso toda tabela restaurada herda
--    arwdDxt para anon da imagem e o pg_dump não emite REVOKE (compara com o default
--    embutido) — a base pareceria produção sem ser. O dump repõe o default ACL real no fim.
-- 2. auth.uid()/auth.jwt() como o GoTrue instala (leem request.jwt.claims);
-- 3. extensões e schemas fora de public/app_auth que o dump referencia;
-- 4. stub do gatilho guard_archived_draft (corpo real fora do dump).
ALTER DEFAULT PRIVILEGES FOR ROLE postgres, supabase_admin IN SCHEMA public
  REVOKE ALL ON TABLES FROM postgres, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres, supabase_admin IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM postgres, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres, supabase_admin IN SCHEMA public
  REVOKE ALL ON FUNCTIONS FROM postgres, anon, authenticated, service_role;
-- auth.uid() como o GoTrue instala (lê request.jwt.claims, que é o que o
-- PostgREST atual define); a imagem crua só lê request.jwt.claim.sub.
create or replace function auth.uid() returns uuid language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claim.sub', true), ''),
                  (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'))::uuid $$;
create or replace function auth.jwt() returns jsonb language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb) $$;
grant execute on function auth.jwt() to anon, authenticated, service_role, postgres;
create extension if not exists pg_net;
create extension if not exists pg_cron;
create schema if not exists meta_draft_private authorization postgres;
create schema if not exists meta_media_private authorization postgres;
-- Stub: corpo real fora do dump; existe só para o gatilho ser criado igual.
create or replace function meta_draft_private.guard_archived_draft() returns trigger
  language plpgsql as $$ begin return new; end $$;
alter function meta_draft_private.guard_archived_draft() owner to postgres;
