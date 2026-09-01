-- =============================================================================
-- v13_01 — Cofre de Ativos: control plane persistido do patrimonio digital
-- P03-T10 (referencias de credencial), P03-T06 (tela ligada a dado real),
-- P03-T02/P12-T02 (onboarding da pagina) e P03-T04 (engines como ativo).
-- ARQUIVO. NAO APLICADO em producao por esta missao.
-- =============================================================================
-- APLICAR COMO: postgres (supabase_admin tambem serve; a guarda aceita os dois)
--
-- ORDEM: independente das series v8, v9 e v12. Nao cria, altera nem le nenhum
--        objeto delas. Nao depende de nenhuma ter sido aplicada.
-- ROLLBACK: supabase/migrations/v13_99_cofre_de_ativos_rollback.sql
--
-- -----------------------------------------------------------------------------
-- A FRONTEIRA QUE ESTE ARQUIVO EXISTE PARA DESENHAR NO BANCO
-- -----------------------------------------------------------------------------
-- O 1Password guarda o VALOR do segredo. Este schema guarda REFERENCIA, dono,
-- finalidade, validade, estado e auditoria — e nada mais. A separacao esta em
-- docs/architecture/ADR-1PASSWORD-ADSPOWER-E-RECUPERACAO-AGENTICA.md, decisao 1.
--
-- Documentar a fronteira nao a implementa. O que a implementa aqui sao tres
-- mecanismos, em camadas, e cada um sozinho seria insuficiente:
--
--   1) FORMA. `cofre_credencial_referencia.localizador` tem CHECK de FORMA por
--      provider: `op://cofre/item/campo` e aceito, `Tr0ub4dor&3` nao. Uma senha
--      bruta nao cabe na coluna — nao por politica, por gramatica.
--
--   2) CHAVE. Todo jsonb que entra passa por `cofre_recusa_chave_sensivel`,
--      que percorre o documento INTEIRO (aninhado, dentro de array) e compara a
--      chave NORMALIZADA (minuscula, sem separadores) contra uma lista fechada.
--      `accessToken`, `ACCESS-TOKEN`, `access token` e `access_token` colapsam
--      todos em `accesstoken` e caem no mesmo ramo. Alias por grafia deixa de
--      ser um caminho.
--
--   3) SUPERFICIE. Nenhuma funcao deste arquivo devolve `localizador`. Nem a de
--      leitura, nem a de escrita, nem o recibo. A postura de credencial e
--      publicada por `cofre_postura_credencial`, que projeta provider, nome
--      logico, finalidade, estado e frescor — e omite o endereco. O locator sai
--      do banco por operacao administrativa direta, fora desta API, com o papel
--      `postgres`, e isso e proposital.
--
-- ⚠️ O QUE ISTO **NAO** PROTEGE, dito sem rodeio: quem tem a senha do papel
-- `postgres` le a coluna. A promessa aqui e que nem a API, nem o navegador, nem
-- o grafo, nem o recibo, nem `service_role` a alcancam — e que um payload com
-- valor bruto e RECUSADO em vez de aceito e escondido.
--
-- -----------------------------------------------------------------------------
-- AS QUATRO REGRAS QUE ATRAVESSAM O SCHEMA
-- -----------------------------------------------------------------------------
-- A. AUSENCIA E NULL, NUNCA ZERO, e "nao verificado" NUNCA e "verificado".
--    `formatos`, `skins`, `nichos` e `vozes` de um engine sao NULL quando o
--    manifesto nao os declara, e tem CHECK `> 0` quando existem: zero seria uma
--    contagem observada, e nao foi observada nada. O mesmo vale para o eixo de
--    verificacao, que tem SEIS valores distintos — `unverified`, `partial`,
--    `verified`, `expired`, `failed` e `blocked` — porque achatar "falhou" e
--    "nao tentei" e como o painel passa a inventar confianca.
--
-- B. NENHUMA VERIFICACAO SEM CARIMBO. As CHECKs `..._sem_carimbo` recusam a
--    linha que afirmaria um resultado sem o instante em que foi observado.
--    Verificacao sem data e indistinguivel de verificacao de um ano atras.
--
-- C. APOSENTADORIA E REVERSIVEL; NAO HA DELETE. Nenhuma tabela concede DELETE a
--    ninguem. Ativo sai de operacao com `aposentado_em` + motivo, relacao se
--    desfaz com `desfeito_em` + motivo, e os dois voltam. A trilha e append-only
--    porque o que aconteceu nao deixa de ter acontecido.
--
-- D. TODA ESCRITA E GOVERNADA. As nove tabelas tem ALL revogado de TODOS os
--    papeis do Data API — inclusive `service_role`. O backend nao faz INSERT:
--    ele chama funcao `SECURITY DEFINER` com allowlist de campo, blocklist de
--    chave, idempotencia e recibo. Nao ha caminho de escrita generica.
--
-- -----------------------------------------------------------------------------
-- SEGURANCA — os defaults deste banco sao INSEGUROS (achado H, 2026-08-24)
-- -----------------------------------------------------------------------------
-- `pg_default_acl` do schema public concede `arwdDxt` a anon, authenticated e
-- service_role em TODA TABELA NOVA, e EXECUTE em TODA FUNCAO NOVA. Uma tabela
-- criada aqui NASCE escrivel pelo navegador, e `REVOKE ... FROM PUBLIC` nao
-- resolve: os grants do default ACL sao NOMINAIS.
--
-- Por isso a secao 20 revoga NOMINALMENTE de cada papel, liga RLS com FORCE e
-- zero policies (negacao por ausencia), e so entao concede EXECUTE das funcoes
-- governadas a `service_role` — e so a ele.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. GUARDAS — abortar cedo e com mensagem, em vez de tarde e com erro cru
-- -----------------------------------------------------------------------------
DO $guarda$
DECLARE
  ja_existem text;
  faltando   text;
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION
      'v13_01 deve rodar como postgres ou supabase_admin; papel atual: %',
      current_user;
  END IF;

  -- PG15 e o piso: `security_invoker` em VIEW so existe a partir do 15, e a
  -- secao 19 depende dele para que a view de leitura NAO passe por cima da RLS
  -- das tabelas que ela junta. Producao medida: supabase/postgres:15.8.1.085.
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION
      'v13_01 exige PostgreSQL 15 ou maior (security_invoker em VIEW); aqui: %',
      current_setting('server_version');
  END IF;

  SELECT string_agg(t, ', ' ORDER BY t) INTO ja_existem
    FROM unnest(ARRAY[
      'cofre_gaveta', 'cofre_tipo', 'cofre_ativo', 'cofre_engine_perfil',
      'cofre_ativo_revisao', 'cofre_relacao', 'cofre_credencial_referencia',
      'cofre_verificacao', 'cofre_operacao'
    ]) AS t
   WHERE to_regclass('public.' || t) IS NOT NULL;

  IF ja_existem IS NOT NULL THEN
    RAISE EXCEPTION
      'v13_01 ja parece aplicada: % ja existe(m). Rode o v13_99 antes de reaplicar.',
      ja_existem;
  END IF;

  -- Os REVOKE nominais da secao 20 falham com erro cru se o papel nao existir.
  -- Num Supabase real os tres existem; num cluster descartavel, nao — e por
  -- isso o harness de prova os cria antes de aplicar.
  SELECT string_agg(r, ', ' ORDER BY r) INTO faltando
    FROM unnest(ARRAY['anon', 'authenticated', 'service_role']) AS r
   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);

  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION
      'v13_01 exige os papeis do Supabase; ausente(s): %. Sem eles o REVOKE nominal nao acontece e a tabela nasce aberta.',
      faltando;
  END IF;

  RAISE NOTICE 'v13_01: guardas ok (papel=%, versao=%)',
    current_user, current_setting('server_version');
END
$guarda$;


-- -----------------------------------------------------------------------------
-- 1. AJUDANTES IMUTAVEIS — porque CHECK nao aceita subconsulta
-- -----------------------------------------------------------------------------
-- `NOT EXISTS (SELECT ... FROM unnest(...))` seria a forma natural de dizer
-- "nenhum elemento em branco", e o Postgres a recusa dentro de CHECK. A
-- alternativa nao e afrouxar a regra: e nomea-la numa funcao IMMUTABLE, que a
-- CHECK pode chamar. O efeito colateral e bom — a regra passa a ter nome, e o
-- erro passa a citar esse nome em vez de despejar a expressao inteira.
CREATE OR REPLACE FUNCTION public.cofre_texto_util(p_valor text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = ''
AS $funcao$
  SELECT p_valor IS NOT NULL AND length(btrim(p_valor)) > 0;
$funcao$;

COMMENT ON FUNCTION public.cofre_texto_util(text) IS
  'Verdadeiro quando o texto existe e nao e apenas espaco. Ausencia e NULL, nao string vazia.';

CREATE OR REPLACE FUNCTION public.cofre_lista_util(p_valores text[], p_min int, p_max int)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = ''
AS $funcao$
  SELECT p_valores IS NOT NULL
     AND cardinality(p_valores) BETWEEN p_min AND p_max
     AND cardinality(p_valores) = (
           SELECT count(*) FROM unnest(p_valores) AS v
            WHERE v IS NOT NULL AND length(btrim(v)) > 0
         );
$funcao$;

COMMENT ON FUNCTION public.cofre_lista_util(text[], int, int) IS
  'Verdadeiro quando a lista tem tamanho no intervalo e nenhum elemento nulo ou em branco.';

-- A GRAMATICA DA REFERENCIA, em UM lugar so — e o motivo de ela nao ser escrita
-- direto na CHECK.
--
-- ⚠️ DEFEITO MEDIDO NESTA MISSAO (01/09/2026), e a razao desta funcao existir:
-- quando a CHECK recusa a linha, o Postgres anexa
-- `DETAIL: Failing row contains (…)` com a LINHA INTEIRA — inclusive o valor do
-- `localizador` que acabou de ser recusado. Ou seja, tentar guardar uma senha no
-- campo errado FAZIA A SENHA APARECER no log do servidor e no corpo do erro do
-- PostgREST. A recusa vazava o que a recusa existia para impedir.
--
-- Com a gramatica nomeada, `cofre_referenciar_credencial` a consulta ANTES do
-- INSERT e levanta uma mensagem que cita o provider e a forma esperada, nunca o
-- valor. A CHECK continua na tabela como ultima linha de defesa — para escrita
-- direta, que nao deveria existir — mas o caminho normal nunca chega nela.
CREATE OR REPLACE FUNCTION public.cofre_localizador_valido(p_provider text, p_localizador text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = ''
AS $funcao$
  SELECT p_localizador IS NOT NULL
     AND length(p_localizador) <= 300
     AND CASE p_provider
           -- Secret reference do 1Password: op://<cofre>/<item>/[secao/]<campo>.
           -- Espaco tem de vir percent-encoded (%20) — a forma segura, e a que
           -- nao quebra quando a referencia viaja por shell ou por JSON.
           --
           -- Query params NAO sao aceitos de proposito. `?attribute=otp` aponta
           -- para um TOTP, e o ADR e explicito: MFA nao entra no Cofre nem por
           -- referencia. Recusar aqui e mais barato do que explicar depois por
           -- que o inventario sabe onde mora o segundo fator.
           WHEN '1password' THEN
             p_localizador ~ '^op://[A-Za-z0-9._%~-]{1,64}/[A-Za-z0-9._%~-]{1,128}(/[A-Za-z0-9._%~-]{1,64}){1,2}$'
           WHEN 'bitwarden'   THEN p_localizador ~ '^bw://[0-9a-fA-F-]{16,64}(/[A-Za-z0-9._-]{1,64})?$'
           WHEN 'vaultwarden' THEN p_localizador ~ '^bwv://[0-9a-fA-F-]{16,64}(/[A-Za-z0-9._-]{1,64})?$'
           WHEN 'passbolt'    THEN p_localizador ~ '^passbolt://[0-9a-fA-F-]{16,64}$'
           WHEN 'infisical'   THEN p_localizador ~ '^infisical://[A-Za-z0-9._/-]{3,200}$'
           ELSE false
         END;
$funcao$;

COMMENT ON FUNCTION public.cofre_localizador_valido(text, text) IS
  'Gramatica da secret reference por provider. Consultada ANTES do INSERT para que a recusa nao ecoe o valor.';

CREATE OR REPLACE FUNCTION public.cofre_forma_esperada(p_provider text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = ''
AS $funcao$
  -- A mensagem de erro que o operador ve. Ela ensina a forma correta sem nunca
  -- repetir o que foi digitado.
  SELECT CASE p_provider
           WHEN '1password'   THEN 'op://<cofre>/<item>/[secao/]<campo>, com espacos em %20 e sem query string'
           WHEN 'bitwarden'   THEN 'bw://<uuid-do-item>[/<campo>]'
           WHEN 'vaultwarden' THEN 'bwv://<uuid-do-item>[/<campo>]'
           WHEN 'passbolt'    THEN 'passbolt://<uuid-do-recurso>'
           WHEN 'infisical'   THEN 'infisical://<caminho/do/segredo>'
           ELSE 'provider desconhecido'
         END;
$funcao$;

-- A NORMALIZACAO que faz alias por grafia deixar de ser um caminho de fuga.
--
-- `accessToken`, `ACCESS-TOKEN`, `Access Token` e `access_token` sao a MESMA
-- intencao escrita de quatro jeitos. Comparar a chave crua contra uma lista
-- pegaria uma e deixaria tres passar — e a lista pareceria completa. Colapsar
-- para minuscula sem separador reduz as quatro a `accesstoken`, e a lista passa
-- a valer para todas as grafias que ainda nao foram inventadas.
CREATE OR REPLACE FUNCTION public.cofre_chave_normalizada(p_chave text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = ''
AS $funcao$
  SELECT lower(regexp_replace(coalesce(p_chave, ''), '[^a-zA-Z0-9]', '', 'g'));
$funcao$;

COMMENT ON FUNCTION public.cofre_chave_normalizada(text) IS
  'Minuscula sem separadores: colapsa accessToken/ACCESS-TOKEN/access_token em accesstoken.';


-- -----------------------------------------------------------------------------
-- 2. cofre_gaveta — as sete gavetas operacionais, como DADO e nao como CHECK
-- -----------------------------------------------------------------------------
-- O contrato publico (src/features/asset-vault/contract.ts) diz que "um tipo
-- pertence a exatamente uma gaveta". Escrever isso como CHECK duplicaria a
-- regra em dois lugares que divergem no primeiro tipo novo. Aqui a regra e
-- ESTRUTURAL: `cofre_ativo` referencia o PAR (kind, cluster), e o par so existe
-- se `cofre_tipo` o declarar. Classificar a mesma conta de duas formas
-- contraditorias deixa de ser possivel — nao e recusado, e inexprimivel.
CREATE TABLE public.cofre_gaveta (
  cluster     text        PRIMARY KEY,
  rotulo      text        NOT NULL,
  descricao   text        NOT NULL,
  ordem       smallint    NOT NULL,

  CONSTRAINT cofre_gaveta_cluster_forma  CHECK (cluster ~ '^[a-z][a-z_]{2,40}$'),
  CONSTRAINT cofre_gaveta_ordem_positiva CHECK (ordem > 0),
  CONSTRAINT cofre_gaveta_ordem_unica    UNIQUE (ordem)
);

COMMENT ON TABLE public.cofre_gaveta IS
  'As sete gavetas operacionais do Cofre. Espelha ASSET_CLUSTERS do contrato publico.';

INSERT INTO public.cofre_gaveta (cluster, rotulo, descricao, ordem) VALUES
  ('social_presence',     'Presencas sociais',        'Perfis, paginas e canais onde a marca publica e constroi audiencia.', 1),
  ('paid_media',          'Midia paga',               'Gerenciadores e contas que compram midia nas plataformas.',           2),
  ('web_properties',      'Sites e dominios',         'Dominios, sites, WordPress, paginas e propriedades monetizadas.',     3),
  ('communities',         'Comunidades e mensagens',  'WhatsApp, Telegram e sistemas que sustentam relacionamento e retencao.', 4),
  ('creative_production', 'Producao criativa',        'Engines que produzem imagem, video, audio e variacoes criativas.',    5),
  ('automation',          'Automacoes e integracoes', 'Workflows, integracoes e rotinas que movem dados e tarefas.',         6),
  ('infrastructure',      'Infraestrutura e dados',   'Bancos, servidores, repositorios e servicos-base da operacao.',       7);


-- -----------------------------------------------------------------------------
-- 3. cofre_tipo — os 27 tipos, cada um em exatamente uma gaveta
-- -----------------------------------------------------------------------------
CREATE TABLE public.cofre_tipo (
  kind      text     PRIMARY KEY,
  cluster   text     NOT NULL REFERENCES public.cofre_gaveta (cluster),
  rotulo    text     NOT NULL,

  CONSTRAINT cofre_tipo_kind_forma CHECK (kind ~ '^[a-z][a-z0-9_]{2,60}$'),
  -- Alvo do FK composto de `cofre_ativo`. Sem este UNIQUE o par nao e
  -- referenciavel, e a integridade da gaveta voltaria a ser um CHECK duplicado.
  CONSTRAINT cofre_tipo_par_unico    UNIQUE (kind, cluster)
);

COMMENT ON TABLE public.cofre_tipo IS
  'Catalogo de tipos de ativo. Espelha ASSET_KINDS e KIND_CLUSTER do contrato publico.';

INSERT INTO public.cofre_tipo (kind, cluster, rotulo) VALUES
  ('facebook_profile',        'social_presence',     'Perfil do Facebook'),
  ('facebook_page',           'social_presence',     'Pagina do Facebook'),
  ('instagram_profile',       'social_presence',     'Perfil do Instagram'),
  ('youtube_channel',         'social_presence',     'Canal do YouTube'),
  ('pinterest_account',       'social_presence',     'Conta do Pinterest'),
  ('tiktok_account',          'social_presence',     'Conta do TikTok'),
  ('linkedin_page',           'social_presence',     'Pagina do LinkedIn'),
  ('x_account',               'social_presence',     'Conta do X'),
  ('meta_business_portfolio', 'paid_media',          'Business Portfolio Meta'),
  ('meta_ad_account',         'paid_media',          'Conta de anuncios Meta'),
  ('google_ads_manager',      'paid_media',          'MCC Google Ads'),
  ('google_ads_account',      'paid_media',          'Conta Google Ads'),
  ('domain',                  'web_properties',      'Dominio'),
  ('website',                 'web_properties',      'Site'),
  ('wordpress_site',          'web_properties',      'Site WordPress'),
  ('landing_page',            'web_properties',      'Landing page'),
  ('monetization_property',   'web_properties',      'Propriedade monetizada'),
  ('whatsapp_account',        'communities',         'Conta WhatsApp'),
  ('whatsapp_community',      'communities',         'Comunidade WhatsApp'),
  ('telegram_channel',        'communities',         'Canal Telegram'),
  ('messaging_hub',           'communities',         'Hub de mensagens'),
  ('creative_engine',         'creative_production', 'Engine criativo'),
  ('automation_workflow',     'automation',          'Workflow de automacao'),
  ('integration',             'automation',          'Integracao'),
  ('database_service',        'infrastructure',      'Banco e API de dados'),
  ('server',                  'infrastructure',      'Servidor'),
  ('repository',              'infrastructure',      'Repositorio'),
  -- Tipo novo desta missao: o perfil de navegador isolado do AdsPower (P03-T07).
  -- Ele entra em `automation` porque e rotina operacional, nao presenca social:
  -- o perfil executa, a pagina publica. Confundi-los faria o Cofre responder
  -- "temos duas paginas" quando ha uma pagina e um perfil que a abre.
  ('browser_profile',         'automation',          'Perfil de navegador isolado');


-- -----------------------------------------------------------------------------
-- 4. cofre_ativo — a identidade do patrimonio
-- -----------------------------------------------------------------------------
-- `ativo_id` e text e DECLARADO, nao sorteado, pelo mesmo motivo de
-- `trafego_campanha.volc_campaign_id`: ele ja existe no contrato publico e nas
-- fixtures como `asset:<familia>:<slug>`, e trocar por uuid quebraria a unica
-- ponte estavel entre o retrato editorial e a linha persistida.
CREATE TABLE public.cofre_ativo (
  ativo_id           text        PRIMARY KEY,
  schema_version     smallint    NOT NULL DEFAULT 1,

  kind               text        NOT NULL,
  cluster            text        NOT NULL,

  nome               text        NOT NULL,
  plataforma         text        NOT NULL,
  estado             text        NOT NULL,
  criticidade        text        NOT NULL,
  resumo             text        NOT NULL,

  dono_nome          text        NOT NULL,
  dono_custodia      text        NOT NULL,

  projeto            text        NULL,
  vertical           text        NULL,

  -- Identificador JA SANITIZADO para exibicao (ex.: '•••-•••-1692'). Nunca o ID
  -- cru de plataforma quando ele for sensivel, e nunca segredo.
  display_id         text        NULL,
  url_publica        text        NULL,
  -- Rotulo de localizacao NAO SENSIVEL (ex.: 'Drive compartilhado VOLC'). O
  -- caminho absoluto do disco do operador contem o e-mail dele; ele nao entra
  -- aqui e nao entra em resposta HTTP nenhuma.
  localizacao_rotulo text        NULL,

  capacidades        text[]      NOT NULL,
  tags               text[]      NOT NULL DEFAULT '{}',
  proxima_acao       text        NOT NULL,

  revisao_atual      integer     NOT NULL DEFAULT 1,

  criado_em          timestamptz NOT NULL DEFAULT now(),
  atualizado_em      timestamptz NOT NULL DEFAULT now(),

  -- Aposentadoria REVERSIVEL. Nao ha DELETE em lugar nenhum deste dominio.
  aposentado_em      timestamptz NULL,
  aposentado_motivo  text        NULL,

  CONSTRAINT cofre_ativo_gaveta_coerente
    FOREIGN KEY (kind, cluster) REFERENCES public.cofre_tipo (kind, cluster),

  CONSTRAINT cofre_ativo_schema_conhecido CHECK (schema_version = 1),
  CONSTRAINT cofre_ativo_id_forma         CHECK (ativo_id ~ '^[a-z][a-z0-9:_-]{2,179}$'),
  CONSTRAINT cofre_ativo_nome_util        CHECK (length(btrim(nome))       BETWEEN 2  AND 160),
  CONSTRAINT cofre_ativo_plataforma_util  CHECK (length(btrim(plataforma)) BETWEEN 1  AND 240),
  CONSTRAINT cofre_ativo_resumo_util      CHECK (length(btrim(resumo))     BETWEEN 10 AND 800),
  CONSTRAINT cofre_ativo_dono_util        CHECK (length(btrim(dono_nome))  BETWEEN 1  AND 240),
  CONSTRAINT cofre_ativo_acao_util        CHECK (length(btrim(proxima_acao)) BETWEEN 10 AND 800),

  CONSTRAINT cofre_ativo_estado_conhecido CHECK (estado IN
    ('declared','verified','ready','active','restricted','inactive','retired')),
  CONSTRAINT cofre_ativo_criticidade_conhecida CHECK (criticidade IN
    ('low','medium','high','critical')),
  CONSTRAINT cofre_ativo_custodia_conhecida CHECK (dono_custodia IN
    ('declared','verified','unassigned')),

  -- Ausencia conhecida e NULL. String vazia e "presente e inutil": ela passa em
  -- NOT NULL, aparece na tela como espaco em branco e nao distingue "nao tem"
  -- de "nao sei" (E-02/E-10 da v9_01).
  CONSTRAINT cofre_ativo_projeto_nao_vazio    CHECK (projeto    IS NULL OR length(btrim(projeto))    > 0),
  CONSTRAINT cofre_ativo_vertical_nao_vazia   CHECK (vertical   IS NULL OR length(btrim(vertical))   > 0),
  CONSTRAINT cofre_ativo_display_id_sanitizado CHECK (
    display_id IS NULL OR (length(btrim(display_id)) BETWEEN 1 AND 80 AND display_id !~ '[[:space:]]{2,}')),
  CONSTRAINT cofre_ativo_localizacao_nao_vazia CHECK (
    localizacao_rotulo IS NULL OR length(btrim(localizacao_rotulo)) BETWEEN 1 AND 240),

  -- Somente HTTP(S), como no contrato publico. `file://`, `javascript:` e
  -- caminho de disco sao recusados aqui e nao so na tela.
  --
  -- ⚠️ O TETO E `+`, E NAO `{3,2000}`, POR DEFEITO MEDIDO EM 01/09/2026.
  -- O limite de contagem de repeticao do regex do Postgres e 255: `{3,256}` ja
  -- levanta `invalid repetition count(s)` (SQLSTATE 2201B). Como CHECK
  -- curto-circuita em NULL, a migration aplicava limpa e a expressao invalida
  -- so era avaliada no PRIMEIRO ativo com endereco publico — ou seja, todo site,
  -- toda pagina e todo perfil. O comprimento e limitado por `length()`, que nao
  -- tem esse teto, e a forma por `+`, que nao tem contagem.
  CONSTRAINT cofre_ativo_url_http CHECK (
    url_publica IS NULL OR (
      length(url_publica) BETWEEN 11 AND 2000
      AND url_publica ~* '^https?://[^[:space:]]+$')),

  CONSTRAINT cofre_ativo_capacidades_util CHECK (public.cofre_lista_util(capacidades, 1, 40)),
  CONSTRAINT cofre_ativo_tags_util         CHECK (public.cofre_lista_util(tags, 0, 30)),

  CONSTRAINT cofre_ativo_revisao_positiva CHECK (revisao_atual > 0),

  -- Aposentadoria sempre carrega o porque. Metade dela e uma linha que ninguem
  -- consegue explicar depois.
  CONSTRAINT cofre_ativo_aposentadoria_completa CHECK (
    (aposentado_em IS NULL AND aposentado_motivo IS NULL)
    OR (aposentado_em IS NOT NULL AND length(btrim(coalesce(aposentado_motivo,''))) >= 10)),
  CONSTRAINT cofre_ativo_aposentado_tem_estado CHECK (
    aposentado_em IS NULL OR estado = 'retired')
);

COMMENT ON TABLE public.cofre_ativo IS
  'Identidade do patrimonio digital. Zero segredo, zero localizador de cofre.';
COMMENT ON COLUMN public.cofre_ativo.display_id IS
  'Identificador JA sanitizado para exibicao. Nunca segredo, nunca ID cru sensivel.';
COMMENT ON COLUMN public.cofre_ativo.localizacao_rotulo IS
  'Rotulo NAO sensivel de localizacao. Caminho absoluto do operador nao entra aqui.';

CREATE INDEX cofre_ativo_cluster_ix   ON public.cofre_ativo (cluster);
CREATE INDEX cofre_ativo_kind_ix      ON public.cofre_ativo (kind);
CREATE INDEX cofre_ativo_estado_ix    ON public.cofre_ativo (estado);
CREATE INDEX cofre_ativo_projeto_ix   ON public.cofre_ativo (projeto) WHERE projeto IS NOT NULL;
CREATE INDEX cofre_ativo_ativos_ix    ON public.cofre_ativo (cluster, nome) WHERE aposentado_em IS NULL;


-- -----------------------------------------------------------------------------
-- 5. cofre_engine_perfil — o que so um engine criativo tem
-- -----------------------------------------------------------------------------
-- Extensao 1:1 de `cofre_ativo` para `kind = 'creative_engine'`. Os campos
-- moram aqui e nao em `cofre_ativo` por duas razoes: doze colunas nulas em toda
-- pagina do Facebook seriam ruido permanente, e — mais importante — a CHECK
-- "contagem e NULL ou POSITIVA" so faz sentido no contexto de um manifesto de
-- engine. Diluida na tabela geral, ela viraria decoracao.
--
-- ⚠️ A REGRA QUE ESTE BLOCO EXISTE PARA IMPOR: ausencia nunca vira capacidade.
-- `docs/creative-engines/motores-de-imagem.json` e `motores-de-video.json` tem
-- SCHEMAS DIFERENTES: o de imagem traz `capabilities`/`limitations`/`maturity`,
-- o de video traz `formats`/`skins`/`niches`/`voices`/`limits`/`state`. Nenhum
-- dos dois traz tudo. O importador preenche o que existe e deixa NULL o que
-- nao existe — e a CHECK `> 0` garante que ninguem "arredonde" um NULL para
-- zero na tentativa de fazer a coluna parecer preenchida.
CREATE TABLE public.cofre_engine_perfil (
  ativo_id               text        PRIMARY KEY
                                     REFERENCES public.cofre_ativo (ativo_id),

  modalidade             text        NOT NULL,
  estado_operacional     text        NOT NULL,

  versao_contrato        text        NULL,

  formatos               integer     NULL,
  skins                  integer     NULL,
  nichos                 integer     NULL,
  vozes                  integer     NULL,

  -- Procedencia da linha: qual documento versionado a sustenta, e com qual
  -- impressao digital. Sem isso, "o engine tem 17 formatos" e uma afirmacao sem
  -- dono, e o proximo a duvidar nao tem onde conferir.
  manifesto_fonte        text        NOT NULL,
  manifesto_sha256       text        NULL,
  fonte_fingerprint      text        NULL,

  capacidades_observadas text[]      NOT NULL,
  limitacoes             text[]      NOT NULL,
  requisitos             text[]      NOT NULL DEFAULT '{}',
  destinos_compativeis   text[]      NOT NULL DEFAULT '{}',

  verificado_em          date        NULL,

  criado_em              timestamptz NOT NULL DEFAULT now(),
  atualizado_em          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT cofre_engine_modalidade_conhecida CHECK (modalidade IN
    ('imagem','video','audio','misto')),

  -- Cinco estados, e a distancia entre eles e o ponto. `catalogado` diz que o
  -- manifesto existe; `externo_parcial` diz que o runtime roda FORA do VOLC O.S.
  -- e nao foi provado integralmente daqui; `integrado` exigiria adapter, job e
  -- prova — nenhum engine esta la hoje, e o importador nao pode inventa-lo.
  CONSTRAINT cofre_engine_estado_conhecido CHECK (estado_operacional IN
    ('catalogado','externo_parcial','integrado','somente_referencia','aposentado')),

  -- Ausencia e NULL, nunca zero: zero formatos seria uma contagem OBSERVADA, e
  -- um manifesto que nao declara formato nao observou zero — nao observou nada.
  CONSTRAINT cofre_engine_formatos_positivos CHECK (formatos IS NULL OR formatos > 0),
  CONSTRAINT cofre_engine_skins_positivas    CHECK (skins    IS NULL OR skins    > 0),
  CONSTRAINT cofre_engine_nichos_positivos   CHECK (nichos   IS NULL OR nichos   > 0),
  CONSTRAINT cofre_engine_vozes_positivas    CHECK (vozes    IS NULL OR vozes    > 0),

  CONSTRAINT cofre_engine_manifesto_util CHECK (public.cofre_texto_util(manifesto_fonte)),
  CONSTRAINT cofre_engine_versao_nao_vazia CHECK (
    versao_contrato IS NULL OR public.cofre_texto_util(versao_contrato)),
  CONSTRAINT cofre_engine_sha_forma CHECK (
    manifesto_sha256 IS NULL OR manifesto_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT cofre_engine_fingerprint_forma CHECK (
    fonte_fingerprint IS NULL OR fonte_fingerprint ~ '^[0-9a-f]{64}$'),

  CONSTRAINT cofre_engine_capacidades_util CHECK (public.cofre_lista_util(capacidades_observadas, 0, 80)),
  CONSTRAINT cofre_engine_limitacoes_util  CHECK (public.cofre_lista_util(limitacoes,             0, 80)),
  CONSTRAINT cofre_engine_requisitos_util  CHECK (public.cofre_lista_util(requisitos,             0, 40)),
  CONSTRAINT cofre_engine_destinos_util    CHECK (public.cofre_lista_util(destinos_compativeis,   0, 60))
);

COMMENT ON TABLE public.cofre_engine_perfil IS
  'Perfil tecnico de engine criativo. NULL = o manifesto nao declara; nunca zero por conveniencia.';


-- -----------------------------------------------------------------------------
-- 6. cofre_ativo_revisao — versionamento append-only
-- -----------------------------------------------------------------------------
-- Toda mutacao governada grava aqui o retrato COMPLETO do ativo depois da
-- mudanca, com autor e motivo. Nao e log: e a unica forma de responder "como
-- essa linha estava antes de alguem aposenta-la?" sem restaurar backup.
--
-- ⚠️ `snapshot` NAO e entrada do usuario. Ele e construido por
-- `cofre_snapshot_ativo()` a partir das colunas tipadas, dentro da mesma
-- transacao. Ninguem passa jsonb livre para ca — e o gatilho da secao 12 ainda
-- assim o inspeciona, porque defesa que depende de "ninguem faria isso" nao e
-- defesa.
CREATE TABLE public.cofre_ativo_revisao (
  revisao_id     bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ativo_id       text        NOT NULL REFERENCES public.cofre_ativo (ativo_id),
  revisao        integer     NOT NULL,

  operacao       text        NOT NULL,
  snapshot       jsonb       NOT NULL,
  motivo         text        NOT NULL,

  autor_sub      uuid        NOT NULL,
  autor_email    text        NOT NULL,

  ocorrido_em    timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT cofre_revisao_unica UNIQUE (ativo_id, revisao),
  CONSTRAINT cofre_revisao_positiva CHECK (revisao > 0),
  CONSTRAINT cofre_revisao_operacao_conhecida CHECK (operacao IN
    ('cadastro','revisao','relacao_criada','relacao_desfeita','aposentadoria',
     'reativacao','verificacao','credencial_referenciada','importacao_engine')),
  CONSTRAINT cofre_revisao_motivo_util CHECK (length(btrim(motivo)) BETWEEN 5 AND 800),
  CONSTRAINT cofre_revisao_email_util  CHECK (public.cofre_texto_util(autor_email)),
  CONSTRAINT cofre_revisao_snapshot_objeto CHECK (jsonb_typeof(snapshot) = 'object')
);

COMMENT ON TABLE public.cofre_ativo_revisao IS
  'Historico append-only do ativo. Snapshot construido pelo banco, nunca recebido pronto.';

CREATE INDEX cofre_revisao_ativo_ix    ON public.cofre_ativo_revisao (ativo_id, revisao DESC);
CREATE INDEX cofre_revisao_ocorrido_ix ON public.cofre_ativo_revisao (ocorrido_em DESC);


-- -----------------------------------------------------------------------------
-- 7. cofre_relacao — as ligacoes, com integridade e sem apagamento
-- -----------------------------------------------------------------------------
-- Duas formas de destino, e a diferenca importa:
--
--   `destino_id`      -> outro ATIVO do Cofre. FK de verdade: a relacao nao
--                        sobrevive a um ativo que nunca existiu.
--   `destino_externo` -> um alvo que NAO e ativo (projeto, capacidade, conceito).
--                        Texto livre com forma, porque o Cofre nao e dono deles.
--
-- Exatamente um dos dois. Aceitar os dois faria a mesma aresta ter duas pontas
-- diferentes; aceitar nenhum criaria aresta sem destino.
CREATE TABLE public.cofre_relacao (
  relacao_id       bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

  origem_id        text        NOT NULL REFERENCES public.cofre_ativo (ativo_id),
  tipo             text        NOT NULL,
  destino_id       text        NULL     REFERENCES public.cofre_ativo (ativo_id),
  destino_externo  text        NULL,
  destino_rotulo   text        NOT NULL,

  estado           text        NOT NULL,

  declarada_por    text        NOT NULL,
  criado_em        timestamptz NOT NULL DEFAULT now(),

  desfeito_em      timestamptz NULL,
  desfeito_motivo  text        NULL,

  CONSTRAINT cofre_relacao_tipo_conhecido CHECK (tipo IN
    ('belongs_to','managed_by','publishes_to','authenticates_through',
     'spends_from','monetizes','depends_on','produces_for')),
  CONSTRAINT cofre_relacao_estado_conhecido CHECK (estado IN ('declared','verified')),

  CONSTRAINT cofre_relacao_um_destino CHECK (
    (destino_id IS NOT NULL AND destino_externo IS NULL)
    OR (destino_id IS NULL AND destino_externo IS NOT NULL)),
  CONSTRAINT cofre_relacao_externo_forma CHECK (
    destino_externo IS NULL OR destino_externo ~ '^[a-z][a-z0-9:_-]{2,179}$'),
  CONSTRAINT cofre_relacao_rotulo_util   CHECK (length(btrim(destino_rotulo)) BETWEEN 1 AND 240),
  CONSTRAINT cofre_relacao_declarante_util CHECK (public.cofre_texto_util(declarada_por)),

  -- Um ativo que depende de si mesmo e um ciclo de um no: ele nao descreve
  -- nada e quebra qualquer travessia de grafo que confie na aresta.
  CONSTRAINT cofre_relacao_sem_laco CHECK (destino_id IS NULL OR destino_id <> origem_id),

  CONSTRAINT cofre_relacao_desfeita_completa CHECK (
    (desfeito_em IS NULL AND desfeito_motivo IS NULL)
    OR (desfeito_em IS NOT NULL AND length(btrim(coalesce(desfeito_motivo,''))) >= 5))
);

COMMENT ON TABLE public.cofre_relacao IS
  'Relacoes entre ativos. Desfazer e marcar desfeito_em; nao ha DELETE.';

-- Uma relacao ATIVA por (origem, tipo, destino). Desfeitas nao competem: a
-- mesma aresta pode ser criada, desfeita e recriada, e a trilha guarda as tres.
CREATE UNIQUE INDEX cofre_relacao_ativa_unica
  ON public.cofre_relacao (origem_id, tipo, coalesce(destino_id, destino_externo))
  WHERE desfeito_em IS NULL;

CREATE INDEX cofre_relacao_origem_ix  ON public.cofre_relacao (origem_id)  WHERE desfeito_em IS NULL;
CREATE INDEX cofre_relacao_destino_ix ON public.cofre_relacao (destino_id) WHERE destino_id IS NOT NULL AND desfeito_em IS NULL;


-- -----------------------------------------------------------------------------
-- 8. cofre_credencial_referencia — a fronteira, escrita como gramatica
-- -----------------------------------------------------------------------------
-- Esta e a tabela que o ADR descreve e que ate agora nao existia. Ela guarda
-- ONDE o segredo esta, nunca O QUE ele e.
--
-- `localizador` tem CHECK de FORMA por provider. Para o 1Password a forma e a
-- secret reference documentada — `op://<cofre>/<item>/[secao/]<campo>`. O efeito
-- pratico e que uma senha, um token ou uma chave PEM NAO CABEM na coluna: eles
-- nao sao referencias mal formatadas, sao textos que a gramatica nao gera. Uma
-- politica que diz "nao coloque senha aqui" depende de todo mundo lembrar; uma
-- CHECK de forma nao depende de ninguem.
--
-- ⚠️ Esta tabela nao aparece em NENHUMA view, e NENHUMA funcao deste arquivo
-- devolve `localizador` — nem para `service_role`. A postura sai por
-- `cofre_postura_credencial`, que projeta provider, nome logico, finalidade,
-- estado e frescor. Quem precisar do endereco o le com o papel `postgres`, fora
-- desta API, e essa assimetria e o desenho, nao uma lacuna.
CREATE TABLE public.cofre_credencial_referencia (
  referencia_id      bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ativo_id           text        NOT NULL REFERENCES public.cofre_ativo (ativo_id),

  provider           text        NOT NULL,
  -- Nome LOGICO da variavel (ADSPOWER_API_KEY), nao o valor dela. A CHECK de
  -- forma recusa qualquer coisa que nao pareca um identificador de ambiente —
  -- inclusive um valor colado por engano, que quase nunca e MAIUSCULA_COM_UNDERSCORE.
  nome_logico        text        NOT NULL,
  localizador        text        NOT NULL,

  finalidade         text        NOT NULL,
  owner_nome         text        NOT NULL,

  estado             text        NOT NULL,
  valido_ate         date        NULL,

  verificacao_estado text        NOT NULL DEFAULT 'unverified',
  verificado_em      timestamptz NULL,

  criado_em          timestamptz NOT NULL DEFAULT now(),
  atualizado_em      timestamptz NOT NULL DEFAULT now(),
  aposentado_em      timestamptz NULL,
  aposentado_motivo  text        NULL,

  CONSTRAINT cofre_credencial_provider_conhecido CHECK (provider IN
    ('1password','bitwarden','vaultwarden','passbolt','infisical')),

  CONSTRAINT cofre_credencial_nome_logico_forma CHECK (
    nome_logico ~ '^[A-Z][A-Z0-9_]{1,63}$'),

  -- A GRAMATICA DA REFERENCIA. Por provider, porque cada cofre tem a sua e uma
  -- forma generica aceitaria as tres primeiras coisas que alguem colasse.
  -- Ultima linha de defesa, para escrita direta que nao deveria existir. O
  -- caminho normal valida ANTES do INSERT (ver cofre_localizador_valido), porque
  -- a violacao de CHECK anexa `DETAIL: Failing row contains (…)` com o valor
  -- recusado — e um erro que ecoa a senha recusada a publica no log.
  CONSTRAINT cofre_credencial_localizador_opaco
    CHECK (public.cofre_localizador_valido(provider, localizador)),

  CONSTRAINT cofre_credencial_estado_conhecido CHECK (estado IN
    ('not_required','not_registered','referenced','review_due','retired')),

  -- Seis valores, e nenhum deles e sinonimo de outro. `failed` e uma tentativa
  -- que aconteceu e deu errado; `blocked` e o cofre trancado, que nao e falha da
  -- credencial; `unverified` e "nunca tentei". Colapsar os tres num booleano e
  -- como o painel passa a dizer "acesso ok" sobre um cofre que ninguem abriu.
  CONSTRAINT cofre_credencial_verificacao_conhecida CHECK (verificacao_estado IN
    ('unverified','partial','verified','expired','failed','blocked')),

  -- NENHUMA AFIRMACAO DE VERIFICACAO SEM CARIMBO. Dizer `verified` sem instante
  -- e indistinguivel de dizer `verified` sobre uma prova de um ano atras.
  CONSTRAINT cofre_credencial_verificacao_sem_carimbo CHECK (
    verificacao_estado = 'unverified' OR verificado_em IS NOT NULL),

  CONSTRAINT cofre_credencial_finalidade_util CHECK (length(btrim(finalidade)) BETWEEN 5 AND 500),
  CONSTRAINT cofre_credencial_owner_util      CHECK (public.cofre_texto_util(owner_nome)),

  CONSTRAINT cofre_credencial_aposentadoria_completa CHECK (
    (aposentado_em IS NULL AND aposentado_motivo IS NULL)
    OR (aposentado_em IS NOT NULL AND length(btrim(coalesce(aposentado_motivo,''))) >= 5))
);

COMMENT ON TABLE public.cofre_credencial_referencia IS
  'Referencia OPACA a um item de cofre externo. Guarda endereco, nunca valor. Nenhuma funcao publica devolve localizador.';
COMMENT ON COLUMN public.cofre_credencial_referencia.localizador IS
  'Secret reference do provider (ex.: op://cofre/item/campo). CHECK de forma impede armazenar valor bruto.';

-- Uma referencia ATIVA por (ativo, nome logico). O mesmo ativo pode ter
-- ADSPOWER_API_KEY e FACEBOOK_PAGE_TOKEN; nao pode ter duas ADSPOWER_API_KEY
-- vivas apontando para lugares diferentes — e assim que um broker escolhe a
-- errada sem ninguem perceber.
CREATE UNIQUE INDEX cofre_credencial_ativa_unica
  ON public.cofre_credencial_referencia (ativo_id, nome_logico)
  WHERE aposentado_em IS NULL;

CREATE INDEX cofre_credencial_ativo_ix ON public.cofre_credencial_referencia (ativo_id);


-- -----------------------------------------------------------------------------
-- 9. cofre_verificacao — recibos append-only de prova
-- -----------------------------------------------------------------------------
-- O que distingue "achamos que a pagina e nossa" de "conferimos a pagina em 29
-- de agosto pelo Business Portfolio". Cada linha traz metodo, procedencia e o
-- instante da observacao. Nao ha UPDATE: uma prova errada e corrigida por uma
-- prova nova, com o motivo dizendo por que a anterior nao valia.
CREATE TABLE public.cofre_verificacao (
  verificacao_id  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ativo_id        text        NOT NULL REFERENCES public.cofre_ativo (ativo_id),

  alvo            text        NOT NULL,
  resultado       text        NOT NULL,
  metodo          text        NOT NULL,
  procedencia     text        NOT NULL,
  evidencia       text        NOT NULL,

  observado_em    timestamptz NOT NULL,
  proximo_ato     text        NULL,
  revisar_em      date        NULL,

  autor_sub       uuid        NOT NULL,
  autor_email     text        NOT NULL,
  registrado_em   timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT cofre_verificacao_alvo_conhecido CHECK (alvo IN ('ativo','credencial','relacao','engine')),
  CONSTRAINT cofre_verificacao_resultado_conhecido CHECK (resultado IN
    ('unverified','partial','verified','expired','failed','blocked')),
  CONSTRAINT cofre_verificacao_procedencia_conhecida CHECK (procedencia IN
    ('owner_declaration','live_observation','repository_inventory','provider_record')),
  CONSTRAINT cofre_verificacao_metodo_util     CHECK (length(btrim(metodo))    BETWEEN 3  AND 240),
  CONSTRAINT cofre_verificacao_evidencia_util  CHECK (length(btrim(evidencia)) BETWEEN 10 AND 1000),
  CONSTRAINT cofre_verificacao_proximo_util    CHECK (
    proximo_ato IS NULL OR length(btrim(proximo_ato)) BETWEEN 5 AND 800),
  -- Recibo NUNCA e datado no futuro: uma observacao que ainda nao aconteceu nao
  -- e observacao. A folga de um minuto absorve relogio de container fora de sincronia.
  CONSTRAINT cofre_verificacao_nao_futura CHECK (observado_em <= now() + interval '1 minute')
);

COMMENT ON TABLE public.cofre_verificacao IS
  'Recibos append-only de verificacao. Sem carimbo nao ha prova; sem procedencia nao ha origem.';

CREATE INDEX cofre_verificacao_ativo_ix     ON public.cofre_verificacao (ativo_id, observado_em DESC);
CREATE INDEX cofre_verificacao_resultado_ix ON public.cofre_verificacao (resultado);


-- -----------------------------------------------------------------------------
-- 10. cofre_operacao — idempotencia e auditoria, append-only
-- -----------------------------------------------------------------------------
-- A semantica e a que evita os dois defeitos classicos de retry:
--
--   mesma chave + MESMA entrada  -> devolve o recibo guardado (replay).
--   mesma chave + OUTRA entrada  -> ERRO 'cofre_idempotencia_divergente'.
--
-- O segundo ramo e o que quase sempre falta. Sem ele, um cliente que reusa a
-- chave por engano sobrescreve silenciosamente uma operacao diferente, e as
-- duas passam a ter o mesmo recibo — que e pior do que falhar.
CREATE TABLE public.cofre_operacao (
  operacao_id        bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

  chave_idempotencia text        NOT NULL,
  rota               text        NOT NULL,
  entrada_hash       text        NOT NULL,
  resultado          jsonb       NOT NULL,

  autor_sub          uuid        NOT NULL,
  autor_email        text        NOT NULL,
  criado_em          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT cofre_operacao_chave_unica UNIQUE (chave_idempotencia),
  CONSTRAINT cofre_operacao_chave_forma CHECK (chave_idempotencia ~ '^[A-Za-z0-9._:-]{8,120}$'),
  CONSTRAINT cofre_operacao_rota_forma  CHECK (rota ~ '^[a-z][a-z0-9_.]{2,80}$'),
  CONSTRAINT cofre_operacao_hash_forma  CHECK (entrada_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT cofre_operacao_resultado_objeto CHECK (jsonb_typeof(resultado) = 'object')
);

COMMENT ON TABLE public.cofre_operacao IS
  'Trilha append-only de operacoes governadas, com chave de idempotencia e recibo sanitizado.';

CREATE INDEX cofre_operacao_criado_ix ON public.cofre_operacao (criado_em DESC);
CREATE INDEX cofre_operacao_autor_ix  ON public.cofre_operacao (autor_sub, criado_em DESC);


-- -----------------------------------------------------------------------------
-- 11. AS DUAS RECUSAS — chave sensivel e campo desconhecido
-- -----------------------------------------------------------------------------
-- Elas respondem a perguntas diferentes, e ter so uma deixa metade do buraco:
--
--   `cofre_recusa_chave_sensivel`     -> "esse documento contem um campo que
--                                        NUNCA pode existir aqui?" Percorre
--                                        objeto, array e aninhamento inteiros.
--   `cofre_recusa_campo_desconhecido` -> "esse documento contem um campo que eu
--                                        nao sei o que e?" Allowlist no topo.
--
-- Sem a primeira, `{"meta":{"credentials":{"access_token":"..."}}}` entraria por
-- estar dentro de um campo permitido. Sem a segunda, um campo novo entraria por
-- nao estar na blocklist — e a blocklist so cresce depois do vazamento.
CREATE OR REPLACE FUNCTION public.cofre_chave_sensivel(p_chave text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = ''
AS $funcao$
  -- A comparacao e sobre a chave NORMALIZADA, entao esta lista cobre todas as
  -- grafias de cada nome. `credential` (singular) esta AUSENTE de proposito: o
  -- contrato publico usa `credential` para a POSTURA — provider, estado, nota —
  -- e proibi-lo quebraria o retrato que ja existe sem esconder segredo nenhum.
  -- `credentials` (plural), `credentiallocator` e `vaultitemid` continuam banidos.
  SELECT public.cofre_chave_normalizada(p_chave) = ANY (ARRAY[
    'password','senha','passwd','pwd','passphrase','senhamestra','masterpassword',
    'secret','segredo','clientsecret','secretkey','chavesecreta','appsecret',
    'token','accesstoken','refreshtoken','idtoken','bearertoken','sessiontoken',
    'apikey','chaveapi','apisecret','xapikey',
    'privatekey','chaveprivada','sshkey','pem','privatepem','certificatekey',
    'totp','otp','otpsecret','mfa','mfasecret','twofactor','doisfatores',
    'recoverycode','codigorecuperacao','backupcode','codigobackup',
    'seedphrase','mnemonic','frasesemente',
    'cookie','cookies','setcookie','sessionid','sessao',
    'credentials','credenciais','credentiallocator','localizador','locator',
    'vaultitemid','secretreference','referenciasecreta','opuri','opref',
    'dotenv','envfile','environmentfile','authorization','authheader'
  ]);
$funcao$;

COMMENT ON FUNCTION public.cofre_chave_sensivel(text) IS
  'Verdadeiro quando a chave normalizada esta na lista fechada de nomes que nunca entram no Cofre.';

CREATE OR REPLACE FUNCTION public.cofre_recusa_chave_sensivel(p_doc jsonb, p_caminho text DEFAULT 'payload')
RETURNS void
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
SET search_path = ''
AS $funcao$
DECLARE
  chave  text;
  valor  jsonb;
  item   jsonb;
  indice int := 0;
BEGIN
  IF p_doc IS NULL THEN
    RETURN;
  END IF;

  IF jsonb_typeof(p_doc) = 'array' THEN
    -- Array e o esconderijo obvio: `{"extras":[{"password":"x"}]}` passaria por
    -- qualquer varredura que so olhasse chaves de objeto no primeiro nivel.
    FOR item IN SELECT * FROM jsonb_array_elements(p_doc) LOOP
      PERFORM public.cofre_recusa_chave_sensivel(item, p_caminho || '[' || indice || ']');
      indice := indice + 1;
    END LOOP;
    RETURN;
  END IF;

  IF jsonb_typeof(p_doc) <> 'object' THEN
    RETURN;
  END IF;

  FOR chave, valor IN SELECT * FROM jsonb_each(p_doc) LOOP
    IF public.cofre_chave_sensivel(chave) THEN
      -- A mensagem cita a CHAVE e o CAMINHO, nunca o valor. Um erro que ecoa o
      -- segredo recusado o publica no log de quem o recusou.
      RAISE EXCEPTION
        'campo proibido no Cofre: %.% — este schema guarda referencia, nunca valor de credencial',
        p_caminho, chave
        USING ERRCODE = 'restrict_violation';
    END IF;
    PERFORM public.cofre_recusa_chave_sensivel(valor, p_caminho || '.' || chave);
  END LOOP;
END
$funcao$;

COMMENT ON FUNCTION public.cofre_recusa_chave_sensivel(jsonb, text) IS
  'Percorre o jsonb inteiro (objeto, array, aninhamento) e levanta na primeira chave sensivel. Nunca ecoa valor.';

CREATE OR REPLACE FUNCTION public.cofre_recusa_campo_desconhecido(
  p_doc        jsonb,
  p_permitidos text[],
  p_contexto   text
)
RETURNS void
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
SET search_path = ''
AS $funcao$
DECLARE
  desconhecidos text;
BEGIN
  IF p_doc IS NULL OR jsonb_typeof(p_doc) <> 'object' THEN
    RAISE EXCEPTION '% exige um objeto JSON', p_contexto
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  SELECT string_agg(k, ', ' ORDER BY k) INTO desconhecidos
    FROM jsonb_object_keys(p_doc) AS k
   WHERE NOT (k = ANY (p_permitidos));

  IF desconhecidos IS NOT NULL THEN
    RAISE EXCEPTION
      '% recebeu campo(s) que este contrato nao conhece: %',
      p_contexto, desconhecidos
      USING ERRCODE = 'invalid_parameter_value';
  END IF;
END
$funcao$;

COMMENT ON FUNCTION public.cofre_recusa_campo_desconhecido(jsonb, text[], text) IS
  'Allowlist de campos no topo do payload. Campo novo e recusado, nao ignorado.';

-- Formatos de credencial sao RECONHECIVEIS, e reconhece-los nao e adivinhar
-- entropia. `-----BEGIN` abre chave PEM; `eyJ` seguido de base64url longo e o
-- cabecalho de um JWT; `op://` num campo de prosa e uma referencia colada onde
-- nao devia. Nenhum dos tres aparece por acidente numa frase operacional.
--
-- ⚠️ Isto NAO e um detector de segredo, e nao deve ser lido como um. Uma senha
-- curta passa por aqui — e e por isso que a defesa real e a CHECK de forma do
-- `localizador` e a lista de chaves, nao esta funcao.
CREATE OR REPLACE FUNCTION public.cofre_sem_material_de_credencial(p_texto text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = ''
AS $funcao$
  SELECT p_texto IS NULL
      OR (p_texto !~ '-----BEGIN [A-Z ]*PRIVATE KEY'
      AND p_texto !~ 'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}'
      AND p_texto !~ '\mop://[A-Za-z0-9._%~-]+/[A-Za-z0-9._%~-]+/'
      AND p_texto !~ '\m(sk|pk|ghp|gho|xox[baprs])[-_][A-Za-z0-9]{16,}');
$funcao$;

COMMENT ON FUNCTION public.cofre_sem_material_de_credencial(text) IS
  'Recusa FORMATOS reconheciveis de credencial (PEM, JWT, op://, prefixos de token). Nao e detector de entropia.';


-- Aplicada aos campos de prosa que uma pessoa preenche a mao — que sao
-- exatamente onde um copiar-colar apressado deposita um token.
ALTER TABLE public.cofre_ativo
  ADD CONSTRAINT cofre_ativo_prosa_limpa CHECK (
    public.cofre_sem_material_de_credencial(resumo)
    AND public.cofre_sem_material_de_credencial(proxima_acao)
    AND public.cofre_sem_material_de_credencial(display_id)
    AND public.cofre_sem_material_de_credencial(localizacao_rotulo));

ALTER TABLE public.cofre_credencial_referencia
  ADD CONSTRAINT cofre_credencial_prosa_limpa CHECK (
    public.cofre_sem_material_de_credencial(finalidade));

ALTER TABLE public.cofre_verificacao
  ADD CONSTRAINT cofre_verificacao_prosa_limpa CHECK (
    public.cofre_sem_material_de_credencial(evidencia)
    AND public.cofre_sem_material_de_credencial(metodo)
    AND public.cofre_sem_material_de_credencial(proximo_ato));

ALTER TABLE public.cofre_ativo_revisao
  ADD CONSTRAINT cofre_revisao_prosa_limpa CHECK (
    public.cofre_sem_material_de_credencial(motivo));


-- -----------------------------------------------------------------------------
-- 12. APPEND-ONLY e guarda de jsonb — o que aconteceu nao deixa de ter acontecido
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.cofre_append_only()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $funcao$
BEGIN
  RAISE EXCEPTION
    '%.% e append-only: % recusado. Corrija com um registro novo, que preserva o anterior.',
    TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'restrict_violation';
END
$funcao$;

CREATE TRIGGER cofre_revisao_append_only
  BEFORE UPDATE OR DELETE ON public.cofre_ativo_revisao
  FOR EACH ROW EXECUTE FUNCTION public.cofre_append_only();

CREATE TRIGGER cofre_verificacao_append_only
  BEFORE UPDATE OR DELETE ON public.cofre_verificacao
  FOR EACH ROW EXECUTE FUNCTION public.cofre_append_only();

CREATE TRIGGER cofre_operacao_append_only
  BEFORE UPDATE OR DELETE ON public.cofre_operacao
  FOR EACH ROW EXECUTE FUNCTION public.cofre_append_only();

-- Defesa em profundidade sobre os dois jsonb do dominio. As funcoes governadas
-- ja constroem esses documentos a partir de colunas tipadas — mas uma defesa que
-- depende de "ninguem escreveria direto na tabela" nao e defesa, e o gatilho
-- continua valendo se alguem, um dia, escrever.
CREATE OR REPLACE FUNCTION public.cofre_jsonb_sem_segredo()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $funcao$
BEGIN
  IF TG_TABLE_NAME = 'cofre_ativo_revisao' THEN
    PERFORM public.cofre_recusa_chave_sensivel(NEW.snapshot, 'snapshot');
  ELSE
    PERFORM public.cofre_recusa_chave_sensivel(NEW.resultado, 'resultado');
  END IF;
  RETURN NEW;
END
$funcao$;

CREATE TRIGGER cofre_revisao_snapshot_sem_segredo
  BEFORE INSERT ON public.cofre_ativo_revisao
  FOR EACH ROW EXECUTE FUNCTION public.cofre_jsonb_sem_segredo();

CREATE TRIGGER cofre_operacao_recibo_sem_segredo
  BEFORE INSERT ON public.cofre_operacao
  FOR EACH ROW EXECUTE FUNCTION public.cofre_jsonb_sem_segredo();

-- `atualizado_em` derivado, e nao confiado a quem escreve. Um campo de frescor
-- que o chamador preenche e um campo de frescor que o chamador esquece.
CREATE OR REPLACE FUNCTION public.cofre_carimba_atualizacao()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $funcao$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END
$funcao$;

CREATE TRIGGER cofre_ativo_carimba
  BEFORE UPDATE ON public.cofre_ativo
  FOR EACH ROW EXECUTE FUNCTION public.cofre_carimba_atualizacao();

CREATE TRIGGER cofre_engine_carimba
  BEFORE UPDATE ON public.cofre_engine_perfil
  FOR EACH ROW EXECUTE FUNCTION public.cofre_carimba_atualizacao();

CREATE TRIGGER cofre_credencial_carimba
  BEFORE UPDATE ON public.cofre_credencial_referencia
  FOR EACH ROW EXECUTE FUNCTION public.cofre_carimba_atualizacao();


-- -----------------------------------------------------------------------------
-- 13. cofre_snapshot_ativo — o retrato, montado pelo banco
-- -----------------------------------------------------------------------------
-- Ele existe para que `cofre_ativo_revisao.snapshot` NAO seja entrada do
-- chamador. Um snapshot recebido pronto e um campo jsonb livre com outro nome:
-- aceitaria qualquer chave, e a unica defesa restante seria a blocklist. Montado
-- aqui, a partir das colunas tipadas, ele so pode conter o que o schema tem.
CREATE OR REPLACE FUNCTION public.cofre_snapshot_ativo(p_ativo_id text)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $funcao$
  SELECT jsonb_strip_nulls(jsonb_build_object(
    'ativo_id',           a.ativo_id,
    'schema_version',     a.schema_version,
    'kind',               a.kind,
    'cluster',            a.cluster,
    'nome',               a.nome,
    'plataforma',         a.plataforma,
    'estado',             a.estado,
    'criticidade',        a.criticidade,
    'resumo',             a.resumo,
    'dono_nome',          a.dono_nome,
    'dono_custodia',      a.dono_custodia,
    'projeto',            a.projeto,
    'vertical',           a.vertical,
    'display_id',         a.display_id,
    'url_publica',        a.url_publica,
    'localizacao_rotulo', a.localizacao_rotulo,
    'capacidades',        to_jsonb(a.capacidades),
    'tags',               to_jsonb(a.tags),
    'proxima_acao',       a.proxima_acao,
    'revisao_atual',      a.revisao_atual,
    'aposentado_em',      a.aposentado_em,
    'aposentado_motivo',  a.aposentado_motivo,
    'engine', (
      SELECT jsonb_strip_nulls(jsonb_build_object(
        'modalidade',             e.modalidade,
        'estado_operacional',     e.estado_operacional,
        'versao_contrato',        e.versao_contrato,
        'formatos',               e.formatos,
        'skins',                  e.skins,
        'nichos',                 e.nichos,
        'vozes',                  e.vozes,
        'manifesto_fonte',        e.manifesto_fonte,
        'manifesto_sha256',       e.manifesto_sha256,
        'fonte_fingerprint',      e.fonte_fingerprint,
        'capacidades_observadas', to_jsonb(e.capacidades_observadas),
        'limitacoes',             to_jsonb(e.limitacoes),
        'requisitos',             to_jsonb(e.requisitos),
        'destinos_compativeis',   to_jsonb(e.destinos_compativeis),
        'verificado_em',          e.verificado_em))
        FROM public.cofre_engine_perfil e WHERE e.ativo_id = a.ativo_id),
    'relacoes', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
               'tipo',    r.tipo,
               'destino', coalesce(r.destino_id, r.destino_externo),
               'rotulo',  r.destino_rotulo,
               'estado',  r.estado) ORDER BY r.relacao_id), '[]'::jsonb)
        FROM public.cofre_relacao r
       WHERE r.origem_id = a.ativo_id AND r.desfeito_em IS NULL)
  ))
  FROM public.cofre_ativo a
 WHERE a.ativo_id = p_ativo_id;
$funcao$;

COMMENT ON FUNCTION public.cofre_snapshot_ativo(text) IS
  'Retrato do ativo montado a partir das colunas tipadas. Nunca inclui credencial nem localizador.';


-- -----------------------------------------------------------------------------
-- 14. cofre_idempotencia — replay honesto, divergencia ruidosa
-- -----------------------------------------------------------------------------
-- Devolve o recibo guardado quando a chave se repete COM a mesma entrada.
-- Levanta quando a chave se repete com entrada DIFERENTE. Devolve NULL quando a
-- chave e nova — e ai a funcao chamadora executa e registra.
CREATE OR REPLACE FUNCTION public.cofre_idempotencia(
  p_chave        text,
  p_rota         text,
  p_entrada_hash text
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  anterior public.cofre_operacao%ROWTYPE;
BEGIN
  SELECT * INTO anterior
    FROM public.cofre_operacao
   WHERE chave_idempotencia = p_chave;

  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  IF anterior.rota <> p_rota OR anterior.entrada_hash <> p_entrada_hash THEN
    -- O ramo que quase sempre falta. Sobrescrever aqui faria duas operacoes
    -- diferentes compartilharem um recibo, e o retry silencioso viraria perda
    -- de dado com aparencia de sucesso.
    RAISE EXCEPTION
      'chave de idempotencia % ja foi usada por outra operacao (rota %); use uma chave nova',
      p_chave, anterior.rota
      USING ERRCODE = 'unique_violation';
  END IF;

  RETURN anterior.resultado || jsonb_build_object('idempotente', true);
END
$funcao$;

COMMENT ON FUNCTION public.cofre_idempotencia(text, text, text) IS
  'NULL quando a chave e nova; recibo guardado no replay; excecao quando a mesma chave traz outra entrada.';

CREATE OR REPLACE FUNCTION public.cofre_registra_operacao(
  p_chave        text,
  p_rota         text,
  p_entrada_hash text,
  p_resultado    jsonb,
  p_autor_sub    uuid,
  p_autor_email  text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
BEGIN
  INSERT INTO public.cofre_operacao
    (chave_idempotencia, rota, entrada_hash, resultado, autor_sub, autor_email)
  VALUES
    (p_chave, p_rota, p_entrada_hash, p_resultado, p_autor_sub, p_autor_email);
  RETURN p_resultado || jsonb_build_object('idempotente', false);
END
$funcao$;

COMMENT ON FUNCTION public.cofre_registra_operacao(text, text, text, jsonb, uuid, text) IS
  'Grava o recibo da operacao e devolve-o marcado como primeira execucao.';


-- -----------------------------------------------------------------------------
-- 15. AS FUNCOES GOVERNADAS DE ESCRITA
-- -----------------------------------------------------------------------------
-- Toda escrita do dominio entra por aqui. Nenhum papel do Data API tem INSERT,
-- UPDATE ou DELETE nas tabelas (secao 20), entao este e o unico caminho — nao
-- por convencao, por privilegio.
--
-- Cada funcao segue a MESMA disciplina, na mesma ordem:
--
--   1. recusa campo desconhecido (allowlist do topo)
--   2. recusa chave sensivel (varredura recursiva)
--   3. deriva o hash da entrada — o CHAMADOR NAO O ENVIA, e por isso nao pode
--      mentir sobre ele: dois payloads diferentes nao conseguem compartilhar
--      recibo nem por engano nem de proposito
--   4. consulta idempotencia (replay devolve o recibo guardado)
--   5. executa
--   6. grava revisao com o snapshot montado pelo banco
--   7. grava e devolve o recibo
--
-- ⚠️ Nenhuma delas devolve `localizador`. Nem no recibo, nem no snapshot, nem
-- na mensagem de erro.

CREATE OR REPLACE FUNCTION public.cofre_entrada_hash(p_rota text, p_payload jsonb)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = ''
AS $funcao$
  -- `jsonb::text` e canonico: o Postgres ordena as chaves e descarta duplicatas
  -- na entrada. Dois payloads logicamente iguais escritos em ordens diferentes
  -- produzem o MESMO hash, que e exatamente o que um retry precisa.
  SELECT encode(sha256(convert_to(p_rota || '|' || p_payload::text, 'UTF8')), 'hex');
$funcao$;

COMMENT ON FUNCTION public.cofre_entrada_hash(text, jsonb) IS
  'Hash canonico da entrada, derivado no banco. O chamador nao o envia e portanto nao pode falsifica-lo.';

CREATE OR REPLACE FUNCTION public.cofre_cadastrar_ativo(
  p_payload     jsonb,
  p_chave       text,
  p_autor_sub   uuid,
  p_autor_email text,
  p_motivo      text DEFAULT 'cadastro inicial pelo Cofre de Ativos'
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  guardado jsonb;
  hash     text;
  novo_id  text;
  recibo   jsonb;
BEGIN
  PERFORM public.cofre_recusa_campo_desconhecido(p_payload, ARRAY[
    'ativo_id','kind','cluster','nome','plataforma','estado','criticidade','resumo',
    'dono_nome','dono_custodia','projeto','vertical','display_id','url_publica',
    'localizacao_rotulo','capacidades','tags','proxima_acao','engine'
  ], 'cofre_cadastrar_ativo');
  PERFORM public.cofre_recusa_chave_sensivel(p_payload, 'ativo');

  hash := public.cofre_entrada_hash('cofre.cadastrar_ativo', p_payload);
  guardado := public.cofre_idempotencia(p_chave, 'cofre.cadastrar_ativo', hash);
  IF guardado IS NOT NULL THEN
    RETURN guardado;
  END IF;

  INSERT INTO public.cofre_ativo (
    ativo_id, kind, cluster, nome, plataforma, estado, criticidade, resumo,
    dono_nome, dono_custodia, projeto, vertical, display_id, url_publica,
    localizacao_rotulo, capacidades, tags, proxima_acao, revisao_atual)
  SELECT
    p_payload->>'ativo_id', p_payload->>'kind', p_payload->>'cluster',
    p_payload->>'nome', p_payload->>'plataforma', p_payload->>'estado',
    p_payload->>'criticidade', p_payload->>'resumo',
    p_payload->>'dono_nome', p_payload->>'dono_custodia',
    p_payload->>'projeto', p_payload->>'vertical',
    p_payload->>'display_id', p_payload->>'url_publica',
    p_payload->>'localizacao_rotulo',
    coalesce((SELECT array_agg(v) FROM jsonb_array_elements_text(p_payload->'capacidades') v), ARRAY[]::text[]),
    coalesce((SELECT array_agg(v) FROM jsonb_array_elements_text(p_payload->'tags') v), ARRAY[]::text[]),
    p_payload->>'proxima_acao', 1
  RETURNING ativo_id INTO novo_id;

  IF p_payload ? 'engine' THEN
    PERFORM public.cofre_recusa_campo_desconhecido(p_payload->'engine', ARRAY[
      'modalidade','estado_operacional','versao_contrato','formatos','skins','nichos','vozes',
      'manifesto_fonte','manifesto_sha256','fonte_fingerprint','capacidades_observadas',
      'limitacoes','requisitos','destinos_compativeis','verificado_em'
    ], 'cofre_cadastrar_ativo.engine');

    INSERT INTO public.cofre_engine_perfil (
      ativo_id, modalidade, estado_operacional, versao_contrato,
      formatos, skins, nichos, vozes,
      manifesto_fonte, manifesto_sha256, fonte_fingerprint,
      capacidades_observadas, limitacoes, requisitos, destinos_compativeis, verificado_em)
    SELECT
      novo_id,
      p_payload->'engine'->>'modalidade',
      p_payload->'engine'->>'estado_operacional',
      p_payload->'engine'->>'versao_contrato',
      -- `->>` devolve NULL quando a chave falta E quando o valor e JSON null.
      -- Os dois significam "o manifesto nao declara", e e assim que NULL chega
      -- na coluna em vez de um zero inventado pelo importador.
      (p_payload->'engine'->>'formatos')::int,
      (p_payload->'engine'->>'skins')::int,
      (p_payload->'engine'->>'nichos')::int,
      (p_payload->'engine'->>'vozes')::int,
      p_payload->'engine'->>'manifesto_fonte',
      p_payload->'engine'->>'manifesto_sha256',
      p_payload->'engine'->>'fonte_fingerprint',
      coalesce((SELECT array_agg(v) FROM jsonb_array_elements_text(p_payload->'engine'->'capacidades_observadas') v), ARRAY[]::text[]),
      coalesce((SELECT array_agg(v) FROM jsonb_array_elements_text(p_payload->'engine'->'limitacoes') v), ARRAY[]::text[]),
      coalesce((SELECT array_agg(v) FROM jsonb_array_elements_text(p_payload->'engine'->'requisitos') v), ARRAY[]::text[]),
      coalesce((SELECT array_agg(v) FROM jsonb_array_elements_text(p_payload->'engine'->'destinos_compativeis') v), ARRAY[]::text[]),
      (p_payload->'engine'->>'verificado_em')::date;
  END IF;

  INSERT INTO public.cofre_ativo_revisao
    (ativo_id, revisao, operacao, snapshot, motivo, autor_sub, autor_email)
  VALUES
    (novo_id, 1,
     CASE WHEN p_payload ? 'engine' THEN 'importacao_engine' ELSE 'cadastro' END,
     public.cofre_snapshot_ativo(novo_id), p_motivo, p_autor_sub, p_autor_email);

  recibo := jsonb_build_object(
    'operacao', 'cofre.cadastrar_ativo', 'ativo_id', novo_id, 'revisao', 1);
  RETURN public.cofre_registra_operacao(p_chave, 'cofre.cadastrar_ativo', hash, recibo, p_autor_sub, p_autor_email);
END
$funcao$;

CREATE OR REPLACE FUNCTION public.cofre_revisar_ativo(
  p_ativo_id    text,
  p_payload     jsonb,
  p_chave       text,
  p_autor_sub   uuid,
  p_autor_email text,
  p_motivo      text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  guardado  jsonb;
  hash      text;
  nova_rev  integer;
  recibo    jsonb;
BEGIN
  PERFORM public.cofre_recusa_campo_desconhecido(p_payload, ARRAY[
    'nome','plataforma','estado','criticidade','resumo','dono_nome','dono_custodia',
    'projeto','vertical','display_id','url_publica','localizacao_rotulo',
    'capacidades','tags','proxima_acao'
  ], 'cofre_revisar_ativo');
  PERFORM public.cofre_recusa_chave_sensivel(p_payload, 'revisao');

  hash := public.cofre_entrada_hash('cofre.revisar_ativo:' || p_ativo_id, p_payload);
  guardado := public.cofre_idempotencia(p_chave, 'cofre.revisar_ativo', hash);
  IF guardado IS NOT NULL THEN
    RETURN guardado;
  END IF;

  -- `coalesce(novo, atual)` e o que faz esta funcao ser um PATCH e nao um PUT:
  -- campo ausente no payload preserva o valor, em vez de apaga-lo. Um PUT
  -- disfarcado de patch e como uma edicao de nome zera a custodia comprovada.
  UPDATE public.cofre_ativo a SET
    nome               = coalesce(p_payload->>'nome',        a.nome),
    plataforma         = coalesce(p_payload->>'plataforma',  a.plataforma),
    estado             = coalesce(p_payload->>'estado',      a.estado),
    criticidade        = coalesce(p_payload->>'criticidade', a.criticidade),
    resumo             = coalesce(p_payload->>'resumo',      a.resumo),
    dono_nome          = coalesce(p_payload->>'dono_nome',   a.dono_nome),
    dono_custodia      = coalesce(p_payload->>'dono_custodia', a.dono_custodia),
    projeto            = CASE WHEN p_payload ? 'projeto'            THEN p_payload->>'projeto'            ELSE a.projeto END,
    vertical           = CASE WHEN p_payload ? 'vertical'           THEN p_payload->>'vertical'           ELSE a.vertical END,
    display_id         = CASE WHEN p_payload ? 'display_id'         THEN p_payload->>'display_id'         ELSE a.display_id END,
    url_publica        = CASE WHEN p_payload ? 'url_publica'        THEN p_payload->>'url_publica'        ELSE a.url_publica END,
    localizacao_rotulo = CASE WHEN p_payload ? 'localizacao_rotulo' THEN p_payload->>'localizacao_rotulo' ELSE a.localizacao_rotulo END,
    capacidades        = CASE WHEN p_payload ? 'capacidades'
                              THEN coalesce((SELECT array_agg(v) FROM jsonb_array_elements_text(p_payload->'capacidades') v), ARRAY[]::text[])
                              ELSE a.capacidades END,
    tags               = CASE WHEN p_payload ? 'tags'
                              THEN coalesce((SELECT array_agg(v) FROM jsonb_array_elements_text(p_payload->'tags') v), ARRAY[]::text[])
                              ELSE a.tags END,
    proxima_acao       = coalesce(p_payload->>'proxima_acao', a.proxima_acao),
    revisao_atual      = a.revisao_atual + 1
  WHERE a.ativo_id = p_ativo_id
  RETURNING a.revisao_atual INTO nova_rev;

  IF nova_rev IS NULL THEN
    RAISE EXCEPTION 'ativo % nao existe no Cofre', p_ativo_id
      USING ERRCODE = 'no_data_found';
  END IF;

  INSERT INTO public.cofre_ativo_revisao
    (ativo_id, revisao, operacao, snapshot, motivo, autor_sub, autor_email)
  VALUES
    (p_ativo_id, nova_rev, 'revisao',
     public.cofre_snapshot_ativo(p_ativo_id), p_motivo, p_autor_sub, p_autor_email);

  recibo := jsonb_build_object(
    'operacao', 'cofre.revisar_ativo', 'ativo_id', p_ativo_id, 'revisao', nova_rev);
  RETURN public.cofre_registra_operacao(p_chave, 'cofre.revisar_ativo', hash, recibo, p_autor_sub, p_autor_email);
END
$funcao$;

CREATE OR REPLACE FUNCTION public.cofre_relacionar(
  p_payload     jsonb,
  p_chave       text,
  p_autor_sub   uuid,
  p_autor_email text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  guardado  jsonb;
  hash      text;
  origem    text := p_payload->>'origem_id';
  nova_rel  bigint;
  nova_rev  integer;
  recibo    jsonb;
BEGIN
  PERFORM public.cofre_recusa_campo_desconhecido(p_payload, ARRAY[
    'origem_id','tipo','destino_id','destino_externo','destino_rotulo','estado','declarada_por'
  ], 'cofre_relacionar');
  PERFORM public.cofre_recusa_chave_sensivel(p_payload, 'relacao');

  hash := public.cofre_entrada_hash('cofre.relacionar', p_payload);
  guardado := public.cofre_idempotencia(p_chave, 'cofre.relacionar', hash);
  IF guardado IS NOT NULL THEN
    RETURN guardado;
  END IF;

  INSERT INTO public.cofre_relacao
    (origem_id, tipo, destino_id, destino_externo, destino_rotulo, estado, declarada_por)
  VALUES
    (origem, p_payload->>'tipo', p_payload->>'destino_id', p_payload->>'destino_externo',
     p_payload->>'destino_rotulo', coalesce(p_payload->>'estado','declared'),
     coalesce(p_payload->>'declarada_por', p_autor_email))
  RETURNING relacao_id INTO nova_rel;

  UPDATE public.cofre_ativo SET revisao_atual = revisao_atual + 1
   WHERE ativo_id = origem
  RETURNING revisao_atual INTO nova_rev;

  INSERT INTO public.cofre_ativo_revisao
    (ativo_id, revisao, operacao, snapshot, motivo, autor_sub, autor_email)
  VALUES
    (origem, nova_rev, 'relacao_criada', public.cofre_snapshot_ativo(origem),
     'relacao ' || (p_payload->>'tipo') || ' -> ' ||
       coalesce(p_payload->>'destino_id', p_payload->>'destino_externo'),
     p_autor_sub, p_autor_email);

  recibo := jsonb_build_object(
    'operacao', 'cofre.relacionar', 'ativo_id', origem,
    'relacao_id', nova_rel, 'revisao', nova_rev);
  RETURN public.cofre_registra_operacao(p_chave, 'cofre.relacionar', hash, recibo, p_autor_sub, p_autor_email);
END
$funcao$;

CREATE OR REPLACE FUNCTION public.cofre_desfazer_relacao(
  p_relacao_id  bigint,
  p_motivo      text,
  p_chave       text,
  p_autor_sub   uuid,
  p_autor_email text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  guardado jsonb;
  hash     text;
  origem   text;
  nova_rev integer;
  recibo   jsonb;
BEGIN
  hash := public.cofre_entrada_hash('cofre.desfazer_relacao',
            jsonb_build_object('relacao_id', p_relacao_id, 'motivo', p_motivo));
  guardado := public.cofre_idempotencia(p_chave, 'cofre.desfazer_relacao', hash);
  IF guardado IS NOT NULL THEN
    RETURN guardado;
  END IF;

  -- `WHERE desfeito_em IS NULL` protege contra desfazer duas vezes com chaves
  -- diferentes: a segunda nao encontra linha e levanta, em vez de reescrever o
  -- motivo original e apagar por que a relacao caiu da primeira vez.
  UPDATE public.cofre_relacao
     SET desfeito_em = now(), desfeito_motivo = p_motivo
   WHERE relacao_id = p_relacao_id AND desfeito_em IS NULL
  RETURNING origem_id INTO origem;

  IF origem IS NULL THEN
    RAISE EXCEPTION 'relacao % nao existe ou ja estava desfeita', p_relacao_id
      USING ERRCODE = 'no_data_found';
  END IF;

  UPDATE public.cofre_ativo SET revisao_atual = revisao_atual + 1
   WHERE ativo_id = origem RETURNING revisao_atual INTO nova_rev;

  INSERT INTO public.cofre_ativo_revisao
    (ativo_id, revisao, operacao, snapshot, motivo, autor_sub, autor_email)
  VALUES
    (origem, nova_rev, 'relacao_desfeita', public.cofre_snapshot_ativo(origem),
     p_motivo, p_autor_sub, p_autor_email);

  recibo := jsonb_build_object(
    'operacao', 'cofre.desfazer_relacao', 'ativo_id', origem,
    'relacao_id', p_relacao_id, 'revisao', nova_rev);
  RETURN public.cofre_registra_operacao(p_chave, 'cofre.desfazer_relacao', hash, recibo, p_autor_sub, p_autor_email);
END
$funcao$;

CREATE OR REPLACE FUNCTION public.cofre_aposentar_ativo(
  p_ativo_id    text,
  p_motivo      text,
  p_chave       text,
  p_autor_sub   uuid,
  p_autor_email text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  guardado jsonb;
  hash     text;
  nova_rev integer;
  recibo   jsonb;
BEGIN
  hash := public.cofre_entrada_hash('cofre.aposentar_ativo',
            jsonb_build_object('ativo_id', p_ativo_id, 'motivo', p_motivo));
  guardado := public.cofre_idempotencia(p_chave, 'cofre.aposentar_ativo', hash);
  IF guardado IS NOT NULL THEN
    RETURN guardado;
  END IF;

  -- Aposentar NAO apaga: marca. O ativo continua consultavel, as relacoes
  -- continuam existindo e a trilha continua inteira. Voltar e um ato, nao uma
  -- restauracao de backup.
  UPDATE public.cofre_ativo
     SET estado = 'retired', aposentado_em = now(), aposentado_motivo = p_motivo,
         revisao_atual = revisao_atual + 1
   WHERE ativo_id = p_ativo_id AND aposentado_em IS NULL
  RETURNING revisao_atual INTO nova_rev;

  IF nova_rev IS NULL THEN
    RAISE EXCEPTION 'ativo % nao existe ou ja estava aposentado', p_ativo_id
      USING ERRCODE = 'no_data_found';
  END IF;

  INSERT INTO public.cofre_ativo_revisao
    (ativo_id, revisao, operacao, snapshot, motivo, autor_sub, autor_email)
  VALUES
    (p_ativo_id, nova_rev, 'aposentadoria', public.cofre_snapshot_ativo(p_ativo_id),
     p_motivo, p_autor_sub, p_autor_email);

  recibo := jsonb_build_object(
    'operacao', 'cofre.aposentar_ativo', 'ativo_id', p_ativo_id, 'revisao', nova_rev);
  RETURN public.cofre_registra_operacao(p_chave, 'cofre.aposentar_ativo', hash, recibo, p_autor_sub, p_autor_email);
END
$funcao$;

CREATE OR REPLACE FUNCTION public.cofre_reativar_ativo(
  p_ativo_id    text,
  p_estado      text,
  p_motivo      text,
  p_chave       text,
  p_autor_sub   uuid,
  p_autor_email text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  guardado jsonb;
  hash     text;
  nova_rev integer;
  recibo   jsonb;
BEGIN
  IF p_estado = 'retired' THEN
    RAISE EXCEPTION 'reativar exige um estado diferente de retired'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  hash := public.cofre_entrada_hash('cofre.reativar_ativo',
            jsonb_build_object('ativo_id', p_ativo_id, 'estado', p_estado, 'motivo', p_motivo));
  guardado := public.cofre_idempotencia(p_chave, 'cofre.reativar_ativo', hash);
  IF guardado IS NOT NULL THEN
    RETURN guardado;
  END IF;

  UPDATE public.cofre_ativo
     SET estado = p_estado, aposentado_em = NULL, aposentado_motivo = NULL,
         revisao_atual = revisao_atual + 1
   WHERE ativo_id = p_ativo_id AND aposentado_em IS NOT NULL
  RETURNING revisao_atual INTO nova_rev;

  IF nova_rev IS NULL THEN
    RAISE EXCEPTION 'ativo % nao existe ou nao estava aposentado', p_ativo_id
      USING ERRCODE = 'no_data_found';
  END IF;

  INSERT INTO public.cofre_ativo_revisao
    (ativo_id, revisao, operacao, snapshot, motivo, autor_sub, autor_email)
  VALUES
    (p_ativo_id, nova_rev, 'reativacao', public.cofre_snapshot_ativo(p_ativo_id),
     p_motivo, p_autor_sub, p_autor_email);

  recibo := jsonb_build_object(
    'operacao', 'cofre.reativar_ativo', 'ativo_id', p_ativo_id, 'revisao', nova_rev);
  RETURN public.cofre_registra_operacao(p_chave, 'cofre.reativar_ativo', hash, recibo, p_autor_sub, p_autor_email);
END
$funcao$;

CREATE OR REPLACE FUNCTION public.cofre_registrar_verificacao(
  p_payload     jsonb,
  p_chave       text,
  p_autor_sub   uuid,
  p_autor_email text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  guardado jsonb;
  hash     text;
  ativo    text := p_payload->>'ativo_id';
  nova_ver bigint;
  nova_rev integer;
  recibo   jsonb;
BEGIN
  PERFORM public.cofre_recusa_campo_desconhecido(p_payload, ARRAY[
    'ativo_id','alvo','resultado','metodo','procedencia','evidencia',
    'observado_em','proximo_ato','revisar_em'
  ], 'cofre_registrar_verificacao');
  PERFORM public.cofre_recusa_chave_sensivel(p_payload, 'verificacao');

  hash := public.cofre_entrada_hash('cofre.registrar_verificacao', p_payload);
  guardado := public.cofre_idempotencia(p_chave, 'cofre.registrar_verificacao', hash);
  IF guardado IS NOT NULL THEN
    RETURN guardado;
  END IF;

  INSERT INTO public.cofre_verificacao
    (ativo_id, alvo, resultado, metodo, procedencia, evidencia,
     observado_em, proximo_ato, revisar_em, autor_sub, autor_email)
  VALUES
    (ativo, p_payload->>'alvo', p_payload->>'resultado', p_payload->>'metodo',
     p_payload->>'procedencia', p_payload->>'evidencia',
     -- Sem DEFAULT now(): o instante da OBSERVACAO nao e o instante do
     -- registro. Deixar o banco preencher transformaria "conferi ontem" em
     -- "conferi agora", que e o mesmo defeito de frescor da v9_01.
     (p_payload->>'observado_em')::timestamptz,
     p_payload->>'proximo_ato', (p_payload->>'revisar_em')::date,
     p_autor_sub, p_autor_email)
  RETURNING verificacao_id INTO nova_ver;

  -- A verificacao de CREDENCIAL tambem move a postura da referencia. Sem isso,
  -- o recibo diria `verified` e o card continuaria dizendo `unverified`.
  IF p_payload->>'alvo' = 'credencial' THEN
    UPDATE public.cofre_credencial_referencia
       SET verificacao_estado = p_payload->>'resultado',
           verificado_em      = (p_payload->>'observado_em')::timestamptz
     WHERE ativo_id = ativo AND aposentado_em IS NULL;
  END IF;

  UPDATE public.cofre_ativo SET revisao_atual = revisao_atual + 1
   WHERE ativo_id = ativo RETURNING revisao_atual INTO nova_rev;

  INSERT INTO public.cofre_ativo_revisao
    (ativo_id, revisao, operacao, snapshot, motivo, autor_sub, autor_email)
  VALUES
    (ativo, nova_rev, 'verificacao', public.cofre_snapshot_ativo(ativo),
     'verificacao ' || (p_payload->>'alvo') || ': ' || (p_payload->>'resultado'),
     p_autor_sub, p_autor_email);

  recibo := jsonb_build_object(
    'operacao', 'cofre.registrar_verificacao', 'ativo_id', ativo,
    'verificacao_id', nova_ver, 'resultado', p_payload->>'resultado', 'revisao', nova_rev);
  RETURN public.cofre_registra_operacao(p_chave, 'cofre.registrar_verificacao', hash, recibo, p_autor_sub, p_autor_email);
END
$funcao$;

CREATE OR REPLACE FUNCTION public.cofre_referenciar_credencial(
  p_payload     jsonb,
  p_chave       text,
  p_autor_sub   uuid,
  p_autor_email text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  guardado jsonb;
  hash     text;
  ativo    text := p_payload->>'ativo_id';
  nova_ref bigint;
  nova_rev integer;
  recibo   jsonb;
BEGIN
  -- `localizador` E um campo permitido AQUI e em nenhum outro lugar. Esta e a
  -- unica porta pela qual ele entra no banco, e a CHECK de forma da secao 8 e
  -- quem decide se o que chegou e endereco ou segredo.
  PERFORM public.cofre_recusa_campo_desconhecido(p_payload, ARRAY[
    'ativo_id','provider','nome_logico','localizador','finalidade','owner_nome',
    'estado','valido_ate'
  ], 'cofre_referenciar_credencial');

  -- A varredura roda no payload SEM o localizador: `localizador` esta na lista
  -- de chaves proibidas (secao 11) de proposito, para que ele nao possa viajar
  -- dentro de nenhum outro documento do dominio. Aqui ele e legitimo, entao a
  -- varredura olha o resto — inclusive um `password` aninhado que alguem
  -- tivesse anexado a esta chamada.
  PERFORM public.cofre_recusa_chave_sensivel(p_payload - 'localizador', 'credencial');

  -- A validacao da FORMA acontece AQUI, e nao so na CHECK, por um motivo
  -- medido: a violacao de CHECK anexa `DETAIL: Failing row contains (…)` com a
  -- linha inteira, e a linha inteira inclui o valor recusado. Alguem colando uma
  -- senha neste campo faria a senha aparecer no log do Postgres e no corpo do
  -- erro do PostgREST — a recusa vazaria exatamente o que ela existe para
  -- impedir. Esta mensagem cita o provider e a forma esperada, nunca o valor.
  IF NOT public.cofre_localizador_valido(p_payload->>'provider', p_payload->>'localizador') THEN
    RAISE EXCEPTION
      'referencia invalida para o provider %: a forma esperada e %. O valor recebido nao e repetido aqui de proposito.',
      coalesce(p_payload->>'provider','(ausente)'),
      public.cofre_forma_esperada(p_payload->>'provider')
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  hash := public.cofre_entrada_hash('cofre.referenciar_credencial', p_payload);
  guardado := public.cofre_idempotencia(p_chave, 'cofre.referenciar_credencial', hash);
  IF guardado IS NOT NULL THEN
    RETURN guardado;
  END IF;

  INSERT INTO public.cofre_credencial_referencia
    (ativo_id, provider, nome_logico, localizador, finalidade, owner_nome, estado, valido_ate)
  VALUES
    (ativo, p_payload->>'provider', p_payload->>'nome_logico', p_payload->>'localizador',
     p_payload->>'finalidade', p_payload->>'owner_nome',
     coalesce(p_payload->>'estado','referenced'), (p_payload->>'valido_ate')::date)
  RETURNING referencia_id INTO nova_ref;

  UPDATE public.cofre_ativo SET revisao_atual = revisao_atual + 1
   WHERE ativo_id = ativo RETURNING revisao_atual INTO nova_rev;

  -- ⚠️ O snapshot NAO recebe o localizador: `cofre_snapshot_ativo` nem sequer
  -- consulta `cofre_credencial_referencia`. O motivo registrado cita o NOME
  -- LOGICO, que e o que um auditor precisa, e nunca o endereco.
  INSERT INTO public.cofre_ativo_revisao
    (ativo_id, revisao, operacao, snapshot, motivo, autor_sub, autor_email)
  VALUES
    (ativo, nova_rev, 'credencial_referenciada', public.cofre_snapshot_ativo(ativo),
     'referencia ' || (p_payload->>'provider') || ' para ' || (p_payload->>'nome_logico'),
     p_autor_sub, p_autor_email);

  recibo := jsonb_build_object(
    'operacao', 'cofre.referenciar_credencial', 'ativo_id', ativo,
    'referencia_id', nova_ref, 'provider', p_payload->>'provider',
    'nome_logico', p_payload->>'nome_logico', 'revisao', nova_rev);
  RETURN public.cofre_registra_operacao(p_chave, 'cofre.referenciar_credencial', hash, recibo, p_autor_sub, p_autor_email);
END
$funcao$;


-- -----------------------------------------------------------------------------
-- 16. LEITURA — postura sim, endereco nunca
-- -----------------------------------------------------------------------------
-- `cofre_postura_credencial` e a projecao que a API pode publicar. Compare a
-- lista de campos com `cofre_credencial_referencia`: `localizador` nao esta
-- aqui, e essa ausencia e o produto desta funcao.
CREATE OR REPLACE FUNCTION public.cofre_postura_credencial(p_ativo_id text)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $funcao$
  SELECT coalesce(jsonb_agg(jsonb_build_object(
           'referencia_id',      c.referencia_id,
           'provider',           c.provider,
           'nome_logico',        c.nome_logico,
           'finalidade',         c.finalidade,
           'owner_nome',         c.owner_nome,
           'estado',             c.estado,
           'valido_ate',         c.valido_ate,
           'verificacao_estado', c.verificacao_estado,
           'verificado_em',      c.verificado_em,
           -- Booleano, nao endereco. A tela precisa saber SE existe referencia
           -- registrada; saber ONDE ela aponta nao muda nada na tela e e
           -- exatamente o que nao pode sair daqui.
           'referencia_registrada', true
         ) ORDER BY c.nome_logico), '[]'::jsonb)
    FROM public.cofre_credencial_referencia c
   WHERE c.ativo_id = p_ativo_id AND c.aposentado_em IS NULL;
$funcao$;

COMMENT ON FUNCTION public.cofre_postura_credencial(text) IS
  'Postura de credencial SEM localizador. A ausencia do campo e o contrato desta funcao.';

CREATE OR REPLACE FUNCTION public.cofre_detalhar_ativo(p_ativo_id text)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $funcao$
  SELECT public.cofre_snapshot_ativo(a.ativo_id)
      || jsonb_build_object(
           'gaveta_rotulo', g.rotulo,
           'tipo_rotulo',   t.rotulo,
           'criado_em',     a.criado_em,
           'atualizado_em', a.atualizado_em,
           'credencial',    public.cofre_postura_credencial(a.ativo_id),
           'verificacao', (
             SELECT coalesce(jsonb_agg(jsonb_build_object(
                      'verificacao_id', v.verificacao_id,
                      'alvo',           v.alvo,
                      'resultado',      v.resultado,
                      'metodo',         v.metodo,
                      'procedencia',    v.procedencia,
                      'evidencia',      v.evidencia,
                      'observado_em',   v.observado_em,
                      'proximo_ato',    v.proximo_ato,
                      'revisar_em',     v.revisar_em)
                      ORDER BY v.observado_em DESC), '[]'::jsonb)
               FROM public.cofre_verificacao v WHERE v.ativo_id = a.ativo_id),
           'historico', (
             SELECT coalesce(jsonb_agg(jsonb_build_object(
                      'revisao',     r.revisao,
                      'operacao',    r.operacao,
                      'motivo',      r.motivo,
                      'autor_email', r.autor_email,
                      'ocorrido_em', r.ocorrido_em)
                      ORDER BY r.revisao DESC), '[]'::jsonb)
               FROM public.cofre_ativo_revisao r WHERE r.ativo_id = a.ativo_id))
    FROM public.cofre_ativo a
    JOIN public.cofre_gaveta g ON g.cluster = a.cluster
    JOIN public.cofre_tipo   t ON t.kind    = a.kind
   WHERE a.ativo_id = p_ativo_id;
$funcao$;

CREATE OR REPLACE FUNCTION public.cofre_listar_ativos(
  p_cluster             text    DEFAULT NULL,
  p_kind                text    DEFAULT NULL,
  p_estado              text    DEFAULT NULL,
  p_busca               text    DEFAULT NULL,
  p_incluir_aposentados boolean DEFAULT false
)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $funcao$
  -- Devolve um OBJETO com `gavetas` e `ativos`, nao um array solto. As sete
  -- gavetas viajam SEMPRE, inclusive as vazias com contagem zero: uma gaveta
  -- que some quando fica vazia faz a estrutura do Cofre parecer menor do que e,
  -- e e por isso que a contagem vem do banco e nao de um `group by` no cliente.
  SELECT jsonb_build_object(
    'gavetas', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
               'cluster',   g.cluster,
               'rotulo',    g.rotulo,
               'descricao', g.descricao,
               'ordem',     g.ordem,
               'total',     (SELECT count(*) FROM public.cofre_ativo a2
                              WHERE a2.cluster = g.cluster
                                AND (p_incluir_aposentados OR a2.aposentado_em IS NULL)))
               ORDER BY g.ordem), '[]'::jsonb)
        FROM public.cofre_gaveta g),
    'ativos', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
               'ativo_id',      a.ativo_id,
               'nome',          a.nome,
               'kind',          a.kind,
               'tipo_rotulo',   t.rotulo,
               'cluster',       a.cluster,
               'plataforma',    a.plataforma,
               'estado',        a.estado,
               'criticidade',   a.criticidade,
               'resumo',        a.resumo,
               'dono_nome',     a.dono_nome,
               'dono_custodia', a.dono_custodia,
               'projeto',       a.projeto,
               'vertical',      a.vertical,
               'display_id',    a.display_id,
               'url_publica',   a.url_publica,
               'tags',          to_jsonb(a.tags),
               'proxima_acao',  a.proxima_acao,
               'revisao_atual', a.revisao_atual,
               'aposentado_em', a.aposentado_em,
               'credencial_registrada', EXISTS (
                 SELECT 1 FROM public.cofre_credencial_referencia c
                  WHERE c.ativo_id = a.ativo_id AND c.aposentado_em IS NULL),
               'verificacao_estado', coalesce((
                 SELECT v.resultado FROM public.cofre_verificacao v
                  WHERE v.ativo_id = a.ativo_id AND v.alvo = 'ativo'
                  ORDER BY v.observado_em DESC LIMIT 1), 'unverified'),
               'verificado_em', (
                 SELECT v.observado_em FROM public.cofre_verificacao v
                  WHERE v.ativo_id = a.ativo_id AND v.alvo = 'ativo'
                  ORDER BY v.observado_em DESC LIMIT 1))
               ORDER BY a.cluster, a.nome), '[]'::jsonb)
        FROM public.cofre_ativo a
        JOIN public.cofre_tipo t ON t.kind = a.kind
       WHERE (p_incluir_aposentados OR a.aposentado_em IS NULL)
         AND (p_cluster IS NULL OR a.cluster = p_cluster)
         AND (p_kind    IS NULL OR a.kind    = p_kind)
         AND (p_estado  IS NULL OR a.estado  = p_estado)
         AND (p_busca   IS NULL OR
              (a.nome || ' ' || a.plataforma || ' ' || coalesce(a.projeto,'') || ' ' ||
               coalesce(a.vertical,'') || ' ' || array_to_string(a.tags,' '))
              ILIKE '%' || p_busca || '%'))
  );
$funcao$;

COMMENT ON FUNCTION public.cofre_listar_ativos(text, text, text, text, boolean) IS
  'Inventario por gaveta. Devolve as sete gavetas sempre, inclusive com contagem zero.';

CREATE OR REPLACE FUNCTION public.cofre_engines_disponiveis()
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $funcao$
  -- A ponte para producao criativa (item G da missao): quais engines existem, o
  -- que produzem e para onde. Ela RESPONDE, nao executa — nenhum job sai daqui.
  SELECT coalesce(jsonb_agg(jsonb_build_object(
           'ativo_id',               a.ativo_id,
           'nome',                   a.nome,
           'estado',                 a.estado,
           'modalidade',             e.modalidade,
           'estado_operacional',     e.estado_operacional,
           'versao_contrato',        e.versao_contrato,
           'formatos',               e.formatos,
           'skins',                  e.skins,
           'nichos',                 e.nichos,
           'vozes',                  e.vozes,
           'capacidades_observadas', to_jsonb(e.capacidades_observadas),
           'limitacoes',             to_jsonb(e.limitacoes),
           'requisitos',             to_jsonb(e.requisitos),
           'destinos_compativeis',   to_jsonb(e.destinos_compativeis),
           'manifesto_fonte',        e.manifesto_fonte,
           'verificado_em',          e.verificado_em,
           'localizacao_rotulo',     a.localizacao_rotulo)
           ORDER BY a.nome), '[]'::jsonb)
    FROM public.cofre_engine_perfil e
    JOIN public.cofre_ativo a ON a.ativo_id = e.ativo_id
   WHERE a.aposentado_em IS NULL;
$funcao$;

COMMENT ON FUNCTION public.cofre_engines_disponiveis() IS
  'Catalogo de engines para o handoff de producao criativa. Responde capacidade; nao dispara job.';


-- -----------------------------------------------------------------------------
-- 17. A GUARDA QUE FALTAVA — o dono precisa atravessar a propria RLS
-- -----------------------------------------------------------------------------
-- `FORCE ROW LEVEL SECURITY` sujeita o DONO da tabela a RLS, e a secao 20 nao
-- cria policy nenhuma. Num banco onde o dono nao atravessa RLS, o schema
-- aplicaria limpo e TODA escrita governada falharia depois — o pior momento
-- possivel para descobrir.
--
-- Medido em producao (database.agenciavolc.com.br, consulta somente leitura a
-- `pg_roles`, 01/09/2026):
--
--   rolname         | rolsuper | rolbypassrls
--   postgres        | f        | t
--   supabase_admin  | t        | t
--   service_role    | f        | t
--   authenticated   | f        | f
--   anon            | f        | f
--
-- `postgres` NAO e superusuario neste Supabase — mas tem BYPASSRLS, e e por
-- isso que as funcoes `SECURITY DEFINER` deste arquivo funcionam sob RLS
-- forcada. A guarda abaixo transforma essa medicao em pre-condicao: onde ela
-- nao valer, a migration ABORTA em vez de deixar uma bomba armada.
--
-- ⚠️ Note o outro lado da mesma tabela: `service_role` TAMBEM tem BYPASSRLS.
-- RLS nao contem `service_role` — quem o contem sao os REVOKE nominais da
-- secao 20. Confiar em RLS para conter o backend seria confiar na trava errada.
DO $guarda_rls$
DECLARE
  atravessa boolean;
BEGIN
  SELECT rolsuper OR rolbypassrls INTO atravessa
    FROM pg_roles WHERE rolname = current_user;

  IF NOT coalesce(atravessa, false) THEN
    RAISE EXCEPTION
      'v13_01 exige que % atravesse RLS (rolsuper ou rolbypassrls). Sem isso, FORCE ROW LEVEL SECURITY sem policy bloquearia as proprias funcoes governadas e toda escrita do Cofre falharia em runtime.',
      current_user;
  END IF;

  RAISE NOTICE 'v13_01: % atravessa RLS — funcoes governadas operarao sob FORCE', current_user;
END
$guarda_rls$;


-- -----------------------------------------------------------------------------
-- 18. VIEW de leitura — security_invoker, e por isso ela nao vaza nada
-- -----------------------------------------------------------------------------
-- Sem `security_invoker=true` uma view roda com os privilegios do DONO, e
-- entregaria as tabelas inteiras a quem tivesse SELECT nela — passando por cima
-- de todo o trabalho da secao 20. Com ele, a view so mostra o que o chamador ja
-- poderia ver; como ninguem tem SELECT nas tabelas, ela e util apenas dentro de
-- funcao `SECURITY DEFINER`.
--
-- ⚠️ Ela NAO junta `cofre_credencial_referencia`. Nem por leitura, nem por
-- EXISTS. A contagem de credenciais vem de `cofre_listar_ativos`, que e funcao
-- governada, para que a superficie de leitura direta nunca toque naquela tabela.
CREATE VIEW public.cofre_inventario WITH (security_invoker = true) AS
  SELECT
    a.ativo_id, a.nome, a.kind, t.rotulo AS tipo_rotulo,
    a.cluster, g.rotulo AS gaveta_rotulo, g.ordem AS gaveta_ordem,
    a.plataforma, a.estado, a.criticidade, a.dono_nome, a.dono_custodia,
    a.projeto, a.vertical, a.display_id, a.url_publica,
    a.revisao_atual, a.criado_em, a.atualizado_em, a.aposentado_em
  FROM public.cofre_ativo a
  JOIN public.cofre_gaveta g ON g.cluster = a.cluster
  JOIN public.cofre_tipo   t ON t.kind    = a.kind;

COMMENT ON VIEW public.cofre_inventario IS
  'Projecao de leitura do inventario. security_invoker=true; nao toca cofre_credencial_referencia.';


-- -----------------------------------------------------------------------------
-- 19. SEGURANCA — REVOKE nominal, RLS forcada, zero policy, grants minimos
-- -----------------------------------------------------------------------------
-- Ordem importa: REVOKE primeiro (as tabelas ja nasceram abertas pelo default
-- ACL do achado H), RLS depois, GRANT minimo por ultimo.
DO $seguranca$
DECLARE
  t text;
  f text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'cofre_gaveta','cofre_tipo','cofre_ativo','cofre_engine_perfil',
    'cofre_ativo_revisao','cofre_relacao','cofre_credencial_referencia',
    'cofre_verificacao','cofre_operacao'
  ]
  LOOP
    -- 1) REVOKE NOMINAL. `FROM PUBLIC` nao resolve: os grants do default ACL
    --    sao concedidos a cada papel POR NOME, e so um REVOKE por nome os tira.
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated', t);
    -- `service_role` inclusive. Ele tem BYPASSRLS, entao RLS nao o contem — o
    -- REVOKE contem. Sem esta linha, um endpoint generico com a service key
    -- escreveria direto na tabela e pularia allowlist, blocklist, idempotencia
    -- e trilha de uma vez so.
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM service_role', t);

    -- 2) RLS FORCADA, com ZERO policies: negacao por ausencia. Defesa em
    --    profundidade — se um GRANT reaparecer por engano numa migration
    --    futura, anon continua lendo zero linha.
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE  ROW LEVEL SECURITY', t);
  END LOOP;

  -- A view: mesmo tratamento. security_invoker ja a impede de vazar, e o REVOKE
  -- faz a segunda camada.
  EXECUTE 'REVOKE ALL ON TABLE public.cofre_inventario FROM PUBLIC';
  EXECUTE 'REVOKE ALL ON TABLE public.cofre_inventario FROM anon';
  EXECUTE 'REVOKE ALL ON TABLE public.cofre_inventario FROM authenticated';
  EXECUTE 'REVOKE ALL ON TABLE public.cofre_inventario FROM service_role';

  -- 3) FUNCOES: revogar de todos, inclusive service_role, e so entao conceder
  --    nominalmente as que compoem a API. As internas (`cofre_snapshot_ativo`,
  --    `cofre_idempotencia`, `cofre_registra_operacao`, as duas recusas, os
  --    ajudantes) ficam SEM grant nenhum: elas rodam dentro das governadas, com
  --    os privilegios do dono, e nao precisam ser chamaveis de fora.
  FOR f IN
    SELECT p.oid::regprocedure::text
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.proname LIKE 'cofre\_%'
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM anon', f);
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM authenticated', f);
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM service_role', f);
  END LOOP;

  -- Sequencias das colunas IDENTITY: o default ACL tambem as abre.
  FOR f IN
    SELECT c.oid::regclass::text
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind = 'S' AND c.relname LIKE 'cofre\_%'
  LOOP
    EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM PUBLIC, anon, authenticated, service_role', f);
  END LOOP;

  RAISE NOTICE 'v13_01: 9 tabelas revogadas nominalmente, RLS forcada, zero policies';
END
$seguranca$;

-- A API governada — e SOMENTE ela. `service_role` nao ganha nada alem disto.
GRANT EXECUTE ON FUNCTION public.cofre_cadastrar_ativo(jsonb, text, uuid, text, text)          TO service_role;
GRANT EXECUTE ON FUNCTION public.cofre_revisar_ativo(text, jsonb, text, uuid, text, text)      TO service_role;
GRANT EXECUTE ON FUNCTION public.cofre_relacionar(jsonb, text, uuid, text)                     TO service_role;
GRANT EXECUTE ON FUNCTION public.cofre_desfazer_relacao(bigint, text, text, uuid, text)        TO service_role;
GRANT EXECUTE ON FUNCTION public.cofre_aposentar_ativo(text, text, text, uuid, text)           TO service_role;
GRANT EXECUTE ON FUNCTION public.cofre_reativar_ativo(text, text, text, text, uuid, text)      TO service_role;
GRANT EXECUTE ON FUNCTION public.cofre_registrar_verificacao(jsonb, text, uuid, text)          TO service_role;
GRANT EXECUTE ON FUNCTION public.cofre_referenciar_credencial(jsonb, text, uuid, text)         TO service_role;
GRANT EXECUTE ON FUNCTION public.cofre_listar_ativos(text, text, text, text, boolean)          TO service_role;
GRANT EXECUTE ON FUNCTION public.cofre_detalhar_ativo(text)                                    TO service_role;
GRANT EXECUTE ON FUNCTION public.cofre_postura_credencial(text)                                TO service_role;
GRANT EXECUTE ON FUNCTION public.cofre_engines_disponiveis()                                   TO service_role;


-- -----------------------------------------------------------------------------
-- 20. CONFERENCIA FINAL — a migration se recusa a terminar meio feita
-- -----------------------------------------------------------------------------
DO $conferencia$
DECLARE
  n_tabelas   int;
  n_rls       int;
  n_forcada   int;
  n_policies  int;
  n_grants    int;
  n_exec_anon int;
BEGIN
  SELECT count(*) INTO n_tabelas
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname LIKE 'cofre\_%';

  SELECT count(*) FILTER (WHERE c.relrowsecurity),
         count(*) FILTER (WHERE c.relforcerowsecurity)
    INTO n_rls, n_forcada
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname LIKE 'cofre\_%';

  SELECT count(*) INTO n_policies
    FROM pg_policies WHERE schemaname = 'public' AND tablename LIKE 'cofre\_%';

  SELECT count(*) INTO n_grants
    FROM information_schema.role_table_grants
   WHERE table_schema = 'public' AND table_name LIKE 'cofre\_%'
     AND grantee IN ('anon','authenticated','PUBLIC');

  SELECT count(*) INTO n_exec_anon
    FROM information_schema.role_routine_grants
   WHERE routine_schema = 'public' AND routine_name LIKE 'cofre\_%'
     AND grantee IN ('anon','authenticated','PUBLIC');

  IF n_tabelas <> 9 THEN
    RAISE EXCEPTION 'v13_01: esperava 9 tabelas cofre_, encontrei %', n_tabelas;
  END IF;
  IF n_rls <> 9 OR n_forcada <> 9 THEN
    RAISE EXCEPTION 'v13_01: RLS em % e forcada em % de 9 tabelas', n_rls, n_forcada;
  END IF;
  IF n_policies <> 0 THEN
    RAISE EXCEPTION 'v13_01: existem % policies em cofre_*; o desenho e negacao por ausencia', n_policies;
  END IF;
  IF n_grants <> 0 THEN
    RAISE EXCEPTION 'v13_01: % grant(s) de tabela para anon/authenticated/PUBLIC sobreviveram', n_grants;
  END IF;
  IF n_exec_anon <> 0 THEN
    RAISE EXCEPTION 'v13_01: % EXECUTE para anon/authenticated/PUBLIC sobreviveram', n_exec_anon;
  END IF;

  RAISE NOTICE 'v13_01 OK: 9 tabelas, RLS forcada em 9, 0 policies, 0 grants a anon/authenticated';
END
$conferencia$;

COMMIT;

-- PostgREST guarda o schema em cache; sem isto as funcoes novas respondem 404
-- ate o proximo reload, e quem estiver depurando vai procurar o erro no backend.
NOTIFY pgrst, 'reload schema';
