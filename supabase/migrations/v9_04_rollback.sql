-- =============================================================================
-- v9_04 ROLLBACK — `url_final` volta a NAO ser preservada
--
-- POR QUE ESTE ARQUIVO EXISTE, E NAO UMA INSTRUCAO
--
-- A nota da v9_04 mandava "reaplicar a definicao da funcao como esta na v9_01".
-- Isso e instrucao manual, nao rollback — e foi exatamente esse tipo de
-- instrucao que produziu o pior defeito desta serie: ao escrever a v9_04 eu
-- reescrevi a funcao a partir do texto e apaguei OITO linhas sem perceber, entre
-- elas a guarda "nenhum numero sem carimbo", que e a regra A do schema inteiro.
-- A migration reportou sucesso.
--
-- `CREATE OR REPLACE FUNCTION` substitui o CORPO INTEIRO. Quem reescreve a
-- funcao a mao apaga tudo o que nao copiar de volta, em silencio. Por isso o
-- corpo abaixo foi EXTRAIDO do `v9_01_trafego_inventario.sql`, e nao redigitado.
--
-- O QUE ESTE ROLLBACK FAZ
--
-- Devolve `url_final` a classe das colunas NAO preservadas. Depois dele, uma
-- varredura que nao traga URL grava `null` — que era o comportamento da v9_01,
-- quando nada escrevia a coluna.
--
-- ⚠️ REVERTER O SCHEMA EXIGE REVERTER O CODIGO JUNTO.
--
-- O adaptador de canal passou a colher `url_final` (`ad_group_ad.ad.final_urls`)
-- e OMITE a chave quando a leitura falha — e essa omissao existe porque o
-- payload do espelho e uniformizado: basta uma linha do lote trazer a chave para
-- todas a mandarem. Sem a preservacao E sem a omissao, uma leitura de anuncio
-- que falhe apaga a URL da conta inteira, e a reconciliacao volta a responder
-- `sem_campanha` — que LIBERA a montagem de uma segunda campanha para o mesmo
-- termo.
--
-- Ou seja: rodar este rollback sem tambem reverter `adaptador_search.py` troca
-- um problema de dado por um que gasta dinheiro.
--
-- ORDEM: se for reverter as duas, reverta a v9_04 ANTES da v9_03. Elas nao se
-- tocam (uma e funcao de gatilho, a outra e view), mas a ordem inversa da
-- aplicacao mantem o par consistente em qualquer ponto.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
  IF to_regclass('public.trafego_campanha_espelho') IS NULL THEN
    RAISE EXCEPTION
      'rollback v9_04 abortado: trafego_campanha_espelho nao existe.';
  END IF;

  IF position('NEW.url_final' IN
      coalesce((SELECT prosrc FROM pg_proc
                 WHERE proname = 'trafego_espelho_preserva_ultima_boa'), '')) = 0
  THEN
    RAISE EXCEPTION
      'rollback v9_04 abortado: a funcao NAO preserva url_final. A v9_04 nao esta aplicada, e nao ha o que reverter.';
  END IF;
END
$guard$;

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

COMMENT ON FUNCTION public.trafego_espelho_preserva_ultima_boa() IS
  'Recusa leitura retroativa; preserva os ROTULOS (nome, estado, veiculacao, canal, moeda) e a ultima entrega medida junto do carimbo dela. Nunca preserva NUMERO sem carimbo, nem presenca.';

-- ── prova, dentro da mesma transacao ────────────────────────────────────────
DO $prova$
DECLARE
  corpo text;
BEGIN
  SELECT prosrc INTO corpo FROM pg_proc
   WHERE proname = 'trafego_espelho_preserva_ultima_boa';

  IF corpo IS NULL THEN
    RAISE EXCEPTION 'rollback v9_04: a funcao sumiu.';
  END IF;
  IF position('NEW.url_final' IN corpo) > 0 THEN
    RAISE EXCEPTION 'rollback v9_04: url_final continua sendo preservada.';
  END IF;

  -- ⚠️ As DUAS guardas da v9_01 continuam vivas. Este e o mesmo par de
  -- verificacoes da v9_04, e pela mesma razao: um rollback que reescreve a
  -- funcao pode apagar uma regra tao facilmente quanto a migration que ele
  -- reverte.
  IF position('entrega com numero e sem carimbo' IN corpo) = 0 THEN
    RAISE EXCEPTION
      'rollback v9_04: a guarda "nenhum numero sem carimbo" sumiu. Ela e a regra A do schema.';
  END IF;
  IF position('Varredura atrasada' IN corpo) = 0 THEN
    RAISE EXCEPTION
      'rollback v9_04: a recusa de leitura retroativa sumiu.';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger
     WHERE tgname = 'trafego_espelho_preserva_ultima_boa'
       AND tgrelid = 'public.trafego_campanha_espelho'::regclass
       AND NOT tgisinternal
  ) THEN
    RAISE EXCEPTION 'rollback v9_04: o gatilho sumiu da tabela.';
  END IF;

  RAISE NOTICE 'v9_04 revertida por %. Reverta `adaptador_search.py` junto.', current_user;
END
$prova$;

COMMIT;
