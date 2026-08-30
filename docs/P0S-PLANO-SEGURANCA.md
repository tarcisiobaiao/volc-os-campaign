# P0-S — Investigação e contenção dos executores legados

**Estado:** ✅ **aprovado e congelado** · **Natureza:** investigação · **Data:** 24/08/2026
**Porta:** [TRAFEGO.md](./TRAFEGO.md) · **Fatos:** [ledger](./EVIDENCIAS-TRAFEGO.md) · **Decisões:** [ADRs](./ADR-TRAFEGO.md)
**Regra desta faixa:** **nada é desativado.** A entrega é evidência, plano e — para endpoint
crítico indeterminado — um registro de aceitação de risco com prazo (ADR-15).

> **Marcação:** **[F]** fato (com `E-nn`) · **[I]** inferência · **[DA]** decisão aceita ·
> **[DP]** decisão pendente · **[R]** risco · **[DE]** dependência externa.

---

## 1. Correção de método — **[DA]**

A proposta anterior de **"rotacionar o path do webhook e observar quem quebra"** está **retirada**.

Path não é autenticação. Rotacionar um caminho secreto substitui um segredo fraco por outro segredo fraco, trata uma superfície pública como se fosse credencial, e usa a quebra de terceiros como instrumento de medição. **[R]** pior: se o consumidor for externo, a quebra é descoberta pelo terceiro, não por nós.

**Ordem correta, adotada:**

```
1. LER   histórico de execuções e logs        → quem chamou, quando, de onde
2. CLASSIFICAR  usado / não usado / indeterminado, com a fonte
3. PROPOR  autenticação real · allowlist de origem · rotação coordenada
           · desativação aprovada
4. EXECUTAR  só com aprovação e janela combinada
```

**[DA]** Ausência de memória sobre consumidores **não é evidência de desuso**. Só o log decide.

## 2. Superfície medida

**[F]** Sete gatilhos externos em workflows marcados como ativos — a lista completa está em
**[E-12](./EVIDENCIAS-TRAFEGO.md#e-12)**. Por criticidade:

| criticidade | superfícies | por quê |
|---|---|---|
| **crítica** | `apply-bidding` (webhook) · `factory v3` (6 formulários públicos) | mutam ou criam na conta real |
| alta | `custo-force-update-gads` | dispara ~99 nós contra a API (cota) |
| média | `receita-force-update-gam` · `gads-campaign-search` | ingestão e criação; o segundo está quebrado desde 24/02 |
| baixa | `pauta-kw-minning` · `joinads` d1/intraday | **[F]** legítimos e vivos, chamados pelo backend e pelo cron |

**[F]** Agravante do `apply-bidding`: o path está em claro no repositório e esteve no bundle do front; seu produtor legítimo está inativo — é um executor armado sem controlador. **[DA]** Path não é autenticação (ADR-06).

**[F]** Nenhuma trava do `volc_ads` (trava de dois fatores, Selo, portão de MCC, recibo) alcança essas duas superfícies: são caminhos paralelos ao Executor ([E-15](./EVIDENCIAS-TRAFEGO.md#e-15) mostra que o próprio núcleo não sabe ajustar — só estes caminhos sabem).

## 3. Investigação

### 3.1 Fontes

| fonte | responde | disponibilidade |
|---|---|---|
| API/tabela de execuções do n8n | quantas vezes, quando, com que carga | **[DE]** exige autorização OAuth que a sessão atual não tem |
| histórico de alterações do Google Ads | se houve mutação de lance por API nos últimos 14 dias e por qual cliente | disponível — **[F]** `entrega.py` já lê `change_event` |
| logs do gateway (Kong) | origem das requisições nos webhooks | **[R]** retenção limitada; verificar antes de contar com ela |
| logs do PostgREST | escritas por role | **[F]** contêineres em `json-file`, 3 × 10 MB — 19/08 **já rotacionou** |

### 3.2 Perguntas por superfície

| superfície | pergunta decisiva | fonte |
|---|---|---|
| `apply-bidding` | houve execução nos últimos 90 dias? houve mutação de lance por API na conta? | execuções do n8n + `change_event` |
| `factory v3` | algum dos 6 formulários recebeu submissão em 2026? em qual conta? | execuções do n8n |
| `force-update` (2) | há chamador vivo — front, bookmark, script, planilha? | execuções + logs de gateway + **o operador** |
| `gads-campaign-search` | ainda entram cards na coluna "google ads" do ClickUp? | ClickUp + execuções |
| `kw-minning`, `joinads` | confirmar que o chamador é o backend e o cron | execuções |

**[I]** O `change_event` do Google Ads é a fonte mais forte para o `apply-bidding`: se houve mutação de lance por API, ela aparece com o tipo de cliente. **[F]** Nas duas campanhas vivas, as alterações registradas são todas de origem painel, pelo operador ([E-14](./EVIDENCIAS-TRAFEGO.md#e-14)) — **[I]** indício de que ele não atuou nelas, e a própria [E-14](./EVIDENCIAS-TRAFEGO.md#e-14) declara que não prova nada sobre outras contas nem além de 14 dias.

## 4. Contenção — proposta, não execução

Ordem por criticidade. **Nenhuma destas ações faz parte da entrega do P0-S**; a entrega é o
plano, com dono e janela.

| superfície | contenção proposta | por quê | pré-requisito |
|---|---|---|---|
| `apply-bidding` | **autenticação real** (cabeçalho verificado) + allowlist de origem; se o log provar desuso, **desativação aprovada** | único caminho vivo que muta conta fora do Executor | evidência de uso |
| `factory v3` | autenticação nos formulários **antes** de qualquer desativação | endpoint público que cria campanha em conta real | evidência de uso |
| `force-update` (2) | substituir por contrato interno autenticado; manter o gesto, trocar a porta | o gesto é legítimo; a porta não | contrato interno existir |
| `gads-campaign-search` | avisar a operação do ClickUp antes de qualquer mudança | **[R]** há gente usando o quadro | comunicação |
| `kw-minning`, `joinads` | **manter**; documentar como contrato de periferia | legítimos e vivos (ADR-05) | — |

**[DA]** Rotação de segredo é **coordenada** — anunciada, com janela e responsável — nunca
usada como sonda (ADR-06).

## 5. Endpoint crítico indeterminado: aceitação com prazo

**[DA]** Classificação `indeterminado` **não autoriza repouso indefinido** (ADR-15). Toda
superfície crítica que a investigação não conseguir classificar recebe um registro com
quatro campos obrigatórios:

| campo | conteúdo |
|---|---|
| **aceite** | quem, nominalmente, aceita o risco |
| **prazo** | data-limite da aceitação |
| **controle compensatório** | o que reduz o risco enquanto isso |
| **reavaliação** | data em que a decisão volta à mesa |

Controles compensatórios, em ordem de preferência: **autenticação real** · allowlist de
origem · limite de taxa · monitoramento de invocação com alerta.

**[DP]** O prazo padrão para superfície crítica indeterminada. Recomendação: **14 dias**,
com controle compensatório aplicado no ato — porque o controle não depende de saber quem
usa, e a evidência pode nunca chegar (**[DE]** o histórico de execuções pode ter retenção
curta).

**[R]** Sem prazo, "indeterminado" vira permanente — que é exatamente como esses endpoints
chegaram até aqui.

## 6. Entregável

Uma tabela com uma linha por superfície: dono · alcance · criticidade · evidência de uso
(com fonte e data) · classificação · contenção proposta · pré-requisito · janela · e, quando
`indeterminado` **e** crítico, o registro de aceitação de risco completo.

**[DA] Nada é desativado nesta faixa.**

## 7. Riscos

**[R]** A investigação pode ser inconclusiva se as execuções do n8n tiverem retenção curta — nesse caso a resposta honesta é "indeterminado", a contenção correta é **autenticar** (não desligar), e o registro de aceitação da §5 passa a ser obrigatório.
**[R]** Autenticar S-2 pode quebrar um formulário que alguém usa sem avisar; a mitigação é anunciar antes, não descobrir depois.
**[DE]** Todo o passo 1 depende de acesso ao histórico de execuções do n8n.
