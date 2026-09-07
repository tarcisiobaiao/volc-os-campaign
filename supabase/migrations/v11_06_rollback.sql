-- =============================================================================
-- v11_06 — ROLLBACK
-- =============================================================================
-- Desfaz o endurecimento e devolve o schema ao estado da v11_05.
--
-- ⚠️ Este rollback REABRE a porta que a v11_06 fechou: ele recria as quatro
-- policies e o `grant ... to authenticated` da v11_05, com os quais um cliente
-- autenticado volta a poder fabricar run e aprovacao para si mesmo via
-- PostgREST. Reverter e uma decisao de disponibilidade, nunca de seguranca.
--
-- ⚠️ Ele tambem derruba a fila: sem 'QUEUED' no CHECK, uma run enfileirada e
-- ainda nao executada passa a violar a constraint. Por isso o pre-voo abaixo
-- RECUSA rodar enquanto existir run em QUEUED, em vez de apagar trabalho do
-- operador para caber no schema antigo. Esvazie a fila (execute ou marque as
-- runs) antes de reverter.
--
-- NAO e destrutivo quanto a dados: nenhuma tabela e derrubada, nenhuma linha e
-- apagada. Apenas `claimed_at` some, e com ela a distincao entre uma run
-- rodando e uma abandonada.
-- =============================================================================

\set ON_ERROR_STOP on

begin;

do $prevoo$
declare
    n integer;
begin
    if to_regclass('public.criativo_agente_run') is null then
        raise exception 'v11_06_rollback: criativo_agente_run nao existe; nada a reverter';
    end if;
    select count(*) into n from public.criativo_agente_run where status = 'QUEUED';
    if n > 0 then
        raise exception
            'v11_06_rollback RECUSADO: % run(s) em QUEUED perderiam o estado. Execute-as ou conclua-as antes de reverter.', n;
    end if;
end
$prevoo$;


-- ── integridade composta volta a ser convencao ───────────────────────────────
alter table public.criativo_agente_decisao
    drop constraint if exists criativo_agente_decisao_run_dono_fk;
alter table public.criativo_agente_decisao
    drop constraint if exists criativo_agente_decisao_operacao_dono_fk;
alter table public.criativo_agente_run
    drop constraint if exists criativo_agente_run_operacao_dono_fk;

alter table public.criativo_agente_decisao
    add constraint criativo_agente_decisao_project_ref_fkey
    foreign key (project_ref) references public.criativo_agente_operacao(project_ref);
alter table public.criativo_agente_decisao
    add constraint criativo_agente_decisao_run_ref_fkey
    foreign key (run_ref) references public.criativo_agente_run(run_ref);
alter table public.criativo_agente_run
    add constraint criativo_agente_run_project_ref_fkey
    foreign key (project_ref) references public.criativo_agente_operacao(project_ref);

alter table public.criativo_agente_run
    drop constraint if exists criativo_agente_run_ref_dono_uk;
alter table public.criativo_agente_operacao
    drop constraint if exists criativo_agente_operacao_ref_dono_uk;


-- ── fila e listagem ──────────────────────────────────────────────────────────
drop index if exists public.criativo_agente_operacao_dono_ix;
drop index if exists public.criativo_agente_run_fila_ix;

alter table public.criativo_agente_run drop column if exists claimed_at;

alter table public.criativo_agente_run
    drop constraint if exists criativo_agente_run_status_ck;
alter table public.criativo_agente_run
    add constraint criativo_agente_run_status_ck
    check (status in ('RUNNING','COMPLETED','FAILED'));


-- ── a porta da v11_05, reaberta exatamente como ela era ──────────────────────
grant select, insert, update on public.criativo_agente_operacao to authenticated;
grant select, insert, update on public.criativo_agente_run to authenticated;
grant select, insert on public.criativo_agente_decisao to authenticated;

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

-- O backend continua precisando escrever. A v11_05 nunca concedeu isso
-- explicitamente (dependia do default ACL); manter o GRANT aqui e mais seguro
-- que reproduzir a omissao original.
grant select, insert, update on public.criativo_agente_operacao to service_role;
grant select, insert, update on public.criativo_agente_run to service_role;
grant select, insert on public.criativo_agente_decisao to service_role;

commit;
