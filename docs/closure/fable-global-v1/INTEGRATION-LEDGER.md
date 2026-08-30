# Ledger de Integração — branches, worktrees e commits não integrados

Snapshot: 2026-08-29, main = `e858651`. Método: `git rev-list --left-right
--count`, `git merge-base --is-ancestor`, `git cherry` (patch-id) e leitura de
diffstat por investigador read-only. **Nenhum merge, poda ou push foi
executado.** A execução deste ledger é do integrador único (AGENTS.md).

## 0. Alerta máximo — backup remoto inexistente

`origin/main` contém apenas o "Initial commit" (`8bffa0e`, 12/02/2026) e tem
história divergente; a main local está **411 commits à frente**. Fev–ago/2026
existe só neste disco. Ação: decisão do dono sobre push (provavelmente
`--force-with-lease` para um remoto próprio, NUNCA para o upstream webgo).
→ missão `M-W1-01`, decisão D9 em OPEN-DECISIONS.

## 1. Fila de integração (ordem recomendada)

| # | Ref | SHA | Estado | Conteúdo | Ação proposta |
|---|---|---|---|---|---|
| 1 | `integration/autonomous-closure-20260829` | `951fe3f` | 8 ahead / **0 behind** — fast-forward possível | ORAKUL Predictive core (services/orakul_predictive/), builder Demand Gen, fronteira criativa S0, ratchets pytest/corretivos; 77 arquivos, +7205/−455 | **Integrar primeiro** (gates depois do FF); supera `feat/orakul-predictive-core-v1` (13 ahead), `aebbaef`, `7174f1f/7bf4ecf`, `8dfc78f` |
| 2 | `agent/...gemini-ads-pmax-observabilidade...` | `5eb6b38` | 1 ahead, base = HEAD | Núcleo read-only de observabilidade PMax (P04-T07) | Integrar após gates (merge trivial) |
| 3 | `agent/...gemini-ads-health-deadman...a2` (a3 tip) | `656d72d` | 3 ahead, base = HEAD; a3 ⊃ a2 ⊃ a1 | Contrato heartbeat/deadman (P10-T04) | Integrar só o tip `656d72d`; a1/a2 são subconjuntos |
| 4 | `feat/harness-gemini-37-flash-v1` + `6fc7923` | `e92793e` / `6fc7923` | 14 ahead/14 behind + 5 ahead divergente | Executor Gemini 3.7 Flash + supervisor contínuo v0 + cancelamento/cleanup | **Reconciliar antes de integrar**: o commit de cancelamento `6fc7923` NÃO está no harness-gemini; mesclar as duas pontas sobre `feat/supervisor-continuo-v0` (`5810036`) |
| 5 | `b1fa53e` (orakul L2/L3 references, órfão) | `b1fa53e` | 1 ahead sobre base antiga `b69969b` | Prova de paridade ORAKUL e matriz de referências | **Decidir**: confrontar com o conteúdo do orakul-predictive-core já absorvido no item 1; integrar ou declarar superado com motivo |

## 2. Superadas por conteúdo (verificar 1 item, depois podar)

| Ref | Motivo | Ressalva antes de podar |
|---|---|---|
| `feat/estudio-criativo-c0-c1-c3`, `integration/estudio-criativo-c0-c1-c3`, `review/estudio-criativo-c0-c1-c3`, `integration/volc-unificado-20260827`, one-shot | Conteúdo entrou na main via `ee68085` (v11_01 + src/pages/criativos presentes na main) | **Conferir se o fix "14 achados" (`c1dd576`/`84ad3cf`) está dentro de `ee68085`** — diffstats divergem (17556 vs 17055 inserções). Missão de verificação de conteúdo antes da poda |
| `feat/criativos-schema-blindado` | 2 commits patch-equivalentes na main (`bf7062f`; v11_02 presente) | Nenhuma |
| `feat/qg-operacional-v2`, `integration/qg-v3-redator` | Conteúdo funcional na main via `integration/codex-qg-redator-convergence` (`2d8ad6e`, ancestral da main); restos são commits pré-rebase e snapshots de grafo superados | Equivalência dos 4 commits pré-rebase é por sucessão de subject (INFERIDO), não patch-id |

## 3. Contidas na main — poda segura (~14 refs)

`feat/hub-trafego`, `feat/qd-agentico`, `feat/search-canary-launch-v1`,
`feat/decision-intelligence-ui-l6`, `feat/estudio-template-lab`,
`feat/design-review-global-premium-v1`, `worktree-p04-display-finalizacao`,
`integration/global-convergence-20260829`,
`integration/codex-qg-redator-convergence`, `sync/webgov6`,
`volc5.1`/`backup/volc5.1-pre-sync`, `agent/deepseek-qg-kanban-v4`, e as refs
`agent/*` com ahead=0 (specs godmode `9885459`, smoke readonly, search-diagnostico,
fable-closure). Zero commits exclusivos (`git merge-base --is-ancestor` = sim).

## 4. Worktrees

- **Consumíveis após itens 1–5**: todas as `.agent-worktrees/*` cujos tips
  ficaram superados; as worktrees nomeadas das branches da seção 3.
- **Vivas / não tocar**: `/private/tmp/volc-autonomous-closure` (fila de
  integração nº1 + supervisor.sqlite), `/private/tmp/volc-supervisor-continuo-v0`
  (linha supervisor), a worktree desta missão
  (`/private/tmp/volc-fable-global-closure-specs-v1`).
- Remoção de qualquer worktree exige confirmação do dono e `git worktree
  remove` (nunca `rm -rf` em worktree registrada).

## 5. Untracked na worktree principal (fora de branch)

16 caminhos untracked na main (ADRs, contracts/, evidence/, missões do
harness, `scripts/adaptar_gads_reports_n8n.py`, `tools/agentic-recovery-smoke/`)
— trabalho documental de 28–29/08 sem versionamento. Ação: lote documental
único, com varredura de segredo antes do commit (missão `M-W1-02`).

## 6. Regra de fechamento do ledger

Cada linha deste ledger só muda de estado com: (a) SHA integrado alcançável
pela main, (b) gates pós-merge verdes registrados, (c) linha atualizada aqui
com o SHA do merge. "Mergeei" sem gates pós-merge não fecha linha.
