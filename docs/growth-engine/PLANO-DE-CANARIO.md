# Plano de Canário — trilha imediata (Search, Crédito Up)

**Escrito em:** 26/08/2026 · **Estado:** **AGUARDANDO AUTORIZAÇÃO DO DONO** — sem pendência técnica desde 26/08/2026
**Nada aqui foi executado.** A trava de escrita do engine está fechada e foi conferida
fechada durante toda a leitura (`escrita_permitida: false`, registrado em
[`diagnostico/evidencia.json`](./diagnostico/evidencia.json)).

**Base factual:** [`diagnostico/README.md`](./diagnostico/README.md) ·
[`fgts.md`](./diagnostico/fgts.md) · [`maquininha.md`](./diagnostico/maquininha.md).
Leitura de 26/08/2026 17:41 BRT, janela `LAST_30_DAYS`, API v25, somente `SELECT`.

---

## 0. O que este plano é, e o que ele não é

Ele **altera duas campanhas que já existem**. Não cria nada. A esteira de criação
pausada → verificação → segunda aprovação → ativação vale para a campanha Display,
e está no [plano da trilha estrutural](#trilha-estrutural--display) mais abaixo.

Alterar é mais barato de reverter que criar, e por isso a trilha imediata vem antes:
o campo alterado tem um valor anterior conhecido, e voltar a ele é uma operação.

⚠️ **Duas campanhas, duas causas diferentes.** Isso decide o que "rollback" significa
em cada uma, e é a razão de elas não entrarem no mesmo lote:

| | FGTS `24156373085` | Maquininha `24155134757` |
|---|---|---|
| como o lance chegou a R$ 0,12 | humano no painel, 19/08 22:39:45, de **R$ 1,00** | **nasceu assim** pela API; zero `AD_GROUP UPDATE` em 423 eventos |
| rollback é… | **reversão** a um valor que já existiu e funcionou | **não existe alvo anterior** — é decisão inédita |
| confiança na proposta | **alta** (o valor proposto é o que o motor havia escolhido) | **média** (o valor proposto é a mediana das estimativas do Google) |

---

## 1. Conta, escopo e credencial

| campo | valor |
|---|---|
| **customer ID** | **`8017851692`** — Crédito Up |
| MCC obrigatório (`login_customer_id`) | `6016739364` — VOLC Negócios Digitais |
| moeda · fuso | **BRL** · `America/Sao_Paulo` |
| status da conta | `ENABLED`, não é conta de teste, faturamento `APPROVED` |
| canal | `SEARCH` (`advertising_channel_type`) |
| geografia | Brasil inteiro (`geoTargetConstants/2076`) — **não muda** |
| idioma | Português (`languageConstants/1014`) — **não muda** |
| rede | Google Search + parceiros de busca — **não muda** |
| conversão principal | `adViewInterstitial` id **`7718441216`** · `ENABLED` · `primary_for_goal: true` · `include_in_conversions_metric: true` |
| assets | **nenhum** — este plano não toca em criativo |

**A conversão existe e mede, e ainda não mediu nada:** zero conversões porque houve
zero cliques. É o que torna defensável comprar tráfego — e é também o que impede
qualquer conclusão sobre CPA nesta janela.

⚠️ **Pré-checagem obrigatória antes de executar, e ela pode invalidar o teste
inteiro:** existe um **limite de gasto diário no nível da CONTA** que se sobrepõe
aos orçamentos de campanha, comum em contas novas ou com verificação de anunciante
pendente, e que **não pode ser aumentado a pedido**. Ele corta para o lado seguro
no dinheiro, mas envenena a leitura: entrega travada por limite de conta **parece
falta de demanda**, e o canário concluiria o oposto do que aconteceu. Ler antes de
alterar qualquer lance.

---

## 2. A intenção

Descobrir se estas duas campanhas têm demanda a um custo que a operação aceita.
Hoje isso é **desconhecido**, e é desconhecido por uma razão evitável: elas não
entram no leilão. Sete dias no ar, R$ 70,00 de orçamento disponível, **R$ 0,00
gastos**, 6 impressões somadas, 0 cliques.

O objetivo do canário **não é lucro**. É comprar a primeira amostra de que a conta
precisa para qualquer decisão seguinte — inclusive a decisão de desistir.

---

## 3. As alterações propostas

### 3.1 · FGTS — `campaigns/24156373085`

| | antes | proposto |
|---|---|---|
| `adGroups/200104492795` · `cpc_bid_micros` | `120000` (R$ 0,12) | **`1000000`** (R$ 1,00) |
| estratégia de lance | `MANUAL_CPC`, `enhanced_cpc_enabled: false` | **não muda** |
| `campaignBudgets/15806163240` · `amount_micros` | `10000000` (R$ 10,00/dia) | **não muda agora** — ver 3.3 |
| `delivery_method` | `STANDARD` | **não muda** |

**Por que R$ 1,00 e não outro número:** é o valor que o próprio motor escolheu ao
criar o grupo às 22:26:13, antes da alteração manual. A R$ 1,00 o lance cobria
**43 das 49** estimativas de primeira página (88%); a R$ 0,12 cobre **7** (14%).
Não é um número novo — é a reversão de uma mudança identificada, com autor,
horário e valor anterior conhecidos.

**Sequência de operações:** uma só. `AdGroupOperation` de `update`, `update_mask`
cobrindo apenas `cpc_bid_micros`. Nada de `mutate` composto: uma alteração de um
campo em um recurso.

### 3.2 · Maquininha — `campaigns/24155134757`

| | antes | proposto |
|---|---|---|
| `adGroups/199084728163` · `cpc_bid_micros` | `120000` (R$ 0,12) | **`2500000`** (R$ 2,50) |
| estratégia de lance | `MANUAL_CPC` | **não muda** |
| `campaignBudgets/15800018633` · `amount_micros` | `10000000` (R$ 10,00/dia) | **não muda agora** — ver 3.3 |

**Por que R$ 2,50:** é a mediana das 10 estimativas de primeira página do Google
(R$ 2,35), arredondada para cima. Cobertura passa de **0 de 10** para cerca de
**5 de 10**. **Não** cobre a cabeça — "maquininha de cartão" pede R$ 15,13, que é
126× o lance atual — e cobrir a cabeça é decisão separada (3.4).

⚠️ **Aqui não há reversão, há escolha.** O lance nunca foi outro. A confiança é
média, e o critério de interrupção (§6) é o que protege a decisão.

### 3.3 · Verba — pré-autorizada por gatilho, não aplicada agora

| campanha | orçamento | sobe para | **somente quando** |
|---|---|---|---|
| FGTS | `campaignBudgets/15806163240` R$ 10,00 | R$ 20,00 | `search_budget_lost_impression_share > 0,10` |
| Maquininha | `campaignBudgets/15800018633` R$ 10,00 | R$ 30,00 | idem |

**Por que a verba não sobe junto com o lance.** Eu havia exigido que as duas
alavancas voltassem juntas, e o dado me corrigiu: `delivery_method` é `STANDARD`,
não `ACCELERATED` — o modo de falha "esgota o orçamento às 10 da manhã" **não
existe** nesta configuração. E `search_budget_lost_impression_share` é o campo que
avisa, medido pelo próprio Google, no instante em que a verba passar a limitar.
Subir as duas ao mesmo tempo custaria a única coisa que este teste produz: saber
qual das duas mudou o resultado.

O gatilho fica **pré-autorizado** para não travar o canário à espera de uma segunda
conversa — mas continua sendo uma alteração que gera recibo próprio.

### 3.4 · O que deliberadamente NÃO entra

- **Nenhuma negativa.** O relatório de termos de busca tem **2 linhas na conta
  inteira**, com zero clique. Sem amostra não se propõe negativa (ADR-25). Lista
  genérica de "termos comumente excluídos" também não — um exemplo vira padrão.
- **Nenhuma troca para Smart Bidding.** `all_conversions = 0.0` e
  `pay_per_conversion_eligibility_failure_reasons` inclui `NOT_ENOUGH_CONVERSIONS`.
  Estratégia automática sem histórico é chute com autoridade, e mexer no lance e na
  estratégia no mesmo teste torna o resultado ilegível.
- **Nenhuma reescrita de copy.** Com 6 impressões e 0 cliques não há amostra que
  sustente afirmação sobre criativo. `quality_info` veio nulo em 91 de 91 keywords.
- **Os 3 termos de cabeça da Maquininha** (R$ 10,75 a R$ 15,13): decisão à parte,
  **sem payload de propósito**. Exige CPC real medido nesta conta primeiro — e é
  exatamente isso que este canário vai produzir.
- **Nenhuma das 3 campanhas removidas** é tocada. Elas ficam como estão.

---

## 4. Teto de gasto

| | FGTS | Maquininha | **total** |
|---|---|---|---|
| orçamento diário | R$ 10,00 | R$ 10,00 | R$ 20,00/dia |
| janela do teste | 72 h | 72 h | — |
| teto nominal (diário × 3) | R$ 30,00 | R$ 30,00 | R$ 60,00 |
| **teto real (2× diário × 3)** | **R$ 60,00** | **R$ 60,00** | **R$ 120,00** |

✅ **Confirmado com fonte oficial em 26/08/2026 — deixou de ser hipótese.** O Google
publica que a veiculação pode chegar a **exatamente 2× o orçamento diário médio**
num dia ("for most campaigns"), e que o gasto mensal é limitado a **30,4× o
diário** (365 ÷ 12). O 30,4 aparece em duas fontes independentes: o Help Center e a
docstring do proto instalado (`CampaignBudget.amount_micros`).

**O teto a declarar ao dono é R$ 120,00.** O mensal (30,4 × R$ 20 = R$ 608) não é a
restrição ativa numa janela de 72 h. Há nota oficial de que campanha iniciada no
meio do mês considera só os dias em que rodou — o que *poderia* baixar para R$ 60 —
mas **a fórmula do rateio não é publicada**, e um plano que autoriza gasto não se
apoia em fórmula não publicada.

⚠️ **`delivery_method` não é o argumento.** O §3.3 usa `STANDARD` para dizer que a
verba não some pela manhã, e isso continua certo — mas por um motivo mais forte:
`ACCELERATED` está **sunsetado desde abril/2020** em todas as versões da API, e
apontar um orçamento para ele devolve `ACTION_NOT_PERMITTED`. O que `STANDARD`
faz é distribuir a veiculação ao longo do período; ele **não** trava o dia em 1× o
diário. Quem trava é o teto de 2×.

---

## 5. Critério de sucesso

A janela é de **72 horas** a partir da alteração. Sucesso **não é** conversão —
não há amostra possível para isso em 72 h nesta conta.

| # | critério | como medir | por quê |
|---|---|---|---|
| 1 | **a campanha entra no leilão** | `impressions > 0` nas duas, no dia seguinte | é a única coisa que este teste existe para provar |
| 2 | **rank deixa de ser a causa dominante** | `search_rank_lost_impression_share` cai materialmente na FGTS | fecha o laço com o diagnóstico |
| 3 | **a verba passa a ser a restrição** | `search_budget_lost_impression_share > 0` | é sinal de **sucesso**: significa que a demanda existe |
| 4 | **CPC real medido** | `metrics.average_cpc` com ao menos 10 cliques somados | é o insumo que falta para decidir a cabeça da Maquininha (3.4) |

**Critérios 3 e 4 são o produto real desta rodada.** Um CPC real medido nesta conta
substitui, pela primeira vez, estimativa por observação — e é ele que torna a
próxima decisão barata.

---

## 6. Critério de interrupção

Qualquer um destes **reverte imediatamente**, sem discussão nova:

1. gasto acumulado passa de **R$ 120,00** (§4).
   ⚠️ **`metrics.cost_micros` é `served cost`, não `billed cost`,** e a diferença
   derruba este gatilho se ele for lido ingenuamente. O Google declara que o custo
   veiculado *pode* exceder os limites e que ele absorve a diferença — o exemplo
   oficial mostra US$ 23 veiculados contra um limite de US$ 20, com US$ 20
   cobrados. **Não existe nenhuma métrica com "billed" em `Metrics` na v25**; o
   relatório de custo cobrado só existe na interface. Portanto: ler
   `cost_micros > 120` **dispara falso**. O gatilho real é `cost_micros` acima de
   **R$ 150** — folga de 25% sobre o teto de cobrança —, e a conciliação do valor
   cobrado se faz depois, no faturamento;
2. CPC médio real passa de **R$ 4,00** na Maquininha ou **R$ 2,00** na FGTS —
   o dobro da estimativa mediana, que é onde a estimativa deixa de descrever o leilão;
3. qualquer campanha ou anúncio muda para `primary_status` diferente de `ELIGIBLE`;
4. qualquer entrada de política aparece em `ad_group_ad.policy_summary`;
5. 72 h completas com `impressions = 0` — significa que o diagnóstico errou, e
   insistir no lance seria tratar o sintoma errado com dinheiro;
6. qualquer alteração manual no painel durante a janela — dois donos no mesmo
   número invalidam o teste (é literalmente o que aconteceu em 19/08).

---

## 7. Rollback

| alteração | operação de volta | prova de que voltou |
|---|---|---|
| FGTS lance | `adGroups/200104492795` `cpc_bid_micros` → **`120000`** | releitura do campo |
| Maquininha lance | `adGroups/199084728163` `cpc_bid_micros` → **`120000`** | releitura do campo |
| FGTS verba (se aplicada) | `campaignBudgets/15806163240` → **`10000000`** | releitura do campo |
| Maquininha verba (se aplicada) | `campaignBudgets/15800018633` → **`10000000`** | releitura do campo |

Todas são alterações de **um campo escalar**, reversíveis por uma operação, sem
efeito colateral estrutural. Nenhum recurso é criado ou removido, então não há
órfão possível.

⚠️ **O que o rollback NÃO desfaz:** o dinheiro gasto e o histórico de leilão. Voltar
o lance não devolve o gasto nem apaga o aprendizado da conta. Por isso o teto e os
critérios de interrupção são o controle real; o rollback é o freio, não o seguro.

---

## 8. Idempotência

Cada alteração carrega uma chave determinística, gravada **antes** do envio
(ADR-22), derivada da intenção — nunca do relógio:

| alteração | idempotency key |
|---|---|
| FGTS lance | `canario:20260826:8017851692:adGroup:200104492795:cpc_bid_micros:1000000` |
| Maquininha lance | `canario:20260826:8017851692:adGroup:199084728163:cpc_bid_micros:2500000` |
| FGTS verba | `canario:20260826:8017851692:budget:15806163240:amount_micros:20000000` |
| Maquininha verba | `canario:20260826:8017851692:budget:15800018633:amount_micros:30000000` |

Uma repetição da mesma intenção encontra a chave e **não** reenvia.

⚠️ **Em resultado remoto indeterminado — timeout, rede, resposta ilegível — não
repetir (ADR-23).** Reconciliar primeiro: ler o campo na conta e comparar com o
valor proposto. Alteração de campo escalar é idempotente por natureza no resultado,
mas o **recibo** não é: reenviar cria um segundo registro de uma decisão que foi
tomada uma vez, e o histórico passa a mentir sobre quantas vezes alguém decidiu.

---

## 9. Impacto esperado, risco e confiança

| | FGTS | Maquininha |
|---|---|---|
| cobertura de 1ª página | 14% → **~88%** | 0/10 → **~5/10** |
| cliques/dia no orçamento atual | ~10 a R$ 1,00 | ~4 a R$ 2,50 |
| gasto esperado em 72 h | até R$ 30 nominal | até R$ 30 nominal |
| **confiança** | **alta** — reverte a um valor que existiu | **média** — valor inédito, derivado de estimativa |

**Risco 1 — a estimativa não é o leilão.** `first_page_cpc_micros` é uma projeção do
Google, condicionada à qualidade atual. O CPC real pode vir acima. Coberto pelo
critério de interrupção 2.

**Risco 2 — entrega residual não vira volume.** A leitura desta rodada mostrou que
abaixo da estimativa a entrega é residual e não acumula; o inverso não está provado.
Pode ser que subir o lance produza entrega e ela não converta. **Isso é resultado
válido, não falha** — e é barato: R$ 120 no pior caso.

**Risco 3 — dois donos.** Em 19/08 uma alteração manual no painel desfez o que a API
havia decidido, 13 minutos depois. Se isso se repetir durante a janela, o teste não
mede nada. Por isso o critério de interrupção 6 existe, e por isso a janela é curta.

**Risco 4 — o teto real de gasto ainda não está confirmado** (§4). Este é o único
item que eu considero **bloqueador de aprovação**: um teto não confirmado
transformaria a autorização do dono numa autorização de valor desconhecido.

---

## 10. A escada, e onde ela para

```
[✓] fato observado ......... 21 consultas SELECT, 26/08 17:41 BRT
[✓] diagnóstico ............ CONFIRMADA nas duas, por causas distintas
[✓] proposta ............... este documento
[✓] validação local ........ valores conferidos contra a evidência crua
[ ] AUTORIZAÇÃO DO DONO .... ← PARA AQUI
[ ] execução ............... com FORGE_PERMITIR_ESCRITA=1 e destravar() com motivo
[ ] verificação remota ..... releitura dos 2 campos alterados
[ ] acompanhamento ......... 72 h, com os 4 critérios de sucesso
[ ] rollback ............... se qualquer critério de interrupção disparar
```

**O bloqueador de aprovação foi fechado em 26/08/2026:** o teto real de gasto
(§4) tem fonte oficial e vale **R$ 120,00**. Não resta pendência técnica — o que
falta é a decisão do dono.

**Uma condição operacional permanece, e ela é de leitura, não de aprovação:** a
pré-checagem do limite de gasto no nível da conta (§1). Se ele existir e for
menor que R$ 20/dia, este canário não mede o que se propõe a medir, e a
recomendação passa a ser resolver a verificação de anunciante primeiro.

---

## Trilha estrutural — Display

A criação de uma campanha Display segue a esteira própria e **não se mistura com
este plano**: `intenção → blueprint → validação local → validate_only → aprovação
para criar PAUSADA → criação pausada → verificação remota → segunda aprovação →
ativação do canário → observação → expansão gradual` (ADR-21).

Ela depende do construtor de Display, que está sendo escrito nesta mesma rodada, e
de um `validate_only` executado contra a conta real — que **também exige
autorização**, ainda que não crie nada.

**Nunca lançar um lote inteiro como primeiro teste.**
