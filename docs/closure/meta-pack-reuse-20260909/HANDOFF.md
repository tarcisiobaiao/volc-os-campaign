# Packs ampliáveis, busca e post original — 09/09/2026

Estado: LOCAL_AND_OFFICIAL_SCHEMA_VERIFIED; reuso remoto e QA visual autenticado pendentes.
Branch: execution/volc-os-operacao-80-20. Base observada: be4483b.
Não houve commit/push nem mudança de autoridade. Alterações preexistentes preservadas.

## Como testar no localhost:8080

1. No Assistente → Criativos, selecione imagens e use **Adicionar seleção a um pack existente**.
   Busque o pack pelo nome, confirme a inclusão e abra o pack atualizado.
2. Em **Meus packs**, abra um pack do Estúdio e use **Adicionar peças da biblioteca**.
   Imagens já incluídas ficam marcadas; a biblioteca tem pesquisa e páginas.
3. Na montagem de anúncios, pesquise imagens pelo nome ou selecione um pack pela busca.
4. Para reusar social proof, escolha **Buscar anúncio existente / Dark Post** no anúncio
   do conjunto desejado. A opção usa o post original e mantém texto/CTA/destino.
   A seleção é persistida no rascunho e força o compilador V2.
5. Revisão humana e confirmação final da criação PAUSED continuam necessárias.
   Não há cópia do desempenho histórico ABO para o anúncio CBO.

## Contratos

- POST /api/criativos/meta/agente/packs/{id}/assets:
  master_refs + expected_manifest_sha256; max dez itens totais, dono/CAS/dedupe.
- GET packs: q por nome + offset; leitura das revisões via manifest_sha256
  no detalhe e seleção. PrepararPackMeta lê explicitamente a versão fixada.
- GET /api/trafego/meta/local/criacao/v2/posts-existentes:
  account_ref/page_ref/q/offset/limit. Retorna referências opacas, origem, copy e preview.
- existingPostRef persiste na função real trafego_meta_campaign_draft_save;
  existing_post_ref chega ao V2. Conta/Página nova limpa a origem e aprovações.
- A compilação resolve a identidade original e o readback exige o mesmo post.
  Nova imagem não é enviada neste caminho.

## Banco oficial

Autoridade conferida: https://database.agenciavolc.com.br.
Aplicadas com ON_ERROR_STOP e COMMIT:
- 20260909215941_creative_pack_append_revisions.sql
- 20260909221222_meta_existing_post_draft.sql

A segunda foi construída a partir da função SAVE vigente, preservando
regulatoryIdentityRef, CAS, proprietário e reset de aprovação. Uma falha sintática
detectada no teste descartável foi corrigida ANTES de aplicá-la oficialmente.

[verify-rollback.sql](verify-rollback.sql) executou no banco oficial e retornou:
PASS: append, owner, CAS, history, opaque post save/read, invalid reference and grants.
Terminou com ROLLBACK. Nenhum pack ou rascunho real foi alterado pelo teste.
RPC de append não está executável por anon/authenticated.

## Verificações

- Backend focal: 49 testes aprovados, incluindo PostgreSQL descartável.
- Frontend focal: 68 testes aprovados em nove arquivos (packs, busca, post, vínculo, seletor acessível).
- Build Vite aprovado; typecheck global ainda tem 76 erros fora dos arquivos novos/alterados desta rodada.
- API 8010 health OK; frontend 8080/packs HTTP 200.
- Rotas novas recusam requisições não autenticadas com 401.
- git diff --check sem erro.
- Regressão ampliada frontend: 228 passaram; uma falha estática preexistente exige texto literal na página MetaCampaignInsightPage (arquivo não alterado nesta rodada).
- Não houve validação visual autenticada; jsdom não equivale a navegador real.

## Limitações honestas

Catálogo de reuso inicial: posts de imagem única com link, copy completa e CTA
suportado. Vídeo/carrossel/flexível e posts sem object_story_spec suficiente não
foram liberados. Não houve prova de nova criação/reuso na Meta real nesta rodada.
A busca de imagens da conta filtra seu catálogo já carregado; packs e posts têm
paginação própria. Biblioteca admite dez peças por pack.

Decisão: [ADR](../../architecture/ADR-META-PACK-VERSIONS-AND-POST-REUSE.md).
Memória: P11-T16; cap_meta_ads. Frescor registrado após reconstrução do grafo.
