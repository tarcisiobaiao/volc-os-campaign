#!/usr/bin/env bash
# provar-migracao-par.sh — o ciclo de QUALQUER par migration/rollback, passando
# pelo protocolo (scripts/migracao-protocolo.sh) e pelo ledger (v20_01), num
# Postgres descartável. Generaliza provar-ciclo-migrations.sh (que só servia à
# série v9) e o modo Docker de provar-v18_01.sh.
#
#   aplicar → recusar reaplicação → recusar hash divergente (arquivo e histórico)
#   → recusar desvio pelo banco (INSERT/UPDATE/DELETE direto no ledger)
#   → rollback (recusa o divergente, aceita o aprovado) → reaplicar
# com o fingerprint de public+app_auth conferido em cada degrau: depois do
# rollback tem de voltar ao de antes; depois da reaplicação, ao da 1ª aplicação.
#
# Uso:
#   scripts/provar-migracao-par.sh --migration ARQ --rollback ARQ [--pre ARQ]... [--prova ARQ.sql]
#   VOLC_PG_IMAGE=supabase/postgres:15.8.1.085 VOLC_LAB_PREFIXO=volc-lab-w9- scripts/provar-migracao-par.sh ...
#
# --pre   dependências aplicadas antes (pelo protocolo, aprovador "laboratorio")
# --prova SQL que roda depois de cada aplicação e tem de terminar sem erro
set -uo pipefail
export LC_ALL=C LANG=C
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROTO="$RAIZ/scripts/migracao-protocolo.sh"
M_DIR="$RAIZ/supabase/migrations"

MIG= ROLL= PROVA= PRE=()
while [ $# -gt 0 ]; do
  case "$1" in
    --migration) MIG="$2"; shift 2 ;;
    --rollback) ROLL="$2"; shift 2 ;;
    --pre) PRE+=("$2"); shift 2 ;;
    --prova) PROVA="$2"; shift 2 ;;
    *) echo "argumento desconhecido: $1" >&2; exit 2 ;;
  esac
done
[ -f "$MIG" ] && [ -f "$ROLL" ] || { sed -n '14,19p' "$0"; exit 2; }

# shellcheck source=lab-postgres-descartavel.sh
. "$RAIZ/scripts/lab-postgres-descartavel.sh" par
lab_criar
echo "▶ servidor $(P -c 'show server_version') · imagem $LAB_IMG · container $LAB_CN"
lab_papeis_supabase

sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
V="$(basename "$MIG" .sql)"
S="$(sha "$MIG")"; SR="$(sha "$ROLL")"
REC="$LAB_DIR/recibos"; mkdir -p "$REC"
proto() { "$PROTO" "$@" --alvo "docker:$LAB_CN" --recibo-dir "$REC" >"$LAB_DIR/proto.out" 2>&1; echo $?; }
fp() { P -c "select md5 from volc_ops.fingerprint_schema() where categoria='_TOTAL'"; }
eventos() { P -c "select count(*) from volc_ops.migracao_evento"; }
seq_de() { P -c "select string_agg(operacao, ',' order by id) from volc_ops.migracao_evento where versao='$V'"; }
divergente() { # cópia com o MESMO nome e um byte a mais: mesma versão, outro sha256
  mkdir -p "$LAB_DIR/div"; cp "$1" "$LAB_DIR/div/$(basename "$1")"
  printf '\n-- alterado depois da aprovação\n' >> "$LAB_DIR/div/$(basename "$1")"
  echo "$LAB_DIR/div/$(basename "$1")"; }
prova_extra() { [ -z "$PROVA" ] && return
  P < "$PROVA" >/dev/null 2>"$LAB_DIR/prova.err" && ok "$1 · prova específica ($(basename "$PROVA")) verde" \
    || { nao "$1 · prova específica falhou"; tail -3 "$LAB_DIR/prova.err" | sed 's/^/      /'; }; }

echo "▶ ledger (v20_01) pelo protocolo"
L="$M_DIR/v20_01_ledger_migrations.sql"
eq "$(proto aplicar --migration "$L" --sha "$(sha "$L")" --aprovador laboratorio --cria-ledger)" 0 "v20_01 aplicada (--cria-ledger)"

for d in ${PRE[@]+"${PRE[@]}"}; do
  eq "$(proto aplicar --migration "$d" --sha "$(sha "$d")" --aprovador laboratorio)" 0 "dependência $(basename "$d" .sql)"
done

echo "▶ 1 · hash divergente é recusado antes de conectar"
FP0="$(fp)"; N0="$(eventos)"
eq "$(proto aplicar --migration "$(divergente "$MIG")" --sha "$S" --aprovador laboratorio)" 10 "arquivo alterado depois da aprovação → 10"
eq "$(proto aplicar --migration "$MIG" --sha "$SR" --aprovador laboratorio)" 10 "sha256 aprovado de outro arquivo → 10"
eq "$(proto aplicar --migration "$MIG" --sha "$S" --rollback "$(divergente "$ROLL")" --sha-rollback "$SR" --aprovador laboratorio)" 10 \
   "rollback alterado depois da aprovação → 10"
eq "$(fp)|$(eventos)" "$FP0|$N0" "schema e ledger intocados pelas recusas"

echo "▶ 2 · aplicar"
eq "$(proto aplicar --migration "$MIG" --sha "$S" --rollback "$ROLL" --sha-rollback "$SR" --aprovador laboratorio --aprovado-em 2026-10-15)" 0 "$V aplicada"
FP1="$(fp)"
[ "$FP1" != "$FP0" ] && ok "fingerprint mudou ($FP0 → $FP1)" || echo "  · fingerprint de public+app_auth não mudou (a migration não toca esses schemas)"
eq "$(P -c "select estado||'|'||sha256||'|'||rollback_sha256 from volc_ops.migracao_estado where versao='$V'")" "aplicada|$S|$SR" "ledger: aplicada com sha256 e rollback aprovados"
prova_extra "aplicada"

echo "▶ 3 · reaplicação recusada"
N1="$(eventos)"
eq "$(proto aplicar --migration "$MIG" --sha "$S" --aprovador laboratorio)" 11 "protocolo recusa reaplicar → 11"
eq "$(lab_sqlstate "INSERT INTO volc_ops.migracao_evento(versao,operacao,arquivo,sha256,aprovador) VALUES ('$V','aplicar','x','$S','desvio')")" P0001 \
   "banco recusa reaplicar mesmo pulando o protocolo (P0001)"
eq "$(lab_sqlstate "UPDATE volc_ops.migracao_evento SET aprovador='outro'")" P0001 "UPDATE no ledger recusado (append-only)"
eq "$(lab_sqlstate "DELETE FROM volc_ops.migracao_evento")" P0001 "DELETE no ledger recusado"
eq "$(lab_sqlstate "TRUNCATE volc_ops.migracao_evento")" P0001 "TRUNCATE no ledger recusado"
eq "$(fp)|$(eventos)" "$FP1|$N1" "schema e ledger intocados"

echo "▶ 4 · rollback"
eq "$(proto reverter --versao "$V" --rollback "$(divergente "$ROLL")" --sha-rollback "$(sha "$LAB_DIR/div/$(basename "$ROLL")")" --aprovador laboratorio)" 10 \
   "rollback diferente do aprovado na aplicação → 10"
eq "$(lab_sqlstate "INSERT INTO volc_ops.migracao_evento(versao,operacao,arquivo,sha256,aprovador) VALUES ('$V','reverter','x','$(printf %064d 0)','desvio')")" P0001 \
   "banco recusa reverter com sha256 fora do aprovado (P0001)"
eq "$(proto reverter --versao "$V" --rollback "$ROLL" --sha-rollback "$SR" --aprovador laboratorio)" 0 "$V revertida"
eq "$(fp)" "$FP0" "fingerprint voltou ao de antes da aplicação"
eq "$(proto reverter --versao "$V" --rollback "$ROLL" --sha-rollback "$SR" --aprovador laboratorio)" 12 "reverter de novo → 12 (não aplicada)"

echo "▶ 5 · reaplicar depois do rollback"
DV="$(divergente "$MIG")"
eq "$(proto aplicar --migration "$DV" --sha "$(sha "$DV")" --aprovador laboratorio)" 10 "mesmo nome com outro conteúdo, mesmo aprovado → 10 (histórico)"
eq "$(lab_sqlstate "INSERT INTO volc_ops.migracao_evento(versao,operacao,arquivo,sha256,aprovador) VALUES ('$V','aplicar','x','$(sha "$DV")','desvio')")" P0001 \
   "banco recusa o mesmo nome com outro sha256 (P0001)"
eq "$(proto aplicar --migration "$MIG" --sha "$S" --rollback "$ROLL" --sha-rollback "$SR" --aprovador laboratorio)" 0 "$V reaplicada"
eq "$(fp)" "$FP1" "fingerprint idêntico ao da 1ª aplicação"
prova_extra "reaplicada"
eq "$(seq_de)" "aplicar,reverter,aplicar" "ledger conta a história: aplicar, reverter, aplicar"

echo "▶ papéis de API não enxergam o ledger"
for r in anon authenticated service_role; do
  eq "$(lab_sqlstate "SET ROLE $r; SELECT count(*) FROM volc_ops.migracao_evento")" 42501 "$r · SELECT no ledger negado (42501)"
done

echo
echo "  recibos do protocolo: $(ls "$REC" | wc -l | tr -d ' ') (destruídos com o container)"
if [ "$FALHAS" = 0 ]; then echo "  CICLO $V VERDE — $(P -c 'show server_version')"; exit 0
else echo "  $FALHAS FALHA(S) — $V"; exit 1; fi
