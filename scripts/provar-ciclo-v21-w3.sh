#!/usr/bin/env bash
# =============================================================================
# provar-ciclo-v21-w3.sh — aplica -> prova -> reverte -> reaplica o pacote
# v7_13 + v21_01 (meta_capi_sites) e v6_01..v6_05 + v21_02 (RBAC v6) num
# laboratório DESCARTÁVEL. NUNCA toca em produção.
#
# Pré-requisito: um Postgres 15 descartável com o schema de produção
# (pg_dump --schema-only -n public -n app_auth, papéis Supabase e o default ACL
# aberto reproduzidos) e um PostgREST apontando para ele. O roteiro que monta os
# dois está em handoffs/freedom-lab-20261015/W3-migrations.md.
#
#   PG_CONTAINER=volc-lab-w3-pg REST_URL=http://127.0.0.1:55494 \
#   JWT_SECRET=... ./scripts/provar-ciclo-v21-w3.sh
# =============================================================================
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_CONTAINER="${PG_CONTAINER:?defina PG_CONTAINER}"
REST_URL="${REST_URL:?defina REST_URL}"
JWT_SECRET="${JWT_SECRET:?defina JWT_SECRET}"

case "$PG_CONTAINER" in volc-lab-*) ;; *) echo "recuso: container fora do prefixo volc-lab-" >&2; exit 2;; esac
case "$REST_URL" in http://127.0.0.1:*|http://localhost:*) ;; *) echo "recuso: REST_URL não é local" >&2; exit 2;; esac

psql_lab() { docker exec -i "$PG_CONTAINER" psql -U postgres -X -q -1 -v ON_ERROR_STOP=1 "$@"; }
aplicar() { echo "  aplica $(basename "$1")"; psql_lab < "$1" >/dev/null; }

jwt() { # $1 role  $2 sub (opcional)
  node -e '
    const c=require("crypto");const [role,sub,seg]=process.argv.slice(1);
    const b=o=>Buffer.from(JSON.stringify(o)).toString("base64url");
    const p={role,exp:Math.floor(Date.now()/1e3)+600};if(sub)p.sub=sub;
    const h=b({alg:"HS256",typ:"JWT"})+"."+b(p);
    process.stdout.write(h+"."+c.createHmac("sha256",seg).update(h).digest("base64url"));
  ' "$1" "${2:-}" "$JWT_SECRET"
}

FALHAS=0
confere() { # $1 rótulo  $2 esperado  $3 obtido
  if [[ "$2" == "$3" ]]; then echo "  ✓ $1 ($3)"; else echo "  ✗ $1: esperado $2, obtido $3"; FALHAS=$((FALHAS+1)); fi
}
http() { # $1 método $2 caminho $3 token(opcional) $4 corpo(opcional)
  local args=(-s -o /dev/null -w '%{http_code}' -X "$1" "${REST_URL}$2")
  [[ -n "${3:-}" ]] && args+=(-H "Authorization: Bearer $3")
  [[ -n "${4:-}" ]] && args+=(-H 'Content-Type: application/json' -d "$4")
  curl "${args[@]}"
}
recarrega() { psql_lab -c "NOTIFY pgrst, 'reload schema'" >/dev/null; sleep 2; }

ADMIN=11111111-1111-1111-1111-111111111111
COMUM=22222222-2222-2222-2222-222222222222
T_ANON=""; T_SVC=$(jwt service_role); T_ADMIN=$(jwt authenticated $ADMIN); T_COMUM=$(jwt authenticated $COMUM)

echo "▶ 0. semente de identidade (admin e usuário comum)"
psql_lab >/dev/null <<SQL
SET session_replication_role = replica;
INSERT INTO auth.users (id, email) VALUES ('$ADMIN','admin@lab.test'), ('$COMUM','comum@lab.test') ON CONFLICT DO NOTHING;
INSERT INTO public.users (id, email, name, role) VALUES ('$ADMIN','admin@lab.test','Admin','ADMIN'), ('$COMUM','comum@lab.test','Comum','OPERATOR') ON CONFLICT DO NOTHING;
INSERT INTO app_auth.user_roles (auth_user_id, role) SELECT '$ADMIN','ADMIN' WHERE NOT EXISTS (SELECT 1 FROM app_auth.user_roles WHERE auth_user_id='$ADMIN');
SQL

echo "▶ 1. antes: o defeito reproduzido"
recarrega
confere "GET campaign_members sem a tabela" 404 "$(http GET /campaign_members "$T_ADMIN")"
confere "GET meta_capi_sites sem a tabela" 404 "$(http GET /meta_capi_sites "$T_SVC")"

ciclo() {
  echo "▶ $1. aplica o pacote"
  aplicar "$RAIZ/src/sql/v7_13_meta_capi_sites.sql"
  aplicar "$RAIZ/supabase/migrations/v21_01_meta_capi_sites_privilegios.sql"
  for f in v6_01_create_campaign_roles v6_02_create_campaign_members v6_03_create_campaign_commissions \
           v6_04_create_daily_campaign_member_payouts v6_05_helper_functions; do
    aplicar "$RAIZ/src/sql/$f.sql"
  done
  aplicar "$RAIZ/supabase/migrations/v21_02_v6_rbac_privilegios.sql"
  recarrega

  echo "▶ $1. prova meta_capi_sites"
  confere "service_role lê" 200 "$(http GET /meta_capi_sites "$T_SVC")"
  confere "anon é negado" 401 "$(http GET /meta_capi_sites "$T_ANON")"
  confere "authenticated é negado" 403 "$(http GET /meta_capi_sites "$T_ADMIN")"
  confere "anon sem TRUNCATE" f "$(docker exec "$PG_CONTAINER" psql -U postgres -Atc "select has_table_privilege('anon','public.meta_capi_sites','TRUNCATE')")"

  echo "▶ $1. prova RBAC v6 (as três tabelas que davam 404 em /settings/users)"
  for t in campaign_roles campaign_members campaign_commissions; do
    confere "admin lê $t" 200 "$(http GET "/$t" "$T_ADMIN")"
    confere "anon não lê $t" 401 "$(http GET "/$t" "$T_ANON")"
  done
  local camp; camp=$(docker exec "$PG_CONTAINER" psql -U postgres -Atc "select campaign_id from public.campaigns order by campaign_id limit 1")
  local corpo="{\"user_id\":\"$COMUM\",\"campaign_id\":\"$camp\",\"role_id\":2}"
  confere "usuário comum NÃO cria vínculo" 403 "$(http POST /campaign_members "$T_COMUM" "$corpo")"
  confere "admin cria vínculo" 201 "$(http POST /campaign_members "$T_ADMIN" "$corpo")"
  confere "usuário comum vê só o próprio vínculo" 1 \
    "$(curl -s "${REST_URL}/campaign_members?select=id" -H "Authorization: Bearer $T_COMUM" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>console.log(JSON.parse(s).length))')"
  confere "usuário comum não roda v6_populate_*" 403 "$(http POST /rpc/v6_populate_member_payouts_for_date "$T_COMUM" '{"p_date":"2026-10-14"}')"

  echo "▶ $1. rollback recusa com dado de negócio"
  if psql_lab < "$RAIZ/supabase/migrations/v21_02_rollback.sql" >/dev/null 2>&1; then
    confere "rollback v21_02 com vínculo" recusa aceitou
  else
    confere "rollback v21_02 com vínculo" recusa recusa
  fi
  psql_lab -c "DELETE FROM public.campaign_members" >/dev/null

  echo "▶ $1. rollback"
  aplicar "$RAIZ/supabase/migrations/v21_02_rollback.sql"
  aplicar "$RAIZ/supabase/migrations/v21_01_rollback.sql"
  recarrega
  confere "campaign_members sumiu" 404 "$(http GET /campaign_members "$T_ADMIN")"
  confere "meta_capi_sites sumiu" 404 "$(http GET /meta_capi_sites "$T_SVC")"
  confere "funções v6 sumiram" 0 "$(docker exec "$PG_CONTAINER" psql -U postgres -Atc "select count(*) from pg_proc where proname like 'v6\_%'")"
  confere "set_pautador_updated_at preservada" 1 "$(docker exec "$PG_CONTAINER" psql -U postgres -Atc "select count(*) from pg_proc where proname='set_pautador_updated_at'")"
}

ciclo 2
ciclo 3   # reaplicar depois do rollback tem de dar o mesmo resultado

echo
if [[ $FALHAS -eq 0 ]]; then echo "RESULTADO: todas as provas passaram"; else echo "RESULTADO: $FALHAS falha(s)"; exit 1; fi
