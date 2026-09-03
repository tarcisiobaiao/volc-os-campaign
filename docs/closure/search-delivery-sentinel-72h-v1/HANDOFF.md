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
