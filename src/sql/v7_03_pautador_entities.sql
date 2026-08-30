-- =====================================================================
-- v7 PAUTADOR PRO — Etapa 3 / ENTITY-FIRST (ADITIVO, NÃO destrutivo)
-- Nova camada onde a UNIDADE do Kanban é uma ENTIDADE (RUT, DIAN, INSS…),
-- e keywords/dores/funis viram subestrutura. Coexiste com pautador_* atual.
--
-- Convenção do repo: prefixo pautador_, PK bigserial, timestamptz, text+CHECK,
-- arrays como jsonb, RLS admin-by-email + read-auth, triggers updated_at.
-- Idempotente (IF NOT EXISTS / DROP POLICY IF EXISTS). Roda DEPOIS de v7_01.
-- >>> Rodar manualmente no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. pautador_entities — o núcleo explorável de conteúdo
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pautador_entities (
    id               bigserial   PRIMARY KEY,
    run_id           bigint      REFERENCES public.pautador_runs(id) ON DELETE SET NULL,
    country_code     text        NOT NULL,
    country          text,                                  -- nome PT-BR (display)
    canonical_name   text        NOT NULL,                  -- "RUT"
    full_name        text,                                  -- "Registro Único Tributario"
    slug             text        NOT NULL,                  -- "rut" (normalizado, siglas preservadas)
    entity_type      text,                                  -- tax_registry, agency, benefit_program...
    entity_category  text,                                  -- identificacao_fiscal, saude, previdencia...
    official_source  text,                                  -- "DIAN" (órgão/fonte oficial)
    related_systems  jsonb       NOT NULL DEFAULT '[]'::jsonb,  -- ["MUISCA"]
    aliases          jsonb       NOT NULL DEFAULT '[]'::jsonb,
    description      text,
    language         text,                                  -- idioma nativo (es-CO...)
    status           text        NOT NULL DEFAULT 'discovered'
        CHECK (status IN ('discovered','validating','mining','funnel','ready','rejected','archived')),
    source           text        NOT NULL DEFAULT 'agent'
        CHECK (source IN ('agent','manual','backfill')),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_pautador_entities_country_slug UNIQUE (country_code, slug)
);

CREATE INDEX IF NOT EXISTS idx_pautador_entities_country  ON public.pautador_entities (country_code);
CREATE INDEX IF NOT EXISTS idx_pautador_entities_slug     ON public.pautador_entities (slug);
CREATE INDEX IF NOT EXISTS idx_pautador_entities_type     ON public.pautador_entities (entity_type);
CREATE INDEX IF NOT EXISTS idx_pautador_entities_category ON public.pautador_entities (entity_category);

DROP TRIGGER IF EXISTS trg_pautador_entities_updated_at ON public.pautador_entities;
CREATE TRIGGER trg_pautador_entities_updated_at
    BEFORE UPDATE ON public.pautador_entities
    FOR EACH ROW EXECUTE FUNCTION public.set_pautador_updated_at();

COMMENT ON TABLE public.pautador_entities IS
    'Pautador Pro ENTITY-FIRST — entidade explorável (RUT, DIAN, INSS…). Unidade do Kanban.';

-- ---------------------------------------------------------------------
-- 2. pautador_entity_opportunities — o CARD do Kanban (1 por entidade)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pautador_entity_opportunities (
    id                bigserial   PRIMARY KEY,
    entity_id         bigint      NOT NULL REFERENCES public.pautador_entities(id) ON DELETE CASCADE,
    run_id            bigint      REFERENCES public.pautador_runs(id) ON DELETE SET NULL,
    country_code      text        NOT NULL,
    status            text        NOT NULL DEFAULT 'discovered'
        CHECK (status IN ('discovered','validating','mining','funnel','ready','rejected','archived')),
    kanban_stage      text        NOT NULL DEFAULT 'discovered',
    gold_tier         text        CHECK (gold_tier IS NULL OR gold_tier IN ('S','A','B','EXPERIMENTAL')),
    strategic_stage   text,                                  -- "S1 · Ponte de utilidade"
    score             numeric(10,4),
    roi_signal        numeric(14,4),
    cpc_min           numeric(14,4),
    cpc_max           numeric(14,4),
    cpc_currency      text,
    volume_level      text,
    rpm_level         text,
    competition_level text,
    confidence_level  text,
    temporal_window   text,
    concrete_pain     text,
    gold_reason       text,
    notes             jsonb       NOT NULL DEFAULT '{}'::jsonb,
    reviewed_by       uuid        REFERENCES public.users(id) ON DELETE SET NULL,
    reviewed_at       timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_pautador_entity_opportunities_entity UNIQUE (entity_id)
);

CREATE INDEX IF NOT EXISTS idx_pautador_entopp_country ON public.pautador_entity_opportunities (country_code);
CREATE INDEX IF NOT EXISTS idx_pautador_entopp_status  ON public.pautador_entity_opportunities (status);
CREATE INDEX IF NOT EXISTS idx_pautador_entopp_score   ON public.pautador_entity_opportunities (score DESC);
CREATE INDEX IF NOT EXISTS idx_pautador_entopp_entity  ON public.pautador_entity_opportunities (entity_id);

DROP TRIGGER IF EXISTS trg_pautador_entopp_updated_at ON public.pautador_entity_opportunities;
CREATE TRIGGER trg_pautador_entopp_updated_at
    BEFORE UPDATE ON public.pautador_entity_opportunities
    FOR EACH ROW EXECUTE FUNCTION public.set_pautador_updated_at();

COMMENT ON TABLE public.pautador_entity_opportunities IS
    'Pautador Pro ENTITY-FIRST — card do Kanban (1 por entidade). Score/ROI auditáveis.';

-- ---------------------------------------------------------------------
-- 3. pautador_entity_seed_queries — keywords/queries (evidência da entidade)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pautador_entity_seed_queries (
    id              bigserial   PRIMARY KEY,
    entity_id       bigint      NOT NULL REFERENCES public.pautador_entities(id) ON DELETE CASCADE,
    opportunity_id  bigint      REFERENCES public.pautador_entity_opportunities(id) ON DELETE CASCADE,
    query           text        NOT NULL,
    query_type      text,                                  -- seed|variation|pain|long_tail|official|transactional|informational
    intent          text,
    score           numeric(10,4),
    source          text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pautador_seedq_entity_query
    ON public.pautador_entity_seed_queries (entity_id, lower(query));
CREATE INDEX IF NOT EXISTS idx_pautador_seedq_entity ON public.pautador_entity_seed_queries (entity_id);

COMMENT ON TABLE public.pautador_entity_seed_queries IS
    'Pautador Pro ENTITY-FIRST — seed queries/keywords da entidade (evidência, não card).';

-- ---------------------------------------------------------------------
-- 4. pautador_entity_pains — dores derivadas da entidade
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pautador_entity_pains (
    id                bigserial   PRIMARY KEY,
    entity_id         bigint      NOT NULL REFERENCES public.pautador_entities(id) ON DELETE CASCADE,
    opportunity_id    bigint      REFERENCES public.pautador_entity_opportunities(id) ON DELETE CASCADE,
    pain_name         text        NOT NULL,
    pain_description  text,
    user_goal         text,
    intent            text,
    severity          text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pautador_pains_entity_name
    ON public.pautador_entity_pains (entity_id, lower(pain_name));
CREATE INDEX IF NOT EXISTS idx_pautador_pains_entity ON public.pautador_entity_pains (entity_id);

COMMENT ON TABLE public.pautador_entity_pains IS
    'Pautador Pro ENTITY-FIRST — dores derivadas da entidade.';

-- ---------------------------------------------------------------------
-- 5. pautador_entity_funnel_hypotheses — hipóteses de funil da entidade
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pautador_entity_funnel_hypotheses (
    id              bigserial   PRIMARY KEY,
    entity_id       bigint      REFERENCES public.pautador_entities(id) ON DELETE CASCADE,
    opportunity_id  bigint      REFERENCES public.pautador_entity_opportunities(id) ON DELETE CASCADE,
    country_code    text        NOT NULL,
    funnel_title    text        NOT NULL,
    funnel_summary  text,
    pages           jsonb       NOT NULL DEFAULT '[]'::jsonb,
    status          text        NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','planned','in_progress','published','archived')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pautador_funnelhyp_entity ON public.pautador_entity_funnel_hypotheses (entity_id);
CREATE INDEX IF NOT EXISTS idx_pautador_funnelhyp_opp    ON public.pautador_entity_funnel_hypotheses (opportunity_id);

DROP TRIGGER IF EXISTS trg_pautador_funnelhyp_updated_at ON public.pautador_entity_funnel_hypotheses;
CREATE TRIGGER trg_pautador_funnelhyp_updated_at
    BEFORE UPDATE ON public.pautador_entity_funnel_hypotheses
    FOR EACH ROW EXECUTE FUNCTION public.set_pautador_updated_at();

COMMENT ON TABLE public.pautador_entity_funnel_hypotheses IS
    'Pautador Pro ENTITY-FIRST — hipóteses de funil centradas na entidade.';

-- =====================================================================
-- RLS — admin-by-email (igual v7_01). service_role faz BYPASS.
-- =====================================================================
ALTER TABLE public.pautador_entities                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pautador_entity_opportunities     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pautador_entity_seed_queries      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pautador_entity_pains             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pautador_entity_funnel_hypotheses ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'pautador_entities',
        'pautador_entity_opportunities',
        'pautador_entity_seed_queries',
        'pautador_entity_pains',
        'pautador_entity_funnel_hypotheses'
    ] LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || ' admin all', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || ' read auth', t);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR ALL TO authenticated '
            'USING (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> ''email'') AND u.role = ''ADMIN'')) '
            'WITH CHECK (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> ''email'') AND u.role = ''ADMIN''))',
            t || ' admin all', t);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated '
            'USING (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> ''email'')))',
            t || ' read auth', t);
    END LOOP;
END $$;

-- =====================================================================
-- Verificação (opcional)
-- SELECT tablename FROM pg_tables WHERE tablename LIKE 'pautador_entit%';
-- =====================================================================
