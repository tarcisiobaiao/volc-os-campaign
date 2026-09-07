-- =============================================================================
-- Meta Ads read model — consistencia do fato, da ausencia e da custodia
-- =============================================================================
-- ⚠️ ARQUIVO CANDIDATO. NAO APLICADO POR ESTA DELEGACAO, EM LUGAR NENHUM.
-- ⚠️ NUNCA aplicar por glob (`supabase/migrations/*.sql`): o diretorio mistura
--    apply e rollback, e este arquivo depende de uma ORDEM. A unica execucao
--    valida e por lista explicita, com `psql`, DEPOIS de:
--
--       v13_01_cofre_de_ativos.sql
--       v15_01_meta_ads_read_model.sql
--       v15_02_meta_ads_insights.sql
--
-- v15_01 e v15_02 tambem sao CANDIDATAS: ninguem sabe se o catalogo oficial as
-- tem. Por isso este arquivo e um DELTA INCREMENTAL — `IF NOT EXISTS`,
-- `IF EXISTS`, `to_regclass`, `CREATE OR REPLACE` — e reaplicar e no-op. Ele
-- nao edita v15_01 nem v15_02 no lugar, e nao as recria: se as tabelas de
-- insight nao existirem, a guarda ABORTA dizendo qual arquivo falta, em vez de
-- criar uma segunda definicao do mesmo objeto e deixar duas verdades no
-- repositorio.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO CONSERTA (cada item foi conferido em arquivo:linha)
-- -----------------------------------------------------------------------------
--
-- 1. AUSENCIA NUNCA ERA MARCADA. v15_02:182,187,192,197,202 LIMPAM
--    `ausente_desde`/`ausencia_causa` em todo upsert, e nenhuma instrucao do
--    schema inteiro os DEFINE. Uma campanha apagada no Ads Manager ficava
--    "presente" para sempre — e um painel que soma o que esta presente somava
--    um objeto que nao existe mais. Aqui a ausencia passa a ser marcada na
--    MESMA transacao dos upserts, por escopo de conta, e SOMENTE quando a
--    leitura foi COMPLETA. Leitura parcial nao marca nada: paginacao truncada
--    e conta vazia tem a mesma forma, e adivinhar entre as duas apaga
--    inventario real.
--
-- 2. SNAPSHOT VELHO REGREDIA SNAPSHOT NOVO. Todo `DO UPDATE` de v15_02
--    (:172,177,182,187,192,197,202,207) escrevia sem comparar instantes. Uma
--    resposta atrasada da Graph sobrescrevia silenciosamente um retrato mais
--    novo. Agora cada um carrega `WHERE EXCLUDED.observado_em >= <tabela>
--    .observado_em`, e o RECIBO diz quantas linhas foram recusadas por
--    desatualizacao — porque uma recusa que ninguem conta e indistinguivel de
--    uma escrita que aconteceu.
--
-- 3. IDEMPOTENCIA ESTAVA ANCORADA NO INSTANTE DA LEITURA.
--    `read_model.py` deriva `snapshot_hash` das LINHAS, e as linhas contem
--    `observado_em`; a chave `idempotency_key` deriva do hash. Dois cliques com
--    um segundo de diferenca produzem duas chaves e dois runs — a chave nao
--    dedupe nada. Este arquivo nao pode editar o Python, entao a RPC passa a
--    ACEITAR uma chave estavel explicita. Ver o COMMENT da funcao: o campo se
--    chama `stable_idempotency_key` e NAO pode conter o instante.
--
-- 4. NAO HAVIA PROJECAO DO ATUAL. O UNIQUE de v15_02:70-79 assa `observado_em`
--    dentro da identidade: dois syncs do mesmo dia sao duas linhas, e qualquer
--    consumidor que some `spend` conta duas vezes. Nasce
--    `public.vw_trafego_meta_insight_latest`, um `DISTINCT ON` sobre o grao
--    VERDADEIRO. As revisoes historicas continuam na tabela base — nada e
--    apagado; a view apenas expoe UMA linha corrente por grao.
--
-- 5. O GRAO DO INSIGHT ESTAVA INCOMPLETO. O fato Python passou a carregar
--    `time_increment`, `action_report_time`, `fuso_da_conta`,
--    `janelas_solicitadas` e, por acao, `medida` ('count' para `actions`,
--    'value' para `action_values`). Sem `time_increment` na identidade, a serie
--    diaria e o agregado `all_days` do MESMO periodo colidiam na chave e uma
--    sobrescrevia a outra: dois fatos diferentes viravam um conflito. As
--    colunas entram, e o UNIQUE e reconstruido com elas.
--
-- 6. A CUSTODIA DO COFRE ERA FORJADA. v15_02:158-167 escrevia direto em
--    `public.cofre_ativo` com `dono_custodia='verified'`, por fora do escritor
--    governado. Uma LEITURA nao verifica custodia de nada; ela declara ter
--    visto. Ver a secao 6 mais abaixo para a decisao tomada e o porque.
--
-- 7. `credential_asset_id` VINHA DO PAYLOAD (v15_02:135) e era usado como
--    identidade (PK de `cofre_ativo`, FK de `trafego_meta_ad_account`). Dois
--    operadores com tokens diferentes colapsavam na MESMA linha de cofre.
--    Agora a credencial e resolvida NO SERVIDOR e o payload que discordar
--    levanta excecao. Identidade nunca vem de quem chama.
--
-- 8. GRANTS. v15_02:120-125 revoga de `anon`/`authenticated` e para ai. O ACL
--    default do Supabase ja tinha concedido tudo a `service_role` e a `PUBLIC`
--    por NOME — inclusive DELETE e TRUNCATE nas tres tabelas de insight. Aqui
--    o REVOKE e nominal e vem ANTES do GRANT, o GRANT e so `SELECT`, e a
--    recusa de remocao de v15_01:269-282 e estendida as tres tabelas (com
--    TRUNCATE junto, que trigger de DELETE nao pega).
--
-- 9. `search_path` INVERTIDO. v15_02:131 declara `public, pg_catalog` — public
--    PRIMEIRO, ao contrario de toda funcao irma deste repositorio. Uma funcao
--    homonima criada em `public` sequestraria a RPC `SECURITY DEFINER`. Aqui e
--    `pg_catalog, public`.
--
-- 10. `FORCE ROW LEVEL SECURITY` SEM POLICY exige que o DONO atravesse RLS. A
--     pre-condicao medida de v13_01:2155-2192 e repetida abaixo: onde ela nao
--     valer, este apply ABORTA em vez de armar uma bomba de runtime.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO NAO FAZ
-- -----------------------------------------------------------------------------
-- Nao apaga linha nenhuma. Nao dropa tabela. Nao promove custodia. Nao abre
-- nenhum caminho de ESCRITA direta: escrita continua entrando so pela RPC
-- `SECURITY DEFINER`. E nao toca em nada fora do dominio `trafego_meta_*` e da
-- API governada do Cofre.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. GUARDA — dependencias, versao, papeis e a pre-condicao de RLS
-- -----------------------------------------------------------------------------
DO $guarda$
DECLARE
  faltando  text;
  atravessa boolean;
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION
      'meta_read_model_consistency deve rodar como postgres ou supabase_admin; atual: %',
      current_user;
  END IF;

  -- A view usa `security_invoker`, que so existe a partir do PG 15. Sem ele a
  -- view leria com os privilegios do DONO e viraria exatamente o desvio de
  -- privilegio que as tabelas base existem para impedir.
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION
      'meta_read_model_consistency exige PostgreSQL 15 ou maior (security_invoker); atual: %',
      current_setting('server_version');
  END IF;

  SELECT string_agg(r, ', ' ORDER BY r) INTO faltando
    FROM unnest(ARRAY['anon','authenticated','service_role']) AS r
   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'meta_read_model_consistency exige papeis Supabase; ausentes: %', faltando;
  END IF;

  IF to_regclass('public.cofre_ativo') IS NULL
     OR to_regproc('public.cofre_cadastrar_ativo') IS NULL THEN
    RAISE EXCEPTION
      'meta_read_model_consistency depende do Cofre governado (v13_01_cofre_de_ativos.sql)';
  END IF;

  SELECT string_agg(t, ', ' ORDER BY t) INTO faltando
    FROM unnest(ARRAY[
      'trafego_meta_business','trafego_meta_ad_account','trafego_meta_campaign',
      'trafego_meta_adset','trafego_meta_ad','trafego_meta_creative',
      'trafego_meta_ad_creative_binding','trafego_meta_sync_run'
    ]) AS t
   WHERE to_regclass('public.' || t) IS NULL;
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION
      'meta_read_model_consistency depende de v15_01_meta_ads_read_model.sql; ausentes: %',
      faltando;
  END IF;

  -- ⚠️ v15_02 e CANDIDATA. Se ela nao estiver aplicada, este arquivo NAO cria
  -- as tabelas de insight: duas definicoes do mesmo objeto em dois arquivos e
  -- como se produz um schema que ninguem consegue mais conferir. Ele ABORTA e
  -- diz o que falta.
  SELECT string_agg(t, ', ' ORDER BY t) INTO faltando
    FROM unnest(ARRAY[
      'trafego_meta_insight_daily','trafego_meta_insight_action',
      'trafego_meta_custom_measurement'
    ]) AS t
   WHERE to_regclass('public.' || t) IS NULL;
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION
      'meta_read_model_consistency e um DELTA sobre v15_02_meta_ads_insights.sql; aplique-a antes. Ausentes: %',
      faltando;
  END IF;

  -- v13_01:2155-2192, repetida por inteiro e de proposito. `FORCE ROW LEVEL
  -- SECURITY` sujeita o DONO a RLS e nao existe policy nenhuma nestas tabelas.
  -- Num banco onde o dono NAO atravessa RLS, tudo aplicaria limpo e a primeira
  -- escrita governada falharia em producao — o pior momento possivel para
  -- descobrir. Medido em 01/09/2026: `postgres` nao e superusuario no Supabase
  -- self-hosted, mas tem BYPASSRLS, e e por isso que as funcoes SECURITY
  -- DEFINER funcionam sob FORCE.
  SELECT rolsuper OR rolbypassrls INTO atravessa
    FROM pg_roles WHERE rolname = current_user;
  IF NOT coalesce(atravessa, false) THEN
    RAISE EXCEPTION
      'meta_read_model_consistency exige que % atravesse RLS (rolsuper ou rolbypassrls). Sem isso, FORCE ROW LEVEL SECURITY sem policy bloquearia a propria RPC SECURITY DEFINER e toda escrita do read model falharia em runtime.',
      current_user;
  END IF;

  RAISE NOTICE 'meta_read_model_consistency: dependencias presentes, % atravessa RLS', current_user;
END
$guarda$;


-- -----------------------------------------------------------------------------
-- 1. A CREDENCIAL FIXADA NO SCHEMA (defeito 7)
-- -----------------------------------------------------------------------------
-- O id do ativo de credencial e IDENTIDADE: ele e PK em `cofre_ativo` e FK em
-- `trafego_meta_ad_account`. Identidade que vem do corpo da requisicao nao e
-- identidade, e sugestao. Dois operadores com tokens diferentes mandando o
-- mesmo `credential_asset_id` colapsavam numa linha so, e a partir dai ninguem
-- mais sabia de qual credencial veio qual leitura.
--
-- A ordem de resolucao e: (1) o que a CONTA ja registrou, que e a autoridade
-- mais forte porque foi escrita antes e nao pelo chamador desta vez; (2) esta
-- constante, para a primeira leitura de uma conta nova.
--
-- ⚠️ Isto e uma REFERENCIA, nao um segredo: o token vive no Keychain do
-- backend e nunca no banco.
CREATE OR REPLACE FUNCTION public.trafego_meta_credencial_pinada()
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = ''
AS $funcao$
  SELECT 'meta_credential_keychain_local'::text;
$funcao$;

COMMENT ON FUNCTION public.trafego_meta_credencial_pinada() IS
  'Referencia de credencial Meta fixada no schema. Nao e segredo; e a identidade que o payload nao pode escolher.';


-- -----------------------------------------------------------------------------
-- 2. AS COLUNAS QUE FALTAVAM NO GRAO DO FATO (defeito 5)
-- -----------------------------------------------------------------------------
-- `time_increment` e `action_report_time` nao sao metadado: eles MUDAM o
-- numero. `all_days` devolve UMA linha do periodo inteiro e nao e somavel com a
-- serie diaria; trocar `impression` por `conversion` MOVE gasto e resultado
-- entre dias. Guardar os dois numeros sem guardar a pergunta produz uma soma
-- silenciosamente errada.
--
-- `account_timezone` e `currency` sao COPIA do que a conta dizia NO INSTANTE do
-- snapshot, nunca um join vivo com `trafego_meta_ad_account`. Se a conta trocar
-- de moeda amanha, um join reescreveria a historia inteira de ontem.
ALTER TABLE public.trafego_meta_insight_daily
  ADD COLUMN IF NOT EXISTS time_increment     text    NOT NULL DEFAULT '1',
  ADD COLUMN IF NOT EXISTS action_report_time text    NOT NULL DEFAULT 'impression',
  ADD COLUMN IF NOT EXISTS account_timezone   text,
  ADD COLUMN IF NOT EXISTS currency           char(3),
  ADD COLUMN IF NOT EXISTS completo           boolean NOT NULL DEFAULT true;

ALTER TABLE public.trafego_meta_insight_action
  ADD COLUMN IF NOT EXISTS medida text NOT NULL DEFAULT 'count';

DO $checks$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conrelid = 'public.trafego_meta_insight_daily'::regclass
                    AND conname = 'trafego_meta_insight_time_increment_conhecido') THEN
    ALTER TABLE public.trafego_meta_insight_daily
      ADD CONSTRAINT trafego_meta_insight_time_increment_conhecido
      CHECK (time_increment IN ('1','7','28','monthly','all_days'));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conrelid = 'public.trafego_meta_insight_daily'::regclass
                    AND conname = 'trafego_meta_insight_report_time_conhecido') THEN
    ALTER TABLE public.trafego_meta_insight_daily
      ADD CONSTRAINT trafego_meta_insight_report_time_conhecido
      CHECK (action_report_time IN ('impression','conversion','mixed'));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conrelid = 'public.trafego_meta_insight_daily'::regclass
                    AND conname = 'trafego_meta_insight_timezone_util') THEN
    ALTER TABLE public.trafego_meta_insight_daily
      ADD CONSTRAINT trafego_meta_insight_timezone_util
      CHECK (account_timezone IS NULL OR btrim(account_timezone) <> '');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conrelid = 'public.trafego_meta_insight_daily'::regclass
                    AND conname = 'trafego_meta_insight_moeda_iso') THEN
    ALTER TABLE public.trafego_meta_insight_daily
      ADD CONSTRAINT trafego_meta_insight_moeda_iso
      CHECK (currency IS NULL OR currency ~ '^[A-Z]{3}$');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conrelid = 'public.trafego_meta_insight_action'::regclass
                    AND conname = 'trafego_meta_action_medida_conhecida') THEN
    ALTER TABLE public.trafego_meta_insight_action
      ADD CONSTRAINT trafego_meta_action_medida_conhecida
      CHECK (medida IN ('count','value'));
  END IF;
END
$checks$;

COMMENT ON COLUMN public.trafego_meta_insight_daily.time_increment IS
  'Incremento PEDIDO a Graph. `all_days` e uma linha agregada do periodo e nunca e somavel com a serie diaria.';
COMMENT ON COLUMN public.trafego_meta_insight_daily.action_report_time IS
  'Quando a conversao foi contada: impression | conversion | mixed. Trocar isto move numero entre dias.';
COMMENT ON COLUMN public.trafego_meta_insight_daily.account_timezone IS
  'Fuso da conta COPIADO no instante do snapshot. Nunca um join vivo: edicao posterior da conta nao reescreve historia.';
COMMENT ON COLUMN public.trafego_meta_insight_daily.currency IS
  'Moeda da conta COPIADA no instante do snapshot, pela mesma razao do fuso.';
COMMENT ON COLUMN public.trafego_meta_insight_daily.completo IS
  'Falso quando a coleta que produziu esta linha foi truncada. Zero medido e zero por truncamento tem a mesma forma sem esta coluna.';
COMMENT ON COLUMN public.trafego_meta_insight_action.medida IS
  '`count` vem de `actions` (eventos); `value` vem de `action_values` (dinheiro). Somar as duas inventa receita.';


-- -----------------------------------------------------------------------------
-- 3. A IDENTIDADE DO FATO E DA ACAO (defeito 5, continuacao)
-- -----------------------------------------------------------------------------
-- O UNIQUE antigo nao continha `time_increment` nem `action_report_time`. Um
-- pedido diario e um pedido `all_days` do MESMO periodo, lidos no MESMO
-- instante, colidiam: dois fatos diferentes eram tratados como conflito e um
-- sobrescrevia o outro. O novo UNIQUE tem MAIS colunas que o antigo, entao ele
-- e estritamente mais fraco — nao existe linha que passava antes e falha agora.
DO $identidade$
DECLARE
  r record;
  antigas constant text[] := ARRAY[
    'ad_account_ativo_id','breakdown','janela_atribuicao','nivel','objeto_externo',
    'observado_em','periodo_fim','periodo_inicio'
  ];
BEGIN
  FOR r IN
    SELECT c.conname,
           (SELECT array_agg(a.attname::text ORDER BY a.attname)
              FROM unnest(c.conkey) AS k(attnum)
              JOIN pg_attribute a
                ON a.attrelid = c.conrelid AND a.attnum = k.attnum) AS colunas
      FROM pg_constraint c
     WHERE c.conrelid = 'public.trafego_meta_insight_daily'::regclass
       AND c.contype = 'u'
  LOOP
    IF r.colunas = antigas THEN
      EXECUTE format(
        'ALTER TABLE public.trafego_meta_insight_daily DROP CONSTRAINT %I', r.conname);
      RAISE NOTICE 'identidade antiga do insight removida: %', r.conname;
    END IF;
  END LOOP;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conrelid = 'public.trafego_meta_insight_daily'::regclass
                    AND conname = 'trafego_meta_insight_grao_unico') THEN
    ALTER TABLE public.trafego_meta_insight_daily
      ADD CONSTRAINT trafego_meta_insight_grao_unico UNIQUE (
        ad_account_ativo_id, nivel, objeto_externo,
        periodo_inicio, periodo_fim, janela_atribuicao, breakdown,
        time_increment, action_report_time, observado_em);
  END IF;
END
$identidade$;

-- A PK (meta_insight_daily_id, ordem) ja separa duas acoes; o que ela NAO
-- garante e que uma linha de `action_values` nao seja numerada por cima de uma
-- de `actions` e a substitua em silencio. Esta UNIQUE torna o grao logico um
-- fato do schema, e nao uma convencao do chamador.
DO $acao_unica$
DECLARE duplicadas bigint;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conrelid = 'public.trafego_meta_insight_action'::regclass
                    AND conname = 'trafego_meta_action_grao_unico') THEN
    SELECT count(*) INTO duplicadas FROM (
      SELECT 1 FROM public.trafego_meta_insight_action
       GROUP BY meta_insight_daily_id, action_type, attribution_window, medida
      HAVING count(*) > 1) AS d;
    IF duplicadas > 0 THEN
      RAISE EXCEPTION
        'ha % grao(s) de action duplicado(s) em trafego_meta_insight_action; resolva para frente antes de aplicar (nao apague historico as cegas)',
        duplicadas;
    END IF;
    ALTER TABLE public.trafego_meta_insight_action
      ADD CONSTRAINT trafego_meta_action_grao_unico
      UNIQUE (meta_insight_daily_id, action_type, attribution_window, medida);
  END IF;
END
$acao_unica$;


-- -----------------------------------------------------------------------------
-- 4. A PROJECAO DO ATUAL (defeito 4)
-- -----------------------------------------------------------------------------
-- A tabela base guarda TODA revisao: dois syncs do mesmo dia sao duas linhas, e
-- isso e correto — apagar a leitura anterior apagaria a prova de que o numero
-- mudou. O que estava errado era nao existir lugar nenhum que dissesse qual das
-- duas e a corrente. Somar a tabela base conta duas vezes.
CREATE INDEX IF NOT EXISTS trafego_meta_insight_grao_corrente_ix
  ON public.trafego_meta_insight_daily (
    ad_account_ativo_id, nivel, objeto_externo,
    periodo_inicio, periodo_fim, janela_atribuicao, breakdown,
    time_increment, action_report_time, observado_em DESC);

DROP VIEW IF EXISTS public.vw_trafego_meta_insight_latest;

-- `security_invoker = true` de proposito: sem ele a view leria com os
-- privilegios do DONO e viraria uma porta lateral para qualquer papel que
-- ganhasse SELECT nela por acidente. Com ele, quem le a view precisa poder ler
-- a tabela base — e `anon`/`authenticated` nao podem.
CREATE VIEW public.vw_trafego_meta_insight_latest
WITH (security_invoker = true) AS
SELECT DISTINCT ON (
    d.ad_account_ativo_id, d.nivel, d.objeto_externo,
    d.periodo_inicio, d.periodo_fim, d.janela_atribuicao, d.breakdown,
    d.time_increment, d.action_report_time)
  d.meta_insight_daily_id,
  d.ad_account_ativo_id,
  d.provider,
  d.conta_externa,
  d.nivel,
  d.objeto_externo,
  d.periodo_inicio,
  d.periodo_fim,
  d.janela_atribuicao,
  d.breakdown,
  d.time_increment,
  d.action_report_time,
  d.account_timezone,
  d.currency,
  d.completo,
  d.observado_em,
  d.spend,
  d.impressions,
  d.reach,
  d.frequency,
  d.clicks,
  d.inline_link_clicks,
  d.landing_page_views,
  d.cpm,
  d.cpc,
  d.ctr
FROM public.trafego_meta_insight_daily d
ORDER BY
  d.ad_account_ativo_id, d.nivel, d.objeto_externo,
  d.periodo_inicio, d.periodo_fim, d.janela_atribuicao, d.breakdown,
  d.time_increment, d.action_report_time,
  d.observado_em DESC;

COMMENT ON VIEW public.vw_trafego_meta_insight_latest IS
  'UMA linha corrente por grao verdadeiro do insight (sem observado_em na identidade). As revisoes anteriores continuam na tabela base; esta view existe para que somar spend nao conte o mesmo dia duas vezes. ⚠️ reach, frequency, cpm, cpc e ctr continuam NAO ADITIVAS entre linhas.';

REVOKE ALL ON public.vw_trafego_meta_insight_latest FROM PUBLIC;
REVOKE ALL ON public.vw_trafego_meta_insight_latest FROM anon;
REVOKE ALL ON public.vw_trafego_meta_insight_latest FROM authenticated;
REVOKE ALL ON public.vw_trafego_meta_insight_latest FROM service_role;
GRANT SELECT ON public.vw_trafego_meta_insight_latest TO service_role;


-- -----------------------------------------------------------------------------
-- 5. GRANTS E RECUSA DE REMOCAO NAS TRES TABELAS DE INSIGHT (defeito 8)
-- -----------------------------------------------------------------------------
-- ⚠️ O REVOKE precisa ser NOMINAL. O ACL default do Supabase concede a cada
-- papel POR NOME; `REVOKE ... FROM PUBLIC` nao tira o que foi concedido a
-- `service_role`. v15_02 revogou de `anon` e `authenticated` e parou — e com
-- isso `service_role` ficou com DELETE e TRUNCATE nas tres tabelas de fatos.
--
-- E o GRANT que fica e so `SELECT`: a escrita entra pela RPC `SECURITY
-- DEFINER`, que roda como o dono. Dar INSERT/UPDATE direto ao backend seria
-- oferecer um caminho que pula guarda de monotonicidade, marcacao de ausencia e
-- recibo — tudo de uma vez.
CREATE OR REPLACE FUNCTION public.trafego_meta_recusa_remocao()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
  RAISE EXCEPTION
    'trafego_meta_insight e fato historico: % recusado; corrija para frente com um novo snapshot',
    TG_OP;
END
$$;

REVOKE ALL ON FUNCTION public.trafego_meta_recusa_remocao() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.trafego_meta_recusa_remocao() FROM anon;
REVOKE ALL ON FUNCTION public.trafego_meta_recusa_remocao() FROM authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_recusa_remocao() FROM service_role;

DO $seguranca$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'trafego_meta_insight_daily','trafego_meta_insight_action',
    'trafego_meta_custom_measurement'
  ] LOOP
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM service_role', t);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE  ROW LEVEL SECURITY', t);
    EXECUTE format('GRANT SELECT ON TABLE public.%I TO service_role', t);

    -- v15_01:269-282, mesmo padrao, estendido. O trigger existe para o DONO,
    -- que passa por cima de GRANT; o REVOKE acima e quem contem o backend.
    IF NOT EXISTS (
      SELECT 1 FROM pg_trigger
       WHERE tgrelid = ('public.' || t)::regclass
         AND tgname = t || '_sem_delete'
    ) THEN
      EXECUTE format(
        'CREATE TRIGGER %I BEFORE DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.trafego_meta_recusa_remocao()',
        t || '_sem_delete', t);
    END IF;

    -- ⚠️ TRUNCATE nao dispara trigger de DELETE. Sem esta linha, a recusa
    -- pareceria completa e o comando que apaga a tabela inteira passaria.
    IF NOT EXISTS (
      SELECT 1 FROM pg_trigger
       WHERE tgrelid = ('public.' || t)::regclass
         AND tgname = t || '_sem_truncate'
    ) THEN
      EXECUTE format(
        'CREATE TRIGGER %I BEFORE TRUNCATE ON public.%I FOR EACH STATEMENT EXECUTE FUNCTION public.trafego_meta_recusa_remocao()',
        t || '_sem_truncate', t);
    END IF;
  END LOOP;
END
$seguranca$;


-- -----------------------------------------------------------------------------
-- 6. O REGISTRO DECLARADO NO COFRE (defeitos 6 e 7)
-- -----------------------------------------------------------------------------
-- ## A DECISAO, e o porque dela
--
-- v15_02 escrevia direto em `cofre_ativo` com `dono_custodia='verified'`. Duas
-- coisas erradas ao mesmo tempo: (a) uma leitura nao VERIFICA custodia de nada,
-- ela declara ter visto; (b) escrever direto pula o escritor governado e, com
-- ele, a revisao e a trilha de operacao — as duas unicas coisas que permitem
-- responder depois "quem colocou este ativo aqui, quando e por que".
--
-- As duas opcoes oferecidas eram: rotear pelo escritor governado, ou nao
-- escrever `cofre_ativo` nenhum a partir da RPC.
--
-- ESCOLHI ROTEAR por `public.cofre_cadastrar_ativo(jsonb, text, uuid, text,
-- text)` — o escritor que v13_01:2272 concede a `service_role` — SEM alterar
-- sua assinatura. Duas razoes:
--
--   1. Nao escrever nao era uma opcao neutra: `trafego_meta_ad_account
--      .cofre_ativo_id` e `credential_ativo_id` sao FK para `cofre_ativo`. Sem
--      a linha do Cofre, a persistencia do read model FALHA inteira. "Nao
--      escrever" seria, na pratica, "nao persistir leitura nenhuma ate alguem
--      cadastrar tres ativos a mao" — e a pressao para consertar isso rapido
--      recriaria o INSERT direto na primeira urgencia.
--   2. Roteando, a linha nasce com trilha: `cofre_ativo_revisao` recebe o
--      snapshot montado pelo BANCO e `cofre_operacao` recebe o recibo. E o
--      unico caminho em que a existencia do ativo tem autor, motivo e data.
--
-- E o que muda de fato:
--   * `dono_custodia` = 'declared' (v13_01:436 oferece exatamente este valor
--     para este caso), NUNCA 'verified'. Promover custodia continua sendo um
--     ato humano autorizado, por `cofre_revisar_ativo` — nunca por uma leitura.
--   * `estado` = 'declared' para conta e business; 'restricted' para a
--     referencia de credencial, que e o que ela e.
--   * A funcao so CADASTRA o que ainda nao existe. Uma leitura nao revisa o
--     Cofre: se o ativo ja esta la, ela nao mexe. Observar de novo nao e um
--     fato novo sobre a custodia.
--   * O autor e uma identidade de MAQUINA fixada no schema, nao um humano
--     emprestado. A trilha precisa dizer a verdade sobre quem escreveu.
CREATE OR REPLACE FUNCTION public.trafego_meta_cofre_declarar_ativo(
  p_ativo_id     text,
  p_kind         text,
  p_cluster      text,
  p_nome         text,
  p_estado       text,
  p_criticidade  text,
  p_resumo       text,
  p_proxima_acao text,
  p_capacidades  text[],
  p_tags         text[]
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  -- Identidade de MAQUINA, fixada aqui. `cofre_ativo_revisao.autor_sub` e NOT
  -- NULL e a trilha nao aceita anonimo; emprestar o sub de um humano faria a
  -- trilha mentir sobre quem escreveu.
  c_autor_sub   constant uuid := '00000000-0000-4000-8000-6d657461ead0'::uuid;
  c_autor_email constant text := 'servico:trafego_meta_read_model';
  v_nome  text;
  v_chave text;
BEGIN
  IF EXISTS (SELECT 1 FROM public.cofre_ativo WHERE ativo_id = p_ativo_id) THEN
    RETURN false;
  END IF;

  -- Serializa duas leituras simultaneas da MESMA conta nova. Sem isto as duas
  -- veriam "nao existe" e a segunda abortaria o snapshot inteiro por
  -- unique_violation numa linha de cofre.
  PERFORM pg_advisory_xact_lock(hashtextextended('cofre:' || p_ativo_id, 1509));
  IF EXISTS (SELECT 1 FROM public.cofre_ativo WHERE ativo_id = p_ativo_id) THEN
    RETURN false;
  END IF;

  -- `cofre_ativo_nome_util` exige 2..160 caracteres. Um nome de uma letra
  -- vindo da Meta abortaria a persistencia inteira da leitura; o fallback e
  -- honesto e nao inventa nome de conta.
  v_nome := btrim(coalesce(p_nome, ''));
  IF length(v_nome) < 2 OR length(v_nome) > 160 THEN
    v_nome := 'Ativo Meta observado';
  END IF;

  -- A chave de idempotencia do Cofre tem gramatica propria
  -- (`^[A-Za-z0-9._:-]{8,120}$`) e o ativo_id pode ter ate 180 caracteres.
  -- Derivar por hash mantem a chave determinista por ativo e sempre valida.
  v_chave := 'meta.read.declara.' ||
             left(encode(sha256(convert_to(p_ativo_id, 'UTF8')), 'hex'), 32);

  PERFORM public.cofre_cadastrar_ativo(
    jsonb_build_object(
      'ativo_id',      p_ativo_id,
      'kind',          p_kind,
      'cluster',       p_cluster,
      'nome',          v_nome,
      'plataforma',    'Meta Ads',
      'estado',        p_estado,
      'criticidade',   p_criticidade,
      'resumo',        p_resumo,
      'dono_nome',     'VOLC',
      -- ⚠️ 'declared', jamais 'verified'. Uma leitura declara ter visto.
      'dono_custodia', 'declared',
      'capacidades',   to_jsonb(p_capacidades),
      'tags',          to_jsonb(p_tags),
      'proxima_acao',  p_proxima_acao),
    v_chave,
    c_autor_sub,
    c_autor_email,
    'ativo declarado por leitura somente-leitura do read model Meta Ads');
  RETURN true;
EXCEPTION WHEN unique_violation THEN
  -- Corrida perdida: outra transacao cadastrou primeiro. O objetivo era que a
  -- linha existisse, e ela existe.
  IF EXISTS (SELECT 1 FROM public.cofre_ativo WHERE ativo_id = p_ativo_id) THEN
    RETURN false;
  END IF;
  RAISE;
END
$$;

COMMENT ON FUNCTION public.trafego_meta_cofre_declarar_ativo(text,text,text,text,text,text,text,text,text[],text[]) IS
  'Cadastra no Cofre, pelo escritor governado, um ativo observado por leitura Meta — sempre com dono_custodia=declared e apenas quando ainda nao existe. Promover custodia continua sendo ato humano autorizado.';

REVOKE ALL ON FUNCTION public.trafego_meta_cofre_declarar_ativo(text,text,text,text,text,text,text,text,text[],text[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.trafego_meta_cofre_declarar_ativo(text,text,text,text,text,text,text,text,text[],text[]) FROM anon;
REVOKE ALL ON FUNCTION public.trafego_meta_cofre_declarar_ativo(text,text,text,text,text,text,text,text,text[],text[]) FROM authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_cofre_declarar_ativo(text,text,text,text,text,text,text,text,text[],text[]) FROM service_role;


-- -----------------------------------------------------------------------------
-- 7. A RPC — reescrita inteira, com as guardas que faltavam
-- -----------------------------------------------------------------------------
-- ⚠️ `search_path = pg_catalog, public` (defeito 9). v15_02 declarava
-- `public, pg_catalog`: com `public` na frente, uma funcao homonima criada em
-- `public` por qualquer papel com CREATE sequestraria uma funcao SECURITY
-- DEFINER que roda como o dono do banco.
CREATE OR REPLACE FUNCTION public.trafego_meta_persistir_snapshot(p_snapshot jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_account_asset      text := p_snapshot->>'account_asset_id';
  v_credencial_payload text := p_snapshot->>'credential_asset_id';
  v_credencial         text;
  v_snapshot_hash      text := p_snapshot->>'snapshot_hash';
  v_chave_volatil      text := p_snapshot->>'idempotency_key';
  v_chave_estavel      text := p_snapshot->>'stable_idempotency_key';
  v_chave              text;
  v_origem_chave       text;
  v_observed           timestamptz := (p_snapshot->>'observed_at')::timestamptz;
  v_window             text := p_snapshot->>'window';
  v_completo           boolean;
  v_parcialidade       jsonb;
  v_run                uuid := gen_random_uuid();
  v_moeda              text;
  v_fuso               text;
  v_entradas           bigint;
  v_gravadas           bigint;
  v_recusadas          jsonb := '{}'::jsonb;
  v_recusadas_total    bigint := 0;
  v_ausencias          jsonb := '{}'::jsonb;
  v_ausencias_total    bigint := 0;
  v_n                  bigint;
  v_anterior           uuid;
BEGIN
  -- ---------------------------------------------------------------------
  -- 7.1 autorizacao e forma do envelope
  -- ---------------------------------------------------------------------
  IF current_setting('role', true) <> 'service_role'
     AND session_user <> 'service_role'
     AND current_user <> 'service_role' THEN
    RAISE EXCEPTION 'trafego_meta_persistir_snapshot exige service_role';
  END IF;
  IF p_snapshot->>'provider' IS DISTINCT FROM 'META_ADS' THEN
    RAISE EXCEPTION 'provider invalido para snapshot Meta';
  END IF;
  IF v_account_asset IS NULL OR v_observed IS NULL THEN
    RAISE EXCEPTION 'snapshot Meta sem conta ou sem instante observado';
  END IF;
  IF v_snapshot_hash !~ '^meta_snapshot_[a-f0-9]{32}$' THEN
    RAISE EXCEPTION 'snapshot Meta sem hash canonico valido';
  END IF;

  -- ---------------------------------------------------------------------
  -- 7.2 COMPLETUDE (defeito 1) — a RPC recusa em vez de adivinhar
  -- ---------------------------------------------------------------------
  -- Marcar ausencia a partir de uma leitura truncada apaga inventario que
  -- existe. Uma pagina que faltou e uma conta que esvaziou tem exatamente a
  -- mesma forma no payload; sem uma declaracao explicita nao ha como
  -- distinguir, e adivinhar aqui e destrutivo. Entao: sem `hierarchy_complete`
  -- booleano, a RPC LEVANTA.
  IF jsonb_typeof(p_snapshot->'hierarchy_complete') IS DISTINCT FROM 'boolean' THEN
    RAISE EXCEPTION
      'META_LEITURA_SEM_COMPLETUDE: o snapshot precisa declarar hierarchy_complete (boolean). Sem ela nao ha como marcar ausencia sem inventar.';
  END IF;
  v_completo := (p_snapshot->>'hierarchy_complete')::boolean;

  -- ---------------------------------------------------------------------
  -- 7.3 IDEMPOTENCIA (defeito 3)
  -- ---------------------------------------------------------------------
  -- `idempotency_key` deriva do `snapshot_hash`, que deriva das linhas, que
  -- contem `observado_em`: dois cliques com um segundo de diferenca produzem
  -- duas chaves. A chave ESTAVEL, quando enviada, e a identidade da unidade
  -- logica de trabalho e nao contem o instante.
  IF v_chave_estavel IS NOT NULL THEN
    IF v_chave_estavel !~ '^meta_sync_[a-f0-9]{32}$' THEN
      RAISE EXCEPTION 'stable_idempotency_key fora da forma meta_sync_<32 hex>';
    END IF;
    v_chave := v_chave_estavel;
    v_origem_chave := 'estavel';
  ELSE
    -- Tolerancia deliberada, e assimetrica em relacao a 7.2: cair para a chave
    -- volatil reproduz o comportamento de hoje (um run a mais), enquanto
    -- adivinhar completude apaga dado. Perda de deduplicacao e barulho; ausencia
    -- inventada e estrago.
    IF v_chave_volatil !~ '^meta_sync_[a-f0-9]{32}$' THEN
      RAISE EXCEPTION 'snapshot Meta sem chave de idempotencia valida';
    END IF;
    v_chave := v_chave_volatil;
    v_origem_chave := 'volatil';
  END IF;

  SELECT run_id INTO v_anterior
    FROM public.trafego_meta_sync_run
   WHERE chave_de_idempotencia = v_chave AND resultado = 'ok'
   ORDER BY concluido_em DESC LIMIT 1;
  IF v_anterior IS NOT NULL THEN
    RETURN jsonb_build_object(
      'ok', true, 'repetido', true, 'run_id', v_anterior::text,
      'chave_origem', v_origem_chave,
      'leitura_completa', v_completo,
      'recusadas_por_desatualizacao', 0,
      'recusadas_por_tabela', '{}'::jsonb,
      'ausencias_marcadas', 0,
      'ausencias_por_tabela', '{}'::jsonb);
  END IF;

  -- ---------------------------------------------------------------------
  -- 7.4 CREDENCIAL RESOLVIDA NO SERVIDOR (defeito 7)
  -- ---------------------------------------------------------------------
  SELECT credential_ativo_id INTO v_credencial
    FROM public.trafego_meta_ad_account
   WHERE cofre_ativo_id = v_account_asset;
  v_credencial := coalesce(v_credencial, public.trafego_meta_credencial_pinada());

  -- O valor nao entra na mensagem: quem chamou ja sabe o que mandou, e repetir
  -- um identificador do chamador em erro so aumenta a chance de vaza-lo em log.
  IF v_credencial_payload IS NOT NULL AND v_credencial_payload <> v_credencial THEN
    RAISE EXCEPTION
      'META_CREDENCIAL_DIVERGENTE: credential_asset_id do payload discorda da credencial registrada para esta conta; identidade nao vem do chamador';
  END IF;
  IF EXISTS (
    SELECT 1
      FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_ad_account}', '[]'::jsonb))
        AS x(credential_ativo_id text)
     WHERE x.credential_ativo_id IS DISTINCT FROM v_credencial
  ) THEN
    RAISE EXCEPTION
      'META_CREDENCIAL_DIVERGENTE: linha de trafego_meta_ad_account traz outra credencial; identidade nao vem do chamador';
  END IF;

  -- ---------------------------------------------------------------------
  -- 7.5 COFRE — pelo escritor governado, custodia 'declared' (defeito 6)
  -- ---------------------------------------------------------------------
  PERFORM public.trafego_meta_cofre_declarar_ativo(
    v_credencial, 'integration', 'automation',
    'Credencial Meta local (referencia)',
    'restricted', 'critical',
    'Referencia local sanitizada; o token vive no Keychain do backend e nunca no banco.',
    'Manter o token fora do banco e usar somente por backend autorizado.',
    ARRAY['meta_read'], ARRAY['meta','keychain']);

  PERFORM public.trafego_meta_cofre_declarar_ativo(
    v_account_asset, 'meta_ad_account', 'paid_media',
    coalesce(p_snapshot #>> '{rows,trafego_meta_ad_account,0,nome_observado}', 'Conta Meta'),
    'declared', 'high',
    'Conta Meta observada por snapshot somente leitura; custodia declarada, nao verificada.',
    'Consultar o inventario persistido; habilitar escrita apenas por missao autorizada.',
    ARRAY['meta_read'], ARRAY['meta','read-model']);

  PERFORM public.trafego_meta_cofre_declarar_ativo(
    b.cofre_ativo_id, 'meta_business_portfolio', 'paid_media',
    coalesce(b.nome_observado, 'Business Meta'),
    'declared', 'high',
    'Business Meta observado por snapshot somente leitura; custodia declarada, nao verificada.',
    'Manter como contexto da conta Meta observada.',
    ARRAY['meta_read'], ARRAY['meta','business'])
  FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_business}', '[]'::jsonb))
    AS b(cofre_ativo_id text, nome_observado text);

  -- ---------------------------------------------------------------------
  -- 7.6 UPSERTS COM GUARDA DE MONOTONICIDADE (defeito 2)
  -- ---------------------------------------------------------------------
  -- Cada bloco conta o que ENTROU e o que foi GRAVADO. A diferenca sao as
  -- linhas que a guarda recusou por serem mais velhas do que o que ja esta no
  -- banco — e elas vao para o recibo. Uma recusa que ninguem conta e
  -- indistinguivel de uma escrita que aconteceu.
  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_business}', '[]'::jsonb))
      AS x(cofre_ativo_id text, business_external_id text, nome_observado text, observado_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_business
      (cofre_ativo_id, business_external_id, nome_observado, observado_em)
    SELECT cofre_ativo_id, business_external_id, nome_observado, observado_em FROM entrada
    ON CONFLICT (cofre_ativo_id) DO UPDATE
       SET nome_observado = EXCLUDED.nome_observado,
           observado_em   = EXCLUDED.observado_em,
           atualizado_em  = now()
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_business.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_business', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_ad_account}', '[]'::jsonb))
      AS x(cofre_ativo_id text, business_ativo_id text, account_external_id text,
           nome_observado text, moeda text, timezone_name text, account_status text,
           readiness_state text, observado_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_ad_account
      (cofre_ativo_id, business_ativo_id, credential_ativo_id, account_external_id,
       nome_observado, moeda, timezone_name, account_status, readiness_state,
       observado_em, ultima_leitura_ok_em)
    -- ⚠️ `v_credencial`, nunca `x.credential_ativo_id`: a coluna e FK de
    -- identidade e ela e resolvida no servidor (7.4).
    SELECT cofre_ativo_id, business_ativo_id, v_credencial, account_external_id,
           nome_observado, moeda, timezone_name, account_status, readiness_state,
           observado_em, observado_em
      FROM entrada
    ON CONFLICT (cofre_ativo_id) DO UPDATE
       SET nome_observado       = EXCLUDED.nome_observado,
           moeda                = EXCLUDED.moeda,
           timezone_name        = EXCLUDED.timezone_name,
           account_status       = EXCLUDED.account_status,
           readiness_state      = EXCLUDED.readiness_state,
           observado_em         = EXCLUDED.observado_em,
           ultima_leitura_ok_em = EXCLUDED.ultima_leitura_ok_em,
           atualizado_em        = now()
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_ad_account.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_ad_account', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_campaign}', '[]'::jsonb))
      AS x(meta_campaign_id uuid, ad_account_ativo_id text, external_id text, nome text,
           status text, effective_status text, objetivo text,
           observado_em timestamptz, ultima_vez_visto_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_campaign
      (meta_campaign_id, ad_account_ativo_id, external_id, nome, status,
       effective_status, objetivo, observado_em, ultima_vez_visto_em)
    SELECT meta_campaign_id, ad_account_ativo_id, external_id, nome, status,
           effective_status, objetivo, observado_em, ultima_vez_visto_em FROM entrada
    ON CONFLICT (ad_account_ativo_id, external_id) DO UPDATE
       SET nome                = EXCLUDED.nome,
           status              = EXCLUDED.status,
           effective_status    = EXCLUDED.effective_status,
           objetivo            = EXCLUDED.objetivo,
           observado_em        = EXCLUDED.observado_em,
           ultima_vez_visto_em = EXCLUDED.ultima_vez_visto_em,
           ausente_desde       = NULL,
           ausencia_causa      = NULL,
           atualizado_em       = now()
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_campaign.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_campaign', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_adset}', '[]'::jsonb))
      AS x(meta_adset_id uuid, meta_campaign_id uuid, external_id text, nome text,
           status text, effective_status text, optimization_goal text,
           observado_em timestamptz, ultima_vez_visto_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_adset
      (meta_adset_id, meta_campaign_id, external_id, nome, status,
       effective_status, optimization_goal, observado_em, ultima_vez_visto_em)
    SELECT meta_adset_id, meta_campaign_id, external_id, nome, status,
           effective_status, optimization_goal, observado_em, ultima_vez_visto_em FROM entrada
    ON CONFLICT (meta_campaign_id, external_id) DO UPDATE
       SET nome                = EXCLUDED.nome,
           status              = EXCLUDED.status,
           effective_status    = EXCLUDED.effective_status,
           optimization_goal   = EXCLUDED.optimization_goal,
           observado_em        = EXCLUDED.observado_em,
           ultima_vez_visto_em = EXCLUDED.ultima_vez_visto_em,
           ausente_desde       = NULL,
           ausencia_causa      = NULL,
           atualizado_em       = now()
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_adset.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_adset', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_creative}', '[]'::jsonb))
      AS x(meta_creative_id uuid, ad_account_ativo_id text, external_id text, nome text,
           object_story_id text, observado_em timestamptz, ultima_vez_visto_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_creative
      (meta_creative_id, ad_account_ativo_id, external_id, nome, object_story_id,
       observado_em, ultima_vez_visto_em)
    SELECT meta_creative_id, ad_account_ativo_id, external_id, nome, object_story_id,
           observado_em, ultima_vez_visto_em FROM entrada
    ON CONFLICT (ad_account_ativo_id, external_id) DO UPDATE
       SET nome                = EXCLUDED.nome,
           object_story_id     = EXCLUDED.object_story_id,
           observado_em        = EXCLUDED.observado_em,
           ultima_vez_visto_em = EXCLUDED.ultima_vez_visto_em,
           ausente_desde       = NULL,
           ausencia_causa      = NULL,
           atualizado_em       = now()
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_creative.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_creative', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_ad}', '[]'::jsonb))
      AS x(meta_ad_id uuid, meta_adset_id uuid, external_id text, nome text,
           status text, effective_status text,
           observado_em timestamptz, ultima_vez_visto_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_ad
      (meta_ad_id, meta_adset_id, external_id, nome, status, effective_status,
       observado_em, ultima_vez_visto_em)
    SELECT meta_ad_id, meta_adset_id, external_id, nome, status, effective_status,
           observado_em, ultima_vez_visto_em FROM entrada
    ON CONFLICT (meta_adset_id, external_id) DO UPDATE
       SET nome                = EXCLUDED.nome,
           status              = EXCLUDED.status,
           effective_status    = EXCLUDED.effective_status,
           observado_em        = EXCLUDED.observado_em,
           ultima_vez_visto_em = EXCLUDED.ultima_vez_visto_em,
           ausente_desde       = NULL,
           ausencia_causa      = NULL,
           atualizado_em       = now()
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_ad.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_ad', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_ad_creative_binding}', '[]'::jsonb))
      AS x(meta_ad_id uuid, meta_creative_id uuid, observado_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_ad_creative_binding (meta_ad_id, meta_creative_id, observado_em)
    SELECT meta_ad_id, meta_creative_id, observado_em FROM entrada
    ON CONFLICT (meta_ad_id, meta_creative_id) DO UPDATE
       SET observado_em   = EXCLUDED.observado_em,
           ausente_desde  = NULL,
           ausencia_causa = NULL
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_ad_creative_binding.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_ad_creative_binding', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  -- ---------------------------------------------------------------------
  -- 7.7 AUSENCIA, e SO com leitura completa (defeito 1)
  -- ---------------------------------------------------------------------
  -- Marca o que a conta parou de mostrar: linha que existia, nao veio neste
  -- snapshot, e cujo `ultima_vez_visto_em` e ANTERIOR a este instante. O escopo
  -- e a conta lida, nunca o banco inteiro. `ausente_desde IS NULL` preserva o
  -- PRIMEIRO instante de ausencia — remarcar toda leitura apagaria ha quanto
  -- tempo o objeto sumiu.
  IF v_completo THEN
    UPDATE public.trafego_meta_campaign c
       SET ausente_desde = v_observed, ausencia_causa = 'nao_encontrada', atualizado_em = now()
     WHERE c.ad_account_ativo_id = v_account_asset
       AND c.ausente_desde IS NULL
       AND c.ultima_vez_visto_em < v_observed;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_ausencias := v_ausencias || jsonb_build_object('trafego_meta_campaign', v_n);
    v_ausencias_total := v_ausencias_total + v_n;

    UPDATE public.trafego_meta_adset s
       SET ausente_desde = v_observed, ausencia_causa = 'nao_encontrada', atualizado_em = now()
     WHERE s.ausente_desde IS NULL
       AND s.ultima_vez_visto_em < v_observed
       AND EXISTS (SELECT 1 FROM public.trafego_meta_campaign c
                    WHERE c.meta_campaign_id = s.meta_campaign_id
                      AND c.ad_account_ativo_id = v_account_asset);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_ausencias := v_ausencias || jsonb_build_object('trafego_meta_adset', v_n);
    v_ausencias_total := v_ausencias_total + v_n;

    UPDATE public.trafego_meta_ad a
       SET ausente_desde = v_observed, ausencia_causa = 'nao_encontrada', atualizado_em = now()
     WHERE a.ausente_desde IS NULL
       AND a.ultima_vez_visto_em < v_observed
       AND EXISTS (SELECT 1
                     FROM public.trafego_meta_adset s
                     JOIN public.trafego_meta_campaign c ON c.meta_campaign_id = s.meta_campaign_id
                    WHERE s.meta_adset_id = a.meta_adset_id
                      AND c.ad_account_ativo_id = v_account_asset);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_ausencias := v_ausencias || jsonb_build_object('trafego_meta_ad', v_n);
    v_ausencias_total := v_ausencias_total + v_n;

    UPDATE public.trafego_meta_creative cr
       SET ausente_desde = v_observed, ausencia_causa = 'nao_encontrada', atualizado_em = now()
     WHERE cr.ad_account_ativo_id = v_account_asset
       AND cr.ausente_desde IS NULL
       AND cr.ultima_vez_visto_em < v_observed;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_ausencias := v_ausencias || jsonb_build_object('trafego_meta_creative', v_n);
    v_ausencias_total := v_ausencias_total + v_n;

    UPDATE public.trafego_meta_ad_creative_binding b
       SET ausente_desde = v_observed, ausencia_causa = 'nao_encontrada'
     WHERE b.ausente_desde IS NULL
       AND b.observado_em < v_observed
       AND EXISTS (SELECT 1
                     FROM public.trafego_meta_ad a
                     JOIN public.trafego_meta_adset s ON s.meta_adset_id = a.meta_adset_id
                     JOIN public.trafego_meta_campaign c ON c.meta_campaign_id = s.meta_campaign_id
                    WHERE a.meta_ad_id = b.meta_ad_id
                      AND c.ad_account_ativo_id = v_account_asset);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_ausencias := v_ausencias || jsonb_build_object('trafego_meta_ad_creative_binding', v_n);
    v_ausencias_total := v_ausencias_total + v_n;
  END IF;

  -- ---------------------------------------------------------------------
  -- 7.8 INSIGHTS — grao completo, moeda e fuso CARIMBADOS (defeito 5)
  -- ---------------------------------------------------------------------
  -- A conta acabou de ser gravada acima; ler dela agora e ler o retrato DESTE
  -- snapshot. O valor e copiado para dentro do fato, e nao consultado por join
  -- na hora do relatorio: uma edicao futura da conta nao pode reescrever o que
  -- ja foi medido.
  SELECT moeda, timezone_name INTO v_moeda, v_fuso
    FROM public.trafego_meta_ad_account
   WHERE cofre_ativo_id = v_account_asset;

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_insight_daily}', '[]'::jsonb))
      AS x(meta_insight_daily_id text, ad_account_ativo_id text, provider text,
           conta_externa text, nivel text, objeto_externo text,
           periodo_inicio date, periodo_fim date, janela_atribuicao text, breakdown text,
           observado_em timestamptz, spend numeric, impressions bigint, reach bigint,
           frequency numeric, clicks bigint, inline_link_clicks bigint,
           landing_page_views bigint, cpm numeric, cpc numeric, ctr numeric,
           time_increment text, action_report_time text, account_timezone text,
           currency text, completo boolean)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_insight_daily
      (meta_insight_daily_id, ad_account_ativo_id, provider, conta_externa, nivel,
       objeto_externo, periodo_inicio, periodo_fim, janela_atribuicao, breakdown,
       observado_em, spend, impressions, reach, frequency, clicks, inline_link_clicks,
       landing_page_views, cpm, cpc, ctr,
       time_increment, action_report_time, account_timezone, currency, completo)
    SELECT meta_insight_daily_id, ad_account_ativo_id, provider, conta_externa, nivel,
           objeto_externo, periodo_inicio, periodo_fim, janela_atribuicao, breakdown,
           observado_em, spend, impressions, reach, frequency, clicks, inline_link_clicks,
           landing_page_views, cpm, cpc, ctr,
           coalesce(time_increment, '1'),
           coalesce(action_report_time, 'impression'),
           coalesce(account_timezone, v_fuso),
           coalesce(currency, v_moeda),
           coalesce(completo, true)
      FROM entrada
    ON CONFLICT (meta_insight_daily_id) DO UPDATE
       SET spend              = EXCLUDED.spend,
           impressions        = EXCLUDED.impressions,
           reach              = EXCLUDED.reach,
           frequency          = EXCLUDED.frequency,
           clicks             = EXCLUDED.clicks,
           inline_link_clicks = EXCLUDED.inline_link_clicks,
           landing_page_views = EXCLUDED.landing_page_views,
           cpm                = EXCLUDED.cpm,
           cpc                = EXCLUDED.cpc,
           ctr                = EXCLUDED.ctr,
           time_increment     = EXCLUDED.time_increment,
           action_report_time = EXCLUDED.action_report_time,
           account_timezone   = EXCLUDED.account_timezone,
           currency           = EXCLUDED.currency,
           completo           = EXCLUDED.completo
     WHERE EXCLUDED.observado_em >= trafego_meta_insight_daily.observado_em
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_insight_daily', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  -- A PK (fato, ordem) separa duas acoes, mas nao impede que uma linha de
  -- `action_values` seja numerada por cima de uma de `actions` e a substitua em
  -- silencio — o mesmo `ordem` com outra identidade. As duas recusas abaixo
  -- transformam esse caso num erro alto em vez de numa contagem perdida.
  IF EXISTS (
    SELECT 1
      FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_insight_action}', '[]'::jsonb))
        AS x(meta_insight_daily_id text, ordem integer)
     GROUP BY x.meta_insight_daily_id, x.ordem
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION
      'META_ACTION_ORDEM_DUPLICADA: duas acoes do mesmo fato com a mesma ordem no payload; numere actions e action_values numa sequencia unica';
  END IF;
  IF EXISTS (
    SELECT 1
      FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_insight_action}', '[]'::jsonb))
        AS x(meta_insight_daily_id text, ordem integer, action_type text,
             attribution_window text, medida text)
      JOIN public.trafego_meta_insight_action a
        ON a.meta_insight_daily_id = x.meta_insight_daily_id AND a.ordem = x.ordem
     WHERE (a.action_type, a.attribution_window, a.medida)
        IS DISTINCT FROM (x.action_type, x.attribution_window, coalesce(x.medida, 'count'))
  ) THEN
    RAISE EXCEPTION
      'META_ACTION_ORDEM_COLIDE: a ordem recebida reinterpretaria uma acao ja gravada com outra identidade; corrija a numeracao em vez de sobrescrever';
  END IF;

  INSERT INTO public.trafego_meta_insight_action
    (meta_insight_daily_id, ordem, action_type, value, attribution_window,
     object_level, date_start, date_stop, medida)
  SELECT meta_insight_daily_id, ordem, action_type, value, attribution_window,
         object_level, date_start, date_stop, coalesce(medida, 'count')
    FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_insight_action}', '[]'::jsonb))
      AS x(meta_insight_daily_id text, ordem integer, action_type text, value numeric,
           attribution_window text, object_level text, date_start date, date_stop date,
           medida text)
  ON CONFLICT (meta_insight_daily_id, ordem) DO UPDATE
     SET value      = EXCLUDED.value,
         date_start = EXCLUDED.date_start,
         date_stop  = EXCLUDED.date_stop,
         object_level = EXCLUDED.object_level;

  INSERT INTO public.trafego_meta_custom_measurement
    (ad_account_ativo_id, measurement_type, observed_count, observado_em, snapshot_hash)
  SELECT ad_account_ativo_id, measurement_type, observed_count, observado_em, snapshot_hash
    FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_custom_measurement}', '[]'::jsonb))
      AS x(ad_account_ativo_id text, measurement_type text, observed_count integer,
           observado_em timestamptz, snapshot_hash text)
  -- Sem guarda de monotonicidade aqui de proposito: `observado_em` faz parte da
  -- PK desta tabela, entao conflito so acontece com o MESMO instante — que e
  -- retry, nao regressao.
  ON CONFLICT (ad_account_ativo_id, measurement_type, observado_em) DO UPDATE
     SET observed_count = EXCLUDED.observed_count,
         snapshot_hash  = EXCLUDED.snapshot_hash;

  -- ---------------------------------------------------------------------
  -- 7.9 RECIBO
  -- ---------------------------------------------------------------------
  v_parcialidade := coalesce(p_snapshot->'partiality', '[]'::jsonb);
  IF jsonb_typeof(v_parcialidade) <> 'array' THEN
    v_parcialidade := '[]'::jsonb;
  END IF;
  IF NOT v_completo THEN
    v_parcialidade := v_parcialidade || jsonb_build_array(
      jsonb_build_object('escopo', 'hierarchy', 'efeito', 'ausencia_nao_marcada'));
  END IF;

  INSERT INTO public.trafego_meta_sync_run
    (run_id, ad_account_ativo_id, chave_de_idempotencia, escopo, resultado,
     iniciado_em, concluido_em, paginas_lidas, contagens, cursor_final,
     snapshot_hash, escrita_executada, parcialidade)
  VALUES (
    v_run, v_account_asset, v_chave, 'hierarchy', 'ok',
    v_observed, clock_timestamp(),
    coalesce((p_snapshot->>'page_count')::int, 0),
    coalesce(p_snapshot->'counts', '{}'::jsonb),
    jsonb_build_object(
      'window', v_window,
      'chave_origem', v_origem_chave,
      'chave_volatil', v_chave_volatil,
      'leitura_completa', v_completo,
      'recusadas_por_desatualizacao', v_recusadas,
      'ausencias_marcadas', v_ausencias),
    v_snapshot_hash, true, v_parcialidade);

  RETURN jsonb_build_object(
    'ok', true, 'repetido', false, 'run_id', v_run::text,
    'chave_origem', v_origem_chave,
    'leitura_completa', v_completo,
    'recusadas_por_desatualizacao', v_recusadas_total,
    'recusadas_por_tabela', v_recusadas,
    'ausencias_marcadas', v_ausencias_total,
    'ausencias_por_tabela', v_ausencias);

EXCEPTION WHEN unique_violation THEN
  -- Corrida de duas execucoes com a MESMA chave. So e replay se houver um run
  -- 'ok' gravado com ela; qualquer outra unique_violation continua sendo erro e
  -- sobe.
  SELECT run_id INTO v_anterior
    FROM public.trafego_meta_sync_run
   WHERE chave_de_idempotencia = v_chave AND resultado = 'ok'
   ORDER BY concluido_em DESC LIMIT 1;
  IF v_anterior IS NOT NULL THEN
    RETURN jsonb_build_object(
      'ok', true, 'repetido', true, 'run_id', v_anterior::text,
      'chave_origem', v_origem_chave,
      'leitura_completa', v_completo,
      'recusadas_por_desatualizacao', 0,
      'recusadas_por_tabela', '{}'::jsonb,
      'ausencias_marcadas', 0,
      'ausencias_por_tabela', '{}'::jsonb);
  END IF;
  RAISE;
END;
$$;

-- ⚠️ ESTE COMENTARIO E O CONTRATO. O lado Python (que esta migration NAO edita)
-- precisa passar a enviar DOIS campos no envelope de `p_snapshot`:
--
--   `hierarchy_complete`      (boolean, OBRIGATORIO)
--       Verdadeiro somente quando a hierarquia inteira da conta foi lida sem
--       truncamento — em `LeituraDaHierarquia`, quando todas as edges
--       terminaram a paginacao. Este e o unico campo que autoriza marcar
--       ausencia. Ausente ou nao-booleano => a RPC LEVANTA
--       `META_LEITURA_SEM_COMPLETUDE` e nao escreve nada.
--
--   `stable_idempotency_key`  (text, forma `^meta_sync_[a-f0-9]{32}$`)
--       A chave que NAO pode conter o instante. Derivacao recomendada:
--           'meta_sync_' + sha256(
--               'META_ADS|' + conta_externa + '|' + janela + '|' +
--               <grao logico do pedido: nivel, periodo_inicio, periodo_fim,
--                time_increment, action_report_time, breakdown,
--                janela_declarada>
--           ).hexdigest()[:32]
--       Ou seja: tudo o que descreve O QUE foi pedido, e NADA sobre QUANDO a
--       resposta chegou. `read_model.py:montar_snapshot_canonico` deriva
--       `idempotency_key` de `snapshot_hash`, que deriva das LINHAS, que contem
--       `observado_em` — por isso dois cliques com um segundo de diferenca
--       produzem duas chaves e dois runs. Enquanto o campo novo nao chegar, a
--       RPC cai para `idempotency_key` e marca `chave_origem: "volatil"` no
--       recibo, para que a degradacao seja visivel em vez de silenciosa.
--
-- As linhas de `trafego_meta_insight_daily` passam a aceitar `time_increment`,
-- `action_report_time`, `account_timezone`, `currency` e `completo`; as de
-- `trafego_meta_insight_action` aceitam `medida` ('count' | 'value'). Quando o
-- Python emitir `action_values`, `ordem` precisa continuar UNICO por fato — a
-- numeracao segue depois de `actions`, nao recomeca do zero.
COMMENT ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) IS
  'Escrita unica e transacional do snapshot Meta. Exige hierarchy_complete (boolean) para marcar ausencia; aceita stable_idempotency_key (sem o instante) para deduplicar; recusa snapshot mais velho que o gravado e diz no recibo quantas linhas recusou; resolve credential_asset_id no servidor; registra ativos no Cofre pelo escritor governado com dono_custodia=declared.';

REVOKE ALL ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) FROM anon;
REVOKE ALL ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) TO service_role;


-- -----------------------------------------------------------------------------
-- 8. CONFERENCIA FINAL — a migration se recusa a terminar meio feita
-- -----------------------------------------------------------------------------
DO $conferencia$
DECLARE
  n_colunas   int;
  n_view      int;
  n_invoker   boolean;
  n_grao      int;
  n_grao_velho int;
  n_triggers  int;
  n_delete    int;
  n_path      text[];
  t           text;
BEGIN
  SELECT count(*) INTO n_colunas FROM pg_attribute
   WHERE attrelid = 'public.trafego_meta_insight_daily'::regclass
     AND NOT attisdropped
     AND attname IN ('time_increment','action_report_time','account_timezone','currency','completo');
  IF n_colunas <> 5 THEN
    RAISE EXCEPTION 'conferencia: trafego_meta_insight_daily deveria ter as 5 colunas de grao; tem %', n_colunas;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_attribute
                  WHERE attrelid = 'public.trafego_meta_insight_action'::regclass
                    AND attname = 'medida' AND NOT attisdropped) THEN
    RAISE EXCEPTION 'conferencia: trafego_meta_insight_action.medida ausente';
  END IF;

  SELECT count(*) INTO n_grao FROM pg_constraint
   WHERE conrelid = 'public.trafego_meta_insight_daily'::regclass
     AND conname = 'trafego_meta_insight_grao_unico';
  IF n_grao <> 1 THEN
    RAISE EXCEPTION 'conferencia: identidade nova do insight ausente';
  END IF;

  SELECT count(*) INTO n_grao_velho FROM pg_constraint c
   WHERE c.conrelid = 'public.trafego_meta_insight_daily'::regclass
     AND c.contype = 'u'
     AND (SELECT array_agg(a.attname::text ORDER BY a.attname)
            FROM unnest(c.conkey) AS k(attnum)
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum)
         = ARRAY['ad_account_ativo_id','breakdown','janela_atribuicao','nivel',
                 'objeto_externo','observado_em','periodo_fim','periodo_inicio'];
  IF n_grao_velho <> 0 THEN
    RAISE EXCEPTION 'conferencia: a identidade antiga do insight continua viva';
  END IF;

  SELECT count(*) INTO n_view FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relname = 'vw_trafego_meta_insight_latest' AND c.relkind = 'v';
  IF n_view <> 1 THEN
    RAISE EXCEPTION 'conferencia: a view de projecao corrente nao existe';
  END IF;
  SELECT coalesce((SELECT option_value::boolean
                     FROM pg_options_to_table((SELECT reloptions FROM pg_class
                                                WHERE oid = 'public.vw_trafego_meta_insight_latest'::regclass))
                    WHERE option_name = 'security_invoker'), false)
    INTO n_invoker;
  IF NOT n_invoker THEN
    RAISE EXCEPTION 'conferencia: a view precisa de security_invoker=true';
  END IF;

  FOREACH t IN ARRAY ARRAY[
    'trafego_meta_insight_daily','trafego_meta_insight_action',
    'trafego_meta_custom_measurement'
  ] LOOP
    IF has_table_privilege('service_role', 'public.' || t, 'DELETE')
       OR has_table_privilege('service_role', 'public.' || t, 'TRUNCATE')
       OR has_table_privilege('service_role', 'public.' || t, 'INSERT')
       OR has_table_privilege('service_role', 'public.' || t, 'UPDATE') THEN
      RAISE EXCEPTION 'conferencia: service_role ainda escreve direto em %', t;
    END IF;
    IF NOT has_table_privilege('service_role', 'public.' || t, 'SELECT') THEN
      RAISE EXCEPTION 'conferencia: service_role precisa de SELECT em %', t;
    END IF;
    IF has_table_privilege('anon', 'public.' || t, 'SELECT')
       OR has_table_privilege('authenticated', 'public.' || t, 'SELECT') THEN
      RAISE EXCEPTION 'conferencia: anon/authenticated ainda leem %', t;
    END IF;
  END LOOP;

  SELECT count(*) INTO n_triggers FROM pg_trigger
   WHERE tgrelid IN ('public.trafego_meta_insight_daily'::regclass,
                     'public.trafego_meta_insight_action'::regclass,
                     'public.trafego_meta_custom_measurement'::regclass)
     AND NOT tgisinternal;
  IF n_triggers <> 6 THEN
    RAISE EXCEPTION 'conferencia: esperados 6 gatilhos de recusa (3 DELETE + 3 TRUNCATE); ha %', n_triggers;
  END IF;
  n_delete := n_triggers;

  SELECT p.proconfig INTO n_path FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = 'public' AND p.proname = 'trafego_meta_persistir_snapshot';
  -- ⚠️ A ORDEM e o ponto: `public` na frente deixaria uma funcao homonima em
  -- `public` sequestrar uma SECURITY DEFINER que roda como o dono do banco.
  IF NOT EXISTS (
    SELECT 1 FROM unnest(coalesce(n_path, ARRAY[]::text[])) AS c(v)
     WHERE replace(c.v, ' ', '') = 'search_path=pg_catalog,public'
  ) THEN
    RAISE EXCEPTION 'conferencia: a RPC precisa de search_path=pg_catalog, public; tem %', n_path;
  END IF;

  RAISE NOTICE 'meta_read_model_consistency: 5 colunas de grao, identidade trocada, view corrente com security_invoker, % gatilhos de recusa, grants minimos', n_delete;
END
$conferencia$;

COMMIT;
