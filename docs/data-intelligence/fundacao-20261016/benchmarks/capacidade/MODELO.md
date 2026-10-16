# Modelo de capacidade — resultado (GERADO)

> Gerado por `experiments/data-intelligence-lab/scripts/fundacao_capacidade_modelo.py` a partir de `pg_medicoes.json` e `horas_campanha_d30.json`. Não editar à mão. Modelo determinístico; bytes medidos em PostgreSQL 16 descartável com DDL de medição (aproximação, ver `04-CADENCIA-E-CAPACIDADE.md`).

- fingerprint `12b983e5dff86298…`, código `1e63632cad6f48e4…`, resultado `b07b4cd99b2bd447…`
- entradas: `horas_campanha_d30.json` `a4e224116048…`, `pg_medicoes.json` `8e82eb11ab9c…`

## 1. Perfis de bytes (medidos, 1e6 linhas, sem partição)

| perfil | formato | heap B/obs | índices B/obs | payload B/linha em lote (campanha/termo) | payload B/linha individual |
|---|---|---:|---:|---|---|
| v21_replica | largo | 630,4 | 220,3 | 75 / 172 | 718 / 1.109 |
| largo_tipado | largo | 204,9 | 81,5 | 75 / 172 | 718 / 1.109 |
| longo_tipado | longo | 167,3 | 90,3 | 75 / 172 | 718 / 1.109 |
| largo_jsonb | largo | 431,3 | 81,5 | 75 / 172 | 718 / 1.109 |

## 2. Jobs na escala atual (agenda documentada)

| job | cron | janela | exec/dia | chamadas/dia | linhas lidas/dia | linhas distintas/dia | redundância | confirmação |
|---|---|---|---:|---:|---:|---:|---:|---|
| gads_campanha_d0 | `7 6-23 * * *` | D-0..D-0 | 18 | 18 | 90 | 22,0 | 75,6% | confirmado no repo (ref+caminho+linha): J:P/collector-invent |
| gads_campanha_d1 | `17 6,14 * * *` | D-1..D-1 | 2 | 2 | 10 | 6,5 | 35,0% | confirmado no repo (ref+caminho+linha): J:P/collector-invent |
| gads_termos | `23 */4 * * *` | D-7..D-1 | 6 | 6 | 13.368 | 579,3 | 95,7% | confirmado no repo (ref+caminho+linha): J:scripts/instalar_c |
| gads_keywords | `23 */4 * * *` | D-7..D-1 | 6 | 6 | 84 | 3,6 | 95,7% | confirmado no repo (ref+caminho+linha): mesmo workflow TFlmT |
| joinads_intraday | `15 6-22/2 * * *` | D-0..D-0 | 9 | 81 | 269 | 147,1 | 45,3% | confirmado no repo (ref+caminho+linha): J:n8n/joinads_v2_int |
| joinads_d1 | `20 6 * * *` | D-7..D-1 | 1 | 64 | 209 | 38,8 | 81,4% | confirmado no repo (ref+caminho+linha): J:n8n/joinads_v2_d1. |
| gads_grupo_d0 | `7 6-23 * * *` | D-0..D-0 | 18 | 18 | 18 | 4,4 | 75,6% | proposta |
| gads_grupo_d1 | `17 6,14 * * *` | D-1..D-1 | 2 | 2 | 2 | 1,3 | 35,0% | proposta |
| gads_anuncio_d1 | `17 6,14 * * *` | D-1..D-1 | 2 | 2 | 4 | 2,6 | 35,0% | proposta |
| gads_campanha_hora_d1 | `37 6 * * *` | D-1..D-1 | 1 | 1 | 21 | 21,0 | 0,0% | proposta (só horas com entrega voltam) |
| gads_campanha_dispositivo_d1 | `37 6 * * *` | D-1..D-1 | 1 | 1 | 3 | 3,0 | 0,0% | proposta |
| gads_campanha_geo_d1 | `37 6 * * *` | D-1..D-1 | 1 | 1 | 10 | 10,0 | 0,0% | proposta; geos por campanha é premissa |

Termos+keywords: a cada 4 h lê 13.452 linhas/dia para 583 distintas; 1×/dia lê 2.242 para 359 (12 → 2 chamadas/dia).

## 3. Cadência × crescimento — jobs `atual`

| cadência intraday | × | ops Google Ads/dia | % Basic (15 mil) | chamadas JoinAds/dia | GB/dia v21 | GB/dia recomendada | 13 m v21 | 13 m recomendada | 3 a v21 | 3 a recomendada |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| atual | 1 | 32 | 0,2% | 145 | 0,01 GB | 0,52 MB | 5,28 GB | 0,50 GB | 14,62 GB | 1,05 GB |
| atual | 10 | 320 | 2,1% | 1.450 | 0,13 GB | 5,20 MB | 52,82 GB | 2,30 GB | 146,20 GB | 3,52 GB |
| atual | 100 | 3.200 | 21,3% | 14.500 | 1,33 GB | 0,05 GB | 528,25 GB | 20,39 GB | 1.462 GB | 28,15 GB |
| atual | 1000 | 32.000 | 213,3% | 145.000 | 13,34 GB | 0,51 GB | 5.282 GB | 201,20 GB | 14.620 GB | 274,51 GB |
| horaria_24h | 1 | 38 | 0,3% | 280 | 0,01 GB | 0,63 MB | 5,46 GB | 0,54 GB | 15,11 GB | 1,10 GB |
| horaria_24h | 10 | 380 | 2,5% | 2.800 | 0,14 GB | 6,27 MB | 54,59 GB | 2,72 GB | 151,08 GB | 3,93 GB |
| horaria_24h | 100 | 3.800 | 25,3% | 28.000 | 1,38 GB | 0,06 GB | 545,86 GB | 24,54 GB | 1.511 GB | 32,30 GB |
| horaria_24h | 1000 | 38.000 | 253,3% | 280.000 | 13,78 GB | 0,61 GB | 5.459 GB | 242,70 GB | 15.108 GB | 316,00 GB |
| 15min | 1 | 110 | 0,7% | 928 | 0,02 GB | 0,93 MB | 6,38 GB | 0,65 GB | 17,66 GB | 1,21 GB |
| 15min | 10 | 1.100 | 7,3% | 9.280 | 0,16 GB | 9,26 MB | 63,82 GB | 3,88 GB | 176,63 GB | 5,09 GB |
| 15min | 100 | 11.000 | 73,3% | 92.800 | 1,61 GB | 0,09 GB | 638,18 GB | 36,10 GB | 1.766 GB | 43,87 GB |
| 15min | 1000 | 110.000 | 733,3% | 928.000 | 16,12 GB | 0,90 GB | 6.382 GB | 358,35 GB | 17.663 GB | 431,66 GB |
| 10min | 1 | 158 | 1,1% | 1.360 | 0,02 GB | 1,07 MB | 7,00 GB | 0,71 GB | 19,37 GB | 1,27 GB |
| 10min | 10 | 1.580 | 10,5% | 13.600 | 0,18 GB | 0,01 GB | 69,97 GB | 4,44 GB | 193,66 GB | 5,66 GB |
| 10min | 100 | 15.800 | 105,3% | 136.000 | 1,77 GB | 0,10 GB | 699,72 GB | 41,76 GB | 1.937 GB | 49,53 GB |
| 10min | 1000 | 158.000 | 1.053% | 1.360.000 | 17,67 GB | 1,05 GB | 6.997 GB | 414,92 GB | 19.366 GB | 488,23 GB |

## 3. Cadência × crescimento — jobs `vertical_completa`

| cadência intraday | × | ops Google Ads/dia | % Basic (15 mil) | chamadas JoinAds/dia | GB/dia v21 | GB/dia recomendada | 13 m v21 | 13 m recomendada | 3 a v21 | 3 a recomendada |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| atual | 1 | 57 | 0,4% | 145 | 0,01 GB | 0,55 MB | 5,30 GB | 0,51 GB | 14,68 GB | 1,07 GB |
| atual | 10 | 570 | 3,8% | 1.450 | 0,13 GB | 5,53 MB | 53,05 GB | 2,43 GB | 146,81 GB | 3,72 GB |
| atual | 100 | 5.700 | 38,0% | 14.500 | 1,34 GB | 0,05 GB | 530,46 GB | 21,67 GB | 1.468 GB | 30,15 GB |
| atual | 1000 | 57.000 | 380,0% | 145.000 | 13,40 GB | 0,54 GB | 5.305 GB | 214,03 GB | 14.681 GB | 294,43 GB |
| horaria_24h | 1 | 69 | 0,5% | 280 | 0,01 GB | 0,66 MB | 5,48 GB | 0,55 GB | 15,18 GB | 1,12 GB |
| horaria_24h | 10 | 690 | 4,6% | 2.800 | 0,14 GB | 6,62 MB | 54,83 GB | 2,86 GB | 151,76 GB | 4,14 GB |
| horaria_24h | 100 | 6.900 | 46,0% | 28.000 | 1,38 GB | 0,06 GB | 548,33 GB | 25,89 GB | 1.518 GB | 34,37 GB |
| horaria_24h | 1000 | 69.000 | 460,0% | 280.000 | 13,85 GB | 0,65 GB | 5.483 GB | 256,25 GB | 15.176 GB | 336,65 GB |
| 15min | 1 | 213 | 1,4% | 928 | 0,02 GB | 0,98 MB | 6,44 GB | 0,68 GB | 17,82 GB | 1,24 GB |
| 15min | 10 | 2.130 | 14,2% | 9.280 | 0,16 GB | 9,83 MB | 64,38 GB | 4,10 GB | 178,18 GB | 5,38 GB |
| 15min | 100 | 21.300 | 142,0% | 92.800 | 1,63 GB | 0,10 GB | 643,77 GB | 38,30 GB | 1.782 GB | 46,78 GB |
| 15min | 1000 | 213.000 | 1.420% | 928.000 | 16,26 GB | 0,96 GB | 6.438 GB | 380,36 GB | 17.818 GB | 460,76 GB |
| 10min | 1 | 309 | 2,1% | 1.360 | 0,02 GB | 1,14 MB | 7,07 GB | 0,74 GB | 19,58 GB | 1,30 GB |
| 10min | 10 | 3.090 | 20,6% | 13.600 | 0,18 GB | 0,01 GB | 70,74 GB | 4,72 GB | 195,79 GB | 6,00 GB |
| 10min | 100 | 30.900 | 206,0% | 136.000 | 1,79 GB | 0,11 GB | 707,40 GB | 44,50 GB | 1.958 GB | 52,98 GB |
| 10min | 1000 | 309.000 | 2.060% | 1.360.000 | 17,86 GB | 1,12 GB | 7.074 GB | 442,37 GB | 19.579 GB | 522,77 GB |

## 4. Políticas de gravação — vertical completa, horária 24 h, ×100

| política | perfil | observações/dia | linhas de payload/dia | GB/dia | 30 d | 13 m | 3 a |
|---|---|---:|---:|---:|---:|---:|---:|
| v21_atual | v21_replica | 1.457.157 | 1.457.157 | 1,38 GB | 41,54 GB | 548,33 GB | 1.518 GB |
| compacto_sem_dedup | largo_tipado | 1.457.157 | 1.457.157 | 0,62 GB | 18,57 GB | 245,08 GB | 678,31 GB |
| compacto_dedup_lote | largo_tipado | 102.586 | 1.435.403 | 0,26 GB | 7,68 GB | 101,39 GB | 280,62 GB |
| compacto_dedup_linha | largo_tipado | 102.586 | 102.586 | 0,13 GB | 3,76 GB | 49,57 GB | 137,19 GB |
| compacto_dedup_linha_em_lote | largo_tipado | 102.586 | 102.586 | 0,05 GB | 1,60 GB | 21,07 GB | 58,33 GB |
| compacto_dedup_sem_indices | largo_tipado | 102.586 | 102.586 | 0,05 GB | 1,36 GB | 17,99 GB | 49,79 GB |
| recomendada | largo_tipado | 102.586 | 102.586 | 0,06 GB | 1,96 GB | 25,89 GB | 34,37 GB |
| compacto_sem_dedup | longo_tipado | 7.436.543 | 1.457.157 | 2,01 GB | 60,42 GB | 797,59 GB | 2.207 GB |
| compacto_dedup_linha | longo_tipado | 572.701 | 102.586 | 0,24 GB | 7,06 GB | 93,14 GB | 257,77 GB |

## 5. Sensibilidade (vertical completa, horária 24 h, ×100, recomendada)

| × p de revisão | × λ | observações/dia | GB/dia | 3 a |
|---:|---:|---:|---:|---:|
| 0.25 | 0.25 | 65.537 | 0,05 GB | 27,97 GB |
| 0.25 | 1.0 | 82.037 | 0,05 GB | 30,51 GB |
| 0.25 | 4.0 | 86.734 | 0,06 GB | 31,23 GB |
| 1.0 | 0.25 | 86.086 | 0,06 GB | 31,83 GB |
| 1.0 | 1.0 | 102.586 | 0,06 GB | 34,37 GB |
| 1.0 | 4.0 | 107.283 | 0,07 GB | 35,09 GB |
| 3.0 | 0.25 | 140.885 | 0,08 GB | 42,12 GB |
| 3.0 | 1.0 | 157.384 | 0,09 GB | 44,66 GB |
| 3.0 | 4.0 | 162.081 | 0,09 GB | 45,39 GB |

## 6. GTM (orientado a evento; lote 10 s ou 20 eventos)

| cenário | eventos/dia | requisições/dia | eventos/requisição | GB/dia | 3 a |
|---|---:|---:|---:|---:|---:|
| medido_raw_events | 4 | 4 | 1,0 | 0,00 MB | 2,64 MB |
| trafego_pago_x1 | 218 | 218 | 1,0 | 0,14 MB | 0,15 GB |
| trafego_pago_x10 | 2.184 | 2.184 | 1,0 | 1,37 MB | 1,47 GB |
| trafego_pago_x100 | 21.840 | 21.840 | 1,0 | 0,01 GB | 14,71 GB |
| trafego_pago_x1000 | 218.400 | 218.400 | 1,0 | 0,13 GB | 147,13 GB |

## 7. Premissas (não medidas)

- `lambda_campanha_ativa_h`: {'valor': 17.319444444444443, 'origem': 'calibrado: impressões D30/720 h'}
- `fracao_mutavel_gads`: {'valor': 0.2, 'origem': '1 de 5 campanhas com entrega (account-snapshot/D0 canário)'}
- `p_revisao_d1`: {'valor': 0.3, 'origem': 'PREMISSA: atraso de conversão não medido (J:P/reconciliation.json:1013)'}
- `p_revisao_termos`: {'valor': 0.02, 'origem': 'PREMISSA'}
- `p_revisao_joinads_d1`: {'valor': 0.05, 'origem': 'PREMISSA'}
- `joinads_lambda_h`: {'valor': 2.0, 'origem': 'PREMISSA'}
- `joinads_consultas_intraday`: {'valor': 9, 'origem': 'PREMISSA: 64 lotes / 7 dias do D1'}
- `geos_por_campanha_dia`: {'valor': 10, 'origem': 'PREMISSA'}
- `crescimento`: mais contas com a mesma estrutura por conta (portfólio de sites)
