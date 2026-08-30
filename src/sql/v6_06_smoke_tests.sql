-- =====================================================================
-- v6 RBAC — Etapa 1 / Arquivo 6 de 6
-- Smoke tests READ-ONLY para confirmar que a Etapa 1 foi aplicada
-- corretamente e que NADA do legado mudou.
--
-- Este arquivo NÃO modifica nada. É apenas um conjunto de queries
-- para você (humano) rodar e olhar os resultados.
-- =====================================================================

-- 1) As 4 tabelas novas existem e estão vazias?
SELECT 'campaign_roles'                  AS tabela, count(*) AS rows FROM public.campaign_roles
UNION ALL SELECT 'campaign_members',                count(*) FROM public.campaign_members
UNION ALL SELECT 'campaign_commissions',            count(*) FROM public.campaign_commissions
UNION ALL SELECT 'daily_campaign_member_payouts',   count(*) FROM public.daily_campaign_member_payouts;
-- Esperado após Etapa 1:
--   campaign_roles                 = 4
--   campaign_members               = 0
--   campaign_commissions           = 0
--   daily_campaign_member_payouts  = 0

-- 2) O catálogo de roles foi semeado corretamente?
SELECT id, code, label FROM public.campaign_roles ORDER BY id;
-- Esperado: 4 linhas (OWNER, OPERATOR, REVIEWER, VIEWER)

-- 3) As 4 funções novas existem?
SELECT proname
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public'
   AND proname LIKE 'v6\_%' ESCAPE '\'
 ORDER BY proname;
-- Esperado:
--   v6_calculate_member_commission
--   v6_get_active_commission_rate
--   v6_populate_member_payouts_for_date
--   v6_populate_member_payouts_for_range

-- 4) NENHUM trigger novo foi criado em daily_campaign_metrics?
SELECT t.tgname
  FROM pg_trigger t
  JOIN pg_class c ON c.oid = t.tgrelid
 WHERE c.relname = 'daily_campaign_metrics'
   AND NOT t.tgisinternal
   AND t.tgname LIKE 'v6\_%' ESCAPE '\';
-- Esperado: 0 linhas. Etapa 1 NÃO instala triggers.

-- 5) O cálculo legado continua intacto? (estado do trigger antigo)
SELECT
    t.tgname,
    CASE WHEN t.tgenabled = 'D' THEN 'DISABLED' ELSE 'ENABLED' END AS state
  FROM pg_trigger t
  JOIN pg_class c ON c.oid = t.tgrelid
 WHERE c.relname = 'daily_campaign_metrics'
   AND t.tgname  = 'trigger_daily_campaign_commission_calculation';
-- Esperado: 1 linha, state = ENABLED.

-- 6) Smoke test da função pura (sem tocar em nenhuma tabela)
-- Caso simples: revenue=100, spend=20, commission=15%
-- Tax depende de get_tax_rate_for_date(CURRENT_DATE) — só queremos
-- confirmar que a função roda sem erro e devolve algum numérico.
SELECT public.v6_calculate_member_commission(100, 20, 15, CURRENT_DATE) AS result_smoke;
-- Esperado: um numérico (>= 0). Não importa o valor exato — só que não dê erro.

-- 7) Smoke test do lookup de vigência (vai retornar NULL porque
--    campaign_commissions ainda está vazio)
SELECT public.v6_get_active_commission_rate(
    '00000000-0000-0000-0000-000000000000'::uuid,
    'sentinela_inexistente',
    CURRENT_DATE
) AS result_lookup;
-- Esperado: NULL.
