-- Rollback v12_03 — devolve o CHECK `trafego_google_coleta_tipo` aos seis
-- valores da v12_01.
--
-- ⚠️ NAO e destrutivo por desenho, e NAO apaga recibo. Ele RECUSA rodar
-- enquanto existir qualquer linha gravada sob um dos seis `tipo_sinal` que a
-- v12_03 introduziu.
--
-- ## Por que recusar em vez de limpar
--
-- `ADD CONSTRAINT ... CHECK` valida as linhas existentes: com um unico recibo
-- PMax gravado, restaurar o CHECK antigo aborta de qualquer jeito. As duas
-- saidas seriam apagar os recibos ou desligar o gatilho append-only para
-- reescreve-los — e as duas destroem observabilidade ja provada para desfazer
-- uma ampliacao de vocabulario. Um rollback que apaga recibo em silencio e
-- pior que um rollback que se recusa e diz quantos sao.
--
-- ## O que fazer quando ele recusar
--
-- 1. exportar as linhas PMax (`SELECT ... WHERE tipo_sinal LIKE 'PMAX_%'`);
-- 2. decidir, com dono e registro, arquivar ou descartar;
-- 3. remover as linhas EXPLICITAMENTE — o gatilho append-only recusa DELETE, e
--    contorna-lo e um ato deliberado que precisa de dono, nao um efeito
--    colateral deste arquivo;
-- 4. so entao reexecutar este rollback.
--
-- `PMAX_RECOMENDACOES_FORCA` nao aparece nesta conta: ela grava em
-- `RECOMENDACOES_ARMAZENADAS`, que e valor da v12_01 e sobrevive ao rollback.
-- Reverter a v12_03 NAO apaga a setima familia — ela nunca dependeu dela.

BEGIN;

DO $$
DECLARE
  definicao text;
  n         bigint;
BEGIN
  IF to_regclass('public.trafego_google_inteligencia_coleta') IS NULL THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'nada a reverter: public.trafego_google_inteligencia_coleta nao existe';
  END IF;

  SELECT pg_get_constraintdef(c.oid) INTO definicao
    FROM pg_constraint c
   WHERE c.conrelid = 'public.trafego_google_inteligencia_coleta'::regclass
     AND c.conname  = 'trafego_google_coleta_tipo';

  IF definicao IS NULL OR position('PMAX_CAMPANHA' in definicao) = 0 THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'v12_03 nao esta aplicada: trafego_google_coleta_tipo nao admite PMAX_CAMPANHA';
  END IF;

  SELECT count(*) INTO n
    FROM public.trafego_google_inteligencia_coleta
   WHERE tipo_sinal IN (
     'PMAX_CAMPANHA', 'PMAX_ASSET_GROUPS', 'PMAX_ASSET_GROUP_ASSETS',
     'PMAX_ASSETS', 'PMAX_DESEMPENHO_ASSET_GROUP', 'PMAX_SINAIS'
   );

  IF n > 0 THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = format(
        'rollback v12_03 recusado: %s recibo(s) gravados sob tipo_sinal PMax. '
        'Restaurar o CHECK antigo com eles no lugar abortaria a validacao; '
        'apaga-los aqui destruiria observabilidade provada em silencio. '
        'Exporte, decida com dono e remova explicitamente antes de reverter.', n
      );
  END IF;
END $$;

ALTER TABLE public.trafego_google_inteligencia_coleta
  DROP CONSTRAINT trafego_google_coleta_tipo;

ALTER TABLE public.trafego_google_inteligencia_coleta
  ADD CONSTRAINT trafego_google_coleta_tipo
  CHECK (tipo_sinal IN (
    'DIAGNOSTICO_ENTREGA',
    'RECOMENDACOES_ARMAZENADAS',
    'RECOMENDACOES_GERADAS',
    'SIMULACOES_CAMPANHA',
    'FORECAST_KEYWORDS',
    'EXPERIMENTOS'
  ));

COMMENT ON CONSTRAINT trafego_google_coleta_tipo
  ON public.trafego_google_inteligencia_coleta IS
  'Os seis valores da v12_01. As familias estruturais PMax voltaram a nao ter lugar no ledger.';

NOTIFY pgrst, 'reload schema';
COMMIT;
