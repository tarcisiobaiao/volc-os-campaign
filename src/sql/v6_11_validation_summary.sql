-- =====================================================================
-- v6 RBAC — Etapa 2 / Arquivo 11 de 11
-- VALIDAÇÃO READ-ONLY do estado pós-Etapa 2.
--
-- OBJETIVO
--   Bateria de queries agregadoras para você (humano) auditar
--   manualmente os números produzidos pelo backfill + populate.
--
-- TIPO DE OPERAÇÃO
--   100% read-only. Apenas SELECTs. Não modifica nada.
--
-- RISCO
--   Zero.
--
-- COMO USAR
--   Rode bloco a bloco no SQL Editor, capturando o resultado de cada
--   um. Os blocos estão organizados por nível de zoom: do total geral
--   para a amostragem fina.
--
-- REVERSÃO
--   Não aplicável.
-- =====================================================================

-- ----------------------------------------------------------------------
-- 1) TOTAL POR USUÁRIO — visão executiva
-- ----------------------------------------------------------------------
SELECT
    u.email                       AS operador,
    count(*)                      AS dias_com_payout,
    count(DISTINCT p.campaign_id) AS campanhas_distintas,
    SUM(p.revenue_revshare)       AS revenue_total,
    SUM(p.spend)                  AS spend_total,
    SUM(p.tax_amount)             AS impostos_total,
    SUM(p.net_profit)             AS lucro_liquido_total,
    SUM(p.amount)                 AS comissao_v6_total
  FROM public.daily_campaign_member_payouts p
  JOIN public.users u ON u.id = p.user_id
 GROUP BY u.email
 ORDER BY comissao_v6_total DESC;

-- ----------------------------------------------------------------------
-- 2) TOTAL MENSAL — Marlise
-- ----------------------------------------------------------------------
SELECT
    DATE_TRUNC('month', p."date")::date AS mes,
    count(*)                            AS linhas,
    count(DISTINCT p.campaign_id)       AS campanhas_distintas,
    SUM(p.revenue_revshare)             AS revenue,
    SUM(p.spend)                        AS spend,
    SUM(p.net_profit)                   AS lucro_liquido,
    SUM(p.amount)                       AS comissao
  FROM public.daily_campaign_member_payouts p
  JOIN public.users u ON u.id = p.user_id
 WHERE u.email = 'marliseac@gmail.com'
 GROUP BY 1
 ORDER BY 1;

-- ----------------------------------------------------------------------
-- 3) COMPARAÇÃO v6 (novo) × LEGADO — confirma o gap
-- ----------------------------------------------------------------------
SELECT
    'sum_amount_v6'           AS metric,
    COALESCE(sum(p.amount), 0)::text AS value
  FROM public.daily_campaign_member_payouts p
UNION ALL
SELECT 'sum_commission_legacy',
       COALESCE(sum(dcm.commission_operator), 0)::text
  FROM public.daily_campaign_metrics dcm
UNION ALL
SELECT 'gap_v6_minus_legacy',
       (COALESCE((SELECT sum(amount) FROM public.daily_campaign_member_payouts), 0)
      - COALESCE((SELECT sum(commission_operator) FROM public.daily_campaign_metrics), 0)
       )::text;
-- ESPERADO: sum_commission_legacy = 0 (todo o histórico)
-- e sum_amount_v6 ≫ 0. O gap representa exatamente o que o
-- sistema legado deveria ter pago e nunca pagou (por causa do bug).

-- ----------------------------------------------------------------------
-- 4) CINCO EXEMPLOS CONCRETOS — para conferência manual com calculadora
-- ----------------------------------------------------------------------
SELECT
    p."date",
    u.email,
    p.campaign_id,
    p.commission_percentage,
    p.revenue_revshare,
    p.spend,
    p.tax_rate,
    p.tax_amount,
    p.net_profit,
    p.amount,
    -- Recálculo independente para conferência
    ROUND(p.revenue_revshare * p.tax_rate, 4)                              AS recheck_tax,
    ROUND(p.revenue_revshare - p.spend - (p.revenue_revshare * p.tax_rate), 4) AS recheck_net,
    ROUND((p.revenue_revshare - p.spend - (p.revenue_revshare * p.tax_rate))
          * (p.commission_percentage / 100.0), 4)                          AS recheck_amount
  FROM public.daily_campaign_member_payouts p
  JOIN public.users u ON u.id = p.user_id
 WHERE p.amount > 0
 ORDER BY p.amount DESC
 LIMIT 5;
-- ESPERADO: as colunas recheck_* devem bater com tax_amount, net_profit
-- e amount linha por linha (até o arredondamento). Se divergir, há bug
-- na função v6_calculate_member_commission ou no populate.

-- ----------------------------------------------------------------------
-- 5) SANITY CHECK DE COBERTURA — buracos no backfill?
--    Para cada par (date, campaign_id) em daily_campaign_metrics
--    onde existe vigência ativa em campaign_commissions, deve haver
--    a linha correspondente em daily_campaign_member_payouts.
-- ----------------------------------------------------------------------
SELECT
    'expected_payout_keys' AS metric,
    count(*)::text         AS value
  FROM public.daily_campaign_metrics dcm
  JOIN public.campaign_commissions cc
    ON cc.campaign_id = dcm.campaign_id
   AND cc.valid_from <= dcm."date"
   AND (cc.valid_to IS NULL OR cc.valid_to >= dcm."date")
UNION ALL
SELECT 'actual_payout_keys',
       count(*)::text
  FROM public.daily_campaign_member_payouts
UNION ALL
SELECT 'missing_payout_keys',
       (SELECT count(*)
          FROM public.daily_campaign_metrics dcm
          JOIN public.campaign_commissions cc
            ON cc.campaign_id = dcm.campaign_id
           AND cc.valid_from <= dcm."date"
           AND (cc.valid_to IS NULL OR cc.valid_to >= dcm."date")
          LEFT JOIN public.daily_campaign_member_payouts p
            ON p."date" = dcm."date"
           AND p.campaign_id = dcm.campaign_id
           AND p.user_id    = cc.user_id
         WHERE p.id IS NULL)::text;
-- ESPERADO:
--   expected_payout_keys == actual_payout_keys
--   missing_payout_keys == 0

-- ----------------------------------------------------------------------
-- 6) PERFIL DOS PAYOUTS — distribuição
-- ----------------------------------------------------------------------
SELECT
    'payouts_total'              AS metric,
    count(*)::text               AS value
  FROM public.daily_campaign_member_payouts
UNION ALL
SELECT 'payouts_amount_gt_0',     count(*)::text
  FROM public.daily_campaign_member_payouts WHERE amount > 0
UNION ALL
SELECT 'payouts_amount_eq_0',     count(*)::text
  FROM public.daily_campaign_member_payouts WHERE amount = 0
UNION ALL
SELECT 'payouts_net_profit_gt_0', count(*)::text
  FROM public.daily_campaign_member_payouts WHERE net_profit > 0
UNION ALL
SELECT 'payouts_net_profit_le_0', count(*)::text
  FROM public.daily_campaign_member_payouts WHERE net_profit <= 0;
-- ESPERADO: net_profit_le_0 deve ser igual a amount_eq_0 (regra:
-- se lucro líquido <= 0, comissão = 0 por design da fórmula).

-- ----------------------------------------------------------------------
-- 7) TOP 10 CAMPANHAS QUE MAIS GERARAM COMISSÃO
-- ----------------------------------------------------------------------
SELECT
    p.campaign_id,
    c.campaign_name,
    count(*)               AS dias_calculados,
    SUM(p.revenue_revshare) AS revenue_total,
    SUM(p.spend)            AS spend_total,
    SUM(p.amount)           AS comissao_total
  FROM public.daily_campaign_member_payouts p
  LEFT JOIN public.campaigns c ON c.campaign_id = p.campaign_id
 GROUP BY p.campaign_id, c.campaign_name
 ORDER BY comissao_total DESC
 LIMIT 10;

-- ----------------------------------------------------------------------
-- 8) MEMBER SEM COMMISSION — confirma que Tarcisio Baiao (0%) virou
--    membro mas não tem linha em campaign_commissions.
-- ----------------------------------------------------------------------
SELECT
    u.email,
    count(DISTINCT cm.campaign_id) AS campanhas_member,
    count(DISTINCT cc.campaign_id) AS campanhas_com_comissao
  FROM public.users u
  LEFT JOIN public.campaign_members      cm ON cm.user_id = u.id
  LEFT JOIN public.campaign_commissions  cc ON cc.user_id = u.id
 WHERE u.role = 'OPERATOR'
 GROUP BY u.email
 ORDER BY u.email;
-- ESPERADO:
--   marliseac@gmail.com         | 306 | 306
--   hello@agenciavolc.com.br    | 0   | 0   (não tem vínculos em user_campaigns)
--
-- Se Tarcisio Baiao tiver vínculos em user_campaigns que não vimos
-- antes, vai aparecer como "X campanhas_member, 0 campanhas_com_comissao"
-- — exatamente o caso de uso "acesso sem comissão" funcionando.
