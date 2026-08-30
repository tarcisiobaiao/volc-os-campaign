# ADR — Demand Gen monta e prova, mas não cria

**Estado:** parcial em 29/08/2026  
**Escopo:** primeira onda executora de Google Ads Demand Gen  
**Fonte versionada:** `docs/growth-engine/matriz-api/demand-gen.md` (API v25,
consulta registrada em 26/08/2026)

## Decisão

O VOLC passa a reconhecer três capacidades distintas por canal:

1. inventariar;
2. montar e provar por `validate_only`;
3. criar por mutação real.

Demand Gen recebe apenas as duas primeiras. O builder participa do mesmo
`volc_ads/subir.py`, mas fica exclusivamente no registro de provadores. O
registro de criação real continua limitado a Search e Display; `/subir`, o
canário e a função final de mutação recusam Demand Gen antes de qualquer trava,
recibo ou chamada externa.

O rótulo de canal no `Preparo` não é autoridade de execução. O selo liga
`customer_id`, `login_customer_id`, o canal extraído de
`campaign_operation.create`, o tipo/verbo e o SHA-256 individual de cada
`MutateOperation`, além da impressão combinada e ordenada. Na entrada de
`subir()`, tudo é derivado novamente das operações. Relabeling, troca de MCC,
canal, tipo ou conteúdo falham antes da trava, do recibo e do cliente de
mutação.

A porta HTTP de prova depende simultaneamente de identidade com capacidade, da
flag de servidor `VOLC_DEMAND_GEN_VALIDATE_ONLY=on` e da sonda local dos protos
v25. Ausência, grafia diferente, capacidade não administrativa, namespace ou
campo incompatível mantêm a porta fechada. A flag nasce desligada e não
autoriza `/subir`.

A bancada do frontend descreve as superfícies e a disponibilidade dessa porta,
mas não redireciona para `NovaCampanhaPage`: o cockpit atual coleta o contrato
de Search e não sabe obter os bytes aprovados pelo Estúdio. Transformá-lo por
similaridade produziria outro canal. Nesta onda, o consumidor utilizável é o
contrato HTTP tipado; um formulário visual próprio permanece lacuna explícita.

## Grafo montado

Um único lote, com `partial_failure=false`, preserva a ordem:

`CampaignBudget → Campaign PAUSED → AdGroup PAUSED → critérios → Asset → AdGroupAd PAUSED`

Budget, campanha, grupo, assets e anúncio usam as faixas temporárias já
declaradas em `campanha/comum.py`. Imagens novas nascem no mesmo lote e são
referenciadas pelo anúncio; não existe upload prévio que possa deixar asset
órfão.

## Escolhas explícitas desta onda

- `advertising_channel_type=DEMAND_GEN`, sem subtype;
- somente `DemandGenMultiAssetAdInfo`;
- `MAXIMIZE_CONVERSIONS` sem `target_cpa_micros`; ausência não vira zero;
- `Campaign.demand_gen_campaign_settings.upgraded_targeting` é obrigatório e
  explícito porque é imutável;
- o ad group não recebe `type_`;
- channel controls ocupam explicitamente um ramo: `ALL_CHANNELS`,
  `ALL_OWNED_AND_OPERATED_CHANNELS` ou `SELECTED_CHANNELS` com ao menos uma das
  flags versionadas na matriz;
- `channel_config` é output-only e nunca é escrito;
- audiência positiva aceita apenas resource names remotos, positivos e da
  conta do pedido, exatamente na forma canônica; duplicatas depois da
  canonização são recusadas;
- o adaptador HTTP não atravessa o montador Search: keywords, grupos,
  critérios e negativas Search preenchidos são recusados, nunca apagados ou
  reinterpretados como intenção;
- intenção e exclusão são campos próprios. Itens não vazios falham fechado
  nesta onda; nenhum texto de intenção vira Audience por analogia;
- país, idioma e vertical precisam vir da origem publicada/confirmada. Uma URL
  manual pode escolher destino, mas não inventa BR, português ou vertical;
- assets passam pela autoridade existente do Estúdio e por
  `criativo_ponte.py`. O router mede os bytes e não mantém uma segunda régua;
- `Linhagem` declarada pelo chamador não é aprovação. Imagem Demand Gen exige
  `ReciboAssetAprovado` emitido pela ponte; reuso remoto exige também os bytes
  preservados no catálogo. Antes do cliente, o builder reconfere emissor,
  canal, papel, resource name, SHA-256, quantidade de bytes, MIME e dimensões;
- sitelinks, callouts, structured snippet, long headline e escolhas de Search
  ou automação sem operação correspondente são recusados, nunca omitidos. Na
  fronteira HTTP, defaults do modelo só viram decisão quando vieram
  explicitamente no pedido;
- pelo menos uma imagem horizontal ou quadrada, no máximo 20 imagens de
  marketing somadas e de um a cinco logos quadrados;
- o piso local do logo é 144×144 e 150 KB, pois o Help Center versionado diz
  144 enquanto o proto diz 128; 144 satisfaz as duas fontes;
- `cpc_inicial` não produz lance em Demand Gen e vira aviso explícito;
- o brief não conhece a moeda da conta. O código não inventa nem converte o
  mínimo diário publicado; o `validate_only` é o juiz desse requisito.

Carrossel, vídeo responsivo e anúncio de produto não são defaults alternativos.
Cada um exige outro contrato e permanece não suportado.

## Ausências preservadas

`None`, lista vazia e valor preenchido continuam estados distintos:

- `None` em targeting, canais, audiência, intenção ou exclusão reprova por dado
  incompleto;
- lista vazia em audiência, intenção ou exclusão é vazio confirmado;
- vazio confirmado de intenção/exclusão é aceito; item preenchido é atualmente
  não suportado;
- tCPA ausente continua ausente no proto;
- falha local impede até a construção do cliente; falha de prova continua sendo
  falha, nunca sucesso ou autorização.

## Lacunas que mantêm o estado parcial

O runtime hermético disponível nesta implementação contém `google-ads 31.3.0`
com o namespace v25. A sonda importou os namespaces gerados, instanciou e
serializou offline `CampaignBudget`, `Campaign`, `CampaignCriterion`, `AdGroup`,
`AdGroupCriterion`, `Asset`, `AdGroupAd`, `DemandGenMultiAssetAdInfo`,
`AdImageAsset` e `AdTextAsset`, incluindo um `MutateOperation` de cada família
emitida pelo builder. A suíte também serializou deterministicamente o grafo
real montado. Nenhum cliente autenticado, credencial ou chamada à API foi
usado.

O estado só pode avançar depois de:

1. a matriz versionada e o SDK continuarem concordando com os campos emitidos;
2. existir persistência/reidratação autorizada do recibo de catálogo, sem
   transformar procedência declarada em aprovação;
3. uma pessoa autorizar `validate_only` numa conta de teste;
4. o veredito e o request id dessa prova serem preservados como evidência.

Mesmo depois dessa prova, criação real de Demand Gen continua fora desta ADR e
exige decisão separada.
