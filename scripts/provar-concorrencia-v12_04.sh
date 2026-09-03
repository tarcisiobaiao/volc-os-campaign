#!/usr/bin/env bash
# Prova concorrente material da v12_04: duas conexões PostgreSQL independentes,
# transações sobrepostas, wait_event_type='Lock' observado e desfecho coerente.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
IMAGEM="${VOLC_PG_IMAGE:-postgres:16-alpine}"
C="volc-v1204-race-$$"
TMP="/tmp/$C"
limpar(){ docker rm -f "$C" >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap limpar EXIT
mkdir -p "$TMP"

docker run --rm -d --name "$C" -e POSTGRES_PASSWORD=descartavel -e POSTGRES_HOST_AUTH_METHOD=trust "$IMAGEM" >/dev/null
for _ in $(seq 1 90); do
  if docker logs "$C" 2>&1 | grep -q "PostgreSQL init process complete" \
     && docker exec "$C" psql -U postgres -d postgres -X -q -At -c "select 1" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
q(){ docker exec -i "$C" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -At -c "$1"; }
f(){ docker exec -i "$C" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -f - >/dev/null; }
q "create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls; grant usage on schema public to anon, authenticated, service_role; alter default privileges in schema public grant all on tables to anon, authenticated, service_role; alter default privileges in schema public grant execute on functions to anon, authenticated, service_role;" >/dev/null
f < "$RAIZ/supabase/migrations/v9_01_trafego_inventario.sql"
f < "$RAIZ/supabase/migrations/v12_04_gads_fato_canonico_dia.sql"

doc(){
  local chave="$1" exec_chave="$2" campanha="$3" origem="$4" colhida="$5" imp="$6"
  cat <<SQL
jsonb_build_object('chave_idempotencia','$chave','execucao_chave','$exec_chave','fonte','n8n','job','gads_dia_d1','disparo','agenda','api_versao','v25','contrato_versao','v1','contrato_sha256',repeat('a',64),'tipo_lote','contas','lote_ordinal',1,'origem_janela','$origem','janela_inicio','2026-08-30','janela_fim','2026-08-30','iniciada_em',now(),'encerrada_em',now(),'duracao_ms',1,'batimento_em',now(),'resultado','ok','projetar_compat',false,'linhas',jsonb_build_array(jsonb_build_object('customer_id','8017851692','campaign_id','$campanha','metric_date','2026-08-30','colhida_em','$colhida','currency_code','BRL','impressoes',$imp,'cliques',1,'custo_micros',1000000)))
SQL
}

ok=0; falhou=0
prova(){ if eval "$2" >/dev/null 2>&1; then echo "  ok   $1"; ok=$((ok+1)); else echo "  FALHOU  $1"; falhou=$((falhou+1)); fi; }

concorrente_mesmo_payload(){
  local DOC; DOC="$(doc 'race_same|1' 'race_same' '5550000001' 'D-1' '2026-08-31T09:00:00Z' 10)"
  docker exec -i "$C" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -At >"$TMP/a.log" 2>&1 <<SQL &
BEGIN;
SELECT public.volc_registrar_gads_campanha_dia($DOC);
SELECT pg_sleep(10);
COMMIT;
SQL
  local A=$!
  for _ in $(seq 1 120); do grep -q 'execucao_id' "$TMP/a.log" && break; sleep 0.05; done
  grep -q 'execucao_id' "$TMP/a.log" || return 1
  docker exec -i "$C" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -At >"$TMP/b.log" 2>&1 <<SQL &
SELECT public.volc_registrar_gads_campanha_dia($DOC);
SQL
  local B=$! lock=0
  for _ in $(seq 1 120); do
    [ "$(q "select count(*) from pg_stat_activity where datname='postgres' and wait_event_type='Lock' and query like '%volc_registrar_gads_campanha_dia%' and query like '%race_same%'")" != 0 ] && { lock=1; break; }
    sleep 0.05
  done
  wait "$A"
  wait "$B"
  [ "$lock" = 1 ] || return 1
  grep -q 'repetida.*true\|"repetida": true\|"repetida" : true' "$TMP/b.log" || return 1
  [ "$(q "select count(*) from public.trafego_coleta_execucao where chave_idempotencia='race_same|1'")" = 1 ] || return 1
  [ "$(q "select count(*) from public.google_ads_campanha_dia where campaign_id='5550000001'")" = 1 ] || return 1
}

payload_divergente(){
  local D1 D2
  D1="$(doc 'race_div|1' 'race_div' '5550000002' 'D-1' '2026-08-31T09:00:00Z' 10)"
  D2="$(doc 'race_div|1' 'race_div' '5550000002' 'D-1' '2026-08-31T09:00:00Z' 11)"
  q "select public.volc_registrar_gads_campanha_dia($D1)" >/dev/null
  if q "select public.volc_registrar_gads_campanha_dia($D2)" 2>"$TMP/div.err" >/dev/null; then return 1; fi
  grep -q 'CHAVE_REUTILIZADA_CONTEUDO_DIVERGENTE' "$TMP/div.err" || return 1
  [ "$(q "select impressoes from public.google_ads_campanha_dia where campaign_id='5550000002'")" = 10 ] || return 1
}

precedencia_empate(){
  q "select public.volc_registrar_gads_campanha_dia($(doc 'race_d0|1' 'race_prec_d0' '5550000003' 'D0' '2026-08-30T12:00:00Z' 1))" >/dev/null
  q "select public.volc_registrar_gads_campanha_dia($(doc 'race_d1|1' 'race_prec_d1' '5550000003' 'D-1' '2026-08-31T09:00:00Z' 2))" >/dev/null
  q "select public.volc_registrar_gads_campanha_dia($(doc 'race_bf|1' 'race_prec_bf' '5550000003' 'backfill' '2026-09-03T09:00:00Z' 3))" >/dev/null
  [ "$(q "select impressoes||':'||origem_janela from public.google_ads_campanha_dia where campaign_id='5550000003'")" = '3:backfill' ] || return 1
  q "select public.volc_registrar_gads_campanha_dia($(doc 'race_tie_a|1' 'race_tie_a' '5550000004' 'D-1' '2026-08-31T09:00:00Z' 4))" >/dev/null
  q "select public.volc_registrar_gads_campanha_dia($(doc 'race_tie_b|1' 'race_tie_b' '5550000004' 'D-1' '2026-08-31T09:00:00Z' 4))" >/dev/null
  # empate total decide pelo menor execucao_id; a execução perdedora deixa recibo com preterida=1.
  [ "$(q "select count(*) from public.trafego_coleta_execucao where execucao_chave in ('race_tie_a','race_tie_b') and linhas_preteridas=1")" = 1 ] || return 1
}

prova "concorrência mesma chave+payload: Lock observado, B idempotente, sem duplicar" concorrente_mesmo_payload
prova "mesma chave+payload divergente: recusa explícita sem overwrite" payload_divergente
empate_divergente(){
  q "select public.volc_registrar_gads_campanha_dia($(doc 'race_tie_div_a|1' 'race_tie_div_a' '5550000005' 'D-1' '2026-08-31T09:00:00Z' 4))" >/dev/null
  if q "select public.volc_registrar_gads_campanha_dia($(doc 'race_tie_div_b|1' 'race_tie_div_b' '5550000005' 'D-1' '2026-08-31T09:00:00Z' 5))" 2>"$TMP/tie_div.err" >/dev/null; then return 1; fi
  grep -q 'FATO_EMPATE_CONTEUDO_DIVERGENTE' "$TMP/tie_div.err" || return 1
  [ "$(q "select impressoes from public.google_ads_campanha_dia where campaign_id='5550000005'")" = 4 ] || return 1
}

isolamento(){
  local D; D="$(doc 'race_iso|1' 'race_iso' '5550000006' 'D-1' '2026-08-31T09:00:00Z' 6)"
  if docker exec -i "$C" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -At 2>"$TMP/iso.err" >/dev/null <<SQL
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT public.volc_registrar_gads_campanha_dia($D);
COMMIT;
SQL
  then return 1; fi
  grep -q 'ISOLAMENTO_NAO_SUPORTADO_V12_04' "$TMP/iso.err" || return 1
}

prova "precedência D0<D-1<backfill e empate determinístico deixam recibo" precedencia_empate
prova "empate total com conteúdo divergente é conflito explícito" empate_divergente
prova "isolamento diferente de READ COMMITTED é recusado com nome" isolamento

echo "passaram $ok · falharam $falhou"
[ "$falhou" -eq 0 ]
