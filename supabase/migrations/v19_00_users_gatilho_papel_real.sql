-- =============================================================================
-- v19_00 — Gatilho de public.users: reconhecer o papel REAL de quem chama
-- MISSÃO W4 (15/10/2026). ARQUIVO. NÃO APLICADO. Pré-requisito da v8_03.
-- =============================================================================
-- APLICAR COMO: supabase_admin (dono da função, v8_01).
--
-- DEFEITO ACHADO NO ENSAIO (base = schema de produção de 15/10):
--   app_auth.tg_users_guard_privileged_columns() é SECURITY DEFINER, dono
--   supabase_admin. Dentro dela current_user é SEMPRE supabase_admin, então o
--   ramo `current_user IN ('service_role','postgres','supabase_admin')` é sempre
--   verdadeiro e o gatilho nunca barra nada. Medido: um authenticated OPERATOR
--   rodou `UPDATE users SET role='ADMIN'` na própria linha e passou (UPDATE 1).
--   A v8_03 liga esse gatilho contando com ele para impedir autopromoção —
--   sem esta correção, a RLS da v8_03 deixa o operador se promover.
--
-- CORREÇÃO: o papel efetivo do chamador vem de current_setting('role') — o
-- SET ROLE que o PostgREST faz (anon/authenticated/service_role) — que um
-- SECURITY DEFINER não altera. Sessão direta sem SET ROLE ('none') cai em
-- session_user (postgres/supabase_admin em psql). Corpo, assinatura,
-- search_path e dono preservados; só a decisão e o actor_db_role da auditoria
-- mudam. O INSERT de auditoria no ramo negado saiu: ele vinha antes de um
-- RAISE e era desfeito junto com a transação — nunca gravou nada. Rollback: v19_99 devolve o corpo original byte a byte.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
  IF NOT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
    RAISE EXCEPTION 'v19_00 exige superusuário (supabase_admin). current_user = %', current_user;
  END IF;
  IF to_regprocedure('app_auth.tg_users_guard_privileged_columns()') IS NULL THEN
    RAISE EXCEPTION 'v19_00 abortada: função de v8_01 ausente';
  END IF;
END
$guard$;

CREATE OR REPLACE FUNCTION app_auth.tg_users_guard_privileged_columns()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
  v_caller uuid := (SELECT auth.uid());
  -- SECURITY DEFINER troca current_user pelo dono; o SET ROLE do chamador fica
  -- em current_setting('role'). 'none' = sessão direta, sem SET ROLE.
  v_papel  text := coalesce(nullif(current_setting('role', true), 'none'), session_user);
BEGIN
  IF NEW.role IS DISTINCT FROM OLD.role
     OR NEW.commission_percentage IS DISTINCT FROM OLD.commission_percentage THEN

    IF NOT (
      public.volc_current_admin()
      OR v_papel IN ('service_role', 'postgres', 'supabase_admin')
    ) THEN
      RAISE EXCEPTION
        'public.users: alterar role/commission_percentage exige ADMIN';
    END IF;

    INSERT INTO app_auth.user_role_audit
      (legacy_user_id, old_role, new_role, actor_db_role, actor_auth_uid, source)
    VALUES
      (OLD.id, OLD.role, NEW.role, v_papel, v_caller,
       'public.users UPDATE de coluna privilegiada');
  END IF;

  RETURN NEW;
END;
$function$;

COMMIT;
