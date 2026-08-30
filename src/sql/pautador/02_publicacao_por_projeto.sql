-- ═══════════════════════════════════════════════════════════════════════════
-- Publicação por projeto — cada projeto é um site, cada site é um WordPress
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Duas tabelas novas. Nada existente é alterado ou removido.
--
-- ## Por que uma tabela nova, e não colunas na `projects`
--
-- O browser fala DIRETO com o Supabase usando a chave anon (`src/lib/supabase.ts`),
-- e a `projects` está com RLS DESLIGADA — o front lê e escreve nela por essa via
-- (`ProjectsSettings.tsx`, quatro caminhos). Medido em 15/08/2026 com a própria
-- chave anon do `.env`:
--
--     GET /rest/v1/projects?select=id,project_name,domain  ->  HTTP 200
--
-- Ou seja: qualquer coluna que entre na `projects` é legível por quem abrir o
-- devtools do dashboard. Um Application Password do WordPress ali seria uma
-- credencial de admin publicada.
--
-- Ligar RLS na `projects` consertaria a causa, mas quebraria o dashboard inteiro
-- (quatro caminhos de leitura/escrita pelo anon). Isolar o segredo numa tabela
-- nova resolve o problema do redator sem esse risco. A `projects` continua como
-- está — e a dívida fica declarada abaixo.
--
-- ⚠️ DÍVIDA HERDADA, NÃO CRIADA AQUI: `public.incubator_sites` guarda
-- `wp_username` e `wp_app_password` em TEXTO PURO e também está sem RLS. Hoje a
-- tabela está vazia, então nada vazou. No dia em que alguém preencher, a
-- credencial fica pública pelo mesmo caminho. Não foi tocada aqui de propósito
-- (é de outra feature, a incubadora do webgo), mas precisa ser resolvida.
--
-- ## Como o segredo fica protegido — duas camadas independentes
--
-- 1. RLS LIGADA E ZERO POLICY. No Postgres, tabela com RLS ativa e nenhuma
--    policy nega tudo. Só roles com BYPASSRLS atravessam. Conferido no servidor:
--
--        service_role | rolbypassrls = t
--        anon         | rolbypassrls = f
--        authenticated| rolbypassrls = f
--
--    O backend usa service_role (nunca exposta ao browser); anon não enxerga a
--    tabela nem para contar linhas.
--
-- 2. O TOKEN VAI CIFRADO. `wp_app_password_enc` guarda um token Fernet gerado
--    no backend (`app/seguranca/segredo.py`) com uma chave que mora no
--    `backend/.env` e NUNCA entra no banco. Um dump do Postgres — backup vazado,
--    replica mal configurada, acesso ao container — devolve texto ilegível.
--
--    A chave não estar no banco é o ponto inteiro. Cifrar com pgcrypto usando
--    uma chave passada no SQL colocaria a chave no log de statements.
--
-- Aplicar:
--   cat src/sql/pautador/02_publicacao_por_projeto.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 \
--     root@178.156.196.149 "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"

begin;

-- ── 1 · o perfil de publicação do projeto ──────────────────────────────────
--
-- Não é só credencial. O engine redator consome, POR SITE: onde publicar
-- (os dois post types), quem assina (cnpj + autores, que vão no rodapé e na
-- assinatura do texto) e para onde recircular (as LPs de outros funis do mesmo
-- domínio). Sem isso ele não consegue montar a página.
--
-- O que NÃO está aqui, de propósito: `allowed_external`. Ele é POR FUNIL, não
-- por site — os canais oficiais de um funil de FGTS não são os de um funil de
-- cartão. Guardar aqui congelaria como propriedade do site algo que muda a cada
-- tema. Fica no plano do funil.

create table if not exists public.project_wordpress (
    id                  bigserial primary key,
    project_id          integer     not null unique
                        references public.projects(id) on delete cascade,

    -- credencial (o token vem cifrado do backend; ver o cabeçalho)
    wp_url              text        not null,
    wp_username         text        not null,
    wp_app_password_enc text,

    -- fiação do WordPress deste site
    post_type           text        not null default 'rec',
    lp_post_type        text        not null default 'r',

    -- identidade editorial: quem assina o que for publicado
    cnpj                text,
    authors             jsonb       not null default '[]'::jsonb,

    -- LPs de OUTROS funis no MESMO domínio, usadas como saída cross-funnel da
    -- página terminal. Vazio é válido: o primeiro funil de um site não tem para
    -- onde recircular, e isso é informação, não erro.
    cross_funnel_lps    text[]      not null default '{}',

    -- último teste de conexão. Existe para a tela poder dizer "funciona" sem
    -- nunca exibir o token: o operador vê o usuário e a data, não a senha.
    conexao_ok          boolean,
    conexao_em          timestamptz,
    conexao_detalhe     text,

    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

comment on table public.project_wordpress is
    'Perfil de publicação de um projeto/site: credencial WordPress (token '
    'cifrado no backend), post types, identidade editorial e saídas '
    'cross-funnel. RLS ligada e SEM policy: só service_role enxerga.';

comment on column public.project_wordpress.wp_app_password_enc is
    'Application Password do WordPress cifrado com Fernet em app/seguranca/'
    'segredo.py. A chave mora no backend/.env e NUNCA no banco — um dump do '
    'Postgres não devolve o token. NULL = credencial ainda não cadastrada.';

comment on column public.project_wordpress.cross_funnel_lps is
    'Slugs de LPs de outros funis no mesmo domínio. A página terminal do funil '
    'recircula para uma delas em vez de morrer sem saída.';

-- ── 2 · uma linha por execução do redator ──────────────────────────────────
--
-- Por que tabela de execuções e não uma coluna `project_id` no card:
--
-- O mesmo tema vira funil em MAIS DE UM site. É a estratégia declarada — o que
-- deu certo num mercado se replica nos outros (BR, MX, CO, CL, PE, AR, ES). Uma
-- coluna no card obrigaria a duplicar o card por mercado, e aí a mesma pauta
-- viraria N cards sem relação entre si, cada um com sua medição.
--
-- Aqui o card continua único e a execução é que se multiplica. De quebra, o
-- custo de cada run fica gravado ao lado do resultado — que é o número que
-- decide se a arbitragem fecha.

create table if not exists public.pautador_funnel_runs (
    id                 bigserial primary key,
    opportunity_id     bigint      not null
                       references public.pautador_entity_opportunities(id) on delete cascade,
    project_id         integer     not null references public.projects(id),

    -- o run_id do engine (slug da LP). NULL enquanto a execução está na fila.
    run_id             text,

    status             text        not null default 'queued',

    -- `rascunho` = gerou os artefatos e não tocou o WordPress.
    -- `publicado` = escreveu no site (sempre como draft do WP, nunca live).
    modo               text        not null default 'rascunho',

    custo_usd          numeric(12,6),
    paginas_planejadas integer,
    paginas_geradas    integer,
    erro               text,

    -- caminhos/URLs do que saiu: elementor.json, gutenberg.html, webp, report.
    artefatos          jsonb       not null default '{}'::jsonb,

    criado_em          timestamptz not null default now(),
    atualizado_em      timestamptz not null default now(),

    constraint pautador_funnel_runs_status_ck
        check (status in ('queued', 'running', 'done', 'failed', 'cancelled')),
    constraint pautador_funnel_runs_modo_ck
        check (modo in ('rascunho', 'publicado'))
);

create index if not exists pautador_funnel_runs_opp_idx
    on public.pautador_funnel_runs (opportunity_id, criado_em desc);
create index if not exists pautador_funnel_runs_projeto_idx
    on public.pautador_funnel_runs (project_id, criado_em desc);

comment on table public.pautador_funnel_runs is
    'Uma linha por execução do redator: qual card, para qual site, quanto '
    'custou e o que saiu. O mesmo card pode ter N execuções — é assim que o '
    'mesmo tema vira funil em vários mercados sem duplicar a pauta.';

-- ── 3 · a trava: RLS ligada, nenhuma policy ────────────────────────────────
--
-- Sem policy, `enable row level security` nega TUDO para quem não tem
-- BYPASSRLS. Não é omissão — é a configuração. O `revoke` abaixo é a segunda
-- camada: mesmo que alguém adicione uma policy por engano no futuro, o
-- privilégio de tabela continua negado a anon.

alter table public.project_wordpress    enable row level security;
alter table public.pautador_funnel_runs enable row level security;

revoke all on public.project_wordpress    from anon, authenticated;
revoke all on public.pautador_funnel_runs from anon, authenticated;

commit;
