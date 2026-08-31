-- =============================================================================
-- v10_03 — a fronteira atomica do lancamento: uma chamada, uma transacao
-- =============================================================================
--
-- ## O defeito que esta migration existe para fechar
--
-- A v10_01 escreveu tres camadas de defesa contra "timeout mas criou". Todas as
-- tres vivem dentro de `IF NEW.estado IS DISTINCT FROM OLD.estado`, no gatilho
-- `trafego_item_estado_valido`. Elas guardam `-> falhou` e
-- `indeterminado -> criando`.
--
-- ABRIR UM RECIBO NAO PASSA POR GATILHO NENHUM — e abrir o recibo e o ato que
-- precede a chamada a plataforma. Reproduzido em cluster descartavel, com a
-- v9_01..v9_04 + v10_01 + v10_02 aplicadas:
--
--     item em `criando`, recibo tentativa=1 `em_voo` (a chamada 1 nao respondeu)
--     INSERT trafego_recibo tentativa=2 'em_voo'  -> ACEITO
--     recibos em voo simultaneos para o mesmo item: 2
--
-- Duas chamadas de criacao podem estar em voo para o MESMO plano, na MESMA
-- conta. E o indice `trafego_recibo_sucesso_unico_ux` so impede registrar dois
-- SUCESSOS: se as duas criarem, a segunda campanha existe na conta e fica
-- invisivel para o sistema, disputando o mesmo leilao que a primeira. O dano
-- nao e duplicar; e duplicar e perder o rastro da duplicata.
--
-- ## Por que uma funcao, e nao disciplina de chamador
--
-- Sobre PostgREST cada requisicao HTTP e uma transacao propria. "Conferir se ha
-- recibo em aberto" e "abrir o recibo novo" em duas requisicoes deixam uma
-- janela em que nenhum dos dois processos ve a intencao do outro. Nenhuma
-- disciplina de chamador fecha essa janela, porque a janela nao esta no
-- chamador. Ela esta entre as transacoes.
--
-- As funcoes abaixo travam o item (`FOR UPDATE`), conferem e escrevem no mesmo
-- `BEGIN/COMMIT`. A janela deixa de existir.
--
-- ## O que esta migration NAO faz, de proposito
--
-- · NAO afrouxa nenhuma guarda da v10_01. O gatilho novo do recibo e uma quarta
--   camada, independente; `CREATE OR REPLACE` em funcao da v10_01 tornaria o
--   rollback dependente de redigitar o corpo antigo — o defeito que o README
--   registra sobre a v9_03.
-- · NAO reabre reenvio depois de `sem_resposta`. Um recibo `sem_resposta` e
--   permanente e a camada 3 da v10_01 conta esses recibos, entao o item nao
--   volta para `criando`. Isso e fail-closed e continua assim: reconciliar e o
--   caminho, reenviar nao e. Afrouxar essa regra e decisao do dono, nao de uma
--   migration.
-- · NAO ativa campanha, NAO cria agenda, NAO fala com plataforma nenhuma.
--
-- ## Dependencia e reversao
--
-- Depende de v9_01 (trafego_campanha) e v10_01. Nao toca a v10_02.
-- Reversao completa em `v10_03_rollback.sql`, que derruba somente o que esta
-- arquivo cria — as dez tabelas da v10_01 continuam de pe.
-- =============================================================================

BEGIN;

DO $guarda$
DECLARE
  faltando  text;
  ja_existe text;
BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'v10_03 exige PostgreSQL 15 ou maior; aqui: %',
      current_setting('server_version');
  END IF;

  IF to_regclass('public.trafego_lote_item') IS NULL
     OR to_regclass('public.trafego_recibo') IS NULL THEN
    RAISE EXCEPTION
      'v10_03 abortada: a v10_01 nao esta aplicada. Esta migration guarda a fronteira que ela desenhou.';
  END IF;

  IF to_regclass('public.trafego_campanha') IS NULL THEN
    RAISE EXCEPTION
      'v10_03 abortada: a v9_01 nao esta aplicada. O sucesso do lancamento grava a identidade da instancia.';
  END IF;

  SELECT string_agg(p, ', ' ORDER BY p) INTO ja_existe
    FROM unnest(ARRAY[
      'trafego_ledger_abrir_lancamento', 'trafego_ledger_despachar',
      'trafego_ledger_fechar', 'trafego_ledger_reconciliar'
    ]) AS p
   WHERE EXISTS (SELECT 1 FROM pg_proc pr JOIN pg_namespace n ON n.oid = pr.pronamespace
                  WHERE n.nspname = 'public' AND pr.proname = p);
  IF ja_existe IS NOT NULL THEN
    RAISE EXCEPTION
      'v10_03 ja parece aplicada: % ja existe(m). Rode v10_03_rollback.sql antes de reaplicar.', ja_existe;
  END IF;

  SELECT string_agg(r, ', ' ORDER BY r) INTO faltando
    FROM unnest(ARRAY['anon', 'authenticated', 'service_role']) AS r
   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION
      'v10_03 exige os papeis do Supabase; ausente(s): %. Sem eles o REVOKE nominal nao acontece e a funcao nasce chamavel por qualquer um.',
      faltando;
  END IF;

  RAISE NOTICE 'v10_03: guardas ok (papel=%, versao=%)',
    current_user, current_setting('server_version');
END
$guarda$;


-- -----------------------------------------------------------------------------
-- 1. A aprovacao humana passa a ter identidade e a apontar para UM plano
-- -----------------------------------------------------------------------------
-- A v10_01 guarda a aprovacao no LOTE (`aprovado_por`, `aprovado_em`), o que
-- responde "alguem aprovou este lote?". Nao responde "alguem aprovou ESTE
-- plano?" — e essa e a pergunta que impede reaproveitar uma autorizacao para
-- outro payload depois de uma autocorrecao.
--
-- `plano_impressao` e a impressao das OPERACOES efetivas (o selo que o
-- `/provar` emite depois de qualquer adaptacao), nao do pedido cru. O pedido
-- cru serve para reconstruir; nunca autoriza.
--
-- `aprovado_por_sub` e a identidade estavel do operador. E-mail muda; o sub do
-- provedor de identidade e o que permite dizer "foi a mesma pessoa" um ano
-- depois.
ALTER TABLE public.trafego_lote_item
  ADD COLUMN plano_impressao     text,
  ADD COLUMN aprovado_por        text,
  ADD COLUMN aprovado_por_sub    text,
  ADD COLUMN aprovado_em         timestamptz,
  ADD COLUMN aprovacao_impressao text;

ALTER TABLE public.trafego_lote_item
  ADD CONSTRAINT trafego_item_plano_impressao_sha256
    CHECK (plano_impressao IS NULL OR plano_impressao ~ '^[0-9a-f]{64}$'),
  ADD CONSTRAINT trafego_item_aprovacao_impressao_sha256
    CHECK (aprovacao_impressao IS NULL OR aprovacao_impressao ~ '^[0-9a-f]{64}$'),

  -- A aprovacao e indivisivel: quem, quando e o que. Metade de uma aprovacao
  -- nao e uma aprovacao fraca — e uma linha que nao sabe o que autorizou.
  ADD CONSTRAINT trafego_item_aprovacao_indivisivel
    CHECK (
      (aprovado_por IS NULL AND aprovado_por_sub IS NULL
       AND aprovado_em IS NULL AND aprovacao_impressao IS NULL)
      OR
      (btrim(coalesce(aprovado_por, '')) <> ''
       AND btrim(coalesce(aprovado_por_sub, '')) <> ''
       AND aprovado_em IS NOT NULL
       AND aprovacao_impressao IS NOT NULL)
    ),

  -- ⚠️ A TRAVA. Uma autorizacao so vale para o plano que ela viu.
  ADD CONSTRAINT trafego_item_aprovacao_vinculada_ao_plano
    CHECK (aprovacao_impressao IS NULL
           OR (plano_impressao IS NOT NULL AND aprovacao_impressao = plano_impressao));

COMMENT ON COLUMN public.trafego_lote_item.plano_impressao IS
  'sha256 das operacoes efetivas provadas. Identidade do que foi revisado, nao do pedido cru.';
COMMENT ON COLUMN public.trafego_lote_item.aprovacao_impressao IS
  'A impressao que o humano de fato aprovou. Igual a plano_impressao por constraint: autorizacao nao migra de plano.';


-- -----------------------------------------------------------------------------
-- 2. CAMADA 4 — a guarda que faltava, no ato que precede a rede
-- -----------------------------------------------------------------------------
-- As camadas 2 e 3 da v10_01 guardam transicoes de estado do ITEM. Esta guarda
-- o RECIBO, que e o objeto que representa "uma chamada esta saindo agora".
--
-- Regra: nao se abre um recibo para um item que ja tem recibo sem desfecho na
-- mesma operacao. `em_voo` e `sem_resposta` significam a mesma coisa aqui — nao
-- sabemos se a chamada anterior criou. Abrir o segundo e apostar.
--
-- A guarda vale mesmo quando NENHUMA transicao de estado acontece, que e
-- exatamente o caso que passava: item ja em `criando`, processo morre no meio
-- da chamada, retomada abre outro recibo sem mexer no item.
CREATE OR REPLACE FUNCTION public.trafego_recibo_um_voo_por_item()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $funcao$
DECLARE
  abertos integer;
  detalhe text;
BEGIN
  SELECT count(*), string_agg(r.tentativa || ':' || r.desfecho, ', ' ORDER BY r.tentativa)
    INTO abertos, detalhe
    FROM public.trafego_recibo r
   WHERE r.item_id  = NEW.item_id
     AND r.operacao = NEW.operacao
     AND r.desfecho IN ('em_voo', 'sem_resposta');

  IF abertos > 0 THEN
    RAISE EXCEPTION
      'trafego_recibo: o item % ja tem % recibo(s) sem desfecho na operacao % (%). Abrir outro e mandar uma segunda chamada enquanto a primeira pode estar a caminho — e as duas criariam campanhas concorrentes na mesma conta. Verifique na conta e reconcilie o recibo aberto.',
      NEW.item_id, abertos, NEW.operacao, detalhe
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_recibo_um_voo_por_item
  BEFORE INSERT ON public.trafego_recibo
  FOR EACH ROW EXECUTE FUNCTION public.trafego_recibo_um_voo_por_item();


-- -----------------------------------------------------------------------------
-- 3. Entrar em `criando` exige aprovacao vinculada — e ela nao se reescreve
-- -----------------------------------------------------------------------------
-- Gatilho separado, de proposito: substituir `trafego_item_estado_valido` faria
-- o rollback ter de redigitar o corpo da v10_01, e um rollback que reescreve
-- regra apaga tanto quanto a migration que ele desfaz.
CREATE OR REPLACE FUNCTION public.trafego_item_aprovacao_vinculada()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $funcao$
BEGIN
  -- O plano e a aprovacao sao a memoria do que foi revisado. Depois de escritos
  -- uma vez, mudar qualquer um faria o recibo descrever outra coisa.
  IF OLD.plano_impressao IS NOT NULL
     AND NEW.plano_impressao IS DISTINCT FROM OLD.plano_impressao THEN
    RAISE EXCEPTION
      'trafego_lote_item: plano_impressao ja registrado (%) e estavel; nao vira %.',
      OLD.plano_impressao, coalesce(NEW.plano_impressao, 'NULL')
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF OLD.aprovado_em IS NOT NULL
     AND (NEW.aprovado_por        IS DISTINCT FROM OLD.aprovado_por
       OR NEW.aprovado_por_sub    IS DISTINCT FROM OLD.aprovado_por_sub
       OR NEW.aprovado_em         IS DISTINCT FROM OLD.aprovado_em
       OR NEW.aprovacao_impressao IS DISTINCT FROM OLD.aprovacao_impressao) THEN
    RAISE EXCEPTION
      'trafego_lote_item: a aprovacao de % em % ja esta registrada. Reescrever uma autorizacao e apagar quem respondeu por ela.',
      OLD.aprovado_por, OLD.aprovado_em
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.estado = 'criando' AND OLD.estado IS DISTINCT FROM 'criando' THEN
    IF NEW.aprovado_em IS NULL THEN
      RAISE EXCEPTION
        'trafego_lote_item: item % entra em `criando` sem aprovacao humana registrada. A chamada sairia sem que ninguem tivesse respondido por ela.',
        NEW.item_id
        USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.plano_impressao IS NULL
       OR NEW.aprovacao_impressao IS DISTINCT FROM NEW.plano_impressao THEN
      RAISE EXCEPTION
        'trafego_lote_item: a aprovacao registrada (%) nao e a deste plano (%). Uma autorizacao nao atravessa de um payload para outro.',
        coalesce(NEW.aprovacao_impressao, 'NULL'), coalesce(NEW.plano_impressao, 'NULL')
        USING ERRCODE = 'restrict_violation';
    END IF;
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_item_aprovacao_vinculada
  BEFORE UPDATE ON public.trafego_lote_item
  FOR EACH ROW EXECUTE FUNCTION public.trafego_item_aprovacao_vinculada();


-- -----------------------------------------------------------------------------
-- 4. trafego_ledger_abrir_lancamento — intencao, blueprint, lote, item, provas
-- -----------------------------------------------------------------------------
-- Tudo o que existe ANTES da autorizacao humana, numa transacao. Reentrar com a
-- mesma chave devolve o que ja existe em vez de criar um segundo caminho; com a
-- mesma chave e plano diferente, RECUSA — a chave e derivada do conteudo, entao
-- chave igual com conteudo diferente significa que alguem derivou errado, e
-- deixar passar seria dar a um plano a idempotencia de outro.
--
-- SECURITY INVOKER de proposito: quem chama e o `service_role`, que ja tem os
-- grants da v10_01. DEFINER transformaria estas funcoes numa escada de
-- privilegio caso o EXECUTE vazasse para `anon` algum dia.
CREATE OR REPLACE FUNCTION public.trafego_ledger_abrir_lancamento(
  p_idempotency_key       text,
  p_plataforma            text,
  p_conta_externa         text,
  p_canal                 text,
  p_objetivo              text,
  p_rotulo                text,
  p_plano                 jsonb,
  p_plano_impressao       text,
  p_declarada_por         text,
  p_declarada_com_base_em text,
  p_blueprint_chave       text,
  p_blueprint_titulo      text,
  p_blueprint_corpo       jsonb,
  p_destino_url           text        DEFAULT NULL,
  p_verba_diaria_teto_micros bigint   DEFAULT NULL,
  p_moeda                 text        DEFAULT NULL,
  p_evidencia             jsonb       DEFAULT '{}'::jsonb,
  p_blueprint_versao      integer     DEFAULT 1,
  p_linhagem_rotulo       text        DEFAULT NULL,
  p_campaign_lineage_id   uuid        DEFAULT NULL,
  p_validacoes            jsonb       DEFAULT '[]'::jsonb,
  p_intencao_id           uuid        DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $funcao$
DECLARE
  v_item        public.trafego_lote_item%ROWTYPE;
  v_lote        public.trafego_lote%ROWTYPE;
  v_linhagem    uuid := p_campaign_lineage_id;
  v_intencao    uuid;
  v_blueprint   uuid;
  v_val         jsonb;
  v_tem_local   boolean := false;
  v_tem_remoto  boolean := false;
BEGIN
  IF p_plano_impressao !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'trafego_ledger_abrir_lancamento: plano_impressao precisa ser um sha256 (64 hex); recebido %.',
      coalesce(p_plano_impressao, 'NULL') USING ERRCODE = 'invalid_parameter_value';
  END IF;

  -- Reentrada: a chave ja existe? Devolve, nao duplica.
  SELECT i.* INTO v_item FROM public.trafego_lote_item i
   WHERE i.idempotency_key = p_idempotency_key FOR UPDATE;

  IF FOUND THEN
    SELECT l.* INTO v_lote FROM public.trafego_lote l WHERE l.lote_id = v_item.lote_id;

    IF v_item.plano_impressao IS DISTINCT FROM p_plano_impressao THEN
      RAISE EXCEPTION
        'trafego_ledger_abrir_lancamento: a chave % ja existe com o plano %, e agora chegou com %. A chave e derivada do conteudo: chave igual com conteudo diferente significa derivacao errada, e deixar passar daria a este plano a idempotencia de outro.',
        p_idempotency_key, v_item.plano_impressao, p_plano_impressao
        USING ERRCODE = 'restrict_violation';
    END IF;

    IF v_lote.conta_externa IS DISTINCT FROM p_conta_externa
       OR v_lote.canal      IS DISTINCT FROM p_canal
       OR v_lote.plataforma IS DISTINCT FROM p_plataforma THEN
      RAISE EXCEPTION
        'trafego_ledger_abrir_lancamento: a chave % pertence a %/%/% e chegou como %/%/%. Uma chave nao atravessa de conta ou canal.',
        p_idempotency_key, v_lote.plataforma, v_lote.conta_externa, v_lote.canal,
        p_plataforma, p_conta_externa, p_canal
        USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN jsonb_build_object(
      'reaproveitado', true,
      'intencao_id',   v_lote.intencao_id,
      'blueprint_id',  v_lote.blueprint_id,
      'lote_id',       v_lote.lote_id,
      'item_id',       v_item.item_id,
      'item_estado',   v_item.estado,
      'lote_estado',   v_lote.estado,
      'tentativas',    v_item.tentativas
    );
  END IF;

  IF v_linhagem IS NULL THEN
    INSERT INTO public.trafego_linhagem (rotulo, declarada_por)
    VALUES (coalesce(nullif(btrim(coalesce(p_linhagem_rotulo, '')), ''), p_rotulo), p_declarada_por)
    RETURNING campaign_lineage_id INTO v_linhagem;
  END IF;

  -- ⚠️ O ID DA INTENCAO PODE VIR DE FORA, E ISSO NAO E DETALHE.
  --
  -- A chave de idempotencia do item e derivada de `intencao_id` (lote.py). Se a
  -- intencao nascesse com `gen_random_uuid()` a cada chamada, a retomada de uma
  -- tentativa perdida produziria uma chave NOVA — e as quatro camadas de defesa
  -- deixariam de reconhecer o que ja foi enviado, que e exatamente o modo de
  -- falha que elas existem para impedir. O chamador deriva o id do conteudo da
  -- intencao (uuid5) e o repassa; duas chamadas iguais recaem na mesma linha.
  IF p_intencao_id IS NOT NULL THEN
    INSERT INTO public.trafego_intencao (
      intencao_id, campaign_lineage_id, plataforma, conta_externa, objetivo, rotulo,
      destino_url, verba_diaria_teto_micros, moeda, declarada_por,
      declarada_com_base_em, evidencia)
    VALUES (
      p_intencao_id, v_linhagem, p_plataforma, p_conta_externa, p_objetivo, p_rotulo,
      p_destino_url, p_verba_diaria_teto_micros, p_moeda, p_declarada_por,
      p_declarada_com_base_em, coalesce(p_evidencia, '{}'::jsonb))
    ON CONFLICT (intencao_id) DO NOTHING;
    v_intencao := p_intencao_id;

    -- Reaproveitar uma intencao exige que ela seja a MESMA intencao. Id igual
    -- com conta ou canal diferentes seria duas autorizacoes de gasto na mesma
    -- linha, e a intencao e imutavel — ninguem corrigiria depois.
    IF NOT EXISTS (
      SELECT 1 FROM public.trafego_intencao i
       WHERE i.intencao_id = p_intencao_id
         AND i.plataforma = p_plataforma AND i.conta_externa = p_conta_externa
    ) THEN
      RAISE EXCEPTION
        'trafego_ledger_abrir_lancamento: a intencao % ja existe declarando outra plataforma/conta. Um id de intencao nao atravessa de conta.',
        p_intencao_id USING ERRCODE = 'restrict_violation';
    END IF;
  ELSE
    INSERT INTO public.trafego_intencao (
      campaign_lineage_id, plataforma, conta_externa, objetivo, rotulo, destino_url,
      verba_diaria_teto_micros, moeda, declarada_por, declarada_com_base_em, evidencia)
    VALUES (
      v_linhagem, p_plataforma, p_conta_externa, p_objetivo, p_rotulo, p_destino_url,
      p_verba_diaria_teto_micros, p_moeda, p_declarada_por, p_declarada_com_base_em,
      coalesce(p_evidencia, '{}'::jsonb))
    RETURNING intencao_id INTO v_intencao;
  END IF;

  SELECT b.blueprint_id INTO v_blueprint FROM public.trafego_blueprint b
   WHERE b.chave = p_blueprint_chave AND b.versao = p_blueprint_versao;
  IF v_blueprint IS NULL THEN
    INSERT INTO public.trafego_blueprint
      (chave, versao, plataforma, canal, titulo, corpo, declarado_por)
    VALUES (p_blueprint_chave, p_blueprint_versao, p_plataforma, p_canal,
            p_blueprint_titulo, coalesce(p_blueprint_corpo, '{}'::jsonb), p_declarada_por)
    RETURNING blueprint_id INTO v_blueprint;
  END IF;

  INSERT INTO public.trafego_lote
    (intencao_id, blueprint_id, plataforma, conta_externa, canal, criado_por)
  VALUES (v_intencao, v_blueprint, p_plataforma, p_conta_externa, p_canal, p_declarada_por)
  RETURNING * INTO v_lote;

  INSERT INTO public.trafego_lote_item
    (lote_id, ordem, idempotency_key, rotulo, plano, plano_impressao)
  VALUES (v_lote.lote_id, 0, p_idempotency_key, p_rotulo, p_plano, p_plano_impressao)
  RETURNING * INTO v_item;

  -- As provas entram como fatos datados; elas nao "passam" o item sozinhas.
  FOR v_val IN SELECT * FROM jsonb_array_elements(coalesce(p_validacoes, '[]'::jsonb))
  LOOP
    INSERT INTO public.trafego_validacao
      (lote_id, item_id, camada, regra, resultado, mensagem, detalhe, validado_em, validado_por)
    VALUES (
      v_lote.lote_id, v_item.item_id,
      v_val ->> 'camada', v_val ->> 'regra', v_val ->> 'resultado',
      v_val ->> 'mensagem', coalesce(v_val -> 'detalhe', '{}'::jsonb),
      now(), coalesce(v_val ->> 'validado_por', p_declarada_por));

    IF v_val ->> 'resultado' = 'passou' AND v_val ->> 'camada' = 'local' THEN
      v_tem_local := true;
    ELSIF v_val ->> 'resultado' = 'passou' AND v_val ->> 'camada' = 'validate_only' THEN
      v_tem_remoto := true;
    END IF;
  END LOOP;

  UPDATE public.trafego_lote SET estado = 'validando' WHERE lote_id = v_lote.lote_id;

  IF v_tem_local THEN
    UPDATE public.trafego_lote_item SET estado = 'validado_local'
     WHERE item_id = v_item.item_id RETURNING * INTO v_item;
  END IF;
  IF v_tem_local AND v_tem_remoto THEN
    UPDATE public.trafego_lote_item SET estado = 'validado_remoto'
     WHERE item_id = v_item.item_id RETURNING * INTO v_item;
    UPDATE public.trafego_lote SET estado = 'aguardando_aprovacao'
     WHERE lote_id = v_lote.lote_id;
  END IF;

  SELECT l.* INTO v_lote FROM public.trafego_lote l WHERE l.lote_id = v_lote.lote_id;

  RETURN jsonb_build_object(
    'reaproveitado', false,
    'intencao_id',   v_intencao,
    'blueprint_id',  v_blueprint,
    'lote_id',       v_lote.lote_id,
    'item_id',       v_item.item_id,
    'item_estado',   v_item.estado,
    'lote_estado',   v_lote.estado,
    'tentativas',    v_item.tentativas
  );
END
$funcao$;


-- -----------------------------------------------------------------------------
-- 5. trafego_ledger_despachar — a autorizacao e o recibo, antes da rede
-- -----------------------------------------------------------------------------
-- ⚠️ ESTA E A FUNCAO QUE JUSTIFICA A MIGRATION. Ela trava o item, confere que a
-- autorizacao e desta conta, deste canal, deste plano e deste operador, move o
-- item para `criando` e abre o recibo `em_voo` — tudo antes de qualquer byte
-- sair para a plataforma, e tudo num unico COMMIT.
--
-- Quem chama so pode falar com o Google DEPOIS que esta funcao retornou. Se ela
-- levantar, nenhuma chamada acontece: erro de persistencia bloqueia o mutate,
-- e nao o contrario.
CREATE OR REPLACE FUNCTION public.trafego_ledger_despachar(
  p_idempotency_key     text,
  p_plataforma          text,
  p_conta_externa       text,
  p_canal               text,
  p_aprovacao_impressao text,
  p_aprovado_por        text,
  p_aprovado_por_sub    text,
  p_operacao            text    DEFAULT 'criar_campanha',
  p_request_id          text    DEFAULT NULL,
  p_aprovacao_observacao text   DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $funcao$
DECLARE
  v_item     public.trafego_lote_item%ROWTYPE;
  v_lote     public.trafego_lote%ROWTYPE;
  v_recibo   uuid;
  v_tentativa integer;
  v_abertos  integer;
BEGIN
  SELECT i.* INTO v_item FROM public.trafego_lote_item i
   WHERE i.idempotency_key = p_idempotency_key FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION
      'trafego_ledger_despachar: nao existe item com a chave %. Abra o lancamento antes de autorizar — autorizar o que nao foi registrado e autorizar de memoria.',
      p_idempotency_key USING ERRCODE = 'no_data_found';
  END IF;

  SELECT l.* INTO v_lote FROM public.trafego_lote l
   WHERE l.lote_id = v_item.lote_id FOR UPDATE;

  IF v_lote.plataforma    IS DISTINCT FROM p_plataforma
     OR v_lote.conta_externa IS DISTINCT FROM p_conta_externa
     OR v_lote.canal         IS DISTINCT FROM p_canal THEN
    RAISE EXCEPTION
      'trafego_ledger_despachar: a autorizacao chegou para %/%/% e o item pertence a %/%/%. Uma aprovacao nao atravessa de conta nem de canal.',
      p_plataforma, p_conta_externa, p_canal,
      v_lote.plataforma, v_lote.conta_externa, v_lote.canal
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF v_item.plano_impressao IS DISTINCT FROM p_aprovacao_impressao THEN
    RAISE EXCEPTION
      'trafego_ledger_despachar: o item guarda o plano % e a aprovacao apresentada e de %. O payload efetivo mudou depois da prova (inclusive por autocorrecao) ou a impressao aprovada nao foi a enviada. Nada foi despachado.',
      coalesce(v_item.plano_impressao, 'NULL'), coalesce(p_aprovacao_impressao, 'NULL')
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- Reentrada honesta: se ja ha recibo sem desfecho, a resposta e verificar, e
  -- nunca despachar de novo. A CAMADA 4 tambem barraria; esta mensagem existe
  -- para o operador saber o que fazer, e nao so que foi recusado.
  SELECT count(*) INTO v_abertos FROM public.trafego_recibo r
   WHERE r.item_id = v_item.item_id AND r.operacao = p_operacao
     AND r.desfecho IN ('em_voo', 'sem_resposta');
  IF v_abertos > 0 THEN
    RAISE EXCEPTION
      'trafego_ledger_despachar: o item % ja tem % recibo(s) sem desfecho. Verifique na conta e reconcilie; despachar agora seria mandar a segunda chamada do mesmo plano.',
      v_item.item_id, v_abertos USING ERRCODE = 'restrict_violation';
  END IF;

  IF v_item.aprovado_em IS NOT NULL
     AND v_item.aprovado_por_sub IS DISTINCT FROM p_aprovado_por_sub THEN
    RAISE EXCEPTION
      'trafego_ledger_despachar: este item ja foi aprovado por outra identidade. Uma autorizacao nao muda de dono.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- O lote sobe ate `executando`; a v10_01 exige `aprovado_em` para isso, e a
  -- exigencia e o ponto.
  IF v_lote.estado = 'preparando' THEN
    UPDATE public.trafego_lote SET estado = 'validando' WHERE lote_id = v_lote.lote_id;
    v_lote.estado := 'validando';
  END IF;
  IF v_lote.estado = 'validando' THEN
    UPDATE public.trafego_lote SET estado = 'aguardando_aprovacao' WHERE lote_id = v_lote.lote_id;
    v_lote.estado := 'aguardando_aprovacao';
  END IF;
  IF v_lote.estado = 'aguardando_aprovacao' THEN
    UPDATE public.trafego_lote
       SET estado = 'aprovado', aprovado_por = p_aprovado_por, aprovado_em = now(),
           aprovacao_observacao = p_aprovacao_observacao
     WHERE lote_id = v_lote.lote_id;
    v_lote.estado := 'aprovado';
  END IF;
  -- Um lote que terminou com falha CONFIRMADA volta a executar. A v10_01 declara
  -- `concluido_com_falhas->executando` justamente porque um erro respondido pela
  -- plataforma e informacao, e informacao nao queima a intencao.
  IF v_lote.estado IN ('aprovado', 'concluido_com_falhas', 'interrompido') THEN
    UPDATE public.trafego_lote SET estado = 'executando' WHERE lote_id = v_lote.lote_id;
    v_lote.estado := 'executando';
  END IF;
  IF v_lote.estado <> 'executando' THEN
    RAISE EXCEPTION
      'trafego_ledger_despachar: o lote esta em `%` e nao pode executar. Nada foi despachado.',
      v_lote.estado USING ERRCODE = 'restrict_violation';
  END IF;

  IF v_item.estado = 'planejado' THEN
    UPDATE public.trafego_lote_item SET estado = 'validado_local'
     WHERE item_id = v_item.item_id; v_item.estado := 'validado_local';
  END IF;
  IF v_item.estado = 'validado_local' THEN
    UPDATE public.trafego_lote_item SET estado = 'validado_remoto'
     WHERE item_id = v_item.item_id; v_item.estado := 'validado_remoto';
  END IF;
  IF v_item.estado = 'validado_remoto' THEN
    UPDATE public.trafego_lote_item SET estado = 'aprovado'
     WHERE item_id = v_item.item_id; v_item.estado := 'aprovado';
  END IF;
  -- ⚠️ `falhou` E REENTRAVEL, `indeterminado` NAO E — e a diferenca e o inteiro
  -- assunto deste arquivo. `falhou` significa que a plataforma RESPONDEU que nao
  -- criou; a camada 2 da v10_01 so deixa um item chegar a `falhou` quando nenhum
  -- recibo esta em aberto, entao sabemos que nada ficou em transito. Ja
  -- `indeterminado` significa que ninguem respondeu, e dali a saida e verificar
  -- na conta (`trafego_ledger_reconciliar`), nunca despachar de novo — a
  -- camada 3 da v10_01 recusa, e esta funcao nem tenta.
  IF v_item.estado = 'falhou' THEN
    UPDATE public.trafego_lote_item SET estado = 'criando', tentativas = v_item.tentativas + 1
     WHERE item_id = v_item.item_id;
    INSERT INTO public.trafego_recibo
      (item_id, idempotency_key, tentativa, operacao, enviado_em, request_id)
    VALUES (v_item.item_id, v_item.idempotency_key, v_item.tentativas + 1, p_operacao, now(), p_request_id)
    RETURNING recibo_id INTO v_recibo;
    RETURN jsonb_build_object(
      'item_id', v_item.item_id, 'lote_id', v_lote.lote_id, 'recibo_id', v_recibo,
      'tentativa', v_item.tentativas + 1, 'desfecho', 'em_voo', 'reentrada_apos', 'falhou');
  END IF;

  IF v_item.estado <> 'aprovado' THEN
    RAISE EXCEPTION
      'trafego_ledger_despachar: o item esta em `%`; so `aprovado` ou `falhou` (erro respondido) entram em `criando`. `indeterminado` sai por verificacao na conta, nao por reenvio. Nada foi despachado.',
      v_item.estado USING ERRCODE = 'restrict_violation';
  END IF;

  v_tentativa := v_item.tentativas + 1;

  -- A aprovacao e a entrada em `criando` no mesmo UPDATE: o gatilho da secao 3
  -- exige a autorizacao vinculada ao plano exatamente aqui.
  UPDATE public.trafego_lote_item
     SET estado              = 'criando',
         tentativas          = v_tentativa,
         aprovado_por        = coalesce(v_item.aprovado_por, p_aprovado_por),
         aprovado_por_sub    = coalesce(v_item.aprovado_por_sub, p_aprovado_por_sub),
         aprovado_em         = coalesce(v_item.aprovado_em, now()),
         aprovacao_impressao = coalesce(v_item.aprovacao_impressao, p_aprovacao_impressao)
   WHERE item_id = v_item.item_id;

  INSERT INTO public.trafego_recibo
    (item_id, idempotency_key, tentativa, operacao, enviado_em, request_id)
  VALUES (v_item.item_id, v_item.idempotency_key, v_tentativa, p_operacao, now(), p_request_id)
  RETURNING recibo_id INTO v_recibo;

  RETURN jsonb_build_object(
    'item_id',   v_item.item_id,
    'lote_id',   v_lote.lote_id,
    'recibo_id', v_recibo,
    'tentativa', v_tentativa,
    'desfecho',  'em_voo'
  );
END
$funcao$;


-- -----------------------------------------------------------------------------
-- 6. trafego_ledger_fechar — a resposta, o id externo e a identidade, juntos
-- -----------------------------------------------------------------------------
-- Fechar o recibo, carimbar o id externo, criar a identidade da instancia e
-- mover o item sao quatro escritas que so fazem sentido juntas: um recibo de
-- sucesso sem id externo e uma campanha que existe na conta e nao existe aqui.
CREATE OR REPLACE FUNCTION public.trafego_ledger_fechar(
  p_recibo_id           uuid,
  p_desfecho            text,
  p_id_externo          text    DEFAULT NULL,
  p_volc_campaign_id    text    DEFAULT NULL,
  p_customer_id         text    DEFAULT NULL,
  p_erro_codigo         text    DEFAULT NULL,
  p_erro_mensagem       text    DEFAULT NULL,
  p_resposta_bruta      jsonb   DEFAULT NULL,
  p_operacoes_consumidas integer DEFAULT NULL,
  p_fechado_por         text    DEFAULT 'volc_os'
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $funcao$
DECLARE
  v_recibo public.trafego_recibo%ROWTYPE;
  v_item   public.trafego_lote_item%ROWTYPE;
  v_estado text;
BEGIN
  IF p_desfecho NOT IN ('sucesso', 'erro', 'sem_resposta') THEN
    RAISE EXCEPTION
      'trafego_ledger_fechar: desfecho % nao existe. `em_voo` nao se fecha em `em_voo`; ausencia de resposta e `sem_resposta`.',
      p_desfecho USING ERRCODE = 'invalid_parameter_value';
  END IF;

  SELECT r.* INTO v_recibo FROM public.trafego_recibo r
   WHERE r.recibo_id = p_recibo_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'trafego_ledger_fechar: recibo % nao existe.', p_recibo_id
      USING ERRCODE = 'no_data_found';
  END IF;
  IF v_recibo.desfecho <> 'em_voo' THEN
    RAISE EXCEPTION
      'trafego_ledger_fechar: o recibo % ja fechou como `%`. Um recibo fecha uma vez; a leitura tardia entra por trafego_ledger_reconciliar.',
      p_recibo_id, v_recibo.desfecho USING ERRCODE = 'restrict_violation';
  END IF;

  SELECT i.* INTO v_item FROM public.trafego_lote_item i
   WHERE i.item_id = v_recibo.item_id FOR UPDATE;

  IF p_desfecho = 'sucesso' THEN
    IF btrim(coalesce(p_id_externo, '')) = '' OR btrim(coalesce(p_volc_campaign_id, '')) = '' THEN
      RAISE EXCEPTION
        'trafego_ledger_fechar: sucesso sem id externo ou sem identidade da instancia. "Criou" sem saber o que criou nao e sucesso — use `sem_resposta` e reconcilie.'
        USING ERRCODE = 'invalid_parameter_value';
    END IF;

    INSERT INTO public.trafego_campanha
      (volc_campaign_id, campaign_id, customer_id, procedencia,
       procedencia_declarada_por, procedencia_declarada_em, criada_por)
    VALUES (p_volc_campaign_id, p_id_externo, p_customer_id, 'volc_os',
            p_fechado_por, now(), p_fechado_por)
    ON CONFLICT (volc_campaign_id) DO NOTHING;

    UPDATE public.trafego_recibo
       SET desfecho = 'sucesso', respondido_em = now(),
           resposta_id_externo = p_id_externo, resposta_bruta = p_resposta_bruta,
           operacoes_consumidas = p_operacoes_consumidas
     WHERE recibo_id = p_recibo_id;

    UPDATE public.trafego_lote_item
       SET estado = 'criada_pausada', id_externo = p_id_externo,
           id_externo_lido_em = now(), volc_campaign_id = p_volc_campaign_id
     WHERE item_id = v_item.item_id;
    v_estado := 'criada_pausada';

    UPDATE public.trafego_lote SET estado = 'concluido'
     WHERE lote_id = v_item.lote_id AND estado = 'executando';

  ELSIF p_desfecho = 'erro' THEN
    IF btrim(coalesce(p_erro_mensagem, '')) = '' THEN
      RAISE EXCEPTION
        'trafego_ledger_fechar: `erro` exige mensagem. Uma falha sem motivo registrado vira "tente de novo" na proxima leitura.'
        USING ERRCODE = 'invalid_parameter_value';
    END IF;

    UPDATE public.trafego_recibo
       SET desfecho = 'erro', respondido_em = now(),
           erro_codigo = p_erro_codigo, erro_mensagem = p_erro_mensagem,
           resposta_bruta = p_resposta_bruta
     WHERE recibo_id = p_recibo_id;

    UPDATE public.trafego_lote_item
       SET estado = 'falhou', erro_codigo = p_erro_codigo,
           erro_mensagem = p_erro_mensagem, erro_em = now(),
           erro_detalhe = p_resposta_bruta
     WHERE item_id = v_item.item_id;
    v_estado := 'falhou';

    UPDATE public.trafego_lote SET estado = 'concluido_com_falhas'
     WHERE lote_id = v_item.lote_id AND estado = 'executando';

  ELSE
    -- ⚠️ `sem_resposta` NAO e falha. E ignorancia carimbada, e o item vai para
    -- `indeterminado` — o unico estado honesto quando nao se sabe se criou.
    UPDATE public.trafego_recibo
       SET desfecho = 'sem_resposta', respondido_em = now(),
           erro_codigo = p_erro_codigo, erro_mensagem = p_erro_mensagem
     WHERE recibo_id = p_recibo_id;

    UPDATE public.trafego_lote_item SET estado = 'indeterminado'
     WHERE item_id = v_item.item_id;
    v_estado := 'indeterminado';

    UPDATE public.trafego_lote SET estado = 'interrompido'
     WHERE lote_id = v_item.lote_id AND estado = 'executando';
  END IF;

  RETURN jsonb_build_object(
    'recibo_id', p_recibo_id, 'item_id', v_item.item_id,
    'desfecho', p_desfecho, 'item_estado', v_estado,
    'id_externo', CASE WHEN p_desfecho = 'sucesso' THEN p_id_externo ELSE NULL END
  );
END
$funcao$;


-- -----------------------------------------------------------------------------
-- 7. trafego_ledger_reconciliar — a leitura tardia fecha o MESMO recibo
-- -----------------------------------------------------------------------------
-- O caminho de quem tem um `em_voo` orfao: le a conta, registra o que viu e
-- fecha o recibo que ja existe. Nunca abre outro, nunca reenvia.
--
-- `achou` e tri-estado por contrato: true = esta la; false = conferi e nao
-- esta; NULL = nao consegui ler. NULL nao move nada — nao ler nao e um fato
-- sobre a conta, e um fato sobre nos.
CREATE OR REPLACE FUNCTION public.trafego_ledger_reconciliar(
  p_item_id            uuid,
  p_metodo             text,
  p_achou              boolean,
  p_verificado_por     text,
  p_id_externo         text    DEFAULT NULL,
  p_volc_campaign_id   text    DEFAULT NULL,
  p_customer_id        text    DEFAULT NULL,
  p_quantidade         integer DEFAULT NULL,
  p_motivo             text    DEFAULT NULL,
  p_estado_externo     text    DEFAULT NULL,
  p_divergencia        jsonb   DEFAULT '{}'::jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $funcao$
DECLARE
  v_item     public.trafego_lote_item%ROWTYPE;
  v_recibo   public.trafego_recibo%ROWTYPE;
  v_verif    uuid;
  v_estado   text;
  v_fechou   text := NULL;
BEGIN
  SELECT i.* INTO v_item FROM public.trafego_lote_item i
   WHERE i.item_id = p_item_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'trafego_ledger_reconciliar: item % nao existe.', p_item_id
      USING ERRCODE = 'no_data_found';
  END IF;

  SELECT r.* INTO v_recibo FROM public.trafego_recibo r
   WHERE r.item_id = p_item_id AND r.desfecho = 'em_voo'
   ORDER BY r.tentativa DESC LIMIT 1 FOR UPDATE;

  INSERT INTO public.trafego_verificacao
    (item_id, recibo_id, verificado_em, verificado_por, metodo, achou, motivo,
     id_externo_encontrado, quantidade_encontrada, estado_externo_observado, divergencia)
  VALUES (p_item_id, v_recibo.recibo_id, now(), p_verificado_por, p_metodo, p_achou,
          p_motivo, p_id_externo, p_quantidade, p_estado_externo,
          coalesce(p_divergencia, '{}'::jsonb))
  RETURNING verificacao_id INTO v_verif;

  v_estado := v_item.estado;

  IF p_achou IS TRUE THEN
    IF btrim(coalesce(p_id_externo, '')) = '' OR btrim(coalesce(p_volc_campaign_id, '')) = '' THEN
      RAISE EXCEPTION
        'trafego_ledger_reconciliar: achou a campanha mas nao trouxe id externo e identidade. "Esta la" sem saber qual e nao fecha recibo nenhum.'
        USING ERRCODE = 'invalid_parameter_value';
    END IF;

    INSERT INTO public.trafego_campanha
      (volc_campaign_id, campaign_id, customer_id, procedencia,
       procedencia_declarada_por, procedencia_declarada_em, criada_por)
    VALUES (p_volc_campaign_id, p_id_externo, p_customer_id, 'volc_os',
            p_verificado_por, now(), p_verificado_por)
    ON CONFLICT (volc_campaign_id) DO NOTHING;

    IF v_recibo.recibo_id IS NOT NULL THEN
      UPDATE public.trafego_recibo
         SET desfecho = 'sucesso', respondido_em = now(), resposta_id_externo = p_id_externo
       WHERE recibo_id = v_recibo.recibo_id;
      v_fechou := 'sucesso';
    END IF;

    IF v_item.estado IN ('criando', 'indeterminado') THEN
      UPDATE public.trafego_lote_item
         SET estado = 'criada_pausada', id_externo = p_id_externo,
             id_externo_lido_em = now(), volc_campaign_id = p_volc_campaign_id
       WHERE item_id = p_item_id;
      v_estado := 'criada_pausada';
      UPDATE public.trafego_lote SET estado = 'concluido'
       WHERE lote_id = v_item.lote_id AND estado IN ('executando', 'interrompido');
    END IF;

  ELSIF p_achou IS FALSE THEN
    -- Conferimos e nao esta la. Isso fecha a IGNORANCIA, nao autoriza reenvio:
    -- o recibo vira `sem_resposta` (nunca houve resposta) e o item fica
    -- `indeterminado`. Reabrir o envio e decisao humana, com plano novo.
    IF v_recibo.recibo_id IS NOT NULL THEN
      UPDATE public.trafego_recibo
         SET desfecho = 'sem_resposta', respondido_em = now(),
             erro_mensagem = coalesce(p_motivo, 'verificacao na conta nao encontrou a campanha')
       WHERE recibo_id = v_recibo.recibo_id;
      v_fechou := 'sem_resposta';
    END IF;
    IF v_item.estado = 'criando' THEN
      UPDATE public.trafego_lote_item SET estado = 'indeterminado' WHERE item_id = p_item_id;
      v_estado := 'indeterminado';
      UPDATE public.trafego_lote SET estado = 'interrompido'
       WHERE lote_id = v_item.lote_id AND estado = 'executando';
    END IF;
  END IF;
  -- p_achou IS NULL: a verificacao fica registrada e NADA muda. De proposito.

  RETURN jsonb_build_object(
    'verificacao_id', v_verif, 'item_id', p_item_id,
    'achou', p_achou, 'item_estado', v_estado,
    'recibo_id', v_recibo.recibo_id, 'recibo_fechado_como', v_fechou
  );
END
$funcao$;


-- -----------------------------------------------------------------------------
-- 8. Seguranca — quem pode chamar, e quem nao pode nem enxergar
-- -----------------------------------------------------------------------------
-- O default do Postgres concede EXECUTE a PUBLIC em toda funcao nova. Sem os
-- REVOKE abaixo, `anon` chamaria `trafego_ledger_despachar` — a funcao que
-- autoriza uma escrita na conta de anuncios — sem autenticacao nenhuma.
DO $seguranca$
DECLARE
  f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'public.trafego_ledger_abrir_lancamento(text,text,text,text,text,text,jsonb,text,text,text,text,text,jsonb,text,bigint,text,jsonb,integer,text,uuid,jsonb,uuid)',
    'public.trafego_ledger_despachar(text,text,text,text,text,text,text,text,text,text)',
    'public.trafego_ledger_fechar(uuid,text,text,text,text,text,text,jsonb,integer,text)',
    'public.trafego_ledger_reconciliar(uuid,text,boolean,text,text,text,text,integer,text,text,jsonb)'
  ] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated, service_role', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', f);
  END LOOP;

  -- Gatilhos nao sao chamaveis por ninguem.
  FOREACH f IN ARRAY ARRAY[
    'public.trafego_recibo_um_voo_por_item()',
    'public.trafego_item_aprovacao_vinculada()'
  ] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated, service_role', f);
  END LOOP;
END
$seguranca$;


-- -----------------------------------------------------------------------------
-- 9. Verificacao dentro da propria transacao
-- -----------------------------------------------------------------------------
DO $verifica$
DECLARE
  faltando text;
  alcancam text;
BEGIN
  SELECT string_agg(p, ', ' ORDER BY p) INTO faltando
    FROM unnest(ARRAY[
      'trafego_ledger_abrir_lancamento', 'trafego_ledger_despachar',
      'trafego_ledger_fechar', 'trafego_ledger_reconciliar',
      'trafego_recibo_um_voo_por_item', 'trafego_item_aprovacao_vinculada'
    ]) AS p
   WHERE NOT EXISTS (SELECT 1 FROM pg_proc pr JOIN pg_namespace n ON n.oid = pr.pronamespace
                      WHERE n.nspname = 'public' AND pr.proname = p);
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'v10_03: funcao nao criada: %', faltando;
  END IF;

  SELECT string_agg(t, ', ' ORDER BY t) INTO faltando
    FROM unnest(ARRAY['trafego_recibo_um_voo_por_item', 'trafego_item_aprovacao_vinculada']) AS t
   WHERE NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = t AND NOT tgisinternal);
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION
      'v10_03: gatilho nao criado: % — a funcao existiria sem nunca disparar, que e pior que nao existir.', faltando;
  END IF;

  SELECT string_agg(c, ', ' ORDER BY c) INTO faltando
    FROM unnest(ARRAY[
      'trafego_item_plano_impressao_sha256', 'trafego_item_aprovacao_impressao_sha256',
      'trafego_item_aprovacao_indivisivel', 'trafego_item_aprovacao_vinculada_ao_plano'
    ]) AS c
   WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = c);
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'v10_03: constraint nao criada: %', faltando;
  END IF;

  -- ⚠️ A conferencia que importa: `anon` nao chama nada disto.
  SELECT string_agg(pr.proname, ', ' ORDER BY pr.proname) INTO alcancam
    FROM pg_proc pr JOIN pg_namespace n ON n.oid = pr.pronamespace
   WHERE n.nspname = 'public' AND pr.proname LIKE 'trafego\_ledger\_%'
     AND (has_function_privilege('anon', pr.oid, 'EXECUTE')
       OR has_function_privilege('authenticated', pr.oid, 'EXECUTE'));
  IF alcancam IS NOT NULL THEN
    RAISE EXCEPTION
      'v10_03: anon/authenticated ainda executam: % — a porta de escrita ficaria aberta sem autenticacao de aplicacao.', alcancam;
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_proc pr JOIN pg_namespace n ON n.oid = pr.pronamespace
     WHERE n.nspname = 'public' AND pr.proname LIKE 'trafego\_ledger\_%'
       AND pr.prosecdef) THEN
    RAISE EXCEPTION
      'v10_03: funcao do ledger marcada SECURITY DEFINER — ela viraria escada de privilegio se o EXECUTE vazasse.';
  END IF;

  RAISE NOTICE 'v10_03: verificacao interna passou';
END
$verifica$;

COMMIT;

-- =============================================================================
-- CONFERENCIA DEPOIS DE APLICAR (somente leitura, cole no psql)
-- =============================================================================
-- -- os recibos sem desfecho, e ha quanto tempo (o que exige reconciliacao):
-- SELECT r.recibo_id, r.item_id, r.idempotency_key, r.tentativa, r.desfecho,
--        now() - r.enviado_em AS ha
--   FROM public.trafego_recibo r
--  WHERE r.desfecho IN ('em_voo', 'sem_resposta') ORDER BY r.enviado_em;
--
-- -- quem pode chamar o ledger (esperado: so service_role):
-- SELECT p.proname, r.rolname, has_function_privilege(r.rolname, p.oid, 'EXECUTE') AS executa
--   FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--   CROSS JOIN (VALUES ('anon'),('authenticated'),('service_role')) AS r(rolname)
--  WHERE n.nspname = 'public' AND p.proname LIKE 'trafego\_ledger\_%' ORDER BY 1, 2;
