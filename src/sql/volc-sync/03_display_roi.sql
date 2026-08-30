-- =============================================================================
-- BLOCO ............: ROI POR PLACEMENT (Display)
-- OBJETOS ..........: public.display_ads_placements   (tabela)
--                     public.display_gam_placements   (tabela)
--                     public.vw_display_roi           (view)
-- ORIGEM ...........: reconstrucao do schema do Supabase do WEBGO.
--                     NAO existe DDL versionado desses objetos em lugar nenhum;
--                     este arquivo foi reconstruido a partir de (a) spec OpenAPI
--                     do PostgREST do WEBGO, (b) amostragem de linhas reais das
--                     duas tabelas e da view, (c) codigo consumidor no repo VOLC.
-- DEPENDENCIAS .....: public.campaigns (colunas id, campaign_id, campaign_name,
--                       advertising_channel_type)  -> VERIFICADO: existe no VOLC
--                     tipo enum public.channel_type -> VERIFICADO: existe no VOLC
--                       (campaigns.advertising_channel_type ja e desse tipo)
--                     gen_random_uuid() (nucleo do PG >= 13)
-- CONSUMIDORES .....: src/hooks/useDisplayROI.ts
--                     src/types/displayROI.ts (contrato DisplayROIRow)
--                     src/components/campaign/DisplayROITable.tsx
--                     src/sql/get_placement_negation_suggestions.sql
--
-- CONTEXTO DE APLICACAO:
--   No VOLC nao ha pipeline de ingestao confirmado alimentando essas tabelas.
--   As tabelas nascem VAZIAS de proposito. A view foi escrita para retornar
--   ZERO LINHAS sem erro nesse cenario (FULL OUTER JOIN de duas tabelas vazias
--   produz 0 linhas; nenhuma agregacao / nenhum HAVING / nenhuma divisao por
--   zero e avaliada). A UI (DisplayROITable) trata array vazio com o estado
--   "Nenhum dado de ROI Display encontrado para este periodo."
--
-- O QUE E OBSERVADO x O QUE E INFERIDO  (detalhado em cada bloco abaixo):
--   OBSERVADO: nomes/ordem/tipos/formatos de todas as colunas das 3 entidades;
--              NOT NULL; DEFAULTs; ausencia de FK; chave de juncao entre as duas
--              tabelas; tipo do JOIN (FULL OUTER); LEFT JOIN com campaigns;
--              formulas de lucro_bruto, roas_pct e status_roi (com limiares).
--   INFERIDO : precisao/escala exatas dos numeric; nomes e existencia dos
--              indices; UNIQUE em (campaign_id, dominio, date); RLS/policies/
--              grants; ausencia de ORDER BY interno na view; se o CASE de
--              status_roi compara o valor bruto ou o arredondado.
--
-- SEGURANCA DO SCRIPT: idempotente e nao destrutivo.
--   Nenhum DROP TABLE / DROP COLUMN / TRUNCATE / DELETE / UPDATE.
--   Pode ser reexecutado quantas vezes for preciso.
--
-- VALIDACAO JA EXECUTADA (PostgreSQL 16 local, descartavel -- nada foi escrito
-- em nenhuma das duas instancias Supabase):
--   1. Script roda limpo do zero e roda de novo sem erro (idempotencia OK).
--   2. Ordem, nomes e tipos das 15 colunas da view batem 1:1 com o spec
--      OpenAPI do WEBGO (inclusive impressions/clicks como integer, nao bigint).
--   3. Com as tabelas vazias: SELECT * FROM vw_display_roi -> 0 linhas, sem erro.
--   4. RECONCILIACAO CONTRA O ORIGINAL: carreguei as 644 linhas reais de
--      display_ads_placements + as 165 de display_gam_placements da fatia
--      campaign_id=23281669601 / date=2026-04-17, rodei esta view e comparei
--      campo a campo com as 686 linhas que a view do WEBGO devolve para a mesma
--      fatia. Resultado: 686/686 linhas, 15/15 colunas, ZERO divergencias.
--   5. src/sql/get_placement_negation_suggestions.sql compila e executa contra
--      esta view (com dados e com a view vazia).
-- =============================================================================


-- =============================================================================
-- 1) TABELA public.display_ads_placements
--    Custo por placement (dominio) vindo do Google Ads.
--
--    OBSERVADO (spec OpenAPI do WEBGO, definitions.display_ads_placements):
--      - required = [id, campaign_id, domain, date]  -> PostgREST lista aqui as
--        colunas NOT NULL (independente de terem DEFAULT). Confirmado cruzando
--        com public.campaigns, cujo required inclui created_at (que tem
--        DEFAULT now()). Logo: as demais colunas sao NULLABLE.
--      - id            uuid,   PK, default gen_random_uuid()
--      - campaign_id   text    (SEM nota <fk/> no spec -> NAO ha FK)
--      - domain        text
--      - tipo          text    default 'WEBSITE'
--      - cost          numeric default 0
--      - conversions   numeric default 0
--      - cost_per_conv numeric default 0
--      - date          date    default CURRENT_DATE
--      - created_at    timestamptz default now()
--    OBSERVADO (linhas reais): campaign_id e o ID numerico da campanha no Google
--      Ads gravado como texto ("23281669601"); domain e o dominio limpo, sem
--      protocolo e sem "www." ("20minutos.es", "mail.google.com"); tipo assume
--      'WEBSITE' e 'GOOGLE_PRODUCTS'; cost/cost_per_conv chegam sempre com 4
--      casas ("0.0000", "128.2500") e conversions com 2 casas ("54.00").
--
--    INFERIDO: a precisao (numero total de digitos) dos numeric. A ESCALA (4 e 2)
--      e observada; a precisao 14 e um teto folgado escolhido por mim.
--    INFERIDO: nao ha CHECK em `tipo` (o spec nao expoe CHECKs; os dois valores
--      vistos convivem sem erro, mas nao consigo provar que nao existe um CHECK).
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.display_ads_placements (
  id            uuid          NOT NULL DEFAULT gen_random_uuid(),
  campaign_id   text          NOT NULL,
  domain        text          NOT NULL,
  tipo          text                   DEFAULT 'WEBSITE',
  cost          numeric(14,4)          DEFAULT 0,
  conversions   numeric(14,2)          DEFAULT 0,
  cost_per_conv numeric(14,4)          DEFAULT 0,
  date          date          NOT NULL DEFAULT CURRENT_DATE,
  created_at    timestamptz            DEFAULT now(),
  CONSTRAINT display_ads_placements_pkey PRIMARY KEY (id)
);


-- =============================================================================
-- 2) TABELA public.display_gam_placements
--    Receita por placement (URL/dominio) vinda do Google Ad Manager.
--
--    OBSERVADO (spec OpenAPI do WEBGO, definitions.display_gam_placements):
--      - required = [id, campaign_id, placement_url, date]
--      - id            uuid, PK, default gen_random_uuid()
--      - campaign_id   text  (SEM nota <fk/> -> NAO ha FK; e bom que nao tenha:
--                             a tabela do WEBGO tem 155.069 linhas com
--                             campaign_id = 'utm' e outras com 'price', lixo de
--                             um parser antigo que quebraria qualquer FK)
--      - placement_url text
--      - revenue_brl   numeric default 0
--      - revenue_usd   numeric default 0
--      - impressions   integer default 0   <- integer, NAO bigint (importante,
--      - clicks        integer default 0      ver secao 4: prova que a view nao
--                                             agrega com SUM)
--      - date          date default CURRENT_DATE
--      - created_at    timestamptz default now()
--    OBSERVADO (linhas reais recentes): campaign_id numerico e placement_url =
--      dominio limpo ("20minutos.es"), no mesmo formato de
--      display_ads_placements.domain -> e isso que permite o JOIN direto.
--      Ha tambem lixo legado (campaign_id='utm' com placement_url
--      'content=23552098018_openapps.com.br'); esse lixo NAO e tratado pela view.
--
--    INFERIDO: precisao dos numeric (escala 4 observada em revenue_brl/usd).
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.display_gam_placements (
  id            uuid          NOT NULL DEFAULT gen_random_uuid(),
  campaign_id   text          NOT NULL,
  placement_url text          NOT NULL,
  revenue_brl   numeric(14,4)          DEFAULT 0,
  revenue_usd   numeric(14,4)          DEFAULT 0,
  impressions   integer                DEFAULT 0,
  clicks        integer                DEFAULT 0,
  date          date          NOT NULL DEFAULT CURRENT_DATE,
  created_at    timestamptz            DEFAULT now(),
  CONSTRAINT display_gam_placements_pkey PRIMARY KEY (id)
);


-- =============================================================================
-- 3) INDICES
--
--    3a) UNIQUE (campaign_id, <dominio>, date)  -- INFERIDO, mas com evidencia forte
--        Evidencia:
--          (i)  Em toda fatia amostrada do WEBGO nao existe UMA duplicata dessa
--               chave. Ex.: campanha 23281669601 em 2026-04-17 -> 644 linhas em
--               display_ads_placements e 644 pares (campaign_id, domain) DISTINTOS;
--               165 linhas em display_gam_placements e 165 pares distintos.
--          (ii) Dentro da MESMA data, os created_at das linhas sao de execucoes
--               diferentes do pipeline (09:02 e 15:01 do dia 17, e 09:05 do dia
--               18, todos para date = 2026-04-17). Isso e a assinatura de um
--               UPSERT (ON CONFLICT DO UPDATE preserva o created_at original e
--               so insere placements novos). Um INSERT puro repetido teria gerado
--               duplicatas; um DELETE+INSERT teria igualado todos os created_at.
--               UPSERT exige um indice UNIQUE nessa chave -> ele existe no WEBGO.
--        RISCO SE EU ESTIVER ERRADO: se o pipeline que vier a alimentar o VOLC
--        fizer INSERT puro, ele vai falhar com 23505 (unique_violation). Nesse
--        caso, e so remover o indice:
--            DROP INDEX IF EXISTS public.ux_display_ads_placements_key;
--            DROP INDEX IF EXISTS public.ux_display_gam_placements_key;
--        (nao removo nada aqui; a instrucao acima e apenas documentacao)
--
--    3b) Indices de leitura (campaign_id, date) e (date)  -- INFERIDO
--        Motivados pelo padrao de acesso real dos consumidores:
--          useDisplayROI.ts  -> .eq('campaign_id', X).gte('date', A).lte('date', B)
--          get_placement_negation_suggestions.sql -> WHERE campaign_id = $1
--                                                    AND date >= CURRENT_DATE-14
--        Nao consigo ler pg_indexes das instancias, entao os NOMES aqui sao meus.
--        Sao inofensivos: indices adicionais nunca mudam resultado, so custo de
--        escrita.
-- =============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS ux_display_ads_placements_key
  ON public.display_ads_placements (campaign_id, domain, date);

CREATE INDEX IF NOT EXISTS ix_display_ads_placements_campaign_date
  ON public.display_ads_placements (campaign_id, date);

CREATE INDEX IF NOT EXISTS ix_display_ads_placements_date
  ON public.display_ads_placements (date);

CREATE UNIQUE INDEX IF NOT EXISTS ux_display_gam_placements_key
  ON public.display_gam_placements (campaign_id, placement_url, date);

CREATE INDEX IF NOT EXISTS ix_display_gam_placements_campaign_date
  ON public.display_gam_placements (campaign_id, date);

CREATE INDEX IF NOT EXISTS ix_display_gam_placements_date
  ON public.display_gam_placements (date);


-- =============================================================================
-- 4) VIEW public.vw_display_roi
--    Cruza custo (Google Ads) x receita (GAM) por placement/canal e data.
--
-- -----------------------------------------------------------------------------
-- 4.1 CHAVE DE JUNCAO -- este era o ponto dificil. EVIDENCIA (tudo OBSERVADO):
-- -----------------------------------------------------------------------------
--  (A) Igualdade CRUA, sem normalizacao nenhuma:
--      display_gam_placements.campaign_id   = display_ads_placements.campaign_id
--      display_gam_placements.placement_url = display_ads_placements.domain
--      display_gam_placements.date          = display_ads_placements.date
--
--      Prova positiva (linha que casa):
--        ads : campaign_id=23281669601, domain='autotest.com.ar',
--              date=2026-04-17, cost=0.0000, conversions=2.00
--        gam : campaign_id=23281669601, placement_url='autotest.com.ar',
--              date=2026-04-17, revenue_brl=1.0500, revenue_usd=0.2064,
--              impressions=10, clicks=3
--        view: canal='autotest.com.ar', investido_brl=0.0000, conversions=2.00,
--              receita_brl=1.0500, receita_usd=0.2064, impressions=10, clicks=3
--        -> os numeros do GAM chegam INTACTOS na view: 1:1, sem soma.
--
--      Prova negativa (descarta qualquer parsing de URL):
--        ads : campaign_id=23552098018, domain='openapps.com.br', 2026-04-15
--        gam : campaign_id='utm',
--              placement_url='content=23552098018_openapps.com.br', 2026-04-15,
--              revenue_brl=5.8400, impressions=114, clicks=39
--        view: canal='openapps.com.br' -> receita_brl=0, impressions=0, clicks=0
--        -> a view NAO extrai o id/dominio de dentro do 'content=...'. Se
--           extraisse, essa linha teria casado. E a linha lixo aparece SEPARADA
--           na view, com campaign_id='utm' e
--           canal='content=23552098018_openapps.com.br'.
--
--  (B) O JOIN e FULL OUTER (nao LEFT). Prova por contagem exata:
--        fatia campaign_id=23281669601 AND date=2026-04-17
--          display_ads_placements ......... 644 linhas
--          display_gam_placements ......... 165 linhas
--          intersecao das chaves .......... 123
--          so no ads ...................... 521
--          so no gam ......................  42
--          |ads UNIAO gam| ................ 686
--          vw_display_roi ................. 686 linhas  <-- BATE EXATO
--        LEFT JOIN daria 644; RIGHT daria 165; INNER daria 123. So FULL OUTER
--        da 686. E a linha 'comedera.com' (que so existe no GAM) aparece na view
--        com investido_brl=0 e conversions=0 -> confirma o lado direito orfao.
--
--  (C) As chaves da view sao COALESCE dos dois lados (consequencia do FULL OUTER):
--        campaign_id = COALESCE(a.campaign_id, g.campaign_id)
--        canal       = COALESCE(a.domain,      g.placement_url)
--        date        = COALESCE(a.date,        g.date)
--      Prova: linhas com campaign_id='utm' / 'price' existem na view e essas
--      strings so existem em display_gam_placements.campaign_id.
--
--  (D) campaigns entra por LEFT JOIN em campaigns.campaign_id (NAO inner).
--      Prova: campaign_id='utm' e campaign_id='price' NAO existem em campaigns,
--      e mesmo assim aparecem na view com
--      campaign_db_id=NULL, campaign_name=NULL, advertising_channel_type=NULL.
--      Se fosse INNER, essas 155k+ linhas sumiriam.
--
--  (E) NAO ha agregacao (nada de GROUP BY / SUM). Provas:
--        - o spec do PostgREST diz vw_display_roi.impressions = "integer".
--          SUM(integer) em PG devolve BIGINT. De fato, a view irma
--          vw_placement_roi_daily expoe impressions como "bigint". Se houvesse
--          SUM aqui, o tipo seria bigint.
--        - os valores da view sao identicos aos da linha unica de origem (4.1 A).
--        - a chave (campaign_id, dominio, date) e unica nas duas tabelas, entao
--          nem haveria o que somar.
--      Quem agrega e o front (useDisplayROI.ts soma por `canal` no cliente).
--
--  (F) NAO ha WHERE nenhum na view. Provas:
--        - linhas com tipo='GOOGLE_PRODUCTS' (domain='mail.google.com')
--          aparecem normalmente -> nao filtra por tipo.
--        - linhas de campanha inexistente ('utm','price') aparecem -> nao filtra
--          por campaigns IS NOT NULL nem por advertising_channel_type='DISPLAY'.
--        - as 644 linhas de ads da fatia testada aparecem todas -> nao filtra por
--          cost > 0 nem por conversions > 0.
--
--  (G) NAO ha ORDER BY dentro da view. -- INFERIDO (evidencia razoavel)
--      Consultas filtradas voltam em ordem nao monotonica em nenhuma coluna.
--      Alem disso os dois consumidores impoem a propria ordenacao
--      (.order('lucro_bruto') no hook; ORDER BY no final da RPC). Omitir ORDER BY
--      e tambem a opcao mais barata em plano de execucao.
--
-- -----------------------------------------------------------------------------
-- 4.2 CONTRATO DE COLUNAS -- ordem e tipos identicos ao spec do WEBGO,
--     e superconjunto do DisplayROIRow de src/types/displayROI.ts:
--        DisplayROIRow exige: campaign_id, canal, date, investido_brl,
--        conversions, receita_brl, receita_usd, impressions, clicks,
--        lucro_bruto, roas_pct, status_roi  -> TODAS presentes.
--        As 3 primeiras colunas (campaign_db_id, campaign_name,
--        advertising_channel_type) sao extras e o front simplesmente ignora
--        (ele faz select('*') e le por nome).
--        get_placement_negation_suggestions.sql exige: canal, date, roas_pct,
--        investido_brl, campaign_id -> TODAS presentes, com os mesmos tipos
--        (canal/text, date/date, roas_pct/numeric, investido_brl/numeric).
--
-- -----------------------------------------------------------------------------
-- 4.3 FORMULAS -- todas OBSERVADAS por reconciliacao numerica em linhas reais:
--        lucro_bruto = receita_brl - investido_brl
--            ex.: 2.5100 - 0.7200 = 1.7900  (a view mostra 1.7900, escala 4,
--                 ou seja SEM ROUND)
--        roas_pct    = ROUND(((receita_brl - investido_brl)
--                             / NULLIF(investido_brl,0)) * 100, 2)
--            ex.: (2.5100-0.7200)/0.7200*100 = 248.6111... -> view: 248.61
--                 (0.7800-0.3600)/0.3600*100 = 116.6666... -> view: 116.67
--            NULLIF confirmado: toda linha com investido_brl = 0 tem
--            roas_pct = NULL (e nao erro / e nao 0).
--            OBS DE NOMENCLATURA: o nome diz "ROAS" mas a formula e ROI
--            (lucro/custo), nao receita/custo. Mantido como esta porque e o que
--            o front espera: useDisplayROI.ts recalcula exatamente
--            ((receita - investido)/investido)*100.
--        status_roi  = CASE roas >= 20 -> 'LUCRATIVO'
--                           roas >=  0 -> 'NEUTRO'
--                           roas <   0 -> 'PREJUIZO'
--                           (sem ELSE -> NULL quando roas e NULL)
--            Limiar 20 fechado por bissecao em dados reais:
--              19.15 / 19.23 / 19.57 / 19.64 -> NEUTRO
--              20.00 / 20.13 / 20.19 / 20.29 -> LUCRATIVO
--                0.00 -> NEUTRO ;  -1.39 / -3.33 / -100.00 -> PREJUIZO
--            E identico ao que useDisplayROI.ts refaz no cliente (>=20, >=0).
--            Ausencia de ELSE confirmada: linhas com investido_brl=0 tem
--            status_roi = NULL na view.
--
--     INFERIDO (unico ponto ambiguo das formulas): se o CASE compara o valor
--     BRUTO ou o ja ARREDONDADO. Escolhi o bruto. So diverge no fio da navalha
--     (ex.: 19.996 -> ROUND=20.00; bruto daria 'NEUTRO', arredondado daria
--     'LUCRATIVO'). Nao encontrei linha real que desempate.
--
-- -----------------------------------------------------------------------------
-- 4.4 COMPORTAMENTO COM TABELAS VAZIAS (requisito desta entrega):
--     FULL OUTER JOIN de duas tabelas vazias -> 0 linhas; o LEFT JOIN com
--     campaigns nao cria linha nenhuma; nao ha agregado sem GROUP BY (que
--     poderia devolver 1 linha de NULLs); nao ha divisao avaliada. Resultado:
--     SELECT * FROM vw_display_roi -> 0 linhas, sem erro. O hook recebe [],
--     hasData=false, e o componente mostra o estado vazio.
--
-- NOTA SOBRE CREATE OR REPLACE VIEW: no VOLC a view nao existe (confirmado:
-- PostgREST responde PGRST205 "Could not find the table 'public.vw_display_roi'").
-- Se em algum ambiente ela ja existir com outra lista/ordem/tipo de colunas, o
-- CREATE OR REPLACE falha (limitacao do PG). Nesse caso e preciso decidir
-- explicitamente por um DROP VIEW -- que este script NAO faz por conta propria.
-- =============================================================================

CREATE OR REPLACE VIEW public.vw_display_roi AS
WITH base AS (
  -- Uniao completa dos dois lados: todo placement que teve CUSTO (Google Ads)
  -- e/ou RECEITA (GAM) naquela campanha/dia vira exatamente uma linha.
  SELECT
    COALESCE(a.campaign_id, g.campaign_id)  AS campaign_id,
    COALESCE(a.domain,      g.placement_url) AS canal,
    COALESCE(a.date,        g.date)          AS date,
    COALESCE(a.cost,        0)               AS investido_brl,
    COALESCE(a.conversions, 0)               AS conversions,
    COALESCE(g.revenue_brl, 0)               AS receita_brl,
    COALESCE(g.revenue_usd, 0)               AS receita_usd,
    COALESCE(g.impressions, 0)               AS impressions,
    COALESCE(g.clicks,      0)               AS clicks
  FROM public.display_ads_placements a
  FULL OUTER JOIN public.display_gam_placements g
    ON  g.campaign_id   = a.campaign_id
    AND g.placement_url = a.domain
    AND g.date          = a.date
),
calc AS (
  -- Lucro e ROI calculados uma unica vez, para o CASE e o ROUND lerem a mesma
  -- expressao. NULLIF protege a divisao quando nao houve investimento.
  SELECT
    b.campaign_id,
    b.canal,
    b.date,
    b.investido_brl,
    b.conversions,
    b.receita_brl,
    b.receita_usd,
    b.impressions,
    b.clicks,
    b.receita_brl - b.investido_brl AS lucro_bruto,
    ((b.receita_brl - b.investido_brl) / NULLIF(b.investido_brl, 0)) * 100 AS roi_bruto
  FROM base b
)
SELECT
  -- Enriquecimento com a campanha. LEFT JOIN: placements de campaign_id que nao
  -- existe em campaigns continuam aparecendo, com estes 3 campos NULL.
  c.id                          AS campaign_db_id,
  c.campaign_name               AS campaign_name,
  c.advertising_channel_type    AS advertising_channel_type,
  k.campaign_id                 AS campaign_id,
  k.canal                       AS canal,
  k.date                        AS date,
  k.investido_brl               AS investido_brl,
  k.conversions                 AS conversions,
  k.receita_brl                 AS receita_brl,
  k.receita_usd                 AS receita_usd,
  k.impressions                 AS impressions,
  k.clicks                      AS clicks,
  k.lucro_bruto                 AS lucro_bruto,
  ROUND(k.roi_bruto, 2)         AS roas_pct,
  CASE
    WHEN k.roi_bruto >= 20 THEN 'LUCRATIVO'
    WHEN k.roi_bruto >=  0 THEN 'NEUTRO'
    WHEN k.roi_bruto <   0 THEN 'PREJUIZO'
    -- sem ELSE: roi_bruto NULL (investido = 0) resulta em status_roi NULL,
    -- exatamente como o WEBGO devolve.
  END::text                     AS status_roi
FROM calc k
LEFT JOIN public.campaigns c
  ON c.campaign_id = k.campaign_id;


-- =============================================================================
-- 5) security_invoker na view  -- INFERIDO / defensivo
--    Nao consigo saber se a view do WEBGO usa security_invoker. Ligo aqui porque
--    e a recomendacao do Supabase (a view passa a respeitar a RLS de quem
--    consulta, em vez de rodar com os direitos do dono). Combinado com as
--    policies da secao 6, o app anon continua lendo normalmente.
--    Envolvido em DO/EXCEPTION porque a opcao so existe no PG >= 15; em versao
--    anterior o script apenas avisa e segue (a view continua valida).
-- =============================================================================

DO $$
BEGIN
  EXECUTE 'ALTER VIEW public.vw_display_roi SET (security_invoker = true)';
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'security_invoker nao aplicado em vw_display_roi (%). Provavel PostgreSQL < 15. A view segue funcional.', SQLERRM;
END
$$;


-- =============================================================================
-- 6) RLS + POLICIES + GRANTS  -- INFERIDO
--    Nao consigo ler pg_policies de nenhuma das duas instancias.
--    Base da decisao (OBSERVADO): o app do VOLC usa APENAS a anon key
--    (src/lib/supabase.ts -> createClient(VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY))
--    e a anon key ja consegue ler public.campaigns no VOLC (HTTP 200 com linhas).
--    Logo, para o ROI Display funcionar, anon precisa de SELECT aqui tambem.
--    Habilito RLS (mais seguro que deixar desligado) com policy de SELECT para
--    anon e authenticated. Escrita fica so para service_role (que ignora RLS).
--
--    SE O ORQUESTRADOR PREFERIR FECHAR MAIS: basta trocar a role da policy de
--    'anon, authenticated' para so 'authenticated' -- mas ai o app, que hoje
--    consulta como anon, passaria a receber 0 linhas (nao erro).
-- =============================================================================

ALTER TABLE public.display_ads_placements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.display_gam_placements ENABLE ROW LEVEL SECURITY;

-- CREATE POLICY nao aceita IF NOT EXISTS; guarda manual via catalogo.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename  = 'display_ads_placements'
      AND policyname = 'display_ads_placements_select'
  ) THEN
    EXECUTE $p$
      CREATE POLICY display_ads_placements_select
        ON public.display_ads_placements
        FOR SELECT
        TO anon, authenticated
        USING (true)
    $p$;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename  = 'display_gam_placements'
      AND policyname = 'display_gam_placements_select'
  ) THEN
    EXECUTE $p$
      CREATE POLICY display_gam_placements_select
        ON public.display_gam_placements
        FOR SELECT
        TO anon, authenticated
        USING (true)
    $p$;
  END IF;
END
$$;

-- GRANTs. Envolvidos em guarda porque as roles do Supabase (anon /
-- authenticated / service_role) podem nao existir num Postgres cru.
DO $$
DECLARE
  r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('GRANT SELECT ON public.display_ads_placements TO %I', r);
      EXECUTE format('GRANT SELECT ON public.display_gam_placements TO %I', r);
      EXECUTE format('GRANT SELECT ON public.vw_display_roi          TO %I', r);
    ELSE
      RAISE NOTICE 'Role % nao existe nesta instancia; GRANT ignorado.', r;
    END IF;
  END LOOP;

  -- Escrita das tabelas base somente para service_role (o pipeline de ingestao).
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    EXECUTE 'GRANT INSERT, UPDATE ON public.display_ads_placements TO service_role';
    EXECUTE 'GRANT INSERT, UPDATE ON public.display_gam_placements TO service_role';
  END IF;
END
$$;


-- =============================================================================
-- 7) DOCUMENTACAO NO CATALOGO
--    ATENCAO: estes COMMENT ON sao ACRESCIMO MEU. O WEBGO nao tem comentario
--    nenhum nesses objetos (o spec OpenAPI de la nao traz `description` alguma
--    nessas tabelas/view, so as notas automaticas de PK). Sao inofensivos, mas
--    fazem o spec do VOLC ficar levemente diferente do spec do WEBGO.
-- =============================================================================

COMMENT ON TABLE public.display_ads_placements IS
  'Custo/conversoes por placement (dominio) do Google Ads, por campanha e dia. Chave logica: (campaign_id, domain, date). DDL reconstruido a partir do Supabase do WEBGO (nao havia DDL versionado).';

COMMENT ON TABLE public.display_gam_placements IS
  'Receita/impressoes/clicks por placement do Google Ad Manager, por campanha e dia. Chave logica: (campaign_id, placement_url, date). DDL reconstruido a partir do Supabase do WEBGO (nao havia DDL versionado).';

COMMENT ON VIEW public.vw_display_roi IS
  'ROI por placement: FULL OUTER JOIN de display_ads_placements x display_gam_placements por (campaign_id, dominio, date), enriquecido com campaigns via LEFT JOIN. roas_pct e na verdade ROI% = (receita-investido)/investido*100 (NULL quando investido=0). status_roi: >=20 LUCRATIVO, >=0 NEUTRO, <0 PREJUIZO, NULL quando roas_pct e NULL.';


-- =============================================================================
-- 8) RECARREGA O CACHE DE SCHEMA DO POSTGREST
--    Sem isso o PostgREST continua respondendo PGRST205 ate reiniciar sozinho.
--    Guardado porque o canal 'pgrst' so existe em instancias Supabase/PostgREST.
-- =============================================================================

DO $$
BEGIN
  NOTIFY pgrst, 'reload schema';
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'NOTIFY pgrst nao executado (%).', SQLERRM;
END
$$;

-- =============================================================================
-- FIM
-- =============================================================================
