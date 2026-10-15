# shellcheck shell=bash
# =============================================================================
# tools/freedom-lab/db/suites/v26_w15.sh — suíte da v26_01 (W15) para o lab.sh
#
# Prova oficial (no Mac):
#
#   LAB_DUMP=<dump schema-only, fora do repo> LAB_DUMP_SHA256=<sha256 do dump> \
#   MIGRATION=supabase/migrations/v26_01_meta_insight_latest_completa.sql \
#   ROLLBACK=supabase/migrations/v26_01_rollback.sql \
#   MIGRATION_SUITE=tools/freedom-lab/db/suites/v26_w15.sh \
#   tools/freedom-lab/lab.sh recriar-prod
#
# Usa só o que o lab.sh dá: P (psql como postgres), PA (psql como
# supabase_admin), ok / nao / eq, RAIZ, RECIBOS, MIGRATION, ROLLBACK.
#
# Base: o schema Meta NÃO está no Supabase oficial (SCHEMA-APPLY-RECEIPT de
# 07/09). Por isso a suíte aplica, NO CONTAINER DESCARTÁVEL, a cadeia Meta do
# repositório que faltar (v13_01 → v15_01 → v15_02 → 20260907210000 →
# 20260908000000 → 20260908120000), cada arquivo só se o objeto-chave dele não
# existir. Isso NÃO é ensaio da janela de produção do schema Meta; é o mínimo
# para a v26_01 ter onde rodar.
#
# Prova, sobre v26_01_meta_insight_latest_completa.sql e v26_01_rollback.sql:
#   1. antes: o defeito medido (a incompleta mais nova vence a completa)
#   2. aplicar: a completa mais recente vence; sem completa, a incompleta mais
#      recente com completo=false; uma linha por grão; dependentes de pé
#   3. security_invoker preservado; anon/authenticated sem SELECT; service_role só SELECT
#   4. reaplicar por cima é recusado sem mudar o fingerprint
#   5. rollback devolve o fingerprint de antes; é idempotente; reaplicar é idêntico
#
# Dados sintéticos fixos (conta 9990001, ativo meta_account_metaacct_w15lab,
# ids w15-*). As linhas de fato ficam no container: as tabelas Meta recusam
# DELETE por gatilho, e o container é destruído no fim do recriar-prod.
# Espelho hermético: backend/tests/test_meta_v26_01_latest_completa.py.
# =============================================================================

for _f in P PA ok nao eq; do
  declare -F "$_f" >/dev/null || { echo "ERRO: v26_w15.sh precisa ser carregada pelo lab.sh (falta $_f)" >&2; return 1 2>/dev/null || exit 1; }
done
unset _f

W15_APLICAR="$RAIZ/supabase/migrations/v26_01_meta_insight_latest_completa.sql"
W15_REVERTER="$RAIZ/supabase/migrations/v26_01_rollback.sql"
W15_ATIVO="meta_account_metaacct_w15lab"

w15_sql() { P -Atc "$1" 2>&1 | head -1; }
w15_aplicar()  { PA -v ON_ERROR_STOP=1 -f - < "$W15_APLICAR"  > "$RECIBOS/w15-$1.out" 2>&1; }
w15_reverter() { PA -v ON_ERROR_STOP=1 -f - < "$W15_REVERTER" > "$RECIBOS/w15-$1.out" 2>&1; }
w15_fp() {
  w15_sql "SELECT md5(concat_ws('|',
    pg_get_viewdef('public.vw_trafego_meta_insight_latest'::regclass, true),
    (SELECT array_to_string(reloptions, ',') FROM pg_class WHERE oid = 'public.vw_trafego_meta_insight_latest'::regclass),
    (SELECT array_to_string(relacl, ',') FROM pg_class WHERE oid = 'public.vw_trafego_meta_insight_latest'::regclass),
    obj_description('public.vw_trafego_meta_insight_latest'::regclass, 'pg_class'),
    (SELECT string_agg(attname || ':' || format_type(atttypid, atttypmod), ',' ORDER BY attnum)
       FROM pg_attribute WHERE attrelid = 'public.vw_trafego_meta_insight_latest'::regclass AND attnum > 0)))"
}
W15_CORRENTE="SELECT string_agg(objeto_externo || '=' || meta_insight_daily_id || ':' || completo, ',' ORDER BY objeto_externo)
  FROM public.vw_trafego_meta_insight_latest WHERE ad_account_ativo_id = '$W15_ATIVO'"
W15_ESPERADO_ANTES="1001=w15-a2:false,1002=w15-b2:true,1003=w15-c2:false,1004=w15-d3:true"
W15_ESPERADO_DEPOIS="1001=w15-a1:true,1002=w15-b2:true,1003=w15-c2:false,1004=w15-d3:true"

# Cadeia Meta: arquivo|objeto-chave (SQL que devolve t quando já existe).
W15_CADEIA="v13_01_cofre_de_ativos.sql|select to_regclass('public.cofre_ativo') is not null
v15_01_meta_ads_read_model.sql|select to_regclass('public.trafego_meta_ad_account') is not null
v15_02_meta_ads_insights.sql|select to_regclass('public.trafego_meta_insight_daily') is not null
20260907210000_meta_read_model_consistency.sql|select to_regclass('public.vw_trafego_meta_insight_latest') is not null
20260908000000_meta_insights_escopo.sql|select coalesce((select pg_get_constraintdef(oid) like '%insights_fechamento%' from pg_constraint where conname = 'trafego_meta_sync_escopo_conhecido'), false)
20260908120000_meta_financeiro_conjunto_dia.sql|select to_regclass('public.vw_trafego_meta_financeiro_conjunto_dia') is not null"

w15_fato() {  # $1 id  $2 objeto  $3 observado_em  $4 spend  $5 completo
  printf "INSERT INTO public.trafego_meta_insight_daily (meta_insight_daily_id, ad_account_ativo_id, conta_externa, nivel, objeto_externo, periodo_inicio, periodo_fim, janela_atribuicao, breakdown, observado_em, spend, impressions, currency, account_timezone, completo) VALUES ('%s', '%s', '9990001', 'adset', '%s', '2026-10-10', '2026-10-10', 'default', 'none', '%s', %s, 100, 'BRL', 'America/Sao_Paulo', %s);\n" \
    "$1" "$W15_ATIVO" "$2" "$3" "$4" "$5"
}

w15_suite() {
  mkdir -p "$RECIBOS"
  echo "▶ v26 · base Meta no container"
  eq "$(basename "${MIGRATION:-}")|$(basename "${ROLLBACK:-}")" \
     "v26_01_meta_insight_latest_completa.sql|v26_01_rollback.sql" "v26 · MIGRATION/ROLLBACK do recibo são a v26_01"
  local linha arq chave
  while IFS= read -r linha; do
    arq=${linha%%|*}; chave=${linha#*|}
    if [ "$(w15_sql "$chave")" = "t" ]; then
      ok "v26 · base já tem $arq"
    elif PA -v ON_ERROR_STOP=1 -f - < "$RAIZ/supabase/migrations/$arq" > "$RECIBOS/w15-base-$arq.out" 2>&1; then
      ok "v26 · cadeia Meta: $arq aplicada no container"
    else
      nao "v26 · cadeia Meta: $arq ($(tail -1 "$RECIBOS/w15-base-$arq.out"))"; return 1
    fi
  done <<< "$W15_CADEIA"

  echo "▶ v26 · semente sintética"
  { printf "BEGIN;\n"
    printf "INSERT INTO public.cofre_ativo (ativo_id, kind, cluster, nome, plataforma, estado, criticidade, resumo, dono_nome, dono_custodia, capacidades, proxima_acao) VALUES ('%s', 'meta_ad_account', 'paid_media', 'Conta Meta lab W15', 'Meta Ads', 'ready', 'high', 'Conta sintetica do laboratorio W15.', 'VOLC', 'verified', ARRAY['meta_read'], 'Nenhuma acao: fixture de teste descartavel.') ON CONFLICT (ativo_id) DO NOTHING;\n" "$W15_ATIVO"
    printf "INSERT INTO public.trafego_meta_ad_account (cofre_ativo_id, account_external_id, moeda, timezone_name, readiness_state) VALUES ('%s', '9990001', 'BRL', 'America/Sao_Paulo', 'READY_FOR_READ') ON CONFLICT DO NOTHING;\n" "$W15_ATIVO"
    w15_fato w15-a1 1001 2026-10-11T10:00:00Z 10.00 true
    w15_fato w15-a2 1001 2026-10-15T11:30:00Z 3.00 false
    w15_fato w15-b1 1002 2026-10-11T10:00:00Z 10.00 true
    w15_fato w15-b2 1002 2026-10-15T11:30:00Z 12.50 true
    w15_fato w15-c1 1003 2026-10-11T10:00:00Z 4.00 false
    w15_fato w15-c2 1003 2026-10-15T11:30:00Z 5.00 false
    w15_fato w15-d1 1004 2026-10-11T10:00:00Z 10.00 true
    w15_fato w15-d2 1004 2026-10-13T11:30:00Z 1.00 false
    w15_fato w15-d3 1004 2026-10-15T11:30:00Z 11.00 true
    printf "COMMIT;\n"
  } | PA -v ON_ERROR_STOP=1 > "$RECIBOS/w15-semente.out" 2>&1 \
    && ok "v26 · semente: 4 grãos, 9 revisões" || { nao "v26 · semente ($(tail -1 "$RECIBOS/w15-semente.out"))"; return 1; }

  echo "▶ v26 · antes"
  local fp_antes fp_depois
  fp_antes=$(w15_fp)
  eq "$(w15_sql "$W15_CORRENTE")" "$W15_ESPERADO_ANTES" "v26 · antes: a incompleta mais nova vencia a completa (o defeito)"

  echo "▶ v26 · aplicar"
  w15_aplicar aplicar && ok "v26 · v26_01 aplicou" || { nao "v26 · aplicar ($(tail -1 "$RECIBOS/w15-aplicar.out"))"; return 1; }
  eq "$(w15_sql "$W15_CORRENTE")" "$W15_ESPERADO_DEPOIS" \
     "v26 · completa mais recente vence; sem completa, a incompleta mais recente com completo=false"
  eq "$(w15_sql "select count(*) from public.vw_trafego_meta_insight_latest where ad_account_ativo_id = '$W15_ATIVO'")" "4" \
     "v26 · uma linha por grão"
  eq "$(w15_sql "select to_regclass('public.vw_trafego_meta_financeiro_conjunto_dia') is not null and to_regclass('public.vw_trafego_meta_financeiro_campanha_dia') is not null")" "t" \
     "v26 · views financeiras dependentes continuam de pé"
  eq "$(w15_sql "select array_to_string(reloptions, ',') from pg_class where oid = 'public.vw_trafego_meta_insight_latest'::regclass")" "security_invoker=true" \
     "v26 · security_invoker preservado"
  eq "$(w15_sql "select has_table_privilege('anon','public.vw_trafego_meta_insight_latest','SELECT') or has_table_privilege('authenticated','public.vw_trafego_meta_insight_latest','SELECT')")" "f" \
     "v26 · anon e authenticated sem SELECT"
  eq "$(w15_sql "select has_table_privilege('service_role','public.vw_trafego_meta_insight_latest','SELECT') and not has_table_privilege('service_role','public.vw_trafego_meta_insight_latest','INSERT,UPDATE,DELETE')")" "t" \
     "v26 · service_role só SELECT"

  echo "▶ v26 · por cima, rollback, reaplicar"
  fp_depois=$(w15_fp)
  w15_aplicar por-cima && nao "v26 · reaplicar por cima passou" || \
    { grep -q 'ja parece aplicada' "$RECIBOS/w15-por-cima.out" && ok "v26 · reaplicar por cima recusado pela guarda" || nao "v26 · por cima falhou por outro motivo"; }
  eq "$(w15_fp)" "$fp_depois" "v26 · a recusa não mudou nada"
  w15_reverter reverter && ok "v26 · rollback aplicou" || nao "v26 · rollback ($(tail -1 "$RECIBOS/w15-reverter.out"))"
  eq "$(w15_fp)" "$fp_antes" "v26 · rollback devolve o fingerprint de antes"
  eq "$(w15_sql "$W15_CORRENTE")" "$W15_ESPERADO_ANTES" "v26 · rollback devolve a ordem antiga"
  w15_reverter reverter-2 && ok "v26 · rollback idempotente" || nao "v26 · rollback 2 ($(tail -1 "$RECIBOS/w15-reverter-2.out"))"
  eq "$(w15_fp)" "$fp_antes" "v26 · fingerprint estável no 2º rollback"
  w15_aplicar reaplicar && ok "v26 · reaplicou" || nao "v26 · reaplicar ($(tail -1 "$RECIBOS/w15-reaplicar.out"))"
  eq "$(w15_fp)" "$fp_depois" "v26 · reaplicar dá o fingerprint da 1ª aplicação"
  [ "$fp_antes" != "$fp_depois" ] && ok "v26 · fingerprint muda com a migration" || nao "v26 · fingerprint não mudou"
}

w15_suite
