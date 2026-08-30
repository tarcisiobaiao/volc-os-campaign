-- =============================================================================
-- v11_03 ROLLBACK — derruba a execução criativa persistida
-- =============================================================================
-- ⚠️ TRANSACIONAL. Sem `begin`, o `psql -f` autocomita cada DROP e um aborto no
-- meio deixa o banco num estado que não é nem o de antes nem o de depois. Já
-- aconteceu neste projeto: o rollback da v11_01 destruía as aprovações humanas
-- ANTES de "abortar em segurança".
--
-- ⚠️ ESTE ARQUIVO É RODADO, NÃO SÓ ESCRITO. `scripts/provar-ciclo-v11_03.sh` o
-- executa a cada rodada, num cluster descartável.
--
-- -----------------------------------------------------------------------------
-- O QUE ELE APAGA, E O QUE NÃO É RECONSTRUÍVEL
-- -----------------------------------------------------------------------------
-- `criativo_render_transicao` é a trilha append-only de quem mudou o quê e
-- quando. Ela é a base de "failed só volta por gesto explícito e AUDITÁVEL":
-- sem ela, a retomada continua explícita e vira invisível. NÃO é reconstruível.
--
-- `criativo_render_recibo` + `artefato` + `validacao` são a prova de que uma
-- peça foi produzida com determinada semente, versões e hashes. Perder isso é
-- perder a capacidade de responder "esta peça é a mesma de ontem?".
--
-- EXPORTE ANTES:
--   \copy public.criativo_render_transicao TO 'transicao.csv' CSV HEADER
--   \copy public.criativo_render_recibo    TO 'recibo.csv'    CSV HEADER
--   \copy public.criativo_render_artefato  TO 'artefato.csv'  CSV HEADER
--
-- As 21 tabelas das v11_01/v11_02 não são tocadas.
-- =============================================================================

\set ON_ERROR_STOP on

begin;

do $guarda$
begin
    if current_user not in ('postgres', 'supabase_admin') then
        raise exception 'v11_03_rollback deve rodar como postgres ou supabase_admin (atual: %)',
            current_user;
    end if;
end
$guarda$;

drop trigger if exists criativo_render_transicao_append_only_tg on public.criativo_render_transicao;
drop trigger if exists criativo_render_retomada_legitima_tg on public.criativo_render_job;
drop trigger if exists criativo_render_recibo_coerente_tg on public.criativo_render_recibo;
-- Gatilho da revisao de 2026-08-29: veredito de job concluido nao muda nem cresce.
drop trigger if exists criativo_render_validacao_imutavel_tg on public.criativo_render_validacao;
drop trigger if exists criativo_render_artefato_imutavel_tg on public.criativo_render_artefato;
drop trigger if exists criativo_render_storage_do_dono_tg on public.criativo_render_artefato;
drop trigger if exists criativo_render_transicao_valida_tg on public.criativo_render_job;

drop function if exists public.criativo_render_transicao_append_only();
drop function if exists public.criativo_render_retomada_legitima();
drop function if exists public.criativo_render_recibo_coerente();
drop function if exists public.criativo_render_validacao_imutavel_apos_render();
drop function if exists public.criativo_render_artefato_imutavel();
drop function if exists public.criativo_render_storage_do_dono();
drop function if exists public.criativo_storage_chave_valida(text, text, uuid, text);
drop function if exists public.criativo_storage_chave(text, uuid, text, text);
drop function if exists public.criativo_render_transicao_valida();

-- Ordem inversa da dependência.
drop table if exists public.criativo_render_validacao;
drop table if exists public.criativo_render_artefato;
drop table if exists public.criativo_render_recibo;
drop table if exists public.criativo_render_transicao;
drop table if exists public.criativo_render_job;

do $verifica$
declare
    n_tab integer; n_fun integer; n_v11 integer;
begin
    select count(*) into n_tab from pg_tables
     where schemaname='public' and tablename like 'criativo_render_%';
    select count(*) into n_fun from pg_proc p join pg_namespace n on n.oid=p.pronamespace
     where n.nspname='public' and p.proname like 'criativo_render_%';
    select count(*) into n_v11 from pg_tables
     where schemaname='public' and tablename like 'criativo_%'
       and tablename not like 'criativo_render_%';

    if n_tab <> 0 then raise exception 'v11_03_rollback: sobraram % tabela(s)', n_tab; end if;
    if n_fun <> 0 then raise exception 'v11_03_rollback: sobraram % funcao(oes)', n_fun; end if;
    if n_v11 <> 21 then
        raise exception 'v11_03_rollback: as 21 tabelas da v11_01/02 viraram %', n_v11;
    end if;
    raise notice 'v11_03_rollback OK: execucao removida, 21 tabelas da v11 intactas.';
end
$verifica$;

commit;
