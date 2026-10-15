-- =============================================================================
-- v21_pacote_aplicar — meta_capi_sites + RBAC v6 com privilégios (PROPOSTA, NÃO APLICADA)
-- GERADO por scripts/montar-pacote-v21.sh. NÃO EDITAR: edite as partes e rode
-- o gerador; `scripts/montar-pacote-v21.sh --check` acusa pacote defasado.
--
-- Uma transação só. Aplicar com:
--   psql -X -v ON_ERROR_STOP=1 -f supabase/migrations/v21_pacote_aplicar.sql
-- Qualquer erro desfaz o pacote inteiro; nenhuma outra sessão vê estado
-- intermediário. NÃO aplicar as partes uma a uma (ver v21_01/v21_02).
--
-- Partes (sha256 no momento da montagem):
--   ba0137fe35a3d3c66162a727a8f9312ee96d3171007841abb90d115d852478a9  src/sql/v7_13_meta_capi_sites.sql
--   b679c32292385f4d1903e038e4a3dea8db88242ae4cd820f614f120708745c84  supabase/migrations/v21_01_meta_capi_sites_privilegios.sql
--   d78d690db04e9a9dff3c552d2ee7af8ca492659bb38e2cf2870d471bc332bb57  src/sql/v6_01_create_campaign_roles.sql
--   bb73987842a0f2e176beb5b27242f66f85b76e7a32356e4b2ed2dabcc59eea68  src/sql/v6_02_create_campaign_members.sql
--   061d9e465002ecb0f6df26a98e0875b735d617418b79b376174820adc37d0e3d  src/sql/v6_03_create_campaign_commissions.sql
--   a563b788ccb10654ce86e30656690c8fe9dcab19850736e4343aa14c199aecd9  src/sql/v6_04_create_daily_campaign_member_payouts.sql
--   6815368d6606d93f663b0d9c076e2ec61c789900f0e9c66d0a6b6c234e331c61  src/sql/v6_05_helper_functions.sql
--   627413885c696e11406d50ee48243cd6af41bbcfebf432509b3b32895659d2df  supabase/migrations/v21_02_v6_rbac_privilegios.sql
-- =============================================================================
\set ON_ERROR_STOP on
BEGIN;

-- Pré-checagem: o pacote CRIA as cinco tabelas. Se alguma já existe, alguém
-- aplicou parte dele fora do pacote: a janela já aconteceu e o caminho certo é
-- auditar e rodar só v21_01/v21_02 sobre o que existe, não reaplicar por cima.
DO $pre$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['meta_capi_sites', 'campaign_roles', 'campaign_members',
                           'campaign_commissions', 'daily_campaign_member_payouts'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      RAISE EXCEPTION 'v21_pacote: public.% já existe — este pacote não reaplica por cima', t;
    END IF;
  END LOOP;
  IF to_regprocedure('public.volc_current_admin()') IS NULL THEN
    RAISE EXCEPTION 'v21_pacote: public.volc_current_admin() ausente (v8_01)';
  END IF;
  IF to_regclass('public.users') IS NULL OR to_regclass('public.campaigns') IS NULL THEN
    RAISE EXCEPTION 'v21_pacote: public.users e public.campaigns são pré-requisito das v6';
  END IF;
END
$pre$;

-- >>>>> início da parte: src/sql/v7_13_meta_capi_sites.sql
-- =====================================================================
-- v7 META CAPI — Etapa 13 / Tabela multi-tenant de sites (ADITIVO, idempotente)
--
-- Substitui o modelo antigo "1 Edge Function + 2 secrets POR SITE" por
-- "1 Edge Function (capi-router) + 1 linha nesta tabela por site".
-- Cadastrar site novo passa a ser um INSERT, não um deploy.
--
-- Quem lê esta tabela:
--   * a Edge Function `capi-router` (service_role, injetada pelo Supabase);
--   * o endpoint autenticado /api/meta-capi/sites (service_role no backend).
-- Ninguém mais.
--
-- POR QUE RLS LIGADA E ZERO POLICIES:
--   RLS ligada sem nenhuma policy = ninguém com a chave `anon` ou
--   `authenticated` consegue ler/escrever nada via PostgREST (o default do
--   Postgres com RLS ativa é NEGAR). O `service_role` faz BYPASS de RLS,
--   então a Edge Function e o backend continuam enxergando tudo.
--   É o oposto das tabelas pautador_*, que têm policy admin-by-email: aqui
--   NÃO queremos nem o admin logado lendo a linha crua pelo client, porque
--   a linha carrega o token da Meta.
--
-- POR QUE CIFRAR O TOKEN MESMO COM RLS LIGADA:
--   O sistema expõe /api/supabase/query (Vercel + Express) que aceita
--   QUALQUER tabela com a service_role e SEM autenticação. Ou seja: hoje
--   existe um caminho público que faz bypass de RLS. Enquanto esse proxy
--   genérico não for corrigido, RLS sozinha não protege nada — o token só
--   está seguro porque o que está gravado é ciphertext AES-GCM, e a chave
--   (CAPI_MASTER_KEY) vive fora do banco, em env var.
--   Defesa em profundidade: RLS + cifra + endpoint próprio autenticado.
--
-- NÃO destrutivo. >>> Rodar no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Função de trigger de updated_at
--    Reuso: `public.set_pautador_updated_at()` (v7_01) é genérica — só faz
--    `NEW.updated_at = NOW()`, não referencia nada de pautador. Reusamos em
--    vez de criar uma cópia. O guard abaixo cria a função SÓ se ela não
--    existir, para que esta migração também rode sozinha num banco novo,
--    sem sobrescrever (CREATE OR REPLACE) uma versão que outra etapa
--    tenha evoluído.
-- ---------------------------------------------------------------------
DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.proname = 'set_pautador_updated_at'
    ) THEN
        EXECUTE $fn$
            CREATE FUNCTION public.set_pautador_updated_at()
            RETURNS TRIGGER AS $body$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $body$ LANGUAGE plpgsql;
        $fn$;
    END IF;
END
$do$;

-- ---------------------------------------------------------------------
-- 1. meta_capi_sites — 1 linha por site rastreado
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.meta_capi_sites (
    id                bigserial   PRIMARY KEY,
    site_key          text        NOT NULL,   -- casa com `site_key` do payload da tag
    site_name         text        NOT NULL,
    domain            text        NOT NULL,   -- fallback por host quando o payload não traz site_key
    cookie_domain     text        NOT NULL,   -- APEX com ponto inicial (".technewsbrasil.com.br")
    endpoint_url      text        NOT NULL,   -- "https://ev.dominio.com.br/capi" (rota do Worker)
    pixel_id          text        NOT NULL,
    capi_token_cipher text        NOT NULL,   -- base64 — AES-GCM 256 (NUNCA texto puro)
    capi_token_iv     text        NOT NULL,   -- base64 — 12 bytes, único por gravação
    events            jsonb       NOT NULL DEFAULT '{"interstitial": true, "rewarded": true}'::jsonb,
    is_active         boolean     NOT NULL DEFAULT true,
    test_event_code   text,                   -- só usado no teste do wizard
    last_check_at     timestamptz,
    last_check_result jsonb,
    created_by        uuid        REFERENCES public.users(id) ON DELETE SET NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

-- Colunas adicionadas em re-execuções (idempotência para bancos que já
-- tenham uma versão anterior da tabela).
ALTER TABLE public.meta_capi_sites
    ADD COLUMN IF NOT EXISTS test_event_code   text,
    ADD COLUMN IF NOT EXISTS last_check_at     timestamptz,
    ADD COLUMN IF NOT EXISTS last_check_result jsonb,
    ADD COLUMN IF NOT EXISTS created_by        uuid;

-- ---------------------------------------------------------------------
-- 2. Índices
--    site_key e domain são os DOIS caminhos de resolução do capi-router:
--    primeiro `body.site_key`, e se faltar, o host de `event_source_url`
--    casado com `domain`. Ambos precisam ser únicos (não pode haver dois
--    sites disputando a mesma chave/host) E indexados para a busca.
--    Um UNIQUE INDEX entrega as duas coisas — criar um índice comum além
--    dele seria índice duplicado, puro custo de escrita.
-- ---------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_meta_capi_sites_site_key
    ON public.meta_capi_sites (site_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_meta_capi_sites_domain
    ON public.meta_capi_sites (domain);
CREATE INDEX IF NOT EXISTS idx_meta_capi_sites_active
    ON public.meta_capi_sites (is_active);

-- ---------------------------------------------------------------------
-- 3. Trigger de updated_at
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_meta_capi_sites_updated_at ON public.meta_capi_sites;
CREATE TRIGGER trg_meta_capi_sites_updated_at
    BEFORE UPDATE ON public.meta_capi_sites
    FOR EACH ROW EXECUTE FUNCTION public.set_pautador_updated_at();

-- ---------------------------------------------------------------------
-- 4. RLS ligada, ZERO policies (ver cabeçalho)
--    Não criar policy aqui é INTENCIONAL — não é esquecimento.
--    FORCE ROW LEVEL SECURITY não é usado de propósito: ele também
--    aplicaria RLS ao dono da tabela, e não queremos quebrar manutenção
--    manual feita no SQL Editor pelo owner.
-- ---------------------------------------------------------------------
ALTER TABLE public.meta_capi_sites ENABLE ROW LEVEL SECURITY;

-- Limpeza defensiva: se alguma execução anterior tiver criado policy,
-- derruba. O estado desejado é "RLS ligada e nenhuma policy".
DO $do$
DECLARE
    pol record;
BEGIN
    FOR pol IN
        SELECT policyname
          FROM pg_policies
         WHERE schemaname = 'public'
           AND tablename  = 'meta_capi_sites'
    LOOP
        EXECUTE format('DROP POLICY %I ON public.meta_capi_sites', pol.policyname);
    END LOOP;
END
$do$;

-- ---------------------------------------------------------------------
-- 5. Documentação (aparece no Studio e no `\d+`)
-- ---------------------------------------------------------------------
COMMENT ON TABLE public.meta_capi_sites IS
    'Meta CAPI multi-tenant — 1 linha por site rastreado. Lida SOMENTE por service_role (Edge Function capi-router e endpoint /api/meta-capi/sites). RLS ligada e sem policies de propósito: anon/authenticated não enxergam nada via PostgREST.';

COMMENT ON COLUMN public.meta_capi_sites.site_key IS
    'Chave multi-tenant enviada pela tag do GTM no campo `site_key`. Derivada do domain (minúsculo, [a-z0-9-]), editável pelo operador. É o caminho primário de resolução do site no capi-router.';

COMMENT ON COLUMN public.meta_capi_sites.site_name IS
    'Nome de exibição do site no wizard. Não participa de nenhuma lógica.';

COMMENT ON COLUMN public.meta_capi_sites.domain IS
    'Host do site ("apps.technewsbrasil.com.br"). Caminho SECUNDÁRIO de resolução: quando o payload não traz site_key, o router casa o host de event_source_url (e o apex) com esta coluna.';

COMMENT ON COLUMN public.meta_capi_sites.cookie_domain IS
    'APEX com ponto inicial (".technewsbrasil.com.br"). Precisa ser o apex e não o host, senão o cookie _fbc/_volc_eid não é compartilhado entre subdomínios e a deduplicação com o Pixel quebra.';

COMMENT ON COLUMN public.meta_capi_sites.endpoint_url IS
    'URL pública que a tag chama ("https://ev.dominio.com.br/capi"). É a rota do Worker Cloudflare, não a da Edge Function.';

COMMENT ON COLUMN public.meta_capi_sites.pixel_id IS
    'ID do Pixel da Meta. Público por natureza (aparece na tag do navegador) — por isso NÃO é cifrado.';

COMMENT ON COLUMN public.meta_capi_sites.capi_token_cipher IS
    'Access token da Conversions API CIFRADO (AES-GCM 256, saída base64, já inclui o auth tag). NUNCA gravar o token em texto puro: os endpoints /api/supabase/* deste sistema aceitam qualquer tabela com service_role e SEM autenticação, ou seja, existe hoje um caminho público que faz bypass de RLS. A cifra é o que mantém o token seguro mesmo se a linha vazar. A chave (CAPI_MASTER_KEY) vive só em env var — backend e secrets da Edge Function — nunca no banco.';

COMMENT ON COLUMN public.meta_capi_sites.capi_token_iv IS
    'IV (nonce) de 12 bytes em base64, sorteado a CADA gravação. Reusar IV com a mesma chave quebra a segurança do AES-GCM, por isso ele é por linha e regravado junto com o cipher.';

COMMENT ON COLUMN public.meta_capi_sites.events IS
    'Quais eventos este site dispara: {"interstitial": bool, "rewarded": bool}. Controla quais tags o wizard gera.';

COMMENT ON COLUMN public.meta_capi_sites.is_active IS
    'Desligar aqui faz o capi-router responder 403 site_inactive sem apagar a configuração.';

COMMENT ON COLUMN public.meta_capi_sites.test_event_code IS
    'test_event_code do Gerenciador de Eventos, usado só no teste ao vivo do wizard. Não deve ir para o tráfego real.';

COMMENT ON COLUMN public.meta_capi_sites.last_check_at IS
    'Quando o wizard rodou o último teste de ponta a ponta (endpoint -> function -> Meta).';

COMMENT ON COLUMN public.meta_capi_sites.last_check_result IS
    'Resultado bruto do último teste, por camada (endpoint/function/meta), para o operador saber ONDE quebrou. Nunca deve conter token.';

COMMENT ON COLUMN public.meta_capi_sites.created_by IS
    'Admin que cadastrou o site (public.users.id = id do auth.users).';

-- =====================================================================
-- Verificação (opcional):
--   SELECT id, site_key, domain, is_active FROM public.meta_capi_sites;
--   SELECT relrowsecurity FROM pg_class WHERE relname = 'meta_capi_sites'; -- deve ser true
--   SELECT count(*) FROM pg_policies WHERE tablename = 'meta_capi_sites';  -- deve ser 0
-- =====================================================================

-- <<<<< fim da parte: src/sql/v7_13_meta_capi_sites.sql

-- >>>>> início da parte: supabase/migrations/v21_01_meta_capi_sites_privilegios.sql
-- =============================================================================
-- v21_01 — privilégios de public.meta_capi_sites (PROPOSTA, NÃO APLICADA)
-- =============================================================================
-- Contexto (15/10/2026): /api/meta-capi/sites responde 500 porque a tabela não
-- existe em produção — `src/sql/v7_13_meta_capi_sites.sql` nunca foi aplicada.
--
-- NÃO APLICAR SOZINHO. Este arquivo é PARTE de
-- `supabase/migrations/v21_pacote_aplicar.sql` (montado por
-- `scripts/montar-pacote-v21.sh`), que roda v7_13 + v21_01 + v6_01..v6_05 +
-- v21_02 numa transação só. Aplicado à parte, a v7_13 confirmaria antes deste
-- arquivo, e nesse intervalo a anon teria SELECT, DELETE e TRUNCATE na tabela.
-- Uso isolado só como remédio, se a tabela já existir sem estes privilégios.
--
-- POR QUE ESTE ARQUIVO EXISTE: em produção o default ACL de `public` concede
-- `arwdDxt` a anon e authenticated em toda tabela nova (medido em 24/08 e
-- reconfirmado em 15/10). A v7_13 liga RLS sem policy, o que esconde as linhas
-- via PostgREST, mas deixa GRANT de TRUNCATE/REFERENCES/TRIGGER aberto, e
-- TRUNCATE não passa por RLS. A tabela guarda o token da Meta cifrado: só o
-- service_role (backend e Edge Function capi-router) precisa dela.
-- =============================================================================

DO $guarda$
BEGIN
  IF to_regclass('public.meta_capi_sites') IS NULL THEN
    RAISE EXCEPTION 'v21_01: aplique src/sql/v7_13_meta_capi_sites.sql antes';
  END IF;
END
$guarda$;

REVOKE ALL ON TABLE public.meta_capi_sites FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.meta_capi_sites_id_seq FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.meta_capi_sites TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.meta_capi_sites_id_seq TO service_role;

NOTIFY pgrst, 'reload schema';

-- <<<<< fim da parte: supabase/migrations/v21_01_meta_capi_sites_privilegios.sql

-- >>>>> início da parte: src/sql/v6_01_create_campaign_roles.sql
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

-- <<<<< fim da parte: src/sql/v6_01_create_campaign_roles.sql

-- >>>>> início da parte: src/sql/v6_02_create_campaign_members.sql
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

-- <<<<< fim da parte: src/sql/v6_02_create_campaign_members.sql

-- >>>>> início da parte: src/sql/v6_03_create_campaign_commissions.sql
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

-- <<<<< fim da parte: src/sql/v6_03_create_campaign_commissions.sql

-- >>>>> início da parte: src/sql/v6_04_create_daily_campaign_member_payouts.sql
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

-- <<<<< fim da parte: src/sql/v6_04_create_daily_campaign_member_payouts.sql

-- >>>>> início da parte: src/sql/v6_05_helper_functions.sql
-- =====================================================================
-- v6 RBAC — Etapa 1 / Arquivo 5 de 6
-- Funções auxiliares do novo modelo. NOMES NOVOS, prefixados v6_*.
-- Não substituem nenhuma função existente. Não criam triggers.
--
-- Pré-requisito: a função public.get_tax_rate_for_date(date) já existe
-- em produção (usada pelo cálculo legado calculate_operator_commission).
--
-- Idempotente via CREATE OR REPLACE.
-- =====================================================================

-- ----------------------------------------------------------------------
-- v6_get_active_commission_rate
-- Retorna a taxa vigente em uma data específica para um par (user, campaign).
-- Retorna NULL se não houver vigência ativa nessa data.
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.v6_get_active_commission_rate(
    p_user_id     uuid,
    p_campaign_id varchar,
    p_date        date
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT cc.percentage
      FROM public.campaign_commissions cc
     WHERE cc.user_id     = p_user_id
       AND cc.campaign_id = p_campaign_id
       AND cc.valid_from <= p_date
       AND (cc.valid_to IS NULL OR cc.valid_to >= p_date)
     ORDER BY cc.valid_from DESC
     LIMIT 1;
$$;

COMMENT ON FUNCTION public.v6_get_active_commission_rate(uuid, varchar, date) IS
    'v6 RBAC — taxa de comissão vigente em uma data específica. Read-only.';

-- ----------------------------------------------------------------------
-- v6_calculate_member_commission
-- Equivalente do calculate_operator_commission legado, mas como função
-- pura (sem dependência implícita de user_campaigns).
-- Retorna a comissão calculada para os parâmetros dados.
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.v6_calculate_member_commission(
    p_revenue_revshare    numeric,
    p_spend               numeric,
    p_commission_pct      numeric,
    p_date                date
)
RETURNS numeric
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_tax_rate   numeric;
    v_tax_amount numeric;
    v_net_profit numeric;
BEGIN
    -- Sem comissão configurada → 0.
    IF p_commission_pct IS NULL OR p_commission_pct <= 0 THEN
        RETURN 0;
    END IF;

    -- Reusa a função existente de imposto vigente.
    v_tax_rate   := public.get_tax_rate_for_date(p_date);
    v_tax_amount := COALESCE(p_revenue_revshare, 0) * v_tax_rate;
    v_net_profit := COALESCE(p_revenue_revshare, 0)
                    - COALESCE(p_spend, 0)
                    - v_tax_amount;

    IF v_net_profit <= 0 THEN
        RETURN 0;
    END IF;

    RETURN v_net_profit * (p_commission_pct / 100.0);
END;
$$;

COMMENT ON FUNCTION public.v6_calculate_member_commission(numeric, numeric, numeric, date) IS
    'v6 RBAC — fórmula pura de comissão. Mesma matemática do calculate_operator_commission legado, sem acoplamento com user_campaigns.';

-- ----------------------------------------------------------------------
-- v6_populate_member_payouts_for_date
-- Calcula e UPSERT em daily_campaign_member_payouts para uma data específica.
-- Para cada (campaign_id, date) em daily_campaign_metrics, busca todos os
-- (user_id) com vigência ativa em campaign_commissions e produz uma
-- linha em payouts.
--
-- Retorna o número de linhas afetadas (inserted + updated).
-- Operação 100% manual. NÃO é trigger. Roda apenas quando chamada.
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.v6_populate_member_payouts_for_date(p_date date)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_count integer;
BEGIN
    WITH src AS (
        SELECT
            dcm."date"                       AS d,
            dcm.campaign_id,
            cc.user_id,
            cc.percentage                    AS pct,
            COALESCE(dcm.revenue_converted_revshare, 0) AS rev,
            COALESCE(dcm.spend, 0)                       AS spd
        FROM public.daily_campaign_metrics dcm
        JOIN public.campaign_commissions cc
          ON cc.campaign_id = dcm.campaign_id
         AND cc.valid_from <= dcm."date"
         AND (cc.valid_to IS NULL OR cc.valid_to >= dcm."date")
        WHERE dcm."date" = p_date
    ),
    calc AS (
        SELECT
            s.*,
            public.get_tax_rate_for_date(s.d) AS tax_rate
        FROM src s
    ),
    final AS (
        SELECT
            c.d,
            c.campaign_id,
            c.user_id,
            c.pct,
            c.rev,
            c.spd,
            c.tax_rate,
            (c.rev * c.tax_rate)                                AS tax_amount,
            (c.rev - c.spd - (c.rev * c.tax_rate))              AS net_profit,
            public.v6_calculate_member_commission(c.rev, c.spd, c.pct, c.d) AS amount
        FROM calc c
    )
    INSERT INTO public.daily_campaign_member_payouts AS p (
        "date", campaign_id, user_id,
        commission_percentage, revenue_revshare, spend,
        tax_rate, tax_amount, net_profit, amount,
        calculated_at, source
    )
    SELECT
        f.d, f.campaign_id, f.user_id,
        f.pct, f.rev, f.spd,
        f.tax_rate, f.tax_amount, f.net_profit, f.amount,
        now(), 'v6_populate_member_payouts_for_date'
    FROM final f
    ON CONFLICT ("date", campaign_id, user_id)
    DO UPDATE SET
        commission_percentage = EXCLUDED.commission_percentage,
        revenue_revshare      = EXCLUDED.revenue_revshare,
        spend                 = EXCLUDED.spend,
        tax_rate              = EXCLUDED.tax_rate,
        tax_amount            = EXCLUDED.tax_amount,
        net_profit            = EXCLUDED.net_profit,
        amount                = EXCLUDED.amount,
        calculated_at         = now(),
        source                = EXCLUDED.source;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION public.v6_populate_member_payouts_for_date(date) IS
    'v6 RBAC — popula daily_campaign_member_payouts para uma data específica. Manual, sem trigger. Idempotente via UPSERT.';

-- ----------------------------------------------------------------------
-- v6_populate_member_payouts_for_range
-- Conveniência: roda v6_populate_member_payouts_for_date para cada dia
-- num intervalo. Retorna o total de linhas afetadas.
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.v6_populate_member_payouts_for_range(
    p_from date,
    p_to   date
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_d     date;
    v_total integer := 0;
BEGIN
    IF p_to < p_from THEN
        RAISE EXCEPTION 'p_to (%) deve ser >= p_from (%)', p_to, p_from;
    END IF;

    v_d := p_from;
    WHILE v_d <= p_to LOOP
        v_total := v_total + public.v6_populate_member_payouts_for_date(v_d);
        v_d := v_d + 1;
    END LOOP;

    RETURN v_total;
END;
$$;

COMMENT ON FUNCTION public.v6_populate_member_payouts_for_range(date, date) IS
    'v6 RBAC — wrapper que aplica v6_populate_member_payouts_for_date dia a dia num intervalo.';

-- <<<<< fim da parte: src/sql/v6_05_helper_functions.sql

-- >>>>> início da parte: supabase/migrations/v21_02_v6_rbac_privilegios.sql
-- =============================================================================
-- v21_02 — RLS e privilégios das tabelas v6 de RBAC (PROPOSTA, NÃO APLICADA)
-- =============================================================================
-- Contexto (15/10/2026): /settings/users é o ponto oficial de corte para o
-- modelo v6 (`src/pages/settings/UsersSettings.tsx`), mas campaign_roles,
-- campaign_members, campaign_commissions e daily_campaign_member_payouts não
-- existem em produção — as v6_01..v6_05 de `src/sql/` nunca foram aplicadas no
-- self-hosted. A página responde 404 nas três primeiras.
--
-- NÃO APLICAR SOZINHO. Este arquivo é PARTE de
-- `supabase/migrations/v21_pacote_aplicar.sql` (montado por
-- `scripts/montar-pacote-v21.sh`): v7_13 + v21_01 + v6_01..v6_05 + ESTE numa
-- transação só. Aplicadas uma por vez, as v6_0x confirmariam antes deste
-- arquivo, e nesse intervalo a anon leria, apagaria e truncaria as quatro
-- tabelas (sem RLS). Uso isolado só como remédio, sobre tabelas já existentes.
-- Os backfills v6_08/v6_09 ficam fora do pacote e são
-- opcionais: em 15/10 `user_campaigns` tem 0 linhas e nenhum usuário tem
-- `commission_percentage > 0`, então não inserem nada.
--
-- POR QUE ESTE ARQUIVO EXISTE: as v6_0x criam as tabelas SEM RLS, e o default
-- ACL de produção dá `arwdDxt` a anon e authenticated em toda tabela nova. Sem
-- isto, a chave anon (pública, no bundle) leria e reescreveria comissões.
--
-- Regra: admin (public.volc_current_admin(), papel em app_auth.user_roles)
-- lê e escreve; o próprio usuário lê os seus vínculos, comissões e payouts;
-- anon não vê nada. payouts só são escritos por função, nunca pelo cliente.
-- =============================================================================

DO $guarda$
BEGIN
  IF to_regclass('public.campaign_roles') IS NULL
     OR to_regclass('public.campaign_members') IS NULL
     OR to_regclass('public.campaign_commissions') IS NULL
     OR to_regclass('public.daily_campaign_member_payouts') IS NULL
     OR to_regprocedure('public.v6_populate_member_payouts_for_date(date)') IS NULL THEN
    RAISE EXCEPTION 'v21_02: aplique src/sql/v6_01..v6_05 antes';
  END IF;
  IF to_regprocedure('public.volc_current_admin()') IS NULL THEN
    RAISE EXCEPTION 'v21_02: public.volc_current_admin() ausente (v8_01)';
  END IF;
END
$guarda$;

-- 1. Fecha tudo, depois abre só o necessário ---------------------------------
REVOKE ALL ON TABLE
  public.campaign_roles, public.campaign_members,
  public.campaign_commissions, public.daily_campaign_member_payouts
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE
  public.campaign_roles_id_seq, public.campaign_members_id_seq,
  public.campaign_commissions_id_seq, public.daily_campaign_member_payouts_id_seq
  FROM PUBLIC, anon, authenticated;

GRANT SELECT ON TABLE public.campaign_roles TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.campaign_members, public.campaign_commissions TO authenticated;
GRANT SELECT ON TABLE public.daily_campaign_member_payouts TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.campaign_members_id_seq, public.campaign_commissions_id_seq TO authenticated;

GRANT ALL ON TABLE
  public.campaign_roles, public.campaign_members,
  public.campaign_commissions, public.daily_campaign_member_payouts
  TO service_role;
GRANT USAGE, SELECT ON SEQUENCE
  public.campaign_roles_id_seq, public.campaign_members_id_seq,
  public.campaign_commissions_id_seq, public.daily_campaign_member_payouts_id_seq
  TO service_role;

-- 2. RLS ---------------------------------------------------------------------
ALTER TABLE public.campaign_roles                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_members              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_commissions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_campaign_member_payouts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS campaign_roles_leitura ON public.campaign_roles;
CREATE POLICY campaign_roles_leitura ON public.campaign_roles
  FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS campaign_members_leitura ON public.campaign_members;
CREATE POLICY campaign_members_leitura ON public.campaign_members
  FOR SELECT TO authenticated
  USING (public.volc_current_admin() OR user_id = (SELECT auth.uid()));
DROP POLICY IF EXISTS campaign_members_escrita_admin ON public.campaign_members;
CREATE POLICY campaign_members_escrita_admin ON public.campaign_members
  FOR ALL TO authenticated
  USING (public.volc_current_admin()) WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS campaign_commissions_leitura ON public.campaign_commissions;
CREATE POLICY campaign_commissions_leitura ON public.campaign_commissions
  FOR SELECT TO authenticated
  USING (public.volc_current_admin() OR user_id = (SELECT auth.uid()));
DROP POLICY IF EXISTS campaign_commissions_escrita_admin ON public.campaign_commissions;
CREATE POLICY campaign_commissions_escrita_admin ON public.campaign_commissions
  FOR ALL TO authenticated
  USING (public.volc_current_admin()) WITH CHECK (public.volc_current_admin());

DROP POLICY IF EXISTS dcmp_leitura ON public.daily_campaign_member_payouts;
CREATE POLICY dcmp_leitura ON public.daily_campaign_member_payouts
  FOR SELECT TO authenticated
  USING (public.volc_current_admin() OR user_id = (SELECT auth.uid()));

-- 3. Funções v6: as de escrita ficam com service_role -------------------------
REVOKE ALL ON FUNCTION
  public.v6_get_active_commission_rate(uuid, varchar, date),
  public.v6_calculate_member_commission(numeric, numeric, numeric, date),
  public.v6_populate_member_payouts_for_date(date),
  public.v6_populate_member_payouts_for_range(date, date)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  public.v6_get_active_commission_rate(uuid, varchar, date),
  public.v6_calculate_member_commission(numeric, numeric, numeric, date)
  TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION
  public.v6_populate_member_payouts_for_date(date),
  public.v6_populate_member_payouts_for_range(date, date)
  TO service_role;

NOTIFY pgrst, 'reload schema';

-- <<<<< fim da parte: supabase/migrations/v21_02_v6_rbac_privilegios.sql

-- Pós-checagem, ainda dentro da transação: se o estado final não for o
-- prometido, nada é confirmado.
DO $pos$
DECLARE
  t text;
  r record;
BEGIN
  FOREACH t IN ARRAY ARRAY['meta_capi_sites', 'campaign_roles', 'campaign_members',
                           'campaign_commissions', 'daily_campaign_member_payouts'] LOOP
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = ('public.' || t)::regclass) THEN
      RAISE EXCEPTION 'v21_pacote: RLS desligada em public.%', t;
    END IF;
    IF has_table_privilege('anon', 'public.' || t, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') THEN
      RAISE EXCEPTION 'v21_pacote: anon ainda tem privilégio em public.%', t;
    END IF;
    IF has_table_privilege('authenticated', 'public.' || t, 'TRUNCATE,REFERENCES,TRIGGER') THEN
      RAISE EXCEPTION 'v21_pacote: authenticated tem TRUNCATE/REFERENCES/TRIGGER em public.%', t;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class c, aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a
                WHERE c.oid = ('public.' || t)::regclass AND a.grantee = 0) THEN
      RAISE EXCEPTION 'v21_pacote: PUBLIC tem privilégio em public.%', t;
    END IF;
  END LOOP;
  IF has_table_privilege('authenticated', 'public.meta_capi_sites', 'SELECT,INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION 'v21_pacote: authenticated alcança meta_capi_sites';
  END IF;
  IF has_table_privilege('authenticated', 'public.daily_campaign_member_payouts', 'INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated', 'public.campaign_roles', 'INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION 'v21_pacote: authenticated escreve em payouts ou no catálogo de papéis';
  END IF;
  FOR r IN SELECT p.oid::regprocedure AS f FROM pg_proc p
            WHERE p.pronamespace = 'public'::regnamespace AND p.proname LIKE 'v6\_populate\_%' LOOP
    IF has_function_privilege('anon', r.f, 'EXECUTE') OR has_function_privilege('authenticated', r.f, 'EXECUTE') THEN
      RAISE EXCEPTION 'v21_pacote: % executável por anon/authenticated', r.f;
    END IF;
  END LOOP;
END
$pos$;

COMMIT;
