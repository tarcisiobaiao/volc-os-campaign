-- =============================================================================
-- v17_03 — Gestão: operações SEM DELTA que a regra declara e limita
-- GADS-GESTAO v1. NÃO APLICADO EM PRODUÇÃO.
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin
--
-- ORDEM: DEPOIS da v10_02 (autogestão). Independente da v17_01. Compatível
--        com a v17_02 PROPOSTA (autonomia T2), nas duas ordens: ela não toca
--        `trafego_proposta_respeita_regra`, e esta não toca `trafego_aprovacao`
--        nem `nivel_autonomia` (ver o fim do arquivo).
-- ROLLBACK: supabase/migrations/v17_03_rollback.sql (recusa se já foi usada)
--
-- -----------------------------------------------------------------------------
-- O PROBLEMA, MEDIDO
-- -----------------------------------------------------------------------------
-- A v10_02 obriga toda regra a declarar limite de alteração (CHECK
-- `trafego_regra_tem_limite_alteracao`), e a trava 4a de
-- `trafego_proposta_respeita_regra` recusa a proposta que não trouxe delta.
-- As duas juntas fazem sentido para dinheiro e nenhum para o resto: das 15
-- ações de gestão do Google Ads, só `orcamento.diario` e `lance.alvo` têm
-- "tamanho". As outras 13 — pausar/ativar, trocar estratégia, negativas,
-- listas, exclusão de placement e de IP, agenda, ajustes de lance por
-- dispositivo e hora, aplicar e dispensar recomendação — saíam 409
-- `regra_exige_delta` no backend (commit 27d2163), e o gatilho as recusaria do
-- mesmo jeito.
--
-- Inventar um delta 0 para passar seria abrir exatamente o furo que a 4a
-- fecha: o registro diria que o limite foi conferido, e nada teria sido.
--
-- -----------------------------------------------------------------------------
-- O DESENHO
-- -----------------------------------------------------------------------------
-- A regra passa a DECLARAR, por operação, o que ela autoriza sem delta e com
-- que teto próprio — numa coluna nova, `operacoes_sem_delta jsonb`:
--
--   {"status":           {"status_permitidos": ["PAUSED", "ENABLED"]},
--    "negativa.keyword": {"max_itens": 50, "escopos": ["campanha", "grupo"]},
--    "recomendacao.aplicar": {"tipos_permitidos": ["SITELINK_ASSET"]}, ...}
--
-- Ausente na regra = não autorizada = trava 4a como hoje. O DEFAULT é `{}`:
-- toda regra que já existe continua exatamente como estava.
--
-- O vocabulário é FECHADO e mora aqui, não na regra. Treze operações em seis
-- classes (a classe é do schema; a regra não reclassifica nada):
--
--   status        status
--   estrategia    lance.estrategia
--   ajuste        ajuste.dispositivo, ajuste.horario
--   segmentacao   negativa.keyword, exclusao.placement, exclusao.ip,
--                 programacao.anuncios
--   estrutura     lista.criar, lista.adicionar, lista.anexar
--   recomendacao  recomendacao.aplicar, recomendacao.dispensar
--
-- E os tetos que cada uma aceita (obrigatório em negrito → *):
--
--   status               *status_permitidos ⊆ {ENABLED, PAUSED}, niveis
--   lance.estrategia     *estrategias, teto_micros (tCPA/teto de CPC que vier junto)
--   ajuste.*             *modificador_min, *modificador_max (0 ≤ min ≤ max ≤ 10)
--   negativa.keyword     *max_itens, escopos ⊆ {campanha, grupo}
--   exclusao.placement   *max_itens, escopos ⊆ {campanha, conta}
--   exclusao.ip          *max_itens, escopos ⊆ {campanha, conta}
--   programacao.anuncios *max_itens (criar + remover), modificador_min/_max
--   lista.criar          *max_itens, max_campanhas
--   lista.adicionar      *max_itens
--   lista.anexar         *max_itens (campanhas anexadas)
--   recomendacao.aplicar *tipos_permitidos (nenhum tipo monetário)
--   recomendacao.dispensar tipos_permitidos
--
-- -----------------------------------------------------------------------------
-- AS INVARIANTES, E QUEM AS DEFENDE
-- -----------------------------------------------------------------------------
--  1. Operação monetária não entra na lista. `orcamento.diario` e `lance.alvo`
--     ficam fora do vocabulário: a CHECK recusa a regra que as liste, e elas
--     continuam passando pela trava 4a e pelos limites (3) e (4). NADA do que
--     a v10_02 aceitava fica mais frouxo, e nada que ela recusava passa sem a
--     regra declarar.
--  2. Teto com nome errado é teto que não vale. A CHECK recusa chave
--     desconhecida por operação ("max_iten" seria ignorado em silêncio) e
--     exige os tetos obrigatórios. Sem isso, a regra diria que limita e não
--     limitaria nada.
--  3. REMOVED não é gestão. `status_permitidos` só aceita ENABLED/PAUSED (CHECK),
--     e o gatilho recusa `valor_proposto.status = REMOVED` mesmo assim.
--  4. Recomendação que mexe em verba ou lance (CAMPAIGN_BUDGET, SET_TARGET_CPA,
--     *_OPT_IN de estratégia, tarifas…) não entra por `recomendacao.aplicar`:
--     a CHECK recusa listá-la e o gatilho recusa aplicá-la. Para elas o
--     caminho é `orcamento.diario`/`lance.alvo`, que têm delta, limite e
--     reverso exato.
--  5. Contagem ausente é recusa, não "zero itens". Proposta de lista sem a
--     lista em `valor_proposto` é recusada — um NULL que passasse por um `IF`
--     seria a trava 4a de novo, com outro nome.
--  6. A declaração é imutável. `trafego_regra_so_aposenta` (v10_02) lista as
--     colunas congeladas e não conhece esta; um gatilho próprio congela
--     `operacoes_sem_delta`. Para mudar o que a regra autoriza, publica-se a
--     versão seguinte — com nome, data e responsável.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTA MIGRATION REESCREVE DA v10_02, E COMO
-- -----------------------------------------------------------------------------
-- Uma função: `trafego_proposta_respeita_regra()`. O corpo foi COPIADO da
-- v10_02 (e conferido contra o banco vivo: md5 do `prosrc` idêntico), e a única
-- mudança é a trava 4a ganhar um ramo IF/ELSE — o ELSE é o texto original.
-- A guarda abaixo recusa rodar se o corpo vivo não for o da v10_02 (alguém já
-- o mudou: CREATE OR REPLACE por cima apagaria a mudança em silêncio), e a
-- verificação no fim procura a CONDIÇÃO de cada trava preservada no `prosrc`
-- novo, e não a mensagem.
--
-- E a view `trafego_regra_vigente` (`SELECT r.*`): o `*` foi expandido quando
-- a view nasceu, então ela não veria a coluna nova — e é por ela que o backend
-- lê a regra. CREATE OR REPLACE com o mesmo texto só acrescenta a coluna no
-- fim; grants, `security_invoker` e comentário ficam.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. GUARDAS
-- -----------------------------------------------------------------------------
DO $guarda$
DECLARE
  faltando text;
  corpo    text;
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION
      'v17_03 deve rodar como postgres ou supabase_admin; papel atual: %', current_user;
  END IF;

  SELECT string_agg(t, ', ' ORDER BY t) INTO faltando
    FROM unnest(ARRAY[
      'trafego_regra_otimizacao', 'trafego_evidencia', 'trafego_diagnostico',
      'trafego_proposta', 'trafego_regra_vigente'
    ]) AS t
   WHERE to_regclass('public.' || t) IS NULL;
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION
      'v17_03 abortada: a v10_02 (autogestao) nao esta aplicada — falta(m) %.', faltando;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_trigger
                  WHERE tgname = 'trafego_proposta_respeita_regra'
                    AND tgrelid = 'public.trafego_proposta'::regclass) THEN
    RAISE EXCEPTION
      'v17_03 abortada: o gatilho trafego_proposta_respeita_regra da v10_02 nao existe. Sem ele nao ha trava 4a para abrir uma excecao.';
  END IF;

  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = 'trafego_regra_otimizacao'
                AND column_name = 'operacoes_sem_delta') THEN
    RAISE EXCEPTION
      'v17_03 ja parece aplicada: trafego_regra_otimizacao.operacoes_sem_delta existe. Rode v17_03_rollback.sql antes de reaplicar.';
  END IF;

  -- ⚠️ O corpo vivo tem de ser o da v10_02. md5 do `prosrc` medido em
  -- 08/10/2026 no espelho e no banco de producao (iguais). Se mudou, alguem
  -- reescreveu a funcao depois da v10_02 — e esta migration, que a substitui
  -- inteira, apagaria essa mudanca sem ninguem ver.
  SELECT md5(p.prosrc) INTO corpo
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = 'public' AND p.proname = 'trafego_proposta_respeita_regra';
  IF corpo IS DISTINCT FROM '23acf5c85b5e23eb172db94f540c15f6' THEN
    RAISE EXCEPTION
      'v17_03 abortada: o corpo de trafego_proposta_respeita_regra() nao e o da v10_02 (md5 %). Leia a versao viva e refaca esta migration a partir DELA.',
      corpo;
  END IF;

  RAISE NOTICE 'v17_03: guardas ok (papel=%, v10_02 presente, corpo da trava 4a conferido)',
    current_user;
END
$guarda$;


-- -----------------------------------------------------------------------------
-- 1. O VOCABULÁRIO — fechado, no schema, e não na regra
-- -----------------------------------------------------------------------------
-- NULL = não é operação sem delta. É o NULL que a CHECK recusa: operação
-- monetária, operação inventada e operação com erro de digitação caem todas
-- aqui, pelo mesmo motivo — ninguém declarou o que ela faz sem tamanho.
CREATE FUNCTION public.trafego_operacao_sem_delta_classe(operacao text)
RETURNS text
LANGUAGE sql
IMMUTABLE PARALLEL SAFE
AS $funcao$
  SELECT CASE operacao
    WHEN 'status'                 THEN 'status'
    WHEN 'lance.estrategia'       THEN 'estrategia'
    WHEN 'ajuste.dispositivo'     THEN 'ajuste'
    WHEN 'ajuste.horario'         THEN 'ajuste'
    WHEN 'negativa.keyword'       THEN 'segmentacao'
    WHEN 'exclusao.placement'     THEN 'segmentacao'
    WHEN 'exclusao.ip'            THEN 'segmentacao'
    WHEN 'programacao.anuncios'   THEN 'segmentacao'
    WHEN 'lista.criar'            THEN 'estrutura'
    WHEN 'lista.adicionar'        THEN 'estrutura'
    WHEN 'lista.anexar'           THEN 'estrutura'
    WHEN 'recomendacao.aplicar'   THEN 'recomendacao'
    WHEN 'recomendacao.dispensar' THEN 'recomendacao'
  END
$funcao$;

COMMENT ON FUNCTION public.trafego_operacao_sem_delta_classe(text) IS
  'v17_03: as 13 operacoes de gestao que nao tem delta, e a classe de cada uma. NULL = fora do vocabulario (inclusive as monetarias, que continuam exigindo delta). Ampliar e por migracao.';


-- Recomendação que mexe em verba, alvo de lance ou estratégia, ou que é
-- tarifa. Por PADRÃO, e não por lista: um `*_CAMPAIGN_BUDGET` novo que o Google
-- crie amanhã cai aqui sem migration. Tipos medidos no enum
-- RecommendationTypeEnum da v25 (lib google-ads 33.0).
CREATE FUNCTION public.trafego_recomendacao_monetaria(tipo text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE PARALLEL SAFE
AS $funcao$
  SELECT coalesce(tipo, '') ~ '(BUDGET|TARGET_CPA|TARGET_ROAS|MAXIMIZE_|ENHANCED_CPC|_FEE$|OPERATING_C)'
$funcao$;

COMMENT ON FUNCTION public.trafego_recomendacao_monetaria(text) IS
  'v17_03: recomendacao que mexe em verba/lance/estrategia ou e tarifa. Nao entra por recomendacao.aplicar — o caminho e orcamento.diario/lance.alvo, que tem delta e limite.';


-- Lista JSON de textos: não vazia, sem repetição e, quando há vocabulário,
-- dentro dele. plpgsql e não SQL: `jsonb_array_elements` sobre um não-array
-- levanta erro, e um AND em SQL não garante a ordem de avaliação.
CREATE FUNCTION public.trafego_sem_delta_lista_valida(j jsonb, vocabulario text[])
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE PARALLEL SAFE
AS $funcao$
BEGIN
  IF j IS NULL OR jsonb_typeof(j) IS DISTINCT FROM 'array' OR jsonb_array_length(j) < 1 THEN
    RETURN false;
  END IF;
  IF EXISTS (SELECT 1 FROM jsonb_array_elements(j) e WHERE jsonb_typeof(e) <> 'string') THEN
    RETURN false;
  END IF;
  IF (SELECT count(*) <> count(DISTINCT e) FROM jsonb_array_elements_text(j) e) THEN
    RETURN false;
  END IF;
  IF vocabulario IS NOT NULL
     AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(j) e WHERE e <> ALL (vocabulario)) THEN
    RETURN false;
  END IF;
  RETURN true;
END
$funcao$;


CREATE FUNCTION public.trafego_sem_delta_numero_entre(j jsonb, minimo numeric, maximo numeric,
                                                      inteiro boolean)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE PARALLEL SAFE
AS $funcao$
DECLARE
  v numeric;
BEGIN
  IF j IS NULL OR jsonb_typeof(j) IS DISTINCT FROM 'number' THEN
    RETURN false;
  END IF;
  v := (j #>> '{}')::numeric;
  IF inteiro AND v <> trunc(v) THEN
    RETURN false;
  END IF;
  RETURN v >= minimo AND v <= maximo;
END
$funcao$;


-- -----------------------------------------------------------------------------
-- 2. A DECLARAÇÃO DA REGRA — o que ela autoriza sem delta, e com que teto
-- -----------------------------------------------------------------------------
-- Devolve o DEFEITO em texto (NULL = válida). A CHECK usa `IS NULL`, que nunca
-- é NULL — o erro clássico de CHECK que dá NULL e passa não tem por onde entrar.
CREATE FUNCTION public.trafego_operacoes_sem_delta_defeito(cfg jsonb)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE PARALLEL SAFE
AS $funcao$
DECLARE
  op     text;
  v      jsonb;
  obrig  text[];
  perm   text[];
  sobra  text[];
  falta  text[];
  tipo   text;
BEGIN
  IF cfg IS NULL OR jsonb_typeof(cfg) IS DISTINCT FROM 'object' THEN
    RETURN 'operacoes_sem_delta tem de ser um objeto {operacao: {tetos}}';
  END IF;

  FOR op, v IN SELECT e.key, e.value FROM jsonb_each(cfg) e LOOP
    IF public.trafego_operacao_sem_delta_classe(op) IS NULL THEN
      RETURN format('%s nao e operacao sem delta (vocabulario da v17_03). Operacao monetaria (orcamento.diario, lance.alvo) continua exigindo delta e limite de alteracao', op);
    END IF;
    IF jsonb_typeof(v) IS DISTINCT FROM 'object' THEN
      RETURN format('%s: os tetos tem de ser um objeto ({} quando a operacao nao tem teto obrigatorio)', op);
    END IF;

    obrig := CASE op
      WHEN 'status'                 THEN ARRAY['status_permitidos']
      WHEN 'lance.estrategia'       THEN ARRAY['estrategias']
      WHEN 'ajuste.dispositivo'     THEN ARRAY['modificador_min', 'modificador_max']
      WHEN 'ajuste.horario'         THEN ARRAY['modificador_min', 'modificador_max']
      WHEN 'recomendacao.aplicar'   THEN ARRAY['tipos_permitidos']
      WHEN 'recomendacao.dispensar' THEN ARRAY[]::text[]
      ELSE ARRAY['max_itens']
    END;
    perm := obrig || CASE op
      WHEN 'status'                 THEN ARRAY['niveis']
      WHEN 'lance.estrategia'       THEN ARRAY['teto_micros']
      WHEN 'negativa.keyword'       THEN ARRAY['escopos']
      WHEN 'exclusao.placement'     THEN ARRAY['escopos']
      WHEN 'exclusao.ip'            THEN ARRAY['escopos']
      WHEN 'programacao.anuncios'   THEN ARRAY['modificador_min', 'modificador_max']
      WHEN 'lista.criar'            THEN ARRAY['max_campanhas']
      WHEN 'recomendacao.dispensar' THEN ARRAY['tipos_permitidos']
      ELSE ARRAY[]::text[]
    END;

    -- ⚠️ Teto com nome errado e teto que nao vale: "max_iten" seria ignorado
    -- pelo gatilho e a regra diria que limita sem limitar nada.
    SELECT array_agg(k ORDER BY k) INTO sobra
      FROM jsonb_object_keys(v) AS k WHERE k <> ALL (perm);
    IF sobra IS NOT NULL THEN
      RETURN format('%s: chave(s) desconhecida(s) %s; aceitas: %s', op, sobra, perm);
    END IF;
    SELECT array_agg(k ORDER BY k) INTO falta
      FROM unnest(obrig) AS k WHERE NOT (v ? k);
    IF falta IS NOT NULL THEN
      RETURN format('%s: teto(s) obrigatorio(s) ausente(s): %s', op, falta);
    END IF;

    IF v ? 'max_itens'
       AND NOT public.trafego_sem_delta_numero_entre(v -> 'max_itens', 1, 1000, true) THEN
      RETURN format('%s: max_itens tem de ser inteiro entre 1 e 1000', op);
    END IF;
    IF v ? 'max_campanhas'
       AND NOT public.trafego_sem_delta_numero_entre(v -> 'max_campanhas', 1, 1000, true) THEN
      RETURN format('%s: max_campanhas tem de ser inteiro entre 1 e 1000', op);
    END IF;
    IF v ? 'teto_micros'
       AND NOT public.trafego_sem_delta_numero_entre(v -> 'teto_micros', 0, 1000000000000, true) THEN
      RETURN format('%s: teto_micros tem de ser inteiro em micros, >= 0', op);
    END IF;
    IF v ? 'status_permitidos'
       AND NOT public.trafego_sem_delta_lista_valida(v -> 'status_permitidos',
                                                     ARRAY['ENABLED', 'PAUSED']) THEN
      RETURN format('%s: status_permitidos so aceita ENABLED e PAUSED, sem repetir. REMOVED nao e gestao: e terminal e tem funil proprio', op);
    END IF;
    IF v ? 'niveis'
       AND NOT public.trafego_sem_delta_lista_valida(v -> 'niveis',
                 ARRAY['campanha', 'grupo', 'anuncio', 'asset_group']) THEN
      RETURN format('%s: niveis so aceita campanha, grupo, anuncio, asset_group', op);
    END IF;
    IF v ? 'escopos'
       AND NOT public.trafego_sem_delta_lista_valida(v -> 'escopos',
                 CASE op WHEN 'negativa.keyword' THEN ARRAY['campanha', 'grupo']
                         ELSE ARRAY['campanha', 'conta'] END) THEN
      RETURN format('%s: escopos fora do vocabulario da operacao', op);
    END IF;
    IF v ? 'estrategias'
       AND NOT public.trafego_sem_delta_lista_valida(v -> 'estrategias',
                 ARRAY['MANUAL_CPC', 'TARGET_SPEND', 'MAXIMIZE_CONVERSIONS',
                       'MAXIMIZE_CONVERSION_VALUE', 'PORTFOLIO']) THEN
      RETURN format('%s: estrategias so aceita MANUAL_CPC, TARGET_SPEND, MAXIMIZE_CONVERSIONS, MAXIMIZE_CONVERSION_VALUE, PORTFOLIO', op);
    END IF;
    IF v ? 'tipos_permitidos' THEN
      IF NOT public.trafego_sem_delta_lista_valida(v -> 'tipos_permitidos', NULL) THEN
        RETURN format('%s: tipos_permitidos tem de ser lista nao vazia de tipos, sem repetir', op);
      END IF;
      FOR tipo IN SELECT jsonb_array_elements_text(v -> 'tipos_permitidos') LOOP
        IF tipo !~ '^[A-Z][A-Z0-9_]*$' THEN
          RETURN format('%s: %s nao e um RecommendationType', op, tipo);
        END IF;
        IF public.trafego_recomendacao_monetaria(tipo) THEN
          RETURN format('%s: %s mexe em verba, lance ou estrategia — use orcamento.diario/lance.alvo, que tem delta e limite', op, tipo);
        END IF;
      END LOOP;
    END IF;
    IF (v ? 'modificador_min') <> (v ? 'modificador_max') THEN
      RETURN format('%s: modificador_min e modificador_max andam juntos', op);
    END IF;
    IF v ? 'modificador_min' THEN
      IF NOT public.trafego_sem_delta_numero_entre(v -> 'modificador_min', 0, 10, false)
         OR NOT public.trafego_sem_delta_numero_entre(v -> 'modificador_max', 0, 10, false)
         OR (v ->> 'modificador_min')::numeric > (v ->> 'modificador_max')::numeric THEN
        RETURN format('%s: modificadores fora de 0 <= min <= max <= 10', op);
      END IF;
    END IF;
  END LOOP;

  RETURN NULL;
END
$funcao$;

COMMENT ON FUNCTION public.trafego_operacoes_sem_delta_defeito(jsonb) IS
  'v17_03: por que uma declaracao operacoes_sem_delta e invalida (NULL = valida). Usada pela CHECK trafego_regra_operacoes_sem_delta_validas.';


ALTER TABLE public.trafego_regra_otimizacao
  ADD COLUMN operacoes_sem_delta jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE public.trafego_regra_otimizacao
  ADD CONSTRAINT trafego_regra_operacoes_sem_delta_validas
  CHECK (public.trafego_operacoes_sem_delta_defeito(operacoes_sem_delta) IS NULL);

COMMENT ON COLUMN public.trafego_regra_otimizacao.operacoes_sem_delta IS
  'v17_03: {operacao: {tetos}} — as operacoes de gestao SEM delta que esta regra autoriza, cada uma com teto proprio. {} = nenhuma (trava 4a da v10_02 como sempre). Monetarias nao entram. Imutavel.';


-- 2.1 A declaração é imutável e, quando inválida, diz POR QUÊ.
--
-- A CHECK acima é a invariante (não se desliga com DISABLE TRIGGER); este
-- gatilho é a explicação: sem ele, quem publica a regra recebe só o nome da
-- constraint e tem de adivinhar qual teto errou.
CREATE FUNCTION public.trafego_regra_operacoes_sem_delta_guarda()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
DECLARE
  defeito text;
BEGIN
  IF TG_OP = 'UPDATE'
     AND NEW.operacoes_sem_delta IS DISTINCT FROM OLD.operacoes_sem_delta THEN
    RAISE EXCEPTION
      'trafego_regra_otimizacao: operacoes_sem_delta e imutavel (v17_03). Para mudar o que a regra % autoriza sem delta, publique (chave, versao+1) e aposente esta.',
      OLD.chave
      USING ERRCODE = 'restrict_violation';
  END IF;

  defeito := public.trafego_operacoes_sem_delta_defeito(NEW.operacoes_sem_delta);
  IF defeito IS NOT NULL THEN
    RAISE EXCEPTION 'trafego_regra_otimizacao: operacoes_sem_delta invalida na regra %: %',
      NEW.chave, defeito
      USING ERRCODE = 'check_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

CREATE TRIGGER trafego_regra_operacoes_sem_delta_guarda
  BEFORE INSERT OR UPDATE ON public.trafego_regra_otimizacao
  FOR EACH ROW EXECUTE FUNCTION public.trafego_regra_operacoes_sem_delta_guarda();


-- -----------------------------------------------------------------------------
-- 3. O TETO PRÓPRIO DE CADA OPERAÇÃO, conferido no INSERT da proposta
-- -----------------------------------------------------------------------------
-- Lê o `valor_proposto` exatamente como `volc_ads/gestao/acoes.py`
-- (`Acao.valor_proposto()`) o escreve — o espelho em Python é
-- `backend/app/trafego/gestao/application/sem_delta.py`. Devolve o defeito
-- (NULL = cabe no teto).
--
-- ⚠️ Toda leitura ausente RECUSA. `jsonb ? NULL` é NULL, `NOT NULL` é NULL, e
-- `IF NULL` não entra: cada teste abaixo usa `coalesce(..., false)` ou
-- `IS DISTINCT FROM` para que "não consegui ler" vire recusa, e não passagem.
CREATE FUNCTION public.trafego_proposta_sem_delta_defeito(
  cfg jsonb, operacao text, alvo_nivel text, atual jsonb, proposto jsonb)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE PARALLEL SAFE
AS $funcao$
DECLARE
  valor   text;
  campo   text;
  n       integer;
  m       jsonb;
  janela  jsonb;
BEGIN
  IF cfg IS NULL OR jsonb_typeof(cfg) IS DISTINCT FROM 'object' THEN
    RETURN format('a regra nao declara %s entre as operacoes sem delta', operacao);
  END IF;
  IF proposto IS NULL OR jsonb_typeof(proposto) IS DISTINCT FROM 'object' THEN
    RETURN 'valor_proposto ausente';
  END IF;

  CASE operacao
  WHEN 'status' THEN
    valor := proposto ->> 'status';
    IF valor IS NULL THEN
      RETURN 'valor_proposto.status ausente';
    END IF;
    IF valor = 'REMOVED' THEN
      RETURN 'REMOVED nao e gestao: e terminal, nao tem reverso e tem funil proprio';
    END IF;
    IF NOT coalesce((cfg -> 'status_permitidos') ? valor, false) THEN
      RETURN format('status %s fora de status_permitidos %s', valor, cfg -> 'status_permitidos');
    END IF;
    IF cfg ? 'niveis' AND NOT coalesce((cfg -> 'niveis') ? alvo_nivel, false) THEN
      RETURN format('nivel %s fora de niveis %s', coalesce(alvo_nivel, '(nenhum)'), cfg -> 'niveis');
    END IF;

  WHEN 'lance.estrategia' THEN
    valor := proposto ->> 'estrategia';
    IF valor IS NULL THEN
      RETURN 'valor_proposto.estrategia ausente';
    END IF;
    IF NOT coalesce((cfg -> 'estrategias') ? valor, false) THEN
      RETURN format('estrategia %s fora de estrategias %s', valor, cfg -> 'estrategias');
    END IF;
    IF cfg ? 'teto_micros' THEN
      FOREACH campo IN ARRAY ARRAY['tcpa_micros', 'teto_cpc_micros'] LOOP
        IF proposto ? campo THEN
          IF jsonb_typeof(proposto -> campo) IS DISTINCT FROM 'number' THEN
            RETURN format('%s nao e numero', campo);
          END IF;
          IF (proposto ->> campo)::numeric > (cfg ->> 'teto_micros')::numeric THEN
            RETURN format('%s = %s passa do teto_micros %s', campo, proposto ->> campo,
                          cfg ->> 'teto_micros');
          END IF;
        END IF;
      END LOOP;
    END IF;

  WHEN 'ajuste.dispositivo', 'ajuste.horario' THEN
    m := proposto -> 'modificador';
    IF m IS NULL OR jsonb_typeof(m) IS DISTINCT FROM 'number' THEN
      RETURN 'valor_proposto.modificador ausente ou nao numerico';
    END IF;
    IF (m #>> '{}')::numeric < (cfg ->> 'modificador_min')::numeric
       OR (m #>> '{}')::numeric > (cfg ->> 'modificador_max')::numeric THEN
      RETURN format('modificador %s fora de [%s, %s]', m, cfg ->> 'modificador_min',
                    cfg ->> 'modificador_max');
    END IF;

  WHEN 'negativa.keyword', 'lista.criar', 'lista.adicionar', 'lista.anexar',
       'exclusao.placement', 'exclusao.ip', 'programacao.anuncios' THEN
    IF operacao = 'programacao.anuncios' THEN
      IF jsonb_typeof(proposto -> 'criar') IS DISTINCT FROM 'array'
         OR jsonb_typeof(proposto -> 'remover') IS DISTINCT FROM 'array' THEN
        RETURN 'valor_proposto sem as listas criar/remover: sem contagem nao ha teto';
      END IF;
      n := jsonb_array_length(proposto -> 'criar') + jsonb_array_length(proposto -> 'remover');
    ELSE
      campo := CASE operacao
        WHEN 'negativa.keyword'   THEN 'adicionar'
        WHEN 'lista.criar'        THEN 'itens'
        WHEN 'lista.adicionar'    THEN 'adicionar'
        WHEN 'lista.anexar'       THEN 'anexar'
        WHEN 'exclusao.placement' THEN 'excluir'
        WHEN 'exclusao.ip'        THEN 'excluir_ips'
      END;
      IF jsonb_typeof(proposto -> campo) IS DISTINCT FROM 'array' THEN
        RETURN format('valor_proposto.%s ausente ou nao e lista: sem contagem nao ha teto', campo);
      END IF;
      n := jsonb_array_length(proposto -> campo);
    END IF;
    IF n < 1 THEN
      RETURN 'proposta sem item nenhum';
    END IF;
    IF n > (cfg ->> 'max_itens')::integer THEN
      RETURN format('%s itens passam do max_itens %s', n, cfg ->> 'max_itens');
    END IF;
    IF cfg ? 'escopos'
       AND NOT coalesce((cfg -> 'escopos') ? (proposto ->> 'escopo'), false) THEN
      RETURN format('escopo %s fora de escopos %s', coalesce(proposto ->> 'escopo', '(nenhum)'),
                    cfg -> 'escopos');
    END IF;
    IF operacao = 'lista.criar' AND cfg ? 'max_campanhas' THEN
      IF jsonb_typeof(proposto -> 'campanhas') IS DISTINCT FROM 'array' THEN
        RETURN 'valor_proposto.campanhas ausente ou nao e lista';
      END IF;
      IF jsonb_array_length(proposto -> 'campanhas') > (cfg ->> 'max_campanhas')::integer THEN
        RETURN format('%s campanhas passam do max_campanhas %s',
                      jsonb_array_length(proposto -> 'campanhas'), cfg ->> 'max_campanhas');
      END IF;
    END IF;
    IF operacao = 'programacao.anuncios' AND cfg ? 'modificador_min' THEN
      FOR janela IN SELECT e FROM jsonb_array_elements(proposto -> 'criar') AS e LOOP
        m := janela -> 'modificador';
        CONTINUE WHEN m IS NULL OR jsonb_typeof(m) = 'null';  -- sem ajuste = 1.0
        IF jsonb_typeof(m) <> 'number'
           OR (m #>> '{}')::numeric < (cfg ->> 'modificador_min')::numeric
           OR (m #>> '{}')::numeric > (cfg ->> 'modificador_max')::numeric THEN
          RETURN format('janela com modificador %s fora de [%s, %s]', m,
                        cfg ->> 'modificador_min', cfg ->> 'modificador_max');
        END IF;
      END LOOP;
    END IF;

  WHEN 'recomendacao.aplicar', 'recomendacao.dispensar' THEN
    -- O tipo vem do "antes" lido na conta (a recomendacao e um resource name
    -- opaco no valor_proposto). Sem ele, nao da para saber se ela mexe em dinheiro.
    valor := atual ->> 'tipo';
    IF operacao = 'recomendacao.aplicar' THEN
      IF valor IS NULL THEN
        RETURN 'valor_atual.tipo ausente: sem o tipo lido nao da para saber se a recomendacao mexe em verba';
      END IF;
      IF public.trafego_recomendacao_monetaria(valor) THEN
        RETURN format('recomendacao %s mexe em verba, lance ou estrategia: monte orcamento.diario/lance.alvo, que tem delta e limite', valor);
      END IF;
    END IF;
    IF cfg ? 'tipos_permitidos'
       AND NOT coalesce((cfg -> 'tipos_permitidos') ? valor, false) THEN
      RETURN format('recomendacao %s fora de tipos_permitidos %s',
                    coalesce(valor, '(tipo nao lido)'), cfg -> 'tipos_permitidos');
    END IF;

  ELSE
    RETURN format('%s nao e operacao sem delta do vocabulario da v17_03', coalesce(operacao, '(nula)'));
  END CASE;

  RETURN NULL;
END
$funcao$;

COMMENT ON FUNCTION public.trafego_proposta_sem_delta_defeito(jsonb, text, text, jsonb, jsonb) IS
  'v17_03: por que uma proposta sem delta passa do teto que a regra declarou para a operacao (NULL = cabe). Espelho em backend/app/trafego/gestao/application/sem_delta.py.';


-- -----------------------------------------------------------------------------
-- 4. A TRAVA 4a GANHA A EXCEÇÃO DECLARADA — o resto da função é a v10_02
-- -----------------------------------------------------------------------------
-- Corpo copiado de supabase/migrations/v10_02_autogestao.sql (seção 10.2),
-- conferido contra o `prosrc` vivo. Mudou: (a) a variável `defeito` no
-- DECLARE; (b) a trava 4a vira IF (exceção declarada) / ELSE (texto original).
CREATE OR REPLACE FUNCTION public.trafego_proposta_respeita_regra()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
DECLARE
  r        public.trafego_regra_otimizacao%ROWTYPE;
  ev       public.trafego_evidencia%ROWTYPE;
  proposto bigint;
  idade    interval;
  defeito  text;
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
  --
  -- ⚠️ v17_03 — A EXCECAO DECLARADA A TRAVA 4a.
  --
  -- Pausar, negativar, excluir placement, mexer na agenda ou aplicar uma
  -- recomendacao nao tem "tamanho em porcentagem": a 4a recusava TODAS essas
  -- operacoes, e a unica saida seria inventar um delta 0 — exatamente o furo
  -- que ela fecha. A saida aqui e a regra DECLARAR, por operacao, o que ela
  -- autoriza sem delta e com que teto proprio (`operacoes_sem_delta`, coluna
  -- imutavel com CHECK de vocabulario). So entra neste ramo a proposta que:
  --   · nao trouxe delta nenhum (as duas colunas nulas); e
  --   · cita uma regra que LISTA aquela operacao.
  -- Todo o resto cai no ELSE, que e a trava 4a da v10_02 INTACTA. Operacao
  -- monetaria (`orcamento.diario`, `lance.alvo`) nao pode ser listada (a CHECK
  -- recusa), entao ela continua exigindo delta e limite como antes.
  IF NEW.delta_pct IS NULL AND NEW.delta_absoluto_micros IS NULL
     AND coalesce(r.operacoes_sem_delta ? NEW.operacao, false) THEN
    defeito := public.trafego_proposta_sem_delta_defeito(
                 r.operacoes_sem_delta -> NEW.operacao, NEW.operacao, NEW.alvo_nivel,
                 NEW.valor_atual, NEW.valor_proposto);
    IF defeito IS NOT NULL THEN
      RAISE EXCEPTION
        'trafego_proposta: a regra % autoriza % sem delta, mas esta proposta passa do teto declarado: %',
        r.chave, NEW.operacao, defeito
        USING ERRCODE = 'restrict_violation';
    END IF;
  ELSE
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
  'Recusa proposta sem evidencia suficiente, com evidencia velha, ou que estoure limite de alteracao ou teto de orcamento da regra citada. v17_03: proposta SEM delta so passa se a regra listar a operacao em operacoes_sem_delta, e dentro do teto declarado.';


-- -----------------------------------------------------------------------------
-- 5. A VIEW QUE O BACKEND LÊ passa a ver a coluna
-- -----------------------------------------------------------------------------
-- Mesmo texto da v10_02; o `r.*` agora expande com `operacoes_sem_delta` no
-- fim. OR REPLACE preserva dono, grants e comentário.
CREATE OR REPLACE VIEW public.trafego_regra_vigente
  WITH (security_invoker = true) AS
SELECT r.*
  FROM public.trafego_regra_otimizacao r
 WHERE r.vigente_desde IS NOT NULL AND r.retirada_em IS NULL;


-- -----------------------------------------------------------------------------
-- 6. SEGURANÇA
-- -----------------------------------------------------------------------------
-- ⚠️ As funções auxiliares PRECISAM de EXECUTE para service_role: a CHECK e o
-- corpo do gatilho as chamam com os privilégios de quem faz o INSERT (os
-- gatilhos aqui não são SECURITY DEFINER). Sem o GRANT, a primeira proposta do
-- backend morreria com "permission denied for function" — que é falha de
-- deploy com cara de recusa de regra.
DO $seguranca$
DECLARE
  f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'public.trafego_operacao_sem_delta_classe(text)',
    'public.trafego_recomendacao_monetaria(text)',
    'public.trafego_sem_delta_lista_valida(jsonb, text[])',
    'public.trafego_sem_delta_numero_entre(jsonb, numeric, numeric, boolean)',
    'public.trafego_operacoes_sem_delta_defeito(jsonb)',
    'public.trafego_proposta_sem_delta_defeito(jsonb, text, text, jsonb, jsonb)'
  ] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM anon', f);
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM authenticated', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', f);
  END LOOP;

  EXECUTE 'REVOKE ALL ON FUNCTION public.trafego_regra_operacoes_sem_delta_guarda() FROM PUBLIC';
  EXECUTE 'REVOKE ALL ON FUNCTION public.trafego_regra_operacoes_sem_delta_guarda() FROM anon';
  EXECUTE 'REVOKE ALL ON FUNCTION public.trafego_regra_operacoes_sem_delta_guarda() FROM authenticated';
  EXECUTE 'REVOKE ALL ON FUNCTION public.trafego_regra_operacoes_sem_delta_guarda() FROM service_role';
END
$seguranca$;


-- -----------------------------------------------------------------------------
-- 7. VERIFICAÇÃO NA PRÓPRIA TRANSAÇÃO
-- -----------------------------------------------------------------------------
DO $verifica$
DECLARE
  corpo   text;
  condicao text;
  rid     uuid;
  eid     uuid;
  did     uuid;
BEGIN
  -- 7.1 As travas da v10_02 continuam no corpo — pela CONDICAO, nao pela
  -- mensagem: um mutante que troca o IF por `IF false` mantem a mensagem.
  SELECT regexp_replace(p.prosrc, '\s+', ' ', 'g') INTO corpo
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = 'public' AND p.proname = 'trafego_proposta_respeita_regra';
  FOREACH condicao IN ARRAY ARRAY[
    'IF ev.suficiencia IS DISTINCT FROM ''suficiente'' THEN',
    'IF NEW.volc_campaign_id IS DISTINCT FROM ev.volc_campaign_id THEN',
    'ELSIF NEW.alvo_nivel = ''campanha'' THEN',
    'IF NEW.alvo_nivel = ''campanha'' AND NEW.volc_campaign_id IS NULL THEN',
    'IF NEW.regra_id IS DISTINCT FROM ( SELECT d.regra_id FROM public.trafego_diagnostico d WHERE d.diagnostico_id = NEW.diagnostico_id) THEN',
    'IF idade > make_interval(hours => r.frescor_maximo_horas) THEN',
    'IF r.limite_alteracao_pct IS NOT NULL AND r.limite_alteracao_absoluto_micros IS NOT NULL AND NEW.delta_pct IS NULL AND NEW.delta_absoluto_micros IS NULL THEN',
    'IF r.limite_alteracao_pct IS NOT NULL AND r.limite_alteracao_absoluto_micros IS NULL AND NEW.delta_pct IS NULL THEN',
    'IF r.limite_alteracao_absoluto_micros IS NOT NULL AND r.limite_alteracao_pct IS NULL AND NEW.delta_absoluto_micros IS NULL THEN',
    'IF NEW.delta_pct IS NOT NULL AND r.limite_alteracao_pct IS NOT NULL AND abs(NEW.delta_pct) > r.limite_alteracao_pct THEN',
    'IF NEW.delta_absoluto_micros IS NOT NULL AND r.limite_alteracao_absoluto_micros IS NOT NULL AND abs(NEW.delta_absoluto_micros) > r.limite_alteracao_absoluto_micros THEN',
    'IF NEW.moeda IS NOT NULL AND NEW.moeda <> r.teto_orcamento_moeda THEN',
    'IF proposto > r.teto_orcamento_micros THEN',
    'IF NEW.delta_pct IS NULL AND NEW.delta_absoluto_micros IS NULL AND coalesce(r.operacoes_sem_delta ? NEW.operacao, false) THEN'
  ] LOOP
    IF position(condicao IN corpo) = 0 THEN
      RAISE EXCEPTION 'v17_03: a condicao "%" sumiu de trafego_proposta_respeita_regra()', condicao;
    END IF;
  END LOOP;

  -- 7.2 Grants: service_role executa as auxiliares; anon/authenticated nao.
  IF NOT has_function_privilege('service_role',
       'public.trafego_proposta_sem_delta_defeito(jsonb, text, text, jsonb, jsonb)', 'EXECUTE')
     OR NOT has_function_privilege('service_role',
       'public.trafego_operacoes_sem_delta_defeito(jsonb)', 'EXECUTE') THEN
    RAISE EXCEPTION 'v17_03: service_role sem EXECUTE nas auxiliares — o INSERT do backend morreria';
  END IF;
  IF has_function_privilege('anon', 'public.trafego_operacoes_sem_delta_defeito(jsonb)', 'EXECUTE')
     OR has_function_privilege('authenticated',
          'public.trafego_proposta_sem_delta_defeito(jsonb, text, text, jsonb, jsonb)', 'EXECUTE') THEN
    RAISE EXCEPTION 'v17_03: anon/authenticated alcancam as auxiliares';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'public' AND table_name = 'trafego_regra_vigente'
                    AND column_name = 'operacoes_sem_delta') THEN
    RAISE EXCEPTION 'v17_03: trafego_regra_vigente nao expoe operacoes_sem_delta';
  END IF;
  IF EXISTS (SELECT 1 FROM public.trafego_regra_otimizacao WHERE operacoes_sem_delta <> '{}'::jsonb) THEN
    RAISE EXCEPTION 'v17_03: regra existente saiu com operacoes_sem_delta diferente de {}';
  END IF;

  -- 7.3 A CHECK recusa o que tem de recusar.
  FOREACH condicao IN ARRAY ARRAY[
    '{"orcamento.diario": {}}',                              -- monetaria
    '{"lance.alvo": {"max_itens": 1}}',                      -- monetaria
    '{"status": {"status_permitidos": ["PAUSED", "REMOVED"]}}',
    '{"status": {}}',                                        -- teto obrigatorio
    '{"negativa.keyword": {"max_iten": 50}}',                -- obrigatorio com erro
    '{"negativa.keyword": {"max_itens": 50, "escopo": ["grupo"]}}',  -- opcional com erro
    '{"exclusao.ip": {"max_itens": 0}}',
    '{"recomendacao.aplicar": {"tipos_permitidos": ["CAMPAIGN_BUDGET"]}}',
    '{"ajuste.horario": {"modificador_min": 1.5, "modificador_max": 0.5}}',
    '[]'
  ] LOOP
    BEGIN
      INSERT INTO public.trafego_regra_otimizacao
        (chave, versao, titulo, objetivo, plataformas, canais, janela_minima_dias,
         atraso_conversao_dias, frescor_maximo_horas, amostra_minima_impressoes,
         dados_obrigatorios, limite_alteracao_pct, cooldown_horas, confianca_minima,
         condicao_rollback, rollback_janela_horas, responsavel, deteccao, acao,
         declarada_por, fonte, operacoes_sem_delta)
      VALUES ('v17_03_prova_check', 1, 'prova', 'prova', ARRAY['GOOGLE_ADS'], ARRAY['*'],
              7, 0, 6, 0, ARRAY['impressoes'], 30, 24, 0.5, 'piorou', 72, 'prova',
              '{}'::jsonb, '{}'::jsonb, 'prova', 'prova', condicao::jsonb);
      RAISE EXCEPTION 'v17_03: a regra com operacoes_sem_delta % foi aceita', condicao;
    EXCEPTION WHEN check_violation THEN
      NULL;  -- e o que se espera
    END;
  END LOOP;

  -- 7.4 O gatilho, ponta a ponta, desfeito no fim (SQLSTATE proprio V1703).
  BEGIN
    INSERT INTO public.trafego_regra_otimizacao
      (chave, versao, titulo, objetivo, plataformas, canais, janela_minima_dias,
       atraso_conversao_dias, frescor_maximo_horas, amostra_minima_impressoes,
       dados_obrigatorios, limite_alteracao_pct, cooldown_horas, confianca_minima,
       condicao_rollback, rollback_janela_horas, responsavel, deteccao, acao,
       declarada_por, fonte, operacoes_sem_delta)
    VALUES ('v17_03_prova_gatilho', 1, 'prova', 'prova', ARRAY['GOOGLE_ADS'], ARRAY['*'],
            7, 0, 6, 0, ARRAY['impressoes'], 30, 24, 0.5, 'piorou', 72, 'prova',
            '{}'::jsonb, '{}'::jsonb, 'prova', 'prova',
            '{"exclusao.ip": {"max_itens": 2, "escopos": ["conta"]}}'::jsonb)
    RETURNING regra_id INTO rid;

    BEGIN
      UPDATE public.trafego_regra_otimizacao SET operacoes_sem_delta = '{}'::jsonb
       WHERE regra_id = rid;
      RAISE EXCEPTION 'v17_03: operacoes_sem_delta foi reescrita numa regra publicada';
    EXCEPTION WHEN restrict_violation THEN NULL;
    END;

    INSERT INTO public.trafego_evidencia
      (regra_id, plataforma, conta_externa, janela_inicio, janela_fim, colhida_em, origem,
       impressoes, suficiencia, suficiencia_em)
    VALUES (rid, 'GOOGLE_ADS', '1234567890', current_date - 8, current_date - 1, now(),
            'v17_03:autoteste', 100, 'suficiente', now())
    RETURNING evidencia_id INTO eid;
    INSERT INTO public.trafego_diagnostico
      (evidencia_id, regra_id, detectado_em, produtor, sintoma, explicacao)
    VALUES (eid, rid, now(), 'v17_03:autoteste', 'prova', 'prova')
    RETURNING diagnostico_id INTO did;

    -- dentro da lista e do teto: nasce
    INSERT INTO public.trafego_proposta
      (diagnostico_id, regra_id, alvo_nivel, alvo_chave, operacao, valor_atual,
       valor_atual_lido_em, valor_proposto, idempotency_key, criada_por, expira_em)
    VALUES (did, rid, 'conta', 'google_ads:1234567890:conta:conta', 'exclusao.ip',
            '{"ips_existentes": []}', now(),
            '{"escopo": "conta", "excluir_ips": ["203.0.113.7", "203.0.113.8"]}',
            'v17_03:autoteste:cabe', 'v17_03', now() + interval '1 hour');

    -- passa do teto, escopo fora, operacao nao listada, monetaria sem delta
    FOREACH condicao IN ARRAY ARRAY[
      'exclusao.ip|{"escopo": "conta", "excluir_ips": ["203.0.113.7", "203.0.113.8", "203.0.113.9"]}',
      'exclusao.ip|{"escopo": "campanha", "excluir_ips": ["203.0.113.7"]}',
      'exclusao.ip|{"escopo": "conta"}',
      'status|{"status": "PAUSED"}',
      'orcamento.diario|{"verba_diaria_micros": 1}'
    ] LOOP
      BEGIN
        INSERT INTO public.trafego_proposta
          (diagnostico_id, regra_id, alvo_nivel, alvo_chave, operacao, valor_atual,
           valor_atual_lido_em, valor_proposto, idempotency_key, criada_por, expira_em)
        VALUES (did, rid, 'conta', 'google_ads:1234567890:conta:conta',
                split_part(condicao, '|', 1), '{"antes": true}', now(),
                split_part(condicao, '|', 2)::jsonb,
                'v17_03:autoteste:' || md5(condicao), 'v17_03', now() + interval '1 hour');
        RAISE EXCEPTION 'v17_03: proposta sem delta aceita fora da regra: %', condicao;
      EXCEPTION WHEN restrict_violation THEN NULL;
      END;
    END LOOP;

    RAISE EXCEPTION USING ERRCODE = 'V1703', MESSAGE = 'v17_03: desfazer o autoteste';
  EXCEPTION WHEN SQLSTATE 'V1703' THEN
    NULL;  -- tudo o que o autoteste gravou foi desfeito com o bloco
  END;

  IF EXISTS (SELECT 1 FROM public.trafego_regra_otimizacao WHERE chave LIKE 'v17_03_prova%') THEN
    RAISE EXCEPTION 'v17_03: o autoteste deixou regra para tras';
  END IF;

  RAISE NOTICE 'v17_03: verificacao interna passou (travas da v10_02 no corpo; vocabulario fechado; teto proprio; monetaria e nao listada continuam recusadas)';
END
$verifica$;

COMMIT;

-- =============================================================================
-- CONFERÊNCIA DEPOIS DE APLICAR (somente leitura, cole no psql)
-- =============================================================================
-- SELECT chave, versao, jsonb_pretty(operacoes_sem_delta)
--   FROM public.trafego_regra_vigente ORDER BY chave;
--
-- SELECT op, public.trafego_operacao_sem_delta_classe(op)
--   FROM unnest(ARRAY['status', 'orcamento.diario', 'recomendacao.aplicar']) AS op;
--
-- -- propostas que so existem por causa da v17_03 (o que o rollback protege):
-- SELECT operacao, count(*) FROM public.trafego_proposta
--  WHERE delta_pct IS NULL AND delta_absoluto_micros IS NULL GROUP BY 1;
--
-- =============================================================================
-- REGRA DE REFERÊNCIA — `gestao_manual_google` cobrindo os 15 tipos
-- =============================================================================
-- ⚠️ EXEMPLO. Os números são conservadores e são do DONO: responsável, teto de
-- verba, limite de alteração e cada teto por operação. Publicar é decisão dele.
-- `orcamento.diario` e `lance.alvo` são cobertos pelas colunas da v10_02
-- (limite 30%, teto de R$ 500/dia); os outros 13 por `operacoes_sem_delta`.
--
-- INSERT INTO public.trafego_regra_otimizacao
--   (chave, versao, titulo, objetivo, plataformas, canais, janela_minima_dias,
--    atraso_conversao_dias, frescor_maximo_horas, amostra_minima_impressoes,
--    dados_obrigatorios, teto_orcamento_micros, teto_orcamento_moeda,
--    limite_alteracao_pct, cooldown_horas, confianca_minima, condicao_rollback,
--    rollback_janela_horas, responsavel, nivel_autonomia, deteccao, acao,
--    declarada_por, fonte, vigente_desde, operacoes_sem_delta)
-- VALUES
--   ('gestao_manual_google', 1, 'Gestão manual de campanhas Google Ads',
--    'Limitar e registrar ajustes pedidos por humano em campanhas no ar',
--    ARRAY['GOOGLE_ADS'], ARRAY['*'], 7, 0, 6, 0,
--    ARRAY['impressoes', 'custo_micros'], 500000000, 'BRL',
--    30, 24, 0.5, 'o operador declara piora no acompanhamento',
--    72, '<dono>', 'T1', '{"tipo": "pedido_humano"}', '{"tipo": "gestao_manual"}',
--    '<quem publica>', 'humano', now(),
--    '{
--      "status":                 {"status_permitidos": ["PAUSED", "ENABLED"],
--                                 "niveis": ["campanha", "grupo", "anuncio", "asset_group"]},
--      "lance.estrategia":       {"estrategias": ["MANUAL_CPC", "TARGET_SPEND",
--                                                 "MAXIMIZE_CONVERSIONS",
--                                                 "MAXIMIZE_CONVERSION_VALUE"],
--                                 "teto_micros": 50000000},
--      "ajuste.dispositivo":     {"modificador_min": 0.5, "modificador_max": 1.5},
--      "ajuste.horario":         {"modificador_min": 0.5, "modificador_max": 1.5},
--      "negativa.keyword":       {"max_itens": 50, "escopos": ["campanha", "grupo"]},
--      "exclusao.placement":     {"max_itens": 50, "escopos": ["campanha", "conta"]},
--      "exclusao.ip":            {"max_itens": 20, "escopos": ["campanha", "conta"]},
--      "programacao.anuncios":   {"max_itens": 42, "modificador_min": 0.5,
--                                 "modificador_max": 1.5},
--      "lista.criar":            {"max_itens": 100, "max_campanhas": 10},
--      "lista.adicionar":        {"max_itens": 100},
--      "lista.anexar":           {"max_itens": 10},
--      "recomendacao.aplicar":   {"tipos_permitidos": ["SITELINK_ASSET", "CALLOUT_ASSET",
--                                                      "CALL_ASSET",
--                                                      "RESPONSIVE_SEARCH_AD_ASSET"]},
--      "recomendacao.dispensar": {}
--    }'::jsonb);
