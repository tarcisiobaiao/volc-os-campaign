-- ═══════════════════════════════════════════════════════════════════════════
-- O run registra com que FLUXO EDITORIAL foi disparado (S2 · item 2, 30/09/2026)
-- ═══════════════════════════════════════════════════════════════════════════
-- O operador liga o fluxo editorial v2 por funil na tela de disparo do redator
-- (`DispararRedatorDialog`). O backend leva a escolha ao motor (perfil do run →
-- `run.editorial_v2`) e a GRAVA aqui, na linha do run: é o que permite
--   · a tela mostrar e reabrir a última escolha deste card;
--   · a publicação avulsa de uma página (`/redator/runs/{id}/publicar/{n}`)
--     retomar o run com o MESMO fluxo com que ele nasceu;
--   · responder por SQL "este funil foi escrito com qual fluxo?".
--
-- NÃO destrutiva. Padrão `false` = o que toda linha anterior foi.
-- O backend só envia a coluna quando o operador LIGA o fluxo; sem esta migração,
-- o disparo de sempre continua funcionando e o v2 é recusado com 409 explicando.
--
-- Aplicar (mesmo dono das colunas de 04_*, o `postgres` do container):
--   cat src/sql/pautador/06_run_editorial_v2.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 \
--     root@178.156.196.149 "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
--
-- Rollback (o backend volta a funcionar só com o fluxo atual):
--   alter table public.pautador_funnel_runs drop column if exists editorial_v2;
--   notify pgrst, 'reload schema';

begin;

alter table public.pautador_funnel_runs
    add column if not exists editorial_v2 boolean not null default false;

comment on column public.pautador_funnel_runs.editorial_v2 is
    'Fluxo editorial v2 (briefing, revisor, recibo) ligado neste run pelo operador. '
    'Superconjunto do v1; publica só como rascunho, nunca automaticamente.';

commit;

-- O PostgREST precisa enxergar a coluna nova.
notify pgrst, 'reload schema';
