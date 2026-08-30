-- =============================================================================
-- v9_02 — `removida` deixa de pedir atenção
--
-- POR QUE ESTA MIGRATION EXISTE
--
-- A primeira varredura real (25/08/2026) leu 84 campanhas em tres contas. 79
-- delas estavam REMOVED na conta, e a regra de atencao marcava todas: o CASE da
-- view devolvia `true` para qualquer `presenca IS NOT NULL`.
--
-- Resultado medido: 81 de 84 pedindo atencao. Um alerta que marca o universo e
-- o mesmo que alerta nenhum — o operador para de olhar, e ai ele para de olhar
-- TAMBEM para as DUAS que importavam. Depois desta migration: 2 de 84, e as
-- duas sao as unicas campanhas ENABLED da fonte (Maquininha de Cartao e FGTS
-- Saque-Aniversario), ligadas e quase sem entrega.
--
-- A distincao que faltava:
--
--   `removida`        a conta DIZ que foi removida e nos registramos. E ACORDO.
--                     Nao ha o que conferir. E historia, e historia mora no
--                     inventario, nao na fila de atencao.
--
--   `nao_encontrada`  a leitura foi BOA e a campanha NAO estava la. Nosso
--                     registro e a conta DISCORDAM, e discordancia merece um
--                     olho. Continua pedindo atencao.
--
-- O CASE abaixo e a traducao literal de `dominio.pede_atencao()`, e as duas
-- MUDAM SEMPRE JUNTAS — ha teste que as compara linha a linha contra um banco
-- real (`test_atencao_da_view_concorda_com_pede_atencao`). Alterar uma sozinha
-- faz o sino e a aba discordarem, que e o defeito que a Fase 1B inteira
-- existe para nao ter.
--
-- Nao altera tabela, nao move dado, nao mexe em RLS nem em grant: so substitui
-- a expressao de uma view. `CREATE OR REPLACE` preserva as permissoes.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
  IF to_regclass('public.trafego_inventario_campanha') IS NULL THEN
    RAISE EXCEPTION 'v9_02 abortada: a view trafego_inventario_campanha nao existe. Aplique v9_01 antes.';
  END IF;
END
$guard$;

CREATE OR REPLACE VIEW public.trafego_inventario_campanha
  WITH (security_invoker = true) AS
SELECT
  base.*,

  -- ATENCAO — a MESMA regra de `backend/app/trafego/dominio.py:pede_atencao()`,
  -- termo por termo e na mesma ordem. Ela e calculada aqui porque o filtro
  -- `?atencao=true` e a contagem do sino precisam resolver NO BANCO: filtrar em
  -- Python faria a paginacao mentir (o limite corta ANTES do filtro) e faria o
  -- sino contar so a pagina corrente.
  --
  -- ⚠️ DUAS DEFINICOES DE `atencao` E O DEFEITO, NAO A SOLUCAO. Se esta
  -- expressao e `pede_atencao()` discordarem, o sino e a aba mostram numeros
  -- diferentes para a mesma pergunta e nao ha como saber qual esta certo.
  -- `backend/tests/test_trafego_persistencia.py` compara as duas linha a linha
  -- contra um banco de verdade; mudar uma sem a outra derruba o teste.
  --
  -- CADA TERMO E UM FATO OBSERVADO:
  --
  --  1. `tentativa_resultado = 'falhou'` — a ultima tentativa de ler a conta
  --     nao voltou. Nao sabemos NADA sobre esta campanha agora, e nao saber e
  --     motivo para olhar. E o E-07: tres contas falhando era visualmente
  --     identico a "tudo bem".
  --  2. `presenca IS NOT NULL` — o espelho registrou uma ressalva (um dos seis
  --     estados). NULO aqui e "presente, sem ressalva" e nao pede nada.
  --  3. ligada e `entrega_lida_em IS NULL` — "esta gastando e nao sei quanto".
  --  4. ligada e `impressoes = 0` / `cliques = 0` — sintoma MEDIDO. Repare em
  --     `impressoes IS NULL` devolvendo `false` na linha anterior: "nao consegui
  --     medir" NAO e "medi e deu zero", e o ramo (3) ja cobriu o primeiro.
  --
  -- O QUE FICA DE FORA, E POR QUE — as duas sao fato observado e mesmo assim
  -- nao entram, entao viajam como COLUNA PROPRIA (`procedencia_desconhecida`,
  -- `sem_vinculo`) para que um filtro futuro as alcance sem passar pelo sino:
  --
  --   · `procedencia = 'desconhecida'` e o estado de TODA campanha que a
  --     varredura descobre — a varredura nao tem como saber quem a criou.
  --     No sino, ela marcaria o inventario inteiro no primeiro dia.
  --   · vinculo ausente e o estado normal de quase tudo: vincular e uma decisao
  --     humana, uma a uma. Marcar tudo enche a aba de linhas CORRETAS, o
  --     operador para de olhar, e o alerta morre — que e o unico jeito de um
  --     alerta falhar de vez.
  CASE
    WHEN base.tentativa_resultado = 'falhou'                          THEN true
    -- `removida` e ACORDO entre o nosso registro e a conta: ela diz que foi
    -- removida e nos registramos. Nao ha o que conferir — e historia, e
    -- historia mora no inventario, nao na fila de atencao. Medido em
    -- 25/08/2026, na primeira varredura real: sem esta excecao, 81 de 84
    -- campanhas pediam atencao, e um alerta que marca o universo e o mesmo
    -- que alerta nenhum.
    --
    -- `nao_encontrada` CONTINUA pedindo: ali a leitura foi BOA e a campanha nao
    -- estava la. Nosso registro e a conta DISCORDAM, e discordancia merece um
    -- olho humano.
    WHEN base.presenca = 'removida'                                   THEN false
    WHEN base.presenca IS NOT NULL                                    THEN true
    WHEN upper(btrim(coalesce(base.estado_externo, ''))) <> 'ENABLED' THEN false
    WHEN base.entrega_lida_em IS NULL                                 THEN true
    WHEN base.impressoes IS NULL                                      THEN false
    WHEN base.impressoes = 0                                          THEN true
    WHEN base.cliques = 0                                             THEN true
    ELSE false
  END AS atencao

FROM (
  SELECT
    c.volc_campaign_id,
    c.campaign_lineage_id,
    c.customer_id,
    c.campaign_id,
    c.procedencia,
    c.criada_em,
    c.criada_por,

    -- PRESENCA — o unico lugar da view onde um valor e substituido, e a troca e
    -- por um termo FORA das seis, nao por um dos seis.
    --
    -- Sem linha no espelho, esta campanha NUNCA foi lida. Deixar `presenca`
    -- nula aqui faria `presenca_projetada()` responder `presente` — afirmando
    -- que a conta respondeu e a campanha estava la, o que ninguem observou.
    -- Escolher um dos seis seria pior: `nao_encontrada` afirma ausencia,
    -- `sincronizacao_falhou` afirma falha, e nenhuma das duas aconteceu.
    --
    -- `nao_espelhada` esta deliberadamente FORA do vocabulario: a propria
    -- `presenca_projetada()` manda valor desconhecido para
    -- `conta_nao_identificada`, que e a afirmacao mais fraca disponivel. A
    -- degradacao e automatica e segura, e nenhum termo novo entrou no contrato.
    -- A CHECK do espelho NAO o aceita — ele nunca pode ser gravado, so
    -- projetado.
    CASE WHEN e.volc_campaign_id IS NULL THEN 'nao_espelhada' ELSE e.presenca END
      AS presenca,

    e.lido_em,
    e.nome,
    e.estado_externo,
    e.veiculacao,
    e.canal,
    e.estrategia,
    e.url_final,
    e.canal_bruto,
    e.estrategia_bruta,
    e.lance_micros,
    e.verba_diaria_micros,
    e.impressoes,
    e.cliques,
    e.custo_micros,
    e.moeda,
    e.entrega_lida_em,

    v.vinculo_id,
    v.opportunity_id,
    v.project_id,
    v.funnel_run_id,
    v.regra              AS vinculo_regra,
    v.confirmado_por     AS vinculo_confirmado_por,
    v.confirmado_em      AS vinculo_confirmado_em,

    s.tentativa_em,
    s.tentativa_resultado,
    s.leitura_boa_em,

    -- Fatos que NAO entram em `atencao` (ver acima), mas que precisam ser
    -- filtraveis: sem coluna, filtrar por eles voltaria a ser trabalho de
    -- Python depois da paginacao — e a paginacao passaria a mentir de novo.
    (c.procedencia = 'desconhecida') AS procedencia_desconhecida,
    (v.vinculo_id IS NULL)           AS sem_vinculo

  FROM public.trafego_campanha c

  -- LEFT: identidade sem espelho e um estado real — a porta de criacao declara
  -- a campanha antes de a primeira varredura passar. INNER a esconderia da tela
  -- exatamente na janela em que o operador acabou de cria-la.
  LEFT JOIN public.trafego_campanha_espelho e
         ON e.volc_campaign_id = c.volc_campaign_id

  -- No maximo UMA linha por campanha: `trafego_vinculo_ativo_por_campanha_ux` e
  -- unico sobre `volc_campaign_id WHERE desfeito_em IS NULL`. Sem esse indice
  -- este LEFT JOIN multiplicaria linhas e a contagem do sino passaria a somar a
  -- mesma campanha duas vezes.
  LEFT JOIN public.trafego_vinculo v
         ON v.volc_campaign_id = c.volc_campaign_id
        AND v.desfeito_em IS NULL

  -- O frescor da CONTA na linha da CAMPANHA. E o que permite ao termo (1) de
  -- `atencao` existir sem uma segunda consulta.
  LEFT JOIN public.trafego_snapshot_conta s
         ON s.customer_id = c.customer_id
) AS base;

COMMIT;
