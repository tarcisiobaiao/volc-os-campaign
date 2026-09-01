-- =============================================================================
-- v10_04_saida_do_indeterminado — a reconciliacao passa a funcionar
-- =============================================================================
--
-- ⚠️ O DEFEITO QUE ESTA MIGRATION FECHA, DITO SEM RODEIO
--
-- A unica saida de um item `indeterminado` era `trafego_ledger_reconciliar`.
-- Ela nunca poderia ter funcionado no caminho para o qual foi escrita.
--
-- A cadeia, medida em 31/08/2026 num cluster efemero:
--
--   1. a chamada de criacao nao responde;
--   2. `trafego_ledger_fechar(..., 'sem_resposta')` poe o item em
--      `indeterminado` E o lote em `interrompido` (v10_03, ramo ELSE);
--   3. o operador confere a conta e chama `trafego_ledger_reconciliar`;
--   4. ela tenta `UPDATE trafego_lote SET estado = 'concluido'
--      WHERE ... estado IN ('executando', 'interrompido')`;
--   5. `trafego_lote_estado_valido` (v10_01) recusa: a lista de transicoes
--      permitidas tem `interrompido->executando` e `interrompido->cancelado`,
--      e NAO tem `interrompido->concluido`;
--   6. a excecao aborta a transacao INTEIRA. O item continua `indeterminado`,
--      a verificacao nao fica gravada, e o recibo nao fecha.
--
-- Ou seja: duas migrations discordavam sobre a maquina de estados, e a
-- discordancia so aparecia no unico caminho que importa. A prova
-- `scripts/provar-ledger-v10-03.sh` nao pegava porque o bloco J reconciliava um
-- item cujo lote ainda estava `executando` — o caso facil, que nunca acontece
-- em producao depois de uma indeterminacao.
--
-- O custo operacional do defeito: todo item indeterminado ficava permanentemente
-- travado, sem saida que nao fosse `UPDATE` a mao no banco — exatamente o que o
-- comentario da propria `trafego_lote_estado_valido` diz que nao pode existir
-- ("um estado sem caminho de saida declarado e um lote que ninguem consegue
-- destravar sem UPDATE a mao").
--
-- ESTA MIGRATION NAO FOI APLICADA no Supabase oficial. Nem a v10_01, v10_02 ou
-- v10_03 foram — ver `README.md`. Ela e preparada, provada em cluster
-- descartavel, e espera autorizacao explicita.
--
-- Tres mudancas, e nada alem delas:
--
--   1. a maquina de estados do lote ganha a saida que faltava;
--   2. a reconciliacao passa a ligar a verificacao ao recibo do item mesmo
--      quando ele ja fechou — sem isso, a auditoria perde o fio entre "nao
--      respondeu" e "conferi depois e estava la";
--   3. a reconciliacao confere que o item pertence a conta informada.
-- =============================================================================

BEGIN;

DO $guarda$
BEGIN
  IF to_regclass('public.trafego_lote') IS NULL THEN
    RAISE EXCEPTION 'v10_04 exige a v10_01 aplicada (trafego_lote ausente).';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                  WHERE n.nspname = 'public'
                    AND p.proname = 'trafego_ledger_reconciliar') THEN
    RAISE EXCEPTION 'v10_04 exige a v10_03 aplicada (trafego_ledger_reconciliar ausente).';
  END IF;
END
$guarda$;


-- -----------------------------------------------------------------------------
-- 1. A maquina de estados do lote ganha a saida que faltava
-- -----------------------------------------------------------------------------
-- `interrompido->concluido` e transicao de negocio legitima, e nao um
-- afrouxamento: "fomos interrompidos, fomos conferir, e o trabalho tinha
-- chegado" e exatamente o que a reconciliacao descobre. Sem ela o estado
-- `interrompido` e um beco sem saida.
--
-- O resto da lista continua identico — em particular, `executando` continua
-- exigindo `aprovado_em`, que e o ADR-09 em forma de schema.
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
    -- v10_04: a saida que faltava para a reconciliacao existir. UMA, e nao
    -- duas: `interrompido->concluido_com_falhas` foi cogitada e removida por
    -- nao ter chamador nenhum. Transicao sem consumidor e superficie que
    -- alguem vai usar sem que ninguem tenha decidido o que ela significa.
    'interrompido->concluido',
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

  -- ⚠️ DAQUI PARA BAIXO E COPIA LITERAL DA v10_01, E PRECISA CONTINUAR SENDO.
  --
  -- `CREATE OR REPLACE FUNCTION` substitui o CORPO INTEIRO. Uma primeira versao
  -- desta migration reescreveu a funcao copiando so a lista de transicoes e
  -- parou no `RETURN NEW` — apagando em silencio a imutabilidade da aprovacao,
  -- a identidade do lote, a monotonicidade da leitura de quota e o carimbo de
  -- `atualizado_em`. Nenhuma prova pegava: a verificacao procurava a substring
  -- da transicao nova, e encontrava.
  --
  -- Uma migration que acrescenta uma transicao e apaga quatro guardas nao e uma
  -- migration incremental; e uma reescrita disfarcada.

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


-- -----------------------------------------------------------------------------
-- 2. e 3. A reconciliacao: fio de auditoria preservado e posse conferida
-- -----------------------------------------------------------------------------
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
  v_lote     public.trafego_lote%ROWTYPE;
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

  SELECT l.* INTO v_lote FROM public.trafego_lote l
   WHERE l.lote_id = v_item.lote_id FOR UPDATE;

  -- ⚠️ POSSE (v10_04). A funcao achava o item so pelo id e nunca conferia de
  -- quem ele era. Com `item_id`, `p_customer_id` e `p_id_externo` chegando como
  -- tres campos independentes, trocar um deles por engano casava o item da
  -- conta A com a campanha da conta B — carimbando no item uma identidade
  -- externa que nao e dele. Nao cria campanha nenhuma, e corrompe a procedencia
  -- de duas. `NULL` continua aceito: quem nao afirma a conta nao erra sobre ela.
  -- ⚠️ E quando `p_achou` afirma que a campanha esta la, a conta e OBRIGATORIA.
  -- Uma primeira versao so conferia quando `p_customer_id` vinha preenchido, o
  -- que transformava a guarda num pedido: bastava omitir o parametro para
  -- carimbar identidade externa em item de qualquer conta. Omitir agora e
  -- recusado no unico caso em que o campo decide alguma coisa.
  IF p_achou IS TRUE AND p_customer_id IS NULL THEN
    RAISE EXCEPTION
      'trafego_ledger_reconciliar: `achou=true` exige p_customer_id. Sem a conta nao da para conferir que a campanha encontrada e do dono deste item.'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  IF p_customer_id IS NOT NULL
     AND regexp_replace(p_customer_id, '\D', '', 'g')
         IS DISTINCT FROM regexp_replace(coalesce(v_lote.conta_externa, ''), '\D', '', 'g') THEN
    RAISE EXCEPTION
      'trafego_ledger_reconciliar: o item % pertence a conta %, e nao a %. Reconciliar um item com a campanha de outra conta trocaria a procedencia das duas.',
      p_item_id, v_lote.conta_externa, p_customer_id
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  -- ⚠️ FIO DA AUDITORIA (v10_04). Antes, so um recibo `em_voo` era procurado.
  -- No caminho NORMAL a rota ja fechou o recibo como `sem_resposta` no instante
  -- em que descobriu a indeterminacao — entao `v_recibo` vinha nulo e a
  -- verificacao ficava gravada sem apontar para recibo nenhum. Quem auditasse
  -- depois nao conseguia ligar "nao respondeu" a "conferi e estava la".
  --
  -- Agora pega-se o recibo mais recente do item, preferindo o que ainda esta
  -- `em_voo`. O que NAO muda: so um recibo `em_voo` pode ser FECHADO aqui. Um
  -- recibo fechado continua fechado — ele diz o que era verdade na hora, e
  -- reescrever isso seria apagar o registro em vez de complementa-lo.
  SELECT r.* INTO v_recibo FROM public.trafego_recibo r
   WHERE r.item_id = p_item_id
   ORDER BY (r.desfecho = 'em_voo') DESC, r.tentativa DESC
   LIMIT 1 FOR UPDATE;

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

    IF v_recibo.recibo_id IS NOT NULL AND v_recibo.desfecho = 'em_voo' THEN
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
      -- ⚠️ O LOTE SO CONCLUI QUANDO NAO SOBRA IRMAO EM ABERTO.
      --
      -- A v10_03 concluia o lote ao reconciliar UM item, sem olhar os irmaos.
      -- Enquanto so `executando->concluido` existia isso ja era frouxo; com a
      -- v10_04 abrindo `interrompido->concluido` ficaria pior, porque
      -- `interrompido` e exatamente o estado de um lote com item indeterminado.
      -- Num lote de dois itens indeterminados, reconciliar um concluiria o lote
      -- e deixaria o outro para tras — e `concluido` significa, no comentario da
      -- propria v10_01, "todos os itens chegaram ao fim sem erro".
      IF NOT EXISTS (
        SELECT 1 FROM public.trafego_lote_item ir
         WHERE ir.lote_id = v_item.lote_id
           AND ir.item_id <> p_item_id
           AND ir.estado IN ('planejado', 'validado_local', 'validado_remoto',
                             'aprovado', 'criando', 'indeterminado')
      ) THEN
        UPDATE public.trafego_lote SET estado = 'concluido'
         WHERE lote_id = v_item.lote_id AND estado IN ('executando', 'interrompido');
      END IF;
    END IF;

  ELSIF p_achou IS FALSE THEN
    -- Conferimos e nao esta la. Isso fecha a IGNORANCIA, nao autoriza reenvio:
    -- o recibo vira `sem_resposta` (nunca houve resposta) e o item fica
    -- `indeterminado`. Reabrir o envio e decisao humana, com plano novo.
    IF v_recibo.recibo_id IS NOT NULL AND v_recibo.desfecho = 'em_voo' THEN
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

-- Os GRANTs da v10_03 sobrevivem ao `CREATE OR REPLACE` (mesma assinatura),
-- mas reafirma-los custa nada e documenta quem pode chamar.
REVOKE ALL ON FUNCTION public.trafego_ledger_reconciliar(uuid,text,boolean,text,text,text,text,integer,text,text,jsonb)
  FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.trafego_ledger_reconciliar(uuid,text,boolean,text,text,text,text,integer,text,text,jsonb)
  TO service_role;
REVOKE ALL ON FUNCTION public.trafego_lote_estado_valido()
  FROM PUBLIC, anon, authenticated, service_role;


-- -----------------------------------------------------------------------------
-- 4. Verificacao dentro da propria transacao
-- -----------------------------------------------------------------------------
DO $verifica$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.proname = 'trafego_lote_estado_valido'
       AND pg_get_functiondef(p.oid) LIKE '%interrompido->concluido%') THEN
    RAISE EXCEPTION 'v10_04: a transicao interrompido->concluido nao entrou.';
  END IF;
  -- ⚠️ E as guardas da v10_01 precisam ter SOBREVIVIDO ao CREATE OR REPLACE.
  -- Procurar so a transicao nova deixaria passar exatamente o defeito que a
  -- primeira versao desta migration tinha: acrescentar uma linha e apagar
  -- quatro guardas.
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.proname = 'trafego_lote_estado_valido'
       AND pg_get_functiondef(p.oid) LIKE '%a autorizacao nao se reescreve%'
       AND pg_get_functiondef(p.oid) LIKE '%sao a identidade do lote e nao mudam%'
       AND pg_get_functiondef(p.oid) LIKE '%mais velha que a corrente%'
       AND pg_get_functiondef(p.oid) LIKE '%atualizado_em := now()%') THEN
    RAISE EXCEPTION 'v10_04: o CREATE OR REPLACE apagou guardas da v10_01.';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.proname = 'trafego_ledger_reconciliar'
       AND pg_get_functiondef(p.oid) LIKE '%pertence a conta%') THEN
    RAISE EXCEPTION 'v10_04: a checagem de posse nao entrou.';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.proname IN
           ('trafego_ledger_reconciliar', 'trafego_lote_estado_valido')
       AND p.prosecdef) THEN
    RAISE EXCEPTION 'v10_04: nenhuma destas funcoes pode ser SECURITY DEFINER.';
  END IF;
END
$verifica$;

COMMIT;
