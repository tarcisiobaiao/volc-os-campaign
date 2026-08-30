-- =====================================================================
-- v6 RBAC — Etapa 1 / Arquivo 4 de 6
-- Tabela de RESULTADO do cálculo novo de comissão (paralela ao
-- daily_campaign_metrics.commission_operator legado).
--
-- Uma linha por (data × campanha × usuário). Permite múltiplos usuários
-- por (data × campanha), o que o modelo legado NÃO permite (single
-- commission_operator field).
--
-- Esta tabela é PREENCHIDA POR DEMANDA via funções v6_populate_*
-- (definidas em v6_05). NÃO há trigger novo. NÃO interfere no pipeline
-- atual de gravação em daily_campaign_metrics.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.daily_campaign_member_payouts (
    id                    bigserial    PRIMARY KEY,
    "date"                date         NOT NULL,
    -- ON DELETE RESTRICT: histórico financeiro NÃO deve ser apagado em
    -- cascata se uma campanha ou usuário for removido. Decisão explícita
    -- (Etapa 1, revisão final). Para remover essas entidades no futuro,
    -- vai ser necessário arquivar/mover os payouts manualmente antes.
    campaign_id           varchar      NOT NULL REFERENCES public.campaigns(campaign_id) ON DELETE RESTRICT,
    user_id               uuid         NOT NULL REFERENCES public.users(id)              ON DELETE RESTRICT,
    commission_percentage numeric(7,4) NOT NULL,
    revenue_revshare      numeric(18,4) NOT NULL,
    spend                 numeric(18,4) NOT NULL,
    tax_rate              numeric(7,4) NOT NULL,
    tax_amount            numeric(18,4) NOT NULL,
    net_profit            numeric(18,4) NOT NULL,
    amount                numeric(18,4) NOT NULL,
    calculated_at         timestamptz  NOT NULL DEFAULT now(),
    source                text         NOT NULL DEFAULT 'v6_calculate_member_commission',

    CONSTRAINT dcmp_unique UNIQUE ("date", campaign_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_dcmp_date         ON public.daily_campaign_member_payouts ("date");
CREATE INDEX IF NOT EXISTS idx_dcmp_user_date    ON public.daily_campaign_member_payouts (user_id, "date");
CREATE INDEX IF NOT EXISTS idx_dcmp_campaign     ON public.daily_campaign_member_payouts (campaign_id);

COMMENT ON TABLE  public.daily_campaign_member_payouts IS
    'v6 RBAC — resultado diário do cálculo novo de comissão por membro. Paralelo ao daily_campaign_metrics.commission_operator (legado).';
COMMENT ON COLUMN public.daily_campaign_member_payouts.amount IS
    'Comissão final calculada para esse usuário/campanha/dia.';
COMMENT ON COLUMN public.daily_campaign_member_payouts.source IS
    'Identificador da função/versão que produziu este registro. Útil para reproducibilidade.';
