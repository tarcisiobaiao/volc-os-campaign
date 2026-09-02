#!/usr/bin/env bash
# A CORRIDA REAL da RPC v12_04, com DUAS CONEXÕES simultâneas.
#
# ## Por que este script existe
# `scripts/provar-ciclo-v12_04.sh` e `scripts/provas-v12_04.sql` provam o
# contrato inteiro — mas SEMPRE em UMA sessão, uma chamada de cada vez. Todas as
# invariantes da v12_04 que dependem de "ler, decidir, escrever" são defendidas
# por um `SELECT` que roda ANTES do `INSERT`, num snapshot que pode ter mudado
# quando a escrita acontece. Em série isso nunca aparece. É por isso que uma
# prova serial de precedência passa e a precedência mesmo assim não existe.
#
# ## Como a corrida é DETERMINÍSTICA e não temporizada
# Nada aqui dorme esperando dar sorte. Duas sessões psql persistentes são
# mantidas abertas por FIFO. O roteiro só avança quando o estado é OBSERVADO:
#  - fim de comando: sentinela `\echo` no stdout da sessão;
#  - bloqueio real: `pg_stat_activity.wait_event_type='Lock'` para o
#    `application_name` daquela sessão, lido por uma TERCEIRA conexão.
# Se o bloqueio esperado não acontece, o degrau falha em vez de passar por sorte.
#
# ## O que ele mede (e o que cada resposta significa)
#  C1 precedência D0 < D-1 sob corrida — janela fechada não pode ser rebaixada
#  C2 empate de posto decidido por `colhida_em`, sob corrida
#  C3 mesma chave + MESMO payload, concorrentes: recibo, não erro cru
#  C4 mesma chave + payload DIVERGENTE, concorrentes: recusa NOMEADA
#  C5 fechamento não fecha sobre escrita não confirmada
#  C6 o recibo sobrevive à supersessão legítima por execução concorrente
#  C7 precedência backfill > D-1 sob corrida
#
# NUNCA fala com database.agenciavolc.com.br. Cluster nasce e morre aqui.
set -uo pipefail

command -v docker >/dev/null || { echo "falta docker no PATH"; exit 2; }
command -v psql   >/dev/null || { echo "falta psql no PATH (host)"; exit 2; }

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
IMAGEM="${VOLC_PG_IMAGE:-postgres:16-alpine}"
C="volc-conc-$$"
PORTA="${VOLC_PG_PORTA:-55432}"
TMP="$(mktemp -d)"

limpar() {
  exec 3>&- 2>/dev/null || true
  exec 4>&- 2>/dev/null || true
  docker rm -f "$C" >/dev/null 2>&1 || true
  rm -rf "$TMP" 2>/dev/null || true
}
trap limpar EXIT

echo "cluster descartável: container $C ($IMAGEM) na porta $PORTA"
docker run --rm -d --name "$C" -p "$PORTA:5432" \
  -e POSTGRES_PASSWORD=descartavel -e POSTGRES_HOST_AUTH_METHOD=trust \
  "$IMAGEM" >/dev/null

# A mesma espera medida em provar-ciclo-v12_04.sh: `pg_isready` responde verde
# para o servidor TEMPORÁRIO do initdb. Espera-se o marcador E um SELECT que
# responde PELA PORTA PUBLICADA (é ela que as duas sessões vão usar).
export PGPASSWORD=descartavel
pronto=0
for _ in $(seq 1 90); do
  if docker logs "$C" 2>&1 | grep -q "PostgreSQL init process complete"; then
    if psql -h 127.0.0.1 -p "$PORTA" -U postgres -d postgres -X -q -At -c "select 1" >/dev/null 2>&1; then
      pronto=1; break
    fi
  fi
  sleep 1
done
[ "$pronto" = 1 ] || { echo "o cluster descartável não subiu"; docker logs "$C" 2>&1 | tail -20; exit 2; }

PSQL=(psql -h 127.0.0.1 -p "$PORTA" -U postgres -d postgres -X -q -At)

q()  { "${PSQL[@]}" -v ON_ERROR_STOP=1 -c "$1"; }
f()  { "${PSQL[@]}" -v ON_ERROR_STOP=1 -f - >/dev/null; }

ok=0; falhou=0
prova() {   # nome | comando  -> espera SUCESSO
  if eval "$2" >/dev/null 2>&1; then echo "  ok      $1"; ok=$((ok+1));
  else echo "  FALHOU  $1"; falhou=$((falhou+1)); fi
}
igual() {   # nome | obtido | esperado
  if [ "$2" = "$3" ]; then echo "  ok      $1"; ok=$((ok+1));
  else echo "  FALHOU  $1 — obtido [$2], esperado [$3]"; falhou=$((falhou+1)); fi
}
contem() {  # nome | texto | agulha
  case "$2" in *"$3"*) echo "  ok      $1"; ok=$((ok+1));;
    *) echo "  FALHOU  $1 — não contém [$3]; texto: $(echo "$2" | tr '\n' ' ' | cut -c1-220)"; falhou=$((falhou+1));; esac
}
nao_contem() {
  case "$2" in *"$3"*) echo "  FALHOU  $1 — contém [$3]; texto: $(echo "$2" | tr '\n' ' ' | cut -c1-220)"; falhou=$((falhou+1));;
    *) echo "  ok      $1"; ok=$((ok+1));; esac
}

# ── as duas sessões persistentes ──────────────────────────────────────────────
# Cada sessão é um psql vivo alimentado por FIFO. O fd fica aberto para o
# processo não ver EOF e sair.
SEQ=0
abrir() {  # $1 = fd, $2 = nome/application_name
  local fifo="$TMP/$2.fifo"
  mkfifo "$fifo"
  ( PGPASSWORD=descartavel psql -h 127.0.0.1 -p "$PORTA" -U postgres -d postgres \
      -X -q -At -v ON_ERROR_STOP=0 -f "$fifo" ) > "$TMP/$2.out" 2>&1 &
  eval "exec $1> \"$fifo\""
  eval "echo \"set application_name='$2';\" >&$1"
}
mandar() {  # $1 = fd, $2 = nome, $3 = sql  — envia e ESPERA a sentinela
  SEQ=$((SEQ+1)); local s="__FIM_${SEQ}__"
  eval "printf '%s\n' \"\$3\" >&\$1"
  eval "printf '\\\\echo %s\n' \"\$s\" >&\$1"
  for _ in $(seq 1 300); do
    grep -q "^$s\$" "$TMP/$2.out" 2>/dev/null && return 0
    sleep 0.1
  done
  echo "  FALHOU  timeout esperando [$3] em $2"; falhou=$((falhou+1)); return 1
}
mandar_async() {  # envia SEM esperar — para o comando que deve BLOQUEAR
  SEQ=$((SEQ+1)); ULTIMA_SENTINELA="__FIM_${SEQ}__"
  eval "printf '%s\n' \"\$3\" >&\$1"
  eval "printf '\\\\echo %s\n' \"\$ULTIMA_SENTINELA\" >&\$1"
}
esperar_sentinela() {  # $1 = nome, $2 = sentinela
  for _ in $(seq 1 300); do
    grep -q "^$2\$" "$TMP/$1.out" 2>/dev/null && return 0
    sleep 0.1
  done
  echo "  FALHOU  timeout esperando sentinela $2 em $1"; falhou=$((falhou+1)); return 1
}
esperar_bloqueio() {  # $1 = application_name — observa o BLOQUEIO, não o relógio
  local n
  for _ in $(seq 1 200); do
    n="$(q "select count(*) from pg_stat_activity where application_name='$1' and state='active' and wait_event_type='Lock'" 2>/dev/null || echo 0)"
    [ "$n" = "1" ] && return 0
    sleep 0.1
  done
  echo "  FALHOU  a sessão $1 NUNCA bloqueou — a corrida não foi encenada"; falhou=$((falhou+1)); return 1
}
saida_desde() {  # $1 = nome, $2 = marca inicial (num de linhas antes)
  tail -n "+$(( $2 + 1 ))" "$TMP/$1.out"
}
linhas() { wc -l < "$TMP/$1.out" | tr -d ' '; }

# ── preparo: papéis e migrations ─────────────────────────────────────────────
q "create role anon nologin; create role authenticated nologin;" >/dev/null
q "create role service_role nologin bypassrls;" >/dev/null
q "grant usage on schema public to anon, authenticated, service_role;" >/dev/null
f < "$RAIZ/supabase/migrations/v9_01_trafego_inventario.sql"
f < "$RAIZ/supabase/migrations/v12_04_gads_fato_canonico_dia.sql"
echo "v9_01 + v12_04 aplicadas no cluster descartável"

# ── fábrica de documentos ────────────────────────────────────────────────────
# Uma função SQL PERMANENTE (schema `conc`) monta o documento inteiro. Permanente
# e não `pg_temp` porque `pg_temp` morre com a sessão que a criou, e as duas
# sessões da corrida são OUTRAS. Montar o JSON em SQL, e não no shell, evita o
# quoting que é onde provas assim costumam mentir.
f <<'SQL'
create schema if not exists conc;
create or replace function conc.doc(
  p_chave text, p_exec text, p_origem text, p_data date,
  p_colhida timestamptz, p_campanha text, p_conta text default '8017851692',
  p_impressoes bigint default 10, p_ordinal integer default 1
) returns jsonb language sql as $$
  select jsonb_build_object(
    'chave_idempotencia', p_chave, 'execucao_chave', p_exec,
    'fonte','n8n', 'job','gads_dia_conc', 'disparo','agenda',
    'api_versao','v25', 'contrato_versao','v1', 'contrato_sha256', repeat('a',64),
    'tipo_lote','contas', 'lote_ordinal', p_ordinal,
    'origem_janela', p_origem, 'janela_inicio', p_data, 'janela_fim', p_data,
    'iniciada_em', p_colhida, 'encerrada_em', p_colhida,
    'duracao_ms', 1, 'batimento_em', p_colhida,
    'resultado','ok', 'projetar_compat', false,
    'linhas', jsonb_build_array(jsonb_build_object(
      'customer_id', p_conta, 'campaign_id', p_campanha,
      'metric_date', p_data, 'colhida_em', p_colhida,
      'currency_code','BRL', 'impressoes', p_impressoes, 'cliques', 1))
  );
$$;
create or replace function conc.fechamento(
  p_chave text, p_exec text, p_origem text, p_data date,
  p_aceitas integer, p_preteridas integer default 0, p_rejeitadas integer default 0
) returns jsonb language sql as $$
  select jsonb_build_object(
    'chave_idempotencia', p_chave, 'execucao_chave', p_exec,
    'fonte','n8n', 'job','gads_dia_conc', 'disparo','agenda',
    'api_versao','v25', 'contrato_versao','v1', 'contrato_sha256', repeat('a',64),
    'tipo_lote','fechamento', 'lote_ordinal', 0,
    'origem_janela', p_origem, 'janela_inicio', p_data, 'janela_fim', p_data,
    'iniciada_em', now(), 'encerrada_em', now(), 'duracao_ms', 1, 'batimento_em', now(),
    'resultado','ok',
    'linhas_aceitas', p_aceitas, 'linhas_preteridas', p_preteridas,
    'linhas_rejeitadas', p_rejeitadas,
    'projecao_estado','nao_solicitada', 'projecao_linhas', 0,
    'linhas', '[]'::jsonb
  );
$$;
SQL

# ── a tabela legada, como o arranjo de provas-v12_04.sql a monta ────────────
# A v12_04 NAO cria nem altera `daily_campaign_metrics`. Ela existe aqui porque
# a projecao de compatibilidade so tem sentido quando o alvo existe — e e
# exatamente o alvo que as corridas C8/C9 disputam.
f <<'SQL'
create table if not exists public.daily_campaign_metrics (
  id uuid primary key default gen_random_uuid(),
  campaign_id text not null,
  date date not null,
  impressions numeric, clicks numeric, spend numeric, conversions numeric,
  ctr numeric, cpc numeric, cost_per_conversion numeric,
  search_impression_share numeric,
  lost_impression_share_budget numeric, lost_impression_share_rank numeric,
  top_impression_percentage numeric, absolute_top_impression_percentage numeric,
  search_click_share numeric, search_exact_match_impression_share numeric,
  revenue numeric, updated_at timestamptz, created_at timestamptz default now(),
  unique (campaign_id, date)
);
SQL

abrir 3 s1
abrir 4 s2
abrir 5 s3
echo "três sessões abertas (s1, s2 e a auxiliar s3)"

# ══════════════════════════════════════════════════════════════════════════════
echo
echo "C1 — PRECEDÊNCIA SOB CORRIDA: D-1 (janela fechada) não pode ser rebaixada por D0"
# s1 grava D-1 e SEGURA a transação. s2 chega com D0 do MESMO fato: o pré-check
# dele roda num snapshot onde a linha ainda não existe, então ele decide gravar.
# Quando s1 confirma, o ON CONFLICT de s2 resolve — e é aí que a decisão velha
# vira escrita nova.
mandar 3 s1 "begin;"
mandar 3 s1 "select conc.doc('c1|d1|1','c1|d1','D-1','2026-08-30','2026-08-30T10:00:00Z','111001') as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
mandar 4 s2 "begin;"
M2=$(linhas s2)
mandar_async 4 s2 "select conc.doc('c1|d0|1','c1|d0','D0','2026-08-30','2026-08-30T23:00:00Z','111001') as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
S_C1="$ULTIMA_SENTINELA"
esperar_bloqueio s2
mandar 3 s1 "commit;"
esperar_sentinela s2 "$S_C1"
mandar 4 s2 "commit;"

igual "C1.1 sobrou UMA linha do fato" \
  "$(q "select count(*) from public.google_ads_campanha_dia where campaign_id='111001'")" "1"
igual "C1.2 a precedência que sobreviveu é a de D-1 (2)" \
  "$(q "select precedencia from public.google_ads_campanha_dia where campaign_id='111001'")" "2"
igual "C1.3 a origem que sobreviveu é D-1" \
  "$(q "select origem_janela from public.google_ads_campanha_dia where campaign_id='111001'")" "D-1"
igual "C1.4 a janela continua FECHADA" \
  "$(q "select janela_fechada from public.google_ads_campanha_dia where campaign_id='111001'")" "t"
igual "C1.5 o D0 preterido contou como PRETERIDA, não como aceita" \
  "$(q "select linhas_preteridas from public.trafego_coleta_execucao where chave_idempotencia='c1|d0|1'")" "1"
igual "C1.6 o D0 preterido NÃO contou linha aceita" \
  "$(q "select linhas_aceitas from public.trafego_coleta_execucao where chave_idempotencia='c1|d0|1'")" "0"

# ══════════════════════════════════════════════════════════════════════════════
echo
echo "C2 — EMPATE DE POSTO SOB CORRIDA: mesmo D-1, decide a colhida_em mais nova"
mandar 3 s1 "begin;"
mandar 3 s1 "select conc.doc(p_chave=>'c2|nova|1',p_exec=>'c2|nova',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T18:00:00Z',p_campanha=>'111002',p_impressoes=>99) as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
mandar 4 s2 "begin;"
mandar_async 4 s2 "select conc.doc(p_chave=>'c2|velha|1',p_exec=>'c2|velha',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T06:00:00Z',p_campanha=>'111002',p_impressoes=>7) as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
S_C2="$ULTIMA_SENTINELA"
esperar_bloqueio s2
mandar 3 s1 "commit;"
esperar_sentinela s2 "$S_C2"
mandar 4 s2 "commit;"

igual "C2.1 a leitura MAIS NOVA sobreviveu (impressoes=99)" \
  "$(q "select impressoes from public.google_ads_campanha_dia where campaign_id='111002'")" "99"
igual "C2.2 a colhida_em preservada é a de 18:00" \
  "$(q "select to_char(colhida_em at time zone 'UTC','HH24:MI') from public.google_ads_campanha_dia where campaign_id='111002'")" "18:00"
igual "C2.3 a leitura velha contou como preterida" \
  "$(q "select linhas_preteridas from public.trafego_coleta_execucao where chave_idempotencia='c2|velha|1'")" "1"

# ══════════════════════════════════════════════════════════════════════════════
echo
echo "C3 — MESMA CHAVE + MESMO PAYLOAD, CONCORRENTES: recibo, não erro cru"
mandar 3 s1 "begin;"
mandar 3 s1 "select conc.doc(p_chave=>'c3|mesma|1',p_exec=>'c3|mesma',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T10:00:00Z',p_campanha=>'111003') as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
mandar 4 s2 "begin;"
M3=$(linhas s2)
mandar_async 4 s2 "select conc.doc(p_chave=>'c3|mesma|1',p_exec=>'c3|mesma',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T10:00:00Z',p_campanha=>'111003') as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
S_C3="$ULTIMA_SENTINELA"
esperar_bloqueio s2
mandar 3 s1 "commit;"
esperar_sentinela s2 "$S_C3"
T3="$(saida_desde s2 "$M3")"
mandar 4 s2 "commit;"

nao_contem "C3.1 a segunda sessão NÃO recebe violação crua de chave duplicada" "$T3" "duplicate key value"
contem    "C3.2 a segunda sessão recebe o recibo guardado (repetida=true)"     "$T3" '"repetida": true'
contem    "C3.3 o recibo devolvido é o da PRIMEIRA sessão (mesmo execucao_id)"  "$T3" "$(q "select execucao_id from public.trafego_coleta_execucao where chave_idempotencia='c3|mesma|1'")"
igual     "C3.4 existe exatamente UM recibo para a chave" \
  "$(q "select count(*) from public.trafego_coleta_execucao where chave_idempotencia='c3|mesma|1'")" "1"
igual     "C3.5 existe exatamente UMA linha do fato" \
  "$(q "select count(*) from public.google_ads_campanha_dia where campaign_id='111003'")" "1"

# ══════════════════════════════════════════════════════════════════════════════
echo
echo "C4 — MESMA CHAVE + PAYLOAD DIVERGENTE, CONCORRENTES: recusa NOMEADA"
mandar 3 s1 "begin;"
mandar 3 s1 "select conc.doc(p_chave=>'c4|div|1',p_exec=>'c4|div',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T10:00:00Z',p_campanha=>'111004',p_impressoes=>10) as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
mandar 4 s2 "begin;"
M4=$(linhas s2)
mandar_async 4 s2 "select conc.doc(p_chave=>'c4|div|1',p_exec=>'c4|div',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T10:00:00Z',p_campanha=>'111004',p_impressoes=>7777) as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
S_C4="$ULTIMA_SENTINELA"
esperar_bloqueio s2
mandar 3 s1 "commit;"
esperar_sentinela s2 "$S_C4"
T4="$(saida_desde s2 "$M4")"
mandar 4 s2 "rollback;"

contem     "C4.1 a recusa é NOMEADA pelo contrato" "$T4" "CHAVE_REUTILIZADA_CONTEUDO_DIVERGENTE"
nao_contem "C4.2 a recusa NÃO é uma violação crua de constraint" "$T4" "duplicate key value"
igual      "C4.3 o payload divergente NÃO entrou no fato" \
  "$(q "select impressoes from public.google_ads_campanha_dia where campaign_id='111004'")" "10"

# ══════════════════════════════════════════════════════════════════════════════
echo
echo "C5 — FECHAMENTO NÃO FECHA SOBRE ESCRITA NÃO CONFIRMADA"
mandar 3 s1 "begin;"
mandar 3 s1 "select conc.doc(p_chave=>'c5|lote|1',p_exec=>'c5|exec',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T10:00:00Z',p_campanha=>'111005') as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
M5=$(linhas s2)
mandar 4 s2 "select conc.fechamento(p_chave=>'c5|fech|0',p_exec=>'c5|exec',p_origem=>'D-1',p_data=>'2026-08-30',p_aceitas=>1) as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
T5="$(saida_desde s2 "$M5")"
mandar 3 s1 "commit;"

contem "C5.1 o fechamento sobre escrita não confirmada é RECUSADO com nome" "$T5" "FECHAMENTO_SEM_ESCRITA"
igual  "C5.2 nenhum recibo de fechamento foi gravado" \
  "$(q "select count(*) from public.trafego_coleta_execucao where chave_idempotencia='c5|fech|0'")" "0"

# ══════════════════════════════════════════════════════════════════════════════
echo
echo "C6 — O RECIBO SOBREVIVE À SUPERSESSÃO LEGÍTIMA POR EXECUÇÃO CONCORRENTE"
# X (D0) grava o fato. Y (D-1) chega concorrente e, legitimamente, supera.
# X ainda não fechou. O fechamento de X descreve o que X realmente aceitou —
# e não pode virar erro de corrupção só porque outra execução passou na frente.
mandar 3 s1 "begin;"
mandar 3 s1 "select conc.doc(p_chave=>'c6|x|1',p_exec=>'c6|x',p_origem=>'D0',p_data=>'2026-08-30',p_colhida=>'2026-08-30T09:00:00Z',p_campanha=>'111006') as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
mandar 3 s1 "commit;"
mandar 4 s2 "begin;"
mandar 4 s2 "select conc.doc(p_chave=>'c6|y|1',p_exec=>'c6|y',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T11:00:00Z',p_campanha=>'111006') as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
mandar 4 s2 "commit;"
M6=$(linhas s1)
mandar 3 s1 "select conc.fechamento(p_chave=>'c6|x|0',p_exec=>'c6|x',p_origem=>'D0',p_data=>'2026-08-30',p_aceitas=>1) as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
T6="$(saida_desde s1 "$M6")"

igual      "C6.1 o fato final é o de D-1 (supersessão legítima)" \
  "$(q "select origem_janela from public.google_ads_campanha_dia where campaign_id='111006'")" "D-1"
nao_contem "C6.2 o fechamento de X NÃO acusa recibo irresolvível" "$T6" "RECIBO_NAO_RESOLVE_FATOS"
igual      "C6.3 o recibo de fechamento de X existe" \
  "$(q "select count(*) from public.trafego_coleta_execucao where chave_idempotencia='c6|x|0'")" "1"

# ══════════════════════════════════════════════════════════════════════════════
echo
echo "C7 — PRECEDÊNCIA SOB CORRIDA: backfill (3) supera D-1 (2), e D-1 não volta"
mandar 3 s1 "begin;"
mandar 3 s1 "select jsonb_set(jsonb_set(conc.doc(p_chave=>'c7|bf|1',p_exec=>'c7|bf',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T12:00:00Z',p_campanha=>'111007',p_impressoes=>555),'{origem_janela}','\"backfill\"'),'{fonte}','\"backfill_manual\"') as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
mandar 4 s2 "begin;"
mandar_async 4 s2 "select conc.doc(p_chave=>'c7|d1|1',p_exec=>'c7|d1',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T23:00:00Z',p_campanha=>'111007',p_impressoes=>1) as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
S_C7="$ULTIMA_SENTINELA"
esperar_bloqueio s2
mandar 3 s1 "commit;"
esperar_sentinela s2 "$S_C7"
mandar 4 s2 "commit;"

igual "C7.1 o backfill sobreviveu (impressoes=555)" \
  "$(q "select impressoes from public.google_ads_campanha_dia where campaign_id='111007'")" "555"
igual "C7.2 a precedência final é 3 (backfill)" \
  "$(q "select precedencia from public.google_ads_campanha_dia where campaign_id='111007'")" "3"

# ══════════════════════════════════════════════════════════════════════════════
echo
echo "C8 — PROJEÇÃO LEGADA: ambiguidade entre CONTAS tem de ser vista sob corrida"
# A legada é endereçada por (campaign_id, date) — sem conta. Duas contas com o
# MESMO campaign_id colidem nela, e a v12_04 trata isso recusando por
# ambiguidade. Mas a ambiguidade é medida por um EXISTS num snapshot: em série o
# EXISTS sempre enxerga a linha anterior (é o que CP-19 mede); com as duas
# transações abertas, nenhuma enxerga a outra — as chaves canônicas são
# DIFERENTES, então elas nem sequer bloqueiam uma à outra no fato.
q "insert into public.daily_campaign_metrics (campaign_id, date, revenue) values ('4900000008','2026-08-30', 99.0) on conflict do nothing" >/dev/null
mandar 3 s1 "begin;"
mandar 3 s1 "select jsonb_set(conc.doc(p_chave=>'c8|a|1',p_exec=>'c8|a',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T10:00:00Z',p_campanha=>'4900000008',p_conta=>'8017851692',p_impressoes=>111),'{projetar_compat}','true') as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
mandar 4 s2 "begin;"
mandar_async 4 s2 "select jsonb_set(conc.doc(p_chave=>'c8|b|1',p_exec=>'c8|b',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T10:00:00Z',p_campanha=>'4900000008',p_conta=>'7788990011',p_impressoes=>222),'{projetar_compat}','true') as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
S_C8="$ULTIMA_SENTINELA"
esperar_bloqueio s2
mandar 3 s1 "commit;"
esperar_sentinela s2 "$S_C8"
mandar 4 s2 "commit;"

igual "C8.1 o fato canônico das DUAS contas está íntegro" \
  "$(q "select count(*) from public.google_ads_campanha_dia where campaign_id='4900000008'")" "2"
igual "C8.2 ao menos um recibo recusou a projeção por ambiguidade" \
  "$(q "select count(*) from public.trafego_coleta_execucao where chave_idempotencia in ('c8|a|1','c8|b|1') and projecao_estado='recusada_ambigua'")" "1"
igual "C8.3 NÃO existem dois recibos dizendo 'aplicada' para a mesma linha legada" \
  "$(q "select count(*) from public.trafego_coleta_execucao where chave_idempotencia in ('c8|a|1','c8|b|1') and projecao_estado='aplicada'")" "1"
igual "C8.4 a receita da legada continua intacta (a projeção nunca a toca)" \
  "$(q "select revenue from public.daily_campaign_metrics where campaign_id='4900000008' and date='2026-08-30'")" "99.0"

# ══════════════════════════════════════════════════════════════════════════════
echo
echo "C9 — PROJEÇÃO LEGADA: dois segmentos do mesmo fato não podem se sobrescrever calados"
# A chave canônica inclui `segments_hash`; a legada não tem esse conceito. Duas
# linhas legítimas do MESMO (conta, campanha, dia) com segmentos diferentes
# mapeiam na MESMA linha legada. O EXISTS de ambiguidade compara só a CONTA —
# não olha segmento — então as duas projetam, a segunda sobrescreve a primeira,
# e o recibo conta as duas como aplicadas. Isto não precisa de corrida: falha em
# série, e passou despercebido porque nenhuma contraprova envia dois segmentos.
q "insert into public.daily_campaign_metrics (campaign_id, date, revenue) values ('4900000009','2026-08-30', 55.0) on conflict do nothing" >/dev/null
mandar 3 s1 "select jsonb_set(jsonb_set(conc.doc(p_chave=>'c9|seg|1',p_exec=>'c9|seg',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T10:00:00Z',p_campanha=>'4900000009',p_impressoes=>10),'{projetar_compat}','true'),'{linhas}',
  (select jsonb_agg(l) from (
     select jsonb_build_object('customer_id','8017851692','campaign_id','4900000009','metric_date','2026-08-30','colhida_em','2026-08-30T10:00:00Z'::timestamptz,'currency_code','BRL','impressoes',10,'segmentos',jsonb_build_object('device','MOBILE')) as l
     union all
     select jsonb_build_object('customer_id','8017851692','campaign_id','4900000009','metric_date','2026-08-30','colhida_em','2026-08-30T10:00:00Z'::timestamptz,'currency_code','BRL','impressoes',20,'segmentos',jsonb_build_object('device','DESKTOP')) as l
  ) x)) as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"

igual "C9.1 as duas linhas segmentadas viraram DOIS fatos canônicos" \
  "$(q "select count(*) from public.google_ads_campanha_dia where campaign_id='4900000009'")" "2"
igual "C9.2 a projeção NÃO declara ter aplicado duas linhas na mesma linha legada" \
  "$(q "select projecao_linhas from public.trafego_coleta_execucao where chave_idempotencia='c9|seg|1'")" "0"
igual "C9.3 a projeção recusa por ambiguidade em vez de escolher um segmento" \
  "$(q "select projecao_estado from public.trafego_coleta_execucao where chave_idempotencia='c9|seg|1'")" "recusada_ambigua"
igual "C9.4 a legada NÃO recebeu o número de um segmento arbitrário" \
  "$(q "select coalesce(impressions::text,'NULO') from public.daily_campaign_metrics where campaign_id='4900000009' and date='2026-08-30'")" "NULO"

# ══════════════════════════════════════════════════════════════════════════════
echo
echo "C10 — A TRAVA DA PROJEÇÃO NÃO PODE PRODUZIR ESPERA CIRCULAR"
# A trava consultiva que consertou C8 é tomada DENTRO de um laço, uma por linha
# legada. Trava dentro de laço só é segura se TODAS as transações a adquirirem
# na MESMA ordem global — senão duas execuções que tocam as mesmas campanhas em
# ordens opostas esperam uma pela outra.
#
# O laço ordenava por `(customer_id, campaign_id)` e travava por
# `(campaign_id, metric_date)`. As duas ordens não coincidem: basta que as
# execuções tenham CONTAS diferentes para as mesmas campanhas saírem em ordem
# invertida. O sintoma não é travar para sempre — o Postgres detecta e aborta
# uma —, é a projeção falhar com 40P01 de forma intermitente, o que é pior de
# diagnosticar do que um erro constante.
#
# A corrida é encenada, não sorteada: uma terceira sessão segura a linha legada
# de BBB, o que prende s1 depois de ela já ter a trava de BBB. Só então s2 pega
# AAA e vai buscar BBB. Quando s3 solta, o ciclo se fecha.
CAMPA=1111111111   # "AAA" — menor campaign_id
CAMPB=8888888888   # "BBB" — maior campaign_id
q "insert into public.daily_campaign_metrics (campaign_id, date, revenue) values ('$CAMPA','2026-08-30',10.0),('$CAMPB','2026-08-30',20.0) on conflict do nothing" >/dev/null

# s3 segura a linha legada de BBB
mandar 5 s3 "begin;"
mandar 5 s3 "update public.daily_campaign_metrics set revenue = revenue where campaign_id='$CAMPB' and date='2026-08-30';"

# T1: contas 1000000xx -> ordenado por conta, BBB vem ANTES de AAA
mandar 3 s1 "begin;"
mandar_async 3 s1 "select jsonb_set(jsonb_set(conc.doc(p_chave=>'c10|t1|1',p_exec=>'c10|t1',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T10:00:00Z',p_campanha=>'$CAMPB'),'{projetar_compat}','true'),'{linhas}',
  jsonb_build_array(
    jsonb_build_object('customer_id','100000001','campaign_id','$CAMPB','metric_date','2026-08-30','colhida_em','2026-08-30T10:00:00Z'::timestamptz,'currency_code','BRL','impressoes',11),
    jsonb_build_object('customer_id','100000002','campaign_id','$CAMPA','metric_date','2026-08-30','colhida_em','2026-08-30T10:00:00Z'::timestamptz,'currency_code','BRL','impressoes',12))) as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
S_T1="$ULTIMA_SENTINELA"
esperar_bloqueio s1

# T2: contas 2000000xx -> ordenado por conta, AAA vem ANTES de BBB
mandar 4 s2 "begin;"
mandar_async 4 s2 "select jsonb_set(jsonb_set(conc.doc(p_chave=>'c10|t2|1',p_exec=>'c10|t2',p_origem=>'D-1',p_data=>'2026-08-30',p_colhida=>'2026-08-30T11:00:00Z',p_campanha=>'$CAMPA'),'{projetar_compat}','true'),'{linhas}',
  jsonb_build_array(
    jsonb_build_object('customer_id','200000001','campaign_id','$CAMPA','metric_date','2026-08-30','colhida_em','2026-08-30T11:00:00Z'::timestamptz,'currency_code','BRL','impressoes',21),
    jsonb_build_object('customer_id','200000002','campaign_id','$CAMPB','metric_date','2026-08-30','colhida_em','2026-08-30T11:00:00Z'::timestamptz,'currency_code','BRL','impressoes',22))) as d \\gset
select public.volc_registrar_gads_campanha_dia(:'d'::jsonb);"
S_T2="$ULTIMA_SENTINELA"
esperar_bloqueio s2

# solta a linha legada: o ciclo se fecha aqui, se ele existir
mandar 5 s3 "commit;"
esperar_sentinela s1 "$S_T1"
# ⚠️ COMMIT DE s1 ANTES de esperar s2, e a ordem importa: com a correção, s2 fica
# esperando a trava consultiva de AAA, que é de TRANSAÇÃO e só solta no commit.
# Esperar a sentinela de s2 antes de commitar s1 seria esperar por algo que eu
# mesmo estou segurando — o teste travaria por desenho do teste, não do código.
mandar 3 s1 "commit;"
esperar_sentinela s2 "$S_T2"
mandar 4 s2 "commit;"

igual "C10.1 nenhuma projeção falhou por espera circular (40P01)" \
  "$(q "select count(*) from public.trafego_coleta_execucao where projecao_erro_codigo = '40P01'")" "0"
igual "C10.2 as duas execuções fecharam seus lotes" \
  "$(q "select count(*) from public.trafego_coleta_execucao where chave_idempotencia in ('c10|t1|1','c10|t2|1')")" "2"
igual "C10.3 os quatro fatos canônicos entraram" \
  "$(q "select count(*) from public.google_ads_campanha_dia where campaign_id in ('$CAMPA','$CAMPB')")" "4"

# ══════════════════════════════════════════════════════════════════════════════
echo
echo "──────────────────────────────────────────────────────────────────────────"
echo "concorrência v12_04:  $ok ok   $falhou falharam"
[ "$falhou" = 0 ] || exit 1
