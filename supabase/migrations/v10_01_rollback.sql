-- =============================================================================
-- v10_01 ROLLBACK — derruba o ciclo de criacao (intencao, lote, recibo)
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin (o mesmo papel que aplicou a v10_01)
--
-- ⚠️ ESTE ARQUIVO E RODADO, NAO SO ESCRITO. `scripts/provar-ciclo-v10.sh` o
-- executa contra um Postgres descartavel a cada rodada, no ciclo
-- aplicar -> reverter -> reaplicar.
--
-- A razao e um defeito medido nesta base: o rollback da v9_03 estava
-- documentado como "reaplique a v9_02" e ABORTAVA com `cannot drop columns from
-- view`. Um rollback documentado e nunca rodado so e descoberto no momento em
-- que alguem precisa dele, que e sempre o pior momento.
--
-- -----------------------------------------------------------------------------
-- ⚠️ O QUE ESTE ARQUIVO APAGA, E POR QUE ISSO E MAIS CARO DO QUE PARECE
-- -----------------------------------------------------------------------------
-- Ele apaga as CHAVES DE IDEMPOTENCIA. Elas sao o unico elo entre um item e uma
-- campanha que talvez ja exista na conta — inclusive as dos recibos que ficaram
-- `em_voo`, que sao exatamente os casos que ninguem resolveu ainda.
--
-- Depois deste rollback, um lote que estava no meio da execucao perde a
-- capacidade de descobrir o que ja criou. A conta continua com as campanhas; o
-- sistema deixa de saber que elas sao dele.
--
-- EXPORTE ANTES. Dez comandos, um minuto, e e a diferenca entre "reaplicar a
-- migration" e "conferir 84 campanhas a mao no painel do Google":
--
--   \copy public.trafego_intencao       TO 'trafego_intencao.csv'       CSV HEADER
--   \copy public.trafego_blueprint      TO 'trafego_blueprint.csv'      CSV HEADER
--   \copy public.trafego_lote           TO 'trafego_lote.csv'           CSV HEADER
--   \copy public.trafego_lote_item      TO 'trafego_lote_item.csv'      CSV HEADER
--   \copy public.trafego_lote_asset     TO 'trafego_lote_asset.csv'     CSV HEADER
--   \copy public.trafego_validacao      TO 'trafego_validacao.csv'      CSV HEADER
--   \copy public.trafego_recibo         TO 'trafego_recibo.csv'         CSV HEADER
--   \copy public.trafego_verificacao    TO 'trafego_verificacao.csv'    CSV HEADER
--   \copy public.trafego_rollback       TO 'trafego_rollback.csv'       CSV HEADER
--   \copy public.trafego_lote_transicao TO 'trafego_lote_transicao.csv' CSV HEADER
--
-- As duas views nao precisam de export: elas nao guardam nada.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO NAO TOCA
-- -----------------------------------------------------------------------------
-- Nada da v9 e nada da v10_02. `trafego_campanha`, `trafego_linhagem`,
-- `trafego_campanha_espelho`, `trafego_snapshot_conta`, `trafego_vinculo`,
-- `trafego_evento` e as duas views do inventario ficam INTACTAS — a v10_01 so
-- aponta para elas, nunca as altera. A prova disso esta no degrau 3 de
-- `scripts/provar-ciclo-v10.sh`, que confere o inventario depois do rollback.
--
-- `CASCADE` nao e usado de proposito: se sobrar alguma coisa apontando para
-- estas tabelas — uma view criada depois, uma FK nova —, o rollback tem de
-- PARAR e mostrar o que e, em vez de arrastar junto um objeto que ninguem
-- pediu para remover.
--
-- -----------------------------------------------------------------------------
-- ROLLBACK PARCIAL — quase sempre e isto que se quer
-- -----------------------------------------------------------------------------
-- (a) "o gatilho nao me deixa marcar o item como falhou"
--     -> ELE ESTA CERTO. Ha recibo em voo, e voce nao sabe se a chamada criou.
--        O caminho e verificar na conta e registrar em `trafego_verificacao`.
--        Marcar `falhou` a forca cria a segunda campanha.
--
-- (b) "preciso destravar um lote parado num estado sem saida"
--     -> NAO derrube o gatilho. Toda transicao legitima esta na lista de
--        `trafego_lote_estado_valido`. Se faltar uma, ela falta TAMBEM em
--        `backend/app/trafego/lote.py:TRANSICOES_DO_LOTE` — acrescente nos dois,
--        numa migration, com o teste que compara as duas listas.
--
-- (c) "o diario de transicoes esta pesando"
--     -> derrube SO ele; o resto continua de pe:
--          DROP TRIGGER trafego_lote_registra_transicao ON public.trafego_lote;
--          DROP TRIGGER trafego_item_registra_transicao ON public.trafego_lote_item;
--        E assuma explicitamente que, a partir dai, o historico voltou a
--        depender de alguem lembrar de grava-lo.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION
      'v10_01_rollback deve rodar como postgres ou supabase_admin; papel atual: %',
      current_user;
  END IF;

  IF to_regclass('public.trafego_lote') IS NULL THEN
    RAISE EXCEPTION
      'rollback abortado: trafego_lote nao existe. A v10_01 nao esta aplicada, e nao ha o que reverter.';
  END IF;

  RAISE NOTICE 'v10_01_rollback: derrubando o ciclo de criacao criado pela v10_01';
END
$guarda$;

-- Views primeiro: `trafego_lote_painel` LE `trafego_item_situacao`, e sem esta
-- ordem o DROP da segunda falharia por dependencia — que e o comportamento
-- certo do banco e o errado para um rollback que precisa terminar.
DROP VIEW IF EXISTS public.trafego_lote_painel;
DROP VIEW IF EXISTS public.trafego_item_situacao;

-- Tabelas na ordem inversa da dependencia. Sem CASCADE.
DROP TABLE IF EXISTS public.trafego_rollback;
DROP TABLE IF EXISTS public.trafego_verificacao;
DROP TABLE IF EXISTS public.trafego_recibo;
DROP TABLE IF EXISTS public.trafego_validacao;
DROP TABLE IF EXISTS public.trafego_lote_asset;
DROP TABLE IF EXISTS public.trafego_lote_item;
DROP TABLE IF EXISTS public.trafego_lote;
DROP TABLE IF EXISTS public.trafego_blueprint;
DROP TABLE IF EXISTS public.trafego_intencao;
DROP TABLE IF EXISTS public.trafego_lote_transicao;

-- As funcoes de gatilho NAO caem junto com as tabelas. Deixa-las para tras
-- faria a reaplicacao encontrar uma funcao antiga com o mesmo nome — e
-- `CREATE OR REPLACE` a substituiria em silencio, o que funciona por acaso e
-- deixa de funcionar no dia em que a assinatura mudar.
DROP FUNCTION IF EXISTS public.trafego_intencao_imutavel();
DROP FUNCTION IF EXISTS public.trafego_blueprint_so_aposenta();
DROP FUNCTION IF EXISTS public.trafego_lote_estado_valido();
DROP FUNCTION IF EXISTS public.trafego_lote_sem_delete();
DROP FUNCTION IF EXISTS public.trafego_item_estado_valido();
DROP FUNCTION IF EXISTS public.trafego_item_sem_delete();
DROP FUNCTION IF EXISTS public.trafego_recibo_fecha_uma_vez();
DROP FUNCTION IF EXISTS public.trafego_lote_append_only();
DROP FUNCTION IF EXISTS public.trafego_rollback_fecha_uma_vez();
DROP FUNCTION IF EXISTS public.trafego_lote_registra_transicao();

-- -----------------------------------------------------------------------------
-- VERIFICACAO NA PROPRIA TRANSACAO
-- -----------------------------------------------------------------------------
-- Um rollback que "roda com sucesso" e deixa metade do schema de pe e pior que
-- um que falha: a reaplicacao seguinte aborta na guarda de "ja parece aplicada"
-- e ninguem entende por que.
DO $verifica$
DECLARE
  sobrou text;
BEGIN
  SELECT string_agg(t, ', ' ORDER BY t) INTO sobrou
    FROM unnest(ARRAY[
      'trafego_intencao', 'trafego_blueprint', 'trafego_lote',
      'trafego_lote_item', 'trafego_lote_asset', 'trafego_validacao',
      'trafego_recibo', 'trafego_verificacao', 'trafego_rollback',
      'trafego_lote_transicao', 'trafego_item_situacao', 'trafego_lote_painel'
    ]) AS t
   WHERE to_regclass('public.' || t) IS NOT NULL;
  IF sobrou IS NOT NULL THEN
    RAISE EXCEPTION 'v10_01_rollback: sobrou de pe: %', sobrou;
  END IF;

  SELECT string_agg(p.proname, ', ' ORDER BY p.proname) INTO sobrou
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = 'public'
     AND p.proname IN (
       'trafego_intencao_imutavel', 'trafego_blueprint_so_aposenta',
       'trafego_lote_estado_valido', 'trafego_lote_sem_delete',
       'trafego_item_estado_valido', 'trafego_item_sem_delete',
       'trafego_recibo_fecha_uma_vez', 'trafego_lote_append_only',
       'trafego_rollback_fecha_uma_vez', 'trafego_lote_registra_transicao');
  IF sobrou IS NOT NULL THEN
    RAISE EXCEPTION 'v10_01_rollback: funcao de gatilho sobrou: %', sobrou;
  END IF;

  -- ⚠️ A v9 tem de continuar INTEIRA. Este rollback nao pode ter arrastado
  -- nada do inventario junto — e sem esta conferencia um `CASCADE` acidental
  -- numa versao futura passaria despercebido ate a tela ficar vazia.
  IF to_regclass('public.trafego_campanha') IS NULL
     OR to_regclass('public.trafego_campanha_espelho') IS NULL
     OR to_regclass('public.trafego_inventario_campanha') IS NULL THEN
    RAISE EXCEPTION
      'v10_01_rollback: o inventario da v9 foi afetado. Isto nao deveria ser possivel — nenhum DROP daqui o alcanca.';
  END IF;

  RAISE NOTICE 'v10_01_rollback: schema limpo; a v9 continua intacta';
END
$verifica$;

COMMIT;
