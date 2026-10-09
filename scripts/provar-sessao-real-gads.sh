#!/usr/bin/env bash
# Prova o caminho HTTP do cockpit Google Ads com AUTENTICAÇÃO REAL (sessão do
# operador), sem dependency_overrides. Só leitura + validate_only.
#
# Uso (um passo):
#   1. No VOLC O.S. logado, console do navegador:
#        copy(JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.endsWith('-auth-token')))).access_token)
#   2. ./scripts/provar-sessao-real-gads.sh
#
# O token é lido da área de transferência (pbpaste), vai num arquivo 600
# temporário para o cabeçalho e é apagado na saída. Nunca é impresso.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
SAIDA="${SAIDA:-/tmp/volc-gads-blindagem/operacao-20261009/sessao-real}"
PEDIDO="${PEDIDO:-/tmp/volc-gads-blindagem/operacao-20261009/provar-106-search-pedido-v3.json}"
PORTA=8099
mkdir -p "$SAIDA"
CAB="$(mktemp)"; chmod 600 "$CAB"
limpar() { rm -f "$CAB"; [ -n "${PID:-}" ] && kill "$PID" 2>/dev/null || true; }
trap limpar EXIT

TOKEN="$(pbpaste | tr -d '[:space:]')"
case "$TOKEN" in eyJ*.*.*) ;; *) echo "a área de transferência não tem um JWT de sessão (passo 1)"; exit 2;; esac
printf 'Authorization: Bearer %s\n' "$TOKEN" > "$CAB"; unset TOKEN

set -a; . "$RAIZ/backend/.env"; set +a
unset FORGE_PERMITIR_ESCRITA
( cd "$RAIZ/backend" && PYTHONPATH="$RAIZ:$RAIZ/backend" .venv/bin/python -m uvicorn app.main:app \
    --host 127.0.0.1 --port "$PORTA" --log-level warning ) > "$SAIDA/backend.log" 2>&1 &
PID=$!
for _ in $(seq 1 60); do curl -s -o /dev/null "http://127.0.0.1:$PORTA/health" && break; sleep 1; done

chamar() {  # nome método rota [corpo]
  local nome=$1 metodo=$2 rota=$3 corpo=${4:-}
  if [ -n "$corpo" ]; then
    codigo=$(curl -s -o "$SAIDA/$nome.json" -w '%{http_code}' -X "$metodo" -H @"$CAB" \
      -H 'Content-Type: application/json' --data @"$corpo" "http://127.0.0.1:$PORTA$rota")
  else
    codigo=$(curl -s -o "$SAIDA/$nome.json" -w '%{http_code}' -X "$metodo" -H @"$CAB" "http://127.0.0.1:$PORTA$rota")
  fi
  echo "$nome → HTTP $codigo"
}
chamar trava GET /api/trafego/trava
chamar escopo GET /api/trafego/escopo
chamar cockpit GET "/api/trafego/candidatos/106?run_id=28"
chamar copy GET "/api/trafego/copy/106?run_id=28"
chamar conjunto GET /api/pautador/opportunities/106/conjunto-pago
chamar provar POST /api/trafego/provar "$PEDIDO"
python3 - "$SAIDA/provar.json" <<'PY'
import json, sys
b = json.load(open(sys.argv[1]))
p = b.get("preparo") or {}
print("provar: aprovado=%s ops=%s selo_retido=%s destino_elegivel=%s" % (
    p.get("aprovado"), p.get("n_operacoes"), bool(p.get("selo_retido")),
    (b.get("destino") or {}).get("elegivel")))
PY
echo "respostas em $SAIDA (nenhuma contém o token)"
