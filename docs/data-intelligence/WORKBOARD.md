# WORKBOARD — VOLC Data Intelligence Lab

Fila explícita da execução. Só o integrador (coordenador) edita este arquivo e só ele commita.
Estados: `todo` · `doing` · `review` · `done` (com prova) · `blocked` · `rejected`.

## Regras de concorrência

- Máximo 4 sessões ativas contando o coordenador → no máximo 3 workers simultâneos.
- Testes pesados/benchmarks longos: um por vez (fila serial no coordenador).
- Nenhum worker cria worktree, commita, faz push/merge/rebase ou toca fora do arquivo que possui.
- Ambiente compartilhado: `experiments/data-intelligence-lab/.venv` (somente o coordenador altera `pyproject.toml`/`uv.lock`).

## Ownership de arquivos

| Owner | Papel | Arquivos possuídos (escrita exclusiva) |
|---|---|---|
| COORD | coordenador/integrador | `docs/data-intelligence/{RUN-MANIFESTO,WORKBOARD,EXPERIMENT-RESULTS,FINAL-REPORT}.md`, `CURATION-HANDOFF.json`, `PROOF-RECEIPT.json`, `experiments/data-intelligence-lab/{pyproject.toml,uv.lock,README.md,.gitignore}`, `src/volc_dil/__init__.py`, `src/volc_dil/contracts/`, `fixtures/contract/`, `tests/data-intelligence/{conftest.py,pytest.ini,test_contracts.py}` |
| A | auditor de arquitetura e dados (read-only no código) | `docs/data-intelligence/DATA-CAPABILITY-MATRIX.md`, `docs/data-intelligence/CATALOG-CLASSIFICATION.md` |
| B | investigador de bibliotecas | `docs/data-intelligence/LIBRARY-DECISIONS.md`, `research/data-intelligence/` |
| C | contratos aplicados + replay + bancada | `src/volc_dil/replay/`, `src/volc_dil/bench/`, `fixtures/replay/`, `tests/data-intelligence/test_replay*.py`, `test_bench*.py` |
| D | estatística (Stat Lab) | `src/volc_dil/statlab/`, `tests/data-intelligence/test_statlab*.py` |
| E | swarm/otimização | `src/volc_dil/swarm/`, `tests/data-intelligence/test_swarm*.py` |
| S (= COORD) | surrogate feasibility (assumido pelo coordenador: limite de 3 workers simultâneos) | `src/volc_dil/surrogate/`, `tests/data-intelligence/test_surrogate*.py` |
| F | revisor adversarial (read-only) | `docs/data-intelligence/ADVERSARIAL-REVIEW.md` (achados); respostas pelo COORD |

## Fila

| # | Fase | Tarefa | Owner | Depende de | Estado | Prova |
|---|---|---|---|---|---|---|
| 0.1 | 0 | Baseline e manifesto | COORD | — | done | `RUN-MANIFESTO.md` §1 |
| 0.2 | 0 | Ambiente `uv` isolado + lockfile | COORD | 0.1 | done | `uv.lock`, manifesto §4 |
| 0.3 | 0 | Classificar cada item do catálogo na base real + overlaps | A | 0.1 | done | `CATALOG-CLASSIFICATION.md` (16ae2958) |
| 0.4 | 0 | Matriz ideia→dado→grão→fonte→existe→cobertura→risco→decisão | A | 0.1 | done | `DATA-CAPABILITY-MATRIX.md` (16ae2958) |
| 0.5 | 0 | Decisões de bibliotecas/repositórios | B | 0.2 | done | `LIBRARY-DECISIONS.md` (3239fda4) |
| 1.1 | 1 | Contrato tipado: identidade, janela/as_of, fonte/frescor/cobertura, moeda/micros, atribuição, value_kind, features/labels, preliminar×fechado, fingerprint | COORD | 0.1 | done | c1903d5f, 212245b6, 7fd5a029, 9054059d |
| 2.1 | 2 | Bancada DuckDB + Polars × implementação atual | C | 1.1 | done (sintético) | 45b6a6ed, 9054059d |
| 3.1 | 3 | Replay econômico v0 + baselines | C | 1.1 | done (sintético) | 1db09c7d, 9054059d |
| 4.1 | 4 | Stat Lab: maturação, shrinkage, CS, FDR, Monte Carlo | D | 0.2 | done (simulação) | 05d79fdb, 39491835 |
| 5.1 | 5 | Swarm: equal/random/greedy/SH/ASHA (+bandit extensão) | E | 0.2 | done (negativo) | fc05316a, 202bd2d1 |
| 6.1 | 6 | Surrogate feasibility | COORD (S) | 0.4, 1.1 | done (dados insuficientes) | 574ac73b, 9054059d |
| 7.1 | 7 | Revisão adversarial | F1, F2 | 2.1–6.1 | done | `ADVERSARIAL-REVIEW.md` (35 achados) |
| 7.2 | 7 | Respostas, recibo, relatório final, handoff de curadoria | COORD | 7.1 | done | `FINAL-REPORT.md`, `PROOF-RECEIPT.json`, `CURATION-HANDOFF.json` |

## Ondas planejadas

1. Onda 1 (paralela): A, B, D. COORD escreve o contrato (1.1) em paralelo.
2. Onda 2: C e E (e S quando a matriz de A existir).
3. Onda 3: F sozinho; depois correções dos owners e consolidação.

## Log de decisões reversíveis

- 2026-10-15 23:3x — Python 3.13 em vez de 3.14 do sistema: cobertura de wheels mais ampla para libs científicas. Reversível.
- 2026-10-15 23:3x — `exclude-newer=2026-10-01`: evita pacotes com < 2 semanas. Reversível.
- 2026-10-15 23:3x — Núcleo econômico `volc_ads/economia/` ausente na base: contrato do lab autocontido; encaixe vira handoff.
- 2026-10-16 — Surrogate executado pelo coordenador (owner S) porque as três vagas de worker estavam ocupadas; revisado de forma independente por F1.
- 2026-10-16 — Revisão adversarial dividida em dois revisores (F1/F2) com escopos disjuntos; correções feitas pelos owners originais.
