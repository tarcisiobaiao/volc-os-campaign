#!/bin/bash
# =============================================================================
# Prova local do ciclo de schema e da recuperação — PostgreSQL DESCARTÁVEL
# =============================================================================
# T03 + T11 · pacote docs/specs/traffic-operational-closure-v2/
#
# ⚠️ ESTE SCRIPT NÃO TOCA O SUPABASE OFICIAL, e não tem como tocar: ele cria um
# cluster novo com `initdb`, num diretório temporário, ouvindo só em 127.0.0.1
# numa porta própria. Nenhuma variável de ambiente do projeto é lida.
#
# O que ele prova, e por que cada etapa existe:
#
#   1. o perfil CREATE_ONLY aplica na ordem declarada pelo manifesto;
#   2. a fronteira de AUTORIZAÇÃO vale com os papéis REAIS — e não como
#      superusuário, que passa por cima de todo GRANT e não prova nada;
#   3. duas sagas concorrentes no mesmo passo: no máximo UM despacho;
#   4. reaplicar é recusado, rollback preserva a dependência, reapply funciona;
#   5. EXPIRAÇÃO fecha novo despacho e NÃO fecha a recuperação histórica —
#      que é o invariante central de T03;
#   6. o órfão IN_FLIGHT deixa de ser invisível.
#
# Uso:  bash docs/closure/traffic-operational-closure-v2/prova-sql-local.sh
# =============================================================================
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PGBIN="${PGBIN:-/opt/homebrew/opt/postgresql@17/bin}"
PORTA="${PORTA:-55432}"
BASE="${BASE:-r0_prova}"
TMP="$(mktemp -d)"
DADOS="$TMP/data"

limpar() {
  "$PGBIN/pg_ctl" -D "$DADOS" -m immediate stop >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap limpar EXIT

psql_() { "$PGBIN/psql" -h 127.0.0.1 -p "$PORTA" -U postgres -v ON_ERROR_STOP=1 "$@"; }

echo "== 0. cluster descartável em $DADOS (porta $PORTA) =="
"$PGBIN/initdb" -D "$DADOS" -U postgres --auth=trust --no-locale --encoding=UTF8 >/dev/null
"$PGBIN/pg_ctl" -D "$DADOS" -o "-p $PORTA -k $TMP -c listen_addresses=127.0.0.1" \
  -l "$TMP/server.log" -w start >/dev/null
psql_ -d postgres -Atc "select 'engine: '||version();"

psql_ -d postgres -q -c "CREATE DATABASE $BASE;"
psql_ -d "$BASE" -q -c "CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN BYPASSRLS;"

echo
echo "== 1. apply do perfil CREATE_ONLY, na ordem do manifesto =="
# ⚠️ Lista EXPLÍCITA. Nunca `supabase/migrations/*.sql`: 20 dos 48 arquivos SQL
# do diretório são ROLLBACKS, e um glob executaria apply e rollback na mesma
# passada. O executor é `psql` porque todo arquivo abre com `\set ON_ERROR_STOP`.
for f in v13_01_cofre_de_ativos.sql \
         v15_01_meta_ads_read_model.sql \
         20260904183418_meta_create_paused_executor.sql \
         20260907120000_meta_recovery_snapshot.sql; do
  printf '   %-52s ' "$f"
  psql_ -d "$BASE" -q -f "$RAIZ/supabase/migrations/$f" && echo "APLICADA"
done

echo
echo "== 2. fronteira de autorização com os papéis REAIS =="
psql_ -d "$BASE" -q <<'SQL'
DO $$
BEGIN
  SET LOCAL ROLE anon;
  PERFORM public.trafego_meta_create_receipt(gen_random_uuid());
  RAISE EXCEPTION 'FALHA: anon executou a RPC';
EXCEPTION WHEN insufficient_privilege THEN RAISE NOTICE '   OK anon recusado na função';
END $$;
DO $$
BEGIN
  SET LOCAL ROLE authenticated;
  PERFORM count(*) FROM public.trafego_meta_create_approval;
  RAISE EXCEPTION 'FALHA: authenticated leu a tabela';
EXCEPTION WHEN insufficient_privilege THEN RAISE NOTICE '   OK authenticated sem SELECT na tabela';
END $$;
DO $$
BEGIN
  SET LOCAL ROLE service_role;
  INSERT INTO public.trafego_meta_create_step (approval_id, step_name, ordinal, payload_sha256)
  VALUES (gen_random_uuid(), 'campaign', 1, repeat('a',64));
  RAISE EXCEPTION 'FALHA: service_role escreveu direto na tabela';
EXCEPTION WHEN insufficient_privilege THEN RAISE NOTICE '   OK service_role sem INSERT direto — só a RPC escreve';
END $$;
SQL

echo
echo "== 3. fixture: validação -> aprovação COM snapshot -> passo preparado =="
APROVACAO=$(psql_ -d "$BASE" -Atq <<'SQL' | tail -1
SET ROLE service_role;
SELECT public.trafego_meta_create_record_validation(
  repeat('7',64), 'metaacct_prova', 'ator-1', 'INDEPENDENT_ROOTS_ONLY',
  ARRAY['campaign','creative'], ARRAY['adset','ad'], 4, 0) ->> 'validation_id' AS vid \gset
SELECT public.trafego_meta_create_approve(
  repeat('7',64), 'metaacct_prova', 'ator-1', 1000, 'BRL',
  clock_timestamp() + interval '15 minutes',
  ARRAY['campaign','adset','creative','ad'], :'vid'::uuid, 1800, true,
  '{"account_ref":"metaacct_prova"}'::jsonb,
  jsonb_build_array(jsonb_build_object(
    'asset_ref','metaasset_prova','content_sha256',repeat('b',64),'item_sha256',repeat('b',64),
    'supply_sha256',repeat('c',64),'policy_receipt_ref','metapolicy_'||repeat('d',24),
    'policy_state','AUTHORIZED','lifecycle','READY_FOR_PAID_MEDIA','image_hash_bound',true,
    'policy_expires_at',(clock_timestamp() + interval '30 minutes')::text)),
  jsonb_build_object(
    'compiler_version','meta-compilador-v2', 'plano_sha256', repeat('7',64),
    'account_ref','metaacct_prova', 'estado_ao_nascer','PAUSED', 'api_version','v26.0',
    'asset_supply', jsonb_build_array(jsonb_build_object('asset_ref','metaasset_prova')),
    'operacoes', jsonb_build_array(
      jsonb_build_object('nome','campaign','endpoint','/act_1234567890/campaigns','payload','{"status":"PAUSED"}'::jsonb),
      jsonb_build_object('nome','adset','endpoint','/act_1234567890/adsets','payload','{"status":"PAUSED"}'::jsonb),
      jsonb_build_object('nome','creative','endpoint','/act_1234567890/adcreatives','payload','{}'::jsonb),
      jsonb_build_object('nome','ad','endpoint','/act_1234567890/ads','payload','{"status":"PAUSED"}'::jsonb))),
  'meta-compilador-v2', repeat('7',64)
) ->> 'approval_id' AS aid \gset
SELECT :'aid';
SQL
)
echo "   approval_id=$APROVACAO"

echo
echo "== 4. CONCORRÊNCIA: duas sessões preparando o MESMO passo =="
cat > "$TMP/worker.sql" <<'SQL'
SET ROLE service_role;
BEGIN;
SELECT pg_sleep(0.2);
SELECT public.trafego_meta_create_prepare_step(
  repeat('7',64), :'aprov'::uuid, 'ator-1', 'campaign', repeat('8',64)) ->> 'state';
SELECT pg_sleep(1.0);
COMMIT;
SQL
psql_ -d "$BASE" -Atq -v aprov="$APROVACAO" -f "$TMP/worker.sql" > "$TMP/w1" 2>&1 &
psql_ -d "$BASE" -Atq -v aprov="$APROVACAO" -f "$TMP/worker.sql" > "$TMP/w2" 2>&1 &
wait
echo "   worker1: $(grep -vE '^$|^SET$|^BEGIN$|^COMMIT$' "$TMP/w1" | head -1)"
echo "   worker2: $(grep -vE '^$|^SET$|^BEGIN$|^COMMIT$' "$TMP/w2" | head -1)"
echo "   => no máximo um DESPACHAR; o outro é obrigado a reconciliar"

echo
echo "== 5. o invariante central: expiração fecha DESPACHO, não RECUPERAÇÃO =="
# Só o superusuário mexe no relógio: é simulação de TEMPO, não de autoridade.
psql_ -d "$BASE" -q -c "UPDATE public.trafego_meta_create_step SET state='IN_FLIGHT', external_object_id=NULL, closed_at=NULL, prepared_at=clock_timestamp()-interval '30 minutes';"
psql_ -d "$BASE" -q -c "UPDATE public.trafego_meta_create_approval SET expires_at = approved_at + interval '1 second';"
psql_ -d "$BASE" -Atq <<SQL
SET ROLE service_role;
SELECT '   estado da aprovação: '||(public.trafego_meta_create_receipt('$APROVACAO'::uuid) ->> 'state');
SQL
psql_ -d "$BASE" -q <<SQL
DO \$\$
BEGIN
  SET LOCAL ROLE service_role;
  PERFORM public.trafego_meta_create_prepare_step(
    repeat('7',64), '$APROVACAO'::uuid, 'ator-1', 'adset', repeat('9',64));
  RAISE EXCEPTION 'FALHA: despachou com aprovação expirada';
EXCEPTION WHEN OTHERS THEN
  IF SQLERRM LIKE 'FALHA%' THEN RAISE; END IF;
  RAISE NOTICE '   OK novo despacho recusado: %', SQLERRM;
END \$\$;
SQL
psql_ -d "$BASE" -Atq <<SQL
SET ROLE service_role;
SELECT '   reclaim do órfão com aprovação EXPIRADA: '||(public.trafego_meta_create_reclaim_orphan(
  (SELECT step_id FROM public.trafego_meta_create_step LIMIT 1), 300) ->> 'state');
SELECT '   passos visíveis para a reconciliação: '
     ||count(*) FILTER (WHERE s->>'state'='AMBIGUOUS')||' ambíguo(s), '
     ||count(*) FILTER (WHERE s->>'state'='IN_FLIGHT')||' em voo'
  FROM jsonb_array_elements(public.trafego_meta_create_approval_manifest('$APROVACAO'::uuid) -> 'steps') s;
SQL

echo
echo "== 6. o snapshot é server-only =="
psql_ -d "$BASE" -Atq <<SQL
SET ROLE service_role;
SELECT '   manifesto interno traz compiled_plan: '||
  (public.trafego_meta_create_approval_manifest('$APROVACAO'::uuid) ? 'compiled_plan')::text;
SELECT '   recibo do navegador traz compiled_plan: '||
  (public.trafego_meta_create_receipt('$APROVACAO'::uuid) ? 'compiled_plan')::text||'  (precisa ser false)';
SELECT '   recibo do navegador vaza endpoint da conta: '||
  (public.trafego_meta_create_receipt('$APROVACAO'::uuid)::text LIKE '%act_1234567890%')::text||'  (precisa ser false)';
SQL

echo
echo "== 7. repetição, rollback e reapply =="
printf '   reaplicar o snapshot:            '
psql_ -d "$BASE" -q -f "$RAIZ/supabase/migrations/20260907120000_meta_recovery_snapshot.sql" >/dev/null 2>&1 \
  && echo "FALHA (reaplicou)" || echo "RECUSADO, como deve"
printf '   rollback do snapshot:            '
psql_ -d "$BASE" -q -f "$RAIZ/supabase/migrations/20260907120100_meta_recovery_snapshot_rollback.sql" >/dev/null && echo "OK"
printf '   CREATE_ONLY preservado:          '
psql_ -d "$BASE" -Atc "select count(*) from unnest(array['trafego_meta_create_approval','trafego_meta_create_step','trafego_meta_validation_receipt']) t where to_regclass('public.'||t) is not null;"
printf '   reapply do snapshot:             '
psql_ -d "$BASE" -q -f "$RAIZ/supabase/migrations/20260907120000_meta_recovery_snapshot.sql" >/dev/null && echo "OK"

echo
echo "== FIM. Cluster descartável removido. Nenhum banco oficial foi tocado. =="
