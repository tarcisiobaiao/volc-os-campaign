#!/bin/sh
# uso: verificar.sh <desde ISO>  — roda verificar_pos_cutover.sql read-only no Postgres oficial
D="$1"; S="$(dirname "$0")/verificar_pos_cutover.sql"
sed "s/:'desde'/'$D'::timestamptz/g" "$S" | ssh -o BatchMode=yes -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
  "docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=30000' supabase-db psql -U postgres -X -q -A -F ' | ' -P footer=off -t"
