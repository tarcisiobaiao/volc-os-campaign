# DataForSEO — o que foi medido, não o que a documentação promete

96 chamadas reais, 19 endpoints, **US$ 1,977**, em 14/08/2026, contra os temas
reais da operação (BR, MX, CO, CL, PE, AR, NG, PH). Tudo abaixo é fatura, não
tabela de preço.

Leia junto de `backend/app/motor_pautas/sensores/dataforseo.py`, que já traduz
quatro eixos para o vocabulário fechado do `espaco.py` — **este documento
corrige três premissas que aquele arquivo assume.**

---

## 1 · A armadilha que mataria a carteira

**`keyword_info.cpc` superestima o CPC real em 7,4× (média geométrica).** Medido
termo a termo contra as contas da operação, a BRL/USD 5,4:

| termo | Google Ads real | DataForSEO | razão |
|---|---:|---:|---:|
| `saque aniversario fgts` | US$ 0,0317 | US$ 0,38 | 0,083 |
| `fgts saque aniversario` | US$ 0,0272 | US$ 0,31 | 0,088 |

E o problema **não é escala** — se fosse, bastaria um fator de correção. **A
ordem inverte dentro do próprio cluster:**

```
ordem DataForSEO:  saque aniversario fgts > fgts saque aniversario > fgts > quem tem direito
ordem REAL:        fgts > quem tem direito > saque aniversario fgts > fgts saque aniversario
```

Não é monotônico. Nenhum fator conserta.

**O que funciona:** `ad_traffic_by_keywords` com o lance real. Com `bid=$0,05`
previu `average_cpc` US$ 0,03 = R$ 0,162, contra R$ 0,171 e R$ 0,175 medidos —
**6% de erro**. O simulador de leilão acerta o que o campo estático erra por 7,4×.

> Marcar `medidos={'spread'}` usando `keyword_info.cpc` faz o portão
> `(spread, ruim)` disparar em tema saudável e matar a carteira inteira. É o
> erro exato que `PORTOES_EXIGEM_MEDICAO` existe para impedir — só que com
> aparência de medição.

**A moeda é USD normalizada globalmente, não moeda local.** Teste decisivo:
`seguro de auto` na Argentina (ARS ~1.000/USD) devolveu `cpc 6,07`. Em ARS seria
US$ 0,006, absurdo. Alinha com BR 5,35 · MX 6,29 · CL 6,70 · PE 4,94 · CO 4,30
para o mesmo arquétipo.

---

## 2 · O modelo de custo, fechado

**`custo = US$ 0,012 + US$ 0,00012 × linhas_devolvidas`** — verificado em 5
endpoints Labs diferentes, exato nos 5. Previu US$ 0,03516 para 193 itens; a
fatura veio US$ 0,03516.

Três consequências operacionais:

- **`filters` corta a CONTA**, não só o ruído: é aplicado no servidor antes de
  cobrar. 663 sugestões brutas → 193 com `cpc>0` derruba de US$ 0,0916 para
  US$ 0,03516.
- **A base domina na cauda curta.** Pedir 10 linhas custa quase o mesmo que
  pedir 100. Lotear é a economia inteira.
- **`keywords_data/google_ads/*` cobra US$ 0,09 FLAT por tarefa, de 1 a 1.000
  keywords.** Chamar com uma keyword é o pior uso possível da API.

**SERP: `depth` default é 100 e custa ~US$ 0,0155.** Passar `depth=10` derruba
para US$ 0,0020 — **7,75× mais barato** — e ainda devolve 9 orgânicos, AI
Overview e PAA completos. Esquecer o `depth` multiplica a fatura por 7,75.

**`dataforseo_labs/categories` é gratuito** (custo 0) e devolve as 3.182
categorias num GET. Baixe uma vez, guarde em disco.

---

## 3 · O que arma cada portão

| eixo | fonte que MEDE | arma o portão? |
|---|---|---|
| `volume` | `historical_search_volume` **sobre o cluster**, não a string exata | ✅ |
| `spread` | `ad_traffic_by_keywords` (denominador) **×** RPM do GAM (numerador) | ✅ **só com os dois** |
| `reposicao` | `monthly_searches` dos **últimos 48 meses** | ✅ |
| `formato_consumo` | índice de facilitador na SERP — ver §5 | ✅ |
| `vacuo` | share de domínio oficial + `bulk_traffic_estimation` | proxy-forte |
| `densidade` | setor dos domínios comerciais do top-10 | proxy-forte |
| `opacidade` | nº de órgãos oficiais distintos → só o nível `fragmentada` | parcial |

**Meia razão não é medição.** O DataForSEO dá o CPC; o RPM vem do GAM. Marcar
`medidos={'spread'}` só com DataForSEO é repetir, com dado caro, o erro que o
módulo existe para não cometer.

**Volume tem que ser medido no CLUSTER.** A string exata mata tema bom por
artefato de fraseado: `subsidio de vivienda ds49` devolve **90/mês** na string
exata — o portão `residual` dispararia. O cluster de `saque aniversario fgts`
soma **858.260/mês** contra 74.000 do termo exato (11,6×).

---

## 4 · Buracos silenciosos — coisas que parecem dado e não são

**O Labs perde keyword sem avisar.** `cesantias` (CO 2170 es) não volta: status
20000, sem erro, o item simplesmente não está no array e `items_count` vem menor.
Reproduzido em duas chamadas. O Google Ads tem `cesantias` com **40.500/mês**.
Quem não comparar o pedido contra o devolvido trata buraco de base como volume
zero e mata tema vivo.

**`cpc: null` não é dado faltando — é ausência de leilão**, e é uma categoria que
o `espaco.py` não tem. Metade das keywords de `2ª via IPTU` onde `direito2.com.br`
ranqueia tem `cpc null` com 390 a 2.900 buscas/mês: demanda real, zero anunciante.
No México é a regra — 32 de 32 termos de forma de pergunta com volume e CPC nulo.

**`bulk_keyword_difficulty` devolve `null` silenciosamente** na cauda longa —
9 de 18 keywords BR. Mesmo buraco em `keyword_info.cpc` (null em 15 de 25).

**Histórico profundo PIORA a sazonalidade.** 2020–2021 quebrou a fase de metade
dos temas de coorte. `enem` sobre 92 meses dá R²=0,41 e sai classificado como
`continua`; sobre os últimos 48 meses dá R²=0,76 e sai `anual`. Use 48 meses.

**A profundidade do histórico varia por keyword** — 92 meses é típico, mas
`inscricao enem` tem 62 e `extrato fgts` tem 100. Nunca assuma janela fixa: leia
o primeiro mês devolvido.

---

## 5 · Dois achados que refutam premissas nossas

**`formato_consumo` é medível — e é por TEMA, não por país.**

Critério: sobre os domínios **únicos** do top-10,
`(facilitador + social) / únicos ≥ 0,40` **e** `oficial ≤ 0,30`. Separou 15 de 15
casos e acende só em NG-nin (0,86/0,29), NG-cac (0,50/0,20), PH-nbi (0,86/0,14).

**A variação intra-Nigéria é maior que a variação BR↔NG.** Isso contraria o
comentário do `espaco.py` ("decisão de PAÍS, não de tema") e contraria o desenho
do `prompts/classificador_eixos.md`, que decide o eixo uma vez na ETAPA A e
proíbe divergência entre itens do mesmo país. **Essa trava está errada.**

**Os zeros à esquerda do histórico são a data de nascimento da entidade, e são
exatos.** `novo rg cin` tem 32 zeros e acende em 2022-04 — o mês em que a CIN foi
criada. `saque aniversario fgts` tem 8 zeros e acende em 2019-07 — o mês da MP do
saque-aniversário. É sinal gratuito para `vacuo`: entidade recém-nascida não teve
tempo de ser explicada por ninguém.

---

## 6 · O que descartar, e por quê

| descartar | motivo medido |
|---|---|
| `serp/.../live/regular` | **não é mais barato**: US$ 0,0035, idêntico ao `advanced`, e devolve 9 campos por orgânico contra 34, com zero blocos SERP |
| `keyword_ideas` para MEDIR o tema | expande **categoria**, não frase. Partindo de `saque aniversario fgts` o topo por volume é `calculadora` (7,48M). Serve como firehose de descoberta, nunca como medida da semente |
| `bulk_keyword_difficulty` | cego no único regime que interessa — `null` em 50% da cauda longa |
| `search_intent` como endpoint próprio | o rótulo já vem de graça em `search_intent_info` dentro do `keyword_suggestions` |
| `keyword_overview` | dominado pelo `historical_search_volume` — mesma fórmula de preço, e este devolve 92-100 meses a mais |
| `keywords_for_site` | reordena o conjunto e produz lixo com cara de dado pelo mesmo preço do `ranked_keywords` |
| `serp/google/ads_advertisers` | casa pelo **nome** do anunciante — mede quem se batizou com o termo, não quem dá lance |
| `metrics.paid.*` | veio **zero** nos quatro portais da operação, que compram Google Ads diariamente |
| `high_top_of_page_bid` como proxy de CPC | `licencia de conducir cdmx` deu `cpc 0,32` com `high 57,26` — 179× acima |
| **ETV como régua de receita** | é volume × CTR-modelo da posição. 83% do ETV de `direito2.com.br` (19.514 de 23.549) vem de **uma página em #38** numa keyword de 9,14M/mês, onde o CTR real é ~0 |
| Toda a família Labs para espionar portal de arbitragem puro | a base é orgânica. `portalmundomais.com` devolveu 53 concorrentes com 1 interseção cada, todas acidentes (flixbus, sptrans) |

**E o mais contraintuitivo:** a interseção entre dois portais vencedores é
evidência de **derrota compartilhada**, não de tema provado. Nas 239 keywords que
`direito2` e `pautasocial` dividem, os dois ranqueiam entre a posição 50 e a 95 —
em nenhuma delas algum dos dois chega ao top-20. Lido ingenuamente, isso marcaria
`vacuo` como disputado quando o campo está vazio.

---

## 7 · Correções a observações anteriores desta mesma sessão

**"Zero anúncios pagos nas SERPs" era artefato.** `paid` deu 0 em 20 de 20 SERPs,
inclusive em `car insurance` nos EUA — a keyword mais disputada do mundo. O
endpoint orgânico não entrega anúncio, ponto. Não é um fato sobre os mercados.

**"AI Overview em 100%" era amostra pequena.** Real: **11 de 15 (73%)**. Por
país: BR 3/4 · MX **0/2** · CL 1/1 · CO 1/1 · PE 1/1 · NG 3/3 · PH 2/2 · US 0/1.
As quatro ausências são todas consultas navegacionais (app, portal de login,
agendamento) — o AIO só aparece quando a pergunta é explicativa.

**O contador de gasto de `/tmp/dfs_gastos.jsonl` é compartilhado entre processos
paralelos.** O delta de `gasto_total()` reportou 8× a 25× o consumo próprio de
cada sonda. Custo tem que vir de `tasks[0].cost`, chamada a chamada.

---

## Economia do funil

| | |
|---|---|
| candidato que morre cedo (histórico em lote + SERP) | **US$ 0,0034** |
| onda de 100 candidatos, do zero ao veredito | **US$ 4,85** → ~13 aprovados |
| **por tema que sai vivo** | **US$ 0,37** |

78% da fatura está em dois nós de US$ 0,09 que só tocam finalistas
(`keywords_for_keywords` e `ad_traffic_by_keywords`). Tudo antes deles custa
centavos — o funil existe para que o tema morra antes de chegar lá.

O JSON integral das 96 medições, com payload mínimo por endpoint, está em
`/tmp/dfs_result.json` desta sessão.
