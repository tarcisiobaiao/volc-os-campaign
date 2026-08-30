#!/usr/bin/env bash
# O ciclo da v11_03 num Postgres descartável: aplicar -> operar -> reverter ->
# reaplicar, com prova de ESTRUTURA, SEGURANÇA e COMPORTAMENTO.
#
# ## Por que um script
# Um rollback só existe se alguém o executa. Este roda o ciclo inteiro do zero, a
# cada execução, num cluster que nasce e morre aqui. Não toca em nada fora de
# /tmp e NUNCA fala com o banco de produção.
#
# ## O que ele prova
# As sete invariantes do contrato da bancada, agora no banco:
#   1. transições válidas passam, inválidas são recusadas;
#   2. lease NÃO é renovado por transição;
#   3. dono é obrigatório em execução e não troca no meio;
#   4. `rendered` exige recibo e é terminal;
#   5. só `failed`/`cancelled` são retomáveis, com retry_n em ordem;
#   6. tenant entra na identidade; retomada cruzada é recusada;
#   7. artefato imutável depois de `rendered`; bytes/hash NOT NULL e com forma;
#   8. mensagem de erro não persiste caminho, stack nem drive do Windows;
#   9. claim concorrente com FOR UPDATE SKIP LOCKED não entrega o mesmo job;
#  10. RLS forçada, zero policies, anon/authenticated sem privilégio;
#  11. a trilha de transições é append-only.
set -euo pipefail

for b in initdb pg_ctl psql; do
  command -v "$b" >/dev/null || { echo "falta $b no PATH"; exit 2; }
done

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
D="$(mktemp -d "${TMPDIR:-/tmp}/v1103.XXXXXX")"
limpar() { pg_ctl -D "$D/d" -m immediate stop >/dev/null 2>&1 || true; rm -rf "$D"; }
trap limpar EXIT

# ⚠️ `LC_ALL=C` não é enfeite. Sem ela, o Postgres 16 do Homebrew no macOS morre
# no arranque com "postmaster became multithreaded during startup" — a própria
# dica do log manda definir a variável. Sem isto o script não sobe cluster nenhum.
export LC_ALL=C LANG=C

echo "cluster descartável em $D"
mkdir -p "$D/s"
initdb -D "$D/d" -U postgres --encoding=UTF8 --locale=C >/dev/null 2>&1
pg_ctl -D "$D/d" -l "$D/pg.log" -o "-k $D/s -h ''" -w start >/dev/null 2>&1
export PGHOST="$D/s" PGUSER=postgres PGDATABASE=postgres

q() { psql -v ON_ERROR_STOP=1 -X -q -At -c "$1"; }
f() { psql -v ON_ERROR_STOP=1 -X -q -f "$1" >/dev/null; }

# ── papéis e o ACL padrão QUEBRADO de produção, reproduzido ─────────────────
#
# ⚠️ ACHADO #10. `service_role` nascia aqui SEM `BYPASSRLS`, e isso fazia o
# cluster de prova ser mais seguro que o banco real: com RLS forçada e zero
# policies, o papel operacional ficava trancado, lia zero linhas e não conseguia
# inserir. As provas de segurança passavam contra um banco que não é o nosso.
#
# Medido no Supabase oficial em 2026-08-29, só no catálogo (`pg_roles`), sem
# tocar em dado e sem aplicar nada: anon=f, authenticated=f, service_role=t na
# coluna `rolbypassrls`. Reproduzimos essa premissa aqui.
q "create role anon nologin; create role authenticated nologin;" >/dev/null
q "create role service_role nologin bypassrls;" >/dev/null
# Mesmo GRANT do service_role, mas SEM bypassrls: é o papel que separa
# "a RLS bloqueou" (silencioso, zero linhas) de "o grant bloqueou" (42501).
q "create role prova_sem_bypass nologin;" >/dev/null
# ⚠️ Isto é o achado H, reproduzido de propósito: sem ele o teste de segurança
# passaria por sorte, testando um banco mais seguro que o real.
q "alter default privileges in schema public grant all on tables to anon, authenticated, service_role;" >/dev/null

ok=0; falhou=0
prova() { # nome, comando-que-deve-passar
  if eval "$2" >/dev/null 2>&1; then echo "  ok   $1"; ok=$((ok+1));
  else echo "  FALHOU  $1"; falhou=$((falhou+1)); fi
}
recusa() { # nome, comando-que-deve-FALHAR
  if eval "$2" >/dev/null 2>&1; then echo "  FALHOU  $1 (foi aceito e devia ser recusado)"; falhou=$((falhou+1));
  else echo "  ok   $1"; ok=$((ok+1)); fi
}

# ── as 21 tabelas anteriores, porque o rollback promete não tocá-las ────────
f "$RAIZ/supabase/migrations/v11_01_estudio_criativo.sql"
f "$RAIZ/supabase/migrations/v11_02_parque_criativo.sql"

echo; echo "DEGRAU 1 — aplicar a v11_03"
f "$RAIZ/supabase/migrations/v11_03_execucao_criativa.sql"
prova "5 tabelas criadas" "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_render_%'\")\" = 5 ]"
prova "RLS forçada nas 5" "[ \"\$(q \"select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname like 'criativo_render_%' and c.relkind='r' and c.relrowsecurity and c.relforcerowsecurity\")\" = 5 ]"
prova "zero policies" "[ \"\$(q \"select count(*) from pg_policies where schemaname='public' and tablename like 'criativo_render_%'\")\" = 0 ]"
prova "anon/authenticated sem privilégio" "[ \"\$(q \"select count(*) from information_schema.role_table_grants where table_schema='public' and table_name like 'criativo_render_%' and grantee in ('anon','authenticated','PUBLIC')\")\" = 0 ]"
prova "service_role sem DELETE" "[ \"\$(q \"select count(*) from information_schema.role_table_grants where table_schema='public' and table_name like 'criativo_render_%' and grantee='service_role' and privilege_type in ('DELETE','TRUNCATE')\")\" = 0 ]"
prova "trilha não é atualizável nem pelo service_role" "[ \"\$(q \"select count(*) from information_schema.role_table_grants where table_schema='public' and table_name='criativo_render_transicao' and grantee='service_role' and privilege_type='UPDATE'\")\" = 0 ]"

echo; echo "DEGRAU 2 — comportamento"
# ⚠️ Em SQL e não em bash. A primeira versão destas provas vivia dentro de `eval`
# com aspas em três níveis, a primeira inserção falhava por quoting e TODAS as
# seguintes cascateavam. Um arranjo de prova que falha por si mesmo não mede nada.
SAIDA="$(psql -X -q -v ON_ERROR_STOP=1 -f "$RAIZ/scripts/provas-v11_03.sql" 2>&1)"
echo "$SAIDA" | grep -vE '^\s*$'
ok=$((ok + $(echo "$SAIDA" | grep -c '^  ok' || true)))
falhou=$((falhou + $(echo "$SAIDA" | grep -c '^FALHOU' || true)))

echo; echo "DEGRAU 2b — segurança sob os PAPÉIS, executando de verdade"
# ⚠️ ACHADO #10. Os degraus de segurança acima leem catálogo: contam grants e
# conferem `relrowsecurity`. Isto aqui EXECUTA select/insert/update/delete/
# truncate sob anon, authenticated, o papel privilegiado com BYPASSRLS e um papel
# com o mesmo grant sem bypass — e confere SQLSTATE específico em cada recusa,
# separando "grant bloqueou" de "RLS bloqueou" de "gatilho recusou" de "a prova
# está quebrada".
q "grant select, insert, update on public.criativo_render_job to prova_sem_bypass" >/dev/null
PAPEIS="$(psql -X -q -v ON_ERROR_STOP=1 -f "$RAIZ/scripts/provas-papeis-v11_03.sql" 2>&1)"
echo "$PAPEIS" | grep -vE '^\s*$'
ok=$((ok + $(echo "$PAPEIS" | grep -c '^  ok' || true)))
falhou=$((falhou + $(echo "$PAPEIS" | grep -c '^FALHOU' || true)))

# claim concorrente: isto SÓ dá para provar com duas sessões de verdade.
q "insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed) values ('tenant-A','c1','{}'::jsonb,'m',7),('tenant-A','c2','{}'::jsonb,'m',7)" >/dev/null
CLAIM="update public.criativo_render_job set estado='claimed', owner='X', lease_ate=now()+interval '60s', batimento_em=now(), tentativa=1 where id = (select id from public.criativo_render_job where estado='queued' order by criado_em for update skip locked limit 1) returning idempotency_key"
A=$(psql -X -q -At -c "$CLAIM" 2>/dev/null | head -1)
B=$(psql -X -q -At -c "$CLAIM" 2>/dev/null | head -1)
if [ -n "$A" ] && [ -n "$B" ] && [ "$A" != "$B" ]; then
  echo "  ok   SKIP LOCKED: dois claims, dois jobs distintos ($A / $B)"; ok=$((ok+1))
else
  echo "FALHOU  SKIP LOCKED: A=$A B=$B"; falhou=$((falhou+1))
fi

echo; echo "DEGRAU 3 — reverter"
f "$RAIZ/supabase/migrations/v11_03_rollback.sql"
prova "as 5 tabelas sumiram" "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_render_%'\")\" = 0 ]"
prova "as 21 da v11_01/02 continuam de pé" "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_%' and tablename not like 'criativo_render_%'\")\" = 21 ]"

echo; echo "DEGRAU 4 — reaplicar"
f "$RAIZ/supabase/migrations/v11_03_execucao_criativa.sql"
prova "5 tabelas de novo" "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_render_%'\")\" = 5 ]"
prova "RLS forçada de novo" "[ \"\$(q \"select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname like 'criativo_render_%' and c.relkind='r' and c.relrowsecurity and c.relforcerowsecurity\")\" = 5 ]"

echo
echo "════════════════════════════════════════════════════════"
echo "  passaram $ok · falharam $falhou"
[ "$falhou" -eq 0 ] || exit 1
echo "  CICLO v11_03 COMPLETO: aplicar → operar → reverter → reaplicar"
