# Gates — Search Delivery Sentinel + Guardião 72h

**Base:** `34dc7b41bce901bd8bebfdec0a01e293678cbf08`
**HEAD:** ver `git log -1` na branch `sprint/search-delivery-sentinel-72h-v1`

---

## Como o baseline foi medido

⚠️ **Duas medições de baseline foram descartadas antes de a terceira valer.**
Isso está registrado porque a diferença mudava a leitura dos números.

1. **Primeira medição, inválida:** rodada antes de o ambiente ser igualado.
   Sem `.env`, 7 arquivos de vitest falham por *"Missing Supabase environment
   variables"* e 15 testes de pytest ficam `skipped` por
   `SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY não encontrados`. São diferenças de
   **ambiente**, não de código. Dava `3800 passed / 112 skipped`.

2. **Segunda tentativa, inválida por outro motivo:** um `git stash -u` numa
   árvore já limpa **não cria stash**, e o `git stash pop` seguinte trouxe um
   *backup pré-existente da branch `main`* — a lista de stash é compartilhada
   entre worktrees. O pop conflitou e portanto **não** apagou o backup alheio; a
   árvore foi restaurada ao HEAD sem perda, e o backup de `main` segue intacto.
   A medição resultante era do meu próprio código, não do baseline.

3. **Terceira, válida:** worktree descartável em `--detach 34dc7b4`, mesmo
   interpretador, mesmo `.env`, removida ao fim. É esta que vale.

---

## Backend — `pytest backend/tests volc_ads -q`

| | passed | skipped | failed |
|---|---|---|---|
| **baseline** `34dc7b4` | 3815 | 97 | 0 |
| **final** | 3937 | 97 | 0 |
| delta | **+122** | **0** | 0 |

Os +122 são exatamente as provas novas desta lane. **Os 97 skips são os mesmos**,
todos por dependência de ambiente (`psycopg` ausente, fixtures de run do
FunnelForge ausentes, `VOLC_SEGREDO_KEY` não definida) — nenhum introduzido nem
removido por esta lane.

### Focais

```
test_trafego_sentinela.py               100 passed
test_trafego_sentinela_vocabulario.py    17 passed
test_trafego_diagnostico_v12.py          32 passed
test_trafego_diagnostico_v12_rota.py      6 passed
test_google_inteligencia_persistente.py  58 passed
test_trafego_alertas.py                  21 passed
test_trafego_inventario.py                  passed
```

---

## Frontend

### `npx vitest run` (contagem do reporter JSON, que é a autoritativa)

| | arquivos | testes | passed | skipped | failed |
|---|---|---|---|---|---|
| **baseline** | 97 | 1409 | 1406 | 3 | 0 |
| **final** | 98 | 1438 | 1435 | 3 | 0 |
| delta | +1 | **+29** | **+29** | **0** | 0 |

Os 3 skips são os mesmos três, todos em
`src/components/trafego/vinculo/__tests__/retratos.test.tsx`.

⚠️ A linha de resumo de uma execução anterior dizia `1404 passed | 5 skipped`.
O reporter JSON, rodado com a árvore em worktree limpa, dá `1406 / 3`. **Vale o
JSON** — a linha de resumo foi lida de uma execução com ambiente diferente.

### `npx tsc --noEmit -p tsconfig.app.json`

| | erros |
|---|---|
| **baseline** | 76 |
| **final** | 76 |
| delta | **0** |

**Zero erros nas áreas desta lane**, antes e depois. Os 76 são herdados e vivem
todos fora dela:

```
31  src/services/supabaseDataService.ts
12  src/pages/ProjectDashboard.tsx
 8  src/components/pautador-pro/AddOpportunityModal.tsx
 7  src/utils/healthChecks.ts
 4  src/pages/settings/ProjectsSettings.tsx
 3  src/pages/GeneralDashboard.tsx
 2  src/pages/settings/CampaignsSettings.tsx
 2  src/pages/Reports.tsx
 2  src/pages/CampaignDetailDashboard.tsx
 2  src/lib/supabase.ts
 2  src/components/dashboard/SiteAnalysis.tsx
 1  src/v6/components/OnboardingWizard.tsx
```

### `npm run build`

`exit 0`, baseline e final.

---

## Segurança e integridade

| gate | resultado |
|---|---|
| `scripts/gate_sem_mutacao_google.py` | `ok 3/3` — antes, depois, e depois da leitura real |
| `scripts/verificar_segredos.py` | nenhum padrão forte no working tree |
| `scripts/verificar_autoridade_supabase.py` | `✓ https://database.agenciavolc.com.br` |
| `git diff --check` | limpo |
| árvore ao encerrar | limpa |
| scanner de id/token nos artefatos novos | nenhuma sequência de 8–12 dígitos, nenhum `token`, `@` ou `http` em `REAL-READ-SUMMARY.json` |

⚠️ `gate_sem_mutacao_google.py` precisa do interpretador com `pytest`. Com o
`python3` do sistema ele imprime `as contraprovas focais da rota NÃO passaram` e
`No module named pytest`, **e sai com código 1** — ou seja, ele se recusa
corretamente, sem falso verde. Rodar sempre com `backend/.venv/bin/python`, que
sai `0`.

Nota de método: numa leitura anterior deste gate eu registrei "exit 0" com o
interpretador errado. Era o código de saída do `tail` da pipeline, não o do
script. Conferido de novo sem pipe: `python3` → 1, `backend/.venv/bin/python` → 0.
O gate está correto; a primeira leitura é que não estava.

---

## Grafo

`graphify-out/` é untracked e não existe nesta worktree. Consultado read-only no
repositório principal:

```json
{"current": true, "built_at_commit": "a539dbd7...", "reason": "insumos idênticos"}
```

O grafo foi construído em `a539dbd7`, que **não** é a base desta lane
(`34dc7b4`). Limitação declarada. `graphify update .` **não** foi executado, e
`scripts/atualizar_grafo_volc_os.py` não foi rodado em modo de escrita.
