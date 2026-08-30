-- =============================================================================
-- v11_01 ROLLBACK — derruba o Estudio Criativo (projeto, job, master, aprovacao)
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin (o mesmo papel que aplicou a v11_01)
--
-- ⚠️ ESTE ARQUIVO E RODADO, NAO SO ESCRITO. `scripts/provar-ciclo-v11.sh` o
-- executa contra um Postgres descartavel a cada rodada, no ciclo
-- aplicar -> reverter -> reaplicar.
--
-- A razao e um defeito medido nesta base: o rollback da v9_03 estava
-- documentado como "reaplique a v9_02" e ABORTAVA com `cannot drop columns from
-- view`. Um rollback documentado e nunca rodado so e descoberto no momento em
-- que alguem precisa dele, que e sempre o pior momento.
--
-- -----------------------------------------------------------------------------
-- ⚠️ O QUE ESTE ARQUIVO APAGA, E POR QUE ISSO E MAIS CARO DO QUE PARECE
-- -----------------------------------------------------------------------------
-- Ele apaga TRES coisas que nao voltam sozinhas:
--
--  1. AS CHAVES DE IDEMPOTENCIA DOS JOBS. Elas sao o unico elo entre um pedido
--     e uma geracao que talvez ja tenha sido PAGA ao provider. Depois deste
--     rollback, reenviar o mesmo briefing gera de novo e cobra de novo — o
--     sistema perde a capacidade de reconhecer o que ja produziu.
--
--  2. AS APROVACOES HUMANAS. Quem aprovou, quando, para qual finalidade e com
--     quais ressalvas. Isso e registro de DECISAO, nao dado derivado: nao ha
--     como recalcular a partir dos arquivos.
--
--  3. A PROCEDENCIA. `motor`, `versao`, `insumo_hash`, `content_hash` e a
--     linhagem de versoes. Os ARQUIVOS continuam no object storage — o banco e
--     que deixa de saber de quem eles sao, o que os produziu e se alguem os
--     autorizou. Um bucket cheio de PNGs sem dono e exatamente o "criativo
--     orfao" que `volc_ads/criativo/contrato.py` existe para impedir.
--
-- EXPORTE ANTES. Dez comandos, um minuto, e e a diferenca entre "reaplicar a
-- migration" e "reconstruir a biblioteca a mao a partir de nomes de arquivo":
--
--   \copy public.criativo_brand_pack  TO 'criativo_brand_pack.csv'  CSV HEADER
--   \copy public.criativo_projeto     TO 'criativo_projeto.csv'     CSV HEADER
--   \copy public.criativo_briefing    TO 'criativo_briefing.csv'    CSV HEADER
--   \copy public.criativo_job         TO 'criativo_job.csv'         CSV HEADER
--   \copy public.criativo_job_evento  TO 'criativo_job_evento.csv'  CSV HEADER
--   \copy public.criativo_master      TO 'criativo_master.csv'      CSV HEADER
--   \copy public.criativo_rendition   TO 'criativo_rendition.csv'   CSV HEADER
--   \copy public.criativo_aprovacao   TO 'criativo_aprovacao.csv'   CSV HEADER
--   \copy public.criativo_pacote      TO 'criativo_pacote.csv'      CSV HEADER
--   \copy public.criativo_entrega     TO 'criativo_entrega.csv'     CSV HEADER
--
-- -----------------------------------------------------------------------------
-- O QUE ELE NAO TOCA
-- -----------------------------------------------------------------------------
-- Nada fora da familia `criativo_*`. As series v9 (inventario de Trafego) e v10
-- (intencao e lote) sao independentes por construcao — a v11_01 nao tem uma
-- unica FK para `trafego_*`, e este rollback nao tem um unico DROP fora do
-- prefixo. `scripts/provar-ciclo-v11.sh` prova essa independencia rodando a v9
-- e a v10 antes e conferindo que elas continuam de pe depois.
--
-- Ele tambem NAO apaga arquivo de object storage: o banco nunca guardou bytes.
-- =============================================================================

\set ON_ERROR_STOP on

-- ⚠️ TRANSACAO EXPLICITA, e ela e o conserto de um defeito critico medido em
-- 28/08/2026.
--
-- Sem `begin`, o `psql -f` autocomita CADA `DROP TABLE`. A promessa da secao
-- abaixo ("sem CASCADE de proposito: se sobrar uma FK que este arquivo nao
-- conhece, quero que ele ABORTE") era falsa na pratica: com uma FK externa
-- apontando para `criativo_master`, o aborto chegava DEPOIS de `criativo_
-- aprovacao`, `criativo_entrega`, `criativo_pacote` e `criativo_rendition` ja
-- terem sido apagadas em definitivo.
--
-- O cabecalho classifica as aprovacoes humanas como o item que "nao ha como
-- recalcular a partir dos arquivos". Era exatamente o que a protecao destruia ao
-- proteger. Pior: os tres gatilhos tambem ja tinham caido, entao naquela janela
-- o master ficava MUTAVEL, e uma reaplicacao da v11_01 respondia
-- "v11_01 OK" sobre um banco sem aprovacao e com hash adulterado.
--
-- Com a transacao, ou tudo cai ou nada cai.
begin;

do $guarda$
begin
    if current_user not in ('postgres', 'supabase_admin') then
        raise exception
            'v11_01_rollback deve rodar como postgres ou supabase_admin (atual: %)',
            current_user;
    end if;
end
$guarda$;

-- Gatilhos primeiro: um DROP TABLE ja levaria os triggers junto, mas dropar
-- explicitamente mantem a FUNCAO como unidade separada e torna o arquivo legivel
-- como o inverso exato da secao 10 da migration.
drop trigger if exists criativo_job_chave_imutavel_tg on public.criativo_job;
drop trigger if exists criativo_evento_append_only_tg on public.criativo_job_evento;
drop trigger if exists criativo_aprovacao_peca_pronta_tg on public.criativo_aprovacao;
drop trigger if exists criativo_master_imutavel_tg on public.criativo_master;

drop function if exists public.criativo_job_chave_imutavel();
drop function if exists public.criativo_evento_append_only();
drop function if exists public.criativo_aprovacao_exige_peca_pronta();
drop function if exists public.criativo_master_imutavel();

-- Ordem inversa da dependencia. Sem CASCADE de proposito: se sobrar uma FK que
-- este arquivo nao conhece, quero que ele ABORTE em vez de arrastar junto uma
-- tabela de outra serie que alguem tenha ligado aqui depois.
drop table if exists public.criativo_entrega;
drop table if exists public.criativo_pacote;
drop table if exists public.criativo_aprovacao;
drop table if exists public.criativo_rendition;
drop table if exists public.criativo_master;
drop table if exists public.criativo_job_evento;
drop table if exists public.criativo_job;
drop table if exists public.criativo_briefing;
drop table if exists public.criativo_projeto;
drop table if exists public.criativo_brand_pack;

-- -----------------------------------------------------------------------------
-- VERIFICACAO EMBUTIDA — o inverso da secao 12 da migration
-- -----------------------------------------------------------------------------
do $verifica$
declare
    n_tabelas  integer;
    n_funcoes  integer;
begin
    select count(*) into n_tabelas
      from pg_tables where schemaname = 'public' and tablename like 'criativo_%';

    select count(*) into n_funcoes
      from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname like 'criativo_%';

    if n_tabelas <> 0 then
        raise exception 'v11_01_rollback: sobraram % tabela(s) criativo_*', n_tabelas;
    end if;
    if n_funcoes <> 0 then
        raise exception 'v11_01_rollback: sobraram % funcao(oes) criativo_*', n_funcoes;
    end if;

    raise notice 'v11_01_rollback OK: 0 tabelas, 0 funcoes.';
end
$verifica$;

commit;
