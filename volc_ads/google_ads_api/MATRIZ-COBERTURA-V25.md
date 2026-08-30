# Matriz de cobertura — Google Ads API v25 × VOLC O.S.

Levantada em 27/08/2026, sobre o canal **SEARCH**. Diz o que a API oferece, o
que o engine escreve, o que o cockpit deixa o operador decidir e o que tem
prova automatizada.

**Versão pinada:** `v25` — `volc_ads/gads/client.py:25` (`VERSAO_API = "v25"`).
**Biblioteca instalada:** `google-ads` 31.3.0 (carrega v21…v25).

## ⚠️ De onde vieram os fatos desta matriz

A coluna "API v25" foi levantada nos **stubs proto gerados pelo Google**, que
vêm dentro do pacote `google-ads` instalado
(`backend/.venv/lib/python3.14/site-packages/google/ads/googleads/v25/`). São
os mesmos arquivos-fonte que alimentam a referência pública, com as docstrings
idênticas às da página de cada recurso.

Não foi possível ler a doc renderizada: `developers.google.com/google-ads/api/`
é uma SPA, e o fetch devolve só o menu de navegação; os caminhos REST de v25
respondem 404. Isso importa: o proto descreve fielmente o **schema** (campos,
oneofs, enums), mas **não** carrega a prosa dos guias — regras de rate limit,
fluxo de aprovação de política e cronograma de aposentadoria de versão não
estão aqui. Onde a evidência não bastou, a linha diz `não confirmado` em vez de
preencher por memória.

## Prova contra a conta real — 27/08/2026

O contrato tipado foi submetido ao `validate_only` na conta `8017851692`
(MCC `6016739364`), pelo caminho normal (`search.validar`). Nada foi criado —
`validate_only` valida e descarta, e não passa pela trava de escrita porque é
leitura para todos os efeitos.

| | |
|---|---|
| operações no payload | **18** |
| achados da validação local | **sem achados** |
| veredito da API | **aceito — nenhuma falha** |
| trava de escrita, antes e depois | `escrita_permitida: False` |

O payload provado carregava, de propósito, tudo o que esta entrega introduziu:

```
saque anual fgts       EXACT    AD_GROUP   positiva
regras do saque anual  PHRASE   AD_GROUP   positiva
simulador              PHRASE   CAMPAIGN   negativa   (origem SEARCH_TERM, medida)
como fazer             EXACT    AD_GROUP   negativa   (origem MANUAL)
```

Ou seja: o próprio Google confirmou que duas positivas com match types
DIFERENTES na mesma campanha, uma negativa de campanha em `PHRASE` e uma
negativa de ad group em `EXACT` formam um payload válido em v25. É a prova que
nenhum teste local dá — os testes provam o que o payload contém; esta prova
mostra que a API o aceita.

### Segunda rodada — o acento é significativo na negativa

Uma revisão adversarial levantou a dúvida: `"grátis"` e `"gratis"` são o MESMO
critério negativo para o Google, ou dois? A resposta muda o comportamento certo
da deduplicação — se forem o mesmo, mandar os dois é redundância; se forem
diferentes, deduplicá-los apaga um bloqueio que o operador declarou.

Submetido um segundo payload com **as duas grafias como negativas de campanha,
lado a lado**:

| | |
|---|---|
| operações no payload | **20** (as 18 acima + as duas grafias) |
| veredito da API | **aceito — nenhuma falha** |

`CampaignCriterion` de keyword é identificado pelo par (texto, match type). Se a
API considerasse as duas grafias o mesmo critério, a segunda operação teria sido
recusada como duplicata e o mutate atômico inteiro cairia. Ela **não** foi.

**Fato medido: acento é significativo em keyword negativa na v25.** É por isso
que `criterio.chave` preserva acento, enquanto `conteudo.chave` — que serve à
deduplicação de keyword POSITIVA entre ad groups, onde o Google casa variantes
próximas — continua removendo.

## Legenda de estado

| estado | significado |
|---|---|
| `implementado` | o engine escreve, e há teste que prova |
| `parcial` | existe, mas com limite declarado na coluna "lacuna" |
| `a fazer` | a API oferece, o VOLC não usa, e não há impedimento conhecido |
| `barrado` | não vai ser feito assim — a razão está na lacuna |

---

## Keywords e negativas

| capacidade | API v25 | VOLC (engine) | cockpit | teste | estado | lacuna → próxima ação |
|---|---|---|---|---|---|---|
| keyword positiva | `AdGroupCriterion.keyword` (`KeywordInfo`) | `search.py` — match type POR keyword | seletor por linha | `testes_criterio.py` | **implementado** | — |
| match type | `KeywordMatchTypeEnum`: `EXACT=2` `PHRASE=3` `BROAD=4` | preservado individualmente | "Exata/Frase/Ampla" | sim | **implementado** | — |
| negativa de campanha | `CampaignCriterion.negative` | `search.py`, match type próprio | nível "Campanha inteira" | sim | **implementado** | — |
| negativa de grupo | `AdGroupCriterion.negative` | `search.py`, escopo por grupo | nível "Só um grupo" | sim | **parcial** | a doutrina P7 (`conjunto_unico=True`) colapsa os N grupos em UM ad group, então hoje "só um grupo" e "todos os grupos" produzem o mesmo payload. O engine já sabe fazer o certo — falta P7 ser revista, não código. |
| negativa de conta | `CustomerNegativeCriterion` — **não aceita keyword solta**; só via `negative_keyword_list` | não usa | não oferece | — | **barrado** | atravessa TODAS as campanhas da conta, inclusive as que este engine não criou. Não pode nascer de um brief de campanha nova. |
| lista compartilhada de negativas | `SharedSet` + `SharedCriterion` + `CampaignSharedSet` | não usa | não oferece | — | **a fazer** | é o caminho certo para negativa de marca reaproveitada entre campanhas. Depende do cofre de ativos. |
| deduplicação | sem enum dedicado em `AdGroupCriterionError`/`CriterionError` para keyword real (o `DUPLICATE_KEYWORD` existente é do **Keyword Planner**) | dedup local por identidade `(texto, match, nível, grupo)` | avisa na revisão | sim | **implementado** | a API não dá o erro nomeado; a defesa é local e roda antes do envio. |
| conflito positiva × negativa | não existe na API | `criterio.conflitos()` | bloco "Revisão" | sim | **implementado** | detecta só a ANULAÇÃO provável. "Estreita o tráfego" ficou de fora: exigiria enumerar o espaço de consultas de uma keyword PHRASE/BROAD, que é aberto. |

## Anúncio

| capacidade | API v25 | VOLC | cockpit | teste | estado | lacuna → próxima ação |
|---|---|---|---|---|---|---|
| RSA | `ResponsiveSearchAdInfo` — 3–15 headlines (30 car.), 2–4 descriptions (90 car.) | `search.py` monta um RSA por ad group | cartão da copy | `testes_search.py` | **parcial** | os N ad groups recebem o MESMO RSA: o brief carrega uma `Copy` só. Relevância keyword→anúncio cai quando os grupos se multiplicam. |
| pinning | `AdTextAsset.pinned_field` → `ServedAssetFieldTypeEnum` (`HEADLINE_1..3`, `DESCRIPTION_1..2`) | não usa | não oferece | — | **a fazer** | necessário quando um headline tiver de aparecer sempre (marca, aviso legal). |
| path1 / path2 | `ResponsiveSearchAdInfo.path1/path2` — path2 exige path1 | não usa | não oferece | — | **a fazer** | ganho de CTR barato; o par tem ordem obrigatória. |
| ad customizers | `CustomizerAttribute`, `CampaignCustomizer`, `AdGroupCustomizer`, `AdGroupCriterionCustomizer` | não usa | não oferece | — | **a fazer** | depois de pinning e path. |
| sitelink / callout / snippet | `SitelinkAsset`, `CalloutAsset`, `StructuredSnippetAsset` + `CampaignAsset` | `search.py` cria e vincula à CAMPANHA | cartão da copy | `testes_search.py` | **implementado** | header do snippet só é validado localmente em pt-BR; nos demais idiomas quem adjudica é o `validate_only`. |
| image asset em Search | `ImageAsset` + `AssetLink` | só em Display | não oferece | — | **a fazer** | o motor de criativo já existe; falta o vínculo no canal Search. |

## Segmentação e configuração

| capacidade | API v25 | VOLC | cockpit | teste | estado | lacuna → próxima ação |
|---|---|---|---|---|---|---|
| geo | `LocationInfo.geo_target_constant`; `Campaign.GeoTargetTypeSetting` | `comum.op_geo` | herda do país | `testes_search.py` | **parcial** | `geo_target_type_setting` (presença × interesse) não é declarado — fica no default da API. |
| idioma | `LanguageInfo.language_constant` (nível campanha) | `comum.op_idioma` | herda | sim | **implementado** | — |
| agenda | `AdScheduleInfo` — `day_of_week`, `start_hour` 0–23, `end_hour` 0–24; **máx. 6 por dia**; obrigatórios no CREATE | **não existe no contrato** | não oferece | — | **a fazer** | não há como declarar dayparting hoje. Contrato inteiro a definir. |
| rede de parceiros | `NetworkSettings.target_search_network` (exige `target_google_search=true`) | **ligado** em `comum.py:167` | **não mostra** | — | **parcial** | está ON sem o operador escolher nem ver. É efeito invisível: deve virar decisão explícita na Mesa de Lance. |
| orçamento | `CampaignBudget`, `explicitly_shared` | `comum.op_budget` | campo na Mesa | sim | **implementado** | orçamento é sempre exclusivo da campanha. |
| estratégia de lance | 19 estratégias em `common/types/bidding.py` | `MANUAL_CPC` e `MAXIMIZE_CONVERSIONS` | Mesa de Lance | `testes_search.py` | **parcial** | tCPA/tROAS não oferecidos. A graduação em 30 conversões é REGISTRADA, não executada. |
| ação de conversão | `Campaign.SelectiveOptimization` é **de campanha de APP** (`APP_CAMPAIGN`/`APP_CAMPAIGN_FOR_ENGAGEMENT`) | não escreve | exibe, e diz que não aplica | — | **barrado** | ⚠️ **Premissa refutada.** `meta_conversao_id` estava documentado como destinado a `campaign.selective_optimization`; a docstring do proto v25 restringe esse campo a campanhas de app. Para Search o caminho é `CampaignConversionGoal` / metas da conta — **redesenhar antes de implementar**. |
| tracking e ValueTrack | `Campaign.tracking_url_template`, `final_url_suffix` | `marcacao.py` — a marcação inteira vai no sufixo | — | `testes_search.py` | **implementado** | `ValueTrack` não é tipo do proto: é sintaxe dentro da string da URL. |

## Prova, erro e leitura

| capacidade | API v25 | VOLC | cockpit | teste | estado | lacuna → próxima ação |
|---|---|---|---|---|---|---|
| `validate_only` | `MutateGoogleAdsRequest.validate_only` (bool) | `gads/client.py:166` — não passa pela trava, é leitura | botão "provar" | sim | **implementado** | — |
| `partial_failure` | `MutateGoogleAdsRequest.partial_failure` + `partial_failure_error` | **não usa, de propósito** | — | `testes_search.py` | **barrado** | o mutate de nascimento é ATÔMICO: campanha meio criada é pior que campanha nenhuma. O tribunal lexical (F6), que muta em lote, é que precisa de `partial_failure` — outro caminho, outro código. |
| findings de política | `AdGroupAd.policy_summary` (`AdGroupAdPolicySummary`), `PolicyTopicEntry` | leitura pós-lançamento | `VereditoDePolitica` | — | **parcial** | lê depois de nascer; não há pré-checagem de política via API (a local é `policy/spec.py`). |
| termos de busca | `search_term_view` (não cobre Performance Max) | não no engine de criação | — | — | **a fazer** | é o insumo do tribunal lexical → propostas `NEGATIVAR_TERMO`/`PROMOVER_TERMO`. Ver `docs/SPEC-ARBITRAGEM.md` §5.1. |
| insight de termos | `CampaignSearchTermInsight`, `CustomerSearchTermInsight` — existem em v25 | não usa | — | — | **a fazer** | agrupa termos por categoria; complementa o `search_term_view`. |
| recomendações | `RecommendationService`, 55 tipos em `RecommendationTypeEnum` | não usa | — | — | **a fazer** | fonte de propostas auditáveis, nunca de aplicação automática. |
| erro de duplicidade | **não confirmado** — sem enum dedicado no escopo real | dedup local | avisa | sim | **implementado** (local) | a hipótese mais consistente com o proto é `MutateError.RESOURCE_ALREADY_EXISTS`, mas nenhuma doc lida confirma. |
| erro de match type inválido | **não confirmado** — provável `RequestError.INVALID_ENUM_VALUE` | recusado na construção do `Criterio` | select fechado | sim | **implementado** (local) | valor inválido não sai da tela nem do dataclass. |
| recibo e reconciliação | não existe na API | `subir.py` — `Selo` com `sha256` do payload | diálogo de lançamento | `testes_criterio.py` | **implementado** | trocar match type ou nível da negativa muda a impressão e invalida o selo anterior. |
| exportação Google Ads Editor | **não existe endpoint.** O Editor aparece só como identidade de quem muda: `ChangeClientTypeEnum.GOOGLE_ADS_EDITOR=7` | não usa | — | — | **barrado** | qualquer CSV de Editor seria formato de arquivo do cliente desktop, não da API — e não seria autoridade sobre a conta. |

---

## Prioridade sugerida

1. **Rede de parceiros virar escolha visível** — está ligada e ninguém vê. É a
   única linha `parcial` que muda entrega de tráfego sem o operador saber.
2. **Redesenhar o destino de `meta_conversao_id`** — a premissa registrada no
   contrato está errada para Search. Enquanto não for redesenhado, a tela
   continua dizendo que o campo não é aplicado, que é o comportamento honesto.
3. **Agenda de anúncios** — contrato inexistente; é a lacuna mais larga.
4. **`search_term_view` → propostas** — destrava o tribunal lexical do F6 e é o
   que dá EVIDÊNCIA MEDIDA às negativas, hoje quase todas hipótese.
5. **Pinning e path1/path2** — ganho barato de CTR, sem risco de gasto.
6. **Copy por sub-intenção** — só passa a valer quando P7 for revista.
