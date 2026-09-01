#!/usr/bin/env bash
# O ciclo da v12_02 num Postgres descartável: aplicar -> operar -> reverter ->
# reaplicar, com prova de ESTRUTURA, SEGURANÇA e COMPORTAMENTO.
#
# ## Por que um script
# Um rollback só existe se alguém o executa. Rollback documentado e nunca rodado
# é rollback que ninguém tem — o da v9_03 estava escrito como "reaplique a v9_02"
# e ABORTAVA, e só apareceu quando alguém tentou. Este roda o ciclo inteiro do
# zero, a cada execução, num cluster que nasce e morre aqui. Não toca em nada
# fora de $TMPDIR e NUNCA fala com o banco de produção.
#
# ## O que ele prova
# As seis invariantes que o schema defende, e não a aplicação:
#   1. destino de conversão offline exige DONO + ID NUMÉRICO — nunca nome;
#   2. ação eleita XOR causa de não eleger;
#   3. `completo` exige ação, destino, frescor com dados e meta resolvida;
#   4. plano incompleto sem bloqueador nomeado é recusado;
#   5. leitura sem conclusão não carrega contagem de conversão;
#   6. campanha que não nasceu não pode ter meta de campanha `com_dados`.
# Mais: idempotência pela impressão, append-only, RLS forçada, zero policies,
# anon/authenticated sem privilégio, e `service_role` SEM escrita direta.
set -euo pipefail

for b in initdb pg_ctl psql; do
  command -v "$b" >/dev/null || { echo "falta $b no PATH"; exit 2; }
done

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
D="$(mktemp -d "${TMPDIR:-/tmp}/v1202.XXXXXX")"
limpar() { pg_ctl -D "$D/d" -m immediate stop >/dev/null 2>&1 || true; rm -rf "$D"; }
trap limpar EXIT

# ⚠️ `LC_ALL=C` não é enfeite. Sem ela, o Postgres do Homebrew no macOS morre no
# arranque com "postmaster became multithreaded during startup".
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
# ⚠️ Sem reproduzir o achado H, a prova de contenção mediria um banco mais seguro
# que o real — e passaria por sorte. `service_role` nasce com BYPASSRLS porque é
# assim no Supabase oficial (medido em pg_roles em 2026-08-29).
q "create role anon nologin; create role authenticated nologin;" >/dev/null
q "create role service_role nologin bypassrls;" >/dev/null
q "alter default privileges in schema public grant all on tables to anon, authenticated, service_role;" >/dev/null
q "alter default privileges in schema public grant execute on functions to anon, authenticated, service_role;" >/dev/null

ok=0; falhou=0
prova() { if eval "$2" >/dev/null 2>&1; then echo "  ok   $1"; ok=$((ok+1));
          else echo "  FALHOU  $1"; falhou=$((falhou+1)); fi; }
recusa() { if eval "$2" >/dev/null 2>&1; then echo "  FALHOU  $1 (foi aceito e devia ser recusado)"; falhou=$((falhou+1));
           else echo "  ok   $1"; ok=$((ok+1)); fi; }

# ── a v9_01, porque a v12_02 tem FK para trafego_campanha ──────────────────
f "$RAIZ/supabase/migrations/v9_01_trafego_inventario.sql"

echo; echo "DEGRAU 1 — aplicar a v12_02"
f "$RAIZ/supabase/migrations/v12_02_plano_de_mensuracao.sql"
prova "tabela criada" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename='trafego_campanha_plano_de_mensuracao'\")\" = 1 ]"
prova "RLS forçada" \
  "[ \"\$(q \"select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname='trafego_campanha_plano_de_mensuracao' and c.relrowsecurity and c.relforcerowsecurity\")\" = 1 ]"
prova "zero policies" \
  "[ \"\$(q \"select count(*) from pg_policies where schemaname='public' and tablename='trafego_campanha_plano_de_mensuracao'\")\" = 0 ]"
prova "anon/authenticated sem privilégio" \
  "[ \"\$(q \"select count(*) from information_schema.role_table_grants where table_schema='public' and table_name='trafego_campanha_plano_de_mensuracao' and grantee in ('anon','authenticated','PUBLIC')\")\" = 0 ]"
prova "service_role SEM escrita direta" \
  "[ \"\$(q \"select count(*) from information_schema.role_table_grants where table_schema='public' and table_name='trafego_campanha_plano_de_mensuracao' and grantee='service_role' and privilege_type in ('INSERT','UPDATE','DELETE','TRUNCATE')\")\" = 0 ]"
prova "service_role lê" \
  "[ \"\$(q \"select has_table_privilege('service_role','public.trafego_campanha_plano_de_mensuracao','SELECT')\")\" = t ]"
prova "anon não executa a função de escrita" \
  "[ \"\$(q \"select has_function_privilege('anon','public.volc_registrar_plano_de_mensuracao(jsonb)','EXECUTE')\")\" = f ]"

echo; echo "DEGRAU 2 — comportamento: as seis invariantes do schema"
# ⚠️ `sed` antes do `grep`, e o motivo é uma prova que quase passou por engano.
# `raise notice` sai pelo stderr JÁ PREFIXADO pelo psql
# (`psql:arquivo.sql:123: NOTICE:  ok ...`), então um `grep '^  ok'` não casa com
# NADA — e a primeira versão deste script somou zero, imprimiu zero linhas e
# anunciou "0 falharam". Um degrau que não roda e diz que passou é pior que um
# degrau que falha.
BRUTO="$(psql -X -q -v ON_ERROR_STOP=0 -f "$RAIZ/scripts/provas-v12_02.sql" 2>&1)"
SAIDA="$(echo "$BRUTO" | sed -E 's/^psql:[^:]*:[0-9]+: NOTICE:  //')"
echo "$SAIDA" | grep -E '^(  ok|FALHOU)' || true
n_ok=$(echo "$SAIDA" | grep -c '^  ok' || true)
n_ko=$(echo "$SAIDA" | grep -c '^FALHOU' || true)
# A guarda contra o degrau mudo: se o bloco de comportamento não produziu prova
# nenhuma, ele NÃO passou — ele não rodou.
if [ "$((n_ok + n_ko))" -lt 20 ]; then
  echo "FALHOU  o degrau de comportamento produziu apenas $((n_ok + n_ko)) provas (esperado >= 20)"
  echo "$BRUTO" | tail -20
  falhou=$((falhou + 1))
fi
ok=$((ok + n_ok)); falhou=$((falhou + n_ko))

echo; echo "DEGRAU 3 — reverter"
f "$RAIZ/supabase/migrations/v12_02_rollback.sql"
prova "a tabela sumiu" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename='trafego_campanha_plano_de_mensuracao'\")\" = 0 ]"
prova "as funções sumiram" \
  "[ \"\$(q \"select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname in ('trafego_plano_append_only','volc_registrar_plano_de_mensuracao')\")\" = 0 ]"
prova "trafego_campanha (v9_01) intacta" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename='trafego_campanha'\")\" = 1 ]"

echo; echo "DEGRAU 4 — reaplicar"
f "$RAIZ/supabase/migrations/v12_02_plano_de_mensuracao.sql"
prova "tabela de novo" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename='trafego_campanha_plano_de_mensuracao'\")\" = 1 ]"
prova "RLS forçada de novo" \
  "[ \"\$(q \"select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname='trafego_campanha_plano_de_mensuracao' and c.relrowsecurity and c.relforcerowsecurity\")\" = 1 ]"
recusa "aplicar uma terceira vez é recusado com nome" \
  "psql -v ON_ERROR_STOP=1 -X -q -f '$RAIZ/supabase/migrations/v12_02_plano_de_mensuracao.sql'"

echo
echo "════════════════════════════════════════════════════════"
echo "  passaram $ok · falharam $falhou"
[ "$falhou" -eq 0 ] || exit 1
echo "  CICLO v12_02 COMPLETO: aplicar → operar → reverter → reaplicar"
