#!/usr/bin/env bash
# Aplica a v17_01 (fatos granulares Google Ads) no Supabase oficial.
# Protocolo da casa: SHA-256 conferido, pg_dump antes, transação única com
# ON_ERROR_STOP, postflight de catálogo, recarga do PostgREST, recibo local.
# Provada antes em espelho local idêntico ao vivo: scripts/provas-v17_01.sql.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
ARQ="$RAIZ/supabase/migrations/v17_01_gads_fatos_granulares.sql"
ESPERADO=7e4ef29bb719aaf84db2d075129c8dfcc238171ba238b26cb0a86c684dfb2631
CARIMBO="$(date +%Y%m%d-%H%M%S)"
RECIBO="$RAIZ/docs/closure/gads-migrations-20261008/RECEIPT-v17_01-$CARIMBO.txt"
vivo() { ssh -i "$HOME/.ssh/volc_hetzner_claude_ed25519" -o BatchMode=yes -o ConnectTimeout=10 root@178.156.196.149 "$@"; }
PSQL="docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
log() { echo "$*" | tee -a "$RECIBO"; }

log "== preflight $CARIMBO"
REAL="$(shasum -a 256 "$ARQ" | cut -d' ' -f1)"
[[ "$REAL" == "$ESPERADO" ]] || { log "SHA DIVERGE: $REAL"; exit 1; }
log "sha ok  v17_01  $REAL"
JA="$(vivo "$PSQL -At -c \"select to_regclass('public.google_ads_fato_granular') is not null\"")"
PRE="$(vivo "$PSQL -At -c \"select (to_regclass('public.google_ads_campanha_dia') is not null) and (to_regclass('public.trafego_coleta_execucao') is not null)\"")"
log "estado  v17_01=$JA  v12_04_presente=$PRE"
[[ "$PRE" == "t" ]] || { log "v12_04 ausente: abortado"; exit 1; }
[[ "$JA" == "f" ]] || { log "v17_01 já aplicada: nada a fazer"; exit 0; }
[[ "${1:-}" == "--so-checar" ]] && { log "só preflight"; exit 0; }

log "== backup"
DUMP="/root/backups/pre-v17_01-$CARIMBO.dump"
vivo "docker exec supabase-db pg_dump -U postgres -Fc -n public postgres > $DUMP && ls -la $DUMP" | tee -a "$RECIBO"
vivo "test -s $DUMP" || { log "backup vazio: abortado"; exit 1; }

log "== aplica v17_01"
vivo "$PSQL" < "$ARQ" >>"$RECIBO" 2>&1 || { log "FALHOU — transação única, nada parcial. Backup: $DUMP"; exit 1; }

log "== postflight"
vivo "$PSQL -At" <<'SQL' | tee -a "$RECIBO"
select 'partições', count(*) from pg_inherits where inhparent = 'public.google_ads_fato_granular'::regclass;
select 'tabelas append-only', count(*) from information_schema.tables where table_schema='public' and table_name in ('google_ads_mudanca','google_ads_estado');
select 'views', count(*) from information_schema.views where table_schema='public' and table_name like 'vw_gads_%';
select 'rpc', count(*) from pg_proc where proname = 'volc_registrar_gads_fatos';
select 'RLS forçada', count(*) from pg_class where relname in ('google_ads_fato_granular','google_ads_mudanca','google_ads_estado') and relrowsecurity and relforcerowsecurity;
select 'anon sem acesso', not has_table_privilege('anon', 'public.google_ads_fato_granular', 'SELECT');
select 'authenticated sem RPC', not has_function_privilege('authenticated', 'public.volc_registrar_gads_fatos(jsonb)', 'EXECUTE');
select 'linhas (deve ser 0)', (select count(*) from google_ads_fato_granular) + (select count(*) from google_ads_mudanca) + (select count(*) from google_ads_estado);
NOTIFY pgrst, 'reload schema';
SQL
log "== fim · backup: $DUMP"
