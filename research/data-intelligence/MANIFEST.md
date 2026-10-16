# MANIFEST — research/data-intelligence (worker B)

Registro de clones, sondas e artefatos do investigador de bibliotecas (worker B) na
corrida `lab/data-intelligence-overnight-20261015`. Datas em UTC.

## Clones

Nenhum clone foi feito. Toda leitura de repositório foi remota:

- GitHub REST API sem autenticação, uma chamada por repositório (39 chamadas em 2026-10-16 ~02:30Z).
- `raw.githubusercontent.com` para READMEs, LICENSE e ChangeLog.
- PyPI JSON API.

Repositórios grandes que **não** devem ser clonados neste disco (`size` da GitHub API, em KB):
ClickHouse 13.968.831, pymc-marketing 2.688.736, catboost 1.708.304, dagster 1.494.875,
or-tools 1.314.579, ray 828.802, airflow 761.712 e duckdb 542.673.

## Sondas de instalabilidade (venvs descartáveis)

Local: `experiments/data-intelligence-lab/.tools/probe-b/<nome>` (gitignored).
Python: CPython 3.13.0 arm64 (`/usr/local/bin/python3.13`).
Instalador: `uv` do bootstrap, com `--exclude-newer 2026-10-01T00:00:00Z`.
Script: `probe-b/probe.sh`. O teste de import roda com `HOME` vazio e `python -I`.

| Sonda | Specs | Resultado | Tamanho do venv | Pacotes | Log |
|---|---|---|---|---|---|
| optuna | optuna==5.0.0 | OK (SuccessiveHalving + TPE, 40 trials) | 38 MB | 11 | `probe-b/optuna.log` |
| mabwiser | mabwiser==2.7.4 | OK (TS e LinTS) | 223 MB | 20 | `probe-b/mabwiser.log` |
| vowpalwabbit | vowpalwabbit==9.11.9 | OK (`--cb_explore_adf`) | 6,2 MB | 1 | `probe-b/vowpalwabbit.log` |
| obp | obp==0.5.7 | **FALHA**: o resolver não acha solução (`torch==1.12`, sem cp313) | — | 0 | `probe-b/obp.log` |
| lightgbm | lightgbm==4.7.0 (+numpy/scipy do lock) | OK pela API nativa; libomp carregada do Homebrew | 100–106 MB | 4 | `probe-b/lightgbm.log` |
| catboost | catboost==1.2.10 (+lock) | OK | 331 MB | 17 | `probe-b/catboost.log` |
| cvxpy | cvxpy==1.9.3 (+lock) | OK (LP; 5 solvers) | 120 MB | 16 | `probe-b/cvxpy.log` |
| ortools | ortools==9.15.6755 | OK (GLOP LP); protobuf 6.33.6 | 131 MB | 9 | `probe-b/ortools.log` |
| pymc-marketing | pymc-marketing==1.2.0 (sem o lock) | OK; resolve para numpy 2.4.6; import em 38,6 s | 408 MB | 51 | `probe-b/pymc-marketing.log` |
| gads-mcp | google-ads-mcp==0.0.4 | OK no import; nenhum cliente instanciado; google-ads 33.0.0 | 167 MB | 87 | `probe-b/gads-mcp.log` |

Os tamanhos são `du -sh` do venv. O uv instala por clone/hardlink do cache, então
somar as colunas superestima o disco real.

**Apagado:** todos os 10 venvs acima foram removidos em 2026-10-16 ~02:45Z (`rm -rf .tools/probe-b/*`),
e o diretório `.tools/probe-b/` também foi removido.
Os logs e os `*.freeze.txt` ficaram em `research/data-intelligence/probe-b/`.

**Cache compartilhado:** o `experiments/data-intelligence-lab/.uv-cache` media 1,5 GB depois das sondas.
Ele é compartilhado com os outros workers e com o ambiente principal. A minha parte não foi isolada
e o cache não foi podado, para não quebrar sondas concorrentes. O COORD pode limpar ao final:

```bash
cd experiments/data-intelligence-lab && UV_CACHE_DIR=$PWD/.uv-cache .tools/bootstrap/bin/uv cache prune
```

## Resoluções sem instalação (`uv pip compile`)

- `probe-b/compat-lab-lock.txt`: cada candidato resolvido com o `uv.lock` do lab como constraint
  (`probe-b/lab-lock-constraints.txt`, 26 pins), para `aarch64-apple-darwin` e cp313.
- `probe-b/compat-protobuf.txt`: OR-Tools × google-ads e OR-Tools × protobuf 7.35.1 (pin do backend).
- `probe-b/compile-*.txt`: saída de cada resolução.

## Experimento hermético

- `probe-b/exp_mcp_null_vs_zero.py` → `.out.json`. Usa uma `GoogleAdsRow` (v23) fabricada, só com
  `campaign.id`, passada pelo formatador do `google-ads-mcp` 0.0.4. Não usa credencial nem rede.

## Metadados brutos

- `probe-b/github_metadados_2026-10-16.json` — 38 repositórios (license, archived, pushed_at, size, issues).
- `probe-b/pypi_metadados_2026-10-16.json` — versão, data de upload, requires_python, wheels cp313/arm64.

## Como apagar tudo o que este worker criou

```bash
rm -rf research/data-intelligence/probe-b research/data-intelligence/MANIFEST.md
rm -f docs/data-intelligence/LIBRARY-DECISIONS.md
```
