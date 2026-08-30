-- =============================================================================
-- v11_02 ROLLBACK — derruba o parque criativo e desfaz a blindagem da v11_01
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin (o mesmo papel que aplicou a v11_02)
--
-- ⚠️ ESTE ARQUIVO E RODADO, NAO SO ESCRITO. `scripts/provar-ciclo-v11.sh` o
-- executa contra um Postgres descartavel a cada rodada.
--
-- ⚠️ TRANSACIONAL, como a v11_02 e o rollback da v11_01. Sem `begin`, o
-- `psql -f` autocomita cada `DROP` e um aborto no meio deixa o banco num estado
-- que nem e o de antes nem o de depois. Isso ja aconteceu neste projeto: o
-- rollback da v11_01 destruia as aprovacoes humanas ANTES de "abortar em
-- seguranca". Ou tudo cai, ou nada cai.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO APAGA
-- -----------------------------------------------------------------------------
-- 1. O PARQUE DECLARADO: quais motores existem, o que cada um sabe fazer, quais
--    formatos o canal exige, as 15 skins, as 14 vozes e os 28 gates. Isso e
--    reconstruivel a partir dos manifestos em `docs/creative-engines/` e do
--    `mapa.json` da fabrica, mas a reconstrucao e manual e demorada.
--
-- 2. O RESULTADO DOS GATES POR PECA (`criativo_master_gate`) e o LEDGER DE
--    DIREITOS (`criativo_master_direito`). Estes NAO sao reconstruiveis: sao o
--    registro de que um portao rodou sobre um arquivo especifico, e de qual
--    licenca cobre cada insumo. Perder o segundo e perder a base juridica de
--    uso de uma peca ja publicada.
--
-- 3. A BLINDAGEM: as CHECKs e gatilhos acrescentados a v11_01. Depois deste
--    rollback, o master volta a aceitar reescrita de `disclosure` e `sintetico`
--    num ativo APROVADO, e a entrega volta a aceitar autorizacao de outro
--    pacote. As colunas `motor_id`, `modo_id` e `finalidade_id` somem, e com
--    elas o vinculo entre job e motor registrado.
--
-- EXPORTE ANTES o que nao e reconstruivel:
--
--   \copy public.criativo_master_gate    TO 'criativo_master_gate.csv'    CSV HEADER
--   \copy public.criativo_master_direito TO 'criativo_master_direito.csv' CSV HEADER
--
-- -----------------------------------------------------------------------------
-- O QUE ELE NAO TOCA
-- -----------------------------------------------------------------------------
-- As 10 tabelas da v11_01 continuam de pe, com todos os jobs, masters,
-- renditions e aprovacoes. Este rollback desfaz a v11_02 e SO ela.
-- =============================================================================

\set ON_ERROR_STOP on

begin;

do $guarda$
begin
    if current_user not in ('postgres', 'supabase_admin') then
        raise exception
            'v11_02_rollback deve rodar como postgres ou supabase_admin (atual: %)',
            current_user;
    end if;
end
$guarda$;

-- ── 1. gatilhos e funcoes acrescentados pela v11_02 ──────────────────────────
drop trigger if exists criativo_entrega_autorizada_tg on public.criativo_entrega;
drop trigger if exists criativo_aprovacao_subject_existe_tg on public.criativo_aprovacao;
drop function if exists public.criativo_entrega_autorizada();
drop function if exists public.criativo_aprovacao_subject_existe();

-- ── 2. a imutabilidade do master volta ao escopo da v11_01 ───────────────────
-- Reescrita literal da versao da v11_01: seis colunas, sem medida e sem
-- declaracao. Restaurar por `CREATE OR REPLACE` e nao por `DROP` mantem o
-- gatilho da v11_01 vivo o tempo todo — em nenhum instante o master fica sem
-- protecao nenhuma.
create or replace function public.criativo_master_imutavel()
returns trigger
language plpgsql
as $$
begin
    if new.storage_chave is distinct from old.storage_chave
       or new.content_hash is distinct from old.content_hash
       or new.motor is distinct from old.motor
       or new.motor_versao is distinct from old.motor_versao
       or new.insumo_hash is distinct from old.insumo_hash
       or new.versao is distinct from old.versao
    then
        raise exception
            'criativo_master %: conteudo e procedencia sao imutaveis. Crie uma versao nova (versao=%).',
            old.id, old.versao + 1
            using errcode = 'integrity_constraint_violation';
    end if;

    if new.arquivado_em is not null and old.arquivado_em is null then
        if exists (
            select 1 from public.criativo_aprovacao a
            where a.subject_tipo = 'master'
              and a.subject_id = old.id
              and a.decisao = 'aprovado'
              and a.revogada_em is null
        ) then
            raise exception
                'criativo_master %: nao arquiva master com aprovacao vigente. Revogue a aprovacao antes.',
                old.id
                using errcode = 'integrity_constraint_violation';
        end if;
    end if;

    return new;
end;
$$;

-- ── 3. as CHECKs de blindagem ───────────────────────────────────────────────
alter table public.criativo_master   drop constraint if exists criativo_master_storage_forma;
alter table public.criativo_master   drop constraint if exists criativo_master_raiz_e_outro;
alter table public.criativo_rendition drop constraint if exists criativo_rendition_ordem_temporal;
alter table public.criativo_rendition drop constraint if exists criativo_rendition_pronta_sem_erro;
alter table public.criativo_entrega  drop constraint if exists criativo_entrega_idem_forma;

-- ── 4. as colunas de vinculo ────────────────────────────────────────────────
-- Depois das tabelas de dominio, nao antes: a FK e destas colunas para la.
alter table public.criativo_job       drop column if exists motor_id;
alter table public.criativo_briefing  drop column if exists modo_id;
alter table public.criativo_aprovacao drop column if exists finalidade_id;

-- ── 5. as tabelas do parque, em ordem inversa da dependencia ────────────────
drop table if exists public.criativo_master_direito;
drop table if exists public.criativo_master_gate;
drop table if exists public.criativo_gate;
drop table if exists public.criativo_voz;
drop table if exists public.criativo_skin;
drop table if exists public.criativo_teto_combinado;
drop table if exists public.criativo_exigencia_de_canal;
drop table if exists public.criativo_finalidade;
drop table if exists public.criativo_formato;
drop table if exists public.criativo_modo_de_producao;
drop table if exists public.criativo_motor;

-- ── 6. verificacao embutida, o inverso da secao 12 da v11_02 ────────────────
do $verifica$
declare
    n_tab integer; n_col integer; n_fun integer;
begin
    select count(*) into n_tab from pg_tables
     where schemaname='public' and tablename like 'criativo_%';
    select count(*) into n_col from information_schema.columns
     where table_schema='public'
       and ((table_name='criativo_job' and column_name='motor_id')
         or (table_name='criativo_briefing' and column_name='modo_id')
         or (table_name='criativo_aprovacao' and column_name='finalidade_id'));
    select count(*) into n_fun from pg_proc p join pg_namespace n on n.oid=p.pronamespace
     where n.nspname='public'
       and p.proname in ('criativo_entrega_autorizada','criativo_aprovacao_subject_existe');

    if n_tab <> 10 then
        raise exception 'v11_02_rollback: esperava 10 tabelas (as da v11_01), achei %', n_tab;
    end if;
    if n_col <> 0 then
        raise exception 'v11_02_rollback: sobraram % coluna(s) de vinculo', n_col;
    end if;
    if n_fun <> 0 then
        raise exception 'v11_02_rollback: sobraram % funcao(oes) da v11_02', n_fun;
    end if;

    raise notice 'v11_02_rollback OK: 10 tabelas da v11_01 de pe, parque removido.';
end
$verifica$;

commit;
