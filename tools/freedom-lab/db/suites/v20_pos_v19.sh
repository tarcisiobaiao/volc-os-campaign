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

echo "▶ v20 · passo 1 do W4 (fora do ledger) gera o recibo"
REC1="$(v20_w4 --passo1 --aprovador laboratorio --inventario "$V20_DIR/inventario-lab.json" --sha-inventario "$INV_SHA")"
[ -n "$REC1" ] && ok "passo 1 gravou $(basename "$REC1")" || { nao "passo 1 não gravou recibo (ver w4-passo1.log)"; return 0; }
eq "$(python3 -I -c "import json,sys;d=json.load(open(sys.argv[1]));print(d['resultado'],len(d['eventos']))" "$REC1")" "ok 5" "recibo do passo 1: ok, 5 eventos"
FP_POS="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))['fingerprint_depois'])" "$REC1")"

echo "▶ v20 · gerador da v20_02 recusa o que não pode virar âncora"
eq "$(v20_gen v20_02 "$REC1" --saida "$V20_DIR/lab/x.sql")" 1 "recibo de laboratório sem --aceitar-lab → recusado"
python3 -I - "$REC1" "$V20_DIR/adulterado.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["eventos"][2]["sha256"] = "0" * 64
json.dump(d, open(sys.argv[2], "w"))
PY
eq "$(v20_gen v20_02 "$V20_DIR/adulterado.json" --saida "$V20_DIR/lab/x.sql" --aceitar-lab)" 1 "evento com sha256 ≠ arquivo do repositório → recusado"
python3 -I -c "import json,sys;d=json.load(open(sys.argv[1]));d['resultado']='falhou';json.dump(d,open(sys.argv[2],'w'))" "$REC1" "$V20_DIR/falhou.json"
eq "$(v20_gen v20_02 "$V20_DIR/falhou.json" --saida "$V20_DIR/lab/x.sql" --aceitar-lab)" 1 "recibo com resultado falhou → recusado"
[ ! -e "$V20_DIR/lab/x.sql" ] && ok "nenhuma recusa escreveu arquivo" || nao "recusa escreveu arquivo"
V20_02_LAB="$V20_DIR/lab/v20_02_ledger_linha_de_base.sql"
eq "$(v20_gen v20_02 "$REC1" --saida "$V20_02_LAB" --aceitar-lab)" 0 "v20_02 gerada do recibo do passo 1"
grep -q "esperado   constant text := '$FP_POS'" "$V20_02_LAB" && ok "âncora constante no arquivo = fingerprint_depois do recibo" || nao "âncora não é a do recibo"
! grep -q "current_setting('volc_ops.fingerprint" "$V20_02_LAB" && ok "âncora não vem de GUC" || nao "âncora lida de GUC"
python3 -I "$V20_GEN" v20_02 "$REC1" --saida "$V20_DIR/lab/de-novo.sql" --aceitar-lab >/dev/null
cmp -s "$V20_02_LAB" "$V20_DIR/lab/de-novo.sql" && ok "geração determinística (mesmo recibo → mesmo arquivo e sha256)" || nao "geração não determinística"

echo "▶ v20 · ledger depois da v19"
eq "$(v20_proto aplicar --migration "$V20_M/v20_01_ledger_migrations.sql" --sha "$(sha "$V20_M/v20_01_ledger_migrations.sql")" --rollback "$V20_M/v20_01_rollback.sql" --sha-rollback "$(sha "$V20_M/v20_01_rollback.sql")" --aprovador laboratorio --cria-ledger)" 0 "v20_01 aplicada pelo protocolo"
eq "$(P -c "select md5 from volc_ops.fingerprint_schema() where categoria='_TOTAL'")" "$FP_POS" "fingerprint do ledger = fingerprint_depois do recibo (mesma SQL, mesma âncora)"
eq "$(v20_proto aplicar --migration "$V20_M/v20_02_ledger_linha_de_base.sql" --sha "$(sha "$V20_M/v20_02_ledger_linha_de_base.sql")" --aprovador laboratorio)" 14 "v20_02 pré-v19 (âncora 695e913a) recusa depois da v19"
eq "$(v20_proto aplicar --migration "$V20_02_LAB" --sha "$(sha "$V20_02_LAB")" --rollback "$V20_M/v20_02_rollback.sql" --sha-rollback "$(sha "$V20_M/v20_02_rollback.sql")" --aprovador laboratorio --aprovado-em 2026-10-15)" 0 "v20_02 gerada aplica pelo protocolo"
eq "$(v20_eventos)" "v20_02_ledger_linha_de_base:aplicar,linha_de_base_producao_20261015:linha_de_base,v19_00_users_gatilho_papel_real:aplicar,v8_03_users_rls_policies:aplicar,v19_01_anon_fecha_public:aplicar,v8_05_users_safe_view:aplicar,v19_02_default_acl_public_sem_anon:aplicar,v20_01_ledger_migrations:aplicar" \
   "ledger: v20_02, linha de base, os 5 eventos da v19 na ordem do recibo, v20_01"
eq "$(P -c "select count(*) from volc_ops.migracao_evento where (versao like 'v19%' or versao like 'v8_0%') and rollback_sha256 = '$(sha "$V20_M/v19_99_rollback.sql")'")" 5 "cada evento v19 leva o par de rollback v19_99 aprovado"
eq "$(P -c "select fingerprint from volc_ops.migracao_evento where versao='linha_de_base_producao_20261015'")" 695e913a4373efd1c2265cdd5ac87251 "linha de base guarda o fingerprint pré-v19 de produção"

echo "▶ v20 · importador: passo 2 e rollback do W4"
REC2="$(v20_w4 --passo2 --aprovador laboratorio)"
[ -n "$REC2" ] && ok "passo 2 gravou $(basename "$REC2")" || nao "passo 2 não gravou recibo"
eq "$(v20_gen importar "$REC2" --saida "$V20_DIR/lab/imp2.sql" --aceitar-lab)" 0 "importação do passo 2 gerada"
P -f - < "$V20_DIR/lab/imp2.sql" > "$V20_DIR/imp2.out" 2>&1 && ok "importação do passo 2 aplicada" || nao "importação do passo 2 falhou"
eq "$(P -c "select estado from volc_ops.migracao_estado where versao='v8_06_users_sensitive_columns_revoke'")" aplicada "ledger: v8_06 aplicada"
P -f - < "$V20_DIR/lab/imp2.sql" > "$V20_DIR/imp2-de-novo.out" 2>&1 && nao "reimportar o mesmo recibo passou" || \
  { grep -q "reaplicação recusada" "$V20_DIR/imp2-de-novo.out" && ok "reimportar o mesmo recibo → recusado pelo gatilho" || nao "reimportação falhou por outro motivo"; }
RECR="$(v20_w4 --rollback --aprovador laboratorio)"
[ -n "$RECR" ] && ok "rollback gravou $(basename "$RECR")" || nao "rollback não gravou recibo"
eq "$(v20_gen importar "$RECR" --saida "$V20_DIR/lab/impr.sql" --aceitar-lab)" 0 "importação do rollback gerada"
P -f - < "$V20_DIR/lab/impr.sql" > "$V20_DIR/impr.out" 2>&1 && ok "importação do rollback aplicada" || nao "importação do rollback falhou"
eq "$(P -c "select string_agg(versao||'='||estado, ',' order by versao) from volc_ops.migracao_estado where versao like 'v19%' or versao like 'v8_0%'")" \
   "v19_00_users_gatilho_papel_real=revertida,v19_01_anon_fecha_public=revertida,v19_02_default_acl_public_sem_anon=revertida,v8_03_users_rls_policies=revertida,v8_05_users_safe_view=revertida,v8_06_users_sensitive_columns_revoke=revertida" \
   "ledger: as 6 versões do incidente revertidas"
eq "$(sqlstate "INSERT INTO volc_ops.migracao_evento(versao,operacao,arquivo,sha256,aprovador) VALUES ('v19_00_users_gatilho_papel_real','reverter','x','$(printf '0%.0s' $(seq 64))','desvio')")" P0001 \
   "reverter de novo, pulando o importador → recusado pelo banco"
P -f - < "$FP" > "$RECIBOS/fp-final.out" 2>&1
