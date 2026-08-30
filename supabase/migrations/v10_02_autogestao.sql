-- =============================================================================
-- v10_02 — Autogestao em nivel T1: a maquina recomenda, o humano aplica
-- GOOGLE GROWTH ENGINE / AGENTE E. ARQUIVO. NAO APLICADO EM PRODUCAO.
-- =============================================================================
-- APLICAR COMO: postgres (supabase_admin tambem serve; a guarda aceita os dois)
--
-- ORDEM: DEPOIS da v9_01. INDEPENDENTE da v10_01 — as duas nao se tocam, e a
--        independencia e proposital: criar campanha e otimizar campanha sao
--        dois ciclos, e reverter um nao pode derrubar o outro.
-- ROLLBACK: supabase/migrations/v10_02_rollback.sql (executavel, e RODADO)
--
-- -----------------------------------------------------------------------------
-- O CICLO QUE ESTE ARQUIVO PERSISTE
-- -----------------------------------------------------------------------------
--
--   snapshot -> suficiencia de evidencia -> deteccao -> diagnostico
--   -> proposta -> diff -> APROVACAO HUMANA -> aplicacao -> verificacao
--   -> acompanhamento -> rollback
--
-- Nove tabelas:
--
--   trafego_regra_otimizacao  a regra como DADO VERSIONADO, nunca como codigo
--   trafego_evidencia         o snapshot em que a decisao se apoia, com carimbo
--   trafego_diagnostico       o que foi detectado, com regra e confianca
--   trafego_proposta          o diff: valor_atual x valor_proposto, em COLUNAS
--                             SEPARADAS
--   trafego_aprovacao         a decisao humana, append-only, com o diff que foi
--                             de fato mostrado
--   trafego_aplicacao         cada tentativa de escrita, escrita ANTES da
--                             chamada (mesmo protocolo do recibo da v10_01)
--   trafego_acompanhamento    verificacao imediata + acompanhamento posterior
--   trafego_atuacao_reversao  o desfazer, com o valor a restaurar
--   trafego_cooldown          o carencia por (regra, alvo) — escrita por gatilho
--
-- -----------------------------------------------------------------------------
-- POR QUE A REGRA E DADO, E NAO CODIGO
-- -----------------------------------------------------------------------------
-- Uma regra em Python nao pode ser CITADA por uma proposta. Ela nao tem versao
-- estavel, nao tem responsavel declarado, nao tem data de vigencia, e o dia em
-- que alguem a ajusta, todas as propostas antigas passam a ser explicadas pela
-- regra nova — o que reescreve retroativamente a razao de um gasto.
--
-- Aqui a proposta guarda o `regra_id` EXATO (chave + versao), e a linha da regra
-- e imutavel. "Por que mexemos no orcamento em 12/09?" tem resposta verificavel
-- para sempre.
--
-- ⚠️ CONTRATO DE FORMATO: `docs/growth-engine/legado-n8n/regras-canonicas.json`
-- (Agente G) descreve as regras herdadas do n8n no MESMO formato desta tabela.
-- O mapeamento campo a campo esta em `docs/growth-engine/persistencia.md`, e
-- `backend/tests/test_intencao_regras_canonicas.py` valida o arquivo contra
-- este esquema assim que ele existir.
--
-- -----------------------------------------------------------------------------
-- T1 EM FORMA DE SCHEMA — a automacao recomenda, o humano aplica
-- -----------------------------------------------------------------------------
-- Isto nao e uma convencao que um `if` no backend possa esquecer. Sao quatro
-- travas no banco:
--
--  1. `trafego_aplicacao.aprovacao_id` e NOT NULL com FK. Nao existe aplicacao
--     sem uma linha de aprovacao humana apontada.
--  2. `trafego_aplicacao_exige_aprovacao` recusa a aplicacao cuja aprovacao
--     apontada nao seja daquela proposta, ou cuja decisao nao seja `aprovada`.
--  3. `trafego_regra_nivel_conhecido` so aceita T0 e T1. T2 — a maquina
--     aplicando sozinha — nao e um valor recusado por engano: ele nao existe no
--     vocabulario, e entra por MIGRACAO quando alguem decidir que entra
--     (ADR-11). Recusa por AUSENCIA DECLARADA, e nao por `if` esquecido.
--  4. `trafego_proposta_respeita_regra` recusa, no INSERT, a proposta que
--     estoure o limite de alteracao, o teto de orcamento, o frescor maximo da
--     evidencia — ou que se apoie em evidencia declarada INSUFICIENTE.
--
-- -----------------------------------------------------------------------------
-- AS REGRAS DA CASA, VALIDAS AQUI TAMBEM
-- -----------------------------------------------------------------------------
-- A. NENHUM NUMERO SEM FRESCOR. `trafego_evidencia.colhida_em` e NOT NULL e
--    denomina TODAS as medidas da linha; `trafego_proposta.valor_atual_lido_em`
--    e NOT NULL e diz de quando e o "antes" do diff. Um diff cujo "antes" e de
--    tres semanas atras propoe mudar uma coisa que ja mudou.
-- B. AUSENCIA E NULL, NUNCA ZERO. Nenhuma metrica tem DEFAULT 0. `conversoes`
--    nula e "nao consegui medir"; zero e "medi e nao houve" — e as duas levam a
--    decisoes opostas sobre pausar uma campanha.
-- D. DECLARADO E OBSERVADO NAO DIVIDEM COLUNA. `valor_atual` e `valor_proposto`
--    sao duas colunas; `trafego_acompanhamento.valor_observado` e uma terceira.
--    Nenhuma sobrescreve outra.
-- E. HISTORICO NAO SE APAGA. Evidencia, diagnostico, aprovacao e acompanhamento
--    sao append-only. Regra e proposta sao imutaveis depois de publicadas.
--
-- -----------------------------------------------------------------------------
-- SEGURANCA — mesmos defaults inseguros da v9 (achado H)
-- -----------------------------------------------------------------------------
-- REVOKE nominal de PUBLIC/anon/authenticated/service_role, RLS ENABLE+FORCE com
-- zero policies, GRANT minimo so para service_role, DELETE para ninguem.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. GUARDAS
-- -----------------------------------------------------------------------------
DO $guarda$
DECLARE
  ja_existem text;
  faltando   text;
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION
      'v10_02 deve rodar como postgres ou supabase_admin; papel atual: %', current_user;
  END IF;

  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION
      'v10_02 exige PostgreSQL 15 ou maior (security_invoker em VIEW); aqui: %',
      current_setting('server_version');
  END IF;

  IF to_regclass('public.trafego_campanha') IS NULL THEN
    RAISE EXCEPTION
      'v10_02 abortada: a v9_01 nao esta aplicada. A evidencia e a proposta apontam para trafego_campanha.';
  END IF;

  SELECT string_agg(t, ', ' ORDER BY t) INTO ja_existem
    FROM unnest(ARRAY[
      'trafego_regra_otimizacao', 'trafego_evidencia', 'trafego_diagnostico',
      'trafego_proposta', 'trafego_aprovacao', 'trafego_aplicacao',
      'trafego_acompanhamento', 'trafego_atuacao_reversao', 'trafego_cooldown',
      'trafego_regra_vigente', 'trafego_proposta_painel', 'trafego_cooldown_ativo'
    ]) AS t
   WHERE to_regclass('public.' || t) IS NOT NULL;

  IF ja_existem IS NOT NULL THEN
    RAISE EXCEPTION
      'v10_02 ja parece aplicada: % ja existe(m). Rode v10_02_rollback.sql antes de reaplicar.',
      ja_existem;
  END IF;

  SELECT string_agg(r, ', ' ORDER BY r) INTO faltando
    FROM unnest(ARRAY['anon', 'authenticated', 'service_role']) AS r
   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION
      'v10_02 exige os papeis do Supabase; ausente(s): %. Sem eles o REVOKE nominal nao acontece e a tabela nasce aberta.',
      faltando;
  END IF;

  RAISE NOTICE 'v10_02: guardas ok (papel=%, versao=%)',
    current_user, current_setting('server_version');
END
$guarda$;


-- -----------------------------------------------------------------------------
-- 1. trafego_regra_otimizacao — a regra como dado versionado e imutavel
-- -----------------------------------------------------------------------------
-- As doze declaracoes que uma regra tem de fazer, e o que cada uma impede:
--
--   objetivo             sem ele, "melhorou" nao tem definicao
--   plataformas/canais   uma regra de Search aplicada a PMax mede outra coisa
--   janela_minima_dias   janela curta transforma ruido em diagnostico
--   atraso_conversao_dias  conversao chega dias depois do clique; sem o atraso,
--                        toda campanha nova parece um fracasso
--   amostra_minima_*     sem amostra, 1 clique sem conversao "prova" algo
--   dados_obrigatorios   quais medidas TEM de estar presentes para a regra
--                        sequer ser avaliada — a suficiencia de evidencia
--   frescor_maximo_horas dado velho decidindo gasto de hoje
--   teto_orcamento_*     o limite absoluto de quanto se pode propor gastar
--   limite_alteracao_*   o limite de quanto se pode mexer de uma vez
--   cooldown_horas       impede a regra de brigar consigo mesma a cada rodada
--   confianca_minima     abaixo dela a regra observa e nao propoe
--   condicao_rollback    o que significa "isto piorou" — declarado ANTES
--   responsavel          quem responde por ela. Regra sem dono nao tem quem a
--                        aposente quando ela passa a errar
CREATE TABLE public.trafego_regra_otimizacao (
  regra_id       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

  -- A identidade estavel atraves das versoes. O cooldown e por `chave`, e nao
  -- por `regra_id`: publicar a v2 de uma regra nao pode zerar a carencia que a
  -- v1 acabou de impor sobre a mesma campanha.
  chave          text        NOT NULL,
  versao         integer     NOT NULL,

  titulo         text        NOT NULL,
  objetivo       text        NOT NULL,

  plataformas    text[]      NOT NULL,
  canais         text[]      NOT NULL,

  janela_minima_dias      integer NOT NULL,
  atraso_conversao_dias   integer NOT NULL,
  frescor_maximo_horas    integer NOT NULL,

  amostra_minima_cliques     integer,
  amostra_minima_impressoes  integer,
  amostra_minima_conversoes  numeric(12,2),

  dados_obrigatorios text[]  NOT NULL,

  teto_orcamento_micros bigint,
  teto_orcamento_moeda  text,

  limite_alteracao_pct              numeric(6,3),
  limite_alteracao_absoluto_micros  bigint,

  cooldown_horas    integer NOT NULL,
  confianca_minima  numeric(4,3) NOT NULL,

  condicao_rollback     text    NOT NULL,
  rollback_janela_horas integer NOT NULL,

  responsavel     text    NOT NULL,
  nivel_autonomia text    NOT NULL DEFAULT 'T1',

  -- A deteccao e a acao como DADO. O banco nao as interpreta — nenhuma CHECK
  -- olha para dentro, nenhum indice depende do formato. Mesma doutrina de
  -- `trafego_evento.chave_de_agrupamento`: uma semantica escolhida cedo demais
  -- contamina tudo que vier depois.
  deteccao        jsonb   NOT NULL,
  acao            jsonb   NOT NULL,

  declarada_por   text        NOT NULL,
  declarada_em    timestamptz NOT NULL DEFAULT now(),
  -- De onde ela veio: 'legado_n8n:<workflow>' para as herdadas, 'humano' para as
  -- escritas aqui. Sem procedencia, uma regra migrada do n8n fica
  -- indistinguivel de uma que alguem inventou numa terca-feira.
  fonte           text        NOT NULL,

  vigente_desde   timestamptz,
  retirada_em     timestamptz,
  retirada_por    text,
  retirada_motivo text,

  CONSTRAINT trafego_regra_chave_valida
    CHECK (chave ~ '^[a-z][a-z0-9_]{2,63}$'),
  CONSTRAINT trafego_regra_versao_positiva CHECK (versao >= 1),
  CONSTRAINT trafego_regra_titulo_nao_vazio   CHECK (btrim(titulo) <> ''),
  CONSTRAINT trafego_regra_objetivo_nao_vazio CHECK (btrim(objetivo) <> ''),
  CONSTRAINT trafego_regra_fonte_nao_vazia    CHECK (btrim(fonte) <> ''),
  -- Regra sem dono nao tem quem a aposente quando ela passa a errar — e uma
  -- regra que erra em silencio gasta verba todo dia.
  CONSTRAINT trafego_regra_responsavel_nao_vazio
    CHECK (btrim(responsavel) <> ''),
  CONSTRAINT trafego_regra_declarante_nao_vazio
    CHECK (btrim(declarada_por) <> ''),

  CONSTRAINT trafego_regra_plataformas_validas
    CHECK (array_length(plataformas, 1) >= 1
           AND plataformas <@ ARRAY['GOOGLE_ADS', 'META_ADS']::text[]),
  -- Canal vem do vocabulario canonico (ADR-18), mais o coringa `*` para a regra
  -- que vale em qualquer canal. Sem o coringa, uma regra de orcamento de conta
  -- teria de listar treze canais e sair errada no dia em que o Google criar o
  -- decimo quarto.
  CONSTRAINT trafego_regra_canais_validos
    CHECK (array_length(canais, 1) >= 1
           AND canais <@ ARRAY[
             '*', 'SEARCH', 'DISPLAY', 'DEMAND_GEN', 'PERFORMANCE_MAX',
             'VIDEO', 'SHOPPING', 'DISCOVERY', 'MULTI_CHANNEL',
             'LOCAL', 'LOCAL_SERVICES', 'SMART', 'HOTEL', 'TRAVEL']::text[]),

  CONSTRAINT trafego_regra_janela_positiva CHECK (janela_minima_dias >= 1),
  CONSTRAINT trafego_regra_atraso_nao_negativo CHECK (atraso_conversao_dias >= 0),
  CONSTRAINT trafego_regra_frescor_positivo CHECK (frescor_maximo_horas >= 1),
  CONSTRAINT trafego_regra_cooldown_positivo CHECK (cooldown_horas >= 1),
  CONSTRAINT trafego_regra_rollback_janela_positiva CHECK (rollback_janela_horas >= 1),
  CONSTRAINT trafego_regra_condicao_rollback_nao_vazia
    CHECK (btrim(condicao_rollback) <> ''),

  CONSTRAINT trafego_regra_amostras_nao_negativas
    CHECK (coalesce(amostra_minima_cliques, 0) >= 0
           AND coalesce(amostra_minima_impressoes, 0) >= 0
           AND coalesce(amostra_minima_conversoes, 0) >= 0),
  -- ⚠️ UMA AMOSTRA MINIMA, PELO MENOS. Uma regra sem piso de amostra dispara
  -- sobre 1 clique e chama isso de diagnostico. E a forma mais comum de uma
  -- automacao de midia destruir uma campanha nova.
  CONSTRAINT trafego_regra_tem_amostra_minima
    CHECK (amostra_minima_cliques IS NOT NULL
           OR amostra_minima_impressoes IS NOT NULL
           OR amostra_minima_conversoes IS NOT NULL),

  -- Suficiencia de evidencia declarada, e nao inferida: a regra diz de quais
  -- medidas ela depende, e a proposta que se apoiar numa evidencia sem elas e
  -- recusada pelo gatilho `trafego_proposta_respeita_regra`.
  CONSTRAINT trafego_regra_tem_dados_obrigatorios
    CHECK (array_length(dados_obrigatorios, 1) >= 1),

  CONSTRAINT trafego_regra_teto_completo
    CHECK ((teto_orcamento_micros IS NULL) = (teto_orcamento_moeda IS NULL)),
  CONSTRAINT trafego_regra_teto_nao_negativo
    CHECK (teto_orcamento_micros IS NULL OR teto_orcamento_micros >= 0),
  CONSTRAINT trafego_regra_teto_moeda_iso
    CHECK (teto_orcamento_moeda IS NULL OR teto_orcamento_moeda ~ '^[A-Z]{3}$'),

  CONSTRAINT trafego_regra_limite_pct_valido
    CHECK (limite_alteracao_pct IS NULL
           OR (limite_alteracao_pct > 0 AND limite_alteracao_pct <= 100)),
  CONSTRAINT trafego_regra_limite_absoluto_valido
    CHECK (limite_alteracao_absoluto_micros IS NULL
           OR limite_alteracao_absoluto_micros >= 0),
  -- ⚠️ UM LIMITE DE ALTERACAO, PELO MENOS. Uma regra que pode mexer sem limite
  -- nao e T1 nem T0: ela e uma automacao com autorizacao ilimitada esperando
  -- um bug de sinal.
  CONSTRAINT trafego_regra_tem_limite_alteracao
    CHECK (limite_alteracao_pct IS NOT NULL
           OR limite_alteracao_absoluto_micros IS NOT NULL),

  CONSTRAINT trafego_regra_confianca_valida
    CHECK (confianca_minima > 0 AND confianca_minima <= 1),

  -- ⚠️ T2 NAO EXISTE NO VOCABULARIO. A maquina aplicando sozinha nao esta
  -- aprovada (ADR-11), e a ausencia e o registro dessa decisao. Quando alguem
  -- decidir que existe, entra por MIGRACAO — com nome, data e motivo — e nao
  -- por um valor que ja estava la esperando.
  CONSTRAINT trafego_regra_nivel_conhecido
    CHECK (nivel_autonomia IN ('T0', 'T1')),

  CONSTRAINT trafego_regra_deteccao_e_objeto CHECK (jsonb_typeof(deteccao) = 'object'),
  CONSTRAINT trafego_regra_acao_e_objeto     CHECK (jsonb_typeof(acao) = 'object'),

  CONSTRAINT trafego_regra_retirada_completa
    CHECK (
      (retirada_em IS NULL AND retirada_por IS NULL)
      OR (retirada_em IS NOT NULL AND btrim(coalesce(retirada_por, '')) <> ''
          AND btrim(coalesce(retirada_motivo, '')) <> '')
    ),
  CONSTRAINT trafego_regra_retirada_depois_da_vigencia
    CHECK (retirada_em IS NULL OR vigente_desde IS NULL OR retirada_em >= vigente_desde)
);

CREATE UNIQUE INDEX trafego_regra_versao_ux
  ON public.trafego_regra_otimizacao (chave, versao);
-- No maximo UMA versao vigente por chave. Duas vigentes seriam a mesma pergunta
-- com duas respostas, e o motor teria de escolher — escolhendo, ele viraria a
-- autoridade sobre a regra, que e justamente o que versionar evita.
CREATE UNIQUE INDEX trafego_regra_vigente_ux
  ON public.trafego_regra_otimizacao (chave)
  WHERE vigente_desde IS NOT NULL AND retirada_em IS NULL;

COMMENT ON TABLE public.trafego_regra_otimizacao IS
  'A regra de otimizacao como DADO versionado e imutavel. Formato espelhado por docs/growth-engine/legado-n8n/regras-canonicas.json.';
COMMENT ON COLUMN public.trafego_regra_otimizacao.nivel_autonomia IS
  'T0 observa, T1 recomenda. T2 (aplicar sozinha) NAO existe no vocabulario — ADR-11. Entra por migracao, nao por valor esquecido.';
COMMENT ON COLUMN public.trafego_regra_otimizacao.dados_obrigatorios IS
  'Quais medidas TEM de estar presentes para a regra ser avaliada. E a suficiencia de evidencia, declarada e nao inferida.';


-- -----------------------------------------------------------------------------
-- 2. trafego_evidencia — o snapshot em que a decisao se apoia
-- -----------------------------------------------------------------------------
-- REGRA A por construcao: `colhida_em` e NOT NULL e denomina TODAS as medidas
-- desta linha. Nao ha como gravar um numero aqui sem a hora em que ele foi
-- lido — o que na v9 exige um gatilho, aqui e estrutura.
--
-- REGRA B em cada metrica: nenhuma tem DEFAULT. `conversoes` NULA e "nao
-- consegui medir"; zero e "medi e nao houve". As duas levam a decisoes opostas
-- sobre pausar uma campanha, e achata-las e como uma automacao de midia mata
-- uma campanha que estava funcionando.
CREATE TABLE public.trafego_evidencia (
  evidencia_id  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  regra_id      uuid        NOT NULL REFERENCES public.trafego_regra_otimizacao (regra_id)
                            ON DELETE RESTRICT,

  plataforma    text        NOT NULL,
  conta_externa text        NOT NULL,
  -- A instancia (ADR-02). NULL quando a evidencia e da CONTA inteira — regra de
  -- orcamento de conta nao tem campanha.
  volc_campaign_id text     REFERENCES public.trafego_campanha (volc_campaign_id)
                            ON DELETE RESTRICT,

  janela_inicio date        NOT NULL,
  janela_fim    date        NOT NULL,
  colhida_em    timestamptz NOT NULL,
  origem        text        NOT NULL,

  impressoes              bigint,
  cliques                 bigint,
  custo_micros            bigint,
  conversoes              numeric(14,2),
  valor_conversao_micros  bigint,
  moeda                   text,
  metricas                jsonb NOT NULL DEFAULT '{}'::jsonb,

  -- SUFICIENCIA — tres estados, e o do meio e o que importa. `nao_avaliada` nao
  -- e sinonimo de `insuficiente`: a primeira diz "ninguem olhou", a segunda diz
  -- "olhei e falta". Nenhuma das duas autoriza uma proposta, e o gatilho
  -- `trafego_proposta_respeita_regra` recusa as duas — mas so a segunda diz o
  -- que falta em `faltantes`.
  suficiencia          text NOT NULL DEFAULT 'nao_avaliada',
  suficiencia_motivo   text,
  suficiencia_em       timestamptz,
  faltantes            text[],

  CONSTRAINT trafego_evidencia_plataforma_conhecida
    CHECK (plataforma IN ('GOOGLE_ADS', 'META_ADS')),
  CONSTRAINT trafego_evidencia_conta_valida
    CHECK (btrim(conta_externa) <> ''
           AND (plataforma <> 'GOOGLE_ADS' OR conta_externa ~ '^[0-9]{6,12}$')),
  CONSTRAINT trafego_evidencia_origem_nao_vazia CHECK (btrim(origem) <> ''),
  CONSTRAINT trafego_evidencia_janela_coerente CHECK (janela_fim >= janela_inicio),
  CONSTRAINT trafego_evidencia_numeros_nao_negativos
    CHECK (coalesce(impressoes, 0) >= 0 AND coalesce(cliques, 0) >= 0
           AND coalesce(custo_micros, 0) >= 0 AND coalesce(conversoes, 0) >= 0
           AND coalesce(valor_conversao_micros, 0) >= 0),
  CONSTRAINT trafego_evidencia_moeda_iso
    CHECK (moeda IS NULL OR moeda ~ '^[A-Z]{3}$'),
  -- REGRA A no dinheiro: custo sem moeda e um numero que ninguem sabe ler, e a
  -- proposta calcularia um delta em uma unidade e o compararia com o teto em
  -- outra.
  CONSTRAINT trafego_evidencia_dinheiro_sem_moeda
    CHECK ((custo_micros IS NULL AND valor_conversao_micros IS NULL)
           OR moeda IS NOT NULL),
  CONSTRAINT trafego_evidencia_metricas_e_objeto
    CHECK (jsonb_typeof(metricas) = 'object'),
  CONSTRAINT trafego_evidencia_suficiencia_conhecida
    CHECK (suficiencia IN ('suficiente', 'insuficiente', 'nao_avaliada')),
  CONSTRAINT trafego_evidencia_suficiencia_coerente
    CHECK (
      (suficiencia = 'nao_avaliada' AND suficiencia_em IS NULL)
      OR (suficiencia <> 'nao_avaliada' AND suficiencia_em IS NOT NULL)
    ),
  -- Quem reprova diz o que falta. Um `insuficiente` mudo obriga o operador a
  -- reproduzir a avaliacao a mao para descobrir a razao.
  CONSTRAINT trafego_evidencia_insuficiente_tem_motivo
    CHECK (suficiencia <> 'insuficiente'
           OR (btrim(coalesce(suficiencia_motivo, '')) <> ''
               AND array_length(faltantes, 1) >= 1))
);

CREATE INDEX trafego_evidencia_campanha_ix
  ON public.trafego_evidencia (volc_campaign_id, colhida_em DESC)
  WHERE volc_campaign_id IS NOT NULL;
CREATE INDEX trafego_evidencia_regra_ix
  ON public.trafego_evidencia (regra_id, colhida_em DESC);
CREATE INDEX trafego_evidencia_conta_ix
  ON public.trafego_evidencia (plataforma, conta_externa, colhida_em DESC);

COMMENT ON TABLE public.trafego_evidencia IS
  'O snapshot em que a decisao se apoia. `colhida_em` NOT NULL denomina todas as medidas — regra A por estrutura, nao por gatilho.';
COMMENT ON COLUMN public.trafego_evidencia.conversoes IS
  'NULL = nao foi possivel medir. 0 = medido e nao houve. Sem DEFAULT, de proposito.';


-- -----------------------------------------------------------------------------
-- 3. trafego_diagnostico — o que foi detectado, e por que
-- -----------------------------------------------------------------------------
-- `explicacao` e NOT NULL pela mesma razao que `trafego_vinculo.regra` e:
-- "cada sugestao declara qual regra casou — sugestao sem regra visivel nao e
-- oferecida" (SPEC 3.2). Se a explicacao nao viaja ate aqui, o humano aprova
-- uma caixa-preta, e a aprovacao humana vira carimbo.
CREATE TABLE public.trafego_diagnostico (
  diagnostico_id uuid       PRIMARY KEY DEFAULT gen_random_uuid(),
  evidencia_id  uuid        NOT NULL REFERENCES public.trafego_evidencia (evidencia_id)
                            ON DELETE RESTRICT,
  regra_id      uuid        NOT NULL REFERENCES public.trafego_regra_otimizacao (regra_id)
                            ON DELETE RESTRICT,

  detectado_em  timestamptz NOT NULL,
  produtor      text        NOT NULL,

  sintoma       text        NOT NULL,
  causa_provavel text,
  explicacao    text        NOT NULL,
  -- NULL = nao foi calculada, e nao "zero de confianca". Zero de confianca seria
  -- uma afirmacao forte; ausencia e ausencia.
  confianca     numeric(4,3),
  severidade    text,

  CONSTRAINT trafego_diagnostico_produtor_nao_vazio CHECK (btrim(produtor) <> ''),
  CONSTRAINT trafego_diagnostico_sintoma_nao_vazio  CHECK (btrim(sintoma) <> ''),
  CONSTRAINT trafego_diagnostico_explicacao_nao_vazia
    CHECK (btrim(explicacao) <> ''),
  CONSTRAINT trafego_diagnostico_confianca_valida
    CHECK (confianca IS NULL OR (confianca > 0 AND confianca <= 1)),
  CONSTRAINT trafego_diagnostico_severidade_conhecida
    CHECK (severidade IS NULL OR severidade IN ('baixa', 'media', 'alta'))
);

CREATE INDEX trafego_diagnostico_evidencia_ix
  ON public.trafego_diagnostico (evidencia_id);
CREATE INDEX trafego_diagnostico_regra_ix
  ON public.trafego_diagnostico (regra_id, detectado_em DESC);

COMMENT ON TABLE public.trafego_diagnostico IS
  'Append-only. `explicacao` NOT NULL: sem ela o humano aprova uma caixa-preta e a aprovacao vira carimbo.';


-- -----------------------------------------------------------------------------
-- 4. trafego_proposta — o diff, em DUAS colunas
-- -----------------------------------------------------------------------------
-- `valor_atual` e `valor_proposto` sao colunas separadas, e nunca a mesma
-- sobrescrita (regra D). Sem as duas nao existe diff, e sem diff nao existe
-- aprovacao informada — o humano estaria autorizando um resultado, nao uma
-- mudanca.
--
-- `valor_atual_lido_em` e a coluna menos obvia e uma das mais importantes:
-- ela diz DE QUANDO e o "antes". Uma proposta cujo antes tem tres semanas
-- propoe mudar uma coisa que ja mudou, e o gatilho a recusa contra o
-- `frescor_maximo_horas` da regra.
CREATE TABLE public.trafego_proposta (
  proposta_id    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  diagnostico_id uuid        NOT NULL REFERENCES public.trafego_diagnostico (diagnostico_id)
                             ON DELETE RESTRICT,
  -- A VERSAO EXATA da regra que produziu esta proposta. Nao a chave: a chave
  -- aponta para "a regra", e "a regra" muda.
  regra_id       uuid        NOT NULL REFERENCES public.trafego_regra_otimizacao (regra_id)
                             ON DELETE RESTRICT,

  volc_campaign_id text      REFERENCES public.trafego_campanha (volc_campaign_id)
                             ON DELETE RESTRICT,
  alvo_nivel     text        NOT NULL,
  alvo_id_externo text,
  -- A chave do cooldown. Denormalizada de proposito: o gatilho de carencia
  -- precisa dela sem um JOIN que atravesse quatro tabelas a cada INSERT.
  alvo_chave     text        NOT NULL,

  operacao       text        NOT NULL,

  valor_atual         jsonb       NOT NULL,
  valor_atual_lido_em timestamptz NOT NULL,
  valor_proposto      jsonb       NOT NULL,

  delta_pct              numeric(8,3),
  delta_absoluto_micros  bigint,
  moeda                  text,

  -- A chave de idempotencia, mesma doutrina da v10_01: derivada do conteudo,
  -- unica, e e por ela que uma aplicacao interrompida se reconhece na retomada.
  idempotency_key text       NOT NULL,

  estado         text        NOT NULL DEFAULT 'aguardando_aprovacao',
  criada_em      timestamptz NOT NULL DEFAULT now(),
  criada_por     text        NOT NULL,
  -- Proposta tem PRAZO. Aplicar uma proposta de uma semana atras e aplicar uma
  -- decisao a um mundo que ja mudou — e o mercado de leilao muda todo dia.
  expira_em      timestamptz NOT NULL,

  CONSTRAINT trafego_proposta_alvo_conhecido
    CHECK (alvo_nivel IN ('conta', 'campanha', 'grupo', 'conjunto',
                          'asset_group', 'anuncio', 'keyword')),
  CONSTRAINT trafego_proposta_alvo_chave_nao_vazia CHECK (btrim(alvo_chave) <> ''),
  CONSTRAINT trafego_proposta_operacao_nao_vazia   CHECK (btrim(operacao) <> ''),
  CONSTRAINT trafego_proposta_criador_nao_vazio    CHECK (btrim(criada_por) <> ''),
  CONSTRAINT trafego_proposta_chave_valida
    CHECK (idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$'),
  CONSTRAINT trafego_proposta_valores_sao_objetos
    CHECK (jsonb_typeof(valor_atual) = 'object'
           AND jsonb_typeof(valor_proposto) = 'object'),
  -- Um diff que nao difere nao e proposta: e uma linha que consome aprovacao
  -- humana para nao mudar nada.
  CONSTRAINT trafego_proposta_diff_difere
    CHECK (valor_atual IS DISTINCT FROM valor_proposto),
  CONSTRAINT trafego_proposta_moeda_iso
    CHECK (moeda IS NULL OR moeda ~ '^[A-Z]{3}$'),
  CONSTRAINT trafego_proposta_delta_absoluto_com_moeda
    CHECK (delta_absoluto_micros IS NULL OR moeda IS NOT NULL),
  CONSTRAINT trafego_proposta_prazo_futuro CHECK (expira_em > criada_em),
  CONSTRAINT trafego_proposta_estado_conhecido
    CHECK (estado IN ('aguardando_aprovacao', 'aprovada', 'recusada',
                      'expirada', 'aplicada', 'revertida', 'cancelada'))
);

CREATE UNIQUE INDEX trafego_proposta_chave_ux
  ON public.trafego_proposta (idempotency_key);
CREATE INDEX trafego_proposta_estado_ix
  ON public.trafego_proposta (estado, criada_em DESC);
CREATE INDEX trafego_proposta_campanha_ix
  ON public.trafego_proposta (volc_campaign_id, criada_em DESC)
  WHERE volc_campaign_id IS NOT NULL;
CREATE INDEX trafego_proposta_alvo_ix
  ON public.trafego_proposta (alvo_chave, criada_em DESC);

COMMENT ON TABLE public.trafego_proposta IS
  'O diff em duas colunas (valor_atual x valor_proposto) + de quando e o "antes". Recusada no INSERT se estourar limite, teto, frescor ou suficiencia da regra.';
COMMENT ON COLUMN public.trafego_proposta.valor_atual_lido_em IS
  'De quando e o "antes" do diff. Um antes velho propoe mudar uma coisa que ja mudou.';


-- -----------------------------------------------------------------------------
-- 5. trafego_aprovacao — a decisao humana, com o diff que foi de fato mostrado
-- -----------------------------------------------------------------------------
-- Tabela separada, e nao uma coluna na proposta, por dois motivos:
--   · append-only de verdade: uma coluna mutavel na proposta poderia ser
--     reescrita, e "quem autorizou este gasto" e a pergunta mais cara do
--     sistema;
--   · `diff_apresentado` guarda O QUE FOI MOSTRADO, e nao o que estava no
--     banco. Se a tela renderizou errado, a diferenca fica registrada — e sem
--     ela, uma disputa sobre "eu nao aprovei isso" nao tem como ser resolvida.
CREATE TABLE public.trafego_aprovacao (
  aprovacao_id  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  proposta_id   uuid        NOT NULL REFERENCES public.trafego_proposta (proposta_id)
                            ON DELETE RESTRICT,

  decisao       text        NOT NULL,
  decidida_por  text        NOT NULL,
  decidida_em   timestamptz NOT NULL DEFAULT now(),
  observacao    text,
  diff_apresentado jsonb    NOT NULL,

  CONSTRAINT trafego_aprovacao_decisao_conhecida
    CHECK (decisao IN ('aprovada', 'recusada')),
  CONSTRAINT trafego_aprovacao_decisor_nao_vazio CHECK (btrim(decidida_por) <> ''),
  CONSTRAINT trafego_aprovacao_diff_e_objeto
    CHECK (jsonb_typeof(diff_apresentado) = 'object'),
  -- Recusa sem motivo nao ensina nada a quem escreveu a regra, e a regra
  -- continua propondo a mesma coisa amanha.
  CONSTRAINT trafego_aprovacao_recusa_tem_motivo
    CHECK (decisao <> 'recusada' OR btrim(coalesce(observacao, '')) <> '')
);

-- UMA decisao por proposta. Duas seriam duas autorizacoes contraditorias sobre
-- o mesmo gasto, e o executor teria de escolher qual obedecer.
CREATE UNIQUE INDEX trafego_aprovacao_proposta_ux
  ON public.trafego_aprovacao (proposta_id);

COMMENT ON TABLE public.trafego_aprovacao IS
  'A decisao humana, append-only. `diff_apresentado` guarda o que foi MOSTRADO, nao o que estava no banco.';


-- -----------------------------------------------------------------------------
-- 6. trafego_aplicacao — a escrita, com o mesmo protocolo do recibo da v10_01
-- -----------------------------------------------------------------------------
--   1. INSERT com `desfecho = 'em_voo'`, `respondido_em` NULO. COMMIT.
--   2. A chamada sai.
--   3. Resposta -> UPDATE. Processo morre -> a linha FICA em `em_voo`.
--
-- `valor_anterior` e capturado AQUI, no envio, e nao no rollback: no rollback
-- ele ja teria sido sobrescrito pela propria aplicacao que se quer desfazer.
CREATE TABLE public.trafego_aplicacao (
  aplicacao_id  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  proposta_id   uuid        NOT NULL REFERENCES public.trafego_proposta (proposta_id)
                            ON DELETE RESTRICT,
  -- ⚠️ TRAVA 1 DE T1: NOT NULL com FK. Nao existe aplicacao sem uma linha de
  -- aprovacao humana apontada. A trava 2 (a decisao tem de ser `aprovada`, e
  -- daquela proposta) esta no gatilho.
  aprovacao_id  uuid        NOT NULL REFERENCES public.trafego_aprovacao (aprovacao_id)
                            ON DELETE RESTRICT,

  idempotency_key text      NOT NULL,
  tentativa     integer     NOT NULL,

  enviado_em    timestamptz NOT NULL,
  respondido_em timestamptz,
  desfecho      text        NOT NULL DEFAULT 'em_voo',

  valor_anterior jsonb      NOT NULL,

  request_id    text,
  resposta_bruta jsonb,
  erro_codigo   text,
  erro_mensagem text,

  CONSTRAINT trafego_aplicacao_chave_valida
    CHECK (idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$'),
  CONSTRAINT trafego_aplicacao_tentativa_positiva CHECK (tentativa >= 1),
  CONSTRAINT trafego_aplicacao_valor_anterior_e_objeto
    CHECK (jsonb_typeof(valor_anterior) = 'object'),
  CONSTRAINT trafego_aplicacao_desfecho_conhecido
    CHECK (desfecho IN ('em_voo', 'sucesso', 'erro', 'sem_resposta')),
  CONSTRAINT trafego_aplicacao_resposta_coerente
    CHECK (
      (desfecho = 'em_voo' AND respondido_em IS NULL)
      OR (desfecho <> 'em_voo' AND respondido_em IS NOT NULL)
    ),
  CONSTRAINT trafego_aplicacao_erro_tem_mensagem
    CHECK (desfecho <> 'erro' OR btrim(coalesce(erro_mensagem, '')) <> ''),
  CONSTRAINT trafego_aplicacao_resposta_nao_anterior
    CHECK (respondido_em IS NULL OR respondido_em >= enviado_em)
);

CREATE UNIQUE INDEX trafego_aplicacao_tentativa_ux
  ON public.trafego_aplicacao (proposta_id, tentativa);
-- ⚠️ NO MAXIMO UM SUCESSO POR CHAVE. Mesma defesa do recibo da v10_01: um
-- executor com defeito que reenviasse nao consegue registrar o segundo sucesso;
-- a transacao aborta e alguem olha, em vez de o orcamento ser dobrado duas vezes.
CREATE UNIQUE INDEX trafego_aplicacao_sucesso_unico_ux
  ON public.trafego_aplicacao (idempotency_key)
  WHERE desfecho = 'sucesso';
CREATE INDEX trafego_aplicacao_em_voo_ix
  ON public.trafego_aplicacao (enviado_em)
  WHERE desfecho = 'em_voo';

COMMENT ON TABLE public.trafego_aplicacao IS
  'Uma linha por tentativa, criada ANTES da chamada. Exige aprovacao humana por FK e por gatilho. `valor_anterior` e capturado no envio.';


-- -----------------------------------------------------------------------------
-- 7. trafego_acompanhamento — verificacao imediata e acompanhamento posterior
-- -----------------------------------------------------------------------------
-- Dois momentos, e nao um: `verificacao` pergunta "a mudanca entrou?" (minutos
-- depois) e `acompanhamento` pergunta "a mudanca ajudou?" (dias depois, contado
-- o atraso de conversao da regra). Juntar os dois faria a primeira esperar a
-- janela da segunda — e uma alteracao que nao entrou ficaria dias sem ser
-- notada.
--
-- `confere` e tri-estado, como o `achou` da v10_01: NULL = nao consegui ler, e
-- NULL nao autoriza nada.
CREATE TABLE public.trafego_acompanhamento (
  acompanhamento_id uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
  aplicacao_id  uuid        NOT NULL REFERENCES public.trafego_aplicacao (aplicacao_id)
                            ON DELETE RESTRICT,

  momento       text        NOT NULL,
  observado_em  timestamptz NOT NULL,
  observado_por text        NOT NULL,

  valor_observado jsonb,
  confere       boolean,
  motivo        text,

  janela_inicio date,
  janela_fim    date,
  impressoes    bigint,
  cliques       bigint,
  custo_micros  bigint,
  conversoes    numeric(14,2),
  moeda         text,

  -- ⚠️ Numero sem o periodo que ele mede nao e medida, e um numero.
  --
  -- As quatro metricas eram anulaveis ao lado de uma janela anulavel, entao
  -- "1.200 cliques" podia entrar sem dizer 1.200 cliques EM QUE. Comparar duas
  -- linhas dessas — que e exatamente o que acompanhar uma atuacao significa —
  -- daria uma diferenca sobre periodos possivelmente diferentes, com cara de
  -- variacao. E a mesma doutrina que a v9 ja impoe no espelho do inventario:
  -- entrega com numero e sem carimbo e recusada.
  CONSTRAINT trafego_acompanhamento_metrica_tem_janela
    CHECK (
      (impressoes IS NULL AND cliques IS NULL
       AND custo_micros IS NULL AND conversoes IS NULL)
      OR (janela_inicio IS NOT NULL AND janela_fim IS NOT NULL)
    ),
  -- (coerencia da janela e custo-com-moeda ja existem mais abaixo, em
  --  `trafego_acompanhamento_janela_coerente` e `..._custo_sem_moeda`. O que
  --  faltava era so a exigencia da janela QUANDO ha metrica.)

  veredito      text,
  -- Este acompanhamento disparou a condicao de rollback declarada na regra?
  -- Booleano NOT NULL com DEFAULT false porque ele e uma CONCLUSAO NOSSA sobre
  -- a linha, sempre conhecida no momento em que a linha e escrita — nao e
  -- medida externa que possa ter falhado.
  gatilho_de_rollback boolean NOT NULL DEFAULT false,

  CONSTRAINT trafego_acompanhamento_momento_conhecido
    CHECK (momento IN ('verificacao', 'acompanhamento')),
  CONSTRAINT trafego_acompanhamento_observador_nao_vazio
    CHECK (btrim(observado_por) <> ''),
  CONSTRAINT trafego_acompanhamento_indeterminado_tem_motivo
    CHECK (confere IS NOT NULL OR btrim(coalesce(motivo, '')) <> ''),
  CONSTRAINT trafego_acompanhamento_numeros_nao_negativos
    CHECK (coalesce(impressoes, 0) >= 0 AND coalesce(cliques, 0) >= 0
           AND coalesce(custo_micros, 0) >= 0 AND coalesce(conversoes, 0) >= 0),
  CONSTRAINT trafego_acompanhamento_moeda_iso
    CHECK (moeda IS NULL OR moeda ~ '^[A-Z]{3}$'),
  CONSTRAINT trafego_acompanhamento_custo_sem_moeda
    CHECK (custo_micros IS NULL OR moeda IS NOT NULL),
  CONSTRAINT trafego_acompanhamento_janela_coerente
    CHECK (janela_inicio IS NULL OR janela_fim IS NULL OR janela_fim >= janela_inicio),
  CONSTRAINT trafego_acompanhamento_veredito_conhecido
    CHECK (veredito IS NULL
           OR veredito IN ('melhorou', 'piorou', 'indiferente', 'indeterminado')),
  -- Nao se dispara rollback sem dizer o que se observou. Um gatilho sem
  -- veredito seria uma reversao sem causa registrada.
  CONSTRAINT trafego_acompanhamento_gatilho_tem_veredito
    CHECK (NOT gatilho_de_rollback OR veredito IS NOT NULL)
);

CREATE INDEX trafego_acompanhamento_aplicacao_ix
  ON public.trafego_acompanhamento (aplicacao_id, observado_em DESC);
CREATE INDEX trafego_acompanhamento_gatilho_ix
  ON public.trafego_acompanhamento (aplicacao_id)
  WHERE gatilho_de_rollback;

COMMENT ON TABLE public.trafego_acompanhamento IS
  'Append-only. `verificacao` = a mudanca entrou? `acompanhamento` = ela ajudou? `confere` NULL = nao consegui ler, e nao autoriza nada.';


-- -----------------------------------------------------------------------------
-- 8. trafego_atuacao_reversao — desfazer uma aplicacao
-- -----------------------------------------------------------------------------
CREATE TABLE public.trafego_atuacao_reversao (
  reversao_id   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  aplicacao_id  uuid        NOT NULL REFERENCES public.trafego_aplicacao (aplicacao_id)
                            ON DELETE RESTRICT,
  -- Qual observacao disparou. NULL quando a reversao e pedido humano direto —
  -- que e legitimo e nao precisa de gatilho automatico para existir.
  acompanhamento_id uuid    REFERENCES public.trafego_acompanhamento (acompanhamento_id)
                            ON DELETE RESTRICT,

  motivo        text        NOT NULL,
  -- 'humano:<quem>' ou 'regra:<chave>@<versao>'. Saber QUEM mandou desfazer e
  -- tao importante quanto saber quem mandou fazer.
  acionado_por  text        NOT NULL,
  acionado_em   timestamptz NOT NULL DEFAULT now(),

  valor_restaurado jsonb    NOT NULL,

  desfecho      text        NOT NULL DEFAULT 'pendente',
  executado_em  timestamptz,
  request_id    text,
  erro_mensagem text,

  CONSTRAINT trafego_reversao_motivo_nao_vazio  CHECK (btrim(motivo) <> ''),
  CONSTRAINT trafego_reversao_acionador_nao_vazio CHECK (btrim(acionado_por) <> ''),
  CONSTRAINT trafego_reversao_valor_e_objeto
    CHECK (jsonb_typeof(valor_restaurado) = 'object'),
  CONSTRAINT trafego_reversao_desfecho_conhecido
    CHECK (desfecho IN ('pendente', 'sucesso', 'erro', 'sem_resposta')),
  CONSTRAINT trafego_reversao_desfecho_coerente
    CHECK (
      (desfecho = 'pendente' AND executado_em IS NULL)
      OR (desfecho <> 'pendente' AND executado_em IS NOT NULL)
    ),
  CONSTRAINT trafego_reversao_erro_tem_mensagem
    CHECK (desfecho <> 'erro' OR btrim(coalesce(erro_mensagem, '')) <> '')
);

-- Uma reversao por aplicacao. Duas seriam duas ordens contraditorias sobre o
-- mesmo valor, e a segunda restauraria por cima do que a primeira restaurou.
CREATE UNIQUE INDEX trafego_reversao_aplicacao_ux
  ON public.trafego_atuacao_reversao (aplicacao_id);

COMMENT ON TABLE public.trafego_atuacao_reversao IS
  'O desfazer de uma aplicacao. Uma por aplicacao. `valor_restaurado` vem de trafego_aplicacao.valor_anterior, capturado no envio.';


-- -----------------------------------------------------------------------------
-- 9. trafego_cooldown — a carencia por (regra, alvo), escrita por gatilho
-- -----------------------------------------------------------------------------
-- Sem esta tabela, `cooldown_horas` seria um numero que ninguem aplica. Com
-- ela, o gatilho `trafego_aplicacao_respeita_cooldown` RECUSA a aplicacao
-- enquanto a carencia estiver de pe.
--
-- A carencia e por `regra_chave` e nao por `regra_id`: publicar a v2 de uma
-- regra nao pode zerar a carencia que a v1 acabou de impor sobre a mesma
-- campanha — seria a rota mais facil para uma regra brigar consigo mesma.
CREATE TABLE public.trafego_cooldown (
  cooldown_id   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  regra_chave   text        NOT NULL,
  alvo_chave    text        NOT NULL,
  aplicacao_id  uuid        REFERENCES public.trafego_aplicacao (aplicacao_id)
                            ON DELETE RESTRICT,

  iniciado_em   timestamptz NOT NULL,
  expira_em     timestamptz NOT NULL,

  CONSTRAINT trafego_cooldown_regra_nao_vazia CHECK (btrim(regra_chave) <> ''),
  CONSTRAINT trafego_cooldown_alvo_nao_vazio  CHECK (btrim(alvo_chave) <> ''),
  CONSTRAINT trafego_cooldown_prazo_futuro    CHECK (expira_em > iniciado_em)
);

-- ⚠️ NAO ha indice unico parcial com `now()` aqui, e a ausencia e proposital:
-- um predicado de indice tem de ser IMUTAVEL, e `now()` nao e. A unicidade da
-- carencia ativa e imposta pelo gatilho de aplicacao, que consulta este indice.
CREATE INDEX trafego_cooldown_ativo_ix
  ON public.trafego_cooldown (regra_chave, alvo_chave, expira_em DESC);

COMMENT ON TABLE public.trafego_cooldown IS
  'A carencia por (regra_chave, alvo_chave). Escrita por gatilho quando uma aplicacao fecha em sucesso — carencia que depende de alguem lembrar nao e carencia.';


-- -----------------------------------------------------------------------------
-- 10. GATILHOS — o que so o banco consegue garantir
-- -----------------------------------------------------------------------------

-- 10.1 Regra publicada e imutavel; so a aposentadoria muda, e uma vez.
CREATE OR REPLACE FUNCTION public.trafego_regra_so_aposenta()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION
      'trafego_regra_otimizacao: DELETE recusado. Toda proposta cita o regra_id que a produziu; apagar a regra apaga a explicacao de um gasto.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.regra_id IS DISTINCT FROM OLD.regra_id
     OR NEW.chave  IS DISTINCT FROM OLD.chave
     OR NEW.versao IS DISTINCT FROM OLD.versao
     OR NEW.objetivo IS DISTINCT FROM OLD.objetivo
     OR NEW.plataformas IS DISTINCT FROM OLD.plataformas
     OR NEW.canais      IS DISTINCT FROM OLD.canais
     OR NEW.janela_minima_dias    IS DISTINCT FROM OLD.janela_minima_dias
     OR NEW.atraso_conversao_dias IS DISTINCT FROM OLD.atraso_conversao_dias
     OR NEW.frescor_maximo_horas  IS DISTINCT FROM OLD.frescor_maximo_horas
     OR NEW.amostra_minima_cliques    IS DISTINCT FROM OLD.amostra_minima_cliques
     OR NEW.amostra_minima_impressoes IS DISTINCT FROM OLD.amostra_minima_impressoes
     OR NEW.amostra_minima_conversoes IS DISTINCT FROM OLD.amostra_minima_conversoes
     OR NEW.dados_obrigatorios IS DISTINCT FROM OLD.dados_obrigatorios
     OR NEW.teto_orcamento_micros IS DISTINCT FROM OLD.teto_orcamento_micros
     OR NEW.teto_orcamento_moeda  IS DISTINCT FROM OLD.teto_orcamento_moeda
     OR NEW.limite_alteracao_pct  IS DISTINCT FROM OLD.limite_alteracao_pct
     OR NEW.limite_alteracao_absoluto_micros
          IS DISTINCT FROM OLD.limite_alteracao_absoluto_micros
     OR NEW.cooldown_horas     IS DISTINCT FROM OLD.cooldown_horas
     OR NEW.confianca_minima   IS DISTINCT FROM OLD.confianca_minima
     OR NEW.condicao_rollback  IS DISTINCT FROM OLD.condicao_rollback
     OR NEW.rollback_janela_horas IS DISTINCT FROM OLD.rollback_janela_horas
     OR NEW.nivel_autonomia    IS DISTINCT FROM OLD.nivel_autonomia
     OR NEW.deteccao IS DISTINCT FROM OLD.deteccao
     OR NEW.acao     IS DISTINCT FROM OLD.acao
     OR NEW.declarada_por IS DISTINCT FROM OLD.declarada_por
     OR NEW.declarada_em  IS DISTINCT FROM OLD.declarada_em
  THEN
    RAISE EXCEPTION
      'trafego_regra_otimizacao: versao publicada e imutavel. Para mudar a regra, publique (chave, versao+1) e aposente esta — reescrever a linha mudaria retroativamente por que uma verba foi mexida.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF OLD.vigente_desde IS NOT NULL
     AND NEW.vigente_desde IS DISTINCT FROM OLD.vigente_desde THEN
    RAISE EXCEPTION
      'trafego_regra_otimizacao: `vigente_desde` ja foi declarada (%); a data em que a regra passou a valer nao se reescreve.',
      OLD.vigente_desde
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF OLD.retirada_em IS NOT NULL
     AND (NEW.retirada_em IS DISTINCT FROM OLD.retirada_em
          OR NEW.retirada_por IS DISTINCT FROM OLD.retirada_por
          OR NEW.retirada_motivo IS DISTINCT FROM OLD.retirada_motivo) THEN
    RAISE EXCEPTION
      'trafego_regra_otimizacao: esta versao ja foi aposentada em % por %; o registro nao se reescreve.',
      OLD.retirada_em, OLD.retirada_por
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_regra_so_aposenta
  BEFORE UPDATE OR DELETE ON public.trafego_regra_otimizacao
  FOR EACH ROW EXECUTE FUNCTION public.trafego_regra_so_aposenta();


-- 10.2 ⚠️ A PROPOSTA RESPEITA A REGRA — a trava 4 de T1.
--
-- CHECK nao alcanca outra tabela; este gatilho alcanca. Ele recusa, no INSERT,
-- as CINCO maneiras conhecidas de uma proposta ser perigosa:
--
--   1. a evidencia nao foi declarada SUFICIENTE     -> decisao sem base
--   2. a evidencia esta mais velha que o frescor    -> decidir hoje com dado de
--      maximo declarado pela regra                     tres semanas atras
--   3. o delta percentual estoura o limite          -> "dobrar o orcamento" numa
--                                                      regra que permite +20%
--   4. o delta absoluto estoura o limite            -> idem, em dinheiro
--   5. o valor proposto estoura o teto de orcamento -> o limite absoluto de
--                                                      quanto se pode gastar
--
-- Cada uma delas ja aconteceu em alguma automacao de midia do mundo real. A
-- diferenca entre "aconteceu e alguem viu" e "aconteceu e a verba sumiu" e
-- estar aqui, e nao num `if` do executor.
CREATE OR REPLACE FUNCTION public.trafego_proposta_respeita_regra()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
DECLARE
  r        public.trafego_regra_otimizacao%ROWTYPE;
  ev       public.trafego_evidencia%ROWTYPE;
  proposto bigint;
  idade    interval;
BEGIN
  SELECT * INTO r FROM public.trafego_regra_otimizacao
   WHERE regra_id = NEW.regra_id;

  SELECT e.* INTO ev
    FROM public.trafego_evidencia e
    JOIN public.trafego_diagnostico d ON d.evidencia_id = e.evidencia_id
   WHERE d.diagnostico_id = NEW.diagnostico_id;

  -- (1) SUFICIENCIA DE EVIDENCIA. `nao_avaliada` cai aqui junto com
  -- `insuficiente`, e de proposito: "ninguem olhou" nao e melhor que "olhei e
  -- falta" na hora de autorizar um gasto.
  IF ev.suficiencia IS DISTINCT FROM 'suficiente' THEN
    RAISE EXCEPTION
      'trafego_proposta: a evidencia % esta como "%" — proposta exige evidencia declarada suficiente. Avalie a suficiencia contra os dados_obrigatorios da regra antes de propor.',
      ev.evidencia_id, ev.suficiencia
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- ⚠️ TRAVA 0 — a proposta tem de falar da MESMA campanha que a evidencia.
  --
  -- Ela roda DEPOIS da checagem de suficiencia de proposito: quando o
  -- diagnostico citado nao existe, `ev` volta inteiramente nulo, e a checagem
  -- de suficiencia ja recusa com a mensagem certa. Rodando antes, esta trava
  -- dizia "a evidencia <NULL> nao mediu campanha nenhuma", que manda procurar
  -- o defeito no lugar errado.
  --
  -- Sem esta comparacao, o diagnostico da campanha A autorizava mudanca na
  -- campanha B, inclusive em OUTRA CONTA do mesmo MCC: as travas de baixo
  -- conferem suficiencia, frescor e limites, e nenhuma delas sabe DE QUE
  -- campanha se trata. Pior, `trafego_proposta_painel` mostra a explicacao do
  -- diagnostico ao lado do alvo da proposta — o humano aprova lendo "cliques
  -- 120, custo 45 BRL" como justificativa de uma campanha que nao foi medida.
  --
  -- `ev.volc_campaign_id` nulo e legitimo: e a evidencia de nivel CONTA. Nesse
  -- caso a proposta nao pode descer para nivel campanha, porque ninguem mediu
  -- aquela campanha em particular.
  IF ev.volc_campaign_id IS NOT NULL THEN
    IF NEW.volc_campaign_id IS DISTINCT FROM ev.volc_campaign_id THEN
      RAISE EXCEPTION
        'trafego_proposta: a evidencia e da campanha % e a proposta aponta para %. Uma medicao so autoriza mudanca no que ela mediu.',
        ev.volc_campaign_id, coalesce(NEW.volc_campaign_id, '(nenhuma)')
        USING ERRCODE = 'restrict_violation';
    END IF;
  ELSIF NEW.alvo_nivel = 'campanha' THEN
    RAISE EXCEPTION
      'trafego_proposta: a evidencia % nao mediu campanha nenhuma (volc_campaign_id nulo), entao ela nao sustenta uma proposta de nivel campanha.',
      ev.evidencia_id
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- E alvo_nivel = 'campanha' exige a campanha nomeada. `alvo_chave` e texto
  -- livre; sem esta linha, `alvo_nivel='campanha'` com volc_campaign_id nulo
  -- passava, e o alvo real ficava so na string.
  IF NEW.alvo_nivel = 'campanha' AND NEW.volc_campaign_id IS NULL THEN
    RAISE EXCEPTION
      'trafego_proposta: alvo_nivel = campanha exige volc_campaign_id. Alvo que existe so em alvo_chave nao e alvo, e uma anotacao.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- ⚠️ TRAVA 0b — a proposta nao escolhe contra qual regra sera medida.
  --
  -- Os limites conferidos abaixo sao os da regra que a PROPOSTA cita. Se ela
  -- puder citar uma regra diferente da que gerou o diagnostico, ela escolhe o
  -- proprio teto: basta apontar para uma regra permissiva. Verificado: uma
  -- proposta de +80% sobre um diagnostico da regra de limite 20% entrava sem
  -- erro citando outra regra de limite 90%.
  IF NEW.regra_id IS DISTINCT FROM (
       SELECT d.regra_id FROM public.trafego_diagnostico d
        WHERE d.diagnostico_id = NEW.diagnostico_id) THEN
    RAISE EXCEPTION
      'trafego_proposta: a regra citada nao e a regra do diagnostico. Os limites sao da regra, e escolher a regra depois do diagnostico e escolher o proprio teto.'
      USING ERRCODE = 'restrict_violation';
  END IF;


  -- (2) FRESCOR. O "antes" do diff tem de caber na janela que a regra declarou.
  idade := NEW.criada_em - NEW.valor_atual_lido_em;
  IF idade > make_interval(hours => r.frescor_maximo_horas) THEN
    RAISE EXCEPTION
      'trafego_proposta: o valor_atual foi lido ha % e a regra % aceita no maximo % h. Um "antes" velho propoe mudar uma coisa que ja mudou.',
      idade, r.chave, r.frescor_maximo_horas
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- (3) LIMITE PERCENTUAL DE ALTERACAO.
  -- ⚠️ TRAVA 4a — delta AUSENTE nao e delta dentro do limite.
  --
  -- As duas travas abaixo comecam com `IS NOT NULL`, entao uma proposta que
  -- simplesmente nao calculou o diff passava por elas em silencio. O limite de
  -- alteracao e o unico teto de tamanho que o T1 tem; deixa-lo furado por
  -- omissao e pior que nao te-lo, porque o registro diz que ele foi conferido.
  IF r.limite_alteracao_pct IS NOT NULL
     AND r.limite_alteracao_absoluto_micros IS NOT NULL
     AND NEW.delta_pct IS NULL AND NEW.delta_absoluto_micros IS NULL THEN
    RAISE EXCEPTION
      'trafego_proposta: a regra % declara limite de alteracao e a proposta nao trouxe delta nenhum. Sem o tamanho da mudanca nao da para dizer que ela cabe no teto.',
      r.chave
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF r.limite_alteracao_pct IS NOT NULL AND r.limite_alteracao_absoluto_micros IS NULL
     AND NEW.delta_pct IS NULL THEN
    RAISE EXCEPTION
      'trafego_proposta: a regra % declara limite percentual e a proposta nao trouxe delta_pct.',
      r.chave
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF r.limite_alteracao_absoluto_micros IS NOT NULL AND r.limite_alteracao_pct IS NULL
     AND NEW.delta_absoluto_micros IS NULL THEN
    RAISE EXCEPTION
      'trafego_proposta: a regra % declara limite absoluto e a proposta nao trouxe delta_absoluto_micros.',
      r.chave
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.delta_pct IS NOT NULL AND r.limite_alteracao_pct IS NOT NULL
     AND abs(NEW.delta_pct) > r.limite_alteracao_pct THEN
    RAISE EXCEPTION
      'trafego_proposta: alteracao de % por cento estoura o limite de % por cento da regra %.',
      NEW.delta_pct, r.limite_alteracao_pct, r.chave
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- (4) LIMITE ABSOLUTO DE ALTERACAO.
  IF NEW.delta_absoluto_micros IS NOT NULL
     AND r.limite_alteracao_absoluto_micros IS NOT NULL
     AND abs(NEW.delta_absoluto_micros) > r.limite_alteracao_absoluto_micros THEN
    RAISE EXCEPTION
      'trafego_proposta: alteracao de % micros estoura o limite absoluto de % micros da regra %.',
      NEW.delta_absoluto_micros, r.limite_alteracao_absoluto_micros, r.chave
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- (5) TETO DE ORCAMENTO. So olha a chave que o dominio usa para verba diaria;
  -- se ela nao estiver no valor proposto, nao ha teto a conferir — e inventar
  -- um seria recusar propostas legitimas de lance, pausa ou segmentacao.
  IF r.teto_orcamento_micros IS NOT NULL
     AND NEW.valor_proposto ? 'verba_diaria_micros'
     AND jsonb_typeof(NEW.valor_proposto -> 'verba_diaria_micros') = 'number' THEN
    proposto := (NEW.valor_proposto ->> 'verba_diaria_micros')::bigint;

    -- Moeda diferente do teto e comparacao invalida, e nao "provavelmente ok".
    -- Converter aqui inventaria uma taxa de cambio dentro de um gatilho.
    IF NEW.moeda IS NOT NULL AND NEW.moeda <> r.teto_orcamento_moeda THEN
      RAISE EXCEPTION
        'trafego_proposta: a proposta esta em % e o teto da regra % esta em % — nao ha como comparar sem inventar uma taxa de cambio.',
        NEW.moeda, r.chave, r.teto_orcamento_moeda
        USING ERRCODE = 'restrict_violation';
    END IF;

    IF proposto > r.teto_orcamento_micros THEN
      RAISE EXCEPTION
        'trafego_proposta: verba diaria proposta (% micros) estoura o teto de % micros da regra %.',
        proposto, r.teto_orcamento_micros, r.chave
        USING ERRCODE = 'restrict_violation';
    END IF;
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_proposta_respeita_regra
  BEFORE INSERT ON public.trafego_proposta
  FOR EACH ROW EXECUTE FUNCTION public.trafego_proposta_respeita_regra();

COMMENT ON FUNCTION public.trafego_proposta_respeita_regra() IS
  'Recusa proposta sem evidencia suficiente, com evidencia velha, ou que estoure limite de alteracao ou teto de orcamento da regra citada.';


-- 10.3 A proposta e imutavel: o diff nao se reescreve depois de mostrado.
CREATE OR REPLACE FUNCTION public.trafego_proposta_diff_imutavel()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION
      'trafego_proposta: DELETE recusado. Proposta abandonada recebe estado `cancelada`; apagar destroi o registro do que foi oferecido a um humano.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.proposta_id  IS DISTINCT FROM OLD.proposta_id
     OR NEW.diagnostico_id IS DISTINCT FROM OLD.diagnostico_id
     OR NEW.regra_id       IS DISTINCT FROM OLD.regra_id
     OR NEW.valor_atual    IS DISTINCT FROM OLD.valor_atual
     OR NEW.valor_proposto IS DISTINCT FROM OLD.valor_proposto
     OR NEW.valor_atual_lido_em IS DISTINCT FROM OLD.valor_atual_lido_em
     OR NEW.delta_pct      IS DISTINCT FROM OLD.delta_pct
     OR NEW.delta_absoluto_micros IS DISTINCT FROM OLD.delta_absoluto_micros
     OR NEW.operacao       IS DISTINCT FROM OLD.operacao
     OR NEW.alvo_chave     IS DISTINCT FROM OLD.alvo_chave
     OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
  THEN
    RAISE EXCEPTION
      'trafego_proposta: o diff e a regra citada sao imutaveis. Um humano aprovou ESTES valores; reescreve-los transformaria a aprovacao dele em autorizacao para outra coisa.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_proposta_diff_imutavel
  BEFORE UPDATE OR DELETE ON public.trafego_proposta
  FOR EACH ROW EXECUTE FUNCTION public.trafego_proposta_diff_imutavel();


-- 10.4 ⚠️ A APLICACAO EXIGE APROVACAO — a trava 2 de T1 — E RESPEITA O COOLDOWN.
CREATE OR REPLACE FUNCTION public.trafego_aplicacao_exige_aprovacao()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
DECLARE
  ap  public.trafego_aprovacao%ROWTYPE;
  pr  public.trafego_proposta%ROWTYPE;
  chave_regra text;
  ativa       timestamptz;
BEGIN
  SELECT * INTO ap FROM public.trafego_aprovacao WHERE aprovacao_id = NEW.aprovacao_id;
  SELECT * INTO pr FROM public.trafego_proposta  WHERE proposta_id  = NEW.proposta_id;

  -- A aprovacao apontada tem de ser DESTA proposta. Sem esta conferencia,
  -- bastaria apontar para qualquer aprovacao existente e a trava viraria
  -- decoracao — um `NOT NULL` que qualquer uuid valido satisfaz.
  IF ap.proposta_id IS DISTINCT FROM NEW.proposta_id THEN
    RAISE EXCEPTION
      'trafego_aplicacao: a aprovacao % e da proposta %, nao da %. Autorizacao nao e transferivel entre propostas.',
      NEW.aprovacao_id, ap.proposta_id, NEW.proposta_id
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF ap.decisao <> 'aprovada' THEN
    RAISE EXCEPTION
      'trafego_aplicacao: a decisao humana registrada foi "%". A maquina recomenda, o humano aplica (T1).',
      ap.decisao
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- PRAZO. Aplicar uma proposta vencida e aplicar uma decisao a um mundo que ja
  -- mudou — e o "antes" que o humano viu ja nao e o "antes" da conta.
  IF pr.expira_em <= NEW.enviado_em THEN
    RAISE EXCEPTION
      'trafego_aplicacao: a proposta expirou em % e o envio e de %. Recalcule o diff e peca aprovacao de novo.',
      pr.expira_em, NEW.enviado_em
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- COOLDOWN. Sem esta guarda, `cooldown_horas` seria um numero que ninguem
  -- aplica — e a regra brigaria consigo mesma a cada rodada, subindo e descendo
  -- o mesmo orcamento enquanto a plataforma reaprende do zero toda vez.
  SELECT r.chave INTO chave_regra
    FROM public.trafego_regra_otimizacao r WHERE r.regra_id = pr.regra_id;

  SELECT max(c.expira_em) INTO ativa
    FROM public.trafego_cooldown c
   WHERE c.regra_chave = chave_regra
     AND c.alvo_chave  = pr.alvo_chave
     AND c.expira_em   > NEW.enviado_em;

  IF ativa IS NOT NULL THEN
    RAISE EXCEPTION
      'trafego_aplicacao: a regra % esta em carencia sobre % ate %. Aplicar agora faria a regra brigar consigo mesma.',
      chave_regra, pr.alvo_chave, ativa
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_aplicacao_exige_aprovacao
  BEFORE INSERT ON public.trafego_aplicacao
  FOR EACH ROW EXECUTE FUNCTION public.trafego_aplicacao_exige_aprovacao();

COMMENT ON FUNCTION public.trafego_aplicacao_exige_aprovacao() IS
  'T1 em forma de gatilho: a aprovacao tem de ser daquela proposta e com decisao `aprovada`; a proposta nao pode estar vencida; a carencia da regra tem de ter passado.';


-- 10.5 A aplicacao fecha uma vez — mesmo protocolo do recibo da v10_01.
CREATE OR REPLACE FUNCTION public.trafego_aplicacao_fecha_uma_vez()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION
      'trafego_aplicacao: DELETE recusado. E a unica prova de que uma escrita saiu — inclusive a que nunca voltou.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.aplicacao_id IS DISTINCT FROM OLD.aplicacao_id
     OR NEW.proposta_id  IS DISTINCT FROM OLD.proposta_id
     OR NEW.aprovacao_id IS DISTINCT FROM OLD.aprovacao_id
     OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
     OR NEW.tentativa    IS DISTINCT FROM OLD.tentativa
     OR NEW.enviado_em   IS DISTINCT FROM OLD.enviado_em
     OR NEW.valor_anterior IS DISTINCT FROM OLD.valor_anterior THEN
    RAISE EXCEPTION
      'trafego_aplicacao: cabecalho e `valor_anterior` sao imutaveis. `valor_anterior` e o que torna o rollback possivel; reescreve-lo restauraria um estado inventado.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF OLD.desfecho <> 'em_voo' AND NEW.desfecho IS DISTINCT FROM OLD.desfecho THEN
    RAISE EXCEPTION
      'trafego_aplicacao: esta aplicacao ja fechou como % em %; ela nao reabre. Uma nova tentativa e uma linha nova.',
      OLD.desfecho, OLD.respondido_em
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_aplicacao_fecha_uma_vez
  BEFORE UPDATE OR DELETE ON public.trafego_aplicacao
  FOR EACH ROW EXECUTE FUNCTION public.trafego_aplicacao_fecha_uma_vez();


-- 10.6 A carencia nasce sozinha quando uma aplicacao da certo.
CREATE OR REPLACE FUNCTION public.trafego_aplicacao_abre_cooldown()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
DECLARE
  chave_regra text;
  horas       integer;
  alvo        text;
BEGIN
  SELECT r.chave, r.cooldown_horas, p.alvo_chave
    INTO chave_regra, horas, alvo
    FROM public.trafego_proposta p
    JOIN public.trafego_regra_otimizacao r ON r.regra_id = p.regra_id
   WHERE p.proposta_id = NEW.proposta_id;

  INSERT INTO public.trafego_cooldown
    (regra_chave, alvo_chave, aplicacao_id, iniciado_em, expira_em)
  VALUES
    (chave_regra, alvo, NEW.aplicacao_id, NEW.respondido_em,
     NEW.respondido_em + make_interval(hours => horas));

  RETURN NULL;
END
$funcao$;

-- ⚠️ `WHEN` na definicao do gatilho, e nao um `IF` no corpo: assim o gatilho nem
-- e chamado nos UPDATEs que nao fecham em sucesso, e a regra fica legivel na
-- definicao do objeto — `\d trafego_aplicacao` mostra a condicao.
CREATE TRIGGER trafego_aplicacao_abre_cooldown
  AFTER UPDATE ON public.trafego_aplicacao
  FOR EACH ROW
  WHEN (OLD.desfecho = 'em_voo' AND NEW.desfecho = 'sucesso')
  EXECUTE FUNCTION public.trafego_aplicacao_abre_cooldown();

COMMENT ON FUNCTION public.trafego_aplicacao_abre_cooldown() IS
  'Apenda a carencia quando uma aplicacao fecha em sucesso. Nao deriva nem sobrescreve nada — so acrescenta a linha que o proximo INSERT vai consultar.';


-- 10.7 Append-only: evidencia, diagnostico, aprovacao, acompanhamento, cooldown.
CREATE OR REPLACE FUNCTION public.trafego_autogestao_append_only()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  RAISE EXCEPTION
    '%: append-only, % recusado. O que foi observado ou decidido nao deixa de ter acontecido; corrija com uma linha nova.',
    TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'restrict_violation';
END
$funcao$;

-- ⚠️ `trafego_evidencia` tem UMA excecao ao append-only, e ela e o UPDATE que
-- declara a suficiencia: a evidencia e colhida antes de ser avaliada, e obrigar
-- as duas coisas na mesma transacao faria a colheita ficar de refem do
-- avaliador. Por isso o gatilho abaixo e seletivo, e nao o append-only puro.
CREATE OR REPLACE FUNCTION public.trafego_evidencia_so_avalia()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION
      'trafego_evidencia: DELETE recusado. E a base declarada de uma decisao de gasto.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- Todas as MEDIDAS sao imutaveis. So o veredito de suficiencia pode ser
  -- escrito, e uma vez so: reavaliar uma evidencia ja julgada mudaria
  -- retroativamente se uma proposta antiga podia existir.
  IF NEW.evidencia_id IS DISTINCT FROM OLD.evidencia_id
     OR NEW.regra_id   IS DISTINCT FROM OLD.regra_id
     OR NEW.volc_campaign_id IS DISTINCT FROM OLD.volc_campaign_id
     OR NEW.colhida_em IS DISTINCT FROM OLD.colhida_em
     OR NEW.janela_inicio IS DISTINCT FROM OLD.janela_inicio
     OR NEW.janela_fim    IS DISTINCT FROM OLD.janela_fim
     OR NEW.impressoes    IS DISTINCT FROM OLD.impressoes
     OR NEW.cliques       IS DISTINCT FROM OLD.cliques
     OR NEW.custo_micros  IS DISTINCT FROM OLD.custo_micros
     OR NEW.conversoes    IS DISTINCT FROM OLD.conversoes
     OR NEW.valor_conversao_micros IS DISTINCT FROM OLD.valor_conversao_micros
     OR NEW.moeda    IS DISTINCT FROM OLD.moeda
     OR NEW.metricas IS DISTINCT FROM OLD.metricas THEN
    RAISE EXCEPTION
      'trafego_evidencia: as medidas sao imutaveis — so a suficiencia pode ser declarada depois. Outra leitura e outra evidencia.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF OLD.suficiencia <> 'nao_avaliada'
     AND NEW.suficiencia IS DISTINCT FROM OLD.suficiencia THEN
    RAISE EXCEPTION
      'trafego_evidencia: a suficiencia ja foi declarada como "%" em %; reavaliar mudaria retroativamente se uma proposta podia existir.',
      OLD.suficiencia, OLD.suficiencia_em
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_evidencia_so_avalia
  BEFORE UPDATE OR DELETE ON public.trafego_evidencia
  FOR EACH ROW EXECUTE FUNCTION public.trafego_evidencia_so_avalia();

CREATE TRIGGER trafego_diagnostico_append_only
  BEFORE UPDATE OR DELETE ON public.trafego_diagnostico
  FOR EACH ROW EXECUTE FUNCTION public.trafego_autogestao_append_only();

CREATE TRIGGER trafego_aprovacao_append_only
  BEFORE UPDATE OR DELETE ON public.trafego_aprovacao
  FOR EACH ROW EXECUTE FUNCTION public.trafego_autogestao_append_only();

CREATE TRIGGER trafego_acompanhamento_append_only
  BEFORE UPDATE OR DELETE ON public.trafego_acompanhamento
  FOR EACH ROW EXECUTE FUNCTION public.trafego_autogestao_append_only();

CREATE TRIGGER trafego_cooldown_append_only
  BEFORE UPDATE OR DELETE ON public.trafego_cooldown
  FOR EACH ROW EXECUTE FUNCTION public.trafego_autogestao_append_only();


-- 10.8 A reversao fecha uma vez.
CREATE OR REPLACE FUNCTION public.trafego_reversao_fecha_uma_vez()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION
      'trafego_atuacao_reversao: DELETE recusado. O pedido de desfazer e parte da trilha, tenha ele funcionado ou nao.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.aplicacao_id IS DISTINCT FROM OLD.aplicacao_id
     OR NEW.valor_restaurado IS DISTINCT FROM OLD.valor_restaurado
     OR NEW.acionado_por IS DISTINCT FROM OLD.acionado_por
     OR NEW.acionado_em  IS DISTINCT FROM OLD.acionado_em THEN
    RAISE EXCEPTION
      'trafego_atuacao_reversao: o pedido e imutavel — inclusive `valor_restaurado`, que e o que torna o desfazer possivel.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF OLD.desfecho <> 'pendente' AND NEW.desfecho IS DISTINCT FROM OLD.desfecho THEN
    RAISE EXCEPTION
      'trafego_atuacao_reversao: esta reversao ja fechou como % em %; ela nao reabre.',
      OLD.desfecho, OLD.executado_em
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_reversao_fecha_uma_vez
  BEFORE UPDATE OR DELETE ON public.trafego_atuacao_reversao
  FOR EACH ROW EXECUTE FUNCTION public.trafego_reversao_fecha_uma_vez();


-- -----------------------------------------------------------------------------
-- 11. PROJECOES DE LEITURA
-- -----------------------------------------------------------------------------

CREATE VIEW public.trafego_regra_vigente
  WITH (security_invoker = true) AS
SELECT r.*
  FROM public.trafego_regra_otimizacao r
 WHERE r.vigente_desde IS NOT NULL AND r.retirada_em IS NULL;

COMMENT ON VIEW public.trafego_regra_vigente IS
  'As regras que valem AGORA. Uma por chave, garantido por trafego_regra_vigente_ux.';


CREATE VIEW public.trafego_cooldown_ativo
  WITH (security_invoker = true) AS
SELECT c.*, c.expira_em - now() AS falta
  FROM public.trafego_cooldown c
 WHERE c.expira_em > now();

COMMENT ON VIEW public.trafego_cooldown_ativo IS
  'As carencias de pe neste instante. `now()` mora aqui e nao num indice — predicado de indice tem de ser imutavel.';


CREATE VIEW public.trafego_proposta_painel
  WITH (security_invoker = true) AS
SELECT
  p.proposta_id,
  p.volc_campaign_id,
  p.alvo_nivel,
  p.alvo_chave,
  p.operacao,
  p.valor_atual,
  p.valor_proposto,
  p.valor_atual_lido_em,
  p.delta_pct,
  p.delta_absoluto_micros,
  p.moeda,
  p.estado,
  p.criada_em,
  p.expira_em,

  r.chave        AS regra_chave,
  r.versao       AS regra_versao,
  r.objetivo     AS regra_objetivo,
  r.responsavel  AS regra_responsavel,
  r.nivel_autonomia,
  r.condicao_rollback,

  d.sintoma,
  d.explicacao,
  d.confianca,
  d.severidade,

  e.colhida_em   AS evidencia_colhida_em,
  e.suficiencia  AS evidencia_suficiencia,
  e.janela_inicio,
  e.janela_fim,

  a.decisao      AS aprovacao_decisao,
  a.decidida_por AS aprovacao_por,
  a.decidida_em  AS aprovacao_em,

  ap.aplicacao_id,
  ap.desfecho    AS aplicacao_desfecho,
  ap.enviado_em  AS aplicacao_enviada_em,

  -- ⚠️ EXPIRACAO DERIVADA, e nao coluna. Guardar `expirada` numa coluna criaria
  -- uma segunda fonte da mesma verdade, que so estaria correta enquanto alguem
  -- rodasse um job de varredura — e um dia esse job falharia em silencio,
  -- deixando propostas vencidas com cara de vivas.
  (p.expira_em <= now() AND p.estado = 'aguardando_aprovacao') AS vencida,

  -- O QUE FALTA PARA ESTA PROPOSTA ANDAR. Traducao literal de
  -- `backend/app/trafego/intencao.py:proximo_passo_da_proposta()`.
  -- ⚠️ `sem_resposta` significa o MESMO que `em_voo` para esta decisao: a
  -- chamada saiu e nao sabemos o que ela fez na conta. A versao anterior olhava
  -- so `em_voo`, entao uma aplicacao fechada como `sem_resposta` caia ate
  -- `WHEN a.decisao = 'aprovada' THEN 'aplicar'` — e o painel mandava aplicar de
  -- novo o MESMO diff ja aprovado, sobre uma conta que pode ja te-lo recebido.
  -- E o mesmo defeito que a guarda de `falhou` tinha no nivel do lote, aqui no
  -- nivel da atuacao.
  CASE
    WHEN ap.desfecho IN ('em_voo', 'sem_resposta')       THEN 'verificar'
    WHEN p.estado = 'aplicada'                           THEN 'acompanhar'
    WHEN p.estado IN ('recusada', 'cancelada', 'revertida', 'expirada') THEN 'nada'
    WHEN p.expira_em <= now()                            THEN 'expirar'
    WHEN a.decisao = 'aprovada'                          THEN 'aplicar'
    WHEN a.aprovacao_id IS NULL                          THEN 'aguardar_humano'
    ELSE 'nada'
  END AS proximo_passo

FROM public.trafego_proposta p
JOIN public.trafego_regra_otimizacao r ON r.regra_id = p.regra_id
JOIN public.trafego_diagnostico d ON d.diagnostico_id = p.diagnostico_id
JOIN public.trafego_evidencia   e ON e.evidencia_id  = d.evidencia_id
-- LEFT: proposta sem aprovacao e o estado NORMAL de tudo que acabou de nascer.
LEFT JOIN public.trafego_aprovacao a ON a.proposta_id = p.proposta_id
-- LATERAL com LIMIT 1: um LEFT JOIN simples multiplicaria a proposta por
-- quantas tentativas de aplicacao existissem, e qualquer contagem sobre esta
-- view passaria a somar a mesma proposta varias vezes.
LEFT JOIN LATERAL (
  SELECT aa.aplicacao_id, aa.desfecho, aa.enviado_em
    FROM public.trafego_aplicacao aa
   WHERE aa.proposta_id = p.proposta_id
   ORDER BY aa.tentativa DESC
   LIMIT 1
) ap ON true;

COMMENT ON VIEW public.trafego_proposta_painel IS
  'Proposta + regra citada + diagnostico + evidencia + aprovacao + ultima aplicacao, com `proximo_passo`. Expiracao e DERIVADA, nunca coluna.';


-- -----------------------------------------------------------------------------
-- 12. SEGURANCA
-- -----------------------------------------------------------------------------
DO $seguranca$
DECLARE
  t text;
  f text;
  tabelas CONSTANT text[] := ARRAY[
    'trafego_regra_otimizacao', 'trafego_evidencia', 'trafego_diagnostico',
    'trafego_proposta', 'trafego_aprovacao', 'trafego_aplicacao',
    'trafego_acompanhamento', 'trafego_atuacao_reversao', 'trafego_cooldown'
  ];
  views CONSTANT text[] := ARRAY[
    'trafego_regra_vigente', 'trafego_cooldown_ativo', 'trafego_proposta_painel'
  ];
  -- Append-only puro: nem UPDATE recebem. `trafego_evidencia` fica FORA desta
  -- lista porque o UPDATE de suficiencia e legitimo — e o gatilho seletivo
  -- `trafego_evidencia_so_avalia` limita o que ele pode tocar.
  so_insere CONSTANT text[] := ARRAY[
    'trafego_diagnostico', 'trafego_aprovacao', 'trafego_acompanhamento',
    'trafego_cooldown'
  ];
BEGIN
  FOREACH t IN ARRAY tabelas LOOP
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM service_role', t);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE  ROW LEVEL SECURITY', t);
    IF t = ANY (so_insere) THEN
      EXECUTE format('GRANT SELECT, INSERT ON TABLE public.%I TO service_role', t);
    ELSE
      EXECUTE format('GRANT SELECT, INSERT, UPDATE ON TABLE public.%I TO service_role', t);
    END IF;
  END LOOP;

  FOREACH t IN ARRAY views LOOP
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM service_role', t);
    EXECUTE format('GRANT SELECT ON TABLE public.%I TO service_role', t);
  END LOOP;

  FOREACH f IN ARRAY ARRAY[
    'trafego_regra_so_aposenta', 'trafego_proposta_respeita_regra',
    'trafego_proposta_diff_imutavel', 'trafego_aplicacao_exige_aprovacao',
    'trafego_aplicacao_fecha_uma_vez', 'trafego_aplicacao_abre_cooldown',
    'trafego_autogestao_append_only', 'trafego_evidencia_so_avalia',
    'trafego_reversao_fecha_uma_vez'
  ] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I() FROM PUBLIC', f);
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I() FROM anon', f);
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I() FROM authenticated', f);
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I() FROM service_role', f);
  END LOOP;

  RAISE NOTICE 'v10_02: 9 tabelas com RLS forcada + 3 views security_invoker, zero policies, anon/authenticated revogados nominalmente';
END
$seguranca$;


-- -----------------------------------------------------------------------------
-- 13. VERIFICACAO NA PROPRIA TRANSACAO
-- -----------------------------------------------------------------------------
DO $verifica$
DECLARE
  meus CONSTANT text[] := ARRAY[
    'trafego_regra_otimizacao', 'trafego_evidencia', 'trafego_diagnostico',
    'trafego_proposta', 'trafego_aprovacao', 'trafego_aplicacao',
    'trafego_acompanhamento', 'trafego_atuacao_reversao', 'trafego_cooldown',
    'trafego_regra_vigente', 'trafego_cooldown_ativo', 'trafego_proposta_painel'
  ];
  abertas     text;
  sem_rls     text;
  com_policy  text;
  sem_invoker text;
  faltando    text;
BEGIN
  SELECT string_agg(t, ', ' ORDER BY t) INTO faltando
    FROM unnest(meus) AS t WHERE to_regclass('public.' || t) IS NULL;
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'v10_02: objeto nao criado: %', faltando;
  END IF;

  SELECT string_agg(DISTINCT c.relname, ', ') INTO abertas
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relname = ANY (meus)
     AND (has_table_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, DELETE')
          OR has_table_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, DELETE'));
  IF abertas IS NOT NULL THEN
    RAISE EXCEPTION 'v10_02: anon/authenticated ainda alcancam: %', abertas;
  END IF;

  SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO sem_invoker
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relname = ANY (meus) AND c.relkind = 'v'
     AND NOT coalesce(
       (SELECT option_value = 'true' FROM pg_options_to_table(c.reloptions)
         WHERE option_name = 'security_invoker'), false);
  IF sem_invoker IS NOT NULL THEN
    RAISE EXCEPTION
      'v10_02: view sem security_invoker: % — ela leria as nove tabelas com os privilegios do dono', sem_invoker;
  END IF;

  SELECT string_agg(c.relname, ', ') INTO sem_rls
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relname = ANY (meus) AND c.relkind = 'r'
     AND NOT (c.relrowsecurity AND c.relforcerowsecurity);
  IF sem_rls IS NOT NULL THEN
    RAISE EXCEPTION 'v10_02: RLS nao esta ligada+forcada em: %', sem_rls;
  END IF;

  SELECT string_agg(tablename, ', ') INTO com_policy
    FROM pg_policies WHERE schemaname = 'public' AND tablename = ANY (meus);
  IF com_policy IS NOT NULL THEN
    RAISE EXCEPTION
      'v10_02: policy inesperada em % — a negacao aqui e por AUSENCIA de policy', com_policy;
  END IF;

  IF EXISTS (
    SELECT 1 FROM unnest(meus) AS t
     WHERE to_regclass('public.' || t) IS NOT NULL
       AND has_table_privilege('service_role', 'public.' || t, 'DELETE')
  ) THEN
    RAISE EXCEPTION 'v10_02: alguma tabela concedeu DELETE a service_role';
  END IF;

  -- ⚠️ T2 NAO PODE PASSAR PELA CHECK. Se alguem afrouxar
  -- `trafego_regra_nivel_conhecido` numa migration futura, esta prova quebra a
  -- aplicacao — que e melhor do que a automacao ganhar autorizacao para aplicar
  -- sozinha por causa de um vocabulario alargado sem discussao.
  BEGIN
    INSERT INTO public.trafego_regra_otimizacao
      (chave, versao, titulo, objetivo, plataformas, canais,
       janela_minima_dias, atraso_conversao_dias, frescor_maximo_horas,
       amostra_minima_cliques, dados_obrigatorios, limite_alteracao_pct,
       cooldown_horas, confianca_minima, condicao_rollback,
       rollback_janela_horas, responsavel, nivel_autonomia, deteccao, acao,
       declarada_por, fonte)
    VALUES
      ('prova_t2_nao_existe', 1, 'prova', 'prova', ARRAY['GOOGLE_ADS'],
       ARRAY['*'], 7, 3, 24, 30, ARRAY['cliques'], 20, 24, 0.8,
       'piorou', 48, 'prova', 'T2', '{}'::jsonb, '{}'::jsonb, 'prova', 'prova');
    RAISE EXCEPTION
      'v10_02: T2 foi aceito. A automacao aplicando sozinha nao esta aprovada (ADR-11) e nao pode entrar por um vocabulario alargado sem migracao.';
  EXCEPTION WHEN check_violation THEN
    NULL;  -- e o que se espera
  END;

  IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'trafego_aplicacao_sucesso_unico_ux') THEN
    RAISE EXCEPTION 'v10_02: trafego_aplicacao_sucesso_unico_ux ausente';
  END IF;

  RAISE NOTICE 'v10_02: verificacao interna passou (inclusive: T2 e recusado)';
END
$verifica$;

COMMIT;

-- =============================================================================
-- CONFERENCIA DEPOIS DE APLICAR (somente leitura, cole no psql)
-- =============================================================================
-- SELECT chave, versao, nivel_autonomia, responsavel, cooldown_horas
--   FROM public.trafego_regra_vigente ORDER BY chave;
--
-- SELECT proposta_id, regra_chave, proximo_passo, vencida
--   FROM public.trafego_proposta_painel
--  WHERE estado = 'aguardando_aprovacao' ORDER BY criada_em DESC;
--
-- SELECT regra_chave, alvo_chave, falta FROM public.trafego_cooldown_ativo;
