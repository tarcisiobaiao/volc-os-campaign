-- =====================================================================
-- v6 RBAC — Etapa 2 / Arquivo 7 de 11
-- DIAGNÓSTICO READ-ONLY do bug do legado: commission_operator = 0 em
-- 100% das 216 143 linhas de daily_campaign_metrics.
--
-- OBJETIVO
--   Reunir num único arquivo as queries que comprovam a causa raiz do
--   problema. Útil pra você (humano) reproduzir o diagnóstico no SQL
--   Editor sem depender da minha sessão.
--
-- TIPO DE OPERAÇÃO
--   100% read-only. Apenas SELECTs. Não modifica nada.
--
-- RISCO
--   Zero. Não há writes.
--
-- ESPERADO
--   Cada bloco abaixo tem um comentário "ESPERADO" descrevendo o que
--   você deve ver. Se algum bloco diferir do esperado, reporte antes
--   de seguir para v6_08.
--
-- REVERSÃO
--   Não aplicável (não escreve nada).
-- =====================================================================

-- ----------------------------------------------------------------------
-- 1) Histograma do commission_operator: confirma que NUNCA foi não-zero
-- ----------------------------------------------------------------------
SELECT 'rows_total'                AS metric, count(*)::text AS value
  FROM public.daily_campaign_metrics
UNION ALL
SELECT 'rows_commission_null',     count(*)::text
  FROM public.daily_campaign_metrics WHERE commission_operator IS NULL
UNION ALL
SELECT 'rows_commission_zero',     count(*)::text
  FROM public.daily_campaign_metrics WHERE commission_operator = 0
UNION ALL
SELECT 'rows_commission_positive', count(*)::text
  FROM public.daily_campaign_metrics WHERE commission_operator > 0
UNION ALL
SELECT 'min_commission_operator',  COALESCE(min(commission_operator)::text, 'NULL')
  FROM public.daily_campaign_metrics
UNION ALL
SELECT 'max_commission_operator',  COALESCE(max(commission_operator)::text, 'NULL')
  FROM public.daily_campaign_metrics;
-- ESPERADO: rows_commission_zero == rows_total, todos os demais 0 ou NULL.
-- Confirma que o sistema legado nunca produziu um único centavo.

-- ----------------------------------------------------------------------
-- 2) Tax rate é razoável? Não é o problema.
-- ----------------------------------------------------------------------
SELECT '2025-09-07' AS date, public.get_tax_rate_for_date('2025-09-07'::date) AS tax_rate
UNION ALL SELECT '2025-10-17', public.get_tax_rate_for_date('2025-10-17'::date)
UNION ALL SELECT '2025-12-01', public.get_tax_rate_for_date('2025-12-01'::date)
UNION ALL SELECT '2026-01-01', public.get_tax_rate_for_date('2026-01-01'::date)
UNION ALL SELECT '2026-04-06', public.get_tax_rate_for_date('2026-04-06'::date);
-- ESPERADO: valores na casa de 0.08-0.12 (8% a 12%). Não está alto o
-- suficiente para zerar net_profit. Logo, tax_rate NÃO é o problema.

-- ----------------------------------------------------------------------
-- 3) Cálculo manual em SQL puro para 5 dias da Marlise.
--    Mostra que matematicamente DEVERIA haver comissão > 0,
--    mas o campo legado está sempre 0.
-- ----------------------------------------------------------------------
WITH marlise AS (
    SELECT id, commission_percentage
      FROM public.users
     WHERE email = 'marliseac@gmail.com'
),
dados AS (
    SELECT
        dcm.date,
        dcm.campaign_id,
        dcm.spend::numeric                       AS spend,
        dcm.revenue_converted_revshare::numeric  AS rev_revshare,
        public.get_tax_rate_for_date(dcm.date)   AS tax_rate,
        dcm.commission_operator                  AS legacy_commission,
        (SELECT commission_percentage FROM marlise) AS pct
      FROM public.daily_campaign_metrics dcm
      JOIN public.user_campaigns uc ON uc.campaign_id = dcm.campaign_id
     WHERE uc.user_id = (SELECT id FROM marlise)
       AND dcm.revenue_converted_revshare > dcm.spend
       AND dcm.date >= '2026-04-01'
     ORDER BY dcm.date DESC, dcm.revenue_converted_revshare DESC
     LIMIT 5
)
SELECT
    date,
    campaign_id,
    spend,
    rev_revshare,
    tax_rate,
    ROUND(rev_revshare * tax_rate, 2)                                  AS tax_amount,
    ROUND(rev_revshare - spend - (rev_revshare * tax_rate), 2)         AS net_profit_calc,
    ROUND((rev_revshare - spend - (rev_revshare * tax_rate)) * (pct/100), 2) AS expected_commission_15pct,
    legacy_commission,
    CASE
        WHEN legacy_commission = 0
         AND (rev_revshare - spend - (rev_revshare * tax_rate)) * (pct/100) > 0
        THEN 'BUG: deveria ter comissão > 0'
        ELSE 'ok'
    END AS bug_marker
  FROM dados;
-- ESPERADO: 5 linhas onde expected_commission_15pct > 0 e
-- legacy_commission = 0.00. Coluna bug_marker = 'BUG: deveria ter comissão > 0'.

-- ----------------------------------------------------------------------
-- 4) A definição atual do trigger inline mostra a causa raiz: typo.
--    A função filtra u.role = 'OPERADOR' (português) mas no banco
--    real users.role = 'OPERATOR' (inglês).
-- ----------------------------------------------------------------------
SELECT pg_get_functiondef(p.oid) AS function_definition
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public'
   AND p.proname  = 'trigger_calculate_commission_operator';
-- ESPERADO: na cláusula WHERE da query SELECT que busca operator_commission_pct,
-- você vê literalmente:   AND u.role = 'OPERADOR'
-- Isso é o bug. Os roles reais são 'ADMIN' e 'OPERATOR'.

-- ----------------------------------------------------------------------
-- 5) Confirmação direta: contar quantos users.role = 'OPERADOR' vs 'OPERATOR'
-- ----------------------------------------------------------------------
SELECT role, count(*) AS total
  FROM public.users
 GROUP BY role
 ORDER BY role;
-- ESPERADO: ADMIN e OPERATOR. Zero linhas com role = 'OPERADOR'.
-- Por isso o trigger nunca encontra match e sempre retorna 0.

-- ----------------------------------------------------------------------
-- 6) A função "boa" (calculate_operator_commission) usa 'OPERATOR'
--    correto, mas NÃO é chamada pelo trigger inline acima.
--    Ela só é chamada pelo trigger_update_user_commission, que só
--    dispara em UPDATE de users.commission_percentage.
-- ----------------------------------------------------------------------
SELECT pg_get_functiondef(p.oid) AS function_definition
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public'
   AND p.proname IN ('calculate_operator_commission',
                     'get_campaign_operator_commission_percentage')
 ORDER BY p.proname;
-- ESPERADO: ambas as funções usam u.role = 'OPERATOR' (correto).
-- A discrepância está SÓ no trigger inline, que duplica a lógica.
