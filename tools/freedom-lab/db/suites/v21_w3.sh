# shellcheck shell=bash
# =============================================================================
# tools/freedom-lab/db/suites/v21_w3.sh — suíte do pacote v21 (W3) para o lab.sh
#
# Prova oficial (no Mac: o dump do schema de produção não entra na nuvem):
#
#   LAB_DUMP=<dump schema-only, fora do repo> LAB_DUMP_SHA256=<sha256 do dump> \
#   MIGRATION=supabase/migrations/v21_pacote_aplicar.sql \
#   ROLLBACK=supabase/migrations/v21_pacote_reverter.sql \
#   MIGRATION_SUITE=tools/freedom-lab/db/suites/v21_w3.sh \
#   tools/freedom-lab/lab.sh recriar-prod
#
# O gancho MIGRATION_SUITE e o recriar-prod são do lab.sh do integrador. A suíte
# precisa estar commitada aqui para o recibo registrar producao_acessada:false.
# MIGRATION/ROLLBACK apontam para o pacote só para o recibo citar os sha256
# certos; quem aplica e reverte é a própria suíte (que confere isso abaixo).
#
# Não é laboratório: não sobe container, não publica porta, não lê .env, não
# gera JWT. Roda DENTRO do lab.sh (carregada por ele) e usa só o que ele dá:
#   P            psql no container do lab (exige rótulo volc.freedom-lab=1 e --network none)
#   estado       SQL como papel (SET LOCAL ROLE), devolve SQLSTATE ou ok:<1ª linha>, com ROLLBACK
#   sqlstate     SQL como postgres, devolve SQLSTATE ou ok (aqui, com COMMIT)
#   ok nao eq    contadores globais T/F e recibo do lab.sh
#   RAIZ RECIBOS FP (FP = caminho do db/fingerprint_schema.sql)
#
# Base exigida: schema de produção (public.users com id uuid, public.campaigns,
# app_auth.user_roles, public.volc_current_admin(), auth.uid()). Sobre a base
# "imagem + semente" a pré-checagem acusa base errada e a suíte FALHA, em vez
# de passar sem provar nada.
#
# O que prova, sobre supabase/migrations/v21_pacote_{aplicar,reverter}.sql:
#   1. o pacote está em dia com as partes (scripts/montar-pacote-v21.sh --check)
#   2. sem janela: durante o pacote aberto, outra sessão (e a anon) não vê tabela
#   3. erro no fim do pacote desfaz tudo, inclusive v7_13 e v6_01..v6_05
#   4. matriz anon / usuário comum / admin / service_role pelos papéis do banco
#   5. reverter recusa com dado de negócio, e a recusa desfaz o reverter inteiro
#   6. reverter devolve o fingerprint anterior, é idempotente, e reaplicar é idêntico
#   7. reaplicar por cima é recusado pela pré-checagem
#
# Identidades sintéticas fixas (@v21.example.invalid); nenhum dado real.
# Simulação de papel por SET LOCAL ROLE + claim no GUC, como o PostgREST faz:
# prova o banco, não o PostgREST.
# =============================================================================

for _f in P ok nao eq estado sqlstate; do  # contrato do lab.sh: também PA, login_como, SONDA
  declare -F "$_f" >/dev/null || { echo "ERRO: v21_w3.sh precisa ser carregada pelo lab.sh (falta $_f)" >&2; return 1 2>/dev/null || exit 1; }
done
unset _f

V21_APLICAR="$RAIZ/supabase/migrations/v21_pacote_aplicar.sql"
V21_REVERTER="$RAIZ/supabase/migrations/v21_pacote_reverter.sql"
V21_ADMIN=00000000-0000-4000-8000-00000000a021
V21_COMUM=00000000-0000-4000-8000-00000000c021
V21_CAMP=v21-lab-0001
V21_TABELAS="meta_capi_sites campaign_roles campaign_members campaign_commissions daily_campaign_member_payouts"

# Claims que auth.uid() lê, como o PostgREST põe. $1 papel  $2 sub (vazio = anon)
v21_claims() { printf "SET LOCAL request.jwt.claim.sub = '%s'; SET LOCAL request.jwt.claims = '{\"sub\":\"%s\",\"role\":\"%s\"}'" "$2" "$2" "$1"; }
# Lê/tenta como papel e desfaz (estado do lab.sh). $1 papel  $2 sub  $3 sql
v21_como() { estado "$1" "$(v21_claims "$1" "$2"); $3"; }
# Grava como papel e CONFIRMA (sqlstate do lab.sh). $1 papel  $2 sub  $3 sql
v21_grava() { sqlstate "BEGIN; SET LOCAL ROLE $1; $(v21_claims "$1" "$2"); $3; COMMIT;"; }
v21_sql() { P -c "$1" 2>&1 | head -1; }
v21_existem() { # quantas das 5 tabelas existem
  v21_sql "select count(*) from unnest(string_to_array('$V21_TABELAS',' ')) t where to_regclass('public.'||t) is not null"
}
v21_aplicar()  { P -f - < "$V21_APLICAR"  > "$RECIBOS/v21-$1.out" 2>&1; }
v21_reverter() { P -f - < "$V21_REVERTER" > "$RECIBOS/v21-$1.out" 2>&1; }
v21_fp() { P -f - < "$FP" > "$RECIBOS/v21-fp-$1.out" 2>&1; }

v21_suite() {
  mkdir -p "$RECIBOS"
  echo "▶ v21 · pré-checagem da base"
  local base
  base=$(v21_sql "select (select format_type(atttypid, atttypmod) from pg_attribute where attrelid = to_regclass('public.users') and attname = 'id') = 'uuid'
                    and to_regclass('public.campaigns') is not null and to_regclass('app_auth.user_roles') is not null
                    and to_regprocedure('public.volc_current_admin()') is not null and to_regprocedure('auth.uid()') is not null")
  if [ "$base" != "t" ]; then
    nao "v21 · base errada: faltam public.users(id uuid), campaigns, app_auth.user_roles, volc_current_admin() ou auth.uid() (use a base de produção)"
    return 1
  fi
  ok "v21 · base tem os pré-requisitos das v6 e da v8_01"
  local out
  if out=$("$RAIZ/scripts/montar-pacote-v21.sh" --check 2>&1); then ok "v21 · pacote em dia com as partes"; else nao "v21 · $out"; fi
  eq "$(grep -c '^COMMIT;$' "$V21_APLICAR")" "1" "v21 · pacote aplicar tem um único COMMIT"
  eq "$(grep -c '^BEGIN;$' "$V21_APLICAR")" "1" "v21 · pacote aplicar tem um único BEGIN"
  eq "$(basename "${MIGRATION:-}")|$(basename "${ROLLBACK:-}")" "v21_pacote_aplicar.sql|v21_pacote_reverter.sql" "v21 · MIGRATION/ROLLBACK do recibo são o pacote v21"
  eq "$(v21_existem)" "0" "v21 · antes: nenhuma das 5 tabelas existe (estado de produção em 15/10)"

  echo "▶ v21 · identidades sintéticas"
  P > "$RECIBOS/v21-semente.out" 2>&1 <<SQL
CREATE FUNCTION pg_temp.v21_semear(tab regclass, base jsonb) RETURNS void LANGUAGE plpgsql AS \$f\$
DECLARE
  v jsonb := base; r record; cols text;
BEGIN
  -- Preenche colunas NOT NULL sem default que a base não trouxe, por tipo.
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
      ELSE to_jsonb('v21-lab'::text) END);
  END LOOP;
  SELECT string_agg(quote_ident(k), ', ') INTO cols FROM jsonb_object_keys(v) k;
  EXECUTE format('INSERT INTO %s (%s) SELECT %s FROM jsonb_populate_record(NULL::%s, \$1) ON CONFLICT DO NOTHING',
                 tab, cols, cols, tab) USING v;
END
\$f\$;
SELECT pg_temp.v21_semear('auth.users', '{"id":"$V21_ADMIN","email":"admin@v21.example.invalid"}');
SELECT pg_temp.v21_semear('auth.users', '{"id":"$V21_COMUM","email":"comum@v21.example.invalid"}');
SELECT pg_temp.v21_semear('public.users', '{"id":"$V21_ADMIN","email":"admin@v21.example.invalid"}');
SELECT pg_temp.v21_semear('public.users', '{"id":"$V21_COMUM","email":"comum@v21.example.invalid"}');
SELECT pg_temp.v21_semear('app_auth.user_roles', '{"auth_user_id":"$V21_ADMIN","role":"ADMIN"}');
SELECT pg_temp.v21_semear('public.campaigns', '{"campaign_id":"$V21_CAMP"}');
SQL
  eq "$(v21_sql "select count(*) from public.users where id in ('$V21_ADMIN','$V21_COMUM')")" "2" "v21 · dois usuários sintéticos semeados"
  eq "$(v21_como authenticated "$V21_ADMIN" 'select public.volc_current_admin()')" "ok:t" "v21 · harness: admin sintético é admin pela v8_01"
  eq "$(v21_como authenticated "$V21_COMUM" 'select public.volc_current_admin()')" "ok:f" "v21 · harness: comum não é admin"

  echo "▶ v21 · controle: a janela que o pacote fecha (v7_13 confirmada sozinha)"
  P -f - < "$RAIZ/src/sql/v7_13_meta_capi_sites.sql" > "$RECIBOS/v21-controle-v7_13.out" 2>&1
  eq "$(v21_sql "select has_table_privilege('anon','public.meta_capi_sites','SELECT,DELETE,TRUNCATE')")" "t" "v21 · controle: v7_13 sozinha deixa SELECT/DELETE/TRUNCATE para a anon (defeito do revisor reproduzido)"
  eq "$(v21_como anon '' 'truncate public.meta_capi_sites')" "ok:TRUNCATE TABLE" "v21 · controle: a anon trunca de fato, então as negações adiante vêm do pacote e não do harness"
  P -c "drop table public.meta_capi_sites" >/dev/null

  v21_fp antes

  echo "▶ v21 · sem janela: pacote aberto numa sessão, outra sessão olhando"
  sed 's/^COMMIT;$/SELECT pg_sleep(6);\nROLLBACK;/' "$V21_APLICAR" > "$RECIBOS/v21-aberto.sql"
  ( P -f - < "$RECIBOS/v21-aberto.sql" > "$RECIBOS/v21-aberto.out" 2>&1 ) &
  local bg=$! i aberto=0
  for i in $(seq 1 40); do
    [ "$(v21_sql "select count(*) from pg_stat_activity where state = 'active' and query like '%pg_sleep(6)%' and pid <> pg_backend_pid()")" = "1" ] && { aberto=1; break; }
    sleep 0.25
  done
  eq "$aberto" "1" "v21 · pacote chegou ao fim (pós-checagem) e está aberto, sem COMMIT"
  eq "$(v21_existem)" "0" "v21 · outra sessão não vê nenhuma das 5 tabelas enquanto o pacote está aberto"
  eq "$(v21_como anon '' 'select count(*) from public.campaign_commissions')" "42P01" "v21 · anon durante o pacote: campaign_commissions não existe para ela"
  eq "$(v21_como anon '' 'select count(*) from public.meta_capi_sites')" "42P01" "v21 · anon durante o pacote: meta_capi_sites não existe para ela"
  wait "$bg"
  eq "$(v21_existem)" "0" "v21 · ROLLBACK do pacote aberto não deixa resíduo"

  echo "▶ v21 · erro no fim desfaz tudo"
  sed 's/^COMMIT;$/SELECT 1\/0;/' "$V21_APLICAR" | P -f - > "$RECIBOS/v21-erro-no-fim.out" 2>&1 && nao "v21 · pacote com erro no fim passou" || \
    { grep -q 'division by zero' "$RECIBOS/v21-erro-no-fim.out" && ok "v21 · pacote com erro no fim falhou pelo erro plantado" || nao "v21 · pacote falhou por outro motivo"; }
  eq "$(v21_existem)" "0" "v21 · depois do erro: nenhuma tabela (v7_13 e v6_0x desfeitas junto)"
  eq "$(v21_sql "select count(*) from pg_proc where pronamespace = 'public'::regnamespace and proname like 'v6\_%'")" "0" "v21 · depois do erro: nenhuma função v6"

  echo "▶ v21 · aplicar"
  v21_aplicar aplicar && ok "v21 · pacote aplicou" || nao "v21 · pacote aplicar ($(tail -1 "$RECIBOS/v21-aplicar.out"))"
  eq "$(v21_existem)" "5" "v21 · as 5 tabelas existem"
  v21_fp depois1

  echo "▶ v21 · matriz de acesso"
  local t
  for t in $V21_TABELAS; do
    eq "$(v21_sql "select has_table_privilege('anon','public.$t','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')")" "f" "v21 · anon sem nenhum privilégio em $t"
    eq "$(v21_como anon '' "select count(*) from public.$t")" "42501" "v21 · anon lê $t: negado"
    eq "$(v21_como anon '' "truncate public.$t cascade")" "42501" "v21 · anon trunca $t: negado"
    eq "$(v21_sql "select relrowsecurity from pg_class where oid = 'public.$t'::regclass")" "t" "v21 · RLS ligada em $t"
  done
  eq "$(v21_como authenticated "$V21_ADMIN" 'select count(*) from public.meta_capi_sites')" "42501" "v21 · admin logado não lê meta_capi_sites (token da Meta)"
  eq "$(v21_como service_role '' 'select count(*) from public.meta_capi_sites')" "ok:0" "v21 · service_role lê meta_capi_sites"
  eq "$(v21_como authenticated "$V21_COMUM" 'select count(*) from public.campaign_roles')" "ok:4" "v21 · comum lê o catálogo de papéis"
  eq "$(v21_como authenticated "$V21_ADMIN" "insert into public.campaign_roles(code,label) values ('X','x')")" "42501" "v21 · admin não escreve no catálogo pelo cliente"
  local ins_c="insert into public.campaign_members(user_id,campaign_id,role_id) select '$V21_COMUM','$V21_CAMP',id from public.campaign_roles where code='OPERATOR'"
  local ins_a="insert into public.campaign_members(user_id,campaign_id,role_id) select '$V21_ADMIN','$V21_CAMP',id from public.campaign_roles where code='OWNER'"
  eq "$(v21_como authenticated "$V21_COMUM" "$ins_c")" "42501" "v21 · comum NÃO cria vínculo (nem para si)"
  eq "$(v21_grava authenticated "$V21_ADMIN" "$ins_c")" "ok" "v21 · admin cria vínculo do comum"
  eq "$(v21_grava authenticated "$V21_ADMIN" "$ins_a")" "ok" "v21 · admin cria o próprio vínculo"
  eq "$(v21_como authenticated "$V21_COMUM" 'select count(*) from public.campaign_members')" "ok:1" "v21 · comum vê só o próprio vínculo"
  eq "$(v21_como authenticated "$V21_ADMIN" 'select count(*) from public.campaign_members')" "ok:2" "v21 · admin vê todos os vínculos"
  eq "$(v21_como authenticated "$V21_COMUM" "with u as (update public.campaign_members set role_id = role_id where user_id = '$V21_ADMIN' returning 1) select count(*) from u")" "ok:0" "v21 · comum altera vínculo alheio: 0 linhas"
  eq "$(v21_como authenticated "$V21_COMUM" "with d as (delete from public.campaign_members returning 1) select count(*) from d")" "ok:0" "v21 · comum apaga vínculos: 0 linhas"
  eq "$(v21_como authenticated "$V21_COMUM" "insert into public.campaign_commissions(user_id,campaign_id,percentage,valid_from) values ('$V21_COMUM','$V21_CAMP',50,'2026-10-01')")" "42501" "v21 · comum NÃO se dá comissão"
  eq "$(v21_como authenticated "$V21_COMUM" "insert into public.daily_campaign_member_payouts(date,campaign_id,user_id,commission_percentage,revenue_revshare,spend,tax_rate,tax_amount,net_profit,amount) values ('2026-10-14','$V21_CAMP','$V21_COMUM',1,1,1,1,1,1,1)")" "42501" "v21 · comum NÃO escreve payout"
  eq "$(v21_como authenticated "$V21_COMUM" "select public.v6_populate_member_payouts_for_date('2026-10-14')")" "42501" "v21 · comum NÃO roda v6_populate_*"
  eq "$(v21_como anon '' "select public.v6_get_active_commission_rate('$V21_COMUM','$V21_CAMP','2026-10-14')")" "42501" "v21 · anon NÃO roda v6_get_active_commission_rate"

  echo "▶ v21 · reverter recusa com dado, e a recusa é atômica"
  v21_reverter reverter-com-vinculo && nao "v21 · reverter apagou vínculos" || \
    { grep -q 'campaign_members tem' "$RECIBOS/v21-reverter-com-vinculo.out" && ok "v21 · reverter recusa com vínculo existente" || nao "v21 · reverter falhou por outro motivo"; }
  P -c "delete from public.campaign_members" >/dev/null
  P -c "insert into public.meta_capi_sites(site_key,site_name,domain,cookie_domain,endpoint_url,pixel_id,capi_token_cipher,capi_token_iv) values ('v21','v21','v21.example.invalid','.example.invalid','https://v21.example.invalid/capi','0','x','x')" >/dev/null
  v21_reverter reverter-com-site && nao "v21 · reverter apagou site cadastrado" || \
    { grep -q 'meta_capi_sites tem' "$RECIBOS/v21-reverter-com-site.out" && ok "v21 · reverter recusa com site cadastrado" || nao "v21 · reverter falhou por outro motivo"; }
  eq "$(v21_existem)" "5" "v21 · recusa no v21_01_rollback desfez o v21_02_rollback que já tinha rodado"
  P -c "delete from public.meta_capi_sites" >/dev/null

  echo "▶ v21 · reverter"
  v21_reverter reverter && ok "v21 · pacote reverter aplicou" || nao "v21 · reverter ($(tail -1 "$RECIBOS/v21-reverter.out"))"
  eq "$(v21_existem)" "0" "v21 · as 5 tabelas sumiram"
  eq "$(v21_sql "select count(*) from pg_proc where proname = 'set_pautador_updated_at'")" "1" "v21 · set_pautador_updated_at preservada"
  v21_fp depois-reverter
  diff -q "$RECIBOS/v21-fp-antes.out" "$RECIBOS/v21-fp-depois-reverter.out" >/dev/null && ok "v21 · reverter devolve o fingerprint exato de antes" || nao "v21 · reverter deixou resíduo no schema"
  v21_reverter reverter-de-novo && ok "v21 · reverter idempotente" || nao "v21 · reverter idempotente"

  echo "▶ v21 · reaplicar"
  v21_aplicar reaplicar && ok "v21 · pacote reaplicou depois do reverter" || nao "v21 · reaplicar"
  v21_fp depois2
  diff -q "$RECIBOS/v21-fp-depois1.out" "$RECIBOS/v21-fp-depois2.out" >/dev/null && ok "v21 · fingerprint idêntico entre 1ª e 2ª aplicação" || nao "v21 · fingerprint divergiu entre aplicações"
  diff -q "$RECIBOS/v21-fp-antes.out" "$RECIBOS/v21-fp-depois1.out" >/dev/null && nao "v21 · fingerprint não mudou com o pacote" || ok "v21 · fingerprint muda com o pacote"
  v21_aplicar por-cima && nao "v21 · reaplicar por cima passou" || \
    { grep -q 'já existe — este pacote não reaplica' "$RECIBOS/v21-por-cima.out" && ok "v21 · reaplicar por cima recusado pela pré-checagem" || nao "v21 · reaplicar por cima falhou por outro motivo"; }
  v21_reverter limpeza >/dev/null && ok "v21 · lab devolvido ao estado anterior" || nao "v21 · limpeza final"
}

v21_suite
