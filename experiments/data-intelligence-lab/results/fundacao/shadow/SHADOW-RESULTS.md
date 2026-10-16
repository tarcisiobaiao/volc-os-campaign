# Shadow engine — resultados (TESTADO COM SINTÉTICO)

> **Gerado** por `scripts/fundacao_shadow.py` a partir de `shadow_resultados.json`; não editar à mão.
> **Natureza:** gerador provisório e/ou Simulator Lab (thread E). Lucro contrafactual vem da VERDADE do
> gerador. Nada aqui é eficácia, calibração ou validação com dado real.

- versão do código (provisório): `91fc5f5c7a3c89ed…`; (simulador): `a1efaf08d3afa7e1…`; sha determinístico: `6928cdd3ad14804b…`
- decisão diária às 7h (America/Sao_Paulo), aplicada ao dia seguinte; menu do oráculo: manter, reduzir 30%, pausar
- valores em BRL (micros ÷ 10⁶), arredondados; `vs manter` positivo = ganharia contra não fazer nada

## Fonte: provisorio

### base

2567 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`16cfdc5ca750…`); 27.42 ms/corte (8 políticas). Lucro de `manter`: 128.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal | -728 | 0 | 2.774 | 728 | 26 | 12 | 0 | 0 | 120/1440 |
| greedy_conservador | 236 | 965 | 1.837 | 0 | 15 | 0 | 0 | 0 | 120/1440 |
| guardiao_72h[regra_margem] | 1.670 | 2.399 | 374 | 0 | 27 | 0 | 0 | 0 | 6/1440 |
| guardiao_72h[regra_margem_imatura] | 1.678 | 2.406 | 367 | 0 | 31 | 2 | 2 | 0 | 8/1440 |
| manter | 0 | 728 | 2.045 | 0 | 0 | 0 | 0 | 0 | 0/1440 |
| regra_margem | 1.670 | 2.399 | 374 | 0 | 27 | 0 | 0 | 0 | 6/1440 |
| regra_margem_imatura | 1.862 | 2.591 | 182 | 0 | 35 | 2 | 2 | 0 | 4/1440 |
| regra_margem_null_zero | 1.881 | 2.609 | 164 | 0 | 49 | 7 | 7 | 0 | 40/1440 |

### campanha_nova

2378 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`5cad86ede533…`); 26.14 ms/corte (8 políticas). Lucro de `manter`: 232.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal | -791 | 0 | 2.756 | 791 | 22 | 12 | 0 | 0 | 114/1383 |
| greedy_conservador | 181 | 972 | 1.806 | 0 | 10 | 0 | 0 | 0 | 114/1383 |
| guardiao_72h[regra_margem] | 1.637 | 2.428 | 328 | 0 | 27 | 0 | 0 | 0 | 6/1383 |
| guardiao_72h[regra_margem_imatura] | 1.637 | 2.428 | 328 | 0 | 27 | 0 | 0 | 0 | 8/1383 |
| manter | 0 | 791 | 1.965 | 0 | 0 | 0 | 0 | 0 | 0/1383 |
| regra_margem | 1.637 | 2.428 | 328 | 0 | 27 | 0 | 0 | 0 | 6/1383 |
| regra_margem_imatura | 1.815 | 2.606 | 150 | 0 | 33 | 1 | 1 | 0 | 5/1383 |
| regra_margem_null_zero | 1.628 | 2.419 | 337 | 0 | 46 | 6 | 6 | 0 | 25/1383 |

### identidade_trocada

2559 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`8a40f21e0c81…`); 33.54 ms/corte (8 políticas). Lucro de `manter`: 128.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal | -422 | 0 | 2.466 | 422 | 17 | 8 | 0 | 24 | 126/1440 |
| greedy_conservador | 47 | 468 | 2.001 | 0 | 3 | 0 | 0 | 20 | 126/1440 |
| guardiao_72h[regra_margem] | 1.120 | 1.541 | 925 | 0 | 19 | 0 | 0 | 8 | 9/1440 |
| guardiao_72h[regra_margem_imatura] | 931 | 1.353 | 1.114 | 0 | 17 | 0 | 0 | 14 | 11/1440 |
| manter | 0 | 422 | 2.045 | 0 | 0 | 0 | 0 | 0 | 0/1440 |
| regra_margem | 1.120 | 1.541 | 925 | 0 | 19 | 0 | 0 | 8 | 9/1440 |
| regra_margem_imatura | 1.115 | 1.537 | 929 | 0 | 21 | 0 | 0 | 14 | 7/1440 |
| regra_margem_null_zero | 1.140 | 1.562 | 905 | 0 | 29 | 2 | 2 | 20 | 44/1440 |

### moeda_misturada

2567 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`9be67eb5db6f…`); 26.92 ms/corte (8 políticas). Lucro de `manter`: 128.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal | -728 | 0 | 2.774 | 728 | 26 | 12 | 0 | 0 | 120/1440 |
| greedy_conservador | 236 | 965 | 1.837 | 0 | 15 | 0 | 0 | 0 | 120/1440 |
| guardiao_72h[regra_margem] | 1.670 | 2.399 | 374 | 0 | 27 | 0 | 0 | 0 | 6/1440 |
| guardiao_72h[regra_margem_imatura] | 1.678 | 2.406 | 367 | 0 | 31 | 2 | 2 | 0 | 8/1440 |
| manter | 0 | 728 | 2.045 | 0 | 0 | 0 | 0 | 0 | 0/1440 |
| regra_margem | 1.670 | 2.399 | 374 | 0 | 27 | 0 | 0 | 0 | 6/1440 |
| regra_margem_imatura | 1.862 | 2.591 | 182 | 0 | 35 | 2 | 2 | 0 | 4/1440 |
| regra_margem_null_zero | 1.881 | 2.609 | 164 | 0 | 49 | 7 | 7 | 0 | 40/1440 |

### restatement_tardio

2571 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`d21c8c0e3bfc…`); 26.73 ms/corte (8 políticas). Lucro de `manter`: 128.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal | -728 | 0 | 2.774 | 728 | 26 | 12 | 0 | 0 | 120/1440 |
| greedy_conservador | 236 | 965 | 1.837 | 0 | 15 | 0 | 0 | 0 | 120/1440 |
| guardiao_72h[regra_margem] | 1.670 | 2.399 | 374 | 0 | 27 | 0 | 0 | 0 | 7/1440 |
| guardiao_72h[regra_margem_imatura] | 1.678 | 2.406 | 367 | 0 | 31 | 2 | 2 | 0 | 8/1440 |
| manter | 0 | 728 | 2.045 | 0 | 0 | 0 | 0 | 0 | 0/1440 |
| regra_margem | 1.670 | 2.399 | 374 | 0 | 27 | 0 | 0 | 0 | 7/1440 |
| regra_margem_imatura | 1.862 | 2.591 | 182 | 0 | 35 | 2 | 2 | 0 | 4/1440 |
| regra_margem_null_zero | 1.881 | 2.609 | 164 | 0 | 49 | 7 | 7 | 0 | 40/1440 |

### zero_sintetizado

2458 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`2d2f5fd5e0e4…`); 33.18 ms/corte (8 políticas). Lucro de `manter`: 128.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal | -277 | 0 | 2.322 | 277 | 25 | 4 | 0 | 0 | 102/1440 |
| greedy_conservador | 161 | 438 | 1.887 | 0 | 10 | 0 | 0 | 0 | 102/1440 |
| guardiao_72h[regra_margem] | 1.670 | 1.948 | 374 | 0 | 27 | 0 | 0 | 0 | 7/1440 |
| guardiao_72h[regra_margem_imatura] | 1.678 | 1.955 | 367 | 0 | 31 | 2 | 2 | 0 | 9/1440 |
| manter | 0 | 277 | 2.045 | 0 | 0 | 0 | 0 | 0 | 0/1440 |
| regra_margem | 1.670 | 1.948 | 374 | 0 | 27 | 0 | 0 | 0 | 7/1440 |
| regra_margem_imatura | 1.862 | 2.140 | 182 | 0 | 35 | 2 | 2 | 0 | 5/1440 |
| regra_margem_null_zero | 1.410 | 1.687 | 635 | 9 | 52 | 10 | 10 | 0 | 43/1440 |

## Fonte: simulador

### estavel

3538 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`df83d88f090f…`); 38.17 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -217 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 217 | 0 | 72 | 0 | 20 | 0 | 0 | 2 | 156/1920 |
| greedy_conservador | -2 | -218 | 258 | 2 | 17 | 0 | 0 | 2 | 156/1920 |
| regra_margem | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 37 | -179 | 219 | 0 | 27 | 2 | 2 | 0 | 12/1920 |
| guardiao_72h[regra_margem_imatura] | 37 | -179 | 219 | 0 | 24 | 2 | 2 | 0 | 14/1920 |
| regra_margem_null_zero | 47 | -170 | 209 | 1 | 36 | 4 | 4 | 0 | 27/1920 |

### campanha_nova_aprendendo

3177 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`4840924883e0…`); 35.87 ms/corte (8 políticas). Lucro de `manter`: -190.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -220 | 277 | 0 | 0 | 0 | 0 | 0 | 0/1913 |
| equal | 220 | 0 | 92 | 0 | 19 | 0 | 0 | 2 | 154/1913 |
| greedy_conservador | -1 | -221 | 278 | 1 | 12 | 0 | 0 | 2 | 154/1913 |
| regra_margem | 50 | -169 | 226 | 0 | 35 | 2 | 0 | 0 | 11/1913 |
| guardiao_72h[regra_margem] | 50 | -169 | 226 | 0 | 35 | 2 | 0 | 0 | 11/1913 |
| regra_margem_imatura | 55 | -165 | 222 | 0 | 41 | 3 | 3 | 0 | 6/1913 |
| guardiao_72h[regra_margem_imatura] | 50 | -169 | 227 | 0 | 34 | 2 | 2 | 0 | 11/1913 |
| regra_margem_null_zero | 82 | -137 | 194 | 0 | 52 | 3 | 3 | 0 | 22/1913 |

### atraso_receita_longo

3409 observações, 241 cortes horários, 1928 decisões, 80 resultados maduros no ledger (`c0e3c411e098…`); 35.15 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -151 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 151 | 0 | 135 | 1 | 20 | 3 | 0 | 3 | 156/1920 |
| greedy_conservador | -1 | -152 | 257 | 1 | 14 | 1 | 0 | 3 | 157/1920 |
| regra_margem | 64 | -87 | 192 | 0 | 35 | 4 | 0 | 0 | 24/1920 |
| guardiao_72h[regra_margem] | 64 | -87 | 192 | 0 | 35 | 4 | 0 | 0 | 24/1920 |
| regra_margem_imatura | 162 | 11 | 94 | 0 | 56 | 10 | 10 | 0 | 32/1920 |
| guardiao_72h[regra_margem_imatura] | 148 | -4 | 108 | 0 | 49 | 8 | 8 | 0 | 40/1920 |
| regra_margem_null_zero | 228 | 77 | 28 | 0 | 68 | 18 | 18 | 1 | 60/1920 |

### restatement_custo

3538 observações, 241 cortes horários, 1928 decisões, 80 resultados maduros no ledger (`52c593c9a299…`); 47.87 ms/corte (8 políticas). Lucro de `manter`: 94.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -124 | 96 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 124 | 0 | 36 | 0 | 19 | 1 | 0 | 2 | 156/1920 |
| greedy_conservador | 0 | -124 | 96 | 0 | 15 | 0 | 0 | 2 | 163/1920 |
| regra_margem | 14 | -111 | 82 | 1 | 25 | 5 | 0 | 0 | 21/1920 |
| guardiao_72h[regra_margem] | 14 | -111 | 82 | 1 | 25 | 5 | 0 | 0 | 21/1920 |
| regra_margem_imatura | 14 | -110 | 82 | 2 | 34 | 6 | 6 | 0 | 23/1920 |
| guardiao_72h[regra_margem_imatura] | 16 | -108 | 80 | 1 | 31 | 5 | 5 | 0 | 26/1920 |
| regra_margem_null_zero | 19 | -105 | 77 | 2 | 41 | 7 | 7 | 0 | 44/1920 |

### fonte_fora_do_ar

3562 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`4315851c8494…`); 66.73 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -202 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 202 | 0 | 85 | 0 | 19 | 0 | 0 | 2 | 140/1920 |
| greedy_conservador | -2 | -204 | 258 | 2 | 17 | 0 | 0 | 2 | 140/1920 |
| regra_margem | 29 | -173 | 227 | 0 | 19 | 1 | 0 | 0 | 28/1920 |
| guardiao_72h[regra_margem] | 29 | -173 | 227 | 0 | 19 | 1 | 0 | 0 | 28/1920 |
| regra_margem_imatura | 29 | -173 | 227 | 0 | 23 | 1 | 1 | 0 | 25/1920 |
| guardiao_72h[regra_margem_imatura] | 29 | -173 | 227 | 0 | 20 | 1 | 1 | 0 | 27/1920 |
| regra_margem_null_zero | 41 | -161 | 215 | 6 | 52 | 19 | 19 | 0 | 42/1920 |

### zero_falso

3538 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`434eff4a644b…`); 80.15 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -202 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 202 | 0 | 85 | 0 | 19 | 0 | 0 | 2 | 138/1920 |
| greedy_conservador | -1 | -203 | 257 | 2 | 14 | 1 | 0 | 2 | 138/1920 |
| regra_margem | 31 | -171 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -171 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 35 | -167 | 221 | 0 | 27 | 2 | 2 | 0 | 12/1920 |
| guardiao_72h[regra_margem_imatura] | 35 | -167 | 221 | 0 | 24 | 2 | 2 | 0 | 14/1920 |
| regra_margem_null_zero | 72 | -130 | 184 | 1 | 35 | 6 | 6 | 0 | 43/1920 |

### zero_sintetizado_coletor

12760 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`f01e6ec93540…`); 195.22 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -217 | 256 | 0 | 0 | 0 | 0 | 0 | 0/9600 |
| equal | 217 | 0 | 72 | 0 | 19 | 0 | 0 | 2 | 154/9600 |
| greedy_conservador | -1 | -218 | 257 | 2 | 14 | 1 | 0 | 2 | 154/9600 |
| regra_margem | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/9600 |
| guardiao_72h[regra_margem] | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/9600 |
| regra_margem_imatura | 37 | -180 | 219 | 0 | 27 | 2 | 2 | 0 | 12/9600 |
| guardiao_72h[regra_margem_imatura] | 37 | -180 | 219 | 0 | 24 | 2 | 2 | 0 | 14/9600 |
| regra_margem_null_zero | 52 | -165 | 204 | 1 | 37 | 5 | 5 | 0 | 65/9600 |

### identidade_trocada

3538 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`13aa4a13732a…`); 53.87 ms/corte (8 políticas). Lucro de `manter`: -89.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -138 | 230 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 138 | 0 | 115 | 0 | 17 | 0 | 0 | 22 | 153/1920 |
| greedy_conservador | -1 | -139 | 231 | 1 | 8 | 0 | 0 | 5 | 150/1920 |
| regra_margem | 3 | -135 | 227 | 0 | 15 | 1 | 0 | 6 | 13/1920 |
| guardiao_72h[regra_margem] | 3 | -135 | 227 | 0 | 15 | 1 | 0 | 6 | 13/1920 |
| regra_margem_imatura | 7 | -130 | 223 | 0 | 19 | 1 | 1 | 8 | 13/1920 |
| guardiao_72h[regra_margem_imatura] | 7 | -130 | 223 | 0 | 16 | 1 | 1 | 8 | 15/1920 |
| regra_margem_null_zero | 11 | -126 | 219 | 1 | 22 | 3 | 3 | 11 | 24/1920 |

### moeda_misturada

3538 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`1db51ad09fe8…`); 40.66 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -217 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 217 | 0 | 72 | 0 | 20 | 0 | 0 | 2 | 156/1920 |
| greedy_conservador | -2 | -218 | 258 | 2 | 17 | 0 | 0 | 2 | 156/1920 |
| regra_margem | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 37 | -179 | 219 | 0 | 27 | 2 | 2 | 0 | 12/1920 |
| guardiao_72h[regra_margem_imatura] | 37 | -179 | 219 | 0 | 24 | 2 | 2 | 0 | 14/1920 |
| regra_margem_null_zero | 47 | -170 | 209 | 1 | 36 | 4 | 4 | 0 | 27/1920 |

### vazamento_tentado

3673 observações, 241 cortes horários, 1928 decisões, 80 resultados maduros no ledger (`d1e11969b67b…`); 38.15 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -217 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 217 | 0 | 72 | 0 | 20 | 0 | 0 | 2 | 156/1920 |
| greedy_conservador | -2 | -218 | 258 | 2 | 17 | 0 | 0 | 2 | 159/1920 |
| regra_margem | 31 | -186 | 225 | 0 | 23 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -186 | 225 | 0 | 23 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 40 | -177 | 216 | 0 | 26 | 2 | 2 | 0 | 9/1920 |
| guardiao_72h[regra_margem_imatura] | 40 | -177 | 216 | 0 | 23 | 2 | 2 | 0 | 11/1920 |
| regra_margem_null_zero | 47 | -170 | 209 | 1 | 32 | 4 | 4 | 0 | 26/1920 |

### custo_d0_multiversao

8212 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`55da7029fc76…`); 37.01 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -218 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 218 | 0 | 72 | 0 | 20 | 0 | 0 | 2 | 158/1920 |
| greedy_conservador | -2 | -220 | 258 | 2 | 17 | 0 | 0 | 2 | 158/1920 |
| regra_margem | 31 | -188 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -188 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 37 | -181 | 219 | 0 | 27 | 2 | 2 | 0 | 12/1920 |
| guardiao_72h[regra_margem_imatura] | 37 | -181 | 219 | 0 | 24 | 2 | 2 | 0 | 14/1920 |
| regra_margem_null_zero | 47 | -171 | 209 | 1 | 36 | 4 | 4 | 0 | 27/1920 |

### execucao_presa

3389 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`ff249293832a…`); 37.43 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -211 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 211 | 0 | 72 | 0 | 20 | 0 | 0 | 2 | 148/1920 |
| greedy_conservador | -1 | -213 | 257 | 1 | 16 | 0 | 0 | 2 | 148/1920 |
| regra_margem | 31 | -181 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -181 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 37 | -174 | 219 | 0 | 26 | 2 | 2 | 0 | 10/1920 |
| guardiao_72h[regra_margem_imatura] | 37 | -174 | 219 | 0 | 23 | 2 | 2 | 0 | 12/1920 |
| regra_margem_null_zero | 47 | -164 | 209 | 1 | 35 | 4 | 4 | 0 | 25/1920 |

### gatilho_legado_joinads

5352 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`ccd0f36c910d…`); 51.3 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -217 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 217 | 0 | 72 | 0 | 20 | 0 | 0 | 2 | 156/1920 |
| greedy_conservador | -2 | -218 | 258 | 2 | 17 | 0 | 0 | 2 | 156/1920 |
| regra_margem | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 37 | -179 | 219 | 0 | 27 | 2 | 2 | 0 | 12/1920 |
| guardiao_72h[regra_margem_imatura] | 37 | -179 | 219 | 0 | 24 | 2 | 2 | 0 | 14/1920 |
| regra_margem_null_zero | 47 | -170 | 209 | 1 | 36 | 4 | 4 | 0 | 27/1920 |

## Contraprovas (resumo; a prova são os testes `test_shadow_*`)

| política | cortes antes da injeção | alterados antes | cortes depois | alterados depois | vazou? |
|---|---:|---:|---:|---:|---|
| controle_trapaceira | 20 | 20 | 19 | 19 | **sim** |
| manter | 20 | 0 | 19 | 19 | não |
| regra_margem | 20 | 0 | 19 | 19 | não |

| política | snapshots com lacuna | distingue null de zero | sensível a valores | cega | suspeita null→0 |
|---|---:|---:|---:|---|---|
| manter | 10 | 0 | 0 | True | não |
| regra_margem | 10 | 2 | 9 | False | não |
| regra_margem_null_zero | 10 | 0 | 10 | False | **sim** |
