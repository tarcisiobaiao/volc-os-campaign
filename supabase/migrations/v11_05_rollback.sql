begin;
drop table if exists public.criativo_agente_decisao;
alter table if exists public.criativo_agente_operacao
    drop constraint if exists criativo_agente_latest_run_fk;
drop table if exists public.criativo_agente_run;
drop table if exists public.criativo_agente_operacao;
commit;
