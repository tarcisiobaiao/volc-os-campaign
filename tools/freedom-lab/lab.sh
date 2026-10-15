#!/usr/bin/env bash
# =============================================================================
# tools/freedom-lab/lab.sh — banco descartável do Freedom Lab.
#
#   criar     sobe supabase/postgres:15.8.1.085 (mesma imagem usada para espelhar
#             produção em 08/10) num container nomeado, SEM porta publicada e com
#             --network none: só se fala com ele por `docker exec`, e ele não
#             alcança a internet (pg_net, http e dblink da imagem ficam sem rota).
#   semear    aplica db/semente_sintetica.sql depois de um gate anti-PII/segredo
#   migrar    aplica a candidata (MIGRATION=...) e registra sha256 no ledger do lab
#   testar    matriz de acesso, sonda, fingerprint, guarda de reaplicação,
#             rollback idempotente e reaplicação a partir do estado anterior
#   destruir  remove só o container com o rótulo volc.freedom-lab=1
#   recriar   destruir → criar → semear → testar (que migra, desfaz e refaz)
#   status    mostra se o container existe
#
# Nunca toca em produção: não lê .env, não usa SSH, não publica porta.
# Recibo do `testar` vai para $RECIBOS (padrão: tools/freedom-lab/runs/<data>/).
# =============================================================================
set -uo pipefail
export LC_ALL=C LANG=C

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$AQUI/../.." && pwd)"
IMAGEM="${LAB_IMAGEM:-supabase/postgres:15.8.1.085}"
NOME="${LAB_NOME:-volc-freedom-lab-db}"
MIGRATION="${MIGRATION:-$RAIZ/supabase/migrations/v18_01_identidade_leitura_minima.PROPOSTA.sql}"
ROLLBACK="${ROLLBACK:-$RAIZ/supabase/migrations/v18_01_identidade_leitura_minima_rollback.PROPOSTA.sql}"
SEMENTE="$AQUI/db/semente_sintetica.sql"
SONDA="$AQUI/db/sonda_acesso.sql"
FP="$AQUI/db/fingerprint_schema.sql"
RECIBOS="${RECIBOS:-$AQUI/runs/$(date +%Y%m%d-%H%M%S)}"

P() { docker exec -i "$NOME" psql -U postgres -d postgres -X -q -A -t -v ON_ERROR_STOP=1 "$@"; }
sha() { shasum -a 256 "$1" | awk '{print $1}'; }

existe() { [ -n "$(docker ps -aq --filter "name=^${NOME}$" --filter label=volc.freedom-lab=1)" ]; }

criar() {
  if existe; then echo "container $NOME já existe (use recriar)"; return 1; fi
  if [ -n "$(docker ps -aq --filter "name=^${NOME}$")" ]; then
    echo "ERRO: existe um $NOME sem o rótulo do lab — não é meu, não toco"; return 1; fi
  # Senha só para o processo de init da imagem; não há porta publicada, então
  # ela não dá acesso a nada fora do container. Gerada e descartada.
  local senha; senha="$(openssl rand -hex 24)"
  docker run -d --name "$NOME" --label volc.freedom-lab=1 --network none \
    -e POSTGRES_PASSWORD="$senha" "$IMAGEM" >/dev/null || return 1
  unset senha
  local i; for i in $(seq 1 90); do
    docker exec "$NOME" pg_isready -U postgres -h localhost >/dev/null 2>&1 && \
      P -c "select 1" >/dev/null 2>&1 && { echo "▶ criado $NOME ($IMAGEM) sem porta publicada"; P -c "select version()"; return 0; }
    sleep 1
  done
  echo "ERRO: banco não ficou pronto"; docker logs --tail 20 "$NOME"; return 1
}

destruir() {
  if existe; then docker rm -f "$NOME" >/dev/null && echo "▶ destruído $NOME"; else echo "nada a destruir"; fi
}

semear() {
  if grep -nEi '@agenciavolc|eyJ[A-Za-z0-9_-]{10,}\.|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}|[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2}|@(gmail|hotmail|outlook)\.' "$SEMENTE"; then
    echo "ERRO: semente contém material proibido; nada aplicado"; return 1; fi
  P -f - < "$SEMENTE" >/dev/null && echo "▶ semente sintética aplicada (sha256 $(sha "$SEMENTE"))"
}

registrar() { P -c "insert into volc_lab.migracao_aplicada(arquivo, sha256, base, resultado) values ('$(basename "$1")','$(sha "$1")','$2','$3')" >/dev/null; }

migrar() {
  local base="${1:-imagem+semente}"
  if P -f - < "$MIGRATION" > "$RECIBOS/migrar.out" 2>&1; then registrar "$MIGRATION" "$base" ok; echo "▶ migrou $(basename "$MIGRATION")"; return 0
  else registrar "$MIGRATION" "$base" falhou; tail -5 "$RECIBOS/migrar.out"; return 1; fi
}

testar() {
  mkdir -p "$RECIBOS"
  local F=0 T=0
  ok()  { T=$((T+1)); printf '  ✓ %s\n' "$1" | tee -a "$RECIBOS/provas.txt"; }
  nao() { T=$((T+1)); F=$((F+1)); printf '  ✗ %s\n' "$1" | tee -a "$RECIBOS/provas.txt"; }
  eq()  { [ "$1" = "$2" ] && ok "$3" || nao "$3 (esperado=$2 obtido=$1)"; }
  estado() {
    local out st
    out=$(printf '\\set VERBOSITY verbose\nBEGIN; SET LOCAL ROLE %s; %s; ROLLBACK;\n' "$1" "$2" \
          | docker exec -i "$NOME" psql -U postgres -X -A -t 2>&1)
    st=$(printf '%s' "$out" | grep -oE 'ERROR:  [0-9A-Z]{5}' | head -1 | awk '{print $2}')
    [ -n "$st" ] && echo "$st" || echo "ok:$(printf '%s' "$out" | grep -vE '^(BEGIN|ROLLBACK|SET)$' | head -1)"
  }
  # A identidade de leitura entra pelo LOGIN real (com o default_transaction_read_only
  # do papel), não por SET ROLE: na imagem Supabase o `postgres` não é superusuário
  # nem membro do papel novo, e um SET ROLE negado devolveria 42501 em toda prova
  # negativa — passaria pelo motivo errado. O pg_hba da imagem confia em 127.0.0.1,
  # então isto prova a IDENTIDADE e as configurações do papel, não a senha.
  login() {
    local out st
    out=$(printf '\\set VERBOSITY verbose\n%s;\n' "$1" \
          | docker exec -i "$NOME" psql -h localhost -U volc_leitura_agente -d postgres -X -A -t 2>&1)
    st=$(printf '%s' "$out" | grep -oE 'ERROR:  [0-9A-Z]{5}' | head -1 | awk '{print $2}')
    if printf '%s' "$out" | grep -q 'psql: error\|authentication failed\|could not connect'; then echo "ERRO_HARNESS_LOGIN"; return; fi
    [ -n "$st" ] && echo "$st" || echo "ok:$(printf '%s' "$out" | grep -vE '^(SET|BEGIN|COMMIT|ROLLBACK)$' | head -1)"
  }
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
  P -f - < "$FP" > "$RECIBOS/fp2.out" 2>&1 || nao "fingerprint pós-reaplicação falhou"
  diff -q "$RECIBOS/fp1.out" "$RECIBOS/fp2.out" >/dev/null && ok "fingerprint idêntico entre 1ª e 2ª aplicação" || nao "fingerprint divergiu"
  diff -q "$RECIBOS/fp0.out" "$RECIBOS/fp2.out" >/dev/null && nao "fingerprint não mudou com a migration" || ok "fingerprint muda com a migration"
  echo "▶ postflight barra leitura fora da allowlist (GRANT a PUBLIC plantado)"
  P -f - < "$ROLLBACK" >/dev/null 2>&1
  P -c "GRANT SELECT ON public.users TO PUBLIC" >/dev/null
  P -f - < "$MIGRATION" > "$RECIBOS/postflight-public.out" 2>&1 && nao "migration aceitou users legível por PUBLIC" || \
    { grep -q "legíveis fora da allowlist" "$RECIBOS/postflight-public.out" && ok "migration aborta quando a leitura alcançaria users via PUBLIC" || nao "migration falhou por outro motivo"; }
  eq "$(P -c "select count(*) from pg_roles where rolname like 'volc_leitura%'")" "0" "aborto do postflight não deixa papel para trás"
  P -c "REVOKE SELECT ON public.users FROM PUBLIC" >/dev/null
  P -c "select arquivo, sha256, base, resultado from volc_lab.migracao_aplicada order by aplicada_em" > "$RECIBOS/ledger-lab.txt"
  {
    echo "{"
    echo "  \"imagem\": \"$IMAGEM\", \"versao\": \"$(P -c 'show server_version')\","
    echo "  \"migration\": \"$(basename "$MIGRATION")\", \"migration_sha256\": \"$(sha "$MIGRATION")\","
    echo "  \"rollback\": \"$(basename "$ROLLBACK")\", \"rollback_sha256\": \"$(sha "$ROLLBACK")\","
    echo "  \"semente_sha256\": \"$(sha "$SEMENTE")\","
    echo "  \"fingerprint_total_pos\": \"$(grep _TOTAL "$RECIBOS/fp2.out" | tr -d ' ')\","
    echo "  \"verificacoes\": $T, \"falhas\": $F, \"producao_acessada\": false, \"producao_acessada_motivo\": \"estrutural: este script não lê .env, não usa SSH e o container não tem rede\""
    echo "}"
  } > "$RECIBOS/recibo.json"
  echo; echo "recibo: $RECIBOS/recibo.json"
  [ $F = 0 ] && { echo "CICLO VERDE ($T/$T)"; return 0; } || { echo "$F FALHA(S) de $T"; return 1; }
}

case "${1:-}" in
  criar) criar ;;
  destruir) destruir ;;
  semear) semear ;;
  migrar) mkdir -p "$RECIBOS"; migrar "${2:-manual}" ;;
  testar) testar ;;
  recriar) destruir; criar && semear && testar; c=$?; [ "${MANTER:-0}" = 1 ] || destruir; exit $c ;;
  status) existe && docker ps -a --filter "name=^${NOME}$" --format '{{.Names}} {{.Status}} {{.Image}}' || echo "ausente" ;;
  *) sed -n 2,20p "$0"; exit 2 ;;
esac
