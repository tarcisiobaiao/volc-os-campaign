# Display — matriz de operação (v25)

Consulta: **26/08/2026**. O que é comum aos quatro canais está em [`comum.md`](./comum.md).

`advertising_channel_type = DISPLAY`, **sem** `advertising_channel_sub_type` para a campanha
Display padrão `[alta]` `[D1]`.

---

## 0. Achado que condiciona todo o resto

> **Não existe guia oficial de criação de campanha Display na Google Ads API.**
> Varri o índice completo de guias (308 URLs de `/google-ads/api/docs/**` extraídas da navegação
> oficial em 26/08/2026): há `campaigns/search-campaigns/getting-started`, `demand-gen/create-campaign`,
> `performance-max/create-campaign`, `shopping-ads/create-campaign`, `app-campaigns/create-campaign`,
> `hotel-ads/create-campaign`, `things-to-do-ads/create-campaign`, `smart-campaigns/create-campaign`
> — e **nenhum** `display-campaigns/*`. O que existe para Display é: `responsive-display-ads/*`,
> `display-upload-ads/*` e `dynamic-remarketing/*` `[alta]` `[D2]`.
>
> Além disso, a própria página de overview de RDA abre com um nudge:
> *"Already using Responsive display ads? See the benefits of upgrading to Performance Max"* `[alta]` `[D3]`.
>
> Consequência: o build de Display no VOLC precisa ser **derivado** de
> `campaigns/overview` + `campaigns/create-campaigns` (genéricos) + o proto. Não há caminho feliz
> documentado. Toda especificação de criativo abaixo vem **do proto**, porque o guia oficial de
> RDA declara literalmente que os números estão "in the reference page and the Help Center
> article" e não os reproduz `[alta]` `[D4]`.

---

## 1. Hierarquia e o que nasce no mesmo mutate

```
CampaignBudget
└── Campaign  (DISPLAY)              network_settings (GDN), bidding
    ├── CampaignCriterion            location, language, topic, placement (negativo), audience
    ├── CampaignAssetSet             (dynamic remarketing não-retail: AssetSet + Asset)
    └── AdGroup  (DISPLAY_STANDARD)
        ├── AdGroupCriterion         topic, user_list, custom_audience, custom_intent, demografia,
        │                            placement (negativo), display_custom_bid_dimension
        └── AdGroupAd
            ├── Ad.responsive_display_ad   (ResponsiveDisplayAdInfo)
            └── Ad.display_upload_ad       (DisplayUploadAdInfo + MediaBundleAsset)
```

Nenhuma exigência oficial de atomicidade para Display `[média]` (ausência de restrição em `[D4]`,
em contraste com a exigência explícita de PMax `[D5]`). `partial_failure` é utilizável, salvo se
o request usar IDs temporários — regra geral em `comum.md`.

---

## 2. Campos obrigatórios na criação

| Recurso | Campo | Regra | Conf. |
|---|---|---|---|
| `Campaign` | `name`, `advertising_channel_type = DISPLAY` | "required and should not be empty when creating new campaigns" | `[alta]` P |
| `Campaign` | `campaign_budget` | resource name | `[alta]` `[D6]` |
| `Campaign` | esquema de lance | `oneof campaign_bidding_strategy` ou `bidding_strategy` | `[alta]` `[D7]` |
| `Campaign` | `contains_eu_political_advertising` | presente em todos os exemplos v25 | `[média]` `[D6]` |
| `AdGroup` | `name`, `campaign` | idem Search | `[alta]` P |
| `AdGroup` | `type_ = DISPLAY_STANDARD` | `Immutable`; valor no enum `AdGroupType` | `[alta]` P |
| `AdGroupAd` | `ad_group`, `ad` | ambos `Immutable` | `[alta]` P |
| `ResponsiveDisplayAdInfo` | `marketing_images` | ≥1 | `[alta]` `[D4]` P |
| `ResponsiveDisplayAdInfo` | `square_marketing_images` | ≥1 | `[alta]` `[D4]` P |
| `ResponsiveDisplayAdInfo` | `headlines` | ≥1 | `[alta]` `[D4]` P |
| `ResponsiveDisplayAdInfo` | `long_headline` | **1, obrigatório** | `[alta]` `[D4]` P |
| `ResponsiveDisplayAdInfo` | `descriptions` | ≥1 | `[alta]` `[D4]` P |
| `ResponsiveDisplayAdInfo` | `business_name` | obrigatório | `[alta]` `[D4]` |

Vale aqui o mesmo alerta do Search: **`campaign.status` default é `ENABLED`** `[alta]` P.

---

## 3. Requisitos de imagem, vídeo e texto do RDA — do proto

`ResponsiveDisplayAdInfo`, docstrings do SDK 31.3.0 `[alta]` P:

### Imagens

| Campo | Mín. dimensão | Proporção | Máx. | Formatos |
|---|---|---|---|---|
| `marketing_images` | **600 × 314** | **1.91:1 (±1%)** | combinado com `square_marketing_images`: **15** | GIF, JPEG, PNG |
| `square_marketing_images` | **300 × 300** | **1:1 (±1%)** | combinado com `marketing_images`: **15** | GIF, JPEG, PNG |
| `logo_images` | **512 × 128** | **4:1 (±1%)** | combinado com `square_logo_images`: **5** | GIF, JPEG, PNG |
| `square_logo_images` | **128 × 128** | **1:1 (±1%)** | combinado com `logo_images`: **5** | GIF, JPEG, PNG |

Ao menos **uma** `marketing_image` e ao menos **uma** `square_marketing_image` são obrigatórias.
Logos são opcionais no proto (só têm teto declarado).

**`[NÃO CONFIRMADO]` — peso máximo de arquivo e dimensão recomendada para RDA.** O proto não
declara `max file size`; a página oficial de RDA remete ao Help Center; `/docs/assets/overview` e
`/docs/assets/working-with-assets` não trazem números. **Não reutilize os 5120 KB de PMax** — são
de outra tabela, de outro canal.

### Vídeo

| Campo | Regra |
|---|---|
| `youtube_videos` (`AdVideoAsset`) | **Opcional**, máximo **5** vídeos `[alta]` P |

**`[NÃO CONFIRMADO]`** — duração mínima, proporção e resolução exigidas para vídeo em RDA. O
proto só declara a contagem. PMax exige ≥10s e 16:9/1:1/9:16, mas isso é a tabela de PMax.

### Texto

| Campo | Mín | Máx | Limite de caractere |
|---|---|---|---|
| `headlines` | **1** | **5** | 30 |
| `long_headline` | **1** (obrigatório) | 1 | 90 |
| `descriptions` | **1** | **5** | 90 |
| `business_name` | 1 | 1 | largura de exibição máxima **25** |
| `call_to_action_text` | 0 | 1 | largura de exibição máxima **30** |

Todos `[alta]` P.

> ⚠️ **Bug de comentário no proto oficial**: a docstring de `descriptions` diz
> *"At least 1 and max 5 **headlines** can be specified"*. O contexto (campo `descriptions`,
> limite de 90 caracteres) deixa claro que se trata de descriptions. Registrado para que ninguém
> "corrija" o parser achando que descobriu um limite compartilhado.

### Cor e formato

| Campo | Regra |
|---|---|
| `main_color` / `accent_color` | Hex (`#ffffff`). **Se um for setado, o outro é obrigatório** |
| `allow_flexible_color` | Default `true`. **Precisa ser `true` se `main_color` e `accent_color` não forem setados** |
| `format_setting` | `ALL_FORMATS` (default), `NATIVE`, `NON_NATIVE` |
| `control_spec` | opt-in de vídeos gerados e asset enhancements |
| `price_prefix`, `promo_text` | textos para formatos dinâmicos |

Todos `[alta]` P + `[D4]`.

---

## 4. Display upload ads (HTML5 / mídia estática)

`Ad.display_upload_ad` (`DisplayUploadAdInfo`) + `MediaBundleAsset` (ZIP em `data`, mutate-only),
com `DisplayUploadProductType` (ex.: `HTML5_UPLOAD_AD`) `[alta]` `[D8]` P.

> **Gate de elegibilidade**: para criar anúncios HTML5 é preciso satisfazer **uma** destas
> condições `[alta]` `[D9]`:
> 1. o media bundle usa **AMPHTML** em vez de HTML tradicional; **ou**
> 2. a conta gastou **mais de US$ 9.000** e tem **mais de 90 dias**; **ou**
> 3. a conta está em allowlist (formulário).
>
> Isto é uma trava de conta, não de código. Precisa ser checado antes de o VOLC oferecer o formato.

**`[NÃO CONFIRMADO]`** — tamanho máximo do ZIP e dimensões suportadas do media bundle para Display.
O proto de `MediaBundleAsset` diz apenas que "o formato depende do campo de anúncio onde será
usado" e remete à doc do campo; a doc do campo não publica os números.

---

## 5. Dynamic remarketing

| Vertical | Tecnologia | Configuração de feed |
|---|---|---|
| Retail | Merchant Center + Google Ads | `ShoppingSetting` na campanha |
| Não-retail | Google Ads | `AssetSet` + `Asset` (via `CampaignAssetSet`) |

`[alta]` `[D10]`. Os tipos de `AssetSetType` disponíveis para isso incluem `DYNAMIC_EDUCATION`,
`DYNAMIC_CUSTOM`, `DYNAMIC_HOTELS_AND_RENTALS`, `DYNAMIC_REAL_ESTATE`, `DYNAMIC_LOCAL`,
`DYNAMIC_FLIGHTS`, `DYNAMIC_TRAVEL`, `DYNAMIC_JOBS`, todos ligados por `CampaignAssetSet` e
marcados como mutáveis `[alta]` `[C24]`.

---

## 6. Campos imutáveis específicos de Display

Além dos gerais (ver `search.md` §3, que vale igual):

| Recurso | Campo | Efeito |
|---|---|---|
| `AdGroup` | `type_` (`DISPLAY_STANDARD`) | Não converte ad group de Display em Search |
| `AdGroupAd` | `ad` | **RDA não é editável** — trocar imagem, headline ou cor exige novo `AdGroupAd` |
| `Ad` | `image_ad` (`ImageAdInfo`) | `Immutable` no proto |
| `Ad` | `legacy_responsive_display_ad` | legado, sem update |
| `Asset` | `media_bundle_asset` | `Immutable` — novo ZIP = novo asset |
| `AdGroupCriterion` | `negative` e o `oneof` do critério | ver `comum.md` §14 |

`[alta]` P.

---

## 7. Targeting — a contradição que precisa ser resolvida antes do build

A tabela oficial de critérios diz, para o tipo **Placement** `[alta]` `[C23]`:

| Tipo | Positivo? | Negativo? | Níveis | Notas |
|---|---|---|---|---|
| Placement | ❌ | ✅ | Campanha, Ad group, Cliente | URL até 250 caracteres, profundidade até 2 níveis; `adsenseformobileapps.com` não permitido |
| Placement list | ❌ | ✅ | Cliente | lista de exclusão reutilizável |

Verifiquei a linha diretamente no HTML da tabela (não só no texto extraído): positivo = ❌.

**Contradição a resolver:** a API expõe o recurso de relatório `managed_placement_view`
(placements gerenciados = targeting positivo) `[alta]` `[D11]`, e `Campaign.network_settings`
descreve `target_content_network` como "ads served on **specified placements** in the Google
Display Network. Placements are specified using the Placement criterion" `[alta]` P — o que
pressupõe placement positivo.

`[NÃO CONFIRMADO]` qual das duas fontes está desatualizada. **Ação recomendada antes de codificar
targeting positivo por placement no VOLC:** testar com `validate_only = true` num
`AdGroupCriterionOperation` com `placement` e `negative = false`, e registrar o erro (ou a
ausência dele) como evidência. Não assuma nenhuma das duas leituras.

### Demais critérios úteis em Display `[alta]` `[C23]`

| Tipo | Positivo | Negativo | Níveis |
|---|---|---|---|
| Topic | ✅ | ✅ | Campanha, Ad group |
| User list | ✅ | ✅ | Campanha, Ad group |
| Custom audience | ✅ | ❌ | Campanha, Ad group |
| Custom intent | ✅ | ❌ | **Só ad group** |
| Custom affinity | ✅ | ❌ | Campanha, Ad group |
| Combined audience | ✅ | ❌ | Campanha, Ad group |
| Age range / Gender / Income range | ✅ | ✅ | Campanha, Ad group |
| Parental status | ✅ | ✅ | Ad group; **campanha só negativo** |
| Content label | ❌ | ✅ | Campanha, Cliente |
| Mobile app category / Mobile application | ✅ | ✅ | Campanha, Ad group, Cliente |
| YouTube channel / YouTube video | ✅ | ✅ | Campanha, Ad group, Cliente |
| Webpage | ✅ | ✅ | Campanha, Ad group |

Controles de ad group só de Display `[alta]` P:
`AdGroup.display_custom_bid_dimension` (`TargetingDimension`) — "only applicable for campaigns"
que usam bid absoluto por dimensão; `AdGroup.optimized_targeting_enabled` (substituto de Audience
Expansion) e `AdGroup.exclude_demographic_expansion`.

---

## 8. Estratégias de lance

| Estratégia | Display | Conf. |
|---|---|---|
| `MANUAL_CPM` | **Só aqui.** "Works only with Display Network Only campaigns"; usar em Search dá `OperationAccessDeniedError.OPERATION_NOT_PERMITTED_FOR_CAMPAIGN_TYPE` | `[alta]` `[D7]` |
| `MAXIMIZE_CONVERSIONS` (standard) | Suportado — "As a standard strategy, it can be used with Search, **Display**, Video, and App campaigns" | `[alta]` `[D7]` |
| `MANUAL_CPC`, `TARGET_SPEND`, `MAXIMIZE_CONVERSION_VALUE`, `TARGET_CPM`, `PERCENT_CPC`, `FIXED_CPM`, `TARGET_CPV`, `MANUAL_CPV` | existem como esquemas Standard; **compatibilidade específica com `DISPLAY` não é declarada canal a canal** na doc oficial | `[NÃO CONFIRMADO]` |
| `COMMISSION`, `PAGE_ONE_PROMOTED`, `TARGET_OUTRANK_SHARE` | "No longer available" | `[alta]` `[D7]` |
| `MANUAL_CPA` | só Local Services | `[alta]` `[D7]` |

**Orçamento total de campanha (`CUSTOM_PERIOD`): Display NÃO está na lista.** A doc lista apenas
Demand Gen, Performance Max, Search e Shopping padrão / YouTube `[alta]` `[D12]`. Display fica com
orçamento diário (`amount_micros`, `period = DAILY`).

---

## 9. Reporting

Recursos GAQL de relatório associados a Display, do índice oficial "Reporting reference v25" `[alta]` `[D11]`:

| Recurso | Uso |
|---|---|
| `display_keyword_view` | keywords de display (contextual) |
| `topic_view` | performance por tópico |
| `managed_placement_view` | placements gerenciados |
| `detail_placement_view` | placement individual (URL/app) |
| `group_placement_view` | domínio/app agregado |
| `detail_content_suitability_placement_view` / `group_content_suitability_placement_view` | adequação de conteúdo |
| `ad_group_audience_view` / `campaign_audience_view` | audiências |
| `age_range_view`, `gender_view`, `parental_status_view`, `income_range_view` | demografia |
| `ad_group_ad_asset_view` | asset dentro do RDA |
| `webpage_view` | critérios de webpage |
| `click_view` | clique individual (janela curta) |

`display_keyword_view`, `topic_view` e a família `*_placement_view` são **exclusivas de Display**
(PMax usa `performance_max_placement_view`, e Demand Gen não expõe placement view) `[média]` — derivado
de `[D11]` + `[P6]` + `[DG5]`.

Segmentos gerais em `comum.md` §7.

---

## 10. Política e eligibility

Padrão comum (`ad_group_ad.policy_summary`, `ad_group_ad.primary_status`) — ver `comum.md` §12–13.
Nada específico de Display além disso na doc consultada.

`AdGroupAd.ad_strength` e `AdGroupAd.action_items` (Output only) valem para RDA e dão a lista de
recomendações de reforço do criativo `[alta]` P.

---

## 11. Diferenças de Display para os outros três

| Eixo | Display |
|---|---|
| vs **Search** | Mesmo esqueleto (ad group + ad), mas sem keyword positiva; **`MANUAL_CPM` é exclusivo daqui**; sem `search_term_view`; sem AI Max |
| vs **Demand Gen** | RDA aceita **15** imagens combinadas e 5 headlines; Demand Gen aceita **20** imagens combinadas (4 orientações, incl. 9:16) e tem `channel_controls`. Demand Gen tem 4 tipos de ad, Display tem RDA + upload |
| vs **PMax** | Display tem ad group + ad explícito e controle de rede; PMax tem asset group, sem controle de rede, e **exige** brand assets no nível campanha |
| Documentação | **É o único dos quatro sem guia de criação de campanha.** Especificação de criativo só existe no proto |
| Formato próprio | `display_upload_ad` (HTML5/AMPHTML) com gate de conta — não existe equivalente nos outros três |

---

## Fontes desta página (consultadas em 26/08/2026)

| Ref | URL |
|---|---|
| D1 | https://developers.google.com/google-ads/api/docs/campaigns/overview |
| D2 | Índice de navegação de `https://developers.google.com/google-ads/api/docs/start` (308 URLs de guia extraídas) |
| D3 | https://developers.google.com/google-ads/api/docs/responsive-display-ads/overview |
| D4 | https://developers.google.com/google-ads/api/docs/responsive-display-ads/create-responsive-display-ads |
| D5 | https://developers.google.com/google-ads/api/performance-max/asset-groups |
| D6 | https://developers.google.com/google-ads/api/docs/campaigns/create-campaigns |
| D7 | https://developers.google.com/google-ads/api/docs/campaigns/bidding/strategy-types |
| D8 | https://developers.google.com/google-ads/api/docs/display-upload-ads/create-display-upload-ad |
| D9 | https://developers.google.com/google-ads/api/docs/display-upload-ads/html5-upload-ads |
| D10 | https://developers.google.com/google-ads/api/docs/dynamic-remarketing/overview |
| D11 | https://developers.google.com/google-ads/api/docs/sunset-dates (índice "Reporting reference v25") |
| D12 | https://developers.google.com/google-ads/api/docs/campaigns/budgets/overview |
| C23, C24 | ver `comum.md` (S23, S24) |
| P6 | https://developers.google.com/google-ads/api/performance-max/reporting |
| DG5 | https://developers.google.com/google-ads/api/docs/demand-gen/reporting |
| P | Protos do SDK instalado `google-ads` 31.3.0, namespace `v25` |
