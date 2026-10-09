#!/usr/bin/env bash
# Coleta recorrente Google Ads → ledger v12_04/v17_01, pela RPC. Read-only no Google.
set -euo pipefail

MODE="${1:-}"
case "$MODE" in d0|d1) ;; *) echo "modo invalido: use d0 ou d1" >&2; exit 64 ;; esac

ROOT=/opt/volc-gads-coleta
LOCK=/run/lock/volc-gads-coleta.lock
RECIBOS=/var/lib/volc-gads-coleta/recibos
CONTA="${VOLC_GADS_CONTA:?defina VOLC_GADS_CONTA}"
MCC="${VOLC_GADS_MCC:?defina VOLC_GADS_MCC}"

# Dono único: uma execução por vez, qualquer modo. A segunda sai 75 sem ler nada.
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "coleta ja esta em execucao; esta invocacao nao concorre" >&2
  exit 75
fi

# Passo da agenda no fuso da conta (v12_04: 06/12/18/23 em D0; D-1 roda uma vez).
if [ "$MODE" = d0 ]; then ORIGEM=D0; PASSO="$(TZ=America/Sao_Paulo date +%H)"
else ORIGEM=D-1; PASSO=06; fi

export HOME="$ROOT"
export GOOGLE_ADS_CONFIGURATION_FILE_PATH="$ROOT/google-ads.yaml"
export SUPABASE_URL="https://database.agenciavolc.com.br"
export SUPABASE_SERVICE_ROLE_KEY="$SERVICE_ROLE_KEY"
unset FORGE_PERMITIR_ESCRITA
export PYTHONPATH="$ROOT/current:$ROOT/current/backend"

mkdir -p "$RECIBOS"
exec "$ROOT/venv/bin/python" -m volc_ads.coleta \
  --conta "$CONTA" --mcc "$MCC" --origem "$ORIGEM" --agenda "$PASSO" \
  --recibo "$RECIBOS/$(date -u +%Y%m%dT%H%M%SZ)-$MODE.json"
