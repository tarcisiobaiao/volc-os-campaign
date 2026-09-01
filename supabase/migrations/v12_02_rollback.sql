-- =============================================================================
-- v12_02 ROLLBACK — derruba o plano canônico de mensuração persistido
-- =============================================================================
-- ⚠️ TRANSACIONAL. Sem `begin`, o `psql -f` autocomita cada DROP e um aborto no
-- meio deixa o banco num estado que não é nem o de antes nem o de depois. Já
-- aconteceu neste projeto: o rollback da v11_01 destruía as aprovações humanas
-- ANTES de "abortar em segurança".
--
-- ⚠️ ESTE ARQUIVO É RODADO, NÃO SÓ ESCRITO. `scripts/provar-ciclo-v12_02.sh` o
-- executa num cluster descartável, no ciclo aplicar → reverter → reaplicar.
-- Rollback documentado e nunca executado é rollback que ninguém tem: o da v9_03
-- estava escrito como "reaplique a v9_02" e ABORTAVA com
-- `cannot drop columns from view` — e só apareceu quando alguém tentou.
--
-- -----------------------------------------------------------------------------
-- O QUE ELE APAGA, E O QUE NÃO É RECONSTRUÍVEL
-- -----------------------------------------------------------------------------
-- `trafego_campanha_plano_de_mensuracao` é a fotografia do que se sabia sobre a
-- mensuração NO INSTANTE em que alguém decidiu criar uma campanha. Ela NÃO é
-- reconstruível: reler a conta hoje devolve o estado de hoje, e o que decide
-- uma auditoria é o estado de então — a meta que valia, a ação que media, o
-- frescor que havia.
--
-- EXPORTE ANTES:
--   \copy public.trafego_campanha_plano_de_mensuracao TO 'plano_de_mensuracao.csv' CSV HEADER
--
-- As tabelas da v9_01, v10_*, v11_* e v12_01 não são tocadas.
-- =============================================================================

\set ON_ERROR_STOP on

begin;

do $guarda$
begin
    if current_user not in ('postgres', 'supabase_admin') then
        raise exception 'v12_02_rollback deve rodar como postgres ou supabase_admin (atual: %)',
            current_user;
    end if;
end
$guarda$;

drop trigger if exists trafego_plano_append_only_tg
    on public.trafego_campanha_plano_de_mensuracao;

drop function if exists public.volc_registrar_plano_de_mensuracao(jsonb);

drop table if exists public.trafego_campanha_plano_de_mensuracao;

-- ⚠️ Depois da tabela, nunca antes: a função é o gatilho da tabela, e derrubá-la
-- primeiro deixaria a tabela sem defesa por um instante dentro da transação.
drop function if exists public.trafego_plano_append_only();

do $verifica$
declare
    n_tab integer; n_fun integer; n_v9 integer; n_v12_01 integer;
begin
    select count(*) into n_tab from pg_tables
     where schemaname='public' and tablename = 'trafego_campanha_plano_de_mensuracao';
    select count(*) into n_fun from pg_proc p join pg_namespace n on n.oid=p.pronamespace
     where n.nspname='public'
       and p.proname in ('trafego_plano_append_only','volc_registrar_plano_de_mensuracao');

    -- ⚠️ Conferir as VIZINHAS, e não só as próprias sobras. O rollback da v12_01
    -- não faz isto, e por isso ele não sabe dizer se derrubou algo além do que
    -- devia. `trafego_campanha` é a âncora de toda a série de tráfego.
    select count(*) into n_v9 from pg_tables
     where schemaname='public' and tablename = 'trafego_campanha';
    select count(*) into n_v12_01 from pg_tables
     where schemaname='public' and tablename like 'trafego_google_inteligencia_%';

    if n_tab <> 0 then
        raise exception 'v12_02_rollback: sobrou % tabela(s)', n_tab;
    end if;
    if n_fun <> 0 then
        raise exception 'v12_02_rollback: sobraram % funcao(oes)', n_fun;
    end if;
    if n_v9 <> 1 then
        raise exception 'v12_02_rollback: public.trafego_campanha (v9_01) sumiu';
    end if;
    if n_v12_01 not in (0, 3) then
        raise exception 'v12_02_rollback: a v12_01 tinha 0 ou 3 tabelas, agora tem %',
            n_v12_01;
    end if;

    raise notice 'v12_02_rollback OK: plano removido, v9_01 e v12_01 intactas.';
end
$verifica$;

notify pgrst, 'reload schema';
commit;
