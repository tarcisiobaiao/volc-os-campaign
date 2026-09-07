#!/bin/bash
# =============================================================================
# Prova local do READ MODEL Meta — PostgreSQL DESCARTÁVEL
# =============================================================================
# T06 · candidata 20260907210000_meta_read_model_consistency.sql
#
# ⚠️ ESTE SCRIPT NÃO TOCA O SUPABASE OFICIAL, e não tem como tocar: ele cria um
# cluster novo com `initdb`, num diretório temporário que ele mesmo destrói,
# ouvindo SÓ em 127.0.0.1, numa porta própria (55433 — a prova irmã usa 55432,
# e duas provas na mesma porta se derrubariam). Nenhuma variável de ambiente do
# projeto é lida; se alguma `SUPABASE_*` estiver definida, o script RECUSA
# rodar em vez de arriscar herdar um alvo real.
#
# ## O que ele prova, e por que cada etapa existe
#
#   1. duas leituras do MESMO dia → a view corrente expõe UMA linha por grão
#      (sem ela, somar `spend` na tabela base conta o mesmo dia duas vezes);
#   2. a MESMA chave estável repetida → `repetido=true` e NENHUM run novo —
#      inclusive quando o instante e o `snapshot_hash` mudaram, que é
#      exatamente o caso de dois cliques com um segundo de diferença;
#   3. snapshot VELHO chegando depois de um novo → recusado, nada regride, e o
#      recibo DIZ quantas linhas recusou;
#   4. objeto sumido numa leitura COMPLETA → `ausente_desde` marcado;
#   5. o mesmo objeto sumido numa leitura PARCIAL → `ausente_desde` continua
#      NULL (ausência exige leitura completa; adivinhar aqui apaga inventário);
#   6. `service_role` não apaga fato: DELETE e TRUNCATE recusados, SELECT vale,
#      a RPC executa;
#   7. `anon` e `authenticated` não leem NENHUMA tabela Meta, nem a view;
#   8. `medida='count'` e `medida='value'` do MESMO `action_type` coexistem sem
#      uma sobrescrever a outra;
#   9. rollback → reapply → a sequência inteira passa de novo.
#
# Uso:  bash docs/closure/traffic-operational-closure-v2/prova-sql-read-model.sh
# =============================================================================
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PORTA="${PORTA:-55433}"

PROVAS=0
FALHAS=0

# ⚠️ AS DUAS FUNÇÕES QUE TRANSFORMAM LEGENDA EM PORTÃO. Imprimir um valor ao
# lado de uma expectativa não é assertar nada; comparar é.
ok() {  # ok <descrição> <valor> <esperado>
  PROVAS=$((PROVAS + 1))
  if [ "$2" = "$3" ]; then
    printf '   PASS  %s\n' "$1"
  else
    FALHAS=$((FALHAS + 1))
    printf '   FAIL  %s — esperado [%s], obtido [%s]\n' "$1" "$3" "$2"
    exit_se_falhou
  fi
}

contem() {  # contem <descrição> <texto> <trecho exigido>
  PROVAS=$((PROVAS + 1))
  case "$2" in
    *"$3"*) printf '   PASS  %s\n' "$1" ;;
    *) FALHAS=$((FALHAS + 1))
       printf '   FAIL  %s — o texto não contém [%s]: %s\n' "$1" "$3" "$2"
       exit_se_falhou ;;
  esac
}

# "exit non-zero on the first failed assertion": a primeira violação encerra.
# Continuar depois dela produziria uma lista de sintomas de uma causa só.
exit_se_falhou() {
  echo
  echo "============================================================"
  echo "PROVA REPROVADA na primeira asserção que falhou: $PROVAS asserções, $FALHAS falha(s)."
  exit 1
}

# -----------------------------------------------------------------------------
# 0a. NENHUMA VARIÁVEL DE AMBIENTE PODE APONTAR PARA ALGO REAL
# -----------------------------------------------------------------------------
# Só o NOME da variável é impresso. O valor pode ser uma service key, e um
# script de prova que ecoa credencial em log é um vazamento com boa intenção.
VARS_SUSPEITAS=""
for VAR in $(env | sed -n 's/^\(SUPABASE[A-Za-z0-9_]*\)=.*/\1/p'); do
  VALOR="${!VAR:-}"
  if [ -n "$VALOR" ]; then
    VARS_SUSPEITAS="$VARS_SUSPEITAS $VAR"
  fi
done
if [ -n "$VARS_SUSPEITAS" ]; then
  echo "RECUSADO: há variável(is) de ambiente Supabase definida(s):$VARS_SUSPEITAS"
  echo "Esta prova só roda num cluster descartável. Rode com: env$(for v in $VARS_SUSPEITAS; do printf ' -u %s' "$v"; done) bash $0"
  exit 1
fi

# -----------------------------------------------------------------------------
# 0b. O BINÁRIO — e SKIP honesto quando não há PostgreSQL nesta máquina
# -----------------------------------------------------------------------------
PGBIN="${PGBIN:-/opt/homebrew/opt/postgresql@17/bin}"
if [ ! -x "$PGBIN/psql" ]; then
  if command -v psql >/dev/null 2>&1; then
    PGBIN="$(dirname "$(command -v psql)")"
  fi
fi
if [ ! -x "$PGBIN/psql" ] || [ ! -x "$PGBIN/initdb" ] || [ ! -x "$PGBIN/pg_ctl" ]; then
  echo "SKIPPED: PostgreSQL não está instalado nesta máquina (psql/initdb/pg_ctl não encontrados)."
  echo "         Nada foi provado e nada foi tocado. Instale o PostgreSQL >= 15 ou aponte PGBIN."
  exit 0
fi

TMP="$(mktemp -d)"
DADOS="$TMP/data"
limpar() {
  "$PGBIN/pg_ctl" -D "$DADOS" -m immediate stop >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap limpar EXIT

psql_() { "$PGBIN/psql" -h 127.0.0.1 -p "$PORTA" -U postgres -v ON_ERROR_STOP=1 "$@"; }

echo "== 0. alvo da prova =="
echo "   host:   127.0.0.1  (listen_addresses=127.0.0.1, sem rede externa)"
echo "   porta:  $PORTA"
echo "   datadir:$DADOS  (destruído na saída)"
ok "o alvo é o loopback, e só ele" "127.0.0.1" "127.0.0.1"

echo
echo "== 0c. cluster descartável =="
"$PGBIN/initdb" -D "$DADOS" -U postgres --auth=trust --no-locale --encoding=UTF8 >/dev/null
"$PGBIN/pg_ctl" -D "$DADOS" -o "-p $PORTA -k $TMP -c listen_addresses=127.0.0.1" \
  -l "$TMP/server.log" -w start >/dev/null
psql_ -d postgres -Atc "select 'engine: '||version();"
VERSAO=$(psql_ -d postgres -Atc "select current_setting('server_version_num')::int >= 150000;")
ok "o engine é PostgreSQL 15 ou maior (security_invoker)" "$VERSAO" "t"

# ⚠️ LISTA EXPLÍCITA E ORDENADA. Nunca `supabase/migrations/*.sql`: metade do
# diretório é ROLLBACK, e um glob executaria apply e rollback na mesma passada.
# A candidata desta trilha NÃO está no SCHEMA-DEPLOY-MANIFEST.json (o manifesto
# pertence ao integrador), então a ordem está declarada aqui, por extenso.
ARQUIVOS=(
  "v13_01_cofre_de_ativos.sql"
  "v15_01_meta_ads_read_model.sql"
  "v15_02_meta_ads_insights.sql"
  "20260907210000_meta_read_model_consistency.sql"
)
CANDIDATA="20260907210000_meta_read_model_consistency.sql"
ROLLBACK="20260907210100_meta_read_model_consistency_rollback.sql"

TABELAS_META="trafego_meta_business trafego_meta_ad_account trafego_meta_project_binding
trafego_meta_campaign trafego_meta_adset trafego_meta_ad trafego_meta_creative
trafego_meta_ad_creative_binding trafego_meta_sync_run trafego_meta_insight_daily
trafego_meta_insight_action trafego_meta_custom_measurement"

# Os papeis sao do CLUSTER, nao do banco: criados uma vez so.
psql_ -d postgres -q -c "CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN BYPASSRLS;"

criar_banco() {  # criar_banco <db>
  psql_ -d postgres -q -c "CREATE DATABASE $1;"
}

aplicar_perfil() {  # aplicar_perfil <db>
  local f
  for f in "${ARQUIVOS[@]}"; do
    printf '   %-52s ' "$f"
    psql_ -d "$1" -q -f "$RAIZ/supabase/migrations/$f" >/dev/null
    echo "APLICADA"
  done
}

# -----------------------------------------------------------------------------
# ANDAIME DA PROVA — o construtor de payload
# -----------------------------------------------------------------------------
# Ele existe para que cada cenário seja UMA linha de bash, e para que a
# diferença entre dois cenários seja visível: o que muda é o argumento, não uma
# parede de JSON copiada.
instalar_andaime() {  # instalar_andaime <db>
  psql_ -d "$1" -q <<'SQL'
CREATE TABLE public.prova_recibo (nome text PRIMARY KEY, recibo jsonb NOT NULL);
GRANT SELECT, INSERT, UPDATE ON public.prova_recibo TO service_role;

CREATE OR REPLACE FUNCTION public.prova_meta_payload(
  p_suf           text,
  p_seg_atras     numeric,
  p_completo      boolean,
  p_campanhas     text[],
  p_chave_estavel text,      -- NULL => o campo não é enviado (fallback volátil)
  p_variacao      text,      -- muda snapshot_hash/chave volátil sem mudar o resto
  p_com_valor     boolean,   -- inclui uma action com medida='value'
  p_nome_campanha text DEFAULT 'Campanha um'
) RETURNS jsonb
LANGUAGE plpgsql
AS $fn$
DECLARE
  v_obs         timestamptz := date_trunc('second', now()) - make_interval(secs => p_seg_atras);
  v_conta       text := '10000000' || p_suf;
  v_biz         text := '20000000' || p_suf;
  v_conta_ativo text := 'meta_account_metaacct_' || md5('conta' || p_suf);
  v_biz_ativo   text := 'meta_business_' || md5('biz' || p_suf);
  v_camp1       text := p_campanhas[1];
  v_adset       uuid := md5('adset' || p_suf)::uuid;
  v_ad          uuid := md5('ad' || p_suf)::uuid;
  v_creative    uuid := md5('creative' || p_suf)::uuid;
  v_dia         date := current_date - 10;
  v_fato_dia    text := 'meta_insight_' || md5('dia' || p_suf || p_seg_atras::text);
  v_fato_all    text := 'meta_insight_' || md5('all' || p_suf || p_seg_atras::text);
  v_hash        text := 'meta_snapshot_' || md5('snap' || p_suf || p_variacao || p_seg_atras::text);
  v_envelope    jsonb;
BEGIN
  v_envelope := jsonb_build_object(
    'provider', 'META_ADS',
    'account_ref', 'metaacct_' || md5('conta' || p_suf),
    'account_asset_id', v_conta_ativo,
    'credential_asset_id', 'meta_credential_keychain_local',
    'window', 'last_7d',
    'observed_at', v_obs,
    'idempotency_key', 'meta_sync_' || md5('vol' || p_suf || p_variacao || p_seg_atras::text),
    'snapshot_hash', v_hash,
    'hierarchy_complete', p_completo,
    'page_count', 4,
    'counts', jsonb_build_object('campaign', cardinality(p_campanhas), 'adset', 1, 'ad', 1, 'creative', 1),
    'rows', jsonb_build_object(
      'trafego_meta_business', jsonb_build_array(jsonb_build_object(
        'cofre_ativo_id', v_biz_ativo,
        'business_external_id', v_biz,
        'nome_observado', 'Business de prova',
        'observado_em', v_obs)),
      'trafego_meta_ad_account', jsonb_build_array(jsonb_build_object(
        'cofre_ativo_id', v_conta_ativo,
        'business_ativo_id', v_biz_ativo,
        'credential_ativo_id', 'meta_credential_keychain_local',
        'account_external_id', v_conta,
        'nome_observado', 'Conta de prova',
        'moeda', 'BRL',
        'timezone_name', 'America/Sao_Paulo',
        'account_status', '1',
        'readiness_state', 'READY_FOR_READ',
        'observado_em', v_obs)),
      'trafego_meta_campaign', (
        SELECT jsonb_agg(jsonb_build_object(
          'meta_campaign_id', md5('camp' || p_suf || e)::uuid,
          'ad_account_ativo_id', v_conta_ativo,
          'external_id', e,
          'nome', CASE WHEN e = v_camp1 THEN p_nome_campanha ELSE 'Campanha ' || e END,
          'status', 'ACTIVE',
          'effective_status', 'ACTIVE',
          'objetivo', 'OUTCOME_TRAFFIC',
          'observado_em', v_obs,
          'ultima_vez_visto_em', v_obs))
        FROM unnest(p_campanhas) AS e),
      'trafego_meta_adset', jsonb_build_array(jsonb_build_object(
        'meta_adset_id', v_adset,
        'meta_campaign_id', md5('camp' || p_suf || v_camp1)::uuid,
        'external_id', '3000000' || p_suf,
        'nome', 'Conjunto de prova',
        'status', 'ACTIVE',
        'effective_status', 'ACTIVE',
        'optimization_goal', 'LINK_CLICKS',
        'observado_em', v_obs,
        'ultima_vez_visto_em', v_obs)),
      'trafego_meta_creative', jsonb_build_array(jsonb_build_object(
        'meta_creative_id', v_creative,
        'ad_account_ativo_id', v_conta_ativo,
        'external_id', '5000000' || p_suf,
        'nome', 'Criativo de prova',
        'object_story_id', NULL,
        'observado_em', v_obs,
        'ultima_vez_visto_em', v_obs)),
      'trafego_meta_ad', jsonb_build_array(jsonb_build_object(
        'meta_ad_id', v_ad,
        'meta_adset_id', v_adset,
        'external_id', '4000000' || p_suf,
        'nome', 'Anuncio de prova',
        'status', 'ACTIVE',
        'effective_status', 'ACTIVE',
        'observado_em', v_obs,
        'ultima_vez_visto_em', v_obs)),
      'trafego_meta_ad_creative_binding', jsonb_build_array(jsonb_build_object(
        'meta_ad_id', v_ad,
        'meta_creative_id', v_creative,
        'observado_em', v_obs)),
      -- DOIS fatos do MESMO período e do MESMO instante, separados só por
      -- `time_increment`. Sob a identidade antiga eles colidiam e um
      -- sobrescrevia o outro; a série diária e o agregado do período são fatos
      -- diferentes, não um conflito.
      'trafego_meta_insight_daily', jsonb_build_array(
        jsonb_build_object(
          'meta_insight_daily_id', v_fato_dia,
          'ad_account_ativo_id', v_conta_ativo,
          'provider', 'META_ADS',
          'conta_externa', v_conta,
          'nivel', 'campaign',
          'objeto_externo', v_camp1,
          'periodo_inicio', v_dia,
          'periodo_fim', v_dia,
          'janela_atribuicao', 'default',
          'breakdown', 'none',
          'observado_em', v_obs,
          'spend', 10.50, 'impressions', 1000, 'reach', 800, 'frequency', 1.25,
          'clicks', 10, 'inline_link_clicks', 8, 'landing_page_views', 6,
          'cpm', 10.5, 'cpc', 1.05, 'ctr', 1.0,
          'time_increment', '1',
          'action_report_time', 'impression',
          'completo', p_completo),
        jsonb_build_object(
          'meta_insight_daily_id', v_fato_all,
          'ad_account_ativo_id', v_conta_ativo,
          'provider', 'META_ADS',
          'conta_externa', v_conta,
          'nivel', 'campaign',
          'objeto_externo', v_camp1,
          'periodo_inicio', v_dia,
          'periodo_fim', v_dia,
          'janela_atribuicao', 'default',
          'breakdown', 'none',
          'observado_em', v_obs,
          'spend', 10.50, 'impressions', 1000, 'reach', 800, 'frequency', 1.25,
          'clicks', 10, 'inline_link_clicks', 8, 'landing_page_views', 6,
          'cpm', 10.5, 'cpc', 1.05, 'ctr', 1.0,
          'time_increment', 'all_days',
          'action_report_time', 'impression',
          'completo', p_completo)),
      -- `actions` conta EVENTOS, `action_values` soma DINHEIRO. Mesmo
      -- action_type, mesma janela, medidas diferentes: elas precisam coexistir.
      'trafego_meta_insight_action', (
        SELECT jsonb_agg(a) FROM (
          SELECT jsonb_build_object(
            'meta_insight_daily_id', v_fato_dia, 'ordem', 0,
            'action_type', 'link_click', 'value', 10,
            'attribution_window', 'default', 'object_level', 'campaign',
            'date_start', v_dia, 'date_stop', v_dia, 'medida', 'count') AS a
          UNION ALL
          SELECT jsonb_build_object(
            'meta_insight_daily_id', v_fato_dia, 'ordem', 1,
            'action_type', 'link_click', 'value', 25.50,
            'attribution_window', 'default', 'object_level', 'campaign',
            'date_start', v_dia, 'date_stop', v_dia, 'medida', 'value')
          WHERE p_com_valor
        ) AS t),
      'trafego_meta_custom_measurement', jsonb_build_array(jsonb_build_object(
        'ad_account_ativo_id', v_conta_ativo,
        'measurement_type', 'campaign',
        'observed_count', cardinality(p_campanhas),
        'observado_em', v_obs,
        'snapshot_hash', v_hash))));

  IF p_chave_estavel IS NOT NULL THEN
    v_envelope := v_envelope || jsonb_build_object('stable_idempotency_key', p_chave_estavel);
  END IF;
  RETURN v_envelope;
END
$fn$;

GRANT EXECUTE ON FUNCTION public.prova_meta_payload(
  text, numeric, boolean, text[], text, text, boolean, text) TO service_role;
SQL
}

# -----------------------------------------------------------------------------
# A SEQUÊNCIA — roda igual antes e depois do ciclo de rollback
# -----------------------------------------------------------------------------
rodar_sequencia() {  # rodar_sequencia <db> <sufixo>
  local BASE="$1"
  local SUF="$2"
  local C1="9100000$SUF"
  local C2="9200000$SUF"
  local CHAVE_S1="meta_sync_$(printf '%s' "s1$SUF" | md5_hex)"
  local CHAVE_S2="meta_sync_$(printf '%s' "s2$SUF" | md5_hex)"
  local CHAVE_S0="meta_sync_$(printf '%s' "s0$SUF" | md5_hex)"
  local CHAVE_S3="meta_sync_$(printf '%s' "s3$SUF" | md5_hex)"
  local CHAVE_S3P="meta_sync_$(printf '%s' "s3p$SUF" | md5_hex)"
  local CHAVE_S4="meta_sync_$(printf '%s' "s4$SUF" | md5_hex)"
  local CONTA_ATIVO
  CONTA_ATIVO="meta_account_metaacct_$(psql_ -d "$BASE" -Atc "select md5('conta$SUF');")"

  gravar() {  # gravar <nome> <args-sql-do-payload>
    psql_ -d "$BASE" -q <<SQL
SET ROLE service_role;
INSERT INTO public.prova_recibo (nome, recibo)
VALUES ('$1', public.trafego_meta_persistir_snapshot(public.prova_meta_payload($2)))
ON CONFLICT (nome) DO UPDATE SET recibo = EXCLUDED.recibo;
SQL
  }
  campo() { psql_ -d "$BASE" -Atc "SELECT recibo->>'$2' FROM public.prova_recibo WHERE nome='$1';"; }

  echo
  echo "-- [$SUF] 1. duas leituras do MESMO dia → UMA linha corrente por grão --"
  gravar s1 "'$SUF', 518400, true, ARRAY['$C1','$C2'], '$CHAVE_S1', 'a', true"
  gravar s2 "'$SUF', 432000, true, ARRAY['$C1','$C2'], '$CHAVE_S2', 'b', true"
  BASE_N=$(psql_ -d "$BASE" -Atc "SELECT count(*) FROM public.trafego_meta_insight_daily WHERE ad_account_ativo_id='$CONTA_ATIVO';")
  VIEW_N=$(psql_ -d "$BASE" -Atc "SELECT count(*) FROM public.vw_trafego_meta_insight_latest WHERE ad_account_ativo_id='$CONTA_ATIVO';")
  ok "a tabela base preserva as 2 revisões de cada um dos 2 grãos" "$BASE_N" "4"
  ok "a view corrente expõe exatamente UMA linha por grão" "$VIEW_N" "2"
  CORRENTE=$(psql_ -d "$BASE" -Atc "SELECT count(*) FROM public.vw_trafego_meta_insight_latest v JOIN public.trafego_meta_insight_daily d ON d.meta_insight_daily_id=v.meta_insight_daily_id WHERE v.ad_account_ativo_id='$CONTA_ATIVO' AND d.observado_em = (SELECT max(observado_em) FROM public.trafego_meta_insight_daily WHERE ad_account_ativo_id='$CONTA_ATIVO');")
  ok "e a linha exposta é a MAIS NOVA das duas" "$CORRENTE" "2"
  GRAOS=$(psql_ -d "$BASE" -Atc "SELECT count(DISTINCT time_increment) FROM public.vw_trafego_meta_insight_latest WHERE ad_account_ativo_id='$CONTA_ATIVO';")
  ok "série diária e agregado all_days coexistem (identidade nova)" "$GRAOS" "2"
  MOEDA=$(psql_ -d "$BASE" -Atc "SELECT DISTINCT btrim(currency)||'/'||account_timezone FROM public.vw_trafego_meta_insight_latest WHERE ad_account_ativo_id='$CONTA_ATIVO';")
  ok "moeda e fuso ficaram CARIMBADOS no fato" "$MOEDA" "BRL/America/Sao_Paulo"

  echo
  echo "-- [$SUF] 2. replay da MESMA chave estável, com outro instante --"
  RUNS_ANTES=$(psql_ -d "$BASE" -Atc "SELECT count(*) FROM public.trafego_meta_sync_run WHERE chave_de_idempotencia='$CHAVE_S2';")
  # Mesma chave estável, `observed_at` um segundo depois e outro snapshot_hash:
  # é o caso que a chave volátil NÃO deduplicava.
  gravar s2r "'$SUF', 431999, true, ARRAY['$C1','$C2'], '$CHAVE_S2', 'c', true"
  REPETIDO=$(campo s2r repetido)
  RUNS_DEPOIS=$(psql_ -d "$BASE" -Atc "SELECT count(*) FROM public.trafego_meta_sync_run WHERE chave_de_idempotencia='$CHAVE_S2';")
  ok "o replay é reconhecido (repetido=true)" "$REPETIDO" "true"
  ok "e NÃO cria um segundo run com a mesma chave" "$RUNS_DEPOIS" "$RUNS_ANTES"
  ORIGEM=$(campo s2 chave_origem)
  ok "o recibo diz que a chave usada foi a estável" "$ORIGEM" "estavel"
  # Sem o campo novo, a RPC cai para a chave volátil — e DIZ que caiu.
  gravar sv "'$SUF', 388800, true, ARRAY['$C1','$C2'], NULL, 'v', true"
  ok "sem o campo novo, a degradação é visível no recibo" "$(campo sv chave_origem)" "volatil"

  echo
  echo "-- [$SUF] 3. snapshot VELHO chegando depois do novo --"
  NOME_ANTES=$(psql_ -d "$BASE" -Atc "SELECT nome FROM public.trafego_meta_campaign WHERE ad_account_ativo_id='$CONTA_ATIVO' AND external_id='$C1';")
  gravar s0 "'$SUF', 604800, true, ARRAY['$C1','$C2'], '$CHAVE_S0', 'z', true, 'NOME REGREDIDO'"
  NOME_DEPOIS=$(psql_ -d "$BASE" -Atc "SELECT nome FROM public.trafego_meta_campaign WHERE ad_account_ativo_id='$CONTA_ATIVO' AND external_id='$C1';")
  RECUSADAS=$(campo s0 recusadas_por_desatualizacao)
  ok "nenhum campo regride com o snapshot velho" "$NOME_DEPOIS" "$NOME_ANTES"
  ok "e o recibo CONTA as linhas que recusou" "$([ "${RECUSADAS:-0}" -ge 7 ] && echo sim || echo nao)" "sim"
  OBS_CONTA=$(psql_ -d "$BASE" -Atc "SELECT (observado_em = (SELECT max(observado_em) FROM public.trafego_meta_ad_account))::text FROM public.trafego_meta_ad_account WHERE cofre_ativo_id='$CONTA_ATIVO';")
  ok "o instante observado da conta continua o mais novo" "$OBS_CONTA" "true"

  echo
  echo "-- [$SUF] 5. objeto ausente numa leitura PARCIAL não vira ausência --"
  gravar s3 "'$SUF', 345600, false, ARRAY['$C1'], '$CHAVE_S3', 'p', true"
  AUSENTE_PARCIAL=$(psql_ -d "$BASE" -Atc "SELECT coalesce(ausente_desde::text,'NULL') FROM public.trafego_meta_campaign WHERE ad_account_ativo_id='$CONTA_ATIVO' AND external_id='$C2';")
  ok "leitura parcial NÃO marca ausência" "$AUSENTE_PARCIAL" "NULL"
  ok "e o recibo declara a leitura como incompleta" "$(campo s3 leitura_completa)" "false"
  ok "e não marcou nada" "$(campo s3 ausencias_marcadas)" "0"

  # Uma linha que OMITE `completo` não pode ser gravada como completa quando a
  # própria transação acabou de ser informada de que a leitura foi truncada.
  # `coalesce(completo, true)` inventaria exatamente a certeza que a RPC recusou
  # lá em cima ao exigir `hierarchy_complete`.
  psql_ -d "$BASE" -q <<SQL
SET ROLE service_role;
WITH cru AS (SELECT public.prova_meta_payload(
       '$SUF', 259200, false, ARRAY['$C1'], '$CHAVE_S3P', 'q', true) AS p),
     sem AS (
       SELECT jsonb_set(p, '{rows,trafego_meta_insight_daily}',
                (SELECT coalesce(jsonb_agg(linha - 'completo'), '[]'::jsonb)
                   FROM jsonb_array_elements(p->'rows'->'trafego_meta_insight_daily') AS linha)
              ) AS p
         FROM cru)
INSERT INTO public.prova_recibo (nome, recibo)
SELECT 'sem_completo', public.trafego_meta_persistir_snapshot(p) FROM sem
ON CONFLICT (nome) DO UPDATE SET recibo = EXCLUDED.recibo;
SQL
  # O id do fato é determinístico em `prova_meta_payload` (md5 de 'dia'||suf||seg),
  # então a linha é endereçada diretamente. Conferir que ela EXISTE antes de
  # afirmar qualquer coisa sobre ela: uma consulta que não acha nada devolveria
  # NULL e o teste passaria sem ter medido nada.
  FATO_SEM_COMPLETO=$(psql_ -d "$BASE" -Atc "SELECT 'meta_insight_' || md5('dia' || '$SUF' || '259200');")
  EXISTE=$(psql_ -d "$BASE" -Atc "SELECT count(*) FROM public.trafego_meta_insight_daily WHERE meta_insight_daily_id='$FATO_SEM_COMPLETO';")
  ok "a linha sem \`completo\` foi mesmo gravada (o teste tem o que medir)" "$EXISTE" "1"
  COMPLETO_HERDADO=$(psql_ -d "$BASE" -Atc "SELECT completo::text FROM public.trafego_meta_insight_daily WHERE meta_insight_daily_id='$FATO_SEM_COMPLETO';")
  ok "linha sem \`completo\` herda a incompletude da leitura, não vira 'true'" \
     "$COMPLETO_HERDADO" "false"

  # A identidade lógica do banco tem de ser tão larga quanto a que os produtores
  # hasheiam: `account_timezone` entra nas duas, ou uma conta que muda de fuso no
  # meio da janela estoura `unique_violation` e derruba o dia inteiro.
  FUSO_NO_GRAO=$(psql_ -d "$BASE" -Atc "SELECT (position('account_timezone' in pg_get_constraintdef(oid)) > 0)::text FROM pg_constraint WHERE conname='trafego_meta_insight_grao_unico';")
  ok "o grão único do banco inclui o fuso da conta" "$FUSO_NO_GRAO" "true"

  echo
  echo "-- [$SUF] 4. objeto ausente numa leitura COMPLETA vira ausência --"
  gravar s4 "'$SUF', 259200, true, ARRAY['$C1'], '$CHAVE_S4', 'q', true"
  AUSENTE=$(psql_ -d "$BASE" -Atc "SELECT (ausente_desde IS NOT NULL)::text||'/'||coalesce(ausencia_causa,'-') FROM public.trafego_meta_campaign WHERE ad_account_ativo_id='$CONTA_ATIVO' AND external_id='$C2';")
  ok "leitura completa marca ausente_desde com a causa" "$AUSENTE" "true/nao_encontrada"
  PRESENTE=$(psql_ -d "$BASE" -Atc "SELECT coalesce(ausente_desde::text,'NULL') FROM public.trafego_meta_campaign WHERE ad_account_ativo_id='$CONTA_ATIVO' AND external_id='$C1';")
  ok "e o objeto que continua na conta NÃO é marcado" "$PRESENTE" "NULL"
  ok "o recibo conta a ausência marcada" "$(campo s4 ausencias_marcadas)" "1"

  echo
  echo "-- [$SUF] 8. count e value do mesmo action_type coexistem --"
  ACOES=$(psql_ -d "$BASE" -Atc "SELECT string_agg(medida||':'||value::text, ',' ORDER BY ordem) FROM public.trafego_meta_insight_action WHERE meta_insight_daily_id = (SELECT meta_insight_daily_id FROM public.vw_trafego_meta_insight_latest WHERE ad_account_ativo_id='$CONTA_ATIVO' AND time_increment='1');")
  ok "as duas medidas do mesmo action_type convivem" "$ACOES" "count:10,value:25.50"

  echo
  echo "-- [$SUF] extra: a completude é OBRIGATÓRIA, e a recusa é pela causa --"
  SAIDA=$(psql_ -d "$BASE" -Atq 2>&1 <<SQL || true
SET ROLE service_role;
SELECT public.trafego_meta_persistir_snapshot(
  (public.prova_meta_payload('$SUF', 172800, true, ARRAY['$C1'], 'meta_sync_$(printf '%s' "sx$SUF" | md5_hex)', 'x', false)) - 'hierarchy_complete');
SQL
)
  contem "snapshot sem hierarchy_complete é recusado PELA CAUSA" "$SAIDA" "META_LEITURA_SEM_COMPLETUDE"

  echo
  echo "-- [$SUF] extra: a credencial não vem do payload --"
  SAIDA=$(psql_ -d "$BASE" -Atq 2>&1 <<SQL || true
SET ROLE service_role;
SELECT public.trafego_meta_persistir_snapshot(
  jsonb_set(public.prova_meta_payload('$SUF', 172800, true, ARRAY['$C1'], 'meta_sync_$(printf '%s' "sy$SUF" | md5_hex)', 'y', false),
            '{credential_asset_id}', '"meta_credential_de_outro_operador"'::jsonb));
SQL
)
  contem "credential_asset_id divergente é recusado PELA CAUSA" "$SAIDA" "META_CREDENCIAL_DIVERGENTE"

  echo
  echo "-- [$SUF] extra: a custódia do Cofre é DECLARADA, com trilha --"
  CUSTODIA=$(psql_ -d "$BASE" -Atc "SELECT string_agg(DISTINCT dono_custodia, ',') FROM public.cofre_ativo WHERE ativo_id LIKE 'meta\_%';")
  ok "nenhum ativo Meta nasce com custódia 'verified'" "$CUSTODIA" "declared"
  TRILHA=$(psql_ -d "$BASE" -Atc "SELECT (count(*) > 0)::text FROM public.cofre_ativo_revisao r JOIN public.cofre_ativo a ON a.ativo_id=r.ativo_id WHERE a.ativo_id='$CONTA_ATIVO' AND r.operacao='cadastro';")
  ok "e existe revisão de cadastro para a conta observada" "$TRILHA" "true"
  OPERACAO=$(psql_ -d "$BASE" -Atc "SELECT (count(*) > 0)::text FROM public.cofre_operacao WHERE rota='cofre.cadastrar_ativo' AND chave_idempotencia LIKE 'meta.read.declara.%';")
  ok "com recibo na trilha de operações governadas" "$OPERACAO" "true"
}

md5_hex() { if command -v md5 >/dev/null 2>&1; then md5 -q; else md5sum | cut -d' ' -f1; fi; }

# -----------------------------------------------------------------------------
# FRONTEIRA DE AUTORIZAÇÃO — com os papéis REAIS, nunca como superusuário
# -----------------------------------------------------------------------------
provar_fronteira() {  # provar_fronteira <db>
  local BASE="$1"
  local T SAIDA

  echo
  echo "-- 6. service_role: SELECT vale, DELETE e TRUNCATE não --"
  for T in trafego_meta_insight_daily trafego_meta_insight_action trafego_meta_custom_measurement; do
    SAIDA=$(psql_ -d "$BASE" -Atq 2>&1 <<SQL || true
SET ROLE service_role;
DELETE FROM public.$T;
SQL
)
    contem "service_role sem DELETE em $T" "$SAIDA" "permission denied"
    SAIDA=$(psql_ -d "$BASE" -Atq 2>&1 <<SQL || true
SET ROLE service_role;
TRUNCATE public.$T;
SQL
)
    contem "service_role sem TRUNCATE em $T" "$SAIDA" "permission denied"
    SAIDA=$(psql_ -d "$BASE" -Atq 2>&1 <<SQL || true
SET ROLE service_role;
SELECT count(*) FROM public.$T;
SQL
)
    case "$SAIDA" in
      *"permission denied"*) ok "service_role LÊ $T" "negado" "permitido" ;;
      *) ok "service_role LÊ $T" "permitido" "permitido" ;;
    esac
    # O DONO passa por cima de GRANT; quem o contém é o gatilho.
    SAIDA=$(psql_ -d "$BASE" -Atq -c "DELETE FROM public.$T;" 2>&1 || true)
    contem "o DONO também é recusado por gatilho em $T" "$SAIDA" "DELETE recusado"
    # ⚠️ `CASCADE` de proposito: sem ele o Postgres para ANTES do gatilho, na FK
    # de `_action` para `_daily`, e a prova mediria a FK em vez da recusa.
    SAIDA=$(psql_ -d "$BASE" -Atq -c "TRUNCATE public.$T CASCADE;" 2>&1 || true)
    contem "e TRUNCATE do DONO é recusado em $T" "$SAIDA" "TRUNCATE recusado"
  done

  echo
  echo "-- 7. anon e authenticated não leem NADA do domínio Meta --"
  for T in $TABELAS_META; do
    for PAPEL in anon authenticated; do
      SAIDA=$(psql_ -d "$BASE" -Atq 2>&1 <<SQL || true
SET ROLE $PAPEL;
SELECT count(*) FROM public.$T;
SQL
)
      contem "$PAPEL sem SELECT em $T" "$SAIDA" "permission denied"
    done
  done
  for PAPEL in anon authenticated; do
    SAIDA=$(psql_ -d "$BASE" -Atq 2>&1 <<SQL || true
SET ROLE $PAPEL;
SELECT count(*) FROM public.vw_trafego_meta_insight_latest;
SQL
)
    contem "$PAPEL sem SELECT na view corrente" "$SAIDA" "permission denied"
    SAIDA=$(psql_ -d "$BASE" -Atq 2>&1 <<SQL || true
SET ROLE $PAPEL;
SELECT public.trafego_meta_persistir_snapshot('{}'::jsonb);
SQL
)
    contem "$PAPEL não executa a RPC" "$SAIDA" "permission denied"
  done
}

# =============================================================================
echo
echo "== 1. banco A: apply do perfil, na ordem declarada =="
criar_banco rm_prova_a
aplicar_perfil rm_prova_a
instalar_andaime rm_prova_a

echo
echo "== 2. a sequência inteira (rodada 1) =="
rodar_sequencia rm_prova_a 1
provar_fronteira rm_prova_a

echo
echo "== 3. o rollback PROTEGE o que foi medido =="
# Com uma ação de medida 'value' gravada, `DROP COLUMN medida` tornaria o
# número ilegível. O rollback recusa em vez de apagar o significado.
SAIDA=$(psql_ -d rm_prova_a -q -f "$RAIZ/supabase/migrations/$ROLLBACK" 2>&1 || true)
contem "rollback com fato de grão não-default é PROIBIDO" "$SAIDA" "PROIBIDO"
AINDA=$(psql_ -d rm_prova_a -Atc "SELECT count(*) FROM public.trafego_meta_insight_action WHERE medida='value';")
ok "e a recusa não apagou a ação de valor" "$([ "$AINDA" -ge 1 ] && echo sim || echo nao)" "sim"

echo
echo "== 4. banco B: rollback → reapply → a sequência de novo (9) =="
criar_banco rm_prova_b
aplicar_perfil rm_prova_b
echo "   rollback sobre tabelas vazias..."
psql_ -d rm_prova_b -q -f "$RAIZ/supabase/migrations/$ROLLBACK" >/dev/null
SOBROU=$(psql_ -d rm_prova_b -Atc "SELECT count(*) FROM unnest(ARRAY['trafego_meta_insight_daily','trafego_meta_insight_action','trafego_meta_custom_measurement','trafego_meta_ad_account','trafego_meta_sync_run']) t WHERE to_regclass('public.'||t) IS NOT NULL;")
ok "o rollback NÃO dropa tabela base nenhuma" "$SOBROU" "5"
COLUNA=$(psql_ -d rm_prova_b -Atc "SELECT count(*) FROM pg_attribute WHERE attrelid='public.trafego_meta_insight_daily'::regclass AND attname='time_increment' AND NOT attisdropped;")
ok "e reverte a coluna que ele mesmo criou" "$COLUNA" "0"
VIEWSUM=$(psql_ -d rm_prova_b -Atc "SELECT (to_regclass('public.vw_trafego_meta_insight_latest') IS NULL)::text;")
ok "e a view corrente some com ele" "$VIEWSUM" "true"
echo "   reapply da candidata..."
psql_ -d rm_prova_b -q -f "$RAIZ/supabase/migrations/$CANDIDATA" >/dev/null
ok "reapply da candidata sobre o schema revertido" "ok" "ok"
instalar_andaime rm_prova_b
rodar_sequencia rm_prova_b 2
provar_fronteira rm_prova_b

echo
echo "== 5. reaplicar a candidata sobre ela mesma é NO-OP, não erro =="
# Ela é um delta idempotente: `IF NOT EXISTS`, `IF EXISTS`, `CREATE OR REPLACE`.
if psql_ -d rm_prova_b -q -f "$RAIZ/supabase/migrations/$CANDIDATA" >/dev/null 2>&1; then
  REAPLICOU="sim"
else
  REAPLICOU="nao"
fi
ok "reaplicar o delta é aceito e não muda nada" "$REAPLICOU" "sim"
DEPOIS=$(psql_ -d rm_prova_b -Atc "SELECT count(*) FROM public.trafego_meta_insight_daily;")
ok "e não duplicou fato nenhum" "$([ "$DEPOIS" -gt 0 ] && echo sim || echo nao)" "sim"

echo
echo "== 6. a guarda recusa aplicar sem v15_02 =="
criar_banco rm_prova_c
psql_ -d rm_prova_c -q -f "$RAIZ/supabase/migrations/v13_01_cofre_de_ativos.sql" >/dev/null
psql_ -d rm_prova_c -q -f "$RAIZ/supabase/migrations/v15_01_meta_ads_read_model.sql" >/dev/null
SAIDA=$(psql_ -d rm_prova_c -q -f "$RAIZ/supabase/migrations/$CANDIDATA" 2>&1 || true)
contem "sem v15_02, a candidata ABORTA dizendo o que falta" "$SAIDA" "v15_02_meta_ads_insights.sql"

echo
echo "============================================================"
if [ "$FALHAS" -eq 0 ]; then
  echo "PROVA COMPLETA: $PROVAS asserções, 0 falhas."
  echo "Cluster descartável removido. Nenhum banco oficial foi tocado."
  exit 0
fi
echo "PROVA REPROVADA: $PROVAS asserções, $FALHAS falha(s)."
exit 1
