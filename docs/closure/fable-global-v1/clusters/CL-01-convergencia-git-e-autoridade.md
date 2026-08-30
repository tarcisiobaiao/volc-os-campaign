# CL-01 · Convergência Git e autoridade operacional

**Horizonte**: A (pré-requisito de tudo) · **Resultado**: uma única verdade na
`main`, com backup remoto, grafo reconciliado e baseline de gates honesto.

## Por que existe

A varredura provou que o valor recente do VOLC O.S. está espalhado: a única
integração pendente limpa (`integration/autonomous-closure-20260829`, 8 commits,
fast-forward possível) carrega ORAKUL Predictive, builder Demand Gen e a
fronteira criativa S0; a safra Gemini de 29/08 (PMax obs `5eb6b38`, deadman
`656d72d`) está fora da main; a linha do supervisor tem duas pontas divergentes;
e `origin/main` só tem o commit inicial — **411 commits sem backup remoto**.
Além disso o grafo contradiz o roadmap em 2 nós (P12-T07, P03-T08 `done` vs nós
`decision`) e o baseline TypeScript real é 77, não 76, enquanto existirem as
pastas duplicadas `" 2"`.

## Tarefas do Roadmap relacionadas

P10-T15 (gate de curadoria pós-integração), P01 (fonte do trabalho), e o
protocolo de fechamento do AGENTS.md.

## Missões

| ID | O quê | Modelo | Paralelo? |
|---|---|---|---|
| M-W1-01 | Backup remoto da main (decisão D9 + push para remoto próprio) | humano+Opus | sim (independente) |
| M-W1-02 | Lote documental: commit dos 16 untracked com varredura de segredo | Codex | sim |
| M-W1-03 | FF `integration/autonomous-closure-20260829` + gates pós-merge | Opus (integrador único) | NÃO — serializa |
| M-W1-04 | Integrar `5eb6b38` (PMax obs) e `656d72d` (deadman a3) + gates | Opus (integrador único) | após M-W1-03 |
| M-W1-05 | Higiene do gate TS: remover pastas `" 2"`, medir baseline real, atualizar CLAUDE.md | DeepSeek/Codex | sim |
| M-W1-06 | Verificação de conteúdo: fix "14 achados" (`c1dd576`) ⊂ `ee68085`? | Gemini | sim (read-only) |
| M-W1-07 | Reconciliar linha supervisor (`6fc7923` + harness-gemini) numa branch única | Codex | após M-W1-03 |
| M-W1-08 | Decidir/integrar órfão `b1fa53e` (paridade ORAKUL L2/L3) | Opus | após M-W1-03 |
| M-W1-09 | Pós-integração: rebuild do grafo pelo pipeline + curadoria (contradições P12-T07/P03-T08) + poda de ~19 refs | Opus (integrador único) | último |

## Ownership

- Integrador único: apenas UMA sessão executa merges/FF/poda (M-W1-03/04/08/09).
- Missões de verificação (M-W1-06) e higiene (M-W1-05) não tocam refs.

## Gates do cluster

- Após cada merge: `npx tsc --noEmit -p tsconfig.app.json` (baseline ≤77 e
  documentado), `npm run build`, suíte pytest relevante do diff, contagem de
  testes antes/depois registrada.
- `git diff --check` limpo; nenhuma ref apagada sem linha correspondente no
  INTEGRATION-LEDGER atualizada.

## Condição de rollback

Cada merge é um commit (ou FF) isolado; rollback = `git reset --hard` do ponto
anterior registrado no ledger ANTES do próximo merge. Poda só depois de todos
os merges verdes.

## Resultado observável

`git log main` contém o trabalho de 29/08; QG mostra tarefas com evidência
nova; `--check` do grafo `current: true` no HEAD novo.
