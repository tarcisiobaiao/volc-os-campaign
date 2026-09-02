-- v12_04 — rollback par a par do fato canonico Google Ads campanha-dia.
--
-- ## ROLLBACK QUE NINGUEM RODOU NAO E ROLLBACK
--
-- O da v9_03 estava escrito como "reaplique a v9_02" e ABORTAVA; so apareceu
-- quando alguem tentou. Este e executado a cada rodada de
-- `scripts/provar-ciclo-v12_04.sh`, num cluster descartavel, no ciclo
-- aplicar -> operar -> reverter -> reaplicar.
--
-- ## ELE RECUSA PERDA SILENCIOSA
--
-- Se houver fato ou recibo gravado, o rollback PARA e diz quantas linhas
-- morreriam. Para seguir mesmo assim e preciso declarar a intencao na sessao:
--
--     SET volc.rollback_v12_04_apagar_fatos = 'sim';
--     \i supabase/migrations/v12_04_rollback.sql
--
-- Tabela vazia dispensa a declaracao — nao ha o que perder.
--
-- ## O QUE ELE NAO DESFAZ, DITO SEM RODEIO
--
-- A projecao de compatibilidade ESCREVEU em colunas de `daily_campaign_metrics`
-- (impressions, clicks, spend, conversions, ctr, cpc, cost_per_conversion e as
-- seis de leilao Search). O rollback NAO reverte esses valores: o valor
-- anterior nao foi guardado, e inventar um seria pior do que declarar a lacuna.
-- Receita, revshare, GAM, comissao, orientacao e otimizacao nunca foram
-- tocados, entao nada ali precisa de reversao.

BEGIN;

DO $$
DECLARE
  fatos    bigint := 0;
  recibos  bigint := 0;
  permitir text := coalesce(current_setting('volc.rollback_v12_04_apagar_fatos', true), '');
BEGIN
  IF to_regclass('public.google_ads_campanha_dia') IS NULL
     AND to_regclass('public.trafego_coleta_execucao') IS NULL THEN
    RAISE EXCEPTION USING
      ERRCODE = '42P01',
      MESSAGE = 'ROLLBACK_SEM_ALVO: nem google_ads_campanha_dia nem '
                'trafego_coleta_execucao existem; a v12_04 nao esta aplicada';
  END IF;

  IF to_regclass('public.google_ads_campanha_dia') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.google_ads_campanha_dia' INTO fatos;
  END IF;
  IF to_regclass('public.trafego_coleta_execucao') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.trafego_coleta_execucao' INTO recibos;
  END IF;

  IF (fatos > 0 OR recibos > 0) AND permitir <> 'sim' THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'ROLLBACK_RECUSADO_PERDA_SILENCIOSA: ' || fatos || ' fatos e '
                || recibos || ' recibos seriam apagados. Declare a intencao com '
                || 'SET volc.rollback_v12_04_apagar_fatos = ''sim'' antes de reverter.';
  END IF;

  IF fatos > 0 OR recibos > 0 THEN
    RAISE NOTICE 'v12_04 rollback autorizado: apagando % fatos e % recibos', fatos, recibos;
  END IF;
END $$;

DROP VIEW  IF EXISTS public.trafego_coleta_execucao_saude;

DROP TRIGGER IF EXISTS trafego_coleta_execucao_append_only
  ON public.trafego_coleta_execucao;

DROP FUNCTION IF EXISTS public.volc_registrar_gads_campanha_dia(jsonb);
DROP FUNCTION IF EXISTS public.volc_gads_projetar_daily_compat(uuid);
DROP FUNCTION IF EXISTS public.volc_gads_uuid_da_chave(text);
DROP FUNCTION IF EXISTS public.trafego_coleta_execucao_append_only();

-- O fato referencia o ledger; a ordem importa.
DROP TABLE IF EXISTS public.google_ads_campanha_dia;
DROP TABLE IF EXISTS public.trafego_coleta_execucao;

NOTIFY pgrst, 'reload schema';
COMMIT;
