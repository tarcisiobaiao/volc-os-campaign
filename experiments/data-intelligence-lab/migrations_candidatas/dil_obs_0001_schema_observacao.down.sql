-- =============================================================================
-- dil_obs_0001 — ROLLBACK de dil_obs_0001_schema_observacao.sql
-- MIGRATION CANDIDATA. NÃO APLICADA EM NENHUM BANCO OPERACIONAL.
-- ⚠️ DESTRÓI o histórico append-only inteiro (DROP não dispara os triggers de append-only).
--    Num banco com dado real, exportar dil_obs.* antes. Idempotente: rodar duas vezes não falha.
-- R1-F21: NÃO há CASCADE cego. Se algum objeto FORA do schema dil_obs depende dele (view, FK,
--    views de qualidade dil_qualidade.*), o rollback PARA e lista os dependentes; remova-os antes.
--    Limite: dependência escondida em corpo de função plpgsql não é rastreada pelo catálogo.
-- Papéis: removidos só se não restar dependência em OUTRO banco do cluster; senão ficam (NOTICE).
-- Só superusuário (R2-G1, mesma regra do up).
-- =============================================================================

BEGIN;

DO $$
DECLARE v_dependentes text;
BEGIN
  IF to_regnamespace('dil_obs') IS NULL THEN
    RETURN;
  END IF;
  SELECT string_agg(DISTINCT pg_catalog.pg_describe_object(d.classid, d.objid, d.objsubid), '; ')
    INTO v_dependentes
    FROM pg_catalog.pg_depend d
   WHERE d.deptype = 'n'
     AND (d.refclassid, d.refobjid) IN (
           SELECT 'pg_catalog.pg_class'::regclass, c.oid FROM pg_catalog.pg_class c WHERE c.relnamespace = 'dil_obs'::regnamespace
           UNION ALL SELECT 'pg_catalog.pg_proc'::regclass, f.oid FROM pg_catalog.pg_proc f WHERE f.pronamespace = 'dil_obs'::regnamespace
           UNION ALL SELECT 'pg_catalog.pg_type'::regclass, t.oid FROM pg_catalog.pg_type t WHERE t.typnamespace = 'dil_obs'::regnamespace)
     -- schema do objeto dependente (sub-objetos — regra de view, trigger, policy, default — pelo da tabela);
     -- tipo de dependente desconhecido conta como externo (conservador)
     AND CASE d.classid
           WHEN 'pg_catalog.pg_class'::regclass THEN (SELECT c.relnamespace FROM pg_catalog.pg_class c WHERE c.oid = d.objid)
           WHEN 'pg_catalog.pg_rewrite'::regclass THEN (SELECT c.relnamespace FROM pg_catalog.pg_rewrite w
                                                         JOIN pg_catalog.pg_class c ON c.oid = w.ev_class WHERE w.oid = d.objid)
           WHEN 'pg_catalog.pg_trigger'::regclass THEN (SELECT c.relnamespace FROM pg_catalog.pg_trigger g
                                                         JOIN pg_catalog.pg_class c ON c.oid = g.tgrelid WHERE g.oid = d.objid)
           WHEN 'pg_catalog.pg_policy'::regclass THEN (SELECT c.relnamespace FROM pg_catalog.pg_policy y
                                                        JOIN pg_catalog.pg_class c ON c.oid = y.polrelid WHERE y.oid = d.objid)
           WHEN 'pg_catalog.pg_attrdef'::regclass THEN (SELECT c.relnamespace FROM pg_catalog.pg_attrdef a
                                                         JOIN pg_catalog.pg_class c ON c.oid = a.adrelid WHERE a.oid = d.objid)
           WHEN 'pg_catalog.pg_constraint'::regclass THEN (SELECT k.connamespace FROM pg_catalog.pg_constraint k WHERE k.oid = d.objid)
           WHEN 'pg_catalog.pg_proc'::regclass THEN (SELECT f.pronamespace FROM pg_catalog.pg_proc f WHERE f.oid = d.objid)
           WHEN 'pg_catalog.pg_type'::regclass THEN (SELECT t.typnamespace FROM pg_catalog.pg_type t WHERE t.oid = d.objid)
         END IS DISTINCT FROM 'dil_obs'::regnamespace;
  IF v_dependentes IS NOT NULL THEN
    RAISE EXCEPTION 'dil_obs_0001.down: objetos fora de dil_obs dependem do schema: %', v_dependentes
      USING ERRCODE = 'dependent_objects_still_exist',
            HINT = 'Remova ou migre esses objetos (ex.: rollback de dq_02_views_dil_obs) e rode o down de novo.';
  END IF;
END $$;

-- R2-G1: SÓ SUPERUSUÁRIO aplica ou desfaz. Quem tem ADMIN OPTION em dil_obs_dono — inclusive o CREATEROLE
-- que criou os papéis, que no PostgreSQL 16 recebe essa opção automaticamente — pode se conceder o papel a
-- qualquer momento e desligar o append-only (DISABLE TRIGGER, TRUNCATE). Por isso papéis e schema não nascem de
-- não-superusuário, e a membresia temporária da R1 deixou de existir. No Supabase self-hosted: supabase_admin.
DO $$
BEGIN
  IF NOT (SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = current_user) THEN
    RAISE EXCEPTION 'dil_obs: aplique como superusuário (% não é superusuário)', current_user
      USING ERRCODE = 'insufficient_privilege',
            HINT = 'No Supabase self-hosted, como supabase_admin. Quem administra dil_obs_dono pode desligar o append-only.';
  END IF;
END $$;

-- sem CASCADE externo: só o que é do próprio schema (a checagem acima garantiu que não há dependente fora)
DROP SCHEMA IF EXISTS dil_obs CASCADE;

DO $$
DECLARE r text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'dil_obs_dono') THEN
    -- remove default ACL e o que sobrar do dono NESTE banco (o papel é dedicado a este schema)
    EXECUTE 'DROP OWNED BY dil_obs_dono';
  END IF;
  FOREACH r IN ARRAY ARRAY['dil_obs_escritor', 'dil_obs_leitor', 'dil_obs_dono'] LOOP
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = r) THEN
      BEGIN
        EXECUTE format('DROP ROLE %I', r);
      EXCEPTION WHEN dependent_objects_still_exist THEN
        RAISE NOTICE 'papel % mantido: ainda há dependências em outro banco do cluster', r;
      END;
    END IF;
  END LOOP;
END $$;


COMMIT;
