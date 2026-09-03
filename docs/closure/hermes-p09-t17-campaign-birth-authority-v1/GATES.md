# Gates

| Gate | Command | Result |
|---|---|---|
| Supabase authority read-only | `python3 scripts/verificar_autoridade_supabase.py` | PASS: `✓ Supabase oficial: https://database.agenciavolc.com.br` |
| Red proof on base | archive of base + `contraprova-vermelha-bypass.py` | RED/PASS: exit 1, fake adapter called once, fake campaign resource, no network |
| Fixed red proof | `PYTHONPATH=. python3 docs/closure/.../contraprova-vermelha-bypass.py` | PASS: exit 0, `AutorizacaoAusente`, adapter 0, receipts 0 |
| `volc_ads` proof suite | `PYTHONPATH=. python3 -m volc_ads.testes_subir` | PASS: 33/33 cases; includes writer payload-impression recalculation |
| New backend authority tests | `PYTHONPATH=.:backend pytest -q backend/tests/test_p09_t17_autoridade_de_nascimento.py` | PASS: 54 passed, 5 warnings |
| Ledger + P09-T17 focused backend | `PYTHONPATH=.:backend pytest -q backend/tests/test_trafego_ledger.py backend/tests/test_p09_t17_autoridade_de_nascimento.py` | PASS: 77 passed, 5 warnings |
| Route no-mutate gate | `python3 scripts/gate_sem_mutacao_google.py` | PASS: 3/3; 5 focal counterproofs passed |
| Structural birth-authority scanner | `python3 scripts/gate_autoridade_de_nascimento.py` | PASS: 4/4; one production emitter |
| Secret scan | `python3 scripts/verificar_segredos.py` | PASS: no strong pattern found |
| JSON validation | `python3 -m json.tool PRODUCER-INVENTORY.json` and `CURATION-HANDOFF.json` | PASS |
| Python syntax | `python3 -m py_compile ...` on touched Python files | PASS |
| Git whitespace | `git diff --check` | PASS |
| Full backend suite, feature tree | `PYTHONPATH=.:backend pytest -q backend/tests` | FAIL inherited/toolchain: 48 failures, 3421 passed, 192 skipped, 24 warnings. Families: missing async pytest plugin, FastAPI version/golden mismatch. |
| Full backend suite, base archive | same on `207e91f...` archive | FAIL inherited/toolchain: 50 failures, 3365 passed, 192 skipped, 25 warnings. Same async plugin/FastAPI families; extra archive failures from no `.git` in archive for git-based gates. |
| Frontend install/build/test | `npm ci` | BLOCKED inherited lock drift: package-lock missing `esbuild@0.28.2` and platform packages, reproduced on base archive too. `npm test`/`npm run build` not run because install cannot complete without changing lockfile (outside lane). |

Warnings seen in pytest are inherited FastAPI/Pydantic/pytest warnings, not P09-T17 failures.
