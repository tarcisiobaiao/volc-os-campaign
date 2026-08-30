-- =====================================================================
-- v6 RBAC — Etapa 2 / Arquivo 8 de 11
-- BACKFILL de campaign_members a partir do legado user_campaigns.
--
-- OBJETIVO
--   Popular a tabela nova campaign_members com TODOS os vínculos atuais
--   de user_campaigns, atribuindo a cada vínculo o role funcional
--   OPERATOR (decisão de design aprovada).
--
-- TIPO DE OPERAÇÃO
--   INSERT em tabela nova (campaign_members), 100% aditivo. Nada é
--   tocado em user_campaigns nem em qualquer outra tabela legada.
--
-- RISCO
--   Baixíssimo. INSERT com ON CONFLICT DO NOTHING (idempotente).
--   Pode ser re-executado sem efeito colateral.
--
-- ESPERADO
--   Após executar:
--     SELECT count(*) FROM public.campaign_members;
--   deve retornar 306 (mesmo número que user_campaigns).
--
--   Distribuição esperada:
--     - 2 user_id distintos (Marlise e Tarcisio Baiao)
--     - 306 campaign_id distintos (1 por linha, sem duplicatas)
--     - 100% role_id = id de 'OPERATOR' (id 2 no seed da Etapa 1)
--     - created_by = NULL em todas (não temos rastreio do criador original)
--     - created_at preservado de user_campaigns.created_at
--
-- REVERSÃO
--   TRUNCATE public.campaign_members;
--   (não dispara nada porque não há trigger novo, e o legado não
--    depende dessa tabela)
-- =====================================================================

INSERT INTO public.campaign_members (
    user_id,
    campaign_id,
    role_id,
    created_at,
    created_by
)
SELECT
    uc.user_id,
    uc.campaign_id,
    (SELECT id FROM public.campaign_roles WHERE code = 'OPERATOR'),
    uc.created_at,
    NULL
  FROM public.user_campaigns uc
ON CONFLICT (user_id, campaign_id, role_id) DO NOTHING;

-- ---------------------------------------------------------------------
-- Verificação rápida (read-only) — rode logo após o INSERT acima
-- para confirmar que o backfill bateu o esperado.
-- ---------------------------------------------------------------------
SELECT
    'campaign_members_total'    AS metric,
    count(*)::text              AS value
  FROM public.campaign_members
UNION ALL
SELECT 'distinct_users',         count(DISTINCT user_id)::text
  FROM public.campaign_members
UNION ALL
SELECT 'distinct_campaigns',     count(DISTINCT campaign_id)::text
  FROM public.campaign_members
UNION ALL
SELECT 'roles_used',             string_agg(DISTINCT cr.code, ',' ORDER BY cr.code)
  FROM public.campaign_members cm
  JOIN public.campaign_roles cr ON cr.id = cm.role_id
UNION ALL
SELECT 'created_by_null_pct',
       (100.0 * count(*) FILTER (WHERE created_by IS NULL) / NULLIF(count(*),0))::text
  FROM public.campaign_members;
-- ESPERADO:
--   campaign_members_total = 306
--   distinct_users         = 2
--   distinct_campaigns     = 306
--   roles_used             = 'OPERATOR'
--   created_by_null_pct    = 100
