-- =============================================================================
-- v9_04 — `url_final` passa a ser rotulo preservado
--
-- POR QUE ESTA MIGRATION EXISTE
--
-- A v9_01 deixou `url_final` DE FORA da lista de rotulos preservados, com uma
-- razao escrita e correta na epoca:
--
--     url_final  ausencia legitima: campanha pode nao ter URL final.
--
-- Era verdade porque NADA escrevia a coluna. Nenhuma consulta pedia URL, e a
-- ausencia so podia significar "esta campanha nao tem destino". Medido em
-- 26/08/2026: `url_final` era NULA nas 84 campanhas das tres contas.
--
-- A partir da U0 o adaptador de canal a colhe (`ad_group_ad.ad.final_urls`, so
-- SELECT), e a ausencia passa a ter DUAS causas possiveis:
--
--   a campanha nao tem destino          ausencia legitima, como antes
--   a leitura do anuncio nao voltou     ausencia por falta de resposta
--
-- E as duas chegam ao banco identicas: `null`.
--
-- O QUE ACONTECE SEM ESTA MIGRATION
--
-- O payload do espelho e uniformizado (`persistencia._uniforme`): basta uma
-- linha do lote trazer a chave para TODAS a mandarem. Uma leitura de anuncio
-- que falhe manda `url_final: null` para a conta inteira e, sem preservacao, o
-- UPDATE apaga a URL de todas as campanhas.
--
-- O estrago nao para no dado. `url_final` e o sinal MAIS FORTE da reconciliacao
-- (SPEC 3.2): sem ele, o quadro de Oportunidades volta a responder
-- `sem_campanha` e a oferecer "montar campanha" para funis que ja tem campanha
-- no ar — que e exatamente o defeito que a U0.2 fecha. Uma falha de leitura
-- passaria a CRIAR duplicidade, silenciosamente.
--
-- POR QUE PRESERVAR E A DIRECAO CERTA DE FALHAR
--
-- Preservar tem um custo real: uma campanha que perdeu todos os anuncios
-- continua exibindo o ultimo destino conhecido, que ja nao vale. E dado velho
-- passando por atual.
--
-- Nao preservar tem outro: uma leitura que falhou faz o sistema afirmar que
-- nenhuma campanha aponta para aquele funil, e convidar o operador a criar uma
-- segunda campanha para o mesmo termo — dois anuncios nossos disputando o mesmo
-- leilao, com verba de verdade.
--
-- Os dois erram; so um gasta dinheiro. E o dado velho tem carimbo (`lido_em`) e
-- aparece na tela como velho; a duplicidade nao tem aviso nenhum.
--
-- `url_final` entra, portanto, na MESMA classe de `nome`, `estado_externo`,
-- `veiculacao`, `canal` e `moeda`: rotulo lido da conta, preservado quando a
-- leitura nao trouxe substituto. Ela nao entra na classe dos NUMEROS
-- (`impressoes`, `lance_micros`, `verba_diaria_micros`), que continuam sem
-- preservacao — numero sem carimbo proprio e a regra A violada.
--
-- O QUE ESTA MIGRATION NAO FAZ
--
-- Nao altera tabela, coluna, CHECK, indice, RLS ou grant. Substitui o corpo de
-- UMA funcao de gatilho. `CREATE OR REPLACE FUNCTION` preserva o gatilho que a
-- referencia.
--
-- ROLLBACK: reaplicar a definicao da funcao como esta em
-- `v9_01_trafego_inventario.sql` (secao 5), que difere desta em uma linha.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
  IF to_regclass('public.trafego_campanha_espelho') IS NULL THEN
    RAISE EXCEPTION
      'v9_04 abortada: trafego_campanha_espelho nao existe. Aplique v9_01 antes.';
  END IF;
END
$guard$;

CREATE OR REPLACE FUNCTION public.trafego_espelho_preserva_ultima_boa()
RETURNS trigger
LANGUAGE plpgsql
AS $funcao$
BEGIN
  -- Leitura retroativa nao entra: uma varredura antiga chegando depois de uma
  -- recente sobrescreveria o novo com o velho.
  IF NEW.lido_em < OLD.lido_em THEN
    RAISE EXCEPTION
      'trafego_campanha_espelho: leitura de % e mais velha que a corrente (%). Varredura atrasada nao sobrescreve leitura mais nova.',
      NEW.lido_em, OLD.lido_em
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- ⚠️ NENHUM NUMERO SEM CARIMBO. Esta guarda vem da v9_01 e e a regra A do
  -- schema inteiro: a CHECK `..._entrega_sem_carimbo` nao alcanca o caso em que
  -- existe uma linha ANTERIOR com carimbo — o UPDATE traria numero novo sob
  -- carimbo velho e passaria. Um custo sem data e indistinguivel de um custo de
  -- ontem.
  --
  -- Ela foi omitida por engano na primeira escrita desta migration, e a
  -- auditoria adversarial a pegou contra um Postgres real. `CREATE OR REPLACE
  -- FUNCTION` substitui o CORPO INTEIRO: reescrever a funcao para acrescentar
  -- uma linha apaga tudo o que nao for copiado de volta, em silencio.
  IF NEW.entrega_lida_em IS NULL
     AND (NEW.impressoes IS NOT NULL OR NEW.cliques IS NOT NULL
          OR NEW.custo_micros IS NOT NULL)
  THEN
    RAISE EXCEPTION
      'trafego_campanha_espelho: entrega com numero e sem carimbo de leitura. Um custo sem data e indistinguivel de um custo de ontem.'
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- ROTULOS: sobrevivem a uma leitura que nao os trouxe. Sao descricoes da
  -- campanha, nao medidas dela — nome nao "expira".
  --
  -- `url_final` entrou nesta lista na v9_04. Ver o cabecalho: a partir do
  -- momento em que o adaptador de canal a colhe, `null` deixou de significar so
  -- "nao tem destino" e passou a significar tambem "nao consegui ler" — e as
  -- duas chegam identicas.
  NEW.nome           := coalesce(NEW.nome,           OLD.nome);
  NEW.estado_externo := coalesce(NEW.estado_externo, OLD.estado_externo);
  NEW.veiculacao     := coalesce(NEW.veiculacao,     OLD.veiculacao);
  NEW.canal          := coalesce(NEW.canal,          OLD.canal);
  NEW.canal_bruto    := coalesce(NEW.canal_bruto,    OLD.canal_bruto);
  NEW.moeda          := coalesce(NEW.moeda,          OLD.moeda);
  NEW.url_final      := coalesce(NEW.url_final,      OLD.url_final);

  -- NUMEROS: nunca preservados sem o carimbo que os denomina. A excecao e o
  -- bloco abaixo, que preserva a ultima entrega medida JUNTO do carimbo dela.
  IF OLD.entrega_lida_em IS NOT NULL
     AND (NEW.entrega_lida_em IS NULL OR NEW.entrega_lida_em < OLD.entrega_lida_em)
  THEN
    NEW.impressoes      := OLD.impressoes;
    NEW.cliques         := OLD.cliques;
    NEW.custo_micros    := OLD.custo_micros;
    -- A moeda que DENOMINA os numeros preservados tem de ser a daquela leitura,
    -- e nao a que chegou agora.
    NEW.moeda           := OLD.moeda;
    NEW.entrega_lida_em := OLD.entrega_lida_em;
  END IF;

  NEW.atualizado_em := now();
  RETURN NEW;
END
$funcao$;

COMMENT ON FUNCTION public.trafego_espelho_preserva_ultima_boa() IS
  'Recusa leitura retroativa; preserva os ROTULOS (nome, estado, veiculacao, canal, moeda, url_final) e a ultima entrega medida junto do carimbo dela. Nunca preserva NUMERO sem carimbo, nem presenca.';

DO $prova$
DECLARE
  corpo text;
BEGIN
  SELECT prosrc INTO corpo FROM pg_proc WHERE proname = 'trafego_espelho_preserva_ultima_boa';
  IF corpo IS NULL OR position('NEW.url_final' IN corpo) = 0 THEN
    RAISE EXCEPTION 'v9_04: a funcao nao passou a preservar url_final.';
  END IF;

  -- ⚠️ A guarda da v9_01 continua viva. `CREATE OR REPLACE FUNCTION` substitui o
  -- corpo inteiro, e uma migration que reescreve uma funcao pode apagar uma
  -- regra sem que nada acuse — foi o que aconteceu na primeira versao desta.
  IF position('entrega com numero e sem carimbo' IN corpo) = 0 THEN
    RAISE EXCEPTION
      'v9_04: a guarda "nenhum numero sem carimbo" sumiu da funcao. Ela e a regra A do schema: um custo sem data e indistinguivel de um custo de ontem.';
  END IF;
  IF position('Varredura atrasada' IN corpo) = 0 THEN
    RAISE EXCEPTION
      'v9_04: a recusa de leitura retroativa sumiu da funcao.';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger
     WHERE tgname = 'trafego_espelho_preserva_ultima_boa'
       AND tgrelid = 'public.trafego_campanha_espelho'::regclass
       AND NOT tgisinternal
  ) THEN
    RAISE EXCEPTION 'v9_04: o gatilho sumiu da tabela — CREATE OR REPLACE deveria te-lo preservado.';
  END IF;
  RAISE NOTICE 'v9_04 aplicada por % — url_final entra nos rotulos preservados.', current_user;
END
$prova$;

COMMIT;
