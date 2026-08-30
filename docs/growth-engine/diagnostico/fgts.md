# FGTS Saque-Aniversário — `24156373085`

Leitura direta da API v25, somente `SELECT`, em **26/08/2026 17:41 BRT**
(`2026-08-26T20:41:57Z`). Conta `8017851692`, `login_customer_id=6016739364`.
Dados crus: [`evidencia.json`](evidencia.json).

> **Três campanhas FGTS foram criadas em 19/08; uma está no ar.**
>
> | id | nome | status | destino |
> |---|---|---|---|
> | `24156134066` | `BR - 20260819_200614 / …` | `REMOVED` | removida via **API** às 21:38:59 |
> | `24161105437` | `BR BR - 20260819_215205 / …` | `REMOVED` | removida via **API** às 22:25:52 |
> | **`24156373085`** | `BR BR - 20260819_222608 / …` | **`ENABLED`** | **a viva** |
>
> As duas removidas nunca saíram de `PAUSED` — foram criadas pausadas e removidas
> pausadas, ambas pela API, sem passar pelo painel. Registram **0 impressões**.
> Elas compartilham os `criterion_id` das keywords com a viva; juntar dados por
> `criterion_id` sem o `ad_group` mistura as três.

---

## OBSERVAÇÃO

### Conta

Idêntica ao dossiê da Maquininha: `8017851692` "Crédito Up", `BRL`,
`America/Sao_Paulo`, `customer.status: ENABLED`, `manager: false`,
`test_account: false`,
`pay_per_conversion_eligibility_failure_reasons: [OTHER, NOT_ENOUGH_CONVERSIONS]`,
`billing_setup.status: APPROVED` desde `2026-08-04 09:27:55`.

### Campanha

| campo | valor |
|---|---|
| `campaign.status` | `ENABLED` |
| **`campaign.primary_status`** | **`ELIGIBLE`** |
| **`campaign.primary_status_reasons`** | **não devolvido** (nenhuma razão) |
| `campaign.serving_status` | `SERVING` |
| `campaign.advertising_channel_type` | `SEARCH` |
| **`campaign.bidding_strategy_type`** | **`MANUAL_CPC`** |
| `campaign.manual_cpc.enhanced_cpc_enabled` | `false` |
| `campaign.start_date_time` | `2026-08-19 22:26:12` |
| `campaign.end_date_time` | **não devolvido** (sem término) |
| `campaign.network_settings` | `target_google_search: true`, `target_search_network: true`, `target_content_network: false`, `target_partner_search_network: false` |
| `campaign.payment_mode` | `CLICKS` |
| `campaign.bidding_strategy_system_status` | `UNAVAILABLE` |

Nenhum campo de estratégia automática foi devolvido: `target_spend`,
`maximize_conversions`, `target_cpa`, `target_roas` **não existem** nesta
campanha. Ela é manual do nascimento até agora.

### Orçamento — `campaign_budget/15806163240`

| campo | valor |
|---|---|
| `amount_micros` | `10000000` → **R$ 10,00/dia** |
| valor no nascimento | `20000000` → R$ 20,00/dia (reduzido em 19/08 22:39:21) |
| `delivery_method` | `STANDARD` |
| `period` / `status` | `DAILY` / `ENABLED` |
| `has_recommended_budget` | `false` |
| `recommended_budget_amount_micros` | **não devolvido** |

### Grupo de anúncios — `200104492795` "AdGroup_20260819_222608"

| campo | valor |
|---|---|
| `ad_group.status` | `ENABLED` |
| **`ad_group.primary_status`** | **`ELIGIBLE`** (sem razões) |
| `ad_group.type` | `SEARCH_STANDARD` |
| **`ad_group.cpc_bid_micros`** | **`120000` → R$ 0,12** |
| valor no nascimento | **`1000000` → R$ 1,00** (alterado em 19/08 22:39:45) |

### Anúncio — `821568692813`

| campo | valor |
|---|---|
| `ad_group_ad.status` | `ENABLED` |
| **`ad_group_ad.primary_status`** | **`ELIGIBLE`** (sem razões) |
| **`policy_summary.approval_status`** | **`APPROVED`** |
| **`policy_summary.review_status`** | **`REVIEWED`** |
| **`policy_summary.policy_topic_entries`** | **não devolvido** (vazio) |
| `ad_group_ad.ad_strength` | **`GOOD`** |
| `ad_group_ad.action_items` | `"Try including more keywords in your headlines."`, `"Try including more keywords in your descriptions."` |
| títulos / descrições | 15 / 4 |
| `ad.final_urls` | `https://creditoup.com.br/r/fgts-saque-aniversario/` |

**Nenhuma restrição de serviços financeiros.** Não há `policy_topic_entries`, o
`approval_status` é `APPROVED` (não `APPROVED_LIMITED`), e nenhum nível da cadeia
devolveu razão de status. Isto é relevante porque o brief versionado classifica a
campanha como vertical `"informativo"` para um produto que é financeiro: **a
suspeita era legítima e a conta a refuta** — não há confundimento de política
contaminando o diagnóstico do lance.

### Keywords — 81, todas `PHRASE`

Uniformes em: `status: ENABLED` (81/81), `approval_status: APPROVED` (81/81),
`system_serving_status: **ELIGIBLE**` (81/81 — nenhuma `RARELY_SERVED`),
`negative: false` (81/81), `disapproval_reasons`: não devolvido,
`cpc_bid_micros` próprio: **não devolvido** (herdam do grupo),
`effective_cpc_bid_micros: 120000`, `effective_cpc_bid_source: **AD_GROUP**`,
`quality_info`: **não devolvido** (81/81 — sem Índice de Qualidade atribuído).

**A divisão que importa:**

| `primary_status_reasons` | keywords |
|---|---|
| **`[AD_GROUP_CRITERION_BELOW_FIRST_PAGE_BID]`** | **42 de 81 (52%)** |
| não devolvido, `primary_status: ELIGIBLE` | 39 de 81 (48%) |

`position_estimates` devolvido para **49 das 81**:
min R$ 0,02 · p25 R$ 0,57 · **mediana R$ 0,92** · p75 R$ 0,92 · max R$ 1,45.

Cinco mais caras: `consultar fgts pelo cpf` R$ 1,45 · `optei pelo saque
aniversário e fui demitido` R$ 1,20 · `fgts saque-aniversário` R$ 1,20 ·
`fgts saque-aniversário como funciona` R$ 1,20 · `aplicativo fgts` R$ 1,07.

**A curva de cobertura é a peça central deste dossiê:**

| lance do grupo | estimativas cobertas | teto de cliques/dia a R$ 10,00 |
|---|---|---|
| **R$ 0,12 (hoje)** | **7 de 49 — 14%** | 83,3 |
| R$ 0,50 | 11 de 49 — 22% | 20,0 |
| **R$ 1,00 (nascimento)** | **43 de 49 — 88%** | 10,0 |
| R$ 1,50 | 49 de 49 — 100% | 6,7 |

### Segmentação

`LOCATION 2076` = **Brazil** (`country_code: BR`, `target_type: Country`),
`ENABLED`, `negative: false`. `LANGUAGE 1014` = **pt**, `ENABLED`,
`negative: false`. `DEVICE` Desktop / HighEndMobile / Tablet, todos `ENABLED`,
`negative: false`, sem `bid_modifier`. **Nenhum `AD_SCHEDULE`.** **Nenhuma
negativa de campanha.** `campaign_shared_set`: **0 linhas**.

### Métricas — vida inteira, `2026-08-19 → 2026-08-26` (datas explícitas)

| métrica | valor | leitura |
|---|---|---|
| `metrics.impressions` | **5** | — |
| `metrics.clicks` | 0 | — |
| `metrics.cost_micros` | 0 → **R$ 0,00** | de R$ 70,00 disponíveis em 7 dias |
| `metrics.average_cpc` | **não devolvido** | sem clique |
| **`metrics.search_impression_share`** | **0,0999** | valor-limite da API para **"< 10%"** |
| **`metrics.search_rank_lost_impression_share`** | **0,9001** | valor-limite para **"> 90%"** |
| **`metrics.search_budget_lost_impression_share`** | **0,0** | **zero, medido — não ausente** |
| `metrics.search_top_impression_share` | 0,0999 | "< 10%" |
| `metrics.search_absolute_top_impression_share` | 0,0999 | "< 10%" |
| `metrics.conversions` / `all_conversions` | 0.0 / 0.0 | — |

Idêntico em `LAST_30_DAYS` (27/07 → 25/08), o que confirma que não houve entrega
anterior ao lançamento.

Diário:

| data | impressões | IS | rank perdido | verba perdida |
|---|---|---|---|---|
| 2026-08-20 | 4 | 0,0999 | 0,9001 | 0,0 |
| 2026-08-21 a 23 | **sem linha devolvida** | — | — | — |
| 2026-08-24 | 1 | não devolvido | não devolvido | não devolvido |
| 2026-08-25 | 0 | 0,0999 | 0,9001 | 0,0 |
| 2026-08-26 (`TODAY`) | **0** | não devolvido | não devolvido | não devolvido |

Termos de busca na janela: **um só** — `"como liberar saque aniversario fgts"`,
1 impressão, 0 cliques.

### Conversões da conta

5 `conversion_action`; 4 `ENABLED`, 1 `HIDDEN`. Única `primary_for_goal: true` e
`include_in_conversions_metric: true`: `7718441216` "adViewInterstitial"
(`WEBPAGE`, `PURCHASE`, janela de 30 dias). **`all_conversions = 0.0` em todas**
na janela.

### `change_event` — o juiz

Janela `LAST_14_DAYS` (12/08 → 26/08). 423 eventos na conta, **todos** em
19/08/2026 entre 12:38:27 e 22:39:45, autor único `tarcisio@agenciavolc.com.br`.
Para esta campanha:

```
22:26:13.670  CAMPAIGN_BUDGET  CREATE  GOOGLE_ADS_API         amount_micros = 20000000   (R$ 20,00/dia)
22:26:13.670  CAMPAIGN         CREATE  GOOGLE_ADS_API         status PAUSED · manualCpc.enhancedCpcEnabled
22:26:13.670  AD_GROUP         CREATE  GOOGLE_ADS_API         cpc_bid_micros = 1000000   (R$ 1,00)
──────────────────────────────────────────────────────────────────────────────────────────────────────
22:39:13.799  CAMPAIGN         UPDATE  GOOGLE_ADS_WEB_CLIENT  status  PAUSED → ENABLED
22:39:21.132  CAMPAIGN_BUDGET  UPDATE  GOOGLE_ADS_WEB_CLIENT  amount_micros  20000000 → 10000000
22:39:45.237  AD_GROUP         UPDATE  GOOGLE_ADS_WEB_CLIENT  cpc_bid_micros  1000000 →  120000
```

**Nenhum evento após 19/08 22:39:45** — sete dias sem qualquer alteração.

---

## DIAGNÓSTICO

**A campanha está plenamente elegível, entra no leilão, e perde mais de 90% da
parcela de impressões por CLASSIFICAÇÃO — com perda por orçamento medida em
exatamente zero. A restrição é o lance, e o lance é resultado de uma alteração
manual feita 26 segundos depois de a campanha ser ligada.**

1. **A medição separa as duas causas possíveis e atribui tudo a uma.**
   `search_rank_lost_impression_share = 0,9001` (">90%") contra
   `search_budget_lost_impression_share = 0,0`. Não é inferência sobre o lance ser
   baixo: é o Google decompondo a impressão perdida e dizendo qual metade a levou.
   Este é o dado mais forte do diagnóstico inteiro.

2. **O Google também nomeia a causa keyword por keyword.**
   `AD_GROUP_CRITERION_BELOW_FIRST_PAGE_BID` em **42 de 81**.

   ⚠️ **Mas a entrega residual não veio de onde se esperaria.** Cruzando por
   `(ad_group, criterion_id)` — a chave correta, já que o `criterion_id` é
   compartilhado com as campanhas irmãs — as 4 keywords que registraram impressão
   são `como sacar o saque-aniversário` (2, estimativa R$ 0,92),
   `fgts saque-aniversário` (1, R$ 1,20), `como sacar o fgts rescisão`
   (1, R$ 0,99) e `calendário fgts` (1, R$ 0,30). **Todas com estimativa acima do
   lance.** Das 7 keywords que R$ 0,12 de fato alcança, **nenhuma entregou.**

   A leitura correta disso é que `first_page_cpc_micros` **não é uma catraca
   liga/desliga**: é o lance para presença *consistente* na primeira página.
   Abaixo dele o anúncio ainda aparece esporadicamente, em leilão raso ou fora de
   pico. O padrão observado é exatamente esse — 4 impressões em 20/08, 1 em 24/08,
   nenhuma linha em 21, 22, 23 e 26/08. **Abaixo da estimativa a entrega é
   residual e não acumula volume**, que é a formulação que a evidência sustenta.

3. **A cadeia inteira está elegível.** `primary_status = ELIGIBLE` sem razões em
   campanha, grupo e anúncio; anúncio `APPROVED`/`REVIEWED` com
   `policy_topic_entries` vazio. Nenhum bloqueio de status ou política.

4. **A causa raiz é a alteração de 22:39:45, e ela é reversível.** O motor criou o
   grupo com **R$ 1,00** — lance que cobre **43 das 49** estimativas (88%). O
   painel o levou a **R$ 0,12** — que cobre **7** (14%). Um humano reduziu a
   cobertura de leilão a um sexto, 26 segundos depois de ligar a campanha, e nada
   foi tocado nos sete dias seguintes.

5. **Orçamento não é gargalo, e isso está medido, não suposto.**
   `search_budget_lost_impression_share = 0,0` **devolvido como zero** — diferente
   de não devolvido. E R$ 0,00 gastos de R$ 70,00 disponíveis. A redução de
   R$ 20,00 para R$ 10,00 no mesmo minuto **não é a causa da não entrega**; ela
   apenas reduz o teto do que a campanha poderá gastar quando voltar a entregar.

6. **Smart Bidding não está em jogo.** `MANUAL_CPC` no nascimento e hoje, sem
   nenhum campo de estratégia automática. A conta de fato não tem histórico de
   conversão (`all_conversions = 0.0`, `NOT_ENOUGH_CONVERSIONS`), mas isso **não
   pode travar** uma estratégia manual — é uma restrição futura, não a causa atual.
   O achado real aqui é outro: **a estratégia declarada em comentário no brief
   (`MaximizeConversions`) nunca chegou à conta**, e o lance que o autor descreveu
   como "rede de proteção que a API ignoraria" virou o lance real do leilão.

7. **Baixo volume está descartado.** `system_serving_status: ELIGIBLE` em 81/81.

### O que a amostra NÃO sustenta

Com **5 impressões e 0 cliques**:

- nenhuma conclusão sobre CTR, criativo ou landing page. O `ad_strength: GOOD` é
  um bom sinal, mas **não foi validado por clique nenhum**;
- `quality_info` **não devolvido** em 81/81 — não há Índice de Qualidade a
  interpretar, e "não devolvido" não é "zero". O Índice de Qualidade **não pode
  ser culpado nem inocentado** pela perda por classificação: é ausência de dado.
  O que fecha o raciocínio mesmo assim é que `first_page_cpc_micros` **já vem
  condicionado à qualidade atual** do anúncio — o Google está dizendo "com este
  anúncio, o lance precisa ser R$ X", e o lance é ~8× menor que esse X;
- as 32 keywords sem `position_estimates` não permitem afirmar que o lance as
  cobre ou não. **Não devolvido**, e o número 49/81 é o denominador honesto;
- os valores `0,0999` e `0,9001` são os **limites de arredondamento** que a API
  usa para "<10%" e ">90%". A parcela real não é conhecida com mais precisão —
  o que se sabe é o lado do limite, e isso basta para o diagnóstico.

---

## HIPÓTESE

| # | hipótese | por que é plausível | teste que a resolveria |
|---|---|---|---|
| H1 | Reverter o lance para R$ 1,00 restaura a entrega em 48–72 h | é o valor com que o motor criou a campanha, e cobre 88% das estimativas contra 14% hoje | aplicar M1 e reler `impressions`, `search_impression_share` e `search_rank_lost_impression_share` em 72 h. `rank_lost` caindo abaixo de 0,9001 confirma; permanecer em ">90%" **refuta** e aponta para qualidade, não lance |
| H2 | A R$ 1,00 o orçamento de R$ 10,00/dia passa a ser o novo gargalo | teto de 10 cliques/dia; se a demanda for maior, a verba estoura | após H1, observar se `search_budget_lost_impression_share` **deixa de ser 0,0**. É o mesmo campo que hoje inocenta a verba |
| H3 | As 32 keywords sem estimativa são de volume marginal | o Google não estima o que quase não é buscado — mas `system_serving_status` diz `ELIGIBLE`, o que contraria | após H1, medir impressões por keyword em `keyword_view` e ver quais permanecem em zero |
| H4 | A vertical `"informativo"` declarada no brief representa risco de política ainda não materializado | a conta hoje está `APPROVED` sem `policy_topic_entries`, mas revisão de serviços financeiros pode ocorrer depois | reler `policy_summary` semanalmente; hoje a hipótese está **sem suporte na conta** |

---

## RECOMENDAÇÃO

Reversíveis, em ordem, e **nada aplicado**:

1. **Reverter `ad_group.cpc_bid_micros` de `120000` para `1000000` (R$ 1,00).**
   É o valor original do motor — uma reversão, não uma invenção, e por isso o
   número mais defensável disponível. Efeito esperado: cobertura de **14% → 88%**
   das estimativas de 1ª página. Rollback: voltar a `120000`.

2. **Manter o orçamento em R$ 10,00/dia neste primeiro ciclo.** A R$ 1,00 ele
   comporta ~10 cliques/dia, o que é volume suficiente para medir. Reverter os
   dois campos ao mesmo tempo confundiria "voltou a entregar por causa do lance"
   com "por causa da verba" — e é justamente essa separação que a evidência de
   hoje torna possível. Só subir para R$ 20,00 **depois** que
   `search_budget_lost_impression_share` deixar de ser `0,0`.

3. **Investigar, fora deste escopo, por que a estratégia declarada não chegou à
   conta.** As 5 campanhas nasceram `MANUAL_CPC` enquanto o brief da FGTS
   documenta `MaximizeConversions`; e o brief declara `cpc_inicial=0.20` enquanto
   o `change_event` mostra a campanha nascendo com R$ 1,00. Duas divergências
   entre código versionado e conta viva, ambas medidas, nenhuma corrigível daqui.

4. **Não reescrever a copy.** `ad_strength: GOOD` já é a melhor nota da conta.

---

## MUTAÇÃO PROPOSTA

**Nada foi aplicado.** A trava de escrita (`volc_ads/gads/modo.py`) esteve fechada
durante todo o diagnóstico (`escrita_permitida: false`) e permanece fechada.

> **Aqui há o que reverter.** As duas alavancas foram cortadas no mesmo minuto
> (22:39:21 e 22:39:45) por um humano no painel. Os valores propostos abaixo não
> são invenções: são **os valores de nascimento**, e por isso são os números mais
> defensáveis disponíveis.

### Parâmetros do canário

| parâmetro | valor | de onde vem |
|---|---|---|
| lance proposto | **R$ 1,00** (`1000000`) | valor com que o motor criou o grupo em 19/08 22:26:13 |
| verba no ciclo 1 | **R$ 10,00/dia** (inalterada) | ver a nota de sequenciamento abaixo |
| cobertura esperada | **7/49 → 43/49** estimativas (14% → 88%) | curva de cobertura medida |
| teto de gasto | **R$ 10,00/dia · R$ 60,00 em 72 h** | ⚠️ NÃO é verba × janela: o Google publica que a veiculação chega a **2× o orçamento diário** num dia. `STANDARD` distribui ao longo do período e **não** trava o dia em 1×. Ver [PLANO-DE-CANARIO §4](../PLANO-DE-CANARIO.md) |
| teto de cliques | ~10/dia (R$ 10,00 ÷ R$ 1,00) | divisão de dois fatos da conta |
| janela de avaliação | **72 h** a partir da aplicação | cobre 3 ciclos diários completos |
| leitura de controle | `impressions`, `search_impression_share`, `search_rank_lost_impression_share`, `search_budget_lost_impression_share`, `average_cpc`, `all_conversions` | rodar `consultas/rodar.py` e comparar com esta linha de base |

**Critério de sucesso:** `search_rank_lost_impression_share` cair abaixo de
`0,9001` **e** ≥ 100 impressões em 72 h.
**Critério de refutação:** `rank_lost` permanecer em ">90%" com o lance a R$ 1,00
→ a restrição não é (só) o lance, e a investigação vai para qualidade/relevância.
**Critérios de interrupção imediata:** gasto acumulado > R$ 90,00 — `metrics.cost_micros` é *served cost*, não *billed*, e o abort precisa de folga sobre o teto de cobrança de R$ 60,00 (ou mais se
M2 tiver disparado); ou `average_cpc` real acima de R$ 1,45 (a maior estimativa de
1ª página da campanha); ou `policy_summary.approval_status` deixar de ser
`APPROVED`; ou `primary_status` deixar de ser `ELIGIBLE` em qualquer nível.

### Sobre "as duas alavancas voltam juntas": por que sequenciar, e por que isso não trava o canário

A objeção é justa — subir o lance sem olhar a verba troca "não entrega" por
"entrega e esgota". Duas coisas a desarmam:

1. `campaign_budget.delivery_method` é **`STANDARD`**, não `ACCELERATED`. O Google
   distribui o gasto ao longo do dia; o modo de falha "acaba às 10 da manhã" é o
   comportamento de `ACCELERATED`, e não é o desta campanha.
2. **O gargalo de verba é medido, não adivinhado.** Hoje
   `search_budget_lost_impression_share = 0,0` — devolvido, e igual a zero. É o
   mesmo campo que passará a ser > 0 no instante em que a verba começar a limitar.

Manter R$ 10,00 no ciclo 1 converte uma incógnita em medição de graça. Para que
isso não custe tempo, **M2 abaixo já vai pré-autorizada com gatilho nomeado**: ela
dispara dentro da mesma janela de 72 h, sem esperar nova rodada de análise.

### M1 — reverter o lance ao valor de nascimento (aplicar no ciclo 1)

```json
{
  "customer_id": "8017851692",
  "login_customer_id": "6016739364",
  "mutate_operations": [
    {
      "ad_group_operation": {
        "update": {
          "resource_name": "customers/8017851692/adGroups/200104492795",
          "cpc_bid_micros": 1000000
        },
        "update_mask": { "paths": ["cpc_bid_micros"] }
      }
    }
  ],
  "partial_failure": false,
  "validate_only": true
}
```

Valor atual `120000`; valor de nascimento `1000000`. **Rollback:** repetir com
`"cpc_bid_micros": 120000`.
Rodar antes com `validate_only: true` — leitura para todos os efeitos, e
`volc_ads/gads/client.py::validar_mutacoes` já faz isso **sem destravar nada**.

### M2 — reverter a verba ao valor de nascimento (pré-autorizada, com gatilho)

```json
{
  "customer_id": "8017851692",
  "login_customer_id": "6016739364",
  "mutate_operations": [
    {
      "campaign_budget_operation": {
        "update": {
          "resource_name": "customers/8017851692/campaignBudgets/15806163240",
          "amount_micros": 20000000
        },
        "update_mask": { "paths": ["amount_micros"] }
      }
    }
  ],
  "partial_failure": false,
  "validate_only": true
}
```

R$ 10,00 → R$ 20,00/dia, restaurando o nascimento. Novo teto: R$ 60,00 em 72 h.
**Gatilho nomeado:** aplicar **assim que** `search_budget_lost_impression_share`
for > 0,10 em qualquer dia após M1. **Rollback:** `10000000`.

### O que eu explicitamente NÃO proponho

- **Nenhuma palavra-chave negativa.** `search_term_view` devolveu **1 linha** para
  esta campanha ("como liberar saque aniversario fgts", 1 impressão, 0 clique).
  Decidir exclusão com um termo é decidir sem amostra. Negativas voltam à mesa
  quando houver relatório de termos real — ou seja, depois de haver tráfego.
- **Não trocar para `MaximizeConversions`**, apesar de ser o que o brief descreve:
  `all_conversions = 0.0` em todas as ações e `NOT_ENOUGH_CONVERSIONS` devolvido
  pela conta. A estratégia entraria sem sinal e entregaria menos. Volta à mesa
  quando houver conversão registrada — e o primeiro ciclo de tráfego é justamente
  o que pode produzi-la.
- **Não aplicar M1 e M2 no mesmo instante**, pelo motivo da nota de sequenciamento.
- **Não reescrever a copy.** `ad_strength: GOOD` já é a melhor nota da conta, e
  mexer nela junto com o lance tornaria o resultado inatribuível.
- **Não tocar nas duas campanhas FGTS removidas.** Estão `REMOVED` com 0
  impressões; removida é um estado legítimo, não um resto a limpar.
- **Não tocar em geo, idioma, rede, dispositivo ou agendamento** — todos testados,
  nenhum é causa.
