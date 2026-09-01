# Documentação oficial do Google — leitura de 01/09/2026

*Fonte única: `developers.google.com`. Nenhum blog, Stack Overflow ou terceiro.*
*API corrente na data da consulta: **v25**.*

Este arquivo existe porque três decisões desta sprint dependem do que a doc
oficial afirma — e uma delas já tinha sido tomada errada por leitura de memória
(`selective_optimization`). Citação literal com URL é mais barato que descobrir
na conta.

---

## 1. `selective_optimization` é de App, não de Search — CONFIRMADO

> "**Important:** You can only set the `selective_optimization` field of
> `Campaign` on an **App campaign**. For all other campaign types, use campaign
> goals to optimize a campaign for specific conversion actions."
> — <https://developers.google.com/google-ads/api/docs/conversions/goals/overview>

**Consequência aplicada:** o comentário de `meta_conversao_id` em
`backend/app/routers/trafego.py`, o texto de `PainelDoLancamento.tsx` e o tipo
em `src/types/trafego.ts` foram corrigidos. Eles mandavam quem lesse implementar
o campo errado — e uma docstring errada num contrato dá confiança para o caminho
errado.

## 2. Herança de conversion goals em Search

> "**Customer goals define the default goals for your entire account**, while
> campaign goals override the customer goals para campanhas com requisitos
> específicos."

> "[ao criar uma ConversionAction] Creates a `CampaignConversionGoal` **for each
> campaign** and the conversion action's category and origin if one doesn't
> already exist."

> "**Key Point:** Since Google Ads automatically creates `CustomerConversionGoal`,
> `CampaignConversionGoal`, and `ConversionGoalCampaignConfig` objects in your
> account, **you can only update those objects. The Google Ads API doesn't
> support creating or removing those objects.**"

> `campaign_conversion_goal.biddable`: "If left unspecified during campaign
> creation or update operations, this value will **inherit the account-level
> default biddability** for the corresponding conversion category and origin."

**Consequência:** a campanha nova HERDA. Trocar a meta só dela é um segundo ato
(`CampaignConversionGoal`, update-only), com validate_only, aprovação,
fingerprint, recibo e rollback próprios — nunca dentro do mutate de nascimento.

### Queries oficiais para ler o efetivo

```sql
-- metas da conta
SELECT customer_conversion_goal.category, customer_conversion_goal.origin,
       customer_conversion_goal.biddable
FROM customer_conversion_goal

-- metas da campanha
SELECT campaign_conversion_goal.campaign, campaign_conversion_goal.category,
       campaign_conversion_goal.origin, campaign_conversion_goal.biddable,
       campaign.id, campaign.name
FROM campaign_conversion_goal WHERE campaign.id = <ID>

-- quem manda de fato nesta campanha
SELECT conversion_goal_campaign_config.goal_config_level,
       conversion_goal_campaign_config.custom_conversion_goal
FROM conversion_goal_campaign_config
```

⚠️ `goal_config_level` ∈ `CUSTOMER | CAMPAIGN` diz qual nível está no comando.
Não existe um recurso único "effective goals": são duas leituras.

⚠️ `conversion_action.primary_for_goal` — "**By default, `primary_for_goal` will
be true if not set.**" e "If false, the conversion action is non-biddable for all
campaigns **regardless** of their customer or campaign conversion goal."
`include_in_conversions_metric` está **deprecado** em favor dele.

## 3. `GenerateRecommendations` — o que É e o que NÃO É gerável pré-lançamento

Existe desde a **v16**; `CAMPAIGN_BUDGET` entrou na **v18**; `is_new_customer`
na **v23**.

**Os 10 tipos geráveis pré-lançamento** (lista literal do
`GenerateRecommendationsRequest`):

```
CAMPAIGN_BUDGET · KEYWORD · MAXIMIZE_CLICKS_OPT_IN
MAXIMIZE_CONVERSIONS_OPT_IN · MAXIMIZE_CONVERSION_VALUE_OPT_IN
SET_TARGET_CPA · SET_TARGET_ROAS · SITELINK_ASSET
TARGET_CPA_OPT_IN · TARGET_ROAS_OPT_IN
```

**Só existem como recomendação ARMAZENADA** (campanha já criada, via GAQL sobre
`recommendation`) — ou seja, **não** são pré-lançamento:

```
MOVE_UNUSED_BUDGET · MARGINAL_ROI_CAMPAIGN_BUDGET
FORECASTING_CAMPAIGN_BUDGET · RESPONSIVE_SEARCH_AD
SEARCH_PARTNERS_OPT_IN · USE_BROAD_MATCH_KEYWORD
```

> "If there isn't sufficient data to generate a recommendation for the requested
> `recommendation_types`, or if the campaign is already in the recommended
> state, the result set won't contain a recommendation for that type."

> "**Important:** The RecommendationService doesn't provide errors when
> insufficient data is provided for a given recommendation type."

⚠️ Isso significa que **vazio não é erro e não é falha** — é exatamente o estado
`VAZIO_CONFIRMADO` que `inteligencia_google/modelo.py` já modela.

**Obrigatórios para SEARCH + CAMPAIGN_BUDGET:** `customer_id`,
`advertising_channel_type`, `recommendation_types[]`, `asset_group_info[]` (com
`final_url` **Required**), `bidding_info`, `country_codes[]`, `language_codes[]`,
`positive_locations_ids[]` ou `negative_locations_ids[]`, `ad_group_info[]` (onde
entram as keywords).

⚠️ **`budget_info` é OPCIONAL**, inclusive para `CAMPAIGN_BUDGET` — não é preciso
mandar orçamento para pedir recomendação de orçamento.

⚠️ **`is_new_customer` (v23+)** é o campo desenhado exatamente para este caso:
"only recommended for customers with 0 campaigns".

## 4. Bid simulations NÃO existem para campanha nova e pausada

> "You must have an **established** criterion, ad group, or campaign to provide
> the system with **baseline information from which to generate predictions**."
> "**Bid simulations are based on past performance.**"
> — <https://developers.google.com/google-ads/api/docs/bid-simulations/prerequisites>

> "**Key Point:** The time range is **always in the past**."

**Consequência:** ausência de simulação no canário recém-criado é **conclusão
válida documentada**, não defeito do coletor. O estado correto é `INELEGIVEL`,
nunca `FALHOU` nem `VAZIO_CONFIRMADO`.

Tipos em Search: `campaign_simulation` aceita CPC_BID, TARGET_CPA, TARGET_ROAS,
TARGET_IMPRESSION_SHARE, BUDGET; `ad_group_criterion_simulation` aceita **só**
CPC_BID em KEYWORD.

## 5. Experimentos Search exigem campanha base

> "**The control arm must specify exactly one campaign in its `campaigns`
> field.**" · code sample oficial: `# The "control" arm references an
> already-existing campaign.`

Ordem: `Experiment` (status `SETUP`) → `ExperimentArm` (todos numa **única**
request, sem partial failure) → modificar `in_design_campaigns` → 
`ScheduleExperiment` (assíncrono). "**At least one change must be made to an
in-design campaign before you can schedule the experiment.**"

**Reporting** — os campos exatos vivem em `metrics.*` do recurso `experiment`:
`*_p_value`, `*_point_estimate` ("The quantity being estimated is
(treatment / control - 1)"), `*_margin_of_error`. Para **conversions** os campos
são `conversions_absolute_change_{p_value,point_estimate,margin_of_error}` —
absolutos, não relativos.

## 6. Data Manager API — o que é, e o que NÃO é

`POST https://datamanager.googleapis.com/v1/events:ingest`, escopo
`https://www.googleapis.com/auth/datamanager`.

- **`validateOnly`** existe, **no corpo** (não query param): "If `true`, the
  request is validated but not executed."
- ⚠️ "You can only retrieve diagnostics for requests that succeed and **don't**
  have `validateOnly` set to `true`."
- Máximo **2000 eventos** por request.
- Campos reais: **`conversionValue`** (não `value`), **`currency`** (não
  `currencyCode` dentro do Event), `transactionId`, `eventTimestamp`
  (**Required**), `consent`, `adIdentifiers` (com `gclid`, `gbraid`, `wbraid`,
  `sessionAttributes`), `userData`.
- "a valid `Event` must have **at least one of `ad_identifiers` or `user_data`**."
- Diagnóstico: `GET /v1/requestStatus:retrieve?requestId=…`. "**Wait for 30
  minutes**" · backoff exponencial · "may take **up to 24 hours**".
- Estados: `PROCESSING | SUCCESS | FAILURE | PARTIAL_SUCCESS`. "**Check the
  `warning_info` even if the overall destination status is `SUCCESS`.**"
- Erro ≠ aviso: "An **error** indicates that the API **completely rejected** the
  record. A **warning** indicates that the API didn't reject the record, but it
  **had to ignore portions**."
- ⚠️ Período de teste: "During the initial **14-day trial period** for a
  conversion action … newly created conversions will appear in your reporting
  but **won't be used for bidding**."

**A Data Manager NÃO cria campanha e NÃO seleciona conversion goal.** A
superfície REST v1 inteira é `adEvents`, `audienceMembers`, `events`,
`requestStatus` e `accountTypes.accounts.*` — nenhum recurso de campanha,
bidding, budget ou goal. A ligação com o Google Ads é o `Destination`:

> "the operating account must be the Google Ads account that **owns the
> conversion action**" · `productDestinationId` = ID de uma ConversionAction com
> `type` `WEBPAGE` (multi-source), `UPLOAD_CLICKS` (offline / ECL) ou
> `STORE_SALES`.

**Consequência:** a `ConversionAction` precisa existir ANTES, criada pela Google
Ads API ou pela UI. A separação de responsabilidades do VOLC está correta.
