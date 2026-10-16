-- SOMENTE PARA O POSTGRESQL DESCARTÁVEL DOS TESTES (thread G). NUNCA aplicar em produção.
--
-- Os demais arquivos desta pasta são CÓPIAS BYTE A BYTE do DDL real (o teste
-- test_qualidade_pg_views.py::test_ddl_base_igual_a_ref confere com `git show` quando a ref existe):
--   v21_01_google_ads_coleta_canonica.sql        = 043c77f545ae:supabase/migrations/v21_01_google_ads_coleta_canonica.sql
--   v21_02_google_ads_hash_no_servidor.sql       = 043c77f545ae:supabase/migrations/v21_02_google_ads_hash_no_servidor.sql
--   v21_03_google_ads_finalizacao_run.sql        = 043c77f545ae:supabase/migrations/v21_03_google_ads_finalizacao_run.sql
--   20261015163704_joinads_collection_canonical.sql
--       = 192bc0652594 (wip/historico-joinads-20261015):supabase/migrations/20261015163704_joinads_collection_canonical.sql
--   20261015170000_joinads_latest_collector_version_guard.sql
--       = 192bc0652594:supabase/migrations/20261015170000_joinads_latest_collector_version_guard.sql
--
-- Este prelúdio só cria o que o Supabase já traz: schema `extensions` com pgcrypto (o DDL real chama
-- extensions.digest) e uma `raw_events` MÍNIMA. O DDL real de raw_events NÃO está versionado em ref
-- alguma (risco R8 do inventário); as colunas abaixo são as que o recibo L3/L4 mostra em produção
-- (ts, event_name, payload jsonb; índice raw_events_dedup(sid, pid, event_name, ts_sec)). As views
-- de qualidade usam só ts, event_name e payload.
-- Papéis anon/authenticated/service_role são criados pela fixture `cluster_pg` (conftest da thread A).

CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;

CREATE TABLE public.raw_events (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  sid         text NOT NULL,
  pid         text NOT NULL,
  event_name  text NOT NULL,
  ts          timestamptz NOT NULL,
  ts_sec      bigint NOT NULL,
  payload     jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE UNIQUE INDEX raw_events_dedup ON public.raw_events (sid, pid, event_name, ts_sec);
REVOKE ALL ON public.raw_events FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON public.raw_events TO service_role;
