#!/usr/bin/env bash
# migracao-protocolo.sh — o protocolo da casa para QUALQUER par migration/rollback,
# com o ledger volc_ops.migracao_evento (v20_01) como registro.
#
# Generaliza scripts/aplicar-migrations-gads-20261008.sh, que fixava três
# arquivos e três sha256 no código. O protocolo é o mesmo:
#   sha256 conferido antes de conectar · estado lido antes · backup (produção) ·
#   o arquivo com a própria transação e ON_ERROR_STOP · releitura depois ·
#   recarga do PostgREST (produção) · recibo local.
# O que muda: a aprovação (sha256 + aprovador) entra por argumento, e o registro
# no ledger entra NA MESMA TRANSAÇÃO da migration — ou os dois acontecem, ou
# nenhum. O ledger tem guardas próprias (gatilho), então reaplicar ou reverter
# com hash divergente é recusado pelo banco mesmo se alguém pular este script.
#
# Uso:
#   migracao-protocolo.sh aplicar  --alvo ALVO --migration ARQ --sha SHA256 --aprovador NOME
#                                  [--rollback ARQ --sha-rollback SHA256] [--aprovado-em AAAA-MM-DD]
#                                  [--recibo-dir DIR] [--cria-ledger]
#   migracao-protocolo.sh reverter --alvo ALVO --versao NOME --rollback ARQ --sha-rollback SHA256
#                                  --aprovador NOME [--recibo-dir DIR] [--remove-ledger]
#   migracao-protocolo.sh estado   --alvo ALVO [--versao NOME]
#
#   ALVO = docker:<container>  Postgres descartável local (laboratório)
#        | producao            Supabase oficial via ssh — exige
#                              VOLC_AUTORIZA_PRODUCAO="<versao>@<sha256>" idêntico
#                              ao que se pede, e faz pg_dump antes. Nunca roda sozinho.
#
# Saída: 0 ok · 2 uso · 10 sha256 divergente · 11 já aplicada · 12 não aplicada ·
#        13 ledger ausente · 14 a migration falhou (transação desfeita) ·
#        15 nada efetivado · 16 produção sem autorização · 17 backup falhou
#
# Limite declarado: a migration roda dentro de UMA transação aberta aqui. Arquivo
# com COMMIT no meio e comandos depois dele, ou comando que não roda em
# transação (CREATE INDEX CONCURRENTLY, VACUUM), fica fora da atomicidade — o
# segundo caso falha fechado (código 14), o primeiro é responsabilidade do arquivo.
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CMD="${1:-}"; shift || true

ALVO= MIG= SHA= ROLL= SHA_R= APROV= APROV_EM= VERSAO= RECIBO_DIR= CRIA=0 REMOVE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --alvo) ALVO="$2"; shift 2 ;;
    --migration) MIG="$2"; shift 2 ;;
    --sha) SHA="$2"; shift 2 ;;
    --rollback) ROLL="$2"; shift 2 ;;
    --sha-rollback) SHA_R="$2"; shift 2 ;;
    --aprovador) APROV="$2"; shift 2 ;;
    --aprovado-em) APROV_EM="$2"; shift 2 ;;
    --versao) VERSAO="$2"; shift 2 ;;
    --recibo-dir) RECIBO_DIR="$2"; shift 2 ;;
    --cria-ledger) CRIA=1; shift ;;
    --remove-ledger) REMOVE=1; shift ;;
    *) echo "argumento desconhecido: $1" >&2; exit 2 ;;
  esac
done

uso() { sed -n '17,29p' "${BASH_SOURCE[0]}" >&2; exit 2; }
[ -n "$CMD" ] && [ -n "$ALVO" ] || uso

# ── alvo ────────────────────────────────────────────────────────────────────
case "$ALVO" in
  docker:?*)
    CONT="${ALVO#docker:}"
    # só o banco descartável do Freedom Lab: rótulo do lab e sem rede (como exigir_lab)
    [ -n "$(docker ps -q --filter "name=^${CONT}$" --filter label=volc.freedom-lab=1)" ] && \
      [ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$CONT" 2>/dev/null)" = none ] || \
      { echo "alvo docker:$CONT não é um container do Freedom Lab (rótulo volc.freedom-lab=1, sem rede): recusado" >&2; exit 2; }
    psql_alvo() { docker exec -i "$CONT" psql -U postgres -d postgres -X -q -v ON_ERROR_STOP=1 "$@"; }
    ;;
  producao)
    SSH=(ssh -i "$HOME/.ssh/volc_hetzner_claude_ed25519" -o BatchMode=yes -o ConnectTimeout=10 root@178.156.196.149)
    psql_alvo() { "${SSH[@]}" "docker exec -i supabase-db psql -U postgres -d postgres -X -q -v ON_ERROR_STOP=1 $*"; }
    ;;
  *) echo "alvo inválido: $ALVO (docker:<container> | producao)" >&2; exit 2 ;;
esac

q()   { printf '%s\n' "$1" | psql_alvo -At; }
lit() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/''/g")"; }
sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
rel() { local a; a="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
        case "$a" in "$RAIZ"/*) echo "${a#"$RAIZ"/}" ;; *) basename "$1" ;; esac; }
hex64() { printf '%s' "$1" | grep -Eq '^[0-9a-f]{64}$'; }

CARIMBO="$(date +%Y%m%d-%H%M%S)"
if [ -z "$RECIBO_DIR" ]; then
  if [ "$ALVO" = producao ]; then RECIBO_DIR="$RAIZ/docs/closure/migracoes-ledger"; else RECIBO_DIR="${TMPDIR:-/tmp}"; fi
fi
mkdir -p "$RECIBO_DIR"
RECIBO=
log() { echo "$*"; [ -n "$RECIBO" ] && echo "$*" >> "$RECIBO"; return 0; }

ledger_existe() { [ "$(q "select to_regclass('volc_ops.migracao_evento') is not null")" = t ]; }
fingerprint()   { ledger_existe && q "select md5 from volc_ops.fingerprint_schema() where categoria='_TOTAL'" || echo "(sem ledger)"; }
estado_de()     { q "select estado || '|' || sha256 || '|' || coalesce(rollback_sha256,'') from volc_ops.migracao_estado where versao = $(lit "$1")"; }

autoriza_producao() { # $1=versao $2=sha
  [ "$ALVO" = producao ] || return 0
  if [ "${VOLC_AUTORIZA_PRODUCAO:-}" != "$1@$2" ]; then
    log "PRODUÇÃO SEM AUTORIZAÇÃO: defina VOLC_AUTORIZA_PRODUCAO=\"$1@$2\" (autorização nominal do operador)"
    exit 16
  fi
  log "== backup"
  local dump="/root/backups/pre-$1-$CARIMBO.dump"
  "${SSH[@]}" "docker exec supabase-db pg_dump -U postgres -Fc -n public -n app_auth -n volc_ops postgres > $dump && test -s $dump && ls -la $dump" >> "$RECIBO" 2>&1 \
    || { log "backup falhou: abortado, nada aplicado"; exit 17; }
  log "backup  $dump"
}

executar() { # $1=arquivo SQL, $2=prefixo SQL (dentro da transação)
  { printf 'BEGIN;\n%s\n' "$2"; cat "$1"; printf '\n;COMMIT;\n'; } | psql_alvo >> "$RECIBO" 2>&1
}

case "$CMD" in
# ════════════════════════════════════════════════════════════════════════════
aplicar)
  [ -n "$MIG" ] && [ -n "$SHA" ] && [ -n "$APROV" ] || uso
  [ -f "$MIG" ] || { echo "arquivo ausente: $MIG" >&2; exit 2; }
  hex64 "$SHA" || { echo "--sha não é sha256 hex" >&2; exit 2; }
  if [ -n "$ROLL$SHA_R" ]; then
    [ -f "$ROLL" ] && hex64 "$SHA_R" || { echo "--rollback e --sha-rollback andam juntos" >&2; exit 2; }
  fi
  VERSAO="$(basename "$MIG" .sql)"
  RECIBO="$RECIBO_DIR/RECEIPT-$VERSAO-aplicar-$CARIMBO.txt"
  log "== preflight $CARIMBO · aplicar $VERSAO · alvo $ALVO · aprovador $APROV"

  real="$(sha "$MIG")"
  [ "$real" = "$SHA" ] || { log "SHA DIVERGE: $VERSAO arquivo=$real aprovado=$SHA — recusado, nada conectado"; exit 10; }
  log "sha ok  $VERSAO  $real"
  if [ -n "$ROLL" ]; then
    real_r="$(sha "$ROLL")"
    [ "$real_r" = "$SHA_R" ] || { log "SHA DIVERGE: rollback $(basename "$ROLL") arquivo=$real_r aprovado=$SHA_R — recusado"; exit 10; }
    log "sha ok  $(basename "$ROLL")  $real_r"
  fi

  if [ $CRIA = 1 ]; then
    ledger_existe && { log "ledger já existe: --cria-ledger recusado"; exit 11; }
  else
    ledger_existe || { log "LEDGER AUSENTE: aplique v20_01 (--cria-ledger) antes"; exit 13; }
    est="$(estado_de "$VERSAO")"
    log "estado  ${est:-(nunca registrada)}"
    case "$est" in aplicada\|*) log "JÁ APLICADA: $VERSAO — reaplicação recusada"; exit 11 ;; esac
    case "$est" in revertida\|*)
      ant="$(echo "$est" | cut -d'|' -f2)"
      [ "$ant" = "$SHA" ] || { log "SHA DIVERGE do histórico: $VERSAO foi registrada com $ant — recusado (use um nome novo)"; exit 10; } ;;
    esac
  fi
  FP_ANTES="$(fingerprint)"; log "fingerprint antes  $FP_ANTES"
  autoriza_producao "$VERSAO" "$SHA"

  prefixo="SELECT set_config('volc_ops.aprovador', $(lit "$APROV"), true), set_config('volc_ops.aprovado_em', $(lit "$APROV_EM"), true);"
  if [ $CRIA = 0 ]; then
    if [ -n "$ROLL" ]; then rarq="$(lit "$(rel "$ROLL")")"; rsha="$(lit "$SHA_R")"; else rarq=NULL; rsha=NULL; fi
    prefixo="$prefixo
INSERT INTO volc_ops.migracao_evento (versao, operacao, arquivo, sha256, rollback_arquivo, rollback_sha256, aprovador, aprovado_em, fingerprint, evidencia)
VALUES ($(lit "$VERSAO"), 'aplicar', $(lit "$(rel "$MIG")"), $(lit "$SHA"), $rarq, $rsha, $(lit "$APROV"),
        nullif($(lit "$APROV_EM"), '')::date,
        (SELECT md5 FROM volc_ops.fingerprint_schema() WHERE categoria = '_TOTAL'),
        $(lit "recibo $(basename "$RECIBO")"));"
  fi
  log "aplica  $VERSAO"
  executar "$MIG" "$prefixo" || { log "FALHOU $VERSAO — transação desfeita, ledger intacto"; tail -4 "$RECIBO" >&2; exit 14; }

  if [ $CRIA = 1 ]; then
    ledger_existe || { log "NADA EFETIVADO: ledger não existe após $VERSAO"; exit 15; }
  else
    est="$(estado_de "$VERSAO")"
    case "$est" in "aplicada|$SHA|"*) ;; *) log "NADA EFETIVADO: o arquivo terminou sem COMMIT (estado=${est:-nenhum})"; exit 15 ;; esac
  fi
  ;;
# ════════════════════════════════════════════════════════════════════════════
reverter)
  [ -n "$VERSAO" ] && [ -n "$ROLL" ] && [ -n "$SHA_R" ] && [ -n "$APROV" ] || uso
  [ -f "$ROLL" ] || { echo "arquivo ausente: $ROLL" >&2; exit 2; }
  hex64 "$SHA_R" || { echo "--sha-rollback não é sha256 hex" >&2; exit 2; }
  RECIBO="$RECIBO_DIR/RECEIPT-$VERSAO-reverter-$CARIMBO.txt"
  log "== preflight $CARIMBO · reverter $VERSAO · alvo $ALVO · aprovador $APROV"
  real_r="$(sha "$ROLL")"
  [ "$real_r" = "$SHA_R" ] || { log "SHA DIVERGE: rollback arquivo=$real_r aprovado=$SHA_R — recusado, nada conectado"; exit 10; }
  log "sha ok  $(basename "$ROLL")  $real_r"
  ledger_existe || { log "LEDGER AUSENTE"; exit 13; }
  if [ $REMOVE = 0 ]; then
    est="$(estado_de "$VERSAO")"
    log "estado  ${est:-(nunca registrada)}"
    case "$est" in aplicada\|*) ;; *) log "NÃO APLICADA: $VERSAO — reversão recusada"; exit 12 ;; esac
    reg="$(echo "$est" | cut -d'|' -f3)"
    [ -z "$reg" ] || [ "$reg" = "$SHA_R" ] || { log "SHA DIVERGE: o rollback aprovado na aplicação é $reg — recusado"; exit 10; }
  fi
  FP_ANTES="$(fingerprint)"; log "fingerprint antes  $FP_ANTES"
  autoriza_producao "$VERSAO" "$SHA_R"

  prefixo="SELECT set_config('volc_ops.aprovador', $(lit "$APROV"), true);"
  if [ $REMOVE = 0 ]; then
    prefixo="$prefixo
INSERT INTO volc_ops.migracao_evento (versao, operacao, arquivo, sha256, aprovador, aprovado_em, fingerprint, evidencia)
VALUES ($(lit "$VERSAO"), 'reverter', $(lit "$(rel "$ROLL")"), $(lit "$SHA_R"), $(lit "$APROV"),
        nullif($(lit "$APROV_EM"), '')::date,
        (SELECT md5 FROM volc_ops.fingerprint_schema() WHERE categoria = '_TOTAL'),
        $(lit "recibo $(basename "$RECIBO")"));"
  fi
  log "reverte $VERSAO"
  executar "$ROLL" "$prefixo" || { log "FALHOU rollback de $VERSAO — transação desfeita"; tail -4 "$RECIBO" >&2; exit 14; }
  if [ $REMOVE = 0 ]; then
    est="$(estado_de "$VERSAO")"
    case "$est" in revertida\|*) ;; *) log "NADA EFETIVADO: estado=${est:-nenhum}"; exit 15 ;; esac
  fi
  ;;
# ════════════════════════════════════════════════════════════════════════════
estado)
  ledger_existe || { echo "ledger ausente em $ALVO"; exit 13; }
  if [ -n "$VERSAO" ]; then estado_de "$VERSAO"
  else q "select versao || ' ' || estado || ' ' || sha256 || ' ' || aprovador from volc_ops.migracao_estado order by evento_id"; fi
  exit 0
  ;;
*) uso ;;
esac

log "== postflight"
FP_DEPOIS="$(fingerprint)"; log "fingerprint depois $FP_DEPOIS"
ledger_existe && q "select '  ' || id || ' ' || versao || ' ' || operacao || ' ' || left(sha256,12) || ' ' || aprovador from volc_ops.migracao_evento order by id desc limit 3" | tee -a "$RECIBO"
[ "$ALVO" = producao ] && q "NOTIFY pgrst, 'reload schema';" >/dev/null
log "== fim · recibo: $RECIBO"
exit 0
