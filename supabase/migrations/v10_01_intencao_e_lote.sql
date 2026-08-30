-- =============================================================================
-- v10_01 — Intencao, lote de preparacao e o ciclo de criacao auditavel
-- GOOGLE GROWTH ENGINE / AGENTE E. ARQUIVO. NAO APLICADO EM PRODUCAO.
-- =============================================================================
-- APLICAR COMO: postgres (supabase_admin tambem serve; a guarda aceita os dois)
--
-- ORDEM: DEPOIS da v9_01. Ela referencia `trafego_campanha` e `trafego_linhagem`.
--        INDEPENDENTE da v10_02 — as duas nao se tocam, e isso e proposital:
--        criar campanha e otimizar campanha sao dois ciclos que podem ser
--        revertidos em qualquer ordem.
-- ROLLBACK: supabase/migrations/v10_01_rollback.sql  (executavel, e RODADO —
--           ver scripts/provar-ciclo-v10.sh)
--
-- -----------------------------------------------------------------------------
-- O CICLO QUE ESTE ARQUIVO PERSISTE
-- -----------------------------------------------------------------------------
--
--   intencao -> blueprint -> lote -> itens candidatos -> validacao local
--   -> validate_only -> aprovacao humana -> criacao PAUSADA -> recibo
--   -> verificacao remota -> canario -> ativacao progressiva -> rollback
--
-- Dez tabelas, e cada uma existe porque um degrau desse ciclo precisa
-- sobreviver a uma queda de processo no meio dele:
--
--   trafego_intencao        o que se quer alcancar, DECLARADO e imutavel
--   trafego_blueprint       a configuracao por canal, VERSIONADA como dado
--   trafego_lote            conta + canal + estado + quota + aprovacao
--   trafego_lote_item       uma campanha candidata, com estado e erro PROPRIOS
--   trafego_lote_asset      os assets do item, declarado separado do observado
--   trafego_validacao       cada validacao (local, validate_only, pos-criacao)
--   trafego_recibo          CADA tentativa de escrita na plataforma
--   trafego_verificacao     o que a conta respondeu DEPOIS, com carimbo
--   trafego_rollback        o desfazer, com o estado anterior guardado ANTES
--   trafego_lote_transicao  diario append-only de toda mudanca de estado
--
-- -----------------------------------------------------------------------------
-- O REQUISITO MAIS IMPORTANTE DO ARQUIVO INTEIRO: "A API RESPONDEU TIMEOUT
-- MAS CRIOU"
-- -----------------------------------------------------------------------------
-- Este e o unico caso que separa um lote seguro de uma maquina de campanhas
-- duplicadas gastando verba de verdade. A defesa aqui tem QUATRO camadas
-- independentes, e nenhuma delas depende de o executor lembrar de nada:
--
--  1. RECIBO ESCRITO ANTES DA CHAMADA. `trafego_recibo` nasce com
--     `desfecho = 'em_voo'` e `respondido_em` NULO. Um processo que morre no
--     meio deixa a linha em `em_voo` — que e a verdade: nao sabemos.
--     Escrever o recibo DEPOIS da resposta perderia exatamente o caso em que a
--     resposta nunca chega.
--
--  2. O ITEM NAO PODE SER DECLARADO `falhou` COM RECIBO EM VOO. O gatilho
--     `trafego_item_estado_valido` recusa (secao 11.4). `falhou` convida a retomada, e
--     retomar sobre uma chamada que talvez tenha criado e como se cria a
--     segunda campanha. O estado honesto e `indeterminado`, e a UNICA saida
--     dele e uma verificacao remota registrada em `trafego_verificacao`.
--
--  3. UM SUCESSO POR CHAVE, FISICAMENTE. O indice parcial
--     `trafego_recibo_sucesso_unico_ux` e UNICO sobre
--     `(idempotency_key, operacao) WHERE desfecho = 'sucesso'`. Um executor com
--     defeito que reenviasse e conseguisse criar duas vezes NAO consegue
--     registrar o segundo sucesso: a transacao aborta e o lote para, em vez de
--     passar a ser dono de duas campanhas sem saber.
--
--  4. UMA CAMPANHA POR ITEM, E UM ITEM POR CAMPANHA.
--     `trafego_lote_item_campanha_ux` e unico sobre `volc_campaign_id`. Duas
--     linhas do lote nao podem apontar para a mesma campanha criada, e a mesma
--     campanha nao pode ser reivindicada por dois lotes.
--
-- A chave de idempotencia e DERIVADA DO CONTEUDO DO PLANO
-- (`backend/app/trafego/lote.py:chave_de_idempotencia`), nao sorteada. A
-- consequencia operacional e a que importa: se o operador NAO mudou nada, a
-- retomada produz a MESMA chave e o sistema reconhece o que ja existe; se ele
-- mudou o plano, a chave muda e o item novo e outra coisa — que e a verdade.
-- Uma chave sorteada faria toda retomada parecer uma criacao nova.
--
-- A chave viaja ATE A CONTA: ela e o rotulo/sufixo gravado na campanha, e e por
-- ele que a verificacao remota (`metodo = 'busca_por_marca'`) responde "isto ja
-- foi criado?" sem depender de nenhum id que talvez nunca tenha voltado. Por
-- isso a CHECK de forma exige no minimo 8 caracteres: uma chave curta colide,
-- e uma colisao aqui e uma campanha adotando o recibo de outra.
--
-- -----------------------------------------------------------------------------
-- AS REGRAS DA CASA, HERDADAS DA v9 E VALIDAS AQUI SEM EXCECAO
-- -----------------------------------------------------------------------------
-- A. NENHUM NUMERO SEM FRESCOR. Toda leitura da conta carrega o instante em que
--    foi lida, POR LINHA (`id_externo_lido_em`, `verificado_em`, `quota_lida_em`,
--    `aprovacao_externa_lida_em`). As CHECKs `..._sem_carimbo` recusam o par
--    incompleto.
-- B. AUSENCIA E NULL, NUNCA ZERO. Nenhuma coluna de MEDIDA tem DEFAULT 0.
--    `tentativas` e `ordem` sao a excecao explicada: sao contagens de ATOS
--    NOSSOS, sempre conhecidas no momento do INSERT, nunca resultado de medicao
--    externa que possa ter falhado.
-- C. FALHA DE UM ITEM NAO CONTAMINA OS OUTROS. O erro e coluna do ITEM
--    (`erro_codigo`, `erro_mensagem`, `erro_em`, `erro_detalhe`), nunca do lote.
--    O lote agrega; ele nao substitui.
-- D. DECLARADO E OBSERVADO NAO DIVIDEM COLUNA. `trafego_lote_item.plano` e o
--    que o VOLC declarou; `trafego_verificacao.valor_observado` e o que a conta
--    respondeu. Nenhum UPDATE de leitura toca o declarado.
-- E. HISTORICO NAO SE APAGA. Estado corrente mora na linha; toda transicao vira
--    linha em `trafego_lote_transicao`, escrita por gatilho — nao por disciplina
--    do chamador.
--
-- -----------------------------------------------------------------------------
-- SEGURANCA — os defaults deste banco sao INSEGUROS (achado H, 24/08/2026)
-- -----------------------------------------------------------------------------
-- `pg_default_acl` do schema `public` concede `arwdDxt` NOMINALMENTE a anon,
-- authenticated e service_role em toda tabela nova. `REVOKE ... FROM PUBLIC`
-- nao remove grant nominal. Portanto, para cada objeto deste arquivo:
--   1) REVOKE nominal de PUBLIC, anon, authenticated e service_role;
--   2) ENABLE + FORCE ROW LEVEL SECURITY com ZERO policies;
--   3) GRANT minimo e explicito, so para service_role.
-- DELETE nao e concedido a NINGUEM em NENHUMA tabela. Cancelar e um estado,
-- reverter e uma linha, e erro de plano vira item novo — nao ha caminho de
-- apagamento no dominio.
--
-- ⚠️ O que isto NAO protege: `service_role` tem `rolbypassrls = t`. RLS nao
-- contem endpoint que carregue a service key sem autenticacao. Esta migration
-- contem anon e authenticated, que e o que o navegador carrega.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO DELIBERADAMENTE NAO FAZ
-- -----------------------------------------------------------------------------
-- - Nao chama, nao habilita e nao pressupoe nenhuma escrita no Google Ads. Ele
--   guarda o RASTRO de uma escrita; a trava de escrita continua fechada.
-- - Nao cria FK para `campaigns`, `projects` nem `pautador_*`. Mesma razao da
--   v9_01: o registro de uma decisao precisa sobreviver ao desaparecimento do
--   alvo, senao a auditoria some junto com o dado auditado.
-- - Nao decide vocabulario de `objetivo` nem de `papel` de asset. Os dois ficam
--   ABERTOS com CHECK de nao-vazio, pela mesma razao que `estrategia` ficou
--   aberta na v9_01: uma lista fechada cedo demais faz o sistema RECUSAR um
--   pedido legitimo, e a recusa aparece como defeito de plataforma.
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
      'v10_01 deve rodar como postgres ou supabase_admin; papel atual: %',
      current_user;
  END IF;

  -- PG15 e o piso pelo mesmo motivo da v9_01: `security_invoker` em VIEW so
  -- existe a partir dele, e sem ele as projecoes da secao 12 viram tunel por
  -- cima de toda a RLS que a secao 13 liga.
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION
      'v10_01 exige PostgreSQL 15 ou maior (security_invoker em VIEW); aqui: %',
      current_setting('server_version');
  END IF;

  IF to_regclass('public.trafego_campanha') IS NULL
     OR to_regclass('public.trafego_linhagem') IS NULL THEN
    RAISE EXCEPTION
      'v10_01 abortada: a v9_01 nao esta aplicada. O item do lote aponta para trafego_campanha, que e a identidade da instancia (ADR-02).';
  END IF;

  SELECT string_agg(t, ', ' ORDER BY t) INTO ja_existem
    FROM unnest(ARRAY[
      'trafego_intencao', 'trafego_blueprint', 'trafego_lote',
      'trafego_lote_item', 'trafego_lote_asset', 'trafego_validacao',
      'trafego_recibo', 'trafego_verificacao', 'trafego_rollback',
      'trafego_lote_transicao', 'trafego_lote_painel', 'trafego_item_situacao'
    ]) AS t
   WHERE to_regclass('public.' || t) IS NOT NULL;

  IF ja_existem IS NOT NULL THEN
    RAISE EXCEPTION
      'v10_01 ja parece aplicada: % ja existe(m). Rode v10_01_rollback.sql antes de reaplicar.',
      ja_existem;
  END IF;

  SELECT string_agg(r, ', ' ORDER BY r) INTO faltando
    FROM unnest(ARRAY['anon', 'authenticated', 'service_role']) AS r
   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);

  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION
      'v10_01 exige os papeis do Supabase; ausente(s): %. Sem eles o REVOKE nominal nao acontece e a tabela nasce aberta.',
      faltando;
  END IF;

  RAISE NOTICE 'v10_01: guardas ok (papel=%, versao=%)',
    current_user, current_setting('server_version');
END
$guarda$;


-- -----------------------------------------------------------------------------
-- 1. trafego_intencao — o que se quer alcancar. Declaracao, nao estado.
-- -----------------------------------------------------------------------------
-- A intencao e o topo do ciclo e a unica coisa dele que NAO tem ciclo de vida:
-- ela e uma declaracao datada, com autor e base. Quem tem estado e o LOTE que
-- nasce dela — e por isso a intencao e imutavel por gatilho.
--
-- POR QUE IMUTAVEL, E NAO "editavel com historico": a intencao e a pergunta que
-- o lote responde. Reescrever a pergunta depois da resposta faz o par
-- pergunta/resposta contar uma historia que ninguem viveu. Mudou a intencao?
-- E outra intencao, com outro id, e o lote novo aponta para ela. O custo e uma
-- linha a mais; o beneficio e que "por que criamos esta campanha?" sempre tem
-- resposta verificavel.
--
-- LINHAGEM (ADR-02): a intencao aponta para `trafego_linhagem`, que e a segunda
-- identidade do sistema — a que atravessa relancamentos e plataformas. A
-- primeira identidade (a instancia) aparece no ITEM, como `volc_campaign_id`.
-- As duas estao aqui, e nenhuma terceira foi inventada.
CREATE TABLE public.trafego_intencao (
  intencao_id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_lineage_id  uuid        REFERENCES public.trafego_linhagem (campaign_lineage_id)
                                   ON DELETE RESTRICT,

  -- IDENTIDADE EXTERNA DA INTENCAO: onde ela sera perseguida.
  -- `plataforma` esta aqui pela mesma razao de `IdentidadeDeCampanha`: ids
  -- externos sao numericos no Google e no Meta, e nada impede que os dois
  -- emitam o mesmo numero. Sem a plataforma na chave, duas campanhas diferentes
  -- viveriam sob a mesma identidade externa.
  plataforma           text        NOT NULL,
  conta_externa        text        NOT NULL,

  objetivo             text        NOT NULL,
  rotulo               text        NOT NULL,
  destino_url          text,

  -- TETO DE VERBA. Nullable: nem toda intencao declara teto. Mas numero sem
  -- unidade e numero sem significado — a CHECK abaixo exige a moeda junto.
  verba_diaria_teto_micros bigint,
  moeda                text,

  -- PROCEDENCIA COMPLETA: quem, quando, com base em que.
  declarada_por        text        NOT NULL,
  declarada_em         timestamptz NOT NULL DEFAULT now(),
  declarada_com_base_em text       NOT NULL,
  evidencia            jsonb       NOT NULL DEFAULT '{}'::jsonb,
  motivo               text,

  CONSTRAINT trafego_intencao_plataforma_conhecida
    CHECK (plataforma IN ('GOOGLE_ADS', 'META_ADS')),

  -- A forma da conta depende da plataforma, e generalizar seria mentir: no
  -- Google a conta e digito puro (o mesmo `^[0-9]{6,12}$` da v9_01), no Meta ela
  -- vem com prefixo. Uma CHECK unica so aceitaria o Google, e a primeira conta
  -- do Meta seria recusada por uma regra que ninguem escreveu de proposito.
  CONSTRAINT trafego_intencao_conta_valida
    CHECK (
      btrim(conta_externa) <> ''
      AND (plataforma <> 'GOOGLE_ADS' OR conta_externa ~ '^[0-9]{6,12}$')
    ),

  -- `objetivo` fica ABERTO de proposito. Fechar a lista aqui seria congelar um
  -- vocabulario que o contrato de regras (docs/growth-engine/legado-n8n/
  -- regras-canonicas.json) ainda esta produzindo, e uma CHECK fechada cedo
  -- demais faz a porta RECUSAR um pedido legitimo — a mesma razao pela qual
  -- `estrategia` ficou aberta na v9_01.
  CONSTRAINT trafego_intencao_objetivo_nao_vazio  CHECK (btrim(objetivo) <> ''),
  CONSTRAINT trafego_intencao_rotulo_nao_vazio    CHECK (btrim(rotulo) <> ''),
  CONSTRAINT trafego_intencao_declarante_nao_vazio
    CHECK (btrim(declarada_por) <> ''),
  -- "Com base em que" NAO e opcional. Uma intencao sem base declarada e um
  -- palpite com carimbo de decisao, e e exatamente ela que ninguem consegue
  -- auditar seis meses depois.
  CONSTRAINT trafego_intencao_base_nao_vazia
    CHECK (btrim(declarada_com_base_em) <> ''),

  CONSTRAINT trafego_intencao_moeda_iso
    CHECK (moeda IS NULL OR moeda ~ '^[A-Z]{3}$'),
  CONSTRAINT trafego_intencao_teto_nao_negativo
    CHECK (verba_diaria_teto_micros IS NULL OR verba_diaria_teto_micros >= 0),
  -- REGRA A aplicada a dinheiro: verba sem moeda e um numero que ninguem sabe
  -- ler. R$ 50 e US$ 50 nao sao o mesmo teto.
  CONSTRAINT trafego_intencao_teto_sem_moeda
    CHECK (verba_diaria_teto_micros IS NULL OR moeda IS NOT NULL)
);

CREATE INDEX trafego_intencao_conta_ix
  ON public.trafego_intencao (plataforma, conta_externa, declarada_em DESC);
CREATE INDEX trafego_intencao_linhagem_ix
  ON public.trafego_intencao (campaign_lineage_id)
  WHERE campaign_lineage_id IS NOT NULL;

COMMENT ON TABLE  public.trafego_intencao IS
  'O que se quer alcancar, declarado com autor, data e base. Imutavel por gatilho: mudou a intencao, e outra intencao.';
COMMENT ON COLUMN public.trafego_intencao.declarada_com_base_em IS
  'A base da declaracao. NOT NULL e nao-vazio: intencao sem base e palpite com carimbo de decisao.';


-- -----------------------------------------------------------------------------
-- 2. trafego_blueprint — a configuracao por canal, VERSIONADA como dado
-- -----------------------------------------------------------------------------
-- O blueprint e o molde: quantos grupos, que tipos de anuncio, que assets sao
-- obrigatorios, que validacoes locais valem. Ele e DADO e nao codigo pela mesma
-- razao que a regra de otimizacao da v10_02 e dado: um molde que so existe em
-- Python nao pode ser citado por um recibo, e um recibo que nao cita o molde
-- nao explica o que foi criado.
--
-- VERSIONADO E IMUTAVEL: `(chave, versao)` e unico e a linha nao muda. Um lote
-- guarda o `blueprint_id` EXATO que usou, entao mudar o molde amanha nao
-- reescreve a explicacao do que foi criado ontem.
CREATE TABLE public.trafego_blueprint (
  blueprint_id   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  chave          text        NOT NULL,
  versao         integer     NOT NULL,

  plataforma     text        NOT NULL,
  canal          text        NOT NULL,

  titulo         text        NOT NULL,
  corpo          jsonb       NOT NULL,

  declarado_por  text        NOT NULL,
  declarado_em   timestamptz NOT NULL DEFAULT now(),
  -- Aposentadoria sem apagamento: `retirado_em` fecha a versao para uso novo e
  -- deixa a linha de pe para quem ja a citou.
  retirado_em    timestamptz,
  retirado_por   text,

  CONSTRAINT trafego_blueprint_chave_nao_vazia   CHECK (btrim(chave) <> ''),
  CONSTRAINT trafego_blueprint_titulo_nao_vazio  CHECK (btrim(titulo) <> ''),
  CONSTRAINT trafego_blueprint_declarante_nao_vazio
    CHECK (btrim(declarado_por) <> ''),
  CONSTRAINT trafego_blueprint_versao_positiva   CHECK (versao >= 1),
  CONSTRAINT trafego_blueprint_plataforma_conhecida
    CHECK (plataforma IN ('GOOGLE_ADS', 'META_ADS')),

  -- O vocabulario canonico de canal e o MESMO da v9_01 (ADR-18): o enum do
  -- Google, e nao a lista do que sabemos construir. Recusar canal sem
  -- construtor e trabalho da PORTA DE CRIACAO — `plataforma.ManifestoDeCanal` —,
  -- nao do schema. Aqui a CHECK impede o APELIDO: 'PMAX' e recusado,
  -- 'PERFORMANCE_MAX' passa.
  CONSTRAINT trafego_blueprint_canal_canonico
    CHECK (
      plataforma <> 'GOOGLE_ADS'
      OR canal IN (
        'SEARCH', 'DISPLAY', 'DEMAND_GEN', 'PERFORMANCE_MAX',
        'VIDEO', 'SHOPPING', 'DISCOVERY', 'MULTI_CHANNEL',
        'LOCAL', 'LOCAL_SERVICES', 'SMART', 'HOTEL', 'TRAVEL')
    ),
  CONSTRAINT trafego_blueprint_corpo_e_objeto
    CHECK (jsonb_typeof(corpo) = 'object'),
  CONSTRAINT trafego_blueprint_retirada_completa
    CHECK (
      (retirado_em IS NULL AND retirado_por IS NULL)
      OR (retirado_em IS NOT NULL AND btrim(coalesce(retirado_por, '')) <> '')
    )
);

CREATE UNIQUE INDEX trafego_blueprint_versao_ux
  ON public.trafego_blueprint (chave, versao);
-- No maximo UMA versao vigente por chave. Duas vigentes seria a mesma pergunta
-- com duas respostas, e o executor teria de escolher — escolhendo, ele viraria
-- a autoridade sobre o molde, que e justamente o que versionar evita.
CREATE UNIQUE INDEX trafego_blueprint_vigente_ux
  ON public.trafego_blueprint (chave)
  WHERE retirado_em IS NULL;

COMMENT ON TABLE  public.trafego_blueprint IS
  'A configuracao por canal como DADO versionado e imutavel. O lote guarda o blueprint_id exato que usou.';


-- -----------------------------------------------------------------------------
-- 3. trafego_lote — conta, canal, quota, aprovacao e estado
-- -----------------------------------------------------------------------------
-- O lote e a unidade de PREPARACAO, nunca a unidade de falha. Ele agrega os
-- itens; ele nao os substitui. Nenhuma coluna daqui carrega erro de item — a
-- regra C em forma de schema.
--
-- APROVACAO HUMANA E ESTRUTURAL: o gatilho
-- `trafego_lote_estado_valido` recusa a transicao para `executando` sem
-- `aprovado_em`. Nao ha caminho de execucao que passe por cima disso, e nao
-- existe "aprovacao automatica" — nem como valor, nem como default.
CREATE TABLE public.trafego_lote (
  lote_id        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  intencao_id    uuid        NOT NULL REFERENCES public.trafego_intencao (intencao_id)
                             ON DELETE RESTRICT,
  blueprint_id   uuid        NOT NULL REFERENCES public.trafego_blueprint (blueprint_id)
                             ON DELETE RESTRICT,

  plataforma     text        NOT NULL,
  conta_externa  text        NOT NULL,
  canal          text        NOT NULL,

  estado         text        NOT NULL DEFAULT 'preparando',

  -- CONCORRENCIA. NULL = nao declarado; o executor usa o proprio teto. Nao ha
  -- DEFAULT numerico porque um default aqui seria uma decisao operacional
  -- tomada pelo schema, e ela mudaria de significado por conta.
  limite_concorrencia   integer,

  -- QUOTA. Duas colunas separadas, e nao uma: `orcada` e o que o VOLC DECLAROU
  -- que ia gastar de operacoes; `consumida` e o que a plataforma cobrou. Sao
  -- declarado x observado (regra D), e achata-los apagaria a diferenca entre
  -- "planejamos errado" e "a API cobrou diferente".
  quota_orcada          integer,
  quota_consumida       integer,
  quota_lida_em         timestamptz,

  aprovado_por          text,
  aprovado_em           timestamptz,
  aprovacao_observacao  text,

  cancelado_por         text,
  cancelado_em          timestamptz,
  cancelado_motivo      text,

  -- O resumo que o operador le. Texto, e nao JSON: ele existe para ser lido por
  -- gente, e um resumo que precisa de renderizador nao e resumo.
  resumo_humano  text,

  criado_por     text        NOT NULL,
  criado_em      timestamptz NOT NULL DEFAULT now(),
  atualizado_em  timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT trafego_lote_plataforma_conhecida
    CHECK (plataforma IN ('GOOGLE_ADS', 'META_ADS')),
  CONSTRAINT trafego_lote_conta_valida
    CHECK (
      btrim(conta_externa) <> ''
      AND (plataforma <> 'GOOGLE_ADS' OR conta_externa ~ '^[0-9]{6,12}$')
    ),
  CONSTRAINT trafego_lote_canal_canonico
    CHECK (
      plataforma <> 'GOOGLE_ADS'
      OR canal IN (
        'SEARCH', 'DISPLAY', 'DEMAND_GEN', 'PERFORMANCE_MAX',
        'VIDEO', 'SHOPPING', 'DISCOVERY', 'MULTI_CHANNEL',
        'LOCAL', 'LOCAL_SERVICES', 'SMART', 'HOTEL', 'TRAVEL')
    ),
  CONSTRAINT trafego_lote_criador_nao_vazio CHECK (btrim(criado_por) <> ''),

  -- O VOCABULARIO DE ESTADO, fechado. Cada termo e um lugar de onde se sai por
  -- um caminho diferente, e nenhum deles e apagar a linha:
  --   preparando            os itens estao sendo montados
  --   validando             validacao local + validate_only em andamento
  --   aguardando_aprovacao  a maquina terminou; falta o humano
  --   aprovado              autorizado, ainda nao executado
  --   executando            escrevendo na plataforma
  --   interrompido          parou no meio (queda, cancelamento em voo)
  --   concluido             todos os itens chegaram ao fim sem erro
  --   concluido_com_falhas  chegou ao fim, e ALGUNS itens falharam — o desfecho
  --                         normal de um lote real, e nao uma excecao
  --   recusado              o humano disse nao
  --   cancelado             abandonado antes de executar
  --   revertido             executado e desfeito
  CONSTRAINT trafego_lote_estado_conhecido
    CHECK (estado IN (
      'preparando', 'validando', 'aguardando_aprovacao', 'aprovado',
      'executando', 'interrompido', 'concluido', 'concluido_com_falhas',
      'recusado', 'cancelado', 'revertido')),

  CONSTRAINT trafego_lote_concorrencia_positiva
    CHECK (limite_concorrencia IS NULL OR limite_concorrencia >= 1),
  CONSTRAINT trafego_lote_quotas_nao_negativas
    CHECK (coalesce(quota_orcada, 0) >= 0 AND coalesce(quota_consumida, 0) >= 0),

  -- REGRA A. `quota_consumida` e MEDIDA na plataforma; sem o instante da
  -- leitura ela e indistinguivel do consumo de ontem — e alguem decide se ainda
  -- pode executar olhando para ela.
  CONSTRAINT trafego_lote_quota_sem_carimbo
    CHECK (quota_consumida IS NULL OR quota_lida_em IS NOT NULL),

  CONSTRAINT trafego_lote_aprovacao_completa
    CHECK (
      (aprovado_em IS NULL AND aprovado_por IS NULL)
      OR (aprovado_em IS NOT NULL AND btrim(coalesce(aprovado_por, '')) <> '')
    ),
  CONSTRAINT trafego_lote_cancelamento_completo
    CHECK (
      (cancelado_em IS NULL AND cancelado_por IS NULL)
      OR (cancelado_em IS NOT NULL AND btrim(coalesce(cancelado_por, '')) <> '')
    ),
  -- Cancelar sem dizer por que e apagar a razao junto com o lote.
  CONSTRAINT trafego_lote_cancelamento_tem_motivo
    CHECK (cancelado_em IS NULL OR btrim(coalesce(cancelado_motivo, '')) <> '')
);

CREATE INDEX trafego_lote_intencao_ix ON public.trafego_lote (intencao_id);
CREATE INDEX trafego_lote_conta_ix
  ON public.trafego_lote (plataforma, conta_externa, criado_em DESC);
-- A ordem do keyset da tela: estado primeiro (o que exige o operador agora),
-- `lote_id` so desempata. Sem a segunda coluna a ordem dentro do degrau seria
-- indefinida e a paginacao por keyset perderia o chao — o mesmo defeito que
-- `ordem_operacional` conserta na v9_03.
CREATE INDEX trafego_lote_estado_ix ON public.trafego_lote (estado, lote_id);

COMMENT ON TABLE  public.trafego_lote IS
  'A unidade de PREPARACAO, nunca a de falha. Erro e sempre do item. Execucao exige aprovado_em, por gatilho.';
COMMENT ON COLUMN public.trafego_lote.quota_consumida IS
  'Observado na plataforma. Exige quota_lida_em (regra A). NULL = nao medido, nunca zero.';


-- -----------------------------------------------------------------------------
-- 4. trafego_lote_item — a campanha candidata. Estado e erro PROPRIOS.
-- -----------------------------------------------------------------------------
-- Esta e a tabela onde a idempotencia mora. Leia o cabecalho, secao "A API
-- RESPONDEU TIMEOUT MAS CRIOU", antes de mexer em qualquer coisa aqui.
CREATE TABLE public.trafego_lote_item (
  item_id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  lote_id          uuid        NOT NULL REFERENCES public.trafego_lote (lote_id)
                               ON DELETE RESTRICT,
  ordem            integer     NOT NULL,

  -- ⚠️ A CHAVE. Unica em toda a tabela, e nao apenas dentro do lote: uma
  -- retomada que crie um lote NOVO para a mesma intencao tem de colidir aqui,
  -- senao a duplicidade so seria descoberta na conta — depois de gasta.
  --
  -- Ela e DERIVADA DO CONTEUDO (ver `lote.chave_de_idempotencia`) e viaja ate a
  -- conta como rotulo, para que a verificacao remota possa perguntar "isto ja
  -- existe?" sem depender de um id que talvez nunca tenha voltado.
  idempotency_key  text        NOT NULL,

  rotulo           text        NOT NULL,

  -- DECLARADO pelo VOLC. Nenhum caminho de leitura escreve aqui (regra D).
  plano            jsonb       NOT NULL,

  estado           text        NOT NULL DEFAULT 'planejado',

  -- ERRO POR ITEM (regra C). Falha de uma campanha nao invalida nem mascara as
  -- demais, porque nao existe lugar no lote onde ela caiba.
  erro_codigo      text,
  erro_mensagem    text,
  erro_em          timestamptz,
  erro_detalhe     jsonb,

  -- Contagem de ATOS NOSSOS, sempre conhecida no INSERT. Nao e medida externa,
  -- entao o DEFAULT 0 aqui nao viola a regra B — ele afirma um fato verdadeiro:
  -- ainda nao tentamos nenhuma vez.
  tentativas       integer     NOT NULL DEFAULT 0,

  -- A PRIMEIRA IDENTIDADE (ADR-02, instancia). Preenchida quando a campanha
  -- passa a existir; ate la, NULL — que e a verdade.
  volc_campaign_id text        REFERENCES public.trafego_campanha (volc_campaign_id)
                               ON DELETE RESTRICT,

  -- OBSERVADO na conta, com carimbo proprio (regra A + regra D).
  id_externo           text,
  id_externo_lido_em   timestamptz,

  cancelado_por    text,
  cancelado_em     timestamptz,

  criado_em        timestamptz NOT NULL DEFAULT now(),
  atualizado_em    timestamptz NOT NULL DEFAULT now(),

  -- Forma da chave. O piso de 8 caracteres nao e estetica: a chave viaja ate a
  -- conta como rotulo e e por ela que a verificacao remota reconhece o que ja
  -- foi criado. Uma chave curta colide, e uma colisao aqui e uma campanha
  -- adotando o recibo de outra. O alfabeto e o que sobrevive a um rotulo do
  -- Google Ads e a um `in.(...)` do PostgREST sem escape.
  CONSTRAINT trafego_item_chave_valida
    CHECK (idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$'),
  CONSTRAINT trafego_item_rotulo_nao_vazio CHECK (btrim(rotulo) <> ''),
  CONSTRAINT trafego_item_ordem_nao_negativa CHECK (ordem >= 0),
  CONSTRAINT trafego_item_tentativas_nao_negativas CHECK (tentativas >= 0),
  CONSTRAINT trafego_item_plano_e_objeto CHECK (jsonb_typeof(plano) = 'object'),

  -- O VOCABULARIO DE ESTADO DO ITEM. `indeterminado` e o termo mais importante
  -- da lista, e ele existe porque o contrario dele e caro:
  --
  --   planejado         montado, nada validado
  --   validado_local    passou nas regras que rodam sem rede
  --   validado_remoto   passou no `validate_only` da plataforma
  --   aprovado          o humano autorizou o lote
  --   criando           a chamada esta em voo
  --   indeterminado     a chamada NAO respondeu. Nao sabemos se criou.
  --                     A UNICA saida daqui e uma verificacao remota.
  --   criada_pausada    criada e PAUSADA — nunca ativa por padrao (ADR-11)
  --   verificada        a conta confirmou o que criamos
  --   canario           ativada em fracao, sob observacao
  --   ativa             ativacao progressiva concluida
  --   falhou            a plataforma recusou, com erro conhecido
  --   cancelada         abandonada antes de virar campanha
  --   revertida         criada e desfeita
  CONSTRAINT trafego_item_estado_conhecido
    CHECK (estado IN (
      'planejado', 'validado_local', 'validado_remoto', 'aprovado',
      'criando', 'indeterminado', 'criada_pausada', 'verificada',
      'canario', 'ativa', 'falhou', 'cancelada', 'revertida')),

  -- REGRA A no erro: um erro sem data e indistinguivel de um erro de ontem, e
  -- e por ele que a retomada decide o que refazer.
  CONSTRAINT trafego_item_erro_sem_carimbo
    CHECK (
      (erro_codigo IS NULL AND erro_mensagem IS NULL AND erro_detalhe IS NULL)
      OR erro_em IS NOT NULL
    ),
  -- `falhou` sem causa e o mesmo defeito de "sumiu da conta": um rotulo que
  -- esconde o que aconteceu. Quem falha diz por que.
  CONSTRAINT trafego_item_falha_tem_causa
    CHECK (estado <> 'falhou' OR btrim(coalesce(erro_mensagem, '')) <> ''),

  CONSTRAINT trafego_item_id_externo_sem_carimbo
    CHECK (id_externo IS NULL OR id_externo_lido_em IS NOT NULL),

  -- Nao se declara criacao sem o id que a conta devolveu. Sem esta CHECK,
  -- `criada_pausada` poderia significar "acho que criou" — que e exatamente o
  -- estado `indeterminado`, com outro nome e sem a obrigacao de verificar.
  CONSTRAINT trafego_item_criada_tem_id
    CHECK (
      estado NOT IN ('criada_pausada', 'verificada', 'canario', 'ativa')
      OR (id_externo IS NOT NULL AND volc_campaign_id IS NOT NULL)
    ),

  CONSTRAINT trafego_item_cancelamento_completo
    CHECK (
      (cancelado_em IS NULL AND cancelado_por IS NULL)
      OR (cancelado_em IS NOT NULL AND btrim(coalesce(cancelado_por, '')) <> '')
    )
);

CREATE UNIQUE INDEX trafego_item_chave_ux
  ON public.trafego_lote_item (idempotency_key);
CREATE UNIQUE INDEX trafego_item_ordem_ux
  ON public.trafego_lote_item (lote_id, ordem);

-- CAMADA 4 DA DEFESA CONTRA DUPLICIDADE. Duas linhas do lote nao podem apontar
-- para a mesma campanha criada, e a mesma campanha nao pode ser reivindicada
-- por dois lotes. Sem este indice, uma retomada mal-sucedida adotaria a campanha
-- do item anterior e os dois pareceriam corretos.
CREATE UNIQUE INDEX trafego_lote_item_campanha_ux
  ON public.trafego_lote_item (volc_campaign_id)
  WHERE volc_campaign_id IS NOT NULL;

-- ⚠️ Chave candidata redundante com a PK, e ela existe por UM motivo: permitir
-- a FK COMPOSTA de `trafego_validacao (lote_id, item_id)`. Sem ela, uma
-- validacao poderia apontar para um lote e um item de OUTRO lote, e o painel
-- somaria validacoes que nao sao daquele lote.
CREATE UNIQUE INDEX trafego_item_lote_item_ux
  ON public.trafego_lote_item (lote_id, item_id);

CREATE INDEX trafego_item_estado_ix ON public.trafego_lote_item (lote_id, estado);
CREATE INDEX trafego_item_campanha_ix
  ON public.trafego_lote_item (volc_campaign_id)
  WHERE volc_campaign_id IS NOT NULL;

COMMENT ON TABLE  public.trafego_lote_item IS
  'A campanha candidata. Idempotency key unica e derivada do conteudo; erro e estado sao do ITEM, nunca do lote.';
COMMENT ON COLUMN public.trafego_lote_item.idempotency_key IS
  'Derivada do conteudo do plano, unica na tabela inteira, e gravada na conta como rotulo. E por ela que a retomada reconhece o que ja foi criado.';
COMMENT ON COLUMN public.trafego_lote_item.estado IS
  'Inclui `indeterminado`: a chamada nao respondeu e nao sabemos se criou. A unica saida e uma verificacao remota registrada.';


-- -----------------------------------------------------------------------------
-- 5. trafego_lote_asset — declarado x observado, em colunas separadas
-- -----------------------------------------------------------------------------
-- O asset tem DOIS lados que nunca dividem coluna:
--   · o que o VOLC declarou (`conteudo`, `uri`, `origem`, `declarado_por`);
--   · o que a conta respondeu (`id_externo`, `aprovacao_externa`), cada um com
--     o seu proprio carimbo.
--
-- `aprovacao_externa` e o veredito de politica da plataforma. Ele NAO tem lista
-- fechada: o Google acrescenta rotulo de politica sem avisar, e uma CHECK
-- fechada faria a leitura FALHAR ao encontrar um valor legitimo — a falha
-- apareceria como "sincronizacao falhou" numa conta que respondeu certo.
CREATE TABLE public.trafego_lote_asset (
  asset_id      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id       uuid        NOT NULL REFERENCES public.trafego_lote_item (item_id)
                            ON DELETE RESTRICT,

  papel         text        NOT NULL,
  ordem         integer     NOT NULL,

  conteudo      text,
  uri           text,
  hash_conteudo text,

  -- Procedencia do asset. Com o creative engine em producao, "quem escreveu
  -- isto" deixa de ser obvio — e um criativo gerado que ninguem revisou nao
  -- pode ser indistinguivel de um escrito por gente.
  origem        text        NOT NULL,
  declarado_por text        NOT NULL,
  declarado_em  timestamptz NOT NULL DEFAULT now(),

  -- OBSERVADO, cada um com carimbo (regra A + D).
  id_externo               text,
  id_externo_lido_em       timestamptz,
  aprovacao_externa        text,
  aprovacao_externa_lida_em timestamptz,

  CONSTRAINT trafego_asset_papel_nao_vazio  CHECK (btrim(papel) <> ''),
  CONSTRAINT trafego_asset_ordem_nao_negativa CHECK (ordem >= 0),
  CONSTRAINT trafego_asset_declarante_nao_vazio
    CHECK (btrim(declarado_por) <> ''),
  CONSTRAINT trafego_asset_origem_conhecida
    CHECK (origem IN ('humano', 'gerado', 'biblioteca', 'importado')),
  -- Asset que nao tem conteudo nem endereco nao e asset.
  CONSTRAINT trafego_asset_tem_corpo
    CHECK (btrim(coalesce(conteudo, '')) <> '' OR btrim(coalesce(uri, '')) <> ''),
  CONSTRAINT trafego_asset_id_externo_sem_carimbo
    CHECK (id_externo IS NULL OR id_externo_lido_em IS NOT NULL),
  CONSTRAINT trafego_asset_aprovacao_sem_carimbo
    CHECK (aprovacao_externa IS NULL OR aprovacao_externa_lida_em IS NOT NULL)
);

CREATE UNIQUE INDEX trafego_asset_posicao_ux
  ON public.trafego_lote_asset (item_id, papel, ordem);
CREATE INDEX trafego_asset_item_ix ON public.trafego_lote_asset (item_id);

COMMENT ON TABLE  public.trafego_lote_asset IS
  'Assets do item. Declarado (conteudo/uri/origem) e observado (id_externo/aprovacao_externa) em colunas separadas, cada lado com carimbo proprio.';


-- -----------------------------------------------------------------------------
-- 6. trafego_validacao — append-only, nas tres camadas
-- -----------------------------------------------------------------------------
-- `camada` separa tres perguntas diferentes que costumam ser confundidas:
--   local          o pedido esta bem formado? (sem rede, sem quota)
--   validate_only  a PLATAFORMA aceitaria isto? (rede, sem criar nada)
--   pos_criacao    o que foi criado bate com o que se pediu?
--
-- Guardar as tres na mesma tabela com a camada declarada permite responder
-- "quantas vezes o validate_only reprovou por politica?" sem reprocessar log.
--
-- FK COMPOSTA `(lote_id, item_id)`: com `item_id` NULO a FK composta nao e
-- checada (MATCH SIMPLE), e isso e exatamente o que se quer — validacao de LOTE
-- inteiro nao tem item. Com item preenchido, o par tem de existir NAQUELE lote.
CREATE TABLE public.trafego_validacao (
  validacao_id  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  lote_id       uuid        NOT NULL REFERENCES public.trafego_lote (lote_id)
                            ON DELETE RESTRICT,
  item_id       uuid,

  camada        text        NOT NULL,
  regra         text        NOT NULL,
  resultado     text        NOT NULL,
  mensagem      text,
  detalhe       jsonb       NOT NULL DEFAULT '{}'::jsonb,

  validado_em   timestamptz NOT NULL,
  validado_por  text        NOT NULL,

  CONSTRAINT trafego_validacao_item_do_mesmo_lote
    FOREIGN KEY (lote_id, item_id)
    REFERENCES public.trafego_lote_item (lote_id, item_id)
    ON DELETE RESTRICT,

  CONSTRAINT trafego_validacao_camada_conhecida
    CHECK (camada IN ('local', 'validate_only', 'pos_criacao')),
  CONSTRAINT trafego_validacao_resultado_conhecido
    CHECK (resultado IN ('passou', 'falhou', 'avisou')),
  CONSTRAINT trafego_validacao_regra_nao_vazia   CHECK (btrim(regra) <> ''),
  CONSTRAINT trafego_validacao_validador_nao_vazio
    CHECK (btrim(validado_por) <> ''),
  -- Mesma doutrina de `trafego_snapshot_falha_tem_motivo`: quem reprova diz o
  -- que viu. Um aviso sem mensagem e pior que nenhum — avisa que falta algo e
  -- nao diz o que.
  CONSTRAINT trafego_validacao_reprova_tem_mensagem
    CHECK (resultado = 'passou' OR btrim(coalesce(mensagem, '')) <> '')
);

CREATE INDEX trafego_validacao_lote_ix
  ON public.trafego_validacao (lote_id, validado_em DESC);
CREATE INDEX trafego_validacao_item_ix
  ON public.trafego_validacao (item_id, validado_em DESC)
  WHERE item_id IS NOT NULL;
CREATE INDEX trafego_validacao_reprovada_ix
  ON public.trafego_validacao (lote_id, camada)
  WHERE resultado <> 'passou';

COMMENT ON TABLE  public.trafego_validacao IS
  'Append-only. Tres camadas declaradas (local, validate_only, pos_criacao). item_id NULO = validacao do lote inteiro.';


-- -----------------------------------------------------------------------------
-- 7. trafego_recibo — CADA tentativa de escrita, escrita ANTES da chamada
-- -----------------------------------------------------------------------------
-- ⚠️ ESTA E A TABELA QUE FECHA O CASO "TIMEOUT MAS CRIOU". O protocolo:
--
--   1. INSERT com `desfecho = 'em_voo'`, `respondido_em` NULO. COMMIT.
--   2. A chamada sai.
--   3. Resposta -> UPDATE para 'sucesso'/'erro', com `respondido_em`.
--      Sem resposta -> UPDATE para 'sem_resposta'.
--      Processo morre -> a linha FICA em 'em_voo'. Isso e a verdade, e e o
--      unico registro possivel de "nao sabemos".
--
-- Escrever o recibo depois da resposta perderia justamente o caso em que a
-- resposta nunca chega — que e o unico caso que este arquivo existe para
-- resolver.
--
-- `request_id` nao e decoracao: e o unico identificador que o suporte da
-- plataforma aceita para investigar uma operacao que "sumiu", e sem ele a
-- reconciliacao de um `em_voo` vira arqueologia.
CREATE TABLE public.trafego_recibo (
  recibo_id        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id          uuid        NOT NULL REFERENCES public.trafego_lote_item (item_id)
                               ON DELETE RESTRICT,

  -- Copiada do item de proposito: o recibo tem de ser legivel sem JOIN quando
  -- alguem esta tentando entender o que aconteceu as 3 da manha.
  idempotency_key  text        NOT NULL,
  tentativa        integer     NOT NULL,
  operacao         text        NOT NULL,

  enviado_em       timestamptz NOT NULL,
  respondido_em    timestamptz,
  desfecho         text        NOT NULL DEFAULT 'em_voo',

  request_id       text,
  resposta_id_externo text,
  resposta_bruta   jsonb,
  erro_codigo      text,
  erro_mensagem    text,

  -- Quota consumida por ESTA chamada. NULL = a plataforma nao informou, e nao
  -- zero: "nao cobrou" e "nao disse quanto cobrou" levam a decisoes opostas
  -- sobre continuar o lote.
  operacoes_consumidas integer,

  CONSTRAINT trafego_recibo_chave_valida
    CHECK (idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$'),
  CONSTRAINT trafego_recibo_tentativa_positiva CHECK (tentativa >= 1),
  CONSTRAINT trafego_recibo_operacao_nao_vazia CHECK (btrim(operacao) <> ''),
  CONSTRAINT trafego_recibo_operacoes_nao_negativas
    CHECK (operacoes_consumidas IS NULL OR operacoes_consumidas >= 0),

  -- Quatro desfechos, e os dois do meio nao sao sinonimos:
  --   em_voo        saiu e ainda nao voltou (ou o processo morreu antes)
  --   sucesso       voltou e criou
  --   erro          voltou e recusou, com codigo
  --   sem_resposta  estourou o tempo. NAO e erro: erro afirma que nao criou.
  CONSTRAINT trafego_recibo_desfecho_conhecido
    CHECK (desfecho IN ('em_voo', 'sucesso', 'erro', 'sem_resposta')),

  -- Um desfecho fechado exige a hora em que fechou; `em_voo` exige que ela nao
  -- exista. Sem os dois lados, "em voo" viraria um rotulo que sobrevive a
  -- resposta e a reconciliacao passaria a reverificar o que ja esta resolvido.
  CONSTRAINT trafego_recibo_resposta_coerente
    CHECK (
      (desfecho = 'em_voo' AND respondido_em IS NULL)
      OR (desfecho <> 'em_voo' AND respondido_em IS NOT NULL)
    ),
  CONSTRAINT trafego_recibo_erro_tem_mensagem
    CHECK (desfecho <> 'erro' OR btrim(coalesce(erro_mensagem, '')) <> ''),
  -- Sucesso sem o id que a plataforma devolveu nao e sucesso: e um `em_voo` que
  -- alguem decidiu chamar de resolvido.
  CONSTRAINT trafego_recibo_sucesso_tem_id
    CHECK (desfecho <> 'sucesso' OR btrim(coalesce(resposta_id_externo, '')) <> ''),
  CONSTRAINT trafego_recibo_resposta_nao_anterior_ao_envio
    CHECK (respondido_em IS NULL OR respondido_em >= enviado_em)
);

CREATE UNIQUE INDEX trafego_recibo_tentativa_ux
  ON public.trafego_recibo (item_id, operacao, tentativa);

-- ⚠️ CAMADA 3 DA DEFESA. NO MAXIMO UM SUCESSO POR (CHAVE, OPERACAO).
-- Um executor com defeito que reenviasse e conseguisse criar duas vezes NAO
-- consegue registrar o segundo sucesso: a transacao aborta e o lote PARA. Uma
-- parada ruidosa e infinitamente melhor que ser dono de duas campanhas sem
-- saber — a segunda gasta verba e disputa o mesmo leilao que a primeira.
CREATE UNIQUE INDEX trafego_recibo_sucesso_unico_ux
  ON public.trafego_recibo (idempotency_key, operacao)
  WHERE desfecho = 'sucesso';

CREATE INDEX trafego_recibo_item_ix
  ON public.trafego_recibo (item_id, enviado_em DESC);
-- A consulta da retomada: "o que ficou em voo?". Parcial porque `em_voo` e o
-- estado raro, e um indice sobre o estado comum nao seria usado.
CREATE INDEX trafego_recibo_em_voo_ix
  ON public.trafego_recibo (enviado_em)
  WHERE desfecho = 'em_voo';
CREATE INDEX trafego_recibo_request_ix
  ON public.trafego_recibo (request_id)
  WHERE request_id IS NOT NULL;

COMMENT ON TABLE  public.trafego_recibo IS
  'Uma linha por tentativa de escrita, criada ANTES da chamada. `em_voo` e o registro honesto de "nao sabemos se criou".';
COMMENT ON COLUMN public.trafego_recibo.desfecho IS
  '`sem_resposta` nao e `erro`: erro afirma que NAO criou; sem_resposta nao afirma nada e obriga verificacao remota.';


-- -----------------------------------------------------------------------------
-- 8. trafego_verificacao — o que a conta respondeu DEPOIS, com carimbo
-- -----------------------------------------------------------------------------
-- A saida do estado `indeterminado` passa OBRIGATORIAMENTE por aqui.
--
-- `achou` e TRI-ESTADO de proposito, e cada valor manda o executor para um
-- lugar diferente:
--   true   existe. Fecha o recibo em voo como sucesso e adota o id observado.
--   false  a leitura foi BOA e nao existe. Libera uma nova tentativa.
--   NULL   NAO CONSEGUI VERIFICAR. Nao libera nada; o item continua
--          `indeterminado` e alguem tenta de novo mais tarde.
--
-- Achatar NULL em `false` seria a forma mais cara de errar deste arquivo
-- inteiro: uma falha de LEITURA viraria autorizacao para criar de novo, e a
-- campanha que ja existe ganharia uma gemea.
--
-- `quantidade_encontrada >= 2` e o alarme de duplicidade JA CONSUMADA: nao ha o
-- que decidir automaticamente ali, e por isso ela e um numero registrado e nao
-- um booleano interpretado.
CREATE TABLE public.trafego_verificacao (
  verificacao_id  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id         uuid        NOT NULL REFERENCES public.trafego_lote_item (item_id)
                              ON DELETE RESTRICT,
  -- Nullable: uma verificacao pode acontecer sem recibo — e o caso da retomada
  -- depois de uma queda que matou o processo antes do INSERT do recibo.
  recibo_id       uuid        REFERENCES public.trafego_recibo (recibo_id)
                              ON DELETE RESTRICT,

  verificado_em   timestamptz NOT NULL,
  verificado_por  text        NOT NULL,
  metodo          text        NOT NULL,

  achou                 boolean,
  motivo                text,
  id_externo_encontrado text,
  quantidade_encontrada integer,

  -- OBSERVADO na conta, para o diff com o declarado.
  estado_externo_observado      text,
  verba_diaria_observada_micros bigint,
  moeda_observada               text,
  divergencia     jsonb       NOT NULL DEFAULT '{}'::jsonb,

  CONSTRAINT trafego_verificacao_verificador_nao_vazio
    CHECK (btrim(verificado_por) <> ''),
  CONSTRAINT trafego_verificacao_metodo_conhecido
    CHECK (metodo IN ('busca_por_marca', 'busca_por_id', 'listagem_da_conta')),
  -- "Nao consegui verificar" sem dizer por que e o mesmo defeito de "sumiu da
  -- conta": um rotulo que esconde a causa.
  CONSTRAINT trafego_verificacao_indeterminada_tem_motivo
    CHECK (achou IS NOT NULL OR btrim(coalesce(motivo, '')) <> ''),
  CONSTRAINT trafego_verificacao_quantidade_nao_negativa
    CHECK (quantidade_encontrada IS NULL OR quantidade_encontrada >= 0),
  -- Achou e nao sabe quantos e uma afirmacao pela metade: ela esconde a
  -- duplicidade, que e o unico motivo pelo qual esta coluna existe.
  CONSTRAINT trafego_verificacao_achou_conta
    CHECK (achou IS NOT TRUE OR coalesce(quantidade_encontrada, 0) >= 1),
  CONSTRAINT trafego_verificacao_nao_achou_zero
    CHECK (achou IS NOT FALSE OR coalesce(quantidade_encontrada, 0) = 0),
  CONSTRAINT trafego_verificacao_moeda_iso
    CHECK (moeda_observada IS NULL OR moeda_observada ~ '^[A-Z]{3}$'),
  CONSTRAINT trafego_verificacao_verba_nao_negativa
    CHECK (verba_diaria_observada_micros IS NULL
           OR verba_diaria_observada_micros >= 0),
  -- REGRA A aplicada ao dinheiro observado.
  CONSTRAINT trafego_verificacao_verba_sem_moeda
    CHECK (verba_diaria_observada_micros IS NULL OR moeda_observada IS NOT NULL)
);

CREATE INDEX trafego_verificacao_item_ix
  ON public.trafego_verificacao (item_id, verificado_em DESC);
CREATE INDEX trafego_verificacao_duplicidade_ix
  ON public.trafego_verificacao (item_id)
  WHERE quantidade_encontrada IS NOT NULL AND quantidade_encontrada >= 2;

COMMENT ON TABLE  public.trafego_verificacao IS
  'O que a conta respondeu depois da escrita. `achou` e tri-estado: NULL = nao consegui verificar, e NULL nunca libera nova tentativa.';
COMMENT ON COLUMN public.trafego_verificacao.achou IS
  'true = existe; false = leitura boa e nao existe; NULL = nao consegui ler. Achatar NULL em false criaria a campanha gemea.';


-- -----------------------------------------------------------------------------
-- 9. trafego_rollback — o desfazer, com o estado anterior guardado ANTES
-- -----------------------------------------------------------------------------
-- `estado_anterior` e NOT NULL e e capturado no momento da SOLICITACAO, nao no
-- da execucao. A diferenca e a que decide se o rollback funciona: capturado na
-- execucao, ele leria um estado que a propria falha ja corrompeu.
--
-- `estrategia` reconhece que "desfazer" nao e uma coisa so:
--   pausar           o desfazer SEGURO. Para o gasto e preserva a campanha.
--   remover          terminal no Google Ads. Nao ha volta, e por isso ele nao e
--                    o padrao de nada.
--   restaurar_valor  devolve orcamento/lance ao valor anterior.
CREATE TABLE public.trafego_rollback (
  rollback_id     uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id         uuid        NOT NULL REFERENCES public.trafego_lote_item (item_id)
                              ON DELETE RESTRICT,

  estrategia      text        NOT NULL,
  motivo          text        NOT NULL,
  estado_anterior jsonb       NOT NULL,

  solicitado_por  text        NOT NULL,
  solicitado_em   timestamptz NOT NULL DEFAULT now(),

  desfecho        text        NOT NULL DEFAULT 'pendente',
  executado_em    timestamptz,
  recibo_id       uuid        REFERENCES public.trafego_recibo (recibo_id)
                              ON DELETE RESTRICT,
  erro_mensagem   text,

  CONSTRAINT trafego_rollback_estrategia_conhecida
    CHECK (estrategia IN ('pausar', 'remover', 'restaurar_valor')),
  CONSTRAINT trafego_rollback_motivo_nao_vazio CHECK (btrim(motivo) <> ''),
  CONSTRAINT trafego_rollback_solicitante_nao_vazio
    CHECK (btrim(solicitado_por) <> ''),
  CONSTRAINT trafego_rollback_estado_anterior_e_objeto
    CHECK (jsonb_typeof(estado_anterior) = 'object'),
  CONSTRAINT trafego_rollback_desfecho_conhecido
    CHECK (desfecho IN ('pendente', 'sucesso', 'erro', 'sem_resposta')),
  CONSTRAINT trafego_rollback_desfecho_coerente
    CHECK (
      (desfecho = 'pendente' AND executado_em IS NULL)
      OR (desfecho <> 'pendente' AND executado_em IS NOT NULL)
    ),
  CONSTRAINT trafego_rollback_erro_tem_mensagem
    CHECK (desfecho <> 'erro' OR btrim(coalesce(erro_mensagem, '')) <> '')
);

-- Um rollback pendente por item. Dois seriam duas ordens contraditorias sobre a
-- mesma campanha, e o executor teria de escolher.
CREATE UNIQUE INDEX trafego_rollback_pendente_ux
  ON public.trafego_rollback (item_id)
  WHERE desfecho = 'pendente';
CREATE INDEX trafego_rollback_item_ix
  ON public.trafego_rollback (item_id, solicitado_em DESC);

COMMENT ON TABLE  public.trafego_rollback IS
  'O desfazer de um item criado. `estado_anterior` e capturado na SOLICITACAO, nao na execucao — na execucao ele ja estaria corrompido.';


-- -----------------------------------------------------------------------------
-- 10. trafego_lote_transicao — o diario append-only de toda mudanca de estado
-- -----------------------------------------------------------------------------
-- ⚠️ Um gatilho que ESCREVE merece justificativa, porque foi um gatilho que
-- criou o defeito de ADR-10. A diferenca e de natureza: aquele SOBRESCREVIA uma
-- declaracao da aplicacao, tornando-a inalcancavel. Este APENDA uma linha num
-- diario que ninguem le como verdade de dominio. Nao deriva, nao decide, nao
-- reescreve.
--
-- Por que gatilho e nao disciplina do chamador: "histórico preservado" que
-- depende de alguem lembrar de gravar nao e historico, e a primeira coisa que
-- se esquece e o registro da transicao que deu errado.
CREATE TABLE public.trafego_lote_transicao (
  transicao_id  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  lote_id       uuid        NOT NULL,
  item_id       uuid,

  de            text,
  para          text        NOT NULL,
  em            timestamptz NOT NULL DEFAULT now(),
  por           text,
  motivo        text,

  CONSTRAINT trafego_transicao_para_nao_vazio CHECK (btrim(para) <> ''),
  CONSTRAINT trafego_transicao_muda_alguma_coisa
    CHECK (de IS DISTINCT FROM para)
);

-- Sem FK de proposito, pela MESMA razao de `trafego_evento.volc_campaign_id`: o
-- diario tem de conseguir registrar a transicao de algo que, no fim da
-- transacao, pode nao existir mais. Uma FK faria o registro do problema falhar
-- pela mesma causa que o problema.
CREATE INDEX trafego_transicao_lote_ix
  ON public.trafego_lote_transicao (lote_id, em DESC);
CREATE INDEX trafego_transicao_item_ix
  ON public.trafego_lote_transicao (item_id, em DESC)
  WHERE item_id IS NOT NULL;

COMMENT ON TABLE  public.trafego_lote_transicao IS
  'Diario append-only de toda mudanca de estado de lote e item. Escrito por gatilho — historico que depende de alguem lembrar nao e historico.';


-- -----------------------------------------------------------------------------
-- 11. GATILHOS — as regras que so o banco consegue garantir
-- -----------------------------------------------------------------------------

-- 11.1 A intencao e uma declaracao. Declaracao nao se reescreve.
CREATE OR REPLACE FUNCTION public.trafego_intencao_imutavel()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION
      'trafego_intencao: DELETE recusado. A intencao explica por que a campanha existe; apaga-la deixa a campanha sem causa.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  RAISE EXCEPTION
    'trafego_intencao: a declaracao e imutavel. Mudou a intencao? E outra intencao, com outro id, e um lote novo apontando para ela — reescrever a pergunta depois da resposta faz o par contar uma historia que ninguem viveu.'
    USING ERRCODE = 'restrict_violation';
END
$funcao$;

CREATE TRIGGER trafego_intencao_imutavel
  BEFORE UPDATE OR DELETE ON public.trafego_intencao
  FOR EACH ROW EXECUTE FUNCTION public.trafego_intencao_imutavel();


-- 11.2 O blueprint e versionado: so a aposentadoria muda, e uma vez so.
CREATE OR REPLACE FUNCTION public.trafego_blueprint_so_aposenta()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION
      'trafego_blueprint: DELETE recusado. Um lote guarda o blueprint_id que usou; apagar a versao apaga a explicacao do que foi criado.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.blueprint_id IS DISTINCT FROM OLD.blueprint_id
     OR NEW.chave      IS DISTINCT FROM OLD.chave
     OR NEW.versao     IS DISTINCT FROM OLD.versao
     OR NEW.plataforma IS DISTINCT FROM OLD.plataforma
     OR NEW.canal      IS DISTINCT FROM OLD.canal
     OR NEW.corpo      IS DISTINCT FROM OLD.corpo
     OR NEW.declarado_por IS DISTINCT FROM OLD.declarado_por
     OR NEW.declarado_em  IS DISTINCT FROM OLD.declarado_em
  THEN
    RAISE EXCEPTION
      'trafego_blueprint: versao publicada e imutavel. Para mudar o molde, publique (chave, versao+1) — reescrever esta linha mudaria retroativamente o que os lotes antigos dizem ter usado.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF OLD.retirado_em IS NOT NULL
     AND (NEW.retirado_em IS DISTINCT FROM OLD.retirado_em
          OR NEW.retirado_por IS DISTINCT FROM OLD.retirado_por) THEN
    RAISE EXCEPTION
      'trafego_blueprint: esta versao ja foi aposentada em % por %; o registro nao se reescreve.',
      OLD.retirado_em, OLD.retirado_por
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_blueprint_so_aposenta
  BEFORE UPDATE OR DELETE ON public.trafego_blueprint
  FOR EACH ROW EXECUTE FUNCTION public.trafego_blueprint_so_aposenta();


-- 11.3 A maquina de estados do LOTE, e a aprovacao humana como estrutura.
--
-- A lista de transicoes vive aqui e em `backend/app/trafego/lote.py:
-- TRANSICOES_DO_LOTE`. Sao DUAS definicoes da mesma regra, e isso e um risco
-- conhecido — o mesmo de `atencao` na v9_01. O antidoto e igual: um teste
-- (`backend/tests/test_lote.py`) compara as duas listas termo a termo.
CREATE OR REPLACE FUNCTION public.trafego_lote_estado_valido()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
DECLARE
  permitidas CONSTANT text[] := ARRAY[
    'preparando->validando',            'preparando->cancelado',
    'validando->preparando',            'validando->aguardando_aprovacao',
    'validando->cancelado',
    'aguardando_aprovacao->aprovado',   'aguardando_aprovacao->recusado',
    'aguardando_aprovacao->cancelado',
    'aprovado->executando',             'aprovado->cancelado',
    'executando->concluido',            'executando->concluido_com_falhas',
    'executando->interrompido',
    'interrompido->executando',         'interrompido->cancelado',
    'concluido_com_falhas->executando', 'concluido_com_falhas->revertido',
    'concluido->revertido'
  ];
BEGIN
  IF NEW.estado IS DISTINCT FROM OLD.estado THEN
    IF NOT (OLD.estado || '->' || NEW.estado = ANY (permitidas)) THEN
      RAISE EXCEPTION
        'trafego_lote: transicao % -> % nao existe. Um estado sem caminho de saida declarado e um lote que ninguem consegue destravar sem UPDATE a mao.',
        OLD.estado, NEW.estado
        USING ERRCODE = 'restrict_violation';
    END IF;

    -- ⚠️ APROVACAO HUMANA, EM FORMA DE SCHEMA. Nao ha caminho de execucao que
    -- passe por cima disto, e nao existe "aprovacao automatica" — nem como
    -- valor, nem como default. E o ADR-09 ("o sistema sugere; o operador
    -- confirma") deixando de depender de um `if` no backend.
    IF NEW.estado = 'executando' AND NEW.aprovado_em IS NULL THEN
      RAISE EXCEPTION
        'trafego_lote: execucao sem aprovacao humana registrada. Preencha aprovado_por/aprovado_em antes — o sistema sugere, o operador confirma.'
        USING ERRCODE = 'restrict_violation';
    END IF;
  END IF;

  -- A aprovacao, uma vez dada, nao se reescreve: ela e a autorizacao que o
  -- recibo cita. Reescrever quem aprovou muda quem responde pelo gasto.
  IF OLD.aprovado_em IS NOT NULL
     AND (NEW.aprovado_em  IS DISTINCT FROM OLD.aprovado_em
          OR NEW.aprovado_por IS DISTINCT FROM OLD.aprovado_por) THEN
    RAISE EXCEPTION
      'trafego_lote: este lote ja foi aprovado em % por %; a autorizacao nao se reescreve.',
      OLD.aprovado_em, OLD.aprovado_por
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.lote_id     IS DISTINCT FROM OLD.lote_id
     OR NEW.intencao_id  IS DISTINCT FROM OLD.intencao_id
     OR NEW.blueprint_id IS DISTINCT FROM OLD.blueprint_id
     OR NEW.plataforma    IS DISTINCT FROM OLD.plataforma
     OR NEW.conta_externa IS DISTINCT FROM OLD.conta_externa
     OR NEW.canal         IS DISTINCT FROM OLD.canal THEN
    RAISE EXCEPTION
      'trafego_lote: intencao, blueprint, plataforma, conta e canal sao a identidade do lote e nao mudam. Outro alvo e outro lote.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- REGRA A no relogio da quota: uma leitura retroativa sobrescreveria a medida
  -- nova com a velha, e o executor decidiria "ainda posso gastar quota" olhando
  -- para um numero de antes.
  IF NEW.quota_lida_em IS NOT NULL AND OLD.quota_lida_em IS NOT NULL
     AND NEW.quota_lida_em < OLD.quota_lida_em THEN
    RAISE EXCEPTION
      'trafego_lote: leitura de quota de % e mais velha que a corrente (%).',
      NEW.quota_lida_em, OLD.quota_lida_em
      USING ERRCODE = 'restrict_violation';
  END IF;

  NEW.atualizado_em := now();
  RETURN NEW;
END
$funcao$;

-- 11.x O lote nao inventa a conta nem o canal que ele diz seguir.
--
-- ⚠️ `trafego_lote` carrega `plataforma`, `conta_externa` e `canal` — que ja
-- existem em `trafego_intencao` (as duas primeiras) e em `trafego_blueprint` (a
-- ultima). A duplicacao e proposital: ela deixa a leitura barata e o indice
-- direto. Mas duplicar sem conferir e criar uma segunda fonte da mesma verdade,
-- e a segunda so precisa estar errada uma vez.
--
-- Sem esta guarda, um lote podia declarar que segue a intencao X — cuja conta e
-- a A — e gravar a conta B. Todo o resto do sistema continuaria coerente
-- consigo mesmo: os itens herdam a conta do LOTE, a chave de idempotencia usa a
-- conta do LOTE, e o recibo tambem. A intencao, que e o unico lugar onde o teto
-- de gasto e o "por que" moram, ficaria falando de outra conta — e o teto
-- aprovado para uma conta protegeria outra.
CREATE OR REPLACE FUNCTION public.trafego_lote_segue_a_intencao()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
DECLARE
  int_plataforma text;
  int_conta      text;
  bp_plataforma  text;
  bp_canal       text;
BEGIN
  SELECT i.plataforma, i.conta_externa INTO int_plataforma, int_conta
    FROM public.trafego_intencao i WHERE i.intencao_id = NEW.intencao_id;

  IF NEW.plataforma IS DISTINCT FROM int_plataforma
     OR NEW.conta_externa IS DISTINCT FROM int_conta THEN
    RAISE EXCEPTION
      'trafego_lote: a intencao e de %/% e o lote declara %/%. O teto de gasto e o porque moram na intencao; um lote que aponta para outra conta gasta sob uma autorizacao que nao e dele.',
      int_plataforma, int_conta, NEW.plataforma, NEW.conta_externa
      USING ERRCODE = 'restrict_violation';
  END IF;

  SELECT b.plataforma, b.canal INTO bp_plataforma, bp_canal
    FROM public.trafego_blueprint b WHERE b.blueprint_id = NEW.blueprint_id;

  IF NEW.canal IS DISTINCT FROM bp_canal
     OR NEW.plataforma IS DISTINCT FROM bp_plataforma THEN
    RAISE EXCEPTION
      'trafego_lote: o blueprint e de %/% e o lote declara %/%. O blueprint e a configuracao POR CANAL; segui-lo em outro canal e seguir uma configuracao que nao descreve o que vai subir.',
      bp_plataforma, bp_canal, NEW.plataforma, NEW.canal
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_lote_segue_a_intencao
  BEFORE INSERT OR UPDATE OF intencao_id, blueprint_id, plataforma, conta_externa, canal
  ON public.trafego_lote
  FOR EACH ROW EXECUTE FUNCTION public.trafego_lote_segue_a_intencao();


CREATE TRIGGER trafego_lote_estado_valido
  BEFORE UPDATE ON public.trafego_lote
  FOR EACH ROW EXECUTE FUNCTION public.trafego_lote_estado_valido();

CREATE OR REPLACE FUNCTION public.trafego_lote_sem_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  RAISE EXCEPTION
    'trafego_lote: DELETE recusado. Lote abandonado recebe estado `cancelado` com motivo; apagar destroi o rastro de uma verba que talvez tenha sido gasta.'
    USING ERRCODE = 'restrict_violation';
END
$funcao$;

CREATE TRIGGER trafego_lote_sem_delete
  BEFORE DELETE ON public.trafego_lote
  FOR EACH ROW EXECUTE FUNCTION public.trafego_lote_sem_delete();


-- 11.4 A maquina de estados do ITEM — e a guarda que fecha o "timeout mas criou"
CREATE OR REPLACE FUNCTION public.trafego_item_estado_valido()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
DECLARE
  permitidas CONSTANT text[] := ARRAY[
    'planejado->validado_local',        'planejado->falhou',
    'planejado->cancelada',
    'validado_local->validado_remoto',  'validado_local->planejado',
    'validado_local->falhou',           'validado_local->cancelada',
    'validado_remoto->aprovado',        'validado_remoto->falhou',
    'validado_remoto->cancelada',
    'aprovado->criando',                'aprovado->cancelada',
    'criando->criada_pausada',          'criando->falhou',
    'criando->indeterminado',
    'indeterminado->criada_pausada',    'indeterminado->criando',
    'indeterminado->falhou',
    'criada_pausada->verificada',       'criada_pausada->falhou',
    'criada_pausada->revertida',
    'verificada->canario',              'verificada->ativa',
    'verificada->revertida',
    'canario->ativa',                   'canario->revertida',
    'ativa->revertida',
    'falhou->criando',                  'falhou->planejado',
    'falhou->cancelada'
  ];
  em_voo integer;
BEGIN
  IF NEW.estado IS DISTINCT FROM OLD.estado THEN
    IF NOT (OLD.estado || '->' || NEW.estado = ANY (permitidas)) THEN
      RAISE EXCEPTION
        'trafego_lote_item: transicao % -> % nao existe.', OLD.estado, NEW.estado
        USING ERRCODE = 'restrict_violation';
    END IF;

    -- ⚠️⚠️ CAMADA 2 DA DEFESA CONTRA "TIMEOUT MAS CRIOU".
    --
    -- `falhou` e um convite a retomada: o executor ve o estado, conclui que
    -- nada foi criado, e manda de novo. Com um recibo ainda EM VOO, essa
    -- conclusao e um palpite — e o palpite errado cria a segunda campanha,
    -- gastando verba de verdade e disputando o mesmo leilao que a primeira.
    --
    -- O estado honesto e `indeterminado`, e a unica saida dele e uma
    -- verificacao remota registrada em `trafego_verificacao`.
    -- ⚠️ `sem_resposta` NAO e um desfecho conhecido: e a ignorancia CARIMBADA.
    --
    -- A versao anterior contava so `desfecho = 'em_voo'`. Fechar o recibo como
    -- `sem_resposta` zerava a contagem e reabria o caminho para `falhou` — que
    -- e o convite a retomada. O executor que desiste de esperar e escreve
    -- `sem_resposta` estaria, sem saber, autorizando a segunda campanha.
    --
    -- Os dois desfechos significam a MESMA coisa para esta guarda: nao sabemos
    -- se a chamada criou. `erro` e `sucesso` sao respostas; estes dois nao sao.
    IF NEW.estado = 'falhou' THEN
      SELECT count(*) INTO em_voo
        FROM public.trafego_recibo r
       WHERE r.item_id = NEW.item_id
         AND r.desfecho IN ('em_voo', 'sem_resposta');
      IF em_voo > 0 THEN
        RAISE EXCEPTION
          'trafego_lote_item: % recibo(s) em voo ou sem resposta — este item nao pode ser declarado `falhou`. Nao sabemos se a chamada criou. Use `indeterminado` e verifique na conta.',
          em_voo
          USING ERRCODE = 'restrict_violation';
      END IF;
    END IF;

    -- ⚠️⚠️ CAMADA 3: a unica saida de `indeterminado` de volta para o envio.
    --
    -- `indeterminado->criando` estava na lista de transicoes permitidas SEM
    -- exigir nada. O comentario acima ja dizia que "a unica saida dele e uma
    -- verificacao remota registrada em trafego_verificacao" — e o codigo nao
    -- exigia essa verificacao. Um executor podia sair de `indeterminado` direto
    -- para `criando` e reenviar o mesmo plano, que e literalmente o caminho que
    -- as outras duas camadas existem para fechar.
    --
    -- A verificacao precisa ter CONCLUIDO: `achou` nulo significa "nao consegui
    -- ler", e nao consegui ler nao libera nova tentativa. E `achou = true`
    -- tambem nao libera: se a campanha ESTA la, o caminho e `criada_pausada`,
    -- nunca reenviar.
    IF OLD.estado = 'indeterminado' AND NEW.estado = 'criando' THEN
      IF NOT EXISTS (
        SELECT 1 FROM public.trafego_verificacao v
         WHERE v.item_id = NEW.item_id
           AND v.achou IS NOT NULL
           AND v.achou = false
      ) THEN
        RAISE EXCEPTION
          'trafego_lote_item: sair de `indeterminado` para `criando` exige uma verificacao na conta que tenha CONCLUIDO que a campanha nao existe (achou = false). Sem ela, reenviar e apostar — e a aposta errada cria a segunda campanha no mesmo leilao.'
          USING ERRCODE = 'restrict_violation';
      END IF;
      -- E se ainda houver recibo sem desfecho, a verificacao nao alcanca o que
      -- pode estar em transito agora.
      SELECT count(*) INTO em_voo
        FROM public.trafego_recibo r
       WHERE r.item_id = NEW.item_id
         AND r.desfecho IN ('em_voo', 'sem_resposta');
      IF em_voo > 0 THEN
        RAISE EXCEPTION
          'trafego_lote_item: % recibo(s) em voo ou sem resposta — nao da para reenviar enquanto uma chamada anterior pode estar a caminho.',
          em_voo
          USING ERRCODE = 'restrict_violation';
      END IF;
    END IF;
  END IF;

  IF NEW.item_id IS DISTINCT FROM OLD.item_id
     OR NEW.lote_id IS DISTINCT FROM OLD.lote_id
     OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key THEN
    RAISE EXCEPTION
      'trafego_lote_item: item, lote e idempotency_key sao a identidade do item. Trocar a chave e perder o unico elo com o que ja foi enviado a plataforma.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- O PLANO E DECLARACAO (regra D). Ele pode ser corrigido ENQUANTO nada foi
  -- enviado; depois disso, mudar o plano faria o recibo descrever uma coisa e o
  -- item descrever outra.
  IF NEW.plano IS DISTINCT FROM OLD.plano
     AND OLD.estado NOT IN ('planejado', 'validado_local') THEN
    RAISE EXCEPTION
      'trafego_lote_item: o plano nao muda depois de %; o recibo passaria a descrever outra coisa. Cancele este item e crie outro — a chave nova sai do conteudo novo.',
      OLD.estado
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- A identidade da instancia (ADR-02) e atribuivel UMA vez. Trocar a campanha
  -- de um item ja criado levaria junto recibo, verificacao e rollback.
  IF OLD.volc_campaign_id IS NOT NULL
     AND NEW.volc_campaign_id IS DISTINCT FROM OLD.volc_campaign_id THEN
    RAISE EXCEPTION
      'trafego_lote_item: volc_campaign_id ja atribuido (%) e estavel; nao vira %.',
      OLD.volc_campaign_id, coalesce(NEW.volc_campaign_id, 'NULL')
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- REGRA A no carimbo do observado.
  IF NEW.id_externo_lido_em IS NOT NULL AND OLD.id_externo_lido_em IS NOT NULL
     AND NEW.id_externo_lido_em < OLD.id_externo_lido_em THEN
    RAISE EXCEPTION
      'trafego_lote_item: leitura de % e mais velha que a corrente (%).',
      NEW.id_externo_lido_em, OLD.id_externo_lido_em
      USING ERRCODE = 'restrict_violation';
  END IF;

  NEW.atualizado_em := now();
  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_item_estado_valido
  BEFORE UPDATE ON public.trafego_lote_item
  FOR EACH ROW EXECUTE FUNCTION public.trafego_item_estado_valido();

CREATE OR REPLACE FUNCTION public.trafego_item_sem_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  RAISE EXCEPTION
    'trafego_lote_item: DELETE recusado. Item abandonado recebe estado `cancelada`; apagar destroi a chave de idempotencia, que e o unico elo com o que ja pode ter sido criado na conta.'
    USING ERRCODE = 'restrict_violation';
END
$funcao$;

CREATE TRIGGER trafego_item_sem_delete
  BEFORE DELETE ON public.trafego_lote_item
  FOR EACH ROW EXECUTE FUNCTION public.trafego_item_sem_delete();


-- 11.5 O recibo fecha UMA vez. Depois disso ele e historia.
CREATE OR REPLACE FUNCTION public.trafego_recibo_fecha_uma_vez()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION
      'trafego_recibo: DELETE recusado. O recibo e a unica prova de que uma chamada saiu — inclusive a que nunca voltou.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.recibo_id       IS DISTINCT FROM OLD.recibo_id
     OR NEW.item_id      IS DISTINCT FROM OLD.item_id
     OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
     OR NEW.tentativa    IS DISTINCT FROM OLD.tentativa
     OR NEW.operacao     IS DISTINCT FROM OLD.operacao
     OR NEW.enviado_em   IS DISTINCT FROM OLD.enviado_em THEN
    RAISE EXCEPTION
      'trafego_recibo: o cabecalho do recibo (item, chave, tentativa, operacao, envio) e imutavel. Outra chamada e outro recibo.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- `em_voo` -> desfecho fechado e a UNICA transicao. Reabrir um recibo fechado
  -- faria a reconciliacao reverificar o que ja esta resolvido, e — pior —
  -- permitiria transformar um `sucesso` em `erro`, apagando a prova de que a
  -- campanha existe.
  IF OLD.desfecho <> 'em_voo' AND NEW.desfecho IS DISTINCT FROM OLD.desfecho THEN
    RAISE EXCEPTION
      'trafego_recibo: este recibo ja fechou como % em %; ele nao reabre. Uma nova tentativa e um recibo novo.',
      OLD.desfecho, OLD.respondido_em
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_recibo_fecha_uma_vez
  BEFORE UPDATE OR DELETE ON public.trafego_recibo
  FOR EACH ROW EXECUTE FUNCTION public.trafego_recibo_fecha_uma_vez();


-- 11.6 Append-only puro: validacao, verificacao e o diario de transicoes.
CREATE OR REPLACE FUNCTION public.trafego_lote_append_only()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  RAISE EXCEPTION
    '%: append-only, % recusado. O que foi observado nao deixa de ter sido observado; corrija com uma linha nova.',
    TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'restrict_violation';
END
$funcao$;

CREATE TRIGGER trafego_validacao_append_only
  BEFORE UPDATE OR DELETE ON public.trafego_validacao
  FOR EACH ROW EXECUTE FUNCTION public.trafego_lote_append_only();

CREATE TRIGGER trafego_verificacao_append_only
  BEFORE UPDATE OR DELETE ON public.trafego_verificacao
  FOR EACH ROW EXECUTE FUNCTION public.trafego_lote_append_only();

CREATE TRIGGER trafego_transicao_append_only
  BEFORE UPDATE OR DELETE ON public.trafego_lote_transicao
  FOR EACH ROW EXECUTE FUNCTION public.trafego_lote_append_only();

CREATE TRIGGER trafego_asset_sem_delete
  BEFORE DELETE ON public.trafego_lote_asset
  FOR EACH ROW EXECUTE FUNCTION public.trafego_lote_append_only();


-- 11.7 O rollback fecha uma vez, como o recibo.
CREATE OR REPLACE FUNCTION public.trafego_rollback_fecha_uma_vez()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION
      'trafego_rollback: DELETE recusado. O pedido de desfazer e parte da trilha, tenha ele funcionado ou nao.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.item_id IS DISTINCT FROM OLD.item_id
     OR NEW.estrategia      IS DISTINCT FROM OLD.estrategia
     OR NEW.estado_anterior IS DISTINCT FROM OLD.estado_anterior
     OR NEW.solicitado_por  IS DISTINCT FROM OLD.solicitado_por
     OR NEW.solicitado_em   IS DISTINCT FROM OLD.solicitado_em THEN
    RAISE EXCEPTION
      'trafego_rollback: o pedido e imutavel — inclusive `estado_anterior`, que e o que torna o desfazer possivel.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF OLD.desfecho <> 'pendente' AND NEW.desfecho IS DISTINCT FROM OLD.desfecho THEN
    RAISE EXCEPTION
      'trafego_rollback: este rollback ja fechou como % em %; ele nao reabre.',
      OLD.desfecho, OLD.executado_em
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_rollback_fecha_uma_vez
  BEFORE UPDATE OR DELETE ON public.trafego_rollback
  FOR EACH ROW EXECUTE FUNCTION public.trafego_rollback_fecha_uma_vez();


-- 11.8 O diario, escrito por gatilho.
CREATE OR REPLACE FUNCTION public.trafego_lote_registra_transicao()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF TG_TABLE_NAME = 'trafego_lote' THEN
    IF TG_OP = 'INSERT' THEN
      INSERT INTO public.trafego_lote_transicao (lote_id, de, para, por)
        VALUES (NEW.lote_id, NULL, NEW.estado, NEW.criado_por);
    ELSIF NEW.estado IS DISTINCT FROM OLD.estado THEN
      INSERT INTO public.trafego_lote_transicao (lote_id, de, para, por, motivo)
        VALUES (NEW.lote_id, OLD.estado, NEW.estado,
                coalesce(NEW.aprovado_por, NEW.cancelado_por, NEW.criado_por),
                NEW.cancelado_motivo);
    END IF;
  ELSE
    IF TG_OP = 'INSERT' THEN
      INSERT INTO public.trafego_lote_transicao (lote_id, item_id, de, para)
        VALUES (NEW.lote_id, NEW.item_id, NULL, NEW.estado);
    ELSIF NEW.estado IS DISTINCT FROM OLD.estado THEN
      INSERT INTO public.trafego_lote_transicao
        (lote_id, item_id, de, para, por, motivo)
        VALUES (NEW.lote_id, NEW.item_id, OLD.estado, NEW.estado,
                NEW.cancelado_por, NEW.erro_mensagem);
    END IF;
  END IF;
  RETURN NULL;
END
$funcao$;

CREATE TRIGGER trafego_lote_registra_transicao
  AFTER INSERT OR UPDATE ON public.trafego_lote
  FOR EACH ROW EXECUTE FUNCTION public.trafego_lote_registra_transicao();

CREATE TRIGGER trafego_item_registra_transicao
  AFTER INSERT OR UPDATE ON public.trafego_lote_item
  FOR EACH ROW EXECUTE FUNCTION public.trafego_lote_registra_transicao();

COMMENT ON FUNCTION public.trafego_lote_registra_transicao() IS
  'Apenda uma linha por mudanca de estado de lote ou item. Nao deriva nem sobrescreve nada — ao contrario do gatilho de E-08.';


-- -----------------------------------------------------------------------------
-- 12. PROJECOES DE LEITURA — o painel montado NO BANCO
-- -----------------------------------------------------------------------------
-- Mesma razao da v9_01: montado no cliente, o painel do lote vira uma consulta
-- por item — o N+1, que some do plano de consulta e reaparece como lentidao sem
-- causa visivel.
--
-- `security_invoker = true` nas duas: sem ele a view roda com o privilegio do
-- DONO e o RLS das dez tabelas de baixo deixa de valer.

CREATE VIEW public.trafego_item_situacao
  WITH (security_invoker = true) AS
SELECT
  i.item_id,
  i.lote_id,
  i.ordem,
  i.idempotency_key,
  i.rotulo,
  i.estado,
  i.tentativas,
  i.volc_campaign_id,
  i.id_externo,
  i.id_externo_lido_em,
  i.erro_codigo,
  i.erro_mensagem,
  i.erro_em,

  -- O recibo em voo, se houver. E a pergunta que a retomada faz primeiro, e ela
  -- precisa resolver no banco: em Python ela viraria uma consulta por item.
  r.recibo_id       AS recibo_em_voo_id,
  r.enviado_em      AS recibo_em_voo_desde,

  v.verificado_em   AS ultima_verificacao_em,
  v.achou           AS ultima_verificacao_achou,
  v.quantidade_encontrada AS ultima_verificacao_quantidade,

  -- ⚠️ O QUE FAZER A SEGUIR, derivado de FATOS e nada mais. Esta expressao e a
  -- traducao literal de `backend/app/trafego/lote.py:proxima_acao()`, e
  -- `backend/tests/test_lote_idempotencia.py` compara as duas linha a linha.
  -- Se divergirem, a tela e o executor passam a discordar sobre o mesmo item —
  -- e nao ha como saber qual esta certo.
  --
  -- A ordem dos ramos e a ordem da seguranca:
  --  1. recibo em voo  -> VERIFICAR. Nunca reenviar: pode ter criado.
  --  2. indeterminado  -> VERIFICAR, mesmo sem recibo (queda antes do INSERT).
  --  3. duplicidade    -> PARAR e chamar gente. Nao ha escolha automatica
  --                       correta entre duas campanhas ja criadas.
  --  4. o resto        -> o caminho normal do ciclo.
  CASE
    WHEN r.recibo_id IS NOT NULL                       THEN 'verificar'
    WHEN i.estado = 'indeterminado'                    THEN 'verificar'
    WHEN coalesce(v.quantidade_encontrada, 0) >= 2     THEN 'parar_duplicidade'
    WHEN i.estado IN ('cancelada', 'revertida', 'ativa') THEN 'nada'
    WHEN i.estado = 'falhou'                           THEN 'decidir_retomada'
    WHEN i.estado = 'criada_pausada'                   THEN 'verificar'
    WHEN i.estado = 'verificada'                       THEN 'ativar_canario'
    WHEN i.estado = 'canario'                          THEN 'ativar'
    WHEN i.estado = 'aprovado'                         THEN 'criar'
    ELSE 'preparar'
  END AS proxima_acao

FROM public.trafego_lote_item i

-- LATERAL e nao LEFT JOIN simples: precisamos de UMA linha (a mais antiga em
-- voo, que e a que preocupa), e um LEFT JOIN sem limite multiplicaria o item
-- por quantos recibos em voo existissem — inflando qualquer contagem feita
-- sobre esta view.
LEFT JOIN LATERAL (
  SELECT rr.recibo_id, rr.enviado_em
    FROM public.trafego_recibo rr
   WHERE rr.item_id = i.item_id AND rr.desfecho = 'em_voo'
   ORDER BY rr.enviado_em ASC
   LIMIT 1
) r ON true

LEFT JOIN LATERAL (
  SELECT vv.verificado_em, vv.achou, vv.quantidade_encontrada
    FROM public.trafego_verificacao vv
   WHERE vv.item_id = i.item_id
   ORDER BY vv.verificado_em DESC
   LIMIT 1
) v ON true;

COMMENT ON VIEW public.trafego_item_situacao IS
  'Item + recibo em voo + ultima verificacao, com `proxima_acao` traduzida de lote.proxima_acao(). Recibo em voo SEMPRE manda verificar, nunca reenviar.';


CREATE VIEW public.trafego_lote_painel
  WITH (security_invoker = true) AS
SELECT
  l.lote_id,
  l.intencao_id,
  l.blueprint_id,
  l.plataforma,
  l.conta_externa,
  l.canal,
  l.estado,
  l.limite_concorrencia,
  l.quota_orcada,
  l.quota_consumida,
  l.quota_lida_em,
  l.aprovado_por,
  l.aprovado_em,
  l.cancelado_em,
  l.resumo_humano,
  l.criado_por,
  l.criado_em,
  l.atualizado_em,

  i.total,
  i.criadas,
  i.falhas,
  i.indeterminados,
  i.cancelados,
  i.em_voo,

  -- ⚠️ `pede_atencao` do lote. Como na v9_01, cada termo e um FATO, e nao uma
  -- opiniao sobre o lote:
  --  1. algum item indeterminado, ou algum recibo em voo -> nao sabemos o que
  --     existe na conta, e nao saber e o motivo mais forte para olhar;
  --  2. o lote parou no meio (`interrompido`);
  --  3. terminou com falhas — que e desfecho normal, e mesmo assim exige um
  --     humano para decidir retomar ou desistir.
  (i.indeterminados > 0 OR i.em_voo > 0
   OR l.estado = 'interrompido'
   OR l.estado = 'concluido_com_falhas') AS atencao

FROM public.trafego_lote l
LEFT JOIN LATERAL (
  SELECT
    count(*)                                                      AS total,
    count(*) FILTER (WHERE s.estado IN ('criada_pausada', 'verificada',
                                        'canario', 'ativa'))      AS criadas,
    count(*) FILTER (WHERE s.estado = 'falhou')                   AS falhas,
    count(*) FILTER (WHERE s.estado = 'indeterminado')            AS indeterminados,
    count(*) FILTER (WHERE s.estado = 'cancelada')                AS cancelados,
    count(*) FILTER (WHERE s.recibo_em_voo_id IS NOT NULL)        AS em_voo
    FROM public.trafego_item_situacao s
   WHERE s.lote_id = l.lote_id
) i ON true;

COMMENT ON VIEW public.trafego_lote_painel IS
  'Lote + contagem por situacao dos itens + `atencao`. Nao decide nada alem disso; o erro continua sendo do item.';


-- -----------------------------------------------------------------------------
-- 13. SEGURANCA — REVOKE nominal, RLS forcada, grants minimos
-- -----------------------------------------------------------------------------
DO $seguranca$
DECLARE
  t text;
  f text;
  tabelas CONSTANT text[] := ARRAY[
    'trafego_intencao', 'trafego_blueprint', 'trafego_lote',
    'trafego_lote_item', 'trafego_lote_asset', 'trafego_validacao',
    'trafego_recibo', 'trafego_verificacao', 'trafego_rollback',
    'trafego_lote_transicao'
  ];
  views CONSTANT text[] := ARRAY[
    'trafego_item_situacao', 'trafego_lote_painel'
  ];
  -- APPEND-ONLY: nem UPDATE elas recebem. O gatilho ja recusaria, mas duas
  -- travas independentes e o ponto — grant errado numa e gatilho na outra.
  so_insere CONSTANT text[] := ARRAY[
    'trafego_intencao', 'trafego_validacao', 'trafego_verificacao',
    'trafego_lote_transicao'
  ];
BEGIN
  FOREACH t IN ARRAY tabelas LOOP
    -- 1) NOMINAL. `FROM PUBLIC` sozinho NAO remove grant nominal, e o default
    --    ACL medido concede nominalmente a anon e authenticated.
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM service_role', t);

    -- 2) Defesa em profundidade. ZERO policies = nega tudo para quem nao tem
    --    BYPASSRLS, mesmo que um GRANT reapareca por engano numa migration
    --    futura. FORCE alcanca ate o dono da tabela.
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE  ROW LEVEL SECURITY', t);

    -- 3) Minimo e explicito, so para service_role. DELETE nao aparece em lugar
    --    nenhum: nao ha caminho de apagamento no dominio.
    IF t = ANY (so_insere) THEN
      EXECUTE format('GRANT SELECT, INSERT ON TABLE public.%I TO service_role', t);
    ELSE
      EXECUTE format('GRANT SELECT, INSERT, UPDATE ON TABLE public.%I TO service_role', t);
    END IF;
  END LOOP;

  -- 3b) AS VIEWS ENTRAM NA MESMA CONTENCAO. Elas nascem com o mesmo default ACL
  --     quebrado — `ALTER DEFAULT PRIVILEGES ... ON TABLES` alcanca VIEW —, e
  --     uma view aberta e um tunel para as dez tabelas recem-fechadas.
  FOREACH t IN ARRAY views LOOP
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM service_role', t);
    EXECUTE format('GRANT SELECT ON TABLE public.%I TO service_role', t);
  END LOOP;

  -- 4) As funcoes tambem nascem com EXECUTE para anon (achado H, tipo 'f').
  FOREACH f IN ARRAY ARRAY[
    'trafego_intencao_imutavel', 'trafego_blueprint_so_aposenta',
    'trafego_lote_estado_valido', 'trafego_lote_sem_delete',
    'trafego_item_estado_valido', 'trafego_item_sem_delete',
    'trafego_recibo_fecha_uma_vez', 'trafego_lote_append_only',
    'trafego_rollback_fecha_uma_vez', 'trafego_lote_registra_transicao'
  ] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I() FROM PUBLIC', f);
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I() FROM anon', f);
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I() FROM authenticated', f);
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I() FROM service_role', f);
  END LOOP;

  RAISE NOTICE 'v10_01: 10 tabelas com RLS forcada + 2 views security_invoker, zero policies, anon/authenticated revogados nominalmente';
END
$seguranca$;


-- -----------------------------------------------------------------------------
-- 14. VERIFICACAO NA PROPRIA TRANSACAO — se algo escapou, nada e aplicado
-- -----------------------------------------------------------------------------
-- Uma migration de seguranca que "roda com sucesso" e deixa uma tabela aberta e
-- pior que uma que falha, porque ela produz um relatorio verde.
DO $verifica$
DECLARE
  meus CONSTANT text[] := ARRAY[
    'trafego_intencao', 'trafego_blueprint', 'trafego_lote',
    'trafego_lote_item', 'trafego_lote_asset', 'trafego_validacao',
    'trafego_recibo', 'trafego_verificacao', 'trafego_rollback',
    'trafego_lote_transicao', 'trafego_item_situacao', 'trafego_lote_painel'
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
    RAISE EXCEPTION 'v10_01: objeto nao criado: %', faltando;
  END IF;

  SELECT string_agg(DISTINCT c.relname, ', ') INTO abertas
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relname = ANY (meus)
     AND (
       has_table_privilege('anon',          c.oid, 'SELECT, INSERT, UPDATE, DELETE')
       OR has_table_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, DELETE')
     );
  IF abertas IS NOT NULL THEN
    RAISE EXCEPTION 'v10_01: anon/authenticated ainda alcancam: %', abertas;
  END IF;

  -- `security_invoker` e a unica coisa que impede a view de ser um tunel por
  -- cima da RLS. Sem esta conferencia, um `CREATE OR REPLACE VIEW` futuro que
  -- esquecesse a opcao abriria as dez tabelas em silencio.
  SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO sem_invoker
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relname = ANY (meus) AND c.relkind = 'v'
     AND NOT coalesce(
       (SELECT option_value = 'true'
          FROM pg_options_to_table(c.reloptions)
         WHERE option_name = 'security_invoker'), false);
  IF sem_invoker IS NOT NULL THEN
    RAISE EXCEPTION
      'v10_01: view sem security_invoker: % — ela leria as dez tabelas com os privilegios do dono', sem_invoker;
  END IF;

  SELECT string_agg(c.relname, ', ') INTO sem_rls
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relname = ANY (meus) AND c.relkind = 'r'
     AND NOT (c.relrowsecurity AND c.relforcerowsecurity);
  IF sem_rls IS NOT NULL THEN
    RAISE EXCEPTION 'v10_01: RLS nao esta ligada+forcada em: %', sem_rls;
  END IF;

  SELECT string_agg(tablename, ', ') INTO com_policy
    FROM pg_policies
   WHERE schemaname = 'public' AND tablename = ANY (meus);
  IF com_policy IS NOT NULL THEN
    RAISE EXCEPTION
      'v10_01: policy inesperada em % — a negacao aqui e por AUSENCIA de policy', com_policy;
  END IF;

  -- DELETE nao existe para ninguem, em nenhuma das dez. E mais forte que
  -- confiar no gatilho, e as duas travas sao independentes de proposito.
  IF EXISTS (
    SELECT 1 FROM unnest(meus) AS t
     WHERE to_regclass('public.' || t) IS NOT NULL
       AND has_table_privilege('service_role', 'public.' || t, 'DELETE')
  ) THEN
    RAISE EXCEPTION 'v10_01: alguma tabela concedeu DELETE a service_role';
  END IF;

  -- As append-only nao podem ter UPDATE nem por grant.
  IF has_table_privilege('service_role', 'public.trafego_validacao', 'UPDATE')
     OR has_table_privilege('service_role', 'public.trafego_verificacao', 'UPDATE')
     OR has_table_privilege('service_role', 'public.trafego_intencao', 'UPDATE')
     OR has_table_privilege('service_role', 'public.trafego_lote_transicao', 'UPDATE') THEN
    RAISE EXCEPTION 'v10_01: tabela append-only com UPDATE concedido a service_role';
  END IF;

  -- O indice que fecha o "timeout mas criou". Sem ele, o resto da migration e
  -- documentacao.
  IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'trafego_recibo_sucesso_unico_ux') THEN
    RAISE EXCEPTION
      'v10_01: trafego_recibo_sucesso_unico_ux ausente — sem ele, dois sucessos com a mesma chave passam e o lote vira dono de duas campanhas sem saber.';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'trafego_item_chave_ux') THEN
    RAISE EXCEPTION 'v10_01: trafego_item_chave_ux ausente — a chave de idempotencia deixou de ser unica.';
  END IF;

  RAISE NOTICE 'v10_01: verificacao interna passou';
END
$verifica$;

COMMIT;

-- =============================================================================
-- CONFERENCIA DEPOIS DE APLICAR (somente leitura, cole no psql)
-- =============================================================================
-- SELECT c.relname, c.relrowsecurity AS rls, c.relforcerowsecurity AS forcada,
--        coalesce(array_to_string(c.relacl, E'\n'), '(sem acl)') AS acl
--   FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
--  WHERE n.nspname = 'public' AND c.relname LIKE 'trafego\_%' AND c.relkind = 'r'
--  ORDER BY 1;
--
-- -- o que ficou em voo, e ha quanto tempo:
-- SELECT item_id, idempotency_key, operacao, enviado_em, now() - enviado_em AS ha
--   FROM public.trafego_recibo WHERE desfecho = 'em_voo' ORDER BY enviado_em;
