#!/usr/bin/env bash
# Prova o caminho HTTP do cockpit Google Ads com AUTENTICAÇÃO REAL (sessão do
# operador), sem dependency_overrides. Só leitura + validate_only (Search).
#
# Uso (um passo):
#   1. No VOLC O.S. logado, console do navegador (copia SÓ a sessão do Supabase
#      da VOLC — a chave é `sb-database-auth-token`, do host database.agenciavolc):
#        copy(JSON.parse(localStorage.getItem('sb-database-auth-token')).access_token)
#   2. ./scripts/provar-sessao-real-gads.sh
#
# Garantias:
# - o token é lido da área de transferência, conferido (emissor
#   https://database.agenciavolc.com.br/auth/v1 e validade) SEM ser impresso,
#   vai para um arquivo 600 dentro de um diretório 700 e é apagado na saída;
# - o backend sobe numa porta LIVRE e o script confere que quem escuta nela é
#   o processo que ele iniciou (não conversa com serviço já aberto);
# - FORGE_PERMITIR_ESCRITA é removida: nada é criado;
# - qualquer HTTP diferente do esperado encerra com o nome da rota.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
AUTORIDADE="https://database.agenciavolc.com.br"
SAIDA="${SAIDA:-/tmp/volc-gads-blindagem/sprint-operacional/sessao-real}"
PEDIDO="${PEDIDO:-/tmp/volc-gads-blindagem/operacao-20261009/provar-106-search-pedido-v3.json}"
mkdir -p "$SAIDA"
COFRE="$(mktemp -d)"; chmod 700 "$COFRE"; CAB="$COFRE/cabecalho"
PID=""
limpar() { rm -rf "$COFRE"; [ -n "$PID" ] && kill "$PID" 2>/dev/null || true; }
trap limpar EXIT

# ── 1. a sessão: do Supabase da VOLC, válida, nunca impressa ────────────────
pbpaste | tr -d '[:space:]' > "$COFRE/token"; chmod 600 "$COFRE/token"
python3 - "$COFRE/token" "$AUTORIDADE" <<'PY'
import base64, json, sys, time
tok = open(sys.argv[1]).read()
partes = tok.split(".")
if len(partes) != 3:
    sys.exit("a área de transferência não tem um JWT (passo 1)")
corpo = json.loads(base64.urlsafe_b64decode(partes[1] + "=" * (-len(partes[1]) % 4)))
iss = str(corpo.get("iss") or "").rstrip("/")
if iss != sys.argv[2] + "/auth/v1":
    sys.exit(f"o token é de outro emissor ({iss or 'sem iss'}), não do Supabase da VOLC")
if float(corpo.get("exp") or 0) <= time.time() + 60:
    sys.exit("a sessão vence em menos de 1 minuto (ou já venceu): entre de novo e copie outra vez")
if corpo.get("role") != "authenticated":
    sys.exit("o token não é de sessão de usuário (role != authenticated)")
print("sessão: emissor e validade conferidos")
PY
printf 'Authorization: Bearer %s\n' "$(cat "$COFRE/token")" > "$CAB"; chmod 600 "$CAB"; rm -f "$COFRE/token"

# ── 2. o backend: porta livre, e é o NOSSO processo que escuta ──────────────
PORTA="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"
set -a; . "$RAIZ/backend/.env"; set +a
unset FORGE_PERMITIR_ESCRITA
[ "${SUPABASE_URL%/}" = "$AUTORIDADE" ] || { echo "backend/.env não aponta para $AUTORIDADE"; exit 2; }
( cd "$RAIZ/backend" && exec env PYTHONPATH="$RAIZ:$RAIZ/backend" .venv/bin/python -m uvicorn app.main:app \
    --host 127.0.0.1 --port "$PORTA" --log-level warning ) > "$SAIDA/backend.log" 2>&1 &
PID=$!
for _ in $(seq 1 60); do curl -s -o /dev/null "http://127.0.0.1:$PORTA/health" && break; sleep 1; done
DONO="$(lsof -nP -iTCP:"$PORTA" -sTCP:LISTEN -t 2>/dev/null | head -1)"
[ "$DONO" = "$PID" ] || { echo "a porta $PORTA não é do backend iniciado (pid $PID, ouvinte ${DONO:-nenhum})"; exit 2; }
curl -s "http://127.0.0.1:$PORTA/health" | python3 -c '
import json,sys; h=json.load(sys.stdin)
assert h.get("service")=="pautador-pro" and h.get("supabase") is True, h
print("backend:", h["service"], h["version"], "status", h["status"])'

# ── 3. as rotas, com o HTTP esperado de cada uma ────────────────────────────
chamar() {  # nome esperado método rota [corpo]
  local nome=$1 esperado=$2 metodo=$3 rota=$4 corpo=${5:-} codigo
  if [ -n "$corpo" ]; then
    codigo=$(curl -s -o "$SAIDA/$nome.json" -w '%{http_code}' -X "$metodo" -H @"$CAB" \
      -H 'Content-Type: application/json' --data @"$corpo" "http://127.0.0.1:$PORTA$rota")
  else
    codigo=$(curl -s -o "$SAIDA/$nome.json" -w '%{http_code}' -X "$metodo" -H @"$CAB" "http://127.0.0.1:$PORTA$rota")
  fi
  if [ "$codigo" != "$esperado" ]; then
    echo "FALHA: $nome ($metodo $rota) respondeu HTTP $codigo, esperado $esperado — ver $SAIDA/$nome.json"
    exit 3
  fi
  echo "$nome → HTTP $codigo"
}
codigo=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORTA/api/trafego/trava")
[ "$codigo" = 401 ] || { echo "FALHA: sem sessão deveria ser 401, veio $codigo"; exit 3; }
echo "sem_sessao → HTTP 401"
chamar trava 200 GET /api/trafego/trava
chamar escopo 200 GET /api/trafego/escopo
chamar cockpit 200 GET "/api/trafego/candidatos/106?run_id=28"
chamar copy 200 GET "/api/trafego/copy/106?run_id=28"
chamar conjunto 200 GET /api/pautador/opportunities/106/conjunto-pago
chamar provar_search 200 POST /api/trafego/provar "$PEDIDO"
python3 - "$SAIDA" <<'PY'
import json, sys
d = sys.argv[1]
t = json.load(open(f"{d}/trava.json"))
p = json.load(open(f"{d}/provar_search.json"))
pr = p.get("preparo") or {}
print("trava: escrita_permitida=%s" % t.get("escrita_permitida"))
print("provar SEARCH: aprovado=%s ops=%s selo_retido=%s destino=%s" % (
    pr.get("aprovado"), pr.get("n_operacoes"), bool(pr.get("selo_retido")),
    ((p.get("destino") or {}).get("leitura_ao_vivo") or {}).get("detalhe") or (p.get("destino") or {}).get("veredito")))
PY
echo "respostas em $SAIDA (nenhuma contém o token)"
