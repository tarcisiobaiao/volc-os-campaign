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
