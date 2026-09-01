#!/usr/bin/env bash
# A costura: os documentos que o JavaScript do workflow monta, entregues à RPC
# v12_04 DE VERDADE, num Postgres descartável.
#
# ## Por que esta prova existe separada
#
# `provar-ciclo-v12_04.sh` prova o banco contra documentos escritos à mão.
# `simular_gads_ledger_v12.mjs` prova o JavaScript contra um dublê de banco. As
# duas podem passar enquanto os dois artefatos discordam no meio — o fluxo
# manda `custo_micros` e a RPC espera `cost_micros`, e ninguém percebe até a
# produção. Aqui o dublê do banco some.
#
# Google Ads continua dublê: nenhuma chamada real, nenhuma credencial, zero rede
# externa. O único destino é o container efêmero.
set -euo pipefail

command -v docker >/dev/null || { echo "falta docker no PATH"; exit 2; }
command -v node >/dev/null || { echo "falta node no PATH"; exit 2; }

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
IMAGEM="${VOLC_PG_IMAGE:-postgres:16-alpine}"
C="volc-e2e-gads-$$"

limpar() { docker rm -f "$C" >/dev/null 2>&1 || true; }
trap limpar EXIT

echo "cluster descartável: container $C ($IMAGEM)"
docker run --rm -d --name "$C" \
  -e POSTGRES_PASSWORD=descartavel -e POSTGRES_HOST_AUTH_METHOD=trust \
  "$IMAGEM" >/dev/null

pronto=0
for _ in $(seq 1 60); do
  if docker exec "$C" pg_isready -U postgres -q >/dev/null 2>&1; then pronto=1; break; fi
  sleep 1
done
[ "$pronto" = 1 ] || { echo "o cluster descartável não subiu"; exit 2; }

f() { docker exec -i "$C" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -f - >/dev/null; }
q() { docker exec -i "$C" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -At -c "$1"; }

q "create role anon nologin; create role authenticated nologin;" >/dev/null
q "create role service_role nologin bypassrls;" >/dev/null
q "grant usage on schema public to anon, authenticated, service_role;" >/dev/null

f < "$RAIZ/supabase/migrations/v9_01_trafego_inventario.sql"
f < "$RAIZ/supabase/migrations/v12_04_gads_fato_canonico_dia.sql"

# A identidade VOLC que o fluxo lê do inventário precisa existir de verdade: a
# FK do fato aponta para `trafego_campanha`, e um id inventado seria recusado.
q "insert into public.trafego_campanha (volc_campaign_id, customer_id, campaign_id, criada_por)
   values ('gads-8017851692-24155134757','8017851692','24155134757','prova-ponta-a-ponta')" >/dev/null

echo
node "$RAIZ/scripts/simular_gads_ledger_v12.mjs" --rpc=psql --container="$C"
