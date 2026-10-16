# Bancada DuckDB × Polars × Python puro × contrato (SINTÉTICO)

> **Gerado** por `scripts/bench_relatorio.py` a partir de `results/bench/bench_resultados.json` e `results/bench/replay_escala.json`; não editar à mão. Dados **sintéticos** (seed `20261015`); mede a operação central do replay, não um workload real do VOLC.

- Execução: `.venv/bin/python -I scripts/bench_executar.py`, `scripts/bench_replay_escala.py`, depois `scripts/bench_relatorio.py`.
- Equivalência: `tests/data-intelligence/test_bench_equivalencia.py` (15 testes).
- Manifesto: `codigo_sha256=e624195b4da876c8…`, `resultado_sha256=e999e504ee87d357…`, `fingerprint=e750fefcb7bfaf29…`; escala: `codigo_sha256=6b7fd04e5dadd3de…`, `resultado_sha256=5f44d41bc55fa609…`.

**Ambiente:** Apple M4, 10 CPUs, 16 GiB, macOS-15.6-arm64-arm-64bit-Mach-O; CPython 3.13.0; duckdb 1.5.6, polars 1.44.2, numpy 2.5.3, pandas 3.0.6 (não usado), sem pyarrow. Threads: {"OMP_NUM_THREADS": 4, "POLARS_MAX_THREADS": 4, "duckdb_threads": 4, "extra": "1 thread em n>=1e5"}. DuckDB: {"autoinstall_known_extensions": "false", "autoload_known_extensions": "false", "memory_limit": "12.7 GiB", "threads": "4"}. Cada medição num subprocesso `python -I`; tempo = mediana de 5 repetições após 1 aquecimento (carga/conversão/exportação: mediana de 3, ou 2); pico de RSS do próprio filho via `os.wait4`. Processo vazio: 15.1 MB.

## 1. A operação (igual nas quatro implementações)

0. validação de linha (estado×valor×moeda; todas recusam com `LinhaMalformada`); 1. corte `disponivel_em <= as_of`; 2. reentrega idêntica deduplicada e contada, versões diferentes no mesmo instante → `EmpateDeVersao` (contrato: `VersaoAmbigua`); 3. agregação por conta × campanha × dia × métrica com a semântica do `agregar` (membro sem valor anula, pior estado vence, >1 moeda → `moedas_misturadas`, 0 → `zero_confirmado`); 4. join custo × receita por identidade exata, contribuição só com a mesma moeda (comparação NULL-segura).

Implementações: **contrato** (`Observacao` → `Snapshot.construir` → `agregar`), **python_puro** (tuplas + dicts), **duckdb** (SQL, resultado em tabela temporária), **polars** (lazy, `collect_all`, lendo Parquet) e **polars_de_tuplas** (mesma operação, mas partindo de tuplas Python em memória: paga a conversão).

## 2. Equivalência

| n alvo | linhas | linhas de resultado | sha256 do resultado | engines | todas iguais | duplicatas exatas |
|---:|---:|---:|---|---|---|---:|
| 1e+03 | 1084 | 140 | `794a09c4384ea412…` | python_puro, contrato, duckdb, polars, polars_de_tuplas | sim | 0 |
| 1e+04 | 10033 | 1064 | `dc2b726736a93297…` | python_puro, contrato, duckdb, polars, polars_de_tuplas | sim | 0 |
| 1e+05 | 99833 | 10500 | `8e98f2df485201f1…` | python_puro, contrato, duckdb, duckdb_1thread, polars, polars_1thread, polars_de_tuplas | sim | 0 |
| 1e+06 | 999371 | 104160 | `43efa06abc8305f8…` | python_puro, duckdb, duckdb_1thread, polars, polars_1thread, polars_de_tuplas | sim | 0 |

Fora do caminho feliz (testes `test_f103_*`): reentrega idêntica é deduplicada e dá a MESMA linha nas quatro engines (antes DuckDB/Polars somavam em dobro); versões diferentes no mesmo instante, micros com moeda nula, `medido` sem micros, `zero_confirmado` ≠ 0 e estado fora do vocabulário levantam a MESMA exceção nas quatro. A versão "ingênua" (soma crua: DuckDB e Polars ignoram NULL; Polars dá 0 para grupo todo nulo) é pega pelo hash.

## 3. Tempo, memória e tamanho

Tempos em ms (mediana). `carga` = JSONL→tuplas (python/contrato/polars_de_tuplas) ou Parquet→memória (duckdb/polars). `conv` = tuplas → objetos do contrato ou → DataFrame Polars. `import` é do processo frio e oscila com o cache de disco.

| n | engine | carga | conv | **operação** | export | total (carga+conv+op+export) | import | pico RSS (MB) |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1e+03 | python_puro | 0.9 | – | **0.6** | 0.0 | 1.5 | 3 | 19.8 |
|  | contrato | 1.0 | 5.7 | **13.4** | 0.0 | 20.1 | 4 | 28.7 |
|  | duckdb | 1.1 | – | **7.6** | 0.8 | 9.5 | 120 | 120.2 |
|  | polars | 0.3 | – | **3.7** | 0.2 | 4.2 | 59 | 80.8 |
|  | polars_de_tuplas | 0.9 | 0.5 | **2.3** | 0.4 | 4.2 | 60 | 71.8 |
| 1e+04 | python_puro | 9.4 | – | **6.7** | 0.0 | 16.0 | 4 | 33.9 |
|  | contrato | 9.5 | 54.8 | **149** | 0.0 | 213 | 4 | 78.6 |
|  | duckdb | 5.9 | – | **15.2** | 1.3 | 22.4 | 36 | 160.6 |
|  | polars | 0.6 | – | **4.5** | 0.6 | 5.7 | 54 | 116.1 |
|  | polars_de_tuplas | 9.5 | 4.6 | **5.5** | 0.6 | 20.3 | 53 | 108.3 |
| 1e+05 | python_puro | 102 | – | **151** | 0.0 | 254 | 3 | 172.9 |
|  | contrato | 95.2 | 581 | **1 747** | 0.0 | 2 423 | 4 | 346.9 |
|  | duckdb | 53.0 | – | **79.7** | 11.6 | 144 | 90 | 320.6 |
|  | duckdb_1thread | 29.4 | – | **142** | 10.4 | 182 | 103 | 250.1 |
|  | polars | 3.2 | – | **26.9** | 5.5 | 35.5 | 58 | 368.6 |
|  | polars_1thread | 2.7 | – | **58.1** | 9.2 | 70.0 | 89 | 176.9 |
|  | polars_de_tuplas | 94.6 | 45.0 | **28.5** | 5.1 | 173 | 54 | 388.2 |
| 1e+06 | python_puro | 1 116 | – | **2 471** | 0.0 | 3 587 | 5 | 1113.2 |
|  | duckdb | 98.1 | – | **594** | 108 | 800 | 114 | 1081.0 |
|  | duckdb_1thread | 285 | – | **1 493** | 105 | 1 882 | 111 | 1067.2 |
|  | polars | 12.8 | – | **481** | 59.6 | 553 | 108 | 1809.8 |
|  | polars_1thread | 29.5 | – | **858** | 71.7 | 960 | 105 | 905.1 |
|  | polars_de_tuplas | 1 131 | 532 | **409** | 53.3 | 2 126 | 111 | 1985.5 |

| n | Parquet (zstd, writer do Polars) | JSONL plano | JSON do contrato (`para_json`) | tuplas → Polars (ms, 1 medição) |
|---:|---:|---:|---:|---:|
| 1e+03 | 0.013 MB | 0.16 MB | 0.78 MB | 144 |
| 1e+04 | 0.080 MB | 1.44 MB | 7.23 MB | 5.3 |
| 1e+05 | 0.768 MB | 14.32 MB | 71.95 MB | 98.6 |
| 1e+06 | 8.098 MB | 143.37 MB | ~720 MB (inferido: 721 B/obs) | 640 |

**Onde o replay v0 gasta tempo** (`replay_escala.json`, 20 dias, política `proportional`, sem medição de preliminar, 1 repetição — ordem de grandeza):

| unidades | obs por snapshot (máx) | ms de `Snapshot.construir` por decisão | % do tempo em snapshot |
|---:|---:|---:|---:|
| 9 | 234 | 2.59 | 80% |
| 51 | 1326 | 13.88 | 82% |
| 201 | 5226 | 55.66 | 84% |
| 501 | 13026 | 145.78 | 84% |

Perfil de `Snapshot.construir` em 20078 observações (0.345 s): `sha256_de` 41% e `para_json` 27% do tempo cumulativo (frações de tempo cumulativo (podem se sobrepor: sha256_de inclui serialização)); 37063 chamadas de `para_json` e 12433 de `sha256_de`.

## 4. Veredito: "DuckDB + Polars melhoram de fato o replay atual?"

**Replay atual do VOLC (cenários dourados) — não.** `executar_replay()` = 3.6 ms (mediana), import 23 ms, `normalizar_linhas_google_ads` com 8 linhas = 0.56 ms; processo inteiro 139 ms, 24.0 MB. Só importar DuckDB custou 36–120 ms e Polars 53–111 ms nesta bancada. Não há volume nem álgebra relacional ali.

**Replay econômico em volume — depende do tamanho, e o primeiro gargalo não é a engine:**

1. O caminho do **contrato** é 12× mais lento que tuplas Python na mesma operação em 1e+05 (1 747 × 151 ms), e `Snapshot.construir` domina o replay v0 (tabela acima). Acima de 1e+05 o contrato não foi rodado (estouraria o orçamento de tempo/memória — inferido por extrapolação linear).
2. Em 1e+06, na operação: Polars (Parquet) 5.1× e DuckDB 4.2× mais rápidos que Python puro. Se os dados já estão em tuplas Python (caso do replay), Polars incluindo conversão + exportação fica 2.5× mais rápido que Python puro.
3. **Pontos de corte** (menor tamanho da grade em que a engine fica mais barata que Python puro):

| Cenário | Polars | DuckDB |
|---|---|---|
| dados em tuplas Python, processo longo (conv+op+export vs op) | entre 1e+04 e 1e+05 | – (sem leitor direto de tuplas sem pyarrow/pandas) |
| idem, processo novo (+ import) | entre 1e+04 e 1e+05 | – |
| dados em repouso (Parquet vs JSONL), processo longo | entre 1e+03 e 1e+04 | entre 1e+04 e 1e+05 |
| idem, processo novo (+ import) | entre 1e+04 e 1e+05 | entre 1e+04 e 1e+05 |

Os snapshots do replay v0 medidos têm até 13026 observações; a decisão sobre adotar uma engine deve usar a linha "dados em tuplas Python" (o replay mantém o log em memória), não a de Parquet. O ganho mais barato e certo é reduzir o custo do `Snapshot` (pedido 1, §6).

**Riscos registrados:**

- NULL em `SUM`/`sum()` (ambas ignoram; Polars dá 0 para grupo todo nulo); comparação `<>` com NULL é lógica de 3 valores — o plano usa `count`/`null_count`, `IS DISTINCT FROM` e `ne_missing`.
- Reentrega duplicada é somada em dobro por um GROUP BY ingênuo — o plano faz `DISTINCT`/`unique()` e conta; versões diferentes no mesmo instante levantam.
- `row_number()`/`unique(keep=...)` com empate é não determinístico — o plano não escolhe, recusa.
- Overflow: Polars soma `Int64` em `Int64`; DuckDB promove para `HUGEINT` (cast explícito para `BIGINT`).
- DuckDB não lê DataFrame Polars sem pyarrow — a troca entre as engines é por Parquet.
- `memory_limit` padrão do DuckDB (80% da RAM) num Mac compartilhado: fixar se adotado. Autoload/autoinstall desligados e verificados.
- Ambiente paralelo `tools/freedom-lab/`: duckdb 1.5.6 (igual) mas **polars 2.0.0** e CPython 3.14 (`tools/freedom-lab/DEPENDENCIAS.json`). O plano usa `join(how="full", coalesce=True, nulls_equal=False)`, `replace_strict`, `ne_missing`, `unique()` — não testado em polars 2.0; tempos não são transferíveis.
- pandas não medido.

## 5. Disco

Pico de artefatos simultâneos ≈ 151 MB (Parquet + JSONL do maior tamanho; cada tamanho é apagado antes do próximo) em `artifacts/bench/` (gitignored); tudo apagado ao fim. Versionado: só JSON/MD de resultado.

## 6. Pedidos de mudança no contrato (não aplicados)

- `Snapshot.construir`: hashear conteúdo só quando há empate e reaproveitar um único `sha256`/`para_json` por observação para ordenar e para o fingerprint (ver perfil acima).
- `contribuicao` entre `Agregado`s com identidade/janela explícitas (a bancada reimplementa o join em `engines._juntar`).
- Moeda esperada da unidade declarada (observação sem valor tem `moeda=None` e não pode ser atribuída a um grupo de moeda).
- `medido` com valor 0 é aceito no lab e recusado no Orakul (`semantica.py:69`) — alinhar.
