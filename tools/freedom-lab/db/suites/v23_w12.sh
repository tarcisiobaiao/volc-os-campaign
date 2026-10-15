# shellcheck shell=bash
# =============================================================================
# tools/freedom-lab/db/suites/v23_w12.sh — suíte da v23_01 (W12) para o lab.sh
#
# Prova oficial (no Mac: o dump do schema de produção não entra na nuvem):
#
#   LAB_DUMP=<dump schema-only, fora do repo> LAB_DUMP_SHA256=<sha256 do dump> \
#   MIGRATION=supabase/migrations/v23_01_receita_datada_cambio.sql \
#   ROLLBACK=supabase/migrations/v23_01_rollback.sql \
#   MIGRATION_SUITE=tools/freedom-lab/db/suites/v23_w12.sh \
#   tools/freedom-lab/lab.sh recriar-prod
#
# Roda DENTRO do lab.sh (carregada por ele) e usa só o que ele dá:
#   P            psql no container do lab, como postgres
#   PA           psql como supabase_admin: dono das tabelas na base de produção,
#                por isso aplica, reverte e faz a limpeza de teste (DISABLE TRIGGER)
#   (o P lê o diário, que tem RLS sem policy, porque o postgres do Supabase tem
#    BYPASSRLS; se a base real não tiver, as leituras do diário falham alto)
#   estado       SQL como papel (SET LOCAL ROLE), devolve SQLSTATE ou ok:<1ª linha>, com ROLLBACK
#   sqlstate     SQL como postgres, devolve SQLSTATE ou ok (com COMMIT)
#   ok nao eq    contadores e recibo do lab.sh
#   RAIZ RECIBOS FP MIGRATION ROLLBACK
#
# Base exigida: schema de produção com exchange_rate_history, joinads_metrics
# e gam_metrics. Sobre outra base a pré-checagem acusa "base errada" e FALHA.
#
# O que prova, sobre v23_01_receita_datada_cambio.sql e v23_01_rollback.sql:
#   1. aplicar: linhas manuais viram legado_manual sem as_of; carga inicial
#      registra cada linha de receita existente uma vez
#   2. câmbio: exata, anterior (com defasagem), defasada e sem_cotacao, sem
#      constante; versão coletada vence a manual; replay por conhecido_ate
#   3. guarda: cotação versionada é imutável, só entra por service_role/postgres,
#      coletado_em é do banco, as_of no futuro e duplicata são recusados
#   4. receita: insert, upsert idêntico (sem versão), mudança de valor,
#      troca de chave, delete, falta de câmbio sem derrubar a ingestão,
#      proveniência, as-of e append-only
#   5. matriz anon / authenticated / service_role
#   6. reverter recusa com dado e a recusa é atômica; reverter devolve o
#      fingerprint de antes, é idempotente; reaplicar é idêntico; por cima é recusado
#
# Dados sintéticos fixos (w12-lab-*, *.example.invalid); nenhum dado real.
# Papel simulado por SET LOCAL ROLE: prova o banco, não o PostgREST.
# =============================================================================

for _f in P PA ok nao eq estado sqlstate; do
  declare -F "$_f" >/dev/null || { echo "ERRO: v23_w12.sh precisa ser carregada pelo lab.sh (falta $_f)" >&2; return 1 2>/dev/null || exit 1; }
done
unset _f

W12_APLICAR="$RAIZ/supabase/migrations/v23_01_receita_datada_cambio.sql"
W12_REVERTER="$RAIZ/supabase/migrations/v23_01_rollback.sql"

# Semente que respeita a base real: preenche coluna NOT NULL sem default que o
# teste não deu (por tipo) e cria a conta GAM pai se houver FK. Função de
# sessão (pg_temp): some no fim de cada chamada.
W12_SEMEAR=$(cat <<'SQL'
CREATE FUNCTION pg_temp.w12_semear(tab regclass, base jsonb) RETURNS jsonb LANGUAGE plpgsql AS $f$
DECLARE
  v jsonb := base; r record; cols text; saida jsonb;
BEGIN
  FOR r IN SELECT a.attname, t.typtype, t.typcategory, a.atttypid, format_type(a.atttypid, a.atttypmod) AS tipo
             FROM pg_attribute a JOIN pg_type t ON t.oid = a.atttypid
             LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
            WHERE a.attrelid = tab AND a.attnum > 0 AND NOT a.attisdropped AND a.attnotnull
              AND d.oid IS NULL AND a.attidentity = '' AND a.attgenerated = '' AND NOT base ? a.attname LOOP
    v := v || jsonb_build_object(r.attname, CASE
      WHEN r.typtype = 'e' THEN (SELECT to_jsonb(enumlabel::text) FROM pg_enum WHERE enumtypid = r.atttypid ORDER BY enumsortorder LIMIT 1)
      WHEN r.typcategory = 'A' THEN '[]'::jsonb
      WHEN r.tipo = 'uuid' THEN to_jsonb(gen_random_uuid())
      WHEN r.tipo IN ('json', 'jsonb') THEN '{}'::jsonb
      WHEN r.typcategory = 'N' THEN '0'::jsonb
      WHEN r.typcategory = 'B' THEN 'false'::jsonb
      WHEN r.typcategory = 'D' THEN to_jsonb('2026-10-14'::text)
      ELSE to_jsonb('w12-lab'::text) END);
  END LOOP;
  SELECT string_agg(quote_ident(k), ', ') INTO cols FROM jsonb_object_keys(v) k;
  EXECUTE format('INSERT INTO %s (%s) SELECT %s FROM jsonb_populate_record(NULL::%s, $1) RETURNING to_jsonb(%s.*)',
                 tab, cols, cols, tab, tab) USING v INTO saida;
  RETURN saida;
END
$f$;
CREATE FUNCTION pg_temp.w12_conta_gam() RETURNS jsonb LANGUAGE plpgsql AS $f$
DECLARE
  pai regclass; col text;
BEGIN
  SELECT k.confrelid::regclass, a.attname INTO pai, col
    FROM pg_constraint k JOIN pg_attribute a ON a.attrelid = k.confrelid AND a.attnum = k.confkey[1]
   WHERE k.conrelid = 'public.gam_metrics'::regclass AND k.contype = 'f'
     AND k.conkey = ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid = 'public.gam_metrics'::regclass AND attname = 'gam_accounts_id')];
  IF pai IS NULL THEN RETURN to_jsonb(9001); END IF;
  RETURN pg_temp.w12_semear(pai, '{}'::jsonb) -> col;
END
$f$;
-- Roda um comando e diz QUANTAS linhas afetou ou POR QUE falhou: 0 linhas não
-- pode passar por recusa, nem recusa por 0 linhas. Classifica o 42501:
-- privilegio (GRANT/REVOKE) ou guarda (cambio_versao_guarda).
CREATE FUNCTION pg_temp.w12_tenta(cmd text) RETURNS text LANGUAGE plpgsql AS $f$
DECLARE n bigint;
BEGIN
  EXECUTE cmd;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN 'ok:' || n;
EXCEPTION WHEN others THEN
  RETURN SQLSTATE || ':' || CASE
    WHEN SQLERRM LIKE 'permission denied for table %' THEN 'privilegio(' || split_part(SQLERRM, 'table ', 2) || ')'
    WHEN SQLERRM LIKE 'câmbio só é gravado pela coleta ou pelo servidor%' THEN 'guarda'
    ELSE SQLERRM END;
END
$f$;
SQL
)

w12_sql() { P -c "$1" 2>&1 | head -1; }
# Bloco descartável: roda como postgres numa transação desfeita e devolve a
# última linha (ou ERRO:<sqlstate>). Papel dentro do bloco: SET LOCAL ROLE.
w12_bloco() {
  local out rc
  out=$(printf '\\set VERBOSITY sqlstate\nBEGIN;\n%s\n%s\nROLLBACK;\n' "$W12_SEMEAR" "$1" | P 2>&1); rc=$?
  if [ $rc -ne 0 ]; then echo "ERRO:$(printf '%s\n' "$out" | grep -o 'ERROR: *[0-9A-Z]\{5\}' | head -1 | awk '{print $2}')"; return; fi
  printf '%s\n' "$out" | grep -v '^$' | tail -1
}
# Comando como service_role com a contagem de linhas guardada em w12_t (o
# SELECT final do bloco lê com $W12_T): 0 linhas aparece, não passa calado.
w12_sr() { printf "CREATE TEMP TABLE IF NOT EXISTS w12_t (r text); GRANT ALL ON w12_t TO PUBLIC; SET LOCAL ROLE service_role; INSERT INTO w12_t SELECT pg_temp.w12_tenta(\$c\$%s\$c\$); RESET ROLE;" "$1"; }
W12_T="(SELECT string_agg(r, ',') FROM w12_t)"
w12_confirma() { printf '\\set VERBOSITY sqlstate\nBEGIN;\n%s\n%s\nCOMMIT;\n' "$W12_SEMEAR" "$1" | P > "$RECIBOS/w12-$2.out" 2>&1; }
# Na base de produção as tabelas são de supabase_admin: aplicar e reverter vão
# pelo PA (o dono). A pré-checagem recusa quem não é dono (provado abaixo pelo P).
w12_aplicar()  { PA -f - < "$W12_APLICAR"  > "$RECIBOS/w12-$1.out" 2>&1; }
w12_reverter() { PA -f - < "$W12_REVERTER" > "$RECIBOS/w12-$1.out" 2>&1; }
w12_dono()     { w12_sql "select string_agg(distinct pg_get_userbyid(relowner), ',') from pg_class where oid in ('public.exchange_rate_history'::regclass,'public.joinads_metrics'::regclass,'public.gam_metrics'::regclass)"; }
# Limpeza só de teste, como dono (DISABLE TRIGGER exige dono). Checada.
w12_limpa() { printf '\\set VERBOSITY sqlstate\nBEGIN;\n%s\nCOMMIT;\n' "$1" | PA > "$RECIBOS/w12-$2.out" 2>&1 \
  && ok "v23 · limpeza de teste ($2) pelo dono" || nao "v23 · limpeza de teste ($2): $(tail -1 "$RECIBOS/w12-$2.out")"; }
w12_fp() { P -f - < "$FP" > "$RECIBOS/w12-fp-$1.out" 2>&1; }
w12_aplicada() { w12_sql "select to_regclass('public.receita_observacao') is not null and exists (select 1 from information_schema.columns where table_schema='public' and table_name='exchange_rate_history' and column_name='as_of')"; }

# Cotação versionada sintética (como postgres). $1 data  $2 taxa  $3 as_of
w12_cot() { printf "SELECT pg_temp.w12_semear('public.exchange_rate_history', jsonb_build_object('rate', %s, 'effective_date', '%s', 'fonte', 'bcb_ptax', 'as_of', '%s', 'proveniencia', '{\"lab\":\"w12\"}'::jsonb));" "$2" "$1" "$3"; }
# Linha JoinAds sintética como service_role (o papel do n8n). $1 data  $2 receita  $3 utm
w12_jads() { printf "SET LOCAL ROLE service_role; SELECT pg_temp.w12_semear('public.joinads_metrics', jsonb_build_object('date','%s','utm_campaign_value','%s','joinads_domain','w12-lab.example.invalid','revenue',%s)); RESET ROLE;" "$1" "${3:-w12-lab-utm}" "$2"; }
W12_OBS="select count(*) from public.receita_observacao where chave->>'utm_campaign_value' = 'w12-lab-utm'"

w12_suite() {
  mkdir -p "$RECIBOS"
  echo "▶ v23 · pré-checagem da base"
  local base
  base=$(w12_sql "select to_regclass('public.exchange_rate_history') is not null and to_regclass('public.joinads_metrics') is not null
                    and to_regclass('public.gam_metrics') is not null
                    and exists (select 1 from information_schema.columns where table_schema='public' and table_name='gam_metrics' and column_name='gam_accounts_id')")
  if [ "$base" != "t" ]; then
    nao "v23 · base errada: faltam exchange_rate_history, joinads_metrics ou gam_metrics(gam_accounts_id) (use a base de produção)"
    return 1
  fi
  ok "v23 · base tem as tabelas de receita e de câmbio"
  eq "$(basename "${MIGRATION:-}")|$(basename "${ROLLBACK:-}")" "v23_01_receita_datada_cambio.sql|v23_01_rollback.sql" "v23 · MIGRATION/ROLLBACK do recibo são a v23_01"
  eq "$(w12_aplicada)" "f" "v23 · antes: v23_01 não aplicada"
  local gatilhos_antes
  gatilhos_antes=$(w12_sql "select string_agg(tgrelid::regclass || '.' || tgname, ',' order by 1) from pg_trigger where tgrelid in ('public.joinads_metrics'::regclass, 'public.gam_metrics'::regclass) and not tgisinternal")
  # Ordem exigida (README das migrations): W4 fecha a escrita da anon ANTES da
  # v23_01. O lab simula isso aqui e devolve o ACL original no fim.
  W12_ACL_ORIG=$(w12_sql "select string_agg(case when a.grantee = 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end || ':' || a.privilege_type, ' ')
                            from pg_class c, aclexplode(c.relacl) a
                           where c.oid = 'public.exchange_rate_history'::regclass and a.privilege_type in ('INSERT','UPDATE','DELETE','TRUNCATE')
                             and (a.grantee = 0 or pg_get_userbyid(a.grantee) = 'anon')")
  PA -c "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.exchange_rate_history FROM anon, PUBLIC" >/dev/null 2>&1 \
    && ok "v23 · W4 simulado antes da v23_01: anon sem escrita no câmbio" || nao "v23 · simular W4 (REVOKE anon)"
  w12_fp antes

  echo "▶ v23 · semente anterior à migration (carga inicial)"
  # A taxa 0 em 20/10 é o caso do revisor: linha manual impossível que já exista.
  w12_confirma "SELECT pg_temp.w12_semear('public.exchange_rate_history', jsonb_build_object('rate', 5.25, 'effective_date', '2026-02-18'));
                SELECT pg_temp.w12_semear('public.exchange_rate_history', jsonb_build_object('rate', 0, 'effective_date', '2026-10-20'));
                $(w12_jads 2026-10-01 3.5 w12-lab-carga)" semente \
    && ok "v23 · semente: 2 cotações manuais (uma com taxa 0) e 1 linha JoinAds" || nao "v23 · semente ($(tail -1 "$RECIBOS/w12-semente.out"))"
  eq "$(w12_dono)" "$(w12_sql "select rolname from pg_roles where rolname = 'supabase_admin'")" "v23 · base com as três tabelas de supabase_admin (como o dump de 15/10)"
  # A base restaurada é schema-only: system_settings nasce vazia, e um UPDATE
  # WHERE key = 'dollar_exchange_rate' afetaria 0 linhas sem disparar gatilho
  # nenhum (prova pelo motivo errado). O dono semeia só as chaves que faltam e
  # a suíte devolve no fim. w12_lab_chave é o controle: chave que não é câmbio.
  W12_SS_NOVAS=$(printf '\\set VERBOSITY sqlstate\n%s\nSELECT coalesce(string_agg(s.k, %s), %s) FROM (VALUES (%s), (%s), (%s)) s(k, v), LATERAL (SELECT pg_temp.w12_semear(%s, jsonb_build_object(%s, s.k, %s, s.v))) x WHERE NOT EXISTS (SELECT 1 FROM public.system_settings y WHERE y.key = s.k);\n' \
    "$W12_SEMEAR" "' '" "'-'" "'dollar_exchange_rate', '5.25'" "'usd_brl_rate', '5.25'" "'w12_lab_chave', 'w12'" "'public.system_settings'" "'key'" "'value'" | PA 2>&1 | tail -1)
  eq "$(w12_sql "select count(*)||'|'||bool_and(value is distinct from '6.1234') from public.system_settings where key in ('dollar_exchange_rate', 'usd_brl_rate', 'w12_lab_chave')")" "3|true" \
     "v23 · system_settings com dollar_exchange_rate, usd_brl_rate e a chave de controle (semeadas pelo dono: ${W12_SS_NOVAS})"

  echo "▶ v23 · quem não é dono não aplica"
  P -f - < "$W12_APLICAR" > "$RECIBOS/w12-aplicar-sem-dono.out" 2>&1 && nao "v23 · postgres (não dono) aplicou" || \
    { grep -q 'não é dono de' "$RECIBOS/w12-aplicar-sem-dono.out" && ok "v23 · pré-checagem recusa postgres que não é dono (o rollback não teria como rodar)" || nao "v23 · aplicar sem dono falhou por outro motivo"; }
  eq "$(w12_aplicada)" "f" "v23 · recusa sem dono não deixou resíduo"

  echo "▶ v23 · aplicar"
  w12_aplicar aplicar && ok "v23 · v23_01 aplicou" || nao "v23 · aplicar ($(tail -1 "$RECIBOS/w12-aplicar.out"))"
  eq "$(w12_aplicada)" "t" "v23 · colunas de versão e diário existem"
  w12_fp depois1
  eq "$(w12_sql "select count(*) from public.exchange_rate_history where fonte <> 'legado_manual' or as_of is not null or coletado_em is not null or par <> 'USD/BRL'")" "0" \
     "v23 · linhas manuais anteriores viram legado_manual, sem as_of e sem coletado_em inventado"
  eq "$(w12_sql "select count(*) || '|' || count(*) filter (where operacao='CARGA' and receita=3.5 and data_referencia='2026-10-01') from public.receita_observacao where chave->>'utm_campaign_value'='w12-lab-carga'")" "1|1" \
     "v23 · carga inicial registrou a linha existente uma vez, com data de referência"
  eq "$(w12_sql "select count(*) from public.receita_observacao") " "$(w12_sql "select (select count(*) from public.joinads_metrics) + (select count(*) from public.gam_metrics)") " \
     "v23 · carga inicial cobre todas as linhas de joinads_metrics e gam_metrics"
  eq "$(w12_sql "select string_agg(tgrelid::regclass || '.' || tgname, ',' order by 1) from pg_trigger where tgrelid in ('public.joinads_metrics'::regclass, 'public.gam_metrics'::regclass) and not tgisinternal and tgname not like 'zz_receita_observacao%' and tgname <> 'zz_receita_releitura'")" \
     "$gatilhos_antes" "v23 · gatilhos legados de receita intactos (só zz_receita_observacao* a mais)"

  echo "▶ v23 · câmbio: resolução sem constante"
  local cots
  cots="$(w12_cot 2026-10-13 5.40 '2026-10-13 13:10:00-03') $(w12_cot 2026-10-13 5.41 '2026-10-13 13:15:00-03')
        SELECT pg_temp.w12_semear('public.exchange_rate_history', jsonb_build_object('rate', 9.99, 'effective_date', '2026-10-13'));"
  eq "$(w12_bloco "$cots SELECT modo||'|'||trim_scale(taxa)||'|'||fonte||'|'||defasagem_dias FROM public.cambio_resolver('2026-10-13');")" "exata|5.41|bcb_ptax|0" \
     "v23 · data exata: última publicação da fonte, e a coletada vence a manual do mesmo dia"
  eq "$(w12_bloco "$cots SELECT modo||'|'||trim_scale(taxa)||'|'||data_cotacao||'|'||defasagem_dias FROM public.cambio_resolver('2026-10-15');")" "anterior|5.41|2026-10-13|2" \
     "v23 · sem cotação no dia: última anterior, marcada como anterior e com defasagem"
  eq "$(w12_bloco "$cots SELECT modo||'|'||coalesce(trim_scale(taxa)::text,'NULL')||'|'||defasagem_dias FROM public.cambio_resolver('2026-10-30');")" "defasada|NULL|17" \
     "v23 · cotação mais velha que 7 dias: recusa (taxa NULL), não usa constante"
  eq "$(w12_bloco "$cots SELECT modo||'|'||coalesce(trim_scale(taxa)::text,'NULL') FROM public.cambio_resolver('2026-10-30', 'USD/BRL', 30);")" "anterior|5.41" \
     "v23 · limite de defasagem é parâmetro explícito"
  eq "$(w12_bloco "SELECT modo||'|'||trim_scale(taxa)||'|'||fonte FROM public.cambio_resolver('2026-02-20');")" "anterior|5.25|legado_manual" \
     "v23 · cotação manual legada continua elegível, identificada como legado_manual"
  eq "$(w12_bloco "SELECT modo||'|'||coalesce(trim_scale(taxa)::text,'NULL')||'|'||coalesce(cotacao_id::text,'NULL') FROM public.cambio_resolver('2025-01-01');")" "sem_cotacao|NULL|NULL" \
     "v23 · nenhuma cotação até a data: sem_cotacao, taxa NULL"
  eq "$(w12_bloco "$cots SELECT modo FROM public.cambio_resolver('2026-10-13', 'EUR/BRL');")" "sem_cotacao" \
     "v23 · par sem cotação não herda o USD/BRL"
  eq "$(w12_bloco "$cots SELECT modo||'|'||coalesce(trim_scale(taxa)::text,'NULL') FROM public.cambio_resolver('2026-10-13', 'USD/BRL', 7, now() - interval '1 second');")" "sem_cotacao|NULL" \
     "v23 · replay por conhecido_ate não enxerga cotação coletada depois, nem linha manual (não se sabe quando entrou)"
  eq "$(w12_bloco "SELECT count(*) FROM public.cambio_resolver(NULL);")" "ERRO:22023" "v23 · data nula é recusada"

  echo "▶ v23 · câmbio: guarda de versão"
  eq "$(w12_bloco "$(w12_cot 2026-10-13 5.40 '2026-10-13 13:10:00-03') SELECT coletado_em = now() FROM public.exchange_rate_history WHERE fonte='bcb_ptax';")" "t" \
     "v23 · coletado_em é carimbado pelo banco"
  eq "$(w12_bloco "SELECT pg_temp.w12_semear('public.exchange_rate_history', jsonb_build_object('rate',5.4,'effective_date','2026-10-13','fonte','bcb_ptax','as_of','2026-10-13 13:10-03','coletado_em','2020-01-01')); SELECT coletado_em = now() FROM public.exchange_rate_history WHERE fonte='bcb_ptax';")" "t" \
     "v23 · coletado_em enviado pelo cliente é ignorado"
  eq "$(w12_bloco "$(w12_cot 2026-10-13 5.40 '2026-10-13 13:10:00-03') $(w12_cot 2026-10-13 5.40 '2026-10-13 13:10:00-03') SELECT 1;")" "ERRO:23505" \
     "v23 · mesma versão duas vezes: duplicata recusada (coleta idempotente por on_conflict)"
  eq "$(w12_bloco "$(w12_cot 2026-10-13 5.40 '2026-10-13 13:10:00-03') UPDATE public.exchange_rate_history SET rate = 6 WHERE fonte='bcb_ptax'; SELECT 1;")" "ERRO:23001" \
     "v23 · cotação versionada não aceita UPDATE"
  eq "$(w12_bloco "$(w12_cot 2026-10-13 5.40 '2026-10-13 13:10:00-03') DELETE FROM public.exchange_rate_history WHERE fonte='bcb_ptax'; SELECT 1;")" "ERRO:23001" \
     "v23 · cotação versionada não aceita DELETE"
  eq "$(w12_bloco "UPDATE public.exchange_rate_history SET fonte='bcb_ptax', as_of=now() WHERE fonte='legado_manual'; SELECT 1;")" "ERRO:23001" \
     "v23 · linha manual não vira versionada por UPDATE"
  eq "$(w12_bloco "$(w12_cot 2026-10-13 5.40 '2099-01-01 00:00:00-03') SELECT 1;")" "ERRO:22023" "v23 · as_of no futuro é recusado"
  eq "$(w12_bloco "$(w12_cot 2026-10-13 0 '2026-10-13 13:10:00-03') SELECT 1;")" "ERRO:23514" "v23 · taxa versionada <= 0 é recusada"
  local manual="SELECT pg_temp.w12_semear('public.exchange_rate_history', jsonb_build_object('rate',7.77,'effective_date','2020-12-31','as_of','2020-12-31 12:00-03','coletado_em','2020-01-01','proveniencia','{\"ator\":\"forjado\"}'::jsonb));"
  eq "$(w12_bloco "$manual SELECT fonte||'|'||(as_of >= now())||'|'||(coletado_em = now())||'|'||(proveniencia->>'ator') FROM public.exchange_rate_history WHERE rate = 7.77;")" "manual|true|true|postgres" \
     "v23 · linha manual nova: fonte manual, as_of e coletado_em do servidor, ator do servidor (o do cliente é sobrescrito)"
  eq "$(w12_bloco "$manual SELECT modo FROM public.cambio_resolver('2021-01-01', 'USD/BRL', 7, '2021-01-01');")" "sem_cotacao" \
     "v23 · cotação 'conhecida em 2021' inventada hoje não entra no replay de 2021"
  eq "$(w12_bloco "$manual $manual SELECT count(DISTINCT as_of) FROM public.exchange_rate_history WHERE rate = 7.77;")" "2" \
     "v23 · duas linhas manuais do mesmo dia na mesma transação não colidem (as_of = clock_timestamp)"
  eq "$(w12_bloco "$manual UPDATE public.exchange_rate_history SET rate = 1 WHERE rate = 7.77; SELECT 1;")" "ERRO:23001" \
     "v23 · linha manual nova é imutável"
  eq "$(w12_bloco "SELECT pg_temp.w12_semear('public.exchange_rate_history', jsonb_build_object('rate',0,'effective_date','2026-10-13')); SELECT 1;")" "ERRO:23514" \
     "v23 · linha manual nova com taxa 0 é recusada"
  eq "$(w12_bloco "SELECT pg_temp.w12_semear('public.exchange_rate_history', jsonb_build_object('rate',5.4,'effective_date','2026-10-13','fonte','bcb_ptax')); SELECT 1;")" "ERRO:23514" \
     "v23 · fonte coletada sem as_of é recusada"
  eq "$(w12_bloco "SELECT pg_temp.w12_semear('public.exchange_rate_history', jsonb_build_object('rate',5.39,'effective_date','2026-10-13')); $(w12_cot 2026-10-13 5.41 '2026-10-13 13:15:00-03') SELECT fonte||'|'||trim_scale(taxa) FROM public.cambio_resolver('2026-10-13');")" "bcb_ptax|5.41" \
     "v23 · no mesmo dia a PTAX vence a manual, mesmo a manual sendo gravada depois"
  eq "$(w12_bloco "UPDATE public.exchange_rate_history SET rate = 0 WHERE fonte = 'legado_manual' AND rate = 5.25; SELECT 1;")" "ERRO:23514" \
     "v23 · linha legada não passa a ter taxa 0 por UPDATE (CHECK vale para toda escrita nova)"
  # O dono devolve o GRANT por um instante: só a guarda pode recusar agora.
  PA -c "GRANT INSERT ON public.exchange_rate_history TO authenticated" >/dev/null 2>&1
  eq "$(w12_sql "select has_table_privilege('authenticated','public.exchange_rate_history','INSERT')")|$(estado authenticated "insert into public.exchange_rate_history (rate, effective_date) values (9.99, '2026-10-15')")" "t|42501" \
     "v23 · mesmo com o GRANT de volta, a guarda recusa authenticated (não depende do W4)"
  PA -c "REVOKE INSERT ON public.exchange_rate_history FROM authenticated" >/dev/null 2>&1
  local papel_w
  for papel_w in anon authenticated; do
    eq "$(estado "$papel_w" "insert into public.exchange_rate_history (rate, effective_date) values (9.99, '2026-10-15')")" "42501" "v23 · $papel_w não grava linha manual de câmbio"
    eq "$(estado "$papel_w" "update public.exchange_rate_history set rate = 9.99")" "42501" "v23 · $papel_w não altera câmbio legado"
    eq "$(estado "$papel_w" "delete from public.exchange_rate_history")" "42501" "v23 · $papel_w não apaga câmbio legado"
    eq "$(w12_sql "select has_table_privilege('$papel_w','public.exchange_rate_history','INSERT,UPDATE,DELETE,TRUNCATE')")" "f" "v23 · $papel_w sem escrita no câmbio (REVOKE)"
  done
  eq "$(w12_bloco "SET LOCAL ROLE authenticated; $(w12_cot 2026-10-13 5.40 '2026-10-13 13:10:00-03') SELECT 1;")" "ERRO:42501" \
     "v23 · authenticated não grava cotação versionada"
  # Gatilho vivo de system_settings (trigger_exchange_rate_historical →
  # record_exchange_rate_change, INVOKER como em produção). Cliente não muda o
  # dólar: a guarda e o REVOKE do histórico derrubam o UPDATE inteiro. O
  # servidor muda e a versão sai manual, carimbada.
  local w12_sub='00000000-0000-4000-8000-00000000a012'
  local w12_jwt="SELECT set_config('request.jwt.claims', '{\"sub\":\"$w12_sub\",\"role\":\"authenticated\"}', true);"
  local w12_dolar="SELECT pg_temp.w12_tenta(\$c\$UPDATE public.system_settings SET value = '6.1234' WHERE key = 'dollar_exchange_rate'\$c\$);"
  local w12_controle="SELECT pg_temp.w12_tenta(\$c\$UPDATE public.system_settings SET value = 'w12-x' WHERE key = 'w12_lab_chave'\$c\$);"
  # service_role muda o dólar e guarda o resultado (linhas afetadas) para o SELECT final.
  local w12_dolar_sr; w12_dolar_sr=$(w12_sr "UPDATE public.system_settings SET value = '6.1234' WHERE key = 'dollar_exchange_rate'")
  local w12_versao="SELECT count(*)||'|'||min(fonte)||'|'||min(proveniencia->>'papel')||'|'||bool_and(as_of >= now() AND coletado_em = now()) FROM public.exchange_rate_history WHERE rate = 6.1234 AND effective_date = current_date;"
  # Controles por papel, decididos pelo privilégio REAL em system_settings:
  # base do dump (GRANT ALL) ou pós-v19/v19_10 (W4 pode ter tirado a escrita).
  # Com escrita: o papel enxerga e altera outra chave (ok:1, então a recusa do
  # dólar não vem de 0 linhas nem de RLS) e o dólar cai no histórico, por
  # privilégio (REVOKE) e, com o GRANT do histórico devolvido, pela guarda.
  # Sem escrita: a recusa vem do privilégio em system_settings. Nunca passa
  # calado: 0 linhas ou qualquer outro resultado reprova.
  local papel_c pre_c ss_w
  for papel_c in authenticated anon; do
    pre_c=""; [ "$papel_c" = authenticated ] && pre_c="$w12_jwt"
    ss_w=$(w12_sql "select has_table_privilege('$papel_c', 'public.system_settings', 'UPDATE')")
    if [ "$ss_w" = t ]; then
      eq "$(w12_bloco "SET LOCAL ROLE $papel_c; $pre_c $w12_controle")" "ok:1" \
         "v23 · controle ($papel_c escreve em system_settings): altera outra chave (1 linha; a linha é visível)"
      eq "$(w12_bloco "SET LOCAL ROLE $papel_c; $pre_c $w12_dolar")" "42501:privilegio(exchange_rate_history)" \
         "v23 · $papel_c muda o dólar: o gatilho dispara e o INSERT no histórico é recusado por privilégio (REVOKE)"
      PA -c "GRANT INSERT ON public.exchange_rate_history TO $papel_c" >/dev/null 2>&1
      eq "$(w12_bloco "SET LOCAL ROLE $papel_c; $pre_c $w12_dolar")" "42501:guarda" \
         "v23 · $papel_c com o GRANT do histórico de volta: a guarda recusa (não depende do REVOKE)"
      PA -c "REVOKE INSERT ON public.exchange_rate_history FROM $papel_c" >/dev/null 2>&1
    elif [ "$ss_w" = f ]; then
      eq "$(w12_bloco "SET LOCAL ROLE $papel_c; $pre_c $w12_controle")|$(w12_bloco "SET LOCAL ROLE $papel_c; $pre_c $w12_dolar")" \
         "42501:privilegio(system_settings)|42501:privilegio(system_settings)" \
         "v23 · $papel_c sem escrita em system_settings (pós-W4): a recusa do dólar vem do privilégio em system_settings"
    else
      nao "v23 · privilégio de $papel_c em system_settings ilegível («$ss_w»)"
    fi
  done
  eq "$(w12_sql "select has_table_privilege('authenticated','public.exchange_rate_history','INSERT') or has_table_privilege('anon','public.exchange_rate_history','INSERT')")" "f" \
     "v23 · GRANT temporário da prova retirado"
  eq "$(w12_bloco "SET LOCAL ROLE authenticated; $w12_jwt INSERT INTO public.exchange_rate_history (rate, effective_date) VALUES (6.1234, current_date); SELECT 1;")" "ERRO:42501" \
     "v23 · authenticated não grava direto no histórico"
  eq "$(w12_bloco "$w12_dolar_sr SELECT (SELECT r FROM w12_t)||'|'||(${w12_versao%;});")" "ok:1|1|manual|service_role|true" \
     "v23 · service_role (servidor) muda o dólar: 1 linha em system_settings e UMA versão manual com papel e carimbo do servidor"
  eq "$(w12_bloco "SELECT set_config('request.jwt.claim.sub', '$w12_sub', true); $w12_dolar_sr SELECT (SELECT r FROM w12_t)||'|'||(SELECT min(proveniencia->>'auth_uid') FROM public.exchange_rate_history WHERE rate = 6.1234);")" "ok:1|$w12_sub" \
     "v23 · versão manual do servidor leva o auth_uid de quem pediu (request.jwt.claim.sub)"
  eq "$(w12_sql "select p.prosecdef||'|'||coalesce(array_to_string(p.proconfig, ','), '-') from pg_proc p where p.oid = 'public.record_exchange_rate_change()'::regprocedure")" "false|-" \
     "v23 · record_exchange_rate_change continua INVOKER sem config, como em produção"
  eq "$(w12_bloco "SET LOCAL ROLE anon; $(w12_cot 2026-10-13 5.40 '2026-10-13 13:10:00-03') SELECT 1;")" "ERRO:42501" \
     "v23 · anon não grava cotação versionada"
  eq "$(w12_bloco "SET LOCAL ROLE service_role; $(w12_cot 2026-10-13 5.40 '2026-10-13 13:10:00-03') RESET ROLE; SELECT count(*) FROM public.exchange_rate_history WHERE fonte='bcb_ptax';")" "1" \
     "v23 · service_role (a coleta) grava cotação versionada"

  echo "▶ v23 · receita: versões, data de referência e câmbio usado"
  local base_rec="$cots $(w12_jads 2026-10-13 10)"
  eq "$(w12_bloco "$base_rec SELECT operacao||'|'||data_referencia||'|'||trim_scale(receita)||'|'||cambio_modo||'|'||trim_scale(cambio_taxa)||'|'||trim_scale(receita_brl)||'|'||(coletado_em = now())||'|'||(cambio_cotacao_id = (SELECT max(id) FROM public.exchange_rate_history WHERE fonte='bcb_ptax')) FROM public.receita_observacao WHERE chave->>'utm_campaign_value'='w12-lab-utm';")" \
     "INSERT|2026-10-13|10|exata|5.41|54.1|true|true" \
     "v23 · insert vira versão com data de referência, coletado_em, cotação usada e receita em BRL"
  eq "$(w12_bloco "$base_rec SELECT receita_convertida_legado IS NOT NULL FROM public.receita_observacao WHERE chave->>'utm_campaign_value'='w12-lab-utm';")" "t" \
     "v23 · revenue_converted legado fica registrado ao lado"
  local upsert="SET LOCAL ROLE service_role; INSERT INTO public.joinads_metrics (date, utm_campaign_value, joinads_domain, revenue) VALUES ('2026-10-13','w12-lab-utm','w12-lab.example.invalid', %s) ON CONFLICT (date, utm_campaign_value, joinads_domain) DO UPDATE SET revenue = EXCLUDED.revenue; RESET ROLE;"
  # shellcheck disable=SC2059
  eq "$(w12_bloco "$base_rec $(printf "$upsert" 10) $(printf "$upsert" 10) $W12_OBS;")" "1" \
     "v23 · upsert idêntico (D-1 reescrevendo) não cria versão"
  # shellcheck disable=SC2059
  eq "$(w12_bloco "$base_rec $(printf "$upsert" 12) $W12_OBS; ")" "2" "v23 · mudança de receita cria versão nova"
  # Releitura (pedido do W14): o mesmo valor regravado não é versão, mas fica registrado.
  local w12_rel="SELECT confirmacoes||'|'||(versao_id = (SELECT max(id) FROM public.receita_observacao WHERE chave->>'utm_campaign_value'='w12-lab-utm'))||'|'||coalesce(confirmado_por->>'papel','-') FROM public.receita_releitura WHERE chave->>'utm_campaign_value'='w12-lab-utm';"
  # shellcheck disable=SC2059
  eq "$(w12_bloco "$base_rec $(printf "$upsert" 10) $(printf "$upsert" 10.00) $w12_rel")" "2|true|service_role" \
     "v23 · releitura do mesmo valor (10 e 10.00) conta confirmação na versão vigente, com quem releu"
  # shellcheck disable=SC2059
  eq "$(w12_bloco "$base_rec $(printf "$upsert" 10) $(printf "$upsert" 12) $w12_rel")" "0|true|-" \
     "v23 · versão nova zera a releitura e passa a apontar para ela"
  # shellcheck disable=SC2059
  eq "$(w12_bloco "$base_rec $(printf "$upsert" 10) SELECT confirmacoes||'|'||(confirmado_em >= coletado_em) FROM public.vw_receita_vigente WHERE chave->>'utm_campaign_value'='w12-lab-utm';")" "1|true" \
     "v23 · vw_receita_vigente expõe confirmado_em e confirmacoes (colunas a mais, versão igual)"
  # B1 do revisor nuvem 2: só o UPDATE que escreve revenue conta como releitura.
  eq "$(w12_bloco "$base_rec $(w12_sr "UPDATE public.joinads_metrics SET updated_at = now() WHERE utm_campaign_value = 'w12-lab-utm'") SELECT $W12_T||'|'||(${w12_rel%;});")" "ok:1|0|true|-" \
     "v23 · UPDATE só de updated_at não é releitura"
  eq "$(w12_bloco "$cots SELECT pg_temp.w12_semear('public.gam_metrics', jsonb_build_object('date','2026-10-13','utm_campaign_value','w12-lab-gam','gam_accounts_id', pg_temp.w12_conta_gam(),'revenue',2));
        CREATE FUNCTION pg_temp.w12_rpc_recalculo() RETURNS bigint LANGUAGE sql AS \$\$ WITH u AS (UPDATE public.gam_metrics SET revenue_converted = revenue * 9 WHERE utm_campaign_value = 'w12-lab-gam' RETURNING 1) SELECT count(*) FROM u \$\$;
        CREATE TEMP TABLE w12_rpc AS SELECT pg_temp.w12_rpc_recalculo() AS n;
        SELECT (SELECT n FROM w12_rpc)||'|'||(SELECT string_agg(confirmacoes::text, ',') FROM public.receita_releitura WHERE chave->>'utm_campaign_value' IN ('w12-lab-gam'));")" "1|0" \
     "v23 · recálculo de revenue_converted chamado direto (RPC do botão Atualizar) não é releitura"
  eq "$(w12_bloco "$base_rec $(w12_sr "UPDATE public.joinads_metrics SET revenue_converted = revenue * 9 WHERE utm_campaign_value = 'w12-lab-utm'") SELECT $W12_T||'|'||(${w12_rel%;});")" "ok:1|0|true|-" \
     "v23 · UPDATE direto só de revenue_converted não é releitura"
  # shellcheck disable=SC2059
  eq "$(w12_bloco "$base_rec $(printf "$upsert" 12) SELECT trim_scale(receita) FROM public.vw_receita_vigente WHERE chave->>'utm_campaign_value'='w12-lab-utm';")" "12" \
     "v23 · vw_receita_vigente mostra a última versão"
  eq "$(w12_bloco "$base_rec UPDATE public.joinads_metrics SET utm_campaign_value='w12-lab-utm2' WHERE utm_campaign_value='w12-lab-utm';
        SELECT string_agg(operacao||':'||removida||':'||(chave->>'utm_campaign_value'), ',' ORDER BY id) FROM public.receita_observacao WHERE chave->>'utm_campaign_value' like 'w12-lab-utm%';")" \
     "INSERT:false:w12-lab-utm,UPDATE:true:w12-lab-utm,UPDATE:false:w12-lab-utm2" \
     "v23 · troca de chave encerra a chave antiga e abre a nova"
  eq "$(w12_bloco "$base_rec DELETE FROM public.joinads_metrics WHERE utm_campaign_value='w12-lab-utm';
        SELECT (SELECT count(*) FROM public.vw_receita_vigente WHERE chave->>'utm_campaign_value'='w12-lab-utm')||'|'||(SELECT operacao||':'||removida||':'||coalesce(trim_scale(receita)::text,'NULL') FROM public.receita_observacao WHERE chave->>'utm_campaign_value'='w12-lab-utm' ORDER BY id DESC LIMIT 1);")" \
     "0|DELETE:true:NULL" "v23 · delete vira versão removida e sai da vigente"
  eq "$(w12_bloco "$cots $(w12_jads 2026-12-01 7) SELECT (SELECT count(*) FROM public.joinads_metrics WHERE utm_campaign_value='w12-lab-utm')||'|'||cambio_modo||'|'||coalesce(trim_scale(receita_brl)::text,'NULL')||'|'||trim_scale(receita) FROM public.receita_observacao WHERE chave->>'utm_campaign_value'='w12-lab-utm';")" \
     "1|defasada|NULL|7" "v23 · sem câmbio válido a ingestão segue e a receita em BRL fica NULL (ausência, não zero)"
  eq "$(w12_bloco "$cots $(w12_jads 2026-10-15 1 w12-lab-ant) SELECT cambio_modo||'|'||cambio_defasagem_dias||'|'||trim_scale(receita_brl) FROM public.receita_observacao WHERE chave->>'utm_campaign_value'='w12-lab-ant';")" \
     "anterior|2|5.41" "v23 · fim de semana/feriado: usa a anterior e grava a defasagem"
  eq "$(w12_bloco "$base_rec SELECT proveniencia->>'papel' FROM public.receita_observacao WHERE chave->>'utm_campaign_value'='w12-lab-utm';")" "service_role" \
     "v23 · proveniência registra o papel de quem gravou"
  eq "$(w12_bloco "$cots SET LOCAL request.headers = '{\"user-agent\":\"n8n\",\"x-volc-proveniencia\":\"n8n:joinads-d1:w12\",\"x-volc-coletado-em\":\"2026-10-14T03:00:00Z\"}'; $(w12_jads 2026-10-13 10)
        SELECT (proveniencia->>'user_agent')||'|'||(proveniencia->>'declarada')||'|'||(proveniencia->>'coletado_em_declarado') FROM public.receita_observacao WHERE chave->>'utm_campaign_value'='w12-lab-utm';")" \
     "n8n|n8n:joinads-d1:w12|2026-10-14T03:00:00Z" "v23 · proveniência e coleta declaradas pelo adaptador (cabeçalho) são registradas"
  eq "$(w12_bloco "$cots SET LOCAL request.headers = 'isto não é json'; $(w12_jads 2026-10-13 10) $W12_OBS;")" "1" \
     "v23 · cabeçalho malformado não derruba a ingestão"
  eq "$(w12_bloco "$cots SELECT pg_temp.w12_semear('public.gam_metrics', jsonb_build_object('date','2026-10-13','utm_campaign_value','w12-lab-gam','gam_accounts_id', pg_temp.w12_conta_gam(),'revenue',2));
        SELECT fonte||'|'||data_referencia||'|'||cambio_modo||'|'||trim_scale(receita_brl) FROM public.receita_observacao WHERE chave->>'utm_campaign_value'='w12-lab-gam';")" \
     "gam|2026-10-13|exata|10.82" "v23 · gam_metrics também versiona, com a chave (date, utm, conta GAM)"
  # Legado (dump 2c70b4a4): mudar o dólar dispara update_all_revenue_converted(),
  # que reescreve revenue_converted do histórico inteiro de gam_metrics. Campo
  # derivado não é fato novo: nenhuma versão nova no diário.
  eq "$(w12_bloco "$cots SELECT pg_temp.w12_semear('public.gam_metrics', jsonb_build_object('date','2026-10-13','utm_campaign_value','w12-lab-gam','gam_accounts_id', pg_temp.w12_conta_gam(),'revenue',2));
        CREATE TEMP TABLE w12_n AS SELECT count(*) AS n, (SELECT revenue_converted FROM public.gam_metrics WHERE utm_campaign_value = 'w12-lab-gam') AS rc FROM public.receita_observacao;
        $w12_dolar_sr
        SELECT (SELECT r FROM w12_t)||'|'||(SELECT count(*) FROM public.gam_metrics WHERE utm_campaign_value = 'w12-lab-gam')||'|'||((SELECT count(*) FROM public.receita_observacao) - n)||'|'||((SELECT revenue_converted FROM public.gam_metrics WHERE utm_campaign_value = 'w12-lab-gam') IS DISTINCT FROM rc)
               ||'|'||(SELECT confirmacoes FROM public.receita_releitura WHERE chave->>'utm_campaign_value' = 'w12-lab-gam') FROM w12_n;")" \
     "ok:1|1|0|true|0" "v23 · mudança do dólar (1 linha em system_settings, 1 linha GAM semeada) reescreve revenue_converted de gam_metrics em massa: nem versão nova, nem releitura (recálculo não releu a fonte)"

  echo "▶ v23 · câmbio impossível, escala numérica e TRUNCATE"
  eq "$(w12_bloco "$cots $(w12_jads 2026-10-20 4 w12-lab-zero) SELECT (SELECT count(*) FROM public.joinads_metrics WHERE utm_campaign_value='w12-lab-zero')||'|'||cambio_modo||'|'||trim_scale(cambio_taxa)||'|'||cambio_defasagem_dias FROM public.receita_observacao WHERE chave->>'utm_campaign_value'='w12-lab-zero';")" \
     "1|anterior|5.41|7" "v23 · linha manual legada com taxa 0 no dia não derruba o upsert do service_role (ignorada; usa a anterior válida)"
  eq "$(w12_bloco "$(w12_jads 2026-10-20 4 w12-lab-zero) SELECT cambio_modo||'|'||coalesce(trim_scale(receita_brl)::text,'NULL') FROM public.receita_observacao WHERE chave->>'utm_campaign_value'='w12-lab-zero';")" \
     "defasada|NULL" "v23 · sem PTAX: taxa 0 ignorada, a manual de fevereiro fica defasada e receita_brl NULL"
  # shellcheck disable=SC2059
  eq "$(w12_bloco "$base_rec $(printf "$upsert" 10.00) $(printf "$upsert" 10.0000) $W12_OBS;")" "1" \
     "v23 · 10 e 10.00 são o mesmo valor: sem versão espúria"
  # Quem trunca é o primeiro papel que DE FATO tem TRUNCATE na base (dump: anon;
  # pós-v19/v19_10: talvez só service_role). Sem nenhum, reprova.
  local papel_t
  papel_t=$(w12_sql "select coalesce((select r from unnest(array['anon','authenticated','service_role']) with ordinality u(r, o) where has_table_privilege(r, 'public.joinads_metrics', 'TRUNCATE') order by o limit 1), '-')")
  if [ "$papel_t" = "-" ]; then
    nao "v23 · nenhum de anon/authenticated/service_role tem TRUNCATE em joinads_metrics: TRUNCATE não provado"
  else
    eq "$(w12_bloco "$base_rec SET LOCAL ROLE $papel_t; TRUNCATE public.joinads_metrics; RESET ROLE;
          SELECT (SELECT count(*) FROM public.vw_receita_vigente WHERE tabela_origem='joinads_metrics')||'|'||(SELECT operacao||':'||removida||':'||(proveniencia->>'papel') FROM public.receita_observacao WHERE chave->>'utm_campaign_value'='w12-lab-utm' ORDER BY id DESC LIMIT 1);")" \
       "0|TRUNCATE:true:$papel_t" "v23 · TRUNCATE na origem (por $papel_t) vira versão removida de cada chave, com o papel, e a vigente acompanha"
  fi
  eq "$(w12_bloco "$base_rec TRUNCATE public.joinads_metrics; $(w12_jads 2026-10-13 10) SELECT count(*)||'|'||trim_scale(max(receita)) FROM public.vw_receita_vigente WHERE chave->>'utm_campaign_value'='w12-lab-utm';")" \
     "1|10" "v23 · reingestão depois do TRUNCATE volta a ficar vigente"

  echo "▶ v23 · as-of e append-only"
  local obs="INSERT INTO public.receita_observacao (fonte, tabela_origem, chave, data_referencia, operacao, removida, moeda, receita, cambio_modo, coletado_em, proveniencia, impressao_digital) VALUES"
  local asof="$obs ('joinads','joinads_metrics','{\"k\":\"w12-lab-asof\"}','2026-10-10','INSERT',false,'USD',5,'sem_cotacao','2026-10-11 03:00Z','{}','a'),
                    ('joinads','joinads_metrics','{\"k\":\"w12-lab-asof\"}','2026-10-10','UPDATE',false,'USD',8,'sem_cotacao','2026-10-12 03:00Z','{}','b'),
                    ('joinads','joinads_metrics','{\"k\":\"w12-lab-asof\"}','2026-10-10','DELETE',true,'USD',NULL,'sem_receita','2026-10-13 03:00Z','{}','c');"
  eq "$(w12_bloco "$asof SELECT coalesce((SELECT trim_scale(receita)::text FROM public.receita_as_of('2026-10-11 12:00Z') WHERE chave->>'k'='w12-lab-asof'),'-')||'|'||coalesce((SELECT trim_scale(receita)::text FROM public.receita_as_of('2026-10-12 12:00Z') WHERE chave->>'k'='w12-lab-asof'),'-')||'|'||coalesce((SELECT trim_scale(receita)::text FROM public.receita_as_of('2026-10-13 12:00Z') WHERE chave->>'k'='w12-lab-asof'),'-')||'|'||coalesce((SELECT trim_scale(receita)::text FROM public.receita_as_of('2026-10-10 12:00Z') WHERE chave->>'k'='w12-lab-asof'),'-');")" \
     "5|8|-|-" "v23 · receita_as_of devolve o que se sabia em cada instante (antes, depois, removida)"
  eq "$(w12_bloco "$asof UPDATE public.receita_observacao SET receita = 1; SELECT 1;")" "ERRO:23001" "v23 · diário não aceita UPDATE"
  eq "$(w12_bloco "$asof DELETE FROM public.receita_observacao; SELECT 1;")" "ERRO:23001" "v23 · diário não aceita DELETE"
  eq "$(w12_bloco "TRUNCATE public.receita_observacao; SELECT 1;")" "ERRO:23001" "v23 · diário não aceita TRUNCATE"
  eq "$(w12_bloco "$obs ('joinads','joinads_metrics','{}','2026-10-10','INSERT',false,'USD',5,'exata',now(),'{}','x'); SELECT 1;")" "ERRO:23514" \
     "v23 · modo exata sem cotação é recusado pelo CHECK"

  echo "▶ v23 · matriz de acesso"
  local papel
  for papel in anon authenticated; do
    eq "$(w12_sql "select has_table_privilege('$papel','public.receita_observacao','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') or has_table_privilege('$papel','public.vw_receita_vigente','SELECT,INSERT,UPDATE,DELETE')")" "f" "v23 · $papel sem privilégio no diário e na vigente"
    eq "$(estado "$papel" 'select count(*) from public.receita_observacao')" "42501" "v23 · $papel lê o diário: negado"
    eq "$(estado "$papel" 'select count(*) from public.vw_receita_vigente')" "42501" "v23 · $papel lê a vigente: negado"
    eq "$(estado "$papel" "select count(*) from public.cambio_resolver('2026-10-13')")" "42501" "v23 · $papel executa cambio_resolver: negado"
    eq "$(estado "$papel" "select count(*) from public.receita_as_of(now())")" "42501" "v23 · $papel executa receita_as_of: negado"
    eq "$(estado "$papel" "select public.receita_observar('joinads','USD','joinads_metrics','{}'::jsonb,array['date'],'INSERT',false,'{}'::jsonb)")" "42501" "v23 · $papel executa receita_observar: negado"
    eq "$(estado "$papel" "insert into public.receita_observacao (fonte, tabela_origem, chave, operacao, removida, moeda, cambio_modo, proveniencia, impressao_digital) values ('joinads','x','{}','INSERT',false,'USD','sem_cotacao','{}','x')")" "42501" "v23 · $papel escreve no diário: negado"
    eq "$(estado "$papel" "update public.receita_observacao set removida = true")" "42501" "v23 · $papel altera o diário: negado"
    eq "$(estado "$papel" "insert into public.v23_01_acl_anterior values ('anon', 'INSERT')")" "42501" "v23 · $papel escreve no retrato de ACL: negado"
    eq "$(estado "$papel" 'select count(*) from public.receita_releitura')" "42501" "v23 · $papel lê a releitura: negado"
  done
  # Incidente do lab (revisor local): setval na sequência do diário fez o
  # upsert de gam_metrics do service_role cair com 23505.
  for papel in anon authenticated service_role postgres; do
    eq "$(w12_sql "select has_sequence_privilege('$papel','public.receita_observacao_id_seq','USAGE') or has_sequence_privilege('$papel','public.receita_observacao_id_seq','UPDATE')")" "f" "v23 · $papel sem USAGE/UPDATE na sequência do diário"
  done
  for papel in anon authenticated service_role; do
    eq "$(estado "$papel" "select setval('public.receita_observacao_id_seq', 1)")" "42501" "v23 · $papel faz setval na sequência do diário: negado"
    eq "$(estado "$papel" "select nextval('public.receita_observacao_id_seq')")" "42501" "v23 · $papel consome a sequência do diário: negado"
  done
  eq "$(sqlstate "select setval('public.receita_observacao_id_seq', 1)")" "42501" "v23 · postgres faz setval na sequência do diário: negado"
  eq "$(w12_bloco "$(w12_jads 2026-10-12 1 w12-lab-seq) SELECT count(*) FROM public.receita_observacao WHERE chave->>'utm_campaign_value' = 'w12-lab-seq';")" "1" \
     "v23 · o diário continua gravando pelo gatilho sem ninguém ter a sequência"
  eq "$(estado service_role 'select count(*) >= 0 from public.vw_receita_vigente')" "ok:t" "v23 · service_role lê a vigente"
  eq "$(estado service_role "select count(*) from public.cambio_resolver('2026-10-13')")" "ok:1" "v23 · service_role executa cambio_resolver"
  eq "$(estado service_role "select public.receita_observar('joinads','USD','joinads_metrics','{}'::jsonb,array['date'],'INSERT',false,'{}'::jsonb)")" "42501" "v23 · service_role não forja versão por receita_observar"
  eq "$(estado service_role "insert into public.receita_observacao (fonte, tabela_origem, chave, operacao, removida, moeda, cambio_modo, proveniencia, impressao_digital) values ('joinads','x','{}','INSERT',false,'USD','sem_cotacao','{}','x')")" "42501" "v23 · service_role não escreve direto no diário"
  eq "$(estado service_role "update public.receita_releitura set confirmado_em = now()")" "42501" "v23 · service_role não forja releitura"
  eq "$(estado service_role 'select count(*) >= 0 from public.receita_releitura')" "ok:t" "v23 · service_role lê a releitura"
  eq "$(w12_sql "select prosecdef from pg_proc where oid = 'public.receita_registrar_observacao()'::regprocedure")" "t" "v23 · gatilho do diário é SECURITY DEFINER"
  eq "$(w12_sql "select relrowsecurity from pg_class where oid = 'public.receita_observacao'::regclass")" "t" "v23 · RLS ligada no diário"

  echo "▶ v23 · releitura em transações separadas (coletas de dias diferentes)"
  # shellcheck disable=SC2059
  w12_confirma "$(w12_jads 2026-10-11 3 w12-lab-rel)" rel-1 && sleep 1 \
    && w12_confirma "SET LOCAL ROLE service_role; INSERT INTO public.joinads_metrics (date, utm_campaign_value, joinads_domain, revenue) VALUES ('2026-10-11','w12-lab-rel','w12-lab.example.invalid', 3) ON CONFLICT (date, utm_campaign_value, joinads_domain) DO UPDATE SET revenue = EXCLUDED.revenue; RESET ROLE;" rel-2 \
    && ok "v23 · coleta e releitura confirmadas" || nao "v23 · releitura ($(tail -1 "$RECIBOS/w12-rel-2.out"))"
  eq "$(w12_sql "select (r.confirmado_em > o.coletado_em)||'|'||r.confirmacoes||'|'||(select count(*) from public.receita_observacao where chave->>'utm_campaign_value' = 'w12-lab-rel') from public.receita_releitura r join public.receita_observacao o on o.id = r.versao_id where r.chave->>'utm_campaign_value' = 'w12-lab-rel'")" "true|1|1" \
     "v23 · releitura posterior: confirmado_em avança além do coletado_em, sem versão nova (receita estável ≠ coletor parado)"

  echo "▶ v23 · reverter recusa com dado, e a recusa é atômica"
  w12_confirma "$(w12_cot 2026-10-13 5.41 '2026-10-13 13:15:00-03') $(w12_jads 2026-10-13 10)" dado \
    && ok "v23 · dado confirmado: 1 cotação versionada e 1 versão de receita" || nao "v23 · dado ($(tail -1 "$RECIBOS/w12-dado.out"))"
  w12_reverter reverter-com-dado && nao "v23 · reverter apagou dado do diário" || \
    { grep -q 'versões além da carga inicial' "$RECIBOS/w12-reverter-com-dado.out" && ok "v23 · reverter recusa com versões de receita" || nao "v23 · reverter falhou por outro motivo"; }
  eq "$(w12_aplicada)" "t" "v23 · recusa não deixou a migration pela metade"
  # Limpeza só de teste: o diário é append-only por gatilho; o dono desliga, apaga o que não é carga e religa.
  w12_limpa "ALTER TABLE public.receita_observacao DISABLE TRIGGER receita_observacao_imutavel;
             DELETE FROM public.receita_releitura r USING public.receita_observacao o WHERE o.id = r.versao_id AND o.operacao <> 'CARGA';
             DELETE FROM public.receita_observacao WHERE operacao <> 'CARGA';
             ALTER TABLE public.receita_observacao ENABLE TRIGGER receita_observacao_imutavel;" limpa-diario
  w12_reverter reverter-com-cotacao && nao "v23 · reverter apagou cotação coletada" || \
    { grep -q 'cotações versionadas' "$RECIBOS/w12-reverter-com-cotacao.out" && ok "v23 · reverter recusa com cotação versionada" || nao "v23 · reverter falhou por outro motivo"; }
  w12_limpa "ALTER TABLE public.exchange_rate_history DISABLE TRIGGER cambio_versao_guarda;
             DELETE FROM public.exchange_rate_history WHERE as_of IS NOT NULL;
             ALTER TABLE public.exchange_rate_history ENABLE TRIGGER cambio_versao_guarda;
             ALTER TABLE public.joinads_metrics DISABLE TRIGGER zz_receita_observacao;
             DELETE FROM public.joinads_metrics WHERE utm_campaign_value LIKE 'w12-lab%';
             ALTER TABLE public.joinads_metrics ENABLE TRIGGER zz_receita_observacao;" limpa-cotacao
  P -f - < "$W12_REVERTER" > "$RECIBOS/w12-reverter-sem-dono.out" 2>&1 && nao "v23 · postgres (não dono) reverteu" || \
    { grep -q 'não é dono de' "$RECIBOS/w12-reverter-sem-dono.out" && ok "v23 · rollback recusa quem não é dono antes de tocar em algo" || nao "v23 · reverter sem dono falhou por outro motivo"; }

  echo "▶ v23 · reverter"
  w12_reverter reverter && ok "v23 · rollback aplicou" || nao "v23 · rollback ($(tail -1 "$RECIBOS/w12-reverter.out"))"
  eq "$(w12_aplicada)" "f" "v23 · colunas de versão e diário sumiram"
  eq "$(w12_sql "select count(*) from public.exchange_rate_history where rate = 5.25 and effective_date = '2026-02-18'")" "1" "v23 · cotação manual preservada pelo rollback"
  w12_fp depois-reverter
  diff -q "$RECIBOS/w12-fp-antes.out" "$RECIBOS/w12-fp-depois-reverter.out" >/dev/null && ok "v23 · rollback devolve o fingerprint exato de antes" || nao "v23 · rollback deixou resíduo no schema"
  w12_reverter reverter-de-novo && ok "v23 · rollback idempotente" || nao "v23 · rollback idempotente"

  echo "▶ v23 · reaplicar"
  w12_aplicar reaplicar && ok "v23 · reaplicou depois do rollback" || nao "v23 · reaplicar ($(tail -1 "$RECIBOS/w12-reaplicar.out"))"
  w12_fp depois2
  diff -q "$RECIBOS/w12-fp-depois1.out" "$RECIBOS/w12-fp-depois2.out" >/dev/null && ok "v23 · fingerprint idêntico entre 1ª e 2ª aplicação" || nao "v23 · fingerprint divergiu entre aplicações"
  diff -q "$RECIBOS/w12-fp-antes.out" "$RECIBOS/w12-fp-depois1.out" >/dev/null && nao "v23 · fingerprint não mudou com a migration" || ok "v23 · fingerprint muda com a migration"
  w12_aplicar por-cima && nao "v23 · reaplicar por cima passou" || \
    { grep -q 'não reaplica por cima' "$RECIBOS/w12-por-cima.out" && ok "v23 · reaplicar por cima recusado pela pré-checagem" || nao "v23 · reaplicar por cima falhou por outro motivo"; }
  w12_reverter limpeza >/dev/null && ok "v23 · rollback de limpeza" || nao "v23 · limpeza final"

  echo "▶ v23 · ordem errada com o W4: o rollback da v23 nunca reabre a anon"
  PA -c "GRANT INSERT, UPDATE, DELETE, TRUNCATE ON public.exchange_rate_history TO anon" >/dev/null 2>&1   # retrato do incidente
  # Retrato dos privilégios dos outros papéis ANTES da v23, para o rollback
  # devolver exatamente o que havia (base do dump ou pós-v19/v19_10).
  local w12_acl_q="select coalesce(string_agg(pg_get_userbyid(a.grantee) || ':' || a.privilege_type, ' ' order by 1), '-') from pg_class c, aclexplode(c.relacl) a where c.oid = 'public.exchange_rate_history'::regclass and a.grantee <> 0 and pg_get_userbyid(a.grantee) <> 'anon'"
  local w12_acl_antes; w12_acl_antes=$(w12_sql "$w12_acl_q")
  w12_aplicar w4-depois && ok "v23 · v23_01 aplicada com a anon ainda aberta (ordem errada)" || nao "v23 · aplicar w4-depois ($(tail -1 "$RECIBOS/w12-w4-depois.out"))"
  eq "$(w12_sql "select count(*) from public.v23_01_acl_anterior where papel = 'anon'")" "4" "v23 · o retrato guardado tem a escrita da anon"
  PA -c "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.exchange_rate_history FROM anon" >/dev/null 2>&1   # W4 fecha a escrita da anon depois da v23
  w12_reverter w4-depois-reverter && ok "v23 · rollback aplicou" || nao "v23 · rollback w4-depois ($(tail -1 "$RECIBOS/w12-w4-depois-reverter.out"))"
  eq "$(w12_sql "select has_table_privilege('anon','public.exchange_rate_history','INSERT') or has_table_privilege('anon','public.exchange_rate_history','UPDATE') or has_table_privilege('anon','public.exchange_rate_history','DELETE') or has_table_privilege('anon','public.exchange_rate_history','TRUNCATE')")" "f" \
     "v23 · com a anon fechada depois da v23, o rollback da v23 deixa a anon fechada"
  grep -q 'NÃO devolvido a anon' "$RECIBOS/w12-w4-depois-reverter.out" && ok "v23 · o que não foi devolvido à anon fica registrado (NOTICE)" || nao "v23 · rollback sem NOTICE do que não devolveu"
  eq "$(w12_sql "$w12_acl_q")" "$w12_acl_antes" "v23 · os outros papéis (authenticated, service_role, postgres…) recebem de volta exatamente o que tinham antes da v23"

  # Devolve o ACL da anon/PUBLIC de antes da suíte (o lab sai como entrou).
  local par_acl
  for par_acl in $W12_ACL_ORIG; do
    PA -c "GRANT ${par_acl#*:} ON public.exchange_rate_history TO ${par_acl%%:*}" >/dev/null 2>&1 || nao "v23 · devolver $par_acl"
  done
  ok "v23 · ACL de anon/PUBLIC no câmbio devolvido ao de antes da suíte"
  w12_limpa "DELETE FROM public.exchange_rate_history WHERE (rate, effective_date) IN ((5.25, '2026-02-18'), (0, '2026-10-20'));" limpa-semente
  # system_settings sai como entrou: só as chaves que a suíte semeou (DELETE não dispara o gatilho de UPDATE).
  if [ -n "$W12_SS_NOVAS" ] && [ "$W12_SS_NOVAS" != "-" ]; then
    w12_limpa "DELETE FROM public.system_settings WHERE key = ANY (string_to_array('$W12_SS_NOVAS', ' '));" limpa-system-settings
  fi
}

w12_suite
