-- =============================================================================
-- v14_01 — Publicacao organica: destino, job, lease, recibo imutavel e
--          reconciliacao. A espinha que liga peca aprovada a control plane
--          externo (Postiz) sem que o VOLC vire scheduler.
-- P12-T09 (porta VOLC de publicacao). ARQUIVO. NAO APLICADO em producao.
-- =============================================================================
-- APLICAR COMO: postgres (supabase_admin tambem serve; a guarda aceita os dois)
--
-- ORDEM: DEPENDE de v11_01 (criativo_aprovacao, criativo_master, criativo_job,
--        criativo_finalidade via v11_02) e de v13_01 (cofre_ativo e as tres
--        funcoes genericas `cofre_entrada_hash`, `cofre_append_only`,
--        `cofre_sem_material_de_credencial`). A guarda da secao 0 aborta com
--        mensagem nomeada quando alguma falta — nunca com erro cru.
-- ROLLBACK: supabase/migrations/v14_99_publicacao_organica_rollback.sql
-- CICLO:    scripts/provar-ciclo-v14_01.sh (aplicar -> operar -> reverter ->
--           reaplicar num Postgres descartavel; nunca toca producao)
--
-- -----------------------------------------------------------------------------
-- POR QUE UMA LINHA NOVA, E NAO UMA EXTENSAO DE `criativo_entrega`
-- -----------------------------------------------------------------------------
-- `criativo_entrega` (v11_01, secao 9) e a tabela mais parecida que existe:
-- tem `idempotency_key`, `autorizacao_id NOT NULL REFERENCES criativo_aprovacao`
-- e um indice parcial que garante um sucesso por chave. Ela foi considerada e
-- NAO foi estendida. As razoes, medidas contra o arquivo:
--
--   1. UNIDADE DE TRABALHO DIFERENTE. `criativo_entrega.pacote_id` e NOT NULL
--      contra `criativo_pacote`, que e NOT NULL contra `criativo_projeto`.
--      Publicacao organica publica UMA PECA APROVADA num DESTINO — obrigar todo
--      post a descender de um pacote de midia paga inverteria o modelo.
--   2. TEMPO. Entrega de pacote e imediata. Publicacao organica tem `modo`
--      (draft/schedule/now), horario local declarado, timezone IANA e instante
--      UTC derivado. Sao cinco colunas e tres invariantes que midia paga nao
--      quer.
--   3. RECONCILIACAO. `criativo_entrega.recibo` e um jsonb MUTAVEL, sem
--      append-only e sem historico. Publicacao organica precisa de observacoes
--      sucessivas do control plane (o mesmo post muda de QUEUE para PUBLISHED
--      horas depois), e isso e uma tabela filha, nao um UPDATE.
--   4. CONCORRENCIA. Nao ha lease, fencing nem contador de tentativa em
--      `criativo_entrega`. Um despachante que morre no meio deixaria a linha
--      `em_voo` para sempre.
--   5. FRONTEIRA DE TRABALHO. `criativo_*` e o dominio do Estudio Criativo e
--      esta sob missao ativa em outro terminal. Alterar a tabela dele aqui
--      seria invadir; o handoff em
--      docs/closure/organic-publication-control-plane-v1/CURATION-HANDOFF.json
--      registra a decisao pendente sobre o destino de `criativo_entrega`.
--
-- O que NAO foi duplicado, e por isso este arquivo NAO cria: o ato de aprovar.
-- `criativo_aprovacao` ja e a decisao humana com ator, instante, finalidade,
-- ressalva e revogacao. Este schema a CONSOME por FK e por gatilho. Inventar um
-- segundo conceito de aprovacao produziria duas verdades sobre a mesma peca.
--
-- -----------------------------------------------------------------------------
-- OS QUATRO MECANISMOS, E POR QUE CADA UM
-- -----------------------------------------------------------------------------
--
--  1) SNAPSHOT IMUTAVEL. `publicacao_organica_job.solicitacao` e montado PELO
--     BANCO a partir das colunas tipadas da peca aprovada, e um gatilho recusa
--     qualquer UPDATE nele. O despachante envia a partir do snapshot, nunca
--     relendo o master. Consequencia direta: uma versao nova da peca criada
--     depois da aprovacao NAO muda o que sai.
--
--  2) IDEMPOTENCIA COM DIGEST DERIVADO NO BANCO. `cofre_entrada_hash` (v13_01)
--     e generica, IMMUTABLE e nao sabe nada sobre Cofre. O chamador nao envia o
--     hash e por isso nao pode mentir sobre ele. Mesma chave + mesma entrada
--     devolve o recibo guardado; mesma chave + OUTRA entrada levanta.
--     ⚠️ A tabela de operacoes e PROPRIA. `cofre_operacao.chave_idempotencia` e
--     UNIQUE GLOBAL: compartilhar a tabela faria uma chave de publicacao colidir
--     com uma do Cofre.
--
--  3) LEASE COM FENCING. Reivindicar incrementa `fencing`. Concluir exige o
--     fencing que recebeu. Um despachante que dormiu, perdeu o lease e acordou
--     escreve com fencing velho e e RECUSADO — em vez de sobrescrever o
--     trabalho de quem assumiu.
--
--  4) "API RESPONDEU" != "CONTEUDO PUBLICADO". Sao estados diferentes
--     (`publicacao_solicitada` vs `publicado` vs `reconciliado`) e a unica
--     transicao para `reconciliado` exige referencia externa E instante de
--     observacao. Timeout entra em `indeterminado`, que NAO e sucesso e NAO e
--     falha — e o unico estado do qual a reconciliacao pode sair para os dois
--     lados. Doutrina herdada de `backend/app/redator/worker.py:583-600`
--     ("sair com codigo 0 e nao publicar e um desfecho real") e de
--     `supabase/migrations/v10_04_saida_do_indeterminado.sql`.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO NAO FAZ
-- -----------------------------------------------------------------------------
-- Nao publica. Nao fala com o Postiz. Nao guarda token, cookie, API key nem
-- localizador de segredo — `referencia_externa` e o id opaco da integracao no
-- control plane, e `identidade_logica` e o nome logico da pagina/perfil. As
-- CHECKs de prosa limpa (secao 9) recusam material de credencial em todas as
-- colunas de texto que a API publica.
--
-- Nao implementa promocao de rascunho para agendamento (`PUT /posts/{id}/status`
-- existe na API do Postiz e NAO foi exercitada nesta missao). Registrado como
-- capacidade disponivel-e-nao-provada em
-- docs/closure/organic-publication-control-plane-v1/POSTIZ-OPERATIONS.md.
-- =============================================================================

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
      'v14_01 deve rodar como postgres ou supabase_admin; papel atual: %',
      current_user;
  END IF;

  -- PG15 e o piso porque e o que PRODUCAO roda (`supabase/postgres:15.8.1.085`,
  -- `SHOW server_version` = 15.8). Provar num major diferente prova outra coisa.
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION
      'v14_01 exige PostgreSQL 15 ou maior, que e a major de producao; aqui: %',
      current_setting('server_version');
  END IF;

  SELECT string_agg(t, ', ' ORDER BY t) INTO ja_existem
    FROM unnest(ARRAY[
      'publicacao_organica_destino', 'publicacao_organica_job',
      'publicacao_organica_operacao', 'publicacao_organica_recibo',
      'publicacao_organica_transicao'
    ]) AS t
   WHERE to_regclass('public.' || t) IS NOT NULL;

  IF ja_existem IS NOT NULL THEN
    RAISE EXCEPTION
      'v14_01 ja parece aplicada: % ja existe(m). Rode o v14_99 antes de reaplicar.',
      ja_existem;
  END IF;

  -- Dependencia da v11_01/v11_02: o ato de aprovar e a peca.
  SELECT string_agg(t, ', ' ORDER BY t) INTO faltando
    FROM unnest(ARRAY['criativo_aprovacao', 'criativo_master', 'criativo_job',
                      'criativo_finalidade']) AS t
   WHERE to_regclass('public.' || t) IS NULL;

  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION
      'v14_01 exige a serie v11 aplicada (o ato de aprovar nao e reinventado aqui); ausente(s): %',
      faltando;
  END IF;

  -- Dependencia da v13_01: o destino e as tres funcoes genericas.
  IF to_regclass('public.cofre_ativo') IS NULL THEN
    RAISE EXCEPTION
      'v14_01 exige a v13_01 aplicada: o destino organico e um `cofre_ativo`, nao um registro paralelo.';
  END IF;

  SELECT string_agg(f, ', ' ORDER BY f) INTO faltando
    FROM unnest(ARRAY[
      'public.cofre_entrada_hash(text,jsonb,jsonb)',
      'public.cofre_append_only()',
      'public.cofre_sem_material_de_credencial(text)'
    ]) AS f
   WHERE to_regprocedure(f) IS NULL;

  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION
      'v14_01 reutiliza funcoes genericas da v13_01; ausente(s): %. Elas sao genericas de proposito — nao ha copia neste arquivo.',
      faltando;
  END IF;

  SELECT string_agg(r, ', ' ORDER BY r) INTO faltando
    FROM unnest(ARRAY['anon', 'authenticated', 'service_role']) AS r
   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);

  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION
      'v14_01 exige os papeis do Supabase; ausente(s): %. Sem eles o REVOKE nominal nao acontece e a tabela nasce aberta.',
      faltando;
  END IF;

  RAISE NOTICE 'v14_01: guardas ok (papel=%, versao=%)',
    current_user, current_setting('server_version');
END
$guarda$;


-- -----------------------------------------------------------------------------
-- 1. AJUDANTES IMUTAVEIS — porque CHECK nao aceita subconsulta
-- -----------------------------------------------------------------------------

-- Forma de nome IANA. NAO prova que a zona existe (isso e `pg_timezone_names`,
-- que e tabela e por isso proibida em CHECK) — prova que o texto tem FORMA de
-- zona. A existencia e conferida na funcao governada, com `AT TIME ZONE` real.
CREATE OR REPLACE FUNCTION public.publicacao_organica_forma_de_timezone(p_tz text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = ''
AS $funcao$
  SELECT p_tz IS NOT NULL
     AND p_tz ~ '^[A-Za-z][A-Za-z0-9+_-]{1,31}(/[A-Za-z0-9+_.-]{1,31}){0,2}$';
$funcao$;

COMMENT ON FUNCTION public.publicacao_organica_forma_de_timezone(text) IS
  'Forma de nome IANA. A EXISTENCIA da zona e conferida na funcao governada, com AT TIME ZONE.';

-- Chave de idempotencia: derivada de conteudo, nunca sorteada. Mesma gramatica
-- do Cofre, pelo mesmo motivo — um uuid aleatorio faz todo retry parecer pedido
-- novo, e publicar de novo custa alcance e credibilidade, nao so dinheiro.
CREATE OR REPLACE FUNCTION public.publicacao_organica_forma_de_chave(p_chave text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = ''
AS $funcao$
  SELECT p_chave IS NOT NULL AND p_chave ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$';
$funcao$;


-- -----------------------------------------------------------------------------
-- 2. publicacao_organica_destino — o canal, ligado ao patrimonio do Cofre
-- -----------------------------------------------------------------------------
-- O destino NAO e um registro paralelo de paginas: ele APONTA para o
-- `cofre_ativo` que ja inventaria a pagina/perfil (kinds `facebook_page`,
-- `instagram_profile`, `youtube_channel`, `tiktok_account`, v13_01 secao 3).
-- Criar um segundo cadastro de destinos produziria a quarta lista divergente
-- que o CAPABILITY-MATRIX ja denuncia.
--
-- ⚠️ `adapter_apto = false` NAO significa "esconder". A regra de produto herdada
-- de `ProjetoDestino {id, nome, apto, motivo}` (publicacao.py:385-432) e do ADR
-- ("MultiPost nunca mascara a ausencia de adapter oficial") e MOSTRAR o destino
-- inapto COM o motivo. Filtrar o inapto para fora da lista tornaria a guarda
-- impossivel de cumprir: o operador nunca veria a lacuna.
CREATE TABLE public.publicacao_organica_destino (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

  ativo_id            text        NOT NULL REFERENCES public.cofre_ativo (ativo_id),
  plataforma          text        NOT NULL,

  -- Nome LOGICO da pagina/perfil. Nunca segredo, nunca id cru de plataforma.
  identidade_logica   text        NOT NULL,

  provedor            text        NOT NULL DEFAULT 'postiz',
  -- Id opaco da integracao no control plane. NULL enquanto o destino nao foi
  -- ligado — e um destino sem referencia NAO pode despachar (secao 6).
  referencia_externa  text        NULL,

  adapter_apto        boolean     NOT NULL DEFAULT false,
  motivo_inapto       text        NULL,

  -- Dono operacional do destino. `owner_sub` e o `sub` da Identidade, o mesmo
  -- valor que `criativo_job.criado_por` guarda.
  owner_sub           uuid        NOT NULL,

  timezone_padrao     text        NOT NULL DEFAULT 'America/Sao_Paulo',
  estado              text        NOT NULL DEFAULT 'ativo',

  criado_em           timestamptz NOT NULL DEFAULT now(),
  atualizado_em       timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT publicacao_organica_destino_ux
    UNIQUE (ativo_id, plataforma, provedor),

  CONSTRAINT publicacao_organica_destino_plataforma_valida
    CHECK (plataforma IN ('facebook', 'instagram', 'youtube', 'tiktok',
                          'linkedin', 'x', 'threads', 'pinterest')),
  CONSTRAINT publicacao_organica_destino_provedor_valido
    CHECK (provedor IN ('postiz', 'multipost')),
  CONSTRAINT publicacao_organica_destino_estado_valido
    CHECK (estado IN ('ativo', 'suspenso', 'aposentado')),
  CONSTRAINT publicacao_organica_destino_identidade_nao_vazia
    CHECK (btrim(identidade_logica) <> ''),
  CONSTRAINT publicacao_organica_destino_tz_forma
    CHECK (public.publicacao_organica_forma_de_timezone(timezone_padrao)),

  -- Apto sem referencia externa e promessa sem endereco: o despachante teria de
  -- adivinhar para onde manda.
  CONSTRAINT publicacao_organica_destino_apto_tem_referencia
    CHECK (adapter_apto = false OR btrim(coalesce(referencia_externa, '')) <> ''),
  -- Inapto sem motivo e um botao cinza sem explicacao. O operador precisa saber
  -- o que falta, nao so que falta.
  CONSTRAINT publicacao_organica_destino_inapto_tem_motivo
    CHECK (adapter_apto = true OR btrim(coalesce(motivo_inapto, '')) <> '')
);

CREATE INDEX publicacao_organica_destino_ativo_ix
  ON public.publicacao_organica_destino (ativo_id);
CREATE INDEX publicacao_organica_destino_owner_ix
  ON public.publicacao_organica_destino (owner_sub, estado);

COMMENT ON TABLE public.publicacao_organica_destino IS
  'Canal organico ligado a um cofre_ativo. Sem segredo: identidade logica e id opaco de integracao.';


-- -----------------------------------------------------------------------------
-- 3. publicacao_organica_job — a intencao canonica de publicar
-- -----------------------------------------------------------------------------
-- Os estados, e a diferenca que cada um carrega:
--
--   rascunho              criado no VOLC; nada saiu daqui
--   pronto                validado e liberado para despacho
--   em_voo                reivindicado e despachado; resposta desconhecida
--   rascunho_externo      o control plane confirmou um DRAFT
--   agendado              o control plane confirmou um agendamento
--   publicacao_solicitada o control plane aceitou publicar AGORA; nao confirmou
--   publicado             o control plane declara PUBLISHED
--   reconciliado          observacao externa com referencia E instante fecha
--   falha                 falha DETERMINADA (o control plane recusou)
--   indeterminado         resposta ambigua ou timeout — nao e sucesso nem falha
--   cancelado             cancelado com seguranca antes de existir no destino
--
-- ⚠️ `publicacao_solicitada` existe porque colapsar "a API respondeu 200" em
-- "o conteudo esta publicado" e o defeito que o proprio repositorio ja pagou
-- caro (worker.py:583-600). Um 200 do Postiz com `type: now` prova que o pedido
-- entrou na fila do Temporal dele, e nada mais.
CREATE TABLE public.publicacao_organica_job (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

  -- --- quem ---
  owner_sub             uuid        NOT NULL,
  owner_email           text        NULL,

  -- --- o que ---
  -- Referencia a peca aprovada. `peca_tipo`/`peca_id`/`peca_versao` espelham
  -- (subject_tipo, subject_id, versao) de `criativo_aprovacao`, e o gatilho da
  -- secao 6 recusa quando os tres nao batem: autorizacao NAO e transferivel.
  peca_tipo             text        NOT NULL,
  peca_id               uuid        NOT NULL,
  peca_versao           integer     NOT NULL,
  peca_content_hash     text        NOT NULL,

  -- --- com que autoridade ---
  autorizacao_id        uuid        NOT NULL REFERENCES public.criativo_aprovacao (id),

  -- --- para onde ---
  destino_id            uuid        NOT NULL REFERENCES public.publicacao_organica_destino (id),
  projeto_id            uuid        NULL REFERENCES public.criativo_projeto (id),

  -- --- quando ---
  modo                  text        NOT NULL,
  -- Horario LOCAL declarado pelo operador, sem zona. Guardado porque e o que
  -- ele digitou; apresentar de volta o UTC convertido nao devolve o que ele viu.
  horario_local         text        NULL,
  timezone              text        NOT NULL,
  -- Instante UTC DERIVADO NO BANCO por `horario_local::timestamp AT TIME ZONE
  -- timezone`. Independente do TZ do servidor por construcao.
  instante_utc          timestamptz NULL,

  -- --- estado ---
  estado                text        NOT NULL DEFAULT 'rascunho',

  -- --- idempotencia e imutabilidade ---
  chave_idempotencia    text        NOT NULL,
  entrada_hash          text        NOT NULL,
  -- SNAPSHOT IMUTAVEL da solicitacao, montado pelo banco. Gatilho da secao 7
  -- recusa qualquer UPDATE nele.
  solicitacao           jsonb       NOT NULL,

  -- --- execucao ---
  adapter               text        NOT NULL DEFAULT 'postiz',
  tentativas            integer     NOT NULL DEFAULT 0,
  ultimo_erro           text        NULL,

  -- --- lease com fencing ---
  lease_owner           text        NULL,
  lease_ate             timestamptz NULL,
  fencing               bigint      NOT NULL DEFAULT 0,

  -- --- consentimento especifico para publicacao imediata ---
  -- `now` atravessa o VOLC apenas com um SIM explicito, de um ator nomeado, num
  -- instante registrado. Sem os tres, a CHECK abaixo recusa a linha.
  consentimento_agora   boolean     NOT NULL DEFAULT false,
  consentimento_ator    uuid        NULL,
  consentimento_em      timestamptz NULL,

  criado_em             timestamptz NOT NULL DEFAULT now(),
  atualizado_em         timestamptz NOT NULL DEFAULT now(),
  cancelado_em          timestamptz NULL,
  cancelado_por         uuid        NULL,

  CONSTRAINT publicacao_organica_job_chave_ux UNIQUE (chave_idempotencia),

  CONSTRAINT publicacao_organica_job_chave_forma
    CHECK (public.publicacao_organica_forma_de_chave(chave_idempotencia)),
  CONSTRAINT publicacao_organica_job_hash_forma
    CHECK (entrada_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT publicacao_organica_job_peca_tipo_valido
    CHECK (peca_tipo IN ('master', 'pacote')),
  CONSTRAINT publicacao_organica_job_peca_versao_positiva
    CHECK (peca_versao >= 1),
  CONSTRAINT publicacao_organica_job_peca_hash_forma
    CHECK (peca_content_hash ~ '^sha256:[0-9a-f]{64}$'),
  CONSTRAINT publicacao_organica_job_modo_valido
    CHECK (modo IN ('draft', 'schedule', 'now')),
  CONSTRAINT publicacao_organica_job_adapter_valido
    CHECK (adapter IN ('postiz', 'multipost')),
  CONSTRAINT publicacao_organica_job_estado_valido
    CHECK (estado IN ('rascunho', 'pronto', 'em_voo', 'rascunho_externo',
                      'agendado', 'publicacao_solicitada', 'publicado',
                      'reconciliado', 'falha', 'indeterminado', 'cancelado')),
  CONSTRAINT publicacao_organica_job_tz_forma
    CHECK (public.publicacao_organica_forma_de_timezone(timezone)),
  CONSTRAINT publicacao_organica_job_tentativas_nao_negativas
    CHECK (tentativas >= 0),

  -- Agendar sem instante e agendar para nunca.
  CONSTRAINT publicacao_organica_job_schedule_tem_instante
    CHECK (modo <> 'schedule' OR (instante_utc IS NOT NULL AND horario_local IS NOT NULL)),
  -- `now` sem os tres campos de consentimento nao existe como linha.
  CONSTRAINT publicacao_organica_job_agora_exige_consentimento
    CHECK (modo <> 'now'
           OR (consentimento_agora = true
               AND consentimento_ator IS NOT NULL
               AND consentimento_em IS NOT NULL)),
  -- Consentimento sem os tres campos juntos e meio-consentimento.
  CONSTRAINT publicacao_organica_job_consentimento_completo
    CHECK ((consentimento_agora = false AND consentimento_ator IS NULL AND consentimento_em IS NULL)
           OR (consentimento_agora = true AND consentimento_ator IS NOT NULL AND consentimento_em IS NOT NULL)),
  -- Lease sem prazo e lease eterno; prazo sem dono e prazo de ninguem.
  CONSTRAINT publicacao_organica_job_lease_par
    CHECK ((lease_owner IS NULL) = (lease_ate IS NULL)),
  CONSTRAINT publicacao_organica_job_fencing_nao_negativo
    CHECK (fencing >= 0),
  CONSTRAINT publicacao_organica_job_cancelamento_par
    CHECK ((cancelado_em IS NULL) = (cancelado_por IS NULL)),
  CONSTRAINT publicacao_organica_job_cancelado_carimbado
    CHECK (estado <> 'cancelado' OR cancelado_em IS NOT NULL)
);

CREATE INDEX publicacao_organica_job_owner_ix
  ON public.publicacao_organica_job (owner_sub, estado, criado_em DESC);
CREATE INDEX publicacao_organica_job_destino_ix
  ON public.publicacao_organica_job (destino_id, criado_em DESC);
CREATE INDEX publicacao_organica_job_pendente_ix
  ON public.publicacao_organica_job (estado, instante_utc)
  WHERE estado IN ('pronto', 'em_voo', 'indeterminado');
CREATE INDEX publicacao_organica_job_autorizacao_ix
  ON public.publicacao_organica_job (autorizacao_id);

COMMENT ON TABLE public.publicacao_organica_job IS
  'Intencao canonica de publicar uma peca aprovada num destino organico, com snapshot imutavel, lease e fencing.';
COMMENT ON COLUMN public.publicacao_organica_job.solicitacao IS
  'Snapshot IMUTAVEL montado pelo banco. O despachante envia daqui, nunca relendo a peca.';


-- -----------------------------------------------------------------------------
-- 4. publicacao_organica_operacao — idempotencia e trilha, append-only
-- -----------------------------------------------------------------------------
-- Tabela PROPRIA, e nao `cofre_operacao`, porque a chave la e UNIQUE GLOBAL.
CREATE TABLE public.publicacao_organica_operacao (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id              uuid        NULL REFERENCES public.publicacao_organica_job (id),
  chave_idempotencia  text        NOT NULL,
  rota                text        NOT NULL,
  entrada_hash        text        NOT NULL,
  resultado           jsonb       NOT NULL,
  desfecho            text        NOT NULL,
  autor_sub           uuid        NULL,
  autor_email         text        NULL,
  criado_em           timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT publicacao_organica_operacao_chave_ux UNIQUE (chave_idempotencia),
  CONSTRAINT publicacao_organica_operacao_chave_forma
    CHECK (public.publicacao_organica_forma_de_chave(chave_idempotencia)),
  CONSTRAINT publicacao_organica_operacao_hash_forma
    CHECK (entrada_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT publicacao_organica_operacao_desfecho_valido
    CHECK (desfecho IN ('sucesso', 'falha', 'indeterminado')),
  CONSTRAINT publicacao_organica_operacao_resultado_objeto
    CHECK (jsonb_typeof(resultado) = 'object')
);

-- UM DESPACHO BEM-SUCEDIDO POR JOB, fisicamente. Mesmo desenho da v10_01 e da
-- v11_01: um executor com defeito que reenviasse NAO consegue registrar o
-- segundo sucesso de despacho — e sem segundo sucesso nao ha segundo post.
--
-- ⚠️ O PREDICADO CITA A ROTA DE DESPACHO, e isso e conserto de um defeito que a
-- prova do ciclo pegou em 02/09/2026. A primeira versao era `(job_id, rota)
-- WHERE desfecho='sucesso'`, o que parecia mais geral e era simplesmente
-- errado: a RECONCILIACAO acontece muitas vezes por job — o mesmo post e
-- observado em DRAFT, depois QUEUE, depois PUBLISHED — e cada observacao
-- bem-sucedida e legitima. O indice largo transformava a segunda reconciliacao
-- num erro de chave duplicada, ou seja, impedia exatamente o mecanismo que a
-- missao existe para construir. O invariante que importa e "um DESPACHO por
-- job", e nao "uma operacao de sucesso por rota".
CREATE UNIQUE INDEX publicacao_organica_operacao_sucesso_ux
  ON public.publicacao_organica_operacao (job_id)
  WHERE desfecho = 'sucesso'
    AND job_id IS NOT NULL
    AND rota = 'publicacao_organica.concluir_despacho';

CREATE INDEX publicacao_organica_operacao_job_ix
  ON public.publicacao_organica_operacao (job_id, criado_em DESC);

CREATE TRIGGER publicacao_organica_operacao_append_only
  BEFORE UPDATE OR DELETE ON public.publicacao_organica_operacao
  FOR EACH ROW EXECUTE FUNCTION public.cofre_append_only();


-- -----------------------------------------------------------------------------
-- 5. publicacao_organica_recibo e _transicao — a prova externa e o historico
-- -----------------------------------------------------------------------------
-- Cada observacao do control plane e uma LINHA NOVA. O mesmo post muda de QUEUE
-- para PUBLISHED horas depois, e sobrescrever apagaria o momento em que ele
-- ainda nao estava no ar — que e exatamente o que uma auditoria pergunta.
--
-- ⚠️ `url_publicada` e guardada VERBATIM como o provedor devolveu. A regra vem
-- de steps.py:2832-2843 do motor: remontar URL a partir de slug ja produziu
-- atribuicao de receita apontando para o post errado, em silencio.
CREATE TABLE public.publicacao_organica_recibo (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id              uuid        NOT NULL REFERENCES public.publicacao_organica_job (id),
  provedor            text        NOT NULL,
  referencia_externa  text        NOT NULL,
  estado_externo      text        NOT NULL,
  url_publicada       text        NULL,
  publicado_em        timestamptz NULL,
  -- Corpo do provedor JA SANITIZADO pela camada de aplicacao. A CHECK da secao
  -- 9 e a ultima peneira, nao a primeira.
  bruto_sanitizado    jsonb       NOT NULL,
  origem              text        NOT NULL,
  observado_em        timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT publicacao_organica_recibo_referencia_nao_vazia
    CHECK (btrim(referencia_externa) <> ''),
  CONSTRAINT publicacao_organica_recibo_estado_valido
    CHECK (estado_externo IN ('DRAFT', 'QUEUE', 'PUBLISHED', 'ERROR', 'DESCONHECIDO')),
  CONSTRAINT publicacao_organica_recibo_origem_valida
    CHECK (origem IN ('despacho', 'reconciliacao')),
  CONSTRAINT publicacao_organica_recibo_bruto_objeto
    CHECK (jsonb_typeof(bruto_sanitizado) = 'object'),
  -- Publicado sem URL nem instante e afirmacao sem prova.
  CONSTRAINT publicacao_organica_recibo_publicado_tem_prova
    CHECK (estado_externo <> 'PUBLISHED'
           OR (btrim(coalesce(url_publicada, '')) <> '' AND publicado_em IS NOT NULL))
);

CREATE INDEX publicacao_organica_recibo_job_ix
  ON public.publicacao_organica_recibo (job_id, observado_em DESC);

CREATE TRIGGER publicacao_organica_recibo_append_only
  BEFORE UPDATE OR DELETE ON public.publicacao_organica_recibo
  FOR EACH ROW EXECUTE FUNCTION public.cofre_append_only();


CREATE TABLE public.publicacao_organica_transicao (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id        uuid        NOT NULL REFERENCES public.publicacao_organica_job (id),
  de            text        NULL,
  para          text        NOT NULL,
  motivo        text        NOT NULL,
  ator_sub      uuid        NULL,
  fencing       bigint      NULL,
  criado_em     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX publicacao_organica_transicao_job_ix
  ON public.publicacao_organica_transicao (job_id, criado_em);

CREATE TRIGGER publicacao_organica_transicao_append_only
  BEFORE UPDATE OR DELETE ON public.publicacao_organica_transicao
  FOR EACH ROW EXECUTE FUNCTION public.cofre_append_only();


-- -----------------------------------------------------------------------------
-- 6. A AUTORIZACAO NAO E TRANSFERIVEL — gatilho BEFORE INSERT no job
-- -----------------------------------------------------------------------------
-- Portao SO na camada FastAPI e o erro que este repositorio ja documentou como
-- insuficiente ("nem um script solto, nem um endpoint esquecido",
-- v10_02_autogestao.sql:1170-1234). As cinco recusas abaixo acontecem no banco.
CREATE OR REPLACE FUNCTION public.publicacao_organica_exige_autorizacao()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $funcao$
DECLARE
  a public.criativo_aprovacao%ROWTYPE;
  classe_da_finalidade text;
  dono_da_peca uuid;
  d public.publicacao_organica_destino%ROWTYPE;
BEGIN
  SELECT * INTO a FROM public.criativo_aprovacao WHERE id = NEW.autorizacao_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'publicacao organica: a autorizacao citada nao existe'
      USING ERRCODE = 'foreign_key_violation';
  END IF;

  -- 1. A decisao tem de ser APROVADO. `ajuste_solicitado` e `rejeitado` sao
  --    decisoes verdadeiras, e nenhuma das duas autoriza publicar.
  IF a.decisao <> 'aprovado' THEN
    RAISE EXCEPTION
      'publicacao organica: a decisao citada e "%", e so "aprovado" autoriza publicar', a.decisao
      USING ERRCODE = 'check_violation';
  END IF;

  -- 2. Aprovacao revogada nao volta a valer porque alguem tentou publicar.
  IF a.revogada_em IS NOT NULL THEN
    RAISE EXCEPTION
      'publicacao organica: esta autorizacao foi revogada e nao autoriza mais'
      USING ERRCODE = 'check_violation';
  END IF;

  -- 3. AUTORIZACAO NAO E TRANSFERIVEL. A aprovacao e de UMA peca numa VERSAO.
  --    Sem esta recusa, aprovar a v1 autorizaria publicar a v2 — que e a
  --    "heranca vaga" que a SPEC do Estudio proibe.
  IF a.subject_tipo <> NEW.peca_tipo
     OR a.subject_id <> NEW.peca_id
     OR a.versao <> NEW.peca_versao THEN
    RAISE EXCEPTION
      'publicacao organica: a autorizacao e de outra peca ou de outra versao; autorizacao nao e transferivel'
      USING ERRCODE = 'check_violation';
  END IF;

  -- 4. A finalidade aprovada tem de ser de classe ORGANICA. Aprovar para
  --    `interna` ou `midia_paga` nao autoriza publicar no feed.
  SELECT f.classe INTO classe_da_finalidade
    FROM public.criativo_finalidade f
   WHERE f.slug = a.finalidade;

  IF classe_da_finalidade IS DISTINCT FROM 'organica' THEN
    RAISE EXCEPTION
      'publicacao organica: a finalidade aprovada ("%") nao e de classe organica', a.finalidade
      USING ERRCODE = 'check_violation';
  END IF;

  -- 5. OWNERSHIP FAIL-CLOSED. O dono do job tem de ser o dono da peca. Sem
  --    esta recusa, o dono A publica a peca do dono B com a aprovacao do B.
  IF NEW.peca_tipo = 'master' THEN
    SELECT j.criado_por INTO dono_da_peca
      FROM public.criativo_master m
      JOIN public.criativo_job j ON j.id = m.job_id
     WHERE m.id = NEW.peca_id;
  ELSE
    SELECT p.criado_por INTO dono_da_peca
      FROM public.criativo_pacote p
     WHERE p.id = NEW.peca_id;
  END IF;

  IF dono_da_peca IS NULL THEN
    -- Peca sem dono conhecido NAO vira publicacao. Um NULL aqui e ausencia de
    -- prova de posse, e ausencia de prova nao autoriza.
    RAISE EXCEPTION
      'publicacao organica: a peca nao tem dono registrado; sem dono nao ha publicacao'
      USING ERRCODE = 'check_violation';
  END IF;

  IF dono_da_peca <> NEW.owner_sub THEN
    RAISE EXCEPTION
      'publicacao organica: esta peca pertence a outro dono'
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  -- 6. O DESTINO tem de ser do mesmo dono, estar ativo e ter adapter apto.
  SELECT * INTO d FROM public.publicacao_organica_destino WHERE id = NEW.destino_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'publicacao organica: destino inexistente'
      USING ERRCODE = 'foreign_key_violation';
  END IF;
  IF d.owner_sub <> NEW.owner_sub THEN
    RAISE EXCEPTION
      'publicacao organica: este destino pertence a outro dono'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF d.estado <> 'ativo' THEN
    RAISE EXCEPTION
      'publicacao organica: o destino esta "%" e nao aceita publicacao', d.estado
      USING ERRCODE = 'check_violation';
  END IF;
  IF d.adapter_apto IS NOT TRUE OR btrim(coalesce(d.referencia_externa, '')) = '' THEN
    RAISE EXCEPTION
      'publicacao organica: o destino nao tem adapter apto; motivo registrado: %',
      coalesce(d.motivo_inapto, 'nao declarado')
      USING ERRCODE = 'check_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER publicacao_organica_job_exige_autorizacao
  BEFORE INSERT ON public.publicacao_organica_job
  FOR EACH ROW EXECUTE FUNCTION public.publicacao_organica_exige_autorizacao();


-- -----------------------------------------------------------------------------
-- 7. O SNAPSHOT NAO MUDA, E A MAQUINA DE ESTADOS TEM ARESTAS DECLARADAS
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.publicacao_organica_job_guarda_update()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $funcao$
DECLARE
  aresta text;
  -- ⚠️ AS ARESTAS "PARA TRAS" NAO SAO DESCUIDO. Depois do despacho, QUEM E DONO
  -- DO ESTADO EXTERNO E O CONTROL PLANE — nos somos donos de quais jobs existem.
  -- Um operador que abre o painel do Postiz e devolve um post agendado para
  -- rascunho produz `agendado>rascunho_externo`, e a reconciliacao tem de poder
  -- REGISTRAR isso. Recusar a aresta faria a nossa linha discordar do mundo em
  -- silencio, que e pior do que o registro incomodo. Doutrina de
  -- `publicacao.py:944-968` (reler-wp: o provedor e dono do campo `status`).
  permitidas text[] := ARRAY[
    -- --- antes de qualquer contato externo ---
    'rascunho>pronto',
    'rascunho>cancelado',
    'pronto>em_voo',
    'pronto>cancelado',
    -- --- o desfecho do despacho ---
    'em_voo>rascunho_externo',
    'em_voo>agendado',
    'em_voo>publicacao_solicitada',
    'em_voo>falha',
    'em_voo>indeterminado',
    -- --- o que a reconciliacao pode observar a partir de rascunho_externo ---
    'rascunho_externo>reconciliado',
    'rascunho_externo>agendado',
    'rascunho_externo>publicado',
    'rascunho_externo>falha',
    'rascunho_externo>indeterminado',
    'rascunho_externo>cancelado',
    -- --- a partir de agendado ---
    'agendado>publicado',
    'agendado>reconciliado',
    'agendado>rascunho_externo',
    'agendado>falha',
    'agendado>indeterminado',
    'agendado>cancelado',
    -- --- a partir de publicacao solicitada ---
    'publicacao_solicitada>publicado',
    'publicacao_solicitada>reconciliado',
    'publicacao_solicitada>agendado',
    'publicacao_solicitada>rascunho_externo',
    'publicacao_solicitada>falha',
    'publicacao_solicitada>indeterminado',
    -- --- a partir de publicado ---
    'publicado>reconciliado',
    'publicado>falha',
    'publicado>indeterminado',
    -- O indeterminado sai para TODOS os lados. E o desenho da v10_04: um estado
    -- que so sai para sucesso nao e indeterminado, e um que so sai para falha e
    -- falha com outro nome.
    'indeterminado>rascunho_externo',
    'indeterminado>agendado',
    'indeterminado>publicado',
    'indeterminado>publicacao_solicitada',
    'indeterminado>reconciliado',
    'indeterminado>falha',
    'indeterminado>cancelado',
    -- Falha determinada ainda pode ser cancelada (encerra a intencao) ou
    -- reconciliada quando a observacao contradiz a falha declarada.
    'falha>cancelado',
    'falha>indeterminado'
  ];
BEGIN
  -- 1. O SNAPSHOT E IMUTAVEL. Esta e a linha que faz "alterar a peca depois da
  --    aprovacao" nao mudar o que sai.
  IF NEW.solicitacao IS DISTINCT FROM OLD.solicitacao THEN
    RAISE EXCEPTION
      'publicacao organica: o snapshot da solicitacao e imutavel. Crie um job novo.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- 2. A identidade do pedido tambem nao muda. Trocar destino, peca, modo,
  --    autorizacao, chave ou hash sob um id ja despachado seria reescrever a
  --    historia — e o recibo ja gravado passaria a citar outra coisa.
  IF NEW.chave_idempotencia IS DISTINCT FROM OLD.chave_idempotencia
     OR NEW.entrada_hash    IS DISTINCT FROM OLD.entrada_hash
     OR NEW.autorizacao_id  IS DISTINCT FROM OLD.autorizacao_id
     OR NEW.destino_id      IS DISTINCT FROM OLD.destino_id
     OR NEW.peca_tipo       IS DISTINCT FROM OLD.peca_tipo
     OR NEW.peca_id         IS DISTINCT FROM OLD.peca_id
     OR NEW.peca_versao     IS DISTINCT FROM OLD.peca_versao
     OR NEW.peca_content_hash IS DISTINCT FROM OLD.peca_content_hash
     OR NEW.modo            IS DISTINCT FROM OLD.modo
     OR NEW.timezone        IS DISTINCT FROM OLD.timezone
     OR NEW.instante_utc    IS DISTINCT FROM OLD.instante_utc
     OR NEW.owner_sub       IS DISTINCT FROM OLD.owner_sub THEN
    RAISE EXCEPTION
      'publicacao organica: identidade do pedido e imutavel (chave, hash, autorizacao, destino, peca, modo, horario, dono).'
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- 3. O fencing so anda para frente. Um consumidor que tentasse recuar o
  --    fencing reabriria a janela que o lease fechou.
  IF NEW.fencing < OLD.fencing THEN
    RAISE EXCEPTION 'publicacao organica: o fencing nao retrocede'
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- 4. A ARESTA TEM DE ESTAR NA LISTA.
  IF NEW.estado IS DISTINCT FROM OLD.estado THEN
    aresta := OLD.estado || '>' || NEW.estado;
    IF NOT (aresta = ANY (permitidas)) THEN
      RAISE EXCEPTION
        'publicacao organica: transicao % nao e permitida', aresta
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  NEW.atualizado_em := now();
  RETURN NEW;
END
$funcao$;

CREATE TRIGGER publicacao_organica_job_guarda
  BEFORE UPDATE ON public.publicacao_organica_job
  FOR EACH ROW EXECUTE FUNCTION public.publicacao_organica_job_guarda_update();

-- Job nao se apaga. Um post que existiu no destino nao deixa de ter existido
-- porque a linha sumiu; e o cancelamento tem estado proprio.
CREATE OR REPLACE FUNCTION public.publicacao_organica_job_sem_delete()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $funcao$
BEGIN
  RAISE EXCEPTION
    'publicacao organica: job nao e apagado. Cancele — o estado cancelado preserva a trilha.'
    USING ERRCODE = 'restrict_violation';
END
$funcao$;

CREATE TRIGGER publicacao_organica_job_sem_delete
  BEFORE DELETE ON public.publicacao_organica_job
  FOR EACH ROW EXECUTE FUNCTION public.publicacao_organica_job_sem_delete();


-- -----------------------------------------------------------------------------
-- 8. IDEMPOTENCIA — replay honesto, divergencia ruidosa (tabela propria)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.publicacao_organica_idempotencia(
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
  anterior public.publicacao_organica_operacao%ROWTYPE;
BEGIN
  SELECT * INTO anterior
    FROM public.publicacao_organica_operacao
   WHERE chave_idempotencia = p_chave;

  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  IF anterior.rota <> p_rota OR anterior.entrada_hash <> p_entrada_hash THEN
    -- ⚠️ A CHAVE NAO ENTRA NA MENSAGEM. A gramatica da chave aceita uma senha
    -- inteira; repeti-la no erro devolveria ao navegador exatamente o material
    -- que a recusa existe para conter. Quem chamou ja sabe qual chave mandou.
    RAISE EXCEPTION
      'esta chave de idempotencia ja foi usada por outra operacao (rota %); use uma chave nova',
      anterior.rota
      USING ERRCODE = 'unique_violation';
  END IF;

  RETURN anterior.resultado || jsonb_build_object('idempotente', true);
END
$funcao$;

CREATE OR REPLACE FUNCTION public.publicacao_organica_registra_operacao(
  p_job_id       uuid,
  p_chave        text,
  p_rota         text,
  p_entrada_hash text,
  p_resultado    jsonb,
  p_desfecho     text,
  p_autor_sub    uuid,
  p_autor_email  text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
BEGIN
  INSERT INTO public.publicacao_organica_operacao
    (job_id, chave_idempotencia, rota, entrada_hash, resultado, desfecho,
     autor_sub, autor_email)
  VALUES
    (p_job_id, p_chave, p_rota, p_entrada_hash, p_resultado, p_desfecho,
     p_autor_sub, p_autor_email);
  RETURN p_resultado || jsonb_build_object('idempotente', false);
END
$funcao$;


-- -----------------------------------------------------------------------------
-- 9. PROSA LIMPA — nenhuma coluna que a API publica carrega credencial
-- -----------------------------------------------------------------------------
ALTER TABLE public.publicacao_organica_destino
  ADD CONSTRAINT publicacao_organica_destino_prosa_limpa CHECK (
    public.cofre_sem_material_de_credencial(identidade_logica)
    AND public.cofre_sem_material_de_credencial(referencia_externa)
    AND public.cofre_sem_material_de_credencial(motivo_inapto)
    AND public.cofre_sem_material_de_credencial(plataforma));

ALTER TABLE public.publicacao_organica_job
  ADD CONSTRAINT publicacao_organica_job_prosa_limpa CHECK (
    public.cofre_sem_material_de_credencial(ultimo_erro)
    AND public.cofre_sem_material_de_credencial(owner_email)
    AND public.cofre_sem_material_de_credencial(horario_local)
    AND public.cofre_sem_material_de_credencial(lease_owner));

ALTER TABLE public.publicacao_organica_recibo
  ADD CONSTRAINT publicacao_organica_recibo_prosa_limpa CHECK (
    public.cofre_sem_material_de_credencial(referencia_externa)
    AND public.cofre_sem_material_de_credencial(url_publicada));


-- -----------------------------------------------------------------------------
-- 10. AS FUNCOES GOVERNADAS DE ESCRITA
-- -----------------------------------------------------------------------------
-- Toda escrita entra por aqui. Nenhum papel do Data API tem INSERT/UPDATE/DELETE
-- nas tabelas (secao 12) — este e o unico caminho por PRIVILEGIO, nao por
-- convencao. Cada funcao segue a mesma ordem: recusar campo desconhecido ->
-- recusar chave sensivel -> derivar hash -> consultar idempotencia -> executar
-- -> registrar recibo.

-- 10.1 registrar destino
CREATE OR REPLACE FUNCTION public.publicacao_organica_registrar_destino(
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
  permitidos text[] := ARRAY['ativo_id','plataforma','identidade_logica','provedor',
                             'referencia_externa','adapter_apto','motivo_inapto',
                             'timezone_padrao'];
  desconhecidos text;
  hash text;
  guardado jsonb;
  novo public.publicacao_organica_destino%ROWTYPE;
  recibo jsonb;
BEGIN
  IF jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'publicacao organica: o cadastro de destino exige um objeto JSON'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  SELECT string_agg(k, ', ' ORDER BY k) INTO desconhecidos
    FROM jsonb_object_keys(p_payload) AS k
   WHERE NOT (k = ANY (permitidos));
  IF desconhecidos IS NOT NULL THEN
    RAISE EXCEPTION
      'publicacao organica: recebeu campo(s) que este contrato nao conhece: %', desconhecidos
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  PERFORM public.cofre_recusa_chave_sensivel(p_payload, 'destino');

  hash := public.cofre_entrada_hash('publicacao_organica.registrar_destino', p_payload,
                                    jsonb_build_object('autor', p_autor_sub, 'email', p_autor_email));
  guardado := public.publicacao_organica_idempotencia(
                p_chave, 'publicacao_organica.registrar_destino', hash);
  IF guardado IS NOT NULL THEN
    RETURN guardado;
  END IF;

  INSERT INTO public.publicacao_organica_destino
    (ativo_id, plataforma, identidade_logica, provedor, referencia_externa,
     adapter_apto, motivo_inapto, owner_sub, timezone_padrao)
  VALUES
    (p_payload->>'ativo_id',
     p_payload->>'plataforma',
     p_payload->>'identidade_logica',
     coalesce(p_payload->>'provedor', 'postiz'),
     p_payload->>'referencia_externa',
     coalesce((p_payload->>'adapter_apto')::boolean, false),
     p_payload->>'motivo_inapto',
     p_autor_sub,
     coalesce(p_payload->>'timezone_padrao', 'America/Sao_Paulo'))
  RETURNING * INTO novo;

  recibo := jsonb_build_object(
    'destino_id', novo.id,
    'ativo_id', novo.ativo_id,
    'plataforma', novo.plataforma,
    'identidade_logica', novo.identidade_logica,
    'provedor', novo.provedor,
    'adapter_apto', novo.adapter_apto,
    'motivo_inapto', novo.motivo_inapto,
    'timezone_padrao', novo.timezone_padrao,
    'estado', novo.estado);

  RETURN public.publicacao_organica_registra_operacao(
    NULL, p_chave, 'publicacao_organica.registrar_destino', hash, recibo,
    'sucesso', p_autor_sub, p_autor_email);
END
$funcao$;


-- 10.2 criar job — onde o snapshot nasce e o horario vira instante
CREATE OR REPLACE FUNCTION public.publicacao_organica_criar_job(
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
  permitidos text[] := ARRAY['peca_tipo','peca_id','peca_versao','autorizacao_id',
                             'destino_id','modo','horario_local','timezone',
                             'consentimento_agora','corpo'];
  desconhecidos text;
  hash text;
  guardado jsonb;
  modo text;
  tz text;
  local_ts timestamp;
  instante timestamptz;
  volta timestamp;
  m public.criativo_master%ROWTYPE;
  d public.publicacao_organica_destino%ROWTYPE;
  a public.criativo_aprovacao%ROWTYPE;
  snapshot jsonb;
  novo public.publicacao_organica_job%ROWTYPE;
  recibo jsonb;
  consente boolean;
BEGIN
  IF jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'publicacao organica: a criacao de job exige um objeto JSON'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  SELECT string_agg(k, ', ' ORDER BY k) INTO desconhecidos
    FROM jsonb_object_keys(p_payload) AS k
   WHERE NOT (k = ANY (permitidos));
  IF desconhecidos IS NOT NULL THEN
    RAISE EXCEPTION
      'publicacao organica: recebeu campo(s) que este contrato nao conhece: %', desconhecidos
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  PERFORM public.cofre_recusa_chave_sensivel(p_payload, 'job');

  modo := p_payload->>'modo';
  IF modo IS NULL OR modo NOT IN ('draft','schedule','now') THEN
    RAISE EXCEPTION 'publicacao organica: modo deve ser draft, schedule ou now'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  consente := coalesce((p_payload->>'consentimento_agora')::boolean, false);
  IF modo = 'now' AND consente IS NOT TRUE THEN
    -- A recusa que impede "agora" de atravessar por descuido. Ela e ANTES da
    -- CHECK da tabela de proposito: a mensagem tem de dizer o que falta.
    RAISE EXCEPTION
      'publicacao organica: publicacao imediata exige consentimento humano explicito e especifico para este job'
      USING ERRCODE = 'check_violation';
  END IF;

  SELECT * INTO d FROM public.publicacao_organica_destino
   WHERE id = (p_payload->>'destino_id')::uuid;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'publicacao organica: destino inexistente'
      USING ERRCODE = 'foreign_key_violation';
  END IF;

  tz := coalesce(p_payload->>'timezone', d.timezone_padrao);

  -- A EXISTENCIA da zona, e nao so a forma. Uma zona inventada seria aceita
  -- pela CHECK de forma e produziria um instante silenciosamente errado.
  BEGIN
    PERFORM now() AT TIME ZONE tz;
  EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'publicacao organica: timezone IANA desconhecido'
      USING ERRCODE = 'invalid_parameter_value';
  END;

  instante := NULL;
  local_ts := NULL;
  IF modo = 'schedule' THEN
    IF p_payload->>'horario_local' IS NULL THEN
      RAISE EXCEPTION 'publicacao organica: agendar exige horario local declarado'
        USING ERRCODE = 'invalid_parameter_value';
    END IF;
    BEGIN
      local_ts := (p_payload->>'horario_local')::timestamp;
    EXCEPTION WHEN OTHERS THEN
      RAISE EXCEPTION 'publicacao organica: horario local nao e um instante valido'
        USING ERRCODE = 'invalid_parameter_value';
    END;

    -- ⚠️ A CONVERSAO NAO DEPENDE DO TZ DO SERVIDOR. `timestamp AT TIME ZONE
    -- <zona>` interpreta o instante NAQUELA zona e devolve timestamptz. Usar
    -- `now()` local ou `::timestamptz` sem zona faria o mesmo horario produzir
    -- instantes diferentes em maquinas diferentes.
    instante := local_ts AT TIME ZONE tz;

    -- Horario local que NAO EXISTE (salto de horario de verao) volta diferente.
    volta := instante AT TIME ZONE tz;
    IF volta IS DISTINCT FROM local_ts THEN
      RAISE EXCEPTION
        'publicacao organica: este horario local nao existe nesta zona (salto de horario de verao)'
        USING ERRCODE = 'invalid_parameter_value';
    END IF;

    IF instante <= now() THEN
      RAISE EXCEPTION
        'publicacao organica: agendar para o passado nao agenda nada'
        USING ERRCODE = 'invalid_parameter_value';
    END IF;
  END IF;

  hash := public.cofre_entrada_hash('publicacao_organica.criar_job', p_payload,
                                    jsonb_build_object('autor', p_autor_sub, 'email', p_autor_email));
  guardado := public.publicacao_organica_idempotencia(
                p_chave, 'publicacao_organica.criar_job', hash);
  IF guardado IS NOT NULL THEN
    RETURN guardado;
  END IF;

  SELECT * INTO a FROM public.criativo_aprovacao
   WHERE id = (p_payload->>'autorizacao_id')::uuid;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'publicacao organica: a autorizacao citada nao existe'
      USING ERRCODE = 'foreign_key_violation';
  END IF;

  IF coalesce(p_payload->>'peca_tipo','master') <> 'master' THEN
    RAISE EXCEPTION
      'publicacao organica: v1 publica apenas peca do tipo master'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  SELECT * INTO m FROM public.criativo_master WHERE id = (p_payload->>'peca_id')::uuid;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'publicacao organica: a peca citada nao existe'
      USING ERRCODE = 'foreign_key_violation';
  END IF;

  -- O SNAPSHOT. Montado a partir das colunas tipadas, aqui, uma vez. O
  -- despachante envia daqui. Reler o master no despacho seria abrir a porta que
  -- este bloco existe para fechar.
  --
  -- ⚠️ `insumo_sanitizado` NAO entra: e prompt, e a SPEC secao 10 proibe expo-lo.
  snapshot := jsonb_build_object(
    'schema', 'publicacao_organica/solicitacao/v1',
    'peca', jsonb_build_object(
      'tipo', 'master',
      'id', m.id,
      'versao', m.versao,
      'slot', m.slot,
      'kind', m.kind,
      'mime', m.mime,
      'content_hash', m.content_hash,
      'storage_chave', m.storage_chave,
      'largura', m.largura,
      'altura', m.altura,
      'duracao_ms', m.duracao_ms,
      'sintetico', m.sintetico,
      'disclosure', m.disclosure),
    'destino', jsonb_build_object(
      'destino_id', d.id,
      'ativo_id', d.ativo_id,
      'plataforma', d.plataforma,
      'identidade_logica', d.identidade_logica,
      'provedor', d.provedor,
      'referencia_externa', d.referencia_externa),
    'autorizacao', jsonb_build_object(
      'id', a.id,
      'finalidade', a.finalidade,
      'ator_id', a.ator_id,
      'decidido_em', a.decidido_em,
      'versao', a.versao),
    'quando', jsonb_build_object(
      'modo', modo,
      'horario_local', p_payload->>'horario_local',
      'timezone', tz,
      'instante_utc', instante),
    'corpo', coalesce(p_payload->'corpo', '{}'::jsonb));

  PERFORM public.cofre_recusa_chave_sensivel(snapshot, 'solicitacao');

  INSERT INTO public.publicacao_organica_job
    (owner_sub, owner_email, peca_tipo, peca_id, peca_versao, peca_content_hash,
     autorizacao_id, destino_id, projeto_id, modo, horario_local, timezone,
     instante_utc, estado, chave_idempotencia, entrada_hash, solicitacao,
     adapter, consentimento_agora, consentimento_ator, consentimento_em)
  VALUES
    (p_autor_sub, p_autor_email, 'master', m.id, m.versao, m.content_hash,
     a.id, d.id, m.projeto_id, modo, p_payload->>'horario_local', tz,
     instante, 'rascunho', p_chave, hash, snapshot,
     CASE WHEN d.provedor = 'multipost' THEN 'multipost' ELSE 'postiz' END,
     consente,
     CASE WHEN consente THEN p_autor_sub ELSE NULL END,
     CASE WHEN consente THEN now() ELSE NULL END)
  RETURNING * INTO novo;

  INSERT INTO public.publicacao_organica_transicao (job_id, de, para, motivo, ator_sub)
  VALUES (novo.id, NULL, 'rascunho', 'job criado', p_autor_sub);

  recibo := jsonb_build_object(
    'job_id', novo.id,
    'estado', novo.estado,
    'modo', novo.modo,
    'timezone', novo.timezone,
    'horario_local', novo.horario_local,
    'instante_utc', novo.instante_utc,
    'destino_id', novo.destino_id,
    'autorizacao_id', novo.autorizacao_id,
    'peca_id', novo.peca_id,
    'peca_versao', novo.peca_versao,
    'adapter', novo.adapter);

  RETURN public.publicacao_organica_registra_operacao(
    novo.id, p_chave, 'publicacao_organica.criar_job', hash, recibo,
    'sucesso', p_autor_sub, p_autor_email);
END
$funcao$;


-- 10.3 liberar para despacho — o unico caminho de rascunho para pronto
CREATE OR REPLACE FUNCTION public.publicacao_organica_liberar(
  p_job_id      uuid,
  p_autor_sub   uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  j public.publicacao_organica_job%ROWTYPE;
BEGIN
  SELECT * INTO j FROM public.publicacao_organica_job WHERE id = p_job_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'publicacao organica: job inexistente' USING ERRCODE = 'no_data_found';
  END IF;
  IF j.owner_sub <> p_autor_sub THEN
    RAISE EXCEPTION 'publicacao organica: este job pertence a outro dono'
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  -- A aprovacao pode ter sido revogada DEPOIS da criacao do job. Liberar sem
  -- reconferir publicaria com uma autorizacao que ja nao vale.
  IF EXISTS (SELECT 1 FROM public.criativo_aprovacao
              WHERE id = j.autorizacao_id AND revogada_em IS NOT NULL) THEN
    RAISE EXCEPTION
      'publicacao organica: a autorizacao deste job foi revogada; ele nao pode ser liberado'
      USING ERRCODE = 'check_violation';
  END IF;

  UPDATE public.publicacao_organica_job SET estado = 'pronto' WHERE id = p_job_id;
  INSERT INTO public.publicacao_organica_transicao (job_id, de, para, motivo, ator_sub)
  VALUES (p_job_id, j.estado, 'pronto', 'liberado para despacho', p_autor_sub);

  RETURN jsonb_build_object('job_id', p_job_id, 'estado', 'pronto');
END
$funcao$;


-- 10.4 reivindicar — claim/lease com fencing
-- ⚠️ `FOR UPDATE` sem `SKIP LOCKED` de proposito: o segundo consumidor ESPERA e
-- entao ve o estado ja mudado, e a recusa dele e informativa ("ja reivindicado
-- por outro"). Com SKIP LOCKED ele veria "nada para fazer", que e outra coisa.
CREATE OR REPLACE FUNCTION public.publicacao_organica_reivindicar(
  p_job_id         uuid,
  p_consumidor     text,
  p_lease_segundos integer DEFAULT 120
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  j public.publicacao_organica_job%ROWTYPE;
  novo_fencing bigint;
BEGIN
  IF p_lease_segundos IS NULL OR p_lease_segundos < 1 OR p_lease_segundos > 3600 THEN
    RAISE EXCEPTION 'publicacao organica: lease deve durar entre 1 e 3600 segundos'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF btrim(coalesce(p_consumidor, '')) = '' THEN
    RAISE EXCEPTION 'publicacao organica: reivindicar exige identificar o consumidor'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  SELECT * INTO j FROM public.publicacao_organica_job WHERE id = p_job_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'publicacao organica: job inexistente' USING ERRCODE = 'no_data_found';
  END IF;

  IF j.estado <> 'pronto' THEN
    RETURN jsonb_build_object(
      'reivindicado', false,
      'motivo', 'o job esta em "' || j.estado || '" e so "pronto" pode ser reivindicado',
      'estado', j.estado);
  END IF;

  IF j.lease_ate IS NOT NULL AND j.lease_ate > now() AND j.lease_owner <> p_consumidor THEN
    RETURN jsonb_build_object(
      'reivindicado', false,
      'motivo', 'ja reivindicado por outro consumidor',
      'estado', j.estado);
  END IF;

  novo_fencing := j.fencing + 1;

  UPDATE public.publicacao_organica_job
     SET estado      = 'em_voo',
         lease_owner = p_consumidor,
         lease_ate   = now() + make_interval(secs => p_lease_segundos),
         fencing     = novo_fencing,
         tentativas  = j.tentativas + 1
   WHERE id = p_job_id;

  INSERT INTO public.publicacao_organica_transicao
    (job_id, de, para, motivo, ator_sub, fencing)
  VALUES (p_job_id, j.estado, 'em_voo', 'reivindicado', NULL, novo_fencing);

  RETURN jsonb_build_object(
    'reivindicado', true,
    'fencing', novo_fencing,
    'estado', 'em_voo',
    'tentativa', j.tentativas + 1,
    'solicitacao', j.solicitacao);
END
$funcao$;


-- 10.5 concluir despacho — a transicao atomica, com recibo
CREATE OR REPLACE FUNCTION public.publicacao_organica_concluir_despacho(
  p_job_id       uuid,
  p_fencing      bigint,
  p_chave        text,
  p_desfecho     text,
  p_recibo       jsonb,
  p_autor_sub    uuid,
  p_autor_email  text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  j public.publicacao_organica_job%ROWTYPE;
  hash text;
  guardado jsonb;
  destino_estado text;
  externo text;
  estado_ext text;
  url text;
  publicado timestamptz;
  saida jsonb;
BEGIN
  IF p_desfecho NOT IN ('sucesso','falha','indeterminado') THEN
    RAISE EXCEPTION 'publicacao organica: desfecho deve ser sucesso, falha ou indeterminado'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF jsonb_typeof(p_recibo) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'publicacao organica: o recibo exige um objeto JSON'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  PERFORM public.cofre_recusa_chave_sensivel(p_recibo, 'recibo');

  hash := public.cofre_entrada_hash(
            'publicacao_organica.concluir_despacho:' || p_job_id::text,
            p_recibo,
            jsonb_build_object('fencing', p_fencing, 'desfecho', p_desfecho));
  guardado := public.publicacao_organica_idempotencia(
                p_chave, 'publicacao_organica.concluir_despacho', hash);
  IF guardado IS NOT NULL THEN
    RETURN guardado;
  END IF;

  SELECT * INTO j FROM public.publicacao_organica_job WHERE id = p_job_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'publicacao organica: job inexistente' USING ERRCODE = 'no_data_found';
  END IF;

  -- FENCING. Um despachante que dormiu e perdeu o lease escreve com fencing
  -- velho e e recusado, em vez de sobrescrever quem assumiu depois dele.
  IF j.fencing <> p_fencing THEN
    RAISE EXCEPTION
      'publicacao organica: fencing vencido (job em %, recebido %); outro consumidor assumiu este job',
      j.fencing, p_fencing
      USING ERRCODE = 'serialization_failure';
  END IF;

  IF j.estado <> 'em_voo' THEN
    RAISE EXCEPTION
      'publicacao organica: so um job em voo pode concluir despacho; este esta em "%"', j.estado
      USING ERRCODE = 'check_violation';
  END IF;

  externo    := p_recibo->>'referencia_externa';
  estado_ext := upper(coalesce(p_recibo->>'estado_externo', 'DESCONHECIDO'));
  url        := p_recibo->>'url_publicada';
  publicado  := CASE WHEN p_recibo->>'publicado_em' IS NULL
                     THEN NULL ELSE (p_recibo->>'publicado_em')::timestamptz END;

  IF p_desfecho = 'sucesso' THEN
    -- "API respondeu" nao vira "publicado". Um sucesso SEM referencia externa
    -- nao e sucesso: e resposta vazia, e resposta vazia nao e recibo.
    IF externo IS NULL OR btrim(externo) = '' THEN
      RAISE EXCEPTION
        'publicacao organica: sucesso sem referencia externa nao e recibo; use desfecho indeterminado'
        USING ERRCODE = 'check_violation';
    END IF;

    destino_estado := CASE j.modo
      WHEN 'draft'    THEN 'rascunho_externo'
      WHEN 'schedule' THEN 'agendado'
      WHEN 'now'      THEN 'publicacao_solicitada'
    END;

    INSERT INTO public.publicacao_organica_recibo
      (job_id, provedor, referencia_externa, estado_externo, url_publicada,
       publicado_em, bruto_sanitizado, origem)
    VALUES
      (p_job_id, j.adapter, externo,
       CASE WHEN estado_ext IN ('DRAFT','QUEUE','PUBLISHED','ERROR')
            THEN estado_ext ELSE 'DESCONHECIDO' END,
       url, publicado, p_recibo, 'despacho');

  ELSIF p_desfecho = 'falha' THEN
    destino_estado := 'falha';
  ELSE
    destino_estado := 'indeterminado';
  END IF;

  UPDATE public.publicacao_organica_job
     SET estado      = destino_estado,
         lease_owner = NULL,
         lease_ate   = NULL,
         ultimo_erro = CASE WHEN p_desfecho = 'sucesso' THEN NULL
                            ELSE left(coalesce(p_recibo->>'erro', 'sem detalhe'), 400) END
   WHERE id = p_job_id;

  INSERT INTO public.publicacao_organica_transicao
    (job_id, de, para, motivo, ator_sub, fencing)
  VALUES (p_job_id, j.estado, destino_estado,
          'despacho concluido: ' || p_desfecho, p_autor_sub, p_fencing);

  saida := jsonb_build_object(
    'job_id', p_job_id,
    'estado', destino_estado,
    'desfecho', p_desfecho,
    'referencia_externa', externo,
    'estado_externo', estado_ext,
    'url_publicada', url);

  RETURN public.publicacao_organica_registra_operacao(
    p_job_id, p_chave, 'publicacao_organica.concluir_despacho', hash, saida,
    p_desfecho, p_autor_sub, p_autor_email);
END
$funcao$;


-- 10.6 reconciliar — a saida do indeterminado, e o fechamento do publicado
CREATE OR REPLACE FUNCTION public.publicacao_organica_reconciliar(
  p_job_id       uuid,
  p_chave        text,
  p_observacao   jsonb,
  p_autor_sub    uuid,
  p_autor_email  text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  j public.publicacao_organica_job%ROWTYPE;
  hash text;
  guardado jsonb;
  externo text;
  estado_ext text;
  url text;
  publicado timestamptz;
  destino_estado text;
  saida jsonb;
BEGIN
  IF jsonb_typeof(p_observacao) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'publicacao organica: a observacao exige um objeto JSON'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;
  PERFORM public.cofre_recusa_chave_sensivel(p_observacao, 'observacao');

  hash := public.cofre_entrada_hash(
            'publicacao_organica.reconciliar:' || p_job_id::text, p_observacao,
            jsonb_build_object('autor', p_autor_sub));
  guardado := public.publicacao_organica_idempotencia(
                p_chave, 'publicacao_organica.reconciliar', hash);
  IF guardado IS NOT NULL THEN
    RETURN guardado;
  END IF;

  SELECT * INTO j FROM public.publicacao_organica_job WHERE id = p_job_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'publicacao organica: job inexistente' USING ERRCODE = 'no_data_found';
  END IF;

  IF j.estado NOT IN ('indeterminado','rascunho_externo','agendado',
                      'publicacao_solicitada','publicado') THEN
    RAISE EXCEPTION
      'publicacao organica: nada a reconciliar num job em "%"', j.estado
      USING ERRCODE = 'check_violation';
  END IF;

  externo    := p_observacao->>'referencia_externa';
  estado_ext := upper(coalesce(p_observacao->>'estado_externo','DESCONHECIDO'));
  url        := p_observacao->>'url_publicada';
  publicado  := CASE WHEN p_observacao->>'publicado_em' IS NULL
                     THEN NULL ELSE (p_observacao->>'publicado_em')::timestamptz END;

  -- Uma reconciliacao que nao encontrou o objeto NAO apaga o job e NAO o
  -- reprova: ela mantem o indeterminado e diz que nao achou. Doutrina de
  -- publicacao.py:1112 ("404 e relatado, nunca apaga a linha").
  IF externo IS NULL OR btrim(externo) = '' THEN
    destino_estado := 'indeterminado';
    saida := jsonb_build_object(
      'job_id', p_job_id, 'estado', destino_estado,
      'fechou', false,
      'motivo', 'o control plane nao devolveu referencia externa para este job');
  ELSE
    INSERT INTO public.publicacao_organica_recibo
      (job_id, provedor, referencia_externa, estado_externo, url_publicada,
       publicado_em, bruto_sanitizado, origem)
    VALUES
      (p_job_id, j.adapter, externo,
       CASE WHEN estado_ext IN ('DRAFT','QUEUE','PUBLISHED','ERROR')
            THEN estado_ext ELSE 'DESCONHECIDO' END,
       url, publicado, p_observacao, 'reconciliacao');

    destino_estado := CASE
      -- PUBLISHED com URL e instante e o unico caminho para reconciliado.
      WHEN estado_ext = 'PUBLISHED' AND btrim(coalesce(url,'')) <> '' AND publicado IS NOT NULL
        THEN 'reconciliado'
      WHEN estado_ext = 'ERROR'  THEN 'falha'
      WHEN estado_ext = 'DRAFT'  THEN 'rascunho_externo'
      WHEN estado_ext = 'QUEUE'  THEN 'agendado'
      ELSE 'indeterminado'
    END;

    -- `rascunho_externo` fecha em `reconciliado` quando o control plane confirma
    -- o rascunho: um draft reconciliado E o desfecho esperado do modo draft.
    IF j.modo = 'draft' AND estado_ext = 'DRAFT' THEN
      destino_estado := 'reconciliado';
    END IF;

    saida := jsonb_build_object(
      'job_id', p_job_id, 'estado', destino_estado,
      'fechou', destino_estado = 'reconciliado',
      'referencia_externa', externo,
      'estado_externo', estado_ext,
      'url_publicada', url);
  END IF;

  IF destino_estado <> j.estado THEN
    UPDATE public.publicacao_organica_job SET estado = destino_estado WHERE id = p_job_id;
    INSERT INTO public.publicacao_organica_transicao
      (job_id, de, para, motivo, ator_sub)
    VALUES (p_job_id, j.estado, destino_estado, 'reconciliacao', p_autor_sub);
  END IF;

  RETURN public.publicacao_organica_registra_operacao(
    p_job_id, p_chave, 'publicacao_organica.reconciliar', hash, saida,
    CASE WHEN destino_estado = 'falha' THEN 'falha'
         WHEN destino_estado = 'indeterminado' THEN 'indeterminado'
         ELSE 'sucesso' END,
    p_autor_sub, p_autor_email);
END
$funcao$;


-- 10.7 cancelar
CREATE OR REPLACE FUNCTION public.publicacao_organica_cancelar(
  p_job_id      uuid,
  p_motivo      text,
  p_autor_sub   uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  j public.publicacao_organica_job%ROWTYPE;
BEGIN
  IF btrim(coalesce(p_motivo,'')) = '' THEN
    RAISE EXCEPTION 'publicacao organica: cancelar exige motivo'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  SELECT * INTO j FROM public.publicacao_organica_job WHERE id = p_job_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'publicacao organica: job inexistente' USING ERRCODE = 'no_data_found';
  END IF;
  IF j.owner_sub <> p_autor_sub THEN
    RAISE EXCEPTION 'publicacao organica: este job pertence a outro dono'
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  -- Um job EM VOO nao e cancelavel: o pedido pode ja ter chegado ao destino, e
  -- marcar cancelado esconderia um post que existe. Ele passa por indeterminado.
  IF j.estado = 'em_voo' THEN
    RAISE EXCEPTION
      'publicacao organica: um job em voo nao e cancelado; reconcilie antes de decidir'
      USING ERRCODE = 'check_violation';
  END IF;

  UPDATE public.publicacao_organica_job
     SET estado = 'cancelado', cancelado_em = now(), cancelado_por = p_autor_sub,
         lease_owner = NULL, lease_ate = NULL
   WHERE id = p_job_id;

  INSERT INTO public.publicacao_organica_transicao (job_id, de, para, motivo, ator_sub)
  VALUES (p_job_id, j.estado, 'cancelado', left(p_motivo, 400), p_autor_sub);

  RETURN jsonb_build_object('job_id', p_job_id, 'estado', 'cancelado');
END
$funcao$;


-- -----------------------------------------------------------------------------
-- 11. LEITURA — o que a tela mostra, com dono no contrato e nunca opcional
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.publicacao_organica_listar_destinos(
  p_owner_sub uuid
)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $funcao$
  SELECT coalesce(jsonb_agg(x ORDER BY x->>'identidade_logica'), '[]'::jsonb)
    FROM (
      SELECT jsonb_build_object(
               'destino_id', d.id,
               'ativo_id', d.ativo_id,
               'nome', a.nome,
               'plataforma', d.plataforma,
               'identidade_logica', d.identidade_logica,
               'provedor', d.provedor,
               -- ⚠️ O destino INAPTO aparece, com o motivo. Filtra-lo daqui
               -- tornaria impossivel cumprir a guarda do ADR.
               'apto', d.adapter_apto AND d.estado = 'ativo',
               'motivo', CASE
                           WHEN d.estado <> 'ativo' THEN 'destino ' || d.estado
                           WHEN NOT d.adapter_apto THEN coalesce(d.motivo_inapto, 'sem adapter apto')
                           ELSE NULL END,
               'timezone_padrao', d.timezone_padrao,
               'estado', d.estado) AS x
        FROM public.publicacao_organica_destino d
        JOIN public.cofre_ativo a ON a.ativo_id = d.ativo_id
       WHERE d.owner_sub = p_owner_sub
    ) s;
$funcao$;

CREATE OR REPLACE FUNCTION public.publicacao_organica_listar_jobs(
  p_owner_sub uuid,
  p_estado    text DEFAULT NULL,
  p_limite    integer DEFAULT 50
)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $funcao$
  SELECT coalesce(jsonb_agg(x ORDER BY x->>'criado_em' DESC), '[]'::jsonb)
    FROM (
      SELECT jsonb_build_object(
               'job_id', j.id,
               'estado', j.estado,
               'modo', j.modo,
               'horario_local', j.horario_local,
               'timezone', j.timezone,
               'instante_utc', j.instante_utc,
               'tentativas', j.tentativas,
               'ultimo_erro', j.ultimo_erro,
               'adapter', j.adapter,
               'destino', jsonb_build_object(
                 'destino_id', d.id,
                 'plataforma', d.plataforma,
                 'identidade_logica', d.identidade_logica),
               'peca', jsonb_build_object(
                 'id', j.peca_id, 'versao', j.peca_versao,
                 'content_hash', j.peca_content_hash),
               'aprovacao', jsonb_build_object(
                 'id', a.id, 'ator_id', a.ator_id,
                 'finalidade', a.finalidade, 'decidido_em', a.decidido_em,
                 'revogada_em', a.revogada_em),
               'recibo', (
                 SELECT jsonb_build_object(
                          'referencia_externa', r.referencia_externa,
                          'estado_externo', r.estado_externo,
                          'url_publicada', r.url_publicada,
                          'publicado_em', r.publicado_em,
                          'observado_em', r.observado_em)
                   FROM public.publicacao_organica_recibo r
                  WHERE r.job_id = j.id
                  ORDER BY r.observado_em DESC, r.id DESC
                  LIMIT 1),
               'criado_em', j.criado_em,
               'atualizado_em', j.atualizado_em) AS x
        FROM public.publicacao_organica_job j
        JOIN public.publicacao_organica_destino d ON d.id = j.destino_id
        JOIN public.criativo_aprovacao a ON a.id = j.autorizacao_id
       WHERE j.owner_sub = p_owner_sub
         AND (p_estado IS NULL OR j.estado = p_estado)
       ORDER BY j.criado_em DESC
       LIMIT greatest(1, least(coalesce(p_limite, 50), 200))
    ) s;
$funcao$;

CREATE OR REPLACE FUNCTION public.publicacao_organica_detalhar_job(
  p_job_id    uuid,
  p_owner_sub uuid
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $funcao$
DECLARE
  j public.publicacao_organica_job%ROWTYPE;
BEGIN
  SELECT * INTO j FROM public.publicacao_organica_job WHERE id = p_job_id;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  -- ⚠️ Dono NAO e filtro opcional. Ler o job de outro dono seria vazamento, e
  -- devolver NULL aqui e a mesma resposta que "nao existe" — de proposito: a
  -- diferenca revelaria a existencia do job alheio.
  IF j.owner_sub <> p_owner_sub THEN
    RETURN NULL;
  END IF;

  RETURN jsonb_build_object(
    'job_id', j.id,
    'estado', j.estado,
    'modo', j.modo,
    'horario_local', j.horario_local,
    'timezone', j.timezone,
    'instante_utc', j.instante_utc,
    'tentativas', j.tentativas,
    'ultimo_erro', j.ultimo_erro,
    'adapter', j.adapter,
    'consentimento_agora', j.consentimento_agora,
    'consentimento_em', j.consentimento_em,
    'solicitacao', j.solicitacao,
    'criado_em', j.criado_em,
    'atualizado_em', j.atualizado_em,
    'recibos', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
               'referencia_externa', r.referencia_externa,
               'estado_externo', r.estado_externo,
               'url_publicada', r.url_publicada,
               'publicado_em', r.publicado_em,
               'origem', r.origem,
               'observado_em', r.observado_em) ORDER BY r.observado_em, r.id), '[]'::jsonb)
        FROM public.publicacao_organica_recibo r WHERE r.job_id = j.id),
    'historico', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
               'de', t.de, 'para', t.para, 'motivo', t.motivo,
               'criado_em', t.criado_em) ORDER BY t.criado_em, t.id), '[]'::jsonb)
        FROM public.publicacao_organica_transicao t WHERE t.job_id = j.id));
END
$funcao$;

-- Fila de despacho: o que esta pronto e ja chegou a hora. Sem dono no filtro
-- porque quem chama e o despachante do servidor, nao um navegador.
CREATE OR REPLACE FUNCTION public.publicacao_organica_fila(
  p_limite integer DEFAULT 20
)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $funcao$
  SELECT coalesce(jsonb_agg(jsonb_build_object(
           'job_id', j.id, 'modo', j.modo, 'instante_utc', j.instante_utc,
           'destino_id', j.destino_id) ORDER BY coalesce(j.instante_utc, j.criado_em)), '[]'::jsonb)
    FROM public.publicacao_organica_job j
   WHERE j.estado = 'pronto'
     AND (j.modo <> 'schedule' OR j.instante_utc <= now())
     AND (j.lease_ate IS NULL OR j.lease_ate <= now())
   LIMIT greatest(1, least(coalesce(p_limite, 20), 200));
$funcao$;


-- -----------------------------------------------------------------------------
-- 12. SEGURANCA — REVOKE nominal, RLS forcada, zero policy, grants minimos
-- -----------------------------------------------------------------------------
DO $seguranca$
DECLARE
  t text;
  f text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'publicacao_organica_destino','publicacao_organica_job',
    'publicacao_organica_operacao','publicacao_organica_recibo',
    'publicacao_organica_transicao'
  ]
  LOOP
    -- REVOKE NOMINAL: o default ACL deste banco concede por NOME, e so um
    -- REVOKE por nome tira. `FROM PUBLIC` sozinho nao resolve.
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated', t);
    -- `service_role` inclusive: ele tem BYPASSRLS, entao RLS nao o contem. O
    -- REVOKE contem. Sem esta linha, o backend escreveria direto na tabela e
    -- pularia allowlist, idempotencia, fencing e trilha de uma vez so.
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM service_role', t);

    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE  ROW LEVEL SECURITY', t);
  END LOOP;

  FOR f IN
    SELECT p.oid::regprocedure::text
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.proname LIKE 'publicacao\_organica\_%'
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM anon', f);
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM authenticated', f);
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM service_role', f);
  END LOOP;

  FOR f IN
    SELECT c.oid::regclass::text
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind = 'S'
       AND c.relname LIKE 'publicacao\_organica\_%'
  LOOP
    EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM PUBLIC, anon, authenticated, service_role', f);
  END LOOP;

  RAISE NOTICE 'v14_01: 5 tabelas revogadas nominalmente, RLS forcada, zero policies';
END
$seguranca$;

-- A API governada — e SOMENTE ela.
-- ⚠️ `publicacao_organica_idempotencia` e `publicacao_organica_registra_operacao`
-- ficam SEM grant: rodam dentro das governadas, com os privilegios do dono.
GRANT EXECUTE ON FUNCTION public.publicacao_organica_registrar_destino(jsonb, text, uuid, text)                        TO service_role;
GRANT EXECUTE ON FUNCTION public.publicacao_organica_criar_job(jsonb, text, uuid, text)                                TO service_role;
GRANT EXECUTE ON FUNCTION public.publicacao_organica_liberar(uuid, uuid)                                               TO service_role;
GRANT EXECUTE ON FUNCTION public.publicacao_organica_reivindicar(uuid, text, integer)                                  TO service_role;
GRANT EXECUTE ON FUNCTION public.publicacao_organica_concluir_despacho(uuid, bigint, text, text, jsonb, uuid, text)     TO service_role;
GRANT EXECUTE ON FUNCTION public.publicacao_organica_reconciliar(uuid, text, jsonb, uuid, text)                        TO service_role;
GRANT EXECUTE ON FUNCTION public.publicacao_organica_cancelar(uuid, text, uuid)                                        TO service_role;
GRANT EXECUTE ON FUNCTION public.publicacao_organica_listar_destinos(uuid)                                             TO service_role;
GRANT EXECUTE ON FUNCTION public.publicacao_organica_listar_jobs(uuid, text, integer)                                  TO service_role;
GRANT EXECUTE ON FUNCTION public.publicacao_organica_detalhar_job(uuid, uuid)                                          TO service_role;
GRANT EXECUTE ON FUNCTION public.publicacao_organica_fila(integer)                                                     TO service_role;


-- -----------------------------------------------------------------------------
-- 13. CONFERENCIA FINAL — a migration se recusa a terminar meio feita
-- -----------------------------------------------------------------------------
DO $conferencia$
DECLARE
  n_tabelas   int;
  n_rls       int;
  n_policies  int;
  n_funcoes   int;
  n_grants    int;
  n_triggers  int;
  abertas     text;
BEGIN
  SELECT count(*) INTO n_tabelas
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind = 'r'
     AND c.relname LIKE 'publicacao\_organica\_%';
  IF n_tabelas <> 5 THEN
    RAISE EXCEPTION 'v14_01: esperava 5 tabelas, encontrei %', n_tabelas;
  END IF;

  SELECT count(*) INTO n_rls
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind = 'r'
     AND c.relname LIKE 'publicacao\_organica\_%'
     AND c.relrowsecurity AND c.relforcerowsecurity;
  IF n_rls <> 5 THEN
    RAISE EXCEPTION 'v14_01: esperava 5 tabelas com RLS forcada, encontrei %', n_rls;
  END IF;

  SELECT count(*) INTO n_policies FROM pg_policies
   WHERE schemaname = 'public' AND tablename LIKE 'publicacao\_organica\_%';
  IF n_policies <> 0 THEN
    RAISE EXCEPTION 'v14_01: negacao e por AUSENCIA de policy; encontrei %', n_policies;
  END IF;

  -- Nenhum papel do Data API pode escrever nas tabelas.
  SELECT string_agg(format('%s/%s', t, r), ', ') INTO abertas
    FROM (
      SELECT c.relname AS t, r.rolname AS r
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN (SELECT rolname FROM pg_roles
                     WHERE rolname IN ('anon','authenticated','service_role')) r
       WHERE n.nspname = 'public' AND c.relkind = 'r'
         AND c.relname LIKE 'publicacao\_organica\_%'
         AND (has_table_privilege(r.rolname, c.oid, 'INSERT')
           OR has_table_privilege(r.rolname, c.oid, 'UPDATE')
           OR has_table_privilege(r.rolname, c.oid, 'DELETE')
           OR has_table_privilege(r.rolname, c.oid, 'SELECT'))
    ) s;
  IF abertas IS NOT NULL THEN
    RAISE EXCEPTION 'v14_01: tabela aberta a papel do Data API: %', abertas;
  END IF;

  SELECT count(*) INTO n_funcoes
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = 'public' AND p.proname LIKE 'publicacao\_organica\_%';
  IF n_funcoes < 15 THEN
    RAISE EXCEPTION 'v14_01: esperava ao menos 15 funcoes, encontrei %', n_funcoes;
  END IF;

  SELECT count(*) INTO n_grants
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = 'public' AND p.proname LIKE 'publicacao\_organica\_%'
     AND has_function_privilege('service_role', p.oid, 'EXECUTE');
  IF n_grants <> 11 THEN
    RAISE EXCEPTION 'v14_01: esperava 11 funcoes executaveis por service_role, encontrei %', n_grants;
  END IF;

  SELECT count(*) INTO n_triggers
    FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND NOT t.tgisinternal
     AND c.relname LIKE 'publicacao\_organica\_%';
  IF n_triggers <> 6 THEN
    RAISE EXCEPTION 'v14_01: esperava 6 gatilhos, encontrei %', n_triggers;
  END IF;

  RAISE NOTICE 'v14_01: conferencia ok — 5 tabelas, RLS forcada, 0 policies, % funcoes, 11 grants, 6 gatilhos',
    n_funcoes;
END
$conferencia$;

COMMIT;
