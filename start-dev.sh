#!/usr/bin/env bash
#
# start-dev.sh — sobe o ambiente de desenvolvimento local do VOLC O.S.
#
#   ./start-dev.sh                 front (Vite) + api (Express) + backend Pautador (FastAPI)
#   ./start-dev.sh --skip-backend  só front + api (sem o Python)
#   ./start-dev.sh --stop          mata o que estiver ocupando as portas
#   ./start-dev.sh --permitir-escrita
#                                  ⚠️ ABRE A TRAVA DE ESCRITA do Google Ads.
#                                  Sem esta flag, `/subir` prova o payload e
#                                  recusa criar — que é o padrão e o certo.
#
# Portas: front 8080  ·  api Node 3001  ·  backend Pautador 8010
# O Vite faz proxy de /api e /health -> Express (3001), que fala com o Supabase
# com a service_role de .env.server. O frontend do Pautador Pro fala direto com
# o backend FastAPI (8010) via VITE_PAUTADOR_API_URL.
#
set -euo pipefail
cd "$(dirname "$0")"
REPO_ROOT="$PWD"

FRONT_PORT="${FRONT_PORT:-8080}"
API_PORT="${API_PORT:-3001}"
PAUTADOR_PORT="${PAUTADOR_PORT:-8010}"
export FRONT_PORT API_PORT
export SERVER_PORT="$API_PORT"   # server/index.js usa SERVER_PORT

SKIP_BACKEND=0

libera_porta() {
  local p="$1" pid
  pid=$(lsof -ti "tcp:$p" 2>/dev/null || true)
  if [ -n "$pid" ]; then kill $pid 2>/dev/null || true; sleep 1; echo "  porta $p liberada (pid $pid)"; fi
}

# ⚠️ A TRAVA DE ESCRITA — o segundo fator, e ele é humano de propósito.
#
# `gads/modo.py` exige DOIS fatores para escrever no Google Ads: `destravar()`
# no código (que o `/subir` já chama, com o motivo que o operador digita) e
# esta variável no ambiente. Um sozinho não basta.
#
# A flag existe para que abrir a trava seja um ato DELIBERADO e visível na
# linha de comando — não algo que ficou ligado num `.env` e ninguém lembra.
# Ela não sobrevive ao próximo boot: reiniciar sem a flag fecha a trava.
PERMITIR_ESCRITA=0
for arg in "$@"; do
  if [ "$arg" = "--permitir-escrita" ]; then PERMITIR_ESCRITA=1; fi
done
if [ "$PERMITIR_ESCRITA" -eq 1 ]; then
  export FORGE_PERMITIR_ESCRITA=1
  echo ""
  echo "  ⚠️  TRAVA DE ESCRITA ABERTA"
  echo "     O /subir vai CRIAR campanha de verdade na conta do Google Ads."
  echo "     Ela nasce PAUSADA, mas persiste e aparece na conta."
  echo "     Feche reiniciando sem --permitir-escrita."
  echo ""
fi

# --stop: encerra tudo e sai
if [ "${1:-}" = "--stop" ]; then
  echo "Encerrando dev..."
  libera_porta "$FRONT_PORT"; libera_porta "$API_PORT"; libera_porta "$PAUTADOR_PORT"
  exit 0
fi
[ "${1:-}" = "--skip-backend" ] && SKIP_BACKEND=1

# Pré-condições
if [ ! -f .env.server ]; then
  echo "⚠️  .env.server não encontrado (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY). Veja .env.server.example."
  exit 1
fi
python3 scripts/verificar_autoridade_supabase.py
[ -d node_modules ] || { echo "node_modules ausente — npm ci..."; npm ci; }

# Backend Pautador: só sobe se o venv existir
RUN_BACKEND=0
if [ "$SKIP_BACKEND" -eq 0 ]; then
  if [ -x backend/.venv/bin/uvicorn ]; then
    RUN_BACKEND=1
  else
    echo "ℹ️  backend/.venv não encontrado — subindo SEM o Pautador Pro."
    echo "    Para habilitar:  cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt"
  fi
fi

# Libera portas de execuções anteriores
libera_porta "$FRONT_PORT"; libera_porta "$API_PORT"
[ "$RUN_BACKEND" -eq 1 ] && libera_porta "$PAUTADOR_PORT"

pids=()
cleanup() {
  echo; echo "Encerrando serviços..."
  for pid in "${pids[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  exit 0
}
trap cleanup INT TERM

echo "▶ API      → http://localhost:$API_PORT   (server/index.js → Supabase)"
node server/index.js & pids+=($!)

if [ "$RUN_BACKEND" -eq 1 ]; then
  echo "▶ Pautador → http://localhost:$PAUTADOR_PORT (backend FastAPI, mock/live)"
  # ⚠️ `--reload-dir ../volc_ads` NÃO é redundante.
  #
  # Medido em 19/08/2026: com apenas `--reload-dir app`, um conserto em
  # `volc_ads/copy/encomendar.py` ficou invisível para o backend em execução —
  # a rota continuou estourando com um erro já corrigido no disco, e o operador
  # reiniciou achando que tinha pegado. O engine mora fora de `backend/app`,
  # mas é chamado por ele; vigiar só um dos dois produz "consertei e não mudou
  # nada", que é o pior tipo de falha para depurar.
  (
    cd backend
    # `app` vive neste diretório, mas o engine `volc_ads` é um pacote irmão na
    # raiz do repositório. Declarar a raiz torna o boot reproduzível fora de um
    # shell que por acaso já tenha o projeto no PYTHONPATH.
    export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
    exec .venv/bin/uvicorn app.main:app --reload \
      --reload-dir app --reload-dir ../volc_ads --port "$PAUTADOR_PORT"
  ) & pids+=($!)
fi

echo "▶ Front    → http://localhost:$FRONT_PORT (Vite, hot-reload)"
npm run dev & pids+=($!)

echo
echo "✅ Ambiente no ar. Abra  http://localhost:$FRONT_PORT  no navegador."
echo "   Ctrl-C encerra todos os processos."
wait
