-- ⏰ CRON JOB - Executar get_rotated_campaign_highlights() todo dia às 6AM
-- Este script cria um job agendado no Supabase usando pg_cron

-- 1️⃣ Habilitar a extensão pg_cron (se ainda não estiver habilitada)
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- 2️⃣ Criar o job que executa todo dia às 6AM (horário de Brasília/São Paulo)
SELECT cron.schedule(
  'update-campaign-highlights-daily',  -- Nome do job
  '0 6 * * *',                          -- Cron expression: 6AM todo dia
  $$
  SELECT get_rotated_campaign_highlights();
  $$
);

-- 3️⃣ OPCIONAL: Criar uma tabela para log de execuções
CREATE TABLE IF NOT EXISTS campaign_highlights_log (
  id BIGSERIAL PRIMARY KEY,
  executed_at TIMESTAMPTZ DEFAULT NOW(),
  total_campaigns INTEGER,
  em_alta_count INTEGER,
  estagnadas_count INTEGER,
  em_baixa_count INTEGER,
  success BOOLEAN DEFAULT TRUE,
  error_message TEXT
);

-- 4️⃣ OPCIONAL: Job com logging
SELECT cron.schedule(
  'update-campaign-highlights-with-log',
  '0 6 * * *',
  $$
  DO $$
  DECLARE
    v_total INTEGER;
    v_em_alta INTEGER;
    v_estagnadas INTEGER;
    v_em_baixa INTEGER;
  BEGIN
    -- Executar a função
    PERFORM get_rotated_campaign_highlights();

    -- Contar resultados
    SELECT COUNT(*) INTO v_total
    FROM campaign_highlights
    WHERE highlighted_at = CURRENT_DATE;

    SELECT COUNT(*) INTO v_em_alta
    FROM campaign_highlights
    WHERE highlighted_at = CURRENT_DATE AND category = 'em_alta';

    SELECT COUNT(*) INTO v_estagnadas
    FROM campaign_highlights
    WHERE highlighted_at = CURRENT_DATE AND category = 'estagnada';

    SELECT COUNT(*) INTO v_em_baixa
    FROM campaign_highlights
    WHERE highlighted_at = CURRENT_DATE AND category = 'em_baixa';

    -- Salvar log
    INSERT INTO campaign_highlights_log (
      total_campaigns,
      em_alta_count,
      estagnadas_count,
      em_baixa_count,
      success
    ) VALUES (
      v_total,
      v_em_alta,
      v_estagnadas,
      v_em_baixa,
      TRUE
    );

  EXCEPTION WHEN OTHERS THEN
    -- Em caso de erro, salvar no log
    INSERT INTO campaign_highlights_log (
      success,
      error_message
    ) VALUES (
      FALSE,
      SQLERRM
    );
  END $$;
  $$
);

-- 📋 COMANDOS ÚTEIS PARA GERENCIAR CRON JOBS:

-- Ver todos os jobs agendados:
-- SELECT * FROM cron.job;

-- Ver histórico de execuções:
-- SELECT * FROM cron.job_run_details ORDER BY start_time DESC LIMIT 10;

-- Deletar um job:
-- SELECT cron.unschedule('update-campaign-highlights-daily');

-- Ver logs das execuções (se criou a tabela de log):
-- SELECT * FROM campaign_highlights_log ORDER BY executed_at DESC LIMIT 10;

-- IMPORTANTE: No Supabase, o timezone padrão é UTC
-- Se quiser ajustar para horário de Brasília (UTC-3), use:
-- '0 9 * * *'  -- 9AM UTC = 6AM BRT (horário de Brasília)
