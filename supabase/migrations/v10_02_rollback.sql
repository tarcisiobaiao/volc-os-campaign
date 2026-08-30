-- =============================================================================
-- v10_02 ROLLBACK — derruba a autogestao (regra, evidencia, proposta, aplicacao)
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin (o mesmo papel que aplicou a v10_02)
--
-- ⚠️ ESTE ARQUIVO E RODADO, NAO SO ESCRITO. `scripts/provar-ciclo-v10.sh` o
-- executa a cada rodada, no ciclo aplicar -> reverter -> reaplicar. O rollback
-- da v9_03 estava documentado como "reaplique a v9_02" e ABORTAVA; um rollback
-- nunca rodado so e descoberto quando alguem precisa dele.
--
-- -----------------------------------------------------------------------------
-- ⚠️ O QUE ESTE ARQUIVO APAGA
-- -----------------------------------------------------------------------------
-- A trilha inteira de POR QUE cada valor de conta foi mexido: a regra citada, a
-- evidencia, o diagnostico, o diff aprovado, quem aprovou, e o
-- `valor_anterior` que torna o rollback DE CONTA possivel.
--
-- Depois deste rollback, uma aplicacao que estava em voo perde o valor anterior:
-- a conta continua com o orcamento alterado, e ninguem sabe mais para quanto
-- voltar. Este e o dado com menos copia de todo o sistema — ele nao existe em
-- lugar nenhum na plataforma.
--
-- EXPORTE ANTES:
--
--   \copy public.trafego_regra_otimizacao TO 'trafego_regra_otimizacao.csv' CSV HEADER
--   \copy public.trafego_evidencia        TO 'trafego_evidencia.csv'        CSV HEADER
--   \copy public.trafego_diagnostico      TO 'trafego_diagnostico.csv'      CSV HEADER
--   \copy public.trafego_proposta         TO 'trafego_proposta.csv'         CSV HEADER
--   \copy public.trafego_aprovacao        TO 'trafego_aprovacao.csv'        CSV HEADER
--   \copy public.trafego_aplicacao        TO 'trafego_aplicacao.csv'        CSV HEADER
--   \copy public.trafego_acompanhamento   TO 'trafego_acompanhamento.csv'   CSV HEADER
--   \copy public.trafego_atuacao_reversao TO 'trafego_atuacao_reversao.csv' CSV HEADER
--   \copy public.trafego_cooldown         TO 'trafego_cooldown.csv'         CSV HEADER
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO NAO TOCA
-- -----------------------------------------------------------------------------
-- Nada da v9 e nada da v10_01. As duas series da v10 sao independentes de
-- proposito: reverter a autogestao nao pode derrubar o ciclo de criacao, nem o
-- contrario. `scripts/provar-ciclo-v10.sh` confere isso no degrau em que reverte
-- so uma delas e continua exercitando a outra.
--
-- `CASCADE` nao e usado: se sobrar algo apontando para estas tabelas, o rollback
-- PARA e mostra o que e.
--
-- -----------------------------------------------------------------------------
-- ROLLBACK PARCIAL — quase sempre e isto que se quer
-- -----------------------------------------------------------------------------
-- (a) "uma regra esta propondo besteira"
--     -> NAO derrube o schema. APOSENTE a versao:
--          UPDATE public.trafego_regra_otimizacao
--             SET retirada_em = now(), retirada_por = '<quem>',
--                 retirada_motivo = '<por que>'
--           WHERE chave = '<chave>' AND retirada_em IS NULL;
--        A regra sai de `trafego_regra_vigente` na hora, as propostas antigas
--        continuam explicadas, e o historico fica.
--
-- (b) "o gatilho recusou minha proposta e eu preciso dela"
--     -> ELE ESTA CERTO em pelo menos um dos cinco motivos que ele mede
--        (evidencia insuficiente, evidencia velha, limite percentual, limite
--        absoluto, teto de orcamento). A saida e publicar uma VERSAO NOVA da
--        regra com o limite que voce de fato quer — declarado, com responsavel
--        e data —, e nao desligar a guarda.
--
-- (c) "a carencia esta travando uma correcao urgente"
--     -> A carencia e por (regra_chave, alvo_chave). Uma correcao urgente que
--        nao pode esperar e uma alteracao MANUAL na plataforma, registrada como
--        tal — nao uma aplicacao da regra por cima da propria carencia.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION
      'v10_02_rollback deve rodar como postgres ou supabase_admin; papel atual: %',
      current_user;
  END IF;

  IF to_regclass('public.trafego_regra_otimizacao') IS NULL THEN
    RAISE EXCEPTION
      'rollback abortado: trafego_regra_otimizacao nao existe. A v10_02 nao esta aplicada, e nao ha o que reverter.';
  END IF;

  RAISE NOTICE 'v10_02_rollback: derrubando a autogestao criada pela v10_02';
END
$guarda$;

DROP VIEW IF EXISTS public.trafego_proposta_painel;
DROP VIEW IF EXISTS public.trafego_cooldown_ativo;
DROP VIEW IF EXISTS public.trafego_regra_vigente;

-- Ordem inversa da dependencia. Sem CASCADE.
-- `trafego_atuacao_reversao` sai ANTES de `trafego_acompanhamento` porque ela o
-- referencia — e nao antes de `trafego_aplicacao`, que ambos referenciam.
DROP TABLE IF EXISTS public.trafego_cooldown;
DROP TABLE IF EXISTS public.trafego_atuacao_reversao;
DROP TABLE IF EXISTS public.trafego_acompanhamento;
DROP TABLE IF EXISTS public.trafego_aplicacao;
DROP TABLE IF EXISTS public.trafego_aprovacao;
DROP TABLE IF EXISTS public.trafego_proposta;
DROP TABLE IF EXISTS public.trafego_diagnostico;
DROP TABLE IF EXISTS public.trafego_evidencia;
DROP TABLE IF EXISTS public.trafego_regra_otimizacao;

DROP FUNCTION IF EXISTS public.trafego_regra_so_aposenta();
DROP FUNCTION IF EXISTS public.trafego_proposta_respeita_regra();
DROP FUNCTION IF EXISTS public.trafego_proposta_diff_imutavel();
DROP FUNCTION IF EXISTS public.trafego_aplicacao_exige_aprovacao();
DROP FUNCTION IF EXISTS public.trafego_aplicacao_fecha_uma_vez();
DROP FUNCTION IF EXISTS public.trafego_aplicacao_abre_cooldown();
DROP FUNCTION IF EXISTS public.trafego_autogestao_append_only();
DROP FUNCTION IF EXISTS public.trafego_evidencia_so_avalia();
DROP FUNCTION IF EXISTS public.trafego_reversao_fecha_uma_vez();

DO $verifica$
DECLARE
  sobrou text;
BEGIN
  SELECT string_agg(t, ', ' ORDER BY t) INTO sobrou
    FROM unnest(ARRAY[
      'trafego_regra_otimizacao', 'trafego_evidencia', 'trafego_diagnostico',
      'trafego_proposta', 'trafego_aprovacao', 'trafego_aplicacao',
      'trafego_acompanhamento', 'trafego_atuacao_reversao', 'trafego_cooldown',
      'trafego_regra_vigente', 'trafego_cooldown_ativo', 'trafego_proposta_painel'
    ]) AS t
   WHERE to_regclass('public.' || t) IS NOT NULL;
  IF sobrou IS NOT NULL THEN
    RAISE EXCEPTION 'v10_02_rollback: sobrou de pe: %', sobrou;
  END IF;

  SELECT string_agg(p.proname, ', ' ORDER BY p.proname) INTO sobrou
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = 'public'
     AND p.proname IN (
       'trafego_regra_so_aposenta', 'trafego_proposta_respeita_regra',
       'trafego_proposta_diff_imutavel', 'trafego_aplicacao_exige_aprovacao',
       'trafego_aplicacao_fecha_uma_vez', 'trafego_aplicacao_abre_cooldown',
       'trafego_autogestao_append_only', 'trafego_evidencia_so_avalia',
       'trafego_reversao_fecha_uma_vez');
  IF sobrou IS NOT NULL THEN
    RAISE EXCEPTION 'v10_02_rollback: funcao de gatilho sobrou: %', sobrou;
  END IF;

  -- A v9 tem de continuar inteira. Nenhum DROP daqui a alcanca — e a
  -- conferencia existe para que um `CASCADE` acidental numa versao futura nao
  -- passe despercebido.
  IF to_regclass('public.trafego_campanha') IS NULL
     OR to_regclass('public.trafego_inventario_campanha') IS NULL THEN
    RAISE EXCEPTION
      'v10_02_rollback: o inventario da v9 foi afetado. Isto nao deveria ser possivel.';
  END IF;

  RAISE NOTICE 'v10_02_rollback: schema limpo; v9 e v10_01 continuam intactas';
END
$verifica$;

COMMIT;
