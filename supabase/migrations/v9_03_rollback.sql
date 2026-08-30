-- =============================================================================
-- v9_03 ROLLBACK — devolve a view ao estado da v9_02
--
-- POR QUE ESTE ARQUIVO EXISTE, E POR QUE O ROLLBACK "OBVIO" NAO FUNCIONA
--
-- A v9_03 dizia, no proprio cabecalho, que o rollback era "reaplicar a v9_02".
-- Nao e. Medido em Postgres 16 descartavel, com v9_01..v9_04 aplicadas:
--
--     psql -f v9_02_atencao_sem_removida.sql
--     ERROR:  cannot drop columns from view
--
-- `CREATE OR REPLACE VIEW` sabe TROCAR a expressao de uma coluna e sabe
-- ACRESCENTAR colunas no fim. Ele nao sabe REMOVER — e a v9_03 acrescentou
-- `historico` e `ordem_operacional`. Um rollback documentado que aborta e pior
-- que rollback nenhum: ele so e descoberto no momento em que alguem precisa
-- dele, que e sempre o pior momento.
--
-- Este arquivo faz o que a v9_03 fez, ao contrario: DROP + CREATE + os grants
-- que o DROP leva junto, tudo numa transacao.
--
-- ⚠️ DEPOIS DE RODAR ISTO, O BACKEND PRECISA VOLTAR JUNTO. O codigo da U0 filtra
-- por `historico` e ordena por `ordem_operacional`; sem as colunas, toda leitura
-- do inventario responde erro do PostgREST. Reverter o schema sem reverter o
-- codigo troca um problema por uma queda total.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
  IF to_regclass('public.trafego_inventario_campanha') IS NULL THEN
    RAISE EXCEPTION 'rollback abortado: a view nao existe.';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_attribute
     WHERE attrelid = 'public.trafego_inventario_campanha'::regclass
       AND attname = 'ordem_operacional' AND NOT attisdropped
  ) THEN
    RAISE EXCEPTION
      'rollback abortado: a view nao tem `ordem_operacional`. A v9_03 nao esta aplicada, e nao ha o que reverter.';
  END IF;
END
$guard$;

DROP VIEW public.trafego_inventario_campanha;

CREATE VIEW public.trafego_inventario_campanha
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

-- Os grants que o DROP levou junto. Sem este bloco a view renasce sem GRANT
-- nenhum e a API responde erro em toda leitura — um rollback que derruba o
-- sistema nao e um rollback.
DO $seguranca$
BEGIN
  REVOKE ALL ON TABLE public.trafego_inventario_campanha FROM PUBLIC;
  REVOKE ALL ON TABLE public.trafego_inventario_campanha FROM anon;
  REVOKE ALL ON TABLE public.trafego_inventario_campanha FROM authenticated;
  REVOKE ALL ON TABLE public.trafego_inventario_campanha FROM service_role;
  GRANT SELECT ON TABLE public.trafego_inventario_campanha TO service_role;
END
$seguranca$;

DO $prova$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_attribute
     WHERE attrelid = 'public.trafego_inventario_campanha'::regclass
       AND attname IN ('historico', 'ordem_operacional') AND NOT attisdropped
  ) THEN
    RAISE EXCEPTION 'rollback: as colunas da v9_03 continuam na view.';
  END IF;
  IF NOT has_table_privilege('service_role',
                             'public.trafego_inventario_campanha', 'SELECT') THEN
    RAISE EXCEPTION 'rollback: service_role ficou sem SELECT na view.';
  END IF;
  IF has_table_privilege('anon', 'public.trafego_inventario_campanha', 'SELECT') THEN
    RAISE EXCEPTION 'rollback: anon alcanca a view.';
  END IF;
  RAISE NOTICE 'v9_03 revertida por %. Reverta o BACKEND junto.', current_user;
END
$prova$;

COMMIT;
