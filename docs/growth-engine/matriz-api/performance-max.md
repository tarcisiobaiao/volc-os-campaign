# Performance Max — matriz de operação (v25)

Consulta: **26/08/2026**. O que é comum aos quatro canais está em [`comum.md`](./comum.md).

`advertising_channel_type = PERFORMANCE_MAX`, **sem `advertising_channel_sub_type`** para a
campanha padrão; `TRAVEL_GOALS` é o subtipo do PMax com metas de viagem `[alta]` `[X1]` `[X2]`.

---

## 1. Hierarquia — o canal que não tem ad group

```
CampaignBudget                        NÃO compartilhado, período DAILY ou CUSTOM_PERIOD
└── Campaign (PERFORMANCE_MAX)
    ├── CampaignAsset                 BUSINESS_NAME e LOGO quando brand_guidelines_enabled
    ├── CampaignCriterion             location, language, ad_schedule, device, brand(-),
    │                                 keyword(-), webpage(-), location_group
    ├── CampaignConversionGoal        override dos goals do cliente
    ├── ShoppingSetting               (PMax retail / Merchant Center)
    └── AssetGroup  (1..100)
        ├── AssetGroupAsset           liga Asset ↔ AssetGroup com AssetFieldType
        ├── AssetGroupSignal          audience | search_theme | local_services_id
        └── AssetGroupListingGroupFilter   (retail)
```

Não existem `AdGroup`, `AdGroupAd`, `Ad`, nem keywords positivas. Consultar `ad_group`,
`ad_group_ad` ou `keyword_view` **não retorna nada** para PMax `[alta]` `[X3]`.

---

## 2. O que precisa nascer no mesmo mutate — e por quê

> **Em campanha PMax não-retail, o `AssetGroup` e todos os `AssetGroupAsset` que satisfazem os
> mínimos obrigatórios têm de ser criados no mesmo bulk mutate request.** O guia é explícito:
> "`AssetGroup` objects **cannot** be created using the `AssetGroupService` so that the minimum
> number of assets requirement can be met. Instead, use a bulk mutate request along with the
> associated `AssetGroupAsset` objects." `[alta]` `[X4]`

Restrições literais `[alta]` `[X4]`:

| Regra | Texto |
|---|---|
| Atomicidade | "`AssetGroupOperation` requests must be atomic." |
| **`partial_failure`** | "**Partial failure is not supported.**" |
| Batch job | "Asset group resources cannot be modified in a batch process using `AssetGroupOperation`. Instead, use the standard `GoogleAdsService.Mutate` with `AssetGroupService`…" |
| Batch job (exceção) | "`AssetGroupAssetOperation` **may** be used within the `BatchJobService` to link or unlink assets to an asset group." |

Caso retail: `AssetGroup` pode ser criado **sem** cumprir os mínimos — mas assim que se tenta
linkar **um** `Asset` via `AssetGroupAsset`, **todos** os requisitos passam a valer. Ou seja, um
asset group de PMax retail só existe em dois estados: **vazio** ou **completo**. E os assets
obrigatórios precisam ir num **único request, sem `partial_failure`** `[alta]` `[X4]`.

Consequência direta para o VOLC: o caso de uso "adicionar uma imagem ao asset group" não existe
como operação incremental na criação. É um lote fechado.

---

## 3. Campos obrigatórios na criação

| Recurso | Campo | Regra | Conf. |
|---|---|---|---|
| `CampaignBudget` | `explicitly_shared = false` | "The budget cannot be shared" | `[alta]` `[X5]` |
| `CampaignBudget` | `period` | `DAILY` para diário; `CUSTOM_PERIOD` para orçamento total (exige start/end date na campanha) | `[alta]` `[X5]` |
| `CampaignBudget` | `amount_micros` / `total_amount_micros` | mutuamente exclusivos | `[alta]` P |
| `Campaign` | `name`, `advertising_channel_type = PERFORMANCE_MAX` | obrigatórios | `[alta]` P `[X2]` |
| `Campaign` | `campaign_budget` | resource name | `[alta]` `[X2]` |
| `Campaign` | `maximize_conversions` **ou** `maximize_conversion_value` | **as únicas duas** | `[alta]` `[X2]` |
| `Campaign` | `contains_eu_political_advertising` | nos exemplos oficiais v25 | `[média]` `[X2]` |
| `AssetGroup` | `name` | **Required**, 1–128 caracteres, **único dentro da campanha** | `[alta]` P |
| `AssetGroup` | `campaign` | `Immutable` | `[alta]` P |
| `AssetGroup` | `final_urls` | **ao menos uma** | `[alta]` `[X4]` |
| `AssetGroupAsset` | `asset_group`, `asset`, `field_type` | os três; os dois primeiros `Immutable` | `[alta]` P `[X4]` |
| `CampaignAsset` | `BUSINESS_NAME` (exatamente 1) e `LOGO` (≥1) | **quando `brand_guidelines_enabled = true`** | `[alta]` `[X6]` `[X7]` |

Recomendação de orçamento (não é validação): diário ≥ **3×** o CPA/custo por conversão alvo `[alta]` `[X5]`.

---

## 4. Requisitos de asset (tabela oficial, reproduzida)

Fonte: guia oficial de asset requirements de PMax `[alta]` `[X8]`.

### Texto obrigatório

| `AssetFieldType` | Mín | Máx | Limite de caracteres |
|---|---|---|---|
| `HEADLINE` | **3** | **15** | 30 |
| `LONG_HEADLINE` | **1** | **5** | 90 |
| `DESCRIPTION` | **2** | **5** | 90 |

⚠️ Ao menos uma `DESCRIPTION` precisa ter **60 caracteres ou menos**, senão
`AssetGroupError.SHORT_DESCRIPTION_REQUIRED` `[alta]` `[X9]`.

### Imagem obrigatória

| `AssetFieldType` | Mín | Máx | Proporção | Recomendada | Mínima | Peso máx. |
|---|---|---|---|---|---|---|
| `MARKETING_IMAGE` | **1** | **20** | 1.91:1 | 1200 × 628 | 600 × 314 | **5120 KB** |
| `SQUARE_MARKETING_IMAGE` | **1** | **20** | 1:1 | 1200 × 1200 | 300 × 300 | 5120 KB |

### Obrigatórios quando brand guidelines está **desligado**

| `AssetFieldType` | Mín | Máx | Caracteres | Proporção | Recomendada | Mínima | Peso máx. |
|---|---|---|---|---|---|---|---|
| `BUSINESS_NAME` | 1 | 1 | 25 | — | — | — | — |
| `LOGO` | 1 | 5 | — | 1:1 | 1200 × 1200 | 128 × 128 | 5120 KB |

### Imagem opcional

| `AssetFieldType` | Máx | Proporção | Recomendada | Mínima | Peso máx. |
|---|---|---|---|---|---|
| `PORTRAIT_MARKETING_IMAGE` | 20 | 4:5 | 960 × 1200 | 480 × 600 | 5120 KB |
| `LANDSCAPE_LOGO` | 20 | 4:1 | 1200 × 300 | 512 × 128 | 5120 KB |

### Outros opcionais

| `AssetFieldType` | Especificação | Máx por asset group |
|---|---|---|
| `YOUTUBE_VIDEO` | Proporção 16:9, 1:1 **ou** 9:16; **≥ 10 segundos** | **15** |
| `CALL_TO_ACTION_SELECTION` | automático ou escolhido na lista | 1 |
| `MEDIA_BUNDLE` | **< 150 KB** | 1 |

Erros correspondentes: `AssetGroupError.NOT_ENOUGH_*_ASSET`, `StringLengthError.TOO_LONG`,
`MediaUploadError.ASPECT_RATIO_NOT_ALLOWED`, `MediaUploadError.DIMENSIONS_NOT_ALLOWED` `[alta]` `[X9]`.

---

## 5. Brand guidelines — a virada de v21 que muda onde o asset mora

| Fato | Conf. |
|---|---|
| `Campaign.brand_guidelines_enabled` é **`Immutable`**, "Writable only at campaign creation … cannot be modified using standard update operations" | `[alta]` P |
| Está **ligado por default** em novas campanhas PMax desde a v21 | `[alta]` `[X2]` `[X9]` |
| Com ele ligado, `BUSINESS_NAME` e `LOGO` vão para **`CampaignAsset`**, não `AssetGroupAsset` | `[alta]` `[X6]` `[X7]` |
| Migrar campanha existente: método dedicado `CampaignService.EnablePMaxBrandGuidelines` (confirmado no SDK: `enable_p_max_brand_guidelines`, com `EnableOperation`, `BrandCampaignAssets`, `EnablementResult`) | `[alta]` P `[X2]` |
| `Campaign.brand_guidelines` carrega `main_color`, `accent_color` e `predefined_font_family` — este último restrito a: **Open Sans, Roboto, Montserrat, Poppins, Lato, Oswald, Playfair Display, Roboto Slab** (case sensitive) | `[alta]` P |

Erros de esquecer isso: `AssetLinkError.BRAND_ASSETS_NOT_LINKED_AT_CAMPAIGN_LEVEL`,
`CampaignError.REQUIRED_LOGO_ASSET_NOT_LINKED`,
`CampaignError.REQUIRED_BUSINESS_NAME_ASSET_NOT_LINKED` `[alta]` `[X9]`.

---

## 6. Campos imutáveis

| Recurso | Campo | Efeito |
|---|---|---|
| `Campaign` | `advertising_channel_type`, **`brand_guidelines_enabled`** | Decisões de criação sem volta pelo update normal |
| `AssetGroup` | `campaign`, `resource_name` | Asset group não migra de campanha |
| `AssetGroupAsset` | `asset_group`, `asset` | Só `field_type` e `status` são editáveis; trocar o asset = novo link |
| `AssetGroupSignal` | `asset_group` e **todo o `oneof` do sinal** (`audience`, `search_theme`, `local_services_id`, `vertical_ads_item_group_rule_list`) | **Sinal não se edita**: "can only be added to or removed from an AssetGroup" |
| `Asset` | `text_asset`, `youtube_video_asset`, `media_bundle_asset` | conteúdo imutável |
| `CampaignBudget` | `period`, `type_` | trocar diário↔total = novo orçamento |

`[alta]` P + `[X10]`.

---

## 7. Estratégias de lance

| Estratégia | Status em PMax |
|---|---|
| `MAXIMIZE_CONVERSIONS` (com `target_cpa_micros` opcional) | **Suportada** `[alta]` `[X2]` |
| `MAXIMIZE_CONVERSION_VALUE` (com `target_roas` opcional) | **Suportada** `[alta]` `[X2]` |
| **Todas as outras** | **Não suportadas** — "The only supported bidding strategies for Performance Max campaigns are…" `[alta]` `[X2]` |
| **Estratégias de portfólio** (`BiddingStrategyService`) | **Proibidas.** "Portfolio bid strategies … are not supported by Performance Max campaigns. Instead of creating multiple campaigns in a portfolio bidding strategy, use fewer campaigns and more asset groups." `[alta]` `[X2]` |

Orçamento total de campanha em PMax aceita: Target ROAS, Maximize conversion value, Target CPA,
Maximize conversions `[alta]` `[X11]`.

Conversion goals: por default a campanha usa **todos** os `CustomerConversionGoal`. Para restringir,
copie cada um para `CampaignConversionGoal` e ajuste `biddable` (`true` aplica, `false` exclui) `[alta]` `[X12]`.

---

## 8. Targeting e sinais — o que é permitido

Critérios suportados em `CampaignCriterion` `[alta]` `[X13]`: ad schedule, age range, **brand**,
device, **keyword**, language, location, location group, webpage.

| Regra | Conf. |
|---|---|
| **`brand` e `keyword` só podem ser negativos** em PMax | `[alta]` `[X13]` |
| Até **10.000 negative keywords** por campanha PMax | `[alta]` `[X13]` |
| Sem location/location group setados, a campanha **inclui todas as regiões** por default | `[alta]` `[X13]` |
| `webpage` negativo é o mecanismo de exclusão de URL do **final URL expansion** | `[alta]` `[X13]` `[X14]` |
| A final URL do asset group **não pode** ser excluída pelo critério `WEBPAGE` | `[alta]` `[X4]` |
| Idioma incompatível com o país da campanha → `CriterionError.CANNOT_TARGET_LANGUAGE` | `[alta]` `[X13]` |

`AssetGroupSignal` — três tipos de dica (audience, search theme, local services id), adicionados
**um por vez** via `AssetGroupSignal.signal` `[alta]` `[X10]`. PMax padrão funciona sem sinal;
**Local Services PMax exige ao menos um sinal por asset group** e ao menos um critério de
localização positivo (`AssetGroupSignalError.CANNOT_REMOVE_ALL_SIGNALS`,
`CampaignCriterionError.CANNOT_REMOVE_ALL_LOCATIONS_FROM_LOCAL_SERVICES_PMAX_CAMPAIGN`) `[alta]` `[X10]` `[X9]`.

`Audience` pode ser criada com escopo `ASSET_GROUP` para uso num único asset group `[alta]` `[X10]`.

---

## 9. Asset automation e text guidelines

`Campaign.asset_automation_settings[]` é uma lista de pares
`(asset_automation_type, asset_automation_status ∈ {OPTED_IN, OPTED_OUT})` `[alta]` P.

Tipos disponíveis no SDK v25 `[alta]` P:
`TEXT_ASSET_AUTOMATION`, `FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION`,
`GENERATE_VERTICAL_YOUTUBE_VIDEOS`, `GENERATE_SHORTER_YOUTUBE_VIDEOS`,
`GENERATE_ENHANCED_YOUTUBE_VIDEOS`, `GENERATE_LANDING_PAGE_PREVIEW`, `GENERATE_LANDING_PAGE_TEXT`,
`GENERATE_IMAGE_ENHANCEMENT`, `GENERATE_IMAGE_EXTRACTION`, `GENERATE_DESIGN_VERSIONS_FOR_IMAGES`,
`GENERATE_VIDEOS_FROM_OTHER_ASSETS`, `GENERATE_ANIMATED_IMAGES_FROM_OTHER_ASSETS`.

Dependência que gera erro se invertida `[alta]` `[X7]`: para usar final URL expansion é preciso
**opt-in em `TEXT_ASSET_AUTOMATION` primeiro**; opt-out de text asset automation enquanto o URL
expansion está ligado retorna erro. E se o final URL expansion estiver ativo, **não é possível
optar por fora da customização de texto** `[alta]` `[X14]`.

`Campaign.text_guidelines`: `term_exclusions` (máx **25**, cada uma até **30 caracteres**) e
`messaging_restrictions` (máx **40**) `[alta]` P `[X7]`.

---

## 10. Limites

| Limite | Valor | Erro |
|---|---|---|
| Campanhas PMax por conta | **100** | `ResourceCountLimitExceededError.ACCOUNT_LIMIT` |
| Asset groups por campanha | **100** (mínimo **1**) | `ResourceCountLimitExceededError.RESOURCE_LIMIT` |
| Listing group filters por asset group | **1.000** | `ResourceCountLimitExceededError.RESOURCE_LIMIT` |
| Subdivisões de listing group filter por campanha | **7** | `AssetGroupListingGroupFilterError.TREE_TOO_DEEP` |
| Negative keywords por campanha | **10.000** | — |
| `YOUTUBE_VIDEO` por asset group | 15 | — |

`[alta]` `[X15]` `[X13]` `[X8]`. Asset group não é compartilhável entre campanhas `[alta]` `[X4]`.
Não se pode remover o último asset group: `AssetGroupError.CANNOT_REMOVE_ALL_ASSET_GROUPS_FROM_CAMPAIGN` `[alta]` `[X9]`.

---

## 11. Política, eligibility e força de criativo

Além do padrão de `comum.md` §12–13:

| Campo | Natureza | Uso |
|---|---|---|
| `asset_group.primary_status` / `primary_status_reasons` | Output only | Por que o asset group não serve |
| `asset_group.ad_strength` | Output only | Força geral do asset group |
| `asset_group.asset_coverage` | Output only | Cobertura de assets |
| `asset_group_asset.primary_status`, `primary_status_reasons`, **`primary_status_details`** | Output only | Diagnóstico por asset link (`AssetLinkPrimaryStatus`) |
| `asset_group_asset.policy_summary` | Output only | Aprovação por asset |
| `asset_group_asset.source` (`AssetSource`) | Output only | User-created vs automação |
| `asset_group_signal.approval_status` + `disapproval_reasons` | Output only | **Só para search themes**; com audience signal fica vazio |

`[alta]` P.

Ao ler `asset_group.asset_coverage`, se um action item recomendar adicionar vídeo
(`ADD_VIDEO`), o campo `asset_coverage.ad_strength_action_items[].video_aspect_ratio_requirement`
diz **qual proporção** é exigida; se não vier setado, qualquer YouTube video asset serve `[alta]` `[X14]`.

---

## 12. Reporting — a tabela oficial por objetivo

| Objetivo | Recursos |
|---|---|
| Performance e placements de campanha | `campaign`, **`performance_max_placement_view`** |
| Performance de asset group | `asset_group` |
| Performance de asset | `asset_group_asset`, `asset_group_top_combination_view` |
| Retail | `asset_group_product_group_view`, `campaign`, `shopping_performance_view`, `shopping_product` |
| Critério de campanha | `location_view` |
| Termos de busca | **`campaign_search_term_view`** |

`[alta]` `[X3]`.

Segmentos úteis, disponíveis a partir da **v23** `[alta]` `[X16]` `[X17]`:
`segments.ad_network_type` (canal), `segments.ad_using_product_data`, `segments.ad_using_video`.
`campaign.feed_types` indica a vertical (ex.: `HOTEL_PROPERTY` em PMax for Travel) `[alta]` `[X16]`.

Aviso oficial: métricas da UI e da API **não são garantidas idênticas** — a API passa por
deduplicação de cliques antes de publicar `[alta]` `[X17]`.

Não existe performance de anúncio individual em PMax; o substituto é ad strength +
asset coverage do asset group `[alta]` `[X17]`.

---

## 13. Diferenças de PMax para os outros três

| Eixo | PMax |
|---|---|
| Estrutura | **Único canal sem ad group/ad.** Asset group + assets soltos; o Google monta o anúncio |
| Controle de rede | **Nenhum.** Serve em Search, Display, YouTube, Discover, Gmail e Maps sem opt-out |
| Bidding | **Único canal com lista fechada de duas estratégias** e portfólio **proibido** |
| Escrita | **Único canal onde `partial_failure` é explicitamente não suportado** (criação de asset group) e onde há restrição declarada de `BatchJobService` |
| Brand | **Único com `brand_guidelines_enabled` imutável** que muda o nível onde `BUSINESS_NAME`/`LOGO` moram |
| Targeting | Keyword e brand **só negativos**; targeting positivo é substituído por `AssetGroupSignal` |
| Criativo | **Única tabela oficial e completa de asset requirements** dos quatro canais (Search e Display não têm equivalente publicado) |
| Reporting | `performance_max_placement_view`, `asset_group_top_combination_view` e `asset_group_product_group_view` são exclusivos |
| Limites | Único com tetos de campanha/asset group publicados na página de system limits |

---

## Fontes desta página (consultadas em 26/08/2026)

| Ref | URL |
|---|---|
| X1 | https://developers.google.com/google-ads/api/docs/campaigns/overview |
| X2 | https://developers.google.com/google-ads/api/performance-max/create-campaign |
| X3 | https://developers.google.com/google-ads/api/performance-max/reporting |
| X4 | https://developers.google.com/google-ads/api/performance-max/asset-groups |
| X5 | https://developers.google.com/google-ads/api/performance-max/create-budget |
| X6 | https://developers.google.com/google-ads/api/docs/deprecations |
| X7 | https://developers.google.com/google-ads/api/performance-max/assets |
| X8 | https://developers.google.com/google-ads/api/performance-max/asset-requirements |
| X9 | https://developers.google.com/google-ads/api/performance-max/common-errors |
| X10 | https://developers.google.com/google-ads/api/performance-max/asset-group-signals |
| X11 | https://developers.google.com/google-ads/api/docs/campaigns/budgets/overview |
| X12 | https://developers.google.com/google-ads/api/performance-max/conversion-goals |
| X13 | https://developers.google.com/google-ads/api/performance-max/create-campaign-criteria |
| X14 | https://developers.google.com/google-ads/api/performance-max/optimizations |
| X15 | https://developers.google.com/google-ads/api/docs/best-practices/system-limits |
| X16 | https://developers.google.com/google-ads/api/performance-max/campaign-reporting |
| X17 | https://developers.google.com/google-ads/api/performance-max/asset-group-reporting |
| P | Protos do SDK instalado `google-ads` 31.3.0, namespace `v25` |
