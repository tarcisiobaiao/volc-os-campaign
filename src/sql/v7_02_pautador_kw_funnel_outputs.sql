-- =====================================================================
-- v7 PAUTADOR PRO — Etapa 2 / Arquivo 1 de 1  (INCREMENTAL, ADITIVO)
-- Adiciona colunas JSONB para armazenar a saída REAL dos pipelines:
--   - Minerador (Fase 2): Google Ads + DataForSEO -> Gold Miner -> Funnel Prospector -> Funnel Factory
--   - Construtor de Funis (Fase 3): Arquiteto -> Page Factory (writingJobs)
--
-- NÃO destrutivo. Idempotente (ADD COLUMN IF NOT EXISTS). Roda DEPOIS de
-- src/sql/v7_01_create_pautador_tables.sql.
-- >>> Rodar manualmente no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
--
-- Mapeia 1:1 com:
--   - backend/app/agents/mining/orchestrator.py  (MiningOrchestrator.run -> dict)
--   - backend/app/agents/funnel_pro/orchestrator.py (FunnelProOrchestrator.run -> dict)
--   - backend/app/schemas.py  (MineResponse / FunnelResponse)
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. pautador_keyword_clusters — saída rica do Minerador (Fase 2)
--    A coluna `keywords` (v7_01) continua sendo o cluster compacto p/ a UI.
--    Estas colunas guardam o resultado completo do pipeline n8n portado.
-- ---------------------------------------------------------------------
ALTER TABLE public.pautador_keyword_clusters
    ADD COLUMN IF NOT EXISTS raw_keywords         jsonb,   -- keywords mescladas classificadas (Mega Merge + Google Ads)
    ADD COLUMN IF NOT EXISTS production_ads_queue jsonb,   -- Gold Miner: fila de ADS (titans/future/gems)
    ADD COLUMN IF NOT EXISTS content_seo_queue    jsonb,   -- Gold Miner: fila de CONTEÚDO (questions/hidden/seasonal)
    ADD COLUMN IF NOT EXISTS funis_sugeridos      jsonb,   -- Funnel Prospector: temas-pai/sub-intenções
    ADD COLUMN IF NOT EXISTS factory_output       jsonb,   -- Funnel Factory: fila de produção por funil
    ADD COLUMN IF NOT EXISTS summary              jsonb,   -- Gold Miner: summary/breakdown
    ADD COLUMN IF NOT EXISTS metrics              jsonb,   -- contagens do pipeline
    ADD COLUMN IF NOT EXISTS services_used        jsonb,   -- ["google_ads:mock","dataforseo:mock","gemini:seed_optimizer",...]
    ADD COLUMN IF NOT EXISTS warnings             jsonb,   -- avisos (serviço ausente, fallback, etc.)
    ADD COLUMN IF NOT EXISTS engine               text;    -- 'live' | 'mock'

COMMENT ON COLUMN public.pautador_keyword_clusters.production_ads_queue IS
    'Fase 2 (Gold Miner): keywords aprovadas para ADS, ordenadas por volume.';
COMMENT ON COLUMN public.pautador_keyword_clusters.factory_output IS
    'Fase 2 (Funnel Factory): fila de produção (1 item por funil sugerido).';

-- ---------------------------------------------------------------------
-- 2. pautador_funnels — saída rica do Construtor de Funis (Fase 3)
--    A tabela é 1 linha por página (v7_01). Estas colunas (denormalizadas,
--    mesmo valor em cada página do funil) guardam a estratégia e os jobs.
-- ---------------------------------------------------------------------
ALTER TABLE public.pautador_funnels
    ADD COLUMN IF NOT EXISTS strategy      jsonb,   -- funnel_strategy {avatar_summary, tone_voice, total_pages}
    ADD COLUMN IF NOT EXISTS pages         jsonb,   -- snapshot de todas as páginas (FunnelPage[])
    ADD COLUMN IF NOT EXISTS writing_jobs  jsonb,   -- Page Factory: writingJobs (briefing por página)
    ADD COLUMN IF NOT EXISTS raw_output    jsonb,   -- JSON cru do Arquiteto (funnel_strategy + pages)
    ADD COLUMN IF NOT EXISTS services_used jsonb,   -- ["gemini:funnel_architect"] | ["funnel_architect:fallback"]
    ADD COLUMN IF NOT EXISTS warnings      jsonb;

COMMENT ON COLUMN public.pautador_funnels.writing_jobs IS
    'Fase 3 (Page Factory): pacote writingJobs para o redator humano (briefing por página).';

-- =====================================================================
-- Verificação (opcional)
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name='pautador_keyword_clusters' AND column_name IN
--   ('production_ads_queue','content_seo_queue','funis_sugeridos','factory_output');
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name='pautador_funnels' AND column_name IN ('writing_jobs','strategy','pages');
-- =====================================================================
