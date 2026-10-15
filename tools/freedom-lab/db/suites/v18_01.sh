# db/suites/v18_01.sh — suíte da migration candidata v18_01 (identidade de leitura
# mínima). Carregada por `lab.sh testar` (padrão quando MIGRATION_SUITE não é dado).
# Usa os helpers do lab.sh: ok, nao, eq, estado, login, P, PA, migrar, registrar,
# e as variáveis MIGRATION, ROLLBACK, FP, SONDA, RECIBOS. Deve deixar o fingerprint
# final em "$RECIBOS/fp-final.out".
login() { login_como volc_leitura_agente "$1"; }
  local L=volc_leitura_agente
  echo "▶ fingerprint do estado imediatamente anterior"; P -f - < "$FP" > "$RECIBOS/fp0.out" 2>&1
  echo "▶ migrar a candidata"
  migrar "imagem+semente" && ok "candidata aplicou sobre imagem 15.8 + semente" || nao "candidata aplicou"
  grep -q "ausente — pulada" "$RECIBOS/migrar.out" && nao "item da allowlist ausente na semente (prova incompleta)" || ok "todos os itens da allowlist existem na semente e foram concedidos"
  eq "$(estado authenticated 'select 1')" "ok:1" "harness · controle positivo: postgres assume authenticated"
  eq "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$NOME")" "none" "isolamento · container sem rede"
  eq "$(estado volc_leitura_agente 'select 1')" "42501" "harness · SET ROLE pelo postgres é NEGADO na imagem (por isso a leitura entra por login)"
  eq "$(login 'select current_user')" "ok:volc_leitura_agente" "harness · login real da identidade de leitura funciona"
  echo "▶ matriz de acesso"
  eq "$(login 'select count(*) from public.google_ads_campanha_dia')" "ok:1" "leitura · fato de mídia: SELECT permitido"
  eq "$(login 'select count(*) from public.trafego_coleta_execucao')" "ok:1" "leitura · RLS forçada: vê pela policy volc_leitura_le"
  eq "$(login 'select sum(n) from public.trafego_coleta_execucao_saude')" "ok:1" "leitura · view security_invoker: vê"
  eq "$(login 'select count(*) from public.users')" "42501" "leitura · users: SELECT negado"
  eq "$(login 'select count(*) from public.meta_business_credentials')" "42501" "leitura · credenciais: SELECT negado"
  eq "$(login "set default_transaction_read_only=off; insert into public.google_ads_campanha_dia values ('a','a',current_date,0)")" "42501" "leitura · INSERT negado"
  eq "$(login 'set default_transaction_read_only=off; create table public.intrusa(i int)')" "42501" "leitura · CREATE em public negado"
  eq "$(estado anon 'select count(*) from public.trafego_coleta_execucao')" "42501" "anon · tabela fechada: negado"
  eq "$(estado anon 'select count(*) from public.users')" "ok:1" "anon · users aberta pelo default ACL da imagem (defeito reproduzido)"
  eq "$(estado authenticated 'select count(*) from public.trafego_coleta_execucao')" "42501" "authenticated · tabela fechada: negado"
  eq "$(estado service_role 'select count(*) from public.trafego_coleta_execucao')" "ok:1" "service_role · BYPASSRLS atravessa RLS"
  eq "$(P -c "select rolbypassrls from pg_roles where rolname='$L'")" "f" "leitura · sem BYPASSRLS"
  eq "$(P -c "select rolbypassrls from pg_roles where rolname='supabase_read_only_user'")" "t" "imagem · supabase_read_only_user TEM BYPASSRLS (inadequado como leitor)"
  eq "$(P -c "select setconfig::text like '%default_transaction_read_only=on%' from pg_db_role_setting where setrole='$L'::regrole")" "t" "leitura · default_transaction_read_only=on"
  eq "$(login 'show transaction_read_only')" "ok:on" "leitura · sessão de login nasce read-only"
  eq "$(login "insert into public.google_ads_campanha_dia values ('a','a',current_date,0)")" "25006" "leitura · INSERT com sessão read-only falha 25006 antes do GRANT"
  case "$(login 'set default_transaction_read_only=off; select public.fn_definer_grava()')" in
    ok:*) ok "LIMITE DECLARADO · SECURITY DEFINER por PUBLIC ainda executa (fecha na v18_02)";;
    *) nao "esperava o buraco declarado aberto";; esac
  eq "$(login 'select public.fn_definer_grava()')" "25006" "defesa em profundidade · sessão read-only barra o definer (25006)"
  echo "▶ sonda e fingerprint (mesmos arquivos que rodariam em produção)"
  P -f - < "$SONDA" > "$RECIBOS/sonda.out" 2>&1 && ok "sonda_acesso.sql executou" || nao "sonda"
  grep -q "S8|anon|users|VE_LINHAS" "$RECIBOS/sonda.out" && ok "sonda S8 vê users exposta a anon" || nao "sonda S8"
  P -f - < "$FP" > "$RECIBOS/fp1.out" 2>&1 && ok "fingerprint executou" || nao "fingerprint"
  echo "▶ reaplicação por cima"
  P -f - < "$MIGRATION" > "$RECIBOS/reaplicar.out" 2>&1 && nao "reaplicação por cima passou" || \
    { grep -q "já existe — esta migration não reaplica" "$RECIBOS/reaplicar.out" && ok "reaplicação por cima recusada pela guarda (mensagem da guarda)" || nao "reaplicação falhou por outro motivo"; }
  echo "▶ rollback recusa membro alheio e preserva policy alheia"
  P -c "CREATE ROLE lab_alheio NOLOGIN; GRANT volc_leitura TO lab_alheio" >/dev/null
  P -f - < "$ROLLBACK" > "$RECIBOS/rollback-alheio.out" 2>&1 && nao "rollback derrubou membership alheia" || \
    { grep -q "membros além" "$RECIBOS/rollback-alheio.out" && ok "rollback recusa quando volc_leitura tem membro alheio" || nao "rollback falhou por outro motivo"; }
  P -c "REVOKE volc_leitura FROM lab_alheio; DROP ROLE lab_alheio" >/dev/null
  P -c "CREATE POLICY volc_leitura_le ON public.users FOR SELECT TO authenticated USING (true)" >/dev/null
  echo "▶ rollback"
  P -f - < "$ROLLBACK" > "$RECIBOS/rollback.out" 2>&1 && { ok "rollback aplicou"; registrar "$ROLLBACK" "pos-candidata" ok; } || nao "rollback"
  eq "$(P -c "select count(*) from pg_roles where rolname like 'volc_leitura%'")" "0" "papéis removidos"
  eq "$(P -c "select count(*) from pg_policy where polname='volc_leitura_le' and polrelid <> 'public.users'::regclass")" "0" "policies da v18_01 removidas"
  eq "$(P -c "select count(*) from pg_policy where polname='volc_leitura_le' and polrelid = 'public.users'::regclass")" "1" "policy homônima alheia (authenticated em users) preservada"
  P -c "DROP POLICY volc_leitura_le ON public.users" >/dev/null
  P -f - < "$FP" > "$RECIBOS/fp-pos-rollback.out" 2>&1 || nao "fingerprint pós-rollback falhou"
  diff -q "$RECIBOS/fp0.out" "$RECIBOS/fp-pos-rollback.out" >/dev/null && ok "rollback devolve o fingerprint exato do estado anterior" || nao "rollback deixou resíduo no schema"
  P -f - < "$ROLLBACK" >/dev/null 2>&1 && ok "rollback idempotente" || nao "rollback idempotente"
  echo "▶ reaplicar a partir do estado anterior"
  migrar "pos-rollback" >/dev/null && ok "candidata reaplicou após rollback" || nao "reaplicação"
  P -f - < "$FP" > "$RECIBOS/fp-final.out" 2>&1 || nao "fingerprint pós-reaplicação falhou"
  diff -q "$RECIBOS/fp1.out" "$RECIBOS/fp-final.out" >/dev/null && ok "fingerprint idêntico entre 1ª e 2ª aplicação" || nao "fingerprint divergiu"
  diff -q "$RECIBOS/fp0.out" "$RECIBOS/fp-final.out" >/dev/null && nao "fingerprint não mudou com a migration" || ok "fingerprint muda com a migration"
  echo "▶ postflight barra leitura fora da allowlist (GRANT a PUBLIC plantado)"
  P -f - < "$ROLLBACK" >/dev/null 2>&1
  P -c "GRANT SELECT ON public.users TO PUBLIC" >/dev/null
  P -f - < "$MIGRATION" > "$RECIBOS/postflight-public.out" 2>&1 && nao "migration aceitou users legível por PUBLIC" || \
    { grep -q "legíveis fora da allowlist" "$RECIBOS/postflight-public.out" && ok "migration aborta quando a leitura alcançaria users via PUBLIC" || nao "migration falhou por outro motivo"; }
  eq "$(P -c "select count(*) from pg_roles where rolname like 'volc_leitura%'")" "0" "aborto do postflight não deixa papel para trás"
  P -c "REVOKE SELECT ON public.users FROM PUBLIC" >/dev/null
  login() { login_como volc_leitura_agente "$1"; }
  _login_antigo() { :; }  # não vaza para outras suítes
