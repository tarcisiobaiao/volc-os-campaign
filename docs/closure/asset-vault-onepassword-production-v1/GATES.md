<!-- GERADO POR ./scripts/medir-gates-cofre.sh — NAO EDITE A MAO -->

| Gate | Comando | Resultado |
|---|---|---|
| base | `git merge-base HEAD origin/volc-os-v2` | `36bec04` |
| HEAD | `git rev-parse HEAD` | `664272f` |
| commits | `git rev-list --count 36bec04..HEAD` | 7 |
| diff | `git diff --shortstat` |  21 files changed, 9776 insertions(+), 475 deletions(-) |
| arvore | `git status --short` | SUJA: 18 caminho(s) |
| espaco em branco | `git diff --check` | limpo |
| ciclo SQL | `./scripts/provar-ciclo-v13_01.sh` | 92 provas passaram · PostgreSQL 15.19 |
| testes backend do Cofre | `pytest backend/tests/test_cofre_ativos.py` | 67 passed in 1.10s |
| suite backend inteira | `pytest backend/tests` | 2187 passed, 53 skipped in 39.98s |
| testes frontend do Cofre | `vitest run src/features/asset-vault` | Tests  24 passed (24) |
| TypeScript | `tsc --noEmit -p tsconfig.app.json` | 76 erros herdados · 0 em asset-vault |
| build | `npm run build` | ok |
| importador de engines | `importar_engines_no_cofre.py --autoteste` | 248 asserções ok · 7 engines |
| smoke 1Password (duple) | `onepassword-smoke/run.py --autoteste` | resultado: 0 falhas |
| smoke 1Password (real) | `onepassword-smoke/run.py` | `blocked/cli_ausente`, exit 10 |
| onboarding da pagina | `onboarding_pagina_facebook.py --autoteste` | 56/56 verificações passaram |
| rotas do Cofre | `len(rotas.router.routes)` | 13 |

<!-- medido em 2026-09-01 20:25:35 -0300 -->
