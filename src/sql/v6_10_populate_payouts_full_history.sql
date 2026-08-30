-- =====================================================================
-- v6 RBAC — Etapa 2 / Arquivo 10 de 11
-- POPULATE histórico completo de daily_campaign_member_payouts.
--
-- OBJETIVO
--   Calcular e gravar os payouts diários do modelo novo para todo o
--   intervalo de dados existente em daily_campaign_metrics.
--   Faz isso chamando a função v6_populate_member_payouts_for_range,
--   que internamente itera dia a dia e faz UPSERT em
--   daily_campaign_member_payouts.
--
--   IMPORTANTE: a função SÓ insere linhas onde existe uma vigência
--   ativa em campaign_commissions para o dia/usuário/campanha. Dias
--   antes do valid_from da Marlise (2025-10-17) NÃO geram linhas
--   automaticamente.
--
-- TIPO DE OPERAÇÃO
--   INSERT/UPSERT em tabela nova (daily_campaign_member_payouts).
--   Nada é tocado em daily_campaign_metrics, user_campaigns ou users.
--   Não dispara nenhum trigger novo (Variante A — manual only).
--
-- RISCO
--   Médio em volume, baixo em impacto. Pode escrever dezenas de
--   milhares de linhas, mas TODAS em uma tabela vazia, isolada do
--   pipeline atual. Se algo der errado, TRUNCATE resolve.
--
-- TEMPO ESTIMADO
--   ~213 dias (2025-09-07 → 2026-04-06) iterados em PL/pgSQL. A função
--   filtra por vigência ativa, então a maior parte do trabalho real
--   acontece nos ~172 dias a partir de 2025-10-17. Estimativa de
--   tempo: dezenas de segundos a poucos minutos. NÃO há risco de
--   travar o legado porque não escreve em tabela monitorada por
--   triggers.
--
-- ESPERADO
--   Algumas dezenas de milhares de linhas em
--   daily_campaign_member_payouts. Todas para a Marlise (único
--   usuário com vigência ativa após backfill).
--
--   IMPORTANTE: cada linha calcula a comissão usando a MESMA fórmula
--   matemática que o legado *deveria* estar usando. Como o legado
--   está bugado (typo OPERADOR vs OPERATOR — vide v6_07), os valores
--   AQUI vão ser DIFERENTES de daily_campaign_metrics.commission_operator
--   (que está sempre em 0). Os valores corretos passarão a viver
--   exclusivamente nesta tabela nova até a Etapa 3 substituir a UI.
--
-- REVERSÃO
--   TRUNCATE public.daily_campaign_member_payouts;
-- =====================================================================

-- A chamada principal. A função retorna o número total de linhas
-- afetadas (inserted + updated).
SELECT public.v6_populate_member_payouts_for_range(
    '2025-09-07'::date,
    CURRENT_DATE
) AS total_rows_affected;

-- ---------------------------------------------------------------------
-- Verificação rápida (read-only)
-- ---------------------------------------------------------------------
SELECT
    'payouts_total'             AS metric,
    count(*)::text              AS value
  FROM public.daily_campaign_member_payouts
UNION ALL
SELECT 'distinct_users',         count(DISTINCT user_id)::text
  FROM public.daily_campaign_member_payouts
UNION ALL
SELECT 'distinct_dates',         count(DISTINCT "date")::text
  FROM public.daily_campaign_member_payouts
UNION ALL
SELECT 'min_date',               COALESCE(min("date")::text, 'NULL')
  FROM public.daily_campaign_member_payouts
UNION ALL
SELECT 'max_date',               COALESCE(max("date")::text, 'NULL')
  FROM public.daily_campaign_member_payouts
UNION ALL
SELECT 'sum_amount_total',       COALESCE(sum(amount)::text, '0')
  FROM public.daily_campaign_member_payouts
UNION ALL
SELECT 'rows_with_amount_gt_0',  count(*)::text
  FROM public.daily_campaign_member_payouts WHERE amount > 0
UNION ALL
SELECT 'rows_with_amount_eq_0',  count(*)::text
  FROM public.daily_campaign_member_payouts WHERE amount = 0;
-- ESPERADO:
--   payouts_total         > 0
--   distinct_users        = 1   (só a Marlise)
--   distinct_dates        ≤ 172 (Out/2025 até hoje)
--   min_date              ≥ 2025-10-17  (não pode ser anterior à vigência)
--   max_date              ≤ CURRENT_DATE
--   sum_amount_total      > 0   (validação primária da vida do sistema)
--   rows_with_amount_gt_0 > 0
--   rows_with_amount_eq_0 = inclui dias sem lucro (não é bug)
