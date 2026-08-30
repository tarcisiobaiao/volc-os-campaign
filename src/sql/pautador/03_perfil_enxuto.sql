-- ═══════════════════════════════════════════════════════════════════════════
-- O perfil de publicação enxuga: sai o que o site já sabe sobre si mesmo
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Três colunas saem de `project_wordpress`. Nenhuma tinha dado (a tabela nasceu
-- em 15/08/2026 e ficou com 0 linhas), então isto não perde nada — é remover
-- campo antes que ele vire órfão, não depois.
--
-- ## Por que cada uma sai
--
-- `cnpj` — o CNPJ já é renderizado pelo TEMA do WordPress, no rodapé do site.
-- Gravá-lo aqui faria o redator carimbar de novo, dentro do conteúdo, o mesmo
-- dado que a página já mostra. Duplicata que só cria chance de divergir.
--
-- `authors` — mesma razão. A assinatura do artigo sai do usuário do WordPress e
-- do tema. Um segundo cadastro de "quem assina", desconectado do primeiro, é a
-- receita para o rodapé dizer uma coisa e o corpo do texto dizer outra.
--
-- `cross_funnel_lps` — o engine já resolve isso melhor sozinho. Em
-- `pipeline/routing.py:80-84` a saída cross-funnel vem de `cross_funnel_targets`,
-- que o `adapters/sitemap_http.py` monta lendo o **sitemap real do site** e
-- pontuando cada URL por léxico: termos do mesmo tópico são redundantes, termos
-- da mesma tarefa com produto diferente são o alvo. A lista do config é só
-- FALLBACK. Manter o campo aqui seria pedir manutenção manual de algo que o
-- site publica sozinho a cada post novo.
--
-- ⚠️ O que fica pendente e NÃO é resolvido por esta migração: o léxico daquele
-- adapter (`_CORE`/`_BRIDGE`) está escrito à mão para o funil de FGTS/crédito —
-- `fgts`, `consignado`, `abono`, `pis`. Para uma vertical diferente ele não
-- pontua nada e o cross-funnel volta ao fallback, que agora está vazio.
--
-- Aplicar:
--   cat src/sql/pautador/03_perfil_enxuto.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 \
--     root@178.156.196.149 "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"

begin;

alter table public.project_wordpress
    drop column if exists cnpj,
    drop column if exists authors,
    drop column if exists cross_funnel_lps;

comment on table public.project_wordpress is
    'Perfil de publicação de um projeto/site: credencial WordPress (token '
    'cifrado no backend) e os dois post types. Identidade editorial (CNPJ, '
    'autor) fica no tema do site; saída cross-funnel vem do sitemap. '
    'RLS ligada e SEM policy: só service_role enxerga.';

commit;
