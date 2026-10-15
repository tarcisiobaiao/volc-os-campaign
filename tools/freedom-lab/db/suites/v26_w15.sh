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
# Base: o recriar-prod parte de um dump schema-only do Supabase oficial. Na
# prova de 2448627 no Mac, a view vw_trafego_meta_insight_latest JÁ estava
# no dump (dono postgres, sem COMMENT); o recibo SCHEMA-APPLY de 07/09, que a
# dava como ausente, está defasado. A suíte confere a cadeia Meta
# (v13_01 → v15_01 → v15_02 → 20260907210000 → 20260908000000 →
# 20260908120000) pelo objeto-chave de cada arquivo e só aplica, NO CONTAINER
# DESCARTÁVEL, o que faltar. Numa base que já tem tudo, nada é aplicado.
#
# Prova, sobre v26_01_meta_insight_latest_completa.sql e v26_01_rollback.sql:
#   1. antes: o defeito medido (a incompleta mais nova vence a completa)
#   2. aplicar: a completa mais recente vence; sem completa, a incompleta mais
#      recente com completo=false; uma linha por grão; dependentes de pé
#   3. security_invoker preservado; anon/authenticated sem SELECT; service_role só SELECT
#   4. reaplicar por cima é recusado sem mudar o fingerprint
#   5. rollback devolve o fingerprint de antes; é idempotente; reaplicar é idêntico
#   6. COMMENT (ou a falta dele), ACL e dono sobrevivem a aplicar e a reverter
#
# As leituras de fingerprint e de COMMENT/ACL/dono são fail-closed: erro do
# psql, saída vazia ou ACL nula viram leitura INVÁLIDA, e comparar uma leitura
# inválida sempre FALHA (duas falhas iguais não passam por igualdade).
#
# Referência: o dump é schema-only, então cofre_gaveta e cofre_tipo chegam
# vazias. A suíte semeia via PA só a gaveta paid_media e o tipo
# (meta_ad_account, paid_media), com ON CONFLICT DO NOTHING, e afirma o par.
# Todo INSERT de prova confere a contagem exata (1 linha) via RETURNING.
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

# No Mac, P e PA são `docker exec -i ... psql`: o docker repassa o stdin
# inteiro do chamador ao container, mesmo com -c. Toda chamada que não lê
# SQL do stdin recebe </dev/null, e os loops leem por fd 3, para que uma
# chamada dentro do loop nunca engula as linhas seguintes.
w15_sql() { P -Atc "$1" < /dev/null 2>&1 | head -1; }
w15_aplicar()  { PA -v ON_ERROR_STOP=1 -f - < "$W15_APLICAR"  > "$RECIBOS/w15-$1.out" 2>&1; }
w15_reverter() { PA -v ON_ERROR_STOP=1 -f - < "$W15_REVERTER" > "$RECIBOS/w15-$1.out" 2>&1; }
# Fingerprint da view: definição, reloptions, ACL, COMMENT e colunas. Com ACL
# nula o SELECT devolve NULL (saída vazia), que w15_fp marca como inválida.
w15_fp() {
  local v
  v=$(w15_sql "SELECT CASE WHEN c.relacl IS NULL THEN NULL ELSE md5(concat_ws('|',
      pg_get_viewdef(c.oid, true),
      coalesce(array_to_string(c.reloptions, ','), '<sem reloptions>'),
      array_to_string(c.relacl, ','),
      coalesce(obj_description(c.oid, 'pg_class'), '<sem COMMENT>'),
      (SELECT string_agg(attname || ':' || format_type(atttypid, atttypmod), ',' ORDER BY attnum)
         FROM pg_attribute WHERE attrelid = c.oid AND attnum > 0))) END
    FROM pg_class c WHERE c.oid = 'public.vw_trafego_meta_insight_latest'::regclass")
  if [[ "$v" =~ ^[0-9a-f]{32}$ ]]; then echo "$v"; else echo "INVALIDO[${v:-vazio ou ACL nula}]"; fi
}
# COMMENT (ou a falta dele), ACL e dono. A v26_01 e o rollback só trocam a
# definição; em produção a view não tem COMMENT, e isso tem de sobreviver.
w15_meta() {
  local v
  v=$(w15_sql "SELECT 'meta=' || coalesce(obj_description(oid, 'pg_class'), '<sem COMMENT>')
      || ' | ' || array_to_string(relacl, ',') || ' | ' || pg_get_userbyid(relowner)
    FROM pg_class WHERE oid = 'public.vw_trafego_meta_insight_latest'::regclass")
  if [[ "$v" == meta=* ]]; then echo "${v#meta=}"; else echo "INVALIDO[${v:-vazio ou ACL nula}]"; fi
}
# Igualdade que FALHA se qualquer lado for leitura inválida.
w15_igual() {  # $1 obtido  $2 esperado  $3 rótulo
  case "$1$2" in
    *INVALIDO\[*) nao "$3 (leitura inválida: obtido=$1 | esperado=$2)"; return 1 ;;
  esac
  eq "$1" "$2" "$3"
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
  printf "INSERT INTO public.trafego_meta_insight_daily (meta_insight_daily_id, ad_account_ativo_id, conta_externa, nivel, objeto_externo, periodo_inicio, periodo_fim, janela_atribuicao, breakdown, observado_em, spend, impressions, currency, account_timezone, completo) VALUES ('%s', '%s', '9990001', 'adset', '%s', '2026-10-10', '2026-10-10', 'default', 'none', '%s', %s, 100, 'BRL', 'America/Sao_Paulo', %s)" \
    "$1" "$W15_ATIVO" "$2" "$3" "$4" "$5"
}

# INSERT de prova com contagem exata: devolve quantas linhas entraram (via
# RETURNING, que independe do -q do psql) e guarda a saída em RECIBOS.
w15_contar() {  # $1 rótulo  $2 INSERT sem ';'
  local saida="$RECIBOS/w15-ins-$1.out"
  PA -v ON_ERROR_STOP=1 -Atc "WITH w15_ins AS ($2 RETURNING 1) SELECT count(*) FROM w15_ins" < /dev/null > "$saida" 2>&1 || return 1
  head -1 "$saida"
}
w15_exige() {  # eq que também devolve o status, para parar a suíte
  eq "$1" "$2" "$3"; [ "$1" = "$2" ]
}
w15_um() {  # $1 rótulo  $2 INSERT sem ';' — exige exatamente 1 linha
  local n
  n=$(w15_contar "$1" "$2") || { nao "v26 · semente $1 ($(tail -1 "$RECIBOS/w15-ins-$1.out"))"; return 1; }
  [ "$n" = "1" ] && ok "v26 · semente $1: 1 linha" || { nao "v26 · semente $1: $n linha(s), esperado 1"; return 1; }
}

w15_suite() {
  mkdir -p "$RECIBOS"
  echo "▶ v26 · base Meta no container"
  eq "$(basename "${MIGRATION:-}")|$(basename "${ROLLBACK:-}")" \
     "v26_01_meta_insight_latest_completa.sql|v26_01_rollback.sql" "v26 · MIGRATION/ROLLBACK do recibo são a v26_01"
  local linha arq chave lidos=0
  while IFS= read -r linha <&3; do
    lidos=$((lidos + 1))
    arq=${linha%%|*}; chave=${linha#*|}
    if [ "$(w15_sql "$chave")" = "t" ]; then
      ok "v26 · base já tem $arq"
    elif PA -v ON_ERROR_STOP=1 -f - < "$RAIZ/supabase/migrations/$arq" > "$RECIBOS/w15-base-$arq.out" 2>&1; then
      ok "v26 · cadeia Meta: $arq aplicada no container"
    else
      nao "v26 · cadeia Meta: $arq ($(tail -1 "$RECIBOS/w15-base-$arq.out"))"; return 1
    fi
  done 3<<< "$W15_CADEIA"
  # Prova de que nenhuma chamada dentro do loop engoliu as linhas seguintes.
  w15_exige "$lidos" "6" "v26 · cadeia Meta: os 6 arquivos foram percorridos" || return 1

  echo "▶ v26 · referência do Cofre (o dump schema-only vem sem dados)"
  # cofre_ativo tem FK (kind, cluster) → cofre_tipo, e cofre_tipo.cluster →
  # cofre_gaveta. O dump de produção é schema-only, então as duas tabelas de
  # referência chegam VAZIAS no container. Semeia só as duas linhas de que a
  # fixture precisa, com os valores literais da v13_01, sem sobrescrever nada
  # que já exista; depois afirma que o par existe.
  w15_contar "ref-gaveta" "INSERT INTO public.cofre_gaveta (cluster, rotulo, descricao, ordem) VALUES ('paid_media', 'Midia paga', 'Gerenciadores e contas que compram midia nas plataformas.', 2) ON CONFLICT DO NOTHING" >/dev/null \
    || { nao "v26 · referência: cofre_gaveta ($(tail -1 "$RECIBOS/w15-ins-ref-gaveta.out"))"; return 1; }
  w15_contar "ref-tipo" "INSERT INTO public.cofre_tipo (kind, cluster, rotulo) VALUES ('meta_ad_account', 'paid_media', 'Conta de anuncios Meta') ON CONFLICT DO NOTHING" >/dev/null \
    || { nao "v26 · referência: cofre_tipo ($(tail -1 "$RECIBOS/w15-ins-ref-tipo.out"))"; return 1; }
  w15_exige "$(w15_sql "select count(*) from public.cofre_gaveta where cluster = 'paid_media'")" "1" \
     "v26 · referência: gaveta paid_media existe" || return 1
  w15_exige "$(w15_sql "select count(*) from public.cofre_tipo where kind = 'meta_ad_account' and cluster = 'paid_media'")" "1" \
     "v26 · referência: tipo (meta_ad_account, paid_media) existe" || return 1

  echo "▶ v26 · semente sintética (cada INSERT confere 1 linha)"
  local fatos="w15-a1 1001 2026-10-11T10:00:00Z 10.00 true
w15-a2 1001 2026-10-15T11:30:00Z 3.00 false
w15-b1 1002 2026-10-11T10:00:00Z 10.00 true
w15-b2 1002 2026-10-15T11:30:00Z 12.50 true
w15-c1 1003 2026-10-11T10:00:00Z 4.00 false
w15-c2 1003 2026-10-15T11:30:00Z 5.00 false
w15-d1 1004 2026-10-11T10:00:00Z 10.00 true
w15-d2 1004 2026-10-13T11:30:00Z 1.00 false
w15-d3 1004 2026-10-15T11:30:00Z 11.00 true"
  w15_um "ativo" "$(printf "INSERT INTO public.cofre_ativo (ativo_id, kind, cluster, nome, plataforma, estado, criticidade, resumo, dono_nome, dono_custodia, capacidades, proxima_acao) VALUES ('%s', 'meta_ad_account', 'paid_media', 'Conta Meta lab W15', 'Meta Ads', 'ready', 'high', 'Conta sintetica do laboratorio W15.', 'VOLC', 'verified', ARRAY['meta_read'], 'Nenhuma acao: fixture de teste descartavel.')" "$W15_ATIVO")" || return 1
  w15_um "conta" "$(printf "INSERT INTO public.trafego_meta_ad_account (cofre_ativo_id, account_external_id, moeda, timezone_name, readiness_state) VALUES ('%s', '9990001', 'BRL', 'America/Sao_Paulo', 'READY_FOR_READ')" "$W15_ATIVO")" || return 1
  local id obj obs spend comp
  while read -r id obj obs spend comp <&3; do
    w15_um "$id" "$(w15_fato "$id" "$obj" "$obs" "$spend" "$comp")" || return 1
  done 3<<< "$fatos"
  w15_exige "$(w15_sql "select count(*) from public.trafego_meta_insight_daily where ad_account_ativo_id = '$W15_ATIVO'")" "9" \
     "v26 · semente: 4 grãos, 9 revisões no fato" || return 1

  echo "▶ v26 · antes"
  local fp_antes fp_depois meta_antes
  fp_antes=$(w15_fp)
  meta_antes=$(w15_meta)
  case "$fp_antes$meta_antes" in
    *INVALIDO\[*) nao "v26 · leitura de antes inválida (fp=$fp_antes | meta=$meta_antes)"; return 1 ;;
  esac
  echo "  ·    COMMENT | ACL | dono antes: $meta_antes"
  eq "$(w15_sql "$W15_CORRENTE")" "$W15_ESPERADO_ANTES" "v26 · antes: a incompleta mais nova vencia a completa (o defeito)"

  echo "▶ v26 · aplicar"
  w15_aplicar aplicar && ok "v26 · v26_01 aplicou" || { nao "v26 · aplicar ($(tail -1 "$RECIBOS/w15-aplicar.out"))"; return 1; }
  eq "$(w15_sql "$W15_CORRENTE")" "$W15_ESPERADO_DEPOIS" \
     "v26 · completa mais recente vence; sem completa, a incompleta mais recente com completo=false"
  w15_igual "$(w15_meta)" "$meta_antes" "v26 · aplicar não mexe em COMMENT, ACL nem dono"
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
  case "$fp_depois" in
    INVALIDO\[*) nao "v26 · fingerprint depois de aplicar inválido ($fp_depois)"; return 1 ;;
  esac
  w15_aplicar por-cima && nao "v26 · reaplicar por cima passou" || \
    { grep -q 'ja parece aplicada' "$RECIBOS/w15-por-cima.out" && ok "v26 · reaplicar por cima recusado pela guarda" || nao "v26 · por cima falhou por outro motivo"; }
  w15_igual "$(w15_fp)" "$fp_depois" "v26 · a recusa não mudou nada"
  w15_reverter reverter && ok "v26 · rollback aplicou" || nao "v26 · rollback ($(tail -1 "$RECIBOS/w15-reverter.out"))"
  w15_igual "$(w15_fp)" "$fp_antes" "v26 · rollback devolve o fingerprint de antes"
  w15_igual "$(w15_meta)" "$meta_antes" "v26 · rollback devolve COMMENT, ACL e dono de antes"
  eq "$(w15_sql "$W15_CORRENTE")" "$W15_ESPERADO_ANTES" "v26 · rollback devolve a ordem antiga"
  w15_reverter reverter-2 && ok "v26 · rollback idempotente" || nao "v26 · rollback 2 ($(tail -1 "$RECIBOS/w15-reverter-2.out"))"
  w15_igual "$(w15_fp)" "$fp_antes" "v26 · fingerprint estável no 2º rollback"
  w15_aplicar reaplicar && ok "v26 · reaplicou" || nao "v26 · reaplicar ($(tail -1 "$RECIBOS/w15-reaplicar.out"))"
  w15_igual "$(w15_fp)" "$fp_depois" "v26 · reaplicar dá o fingerprint da 1ª aplicação"
  [ "$fp_antes" != "$fp_depois" ] && ok "v26 · fingerprint muda com a migration" || nao "v26 · fingerprint não mudou"
}

# W15_SO_FUNCOES=1 só define as funções (usado pelo teste das leituras fail-closed).
[ "${W15_SO_FUNCOES:-0}" = "1" ] || w15_suite
