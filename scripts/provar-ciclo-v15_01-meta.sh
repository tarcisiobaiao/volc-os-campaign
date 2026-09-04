#!/usr/bin/env bash
# Prova local e descartavel do read model Meta. Nunca usa Supabase ou Meta.
set -euo pipefail
export LC_ALL=C LANG=C

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COFRE="${RAIZ}/supabase/migrations/v13_01_cofre_de_ativos.sql"
MIGRATION="${RAIZ}/supabase/migrations/v15_01_meta_ads_read_model.sql"
ROLLBACK="${RAIZ}/supabase/migrations/v15_99_meta_ads_read_model_rollback.sql"
IMAGEM="postgres:15"
BASE="$(mktemp -d "${TMPDIR:-/tmp}/volc-meta-v15.XXXXXX")"
CID=""; PGDATA=""; SOCK=""; LOCAL=0

[[ "${1:-}" == "--local" ]] && LOCAL=1
[[ $# -le 1 ]] || { echo "uso: $0 [--local]" >&2; exit 2; }
for arquivo in "$COFRE" "$MIGRATION" "$ROLLBACK"; do
  [[ -f "$arquivo" ]] || { echo "arquivo ausente: $arquivo" >&2; exit 1; }
done

limpar() {
  codigo=$?
  if [[ -n "$CID" ]]; then docker rm -f "$CID" >/dev/null 2>&1 || true; fi
  if [[ -n "$PGDATA" && -d "$PGDATA" ]]; then
    pg_ctl -D "$PGDATA" -m immediate stop >/dev/null 2>&1 || true
  fi
  rm -R "$BASE"
  exit "$codigo"
}
trap limpar EXIT

if [[ $LOCAL -eq 0 ]] && command -v docker >/dev/null 2>&1 \
   && docker image inspect "$IMAGEM" >/dev/null 2>&1; then
  echo "▶ PostgreSQL 15 descartavel em Docker (pull proibido)"
  CID="$(docker run --pull=never -d --rm \
    -e POSTGRES_PASSWORD=prova -e POSTGRES_HOST_AUTH_METHOD=trust \
    "$IMAGEM" -c fsync=off)"
  for _ in $(seq 1 120); do
    if docker exec "$CID" psql -U postgres -X -q -t -A -c 'select 1' >/dev/null 2>&1; then
      break
    fi
    sleep 0.25
  done
  docker exec "$CID" psql -U postgres -X -q -t -A -c 'select 1' >/dev/null
  executar() { docker exec -i "$CID" psql -U postgres -X -q -v ON_ERROR_STOP=1 "$@"; }
  aplicar() { docker exec -i "$CID" psql -U postgres -X -q -v ON_ERROR_STOP=1 < "$1"; }
else
  for binario in initdb pg_ctl psql; do
    command -v "$binario" >/dev/null 2>&1 || {
      echo "postgres:15 nao esta local no Docker e falta $binario; nada foi baixado" >&2
      exit 1
    }
  done
  echo "▶ PostgreSQL local descartavel"
  PGDATA="${BASE}/pgdata"; SOCK="${BASE}/sock"
  mkdir -p "$SOCK"
  initdb -D "$PGDATA" -A trust -U postgres >/dev/null
  pg_ctl -D "$PGDATA" -o "-k $SOCK -h '' -F" -w start >/dev/null
  executar() { psql -h "$SOCK" -U postgres -d postgres -X -q -v ON_ERROR_STOP=1 "$@"; }
  aplicar() { psql -h "$SOCK" -U postgres -d postgres -X -q -v ON_ERROR_STOP=1 < "$1"; }
fi

executar <<'SQL'
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN BYPASSRLS;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon, authenticated, service_role;
SQL

aplicar "$COFRE"
aplicar "$MIGRATION"

executar <<'SQL'
DO $prova$
DECLARE n integer; falhou boolean;
BEGIN
  SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace s ON s.oid=c.relnamespace
   WHERE s.nspname='public' AND c.relname LIKE 'trafego_meta_%' AND c.relkind='r';
  IF n <> 9 THEN RAISE EXCEPTION 'esperava 9 tabelas Meta; encontrou %', n; END IF;

  SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace s ON s.oid=c.relnamespace
   WHERE s.nspname='public' AND c.relname LIKE 'trafego_meta_%' AND c.relkind='r'
     AND c.relrowsecurity AND c.relforcerowsecurity;
  IF n <> 9 THEN RAISE EXCEPTION 'RLS/FORCE ausente em tabela Meta'; END IF;

  SELECT count(*) INTO n FROM information_schema.columns
   WHERE table_schema='public' AND table_name LIKE 'trafego_meta_%'
     AND regexp_replace(lower(column_name), '[^a-z0-9]', '', 'g') IN
       ('token','accesstoken','clientsecret','localizador','rawresponse');
  IF n <> 0 THEN RAISE EXCEPTION 'coluna sensivel apareceu no read model'; END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.role_table_grants
     WHERE table_schema='public' AND table_name LIKE 'trafego_meta_%'
       AND grantee IN ('anon','authenticated')
  ) THEN RAISE EXCEPTION 'papel de browser recebeu grant Meta'; END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.role_table_grants
     WHERE table_schema='public' AND table_name LIKE 'trafego_meta_%'
       AND grantee='service_role' AND privilege_type NOT IN ('SELECT','INSERT','UPDATE')
  ) THEN RAISE EXCEPTION 'service_role recebeu privilegio alem do read-sync'; END IF;
END
$prova$;

INSERT INTO public.cofre_ativo
  (ativo_id,kind,cluster,nome,plataforma,estado,criticidade,resumo,
   dono_nome,dono_custodia,capacidades,proxima_acao)
VALUES
  ('asset:meta-business:piloto','meta_business_portfolio','paid_media',
   'Business piloto','Meta','verified','high',
   'Business de prova local sem qualquer identificador ou acesso real.',
   'Operacao local','verified',ARRAY['Leitura Meta'],
   'Manter a prova local sem conectar uma conta real.'),
  ('asset:meta-ad-account:piloto','meta_ad_account','paid_media',
   'Conta piloto','Meta','verified','high',
   'Conta de prova local sem qualquer identificador ou acesso real.',
   'Operacao local','verified',ARRAY['Leitura Meta'],
   'Manter a prova local sem conectar uma conta real.');

INSERT INTO public.trafego_meta_business
  (cofre_ativo_id,business_external_id,nome_observado,observado_em)
VALUES ('asset:meta-business:piloto','100','Business',now());

INSERT INTO public.trafego_meta_ad_account
  (cofre_ativo_id,business_ativo_id,account_external_id,readiness_state,observado_em)
VALUES ('asset:meta-ad-account:piloto','asset:meta-business:piloto','200','READY_FOR_READ',now());

INSERT INTO public.trafego_meta_project_binding
  (ad_account_ativo_id,project_id,confirmado_por,evidencia_resumo)
VALUES ('asset:meta-ad-account:piloto',1,'prova-local','fixture hermetica local');

INSERT INTO public.trafego_meta_campaign
  (meta_campaign_id,ad_account_ativo_id,external_id,nome,status,effective_status,
   observado_em,ultima_vez_visto_em)
VALUES ('11111111-1111-1111-1111-111111111111','asset:meta-ad-account:piloto',
        '300','Campanha','PAUSED','PAUSED',now(),now());

INSERT INTO public.trafego_meta_adset
  (meta_adset_id,meta_campaign_id,external_id,nome,observado_em,ultima_vez_visto_em)
VALUES ('22222222-2222-2222-2222-222222222222','11111111-1111-1111-1111-111111111111',
        '400','Conjunto',now(),now());

INSERT INTO public.trafego_meta_ad
  (meta_ad_id,meta_adset_id,external_id,nome,observado_em,ultima_vez_visto_em)
VALUES ('33333333-3333-3333-3333-333333333333','22222222-2222-2222-2222-222222222222',
        '500','Anuncio',now(),now());

INSERT INTO public.trafego_meta_creative
  (meta_creative_id,ad_account_ativo_id,external_id,nome,observado_em,ultima_vez_visto_em)
VALUES ('44444444-4444-4444-4444-444444444444','asset:meta-ad-account:piloto',
        '600','Criativo',now(),now());

INSERT INTO public.trafego_meta_ad_creative_binding
  (meta_ad_id,meta_creative_id,observado_em)
VALUES ('33333333-3333-3333-3333-333333333333','44444444-4444-4444-4444-444444444444',now());

INSERT INTO public.trafego_meta_sync_run
  (run_id,ad_account_ativo_id,chave_de_idempotencia,resultado,iniciado_em,concluido_em,
   paginas_lidas,contagens,erro_codigo,erro_mensagem)
VALUES
  ('55555555-5555-5555-5555-555555555551','asset:meta-ad-account:piloto',
   'meta_sync_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','falhou',now(),now(),0,'{}',
   'META_RATE_LIMIT','limite temporario'),
  ('55555555-5555-5555-5555-555555555552','asset:meta-ad-account:piloto',
   'meta_sync_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','falhou',now(),now(),0,'{}',
   'META_RATE_LIMIT','retry permitido'),
  ('55555555-5555-5555-5555-555555555553','asset:meta-ad-account:piloto',
   'meta_sync_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','ok',now(),now(),4,
   '{"campaign":1,"adset":1,"ad":1,"creative":1}',NULL,NULL);

DO $recusas$
DECLARE recusou boolean;
BEGIN
  recusou := false;
  BEGIN
    INSERT INTO public.trafego_meta_sync_run
      (run_id,ad_account_ativo_id,chave_de_idempotencia,resultado,iniciado_em,concluido_em)
    VALUES ('55555555-5555-5555-5555-555555555554','asset:meta-ad-account:piloto',
            'meta_sync_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','ok',now(),now());
  EXCEPTION WHEN unique_violation THEN recusou := true; END;
  IF NOT recusou THEN RAISE EXCEPTION 'segundo sucesso idempotente passou'; END IF;

  recusou := false;
  BEGIN
    INSERT INTO public.trafego_meta_ad_account
      (cofre_ativo_id,business_ativo_id,account_external_id)
    VALUES ('asset:meta-ad-account:piloto','asset:meta-business:piloto','act_200');
  EXCEPTION WHEN check_violation OR unique_violation THEN recusou := true; END;
  IF NOT recusou THEN RAISE EXCEPTION 'account id com act_ passou'; END IF;

  recusou := false;
  BEGIN
    DELETE FROM public.trafego_meta_campaign
     WHERE meta_campaign_id='11111111-1111-1111-1111-111111111111';
  EXCEPTION WHEN raise_exception THEN recusou := true; END;
  IF NOT recusou THEN RAISE EXCEPTION 'DELETE de campanha passou'; END IF;
END
$recusas$;
SQL

aplicar "$ROLLBACK"
executar -t -A <<'SQL' | grep -qx '0'
SELECT count(*) FROM pg_class c JOIN pg_namespace s ON s.oid=c.relnamespace
 WHERE s.nspname='public' AND c.relname LIKE 'trafego_meta_%' AND c.relkind='r';
SQL
executar -t -A <<'SQL' | grep -qx '1'
SELECT count(*) FROM public.cofre_ativo WHERE ativo_id='asset:meta-ad-account:piloto';
SQL
aplicar "$MIGRATION"

echo "PASS v15_01: apply, constraints, RLS/grants, no-delete, rollback e reapply"
