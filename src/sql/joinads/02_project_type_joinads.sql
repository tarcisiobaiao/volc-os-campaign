-- ============================================================================
-- Configuração do projeto da Join Ads
--
-- ⚠️ MUDANÇA DE DECISÃO (2026-08-11). Este arquivo propunha antes criar um
--    terceiro valor de enum, `JOINADS`. Foi descartado. A Join entra como
--    **project_type = 'GAM'**, e nenhum ALTER TYPE é necessário.
--
-- Por quê GAM e não um tipo novo: no VOLC O.S. o `project_type` não descreve o
-- fornecedor, descreve o COMPORTAMENTO do dado. `ADSENSE` é o tipo "receita
-- total, sem revshare" — por isso o front mostra "Revenue Total:" para ele e
-- "Revenue (após RevShare):" para os demais. A Join tem revshare (10%), tem
-- eixo de campanha, e suas métricas caem nas colunas `gam_*` da
-- daily_campaign_metrics. Comportamentalmente ela É GAM.
--
-- Consequência prática: **zero mudança no front**. O enum do TypeScript, o
-- `isAdSenseProject`, o seletor de tipo — nada disso precisa saber que a Join
-- existe. Um valor novo no enum obrigaria a mexer em ~6 pontos e a decidir, em
-- cada um, se JOINADS se comporta como GAM (a resposta seria "sim" em todos).
-- ============================================================================

-- ─── estado atual ───────────────────────────────────────────────────────────
--
-- O projeto NÃO precisa ser inserido: o trigger `trigger_daily_project_metrics_auto_fill`
-- já o criou sozinho no primeiro run do flow, via `get_or_create_project_id_by_url`,
-- e o criou com `project_type = 'GAM'`.
--
-- O que ele NÃO acertou foi o revshare, que nasceu 0:
--
--   id | project_name      | project_type | revshare
--    2 | creditoup.com.br  | GAM          | 0
--
-- Com revshare 0, `calculate_revshare_discount` faz `valor * (1 - 0)` e o
-- `revenue_converted_revshare` sai igual ao bruto — ou seja, os 10% da Join
-- nunca são descontados. É isso que o UPDATE abaixo corrige.

BEGIN;

UPDATE public.projects
SET revshare   = 0.10,
    taxes      = COALESCE(taxes, 0),
    updated_at = now()
WHERE domain = 'creditoup.com.br'
  AND project_type = 'GAM';

-- ─── recálculo retroativo ───────────────────────────────────────────────────
--
-- Mudar `projects.revshare` não mexe sozinho nas linhas já gravadas: quem
-- calcula o `revenue_converted_revshare` é um trigger BEFORE INSERT OR UPDATE,
-- então ele só roda de novo se a linha for tocada. O UPDATE abaixo é um no-op
-- de conteúdo que existe só para disparar o trigger.

UPDATE public.daily_project_metrics
SET updated_at = now()
WHERE project_id = (SELECT id FROM public.projects WHERE domain = 'creditoup.com.br');

-- Mesmo motivo do lado da campanha — lá quem calcula é o
-- `trigger_daily_campaign_revshare_calculation`.
UPDATE public.daily_campaign_metrics dcm
SET updated_at = now()
WHERE EXISTS (
    SELECT 1 FROM public.joinads_metrics jm
    WHERE jm.utm_campaign_value = dcm.campaign_id
      AND jm.date = dcm.date
);

COMMIT;

-- Conferir (revenue_converted_revshare deve ficar 90% do revenue_converted):
--   SELECT date, url_projeto, revenue, revenue_converted, revenue_converted_revshare
--   FROM daily_project_metrics
--   WHERE url_projeto = 'creditoup.com.br' ORDER BY date;
