-- =====================================================================
-- v6 RBAC — Etapa 1 / Arquivo 2 de 6
-- Vínculo M:N entre usuário e campanha COM role funcional explícito.
-- Esta tabela representa APENAS ACESSO. Não diz nada sobre comissão.
--
-- Aditivo. Roda em paralelo a public.user_campaigns (legado).
-- Nada em user_campaigns é tocado.
--
-- Tipos confirmados via diagnóstico:
--   public.users.id            uuid  (FK → auth.users.id)
--   public.campaigns.campaign_id varchar  (ID do Google Ads, NÃO o int PK)
--   public.user_campaigns.campaign_id varchar  (FK → campaigns.campaign_id)
-- Usamos o mesmo padrão: campaign_id = varchar.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.campaign_members (
    id          bigserial   PRIMARY KEY,
    user_id     uuid        NOT NULL REFERENCES public.users(id)         ON DELETE CASCADE,
    campaign_id varchar     NOT NULL REFERENCES public.campaigns(campaign_id) ON DELETE CASCADE,
    role_id     smallint    NOT NULL REFERENCES public.campaign_roles(id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    created_by  uuid        REFERENCES public.users(id) ON DELETE SET NULL,
    -- Permite múltiplos roles do mesmo usuário na mesma campanha
    -- (ex: alguém ser OWNER e REVIEWER simultaneamente).
    CONSTRAINT campaign_members_unique UNIQUE (user_id, campaign_id, role_id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_members_user
    ON public.campaign_members (user_id);

CREATE INDEX IF NOT EXISTS idx_campaign_members_campaign
    ON public.campaign_members (campaign_id);

CREATE INDEX IF NOT EXISTS idx_campaign_members_role
    ON public.campaign_members (role_id);

COMMENT ON TABLE  public.campaign_members IS
    'v6 RBAC — vínculo (usuário × campanha × role funcional). Apenas ACESSO. Comissão é separada (campaign_commissions).';
COMMENT ON COLUMN public.campaign_members.campaign_id IS
    'ID do Google Ads (varchar), consistente com user_campaigns.campaign_id.';
COMMENT ON COLUMN public.campaign_members.role_id IS
    'Role funcional desta participação. FK → campaign_roles.';
