# Demand Gen — matriz de operação (v25)

Consulta: **26/08/2026**. O que é comum aos quatro canais está em [`comum.md`](./comum.md).

`advertising_channel_type = DEMAND_GEN`. **Nenhum `advertising_channel_sub_type` deve ser
setado** `[alta]` `[G1]` `[G2]`.

Superfícies: YouTube (incluindo Shorts), Discover, Gmail, Google Maps e Google Display Network `[alta]` `[G3]` `[G4]`.

---

## 1. Hierarquia e ordem de criação

```
CampaignBudget                       NÃO pode ser compartilhado
└── Campaign (DEMAND_GEN)            demand_gen_campaign_settings.upgraded_targeting (immutable)
    ├── CampaignCriterion            (ou no ad group, se upgraded_targeting = true)
    ├── ShoppingSetting.merchant_id  (só para product ads)
    └── AdGroup  (SEM type_)         demand_gen_ad_group_settings.channel_controls
        ├── AdGroupCriterion         audience (AudienceInfo), location, language, listing_group
        └── AdGroupAd
            └── um de:
                Ad.demand_gen_multi_asset_ad
                Ad.demand_gen_carousel_ad
                Ad.demand_gen_video_responsive_ad
                Ad.demand_gen_product_ad
```

Ordem oficial `[alta]` `[G1]`: (1) orçamento → (2) campanha + bidding → (3) ad group **sem type**
→ (4) audiences → (5) assets e ads.

> A doc **recomenda** criar tudo num único `GoogleAdsService.Mutate`, "for efficiency and to
> prevent orphaned entities" `[alta]` `[G1]`. É recomendação, não erro se separado — diferente de
> PMax, onde a atomicidade do asset group é obrigatória.

Como o request usa IDs temporários encadeados, **`partial_failure` não deve ser usado** nele —
regra geral de `comum.md` §4.

---

## 2. Campos obrigatórios na criação

| Recurso | Campo | Regra | Conf. |
|---|---|---|---|
| `CampaignBudget` | `name` | ver `comum.md`/`search.md` §2 | `[alta]` P |
| `CampaignBudget` | `amount_micros` | diário; **`explicitly_shared` deve ser `false`** — "Demand Gen campaign can't use a shared budget" | `[alta]` `[G1]` |
| `CampaignBudget` | `total_amount_micros` + `period = CUSTOM_PERIOD` | alternativa (orçamento total de campanha) | `[alta]` `[G1]` `[G5]` |
| `CampaignBudget` | `delivery_method` | `STANDARD` nos exemplos; default `STANDARD` | `[alta]` P |
| `Campaign` | `name`, `advertising_channel_type = DEMAND_GEN` | obrigatórios | `[alta]` P `[G1]` |
| `Campaign` | `campaign_budget` | resource name | `[alta]` `[G1]` |
| `Campaign` | esquema de lance | ver §5 | `[alta]` `[G1]` |
| `Campaign` | `contains_eu_political_advertising` | nos exemplos oficiais | `[média]` `[G1]` |
| `AdGroup` | `name`, `campaign` | obrigatórios | `[alta]` P |
| `AdGroup` | `type_` | **não setar** — "Create an ad group without a type" | `[alta]` `[G1]` |
| `AdGroupAd` | `ad_group`, `ad` | ambos `Immutable` | `[alta]` P |
| `Ad` | `final_urls` | ao menos uma | `[média]` `[G1]` |

### ⚠️ Orçamento mínimo obrigatório desde 01/04/2026

**5 USD/dia** (ou equivalente em moeda local) para **todas** as campanhas Demand Gen. Criação ou
update que resulte em diário abaixo disso **falha**, com detalhe em
`details.budget_per_day_minimum_error_details`. Campanhas existentes abaixo do mínimo só são
afetadas quando o orçamento ou a duração forem editados `[alta]` `[G6]`.

Recomendação oficial (não é validação): orçamento diário ≥ **15×** o target CPA esperado `[alta]` `[G1]`.

---

## 3. Os quatro tipos de anúncio e seus assets

Todos os números vêm das docstrings do proto instalado `[alta]` P, salvo indicação.

### `DemandGenMultiAssetAdInfo`

| Campo | Mín | Máx | Dimensão mín. | Proporção |
|---|---|---|---|---|
| `marketing_images` | obrigatório **se** `square_marketing_images` ausente | teto **combinado 20** | 600 × 314 | 1.91:1 (±1%) |
| `square_marketing_images` | obrigatório **se** `marketing_images` ausente | combinado 20 | 300 × 300 | 1:1 (±1%) |
| `portrait_marketing_images` | 0 | combinado 20 | 480 × 600 | 4:5 (±1%) |
| `tall_portrait_marketing_images` | 0 | combinado 20 | **600 × 1067** | **9:16 (±1%)** |
| `logo_images` | **1** | **5** | 128 × 128 | 1:1 (±1%) |
| `classic_display_images` | 0 | **20** (contagem própria) | — | — |
| `headlines` | **1** | **5** | — | largura máx. 30 |
| `descriptions` | **1** | **5** | — | largura máx. 90 |
| `business_name` | **1 (Required)** | 1 | — | largura máx. 25 |
| `call_to_action_text` | 0 | 1 | — | — |

Formatos de imagem válidos: **GIF, JPEG, PNG**.

### `DemandGenCarouselAdInfo`

| Campo | Regra |
|---|---|
| `business_name` | **Required** |
| `logo_image` | **Required**, mín. 128 × 128, 1:1 (±1%) |
| `headline` | **Required** (um só) |
| `description` | **Required** (uma só) |
| `carousel_cards` | **Required. Mín 2, máx 10** |
| `call_to_action_text` | opcional |

Cada card é um `AdDemandGenCarouselCardAsset` apontando para um `Asset` do tipo
`demand_gen_carousel_card_asset` (`AssetFieldType.DEMAND_GEN_CAROUSEL_CARD`, e o campo do asset é
**`Immutable`**). Dentro do card: `marketing_image_asset` (1.91:1) **e/ou**
`square_marketing_image_asset` — pelo menos um dos dois é obrigatório; `portrait_marketing_image_asset`
(4:5) é opcional; `headline` é **Required** `[alta]` P.

### `DemandGenVideoResponsiveAdInfo`

| Campo | Regra |
|---|---|
| `videos` | **Required** — lista de `AdVideoAsset` (YouTube) |
| `logo_images` | **Required**, mín. 128 × 128, 1:1 (±1%), GIF/JPEG/PNG |
| `business_name` | **Required** (`AdTextAsset`) |
| `headlines`, `long_headlines`, `descriptions` | listas; o proto **não declara mínimos** |
| `companion_banners` | "Currently, only a single value … is supported" |
| `breadcrumb1`, `breadcrumb2`, `call_to_actions` | opcionais |

> ⚠️ Divergência de fontes sobre os mínimos deste tipo. O guia oficial resume
> "Video assets (minimum 1), Headlines (minimum 3), Long headlines (minimum 1),
> Descriptions (minimum 2), Logo images (minimum 1), Business name" `[média]` `[G1]`, mas o **proto
> não declara** esses mínimos. Trate 3/1/2 como piso operacional, não como validação garantida:
> `[baixa]` para os números exatos, `[alta]` apenas para `videos`, `logo_images` e `business_name`
> serem obrigatórios.

### `DemandGenProductAdInfo`

| Campo | Regra |
|---|---|
| `headline` | **Required** (um) |
| `description` | **Required** (uma) |
| `logo_image` | **Required**, mín. 128 × 128, 1:1 (±1%) |
| `business_name` | **Required** |
| `call_to_action` | opcional |
| `breadcrumb1`, `breadcrumb2` | opcionais |

---

## 4. Especificações de mídia (Help Center oficial)

Fonte: Help Center do Google Ads, guia de specs de criativo Demand Gen `[alta]` `[G7]`.
Autoridade menor que o proto para nome de campo, mas é a **única** fonte oficial para peso e
duração — o proto não os declara.

### Imagem

| Orientação | Proporção | Dimensão mínima | Recomendada | Formato | Peso máx. |
|---|---|---|---|---|---|
| Quadrada | 1:1 | 300 × 300 | 1200 × 1200 | .jpg, .png | **5 MB** |
| Horizontal | 1.91:1 | 600 × 314 | 1200 × 628 | .jpg, .png | 5 MB |
| Vertical | 4:5 | 480 × 600 | 960 × 1200 | .jpg, .png | 5 MB |
| Vertical 9:16 | 9:16 | 600 × 1067 | 1080 × 1920 (**recomendado para Shorts**) | .jpg, .png | 5 MB |
| **Logo** | 1:1 | **144 × 144** | 1200 × 1200 | .jpg, .png | **150 KB** |

> ⚠️ Contradição entre fontes oficiais no logo: o **proto** exige mínimo **128 × 128**; o **Help
> Center** publica mínimo **144 × 144**. Use **144 × 144** como piso de produção (satisfaz os dois)
> e registre a divergência. `[alta]` para ambos os números; `[baixa]` para qual é a validação real.

### Uploaded Display ads dentro de Demand Gen

Dimensões comuns publicadas: 300×250, 336×280, 728×90, 970×90, 160×600, 300×600, 320×50.
Formatos .jpg, .png, .gif (**não animado**), peso máximo **150 KB** `[alta]` `[G7]`.

### Vídeo

| Orientação | Proporção | Recomendado HD |
|---|---|---|
| Quadrado | 1:1 | 1080 × 1080 |
| Horizontal | 16:9 | 1920 × 1080 |
| Vertical | 4:5 | 1080 × 1350 |
| Vertical 9:16 | 9:16 | 1080 × 1920 (recomendado para Shorts) |

Formato: **MPG (MPEG-2 ou MPEG-4)**. Peso máximo **256 GB**. Duração mínima **5 segundos**;
**vídeos com menos de 10 segundos são inelegíveis para YouTube In-stream** `[alta]` `[G7]`.

---

## 5. Estratégias de lance

Suportadas, segundo o guia de criação `[alta]` `[G1]`:
**Maximize clicks** (`target_spend`), **Target CPA** (`target_cpa`), **Maximize conversions**
(`maximize_conversions`) e **Target ROAS** (`target_roas`).

Orçamento total de campanha (`CUSTOM_PERIOD`) em Demand Gen aceita:
Maximize conversions, Target CPA, Maximize conversion value, Target ROAS, Maximize clicks e
**Manual CPC** `[alta]` `[G5]`.

> Divergência a resolver: as release notes trazem, no resumo, "Demand Gen campaigns now support
> the **TargetCPC** bidding strategy" `[média]` `[G8]`, e `Campaign.target_cpc` existe no proto
> `[alta]` P — mas o guia de criação não lista Target CPC entre as suportadas. `[baixa]` para
> Target CPC em Demand Gen. Verificar com `validate_only` antes de expor no VOLC.

Portfólio (`BiddingStrategyService`) em Demand Gen: **`[NÃO CONFIRMADO]`** — a doc não afirma nem
nega. (Em PMax a proibição é explícita; aqui não há declaração.)

---

## 6. Channel controls — o mecanismo que só Demand Gen tem

`AdGroup.demand_gen_ad_group_settings.channel_controls`, um **`oneof`** entre `channel_strategy` e
`selected_channels` `[alta]` P `[G9]`:

| Configuração | Como setar | Efeito |
|---|---|---|
| Todos os canais (**default**) | `channel_strategy = ALL_CHANNELS` | Todas as superfícies suportadas |
| Só Google O&O | `channel_strategy = ALL_OWNED_AND_OPERATED_CHANNELS` | Discover, YouTube, Gmail, Maps. **Display (terceiros) fica desligado** |
| Canal a canal | `selected_channels.<flag> = true` | Flags: `youtube_in_stream`, `youtube_in_feed`, `youtube_shorts`, `discover`, `gmail`, `display`, `maps` |

`selected_channels` "should be set with at least one true value when present" `[alta]` P.
`channel_config` (`DemandGenChannelConfig`) é **Output only** e diz qual dos dois ramos do oneof
está populado — é o campo certo para o VOLC ler o estado `[alta]` P `[G9]`.

Não existe `network_settings` aqui; não existe `channel_controls` em Search/Display/PMax `[alta]` `[G4]`.

---

## 7. Targeting

- **`Campaign.demand_gen_campaign_settings.upgraded_targeting`**: `Immutable`, **default `true`**,
  **só pode ser setado na criação**. Com `true`, location e language passam a ser configuráveis
  **no ad group** em vez de na campanha `[alta]` P `[G1]`.
- Audiences no ad group via `AdGroupCriterion.audience` apontando para o resource name de um
  `Audience` `[alta]` `[G10]`.
- **Lookalike segments** são um recurso de audiência que "outros tipos de campanha não suportam" `[alta]` `[G10]`.
- Criando audiência com `AudienceService.MutateAudiences`, o `audience_id` sai do
  `resource_name` do resultado ou do recurso mutável quando `response_content_type = MUTABLE_RESOURCE` `[alta]` `[G10]`.

---

## 8. Product ads (feed do Merchant Center)

Passos oficiais `[alta]` `[G11]`:

1. Obter o ID da conta Merchant Center e verificar que está linkada ao Google Ads.
2. Criar `ShoppingSetting` na campanha com `merchant_id` apontando para ela.
3. Criar ad group + um dos três tipos de ad que suportam feed
   (`DemandGenProductAdInfo`, `DemandGenMultiAssetAdInfo`, `DemandGenVideoResponsiveAdInfo`).
4. Criar `AdGroupCriterion` do tipo **`listing_group`** para restringir quais produtos entram.

Recomendação oficial: **incluir ao menos um listing group por ad group de product ads, mesmo que
cubra todos os produtos**, para habilitar reporting completo `[alta]` `[G11]`.

Pode ser feito na criação da campanha ou depois, numa campanha Demand Gen existente `[alta]` `[G11]`.

---

## 9. Campos imutáveis específicos

| Recurso | Campo | Efeito |
|---|---|---|
| `Campaign` | `demand_gen_campaign_settings.upgraded_targeting` | Escolha de targeting no ad group vs campanha é **decidida uma vez, na criação** |
| `AdGroupAd` | `ad` | Trocar criativo = novo `AdGroupAd` |
| `Asset` | `demand_gen_carousel_card_asset` | Card de carrossel não se edita |
| `Asset` | `youtube_video_asset`, `text_asset` | idem |
| `AdGroupCriterion` | `audience`, `listing_group`, `negative` | recriar |

`[alta]` P.

---

## 10. Reporting

| Nível | Recursos | Observação |
|---|---|---|
| Campanha | `campaign` com `advertising_channel_type = DEMAND_GEN` | **Para contar cliques, filtre `segments.click_type = CROSS_NETWORK`** `[alta]` `[G12]` |
| Anúncio | `ad_group_ad` filtrando por `ad_group_ad.ad.type` para cada um dos três tipos suportados | `[alta]` `[G12]` |
| Asset | `asset` do tipo carousel card + métricas de `asset` | `[alta]` `[G12]` |

> ⚠️ **Anúncios do tipo "Demand Gen video ad (legacy)", visíveis na UI, NÃO são suportados pela
> API e não são retornados por `SearchStream`** `[alta]` `[G12]`. Qualquer inventário do VOLC que
> conte anúncios por conta vai divergir da UI em contas com esse legado.

> ⚠️ A doc fala em "três tipos" no reporting `[alta]` `[G12]`, mas o proto expõe **quatro**
> (`demand_gen_product_ad` incluso) `[alta]` P. `[baixa]` sobre a cobertura de reporting do
> quarto tipo.

Recomendação dedicada: `IMPROVE_DEMAND_GEN_AD_STRENGTH` `[alta]` (ver `comum.md` §9).

---

## 11. Diferenças de Demand Gen para os outros três

| Eixo | Demand Gen |
|---|---|
| vs **Search** | Sem keyword; ad group **sem `type_`**; criativo visual; `channel_controls` no lugar de `network_settings` |
| vs **Display** | 4 orientações de imagem incl. **9:16** e teto combinado de **20** (Display: 2 orientações, teto 15); **carrossel** (2–10 cards) não existe em Display; vídeo é peça central, não acessório |
| vs **PMax** | Mantém ad group + ad **explícitos** e permite escolher canal; PMax não permite nem uma coisa nem outra. Demand Gen tem `upgraded_targeting`; PMax tem `asset_group_signal` |
| Exclusivo | Orçamento diário **mínimo de 5 USD** validado pela API; `click_type = CROSS_NETWORK` obrigatório no reporting de cliques; **Lookalike segments** |

---

## Fontes desta página (consultadas em 26/08/2026)

| Ref | URL |
|---|---|
| G1 | https://developers.google.com/google-ads/api/docs/demand-gen/create-campaign |
| G2 | https://developers.google.com/google-ads/api/docs/campaigns/overview |
| G3 | https://developers.google.com/google-ads/api/docs/demand-gen/overview |
| G4 | https://developers.google.com/google-ads/api/docs/demand-gen/channel-controls |
| G5 | https://developers.google.com/google-ads/api/docs/campaigns/budgets/overview |
| G6 | https://developers.google.com/google-ads/api/docs/deprecations |
| G7 | https://support.google.com/google-ads/answer/13704860 (Help Center oficial — specs de criativo Demand Gen) |
| G8 | https://developers.google.com/google-ads/api/docs/release-notes |
| G9 | https://developers.google.com/google-ads/api/docs/demand-gen/channel-controls |
| G10 | https://developers.google.com/google-ads/api/docs/demand-gen/audience-targeting |
| G11 | https://developers.google.com/google-ads/api/docs/demand-gen/product-ads |
| G12 | https://developers.google.com/google-ads/api/docs/demand-gen/reporting |
| — | Requisitos mínimos de conta/campanha: https://support.google.com/google-ads/answer/13703192 (baixado, não citado acima) |
| P | Protos do SDK instalado `google-ads` 31.3.0, namespace `v25` |
