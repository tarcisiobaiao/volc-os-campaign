-- =============================================================================
-- v11_07 — ROLLBACK
-- =============================================================================
-- Derruba a ponte peca->job.
--
-- ⚠️ DESTRUTIVO QUANTO A PROCEDENCIA. As imagens e os jobs SOBREVIVEM: eles
-- vivem em `criativo_job` e no parque, e nada aqui os toca. O que se perde e a
-- resposta para "de qual peca aprovada veio esta imagem" — depois disto ela so
-- existiria por adivinhacao no texto do briefing.
--
-- Por isso o pre-voo CONTA as linhas e RECUSA rodar com a ponte populada, a
-- menos que quem executa declare a intencao:
--
--     psql -v confirmar_perda_de_procedencia=1 -f v11_07_rollback.sql
--
-- Uma reversao que apaga trilha em silencio e a que ninguem lembra de ter feito.
-- =============================================================================

\set ON_ERROR_STOP on

-- Default explicito: sem a variavel na linha de comando, a resposta e "nao".
\if :{?confirmar_perda_de_procedencia}
\else
  \set confirmar_perda_de_procedencia 0
\endif

begin;

-- O parametro entra na sessao ANTES do bloco que o le. Na versao anterior deste
-- arquivo o `set` vinha depois, entao o guarda nunca enxergava a confirmacao e
-- o rollback era impossivel de completar mesmo com a intencao declarada.
set local volc.confirmar_perda = :'confirmar_perda_de_procedencia';

do $prevoo$
declare
    n integer;
    confirmado boolean := coalesce(current_setting('volc.confirmar_perda', true), '0') = '1';
begin
    if to_regclass('public.criativo_agente_peca_job') is null then
        raise notice 'v11_07_rollback: a ponte nao existe; nada a fazer';
        return;
    end if;
    select count(*) into n from public.criativo_agente_peca_job;
    if n > 0 and not confirmado then
        raise exception
            'v11_07_rollback RECUSADO: % linha(s) de procedencia seriam perdidas. '
            'Rode com -v confirmar_perda_de_procedencia=1 se essa e a intencao.', n;
    end if;
    if n > 0 then
        raise notice 'v11_07_rollback: perda de % linha(s) de procedencia CONFIRMADA', n;
    end if;
end
$prevoo$;

drop index if exists public.criativo_agente_peca_job_job_ix;
drop index if exists public.criativo_agente_peca_job_operacao_ix;
drop table if exists public.criativo_agente_peca_job;

commit;
