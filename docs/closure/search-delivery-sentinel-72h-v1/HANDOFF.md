# Search Delivery Sentinel + Guardião 72h — v1

**Branch:** `sprint/search-delivery-sentinel-72h-v1`
**Base:** `origin/volc-os-v2` @ `34dc7b41bce901bd8bebfdec0a01e293678cbf08` (SHA conferido, idêntico ao esperado)
**Worktree:** `/private/tmp/volc-search-delivery-sentinel-72h-v1`
**Data:** 03/09/2026

---

## 1. O defeito central, reproduzido antes de qualquer conserto

O diagnóstico persistido v12 nunca preenchia o degrau `conta`. Não por falha de
leitura: **não existia caminho de payload para `customer.status`**, e nenhuma
consulta do VOLC-OS pedia esse campo.

Como `conta` é o **primeiro** eixo da ordem causal, o efeito atravessava o
sistema inteiro. Provado executando o `escada.ts` real contra a saída real do
backend:

```
vereditoDaEscada(degraus)   →  { tipo: 'nao_apurado', eixo: 'conta' }
degrausConfiaveis(...)      →  { confiaveis: [], suspensos: [9 degraus] }
```

**Toda campanha** — saudável, pausada, suspensa — abria a página canônica com
*"Não foi possível apurar — parou em conta"*. A escada inteira era leitura
suspensa permanente: a tela nunca mentia de verde porque nunca diagnosticava
nada. Uma conta suspensa por política era indistinguível de uma falha nossa.

Rodando o cenário Crédito Up contra `34dc7b4`:

```
conta        nao_apurado  "A coleta v12 não trouxe evidência suficiente"
campanha     ok           "ligada sem bloqueio nestes campos"
keyword      ok           "A conta observou keyword habilitado"   ← FALSO VERDE
leilao       limita       "A conta mediu zero impressões"
```

As keywords tinham lance de R$ 0,50 contra estimativa de primeira página de
R$ 3,20 e Quality Score 3. Os três números **estavam no payload** —
`effective_cpc_bid_micros`, `position_estimates.first_page_cpc_micros` e
`quality_info.quality_score` atravessam a allowlist de `CAMINHOS_ITEM` desde a
v12 — e nenhum deles era lido. O degrau saía `ok` porque `primary_status` dizia
`ELIGIBLE`, que é verdade e não é a pergunta: elegível quer dizer *pode* ir a
leilão, não *vai*.

---

## 2. Os oito falsos verdes corrigidos

| # | Onde | O input que produzia o erro | O resultado errado |
|---|---|---|---|
| 1 | `diagnostico_persistido._degraus_observados` | conta `SUSPENDED` | `conta: nao_apurado` para sempre — não havia campo |
| 2 | idem | `budget_lost=0.00`, `rank_lost=0.90` | `orcamento: ok, "zero de perda por orçamento"`, e **nenhum degrau mencionava rank** |
| 3 | idem | `ENABLED` + `MISCONFIGURED` + `SUSPENDED` | `impedimento: "primary_status e serving_status ausentes"` — factualmente falso, os dois vieram |
| 4 | idem | `approval_status=DISAPPROVED` | `anuncio: ok, "presente"` sobre anúncio reprovado |
| 5 | idem | keyword `ELIGIBLE`, lance 0,50 vs 3,20 | `keyword: ok, "presente"` |
| 6 | idem | `estado_coleta="parcial"` | degraus continuavam `ok`, afirmando sobre o que não foi lido |
| 7 | `SupabaseRepositorioDiagnostico` | campanha com > 1000 itens | `select` truncava em silêncio; um anúncio elegível na primeira página pintava de verde 500 reprovados depois da linha 1000 |
| 8 | `useAtencao.estadoDoSino` | `quantos=0` + `parcial=true` | check verde "Nenhuma condição ativa" sobre lista incompleta |

`select_all` (paginado) **já existia** em `supabase_service.py:80-102` e não era
chamado. `search_rank_lost_impression_share` e `policy_summary.approval_status`
**já estavam na allowlist** e não eram lidos.

---

## 3. O modelo de estados

`backend/app/trafego/sentinela.py` — domínio puro, sem rede, sem SDK, sem I/O.

### Precedência causal (`PRECEDENCIA`, 16 posições)

```
 1 ACCOUNT_BLOCKED         crítica       conta suspensa/cancelada/encerrada
 2 ACCESS_UNAVAILABLE      crítica       a conta recusou a leitura
 3 POLICY_BLOCKED          crítica       destino/anúncio/keyword reprovado
 4 POLICY_REVIEW           média         o Google ainda não decidiu
 5 DATA_UNAVAILABLE        média         falhou, velho, ausente ou nunca lido
 6 CAMPAIGN_OFF            informativa   desligada por decisão — NÃO é incidente
 7 ADS_NOT_READY           alta          sem anúncio apto o leilão não começa
 8 NO_DELIVERY             alta          ligada, madura, fresca, zero impressões
 9 LIMITED_BY_BUDGET       média         perda de IS por orçamento MEDIDA
10 LIMITED_BY_RANK         média         lance abaixo da 1ª página / rank lost
11 KEYWORD_STRUCTURE_RISK  baixa         redundância, baixa qualidade, rara
12 MEASUREMENT_NOT_READY   média         Smart Bidding sem conversão medida
13 LOW_DEMAND              baixa
14 LEARNING                informativa
15 OBSERVING               informativa   janela imatura — ausência de conclusão
16 HEALTHY                 informativa   alcançável só com prova COMPLETA
```

**`CAMPAIGN_OFF` não está na lista sugerida pela missão e é necessário.**
"Campanha PAUSED com zero gasto não é falha" é regra invariante, e sem um estado
próprio ela teria de sair `HEALTHY` (falso verde) ou `NO_DELIVERY` (falso
alarme) — os dois proibidos pelo nome. É a conversão direta do
`campanha/bloqueia/desligada` que o projeto já emitia.

**`DATA_UNAVAILABLE` acima de `NO_DELIVERY`** porque coleta velha com zero
métricas é desconhecimento, não ausência de entrega. **`OBSERVING` no fim**
porque ele é a ausência de conclusão madura, não uma conclusão — são duas coisas
diferentes, e a missão exige os quatro estados de ausência separados.

`ordem_da_causa` manda status desconhecido para o **fim**, nunca para o topo:
quem trata o desconhecido é `evidencia_dubia`, no lugar certo da ordem.

### Vocabulário: convertido, não duplicado

`CONVERSAO_DO_EIXO` mapeia os 9 eixos existentes (`conta`…`leilao`) para os 7
escopos da sentinela. A escada, `EstadoDoDegrau`, `EstadoDaColeta` e
`FrescorDoDiagnostico` permanecem intactos — a sentinela **lê** o que eles
produzem e responde a pergunta que eles não respondem: *qual causa manda, e o
que fazer agora*.

---

## 4. As janelas do guardião 72h

`PoliticaDoGuardiao` — versionada, justificada e configurável. Nenhum número é
universal, e é por isso que são um objeto e não constantes soltas.

| janela | quando | madura? |
|---|---|---|
| `nascimento` | < 6h (carência) | não |
| `ate_24h` | 6h – 24h | não |
| `24_72h` | 24h – 72h | **sim** |
| `apos_72h` | > 72h | **sim** |
| `indeterminada` | idade desconhecida ou `NaN` | **não** |

`horas_para_incidente = 24` é o **mesmo** `dominio.HORAS_ATE_ALERTAR` que o sino
já usa. Divergir faria a mesma campanha aparecer no sino e não na sentinela, sem
resposta certa entre as duas telas.

`indeterminada` não é uma janela: é a confissão de que não sabemos a idade.
`horas_ligada=None` **não vira zero**, e `NaN` também não vira "madura" — toda
comparação com `NaN` é falsa, e sem o guarda a cascata caía em `apos_72h`.

---

## 5. Sinais Google consumidos

| sinal | de onde | estado |
|---|---|---|
| `customer.status` | **coletor estendido** | novo — era o campo que faltava |
| `customer_conversion_goal.*` | **coletor estendido** | novo |
| `campaign.status/primary_status/reasons/serving_status` | já coletado | agora com `MISCONFIGURED`/`SUSPENDED` reconhecidos |
| `campaign_budget.amount_micros` | já coletado | lido |
| `metrics.*` (8 métricas) | já coletado | `search_rank_lost_impression_share` agora **lido** |
| `ad_group_criterion.effective_cpc_bid_micros` | já coletado | agora **lido** |
| `…position_estimates.first_page_cpc_micros` | já coletado | agora **lido** |
| `…quality_info.quality_score` | já coletado | agora **lido** |
| `…primary_status_reasons` | já coletado | agora **lido**, com nomes conferidos no SDK |
| `ad_group_ad.policy_summary.approval_status/review_status` | já coletado | agora **lido** |
| `recommendation.*` | já coletado | agora **adjudicado**, nunca aplicado |
| `ad_group_criterion` (estrutura, **sem data**) | **coletor estendido** | novo — separa inventário de desempenho |

### Sem migration

`customer.status` e as metas viajam **dentro** do documento `DIAGNOSTICO_ENTREGA`
que já existe, como `tipo_item` novos (`account`, `conversion_goal`). O CHECK de
`tipo_item` na `v12_01` é `btrim(tipo_item) <> ''` — **aberto de propósito** —
enquanto o de `tipo_sinal` é fechado em doze valores e `DIAGNOSTICO_ENTREGA` é um
deles. Nenhuma migration foi criada, proposta ou aplicada.

---

## 6. Alertas e idempotência

`chave_do_incidente = sha256(customer_id | volc_campaign_id | escopo | status)[:32]`

**A janela NÃO entra na chave.** Duas leituras da mesma condição em janelas
diferentes são o mesmo incidente continuando; incluir a janela criaria um
incidente novo a cada coleta e inundaria o operador com o mesmo fato. A janela
viaja em `ultima_janela`, onde informa sem fragmentar a identidade.

`consolidar(anteriores, atuais, quando)` — função pura, quatro transições:

- **repetição** → `primeira_vez_em` preservado, `ocorrencias` sobe;
- **resolução** → ganha `resolvido_em`; sumir apagaria a prova de que existiu;
- **reabertura** → `primeira_vez_em` do original mantido, `reaberturas` sobe;
- **nova** → entra como está.

O reconhecimento atravessa a repetição (quem já disse "estou ciente" não repete
a cada coleta) e **não** atravessa a reabertura (problema que voltou é fato novo,
e presumir ciência seria silenciar o alerta em nome do conforto).

Reuso de armazenamento: nenhuma tabela nova. O incidente é derivado do ledger
append-only que já existe.

---

## 7. Superfície operacional

- `GET /api/trafego/campanhas/{id}/diagnostico` — envelope **v2**, com
  `sentinela` servida pelo backend;
- `CampanhaCanonPage` — o veredito **acima** da escada, com severidade, idade,
  frescor, janela, estado da prova, evidência, causas secundárias com
  denominador, desconhecidos, recomendações adjudicadas e próximo ato;
- **declaração explícita, em texto, de que nenhuma alteração foi aplicada** —
  o operador lê, em vez de deduzir da ausência de um botão;
- sino: sexto estado `lista_incompleta`, com rótulo acessível coerente.

Verde exige **três** condições: `HEALTHY` + evidência `apurada` + frescor
`recente`. Servidor sem o campo → a tela diz que não recebeu veredito; não
desenha saúde.

---

## 8. Um defeito desta lane, cometido e consertado dentro dela

O recibo de destino não consultado saía como `ausente`. Como `ausente` **é**
causa (`DATA_UNAVAILABLE`, posição 5) e `OBSERVING` está na 15, **toda** campanha
passou a ter o destino como causa primária — uma campanha recém-criada em
carência saía `DATA_UNAVAILABLE@destination` em vez de `OBSERVING`.

Era o mesmo defeito do eixo `conta`, com outra roupa: um degrau que ninguém
preenche sequestrando o veredito de todas as campanhas. `nao_consultado` e
`ausente` agora são fatos diferentes — o primeiro vai para `desconhecidos` e
rebaixa a evidência; o segundo é causa.

---

## 9. Cinco nomes de enum inventados, encontrados e fixados

A revisão factual (contra o **descriptor protobuf do SDK instalado**, não contra
documentação nem memória) encontrou nomes que não existem na v25:

```
AD_GROUP_CRITERION_LOW_QUALITY_SCORE   → o real é ..._LOW_QUALITY
BELOW_FIRST_PAGE_BID                   → o real é AD_GROUP_CRITERION_BELOW_FIRST_PAGE_BID
AD_GROUP_CRITERION_LOW_SEARCH_VOLUME   → não existe
AD_GROUP_CRITERION_POLICY_DISAPPROVED  → o real é ..._DISAPPROVED
REVIEWED_AND_PENDING                   → o real é ELIGIBLE_MAY_SERVE
NOT_STARTED (campanha)                 → o real é PENDING
```

Um nome inventado é o defeito mais silencioso possível: não quebra, não avisa,
não aparece em teste — ele simplesmente **nunca casa**, e a causa some.

`test_trafego_sentinela_vocabulario.py` fixa cada conjunto no descriptor. O
guarda foi **provado**: reintroduzindo o nome errado a suíte falha com a mensagem
exata, e volta a passar ao reverter.

A leitura real confirmou a correção do jeito mais direto possível: o Google
devolveu `AD_GROUP_CRITERION_BELOW_FIRST_PAGE_BID` em 10 de 10 keywords. Com o
nome da primeira versão, isso teria casado **zero**.

---

## 10. Revisão adversarial

**Codex `gpt-5.6-sol`, esforço high, read-only, uma rodada.** Doze achados,
todos com contraprova executada. Veredito: **REJEITAR**. Todos corrigidos, com
18 regressões novas usando o input exato do revisor. Detalhe em `CONTRAPROVAS.md`.

Três deles eram o defeito central desta lane, repetido:
- `KW_EM_REVISAO` criado, verificado e **nunca consultado** (o mesmo que
  `first_page_cpc_micros`);
- anúncio apto definido como "ausência de reprovação" em vez de aprovação lida;
- um `return` fazendo a **ordem de avaliação** decidir o veredito, quando quem
  decide é `PRECEDENCIA`.

**Gemini: `NOT_AVAILABLE`** (exit 41, sem método de auth configurado). Registrado
em menos de cinco minutos; CLI/auth **não** foram consertados, conforme a missão.
A revisão factual foi feita contra o descriptor do SDK — evidência de primeira
mão, melhor que a memória de um modelo.

---

## 11. Leitura real

Ver `REAL-READ-SUMMARY.json`. Somente-leitura, pseudonimizada, gate de não
mutação verde antes e depois, zero mutações.

O resultado confirma o incidente na conta viva: `customer.status = SUSPENDED`,
invisível ao filtro `status='ENABLED'` de `contas.py`, com 2 campanhas Search
respondendo `ENABLED/ELIGIBLE/SERVING`, 9 impressões e R$ 0,00 em 7 dias, e
10 de 10 keywords declaradas abaixo do lance de primeira página pelo próprio
Google. O veredito da sentinela sobre esse dado real:
**`ACCOUNT_BLOCKED` / crítica / account**, com o lance como causa secundária
quantificada.

---

## 12. O que NÃO foi feito

- **Nenhuma mutação Google Ads.** Zero `mutate`, `apply`, `dismiss`, `upload`,
  `create`, `update`, `remove`. Provado por AST sobre o módulo, pelo
  `gate_sem_mutacao_google.py` e pela leitura real com a trava fechada.
- Nenhuma migration criada, proposta ou aplicada.
- Nenhuma escrita no Supabase.
- Roadmap, curadoria e grafo: **apenas handoff proposto**, em
  `CURATION-HANDOFF.json`. Nenhum deles foi editado.
- `backend/app/landing_policy/**`, FunnelForge, WordPress, n8n, Data Manager,
  Harness V3: **não tocados**.
- Nenhum push, merge ou deploy.

---

## 13. Handoff para outra frente

**`backend/app/trafego/contas.py` está FORA do ownership desta lane e tem o
defeito gêmeo.** Ver `CURATION-HANDOFF.json` → `handoffs[0]`.

```sql
-- GAQL_CLIENTES, linha 54
WHERE customer_client.status = 'ENABLED'
```

Uma conta suspensa **desaparece** da descoberta, sem linha e sem explicação — o
próprio docstring do arquivo diz que esconder uma conta "faria uma conta sumir
da lista sem explicação e ninguém saberia por quê", e é exatamente o que a
cláusula faz. E `GAQL_CONTA` não seleciona `customer.status`.

Medido na conta real: **2 de 4 contas sob o MCC são invisíveis a esse filtro.**

Esta lane não tocou o arquivo. A sentinela contorna coletando `customer.status`
por conta própria dentro de `volc_ads/inteligencia_google/**`, que é ownership
dela — mas a lista de contas do produto continua cega.

---

## 14. Veredito da lane

**`LOCAL_CLOSURE_ACCEPTED`**, com as ressalvas da seção 15 declaradas.

Os catorze critérios de aceite, um a um:

| # | critério | prova |
|---|---|---|
| 1 | status suspenso vence diagnóstico inferior | `test_01`, `test_11c`, `test_r07`, `test_p01` — e a leitura real |
| 2 | campanha pausada não gera falso alerta | `test_02`, `test_02b` |
| 3 | habilitada e madura sem entrega gera incidente | `test_04`; `test_03*` provam que a imatura **não** gera |
| 4 | frescor e ausência tratados honestamente | `test_05*`, `test_06*`, `test_r04b`, `test_p14` |
| 5 | keywords limitadas com denominador e evidência | `test_07`, `test_08`, `test_r09`, `test_r15b` |
| 6 | redundância agrupada sem inventar intenção | `test_20*` — `credito consignado` ≠ `credito pessoal` |
| 7 | recomendações coletadas e adjudicadas, nunca aplicadas | `test_15`, `test_r01`, `test_r06`, `test_p10`–`12` |
| 8 | o QG mostra o incidente e o próximo ato | `veredito-da-sentinela.test.tsx`, `diagnostico-na-pagina.test.tsx` |
| 9 | alertas idempotentes e resolvíveis | `test_13*`, `test_14*` |
| 10 | nenhum método mutável alcançável | `test_16` (AST), `gate_sem_mutacao_google` 3/3, leitura real com trava fechada |
| 11 | gates verdes ou diferenças herdadas provadas | `GATES.md` — 76 erros de tsc herdados, zero novos |
| 12 | árvore limpa | `git status --porcelain` vazio |
| 13 | Roadmap/curadoria/grafo só com handoff proposto | `CURATION-HANDOFF.json`; nenhum dos três editado |
| 14 | nenhuma mutação externa | seção 12 |

**Por que não `PARTIAL`:** o critério de rebaixamento da missão é *"se o backend
ficar pronto mas a informação não aparecer na superfície operacional"*. Ela
aparece: a página canônica abre com o veredito, o sino parou de mentir, e as
duas coisas têm prova de tela.

---

## 15. Ressalvas honestas

Nada abaixo invalida o aceite, e nada abaixo deveria ser esquecido.

1. **`consolidar()` é função pura sem chamador.** A idempotência está
   implementada e provada; nenhuma rotina de produção a invoca ainda. O
   incidente ainda não é persistido nem exibido em fila.
2. **`horas_ligada` é opcional no repositório.** Sem `transicoes()`, a janela do
   guardião sai `indeterminada` — foi o que aconteceu na leitura real. A
   sentinela é honesta a respeito, mas o guardião 72h só opera plenamente quando
   o diário for ligado.
3. **A fila de atenção ainda não consome o veredito.** Ela projeta o sintoma do
   inventário; a página canônica e o sino foram integrados, a fila não.
4. **`keyword_view` + `segments.date`** continua apagando a keyword que nunca
   serviu na janela, e `keyword_count` é gravado como MEDIDO sobre um
   subconjunto enviesado. Reproduzido pela recon, **não** por contraprova
   executável desta lane — e por isso foi para handoff, não para conserto: a
   missão exige achado reproduzido antes de correção.
5. **`backend/app/trafego/contas.py` continua cego** a contas suspensas. Fora do
   ownership; handoff exato na seção 13, com a medida real (2 de 4 contas).
6. **A causa da suspensão não foi estabelecida** e não deveria ser: segue
   `HYPOTHESIS_PARTIALLY_SUPPORTED`.

---

## 16. Nota de método

Três defeitos meus estão registrados no histórico em vez de apagados dele,
porque o padrão que eles formam é a informação mais útil deste pacote:

- **`test_16` na primeira versão** varria o texto do arquivo e falhava por causa
  do próprio docblock. Um teste que não distingue código de comentário não prova
  nada sobre o que o módulo executa;
- **cinco nomes de enum escritos de memória** — encontrados só porque a
  conferência foi feita contra o descriptor do SDK, e não contra a lembrança de
  ninguém. Um nome inventado nunca casa, e a causa some em silêncio;
- **o `else` que afirma uma falta inexistente** — corrigido no eixo `campanha`
  na primeira rodada, com um comentário explicando por que era errado, e
  **cometido de novo** no eixo da keyword logo depois. A revisão adversarial o
  pegou.

O denominador comum dos três é o mesmo defeito que esta lane existe para
consertar: **afirmar mais do que a evidência sustenta.** A diferença entre a
versão inicial e a final não foi conhecimento — foi conferir.

Duas medições de baseline também foram descartadas por método (`GATES.md`), e um
`git stash pop` acidental trouxe um backup da branch `main`; o pop conflitou,
portanto não apagou nada, a árvore foi restaurada ao HEAD sem perda e o backup
alheio segue intacto. Registrado porque worktrees compartilham a lista de stash,
e isso não é óbvio.


---

## 17. Rodada corretiva — dois bloqueantes da avaliação independente

Reproduzidos contra `98c66da` antes de qualquer conserto.

### BLOQUEANTE 1 — `TARGET_IMPRESSION_SHARE`

`ESTRATEGIAS_SMART_BIDDING` incluía TIS, e `_causas_da_medicao` afirmava que
essa estratégia depende de conversão medida. **É factualmente errado:** TIS
otimiza participação e posição de impressão, não conversões.

TIS **é** lance automático, e era exatamente isso que o nome antigo escondia —
"smart bidding" agrupa por *automação*, e a pergunta certa é outra: **a
estratégia otimiza CONTRA um sinal de conversão?** O conjunto foi renomeado para
`ESTRATEGIAS_DEPENDENTES_DE_CONVERSAO`, que é o critério de fato, e TIS saiu.
`MAXIMIZE_CONVERSIONS`, `MAXIMIZE_CONVERSION_VALUE`, `TARGET_CPA` e
`TARGET_ROAS` continuam dentro.

Reprodução: TIS + `NAO_PRONTO` → `MEASUREMENT_NOT_READY`. Agora: `HEALTHY`.

### BLOQUEANTE 2 — `keyword_view` vazia lida como "zero keywords"

`keyword_view` com `segments.date` só devolve linha para keyword que **teve
métrica na janela**. Zero linhas viravam `NO_DELIVERY@keyword` — uma afirmação
sobre **configuração** feita a partir de uma consulta sobre **desempenho**.

Reprodução: campanha `ENABLED`, `horas_ligada=1`, janela `nascimento`,
`impressions=0`, `keyword_view` vazia → `NO_DELIVERY / keyword / nascimento`.
Falso alarme dentro da própria carência do guardião.

**Correção preferida aplicada, não o mínimo conservador:**

| | antes | agora |
|---|---|---|
| estrutura | `keyword_view` + `segments.date` | `ad_group_criterion`, `type='KEYWORD'`, **sem data** |
| métrica | mesma consulta | `keyword_view` na janela |
| correlação | — | por `criterion_id` |
| `keyword_count` | linhas da janela, gravado como MEDIDO | total **estrutural** |
| afirmar "zero keywords" | qualquer zero | só com `estrutura_de_keywords_apurada = true` |

O payload da coleta passou a declarar `estrutura_de_keywords_apurada`, e
`COLUNAS_COLETA` lê **esse único campo** do payload. `None` de uma coleta antiga
**não é `False`**: ela não afirma que o inventário falhou, apenas não sabe dizer.

Sem prova estrutural: janela imatura → **nenhuma** causa de keyword (`OBSERVING`
da campanha prevalece); janela madura → `DATA_UNAVAILABLE@keyword`. Em ambos, o
não-apurado vai para `desconhecidos` e rebaixa a evidência sozinho.

Isto fecha o item 4 do handoff da seção 13 e a ressalva 4 da seção 15 — que
estavam em backlog por falta de contraprova executável. A avaliação independente
forneceu o cenário, e com ele o conserto passou a caber no método.

### Gates da rodada corretiva

```
pytest backend/tests volc_ads -q   3937 -> 3951 passed, 97 skipped (0 failed)
focais frontend                    6 arquivos, 81 provas, 0 failed
tsc                                76 herdados, zero novos
gate_sem_mutacao_google            exit 0
verificar_segredos                 limpo
git diff --check                   limpo
```

Suíte completa executada porque a mudança cruza contratos compartilhados
(`COLUNAS_COLETA` e as consultas do coletor).
