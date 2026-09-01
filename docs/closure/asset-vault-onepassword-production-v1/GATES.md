<!-- GERADO POR ./scripts/medir-gates-cofre.sh — NAO EDITE A MAO -->

| Gate | Comando | Resultado |
|---|---|---|
| base | `git merge-base HEAD origin/volc-os-v2` | `36bec04` |
| HEAD | `git rev-parse HEAD` | `209302e` |
| commits | `git rev-list --count 36bec04..HEAD` | 9 |
| diff | `git diff --shortstat` |  31 files changed, 13993 insertions(+), 477 deletions(-) |
| arvore (fora deste GATES.md) | `git status --short` | SUJA: 1 caminho(s): scripts/medir-gates-cofre.sh  |
| espaco em branco | `git diff --check` | limpo |
| ciclo SQL | `./scripts/provar-ciclo-v13_01.sh` | 92 provas passaram · PostgreSQL 15.19 |
| testes backend do Cofre | `pytest backend/tests/test_cofre_ativos.py` | 67 passed in 0.88s |
| suite backend inteira | `pytest backend/tests` | 2187 passed, 53 skipped in 42.09s |
| testes frontend do Cofre | `vitest run src/features/asset-vault` | Tests  24 passed (24) |
| TypeScript | `tsc --noEmit -p tsconfig.app.json` | 76 erros herdados · 0 em asset-vault |
| build | `npm run build` | ok |
| importador de engines | `importar_engines_no_cofre.py --autoteste` | 248 asserções ok · 7 engines |
| smoke 1Password (duple) | `onepassword-smoke/run.py --autoteste` | resultado: 0 falhas |
| smoke 1Password (real) | `onepassword-smoke/run.py` | `blocked/cli_ausente`, exit 10 |
| onboarding da pagina | `onboarding_pagina_facebook.py --autoteste` | 56/56 verificações passaram |
| rotas do Cofre | `len(rotas.router.routes)` | 13 |

<!-- medido em 2026-09-01 20:37:13 -0300 -->
<!-- ⚠️ Se este arquivo foi commitado junto com a medicao, o HEAD acima e o
     commit ANTERIOR: um arquivo gerado nao conhece o hash do commit que o
     contem. Confira com `git log --oneline -1`. -->
