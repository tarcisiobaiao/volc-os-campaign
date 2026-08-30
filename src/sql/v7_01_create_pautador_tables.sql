-- =====================================================================
-- v7 PAUTADOR PRO — Etapa 1 / Arquivo 1 de 1
-- Cria as 6 tabelas do Pautador Pro (descoberta / mineracao / funis de
-- arbitragem de atencao por pais) com RLS admin + human-in-the-loop,
-- indices e triggers de updated_at.
--
-- Aditivo, nao destrutivo. Idempotente (CREATE TABLE IF NOT EXISTS,
-- CREATE INDEX IF NOT EXISTS, DROP POLICY/TRIGGER IF EXISTS, ON CONFLICT).
-- >>> Rodar manualmente no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
--
-- Convencoes seguidas (ver src/sql/v6_*, create_campaign_highlights_table.sql,
-- create_project_cost_sharing_table.sql, setup_users_rls_policies.sql):
--   - PK: bigserial (estilo incubator_sites / campaign_highlights)
--   - timestamps: timestamptz NOT NULL DEFAULT now() (UTC, estilo v6)
--   - "enums" = text + CHECK (... IN (...))   (o repo NAO usa ENUM nativo)
--   - trigger updated_at por tabela: NEW.updated_at = NOW()
--   - RLS: lower(users.email) = lower(auth.jwt() ->> 'email') AND users.role = 'ADMIN'
--     (a tabela public.users e indexada por EMAIL — ver AuthContext.fetchUserProfile;
--      NAO existe coluna google_oauth_id neste banco, ao contrario do que
--      setup_users_rls_policies.sql sugere — aquele arquivo nunca foi aplicado.)
--   - service_role (n8n / backend FastAPI) faz BYPASS de RLS; nunca exposto ao frontend
--
-- IMPORTANTE — CONTRATO CANONICO:
--   As estimativas economicas sao QUALITATIVAS (low|medium|high|very_high),
--   exatamente como o agente GOD MODE as produz. A nota numerica de
--   arbitragem (arbitrage_score) e o sinal de ROI sao DERIVADOS dessas
--   estimativas + do CPC parseado, no backend (scoring.py).
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Trigger generico de updated_at (compartilhado pelas tabelas v7)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_pautador_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 1. pautador_countries — catalogo de paises-alvo (idioma nativo, RPM)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pautador_countries (
    id              bigserial   PRIMARY KEY,
    country_code    text        NOT NULL UNIQUE,           -- ISO-3166-1 alpha-2 (ex: GB, PT, GT)
    country_name    text        NOT NULL,                  -- nome em PT-BR (ex: 'Reino Unido')
    native_language text        NOT NULL,                  -- locale de busca (ex: en-GB, pt-PT)
    market_tier     text        NOT NULL DEFAULT 'medium_value'
        CHECK (market_tier IN ('high_value','medium_value','volume_play')),
    rpm_index       numeric(10,4),                         -- potencial de RPM relativo (proxy)
    is_active       boolean     NOT NULL DEFAULT true,
    flag_emoji      text,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pautador_countries_active
    ON public.pautador_countries (is_active);

DROP TRIGGER IF EXISTS trg_pautador_countries_updated_at ON public.pautador_countries;
CREATE TRIGGER trg_pautador_countries_updated_at
    BEFORE UPDATE ON public.pautador_countries
    FOR EACH ROW EXECUTE FUNCTION public.set_pautador_updated_at();

COMMENT ON TABLE public.pautador_countries IS
    'Pautador Pro — catalogo de paises-alvo com idioma nativo, market_tier e indice de RPM.';

-- ---------------------------------------------------------------------
-- 2. pautador_runs — uma execucao do Descobridor (lote de 40 oportunidades)
--    Distribuicao alvo por run: 8 S / 14 A / 12 B / 6 EXPERIMENTAL = 40.
--    Guarda tambem a inteligencia cultural / personas / insights do agente.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pautador_runs (
    id              bigserial   PRIMARY KEY,
    run_uuid        uuid        NOT NULL DEFAULT gen_random_uuid() UNIQUE, -- id estavel p/ backend/n8n
    country_id      bigint      REFERENCES public.pautador_countries(id) ON DELETE SET NULL,
    country         text        NOT NULL,                  -- nome do pais (PT-BR), denormalizado
    country_code    text,
    native_language text,
    market_tier     text
        CHECK (market_tier IS NULL OR market_tier IN ('high_value','medium_value','volume_play')),
    phase           text        NOT NULL DEFAULT 'discovery'
        CHECK (phase IN ('discovery','mining','funnel')),
    status          text        NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','running','completed','failed','reviewed','archived')),
    requested_count integer     NOT NULL DEFAULT 40,
    produced_count  integer     NOT NULL DEFAULT 0,
    -- snapshot da distribuicao alvo de tiers (default 8/14/12/6 = 40)
    target_tier_s   integer     NOT NULL DEFAULT 8,
    target_tier_a   integer     NOT NULL DEFAULT 14,
    target_tier_b   integer     NOT NULL DEFAULT 12,
    target_tier_exp integer     NOT NULL DEFAULT 6,
    -- inteligencia produzida pelo agente (jsonb, estilo sync_logs.metadata)
    cultural_intelligence jsonb,                           -- key_institutions, main_benefits_programs, ...
    personas        jsonb,                                 -- array de 8 personas
    insights        jsonb,                                 -- market_observation, untapped_angle, ...
    -- execucao
    engine          text,                                  -- 'mock' | 'gemini' | 'openai' | ...
    model           text,                                  -- modelo LLM efetivamente usado
    grounding_calls integer     NOT NULL DEFAULT 0,        -- chamadas Perplexity/grounding feitas
    n8n_execution_id text,
    params          jsonb,
    error_message   text,
    started_at      timestamptz,
    completed_at    timestamptz,
    created_by      uuid        REFERENCES public.users(id) ON DELETE SET NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pautador_runs_counts_nonneg
        CHECK (requested_count >= 0 AND produced_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_pautador_runs_country ON public.pautador_runs (country_id);
CREATE INDEX IF NOT EXISTS idx_pautador_runs_status  ON public.pautador_runs (status);
CREATE INDEX IF NOT EXISTS idx_pautador_runs_created ON public.pautador_runs (created_at DESC);

DROP TRIGGER IF EXISTS trg_pautador_runs_updated_at ON public.pautador_runs;
CREATE TRIGGER trg_pautador_runs_updated_at
    BEFORE UPDATE ON public.pautador_runs
    FOR EACH ROW EXECUTE FUNCTION public.set_pautador_updated_at();

COMMENT ON TABLE public.pautador_runs IS
    'Pautador Pro — execucao do Descobridor. Cada run produz ate 40 oportunidades (8 S / 14 A / 12 B / 6 EXP) + inteligencia cultural.';

-- ---------------------------------------------------------------------
-- 3. pautador_opportunities — o CARD canonico (toda oportunidade)
--    Contrato canonico: TODO campo abaixo deve ser preservado.
--    Estimativas economicas QUALITATIVAS; score/roi DERIVADOS no backend.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pautador_opportunities (
    id                      bigserial   PRIMARY KEY,
    run_id                  bigint      NOT NULL REFERENCES public.pautador_runs(id) ON DELETE CASCADE,
    seed_id                 text,                          -- 'seed_001' (id do agente dentro da run)

    -- localizacao / idioma
    country                 text        NOT NULL,
    native_language         text,

    -- keyword core (no idioma NATIVO do pais)
    keyword                 text        NOT NULL,          -- long-tail
    main_keyword            text        NOT NULL,          -- binomio de intencao (2-3 palavras)
    keyword_pt_translation  text,                          -- traducao PT-BR

    -- classificacao (text + CHECK, estilo do repo)
    tier                    text        NOT NULL
        CHECK (tier IN ('S','A','B','EXPERIMENTAL')),
    category                text        NOT NULL
        CHECK (category IN ('S1','S2','S3','S4','S5','S6',
                            'A1','A2','A3','A4',
                            'B1','B2','B3',
                            'EXP')),

    -- estimativas economicas QUALITATIVAS (como o agente as produz)
    volume_estimate         text
        CHECK (volume_estimate     IS NULL OR volume_estimate     IN ('low','medium','high','very_high')),
    rpm_potential           text
        CHECK (rpm_potential       IS NULL OR rpm_potential       IN ('low','medium','high','very_high')),
    competition_estimate    text
        CHECK (competition_estimate IS NULL OR competition_estimate IN ('low','medium','high')),
    confidence              text
        CHECK (confidence          IS NULL OR confidence          IN ('low','medium','high','very_high')),
    intent                  text
        CHECK (intent              IS NULL OR intent              IN ('informational','navigational','calculator','comparison')),
    timing                  text
        CHECK (timing              IS NULL OR timing              IN ('evergreen','seasonal','event_driven','trending')),

    -- CPC: string crua (no idioma/moeda local) + parse numerico
    cpc_estimate_local      text,                          -- ex: 'GBP 1.20-3.50' / '£1.20-£3.50'
    cpc_min                 numeric(14,4),
    cpc_max                 numeric(14,4),
    cpc_avg                 numeric(14,4),
    currency                text,

    -- derivados (backend scoring.py)
    arbitrage_score         numeric(10,4),                 -- nota final auditavel
    estimated_roi_signal    numeric(14,4),                 -- proxy RPM_score / cpc_avg

    -- semantica
    persona                 text,                          -- nome da persona alvo
    pain_point              text,                          -- PT-BR
    reasoning               text,                          -- PT-BR (razao de ser ouro)
    variations              jsonb       NOT NULL DEFAULT '[]'::jsonb,  -- 3-5 variacoes (idioma nativo)
    expansion_hooks         jsonb       NOT NULL DEFAULT '[]'::jsonb,  -- 3-5 hooks de conteudo

    -- workflow human-in-the-loop (alinhado as colunas do Kanban)
    status                  text        NOT NULL DEFAULT 'discovered'
        CHECK (status IN ('discovered','validating','mining','funnel','ready','rejected','archived')),
    source                  text        NOT NULL DEFAULT 'agent'
        CHECK (source IN ('agent','manual')),
    reviewed_by             uuid        REFERENCES public.users(id) ON DELETE SET NULL,
    reviewed_at             timestamptz,

    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);

-- impede a mesma keyword duplicada dentro de uma mesma run
CREATE UNIQUE INDEX IF NOT EXISTS uq_pautador_opportunities_run_keyword
    ON public.pautador_opportunities (run_id, lower(keyword));

CREATE INDEX IF NOT EXISTS idx_pautador_opps_run       ON public.pautador_opportunities (run_id);
CREATE INDEX IF NOT EXISTS idx_pautador_opps_tier      ON public.pautador_opportunities (tier);
CREATE INDEX IF NOT EXISTS idx_pautador_opps_category  ON public.pautador_opportunities (category);
CREATE INDEX IF NOT EXISTS idx_pautador_opps_status    ON public.pautador_opportunities (status);
CREATE INDEX IF NOT EXISTS idx_pautador_opps_country   ON public.pautador_opportunities (country);
CREATE INDEX IF NOT EXISTS idx_pautador_opps_arbitrage ON public.pautador_opportunities (arbitrage_score DESC);

DROP TRIGGER IF EXISTS trg_pautador_opps_updated_at ON public.pautador_opportunities;
CREATE TRIGGER trg_pautador_opps_updated_at
    BEFORE UPDATE ON public.pautador_opportunities
    FOR EACH ROW EXECUTE FUNCTION public.set_pautador_updated_at();

COMMENT ON TABLE public.pautador_opportunities IS
    'Pautador Pro — card canonico de oportunidade. Estimativas qualitativas; arbitrage_score/roi derivados no backend.';
COMMENT ON COLUMN public.pautador_opportunities.tier     IS 'S (Ouro Puro) | A (Ouro) | B (Prata) | EXPERIMENTAL.';
COMMENT ON COLUMN public.pautador_opportunities.category IS 'S1..S6 | A1..A4 | B1..B3 | EXP.';
COMMENT ON COLUMN public.pautador_opportunities.status   IS 'Kanban: discovered -> validating -> mining -> funnel -> ready (+ rejected/archived).';

-- ---------------------------------------------------------------------
-- 4. pautador_keyword_clusters — arvore de keywords (Fase 2 / Minerador)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pautador_keyword_clusters (
    id              bigserial   PRIMARY KEY,
    run_id          bigint      REFERENCES public.pautador_runs(id) ON DELETE CASCADE,
    opportunity_id  bigint      REFERENCES public.pautador_opportunities(id) ON DELETE CASCADE,
    cluster_name    text        NOT NULL,
    main_keyword    text,
    intent          text,
    -- arvore: [{ keyword, volume, cpc_local, competition, intent }, ...]
    keywords        jsonb       NOT NULL DEFAULT '[]'::jsonb,
    total_volume    numeric(14,2),
    avg_cpc_local   numeric(14,4),
    currency        text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pautador_clusters_run         ON public.pautador_keyword_clusters (run_id);
CREATE INDEX IF NOT EXISTS idx_pautador_clusters_opportunity ON public.pautador_keyword_clusters (opportunity_id);

DROP TRIGGER IF EXISTS trg_pautador_clusters_updated_at ON public.pautador_keyword_clusters;
CREATE TRIGGER trg_pautador_clusters_updated_at
    BEFORE UPDATE ON public.pautador_keyword_clusters
    FOR EACH ROW EXECUTE FUNCTION public.set_pautador_updated_at();

COMMENT ON TABLE public.pautador_keyword_clusters IS
    'Pautador Pro — arvore de keywords (Fase 2 / Minerador) vinculada a uma oportunidade.';

-- ---------------------------------------------------------------------
-- 5. pautador_funnels — funil de 5 paginas (Fase 3 / Construtor de Funis)
--    Cada linha = UMA pagina do funil (avatar, objetivo emocional, etc).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pautador_funnels (
    id                bigserial   PRIMARY KEY,
    opportunity_id    bigint      NOT NULL REFERENCES public.pautador_opportunities(id) ON DELETE CASCADE,
    run_id            bigint      REFERENCES public.pautador_runs(id) ON DELETE SET NULL,
    funnel_name       text        NOT NULL,
    avatar            text,                                -- avatar/persona da pagina
    position          integer     NOT NULL DEFAULT 1,      -- 1..5 (ordem das paginas)
    page_title        text,
    stage             text        NOT NULL DEFAULT 'tofu'
        CHECK (stage IN ('tofu','mofu','bofu')),           -- topo/meio/fundo de funil
    emotional_goal    text,                                -- objetivo emocional da pagina
    subtitles         jsonb       NOT NULL DEFAULT '[]'::jsonb,  -- esqueleto de subtitulos
    internal_links    jsonb       NOT NULL DEFAULT '[]'::jsonb,  -- chamadas/ligacoes entre paginas
    content_outline   jsonb,                               -- estrutura adicional
    target_url        text,
    status            text        NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','planned','in_progress','published','archived')),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pautador_funnels_opportunity ON public.pautador_funnels (opportunity_id);
CREATE INDEX IF NOT EXISTS idx_pautador_funnels_run         ON public.pautador_funnels (run_id);
CREATE INDEX IF NOT EXISTS idx_pautador_funnels_status      ON public.pautador_funnels (status);

DROP TRIGGER IF EXISTS trg_pautador_funnels_updated_at ON public.pautador_funnels;
CREATE TRIGGER trg_pautador_funnels_updated_at
    BEFORE UPDATE ON public.pautador_funnels
    FOR EACH ROW EXECUTE FUNCTION public.set_pautador_updated_at();

COMMENT ON TABLE public.pautador_funnels IS
    'Pautador Pro — paginas do funil (Fase 3). Cada linha e uma das 5 paginas com avatar, objetivo emocional, subtitulos e ligacoes.';

-- ---------------------------------------------------------------------
-- 6. pautador_agent_logs — telemetria/auditoria (append-only; sem updated_at)
--    Estilo pipeline_logs / notification_log.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pautador_agent_logs (
    id              bigserial   PRIMARY KEY,
    run_id          bigint      REFERENCES public.pautador_runs(id) ON DELETE CASCADE,
    opportunity_id  bigint      REFERENCES public.pautador_opportunities(id) ON DELETE SET NULL,
    agent           text,                                  -- nome do agente (CountryResearchAgent, ...)
    phase           text,                                  -- discovery | mining | funnel
    level           text        NOT NULL DEFAULT 'info'
        CHECK (level IN ('debug','info','warn','error')),
    step            text,
    message         text        NOT NULL,
    payload         jsonb,                                 -- request/response estruturado
    n8n_execution_id text,
    duration_ms     integer,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pautador_logs_run     ON public.pautador_agent_logs (run_id);
CREATE INDEX IF NOT EXISTS idx_pautador_logs_level   ON public.pautador_agent_logs (level);
CREATE INDEX IF NOT EXISTS idx_pautador_logs_created ON public.pautador_agent_logs (created_at DESC);

COMMENT ON TABLE public.pautador_agent_logs IS
    'Pautador Pro — log append-only de telemetria/auditoria das execucoes dos agentes.';

-- =====================================================================
-- RLS — admin + human-in-the-loop
-- Policies por verbo com USING/WITH CHECK que checam o papel ADMIN na
-- tabela public.users pelo EMAIL do JWT: lower(email) = lower(auth.jwt()->>'email').
-- service_role (backend FastAPI / api/*) faz BYPASS automatico de RLS e
-- NUNCA e exposto ao frontend. anon NAO recebe acesso.
--
-- NOTA: o vinculo entre o usuario autenticado (Supabase Auth) e public.users
-- e feito por EMAIL (auth.jwt() ->> 'email'), pois public.users e indexada por
-- email (ver AuthContext.fetchUserProfile -> secureApi.me(), que desde
-- 24/08/2026 identifica o usuario pelo JWT em vez de por e-mail no corpo).
-- Verificado no banco: public.users NAO tem coluna google_oauth_id.
-- =====================================================================

ALTER TABLE public.pautador_countries        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pautador_runs             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pautador_opportunities    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pautador_keyword_clusters ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pautador_funnels          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pautador_agent_logs       ENABLE ROW LEVEL SECURITY;

-- ---- pautador_countries (ADMIN: tudo / autenticado: leitura) ----
DROP POLICY IF EXISTS "pautador_countries admin all" ON public.pautador_countries;
DROP POLICY IF EXISTS "pautador_countries read auth" ON public.pautador_countries;
CREATE POLICY "pautador_countries admin all"
    ON public.pautador_countries FOR ALL TO authenticated
    USING      (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email') AND u.role = 'ADMIN'))
    WITH CHECK (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email') AND u.role = 'ADMIN'));
CREATE POLICY "pautador_countries read auth"
    ON public.pautador_countries FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email')));

-- ---- pautador_runs (ADMIN: tudo / autenticado: leitura) ----
DROP POLICY IF EXISTS "pautador_runs admin all" ON public.pautador_runs;
DROP POLICY IF EXISTS "pautador_runs read auth" ON public.pautador_runs;
CREATE POLICY "pautador_runs admin all"
    ON public.pautador_runs FOR ALL TO authenticated
    USING      (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email') AND u.role = 'ADMIN'))
    WITH CHECK (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email') AND u.role = 'ADMIN'));
CREATE POLICY "pautador_runs read auth"
    ON public.pautador_runs FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email')));

-- ---- pautador_opportunities (ADMIN: tudo / autenticado: leitura + revisao) ----
DROP POLICY IF EXISTS "pautador_opportunities admin all"   ON public.pautador_opportunities;
DROP POLICY IF EXISTS "pautador_opportunities read auth"   ON public.pautador_opportunities;
DROP POLICY IF EXISTS "pautador_opportunities review auth" ON public.pautador_opportunities;
CREATE POLICY "pautador_opportunities admin all"
    ON public.pautador_opportunities FOR ALL TO authenticated
    USING      (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email') AND u.role = 'ADMIN'))
    WITH CHECK (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email') AND u.role = 'ADMIN'));
CREATE POLICY "pautador_opportunities read auth"
    ON public.pautador_opportunities FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email')));
-- NOTA: a pagina /pautador-pro e admin-only (ProtectedRoute + guard interno),
-- entao a policy "admin all" acima ja cobre os moves de Kanban feitos pelo admin.
-- NAO criamos uma UPDATE policy ampla "TO authenticated" porque RLS nao tem
-- granularidade de coluna: ela deixaria qualquer usuario autenticado reescrever
-- QUALQUER campo (keyword, tier, arbitrage_score...). Se no futuro operadores
-- precisarem mover cards, prefira controle por coluna:
--   REVOKE UPDATE ON public.pautador_opportunities FROM authenticated;
--   GRANT  UPDATE (status, reviewed_by, reviewed_at) ON public.pautador_opportunities TO authenticated;
-- combinado com uma policy USING que valide o usuario autenticado.

-- ---- pautador_keyword_clusters (ADMIN: tudo / autenticado: leitura) ----
DROP POLICY IF EXISTS "pautador_clusters admin all" ON public.pautador_keyword_clusters;
DROP POLICY IF EXISTS "pautador_clusters read auth" ON public.pautador_keyword_clusters;
CREATE POLICY "pautador_clusters admin all"
    ON public.pautador_keyword_clusters FOR ALL TO authenticated
    USING      (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email') AND u.role = 'ADMIN'))
    WITH CHECK (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email') AND u.role = 'ADMIN'));
CREATE POLICY "pautador_clusters read auth"
    ON public.pautador_keyword_clusters FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email')));

-- ---- pautador_funnels (ADMIN: tudo / autenticado: leitura) ----
DROP POLICY IF EXISTS "pautador_funnels admin all" ON public.pautador_funnels;
DROP POLICY IF EXISTS "pautador_funnels read auth" ON public.pautador_funnels;
CREATE POLICY "pautador_funnels admin all"
    ON public.pautador_funnels FOR ALL TO authenticated
    USING      (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email') AND u.role = 'ADMIN'))
    WITH CHECK (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email') AND u.role = 'ADMIN'));
CREATE POLICY "pautador_funnels read auth"
    ON public.pautador_funnels FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email')));

-- ---- pautador_agent_logs (somente ADMIN le; insert via service_role) ----
DROP POLICY IF EXISTS "pautador_logs admin read" ON public.pautador_agent_logs;
CREATE POLICY "pautador_logs admin read"
    ON public.pautador_agent_logs FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email') AND u.role = 'ADMIN'));

-- =====================================================================
-- Seed idempotente — paises da bancada de teste do documento (UK / PT / GT)
-- =====================================================================
INSERT INTO public.pautador_countries (country_code, country_name, native_language, market_tier, rpm_index, flag_emoji)
VALUES
    ('GB', 'Reino Unido', 'en-GB', 'high_value',   95.0000, '🇬🇧'),
    ('PT', 'Portugal',    'pt-PT', 'medium_value', 55.0000, '🇵🇹'),
    ('GT', 'Guatemala',   'es-GT', 'volume_play',  18.0000, '🇬🇹'),
    ('US', 'Estados Unidos', 'en-US', 'high_value', 100.0000, '🇺🇸'),
    ('BR', 'Brasil',      'pt-BR', 'medium_value', 30.0000, '🇧🇷'),
    ('DE', 'Alemanha',    'de-DE', 'high_value',   80.0000, '🇩🇪')
ON CONFLICT (country_code) DO NOTHING;

-- =====================================================================
-- Verificacao (opcional)
-- SELECT tablename FROM pg_tables WHERE tablename LIKE 'pautador_%';
-- SELECT schemaname, tablename, policyname FROM pg_policies WHERE tablename LIKE 'pautador_%';
-- =====================================================================
