#!/usr/bin/env bash
# =============================================================================
# tools/freedom-lab/lab.sh — banco descartável do Freedom Lab.
#
#   criar     sobe supabase/postgres:15.8.1.085 (mesma imagem usada para espelhar
#             produção em 08/10) num container nomeado, SEM porta publicada e com
#             --network none: só se fala com ele por `docker exec`, e ele não
#             alcança a internet (pg_net, http e dblink da imagem ficam sem rota).
#   semear    aplica db/semente_sintetica.sql depois de um gate anti-PII/segredo
#   migrar    aplica a candidata (MIGRATION=...) e registra sha256 no ledger do lab
#   testar    matriz de acesso, sonda, fingerprint, guarda de reaplicação,
#             rollback idempotente e reaplicação a partir do estado anterior
#   destruir  remove só o container com o rótulo volc.freedom-lab=1
#   base-prod restaura dump --schema-only de produção (LAB_DUMP + LAB_DUMP_SHA256,
#             fora do repo) sobre a imagem, como supabase_admin, em blocos
#   recriar   destruir → criar → semear → testar (que migra, desfaz e refaz)
#   recriar-prod destruir → criar → base-prod → [LAB_SEMENTE] → testar
#   MIGRATION_SUITE=<arquivo> troca a suíte do testar (padrão db/suites/v18_01.sh)
#   status    mostra se o container existe
#
# Também é biblioteca: `. tools/freedom-lab/lab.sh` (com LAB_NOME próprio) dá
# criar/destruir/P/PA/sqlstate/ok/nao/eq sem rodar comando — é assim que as provas
# do ledger (scripts/provar-ledger-migracoes.sh, scripts/provar-migracao-par.sh)
# sobem o banco descartável, em vez de um laboratório paralelo.
#
# Nunca toca em produção: não lê .env, não usa SSH, não publica porta.
# Recibo do `testar` vai para $RECIBOS (padrão: tools/freedom-lab/runs/<data>/).
# =============================================================================
set -uo pipefail
export LC_ALL=C LANG=C

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$AQUI/../.." && pwd)"
IMAGEM="${LAB_IMAGEM:-supabase/postgres:15.8.1.085}"
NOME="${LAB_NOME:-volc-freedom-lab-db}"
MIGRATION="${MIGRATION:-$RAIZ/supabase/migrations/v18_01_identidade_leitura_minima.PROPOSTA.sql}"
ROLLBACK="${ROLLBACK:-$RAIZ/supabase/migrations/v18_01_identidade_leitura_minima_rollback.PROPOSTA.sql}"
SEMENTE="$AQUI/db/semente_sintetica.sql"
SONDA="$AQUI/db/sonda_acesso.sql"
FP="$AQUI/db/fingerprint_schema.sql"
RECIBOS="${RECIBOS:-$AQUI/runs/$(date +%Y%m%d-%H%M%S)}"
SUITE="${MIGRATION_SUITE:-$AQUI/db/suites/v18_01.sh}"
SUITE_GARANTIDA="nao"
PREREQS_PROD="$AQUI/db/base_prod_prereqs.sql"

# Toda execução de SQL exige o container do LAB (nome + rótulo) e sem rede:
# um LAB_NOME apontado para outro container nunca recebe migration, GRANT ou rollback.
exigir_lab() {
  existe || { echo "ERRO: $NOME não existe ou não tem o rótulo volc.freedom-lab=1; nada executado" >&2; return 97; }
  [ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$NOME")" = "none" ] || \
    { echo "ERRO: $NOME tem rede; o lab só roda sem rede" >&2; return 98; }
}
P() { exigir_lab || return $?; docker exec -i "$NOME" psql -U postgres -d postgres -X -q -A -t -v ON_ERROR_STOP=1 "$@"; }
# Como supabase_admin (superusuário da imagem), para migrations de users/default ACL
# e restore com donos. Pelo loopback do container, que o pg_hba da imagem confia.
PA() { exigir_lab || return $?; docker exec -i "$NOME" psql -h localhost -U supabase_admin -d postgres -X -q -A -t -v ON_ERROR_STOP=1 "$@"; }
sha() { shasum -a 256 "$1" | awk '{print $1}'; }

# SQLSTATE do primeiro erro de um bloco SQL rodado como postgres, ou "ok"
sqlstate() {
  exigir_lab || return $?
  local out st
  out="$(printf '\\set VERBOSITY verbose\n%s\n' "$1" | docker exec -i "$NOME" psql -U postgres -d postgres -X -A -t 2>&1)"
  st="$(printf '%s' "$out" | grep -oE 'ERROR:  [0-9A-Z]{5}' | head -1 | awk '{print $2}')"
  [ -n "$st" ] && echo "$st" || echo ok
}

# Contadores de verificação (T total, F falhas); recibo em $RECIBOS/provas.txt
T=0 F=0
ok()  { T=$((T+1)); printf '  ✓ %s\n' "$1" | tee -a "$RECIBOS/provas.txt"; }
nao() { T=$((T+1)); F=$((F+1)); printf '  ✗ %s\n' "$1" | tee -a "$RECIBOS/provas.txt"; }
eq()  { [ "$1" = "$2" ] && ok "$3" || nao "$3 (esperado=$2 obtido=$1)"; }

existe() { [ -n "$(docker ps -aq --filter "name=^${NOME}$" --filter label=volc.freedom-lab=1)" ]; }

criar() {
  if existe; then echo "container $NOME já existe (use recriar)"; return 1; fi
  if [ -n "$(docker ps -aq --filter "name=^${NOME}$")" ]; then
    echo "ERRO: existe um $NOME sem o rótulo do lab — não é meu, não toco"; return 1; fi
  # Senha só para o processo de init da imagem; não há porta publicada, então
  # ela não dá acesso a nada fora do container. Gerada e descartada.
  local senha; senha="$(openssl rand -hex 24)"
  docker run -d --name "$NOME" --label volc.freedom-lab=1 --network none \
    -e POSTGRES_PASSWORD="$senha" "$IMAGEM" >/dev/null || return 1
  unset senha
  # A imagem sobe um servidor temporário (listen_addresses vazio, só socket), roda o
  # init e REINICIA: "aceitou conexão" não basta. Primeiro o servidor definitivo
  # (escuta TCP) com o mesmo postmaster em três leituras seguidas (W9)…
  local i t ant="" iguais=0
  for i in $(seq 1 120); do
    t="$(P -c "select pg_postmaster_start_time() where current_setting('listen_addresses') <> ''" 2>/dev/null)"
    if [ -n "$t" ] && [ "$t" = "$ant" ]; then iguais=$((iguais+1)); else iguais=0; fi
    ant="$t"
    [ $iguais -ge 3 ] && break
    sleep 1
  done
  # …depois o fim do init: o 1º "select 1" chega antes do fim do init da imagem, que ainda cria auth.uid e
  # rebaixa postgres de superusuário. Rodar antes disso testaria um banco mais
  # permissivo que produção. Espera os dois (medido pelo W4 em 15/10).
  for i in $(seq 1 120); do
    [ "$(P -c "select count(*) from pg_proc where proname='uid' and pronamespace='auth'::regnamespace" 2>/dev/null)" = "1" ] && \
    [ "$(P -c "select rolsuper from pg_roles where rolname='postgres'" 2>/dev/null)" = "f" ] && \
      { echo "▶ criado $NOME ($IMAGEM) sem rede e sem porta; init concluído"; P -c "select version()"; return 0; }
    sleep 1
  done
  echo "ERRO: banco/init não ficou pronto"; docker logs --tail 20 "$NOME"; return 1
}

destruir() {
  if existe; then docker rm -f "$NOME" >/dev/null && echo "▶ destruído $NOME"; else echo "nada a destruir"; fi
}

gate_semente() {
  if grep -nEi '@agenciavolc|eyJ[A-Za-z0-9_-]{10,}\.|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}|[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2}|@(gmail|hotmail|outlook|yahoo|uol|bol|icloud)\.' "$1" >/dev/null; then
    echo "ERRO: semente $(basename "$1") contém material proibido; nada aplicado" >&2; return 1; fi
}
semear() {
  exigir_lab || return $?
  gate_semente "$SEMENTE" || return 1
  P -f - < "$SEMENTE" >/dev/null && echo "▶ semente sintética aplicada (sha256 $(sha "$SEMENTE"))"
}
semear_prod() {  # LAB_SEMENTE sobre a base de produção, como supabase_admin, pelo mesmo gate
  exigir_lab || return $?
  gate_semente "$LAB_SEMENTE" || return 1
  PA -f - < "$LAB_SEMENTE" >/dev/null && export SEMENTE_APLICADA_SHA="$(sha "$LAB_SEMENTE")" && \
    echo "▶ semente $(basename "$LAB_SEMENTE") aplicada (sha256 $SEMENTE_APLICADA_SHA)"
}


# estado <papel> <sql> [claims-json] → SQLSTATE do 1º erro, ou ok:<1ª linha>; sempre em ROLLBACK.
# Com claims, define request.jwt.claims como o PostgREST faz, para exercitar policy por auth.uid().
estado() {
  exigir_lab >/dev/null 2>&1 || { echo "ERRO_HARNESS_LAB"; return; }
  local out st claims=""
  [ -n "${3:-}" ] && claims="SET LOCAL request.jwt.claims = '$3';"
  out=$(printf '\\set VERBOSITY verbose\nBEGIN; SET LOCAL ROLE %s; %s %s; ROLLBACK;\n' "$1" "$claims" "$2" \
        | docker exec -i "$NOME" psql -h localhost -U "${ESTADO_COMO:-postgres}" -d postgres -X -A -t 2>&1)
  st=$(printf '%s' "$out" | grep -oE 'ERROR:  [0-9A-Z]{5}' | head -1 | awk '{print $2}')
  [ -n "$st" ] && echo "$st" || echo "ok:$(printf '%s' "$out" | grep -vE '^(BEGIN|ROLLBACK|SET|UPDATE [0-9]+|DELETE [0-9]+|INSERT 0 [0-9]+|TRUNCATE TABLE)$' | head -1)"
}
# login <papel> <sql>: entra pelo LOGIN real do papel (com o default_transaction_read_only
# dele), não por SET ROLE: na imagem Supabase o `postgres` não é superusuário nem membro
# de papéis novos, e um SET ROLE negado devolveria 42501 pelo motivo errado. O pg_hba da
# imagem confia em 127.0.0.1: prova a IDENTIDADE e a configuração, não a senha.
login_como() {
  exigir_lab >/dev/null 2>&1 || { echo "ERRO_HARNESS_LAB"; return; }
  local out st
  out=$(printf '\\set VERBOSITY verbose\n%s;\n' "$2" \
        | docker exec -i "$NOME" psql -h localhost -U "$1" -d postgres -X -A -t 2>&1)
  st=$(printf '%s' "$out" | grep -oE 'ERROR:  [0-9A-Z]{5}' | head -1 | awk '{print $2}')
  if printf '%s' "$out" | grep -q 'psql: error\|authentication failed\|could not connect'; then echo "ERRO_HARNESS_LOGIN"; return; fi
  [ -n "$st" ] && echo "$st" || echo "ok:$(printf '%s' "$out" | grep -vE '^(SET|BEGIN|COMMIT|ROLLBACK)$' | head -1)"
}

# base-prod: restaura o dump --schema-only de PRODUÇÃO (fora do repo, conferido por sha256)
# sobre a imagem, para provar migration contra o estado imediatamente anterior real.
restaurar_blocos() {
  local dump="$1" blocos="$2" b
  python3 -I "$AQUI/db/restaurar_em_blocos.py" "$dump" "$blocos" >/dev/null || return 1
  : > "$RECIBOS/restore.log"
  for b in "$blocos"/*.sql; do
    pronto || return 1
    if ! PA -f - < "$b" >> "$RECIBOS/restore.log" 2>&1; then
      # Medido pelo W4: o backend do restore pode cair perto do fim sem o psql registrar
      # ERROR. Refaz o bloco uma vez; "already exists" é esperado, outro erro aborta.
      echo "  ✗ bloco $(basename "$b"): refazendo uma vez"; sleep 5; pronto || return 1
      docker exec -i "$NOME" psql -h localhost -U supabase_admin -d postgres -X -q < "$b" > "$RECIBOS/refazer-$(basename "$b").log" 2>&1
      grep ERROR "$RECIBOS/refazer-$(basename "$b").log" | grep -v "already exists" | grep -q . && { echo "ERRO no bloco refeito"; return 1; }
    fi
  done
  echo "$(ls "$blocos" | wc -l | tr -d ' ')" > "$RECIBOS/blocos.n"
}

base_prod() {
  local dump="${LAB_DUMP:?defina LAB_DUMP (caminho do dump --schema-only, fora do repo)}"
  local esperado="${LAB_DUMP_SHA256:?defina LAB_DUMP_SHA256}"
  [ -f "$dump" ] && [ "$(sha "$dump")" = "$esperado" ] || { echo "ERRO: dump ausente ou sha256 divergente; nada restaurado" >&2; return 1; }
  python3 -I "$AQUI/db/verificar_dump_schema.py" "$dump" || { echo "ERRO: dump contém dado; só --schema-only; nada restaurado" >&2; return 1; }
  exigir_lab || return $?
  mkdir -p "$RECIBOS"
  PA -f - < "$PREREQS_PROD" > "$RECIBOS/prereqs.log" 2>&1 || { tail -5 "$RECIBOS/prereqs.log"; return 1; }
  # Os blocos são cópia do schema de produção: ficam FORA do repo e somem no fim,
  # inclusive quando o restore falha.
  local blocos c; blocos="$(mktemp -d "${TMPDIR:-/tmp}/volc-lab-blocos.XXXXXX")"
  trap 'rm -rf "$blocos"; exit 130' INT TERM   # Ctrl-C não deixa schema de produção no TMPDIR
  restaurar_blocos "$dump" "$blocos"; c=$?
  rm -rf "$blocos"; trap - INT TERM
  [ $c = 0 ] || return $c
  PA -c "create schema if not exists volc_lab; create table if not exists volc_lab.base(valor text); insert into volc_lab.base values ('prod-schema:$esperado')" >/dev/null
  P -f - < "$FP" 2>/dev/null | grep '|' | tr -d ' ' > "$RECIBOS/fp-base-prod.txt"
  echo "▶ base de produção restaurada em $(cat "$RECIBOS/blocos.n") blocos (dump sha256 $esperado); fingerprint em fp-base-prod.txt"
}
pronto() { local i; for i in $(seq 1 180); do P -c "select 1" >/dev/null 2>&1 && return 0; sleep 1; done; echo "ERRO: banco não voltou"; return 1; }

registrar() { P -c "insert into volc_lab.migracao_aplicada(arquivo, sha256, base, resultado) values ('$(basename "$1")','$(sha "$1")','$2','$3')" >/dev/null; }

migrar() {
  local base="${1:-imagem+semente}"
  if P -f - < "$MIGRATION" > "$RECIBOS/migrar.out" 2>&1; then registrar "$MIGRATION" "$base" ok; echo "▶ migrou $(basename "$MIGRATION")"; return 0
  else registrar "$MIGRATION" "$base" falhou; tail -5 "$RECIBOS/migrar.out"; return 1; fi
}

testar() {
  exigir_lab || return $?
  mkdir -p "$RECIBOS"
  T=0 F=0
  # A suíte entra por `source`: só vale garantia estrutural se for arquivo de db/suites/
  # versionado e sem alteração local. Fora disso, só com LAB_SUITE_LIVRE=1, e o recibo
  # deixa de afirmar que produção não foi acessada.
  local suite_real; suite_real="$(cd "$(dirname "$SUITE")" && pwd)/$(basename "$SUITE")"
  if [ "$(dirname "$suite_real")" = "$AQUI/db/suites" ] && git -C "$RAIZ" ls-files --error-unmatch "$suite_real" >/dev/null 2>&1 \
     && git -C "$RAIZ" diff --quiet HEAD -- "$suite_real"; then
    SUITE_GARANTIDA="sim"
  elif [ "${LAB_SUITE_LIVRE:-0}" != 1 ]; then
    echo "ERRO: suíte fora de db/suites/ ou não commitada; use LAB_SUITE_LIVRE=1 para rodar sem garantia" >&2; return 96
  fi
  local suite_sha; suite_sha="$(sha "$SUITE")"
  echo "▶ suíte: $(basename "$SUITE") (sha256 $suite_sha, garantida=$SUITE_GARANTIDA)"
  # shellcheck source=/dev/null
  source "$SUITE"
  P -c "select arquivo, sha256, base, resultado from volc_lab.migracao_aplicada order by aplicada_em" > "$RECIBOS/ledger-lab.txt"
  # Base explícita: a tabela volc_lab.base só existe depois de base-prod. A consulta não
  # pode citá-la quando ela não existe (o planner resolve a relação mesmo no ramo morto).
  local base_do_lab="imagem+semente" semente_json
  # Semente realmente aplicada: a sintética na base imagem, LAB_SEMENTE (se houver) na de produção.
  if [ -n "${SEMENTE_APLICADA_SHA:-}" ]; then semente_json="\"$SEMENTE_APLICADA_SHA\""
  elif [ "$(P -c "select to_regclass('volc_lab.base') is not null")" = "t" ]; then semente_json=null
  else semente_json="\"$(sha "$SEMENTE")\""; fi
  [ "$(P -c "select to_regclass('volc_lab.base') is not null")" = "t" ] && base_do_lab="$(P -c "select valor from volc_lab.base limit 1")"
  {
    echo "{"
    echo "  \"imagem\": \"$IMAGEM\", \"versao\": \"$(P -c 'show server_version')\","
    echo "  \"migration\": \"$(basename "$MIGRATION")\", \"migration_sha256\": \"$(sha "$MIGRATION")\","
    echo "  \"rollback\": \"$(basename "$ROLLBACK")\", \"rollback_sha256\": \"$(sha "$ROLLBACK")\","
    echo "  \"semente_sha256\": \"$(sha "$SEMENTE")\","
    echo "  \"harness_sha256\": {\"lab.sh\": \"$(sha "$0")\", \"sonda_acesso.sql\": \"$(sha "$SONDA")\", \"fingerprint_schema.sql\": \"$(sha "$FP")\"},"
    echo "  \"suite\": \"${SUITE#$RAIZ/}\", \"suite_sha256\": \"$suite_sha\", \"suite_versionada\": \"$SUITE_GARANTIDA\","
    echo "  \"base\": \"$base_do_lab\","
    echo "  \"semente_aplicada_sha256\": $semente_json,"
    echo "  \"fingerprint_total_pos\": \"$(grep _TOTAL "$RECIBOS/fp-final.out" 2>/dev/null | tr -d ' ')\","
    echo "  \"verificacoes\": $T, \"falhas\": $F, \"producao_acessada\": $( [ "$SUITE_GARANTIDA" = sim ] && echo false || echo '\"nao_garantido\"'), \"producao_acessada_motivo\": \"$( [ "$SUITE_GARANTIDA" = sim ] && echo 'estrutural: lab.sh não lê .env nem usa SSH, o container não tem rede e a suíte é versionada' || echo 'suíte livre carregada por source: o lab.sh não garante o que ela faz')\""
    echo "}"
  } > "$RECIBOS/recibo.json"
  echo; echo "recibo: $RECIBOS/recibo.json"
  [ $F = 0 ] && { echo "CICLO VERDE ($T/$T)"; return 0; } || { echo "$F FALHA(S) de $T"; return 1; }
}

# Carregado com `.` (biblioteca): só as funções, nenhum comando.
[ "${BASH_SOURCE[0]}" = "$0" ] || return 0

case "${1:-}" in
  criar) criar ;;
  destruir) destruir ;;
  semear) semear ;;
  migrar) mkdir -p "$RECIBOS"; migrar "${2:-manual}" ;;
  testar) testar ;;
  base-prod) base_prod ;;
  recriar) destruir; criar && semear && testar; c=$?; [ "${MANTER:-0}" = 1 ] || destruir; exit $c ;;
  recriar-prod) destruir; criar && base_prod && { [ -z "${LAB_SEMENTE:-}" ] || semear_prod; } && testar; c=$?; [ "${MANTER:-0}" = 1 ] || destruir; exit $c ;;
  status) existe && docker ps -a --filter "name=^${NOME}$" --format '{{.Names}} {{.Status}} {{.Image}}' || echo "ausente" ;;
  *) sed -n 2,20p "$0"; exit 2 ;;
esac
