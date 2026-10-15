#!/usr/bin/env bash
# =============================================================================
# scripts/aplicar-incidente-anon-w4.sh — aplica o pacote do incidente anon (W4)
# no Supabase oficial. NÃO FOI EXECUTADO. Só roda com autorização nominal do
# Tarcísio, numa janela combinada. Mesmo protocolo de
# scripts/aplicar-migrations-gads-20261008.sh: SHA-256 conferido, preflight,
# backup antes, cada arquivo na própria transação com ON_ERROR_STOP, postflight
# por sonda, recarga do PostgREST, recibo local.
#
# Uso:  scripts/aplicar-incidente-anon-w4.sh --so-checar   (preflight read-only)
#       scripts/aplicar-incidente-anon-w4.sh --passo1      (v19_00 v8_03 v19_01 v8_05 v19_02)
#       scripts/aplicar-incidente-anon-w4.sh --passo2      (v8_06; só com o frontend novo no ar)
#       scripts/aplicar-incidente-anon-w4.sh --rollback    (v19_99; devolve o estado inseguro)
# =============================================================================
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
MIG="$RAIZ/supabase/migrations"
SSH=(ssh -i "$HOME/.ssh/volc_hetzner_claude_ed25519" -o BatchMode=yes -o ConnectTimeout=10 root@178.156.196.149)
# supabase_admin por TCP local do container (pg_hba da imagem: trust em 127.0.0.1;
# o preflight P0 confirma que a sessão é superusuário antes de qualquer escrita).
SA="docker exec -i supabase-db psql -h 127.0.0.1 -U supabase_admin -d postgres -X -v ON_ERROR_STOP=1"
PG="docker exec -i supabase-db psql -U postgres -d postgres -X -v ON_ERROR_STOP=1"
CARIMBO="$(date +%Y%m%d-%H%M%S)"
RECIBO="$RAIZ/docs/closure/incidente-anon-w4/RECEIPT-$CARIMBO.txt"
H=/Users/mac/Desktop/VOLC-OS-CAMPAIGN/handoffs/freedom-lab-20261015

sha_esperado() {   # bash 3.2 do macOS: sem array associativo
  case "$1" in
    v19_00_users_gatilho_papel_real)       echo 115b5aee43010fa5e6bcd5ea458fc0725d5a299774e86c72a0cea3635f4d0a67 ;;
    v8_03_users_rls_policies)              echo e7af8372de3b25ee9811c2f0302052d7546f492e4261be72b2aded3bdc6b84ec ;;
    v19_01_anon_fecha_public)              echo 55790e5efa52ae7781c8ac05b5798ea482e6a353a1db1d40129eefa60852b7c4 ;;
    v8_05_users_safe_view)                 echo 7fb3d2de616404bc3c68f8aee8e2f70b9525bad102f2a17c885b4c54a5434f68 ;;
    v19_02_default_acl_public_sem_anon)    echo 3f2f16fef7c7245f0b8d444c5fed7c8d5629f1dc6ad88d47dde2bfae049d46bb ;;
    v8_06_users_sensitive_columns_revoke)  echo 0010e0874cfe518218eb483223fa5d42b00e40f3138f203b5ca0423efa381554 ;;
    v19_99_rollback)                       echo 21eb455080b946fc5016f71eacbf59aecafbddfdb35eeedf7f87b6cbb6e3e48f ;;
  esac
}
mkdir -p "$(dirname "$RECIBO")"
log() { echo "$*" | tee -a "$RECIBO"; }
conferir() { local real; real="$(shasum -a 256 "$MIG/$1.sql" | cut -d' ' -f1)"
  [[ "$real" == "$(sha_esperado "$1")" ]] || { log "SHA DIVERGE: $1 ($real)"; exit 1; }; log "sha ok  $1  $real"; }
aplicar() { # aplicar <papel> <migration>
  local cmd="$SA"; [[ "$1" == postgres ]] && cmd="$PG"
  conferir "$2"; log "aplica  $2 como $1"
  "${SSH[@]}" "$cmd" < "$MIG/$2.sql" >>"$RECIBO" 2>&1 \
    || { log "FALHOU $2 — transação própria, nada parcial. Backup: ${DUMP:-sem backup}"; exit 1; }
}
sonda() { "${SSH[@]}" "$PG -P pager=off" < "$H/B-sonda-producao.sql" > "$1.out" 2> "$1.err"
  log "sonda   $1 · anon VE_LINHAS=$(grep -c 'S8|anon|.*|VE_LINHAS' "$1.err")"; }

log "== preflight $CARIMBO"
"${SSH[@]}" "$SA -P pager=off" < "$RAIZ/scripts/preflight-incidente-anon-w4.sql" | tee -a "$RECIBO"
[[ "${1:-}" == "--so-checar" ]] && { log "só preflight: nada aplicado"; exit 0; }
read -r -p "Preflight lido e sem BLOQUEIA=t? digite APLICAR: " ok; [[ "$ok" == "APLICAR" ]] || exit 1

log "== backup"
DUMP="/root/backups/pre-incidente-anon-w4-$CARIMBO.dump"
"${SSH[@]}" "docker exec supabase-db pg_dump -U postgres -Fc -n public -n app_auth postgres > $DUMP && ls -la $DUMP" | tee -a "$RECIBO"
"${SSH[@]}" "test -s $DUMP" || { log "backup vazio: abortado"; exit 1; }
sonda "$(dirname "$RECIBO")/sonda-antes-$CARIMBO"

case "${1:-}" in
  --passo1)
    aplicar supabase_admin v19_00_users_gatilho_papel_real
    aplicar supabase_admin v8_03_users_rls_policies
    aplicar supabase_admin v19_01_anon_fecha_public
    aplicar postgres       v8_05_users_safe_view
    aplicar supabase_admin v19_02_default_acl_public_sem_anon ;;
  --passo2)
    aplicar supabase_admin v8_06_users_sensitive_columns_revoke ;;
  --rollback)
    aplicar supabase_admin v19_99_rollback ;;
  *) log "uso: --so-checar | --passo1 | --passo2 | --rollback"; exit 2 ;;
esac
"${SSH[@]}" "$PG -c \"NOTIFY pgrst, 'reload schema'\"" >>"$RECIBO" 2>&1
sonda "$(dirname "$RECIBO")/sonda-depois-$CARIMBO"
log "== fim · recibo: $RECIBO · backup no servidor: $DUMP"
log "   Esperado após --passo1: anon VE_LINHAS=0; S5 sem linhas de anon em public."
