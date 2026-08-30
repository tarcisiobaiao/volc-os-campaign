-- =====================================================================================
-- APLICAR NO SUPABASE STUDIO -> SQL EDITOR  (VOLC O.S. / sync webgov6)
-- =====================================================================================
-- Cole este arquivo inteiro e clique em RUN. Sao os 3 blocos aplicaveis, ja na ordem
-- correta de dependencia. Todos idempotentes (pode rodar de novo sem estragar nada).
--
-- Se der erro em algum ponto, PARE e mande o erro — nao force. Os blocos foram
-- validados contra um PostgreSQL 16 com o schema real do seu banco, mas o Studio roda
-- contra o banco de verdade e pode haver algo que a validacao nao viu.
--
-- NAO inclui o bloco de cambio mensal (04), bloqueado por 2 defeitos destrutivos
-- — ver README.md nesta pasta.
-- =====================================================================================


-- #####################################################################
-- ## BLOCO 1/3 — INCUBADORA: TABELAS + VIEW
-- #####################################################################
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


-- #####################################################################
-- ## BLOCO 2/3 — INCUBADORA: FUNCOES (depende do bloco 1)
-- #####################################################################
-- =============================================================================
-- BLOCO: INCUBADORA — FUNÇÕES (RPC)
-- Objetos criados:
--   1) public.claim_next_incubator_article()                       -> jsonb
--   2) public.insert_incubator_articles_batch(bigint, text[])      -> jsonb
--
-- Origem / procedência deste DDL:
--   O corpo original destas funções NÃO estava versionado em lugar nenhum e não
--   é acessível via PostgREST (não há acesso a pg_catalog / pg_get_functiondef
--   no Supabase de origem). Portanto este arquivo é uma RECONSTRUÇÃO
--   COMPORTAMENTAL: as ASSINATURAS e o CONTRATO DE RETORNO são OBSERVADOS
--   (spec OpenAPI do WEBGO + call sites reais), o CORPO é INFERIDO.
--
--   Evidências usadas (todas de leitura):
--   [OBS-1] Spec OpenAPI WEBGO (PostgREST 12.2.12), path
--           /rpc/insert_incubator_articles_batch:
--             POST body {p_site_id: integer/bigint, p_titles: array of string
--             (format text[])}, ambos required  -> assinatura exata.
--   [OBS-2] Spec OpenAPI WEBGO, path /rpc/claim_next_incubator_article:
--           GET sem parameters e POST com schema de body {"type":"object"} sem
--           properties -> a função NÃO recebe argumentos.
--   [OBS-3] src/hooks/incubator/useTitles.ts + src/services/incubatorService.ts
--           chamam a RPC com {p_site_id, p_titles} e fazem
--           `return data as BulkInsertResult`, e BulkInsertResult
--           (src/types/incubator.ts) = { inserted, skipped_duplicates,
--           total_articles } -> a função retorna UM objeto JSON (jsonb), não
--           uma tabela.
--   [OBS-4] Workflow n8n "Incubator Cron Publisher"
--           (/Users/mac/Desktop/SISTEMAS/WEBGO/Sistema Webgo/incubator_cron_publisher.json):
--             - node "⏰ Cron 10min"  -> polling a cada 10 minutos;
--             - node "🔍 Claim Next Article" -> POST .../rpc/claim_next_incubator_article
--               com body literal "{}" (confirma zero argumentos);
--             - node "🔀 Artigo encontrado?" -> testa `$json.found === true`
--               (boolean estrito);
--             - node "🎯 CONFIG (from Supabase)" -> lê `$json.article.id`,
--               `$json.article.title`, `$json.article.site_id`,
--               `$json.site.site_name`, `.site_niche`, `.site_audience`,
--               `.wp_url`, `.wp_username`, `.wp_app_password`.
--           => contrato de retorno: {found: bool, article: {...}, site: {...}}.
--   [OBS-5] Dados reais do WEBGO: nas 4 campanhas existentes,
--           incubator_sites.total_articles_planned == COUNT(incubator_articles)
--           do site (28/28, 20/20, 30/30, 50/50); e o frontend NUNCA escreve
--           total_articles_planned no caminho de inserção (só no de remoção,
--           useTitles.ts:49) -> quem mantém esse contador na inserção é a RPC.
--   [OBS-6] Dados reais: todas as linhas de um mesmo lote têm created_at
--           idêntico ao microssegundo -> a inserção é uma única instrução SQL
--           (INSERT ... SELECT FROM unnest(...)), não um loop.
--   [OBS-7] Dados reais + view v_incubator_schedule_progress: existem 55 linhas
--           em status intermediário (researching/writing/image_generating) com
--           scheduled_at no passado, e mesmo assim total_waiting/total_overdue
--           da view são 0 -> a "fila" é definida por status = 'pending'.
--
-- Dependências (devem existir ANTES deste arquivo):
--   - public.incubator_sites     (id bigint PK, schedule_active boolean,
--                                 total_articles_planned int, updated_at timestamptz, ...)
--   - public.incubator_articles  (id bigint PK, site_id bigint FK -> incubator_sites.id,
--                                 title text, status text, retry_count int,
--                                 scheduled_at timestamptz, created_at/updated_at timestamptz, ...)
--   - roles padrão do Supabase: anon, authenticated, service_role
--
-- Não destrutivo: nenhum DROP TABLE / DROP COLUMN / TRUNCATE / DELETE.
-- Idempotente: pode ser executado várias vezes.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 0) GUARDA DE IDEMPOTÊNCIA
--
-- CREATE OR REPLACE FUNCTION falha com erro se já existir uma função com o MESMO
-- nome e MESMOS argumentos porém com TIPO DE RETORNO diferente. Para que este
-- arquivo possa ser reaplicado com segurança, removemos APENAS nesse caso, e
-- APENAS a assinatura exata (forma específica com a lista de tipos). Nenhum
-- outro overload é tocado.
-- -----------------------------------------------------------------------------
DO $guard$
DECLARE
  v_oid     oid;
  v_retorno text;
BEGIN
  -- claim_next_incubator_article()
  v_oid := to_regprocedure('public.claim_next_incubator_article()');
  IF v_oid IS NOT NULL THEN
    SELECT pg_get_function_result(v_oid) INTO v_retorno;
    IF v_retorno IS DISTINCT FROM 'jsonb' THEN
      RAISE NOTICE 'Removendo public.claim_next_incubator_article() (retorno atual: %, esperado: jsonb)', v_retorno;
      DROP FUNCTION public.claim_next_incubator_article();
    END IF;
  END IF;

  -- insert_incubator_articles_batch(bigint, text[])
  v_oid := to_regprocedure('public.insert_incubator_articles_batch(bigint, text[])');
  IF v_oid IS NOT NULL THEN
    SELECT pg_get_function_result(v_oid) INTO v_retorno;
    IF v_retorno IS DISTINCT FROM 'jsonb' THEN
      RAISE NOTICE 'Removendo public.insert_incubator_articles_batch(bigint, text[]) (retorno atual: %, esperado: jsonb)', v_retorno;
      DROP FUNCTION public.insert_incubator_articles_batch(bigint, text[]);
    END IF;
  END IF;
END
$guard$;


-- -----------------------------------------------------------------------------
-- 1) ÍNDICES DE APOIO (opcionais, não obrigatórios para as funções rodarem)
--
-- 1a) Índice parcial da fila: acelera o SELECT ... FOR UPDATE SKIP LOCKED do
--     claim, que sempre filtra status='pending' e ordena por scheduled_at.
--     INFERIDO (otimização); não altera semântica.
-- 1b) Índice de deduplicação por (site_id, lower(btrim(title))).
--     NÃO consegui determinar se o WEBGO tem um índice único aqui — o PostgREST
--     não expõe índices. Os dados reais NÃO contêm nenhum título duplicado
--     dentro do mesmo site (128 linhas, 0 duplicatas), o que é compatível tanto
--     com um índice único quanto com dedup só na função.
--     Por segurança este índice é criado como NÃO-ÚNICO: ele acelera o
--     anti-join de deduplicação sem risco de falhar caso a tabela de destino já
--     contenha duplicatas. A criação do índice ÚNICO fica comentada abaixo, para
--     decisão consciente de quem aplica.
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_incubator_articles_fila
  ON public.incubator_articles (scheduled_at, id)
  WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_incubator_articles_site_title_norm
  ON public.incubator_articles (site_id, lower(btrim(title)));

-- OPCIONAL / decisão do operador: transformar a dedup em garantia do banco.
-- Só rode se tiver certeza de que não há duplicatas pré-existentes, senão falha.
--   CREATE UNIQUE INDEX IF NOT EXISTS uq_incubator_articles_site_title_norm
--     ON public.incubator_articles (site_id, lower(btrim(title)));


-- -----------------------------------------------------------------------------
-- 2) claim_next_incubator_article()
--
-- Contrato (OBSERVADO em [OBS-2] e [OBS-4]):
--   - sem argumentos;
--   - retorna UM objeto jsonb:
--       { "found": true,  "article": {<linha completa de incubator_articles>},
--                          "site":    {<linha completa de incubator_sites>} }
--       { "found": false, "article": null, "site": null }
--
-- Comportamento (INFERIDO — padrão de FILA):
--   Seleciona o próximo artigo elegível e o marca como reivindicado dentro da
--   MESMA instrução, de forma atômica. Usa
--       UPDATE ... WHERE id = (SELECT ... ORDER BY ... LIMIT 1
--                              FOR UPDATE SKIP LOCKED) RETURNING *
--   SKIP LOCKED é obrigatório: o cron do n8n roda a cada 10 min e pode ter
--   execuções concorrentes/sobrepostas; sem SKIP LOCKED dois workers podem
--   reivindicar o mesmo artigo (ou serializar e travar).
--
-- Elegibilidade (INFERIDA, com as evidências entre colchetes):
--   a.status = 'pending'          -- [OBS-7] a fila é o status 'pending'
--   a.scheduled_at IS NOT NULL
--   a.scheduled_at <= now()       -- o schedule é o "quando"; retryArticle()
--                                 -- (incubatorService.ts) recoloca em 'pending'
--                                 -- com scheduled_at = agora + 1 min
--   s.schedule_active IS TRUE     -- pauseSchedule()/resumeSchedule() só mexem
--                                 -- nesse flag; se o claim não o respeitasse,
--                                 -- o botão "Pausar" da UI não teria efeito
--   ORDER BY a.scheduled_at, a.id -- FIFO pelo horário agendado
--
-- Marcação da reivindicação (INFERIDA):
--   status := 'researching'. Não existe coluna claimed_at / locked_by /
--   worker_id em incubator_articles [OBS: spec OpenAPI lista as 21 colunas], logo
--   a única marca possível é a transição de status. 'researching' é o primeiro
--   passo do pipeline no type ArticleStatus (src/types/incubator.ts) e o nó
--   seguinte do n8n ("📡 Status → researching") faz exatamente esse PATCH — aqui
--   ele se torna redundante, o que é o comportamento seguro.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.claim_next_incubator_article()
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $fn$
DECLARE
  v_article public.incubator_articles%ROWTYPE;
  v_site    public.incubator_sites%ROWTYPE;
BEGIN
  -- Reivindicação atômica: a subquery escolhe UM candidato, trava a linha
  -- (pulando as já travadas por outro worker) e o UPDATE externo a marca.
  UPDATE public.incubator_articles AS a
     SET status     = 'researching',
         updated_at = now()
   WHERE a.id = (
           SELECT c.id
             FROM public.incubator_articles AS c
            WHERE c.status = 'pending'
              AND c.scheduled_at IS NOT NULL
              AND c.scheduled_at <= now()
              -- Respeita o botão Pausar/Retomar da UI. Se você decidir que
              -- retentativas devem rodar mesmo em site pausado, comente as
              -- 5 linhas abaixo (é o único ponto a mudar).
              AND c.site_id IN (
                    SELECT s.id
                      FROM public.incubator_sites AS s
                     WHERE s.schedule_active IS TRUE
                  )
            ORDER BY c.scheduled_at ASC, c.id ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
         )
  RETURNING a.* INTO v_article;

  -- Nada elegível agora (fila vazia, nada vencido, ou tudo travado por outro worker).
  IF NOT FOUND THEN
    RETURN jsonb_build_object(
      'found',   false,
      'article', NULL,
      'site',    NULL
    );
  END IF;

  -- O n8n precisa das credenciais/contexto do site no mesmo payload
  -- (site_name, site_niche, site_audience, wp_url, wp_username, wp_app_password).
  SELECT s.* INTO v_site
    FROM public.incubator_sites AS s
   WHERE s.id = v_article.site_id;

  RETURN jsonb_build_object(
    'found',   true,
    'article', to_jsonb(v_article),
    'site',    to_jsonb(v_site)
  );
END;
$fn$;

COMMENT ON FUNCTION public.claim_next_incubator_article() IS
  'Incubadora: reivindica atomicamente o proximo artigo elegivel da fila '
  '(status=pending, scheduled_at<=now(), site com schedule_active=true), '
  'marcando-o como researching, e devolve {found, article, site} em jsonb. '
  'Usa FOR UPDATE SKIP LOCKED (seguro para workers concorrentes). '
  'DDL RECONSTRUIDO: assinatura e contrato de retorno observados; corpo inferido.';


-- -----------------------------------------------------------------------------
-- 3) insert_incubator_articles_batch(p_site_id bigint, p_titles text[])
--
-- Contrato (OBSERVADO em [OBS-1] e [OBS-3]):
--   - argumentos p_site_id bigint (required) e p_titles text[] (required);
--   - retorna UM objeto jsonb:
--       { "inserted": int, "skipped_duplicates": int, "total_articles": int }
--
-- Comportamento (INFERIDO):
--   - Insere em UMA única instrução (unnest + INSERT ... SELECT) [OBS-6].
--   - Idempotente por chave natural (site_id, título normalizado): reexecutar o
--     mesmo lote não duplica nada, apenas soma em skipped_duplicates. Isso é
--     obrigatório porque quem chama é automação/UI com retry.
--   - A normalização do título é lower(btrim(title)), espelhando a deduplicação
--     que o front já faz em src/components/incubator/TitleInput.tsx
--     (`t.toLowerCase().trim()`).
--   - Deduplica também DENTRO do próprio array recebido (DISTINCT ON).
--   - A dedup é feita por anti-join NOT EXISTS + `ON CONFLICT DO NOTHING` sem
--     alvo. Motivo: `ON CONFLICT (col,...) DO NOTHING` com alvo explícito FALHA
--     se o índice único correspondente não existir, e não foi possível confirmar
--     se ele existe no WEBGO. A forma sem alvo funciona com ou sem índice.
--   - Atualiza incubator_sites.total_articles_planned com a contagem real de
--     artigos do site [OBS-5].
--   - Novos artigos nascem status='pending', scheduled_at NULL: o agendamento é
--     feito depois pela Edge Function `generate-schedule`
--     (incubatorService.ts:generateSchedule).
--
-- Semântica de skipped_duplicates (INFERIDA):
--   recebidos - inserted, isto é, tudo que veio no array e não virou linha nova
--   (duplicata interna ao lote, duplicata já existente no site, ou string vazia).
--   inserted + skipped_duplicates == cardinality(p_titles), sempre.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.insert_incubator_articles_batch(
  p_site_id bigint,
  p_titles  text[]
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $fn$
DECLARE
  v_recebidos integer := 0;
  v_inserted  integer := 0;
  v_total     bigint  := 0;
BEGIN
  IF p_site_id IS NULL THEN
    RAISE EXCEPTION 'insert_incubator_articles_batch: p_site_id e obrigatorio';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM public.incubator_sites WHERE id = p_site_id) THEN
    RAISE EXCEPTION 'insert_incubator_articles_batch: site % nao encontrado em incubator_sites', p_site_id
      USING ERRCODE = 'foreign_key_violation';
  END IF;

  v_recebidos := COALESCE(array_length(p_titles, 1), 0);

  IF v_recebidos > 0 THEN
    WITH entrada AS (
      -- 1 linha por título normalizado: mata duplicata interna ao lote e branco
      SELECT DISTINCT ON (lower(btrim(t.titulo)))
             btrim(t.titulo) AS titulo
        FROM unnest(p_titles) AS t(titulo)
       WHERE btrim(COALESCE(t.titulo, '')) <> ''
       ORDER BY lower(btrim(t.titulo))
    ),
    inseridos AS (
      INSERT INTO public.incubator_articles (
        site_id, title, status, retry_count, created_at, updated_at
      )
      SELECT p_site_id, e.titulo, 'pending', 0, now(), now()
        FROM entrada AS e
       WHERE NOT EXISTS (            -- mata duplicata já existente no site
             SELECT 1
               FROM public.incubator_articles AS a
              WHERE a.site_id = p_site_id
                AND lower(btrim(a.title)) = lower(e.titulo)
           )
      ON CONFLICT DO NOTHING          -- rede de proteção p/ corrida entre 2 lotes
      RETURNING 1
    )
    SELECT count(*)::integer INTO v_inserted FROM inseridos;
  END IF;

  -- Contagem real depois da inserção (é o total_articles devolvido à UI).
  SELECT count(*) INTO v_total
    FROM public.incubator_articles
   WHERE site_id = p_site_id;

  -- Mantém o contador do site coerente com a realidade [OBS-5].
  UPDATE public.incubator_sites
     SET total_articles_planned = v_total,
         updated_at             = now()
   WHERE id = p_site_id;

  RETURN jsonb_build_object(
    'inserted',           v_inserted,
    'skipped_duplicates', GREATEST(v_recebidos - v_inserted, 0),
    'total_articles',     v_total
  );
END;
$fn$;

COMMENT ON FUNCTION public.insert_incubator_articles_batch(bigint, text[]) IS
  'Incubadora: insere um lote de titulos como artigos pending de um site, em uma '
  'unica instrucao, deduplicando por (site_id, lower(btrim(title))) dentro do lote '
  'e contra o que ja existe; atualiza incubator_sites.total_articles_planned e '
  'devolve {inserted, skipped_duplicates, total_articles} em jsonb. '
  'DDL RECONSTRUIDO: assinatura e contrato de retorno observados; corpo inferido.';


-- -----------------------------------------------------------------------------
-- 4) PERMISSÕES
--
-- Por padrão o PostgreSQL concede EXECUTE a PUBLIC em toda função nova, o que no
-- Supabase expõe a RPC ao role `anon` (qualquer visitante com a anon key).
-- Aqui restringimos:
--   - insert_incubator_articles_batch: chamada pelo browser com sessão logada
--     (useTitles.ts / incubatorService.createSite) -> authenticated + service_role.
--   - claim_next_incubator_article: chamada só pelo n8n com service_role
--     [OBS-4]. `authenticated` é mantido para permitir um eventual gatilho manual
--     no painel admin; remova a linha se quiser fechar ainda mais.
-- REVOKE de privilégio não é operação destrutiva de dados.
-- -----------------------------------------------------------------------------
REVOKE ALL ON FUNCTION public.claim_next_incubator_article() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.insert_incubator_articles_batch(bigint, text[]) FROM PUBLIC;

DO $perm$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON FUNCTION public.claim_next_incubator_article() FROM anon;
    REVOKE ALL ON FUNCTION public.insert_incubator_articles_batch(bigint, text[]) FROM anon;
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    GRANT EXECUTE ON FUNCTION public.claim_next_incubator_article() TO authenticated;
    GRANT EXECUTE ON FUNCTION public.insert_incubator_articles_batch(bigint, text[]) TO authenticated;
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    GRANT EXECUTE ON FUNCTION public.claim_next_incubator_article() TO service_role;
    GRANT EXECUTE ON FUNCTION public.insert_incubator_articles_batch(bigint, text[]) TO service_role;
  END IF;
END
$perm$;


-- -----------------------------------------------------------------------------
-- 5) Recarrega o cache de schema do PostgREST para as RPCs aparecerem em /rest/v1/
-- -----------------------------------------------------------------------------
NOTIFY pgrst, 'reload schema';


-- #####################################################################
-- ## BLOCO 3/3 — ROI POR PLACEMENT (independente)
-- #####################################################################
-- =============================================================================
-- BLOCO ............: ROI POR PLACEMENT (Display)
-- OBJETOS ..........: public.display_ads_placements   (tabela)
--                     public.display_gam_placements   (tabela)
--                     public.vw_display_roi           (view)
-- ORIGEM ...........: reconstrucao do schema do Supabase do WEBGO.
--                     NAO existe DDL versionado desses objetos em lugar nenhum;
--                     este arquivo foi reconstruido a partir de (a) spec OpenAPI
--                     do PostgREST do WEBGO, (b) amostragem de linhas reais das
--                     duas tabelas e da view, (c) codigo consumidor no repo VOLC.
-- DEPENDENCIAS .....: public.campaigns (colunas id, campaign_id, campaign_name,
--                       advertising_channel_type)  -> VERIFICADO: existe no VOLC
--                     tipo enum public.channel_type -> VERIFICADO: existe no VOLC
--                       (campaigns.advertising_channel_type ja e desse tipo)
--                     gen_random_uuid() (nucleo do PG >= 13)
-- CONSUMIDORES .....: src/hooks/useDisplayROI.ts
--                     src/types/displayROI.ts (contrato DisplayROIRow)
--                     src/components/campaign/DisplayROITable.tsx
--                     src/sql/get_placement_negation_suggestions.sql
--
-- CONTEXTO DE APLICACAO:
--   No VOLC nao ha pipeline de ingestao confirmado alimentando essas tabelas.
--   As tabelas nascem VAZIAS de proposito. A view foi escrita para retornar
--   ZERO LINHAS sem erro nesse cenario (FULL OUTER JOIN de duas tabelas vazias
--   produz 0 linhas; nenhuma agregacao / nenhum HAVING / nenhuma divisao por
--   zero e avaliada). A UI (DisplayROITable) trata array vazio com o estado
--   "Nenhum dado de ROI Display encontrado para este periodo."
--
-- O QUE E OBSERVADO x O QUE E INFERIDO  (detalhado em cada bloco abaixo):
--   OBSERVADO: nomes/ordem/tipos/formatos de todas as colunas das 3 entidades;
--              NOT NULL; DEFAULTs; ausencia de FK; chave de juncao entre as duas
--              tabelas; tipo do JOIN (FULL OUTER); LEFT JOIN com campaigns;
--              formulas de lucro_bruto, roas_pct e status_roi (com limiares).
--   INFERIDO : precisao/escala exatas dos numeric; nomes e existencia dos
--              indices; UNIQUE em (campaign_id, dominio, date); RLS/policies/
--              grants; ausencia de ORDER BY interno na view; se o CASE de
--              status_roi compara o valor bruto ou o arredondado.
--
-- SEGURANCA DO SCRIPT: idempotente e nao destrutivo.
--   Nenhum DROP TABLE / DROP COLUMN / TRUNCATE / DELETE / UPDATE.
--   Pode ser reexecutado quantas vezes for preciso.
--
-- VALIDACAO JA EXECUTADA (PostgreSQL 16 local, descartavel -- nada foi escrito
-- em nenhuma das duas instancias Supabase):
--   1. Script roda limpo do zero e roda de novo sem erro (idempotencia OK).
--   2. Ordem, nomes e tipos das 15 colunas da view batem 1:1 com o spec
--      OpenAPI do WEBGO (inclusive impressions/clicks como integer, nao bigint).
--   3. Com as tabelas vazias: SELECT * FROM vw_display_roi -> 0 linhas, sem erro.
--   4. RECONCILIACAO CONTRA O ORIGINAL: carreguei as 644 linhas reais de
--      display_ads_placements + as 165 de display_gam_placements da fatia
--      campaign_id=23281669601 / date=2026-04-17, rodei esta view e comparei
--      campo a campo com as 686 linhas que a view do WEBGO devolve para a mesma
--      fatia. Resultado: 686/686 linhas, 15/15 colunas, ZERO divergencias.
--   5. src/sql/get_placement_negation_suggestions.sql compila e executa contra
--      esta view (com dados e com a view vazia).
-- =============================================================================


-- =============================================================================
-- 1) TABELA public.display_ads_placements
--    Custo por placement (dominio) vindo do Google Ads.
--
--    OBSERVADO (spec OpenAPI do WEBGO, definitions.display_ads_placements):
--      - required = [id, campaign_id, domain, date]  -> PostgREST lista aqui as
--        colunas NOT NULL (independente de terem DEFAULT). Confirmado cruzando
--        com public.campaigns, cujo required inclui created_at (que tem
--        DEFAULT now()). Logo: as demais colunas sao NULLABLE.
--      - id            uuid,   PK, default gen_random_uuid()
--      - campaign_id   text    (SEM nota <fk/> no spec -> NAO ha FK)
--      - domain        text
--      - tipo          text    default 'WEBSITE'
--      - cost          numeric default 0
--      - conversions   numeric default 0
--      - cost_per_conv numeric default 0
--      - date          date    default CURRENT_DATE
--      - created_at    timestamptz default now()
--    OBSERVADO (linhas reais): campaign_id e o ID numerico da campanha no Google
--      Ads gravado como texto ("23281669601"); domain e o dominio limpo, sem
--      protocolo e sem "www." ("20minutos.es", "mail.google.com"); tipo assume
--      'WEBSITE' e 'GOOGLE_PRODUCTS'; cost/cost_per_conv chegam sempre com 4
--      casas ("0.0000", "128.2500") e conversions com 2 casas ("54.00").
--
--    INFERIDO: a precisao (numero total de digitos) dos numeric. A ESCALA (4 e 2)
--      e observada; a precisao 14 e um teto folgado escolhido por mim.
--    INFERIDO: nao ha CHECK em `tipo` (o spec nao expoe CHECKs; os dois valores
--      vistos convivem sem erro, mas nao consigo provar que nao existe um CHECK).
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.display_ads_placements (
  id            uuid          NOT NULL DEFAULT gen_random_uuid(),
  campaign_id   text          NOT NULL,
  domain        text          NOT NULL,
  tipo          text                   DEFAULT 'WEBSITE',
  cost          numeric(14,4)          DEFAULT 0,
  conversions   numeric(14,2)          DEFAULT 0,
  cost_per_conv numeric(14,4)          DEFAULT 0,
  date          date          NOT NULL DEFAULT CURRENT_DATE,
  created_at    timestamptz            DEFAULT now(),
  CONSTRAINT display_ads_placements_pkey PRIMARY KEY (id)
);


-- =============================================================================
-- 2) TABELA public.display_gam_placements
--    Receita por placement (URL/dominio) vinda do Google Ad Manager.
--
--    OBSERVADO (spec OpenAPI do WEBGO, definitions.display_gam_placements):
--      - required = [id, campaign_id, placement_url, date]
--      - id            uuid, PK, default gen_random_uuid()
--      - campaign_id   text  (SEM nota <fk/> -> NAO ha FK; e bom que nao tenha:
--                             a tabela do WEBGO tem 155.069 linhas com
--                             campaign_id = 'utm' e outras com 'price', lixo de
--                             um parser antigo que quebraria qualquer FK)
--      - placement_url text
--      - revenue_brl   numeric default 0
--      - revenue_usd   numeric default 0
--      - impressions   integer default 0   <- integer, NAO bigint (importante,
--      - clicks        integer default 0      ver secao 4: prova que a view nao
--                                             agrega com SUM)
--      - date          date default CURRENT_DATE
--      - created_at    timestamptz default now()
--    OBSERVADO (linhas reais recentes): campaign_id numerico e placement_url =
--      dominio limpo ("20minutos.es"), no mesmo formato de
--      display_ads_placements.domain -> e isso que permite o JOIN direto.
--      Ha tambem lixo legado (campaign_id='utm' com placement_url
--      'content=23552098018_openapps.com.br'); esse lixo NAO e tratado pela view.
--
--    INFERIDO: precisao dos numeric (escala 4 observada em revenue_brl/usd).
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.display_gam_placements (
  id            uuid          NOT NULL DEFAULT gen_random_uuid(),
  campaign_id   text          NOT NULL,
  placement_url text          NOT NULL,
  revenue_brl   numeric(14,4)          DEFAULT 0,
  revenue_usd   numeric(14,4)          DEFAULT 0,
  impressions   integer                DEFAULT 0,
  clicks        integer                DEFAULT 0,
  date          date          NOT NULL DEFAULT CURRENT_DATE,
  created_at    timestamptz            DEFAULT now(),
  CONSTRAINT display_gam_placements_pkey PRIMARY KEY (id)
);


-- =============================================================================
-- 3) INDICES
--
--    3a) UNIQUE (campaign_id, <dominio>, date)  -- INFERIDO, mas com evidencia forte
--        Evidencia:
--          (i)  Em toda fatia amostrada do WEBGO nao existe UMA duplicata dessa
--               chave. Ex.: campanha 23281669601 em 2026-04-17 -> 644 linhas em
--               display_ads_placements e 644 pares (campaign_id, domain) DISTINTOS;
--               165 linhas em display_gam_placements e 165 pares distintos.
--          (ii) Dentro da MESMA data, os created_at das linhas sao de execucoes
--               diferentes do pipeline (09:02 e 15:01 do dia 17, e 09:05 do dia
--               18, todos para date = 2026-04-17). Isso e a assinatura de um
--               UPSERT (ON CONFLICT DO UPDATE preserva o created_at original e
--               so insere placements novos). Um INSERT puro repetido teria gerado
--               duplicatas; um DELETE+INSERT teria igualado todos os created_at.
--               UPSERT exige um indice UNIQUE nessa chave -> ele existe no WEBGO.
--        RISCO SE EU ESTIVER ERRADO: se o pipeline que vier a alimentar o VOLC
--        fizer INSERT puro, ele vai falhar com 23505 (unique_violation). Nesse
--        caso, e so remover o indice:
--            DROP INDEX IF EXISTS public.ux_display_ads_placements_key;
--            DROP INDEX IF EXISTS public.ux_display_gam_placements_key;
--        (nao removo nada aqui; a instrucao acima e apenas documentacao)
--
--    3b) Indices de leitura (campaign_id, date) e (date)  -- INFERIDO
--        Motivados pelo padrao de acesso real dos consumidores:
--          useDisplayROI.ts  -> .eq('campaign_id', X).gte('date', A).lte('date', B)
--          get_placement_negation_suggestions.sql -> WHERE campaign_id = $1
--                                                    AND date >= CURRENT_DATE-14
--        Nao consigo ler pg_indexes das instancias, entao os NOMES aqui sao meus.
--        Sao inofensivos: indices adicionais nunca mudam resultado, so custo de
--        escrita.
-- =============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS ux_display_ads_placements_key
  ON public.display_ads_placements (campaign_id, domain, date);

CREATE INDEX IF NOT EXISTS ix_display_ads_placements_campaign_date
  ON public.display_ads_placements (campaign_id, date);

CREATE INDEX IF NOT EXISTS ix_display_ads_placements_date
  ON public.display_ads_placements (date);

CREATE UNIQUE INDEX IF NOT EXISTS ux_display_gam_placements_key
  ON public.display_gam_placements (campaign_id, placement_url, date);

CREATE INDEX IF NOT EXISTS ix_display_gam_placements_campaign_date
  ON public.display_gam_placements (campaign_id, date);

CREATE INDEX IF NOT EXISTS ix_display_gam_placements_date
  ON public.display_gam_placements (date);


-- =============================================================================
-- 4) VIEW public.vw_display_roi
--    Cruza custo (Google Ads) x receita (GAM) por placement/canal e data.
--
-- -----------------------------------------------------------------------------
-- 4.1 CHAVE DE JUNCAO -- este era o ponto dificil. EVIDENCIA (tudo OBSERVADO):
-- -----------------------------------------------------------------------------
--  (A) Igualdade CRUA, sem normalizacao nenhuma:
--      display_gam_placements.campaign_id   = display_ads_placements.campaign_id
--      display_gam_placements.placement_url = display_ads_placements.domain
--      display_gam_placements.date          = display_ads_placements.date
--
--      Prova positiva (linha que casa):
--        ads : campaign_id=23281669601, domain='autotest.com.ar',
--              date=2026-04-17, cost=0.0000, conversions=2.00
--        gam : campaign_id=23281669601, placement_url='autotest.com.ar',
--              date=2026-04-17, revenue_brl=1.0500, revenue_usd=0.2064,
--              impressions=10, clicks=3
--        view: canal='autotest.com.ar', investido_brl=0.0000, conversions=2.00,
--              receita_brl=1.0500, receita_usd=0.2064, impressions=10, clicks=3
--        -> os numeros do GAM chegam INTACTOS na view: 1:1, sem soma.
--
--      Prova negativa (descarta qualquer parsing de URL):
--        ads : campaign_id=23552098018, domain='openapps.com.br', 2026-04-15
--        gam : campaign_id='utm',
--              placement_url='content=23552098018_openapps.com.br', 2026-04-15,
--              revenue_brl=5.8400, impressions=114, clicks=39
--        view: canal='openapps.com.br' -> receita_brl=0, impressions=0, clicks=0
--        -> a view NAO extrai o id/dominio de dentro do 'content=...'. Se
--           extraisse, essa linha teria casado. E a linha lixo aparece SEPARADA
--           na view, com campaign_id='utm' e
--           canal='content=23552098018_openapps.com.br'.
--
--  (B) O JOIN e FULL OUTER (nao LEFT). Prova por contagem exata:
--        fatia campaign_id=23281669601 AND date=2026-04-17
--          display_ads_placements ......... 644 linhas
--          display_gam_placements ......... 165 linhas
--          intersecao das chaves .......... 123
--          so no ads ...................... 521
--          so no gam ......................  42
--          |ads UNIAO gam| ................ 686
--          vw_display_roi ................. 686 linhas  <-- BATE EXATO
--        LEFT JOIN daria 644; RIGHT daria 165; INNER daria 123. So FULL OUTER
--        da 686. E a linha 'comedera.com' (que so existe no GAM) aparece na view
--        com investido_brl=0 e conversions=0 -> confirma o lado direito orfao.
--
--  (C) As chaves da view sao COALESCE dos dois lados (consequencia do FULL OUTER):
--        campaign_id = COALESCE(a.campaign_id, g.campaign_id)
--        canal       = COALESCE(a.domain,      g.placement_url)
--        date        = COALESCE(a.date,        g.date)
--      Prova: linhas com campaign_id='utm' / 'price' existem na view e essas
--      strings so existem em display_gam_placements.campaign_id.
--
--  (D) campaigns entra por LEFT JOIN em campaigns.campaign_id (NAO inner).
--      Prova: campaign_id='utm' e campaign_id='price' NAO existem em campaigns,
--      e mesmo assim aparecem na view com
--      campaign_db_id=NULL, campaign_name=NULL, advertising_channel_type=NULL.
--      Se fosse INNER, essas 155k+ linhas sumiriam.
--
--  (E) NAO ha agregacao (nada de GROUP BY / SUM). Provas:
--        - o spec do PostgREST diz vw_display_roi.impressions = "integer".
--          SUM(integer) em PG devolve BIGINT. De fato, a view irma
--          vw_placement_roi_daily expoe impressions como "bigint". Se houvesse
--          SUM aqui, o tipo seria bigint.
--        - os valores da view sao identicos aos da linha unica de origem (4.1 A).
--        - a chave (campaign_id, dominio, date) e unica nas duas tabelas, entao
--          nem haveria o que somar.
--      Quem agrega e o front (useDisplayROI.ts soma por `canal` no cliente).
--
--  (F) NAO ha WHERE nenhum na view. Provas:
--        - linhas com tipo='GOOGLE_PRODUCTS' (domain='mail.google.com')
--          aparecem normalmente -> nao filtra por tipo.
--        - linhas de campanha inexistente ('utm','price') aparecem -> nao filtra
--          por campaigns IS NOT NULL nem por advertising_channel_type='DISPLAY'.
--        - as 644 linhas de ads da fatia testada aparecem todas -> nao filtra por
--          cost > 0 nem por conversions > 0.
--
--  (G) NAO ha ORDER BY dentro da view. -- INFERIDO (evidencia razoavel)
--      Consultas filtradas voltam em ordem nao monotonica em nenhuma coluna.
--      Alem disso os dois consumidores impoem a propria ordenacao
--      (.order('lucro_bruto') no hook; ORDER BY no final da RPC). Omitir ORDER BY
--      e tambem a opcao mais barata em plano de execucao.
--
-- -----------------------------------------------------------------------------
-- 4.2 CONTRATO DE COLUNAS -- ordem e tipos identicos ao spec do WEBGO,
--     e superconjunto do DisplayROIRow de src/types/displayROI.ts:
--        DisplayROIRow exige: campaign_id, canal, date, investido_brl,
--        conversions, receita_brl, receita_usd, impressions, clicks,
--        lucro_bruto, roas_pct, status_roi  -> TODAS presentes.
--        As 3 primeiras colunas (campaign_db_id, campaign_name,
--        advertising_channel_type) sao extras e o front simplesmente ignora
--        (ele faz select('*') e le por nome).
--        get_placement_negation_suggestions.sql exige: canal, date, roas_pct,
--        investido_brl, campaign_id -> TODAS presentes, com os mesmos tipos
--        (canal/text, date/date, roas_pct/numeric, investido_brl/numeric).
--
-- -----------------------------------------------------------------------------
-- 4.3 FORMULAS -- todas OBSERVADAS por reconciliacao numerica em linhas reais:
--        lucro_bruto = receita_brl - investido_brl
--            ex.: 2.5100 - 0.7200 = 1.7900  (a view mostra 1.7900, escala 4,
--                 ou seja SEM ROUND)
--        roas_pct    = ROUND(((receita_brl - investido_brl)
--                             / NULLIF(investido_brl,0)) * 100, 2)
--            ex.: (2.5100-0.7200)/0.7200*100 = 248.6111... -> view: 248.61
--                 (0.7800-0.3600)/0.3600*100 = 116.6666... -> view: 116.67
--            NULLIF confirmado: toda linha com investido_brl = 0 tem
--            roas_pct = NULL (e nao erro / e nao 0).
--            OBS DE NOMENCLATURA: o nome diz "ROAS" mas a formula e ROI
--            (lucro/custo), nao receita/custo. Mantido como esta porque e o que
--            o front espera: useDisplayROI.ts recalcula exatamente
--            ((receita - investido)/investido)*100.
--        status_roi  = CASE roas >= 20 -> 'LUCRATIVO'
--                           roas >=  0 -> 'NEUTRO'
--                           roas <   0 -> 'PREJUIZO'
--                           (sem ELSE -> NULL quando roas e NULL)
--            Limiar 20 fechado por bissecao em dados reais:
--              19.15 / 19.23 / 19.57 / 19.64 -> NEUTRO
--              20.00 / 20.13 / 20.19 / 20.29 -> LUCRATIVO
--                0.00 -> NEUTRO ;  -1.39 / -3.33 / -100.00 -> PREJUIZO
--            E identico ao que useDisplayROI.ts refaz no cliente (>=20, >=0).
--            Ausencia de ELSE confirmada: linhas com investido_brl=0 tem
--            status_roi = NULL na view.
--
--     INFERIDO (unico ponto ambiguo das formulas): se o CASE compara o valor
--     BRUTO ou o ja ARREDONDADO. Escolhi o bruto. So diverge no fio da navalha
--     (ex.: 19.996 -> ROUND=20.00; bruto daria 'NEUTRO', arredondado daria
--     'LUCRATIVO'). Nao encontrei linha real que desempate.
--
-- -----------------------------------------------------------------------------
-- 4.4 COMPORTAMENTO COM TABELAS VAZIAS (requisito desta entrega):
--     FULL OUTER JOIN de duas tabelas vazias -> 0 linhas; o LEFT JOIN com
--     campaigns nao cria linha nenhuma; nao ha agregado sem GROUP BY (que
--     poderia devolver 1 linha de NULLs); nao ha divisao avaliada. Resultado:
--     SELECT * FROM vw_display_roi -> 0 linhas, sem erro. O hook recebe [],
--     hasData=false, e o componente mostra o estado vazio.
--
-- NOTA SOBRE CREATE OR REPLACE VIEW: no VOLC a view nao existe (confirmado:
-- PostgREST responde PGRST205 "Could not find the table 'public.vw_display_roi'").
-- Se em algum ambiente ela ja existir com outra lista/ordem/tipo de colunas, o
-- CREATE OR REPLACE falha (limitacao do PG). Nesse caso e preciso decidir
-- explicitamente por um DROP VIEW -- que este script NAO faz por conta propria.
-- =============================================================================

CREATE OR REPLACE VIEW public.vw_display_roi AS
WITH base AS (
  -- Uniao completa dos dois lados: todo placement que teve CUSTO (Google Ads)
  -- e/ou RECEITA (GAM) naquela campanha/dia vira exatamente uma linha.
  SELECT
    COALESCE(a.campaign_id, g.campaign_id)  AS campaign_id,
    COALESCE(a.domain,      g.placement_url) AS canal,
    COALESCE(a.date,        g.date)          AS date,
    COALESCE(a.cost,        0)               AS investido_brl,
    COALESCE(a.conversions, 0)               AS conversions,
    COALESCE(g.revenue_brl, 0)               AS receita_brl,
    COALESCE(g.revenue_usd, 0)               AS receita_usd,
    COALESCE(g.impressions, 0)               AS impressions,
    COALESCE(g.clicks,      0)               AS clicks
  FROM public.display_ads_placements a
  FULL OUTER JOIN public.display_gam_placements g
    ON  g.campaign_id   = a.campaign_id
    AND g.placement_url = a.domain
    AND g.date          = a.date
),
calc AS (
  -- Lucro e ROI calculados uma unica vez, para o CASE e o ROUND lerem a mesma
  -- expressao. NULLIF protege a divisao quando nao houve investimento.
  SELECT
    b.campaign_id,
    b.canal,
    b.date,
    b.investido_brl,
    b.conversions,
    b.receita_brl,
    b.receita_usd,
    b.impressions,
    b.clicks,
    b.receita_brl - b.investido_brl AS lucro_bruto,
    ((b.receita_brl - b.investido_brl) / NULLIF(b.investido_brl, 0)) * 100 AS roi_bruto
  FROM base b
)
SELECT
  -- Enriquecimento com a campanha. LEFT JOIN: placements de campaign_id que nao
  -- existe em campaigns continuam aparecendo, com estes 3 campos NULL.
  c.id                          AS campaign_db_id,
  c.campaign_name               AS campaign_name,
  c.advertising_channel_type    AS advertising_channel_type,
  k.campaign_id                 AS campaign_id,
  k.canal                       AS canal,
  k.date                        AS date,
  k.investido_brl               AS investido_brl,
  k.conversions                 AS conversions,
  k.receita_brl                 AS receita_brl,
  k.receita_usd                 AS receita_usd,
  k.impressions                 AS impressions,
  k.clicks                      AS clicks,
  k.lucro_bruto                 AS lucro_bruto,
  ROUND(k.roi_bruto, 2)         AS roas_pct,
  CASE
    WHEN k.roi_bruto >= 20 THEN 'LUCRATIVO'
    WHEN k.roi_bruto >=  0 THEN 'NEUTRO'
    WHEN k.roi_bruto <   0 THEN 'PREJUIZO'
    -- sem ELSE: roi_bruto NULL (investido = 0) resulta em status_roi NULL,
    -- exatamente como o WEBGO devolve.
  END::text                     AS status_roi
FROM calc k
LEFT JOIN public.campaigns c
  ON c.campaign_id = k.campaign_id;


-- =============================================================================
-- 5) security_invoker na view  -- INFERIDO / defensivo
--    Nao consigo saber se a view do WEBGO usa security_invoker. Ligo aqui porque
--    e a recomendacao do Supabase (a view passa a respeitar a RLS de quem
--    consulta, em vez de rodar com os direitos do dono). Combinado com as
--    policies da secao 6, o app anon continua lendo normalmente.
--    Envolvido em DO/EXCEPTION porque a opcao so existe no PG >= 15; em versao
--    anterior o script apenas avisa e segue (a view continua valida).
-- =============================================================================

DO $$
BEGIN
  EXECUTE 'ALTER VIEW public.vw_display_roi SET (security_invoker = true)';
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'security_invoker nao aplicado em vw_display_roi (%). Provavel PostgreSQL < 15. A view segue funcional.', SQLERRM;
END
$$;


-- =============================================================================
-- 6) RLS + POLICIES + GRANTS  -- INFERIDO
--    Nao consigo ler pg_policies de nenhuma das duas instancias.
--    Base da decisao (OBSERVADO): o app do VOLC usa APENAS a anon key
--    (src/lib/supabase.ts -> createClient(VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY))
--    e a anon key ja consegue ler public.campaigns no VOLC (HTTP 200 com linhas).
--    Logo, para o ROI Display funcionar, anon precisa de SELECT aqui tambem.
--    Habilito RLS (mais seguro que deixar desligado) com policy de SELECT para
--    anon e authenticated. Escrita fica so para service_role (que ignora RLS).
--
--    SE O ORQUESTRADOR PREFERIR FECHAR MAIS: basta trocar a role da policy de
--    'anon, authenticated' para so 'authenticated' -- mas ai o app, que hoje
--    consulta como anon, passaria a receber 0 linhas (nao erro).
-- =============================================================================

ALTER TABLE public.display_ads_placements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.display_gam_placements ENABLE ROW LEVEL SECURITY;

-- CREATE POLICY nao aceita IF NOT EXISTS; guarda manual via catalogo.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename  = 'display_ads_placements'
      AND policyname = 'display_ads_placements_select'
  ) THEN
    EXECUTE $p$
      CREATE POLICY display_ads_placements_select
        ON public.display_ads_placements
        FOR SELECT
        TO anon, authenticated
        USING (true)
    $p$;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename  = 'display_gam_placements'
      AND policyname = 'display_gam_placements_select'
  ) THEN
    EXECUTE $p$
      CREATE POLICY display_gam_placements_select
        ON public.display_gam_placements
        FOR SELECT
        TO anon, authenticated
        USING (true)
    $p$;
  END IF;
END
$$;

-- GRANTs. Envolvidos em guarda porque as roles do Supabase (anon /
-- authenticated / service_role) podem nao existir num Postgres cru.
DO $$
DECLARE
  r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('GRANT SELECT ON public.display_ads_placements TO %I', r);
      EXECUTE format('GRANT SELECT ON public.display_gam_placements TO %I', r);
      EXECUTE format('GRANT SELECT ON public.vw_display_roi          TO %I', r);
    ELSE
      RAISE NOTICE 'Role % nao existe nesta instancia; GRANT ignorado.', r;
    END IF;
  END LOOP;

  -- Escrita das tabelas base somente para service_role (o pipeline de ingestao).
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    EXECUTE 'GRANT INSERT, UPDATE ON public.display_ads_placements TO service_role';
    EXECUTE 'GRANT INSERT, UPDATE ON public.display_gam_placements TO service_role';
  END IF;
END
$$;


-- =============================================================================
-- 7) DOCUMENTACAO NO CATALOGO
--    ATENCAO: estes COMMENT ON sao ACRESCIMO MEU. O WEBGO nao tem comentario
--    nenhum nesses objetos (o spec OpenAPI de la nao traz `description` alguma
--    nessas tabelas/view, so as notas automaticas de PK). Sao inofensivos, mas
--    fazem o spec do VOLC ficar levemente diferente do spec do WEBGO.
-- =============================================================================

COMMENT ON TABLE public.display_ads_placements IS
  'Custo/conversoes por placement (dominio) do Google Ads, por campanha e dia. Chave logica: (campaign_id, domain, date). DDL reconstruido a partir do Supabase do WEBGO (nao havia DDL versionado).';

COMMENT ON TABLE public.display_gam_placements IS
  'Receita/impressoes/clicks por placement do Google Ad Manager, por campanha e dia. Chave logica: (campaign_id, placement_url, date). DDL reconstruido a partir do Supabase do WEBGO (nao havia DDL versionado).';

COMMENT ON VIEW public.vw_display_roi IS
  'ROI por placement: FULL OUTER JOIN de display_ads_placements x display_gam_placements por (campaign_id, dominio, date), enriquecido com campaigns via LEFT JOIN. roas_pct e na verdade ROI% = (receita-investido)/investido*100 (NULL quando investido=0). status_roi: >=20 LUCRATIVO, >=0 NEUTRO, <0 PREJUIZO, NULL quando roas_pct e NULL.';


-- =============================================================================
-- 8) RECARREGA O CACHE DE SCHEMA DO POSTGREST
--    Sem isso o PostgREST continua respondendo PGRST205 ate reiniciar sozinho.
--    Guardado porque o canal 'pgrst' so existe em instancias Supabase/PostgREST.
-- =============================================================================

DO $$
BEGIN
  NOTIFY pgrst, 'reload schema';
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'NOTIFY pgrst nao executado (%).', SQLERRM;
END
$$;

-- =============================================================================
-- FIM
-- =============================================================================
