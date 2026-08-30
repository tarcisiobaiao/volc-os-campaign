-- =====================================================================
-- v6 RBAC — Etapa 1 / Arquivo 1 de 6
-- Cria o catálogo de roles funcionais POR CAMPANHA.
--
-- Aditivo, não destrutivo. Não toca em users.role nem em user_campaigns.
-- O role global atual (users.role = ADMIN/OPERATOR) continua existindo
-- e governando o acesso ao painel admin. Esta tabela governa o role
-- *funcional* de um usuário DENTRO de uma campanha específica.
--
-- Idempotente: pode ser executado múltiplas vezes sem efeito colateral.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.campaign_roles (
    id          smallserial PRIMARY KEY,
    code        text        NOT NULL UNIQUE,
    label       text        NOT NULL,
    description text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.campaign_roles IS 'Catálogo de roles funcionais por campanha (v6 RBAC). Independente de users.role.';
COMMENT ON COLUMN public.campaign_roles.code  IS 'Identificador estável usado pelo código (ex: OWNER, OPERATOR).';
COMMENT ON COLUMN public.campaign_roles.label IS 'Rótulo legível para UI.';

-- Seed dos roles iniciais (idempotente).
INSERT INTO public.campaign_roles (code, label, description) VALUES
    ('OWNER',    'Dono',     'Responsável principal pela campanha. Pode gerenciar membros e comissões.'),
    ('OPERATOR', 'Operador', 'Executa otimizações e responde pela performance da campanha.'),
    ('REVIEWER', 'Revisor',  'Acompanha e revisa, sem capacidade de editar.'),
    ('VIEWER',   'Espectador','Acesso somente leitura.')
ON CONFLICT (code) DO NOTHING;

-- Validação visual (read-only). Não modifica nada.
-- SELECT id, code, label FROM public.campaign_roles ORDER BY id;
