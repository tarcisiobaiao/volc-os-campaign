-- =============================================================================
-- v11_07 — A PONTE ENTRE A PECA ESTRATEGICA E O JOB DE MIDIA
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin.
-- ⚠️ NAO APLICADA EM PRODUCAO. Ver `supabase/migrations/README.md`.
-- ORDEM: DEPOIS da v11_06 (usa a chave unica (project_ref, owner_id) que ela
--        cria) e DEPOIS da v11_01 (referencia `criativo_job`).
--
-- -----------------------------------------------------------------------------
-- O QUE ESTA MIGRATION RESOLVE
-- -----------------------------------------------------------------------------
-- A decisao D07 do contrato desta frente e explicita:
--
--     "Nao trocar IDs para encaixar: `crproj_` do assistente NAO e
--      `creative_projeto.id`. Ponte explicita owner-scoped entre
--      operacao/run/peca estrategica e projeto/briefing/job/master do Estudio."
--
-- Sao dois espacos de identidade diferentes e nenhum dos dois deve ceder. O
-- assistente nomeia conceitos (`creative_<slug>`) dentro de uma run; o Estudio
-- nomeia trabalhos pagos (`criativo_job.id`). Reaproveitar uma coluna existente
-- para guardar o outro lado — ou pior, fazer os ids coincidirem — apaga a
-- diferenca entre "a ideia" e "o arquivo que custou dinheiro".
--
-- Sem esta tabela a pergunta "de qual peca aprovada veio esta imagem?" so teria
-- resposta por heuristica de texto do briefing, que e adivinhacao com cara de
-- procedencia.
--
-- ⚠️ A ponte NAO e uma FK entre os dois mundos e pronto: ela carrega o
-- `run_ref` e o `creative_ref` porque a MESMA peca pode ser regerada em outra
-- run, e as duas imagens precisam continuar distinguiveis depois.
-- =============================================================================

\set ON_ERROR_STOP on

begin;


-- =============================================================================
-- 1. PRE-VOO
-- =============================================================================

do $prevoo$
begin
    if to_regclass('public.criativo_agente_run') is null then
        raise exception 'v11_07 exige a v11_05 (criativo_agente_run)';
    end if;
    if to_regclass('public.criativo_job') is null then
        raise exception 'v11_07 exige a v11_01 (criativo_job)';
    end if;
    if not exists (
        select 1 from pg_constraint where conname = 'criativo_agente_run_ref_dono_uk'
    ) then
        raise exception
            'v11_07 exige a v11_06 (chave unica (run_ref, owner_id) em criativo_agente_run)';
    end if;
end
$prevoo$;


-- =============================================================================
-- 2. A PONTE
-- =============================================================================

create table if not exists public.criativo_agente_peca_job (
    ponte_ref      text primary key,
    owner_id       uuid not null,
    project_ref    text not null,
    run_ref        text not null,
    creative_ref   text not null,
    group_ref      text not null,
    copy_ref       text not null,
    state_ref      text not null,
    job_id         uuid not null references public.criativo_job(id),
    slots          text[] not null,
    fato_refs      text[] not null default '{}',
    rule_refs      text[] not null default '{}',
    created_at     timestamptz not null default now(),

    constraint criativo_agente_peca_job_ref_ck
        check (ponte_ref ~ '^crpj_[a-f0-9]{24}$'),
    constraint criativo_agente_peca_job_creative_ck
        check (creative_ref ~ '^creative_[a-z0-9_-]{3,64}$'),
    constraint criativo_agente_peca_job_group_ck
        check (group_ref ~ '^group_[a-z0-9_-]{3,64}$'),
    constraint criativo_agente_peca_job_copy_ck
        check (copy_ref ~ '^copy_[a-z0-9_-]{3,64}$'),
    constraint criativo_agente_peca_job_state_ck
        check (state_ref ~ '^state_[a-z0-9_-]{3,64}$'),
    constraint criativo_agente_peca_job_slots_ck
        check (cardinality(slots) between 1 and 12),

    -- O dono viaja junto nas duas pontas, como na v11_06: a integridade e
    -- constraint, nao convencao.
    constraint criativo_agente_peca_job_run_dono_fk
        foreign key (run_ref, owner_id)
        references public.criativo_agente_run (run_ref, owner_id),
    constraint criativo_agente_peca_job_operacao_dono_fk
        foreign key (project_ref, owner_id)
        references public.criativo_agente_operacao (project_ref, owner_id),

    -- A MESMA peca da MESMA run nao gera dois jobs. Reenviar o pedido devolve o
    -- job que ja existe em vez de pagar de novo — a mesma promessa que
    -- `criativo_job` ja faz por chave de idempotencia, dita tambem deste lado.
    constraint criativo_agente_peca_job_unica
        unique (run_ref, creative_ref)
);

comment on table public.criativo_agente_peca_job is
    'Ponte entre a peca estrategica aprovada (assistente) e o job de midia '
    '(Estudio). Dois espacos de identidade que NAO se fundem: ela responde '
    '"de qual peca aprovada veio esta imagem" sem adivinhar por texto.';

comment on column public.criativo_agente_peca_job.slots is
    'Os formatos pedidos NESTE job. N conceitos x M formatos: o conceito e a '
    'linha, os formatos sao o array.';

create index if not exists criativo_agente_peca_job_operacao_ix
    on public.criativo_agente_peca_job (project_ref, created_at desc);
create index if not exists criativo_agente_peca_job_job_ix
    on public.criativo_agente_peca_job (job_id);


-- =============================================================================
-- 3. SEGURANCA — o mesmo padrao da casa, desde o nascimento
-- =============================================================================
-- Esta tabela ja nasce fechada, sem repetir o erro que a v11_06 teve de
-- consertar na v11_05.

alter table public.criativo_agente_peca_job enable row level security;
alter table public.criativo_agente_peca_job force row level security;
revoke all on public.criativo_agente_peca_job from public, anon, authenticated, service_role;
grant select, insert on public.criativo_agente_peca_job to service_role;


-- =============================================================================
-- 4. VERIFICACAO EMBUTIDA
-- =============================================================================

do $verificacao$
declare
    n integer;
begin
    select count(*) into n
    from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name = 'criativo_agente_peca_job'
      and grantee in ('anon', 'authenticated', 'PUBLIC');
    if n <> 0 then
        raise exception 'v11_07 FALHOU: % privilegios para anon/authenticated/public', n;
    end if;

    select count(*) into n
    from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name = 'criativo_agente_peca_job'
      and grantee = 'service_role'
      and privilege_type in ('UPDATE', 'DELETE', 'TRUNCATE');
    if n <> 0 then
        raise exception 'v11_07 FALHOU: a ponte deve ser append-only (% privilegio(s) a mais)', n;
    end if;

    if not exists (
        select 1 from pg_constraint where conname = 'criativo_agente_peca_job_unica'
    ) then
        raise exception 'v11_07 FALHOU: falta a unicidade (run_ref, creative_ref)';
    end if;

    raise notice 'v11_07 OK: ponte peca->job append-only, fechada e com dono nas duas pontas.';
end
$verificacao$;

commit;
