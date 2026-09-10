-- New render attempts preserve the approved strategic snapshot and old media.
-- No grants/RLS/approval rows are changed. Existing requests remain 'original'.
begin;
set local lock_timeout = '5s';
alter table public.criativo_agente_peca_job
  add column if not exists geracao_ref text not null default 'original';
alter table public.criativo_agente_peca_job
  add column if not exists plano_sha256 text;
alter table public.criativo_agente_peca_job
  drop constraint if exists criativo_agente_peca_job_plano_ck;
alter table public.criativo_agente_peca_job
  add constraint criativo_agente_peca_job_plano_ck
  check (plano_sha256 is null or plano_sha256 ~ '^[a-f0-9]{64}$');
alter table public.criativo_agente_peca_job
  drop constraint if exists criativo_agente_peca_job_geracao_ck;
alter table public.criativo_agente_peca_job
  add constraint criativo_agente_peca_job_geracao_ck
  check (geracao_ref = 'original' or geracao_ref ~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$');
-- Replace the uniqueness atomically; duplicate delivery of one version remains
-- impossible. The original unique constraint prevented ALL explicit re-renders.
alter table public.criativo_agente_peca_job
  drop constraint if exists criativo_agente_peca_job_unica;
alter table public.criativo_agente_peca_job
  add constraint criativo_agente_peca_job_unica unique (run_ref, creative_ref, geracao_ref);
comment on column public.criativo_agente_peca_job.geracao_ref is
  'Explicit render version. Retrying keeps it; generating again uses a new UUID. Original content approvals are not rewritten.';
notify pgrst, 'reload schema';
commit;
