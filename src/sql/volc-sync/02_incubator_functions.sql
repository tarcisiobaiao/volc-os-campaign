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
