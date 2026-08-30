-- =====================================================================================
-- BLOCO ........: INCUBADORA — TABELAS + VIEW
-- OBJETOS ......: public.incubator_sites
--                 public.incubator_articles
--                 public.incubator_pipeline_logs
--                 public.v_incubator_schedule_progress   (view de agregação)
--                 public.update_updated_at()             (função de trigger — auxiliar)
--
-- ORIGEM .......: reconstruído a partir do Supabase do WEBGO em 2026-08-05 por:
--                   (a) spec OpenAPI de <WEBGO>/rest/v1/  — tipos, formatos, NOT NULL,
--                       DEFAULTs, PKs e FKs (as FKs vêm no .description das colunas);
--                   (b) amostragem real: 4 linhas em incubator_sites, 128 em
--                       incubator_articles, 0 em incubator_pipeline_logs,
--                       4 linhas na view;
--                   (c) código consumidor já merjado no repo VOLC:
--                       src/types/incubator.ts, src/services/incubatorService.ts,
--                       src/hooks/incubator/*, src/components/incubator/*;
--                   (d) docs/archive/plans/incubadora-sites-plan.md — plano original da Incubadora.
--
-- DEPENDÊNCIAS .: public.users(id uuid)  -> já existe no VOLC (verificado via PostgREST).
--                 Extensão pgcrypto/uuid NÃO é necessária (nenhum default de uuid aqui).
--                 RPCs correlatas (NÃO fazem parte deste arquivo, entregues à parte):
--                   public.insert_incubator_articles_batch(p_site_id bigint, p_titles text[])
--                   public.claim_next_incubator_article(...)
--                 Edge Function `generate-schedule` (preenche scheduled_at/schedule_batch_id).
--
-- O QUE É INFERIDO (leia também o campo "incertezas" do relatório):
--   * estratégia de auto-incremento do id (IDENTITY vs bigserial) — não observável;
--   * ON DELETE das FKs (CASCADE para site_id inferido de deleteSite(); SET NULL para
--     created_by inferido do fato da coluna ser NULLABLE);
--   * a query interna da view (deduzida das 11 colunas + confronto com os dados);
--   * função/trigger de updated_at (evidência forte, ver seção 1);
--   * TODOS os índices (nenhum índice é observável via PostgREST);
--   * enums de status: valores vindos de src/types/incubator.ts, NÃO de CHECKs lidos.
--
-- O QUE É *OBSERVADO* E NÃO FOI REPRODUZIDO — LEIA A SEÇÃO 10:
--   No WEBGO as 3 tabelas estão com ROW LEVEL SECURITY **LIGADA**. Não consegui ler
--   pg_policies, então NÃO reproduzo policies inventadas. As tabelas são criadas aqui
--   SEM RLS, e a seção 10 traz o bloco pronto (comentado) + como descobrir o real.
--
-- SEGURANÇA DE EXECUÇÃO: script idempotente e NÃO destrutivo.
--   Sem DROP TABLE, DROP COLUMN, TRUNCATE ou DELETE. Os únicos DROPs são
--   `DROP TRIGGER IF EXISTS` imediatamente antes do CREATE TRIGGER correspondente
--   (Postgres não tem CREATE OR REPLACE TRIGGER até a v14; este é o padrão idempotente
--   canônico e não toca em dado nenhum).
--
-- VALIDADO: este script foi aplicado 2x (idempotência) num PostgreSQL 16 descartável
--   local, com stubs de public.users e dos papéis anon/authenticated/service_role.
--   Em seguida os 4 sites e os 128 artigos reais do WEBGO foram carregados e a view
--   reconstruída devolveu EXATAMENTE os mesmos valores da view real do WEBGO nas 11
--   colunas e nas 4 linhas.
-- =====================================================================================

BEGIN;

-- =====================================================================================
-- 1. FUNÇÃO DE TRIGGER updated_at
-- -------------------------------------------------------------------------------------
-- INFERIDO (com evidência forte). Não dá para ler o corpo de funções de trigger via
-- PostgREST (elas não são expostas como RPC). A evidência de que existe um trigger,
-- e não atualização feita pela aplicação:
--   * em incubator_articles, `updated_at` tem 5–6 dígitos de fração de segundo em
--     100% das 128 linhas (assinatura de now() do Postgres), enquanto `published_at`
--     tem 3 dígitos (assinatura de `new Date().toISOString()` do JS/n8n);
--   * em linhas publicadas, updated_at é ~40–120 ms POSTERIOR a published_at
--     (ex.: published_at=15:43:12.303  ->  updated_at=15:43:12.410953), ou seja, foi
--     carimbado pelo banco no momento do UPDATE, não pelo cliente;
--   * docs/archive/plans/incubadora-sites-plan.md, ETAPA 1: "Funcao update_updated_at() + triggers" — e registra que a
--     função não existia e precisava ser criada na migration. O nome vem daí.
--
-- Criada com guarda "só se não existir" em vez de CREATE OR REPLACE: se outro bloco da
-- sincronização já tiver criado public.update_updated_at() com corpo próprio, não
-- queremos sobrescrever silenciosamente.
-- =====================================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.proname = 'update_updated_at'
           AND p.pronargs = 0
    ) THEN
        CREATE FUNCTION public.update_updated_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $fn$;
        COMMENT ON FUNCTION public.update_updated_at() IS
            'Trigger BEFORE UPDATE genérica: carimba NEW.updated_at = now(). Usada pelas tabelas da Incubadora.';
    ELSE
        RAISE NOTICE 'public.update_updated_at() já existe — mantida como está.';
    END IF;
END
$$;


-- =====================================================================================
-- 2. TABELA public.incubator_sites
-- -------------------------------------------------------------------------------------
-- Um "site incubado": domínio WordPress próprio que recebe artigos gerados por IA até
-- ficar apto a submeter ao AdSense.
--
-- OBSERVADO no spec (tipo, formato, DEFAULT e nulidade de TODAS as colunas abaixo).
-- Atenção a duas peculiaridades OBSERVADAS que parecem erro mas não são:
--   * NOT NULL é só: id, site_name, site_niche, site_audience, wp_url, status, country.
--     created_at/updated_at e TODOS os contadores/flags são NULLABLE apesar de terem
--     DEFAULT (confirmei o critério do PostgREST: `required` == NOT NULL, independente
--     de DEFAULT — controlado contra outras tabelas do mesmo spec). Reproduzido fiel.
--   * schedule_window_start/end são **text** com DEFAULT '7' e '21' (não são time nem
--     integer). Os dados reais guardam 'HH:MM' ('09:22', '07:00', '21:00'), e o front
--     tem um normalizador para o formato legado sem ':' — ver toTimeStr() em
--     src/services/incubatorService.ts:155. Ou seja, o DEFAULT numérico é resíduo
--     histórico e está sendo reproduzido tal como está no WEBGO.
--
-- INFERIDO: `GENERATED BY DEFAULT AS IDENTITY`. O spec só mostra id bigint NOT NULL PK
-- (o PostgREST esconde o default de sequência). Escolhi BY DEFAULT (e não ALWAYS) para
-- não bloquear um eventual import preservando os ids do WEBGO. Comportamento
-- equivalente a bigserial para todos os caminhos da aplicação.
-- =====================================================================================
CREATE TABLE IF NOT EXISTS public.incubator_sites (
    id                            bigint      GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    -- Identidade editorial do site (tudo NOT NULL — vem do NewSiteModal)
    site_name                     text        NOT NULL,
    site_niche                    text        NOT NULL,
    site_audience                 text        NOT NULL,
    country                       text        NOT NULL DEFAULT 'Brasil',
    site_context                  text,

    -- Credenciais WordPress usadas pelo n8n para publicar
    wp_url                        text        NOT NULL,
    wp_username                   text,
    wp_app_password               text,

    -- Integração com Google Sheets (legado — 100% NULL nas 4 linhas reais)
    sheets_url                    text,
    sheet_tab_name                text,

    -- Estado no Kanban da Incubadora
    status                        text        NOT NULL DEFAULT 'draft',

    -- Contadores denormalizados (mantidos pelo n8n / pelo front, não por trigger)
    total_articles_planned        integer     DEFAULT 0,
    total_articles_published      integer     DEFAULT 0,
    total_articles_failed         integer     DEFAULT 0,

    -- Ciclo do AdSense (100% NULL nas 4 linhas reais — colunas ainda não exercitadas)
    adsense_submission_date       timestamptz,
    adsense_response_date         timestamptz,
    adsense_rejection_reason      text,
    adsense_pub_id                text,

    -- Rastro da execução no n8n (100% NULL nas 4 linhas reais)
    n8n_workflow_id               text,
    n8n_last_execution_id         text,
    n8n_last_execution_status     text,

    -- Configuração do pipeline de conteúdo
    auto_publish                  boolean     DEFAULT true,
    articles_per_batch            integer     DEFAULT 5,

    -- Configuração do AGENDAMENTO de publicação (consumida pela Edge Function
    -- generate-schedule e por src/components/incubator/schedule/ScheduleConfig.tsx)
    schedule_total_days           integer     DEFAULT 7,
    schedule_window_start         text        DEFAULT '7',   -- ver nota acima: hoje guarda 'HH:MM'
    schedule_window_end           text        DEFAULT '21',  -- idem
    schedule_min_gap_minutes      integer     DEFAULT 45,
    schedule_active               boolean     DEFAULT false,
    schedule_started_at           timestamptz,
    schedule_estimated_completion timestamptz,

    -- Autoria e auditoria
    created_by                    uuid,       -- FK -> public.users(id), criada na seção 5
    created_at                    timestamptz DEFAULT now(),
    updated_at                    timestamptz DEFAULT now()
);

-- Reconciliação para instalações parciais/antigas desta tabela.
-- Só entra em ação se a tabela JÁ existia sem as colunas que foram acrescentadas
-- depois no WEBGO (site_context, country e o bloco schedule_*). É aditivo e idempotente.
ALTER TABLE public.incubator_sites
    ADD COLUMN IF NOT EXISTS site_context                  text,
    ADD COLUMN IF NOT EXISTS country                       text        NOT NULL DEFAULT 'Brasil',
    ADD COLUMN IF NOT EXISTS schedule_total_days           integer     DEFAULT 7,
    ADD COLUMN IF NOT EXISTS schedule_window_start         text        DEFAULT '7',
    ADD COLUMN IF NOT EXISTS schedule_window_end           text        DEFAULT '21',
    ADD COLUMN IF NOT EXISTS schedule_min_gap_minutes      integer     DEFAULT 45,
    ADD COLUMN IF NOT EXISTS schedule_active               boolean     DEFAULT false,
    ADD COLUMN IF NOT EXISTS schedule_started_at           timestamptz,
    ADD COLUMN IF NOT EXISTS schedule_estimated_completion timestamptz;


-- =====================================================================================
-- 3. TABELA public.incubator_articles
-- -------------------------------------------------------------------------------------
-- Uma linha por artigo. Nasce como um TÍTULO puro (status 'pending') inserido em lote
-- pela RPC insert_incubator_articles_batch, ganha um horário de publicação
-- (scheduled_at + schedule_batch_id) pela Edge Function generate-schedule, e é
-- consumido pelo n8n, que vai promovendo o status até 'published'.
--
-- OBSERVADO: NOT NULL apenas em id, site_id, title, status (default 'pending').
--            Todo o resto é nullable. 128 linhas reais confirmam o preenchimento
--            progressivo (slug/seo_title/wp_post_id só aparecem em 'published').
-- OBSERVADO: `published_at` tem 3 dígitos de fração (gravado pelo n8n em JS) e
--            `scheduled_at` tem 0 dígitos (segundos truncados pelo gerador de schedule).
--            Nenhuma das duas tem DEFAULT.
-- =====================================================================================
CREATE TABLE IF NOT EXISTS public.incubator_articles (
    id                 bigint      GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    site_id            bigint      NOT NULL,          -- FK -> incubator_sites(id), seção 5
    title              text        NOT NULL,

    -- Estado no pipeline de conteúdo
    status             text        NOT NULL DEFAULT 'pending',

    -- Resultado no WordPress (preenchido só quando publica)
    slug               text,
    wp_post_id         bigint,
    wp_post_url        text,

    -- Campos de SEO produzidos pela IA
    seo_title          text,
    meta_description   text,
    focus_keyword      text,
    excerpt            text,
    featured_image_url text,
    image_alt_text     text,

    -- Diagnóstico de falha (usado por retryArticle/retryAllFailed no service)
    failed_at_step     text,
    error_message      text,
    retry_count        integer     DEFAULT 0,

    -- Agendamento de publicação
    scheduled_at       timestamptz,
    schedule_batch_id  uuid,       -- agrupa tudo que foi agendado numa mesma rodada

    -- Auditoria
    created_at         timestamptz DEFAULT now(),
    published_at       timestamptz,
    updated_at         timestamptz DEFAULT now()
);

-- Reconciliação aditiva (mesma lógica da seção 2): scheduled_at/schedule_batch_id
-- claramente entraram depois, junto com a feature de agendamento.
ALTER TABLE public.incubator_articles
    ADD COLUMN IF NOT EXISTS scheduled_at      timestamptz,
    ADD COLUMN IF NOT EXISTS schedule_batch_id uuid;


-- =====================================================================================
-- 4. TABELA public.incubator_pipeline_logs
-- -------------------------------------------------------------------------------------
-- Timeline de execuções do pipeline por site. Renderizada em
-- src/components/incubator/detail/PipelineLog.tsx via fetchPipelineLogs(), que faz
-- `.eq('site_id', X).order('started_at', desc).limit(20)`.
--
-- ATENÇÃO — HONESTIDADE: esta tabela está **VAZIA no WEBGO** (0 linhas, confirmado com
-- Prefer: count=exact). Logo, os valores de execution_type e status NÃO puderam ser
-- observados em dado real: eles vêm exclusivamente dos tipos ExecutionType/ExecutionStatus
-- em src/types/incubator.ts:28-38 e estão apenas documentados em COMMENT (seção 9), sem
-- CHECK. Toda a estrutura de colunas, essa sim, é OBSERVADA no spec.
-- =====================================================================================
CREATE TABLE IF NOT EXISTS public.incubator_pipeline_logs (
    id                 bigint      GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    site_id            bigint      NOT NULL,          -- FK -> incubator_sites(id), seção 5

    execution_type     text        NOT NULL,          -- content_batch | single_article | adsense_submit | status_check
    status             text        NOT NULL DEFAULT 'running',  -- running | success | partial_success | error

    articles_attempted integer     DEFAULT 0,
    articles_succeeded integer     DEFAULT 0,
    articles_failed    integer     DEFAULT 0,

    error_message      text,
    n8n_execution_id   text,

    started_at         timestamptz DEFAULT now(),
    completed_at       timestamptz,
    duration_seconds   integer
);


-- =====================================================================================
-- 5. CHAVES ESTRANGEIRAS
-- -------------------------------------------------------------------------------------
-- OBSERVADO (o alvo de cada FK vem do .description da coluna no spec OpenAPI):
--   incubator_sites.created_by      -> users.id
--   incubator_articles.site_id      -> incubator_sites.id
--   incubator_pipeline_logs.site_id -> incubator_sites.id
--
-- INFERIDO (a ação ON DELETE não aparece no spec):
--   * site_id -> CASCADE. Evidência forte: incubatorService.deleteSite() (linha 92)
--     apaga o site direto, sem apagar artigos/logs antes. Sem CASCADE, deletar
--     qualquer site com artigos daria erro de FK — e o botão de excluir do Kanban
--     funciona no WEBGO. ON UPDATE fica no default (NO ACTION); a PK é identity e
--     nunca é atualizada.
--   * created_by -> SET NULL. A coluna é NULLABLE (observado), o que combina com
--     SET NULL; e evita que apagar um usuário no painel de admin fique bloqueado
--     por FK ou, pior, arraste sites junto. Se você preferir fidelidade máxima e
--     sabe que lá é NO ACTION, troque abaixo.
-- =====================================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'incubator_sites_created_by_fkey' AND conrelid = 'public.incubator_sites'::regclass) THEN
        ALTER TABLE public.incubator_sites
            ADD CONSTRAINT incubator_sites_created_by_fkey
            FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'incubator_articles_site_id_fkey' AND conrelid = 'public.incubator_articles'::regclass) THEN
        ALTER TABLE public.incubator_articles
            ADD CONSTRAINT incubator_articles_site_id_fkey
            FOREIGN KEY (site_id) REFERENCES public.incubator_sites(id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'incubator_pipeline_logs_site_id_fkey' AND conrelid = 'public.incubator_pipeline_logs'::regclass) THEN
        ALTER TABLE public.incubator_pipeline_logs
            ADD CONSTRAINT incubator_pipeline_logs_site_id_fkey
            FOREIGN KEY (site_id) REFERENCES public.incubator_sites(id) ON DELETE CASCADE;
    END IF;
END
$$;


-- =====================================================================================
-- 6. ÍNDICES
-- -------------------------------------------------------------------------------------
-- TODOS INFERIDOS. Índice não é observável via PostgREST — o que está aqui foi derivado
-- das queries que o código REALMENTE executa. A referência de cada um está no comentário.
-- Nenhum é UNIQUE (ver seção 11 sobre a unicidade de (site_id, title), que não consegui
-- determinar).
-- =====================================================================================

-- --- incubator_sites -------------------------------------------------------------
-- fetchSites(): .order('updated_at', desc)  [incubatorService.ts:19] — listagem do
-- dashboard e do Kanban, é a query mais chamada da tela.
CREATE INDEX IF NOT EXISTS idx_incubator_sites_updated_at
    ON public.incubator_sites (updated_at DESC);

-- Agrupamento por coluna do Kanban e KpiCards (contagem por status).
CREATE INDEX IF NOT EXISTS idx_incubator_sites_status
    ON public.incubator_sites (status);

-- Suporte à FK created_by: o Postgres NÃO indexa o lado filho automaticamente, e sem
-- este índice todo DELETE/UPDATE em public.users faz seq scan em incubator_sites.
CREATE INDEX IF NOT EXISTS idx_incubator_sites_created_by
    ON public.incubator_sites (created_by);

-- Parcial: o worker de agendamento só se interessa por sites com schedule ligado.
CREATE INDEX IF NOT EXISTS idx_incubator_sites_schedule_active
    ON public.incubator_sites (id)
    WHERE schedule_active;

-- --- incubator_articles ----------------------------------------------------------
-- Suporte à FK site_id (obrigatório para o ON DELETE CASCADE não virar seq scan) e
-- base de todas as consultas por site.
CREATE INDEX IF NOT EXISTS idx_incubator_articles_site_id
    ON public.incubator_articles (site_id);

-- fetchArticles(): .eq('site_id',X).order('created_at', desc)  [incubatorService.ts:106-108]
CREATE INDEX IF NOT EXISTS idx_incubator_articles_site_created_at
    ON public.incubator_articles (site_id, created_at DESC);

-- Filtro (site_id, status). Usado em MUITOS pontos:
--   startPipeline() conta pending          [incubatorService.ts:146-147]
--   clearSchedule() zera pending           [incubatorService.ts:261-262]
--   retryAllFailed() busca failed          [incubatorService.ts:304-305]
--   useTitles.removeTitles() in(pending,failed)
--   e é o índice que serve a agregação da view v_incubator_schedule_progress.
CREATE INDEX IF NOT EXISTS idx_incubator_articles_site_status
    ON public.incubator_articles (site_id, status);

-- Ordenação da timeline de publicação (ScheduleTimeline.tsx ordena por scheduled_at).
CREATE INDEX IF NOT EXISTS idx_incubator_articles_scheduled_at
    ON public.incubator_articles (scheduled_at);

-- Índice PARCIAL do caminho quente do n8n (claim_next_incubator_article: "o próximo
-- pendente cujo horário já chegou") foi movido para 02_incubator_functions.sql, onde
-- é criado como idx_incubator_articles_fila (scheduled_at, id) WHERE status='pending'.
-- A versão de lá cobre também o desempate por id do ORDER BY da função, então manter
-- as duas deixaria um índice redundante custando escrita à toa.

-- Agrupamento por rodada de agendamento (schedule_batch_id devolvido por generate-schedule).
CREATE INDEX IF NOT EXISTS idx_incubator_articles_batch
    ON public.incubator_articles (schedule_batch_id);

-- Deduplicação de títulos: insert_incubator_articles_batch devolve `skipped_duplicates`
-- (ver BulkInsertResult em src/types/incubator.ts:135) e useTitles.fetchExistingTitles()
-- lê todos os títulos do site. NÃO é UNIQUE de propósito — ver seção 11.
-- O índice fica em 02_incubator_functions.sql como idx_incubator_articles_site_title_norm
-- (site_id, lower(btrim(title))), que é a forma que casa com o anti-join normalizado da
-- função de insert. Um índice em (site_id, title) cru não seria usado por aquele plano.

-- --- incubator_pipeline_logs -----------------------------------------------------
-- fetchPipelineLogs(): .eq('site_id',X).order('started_at', desc).limit(20)
-- [incubatorService.ts:119-122] — é literalmente a única query desta tabela no front.
CREATE INDEX IF NOT EXISTS idx_incubator_pipeline_logs_site_started_at
    ON public.incubator_pipeline_logs (site_id, started_at DESC);

-- Parcial: encontrar execuções ainda em andamento (para marcar timeout/travamento).
CREATE INDEX IF NOT EXISTS idx_incubator_pipeline_logs_running
    ON public.incubator_pipeline_logs (started_at)
    WHERE status = 'running';


-- =====================================================================================
-- 7. TRIGGERS DE updated_at
-- -------------------------------------------------------------------------------------
-- INFERIDO — justificativa e evidência na seção 1.
-- incubator_pipeline_logs NÃO recebe trigger: ela não tem coluna updated_at (observado
-- no spec), o ciclo de vida dela é started_at -> completed_at.
-- DROP TRIGGER IF EXISTS + CREATE é o padrão idempotente; não afeta dados.
-- =====================================================================================
DROP TRIGGER IF EXISTS trg_incubator_sites_updated_at ON public.incubator_sites;
CREATE TRIGGER trg_incubator_sites_updated_at
    BEFORE UPDATE ON public.incubator_sites
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

DROP TRIGGER IF EXISTS trg_incubator_articles_updated_at ON public.incubator_articles;
CREATE TRIGGER trg_incubator_articles_updated_at
    BEFORE UPDATE ON public.incubator_articles
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


-- =====================================================================================
-- 8. VIEW public.v_incubator_schedule_progress
-- -------------------------------------------------------------------------------------
-- OBSERVADO: as 11 primeiras colunas, na ordem exata do spec OpenAPI —
--   site_id, site_name, schedule_active, schedule_started_at,
--   schedule_estimated_completion, total_scheduled, total_published, total_failed,
--   total_waiting, total_overdue, next_scheduled_at.
--   Os cinco primeiros vêm crus de incubator_sites; os total_* são bigint (COUNT).
-- OBSERVADO: as 4 linhas da view no WEBGO batem 1:1 com os 4 sites, INCLUSIVE o site 5,
--   que tem schedule_active=false e schedule_started_at=null -> a view NÃO filtra por
--   schedule_active. E o `site_id` é marcado como PK pelo PostgREST -> 1 linha por site.
--
-- INFERIDO (a query em si). Como cada agregado foi deduzido, confrontado com os dados
-- reais (128 artigos / 4 sites):
--
--  total_scheduled  = COUNT FILTER (scheduled_at IS NOT NULL)
--      Observado 28/20/30/50 para os sites 4/5/6/7. Hoje TODOS os 128 artigos têm
--      scheduled_at, então COUNT(*) daria o mesmo número — não dá para distinguir só
--      pelos dados. Escolhi o FILTER por dois motivos: o nome da coluna, e o fato de
--      clearSchedule() [incubatorService.ts:258-263] setar scheduled_at=NULL nos
--      pendentes; com COUNT(*) o "total agendado" continuaria mentindo depois de
--      limpar o schedule.
--
--  total_published  = COUNT FILTER (status = 'published')
--      Bate exatamente: 28/10/2/33 na view vs. 28/10/2/33 contando os artigos.
--
--  total_failed     = COUNT FILTER (status = 'failed')
--      Observado 0 nos 4 sites; não há nenhum artigo 'failed' no banco, então o valor
--      do literal 'failed' vem de ArticleStatus (src/types/incubator.ts:26) e de
--      retryAllFailed()/.eq('status','failed') [incubatorService.ts:305].
--
--  total_waiting    = COUNT FILTER (status = 'pending' AND scheduled_at >  now())
--  total_overdue    = COUNT FILTER (status = 'pending' AND scheduled_at <= now())
--      Aqui a dedução é a parte mais informativa. A view devolve 0 e 0 para os quatro
--      sites, MAS os sites 5/6/7 têm 55 artigos em estados intermediários
--      (image_generating=51, writing=3, researching=1) com scheduled_at NO PASSADO.
--      Portanto "overdue" NÃO pode ser "não publicado e horário vencido" — isso daria
--      55, não 0. O único recorte compatível com 0 é restringir a status='pending'
--      (fila que ainda não foi puxada pelo n8n) — e de fato não há nenhuma linha
--      'pending' hoje no WEBGO. O par waiting/overdue é então a mesma fila partida
--      pelo horário: ainda vai chegar vs. já passou da hora.
--
--  next_scheduled_at = MIN(scheduled_at) FILTER (status='pending' AND scheduled_at > now())
--      Observado NULL nos 4 sites — consistente com "zero pendentes". Escolhi
--      restringir ao futuro porque a UI rotula esse valor como "Próximo artigo"
--      (ScheduleTimeline.tsx:151) e porque o atraso já é reportado por total_overdue.
--
-- INFERIDO: LEFT JOIN (e não INNER). Todos os 4 sites do WEBGO têm artigos, então o
--   dado não distingue. LEFT JOIN faz um site recém-criado aparecer com zeros em vez de
--   sumir; o front tolera as duas formas (trata PGRST116 como null em
--   fetchScheduleProgress, incubatorService.ts:248-251).
--
-- SEM `security_invoker`: OBSERVADO. Sondei a view com a chave ANON do WEBGO e ela
--   devolve as 4 linhas, enquanto as 3 tabelas devolvem 0 linhas para o mesmo anon.
--   Isso só acontece se a view roda com os direitos do dono (padrão do Postgres,
--   security_invoker = false). Reproduzido igual. Consequência: quando você ligar RLS
--   nas tabelas (seção 10), esta view continuará legível por quem tiver GRANT nela —
--   é assim que o WEBGO está hoje, mas é um bypass consciente de RLS.
--
-- Colunas 12+ (published_count ... estimated_completion): ADIÇÃO DELIBERADA, NÃO
--   existem no WEBGO. Motivo: a interface ScheduleProgress do repo
--   (src/types/incubator.ts:223-233) declara published_count/pending_count/failed_count/
--   progress_pct/last_published_at/estimated_completion, e ScheduleTimeline.tsx:58 lê
--   `progress.published_count` e `progress.progress_pct` — que hoje sairiam `undefined`
--   contra a view real do WEBGO. Como são colunas ADITIVAS (nada quebra em quem usa
--   select('*')), incluí para o front funcionar. Se você quiser fidelidade estrita ao
--   WEBGO, apague o bloco entre os marcadores COMPAT abaixo.
-- =====================================================================================
CREATE OR REPLACE VIEW public.v_incubator_schedule_progress AS
SELECT
    -- ---- colunas 1..5: cruas de incubator_sites (OBSERVADAS) ----
    s.id                                AS site_id,
    s.site_name,
    s.schedule_active,
    s.schedule_started_at,
    s.schedule_estimated_completion,

    -- ---- colunas 6..11: agregados (OBSERVADAS no spec, query INFERIDA) ----
    COUNT(a.id) FILTER (WHERE a.scheduled_at IS NOT NULL)                    AS total_scheduled,
    COUNT(a.id) FILTER (WHERE a.status = 'published')                        AS total_published,
    COUNT(a.id) FILTER (WHERE a.status = 'failed')                           AS total_failed,
    COUNT(a.id) FILTER (WHERE a.status = 'pending'
                          AND a.scheduled_at IS NOT NULL
                          AND a.scheduled_at >  now())                       AS total_waiting,
    COUNT(a.id) FILTER (WHERE a.status = 'pending'
                          AND a.scheduled_at IS NOT NULL
                          AND a.scheduled_at <= now())                       AS total_overdue,
    MIN(a.scheduled_at) FILTER (WHERE a.status = 'pending'
                                  AND a.scheduled_at > now())                AS next_scheduled_at,

    -- ==================== INÍCIO COMPAT (não existe no WEBGO) ====================
    -- Aliases/derivados para satisfazer a interface ScheduleProgress do front.
    COUNT(a.id) FILTER (WHERE a.status = 'published')                        AS published_count,
    COUNT(a.id) FILTER (WHERE a.scheduled_at IS NOT NULL
                          AND a.status NOT IN ('published', 'failed'))       AS pending_count,
    COUNT(a.id) FILTER (WHERE a.status = 'failed')                           AS failed_count,
    CASE
        WHEN COUNT(a.id) FILTER (WHERE a.scheduled_at IS NOT NULL) > 0
        THEN ROUND(
                 100.0 * COUNT(a.id) FILTER (WHERE a.status = 'published')
                       / COUNT(a.id) FILTER (WHERE a.scheduled_at IS NOT NULL)
             )::int
        ELSE 0
    END                                                                      AS progress_pct,
    MAX(a.published_at)                                                      AS last_published_at,
    s.schedule_estimated_completion                                          AS estimated_completion
    -- ===================== FIM COMPAT ============================================
FROM public.incubator_sites s
LEFT JOIN public.incubator_articles a
       ON a.site_id = s.id
-- GROUP BY só pela PK: o Postgres reconhece a dependência funcional e libera s.site_name
-- e os demais s.* no SELECT. Assim, acrescentar coluna de site na view não exige mexer aqui.
GROUP BY s.id;


-- =====================================================================================
-- 9. DOCUMENTAÇÃO (aparece no Studio e no \d+)
-- -------------------------------------------------------------------------------------
-- Os valores de status listados abaixo vêm de src/types/incubator.ts, NÃO de CHECKs
-- lidos do banco. Estão como COMMENT justamente para documentar sem impor constraint.
-- Marcados com (visto) os valores que aparecem em dado real no WEBGO hoje.
-- =====================================================================================
COMMENT ON TABLE public.incubator_sites IS
    'Incubadora — 1 linha por site WordPress incubado. Fluxo: criar (draft) -> gerar conteúdo por IA via n8n -> submeter ao AdSense -> aprovado. Reconstruída do Supabase do WEBGO em 2026-08-05 a partir do spec OpenAPI + dados reais; índices, triggers e ON DELETE são inferidos.';
COMMENT ON COLUMN public.incubator_sites.status IS
    'Estado no Kanban. Valores (de SiteStatus em src/types/incubator.ts:7-16): draft (visto) | content_generating (visto) | content_ready | review | submitting (visto) | submitted | approved (visto) | rejected | paused. SEM CHECK no banco — ver seção 11 do script.';
COMMENT ON COLUMN public.incubator_sites.schedule_window_start IS
    'Início da janela diária de publicação. Tipo TEXT (não time) e DEFAULT ''7'' — resíduo histórico OBSERVADO no WEBGO. Os dados reais guardam ''HH:MM'' (ex.: ''09:22''). O front normaliza o formato legado em toTimeStr(), src/services/incubatorService.ts:155.';
COMMENT ON COLUMN public.incubator_sites.schedule_window_end IS
    'Fim da janela diária de publicação. Mesmas observações de schedule_window_start; DEFAULT ''21''.';
COMMENT ON COLUMN public.incubator_sites.schedule_min_gap_minutes IS
    'Intervalo mínimo, em minutos, entre duas publicações do mesmo site. Consumido pela Edge Function generate-schedule. Valores reais vistos: 5, 45, 60.';
COMMENT ON COLUMN public.incubator_sites.created_by IS
    'Autor do site. FK -> public.users(id) (uuid). ATENÇÃO: NÃO é auth.uid(). O front resolve esse uuid buscando public.users pelo EMAIL do usuário autenticado (incubatorService.ts:41-48), ou seja, users.id e auth.uid() são identidades distintas neste sistema — isso importa se você for escrever policies de RLS.';
COMMENT ON COLUMN public.incubator_sites.total_articles_planned IS
    'Contador denormalizado. NÃO é mantido por trigger: quem atualiza é a aplicação (useTitles.removeTitles recalcula com COUNT e faz UPDATE) e o n8n.';

COMMENT ON TABLE public.incubator_articles IS
    'Incubadora — 1 linha por artigo. Nasce só com o título (status pending) via RPC insert_incubator_articles_batch, recebe scheduled_at/schedule_batch_id da Edge Function generate-schedule e é promovido pelo n8n até published.';
COMMENT ON COLUMN public.incubator_articles.status IS
    'Estado no pipeline de conteúdo. Valores (de ArticleStatus em src/types/incubator.ts:18-26): pending | researching (visto) | writing (visto) | seo_optimizing | image_generating (visto) | publishing | published (visto) | failed. SEM CHECK no banco — ver seção 11.';
COMMENT ON COLUMN public.incubator_articles.scheduled_at IS
    'Horário-alvo de publicação, calculado pela Edge Function generate-schedule dentro da janela do site. Nos dados reais vem com segundos truncados (sem fração). NULL = artigo sem agendamento (é o que clearSchedule() faz nos pendentes).';
COMMENT ON COLUMN public.incubator_articles.schedule_batch_id IS
    'uuid da rodada de agendamento que produziu este scheduled_at (campo batch_id da resposta de generate-schedule). Permite reagendar/limpar um lote inteiro.';
COMMENT ON COLUMN public.incubator_articles.published_at IS
    'Carimbado pelo n8n no momento da publicação no WordPress (precisão de milissegundo, vem do JS). Diferente de updated_at, que é carimbado pelo banco.';
COMMENT ON COLUMN public.incubator_articles.failed_at_step IS
    'Etapa do pipeline onde falhou. Zerado junto com error_message por retryArticle/retryAllFailed. Nenhuma linha real preenchida até hoje.';

COMMENT ON TABLE public.incubator_pipeline_logs IS
    'Incubadora — timeline de execuções do pipeline por site (renderizada por PipelineLog.tsx). ATENÇÃO: tabela VAZIA no WEBGO na data da reconstrução (0 linhas), portanto os valores de execution_type/status não são observados, só documentados a partir dos tipos do front.';
COMMENT ON COLUMN public.incubator_pipeline_logs.execution_type IS
    'Tipo da execução. Valores de ExecutionType (src/types/incubator.ts:28-32): content_batch | single_article | adsense_submit | status_check. NENHUM observado em dado real — tabela vazia.';
COMMENT ON COLUMN public.incubator_pipeline_logs.status IS
    'Resultado da execução. Valores de ExecutionStatus (src/types/incubator.ts:34-38): running (default) | success | partial_success | error. NENHUM observado em dado real — tabela vazia.';

COMMENT ON VIEW public.v_incubator_schedule_progress IS
    'Incubadora — progresso do agendamento de publicação, 1 linha por site (inclusive sites com schedule desligado). Colunas 1..11 são fiéis ao WEBGO; a query de agregação é INFERIDA (conferida contra os 128 artigos reais). As colunas published_count/pending_count/failed_count/progress_pct/last_published_at/estimated_completion NÃO existem no WEBGO — foram acrescentadas para casar com a interface ScheduleProgress do front (src/types/incubator.ts:223).';


-- =====================================================================================
-- 10. RLS — ESTADO REAL DO WEBGO E POR QUE ESTE SCRIPT *NÃO* LIGA RLS
-- -------------------------------------------------------------------------------------
-- OBSERVADO (sondagem read-only feita com a chave ANON do WEBGO):
--     incubator_sites          -> anon recebe 0 linhas (service_role recebe 4)
--     incubator_articles       -> anon recebe 0 linhas (service_role recebe 128)
--     incubator_pipeline_logs  -> anon recebe 0 linhas (tabela vazia, inconclusivo)
--     v_incubator_schedule_progress -> anon recebe as 4 linhas normalmente
--   Conclusão segura: no WEBGO, RLS está **LIGADA** em incubator_sites e
--   incubator_articles, e não existe policy que atenda o papel `anon`.
--
-- INFERIDO (com confiança alta): existe policy para o papel `authenticated` com CRUD
--   completo. O front usa um client Supabase comum com a ANON KEY + sessão do usuário
--   (src/lib/supabase.ts:10), e faz select/insert/update/delete direto nessas tabelas.
--   Se não houvesse policy para authenticated, a Incubadora inteira estaria quebrada
--   no WEBGO — e ela funciona.
--
-- O QUE EU NÃO CONSEGUI DETERMINAR: o PREDICADO das policies. Sem acesso a pg_policies
--   não dá para saber se é `USING (true) TO authenticated` ou se há checagem de papel
--   (ex.: EXISTS em public.users com role='ADMIN'). Note que o repo tem OS DOIS estilos:
--   src/sql/setup_users_rls_policies.sql usa checagem de ADMIN, e
--   src/sql/v7_13_meta_capi_sites.sql usa "RLS ligada e ZERO policies" de propósito.
--   Nenhum dos dois pode ser assumido aqui.
--
-- DECISÃO: conforme instruído, NÃO invento policy. As tabelas ficam SEM RLS, o que é
--   uma REGRESSÃO DE SEGURANÇA CONSCIENTE em relação ao WEBGO: com a instalação atual,
--   qualquer portador da anon key do VOLC lê e escreve nas 3 tabelas — inclusive
--   incubator_sites.wp_app_password, que guarda senha de aplicativo do WordPress em
--   TEXTO PURO. Resolva isso antes de expor a instância.
--
-- COMO DESCOBRIR O REAL (rode no SQL Editor do WEBGO, é só leitura):
--     SELECT tablename, policyname, permissive, roles, cmd, qual, with_check
--       FROM pg_policies
--      WHERE schemaname = 'public'
--        AND tablename LIKE 'incubator_%'
--      ORDER BY tablename, policyname;
--     SELECT relname, relrowsecurity, relforcerowsecurity
--       FROM pg_class
--      WHERE relname LIKE 'incubator_%';
--
-- BLOCO PRONTO — descomente SÓ depois de confirmar acima que o predicado é este:
-- ------------------------------------------------------------------------------------
-- ALTER TABLE public.incubator_sites         ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.incubator_articles      ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.incubator_pipeline_logs ENABLE ROW LEVEL SECURITY;
--
-- DROP POLICY IF EXISTS incubator_sites_authenticated_all         ON public.incubator_sites;
-- CREATE POLICY incubator_sites_authenticated_all
--     ON public.incubator_sites FOR ALL TO authenticated
--     USING (true) WITH CHECK (true);
--
-- DROP POLICY IF EXISTS incubator_articles_authenticated_all      ON public.incubator_articles;
-- CREATE POLICY incubator_articles_authenticated_all
--     ON public.incubator_articles FOR ALL TO authenticated
--     USING (true) WITH CHECK (true);
--
-- DROP POLICY IF EXISTS incubator_pipeline_logs_authenticated_all ON public.incubator_pipeline_logs;
-- CREATE POLICY incubator_pipeline_logs_authenticated_all
--     ON public.incubator_pipeline_logs FOR ALL TO authenticated
--     USING (true) WITH CHECK (true);
-- ------------------------------------------------------------------------------------


-- =====================================================================================
-- 11. CHECK CONSTRAINTS E UNICIDADE — DELIBERADAMENTE NÃO APLICADOS
-- -------------------------------------------------------------------------------------
-- (a) CHECK de status: não consigo ler pg_constraint do WEBGO. Se eu criar um CHECK e o
--     WEBGO não tiver, o primeiro status novo que o n8n gravar quebra a produção; se o
--     WEBGO tiver e eu não criar, nada quebra. Assimetria clara -> não criar. As listas
--     de valores estão documentadas em COMMENT (seção 9). Descomente se quiser travar:
--
-- ALTER TABLE public.incubator_sites    ADD CONSTRAINT incubator_sites_status_check
--     CHECK (status IN ('draft','content_generating','content_ready','review',
--                       'submitting','submitted','approved','rejected','paused'));
-- ALTER TABLE public.incubator_articles ADD CONSTRAINT incubator_articles_status_check
--     CHECK (status IN ('pending','researching','writing','seo_optimizing',
--                       'image_generating','publishing','published','failed'));
-- ALTER TABLE public.incubator_pipeline_logs ADD CONSTRAINT incubator_pipeline_logs_type_check
--     CHECK (execution_type IN ('content_batch','single_article','adsense_submit','status_check'));
-- ALTER TABLE public.incubator_pipeline_logs ADD CONSTRAINT incubator_pipeline_logs_status_check
--     CHECK (status IN ('running','success','partial_success','error'));
--
-- (b) UNIQUE (site_id, title): há indício, não prova. A RPC
--     insert_incubator_articles_batch devolve `skipped_duplicates` (BulkInsertResult,
--     src/types/incubator.ts:135), TitleInput.tsx faz dedupe no cliente, e não existe
--     nenhum par (site_id, title) repetido nas 128 linhas reais. Mas "devolve
--     skipped_duplicates" tanto pode ser ON CONFLICT DO NOTHING (exige o índice único)
--     quanto NOT EXISTS (não exige). ATENÇÃO AO ORQUESTRADOR: se o DDL da RPC
--     insert_incubator_articles_batch usar ON CONFLICT (site_id, title), este índice
--     único é OBRIGATÓRIO ou a RPC dá erro em tempo de execução — descomente:
--
-- CREATE UNIQUE INDEX IF NOT EXISTS uq_incubator_articles_site_title
--     ON public.incubator_articles (site_id, title);
--
--     (No mesmo caso, remova o idx_incubator_articles_site_title não-único da seção 6,
--      que passa a ser redundante.)
-- =====================================================================================


-- =====================================================================================
-- 12. REALTIME
-- -------------------------------------------------------------------------------------
-- INFERIDO a partir do código: src/hooks/incubator/useIncubatorRealtime.ts assina
-- postgres_changes (INSERT e UPDATE) em public.incubator_sites e public.incubator_articles.
-- Sem as tabelas na publication supabase_realtime, o hook assina e nunca recebe evento —
-- falha silenciosa, sem erro na tela. O plano arquivado da Incubadora (ETAPA 1) também lista "Realtime publication".
-- incubator_pipeline_logs NÃO é assinada por ninguém, então fica de fora.
--
-- Envolvido em bloco com tratamento de exceção porque ALTER PUBLICATION exige ser dono
-- da publication; se o papel que roda a migration não tiver, o script emite aviso em vez
-- de abortar tudo.
-- =====================================================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_publication_tables
             WHERE pubname = 'supabase_realtime'
               AND schemaname = 'public' AND tablename = 'incubator_sites'
        ) THEN
            ALTER PUBLICATION supabase_realtime ADD TABLE public.incubator_sites;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_publication_tables
             WHERE pubname = 'supabase_realtime'
               AND schemaname = 'public' AND tablename = 'incubator_articles'
        ) THEN
            ALTER PUBLICATION supabase_realtime ADD TABLE public.incubator_articles;
        END IF;
    ELSE
        RAISE NOTICE 'Publication supabase_realtime não existe — Realtime não configurado para a Incubadora.';
    END IF;
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'Sem permissão para ALTER PUBLICATION supabase_realtime. Rode como owner: ALTER PUBLICATION supabase_realtime ADD TABLE public.incubator_sites, public.incubator_articles;';
END
$$;


-- =====================================================================================
-- 13. GRANTS
-- -------------------------------------------------------------------------------------
-- Necessários porque o VOLC é self-hosted e nem sempre há default privileges configurados
-- para os papéis do PostgREST. Com RLS desligada (seção 10), estes grants por si só já
-- dão acesso total — mais um motivo para resolver a RLS antes de expor a instância.
--
-- `anon` recebe SELECT SÓ na view: é exatamente o que foi OBSERVADO no WEBGO (anon lê a
-- view e não lê as tabelas). Se você achar que isso é vazamento (a view expõe site_name),
-- remova `anon` da última linha — o front autenticado não depende dele.
--
-- NÃO há GRANT em sequência: as PKs são `GENERATED BY DEFAULT AS IDENTITY`, e o Postgres
-- não exige privilégio na sequência subjacente para identity (ao contrário de bigserial).
-- Se você trocar as PKs para bigserial, aí sim precisará de
-- GRANT USAGE, SELECT ON SEQUENCE public.<tabela>_id_seq TO authenticated, service_role.
--
-- Envolvido em DO porque em instalação self-hosted algum desses papéis pode não existir;
-- nesse caso o script avisa em vez de abortar a migration inteira.
-- =====================================================================================
DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['authenticated', 'service_role'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.incubator_sites         TO %I', r);
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.incubator_articles      TO %I', r);
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.incubator_pipeline_logs TO %I', r);
            EXECUTE format('GRANT SELECT ON public.v_incubator_schedule_progress TO %I', r);
        ELSE
            RAISE NOTICE 'Papel % não existe nesta instância — grants ignorados.', r;
        END IF;
    END LOOP;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'GRANT SELECT ON public.v_incubator_schedule_progress TO anon';
    END IF;
END
$$;

COMMIT;

-- =====================================================================================
-- PÓS-EXECUÇÃO — SE VOCÊ IMPORTAR OS DADOS DO WEBGO PRESERVANDO OS IDs,
-- avance as sequências ou o próximo INSERT colide com a PK:
--
--   SELECT setval(pg_get_serial_sequence('public.incubator_sites','id'),
--                 COALESCE((SELECT MAX(id) FROM public.incubator_sites), 1));
--   SELECT setval(pg_get_serial_sequence('public.incubator_articles','id'),
--                 COALESCE((SELECT MAX(id) FROM public.incubator_articles), 1));
--   SELECT setval(pg_get_serial_sequence('public.incubator_pipeline_logs','id'),
--                 COALESCE((SELECT MAX(id) FROM public.incubator_pipeline_logs), 1));
-- =====================================================================================
