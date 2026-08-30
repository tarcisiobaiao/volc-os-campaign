-- =============================================================================
-- v9_99 — Rollback do inventario operacional de Trafego (v9_01)
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin (o mesmo papel que aplicou a v9_01)
--
-- ⚠️ ISTO APAGA DADO, e o dado que ele apaga e justamente o que nao tem outra
-- copia: a identidade interna das campanhas, a trilha de vinculos confirmados e
-- o diario append-only de eventos. `campaigns` NAO tem esses campos — foi por
-- isso que este dominio nasceu separado.
--
-- EXPORTE ANTES. Os seis comandos abaixo levam um minuto e sao a diferenca
-- entre "reaplicar a migration" e "refazer a reconciliacao a mao":
--
--   \copy public.trafego_linhagem         TO 'trafego_linhagem.csv'         CSV HEADER
--   \copy public.trafego_campanha         TO 'trafego_campanha.csv'         CSV HEADER
--   \copy public.trafego_campanha_espelho TO 'trafego_campanha_espelho.csv' CSV HEADER
--   \copy public.trafego_snapshot_conta   TO 'trafego_snapshot_conta.csv'   CSV HEADER
--   \copy public.trafego_vinculo          TO 'trafego_vinculo.csv'          CSV HEADER
--   \copy public.trafego_evento           TO 'trafego_evento.csv'           CSV HEADER
--
-- As duas views da secao 12 (`trafego_inventario_campanha`,
-- `trafego_inventario_conta`) NAO precisam de export: elas nao guardam nada,
-- so leem as seis tabelas acima.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO NAO TOCA
-- -----------------------------------------------------------------------------
-- Nada fora do prefixo `trafego_`. Ele nao altera `campaigns`,
-- `daily_campaign_metrics`, `projects`, `pautador_*`, nem qualquer objeto da
-- serie v8. O dominio de Trafego foi desenhado para ser removivel sem deixar
-- buraco em nada que ja existia — e este arquivo e a prova disso.
--
-- Reverter NAO reabre nenhum risco de seguranca: as seis tabelas somem, e com
-- elas os grants. E o unico rollback desta base que pode ser rodado sem tratar
-- o resultado como incidente.
--
-- -----------------------------------------------------------------------------
-- ROLLBACK PARCIAL — quase sempre e isto que se quer
-- -----------------------------------------------------------------------------
-- Nao rode o arquivo inteiro se o sintoma for pontual. Por sintoma:
--
-- (a) "o gatilho de imutabilidade esta barrando um conserto legitimo"
--     -> NAO derrube o gatilho. Faca o conserto como linha nova + evento, que
--        e o caminho desenhado. Se for inevitavel, desligue-o SO pela duracao
--        da transacao e ligue de volta no mesmo COMMIT:
--          BEGIN;
--          ALTER TABLE public.trafego_campanha DISABLE TRIGGER trafego_campanha_identidade_imutavel;
--          -- o conserto, com o motivo registrado em trafego_evento
--          ALTER TABLE public.trafego_campanha ENABLE  TRIGGER trafego_campanha_identidade_imutavel;
--          COMMIT;
--
-- (b) "o diario automatico de tentativas esta pesando na varredura"
--     -> derrube SO ele; o resto do dominio continua de pe:
--          DROP TRIGGER trafego_snapshot_registra_tentativa ON public.trafego_snapshot_conta;
--        E assuma explicitamente que, a partir dai, registrar a tentativa
--        voltou a depender de o sincronizador lembrar.
--
-- (c) "o backend nao enxerga as tabelas"
--     -> NAO e caso de rollback. Ou o papel do backend nao e service_role, ou o
--        PostgREST nao recarregou o cache de schema. Ver o preflight no README.
--          NOTIFY pgrst, 'reload schema';
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION
      'v9_99 deve rodar como postgres ou supabase_admin; papel atual: %', current_user;
  END IF;
  RAISE NOTICE 'v9_99: derrubando o dominio de Trafego criado pela v9_01';
END
$guarda$;

-- Ordem inversa da dependencia. `CASCADE` nao e usado de proposito: se sobrar
-- alguma coisa apontando para estas tabelas — uma view, uma FK criada depois —
-- o rollback tem de PARAR e mostrar o que e, em vez de arrastar junto um objeto
-- que ninguem sabia que existia.
--
-- As DUAS views da secao 12 saem primeiro, e nominalmente. Elas sao objeto
-- CONHECIDO deste rollback, entao derruba-las por nome nao contradiz o
-- paragrafo acima — o que continua proibido e o `CASCADE` que arrasta o
-- desconhecido. Se uma terceira view aparecer, o `DROP TABLE` sem CASCADE vai
-- falhar dizendo o nome dela, que e exatamente o comportamento desejado.
DROP VIEW IF EXISTS public.trafego_inventario_campanha;
DROP VIEW IF EXISTS public.trafego_inventario_conta;

DROP TRIGGER IF EXISTS trafego_snapshot_registra_tentativa  ON public.trafego_snapshot_conta;
DROP TRIGGER IF EXISTS trafego_snapshot_preserva_ultima_boa ON public.trafego_snapshot_conta;
DROP TRIGGER IF EXISTS trafego_evento_append_only           ON public.trafego_evento;
DROP TRIGGER IF EXISTS trafego_vinculo_so_desfaz            ON public.trafego_vinculo;
DROP TRIGGER IF EXISTS trafego_espelho_preserva_ultima_boa  ON public.trafego_campanha_espelho;
DROP TRIGGER IF EXISTS trafego_campanha_identidade_imutavel ON public.trafego_campanha;

DROP TABLE IF EXISTS public.trafego_vinculo;
DROP TABLE IF EXISTS public.trafego_evento;
DROP TABLE IF EXISTS public.trafego_snapshot_conta;
DROP TABLE IF EXISTS public.trafego_campanha_espelho;
DROP TABLE IF EXISTS public.trafego_campanha;
DROP TABLE IF EXISTS public.trafego_linhagem;

DROP FUNCTION IF EXISTS public.trafego_snapshot_registra_tentativa();
DROP FUNCTION IF EXISTS public.trafego_snapshot_preserva_ultima_boa();
DROP FUNCTION IF EXISTS public.trafego_evento_append_only();
DROP FUNCTION IF EXISTS public.trafego_vinculo_so_desfaz();
DROP FUNCTION IF EXISTS public.trafego_espelho_preserva_ultima_boa();
DROP FUNCTION IF EXISTS public.trafego_campanha_identidade_imutavel();

DO $verifica$
DECLARE
  sobrou text;
BEGIN
  -- `relkind IN ('r','v')`: enquanto a conferencia so olhava tabela, uma view
  -- esquecida sobreviveria ao rollback apontando para tabelas que nao existem
  -- mais — e a reaplicacao falharia com erro cru, sem dizer por que.
  SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO sobrou
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v')
     AND c.relname LIKE 'trafego\_%';
  IF sobrou IS NOT NULL THEN
    RAISE EXCEPTION 'v9_99: sobrou tabela ou view do dominio: %', sobrou;
  END IF;

  SELECT string_agg(p.proname, ', ' ORDER BY p.proname) INTO sobrou
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = 'public' AND p.proname LIKE 'trafego\_%';
  IF sobrou IS NOT NULL THEN
    RAISE EXCEPTION 'v9_99: sobrou funcao do dominio: %', sobrou;
  END IF;

  RAISE NOTICE 'v9_99: dominio de Trafego removido; nada com prefixo trafego_ restou em public';
END
$verifica$;

COMMIT;

-- =============================================================================
-- CONFERENCIA DEPOIS DE REVERTER (somente leitura)
-- =============================================================================
-- SELECT to_regclass('public.trafego_campanha'), to_regclass('public.trafego_evento');
-- -- os dois devem ser NULL
--
-- SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--  WHERE n.nspname = 'public' AND p.proname LIKE 'trafego\_%';
-- -- deve ser 0
