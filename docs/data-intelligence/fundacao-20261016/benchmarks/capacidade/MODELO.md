# Modelo de capacidade — resultado (GERADO)

> Gerado por `experiments/data-intelligence-lab/scripts/fundacao_capacidade_modelo.py` a partir de `pg_medicoes.json` e `horas_campanha_d30.json`. Não editar à mão. Modelo determinístico; bytes medidos em PostgreSQL 16 descartável com DDL de medição (aproximação, ver `04-CADENCIA-E-CAPACIDADE.md`).

- fingerprint `d816c41deca4e811…`, código `c69ccdb098941020…`, resultado `f38e1bbf106d7131…`
- entradas: `horas_campanha_d30.json` `c9f9d1054204…`, `pg_medicoes.json` `26486db6e4dd…`, `pg_medicoes_dil_obs.json` `f1373638e53c…`

## 1. Perfis de bytes (medidos, 1e6 linhas, sem partição)

| perfil | formato | heap B/obs | índices B/obs | payload B/linha em lote (campanha/termo) | payload B/linha individual |
|---|---|---:|---:|---|---|
| v21_replica | largo | 630,4 | 220,3 | 75 / 172 | 718 / 1.109 |
| largo_tipado | largo | 204,9 | 81,5 | 75 / 172 | 718 / 1.109 |
| longo_tipado | longo | 167,3 | 90,3 | 75 / 172 | 718 / 1.109 |
| largo_jsonb | largo | 431,3 | 81,5 | 75 / 172 | 718 / 1.109 |
| dil_obs_real | longo | 630,4 | 453,3 | 75 / 172 | 718 / 1.109 |
| v21_real | largo | 1.140 | 0,0 | 75 / 172 | 718 / 1.109 |

## 2. Jobs na escala atual (agenda documentada)

| job | cron | janela | exec/dia | chamadas/dia | linhas lidas/dia | linhas distintas/dia | redundância | confirmação |
|---|---|---|---:|---:|---:|---:|---:|---|
| gads_campanha_d0 | `7 6-23 * * *` | D-0..D-0 | 18 | 90 | 90 | 22,0 | 75,6% | confirmado no repo (ref+caminho+linha): J:P/collector-invent |
| gads_campanha_d1 | `17 6,14 * * *` | D-1..D-1 | 2 | 10 | 10 | 6,5 | 35,0% | confirmado no repo (ref+caminho+linha): J:P/collector-invent |
| gads_termos | `23 */4 * * *` | D-7..D-1 | 6 | 12 | 13.368 | 383,5 | 97,1% | confirmado no repo (ref+caminho+linha): J:scripts/instalar_c |
| gads_keywords | `23 */4 * * *` | D-7..D-1 | 6 | 6 | 84 | 2,4 | 97,1% | confirmado no repo (ref+caminho+linha): mesmo workflow TFlmT |
| joinads_intraday | `15 6-22/2 * * *` | D-0..D-0 | 9 | 81 | 269 | 147,1 | 45,3% | confirmado no repo (ref+caminho+linha): J:n8n/joinads_v2_int |
| joinads_d1 | `20 6 * * *` | D-7..D-1 | 1 | 64 | 209 | 38,8 | 81,4% | confirmado no repo (ref+caminho+linha): J:n8n/joinads_v2_d1. |
| gads_grupo_d0 | `7 6-23 * * *` | D-0..D-0 | 18 | 18 | 18 | 4,4 | 75,6% | proposta |
| gads_grupo_d1 | `17 6,14 * * *` | D-1..D-1 | 2 | 2 | 2 | 1,3 | 35,0% | proposta |
| gads_anuncio_d1 | `17 6,14 * * *` | D-1..D-1 | 2 | 2 | 4 | 2,6 | 35,0% | proposta |
| gads_campanha_hora_d1 | `37 6 * * *` | D-1..D-1 | 1 | 1 | 21 | 21,0 | 0,0% | proposta (só horas com entrega voltam) |
| gads_campanha_dispositivo_d1 | `37 6 * * *` | D-1..D-1 | 1 | 1 | 3 | 3,0 | 0,0% | proposta |
| gads_campanha_geo_d1 | `37 6 * * *` | D-1..D-1 | 1 | 1 | 10 | 10,0 | 0,0% | proposta; geos por campanha é premissa |

Termos+keywords: a cada 4 h lê 13.452 linhas/dia para 386 distintas; 1×/dia lê 2.242 para 330 (18 → 3 chamadas/dia).

## 3. Cadência × crescimento — jobs `atual`

| cadência intraday | × | ops Google Ads/dia | % Basic (15 mil) | chamadas JoinAds/dia | GB/dia v21 real | GB/dia recomendada | 13 m v21 real | 13 m recomendada | 3 a v21 real | 3 a recomendada |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| atual | 1 | 118 | 0,8% | 145 | 0,02 GB | 0,43 MB | 6,78 GB | 0,17 GB | 18,76 GB | 0,24 GB |
| atual | 10 | 946 | 6,3% | 1.450 | 0,17 GB | 4,29 MB | 67,79 GB | 1,66 GB | 187,63 GB | 2,39 GB |
| atual | 100 | 9.226 | 61,5% | 14.500 | 1,71 GB | 0,04 GB | 677,93 GB | 16,58 GB | 1.876 GB | 23,87 GB |
| atual | 1000 | 92.026 | 613,5% | 145.000 | 17,12 GB | 0,42 GB | 6.779 GB | 165,84 GB | 18.763 GB | 238,66 GB |
| horaria_24h | 1 | 148 | 1,0% | 280 | 0,02 GB | 0,54 MB | 7,01 GB | 0,21 GB | 19,39 GB | 0,28 GB |
| horaria_24h | 10 | 1.192 | 7,9% | 2.800 | 0,18 GB | 5,38 MB | 70,06 GB | 2,08 GB | 193,92 GB | 2,81 GB |
| horaria_24h | 100 | 11.632 | 77,5% | 28.000 | 1,77 GB | 0,05 GB | 700,65 GB | 20,80 GB | 1.939 GB | 28,09 GB |
| horaria_24h | 1000 | 116.032 | 773,5% | 280.000 | 17,69 GB | 0,53 GB | 7.006 GB | 208,02 GB | 19.392 GB | 280,85 GB |
| 15min | 1 | 508 | 3,4% | 928 | 0,02 GB | 0,84 MB | 8,20 GB | 0,33 GB | 22,69 GB | 0,40 GB |
| 15min | 10 | 4.144 | 27,6% | 9.280 | 0,21 GB | 8,40 MB | 81,97 GB | 3,25 GB | 226,88 GB | 3,98 GB |
| 15min | 100 | 40.504 | 270,0% | 92.800 | 2,07 GB | 0,08 GB | 819,74 GB | 32,49 GB | 2.269 GB | 39,77 GB |
| 15min | 1000 | 404.104 | 2.694% | 928.000 | 20,70 GB | 0,82 GB | 8.197 GB | 324,87 GB | 22.688 GB | 397,69 GB |
| 10min | 1 | 748 | 5,0% | 1.360 | 0,02 GB | 0,99 MB | 8,99 GB | 0,38 GB | 24,89 GB | 0,46 GB |
| 10min | 10 | 6.112 | 40,7% | 13.600 | 0,23 GB | 9,87 MB | 89,91 GB | 3,82 GB | 248,85 GB | 4,55 GB |
| 10min | 100 | 59.752 | 398,3% | 136.000 | 2,27 GB | 0,10 GB | 899,14 GB | 38,17 GB | 2.489 GB | 45,46 GB |
| 10min | 1000 | 596.152 | 3.974% | 1.360.000 | 22,71 GB | 0,96 GB | 8.991 GB | 381,74 GB | 24.885 GB | 454,57 GB |

Contas que cabem na quota (operações = a·contas + b; piso sem retries): atual: a=92, b=26 → Basic 162, Explorer 31; horaria_24h: a=116, b=32 → Basic 129, Explorer 24; 15min: a=404, b=104 → Basic 36, Explorer 6; 10min: a=596, b=152 → Basic 24, Explorer 4.

## 3. Cadência × crescimento — jobs `vertical_completa`

| cadência intraday | × | ops Google Ads/dia | % Basic (15 mil) | chamadas JoinAds/dia | GB/dia v21 real | GB/dia recomendada | 13 m v21 real | 13 m recomendada | 3 a v21 real | 3 a recomendada |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| atual | 1 | 143 | 1,0% | 145 | 0,02 GB | 0,46 MB | 6,81 GB | 0,18 GB | 18,84 GB | 0,26 GB |
| atual | 10 | 1.196 | 8,0% | 1.450 | 0,17 GB | 4,62 MB | 68,08 GB | 1,79 GB | 188,41 GB | 2,59 GB |
| atual | 100 | 11.726 | 78,2% | 14.500 | 1,72 GB | 0,05 GB | 680,76 GB | 17,88 GB | 1.884 GB | 25,88 GB |
| atual | 1000 | 117.026 | 780,2% | 145.000 | 17,19 GB | 0,45 GB | 6.808 GB | 178,83 GB | 18.841 GB | 258,74 GB |
| horaria_24h | 1 | 179 | 1,2% | 280 | 0,02 GB | 0,57 MB | 7,04 GB | 0,22 GB | 19,48 GB | 0,30 GB |
| horaria_24h | 10 | 1.502 | 10,0% | 2.800 | 0,18 GB | 5,73 MB | 70,38 GB | 2,22 GB | 194,79 GB | 3,02 GB |
| horaria_24h | 100 | 14.732 | 98,2% | 28.000 | 1,78 GB | 0,06 GB | 703,80 GB | 22,17 GB | 1.948 GB | 30,17 GB |
| horaria_24h | 1000 | 147.032 | 980,2% | 280.000 | 17,77 GB | 0,56 GB | 7.038 GB | 221,74 GB | 19.479 GB | 301,66 GB |
| 15min | 1 | 611 | 4,1% | 928 | 0,02 GB | 0,90 MB | 8,27 GB | 0,35 GB | 22,88 GB | 0,43 GB |
| 15min | 10 | 5.174 | 34,5% | 9.280 | 0,21 GB | 8,98 MB | 82,68 GB | 3,47 GB | 228,83 GB | 4,27 GB |
| 15min | 100 | 50.804 | 338,7% | 92.800 | 2,09 GB | 0,09 GB | 826,78 GB | 34,71 GB | 2.288 GB | 42,70 GB |
| 15min | 1000 | 507.104 | 3.381% | 928.000 | 20,88 GB | 0,88 GB | 8.268 GB | 347,08 GB | 22.883 GB | 427,00 GB |
| 10min | 1 | 899 | 6,0% | 1.360 | 0,02 GB | 1,06 MB | 9,09 GB | 0,41 GB | 25,15 GB | 0,49 GB |
| 10min | 10 | 7.622 | 50,8% | 13.600 | 0,23 GB | 0,01 GB | 90,88 GB | 4,09 GB | 251,52 GB | 4,90 GB |
| 10min | 100 | 74.852 | 499,0% | 136.000 | 2,29 GB | 0,10 GB | 908,77 GB | 40,94 GB | 2.515 GB | 48,94 GB |
| 10min | 1000 | 747.152 | 4.981% | 1.360.000 | 22,95 GB | 1,03 GB | 9.088 GB | 409,42 GB | 25.152 GB | 489,34 GB |

Contas que cabem na quota (operações = a·contas + b; piso sem retries): atual: a=117, b=26 → Basic 127, Explorer 24; horaria_24h: a=147, b=32 → Basic 101, Explorer 19; 15min: a=507, b=104 → Basic 29, Explorer 5; 10min: a=747, b=152 → Basic 19, Explorer 3.

## 4. Políticas de gravação — vertical completa, horária 24 h, ×100

| política | perfil | observações/dia | linhas de payload/dia | GB/dia | 30 d | 13 m | 3 a |
|---|---|---:|---:|---:|---:|---:|---:|
| v21_atual | v21_real | 1.457.157 | 1.457.157 | 1,78 GB | 53,32 GB | 703,80 GB | 1.948 GB |
| v21_atual | v21_replica | 1.457.157 | 1.457.157 | 1,38 GB | 41,54 GB | 548,33 GB | 1.518 GB |
| compacto_sem_dedup | largo_tipado | 1.457.157 | 1.457.157 | 0,62 GB | 18,57 GB | 245,08 GB | 678,31 GB |
| compacto_dedup_lote | largo_tipado | 82.889 | 1.434.137 | 0,25 GB | 7,52 GB | 99,28 GB | 274,77 GB |
| compacto_dedup_linha | largo_tipado | 82.889 | 82.889 | 0,10 GB | 2,99 GB | 39,45 GB | 109,19 GB |
| compacto_dedup_linha_em_lote | largo_tipado | 82.889 | 82.889 | 0,04 GB | 1,31 GB | 17,34 GB | 48,00 GB |
| compacto_dedup_sem_indices | largo_tipado | 82.889 | 82.889 | 0,04 GB | 1,13 GB | 14,85 GB | 41,11 GB |
| recomendada | largo_tipado | 82.889 | 82.889 | 0,06 GB | 1,68 GB | 22,17 GB | 30,17 GB |
| compacto_sem_dedup | longo_tipado | 7.436.543 | 1.457.157 | 2,01 GB | 60,42 GB | 797,59 GB | 2.207 GB |
| compacto_dedup_linha | longo_tipado | 474.213 | 82.889 | 0,19 GB | 5,74 GB | 75,74 GB | 209,63 GB |
| compacto_dedup_linha_em_lote | dil_obs_real | 474.213 | 82.889 | 0,50 GB | 15,01 GB | 198,12 GB | 548,33 GB |
| recomendada | dil_obs_real | 474.213 | 82.889 | 0,53 GB | 15,86 GB | 209,32 GB | 217,31 GB |

## 4b. R1 F13 — redundância real × prevista (termos)

- Real (recibo, 7 dias): 23.891 lidas, 2.525 distintas → razão de distintas **10,6%** (redundância 89,4%), coletor com 13 runs e ~21 h de vida.
- Prevista em regime estacionário (42 leituras por termo-dia): p=0.0: 2,4%, p=0.005: 2,9%, p=0.02: 4,3%, p=0.084: 10,6%.
- Coletor jovem (13 runs, p = 0): 2.546 distintas previstas → 10,7% sobre as lidas reais. A diferença 10,6% × 4,3% é idade do coletor (H5), não erro de premissa; o recibo é compatível com p ≈ 0.

| p de revisão de termos | cenário | observações/dia | GB/dia | 13 m | 3 a |
|---:|---|---:|---:|---:|---:|
| 0.0 | atual atual ×1 | 535 | 0,40 MB | 0,15 GB | 0,23 GB |
| 0.0 | vertical_completa horaria_24h ×100 | 76.323 | 0,05 GB | 20,91 GB | 28,90 GB |
| 0.005 | atual atual ×1 | 600 | 0,43 MB | 0,17 GB | 0,24 GB |
| 0.005 | vertical_completa horaria_24h ×100 | 82.889 | 0,06 GB | 22,17 GB | 30,17 GB |
| 0.02 | atual atual ×1 | 797 | 0,53 MB | 0,20 GB | 0,28 GB |
| 0.02 | vertical_completa horaria_24h ×100 | 102.586 | 0,07 GB | 25,98 GB | 33,97 GB |
| 0.084 | atual atual ×1 | 1.638 | 0,95 MB | 0,37 GB | 0,44 GB |
| 0.084 | vertical_completa horaria_24h ×100 | 186.629 | 0,11 GB | 42,20 GB | 50,20 GB |

## 5. Sensibilidade (vertical completa, horária 24 h, ×100, recomendada)

| × p de revisão | × λ | observações/dia | GB/dia | 3 a |
|---:|---:|---:|---:|---:|
| 0.25 | 0.25 | 60.613 | 0,05 GB | 26,48 GB |
| 0.25 | 1.0 | 77.112 | 0,05 GB | 29,08 GB |
| 0.25 | 4.0 | 81.809 | 0,06 GB | 29,82 GB |
| 1.0 | 0.25 | 66.389 | 0,05 GB | 27,57 GB |
| 1.0 | 1.0 | 82.889 | 0,06 GB | 30,17 GB |
| 1.0 | 4.0 | 87.586 | 0,06 GB | 30,91 GB |
| 3.0 | 0.25 | 81.792 | 0,06 GB | 30,46 GB |
| 3.0 | 1.0 | 98.292 | 0,06 GB | 33,06 GB |
| 3.0 | 4.0 | 102.989 | 0,07 GB | 33,80 GB |

## 6. GTM (orientado a evento; lote 10 s ou 20 eventos)

| cenário | eventos/dia | requisições/dia | eventos/requisição | GB/dia | 3 a |
|---|---:|---:|---:|---:|---:|
| medido_raw_events | 4 | 4 | 1,0 | 0,00 MB | 2,64 MB |
| trafego_pago_x1 | 218 | 218 | 1,0 | 0,14 MB | 0,15 GB |
| trafego_pago_x10 | 2.184 | 2.184 | 1,0 | 1,37 MB | 1,47 GB |
| trafego_pago_x100 | 21.840 | 21.840 | 1,0 | 0,01 GB | 14,71 GB |
| trafego_pago_x1000 | 218.400 | 218.400 | 1,0 | 0,13 GB | 147,13 GB |

## 7. Premissas (não medidas)

- `lambda_campanha_ativa_h`: {'valor': 17.32, 'origem': 'calibrado: impressões D30/720 h'}
- `fracao_mutavel_gads`: {'valor': 0.2, 'origem': '1 de 5 campanhas com entrega (account-snapshot/D0 canário)'}
- `p_revisao_d1`: {'valor': 0.3, 'origem': 'PREMISSA: atraso de conversão não medido (J:P/reconciliation.json:1013)'}
- `p_revisao_termos`: {'valor': 0.005, 'origem': 'limite superior compatível com o recibo (2.525 distintas ≈ 2.546 termo-dias); era 0,02'}
- `p_revisao_joinads_d1`: {'valor': 0.05, 'origem': 'PREMISSA'}
- `joinads_lambda_h`: {'valor': 2.0, 'origem': 'PREMISSA'}
- `joinads_consultas_intraday`: {'valor': 9, 'origem': 'PREMISSA: 64 lotes / 7 dias do D1'}
- `geos_por_campanha_dia`: {'valor': 10, 'origem': 'PREMISSA'}
- `crescimento`: mais contas com a mesma estrutura por conta (portfólio de sites)
