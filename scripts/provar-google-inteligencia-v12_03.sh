#!/usr/bin/env bash
# O ciclo da v12_03 num Postgres descartavel: aplicar -> provar -> reverter ->
# reaplicar, com prova de ESTRUTURA, SEGURANCA e COMPORTAMENTO.
#
# ## Por que docker, e nao initdb
#
# `scripts/provar-ciclo-v12_02.sh` exige `initdb`/`pg_ctl`/`psql` no PATH e sai 2
# quando faltam. Nesta maquina eles nao existem e o docker existe. O cluster
# continua descartavel e continua nascendo e morrendo aqui — o que muda e onde
# ele mora. NUNCA fala com o Supabase oficial: o container so escuta no socket
# interno dele, e o repositorio e montado SOMENTE LEITURA.
#
# ## O que ele prova
#
#   A. a v12_01 RECUSA cada um dos seis novos tipo_sinal;
#   B. a v12_03 continua aceitando os seis tipos antigos;
#   C. tipo desconhecido continua recusado — inclusive PMAX_RECOMENDACOES_FORCA,
#      que nunca ganhou valor proprio;
#   D. aplicar -> reverter -> reaplicar preserva linhas e invariantes;
#   E. a setima familia continua em RECOMENDACOES_ARMAZENADAS, distinguida por
#      campaign_id + payload.familia;
#   F. repeticao idempotente nao cria duas coletas;
#   G. o coleta_id devolvido resolve exatamente uma linha;
#   H. zero, vazio, falha, inelegivel e ausencia nao se achatam;
#   I. identidade frouxa nao passa pelo banco.
#
# Mais: RLS forcada, zero policies, anon/authenticated sem privilegio,
# `service_role` SEM escrita direta, append-only vivo, e o rollback que se
# RECUSA a apagar recibo PMax em silencio.
set -euo pipefail

command -v docker >/dev/null || { echo "INFRA: falta docker no PATH"; exit 2; }
docker info >/dev/null 2>&1 || { echo "INFRA: daemon docker indisponivel"; exit 2; }

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
IMAGEM="${VOLC_PG_IMAGE:-postgres:16-alpine}"
NOME="volc-v1203-$$"

limpar() { docker rm -f "$NOME" >/dev/null 2>&1 || true; }
trap limpar EXIT

echo "cluster descartavel: $NOME ($IMAGEM)"
docker run -d --name "$NOME" \
  -e POSTGRES_PASSWORD=descartavel -e POSTGRES_DB=postgres \
  -e LC_ALL=C -e LANG=C \
  -v "$RAIZ:/repo:ro" \
  "$IMAGEM" >/dev/null

# ⚠️ Espera ATIVA com teto. Um `sleep` fixo transforma maquina lenta em falha de
# migration, que e exatamente a confusao entre infra e produto que esta lane
# nao pode cometer.
pronto=0
for _ in $(seq 1 60); do
  if docker exec "$NOME" pg_isready -U postgres -q >/dev/null 2>&1; then pronto=1; break; fi
  sleep 1
done
[ "$pronto" = 1 ] || { echo "INFRA: postgres nao subiu em 60s"; docker logs "$NOME" | tail -20; exit 2; }

q() { docker exec -i "$NOME" psql -v ON_ERROR_STOP=1 -X -q -At -U postgres -c "$1"; }
f() { docker exec -i "$NOME" psql -v ON_ERROR_STOP=1 -X -q -U postgres -f "$1" >/dev/null; }

# Quantos valores o CHECK `trafego_google_coleta_tipo` admite HOJE. Conta os
# literais entre aspas na definicao devolvida pelo catalogo — nao no arquivo de
# migration, que diz o que alguem quis, e nao o que o banco tem.
n_valores() {
  q "select count(*) from (select regexp_matches(pg_get_constraintdef(c.oid), '''[A-Z_]+''', 'g') from pg_constraint c where c.conrelid='public.trafego_google_inteligencia_coleta'::regclass and c.conname='trafego_google_coleta_tipo') t"
}
definicao_do_tipo() {
  q "select pg_get_constraintdef(c.oid) from pg_constraint c where c.conrelid='public.trafego_google_inteligencia_coleta'::regclass and c.conname='trafego_google_coleta_tipo'"
}

ok=0; falhou=0
prova() { if eval "$2" >/dev/null 2>&1; then echo "  ok   $1"; ok=$((ok+1));
          else echo "  FALHOU  $1"; falhou=$((falhou+1)); fi; }
recusa() { if eval "$2" >/dev/null 2>&1; then echo "  FALHOU  $1 (foi aceito e devia ser recusado)"; falhou=$((falhou+1));
           else echo "  ok   $1"; ok=$((ok+1)); fi; }

# ⚠️ `sed` antes do `grep`. `raise notice` sai pelo stderr JA PREFIXADO pelo psql
# (`psql:arquivo.sql:123: NOTICE:  ok ...`), entao um `grep '^  ok'` nao casa com
# NADA — a primeira versao do script da v12_02 somou zero e anunciou "0
# falharam". Um degrau que nao roda e diz que passou e pior que um que falha.
comportamento() {
  local rotulo="$1" minimo="$2" bruto saida n_ok n_ko
  bruto="$(docker exec -i "$NOME" psql -X -q -v ON_ERROR_STOP=0 -U postgres \
            -f /repo/scripts/provar-google-inteligencia-v12_03.sql 2>&1)"
  saida="$(echo "$bruto" | sed -E 's/^psql:[^:]*:[0-9]+: NOTICE:  //')"
  echo "$saida" | grep -E '^(  ok|FALHOU|-- fase)' || true
  n_ok=$(echo "$saida" | grep -c '^  ok' || true)
  n_ko=$(echo "$saida" | grep -c '^FALHOU' || true)
  if [ "$((n_ok + n_ko))" -lt "$minimo" ]; then
    echo "  FALHOU  $rotulo produziu apenas $((n_ok + n_ko)) provas (esperado >= $minimo)"
    echo "$bruto" | tail -20
    falhou=$((falhou + 1))
  fi
  ok=$((ok + n_ok)); falhou=$((falhou + n_ko))
}

# ── papeis e o ACL padrao QUEBRADO de producao, reproduzido ─────────────────
#
# Sem reproduzir o achado H, a prova de contencao mediria um banco mais seguro
# que o real. `service_role` nasce com BYPASSRLS porque e assim no Supabase
# oficial (medido em pg_roles em 2026-08-29).
q "create role anon nologin; create role authenticated nologin;" >/dev/null
q "create role service_role nologin bypassrls;" >/dev/null
q "alter default privileges in schema public grant all on tables to anon, authenticated, service_role;" >/dev/null
q "alter default privileges in schema public grant execute on functions to anon, authenticated, service_role;" >/dev/null

echo; echo "DEGRAU 0 — v9_01 (FK de volc_campaign_id) e v12_01 (o ledger)"
f /repo/supabase/migrations/v9_01_trafego_inventario.sql
f /repo/supabase/migrations/v12_01_google_inteligencia_coletas.sql
prova "o CHECK da v12_01 tem exatamente seis valores" '[ "$(n_valores)" = 6 ]'
prova "a v12_01 nasce sem nenhum valor PMax" \
  '! definicao_do_tipo | grep -q PMAX_'

echo; echo "DEGRAU 1 — comportamento ANTES da v12_03 (contraprova A, vermelha por desenho)"
comportamento "o degrau A" 30

echo; echo "DEGRAU 2 — aplicar a v12_03"
f /repo/supabase/migrations/v12_03_pmax_observability_ledger.sql
prova "o CHECK passou a ter doze valores" '[ "$(n_valores)" = 12 ]'
prova "os seis valores da v12_01 continuam no CHECK" \
  "[ \"\$(q \"select count(*) from unnest(array['DIAGNOSTICO_ENTREGA','RECOMENDACOES_ARMAZENADAS','RECOMENDACOES_GERADAS','SIMULACOES_CAMPANHA','FORECAST_KEYWORDS','EXPERIMENTOS']) v where position(v in (select pg_get_constraintdef(c.oid) from pg_constraint c where c.conrelid='public.trafego_google_inteligencia_coleta'::regclass and c.conname='trafego_google_coleta_tipo')) > 0\")\" = 6 ]"
prova "as seis familias estruturais entraram" \
  "[ \"\$(q \"select count(*) from unnest(array['PMAX_CAMPANHA','PMAX_ASSET_GROUPS','PMAX_ASSET_GROUP_ASSETS','PMAX_ASSETS','PMAX_DESEMPENHO_ASSET_GROUP','PMAX_SINAIS']) v where position(v in (select pg_get_constraintdef(c.oid) from pg_constraint c where c.conrelid='public.trafego_google_inteligencia_coleta'::regclass and c.conname='trafego_google_coleta_tipo')) > 0\")\" = 6 ]"
prova "PMAX_RECOMENDACOES_FORCA NAO virou tipo_sinal" \
  '! definicao_do_tipo | grep -q PMAX_RECOMENDACOES_FORCA'
prova "nenhuma coluna nova foi criada" \
  "[ \"\$(q \"select count(*) from information_schema.columns where table_schema='public' and table_name='trafego_google_inteligencia_coleta'\")\" = 22 ]"
prova "as tres tabelas do ledger continuam de pe" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename in ('trafego_google_inteligencia_coleta','trafego_google_inteligencia_item','trafego_google_inteligencia_metrica')\")\" = 3 ]"
prova "as treze constraints CHECK da v12_01 continuam (uma delas reescrita)" \
  "[ \"\$(q \"select count(*) from pg_constraint where conrelid='public.trafego_google_inteligencia_coleta'::regclass and contype='c'\")\" = 13 ]"
prova "a UNIQUE da chave de idempotencia sobreviveu" \
  "[ \"\$(q \"select count(*) from pg_constraint where conrelid='public.trafego_google_inteligencia_coleta'::regclass and contype='u'\")\" = 1 ]"
prova "a FK para trafego_campanha sobreviveu" \
  "[ \"\$(q \"select count(*) from pg_constraint where conrelid='public.trafego_google_inteligencia_coleta'::regclass and contype='f'\")\" = 1 ]"
prova "RLS forcada nas tres tabelas" \
  "[ \"\$(q \"select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname in ('trafego_google_inteligencia_coleta','trafego_google_inteligencia_item','trafego_google_inteligencia_metrica') and c.relrowsecurity and c.relforcerowsecurity\")\" = 3 ]"
prova "zero policies" \
  "[ \"\$(q \"select count(*) from pg_policies where schemaname='public' and tablename like 'trafego_google_inteligencia_%'\")\" = 0 ]"
prova "anon/authenticated sem privilegio" \
  "[ \"\$(q \"select count(*) from information_schema.role_table_grants where table_schema='public' and table_name like 'trafego_google_inteligencia_%' and grantee in ('anon','authenticated','PUBLIC')\")\" = 0 ]"
prova "service_role SEM escrita direta" \
  "[ \"\$(q \"select count(*) from information_schema.role_table_grants where table_schema='public' and table_name like 'trafego_google_inteligencia_%' and grantee='service_role' and privilege_type in ('INSERT','UPDATE','DELETE','TRUNCATE')\")\" = 0 ]"
prova "service_role le" \
  "[ \"\$(q \"select has_table_privilege('service_role','public.trafego_google_inteligencia_coleta','SELECT')\")\" = t ]"
prova "anon NAO executa a RPC de escrita" \
  "[ \"\$(q \"select has_function_privilege('anon','public.volc_registrar_google_inteligencia(jsonb)','EXECUTE')\")\" = f ]"
prova "service_role executa a RPC de escrita" \
  "[ \"\$(q \"select has_function_privilege('service_role','public.volc_registrar_google_inteligencia(jsonb)','EXECUTE')\")\" = t ]"
prova "os tres gatilhos append-only continuam armados" \
  "[ \"\$(q \"select count(*) from pg_trigger where tgname like 'trafego_google_%append_only' and not tgisinternal\")\" = 3 ]"
recusa "aplicar a v12_03 duas vezes e recusado com nome" \
  "docker exec -i '$NOME' psql -v ON_ERROR_STOP=1 -X -q -U postgres -f /repo/supabase/migrations/v12_03_pmax_observability_ledger.sql"

echo; echo "DEGRAU 3 — comportamento DEPOIS da v12_03"
comportamento "o degrau v12_03" 30

echo; echo "DEGRAU 4 — o rollback se RECUSA a apagar recibo PMax em silencio"
prova "ha recibo PMax gravado" \
  "[ \"\$(q \"select count(*) > 0 from public.trafego_google_inteligencia_coleta where tipo_sinal like 'PMAX_%'\")\" = t ]"
recusa "reverter com recibo PMax no lugar e recusado" \
  "docker exec -i '$NOME' psql -v ON_ERROR_STOP=1 -X -q -U postgres -f /repo/supabase/migrations/v12_03_rollback.sql"
prova "a recusa NAO apagou nada" \
  "[ \"\$(q \"select count(*) > 0 from public.trafego_google_inteligencia_coleta where tipo_sinal like 'PMAX_%'\")\" = t ]"
prova "e o CHECK continua ampliado apos a recusa" \
  "[ \"\$(q \"select position('PMAX_CAMPANHA' in (select pg_get_constraintdef(oid) from pg_constraint where conname='trafego_google_coleta_tipo')) > 0\")\" = t ]"

echo; echo "DEGRAU 5 — arquivar EXPLICITAMENTE os recibos PMax, e so entao reverter"
# ⚠️ O gatilho append-only recusa DELETE. Desliga-lo e um ato DELIBERADO, com
# dono — e por isso ele mora aqui, no arranjo de prova, e nao dentro do arquivo
# de rollback, onde seria um efeito colateral que ninguem pediu.
q "create table arquivo_pmax_v1203 as select * from public.trafego_google_inteligencia_coleta where tipo_sinal like 'PMAX_%'" >/dev/null
prova "o arquivo guardou os recibos ANTES de remove-los" \
  "[ \"\$(q \"select count(*) > 0 from arquivo_pmax_v1203\")\" = t ]"
q "alter table public.trafego_google_inteligencia_coleta disable trigger trafego_google_coleta_append_only" >/dev/null
q "alter table public.trafego_google_inteligencia_item disable trigger trafego_google_item_append_only" >/dev/null
q "alter table public.trafego_google_inteligencia_metrica disable trigger trafego_google_metrica_append_only" >/dev/null
q "delete from public.trafego_google_inteligencia_metrica where coleta_id in (select coleta_id from arquivo_pmax_v1203)" >/dev/null
q "delete from public.trafego_google_inteligencia_item where coleta_id in (select coleta_id from arquivo_pmax_v1203)" >/dev/null
q "delete from public.trafego_google_inteligencia_coleta where tipo_sinal like 'PMAX_%'" >/dev/null
q "alter table public.trafego_google_inteligencia_coleta enable trigger trafego_google_coleta_append_only" >/dev/null
q "alter table public.trafego_google_inteligencia_item enable trigger trafego_google_item_append_only" >/dev/null
q "alter table public.trafego_google_inteligencia_metrica enable trigger trafego_google_metrica_append_only" >/dev/null
prova "nenhum recibo PMax sobrou no ledger" \
  "[ \"\$(q \"select count(*) from public.trafego_google_inteligencia_coleta where tipo_sinal like 'PMAX_%'\")\" = 0 ]"

f /repo/supabase/migrations/v12_03_rollback.sql
prova "o CHECK voltou a ter seis valores" '[ "$(n_valores)" = 6 ]'
prova "as tres tabelas continuam de pe apos o rollback" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename in ('trafego_google_inteligencia_coleta','trafego_google_inteligencia_item','trafego_google_inteligencia_metrica')\")\" = 3 ]"
prova "a RPC da v12_01 sobreviveu ao rollback" \
  "[ \"\$(q \"select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname='volc_registrar_google_inteligencia'\")\" = 1 ]"
prova "RLS forcada sobreviveu ao rollback" \
  "[ \"\$(q \"select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname like 'trafego_google_inteligencia_%' and c.relrowsecurity and c.relforcerowsecurity\")\" = 3 ]"
prova "os recibos da fase v12_01 continuam la (contraprova D)" \
  "[ \"\$(q \"select count(*) from public.trafego_google_inteligencia_coleta where payload->>'fase'='v12_01' and chave_idempotencia like '%|B-%'\")\" = 6 ]"
prova "a setima familia sobreviveu: ela nunca dependeu da v12_03" \
  "[ \"\$(q \"select count(*) > 0 from public.trafego_google_inteligencia_coleta where tipo_sinal='RECOMENDACOES_ARMAZENADAS' and payload->>'familia'='PMAX_RECOMENDACOES_FORCA'\")\" = t ]"
recusa "reverter duas vezes e recusado com nome" \
  "docker exec -i '$NOME' psql -v ON_ERROR_STOP=1 -X -q -U postgres -f /repo/supabase/migrations/v12_03_rollback.sql"

echo; echo "DEGRAU 6 — comportamento DEPOIS do rollback (os seis voltam a ser recusados)"
comportamento "o degrau revertido" 30

echo; echo "DEGRAU 7 — reaplicar"
f /repo/supabase/migrations/v12_03_pmax_observability_ledger.sql
prova "o CHECK tem doze valores de novo" '[ "$(n_valores)" = 12 ]'
prova "RLS forcada de novo" \
  "[ \"\$(q \"select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname like 'trafego_google_inteligencia_%' and c.relrowsecurity and c.relforcerowsecurity\")\" = 3 ]"
prova "os recibos das fases anteriores continuam intactos" \
  "[ \"\$(q \"select count(*) from public.trafego_google_inteligencia_coleta where chave_idempotencia like '%|B-%'\")\" = 18 ]"
prova "append-only continua armado depois do ciclo inteiro" \
  "[ \"\$(q \"select count(*) from pg_trigger where tgname like 'trafego_google_%append_only' and not tgisinternal and tgenabled='O'\")\" = 3 ]"

echo
echo "════════════════════════════════════════════════════════"
echo "  passaram $ok · falharam $falhou"
[ "$falhou" -eq 0 ] || exit 1
echo "  CICLO v12_03 COMPLETO: aplicar → provar → reverter → reaplicar"
