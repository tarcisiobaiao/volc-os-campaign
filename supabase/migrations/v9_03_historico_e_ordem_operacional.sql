-- =============================================================================
-- v9_03 — historico separado do operacional, e uma ordem que o banco sabe fazer
--
-- POR QUE ESTA MIGRATION EXISTE
--
-- Medido em 26/08/2026 no Supabase oficial: das 84 campanhas do inventario, 79
-- estao REMOVED. Sao 94% de historia. A tela abria mostrando historia, e as 5
-- campanhas que existem de verdade — 2 ligadas, 3 pausadas — ficavam depois
-- delas, fora da primeira pagina.
--
-- O inventario nao estava errado: as 79 sao fatos da conta e continuam
-- consultaveis. Errado era o PADRAO. Quem abre o Hub para trabalhar quer o que
-- esta no ar; quem quer historia pede historia.
--
-- DUAS COLUNAS, E POR QUE ELAS PRECISAM SER COLUNAS
--
-- O PostgREST ordena e filtra por COLUNA. Ele nao aceita expressao no `order`
-- nem no filtro. Sem estas duas colunas, "excluir removidas" e "ativas antes do
-- historico" so poderiam ser feitos em Python DEPOIS de baixar a pagina — e o
-- limite corta ANTES do filtro, entao a paginacao passaria a mentir: pagina de
-- 55 linhas devolvendo 3, e "carregar mais" trazendo mais nada.
--
-- E a mesma razao pela qual `atencao`, `procedencia_desconhecida` e
-- `sem_vinculo` ja sao colunas desta view. Nao e otimizacao; e o que permite ao
-- filtro existir.
--
--   historico            a conta declara a campanha como removida
--   ordem_operacional    0 atencao · 1 ligada · 2 pausada · 3 demais presentes
--                        · 4 historico
--
-- POR QUE `historico` OLHA PARA DOIS CAMPOS
--
-- `presenca = 'removida'` e o NOSSO registro de que a conta declarou remocao;
-- `estado_externo = 'REMOVED'` e o que a conta respondeu. Hoje os dois andam
-- juntos — a varredura grava um a partir do outro (`sincronizador.py`) — e a
-- medicao de 26/08 confirma: 79 e 79, as mesmas linhas.
--
-- Olhar so para um seria confiar que eles nunca se separam. Uma linha inserida
-- a mao, um backfill ou uma reconciliacao futura pode escrever um sem o outro,
-- e o modo de falhar importa: com o OR, uma campanha removida jamais reaparece
-- como operacional. O inverso — uma campanha viva sumir do padrao — seria o
-- defeito grave, e ele exige que AMBOS afirmem remocao, o que nenhum caminho
-- do codigo faz por acidente.
--
-- POR QUE `ordem_operacional` NAO E UM `CASE` NA APLICACAO
--
-- Mesma razao de `atencao`: duas definicoes da mesma regra e o defeito, nao a
-- solucao. `backend/app/trafego/dominio.py:ordem_operacional()` e a traducao
-- literal deste CASE, e `test_ordem_da_view_concorda_com_o_dominio` compara as
-- duas linha a linha contra um Postgres real. Mudar uma sozinha derruba o teste.
--
-- ATENCAO VEM ANTES DE LIGADA, E ISSO E DELIBERADO
--
-- Uma campanha pausada que pede atencao (`nao_encontrada`, por exemplo) sobe
-- na frente de uma ligada que esta bem. A ordem responde "o que exige o
-- operador agora?", nao "o que esta mais viva?". `atencao` ja exclui `removida`
-- (v9_02), entao historia nunca sobe por este ramo.
--
-- O QUE ESTA MIGRATION NAO FAZ
--
-- Nao apaga linha, nao move dado, nao toca em tabela, RLS, grant ou indice.
-- Substitui UMA view. `DROP` + `CREATE` em vez de `CREATE OR REPLACE` porque o
-- Postgres so aceita colunas NOVAS no FIM da lista, e `base.*` as colocaria no
-- meio. Dentro da mesma transacao, e o bloco de seguranca reaplica os grants
-- que o `DROP` leva junto — sem ele a view nasceria sem GRANT nenhum e a API
-- responderia 401 em tudo.
--
-- ROLLBACK: `v9_03_rollback.sql`, e SO ele.
--
-- ⚠️ Reaplicar a v9_02 NAO reverte, e isto foi medido: `CREATE OR REPLACE VIEW`
-- sabe trocar expressao e acrescentar coluna no fim, mas nao sabe REMOVER —
-- devolve `cannot drop columns from view` e aborta. Um rollback documentado que
-- nao executa e descoberto no unico momento em que alguem precisa dele.
--
-- E o rollback do schema exige o do CODIGO junto: a U0 filtra por `historico` e
-- ordena por `ordem_operacional`, e sem as colunas toda leitura do inventario
-- responde erro.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
  IF to_regclass('public.trafego_inventario_campanha') IS NULL THEN
    RAISE EXCEPTION
      'v9_03 abortada: a view trafego_inventario_campanha nao existe. Aplique v9_01 e v9_02 antes.';
  END IF;

  -- Sem a v9_02 aplicada, `atencao` ainda marca `removida` — e `ordem_operacional`
  -- colocaria as 79 removidas no ramo 0, na frente de tudo. A ordem ficaria
  -- exatamente invertida, e nada no resultado denunciaria.
  IF NOT EXISTS (
    SELECT 1 FROM pg_attribute
     WHERE attrelid = 'public.trafego_inventario_campanha'::regclass
       AND attname  = 'atencao'
       AND NOT attisdropped
  ) THEN
    RAISE EXCEPTION
      'v9_03 abortada: a view nao expoe a coluna `atencao`. Aplique v9_02 antes.';
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
  --  1. `presenca = 'removida'` — ACORDO entre o nosso registro e a conta. E
  --     historia, e historia nao e fila (v9_02). Vem PRIMEIRO: ver abaixo.
  --  2. `tentativa_resultado = 'falhou'` — a ultima tentativa de ler a conta
  --     nao voltou. Nao sabemos NADA sobre esta campanha agora, e nao saber e
  --     motivo para olhar.
  --  3. `presenca IS NOT NULL` — o espelho registrou outra ressalva. NULO aqui
  --     e "presente, sem ressalva" e nao pede nada.
  --  4. ligada e `entrega_lida_em IS NULL` — "esta gastando e nao sei quanto".
  --  5. ligada e `impressoes = 0` / `cliques = 0` — sintoma MEDIDO.
  CASE
    -- `removida` ANTES da falha de leitura: remocao no Google Ads e TERMINAL, e
    -- o acordo registrado continua valendo quando a conta nao pode ser lida.
    -- Com a ordem invertida, uma conta caindo devolvia as 79 removidas para a
    -- fila e o sino saltava de 2 para 81 — o alarme que marca o universo,
    -- entrando pela porta dos fundos no pior dia possivel.
    WHEN base.presenca = 'removida'                                   THEN false
    WHEN base.tentativa_resultado = 'falhou'                          THEN true
    WHEN base.presenca IS NOT NULL                                    THEN true
    WHEN upper(btrim(coalesce(base.estado_externo, ''))) <> 'ENABLED' THEN false
    WHEN base.entrega_lida_em IS NULL                                 THEN true
    WHEN base.impressoes IS NULL                                      THEN false
    WHEN base.impressoes = 0                                          THEN true
    WHEN base.cliques = 0                                             THEN true
    ELSE false
  END AS atencao,

  -- HISTORICO — a conta declara a campanha como removida.
  --
  -- Duas fontes para o mesmo fato, unidas por OR: ver o cabecalho. O
  -- `coalesce`/`btrim`/`upper` existe porque `estado_externo` e texto livre no
  -- espelho (a conta responde o enum do Google, que muda sem avisar) e
  -- `'removed'` minusculo ou com espaco continua sendo remocao.
  --
  -- ⚠️ `nao_encontrada` NAO e historico. Ali a leitura foi boa e a campanha nao
  -- estava la: nosso registro e a conta DISCORDAM. Esconder isso do padrao
  -- seria arquivar uma divergencia sem ninguem ter olhado.
  -- ⚠️ `IS NOT DISTINCT FROM`, e nao `=`. Aqui mora a logica de tres valores.
  --
  -- `presenca` e NULO no caso NORMAL: nulo significa "presente, sem ressalva".
  -- Com `=`, `NULL = 'removida'` devolve NULL, `NULL OR false` devolve NULL, e
  -- o filtro `historico=is.false` do PostgREST DESCARTA nulo. O resultado seria
  -- o contrario exato do objetivo: as 5 campanhas que existem sumiriam do
  -- padrao e sobrariam as 79 removidas — todas com `presenca` preenchida.
  --
  -- Pego pela suite contra o Postgres de verdade, na primeira execucao. Um
  -- dublê nao teria pego: ele nao tem logica de tres valores.
  (
    base.presenca IS NOT DISTINCT FROM 'removida'
    OR upper(btrim(coalesce(base.estado_externo, ''))) = 'REMOVED'
  ) AS historico,

  -- ORDEM OPERACIONAL — o que exige o operador agora, primeiro.
  --
  -- Repare que os ramos leem a MESMA expressao de `atencao` e de `historico`
  -- acima, reescrita: uma coluna da lista SELECT nao pode referenciar outra da
  -- mesma lista. A alternativa seria mais um nivel de subconsulta, que
  -- renomearia as colunas e quebraria `base.*`. O preco e a repeticao; o
  -- antidoto e o teste de paridade contra `dominio.ordem_operacional()`.
  --
  --   0  pede atencao        divergencia, falha de leitura, ou entrega ruim
  --   1  ligada              ENABLED, sem nada a conferir
  --   2  pausada             PAUSED
  --   3  demais presentes    qualquer outro estado que nao seja historia
  --   4  historico           a conta declara removida
  --
  -- ⚠️ **SEM `tentativa_resultado`.** Esta e a diferenca entre `ordem_operacional`
  -- e `atencao`, e ela e a razao de a paginacao funcionar.
  --
  -- `ordem_operacional` e a SEGUNDA CHAVE do keyset do cursor. Um keyset exige
  -- que a chave seja estavel para a linha durante a paginacao: a pagina seguinte
  -- e "o que vem depois desta tupla", e se a tupla se move, o ponto deixa de
  -- existir.
  --
  -- `tentativa_resultado` vem de `trafego_snapshot_conta` — e da CONTA, nao da
  -- campanha. Uma unica gravacao de snapshot reescreveria o degrau de TODAS as
  -- campanhas da conta ao mesmo tempo, e o cursor emitido antes passaria a
  -- descrever um ponto inexistente.
  --
  -- Medido contra Postgres real: conta com 6 campanhas saudaveis, limite 3.
  -- Pagina 1 devolvia C-1..C-3; uma varredura que falha entre as duas paginas
  -- levava as seis ao degrau 0, e a pagina 2 voltava VAZIA com
  -- `proximo_cursor: null` — C-4, C-5 e C-6 sumiam da listagem inteira enquanto
  -- o cabecalho continuava dizendo "6 campanhas". Na direcao oposta
  -- (falhou -> ok), a sequencia observada foi C-1,C-2,C-3,C-1,C-2,C-3,C-4,C-5,C-6.
  --
  -- Agora o degrau depende SO de colunas do espelho, que mudam quando a propria
  -- campanha e relida. Isso e o desvio normal de qualquer keyset — atinge a
  -- linha que mudou, e nao o grupo inteiro. E uma varredura que FALHA nao toca
  -- no espelho: os degraus nem se movem.
  --
  -- A falha da conta NAO se perde: `atencao` continua marcando todas as
  -- campanhas dela (primeiro ramo do CASE acima), o sino continua contando, e o
  -- cabecalho do grupo declara `frescor: falhou` com o motivo. O que sai daqui
  -- e so a ORDEM — porque ordem precisa de chave estavel, e "a conta falhou" e
  -- fato da conta, ja dito no lugar da conta.
  CASE
    WHEN (
      base.presenca IS NOT DISTINCT FROM 'removida'
      OR upper(btrim(coalesce(base.estado_externo, ''))) = 'REMOVED'
    ) THEN 4
    WHEN (
      CASE
        WHEN base.presenca = 'removida'                                   THEN false
        WHEN base.presenca IS NOT NULL                                    THEN true
        WHEN upper(btrim(coalesce(base.estado_externo, ''))) <> 'ENABLED' THEN false
        WHEN base.entrega_lida_em IS NULL                                 THEN true
        WHEN base.impressoes IS NULL                                      THEN false
        WHEN base.impressoes = 0                                          THEN true
        WHEN base.cliques = 0                                             THEN true
        ELSE false
      END
    ) THEN 0
    WHEN upper(btrim(coalesce(base.estado_externo, ''))) = 'ENABLED' THEN 1
    WHEN upper(btrim(coalesce(base.estado_externo, ''))) = 'PAUSED'  THEN 2
    ELSE 3
  END::smallint AS ordem_operacional

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
    --
    -- `nao_espelhada` esta deliberadamente FORA do vocabulario: a propria
    -- `presenca_projetada()` manda valor desconhecido para
    -- `conta_nao_identificada`, que e a afirmacao mais fraca disponivel. A CHECK
    -- do espelho NAO o aceita — ele nunca pode ser gravado, so projetado.
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

    -- Fatos que NAO entram em `atencao`, mas que precisam ser filtraveis: sem
    -- coluna, filtrar por eles voltaria a ser trabalho de Python depois da
    -- paginacao — e a paginacao passaria a mentir de novo.
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

  -- O frescor da CONTA na linha da CAMPANHA. E o que permite ao primeiro termo
  -- de `atencao` existir sem uma segunda consulta.
  LEFT JOIN public.trafego_snapshot_conta s
         ON s.customer_id = c.customer_id
) AS base;

COMMENT ON VIEW public.trafego_inventario_campanha IS
  'Projecao de leitura do inventario. `atencao`, `historico` e `ordem_operacional` '
  'sao calculadas aqui porque o PostgREST filtra e ordena por COLUNA: em Python, '
  'o limite da pagina cortaria ANTES do filtro. As tres tem espelho literal em '
  'backend/app/trafego/dominio.py e testes de paridade contra banco real.';

-- ── os grants que o DROP levou junto ────────────────────────────────────────
--
-- `DROP VIEW` apaga o objeto e todos os privilegios dele. Sem este bloco a view
-- renasce sem GRANT nenhum, `service_role` perde o SELECT e a API responde
-- erro em toda leitura do inventario — uma quebra total, na primeira
-- requisicao depois da migration.
--
-- A ordem e REVOKE nominal primeiro: o `pg_default_acl` do schema `public`
-- concede NOMINALMENTE a `anon`, e um REVOKE de PUBLIC nao alcanca concessao
-- nominal. Foi medido em v9_01 (seis casos) e continua valendo.
DO $seguranca$
BEGIN
  REVOKE ALL ON TABLE public.trafego_inventario_campanha FROM PUBLIC;
  REVOKE ALL ON TABLE public.trafego_inventario_campanha FROM anon;
  REVOKE ALL ON TABLE public.trafego_inventario_campanha FROM authenticated;
  REVOKE ALL ON TABLE public.trafego_inventario_campanha FROM service_role;

  -- Somente leitura, e somente para o papel do backend. A view roda com
  -- `security_invoker`, entao o RLS FORCE das tabelas de baixo continua valendo
  -- para quem a consultar — ela nao e um atalho para os dados.
  GRANT SELECT ON TABLE public.trafego_inventario_campanha TO service_role;
END
$seguranca$;

-- ── prova imediata, dentro da mesma transacao ───────────────────────────────
--
-- Se qualquer uma falhar, o COMMIT nao acontece e o banco fica exatamente como
-- estava. Uma migration de view que nao se prova sai daqui como "aplicada" e so
-- e descoberta pela tela.
DO $prova$
DECLARE
  faltando text;
  sem_grant boolean;
BEGIN
  SELECT string_agg(col, ', ')
    INTO faltando
    FROM unnest(ARRAY['atencao', 'historico', 'ordem_operacional']) AS col
   WHERE NOT EXISTS (
     SELECT 1 FROM pg_attribute
      WHERE attrelid = 'public.trafego_inventario_campanha'::regclass
        AND attname = col AND NOT attisdropped
   );
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'v9_03: a view nasceu sem a(s) coluna(s) %', faltando;
  END IF;

  SELECT NOT has_table_privilege('service_role',
                                 'public.trafego_inventario_campanha', 'SELECT')
    INTO sem_grant;
  IF sem_grant THEN
    RAISE EXCEPTION
      'v9_03: service_role ficou sem SELECT na view — a API responderia erro em toda leitura.';
  END IF;

  IF has_table_privilege('anon', 'public.trafego_inventario_campanha', 'SELECT') THEN
    RAISE EXCEPTION
      'v9_03: anon alcanca a view. O REVOKE nominal nao pegou.';
  END IF;

  RAISE NOTICE 'v9_03 aplicada por % — historico e ordem_operacional publicadas, grants refeitos.',
    current_user;
END
$prova$;

COMMIT;
