-- Provas da v17_01 — rodam numa transação desfeita (ROLLBACK no fim).
-- Uso (banco DESCARTÁVEL com a v17_01 aplicada; nunca no oficial):
--   psql -v ON_ERROR_STOP=1 -f scripts/provas-v17_01.sql
-- Cada bloco falha com RAISE EXCEPTION se a invariante não vale.
\set QUIET on
BEGIN;

CREATE FUNCTION pg_temp.doc(familia text, chave text, origem text, dia date, linhas jsonb)
RETURNS jsonb LANGUAGE sql AS $$
  SELECT jsonb_build_object(
    'familia', familia, 'chave_idempotencia', chave, 'customer_id', '5478096539',
    'origem_janela', origem, 'janela_inicio', dia, 'janela_fim', dia, 'api_versao', 'v25',
    'contrato_versao', 'v17_01', 'contrato_sha256', repeat('c', 64),
    'iniciada_em', '2026-10-08T10:00:00Z', 'encerrada_em', '2026-10-08T10:00:05Z', 'linhas', linhas)
$$;
CREATE FUNCTION pg_temp.hora(h int, custo bigint, colhida text) RETURNS jsonb LANGUAGE sql AS $$
  SELECT jsonb_build_object('campaign_id', '24278665189', 'metric_date', '2026-10-07', 'hora', h,
    'dispositivo', 'MOBILE', 'rede', 'SEARCH', 'fuso', 'America/Sao_Paulo', 'currency_code', 'BRL',
    'colhida_em', colhida, 'impressoes', 100, 'cliques', 10, 'custo_micros', custo, 'conversoes', 1)
$$;
GRANT EXECUTE ON FUNCTION pg_temp.doc(text, text, text, date, jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION pg_temp.hora(int, bigint, text) TO service_role;
SET LOCAL ROLE service_role;

-- 1. escreve e recibo
DO $$ DECLARE r jsonb; BEGIN
  r := volc_registrar_gads_fatos(pg_temp.doc('hora_dispositivo', 'k1', 'D0', '2026-10-07',
         jsonb_build_array(pg_temp.hora(9, 1000000, '2026-10-07T12:00:00Z'), pg_temp.hora(10, 2000000, '2026-10-07T12:00:00Z'))));
  IF (r->>'aceitas')::int <> 2 OR r->>'resultado' <> 'ok' THEN RAISE EXCEPTION '1 falhou: %', r; END IF;
  IF (SELECT count(*) FROM trafego_coleta_execucao WHERE chave_idempotencia = 'k1' AND job = 'gads_hora_dispositivo') <> 1
    THEN RAISE EXCEPTION '1: recibo ausente'; END IF;
  RAISE NOTICE 'ok 1  escreve 2 fatos e 1 recibo';
END $$;

-- 2. mesma chave + mesmo conteúdo: devolve o recibo, não escreve
DO $$ DECLARE r jsonb; BEGIN
  r := volc_registrar_gads_fatos(pg_temp.doc('hora_dispositivo', 'k1', 'D0', '2026-10-07',
         jsonb_build_array(pg_temp.hora(9, 1000000, '2026-10-07T12:00:00Z'), pg_temp.hora(10, 2000000, '2026-10-07T12:00:00Z'))));
  IF (r->>'repetida')::boolean IS NOT TRUE THEN RAISE EXCEPTION '2 falhou: %', r; END IF;
  IF (SELECT count(*) FROM google_ads_fato_granular) <> 2 THEN RAISE EXCEPTION '2: escreveu de novo'; END IF;
  RAISE NOTICE 'ok 2  repetição idempotente';
END $$;

-- 3. mesma chave + conteúdo diferente: recusa
DO $$ BEGIN
  PERFORM volc_registrar_gads_fatos(pg_temp.doc('hora_dispositivo', 'k1', 'D0', '2026-10-07',
          jsonb_build_array(pg_temp.hora(9, 9999999, '2026-10-07T12:00:00Z'))));
  RAISE EXCEPTION '3 falhou: aceitou conteúdo divergente';
EXCEPTION WHEN unique_violation THEN
  RAISE NOTICE 'ok 3  chave igual com conteúdo divergente recusada';
END $$;

-- 4. precedência: D-1 substitui D0; D0 depois não rebaixa
DO $$ DECLARE r jsonb; v bigint; BEGIN
  r := volc_registrar_gads_fatos(pg_temp.doc('hora_dispositivo', 'k2', 'D-1', '2026-10-07',
         jsonb_build_array(pg_temp.hora(9, 1500000, '2026-10-08T06:00:00Z'))));
  IF (r->>'aceitas')::int <> 1 THEN RAISE EXCEPTION '4a: %', r; END IF;
  r := volc_registrar_gads_fatos(pg_temp.doc('hora_dispositivo', 'k3', 'D0', '2026-10-07',
         jsonb_build_array(pg_temp.hora(9, 7000000, '2026-10-08T09:00:00Z'))));
  IF (r->>'preteridas')::int <> 1 THEN RAISE EXCEPTION '4b: %', r; END IF;
  SELECT custo_micros INTO v FROM google_ads_fato_granular WHERE hora = 9;
  IF v <> 1500000 THEN RAISE EXCEPTION '4c: D0 rebaixou D-1 (%)', v; END IF;
  RAISE NOTICE 'ok 4  D-1 substitui D0; D0 posterior não rebaixa';
END $$;

-- 5. NULL ≠ 0
DO $$ DECLARE r jsonb; l jsonb; BEGIN
  l := pg_temp.hora(11, 0, '2026-10-07T12:00:00Z') - 'cliques';
  r := volc_registrar_gads_fatos(pg_temp.doc('hora_dispositivo', 'k4', 'D0', '2026-10-07', jsonb_build_array(l)));
  IF NOT EXISTS (SELECT 1 FROM google_ads_fato_granular WHERE hora = 11 AND cliques IS NULL AND custo_micros = 0)
    THEN RAISE EXCEPTION '5 falhou'; END IF;
  RAISE NOTICE 'ok 5  ausente fica NULL, zero medido fica 0';
END $$;

-- 6. número como string: linha rejeitada, resultado parcial / falhou
DO $$ DECLARE r jsonb; BEGIN
  r := volc_registrar_gads_fatos(pg_temp.doc('hora_dispositivo', 'k5', 'D0', '2026-10-07', jsonb_build_array(
         pg_temp.hora(12, 1, '2026-10-07T12:00:00Z'),
         jsonb_set(pg_temp.hora(13, 1, '2026-10-07T12:00:00Z'), '{custo_micros}', '"123"'))));
  IF r->>'resultado' <> 'parcial' OR (r->>'rejeitadas')::int <> 1 THEN RAISE EXCEPTION '6a: %', r; END IF;
  r := volc_registrar_gads_fatos(pg_temp.doc('hora_dispositivo', 'k6', 'D0', '2026-10-07', jsonb_build_array(
         jsonb_set(pg_temp.hora(14, 1, '2026-10-07T12:00:00Z'), '{cliques}', '""'))));
  IF r->>'resultado' <> 'falhou' THEN RAISE EXCEPTION '6b: %', r; END IF;
  RAISE NOTICE 'ok 6  string vira rejeição nomeada (parcial / falhou)';
END $$;

-- 7. dimensão obrigatória da família e data fora da janela
DO $$ DECLARE r jsonb; BEGIN
  r := volc_registrar_gads_fatos(pg_temp.doc('url', 'k7', 'D0', '2026-10-07', jsonb_build_array(
         jsonb_build_object('campaign_id', '1', 'metric_date', '2026-10-07', 'url_tipo', 'final',
                            'currency_code', 'BRL', 'colhida_em', '2026-10-07T12:00:00Z', 'cliques', 1),
         jsonb_build_object('campaign_id', '1', 'metric_date', '2026-10-01', 'url', 'https://x.com/a', 'url_tipo', 'final',
                            'currency_code', 'BRL', 'colhida_em', '2026-10-07T12:00:00Z', 'cliques', 1))));
  IF (r->>'rejeitadas')::int <> 2 THEN RAISE EXCEPTION '7: %', r; END IF;
  RAISE NOTICE 'ok 7  URL sem url e data fora da janela rejeitadas';
END $$;

-- 8. mudança: o mesmo evento não entra duas vezes; append-only
DO $$ DECLARE r jsonb; m jsonb; BEGIN
  m := jsonb_build_object('change_event_rn', 'customers/5478096539/changeEvents/1', 'ocorrido_em', '2026-10-07T15:00:00Z',
         'tipo_recurso', 'CAMPAIGN_BUDGET', 'recurso_alterado', 'customers/5478096539/campaignBudgets/9',
         'operacao', 'UPDATE', 'campaign_id', '24278665189', 'cliente', 'GOOGLE_ADS_WEB_CLIENT',
         'campos_alterados', jsonb_build_array('amount_micros'), 'colhida_em', '2026-10-08T06:00:00Z');
  r := volc_registrar_gads_fatos(pg_temp.doc('mudanca', 'k8', 'D-1', '2026-10-07', jsonb_build_array(m)));
  r := volc_registrar_gads_fatos(pg_temp.doc('mudanca', 'k9', 'D-1', '2026-10-07', jsonb_build_array(m)));
  IF (r->>'preteridas')::int <> 1 OR (SELECT count(*) FROM google_ads_mudanca) <> 1 THEN RAISE EXCEPTION '8a: %', r; END IF;
  BEGIN
    UPDATE google_ads_mudanca SET usuario = 'x';
    RAISE EXCEPTION '8b: UPDATE passou';
  EXCEPTION WHEN check_violation OR insufficient_privilege THEN NULL;
  END;
  RAISE NOTICE 'ok 8  mudança idempotente e imutável';
END $$;

-- 9. estado: só grava quando muda
DO $$ DECLARE r jsonb; e jsonb; BEGIN
  e := jsonb_build_object('entidade_tipo', 'campaign', 'entidade_id', '24278665189', 'campaign_id', '24278665189',
         'status', 'ENABLED', 'primary_status', 'LIMITED', 'primary_status_reasons', jsonb_build_array('BIDDING_STRATEGY_LEARNING'),
         'observado_em', '2026-10-08T06:00:00Z');
  r := volc_registrar_gads_fatos(pg_temp.doc('estado', 'k10', 'D0', '2026-10-08', jsonb_build_array(e)));
  r := volc_registrar_gads_fatos(pg_temp.doc('estado', 'k11', 'D0', '2026-10-08',
         jsonb_build_array(jsonb_set(e, '{observado_em}', '"2026-10-08T10:00:00Z"'))));
  IF (r->>'preteridas')::int <> 1 THEN RAISE EXCEPTION '9a: %', r; END IF;
  r := volc_registrar_gads_fatos(pg_temp.doc('estado', 'k12', 'D0', '2026-10-08',
         jsonb_build_array(jsonb_set(jsonb_set(e, '{primary_status}', '"ELIGIBLE"'), '{observado_em}', '"2026-10-08T12:00:00Z"'))));
  IF (r->>'aceitas')::int <> 1 OR (SELECT count(*) FROM google_ads_estado) <> 2 THEN RAISE EXCEPTION '9b: %', r; END IF;
  RAISE NOTICE 'ok 9  estado só entra quando muda';
END $$;

-- 10. as views cruzam custo e receita
RESET ROLE;
DO $$ DECLARE ex uuid; v record; BEGIN
  SELECT execucao_id INTO ex FROM trafego_coleta_execucao WHERE chave_idempotencia = 'k1';
  INSERT INTO google_ads_campanha_dia (customer_id, campaign_id, metric_date, segments_hash, segmentos, execucao_id,
    colhida_em, api_versao, currency_code, origem_janela, janela_fechada, precedencia, cliques, custo_micros, metricas_extras)
  VALUES ('5478096539', '24278665189', '2026-10-07', repeat('a', 64), '{}', ex, now(), 'v25', 'BRL', 'D-1', true, 2,
          30, 30000000, '{"invalid_clicks": 2}');
  -- A receita entra em USD (`revenue`); os triggers legados convertem para BRL
  -- (`revenue_converted`) pela cotação vigente. A view tem de somar o que o
  -- BANCO converteu — por isso o esperado é lido da tabela, não fixado aqui.
  INSERT INTO gam_metrics (date, utm_campaign_value, gam_accounts_id, revenue)
  VALUES ('2026-10-07', '24278665189', 'conta-teste', 5);
  INSERT INTO joinads_metrics (date, utm_campaign_value, joinads_domain, revenue)
  VALUES ('2026-10-07', '24278665189', 'x.com', 4);
  SELECT * INTO v FROM vw_gads_arbitragem_campanha_dia WHERE campaign_id = '24278665189';
  IF v.receita_gam_brl IS DISTINCT FROM (SELECT sum(revenue_converted) FROM gam_metrics
                                         WHERE utm_campaign_value = '24278665189' AND date = '2026-10-07')
     OR v.receita_joinads_brl IS DISTINCT FROM (SELECT sum(revenue_converted) FROM joinads_metrics
                                         WHERE utm_campaign_value = '24278665189' AND date = '2026-10-07')
     OR v.custo <> 30 OR v.cliques_invalidos <> 2
     OR v.lucro_brl IS DISTINCT FROM v.receita_brl - 30
     OR v.roas IS DISTINCT FROM round(v.receita_brl / 30, 4)
     OR v.receita_por_clique IS DISTINCT FROM round(v.receita_brl / 30, 4)
    THEN RAISE EXCEPTION '10a: %', row_to_json(v); END IF;
  RAISE NOTICE '   10a receita convertida pelo banco: GAM % + JoinAds % = % BRL; ROAS %',
    v.receita_gam_brl, v.receita_joinads_brl, v.receita_brl, v.roas;

  PERFORM volc_registrar_gads_fatos(pg_temp.doc('placement', 'k13', 'D-1', '2026-10-07', jsonb_build_array(
    jsonb_build_object('campaign_id', '777', 'metric_date', '2026-10-07', 'placement', 'www.Portal.com.br',
      'placement_view', 'detail', 'placement_tipo', 'WEBSITE', 'currency_code', 'BRL',
      'colhida_em', '2026-10-08T06:00:00Z', 'cliques', 5, 'custo_micros', 4000000))));
  INSERT INTO display_gam_placements (campaign_id, placement_url, revenue_brl, date)
  VALUES ('777', 'https://portal.com.br/artigo?x=1', 10, '2026-10-07');
  SELECT * INTO v FROM vw_gads_arbitragem_placement_dia WHERE campaign_id = '777';
  IF v.dominio <> 'portal.com.br' OR v.receita_brl <> 10 OR v.roas <> 2.5 THEN RAISE EXCEPTION '10b: %', row_to_json(v); END IF;

  -- hourly_stats tem FK para projects; o projeto de prova morre no ROLLBACK.
  INSERT INTO projects (id, project_name, main_url, start_date, status)
  VALUES (990001, 'prova-v17_01', 'https://prova.invalido', '2026-10-01', 'Active');
  INSERT INTO hourly_stats (project_id, campaign_id, hour_bucket, revenue)
  VALUES (990001, '24278665189', '2026-10-07 12:00:00+00', 3.5);   -- 09h em São Paulo
  SELECT * INTO v FROM vw_gads_arbitragem_hora WHERE campaign_id = '24278665189' AND hora = 9;
  IF v.receita <> 3.5 OR v.custo <> 1.5 THEN RAISE EXCEPTION '10c: %', row_to_json(v); END IF;
  RAISE NOTICE 'ok 10 views: campanha × receita convertida, placement por domínio (ROAS 2,5), hora no fuso da conta';
END $$;

-- 11. fronteira: anon e authenticated não leem nem escrevem
DO $$ BEGIN
  SET LOCAL ROLE anon;
  BEGIN PERFORM 1 FROM google_ads_fato_granular; RAISE EXCEPTION '11a: anon leu';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  SET LOCAL ROLE authenticated;
  BEGIN PERFORM volc_registrar_gads_fatos('{}'); RAISE EXCEPTION '11b: authenticated executou';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  BEGIN PERFORM 1 FROM vw_gads_arbitragem_campanha_dia; RAISE EXCEPTION '11c: authenticated leu a view';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  RESET ROLE;
  RAISE NOTICE 'ok 11 anon/authenticated recusados em tabela, view e RPC';
END $$;

-- 12. fato sem recibo não sobrevive
DO $$ BEGIN
  SET CONSTRAINTS ALL IMMEDIATE;
  INSERT INTO google_ads_fato_granular (familia, customer_id, campaign_id, metric_date, dimensao_hash, url, url_tipo,
    execucao_id, colhida_em, api_versao, currency_code, origem_janela, janela_fechada, precedencia)
  VALUES ('url', '5478096539', '1', '2026-10-07', repeat('b', 64), 'https://x.com', 'final',
          gen_random_uuid(), now(), 'v25', 'BRL', 'D0', false, 1);
  RAISE EXCEPTION '12: fato órfão aceito';
EXCEPTION WHEN foreign_key_violation THEN
  SET CONSTRAINTS ALL DEFERRED;
  RAISE NOTICE 'ok 12 fato sem recibo recusado pela FK';
END $$;

ROLLBACK;
\echo 'PROVAS v17_01 VERDES (transação desfeita)'
