-- =============================================================================
-- v11_06 — O ASSISTENTE PRECISA DE FILA, E A v11_05 ABRIU A PORTA ERRADA
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin.
-- ⚠️ NAO APLICADA EM PRODUCAO. Ver `supabase/migrations/README.md`.
-- ORDEM: DEPOIS da v11_05 (altera as tres tabelas que ela cria).
--        Independente de v11_01..v11_04.
--
-- Arquivo separado, e nao edicao da v11_05, de proposito: o estado fisico
-- oficial e desconhecido ate o catalogo, e reescrever uma migration que possa
-- ter sido aplicada troca um problema conhecido por um irreproduzivel. Este
-- delta e idempotente e vale nos dois mundos.
--
-- -----------------------------------------------------------------------------
-- 1. O QUE ESTA MIGRATION RESOLVE
-- -----------------------------------------------------------------------------
-- (A) SEGURANCA — a v11_05 inverteu a doutrina da propria familia.
--
--     v11_01:870 e v11_04:328 fazem
--         revoke all ... from public, anon, authenticated, service_role
--         grant select, insert, update ... to service_role
--     com RLS forcada e ZERO policies, porque a unica porta e o FastAPI
--     segurando service_role. A v11_05 fez o oposto: quatro policies e
--         grant select, insert, update ... to authenticated
--
--     Medido no arquivo: um cliente autenticado, com o proprio JWT e sem passar
--     pelo backend, consegue via PostgREST
--       1. inserir uma run e dar PATCH nela para status='COMPLETED' com um
--          `output` arbitrario  -> um lote estrategico que nenhum modelo gerou;
--       2. inserir uma decisao com decisao='APROVADO' e um snapshot_sha256 que
--          so passa por regex, nunca e recomputado -> uma aprovacao fabricada;
--       3. mover a operacao para READY_FOR_REVIEW e repontar latest_run_ref.
--     O confinamento por dono segura: ninguem forja para OUTRO usuario. O que
--     nao segura e a fabricacao para SI MESMO, e e ela que a etapa seguinte
--     desta frente consome como se fosse prova.
--
--     ⚠️ E ha um privilegio que a v11_05 nem revoga: `revoke ... from anon`
--     nao tira nada de `authenticated`, que herda `arwdDxt` do default ACL
--     quebrado deste banco (ACHADO H, 24/08/2026, registrado em v11_04:312).
--     Com a policy `for all`, isso da DELETE ao cliente sobre as proprias
--     operacoes e runs — apagar a trilha e exatamente o que ninguem pode poder.
--
--     ⚠️ A v11_05 tambem nunca concede nada a `service_role`: o backend
--     funciona hoje SO por herdar o mesmo default ACL quebrado. Por isso o
--     REVOKE abaixo vem obrigatoriamente acompanhado do GRANT explicito; um
--     revoke sozinho derrubaria o Assistente inteiro.
--
-- (B) FILA — criar e executar viraram atos separados no backend.
--
--     `criar operacao` gravava a run e SEGURAVA o request ate o LLM terminar.
--     Duas geracoes encadeadas estouram qualquer timeout de proxy, e quem
--     recarregava a pagina nao sabia se a run existia. O backend agora grava a
--     run como QUEUED e devolve a ref na hora; executar e outra rota, que
--     reivindica a run com um compare-and-set.
--
--     Isso exige dois objetos que a v11_05 nao tem: o valor 'QUEUED' no CHECK
--     de status e a coluna `claimed_at`, que e o que permite retomar uma run
--     abandonada sem roubar uma execucao saudavel.
--
-- (C) LISTAGEM — nao existia indice para "as operacoes deste dono".
--
--     Sem a listagem nao ha historico nem retomada, e a listagem ordena por
--     `updated_at` porque o operador procura o que mexeu por ultimo.
--
-- (D) INTEGRIDADE — owner -> operacao -> run -> decisao era convencao.
--
--     As FKs da v11_05 garantem que as refs existem, mas NADA amarra o
--     `owner_id` do filho ao do pai. Como a checagem de FK roda com privilegio
--     de integridade referencial e nao passa por RLS, o usuario B podia inserir
--     uma run apontando para a operacao do usuario A carregando owner_id = B.
--     A linha fica invisivel para A (toda leitura filtra owner_id), entao e
--     contaminacao de namespace e nao vazamento — mas e uma invariante que so
--     vivia em `criativos_agente.py`. As FKs compostas abaixo a tornam schema.
-- =============================================================================

\set ON_ERROR_STOP on

begin;


-- =============================================================================
-- 2. PRE-VOO: a v11_05 precisa estar aplicada
-- =============================================================================
-- Uma migration que "aplica sem erro" contra um schema que nao existe e o pior
-- desfecho: ela reporta sucesso e nao fez nada.

do $prevoo$
begin
    if to_regclass('public.criativo_agente_operacao') is null
       or to_regclass('public.criativo_agente_run') is null
       or to_regclass('public.criativo_agente_decisao') is null then
        raise exception
            'v11_06 exige as tres tabelas da v11_05 (operacao, run, decisao); aplique a v11_05 antes';
    end if;
end
$prevoo$;


-- =============================================================================
-- 3. FILA: o estado QUEUED e o carimbo de reivindicacao
-- =============================================================================

alter table public.criativo_agente_run
    drop constraint if exists criativo_agente_run_status_ck;
alter table public.criativo_agente_run
    add constraint criativo_agente_run_status_ck
    check (status in ('QUEUED','RUNNING','COMPLETED','FAILED'));

alter table public.criativo_agente_run
    add column if not exists claimed_at timestamptz;

comment on column public.criativo_agente_run.claimed_at is
    'Quando esta run foi reivindicada para execucao. NULL enquanto QUEUED. '
    'E o que distingue uma run rodando de uma run abandonada por um processo '
    'que morreu: passado o lease, outra execucao pode retomar sem disputar '
    'com um worker vivo.';

-- A fila so e util se der para achar o proximo trabalho sem varrer a tabela.
create index if not exists criativo_agente_run_fila_ix
    on public.criativo_agente_run (status, claimed_at)
    where status in ('QUEUED','RUNNING');


-- =============================================================================
-- 4. LISTAGEM POR DONO
-- =============================================================================

create index if not exists criativo_agente_operacao_dono_ix
    on public.criativo_agente_operacao (owner_id, updated_at desc);


-- =============================================================================
-- 5. INTEGRIDADE: o dono deixa de ser convencao e vira constraint
-- =============================================================================
-- ⚠️ A ORDEM AQUI E O QUE TORNA O REAPPLY POSSIVEL. As FKs compostas dependem
-- dos indices das chaves unicas, entao um `drop constraint ... uk` com a FK
-- ainda de pe falha com "other objects depend on it" — medido na SEGUNDA
-- aplicacao, no passo 9 de `scripts/provar-ciclo-v11_06.sh`. Filhos primeiro,
-- depois as chaves, depois os filhos de novo.

-- (i) soltar as FKs compostas, caso venham de uma aplicacao anterior
alter table public.criativo_agente_decisao
    drop constraint if exists criativo_agente_decisao_run_dono_fk;
alter table public.criativo_agente_decisao
    drop constraint if exists criativo_agente_decisao_operacao_dono_fk;
alter table public.criativo_agente_run
    drop constraint if exists criativo_agente_run_operacao_dono_fk;

-- (ii) as chaves unicas que sustentam as FKs compostas. Elas nao mudam a
--      identidade das tabelas, que continua sendo a PK de ref.
alter table public.criativo_agente_operacao
    drop constraint if exists criativo_agente_operacao_ref_dono_uk;
alter table public.criativo_agente_operacao
    add constraint criativo_agente_operacao_ref_dono_uk unique (project_ref, owner_id);

alter table public.criativo_agente_run
    drop constraint if exists criativo_agente_run_ref_dono_uk;
alter table public.criativo_agente_run
    add constraint criativo_agente_run_ref_dono_uk unique (run_ref, owner_id);

-- (iii) as FKs simples da v11_05 dao lugar as compostas, que carregam o dono.
alter table public.criativo_agente_run
    drop constraint if exists criativo_agente_run_project_ref_fkey;
alter table public.criativo_agente_run
    add constraint criativo_agente_run_operacao_dono_fk
    foreign key (project_ref, owner_id)
    references public.criativo_agente_operacao (project_ref, owner_id);

-- Isto tambem fecha, de graca, a invariante que so vivia no router: a run
-- apontada pela decisao passa a ser obrigatoriamente da MESMA operacao.
alter table public.criativo_agente_decisao
    drop constraint if exists criativo_agente_decisao_project_ref_fkey;
alter table public.criativo_agente_decisao
    drop constraint if exists criativo_agente_decisao_run_ref_fkey;
alter table public.criativo_agente_decisao
    add constraint criativo_agente_decisao_operacao_dono_fk
    foreign key (project_ref, owner_id)
    references public.criativo_agente_operacao (project_ref, owner_id);
alter table public.criativo_agente_decisao
    add constraint criativo_agente_decisao_run_dono_fk
    foreign key (run_ref, owner_id)
    references public.criativo_agente_run (run_ref, owner_id);


-- =============================================================================
-- 6. SEGURANCA: fechar a porta que a v11_05 deixou aberta
-- =============================================================================
-- As policies saem porque nao ha mais a quem servir: `authenticated` perde todo
-- privilegio, e `service_role` (BYPASSRLS) nunca consultou policy nenhuma. RLS
-- continua ENABLE + FORCE — se um dia alguem reconceder algo por engano, a
-- ausencia de policy nega por padrao em vez de liberar.

drop policy if exists criativo_agente_operacao_owner on public.criativo_agente_operacao;
drop policy if exists criativo_agente_run_owner on public.criativo_agente_run;
drop policy if exists criativo_agente_decisao_owner on public.criativo_agente_decisao;
drop policy if exists criativo_agente_decisao_insert_owner on public.criativo_agente_decisao;

do $seguranca$
declare
    t text;
begin
    foreach t in array array[
        'criativo_agente_operacao', 'criativo_agente_run', 'criativo_agente_decisao'
    ]
    loop
        execute format('alter table public.%I enable row level security', t);
        execute format('alter table public.%I force row level security', t);
        -- `service_role` no REVOKE por causa do default ACL quebrado deste
        -- banco: sem ele o GRANT seguinte pareceria restringir e so
        -- reafirmaria tres dos sete privilegios que a tabela ja nasceu tendo.
        execute format(
            'revoke all on public.%I from public, anon, authenticated, service_role', t);
        -- Sem DELETE e sem TRUNCATE para ninguem. Exclusao e logica.
        execute format(
            'grant select, insert, update on public.%I to service_role', t);
    end loop;
end
$seguranca$;

-- A decisao e append-only por construcao, e o schema passa a dizer isso.
revoke update on public.criativo_agente_decisao from service_role;


-- =============================================================================
-- 7. VERIFICACAO EMBUTIDA
-- =============================================================================
-- Uma migration que aplica "sem erro" e deixa `authenticated` com privilegio
-- passa despercebida ate a auditoria seguinte. Esta confere a si mesma.

do $verificacao$
declare
    n integer;
begin
    -- (a) nenhum privilegio sobrou para anon/authenticated/public
    select count(*) into n
    from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name like 'criativo_agente_%'
      and grantee in ('anon', 'authenticated', 'PUBLIC');
    if n <> 0 then
        raise exception 'v11_06 FALHOU: % privilegios ainda concedidos a anon/authenticated/public', n;
    end if;

    -- (b) service_role tem exatamente o necessario e nada de DELETE/TRUNCATE
    select count(*) into n
    from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name like 'criativo_agente_%'
      and grantee = 'service_role'
      and privilege_type in ('DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER');
    if n <> 0 then
        raise exception 'v11_06 FALHOU: service_role ainda tem % privilegio(s) proibido(s)', n;
    end if;

    -- (c) nenhuma policy sobrevive
    select count(*) into n from pg_policies
    where schemaname = 'public' and tablename like 'criativo_agente_%';
    if n <> 0 then
        raise exception 'v11_06 FALHOU: % policy(s) ainda existem', n;
    end if;

    -- (d) RLS forcada nas tres
    select count(*) into n from pg_class c
    join pg_namespace ns on ns.oid = c.relnamespace
    where ns.nspname = 'public' and c.relname like 'criativo_agente_%'
      and c.relkind = 'r' and c.relrowsecurity and c.relforcerowsecurity;
    if n <> 3 then
        raise exception 'v11_06 FALHOU: RLS forcada em % tabelas, esperado 3', n;
    end if;

    -- (e) a fila existe
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'criativo_agente_run'
          and column_name = 'claimed_at'
    ) then
        raise exception 'v11_06 FALHOU: criativo_agente_run.claimed_at ausente';
    end if;
    if not exists (
        select 1 from pg_constraint
        where conname = 'criativo_agente_run_status_ck'
          and pg_get_constraintdef(oid) like '%QUEUED%'
    ) then
        raise exception 'v11_06 FALHOU: status QUEUED nao entrou no CHECK';
    end if;

    -- (f) as FKs compostas amarram o dono
    select count(*) into n from pg_constraint
    where conname in (
        'criativo_agente_run_operacao_dono_fk',
        'criativo_agente_decisao_operacao_dono_fk',
        'criativo_agente_decisao_run_dono_fk'
    );
    if n <> 3 then
        raise exception 'v11_06 FALHOU: % de 3 FKs compostas presentes', n;
    end if;

    raise notice 'v11_06 OK: fila, listagem, integridade por dono e porta fechada.';
end
$verificacao$;

commit;
