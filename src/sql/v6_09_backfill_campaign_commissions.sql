-- =====================================================================
-- v6 RBAC — Etapa 2 / Arquivo 9 de 11
-- BACKFILL de campaign_commissions a partir do legado.
--
-- OBJETIVO
--   Popular campaign_commissions com a taxa atual de comissão de cada
--   operador, versionada por vigência:
--     - percentage    = users.commission_percentage
--     - valid_from    = users.created_at::date  (data em que o usuário
--                       passou a existir no sistema — proxy para "início
--                       real da vigência de comissão")
--     - valid_to      = NULL  (vigente)
--     - created_by    = NULL  (sem rastreio)
--     - notes         = string explicando que veio de backfill
--
--   APENAS usuários com commission_percentage > 0 entram. Operadores
--   com 0% (ex: Tarcisio Baiao no estado atual) NÃO recebem linha aqui
--   — exatamente o comportamento desejado pela refatoração:
--   "ser member NÃO implica direito a comissão".
--
--   POR QUE NÃO usar user_campaigns.created_at?
--   No diagnóstico de Etapa 2 descobrimos que as 302 linhas da Marlise
--   em user_campaigns foram apagadas e re-inseridas em lote em
--   2026-03-30 20:32 UTC (provavelmente uma operação técnica de
--   ressincronização). Usar uc.created_at::date "congelaria" a vigência
--   da comissão em 2026-03-30, perdendo ~164 dias de período em que a
--   Marlise era operadora real do sistema. Trocando para
--   users.created_at::date, recuperamos a semântica correta:
--   a vigência começa quando o usuário virou usuário do sistema.
--
-- TIPO DE OPERAÇÃO
--   INSERT em tabela nova (campaign_commissions), 100% aditivo.
--
-- RISCO
--   Baixíssimo. ON CONFLICT DO NOTHING (idempotente). Sem efeito sobre
--   users.commission_percentage nem sobre user_campaigns.
--
-- ESPERADO
--   No estado atual do banco, apenas Marlise tem commission_percentage > 0
--   (15%). Ela tem 302 vínculos em user_campaigns; portanto o INSERT
--   vai produzir 302 linhas em campaign_commissions, todas com:
--     - percentage = 15.00
--     - valid_from = 2025-10-17  (Marlise.created_at::date)
--     - valid_to   = NULL
--
--   Confira via:
--     SELECT count(*), MIN(valid_from), MAX(valid_from)
--     FROM public.campaign_commissions;
--
-- REVERSÃO
--   TRUNCATE public.campaign_commissions;
-- =====================================================================

INSERT INTO public.campaign_commissions (
    user_id,
    campaign_id,
    percentage,
    valid_from,
    valid_to,
    created_by,
    notes
)
SELECT
    uc.user_id,
    uc.campaign_id,
    u.commission_percentage,
    u.created_at::date,
    NULL,
    NULL,
    'backfill from users.commission_percentage on ' || CURRENT_DATE::text
    || ' (valid_from = users.created_at::date)'
  FROM public.user_campaigns uc
  JOIN public.users u ON u.id = uc.user_id
 WHERE u.commission_percentage IS NOT NULL
   AND u.commission_percentage > 0
ON CONFLICT (user_id, campaign_id, valid_from) DO NOTHING;

-- ---------------------------------------------------------------------
-- Verificação rápida (read-only)
-- ---------------------------------------------------------------------
SELECT
    'commissions_total'           AS metric,
    count(*)::text                AS value
  FROM public.campaign_commissions
UNION ALL
SELECT 'distinct_users',           count(DISTINCT user_id)::text
  FROM public.campaign_commissions
UNION ALL
SELECT 'distinct_percentages',     string_agg(DISTINCT percentage::text, ',' ORDER BY percentage::text)
  FROM public.campaign_commissions
UNION ALL
SELECT 'min_valid_from',           COALESCE(min(valid_from)::text, 'NULL')
  FROM public.campaign_commissions
UNION ALL
SELECT 'max_valid_from',           COALESCE(max(valid_from)::text, 'NULL')
  FROM public.campaign_commissions
UNION ALL
SELECT 'rows_with_valid_to_null',  count(*)::text
  FROM public.campaign_commissions WHERE valid_to IS NULL;
-- ESPERADO (estado atual do banco):
--   commissions_total      = 302  (302 vínculos da Marlise; Tarcisio Baiao
--                                  fica de fora porque tem commission=0)
--   distinct_users         = 1   (só a Marlise)
--   distinct_percentages   = '15.0000'
--   min_valid_from         = 2025-10-17  (Marlise.created_at::date)
--   max_valid_from         = 2025-10-17  (mesma data para todas as 302)
--   rows_with_valid_to_null = 302  (todas vigentes)
