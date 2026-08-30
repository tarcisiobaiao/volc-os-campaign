#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-frequente}"
case "$MODE" in frequente|completa) ;; *) echo "modo invalido" >&2; exit 64 ;; esac

ROOT=/opt/volc-google-intelligence
LOCK=/run/lock/volc-google-intelligence.lock

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "coleta ja esta em execucao; esta invocacao nao concorre" >&2
  exit 75
fi

export HOME="$ROOT"
export VITE_SUPABASE_URL="https://database.agenciavolc.com.br"
export SUPABASE_SERVICE_ROLE_KEY="$SERVICE_ROLE_KEY"
unset FORGE_PERMITIR_ESCRITA
export PYTHONPATH="$ROOT/current"

exec "$ROOT/venv/bin/python" \
  "$ROOT/current/scripts/coletar_google_inteligencia.py" \
  --modo "$MODE"
