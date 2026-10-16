# VOLC Data Intelligence Lab (bancada hermética)

Laboratório local para provar, com código e evidência, contrato de dado econômico, replay
`as_of`, estatística, swarm e surrogate **antes** de qualquer shadow real. Não é serviço,
não lê produção, não chama API e não tem caminho de mutação.

## Ambiente

```bash
cd experiments/data-intelligence-lab
# uv isolado (sem instalação global); recriar o bootstrap se .tools/ não existir:
/usr/local/bin/python3.13 -m venv .tools/bootstrap && .tools/bootstrap/bin/python -m pip install uv
UV_CACHE_DIR=$PWD/.uv-cache UV_PYTHON_DOWNLOADS=never .tools/bootstrap/bin/uv sync --frozen --python /usr/local/bin/python3.13
```

`uv.lock` é travado com `exclude-newer = 2026-10-01` (só pacotes com ≥ 2 semanas). Dependências:
numpy, scipy, statsmodels, scikit-learn, duckdb, polars (+ pytest no grupo dev). Decisões em
`docs/data-intelligence/LIBRARY-DECISIONS.md`.

## Testes (da raiz do repositório)

```bash
OMP_NUM_THREADS=2 experiments/data-intelligence-lab/.venv/bin/python -m pytest tests/data-intelligence -q
```

`tests/data-intelligence/pytest.ini` isola a suíte do conftest da raiz; `conftest.py` bloqueia
qualquer conexão de rede durante os testes.

## Pacotes (`src/volc_dil/`)

| Pacote | Fase | O que faz | Resultados |
|---|---|---|---|
| `contracts/` | 1 | Observação econômica tipada, snapshot `as_of`, agregação anulável, identidade estrita, rótulo, circularidade, fingerprint | `docs/data-intelligence/CONTRATO-DADO-ECONOMICO.md` |
| `bench/` | 2 | DuckDB × Polars × stdlib sobre a mesma operação, com equivalência | `results/bench/` |
| `replay/` | 3 | Replay econômico `as_of` com baselines e métricas | `results/replay/` |
| `statlab/` | 4 | Maturação, shrinkage, confidence sequences, FDR | `results/statlab/` |
| `swarm/` | 5 | Successive Halving/ASHA × equal/random/greedy | `results/swarm/` |
| `surrogate/` | 6 | Portão de viabilidade + experimento de poder | `results/surrogate/` |

Scripts em `scripts/` regeneram cada resultado de forma determinística (seed padrão 20261015);
todo JSON de resultado carrega `manifesto` com seed, hashes de entrada, código, resultado e versões.

## Fronteiras

- Escreve só em `experiments/data-intelligence-lab/`, `docs/data-intelligence/`, `tests/data-intelligence/`, `research/data-intelligence/`.
- Lê (somente leitura) fixtures versionadas do repositório; nenhum valor monetário real individual é gravado em resultado.
- Tudo aqui é sintético ou n minúsculo: nada é "validado" para produção.
- Limpeza: apagar `.tools/`, `.venv/`, `.uv-cache/`, `artifacts/` (todos fora do Git).
