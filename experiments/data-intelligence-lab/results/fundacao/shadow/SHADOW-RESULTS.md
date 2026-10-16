# Shadow engine — resultados (TESTADO COM SINTÉTICO)

> **Gerado** por `scripts/fundacao_shadow.py` a partir de `shadow_resultados.json`; não editar à mão.
> **Natureza:** gerador provisório e/ou Simulator Lab (thread E). Lucro contrafactual vem da VERDADE do
> gerador. Nada aqui é eficácia, calibração ou validação com dado real.

- versão do código: `a7a678e4b3f9663c…`; sha determinístico: `68086fa0bae2b887…`
- kernel: provisório com `cobertura_sem_earnings=bloquear`; simulador com `aceitar_declarado` (a E não emite /earnings)
- decisão diária às 7h (America/Sao_Paulo), aplicada ao dia seguinte; menu do oráculo: manter, reduzir 30%, pausar
- valores em BRL (micros ÷ 10⁶), arredondados; `vs manter` positivo = ganharia contra não fazer nada

## Fonte: provisorio

### base

2375 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`092d5faebe76…`); 23.41 ms/corte (8 políticas). Lucro de `manter`: 128.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | 728 | 2.045 | 0 | 0 | 0 | 0 | 0 | 0/1440 |
| equal | -728 | 0 | 2.774 | 728 | 26 | 12 | 0 | 0 | 120/1440 |
| greedy_conservador | 236 | 965 | 1.837 | 0 | 15 | 0 | 0 | 0 | 120/1440 |
| regra_margem | 1.670 | 2.399 | 374 | 0 | 27 | 0 | 0 | 0 | 6/1440 |
| guardiao_72h[regra_margem] | 1.670 | 2.399 | 374 | 0 | 27 | 0 | 0 | 0 | 6/1440 |
| regra_margem_imatura | 1.862 | 2.591 | 182 | 0 | 35 | 2 | 2 | 0 | 4/1440 |
| guardiao_72h[regra_margem_imatura] | 1.678 | 2.406 | 367 | 0 | 31 | 2 | 2 | 0 | 8/1440 |
| regra_margem_null_zero | 0 | 728 | 2.045 | 0 | 0 | 0 | 0 | 49 | 88/1440 |

### campanha_nova

2200 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`2685b9c12e93…`); 19.34 ms/corte (8 políticas). Lucro de `manter`: 232.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | 791 | 1.965 | 0 | 0 | 0 | 0 | 0 | 0/1383 |
| equal | -791 | 0 | 2.756 | 791 | 22 | 12 | 0 | 0 | 114/1383 |
| greedy_conservador | 181 | 972 | 1.806 | 0 | 10 | 0 | 0 | 0 | 114/1383 |
| regra_margem | 1.637 | 2.428 | 328 | 0 | 27 | 0 | 0 | 0 | 6/1383 |
| guardiao_72h[regra_margem] | 1.637 | 2.428 | 328 | 0 | 27 | 0 | 0 | 0 | 6/1383 |
| regra_margem_imatura | 1.815 | 2.606 | 150 | 0 | 33 | 1 | 1 | 0 | 5/1383 |
| guardiao_72h[regra_margem_imatura] | 1.637 | 2.428 | 328 | 0 | 27 | 0 | 0 | 0 | 8/1383 |
| regra_margem_null_zero | 0 | 791 | 1.965 | 0 | 0 | 0 | 0 | 46 | 81/1383 |

### zero_sintetizado

2266 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`5671e66a87f5…`); 19.56 ms/corte (8 políticas). Lucro de `manter`: 128.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | 277 | 2.045 | 0 | 0 | 0 | 0 | 0 | 0/1440 |
| equal | -277 | 0 | 2.322 | 277 | 25 | 4 | 0 | 0 | 102/1440 |
| greedy_conservador | 161 | 438 | 1.887 | 0 | 10 | 0 | 0 | 0 | 102/1440 |
| regra_margem | 1.670 | 1.948 | 374 | 0 | 27 | 0 | 0 | 0 | 7/1440 |
| guardiao_72h[regra_margem] | 1.670 | 1.948 | 374 | 0 | 27 | 0 | 0 | 0 | 7/1440 |
| regra_margem_imatura | 1.862 | 2.140 | 182 | 0 | 35 | 2 | 2 | 0 | 5/1440 |
| guardiao_72h[regra_margem_imatura] | 1.678 | 1.955 | 367 | 0 | 31 | 2 | 2 | 0 | 9/1440 |
| regra_margem_null_zero | 0 | 277 | 2.045 | 0 | 0 | 0 | 0 | 52 | 97/1440 |

### identidade_trocada

2367 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`0b219eecc266…`); 20.21 ms/corte (8 políticas). Lucro de `manter`: 128.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | 422 | 2.045 | 0 | 0 | 0 | 0 | 0 | 0/1440 |
| equal | -422 | 0 | 2.466 | 422 | 17 | 8 | 0 | 24 | 126/1440 |
| greedy_conservador | 47 | 468 | 2.001 | 0 | 3 | 0 | 0 | 20 | 126/1440 |
| regra_margem | 1.120 | 1.541 | 925 | 0 | 19 | 0 | 0 | 8 | 9/1440 |
| guardiao_72h[regra_margem] | 1.120 | 1.541 | 925 | 0 | 19 | 0 | 0 | 8 | 9/1440 |
| regra_margem_imatura | 1.115 | 1.537 | 929 | 0 | 21 | 0 | 0 | 14 | 7/1440 |
| guardiao_72h[regra_margem_imatura] | 931 | 1.353 | 1.114 | 0 | 17 | 0 | 0 | 14 | 11/1440 |
| regra_margem_null_zero | 0 | 422 | 2.045 | 0 | 0 | 0 | 0 | 49 | 59/1440 |

### moeda_misturada

2375 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`4e5d012adfb9…`); 22.62 ms/corte (8 políticas). Lucro de `manter`: 128.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | 789 | 2.045 | 0 | 0 | 0 | 0 | 0 | 0/1440 |
| equal | -789 | 0 | 2.835 | 789 | 16 | 12 | 0 | 10 | 120/1440 |
| greedy_conservador | 192 | 982 | 1.881 | 0 | 10 | 0 | 0 | 5 | 120/1440 |
| regra_margem | 1.505 | 2.294 | 540 | 0 | 18 | 0 | 0 | 9 | 6/1440 |
| guardiao_72h[regra_margem] | 1.505 | 2.294 | 540 | 0 | 18 | 0 | 0 | 9 | 6/1440 |
| regra_margem_imatura | 1.676 | 2.465 | 369 | 0 | 25 | 2 | 2 | 10 | 4/1440 |
| guardiao_72h[regra_margem_imatura] | 1.513 | 2.302 | 532 | 0 | 22 | 2 | 2 | 9 | 8/1440 |
| regra_margem_null_zero | 0 | 789 | 2.045 | 0 | 0 | 0 | 0 | 49 | 76/1440 |

### restatement_tardio

2379 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`69cdc0821732…`); 19.97 ms/corte (8 políticas). Lucro de `manter`: 128.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | 728 | 2.045 | 0 | 0 | 0 | 0 | 0 | 0/1440 |
| equal | -728 | 0 | 2.774 | 728 | 26 | 12 | 0 | 0 | 120/1440 |
| greedy_conservador | 236 | 965 | 1.837 | 0 | 15 | 0 | 0 | 0 | 120/1440 |
| regra_margem | 1.670 | 2.399 | 374 | 0 | 27 | 0 | 0 | 0 | 7/1440 |
| guardiao_72h[regra_margem] | 1.670 | 2.399 | 374 | 0 | 27 | 0 | 0 | 0 | 7/1440 |
| regra_margem_imatura | 1.862 | 2.591 | 182 | 0 | 35 | 2 | 2 | 0 | 4/1440 |
| guardiao_72h[regra_margem_imatura] | 1.678 | 2.406 | 367 | 0 | 31 | 2 | 2 | 0 | 8/1440 |
| regra_margem_null_zero | 0 | 728 | 2.045 | 0 | 0 | 0 | 0 | 49 | 88/1440 |

## Fonte: simulador

### estavel

3538 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`467905e74345…`); 28.37 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -217 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 217 | 0 | 72 | 0 | 20 | 0 | 0 | 2 | 156/1920 |
| greedy_conservador | -2 | -218 | 258 | 2 | 17 | 0 | 0 | 2 | 156/1920 |
| regra_margem | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 37 | -179 | 219 | 0 | 27 | 2 | 2 | 0 | 12/1920 |
| guardiao_72h[regra_margem_imatura] | 37 | -179 | 219 | 0 | 24 | 2 | 2 | 0 | 14/1920 |
| regra_margem_null_zero | 44 | -173 | 212 | 0 | 28 | 1 | 1 | 8 | 29/1920 |

### campanha_nova_aprendendo

3177 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`6393d9e7ad72…`); 22.06 ms/corte (8 políticas). Lucro de `manter`: -190.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -220 | 277 | 0 | 0 | 0 | 0 | 0 | 0/1913 |
| equal | 220 | 0 | 92 | 0 | 19 | 0 | 0 | 2 | 154/1913 |
| greedy_conservador | -1 | -221 | 278 | 1 | 12 | 0 | 0 | 2 | 154/1913 |
| regra_margem | 50 | -169 | 226 | 0 | 35 | 2 | 0 | 0 | 11/1913 |
| guardiao_72h[regra_margem] | 50 | -169 | 226 | 0 | 35 | 2 | 0 | 0 | 11/1913 |
| regra_margem_imatura | 55 | -165 | 222 | 0 | 41 | 3 | 3 | 0 | 6/1913 |
| guardiao_72h[regra_margem_imatura] | 50 | -169 | 227 | 0 | 34 | 2 | 2 | 0 | 11/1913 |
| regra_margem_null_zero | 73 | -146 | 204 | 0 | 41 | 3 | 3 | 11 | 26/1913 |

### atraso_receita_longo

3409 observações, 241 cortes horários, 1928 decisões, 80 resultados maduros no ledger (`d45b7a9809b9…`); 25.49 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -151 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 151 | 0 | 135 | 1 | 20 | 3 | 0 | 3 | 156/1920 |
| greedy_conservador | -1 | -152 | 257 | 1 | 14 | 1 | 0 | 3 | 157/1920 |
| regra_margem | 64 | -87 | 192 | 0 | 34 | 4 | 0 | 0 | 22/1920 |
| guardiao_72h[regra_margem] | 64 | -87 | 192 | 0 | 34 | 4 | 0 | 0 | 22/1920 |
| regra_margem_imatura | 145 | -6 | 111 | 0 | 56 | 10 | 10 | 0 | 30/1920 |
| guardiao_72h[regra_margem_imatura] | 130 | -21 | 126 | 0 | 49 | 8 | 8 | 0 | 38/1920 |
| regra_margem_null_zero | 0 | -151 | 256 | 0 | 0 | 0 | 0 | 69 | 131/1920 |

### restatement_custo

3538 observações, 241 cortes horários, 1928 decisões, 80 resultados maduros no ledger (`244ecda50df4…`); 22.62 ms/corte (8 políticas). Lucro de `manter`: 94.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -124 | 96 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 124 | 0 | 36 | 0 | 19 | 1 | 0 | 2 | 156/1920 |
| greedy_conservador | 0 | -124 | 96 | 0 | 15 | 0 | 0 | 2 | 163/1920 |
| regra_margem | 14 | -111 | 82 | 1 | 25 | 5 | 0 | 0 | 21/1920 |
| guardiao_72h[regra_margem] | 14 | -111 | 82 | 1 | 25 | 5 | 0 | 0 | 21/1920 |
| regra_margem_imatura | 14 | -110 | 82 | 2 | 34 | 6 | 6 | 0 | 23/1920 |
| guardiao_72h[regra_margem_imatura] | 16 | -108 | 80 | 1 | 31 | 5 | 5 | 0 | 26/1920 |
| regra_margem_null_zero | 18 | -106 | 78 | 1 | 35 | 5 | 5 | 6 | 47/1920 |

### fonte_fora_do_ar

3562 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`1af9ec696f05…`); 20.5 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -202 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 202 | 0 | 85 | 0 | 19 | 0 | 0 | 2 | 140/1920 |
| greedy_conservador | -2 | -204 | 258 | 2 | 17 | 0 | 0 | 2 | 140/1920 |
| regra_margem | 29 | -173 | 227 | 0 | 19 | 1 | 0 | 0 | 28/1920 |
| guardiao_72h[regra_margem] | 29 | -173 | 227 | 0 | 19 | 1 | 0 | 0 | 28/1920 |
| regra_margem_imatura | 29 | -173 | 227 | 0 | 23 | 1 | 1 | 0 | 25/1920 |
| guardiao_72h[regra_margem_imatura] | 29 | -173 | 227 | 0 | 20 | 1 | 1 | 0 | 27/1920 |
| regra_margem_null_zero | 26 | -176 | 230 | 0 | 17 | 1 | 1 | 35 | 46/1920 |

### outlier_bot

3538 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`34f67bf1dd42…`); 22.86 ms/corte (8 políticas). Lucro de `manter`: -135.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -218 | 267 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 218 | 0 | 82 | 0 | 20 | 0 | 0 | 2 | 156/1920 |
| greedy_conservador | -0 | -218 | 267 | 1 | 16 | 1 | 0 | 2 | 156/1920 |
| regra_margem | 42 | -176 | 225 | 0 | 27 | 2 | 0 | 0 | 21/1920 |
| guardiao_72h[regra_margem] | 42 | -176 | 225 | 0 | 27 | 2 | 0 | 0 | 21/1920 |
| regra_margem_imatura | 46 | -171 | 221 | 1 | 34 | 7 | 7 | 0 | 11/1920 |
| guardiao_72h[regra_margem_imatura] | 47 | -171 | 220 | 0 | 30 | 6 | 6 | 0 | 15/1920 |
| regra_margem_null_zero | 45 | -173 | 222 | 0 | 38 | 6 | 6 | 8 | 28/1920 |

### quebra_regime_rpm

3538 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`1692ada5e9ff…`); 23.04 ms/corte (8 políticas). Lucro de `manter`: -1.012.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -602 | 1.079 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 602 | 0 | 486 | 0 | 17 | 0 | 0 | 2 | 156/1920 |
| greedy_conservador | 1 | -601 | 1.078 | 2 | 17 | 0 | 0 | 2 | 156/1920 |
| regra_margem | 350 | -252 | 729 | 0 | 28 | 1 | 0 | 0 | 20/1920 |
| guardiao_72h[regra_margem] | 350 | -252 | 729 | 0 | 28 | 1 | 0 | 0 | 20/1920 |
| regra_margem_imatura | 535 | -67 | 544 | 0 | 40 | 1 | 1 | 0 | 11/1920 |
| guardiao_72h[regra_margem_imatura] | 535 | -67 | 544 | 0 | 37 | 1 | 1 | 0 | 13/1920 |
| regra_margem_null_zero | 636 | 35 | 442 | 0 | 37 | 0 | 0 | 8 | 30/1920 |

### mudanca_orcamento

3538 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`7d690e5b7e07…`); 25.36 ms/corte (8 políticas). Lucro de `manter`: -5.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -132 | 167 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 132 | 0 | 74 | 0 | 23 | 1 | 0 | 2 | 156/1920 |
| greedy_conservador | 4 | -128 | 167 | 0 | 17 | 1 | 0 | 2 | 156/1920 |
| regra_margem | 60 | -72 | 107 | 0 | 22 | 1 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 60 | -72 | 107 | 0 | 22 | 1 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 82 | -50 | 85 | 0 | 25 | 1 | 1 | 0 | 9/1920 |
| guardiao_72h[regra_margem_imatura] | 68 | -64 | 99 | 0 | 22 | 1 | 1 | 0 | 12/1920 |
| regra_margem_null_zero | 66 | -66 | 101 | 0 | 26 | 1 | 1 | 6 | 23/1920 |

### sazonal_fim_de_semana

3538 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`0331a05cf036…`); 23.15 ms/corte (8 políticas). Lucro de `manter`: -144.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -190 | 266 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 190 | 0 | 96 | 0 | 19 | 0 | 0 | 2 | 156/1920 |
| greedy_conservador | 0 | -190 | 266 | 1 | 16 | 0 | 0 | 2 | 156/1920 |
| regra_margem | 26 | -164 | 240 | 0 | 23 | 1 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 26 | -164 | 240 | 0 | 23 | 1 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 30 | -160 | 237 | 0 | 27 | 1 | 1 | 0 | 10/1920 |
| guardiao_72h[regra_margem_imatura] | 30 | -160 | 237 | 0 | 24 | 1 | 1 | 0 | 13/1920 |
| regra_margem_null_zero | 38 | -152 | 229 | 0 | 26 | 0 | 0 | 7 | 29/1920 |

### zero_falso

3538 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`3237ee56c805…`); 22.96 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -202 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 202 | 0 | 85 | 0 | 19 | 0 | 0 | 2 | 138/1920 |
| greedy_conservador | -1 | -203 | 257 | 2 | 14 | 1 | 0 | 2 | 138/1920 |
| regra_margem | 31 | -171 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -171 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 35 | -167 | 221 | 0 | 27 | 2 | 2 | 0 | 12/1920 |
| guardiao_72h[regra_margem_imatura] | 35 | -167 | 221 | 0 | 24 | 2 | 2 | 0 | 14/1920 |
| regra_margem_null_zero | 47 | -155 | 209 | 0 | 25 | 2 | 2 | 10 | 45/1920 |

### zero_sintetizado_coletor

12760 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`f3b01fb03cce…`); 117.08 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -217 | 256 | 0 | 0 | 0 | 0 | 0 | 0/9600 |
| equal | 217 | 0 | 72 | 0 | 19 | 0 | 0 | 2 | 154/9600 |
| greedy_conservador | -1 | -218 | 257 | 2 | 14 | 1 | 0 | 2 | 154/9600 |
| regra_margem | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/9600 |
| guardiao_72h[regra_margem] | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/9600 |
| regra_margem_imatura | 37 | -180 | 219 | 0 | 27 | 2 | 2 | 0 | 12/9600 |
| guardiao_72h[regra_margem_imatura] | 37 | -180 | 219 | 0 | 24 | 2 | 2 | 0 | 14/9600 |
| regra_margem_null_zero | 49 | -168 | 207 | 0 | 29 | 2 | 2 | 8 | 99/9600 |

### identidade_trocada

3538 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`ae06b828bd0b…`); 27.25 ms/corte (8 políticas). Lucro de `manter`: -89.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -138 | 230 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 138 | 0 | 115 | 0 | 17 | 0 | 0 | 22 | 153/1920 |
| greedy_conservador | -1 | -139 | 231 | 1 | 8 | 0 | 0 | 5 | 150/1920 |
| regra_margem | 3 | -135 | 227 | 0 | 15 | 1 | 0 | 6 | 13/1920 |
| guardiao_72h[regra_margem] | 3 | -135 | 227 | 0 | 15 | 1 | 0 | 6 | 13/1920 |
| regra_margem_imatura | 7 | -130 | 223 | 0 | 19 | 1 | 1 | 8 | 13/1920 |
| guardiao_72h[regra_margem_imatura] | 7 | -130 | 223 | 0 | 16 | 1 | 1 | 8 | 15/1920 |
| regra_margem_null_zero | 8 | -130 | 223 | 0 | 15 | 1 | 1 | 18 | 26/1920 |

### moeda_misturada

3538 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`6daf68f099f5…`); 23.11 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -217 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 217 | 0 | 72 | 0 | 20 | 0 | 0 | 2 | 156/1920 |
| greedy_conservador | -2 | -218 | 258 | 2 | 17 | 0 | 0 | 2 | 156/1920 |
| regra_margem | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 37 | -179 | 219 | 0 | 27 | 2 | 2 | 0 | 12/1920 |
| guardiao_72h[regra_margem_imatura] | 37 | -179 | 219 | 0 | 24 | 2 | 2 | 0 | 14/1920 |
| regra_margem_null_zero | 44 | -173 | 212 | 0 | 28 | 1 | 1 | 8 | 29/1920 |

### vazamento_tentado

3673 observações, 241 cortes horários, 1928 decisões, 80 resultados maduros no ledger (`aa8fb395a5ce…`); 22.35 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -217 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 217 | 0 | 72 | 0 | 20 | 0 | 0 | 2 | 156/1920 |
| greedy_conservador | -2 | -218 | 258 | 2 | 17 | 0 | 0 | 2 | 159/1920 |
| regra_margem | 31 | -186 | 225 | 0 | 23 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -186 | 225 | 0 | 23 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 40 | -177 | 216 | 0 | 26 | 2 | 2 | 0 | 9/1920 |
| guardiao_72h[regra_margem_imatura] | 40 | -177 | 216 | 0 | 23 | 2 | 2 | 0 | 11/1920 |
| regra_margem_null_zero | 43 | -174 | 213 | 0 | 24 | 1 | 1 | 8 | 28/1920 |

### custo_d0_multiversao

8212 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`5f4d87ae0d84…`); 22.99 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -218 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 218 | 0 | 72 | 0 | 20 | 0 | 0 | 2 | 158/1920 |
| greedy_conservador | -2 | -220 | 258 | 2 | 17 | 0 | 0 | 2 | 158/1920 |
| regra_margem | 31 | -188 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -188 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 37 | -181 | 219 | 0 | 27 | 2 | 2 | 0 | 12/1920 |
| guardiao_72h[regra_margem_imatura] | 37 | -181 | 219 | 0 | 24 | 2 | 2 | 0 | 14/1920 |
| regra_margem_null_zero | 44 | -174 | 212 | 0 | 28 | 1 | 1 | 8 | 29/1920 |

### execucao_presa

3389 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`6fa7c74f21c5…`); 26.7 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -211 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 211 | 0 | 72 | 0 | 20 | 0 | 0 | 2 | 148/1920 |
| greedy_conservador | -1 | -213 | 257 | 1 | 16 | 0 | 0 | 2 | 148/1920 |
| regra_margem | 31 | -181 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -181 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 37 | -174 | 219 | 0 | 26 | 2 | 2 | 0 | 10/1920 |
| guardiao_72h[regra_margem_imatura] | 37 | -174 | 219 | 0 | 23 | 2 | 2 | 0 | 12/1920 |
| regra_margem_null_zero | 44 | -168 | 212 | 0 | 27 | 1 | 1 | 8 | 27/1920 |

### gatilho_legado_joinads

5352 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`9d7f2973a89d…`); 31.78 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -217 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 217 | 0 | 72 | 0 | 20 | 0 | 0 | 2 | 156/1920 |
| greedy_conservador | -2 | -218 | 258 | 2 | 17 | 0 | 0 | 2 | 156/1920 |
| regra_margem | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 37 | -179 | 219 | 0 | 27 | 2 | 2 | 0 | 12/1920 |
| guardiao_72h[regra_margem_imatura] | 37 | -179 | 219 | 0 | 24 | 2 | 2 | 0 | 14/1920 |
| regra_margem_null_zero | 44 | -173 | 212 | 0 | 28 | 1 | 1 | 8 | 29/1920 |

### sensor_sem_campanha

3354 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`2ce05b7d6453…`); 27.03 ms/corte (8 políticas). Lucro de `manter`: -114.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -217 | 256 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 217 | 0 | 72 | 0 | 20 | 0 | 0 | 2 | 156/1920 |
| greedy_conservador | -2 | -218 | 258 | 2 | 17 | 0 | 0 | 2 | 156/1920 |
| regra_margem | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| guardiao_72h[regra_margem] | 31 | -186 | 225 | 0 | 22 | 2 | 0 | 0 | 15/1920 |
| regra_margem_imatura | 37 | -179 | 219 | 0 | 27 | 2 | 2 | 0 | 12/1920 |
| guardiao_72h[regra_margem_imatura] | 37 | -179 | 219 | 0 | 24 | 2 | 2 | 0 | 14/1920 |
| regra_margem_null_zero | 44 | -173 | 212 | 0 | 28 | 1 | 1 | 8 | 29/1920 |

### dedup_por_segundo

3538 observações, 241 cortes horários, 1928 decisões, 72 resultados maduros no ledger (`dbe1d43304fd…`); 23.46 ms/corte (8 políticas). Lucro de `manter`: -139.

| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| manter | 0 | -218 | 267 | 0 | 0 | 0 | 0 | 0 | 0/1920 |
| equal | 218 | 0 | 82 | 0 | 20 | 0 | 0 | 2 | 156/1920 |
| greedy_conservador | -0 | -218 | 267 | 1 | 16 | 1 | 0 | 2 | 156/1920 |
| regra_margem | 46 | -172 | 221 | 0 | 27 | 2 | 0 | 0 | 19/1920 |
| guardiao_72h[regra_margem] | 46 | -172 | 221 | 0 | 27 | 2 | 0 | 0 | 19/1920 |
| regra_margem_imatura | 46 | -171 | 220 | 1 | 36 | 7 | 7 | 0 | 13/1920 |
| guardiao_72h[regra_margem_imatura] | 47 | -171 | 220 | 0 | 32 | 6 | 6 | 0 | 17/1920 |
| regra_margem_null_zero | 45 | -173 | 222 | 0 | 38 | 6 | 6 | 8 | 25/1920 |

## Contraprovas (resumo; a prova são os testes `test_shadow_*`)

| política | cortes antes da injeção | alterados antes | cortes depois | alterados depois | vazou? |
|---|---:|---:|---:|---:|---|
| regra_margem | 20 | 0 | 19 | 19 | não |
| manter | 20 | 0 | 19 | 19 | não |
| controle_trapaceira | 20 | 20 | 19 | 19 | **sim** |

| política | snapshots com lacuna | distingue null de zero | sensível a valores | cega | suspeita null→0 |
|---|---:|---:|---:|---|---|
| manter | 10 | 0 | 0 | True | não |
| regra_margem | 10 | 2 | 9 | False | não |
| regra_margem_null_zero | 10 | 0 | 10 | False | **sim** |
