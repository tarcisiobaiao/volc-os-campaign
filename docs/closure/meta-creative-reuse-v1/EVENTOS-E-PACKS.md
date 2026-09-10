# Eventos padrão e seleção de packs

Estado: LOCAL_PARTIAL. Não certifica lançamento em produção.

## Entregue nesta rodada

- Mensuração OPTIMIZE oferece ViewContent (CONTENT_VIEW), Lead, CompleteRegistration, Purchase, AddToCart e InitiateCheckout. Escolher evento padrão limpa conversão personalizada; escolher conversão personalizada limpa evento padrão. A fonte pixel/dataset continua obrigatória e resolvida no backend.
- ViewContent não depende do catálogo de conversões personalizadas. Esta escolha não prova que o evento foi recebido recentemente nem instala CAPI/GTM. Elegibilidade da combinação na conta exige validação Meta.
- Criador oferece Usar pack salvo, com capas, paginação, erro recuperável e link para peças/textos. Seleção passa pela rota autenticada existente, que confere dono e masters; referência em URL é preservada.
- Pack inválido, em leitura ou aguardando registro não libera compilação com imagens anteriores. Cancelar retira a referência da URL. Repetir a seleção permite nova conferência.
- Packs META_SNAPSHOT são referências e não são oferecidos como arquivos para envio.

## Evidência

- 23 testes frontend: seletor, packs, rascunho V2.
- 29 testes da página de criação V2.
- 46 testes de contrato backend, incluindo CONTENT_VIEW -> promoted_object com pixel_id e sem custom_conversion_id.
- Build Vite passou; componente de mensuração atualizado servido em 8080 com HTTP 200. TypeScript global reporta 77 erros, nenhum nos arquivos alterados desta rodada; não foi certificado um baseline global limpo. QA visual autenticado desta alteração não executado.
- Referência primária: https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adpromotedobject.py (CustomEventType.content_view = CONTENT_VIEW).

## Pendências que permanecem

Registro governado master -> imagem da conta com avaliação de política, associação final de imagem/copy aos anúncios e canário PAUSED real continuam separados. A seleção do pack NÃO remove esse bloqueio. Não houve leitura/mutação Meta, geração paga, alteração no Supabase ou push. QA autenticado da jornada completa ainda é necessário.

Memória: P11-T02/P11-T04 e cap_bancada_criativa permanecem partial. A galeria da rodada anterior está descrita em PACK-GALLERY-HANDOFF.md.
