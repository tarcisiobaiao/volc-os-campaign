#!/bin/bash
# =============================================================================
# Prova do ciclo de schema do REGISTRO DE MIDIA — PostgreSQL DESCARTAVEL
# =============================================================================
# T08 · pacote docs/specs/meta-operator-go-live-v1/
#
# ⚠️ ESTE SCRIPT NAO TOCA O SUPABASE OFICIAL, e nao tem como tocar: ele cria um
# cluster novo com `initdb` num diretorio temporario, ouvindo so em 127.0.0.1
# numa porta propria. Nenhuma variavel de ambiente do projeto e lida, e a
# string de conexao e montada aqui.
#
# Toda expectativa e uma ASSERCAO. Nada e impresso "para o operador conferir":
# um portao que imprime a propria violacao e devolve zero e legenda, nao portao.
#
# O que ele prova:
#   1. a migration aplica sobre a dependencia real (o helper de papel);
#   2. reservar → concluir grava o recibo ANTES do efeito e fecha com o hash;
#   3. os MESMOS bytes na MESMA conta nao geram segundo despacho (idempotencia);
#   4. os mesmos bytes em OUTRA conta sao outro registro (isolamento);
#   5. a CERCA: token antigo nao conclui, nao marca ambiguo e nao falha;
#   6. AMBIGUO permanece ambiguo — nenhuma reserva o devolve a DESPACHAR;
#   7. FALHOU pode ser retentado, porque a recusa explicita prova que nada nasceu;
#   8. service_role NAO escreve direto na tabela: so a RPC escreve;
#   9. reaplicar e recusado pela guarda;
#  10. o rollback recusa apagar recibo real sem ato deliberado;
#  11. rollback autorizado + reapply funcionam.
#
# Uso:  bash docs/closure/meta-operator-go-live-v1/prova-sql-registro-de-midia.sh
# =============================================================================
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BASE="$(mktemp -d)"
PGPORT_PROVA=54399
export PGHOST="$BASE/sock"
mkdir -p "$PGHOST"

OK=0
FALHAS=0

limpar() {
  pg_ctl -D "$BASE/data" -m immediate stop >/dev/null 2>&1 || true
  rm -rf "$BASE"
}
trap limpar EXIT

afirmar() {
  local descricao="$1" obtido="$2" esperado="$3"
  if [ "$obtido" = "$esperado" ]; then
    OK=$((OK + 1)); echo "  ok   · $descricao"
  else
    FALHAS=$((FALHAS + 1)); echo "  FALHA· $descricao (obtido: '$obtido', esperado: '$esperado')"
  fi
}

q() { psql -X -q -t -A -d prova -v ON_ERROR_STOP=1 -c "$1"; }
# ⚠️ `|| true` e `pipefail` desligado aqui de proposito: metade das provas
# ESPERA que o psql falhe (papel negado, cerca, guarda de reaplicacao). Sem
# isto, `set -euo pipefail` mataria o script exatamente na asserção que ele
# existe para fazer — e a prova terminaria em silencio, com codigo zero.
# ⚠️ `SET ROLE`, e nao `PGUSER=`. Os papeis do Supabase sao NOLOGIN — conectar
# como eles e impossivel, e uma prova que tentasse isso mediria a recusa de
# LOGIN em vez da recusa de GRANT. `SET ROLE` troca o `current_user`, e e sobre
# ele que o Postgres decide privilegio e RLS.
q_como() {
  set +o pipefail
  psql -X -q -t -A -d prova -c "SET ROLE $1; $2" 2>&1 | tr -d '\n' || true
  set -o pipefail
}

# Mesmo motivo, para os dois arquivos que devem ser RECUSADOS.
psql_esperando_falha() {
  set +o pipefail
  psql -X -q -d prova -f "$1" 2>&1 | tr -d '\n' || true
  set -o pipefail
}

echo "▶ cluster descartavel em $BASE"
initdb -D "$BASE/data" -U postgres --auth=trust >/dev/null
pg_ctl -D "$BASE/data" -o "-p $PGPORT_PROVA -k '$PGHOST' -c listen_addresses=''" -l "$BASE/log" start >/dev/null
export PGPORT=$PGPORT_PROVA PGUSER=postgres
createdb prova
q "CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null
for papel in anon authenticated service_role; do
  q "CREATE ROLE $papel NOLOGIN;" >/dev/null
done

echo "▶ 1. dependencia + migration"
# A migration depende de `trafego_meta_exigir_service_role()`, criada na janela
# de criacao. Aqui ela e recriada com o MESMO corpo semantico, para que a prova
# nao precise aplicar a cadeia inteira do read model — e para que a CHECK de
# papel seja exercitada de verdade.
q "
CREATE OR REPLACE FUNCTION public.trafego_meta_exigir_service_role()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS \$\$
BEGIN
  IF current_setting('request.jwt.claim.role', true) IS DISTINCT FROM 'service_role'
     AND current_user NOT IN ('postgres','supabase_admin','service_role') THEN
    RAISE EXCEPTION 'META_LEDGER_ROLE_DENIED';
  END IF;
END;
\$\$;
GRANT EXECUTE ON FUNCTION public.trafego_meta_exigir_service_role() TO service_role;
" >/dev/null

psql -X -q -d prova -v ON_ERROR_STOP=1 \
  -f "$RAIZ/supabase/migrations/20260908020000_meta_asset_registration.sql" >/dev/null
afirmar "tabela existe apos apply" \
  "$(q "SELECT to_regclass('public.trafego_meta_asset_registration') IS NOT NULL;")" "t"
afirmar "RLS ligada e forcada" \
  "$(q "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname='trafego_meta_asset_registration';")" "t"
afirmar "indice de idempotencia existe" \
  "$(q "SELECT count(*) FROM pg_indexes WHERE indexname='trafego_meta_asset_registration_idem_ux';")" "1"

SHA_A="$(printf 'a%.0s' {1..64})"
SHA_B="$(printf 'b%.0s' {1..64})"

echo "▶ 2. reservar → concluir"
RES1="$(q "SELECT public.trafego_meta_reservar_registro_ativo('metaacct_alpha','$SHA_A','operador','master-1');")"
afirmar "primeira reserva despacha" "$(echo "$RES1" | python3 -c 'import json,sys;print(json.load(sys.stdin)["estado"])')" "DESPACHAR"
REF1="$(echo "$RES1" | python3 -c 'import json,sys;print(json.load(sys.stdin)["reserva_ref"])')"
TOK1="$(echo "$RES1" | python3 -c 'import json,sys;print(json.load(sys.stdin)["claim_token"])')"
afirmar "recibo existe ANTES do efeito externo" \
  "$(q "SELECT state FROM public.trafego_meta_asset_registration WHERE registration_id='$REF1';")" "DESPACHAR"
q "SELECT public.trafego_meta_concluir_registro_ativo('$REF1','hashDaPeca_01','$TOK1');" >/dev/null
afirmar "conclusao grava hash" \
  "$(q "SELECT state||'/'||image_hash FROM public.trafego_meta_asset_registration WHERE registration_id='$REF1';")" \
  "REGISTRADO/hashDaPeca_01"

echo "▶ 3. idempotencia por (conta, bytes)"
RES2="$(q "SELECT public.trafego_meta_reservar_registro_ativo('metaacct_alpha','$SHA_A','operador','master-1');")"
afirmar "replay devolve REGISTRADO, nao DESPACHAR" \
  "$(echo "$RES2" | python3 -c 'import json,sys;print(json.load(sys.stdin)["estado"])')" "REGISTRADO"
afirmar "replay devolve o hash que ja existe" \
  "$(echo "$RES2" | python3 -c 'import json,sys;print(json.load(sys.stdin)["image_hash"])')" "hashDaPeca_01"
afirmar "nenhuma linha nova foi criada" \
  "$(q "SELECT count(*) FROM public.trafego_meta_asset_registration;")" "1"

echo "▶ 4. isolamento entre contas"
RES3="$(q "SELECT public.trafego_meta_reservar_registro_ativo('metaacct_beta','$SHA_A','operador','master-1');")"
afirmar "mesmos bytes em OUTRA conta sao outro registro" \
  "$(echo "$RES3" | python3 -c 'import json,sys;print(json.load(sys.stdin)["estado"])')" "DESPACHAR"
afirmar "agora sao duas linhas" \
  "$(q "SELECT count(*) FROM public.trafego_meta_asset_registration;")" "2"
REF3="$(echo "$RES3" | python3 -c 'import json,sys;print(json.load(sys.stdin)["reserva_ref"])')"
TOK3="$(echo "$RES3" | python3 -c 'import json,sys;print(json.load(sys.stdin)["claim_token"])')"

echo "▶ 5. a cerca"
FENCE="$(q_como postgres "SELECT public.trafego_meta_concluir_registro_ativo('$REF3','hashOutro_02','00000000-0000-0000-0000-000000000000');")"
case "$FENCE" in *META_ASSET_CLAIM_FENCED*) afirmar "token errado nao conclui" "cercado" "cercado";;
  *) afirmar "token errado nao conclui" "$FENCE" "cercado";; esac
q "SELECT public.trafego_meta_marcar_registro_ativo_ambiguo('$REF3','$TOK3');" >/dev/null
afirmar "token certo marca ambiguo" \
  "$(q "SELECT state FROM public.trafego_meta_asset_registration WHERE registration_id='$REF3';")" "AMBIGUO"
FENCE2="$(q_como postgres "SELECT public.trafego_meta_concluir_registro_ativo('$REF3','hashTardio_03','$TOK3');")"
case "$FENCE2" in *META_ASSET_CLAIM_FENCED*) afirmar "token ja usado nao conclui depois" "cercado" "cercado";;
  *) afirmar "token ja usado nao conclui depois" "$FENCE2" "cercado";; esac

echo "▶ 6. AMBIGUO nao volta a DESPACHAR"
RES4="$(q "SELECT public.trafego_meta_reservar_registro_ativo('metaacct_beta','$SHA_A','operador','master-1');")"
afirmar "reserva sobre ambiguo continua ambigua" \
  "$(echo "$RES4" | python3 -c 'import json,sys;print(json.load(sys.stdin)["estado"])')" "AMBIGUO"

echo "▶ 7. FALHOU pode ser retentado"
RES5="$(q "SELECT public.trafego_meta_reservar_registro_ativo('metaacct_alpha','$SHA_B','operador','master-2');")"
REF5="$(echo "$RES5" | python3 -c 'import json,sys;print(json.load(sys.stdin)["reserva_ref"])')"
TOK5="$(echo "$RES5" | python3 -c 'import json,sys;print(json.load(sys.stdin)["claim_token"])')"
q "SELECT public.trafego_meta_falhar_registro_ativo('$REF5','META_ASSET_UPLOAD_REJECTED','$TOK5');" >/dev/null
afirmar "falha explicita fecha o recibo" \
  "$(q "SELECT state FROM public.trafego_meta_asset_registration WHERE registration_id='$REF5';")" "FALHOU"
RES6="$(q "SELECT public.trafego_meta_reservar_registro_ativo('metaacct_alpha','$SHA_B','operador','master-2');")"
afirmar "recusa explicita permite nova tentativa" \
  "$(echo "$RES6" | python3 -c 'import json,sys;print(json.load(sys.stdin)["estado"])')" "DESPACHAR"

echo "▶ 8. service_role nao escreve direto"
ESCRITA="$(q_como service_role "INSERT INTO public.trafego_meta_asset_registration (account_ref, content_sha256, actor_id, master_ref, state) VALUES ('metaacct_gamma','$SHA_B','x','y','REGISTRADO');")"
case "$ESCRITA" in *"permission denied"*|*"permissão negada"*) afirmar "INSERT direto negado" "negado" "negado";;
  *) afirmar "INSERT direto negado" "$ESCRITA" "negado";; esac
LEITURA="$(q_como service_role "SELECT count(*) FROM public.trafego_meta_asset_registration;")"
case "$LEITURA" in *"permission denied"*) afirmar "SELECT permitido a service_role" "negado" "permitido";;
  *) afirmar "SELECT permitido a service_role" "permitido" "permitido";; esac

echo "▶ 9. reaplicar e recusado"
REAPLY="$(psql_esperando_falha "$RAIZ/supabase/migrations/20260908020000_meta_asset_registration.sql")"
case "$REAPLY" in *"ja parece aplicado"*) afirmar "guarda recusa reaplicacao" "recusado" "recusado";;
  *) afirmar "guarda recusa reaplicacao" "$REAPLY" "recusado";; esac

echo "▶ 10. rollback recusa apagar recibo real"
ROLL="$(psql_esperando_falha "$RAIZ/supabase/migrations/20260908020100_meta_asset_registration_rollback.sql")"
case "$ROLL" in *"recusado:"*) afirmar "rollback protege recibo existente" "recusado" "recusado";;
  *) afirmar "rollback protege recibo existente" "$ROLL" "recusado";; esac
afirmar "tabela continua de pe apos rollback recusado" \
  "$(q "SELECT to_regclass('public.trafego_meta_asset_registration') IS NOT NULL;")" "t"

echo "▶ 11. rollback autorizado + reapply"
psql -X -q -d prova -v ON_ERROR_STOP=1 \
  -c "SET volc.rollback_destrutivo_autorizado = 'sim';" \
  -f "$RAIZ/supabase/migrations/20260908020100_meta_asset_registration_rollback.sql" >/dev/null
afirmar "tabela some apos rollback autorizado" \
  "$(q "SELECT to_regclass('public.trafego_meta_asset_registration') IS NULL;")" "t"
psql -X -q -d prova -v ON_ERROR_STOP=1 \
  -f "$RAIZ/supabase/migrations/20260908020000_meta_asset_registration.sql" >/dev/null
afirmar "reapply funciona" \
  "$(q "SELECT to_regclass('public.trafego_meta_asset_registration') IS NOT NULL;")" "t"
afirmar "reapply comeca vazio" \
  "$(q "SELECT count(*) FROM public.trafego_meta_asset_registration;")" "0"

echo
echo "════════════════════════════════════════"
echo "  asserções ok: $OK   ·   falhas: $FALHAS"
echo "════════════════════════════════════════"
[ "$FALHAS" -eq 0 ] || exit 1
