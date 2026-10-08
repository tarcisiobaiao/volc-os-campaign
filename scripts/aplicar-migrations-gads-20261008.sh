#!/usr/bin/env bash
# Aplica no Supabase oficial (database.agenciavolc.com.br) as três migrations
# Google Ads que o inventário de 08/10/2026 achou AUSENTES no banco vivo:
#
#   v12_03_pmax_observability_ledger  — amplia o CHECK de tipo_sinal (6 famílias PMax)
#   v10_02_autogestao                 — proposta → aprovação → aplicação → reversão (0/40 objetos)
#   v12_04_gads_fato_canonico_dia     — google_ads_campanha_dia + ledger de coleta (0/15)
#
# Protocolo da casa (supabase/migrations/README.md): SHA-256 conferido, backup
# antes, cada arquivo com a própria transação e ON_ERROR_STOP, releitura de
# catálogo depois, recarga do PostgREST, recibo local. Nenhuma linha de negócio
# é criada. Autorizado pelo Tarcísio em 08/10/2026.
#
# Uso:  scripts/aplicar-migrations-gads-20261008.sh            (aplica)
#       scripts/aplicar-migrations-gads-20261008.sh --so-checar (só preflight)
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
SSH=(ssh -i "$HOME/.ssh/volc_hetzner_claude_ed25519" -o BatchMode=yes -o ConnectTimeout=10 root@178.156.196.149)
PSQL="docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
CARIMBO="$(date +%Y%m%d-%H%M%S)"
RECIBO="$RAIZ/docs/closure/gads-migrations-20261008/RECEIPT-$CARIMBO.txt"

ORDEM=(v12_03_pmax_observability_ledger v10_02_autogestao v12_04_gads_fato_canonico_dia)
# `case` e não array associativo: o bash do macOS é o 3.2, sem `declare -A`.
sha_esperado() {
  case "$1" in
    v12_03_pmax_observability_ledger) echo f31dd1daf921de5c172f4a7d383476598c464181c4020a18f2d9d7289d6769c6 ;;
    v10_02_autogestao)                echo 124eac489c9d3bb88eb6c79fed0b3c2a8e7256064279954b2023144e073e0846 ;;
    v12_04_gads_fato_canonico_dia)    echo 3f40d05bb28f6019b8dbc1bb9bee88a53ce9cb471d8022e9d884b24c5b29d864 ;;
  esac
}

mkdir -p "$(dirname "$RECIBO")"
log() { echo "$*" | tee -a "$RECIBO"; }

log "== preflight $CARIMBO"
for m in "${ORDEM[@]}"; do
  real="$(shasum -a 256 "$RAIZ/supabase/migrations/$m.sql" | cut -d' ' -f1)"
  [[ "$real" == "$(sha_esperado "$m")" ]] || { log "SHA DIVERGE: $m ($real)"; exit 1; }
  log "sha ok  $m  $real"
done
"${SSH[@]}" "df -h / | tail -1" | sed 's/^/disco   /' | tee -a "$RECIBO"
JA_V12_03="$("${SSH[@]}" "$PSQL -At -c \"select coalesce(bool_or(pg_get_constraintdef(oid) like '%PMAX_SINAIS%'), false) from pg_constraint where conname='trafego_google_coleta_tipo'\"")"
JA_V10_02="$("${SSH[@]}" "$PSQL -At -c \"select to_regclass('public.trafego_proposta') is not null\"")"
JA_V12_04="$("${SSH[@]}" "$PSQL -At -c \"select to_regclass('public.google_ads_campanha_dia') is not null\"")"
log "estado   v12_03=$JA_V12_03 v10_02=$JA_V10_02 v12_04=$JA_V12_04"
[[ "${1:-}" == "--so-checar" ]] && { log "só preflight: nada aplicado"; exit 0; }

log "== backup"
DUMP="/root/backups/pre-gads-migrations-$CARIMBO.dump"
"${SSH[@]}" "docker exec supabase-db pg_dump -U postgres -Fc -n public postgres > $DUMP && ls -la $DUMP" | tee -a "$RECIBO"
"${SSH[@]}" "test -s $DUMP" || { log "backup vazio: abortado"; exit 1; }

aplicar() {
  local m="$1" ja="$2"
  if [[ "$ja" == "t" ]]; then log "pula    $m (já aplicada)"; return; fi
  log "aplica  $m"
  "${SSH[@]}" "$PSQL" < "$RAIZ/supabase/migrations/$m.sql" >>"$RECIBO" 2>&1 \
    || { log "FALHOU $m — o arquivo tem a própria transação; nada parcial. Backup: $DUMP"; exit 1; }
}
aplicar v12_03_pmax_observability_ledger "$JA_V12_03"
aplicar v10_02_autogestao "$JA_V10_02"
aplicar v12_04_gads_fato_canonico_dia "$JA_V12_04"

log "== postflight"
"${SSH[@]}" "$PSQL -At" <<'SQL' | tee -a "$RECIBO"
select 'v12_03 CHECK com PMax', bool_or(pg_get_constraintdef(oid) like '%PMAX_SINAIS%') from pg_constraint where conname='trafego_google_coleta_tipo';
select 'v10_02 tabelas', count(*) from information_schema.tables where table_schema='public' and table_name in ('trafego_regra_otimizacao','trafego_evidencia','trafego_diagnostico','trafego_proposta','trafego_aprovacao','trafego_aplicacao','trafego_acompanhamento','trafego_atuacao_reversao','trafego_cooldown');
select 'v12_04 objetos', count(*) from information_schema.tables where table_schema='public' and table_name in ('google_ads_campanha_dia','trafego_coleta_execucao','trafego_coleta_execucao_saude');
select 'v12_04 rpc', count(*) from pg_proc where proname in ('volc_registrar_gads_campanha_dia','volc_gads_projetar_daily_compat');
select 'linhas novas (deve ser 0)', (select count(*) from google_ads_campanha_dia) + (select count(*) from trafego_proposta);
select 'RLS forçada sem policy', count(*) from pg_class c where c.relname in ('google_ads_campanha_dia','trafego_coleta_execucao','trafego_proposta') and c.relrowsecurity and c.relforcerowsecurity;
NOTIFY pgrst, 'reload schema';
SQL
log "== fim · recibo: $RECIBO · backup no servidor: $DUMP"
