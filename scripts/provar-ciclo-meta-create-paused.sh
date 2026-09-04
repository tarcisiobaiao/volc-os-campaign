#!/usr/bin/env bash
# Prova local e descartavel da migration candidata do nascimento Meta PAUSED.
#
# Cobre o ciclo inteiro que faltava: aplicar -> USAR -> reverter -> reaplicar.
# "Usar" nao e decoracao: um apply que nunca exercita as RPCs deixa passar
# rename de funcao, troca de parametro e regra de autorizacao quebrada — que e
# exatamente o defeito que o contrato Python<->SQL do registro tinha.
#
# Nunca toca o Supabase oficial nem a Meta. Nenhuma imagem e baixada.
set -euo pipefail
export LC_ALL=C LANG=C

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COFRE="${RAIZ}/supabase/migrations/v13_01_cofre_de_ativos.sql"
READ_MODEL="${RAIZ}/supabase/migrations/v15_01_meta_ads_read_model.sql"
MIGRATION="${RAIZ}/supabase/migrations/20260904183418_meta_create_paused_executor.sql"
ROLLBACK="${RAIZ}/supabase/migrations/20260904183514_meta_create_paused_executor_rollback.sql"
IMAGEM="postgres:15"
BASE="$(mktemp -d "${TMPDIR:-/tmp}/volc-meta-create.XXXXXX")"
CID=""; PGDATA=""; SOCK=""; LOCAL=0

[[ "${1:-}" == "--local" ]] && LOCAL=1
[[ $# -le 1 ]] || { echo "uso: $0 [--local]" >&2; exit 2; }
for arquivo in "$COFRE" "$READ_MODEL" "$MIGRATION" "$ROLLBACK"; do
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
-- O default ACL quebrado do Supabase e reproduzido de proposito: a migration
-- precisa REVOGAR sozinha, nao contar com um banco limpo.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon, authenticated, service_role;
SQL

echo "▶ pre-requisito: cofre + read model Meta"
aplicar "$COFRE"
aplicar "$READ_MODEL"

echo "▶ aplicar a migration candidata"
aplicar "$MIGRATION"

echo "▶ forma: tabelas, RLS, grants"
executar <<'SQL'
DO $prova$
DECLARE n integer;
BEGIN
  SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace s ON s.oid=c.relnamespace
   WHERE s.nspname='public' AND c.relkind='r'
     AND c.relname IN ('trafego_meta_create_approval','trafego_meta_create_step');
  IF n <> 2 THEN RAISE EXCEPTION 'esperava as 2 tabelas de criacao; encontrou %', n; END IF;

  SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace s ON s.oid=c.relnamespace
   WHERE s.nspname='public' AND c.relkind='r'
     AND c.relname IN ('trafego_meta_create_approval','trafego_meta_create_step')
     AND c.relrowsecurity AND c.relforcerowsecurity;
  IF n <> 2 THEN RAISE EXCEPTION 'RLS/FORCE ausente na autoridade de criacao'; END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.role_table_grants
     WHERE table_schema='public'
       AND table_name IN ('trafego_meta_create_approval','trafego_meta_create_step')
       AND grantee IN ('anon','authenticated')
  ) THEN RAISE EXCEPTION 'papel de browser recebeu grant na autoridade de criacao'; END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.role_table_grants
     WHERE table_schema='public'
       AND table_name IN ('trafego_meta_create_approval','trafego_meta_create_step')
       AND grantee='service_role' AND privilege_type <> 'SELECT'
  ) THEN RAISE EXCEPTION 'service_role escreve direto na tabela em vez de usar RPC'; END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.role_routine_grants
     WHERE routine_schema='public' AND routine_name LIKE 'trafego_meta_create_%'
       AND grantee IN ('anon','authenticated','PUBLIC')
  ) THEN RAISE EXCEPTION 'papel de browser pode executar RPC de criacao'; END IF;
END
$prova$;
SQL

echo "▶ uso: a saga inteira pelas RPCs, como o executor Python as chama"
executar <<'SQL'
SET ROLE service_role;
DO $uso$
DECLARE
  v_aprovacao jsonb; v_id uuid; v_passo jsonb; v_ref uuid; v_recibo jsonb;
  v_hash text := repeat('a', 64);
  v_payload text := repeat('b', 64);
  v_manifesto text[] := ARRAY['campaign','adset','creative:v1','ad:v1'];
BEGIN
  -- ⚠️ Notacao NOMEADA de proposito, com os mesmos nomes que
  -- backend/app/trafego/meta_execucao/registro.py envia via PostgREST. Chamar
  -- por posicao deixaria um rename de parametro passar verde.
  v_aprovacao := public.trafego_meta_create_approve(
    p_plan_sha256 => v_hash,
    p_account_ref => 'metaacct_prova_local',
    p_actor_id => 'operador-local',
    p_daily_budget_minor => 1000,
    p_expires_at => clock_timestamp() + interval '1 hour',
    p_steps_expected => v_manifesto);
  v_id := (v_aprovacao->>'approval_id')::uuid;
  IF v_aprovacao->'steps_expected' IS NULL THEN
    RAISE EXCEPTION 'aprovacao nao devolveu o manifesto';
  END IF;

  -- 1. campaign: primeiro passo do manifesto, despacha.
  v_passo := public.trafego_meta_create_prepare_step(
    p_plan_sha256 => v_hash, p_approval_id => v_id, p_actor_id => 'operador-local',
    p_step_name => 'campaign', p_payload_sha256 => v_payload);
  IF v_passo->>'state' <> 'DESPACHAR' THEN
    RAISE EXCEPTION 'primeiro passo deveria despachar; veio %', v_passo->>'state';
  END IF;
  v_ref := (v_passo->>'step_ref')::uuid;

  -- Um passo fora de ordem nao pode ser preparado antes do anterior fechar.
  BEGIN
    PERFORM public.trafego_meta_create_prepare_step(
      p_plan_sha256 => v_hash, p_approval_id => v_id, p_actor_id => 'operador-local',
      p_step_name => 'creative:v1', p_payload_sha256 => v_payload);
    RAISE EXCEPTION 'passo fora de ordem foi aceito';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> 'META_STEP_OUT_OF_ORDER' THEN RAISE; END IF;
  END;

  -- Um passo fora do manifesto aprovado nunca entra.
  BEGIN
    PERFORM public.trafego_meta_create_prepare_step(
      p_plan_sha256 => v_hash, p_approval_id => v_id, p_actor_id => 'operador-local',
      p_step_name => 'creative:extra', p_payload_sha256 => v_payload);
    RAISE EXCEPTION 'passo fora do manifesto foi aceito';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> 'META_STEP_OUTSIDE_APPROVED_PLAN' THEN RAISE; END IF;
  END;

  -- Ator diferente do aprovador tambem nao.
  BEGIN
    PERFORM public.trafego_meta_create_prepare_step(
      p_plan_sha256 => v_hash, p_approval_id => v_id, p_actor_id => 'outro-operador',
      p_step_name => 'campaign', p_payload_sha256 => v_payload);
    RAISE EXCEPTION 'ator divergente foi aceito';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> 'META_APPROVAL_ACTOR_DIVERGED' THEN RAISE; END IF;
  END;

  -- Mesmo passo com payload diferente e divergencia, nao retomada.
  BEGIN
    PERFORM public.trafego_meta_create_prepare_step(
      p_plan_sha256 => v_hash, p_approval_id => v_id, p_actor_id => 'operador-local',
      p_step_name => 'campaign', p_payload_sha256 => repeat('c', 64));
    RAISE EXCEPTION 'payload divergente foi aceito';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> 'META_STEP_PAYLOAD_DIVERGED' THEN RAISE; END IF;
  END;

  PERFORM public.trafego_meta_create_close_step(
    p_step_ref => v_ref, p_external_object_id => '1001');
  -- Fechar de novo com o MESMO id e idempotente.
  IF (public.trafego_meta_create_close_step(
        p_step_ref => v_ref, p_external_object_id => '1001'))->>'repeated' <> 'true' THEN
    RAISE EXCEPTION 'reentrada do fechamento nao foi idempotente';
  END IF;
  -- Fechar com id DIFERENTE e divergencia.
  BEGIN
    PERFORM public.trafego_meta_create_close_step(
      p_step_ref => v_ref, p_external_object_id => '9999');
    RAISE EXCEPTION 'id externo divergente foi aceito';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> 'META_EXTERNAL_ID_DIVERGED' THEN RAISE; END IF;
  END;

  -- Retomada do passo ja criado devolve o id, sem novo POST.
  v_passo := public.trafego_meta_create_prepare_step(
    p_plan_sha256 => v_hash, p_approval_id => v_id, p_actor_id => 'operador-local',
    p_step_name => 'campaign', p_payload_sha256 => v_payload);
  IF v_passo->>'state' <> 'CRIADO' OR v_passo->>'external_object_id' <> '1001' THEN
    RAISE EXCEPTION 'retomada de passo criado nao devolveu o id gravado';
  END IF;

  -- 2. adset: agora o anterior existe.
  v_passo := public.trafego_meta_create_prepare_step(
    p_plan_sha256 => v_hash, p_approval_id => v_id, p_actor_id => 'operador-local',
    p_step_name => 'adset', p_payload_sha256 => v_payload);
  v_ref := (v_passo->>'step_ref')::uuid;
  PERFORM public.trafego_meta_create_close_step(
    p_step_ref => v_ref, p_external_object_id => '1002');

  -- 3. creative:v1 fica AMBIGUO: um IN_FLIGHT preparado duas vezes nao pode
  --    virar segundo POST.
  v_passo := public.trafego_meta_create_prepare_step(
    p_plan_sha256 => v_hash, p_approval_id => v_id, p_actor_id => 'operador-local',
    p_step_name => 'creative:v1', p_payload_sha256 => v_payload);
  v_passo := public.trafego_meta_create_prepare_step(
    p_plan_sha256 => v_hash, p_approval_id => v_id, p_actor_id => 'operador-local',
    p_step_name => 'creative:v1', p_payload_sha256 => v_payload);
  IF v_passo->>'state' <> 'AMBIGUO' THEN
    RAISE EXCEPTION 'reentrada de passo em voo deveria ficar ambigua; veio %', v_passo->>'state';
  END IF;

  v_recibo := public.trafego_meta_create_receipt(p_approval_id => v_id);
  IF jsonb_array_length(v_recibo->'steps') <> 3 THEN
    RAISE EXCEPTION 'recibo deveria listar 3 passos; listou %',
      jsonb_array_length(v_recibo->'steps');
  END IF;
  -- ⚠️ O recibo nunca devolve o id externo, so a afirmacao de que ele existe.
  IF v_recibo::text LIKE '%1001%' THEN
    RAISE EXCEPTION 'o recibo vazou um identificador externo';
  END IF;
END
$uso$;
RESET ROLE;
SQL

echo "▶ autorizacao: sem service_role nada executa"
executar <<'SQL'
SET ROLE authenticated;
DO $nega$
BEGIN
  BEGIN
    PERFORM public.trafego_meta_create_approve(
      repeat('d', 64), 'metaacct_prova_local', 'invasor', 1000,
      clock_timestamp() + interval '1 hour', ARRAY['campaign']);
    RAISE EXCEPTION 'papel de browser conseguiu aprovar criacao Meta';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
END
$nega$;
RESET ROLE;
SQL

echo "▶ reverter"
aplicar "$ROLLBACK"
executar <<'SQL'
DO $limpo$
DECLARE n integer;
BEGIN
  SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace s ON s.oid=c.relnamespace
   WHERE s.nspname='public'
     AND c.relname IN ('trafego_meta_create_approval','trafego_meta_create_step');
  IF n <> 0 THEN RAISE EXCEPTION 'rollback deixou % tabela(s) de criacao', n; END IF;
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace s ON s.oid=p.pronamespace
   WHERE s.nspname='public' AND p.proname LIKE 'trafego_meta_create_%';
  IF n <> 0 THEN RAISE EXCEPTION 'rollback deixou % funcao(oes) de criacao', n; END IF;
  -- O read model precisa sair intacto: criacao e observacao sao autoridades
  -- diferentes, e reverter uma nao pode derrubar a outra.
  IF to_regclass('public.trafego_meta_ad_account') IS NULL THEN
    RAISE EXCEPTION 'rollback da criacao derrubou o read model Meta';
  END IF;
END
$limpo$;
SQL

echo "▶ reaplicar"
aplicar "$MIGRATION"
executar <<'SQL'
SET ROLE service_role;
DO $reaplicado$
DECLARE v jsonb;
BEGIN
  v := public.trafego_meta_create_approve(
    repeat('e', 64), 'metaacct_prova_local', 'operador-local', 500,
    clock_timestamp() + interval '1 hour', ARRAY['campaign','adset']);
  IF (v->>'ok')::boolean IS NOT TRUE THEN
    RAISE EXCEPTION 'reaplicacao nao deixou a autoridade utilizavel';
  END IF;
END
$reaplicado$;
RESET ROLE;
SQL

echo "✓ ciclo aplicar → usar → reverter → reaplicar provado em PostgreSQL descartavel"
