# shellcheck shell=bash
# =============================================================================
# db/suites/v20_pos_v19.sh — o ledger (v20) depois do pacote do incidente anon (v19).
#
# Ordem decidida: v19 roda antes e fora do ledger, pelo script do W4, e grava
# RECEIPT-*.json; a v20_02 nasce DESSE recibo (âncora constante + backfill) e os
# recibos seguintes (passo 2, rollback) entram pelo importador. Tudo pelo script
# real do W4 em modo laboratório (W4_ALVO_LAB = este container, sem rede).
#
#   LAB_DUMP=… LAB_DUMP_SHA256=2c70b4a4… \
#   LAB_SEMENTE=tools/freedom-lab/db/suites/v19_incidente_anon_semente.sql \
#   MIGRATION=supabase/migrations/v20_02_ledger_linha_de_base.sql \
#   ROLLBACK=supabase/migrations/v20_02_rollback.sql \
#   MIGRATION_SUITE=tools/freedom-lab/db/suites/v20_pos_v19.sh \
#   tools/freedom-lab/lab.sh recriar-prod
#
# Usa do lab.sh: P, ok, nao, eq, sqlstate, sha, NOME, RAIZ, RECIBOS.
# O inventário de consumidores aqui é SINTÉTICO e só existe no recibo do lab.
# =============================================================================
for _f in P ok nao eq sqlstate sha; do
  declare -F "$_f" >/dev/null || { echo "ERRO: v20_pos_v19.sh precisa do lab.sh (falta $_f)" >&2; return 1 2>/dev/null || exit 1; }
done; unset _f

V20_GEN="$RAIZ/scripts/ledger_recibo_incidente.py"
V20_W4="$RAIZ/scripts/aplicar-incidente-anon-w4.sh"
V20_PROTO="$RAIZ/scripts/migracao-protocolo.sh"
V20_M="$RAIZ/supabase/migrations"
V20_DIR="$RECIBOS/v20pos"; mkdir -p "$V20_DIR/w4" "$V20_DIR/proto" "$V20_DIR/lab"

v20_w4() { # v20_w4 <operacao> [args…] → roda o script do W4 contra ESTE container; ecoa o RECEIPT gerado
  local antes; antes="$(ls "$V20_DIR/w4"/RECEIPT-*.json 2>/dev/null | wc -l)"
  echo APLICAR | W4_ALVO_LAB="$NOME" W4_RECIBO_DIR="$V20_DIR/w4" bash "$V20_W4" "$@" \
    > "$V20_DIR/w4-$(echo "$1" | tr -d -).log" 2>&1
  local rc=$?
  [ "$(ls "$V20_DIR/w4"/RECEIPT-*.json 2>/dev/null | wc -l)" -gt "$antes" ] && ls -t "$V20_DIR/w4"/RECEIPT-*.json | head -1
  return $rc
}
v20_proto() { "$V20_PROTO" "$@" --alvo "docker:$NOME" --recibo-dir "$V20_DIR/proto" > "$V20_DIR/proto.out" 2>&1; echo $?; }
v20_gen() { python3 -I "$V20_GEN" "$@" > "$V20_DIR/gen.out" 2>&1; echo $?; }
v20_recusa() { grep -q "$1" "$V20_DIR/gen.out"; }  # a recusa veio pelo motivo certo, não por traceback
v20_imp() { { echo "select set_config('volc_ops.aprovador', '${2-laboratorio}', false);"; cat "$1"; } | P -f - > "$V20_DIR/imp.out" 2>&1; }
v20_eventos() { P -c "select string_agg(versao||':'||operacao, ',' order by id) from volc_ops.migracao_evento"; }

echo "▶ v20 · inventário sintético assinado (só laboratório)"
python3 -I - "$RAIZ/docs/INCIDENTE-ANON-INVENTARIO.modelo.json" "$V20_DIR/inventario-lab.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for c in d["consumidores"]:
    c.update(confirmado_em_producao=True, evidencia="laboratório: consumidor sintético", decisao="nao_usa_anon")
d.update(assinado_por="laboratorio", assinado_em="2026-10-15", bloqueia_passo1=False)
json.dump(d, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
PY
INV_SHA="$(sha "$V20_DIR/inventario-lab.json")"

echo "▶ v20 · ledger criado ANTES da v19 (não muda public/app_auth)"
eq "$(v20_proto aplicar --migration "$V20_M/v20_01_ledger_migrations.sql" --sha "$(sha "$V20_M/v20_01_ledger_migrations.sql")" --rollback "$V20_M/v20_01_rollback.sql" --sha-rollback "$(sha "$V20_M/v20_01_rollback.sql")" --aprovador laboratorio --cria-ledger)" 0 "v20_01 aplicada pelo protocolo"
FP_BASE="$(P -c "select md5 from volc_ops.fingerprint_schema() where categoria='_TOTAL'")"

echo "▶ v20 · recibo FORJADO (v19 não aplicada) não vira registro"
python3 -I - "$RAIZ/tools/freedom-lab/tests/fixtures/RECEIPT-lab-passo1.json" "$V20_DIR/forjado.json" "$FP_BASE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["alvo"] = "producao"; d["fingerprint_depois"] = sys.argv[3]
d["fingerprint_antes"] = "0" * 32
json.dump(d, open(sys.argv[2], "w"))
PY
eq "$(v20_gen v20_02 "$V20_DIR/forjado.json" --saida "$V20_DIR/lab/v20_02_ledger_linha_de_base_pos_v19.sql" --ancora-pre-v19 00000000000000000000000000000000)" 0 "gerador aceita a forma do recibo forjado (sha certos, alvo=producao)"
eq "$(v20_proto aplicar --migration "$V20_DIR/lab/v20_02_ledger_linha_de_base_pos_v19.sql" --sha "$(sha "$V20_DIR/lab/v20_02_ledger_linha_de_base_pos_v19.sql")" --aprovador laboratorio)" 14 "…mas o banco recusa ao aplicar"
grep -q "v19_00 ausente" "$V20_DIR"/proto/RECEIPT-v20_02_ledger_linha_de_base_pos_v19-aplicar-*.txt && ok "recusa pelo efeito ausente da 1ª migration da v19" || nao "recusa por outro motivo"
eq "$(P -c "select count(*) from volc_ops.migracao_evento")" 0 "ledger intocado pela forja"
rm -f "$V20_DIR/lab/v20_02_ledger_linha_de_base_pos_v19.sql"

echo "▶ v20 · passo 1 do W4 (fora do ledger) gera o recibo"
REC1="$(v20_w4 --passo1 --aprovador laboratorio --inventario "$V20_DIR/inventario-lab.json" --sha-inventario "$INV_SHA")"
[ -n "$REC1" ] && ok "passo 1 gravou o recibo" || { nao "passo 1 não gravou recibo (ver w4-passo1.log)"; return 0; }
eq "$(python3 -I -c "import json,sys;d=json.load(open(sys.argv[1]));print(d['resultado'],len(d['eventos']))" "$REC1")" "ok 5" "recibo do passo 1: ok, 5 eventos"
FP_POS="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))['fingerprint_depois'])" "$REC1")"
eq "$(P -c "select md5 from volc_ops.fingerprint_schema() where categoria='_TOTAL'")" "$FP_POS" "fingerprint do ledger = fingerprint_depois do recibo"

echo "▶ v20 · gerador recusa pelo motivo certo"
python3 -I -c "import json,sys;d=json.load(open(sys.argv[1]));d['eventos'][2]['sha256']='0'*64;json.dump(d,open(sys.argv[2],'w'))" "$REC1" "$V20_DIR/adulterado.json"
eq "$(v20_gen v20_02 "$V20_DIR/adulterado.json" --saida "$V20_DIR/lab/x.sql" --ancora-pre-v19 "$FP_BASE")" 1 "evento com sha256 ≠ repositório → recusado"
v20_recusa "sha256 do recibo" && ok "…com a mensagem do sha256" || nao "…recusou por outro motivo"
python3 -I -c "import json,sys;d=json.load(open(sys.argv[1]));d['alvo']='producao\nCREATE TABLE public.injetado(i int);';json.dump(d,open(sys.argv[2],'w'))" "$REC1" "$V20_DIR/injecao.json"
eq "$(v20_gen v20_02 "$V20_DIR/injecao.json" --saida "$V20_DIR/lab/x.sql" --ancora-pre-v19 "$FP_BASE")" 1 "quebra de linha no alvo → recusado"
v20_recusa "alvo: formato inválido" && ok "…pela validação de formato" || nao "…recusou por outro motivo"
[ ! -e "$V20_DIR/lab/x.sql" ] && ok "nenhuma recusa escreveu arquivo" || nao "recusa escreveu arquivo"
eq "$(v20_gen v20_02 "$REC1" --saida "$RAIZ/supabase/migrations/v20_02_ledger_linha_de_base.sql" --ancora-pre-v19 "$FP_BASE")" 1 "saída sobre a v20_02 versionada → recusada"
git -C "$RAIZ" diff --quiet -- supabase/migrations/v20_02_ledger_linha_de_base.sql && ok "v20_02 versionada intacta (git diff limpo)" || nao "v20_02 versionada alterada"
V20_02_LAB="$V20_DIR/lab/v20_02_ledger_linha_de_base_pos_v19.sql"
eq "$(v20_gen v20_02 "$REC1" --saida "$V20_DIR/lab/sem-ancora.sql")" 1 "âncora de produção (695e913a) ≠ fingerprint_antes do lab → recusado"
v20_recusa "houve DDL" && ok "…com a mensagem de DDL entre a medição e o passo 1" || nao "…recusou por outro motivo"
eq "$(v20_gen v20_02 "$REC1" --saida "$V20_02_LAB" --ancora-pre-v19 "$FP_BASE")" 0 "v20_02 pós-v19 gerada do recibo real, âncora = base medida antes do passo 1"
grep -q "esperado   constant text := '$FP_POS'" "$V20_02_LAB" && ok "âncora constante = fingerprint_depois do recibo" || nao "âncora não é a do recibo"

echo "▶ v20 · linha de base pós-v19"
eq "$(v20_proto aplicar --migration "$V20_M/v20_02_ledger_linha_de_base.sql" --sha "$(sha "$V20_M/v20_02_ledger_linha_de_base.sql")" --aprovador laboratorio)" 14 "v20_02 versionada (pré-v19) recusa"
grep -q "o schema mudou desde a medição" "$V20_DIR"/proto/RECEIPT-v20_02_ledger_linha_de_base-aplicar-*.txt && ok "…pela âncora 695e913a (no lab a base já difere de produção: prova não discriminante sozinha)" || nao "…por outro motivo"
V20_RB="$V20_M/v20_02_pos_v19_rollback.sql"; V20_PROPRIA=v20_02_ledger_linha_de_base_pos_v19
v20_sem_propria() { P -c "select coalesce(string_agg(versao||':'||operacao||':'||sha256, ',' order by id), '<vazio>') from volc_ops.migracao_evento where versao <> '$V20_PROPRIA'"; }
V20_ANTES="$(v20_sem_propria)"
V20_BACKFILL="linha_de_base_producao_20261015:linha_de_base,v19_00_users_gatilho_papel_real:aplicar,v8_03_users_rls_policies:aplicar,v19_01_anon_fecha_public:aplicar,v8_05_users_safe_view:aplicar,v19_02_default_acl_public_sem_anon:aplicar,v20_01_ledger_migrations:aplicar"
v20_aplica_pos() { v20_proto aplicar --migration "$V20_02_LAB" --sha "$(sha "$V20_02_LAB")" --rollback "$V20_RB" --sha-rollback "$(sha "$V20_RB")" --aprovador laboratorio --aprovado-em 2026-10-15; }
eq "$(v20_aplica_pos)" 0 "v20_02 pós-v19 aplica pelo protocolo, com o par de rollback"
eq "$(v20_eventos)" "$V20_PROPRIA:aplicar,$V20_BACKFILL" "ledger: v20_02 pós-v19, linha de base, os 5 eventos da v19 na ordem, v20_01"

echo "▶ v20 · rollback da v20_02 pós-v19"
eq "$(v20_proto reverter --versao "$V20_PROPRIA" --rollback "$V20_RB" --sha-rollback "$(sha "$V20_RB")" --aprovador laboratorio)" 0 "rollback pelo protocolo"
eq "$(v20_sem_propria)" "$V20_ANTES" "ledger volta exatamente ao estado anterior (fora o próprio aplicar/reverter)"
eq "$(P -c "select estado from volc_ops.migracao_estado where versao='$V20_PROPRIA'")" revertida "estado: v20_02 pós-v19 revertida"
eq "$(P -c "select md5 from volc_ops.fingerprint_schema() where categoria='_TOTAL'")" "$FP_POS" "rollback do ledger não mexe no schema (a v19 continua aplicada)"
eq "$(v20_proto reverter --versao "$V20_PROPRIA" --rollback "$V20_RB" --sha-rollback "$(sha "$V20_RB")" --aprovador laboratorio)" 12 "reverter de novo → não aplicada (12)"
{ echo "BEGIN;"; cat "$V20_RB" | sed '/^BEGIN;$/d; /^COMMIT;$/d'; echo "ROLLBACK;"; } > "$V20_DIR/rb-solto.sql"
P -f - < "$V20_DIR/rb-solto.sql" > "$V20_DIR/rb-solto.out" 2>&1 && nao "rollback solto com ledger vazio passou" || \
  { grep -q "backfill incompleto" "$V20_DIR/rb-solto.out" && ok "rollback sem backfill → recusado (nada a desfazer)" || nao "recusou por outro motivo"; }
eq "$(v20_aplica_pos)" 0 "v20_02 pós-v19 reaplica depois do rollback"
eq "$(P -c "select string_agg(versao||':'||operacao, ',' order by id) from volc_ops.migracao_evento where versao <> '$V20_PROPRIA'")" "$V20_BACKFILL" "backfill de novo, idêntico"
eq "$(P -c "select count(*) from volc_ops.migracao_evento where (versao like 'v19%' or versao like 'v8_0%') and rollback_sha256 = '$(sha "$V20_M/v19_99_rollback.sql")'")" 5 "cada evento v19 leva o par v19_99"
eq "$(P -c "select count(*) from volc_ops.migracao_evento where (versao like 'v19%' or versao like 'v8_0%') and aprovador = 'laboratorio' and fingerprint is null")" 4 "aprovador do protocolo; fingerprint só no 1º evento (os outros não foram medidos)"

echo "▶ v20 · importador: passo 2 e rollback"
REC2="$(v20_w4 --passo2 --aprovador laboratorio)"
[ -n "$REC2" ] && ok "passo 2 gravou o recibo" || nao "passo 2 não gravou recibo"
eq "$(v20_gen importar "$REC2" --saida "$V20_DIR/lab/imp2.sql")" 0 "importação do passo 2 gerada"
v20_imp "$V20_DIR/lab/imp2.sql" "" && nao "importação sem aprovador passou" || { grep -q "sem aprovador" "$V20_DIR/imp.out" && ok "importação sem aprovador → recusada" || nao "recusou por outro motivo"; }
v20_imp "$V20_DIR/lab/imp2.sql" && ok "importação do passo 2 aplicada com aprovador" || nao "importação do passo 2 falhou"
eq "$(P -c "select estado from volc_ops.migracao_estado where versao='v8_06_users_sensitive_columns_revoke'")" aplicada "ledger: v8_06 aplicada"
eq "$(v20_proto reverter --versao "$V20_PROPRIA" --rollback "$V20_RB" --sha-rollback "$(sha "$V20_RB")" --aprovador laboratorio)" 14 "rollback da v20_02 pós-v19 com evento posterior (v8_06) → recusado"
grep -q "dependem da linha de base" "$V20_DIR"/proto/RECEIPT-"$V20_PROPRIA"-reverter-*.txt && ok "…porque outra versão se ancorou na base" || nao "…por outro motivo"
v20_imp "$V20_DIR/lab/imp2.sql" && nao "reimportar o mesmo recibo passou" || \
  { grep -q "reaplicação recusada\|recibo não corresponde" "$V20_DIR/imp.out" && ok "reimportar o passo 2 → recusado" || nao "reimportação falhou por outro motivo"; }
eq "$(v20_gen importar "$REC2" --saida "$V20_DIR/lab/imp2.sql")" 1 "importar de novo para o mesmo arquivo → recusado (nunca sobrescreve)"
RECR="$(v20_w4 --rollback --aprovador laboratorio)"
[ -n "$RECR" ] && ok "rollback gravou o recibo" || nao "rollback não gravou recibo"
eq "$(v20_gen importar "$RECR" --saida "$V20_DIR/lab/impr.sql")" 0 "importação do rollback gerada"
v20_imp "$V20_DIR/lab/impr.sql" && ok "importação do rollback aplicada" || nao "importação do rollback falhou"
eq "$(P -c "select string_agg(versao||'='||estado, ',' order by versao) from volc_ops.migracao_estado where versao like 'v19%' or versao like 'v8_0%'")" \
   "v19_00_users_gatilho_papel_real=revertida,v19_01_anon_fecha_public=revertida,v19_02_default_acl_public_sem_anon=revertida,v8_03_users_rls_policies=revertida,v8_05_users_safe_view=revertida,v8_06_users_sensitive_columns_revoke=revertida" \
   "ledger: as 6 versões do incidente revertidas"
v20_imp "$V20_DIR/lab/impr.sql" && nao "reimportar o rollback passou" || { grep -q "nada a importar" "$V20_DIR/imp.out" && ok "reimportar o rollback → recusado (nada a importar)" || nao "recusou por outro motivo"; }
eq "$(sqlstate "INSERT INTO volc_ops.migracao_evento(versao,operacao,arquivo,sha256,aprovador) VALUES ('v19_00_users_gatilho_papel_real','reverter','x','$(printf '0%.0s' $(seq 64))','desvio')")" P0001 \
   "reverter de novo, pulando o importador → recusado pelo banco"
{ echo "{\"harness_ledger\": {\"ledger_recibo_incidente.py\": \"$(sha "$V20_GEN")\", \"aplicar-incidente-anon-w4.sh\": \"$(sha "$V20_W4")\", \"migracao-protocolo.sh\": \"$(sha "$V20_PROTO")\", \"v20_02_pos_v19_gerada\": \"$(sha "$V20_02_LAB")\", \"v20_02_pos_v19_rollback.sql\": \"$(sha "$V20_RB")\"}}"; } > "$RECIBOS/harness-ledger.json"
python3 -I -m json.tool "$RECIBOS/harness-ledger.json" >/dev/null && ok "harness-ledger.json é JSON válido" || nao "harness-ledger.json inválido"

echo "▶ v20 · R1: pacote aplicado pela metade não vira registro"
for m in v19_00_users_gatilho_papel_real v8_03_users_rls_policies v19_01_anon_fecha_public; do
  PA -f - < "$V20_M/$m.sql" > "$V20_DIR/parcial-$m.out" 2>&1 || nao "aplicação parcial: $m falhou"
done
FP_PARCIAL="$(P -c "select md5 from volc_ops.fingerprint_schema() where categoria='_TOTAL'")"
python3 -I - "$REC1" "$V20_DIR/parcial.json" "$FP_BASE" "$FP_PARCIAL" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["fingerprint_antes"], d["fingerprint_depois"] = sys.argv[3], sys.argv[4]
json.dump(d, open(sys.argv[2], "w"))
PY
eq "$(v20_gen v20_02 "$V20_DIR/parcial.json" --saida "$V20_DIR/lab/parcial.sql" --ancora-pre-v19 "$FP_BASE")" 0 "recibo que esconde a aplicação parcial gera (forma válida)"
N_ANTES="$(P -c "select count(*) from volc_ops.migracao_evento")"
v20_imp "$V20_DIR/lab/parcial.sql" && nao "v20_02 com pacote pela metade passou" || \
  { grep -q "v8_05 ausente" "$V20_DIR/imp.out" && ok "…mas o banco recusa: v8_05 ausente (1ª migration faltante)" || nao "recusou por outro motivo"; }
eq "$(P -c "select count(*) from volc_ops.migracao_evento")" "$N_ANTES" "nenhum evento gravado pela tentativa parcial"
v20_w4 --rollback --aprovador laboratorio >/dev/null || true

echo "▶ v20 · R2: DDL extra antes do W4 quebra a âncora pré-v19"
P -c "CREATE TABLE public.ddl_extra_antes_do_w4 (i int)" >/dev/null && ok "DDL extra aplicada antes do passo 1" || nao "DDL extra falhou"
REC_DDL="$(v20_w4 --passo1 --aprovador laboratorio --inventario "$V20_DIR/inventario-lab.json" --sha-inventario "$INV_SHA")"
[ -n "$REC_DDL" ] && ok "passo 1 sobre base com DDL extra gravou recibo" || nao "passo 1 com DDL extra sem recibo"
eq "$(v20_gen v20_02 "$REC_DDL" --saida "$V20_DIR/lab/ddl.sql" --ancora-pre-v19 "$FP_BASE")" 1 "fingerprint_antes ≠ âncora pré-v19 → recusado"
v20_recusa "houve DDL" && ok "…com a mensagem de DDL entre a medição e o passo 1" || nao "…recusou por outro motivo"
P -f - < "$FP" > "$RECIBOS/fp-final.out" 2>&1
