# Contraprovas — Search Delivery Sentinel + Guardião 72h

Toda contraprova abaixo **nasceu vermelha** contra `34dc7b4`. Nenhuma foi
escrita depois do conserto para descrevê-lo.

Fixtures **sintéticas**: `9990001111` não corresponde a conta alguma, e
`test_r12` falha se um identificador operacional real aparecer em qualquer
arquivo desta lane.

```
backend/tests/test_trafego_sentinela.py              100 provas
backend/tests/test_trafego_sentinela_vocabulario.py   17 provas
backend/tests/test_google_inteligencia_persistente.py  +5 provas
src/components/trafego/diagnostico/__tests__/veredito-da-sentinela.test.tsx  20
src/components/layout/__tests__/sino-de-alertas.test.tsx  +7
src/pages/trafego/__tests__/diagnostico-na-pagina.test.tsx +2
```

---

## As 18 contraprovas exigidas pela missão

| # | exigência | prova | veredito |
|---|---|---|---|
| 1 | Conta suspensa + keywords limitadas → suspensão vence | `test_01_conta_suspensa_vence_keywords_limitadas` | `ACCOUNT_BLOCKED`; lance vira secundária |
| 2 | Conta ok + campanha pausada + zero gasto → sem `NO_DELIVERY` | `test_02`, `test_02b` | `CAMPAIGN_OFF`, não-incidente; o lance é calado |
| 3 | Recém-criada na carência → `OBSERVING` | `test_03`, `03b`, `03c`, `03d` | `OBSERVING`, janela `nascimento` |
| 4 | Madura, fresca, zero impressões → `NO_DELIVERY` | `test_04`, `04b` | `NO_DELIVERY`; idade desconhecida NÃO gera incidente |
| 5 | Coleta velha + zero métricas → `DATA_UNAVAILABLE` | `test_05`, `05b`, `05c` | nunca `NO_DELIVERY` |
| 6 | Falha na coleta de recomendações ≠ zero | `test_06`, `06b`, `06c` | `itens: None`, `quantidade: None` |
| 7 | 100% abaixo da 1ª página → causa com denominador | `test_07`, `07b` | "3 de 3 (100%)"; percentual sem denominador é recusado |
| 8 | Keyword sem dado fora do denominador medido | `test_08` | denominador 2, `fora_da_conta: 2` |
| 9 | Nenhum anúncio apto vem antes do lance | `test_09`, `09b` | `ADS_NOT_READY` < `LIMITED_BY_RANK` na precedência |
| 10 | Policy review não afirma aprovado nem reprovado | `test_10`, `10b` | `POLICY_REVIEW`, severidade média |
| 11 | Destination receipt ausente | `test_11`, `11b`, `11c` | ausência ≠ aprovação; conta suspensa ainda vence |
| 12 | Smart Bidding sem conversion goal | `test_12`, `12b`, `12c` | `MEASUREMENT_NOT_READY`; `MANUAL_CPC` não gera alarme |
| 13 | Duas leituras iguais → um incidente | `test_13`, `13b`, `13c` | mesma chave apesar de janelas diferentes |
| 14 | Resolvido e recorrente reabre com histórico | `test_14`, `14b`, `14c` | `primeira_vez_em` original preservado |
| 15 | Recomendação registrada, nunca aplicada | `test_15`, `15b` | `aplicada: false` |
| 16 | Nenhum método mutável alcançável | `test_16` | **prova por AST**, não por busca de texto |
| 17 | Saudável com evidência fresca → `HEALTHY` | `test_17`, `17b` | prova parcial nunca sai `HEALTHY` |
| 18 | Enum futuro/desconhecido → falha conservadora | `test_18`, `18b`, `18c` | `DATA_UNAVAILABLE`, nunca verde |

`test_16` merece nota: a primeira versão varria o **texto** do arquivo e falhava
por causa do próprio docblock, que cita `google.ads` para dizer que não o
importa. Um teste que não distingue código de comentário não prova nada sobre o
que o módulo executa. A versão final percorre a **árvore sintática**.

---

## As contraprovas do diagnóstico persistido (`test_p*`)

Os falsos verdes medidos, cada um com o input exato:

| prova | input | antes | depois |
|---|---|---|---|
| `test_p01` | conta `SUSPENDED` | `conta: nao_apurado` | `conta: bloqueia` |
| `test_p01b` | conta `ENABLED` | escada suspensa permanentemente | `conta: ok` |
| `test_p02` | `budget_lost=0.00`, `rank_lost=0.90` | `orcamento: ok` calado sobre rank | aponta o leilão; rank vira evidência |
| `test_p03` | `ENABLED`+`MISCONFIGURED`+`SUSPENDED` | `impedimento` factualmente falso | `bloqueia`, sem impedimento inventado |
| `test_p03b` | `HIBERNATING` | — | `nao_apurado`, nomeia o valor |
| `test_p04` | `approval_status=DISAPPROVED` | `anuncio: ok, presente` | `bloqueia` |
| `test_p04b` | `APPROVED_LIMITED` | verde | `limita` |
| `test_p04c` | `REVIEW_IN_PROGRESS` | verde | `nao_apurado, "em revisão"` |
| `test_p05` | lance 0,50 vs 3,20 | `keyword: ok` | `bloqueia`, com "2 de 2" na evidência |
| `test_p06` | `estado="parcial"` | degraus `ok` | nenhum `ok` sobrevive |
| `test_p07` | metas de conversão | `conversao: nao_apurado` | `ok` / `limita` conforme o observado |
| `test_p08` | envelope | sem veredito | `versao: 2` + `sentinela` |
| `test_p09` | sem transições | — | janela `indeterminada`, sem `NO_DELIVERY` |
| `test_p10`–`12` | recomendações | — | não lida ≠ zero; falha ≠ zero; adjudicada ≠ aplicada |
| `test_p13` | repositório | `select` truncava em 1000 | `select_all` paginado |
| `test_p14` | destino não consultado | sequestrava o veredito | vai para `desconhecidos` |

---

## A revisão adversarial (`test_r*`)

Codex `gpt-5.6-sol`, esforço high, read-only. **Doze achados, todos com
contraprova executada pelo revisor. Veredito: REJEITAR.** Todos corrigidos.

| # | sev | achado | correção | regressão |
|---|---|---|---|---|
| 1 | 🔴 | `recommendation.impact` vazava payload **bruto** na resposta HTTP | `METRICAS_DE_IMPACTO`: allowlist nominal, valores forçados a numérico | `test_r01`, `r01b` |
| 2 | 🔴 | `KW_EM_REVISAO`/`KW_RESTRITA` criados, verificados e **nunca consultados** → keyword em revisão saía `HEALTHY` | consultados em `ler_keywords`; viram causa `POLICY_REVIEW`/`POLICY_BLOCKED` | `test_r02`, `r02b` |
| 3 | 🔴 | anúncio apto era "ausência de reprovação": `approval_status=UNKNOWN` → `HEALTHY` | apto exige `APPROVED` **lido** | `test_r03`, `r03b` |
| 4 | 🟠 | mesma resposta com `desconhecidos` **e** `evidencia: apurada` | `_estado_da_evidencia` **derivado** de `_desconhecidos` — a contradição virou impossível de escrever | `test_r04`, `r04b` |
| 5 | 🟠 | `podeSerLidoComoBom` prometia uma "tranca do frescor" que não existia: `HEALTHY`+`apurada`+`velho` saía verde | terceira condição, `frescor === 'recente'` | `sentinela.test` |
| 6 | 🟠 | `quantidade=1` com itens `[]` → `vazio_confirmado` | o cabeçalho da coleta tem voto | `test_r06`, `r06b` |
| 7 | 🟠 | um `return` fazia a **ordem de avaliação** decidir: `SUSPENDED` + acesso negado → `ACCESS_UNAVAILABLE` | sem `return`; `PRECEDENCIA` decide | `test_r07`, `r07b` |
| 8 | 🟡 | `aria-label` do sino dizia "nenhuma condição ativa" sob `lista_incompleta` | `rotuloDoSino` extraída, exportada e provada; `default` nunca otimista | `sino.test` |
| 9 | 🟡 | denominador de qualidade contava a keyword **dentro e fora** | classificação por motivo entra no universo medido | `test_r09`, `r09b` |
| 10 | 🟡 | política sumia na serialização: frase sem `%`, JSON com `100%` | a política viaja **no** `Denominador` | `test_r10` |
| 11 | 🟡 | `NaN` virava campanha madura | `NaN` e negativo → `indeterminada` | `test_r11`, `r11b` |
| 12 | 🔵 | identificador operacional real em fixture nova | fixture sintética; guarda lê o id do brief sem escrevê-lo | `test_r12` |

---

## As provas de vocabulário

`test_trafego_sentinela_vocabulario.py` fixa **todo** nome de enum no descriptor
protobuf do SDK instalado. Não é documentação, não é memória, não é modelo.

Cinco nomes inventados foram encontrados por essa conferência:

```
AD_GROUP_CRITERION_LOW_QUALITY_SCORE   → ..._LOW_QUALITY
BELOW_FIRST_PAGE_BID                   → AD_GROUP_CRITERION_BELOW_FIRST_PAGE_BID
AD_GROUP_CRITERION_LOW_SEARCH_VOLUME   → não existe
AD_GROUP_CRITERION_POLICY_DISAPPROVED  → ..._DISAPPROVED
REVIEWED_AND_PENDING                   → ELIGIBLE_MAY_SERVE
```

**O guarda foi provado.** Reintroduzindo `AD_GROUP_CRITERION_LOW_QUALITY_SCORE`:

```
AssertionError: KW_BAIXA_QUALIDADE carrega nome(s) que a API não tem:
['AD_GROUP_CRITERION_LOW_QUALITY_SCORE']. Um nome inventado nunca casa,
e a causa some em silêncio.
1 failed, 16 passed
```

Revertendo: `17 passed`.

Duas provas passivas merecem nota:

- `test_a_conta_bloqueada_cobre_os_tres_estados_terminais` — se a API ganhar um
  quarto estado terminal de conta, a suíte falha e alguém decide, em vez de o
  estado novo cair no ramo "não reconhecido" para sempre;
- `test_os_conjuntos_de_keyword_nao_se_sobrepoem` — um motivo em dois baldes
  contaria a mesma keyword duas vezes.

---

## O que continua sem prova

- **A causa da suspensão.** A hipótese dos links externos permanece
  `HYPOTHESIS_PARTIALLY_SUPPORTED`; a API não expõe o motivo literal, e nada
  aqui conclui causalidade de política.
- **`horas_ligada` na leitura real.** O diário `trafego_evento` não foi
  consultado no smoke, e por isso a janela saiu `indeterminada` — dito, não
  escondido.
- **Prontidão de mensuração de ponta a ponta.** A sentinela **consome** o
  veredito de `trafego.prontidao`; ela não o recalcula, e a ponte só sabe
  derivá-lo das metas observadas na coleta.
- **Recibo de destino.** `nao_consultado` é a leitura honesta: esta lane não
  toca `landing_policy` e não persiste recibo por campanha.


---

## A verificação das correções

Segunda passada do mesmo revisor, contra `ed0c9ea`. Confirmou 11 dos 12 achados
como **CORRIGIDOS**, e encontrou **quatro** condições novas. Três já estavam
resolvidas em `9d291ea` (aprovação ausente, `APPROVED_LIMITED`, denominadores de
anúncio). A quarta era nova e real:

| # | achado | correção | regressão |
|---|---|---|---|
| 13 | aprovação **ausente** era mais permissiva que `UNKNOWN` | ausente = desconhecido | `test_r13` |
| 14 | `APPROVED_LIMITED` virou `sem_estado` — perda de informação conhecida | campo `limitados` próprio | `test_r14` |
| 15 | quatro `Denominador` de anúncio sem a política | todos herdam; **guarda por AST** | `test_r15`, `r15b` |
| 16 | `HEALTHY` ficou inalcançável? | **não** — e agora há prova disso | `test_r16` |
| 17 | **cinco** motivos de keyword caíam num `else` que afirmava falta de lance sobre keyword cujo lance foi lido | ramo próprio por motivo | `test_r17`, `r17b`, `r17c` |

O achado 17 merece registro: é o mesmo defeito do eixo `campanha` da primeira
rodada — um `else` afirmando uma ausência que não existe — cometido de novo no
eixo da keyword, **depois** de eu ter escrito o comentário explicando por que
aquilo era errado. A frase gerada se contradizia sozinha: dizia
*"0 de 1 vieram sem lance"* ao lado de
*`impedimento: "lance ou estimativa de primeira página ausentes"`*.

`test_r15b` e `test_r16` são de um tipo diferente dos demais: não provam um
comportamento, provam que uma **classe** de erro não pode ser reescrita.
`test_r15b` percorre a AST e falha se alguém construir um `Denominador` sem a
política; `test_r16` garante que a correção do achado 4 não tornou `HEALTHY`
inalcançável — um estado que nenhuma entrada atinge é um teste que não pode
falhar, e um teste que não pode falhar não prova nada.
