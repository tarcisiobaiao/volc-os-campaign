-- v12_03 — o vocabulario do ledger aprende as seis familias estruturais PMax
--
-- Autoridade: database.agenciavolc.com.br.
-- Esta migration NAO cria tabela, NAO cria coluna, NAO reescreve recibo e NAO
-- decide nada sobre campanha. Ela faz UMA coisa: amplia o CHECK
-- `trafego_google_coleta_tipo` da v12_01 para que seis leituras que ja existem
-- deixem de ser recusadas na porta do banco.
--
-- ## Por que so o CHECK
--
-- A leitura read-only de Performance Max responde SETE perguntas independentes
-- (`volc_ads/inteligencia_google/pmax.py`). Seis delas nao tinham valor honesto
-- no vocabulario de seis da v12_01, e gravar sob um dos existentes faria um
-- recibo PMax responder por outra pergunta — `DIAGNOSTICO_ENTREGA`, em
-- particular, e lido pelo diagnostico Search da MESMA campanha
-- (`backend/app/trafego/diagnostico_persistido.py`). Entao a coleta parava a
-- persistencia dessas seis e nomeava a lacuna. Esta migration fecha a lacuna.
--
-- A setima — `PMAX_RECOMENDACOES_FORCA` — NAO ganha valor proprio e continua em
-- `RECOMENDACOES_ARMAZENADAS`: ela E uma leitura de `recommendation`, e o que a
-- distingue da varredura de conta e `campaign_id` mais `payload.familia`. Criar
-- um setimo valor duplicaria a mesma pergunta sob dois nomes.
--
-- ## O que esta migration deliberadamente NAO faz
--
-- Nenhuma coluna nova para metrica, asset, sinal ou payload PMax. A leitura
-- real de 01/09/2026 (`docs/closure/hermes-p04-t07-pmax-real-read-v1/`) provou
-- que as sete familias respondem, mas com volume baixo demais para decidir
-- normalizacao — e nove campos que a v25 REAL recusou com `UNRECOGNIZED_FIELD`
-- jamais podem virar coluna, porque seriam colunas que nunca recebem valor.
-- Item e metrica continuam nas tabelas que ja existem.

BEGIN;

DO $$
DECLARE
  definicao text;
  faltando  text[];
BEGIN
  IF to_regclass('public.trafego_google_inteligencia_coleta') IS NULL THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'v12_03 exige a v12_01: public.trafego_google_inteligencia_coleta nao existe';
  END IF;

  SELECT pg_get_constraintdef(c.oid) INTO definicao
    FROM pg_constraint c
   WHERE c.conrelid = 'public.trafego_google_inteligencia_coleta'::regclass
     AND c.conname  = 'trafego_google_coleta_tipo';

  IF definicao IS NULL THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'v12_03 exige o CHECK trafego_google_coleta_tipo da v12_01; ele nao esta na tabela';
  END IF;

  -- Ja aplicada: recusa NOMEADA, e nao um DROP/ADD silencioso. Reaplicar por
  -- cima esconderia que alguem ja mexeu no vocabulario entre as duas execucoes.
  IF position('PMAX_CAMPANHA' in definicao) > 0 THEN
    RAISE EXCEPTION USING
      ERRCODE = '42710',
      MESSAGE = 'v12_03 ja aplicada: trafego_google_coleta_tipo ja admite PMAX_CAMPANHA';
  END IF;

  -- ⚠️ A guarda que impede esta migration de APAGAR vocabulario. Ela substitui
  -- o CHECK inteiro; se o CHECK encontrado nao for o da v12_01 — porque alguem
  -- ja o alterou a mao — reescreve-lo aqui removeria silenciosamente valores em
  -- uso. Fail-closed, com os valores que faltam ditos por nome.
  faltando := ARRAY(
    SELECT v FROM unnest(ARRAY[
      'DIAGNOSTICO_ENTREGA', 'RECOMENDACOES_ARMAZENADAS', 'RECOMENDACOES_GERADAS',
      'SIMULACOES_CAMPANHA', 'FORECAST_KEYWORDS', 'EXPERIMENTOS'
    ]) AS v
    WHERE position(v in definicao) = 0
  );
  IF array_length(faltando, 1) IS NOT NULL THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = format(
        'v12_03 recusada: o CHECK atual nao admite %s; ampliar por cima dele '
        'apagaria vocabulario em uso', array_to_string(faltando, ', ')
      );
  END IF;
END $$;

ALTER TABLE public.trafego_google_inteligencia_coleta
  DROP CONSTRAINT trafego_google_coleta_tipo;

-- ⚠️ ADD CONSTRAINT valida as linhas que ja estao la. Como este CHECK so
-- AMPLIA, nenhuma linha existente pode ser rejeitada — e se alguma fosse, a
-- migration abortaria inteira, que e o comportamento desejado.
ALTER TABLE public.trafego_google_inteligencia_coleta
  ADD CONSTRAINT trafego_google_coleta_tipo
  CHECK (tipo_sinal IN (
    -- os seis da v12_01, preservados byte a byte
    'DIAGNOSTICO_ENTREGA',
    'RECOMENDACOES_ARMAZENADAS',
    'RECOMENDACOES_GERADAS',
    'SIMULACOES_CAMPANHA',
    'FORECAST_KEYWORDS',
    'EXPERIMENTOS',
    -- as seis familias estruturais de Performance Max (v12_03)
    'PMAX_CAMPANHA',
    'PMAX_ASSET_GROUPS',
    'PMAX_ASSET_GROUP_ASSETS',
    'PMAX_ASSETS',
    'PMAX_DESEMPENHO_ASSET_GROUP',
    'PMAX_SINAIS'
  ));

COMMENT ON CONSTRAINT trafego_google_coleta_tipo
  ON public.trafego_google_inteligencia_coleta IS
  'Doze valores: os seis da v12_01 mais as seis familias estruturais PMax da v12_03. A setima familia PMax (PMAX_RECOMENDACOES_FORCA) NAO tem valor proprio: ela grava em RECOMENDACOES_ARMAZENADAS e e distinguida por campaign_id mais payload.familia.';

NOTIFY pgrst, 'reload schema';
COMMIT;
