-- v12_04 — fato canonico Google Ads campanha-dia + ledger de execucao D0/D-1
--
-- Autoridade: database.agenciavolc.com.br.
-- Desenho autoritativo: docs/architecture/GADS-REPORT-D0-D1-E-CONTRATO-DE-DADOS.md
-- (secoes "Proxima migration proposta" e "Aceite para ativar os workflows").
-- Estilo e disciplina: v12_01_google_inteligencia_coletas.sql.
--
-- ## POR QUE v12_04 E NAO v13_01
--
-- O prompt M-W2-02 (docs/closure/fable-global-v1/prompts/m-w2-02-migration-d0-d1.md)
-- reserva `v13_01_gads_fato_canonico.sql` para uma sessao interativa em branch
-- propria, e a serie v12_03 esta reservada a ampliacao de `tipo_sinal` do PMax
-- (docs/closure/hermes-p04-t07-pmax-real-read-v1/V12-03-REQUIREMENTS.md). Esta
-- entrega nao pode tocar nenhuma das duas. O objeto entregue aqui e o mesmo que
-- aquele prompt descreve; se as duas lanes existirem, o integrador escolhe UMA.
-- A escolha nao fica no ar: o preflight abaixo ABORTA se as tabelas ja existirem,
-- entao aplicar as duas por engano e mecanicamente impossivel.
--
-- ## O QUE ESTA MIGRATION NAO FAZ
--
-- Nao altera `daily_campaign_metrics` (nem coluna, nem constraint, nem trigger).
-- Nao apaga, reescreve nem recalcula nada do legado. Nao promove o legado a
-- autoridade: ele recebe uma PROJECAO de compatibilidade, restrita as colunas de
-- entrega que o Google Ads mede, e nunca encosta em receita, revshare, GAM,
-- comissao, orientacao ou otimizacao.
--
-- ## AS SETE INVARIANTES QUE O SCHEMA DEFENDE (e nao a aplicacao)
--
--  1. IDENTIDADE COMPLETA. A chave do fato e (customer_id, campaign_id,
--     metric_date, segments_hash). Duas contas com o MESMO campaign_id nao
--     colidem — o defeito que `daily_campaign_metrics` carrega ate hoje.
--  2. NULL != 0. Nenhuma metrica tem DEFAULT. Ausencia permanece NULL; zero so
--     entra quando a leitura bem-sucedida devolveu zero. Numero que chega como
--     STRING e recusado, porque '' -> 0 e exatamente como zero fabricado nasce.
--  3. D0 E D-1 NAO DISPUTAM A CHAVE. Elas COMPARTILHAM a chave e a precedencia e
--     TOTAL e declarada: backfill(3) > D-1(2) > D0(1). Janela fechada nunca e
--     rebaixada por leitura intradia. Empate de posto decide por `colhida_em`.
--  4. IDEMPOTENCIA COM MEMORIA. Mesma `chave_idempotencia` + mesmo conteudo
--     devolve o recibo guardado e NAO escreve. Mesma chave com conteudo
--     DIFERENTE e RECUSADA — aceitar seria deixar um retry reescrever historia.
--  5. RECIBO RESOLVE EXATAMENTE. O fechamento reconcilia o que o chamador
--     declarou contra o que o banco realmente persistiu, e recusa fechar quando
--     divergem, quando falta um lote na sequencia ou quando nada foi escrito.
--  6. FECHAMENTO DEPOIS DA ESCRITA. A FK do fato para o ledger e DEFERRABLE
--     INITIALLY DEFERRED: o fato e escrito antes, o recibo depois, na mesma
--     transacao. Fato sem recibo nao sobrevive ao COMMIT.
--  7. FALHA DA PROJECAO NAO APAGA O FATO. A projecao roda em bloco proprio com
--     EXCEPTION; o SQLSTATE dela vai para o recibo. Isso NAO e engolir erro: o
--     erro fica nomeado e visivel em `projecao_estado`/`projecao_erro_codigo`,
--     e o fato canonico — que e a verdade — sobrevive.

BEGIN;

DO $$
BEGIN
  IF to_regclass('public.trafego_campanha') IS NULL THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'v12_04 exige v9_01: public.trafego_campanha nao existe';
  END IF;
  IF to_regclass('public.trafego_coleta_execucao') IS NOT NULL THEN
    RAISE EXCEPTION USING
      ERRCODE = '42P07',
      MESSAGE = 'v12_04 ja aplicada (ou v13_01 da lane M-W2-02 esta no banco): '
                'public.trafego_coleta_execucao existe. Escolha UMA autoridade antes de seguir.';
  END IF;
  IF to_regclass('public.google_ads_campanha_dia') IS NOT NULL THEN
    RAISE EXCEPTION USING
      ERRCODE = '42P07',
      MESSAGE = 'v12_04 ja aplicada (ou v13_01 da lane M-W2-02 esta no banco): '
                'public.google_ads_campanha_dia existe. Escolha UMA autoridade antes de seguir.';
  END IF;
END $$;


-- ─────────────────────────────────────────────────────── ledger de execucao ──
--
-- Uma linha por LOTE. Um lote e ou um pedaco de contas/linhas ingerido
-- (`tipo_lote='contas'`, ordinal >= 1) ou o FECHAMENTO da execucao inteira
-- (`tipo_lote='fechamento'`, ordinal 0). A execucao logica e `execucao_chave`;
-- ela agrupa os lotes e e o que a reconciliacao soma.
--
-- ⚠️ `execucao_chave` inclui o PASSO da agenda (06/12/18/23 em D0). Isso e
-- deliberado: as quatro passadas do mesmo dia sao QUATRO leituras distintas da
-- mesma janela, nao repeticoes da mesma. Colapsa-las numa chave so obrigaria a
-- ATUALIZAR o recibo — e recibo que se atualiza deixa de ser recibo. E tambem
-- preserva a doutrina do coletor v3: uma falha nao ocupa a chave do sucesso
-- posterior, entao retry guarda a falha E registra a recuperacao.
CREATE TABLE public.trafego_coleta_execucao (
  execucao_id           uuid PRIMARY KEY,
  chave_idempotencia    text        NOT NULL UNIQUE,
  execucao_chave        text        NOT NULL,

  fonte                 text        NOT NULL,
  job                   text        NOT NULL,
  disparo               text        NOT NULL,
  workflow_id           text,
  execucao_externa_id   text,

  api_versao            text        NOT NULL,
  contrato_versao       text        NOT NULL,
  contrato_sha256       text        NOT NULL,

  tipo_lote             text        NOT NULL,
  lote_ordinal          integer     NOT NULL,

  origem_janela         text        NOT NULL,
  janela_inicio         date        NOT NULL,
  janela_fim            date        NOT NULL,

  iniciada_em           timestamptz NOT NULL,
  encerrada_em          timestamptz NOT NULL,
  duracao_ms            integer     NOT NULL,
  batimento_em          timestamptz NOT NULL,

  resultado             text        NOT NULL,
  motivo                text,
  escopo                text,

  contas_tentadas       text[]      NOT NULL DEFAULT '{}'::text[],
  contas_aceitas        text[]      NOT NULL DEFAULT '{}'::text[],
  contas_recusadas      jsonb       NOT NULL DEFAULT '[]'::jsonb,

  linhas_lidas          integer     NOT NULL,
  linhas_aceitas        integer     NOT NULL,
  linhas_preteridas     integer     NOT NULL,
  linhas_rejeitadas     integer     NOT NULL,
  rejeicoes             jsonb       NOT NULL DEFAULT '[]'::jsonb,

  projecao_estado       text        NOT NULL,
  projecao_linhas       integer     NOT NULL DEFAULT 0,
  projecao_erro_codigo  text,

  payload_sha256        text        NOT NULL,
  registrada_em         timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT trafego_coleta_execucao_chave_valida
    CHECK (btrim(chave_idempotencia) <> '' AND btrim(execucao_chave) <> ''),
  CONSTRAINT trafego_coleta_execucao_fonte
    CHECK (fonte IN ('n8n', 'python_oneshot', 'backfill_manual')),
  CONSTRAINT trafego_coleta_execucao_job
    CHECK (job ~ '^[a-z0-9_]{3,40}$'),
  CONSTRAINT trafego_coleta_execucao_disparo
    CHECK (disparo IN ('agenda', 'manual')),
  CONSTRAINT trafego_coleta_execucao_api
    CHECK (api_versao ~ '^v[0-9]{1,3}$'),
  CONSTRAINT trafego_coleta_execucao_contrato
    CHECK (btrim(contrato_versao) <> '' AND contrato_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT trafego_coleta_execucao_payload_hash
    CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),

  -- Fechamento e ordinal 0 e so pode haver um por execucao; lote de contas
  -- comeca em 1 e cresce sem buraco (a contiguidade e conferida no fechamento).
  CONSTRAINT trafego_coleta_execucao_tipo_lote
    CHECK (
      (tipo_lote = 'fechamento' AND lote_ordinal = 0)
      OR (tipo_lote = 'contas' AND lote_ordinal >= 1)
    ),

  CONSTRAINT trafego_coleta_execucao_origem
    CHECK (origem_janela IN ('D0', 'D-1', 'backfill')),
  -- D0 e D-1 leem UM dia. Intervalo so existe em backfill declarado.
  CONSTRAINT trafego_coleta_execucao_janela
    CHECK (
      janela_fim >= janela_inicio
      AND (origem_janela = 'backfill' OR janela_inicio = janela_fim)
    ),

  CONSTRAINT trafego_coleta_execucao_tempo
    CHECK (encerrada_em >= iniciada_em AND duracao_ms >= 0),

  CONSTRAINT trafego_coleta_execucao_resultado
    CHECK (resultado IN ('ok', 'parcial', 'falhou')),
  -- Resultado que nao e 'ok' precisa dizer por que. 'ok' nao inventa motivo.
  CONSTRAINT trafego_coleta_execucao_motivo_semantico
    CHECK (
      (resultado = 'ok' AND motivo IS NULL)
      OR (resultado IN ('parcial', 'falhou') AND btrim(coalesce(motivo, '')) <> '')
    ),
  CONSTRAINT trafego_coleta_execucao_ok_sem_recusa
    CHECK (
      resultado <> 'ok'
      OR (linhas_rejeitadas = 0 AND jsonb_array_length(contas_recusadas) = 0)
    ),
  -- 'falhou' e "nada aproveitavel". Se alguma linha entrou, o desfecho honesto
  -- e 'parcial' — e a linha verde continua verde (contraprova 8).
  CONSTRAINT trafego_coleta_execucao_falha_sem_linha
    CHECK (resultado <> 'falhou' OR linhas_aceitas = 0),

  CONSTRAINT trafego_coleta_execucao_contagens_nao_negativas
    CHECK (
      linhas_lidas >= 0 AND linhas_aceitas >= 0
      AND linhas_preteridas >= 0 AND linhas_rejeitadas >= 0
      AND projecao_linhas >= 0
    ),
  -- A soma fecha. Sem esta linha, "lidas" viraria um numero decorativo.
  CONSTRAINT trafego_coleta_execucao_contagens_fecham
    CHECK (linhas_lidas = linhas_aceitas + linhas_preteridas + linhas_rejeitadas),
  CONSTRAINT trafego_coleta_execucao_projecao_cabe
    CHECK (projecao_linhas <= linhas_aceitas),

  -- Conta e digito. Vazio nao e ausencia: array vazio significa "nenhuma", e
  -- uma string em branco dentro do array significaria "identidade que nao
  -- endereca nada" — o mesmo defeito de `customer_id = ''` na v9_01.
  --
  -- ⚠️ A primeira versao desta guarda era so o regex sobre `array_to_string`, e
  -- a contraprova CP-24b passou por cima dela: `array_to_string(ARRAY[''], ',')`
  -- devolve string VAZIA, que e exatamente o que o `?` do regex aceitava. Um
  -- array com um elemento em branco ficava indistinguivel de um array vazio.
  -- Por isso a cardinalidade tambem e conferida: NULO no meio some no
  -- `array_to_string` e branco produz parte vazia.
  CONSTRAINT trafego_coleta_execucao_contas_tentadas_forma
    CHECK (
      coalesce(cardinality(contas_tentadas), 0) = 0
      OR (array_to_string(contas_tentadas, ',') ~ '^[0-9]{6,12}(,[0-9]{6,12})*$'
          AND cardinality(contas_tentadas)
              = coalesce(array_length(
                  string_to_array(array_to_string(contas_tentadas, ','), ','), 1), 0))
    ),
  CONSTRAINT trafego_coleta_execucao_contas_aceitas_forma
    CHECK (
      coalesce(cardinality(contas_aceitas), 0) = 0
      OR (array_to_string(contas_aceitas, ',') ~ '^[0-9]{6,12}(,[0-9]{6,12})*$'
          AND cardinality(contas_aceitas)
              = coalesce(array_length(
                  string_to_array(array_to_string(contas_aceitas, ','), ','), 1), 0))
    ),
  CONSTRAINT trafego_coleta_execucao_contas_recusadas_forma
    CHECK (jsonb_typeof(contas_recusadas) = 'array'),
  CONSTRAINT trafego_coleta_execucao_rejeicoes_forma
    CHECK (jsonb_typeof(rejeicoes) = 'array'),

  CONSTRAINT trafego_coleta_execucao_projecao_estado
    CHECK (projecao_estado IN (
      'nao_solicitada', 'aplicada', 'parcial',
      'recusada_ambigua', 'indisponivel', 'falhou'
    )),
  -- Projecao que falhou precisa dizer QUAL erro. Estado sem codigo seria
  -- exatamente o "engoliu a excecao e respondeu sucesso" que o H12 denuncia.
  CONSTRAINT trafego_coleta_execucao_projecao_erro_semantico
    CHECK (
      (projecao_estado = 'falhou' AND btrim(coalesce(projecao_erro_codigo, '')) <> '')
      OR (projecao_estado <> 'falhou' AND projecao_erro_codigo IS NULL)
    ),
  CONSTRAINT trafego_coleta_execucao_projecao_zero_quando_nao_aplica
    CHECK (projecao_estado IN ('aplicada', 'parcial') OR projecao_linhas = 0),

  CONSTRAINT trafego_coleta_execucao_lote_unico
    UNIQUE (execucao_chave, tipo_lote, lote_ordinal)
);


-- ───────────────────────────────────────────────── fato canonico campanha-dia ──
--
-- ⚠️ NENHUMA metrica tem DEFAULT, e isso e o ponto inteiro da tabela. A legada
-- grava 0 quando nao sabe (src/sql/update_sync_gam_function.sql:41 insere
-- "-- Metricas Google Ads zeradas"), e depois ninguem consegue separar "gastou
-- zero" de "nao li". Aqui NULL e ausencia e 0 e medida.
CREATE TABLE public.google_ads_campanha_dia (
  fato_id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  -- IDENTIDADE
  customer_id            text        NOT NULL,
  campaign_id            text        NOT NULL,
  metric_date            date        NOT NULL,
  segments_hash          text        NOT NULL,
  volc_campaign_id       text        REFERENCES public.trafego_campanha (volc_campaign_id)
                                     ON DELETE RESTRICT,
  segmentos              jsonb       NOT NULL DEFAULT '{}'::jsonb,

  campaign_name          text,
  campaign_status        text,
  advertising_channel_type text,

  -- PROVA. `execucao_id` e DEFERRABLE de proposito: o fato entra antes do
  -- recibo, e o COMMIT recusa fato orfao.
  execucao_id            uuid        NOT NULL
                                     REFERENCES public.trafego_coleta_execucao (execucao_id)
                                     ON DELETE RESTRICT
                                     DEFERRABLE INITIALLY DEFERRED,
  colhida_em             timestamptz NOT NULL,
  api_versao             text        NOT NULL,
  currency_code          text        NOT NULL,
  origem_janela          text        NOT NULL,
  janela_fechada         boolean     NOT NULL,
  precedencia            smallint    NOT NULL,

  -- ENTREGA (int64 na API)
  impressoes             bigint,
  cliques                bigint,
  interacoes             bigint,
  custo_micros           bigint,

  -- RESULTADO (double na API)
  conversoes                   numeric,
  todas_conversoes             numeric,
  valor_conversoes             numeric,
  valor_todas_conversoes       numeric,

  -- EFICIENCIA. Dinheiro conserva micros E moeda; `ctr` e taxa 0..1.
  ctr                          numeric,
  cpc_medio_micros             numeric,
  custo_por_conversao_micros   numeric,

  -- LEILAO SEARCH (taxas 0..1 na API, nunca percentuais 0..100)
  search_impression_share                numeric,
  search_budget_lost_impression_share    numeric,
  search_rank_lost_impression_share      numeric,
  search_top_impression_share            numeric,
  search_absolute_top_impression_share   numeric,
  search_click_share                     numeric,
  search_exact_match_impression_share    numeric,
  top_impression_percentage              numeric,
  absolute_top_impression_percentage     numeric,

  -- Campos compativeis ainda nao promovidos a coluna. NAO e deposito de outra
  -- granularidade: ad group, keyword, search term e asset tem tabela propria.
  metricas_extras        jsonb       NOT NULL DEFAULT '{}'::jsonb,

  atualizada_em          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT google_ads_campanha_dia_identidade
    CHECK (customer_id ~ '^[0-9]{6,12}$' AND campaign_id ~ '^[0-9]{1,20}$'),
  CONSTRAINT google_ads_campanha_dia_segments_hash
    CHECK (segments_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT google_ads_campanha_dia_segmentos_objeto
    CHECK (jsonb_typeof(segmentos) = 'object'),
  CONSTRAINT google_ads_campanha_dia_extras_objeto
    CHECK (jsonb_typeof(metricas_extras) = 'object'),
  CONSTRAINT google_ads_campanha_dia_moeda
    CHECK (currency_code ~ '^[A-Z]{3}$'),
  CONSTRAINT google_ads_campanha_dia_api
    CHECK (api_versao ~ '^v[0-9]{1,3}$'),
  CONSTRAINT google_ads_campanha_dia_origem
    CHECK (origem_janela IN ('D0', 'D-1', 'backfill')),
  -- Janela fechada e uma consequencia da origem, nao uma segunda opiniao.
  CONSTRAINT google_ads_campanha_dia_janela_coerente
    CHECK (janela_fechada = (origem_janela <> 'D0')),
  CONSTRAINT google_ads_campanha_dia_precedencia_coerente
    CHECK (precedencia = CASE origem_janela
                           WHEN 'D0' THEN 1 WHEN 'D-1' THEN 2 ELSE 3 END),

  CONSTRAINT google_ads_campanha_dia_entrega_nao_negativa
    CHECK (
      (impressoes   IS NULL OR impressoes   >= 0)
      AND (cliques      IS NULL OR cliques      >= 0)
      AND (interacoes   IS NULL OR interacoes   >= 0)
      AND (custo_micros IS NULL OR custo_micros >= 0)
    ),
  CONSTRAINT google_ads_campanha_dia_resultado_nao_negativo
    CHECK (
      (conversoes             IS NULL OR conversoes             >= 0)
      AND (todas_conversoes       IS NULL OR todas_conversoes       >= 0)
      AND (valor_conversoes       IS NULL OR valor_conversoes       >= 0)
      AND (valor_todas_conversoes IS NULL OR valor_todas_conversoes >= 0)
    ),
  CONSTRAINT google_ads_campanha_dia_eficiencia_nao_negativa
    CHECK (
      (cpc_medio_micros           IS NULL OR cpc_medio_micros           >= 0)
      AND (custo_por_conversao_micros IS NULL OR custo_por_conversao_micros >= 0)
    ),
  -- Taxas sao 0..1. Um dia em que a API devolver 0..100 aqui, esta constraint
  -- grita — que e melhor do que multiplicar o gasto por cem numa tela.
  CONSTRAINT google_ads_campanha_dia_taxas
    CHECK (
      (ctr IS NULL OR (ctr >= 0 AND ctr <= 1))
      AND (search_impression_share              IS NULL OR (search_impression_share              BETWEEN 0 AND 1))
      AND (search_budget_lost_impression_share  IS NULL OR (search_budget_lost_impression_share  BETWEEN 0 AND 1))
      AND (search_rank_lost_impression_share    IS NULL OR (search_rank_lost_impression_share    BETWEEN 0 AND 1))
      AND (search_top_impression_share          IS NULL OR (search_top_impression_share          BETWEEN 0 AND 1))
      AND (search_absolute_top_impression_share IS NULL OR (search_absolute_top_impression_share BETWEEN 0 AND 1))
      AND (search_click_share                   IS NULL OR (search_click_share                   BETWEEN 0 AND 1))
      AND (search_exact_match_impression_share  IS NULL OR (search_exact_match_impression_share  BETWEEN 0 AND 1))
      AND (top_impression_percentage            IS NULL OR (top_impression_percentage            BETWEEN 0 AND 1))
      AND (absolute_top_impression_percentage   IS NULL OR (absolute_top_impression_percentage   BETWEEN 0 AND 1))
    ),

  CONSTRAINT google_ads_campanha_dia_chave
    UNIQUE (customer_id, campaign_id, metric_date, segments_hash)
);

CREATE INDEX trafego_coleta_execucao_chave_ix
  ON public.trafego_coleta_execucao (execucao_chave, tipo_lote, lote_ordinal);
CREATE INDEX trafego_coleta_execucao_janela_ix
  ON public.trafego_coleta_execucao (job, janela_inicio DESC, encerrada_em DESC);
CREATE INDEX trafego_coleta_execucao_batimento_ix
  ON public.trafego_coleta_execucao (job, batimento_em DESC);
CREATE INDEX trafego_coleta_execucao_resultado_ix
  ON public.trafego_coleta_execucao (resultado, encerrada_em DESC);

CREATE INDEX google_ads_campanha_dia_conta_ix
  ON public.google_ads_campanha_dia (customer_id, metric_date DESC);
CREATE INDEX google_ads_campanha_dia_legado_ix
  ON public.google_ads_campanha_dia (campaign_id, metric_date);
CREATE INDEX google_ads_campanha_dia_execucao_ix
  ON public.google_ads_campanha_dia (execucao_id);
CREATE INDEX google_ads_campanha_dia_volc_ix
  ON public.google_ads_campanha_dia (volc_campaign_id, metric_date DESC)
  WHERE volc_campaign_id IS NOT NULL;

COMMENT ON TABLE public.trafego_coleta_execucao IS
  'Ledger append-only de cada lote de ingestao Google Ads campanha-dia. Uma linha por lote; o fechamento (ordinal 0) reconcilia contra o que o banco persistiu e recusa fechar quando diverge.';
COMMENT ON COLUMN public.trafego_coleta_execucao.execucao_chave IS
  'job:origem_janela:janela_inicio:passo. O passo separa as quatro passadas D0 do mesmo dia — quatro leituras, quatro recibos.';
COMMENT ON COLUMN public.trafego_coleta_execucao.batimento_em IS
  'Carimbo de vida declarado pelo chamador no instante do lote. Alimenta o deadman de docs/contracts/HEALTH-DEADMAN-GOOGLE-INTELLIGENCE.md; ausencia continua sendo ausencia.';
COMMENT ON TABLE public.google_ads_campanha_dia IS
  'Fato canonico campanha-dia. NULL = nao medido; 0 = medido e zerado. Dinheiro em micros com moeda. Chave por conta+campanha+data+segmentos: duas contas com o mesmo campaign_id nunca colidem.';
COMMENT ON COLUMN public.google_ads_campanha_dia.precedencia IS
  'Posto derivado da origem: D0=1, D-1=2, backfill=3. Leitura de posto menor nunca rebaixa um fato de posto maior.';
COMMENT ON COLUMN public.google_ads_campanha_dia.metricas_extras IS
  'Campos compativeis ainda nao promovidos a coluna, na MESMA granularidade campanha-dia. Ad group, keyword, search term e asset tem tabela propria — nao entram aqui.';


-- ────────────────────────────────────────────────────────────── append-only ──
CREATE OR REPLACE FUNCTION public.trafego_coleta_execucao_append_only()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
  RAISE EXCEPTION USING
    ERRCODE = '55000',
    MESSAGE = format('%s e append-only: UPDATE e DELETE recusados', TG_TABLE_NAME);
END;
$$;

CREATE TRIGGER trafego_coleta_execucao_append_only
  BEFORE UPDATE OR DELETE ON public.trafego_coleta_execucao
  FOR EACH ROW EXECUTE FUNCTION public.trafego_coleta_execucao_append_only();


-- ───────────────────────────────────────────── identidade derivada, nao sorteada ──
--
-- `execucao_id` sai da chave de idempotencia por sha256. Duas consequencias:
-- um retry resolve para o MESMO uuid, e ninguem precisa hashear em JavaScript
-- (o Code node do n8n nao tem `require('crypto')` — os builtins sao bloqueados
-- por padrao, e um hash caseiro em JS seria pior do que nao ter hash).
CREATE OR REPLACE FUNCTION public.volc_gads_uuid_da_chave(chave text)
RETURNS uuid
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, public
AS $$
  SELECT (
      substr(h,  1, 8) || '-' ||
      substr(h,  9, 4) || '-' ||
      -- versao 8 (UUID derivado de nome, RFC 9562) e variante RFC 4122.
      '8' || substr(h, 14, 3) || '-' ||
      (CASE WHEN substr(h, 17, 1) IN ('8','9','a','b') THEN substr(h, 17, 1) ELSE '8' END)
        || substr(h, 18, 3) || '-' ||
      substr(h, 21, 12)
    )::uuid
  FROM (SELECT encode(sha256(convert_to(chave, 'UTF8')), 'hex') AS h) AS d;
$$;

COMMENT ON FUNCTION public.volc_gads_uuid_da_chave(text) IS
  'UUIDv8 deterministico a partir da chave de idempotencia. Retry resolve para o mesmo identificador.';


-- ───────────────────────────────────────── projecao de compatibilidade legada ──
--
-- ## O QUE ELA E, DITO ANTES QUE ALGUEM CONCLUA SOZINHO
--
-- Ela NAO torna `daily_campaign_metrics` autoridade. Ela mantem as telas atuais
-- lendo enquanto os consumidores migram. Por isso:
--
--  * escreve SOMENTE as 16 colunas de ENTREGA que o Google Ads mede;
--  * NUNCA encosta em revenue, revenue_converted, revenue_converted_revshare,
--    roas, rps, ecpm, commission_operator, gam_*, fill_rate, match_rate,
--    page_views, pmr, viewability, viewable_impressions, unfilled_impressions,
--    orientacao_* nem otimizacao_*;
--  * quando o fato canonico e NULL, grava NULL — nunca 0. Se a coluna legada
--    for NOT NULL, a projecao FALHA com SQLSTATE nomeado, e essa falha aparece
--    no recibo. Falhar alto e melhor do que gravar um zero que ninguem pediu;
--  * RECUSA a linha quando `campaign_id` e ambiguo. A legada nao tem
--    `customer_id`: se duas contas tiverem o mesmo `campaign_id` na mesma data,
--    projetar as duas escreveria uma por cima da outra em silencio. O fato
--    canonico guarda as duas separadas; a projecao declara `recusada_ambigua`.
--
-- Retorna (linhas_projetadas, estado). Nao levanta excecao: quem trata e o
-- chamador, que grava o desfecho no recibo.
CREATE OR REPLACE FUNCTION public.volc_gads_projetar_daily_compat(
  p_execucao_id uuid
)
RETURNS TABLE (linhas integer, estado text, erro_codigo text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  aplicadas   integer := 0;
  ambiguas    integer := 0;
  f           record;
BEGIN
  IF to_regclass('public.daily_campaign_metrics') IS NULL THEN
    RETURN QUERY SELECT 0, 'indisponivel'::text, NULL::text;
    RETURN;
  END IF;

  BEGIN
    FOR f IN
      SELECT g.*
        FROM public.google_ads_campanha_dia g
       WHERE g.execucao_id = p_execucao_id
       ORDER BY g.customer_id, g.campaign_id
    LOOP
      -- Ambiguidade e medida no FATO, nao suposta: existe outra conta com o
      -- mesmo campaign_id na mesma data?
      IF EXISTS (
        SELECT 1
          FROM public.google_ads_campanha_dia o
         WHERE o.campaign_id = f.campaign_id
           AND o.metric_date = f.metric_date
           AND o.customer_id <> f.customer_id
      ) THEN
        ambiguas := ambiguas + 1;
        CONTINUE;
      END IF;

      UPDATE public.daily_campaign_metrics d
         SET impressions                        = f.impressoes,
             clicks                             = f.cliques,
             spend                              = CASE WHEN f.custo_micros IS NULL
                                                       THEN NULL
                                                       ELSE f.custo_micros / 1000000.0 END,
             conversions                        = f.conversoes,
             ctr                                = f.ctr,
             cpc                                = CASE WHEN f.cpc_medio_micros IS NULL
                                                       THEN NULL
                                                       ELSE f.cpc_medio_micros / 1000000.0 END,
             cost_per_conversion                = CASE WHEN f.custo_por_conversao_micros IS NULL
                                                       THEN NULL
                                                       ELSE f.custo_por_conversao_micros / 1000000.0 END,
             search_impression_share            = f.search_impression_share,
             lost_impression_share_budget       = f.search_budget_lost_impression_share,
             lost_impression_share_rank         = f.search_rank_lost_impression_share,
             top_impression_percentage          = f.top_impression_percentage,
             absolute_top_impression_percentage = f.absolute_top_impression_percentage,
             search_click_share                 = f.search_click_share,
             search_exact_match_impression_share = f.search_exact_match_impression_share,
             updated_at                         = now()
       WHERE d.campaign_id = f.campaign_id
         AND d.date        = f.metric_date;

      IF FOUND THEN
        aplicadas := aplicadas + 1;
      END IF;
      -- ⚠️ Sem linha legada, a projecao NAO cria uma. Criar linha nova em
      -- `daily_campaign_metrics` significaria decidir revenue/revshare/projeto
      -- sem dado — que e como a legada ficou cheia de zero fabricado. Fato
      -- canonico basta; a tela migra ou o backfill legado e outra tarefa.
    END LOOP;

    IF ambiguas > 0 AND aplicadas = 0 THEN
      RETURN QUERY SELECT aplicadas, 'recusada_ambigua'::text, NULL::text;
    ELSIF ambiguas > 0 THEN
      RETURN QUERY SELECT aplicadas, 'parcial'::text, NULL::text;
    ELSE
      RETURN QUERY SELECT aplicadas, 'aplicada'::text, NULL::text;
    END IF;
  EXCEPTION WHEN OTHERS THEN
    -- NAO e engolir excecao: o SQLSTATE volta e vai para o recibo, visivel.
    -- O que esta protegido e o FATO CANONICO — ele nao pode morrer porque uma
    -- tabela legada tem uma constraint que ninguem controla.
    RETURN QUERY SELECT 0, 'falhou'::text, SQLSTATE::text;
  END;
END;
$$;


-- ─────────────────────────────────────────────────── a UNICA RPC de ingestao ──
--
-- Uma so porta. O n8n orquestra e agenda; consistencia, identidade,
-- idempotencia, precedencia, reconciliacao e projecao ficam AQUI.
CREATE OR REPLACE FUNCTION public.volc_registrar_gads_campanha_dia(documento jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_chave        text;
  v_exec_chave   text;
  v_tipo         text;
  v_ordinal      integer;
  v_origem       text;
  v_ini          date;
  v_fim          date;
  v_api          text;
  v_hash_alvo    jsonb;
  v_payload      text;
  v_exec_id      uuid;
  v_existente    record;
  v_linhas       jsonb;
  v_linha        jsonb;
  v_i            integer;
  v_aceitas      integer := 0;
  v_preteridas   integer := 0;
  v_rejeitadas   integer := 0;
  v_rejeicoes    jsonb := '[]'::jsonb;
  v_motivo_linha text;
  v_seg          jsonb;
  v_seg_hash     text;
  v_precedencia  smallint;
  v_atual        record;
  v_proj_linhas  integer := 0;
  v_proj_estado  text := 'nao_solicitada';
  v_proj_erro    text := NULL;
  v_soma         record;
  v_fatos        integer;
  v_resultado    text;
  v_projetar     boolean;
BEGIN
  IF jsonb_typeof(documento) <> 'object' THEN
    RAISE EXCEPTION USING ERRCODE = '22023',
      MESSAGE = 'DOCUMENTO_INVALIDO: documento precisa ser objeto JSON';
  END IF;

  v_chave      := documento->>'chave_idempotencia';
  v_exec_chave := documento->>'execucao_chave';
  v_tipo       := documento->>'tipo_lote';
  v_ordinal    := (documento->>'lote_ordinal')::integer;
  v_origem     := documento->>'origem_janela';
  v_ini        := (documento->>'janela_inicio')::date;
  v_fim        := (documento->>'janela_fim')::date;
  v_api        := documento->>'api_versao';
  v_resultado  := documento->>'resultado';
  v_linhas     := coalesce(documento->'linhas', '[]'::jsonb);

  IF coalesce(btrim(v_chave), '') = '' OR coalesce(btrim(v_exec_chave), '') = '' THEN
    RAISE EXCEPTION USING ERRCODE = '22023',
      MESSAGE = 'DOCUMENTO_INVALIDO: chave_idempotencia e execucao_chave sao obrigatorias';
  END IF;
  IF jsonb_typeof(v_linhas) <> 'array' THEN
    RAISE EXCEPTION USING ERRCODE = '22023',
      MESSAGE = 'DOCUMENTO_INVALIDO: linhas precisa ser array';
  END IF;

  -- ── impressao do CONTEUDO, nao do relogio ────────────────────────────────
  -- Um retry legitimo repete os mesmos dados com outro `encerrada_em`. Se o
  -- carimbo entrasse na impressao, todo retry viraria "conteudo diferente" e a
  -- contraprova de idempotencia morreria. Entram identidade, janela, contrato,
  -- desfecho e AS LINHAS; ficam de fora os campos de tempo e de vida.
  v_hash_alvo := jsonb_build_object(
    'execucao_chave',  v_exec_chave,
    'tipo_lote',       v_tipo,
    'lote_ordinal',    v_ordinal,
    'origem_janela',   v_origem,
    'janela_inicio',   v_ini,
    'janela_fim',      v_fim,
    'api_versao',      v_api,
    'contrato_sha256', documento->>'contrato_sha256',
    'resultado',       v_resultado,
    'motivo',          documento->>'motivo',
    'contas_tentadas', coalesce(documento->'contas_tentadas', '[]'::jsonb),
    'contas_aceitas',  coalesce(documento->'contas_aceitas', '[]'::jsonb),
    'linhas',          v_linhas
  );
  v_payload := encode(sha256(convert_to(v_hash_alvo::text, 'UTF8')), 'hex');

  -- Esta RPC foi desenhada e provada em READ COMMITTED. Em isolamento de
  -- snapshot fixo, uma sessão que esperou o lock poderia continuar sem enxergar
  -- o recibo recém-commitado pela vencedora e cair em UNIQUE. Falhar com nome é
  -- melhor do que fingir idempotência fora do contrato testado.
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION USING ERRCODE = '25001',
      MESSAGE = 'ISOLAMENTO_NAO_SUPORTADO_V12_04: use READ COMMITTED para a RPC';
  END IF;

  -- Locks por identidade de fato são tomados ANTES do lock de idempotência e em
  -- ordem determinística. Isso evita deadlock entre duas execuções com chaves
  -- distintas que disputam os mesmos fatos em ordem oposta.
  PERFORM pg_advisory_xact_lock(hashtextextended('v12_04:fato:' || k, 0))
    FROM (
      SELECT DISTINCT
             coalesce(x->>'customer_id', '<null>') || '|' ||
             coalesce(x->>'campaign_id', '<null>') || '|' ||
             coalesce(x->>'metric_date', '<null>') || '|' ||
             encode(sha256(convert_to(coalesce(x->'segmentos', '{}'::jsonb)::text, 'UTF8')), 'hex') AS k
        FROM jsonb_array_elements(v_linhas) x
       ORDER BY 1
    ) s;

  -- Depois dos locks de fato, serializamos a chave de idempotência. Sem este
  -- lock, duas transações iguais podiam ambas não ver o recibo invisível da
  -- outra; a perdedora quebrava em UNIQUE depois de já disputar fato.
  PERFORM pg_advisory_xact_lock(hashtextextended('v12_04:idempotencia:' || v_chave, 0));

  -- ── idempotencia com memoria ─────────────────────────────────────────────
  SELECT * INTO v_existente
    FROM public.trafego_coleta_execucao
   WHERE chave_idempotencia = v_chave;

  IF FOUND THEN
    IF v_existente.payload_sha256 <> v_payload THEN
      RAISE EXCEPTION USING ERRCODE = '22023',
        MESSAGE = 'CHAVE_REUTILIZADA_CONTEUDO_DIVERGENTE: a chave '
                  || v_chave || ' ja existe com outro conteudo';
    END IF;
    RETURN jsonb_build_object(
      'execucao_id',       v_existente.execucao_id,
      'chave_idempotencia', v_existente.chave_idempotencia,
      'repetida',          true,
      'linhas_lidas',      v_existente.linhas_lidas,
      'linhas_aceitas',    v_existente.linhas_aceitas,
      'linhas_preteridas', v_existente.linhas_preteridas,
      'linhas_rejeitadas', v_existente.linhas_rejeitadas,
      'rejeicoes',         v_existente.rejeicoes,
      'projecao_estado',   v_existente.projecao_estado,
      'projecao_linhas',   v_existente.projecao_linhas,
      'resultado',         v_existente.resultado
    );
  END IF;

  v_exec_id := public.volc_gads_uuid_da_chave(v_chave);

  -- ── lote de contas: escreve o fato ANTES do recibo ───────────────────────
  IF v_tipo = 'contas' THEN

    -- Duplicata dentro do proprio lote e defeito de paginacao, nao dado.
    IF (SELECT count(*) FROM jsonb_array_elements(v_linhas) x)
       <> (SELECT count(DISTINCT coalesce(x->>'customer_id', '') || '|'
                                 || coalesce(x->>'campaign_id', '') || '|'
                                 || coalesce(x->>'metric_date', '') || '|'
                                 || coalesce((x->'segmentos')::text, '{}'))
             FROM jsonb_array_elements(v_linhas) x) THEN
      RAISE EXCEPTION USING ERRCODE = '22023',
        MESSAGE = 'LINHAS_DUPLICADAS_NO_LOTE: a mesma chave de fato aparece duas vezes no lote';
    END IF;

    v_i := 0;
    FOR v_linha IN SELECT value FROM jsonb_array_elements(v_linhas) LOOP
      v_i := v_i + 1;
      v_motivo_linha := NULL;

      -- validacao semantica, campo a campo
      IF coalesce(v_linha->>'customer_id', '') !~ '^[0-9]{6,12}$' THEN
        v_motivo_linha := 'CUSTOMER_ID_INVALIDO';
      ELSIF coalesce(v_linha->>'campaign_id', '') !~ '^[0-9]{1,20}$' THEN
        v_motivo_linha := 'CAMPAIGN_ID_INVALIDO';
      ELSIF coalesce(v_linha->>'currency_code', '') !~ '^[A-Z]{3}$' THEN
        v_motivo_linha := 'MOEDA_AUSENTE_OU_INVALIDA';
      ELSIF (v_linha->>'metric_date') IS NULL THEN
        v_motivo_linha := 'DATA_AUSENTE';
      ELSIF (v_linha->>'metric_date')::date < v_ini
            OR (v_linha->>'metric_date')::date > v_fim THEN
        v_motivo_linha := 'DATA_FORA_DA_JANELA';
      ELSIF (v_linha->>'colhida_em') IS NULL THEN
        v_motivo_linha := 'COLHIDA_EM_AUSENTE';
      ELSIF jsonb_typeof(coalesce(v_linha->'segmentos', '{}'::jsonb)) <> 'object' THEN
        v_motivo_linha := 'SEGMENTOS_INVALIDOS';
      ELSE
        -- ⚠️ Numero que chega como STRING e recusado. `''::numeric` explode e
        -- `'0'` passaria como zero medido — os dois caminhos fabricam dado.
        SELECT string_agg(k, ',') INTO v_motivo_linha
          FROM jsonb_each(v_linha) e(k, v)
         WHERE k IN (
                 'impressoes','cliques','interacoes','custo_micros',
                 'conversoes','todas_conversoes','valor_conversoes',
                 'valor_todas_conversoes','ctr','cpc_medio_micros',
                 'custo_por_conversao_micros',
                 'search_impression_share','search_budget_lost_impression_share',
                 'search_rank_lost_impression_share','search_top_impression_share',
                 'search_absolute_top_impression_share','search_click_share',
                 'search_exact_match_impression_share',
                 'top_impression_percentage','absolute_top_impression_percentage')
           AND jsonb_typeof(v) NOT IN ('number', 'null');
        IF v_motivo_linha IS NOT NULL THEN
          v_motivo_linha := 'METRICA_NAO_NUMERICA:' || v_motivo_linha;
        END IF;
      END IF;

      IF v_motivo_linha IS NOT NULL THEN
        v_rejeitadas := v_rejeitadas + 1;
        v_rejeicoes := v_rejeicoes || jsonb_build_object(
          'ordinal', v_i,
          'customer_id', v_linha->>'customer_id',
          'campaign_id', v_linha->>'campaign_id',
          'metric_date', v_linha->>'metric_date',
          'motivo', v_motivo_linha
        );
        CONTINUE;
      END IF;

      v_seg := coalesce(v_linha->'segmentos', '{}'::jsonb);
      v_seg_hash := encode(sha256(convert_to(v_seg::text, 'UTF8')), 'hex');
      v_precedencia := CASE v_origem WHEN 'D0' THEN 1 WHEN 'D-1' THEN 2 ELSE 3 END;

      -- Lock transacional por identidade canonica do fato. Ele torna falsa a
      -- leitura concorrente 'nao existe ainda' e permite que a segunda sessao
      -- decida contra o fato materializado pela primeira.
      PERFORM pg_advisory_xact_lock(hashtextextended(
        'v12_04:fato:' || (v_linha->>'customer_id') || '|' || (v_linha->>'campaign_id')
        || '|' || (v_linha->>'metric_date') || '|' || v_seg_hash, 0));

      SELECT g.*
        INTO v_atual
        FROM public.google_ads_campanha_dia g
       WHERE g.customer_id   = v_linha->>'customer_id'
         AND g.campaign_id   = v_linha->>'campaign_id'
         AND g.metric_date   = (v_linha->>'metric_date')::date
         AND g.segments_hash = v_seg_hash;

      IF FOUND THEN
        -- A mesma execucao nao pode escrever o mesmo fato duas vezes: se
        -- pudesse, `linhas_aceitas` deixaria de resolver as linhas persistidas
        -- e a reconciliacao do fechamento viraria decoracao.
        IF EXISTS (
          SELECT 1 FROM public.trafego_coleta_execucao e
           WHERE e.execucao_id = v_atual.execucao_id
             AND e.execucao_chave = v_exec_chave
        ) OR v_atual.execucao_id = v_exec_id THEN
          RAISE EXCEPTION USING ERRCODE = '22023',
            MESSAGE = 'FATO_DUPLICADO_NA_EXECUCAO: '
                      || (v_linha->>'customer_id') || '/' || (v_linha->>'campaign_id')
                      || '/' || (v_linha->>'metric_date');
        END IF;

        -- precedencia total e declarada
        -- Empate total é determinístico e conservador: se o conteúdo é o
        -- mesmo, o primeiro fato materializado fica e o segundo deixa recibo
        -- coerente como preterido. Se o conteúdo diverge no mesmo posto e mesmo
        -- colhida_em, não é idempotência: é conflito explícito.
        IF v_precedencia = v_atual.precedencia
           AND (v_linha->>'colhida_em')::timestamptz = v_atual.colhida_em THEN
          IF (v_linha->>'currency_code') IS DISTINCT FROM v_atual.currency_code
             OR ((v_linha->>'impressoes')::bigint IS DISTINCT FROM v_atual.impressoes)
             OR ((v_linha->>'cliques')::bigint IS DISTINCT FROM v_atual.cliques)
             OR ((v_linha->>'interacoes')::bigint IS DISTINCT FROM v_atual.interacoes)
             OR ((v_linha->>'custo_micros')::bigint IS DISTINCT FROM v_atual.custo_micros)
             OR ((v_linha->>'conversoes')::numeric IS DISTINCT FROM v_atual.conversoes)
             OR ((v_linha->>'todas_conversoes')::numeric IS DISTINCT FROM v_atual.todas_conversoes)
             OR ((v_linha->>'valor_conversoes')::numeric IS DISTINCT FROM v_atual.valor_conversoes)
             OR ((v_linha->>'valor_todas_conversoes')::numeric IS DISTINCT FROM v_atual.valor_todas_conversoes)
             OR ((v_linha->>'ctr')::numeric IS DISTINCT FROM v_atual.ctr)
             OR ((v_linha->>'cpc_medio_micros')::numeric IS DISTINCT FROM v_atual.cpc_medio_micros)
             OR ((v_linha->>'custo_por_conversao_micros')::numeric IS DISTINCT FROM v_atual.custo_por_conversao_micros) THEN
            RAISE EXCEPTION USING ERRCODE = '22023',
              MESSAGE = 'FATO_EMPATE_CONTEUDO_DIVERGENTE: '
                        || (v_linha->>'customer_id') || '/' || (v_linha->>'campaign_id')
                        || '/' || (v_linha->>'metric_date');
          END IF;
          v_preteridas := v_preteridas + 1;
          CONTINUE;
        END IF;

        IF v_precedencia < v_atual.precedencia
           OR (v_precedencia = v_atual.precedencia
               AND (v_linha->>'colhida_em')::timestamptz < v_atual.colhida_em) THEN
          v_preteridas := v_preteridas + 1;
          CONTINUE;
        END IF;
      END IF;

      INSERT INTO public.google_ads_campanha_dia AS g (
        customer_id, campaign_id, metric_date, segments_hash, segmentos,
        volc_campaign_id, campaign_name, campaign_status, advertising_channel_type,
        execucao_id, colhida_em, api_versao, currency_code,
        origem_janela, janela_fechada, precedencia,
        impressoes, cliques, interacoes, custo_micros,
        conversoes, todas_conversoes, valor_conversoes, valor_todas_conversoes,
        ctr, cpc_medio_micros, custo_por_conversao_micros,
        search_impression_share, search_budget_lost_impression_share,
        search_rank_lost_impression_share, search_top_impression_share,
        search_absolute_top_impression_share, search_click_share,
        search_exact_match_impression_share,
        top_impression_percentage, absolute_top_impression_percentage,
        metricas_extras, atualizada_em
      ) VALUES (
        v_linha->>'customer_id', v_linha->>'campaign_id',
        (v_linha->>'metric_date')::date, v_seg_hash, v_seg,
        nullif(v_linha->>'volc_campaign_id', ''),
        nullif(v_linha->>'campaign_name', ''),
        nullif(v_linha->>'campaign_status', ''),
        nullif(v_linha->>'advertising_channel_type', ''),
        v_exec_id, (v_linha->>'colhida_em')::timestamptz, v_api,
        v_linha->>'currency_code',
        v_origem, v_origem <> 'D0', v_precedencia,
        (v_linha->>'impressoes')::bigint, (v_linha->>'cliques')::bigint,
        (v_linha->>'interacoes')::bigint, (v_linha->>'custo_micros')::bigint,
        (v_linha->>'conversoes')::numeric, (v_linha->>'todas_conversoes')::numeric,
        (v_linha->>'valor_conversoes')::numeric,
        (v_linha->>'valor_todas_conversoes')::numeric,
        (v_linha->>'ctr')::numeric, (v_linha->>'cpc_medio_micros')::numeric,
        (v_linha->>'custo_por_conversao_micros')::numeric,
        (v_linha->>'search_impression_share')::numeric,
        (v_linha->>'search_budget_lost_impression_share')::numeric,
        (v_linha->>'search_rank_lost_impression_share')::numeric,
        (v_linha->>'search_top_impression_share')::numeric,
        (v_linha->>'search_absolute_top_impression_share')::numeric,
        (v_linha->>'search_click_share')::numeric,
        (v_linha->>'search_exact_match_impression_share')::numeric,
        (v_linha->>'top_impression_percentage')::numeric,
        (v_linha->>'absolute_top_impression_percentage')::numeric,
        coalesce(v_linha->'metricas_extras', '{}'::jsonb), now()
      )
      ON CONFLICT (customer_id, campaign_id, metric_date, segments_hash)
      DO UPDATE SET
        segmentos = EXCLUDED.segmentos,
        volc_campaign_id = EXCLUDED.volc_campaign_id,
        campaign_name = EXCLUDED.campaign_name,
        campaign_status = EXCLUDED.campaign_status,
        advertising_channel_type = EXCLUDED.advertising_channel_type,
        execucao_id = EXCLUDED.execucao_id,
        colhida_em = EXCLUDED.colhida_em,
        api_versao = EXCLUDED.api_versao,
        currency_code = EXCLUDED.currency_code,
        origem_janela = EXCLUDED.origem_janela,
        janela_fechada = EXCLUDED.janela_fechada,
        precedencia = EXCLUDED.precedencia,
        impressoes = EXCLUDED.impressoes,
        cliques = EXCLUDED.cliques,
        interacoes = EXCLUDED.interacoes,
        custo_micros = EXCLUDED.custo_micros,
        conversoes = EXCLUDED.conversoes,
        todas_conversoes = EXCLUDED.todas_conversoes,
        valor_conversoes = EXCLUDED.valor_conversoes,
        valor_todas_conversoes = EXCLUDED.valor_todas_conversoes,
        ctr = EXCLUDED.ctr,
        cpc_medio_micros = EXCLUDED.cpc_medio_micros,
        custo_por_conversao_micros = EXCLUDED.custo_por_conversao_micros,
        search_impression_share = EXCLUDED.search_impression_share,
        search_budget_lost_impression_share = EXCLUDED.search_budget_lost_impression_share,
        search_rank_lost_impression_share = EXCLUDED.search_rank_lost_impression_share,
        search_top_impression_share = EXCLUDED.search_top_impression_share,
        search_absolute_top_impression_share = EXCLUDED.search_absolute_top_impression_share,
        search_click_share = EXCLUDED.search_click_share,
        search_exact_match_impression_share = EXCLUDED.search_exact_match_impression_share,
        top_impression_percentage = EXCLUDED.top_impression_percentage,
        absolute_top_impression_percentage = EXCLUDED.absolute_top_impression_percentage,
        metricas_extras = EXCLUDED.metricas_extras,
        atualizada_em = now();

      v_aceitas := v_aceitas + 1;
    END LOOP;

    -- projecao: fault-isolated, com desfecho nomeado no recibo.
    -- Default fechado: o workflow novo pede explicitamente `true`, mas um
    -- documento manual incompleto não projeta por acidente.
    v_projetar := coalesce((documento->>'projetar_compat')::boolean, false);
    IF v_rejeitadas > 0 AND v_resultado = 'ok' THEN
      v_resultado := CASE WHEN v_aceitas > 0 OR v_preteridas > 0 THEN 'parcial' ELSE 'falhou' END;
      IF v_resultado = 'parcial' THEN
        documento := jsonb_set(documento, '{motivo}', to_jsonb((v_rejeitadas::text || ' linhas rejeitadas pela RPC')::text), true);
      ELSE
        documento := jsonb_set(documento, '{motivo}', to_jsonb('todas as linhas foram rejeitadas pela RPC'::text), true);
      END IF;
    END IF;

    IF v_projetar AND v_aceitas > 0 THEN
      SELECT p.linhas, p.estado, p.erro_codigo
        INTO v_proj_linhas, v_proj_estado, v_proj_erro
        FROM public.volc_gads_projetar_daily_compat(v_exec_id) p;
    ELSIF v_projetar THEN
      v_proj_estado := 'nao_solicitada';
      v_proj_linhas := 0;
    END IF;

  ELSIF v_tipo = 'fechamento' THEN

    v_aceitas    := coalesce((documento->>'linhas_aceitas')::integer, 0);
    v_preteridas := coalesce((documento->>'linhas_preteridas')::integer, 0);
    v_rejeitadas := coalesce((documento->>'linhas_rejeitadas')::integer, 0);
    v_proj_estado := coalesce(documento->>'projecao_estado', 'nao_solicitada');
    v_proj_linhas := coalesce((documento->>'projecao_linhas')::integer, 0);

    SELECT
        coalesce(sum(e.linhas_aceitas), 0)::integer     AS aceitas,
        coalesce(sum(e.linhas_preteridas), 0)::integer  AS preteridas,
        coalesce(sum(e.linhas_rejeitadas), 0)::integer  AS rejeitadas,
        coalesce(sum(e.projecao_linhas), 0)::integer    AS projetadas,
        count(*)::integer                               AS lotes,
        coalesce(max(e.lote_ordinal), 0)::integer       AS maior
      INTO v_soma
      FROM public.trafego_coleta_execucao e
     WHERE e.execucao_chave = v_exec_chave
       AND e.tipo_lote = 'contas';

    -- ⚠️ FECHAMENTO NAO VEM ANTES DA ESCRITA. Fechar uma execucao que declara
    -- linha aceita sem nenhum lote gravado seria anunciar ingestao que nao
    -- aconteceu.
    IF v_soma.lotes = 0 AND (v_aceitas > 0 OR v_preteridas > 0 OR v_rejeitadas > 0) THEN
      RAISE EXCEPTION USING ERRCODE = '22023',
        MESSAGE = 'FECHAMENTO_SEM_ESCRITA: nenhum lote de contas registrado para '
                  || v_exec_chave;
    END IF;
    IF v_soma.lotes <> v_soma.maior THEN
      RAISE EXCEPTION USING ERRCODE = '22023',
        MESSAGE = 'LOTE_FALTANDO: ' || v_soma.lotes || ' lotes gravados mas o maior ordinal e '
                  || v_soma.maior;
    END IF;
    IF v_aceitas    <> v_soma.aceitas
       OR v_preteridas <> v_soma.preteridas
       OR v_rejeitadas <> v_soma.rejeitadas THEN
      RAISE EXCEPTION USING ERRCODE = '22023',
        MESSAGE = 'RECONCILIACAO_DIVERGENTE: declarado '
                  || v_aceitas || '/' || v_preteridas || '/' || v_rejeitadas
                  || ' e o ledger soma '
                  || v_soma.aceitas || '/' || v_soma.preteridas || '/' || v_soma.rejeitadas;
    END IF;

    -- O recibo tem de resolver EXATAMENTE as linhas persistidas.
    SELECT count(*)::integer INTO v_fatos
      FROM public.google_ads_campanha_dia g
      JOIN public.trafego_coleta_execucao e ON e.execucao_id = g.execucao_id
     WHERE e.execucao_chave = v_exec_chave
       AND e.tipo_lote = 'contas';

    IF v_fatos <> v_soma.aceitas THEN
      RAISE EXCEPTION USING ERRCODE = '22023',
        MESSAGE = 'RECIBO_NAO_RESOLVE_FATOS: ledger diz ' || v_soma.aceitas
                  || ' aceitas e a tabela tem ' || v_fatos || ' linhas desta execucao';
    END IF;

    IF v_proj_linhas <> v_soma.projetadas THEN
      RAISE EXCEPTION USING ERRCODE = '22023',
        MESSAGE = 'PROJECAO_DIVERGENTE: declarado ' || v_proj_linhas
                  || ' e o ledger soma ' || v_soma.projetadas;
    END IF;

  ELSE
    RAISE EXCEPTION USING ERRCODE = '22023',
      MESSAGE = 'TIPO_LOTE_INVALIDO: ' || coalesce(v_tipo, '(nulo)');
  END IF;

  INSERT INTO public.trafego_coleta_execucao (
    execucao_id, chave_idempotencia, execucao_chave,
    fonte, job, disparo, workflow_id, execucao_externa_id,
    api_versao, contrato_versao, contrato_sha256,
    tipo_lote, lote_ordinal,
    origem_janela, janela_inicio, janela_fim,
    iniciada_em, encerrada_em, duracao_ms, batimento_em,
    resultado, motivo, escopo,
    contas_tentadas, contas_aceitas, contas_recusadas,
    linhas_lidas, linhas_aceitas, linhas_preteridas, linhas_rejeitadas, rejeicoes,
    projecao_estado, projecao_linhas, projecao_erro_codigo,
    payload_sha256
  ) VALUES (
    v_exec_id, v_chave, v_exec_chave,
    documento->>'fonte', documento->>'job', documento->>'disparo',
    nullif(documento->>'workflow_id', ''), nullif(documento->>'execucao_externa_id', ''),
    v_api, documento->>'contrato_versao', documento->>'contrato_sha256',
    v_tipo, v_ordinal,
    v_origem, v_ini, v_fim,
    (documento->>'iniciada_em')::timestamptz,
    (documento->>'encerrada_em')::timestamptz,
    (documento->>'duracao_ms')::integer,
    (documento->>'batimento_em')::timestamptz,
    v_resultado, nullif(documento->>'motivo', ''), nullif(documento->>'escopo', ''),
    ARRAY(SELECT jsonb_array_elements_text(coalesce(documento->'contas_tentadas', '[]'::jsonb))),
    ARRAY(SELECT jsonb_array_elements_text(coalesce(documento->'contas_aceitas', '[]'::jsonb))),
    coalesce(documento->'contas_recusadas', '[]'::jsonb),
    v_aceitas + v_preteridas + v_rejeitadas,
    v_aceitas, v_preteridas, v_rejeitadas, v_rejeicoes,
    v_proj_estado, v_proj_linhas, v_proj_erro,
    v_payload
  );

  RETURN jsonb_build_object(
    'execucao_id',        v_exec_id,
    'chave_idempotencia', v_chave,
    'repetida',           false,
    'linhas_lidas',       v_aceitas + v_preteridas + v_rejeitadas,
    'linhas_aceitas',     v_aceitas,
    'linhas_preteridas',  v_preteridas,
    'linhas_rejeitadas',  v_rejeitadas,
    'rejeicoes',          v_rejeicoes,
    'projecao_estado',    v_proj_estado,
    'projecao_linhas',    v_proj_linhas,
    'projecao_erro_codigo', v_proj_erro,
    'resultado',          v_resultado
  );
END;
$$;

COMMENT ON FUNCTION public.volc_registrar_gads_campanha_dia(jsonb) IS
  'Unica porta de ingestao do fato campanha-dia. Idempotente pela chave, recusa a mesma chave com outro conteudo, aplica precedencia D0<D-1<backfill, projeta compatibilidade em bloco isolado e so fecha a execucao depois de reconciliar contra o que foi persistido.';


-- ─────────────────────────────────────────────── leitura de saude / deadman ──
--
-- View read-only para o QG e para o deadman. Nao decide, nao alerta, nao
-- persiste: mostra o ultimo fechamento por job e a idade do batimento. Quem
-- classifica SAUDAVEL/ATRASADO/FALHOU e o contrato de saude ja existente.
CREATE VIEW public.trafego_coleta_execucao_saude
  WITH (security_invoker = true) AS
SELECT
  e.job,
  e.origem_janela,
  e.execucao_chave,
  e.janela_inicio,
  e.encerrada_em,
  e.batimento_em,
  e.resultado,
  e.motivo,
  e.linhas_lidas,
  e.linhas_aceitas,
  e.linhas_preteridas,
  e.linhas_rejeitadas,
  e.projecao_estado,
  e.projecao_linhas,
  -- Idade e um FATO, nao um veredito. `SAUDAVEL` continua sendo derivado pelo
  -- contrato de saude, com schedule e tolerancia explicitos.
  (now() - e.batimento_em) AS idade_do_batimento
FROM public.trafego_coleta_execucao e
WHERE e.tipo_lote = 'fechamento';

COMMENT ON VIEW public.trafego_coleta_execucao_saude IS
  'Ultimo estado por fechamento de execucao. Fornece evidencia ao deadman; nao classifica saude sozinha.';


-- ────────────────────────────────────────────────────────────────── seguranca ──
--
-- O ACL padrao de `public` concede tudo a todos em toda tabela nova, e isso e
-- real no Supabase oficial. Por isso REVOKE vem antes de GRANT, e `service_role`
-- tambem perde escrita direta: a unica porta e a RPC.
ALTER TABLE public.trafego_coleta_execucao ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_coleta_execucao FORCE ROW LEVEL SECURITY;
ALTER TABLE public.google_ads_campanha_dia ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.google_ads_campanha_dia FORCE ROW LEVEL SECURITY;

REVOKE ALL ON public.trafego_coleta_execucao FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.google_ads_campanha_dia FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.trafego_coleta_execucao_saude FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.volc_registrar_gads_campanha_dia(jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.volc_gads_projetar_daily_compat(uuid) FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.volc_gads_uuid_da_chave(text) FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.trafego_coleta_execucao TO service_role;
GRANT SELECT ON public.google_ads_campanha_dia TO service_role;
GRANT SELECT ON public.trafego_coleta_execucao_saude TO service_role;
GRANT EXECUTE ON FUNCTION public.volc_registrar_gads_campanha_dia(jsonb) TO service_role;

NOTIFY pgrst, 'reload schema';
COMMIT;
