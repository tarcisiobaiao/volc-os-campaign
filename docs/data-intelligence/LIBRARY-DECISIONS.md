# LIBRARY-DECISIONS — VOLC Data Intelligence Lab

**Owner:** worker B (investigador de bibliotecas e repositórios) · **Tarefa:** WORKBOARD 0.5
**Coleta de evidência:** 2026-10-16, entre 02:30 e 02:50 UTC (noite de 2026-10-15 no Brasil)
**Ambiente das sondas:** CPython 3.13.0 arm64 (macOS 15 / Darwin 24.6.0), `uv` do bootstrap, `--exclude-newer 2026-10-01T00:00:00Z`
**Estado:** proposta. Nenhuma linha do `pyproject.toml`/`uv.lock` foi alterada. A decisão final cabe ao COORD.

Etiquetas de evidência usadas no documento:
**[D] demonstrado** (sonda ou resolução executada aqui) ·
**[F] fonte primária lida** (PyPI JSON, GitHub API, README/LICENSE/ChangeLog) ·
**[P] evidência anterior do repositório** (`.claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-C-dados/RELATORIO-C.md`, 2026-10-14, não refeita) ·
**[I] inferido** · **[H] hipótese**.

Artefatos brutos: `research/data-intelligence/probe-b/` (logs, freezes, resoluções, metadados, experimento MCP).
Clones, sondas e limpeza: `research/data-intelligence/MANIFEST.md`.

Definições:
- **Último release:** data de upload no PyPI da versão mais nova.
- **Último commit:** `pushed_at` da GitHub API, que conta push em qualquer branch.
- **Tamanho:** `du -sh` do venv da sonda, com dependências.
- **Py3.13/arm64:** "instalado" é [D] com import; "resolve" é [D] por `uv pip compile` para cp313/aarch64-apple-darwin; "wheel" é [F].

---

## 1. Tabela principal

| item | decisão | papel no VOLC | licença | manutenção (último release · último push) | Py3.13/arm64 | tamanho | risco | evidência |
|---|---|---|---|---|---|---|---|---|
| **DuckDB** | **adotar** no lab, provisório até o benchmark 2.1 | motor SQL em processo para replay sobre Parquet/CSV/JSON | MIT | 1.5.6 · 2026-09-28 / push 2026-10-15 | instalado no lock (wheel cp313 arm64, 32,8 MB) | wheel 32,8 MB | baixo; autoload de extensões busca na rede [I] | PyPI `duckdb`; github.com/duckdb/duckdb; `uv.lock` |
| **Polars** | **adotar** no lab, provisório até o benchmark 2.1 | DataFrame lazy para normalização e features | MIT (repo; o campo do PyPI traz só o copyright) | 1.44.2 · 2026-09-09 (2.0.0 saiu em 2026-10-06, fora da janela) / push 2026-10-15 | instalado no lock (`polars` + `polars-runtime-32`) | — (já no lock) | médio: major 2.0 pendente | PyPI `polars`; `uv.lock` |
| **Optuna** | **referência**; adiar como dependência | oráculo para conferir o SH/ASHA próprio do swarm (E), só em trials sintéticos/históricos | MIT | 5.0.0 · 2026-09-07 / push 2026-10-15 | instalado [D] | 38 MB, 11 pacotes | baixo; arrasta SQLAlchemy+Alembic | sonda `optuna.log` (40 trials, 37 podados) |
| **ConfSeq** | **referência** (sem dependência) | fórmulas de confidence sequence para outcome limitado; implementar em numpy | MIT | 0.0.11 · 2023-01-26 / push 2026-01-07 | **sem wheel cp313** (wheels só até cp310; sdist com C++14 + Boost) [F] | — | alto: README diz "early-stage"; `pytest` e `matplotlib` são deps de runtime | PyPI `confseq`; README (raw); sonda própria fica com o worker D |
| **MABWiser** | **referência**; adiar | baseline TS/LinTS em simulação | Apache-2.0 | 2.7.4 · 2024-08-30 / push 2024-09-05 | instalado [D] (numpy 2.5.3, pandas 3.0.6) | 223 MB, 20 pacotes (seaborn/matplotlib) | médio: parado há ~25 meses | sonda `mabwiser.log`; CHANGELOG |
| **Vowpal Wabbit** | **adiar** | contextual bandit `cb_explore_adf` em simulação, se o volume justificar | BSD-3 (PyPI); LICENSE próprio Microsoft/Yahoo (GitHub: NOASSERTION) | 9.11.9 · 2026-09-27 / push 2026-10-15 | instalado [D] | 6,2 MB, 1 pacote | baixo técnico; alto conceitual (overkill) | sonda `vowpalwabbit.log` |
| **Open Bandit Pipeline (obp)** | **rejeitar** como dependência; **referência** de estimadores OPE | IPW/SNIPW/DR como especificação | Apache-2.0 | 0.5.7 · 2023-04-14 / push 2024-06-03 | **não instala** [D]: exige `torch==1.12` (sem cp313) | — | alto | sonda `obp.log` |
| **scikit-learn** | **adotar** (já no lock) | RidgeCV, TimeSeriesSplit, calibração isotônica, HDBSCAN | BSD-3-Clause | 1.9.1 · 2026-09-10 / push 2026-10-14 | instalado no lock | wheel 8,3 MB | baixo | PyPI; `uv.lock` |
| **statsmodels** | **adotar** (já no lock) | FDR (`multipletests`), GLM, diagnósticos | BSD-3-Clause | 0.15.0 · 2026-08-27 / push 2026-10-15 | instalado no lock | wheel 11,6 MB | baixo | PyPI; `uv.lock` |
| **LightGBM** | **adiar** | boosting só depois de baseline linear + volume + validação temporal | MIT (repo; o campo do PyPI está vazio) | 4.7.0 · 2026-07-18 / push 2026-10-15 | instalado [D], **mas a libomp vem do Homebrew** | 100–106 MB, 4 pacotes | médio: lib nativa externa; a API sklearn não declara scikit-learn | sonda `lightgbm.log` (`otool`, `DYLD_PRINT_LIBRARIES`) |
| **CatBoost** | **adiar** | idem LightGBM; categóricas nativas | Apache-2.0 | 1.2.10 · 2026-02-18 / push 2026-10-15 | instalado [D] (`requires_python` vazio no PyPI) | 331 MB, 17 pacotes | médio: peso; grava `catboost_info/` por padrão [I] | sonda `catboost.log` |
| **PyMC Marketing** | **adiar** | benchmark posterior de MMM/shrinkage; não explica sessão nem controle intradiário | Apache-2.0 | 1.2.0 · 2026-09-29 / push 2026-10-15 | **conflita com o lock** [D]: exige `numpy<2.5`; o lock tem 2.5.3. Isolado: instalado [D] | 408 MB, 51 pacotes; import de 38,6 s | alto: conflito + peso + release a 2 dias do corte | `compat-lab-lock.txt`; sonda `pymc-marketing.log` |
| **Google Meridian** (citado em D20) | **rejeitar** agora | MMM bayesiano do Google | Apache-2.0 (repo) | 2.1.0 · 2026-09-25 / push 2026-10-16 | **conflita com o lock** [D]: `statsmodels<0.15`; além disso `tensorflow` + `tfp-nightly` fixo e `numpy<2.4` [F] | não sondado (> 600 MB [I]) | alto | `compile-google-meridian.txt`; PyPI requires_dist |
| **OR-Tools** | **adiar** (verificador) | verificador de alocação com restrições depois do allocator A0/A1 | Apache-2.0 | 9.15.6755 · 2026-01-14 / push 2026-10-15 | instalado [D] | 131 MB, 9 pacotes | médio: fixa `protobuf>=6.33.1,<6.34`; não convive com o pin 7.35.1 do backend [D] | sonda `ortools.log`; `compat-protobuf.txt` |
| **CVXPY** | **adiar** (verificador) | otimização convexa (CVaR, QP) se scipy não bastar | Apache-2.0 | 1.9.3 · 2026-09-19 / push 2026-10-13 | instalado [D] | 120 MB, 16 pacotes | baixo-médio: 5 solvers nativos | sonda `cvxpy.log` |
| **google-ads-python** | **adotar fora do lab** (já é a porta técnica do backend); **rejeitar dentro do lab** | transporte GAQL/serviços em `volc_ads/` e `backend/` | Apache-2.0 | 34.0.0 · 2026-10-15 (API v26); 33.0.0 · 2026-09-23 / push 2026-10-15 | resolve [D] (puro Python; wheel de 19,4 MB) | 167 MB com o MCP | médio: cadência de sunset de versões da API | `backend/requirements-dev.txt:29` (`google-ads>=33.0.0,<34`); ChangeLog |
| **GAARF** (`google-ads-api-report-fetcher`) | **referência** de padrões; rejeitar como dependência | ideias de templates/macros GAQL e writers | Apache-2.0 | 1.18.3 · 2026-02-04 / push 2026-10-15; o código migrou para `google/garf` [P] | resolve [D] (garf-google-ads 1.2.1: 47 pacotes) | 365 MB [P] | alto: NULL→0 [P]; `main` do garf ganhou actors de mutação [P]; "not an officially supported Google product" [F] | README (raw); RELATORIO-C [P] |
| **Google Ads MCP** | **adiar** (só ferramenta de dev, com conta de teste) | exploração ad hoc de GAQL por agente | Apache-2.0 | 0.0.5 · 2026-10-09; 0.0.4 · 2026-09-25 / push 2026-10-09 | instalado [D] (0.0.4) | 167 MB, 87 pacotes | **alto**: NULL→0 [D]; escopo OAuth `adwords` completo; modo remoto em `0.0.0.0:8080`; versão 0.0.x | sonda `gads-mcp.log`; `exp_mcp_null_vs_zero.out.json` |
| **Google Ads API Developer Assistant** | **referência** (ferramenta de dev) | gerar e validar GAQL; não é runtime | Apache-2.0 | sem PyPI / push 2026-10-15 | não aplicável (roda no host do agente) | não medido | alto se usado com credencial real: executa o código gerado | README (raw); `volc_ads/google_ads_api/assistant_for_devs_gads_api.md` |
| Tightlock | referência | padrões de Data Manager/enhanced conversions | Apache-2.0 | sem PyPI / push 2026-04-13; 16 issues abertas | n/a | repo 0,6 MB | médio: upload de valor exige contrato próprio | GitHub API |
| ads-policy-monitor | referência | padrão GAQL de policy | Apache-2.0 | push 2026-05-28 | n/a | 1,2 MB | médio: janela `DURING LAST_30_DAYS` pode omitir reprovados sem impressão [P] | GitHub API; RELATORIO-C [P] |
| agentic_dsta (ADSTA) | referência | padrões de toolset/eventos | Apache-2.0 | push 2026-06-23; 11 estrelas, 24 issues | n/a | 3,4 MB | alto se copiado: runtime mutador/Firestore | GitHub API |
| if-this-then-ad | referência | regras condicionais por evento externo | Apache-2.0 | push 2026-09-25 | n/a | 5,1 MB | médio: runtime mutador | GitHub API |
| marketing-analytics-jumpstart | rejeitar agora | stack BigQuery/Vertex | Apache-2.0 | push 2026-01-05; 50 issues | n/a | 20 MB | alto: autoridade paralela | GitHub API |
| sentence-transformers | adiar | embeddings para clustering de termos (D33) | Apache-2.0 | 6.1.0 · 2026-09-18 | resolve [D] (41 pacotes, torch) | torch: wheel de 127 MB | médio: baixa modelo do HF Hub | `compile-sentence-transformers.txt` |
| BERTopic | rejeitar agora | tópicos sobre termos | MIT | 0.17.4 · 2025-12-03 / push 2026-10-14 | resolve [D] (51 pacotes) | não medido | alto: experimento anterior refutou "negativar o cluster" [P] | `compile-bertopic.txt`; [P] |
| pgvector | adiar | busca vetorial no Supabase | PostgreSQL License (GitHub: NOASSERTION) | cliente Python 0.5.1 · 2026-10-09 / push 2026-10-15 | puro | n/a | baixo técnico; exige migration | LICENSE (raw) |
| Feast | rejeitar agora | feature store | Apache-2.0 | 0.67.0 · 2026-10-13 | não testado no lab; conflito `tenacity<9` com o backend [P] | 165 requires_dist | alto | PyPI; [P] |
| Prefect | rejeitar | orquestrador (o n8n já é a agenda) | Apache-2.0 | 3.8.8 · 2026-10-06 | conflito `fastapi>=0.139` com o backend [P] | 83 requires_dist | alto | PyPI; [P] |
| Dagster | rejeitar | orquestrador | Apache-2.0 | 1.13.26 · 2026-10-09 | conflito `protobuf<7` com o backend [P] | 100 requires_dist | alto | PyPI; [P] |
| Airflow | rejeitar | orquestrador | Apache-2.0 | 3.3.2 · 2026-09-17 | não testado | 251 requires_dist | alto | PyPI |
| Ray | rejeitar | paralelismo distribuído | Apache-2.0 | 2.59.0 · 2026-10-02 | wheel cp313 arm64 [F] | wheel de 67,4 MB; 285 requires_dist | alto | PyPI |
| redis-py | adiar | só para lock/cache explícito, se surgir | MIT | 8.1.0 · 2026-07-30 | puro | 0,6 MB | baixo técnico; precisa de servidor | PyPI |
| ClickHouse | rejeitar agora | OLAP | Apache-2.0 | clickhouse-connect 1.10.1 · 2026-10-14 | wheel cp313 [F] | repo de 13,9 GB | alto: segunda autoridade | PyPI; GitHub API |
| BigQuery | adiar | só com requisito de ADH/clean room | Apache-2.0 | google-cloud-bigquery 3.46.2 · 2026-10-15 | puro | — | alto: autoridade paralela + custo | PyPI |
| Riskfolio-Lib | adiar | otimização de portfólio/CVaR | BSD-3-Clause | 7.4.0 · 2026-10-04; 7.3.0 · 2026-05-31 | resolve [D] (85 pacotes) | não medido | médio: 85 pacotes para algo que o scipy faz | `compile-riskfolio-lib.txt` |
| Bytewax | rejeitar | streaming | Apache-2.0 (repo) | 0.21.1 · 2024-11-25; "community-maintained" desde 2025-05 [F] | **não resolve** [D]: sem wheel cp313 | — | alto | `compile-bytewax.txt`; README (raw) |
| scikit-survival | rejeitar agora | análise de sobrevivência (maturação) | **GPL-3.0-or-later** | 0.28.0 · 2026-07-05 | resolve [D] (17 pacotes) | wheel de 0,9 MB | **alto: copyleft** | PyPI; `compile-scikit-survival.txt` |
| Prophet | rejeitar | forecasting automático (o catálogo D14 veta) | MIT | 1.5.0 · 2026-10-05; 1.4.0 · 2026-08-15 | resolve [D] (17 pacotes; cmdstan embutido [I]) | wheel de 12 MB | médio: binário Stan | `compile-prophet.txt` |

---

## 2. Justificativas e condições objetivas de mudança

### 2.1 Dados: DuckDB e Polars

- **Decisão:** adotar no lab, **provisoriamente**. Os dois já estão no `uv.lock` (duckdb 1.5.6, polars 1.44.2), e a regra do projeto é que entrem por benchmark, não por moda. Quem decide a permanência é o benchmark 2.1 (worker C), não esta matriz.
- **Licença/manutenção [F]:** ambos MIT; push em 2026-10-15; ~42k e ~40k estrelas. Nenhum dos dois está arquivado.
- **Polars 2.0.0 [F]:** saiu em 2026-10-06 e o `exclude-newer` o exclui. O pacote `polars` virou meta-pacote: o binário fica em `polars-runtime-32`. Não suba para 2.x nesta corrida (breaking changes não verificados).
- **DuckDB [I]:** o autoload de extensões conhecidas pode baixar binários de `extensions.duckdb.org` no primeiro uso (por exemplo, httpfs). No lab hermético, use `SET autoinstall_known_extensions=false; SET autoload_known_extensions=false;` (documentação; não testado aqui).
- **Muda a decisão se** o benchmark 2.1 mostrar ganho inferior a ~2× em tempo/memória sobre a implementação stdlib/numpy atual nas fixtures VOLC. Nesse caso, retire a dependência (stdlib resolve).
- **Fora do lab:** adiar. O Supabase/Postgres continua sendo a autoridade (D47). A evidência anterior [P] observou ~3.605 linhas/dia por conta, o que não pede engine OLAP.

### 2.2 Optuna

- **[D]:** 5.0.0 instala em 1 s, com 38 MB e 11 pacotes (SQLAlchemy 2.1.1, Alembic, colorlog, tqdm, PyYAML). `SuccessiveHalvingPruner` e `HyperbandPruner` existem. Um estudo de 40 trials em `InMemoryStorage` podou 37.
- **Por que não adotar já:** o SH/ASHA do swarm (D21) mede "degraus" em cliques/gasto/outcomes maduros sobre células sintéticas. Isso cabe em ~50 linhas de numpy, auditáveis e sem estado. O modelo do Optuna (trial → `report(step)` → `should_prune`) supõe uma função objetivo iterável, e não modela orçamento compartilhado nem interferência entre células.
- **Papel permitido:** oráculo de teste em venv separado, conferindo a implementação própria com a mesma semente e os mesmos cenários. Nunca toca campanha viva (X04 do catálogo).
- **Muda a decisão se** o worker E precisar de amostrador multiobjetivo/TPE, ou se a implementação própria divergir do oráculo e a correção custar mais que a dependência.

### 2.3 ConfSeq (só fontes; a sonda é do worker D)

- **[F]:**
  - Último release 0.0.11 em 2023-01-26.
  - Wheels só para cp37–cp310 (macOS universal2 até cp310). Para cp313 sobra o sdist, que pede compilador C++14 e headers do Boost.
  - `requires_dist` traz `pytest`, `matplotlib` e `multiprocess` como dependências de runtime.
  - O README diz, textualmente, que está "in early-stage development and should not be considered stable" e que os testes rodam em Python 3.7–3.10.
- **Decisão:** referência. Implemente as fronteiras de Waudby-Smith & Ramdas (Hoeffding/empirical-Bernstein para outcomes em [0,1]) em numpy. Se a sonda do worker D compilar, use o confseq apenas como oráculo de cobertura em simulação.
- **Muda a decisão se** surgir wheel oficial cp313 com CI ativo **e** os testes de cobertura do worker D passarem com outcome limitado.

### 2.4 Bandits: MABWiser, Vowpal Wabbit e OBP

- **MABWiser [D]:** 2.7.4 funciona em 3.13 com numpy 2.5.3, pandas 3.0.6 e sklearn 1.9.1 (TS e LinTS), sem warnings. Mas [F] o último release é de 2024-08-30 (mudança: `np.Inf`→`np.inf`) e o último push de 2024-09-05. Puxa seaborn/matplotlib (223 MB). Thompson Beta-Bernoulli e LinTS cabem em numpy. **Referência; adiar.**
- **Vowpal Wabbit [D]:** 9.11.9, wheel cp313 arm64, 6,2 MB, zero dependências; `--cb_explore_adf --epsilon 0.1` devolveu PMF. Ativo (release em 2026-09-27). É poderoso demais para o volume atual (uma conta, células pequenas) e opaco para auditoria. **Adiar.**
- **OBP [D]:** `obp==0.5.7` não resolve em cp313 porque depende de `torch==1.12`, que só tem wheels até cp310. Parado desde 2023-04-14. **Rejeitar como dependência.** IPW/SNIPW/DR servem de especificação para o avaliador off-policy do swarm.
- **Regra do projeto mantida:** bandits ficam em simulação, sem realocação real.
- **Muda a decisão se**:
  - o replay as-of tiver ≥10⁴ decisões contextuais com propensões logadas, o que justificaria VW;
  - ou o MABWiser voltar a ter release nos últimos 12 meses e a implementação numpy própria falhar nos testes.

### 2.5 scikit-learn e statsmodels

- Já estão no lock, com releases recentes (1.9.1 em 2026-09-10; 0.15.0 em 2026-08-27) e licença BSD-3. Cobrem:
  - o baseline RidgeCV do surrogate (D22);
  - `TimeSeriesSplit` para validação out-of-time;
  - calibração isotônica;
  - `sklearn.cluster.HDBSCAN`, o que dispensa o pacote `hdbscan` [P];
  - FDR Benjamini-Hochberg (`statsmodels.stats.multitest.multipletests`, D17).
- **Atenção [D]:** statsmodels 0.15.0 é incompatível com `google-meridian` (que exige <0.15). Mais um motivo para não trazer o Meridian.

### 2.6 LightGBM e CatBoost

- **Regra do projeto:** só depois de baseline linear + volume + validação temporal.
- **LightGBM [D]:**
  - `lib_lightgbm.dylib` linka `@rpath/libomp.dylib`, com `LC_RPATH` = `/opt/homebrew/opt/libomp/lib` e `/opt/local/lib/libomp`.
  - Nesta máquina, a sonda carregou `/opt/homebrew/Cellar/libomp/22.1.5/lib/libomp.dylib`. Funcionou porque o Homebrew já estava lá; este worker não instalou nada.
  - Em outro Mac sem libomp do Homebrew o import deve falhar [I]. Logo, o lab **não é hermético** com LightGBM em macOS.
  - A API `LGBMRegressor` falhou com "scikit-learn is required" porque o sklearn não é dependência declarada.
- **CatBoost [D]:** 1.2.10 funciona em cp313 arm64, mas o venv tem 331 MB (plotly, matplotlib, graphviz). O release é de 2026-02-18, há 8 meses. Por padrão grava `catboost_info/` no cwd [I]; nas sondas foi usado `allow_writing_files=False`.
- **Muda a decisão se** o worker S demonstrar:
  1. label econômico no grão válido;
  2. baseline RidgeCV calibrado;
  3. n ≥ ~5.000 linhas out-of-time [H: limiar a calibrar];
  4. ganho out-of-time com IC que exclui zero.
- Preferência entre os dois [I]: **LightGBM** em Linux/CI, que é leve, ou **CatBoost** se as categóricas dominarem e o peso for aceito.

### 2.7 PyMC Marketing (e Meridian)

- **[D]:** `pymc-marketing==1.2.0` **não resolve** contra o lock, por exigir `numpy>=2.0,<2.5` (o lock tem 2.5.3). Isolado, instala 51 pacotes e 408 MB, resolve para numpy 2.4.6, PyMC 6.3.2 e PyTensor 3.3.2, e leva 38,6 s no primeiro import (inclui o cache de fontes do matplotlib). Exige Python >=3.12.
- **Escopo:** MMM é agregado/semanal. Não explica sessão nem controle intradiário (regra do projeto). O shrinkage de D15 começa por Beta-Binomial/Gamma-Poisson empírico em scipy.
- **Meridian [D/F]:** não resolve contra o lock (`statsmodels<0.15`) e exige `tensorflow<2.22`, `tfp-nightly==0.26.0.dev20260130` e `numpy<2.4`. Rejeitado.
- **Muda a decisão se** houver ≥ ~2 anos de série semanal de gasto por canal com variação exógena **e** pergunta de orçamento entre canais. Mesmo assim, só em venv separado com numpy <2.5.

### 2.8 OR-Tools e CVXPY (verificadores)

- **[D]:** os dois resolvem o LP de brinquedo (3 unidades, teto 60, orçamento 100). A mesma solução `[60, 40, 0]` sai do `scipy.optimize.linprog(method='highs')` e do `scipy.optimize.milp` com o **scipy 1.18.1 que já está no lock**. Para A0/A1 do allocator, o scipy basta.
- **OR-Tools [D]:**
  - Fixa `protobuf>=6.33.1,<6.34`.
  - Junto com `google-ads==33.0.0` o resolver acha `protobuf 6.33.6`.
  - Contra o pin `protobuf==7.35.1` do backend, falha.
  - O `tools/freedom-lab/pyproject.toml` já registra essa decisão: OR-Tools dentro, google-ads fora.
- **CVXPY [D]:** 120 MB com 5 solvers nativos (CLARABEL, SCS, SCIPY, HIGHS, OSQP).
- **Muda a decisão se** o allocator precisar de restrições cônicas/quadráticas (CVXPY) ou de programação por restrições/roteamento combinatório (OR-Tools CP-SAT) que o HiGHS via scipy não expressa. O papel seguiria sendo de verificador, nunca de primeiro motor.

### 2.9 Ecossistema Google Ads

- **google-ads-python [F]:**
  - 34.0.0 saiu hoje, 2026-10-15 (API v26), fora da janela.
  - 33.0.0 (2026-09-23) trouxe v25_2 e removeu v21/v22.
  - O pacote 33 contém `v23`, `v24` e `v25` [D].
  - O backend fixa `google-ads>=33.0.0,<34` (`backend/requirements-dev.txt:29`).
  - **Decisão:** continua sendo a porta técnica (D38) fora do lab. **Dentro do lab, não entra.** O lab consome snapshots/fixtures tipados, e importar o SDK no lab abriria a tentação de chamar API.
  - **Muda a decisão se:** nunca dentro do lab nesta fase.
- **GAARF [P/F]:**
  - O pacote vivo migrou para `google/garf` (push 2026-10-15, Apache-2.0 [F]).
  - A evidência anterior provou que o parser devolve `0` para campo ausente, o que viola NULL≠0.
  - O `main` do garf ganhou actors de mutação.
  - O README do gaarf diz "This is not an officially supported Google product".
  - **Decisão:** referência de padrões (macros de data, templates), sem dependência.
  - **Muda a decisão se** o garf passar a preservar ausência (None), separar leitura de mutação em pacotes distintos **e** um benchmark contra o coletor canônico (D01) mostrar ganho. Isso exige ADR.
- **Google Ads MCP [D]:**
  - A 0.0.4 (anterior ao corte) expõe 3 tools: `search`, `get_resource_metadata` e `list_accessible_customers`. Não há tool de mutate.
  - O escopo OAuth pedido é `https://www.googleapis.com/auth/adwords`, que é escrita e leitura. O "read-only" vem só da superfície de tools, não da credencial.
  - No modo remoto, `run_server()` sobe `streamable-http` em `host="0.0.0.0"` e `PORT` padrão 8080, a mesma porta do Vite do VOLC, exposta em todas as interfaces.
  - **Experimento [D]:** uma `GoogleAdsRow` só com `campaign.id` passou pelo `format_output_row`. Saiu `metrics.impressions: 0`, `metrics.cost_micros: 0` e `quality_score: 0`, embora `"impressions" in row.metrics` seja `False`. **Viola NULL≠0.**
  - A versão é 0.0.x, com `mcp==2.0.0` fixo e 87 pacotes.
  - **Decisão:** adiar. Pode servir só como ferramenta de exploração de dev, com conta de teste, nunca como fonte de dado para o lab ou para decisão.
  - **Muda a decisão se** existir release ≥1.0 que preserve ausência, mais credencial com escopo efetivamente restrito (por exemplo, usuário com papel read-only na conta) e bind em `127.0.0.1`.
- **Developer Assistant [F]:**
  - Sem pacote PyPI.
  - Roda dentro de Antigravity/Claude Code, clona as client libraries e lê `~/google-ads.yaml`.
  - Gera **e executa** código "directly in your terminal".
  - A proibição de mutate não revisado é uma restrição de prompt (`AGENTS.md`/`CLAUDE.md`), não um bloqueio técnico.
  - **Decisão:** referência e ferramenta de dev, só sem credencial produtiva (D40). O VOLC já tem nota em `volc_ads/google_ads_api/assistant_for_devs_gads_api.md`.
- **Tightlock, ads-policy-monitor, ADSTA, IFTTA [F]:** todos Apache-2.0, sem PyPI e sem arquivamento. Valem como referência de padrões. Não copiar runtime mutador (ADSTA/IFTTA), não montar Firestore/BigQuery paralelo e não fazer upload de valor (Tightlock) sem contrato próprio.
- **Marketing Analytics Jumpstart:** rejeitar agora. É um stack BigQuery/Vertex completo, com último push em 2026-01-05 e 50 issues abertas.

### 2.10 Semântica (sentence-transformers, BERTopic, pgvector)

- **[P]:** o experimento anterior, em 200 termos PT-BR rotulados, mostrou clusters mistos ("manter" × "negativar") em todas as variantes. O HDBSCAN sobre embeddings teve ARI 0,005. A hipótese "negativar a intenção inteira" foi refutada.
- **[D]:** as duas libs resolvem contra o lock, com 41 e 51 pacotes, ambas via torch.
- **Decisão:**
  - sentence-transformers: adiar. Um spike offline em corpus sanitizado só faz sentido com métrica de pureza/overblocking e revisão humana.
  - BERTopic: rejeitar agora.
  - pgvector: adiar até o clustering em memória provar valor. A licença é a PostgreSQL License [F].

### 2.11 Infraestrutura opcional

- **Feast, Prefect, Dagster e Airflow:** rejeitar. O n8n é a autoridade de agenda e o lab usa CLI. Há conflitos concretos com o backend [P]:
  - Feast: `tenacity<9`;
  - Prefect: `fastapi>=0.139`;
  - Dagster: `protobuf<7`.
- **Ray:** rejeitar. Wheel de 67 MB e 285 requires_dist, para um motor que opera uma conta.
- **redis-py:** adiar. Só entra para lock/cache explícito com dono.
- **ClickHouse e BigQuery:**
  - ClickHouse: rejeitar agora.
  - BigQuery: adiar.
  - Os dois criariam uma segunda autoridade. Reavaliar só se o volume ou um requisito de ADH/clean room não couber em Postgres + Parquet/DuckDB, com benchmark.
- **Riskfolio-Lib:** adiar. São 85 pacotes, e CVaR/drawdown cabem em scipy (o CVaR de Rockafellar-Uryasev é um LP no `linprog`).
- **Bytewax:** rejeitar. Não resolve em cp313 [D], o último release é de 2024-11-25 e o README declara "community-maintained" desde maio de 2025 [F].
- **scikit-survival:** rejeitar por licença **GPL-3.0-or-later**. Se a maturação pedir sobrevivência, implemente Kaplan-Meier/hazard discreto em numpy.
- **Prophet:** rejeitar para maturação, conforme o catálogo (D14: "nada de Prophet automático").

---

## 3. Riscos de supply chain e licença

1. **Copyleft:** `scikit-survival` é GPL-3.0-or-later [F]. Incorporá-lo ao lab contaminaria a distribuição de qualquer artefato derivado. Rejeitado.
2. **Licenças não-SPDX ou ambíguas na GitHub API** (`NOASSERTION`):
   - Vowpal Wabbit: LICENSE próprio, copyright Microsoft 2012–2014 e Yahoo 2007–2012, "All rights reserved" seguido de termos BSD-like; o PyPI declara BSD-3.
   - pgvector: PostgreSQL License.
   - Campo de licença vazio ou só com texto de copyright no PyPI: `lightgbm`, `google-meridian`, `bytewax` e `polars`.
   - Antes de adotar, confira o arquivo LICENSE do sdist/wheel, não o metadado.
3. **Binários nativos pré-compilados pelo upstream:** duckdb, polars-runtime-32, catboost, lightgbm, ortools, vowpalwabbit, os solvers do CVXPY (clarabel, scs, osqp, highspy), ray e o cmdstan embutido no prophet [I]. A integridade depende dos hashes do `uv.lock`. Não há build reprodutível local.
4. **Dependência de biblioteca do sistema fora do lock:** o LightGBM no macOS carrega a `libomp` do Homebrew [D]. O lock não captura isso, então o ambiente não é hermético entre máquinas.
5. **Rede em tempo de execução:**
   - DuckDB: autoload/autoinstall de extensões [I].
   - sentence-transformers/BERTopic: download de modelos do Hugging Face Hub (o experimento anterior baixou 240 MB sem token [P]).
   - Telemetria anônima ligada por padrão em Prefect, Dagster e Ray (usage stats) [I, documentação; não verificado aqui].
   - Nenhuma dessas libs entra no lab.
6. **Projetos sem suporte oficial ou pré-1.0:**
   - GAARF: "not an officially supported Google product" [F].
   - Google Ads MCP: 0.0.x [F].
   - ConfSeq: "early-stage" [F].
   - Bytewax: comunitário desde 2025-05 [F].
   - MABWiser: sem release desde 2024-08 [F].
   - OBP: sem release desde 2023-04 [F].
7. **Superfície de credencial:** o MCP pede o escopo `adwords` completo e ouve em `0.0.0.0` no modo remoto [D]. O Developer Assistant executa código gerado com `~/google-ads.yaml` [F]. Nenhum dos dois roda com credencial produtiva no lab.
8. **Janela de frescor:** com `exclude-newer=2026-10-01`, tudo o que foi sondado tem ≥14 dias em 2026-10-15. Alguns ficaram perto do limite:
   - `pymc-marketing 1.2.0`: 2026-09-29;
   - `duckdb 1.5.6`: 2026-09-28;
   - `vowpalwabbit 9.11.9`: 2026-09-27.

   Ficaram de fora versões publicadas depois do corte: `polars 2.0.0`, `google-ads 34.0.0`, `google-ads-mcp 0.0.5`, `prophet 1.5.0`, `riskfolio-lib 7.4.0`, `ray 2.59.0`. O incidente do LiteLLM (versões 1.82.7/1.82.8 comprometidas em 2026-03-24, fontes secundárias [P]) justifica manter a janela.
9. **Conflitos de pin com autoridades existentes [D]:**
   - `pymc-marketing` × numpy 2.5.3 do lab;
   - `google-meridian` × statsmodels 0.15.0 do lab;
   - `ortools` × protobuf 7.35.1 do backend.

   Qualquer uma dessas libs, se um dia entrar, vai em venv separado, nunca no backend.
10. **Dependências de runtime estranhas:** `confseq` declara `pytest` como dependência de instalação [F]. `catboost` puxa `plotly` e `graphviz` [D]. `mabwiser` puxa `seaborn` [D].

---

## 4. Resumo das dependências do lab

- **Ficam:** numpy, scipy, statsmodels, scikit-learn (já no lock); duckdb e polars (provisórias, sujeitas ao benchmark 2.1).
- **Não entram nesta corrida:** todo o resto. Optuna e confseq podem aparecer como *oráculos de teste* em venv descartável, sem entrar no `pyproject.toml`.
- **O scipy do lock já cobre:** LP/MILP (`linprog`/`milp` com HiGHS, [D]), PCHIP (D18), quantis/CVaR e shrinkage empírico.

---

## 5. O que NÃO foi verificado

- **Benchmarks de desempenho** de DuckDB/Polars contra a implementação atual. São do worker C (2.1).
- **ConfSeq:** compilação a partir do sdist em cp313, cobertura e API. Ficam com o worker D.
- **Instalação real** (só resolução ou metadados) de: sentence-transformers, BERTopic, Riskfolio-Lib, scikit-survival, Prophet, garf, Feast, Prefect, Dagster, Airflow, Ray, ClickHouse, BigQuery, redis-py, pgvector e Meridian.
- **Conflitos de Feast/Prefect/Dagster com o backend:** vêm da evidência anterior [P] de 2026-10-14, em Python 3.14.6, e não foram refeitos aqui.
- **LightGBM sem Homebrew:** o import sem `libomp` do Homebrew não foi testado. A falha em outra máquina é inferência [I] baseada no `LC_RPATH`.
- **Telemetria:** a de Prefect/Dagster/Ray e o autoload de extensões do DuckDB vêm de conhecimento de documentação [I], não de inspeção de tráfego.
- **Comportamento do `google-ads-mcp` 0.0.5:** posterior ao corte, só a 0.0.4 foi inspecionada. O `main` atual pode ter tools diferentes.
- **Developer Assistant:** não foi instalado nem executado. A análise usa só o README.
- **Assinaturas e atestados:** sigstore/PEP 740 e attestations do PyPI não foram verificados. Hashes, só os do `uv.lock`.
- **Licenças:** os arquivos LICENSE dentro dos wheels não foram lidos, só o metadado do PyPI e a GitHub API. Para VW e pgvector foi lido o LICENSE do repositório.
- **`pushed_at`:** pode refletir push de bot ou de branch secundária, não necessariamente um commit no default branch.
- **Issues e segurança:** as issues abertas não foram triadas, e os advisories (GHSA/OSV) de nenhum pacote foram consultados.
