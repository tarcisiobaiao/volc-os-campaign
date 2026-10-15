#!/usr/bin/env bash
# =============================================================================
# scripts/aplicar-incidente-anon-w4.sh — aplica o pacote do incidente anon (W4)
# no Supabase oficial. NÃO FOI EXECUTADO. Só roda com autorização nominal do
# Tarcísio (operação e hashes nomeados), numa janela combinada. Protocolo de
# scripts/aplicar-migrations-gads-20261008.sh: SHA-256 conferido, preflight,
# backup antes, cada arquivo na própria transação com ON_ERROR_STOP, verificação
# como anon de verdade antes e depois, recarga do PostgREST, recibo local.
#
# Uso:  --so-checar  preflight + verificação; só leitura, nunca supabase_admin
#       --passo1 --aprovador NOME --inventario ARQ --sha-inventario SHA256
#                    v19_00 v8_03 v19_01 v8_05 v19_02. Recusa sem inventário de
#                    consumidores da anon ASSINADO (modelo:
#                    docs/INCIDENTE-ANON-INVENTARIO.modelo.json) com o sha256 dado
#       --passo2 --aprovador NOME      v8_06 (só com o frontend novo no ar)
#       --rollback --aprovador NOME    v19_99 (estado inseguro; aborta se a ACL mudou depois)
#
# ORDEM COM O LEDGER (decisão do coordenador, 15/10): o pacote v19 vai ANTES do
# ledger v20 e FORA dele — v20 nunca foi aplicado em produção, e o protocolo v20
# roda como postgres dentro de BEGIN…COMMIT, enquanto os v19 exigem superusuário
# e têm transação própria. Para o ledger importar depois, este script grava um
# recibo JSON por execução (RECEIPT-*.json) com os campos de
# volc_ops.migracao_evento: versao, operacao, arquivo, sha256, rollback_*,
# aprovador, aprovado_em, fingerprint (md5 _TOTAL antes), evidencia — mais o
# fingerprint depois e o carimbo de tempo de cada arquivo.
#
# Cada ARQUIVO é atômico; o PASSO não é: se o 3º arquivo falhar, os dois
# primeiros ficam aplicados. O script para no arquivo que falhou e diz o que
# ficou; continue para frente ou rode --rollback (que tolera aplicação parcial).
# =============================================================================
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
MIG="$RAIZ/supabase/migrations"
SSH=(ssh -i "$HOME/.ssh/volc_hetzner_claude_ed25519" -o BatchMode=yes -o ConnectTimeout=10 root@178.156.196.149)
CONT=supabase-db; BACKUPS=/root/backups
# Ensaio do PRÓPRIO script no laboratório (nunca produção): W4_ALVO_LAB=<container
# do lab.sh, rótulo volc.freedom-lab=1, sem rede> troca o ssh por bash local.
if [[ -n "${W4_ALVO_LAB:-}" ]]; then
  [[ -n "$(docker ps -q --filter "name=^${W4_ALVO_LAB}$" --filter label=volc.freedom-lab=1)" ]] \
    && [[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$W4_ALVO_LAB")" == none ]] \
    || { echo "W4_ALVO_LAB precisa ser um container do lab.sh, sem rede"; exit 97; }
  SSH=(bash -c); CONT="$W4_ALVO_LAB"; BACKUPS=/tmp
fi
# Escrita: supabase_admin pelo TCP local do container. Cada migration tem guarda
# que aborta se a sessão não for superusuário.
SA="docker exec -i $CONT psql -h 127.0.0.1 -U supabase_admin -d postgres -X -v ON_ERROR_STOP=1"
PG="docker exec -i $CONT psql -U postgres -d postgres -X -v ON_ERROR_STOP=1"
# Preflight: a menor identidade de leitura que existe hoje, sem grant de escrita,
# com a sessão forçada read-only.
LEITURA="docker exec -i -e PGOPTIONS=-c\\ default_transaction_read_only=on $CONT psql -h 127.0.0.1 -U supabase_read_only_user -d postgres -X -q -A -t -F'|' -v ON_ERROR_STOP=1"
# Verificação como anon: postgres (membro de anon), sessão forçada read-only,
# BEGIN READ ONLY no arquivo. supabase_read_only_user não assume anon.
VERIFICA="docker exec -i -e PGOPTIONS=-c\\ default_transaction_read_only=on $CONT psql -U postgres -d postgres -X -q -A -t -F'|' -v ON_ERROR_STOP=1"
OP="${1:-}"; shift || true
APROV= INVENT= SHA_INV=
while [ $# -gt 0 ]; do
  case "$1" in
    --aprovador) APROV="$2"; shift 2 ;;
    --inventario) INVENT="$2"; shift 2 ;;
    --sha-inventario) SHA_INV="$2"; shift 2 ;;
    *) echo "argumento desconhecido: $1" >&2; exit 2 ;;
  esac
done
CARIMBO="$(date +%Y%m%d-%H%M%S)"
RECIBO="${W4_RECIBO_DIR:-$RAIZ/docs/closure/incidente-anon-w4}/RECEIPT-$CARIMBO.txt"
RECIBO_JSON="${RECIBO%.txt}.json"

sha_esperado() {   # bash 3.2 do macOS: sem array associativo
  case "$1" in
    v19_00_users_gatilho_papel_real)       echo 115b5aee43010fa5e6bcd5ea458fc0725d5a299774e86c72a0cea3635f4d0a67 ;;
    v8_03_users_rls_policies)              echo e7af8372de3b25ee9811c2f0302052d7546f492e4261be72b2aded3bdc6b84ec ;;
    v19_01_anon_fecha_public)              echo e7b0c9ba20fa96e7190a740d6f713fa8eac4cbd4b13a446d433c83378e4f858c ;;
    v8_05_users_safe_view)                 echo 7fb3d2de616404bc3c68f8aee8e2f70b9525bad102f2a17c885b4c54a5434f68 ;;
    v19_02_default_acl_public_sem_anon)    echo 8919245ed846060f690e4baa47d3c07d35caf65a6171f859f2b92f3b5b23b671 ;;
    v8_06_users_sensitive_columns_revoke)  echo 0010e0874cfe518218eb483223fa5d42b00e40f3138f203b5ca0423efa381554 ;;
    v19_99_rollback)                       echo 3abff0a814e1db384daaaa9181cbefb8865047ea98025393e4f4fe22293c8fdd ;;
    preflight-incidente-anon-w4)           echo 84892780f9d43e297c9843e03f41c7ae8cfef13f7b7fab7b2e7dbb9243bfd7ae ;;
    fingerprint_schema)                    echo 0f6c05509466e9bc92474465d4427cf5fe426a477d15fc50a31871317e30d2c7 ;;
    verificar-anon-w4)                     echo b05f011d36208836b7c1b6f97642597f30ef56e6dfc63edc8ecfc8f716dbfb23 ;;
  esac
}
mkdir -p "$(dirname "$RECIBO")"
log() { echo "$*" | tee -a "$RECIBO"; }
conferir() { local f="$1" real; real="$(shasum -a 256 "$f" | cut -d' ' -f1)"
  [[ "$real" == "$(sha_esperado "$(basename "$f" .sql)")" ]] || { log "SHA DIVERGE: $f ($real)"; exit 1; }
  log "sha ok  $(basename "$f")  $real"; }
APLICADOS=""
aplicar() { # aplicar <papel> <migration>
  local cmd="$SA" ini; [[ "$1" == postgres ]] && cmd="$PG"
  conferir "$MIG/$2.sql"; log "aplica  $2 como $1"; ini="$(date -u +%FT%TZ)"
  if ! "${SSH[@]}" "$cmd" < "$MIG/$2.sql" >>"$RECIBO" 2>&1; then
    log "FALHOU $2 (transação própria: este arquivo não deixou nada)."
    log "Já aplicados neste passo:${APLICADOS:- nenhum}. Backup: ${DUMP:-sem backup}"
    exit 1
  fi
  APLICADOS="$APLICADOS $2"
  if [[ "$OPERACAO_LEDGER" == reverter ]]; then
    # No ledger, "reverter" é por versão revertida, com o arquivo de rollback executado.
    local v; for v in v8_06_users_sensitive_columns_revoke v19_02_default_acl_public_sem_anon v8_05_users_safe_view \
                      v19_01_anon_fecha_public v8_03_users_rls_policies v19_00_users_gatilho_papel_real; do
      evento "$v" "$2.sql" "$(sha_esperado "$2")" "$ini" "$(date -u +%FT%TZ)"
    done
  else
    evento "$2" "$2.sql" "$(sha_esperado "$2")" "$ini" "$(date -u +%FT%TZ)"
  fi
}
# verificar <ABERTO|FECHADO>: mede como anon e exige o estado esperado.
verificar() {
  local saida v1 v2 v3 v4 estado
  conferir "$RAIZ/scripts/verificar-anon-w4.sql"
  saida="$("${SSH[@]}" "$VERIFICA" < "$RAIZ/scripts/verificar-anon-w4.sql")"
  printf '%s\n' "$saida" | sed 's/^/verifica /' | tee -a "$RECIBO"
  v1=$(printf '%s\n' "$saida" | awk -F'|' '$1=="V1"{print $3}')
  v2=$(printf '%s\n' "$saida" | awk -F'|' '$1=="V2"{print $3}')
  v3=$(printf '%s\n' "$saida" | awk -F'|' '$1=="V3"{print $3}')
  v4=$(printf '%s\n' "$saida" | awk -F'|' '$1=="V4"{print $3}')
  [[ "$v1" == 0 && "$v2" == 0 && "$v3" == 0 && "$v4" == 0 ]] && estado=FECHADO || estado=ABERTO
  [[ -n "$v1" && -n "$v4" ]] || estado=ILEGIVEL
  log "verifica anon: $estado (esperado: $1)"
  [[ "$estado" == "$1" ]] || { log "VERIFICAÇÃO NÃO BATE: esperado $1, medido $estado"; return 1; }
}

FP_SQL="$RAIZ/tools/freedom-lab/db/fingerprint_schema.sql"
fingerprint() { # md5 _TOTAL de public+app_auth, só leitura (mesma SQL do lab e da âncora 695e913a…)
  conferir "$FP_SQL" >/dev/null
  "${SSH[@]}" "$VERIFICA" < "$FP_SQL" | awk -F'|' '$1=="_TOTAL"{print $3}'; }
EVENTOS=""
evento() { # evento <versao> <arquivo> <sha> <inicio> <fim> — linha do recibo JSON
  EVENTOS="$EVENTOS${EVENTOS:+,}
    {\"versao\": \"$1\", \"operacao\": \"$OPERACAO_LEDGER\", \"arquivo\": \"supabase/migrations/$2\", \"sha256\": \"$3\",
     \"rollback_arquivo\": $ROLL_JSON, \"rollback_sha256\": $ROLL_SHA_JSON,
     \"aprovador\": \"$APROV\", \"aprovado_em\": \"$(date +%F)\", \"executado_por\": \"$EXECUTOR\",
     \"inicio\": \"$4\", \"fim\": \"$5\"}"; }
gravar_recibo_json() { # gravar_recibo_json <fp_antes> <fp_depois> <resultado>
  cat > "$RECIBO_JSON" <<JSON
{
  "pacote": "incidente-anon-w4", "operacao": "$OP", "resultado": "$3",
  "alvo": "${W4_ALVO_LAB:-producao}", "carimbo": "$CARIMBO",
  "fingerprint_antes": "$1", "fingerprint_depois": "$2",
  "fingerprint_sql": "tools/freedom-lab/db/fingerprint_schema.sql", "fingerprint_sql_sha256": "$(shasum -a 256 "$FP_SQL" | cut -d' ' -f1)",
  "inventario": "${INVENT:-}", "inventario_sha256": "${SHA_INV:-}",
  "backup": "${DUMP:-}", "recibo_texto": "$(basename "$RECIBO")",
  "eventos": [$EVENTOS
  ]
}
JSON
  log "recibo para o ledger: $RECIBO_JSON"; }

log "== preflight $CARIMBO"
conferir "$RAIZ/scripts/preflight-incidente-anon-w4.sql"
PRE="$("${SSH[@]}" "$LEITURA" < "$RAIZ/scripts/preflight-incidente-anon-w4.sql")"
printf '%s\n' "$PRE" | sed 's/^/preflight /' | tee -a "$RECIBO"
BLOQ="$(printf '%s\n' "$PRE" | awk -F'|' '$3=="t"{print $1}')"

case "$OP" in
  --so-checar)
    verificar ABERTO || true
    [[ -z "$BLOQ" ]] && log "preflight sem bloqueio" || log "BLOQUEIOS: $BLOQ"
    log "só leitura: nada aplicado"; exit 0 ;;
  --passo1)
    [[ -z "$BLOQ" ]] || { log "RECUSADO: preflight bloqueia em: $BLOQ"; exit 1; }
    # Inventário de consumidores da anon assinado — sem ele, o passo 1 não sai.
    [[ -n "$INVENT" && -f "$INVENT" && -n "$SHA_INV" ]] || { log "RECUSADO: falta --inventario ARQ --sha-inventario SHA256"; exit 1; }
    [[ "$(shasum -a 256 "$INVENT" | cut -d' ' -f1)" == "$SHA_INV" ]] || { log "RECUSADO: sha256 do inventário diverge do informado"; exit 1; }
    python3 -I - "$INVENT" <<'PY' | tee -a "$RECIBO" || { log "RECUSADO: inventário incompleto ou não assinado"; exit 1; }
import json, sys
d = json.load(open(sys.argv[1])); val = set(d.get("decisoes_validas", []))
falta = [c["id"] for c in d.get("consumidores", [])
         if not c.get("confirmado_em_producao") or not c.get("evidencia") or c.get("decisao") not in val]
erros = []
if not d.get("consumidores"): erros.append("sem consumidores")
if falta: erros.append("sem confirmação/evidência/decisão: " + ", ".join(falta))
if not str(d.get("assinado_por", "")).strip() or not str(d.get("assinado_em", "")).strip(): erros.append("sem assinatura")
if d.get("bloqueia_passo1") is not False: erros.append("bloqueia_passo1 não é false")
if erros: print("inventario RECUSADO: " + "; ".join(erros)); sys.exit(1)
print("inventario ok: %d consumidores, assinado por %s em %s" % (len(d["consumidores"]), d["assinado_por"], d["assinado_em"]))
PY
    # O instrumento precisa enxergar o buraco antes; senão o "FECHADO" de depois não prova nada.
    verificar ABERTO || { log "RECUSADO: a verificação não vê o buraco antes de aplicar"; exit 1; } ;;
  --passo2|--rollback) ;;
  *) log "uso: --so-checar | --passo1 | --passo2 | --rollback"; exit 2 ;;
esac
[[ -n "$APROV" ]] || { log "RECUSADO: falta --aprovador NOME (quem autorizou esta operação com estes hashes)"; exit 1; }
read -r -p "Operação $OP com os hashes acima, aprovada por $APROV? digite APLICAR: " ok; [[ "$ok" == "APLICAR" ]] || exit 1

log "== backup"
DUMP="$BACKUPS/pre-incidente-anon-w4-$CARIMBO.dump"
"${SSH[@]}" "docker exec $CONT pg_dump -U postgres -Fc -n public -n app_auth postgres > $DUMP && ls -la $DUMP" | tee -a "$RECIBO"
"${SSH[@]}" "test -s $DUMP" || { log "backup vazio: abortado"; exit 1; }

EXECUTOR="supabase_admin@$(hostname -s)"
FP_ANTES="$(fingerprint)"; log "fingerprint antes: $FP_ANTES"
ROLL_JSON='"supabase/migrations/v19_99_rollback.sql"'; ROLL_SHA_JSON="\"$(sha_esperado v19_99_rollback)\""
OPERACAO_LEDGER=aplicar
trap 'gravar_recibo_json "$FP_ANTES" "$(fingerprint 2>/dev/null || echo ?)" falhou' ERR
case "$OP" in
  --passo1)
    aplicar supabase_admin v19_00_users_gatilho_papel_real
    aplicar supabase_admin v8_03_users_rls_policies
    aplicar supabase_admin v19_01_anon_fecha_public
    aplicar postgres       v8_05_users_safe_view
    aplicar supabase_admin v19_02_default_acl_public_sem_anon ;;
  --passo2)
    aplicar supabase_admin v8_06_users_sensitive_columns_revoke ;;
  --rollback)
    OPERACAO_LEDGER=reverter; ROLL_JSON=null; ROLL_SHA_JSON=null
    aplicar supabase_admin v19_99_rollback ;;
esac
trap - ERR
"${SSH[@]}" "$PG -c \"NOTIFY pgrst, 'reload schema'\"" >>"$RECIBO" 2>&1
case "$OP" in
  --passo1|--passo2) verificar FECHADO || { log "ALERTA: anon ainda alcança public — investigar já"; gravar_recibo_json "$FP_ANTES" "$(fingerprint)" "aplicado_mas_anon_aberto"; exit 1; } ;;
  --rollback)        verificar ABERTO  || log "nota: rollback não reabriu anon como esperado" ;;
esac
FP_DEPOIS="$(fingerprint)"; log "fingerprint depois: $FP_DEPOIS"
gravar_recibo_json "$FP_ANTES" "$FP_DEPOIS" ok
log "== fim · recibo: $RECIBO · backup no servidor: $DUMP"
