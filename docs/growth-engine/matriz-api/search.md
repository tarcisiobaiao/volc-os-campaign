# Search — matriz de operação (v25)

Consulta: **26/08/2026**. Convenções de confiança e tudo que é comum aos quatro canais estão em
[`comum.md`](./comum.md) — este arquivo não repete quotas, `validate_only`, `partial_failure`,
`change_event`, `primary_status` nem o modelo de assets.

`advertising_channel_type = SEARCH`, **sem** `advertising_channel_sub_type` `[alta]` `[T1]`.

---

## 1. Hierarquia e o que nasce no mesmo mutate

```
CampaignBudget                       (compartilhável entre campanhas)
└── Campaign  (SEARCH)               network_settings, bidding, ai_max_setting
    ├── CampaignCriterion            location, language, negativos de campanha, brand list
    ├── CampaignAsset                sitelink, callout, structured snippet, call, image…
    └── AdGroup  (SEARCH_STANDARD)
        ├── AdGroupCriterion         keywords (positivas e negativas), audiences, demografia
        ├── AdGroupAsset             assets no nível ad group
        └── AdGroupAd
            └── Ad.responsive_search_ad  (ResponsiveSearchAdInfo)
```

Recursos **mandatórios** para uma campanha Search válida e ativa, segundo o guia oficial:
`CampaignBudget`, `Campaign`, `AdGroup`, `AdGroupCriterion` (keywords) e `AdGroupAd` com RSA `[alta]` `[T2]`.

O guia recomenda um **bulk mutate** (`GoogleAdsService.Mutate`) com IDs temporários para criar
tudo num request, mas **não obriga**: "Although you don't have to create every resource in a
single bulk request" `[alta]` `[T2]`. Isso separa Search de Demand Gen e PMax, onde a
atomicidade é exigida ou fortemente recomendada.

---

## 2. Campos obrigatórios na criação (nome exato do proto)

| Recurso | Campo | Regra | Conf. |
|---|---|---|---|
| `CampaignBudget` | `name` | Obrigatório **se `explicitly_shared = true`** (default). Se não compartilhado, herda o nome da campanha. 1–255 bytes UTF-8 | `[alta]` P |
| `CampaignBudget` | `amount_micros` **ou** `total_amount_micros` | Mutuamente exclusivos. `amount_micros` com `period = DAILY` (default); `total_amount_micros` com `period = CUSTOM_PERIOD` | `[alta]` P |
| `Campaign` | `name` | "required and should not be empty when creating new campaigns"; sem `\0`, `\n`, `\r` | `[alta]` P |
| `Campaign` | `advertising_channel_type` | "required and should not be empty when creating new campaigns" → `SEARCH` | `[alta]` P |
| `Campaign` | `campaign_budget` | resource name do orçamento | `[alta]` `[T2]` |
| `Campaign` | esquema de lance | um do `oneof campaign_bidding_strategy` (ex.: `manual_cpc`, `target_spend`) **ou** `bidding_strategy` (portfólio) | `[alta]` `[T3]` |
| `Campaign` | `contains_eu_political_advertising` | Autodeclaração; presente em **todos** os exemplos oficiais v25 de criação | `[média]` `[T4]` |
| `AdGroup` | `name` | "required and should not be empty"; < 255 caracteres full-width UTF-8 | `[alta]` P |
| `AdGroup` | `campaign` | resource name | `[alta]` P |
| `AdGroupAd` | `ad_group`, `ad` | ambos `Immutable` | `[alta]` P |
| `Ad` | `final_urls` | ao menos uma URL | `[alta]` `[T5]` |
| `ResponsiveSearchAdInfo` | `headlines` | **mínimo 3** | `[alta]` `[T5]` |
| `ResponsiveSearchAdInfo` | `descriptions` | **mínimo 2** | `[alta]` `[T5]` |

⚠️ **`campaign.status` tem default `ENABLED` na criação** `[alta]` P. Todos os exemplos oficiais
setam `PAUSED` explicitamente. Se o VOLC omitir `status`, a campanha nasce **ligada e gastando**.

---

## 3. Campos imutáveis — o que o VOLC nunca poderá "editar"

| Recurso | Campo imutável | Efeito prático |
|---|---|---|
| `Campaign` | `advertising_channel_type`, `advertising_channel_sub_type` | Trocar de canal = **criar outra campanha** |
| `Campaign` | `resource_name`, `brand_guidelines_enabled` | — |
| `CampaignBudget` | `period`, `type_`, `resource_name` | Trocar diário↔total exige **novo orçamento** |
| `AdGroup` | `type_`, `campaign`, `audience_setting` | Mover ad group entre campanhas é impossível |
| `AdGroupAd` | `ad_group`, **`ad`** | **Editar o criativo de um RSA existente é impossível pela API**: `AdGroupAd.ad` é `Immutable` → cria-se novo `AdGroupAd` e remove-se o antigo |
| `AdGroupCriterion` / `CampaignCriterion` | o `oneof` do critério inteiro e `negative` | Mudar texto de keyword ou virar negativa = recriar |
| `Asset` | `text_asset`, `youtube_video_asset`, `media_bundle_asset` | Conteúdo de asset não se edita |
| `Customer` | `currency_code`, `time_zone` | Fixos por conta |

Todos `[alta]`, do descriptor/docstring do proto instalado.

> Consequência de arquitetura para o VOLC: no domínio Search, "editar anúncio" **não existe**.
> Existe *substituir*. O caso de uso tem de ser modelado como replace-and-retire, com o histórico
> apontando para dois `AdGroupAd` distintos.

O que **é** editável em quente: `campaign.status`, `campaign.name`, `campaign_budget.amount_micros`,
o esquema de lance da campanha, `ad_group.status`, `ad_group.cpc_bid_micros`,
`ad_group_criterion.status` / `cpc_bid_micros` / `bid_modifier` / `final_urls`,
`ad_group_ad.status`, `ad.final_urls` e templates de tracking `[alta]` P.

---

## 4. Leitura (GAQL) e escrita (services)

### Recursos GAQL específicos ou centrais do Search

| Recurso | Para quê |
|---|---|
| `campaign`, `ad_group`, `ad_group_ad`, `ad_group_criterion` | estrutura + métricas |
| `keyword_view` | performance por keyword |
| `search_term_view` | termos de busca reais |
| `campaign_search_term_view` | termos no nível campanha |
| `campaign_search_term_insight`, `customer_search_term_insight` | agrupamento de termos por tema |
| `ai_max_search_term_ad_combination_view` | **exclusivo AI Max**: termo × headline × landing page |
| `dynamic_search_ads_search_term_view` | exclusivo DSA |
| `paid_organic_search_term_view` | pareamento pago/orgânico (exige Search Console linkado) |
| `expanded_landing_page_view`, `landing_page_view` | performance por landing page |
| `ad_group_ad_asset_view` | performance de headline/description dentro do RSA |
| `ad_group_simulation`, `campaign_simulation`, `ad_group_criterion_simulation` | simulações de lance |
| `ad_schedule_view`, `age_range_view`, `gender_view`, `parental_status_view`, `income_range_view`, `geographic_view`, `user_location_view`, `distance_view` | segmentações |

Lista derivada do índice de "Reporting reference v25" e dos guias de Search `[alta]` `[T6]` `[T2]` `[T7]`.

### Services de escrita

`CampaignBudgetService`, `CampaignService`, `CampaignCriterionService`, `AdGroupService`,
`AdGroupCriterionService`, `AdGroupAdService`, `AdGroupAdLabelService`, `CampaignAssetService`,
`AdGroupAssetService`, `SharedSetService` + `SharedCriterionService` + `CampaignSharedSetService`
(listas de negativas), `CustomizerAttributeService` + `CustomerCustomizerService` /
`AdGroupCustomizerService` (ad customizers), `BiddingStrategyService` (portfólio) `[alta]` `[T8]`.

`validate_only` e `partial_failure`: comportamento padrão descrito em `comum.md`. Search **não**
tem restrição especial documentada contra `partial_failure` — diferente de PMax `[média]`
(ausência de restrição em `[T2]`, contraste com `[P5]`).

---

## 5. Criativo: requisitos de texto, imagem e vídeo

### RSA (`ResponsiveSearchAdInfo`)

| Elemento | Mín | Máx | Limite | Conf. |
|---|---|---|---|---|
| `headlines` (`AdTextAsset`) | **3** | `[NÃO CONFIRMADO]` — nem o proto nem o guia declaram o teto na doc consultada | **30 caracteres** por headline | `[alta]` `[T5]` `[T9]` |
| `descriptions` (`AdTextAsset`) | **2** | `[NÃO CONFIRMADO]` na doc consultada | **90 caracteres** | `[alta]` `[T5]` `[T9]` |
| `path1` / `path2` | 0 | — | **15 caracteres** cada; `path2` só se `path1` setado | `[alta]` `[T9]` P |
| `final_urls` | 1 | — | **2.084 bytes** | `[alta]` `[T5]` `[T9]` |

No serve, o RSA aparece com **três headlines e duas descriptions** `[alta]` `[T10]`.
Pinning: `AdTextAsset.pinned_field` fixa um asset numa posição; múltiplos assets pinados na mesma
posição rotacionam entre si `[alta]` `[T10]`.

### Imagem e vídeo em Search

O anúncio de Search **não carrega** imagem ou vídeo no próprio `Ad`. Imagem entra como asset
linkado (`AssetFieldType.AD_IMAGE` via `CampaignAsset`/`AdGroupAsset`, marcado como **não mutável**
na tabela oficial de assets) `[alta]` `[C24]`.

**`[NÃO CONFIRMADO]`** — dimensões, proporção, peso e formato de `AD_IMAGE`. Procurei em
`/docs/assets/overview`, `/docs/assets/working-with-assets`, `/docs/campaigns/search-campaigns/getting-started`,
`/docs/responsive-search-ads/*` e no proto `ImageAsset`/`AdImageAsset`: nenhuma fonte oficial de
API publica esses números. A única fonte é o Help Center de image extensions, que **não consultei**.
Não assuma que os números de PMax valem aqui.

---

## 6. Estratégias de lance

**Compatíveis, confirmadas em contexto Standard** `[alta]` `[T3]`:
`MANUAL_CPC`, `TARGET_SPEND` (Maximize clicks), `MAXIMIZE_CONVERSIONS` (com `target_cpa_micros`
opcional), `MAXIMIZE_CONVERSION_VALUE` (com `target_roas` opcional), `TARGET_IMPRESSION_SHARE`.

**Portfólio** (`BiddingStrategyService`): `MAXIMIZE_CONVERSIONS`, `TARGET_CPA`, `TARGET_ROAS`,
`TARGET_SPEND`, `TARGET_IMPRESSION_SHARE` `[alta]` `[T3]`.

**Proibidas / erro garantido:**

| Estratégia | O que acontece | Conf. |
|---|---|---|
| `MANUAL_CPM` | "Works only with Display Network Only campaigns. Using this bidding scheme with Search campaigns results in `OperationAccessDeniedError.OPERATION_NOT_PERMITTED_FOR_CAMPAIGN_TYPE`" | `[alta]` `[T3]` |
| `COMMISSION`, `PAGE_ONE_PROMOTED`, `TARGET_OUTRANK_SHARE` | "No longer available" | `[alta]` `[T3]` |
| `MANUAL_CPA` | só Local Services | `[alta]` `[T3]` |
| Esquema portfolio-only em contexto standard | `BiddingError.INVALID_ANONYMOUS_BIDDING_STRATEGY_TYPE` | `[alta]` `[T3]` |
| Esquema standard-only em portfólio | `BiddingStrategyError.BIDDING_STRATEGY_NOT_SUPPORTED` | `[alta]` `[T3]` |

**Orçamento total de campanha** (`total_amount_micros` + `period = CUSTOM_PERIOD`) em Search só
funciona com: Target ROAS, Maximize conversion value, Target CPA, Maximize conversions,
Maximize clicks, Target impression share, Manual CPC — e exige start/end date `[alta]` `[T11]`.

---

## 7. Controle de rede — o que só Search tem

`Campaign.network_settings` (`NetworkSettings`) `[alta]` P:

| Campo | Efeito |
|---|---|
| `target_google_search` | google.com |
| `target_search_network` | Search Partners — **exige `target_google_search = true`** |
| `target_content_network` | Display Expansion on Search (GDN com verba não gasta da Search) |
| `target_partner_search_network` | rede de parceiros restrita a contas selecionadas |
| `target_youtube`, `target_google_tv_network` | YouTube / Google TV |

`target_content_network = true` é literalmente como se liga **Display Expansion on Search** `[alta]` `[T12]`.

PMax não tem `network_settings` (sem opt-out de rede); Demand Gen usa `channel_controls` no ad
group, não `network_settings` `[alta]` `[T1]`.

---

## 8. AI Max — camada de v25 que muda o contrato do canal

Não é um novo `advertising_channel_type`; é uma camada sobre Search `[alta]` `[T7]`.

| Controle | Campo |
|---|---|
| Ligar | `Campaign.ai_max_setting.enable_ai_max` |
| Diagnóstico | `Campaign.AiMaxSetting.bundling_required` (**Output only**) |
| Desligar search term matching por ad group | `AdGroup.ai_max_ad_group_setting.disable_search_term_matching` |
| Text customization | `Campaign.asset_automation_settings` com `TEXT_ASSET_AUTOMATION` = `OPTED_IN` |
| Final URL expansion | `asset_automation_settings` com o tipo correspondente = `OPTED_IN` |
| Guard-rails de texto | `Campaign.text_guidelines.term_exclusions` (máx **25**, **30 caracteres** cada) e `messaging_restrictions` (máx **40**) |

Todos `[alta]` `[T7]` + proto.

⚠️ Com AI Max ligado, `Campaign.keyword_match_type` fica **deprecado e inaplicável**; tentar
alterá-lo retorna `CampaignError.CANNOT_SET_CAMPAIGN_KEYWORD_MATCH_TYPE`. Todas as keywords
passam a ser tratadas como **broad** por default, a menos que o ad group desabilite search term
matching `[alta]` `[T7]`.

A v25.1 acrescentou `Campaign.aca_migration_date_time` e `Campaign.broad_match_migration_date_time`
para acompanhar a auto-migração para AI Max — **campos ausentes no SDK 31.3.0** `[alta]` `[C2]`.

---

## 9. Limites com efeito no build de Search

| Limite | Valor | Conf. |
|---|---|---|
| Keyword | 80 caracteres | `[alta]` `[C17]` |
| Headline / description / path | 30 / 90 / 15 caracteres | `[alta]` `[C17]` |
| Final URL de anúncio / de critério | 2.084 / 2.047 bytes | `[alta]` `[C17]` |
| Estratégias de lance em ad groups por campanha | 1.000 | `[alta]` `[C17]` |
| Blocos de IP excluídos por campanha | 500 | `[alta]` `[C17]` |
| Keywords por conta / por campanha | `[NÃO CONFIRMADO]` — não está na página de limites de sistema | — |

---

## 10. Diferenças de Search para os outros três canais

| Eixo | Search | Display | Demand Gen | PMax |
|---|---|---|---|---|
| Estrutura | Ad group + Ad | Ad group + Ad | Ad group + Ad | **Asset group**, sem ad group |
| Criativo | Texto puro, `ResponsiveSearchAdInfo` | Imagem+texto, `ResponsiveDisplayAdInfo` | Imagem/vídeo/carrossel, 4 tipos de ad | Assets soltos, ad montado pelo Google |
| Targeting principal | **Keyword** (o único canal onde keyword é positiva no ad group) | Placement/topic/audience | Audience + channel controls | Só **sinais**, não targeting |
| Controle de rede | `network_settings` completo | `network_settings` (GDN) | `channel_controls` no ad group | Nenhum |
| Guia oficial de criação | **Sim**, dedicado (`search-campaigns/getting-started`) | **Não existe** guia de campanha | Sim (`demand-gen/create-campaign`) | Sim, seção inteira |
| Atomicidade exigida | Não | Não documentada | Recomendada | **Exigida** para asset group |
| `search_term_view` | Sim | Não | Não | Só `campaign_search_term_view` |
| Camada de IA nativa | **AI Max** | — | — | Asset automation |

---

## Fontes desta página (consultadas em 26/08/2026)

| Ref | URL |
|---|---|
| T1 | https://developers.google.com/google-ads/api/docs/campaigns/overview |
| T2 | https://developers.google.com/google-ads/api/docs/campaigns/search-campaigns/getting-started |
| T3 | https://developers.google.com/google-ads/api/docs/campaigns/bidding/strategy-types |
| T4 | https://developers.google.com/google-ads/api/docs/campaigns/create-campaigns |
| T5 | https://developers.google.com/google-ads/api/docs/responsive-search-ads/create-responsive-search-ads |
| T6 | https://developers.google.com/google-ads/api/docs/sunset-dates (índice "Reporting reference v25" da navegação) |
| T7 | https://developers.google.com/google-ads/api/docs/campaigns/ai-max-for-search-campaigns/getting-started |
| T8 | https://developers.google.com/google-ads/api/docs/campaigns/create-ad-groups |
| T9 | https://developers.google.com/google-ads/api/docs/best-practices/system-limits |
| T10 | https://developers.google.com/google-ads/api/docs/responsive-search-ads/overview |
| T11 | https://developers.google.com/google-ads/api/docs/campaigns/budgets/overview |
| T12 | https://developers.google.com/google-ads/api/docs/campaigns/create-campaigns |
| C17, C24, C2 | ver `comum.md` (S17, S24, S2) |
| P5 | https://developers.google.com/google-ads/api/performance-max/asset-groups |
| P | Protos do SDK instalado `google-ads` 31.3.0, namespace `v25` |
