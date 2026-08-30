-- ═══════════════════════════════════════════════════════════════════════════
-- A matriz do redator, e o elo com a campanha
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Colunas novas em `pautador_funnel_runs`. Nada existente é alterado.
--
-- ## O que estava faltando, e por quê isso importa
--
-- O worker JÁ calcula o dicionário completo de etapas (`resumo_do_estado`), e o
-- filtro `_COLUNAS` o descarta antes de gravar. Durante os ~45 minutos e ~US$ 2
-- que um funil leva para ser escrito, tudo que a tela conseguia mostrar eram
-- quatro escalares: run_id, páginas planejadas, páginas geradas e custo.
--
-- O operador não via em QUAL das 11 etapas o motor estava, não via que
-- `research_p1` fica até 236 s sem escrever nada, e não via que ~80% do dinheiro
-- já saiu quando a redação da última página fecha — que é exatamente a
-- informação que decide se vale cancelar.
--
-- ## `paginas_publicadas` é o contrato do próximo módulo
--
-- Medido no run de 17/08/2026: o motor recebia do WordPress um objeto com `id`,
-- `slug`, `link` e `status`, extraía SÓ o `id` e descartava o resto. As 5 a 7
-- URLs de um funil publicado precisavam ser REDIGITADAS à mão em
-- `campaign_funnel_urls` — que é a tabela por onde a receita do AdSense é
-- atribuída ao clique comprado, por igualdade de string exata.
--
-- ⚠️ Gravado VERBATIM do que o WP devolveu, nunca remontado a partir do slug: o
-- slug muda em três pontos independentes (a ponte, o `dedupe_slugs` e o próprio
-- WordPress, que acrescenta `-2` em colisão e só conta isso na resposta REST).
--
-- ⚠️ E o `link` de um RASCUNHO não é o permalink: o WP devolveu
-- `https://creditoup.com.br/?post_type=r&p=2146` para a LP. O `/r/<slug>/` só
-- nasce quando o post vai ao ar — por isso `status_wp` viaja junto.
--
-- Aplicar:
--   cat src/sql/pautador/04_matriz_do_redator.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 \
--     root@178.156.196.149 "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"

begin;

alter table public.pautador_funnel_runs
    -- O `step_status` inteiro do motor: {chave: {status, attempts, model_used,
    -- cost_usd, latency_ms, issues[]}}. É a matéria-prima da matriz.
    add column if not exists passos jsonb not null default '{}'::jsonb,

    -- As linhas da matriz: uma por página do plano, com papel, slug, h1 e a
    -- máscara `aplicaveis` (quais colunas fazem sentido NAQUELA página).
    -- Calculada no servidor porque ausência de chave é ambígua por construção:
    -- significa ao mesmo tempo "não se aplica", "a flag está desligada",
    -- "ainda não chegou" e "a página morreu antes". A tela não tem como
    -- desambiguar sozinha.
    add column if not exists paginas jsonb not null default '[]'::jsonb,

    -- Impressão digital de `passos`. A tela pergunta a cada 3s; com isto o
    -- backend responde 304 quando nada mudou, e o worker só grava quando muda —
    -- senão seriam ~900 escritas idênticas por run.
    add column if not exists passos_hash text,

    -- O que o WordPress devolveu, por página. Ver o cabeçalho.
    add column if not exists paginas_publicadas jsonb not null default '[]'::jsonb,

    -- A URL absoluta da landing page, desnormalizada. Não é redundância: é o
    -- campo que o módulo de campanha lê para preencher a URL final do anúncio
    -- sem varrer o jsonb. Um funil tem uma LP; o resto é destino de navegação.
    add column if not exists lp_url text,

    -- Os tetos DESTE run. Hoje o disparo os aceita e os repassa ao motor, mas
    -- não os guarda — então a régua de custo da tela não teria contra o que
    -- comparar o gasto.
    add column if not exists teto_usd numeric(12,6),
    add column if not exists teto_pagina_usd numeric(12,6);

comment on column public.pautador_funnel_runs.passos is
    'O step_status completo do motor. Matéria-prima da matriz páginas × etapas.';
comment on column public.pautador_funnel_runs.paginas_publicadas is
    'Uma entrada por página publicada, VERBATIM da resposta REST do WordPress '
    '(post_id, slug, url_wp, status_wp). Contrato de elo com o módulo de '
    'campanha: é por igualdade de string com campaign_funnel_urls que a receita '
    'do AdSense é atribuída ao clique comprado.';
comment on column public.pautador_funnel_runs.passos_hash is
    'Impressão digital de `passos`, para 304 no polling e para o worker não '
    'gravar linha idêntica a cada 3 segundos.';

commit;
