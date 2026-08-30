# Plano Mestre de Fechamento — VOLC O.S. (fable-global-v1)

Base: `e858651` · 2026-08-29 · Grafo: current:true (build a539dbd, digest idêntico)
Fonte factual: `FACT-MATRIX.json` (42 fatos) · Decisões humanas: `OPEN-DECISIONS.md`

## 1. Diagnóstico em cinco frases

1. **O sistema não sofre de falta de construção — sofre de falta de
   fechamento**: 36 tarefas partial contra 71 todo, e as partial concentram o
   valor (canário real criado, v12_01 com dados reais, kernel decisório
   testado, bancada criativa provada).
2. **O valor de 29/08 está preso fora da main**: um fast-forward limpo
   (`integration/autonomous-closure-20260829`) entrega ORAKUL Predictive,
   Demand Gen e a fronteira criativa S0 de uma vez; dois candidatos Gemini com
   gates verdes morreram por crash de revisor, não por mérito.
3. **A máquina de agentes quebrou por ambiente, não por inteligência**: um
   único defeito (gate chamando python inexistente) parou 4 frentes; um
   segundo (escopo de leitura dos reviewers) matou candidatos prontos.
4. **O caminho do caixa está a três decisões humanas de destravar**: D1
   (aplicar v10), D4 (credenciais/RLS) e D10 (webhook aberto) — todo o resto
   do Horizonte A pode andar sem esperar ninguém.
5. **Há um risco existencial silencioso**: 411 commits sem backup remoto (D9).

## 2. Norte e horizontes

**Horizonte A (caixa)**: lançar e diagnosticar Search com segurança —
criação pausada/validate_only, evidência no Supabase oficial, decisão no
frontend, confirmação humana antes de mutação, operação observável em
localhost + banco oficial (deploy do FastAPI é decisão futura D12).

**Horizonte B (VOLC O.S. completo)**: organizado em clusters CL-06..CL-12 e
onda 4, sem nenhuma aresta entrando no caminho crítico do A.

## 3. Clusters (14)

| ID | Cluster | Horizonte | Estado-chave |
|---|---|---|---|
| CL-01 | Convergência Git e autoridade | A (pré-tudo) | FF pronto; 411 commits sem backup |
| CL-02 | Search lançável | A | canário real; faltam 5 gates de governança (D1, D4) |
| CL-03 | Diagnóstico Search | A | dado real órfão de consumidor; front pronto |
| CL-04 | Ingestão GAds→Supabase | A | fato canônico só proposta; 5/5 custo no banco errado |
| CL-05 | Decisão e ORAKUL | A/B | kernel testado sintético; v10 não aplicada |
| CL-06 | Multicanal Google | A tardio/B | Display a uma prova real; DemandGen no FF |
| CL-07 | Produção de criativos | B | v11_03 provada não aplicada (D6) |
| CL-08 | ORAKUL Predictive | B | core no FF; ledger preditivo inexistente |
| CL-09 | Frontend operacional | A | diagnóstico e L6 aguardando contrato |
| CL-10 | Segurança operacional | A (gate) | webhook aberto; service_role exposta; P02-T05 risk |
| CL-11 | Integrações e legado n8n | A tardio/B | 13 flows no hosted legado |
| CL-12 | Ativos, orgânico e Meta | B | ADRs prontos, implementação zero |
| CL-13 | QG/workbook/grafo | transversal | contradições done↔decision; rebuild devido |
| CL-14 | Harness e supervisores | transversal | v2 fora da main; 2 defeitos vivos |

## 4. Ondas (detalhe em EXECUTION-WAVES.md)

- **Onda 1 — Convergência e desbloqueio**: 8 missões; zero decisões de
  produto (D9 recomendada). Entrega: main única, harness são, grafo fiel.
- **Onda 2 — Horizonte A sem esperar o dono**: 7 missões; entrega o
  diagnóstico REAL na tela e os pacotes prontos-para-janela (migration D0/D-1,
  segurança executável).
- **Onda 3 — Destravada por decisões**: espinha D1→v10→writer→canário
  fechado→janela D4/D10 → **Search lançável**. Paralelos: agenda única (D3),
  coleta contínua (D2), shadow real, Display real (D5).
- **Onda 4 — Horizonte B ordenado**: criativos (D6), preditivo, Cofre,
  orgânico/Postiz, Meta, receita/câmbio (D11).

## 5. Caminho crítico (Horizonte A)

```text
M-W1-03 (FF) ──► M-W1-09 (grafo/curadoria) ──► [D1] ──► M-W3-01 (v10 aplicada)
   ──► M-W3-02 (writer+caller) ──► M-W3-03 (canário reconciliado, P05-T11 done)
   ──► M-W3-13 [D4+D10] (janela de segurança) ──► SEARCH LANÇÁVEL
paralelo de maior valor: M-W2-01 (diagnóstico real na tela — sem nenhum portão)
```

Gargalos são humanos (D1, D4, D10), não técnicos. A recomendação econômica é
agendar UMA sessão de decisões com o dono usando `OPEN-DECISIONS.md` como
pauta — ela destrava a onda 3 inteira.

## 6. Integrações (ordem; detalhe em INTEGRATION-LEDGER.md)

1. FF `autonomous-closure` (0 conflitos) → 2. candidatos Gemini revisados →
3. linha do harness reconciliada → 4. órfãos decididos → 5. poda de ~19 refs
→ 6. rebuild do grafo → 7. push final (D9).

## 7. Riscos principais

| Risco | Severidade | Mitigação no plano |
|---|---|---|
| Perda do disco (sem backup remoto) | existencial | M-W1-01 imediata (D9) |
| Webhook de mutação aberto | alta | inventário M-W2-05 → janela D10 |
| service_role exposta em endpoints sem auth | alta | M-W2-05 → D4 |
| Supervisores queimando tentativas no defeito de gate | média | M-W1-05; D13 conservador |
| Dupla verdade de dados (hosted legado) | média | CL-11 rotina a rotina, nunca URL cega |
| "Código pronto" promovido a "concluído" | crônica | DoD binário + curadoria proposta, nunca aplicada por worker |

## 8. Progresso (fórmula declarada, sem invenção)

Fórmula oficial do roadmap: soma de `status_weights` sobre tarefas não-reserved.
Hoje: (33×1.0 + 36×0.5 + 1×0.25)/141 = **36,3%**.

Projeção por tarefas (não por tempo): o plano das ondas 1–3 converte em `done`
com prova as tarefas P05-T11, P05-T07, P05-T04, P09-T01, P09-T02, P09-T03
(porta única com webhook morto), P06-T08, P10-T16, P10-T04, P02-T05, P04-T07,
P01-T10* e promove P14-T02 e P04-T04/T05 de partial para quase-done
(*IDs da expansão presa no FF). Se todas fecharem: +12 done e ~4 partial
novos ⇒ ~(45 + 40×0.5 + 0×0.25)/141 ≈ **46%**. O número é projeção mecânica
da mesma fórmula, condicionada a prova real de cada aceite — não é promessa.

## 9. O que este plano recusa

- Reescrever engines existentes (volc_ads, kernel decisório, bancada, harness).
- Missões para Gemini/DeepSeek com arquitetura em aberto.
- Qualquer mutação externa "para testar".
- Tratar branch/worktree como entrega.
- Percentual sem fórmula e denominador.
