-- =============================================================================
-- v17_02 — PROPOSTA: autonomia T2 por operação na autogestão (a máquina aplica)
-- ⚠️ PROPOSTA. NÃO APLICAR. Depende de DECISÃO DO DONO (ADR-11).
-- =============================================================================
-- O nome termina em `.PROPOSTA.sql` para nenhum runner de migration pegá-lo. Se
-- o dono decidir que T2 entra: renomeie para `v17_02_autonomia_gestao.sql`,
-- mova a seção ROLLBACK (fim deste arquivo) para `v17_02_rollback.sql`, ajuste
-- os números marcados com `DECISÃO` e só então aplique (como postgres ou
-- supabase_admin).
--
-- ORDEM: depois da v10_02 (autogestão) e da v17_01. Não toca a v10_01/v10_03.
--
-- -----------------------------------------------------------------------------
-- O QUE A v10_02 PROÍBE HOJE, E COMO ESTA MIGRATION AFROUXA SÓ O NECESSÁRIO
-- -----------------------------------------------------------------------------
-- A v10_02 tem quatro travas de T1. Esta proposta NÃO remove nenhuma:
--
--   1. `trafego_aplicacao.aprovacao_id` NOT NULL com FK  → CONTINUA. Toda
--      aplicação autônoma também aponta para uma linha de `trafego_aprovacao`;
--      a diferença é quem decidiu, que passa a ser COLUNA (`decisor_tipo`).
--   2. `trafego_aplicacao_exige_aprovacao` (decisão = aprovada, mesma proposta,
--      prazo, carência) → CONTINUA, intocado. A autonomia não pula carência.
--   3. `trafego_regra_nivel_conhecido` (só T0/T1) → AMPLIADA para T2, com uma
--      CHECK nova que exige da regra T2 a lista de operações autônomas e um
--      limite percentual MENOR que o de T1.
--   4. `trafego_proposta_respeita_regra` → CONTINUA, intocado.
--
-- E acrescenta duas travas novas:
--
--   5. `trafego_aprovacao_autonoma_exige_t2` — decisor `regra` só é aceito se a
--      regra da proposta for T2, VIGENTE, listar a operação da proposta em
--      `acao->'operacoes_autonomas'`, e se `decidida_por` for exatamente
--      `regra:<chave>@<versao>` da regra citada. Autonomia é por OPERAÇÃO:
--      pausar e dobrar orçamento são riscos diferentes, e uma regra T2 de
--      orçamento não ganha, por tabela, o direito de pausar campanha.
--   6. `trafego_autonomia_suspensao` — o botão vermelho. Uma linha ativa (por
--      conta, ou `*` para todas) faz o gatilho 5 recusar toda decisão autônoma,
--      sem migration, sem deploy, e com autor e motivo registrados.
--
-- O lado do código já tem o ponto único: `backend/app/trafego/gestao/
-- application/autonomia.py` (`NIVEIS_QUE_APLICAM_SEM_HUMANO`, hoje vazio, e
-- `aplica_sem_humano(regra, operacao)`, que confere a mesma lista). Um sem o
-- outro não faz nada: o banco recusa decisor `regra` sem esta migration, e o
-- código não grava decisor `regra` sem o nível na constante.
--
-- -----------------------------------------------------------------------------
-- O QUE FICA PARA A DECISÃO (marcado `DECISÃO` no corpo)
-- -----------------------------------------------------------------------------
--   · o teto do limite percentual de uma regra T2 (proposto: 20%);
--   · se a máquina pode RECUSAR sozinha (proposto: não — decisor `regra` só
--     aprova; recusa autônoma seria a máquina silenciando a si mesma);
--   · `trafego_proposta_painel.proximo_passo` continua dizendo
--     `aguardar_humano` para proposta T2 sem decisão. A view NÃO é reescrita
--     aqui de propósito: ela tem um espelho em Python
--     (`intencao.proximo_passo_da_proposta`) e mudar uma sem a outra faz tela
--     e motor discordarem. Se o dono quiser `aplicar_autonomo` na tela, as
--     duas mudam juntas, copiando a view INTEIRA da v10_02 (CREATE OR REPLACE
--     a partir de resumo apaga guarda em silêncio).
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. GUARDAS
-- -----------------------------------------------------------------------------
DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'v17_02 deve rodar como postgres ou supabase_admin; papel atual: %',
      current_user;
  END IF;
  IF to_regclass('public.trafego_aprovacao') IS NULL
     OR to_regclass('public.trafego_regra_otimizacao') IS NULL THEN
    RAISE EXCEPTION 'v17_02 recusada: a v10_02 (autogestao) nao esta aplicada';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = 'trafego_aprovacao'
                AND column_name = 'decisor_tipo') THEN
    RAISE EXCEPTION 'v17_02 ja parece aplicada: trafego_aprovacao.decisor_tipo existe';
  END IF;
  IF to_regclass('public.trafego_autonomia_suspensao') IS NOT NULL THEN
    RAISE EXCEPTION 'v17_02 ja parece aplicada: trafego_autonomia_suspensao existe';
  END IF;
END
$guarda$;


-- -----------------------------------------------------------------------------
-- 1. T2 no vocabulário — com as condições que a tornam aceitável
-- -----------------------------------------------------------------------------
ALTER TABLE public.trafego_regra_otimizacao
  DROP CONSTRAINT trafego_regra_nivel_conhecido;
ALTER TABLE public.trafego_regra_otimizacao
  ADD CONSTRAINT trafego_regra_nivel_conhecido
  CHECK (nivel_autonomia IN ('T0', 'T1', 'T2'));

-- Uma regra T2 DECLARA o que pode fazer sozinha e mexe pouco de cada vez.
-- `acao` já é imutável depois de publicada (`trafego_regra_so_aposenta` a
-- cobre), então a lista não muda sob uma regra vigente: para ampliar, publica-se
-- a versão seguinte — com nome, data e responsável.
--
-- ⚠️ CASE, e não `typeof = 'array' AND length >= 1`: sem a chave, `typeof` é
-- NULL, o OR inteiro vira NULL — e CHECK que dá NULL PASSA. Foi exatamente o
-- que a verificação da seção 6 pegou no ensaio de 08/10 (T2 sem lista aceita).
-- O CASE também impede `jsonb_array_length` de rodar sobre um não-array.
ALTER TABLE public.trafego_regra_otimizacao
  ADD CONSTRAINT trafego_regra_t2_declara_operacoes
  CHECK (
    nivel_autonomia <> 'T2'
    OR CASE WHEN jsonb_typeof(acao -> 'operacoes_autonomas') = 'array'
            THEN jsonb_array_length(acao -> 'operacoes_autonomas') >= 1
            ELSE false END
  );

-- DECISÃO: 20% é a proposta. Uma regra T2 sem limite percentual, ou com um
-- limite maior que o de qualquer ajuste que um humano faria sem olhar, é uma
-- autorização ilimitada esperando um bug de sinal.
ALTER TABLE public.trafego_regra_otimizacao
  ADD CONSTRAINT trafego_regra_t2_limite_menor
  CHECK (nivel_autonomia <> 'T2'
         OR (limite_alteracao_pct IS NOT NULL AND limite_alteracao_pct <= 20));

COMMENT ON COLUMN public.trafego_regra_otimizacao.nivel_autonomia IS
  'T0 observa, T1 recomenda, T2 aplica SOZINHA as operacoes listadas em acao->operacoes_autonomas (v17_02). Ver trafego_aprovacao_autonoma_exige_t2.';


-- -----------------------------------------------------------------------------
-- 2. Quem decidiu vira COLUNA — e não um prefixo de texto
-- -----------------------------------------------------------------------------
-- `ADD COLUMN ... DEFAULT` não dispara o gatilho append-only (não é UPDATE de
-- linha), e o DEFAULT 'humano' é a verdade de toda linha anterior: até aqui só
-- humano decidia.
ALTER TABLE public.trafego_aprovacao
  ADD COLUMN decisor_tipo text NOT NULL DEFAULT 'humano';

ALTER TABLE public.trafego_aprovacao
  ADD CONSTRAINT trafego_aprovacao_decisor_conhecido
  CHECK (decisor_tipo IN ('humano', 'regra'));

-- O texto e a coluna não podem se contradizer: uma linha `humano` assinada
-- `regra:...` (ou o contrário) faria "quem autorizou este gasto" ter duas
-- respostas.
ALTER TABLE public.trafego_aprovacao
  ADD CONSTRAINT trafego_aprovacao_decisor_coerente
  CHECK (
    (decisor_tipo = 'regra'
      AND decidida_por ~ '^regra:[a-z][a-z0-9_]{2,63}@[0-9]+$')
    OR (decisor_tipo = 'humano' AND decidida_por !~ '^regra:')
  );

-- DECISÃO: a máquina só APROVA. Recusa autônoma seria a regra silenciando as
-- próprias propostas sem ninguém ver; a recusa continua sendo humana.
ALTER TABLE public.trafego_aprovacao
  ADD CONSTRAINT trafego_aprovacao_regra_so_aprova
  CHECK (decisor_tipo <> 'regra' OR decisao = 'aprovada');

COMMENT ON COLUMN public.trafego_aprovacao.decisor_tipo IS
  'humano = decisao de pessoa (T1). regra = decisao autonoma de regra T2 (v17_02), so aceita por trafego_aprovacao_autonoma_exige_t2.';


-- -----------------------------------------------------------------------------
-- 3. O botão vermelho — suspensão da autonomia, por conta ou geral
-- -----------------------------------------------------------------------------
CREATE TABLE public.trafego_autonomia_suspensao (
  suspensao_id   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  -- '*' suspende todas as contas; senão, o customer_id da conta.
  conta_externa  text        NOT NULL,
  suspensa_em    timestamptz NOT NULL DEFAULT now(),
  suspensa_por   text        NOT NULL,
  motivo         text        NOT NULL,
  retomada_em    timestamptz,
  retomada_por   text,

  CONSTRAINT trafego_autonomia_conta_valida
    CHECK (conta_externa = '*' OR conta_externa ~ '^[0-9]{6,12}$'),
  CONSTRAINT trafego_autonomia_autor_nao_vazio CHECK (btrim(suspensa_por) <> ''),
  CONSTRAINT trafego_autonomia_motivo_nao_vazio CHECK (btrim(motivo) <> ''),
  CONSTRAINT trafego_autonomia_retomada_completa
    CHECK ((retomada_em IS NULL AND retomada_por IS NULL)
           OR (retomada_em IS NOT NULL AND btrim(coalesce(retomada_por, '')) <> ''
               AND retomada_em >= suspensa_em))
);

CREATE INDEX trafego_autonomia_suspensao_ativa_ix
  ON public.trafego_autonomia_suspensao (conta_externa)
  WHERE retomada_em IS NULL;

-- Suspensão é histórico: só a retomada muda, e uma vez.
CREATE OR REPLACE FUNCTION public.trafego_autonomia_suspensao_so_retoma()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'trafego_autonomia_suspensao: DELETE recusado; retome com retomada_em.'
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.suspensao_id IS DISTINCT FROM OLD.suspensao_id
     OR NEW.conta_externa IS DISTINCT FROM OLD.conta_externa
     OR NEW.suspensa_em IS DISTINCT FROM OLD.suspensa_em
     OR NEW.suspensa_por IS DISTINCT FROM OLD.suspensa_por
     OR NEW.motivo IS DISTINCT FROM OLD.motivo
     OR OLD.retomada_em IS NOT NULL THEN
    RAISE EXCEPTION 'trafego_autonomia_suspensao: so a retomada muda, e uma vez.'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_autonomia_suspensao_so_retoma
  BEFORE UPDATE OR DELETE ON public.trafego_autonomia_suspensao
  FOR EACH ROW EXECUTE FUNCTION public.trafego_autonomia_suspensao_so_retoma();


-- -----------------------------------------------------------------------------
-- 4. ⚠️ A TRAVA NOVA: decisor `regra` só para T2 vigente, operação listada, sem
--    suspensão. Função NOVA — nenhuma função da v10_02 é reescrita.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trafego_aprovacao_autonoma_exige_t2()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
DECLARE
  pr    public.trafego_proposta%ROWTYPE;
  r     public.trafego_regra_otimizacao%ROWTYPE;
  conta text;
BEGIN
  IF NEW.decisor_tipo IS DISTINCT FROM 'regra' THEN
    RETURN NEW;
  END IF;

  SELECT * INTO pr FROM public.trafego_proposta WHERE proposta_id = NEW.proposta_id;
  SELECT * INTO r  FROM public.trafego_regra_otimizacao WHERE regra_id = pr.regra_id;

  IF r.nivel_autonomia IS DISTINCT FROM 'T2' THEN
    RAISE EXCEPTION
      'trafego_aprovacao: decisao autonoma exige regra T2; a regra % v% e %. A maquina recomenda, o humano aplica.',
      r.chave, r.versao, r.nivel_autonomia
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF r.vigente_desde IS NULL OR r.retirada_em IS NOT NULL THEN
    RAISE EXCEPTION
      'trafego_aprovacao: a regra % v% nao esta vigente; regra aposentada nao decide sozinha.',
      r.chave, r.versao
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NOT ((r.acao -> 'operacoes_autonomas') ? pr.operacao) THEN
    RAISE EXCEPTION
      'trafego_aprovacao: a regra % v% nao lista % em acao->operacoes_autonomas. Autonomia e por operacao.',
      r.chave, r.versao, pr.operacao
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.decidida_por IS DISTINCT FROM ('regra:' || r.chave || '@' || r.versao) THEN
    RAISE EXCEPTION
      'trafego_aprovacao: decisao autonoma assinada % e a regra da proposta e regra:%@%.',
      NEW.decidida_por, r.chave, r.versao
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- A conta sai de `alvo_chave` (`google_ads:<conta>:<nivel>:<alvo>`), que a
  -- v10_02 congela no INSERT da proposta.
  conta := split_part(pr.alvo_chave, ':', 2);
  IF EXISTS (SELECT 1 FROM public.trafego_autonomia_suspensao s
              WHERE s.retomada_em IS NULL AND s.conta_externa IN ('*', conta)) THEN
    RAISE EXCEPTION
      'trafego_aprovacao: autonomia suspensa para a conta % (trafego_autonomia_suspensao). Decida como humano.',
      conta
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_aprovacao_autonoma_exige_t2
  BEFORE INSERT ON public.trafego_aprovacao
  FOR EACH ROW EXECUTE FUNCTION public.trafego_aprovacao_autonoma_exige_t2();

COMMENT ON FUNCTION public.trafego_aprovacao_autonoma_exige_t2() IS
  'v17_02: decisor regra so com regra T2 vigente que lista a operacao, assinatura regra:<chave>@<versao> e sem suspensao ativa.';


-- -----------------------------------------------------------------------------
-- 5. SEGURANÇA — os mesmos defaults da v10_02
-- -----------------------------------------------------------------------------
REVOKE ALL ON TABLE public.trafego_autonomia_suspensao FROM PUBLIC, anon, authenticated, service_role;
ALTER TABLE public.trafego_autonomia_suspensao ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_autonomia_suspensao FORCE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE ON TABLE public.trafego_autonomia_suspensao TO service_role;

REVOKE ALL ON FUNCTION public.trafego_aprovacao_autonoma_exige_t2() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.trafego_autonomia_suspensao_so_retoma() FROM PUBLIC, anon, authenticated, service_role;


-- -----------------------------------------------------------------------------
-- 6. VERIFICAÇÃO NA PRÓPRIA TRANSAÇÃO
-- -----------------------------------------------------------------------------
DO $verifica$
BEGIN
  -- T2 sem lista de operações tem de ser recusada pela CHECK nova.
  BEGIN
    INSERT INTO public.trafego_regra_otimizacao
      (chave, versao, titulo, objetivo, plataformas, canais, janela_minima_dias,
       atraso_conversao_dias, frescor_maximo_horas, amostra_minima_cliques,
       dados_obrigatorios, limite_alteracao_pct, cooldown_horas, confianca_minima,
       condicao_rollback, rollback_janela_horas, responsavel, nivel_autonomia,
       deteccao, acao, declarada_por, fonte)
    VALUES ('prova_t2_sem_lista', 1, 'prova', 'prova', ARRAY['GOOGLE_ADS'], ARRAY['*'],
            7, 0, 6, 30, ARRAY['cliques'], 10, 24, 0.8, 'piorou', 48, 'prova', 'T2',
            '{}'::jsonb, '{}'::jsonb, 'prova', 'prova');
    RAISE EXCEPTION 'v17_02: T2 sem operacoes_autonomas foi aceita';
  EXCEPTION WHEN check_violation THEN NULL;
  END;

  -- T2 com limite acima do teto também.
  BEGIN
    INSERT INTO public.trafego_regra_otimizacao
      (chave, versao, titulo, objetivo, plataformas, canais, janela_minima_dias,
       atraso_conversao_dias, frescor_maximo_horas, amostra_minima_cliques,
       dados_obrigatorios, limite_alteracao_pct, cooldown_horas, confianca_minima,
       condicao_rollback, rollback_janela_horas, responsavel, nivel_autonomia,
       deteccao, acao, declarada_por, fonte)
    VALUES ('prova_t2_limite_alto', 1, 'prova', 'prova', ARRAY['GOOGLE_ADS'], ARRAY['*'],
            7, 0, 6, 30, ARRAY['cliques'], 50, 24, 0.8, 'piorou', 48, 'prova', 'T2',
            '{}'::jsonb, '{"operacoes_autonomas": ["orcamento.diario"]}'::jsonb,
            'prova', 'prova');
    RAISE EXCEPTION 'v17_02: T2 com limite de 50%% foi aceita';
  EXCEPTION WHEN check_violation THEN NULL;
  END;

  IF NOT EXISTS (SELECT 1 FROM pg_trigger
                  WHERE tgname = 'trafego_aprovacao_autonoma_exige_t2') THEN
    RAISE EXCEPTION 'v17_02: gatilho trafego_aprovacao_autonoma_exige_t2 ausente';
  END IF;
  IF EXISTS (SELECT 1 FROM public.trafego_aprovacao WHERE decisor_tipo <> 'humano') THEN
    RAISE EXCEPTION 'v17_02: linha anterior saiu com decisor diferente de humano';
  END IF;
  IF has_table_privilege('anon', 'public.trafego_autonomia_suspensao', 'SELECT')
     OR has_table_privilege('authenticated', 'public.trafego_autonomia_suspensao', 'SELECT') THEN
    RAISE EXCEPTION 'v17_02: anon/authenticated alcancam trafego_autonomia_suspensao';
  END IF;

  RAISE NOTICE 'v17_02: verificacao interna passou (T2 so com lista e limite <= 20%%; decisor regra so via gatilho)';
END
$verifica$;

COMMIT;


-- =============================================================================
-- ROLLBACK (mover para v17_02_rollback.sql quando promovida)
-- =============================================================================
-- Recusa se a autonomia já foi USADA: apagar `decisor_tipo` reescreveria
-- "quem autorizou este gasto" de linhas reais para `humano`, que é falso.
-- Nesse caso o caminho é aposentar as regras T2 (retirada_em) e suspender a
-- autonomia com `conta_externa = '*'`, não desfazer o schema.
--
-- \set ON_ERROR_STOP on
-- BEGIN;
-- DO $guarda_rb$
-- BEGIN
--   IF EXISTS (SELECT 1 FROM public.trafego_aprovacao WHERE decisor_tipo = 'regra') THEN
--     RAISE EXCEPTION 'rollback v17_02 recusado: ha aprovacoes autonomas registradas. Aposente as regras T2 e suspenda a autonomia em vez de apagar o historico.';
--   END IF;
--   IF EXISTS (SELECT 1 FROM public.trafego_regra_otimizacao WHERE nivel_autonomia = 'T2') THEN
--     RAISE EXCEPTION 'rollback v17_02 recusado: ha regras T2 publicadas; a CHECK de volta (T0/T1) as recusaria.';
--   END IF;
-- END
-- $guarda_rb$;
-- DROP TRIGGER IF EXISTS trafego_aprovacao_autonoma_exige_t2 ON public.trafego_aprovacao;
-- DROP FUNCTION IF EXISTS public.trafego_aprovacao_autonoma_exige_t2();
-- ALTER TABLE public.trafego_aprovacao DROP CONSTRAINT IF EXISTS trafego_aprovacao_regra_so_aprova;
-- ALTER TABLE public.trafego_aprovacao DROP CONSTRAINT IF EXISTS trafego_aprovacao_decisor_coerente;
-- ALTER TABLE public.trafego_aprovacao DROP CONSTRAINT IF EXISTS trafego_aprovacao_decisor_conhecido;
-- ALTER TABLE public.trafego_aprovacao DROP COLUMN IF EXISTS decisor_tipo;
-- DROP TRIGGER IF EXISTS trafego_autonomia_suspensao_so_retoma ON public.trafego_autonomia_suspensao;
-- DROP FUNCTION IF EXISTS public.trafego_autonomia_suspensao_so_retoma();
-- DROP TABLE IF EXISTS public.trafego_autonomia_suspensao;
-- ALTER TABLE public.trafego_regra_otimizacao DROP CONSTRAINT IF EXISTS trafego_regra_t2_limite_menor;
-- ALTER TABLE public.trafego_regra_otimizacao DROP CONSTRAINT IF EXISTS trafego_regra_t2_declara_operacoes;
-- ALTER TABLE public.trafego_regra_otimizacao DROP CONSTRAINT trafego_regra_nivel_conhecido;
-- ALTER TABLE public.trafego_regra_otimizacao ADD CONSTRAINT trafego_regra_nivel_conhecido
--   CHECK (nivel_autonomia IN ('T0', 'T1'));
-- COMMENT ON COLUMN public.trafego_regra_otimizacao.nivel_autonomia IS
--   'T0 observa, T1 recomenda. T2 (aplicar sozinha) NAO existe no vocabulario — ADR-11. Entra por migracao, nao por valor esquecido.';
-- COMMIT;
