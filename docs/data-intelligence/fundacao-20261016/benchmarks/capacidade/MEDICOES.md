# Medições PostgreSQL descartável — todas (GERADO)

> Gerado por `fundacao_capacidade_modelo.py` a partir de `pg_medicoes.json`. Nenhuma linha omitida. Latências por chamada medidas no servidor (`clock_timestamp`), consultas `as_of` por EXECUTE (planejamento incluído); globais medidas no cliente psql (inclui ~10–20 ms de processo).

- PostgreSQL 16.11 (Homebrew) on aarch64-apple-darwin24.6.0, c; config {'autovacuum': 'off', 'block_size': '8192', 'default_toast_compression': 'pglz', 'fsync': 'on', 'shared_buffers': '32768', 'synchronous_commit': 'on', 'wal_level': 'minimal', 'work_mem': '65536'}; amostras {'as_of_ponto': 5000, 'snapshot': 60, 'ingestao': 60, 'global': 5}
- duração 1.643 s; pico amostrado do diretório do cluster 3,20 GiB; cluster apagado: True
- linhas `dil_obs_0001` vêm da rodada dedicada (`pg_medicoes_dil_obs.json`): {'duracao_s': 877.5725960731506, 'cluster_apagado': True, 'pico_amostrado_dir_cluster_bytes': 2503589990, 'amostras': {'as_of_ponto': 5000, 'snapshot': 60, 'ingestao': 60, 'global': 5}}

## Tamanho

| variante | partição | n alvo | linhas | heap B/linha | índices B/linha | total B/valor | índices por nome (MB) |
|---|---|---:|---:|---:|---:|---:|---|
| longo | não | 1e+05 | 99000 | 167,6 | 91,1 | 258,8 | longo_h_1e05_as_of 6.4, longo_h_1e05_brin 0.0, longo_h_1e05_pk 2.1 |
| longo | sim | 1e+05 | 99000 | 168,6 | 102,7 | 271,2 | longo_p_1e05_2026_07_conta_id_nivel_entidade_id_segmento_di_idx 2.2, longo_p_1e05_2026_07_disponivel_em_idx 0.0, longo_p_1e05_2026_07_pkey 1.0, longo_p_1e05_2026_08_conta_id_nivel_entidade_id_segmento_di_idx 2.2, longo_p_1e05_2026_08_disponivel_em_idx 0.0, longo_p_1e05_2026_08_pkey 1.0, longo_p_1e05_2026_09_conta_id_nivel_entidade_id_segmento_di_idx 2.0, longo_p_1e05_2026_09_disponivel_em_idx 0.0, longo_p_1e05_2026_09_pkey 0.9, longo_p_1e05_2026_10_conta_id_nivel_entidade_id_segmento_di_idx 0.0, longo_p_1e05_2026_10_disponivel_em_idx 0.0, longo_p_1e05_2026_10_pkey 0.0 |
| texto | não | 1e+05 | 99000 | 230,1 | 118,7 | 348,8 | texto_h_1e05_as_of 9.0, texto_h_1e05_brin 0.0, texto_h_1e05_pk 2.1 |
| largo | não | 1e+05 | 99990 | 205,2 | 82,3 | 35,9 | largo_h_1e05_as_of 5.6, largo_h_1e05_brin 0.0, largo_h_1e05_pk 2.2 |
| jsonb | não | 1e+05 | 99990 | 431,7 | 82,3 | 64,3 | jsonb_h_1e05_as_of 5.6, jsonb_h_1e05_brin 0.0, jsonb_h_1e05_pk 2.2 |
| v21 | não | 1e+05 | 99990 | 630,7 | 216,0 | 105,8 | v21_h_1e05_cix 5.6, v21_h_1e05_gd 0.1, v21_h_1e05_gm 4.6, v21_h_1e05_pk 3.0, v21_h_1e05_rix 0.7, v21_h_1e05_uq 6.5 |
| longo | não | 1e+06 | 999900 | 167,3 | 90,3 | 257,6 | longo_h_1e06_as_of 64.6, longo_h_1e06_brin 0.0, longo_h_1e06_pk 21.4 |
| longo | sim | 1e+06 | 999900 | 167,3 | 99,6 | 267,0 | longo_p_1e06_2026_07_conta_id_nivel_entidade_id_segmento_di_idx 22.3, longo_p_1e06_2026_07_disponivel_em_idx 0.0, longo_p_1e06_2026_07_pkey 10.4, longo_p_1e06_2026_08_conta_id_nivel_entidade_id_segmento_di_idx 22.3, longo_p_1e06_2026_08_disponivel_em_idx 0.0, longo_p_1e06_2026_08_pkey 10.4, longo_p_1e06_2026_09_conta_id_nivel_entidade_id_segmento_di_idx 20.1, longo_p_1e06_2026_09_disponivel_em_idx 0.0, longo_p_1e06_2026_09_pkey 9.4, longo_p_1e06_2026_10_conta_id_nivel_entidade_id_segmento_di_idx 0.0, longo_p_1e06_2026_10_disponivel_em_idx 0.0, longo_p_1e06_2026_10_pkey 0.0 |
| texto | não | 1e+06 | 999900 | 230,4 | 118,0 | 348,4 | texto_h_1e06_as_of 91.0, texto_h_1e06_brin 0.0, texto_h_1e06_pk 21.4 |
| largo | não | 1e+06 | 999900 | 204,9 | 81,5 | 35,8 | largo_h_1e06_as_of 56.3, largo_h_1e06_brin 0.0, largo_h_1e06_pk 21.4 |
| jsonb | não | 1e+06 | 999900 | 431,3 | 81,5 | 64,1 | jsonb_h_1e06_as_of 56.3, jsonb_h_1e06_brin 0.0, jsonb_h_1e06_pk 21.4 |
| v21 | não | 1e+06 | 999900 | 630,4 | 220,3 | 106,3 | v21_h_1e06_cix 56.3, v21_h_1e06_gd 1.1, v21_h_1e06_gm 50.8, v21_h_1e06_pk 30.1, v21_h_1e06_rix 7.1, v21_h_1e06_uq 64.7 |
| longo | não | 1e+07 | 9999000 | 167,2 | 90,2 | 257,5 | longo_h_1e07_as_of 646.1, longo_h_1e07_brin 0.1, longo_h_1e07_pk 214.2 |
| longo | sim | 1e+07 | 9999000 | 167,2 | 99,3 | 266,5 | longo_p_1e07_2026_07_conta_id_nivel_entidade_id_segmento_di_idx 222.6, longo_p_1e07_2026_07_disponivel_em_idx 0.0, longo_p_1e07_2026_07_pkey 103.5, longo_p_1e07_2026_08_conta_id_nivel_entidade_id_segmento_di_idx 222.6, longo_p_1e07_2026_08_disponivel_em_idx 0.0, longo_p_1e07_2026_08_pkey 103.5, longo_p_1e07_2026_09_conta_id_nivel_entidade_id_segmento_di_idx 201.0, longo_p_1e07_2026_09_disponivel_em_idx 0.0, longo_p_1e07_2026_09_pkey 93.5, longo_p_1e07_2026_10_conta_id_nivel_entidade_id_segmento_di_idx 0.0, longo_p_1e07_2026_10_disponivel_em_idx 0.0, longo_p_1e07_2026_10_pkey 0.0 |
| dil_obs_0001 | não | 1e+05 | 99000 | 630,7 | 449,6 | 1.080 | ix_obs_chave_base 11.8, ix_obs_entidade 2.4, ix_obs_lote 0.6, ix_obs_run 0.6, observacao_pkey 2.1, uq_obs_chave_idempotencia 11.8, uq_obs_versao 13.0 |
| dil_obs_0001 | não | 1e+06 | 999900 | 630,4 | 453,3 | 1.084 | ix_obs_chave_base 119.3, ix_obs_entidade 28.9, ix_obs_lote 6.2, ix_obs_run 6.2, observacao_pkey 21.4, uq_obs_chave_idempotencia 119.3, uq_obs_versao 131.0 |

## Latência por chamada (ms)

| variante | partição | n alvo | medida | n | min | p50 | p95 | p99 | máx | média | desvio |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| longo | não | 1e+05 | as_of_ponto | 5000 | 0,021 | 0,036 | 0,103 | 0,294 | 3,543 | 0,051 | 0,096 |
| longo | não | 1e+05 | snapshot_conta_dia | 60 | 0,224 | 0,556 | 0,925 | 1,702 | 1,837 | 0,562 | 0,293 |
| longo | não | 1e+05 | ingestao_lote_1000_cru | 60 | 8,050 | 13,236 | 21,670 | 22,761 | 23,359 | 14,299 | 3,784 |
| longo | não | 1e+05 | ingestao_lote_1000_dedup | 60 | 10,199 | 16,291 | 29,069 | 32,412 | 58,528 | 17,404 | 7,350 |
| longo | não | 1e+05 | ingestao_lote_5000_cru | 60 | 36,003 | 66,684 | 150,507 | 226,244 | 315,827 | 78,567 | 45,592 |
| longo | não | 1e+05 | ingestao_lote_5000_dedup | 60 | 54,645 | 104,432 | 214,699 | 273,999 | 281,804 | 117,199 | 47,597 |
| longo | sim | 1e+05 | as_of_ponto | 5000 | 0,030 | 0,075 | 0,296 | 1,472 | 21,354 | 0,140 | 0,531 |
| longo | sim | 1e+05 | snapshot_conta_dia | 60 | 0,090 | 0,178 | 0,449 | 1,082 | 2,117 | 0,248 | 0,290 |
| longo | sim | 1e+05 | ingestao_lote_1000_cru | 60 | 8,557 | 16,800 | 34,523 | 61,975 | 99,219 | 20,779 | 13,788 |
| longo | sim | 1e+05 | ingestao_lote_1000_dedup | 60 | 12,617 | 22,248 | 78,956 | 96,890 | 102,608 | 27,617 | 18,175 |
| longo | sim | 1e+05 | ingestao_lote_5000_cru | 60 | 54,383 | 86,885 | 253,448 | 277,169 | 460,462 | 105,871 | 66,109 |
| longo | sim | 1e+05 | ingestao_lote_5000_dedup | 60 | 78,694 | 126,826 | 465,398 | 1.447 | 2.990 | 230,149 | 405,219 |
| v21 | não | 1e+05 | as_of_ponto | 5000 | 0,020 | 0,048 | 0,104 | 0,328 | 12,647 | 0,063 | 0,225 |
| longo | não | 1e+06 | as_of_ponto | 5000 | 0,023 | 0,058 | 0,138 | 0,242 | 5,022 | 0,066 | 0,099 |
| longo | não | 1e+06 | snapshot_conta_dia | 60 | 3,237 | 4,785 | 8,549 | 9,336 | 14,373 | 5,279 | 1,772 |
| longo | não | 1e+06 | ingestao_lote_1000_cru | 60 | 9,706 | 14,609 | 43,818 | 50,269 | 123,030 | 19,749 | 16,121 |
| longo | não | 1e+06 | ingestao_lote_1000_dedup | 60 | 11,376 | 20,708 | 36,352 | 40,488 | 41,415 | 22,622 | 6,752 |
| longo | não | 1e+06 | ingestao_lote_5000_cru | 60 | 58,330 | 95,297 | 272,866 | 542,560 | 644,644 | 127,061 | 105,463 |
| longo | não | 1e+06 | ingestao_lote_5000_dedup | 60 | 71,949 | 126,025 | 329,300 | 411,956 | 412,878 | 152,310 | 77,734 |
| longo | sim | 1e+06 | as_of_ponto | 5000 | 0,031 | 0,051 | 0,286 | 0,869 | 8,662 | 0,106 | 0,263 |
| longo | sim | 1e+06 | snapshot_conta_dia | 60 | 0,177 | 1,990 | 10,421 | 15,193 | 23,461 | 3,293 | 3,908 |
| longo | sim | 1e+06 | ingestao_lote_1000_cru | 60 | 9,107 | 17,770 | 38,784 | 56,544 | 94,352 | 20,830 | 12,818 |
| longo | sim | 1e+06 | ingestao_lote_1000_dedup | 60 | 7,557 | 21,005 | 68,607 | 82,071 | 100,200 | 26,873 | 16,778 |
| longo | sim | 1e+06 | ingestao_lote_5000_cru | 60 | 68,715 | 97,615 | 246,721 | 265,709 | 354,771 | 124,516 | 60,026 |
| longo | sim | 1e+06 | ingestao_lote_5000_dedup | 60 | 65,254 | 131,834 | 532,614 | 909,557 | 1.463 | 207,195 | 219,955 |
| v21 | não | 1e+06 | as_of_ponto | 5000 | 0,021 | 0,061 | 0,681 | 3,168 | 21,019 | 0,237 | 0,851 |
| longo | não | 1e+07 | as_of_ponto | 5000 | 0,023 | 0,216 | 0,530 | 1,254 | 21,009 | 0,259 | 0,430 |
| longo | não | 1e+07 | snapshot_conta_dia | 60 | 21,750 | 34,404 | 59,866 | 78,134 | 185,698 | 39,288 | 22,283 |
| longo | não | 1e+07 | ingestao_lote_1000_cru | 60 | 5,444 | 13,189 | 42,322 | 59,899 | 184,938 | 18,927 | 24,353 |
| longo | não | 1e+07 | ingestao_lote_1000_dedup | 60 | 5,407 | 11,022 | 18,531 | 18,688 | 19,281 | 11,902 | 3,353 |
| longo | não | 1e+07 | ingestao_lote_5000_cru | 60 | 27,935 | 54,656 | 163,120 | 225,722 | 227,494 | 72,379 | 44,775 |
| longo | não | 1e+07 | ingestao_lote_5000_dedup | 60 | 38,074 | 69,019 | 166,960 | 246,530 | 409,729 | 85,389 | 56,012 |
| longo | sim | 1e+07 | as_of_ponto | 5000 | 0,032 | 0,187 | 0,498 | 1,327 | 16,994 | 0,253 | 0,414 |
| longo | sim | 1e+07 | snapshot_conta_dia | 60 | 0,657 | 14,723 | 24,100 | 88,366 | 142,001 | 18,724 | 19,958 |
| longo | sim | 1e+07 | ingestao_lote_1000_cru | 60 | 6,507 | 14,873 | 34,746 | 42,140 | 43,299 | 17,025 | 8,037 |
| longo | sim | 1e+07 | ingestao_lote_1000_dedup | 60 | 9,592 | 17,941 | 31,804 | 38,027 | 52,134 | 19,269 | 7,147 |
| longo | sim | 1e+07 | ingestao_lote_5000_cru | 60 | 37,132 | 63,457 | 109,860 | 325,982 | 350,398 | 77,095 | 54,879 |
| longo | sim | 1e+07 | ingestao_lote_5000_dedup | 60 | 42,352 | 67,388 | 128,427 | 137,671 | 182,600 | 76,446 | 24,842 |
| dil_obs_0001 | não | 1e+05 | as_of_ponto | 5000 | 0,016 | 0,018 | 0,103 | 0,192 | 1,045 | 0,032 | 0,040 |
| dil_obs_0001 | não | 1e+06 | as_of_ponto | 5000 | 0,017 | 0,069 | 0,701 | 2,043 | 40,158 | 0,217 | 0,876 |

## Consultas globais (s, mediana após 1 aquecimento; todas as repetições no JSON)

| variante | n alvo | medida | chaves | p50 s | máx s | repetições (s) |
|---|---:|---|---:|---:|---:|---|
| dil_obs_0001 | 1e+05 | as_of_global_funcao_meio | 44000 | 0,124 | 0,159 | 0.375, 0.159, 0.124, 0.119, 0.138, 0.124 |
| dil_obs_0001 | 1e+05 | as_of_global_consulta_meio | 44000 | 0,035 | 0,046 | 0.028, 0.029, 0.046, 0.035, 0.034, 0.036 |
| dil_obs_0001 | 1e+05 | as_of_global_consulta_linha_inteira_meio | 44000 | 0,097 | 0,118 | 0.047, 0.061, 0.097, 0.118, 0.101, 0.054 |
| dil_obs_0001 | 1e+05 | as_of_global_funcao_fim | 90000 | 0,994 | 1,530 | 1.295, 0.936, 1.530, 0.982, 0.994, 1.141 |
| dil_obs_0001 | 1e+05 | as_of_global_consulta_fim | 90000 | 0,021 | 0,022 | 0.028, 0.021, 0.022, 0.020, 0.021, 0.020 |
| dil_obs_0001 | 1e+05 | as_of_global_consulta_linha_inteira_fim | 90000 | 0,066 | 0,104 | 0.035, 0.052, 0.066, 0.100, 0.063, 0.104 |
| dil_obs_0001 | 1e+05 | latest_view | – | 0,864 | 1,432 | 1.214, 0.694, 0.647, 0.958, 1.432, 0.864 |
| dil_obs_0001 | 1e+06 | as_of_global_funcao_meio | 444400 | 8,498 | 9,856 | 16.411, 9.856, 8.498, 7.634, 9.645, 7.728 |
| dil_obs_0001 | 1e+06 | as_of_global_consulta_meio | 444400 | 0,117 | 0,475 | 3.698, 0.163, 0.475, 0.097, 0.117, 0.092 |
| dil_obs_0001 | 1e+06 | as_of_global_consulta_linha_inteira_meio | 444400 | 0,179 | 0,186 | 0.189, 0.186, 0.174, 0.166, 0.183, 0.179 |
| dil_obs_0001 | 1e+06 | as_of_global_funcao_fim | 909000 | 17,470 | 24,851 | 16.192, 14.346, 24.851, 17.470, 18.254, 14.014 |
| dil_obs_0001 | 1e+06 | as_of_global_consulta_fim | 909000 | 0,179 | 0,186 | 0.454, 0.179, 0.154, 0.142, 0.179, 0.186 |
| dil_obs_0001 | 1e+06 | as_of_global_consulta_linha_inteira_fim | 909000 | 0,316 | 0,436 | 0.330, 0.436, 0.316, 0.268, 0.330, 0.279 |
| dil_obs_0001 | 1e+06 | latest_view | – | 19,004 | 38,820 | 44.835, 17.907, 20.553, 38.820, 19.004, 16.996 |
| longo (snapshot total) | 1e+05 | pg_snapshot | – | 0,071 | – | 0.091, 0.071, 0.056, 0.086, 0.071, 0.069 |
| longo (snapshot total) | 1e+06 | pg_snapshot | – | 0,691 | – | 1.238, 0.904, 0.644, 0.691, 0.722, 0.602 |
| parquet | 1e+05 | duckdb / polars | 44000 | 0,009 / 0,013 | – | duck 0.018, 0.034, 0.009, 0.020, 0.009, 0.009; pl 0.233, 0.013, 0.018, 0.013, 0.024, 0.010 |
| parquet | 1e+06 | duckdb / polars | 444400 | 0,071 / 0,112 | – | duck 0.067, 0.063, 0.090, 0.073, 0.059, 0.071; pl 0.130, 0.083, 0.105, 0.112, 0.170, 0.122 |
| parquet | 1e+07 | duckdb / polars | 4444000 | 0,923 / 1,536 | – | duck 1.118, 0.750, 0.738, 0.923, 1.125, 1.002; pl 1.780, 1.498, 1.475, 2.023, 2.254, 1.536 |

## Payload bruto

| tipo | JSON B/linha | tabela B/linha da API | razão de compressão |
|---|---:|---:|---:|
| campanha_linha_pglz | 448 | 718 | 0,62 |
| campanha_lote_pglz | 448 | 75 | 5,97 |
| campanha_linha_lz4 | 448 | 718 | 0,62 |
| campanha_lote_lz4 | 448 | 75 | 5,97 |
| termo_linha_pglz | 782 | 1.109 | 0,71 |
| termo_lote_pglz | 782 | 172 | 4,56 |
| termo_linha_lz4 | 782 | 1.109 | 0,71 |
| termo_lote_lz4 | 782 | 130 | 6,00 |
