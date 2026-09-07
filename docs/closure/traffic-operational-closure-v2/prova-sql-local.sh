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
# ## O que mudou nesta rodada, e por quê
#
# A versão anterior IMPRIMIA expectativas em vez de cobrá-las. Ela dizia
# "(precisa ser false)" ao lado de um valor, mostrava `worker1:`/`worker2:` sem
# conferir, e escrevia "FALHA (reaplicou)" saindo com zero. Um portão que
# imprime a própria violação e devolve sucesso não é portão — é legenda.
#
# Agora toda expectativa é uma ASSERÇÃO, o script termina com contagem, e
# qualquer violação sai com código diferente de zero.
#
# ## E a lista de arquivos é UMA só
#
# Ela vem de `SCHEMA-DEPLOY-MANIFEST.json`, lida por
# `scripts/verificar_perfil_schema_meta.py --lista-apply`. Duas listas divergem:
# foi exatamente assim que o manifesto ficou parado na terceira migration
# enquanto esta prova já aplicava a quarta — o achado R0-A01.
#
# O que ele prova, e por que cada etapa existe:
#
#   0. o perfil declarado bate com os arquivos (sha256, dependência, rollback);
#   1. o perfil aplica na ordem declarada pelo manifesto;
#   2. a fronteira de AUTORIZAÇÃO vale com os papéis REAIS — e não como
#      superusuário, que passa por cima de todo GRANT e não prova nada;
#   3. duas sagas concorrentes no mesmo passo: no máximo UM despacho, CONFERIDO;
#   4. a CERCA: trabalhador antigo não conclui, e o id que ele viu não se perde;
#   5. EXPIRAÇÃO fecha novo despacho e NÃO fecha a recuperação histórica;
#   6. o snapshot é server-only, e o recibo não vaza id nem endpoint;
#   7. reaplicar é recusado, rollback respeita a ordem, reapply funciona;
#   8. o catálogo vivo é classificado pelo verificador, e ele exige PERFIL_ATUAL.
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

PROVAS=0
FALHAS=0

limpar() {
  "$PGBIN/pg_ctl" -D "$DADOS" -m immediate stop >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap limpar EXIT

psql_() { "$PGBIN/psql" -h 127.0.0.1 -p "$PORTA" -U postgres -v ON_ERROR_STOP=1 "$@"; }

# ⚠️ AS DUAS FUNÇÕES QUE TRANSFORMAM LEGENDA EM PORTÃO.
ok() {  # ok <descrição> <valor> <esperado>
  PROVAS=$((PROVAS + 1))
  if [ "$2" = "$3" ]; then
    printf '   OK   %s\n' "$1"
  else
    FALHAS=$((FALHAS + 1))
    printf '   FALHA %s — esperado [%s], obtido [%s]\n' "$1" "$3" "$2"
  fi
}

contem() {  # contem <descrição> <texto> <trecho exigido>
  PROVAS=$((PROVAS + 1))
  case "$2" in
    *"$3"*) printf '   OK   %s\n' "$1" ;;
    *) FALHAS=$((FALHAS + 1))
       printf '   FALHA %s — o texto não contém [%s]: %s\n' "$1" "$3" "$2" ;;
  esac
}

echo "== 0. o perfil declarado bate com os arquivos =="
# ⚠️ ANTES DE SUBIR CLUSTER NENHUM. Checksum divergente, dependência fora de
# ordem ou rollback na lista de apply são erros de CONSTRUÇÃO da janela, e
# descobri-los depois do primeiro `psql` seria descobrir tarde demais.
python3 "$RAIZ/scripts/verificar_perfil_schema_meta.py" --arquivos --runtime
PROVAS=$((PROVAS + 1))
# ⚠️ Sem `mapfile`: o bash que a Apple entrega é o 3.2, e ele não o tem. Um
# array montado com `read` funciona nos dois.
APLICAR=()
while IFS= read -r LINHA; do
  [ -n "$LINHA" ] && APLICAR+=("$LINHA")
done < <(python3 "$RAIZ/scripts/verificar_perfil_schema_meta.py" --lista-apply)
ok "o manifesto declara os arquivos do perfil" "$([ ${#APLICAR[@]} -ge 3 ] && echo sim || echo nao)" "sim"

echo
echo "== 0b. cluster descartável em $DADOS (porta $PORTA) =="
"$PGBIN/initdb" -D "$DADOS" -U postgres --auth=trust --no-locale --encoding=UTF8 >/dev/null
"$PGBIN/pg_ctl" -D "$DADOS" -o "-p $PORTA -k $TMP -c listen_addresses=127.0.0.1" \
  -l "$TMP/server.log" -w start >/dev/null
psql_ -d postgres -Atc "select 'engine: '||version();"

psql_ -d postgres -q -c "CREATE DATABASE $BASE;"
psql_ -d "$BASE" -q -c "CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN BYPASSRLS;"

echo
echo "== 1. apply do perfil, na ordem do MANIFESTO =="
# ⚠️ Lista EXPLÍCITA e derivada do manifesto. Nunca `supabase/migrations/*.sql`:
# 20 dos 48 arquivos SQL do diretório são ROLLBACKS, e um glob executaria apply
# e rollback na mesma passada. O executor é `psql` porque todo arquivo abre com
# a meta-instrução `\set ON_ERROR_STOP`.
for f in "${APLICAR[@]}"; do
  printf '   %-52s ' "$f"
  psql_ -d "$BASE" -q -f "$RAIZ/supabase/migrations/$f" >/dev/null && echo "APLICADA"
done

echo
echo "== 2. fronteira de autorização com os papéis REAIS =="
# Cada bloco LEVANTA se a chamada for aceita, e `ON_ERROR_STOP=1` derruba o
# script. A asserção é o próprio `RAISE`.
psql_ -d "$BASE" -q <<'SQL'
DO $$
BEGIN
  SET LOCAL ROLE anon;
  PERFORM public.trafego_meta_create_receipt(gen_random_uuid());
  RAISE EXCEPTION 'FALHA: anon executou a RPC';
EXCEPTION WHEN insufficient_privilege THEN RAISE NOTICE '   OK   anon recusado na função';
END $$;
DO $$
BEGIN
  SET LOCAL ROLE authenticated;
  PERFORM count(*) FROM public.trafego_meta_create_approval;
  RAISE EXCEPTION 'FALHA: authenticated leu a tabela';
EXCEPTION WHEN insufficient_privilege THEN RAISE NOTICE '   OK   authenticated sem SELECT na tabela';
END $$;
DO $$
BEGIN
  SET LOCAL ROLE service_role;
  INSERT INTO public.trafego_meta_create_step (approval_id, step_name, ordinal, payload_sha256)
  VALUES (gen_random_uuid(), 'campaign', 1, repeat('a',64));
  RAISE EXCEPTION 'FALHA: service_role escreveu direto na tabela';
EXCEPTION WHEN insufficient_privilege THEN RAISE NOTICE '   OK   service_role sem INSERT direto — só a RPC escreve';
END $$;
SQL
PROVAS=$((PROVAS + 3))

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
# ⚠️ `|| true` porque o perdedor da corrida pode ABORTAR — e abortar também é
# um desfecho honesto. O que não pode é os DOIS despacharem, e é isso que a
# asserção abaixo cobra.
psql_ -d "$BASE" -Atq -v aprov="$APROVACAO" -f "$TMP/worker.sql" > "$TMP/w1" 2>&1 || true &
psql_ -d "$BASE" -Atq -v aprov="$APROVACAO" -f "$TMP/worker.sql" > "$TMP/w2" 2>&1 || true &
wait
W1=$(grep -vE '^$|^SET$|^BEGIN$|^COMMIT$' "$TMP/w1" | head -1)
W2=$(grep -vE '^$|^SET$|^BEGIN$|^COMMIT$' "$TMP/w2" | head -1)
echo "   worker1: $W1"
echo "   worker2: $W2"
# ⚠️ ANTES ISTO ERA UM `echo`. Os dois estados eram impressos e nada os
# comparava: a prova de que no máximo um despacho é autorizado existia só na
# frase que vinha depois.
DESPACHOS=0
[ "$W1" = "DESPACHAR" ] && DESPACHOS=$((DESPACHOS + 1))
[ "$W2" = "DESPACHAR" ] && DESPACHOS=$((DESPACHOS + 1))
ok "no máximo UM worker recebe DESPACHAR" "$DESPACHOS" "1"
OUTRO=0
[ "$W1" = "AMBIGUO" ] && OUTRO=$((OUTRO + 1))
[ "$W2" = "AMBIGUO" ] && OUTRO=$((OUTRO + 1))
ok "o outro é obrigado a reconciliar (AMBIGUO)" "$OUTRO" "1"

echo
echo "== 5. A CERCA: autoridade velha não conclui, e o id visto não se perde =="
# O cenário exato de R0-A06, com DUAS sessões reais e a resposta do primeiro
# trabalhador chegando atrasada.
psql_ -d "$BASE" -q -c "DELETE FROM public.trafego_meta_create_step;"
TOKEN=$(psql_ -d "$BASE" -Atq -v aprov="$APROVACAO" <<'SQL' | tail -1
SET ROLE service_role;
SELECT public.trafego_meta_create_prepare_step(
  repeat('7',64), :'aprov'::uuid, 'ator-1', 'campaign', repeat('8',64)) ->> 'claim_token';
SQL
)
PASSO=$(psql_ -d "$BASE" -Atc "SELECT step_id FROM public.trafego_meta_create_step WHERE step_name='campaign';")
ok "o DESPACHAR entrega um token de reivindicação" \
   "$([ -n "$TOKEN" ] && [ "$TOKEN" != "" ] && echo sim || echo nao)" "sim"

# A segunda sessão toma a reivindicação enquanto a primeira ainda está no ar.
psql_ -d "$BASE" -q -c "UPDATE public.trafego_meta_create_step SET prepared_at = clock_timestamp() - interval '30 minutes';"
GERACAO=$(psql_ -d "$BASE" -Atq <<SQL | tail -1
SET ROLE service_role;
SELECT public.trafego_meta_create_reclaim_orphan('$PASSO'::uuid, 300) ->> 'claim_generation';
SQL
)
ok "a promoção por idade INCREMENTA a geração (revoga)" "$GERACAO" "2"

# O trabalhador antigo volta com o token velho. Ele NÃO pode concluir.
SAIDA=$(psql_ -d "$BASE" -Atq <<SQL 2>&1 || true
SET ROLE service_role;
SELECT public.trafego_meta_create_close_step('$PASSO'::uuid, '1001', '$TOKEN'::uuid);
SQL
)
contem "fechar com token vencido é recusado PELA CAUSA" "$SAIDA" "META_STEP_CLAIM_FENCED"
SAIDA=$(psql_ -d "$BASE" -Atq <<SQL 2>&1 || true
SET ROLE service_role;
SELECT public.trafego_meta_create_fail_step('$PASSO'::uuid, 'META_TESTE', '$TOKEN'::uuid);
SQL
)
contem "FALHAR com token vencido é recusado PELA CAUSA" "$SAIDA" "META_STEP_CLAIM_FENCED"

# Mas o id que ele viu nascer NÃO se perde: nenhuma linha de banco cancela uma
# requisição já entregue.
psql_ -d "$BASE" -Atq >/dev/null <<SQL
SET ROLE service_role;
SELECT public.trafego_meta_create_record_fenced_dispatch('$PASSO'::uuid, '$TOKEN'::uuid, '1001');
SQL
OBSERVADO=$(psql_ -d "$BASE" -Atc "SELECT observed_external_ids::text FROM public.trafego_meta_create_step WHERE step_id='$PASSO';")
ok "o id observado pelo cercado é preservado" "$OBSERVADO" '["1001"]'
ESTADO=$(psql_ -d "$BASE" -Atc "SELECT state||'/'||coalesce(external_object_id,'-') FROM public.trafego_meta_create_step WHERE step_id='$PASSO';")
ok "e ele NÃO vira identidade concluída do passo" "$ESTADO" "AMBIGUOUS/-"

# A recuperação por LEITURA é quem conclui, e ela grava a evidência junto.
psql_ -d "$BASE" -Atq >/dev/null <<SQL
SET ROLE service_role;
SELECT public.trafego_meta_create_conclude_by_recovery(
  '$PASSO'::uuid, '1001', '{"matched": true, "tipo": "campaign", "status": "PAUSED"}'::jsonb);
SQL
CONFIRMADO=$(psql_ -d "$BASE" -Atq <<SQL | tail -1
SET ROLE service_role;
SELECT (s->>'readback_confirmed') FROM jsonb_array_elements(
  public.trafego_meta_create_receipt('$APROVACAO'::uuid) -> 'steps') s
 WHERE s->>'name' = 'campaign';
SQL
)
ok "a leitura conclui o passo E grava a confirmação" "$CONFIRMADO" "true"

echo
echo "== 6. o invariante central: expiração fecha DESPACHO, não RECUPERAÇÃO =="
psql_ -d "$BASE" -q -c "UPDATE public.trafego_meta_create_step SET state='IN_FLIGHT', external_object_id=NULL, closed_at=NULL, readback_at=NULL, readback_evidence=NULL, claim_token=NULL, claim_owner=NULL, claimed_at=NULL, prepared_at=clock_timestamp()-interval '30 minutes';"
psql_ -d "$BASE" -q -c "UPDATE public.trafego_meta_create_approval SET expires_at = approved_at + interval '1 second';"
ESTADO=$(psql_ -d "$BASE" -Atq <<SQL | tail -1
SET ROLE service_role;
SELECT public.trafego_meta_create_receipt('$APROVACAO'::uuid) ->> 'state';
SQL
)
ok "a aprovação vencida é declarada EXPIRED" "$ESTADO" "EXPIRED"
# ⚠️ A RECUSA É CONFERIDA PELA CAUSA. `WHEN OTHERS` aceitaria um erro de
# digitação como se fosse o portão funcionando.
SAIDA=$(psql_ -d "$BASE" -Atq <<SQL 2>&1 || true
SET ROLE service_role;
SELECT public.trafego_meta_create_prepare_step(
  repeat('7',64), '$APROVACAO'::uuid, 'ator-1', 'adset', repeat('9',64));
SQL
)
contem "novo despacho recusado PELA CAUSA certa" "$SAIDA" "META_APPROVAL_NOT_ACTIVE"
RECLAIM=$(psql_ -d "$BASE" -Atq <<SQL | tail -1
SET ROLE service_role;
SELECT public.trafego_meta_create_reclaim_orphan(
  (SELECT step_id FROM public.trafego_meta_create_step LIMIT 1), 300) ->> 'state';
SQL
)
ok "o órfão continua recuperável com aprovação EXPIRADA" "$RECLAIM" "AMBIGUOUS"
VISIVEIS=$(psql_ -d "$BASE" -Atq <<SQL | tail -1
SET ROLE service_role;
SELECT count(*) FILTER (WHERE s->>'state'='AMBIGUOUS')
  FROM jsonb_array_elements(public.trafego_meta_create_approval_manifest('$APROVACAO'::uuid) -> 'steps') s;
SQL
)
ok "e ele APARECE para a reconciliação" "$VISIVEIS" "1"

echo
echo "== 7. o snapshot é server-only, e o recibo não vaza identificador =="
INTERNO=$(psql_ -d "$BASE" -Atq <<SQL | tail -1
SET ROLE service_role;
SELECT (public.trafego_meta_create_approval_manifest('$APROVACAO'::uuid) ? 'compiled_plan')::text;
SQL
)
ok "o manifesto INTERNO traz compiled_plan" "$INTERNO" "true"
NAVEGADOR=$(psql_ -d "$BASE" -Atq <<SQL | tail -1
SET ROLE service_role;
SELECT (public.trafego_meta_create_receipt('$APROVACAO'::uuid) ? 'compiled_plan')::text;
SQL
)
# ⚠️ ANTES ISTO ERA UM `echo` com "(precisa ser false)" ao lado. O valor era
# impresso e nada o comparava.
ok "o recibo do navegador NÃO traz compiled_plan" "$NAVEGADOR" "false"
VAZOU=$(psql_ -d "$BASE" -Atq <<SQL | tail -1
SET ROLE service_role;
SELECT (public.trafego_meta_create_receipt('$APROVACAO'::uuid)::text LIKE '%act_1234567890%')::text;
SQL
)
ok "o recibo do navegador NÃO vaza o endpoint da conta" "$VAZOU" "false"
VAZOU_ID=$(psql_ -d "$BASE" -Atq <<SQL | tail -1
SET ROLE service_role;
SELECT (public.trafego_meta_create_receipt('$APROVACAO'::uuid)::text LIKE '%external_object_id%')::text;
SQL
)
ok "o recibo do navegador NÃO traz external_object_id" "$VAZOU_ID" "false"

echo
echo "== 8. o catálogo vivo é classificado, e precisa ser o PERFIL ATUAL =="
psql_ -d "$BASE" -Atq > "$TMP/catalogo.json" <<'SQL'
SELECT jsonb_pretty(jsonb_build_object(
  'columns', (SELECT coalesce(jsonb_agg(c.rel||'.'||c.att), '[]'::jsonb) FROM (
      SELECT a.attrelid::regclass::text AS rel, a.attname AS att
        FROM pg_attribute a
       WHERE a.attrelid IN ('public.trafego_meta_create_step'::regclass,
                            'public.trafego_meta_create_approval'::regclass)
         AND a.attnum > 0 AND NOT a.attisdropped) c),
  'constraints', (SELECT coalesce(jsonb_agg(conname), '[]'::jsonb) FROM pg_constraint
     WHERE conrelid IN ('public.trafego_meta_create_step'::regclass,
                        'public.trafego_meta_create_approval'::regclass)),
  'functions', (SELECT coalesce(jsonb_agg(
       p.proname||'('||pg_get_function_identity_arguments(p.oid)||')'), '[]'::jsonb)
     FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='public' AND p.proname LIKE 'trafego_meta%'),
  'security_definer', (SELECT coalesce(jsonb_agg(
       p.proname||'('||pg_get_function_identity_arguments(p.oid)||')'), '[]'::jsonb)
     FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='public' AND p.proname LIKE 'trafego_meta%' AND p.prosecdef),
  'granted', (SELECT coalesce(jsonb_agg(
       p.proname||'('||pg_get_function_identity_arguments(p.oid)||')'), '[]'::jsonb)
     FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='public' AND p.proname LIKE 'trafego_meta%'
      AND has_function_privilege('service_role', p.oid, 'EXECUTE'))
));
SQL
python3 "$RAIZ/scripts/verificar_perfil_schema_meta.py" --catalogo "$TMP/catalogo.json"
PROVAS=$((PROVAS + 1))
echo "   OK   catálogo classificado como PERFIL_ATUAL"

echo
echo "== 9. repetição, rollback na ORDEM e reapply =="
# ⚠️ ANTES: `&& echo "FALHA (reaplicou)" || echo "RECUSADO"` — que imprime a
# violação e sai com zero. Agora reaplicar com sucesso é FALHA de verdade.
if psql_ -d "$BASE" -q -f "$RAIZ/supabase/migrations/20260907190000_meta_worker_fencing.sql" >/dev/null 2>&1; then
  REAPLICOU="sim"
else
  REAPLICOU="nao"
fi
ok "reaplicar a cerca sobre schema já aplicado é RECUSADO" "$REAPLICOU" "nao"

# Reverter FORA DE ORDEM precisa ser recusado: o rollback do snapshot com a
# cerca viva criaria uma segunda sobrecarga de flag_readback e dropparia colunas
# que as funções da cerca leem.
SAIDA=$(psql_ -d "$BASE" -q -f "$RAIZ/supabase/migrations/20260907120100_meta_recovery_snapshot_rollback.sql" 2>&1 || true)
contem "rollback FORA DE ORDEM é recusado pela causa" "$SAIDA" "BLOQUEADO"

# Com ids reais no livro, o rollback da cerca também recusa — apagar o ledger
# não apaga a campanha, apaga só a prova dela.
psql_ -d "$BASE" -q -c "UPDATE public.trafego_meta_create_step SET observed_external_ids='[\"1001\"]'::jsonb;"
SAIDA=$(psql_ -d "$BASE" -q -f "$RAIZ/supabase/migrations/20260907190100_meta_worker_fencing_rollback.sql" 2>&1 || true)
contem "rollback com id conhecido é PROIBIDO" "$SAIDA" "PROIBIDO"

psql_ -d "$BASE" -q -c "DELETE FROM public.trafego_meta_create_step;"
psql_ -d "$BASE" -q -f "$RAIZ/supabase/migrations/20260907190100_meta_worker_fencing_rollback.sql" >/dev/null
ok "rollback da cerca sobre tabelas vazias" "ok" "ok"
psql_ -d "$BASE" -q -f "$RAIZ/supabase/migrations/20260907120100_meta_recovery_snapshot_rollback.sql" >/dev/null
ok "rollback do snapshot, agora na ordem certa" "ok" "ok"
PRESERVADO=$(psql_ -d "$BASE" -Atc "select count(*) from unnest(array['trafego_meta_create_approval','trafego_meta_create_step','trafego_meta_validation_receipt']) t where to_regclass('public.'||t) is not null;")
ok "o CREATE_ONLY base é PRESERVADO pelos dois rollbacks" "$PRESERVADO" "3"
psql_ -d "$BASE" -q -f "$RAIZ/supabase/migrations/20260907120000_meta_recovery_snapshot.sql" >/dev/null
psql_ -d "$BASE" -q -f "$RAIZ/supabase/migrations/20260907190000_meta_worker_fencing.sql" >/dev/null
ok "reapply da escada inteira" "ok" "ok"

echo
echo "============================================================"
if [ "$FALHAS" -eq 0 ]; then
  echo "PROVA COMPLETA: $PROVAS asserções, 0 falhas."
  echo "Cluster descartável removido. Nenhum banco oficial foi tocado."
  exit 0
fi
echo "PROVA REPROVADA: $PROVAS asserções, $FALHAS falha(s)."
echo "Cluster descartável removido. Nenhum banco oficial foi tocado."
exit 1
