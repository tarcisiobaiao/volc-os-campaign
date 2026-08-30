-- ═══════════════════════════════════════════════════════════════════════════
-- Coluna "Em validação" — onde o palpite vira medição, com a proveniência junto
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Duas tabelas novas e uma coluna. Nada existente é alterado ou removido.
--
-- `pautador_entity_axes` é a peça que dura mais que o recurso que a criou. Ela
-- não foi desenhada como experimento — foi desenhada para gravar a proveniência
-- de cada número no dia em que ele foi medido. É o que, daqui a seis meses,
-- permite perguntar se o motor acertava. Não a simplifique "porque ninguém
-- consulta": é ela que transforma medição paga em ativo.
--
-- Uma linha por (oportunidade, eixo). A tabela é, deliberadamente, a assinatura
-- de `motor_pautas.espaco.posicionar()`:
--
--     posicionar(termo, pais=..., medidos={eixos com proveniencia='medido'},
--                **{eixo: nivel for eixos com nivel not null})
--
-- Aplicar:
--   cat src/sql/pautador/01_validacao_eixos.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 \
--     root@178.156.196.149 "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"

begin;

-- ── 1 · os eixos, com proveniência e prova ──────────────────────────────────

create table if not exists public.pautador_entity_axes (
    id              bigserial primary key,
    opportunity_id  bigint      not null,
    eixo            text        not null,
    nivel           text,
    proveniencia    text        not null,
    -- A prova que sustenta o nível. Não é enfeite: um eixo medido sem a série
    -- que o sustenta volta a ser declaração na primeira vez que alguém duvidar.
    --   volume          -> {cluster: [...], soma_mensal, serie: [...], termo_cabeca}
    --   reposicao       -> {media, amplitude, tendencia, meses}
    --   vacuo           -> {termo, dominios: [...], oficiais, portais, etv_por_dominio}
    --   formato_consumo -> {termo, unicos, facilitador, social, oficial, r_fac, r_of}
    evidencia       jsonb       not null default '{}'::jsonb,
    -- Preenchido só quando proveniencia = 'ausente'. `buraco_de_base` é o caso
    -- mais importante: o Labs devolve status 20000, sem erro, com o item
    -- simplesmente fora do array. Tratar isso como volume zero mata tema vivo
    -- (`cesantias`, CO, 40.500 buscas/mês reais).
    motivo_ausencia text,
    medido_em       timestamptz not null default now(),

    constraint pautador_entity_axes_uk unique (opportunity_id, eixo),

    constraint pautador_entity_axes_proveniencia_ck
        check (proveniencia in ('medido', 'julgado', 'ausente')),

    -- Ausente não tem nível, e nível não é ausente. Sem isto, um eixo pode
    -- entrar na média geométrica dizendo que foi medido quando não foi — que é
    -- exatamente o erro que `PORTOES_EXIGEM_MEDICAO` existe para impedir.
    constraint pautador_entity_axes_coerencia_ck
        check (
            (proveniencia = 'ausente' and nivel is null and motivo_ausencia is not null)
            or (proveniencia <> 'ausente' and nivel is not null)
        ),

    constraint pautador_entity_axes_eixo_ck
        check (eixo in ('ignorancia', 'engajamento', 'opacidade', 'reposicao',
                        'volume', 'spread', 'densidade', 'formato_consumo',
                        'vacuo', 'producao'))
);

create index if not exists pautador_entity_axes_opp_idx
    on public.pautador_entity_axes (opportunity_id);
create index if not exists pautador_entity_axes_eixo_idx
    on public.pautador_entity_axes (eixo, nivel);

comment on table public.pautador_entity_axes is
    'Um eixo do motor por linha, com proveniência (medido|julgado|ausente) e a '
    'prova. É a assinatura de motor_pautas.espaco.posicionar() em forma de tabela.';
comment on column public.pautador_entity_axes.proveniencia is
    'medido = API mediu o mundo · julgado = LLM leu a pessoa · ausente = não deu, '
    'e o motivo está em motivo_ausencia. A fronteira entre os dois primeiros não '
    'é negociável: nenhuma API mede o buraco de conhecimento de quem busca.';

-- ── 2 · a execução, para auditar custo e perda silenciosa ───────────────────

create table if not exists public.pautador_validation_runs (
    id              bigserial primary key,
    lote_id         uuid        not null,
    modo            text        not null,
    opportunity_ids bigint[]    not null default '{}',
    -- Custo vem de tasks[0].cost, chamada a chamada, DENTRO do processo. Um
    -- contador compartilhado entre processos paralelos reportou 8x a 25x o
    -- consumo próprio de cada sonda — o número tem que vir da própria resposta.
    custo_usd       numeric(12,6) not null default 0,
    -- O que a mesma validação teria custado card a card. Existe para o relatório
    -- conseguir dizer, em números, por que o lote é o caminho padrão: a base de
    -- US$ 0,012 por chamada domina na cauda curta, e arrastar 20 cards um a um
    -- paga base cheia 20 vezes.
    custo_individual_estimado_usd numeric(12,6),
    endpoints       jsonb       not null default '[]'::jsonb,
    -- A defesa contra a perda silenciosa: pedido contra devolvido, sempre.
    keywords_pedidas    integer not null default 0,
    keywords_devolvidas integer not null default 0,
    faltantes       jsonb       not null default '[]'::jsonb,
    erros           jsonb       not null default '[]'::jsonb,
    duracao_ms      integer,
    criado_em       timestamptz not null default now(),

    constraint pautador_validation_runs_modo_ck check (modo in ('lote', 'individual'))
);

create index if not exists pautador_validation_runs_lote_idx
    on public.pautador_validation_runs (lote_id);
create index if not exists pautador_validation_runs_criado_idx
    on public.pautador_validation_runs (criado_em desc);

comment on table public.pautador_validation_runs is
    'Uma linha por execução da validação. Guarda custo real (tasks[0].cost), o '
    'contraste pedido x devolvido, e o custo que o modo individual teria tido.';

-- ── 3 · o resumo desnormalizado que o board lê ─────────────────────────────
-- Coluna aditiva e anulável na tabela viva. A verdade durável são as duas
-- tabelas acima; esta é só a leitura rápida do card, para o board não precisar
-- de join. `apto` NÃO ordena e NÃO barra card — ver o comentário abaixo.

alter table public.pautador_entity_opportunities
    add column if not exists validacao jsonb;

comment on column public.pautador_entity_opportunities.validacao is
    'Resumo da coluna "Em validação": {apto, motivo, indice, cobertura, perfil, '
    'alertas[], eixos:{eixo:{nivel,proveniencia}}, custo_usd, validado_em}. '
    'É EXIBIÇÃO, não decisão: nada aqui ordena o board nem barra card. '
    'A exceção declarada é `apto:false` por canal não medido — sem SERP não há '
    'como saber se o funil fecha naquele mercado, e eixo ausente SAI da média '
    'geométrica, ou seja o silêncio subiria a nota. O card fica fora da fila '
    'com o motivo gravado, e continua visível e arrastável.';

commit;
