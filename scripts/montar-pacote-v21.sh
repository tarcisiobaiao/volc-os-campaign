#!/usr/bin/env bash
# =============================================================================
# montar-pacote-v21.sh — monta o pacote v21 (W3) como UMA transação.
#
#   scripts/montar-pacote-v21.sh            regrava os dois pacotes
#   scripts/montar-pacote-v21.sh --check    sai 1 se algum pacote estiver defasado
#
# Gera (não editar à mão; edite as partes e rode de novo):
#   supabase/migrations/v21_pacote_aplicar.sql
#       BEGIN · pré-checagem · v7_13 · v21_01 · v6_01..v6_05 · v21_02 · pós-checagem · COMMIT
#   supabase/migrations/v21_pacote_reverter.sql
#       BEGIN · v21_02_rollback · v21_01_rollback · pós-checagem · COMMIT
#
# Por que um pacote: aplicadas uma por vez, cada parte confirma sozinha, e entre
# v7_13 e v21_01 (ou entre v6_05 e v21_02) a anon tem SELECT, DELETE e TRUNCATE
# nas tabelas novas pelo default ACL de produção. Numa transação só, nenhuma
# outra sessão enxerga as tabelas antes do COMMIT, e qualquer erro desfaz tudo.
#
# Recusa montar se uma parte tiver controle de transação (BEGIN;/COMMIT;/ROLLBACK;
# em início de linha) ou meta-comando do psql: isso quebraria a transação única.
# =============================================================================
set -euo pipefail
export LC_ALL=C
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

APLICAR_PARTES=(
  src/sql/v7_13_meta_capi_sites.sql
  supabase/migrations/v21_01_meta_capi_sites_privilegios.sql
  src/sql/v6_01_create_campaign_roles.sql
  src/sql/v6_02_create_campaign_members.sql
  src/sql/v6_03_create_campaign_commissions.sql
  src/sql/v6_04_create_daily_campaign_member_payouts.sql
  src/sql/v6_05_helper_functions.sql
  supabase/migrations/v21_02_v6_rbac_privilegios.sql
)
REVERTER_PARTES=(
  supabase/migrations/v21_02_rollback.sql
  supabase/migrations/v21_01_rollback.sql
)
SAIDA_APLICAR=supabase/migrations/v21_pacote_aplicar.sql
SAIDA_REVERTER=supabase/migrations/v21_pacote_reverter.sql

sha() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | awk '{print $1}'; }

conferir_parte() {
  local f="$1"
  [ -f "$f" ] || { echo "ERRO: parte ausente: $f" >&2; exit 1; }
  # END; fica de fora: nas partes ele só aparece como fim de corpo plpgsql.
  if grep -qEi '^[[:space:]]*(begin|commit|rollback|start[[:space:]]+transaction|abort)[[:space:]]*;' "$f"; then
    echo "ERRO: $f tem controle de transação; quebraria a transação única" >&2; exit 1
  fi
  if grep -qE '^[[:space:]]*\\' "$f"; then
    echo "ERRO: $f tem meta-comando do psql" >&2; exit 1
  fi
}

cabecalho() { # $1 título  $2 arquivo gerado  $3.. partes
  local titulo="$1" saida="$2"; shift 2
  cat <<EOF
-- =============================================================================
-- $titulo (PROPOSTA, NÃO APLICADA)
-- GERADO por scripts/montar-pacote-v21.sh. NÃO EDITAR: edite as partes e rode
-- o gerador; \`scripts/montar-pacote-v21.sh --check\` acusa pacote defasado.
--
-- Uma transação só. Aplicar com:
--   psql -X -v ON_ERROR_STOP=1 -f $saida
-- Qualquer erro desfaz o pacote inteiro; nenhuma outra sessão vê estado
-- intermediário. NÃO aplicar as partes uma a uma (ver v21_01/v21_02).
--
-- Partes (sha256 no momento da montagem):
EOF
  local f; for f in "$@"; do printf -- '--   %s  %s\n' "$(sha "$f")" "$f"; done
  cat <<'EOF'
-- =============================================================================
\set ON_ERROR_STOP on
BEGIN;
EOF
}

incluir() { # $1 parte
  printf '\n-- >>>>> início da parte: %s\n' "$1"
  cat "$1"
  printf '\n-- <<<<< fim da parte: %s\n' "$1"
}

montar_aplicar() {
  cabecalho "v21_pacote_aplicar — meta_capi_sites + RBAC v6 com privilégios" "$SAIDA_APLICAR" "${APLICAR_PARTES[@]}"
  cat <<'EOF'

-- Pré-checagem: o pacote CRIA as cinco tabelas. Se alguma já existe, alguém
-- aplicou parte dele fora do pacote: a janela já aconteceu e o caminho certo é
-- auditar e rodar só v21_01/v21_02 sobre o que existe, não reaplicar por cima.
DO $pre$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['meta_capi_sites', 'campaign_roles', 'campaign_members',
                           'campaign_commissions', 'daily_campaign_member_payouts'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      RAISE EXCEPTION 'v21_pacote: public.% já existe — este pacote não reaplica por cima', t;
    END IF;
  END LOOP;
  IF to_regprocedure('public.volc_current_admin()') IS NULL THEN
    RAISE EXCEPTION 'v21_pacote: public.volc_current_admin() ausente (v8_01)';
  END IF;
  IF to_regclass('public.users') IS NULL OR to_regclass('public.campaigns') IS NULL THEN
    RAISE EXCEPTION 'v21_pacote: public.users e public.campaigns são pré-requisito das v6';
  END IF;
END
$pre$;
EOF
  local f; for f in "${APLICAR_PARTES[@]}"; do incluir "$f"; done
  cat <<'EOF'

-- Pós-checagem, ainda dentro da transação: se o estado final não for o
-- prometido, nada é confirmado.
DO $pos$
DECLARE
  t text;
  r record;
BEGIN
  FOREACH t IN ARRAY ARRAY['meta_capi_sites', 'campaign_roles', 'campaign_members',
                           'campaign_commissions', 'daily_campaign_member_payouts'] LOOP
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = ('public.' || t)::regclass) THEN
      RAISE EXCEPTION 'v21_pacote: RLS desligada em public.%', t;
    END IF;
    IF has_table_privilege('anon', 'public.' || t, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') THEN
      RAISE EXCEPTION 'v21_pacote: anon ainda tem privilégio em public.%', t;
    END IF;
    IF has_table_privilege('authenticated', 'public.' || t, 'TRUNCATE,REFERENCES,TRIGGER') THEN
      RAISE EXCEPTION 'v21_pacote: authenticated tem TRUNCATE/REFERENCES/TRIGGER em public.%', t;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class c, aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a
                WHERE c.oid = ('public.' || t)::regclass AND a.grantee = 0) THEN
      RAISE EXCEPTION 'v21_pacote: PUBLIC tem privilégio em public.%', t;
    END IF;
  END LOOP;
  IF has_table_privilege('authenticated', 'public.meta_capi_sites', 'SELECT,INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION 'v21_pacote: authenticated alcança meta_capi_sites';
  END IF;
  IF has_table_privilege('authenticated', 'public.daily_campaign_member_payouts', 'INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated', 'public.campaign_roles', 'INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION 'v21_pacote: authenticated escreve em payouts ou no catálogo de papéis';
  END IF;
  FOR r IN SELECT p.oid::regprocedure AS f FROM pg_proc p
            WHERE p.pronamespace = 'public'::regnamespace AND p.proname LIKE 'v6\_populate\_%' LOOP
    IF has_function_privilege('anon', r.f, 'EXECUTE') OR has_function_privilege('authenticated', r.f, 'EXECUTE') THEN
      RAISE EXCEPTION 'v21_pacote: % executável por anon/authenticated', r.f;
    END IF;
  END LOOP;
END
$pos$;

COMMIT;
EOF
}

montar_reverter() {
  cabecalho "v21_pacote_reverter — desfaz o v21_pacote_aplicar" "$SAIDA_REVERTER" "${REVERTER_PARTES[@]}"
  local f; for f in "${REVERTER_PARTES[@]}"; do incluir "$f"; done
  cat <<'EOF'

-- Pós-checagem: ou some tudo, ou nada é confirmado. Se o v21_01_rollback recusar
-- (site cadastrado), o v21_02_rollback que já rodou acima também é desfeito.
DO $pos$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['meta_capi_sites', 'campaign_roles', 'campaign_members',
                           'campaign_commissions', 'daily_campaign_member_payouts'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      RAISE EXCEPTION 'v21_pacote_reverter: public.% ainda existe', t;
    END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_proc WHERE pronamespace = 'public'::regnamespace AND proname LIKE 'v6\_%') THEN
    RAISE EXCEPTION 'v21_pacote_reverter: funções v6_* ainda existem';
  END IF;
END
$pos$;

COMMIT;
EOF
}

for f in "${APLICAR_PARTES[@]}" "${REVERTER_PARTES[@]}"; do conferir_parte "$f"; done

tmp_a="$(mktemp)"; tmp_r="$(mktemp)"; trap 'rm -f "$tmp_a" "$tmp_r"' EXIT
montar_aplicar > "$tmp_a"
montar_reverter > "$tmp_r"

if [ "${1:-}" = "--check" ]; then
  rc=0
  cmp -s "$tmp_a" "$SAIDA_APLICAR" || { echo "DEFASADO: $SAIDA_APLICAR (rode scripts/montar-pacote-v21.sh)"; rc=1; }
  cmp -s "$tmp_r" "$SAIDA_REVERTER" || { echo "DEFASADO: $SAIDA_REVERTER (rode scripts/montar-pacote-v21.sh)"; rc=1; }
  [ $rc = 0 ] && echo "pacote v21 em dia: aplicar $(sha "$SAIDA_APLICAR") · reverter $(sha "$SAIDA_REVERTER")"
  exit $rc
fi

cp "$tmp_a" "$SAIDA_APLICAR"; cp "$tmp_r" "$SAIDA_REVERTER"
echo "montado: $SAIDA_APLICAR $(sha "$SAIDA_APLICAR")"
echo "montado: $SAIDA_REVERTER $(sha "$SAIDA_REVERTER")"
