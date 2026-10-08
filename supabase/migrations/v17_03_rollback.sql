-- =============================================================================
-- v17_03 ROLLBACK — devolve a trava 4a da v10_02 e apaga `operacoes_sem_delta`
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin
--
-- ⚠️ RECUSA SE A v17_03 JÁ FOI USADA. Duas formas de uso, e as duas param aqui:
--
--   1. Existe proposta SEM delta nenhum (`delta_pct` e `delta_absoluto_micros`
--      nulos). Sob a v10_02 ela é impossível — toda regra declara limite, e a
--      trava 4a recusa proposta sem delta em qualquer combinação de limites —,
--      então cada linha dessas só existe porque a v17_03 a autorizou. Apagar a
--      coluna deixaria a proposta citando uma regra que, pelo schema de volta,
--      nunca a teria permitido: "por que pausamos em 12/10?" perderia a resposta.
--   2. Existe regra com `operacoes_sem_delta` diferente de `{}`. A regra é
--      imutável (v10_02); apagar a coluna reescreveria o que uma versão
--      PUBLICADA autorizava.
--
-- Nesses casos o caminho não é desfazer o schema: é aposentar a regra
-- (`retirada_em`) e publicar a versão seguinte com `operacoes_sem_delta = {}`.
--
-- O QUE VOLTA: o corpo de `trafego_proposta_respeita_regra()` é o da v10_02,
-- copiado verbatim, e a verificação confere o md5 do `prosrc` contra o medido
-- antes da v17_03 (23acf5c85b5e23eb172db94f540c15f6) — volta byte a byte, ou o
-- rollback aborta. A view `trafego_regra_vigente` precisa ser RECRIADA (OR
-- REPLACE não remove coluna), com os mesmos grants e comentário da v10_02.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guarda_rb$
DECLARE
  propostas bigint;
  regras    text;
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'rollback v17_03 deve rodar como postgres ou supabase_admin; papel atual: %',
      current_user;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'public' AND table_name = 'trafego_regra_otimizacao'
                    AND column_name = 'operacoes_sem_delta') THEN
    RAISE EXCEPTION 'rollback v17_03: a v17_03 nao esta aplicada (operacoes_sem_delta nao existe)';
  END IF;

  SELECT count(*) INTO propostas
    FROM public.trafego_proposta
   WHERE delta_pct IS NULL AND delta_absoluto_micros IS NULL;
  IF propostas > 0 THEN
    RAISE EXCEPTION
      'rollback v17_03 recusado: % proposta(s) sem delta existem, e so a v17_03 as permite. Aposente a regra e publique a versao seguinte com operacoes_sem_delta = {} em vez de apagar o historico.',
      propostas;
  END IF;

  SELECT string_agg(chave || '@' || versao, ', ' ORDER BY chave, versao) INTO regras
    FROM public.trafego_regra_otimizacao
   WHERE operacoes_sem_delta <> '{}'::jsonb;
  IF regras IS NOT NULL THEN
    RAISE EXCEPTION
      'rollback v17_03 recusado: a(s) regra(s) % declaram operacoes_sem_delta. Regra publicada e imutavel; apagar a coluna reescreveria o que ela autorizava.',
      regras;
  END IF;

  RAISE NOTICE 'rollback v17_03: guardas ok (nenhuma proposta sem delta, nenhuma regra declarando operacoes_sem_delta)';
END
$guarda_rb$;


-- 1. A trava 4a da v10_02, VERBATIM (supabase/migrations/v10_02_autogestao.sql, 10.2).
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

COMMENT ON FUNCTION public.trafego_proposta_respeita_regra() IS
  'Recusa proposta sem evidencia suficiente, com evidencia velha, ou que estoure limite de alteracao ou teto de orcamento da regra citada.';


-- 2. A coluna e o que a defendia. A view (`SELECT r.*`) depende da coluna, e
--    OR REPLACE nao remove coluna de view: DROP antes, CREATE depois, com os
--    grants e o comentario da v10_02.
DROP VIEW public.trafego_regra_vigente;
DROP TRIGGER trafego_regra_operacoes_sem_delta_guarda ON public.trafego_regra_otimizacao;
DROP FUNCTION public.trafego_regra_operacoes_sem_delta_guarda();
ALTER TABLE public.trafego_regra_otimizacao
  DROP CONSTRAINT trafego_regra_operacoes_sem_delta_validas;
ALTER TABLE public.trafego_regra_otimizacao DROP COLUMN operacoes_sem_delta;

CREATE VIEW public.trafego_regra_vigente
  WITH (security_invoker = true) AS
SELECT r.*
  FROM public.trafego_regra_otimizacao r
 WHERE r.vigente_desde IS NOT NULL AND r.retirada_em IS NULL;

COMMENT ON VIEW public.trafego_regra_vigente IS
  'As regras que valem AGORA. Uma por chave, garantido por trafego_regra_vigente_ux.';

REVOKE ALL ON TABLE public.trafego_regra_vigente FROM PUBLIC;
REVOKE ALL ON TABLE public.trafego_regra_vigente FROM anon;
REVOKE ALL ON TABLE public.trafego_regra_vigente FROM authenticated;
REVOKE ALL ON TABLE public.trafego_regra_vigente FROM service_role;
GRANT SELECT ON TABLE public.trafego_regra_vigente TO service_role;


-- 3. As auxiliares (a CHECK que as chamava ja saiu).
DROP FUNCTION public.trafego_proposta_sem_delta_defeito(jsonb, text, text, jsonb, jsonb);
DROP FUNCTION public.trafego_operacoes_sem_delta_defeito(jsonb);
DROP FUNCTION public.trafego_sem_delta_numero_entre(jsonb, numeric, numeric, boolean);
DROP FUNCTION public.trafego_sem_delta_lista_valida(jsonb, text[]);
DROP FUNCTION public.trafego_recomendacao_monetaria(text);
DROP FUNCTION public.trafego_operacao_sem_delta_classe(text);


-- 4. VERIFICACAO: volta byte a byte, ou nao volta.
DO $verifica_rb$
DECLARE
  corpo text;
BEGIN
  SELECT md5(p.prosrc) INTO corpo
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = 'public' AND p.proname = 'trafego_proposta_respeita_regra';
  IF corpo IS DISTINCT FROM '23acf5c85b5e23eb172db94f540c15f6' THEN
    RAISE EXCEPTION 'rollback v17_03: o corpo restaurado nao e o da v10_02 (md5 %)', corpo;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name IN ('trafego_regra_otimizacao', 'trafego_regra_vigente')
                AND column_name = 'operacoes_sem_delta') THEN
    RAISE EXCEPTION 'rollback v17_03: operacoes_sem_delta ainda existe';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname IN (
               'trafego_operacao_sem_delta_classe', 'trafego_recomendacao_monetaria',
               'trafego_sem_delta_lista_valida', 'trafego_sem_delta_numero_entre',
               'trafego_operacoes_sem_delta_defeito', 'trafego_proposta_sem_delta_defeito',
               'trafego_regra_operacoes_sem_delta_guarda')) THEN
    RAISE EXCEPTION 'rollback v17_03: sobrou funcao da v17_03';
  END IF;
  IF NOT (SELECT coalesce(bool_or(option_value = 'true'), false)
            FROM pg_class c, pg_options_to_table(c.reloptions)
           WHERE c.oid = 'public.trafego_regra_vigente'::regclass
             AND option_name = 'security_invoker') THEN
    RAISE EXCEPTION 'rollback v17_03: trafego_regra_vigente voltou sem security_invoker';
  END IF;
  IF has_table_privilege('anon', 'public.trafego_regra_vigente', 'SELECT')
     OR has_table_privilege('authenticated', 'public.trafego_regra_vigente', 'SELECT')
     OR NOT has_table_privilege('service_role', 'public.trafego_regra_vigente', 'SELECT') THEN
    RAISE EXCEPTION 'rollback v17_03: grants de trafego_regra_vigente nao voltaram aos da v10_02';
  END IF;
  RAISE NOTICE 'rollback v17_03: trava 4a da v10_02 restaurada (md5 conferido), coluna e funcoes removidas';
END
$verifica_rb$;

COMMIT;
