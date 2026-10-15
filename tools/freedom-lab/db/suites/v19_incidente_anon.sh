# db/suites/v19_incidente_anon.sh — suíte do pacote do incidente da chave anon (W4).
# Carregada por lab.sh testar (MIGRATION_SUITE). Roda sobre a base de produção:
#
#   LAB_NOME=volc-lab-w4-anon \
#   LAB_DUMP=/Users/mac/Desktop/VOLC-OS-CAMPAIGN/handoffs/freedom-lab-20261015/prod-schema-only.sql \
#   LAB_DUMP_SHA256=2c70b4a4b5c6616d54c126c2a5e2be6d13d1f29e424f1ed2660d58f39e4c833c \
#   LAB_SEMENTE=tools/freedom-lab/db/suites/v19_incidente_anon_semente.sql \
#   MIGRATION=supabase/migrations/v19_01_anon_fecha_public.sql \
#   ROLLBACK=supabase/migrations/v19_99_rollback.sql \
#   MIGRATION_SUITE=tools/freedom-lab/db/suites/v19_incidente_anon.sh \
#   tools/freedom-lab/lab.sh recriar-prod
#
#   0. equivalência: fingerprint e sonda da base × saídas de PRODUÇÃO de 15/10
#      (W4_REF: B-fingerprint.sql, B-sonda-producao.sql e as saídas, fora do repo)
#   1. defeito reproduzido: anon lê e escreve users
#   2. pacote na ordem de produção: v19_00, v8_03, v19_01, v8_05, v19_02
#   3. matriz anon / authenticated (JWT de ADMIN e de OPERADOR) / service_role /
#      postgres / objeto novo; sonda S8 depois
#   4. v8_06 (passo 2): select('*') quebra, colunas nominais não
#   5. rollback v19_99 devolve o fingerprint exato da base; idempotente
#   6. reaplicação devolve o fingerprint da 1ª aplicação; guarda de reaplicação
# Usa os helpers do lab.sh: ok, nao, eq, estado, P, PA, registrar.
W4_REF="${W4_REF:-/Users/mac/Desktop/VOLC-OS-CAMPAIGN/handoffs/freedom-lab-20261015}"
W4_MIG="$RAIZ/supabase/migrations"; R="$RECIBOS"
H="$W4_REF"; FP_SQL="$W4_REF/B-fingerprint.sql"; SONDA_PROD="$W4_REF/B-sonda-producao.sql"
for f in "$FP_SQL" "$SONDA_PROD" "$W4_REF/fingerprint-prod.out" "$W4_REF/sonda-prod.out"; do
  [ -f "$f" ] || nao "referência de produção ausente: $f (a equivalência não é provada)"
done
fp()    { P -f - < "$FP_SQL" 2>&1 | grep '|' | tr -d ' ' > "$1"; }
sonda() { docker exec -i "$NOME" psql -U postgres -d postgres -X -P pager=off < "$SONDA_PROD" > "$1.out" 2> "$1.err"; }
# Mesmas identidades do script de aplicação em produção:
#   preflight → supabase_read_only_user, sessão read-only
#   verifica  → postgres (membro de anon), sessão read-only, SET ROLE anon de verdade
preflight() { docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' "$NOME" \
  psql -h localhost -U supabase_read_only_user -d postgres -X -q -A -t -F'|' -v ON_ERROR_STOP=1 \
  < "$RAIZ/scripts/preflight-incidente-anon-w4.sql" 2>&1; }
# verifica [usuario] → ABERTO | FECHADO | ILEGIVEL (mesma regra do script de aplicação)
verifica() {
  local u="${1:-postgres}" h="" out v1 v2 v4
  [ "$u" != postgres ] && h="-h localhost"
  out=$(docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' "$NOME" \
        psql $h -U "$u" -d postgres -X -q -A -t -F'|' -v ON_ERROR_STOP=1 < "$RAIZ/scripts/verificar-anon-w4.sql" 2>&1)
  v1=$(printf '%s\n' "$out" | awk -F'|' '$1=="V1"{print $3}'); v2=$(printf '%s\n' "$out" | awk -F'|' '$1=="V2"{print $3}')
  v4=$(printf '%s\n' "$out" | awk -F'|' '$1=="V4"{print $3}')
  printf '%s\n' "$out" >> "$RECIBOS/verifica.txt"
  [ -n "$v1" ] && [ -n "$v4" ] || { echo ILEGIVEL; return; }
  [ "$v1" = 0 ] && [ "$v2" = 0 ] && [ "$v4" = 0 ] && echo FECHADO || echo ABERTO
}
aplicar() { # aplicar <papel> <arquivo> — registra no ledger do lab
  local cmd=PA; [ "$1" = postgres ] && cmd=P
  if $cmd -f - < "$W4_MIG/$2" > "$RECIBOS/aplicar-$2.log" 2>&1; then registrar "$W4_MIG/$2" "$1" ok; return 0
  else registrar "$W4_MIG/$2" "$1" falhou; return 1; fi
}
PA -c "CREATE SCHEMA IF NOT EXISTS volc_lab; CREATE TABLE IF NOT EXISTS volc_lab.migracao_aplicada (
  arquivo text NOT NULL, sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  aplicada_em timestamptz NOT NULL DEFAULT now(), base text NOT NULL, resultado text NOT NULL);
  GRANT USAGE ON SCHEMA volc_lab TO postgres; GRANT ALL ON volc_lab.migracao_aplicada TO postgres" >/dev/null

ADMIN='{"sub":"a0000000-0000-4000-8000-00000000000a","email":"admin@example.invalid","role":"authenticated"}'
OPER='{"sub":"a0000000-0000-4000-8000-00000000000b","email":"operador@example.invalid","role":"authenticated"}'
# alcanca <papel>: quantas relações de public o papel consegue SELECT de verdade
ANON_ALCANCA="DO \$\$ DECLARE r record; n int := 0; BEGIN
  FOR r IN SELECT c.oid::regclass o FROM pg_class c WHERE c.relnamespace='public'::regnamespace AND c.relkind IN ('r','p','v','m') LOOP
    BEGIN EXECUTE format('SELECT 1 FROM %s LIMIT 1', r.o); n := n + 1;
    EXCEPTION WHEN insufficient_privilege THEN NULL; END; END LOOP;
  RAISE EXCEPTION 'ALCANCA=%', n; END \$\$"
alcanca() { printf 'BEGIN; SET LOCAL ROLE %s; %s; ROLLBACK;\n' "$1" "$ANON_ALCANCA" \
            | docker exec -i "$NOME" psql -h localhost -U supabase_admin -d postgres -X -A -t 2>&1 | grep -oE 'ALCANCA=[0-9]+' | cut -d= -f2; }

echo "▶ 0. equivalência da base com produção"
fp "$R/fp-base.txt"
for c in tabelas colunas indices views funcoes gatilhos extensoes grants_funcao; do
  eq "$(grep "^$c|" "$R/fp-base.txt")" "$(grep "^ *$c *|" "$H/fingerprint-prod.out" | tr -d ' ')" "fingerprint · $c idêntico a produção"
done
for c in constraints policies grants; do
  b=$(grep "^$c|" "$R/fp-base.txt" | cut -d'|' -f2); p=$(grep "^ *$c *|" "$H/fingerprint-prod.out" | tr -d ' ' | cut -d'|' -f2)
  eq "$b" "$p" "fingerprint · $c mesma contagem que produção (md5 diverge — ver handoff)"
done
sonda "$R/sonda-base"
diff <(sed -n '/== S7 /,/== S8/p' "$H/sonda-prod.out") <(sed -n '/== S7 /,/== S8/p' "$R/sonda-base.out") >/dev/null \
  && ok "sonda · S7/S7b (GRANT × RLS por tabela) idêntica a produção" || nao "sonda · S7/S7b diverge"
diff <(sed -n '/== S9/,/== S10/p' "$H/sonda-prod.out") <(sed -n '/== S9/,/== S10/p' "$R/sonda-base.out") >/dev/null \
  && ok "sonda · S9 (SECURITY DEFINER executáveis) idêntica a produção" || nao "sonda · S9 diverge"
diff <(sed -n '/== S10/,/== S11/p' "$H/sonda-prod.out" | sort) <(sed -n '/== S10/,/== S11/p' "$R/sonda-base.out" | sort) >/dev/null \
  && ok "sonda · S10 (default ACL) idêntica a produção" || nao "sonda · S10 diverge"
eq "$(grep -c '^anon|public|' <(sed -n '/== S5/,/== S6/p' "$R/sonda-base.out" | tr -d ' '))" "7" "sonda · S5 anon com os 7 privilégios em public"
eq "$(sed -n '/== S5/,/== S6/p' "$R/sonda-base.out" | grep -E '^ anon +\| public' | awk -F'|' '{print $4}' | tr -d ' ' | sort -u)" "62" "sonda · S5 anon em 62 relações (produção: 62)"

preflight > "$R/preflight-base.txt" && ok "preflight roda como supabase_read_only_user, sessão read-only" || nao "preflight falhou (ver preflight-base.txt)"
eq "$(grep -c '|t$' "$R/preflight-base.txt")" "0" "preflight · nenhum bloqueio na base"
grep -q '^P0 sessão só leitura (supabase_read_only_user)|on|f$' "$R/preflight-base.txt" && ok "preflight · P0 sessão read-only, sem supabase_admin" || nao "preflight · P0"
grep -q '^P1 auth.uid lê request.jwt.claims|true|f$' "$R/preflight-base.txt" && ok "preflight · P1" || nao "preflight · P1"
grep -q '^P3 gatilho de users = original de 15/10|true|f$' "$R/preflight-base.txt" && ok "preflight · P3 corpo do gatilho = produção (md5)" || nao "preflight · P3"
grep -q '^P6 relações de public com privilégio de anon (15/10: 62)|62|f$' "$R/preflight-base.txt" && ok "preflight · P6 = 62 relações" || nao "preflight · P6"
PA -c "insert into public.users (id, name, email, role) values ('b0000000-0000-4000-8000-0000000000cc','Admin Sem Papel','admin2@example.invalid','ADMIN')" >/dev/null
grep -q '^P4 ADMIN do cadastro sem papel em app_auth|1 de 2|t$' <(preflight) && ok "preflight · P4 BLOQUEIA com ADMIN sem papel em app_auth" || nao "preflight · P4 não bloqueou ADMIN sem papel"
PA -c "delete from public.users where id='b0000000-0000-4000-8000-0000000000cc'" >/dev/null
eq "$(verifica)" "ABERTO" "verificação como anon (postgres, read-only) vê o buraco no estado inseguro"
eq "$(verifica supabase_read_only_user)" "ILEGIVEL" "verificação como supabase_read_only_user não finge FECHADO (não assume anon)"

echo "▶ 1. defeito reproduzido na base"
eq "$(estado anon 'select count(*) from public.users')" "ok:2" "anon · lê public.users"
eq "$(estado anon "select password_hash from public.users where email='admin@example.invalid'")" "ok:HASH-SINTETICO-A" "anon · lê password_hash"
eq "$(estado anon "update public.users set role='ADMIN' where email='operador@example.invalid' returning role")" "ok:ADMIN" "anon · promove operador a ADMIN"
eq "$(estado anon 'select count(*) from public.projects')" "ok:1" "anon · lê projects"
eq "$(alcanca anon)" "62" "anon · SELECT real alcança 62 relações"

echo "▶ 2. aplica o pacote (ordem de produção)"
aplicar supabase_admin v19_00_users_gatilho_papel_real.sql && ok "v19_00 aplicou (supabase_admin)" || { nao "v19_00"; tail -5 "$R/aplicar-v19_00_users_gatilho_papel_real.sql.log"; }
aplicar supabase_admin v8_03_users_rls_policies.sql && ok "v8_03 aplicou (supabase_admin)" || { nao "v8_03"; tail -5 "$R/aplicar-v8_03_users_rls_policies.sql.log"; }
aplicar supabase_admin v19_01_anon_fecha_public.sql && ok "v19_01 aplicou (supabase_admin)" || { nao "v19_01"; tail -5 "$R/aplicar-v19_01_anon_fecha_public.sql.log"; }
aplicar postgres v8_05_users_safe_view.sql && ok "v8_05 aplicou (postgres)" || { nao "v8_05"; tail -5 "$R/aplicar-v8_05_users_safe_view.sql.log"; }
aplicar supabase_admin v19_02_default_acl_public_sem_anon.sql && ok "v19_02 aplicou (supabase_admin)" || { nao "v19_02"; tail -5 "$R/aplicar-v19_02_default_acl_public_sem_anon.sql.log"; }
fp "$R/fp-pacote1.txt"

echo "▶ 3a. anon"
eq "$(alcanca anon)" "0" "anon · SELECT real alcança 0 relações de public"
eq "$(estado anon 'select count(*) from public.users')" "42501" "anon · users negado"
eq "$(estado anon 'select count(*) from public.users_safe')" "42501" "anon · users_safe negado"
eq "$(estado anon "insert into public.users(id,name,email,role) values (gen_random_uuid(),'x','x@example.invalid','ADMIN')")" "42501" "anon · INSERT em users negado"
eq "$(estado anon 'truncate public.sync_logs')" "42501" "anon · TRUNCATE negado"
eq "$(estado anon "insert into public.raw_events default values")" "42501" "anon · INSERT em raw_events negado"
eq "$(estado anon "select * from public.get_dashboard_totals(current_date-30, current_date, null)")" "42501" "anon · RPC invoker sobre tabela fechada negada"
sonda "$R/sonda-pacote"
eq "$(grep -c 'S8|anon|.*|VE_LINHAS' "$R/sonda-pacote.err")" "0" "sonda S8 · anon vê linha em 0 relações"
eq "$(verifica)" "FECHADO" "verificação como anon: FECHADO depois do pacote"
eq "$(grep -c '^anon|public|' <(sed -n '/== S5/,/== S6/p' "$R/sonda-pacote.out" | tr -d ' '))" "0" "sonda S5 · anon sem grant em public"

echo "▶ 3b. authenticated como ADMIN (JWT com sub em app_auth.user_roles)"
eq "$(estado authenticated 'select count(*) from public.users' "$ADMIN")" "ok:2" "admin · vê todos os usuários"
eq "$(estado authenticated 'select count(*) from public.users_safe' "$ADMIN")" "ok:2" "admin · users_safe vê todos"
eq "$(estado authenticated "update public.users set name='Op' where email='operador@example.invalid' returning name" "$ADMIN")" "ok:Op" "admin · edita outro usuário"
eq "$(estado authenticated 'select count(*) from public.projects' "$ADMIN")" "ok:1" "admin · projects (frontend) continua"
eq "$(estado authenticated 'select count(*) from public.campaigns' "$ADMIN")" "ok:1" "admin · campaigns (frontend) continua"
eq "$(estado authenticated "insert into public.operational_cost_categories(name) values ('w4') returning name" "$ADMIN")" "ok:w4" "admin · CRUD de operational_cost_categories continua"
eq "$(estado authenticated "update public.system_settings set value='y' where key='w4_sintetico' returning value" "$ADMIN")" "ok:y" "admin · update de system_settings (câmbio) continua"
eq "$(estado authenticated "select count(*) from public.get_dashboard_totals(current_date-30, current_date, null)" "$ADMIN")" "ok:1" "admin · RPC get_dashboard_totals continua"
eq "$(estado authenticated 'truncate public.sync_logs' "$ADMIN")" "42501" "admin · TRUNCATE negado (ignoraria RLS)"
eq "$(estado authenticated "update public.users set password_hash='x' where email='operador@example.invalid'" "$ADMIN")" "42501" "admin · escrita em password_hash negada ao browser"

echo "▶ 3c. authenticated como OPERADOR"
eq "$(estado authenticated 'select count(*) from public.users' "$OPER")" "ok:1" "operador · vê só a própria linha"
eq "$(estado authenticated "select count(*) from public.users where email='admin@example.invalid'" "$OPER")" "ok:0" "operador · não vê o admin"
eq "$(estado authenticated "update public.users set role='ADMIN' where email='operador@example.invalid'" "$OPER")" "P0001" "operador · autopromoção barrada pelo gatilho (v19_00)"
eq "$(estado authenticated "update public.users set commission_percentage=99 where email='operador@example.invalid'" "$OPER")" "P0001" "operador · não altera a própria comissão"
eq "$(estado authenticated "update public.users set role='VIEWER' where email='operador@example.invalid' returning role" "$ADMIN")" "ok:VIEWER" "admin · altera role de outro (gatilho reconhece ADMIN)"
eq "$(estado service_role "update public.users set role='VIEWER' where email='operador@example.invalid' returning role")" "ok:VIEWER" "service_role · altera role (backend)"
eq "$(estado authenticated "update public.users set needs_password_change=false where email='operador@example.invalid' returning email" "$OPER")" "ok:operador@example.invalid" "operador · ChangePassword (needs_password_change) continua"
eq "$(estado authenticated "delete from public.users where email='admin@example.invalid' returning 1" "$OPER")" "ok:" "operador · DELETE em outro usuário afeta 0 linhas"
eq "$(estado authenticated "select id, name, email, role, created_at, updated_at from public.users" "$OPER")" "ok:b0000000-0000-4000-8000-00000000000b|Operador Sintético|operador@example.invalid|OPERATOR|$(estado postgres "select created_at from public.users where email='operador@example.invalid'" | cut -d: -f2-)|$(estado postgres "select updated_at from public.users where email='operador@example.invalid'" | cut -d: -f2-)" "operador · select de useUserProfile (colunas nominais) devolve o perfil"
eq "$(estado authenticated 'select count(*) from public.user_projects' "$OPER")" "ok:1" "operador · user_projects (escopo) continua"

echo "▶ 3d. backend (service_role: Node/Vercel, FastAPI, volc_ads, n8n) e postgres"
eq "$(estado service_role 'select count(*) from public.users')" "ok:2" "service_role · lê users (BYPASSRLS)"
eq "$(estado service_role "insert into public.users(id,name,email,role) values (gen_random_uuid(),'n','novo@example.invalid','VIEWER') returning role")" "ok:VIEWER" "service_role · api/users/create continua"
eq "$(estado service_role "update public.users set password_hash='h' where email='operador@example.invalid' returning 1")" "ok:1" "service_role · escreve coluna sensível (fluxo de senha do servidor)"
eq "$(estado service_role "select has_table_privilege('service_role','public.joinads_metrics','INSERT,UPDATE,SELECT')")" "ok:t" "service_role · INSERT/UPDATE/SELECT em joinads_metrics mantidos"
eq "$(estado postgres 'select count(*) from public.users')" "ok:2" "postgres · lê users"

echo "▶ 3e. objeto novo nasce fechado (v19_02)"
P -c "create table public.w4_nova(i int); insert into public.w4_nova values (1)" >/dev/null 2>&1
eq "$(estado anon 'select count(*) from public.w4_nova')" "42501" "nova tabela de postgres · anon negado"
eq "$(estado authenticated 'select count(*) from public.w4_nova' "$ADMIN")" "ok:1" "nova tabela de postgres · authenticated lê"
eq "$(estado authenticated 'truncate public.w4_nova' "$ADMIN")" "42501" "nova tabela de postgres · authenticated sem TRUNCATE"
eq "$(estado service_role 'select count(*) from public.w4_nova')" "ok:1" "nova tabela de postgres · service_role lê"
P -c "drop table public.w4_nova" >/dev/null

echo "▶ 4. v8_06 (passo 2: depois do frontend sem select('*') em produção)"
aplicar supabase_admin v8_06_users_sensitive_columns_revoke.sql && ok "v8_06 aplicou" || { nao "v8_06"; tail -5 "$R/aplicar-v8_06_users_sensitive_columns_revoke.sql.log"; }
eq "$(estado authenticated 'select * from public.users' "$OPER")" "42501" "v8_06 · select('*') do browser quebra (por isso o frontend vai antes)"
eq "$(estado authenticated 'select id, name, email, role, created_at, updated_at from public.users' "$OPER")" "$(estado authenticated 'select id, name, email, role, created_at, updated_at from public.users_safe' "$OPER")" "v8_06 · colunas nominais (useUserProfile corrigido) continuam"
eq "$(estado authenticated 'select password_hash from public.users' "$ADMIN")" "42501" "v8_06 · nem admin lê password_hash pelo browser"
eq "$(estado service_role "select count(password_hash) from public.users")" "ok:2" "v8_06 · service_role continua lendo"

echo "▶ 5. rollback completo (v19_99) a partir do pacote + v8_06"
PA -c "REVOKE DELETE ON public.campaigns FROM authenticated" >/dev/null
aplicar supabase_admin v19_99_rollback.sql && nao "rollback passou por cima de ACL alterada depois da aplicação" \
  || { grep -q "ACL mudou depois da v19_01" "$R/aplicar-v19_99_rollback.sql.log" && ok "rollback ABORTA se a ACL mudou depois (campaigns), sem desfazer nada" || nao "rollback falhou por outro motivo"; }
eq "$(estado authenticated 'delete from public.campaigns where false' "$ADMIN")" "42501" "endurecimento posterior preservado após o rollback abortado"
PA -c "GRANT DELETE ON public.campaigns TO authenticated" >/dev/null
ANTES_AUTH=$(PA -c "select relacl::text from pg_class where oid='auth.users'::regclass")
docker exec -i -e PGOPTIONS='-c search_path=auth,public' "$NOME" psql -h localhost -U supabase_admin -d postgres -X -q -v ON_ERROR_STOP=1 \
  < "$W4_MIG/v19_99_rollback.sql" > "$R/aplicar-v19_99_rollback.sql.log" 2>&1 && { ok "v19_99 aplicou (sessão com search_path=auth,public)"; registrar "$W4_MIG/v19_99_rollback.sql" supabase_admin ok; } \
  || { nao "v19_99"; tail -5 "$R/aplicar-v19_99_rollback.sql.log"; }
eq "$(PA -c "select relacl::text from pg_class where oid='auth.users'::regclass")" "$ANTES_AUTH" "rollback não toca auth.users mesmo com auth no search_path (nomes qualificados)"
eq "$(verifica)" "ABERTO" "verificação como anon: ABERTO de novo depois do rollback"
fp "$R/fp-rollback.txt"
diff "$R/fp-base.txt" "$R/fp-rollback.txt" > "$R/diff-base-rollback.txt" && ok "rollback devolve o fingerprint EXATO da base (12/12 categorias)" || nao "rollback deixou resíduo (ver diff-base-rollback.txt)"
eq "$(alcanca anon)" "62" "rollback · anon volta a alcançar 62 relações (estado anterior)"
aplicar supabase_admin v19_99_rollback.sql && ok "rollback idempotente (2ª execução passa)" || nao "rollback idempotente"
fp "$R/fp-rollback2.txt"; diff -q "$R/fp-base.txt" "$R/fp-rollback2.txt" >/dev/null && ok "2ª execução do rollback não muda nada" || nao "2ª execução mudou o schema"

echo "▶ 6. reaplicação"
aplicar supabase_admin v19_00_users_gatilho_papel_real.sql && aplicar supabase_admin v8_03_users_rls_policies.sql \
  && aplicar supabase_admin v19_01_anon_fecha_public.sql \
  && aplicar postgres v8_05_users_safe_view.sql && aplicar supabase_admin v19_02_default_acl_public_sem_anon.sql \
  && ok "pacote reaplicou após rollback" || nao "reaplicação"
fp "$R/fp-pacote2.txt"
diff "$R/fp-pacote1.txt" "$R/fp-pacote2.txt" > "$R/diff-pacote1-pacote2.txt" && ok "fingerprint idêntico entre 1ª e 2ª aplicação" || nao "fingerprint divergiu entre aplicações"
diff -q "$R/fp-base.txt" "$R/fp-pacote1.txt" >/dev/null && nao "pacote não mudou o schema" || ok "pacote muda o schema (só grants, policies, constraints, índices, views, gatilhos de users)"
aplicar supabase_admin v19_01_anon_fecha_public.sql && nao "v19_01 reaplicou por cima" \
  || { grep -q "já aplicada" "$R/aplicar-v19_01_anon_fecha_public.sql.log" && ok "v19_01 por cima recusada pela guarda" || nao "v19_01 por cima falhou por outro motivo"; }
eq "$(alcanca anon)" "0" "estado final · anon alcança 0 relações"

for f in v19_00_users_gatilho_papel_real v8_03_users_rls_policies v19_01_anon_fecha_public v8_05_users_safe_view \
         v19_02_default_acl_public_sem_anon v8_06_users_sensitive_columns_revoke v19_99_rollback; do
  echo "$f.sql $(sha "$W4_MIG/$f.sql")"
done > "$RECIBOS/pacote-sha256.txt"
P -f - < "$FP" > "$RECIBOS/fp-final.out" 2>&1
