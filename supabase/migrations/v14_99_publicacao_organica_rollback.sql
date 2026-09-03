-- =============================================================================
-- v14_99 — Rollback da Publicacao Organica (v14_01)
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin (o mesmo papel que aplicou a v14_01)
--
-- ⚠️ ISTO APAGA DADO, e apaga justamente o que nao tem outra copia: os RECIBOS
-- de publicacao. O post continua no destino — o Instagram nao desfaz nada
-- porque uma tabela sumiu — mas a prova de QUEM autorizou, QUANDO, com QUAL
-- versao da peca e com QUAL referencia externa some junto. Depois disso,
-- "publicamos isso?" volta a ser uma pergunta para a memoria de alguem.
--
-- EXPORTE ANTES. Os cinco comandos abaixo levam segundos:
--
--   \copy public.publicacao_organica_destino   TO 'publicacao_organica_destino.csv'   CSV HEADER
--   \copy public.publicacao_organica_job       TO 'publicacao_organica_job.csv'       CSV HEADER
--   \copy public.publicacao_organica_operacao  TO 'publicacao_organica_operacao.csv'  CSV HEADER
--   \copy public.publicacao_organica_recibo    TO 'publicacao_organica_recibo.csv'    CSV HEADER
--   \copy public.publicacao_organica_transicao TO 'publicacao_organica_transicao.csv' CSV HEADER
--
-- Nenhum dos cinco carrega segredo: as CHECKs de prosa limpa da secao 9 da
-- v14_01 recusam material de credencial em toda coluna de texto que a API
-- publica. O que eles carregam e a TRILHA, e por isso o export e barato e a
-- perda e cara.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO NAO TOCA — E POR QUE ISSO IMPORTA
-- -----------------------------------------------------------------------------
-- ⚠️ AS TRES FUNCOES GENERICAS DA v13_01 FICAM. `cofre_entrada_hash`,
-- `cofre_append_only` e `cofre_sem_material_de_credencial` sao usadas pela
-- v14_01 mas PERTENCEM a v13_01, e o Cofre continua dependendo delas. Derruba-
-- las aqui quebraria nove tabelas de outro dominio. Quem quiser remove-las roda
-- o v13_99, que e o arquivo que as criou.
--
-- Tambem nao toca: `criativo_*` (a peca e a aprovacao continuam existindo — a
-- publicacao as CONSOME, nunca as possui), `cofre_*`, `pautador_*`, `trafego_*`,
-- `project_wordpress`, `app_auth.*`. O dominio nasceu separado para poder sair
-- sem deixar buraco.
--
-- Reverter NAO reabre risco de seguranca: as cinco tabelas somem, e com elas os
-- grants. Nenhuma delas guardou segredo.
--
-- -----------------------------------------------------------------------------
-- ROLLBACK PARCIAL — quase sempre e isto que se quer
-- -----------------------------------------------------------------------------
-- (a) "o gatilho append-only esta barrando um conserto do recibo"
--     -> NAO derrube o gatilho. O conserto e uma OBSERVACAO NOVA, que e o
--        caminho desenhado: `publicacao_organica_reconciliar` acrescenta uma
--        linha e move o estado. A trilha existe para nao ser reescrita.
--
-- (b) "um job ficou preso em em_voo porque o despachante morreu"
--     -> NAO faca UPDATE direto (o REVOKE da secao 12 nem permite). Espere o
--        lease vencer e chame `publicacao_organica_expirar_lease(job_id)`, que
--        move o job para `indeterminado` — o estado que diz exatamente o que
--        sabemos: nada. De la, `publicacao_organica_reconciliar` resolve.
--        `publicacao_organica_presos()` lista quem esta nessa situacao.
--        ⚠️ NAO redespache: o pedido pode ter chegado, e redespachar duplica.
--
-- (c) "preciso publicar de novo a mesma peca"
--     -> Isso e um JOB NOVO, com chave de idempotencia nova. Reaproveitar o job
--        antigo apagaria a distincao entre "tentamos duas vezes" e "publicamos
--        duas vezes", que e a distincao que a tabela inteira existe para manter.
--
-- (d) "a transicao X>Y foi recusada e eu preciso dela"
--     -> Acrescente a aresta na lista de `publicacao_organica_job_guarda_update`
--        com uma linha dizendo POR QUE ela e legitima. Nao remova o gatilho: uma
--        maquina de estados sem arestas declaradas nao e maquina de estados.
-- =============================================================================

BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION
      'v14_99 deve rodar como postgres ou supabase_admin; papel atual: %',
      current_user;
  END IF;
  RAISE NOTICE 'v14_99: revertendo a publicacao organica (papel=%)', current_user;
END
$guarda$;

-- Ordem: gatilhos (os append-only recusariam o DROP das linhas, nao o da
-- tabela — mas derruba-los primeiro deixa o arquivo legivel), depois as funcoes
-- governadas, depois as tabelas na ordem inversa das FKs.

DROP TRIGGER IF EXISTS publicacao_organica_transicao_append_only ON public.publicacao_organica_transicao;
DROP TRIGGER IF EXISTS publicacao_organica_recibo_append_only    ON public.publicacao_organica_recibo;
DROP TRIGGER IF EXISTS publicacao_organica_operacao_append_only  ON public.publicacao_organica_operacao;
DROP TRIGGER IF EXISTS publicacao_organica_job_sem_delete        ON public.publicacao_organica_job;
DROP TRIGGER IF EXISTS publicacao_organica_job_guarda            ON public.publicacao_organica_job;
DROP TRIGGER IF EXISTS publicacao_organica_job_exige_autorizacao ON public.publicacao_organica_job;

DROP FUNCTION IF EXISTS public.publicacao_organica_presos(integer);
DROP FUNCTION IF EXISTS public.publicacao_organica_expirar_lease(uuid, text);
DROP FUNCTION IF EXISTS public.publicacao_organica_fila(integer);
DROP FUNCTION IF EXISTS public.publicacao_organica_detalhar_job(uuid, uuid);
DROP FUNCTION IF EXISTS public.publicacao_organica_listar_jobs(uuid, text, integer);
DROP FUNCTION IF EXISTS public.publicacao_organica_listar_destinos(uuid);
DROP FUNCTION IF EXISTS public.publicacao_organica_cancelar(uuid, text, uuid);
DROP FUNCTION IF EXISTS public.publicacao_organica_reconciliar(uuid, text, jsonb, uuid, text);
DROP FUNCTION IF EXISTS public.publicacao_organica_concluir_despacho(uuid, bigint, text, text, jsonb, uuid, text);
DROP FUNCTION IF EXISTS public.publicacao_organica_reivindicar(uuid, text, integer);
DROP FUNCTION IF EXISTS public.publicacao_organica_liberar(uuid, uuid);
DROP FUNCTION IF EXISTS public.publicacao_organica_criar_job(jsonb, text, uuid, text);
DROP FUNCTION IF EXISTS public.publicacao_organica_registrar_destino(jsonb, text, uuid, text);
DROP FUNCTION IF EXISTS public.publicacao_organica_registra_operacao(uuid, text, text, text, jsonb, text, uuid, text);
DROP FUNCTION IF EXISTS public.publicacao_organica_idempotencia(text, text, text);
DROP FUNCTION IF EXISTS public.publicacao_organica_job_sem_delete();
DROP FUNCTION IF EXISTS public.publicacao_organica_job_guarda_update();
DROP FUNCTION IF EXISTS public.publicacao_organica_exige_autorizacao();

DROP TABLE IF EXISTS public.publicacao_organica_transicao;
DROP TABLE IF EXISTS public.publicacao_organica_recibo;
DROP TABLE IF EXISTS public.publicacao_organica_operacao;
DROP TABLE IF EXISTS public.publicacao_organica_job;
DROP TABLE IF EXISTS public.publicacao_organica_destino;

-- Os dois ajudantes imutaveis sao deste arquivo e saem com ele. As TRES
-- funcoes da v13_01 (`cofre_entrada_hash`, `cofre_append_only`,
-- `cofre_sem_material_de_credencial`) NAO estao aqui, de proposito — ver o
-- cabecalho.
DROP FUNCTION IF EXISTS public.publicacao_organica_forma_de_chave(text);
DROP FUNCTION IF EXISTS public.publicacao_organica_forma_de_timezone(text);

DO $conferencia$
DECLARE
  sobrou text;
BEGIN
  -- ⚠️ TODA relacao, e nao so `relkind='r'`. A primeira versao conferia apenas
  -- tabelas comuns, entao uma sequence, view ou tabela particionada orfa
  -- passaria por um rollback declarado "completo" — apontado por revisao
  -- adversarial cruzada em 02/09/2026.
  SELECT string_agg(c.relname || ' (' || c.relkind::text || ')', ', ' ORDER BY c.relname) INTO sobrou
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public'
     AND c.relname LIKE 'publicacao\_organica\_%';
  IF sobrou IS NOT NULL THEN
    RAISE EXCEPTION 'v14_99: sobrou relacao: %', sobrou;
  END IF;

  SELECT string_agg(p.proname, ', ' ORDER BY p.proname) INTO sobrou
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = 'public' AND p.proname LIKE 'publicacao\_organica\_%';
  IF sobrou IS NOT NULL THEN
    RAISE EXCEPTION 'v14_99: sobrou funcao: %', sobrou;
  END IF;

  -- A prova de que o rollback NAO levou junto o que nao e dele.
  IF to_regprocedure('public.cofre_entrada_hash(text,jsonb,jsonb)') IS NULL
     OR to_regprocedure('public.cofre_append_only()') IS NULL
     OR to_regprocedure('public.cofre_sem_material_de_credencial(text)') IS NULL THEN
    RAISE EXCEPTION
      'v14_99: as funcoes genericas da v13_01 sumiram — este rollback nao pode toca-las';
  END IF;

  RAISE NOTICE 'v14_99: reversao completa; as funcoes da v13_01 continuam intactas';
END
$conferencia$;

COMMIT;
