-- db/suites/v19_incidente_anon_semente.sql — semente sintética do ensaio W4 (incidente anon).
-- Aplicada por lab.sh recriar-prod via LAB_SEMENTE, como supabase_admin, sobre a base de produção.
-- Só @example.invalid; ids de public.users NÃO casam com auth.users (v8 M3/M5), como em produção.
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at)
values ('00000000-0000-0000-0000-000000000000','a0000000-0000-4000-8000-00000000000a','authenticated','authenticated','admin@example.invalid', now(), now()),
       ('00000000-0000-0000-0000-000000000000','a0000000-0000-4000-8000-00000000000b','authenticated','authenticated','operador@example.invalid', now(), now());
insert into public.users (id, name, email, role, password_hash, token_primeiro_acesso, needs_password_change)
values ('b0000000-0000-4000-8000-00000000000a','Admin Sintético','admin@example.invalid','ADMIN','HASH-SINTETICO-A','TOKEN-SINTETICO-A', false),
       ('b0000000-0000-4000-8000-00000000000b','Operador Sintético','operador@example.invalid','OPERATOR','HASH-SINTETICO-B','TOKEN-SINTETICO-B', false);
insert into app_auth.user_roles (auth_user_id, role, note)
values ('a0000000-0000-4000-8000-00000000000a', 'ADMIN', 'semente W4');
insert into public.system_settings (key, value) values ('w4_sintetico', 'x');
insert into public.projects (id, project_name, main_url, start_date, status)
  values (990001, 'Projeto Sintético', 'https://exemplo.invalid', current_date, 'Active');
insert into public.campaigns (id, project_id, campaign_name, start_date, status)
  values (990001, 990001, 'Campanha Sintética', current_date, 'Active');
insert into public.user_projects (id, user_id, project_id)
  values (990001, 'b0000000-0000-4000-8000-00000000000b', 990001);
