# ADR — packs versionados e reaproveitamento de posts Meta

**Estado:** aceita em 09/09/2026 para o contrato local; aceitação remota do reuso ainda não demonstrada.
**Escopo:** biblioteca criativa e montagem de anúncios Meta no VOLC-OS.

## Decisão

Um pack mantém sua identidade e pode receber imagens adicionais, até dez itens.
O backend verifica o proprietário de cada master e guarda copy/proveniência.
O append exige o hash esperado e bloqueia a linha no PostgreSQL: duas edições
concorrentes não se sobrescrevem. Imagens repetidas não são duplicadas.
Cada versão anterior permanece imutável e endereçável por pack + hash.
Uma seleção já fixada num conjunto continua com os mesmos masters e hash; crescer
a biblioteca não amplia silenciosamente uma campanha nem renova sua aprovação.

Pack não equivale a post. Reusar social proof usa a identidade original do post,
resolvida pelo backend na conta/Página autorizadas. O navegador guarda uma referência
opaca, sem token. A compilação V2 reconsulta a origem e exige imagem, copy, CTA e
destino compatíveis; emite object_story_id, não uma reconstrução do post.
O novo anúncio permanece vinculado ao seu novo conjunto, com tracking dinâmico.
Resultados históricos não são transferidos. Ativação não faz parte deste ato.

## Alternativas e consequências

Sobrescrever o manifest sem histórico invalidaria rascunhos antigos; criar outro
pack para qualquer inclusão obrigaria o operador a gerenciar cópias. Mantemos
cabeça editável apenas por append e snapshots imutáveis.
Duplicar uma imagem/criativo não foi tratado como preservação de comentários.

O catálogo inicial de posts admite imagem única com link, copy completa e CTA
compatível. Vídeo, carrossel, flexível e registros sem contexto suficiente não
são oferecidos como elegíveis. Pesquisa paginada usa cache de leitura curto por
proprietário/conta/Página/credencial; compilação nunca usa esse cache como prova.

Não remover a tabela de revisões num rollback de aplicação: rascunhos podem
referenciar seu histórico. Desativar o append na UI mantém leitura das versões.

## Provas e operação

Ver [handoff](../closure/meta-pack-reuse-20260909/HANDOFF.md). As migrations foram
aplicadas no Supabase oficial; testes sintéticos nele usaram ROLLBACK. Nenhuma
criação, upload, geração paga ou ativação Meta foi executada nesta rodada.
