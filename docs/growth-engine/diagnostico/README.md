# Diagnóstico — as duas campanhas Search da Crédito Up

**Leitura direta da API do Google Ads v25, somente `SELECT`, em 26/08/2026 17:41 BRT**
(`2026-08-26T20:41:57Z`). Conta `8017851692` (Crédito Up), sob o MCC da casa
`6016739364`. Trava de escrita conferida e **fechada** no momento da leitura
(`escrita_permitida: false`). Dados crus em [`evidencia.json`](evidencia.json);
consultas reproduzíveis em [`consultas/`](consultas/).

---

## Veredito da hipótese do CPC de R$ 0,12: **CONFIRMADA** nas duas campanhas

Não por inferência a partir do valor ser baixo, mas porque **o próprio Google diz
isso, em dois campos independentes**, e porque as causas concorrentes foram
testadas uma a uma e todas caíram.

| prova | Maquininha `24155134757` | FGTS `24156373085` |
|---|---|---|
| lance efetivo no leilão | **R$ 0,12** | **R$ 0,12** |
| keywords sinalizadas `AD_GROUP_CRITERION_BELOW_FIRST_PAGE_BID` | **10 de 10 (100%)** | **42 de 81 (52%)** |
| keywords cujo lance cobre a estimativa de 1ª página do Google | **0 de 10 (0%)** | 7 de 49 (14%) |
| `search_rank_lost_impression_share` | **não devolvido** (amostra de 1 impressão) | **0,9001 → ">90%"** |
| `search_budget_lost_impression_share` | **não devolvido** | **0,0 → zero** |
| impressões desde o lançamento (19/08 → 26/08) | **1** | **5** |
| custo | R$ 0,00 de R$ 10,00/dia × 7 dias | R$ 0,00 de R$ 10,00/dia × 7 dias |

A linha decisiva é a da FGTS: **90% da parcela de impressões foi perdida por
CLASSIFICAÇÃO e 0% por ORÇAMENTO.** Não é opinião sobre o lance — é a medição do
Google separando as duas causas possíveis e atribuindo tudo a uma delas.

Na Maquininha essa medição **não existe** (a API não devolveu as parcelas de
impressão: uma impressão em sete dias é amostra insuficiente). Lá a confirmação
vem de outro lugar, igualmente direto: das 10 keywords, **as 10** estão marcadas
pelo Google como abaixo do lance de primeira página, e **nenhuma** das 10
estimativas de primeira página é alcançada por R$ 0,12. A mediana é R$ 2,35 e a
cabeça — "maquininha de cartão" — pede **R$ 15,13**, ou seja, **126× o lance**.

### O que a confirmação NÃO autoriza a dizer

- **Não prova que subir o lance produzirá volume rentável.** Prova que o lance é
  a restrição que hoje impede a entrada no leilão. O CPA que resultará disso é
  outra pergunta, e nenhuma leitura desta conta a responde.
- **Não sustenta nenhuma conclusão sobre CTR, criativo ou landing page.** Com 1 e
  5 impressões, e **zero** clique, não há amostra. `quality_info` veio **não
  devolvido** nas 91 keywords vivas — o Google ainda não atribuiu Índice de
  Qualidade, justamente por falta de entrega.
- **Não descreve o dia de hoje.** Em 26/08 as duas campanhas registram **0
  impressões** até o momento da leitura.

---

## A causa raiz é anterior ao lance: uma alteração manual de 19/08 às 22:39

O `change_event` (janela `LAST_14_DAYS`, 423 eventos, todos de 19/08/2026, autor
único `tarcisio@agenciavolc.com.br`) mostra duas histórias diferentes:

**FGTS `24156373085`** — o motor criou a campanha às 22:26:13 via
`GOOGLE_ADS_API`, pausada, com **lance R$ 1,00** e **orçamento R$ 20,00/dia**.
Treze minutos depois, três alterações consecutivas via `GOOGLE_ADS_WEB_CLIENT`
(o painel, um humano):

```
22:39:13  campaign.status         PAUSED  → ENABLED
22:39:21  budget.amount_micros    R$ 20,00 → R$ 10,00
22:39:45  ad_group.cpc_bid_micros R$ 1,00  → R$ 0,12
```

Vinte e seis segundos depois de ligar a campanha, o lance caiu para 12% do que o
motor havia definido. **A R$ 1,00 o lance cobria 43 das 49 estimativas de
primeira página (88%). A R$ 0,12 passou a cobrir 7 (14%).** Essa única alteração
explica a campanha inteira, e é reversível.

**Maquininha `24155134757`** — nasceu às 13:15:50 já com **R$ 0,12**, o valor
padrão de fábrica do `Brief`, e foi ligada às 13:37:58 pelo painel. **Nunca teve
o lance ajustado.** Aqui não houve alteração humana a reverter: houve um valor de
fábrica que nunca foi revisto e que, para este conjunto de termos, é 20× menor
que a mediana do que o leilão pede.

Em ambos os casos, **nada foi tocado depois de 19/08 22:39:45** — sete dias de
imobilidade confirmados pela ausência de eventos.

---

## Duas correções ao handoff, ambas com evidência

Registradas porque foram pedidas explicitamente, e porque cada uma muda uma
conclusão.

### 1. "Os R$ 0,12 foram decisão manual" vale para a FGTS, **não** para a Maquininha

O `change_event` distingue as duas com clareza:

| | lance no `CREATE` | houve `AD_GROUP UPDATE` de lance? | leitura |
|---|---|---|---|
| **FGTS `24156373085`** | **R$ 1,00** (API, 22:26:13) | **sim** — 22:39:45, `GOOGLE_ADS_WEB_CLIENT` | **decisão manual**, reversível |
| **Maquininha `24155134757`** | **R$ 0,12** (API, 13:15:50) | **não — nenhum** | **valor de nascimento**, nunca revisto |

Na Maquininha o único evento humano foi `PAUSED → ENABLED` às 13:37:58. O lance
saiu da API já em R$ 0,12 e assim permaneceu. A leitura de "default de fábrica
que nunca foi ajustado" **sobrevive para a Maquininha** — o que cai é generalizá-la
para as duas. São causas diferentes com o mesmo sintoma, e por isso as
recomendações também diferem: uma é **reverter**, a outra é **decidir pela
primeira vez**.

### 2. A verificação "7 alcançáveis / 4 entregaram" **não se sustenta**

Refazendo o cruzamento com a chave correta — `(ad_group, criterion_id)`, porque o
`criterion_id` de uma keyword é compartilhado entre campanhas irmãs:

| campanha | keyword que entregou | impressões | estimativa de 1ª página | alcançável a R$ 0,12? |
|---|---|---|---|---|
| Maquininha | maquininha de cartão | 1 | **R$ 15,13** | **não** |
| FGTS | como sacar o saque-aniversário | 2 | R$ 0,92 | não |
| FGTS | fgts saque-aniversário | 1 | R$ 1,20 | não |
| FGTS | como sacar o fgts rescisão | 1 | R$ 0,99 | não |
| FGTS | calendário fgts | 1 | R$ 0,30 | não |

**Das 7 keywords da FGTS alcançáveis a R$ 0,12, nenhuma entregou.** As 5 impressões
das duas campanhas vieram todas de keywords cuja estimativa está **acima** do
lance — e a única impressão da Maquininha veio justamente da mais cara de todas,
a R$ 15,13. A coincidência numérica 7/4 é acaso, não mecanismo.

Isso **não enfraquece o veredito — corrige o modelo**. `first_page_cpc_micros` não
é uma catraca liga/desliga: é o lance estimado para presença *consistente* na
primeira página. Abaixo dele o anúncio ainda aparece esporadicamente, em leilões
rasos ou fora de pico — que é exatamente o padrão observado: **5 impressões em 7
dias, zero clique, zero custo**. A conclusão correta não é "abaixo da estimativa
não entrega nada", e sim **"abaixo da estimativa a entrega é residual e não
acumula volume"** — o que a série diária confirma (4 impressões em 20/08, 1 em
24/08, nenhuma linha em 21, 22, 23 e 26/08).

---

## Índice de Qualidade: não pode ser culpado nem inocentado

`quality_info` veio **não devolvido nas 91 keywords vivas** (10 + 81). O Google
não calcula Índice de Qualidade sem histórico de veiculação, e não há histórico
justamente porque não há entrega. Portanto:

- **não é "Índice de Qualidade ruim"** — é ausência de dado;
- não se pode atribuir a perda por classificação à qualidade, **nem descartá-la**;
- o que fecha o raciocínio é que `first_page_cpc_micros` **já é condicionado à
  qualidade atual** do anúncio. O Google está dizendo "com o anúncio que você tem
  hoje, o lance precisa ser R$ X" — e o lance é 8× a 126× menor que esse X.

---

## Causas concorrentes: todas testadas, todas refutadas

| causa candidata | veredito | evidência literal |
|---|---|---|
| campanha/grupo/anúncio pausado ou removido | **refutada** | `campaign.primary_status = ELIGIBLE` **sem `primary_status_reasons`** nas duas; grupo e anúncio idem |
| anúncio reprovado ou limitado por política | **refutada** | `policy_summary.approval_status = APPROVED`, `review_status = REVIEWED`, `policy_topic_entries` **não devolvido** (vazio) nos 5 anúncios da conta |
| exigência de verificação de serviços financeiros | **refutada** | nenhuma razão de status em campanha, grupo, anúncio ou keyword; e as campanhas **entregaram** 1 e 5 impressões — o que política bloqueada não faria |
| keyword de baixo volume | **refutada** | `system_serving_status = ELIGIBLE` em **263 de 263** keywords; nenhuma `RARELY_SERVED` |
| keyword reprovada | **refutada** | `approval_status = APPROVED` em 263/263; `disapproval_reasons` não devolvido |
| orçamento zerado ou esgotado | **refutada** | R$ 10,00/dia ativo nas duas; **R$ 0,00 gastos** em 7 dias; `search_budget_lost_impression_share = 0,0` na FGTS |
| Smart Bidding sem conversão | **não se aplica** | `bidding_strategy_type = MANUAL_CPC` nas 5 campanhas — não há estratégia automática para travar |
| geo ou idioma incompatível | **refutada** | `LOCATION 2076 = Brazil` (país) e `LANGUAGE 1014 = pt`, ambos `negative: false` |
| rede desligada | **refutada** | `target_google_search: true`, `target_search_network: true` |
| agendamento | **refutada** | **nenhum** `campaign_criterion` do tipo `AD_SCHEDULE` — veiculação 24/7 |
| negativas bloqueando tudo | **refutada** | zero negativas de campanha; `campaign_shared_set` devolveu **0 linhas**; 263/263 keywords com `negative: false` |
| data de término no passado | **refutada** | `campaign.end_date_time` **não devolvido** — sem data de término |
| conta suspensa / faturamento | **refutada** | `customer.status = ENABLED`; `billing_setup.status = APPROVED` desde 04/08/2026 |
| dispositivo excluído | **refutada** | Desktop, HighEndMobile e Tablet todos `ENABLED`, `negative: false`, sem `bid_modifier` |

---

## Achado colateral: a estratégia declarada no brief nunca foi aplicada

As **cinco** campanhas da conta estão em `MANUAL_CPC` com
`enhanced_cpc_enabled: false`, e o `change_event` de criação registra
`manualCpc.enhancedCpcEnabled` entre os campos escritos — ou seja, o motor as
criou assim deliberadamente. Isso importa porque
`volc_ads/briefs/fgts_saque_aniversario.py` documenta em comentário que a
campanha subiria em `MaximizeConversions` e que o lance ali seria ignorado pela
API. **Não foi ignorado: virou o lance real do leilão.**

Segundo achado, este contra o próprio brief: o arquivo declara `cpc_inicial=0.20`,
mas o `change_event` de criação mostra a FGTS nascendo com **R$ 1,00**. O que
está na conta não corresponde ao que está versionado no brief. Investigar o
caminho de código está fora deste escopo — fica registrado como divergência
medida.

Terceiro, cosmético e sem efeito em entrega: duas campanhas carregam o prefixo de
país duplicado, `"BR BR - "`.

---

## Recomendação, em uma frase por campanha

- **FGTS** — reverter a alteração manual de 22:39:45: lance de volta a R$ 1,00
  (cobertura de 14% → 88% das estimativas), mantendo o orçamento em R$ 10,00/dia,
  que a R$ 1,00 comporta ~10 cliques/dia.
- **Maquininha** — subir o lance de fábrica R$ 0,12 para R$ 2,50 (mediana das
  estimativas, cobertura 0% → 50%) **e** decidir sobre os três termos de cabeça
  que pedem de R$ 10,75 a R$ 15,13: a R$ 10,00/dia eles compram menos de um
  clique por dia, e ou o orçamento sobe, ou eles saem do grupo.

Os payloads exatos, com teto de gasto, janela e critério de interrupção, estão em
[`maquininha.md`](maquininha.md) e [`fgts.md`](fgts.md), na seção **MUTAÇÃO
PROPOSTA**. **Nada foi aplicado.**

### O que este diagnóstico se recusa a propor

- **Nenhuma palavra-chave negativa.** `search_term_view` devolveu **2 linhas na
  janela inteira**, ambas com 0 clique. Propor negativa a partir de dois termos
  seria decidir exclusão com uma amostra que não descreve nada. Negativas voltam à
  mesa quando houver relatório de termos real — isto é, depois de haver tráfego.
- **Nenhuma troca de estratégia de lance.** A conta tem `all_conversions = 0.0` em
  todas as ações e o Google devolve `NOT_ENOUGH_CONVERSIONS`; Smart Bidding
  entraria sem sinal. Além disso, mexer em lance e estratégia na mesma janela
  tornaria o resultado inatribuível.
- **Nenhuma reescrita de copy no mesmo lote do lance**, pelo mesmo motivo.

### O rastreio existe e mede — é o que torna defensável comprar tráfego

`conversion_action 7718441216` "adViewInterstitial": `status: ENABLED`,
`primary_for_goal: true`, `include_in_conversions_metric: true`, `WEBPAGE`,
janela de 30 dias. **Está configurada para contar e alimenta a coluna
`conversions`.** Ressalva honesta: ela registra `all_conversions = 0.0` na janela
— está pronta para medir, mas **ainda não mediu nada**, porque não houve clique.
O primeiro ciclo de tráfego é também o primeiro teste real do rastreio.
