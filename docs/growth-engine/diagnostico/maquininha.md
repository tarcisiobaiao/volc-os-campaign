# Maquininha de Cartão — `24155134757`

Leitura direta da API v25, somente `SELECT`, em **26/08/2026 17:41 BRT**
(`2026-08-26T20:41:57Z`). Conta `8017851692`, `login_customer_id=6016739364`.
Dados crus: [`evidencia.json`](evidencia.json).

> **Cuidado com o homônimo.** A conta tem **duas** campanhas Maquininha. A viva é
> a `24155134757` (`BR - 20260819_131546 / …`). A `24155028398`
> (`BR - 20260819_123824 / …`) está **REMOVED** desde 19/08 13:02 e não aparece
> neste dossiê exceto quando citada. Elas compartilham os `criterion_id` das
> keywords — juntar dados por `criterion_id` sem o `ad_group` mistura as duas.

---

## OBSERVAÇÃO

### Conta

| campo | valor |
|---|---|
| `customer.id` / `descriptive_name` | `8017851692` / Crédito Up |
| `customer.currency_code` | `BRL` |
| `customer.time_zone` | `America/Sao_Paulo` |
| `customer.status` | `ENABLED` |
| `customer.manager` / `test_account` | `false` / `false` |
| `customer.pay_per_conversion_eligibility_failure_reasons` | `[OTHER, NOT_ENOUGH_CONVERSIONS]` |
| `billing_setup.status` | `APPROVED`, desde `2026-08-04 09:27:55` |

### Campanha

| campo | valor |
|---|---|
| `campaign.status` | `ENABLED` |
| **`campaign.primary_status`** | **`ELIGIBLE`** |
| **`campaign.primary_status_reasons`** | **não devolvido** (nenhuma razão) |
| `campaign.serving_status` | `SERVING` |
| `campaign.advertising_channel_type` | `SEARCH` |
| `campaign.bidding_strategy_type` | `MANUAL_CPC` |
| `campaign.manual_cpc.enhanced_cpc_enabled` | `false` |
| `campaign.start_date_time` | `2026-08-19 13:15:49` |
| `campaign.end_date_time` | **não devolvido** (sem término) |
| `campaign.network_settings` | `target_google_search: true`, `target_search_network: true`, `target_content_network: false`, `target_partner_search_network: false` |
| `campaign.payment_mode` | `CLICKS` |
| `campaign.bidding_strategy_system_status` | `UNAVAILABLE` |
| `campaign.optimization_score` | **não devolvido** |

`bidding_strategy_system_status: UNAVAILABLE` é o esperado em `MANUAL_CPC` — esse
campo descreve estratégia de portfólio, e não há uma aqui. Não é defeito.

### Orçamento — `campaign_budget/15800018633`

| campo | valor |
|---|---|
| `amount_micros` | `10000000` → **R$ 10,00/dia** |
| `delivery_method` | `STANDARD` |
| `period` / `status` | `DAILY` / `ENABLED` |
| `explicitly_shared` | `false` |
| `has_recommended_budget` | `false` |
| `recommended_budget_amount_micros` | **não devolvido** |

### Grupo de anúncios — `199084728163` "AdGroup_20260819_131546"

| campo | valor |
|---|---|
| `ad_group.status` | `ENABLED` |
| **`ad_group.primary_status`** | **`ELIGIBLE`** (sem razões) |
| `ad_group.type` | `SEARCH_STANDARD` |
| **`ad_group.cpc_bid_micros`** | **`120000` → R$ 0,12** |

### Anúncio — `821459034661`

| campo | valor |
|---|---|
| `ad_group_ad.status` | `ENABLED` |
| **`ad_group_ad.primary_status`** | **`ELIGIBLE`** (sem razões) |
| **`policy_summary.approval_status`** | **`APPROVED`** |
| **`policy_summary.review_status`** | **`REVIEWED`** |
| **`policy_summary.policy_topic_entries`** | **não devolvido** (vazio) |
| `ad_group_ad.ad_strength` | **`POOR`** |
| `ad_group_ad.action_items` | `"Try including more keywords in your headlines."`, `"Try including more keywords in your descriptions."` |
| títulos / descrições | 15 / 4 |
| `ad.final_urls` | `https://creditoup.com.br/r/maquininha-de-cartao-menor-taxa/` |

### Keywords — 10, todas `PHRASE`

Uniformes em: `status: ENABLED` (10/10), `approval_status: APPROVED` (10/10),
`system_serving_status: **ELIGIBLE**` (10/10 — nenhuma `RARELY_SERVED`),
`negative: false` (10/10), `disapproval_reasons`: não devolvido,
`cpc_bid_micros` próprio: **não devolvido** (herdam do grupo),
`effective_cpc_bid_micros: 120000`, `effective_cpc_bid_source: **AD_GROUP**`,
`quality_info`: **não devolvido** (10/10 — sem Índice de Qualidade atribuído).

**`primary_status_reasons` = `[AD_GROUP_CRITERION_BELOW_FIRST_PAGE_BID]` em 10 de
10.** (`primary_status` veio literalmente `UNKNOWN`: o enum
`AdGroupCriterionPrimaryStatus` da v25 não tem um valor para "limitada", então o
estado é legível apenas pela razão.)

`position_estimates` **existe e é devolvido na v25** — 10 de 10 keywords vivas:

| keyword | 1ª página | topo | × o lance de R$ 0,12 | impressões (30d) |
|---|---|---|---|---|
| maquininha de cartão | **R$ 15,13** | R$ 20,00 | **126×** | **1** |
| maquininha ton | R$ 14,53 | R$ 16,18 | 121× | 0 |
| maquininha moderninha | R$ 10,75 | R$ 10,75 | 90× | 0 |
| maquininha stone | R$ 3,20 | R$ 3,33 | 27× | 0 |
| maquininha pagseguro | R$ 2,85 | R$ 2,85 | 24× | 0 |
| maquininha mercado pago | R$ 1,85 | R$ 1,85 | 15× | 0 |
| moderninha pro 2 | R$ 1,67 | R$ 1,67 | 14× | 0 |
| mercado pago point mini d150 | R$ 1,56 | R$ 1,56 | 13× | 0 |
| maquininha de cartão no celular pessoa física | R$ 0,92 | R$ 1,03 | 8× | 0 |
| qual o melhor aplicativo para passar cartão | R$ 0,92 | R$ 1,03 | 8× | 0 |

⚠️ **A linha de cima carregava `0` e o valor medido é `1`.** A auditoria
adversarial de 26/08/2026 pegou a contradição dentro deste próprio arquivo: a
seção sobre não remover keyword (mais abaixo) se apoia justamente nessa
impressão, e a tabela a zerava. Uma tabela que zera a única entrega da campanha
sustenta exatamente a conclusão oposta à do parágrafo que a cita.

E a impressão ser da keyword **mais cara** (R$ 15,13 de primeira página, 126× o
lance) é o dado mais informativo da tabela: mostra que a entrega residual
acontece onde o leilão é mais disputado, e não onde ele é mais barato — o que
descarta a leitura de que o lance alcançaria "as baratas primeiro".

min R$ 0,92 · p25 R$ 1,40 · **mediana R$ 2,35** · p75 R$ 11,70 · max R$ 15,13.
**Nenhuma das 10 é alcançada por R$ 0,12.**

### Segmentação

`LOCATION 2076` = **Brazil** (`country_code: BR`, `target_type: Country`),
`ENABLED`, `negative: false`. `LANGUAGE 1014` = **pt**, `ENABLED`,
`negative: false`. `DEVICE` 30000 Desktop / 30001 HighEndMobile / 30002 Tablet —
todos `ENABLED`, `negative: false`, `bid_modifier` **não devolvido**.
**Nenhum critério `AD_SCHEDULE`.** **Nenhuma negativa de campanha.**
`campaign_shared_set` devolveu **0 linhas** — não há lista de negativas
compartilhada.

### Métricas — janela `LAST_30_DAYS` = 27/07/2026 → 25/08/2026

| métrica | valor |
|---|---|
| `metrics.impressions` | **1** |
| `metrics.clicks` | 0 |
| `metrics.cost_micros` | 0 → **R$ 0,00** |
| `metrics.ctr` | 0.0 |
| `metrics.average_cpc` | **não devolvido** (sem clique) |
| `metrics.conversions` / `all_conversions` | 0.0 / 0.0 |
| `metrics.search_impression_share` | **NÃO DEVOLVIDO** |
| `metrics.search_budget_lost_impression_share` | **NÃO DEVOLVIDO** |
| `metrics.search_rank_lost_impression_share` | **NÃO DEVOLVIDO** |
| `metrics.search_top_impression_share` | **NÃO DEVOLVIDO** |

Janela explícita `2026-08-19 → 2026-08-26` (vida inteira): idêntico — 1 impressão,
0 cliques, R$ 0,00, e as parcelas de impressão **igualmente não devolvidas**.

Diário: **uma única linha**, `2026-08-19`, com 1 impressão. De 20/08 a 25/08 a API
não devolveu linha alguma. Em `TODAY` (26/08): **0 impressões**.

Termos de busca na janela: **um só** — `"tom máquina"`, 1 impressão, 0 cliques.

### Conversões da conta

5 `conversion_action`: uma `HIDDEN` (`GOOGLE_ANALYTICS_4_PURCHASE`) e quatro
`ENABLED`. Só `7718441216` "adViewInterstitial" é `primary_for_goal: true` e
`include_in_conversions_metric: true`. **Todas com `all_conversions = 0.0`** na
janela.

### `change_event` — janela `LAST_14_DAYS` (12/08 → 26/08)

Toda a história desta campanha cabe em três linhas, todas de 19/08/2026, autor
`tarcisio@agenciavolc.com.br`:

```
13:15:50.399  CAMPAIGN_BUDGET  CREATE  GOOGLE_ADS_API         R$ 10,00/dia, STANDARD
13:15:50.399  CAMPAIGN         CREATE  GOOGLE_ADS_API         status PAUSED, MANUAL_CPC
13:15:50.399  AD_GROUP         CREATE  GOOGLE_ADS_API         cpc_bid_micros = 120000  (R$ 0,12)
13:37:58.714  CAMPAIGN         UPDATE  GOOGLE_ADS_WEB_CLIENT  status PAUSED → ENABLED
```

**Nenhum evento após 19/08 13:37:58.** O lance nunca foi tocado desde o
nascimento. (Os demais 38 eventos do lote são `CREATE` de keywords, assets e do
anúncio, no mesmo segundo.)

---

## DIAGNÓSTICO

**A campanha está plenamente elegível e não entra no leilão porque o lance não
alcança o preço de entrada de nenhuma das suas keywords.**

1. **Elegibilidade é fato, não suposição.** `primary_status = ELIGIBLE` **sem
   razões** nos três níveis — campanha, grupo e anúncio — e `APPROVED/REVIEWED` no
   anúncio com `policy_topic_entries` vazio. Não há bloqueio de status nem de
   política em lugar nenhum da cadeia.

2. **O Google nomeia a causa, keyword por keyword.**
   `AD_GROUP_CRITERION_BELOW_FIRST_PAGE_BID` em **10 de 10**. Esse campo não é
   nossa interpretação do valor do lance: é o sistema declarando que o lance está
   abaixo do necessário para a primeira página.

3. **E quantifica o quanto.** `position_estimates` devolveu as 10 estimativas, e
   **R$ 0,12 não cobre nenhuma**. O termo de cabeça pede 126× o lance. Vale
   registrar que `first_page_cpc_micros` já é uma estimativa *condicionada à
   qualidade atual do anúncio* — por isso ela substitui, e não apenas
   complementa, a discussão sobre Índice de Qualidade.

4. **Orçamento está descartado por construção.** R$ 10,00/dia ativos, `STANDARD`,
   e **R$ 0,00 gastos em sete dias**. Não se perde leilão por verba quando a verba
   inteira sobra.

5. **Smart Bidding não está em jogo.** `MANUAL_CPC`: a ausência de conversões na
   conta (`all_conversions = 0.0` em todas as ações, e
   `pay_per_conversion_eligibility_failure_reasons` incluindo
   `NOT_ENOUGH_CONVERSIONS`) é real, mas **não pode travar** uma estratégia
   manual. Não é causa aqui.

6. **Baixo volume está descartado.** `system_serving_status: ELIGIBLE` em 10/10.
   Nenhuma `RARELY_SERVED`. E "maquininha de cartão" a R$ 15,13 de CPC de primeira
   página é o oposto de um termo sem demanda — é um termo caro porque é disputado.

### O que a amostra NÃO sustenta

Com **1 impressão e 0 cliques**, esta campanha não sustenta nenhuma conclusão
sobre CTR, qualidade de anúncio ou landing page. Especificamente:

- o `ad_strength: POOR` **não pode ser apontado como causa da não entrega** — um
  anúncio POOR veicula; ele apenas encarece o leilão;
- `quality_info` veio **não devolvido** nas 10 keywords: o Google ainda não
  atribuiu Índice de Qualidade, por falta de entrega. Não é "QS zero";
- as parcelas de impressão **não foram devolvidas**. Isso não é 0% de perda por
  classificação — é ausência de medição por amostra insuficiente. A magnitude da
  perda desta campanha permanece **não medida**; o diagnóstico se apoia na
  declaração por keyword e nas estimativas, não numa parcela de impressão.

---

## HIPÓTESE

| # | hipótese | por que é plausível | teste que a resolveria |
|---|---|---|---|
| H1 | Subir o lance para ~R$ 2,50 produz entrega mensurável em 48–72 h | é o mínimo que cruza a mediana das estimativas (cobertura 0% → 50%) | aplicar a mutação e reler `impressions` e `search_rank_lost_impression_share` em 72 h. Entrega ≥ 100 impressões confirma; entrega ainda nula **refuta** e reabre o caso |
| H2 | Mesmo entregando, o orçamento de R$ 10,00/dia é incompatível com os três termos de cabeça | a R$ 15,13 de CPC de primeira página, R$ 10,00 compram **0,66 clique/dia** | separar os 3 termos caros em grupo próprio e medir CPC real; ou subir a verba e medir esgotamento |
| H3 | `ad_strength: POOR` está inflando o preço de entrada | os `action_items` do Google pedem variedade de keywords no texto, e o preço de 1ª página é condicionado à qualidade | reescrever a copy, reler `ad_strength` e comparar `first_page_cpc_micros` antes × depois, **com o lance constante** |
| H4 | 10 keywords `PHRASE` é cobertura estreita demais para 7 dias sem impressão | a FGTS, com 81 keywords e o mesmo lance, obteve 5× mais impressões | ampliar o conjunto e medir impressões por keyword |

H1 é a única que precisa ser resolvida antes das outras: enquanto o lance não
cruzar o piso, nenhuma das demais produz dado interpretável.

---

## RECOMENDAÇÃO

Reversíveis, em ordem, e **nada aplicado**:

1. **Subir `ad_group.cpc_bid_micros` de `120000` para `2500000` (R$ 2,50).**
   Efeito esperado: cobertura das estimativas de 1ª página vai de **0/10 para
   5/10**; teto teórico de ~4 cliques/dia com a verba atual. Rollback: voltar a
   `120000` — um campo, um valor.
   *Por que R$ 2,50 e não R$ 15,50:* R$ 15,50 cobriria 10/10 mas compraria 0,6
   clique/dia, e a primeira medição sairia de uma amostra inútil. R$ 2,50 é a
   mediana das estimativas — o menor lance que produz volume interpretável.

2. **Depois de 72 h de medição, decidir sobre os três termos de cabeça**
   ("maquininha de cartão" R$ 15,13, "maquininha ton" R$ 14,53,
   "maquininha moderninha" R$ 10,75). A R$ 10,00/dia eles são incompatíveis com a
   verba. Duas saídas legítimas: subir a verba, ou movê-los para grupo próprio com
   lance e verba dedicados. **Não recomendo remover keyword antes da medição** —
   removida, ela deixa de gerar a estimativa que sustenta a decisão.

3. **Não mexer na copy ainda.** O `ad_strength: POOR` é real e vale trabalho, mas
   trocar copy e lance no mesmo lote destrói a capacidade de atribuir o resultado.
   Lance primeiro, copy depois, medindo entre os dois.

---

## MUTAÇÃO PROPOSTA

**Nada foi aplicado.** A trava de escrita (`volc_ads/gads/modo.py`) esteve fechada
durante todo o diagnóstico (`escrita_permitida: false`) e permanece fechada.

> **Esta campanha não tem nada a reverter.** O `change_event` não registra
> **nenhum** `AD_GROUP UPDATE` aqui: o lance saiu da API já em R$ 0,12 às
> 13:15:50 e nunca foi tocado. O único evento humano foi `PAUSED → ENABLED` às
> 13:37:58. Diferente da FGTS, aqui não se desfaz uma decisão — **decide-se pela
> primeira vez**, e por isso o valor proposto precisa ser justificado do zero.

### Parâmetros do canário

| parâmetro | valor | de onde vem |
|---|---|---|
| lance proposto | **R$ 2,50** (`2500000`) | mediana das 10 estimativas de 1ª página (R$ 2,35), arredondada para cima |
| verba proposta | **R$ 10,00/dia** (inalterada) | nunca foi cortada; `budget_lost` não é devolvido, então não há gargalo medido |
| cobertura esperada | **0/10 → 5/10** estimativas | curva de cobertura medida |
| teto de gasto | **R$ 10,00/dia · R$ 60,00 em 72 h** | ⚠️ NÃO é verba × janela: o Google publica que a veiculação chega a **2× o orçamento diário** num dia. `STANDARD` distribui ao longo do período e **não** trava o dia em 1×. Ver [PLANO-DE-CANARIO §4](../PLANO-DE-CANARIO.md) |
| teto de cliques | ~4/dia (R$ 10,00 ÷ R$ 2,50) | divisão de dois fatos da conta |
| janela de avaliação | **72 h** a partir da aplicação | cobre 3 ciclos diários completos |
| leitura de controle | `impressions`, `search_impression_share`, `search_rank_lost_impression_share`, `search_budget_lost_impression_share`, `average_cpc`, `all_conversions` | rodar `consultas/rodar.py` de novo e comparar com esta linha de base |

**Critério de sucesso:** ≥ 100 impressões em 72 h — o piso a partir do qual zero
clique passa a ser informação em vez de acaso (mesma régua de
`volc_ads/entrega.py`).
**Critério de refutação:** entrega ainda residual (< 20 impressões) com
`rank_lost` alto → o lance **não** era a restrição sozinha, e a investigação volta
para qualidade/relevância.
**Critérios de interrupção imediata:** gasto acumulado > R$ 30,00; ou
`average_cpc` real acima da estimativa de topo da keyword que gastou; ou
`policy_summary.approval_status` deixar de ser `APPROVED`; ou `primary_status`
deixar de ser `ELIGIBLE` em qualquer nível.

### M1 — lance do grupo (a única a aplicar no primeiro ciclo)

```json
{
  "customer_id": "8017851692",
  "login_customer_id": "6016739364",
  "mutate_operations": [
    {
      "ad_group_operation": {
        "update": {
          "resource_name": "customers/8017851692/adGroups/199084728163",
          "cpc_bid_micros": 2500000
        },
        "update_mask": { "paths": ["cpc_bid_micros"] }
      }
    }
  ],
  "partial_failure": false,
  "validate_only": true
}
```

Valor atual `120000`. **Rollback:** repetir com `"cpc_bid_micros": 120000` — um
campo, um valor, efeito imediato.
Rodar antes com `validate_only: true`: é leitura para todos os efeitos, e
`volc_ads/gads/client.py::validar_mutacoes` já faz exatamente isso **sem
destravar nada**.

*Por que R$ 2,50 e não R$ 15,50:* R$ 15,50 cobriria 10/10 estimativas, mas
compraria **0,6 clique/dia** com a verba atual — a medição sairia de uma amostra
inútil e o gasto iria inteiro para um único termo. R$ 2,50 é o menor lance que
produz volume interpretável.

### M2 — verba, **condicional e pré-autorizada** dentro da mesma janela

```json
{
  "customer_id": "8017851692",
  "login_customer_id": "6016739364",
  "mutate_operations": [
    {
      "campaign_budget_operation": {
        "update": {
          "resource_name": "customers/8017851692/campaignBudgets/15800018633",
          "amount_micros": 30000000
        },
        "update_mask": { "paths": ["amount_micros"] }
      }
    }
  ],
  "partial_failure": false,
  "validate_only": true
}
```

R$ 10,00 → R$ 30,00/dia. Novo teto: R$ 90,00 em 72 h.
**Gatilho nomeado:** aplicar **assim que** `search_budget_lost_impression_share`
passar a ser devolvido **e** for > 0,10 em qualquer dia da janela. Hoje ele é
**não devolvido** — subir verba antes disso é gastar contra um gargalo que não foi
medido. **Rollback:** `10000000`.

### M3 — os três termos de cabeça, **não antes de 72 h**

"maquininha de cartão" (R$ 15,13), "maquininha ton" (R$ 14,53) e "maquininha
moderninha" (R$ 10,75) são estruturalmente incompatíveis com R$ 10,00/dia: cada
clique consome de 1 a 1,5 dia de verba. Duas saídas legítimas — grupo próprio com
verba dedicada, ou verba maior. **Nenhuma delas se decide antes de existir CPC
real medido**, e por isso não há payload aqui: propor agora seria escolher entre
duas hipóteses com zero dado de custo.
⚠️ Note que a única impressão desta campanha veio **justamente de "maquininha de
cartão"**, a mais cara — mais uma razão para não removê-la antes de medir.

### O que eu explicitamente NÃO proponho

- **Nenhuma palavra-chave negativa.** O relatório de termos tem **1 linha**
  ("tom máquina", 1 impressão, 0 clique). Não se exclui tráfego com base em um
  termo. Negativas só depois de haver relatório real.
- **Não trocar para `MaximizeConversions`** — `all_conversions = 0.0` e
  `NOT_ENOUGH_CONVERSIONS`; a estratégia entraria sem sinal e entregaria menos.
- **Não reescrever a copy no mesmo lote.** O `ad_strength: POOR` é real e merece
  trabalho, mas duas variáveis na mesma janela tornam o resultado inatribuível.
- **Não remover keyword nenhuma** antes de haver medição com lance viável.
- **Não tocar em geo, idioma, rede, dispositivo ou agendamento** — os cinco foram
  testados e nenhum é causa.
