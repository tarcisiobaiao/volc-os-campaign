# Pesquisa A: APIs e execução Google Ads (14/10/2026)

Escopo: A01–A40 + A41–A46 (novos); detalhe em `resultados.json`. Provas: páginas primárias, PyPI/GitHub API, introspecção offline
do SDK `google-ads` 33.0.0 (v25) e leitura de clones no scratch. Nenhuma chamada autenticada nem credencial lida.

Placar: 14 confirmadas, 24 parciais, 7 refutadas, 1 não verificável.
Refutadas: A02 (BatchJob "obrigatório"/evita rate limit), A16 (tightrope não existe), A24
(OfflineUserDataJob para conversão de clique), A29 (pausar headline de RSA), A30 (scalper por
bid modifier sob Smart Bidding), A39 (OCI "controla o cérebro"), A11 (agente autônomo oficial).

## 1. Atomicidade e quotas

- `GoogleAdsService.Mutate` mistura tipos de recurso; per-resource services aceitam um tipo só
  ([mutating/overview](https://developers.google.com/google-ads/api/docs/mutating/overview)).
  Docstring do SDK v25 (`MutateGoogleAdsRequest.partial_failure`): *"If false, all operations will be
  carried out in one transaction if and only if they are all valid. Default is false."* IDs
  temporários negativos (`customers/X/campaigns/-1`) ligam pai e filho no mesmo request. É por request
  e por `customer_id`: o rollback só cobre o que está no mesmo request.
- `partial_failure=true`: `partial_failure_error` é `google.rpc.Status` com exatamente um
  `GoogleAdsFailure` em `details`; a operação que falhou volta vazia; o índice está em
  `location.field_path_elements[0].index`
  ([partial-failures](https://developers.google.com/google-ads/api/docs/best-practices/partial-failures)).
  Nem toda operação suporta (`MutateError.OPERATION_DOES_NOT_SUPPORT_PARTIAL_FAILURE`, por exemplo
  CampaignConversionGoal e criação de ExperimentArm).
- Limites ([quotas](https://developers.google.com/google-ads/api/docs/best-practices/quotas), 14/10/2026): Mutate ≤ 10.000 operações
  por request (Billing/AccountBudget: 1); "20.000 para AdGroupCriterion" não existe; não há limite em bytes documentado (bibliotecas
  usam 64 MB; resposta maior dá `RESOURCE_EXHAUSTED`). Operações/dia: Explorer 2.880 em produção, Basic 15.000, Standard ilimitado.
- BatchJob ([overview](https://developers.google.com/google-ads/api/docs/batch-processing/overview), [best-practices](https://developers.google.com/google-ads/api/docs/batch-processing/best-practices)):
  sempre partial failure, exceto sub-lotes atômicos (≤1.000 ops) de operações interdependentes (asset group, listing group filter;
  o SDK ainda traz `CAMPAIGN_AND_CAMPAIGN_ASSET_TRANSACTION_FAILURE`); recomenda ≤1.000 ops por `AddBatchJobOperationsRequest`
  (teto 10.000); ≤1.000.000 ops/job; ≤100 jobs ativos/pendentes por conta; sem `validate_only`; cada operação conta na quota e
  "doesn't guarantee higher throughput".
- Concorrência: o erro exato é `google.ads.googleads.v25.errors.DatabaseErrorEnum.DatabaseError.CONCURRENT_MODIFICATION`,
  que pode vir de qualquer serviço de mutate. A doc diz *"Multiple requests were attempting to modify the same resource at once. Retry the request."*
  ([DatabaseError v25](https://developers.google.com/google-ads/api/reference/rpc/v25/DatabaseErrorEnum.DatabaseError)).
  No BatchJob, o Google recomenda agrupar as operações de um mesmo pai em sequência e não mutar o mesmo
  objeto em jobs concorrentes. Uma fila por `customer_id` evita colisão entre os workers do VOLC, mas não
  impede que a UI, scripts, regras automáticas ou outros usuários escrevam ao mesmo tempo. O
  VOLC já trata o erro como TRANSIENT e retenta (`volc_ads/gads/errors.py`). O risco que sobra é o
  reenvio cego, que pode sobrescrever uma edição feita na UI depois da leitura "antes" (Delta 1).

## 2. Data Manager API

- O pacote real é `google-ads-datamanager` 0.9.4 (Apache-2.0, selo `support-preview`, Python ≥3.10),
  com fonte em `googleapis/google-cloud-python/packages/google-ads-datamanager`. O repositório
  `googleads/data-manager-python` (commit 62592ff) é outra coisa: publica `google-ads-datamanager-util`
  0.4.0 (formatação, hash e criptografia) e os samples.
- RPCs (wheel com sha256 conferido): `IngestionService` = IngestEvents, IngestAudienceMembers, RemoveAudienceMembers,
  RemoveAllAudienceMembers, IngestUsers, RemoveUsers, IngestAdEvents, RetrieveRequestStatus; mais UserList, PartnerLink,
  MarketingDataInsights e licenças. Endpoint `datamanager.googleapis.com`, RPCs unárias (sem streaming).
- Todos os Ingest* e Remove* têm `validate_only`. O diagnóstico vem por `RetrieveRequestStatus(request_id)`: a doc manda esperar 30 min, usar
  backoff de até 60 min e parar em 24 h. Os estados são PROCESSING, SUCCESS, FAILURE e PARTIAL_SUCCESS. O diagnóstico não existe para requests com
  `validate_only` ([diagnostics](https://developers.google.com/data-manager/api/devguides/diagnostics)). O modelo de erro é fast-fail, não
  partial failure ([upgrade](https://developers.google.com/data-manager/api/devguides/events/google-ads/offline/upgrade)).
- Identificadores em `AdIdentifiers`: gclid, gbraid, wbraid, session_attributes, landing_page_device_info, dclid etc. Também há
  `transaction_id`, `user_data` (até 10 identificadores), `consent` (ad_user_data e ad_personalization), `currency`, `conversion_value`
  em unidade de moeda (não micros) e `destinations` (até 10).
- `operating_account` = conta dona da ação de conversão. Limites ([limits](https://developers.google.com/data-manager/api/devguides/limits)):
  2.000 eventos/request, 300 requests/min e 100.000/dia por projeto.
- Ajustes ([conversion-adjustments](https://developers.google.com/data-manager/api/devguides/events/google-ads/conversion-adjustments)):
  mesmo `transactionId` na mesma ação vira ajuste (valor substitui, contagem não muda); *"the Data Manager API doesn't support
  conversion retractions"*; store sales não ajustáveis; multi-fonte tem 14 dias de trial sem efeito no lance.
- Papéis: `UploadClickConversions` sobe clique offline; `ConversionAdjustmentUploadService` faz RESTATEMENT/RETRACTION/ENHANCEMENT;
  `OfflineUserDataJobService` só Customer Match e Store Sales (enum `OfflineUserDataJobType`), **não** conversão de clique;
  a Data Manager junta upload e restatement, sem retraction.
- Restrições de 2026 ([deprecations](https://developers.google.com/google-ads/api/docs/deprecations)): desde 15/06/2026, tokens sem
  upload offline entre 17/12/2025 e 15/06/2026 recebem `CUSTOMER_NOT_ALLOWLISTED_FOR_THIS_FEATURE` em UploadClickConversions; desde
  02/02/2026 session attributes/IP restritos a novos adotantes; desde 01/04/2026 Customer Match via OfflineUserDataJobService restrito
  a quem não usou entre 01/10/2025 e 31/03/2026. Migração indicada: Data Manager.
- Novo (A41): o token de desenvolvedor foi aposentado em 09/09/2026. O nível de acesso agora é o do projeto Cloud,
  e o header é ignorado. O Google avisa que uma versão major futura vai recusar o token
  ([developer-token](https://developers.google.com/google-ads/api/docs/api-policy/developer-token)).

## 3. RESTATEMENT e RETRACTION (Google Ads API, v25)

Fontes: [upload-adjustments](https://developers.google.com/google-ads/api/docs/conversions/upload-adjustments) e as docstrings do SDK.
- Tipos de ação elegíveis: SALESFORCE, UPLOAD_CLICKS e WEBPAGE.
- Identificação: `order_id` recomendado (obrigatório para WEBPAGE ou se a original tinha); `gclid_date_time_pair` é "less durable" e
  não pode vir junto (`GCLID_DATE_TIME_PAIR_AND_ORDER_ID_BOTH_SET`); GBRAID sim, WBRAID não.
- `adjusted_value` é valor absoluto ("from 100 to 70, an adjusted value of 70"). A moeda vem de `currency_code`; sem ela, vale a moeda da ação e depois a da conta.
- Janelas: >54 dias dá `CONVERSION_EXPIRED`; <24 h dá `TOO_RECENT_CONVERSION`; esperar 4–6 h após criar a ação; ≤2.000 ajustes por
  request; teto por conversão (`TOO_MANY_ADJUSTMENTS`).
- Ordem: segunda restatement exige `adjustment_date_time` mais recente (senão ignorada ou `MORE_RECENT_RESTATEMENT_FOUND`); retraction é
  terminal (`CONVERSION_ALREADY_RETRACTED`); `partial_failure` deve ser true.
- "RETRACTION imediata quando o antifraude marca a sessão" é falso: a conversão precisa ter pelo menos 24 h.

## 4. BiddingSeasonalityAdjustment

O recurso e o serviço são `BiddingSeasonalityAdjustmentService.MutateBiddingSeasonalityAdjustments` (tem
`validate_only` e `partial_failure`).
- Campos: `scope` (CUSTOMER, CAMPAIGN ou CHANNEL), `campaigns` (até 2.000), `advertising_channel_types` (só DISPLAY,
  SEARCH e SHOPPING; não pode vir junto com `campaigns`), `devices`, `conversion_rate_modifier` de 0,1 a 10,0 (1,0 não muda nada) e
  `start_date_time`/`end_date_time` com intervalo em (0, 14 dias]. O ajuste é para o futuro, e o proto diz que não pode ser usado em MCC.
  A Ajuda diz que dá para criar a partir do MCC. As duas fontes divergem.
- [Ajuda 10369906](https://support.google.com/google-ads/answer/10369906): mexe só na taxa de conversão (não no valor); "ideal for short
  events of 1–7 days", funciona mal >14 dias, não é para sazonalidade regular; Search/Shopping/Demand Gen/Display só com tCPA/tROAS,
  PMax e App com qualquer estratégia; campanhas "return to their pre-adjust performance after the event is finished" (cobre "volta
  imediata"; "sem choque" não é prometido).
- `BiddingDataExclusion` é a ferramenta para dados ruins do passado: é retroativa e tem os mesmos campos, sem o modifier.

## 5. Experimentos

Os métodos do `ExperimentService` (v25) são MutateExperiments, ScheduleExperiment (assíncrono, long-running op),
EndExperiment (síncrono), PromoteExperiment (assíncrono), GraduateExperiment (síncrono, com `campaign_budget_mappings`) e
ListExperimentAsyncErrors. O `ExperimentArmService` só tem MutateExperimentArms.
- Schedule, Promote, Graduate e End têm `validate_only`. `ExperimentArm.traffic_split` (não traffic_split_percent) é int 1–100 com soma
  100; `campaigns` ≤1; `suffix` vai no nome do tratamento.
- System-managed: SEARCH_CUSTOM, DISPLAY_CUSTOM, HOTEL_CUSTOM, YOUTUBE_CUSTOM, PMAX_REPLACEMENT_SHOPPING (não promovível; descartar 7
  primeiros dias). Não existe tipo Demand Gen.
- Promote copia as mudanças do tratamento para a campanha controle, que mantém o ID. A doc não diz "sem perda de histórico"; isso é inferência
  ([system-managed](https://developers.google.com/google-ads/api/docs/experiments/system-managed),
  [async-errors](https://developers.google.com/google-ads/api/docs/experiments/async-errors)).

## 6. Quality Score

- `ad_group_criterion.quality_info.{quality_score, creative_quality_score, post_click_quality_score, search_predicted_ctr}` = estado atual
  (score pode vir vazio); `metrics.historical_{quality_score, creative_quality_score, landing_page_quality_score, search_predicted_ctr}`
  segmentável por data em `keyword_view`; componentes BELOW_AVERAGE/AVERAGE/ABOVE_AVERAGE.
- A Ajuda diz que "Quality Score is not an input in the ad auction" e que ele é diagnóstico calculado sobre 90 dias de buscas exatas
  ([6167118](https://support.google.com/google-ads/answer/6167118)).
- "LP BELOW_AVERAGE ⇒ CWV/excesso de anúncios/template" não tem fonte. A [2404197](https://support.google.com/google-ads/answer/2404197) só fala em relevância e utilidade.
- O VOLC já coleta tudo isso em `volc_ads/coleta/familias/keyword.py`.

## 7. Assets

- `ad_group_ad_asset_view` cobre App, Demand Gen e RSA, mas não RDA. Tem 32 métricas (clicks, impressions, cost, conversions…) e os campos
  field_type, pinned_field, enabled (output only), policy_summary, source e performance_label.
- Release notes da v23 (28/01/2026): *"The performance label enum is no longer returned for Search and Display."*
  O campo ainda existe na v25, mas vem vazio para RSA (A42).
- `asset_group_asset` (PMax) tem 33 métricas e status/primary_status/policy, mas não tem `performance_label` no v25. O catálogo recusa o campo, e o
  resumo da página de PMax que sugere o contrário está desatualizado.
- `asset_group_top_combination_view` sem métricas; `campaign_asset`/`ad_group_asset` com 32.
- Risco de soma: as métricas de ativo contam cada instância servida. Somar ativos de um anúncio não dá o total do anúncio, e somar canais em `campaign_aggregate_asset_view` duplica Search (já anotado em `coleta/familias/asset.py`).
- Trocar copy de RSA = `AdService.MutateAds` (`AdOperation` só tem `update` + `update_mask`; lista substituída inteira,
  [mutate-ads](https://developers.google.com/google-ads/api/docs/ads/mutate-ads)); não via AdGroupAdOperation (`AdGroupAd.ad` é Immutable).
- Headline não tem status (`AdTextAsset` = text, pinned_field, asset_performance_label, policy_summary_info): pausa só o anúncio inteiro.

## 8. Placements: o que o VOLC pode ler e propor

| View (v25) | Cobre | Métricas | Grão |
|---|---|---|---|
| `group_placement_view` | Rede de Display e YouTube ("where ads showed"), automático + gerenciado | 36 (custo, cliques, conversões, active view, vídeo) | grupo de anúncios × domínio/canal/app |
| `detail_placement_view` | sobretudo Display; URL, vídeo, app | 38 | grupo × URL/vídeo |
| `managed_placement_view` | só placements alvo | 44 | grupo × critério |
| `performance_max_placement_view` | PMax (WEBSITE, MOBILE_APPLICATION, YOUTUBE_VIDEO) | **só impressions**; segmentos `ad_network_type`, `date` | campanha × placement |
| `detail_/group_content_suitability_placement_view` | adequação de conteúdo | **só impressions**; segmento `date`; campanha/grupo segmentam | campanha/grupo × placement |

Fontes: [placement-views](https://developers.google.com/google-ads/api/docs/reporting/placement-views) e as páginas
`/fields/v25/*` (`experimentos/campos_compativeis_v25.out.json`). Demand Gen não aparece citada em nenhuma doc de placement.
O caminho provável é group/detail, mas é preciso confirmar com um `search` real.

Exclusões ([criteria](https://developers.google.com/google-ads/api/docs/targeting/criteria)):
- Placement, vídeo/canal do YouTube e app podem ser negativos em campanha, grupo e conta.
- PlacementList só existe na conta: é `CustomerNegativeCriterion.placement_list` apontando para um shared set `NEGATIVE_PLACEMENTS`.
- A lista de critérios de campanha PMax ([pmax criteria](https://developers.google.com/google-ads/api/performance-max/create-campaign-criteria))
  não inclui PLACEMENT. Em PMax, a exclusão é no nível da conta (é preciso provar com validate_only).
- IP só pode ser excluído na campanha ou na conta. A [Ajuda 2456098](https://support.google.com/google-ads/answer/2456098) diz que a exclusão por campanha não existe em Vídeo, Hotel, App, PMax e Smart Display.

## 9. tCPA por grupo

[override-strategies](https://developers.google.com/google-ads/api/docs/campaigns/bidding/override-strategies):
- `ad_group.target_cpa_micros` sobrepõe a meta em TargetCpa ou em MaximizeConversions com target_cpa definido, tanto padrão quanto portfólio TargetCpa.
- `ad_group.target_roas` sobrepõe em TargetRoas ou MaximizeConversionValue com target_roas, mas só na estratégia padrão e em portfólio de Search.
  Em outros portfólios dá erro.
- Em Demand Gen com TargetCpc, `target_cpc_micros` sobrepõe no grupo.
- Fora desses casos o valor é ignorado em silêncio. Por isso convém ler `effective_target_cpa_micros/_source` (BiddingSource: CAMPAIGN_BIDDING_STRATEGY, AD_GROUP, AD_GROUP_CRITERION).
- Para remover o override, envia-se o campo vazio no update_mask.

## 10. Modificadores, IP e value rules

- Modificadores ([bid-modifiers](https://developers.google.com/google-ads/api/docs/targeting/bid-modifiers)): `AdGroupBidModifier` aceita
  DeviceInfo e hotel; `CampaignBidModifier` só InteractionType CALL; geo/horário/demografia via `bid_modifier` do critério. Sob Smart
  Bidding os manuais "won't be supported", exceto dispositivo −100%; no tCPA o ajuste de dispositivo muda a meta
  ([2732132](https://support.google.com/google-ads/answer/2732132)).
- IP: `IpBlockInfo.ip_address` aceita IP ou CIDR, IPv4 e IPv6 (docstring: `2001:db8::/48`); 500 por campanha e 500 por conta; o VOLC
  aceita só IPv4 /24–/32 (A46).
- Value rules ([conversion-value-rules](https://developers.google.com/google-ads/api/docs/conversions/conversion-value-rules)): condições
  geo, dispositivo, público, itinerário (allowlist) ou nenhuma, ≤2 dimensões por rule set; ADD (>0), MULTIPLY (0,5–10), SET (>0, restrito);
  rule set CUSTOMER ou CAMPAIGN (campanha prevalece). A doc não permite nem proíbe valores "não reais".

## 11. Repositórios externos (clones em scratch; nada executado)

- `googleads/google-ads-mcp` @9a78cbd (Apache-2.0, PyPI 0.0.5): é **somente leitura**, como confirmam o código (tools `readOnlyHint=True`, zero mutate) e a
  [doc oficial](https://developers.google.com/google-ads/api/docs/developer-toolkit/mcp-server). Tools: search, get_resource_metadata, list_accessible_customers.
- `google-marketing-solutions/agentic_dsta` @23a35f2 (Apache-2.0, "not officially supported"): FastAPI + ADK. Lê campanha, geo,
  orçamentos compartilhados e portfólios; escreve status, orçamento, geo (campanha/grupo), estratégia, orçamento compartilhado e
  portfólio por `mutate_*` real, sem validate_only, retry ou ledger; diagnóstico = só os dados lidos. Problemas: GAQL por f-string,
  update de geo remove tudo e recria, "aprovação" só no prompt, matriz canal×estratégia é "Example structure" sem Demand Gen.
  Aproveitar: só a ideia "sinal externo → regra"; o VOLC já cobre as ações com antes/conferir/reverso.
- IFTTA: org real google-marketing-solutions (`google/if-this-then-ad` dá 301); Apps Script fixo em `googleads.googleapis.com/v14` (aposentada).
- Tightlock @69925d7 (Apache-2.0, "experimental, unsupported"): roda em Docker com Airflow, Postgres e Drill. Fixa `google-ads==24.1.0`, que só cobre versões aposentadas, e usa OCI legado. O
  Megalista indica "GADM or Tightlock". "Substituto oficial" é exagero.
- Megalista: arquivado (README: após 31/12/2024; último commit 02/01/2025); `google-marketing-solutions/megalista` e `tightrope` dão 404.
- adloop (MIT, v0.30.0): MCP com escrita governada (ValidateOnlyClient fail-closed, two-phase apply, tetos): referência de padrão.
  claude-keitaro (MIT): skill, não MCP, com **cloaking** (rejeitado). advertising-hub (MIT): quase só docs, 3 scripts de leitura.

## 12. Gemini: preço e teto

Fontes: [pricing](https://ai.google.dev/gemini-api/docs/pricing) (atualizada em 14/10/2026) e [models](https://ai.google.dev/gemini-api/docs/models).
- `gemini-3.8-flash` (estável, ficha de set/2026): 1.048.576 tokens de entrada, 65.536 de saída; thinking low–high ("minimal" dá erro).
  Pago Standard **US$ 0,75/1M entrada, US$ 3,75/1M saída**, sobe para 1,50/7,50 em 01/01/2027; batch 0,375/1,875; cache 0,075.
- **`gemini-3.5-flash` não aparece** no catálogo nem nos preços (só `gemini-3.5-flash-lite`, 0,30/2,50). O backend usa `gemini-3.8-flash`.
- Teto do integrador: custo ≈ 0,75·E + 3,75·S (US$ por milhão de tokens). 4 gerações de 100k entrada + 20k saída ≈ US$ 0,60; estourar
  US$ 2 em 4 chamadas exigiria ≈ 300k entrada + 73k saída cada. Thinking provavelmente é cobrado como saída (não confirmado): use os
  tokens de saída do `usage_metadata`.

## 13. v26 / SDK 34

A v26 saiu em 14/10/2026 ([sunset-dates](https://developers.google.com/google-ads/api/docs/sunset-dates)).
[client-libs](https://developers.google.com/google-ads/api/docs/client-libs): Python v26 exige ≥34.0.0. PyPI ainda em **33.0.0**
(23/09/2026); GitHub tem o commit "Release v26" (9d34d05, 20:04Z de 14/10) sem tag/release. v25 sai do ar em agosto/2027: não há
motivo para migrar agora.

## Deltas acionáveis para o integrador

Todas as GAQLs abaixo passaram no catálogo do repo
(`experimentos/validar_gaql_propostas.out.txt`, 15/15). A compatibilidade de métricas foi conferida nas páginas `/fields/v25`.

1. **`volc_ads/gestao/lote.py:enviar`: não retentar às cegas `CONCURRENT_MODIFICATION` em escrita real.**
   - Hoje o `client.executar` reenvia o mesmo request.
   - Mudança: na escrita real (`validate_only=False`), quando a falha for `CONCURRENT_MODIFICATION`, reexecutar `consultas_antes` e `conferir` de cada ação antes de reenviar, e recusar se o "antes" mudou.
   - Por quê: a UI e outros atores escrevem na mesma conta, e uma fila própria não evita isso (pergunta 1).
2. **`volc_ads/gestao/acoes.py:AlterarAlvoDeLance`: adicionar nível `grupo`.**
   - Mudança: escrever `AdGroup.target_cpa_micros` (ou `target_roas`) com update_mask; "antes" = GAQL `tcpa_efetivo_por_grupo`
     (`ad_group.target_cpa_micros, effective_target_cpa_micros, effective_target_cpa_source, effective_target_roas(_source)` +
     `campaign.bidding_strategy_type, campaign.bidding_strategy`); recusar quando o override é ignorado (tROAS em portfólio não-Search,
     MaxConv sem target_cpa); reverso = valor anterior ou campo vazio.
   - Por quê: é o pedido do operador (A34), e a API documenta o override.
3. **`volc_ads/gestao/acoes.py:ExcluirPlacements` e `ExcluirIps`: guardas por canal.**
   - Mudança: em `conferir`, recusar `escopo="campanha"` quando o canal lido for PERFORMANCE_MAX e indicar conta ou lista
     `NEGATIVE_PLACEMENTS` via `placement_list`; em IP, recusar campanha em PERFORMANCE_MAX/VIDEO/APP/HOTEL e checar 500 por conta.
   - Por quê: a lista de critérios de campanha PMax não tem PLACEMENT e a Ajuda de IP exclui esses canais. Hoje o erro só aparece no validate_only, e como um erro genérico.
4. **`volc_ads/coleta/familias/placement.py`: anotar o canal e cobrir a adequação de conteúdo.**
   - Mudança: incluir `campaign.advertising_channel_type` no SELECT das três views; acrescentar `detail_content_suitability_placement_view`
     só com `metrics.impressions` (GAQL `placements_adequacao_conteudo`), `placement_view="suitability"`.
   - Por quê: o operador pediu placements por canal (Display, DG, PMax, YouTube). PMax e suitability só têm impressões, e o leitor não pode comparar custo entre views.
5. **`volc_ads/coleta/familias/asset.py:normalizar`: o rótulo de Search vira ausente.**
   - Mudança: mapear `UNSPECIFIED`/`UNKNOWN` de `performance_label` para `None` e documentar que, desde a v23, Search/Display não recebem
     rótulo; regras de copy de RSA usam métricas por ativo (`rsa_ativos_politica_metricas`) e `policy_summary`; ação futura de copy =
     `AdService.MutateAds` (lista inteira) com validate_only, nunca "pausar headline".
   - Por quê: A28, A29 e A42.
6. **`backend/app/trafego/data_manager.py`: alinhar o envelope ao contrato real (sem enviar).**
   - Mudança: validar ≤2.000 eventos e ≤10 destinos por request; `conversion_value` em moeda; `operating_account` = dona da ação;
     ajuste só como "mesmo `transaction_id` + valor absoluto"; recusa explícita de "retratar" (não existe na Data Manager; na Google Ads
     API exige ≥24 h e ≤54 dias e é terminal); recibo prevê `request_id` e `RetrieveRequestStatus` após 30 min (indisponível em validate_only).
   - Por quê: perguntas 2 e 3. Evita prometer antifraude por retraction e lote acima do limite.

Outras leituras validadas no catálogo (texto em `experimentos/validar_gaql_propostas.py`): `exclusoes_conta` (inclui `placement_list.shared_set`,
`ip_block.ip_address`), `listas_negativas_placement`, `sazonalidade_e_exclusoes`, `experimentos`, `bracos_de_experimento`, `regras_de_valor`, `pmax_ativos_status_politica`.
