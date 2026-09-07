-- Assistente de Criativos Meta: estado estratégico e decisões, sem mídia e sem Ads mutate.
begin;

create table if not exists public.criativo_agente_operacao (
    project_ref        text primary key,
    owner_id           uuid not null,
    status             text not null default 'RUNNING',
    input              jsonb not null,
    latest_run_ref     text,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    constraint criativo_agente_operacao_ref_ck
        check (project_ref ~ '^crproj_[a-f0-9]{24}$'),
    constraint criativo_agente_operacao_status_ck
        check (status in ('RUNNING','READY_FOR_REVIEW','FAILED','ARCHIVED')),
    constraint criativo_agente_operacao_input_object_ck
        check (jsonb_typeof(input) = 'object')
);

create table if not exists public.criativo_agente_run (
    run_ref             text primary key,
    project_ref         text not null references public.criativo_agente_operacao(project_ref),
    owner_id            uuid not null,
    status              text not null default 'RUNNING',
    phase               text not null,
    input               jsonb not null,
    output              jsonb,
    model               text,
    tentativas          integer,
    request_sha256      text,
    knowledge_sha256    text,
    error               jsonb,
    created_at          timestamptz not null default now(),
    finished_at         timestamptz,
    constraint criativo_agente_run_ref_ck check (run_ref ~ '^crrun_[a-f0-9]{24}$'),
    constraint criativo_agente_run_status_ck check (status in ('RUNNING','COMPLETED','FAILED')),
    constraint criativo_agente_run_phase_ck
        check (phase in ('NOVA_OPERACAO','DIAGNOSTICO','ARQUITETURA','MATRIZ','COPY','REFACAO')),
    constraint criativo_agente_run_input_object_ck check (jsonb_typeof(input) = 'object'),
    constraint criativo_agente_run_output_object_ck check (output is null or jsonb_typeof(output) = 'object'),
    constraint criativo_agente_run_attempts_ck check (tentativas is null or tentativas between 1 and 2),
    constraint criativo_agente_run_request_hash_ck check (request_sha256 is null or request_sha256 ~ '^[a-f0-9]{64}$'),
    constraint criativo_agente_run_knowledge_hash_ck check (knowledge_sha256 is null or knowledge_sha256 ~ '^[a-f0-9]{64}$')
);

alter table public.criativo_agente_operacao
    add constraint criativo_agente_latest_run_fk
    foreign key (latest_run_ref) references public.criativo_agente_run(run_ref)
    deferrable initially deferred;

create table if not exists public.criativo_agente_decisao (
    decision_ref        text primary key,
    project_ref         text not null references public.criativo_agente_operacao(project_ref),
    run_ref             text not null references public.criativo_agente_run(run_ref),
    owner_id            uuid not null,
    decisao             text not null,
    scope               text not null,
    path                text not null,
    snapshot            jsonb not null,
    snapshot_sha256     text not null,
    feedback            text,
    created_at          timestamptz not null default now(),
    constraint criativo_agente_decisao_ref_ck check (decision_ref ~ '^crdec_[a-f0-9]{24}$'),
    constraint criativo_agente_decisao_tipo_ck check (decisao in ('APROVADO','REPROVADO')),
    constraint criativo_agente_decisao_scope_ck check (scope in ('PONTUAL','GRUPO','PROJETO','UNIVERSAL')),
    constraint criativo_agente_decisao_path_ck check (path ~ '^/[A-Za-z0-9_/-]+$'),
    constraint criativo_agente_decisao_hash_ck check (snapshot_sha256 ~ '^[a-f0-9]{64}$')
);

create index if not exists criativo_agente_run_project_ix
    on public.criativo_agente_run(project_ref, created_at desc);
create index if not exists criativo_agente_decisao_project_ix
    on public.criativo_agente_decisao(project_ref, created_at asc);

alter table public.criativo_agente_operacao enable row level security;
alter table public.criativo_agente_operacao force row level security;
alter table public.criativo_agente_run enable row level security;
alter table public.criativo_agente_run force row level security;
alter table public.criativo_agente_decisao enable row level security;
alter table public.criativo_agente_decisao force row level security;

drop policy if exists criativo_agente_operacao_owner on public.criativo_agente_operacao;
create policy criativo_agente_operacao_owner on public.criativo_agente_operacao
    for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
drop policy if exists criativo_agente_run_owner on public.criativo_agente_run;
create policy criativo_agente_run_owner on public.criativo_agente_run
    for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
drop policy if exists criativo_agente_decisao_owner on public.criativo_agente_decisao;
create policy criativo_agente_decisao_owner on public.criativo_agente_decisao
    for select to authenticated using (owner_id = auth.uid());
drop policy if exists criativo_agente_decisao_insert_owner on public.criativo_agente_decisao;
create policy criativo_agente_decisao_insert_owner on public.criativo_agente_decisao
    for insert to authenticated with check (owner_id = auth.uid());

revoke all on public.criativo_agente_operacao from anon;
revoke all on public.criativo_agente_run from anon;
revoke all on public.criativo_agente_decisao from anon;
grant select, insert, update on public.criativo_agente_operacao to authenticated;
grant select, insert, update on public.criativo_agente_run to authenticated;
grant select, insert on public.criativo_agente_decisao to authenticated;

commit;
