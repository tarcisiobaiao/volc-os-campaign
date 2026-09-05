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
     AND c.relname IN ('trafego_meta_create_approval','trafego_meta_create_step',
                       'trafego_meta_validation_receipt');
  IF n <> 3 THEN RAISE EXCEPTION 'esperava as 3 tabelas de criacao; encontrou %', n; END IF;

  SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace s ON s.oid=c.relnamespace
   WHERE s.nspname='public' AND c.relkind='r'
     AND c.relname IN ('trafego_meta_create_approval','trafego_meta_create_step',
                       'trafego_meta_validation_receipt')
     AND c.relrowsecurity AND c.relforcerowsecurity;
  IF n <> 3 THEN RAISE EXCEPTION 'RLS/FORCE ausente na autoridade de criacao'; END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.role_table_grants
     WHERE table_schema='public'
       AND table_name IN ('trafego_meta_create_approval','trafego_meta_create_step',
                          'trafego_meta_validation_receipt')
       AND grantee IN ('anon','authenticated')
  ) THEN RAISE EXCEPTION 'papel de browser recebeu grant na autoridade de criacao'; END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.role_table_grants
     WHERE table_schema='public'
       AND table_name IN ('trafego_meta_create_approval','trafego_meta_create_step',
                          'trafego_meta_validation_receipt')
       AND grantee='service_role' AND privilege_type <> 'SELECT'
  ) THEN RAISE EXCEPTION 'service_role escreve direto na tabela em vez de usar RPC'; END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.role_routine_grants
     WHERE routine_schema='public' AND routine_name LIKE 'trafego_meta_create_%'
       AND grantee IN ('anon','authenticated','PUBLIC')
  ) THEN RAISE EXCEPTION 'papel de browser pode executar RPC de criacao'; END IF;

  -- ⚠️ Toda RPC nova precisa de GRANT ao service_role. Sem esta contagem, uma
  -- funcao acrescentada sem o par REVOKE/GRANT so falharia em producao, na
  -- primeira chamada — que e o pior lugar para descobrir.
  SELECT count(*) INTO n FROM information_schema.role_routine_grants
   WHERE routine_schema='public' AND routine_name LIKE 'trafego_meta_create_%'
     AND grantee='service_role' AND privilege_type='EXECUTE';
  IF n <> 9 THEN
    RAISE EXCEPTION 'esperava 9 RPCs executaveis pelo service_role; encontrou %', n;
  END IF;
END
$prova$;
SQL

echo "▶ uso: a saga inteira pelas RPCs, como o executor Python as chama"
executar <<'SQL'
SET ROLE service_role;
DO $uso$
DECLARE
  v_aprovacao jsonb; v_id uuid; v_passo jsonb; v_ref uuid; v_recibo jsonb;
  v_validacao jsonb; v_vid uuid; v_manifesto_srv jsonb;
  v_hash text := repeat('a', 64);
  v_payload text := repeat('b', 64);
  v_manifesto text[] := ARRAY['campaign','adset','creative:v1','ad:v1'];
BEGIN
  -- ⚠️ Notacao NOMEADA de proposito, com os mesmos nomes que
  -- backend/app/trafego/meta_execucao/registro.py envia via PostgREST. Chamar
  -- por posicao deixaria um rename de parametro passar verde.
  --
  -- NAO EXISTE APROVACAO SEM RECIBO DE VALIDACAO. A gravacao abaixo e o que a
  -- rota /validar faz depois de a Meta responder `success` — e e por ela que a
  -- aprovacao sabe que o plano foi validado, em vez de acreditar no navegador.
  v_validacao := public.trafego_meta_create_record_validation(
    p_plan_sha256 => v_hash,
    p_account_ref => 'metaacct_prova_local',
    p_actor_id => 'operador-local',
    p_coverage => 'INDEPENDENT_ROOTS_ONLY',
    p_steps_validated => ARRAY['campaign','creative:v1'],
    p_steps_pending => ARRAY['adset','ad:v1'],
    p_operations_total => 4,
    p_objects_created => 0);
  v_vid := (v_validacao->>'validation_id')::uuid;

  v_aprovacao := public.trafego_meta_create_approve(
    p_plan_sha256 => v_hash,
    p_account_ref => 'metaacct_prova_local',
    p_actor_id => 'operador-local',
    p_daily_budget_minor => 1000,
    p_currency => 'BRL',
    p_expires_at => clock_timestamp() + interval '15 minutes',
    p_steps_expected => v_manifesto,
    p_validation_id => v_vid,
    p_validation_max_age_seconds => 1800,
    p_paused_birth_confirmed => true,
    p_plan_request => '{"account_ref":"metaacct_prova_local"}'::jsonb);
  v_id := (v_aprovacao->>'approval_id')::uuid;
  IF v_aprovacao->'steps_expected' IS NULL THEN
    RAISE EXCEPTION 'aprovacao nao devolveu o manifesto';
  END IF;
  IF (v_aprovacao->>'operations_expected')::int <> 4 THEN
    RAISE EXCEPTION 'aprovacao nao fixou a contagem de operacoes';
  END IF;
  IF (v_aprovacao->>'paused_birth_confirmed')::boolean IS NOT TRUE THEN
    RAISE EXCEPTION 'aprovacao nao fixou a confirmacao de nascimento PAUSED';
  END IF;

  -- O manifesto do servidor devolve o pedido do operador e o step_ref. E ele
  -- que permite a rota de criacao receber so o approval_id.
  v_manifesto_srv := public.trafego_meta_create_approval_manifest(p_approval_id => v_id);
  IF v_manifesto_srv->'plan_request' IS NULL THEN
    RAISE EXCEPTION 'manifesto do servidor nao devolveu o pedido do operador';
  END IF;
  IF (v_manifesto_srv->>'daily_budget_minor')::bigint <> 1000
     OR v_manifesto_srv->>'currency' <> 'BRL' THEN
    RAISE EXCEPTION 'manifesto do servidor nao fixou orcamento e moeda';
  END IF;

  -- 1. campaign: primeiro passo do manifesto, despacha.
  v_passo := public.trafego_meta_create_prepare_step(
    p_plan_sha256 => v_hash, p_approval_id => v_id, p_actor_id => 'operador-local',
    p_step_name => 'campaign', p_payload_sha256 => v_payload);
  IF v_passo->>'state' <> 'DESPACHAR' THEN
    RAISE EXCEPTION 'primeiro passo deveria despachar; veio %', v_passo->>'state';
  END IF;
  v_ref := (v_passo->>'step_ref')::uuid;

  -- Manifesto vazio nao pode virar aprovacao: ela ficaria APPROVED e inutil,
  -- porque nenhum passo poderia ser preparado depois.
  BEGIN
    PERFORM public.trafego_meta_create_approve(
      p_plan_sha256 => repeat('f', 64),
      p_account_ref => 'metaacct_prova_local',
      p_actor_id => 'operador-local',
      p_daily_budget_minor => 1000,
      p_currency => 'BRL',
      p_expires_at => clock_timestamp() + interval '15 minutes',
      p_steps_expected => ARRAY[]::text[],
      p_validation_id => v_vid,
      p_validation_max_age_seconds => 1800,
      p_paused_birth_confirmed => true,
      p_plan_request => '{}'::jsonb);
    RAISE EXCEPTION 'manifesto vazio foi aceito';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> 'META_APPROVAL_MANIFEST_EMPTY' THEN RAISE; END IF;
  END;

  -- Manifesto com passo repetido tambem nao.
  BEGIN
    PERFORM public.trafego_meta_create_approve(
      p_plan_sha256 => repeat('f', 64),
      p_account_ref => 'metaacct_prova_local',
      p_actor_id => 'operador-local',
      p_daily_budget_minor => 1000,
      p_currency => 'BRL',
      p_expires_at => clock_timestamp() + interval '15 minutes',
      p_steps_expected => ARRAY['campaign','campaign'],
      p_validation_id => v_vid,
      p_validation_max_age_seconds => 1800,
      p_paused_birth_confirmed => true,
      p_plan_request => '{}'::jsonb);
    RAISE EXCEPTION 'manifesto com passo repetido foi aceito';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> 'META_APPROVAL_MANIFEST_DUPLICATE' THEN RAISE; END IF;
  END;

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

echo "▶ ajudante de prova: aprovar exige recibo de validacao, sempre"
executar <<'SQL'
-- Fixture do proprio script, nao da migration: encapsula o par
-- record_validation -> approve para que as provas seguintes falem sobre a
-- REGRA em teste, e nao sobre a assinatura da RPC. Ela e derrubada antes do
-- rollback.
CREATE FUNCTION public.prova_aprovar(
  p_hash text,
  p_ator text,
  p_janela interval DEFAULT interval '15 minutes',
  p_manifesto text[] DEFAULT ARRAY['campaign','adset']
) RETURNS jsonb
LANGUAGE plpgsql
AS $ajuda$
DECLARE v_vid uuid;
BEGIN
  v_vid := (public.trafego_meta_create_record_validation(
    p_plan_sha256 => p_hash,
    p_account_ref => 'metaacct_prova_local',
    p_actor_id => p_ator,
    p_coverage => 'INDEPENDENT_ROOTS_ONLY',
    p_steps_validated => ARRAY[p_manifesto[1]],
    p_steps_pending => p_manifesto[2:],
    p_operations_total => cardinality(p_manifesto),
    p_objects_created => 0)->>'validation_id')::uuid;
  RETURN public.trafego_meta_create_approve(
    p_plan_sha256 => p_hash,
    p_account_ref => 'metaacct_prova_local',
    p_actor_id => p_ator,
    p_daily_budget_minor => 1000,
    p_currency => 'BRL',
    p_expires_at => clock_timestamp() + p_janela,
    p_steps_expected => p_manifesto,
    p_validation_id => v_vid,
    p_validation_max_age_seconds => 1800,
    p_paused_birth_confirmed => true,
    p_plan_request => '{"account_ref":"metaacct_prova_local"}'::jsonb);
END
$ajuda$;
SQL

echo "▶ o recibo de validacao e a condicao da aprovacao, campo a campo"
executar <<'SQL'
SET ROLE service_role;
DO $vinculo$
DECLARE
  v_vid uuid; v_hash text := repeat('7', 64);
  v_manifesto text[] := ARRAY['campaign','adset'];
BEGIN
  v_vid := (public.trafego_meta_create_record_validation(
    v_hash, 'metaacct_prova_local', 'operador-local', 'INDEPENDENT_ROOTS_ONLY',
    ARRAY['campaign'], ARRAY['adset'], 2, 0)->>'validation_id')::uuid;

  -- 1. Recibo inexistente: um validation_id inventado pelo navegador nao abre nada.
  BEGIN
    PERFORM public.trafego_meta_create_approve(
      v_hash, 'metaacct_prova_local', 'operador-local', 1000, 'BRL',
      clock_timestamp() + interval '15 minutes', v_manifesto,
      '00000000-0000-0000-0000-000000000000'::uuid, 1800, true, '{}'::jsonb);
    RAISE EXCEPTION 'recibo inexistente foi aceito';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_VALIDATION_RECEIPT_NOT_FOUND' THEN RAISE; END IF;
  END;

  -- 2. Hash divergente entre o plano aprovado e o plano validado.
  BEGIN
    PERFORM public.trafego_meta_create_approve(
      repeat('8', 64), 'metaacct_prova_local', 'operador-local', 1000, 'BRL',
      clock_timestamp() + interval '15 minutes', v_manifesto, v_vid, 1800, true, '{}'::jsonb);
    RAISE EXCEPTION 'plano diferente do validado foi aceito';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_VALIDATION_PLAN_DIVERGED' THEN RAISE; END IF;
  END;

  -- 3. Conta divergente.
  BEGIN
    PERFORM public.trafego_meta_create_approve(
      v_hash, 'metaacct_outra_conta', 'operador-local', 1000, 'BRL',
      clock_timestamp() + interval '15 minutes', v_manifesto, v_vid, 1800, true, '{}'::jsonb);
    RAISE EXCEPTION 'conta diferente da validada foi aceita';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_VALIDATION_ACCOUNT_DIVERGED' THEN RAISE; END IF;
  END;

  -- 4. Ator divergente: quem validou nao e quem aprova.
  BEGIN
    PERFORM public.trafego_meta_create_approve(
      v_hash, 'metaacct_prova_local', 'outro-operador', 1000, 'BRL',
      clock_timestamp() + interval '15 minutes', v_manifesto, v_vid, 1800, true, '{}'::jsonb);
    RAISE EXCEPTION 'ator diferente do validador foi aceito';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_VALIDATION_ACTOR_DIVERGED' THEN RAISE; END IF;
  END;

  -- 5. Manifesto diferente do que foi validado.
  BEGIN
    PERFORM public.trafego_meta_create_approve(
      v_hash, 'metaacct_prova_local', 'operador-local', 1000, 'BRL',
      clock_timestamp() + interval '15 minutes', ARRAY['campaign','adset','creative'],
      v_vid, 1800, true, '{}'::jsonb);
    RAISE EXCEPTION 'manifesto diferente do validado foi aceito';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_VALIDATION_MANIFEST_DIVERGED' THEN RAISE; END IF;
  END;

  -- 6. Sem a confirmacao humana de nascimento PAUSED nao existe aprovacao.
  BEGIN
    PERFORM public.trafego_meta_create_approve(
      v_hash, 'metaacct_prova_local', 'operador-local', 1000, 'BRL',
      clock_timestamp() + interval '15 minutes', v_manifesto, v_vid, 1800, false, '{}'::jsonb);
    RAISE EXCEPTION 'aprovacao sem confirmacao PAUSED foi aceita';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_PAUSED_BIRTH_NOT_CONFIRMED' THEN RAISE; END IF;
  END;

  -- 7. Expiracao longa: uma autorizacao de gasto nao vive um dia.
  BEGIN
    PERFORM public.trafego_meta_create_approve(
      v_hash, 'metaacct_prova_local', 'operador-local', 1000, 'BRL',
      clock_timestamp() + interval '2 hours', v_manifesto, v_vid, 1800, true, '{}'::jsonb);
    RAISE EXCEPTION 'expiracao de duas horas foi aceita';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_APPROVAL_EXPIRY_TOO_LONG' THEN RAISE; END IF;
  END;

  -- 8. Um validate_only que criou objeto NAO e recibo de validacao.
  BEGIN
    PERFORM public.trafego_meta_create_record_validation(
      repeat('9', 64), 'metaacct_prova_local', 'operador-local', 'INDEPENDENT_ROOTS_ONLY',
      ARRAY['campaign'], ARRAY['adset'], 2, 1);
    RAISE EXCEPTION 'recibo com objeto criado foi aceito';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_VALIDATION_NOT_CLEAN' THEN RAISE; END IF;
  END;

  -- 9. Cobertura desconhecida nao vira recibo: gravar outra palavra faria uma
  --    aprovacao futura acreditar numa validacao mais ampla do que a que houve.
  BEGIN
    PERFORM public.trafego_meta_create_record_validation(
      repeat('9', 64), 'metaacct_prova_local', 'operador-local', 'FULL_PLAN_ACCEPTED',
      ARRAY['campaign'], ARRAY['adset'], 2, 0);
    RAISE EXCEPTION 'cobertura desconhecida foi aceita';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_VALIDATION_COVERAGE_UNKNOWN' THEN RAISE; END IF;
  END;

  -- 10. O recibo autoriza UMA aprovacao. Reaproveitar e replay.
  PERFORM public.trafego_meta_create_approve(
    v_hash, 'metaacct_prova_local', 'operador-local', 1000, 'BRL',
    clock_timestamp() + interval '1 second', v_manifesto, v_vid, 1800, true,
    '{"a":1}'::jsonb);
  PERFORM pg_sleep(1.2);
  BEGIN
    PERFORM public.trafego_meta_create_approve(
      v_hash, 'metaacct_prova_local', 'operador-local', 1000, 'BRL',
      clock_timestamp() + interval '15 minutes', v_manifesto, v_vid, 1800, true,
      '{"a":1}'::jsonb);
    RAISE EXCEPTION 'o mesmo recibo autorizou duas aprovacoes';
  EXCEPTION WHEN unique_violation THEN NULL;
  END;
END
$vinculo$;
RESET ROLE;
SQL

echo "▶ uma aprovacao viva por plano: expiracao e falha liberam, ambiguidade prende"
executar <<'SQL'
SET ROLE service_role;
DO $unica$
DECLARE
  v_ap jsonb; v_id uuid; v_passo jsonb; v_ref uuid;
  v_curto text := repeat('e', 64);
  v_falho text := repeat('f', 64);
  v_ambiguo text := repeat('0', 64);
  v_outro text := repeat('1', 64);
  v_payload text := repeat('b', 64);
BEGIN
  -- 1. DUAS APROVACOES VIVAS DO MESMO PLANO: a segunda tem de ser recusada.
  --    Cada uma traz o SEU recibo de validacao, senao o que barraria a segunda
  --    seria o UNIQUE do recibo — e a prova do portao de plano nao existiria.
  v_ap := public.prova_aprovar(v_curto, 'operador-local', interval '1 second');
  BEGIN
    PERFORM public.prova_aprovar(v_curto, 'operador-local');
    RAISE EXCEPTION 'duas aprovacoes vivas do mesmo plano foram aceitas';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_APPROVAL_ALREADY_LIVE' THEN RAISE; END IF;
  END;

  -- 2. Outro plano nunca e barrado pelo vizinho.
  PERFORM public.prova_aprovar(v_outro, 'operador-local');

  -- 3. EXPIRACAO LIBERA. `clock_timestamp()` anda dentro da transacao, entao a
  --    aprovacao de 1 segundo morre de verdade aqui — nao e simulacao por UPDATE.
  PERFORM pg_sleep(1.2);
  PERFORM public.prova_aprovar(v_curto, 'operador-local');
  IF (SELECT count(*) FROM public.trafego_meta_create_approval
       WHERE plan_sha256 = v_curto) <> 2 THEN
    RAISE EXCEPTION 'reaprovacao apos expiracao deveria criar a segunda linha';
  END IF;

  -- 4. FALHA LIBERA: um passo FALHO nunca volta a despachar, entao segurar o
  --    plano refem dele ate a expiracao prenderia o operador a um livro morto.
  v_ap := public.prova_aprovar(v_falho, 'operador-local');
  v_id := (v_ap->>'approval_id')::uuid;
  v_passo := public.trafego_meta_create_prepare_step(
    p_plan_sha256 => v_falho, p_approval_id => v_id, p_actor_id => 'operador-local',
    p_step_name => 'campaign', p_payload_sha256 => v_payload);
  PERFORM public.trafego_meta_create_fail_step(
    p_step_ref => (v_passo->>'step_ref')::uuid, p_error_code => 'META_REMOTE_CREATE_FAILED');
  PERFORM public.prova_aprovar(v_falho, 'operador-local');

  -- 5. AMBIGUIDADE PRENDE: pode ter nascido objeto. Reaprovar antes de
  --    reconciliar e exatamente a duplicacao que o portao existe para impedir.
  v_ap := public.prova_aprovar(v_ambiguo, 'operador-local');
  v_id := (v_ap->>'approval_id')::uuid;
  PERFORM public.trafego_meta_create_prepare_step(
    p_plan_sha256 => v_ambiguo, p_approval_id => v_id, p_actor_id => 'operador-local',
    p_step_name => 'campaign', p_payload_sha256 => v_payload);
  v_passo := public.trafego_meta_create_prepare_step(
    p_plan_sha256 => v_ambiguo, p_approval_id => v_id, p_actor_id => 'operador-local',
    p_step_name => 'campaign', p_payload_sha256 => v_payload);
  IF v_passo->>'state' <> 'AMBIGUO' THEN
    RAISE EXCEPTION 'o passo deveria estar ambiguo para esta prova';
  END IF;
  v_ref := (v_passo->>'step_ref')::uuid;
  BEGIN
    PERFORM public.prova_aprovar(v_ambiguo, 'operador-local');
    RAISE EXCEPTION 'reaprovou um plano com passo ambiguo, sem reconciliar';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_APPROVAL_ALREADY_LIVE' THEN RAISE; END IF;
  END;

  -- 6. RECONCILIACAO: o unico caminho de AMBIGUOUS para FALHO, e ele exige que
  --    a ausencia tenha sido provada por leitura. `fail_step` continua recusando
  --    o estado ambiguo, que e o que impede fechar um recibo sem prova.
  BEGIN
    PERFORM public.trafego_meta_create_fail_step(
      p_step_ref => v_ref, p_error_code => 'META_REMOTE_CREATE_FAILED');
    RAISE EXCEPTION 'fail_step fechou um passo ambiguo sem reconciliacao';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_STEP_CANNOT_FAIL' THEN RAISE; END IF;
  END;
  IF (public.trafego_meta_create_resolve_absent(
        p_step_ref => v_ref, p_error_code => 'META_RECONCILED_ABSENT'))->>'state' <> 'FAILED' THEN
    RAISE EXCEPTION 'a reconciliacao por ausencia nao fechou o passo';
  END IF;
  BEGIN
    PERFORM public.trafego_meta_create_resolve_absent(
      p_step_ref => v_ref, p_error_code => 'META_RECONCILED_ABSENT');
    RAISE EXCEPTION 'resolve_absent aceitou um passo que ja estava fechado';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_STEP_NOT_AMBIGUOUS' THEN RAISE; END IF;
  END;

  -- 7. Reconciliar por PRESENCA nao precisa de funcao nova: close_step ja aceita
  --    AMBIGUOUS -> CREATED, e continua recusando um id diferente do gravado.
  v_ap := public.prova_aprovar(repeat('2', 64), 'operador-local');
  v_id := (v_ap->>'approval_id')::uuid;
  PERFORM public.trafego_meta_create_prepare_step(
    p_plan_sha256 => repeat('2', 64), p_approval_id => v_id, p_actor_id => 'operador-local',
    p_step_name => 'campaign', p_payload_sha256 => v_payload);
  v_passo := public.trafego_meta_create_prepare_step(
    p_plan_sha256 => repeat('2', 64), p_approval_id => v_id, p_actor_id => 'operador-local',
    p_step_name => 'campaign', p_payload_sha256 => v_payload);
  v_ref := (v_passo->>'step_ref')::uuid;
  PERFORM public.trafego_meta_create_close_step(
    p_step_ref => v_ref, p_external_object_id => '7777');
  IF (SELECT state FROM public.trafego_meta_create_step WHERE step_id = v_ref) <> 'CREATED' THEN
    RAISE EXCEPTION 'a reconciliacao por presenca nao fechou o passo como criado';
  END IF;

  -- 8. Hash fora de forma nao chega a virar chave de lock.
  BEGIN
    PERFORM public.trafego_meta_create_approve(
      'nao-e-hash', 'metaacct_prova_local', 'operador-local', 1000, 'BRL',
      clock_timestamp() + interval '15 minutes', ARRAY['campaign'],
      gen_random_uuid(), 1800, true, '{}'::jsonb);
    RAISE EXCEPTION 'hash invalido foi aceito';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'META_APPROVAL_PLAN_HASH_INVALID' THEN RAISE; END IF;
  END;
END
$unica$;
RESET ROLE;
SQL

echo "▶ concorrencia real: duas sessoes disputando o mesmo plano"
# ⚠️ Sem lock, as duas sessoes leem "nao existe" ao mesmo tempo — em READ
# COMMITTED a linha nao commitada da outra e invisivel — e AMBAS inserem. O
# EXISTS sozinho nao fecha essa janela; e por isso que a prova precisa de duas
# conexoes de verdade, nao de um DO block.
PLANO_DISPUTADO="$(printf 'c%.0s' $(seq 1 64))"
executar > "${BASE}/sessao-a.log" 2>&1 <<SQL &
BEGIN;
SET ROLE service_role;
-- ⚠️ Cada sessao grava o SEU recibo de validacao. Compartilhar um faria o
-- UNIQUE(validation_id) barrar a segunda, e a prova passaria a ser sobre a
-- unicidade do recibo em vez do lock consultivo por plano.
SELECT public.prova_aprovar('${PLANO_DISPUTADO}', 'sessao-a');
SELECT pg_sleep(2);
COMMIT;
SQL
PID_A=$!
sleep 0.7
executar > "${BASE}/sessao-b.log" 2>&1 <<SQL &
BEGIN;
SET ROLE service_role;
SELECT public.prova_aprovar('${PLANO_DISPUTADO}', 'sessao-b');
COMMIT;
SQL
PID_B=$!
CODIGO_A=0; CODIGO_B=0
wait "$PID_A" || CODIGO_A=$?
wait "$PID_B" || CODIGO_B=$?
[[ $CODIGO_A -eq 0 ]] || { echo "a sessao A deveria ter aprovado" >&2; cat "${BASE}/sessao-a.log" >&2; exit 1; }
[[ $CODIGO_B -ne 0 ]] || { echo "a sessao B aprovou o mesmo plano em paralelo" >&2; exit 1; }
grep -q 'META_APPROVAL_ALREADY_LIVE' "${BASE}/sessao-b.log" || {
  echo "a sessao B falhou por outro motivo:" >&2; cat "${BASE}/sessao-b.log" >&2; exit 1; }
executar -v ON_ERROR_STOP=1 <<SQL
DO \$disputa\$
BEGIN
  IF (SELECT count(*) FROM public.trafego_meta_create_approval
       WHERE plan_sha256 = '${PLANO_DISPUTADO}') <> 1 THEN
    RAISE EXCEPTION 'a disputa deixou % linhas para o mesmo plano',
      (SELECT count(*) FROM public.trafego_meta_create_approval
        WHERE plan_sha256 = '${PLANO_DISPUTADO}');
  END IF;
END
\$disputa\$;
SQL
echo "  ✓ so a sessao A aprovou; a B esperou o lock e foi recusada"

echo "▶ autorizacao: sem service_role nada executa"
executar <<'SQL'
SET ROLE authenticated;
DO $nega$
BEGIN
  BEGIN
    PERFORM public.trafego_meta_create_approve(
      repeat('d', 64), 'metaacct_prova_local', 'invasor', 1000, 'BRL',
      clock_timestamp() + interval '15 minutes', ARRAY['campaign'],
      gen_random_uuid(), 1800, true, '{}'::jsonb);
    RAISE EXCEPTION 'papel de browser conseguiu aprovar criacao Meta';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
  -- Gravar recibo de validacao tambem e privilegio de servico.
  BEGIN
    PERFORM public.trafego_meta_create_record_validation(
      repeat('d', 64), 'metaacct_prova_local', 'invasor', 'INDEPENDENT_ROOTS_ONLY',
      ARRAY['campaign'], ARRAY['adset'], 2, 0);
    RAISE EXCEPTION 'papel de browser gravou recibo de validacao Meta';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
END
$nega$;
RESET ROLE;
SQL

echo "▶ reverter"
# A fixture do script sai antes: ela nao pertence a migration, e deixa-la viva
# faria a prova de limpeza do rollback julgar um objeto que nao e dela.
executar -c 'DROP FUNCTION IF EXISTS public.prova_aprovar(text,text,interval,text[]);'
aplicar "$ROLLBACK"
executar <<'SQL'
DO $limpo$
DECLARE n integer;
BEGIN
  SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace s ON s.oid=c.relnamespace
   WHERE s.nspname='public'
     AND c.relname IN ('trafego_meta_create_approval','trafego_meta_create_step',
                       'trafego_meta_validation_receipt');
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
DECLARE v jsonb; v_vid uuid;
BEGIN
  v_vid := (public.trafego_meta_create_record_validation(
    repeat('e', 64), 'metaacct_prova_local', 'operador-local', 'INDEPENDENT_ROOTS_ONLY',
    ARRAY['campaign'], ARRAY['adset'], 2, 0)->>'validation_id')::uuid;
  v := public.trafego_meta_create_approve(
    repeat('e', 64), 'metaacct_prova_local', 'operador-local', 500, 'BRL',
    clock_timestamp() + interval '15 minutes', ARRAY['campaign','adset'],
    v_vid, 1800, true, '{"account_ref":"metaacct_prova_local"}'::jsonb);
  IF (v->>'ok')::boolean IS NOT TRUE THEN
    RAISE EXCEPTION 'reaplicacao nao deixou a autoridade utilizavel';
  END IF;
END
$reaplicado$;
RESET ROLE;
SQL

echo "✓ ciclo aplicar → usar → reverter → reaplicar provado em PostgreSQL descartavel"
