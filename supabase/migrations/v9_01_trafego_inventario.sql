-- =============================================================================
-- v9_01 — Inventario operacional de Trafego: dominio novo, separado do legado
-- FASE 1B / FRENTE 1 (dominio e banco). ARQUIVO. NAO APLICADO.
-- =============================================================================
-- APLICAR COMO: postgres  (supabase_admin tambem serve; a guarda aceita os dois)
--   -- (comando de aplicacao: ver runbook privado de infraestrutura)
--
-- ORDEM: independente da serie v8. Nao toca em nenhum objeto que a v8 cria ou
--        altera, e nao depende de nenhuma delas ter sido aplicada.
-- PREFLIGHT: supabase/migrations/README.md, secao "Preflight do v9_01".
-- ROLLBACK:  supabase/migrations/v9_99_trafego_inventario_rollback.sql
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO CRIA, E POR QUE EM TABELAS NOVAS
-- -----------------------------------------------------------------------------
-- Seis tabelas em public, prefixo trafego_:
--
--   trafego_linhagem          a intencao operacional, estavel no tempo
--   trafego_campanha          a IDENTIDADE — verdade do VOLC, nao espelho
--   trafego_campanha_espelho  o que a conta respondeu, com carimbo de leitura
--   trafego_snapshot_conta    o resultado de cada tentativa de leitura por conta
--   trafego_vinculo           campanha <-> funil, auditavel e reversivel
--   trafego_evento            registro append-only do que aconteceu
--
-- E DUAS projecoes de leitura (secao 12), que existem para o inventario ser
-- montado NO BANCO e nao no cliente:
--
--   trafego_inventario_campanha  identidade + espelho + vinculo ativo, com o
--                                booleano `atencao` calculado a partir de FATOS
--   trafego_inventario_conta     o snapshot da conta no vocabulario que a
--                                projecao le
--
-- Sem elas, `montar_inventario` faria uma consulta por campanha para descobrir
-- o espelho e outra para o vinculo — o N+1 classico, que some do plano de
-- consulta e reaparece como lentidao sem causa visivel.
--
-- Elas NAO substituem `campaigns` e NAO a alteram. A separacao e deliberada e
-- tem causa medida: o gatilho `sync_status_from_google_ads` e BEFORE
-- INSERT/UPDATE em `campaigns` e executa `NEW.status_source = 'auto'` sempre
-- que `google_ads_status` nao e nulo — e a porta de criacao SEMPRE envia esse
-- campo. Ou seja, a procedencia que a aplicacao declara e inalcancavel por
-- construcao naquela tabela (E-08, ADR-10). Declarar procedencia em `campaigns`
-- seria escrever num campo que um gatilho reescreve no mesmo comando.
--
-- Aqui a procedencia mora em `trafego_campanha.procedencia`, que nenhum gatilho
-- deriva. O unico gatilho que a toca RECUSA sobrescrita (ver secao 3).
--
-- -----------------------------------------------------------------------------
-- AS TRES REGRAS QUE ATRAVESSAM O SCHEMA INTEIRO
-- -----------------------------------------------------------------------------
-- A. NENHUM NUMERO SEM FRESCOR. Toda medida viaja com o instante em que foi
--    lida. As CHECKs `..._sem_carimbo` recusam a linha que traria numero sem
--    data. Custo sem data e indistinguivel de custo de ontem, e alguem decide
--    gasto olhando para ele.
--
-- B. AUSENCIA E NULL, NUNCA ZERO. Nenhuma coluna de medida tem DEFAULT 0.
--    Falha ao medir grava NULL; zero e um fato medido (a campanha nao
--    apareceu). Trocar um pelo outro inventa um resultado que ninguem observou.
--    O mesmo vale para texto: `customer_id = ''` e RECUSADO por CHECK —
--    ausencia conhecida e NULL. Os dois significam coisas diferentes e achata-
--    los apaga a diferenca entre "nao tem" e "nao sei" (E-02, E-10).
--
-- C. FALHA DE UMA CONTA NAO CONTAMINA AS OUTRAS. O isolamento e por linha: cada
--    conta tem a sua em `trafego_snapshot_conta`, e os gatilhos
--    `..._preserva_ultima_boa` impedem fisicamente que uma tentativa que
--    falhou apague a ultima leitura utilizavel.
--
-- -----------------------------------------------------------------------------
-- SEGURANCA — os defaults deste banco sao INSEGUROS, e por isso cada REVOKE
-- aqui e NOMINAL
-- -----------------------------------------------------------------------------
-- Medido em 2026-08-24 (o mesmo achado H que motivou a v8_07): `pg_default_acl`
-- do schema public concede `arwdDxt` a anon, authenticated e service_role em
-- TODA TABELA NOVA, para os dois donos (postgres e supabase_admin). E concede
-- EXECUTE em TODA FUNCAO NOVA para os mesmos tres papeis.
--
-- Consequencia direta: uma tabela criada aqui NASCE escrivel pelo navegador.
-- `REVOKE ... FROM PUBLIC` nao resolve — os grants do default ACL sao NOMINAIS,
-- concedidos a cada papel por nome, e so um REVOKE nominal os remove.
--
-- Por isso, para cada tabela deste arquivo:
--   1) REVOKE ALL ... FROM PUBLIC, anon, authenticated   (nominal, nao confia
--      em default privileges — que e exatamente o que esta quebrado);
--   2) ENABLE + FORCE ROW LEVEL SECURITY, com ZERO policies — negacao por
--      ausencia, defesa em profundidade: mesmo que um GRANT reapareca por
--      engano, anon continua lendo zero linha;
--   3) GRANT minimo e explicito para service_role — e so ele.
--
-- DELETE nao e concedido a NINGUEM em NENHUMA das seis tabelas. Nao ha caminho
-- de apagamento no dominio: campanha que sumiu da varredura recebe estado de
-- presenca (ADR-13), vinculo desfeito vira linha com `desfeito_em`, e evento e
-- append-only. Sem DELETE, o endpoint aberto de escrita generica que a Frente
-- 1/3 ainda vai fechar nao consegue destruir inventario nem trilha.
--
-- ⚠️ O QUE ISTO **NAO** PROTEGE, dito sem rodeio: `service_role` tem
-- `rolbypassrls = t`. RLS nao contem os endpoints que carregam a service key
-- sem autenticacao. Fecha-los e trabalho da Frente 1/3; ver o pedido registrado
-- no README. Esta migration contem anon e authenticated, que e o que o
-- navegador carrega.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO DELIBERADAMENTE NAO FAZ
-- -----------------------------------------------------------------------------
-- - Nao cria FK para `projects`, `pautador_funnel_runs` nem `campaigns`. O
--   vinculo e um REGISTRO DO QUE FOI DECIDIDO: ele precisa sobreviver ao
--   desaparecimento do alvo, senao a auditoria some junto com o dado auditado.
--   A conferencia de existencia dos alvos esta no preflight, como leitura.
-- - Nao cria tabela, coluna nem enum de Display, Demand Gen ou PMax. O
--   vocabulario de canal aceita os valores reais do enum do Google porque o
--   ESPELHO tem de registrar honestamente o que a conta respondeu — isso nao e
--   implementar canal (ADR-18, ADR-19).
-- - Nao implementa lance, orcamento, graduacao nem automacao. ADR-11 continua
--   valendo: nada disso esta aprovado.
--
-- -----------------------------------------------------------------------------
-- POR QUE `volc_campaign_id` E `text`, E NAO `uuid`
-- -----------------------------------------------------------------------------
-- A identidade interna e DERIVADA do par (customer_id, campaign_id), nao
-- sorteada — `backend/app/trafego/sincronizador.py:volc_campaign_id()` produz
-- `gads-<conta>-<campanha>`. A derivacao existe por uma razao operacional
-- medida: a varredura precisa ser idempotente SEM uma ida ao banco por campanha
-- para descobrir se a identidade ja existe. Um `uuid` sorteado exigiria essa
-- ida, e um erro nela cunharia uma SEGUNDA identidade para a mesma campanha
-- externa — exatamente o que ADR-02 existe para impedir.
--
-- A alternativa seria um uuid v5 derivado do mesmo par, que tambem e
-- determinstico. Ela foi recusada porque colocaria a REGRA DE DERIVACAO em dois
-- lugares: a do dominio (texto) e a da persistencia (uuid). Duas regras para a
-- mesma identidade e a mesma doenca de duas fontes de schema.
--
-- Consequencia aceita: nao ha `DEFAULT` para esta coluna. Identidade e sempre
-- DECLARADA por quem insere; o banco nao sorteia endereco de campanha. A CHECK
-- de forma abaixo recusa vazio e espaco, que sao as duas maneiras de a
-- identidade chegar "presente e inutil".
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
      'v9_01 deve rodar como postgres ou supabase_admin; papel atual: %',
      current_user;
  END IF;

  -- PG15 e o piso, e quem o define e a SECAO 12: `security_invoker` em VIEW so
  -- existe a partir do 15. Sem ele, uma view herda os privilegios do DONO — e as
  -- duas projecoes de leitura passariam por cima de toda a RLS das tabelas que
  -- elas juntam, entregando as seis a quem tivesse SELECT na view. O trabalho de
  -- seguranca da secao 13 viraria decoracao.
  --
  -- Producao medida em 24/08/2026: 15.8. O piso nao custa nada aqui e fecha o
  -- unico caminho pelo qual esta migration poderia abrir o que ela fecha.
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION
      'v9_01 exige PostgreSQL 15 ou maior (security_invoker em VIEW); aqui: %',
      current_setting('server_version');
  END IF;

  -- Reaplicacao parcial e como se chega a um schema meio migrado. Melhor
  -- abortar dizendo o que ja existe do que criar o resto por cima.
  SELECT string_agg(t, ', ' ORDER BY t) INTO ja_existem
    FROM unnest(ARRAY[
      'trafego_linhagem', 'trafego_campanha', 'trafego_campanha_espelho',
      'trafego_snapshot_conta', 'trafego_vinculo', 'trafego_evento',
      'trafego_inventario_campanha', 'trafego_inventario_conta'
    ]) AS t
   WHERE to_regclass('public.' || t) IS NOT NULL;

  IF ja_existem IS NOT NULL THEN
    RAISE EXCEPTION
      'v9_01 ja parece aplicada: % ja existe(m). Rode o rollback antes de reaplicar.',
      ja_existem;
  END IF;

  -- Os REVOKE nominais abaixo falham com erro cru se o papel nao existir.
  -- Num Supabase real os tres existem; num cluster descartavel, nao.
  SELECT string_agg(r, ', ' ORDER BY r) INTO faltando
    FROM unnest(ARRAY['anon', 'authenticated', 'service_role']) AS r
   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);

  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION
      'v9_01 exige os papeis do Supabase; ausente(s): %. Sem eles o REVOKE nominal nao acontece e a tabela nasce aberta.',
      faltando;
  END IF;

  RAISE NOTICE 'v9_01: guardas ok (papel=%, versao=%)',
    current_user, current_setting('server_version');
END
$guarda$;


-- -----------------------------------------------------------------------------
-- 1. trafego_linhagem — a intencao operacional
-- -----------------------------------------------------------------------------
-- Uma linhagem agrupa as instancias de uma mesma intencao ao longo do tempo.
-- Medido: a FGTS gerou tres campanhas externas numa noite e a Maquininha, duas
-- (E-05). Sem linhagem, "relancamento" e "campanha nova" sao indistinguiveis, e
-- a prova de duplicidade perde o unico sinal de intencao que ela tem (ADR-03).
CREATE TABLE public.trafego_linhagem (
  campaign_lineage_id  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

  rotulo               text        NOT NULL,
  declarada_por        text        NOT NULL,
  declarada_em         timestamptz NOT NULL DEFAULT now(),
  motivo               text,

  CONSTRAINT trafego_linhagem_rotulo_nao_vazio
    CHECK (btrim(rotulo) <> ''),
  CONSTRAINT trafego_linhagem_declarante_nao_vazio
    CHECK (btrim(declarada_por) <> '')
);

COMMENT ON TABLE  public.trafego_linhagem IS
  'Intencao operacional que agrupa instancias de campanha ao longo do tempo (ADR-02). Id imutavel.';
COMMENT ON COLUMN public.trafego_linhagem.declarada_por IS
  'Quem declarou a linhagem. Vazio e recusado: linhagem sem autor nao e auditavel.';


-- -----------------------------------------------------------------------------
-- 2. trafego_campanha — a IDENTIDADE. Verdade do VOLC, nao espelho.
-- -----------------------------------------------------------------------------
-- Esta tabela guarda o que o VOLC DECIDE: quem e a campanha, a que intencao ela
-- pertence, e como ela veio parar aqui. Nada nela e derivado da conta.
--
-- O que a conta responde mora em trafego_campanha_espelho, com carimbo. A
-- separacao e o conserto de ADR-10 em forma de schema: dado declarado e dado
-- espelhado nao dividem tabela, entao nenhum gatilho de espelho alcanca uma
-- declaracao.
CREATE TABLE public.trafego_campanha (
  -- text e sem DEFAULT: a identidade e DERIVADA do par (conta, campanha) pelo
  -- dominio, nunca sorteada pelo banco. Ver o cabecalho, secao
  -- "POR QUE `volc_campaign_id` E `text`".
  volc_campaign_id     text        PRIMARY KEY,
  campaign_lineage_id  uuid        REFERENCES public.trafego_linhagem (campaign_lineage_id)
                                   ON DELETE RESTRICT,

  -- IDENTIDADE EXTERNA. `customer_id` NULO significa "nao sei em que conta
  -- procurar" — e o estado das quatro linhas de `campaigns` medidas em 24/08
  -- (E-02), que ali estao como STRING VAZIA. Aqui vazio e recusado por CHECK,
  -- nao por validacao de aplicacao: a aplicacao ja tentou e o dado passou.
  customer_id          text,
  campaign_id          text        NOT NULL,

  -- PROCEDENCIA. Declarada pela aplicacao, nunca derivada pelo banco (ADR-10).
  procedencia               text        NOT NULL DEFAULT 'desconhecida',
  procedencia_declarada_por text,
  procedencia_declarada_em  timestamptz,

  criada_em            timestamptz NOT NULL DEFAULT now(),
  criada_por           text        NOT NULL,

  -- Vazio nao e ausencia. Se nao sabemos a conta, a coluna e NULL; se sabemos,
  -- ela e digito. A forma tambem recusa '801-785-1692' e '  8017851692  ',
  -- que sao a mesma conta escrita de um jeito que nao casa em JOIN nenhum.
  -- Identidade presente e inutil e o mesmo defeito de `customer_id = ''`: a
  -- coluna esta preenchida e nao endereca nada. A forma aceita tanto o
  -- `gads-<conta>-<campanha>` que o dominio deriva quanto um uuid em texto, e
  -- recusa espaco no meio — que quebraria o `in.(...)` do PostgREST em silencio.
  CONSTRAINT trafego_campanha_identidade_valida
    CHECK (volc_campaign_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$'),
  CONSTRAINT trafego_campanha_customer_id_valido
    CHECK (customer_id IS NULL OR customer_id ~ '^[0-9]{6,12}$'),
  CONSTRAINT trafego_campanha_campaign_id_valido
    CHECK (campaign_id ~ '^[0-9]{1,20}$'),
  CONSTRAINT trafego_campanha_criador_nao_vazio
    CHECK (btrim(criada_por) <> ''),
  CONSTRAINT trafego_campanha_procedencia_conhecida
    CHECK (procedencia IN ('volc_os', 'descoberta', 'legado', 'desconhecida')),

  -- 'desconhecida' e a ausencia de declaracao — logo nao tem declarante. Uma
  -- procedencia determinada SEM quem a declarou seria uma afirmacao sem autor,
  -- que e como `status_source = 'auto'` chegou onde chegou.
  CONSTRAINT trafego_campanha_procedencia_tem_autor
    CHECK (
      (procedencia = 'desconhecida'
        AND procedencia_declarada_por IS NULL
        AND procedencia_declarada_em IS NULL)
      OR
      (procedencia <> 'desconhecida'
        AND btrim(coalesce(procedencia_declarada_por, '')) <> ''
        AND procedencia_declarada_em IS NOT NULL)
    )
);

-- IDENTIDADE EXTERNA UNICA, em dois indices parciais em vez de um UNIQUE com
-- NULLS NOT DISTINCT. Motivo: NULLS NOT DISTINCT so existe a partir do PG15 e
-- amarraria o arquivo a uma versao; e os dois indices dizem em voz alta as duas
-- regras diferentes que estao sendo impostas.
CREATE UNIQUE INDEX trafego_campanha_identidade_externa_ux
  ON public.trafego_campanha (customer_id, campaign_id)
  WHERE customer_id IS NOT NULL;

-- Duas linhas sem conta e com o mesmo campaign_id sao a mesma campanha vista
-- duas vezes. Uma linha SEM conta e outra COM conta, mesmo campaign_id, podem
-- coexistir: nao sabemos que sao a mesma, e afirmar que sao seria inventar uma
-- medicao. Quando a reconciliacao promover a linha legada, o indice de cima
-- recusa a colisao — que e o momento certo de descobrir.
CREATE UNIQUE INDEX trafego_campanha_legado_sem_conta_ux
  ON public.trafego_campanha (campaign_id)
  WHERE customer_id IS NULL;

CREATE INDEX trafego_campanha_linhagem_ix
  ON public.trafego_campanha (campaign_lineage_id)
  WHERE campaign_lineage_id IS NOT NULL;

-- A ordem e a do keyset de `inventario.py` — `(customer_id, volc_campaign_id)`.
-- Um indice so em `customer_id` obrigaria um sort por pagina; com as duas
-- colunas o cursor caminha pelo indice.
CREATE INDEX trafego_campanha_conta_ix
  ON public.trafego_campanha (customer_id, volc_campaign_id)
  WHERE customer_id IS NOT NULL;

COMMENT ON TABLE  public.trafego_campanha IS
  'Identidade interna 1:1 com uma campanha externa (ADR-02). Imutavel: ver gatilho trafego_campanha_identidade_imutavel.';
COMMENT ON COLUMN public.trafego_campanha.customer_id IS
  'Conta de anuncio. NULL = nao sabemos qual. String vazia e RECUSADA por CHECK (E-02, E-10).';
COMMENT ON COLUMN public.trafego_campanha.procedencia IS
  'Como a campanha veio parar aqui. Declarada pela aplicacao; nenhum gatilho a deriva (ADR-10).';


-- -----------------------------------------------------------------------------
-- 3. Gatilho de identidade — imutabilidade, e a UNICA promocao permitida
-- -----------------------------------------------------------------------------
-- A unicidade nao basta. Um indice unico impede DUAS linhas iguais; ele nao
-- impede que a linha da campanha A passe a apontar para a campanha B, levando
-- junto o vinculo, a linhagem, os eventos e o recibo. Endereco que muda nao e
-- endereco, e a auditoria vira ficcao. Por isso a regra e um gatilho.
--
-- Uma unica transicao e permitida, e ela e MONOTONICA: customer_id NULL -> id
-- valido. Ela existe porque as linhas historicas nascem `legado nao
-- reconciliado` justamente por nao ter conta (ADR-13), e "cada estado tem um
-- caminho de saida diferente, e nenhum deles e apagar a linha". Sem essa
-- transicao, reconciliar uma linha legada exigiria criar outra e abandonar o
-- historico. O caminho de volta (id valido -> NULL, ou id -> outro id) e
-- recusado: desaprender uma conta nao e reconciliacao, e trocar de conta e
-- trocar de campanha.
CREATE OR REPLACE FUNCTION public.trafego_campanha_identidade_imutavel()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF NEW.volc_campaign_id IS DISTINCT FROM OLD.volc_campaign_id THEN
    RAISE EXCEPTION
      'trafego_campanha: volc_campaign_id e imutavel (% -> %). Ele e o endereco da campanha em recibo, vinculo e evento.',
      OLD.volc_campaign_id, NEW.volc_campaign_id
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.campaign_id IS DISTINCT FROM OLD.campaign_id THEN
    RAISE EXCEPTION
      'trafego_campanha: campaign_id e imutavel (% -> %). Outra campanha externa e outra linha, com outra identidade.',
      OLD.campaign_id, NEW.campaign_id
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- UM ramo, e nao dois. Havia aqui um segundo `IF NEW.customer_id IS NULL`
  -- com mensagem propria, e ele era CODIGO MORTO: para chegar nele seria
  -- preciso que OLD fosse NULL e NEW tambem — e nesse caso os dois nao sao
  -- DISTINCT, entao o `IF` de fora nem abre. Quem descobriu isso foi o
  -- `_prova_recusa` passando a exigir o SQLSTATE e a mensagem certos: a prova
  -- "customer_id conhecido nao volta a NULL" vinha passando pelo ramo de cima,
  -- e o de baixo nunca rodou uma vez sequer.
  --
  -- O ramo que sobrou cobre os DOIS casos, e a mensagem diz os dois: trocar de
  -- conta e trocar de campanha, e desaprender a conta nao e reconciliacao.
  IF NEW.customer_id IS DISTINCT FROM OLD.customer_id
     AND OLD.customer_id IS NOT NULL THEN
    RAISE EXCEPTION
      'trafego_campanha: customer_id ja conhecido (%) nao pode virar %. Reconciliacao promove de NULL para conhecido; nunca o contrario.',
      OLD.customer_id, coalesce(NEW.customer_id, 'NULL')
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- LINHAGEM ESTAVEL, mesma logica: atribuivel uma vez, nunca reescrita. ADR-02
  -- recomenda declara-la no lancamento, e uma campanha descoberta so a recebe
  -- quando alguem confirma a sugestao. O que nao pode e a intencao de ontem
  -- virar outra hoje, porque a linhagem e sinal FORTE na prova de duplicidade
  -- (ADR-03): reescreve-la muda um veredito ja dado.
  IF NEW.campaign_lineage_id IS DISTINCT FROM OLD.campaign_lineage_id
     AND OLD.campaign_lineage_id IS NOT NULL THEN
    RAISE EXCEPTION
      'trafego_campanha: campaign_lineage_id ja atribuido (%) e estavel; nao vira %.',
      OLD.campaign_lineage_id, coalesce(NEW.campaign_lineage_id::text, 'NULL')
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- PROCEDENCIA declarada nao e sobrescrita — nem pela aplicacao, nem por
  -- gatilho nenhum. E o defeito de E-08 fechado do lado do schema: la, um
  -- BEFORE trigger reescrevia `status_source` a cada UPDATE; aqui, a tentativa
  -- de reescrever LEVANTA. Resolver 'desconhecida' e permitido uma vez.
  IF NEW.procedencia IS DISTINCT FROM OLD.procedencia
     AND OLD.procedencia <> 'desconhecida' THEN
    RAISE EXCEPTION
      'trafego_campanha: procedencia ja declarada (%) nao vira %. Procedencia e declaracao da aplicacao, nao estado derivado (ADR-10).',
      OLD.procedencia, NEW.procedencia
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.criada_em IS DISTINCT FROM OLD.criada_em
     OR NEW.criada_por IS DISTINCT FROM OLD.criada_por THEN
    RAISE EXCEPTION
      'trafego_campanha: criada_em/criada_por sao registro de origem e nao mudam.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_campanha_identidade_imutavel
  BEFORE UPDATE ON public.trafego_campanha
  FOR EACH ROW EXECUTE FUNCTION public.trafego_campanha_identidade_imutavel();

COMMENT ON FUNCTION public.trafego_campanha_identidade_imutavel() IS
  'Recusa UPDATE da identidade, da linhagem ja atribuida e da procedencia ja declarada. Permite so a promocao monotonica de customer_id NULL -> conhecido.';


-- -----------------------------------------------------------------------------
-- 4. trafego_campanha_espelho — o que a conta respondeu, com carimbo
-- -----------------------------------------------------------------------------
-- Uma linha por campanha, sempre a leitura corrente. A conta e a autoridade
-- sobre existencia, status, lance, verba e entrega (ADR-01); aqui e memoria
-- governada, e memoria sem data nao governa nada.
CREATE TABLE public.trafego_campanha_espelho (
  volc_campaign_id     text        PRIMARY KEY
                                   REFERENCES public.trafego_campanha (volc_campaign_id)
                                   ON DELETE RESTRICT,

  -- Quando a CONTA foi lida. NOT NULL: nao existe espelho sem leitura.
  lido_em              timestamptz NOT NULL,

  -- Estado de presenca (ADR-13). Vocabulario fechado, e `sumiu_da_conta` nao
  -- esta nele de proposito: some e conclusao, e a conclusao erra quando a causa
  -- real foi uma leitura que falhou.
  --
  -- ⚠️ NULO = A CAMPANHA ESTAVA LA, SEM RESSALVA. E uma lacuna do vocabulario,
  -- nao um descuido: os seis estados do ADR-13 nomeiam apenas EXCECOES —
  -- `removida`, `nao_encontrada`, `conta_nao_identificada`, `fora_de_escopo`,
  -- `sincronizacao_falhou`, `legado_nao_reconciliado`. Nenhum deles nomeia o
  -- caso normal, que e a maioria das linhas. Inventar um setimo termo aqui
  -- seria decidir sozinho um vocabulario que o contrato congelou, entao a
  -- coluna admite NULL e a lacuna esta REGISTRADA para o dono fechar — ou
  -- acrescentando o termo, ou declarando `presenca` opcional no contrato.
  --
  -- ⚠️ O preco de admitir NULL: "esqueci de escrever" e "esta tudo bem" ficam
  -- iguais no banco. Quem fecha isso e a porta de escrita — a funcao
  -- `presenca()` de `backend/app/trafego/dominio.py` LEVANTA quando nao ha
  -- leitura, em vez de devolver NULL. Enquanto a lacuna existir, essa e a unica
  -- trava; ela e de aplicacao, e por isso esta dita aqui em voz alta.
  presenca             text,

  nome                 text,
  -- Sem traducao: o que o Google respondeu (ENABLED / PAUSED / REMOVED).
  estado_externo       text,
  veiculacao           text,
  canal                text,
  estrategia           text,
  url_final            text,

  -- O QUE A CONTA RESPONDEU, ANTES DA TRADUCAO. `canal_canonico()` devolve NULL
  -- para canal fora do vocabulario e `estrategia_canonica()` faz o mesmo — e sem
  -- estas duas colunas o fato "a conta respondeu TRAVEL" seria destruido na
  -- gravacao. A tela mostraria "canal: —" e ninguem teria como descobrir por que.
  -- Sao forense: nenhuma CHECK as fecha, e nada as le como verdade de dominio.
  canal_bruto          text,
  estrategia_bruta     text,

  lance_micros         bigint,
  verba_diaria_micros  bigint,

  -- ENTREGA. Nenhum DEFAULT 0 aqui, em nenhuma das quatro colunas: zero e "a
  -- campanha nao apareceu", NULL e "nao consegui medir". Medido em 24/08: as
  -- duas campanhas vivas tinham 1 e 4 impressoes e R$ 0,00 gastos (E-01) —
  -- zeros VERDADEIROS, que so significam alguma coisa se nao puderem ser
  -- confundidos com falha de leitura.
  impressoes           bigint,
  cliques              bigint,
  custo_micros         bigint,
  entrega_lida_em      timestamptz,

  -- MOEDA NAO E MEDIDA, E UNIDADE. Ela denomina `lance_micros` e
  -- `verba_diaria_micros` tambem, e esses dois tem o carimbo da camada comum
  -- (`lido_em`), nao o da entrega. Enquanto ela estava dentro do grupo da
  -- entrega, a CHECK `..._entrega_sem_carimbo` obrigava a apaga-la sempre que a
  -- medicao de entrega falhava — e a verba do dia aparecia na tela sem dizer em
  -- que moeda. Regra A fala de NUMERO sem data; moeda nao e numero.
  moeda                text,

  atualizado_em        timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT trafego_espelho_presenca_conhecida
    CHECK (presenca IS NULL OR presenca IN (
      'removida', 'nao_encontrada', 'conta_nao_identificada',
      'fora_de_escopo', 'sincronizacao_falhou', 'legado_nao_reconciliado'
    )),

  -- VOCABULARIO CANONICO DE CANAL (ADR-18). A lista e a do enum do Google, e
  -- nao a dos canais implementados, porque o espelho tem de registrar o que a
  -- conta respondeu — inclusive um canal que nos nao sabemos construir. O que a
  -- CHECK impede e o apelido: 'PMAX' e recusado, 'PERFORMANCE_MAX' passa. Foi
  -- exatamente essa divergencia que E-21 mediu em cinco lugares.
  -- Recusar canal sem construtor e trabalho da PORTA DE CRIACAO, nao do espelho.
  CONSTRAINT trafego_espelho_canal_canonico
    CHECK (canal IS NULL OR canal IN (
      'SEARCH', 'DISPLAY', 'DEMAND_GEN', 'PERFORMANCE_MAX',
      'VIDEO', 'SHOPPING', 'DISCOVERY', 'MULTI_CHANNEL',
      'LOCAL', 'LOCAL_SERVICES', 'SMART', 'HOTEL', 'TRAVEL',
      'UNSPECIFIED', 'UNKNOWN'
    )),

  -- `estrategia` NAO tem lista fechada, e a assimetria e proposital: a conta
  -- pode responder TARGET_SPEND, MAXIMIZE_CLICKS, TARGET_ROAS e mais meia duzia
  -- que o produto nao usa hoje. Uma CHECK fechada faria a varredura FALHAR ao
  -- ler uma campanha legitima — e a falha apareceria como "sincronizacao
  -- falhou" numa conta que respondeu perfeitamente.
  CONSTRAINT trafego_espelho_estrategia_nao_vazia
    CHECK (estrategia IS NULL OR btrim(estrategia) <> ''),

  CONSTRAINT trafego_espelho_moeda_iso
    CHECK (moeda IS NULL OR moeda ~ '^[A-Z]{3}$'),

  -- Micros nunca sao negativos, e um negativo aqui e sinal de conversao errada
  -- de unidade, nao de desconto.
  CONSTRAINT trafego_espelho_numeros_nao_negativos
    CHECK (
      coalesce(lance_micros, 0) >= 0
      AND coalesce(verba_diaria_micros, 0) >= 0
      AND coalesce(impressoes, 0) >= 0
      AND coalesce(cliques, 0) >= 0
      AND coalesce(custo_micros, 0) >= 0
    ),

  -- REGRA A, em forma de constraint: numero de entrega sem carimbo nao entra.
  -- `moeda` ficou de fora do grupo de proposito — ver o comentario da coluna.
  CONSTRAINT trafego_espelho_entrega_sem_carimbo
    CHECK (
      (impressoes IS NULL AND cliques IS NULL AND custo_micros IS NULL)
      OR entrega_lida_em IS NOT NULL
    )
);

CREATE INDEX trafego_espelho_presenca_ix
  ON public.trafego_campanha_espelho (presenca);

CREATE INDEX trafego_espelho_lido_em_ix
  ON public.trafego_campanha_espelho (lido_em DESC);

COMMENT ON TABLE  public.trafego_campanha_espelho IS
  'Espelho da conta, com carimbo de leitura (ADR-01). Nenhuma coluna daqui e verdade do VOLC.';
COMMENT ON COLUMN public.trafego_campanha_espelho.impressoes IS
  'NULL = nao foi possivel medir. 0 = medido e a campanha nao apareceu. Sem DEFAULT, de proposito.';
COMMENT ON COLUMN public.trafego_campanha_espelho.presenca IS
  'Um dos seis estados do ADR-13, ou NULL para "estava la, sem ressalva" — os seis nomeiam so excecoes. Nao existe "sumiu da conta".';


-- -----------------------------------------------------------------------------
-- 5. Gatilho do espelho — a leitura nao anda para tras, e falha nao apaga
-- -----------------------------------------------------------------------------
-- Duas coisas que so o banco consegue garantir, porque dependem do estado
-- anterior da linha e a aplicacao nao o tem em maos no momento do UPSERT:
--
--  (i) uma varredura atrasada nao sobrescreve uma leitura mais nova. Sem isto,
--      duas sincronizacoes concorrentes fazem o inventario oscilar e a idade do
--      dado passa a mentir.
--
-- (ii) uma tentativa que nao mediu entrega NAO apaga a ultima entrega medida.
--      E a regra C dentro da linha: a ultima medida boa fica, E O CARIMBO DELA
--      FICA JUNTO. Preservar o numero sem preservar a data seria pior que
--      apagar — viraria dado velho passando por novo.
--
-- (iii) uma tentativa que nao trouxe os ROTULOS nao apaga os rotulos.
--      E a mesma regra C, um degrau acima: sem isto uma leitura parcial deixava
--      a linha SEM NOME na tela, e uma campanha sem nome nao e operavel — o
--      operador nao sabe o que esta olhando nem o que pausar.
--
-- A LINHA QUE SEPARA (ii) DE (iii), E QUE DECIDE CADA COLUNA
--
-- A pergunta e uma so: NULO nesta coluna pode ser um fato MEDIDO?
--
--   · Se PODE, preservar INVENTA. A tela mostraria como atual um valor que a
--     conta ja nao tem, e ninguem teria como notar.
--   · Se NAO PODE — porque a API sempre responde algo ali —, o nulo so pode
--     significar "esta varredura nao mediu isto", e aceita-lo apaga dado bom.
--
-- Aplicada coluna a coluna, essa pergunta cai exatamente sobre a divisao entre
-- ROTULO e NUMERO, e e por isso que a regra final cabe numa frase:
-- PRESERVA-SE ROTULO; NUNCA NUMERO. Numero so sobrevive junto do carimbo dele,
-- que e o que o bloco (ii) faz com a entrega.
CREATE OR REPLACE FUNCTION public.trafego_espelho_preserva_ultima_boa()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF NEW.lido_em < OLD.lido_em THEN
    RAISE EXCEPTION
      'trafego_campanha_espelho: leitura de % e mais velha que a corrente (%). Varredura atrasada nao sobrescreve leitura mais nova.',
      NEW.lido_em, OLD.lido_em
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- A CHECK `..._entrega_sem_carimbo` nao alcanca este caso: quando existe uma
  -- entrega boa anterior, a preservacao abaixo reescreveria NEW e a linha
  -- passaria na CHECK — engolindo em silencio um numero que o chamador mandou
  -- sem data. Regra A vale igual com ou sem historico, entao a recusa e aqui.
  IF NEW.entrega_lida_em IS NULL
     AND (NEW.impressoes IS NOT NULL OR NEW.cliques IS NOT NULL
          OR NEW.custo_micros IS NOT NULL)
  THEN
    RAISE EXCEPTION
      'trafego_campanha_espelho: entrega com numero e sem carimbo de leitura. Um custo sem data e indistinguivel de um custo de ontem.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- (iii) ROTULOS. Preservados porque NULO neles so pode ser "nao medi":
  --
  --   nome            a API nunca responde campanha sem nome. Sem ele a linha
  --                   fica sem identificacao na tela — o defeito mais visivel
  --                   de uma leitura parcial.
  --   estado_externo  `campaign.status` sempre volta (ENABLED/PAUSED/REMOVED).
  --   veiculacao      quando pedida, sempre volta; nulo = nao foi pedida.
  --   canal           `advertising_channel_type` sempre volta E e IMUTAVEL na
  --                   campanha do Google Ads — o valor antigo continua sendo a
  --                   verdade, entao preservar nao pode envelhecer.
  --   canal_bruto     idem: e a resposta crua do mesmo campo.
  --   moeda           a conta sempre tem moeda; e unidade, nao medida.
  --
  -- FICAM DE FORA, e cada um por um motivo diferente:
  --
  --   presenca        NULO E O FATO "presente, sem ressalva". Preservar deixaria
  --                   `removida` colada para sempre numa campanha reativada —
  --                   inverteria a regra em vez de protege-la.
  --   estrategia      MUDA na vida da campanha, e `estrategia_canonica()`
  --                   devolve NULL para estrategia fora do vocabulario. Ou seja,
  --                   o nulo PODE ser medicao. Preservar mostraria MANUAL_CPC
  --                   numa campanha ja em TARGET_ROAS — e `teto_de_cliques()`
  --                   calcularia um teto que nao existe, a partir de um lance
  --                   que ninguem mais usa.
  --   estrategia_bruta  acompanha `estrategia`: preservar o cru sem o traduzido
  --                   faria os dois discordarem, que e pior que os dois nulos.
  --   url_final       ausencia legitima: campanha pode nao ter URL final.
  --   lance_micros    ausencia legitima: lance automatico nao tem lance manual.
  --                   E e NUMERO — o carimbo dele e `lido_em`, que acabou de
  --                   avancar; preserva-lo seria dado velho passando por novo.
  --   verba_diaria_micros  idem, e tambem NUMERO.
  NEW.nome           := coalesce(NEW.nome,           OLD.nome);
  NEW.estado_externo := coalesce(NEW.estado_externo, OLD.estado_externo);
  NEW.veiculacao     := coalesce(NEW.veiculacao,     OLD.veiculacao);
  NEW.canal          := coalesce(NEW.canal,          OLD.canal);
  NEW.canal_bruto    := coalesce(NEW.canal_bruto,    OLD.canal_bruto);
  NEW.moeda          := coalesce(NEW.moeda,          OLD.moeda);

  IF OLD.entrega_lida_em IS NOT NULL
     AND (NEW.entrega_lida_em IS NULL OR NEW.entrega_lida_em < OLD.entrega_lida_em)
  THEN
    NEW.impressoes      := OLD.impressoes;
    NEW.cliques         := OLD.cliques;
    NEW.custo_micros    := OLD.custo_micros;
    -- A moeda que DENOMINA os numeros preservados tem de ser a daquela leitura,
    -- e nao a que chegou agora. O `coalesce` acima ja protege o caso comum
    -- (moeda nova nula); esta linha protege o caso raro em que ela vem
    -- diferente — numero antigo com moeda nova seria conversao inventada.
    NEW.moeda           := OLD.moeda;
    NEW.entrega_lida_em := OLD.entrega_lida_em;
  END IF;

  NEW.atualizado_em := now();
  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_espelho_preserva_ultima_boa
  BEFORE UPDATE ON public.trafego_campanha_espelho
  FOR EACH ROW EXECUTE FUNCTION public.trafego_espelho_preserva_ultima_boa();

COMMENT ON FUNCTION public.trafego_espelho_preserva_ultima_boa() IS
  'Recusa leitura retroativa; preserva os ROTULOS (nome, estado, veiculacao, canal, moeda) e a ultima entrega medida junto do carimbo dela. Nunca preserva NUMERO sem carimbo, nem presenca.';


-- -----------------------------------------------------------------------------
-- 6. trafego_snapshot_conta — o resultado de CADA tentativa de leitura
-- -----------------------------------------------------------------------------
-- Uma linha por conta. A linha carrega DOIS tempos distintos, e nao ha como
-- fundi-los sem perder informacao:
--
--   tentativa_*   a ultima tentativa, tenha ela dado certo ou nao;
--   leitura_boa_* a ultima tentativa que deu certo.
--
-- Medido em 24/08: hoje tres contas falhando e visualmente identico a "tudo
-- bem" (E-07). A separacao acima e o que permite a tela dizer "falhou agora,
-- ultimo dado bom e de ha 40 min" em vez de escolher entre mentir e apagar.
--
-- AUSENCIA DE LINHA E INFORMACAO: conta descoberta que nunca foi varrida NAO
-- tem linha aqui, e a projecao a chama de `nunca_lido`. "Nao perguntei" e
-- "perguntei e nao ha nada" levam a acoes opostas e nao podem ser a mesma coisa.
-- Por isso `vazio_confirmado` tambem NAO e um valor de `tentativa_resultado`:
-- ele e derivado (resultado 'ok' com zero campanhas), para nao existirem duas
-- fontes da mesma verdade que possam divergir.
CREATE TABLE public.trafego_snapshot_conta (
  customer_id            text        PRIMARY KEY,
  nome                   text,

  tentativa_em           timestamptz NOT NULL,
  tentativa_resultado    text        NOT NULL,
  tentativa_motivo       text,

  -- O QUE faltou, separado do PORQUE. A varredura sabe dizer o escopo
  -- (`entrega(ultimos_7d)`, `filhas(SEARCH)`) e o motivo, e junta-los num texto
  -- so obrigaria a projecao a parti-lo de volta com uma heuristica. Sem esta
  -- coluna, `montar_inventario` cai no literal "conta" e o operador perde a
  -- unica pista de onde procurar.
  tentativa_escopo       text,
  tentativa_duracao_ms   integer,

  leitura_boa_em         timestamptz,
  leitura_boa_campanhas  integer,
  leitura_boa_duracao_ms integer,

  atualizado_em          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT trafego_snapshot_customer_id_valido
    CHECK (customer_id ~ '^[0-9]{6,12}$'),
  -- TRES desfechos, e o do meio e o que a regra E protege. `parcial` e "a camada
  -- comum voltou e alguma parte nao" — a entrega, ou as entidades filhas de um
  -- canal. Sem ele, a varredura parcial teria de ser gravada como 'ok', e
  -- `frescor_da_conta()` devolveria `recente` para uma conta que nao entregou
  -- metade do que foi pedido. Frescor desconhecido virando `recente` e
  -- exatamente o que nao pode acontecer.
  CONSTRAINT trafego_snapshot_resultado_conhecido
    CHECK (tentativa_resultado IN ('ok', 'parcial', 'falhou')),

  -- Falha sem motivo e o mesmo defeito de "sumiu da conta": um rotulo que
  -- esconde a causa. Quem escreve 'falhou' — ou 'parcial' — tem de dizer o que
  -- aconteceu. `parcial` sem motivo seria pior que 'ok': avisa que falta algo e
  -- nao diz o que.
  CONSTRAINT trafego_snapshot_falha_tem_motivo
    CHECK (
      tentativa_resultado NOT IN ('falhou', 'parcial')
      OR btrim(coalesce(tentativa_motivo, '')) <> ''
    ),

  -- Leitura boa e um par indivisivel: quando ela existe, existe a contagem.
  CONSTRAINT trafego_snapshot_leitura_boa_completa
    CHECK ((leitura_boa_em IS NULL) = (leitura_boa_campanhas IS NULL)),

  CONSTRAINT trafego_snapshot_contagens_nao_negativas
    CHECK (
      coalesce(leitura_boa_campanhas, 0) >= 0
      AND coalesce(tentativa_duracao_ms, 0) >= 0
      AND coalesce(leitura_boa_duracao_ms, 0) >= 0
    ),

  CONSTRAINT trafego_snapshot_leitura_boa_nao_futura
    CHECK (leitura_boa_em IS NULL OR leitura_boa_em <= tentativa_em)
);

COMMENT ON TABLE  public.trafego_snapshot_conta IS
  'Resultado da ultima tentativa de leitura por conta + a ultima leitura BOA, em colunas separadas (regra C). Ausencia de linha = nunca lido.';
COMMENT ON COLUMN public.trafego_snapshot_conta.leitura_boa_em IS
  'Ultima leitura bem-sucedida. Uma falha nova NAO a apaga — ver gatilho trafego_snapshot_preserva_ultima_boa.';


-- -----------------------------------------------------------------------------
-- 7. Gatilho do snapshot — falha nova nao apaga leitura boa antiga
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trafego_snapshot_preserva_ultima_boa()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF NEW.tentativa_em < OLD.tentativa_em THEN
    RAISE EXCEPTION
      'trafego_snapshot_conta: tentativa de % e mais velha que a corrente (%).',
      NEW.tentativa_em, OLD.tentativa_em
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- A parte que importa: o escritor da varredura NAO precisa lembrar de
  -- recopiar a leitura boa quando falha. Se ele esquecer, o banco lembra. Uma
  -- regra que depende de ninguem esquecer nao e regra.
  -- Mesma armadilha do espelho: a preservacao abaixo faria a CHECK de par
  -- indivisivel passar por cima de uma contagem sem data.
  IF NEW.leitura_boa_em IS NULL AND NEW.leitura_boa_campanhas IS NOT NULL THEN
    RAISE EXCEPTION
      'trafego_snapshot_conta: contagem de campanhas sem o instante da leitura boa.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF OLD.leitura_boa_em IS NOT NULL
     AND (NEW.leitura_boa_em IS NULL OR NEW.leitura_boa_em < OLD.leitura_boa_em)
  THEN
    NEW.leitura_boa_em         := OLD.leitura_boa_em;
    NEW.leitura_boa_campanhas  := OLD.leitura_boa_campanhas;
    NEW.leitura_boa_duracao_ms := OLD.leitura_boa_duracao_ms;
  END IF;

  NEW.atualizado_em := now();
  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_snapshot_preserva_ultima_boa
  BEFORE UPDATE ON public.trafego_snapshot_conta
  FOR EACH ROW EXECUTE FUNCTION public.trafego_snapshot_preserva_ultima_boa();

COMMENT ON FUNCTION public.trafego_snapshot_preserva_ultima_boa() IS
  'Recusa tentativa retroativa e impede que uma tentativa que falhou apague a ultima leitura boa da conta.';


-- -----------------------------------------------------------------------------
-- 8. trafego_vinculo — campanha <-> funil, auditavel e reversivel
-- -----------------------------------------------------------------------------
-- "O sistema sugere; o operador confirma" (ADR-09). Aqui isso e estrutural:
-- `confirmado_por` e NOT NULL e nao aceita vazio, entao VINCULO SEM CONFIRMACAO
-- HUMANA NAO EXISTE — nao ha estado "sugerido" nesta tabela. Sugestao e
-- calculo, e calculo nao se persiste como se fosse decisao.
--
-- Reversibilidade sem apagamento: desfazer preenche `desfeito_*`. A linha fica,
-- porque o risco medido de um vinculo errado e contaminar atribuicao de receita
-- de forma permanente e silenciosa — e reconstruir o que foi desfeito exige
-- saber que foi desfeito, por quem e por que.
--
-- SEM FK para `projects` / `pautador_funnel_runs` / `campaigns`, de proposito:
-- o vinculo e o registro de uma DECISAO, e ele precisa sobreviver ao
-- desaparecimento do alvo. Uma FK faria a trilha de auditoria ser apagada junto
-- com o dado auditado — ou faria a limpeza do legado travar sem explicacao.
-- A conferencia de existencia dos alvos esta no preflight, como LEITURA.
CREATE TABLE public.trafego_vinculo (
  vinculo_id        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  volc_campaign_id  text        NOT NULL
                                REFERENCES public.trafego_campanha (volc_campaign_id)
                                ON DELETE RESTRICT,

  opportunity_id    bigint,
  project_id        bigint,
  funnel_run_id     bigint,

  -- Qual regra casou, e com que evidencia. "Cada sugestao declara qual regra
  -- casou — sugestao sem regra visivel nao e oferecida" (SPEC 3.2). Se a regra
  -- nao viaja ate aqui, o operador confirmou uma caixa-preta.
  regra             text        NOT NULL,
  evidencia         jsonb       NOT NULL DEFAULT '{}'::jsonb,

  confirmado_por    text        NOT NULL,
  confirmado_em     timestamptz NOT NULL DEFAULT now(),

  -- Qual vinculo este substituiu. E o que permite reconstruir a cadeia inteira
  -- de decisoes sobre a mesma campanha.
  vinculo_anterior  uuid        REFERENCES public.trafego_vinculo (vinculo_id)
                                ON DELETE RESTRICT,

  desfeito_por      text,
  desfeito_em       timestamptz,
  desfeito_motivo   text,

  CONSTRAINT trafego_vinculo_regra_nao_vazia
    CHECK (btrim(regra) <> ''),
  CONSTRAINT trafego_vinculo_confirmado_por_nao_vazio
    CHECK (btrim(confirmado_por) <> ''),

  -- Vinculo que nao aponta para nada nao e vinculo.
  CONSTRAINT trafego_vinculo_tem_alvo
    CHECK (opportunity_id IS NOT NULL OR project_id IS NOT NULL OR funnel_run_id IS NOT NULL),

  CONSTRAINT trafego_vinculo_desfazer_completo
    CHECK (
      (desfeito_em IS NULL AND desfeito_por IS NULL)
      OR (desfeito_em IS NOT NULL AND btrim(coalesce(desfeito_por, '')) <> '')
    ),
  CONSTRAINT trafego_vinculo_desfeito_depois_de_confirmado
    CHECK (desfeito_em IS NULL OR desfeito_em >= confirmado_em),
  CONSTRAINT trafego_vinculo_nao_aponta_para_si
    CHECK (vinculo_anterior IS NULL OR vinculo_anterior <> vinculo_id)
);

-- No maximo um vinculo ATIVO por campanha. Vinculos desfeitos ficam, tantos
-- quantos forem, e e por isso que o indice e parcial.
CREATE UNIQUE INDEX trafego_vinculo_ativo_por_campanha_ux
  ON public.trafego_vinculo (volc_campaign_id)
  WHERE desfeito_em IS NULL;

CREATE INDEX trafego_vinculo_campanha_ix   ON public.trafego_vinculo (volc_campaign_id);
CREATE INDEX trafego_vinculo_projeto_ix    ON public.trafego_vinculo (project_id)
  WHERE project_id IS NOT NULL;
CREATE INDEX trafego_vinculo_oportunidade_ix ON public.trafego_vinculo (opportunity_id)
  WHERE opportunity_id IS NOT NULL;
CREATE INDEX trafego_vinculo_anterior_ix   ON public.trafego_vinculo (vinculo_anterior)
  WHERE vinculo_anterior IS NOT NULL;

COMMENT ON TABLE  public.trafego_vinculo IS
  'Vinculo campanha <-> funil (ADR-09): exige confirmacao humana registrada, e reversivel por desfazer, e nunca apagado.';
COMMENT ON COLUMN public.trafego_vinculo.confirmado_por IS
  'Quem confirmou. NOT NULL e nao-vazio: vinculo sem confirmacao humana nao existe.';


-- -----------------------------------------------------------------------------
-- 9. Gatilho do vinculo — desfazer e a UNICA mutacao; apagar nao existe
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trafego_vinculo_so_desfaz()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION
      'trafego_vinculo: DELETE recusado. Reverter um vinculo e preencher desfeito_por/desfeito_em — apagar destroi a trilha que torna o erro corrigivel.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.vinculo_id       IS DISTINCT FROM OLD.vinculo_id
     OR NEW.volc_campaign_id IS DISTINCT FROM OLD.volc_campaign_id
     OR NEW.opportunity_id   IS DISTINCT FROM OLD.opportunity_id
     OR NEW.project_id       IS DISTINCT FROM OLD.project_id
     OR NEW.funnel_run_id    IS DISTINCT FROM OLD.funnel_run_id
     OR NEW.regra            IS DISTINCT FROM OLD.regra
     OR NEW.evidencia        IS DISTINCT FROM OLD.evidencia
     OR NEW.confirmado_por   IS DISTINCT FROM OLD.confirmado_por
     OR NEW.confirmado_em    IS DISTINCT FROM OLD.confirmado_em
     OR NEW.vinculo_anterior IS DISTINCT FROM OLD.vinculo_anterior
  THEN
    RAISE EXCEPTION
      'trafego_vinculo: a decisao confirmada e imutavel. Para corrigir, desfaca este vinculo e crie outro apontando para ele em vinculo_anterior.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- Desfazer e irreversivel como EVENTO: o vinculo pode ser refeito, mas por
  -- uma linha NOVA. Deixar `desfeito_em` voltar a NULL apagaria a informacao de
  -- que alguem, um dia, desconfiou dele.
  IF OLD.desfeito_em IS NOT NULL
     AND (NEW.desfeito_em     IS DISTINCT FROM OLD.desfeito_em
       OR NEW.desfeito_por    IS DISTINCT FROM OLD.desfeito_por
       OR NEW.desfeito_motivo IS DISTINCT FROM OLD.desfeito_motivo)
  THEN
    RAISE EXCEPTION
      'trafego_vinculo: este vinculo ja foi desfeito em % por %; o registro do desfazer nao se reescreve.',
      OLD.desfeito_em, OLD.desfeito_por
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_vinculo_so_desfaz
  BEFORE UPDATE OR DELETE ON public.trafego_vinculo
  FOR EACH ROW EXECUTE FUNCTION public.trafego_vinculo_so_desfaz();

COMMENT ON FUNCTION public.trafego_vinculo_so_desfaz() IS
  'Recusa DELETE e qualquer UPDATE que nao seja o preenchimento unico dos campos de desfazer.';


-- -----------------------------------------------------------------------------
-- 10. trafego_evento — append-only
-- -----------------------------------------------------------------------------
-- O P0 entrega o evento operacional e nada alem dele (ADR-14). Ele existe para
-- uma coisa: que uma falha NAO SE PERCA. Hoje falha de persistencia vira aviso
-- no corpo de uma resposta HTTP, exibido uma vez e nunca guardado.
--
-- `chave_de_agrupamento` e OPACA de proposito. Nenhuma CHECK interpreta o seu
-- formato, nenhum indice depende do seu significado. O risco registrado e que
-- uma chave mal escolhida no P0 contamine a agregacao do P1; o antidoto e o
-- banco nao ter opiniao sobre ela.
--
-- `volc_campaign_id` NAO tem FK, e essa e a decisao mais importante da tabela:
-- o caso que motivou o evento e justamente aquele em que a campanha NAO foi
-- persistida. Uma FK faria o registro da falha falhar pela mesma razao que a
-- linha falhou — perdendo exatamente o que se queria guardar.
CREATE TABLE public.trafego_evento (
  evento_id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Quando aconteceu, e quando conseguimos gravar. Sao coisas diferentes quando
  -- o registro e feito por um reprocessamento.
  ocorrido_em           timestamptz NOT NULL DEFAULT now(),
  registrado_em         timestamptz NOT NULL DEFAULT now(),

  tipo                  text        NOT NULL,
  chave_de_agrupamento  text        NOT NULL,
  produtor              text        NOT NULL,

  sujeito_tipo          text,
  sujeito_id            text,
  customer_id           text,
  volc_campaign_id      text,

  carga                 jsonb       NOT NULL DEFAULT '{}'::jsonb,

  CONSTRAINT trafego_evento_tipo_nao_vazio
    CHECK (btrim(tipo) <> ''),
  CONSTRAINT trafego_evento_chave_nao_vazia
    CHECK (btrim(chave_de_agrupamento) <> ''),
  CONSTRAINT trafego_evento_produtor_nao_vazio
    CHECK (btrim(produtor) <> ''),
  CONSTRAINT trafego_evento_sujeito_conhecido
    CHECK (sujeito_tipo IS NULL OR sujeito_tipo IN
      ('campanha', 'conta', 'linhagem', 'vinculo', 'sistema')),
  CONSTRAINT trafego_evento_customer_id_valido
    CHECK (customer_id IS NULL OR customer_id ~ '^[0-9]{6,12}$')
);

CREATE INDEX trafego_evento_chave_ix
  ON public.trafego_evento (chave_de_agrupamento, ocorrido_em DESC);
CREATE INDEX trafego_evento_ocorrido_ix
  ON public.trafego_evento (ocorrido_em DESC);
CREATE INDEX trafego_evento_campanha_ix
  ON public.trafego_evento (volc_campaign_id, ocorrido_em DESC)
  WHERE volc_campaign_id IS NOT NULL;
CREATE INDEX trafego_evento_conta_ix
  ON public.trafego_evento (customer_id, ocorrido_em DESC)
  WHERE customer_id IS NOT NULL;

COMMENT ON TABLE  public.trafego_evento IS
  'Registro append-only do que aconteceu (ADR-14). UPDATE e DELETE sao recusados por gatilho.';
COMMENT ON COLUMN public.trafego_evento.chave_de_agrupamento IS
  'Opaca. O banco nao a interpreta, para que a agregacao do P1 nao herde uma semantica escolhida cedo demais.';
COMMENT ON COLUMN public.trafego_evento.volc_campaign_id IS
  'Sem FK de proposito: o evento tem de conseguir descrever uma campanha que NAO foi persistida.';

CREATE OR REPLACE FUNCTION public.trafego_evento_append_only()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  RAISE EXCEPTION
    'trafego_evento e append-only: % recusado. O que aconteceu nao deixa de ter acontecido; corrija com um evento novo.',
    TG_OP
    USING ERRCODE = 'restrict_violation';
END
$funcao$;

CREATE TRIGGER trafego_evento_append_only
  BEFORE UPDATE OR DELETE ON public.trafego_evento
  FOR EACH ROW EXECUTE FUNCTION public.trafego_evento_append_only();

COMMENT ON FUNCTION public.trafego_evento_append_only() IS
  'Recusa UPDATE e DELETE em trafego_evento.';


-- -----------------------------------------------------------------------------
-- 11. Diario da varredura — cada tentativa vira evento, por construcao
-- -----------------------------------------------------------------------------
-- `trafego_snapshot_conta` guarda o ESTADO corrente de cada conta; este gatilho
-- e o que faz o HISTORICO de cada tentativa existir, sem depender de o
-- sincronizador lembrar de registra-lo.
--
-- ⚠️ Um gatilho que escreve merece justificativa, porque foi um gatilho que
-- criou o defeito de ADR-10. A diferenca e de natureza: aquele SOBRESCREVIA uma
-- declaracao da aplicacao (`status_source`), tornando-a inalcancavel. Este nao
-- toca em nada — ele APENDA uma linha num diario que ninguem le como verdade de
-- dominio. Nao deriva, nao decide, nao reescreve.
CREATE OR REPLACE FUNCTION public.trafego_snapshot_registra_tentativa()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  INSERT INTO public.trafego_evento (
    ocorrido_em, tipo, chave_de_agrupamento, produtor,
    sujeito_tipo, sujeito_id, customer_id, carga
  ) VALUES (
    NEW.tentativa_em,
    'sincronizacao.conta.' || NEW.tentativa_resultado,
    'sincronizacao.conta:' || NEW.customer_id,
    'banco:trafego_snapshot_registra_tentativa',
    'conta',
    NEW.customer_id,
    NEW.customer_id,
    jsonb_strip_nulls(jsonb_build_object(
      'resultado',              NEW.tentativa_resultado,
      'motivo',                 NEW.tentativa_motivo,
      'duracao_ms',             NEW.tentativa_duracao_ms,
      'leitura_boa_em',         NEW.leitura_boa_em,
      'leitura_boa_campanhas',  NEW.leitura_boa_campanhas
    ))
  );
  RETURN NULL;
END
$funcao$;

CREATE TRIGGER trafego_snapshot_registra_tentativa
  AFTER INSERT OR UPDATE ON public.trafego_snapshot_conta
  FOR EACH ROW EXECUTE FUNCTION public.trafego_snapshot_registra_tentativa();

COMMENT ON FUNCTION public.trafego_snapshot_registra_tentativa() IS
  'Apenda um evento por tentativa de leitura de conta. Nao deriva nem sobrescreve nada — ao contrario do gatilho de E-08.';


-- -----------------------------------------------------------------------------
-- 12. PROJECOES DE LEITURA — o inventario montado NO BANCO
-- -----------------------------------------------------------------------------
-- Duas views, e as duas existem por motivos operacionais medidos.
--
-- POR QUE VIEW, E NAO JOIN NO CLIENTE
-- A identidade (`trafego_campanha`), o espelho (`trafego_campanha_espelho`), o
-- vinculo ativo (`trafego_vinculo`) e o frescor da conta
-- (`trafego_snapshot_conta`) sao QUATRO tabelas, e a listagem precisa das
-- quatro na mesma linha. Montado no cliente, isso vira uma consulta por
-- campanha — o N+1 — e o pior dele nao e a lentidao: e que o N+1 SOME DO PLANO
-- DE CONSULTA. `EXPLAIN` na consulta principal mostra um plano barato e
-- honesto, e as outras 50 requisicoes nao aparecem em lugar nenhum.
--
-- POR QUE `security_invoker = true`
-- Uma view roda com os privilegios do DONO por padrao. Uma view de postgres
-- sobre estas seis tabelas seria um tunel: quem tivesse SELECT nela leria tudo,
-- por cima da RLS que a secao 13 liga. Com `security_invoker`, a view exige do
-- CHAMADOR o mesmo que a tabela exigiria — anon continua lendo zero linha,
-- mesmo que um GRANT reapareca por engano. E o motivo de a guarda desta
-- migration exigir PostgreSQL 15.
--
-- ⚠️ NENHUMA DAS DUAS DECIDE NADA. Elas juntam e renomeiam. A unica coisa
-- calculada e o booleano `atencao`, e ele e a TRADUCAO LITERAL de
-- `dominio.pede_atencao()` — ver o comentario dele abaixo.

CREATE VIEW public.trafego_inventario_conta
  WITH (security_invoker = true) AS
SELECT
  s.customer_id,
  s.nome,
  s.tentativa_em,
  s.tentativa_resultado,
  s.tentativa_motivo,
  s.tentativa_duracao_ms,
  -- O nome que a projecao le. A tabela chama de `tentativa_escopo` porque ali o
  -- prefixo agrupa os campos da tentativa; a projecao chama de `escopo_parcial`
  -- porque e o que ela mostra em `faltou[].escopo`. Renomear na view custa zero
  -- e evita um mapa de apelidos em Python, que e onde eles apodrecem.
  s.tentativa_escopo AS escopo_parcial,
  s.leitura_boa_em,
  s.leitura_boa_campanhas,
  s.leitura_boa_duracao_ms,
  -- DERIVADO, e nao coluna, de proposito: `vazio_confirmado` e "a leitura foi
  -- boa e nao havia nada". Guardar isso numa coluna criaria uma segunda fonte
  -- da mesma verdade, que pode divergir de `leitura_boa_campanhas` e nunca mais
  -- concordar. `coalesce(..., false)` porque contagem NULA e "nao sei", e nao
  -- sei nao e vazio confirmado — e o `nunca_lido` que a projecao devolve.
  coalesce(s.tentativa_resultado = 'ok' AND s.leitura_boa_campanhas = 0, false)
    AS vazio_confirmado,
  s.atualizado_em
FROM public.trafego_snapshot_conta s;

COMMENT ON VIEW public.trafego_inventario_conta IS
  'O snapshot da conta no vocabulario que a projecao le. Ausencia de linha continua significando "nunca lido" — a view nao inventa linha para conta que nunca foi varrida.';


CREATE VIEW public.trafego_inventario_campanha
  WITH (security_invoker = true) AS
SELECT
  base.*,

  -- ATENCAO — a MESMA regra de `backend/app/trafego/dominio.py:pede_atencao()`,
  -- termo por termo e na mesma ordem. Ela e calculada aqui porque o filtro
  -- `?atencao=true` e a contagem do sino precisam resolver NO BANCO: filtrar em
  -- Python faria a paginacao mentir (o limite corta ANTES do filtro) e faria o
  -- sino contar so a pagina corrente.
  --
  -- ⚠️ DUAS DEFINICOES DE `atencao` E O DEFEITO, NAO A SOLUCAO. Se esta
  -- expressao e `pede_atencao()` discordarem, o sino e a aba mostram numeros
  -- diferentes para a mesma pergunta e nao ha como saber qual esta certo.
  -- `backend/tests/test_trafego_persistencia.py` compara as duas linha a linha
  -- contra um banco de verdade; mudar uma sem a outra derruba o teste.
  --
  -- CADA TERMO E UM FATO OBSERVADO:
  --
  --  1. `tentativa_resultado = 'falhou'` — a ultima tentativa de ler a conta
  --     nao voltou. Nao sabemos NADA sobre esta campanha agora, e nao saber e
  --     motivo para olhar. E o E-07: tres contas falhando era visualmente
  --     identico a "tudo bem".
  --  2. `presenca IS NOT NULL` — o espelho registrou uma ressalva (um dos seis
  --     estados). NULO aqui e "presente, sem ressalva" e nao pede nada.
  --  3. ligada e `entrega_lida_em IS NULL` — "esta gastando e nao sei quanto".
  --  4. ligada e `impressoes = 0` / `cliques = 0` — sintoma MEDIDO. Repare em
  --     `impressoes IS NULL` devolvendo `false` na linha anterior: "nao consegui
  --     medir" NAO e "medi e deu zero", e o ramo (3) ja cobriu o primeiro.
  --
  -- O QUE FICA DE FORA, E POR QUE — as duas sao fato observado e mesmo assim
  -- nao entram, entao viajam como COLUNA PROPRIA (`procedencia_desconhecida`,
  -- `sem_vinculo`) para que um filtro futuro as alcance sem passar pelo sino:
  --
  --   · `procedencia = 'desconhecida'` e o estado de TODA campanha que a
  --     varredura descobre — a varredura nao tem como saber quem a criou.
  --     No sino, ela marcaria o inventario inteiro no primeiro dia.
  --   · vinculo ausente e o estado normal de quase tudo: vincular e uma decisao
  --     humana, uma a uma. Marcar tudo enche a aba de linhas CORRETAS, o
  --     operador para de olhar, e o alerta morre — que e o unico jeito de um
  --     alerta falhar de vez.
  CASE
    WHEN base.tentativa_resultado = 'falhou'                          THEN true
    WHEN base.presenca IS NOT NULL                                    THEN true
    WHEN upper(btrim(coalesce(base.estado_externo, ''))) <> 'ENABLED' THEN false
    WHEN base.entrega_lida_em IS NULL                                 THEN true
    WHEN base.impressoes IS NULL                                      THEN false
    WHEN base.impressoes = 0                                          THEN true
    WHEN base.cliques = 0                                             THEN true
    ELSE false
  END AS atencao

FROM (
  SELECT
    c.volc_campaign_id,
    c.campaign_lineage_id,
    c.customer_id,
    c.campaign_id,
    c.procedencia,
    c.criada_em,
    c.criada_por,

    -- PRESENCA — o unico lugar da view onde um valor e substituido, e a troca e
    -- por um termo FORA das seis, nao por um dos seis.
    --
    -- Sem linha no espelho, esta campanha NUNCA foi lida. Deixar `presenca`
    -- nula aqui faria `presenca_projetada()` responder `presente` — afirmando
    -- que a conta respondeu e a campanha estava la, o que ninguem observou.
    -- Escolher um dos seis seria pior: `nao_encontrada` afirma ausencia,
    -- `sincronizacao_falhou` afirma falha, e nenhuma das duas aconteceu.
    --
    -- `nao_espelhada` esta deliberadamente FORA do vocabulario: a propria
    -- `presenca_projetada()` manda valor desconhecido para
    -- `conta_nao_identificada`, que e a afirmacao mais fraca disponivel. A
    -- degradacao e automatica e segura, e nenhum termo novo entrou no contrato.
    -- A CHECK do espelho NAO o aceita — ele nunca pode ser gravado, so
    -- projetado.
    CASE WHEN e.volc_campaign_id IS NULL THEN 'nao_espelhada' ELSE e.presenca END
      AS presenca,

    e.lido_em,
    e.nome,
    e.estado_externo,
    e.veiculacao,
    e.canal,
    e.estrategia,
    e.url_final,
    e.canal_bruto,
    e.estrategia_bruta,
    e.lance_micros,
    e.verba_diaria_micros,
    e.impressoes,
    e.cliques,
    e.custo_micros,
    e.moeda,
    e.entrega_lida_em,

    v.vinculo_id,
    v.opportunity_id,
    v.project_id,
    v.funnel_run_id,
    v.regra              AS vinculo_regra,
    v.confirmado_por     AS vinculo_confirmado_por,
    v.confirmado_em      AS vinculo_confirmado_em,

    s.tentativa_em,
    s.tentativa_resultado,
    s.leitura_boa_em,

    -- Fatos que NAO entram em `atencao` (ver acima), mas que precisam ser
    -- filtraveis: sem coluna, filtrar por eles voltaria a ser trabalho de
    -- Python depois da paginacao — e a paginacao passaria a mentir de novo.
    (c.procedencia = 'desconhecida') AS procedencia_desconhecida,
    (v.vinculo_id IS NULL)           AS sem_vinculo

  FROM public.trafego_campanha c

  -- LEFT: identidade sem espelho e um estado real — a porta de criacao declara
  -- a campanha antes de a primeira varredura passar. INNER a esconderia da tela
  -- exatamente na janela em que o operador acabou de cria-la.
  LEFT JOIN public.trafego_campanha_espelho e
         ON e.volc_campaign_id = c.volc_campaign_id

  -- No maximo UMA linha por campanha: `trafego_vinculo_ativo_por_campanha_ux` e
  -- unico sobre `volc_campaign_id WHERE desfeito_em IS NULL`. Sem esse indice
  -- este LEFT JOIN multiplicaria linhas e a contagem do sino passaria a somar a
  -- mesma campanha duas vezes.
  LEFT JOIN public.trafego_vinculo v
         ON v.volc_campaign_id = c.volc_campaign_id
        AND v.desfeito_em IS NULL

  -- O frescor da CONTA na linha da CAMPANHA. E o que permite ao termo (1) de
  -- `atencao` existir sem uma segunda consulta.
  LEFT JOIN public.trafego_snapshot_conta s
         ON s.customer_id = c.customer_id
) AS base;

COMMENT ON VIEW public.trafego_inventario_campanha IS
  'Identidade + espelho + vinculo ativo + frescor da conta, com `atencao` traduzido de dominio.pede_atencao(). Nao decide nada alem disso.';


-- -----------------------------------------------------------------------------
-- 13. SEGURANCA — REVOKE nominal, RLS forcada, grants minimos
-- -----------------------------------------------------------------------------
-- Ordem importa: REVOKE primeiro (as tabelas ja nasceram abertas pelo default
-- ACL do achado H), RLS depois, GRANT minimo por ultimo.
DO $seguranca$
DECLARE
  t text;
  f text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'trafego_linhagem', 'trafego_campanha', 'trafego_campanha_espelho',
    'trafego_snapshot_conta', 'trafego_vinculo', 'trafego_evento'
  ] LOOP
    -- 1) Nominal. `FROM PUBLIC` sozinho NAO remove grant nominal, e o default
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
  END LOOP;

  -- 3) Minimo, explicito e so para service_role — o unico papel que o backend
  --    usa. DELETE nao aparece em lugar nenhum: nao ha caminho de apagamento
  --    no dominio, e nao conceder e mais forte que confiar no gatilho.
  --    TRUNCATE, REFERENCES e TRIGGER tambem ficam de fora.
  EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE public.trafego_linhagem          TO service_role';
  EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE public.trafego_campanha          TO service_role';
  EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE public.trafego_campanha_espelho  TO service_role';
  EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE public.trafego_snapshot_conta    TO service_role';
  EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE public.trafego_vinculo           TO service_role';
  -- Evento e append-only: nem UPDATE ele recebe. O gatilho ja recusaria, mas
  -- duas travas independentes e o ponto — grant errado numa e gatilho na outra.
  EXECUTE 'GRANT SELECT, INSERT             ON TABLE public.trafego_evento        TO service_role';

  -- 3b) AS VIEWS DA SECAO 12 ENTRAM NA MESMA CONTENCAO. Elas nascem com o mesmo
  --     default ACL quebrado das tabelas — `ALTER DEFAULT PRIVILEGES ... ON
  --     TABLES` alcanca VIEW tambem, e uma view aberta e um tunel para as seis
  --     tabelas que acabaram de ser fechadas.
  --
  --     RLS nao se liga em view; a contencao delas e outra e esta em duas
  --     camadas: o REVOKE nominal (ninguem alem de service_role chega nelas) e o
  --     `security_invoker = true` (mesmo quem chegar precisa passar pela RLS das
  --     tabelas de baixo, como se estivesse consultando as tabelas).
  --
  --     So SELECT: escrita vai nas tabelas, sempre. Uma view atualizavel aqui
  --     seria uma segunda porta de escrita, com outras regras.
  FOREACH t IN ARRAY ARRAY[
    'trafego_inventario_conta', 'trafego_inventario_campanha'
  ] LOOP
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM service_role', t);
    EXECUTE format('GRANT SELECT ON TABLE public.%I TO service_role', t);
  END LOOP;

  -- 4) As funcoes tambem nascem com EXECUTE para anon (achado H, tipo 'f').
  --    Funcao de gatilho nao e chamavel por RPC, mas deixa-la executavel por
  --    anon e superficie gratuita — e a superficie de RPC deste banco ja e a
  --    mais larga que sobrou.
  FOREACH f IN ARRAY ARRAY[
    'trafego_campanha_identidade_imutavel', 'trafego_espelho_preserva_ultima_boa',
    'trafego_snapshot_preserva_ultima_boa', 'trafego_vinculo_so_desfaz',
    'trafego_evento_append_only', 'trafego_snapshot_registra_tentativa'
  ] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I() FROM PUBLIC', f);
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I() FROM anon', f);
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I() FROM authenticated', f);
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I() FROM service_role', f);
  END LOOP;

  RAISE NOTICE 'v9_01: 6 tabelas com RLS forcada + 2 views security_invoker, zero policies, anon/authenticated revogados nominalmente';
END
$seguranca$;


-- -----------------------------------------------------------------------------
-- 14. VERIFICACAO NA PROPRIA TRANSACAO — se algo escapou, nada e aplicado
-- -----------------------------------------------------------------------------
-- Uma migration de seguranca que "roda com sucesso" e deixa uma tabela aberta e
-- pior que uma que falha, porque ela produz um relatorio verde.
DO $verifica$
DECLARE
  abertas     text;
  sem_rls     text;
  com_policy  text;
  sem_invoker text;
BEGIN
  -- `relkind IN ('r','v')`: a view entra na mesma conferencia. Enquanto ela
  -- estava fora, uma view aberta passava neste bloco sem ser vista — e ela le
  -- as seis tabelas.
  SELECT string_agg(DISTINCT c.relname, ', ') INTO abertas
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public'
     AND c.relname LIKE 'trafego\_%'
     AND c.relkind IN ('r', 'v')
     AND (
       has_table_privilege('anon',          c.oid, 'SELECT, INSERT, UPDATE, DELETE')
       OR has_table_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, DELETE')
     );
  IF abertas IS NOT NULL THEN
    RAISE EXCEPTION 'v9_01: anon/authenticated ainda alcancam: %', abertas;
  END IF;

  -- `security_invoker` e a unica coisa que impede a view de ser um tunel por
  -- cima da RLS. Sem esta conferencia, um `CREATE OR REPLACE VIEW` futuro que
  -- esquecesse a opcao abriria as seis tabelas em silencio, e a migration
  -- continuaria "verde".
  SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO sem_invoker
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public'
     AND c.relname LIKE 'trafego\_%'
     AND c.relkind = 'v'
     AND NOT coalesce(
       (SELECT option_value = 'true'
          FROM pg_options_to_table(c.reloptions)
         WHERE option_name = 'security_invoker'), false);
  IF sem_invoker IS NOT NULL THEN
    RAISE EXCEPTION
      'v9_01: view sem security_invoker: % — ela leria as seis tabelas com os privilegios do dono',
      sem_invoker;
  END IF;

  SELECT string_agg(c.relname, ', ') INTO sem_rls
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public'
     AND c.relname LIKE 'trafego\_%'
     AND c.relkind = 'r'
     AND NOT (c.relrowsecurity AND c.relforcerowsecurity);
  IF sem_rls IS NOT NULL THEN
    RAISE EXCEPTION 'v9_01: RLS nao esta ligada+forcada em: %', sem_rls;
  END IF;

  SELECT string_agg(tablename, ', ') INTO com_policy
    FROM pg_policies
   WHERE schemaname = 'public' AND tablename LIKE 'trafego\_%';
  IF com_policy IS NOT NULL THEN
    RAISE EXCEPTION
      'v9_01: policy inesperada em % — a negacao aqui e por AUSENCIA de policy', com_policy;
  END IF;

  IF has_table_privilege('service_role', 'public.trafego_evento', 'UPDATE')
     OR has_table_privilege('service_role', 'public.trafego_evento', 'DELETE') THEN
    RAISE EXCEPTION 'v9_01: trafego_evento nao pode ter UPDATE/DELETE para service_role';
  END IF;

  IF to_regclass('public.trafego_inventario_campanha') IS NULL
     OR to_regclass('public.trafego_inventario_conta') IS NULL THEN
    RAISE EXCEPTION 'v9_01: as projecoes de leitura da secao 12 nao foram criadas';
  END IF;

  RAISE NOTICE 'v9_01: verificacao interna passou';
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
-- SELECT tgname, tgrelid::regclass, tgenabled
--   FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE 'trafego\_%' ORDER BY 2, 1;
