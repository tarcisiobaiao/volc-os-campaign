# Packs criativos e ações por nível

Implementado na branch operacional existente, sem criar outra worktree.

## Como testar

1. No Assistente Criativo, envie uma geração já autorizada: o formulário é substituído pelo acompanhamento do pedido, com quantidade/modelo/qualidade. Não há percentual inventado nem retry automático.
2. Em **Criativos**, selecione imagens prontas, informe um nome e clique **Salvar seleção**. **Meus packs** lista os snapshots do usuário autenticado.
3. **Preparar campanha** abre um rascunho com as referências do pack reconferidas no servidor. No assistente embutido, **Usar nesta campanha** envia as referências ao rascunho atual. Nenhum desses atos publica.
4. Na campanha demo, expanda conjuntos ou use a hierarquia abaixo. Há atalhos de pausa, duplicação e salvar pack para conjunto e anúncio. Pausa/duplicação abrem propostas; o executor remoto ainda não existe. Salvar pack em demo baixa um exemplo rotulado, sem contaminar o banco.

## Persistência e identidade

`criativo_reuso_pack` está aplicada no Supabase oficial `https://database.agenciavolc.com.br`. Manifestos imutáveis, isolados por proprietário, com unicidade `(owner_id, manifest_sha256)`. Somente backend service_role lê/insere; anon/authenticated não têm grants. Não há update/delete pelo backend.

Packs de Estúdio preservam master, hash dos bytes, job, versão, formato e ponte da estratégia. Quando a ponte existe, preservam também o texto de origem da run concluída; isso não transfere aprovação para outra finalidade. Seleção reconfere propriedade, tipo imagem, arquivamento e hash.

Packs Meta preservam referências internas do read model: conta → campanha → conjunto → anúncio → criativo. Snapshot parcial/ambíguo bloqueia salvamento. A identidade de post não está observada nessa projeção: `post_ref=null`, explicitamente. Referência interna NÃO é o ID externo da Graph API. Não fabricar `object_story_id` a partir de creative_id ou image_hash.

Arquivos continuam no armazenamento local já usado pelo Estúdio. Pack é um manifesto persistido, não upload dos bytes ao Supabase, bucket novo ou backup dos arquivos.

## Limites que continuam abertos

- Registro governado da imagem na conta Meta com avaliação da peça final; o wizard continua bloqueando compilação com masters não registrados.
- Executor real de pausa/duplicação, com autorização, idempotência, tratamento de ambiguidade e read-back. Os novos atalhos NÃO fingem executar.
- Reutilização de post existente/dark post preservando engajamento; exige identidade e elegibilidade na conta/Página de destino.
- Linhagem completa entre master local e cada uso real/publicação Meta. Packs não inventam essa ligação quando ela ainda não foi observada.
- QA autenticado de salvar o pack do usuário e publicação real. A geração bem-sucedida foi informada pelo usuário; nenhuma nova chamada paga nesta rodada.

Leitura posterior do banco oficial confirmou **um master** da operação mostrada:
modelo solicitado `gpt-image-2`, qualidade `medium`, 1080×1350 e 1.807.002 bytes
registrados. `modelo_servido` permanece NULL; não preencher por inferência.
Isso confirma metadados persistidos, não download/revalidação dos bytes nesta rodada.

GAM continua por conjunto. Campanha soma conjuntos; anúncio não recebe uma cópia da receita do conjunto. Duplicação não transfere desempenho histórico.

## Provas

Ver `RECEIPT.json`. SQL provado em PostgreSQL local descartável e no oficial por INSERT/read-back/ROLLBACK. A prova oficial deixou zero linhas de teste. Browser headless usou componentes reais com provider demo e rede externa bloqueada, não uma sessão autenticada do cliente. Loading capturado em 375/768/1440 × claro/escuro; Escape fecha o diálogo; reduced motion retorna animação `none`.

Roadmap: P11-T02, P11-T04 e P11-T06 permanecem **partial**. Nó principal: `concept:asset_lineage`. Nenhum push, deploy, Meta mutate, Google Ads, n8n ou geração paga.

## Reversão

Não há rollback destrutivo automático: packs são snapshots imutáveis. Para recuar o recurso, desabilitar seus pontos de entrada e preservar a tabela. Qualquer remoção de dados requer inventário e autorização específica. Backup prévio do schema registrado no recibo; ele não é backup de dados/imagens.
