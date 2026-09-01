# Comum — o que vale para os quatro canais

> ⚠️ **PREMISSA REFUTADA em 01/09/2026.** `campaign.selective_optimization` é campo de campanha de **APP**, não de Search — confirmado literalmente na doc oficial (callout "Important" em `conversions/goals/overview`), ver `docs/architecture/evidence/GOOGLE-ADS-DOCS-2026-09-01.md`. Para Search, a campanha **herda** os `CustomerConversionGoal` da conta, e sobrescrever exige `CampaignConversionGoal` — que a API só **atualiza**, nunca cria nem remove. O texto abaixo é histórico e não deve ser implementado como está.


Consulta: **26/08/2026**. API alvo: **v25**. SDK inspecionado: `google-ads` **31.3.0**
(`backend/.venv/lib/python3.14/site-packages/google/ads/googleads/v25/`).

Convenção de confiança usada em todos os arquivos desta pasta:

| Marca | Significa |
|---|---|
| `[alta]` | Descriptor/docstring do proto instalado, ou tabela oficial reproduzida literalmente |
| `[média]` | Prosa da documentação oficial (sem tabela normativa) |
| `[baixa]` | Inferência a partir de duas fontes oficiais que não se declaram |
| `[NÃO CONFIRMADO]` | Não achei fonte oficial; está escrito o que foi tentado |

Fontes citadas como `[S#]` estão no rodapé e em `fontes.json`.

---

## 1. Versão, ciclo de vida e o descompasso do SDK local

| Versão | Lançamento | Sunset | Confiança |
|---|---|---|---|
| v22 | 15/10/2025 | outubro/2026 (tentativo) | `[alta]` `[S1]` |
| v23 / v23.1 / v23.2 | 28/01/2026 · 25/02/2026 · 25/03/2026 | fevereiro/2027 | `[alta]` `[S1]` |
| v24 / v24.1 / v24.2 | 22/04/2026 · 13/05/2026 · 24/06/2026 | maio/2027 · maio/2027 · junho/2027 | `[alta]` `[S1]` |
| **v25** | **22/07/2026** | **agosto/2027** | `[alta]` `[S1]` |
| v25.1 | **19/08/2026** (já lançada) | agosto/2027 | `[alta]` `[S1]` `[S2]` |
| v25.2 | setembro/2026 (previsto) | agosto/2027 | `[alta]` `[S1]` |
| v26 | outubro/2026 (previsto) | novembro/2027 | `[alta]` `[S1]` |
| v26.1 | novembro/2026 (previsto, **opcional**) | novembro/2027 | `[alta]` `[S1]` |

Regras do ciclo: no máximo **duas atualizações por ano**; salto não sequencial permitido
(N → N+2); major dura ~12 meses, minor ~10 meses `[alta]` `[S1]`.
O corpo da página diz "no máximo **cinco** versões major simultâneas"; o resumo automático
da mesma página diz "quatro" — divergência interna da fonte, use cinco (corpo normativo) `[média]` `[S1]`.

Cliente Python mínimo para v25: **31.2.0** `[alta]` `[S1]`. Instalado: **31.3.0** ✔.

> ### ⚠️ Achado operacional: o SDK local está uma minor atrás da API viva
> A v25.1 saiu em 19/08/2026 e é **aditiva** dentro do namespace `v25`. Verifiquei por
> introspecção direta que o pacote instalado **não contém** as adições da v25.1 `[alta]`:
>
> | Item da v25.1 `[S2]` | Presente no SDK 31.3.0? |
> |---|---|
> | `Campaign.aca_migration_date_time` | **AUSENTE** |
> | `Campaign.broad_match_migration_date_time` | **AUSENTE** |
> | `AssetFieldType.TEXT_DISCLAIMER` | **AUSENTE** |
> | resource `LiftMeasurementConfig` | **AUSENTE** |
>
> Consequência para o VOLC: o proto local é verdade estrutural para **v25.0**, não para
> a v25 viva. Campos novos existem no servidor e o SDK não sabe serializá-los. Qual versão
> mínima do cliente Python cobre a v25.1 é apontada pelo Changelog do Python, que **não
> consultei** — `[NÃO CONFIRMADO]`.

### Depreciações não versionadas com efeito no motor `[alta]` `[S3]`

| Efetivo | Área | O que muda |
|---|---|---|
| 01/07/2025 | Brand guidelines | Em PMax com brand guidelines ligado (padrão), `BUSINESS_NAME` e `LOGO` passam para `CampaignAsset` (nível campanha), não `AssetGroupAsset` |
| 01/01/2026 | Call-only ads | `CallAdInfo` não pode mais ser criado; para de servir em fev/2027 |
| 01/04/2026 | **Demand Gen** | Orçamento diário mínimo de **5 USD** (ou equivalente local) obrigatório; violação retorna erro com `details.budget_per_day_minimum_error_details` |
| 01/04/2026 | Customer Match | Tokens sem uso entre 01/10/2025–31/03/2026 bloqueados (`CUSTOMER_NOT_ALLOWLISTED_FOR_THIS_FEATURE`); migrar para Data Manager API |
| 01/06/2026 | Retenção de dados | Dado granular (diário/horário/semanal) cai para **37 meses**; agregado (mensal+) fica 11 anos |
| 15/06/2026 | Conversões offline | Tokens sem upload entre 17/12/2025–15/06/2026 bloqueados |
| 23/09/2026 | Smart Campaigns | Não se cria mais; existentes seguem servindo |

---

## 2. Modelo de escrita: três caminhos, um só comportamento transacional

| Caminho | Cruza tipos de recurso? | IDs temporários | Uso |
|---|---|---|---|
| `<Recurso>Service.Mutate<Recursos>` | Não. Cada operação é independente, **sem referência cruzada** | Não | Alterar N objetos do mesmo tipo `[alta]` `[S4]` |
| `GoogleAdsService.Mutate` (bulk) | Sim, via `MutateOperation` repetido | **Sim** | Criar estrutura inteira numa chamada `[alta]` `[S5]` |
| `BatchJobService` | Sim | Sim | Lote assíncrono grande `[alta]` `[S6]` |

Regras que valem nos três `[alta]` `[S7]`:

- `create` / `update` / `remove` são um `oneof` — uma operação faz **uma** coisa.
- `update` **exige** `update_mask`; sem ele o campo não é tocado.
- **Atomicidade por default**: "as operações só são aplicadas se **todas** tiverem sucesso".
- `response_content_type`: `RESOURCE_NAME_ONLY` (default) ou `MUTABLE_RESOURCE` — o segundo
  devolve o recurso mutável e evita um `Search` de volta, ao custo de payload `[média]` `[S8]`.
- Mutação cross-account é bloqueada, salvo se a conta for manager de quem criou `[média]` `[S9]`.

### IDs temporários (negativos) `[alta]` `[S6]` `[S8]`

- `resource_name = "customers/{cid}/campaigns/-1"` cria a campanha e a torna referenciável.
- Só pode ser **usado depois de definido** — a ordem das operações importa.
- Cada ID temporário é **único no request inteiro**, mesmo entre tipos diferentes; reuso = erro.
- **Não sobrevive** entre requests ou jobs.

---

## 3. `validate_only`

Definição literal do proto instalado `[alta]`:

| Request | Texto do proto |
|---|---|
| `MutateCampaignsRequest.validate_only` | "If true, the request is validated but not executed. Only errors are returned, not results." |
| `MutateGoogleAdsRequest.validate_only` | "If true, the request is validated but not executed. **Mutates only return errors, not results. Actions return results and errors.**" |

Onde existe: `GoogleAdsService.Search`, `GoogleAdsService.SearchStream` e **a maioria** dos
mutates — a doc manda conferir a referência por método, não presumir `[alta]` `[S10]`.
Presença do campo no request message é o teste definitivo `[alta]` (mesma lógica de `partial_failure`, `[S11]`).

**O que ele cobre**, conforme a doc: verificar que "o request está estruturado corretamente
**e não viola políticas**" `[alta]` `[S10]`.

**O que ele NÃO cobre:**

- Não devolve `results` nem resource names — logo **não dá para obter IDs reais** em dry-run `[alta]` (proto).
- Existem operações que **rejeitam** `validate_only`: a v25.1 adicionou
  `SmartCampaignError.VALIDATE_ONLY_GENERATE_PMAX_NOT_SUPPORTED` `[alta]` `[S2]`.
- **`[NÃO CONFIRMADO]`** — uma lista oficial e exaustiva do que `validate_only` deixa passar.
  Procurei em `/docs/mutating/*`, `/docs/best-practices/testing`, `/docs/best-practices/error-types`,
  `/docs/best-practices/understand-api-errors` e no proto: nenhuma fonte enumera exclusões.
  Não preencha essa lacuna por memória; trate `validate_only` como gate de forma + política,
  e assuma que condições dependentes de estado do commit podem escapar.

---

## 4. `partial_failure`

| Aspecto | Fato | Fonte |
|---|---|---|
| Default | `false` — tudo ou nada | `[alta]` proto |
| Como saber se existe | O request message tem o campo `partial_failure`. `MutateAdGroupsRequest` tem; `MutateCampaignConversionGoalsRequest` não | `[alta]` `[S11]` |
| Formato do erro | `response.partial_failure_error` do tipo `google.rpc.Status`; `details` tem **um** elemento, um `Any` empacotando `GoogleAdsFailure`; `GoogleAdsFailure.errors` é lista de `GoogleAdsError` | `[alta]` `[S11]` |
| **Como achar o item que falhou** | `GoogleAdsError.location.field_path_elements[0].index` — índice **0-based** da operação no lote | `[alta]` `[S11]` |
| Operações OK | devolvem resource name em `results` | `[alta]` `[S11]` |
| Operações que falharam | devolvem **mensagem vazia** na mesma posição de `results` | `[alta]` `[S11]` |

**Quando NÃO usar** — citação da doc: "If a temporary ID is needed for cross-operation resource
referencing within the same request … you shouldn't use partial failure, because the success of
the second operation is dependent on the success of the first" `[alta]` `[S11]`.
Isso elimina `partial_failure` de todo fluxo de criação de estrutura nova (orçamento → campanha
→ ad group → anúncio) nos quatro canais.

Armadilha assíncrona: em `OfflineUserDataJob`, se **todas** as operações falharem o job ainda
termina com status `SUCCESS`, vazio. Sempre inspecione `partial_failure_error` `[alta]` `[S11]`.

---

## 5. Idempotência

**A API não oferece chave de idempotência.** Varri as 70 páginas oficiais baixadas
(guias completos de mutating, batch, best-practices, erros, todos os quatro canais):
zero ocorrências de "idempotent"/"idempotency" `[média]` — alta para o corpus varrido,
média como afirmação sobre o site inteiro.

O que a API dá, e o que sobra para a aplicação:

| Precisa | A API oferece | O VOLC precisa construir |
|---|---|---|
| Não duplicar na retry | Atomicidade do request (all-or-nothing) `[alta]` `[S7]` | Chave de negócio própria + tabela de execuções; retry só depois de reconciliar |
| Saber se já aplicou | `change_event` (campo a campo, 30 dias) e `change_status` (o que mudou) `[alta]` `[S12]` `[S13]` | Reconciliação por `resource_name` como chave natural |
| Distinguir falha de rede de falha de negócio | Erro sem `GoogleAdsFailure` (ex.: rede) **não** consome quota e nunca chegou ao serviço `[alta]` `[S14]` | Retry seguro só nessa classe; `GoogleAdsFailure` já consumiu quota e pode ter aplicado |
| Backoff | `RESOURCE_TEMPORARILY_EXHAUSTED` é retryable `[alta]` `[S15]` | Backoff exponencial (a doc sugere 5s → 10s → 20s) `[média]` `[S16]` |

Classificação oficial de erros: **Authentication**, **Retryable**, **Validation**,
**Sync-related** `[alta]` `[S16]`.

---

## 6. Limites, quotas e rate limits

### Quota diária (por developer token) `[alta]` `[S14]`

| Nível de acesso | Contas de produção | Contas de teste |
|---|---|---|
| Explorer | **2.880** operações/dia | 15.000 operações/dia |
| Basic | **15.000** operações/dia | 15.000 operações/dia |
| Standard | não numerado nesta página — remete a Access Levels `[NÃO CONFIRMADO]` | — |

Erro ao estourar: `RESOURCE_EXHAUSTED`.

Contagem: `Search`/`SearchStream` = **1 operação** cada (independente do número de lotes do
stream); páginas seguintes com `next_page_token` **válido** **não** contam; token expirado/inválido
conta e ainda dá exceção; requests rejeitados com `GoogleAdsFailure` **contam** `[alta]` `[S14]`.

### Por request `[alta]` `[S14]`

| Limite | Valor | Erro |
|---|---|---|
| Operações de mutate por request | **10.000** | `TOO_MANY_MUTATE_OPERATIONS` |
| Operações de "action" por request | **100** | `TOO_MANY_ACTION_OPERATIONS` |
| Tamanho da resposta gRPC | **64 MB** | `429 Resource Exhausted` — **não** gera `GoogleAdsError` |
| Itens num `IN` de GAQL | **20.000** | `FILTER_HAS_TOO_MANY_VALUES` |
| Conversões por upload | 2.000 | `TOO_MANY_CONVERSIONS_IN_REQUEST` |
| Billing / Account Budget | **1** operação por mutate | `TOO_MANY_MUTATE_OPERATIONS` |
| Planning Service | 1 QPS | `RESOURCE_EXHAUSTED` |

### Rate limit `[alta]` `[S15]`

Token bucket por **CID** *e* por **developer token**, independentes. O QPS exato **varia com a
carga do servidor** e não é publicado. Violação → `RESOURCE_TEMPORARILY_EXHAUSTED`.
Nota importante: agrupar operações reduz o limite de *requests* por minuto mas pode acionar o
limite de *operações* por minuto contra uma única conta.

### Limites de sistema relevantes `[alta]` `[S17]`

| Objeto | Limite | Erro |
|---|---|---|
| Nome de campanha / ad group | 256 caracteres | `StringLengthError.TOO_LONG` / `AdGroupError.INVALID_ADGROUP_NAME` |
| Headline | 30 caracteres | `AdError.LINE_TOO_WIDE` |
| Description | 90 caracteres | `AdError.LINE_TOO_WIDE` |
| Path1/Path2 | 15 caracteres | `AdError.LINE_TOO_WIDE` |
| Final URL de **anúncio** | 2.084 bytes (UTF-8, prefixo do protocolo conta) | `StringLengthError.TOO_LONG` |
| Final URL de **critério** | 2.047 bytes | `StringLengthError.TOO_LONG` |
| Keyword | 80 caracteres | `CriterionError.KEYWORD_TEXT_TOO_LONG` |
| URL de placement | 250 caracteres (protocolo é removido, não conta) | `CriterionError.PLACEMENT_URL_IS_TOO_LONG` |
| Orçamentos compartilhados / não compartilhados por conta | 11.000 / 20.000 | `ResourceCountLimitExceededError.ACCOUNT_LIMIT` |
| Estratégias de lance em ad groups por campanha | 1.000 | `ResourceCountLimitExceededError.CAMPAIGN_LIMIT` |
| Blocos de IP excluídos por campanha | 500 | `ResourceCountLimitExceededError.CAMPAIGN_LIMIT` |
| Labels por entidade / por conta | 50 / 100.000 | `ResourceCountLimitExceededError.*` |

**Máximo de campanhas por conta: `[NÃO CONFIRMADO]`.** A página de limites de sistema declara
explicitamente que esse número não está lá ("See *About your Google Ads account limits* for
product limits such as the maximum number of campaigns per account") `[alta]` `[S17]`.
Limites específicos de PMax estão em `performance-max.md`.

---

## 7. Leitura: GAQL e reporting

- `GoogleAdsService.Search` (paginado) e `SearchStream` (streaming) `[alta]` `[S18]`.
- `GoogleAdsFieldService` é o catálogo de campos com **compatibilidade** declarada — use-o para
  saber se um `segments.X` pode acompanhar um `metrics.Y` no mesmo `FROM` `[alta]` `[S18]`.
- Segmentação: a API aceita **vários segmentos no mesmo query** (a UI aceita um). Cada segmento
  adicional multiplica linhas `[alta]` `[S19]`.
- **Segmentação implícita**: todo relatório já é segmentado pelo `resource_name` do `FROM`, mesmo
  sem selecioná-lo `[alta]` `[S19]`.
- Nem todo `segments.*` é selecionável em todo recurso, e precisa ser compatível com os demais
  segmentos e métricas escolhidos `[alta]` `[S19]`.
- `metrics.optimization_score_url` e `metrics.optimization_score_uplift` existem em `customer` e
  `campaign`; segmentáveis por `segments.recommendation_type` `[alta]` `[S20]`.

---

## 8. `change_event` e `change_status`

| | `change_event` | `change_status` |
|---|---|---|
| Granularidade | Campo a campo: `old_resource`, `new_resource`, `changed_fields`, `resource_change_operation` | Só "este recurso mudou", com `ADDED`/`CHANGED`/`REMOVED` |
| Janela | **Obrigatoriamente dentro dos últimos 30 dias** | filtrável por data |
| `LIMIT` | **Obrigatório**, máximo **10.000 linhas** | — |
| Latência | até **3 minutos** | — |
| Autoria | `user_email` e `client_type` (distingue API de web client) | — |
| Cobertura | **Não** traz todas as mudanças | Mais abrangente; múltiplas mudanças no período colapsam na **última** |
| Ruído | — | Mudança em filho pode ser reportada no **pai** (ex.: bid modifier de ad group aparece como `AD_GROUP`) |

Fontes: `[alta]` `[S12]` `[S13]`. Paginação além de 10.000: anote o timestamp da última linha e
reinicie o intervalo depois dele `[alta]` `[S12]`.

Para o VOLC: `change_status` é o detector ("o que mexeu"), `change_event` é o forense
("o que exatamente mudou e quem"). Nem toda linha de `change_status` tem contrapartida em
`change_event` `[alta]` `[S13]`.

---

## 9. `recommendation`

- `RecommendationService`: `ApplyRecommendation`, `DismissRecommendation` `[alta]` `[S20]`.
- `RecommendationSubscriptionService`: aplica certos tipos automaticamente `[alta]` `[S20]`.
- Optimization score existe em `Customer` e `Campaign`. Score agregado de várias contas =
  `Customer.optimization_score * Customer.optimization_score_weight` `[alta]` `[S20]`.

Tipos com efeito direto nos quatro canais `[alta]` `[S20]`:

| Canal | Tipos |
|---|---|
| Todos | `CAMPAIGN_BUDGET`, `FORECASTING_CAMPAIGN_BUDGET`, `MARGINAL_ROI_CAMPAIGN_BUDGET`, `MOVE_UNUSED_BUDGET`, `TARGET_CPA_OPT_IN`, `TARGET_ROAS_OPT_IN`, `MAXIMIZE_CONVERSIONS_OPT_IN`, `MAXIMIZE_CONVERSION_VALUE_OPT_IN`, `MAXIMIZE_CLICKS_OPT_IN`, `RAISE_TARGET_CPA`, `RAISE_TARGET_CPA_BID_TOO_LOW`, `LOWER_TARGET_ROAS`, `SET_TARGET_CPA` |
| Search | `KEYWORD`, `TEXT_AD`, `RESPONSIVE_SEARCH_AD`, `RESPONSIVE_SEARCH_AD_ASSET`, `RESPONSIVE_SEARCH_AD_IMPROVE_AD_STRENGTH`, `USE_BROAD_MATCH_KEYWORD`, `SEARCH_PARTNERS_OPT_IN`, `OPTIMIZE_AD_ROTATION` |
| Display | `DISPLAY_EXPANSION_OPT_IN`, `CUSTOM_AUDIENCE_OPT_IN`, `DYNAMIC_IMAGE_EXTENSION_OPT_IN` |
| Demand Gen | `IMPROVE_DEMAND_GEN_AD_STRENGTH` |
| PMax | `PERFORMANCE_MAX_OPT_IN`, `IMPROVE_PERFORMANCE_MAX_AD_STRENGTH`, `PERFORMANCE_MAX_FINAL_URL_OPT_IN`, `MIGRATE_DYNAMIC_SEARCH_ADS_CAMPAIGN_TO_PERFORMANCE_MAX` |

`IMPROVE_PERFORMANCE_MAX_AD_STRENGTH` é o único caminho oficial para chegar a "Excellent"
em asset group `[média]` `[S20]`.

---

## 10. `customer_status` e o recurso `customer`

`Customer.status` é **Output only** `[alta]` (proto). Valores:
`UNSPECIFIED, UNKNOWN, ENABLED, CANCELED, SUSPENDED, CLOSED` `[alta]`.

Outros campos do `customer` que decidem o que o VOLC pode fazer `[alta]` (proto):

| Campo | Natureza | Por que importa |
|---|---|---|
| `currency_code`, `time_zone` | **Immutable** | Fixa a moeda dos micros e o fuso do relatório; não há "editar" |
| `manager`, `test_account` | Output only | Roteia comportamento (test account tem quota e features diferentes) |
| `optimization_score`, `optimization_score_weight` | Output only | Insumo do score agregado |
| `conversion_tracking_setting` | mutável parcialmente | Aponta a conta dona da conversão |
| `tracking_url_template`, `final_url_suffix`, `auto_tagging_enabled`, `call_reporting_setting` | "Only mutable in an `update` operation" | Não podem ser setados na criação |

---

## 11. Conversion actions, goals e Smart Bidding

Cadeia oficial `[alta]` `[S21]`:

1. `ConversionAction` tem `category` e `origin`. Os campos-chave do proto são
   `primary_for_goal`, `include_in_conversions_metric`, `counting_type`,
   `attribution_model_settings`, `value_settings`, janelas de lookback `[alta]` (proto).
2. Ao criar uma `ConversionAction`, o Google Ads **cria automaticamente** o
   `CustomerConversionGoal` do par `(category, origin)` se não existir, e um
   `CampaignConversionGoal` por campanha.
3. `CustomerConversionGoal.biddable` = **default da conta**: `true` significa "lançar e otimizar
   para esse goal"; `false` significa "só reportar".
4. `CampaignConversionGoal` **sobrepõe** o nível cliente para aquela campanha.
5. Se `CampaignConversionGoal` não bastar, use `CustomConversionGoal` + o campo
   `campaign.selective_optimization` para escolher `ConversionAction` específicas.
6. Ao mutar `CampaignConversionGoal`, o Google fixa `ConversionGoalCampaignConfig.goal_config_level`
   em `CAMPAIGN` e **para** de propagar mudanças de conta para aquela campanha.

Implicação para Smart Bidding: `MAXIMIZE_CONVERSIONS`/`TARGET_CPA` e
`MAXIMIZE_CONVERSION_VALUE`/`TARGET_ROAS` otimizam **exatamente o conjunto de goals biddable**
vigente na campanha. Trocar bidding sem olhar goals é mudar a métrica-alvo sem saber `[média]` `[S21]`.

`ConversionAction.origin` aparece na UI como **"Conversion source"**, e não como o campo
"Source" da aba Conversion actions — armadilha de nomenclatura `[alta]` `[S21]`.

---

## 12. `campaign.status` × `primary_status` — o par que decide diagnóstico

Três campos distintos, três perguntas distintas `[alta]` (proto):

| Campo | Natureza | Pergunta que responde | Valores |
|---|---|---|---|
| `campaign.status` | **Gravável** | O que o operador *pediu*? | `ENABLED`, `PAUSED`, `REMOVED` |
| `campaign.serving_status` | Output only | Estado bruto de veiculação | `SERVING`, `NONE`, `ENDED`, `PENDING`, `SUSPENDED` |
| `campaign.primary_status` | Output only | **Está entregando? Se não, em que classe de problema?** | `ELIGIBLE`, `PAUSED`, `REMOVED`, `ENDED`, `PENDING`, `MISCONFIGURED`, `LIMITED`, `LEARNING`, `NOT_ELIGIBLE` |
| `campaign.primary_status_reasons[]` | Output only | **Por quê?** | 44 valores |

O erro clássico é ler `status = ENABLED` e concluir "está rodando". `ENABLED` +
`primary_status = MISCONFIGURED` é uma campanha ligada que não entrega nada.

Razões (`CampaignPrimaryStatusReason`) agrupadas por o que o VOLC deve fazer `[alta]` (proto):

| Classe | Valores |
|---|---|
| Intenção do operador | `CAMPAIGN_REMOVED`, `CAMPAIGN_PAUSED`, `CAMPAIGN_PENDING`, `CAMPAIGN_ENDED`, `CAMPAIGN_DRAFT` |
| Orçamento | `BUDGET_CONSTRAINED`, `BUDGET_MISCONFIGURED` |
| Lance | `BIDDING_STRATEGY_MISCONFIGURED`, `BIDDING_STRATEGY_LIMITED`, `BIDDING_STRATEGY_LEARNING`, `BIDDING_STRATEGY_CONSTRAINED` |
| Estrutura ad-group (Search/Display) | `AD_GROUPS_PAUSED`, `NO_AD_GROUPS`, `KEYWORDS_PAUSED`, `NO_KEYWORDS`, `AD_GROUP_ADS_PAUSED`, `NO_AD_GROUP_ADS` |
| Estrutura asset-group (PMax) | `NO_ASSET_GROUPS`, `ASSET_GROUPS_PAUSED`, `HAS_ASSET_GROUPS_DISAPPROVED`, `HAS_ASSET_GROUPS_LIMITED_BY_POLICY`, `MOST_ASSET_GROUPS_UNDER_REVIEW` |
| Política de anúncio | `HAS_ADS_DISAPPROVED`, `HAS_ADS_LIMITED_BY_POLICY`, `MOST_ADS_UNDER_REVIEW` |
| Assets obrigatórios | `MISSING_LEAD_FORM_EXTENSION`, `MISSING_CALL_EXTENSION`, `LEAD_FORM_EXTENSION_*`, `CALL_EXTENSION_*` |
| Segmentação | `SEARCH_VOLUME_LIMITED`, `MISSING_LOCATION_TARGETING` |
| Outros | `CAMPAIGN_GROUP_PAUSED`, `CAMPAIGN_GROUP_ALL_GROUP_BUDGETS_ENDED`, `APP_NOT_RELEASED`, `APP_PARTIALLY_RELEASED`, `NO_MOBILE_APPLICATION_AD_GROUP_CRITERIA`, `CAMPAIGN_NOT_BOOKED`, `BOOKING_HOLD_EXPIRING`, `BOOKING_HOLD_EXPIRED`, `BOOKING_CANCELLED` |

O mesmo par existe em `ad_group.primary_status(_reasons)`,
`ad_group_ad.primary_status(_reasons)`, `ad_group_criterion.primary_status(_reasons)`,
`asset_group.primary_status(_reasons)` e `asset_group_asset.primary_status(_reasons)` (este com
`AssetLinkPrimaryStatus` + `primary_status_details`) `[alta]` (proto).

**`[NÃO CONFIRMADO]`**: não existe guia dedicado a primary status —
`/docs/reporting/primary-status` retorna **404**. A referência é o enum RPC.

---

## 13. Política e eligibility na leitura

Padrão comum `[alta]` (proto):

- `ad_group_ad.policy_summary` → `AdGroupAdPolicySummary { policy_topic_entries[], review_status, approval_status }`
- `asset.policy_summary` + `asset.field_type_policy_summaries[]` → mesma forma
- `asset_group_asset.policy_summary` → idem
- `ad_group_criterion.approval_status` + `ad_group_criterion.disapproval_reasons[]`
- `asset_group_signal.approval_status` + `disapproval_reasons[]` (só para search themes)

| Enum | Valores |
|---|---|
| `PolicyApprovalStatus` | `DISAPPROVED`, `APPROVED_LIMITED`, `APPROVED`, `AREA_OF_INTEREST_ONLY` |
| `PolicyReviewStatus` | `REVIEW_IN_PROGRESS`, `REVIEWED`, `UNDER_APPEAL`, `ELIGIBLE_MAY_SERVE` |

`APPROVED_LIMITED` é aprovado **com restrição de veiculação** — o VOLC deve tratar como alerta,
não como verde `[média]` (semântica do enum + `HAS_ADS_LIMITED_BY_POLICY`).

Isenção de política: `/docs/policy-exemption/*` cobre pedido de exceção para anúncios e keywords `[média]` `[S22]`.

---

## 14. `campaign_criterion` × `ad_group_criterion`

Três níveis, com regras diferentes `[alta]` `[S23]`:

| Nível | Serviço | Restrição |
|---|---|---|
| Cliente | `CustomerNegativeCriterionService` | **Só negativo** |
| Campanha | `CampaignCriterionService` | Positivo e negativo, conforme o tipo |
| Ad group | `AdGroupCriterionService` | Positivo e negativo, conforme o tipo |

Estrutura idêntica nos dois principais `[alta]` (proto):

- O tipo de critério é um **`oneof` inteiramente `Immutable`** (`keyword`, `location`, `audience`,
  `placement`, `topic`, …). Não existe "editar o critério" — só remover e recriar.
- `negative` é **`Immutable`**: alternar entre targeting e exclusão **exige recriar** o critério.
- `criterion_id` e `display_name` são **Output only** e **ignorados no mutate**.
- `bid_modifier`: faixa **0.1 – 10.0**.
- Só em `ad_group_criterion`: `quality_info`, `system_serving_status`, `approval_status`,
  `disapproval_reasons`, `position_estimates`, bids efetivos e `primary_status`.
- Só em `campaign_criterion`: `campaign` (immutable) e critérios exclusivos de campanha
  (`ad_schedule`, `device`, `carrier`, `ip_block`, `content_label`, `proximity`,
  `location_group`, `listing_scope`, `keyword_theme`, `local_service_id`).

Assimetrias que mordem `[alta]` `[S23]`:

| Tipo | Regra |
|---|---|
| Keyword | No nível **campanha só pode ser negativa** |
| Parental status | No nível **campanha só negativo**; no ad group positivo e negativo |
| Placement | **Só negativo** em qualquer nível (campanha, ad group, cliente) |
| Audience | **Só no ad group**, só positivo |
| Custom intent | **Só no ad group** |
| Content label | Campanha e cliente, **só negativo** |
| Negative keyword list / Placement list | **Só no cliente**, só negativo |

---

## 15. Assets: o modelo compartilhado

`Asset` (dado) → `AssetFieldType` (papel) → linkagem (`CustomerAsset` / `CampaignAsset` /
`AdGroupAsset` / `AssetGroupAsset` / `AssetSetAsset`) `[alta]` `[S24]`.

- Um `Asset` pode ser linkado a **vários** `AssetSet`, mas um `AssetSetAsset` liga a **um** só `[alta]` `[S24]`.
- `AssetService` cria apenas `YoutubeVideoAsset`, `MediaBundleAsset` e `ImageAsset`;
  **`TextAsset` deve ser criado inline no anúncio** `[alta]` `[S25]`.
- No proto: `asset.image_asset` e `asset.location_asset` são **Output only**;
  `youtube_video_asset`, `media_bundle_asset`, `text_asset`, `call_to_action_asset`,
  `demand_gen_carousel_card_asset`, `hotel_property_asset`, `app_deep_link_asset` e
  `youtube_video_list_asset` são **Immutable** `[alta]` (proto).
  Ou seja: **o conteúdo de um asset não se edita — cria-se outro e re-linka.**
- `ImageAsset.data` (bytes) é **mutate-only** — sobe na criação e nunca volta na leitura `[alta]` (proto).
- `Asset.source` (`AssetSource`) distingue user-created de gerado por automação; assets de text
  customization **não podem ser modificados** `[alta]` `[S24]`.

`AssetFieldType` tem 37 valores no SDK instalado (v25.0); a v25.1 acrescenta `TEXT_DISCLAIMER` `[alta]`.

---

## 16. Orçamento e teto real de gasto

Escrito a pedido do condutor para o Plano de Canário. A pergunta que esta seção responde é:
**se eu autorizo R$ X/dia por N dias, qual é o maior valor que a plataforma pode cobrar?**

### 16.1 Os dois tetos publicados

| Teto | Fórmula | Fonte | Conf. |
|---|---|---|---|
| **Diário** | **2 × o orçamento diário médio** | "For most campaigns, the daily spending limit is your average daily budget multiplied by 2." | `[alta]` `[S32]` `[S33]` `[S34]` |
| **Mensal** | **30,4 × o orçamento diário médio** | "your monthly spending limit is 30.4 times your average daily budget"; e o proto: "The effective monthly spend is **capped at 30.4 times** this daily amount" | `[alta]` `[S32]` `[S33]` + **P** |

O 30,4 é 365/12 — o número médio de dias num mês `[alta]` `[T11]` `[S33]`.

Exemplo oficial: diário US$ 10 → limite diário US$ 20, limite mensal US$ 304 `[alta]` `[S32]`.

**Resposta direta às perguntas 1 e 2 do condutor:** sim, o Google pode veicular acima do diário
num dia específico, e o limite é **exatamente 2×** — a memória estava certa e agora tem fonte.
O teto mensal de **30,4× o diário** também está confirmado, e por **duas fontes independentes**
(Help Center e a docstring do proto instalado), o que é o grau mais alto de evidência disponível aqui.

**Exceção documentada:** campanhas *Pay for conversions* — na API, `Campaign.payment_mode = CONVERSIONS`
(`PaymentMode` = `CLICKS`, `CONVERSION_VALUE`, `CONVERSIONS`, `GUEST_STAY`) — **não têm limite
diário**; ficam sujeitas apenas ao limite mensal `[alta]` `[S32]` + P. Um canário precisa checar
`campaign.payment_mode` antes de assumir o teto de 2×.

### 16.2 O teto de uma janela de N dias — e por que não é `diário × dias`

O único teto publicado na granularidade de dias é o diário. Portanto, para uma janela curta:

> **Teto defensável de N dias = N × (2 × orçamento diário)**

Para o canário do condutor — R$ 20/dia por 3 dias — isso dá **3 × R$ 40 = R$ 120**.
`[média]` (aritmética direta sobre um teto `[alta]`).

**O teto nominal de R$ 60 (R$ 20 × 3) não é um teto.** É a média que a plataforma persegue, não
o limite que ela respeita. Os R$ 120 que o §4 do Plano de Canário carrega como *hipótese
conservadora* deixam de ser hipótese: passam a ser derivação de um limite oficial.

Por que o teto mensal não reduz esse número para 3 dias:

- 30,4 × R$ 20 = R$ 608, muito acima de R$ 120 — não é a restrição ativa.
- O Help Center diz que, para campanha iniciada no meio do mês, "we'll only take into account the
  **days the campaign was running**" `[alta]` `[S32]`. Isso *sugere* um rateio que poderia baixar
  o teto de 3 dias para R$ 60 — mas **a fórmula exata do rateio não é publicada**.
  `[NÃO CONFIRMADO]`. Procurei em `budgets/overview`, `budgets/create-budgets`,
  "About spending limits", "About average daily budgets", "About overdelivery" e "Budgets overview":
  nenhuma das seis publica a fórmula.
- **Um plano que autoriza gasto não pode se apoiar num rateio não publicado.** Use R$ 120.

### 16.3 ⚠️ O que a API reporta não é o que é cobrado

Distinção oficial, e é a armadilha mais cara desta seção `[alta]` `[S32]` `[S34]` `[S35]`:

| Termo | Definição oficial |
|---|---|
| **Served cost** | "the cost of all the clicks or impressions that the campaign received" |
| **Billed cost** | "the actual amount you're responsible for paying after adjustments" |

> "While served costs might exceed daily or monthly spending limits, **you'll never pay more than
> these two limits**. When such a situation occurs, **Google will cover the difference**." `[alta]` `[S32]`

O exemplo oficial: diário US$ 10, limite US$ 20, dia de demanda alta gera **US$ 23 de served
cost** → billed cost é US$ 20 e o Google absorve os US$ 3 `[alta]` `[S32]`.

**E a API só expõe o served cost.** Verifiquei por introspecção do proto v25: `metrics.cost_micros`
é "The sum of your cost-per-click (CPC) and cost-per-thousand impressions (CPM) costs during this
period", e **não existe nenhuma métrica contendo "bill" em `Metrics`** `[alta]` P. O relatório
*Billed cost* existe apenas na UI, em Report editor → Template gallery → Billing `[alta]` `[S32]` `[S34]`.

Consequência operacional para o canário:

| Se o gatilho de aborto for | O que acontece |
|---|---|
| `metrics.cost_micros > teto` | **Pode disparar falso.** O served cost tem permissão documentada para passar do teto sem que haja cobrança acima dele |
| Leitura observada com margem | Correto, desde que a margem absorva o excesso de served cost |

Se o condutor trocar o teto calculado por um **teto observado**, o número observado precisa ser
lido como served cost, e o abort deve ter folga sobre o teto de billing — ou o canário vai abortar
por um gasto que ninguém pagou.

### 16.4 `delivery_method`: `ACCELERATED` está sunsetado desde 2020

O enum **ainda existe** no proto v25 — `BudgetDeliveryMethod` = `UNSPECIFIED, UNKNOWN, STANDARD,
ACCELERATED`, com `ACCELERATED` documentado como "The budget server will not throttle serving, and
ads will serve as fast as possible" `[alta]` P. **A presença no enum não significa que seja
utilizável.**

Cronologia oficial, do Google Ads Developer Blog `[alta]` `[S38]`:

| Data | O que aconteceu |
|---|---|
| Outubro/2019 | Sunset anunciado para campanhas **Search**, **Shopping** e **shared budgets** — já tornadas indisponíveis |
| **Fim de abril/2020** | Sunset estendido a **todos os demais tipos**, incluindo **Display**, App e vídeo, para orçamentos **compartilhados e não compartilhados**, e em **todas as versões** da AdWords API, Google Ads API e Ads scripts |
| Maio/2020 | Até **editar** `amount` ou `status` de orçamentos `ACCELERATED` remanescentes passa a dar erro |

Erros que a própria Google Ads API retorna desde então `[alta]` `[S38]`:

| Operação | Campo | Erro |
|---|---|---|
| Criar orçamento com `ACCELERATED` | `CampaignBudgetService.delivery_method` | `OperationAccessDenied.ACTION_NOT_PERMITTED` |
| Mudar `STANDARD` → `ACCELERATED` | `CampaignBudgetService.delivery_method` | `OperationAccessDenied.ACTION_NOT_PERMITTED` |
| Apontar campanha para orçamento `ACCELERATED` preexistente | `CampaignService.campaign_budget` | `OperationAccessDenied.ACTION_NOT_PERMITTED` |

O proto v25 ainda carrega o erro dedicado `CampaignBudgetError.CANNOT_USE_ACCELERATED_DELIVERY_MODE`
(valor 20): "Cannot use accelerated delivery method on this budget" `[alta]` P.

> **Resposta direta à pergunta 3 do condutor.** O argumento do diagnóstico — "é `STANDARD`, logo
> não esgota de manhã" — está **correto e agora tem fonte**, mas por um motivo mais forte do que o
> assumido: não é que a campanha *esteja* em `STANDARD` por escolha do operador; é que
> **`ACCELERATED` não é selecionável em nenhum tipo de campanha desde abril de 2020**. Todo
> orçamento é `STANDARD` por imposição da plataforma.
>
> **Mas cuidado com o que `STANDARD` garante.** A definição do proto é "throttle serving **evenly
> across the entire time period**" `[alta]` P — isso é *pacing*, e o período é o mês. `STANDARD`
> **não** é uma trava diária de 1× o orçamento. O teto diário continua sendo **2×**. Um plano que
> escreva "está em STANDARD, logo não passa do diário" trocaria um erro por outro.

### 16.5 Orçamento compartilhado — o teto vale por orçamento ou por campanha?

Confirmado `[alta]` `[S36]`:

- Shared budget é "**a single average daily budget** that's shared by multiple campaigns in an account".
- Realoca verba subutilizada de uma campanha para outra dentro do mesmo orçamento.
- Disponível **apenas** em Search, Shopping, Display e Video.
- **Incompatível** com Performance Max, App, Hotel com estratégia Commission, Smart Shopping,
  campanhas em experimento e campanhas com orçamento total.

Confirmado na API `[alta]` `[S26]` `[S27]` `[S29]` + P:

- `explicitly_shared` **default é `true`** se omitido na criação — o VOLC precisa setar `false`
  explicitamente para um orçamento dedicado.
- **`true` → `false` é irreversível**: `CampaignBudgetError.CANNOT_UPDATE_CAMPAIGN_BUDGET_TO_IMPLICITLY_SHARED`.
  ("A shared campaign budget can never become non-shared.")
- Campanha com experimento ativo **exige** orçamento não compartilhado.
- Remover orçamento em uso: `CampaignBudgetError.CAMPAIGN_BUDGET_IN_USE`. Cheque
  `campaign_budget.reference_count > 0` antes `[alta]` `[S30]`.

**Resposta à pergunta 4: `[NÃO CONFIRMADO]` na formulação exata.** Nenhuma das fontes oficiais que
consultei declara literalmente se o multiplicador de 2× incide sobre o **pool** compartilhado ou
**por campanha** que o usa. Procurei em "About spending limits" `[S32]`, "About shared budgets"
`[S36]`, "Budgets overview" `[S35]`, "About average daily budgets" `[S33]`, e nos guias de API
`budgets/overview` `[T11]` e `budgets/share-budgets` `[S27]`. A página de limites fala em limite
"for a campaign"; a de shared budgets fala em "a single average daily budget". As duas leituras
sobrevivem ao texto.

> **Recomendação operacional para o canário:** use `explicitly_shared = false`. Com orçamento
> dedicado a uma única campanha, o teto é inequívoco (2× diário, N × 2× diário na janela) e a
> ambiguidade desaparece. Como a transição para compartilhado é irreversível, começar dedicado
> também preserva a opção.

### 16.6 O teto que ninguém pediu e pode invalidar a leitura

Existe um **limite de gasto diário no nível da conta**, distinto de tudo acima `[alta]` `[S37]`:

- "determines the maximum amount your Google Ads account can spend per day across all ad campaigns";
- **"This limit overrides any campaign-level budgets you've set"**;
- aplicado com frequência a **contas novas**, contas com mudanças recentes, contas sob suspeita ou
  **pendentes de verificação de anunciante**;
- ao ser atingido, "your ads will stop showing and automatically resume the next day";
- **não é possível solicitar aumento**; é gerido por sistemas automatizados.

Para um canário em conta nova, isso corta para o lado seguro no gasto — mas pode **invalidar a
leitura**: entrega interrompida por trava de conta parece falta de demanda. Vale registrar o
estado da conta antes de interpretar um canário que gastou menos do que o esperado.

### 16.7 Erros de orçamento que o VOLC vai encontrar

| Erro | Quando |
|---|---|
| `CampaignBudgetError.BUDGET_BELOW_PER_DAY_MINIMUM` (22) | Abaixo do mínimo por dia da campanha; detalhe em `details.budget_per_day_minimum_error_details` (é o caminho do mínimo de 5 USD do Demand Gen, §1) |
| `CampaignBudgetError.CANNOT_USE_ACCELERATED_DELIVERY_MODE` (20) | `delivery_method = ACCELERATED` |
| `CampaignBudgetError.TOTAL_BUDGET_AMOUNT_MUST_BE_UNSET_FOR_BUDGET_PERIOD_DAILY` (18) / `BUDGET_AMOUNT_MUST_BE_UNSET_FOR_CUSTOM_BUDGET_PERIOD` (21) | Misturar `amount_micros` e `total_amount_micros` |
| `CampaignBudgetError.CANNOT_UPDATE_CAMPAIGN_BUDGET_TO_IMPLICITLY_SHARED` (7) | Tentar voltar de compartilhado para dedicado |
| `CampaignBudgetError.CAMPAIGN_BUDGET_IN_USE` (3) | Remover orçamento com `reference_count > 0` |
| `CampaignBudgetError.MONEY_AMOUNT_LESS_THAN_CURRENCY_MINIMUM_CPC` (13) / `NON_MULTIPLE_OF_MINIMUM_CURRENCY_UNIT` (16) / `MONEY_AMOUNT_IN_WRONG_CURRENCY` (12) | Valor mal formado para a moeda da conta (`customer.currency_code`, imutável — §10) |
| `ResourceCountLimitExceededError.ACCOUNT_LIMIT` | 11.000 compartilhados / 20.000 dedicados (§6) |

Enum completo lido do proto instalado `[alta]` P; descrições cruzadas com `[S29]`.

### 16.8 Resumo para quem só precisa do número

| Pergunta | Resposta | Conf. |
|---|---|---|
| Pode gastar acima do diário num dia? | Sim, **até 2×** | `[alta]` |
| Teto mensal? | **30,4 ×** o diário | `[alta]` (duas fontes) |
| Teto de 3 dias a R$ 20/dia? | **R$ 120** (3 × 2 × 20) | `[média]` (aritmética sobre teto `[alta]`) |
| O nominal de R$ 60 é teto? | **Não.** É a média perseguida | `[alta]` |
| Rateio do teto mensal para campanha de 3 dias poderia baixar para R$ 60? | Talvez — **fórmula não publicada**, não usar | `[NÃO CONFIRMADO]` |
| `ACCELERATED` existe na v25? | No enum sim; **inutilizável desde abril/2020**, erro `ACTION_NOT_PERMITTED` | `[alta]` |
| `STANDARD` impede passar do diário? | **Não.** É pacing mensal; o teto diário segue 2× | `[alta]` |
| Teto de shared budget: por pool ou por campanha? | Não declarado — **use orçamento dedicado** | `[NÃO CONFIRMADO]` |
| `metrics.cost_micros` é o valor cobrado? | **Não. É served cost.** Não existe métrica de billed cost na API | `[alta]` |

---

## Fontes desta página (todas consultadas em 26/08/2026)

| Ref | URL |
|---|---|
| S1 | https://developers.google.com/google-ads/api/docs/sunset-dates |
| S2 | https://developers.google.com/google-ads/api/docs/release-notes |
| S3 | https://developers.google.com/google-ads/api/docs/deprecations |
| S4 | https://developers.google.com/google-ads/api/docs/mutating/service-mutates |
| S5 | https://developers.google.com/google-ads/api/docs/mutating/bulk-mutate |
| S6 | https://developers.google.com/google-ads/api/docs/batch-processing/temporary-ids |
| S7 | https://developers.google.com/google-ads/api/docs/concepts/changing-objects |
| S8 | https://developers.google.com/google-ads/api/docs/mutating/best-practices |
| S9 | https://developers.google.com/google-ads/api/docs/mutating/overview |
| S10 | https://developers.google.com/google-ads/api/docs/best-practices/testing |
| S11 | https://developers.google.com/google-ads/api/docs/best-practices/partial-failures |
| S12 | https://developers.google.com/google-ads/api/docs/change-event |
| S13 | https://developers.google.com/google-ads/api/docs/change-status |
| S14 | https://developers.google.com/google-ads/api/docs/best-practices/quotas |
| S15 | https://developers.google.com/google-ads/api/docs/productionize/rate-limits |
| S16 | https://developers.google.com/google-ads/api/docs/best-practices/error-types |
| S17 | https://developers.google.com/google-ads/api/docs/best-practices/system-limits |
| S18 | https://developers.google.com/google-ads/api/docs/query/overview |
| S19 | https://developers.google.com/google-ads/api/docs/reporting/segmentation |
| S20 | https://developers.google.com/google-ads/api/docs/recommendations |
| S21 | https://developers.google.com/google-ads/api/docs/conversions/goals/overview |
| S22 | https://developers.google.com/google-ads/api/docs/policy-exemption/overview |
| S23 | https://developers.google.com/google-ads/api/docs/targeting/criteria |
| S24 | https://developers.google.com/google-ads/api/docs/assets/overview |
| S25 | https://developers.google.com/google-ads/api/reference/rpc/v25/AssetService (descrição do serviço, via snapshot `volc_ads/google_ads_api/api_reference_v25.md`) |
| S26 | https://developers.google.com/google-ads/api/docs/campaigns/budgets/create-budgets |
| S27 | https://developers.google.com/google-ads/api/docs/campaigns/budgets/share-budgets |
| S28 | https://developers.google.com/google-ads/api/docs/campaigns/budgets/assign-budgets |
| S29 | https://developers.google.com/google-ads/api/docs/campaigns/budgets/restrictions-errors |
| S30 | https://developers.google.com/google-ads/api/docs/campaigns/budgets/remove-budgets |
| S31 | https://developers.google.com/google-ads/api/docs/campaigns/budgets/track-performance |
| S32 | https://support.google.com/google-ads/answer/10486637 — *About spending limits* (Help Center oficial) |
| S33 | https://support.google.com/google-ads/answer/6385083 — *About average daily budgets* |
| S34 | https://support.google.com/google-ads/answer/1704443 — *About overdelivery and your average daily budget* |
| S35 | https://support.google.com/google-ads/answer/10486536 — *Budgets overview* |
| S36 | https://support.google.com/google-ads/answer/10487241 — *About shared budgets* |
| S37 | https://support.google.com/google-ads/answer/12795729 — *About daily spending limits in Google Ads accounts* |
| S38 | https://ads-developers.googleblog.com/2020/01/complete-sunset-of-accelerated-budget.html — Google Ads Developer Blog, *Complete sunset of accelerated budget delivery* (referencia o anúncio de out/2019) |
| T11 | https://developers.google.com/google-ads/api/docs/campaigns/budgets/overview |
| P | Protos do SDK instalado: `backend/.venv/lib/python3.14/site-packages/google/ads/googleads/v25/` (`google-ads` 31.3.0) |
