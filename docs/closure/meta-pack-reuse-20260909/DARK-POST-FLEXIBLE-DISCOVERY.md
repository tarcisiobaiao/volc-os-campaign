# Descoberta de Dark Posts flexíveis — 09/09/2026

## Resultado

O catálogo de posts existentes deixou de exigir `object_story_spec.link_data`
e de rejeitar todo `asset_feed_spec`. A identidade reutilizável é o
`effective_object_story_id` devolvido pelo anúncio, sempre reconferido na conta
e Página selecionadas antes da compilação.

Criativos flexíveis de imagem entram quando possuem:

- uma identidade de post válida e pertencente à Página;
- um único destino HTTPS;
- um único CTA suportado;
- pelo menos uma imagem e os textos exigidos pelo contrato.

Variações de mídia por posicionamento e variações de texto são preservadas no
post original. A interface as identifica e não promete recombinar ou recriar o
criativo. Vídeos e posts com destinos ambíguos continuam recusados.

## Prova real sanitizada

Leitura somente-leitura da primeira página da conta selecionada:

- 100 anúncios observados;
- 100 com `effective_object_story_id`;
- 100 com `asset_feed_spec`;
- 72 criativos de imagem e 27 de vídeo na amostra;
- 44 posts de imagem pertencentes à Página selecionada aceitos pelo catálogo;
- a referência representativa do primeiro post aceito resolveu entre 358
  imagens da biblioteca da mesma conta;
- o objeto direto do post respondeu permissão 10, portanto essa leitura não é
  tratada como pré-condição: a identidade já é lida pelo anúncio autorizado.

Nenhum anúncio, criativo, conjunto ou campanha foi criado ou alterado.

## Contrato de reuso

O compilador continua emitindo `object_story_id` para o criativo e não envia
`object_story_spec`; o anúncio novo nasce no conjunto escolhido e o post não é
recriado. Engajamento pertence ao post original. Métricas históricas do anúncio
de origem não são transferidas para o novo anúncio.

Fontes primárias verificadas:

- `AdCreative` expõe `effective_object_story_id`, `object_story_id` e
  `source_facebook_post_id`:
  https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adcreative.py
- `AdAccount.create_ad_creative` aceita `object_story_id`:
  https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adaccount.py

## Gates

- backend focal: 97 passed;
- frontend focal: 34 passed;
- build Vite: aprovado;
- leitura real sanitizada: aprovada;
- SQL descartável adicional: bloqueado pelo sandbox em `shmget`; nenhuma
  migration foi alterada nesta rodada;
- QA visual autenticado e canário PAUSED com post original: pendentes.
