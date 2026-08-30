-- ═══════════════════════════════════════════════════════════════════════════
-- A aresta de volta: da campanha para a execução do redator
-- ═══════════════════════════════════════════════════════════════════════════
--
-- ⚠️ ESTE ARQUIVO PRECISA DO DONO DA TABELA. `public.campaigns` pertence a
-- `supabase_admin`, e o `postgres` do container NÃO é superusuário
-- (`rolsuper = f`) — um `ALTER TABLE campaigns` como postgres falha com
-- "must be owner of table campaigns" e, dentro de uma transação, derruba a
-- migração INTEIRA junto. Foi o que aconteceu em 17/08/2026, levando embora as
-- colunas de `pautador_funnel_runs` que já tinham sido criadas no mesmo bloco.
--
-- Por isso ele está separado do `04_*`: cada migração com um dono só.
--
-- Aplicar (note o -U supabase_admin):
--   cat src/sql/pautador/05_campanha_aponta_para_o_run.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 \
--     root@178.156.196.149 "docker exec -i supabase-db psql -U supabase_admin -v ON_ERROR_STOP=1"

begin;
-- ── a aresta de volta: da campanha para o run ──────────────────────────────
--
-- A direção é essa (a campanha aponta para o run) porque um run pode gerar
-- VÁRIAS campanhas: Search, Display, retomadas. Sem ela, responder "aquele tema
-- deu certo?" por SQL é impossível — o ciclo pauta → funil → campanha →
-- resultado fica sem o salto do meio.
alter table public.campaigns
    add column if not exists funnel_run_id bigint
        references public.pautador_funnel_runs(id) on delete set null;

create index if not exists campaigns_funnel_run_idx
    on public.campaigns (funnel_run_id) where funnel_run_id is not null;

comment on column public.campaigns.funnel_run_id is
    'Qual execução do redator produziu as páginas desta campanha. Fecha o ciclo '
    'card -> run -> campanha -> RPM/CPC. NULL para as campanhas anteriores ao '
    'redator, que foram criadas à mão.';

commit;
