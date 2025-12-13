-- CRON JOB PARA ATUALIZAR CAMPANHAS DESTACADAS DIARIAMENTE ÀS 6AM (9AM UTC)
-- ⚠️ Este é o ÚNICO lugar que deve inserir dados na tabela campaign_highlights

-- Verificar se já existe um cron job
SELECT * FROM cron.job WHERE jobname = 'refresh_campaign_highlights_daily';

-- Se existir, deletar o antigo
SELECT cron.unschedule('refresh_campaign_highlights_daily');

-- Criar novo cron job que roda às 6AM (Brasília) = 9AM UTC
SELECT cron.schedule(
  'refresh_campaign_highlights_daily',  -- Nome do job
  '0 9 * * *',                          -- 9AM UTC = 6AM Brasília (todo dia)
  $$SELECT refresh_campaign_highlights();$$  -- Chama a função de refresh
);

-- Verificar se foi criado
SELECT * FROM cron.job WHERE jobname = 'refresh_campaign_highlights_daily';
