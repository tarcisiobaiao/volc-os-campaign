-- =============================================================================
-- v13_99 — Rollback do Cofre de Ativos (v13_01)
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin (o mesmo papel que aplicou a v13_01)
--
-- ⚠️ ISTO APAGA DADO, e apaga justamente o que nao tem outra copia: o
-- inventario do patrimonio, a trilha append-only de revisoes e verificacoes, e
-- as REFERENCIAS de credencial. As referencias nao sao os segredos — eles
-- continuam intactos no 1Password — mas o mapa de qual ativo usa qual item
-- volta a existir apenas na cabeca de quem cadastrou.
--
-- EXPORTE ANTES. Os nove comandos abaixo levam um minuto:
--
--   \copy public.cofre_ativo                  TO 'cofre_ativo.csv'                  CSV HEADER
--   \copy public.cofre_engine_perfil          TO 'cofre_engine_perfil.csv'          CSV HEADER
--   \copy public.cofre_ativo_revisao          TO 'cofre_ativo_revisao.csv'          CSV HEADER
--   \copy public.cofre_relacao                TO 'cofre_relacao.csv'                CSV HEADER
--   \copy public.cofre_verificacao            TO 'cofre_verificacao.csv'            CSV HEADER
--   \copy public.cofre_operacao               TO 'cofre_operacao.csv'               CSV HEADER
--   \copy public.cofre_gaveta                 TO 'cofre_gaveta.csv'                 CSV HEADER
--   \copy public.cofre_tipo                   TO 'cofre_tipo.csv'                   CSV HEADER
--
-- ⚠️ O NONO EXPORT MERECE DECISAO SEPARADA:
--
--   \copy public.cofre_credencial_referencia  TO 'cofre_credencial_referencia.csv'  CSV HEADER
--
-- Ele escreve a coluna `localizador` num arquivo em disco. O localizador nao e
-- segredo — e endereco — mas um CSV com o mapa completo de onde cada credencial
-- da operacao mora e material sensivel por agregacao. Se exportar: para disco
-- cifrado, fora de qualquer diretorio versionado, e apague depois de reaplicar.
-- Se nao exportar: as referencias sao recadastradas a mao, o que e trabalhoso e
-- seguro. As duas escolhas sao defensaveis; a que nao e defensavel e exportar
-- sem decidir.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO NAO TOCA
-- -----------------------------------------------------------------------------
-- Nada fora do prefixo `cofre_`. Ele nao altera `campaigns`, `trafego_*`,
-- `pautador_*`, `app_auth.*`, nem qualquer objeto das series v8 a v12. O
-- dominio do Cofre nasceu separado para poder sair sem deixar buraco.
--
-- Reverter NAO reabre risco de seguranca: as nove tabelas somem, e com elas os
-- grants. Nenhum segredo e revelado por remover uma tabela que nunca guardou
-- segredo.
--
-- -----------------------------------------------------------------------------
-- ROLLBACK PARCIAL — quase sempre e isto que se quer
-- -----------------------------------------------------------------------------
-- (a) "o gatilho append-only esta barrando um conserto legitimo"
--     -> NAO derrube o gatilho. O conserto e um registro NOVO, que e o caminho
--        desenhado: `cofre_revisar_ativo` para o ativo, `cofre_registrar_-
--        verificacao` para a prova. A trilha existe para nao ser reescrita.
--
-- (b) "a CHECK do localizador esta recusando uma referencia legitima"
--     -> NAO afrouxe a CHECK para um `~ '.*'`. Se o provider novo tem outra
--        gramatica, ADICIONE o ramo dele:
--          ALTER TABLE public.cofre_credencial_referencia
--            DROP CONSTRAINT cofre_credencial_localizador_opaco;
--          ALTER TABLE public.cofre_credencial_referencia
--            ADD  CONSTRAINT cofre_credencial_localizador_opaco CHECK (...ramos + o novo...);
--        Uma CHECK que aceita tudo tem o mesmo efeito de nao existir, com a
--        desvantagem de parecer que existe.
--
-- (c) "o backend nao enxerga as funcoes"
--     -> NAO e caso de rollback. Ou o papel nao e service_role, ou o PostgREST
--        nao recarregou o cache: `NOTIFY pgrst, 'reload schema';`
--
-- (d) "quero zerar so os dados, mantendo o schema"
--     -> Nao ha DELETE concedido a ninguem, e isso e desenho. Zerar exige o
--        papel dono e um TRUNCATE explicito, na ordem das FKs:
--          TRUNCATE public.cofre_operacao, public.cofre_verificacao,
--                   public.cofre_ativo_revisao, public.cofre_credencial_referencia,
--                   public.cofre_relacao, public.cofre_engine_perfil,
--                   public.cofre_ativo RESTART IDENTITY;
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION
      'v13_99 deve rodar como postgres ou supabase_admin; papel atual: %',
      current_user;
  END IF;
  RAISE NOTICE 'v13_99: removendo o dominio Cofre de Ativos (papel=%)', current_user;
END
$guarda$;

-- Ordem: funcoes, depois tabelas na ordem inversa das FKs. (Nao ha view:
-- `cofre_inventario` foi removida do desenho por nao ter consumidor.)
-- `CASCADE` nao e usado em lugar nenhum: ele apagaria em silencio um objeto de
-- outro dominio que dependesse destes, e a lista explicita e a unica forma de o
-- rollback nao levar junto o que nao e dele.
DROP FUNCTION IF EXISTS public.cofre_engines_disponiveis();
DROP FUNCTION IF EXISTS public.cofre_postura_credencial(text);
DROP FUNCTION IF EXISTS public.cofre_detalhar_ativo(text);
DROP FUNCTION IF EXISTS public.cofre_listar_ativos(text, text, text, text, boolean);
DROP FUNCTION IF EXISTS public.cofre_referenciar_credencial(jsonb, text, uuid, text);
DROP FUNCTION IF EXISTS public.cofre_registrar_verificacao(jsonb, text, uuid, text);
DROP FUNCTION IF EXISTS public.cofre_reativar_ativo(text, text, text, text, uuid, text);
DROP FUNCTION IF EXISTS public.cofre_aposentar_ativo(text, text, text, uuid, text);
DROP FUNCTION IF EXISTS public.cofre_desfazer_relacao(bigint, text, text, uuid, text);
DROP FUNCTION IF EXISTS public.cofre_relacionar(jsonb, text, uuid, text);
DROP FUNCTION IF EXISTS public.cofre_revisar_ativo(text, jsonb, text, uuid, text, text);
DROP FUNCTION IF EXISTS public.cofre_cadastrar_ativo(jsonb, text, uuid, text, text);
DROP FUNCTION IF EXISTS public.cofre_registra_operacao(text, text, text, jsonb, uuid, text);
DROP FUNCTION IF EXISTS public.cofre_idempotencia(text, text, text);
DROP FUNCTION IF EXISTS public.cofre_entrada_hash(text, jsonb);
DROP FUNCTION IF EXISTS public.cofre_snapshot_ativo(text);

-- As tabelas primeiro, porque os gatilhos as referenciam.
DROP TABLE IF EXISTS public.cofre_operacao;
DROP TABLE IF EXISTS public.cofre_verificacao;
DROP TABLE IF EXISTS public.cofre_credencial_referencia;
DROP TABLE IF EXISTS public.cofre_relacao;
DROP TABLE IF EXISTS public.cofre_ativo_revisao;
DROP TABLE IF EXISTS public.cofre_engine_perfil;
DROP TABLE IF EXISTS public.cofre_ativo;
DROP TABLE IF EXISTS public.cofre_tipo;
DROP TABLE IF EXISTS public.cofre_gaveta;

-- Gatilhos e ajudantes por ultimo: eles so ficam sem dono depois das tabelas.
DROP FUNCTION IF EXISTS public.cofre_carimba_atualizacao();
DROP FUNCTION IF EXISTS public.cofre_jsonb_sem_segredo();
DROP FUNCTION IF EXISTS public.cofre_append_only();
DROP FUNCTION IF EXISTS public.cofre_sem_material_de_credencial(text);
DROP FUNCTION IF EXISTS public.cofre_forma_esperada(text);
DROP FUNCTION IF EXISTS public.cofre_localizador_valido(text, text);
DROP FUNCTION IF EXISTS public.cofre_recusa_campo_desconhecido(jsonb, text[], text);
DROP FUNCTION IF EXISTS public.cofre_recusa_chave_sensivel(jsonb, text);
DROP FUNCTION IF EXISTS public.cofre_chave_sensivel(text);
DROP FUNCTION IF EXISTS public.cofre_chave_normalizada(text);
DROP FUNCTION IF EXISTS public.cofre_lista_util(text[], int, int);
DROP FUNCTION IF EXISTS public.cofre_texto_util(text);

DO $conferencia$
DECLARE
  restaram_tabelas int;
  restaram_funcoes int;
BEGIN
  SELECT count(*) INTO restaram_tabelas
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind IN ('r','v') AND c.relname LIKE 'cofre\_%';

  SELECT count(*) INTO restaram_funcoes
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = 'public' AND p.proname LIKE 'cofre\_%';

  IF restaram_tabelas <> 0 OR restaram_funcoes <> 0 THEN
    RAISE EXCEPTION
      'v13_99 deixou % objeto(s) de tabela/view e % funcao(oes) cofre_ de pe',
      restaram_tabelas, restaram_funcoes;
  END IF;

  RAISE NOTICE 'v13_99 OK: nada com prefixo cofre_ restou';
END
$conferencia$;

COMMIT;

NOTIFY pgrst, 'reload schema';
