# shellcheck shell=bash
# =============================================================================
# tools/freedom-lab/db/suites/v25_w14.sh — suíte da v25_01 (W14) para o lab.sh
#
# Prova oficial (no Mac: o dump do schema de produção não entra na nuvem):
#
#   LAB_DUMP=<dump schema-only, fora do repo> LAB_DUMP_SHA256=<sha256 do dump> \
#   MIGRATION=supabase/migrations/v25_01_conversao_offline_ledger.sql \
#   ROLLBACK=supabase/migrations/v25_01_rollback.sql \
#   MIGRATION_SUITE=tools/freedom-lab/db/suites/v25_w14.sh \
#   tools/freedom-lab/lab.sh recriar-prod
#
# Usa só o que o lab.sh dá: P (psql como postgres, -q -A -t, ON_ERROR_STOP),
# PA (psql como supabase_admin, que aplica, reverte e faz a limpeza de teste),
# ok / nao / eq, RAIZ, RECIBOS e FP (fingerprint do schema).
#
# O que prova, sobre v25_01_conversao_offline_ledger.sql e v25_01_rollback.sql:
#   1. aplicar; reaplicar por cima é recusado; base sem papéis do Supabase é recusada
#   2. matriz anon / authenticated / service_role / postgres
#   3. decisão: elegível só com valor > 0, moeda, hora e proveniência; pulado só
#      com motivo e sem valor; append-only; repetição idempotente
#   4. lote: validate_only abre e fecha; real exige validate_only ACEITO do
#      mesmo envelope com os MESMOS itens, decisão elegível com o mesmo valor
#      para cada item e aprovação com a mesma impressão e destino declarado;
#      segundo envio vivo do mesmo envelope ou do mesmo transaction_id é
#      recusado (23505); recusado e falha liberam; sem_resposta prende outro
#      envelope e só sai pelo reenvio do MESMO (vira reenviado); transições
#      fechadas; request_id e identidade imutáveis; fechar com o pedido de
#      outro lote é recusado; DELETE e TRUNCATE recusados
#   4b. teto do rateio: por coorte, o real vivo (já enviados + o lote) não passa
#      do teto da proveniência nem das sessões; a view por coorte é só da
#      service_role; o reenvio do mesmo envelope não conta duas vezes
#   4c. dois envios reais da mesma coorte em paralelo: o segundo espera a trava
#      da coorte e é recusado pelo teto (sessões commitadas, limpas pelo dono)
#   5. rollback recusa com dado (atômico), devolve o fingerprint, é idempotente;
#      reaplicar dá o mesmo fingerprint
#
# Dados sintéticos fixos (contas 1111111111/2222222222, ação 900001); nenhum
# dado real. Papel simulado por SET LOCAL ROLE: prova o banco, não o PostgREST.
# =============================================================================

for _f in P PA ok nao eq; do
  declare -F "$_f" >/dev/null || { echo "ERRO: v25_w14.sh precisa ser carregada pelo lab.sh (falta $_f)" >&2; return 1 2>/dev/null || exit 1; }
done
unset _f

W14_APLICAR="$RAIZ/supabase/migrations/v25_01_conversao_offline_ledger.sql"
W14_REVERTER="$RAIZ/supabase/migrations/v25_01_rollback.sql"

w14_sql() { P -c "$1" 2>&1 | head -1; }

# Roda SQL como papel, numa transação desfeita. Saída: ok:<última linha> ou ERRO:<SQLSTATE>.
w14_bloco() {
  local papel=$1 sql=$2 out rc
  out=$(printf '\\set VERBOSITY sqlstate\nBEGIN;\nSET LOCAL ROLE %s;\n%s\nROLLBACK;\n' "$papel" "$sql" | P 2>&1); rc=$?
  if [ "$rc" -ne 0 ] || printf '%s' "$out" | grep -qE '^(ERROR|ERRO|psql:)'; then
    echo "ERRO:$(printf '%s\n' "$out" | grep -oE '(ERROR|ERRO):  [0-9A-Z]{5}' | head -1 | awk '{print $2}')"
  else
    echo "ok:$(printf '%s\n' "$out" | tail -1)"
  fi
}

w14_aplicar()  { PA -f - < "$W14_APLICAR"  > "$RECIBOS/w14-$1.out" 2>&1; }
w14_reverter() { PA -f - < "$W14_REVERTER" > "$RECIBOS/w14-$1.out" 2>&1; }
w14_fp() { P -f - < "$FP" > "$RECIBOS/w14-fp-$1.out" 2>&1; }
w14_aplicada() { w14_sql "select to_regclass('public.conversao_offline_lote') is not null"; }

# ── fixtures (texto SQL) ──
W14_IMP_A=$(printf 'a%.0s' $(seq 64))
W14_IMP_B=$(printf 'b%.0s' $(seq 64))
W14_VIMP=$(printf 'c%.0s' $(seq 64))
W14_TID1="volc-w14-$(printf '1%.0s' $(seq 40))"
W14_TID2="volc-w14-$(printf '2%.0s' $(seq 40))"
W14_SHA=$(printf 'd%.0s' $(seq 64))

w14_lote_json() { # modo impressao tids(csv) [validacao_id] [impressao_aprovada]
  local modo=$1 imp=$2 tids=$3 val=${4:-null} apr=${5:-$2} itens="" t
  for t in ${tids//,/ }; do itens="${itens:+$itens,}{\"transaction_id\":\"$t\",\"valor_impressao\":\"$W14_VIMP\"}"; done
  local aprov=null
  [ "$modo" = real ] && aprov="{\"impressao\":\"$apr\",\"aprovado_por\":\"Tarcisio\",\"aprovado_em\":\"2026-10-15T15:00:00-03:00\",\"referencia\":\"lab\",\"destino_primario\":false}"
  printf '{"modo":"%s","impressao":"%s","customer_id":"1111111111","login_customer_id":"2222222222","operating_account_id":"1111111111","product_destination_id":"900001","itens":[%s],"aprovacao":%s,"validacao_lote_id":%s}' \
    "$modo" "$imp" "$itens" "$aprov" "$val"
}
w14_abrir() { printf "SELECT public.conversao_offline_abrir_lote('%s'::jsonb)" "$(w14_lote_json "$@")"; }
# validate_only aceito do envelope A, guardado em v (psql var não atravessa: CTE)
W14_VAL_A_NU="SELECT public.conversao_offline_fechar_lote(($(w14_abrir validate_only "$W14_IMP_A" "$W14_TID1")), 'aceito', NULL, '{}'::jsonb);"
# Sem decisão elegível gravada o real não abre (proveniência): as fixtures gravam antes.
W14_VAL_ID="(SELECT max(id) FROM public.conversao_offline_lote WHERE modo='validate_only' AND impressao='$W14_IMP_A')"

w14_decisao() { # estado valor motivo proveniencia ocorrido_em [tid] [valor_impressao] [rodada]
  local tid=${6:-$W14_TID1} vimp=${7:-$W14_VIMP} rodada=${8:-r1}
  printf "INSERT INTO public.conversao_offline_decisao (rodada, customer_id, operating_account_id, product_destination_id, transaction_id, visita_ref, clique_tipo, clique_sha256, ocorrido_em, estado, coorte_data, coorte_campanha, coorte_dominio, motivo, detalhe, valor, moeda, estimado, valor_impressao, proveniencia) VALUES ('%s','1111111111','1111111111','900001','%s','v1','gclid','%s',%s,'%s','2026-10-10','cup-lab','lab.invalid',%s,%s,%s,%s,%s,%s,'%s'::jsonb) ON CONFLICT DO NOTHING RETURNING estado;" \
    "$rodada" "$tid" "$W14_SHA" "$5" "$1" "$3" "$( [ "$3" = NULL ] && echo NULL || echo "'detalhe'")" "$2" \
    "$( [ "$2" = NULL ] && echo NULL || echo "'BRL'")" "$( [ "$2" = NULL ] && echo NULL || echo true)" \
    "$( [ "$2" = NULL ] && echo NULL || echo "'$vimp'")" "$4"
}
W14_PROV='{"receita":{"fonte":"joinads"},"cambio":{"modo":"exata"}}'
W14_HORA="'2026-10-10T10:00:00-03:00'"
w14_prov_rateio() { # sessoes teto
  printf '{"receita":{"fonte":"joinads"},"cambio":{"modo":"exata"},"metodo":"rateio_uniforme_por_sessao","sessoes_da_coorte":%s,"teto_da_coorte":"%s"}' "$1" "$2"
}
# validate_only aceito de <impressao> com <tids>, e depois o real do mesmo envelope
w14_val_e_real() { # impressao tids
  printf "SELECT public.conversao_offline_fechar_lote((%s), 'aceito', NULL, '{}'::jsonb); SELECT public.conversao_offline_abrir_lote(jsonb_set('%s'::jsonb, '{validacao_lote_id}', to_jsonb((SELECT max(id) FROM public.conversao_offline_lote WHERE modo='validate_only' AND impressao='%s')))) > 0;" \
    "$(w14_abrir validate_only "$1" "$2")" "$(w14_lote_json real "$1" "$2" 0)" "$1"
}
W14_DEC="$(w14_decisao elegivel 12.34 NULL "$W14_PROV" "$W14_HORA" "$W14_TID1") $(w14_decisao elegivel 12.34 NULL "$W14_PROV" "$W14_HORA" "$W14_TID2")"
W14_VAL_A="$W14_DEC $W14_VAL_A_NU"

w14_suite() {
  echo "▶ v25 · pré-condições"
  eq "$(basename "${MIGRATION:-}")|$(basename "${ROLLBACK:-}")" "v25_01_conversao_offline_ledger.sql|v25_01_rollback.sql" "v25 · MIGRATION/ROLLBACK do recibo são a v25_01"
  eq "$(w14_aplicada)" "f" "v25 · antes: v25_01 não aplicada"
  w14_fp antes

  echo "▶ v25 · aplicar"
  w14_aplicar aplicar && ok "v25 · aplicou pelo supabase_admin" || nao "v25 · aplicar ($(tail -1 "$RECIBOS/w14-aplicar.out"))"
  eq "$(w14_aplicada)" "t" "v25 · tabelas existem"
  w14_fp depois1
  w14_aplicar por-cima && nao "v25 · reaplicar por cima passou" || \
    { grep -q 'não reaplica por cima' "$RECIBOS/w14-por-cima.out" && ok "v25 · reaplicar por cima recusado" || nao "v25 · por cima falhou por outro motivo"; }

  echo "▶ v25 · privilégios"
  local t
  for t in conversao_offline_decisao conversao_offline_lote conversao_offline_item; do
    eq "$(w14_bloco anon "SELECT count(*) FROM public.$t;")" "ERRO:42501" "v25 · anon não lê $t"
    eq "$(w14_bloco authenticated "SELECT count(*) FROM public.$t;")" "ERRO:42501" "v25 · authenticated não lê $t"
    eq "$(w14_bloco service_role "SELECT count(*) FROM public.$t;")" "ok:0" "v25 · service_role lê $t"
  done
  eq "$(w14_bloco anon "$(w14_abrir validate_only "$W14_IMP_A" "$W14_TID1");")" "ERRO:42501" "v25 · anon não abre lote"
  eq "$(w14_bloco authenticated "$(w14_abrir validate_only "$W14_IMP_A" "$W14_TID1");")" "ERRO:42501" "v25 · authenticated não abre lote"
  eq "$(w14_bloco anon "$(w14_decisao pulado NULL "'receita_ausente'" '{}' NULL)")" "ERRO:42501" "v25 · anon não grava decisão"
  eq "$(w14_bloco service_role "$(w14_abrir validate_only "$W14_IMP_A" "$W14_TID1") > 0;")" "ok:t" "v25 · service_role abre lote pela RPC"
  eq "$(w14_bloco service_role "INSERT INTO public.conversao_offline_lote (impressao, modo, customer_id, login_customer_id, operating_account_id, product_destination_id, itens) VALUES ('$W14_IMP_A','validate_only','1111111111','2222222222','1111111111','900001',1);")" "ERRO:42501" "v25 · service_role não escreve lote direto"
  eq "$(w14_bloco service_role "$W14_VAL_A UPDATE public.conversao_offline_lote SET estado='sucesso';")" "ERRO:42501" "v25 · service_role não altera lote direto"
  eq "$(w14_bloco service_role "$(w14_decisao pulado NULL "'receita_ausente'" '{}' NULL) DELETE FROM public.conversao_offline_decisao;")" "ERRO:42501" "v25 · service_role não apaga decisão"

  echo "▶ v25 · decisão"
  eq "$(w14_bloco service_role "$(w14_decisao elegivel 12.34 NULL "$W14_PROV" "'2026-10-10T10:00:00-03:00'")")" "ok:elegivel" "v25 · elegível com valor, moeda, hora e proveniência"
  eq "$(w14_bloco service_role "$(w14_decisao elegivel 0 NULL "$W14_PROV" "'2026-10-10T10:00:00-03:00'")")" "ERRO:23514" "v25 · elegível com valor 0 recusado"
  eq "$(w14_bloco service_role "$(w14_decisao elegivel 10 NULL '{}' "'2026-10-10T10:00:00-03:00'")")" "ERRO:23514" "v25 · elegível sem proveniência de receita e câmbio recusado"
  eq "$(w14_bloco service_role "$(w14_decisao elegivel 12.34 NULL "$W14_PROV" NULL)")" "ERRO:23514" "v25 · elegível sem hora recusado"
  eq "$(w14_bloco service_role "$(w14_decisao pulado 5 "'receita_imatura'" '{}' NULL)")" "ERRO:23514" "v25 · pulado com valor recusado"
  eq "$(w14_bloco service_role "$(w14_decisao pulado NULL NULL '{}' NULL)")" "ERRO:23514" "v25 · pulado sem motivo recusado"
  eq "$(w14_bloco service_role "$(w14_decisao pulado NULL "'receita_ausente'" '{}' NULL) $(w14_decisao pulado NULL "'receita_ausente'" '{}' NULL) SELECT count(*) FROM public.conversao_offline_decisao;")" "ok:1" \
     "v25 · repetir a mesma decisão da mesma rodada é no-op (ON CONFLICT DO NOTHING)"
  eq "$(w14_bloco postgres "$(w14_decisao pulado NULL "'receita_ausente'" '{}' NULL) UPDATE public.conversao_offline_decisao SET detalhe='x';")" "ERRO:55000" "v25 · decisão é append-only (UPDATE)"
  eq "$(w14_bloco postgres "$(w14_decisao pulado NULL "'receita_ausente'" '{}' NULL) DELETE FROM public.conversao_offline_decisao;")" "ERRO:55000" "v25 · decisão não se apaga (DELETE)"
  eq "$(w14_bloco postgres "TRUNCATE public.conversao_offline_decisao;")" "ERRO:55000" "v25 · decisão não se apaga (TRUNCATE)"

  echo "▶ v25 · lote"
  local real_a="SELECT public.conversao_offline_abrir_lote(jsonb_set('$(w14_lote_json real "$W14_IMP_A" "$W14_TID1" 0)'::jsonb, '{validacao_lote_id}', to_jsonb($W14_VAL_ID)))"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT estado FROM public.conversao_offline_lote;")" "ok:aceito" "v25 · validate_only em_voo → aceito"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_fechar_lote($W14_VAL_ID, 'sucesso', NULL, '{}');")" "ERRO:55000" "v25 · validate_only não vai para sucesso"
  eq "$(w14_bloco service_role "$(w14_abrir real "$W14_IMP_A" "$W14_TID1" 999999);")" "ERRO:55000" "v25 · real sem validate_only existente recusado"
  eq "$(w14_bloco service_role "SELECT public.conversao_offline_fechar_lote(($(w14_abrir validate_only "$W14_IMP_A" "$W14_TID1")), 'recusado', NULL, '{}'); $real_a;")" "ERRO:55000" \
     "v25 · real com validate_only RECUSADO recusado"
  eq "$(w14_bloco service_role "SELECT public.conversao_offline_fechar_lote(($(w14_abrir validate_only "$W14_IMP_B" "$W14_TID1")), 'aceito', NULL, '{}'); SELECT public.conversao_offline_abrir_lote(jsonb_set('$(w14_lote_json real "$W14_IMP_A" "$W14_TID1" 0)'::jsonb, '{validacao_lote_id}', to_jsonb((SELECT max(id) FROM public.conversao_offline_lote))));")" "ERRO:55000" \
     "v25 · real com validate_only de OUTRO envelope recusado"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_abrir_lote(jsonb_set('$(w14_lote_json real "$W14_IMP_A" "$W14_TID1" 0 "$W14_IMP_B")'::jsonb, '{validacao_lote_id}', to_jsonb($W14_VAL_ID)));")" "ERRO:23514" \
     "v25 · aprovação de outra impressão recusada"
  eq "$(w14_bloco service_role "$W14_VAL_A $real_a > 0;")" "ok:t" "v25 · real com validate_only aceito e aprovação da mesma impressão abre"
  eq "$(w14_bloco service_role "$W14_VAL_A $real_a; $real_a;")" "ERRO:23505" "v25 · segundo envio real vivo do mesmo envelope recusado"
  eq "$(w14_bloco service_role "$W14_VAL_A $real_a; SELECT public.conversao_offline_fechar_lote(($(w14_abrir validate_only "$W14_IMP_B" "$W14_TID1")), 'aceito', NULL, '{}'); SELECT public.conversao_offline_abrir_lote(jsonb_set('$(w14_lote_json real "$W14_IMP_B" "$W14_TID1" 0)'::jsonb, '{validacao_lote_id}', to_jsonb((SELECT max(id) FROM public.conversao_offline_lote WHERE modo='validate_only'))));")" "ERRO:23505" \
     "v25 · mesmo transaction_id em outro envelope com envio real vivo recusado"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_fechar_lote(($real_a), 'aceito', NULL, '{}');")" "ERRO:23514" "v25 · real aceito sem request_id recusado"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_fechar_lote(($real_a), 'aceito', 'req-1', '{}'); SELECT estado||'|'||request_id FROM public.conversao_offline_lote WHERE modo='real';")" "ok:aceito|req-1" "v25 · real em_voo → aceito com request_id"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_fechar_lote(($real_a), 'aceito', 'req-1', '{}'); SELECT public.conversao_offline_fechar_lote((SELECT id FROM public.conversao_offline_lote WHERE modo='real'), 'sucesso', 'req-1', '{}'); SELECT string_agg(estado, ',') FROM public.conversao_offline_item WHERE modo='real';")" "ok:sucesso" \
     "v25 · reconciliação aceito → sucesso, e o item acompanha"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_fechar_lote(($real_a), 'aceito', 'req-1', '{}'); SELECT public.conversao_offline_fechar_lote((SELECT id FROM public.conversao_offline_lote WHERE modo='real'), 'em_voo', NULL, '{}');")" "ERRO:55000" \
     "v25 · transição para trás recusada"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_fechar_lote(($real_a), 'recusado', NULL, '{}'); $real_a > 0;")" "ok:t" "v25 · envio real recusado libera o mesmo envelope"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_fechar_lote(($real_a), 'sem_resposta', NULL, '{}'); $real_a; SELECT string_agg(l.estado || '/' || i.estado, ',' ORDER BY l.id) FROM public.conversao_offline_lote l JOIN public.conversao_offline_item i ON i.lote_id = l.id WHERE l.modo='real';")" "ok:reenviado/reenviado,em_voo/em_voo" \
     "v25 · sem_resposta só sai pelo reenvio do MESMO envelope (o velho vira reenviado)"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_fechar_lote(($real_a), 'sem_resposta', NULL, '{}'); SELECT public.conversao_offline_fechar_lote((SELECT id FROM public.conversao_offline_lote WHERE modo='real'), 'reenviado', NULL, '{}');")" "ERRO:55000" \
     "v25 · reenviado não se marca à mão pela RPC de fechar"
  local val_b="SELECT public.conversao_offline_fechar_lote(($(w14_abrir validate_only "$W14_IMP_B" "$W14_TID1")), 'aceito', NULL, '{}');"
  local real_b="SELECT public.conversao_offline_abrir_lote(jsonb_set('$(w14_lote_json real "$W14_IMP_B" "$W14_TID1" 0)'::jsonb, '{validacao_lote_id}', to_jsonb((SELECT max(id) FROM public.conversao_offline_lote WHERE modo='validate_only' AND impressao='$W14_IMP_B'))))"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_fechar_lote(($real_a), 'sem_resposta', NULL, '{}'); $val_b $real_b;")" "ERRO:23505" \
     "v25 · transaction_id em sem_resposta prende também em OUTRO envelope"
  eq "$(w14_bloco service_role "$W14_VAL_A $real_a; SELECT public.conversao_offline_fechar_lote(($(w14_abrir validate_only "$W14_IMP_A" "$W14_TID2")), 'aceito', NULL, '{}'); SELECT public.conversao_offline_abrir_lote(jsonb_set('$(w14_lote_json real "$W14_IMP_A" "$W14_TID2" 0)'::jsonb, '{validacao_lote_id}', to_jsonb((SELECT max(id) FROM public.conversao_offline_lote WHERE modo='validate_only'))));")" "ERRO:23505" \
     "v25 · a impressão do envelope sozinha já impede o segundo envio real vivo"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_fechar_lote(($real_a), 'sem_resposta', NULL, '{}'); SELECT public.conversao_offline_fechar_lote((SELECT id FROM public.conversao_offline_lote WHERE modo='real'), 'sucesso', 'x', '{}');")" "ERRO:55000" \
     "v25 · sem_resposta não vira sucesso sem verificação"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_fechar_lote(($real_a), 'aceito', 'req-1', '{}'); SELECT public.conversao_offline_fechar_lote((SELECT id FROM public.conversao_offline_lote WHERE modo='real'), 'falha', 'req-1', '{}'); $real_a > 0;")" "ok:t" \
     "v25 · falha confirmada libera o reenvio"
  eq "$(w14_bloco postgres "$W14_VAL_A UPDATE public.conversao_offline_lote SET impressao='$W14_IMP_B';")" "ERRO:55000" "v25 · identidade do lote imutável (até para postgres)"
  eq "$(w14_bloco postgres "$W14_VAL_A SELECT public.conversao_offline_fechar_lote(($real_a), 'aceito', 'req-1', '{}'); UPDATE public.conversao_offline_lote SET request_id='req-2' WHERE modo='real';")" "ERRO:55000" "v25 · request_id gravado não muda"
  eq "$(w14_bloco postgres "$W14_VAL_A DELETE FROM public.conversao_offline_lote WHERE modo='validate_only';")" "ERRO:55000" "v25 · lote não se apaga"
  eq "$(w14_bloco postgres "$W14_VAL_A UPDATE public.conversao_offline_item SET transaction_id='$W14_TID2';")" "ERRO:55000" "v25 · item só muda de estado"
  echo "▶ v25 · proveniência, itens e pedido (revisão W14, ciclo 1)"
  eq "$(w14_bloco service_role "$W14_VAL_A_NU $real_a;")" "ERRO:55000" "v25 · real sem decisão elegível gravada recusado"
  eq "$(w14_bloco service_role "$(w14_decisao elegivel 12.34 NULL "$W14_PROV" "$W14_HORA" "$W14_TID1" "$W14_IMP_B") $W14_VAL_A_NU $real_a;")" "ERRO:55000" \
     "v25 · decisão elegível com OUTRO valor não serve"
  eq "$(w14_bloco service_role "$(w14_decisao pulado NULL "'receita_imatura'" '{}' NULL) $W14_VAL_A_NU $real_a;")" "ERRO:55000" "v25 · decisão pulada não serve"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_abrir_lote(jsonb_set('$(w14_lote_json real "$W14_IMP_A" "$W14_TID1,$W14_TID2" 0)'::jsonb, '{validacao_lote_id}', to_jsonb($W14_VAL_ID)));")" "ERRO:55000" \
     "v25 · real com item a MAIS que o validado recusado"
  eq "$(w14_bloco service_role "$W14_DEC SELECT public.conversao_offline_fechar_lote(($(w14_abrir validate_only "$W14_IMP_A" "$W14_TID1,$W14_TID2")), 'aceito', NULL, '{}'); $real_a;")" "ERRO:55000" \
     "v25 · real com item a MENOS que o validado recusado"
  eq "$(w14_bloco service_role "$W14_VAL_A SELECT public.conversao_offline_fechar_lote(($real_a), 'aceito', 'req-1', '{}'); SELECT public.conversao_offline_fechar_lote((SELECT id FROM public.conversao_offline_lote WHERE modo='real'), 'sucesso', 'req-2', '{}');")" "ERRO:55000" \
     "v25 · fechar com o pedido de OUTRO lote recusado"
  local sem_destino="SELECT public.conversao_offline_abrir_lote(jsonb_set(jsonb_set('$(w14_lote_json real "$W14_IMP_A" "$W14_TID1" 0)'::jsonb, '{validacao_lote_id}', to_jsonb($W14_VAL_ID))"
  eq "$(w14_bloco service_role "$W14_VAL_A $sem_destino, '{aprovacao}', ('$(w14_lote_json real "$W14_IMP_A" "$W14_TID1" 0)'::jsonb -> 'aprovacao') - 'destino_primario'));")" "ERRO:23514" \
     "v25 · aprovação sem destino_primario declarado recusada"
  eq "$(w14_bloco service_role "$W14_VAL_A $sem_destino, '{aprovacao}', ('$(w14_lote_json real "$W14_IMP_A" "$W14_TID1" 0)'::jsonb -> 'aprovacao') - 'impressao'));")" "ERRO:23514" \
     "v25 · aprovação sem impressão recusada (chave ausente não é NULL que passa)"
  eq "$(w14_bloco service_role "$(w14_decisao elegivel NULL NULL "$W14_PROV" "$W14_HORA")")" "ERRO:23514" "v25 · elegível sem valor recusado"
  eq "$(w14_bloco service_role "$W14_VAL_A $sem_destino, '{aprovacao,destino_primario}', '\"nao\"'::jsonb));")" "ERRO:23514" \
     "v25 · destino_primario que não é booleano recusado"
  eq "$(w14_bloco service_role "$W14_VAL_A $sem_destino, '{aprovacao,aprovado_em}', '\"ontem\"'::jsonb));")" "ERRO:23514" \
     "v25 · aprovado_em fora de ISO-8601 com fuso recusado"
  eq "$(w14_bloco service_role "$W14_VAL_A $sem_destino, '{aprovacao,aprovado_por}', '\"   \"'::jsonb));")" "ERRO:23514" \
     "v25 · aprovador em branco recusado"
  eq "$(w14_bloco service_role "$(w14_decisao elegivel 12.34 NULL '{"receita":"joinads","cambio":{"modo":"exata"}}' "$W14_HORA")")" "ERRO:23514" \
     "v25 · proveniência de receita que não é objeto recusada"
  eq "$(w14_bloco service_role "$(w14_decisao pulado NULL "'   '" '{}' NULL)")" "ERRO:23514" "v25 · motivo em branco recusado"
  eq "$(w14_bloco anon "SELECT nextval('public.conversao_offline_lote_id_seq');")" "ERRO:42501" "v25 · anon não usa a sequência do lote"
  eq "$(w14_bloco anon "SELECT nextval('public.conversao_offline_decisao_id_seq');")" "ERRO:42501" "v25 · anon não usa a sequência da decisão"

  echo "▶ v25 · teto do rateio por coorte (revisão nuvem 2, obrigatório 2)"
  d2() { echo "$(w14_decisao elegivel 12.34 NULL "$(w14_prov_rateio "$1" "$2")" "$W14_HORA" "$W14_TID1") $(w14_decisao elegivel 12.34 NULL "$(w14_prov_rateio "$1" "$2")" "$W14_HORA" "$W14_TID2")"; }
  eq "$(w14_bloco service_role "$(d2 2 24.68) $(w14_val_e_real "$W14_IMP_A" "$W14_TID1,$W14_TID2")")" "ok:t" "v25 · 2 cliques, 2 sessões, soma = teto: abre"
  eq "$(w14_bloco service_role "$(d2 1 24.68) $(w14_val_e_real "$W14_IMP_A" "$W14_TID1,$W14_TID2")")" "ERRO:23514" "v25 · mais cliques que sessões recusado"
  eq "$(w14_bloco service_role "$(d2 2 20.00) $(w14_val_e_real "$W14_IMP_A" "$W14_TID1,$W14_TID2")")" "ERRO:23514" "v25 · soma acima do teto recusada"
  eq "$(w14_bloco service_role "$(d2 2 24.68) $(w14_val_e_real "$W14_IMP_A" "$W14_TID1") $(w14_val_e_real "$W14_IMP_B" "$W14_TID2") SELECT itens_vivos || '|' || soma_valor FROM public.conversao_offline_envio_por_coorte;")" "ok:2|24.68" \
     "v25 · segundo envio da coorte cabe no teto e a view soma os dois"
  eq "$(w14_bloco service_role "$(d2 1 12.34) $(w14_val_e_real "$W14_IMP_A" "$W14_TID1") $(w14_val_e_real "$W14_IMP_B" "$W14_TID2")")" "ERRO:23514" \
     "v25 · o já enviado de OUTRO lote conta no teto da coorte"
  eq "$(w14_bloco service_role "$(d2 2 20.00) $(w14_val_e_real "$W14_IMP_A" "$W14_TID1") $(w14_val_e_real "$W14_IMP_B" "$W14_TID2")")" "ERRO:23514" \
     "v25 · a SOMA do já enviado conta no teto (sessões sobrando, dinheiro não)"
  eq "$(w14_bloco service_role "$(d2 1 12.34) $(w14_val_e_real "$W14_IMP_A" "$W14_TID1") SELECT public.conversao_offline_fechar_lote((SELECT max(id) FROM public.conversao_offline_lote WHERE modo='real'), 'sem_resposta', NULL, '{}'); SELECT public.conversao_offline_abrir_lote(jsonb_set('$(w14_lote_json real "$W14_IMP_A" "$W14_TID1" 0)'::jsonb, '{validacao_lote_id}', to_jsonb((SELECT max(id) FROM public.conversao_offline_lote WHERE modo='validate_only')))) > 0;")" "ok:t" \
     "v25 · reenvio do mesmo envelope não conta duas vezes no teto"
  eq "$(w14_bloco service_role "$(w14_decisao elegivel 12.34 NULL "$(w14_prov_rateio 2 10.00)" "$W14_HORA")")" "ERRO:23514" "v25 · decisão de rateio com valor acima do teto recusada"
  eq "$(w14_bloco service_role "$(w14_decisao elegivel 12.34 NULL '{"receita":{},"cambio":{},"metodo":"rateio_uniforme_por_sessao"}' "$W14_HORA")")" "ERRO:23514" "v25 · decisão de rateio sem sessões e teto recusada"
  eq "$(w14_bloco anon "SELECT count(*) FROM public.conversao_offline_envio_por_coorte;")" "ERRO:42501" "v25 · anon não lê a soma por coorte"
  eq "$(w14_bloco authenticated "SELECT count(*) FROM public.conversao_offline_envio_por_coorte;")" "ERRO:42501" "v25 · authenticated não lê a soma por coorte"
  eq "$(w14_bloco service_role "SELECT count(*) FROM public.conversao_offline_envio_por_coorte;")" "ok:0" "v25 · service_role lê a soma por coorte"

  eq "$(w14_bloco service_role "SELECT public.conversao_offline_abrir_lote('$(w14_lote_json validate_only "$W14_IMP_A" "$W14_TID1")'::jsonb || '{\"aprovacao\":{\"x\":1}}'::jsonb);")" "ERRO:22023" \
     "v25 · validate_only não carrega aprovação"

  echo "▶ v25 · teto sob concorrência (revisão nuvem 2, ressalva)"
  # Duas sessões de verdade, COMMITADAS: A abre o real e segura a transação;
  # B abre o real da mesma coorte em paralelo. Sem a trava por coorte, as duas
  # passam (80 para teto 50). Limpeza depois, pelo dono, com os gatilhos off.
  local pc; pc=$(w14_prov_rateio 2 50.00)
  local sa="BEGIN; SET LOCAL ROLE service_role; $(w14_decisao elegivel 40.00 NULL "$pc" "$W14_HORA" "$W14_TID1" "$W14_VIMP" corrida) $(w14_val_e_real "$W14_IMP_A" "$W14_TID1") SELECT pg_sleep(2); COMMIT;"
  local sb="BEGIN; SET LOCAL ROLE service_role; $(w14_decisao elegivel 40.00 NULL "$pc" "$W14_HORA" "$W14_TID2" "$W14_VIMP" corrida) $(w14_val_e_real "$W14_IMP_B" "$W14_TID2") COMMIT;"
  ( printf '\\set VERBOSITY sqlstate\n%s\n' "$sa" | P > "$RECIBOS/w14-corrida-a.out" 2>&1 ) &
  local pid=$!
  sleep 0.7
  printf '\\set VERBOSITY sqlstate\n%s\n' "$sb" | P > "$RECIBOS/w14-corrida-b.out" 2>&1
  wait "$pid"
  eq "$(grep -c '^t$' "$RECIBOS/w14-corrida-a.out")" "1" "v25 · corrida: a sessão A abre o real"
  eq "$(grep -oE '(ERROR|ERRO):  [0-9A-Z]{5}' "$RECIBOS/w14-corrida-b.out" | head -1 | awk '{print $2}')" "23514" \
     "v25 · corrida: a sessão B, em paralelo na mesma coorte, espera A e é recusada"
  eq "$(P -c "SELECT itens_vivos || '|' || soma_valor FROM public.conversao_offline_envio_por_coorte" 2>&1)" "1|40.00" \
     "v25 · corrida: o vivo da coorte fica dentro do teto"
  PA -c "ALTER TABLE public.conversao_offline_item DISABLE TRIGGER USER; ALTER TABLE public.conversao_offline_lote DISABLE TRIGGER USER; ALTER TABLE public.conversao_offline_decisao DISABLE TRIGGER USER; DELETE FROM public.conversao_offline_item; DELETE FROM public.conversao_offline_lote; DELETE FROM public.conversao_offline_decisao WHERE rodada='corrida'; ALTER TABLE public.conversao_offline_item ENABLE TRIGGER USER; ALTER TABLE public.conversao_offline_lote ENABLE TRIGGER USER; ALTER TABLE public.conversao_offline_decisao ENABLE TRIGGER USER;" >/dev/null 2>&1 \
    && ok "v25 · corrida: limpeza de teste pelo dono" || nao "v25 · corrida: limpeza"

  echo "▶ v25 · reverter"
  PA -c "INSERT INTO public.conversao_offline_decisao (rodada, customer_id, operating_account_id, product_destination_id, transaction_id, visita_ref, clique_tipo, clique_sha256, estado, coorte_data, coorte_campanha, coorte_dominio, motivo, detalhe) VALUES ('lab','1111111111','1111111111','900001','$W14_TID1','v1','gclid','$W14_SHA','pulado','2026-10-10','cup-lab','lab.invalid','receita_ausente','lab')" >/dev/null 2>&1 \
    && ok "v25 · semente de rastro gravada" || nao "v25 · semente de rastro"
  w14_reverter com-dado && nao "v25 · rollback com rastro passou" || \
    { grep -q 'o rastro não é apagado' "$RECIBOS/w14-com-dado.out" && ok "v25 · rollback recusa com rastro" || nao "v25 · rollback com dado falhou por outro motivo"; }
  eq "$(w14_aplicada)" "t" "v25 · recusa do rollback é atômica"
  PA -c "ALTER TABLE public.conversao_offline_decisao DISABLE TRIGGER conversao_offline_decisao_imutavel; DELETE FROM public.conversao_offline_decisao WHERE rodada='lab'; ALTER TABLE public.conversao_offline_decisao ENABLE TRIGGER conversao_offline_decisao_imutavel;" >/dev/null 2>&1 \
    && ok "v25 · limpeza de teste pelo dono" || nao "v25 · limpeza de teste"
  w14_reverter reverter && ok "v25 · rollback aplicou" || nao "v25 · rollback ($(tail -1 "$RECIBOS/w14-reverter.out"))"
  eq "$(w14_aplicada)" "f" "v25 · tabelas sumiram"
  w14_fp depois-reverter
  diff -q "$RECIBOS/w14-fp-antes.out" "$RECIBOS/w14-fp-depois-reverter.out" >/dev/null && ok "v25 · rollback devolve o fingerprint de antes" || nao "v25 · rollback deixou resíduo"
  w14_reverter de-novo && ok "v25 · rollback idempotente" || nao "v25 · rollback idempotente"

  echo "▶ v25 · reaplicar"
  w14_aplicar reaplicar && ok "v25 · reaplicou" || nao "v25 · reaplicar ($(tail -1 "$RECIBOS/w14-reaplicar.out"))"
  w14_fp depois2
  diff -q "$RECIBOS/w14-fp-depois1.out" "$RECIBOS/w14-fp-depois2.out" >/dev/null && ok "v25 · fingerprint idêntico entre aplicações" || nao "v25 · fingerprint divergiu"
  diff -q "$RECIBOS/w14-fp-antes.out" "$RECIBOS/w14-fp-depois1.out" >/dev/null && nao "v25 · fingerprint não mudou" || ok "v25 · fingerprint muda com a migration"
  w14_reverter limpeza && ok "v25 · rollback de limpeza" || nao "v25 · limpeza final"
}

w14_suite
