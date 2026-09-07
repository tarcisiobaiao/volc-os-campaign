#!/usr/bin/env bash
# Prova o ciclo apply -> uso -> rollback -> reapply da v11_05 + v11_06 + v11_07 num
# PostgreSQL DESCARTAVEL. Nunca toca database.agenciavolc.com.br.
#
# Por que um cluster proprio e nao um banco no cluster do dev: o teste precisa
# criar as roles `anon`, `authenticated` e `service_role` e mexer em ACL default.
# Fazer isso num cluster compartilhado deixa residuo que ninguem procura depois.
#
# Uso:  ./scripts/provar-ciclo-assistente-criativo.sh
# Saida: PROVA OK / PROVA FALHOU, e o diretorio do cluster e removido no fim.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIG="$RAIZ/supabase/migrations"
BASE="${TMPDIR:-/tmp}/volc-v11_06-prova-$$"
PGDATA="$BASE/data"
PORTA="${PGPORT_PROVA:-55406}"
SOCK="$BASE/sock"

limpar() {
  pg_ctl -D "$PGDATA" -m immediate stop >/dev/null 2>&1 || true
  rm -rf "$BASE"
}
trap limpar EXIT

mkdir -p "$PGDATA" "$SOCK"
initdb -D "$PGDATA" -U postgres --auth=trust >/dev/null
pg_ctl -D "$PGDATA" -o "-p $PORTA -k $SOCK -c listen_addresses=''" -l "$BASE/pg.log" -w start >/dev/null

psql() { command psql -h "$SOCK" -p "$PORTA" -U postgres -d postgres -v ON_ERROR_STOP=1 "$@"; }

echo "── 0. cenario Supabase minimo (roles, auth.uid, default ACL quebrado)"
psql -q <<'SQL'
create role anon nologin;
create role authenticated nologin;
-- BYPASSRLS e o que o Supabase real da a esta role, e e o que faz o padrao
-- da casa (RLS forcada + ZERO policies + grant so a service_role) funcionar.
-- Sem este atributo a prova acusaria um defeito que nao existe no destino.
create role service_role nologin bypassrls;
create schema if not exists auth;
-- Stub: no Supabase real isto le o JWT. Aqui so precisa existir e tipar.
create or replace function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
-- ⚠️ Reproduz o ACHADO H (24/08/2026): default ACL concede tudo a todos em
-- TODA tabela nova. Sem isto a prova de seguranca seria mais facil que a
-- realidade e nao valeria nada.
alter default privileges in schema public
  grant all on tables to anon, authenticated, service_role;
SQL

echo "── 1. apply v11_05"
psql -q -f "$MIG/v11_05_criativo_agente_meta.sql"

echo "── 2. a v11_05 REALMENTE deixa o cliente fabricar run e aprovacao"
psql -q <<'SQL'
do $$
declare n integer;
begin
  select count(*) into n
  from information_schema.role_table_grants
  where table_schema='public' and table_name like 'criativo_agente_%'
    and grantee='authenticated' and privilege_type in ('INSERT','UPDATE');
  if n = 0 then
    raise exception 'prova invalida: esperava encontrar a porta aberta da v11_05';
  end if;
  raise notice 'v11_05 confirmada aberta: % grants INSERT/UPDATE a authenticated', n;
end $$;
SQL

echo "── 2b. stub de criativo_job (a v11_01 inteira nao faz parte desta prova)"
psql -q <<'SQL'
-- Apenas a superficie que a ponte referencia. Provar a v11_01 aqui seria provar
-- outra migration; o que importa e que a FK da ponte encontra o alvo certo.
create table if not exists public.criativo_job (id uuid primary key);
SQL

echo "── 3. apply v11_06 (endurecimento + fila)"
psql -q -f "$MIG/v11_06_criativo_agente_endurecimento.sql"

echo "── 3b. apply v11_07 (ponte peca->job)"
psql -q -f "$MIG/v11_07_criativo_agente_ponte_estudio.sql"

echo "── 4. USO: o backend (service_role) trabalha; o cliente nao"
psql -q <<'SQL'
-- o servidor grava a operacao, enfileira, reivindica e conclui
set role service_role;
insert into public.criativo_agente_operacao (project_ref, owner_id, status, input)
values ('crproj_'||repeat('a',24), '11111111-1111-1111-1111-111111111111', 'RUNNING', '{"nome_da_operacao":"Prova"}');

insert into public.criativo_agente_run (run_ref, project_ref, owner_id, status, phase, input)
values ('crrun_'||repeat('b',24), 'crproj_'||repeat('a',24),
        '11111111-1111-1111-1111-111111111111', 'QUEUED', 'NOVA_OPERACAO', '{}');

-- compare-and-set: so sai da fila quem esta QUEUED
update public.criativo_agente_run
   set status='RUNNING', claimed_at=now()
 where run_ref='crrun_'||repeat('b',24) and status='QUEUED';

update public.criativo_agente_run set status='COMPLETED', output='{"ok":true}'
 where run_ref='crrun_'||repeat('b',24) and status='RUNNING';

insert into public.criativo_agente_decisao
  (decision_ref, project_ref, run_ref, owner_id, decisao, scope, path, snapshot, snapshot_sha256)
values ('crdec_'||repeat('c',24), 'crproj_'||repeat('a',24), 'crrun_'||repeat('b',24),
        '11111111-1111-1111-1111-111111111111', 'APROVADO', 'GRUPO',
        '/grupos/group_x/nome', '"Territorio"', repeat('d',64));
reset role;

do $$
begin
  if (select count(*) from public.criativo_agente_run where status='COMPLETED') <> 1 then
    raise exception 'uso FALHOU: a run nao completou';
  end if;
  raise notice 'uso OK: fila -> claim -> completed -> decisao, tudo por service_role';
end $$;
SQL

echo "── 5. o cliente autenticado nao consegue mais fabricar nada"
psql -q <<'SQL'
do $$
declare bloqueado boolean := false;
begin
  begin
    set local role authenticated;
    perform set_config('request.jwt.claim.sub','22222222-2222-2222-2222-222222222222', true);
    insert into public.criativo_agente_run (run_ref, project_ref, owner_id, status, phase, input)
    values ('crrun_'||repeat('e',24), 'crproj_'||repeat('a',24),
            '22222222-2222-2222-2222-222222222222', 'COMPLETED', 'COPY', '{}');
  exception when insufficient_privilege then
    bloqueado := true;
  end;
  reset role;
  if not bloqueado then
    raise exception 'SEGURANCA FALHOU: authenticated ainda insere run';
  end if;
  raise notice 'seguranca OK: authenticated recusado ao tentar fabricar run';
end $$;

do $$
declare bloqueado boolean := false;
begin
  begin
    set local role authenticated;
    delete from public.criativo_agente_operacao;
  exception when insufficient_privilege then
    bloqueado := true;
  end;
  reset role;
  if not bloqueado then
    raise exception 'SEGURANCA FALHOU: authenticated ainda apaga a trilha';
  end if;
  raise notice 'seguranca OK: DELETE herdado do default ACL foi revogado';
end $$;
SQL

echo "── 6. a FK composta recusa run de outro dono sobre a mesma operacao"
psql -q <<'SQL'
do $$
declare bloqueado boolean := false;
begin
  begin
    set local role service_role;
    insert into public.criativo_agente_run (run_ref, project_ref, owner_id, status, phase, input)
    values ('crrun_'||repeat('f',24), 'crproj_'||repeat('a',24),
            '99999999-9999-9999-9999-999999999999', 'QUEUED', 'COPY', '{}');
  exception when foreign_key_violation then
    bloqueado := true;
  end;
  reset role;
  if not bloqueado then
    raise exception 'INTEGRIDADE FALHOU: run de outro dono entrou na operacao alheia';
  end if;
  raise notice 'integridade OK: owner -> operacao -> run virou constraint';
end $$;
SQL

echo "── 6b. a ponte guarda procedencia e recusa gerar a mesma peca duas vezes"
psql -q <<'SQL'
set role service_role;
insert into public.criativo_job (id) values ('00000000-0000-0000-0000-0000000000aa');
insert into public.criativo_agente_peca_job
  (ponte_ref, owner_id, project_ref, run_ref, creative_ref, group_ref, copy_ref, state_ref, job_id, slots)
values ('crpj_'||repeat('1',24), '11111111-1111-1111-1111-111111111111',
        'crproj_'||repeat('a',24), 'crrun_'||repeat('b',24),
        'creative_hook_frio', 'group_frio', 'copy_frio', 'state_frio',
        '00000000-0000-0000-0000-0000000000aa', array['1x1','4x5']);
reset role;

do $$
declare bloqueado boolean := false;
begin
  begin
    set local role service_role;
    insert into public.criativo_agente_peca_job
      (ponte_ref, owner_id, project_ref, run_ref, creative_ref, group_ref, copy_ref, state_ref, job_id, slots)
    values ('crpj_'||repeat('2',24), '11111111-1111-1111-1111-111111111111',
            'crproj_'||repeat('a',24), 'crrun_'||repeat('b',24),
            'creative_hook_frio', 'group_frio', 'copy_frio', 'state_frio',
            '00000000-0000-0000-0000-0000000000aa', array['9x16']);
  exception when unique_violation then
    bloqueado := true;
  end;
  reset role;
  if not bloqueado then
    raise exception 'PONTE FALHOU: a mesma peca da mesma run gerou dois jobs';
  end if;
  raise notice 'ponte OK: (run_ref, creative_ref) e unica — reenviar nao paga de novo';
end $$;

do $$
declare bloqueado boolean := false;
begin
  begin
    set local role service_role;
    update public.criativo_agente_peca_job set slots = array['1x1'];
  exception when insufficient_privilege then
    bloqueado := true;
  end;
  reset role;
  if not bloqueado then
    raise exception 'PONTE FALHOU: a procedencia deveria ser append-only';
  end if;
  raise notice 'ponte OK: append-only, nem o servidor reescreve procedencia';
end $$;
SQL

echo "── 6c. o rollback da ponte RECUSA apagar procedencia sem confirmacao"
if psql -q -f "$MIG/v11_07_rollback.sql" >/dev/null 2>&1; then
  echo "PROVA FALHOU: o rollback da ponte apagou procedencia sem confirmacao"; exit 1
fi
echo "   salvaguarda OK: rollback da ponte recusado"
psql -q -v confirmar_perda_de_procedencia=1 -f "$MIG/v11_07_rollback.sql" >/dev/null
echo "   com a intencao declarada, o rollback da ponte roda"

echo "── 7. rollback RECUSA enquanto houver run em QUEUED"
psql -q -c "set role service_role; insert into public.criativo_agente_run (run_ref, project_ref, owner_id, status, phase, input) values ('crrun_'||repeat('9',24), 'crproj_'||repeat('a',24), '11111111-1111-1111-1111-111111111111', 'QUEUED', 'COPY', '{}'); reset role;"
if psql -q -f "$MIG/v11_06_rollback.sql" >/dev/null 2>&1; then
  echo "PROVA FALHOU: o rollback aceitou apagar uma run enfileirada"; exit 1
fi
echo "   salvaguarda OK: rollback recusado com fila nao vazia"
psql -q -c "set role service_role; update public.criativo_agente_run set status='FAILED' where status='QUEUED'; reset role;"

echo "── 8. rollback"
psql -q -f "$MIG/v11_06_rollback.sql"
psql -q <<'SQL'
do $$
declare n integer;
begin
  select count(*) into n from information_schema.columns
  where table_schema='public' and table_name='criativo_agente_run' and column_name='claimed_at';
  if n <> 0 then raise exception 'rollback FALHOU: claimed_at sobreviveu'; end if;
  select count(*) into n from public.criativo_agente_run;
  if n < 2 then raise exception 'rollback FALHOU: perdeu linhas (restaram %)', n; end if;
  raise notice 'rollback OK: schema voltou a v11_05 e os dados ficaram (% runs)', n;
end $$;
SQL

echo "── 9. reapply (idempotencia do delta)"
psql -q -f "$MIG/v11_06_criativo_agente_endurecimento.sql"
psql -q -f "$MIG/v11_06_criativo_agente_endurecimento.sql"
echo "   reapply OK: aplicar duas vezes seguidas nao quebra"

echo
echo "PROVA OK — v11_05 + v11_06 + v11_07: apply, uso, seguranca, integridade, ponte, rollback, reapply."
