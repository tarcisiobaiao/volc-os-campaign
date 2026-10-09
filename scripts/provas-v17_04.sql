-- Provas da v17_04 — só em banco DESCARTÁVEL com v17_01 e v17_04 aplicadas.
-- Tudo numa transação desfeita (ROLLBACK no fim). Cada bloco levanta se a
-- regra não vale.
\set QUIET on
BEGIN;

INSERT INTO projects (id, project_name, main_url, start_date, status) VALUES
  (990101, 'prova-v17_04-a', 'https://a.invalido', '2026-10-01', 'Active'),
  (990102, 'prova-v17_04-b', 'https://b.invalido', '2026-10-01', 'Active');
-- Campanhas legadas: é o que faz o roteador classificar GOOGLE_CAMPAIGN.
INSERT INTO campaigns (id, project_id, campaign_id, campaign_name, start_date, status) VALUES
  (990201, 990101, '222', 'prova-222', '2026-10-01', 'Active');

CREATE TEMP TABLE ctx (k text PRIMARY KEY, v uuid);
DO $$
DECLARE r jsonb;
  doc jsonb := jsonb_build_object('familia', 'url', 'customer_id', '5478096539', 'api_versao', 'v25',
    'contrato_versao', 'v17_04', 'contrato_sha256', repeat('c', 64),
    'iniciada_em', '2026-10-08T06:00:00Z', 'encerrada_em', '2026-10-08T06:00:05Z');
BEGIN
  r := volc_registrar_gads_fatos(doc || jsonb_build_object('chave_idempotencia', 'p1704-d1', 'origem_janela', 'D-1',
         'janela_inicio', '2026-10-07', 'janela_fim', '2026-10-07', 'linhas', '[]'::jsonb));
  INSERT INTO ctx VALUES ('d1', (r->>'execucao_id')::uuid);
  r := volc_registrar_gads_fatos(doc || jsonb_build_object('chave_idempotencia', 'p1704-d0', 'origem_janela', 'D0',
         'janela_inicio', '2026-10-08', 'janela_fim', '2026-10-08', 'linhas', '[]'::jsonb));
  INSERT INTO ctx VALUES ('d0', (r->>'execucao_id')::uuid);
END $$;

-- Custo campanha-dia (linha sem segmentação). 111..777 são os cenários.
INSERT INTO google_ads_campanha_dia (customer_id, campaign_id, metric_date, segments_hash, segmentos, execucao_id,
  colhida_em, api_versao, currency_code, origem_janela, janela_fechada, precedencia, cliques, custo_micros)
SELECT '5478096539', c.cid, c.dia, md5(c.cid) || md5(c.cid), '{}'::jsonb,
       (SELECT v FROM ctx WHERE k = c.janela), now(), 'v25', c.moeda,
       CASE c.janela WHEN 'd1' THEN 'D-1' ELSE 'D0' END, c.janela = 'd1', CASE c.janela WHEN 'd1' THEN 2 ELSE 1 END,
       20, 10000000
  FROM (VALUES ('111', DATE '2026-10-07', 'd1', 'BRL'), ('222', '2026-10-07', 'd1', 'BRL'),
               ('333', '2026-10-07', 'd1', 'BRL'), ('444', '2026-10-08', 'd0', 'BRL'),
               ('555', '2026-10-07', 'd1', 'USD'), ('666', '2026-10-07', 'd1', 'BRL'),
               ('777', '2026-10-07', 'd1', 'BRL')) AS c(cid, dia, janela, moeda);

-- Receita. JoinAds em 111, 222, 444, 555; dois projetos em 666.
INSERT INTO joinads_metrics (date, utm_campaign_value, joinads_domain, project_id, revenue) VALUES
  ('2026-10-07', '111', 'a.invalido', 990101, 4),
  ('2026-10-07', '222', 'a.invalido', 990101, 4),
  ('2026-10-08', '444', 'a.invalido', 990101, 4),
  ('2026-10-07', '555', 'a.invalido', 990101, 4),
  ('2026-10-07', '666', 'a.invalido', 990101, 2),
  ('2026-10-07', '666', 'b.invalido', 990102, 2);
-- GAM: 222 atribuído (GOOGLE_CAMPAIGN) → sobreposição com o JoinAds; 333 sem campanha legada → UNMATCHED.
INSERT INTO gam_metrics (date, utm_campaign_value, gam_accounts_id, project_id, revenue) VALUES
  ('2026-10-07', '222', 'conta-prova', 990101, 3),
  ('2026-10-07', '333', 'conta-prova', 990101, 3);

DO $$
DECLARE esperado jsonb := '{"111":"reconciliada_fonte_unica","222":"nao_reconciliada_sobreposicao",
  "333":"nao_reconciliada_atribuicao","444":"janela_aberta","555":"nao_reconciliada_moeda",
  "666":"nao_reconciliada_projeto","777":"sem_receita_registrada"}';
  r record;
BEGIN
  FOR r IN SELECT * FROM vw_gads_arbitragem_campanha_dia
            WHERE campaign_id IN ('111','222','333','444','555','666','777') LOOP
    IF r.receita_status <> esperado ->> r.campaign_id THEN
      RAISE EXCEPTION 'campanha %: status % (esperado %)', r.campaign_id, r.receita_status, esperado ->> r.campaign_id;
    END IF;
    IF (r.receita_status = 'reconciliada_fonte_unica') <> (r.lucro_brl IS NOT NULL) THEN
      RAISE EXCEPTION 'campanha %: lucro % com status %', r.campaign_id, r.lucro_brl, r.receita_status;
    END IF;
    IF r.utilizavel_para_otimizacao <> (r.receita_status = 'reconciliada_fonte_unica') THEN
      RAISE EXCEPTION 'campanha %: utilizavel incoerente', r.campaign_id;
    END IF;
    IF r.receita_status LIKE 'nao_reconciliada%' AND (r.receita_brl IS NOT NULL OR r.receita_rotulo <> 'receita não reconciliada') THEN
      RAISE EXCEPTION 'campanha %: receita % rotulo %', r.campaign_id, r.receita_brl, r.receita_rotulo;
    END IF;
    RAISE NOTICE 'ok %  % · receita % · lucro % · roas %', r.campaign_id, r.receita_status, r.receita_brl, r.lucro_brl, r.roas;
  END LOOP;
  IF (SELECT count(*) FROM vw_gads_arbitragem_campanha_dia WHERE campaign_id IN ('111','222','333','444','555','666','777')) <> 7 THEN
    RAISE EXCEPTION 'faltou campanha na view';
  END IF;
  -- o lucro reconciliado é receita convertida menos custo, sem soma de fontes
  IF (SELECT lucro_brl FROM vw_gads_arbitragem_campanha_dia WHERE campaign_id = '111')
     <> (SELECT revenue_converted FROM joinads_metrics WHERE utm_campaign_value = '111') - 10 THEN
    RAISE EXCEPTION 'lucro de 111 não é receita JoinAds − custo';
  END IF;
  -- os componentes continuam visíveis para reconciliação manual
  IF (SELECT receita_gam_brl IS NULL OR receita_joinads_brl IS NULL FROM vw_gads_arbitragem_campanha_dia WHERE campaign_id = '222') THEN
    RAISE EXCEPTION '222: componentes sumiram';
  END IF;
END $$;

-- Placement e hora: custo sim, receita nunca.
DO $$
DECLARE r jsonb; v record;
BEGIN
  r := volc_registrar_gads_fatos(jsonb_build_object('familia', 'placement', 'chave_idempotencia', 'p1704-pl',
    'customer_id', '5478096539', 'origem_janela', 'D-1', 'janela_inicio', '2026-10-07', 'janela_fim', '2026-10-07',
    'api_versao', 'v25', 'contrato_versao', 'v17_04', 'contrato_sha256', repeat('c', 64),
    'iniciada_em', '2026-10-08T06:00:00Z', 'encerrada_em', '2026-10-08T06:00:05Z',
    'linhas', jsonb_build_array(jsonb_build_object('campaign_id', '111', 'metric_date', '2026-10-07',
      'placement', 'www.portal.com.br', 'placement_view', 'detail', 'currency_code', 'BRL',
      'colhida_em', '2026-10-08T06:00:00Z', 'cliques', 5, 'custo_micros', 4000000))));
  r := volc_registrar_gads_fatos(jsonb_build_object('familia', 'hora_dispositivo', 'chave_idempotencia', 'p1704-hr',
    'customer_id', '5478096539', 'origem_janela', 'D-1', 'janela_inicio', '2026-10-07', 'janela_fim', '2026-10-07',
    'api_versao', 'v25', 'contrato_versao', 'v17_04', 'contrato_sha256', repeat('c', 64),
    'iniciada_em', '2026-10-08T06:00:00Z', 'encerrada_em', '2026-10-08T06:00:05Z',
    'linhas', jsonb_build_array(jsonb_build_object('campaign_id', '111', 'metric_date', '2026-10-07', 'hora', 9,
      'dispositivo', 'MOBILE', 'rede', 'CONTENT', 'fuso', 'America/Sao_Paulo', 'currency_code', 'BRL',
      'colhida_em', '2026-10-08T06:00:00Z', 'cliques', 5, 'custo_micros', 4000000))));
  INSERT INTO display_gam_placements (campaign_id, placement_url, revenue_brl, date)
  VALUES ('111', 'portal.com.br', 10, '2026-10-07');
  SELECT * INTO v FROM vw_gads_arbitragem_placement_dia WHERE campaign_id = '111';
  IF v.custo <> 4 OR v.receita_brl IS NOT NULL OR v.utilizavel_para_otimizacao THEN
    RAISE EXCEPTION 'placement inventou receita: %', row_to_json(v);
  END IF;
  SELECT * INTO v FROM vw_gads_arbitragem_hora WHERE campaign_id = '111' AND hora = 9;
  IF v.custo <> 4 OR v.receita_brl IS NOT NULL OR v.utilizavel_para_otimizacao THEN
    RAISE EXCEPTION 'hora pôs receita sem moeda: %', row_to_json(v);
  END IF;
  RAISE NOTICE 'ok placement e hora: custo 4,00 · receita NULL · não utilizável (mesmo com receita GAM por placement na tabela)';
END $$;

ROLLBACK;
\echo 'PROVAS v17_04 VERDES (transação desfeita)'
