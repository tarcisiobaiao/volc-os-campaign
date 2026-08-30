-- ============================================================================
-- Limpeza das linhas gravadas pelos flows ANTES das correções de 2026-08-11.
--
-- Três defeitos produziram dado ruim nos primeiros runs:
--
--  1. A Join agrega o período inteiro numa linha só quando start_date != end_date
--     e devolve `date` como "10/08/2026 à 11/08/2026". O parser antigo casava o
--     prefixo e gravava o total de 2 dias como se fosse do dia 10.
--
--  2. O normalizador reconstruía o bruto dividindo `revenue_client` por 0,9 —
--     mas a API já devolve `revenue` bruto (campo ausente da doc). Resultado:
--     receita 11% inflada (0,01 virou 0,011111).
--
--  3. A API ignora o `custom_key` pedido quando não há dado para ele e devolve
--     outro. Pedimos `utm_campaign`, veio `land_uri` — e o valor "/" entrou
--     como se fosse id de campanha, inclusive na daily_campaign_metrics.
--
-- Os defeitos 1 e 2 se corrigem sozinhos: rodar o flow corrigido faz upsert por
-- (date, url_projeto) e sobrescreve. O defeito 3 NÃO — nenhum upsert apaga uma
-- linha com chave que não existe mais na origem. Por isso este arquivo.
--
-- Conferir antes de rodar:
--   SELECT * FROM joinads_metrics;
--   SELECT * FROM daily_campaign_metrics WHERE campaign_id = '/';
-- ============================================================================

BEGIN;

-- ─── 1. linhas de campanha que na verdade são land_uri ──────────────────────
--
-- Um utm_campaign de verdade nunca começa com "/" nem contém "://". Se o site
-- já tiver campanhas reais quando você rodar isto, o filtro não encosta nelas.

DELETE FROM public.daily_campaign_metrics
WHERE campaign_id LIKE '/%' OR campaign_id LIKE '%://%';

DELETE FROM public.joinads_metrics
WHERE utm_campaign_value LIKE '/%' OR utm_campaign_value LIKE '%://%';

-- ─── 2. receita inflada pelo gross-up indevido ──────────────────────────────
--
-- Em vez de tentar desfazer a conta (arriscado — não dá para distinguir uma
-- linha inflada de uma legítima só pelo valor), apagamos a janela afetada e
-- deixamos o flow corrigido reingerir. O upsert repõe com o valor certo.

DELETE FROM public.daily_project_metrics
WHERE url_projeto = 'creditoup.com.br'
  AND date BETWEEN '2026-08-09' AND '2026-08-11';

COMMIT;

-- Depois: rodar o flow "JOIN ADS - REPORT - DAY BEFORE" manualmente uma vez
-- (ou via webhook com {"lookback_days": 5}) para repor a janela com dado limpo.
