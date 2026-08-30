# Tráfego — porta de entrada

**Estado do pacote:** ✅ **APROVADO E CONGELADO** — referência oficial da camada
**Data:** 24/08/2026 · **Canônico para:** camada de Tráfego do VOLC O.S.

> **Comece por aqui.** Este é o único índice da camada de Tráfego. Qualquer documento
> não listado abaixo como *vigente* está superado ou fora de escopo.

---

## 1. Estado

**Congelado em 24/08/2026.** O pacote foi aprovado pelo dono e é a **referência oficial** da
camada de Tráfego. Nada foi implementado — o congelamento é do *planejamento*.

Mudança material daqui em diante exige: novo ADR (ou emenda a um existente), atualização do
ledger se envolver medição, e regeneração do Mapa Vivo.

## 2. Documentos vigentes

| # | documento | responde | estado |
|---|---|---|---|
| 0 | **[Ledger de evidências](./EVIDENCIAS-TRAFEGO.md)** | "que fatos foram medidos, quando e como" | ✅ vigente — **fonte única dos números** |
| 1 | [PRD — Tráfego como Operação](./PRD-TRAFEGO-OPERACAO.md) | "qual é o problema, para quem, em que ordem" | ✅ vigente |
| 2 | [SPEC do P0](./SPEC-P0-TRAFEGO.md) | "o que se constrói, como e onde" | ✅ vigente |
| 3 | [Plano P0-A](./P0A-PLANO-DIAGNOSTICO.md) | "por que as duas campanhas não entregam" (somente leitura) | ✅ vigente |
| 4 | [Plano P0-S](./P0S-PLANO-SEGURANCA.md) | "quem pode disparar os executores legados" | ✅ vigente |
| 5 | [ADRs](./ADR-TRAFEGO.md) | "o que foi decidido, contra o quê, com base em quê" | ✅ vigente |
| 6 | [SPEC do Hub de Tráfego](./SPEC-HUB-DE-TRAFEGO.md) | **o nascimento da campanha** — cockpit, provas, travas | vigente **em parte** (ver §4) |
| 7 | [Smart Bidding 17/08](./SMART-BIDDING-2026-08-17.md) | o regime novo e o que ele torna perigoso | vigente |
| 8 | [SPEC de arbitragem](./SPEC-ARBITRAGEM.md) e [PRD de arbitragem](./PRD-ARBITRAGEM.md) | a visão de sistema além de Tráfego | vigente, escopo maior |
| 9 | [Prompt de abertura](./COMECE-AQUI-TRAFEGO.md) | como abrir uma sessão de trabalho | vigente como **prompt**, não como spec |

## 3. Matriz de autoridade

**[DA]** Não há precedência linear (ADR-20). A autoridade depende do **tipo de pergunta**:

| pergunta | autoridade |
|---|---|
| "o que o sistema **faz** hoje?" | o código |
| "o que **existe** na conta de anúncio?" | a conta, via snapshot com frescor |
| "qual é o **número** medido?" | o [ledger](./EVIDENCIAS-TRAFEGO.md) |
| "**por que** está assim?" | os [ADRs](./ADR-TRAFEGO.md) |
| "o que **deve** ser construído?" | [PRD](./PRD-TRAFEGO-OPERACAO.md) e [SPEC](./SPEC-P0-TRAFEGO.md) |
| "o que é **proibido**?" | as regras duras do dono |
| "o que a **operação** decidiu?" | o dono |

Divergência entre código e SPEC é **item de trabalho**, não erro de documento — se o código
sempre ganhasse, todo defeito conhecido viraria especificação.

## 4. O que foi superado, e por quê

| documento / seção | estado | motivo |
|---|---|---|
| SPEC-HUB §4.1 (`/trafego` — o quadro) | **superado** por [SPEC do P0 §6](./SPEC-P0-TRAFEGO.md) | o quadro deixa de ser a tela e vira uma aba; o padrão passa a ser o inventário |
| SPEC-HUB §1 — *"`metrics.` tem zero ocorrências; uma tela com ROAS seria ficção"* | **superado como fato**, mantido como princípio | `entrega.py` passou a ler métricas de custo e entrega ([E-01](./EVIDENCIAS-TRAFEGO.md#e-01)). O princípio — não desenhar número que não se mede — continua |
| SPEC-HUB §8 e §9 (o que construir / aceite) | **superado** pelo backlog do [PRD](./PRD-TRAFEGO-OPERACAO.md) §7 | escopo mudou de "nascimento" para "operação" |
| SPEC-HUB §4.2, §4.3, §5, §6, §10 | **vigentes** | cockpit de nascimento, provas, travas e o retrato do que existe |
| COMECE-AQUI-TRAFEGO | **vigente como prompt**; o ponteiro mudou | apontava para SPEC-HUB §10; deve apontar para esta porta |
| Qualquer proposta anterior de *"n8n: zero papel"* | **superada** | substituída pela fronteira do [ADR-05](./ADR-TRAFEGO.md) |
| Qualquer proposta anterior de *"rotacionar o path e observar quem quebra"* | **retirada** | ver [ADR-06](./ADR-TRAFEGO.md) |
| Estado `sumiu da conta` | **retirado** | substituído pelos seis estados de presença do [ADR-13](./ADR-TRAFEGO.md) |

## 5. Convenções do pacote

**Marcação:** **[F]** fato comprovado (sempre com `E-nn`) · **[I]** inferência ·
**[DA]** decisão aceita · **[DP]** decisão pendente · **[R]** risco ·
**[DE]** dependência externa.

**Números:** nenhum documento repete medição. Todo fato aponta para o ledger.

**Hierarquia de títulos:** `#` título do documento · `##` seção · `###` subseção.
