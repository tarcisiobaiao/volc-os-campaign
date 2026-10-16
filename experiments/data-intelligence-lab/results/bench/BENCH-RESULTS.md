# Bancada DuckDB × Polars × Python puro × contrato (SINTÉTICO)

> **Natureza:** dados sintéticos gerados por seed (`20261015`). Mede a operação central do replay, não um workload real do VOLC.

- Código: `experiments/data-intelligence-lab/src/volc_dil/bench/` (`dados.py`, `engines.py`, `worker.py`)
- Execução: `cd experiments/data-intelligence-lab && .venv/bin/python -I scripts/bench_executar.py` (~65 s) e `.venv/bin/python -I scripts/bench_replay_escala.py` (~7 s)
- Equivalência: `tests/data-intelligence/test_bench_equivalencia.py` (10 testes, < 1 s)
- JSON: `results/bench/bench_resultados.json` (manifesto, versões, máquina, threads, seed, sha256 dos Parquet) e `results/bench/replay_escala.json`

**Ambiente:** Apple M4, 10 CPUs, 16 GB, macOS 15.6 arm64; CPython 3.13.0; duckdb 1.5.6, polars 1.44.2, numpy 2.5.3, pandas 3.0.6 (não usado), sem pyarrow. Threads fixadas: `OMP_NUM_THREADS=POLARS_MAX_THREADS=4`, DuckDB `threads=4` (+ rodada com 1 thread em 1e5/1e6). DuckDB com `autoinstall_known_extensions=false` e `autoload_known_extensions=false` (verificado em `duckdb_settings()`; `parquet` e `json` já vêm embutidos). Cada medição roda num subprocesso `python -I`; tempo = mediana de 5 repetições após 1 aquecimento descartado (carga: mediana de 3); pico de RSS do filho via `os.wait4` (rusage daquele filho, não o máximo acumulado de `RUSAGE_CHILDREN`). Processo vazio: 14,9 MB.

## 1. A operação (igual nas quatro implementações)

1. corte `disponivel_em <= as_of`; 2. última versão por chave lógica (contando empates de versão — o contrato os recusa como `VersaoAmbigua`); 3. agregação por conta × campanha × dia × métrica somando devices **com a semântica do `agregar` do contrato** (membro sem valor anula o total e o pior estado vence; >1 moeda no grupo → total NULL, `moedas_misturadas`; total 0 → `zero_confirmado`); 4. join custo × receita por identidade **exata** (conta, campanha, dia), full outer, contribuição só com ambos com valor e mesma moeda, senão NULL + motivo.

Implementações: **contrato** (`Observacao` → `Snapshot.construir` → `agregar`), **python_puro** (tuplas + dicts, estilo do VOLC), **duckdb** (SQL com janelas, resultado materializado em tabela temporária), **polars** (lazy, `collect_all`).

O dataset tem as armadilhas de propósito: `nao_coletado`, `falha`, zero confirmado, preliminar→revisada, backfill de custo, 5% de unidades em USD, unidade-dia com um device em outra moeda, receita sob outra conta com o mesmo `entidade_id`.

## 2. Equivalência — demonstrada

| n alvo | linhas | linhas de resultado | sha256 do resultado canônico | engines iguais |
|---:|---:|---:|---|---|
| 1e3 | 1 084 | 112 | `cde2a261279cb9e2…` | contrato = python = duckdb = polars |
| 1e4 | 10 033 | 1 036 | `7c130a87d9167393…` | contrato = python = duckdb = polars |
| 1e5 | 99 833 | ~10 k | `eb1fffbcc2aab20a…` | contrato = python = duckdb(4t,1t) = polars(4t,1t) |
| 1e6 | 999 371 | ~107 k | `eca47c6214a5843f…` | python = duckdb(4t,1t) = polars(4t,1t) (contrato não rodado, §4) |

Contraprovas de semântica (todas passam = o erro é detectado):

- `SUM` cru do DuckDB e `sum()` do Polars **ignoram NULL**; Polars devolve **0** para um grupo todo nulo. A versão "ingênua" (soma crua) de cada engine dá hash diferente do correto e o teste acha o grupo em que o correto diz "sem valor" e o ingênuo inventou número (`test_sum_ingenuo_que_ignora_null_e_detectado`, `test_semantica_crua_das_engines_e_o_risco_documentado`).
- Grupo com membro `falha` + `nao_coletado` → total NULL, estado `falha`, `n_sem=2` em todas; BRL+USD no mesmo grupo → `moedas_misturadas` em todas; receita sob `acc-B` nunca pareia com custo de `acc-A`; empate de versão é contado igual em python/duckdb/polars e o contrato levanta; embaralhar a entrada não muda o hash; corte as_of remove revisões futuras.

## 3. Tempo, memória e tamanho

Tempos em ms (mediana). `carga` = JSONL→tuplas (python/contrato) ou Parquet→memória (duckdb/polars). `conv` = tuplas → objetos do contrato. `export` = resultado nativo → tuplas Python. `import` é do processo frio (oscila com cache de disco: Polars 51–550 ms, DuckDB 35–120 ms entre rodadas).

| n | engine | carga | conv | **operação** | export | carga+op+export | import | pico RSS (MB) |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1e3 | python_puro | 1,4 | – | **0,5** | 0 | 1,9 | 6 | 20 |
| | contrato | 0,9 | 3,9 | 18,5 | 0 | 23,3 | 4 | 28 |
| | duckdb | 1,2 | – | 6,8 | 0,4 | 8,4 | 120 | 115 |
| | polars | 0,3 | – | 1,0 | 0,1 | 1,4 | 51 | 75 |
| 1e4 | python_puro | 9,4 | – | 4,4 | 0 | 13,8 | 4 | 34 |
| | contrato | 9,1 | 35,5 | 187,6 | 0 | 232 | 4 | 71 |
| | duckdb | 6,1 | – | 11,5 | 1,2 | 18,8 | 39 | 148 |
| | polars | 0,6 | – | **1,8** | 0,6 | 3,0 | 52 | 97 |
| 1e5 | python_puro | 104,7 | – | 97,2 | 0 | 202 | 4 | 173 |
| | contrato | 92,4 | 454,3 | 2 112 | 0 | 2 659 | 4 | 336 |
| | duckdb (4t) | 53,4 | – | 75,2 | 10,9 | 140 | 43 | 274 |
| | duckdb (1t) | 29,2 | – | 121,8 | 10,9 | 162 | – | 217 |
| | polars (4t) | 3,2 | – | **11,3** | 4,9 | 19,4 | 63 | 253 |
| | polars (1t) | 2,7 | – | 24,3 | 6,3 | 33,3 | – | 166 |
| 1e6 | python_puro | 1 133 | – | 1 607 | 0 | 2 740 | 4 | 1 066 |
| | duckdb (4t) | 82,5 | – | 505 | 104 | 692 | 103 | 972 |
| | duckdb (1t) | 269 | – | 1 278 | 102 | 1 649 | – | 996 |
| | polars (4t) | 11,9 | – | **172** | 51,7 | 236 | 137 | 1 048 |
| | polars (1t) | 28,7 | – | 399 | 69,8 | 497 | – | 706 |

Polars `scan_parquet` + operação (lazy direto do arquivo): 1e5 = 11,6 ms; 1e6 = 152 ms (≈ ler + operar em memória).

**Artefatos** (mesmos dados):

| n | Parquet (zstd, writer nativo do Polars) | JSONL plano | JSON do contrato (`para_json`) |
|---:|---:|---:|---:|
| 1e3 | 13 KB | 156 KB | 781 KB |
| 1e4 | 80 KB | 1,4 MB | 7,2 MB |
| 1e5 | 768 KB | 14,3 MB | 71,9 MB |
| 1e6 | 8,1 MB | 143 MB | ~720 MB (inferido, linear: ~720 B/obs) |

Parquet é ~18× menor que o JSONL plano e ~94× menor que o JSON do contrato.

**Onde o replay v0 gasta tempo** (`replay_escala.json`, 20 dias, política `proportional`, 1 repetição):

| unidades | obs por snapshot (máx) | ms de `Snapshot.construir` por decisão | % do tempo total em snapshot |
|---:|---:|---:|---:|
| 9 | 234 | 3,8 | 90% |
| 51 | 1 326 | 22 | 90% |
| 201 | 5 226 | 86 | 90% |
| 501 | 13 026 | 217 | 91% |

≈ 17 µs por observação, dominados por `para_json` + `sha256` (perfil em 2·10⁴ obs: `sha256_de` 39% e `para_json` 34% do tempo total da operação; cada observação é serializada ~3× e hasheada ~2×). A política e a agregação são < 5%.

## 4. Veredito: "DuckDB + Polars melhoram de fato o replay atual?"

**Replay atual do VOLC (8 cenários dourados) — não.** `executar_replay()` leva **2,7 ms** (mediana) e o import do módulo 19 ms; `normalizar_linhas_google_ads` com a fixture de 8 linhas leva 0,45 ms; processo inteiro 110 ms de parede e 23 MB de RSS. Só o `import duckdb` (35–120 ms, +100 MB) ou `import polars` (50+ ms, +60 MB) custa 15–45× o replay inteiro. Não há volume, não há gargalo, e o trabalho é validação/classificação de dicionários aninhados — não é álgebra relacional.

**Replay econômico em volume — depende do tamanho, e o primeiro gargalo não é a engine:**

1. O caminho do **contrato** (objetos `Observacao` + `Snapshot`) é ~22× mais lento que tuplas Python planas na mesma operação (1e5: 2,1 s × 97 ms) e não cabe no orçamento em 1e6 (inferido: ~21 s/rep de operação + ~4,5 s de conversão + ~3,4 GB de RSS; não executado por isso). O ganho mais barato é tornar o `Snapshot` mais barato (pedido 1, §6) ou separar "validar na borda" de "cortar em volume".
2. **Polars lazy** é a engine mais rápida em todos os tamanhos ≥ 1e4 (1e6: 9,3× mais rápida que Python puro na operação, 11,6× ponta a ponta com carga), com a mesma resposta byte a byte.
3. **DuckDB** só passa o Python puro a partir de ~1e5 (1e6: 3,2× na operação) e fica 3× atrás do Polars aqui, com RSS parecido (~1 GB em 1e6). Suas vantagens (SQL, consulta direta a Parquet, out-of-core) não foram exercitadas por esta operação.
4. **Ponto de corte (critério: tempo poupado > custo de import + dependência):** em processo novo, Polars compensa a partir de **~1e5 observações por corte as_of** (operação poupada ≈ 85 ms > import ≈ 50–60 ms); em processo longo (import amortizado), já a partir de ~1e4. Abaixo de ~1e4, Python puro é mais rápido ou empata. Hoje os snapshots do replay v0 têm 0,2–13 mil observações: **ainda não compensa**; compensaria em backtests de ~1 000 campanhas × 30 dias × várias versões, ou rodando muitas seeds/políticas sobre o mesmo log (carga em Parquet + `scan_parquet`).

**Riscos registrados:**

- NULL em `SUM`/`sum()` (ambas ignoram; Polars dá 0 para tudo-nulo) — o plano usa `count`/`null_count` explícitos; teste de equivalência é o gate.
- `row_number()`/`unique(keep=...)` com empate de versão é não determinístico — a bancada **conta** empates (`n_empates`) em vez de escolher.
- Overflow: Polars soma `Int64` em `Int64`; DuckDB promove para `HUGEINT` (a bancada faz cast explícito para `BIGINT`). Sem risco nesta escala; em micros agregados de muitos anos pode haver.
- DuckDB **não lê DataFrame Polars sem pyarrow** (`ModuleNotFoundError: pyarrow` ao consultar o frame) — a troca entre as duas engines é por Parquet.
- `memory_limit` padrão do DuckDB = 12,7 GiB (80% da RAM) num Mac compartilhado: fixar explicitamente se for adotado.
- Autoload/autoinstall de extensões desligados e verificados; `enable_external_access` continua ligado (necessário para ler Parquet local).
- **Ambiente paralelo** `tools/freedom-lab/` usa duckdb 1.5.6 (igual) mas **polars 2.0.0** e CPython 3.14.6 (`tools/freedom-lab/DEPENDENCIAS.json`); este lab usa polars 1.44.2 / CPython 3.13. O plano usa `join(how="full", coalesce=True, nulls_equal=False)`, `replace_strict`, `pl.len()`, `n_unique` após `drop_nulls` — **não testado em polars 2.0**; o teste de equivalência deve rodar lá antes de qualquer reuso. Números de tempo não são transferíveis entre os dois ambientes.
- pandas não foi medido (opcional; sem pyarrow, inteiro anulável exigiria `Int64` e strings `object`).

## 5. Disco

Pico em `artifacts/bench/` ≈ 170 MB (JSONL de 1e6 = 143 MB + Parquets); tudo apagado ao fim (`artifacts/` = 0 B). Versionado: só JSON/MD de resultado (< 30 KB) e o MANIFEST/fixture do replay (149 KB).

## 6. Pedidos de mudança no contrato (para o coordenador; não aplicados)

1. `Snapshot.construir`: hashear conteúdo só quando há empate (`len(empatadas) > 1`) e reaproveitar um único `sha256`/`para_json` por observação para ordenar e para o fingerprint. Estimativa (inferida do perfil): −35% a −50% do tempo do replay v0.
2. `contribuicao` só aceita `Observacao`; falta `contribuicao` entre `Agregado`s com identidade/janela explícitas — a bancada teve de reimplementar o join (`engines._juntar`).
3. Observação sem valor tem `moeda=None`: um NULL não pode ser atribuído a um grupo de moeda. Declarar a moeda esperada da unidade (na `ChaveUnidade` ou num registro de unidade) evita ambiguidade.
4. `estado=medido` com valor 0 é aceito no lab e recusado no Orakul (`semantica.py:69`) — alinhar.
