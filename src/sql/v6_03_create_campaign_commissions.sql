-- =====================================================================
-- v6 RBAC — Etapa 1 / Arquivo 3 de 6
-- Comissão explícita, opcional e VERSIONADA por vigência (valid_from/valid_to).
--
-- Decisões de design:
-- 1) Existência de linha = direito a comissão. SEM linha = sem comissão
--    (mesmo que o usuário seja membro da campanha).
-- 2) Versionamento por vigência: mudar a taxa NÃO reescreve histórico.
--    Cria-se uma nova linha; a antiga ganha valid_to.
-- 3) Granularidade: por par (user_id × campaign_id). Não é por usuário só.
-- 4) NÃO usamos EXCLUDE constraint pra non-overlap aqui (exigiria
--    btree_gist). Não-overlap é responsabilidade da camada de aplicação.
--    Uma query de validação para sobreposições pode ser criada na Etapa 2.
--
-- Aditivo. Não toca em users.commission_percentage (legado continua).
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.campaign_commissions (
    id          bigserial   PRIMARY KEY,
    user_id     uuid        NOT NULL REFERENCES public.users(id)             ON DELETE CASCADE,
    campaign_id varchar     NOT NULL REFERENCES public.campaigns(campaign_id) ON DELETE CASCADE,
    percentage  numeric(7,4) NOT NULL,
    valid_from  date        NOT NULL,
    valid_to    date,
    created_at  timestamptz NOT NULL DEFAULT now(),
    created_by  uuid        REFERENCES public.users(id) ON DELETE SET NULL,
    notes       text,

    CONSTRAINT campaign_commissions_percentage_range
        CHECK (percentage >= 0 AND percentage <= 100),
    CONSTRAINT campaign_commissions_valid_range
        CHECK (valid_to IS NULL OR valid_to >= valid_from),
    -- Impede dois registros com a mesma data de início (defesa básica
    -- contra inserção duplicada da mesma alteração).
    CONSTRAINT campaign_commissions_unique_start
        UNIQUE (user_id, campaign_id, valid_from)
);

CREATE INDEX IF NOT EXISTS idx_campaign_commissions_lookup
    ON public.campaign_commissions (user_id, campaign_id, valid_from);

CREATE INDEX IF NOT EXISTS idx_campaign_commissions_campaign
    ON public.campaign_commissions (campaign_id);

CREATE INDEX IF NOT EXISTS idx_campaign_commissions_active
    ON public.campaign_commissions (user_id, campaign_id)
    WHERE valid_to IS NULL;

COMMENT ON TABLE  public.campaign_commissions IS
    'v6 RBAC — comissões versionadas por (user × campaign × vigência). Linha presente = direito; linha ausente = sem comissão.';
COMMENT ON COLUMN public.campaign_commissions.valid_from IS
    'Data de início de vigência (inclusiva).';
COMMENT ON COLUMN public.campaign_commissions.valid_to IS
    'Data fim de vigência (inclusiva). NULL = vigente até hoje.';
COMMENT ON COLUMN public.campaign_commissions.percentage IS
    'Percentual de comissão (0 a 100). Numeric(7,4) permite até 4 casas (ex: 12.5000).';
