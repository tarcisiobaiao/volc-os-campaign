-- =============================================================================
-- v10_04_rollback — devolve a maquina de estados e a reconciliacao da v10_03
-- =============================================================================
--
-- ⚠️ O QUE ESTE ROLLBACK CUSTA, DITO ANTES DE SER RODADO
--
-- Ele REABRE o defeito que a v10_04 fecha: a reconciliacao volta a tentar
-- `interrompido->concluido`, a maquina de estados volta a recusar essa
-- transicao, e todo item que ficou `indeterminado` volta a nao ter saida
-- nenhuma que nao seja `UPDATE` a mao no banco.
--
-- Perde-se tambem a checagem de posse: reconciliar o item de uma conta com a
-- campanha de outra volta a ser aceito.
--
-- Antes de rodar, leia o que ficaria travado:
--
--   SELECT i.item_id, i.estado, l.estado AS lote, l.conta_externa
--     FROM public.trafego_lote_item i
--     JOIN public.trafego_lote l ON l.lote_id = i.lote_id
--    WHERE i.estado = 'indeterminado';
--
-- Os itens ja reconciliados PERMANECEM reconciliados: este arquivo restaura
-- funcoes, e nao desfaz linhas. Nenhuma verificacao gravada e apagada, e
-- nenhum recibo muda de desfecho.
-- =============================================================================

BEGIN;

DO $guarda$
BEGIN
  IF to_regclass('public.trafego_lote') IS NULL THEN
    RAISE EXCEPTION 'v10_04_rollback: trafego_lote ausente; nada a desfazer.';
  END IF;
END
$guarda$;


-- 1. A maquina de estados volta ao texto da v10_01, sem as duas transicoes.
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

    IF NEW.estado = 'executando' AND NEW.aprovado_em IS NULL THEN
      RAISE EXCEPTION
        'trafego_lote: execucao sem aprovacao humana registrada. Preencha aprovado_por/aprovado_em antes — o sistema sugere, o operador confirma.'
        USING ERRCODE = 'restrict_violation';
    END IF;
  END IF;
  RETURN NEW;
END
$funcao$;


-- 2. A reconciliacao volta ao corpo da v10_03: so recibo `em_voo`, sem posse.
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

  RETURN jsonb_build_object(
    'verificacao_id', v_verif, 'item_id', p_item_id,
    'achou', p_achou, 'item_estado', v_estado,
    'recibo_id', v_recibo.recibo_id, 'recibo_fechado_como', v_fechou
  );
END
$funcao$;

REVOKE ALL ON FUNCTION public.trafego_ledger_reconciliar(uuid,text,boolean,text,text,text,text,integer,text,text,jsonb)
  FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.trafego_ledger_reconciliar(uuid,text,boolean,text,text,text,text,integer,text,text,jsonb)
  TO service_role;

COMMIT;
