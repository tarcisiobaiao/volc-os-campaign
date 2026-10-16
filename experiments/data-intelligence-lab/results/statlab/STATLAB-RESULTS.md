# STATLAB — resultados (worker D, Fase 4)

> Tudo abaixo é **simulação com seed**, sem dado real. Parâmetros (n, CVR, atrasos, limiares, top-k) são de cenário, nunca defaults operacionais. Gerado por `scripts/statlab_relatorio.py` a partir dos JSONs desta pasta.

Versões: python 3.13.0, numpy 2.5.3, scipy 1.18.1, statsmodels 0.15.0, statlab 0.1.0. Seeds e n de simulações estão em cada seção e em cada JSON.

## 0. Sonda `confseq`

- instalação padrão: **FALHOU** — confseq==0.0.11 (sdist; único candidato); build CMake falha: Boost ≥ 1.70 ausente (e Ninja ausente).
- somente wheel: **FALHOU** — nenhuma versão de confseq tem wheel utilizável para cp313 macOS arm64.
- import no venv da sonda: `ModuleNotFoundError: No module named 'confseq'`.
- decisão: não usar confseq no ambiente principal; CS implementada em NumPy (volc_dil.statlab.sequencias_confianca, PrPl-EB). Compilar exigiria Boost >= 1.70 e CMake/Ninja instalados globalmente — proibido nesta fase.

## 1. Maturação / nowcasting (seed base 20261015, 300 mundos por cenário, as_of=149, idade final=60 dias)

Método base: fator m(a) = Σobs(a)/Σfinal nas últimas 28 coortes maduras antes do as_of (chain-ladder restrito a coortes maduras). Guarda: m(a) < 0,3 ou < 14 coortes válidas → `insuficiente`. Intervalo 90%: (i) razão empírica final/obs(a) das coortes maduras (preditivo); (ii) bootstrap só do fator. Limiares são parâmetros de cenário. IC95 de Monte Carlo entre colchetes, **por mundo** (as idades de um mesmo mundo compartilham o fator e não são independentes); com 0% ou 100% em todos os mundos o IC normal degenera em largura zero — leia como 'em nenhum/todos os 300 mundos'.

### `custo_rapido` (seed 20261015)
Verdade final por coorte: p5/p50/p95 = 129.714, 214.229, 341.532; fração zero = 0.000.

| idade (d) | m(a) médio | MAPE sem guarda | APE máx sem guarda | % insuficiente c/ guarda | viés rel. c/ guarda | cobertura IC90 razão | cobertura IC90 bootstrap-fator |
|---|---|---|---|---|---|---|---|
| 0–0 | 0.769 | 0.021 [0.020; 0.023] | 0.080 | 0.0% [0.0; 0.0] | 0.004 | 88.7% [85.1; 92.3] | 25.7% [20.7; 30.6] |
| 1–2 | 0.967 | 0.007 [0.007; 0.008] | 0.049 | 0.0% [0.0; 0.0] | 6.27e-04 | 85.8% [83.0; 88.6] | 25.0% [21.6; 28.4] |
| 3–6 | 0.999 | 0.001 [9.33e-04; 0.001] | 0.016 | 0.0% [0.0; 0.0] | 3.36e-05 | 94.1% [92.7; 95.5] | 47.7% [45.9; 49.4] |
| 7–13 | 1.000 | 3.08e-06 [9.26e-07; 5.23e-06] | 0.002 | 0.0% [0.0; 0.0] | 1.34e-06 | 100.0% [99.9; 100.0] | 100.0% [99.9; 100.0] |
| 14–29 | 1.000 | 0.000 [0.000; 0.000] | 0.000 | 0.0% [0.0; 0.0] | 0.000 | 100.0% [100.0; 100.0] | 100.0% [100.0; 100.0] |
| 30–59 | 1.000 | 0.000 [0.000; 0.000] | 0.000 | 0.0% [0.0; 0.0] | 0.000 | 100.0% [100.0; 100.0] | 100.0% [100.0; 100.0] |

### `receita_baixa_magnitude_centavo_ate_d3` (seed 20267015)
Verdade final por coorte: p5/p50/p95 = 0.020, 0.320, 1.080; fração zero = 0.032.

| idade (d) | m(a) médio | MAPE sem guarda | APE máx sem guarda | % insuficiente c/ guarda | viés rel. c/ guarda | cobertura IC90 razão | cobertura IC90 bootstrap-fator |
|---|---|---|---|---|---|---|---|
| 0–0 | 0.351 | 0.719 [0.665; 0.773] | 3.159 | 25.0% [20.1; 29.9] | -0.105 | 89.7% [85.3; 94.1] (sem IC: 115) | 21.3% [16.0; 26.7] |
| 1–2 | 0.798 | 0.257 [0.239; 0.275] | 1.061 | 0.0% [0.0; 0.0] | -9.25e-05 | 91.7% [89.3; 94.0] (sem IC: 23) | 17.7% [14.6; 20.7] |
| 3–6 | 1.000 | 0.000 [0.000; 0.000] | 0.000 | 0.0% [0.0; 0.0] | 0.000 | 100.0% [100.0; 100.0] (sem IC: 55) | 100.0% [100.0; 100.0] |

### `receita_baixa_magnitude_sem_arredondar_ate_d3` (seed 20268015)
Verdade final por coorte: p5/p50/p95 = 0.031, 0.306, 1.058; fração zero = 0.026.

| idade (d) | m(a) médio | MAPE sem guarda | APE máx sem guarda | % insuficiente c/ guarda | viés rel. c/ guarda | cobertura IC90 razão | cobertura IC90 bootstrap-fator |
|---|---|---|---|---|---|---|---|
| 0–0 | 0.349 | 0.735 [0.671; 0.798] | 3.395 | 23.7% [18.8; 28.5] | -0.009 | 82.8% [77.5; 88.2] (sem IC: 108) | 29.3% [23.4; 35.2] |
| 1–2 | 0.805 | 0.256 [0.238; 0.274] | 1.000 | 0.0% [0.0; 0.0] | 0.001 | 91.8% [89.4; 94.1] (sem IC: 19) | 15.5% [12.8; 18.2] |
| 3–6 | 1.000 | 0.000 [0.000; 0.000] | 0.000 | 0.0% [0.0; 0.0] | 0.000 | 100.0% [100.0; 100.0] (sem IC: 46) | 100.0% [100.0; 100.0] |

### `receita_d_mais_1_fator_zero_na_idade_0` (seed 20264015)
Verdade final por coorte: p5/p50/p95 = 48.167, 116.131, 233.435; fração zero = 0.000.

| idade (d) | m(a) médio | MAPE sem guarda | APE máx sem guarda | % insuficiente c/ guarda | viés rel. c/ guarda | cobertura IC90 razão | cobertura IC90 bootstrap-fator |
|---|---|---|---|---|---|---|---|
| 0–0 | 0.000 | — | — | 100.0% [100.0; 100.0] | — | — (sem IC: 300) | — |
| 1–2 | 0.237 | 0.478 [0.449; 0.508] | 3.060 | 73.0% [70.2; 75.8] | -0.110 | 85.2% [79.7; 90.7] (sem IC: 438) | 20.4% [14.1; 26.6] |
| 3–6 | 0.550 | 0.279 [0.267; 0.291] | 1.264 | 0.1% [0.0; 0.2] | 0.019 | 80.0% [77.6; 82.4] (sem IC: 2) | 19.9% [17.7; 22.2] |
| 7–13 | 0.827 | 0.116 [0.112; 0.120] | 0.738 | 0.0% [0.0; 0.0] | 0.007 | 85.4% [83.8; 87.0] | 22.8% [20.9; 24.6] |
| 14–29 | 0.973 | 0.031 [0.029; 0.032] | 0.643 | 0.0% [0.0; 0.0] | 0.001 | 92.2% [91.3; 93.0] | 17.6% [16.4; 18.9] |
| 30–59 | 0.999 | 0.002 [0.001; 0.002] | 0.317 | 0.0% [0.0; 0.0] | 6.04e-05 | 98.0% [97.7; 98.3] | 90.2% [89.2; 91.2] |

### `receita_estavel` (seed 20262015)
Verdade final por coorte: p5/p50/p95 = 48.895, 117.081, 235.901; fração zero = 0.000.

| idade (d) | m(a) médio | MAPE sem guarda | APE máx sem guarda | % insuficiente c/ guarda | viés rel. c/ guarda | cobertura IC90 razão | cobertura IC90 bootstrap-fator |
|---|---|---|---|---|---|---|---|
| 0–0 | 0.084 | 0.703 [0.631; 0.775] | 5.101 | 100.0% [100.0; 100.0] | — | — (sem IC: 300) | — |
| 1–2 | 0.319 | 0.385 [0.361; 0.409] | 1.960 | 48.5% [47.4; 49.6] | 0.009 | 81.4% [77.1; 85.8] (sem IC: 291) | 23.2% [18.5; 28.0] |
| 3–6 | 0.618 | 0.222 [0.213; 0.232] | 0.915 | 0.0% [0.0; 0.0] | 3.43e-04 | 82.1% [80.0; 84.2] | 22.8% [20.5; 25.2] |
| 7–13 | 0.840 | 0.108 [0.104; 0.112] | 0.683 | 0.0% [0.0; 0.0] | 0.007 | 85.2% [83.6; 86.8] | 21.6% [19.6; 23.5] |
| 14–29 | 0.956 | 0.047 [0.046; 0.049] | 0.698 | 0.0% [0.0; 0.0] | -4.22e-04 | 91.2% [90.3; 92.1] | 19.5% [18.3; 20.6] |
| 30–59 | 0.994 | 0.009 [0.008; 0.009] | 0.375 | 0.0% [0.0; 0.0] | -1.77e-05 | 94.4% [93.9; 94.9] | 47.5% [45.9; 49.2] |

### `receita_lenta_fator_perto_de_zero` (seed 20263015)
Verdade final por coorte: p5/p50/p95 = 48.214, 117.378, 235.949; fração zero = 0.000.

| idade (d) | m(a) médio | MAPE sem guarda | APE máx sem guarda | % insuficiente c/ guarda | viés rel. c/ guarda | cobertura IC90 razão | cobertura IC90 bootstrap-fator |
|---|---|---|---|---|---|---|---|
| 0–0 | 0.022 | 1.363 [1.118; 1.609] | 17.144 | 100.0% [100.0; 100.0] | — | — (sem IC: 300) | — |
| 1–2 | 0.106 | 0.698 [0.646; 0.750] | 5.872 | 100.0% [100.0; 100.0] | — | — (sem IC: 600) | — |
| 3–6 | 0.280 | 0.464 [0.442; 0.487] | 2.750 | 58.9% [57.0; 60.8] | -0.005 | 87.3% [84.2; 90.4] (sem IC: 707) | 25.3% [21.2; 29.4] |
| 7–13 | 0.511 | 0.282 [0.274; 0.291] | 1.535 | 0.0% [0.0; 0.0] | 9.45e-04 | 81.9% [80.2; 83.6] (sem IC: 1) | 21.4% [19.5; 23.2] |
| 14–29 | 0.759 | 0.147 [0.144; 0.151] | 0.853 | 0.0% [0.0; 0.0] | 0.004 | 85.3% [84.2; 86.5] | 22.8% [21.5; 24.2] |
| 30–59 | 0.944 | 0.052 [0.051; 0.054] | 0.666 | 0.0% [0.0; 0.0] | 0.002 | 90.0% [89.3; 90.7] | 24.4% [23.5; 25.3] |

### `receita_mudanca_regime_atraso_metade_ultimas_30_coortes` (seed 20266015)
Verdade final por coorte: p5/p50/p95 = 48.345, 116.451, 233.029; fração zero = 0.000.

| idade (d) | m(a) médio | MAPE sem guarda | APE máx sem guarda | % insuficiente c/ guarda | viés rel. c/ guarda | cobertura IC90 razão | cobertura IC90 bootstrap-fator |
|---|---|---|---|---|---|---|---|
| 0–0 | 0.086 | 2.056 [1.870; 2.242] | 9.289 | 100.0% [100.0; 100.0] | — | — (sem IC: 300) | — |
| 1–2 | 0.318 | 0.928 [0.880; 0.975] | 2.920 | 48.2% [47.0; 49.3] | 0.703 | 45.8% [40.2; 51.4] (sem IC: 289) | 5.4% [2.9; 7.8] |
| 3–6 | 0.616 | 0.393 [0.380; 0.405] | 1.288 | 0.0% [0.0; 0.0] | 0.346 | 42.5% [39.7; 45.3] | 7.5% [6.0; 9.0] |
| 7–13 | 0.838 | 0.153 [0.149; 0.157] | 0.660 | 0.0% [0.0; 0.0] | 0.144 | 49.3% [46.8; 51.9] | 6.4% [5.3; 7.4] |
| 14–29 | 0.955 | 0.045 [0.043; 0.046] | 0.531 | 0.0% [0.0; 0.0] | 0.038 | 92.8% [91.7; 93.8] | 5.4% [4.7; 6.0] |
| 30–59 | 0.994 | 0.009 [0.009; 0.010] | 0.590 | 0.0% [0.0; 0.0] | 7.17e-04 | 95.0% [94.6; 95.5] | 47.2% [45.7; 48.8] |

Variante link-ratio (usa coortes parcialmente maduras) no mesmo mundo:

| idade | viés rel. coortes maduras | viés rel. link-ratio | % insuf. link-ratio | APE máx link-ratio sem guarda |
|---|---|---|---|---|
| 0–0 | — | -0.305 | 99.7% [99.0; 100.0] | 2.172 |
| 1–2 | 0.703 | 0.134 | 0.0% [0.0; 0.0] | 1.101 |
| 3–6 | 0.346 | 0.091 | 0.0% [0.0; 0.0] | 0.708 |
| 7–13 | 0.144 | 0.072 | 0.0% [0.0; 0.0] | 0.676 |
| 14–29 | 0.038 | 0.031 | 0.0% [0.0; 0.0] | 0.543 |
| 30–59 | 7.17e-04 | 5.37e-04 | 0.0% [0.0; 0.0] | 0.594 |

### `receita_mudanca_regime_atraso_x2_5_ultimas_30_coortes` (seed 20265015)
Verdade final por coorte: p5/p50/p95 = 48.736, 117.082, 236.518; fração zero = 0.000.

| idade (d) | m(a) médio | MAPE sem guarda | APE máx sem guarda | % insuficiente c/ guarda | viés rel. c/ guarda | cobertura IC90 razão | cobertura IC90 bootstrap-fator |
|---|---|---|---|---|---|---|---|
| 0–0 | 0.084 | 0.874 [0.847; 0.901] | 1.000 | 100.0% [100.0; 100.0] | — | — (sem IC: 300) | — |
| 1–2 | 0.318 | 0.740 [0.721; 0.758] | 1.000 | 48.2% [47.0; 49.3] | -0.685 | 30.3% [25.1; 35.6] (sem IC: 299) | 4.0% [1.8; 6.2] |
| 3–6 | 0.617 | 0.549 [0.536; 0.563] | 1.000 | 0.0% [0.0; 0.0] | -0.531 | 29.2% [26.4; 32.0] (sem IC: 3) | 3.4% [2.4; 4.4] |
| 7–13 | 0.839 | 0.350 [0.342; 0.358] | 0.947 | 0.0% [0.0; 0.0] | -0.353 | 33.9% [31.4; 36.3] | 4.9% [3.9; 5.8] |
| 14–29 | 0.956 | 0.158 [0.154; 0.161] | 0.853 | 0.0% [0.0; 0.0] | -0.151 | 44.7% [42.7; 46.8] | 11.0% [10.0; 11.9] |
| 30–59 | 0.994 | 0.009 [0.009; 0.010] | 0.582 | 0.0% [0.0; 0.0] | 3.04e-06 | 94.7% [94.2; 95.3] | 47.4% [45.7; 49.2] |

Variante link-ratio (usa coortes parcialmente maduras) no mesmo mundo:

| idade | viés rel. coortes maduras | viés rel. link-ratio | % insuf. link-ratio | APE máx link-ratio sem guarda |
|---|---|---|---|---|
| 0–0 | — | — | 100.0% [100.0; 100.0] | 14.447 |
| 1–2 | -0.685 | — | 100.0% [100.0; 100.0] | 5.119 |
| 3–6 | -0.531 | -0.307 | 18.2% [16.8; 19.7] | 1.814 |
| 7–13 | -0.353 | -0.248 | 0.0% [0.0; 0.0] | 0.942 |
| 14–29 | -0.151 | -0.136 | 0.0% [0.0; 0.0] | 0.847 |
| 30–59 | 3.04e-06 | 1.44e-04 | 0.0% [0.0; 0.0] | 0.589 |

## 2. Shrinkage Empirical Bayes (300 réplicas por cenário, K=300 unidades, top-k=10, intervalo 90%)

MSE relativo = MSE/MSE do cru na mesma réplica (unidades com n>0). Vencedores por sorte = unidades no top-k estimado fora do top-k verdadeiro. Calibração = cov(est, verdade)/var(est) (1 = calibrado). IC95 de Monte Carlo entre colchetes.

### contagens_gamma_poisson
**`contagem_gamma_heterogenea`** (seed 20271015).

| estimador | MSE rel. ao cru | vencedores por sorte (de k) | regret top-k | calibração | cobertura | cobertura top-10% verdadeiro |
|---|---|---|---|---|---|---|
| cru | 1.000 [1.000; 1.000] | 3.92 [3.78; 4.07] | 0.110 [0.104; 0.116] | 0.74 [0.73; 0.74] | 93.8% [93.6; 93.9] | — |
| eb_mle | 0.609 [0.598; 0.621] | 3.48 [3.33; 3.63] | 0.075 [0.071; 0.079] | 1.00 [1.00; 1.01] | 89.7% [89.5; 89.9] | — |
| eb_momentos | 0.611 [0.599; 0.623] | 3.50 [3.36; 3.65] | 0.075 [0.071; 0.079] | 1.00 [1.00; 1.01] | 89.7% [89.5; 89.9] | — |
| media_grupo | 2.874 [2.801; 2.946] | 9.67 [9.61; 9.73] | 0.682 [0.674; 0.690] | -0.08 [-0.18; 0.02] | — | — |

**`contagem_gamma_quase_homogenea`** (seed 20271115).

| estimador | MSE rel. ao cru | vencedores por sorte (de k) | regret top-k | calibração | cobertura | cobertura top-10% verdadeiro |
|---|---|---|---|---|---|---|
| cru | 1.000 [1.000; 1.000] | 9.36 [9.27; 9.45] | 0.124 [0.122; 0.127] | 0.03 [0.03; 0.03] | 93.3% [93.1; 93.4] | — |
| eb_mle | 0.029 [0.028; 0.029] | 8.97 [8.87; 9.07] | 0.099 [0.097; 0.101] | 82.65 [63.62; 101.67] | 67.3% [63.4; 71.3] | — |
| eb_momentos | 0.029 [0.028; 0.030] | 8.95 [8.85; 9.05] | 0.099 [0.097; 0.101] | 3.97e+03 [3.02e+03; 4.93e+03] | 69.0% [64.9; 73.2] | — |
| media_grupo | 0.030 [0.029; 0.030] | 9.64 [9.57; 9.70] | 0.140 [0.137; 0.142] | -0.05 [-0.14; 0.04] | — | — |

### receita_monetaria
**`receita_cauda_pesada_sigma2`** (seed 20281115). Peso mediano do prior no Gamma-Poisson aplicado a dinheiro: R$ 0.00026 vs centavos 0.0000020 (mesmos dados).

| estimador | MSE rel. ao cru | vencedores por sorte (de k) | regret top-k | calibração | cobertura | cobertura top-10% verdadeiro |
|---|---|---|---|---|---|---|
| cru | 1.000 [1.000; 1.000] | 8.24 [8.11; 8.37] | 0.502 [0.490; 0.514] | 0.10 [0.09; 0.11] | — | — |
| eb_normal_var_empirica | 0.147 [0.133; 0.160] | 8.81 [8.68; 8.94] | 0.606 [0.588; 0.623] | 3.44 [0.42; 6.46] | 43.6% [38.4; 48.8] | — |
| gamma_poisson_centavos | 1.000 [1.000; 1.000] | 8.24 [8.11; 8.37] | 0.502 [0.490; 0.514] | 0.10 [0.09; 0.11] | 0.2% [0.2; 0.2] | — |
| gamma_poisson_reais | 0.999 [0.999; 0.999] | 8.24 [8.11; 8.37] | 0.502 [0.490; 0.514] | 0.10 [0.09; 0.11] | 2.0% [1.9; 2.1] | — |
| hurdle_beta_lognormal | 0.081 [0.073; 0.089] | 6.31 [6.15; 6.48] | 0.286 [0.275; 0.296] | 1.00 [0.98; 1.02] | 87.6% [87.1; 88.1] | — |
| media_grupo | 0.140 [0.126; 0.155] | 9.63 [9.57; 9.69] | 0.744 [0.737; 0.752] | 0.02 [-0.07; 0.10] | — | — |

**`receita_lognormal_zero_inflada`** (seed 20281015). Peso mediano do prior no Gamma-Poisson aplicado a dinheiro: R$ 0.00181 vs centavos 0.0000110 (mesmos dados).

| estimador | MSE rel. ao cru | vencedores por sorte (de k) | regret top-k | calibração | cobertura | cobertura top-10% verdadeiro |
|---|---|---|---|---|---|---|
| cru | 1.000 [1.000; 1.000] | 6.83 [6.68; 6.98] | 0.352 [0.342; 0.363] | 0.32 [0.31; 0.33] | — | — |
| eb_normal_var_empirica | 0.313 [0.300; 0.327] | 6.33 [6.18; 6.48] | 0.293 [0.282; 0.304] | 1.10 [1.07; 1.14] | 90.9% [90.2; 91.6] | — |
| gamma_poisson_centavos | 1.000 [1.000; 1.000] | 6.83 [6.68; 6.98] | 0.352 [0.342; 0.363] | 0.32 [0.31; 0.33] | 0.9% [0.8; 1.0] | — |
| gamma_poisson_reais | 0.989 [0.988; 0.990] | 6.82 [6.68; 6.97] | 0.352 [0.341; 0.362] | 0.32 [0.31; 0.33] | 9.2% [9.0; 9.4] | — |
| hurdle_beta_lognormal | 0.265 [0.252; 0.277] | 5.76 [5.61; 5.92] | 0.232 [0.223; 0.241] | 1.01 [0.99; 1.02] | 89.3% [89.0; 89.5] | — |
| media_grupo | 0.505 [0.482; 0.528] | 9.64 [9.57; 9.71] | 0.751 [0.743; 0.760] | 0.03 [-0.06; 0.11] | — | — |

**`receita_valor_pareto_hurdle_mal_especificado`** (seed 20281215). Peso mediano do prior no Gamma-Poisson aplicado a dinheiro: R$ 0.00131 vs centavos 0.0000080 (mesmos dados).

| estimador | MSE rel. ao cru | vencedores por sorte (de k) | regret top-k | calibração | cobertura | cobertura top-10% verdadeiro |
|---|---|---|---|---|---|---|
| cru | 1.000 [1.000; 1.000] | 6.64 [6.48; 6.80] | 0.342 [0.330; 0.354] | 0.32 [0.31; 0.33] | — | — |
| eb_normal_var_empirica | 0.349 [0.329; 0.368] | 6.60 [6.41; 6.79] | 0.338 [0.321; 0.356] | 1.25 [1.07; 1.43] | 82.6% [79.7; 85.5] | — |
| gamma_poisson_centavos | 1.000 [1.000; 1.000] | 6.64 [6.48; 6.80] | 0.342 [0.330; 0.354] | 0.32 [0.31; 0.33] | 0.9% [0.9; 1.0] | — |
| gamma_poisson_reais | 0.992 [0.991; 0.993] | 6.63 [6.47; 6.79] | 0.342 [0.330; 0.354] | 0.32 [0.31; 0.34] | 9.8% [9.6; 9.9] | — |
| hurdle_beta_lognormal | 0.250 [0.235; 0.264] | 5.26 [5.10; 5.42] | 0.206 [0.198; 0.215] | 1.08 [1.07; 1.10] | 88.1% [87.8; 88.4] | — |
| media_grupo | 0.526 [0.495; 0.558] | 9.71 [9.65; 9.77] | 0.752 [0.745; 0.760] | 4.79e-03 [-0.07; 0.08] | — | — |

### taxas_beta_binomial
**`cvr_beta_unimodal`** (seed 20261015). Status do prior: {"mle": {"estimado": 300}, "momentos": {"estimado": 300}}.

| estimador | MSE rel. ao cru | vencedores por sorte (de k) | regret top-k | calibração | cobertura | cobertura top-10% verdadeiro |
|---|---|---|---|---|---|---|
| cru | 1.000 [1.000; 1.000] | 7.00 [6.86; 7.14] | 0.327 [0.317; 0.337] | 0.33 [0.33; 0.34] | 91.8% [91.6; 92.0] | 91.2% [90.7; 91.8] |
| eb_mle | 0.280 [0.272; 0.288] | 5.91 [5.76; 6.06] | 0.202 [0.195; 0.209] | 1.00 [0.98; 1.01] | 89.9% [89.6; 90.2] | 67.9% [66.6; 69.2] |
| eb_momentos | 0.282 [0.274; 0.289] | 5.93 [5.78; 6.08] | 0.202 [0.194; 0.209] | 1.01 [0.99; 1.02] | 89.4% [89.1; 89.8] | — |
| media_grupo | 0.514 [0.499; 0.528] | 9.66 [9.59; 9.73] | 0.689 [0.681; 0.697] | -0.01 [-0.12; 0.09] | — | — |

**`cvr_bimodal_vencedores_raros`** (seed 20261115). Status do prior: {"mle": {"estimado": 300}, "momentos": {"estimado": 300}}.

| estimador | MSE rel. ao cru | vencedores por sorte (de k) | regret top-k | calibração | cobertura | cobertura top-10% verdadeiro |
|---|---|---|---|---|---|---|
| cru | 1.000 [1.000; 1.000] | 6.27 [6.12; 6.42] | 0.369 [0.357; 0.380] | 0.28 [0.27; 0.28] | 92.1% [91.9; 92.2] | 91.5% [90.9; 92.1] |
| eb_mle | 0.241 [0.233; 0.248] | 5.06 [4.90; 5.23] | 0.234 [0.224; 0.244] | 1.15 [1.13; 1.17] | 91.7% [91.4; 92.0] | 57.3% [55.9; 58.8] |
| eb_momentos | 0.240 [0.233; 0.248] | 5.03 [4.87; 5.19] | 0.234 [0.224; 0.244] | 1.04 [1.02; 1.06] | 92.6% [92.4; 92.9] | — |
| media_grupo | 0.397 [0.384; 0.411] | 9.73 [9.67; 9.78] | 0.744 [0.737; 0.751] | 0.03 [-0.04; 0.10] | — | — |

**`cvr_n_grande_pouco_ganho`** (seed 20261315). Status do prior: {"mle": {"estimado": 300}, "momentos": {"estimado": 300}}.

| estimador | MSE rel. ao cru | vencedores por sorte (de k) | regret top-k | calibração | cobertura | cobertura top-10% verdadeiro |
|---|---|---|---|---|---|---|
| cru | 1.000 [1.000; 1.000] | 0.99 [0.90; 1.07] | 0.004 [0.004; 0.005] | 0.99 [0.99; 0.99] | 89.9% [89.7; 90.1] | 89.6% [89.0; 90.2] |
| eb_mle | 0.986 [0.984; 0.988] | 0.98 [0.89; 1.07] | 0.004 [0.004; 0.005] | 1.00 [1.00; 1.00] | 89.8% [89.6; 90.0] | 89.1% [88.5; 89.8] |
| eb_momentos | 0.986 [0.984; 0.988] | 0.98 [0.89; 1.07] | 0.004 [0.004; 0.005] | 1.00 [1.00; 1.00] | 89.8% [89.6; 90.0] | — |
| media_grupo | 79.558 [78.209; 80.906] | 9.72 [9.66; 9.78] | 0.695 [0.687; 0.703] | 0.03 [-0.06; 0.13] | — | — |

**`cvr_n_informativo`** (seed 20261215). Status do prior: {"mle": {"estimado": 300}, "momentos": {"estimado": 300}}.

| estimador | MSE rel. ao cru | vencedores por sorte (de k) | regret top-k | calibração | cobertura | cobertura top-10% verdadeiro |
|---|---|---|---|---|---|---|
| cru | 1.000 [1.000; 1.000] | 5.61 [5.45; 5.77] | 0.258 [0.248; 0.268] | 0.50 [0.49; 0.51] | 91.8% [91.6; 92.0] | 90.5% [89.9; 91.1] |
| eb_mle | 0.469 [0.458; 0.479] | 3.90 [3.76; 4.05] | 0.100 [0.094; 0.105] | 1.04 [1.03; 1.05] | 85.3% [84.9; 85.7] | 80.2% [79.2; 81.2] |
| eb_momentos | 0.647 [0.630; 0.664] | 3.97 [3.83; 4.11] | 0.105 [0.100; 0.111] | 1.04 [1.02; 1.05] | 78.9% [78.3; 79.5] | — |
| media_grupo | 1.428 [1.380; 1.476] | 9.70 [9.64; 9.76] | 0.715 [0.708; 0.723] | -0.03 [-0.09; 0.03] | — | — |

**`cvr_sem_heterogeneidade`** (seed 20261415). Status do prior: {"mle": {"estimado": 294, "fronteira_mle": 6}, "momentos": {"estimado": 154, "sem_heterogeneidade_detectada": 146}}.

| estimador | MSE rel. ao cru | vencedores por sorte (de k) | regret top-k | calibração | cobertura | cobertura top-10% verdadeiro |
|---|---|---|---|---|---|---|
| cru | 1.000 [1.000; 1.000] | 9.66 [9.59; 9.72] | 0.013 [0.012; 0.013] | -1.75e-05 [-5.11e-05; 1.61e-05] | 91.9% [91.8; 92.1] | 92.2% [91.6; 92.8] |
| eb_mle | 0.002 [0.001; 0.002] | 9.63 [9.57; 9.69] | 0.012 [0.012; 0.012] | 0.59 [-0.64; 1.82] | 85.1% [81.4; 88.9] | 85.5% [81.7; 89.4] |
| eb_momentos | 0.002 [0.002; 0.003] | 9.64 [9.58; 9.70] | 0.012 [0.012; 0.013] | 2.30 [-2.91; 7.50] | 54.3% [49.0; 59.7] | — |
| media_grupo | 0.001 [9.98e-04; 0.001] | 9.69 [9.63; 9.75] | 0.012 [0.012; 0.013] | -0.03 [-0.13; 0.08] | — | — |

## 3. Confidence sequences (1000 trajetórias, T=10000, alpha=0.05)

CS: PrPl-EB, Waudby-Smith & Ramdas (2024) JRSS-B 86(1), seção 3; c = 1/2; running intersection. Comparador: Wald/t de horizonte fixo recalculado a cada passo (peeking). Erro uniforme = fração de trajetórias em que a média verdadeira sai do intervalo em ALGUM t ≥ 10 (e a partir de t ≥ 100 / ≥ 1000, para separar a degeneração de amostra minúscula). IC95 de Monte Carlo (Wilson).

### 3a. Cobertura uniforme no tempo

| outcome (seed) | método | erro uniforme t≥10 | t≥100 | t≥1000 | erro só no horizonte T | largura t=100 | t=1000 | t=T |
|---|---|---|---|---|---|---|---|---|
| bernoulli_p0.05_cvr_baixa (20261016) | cs_prpl_eb | 1.9% [1.2; 2.9] | 1.9% [1.2; 2.9] | 1.9% [1.2; 2.9] | 1.9% [1.2; 2.9] | 0.1396 [0.1378; 0.1414] | 0.0475 [0.0472; 0.0478] | 0.0175 [0.0174; 0.0176] |
| bernoulli_p0.05_cvr_baixa (20261016) | wald_peeking | 79.3% [76.7; 81.7] | 53.9% [50.8; 57.0] | 34.4% [31.5; 37.4] | 4.5% [3.4; 6.0] | 0.0842 [0.0831; 0.0854] | 0.0269 [0.0268; 0.0271] | 0.0085 [0.0085; 0.0086] |
| bernoulli_p0.5 (20261015) | cs_prpl_eb | 1.9% [1.2; 2.9] | 1.9% [1.2; 2.9] | 1.9% [1.2; 2.9] | 1.9% [1.2; 2.9] | 0.3313 [0.3304; 0.3322] | 0.1222 [0.1220; 0.1225] | 0.0480 [0.0478; 0.0481] |
| bernoulli_p0.5 (20261015) | wald_peeking | 59.5% [56.4; 62.5] | 48.1% [45.0; 51.2] | 32.5% [29.7; 35.5] | 5.6% [4.3; 7.2] | 0.1984 [0.1983; 0.1985] | 0.0621 [0.0621; 0.0621] | 0.0196 [0.0196; 0.0196] |
| beta_media0.3 (20261017) | cs_prpl_eb | 0.8% [0.4; 1.6] | 0.8% [0.4; 1.6] | 0.8% [0.4; 1.6] | 0.8% [0.4; 1.6] | 0.1733 [0.1730; 0.1735] | 0.0402 [0.0401; 0.0403] | 0.0146 [0.0146; 0.0146] |
| beta_media0.3 (20261017) | wald_peeking | 62.9% [59.9; 65.8] | 50.8% [47.7; 53.9] | 33.2% [30.4; 36.2] | 4.9% [3.7; 6.4] | 0.0742 [0.0739; 0.0745] | 0.0232 [0.0232; 0.0232] | 0.0073 [0.0073; 0.0073] |

### 3b. Decisão 'μ > μ0' (μ0 = 0,05)

| cenário (seed) | método | decide em algum t ≤ T | decide olhando só em T | t mediano até decidir | erro uniforme |
|---|---|---|---|---|---|
| alternativa_p0.06_vs_mu0_0.05 (20261026) | cs_prpl_eb | 52.8% [49.7; 55.9] | 52.8% [49.7; 55.9] | 9.48e+03 | 1.8% [1.1; 2.8] |
| alternativa_p0.06_vs_mu0_0.05 (20261026) | wald_peeking | 99.7% [99.1; 99.9] | 99.2% [98.4; 99.6] | 1.28e+03 | 76.6% [73.9; 79.1] |
| alternativa_p0.075_vs_mu0_0.05 (20261027) | cs_prpl_eb | 100.0% [99.6; 100.0] | 100.0% [99.6; 100.0] | 1.47e+03 | 2.2% [1.5; 3.3] |
| alternativa_p0.075_vs_mu0_0.05 (20261027) | wald_peeking | 100.0% [99.6; 100.0] | 100.0% [99.6; 100.0] | 322 | 75.5% [72.7; 78.1] |
| nulo_p_igual_mu0 (20261025) | cs_prpl_eb | 0.2% [0.1; 0.7] | 0.2% [0.1; 0.7] | > 10000 | 1.9% [1.2; 2.9] |
| nulo_p_igual_mu0 (20261025) | wald_peeking | 16.4% [14.2; 18.8] | 2.4% [1.6; 3.5] | > 10000 | 80.1% [77.5; 82.5] |

### 3c. Contraprova: outcome ilimitado (receita/visitante) normalizado por um limite errado

Limite B = máximo de um piloto de 500 observações; X/B recortado em [0,1] (sem recorte a CS levanta `ForaDoSuporte`). A CS passa a cobrir E[min(X,B)]/B, não E[X]/B.

| cauda (seed) | % obs > B | erro uniforme CS recortada | erro uniforme Wald peeking (bruto) | erro Wald só em T (bruto) | sem recorte |
|---|---|---|---|---|---|
| lognormal_sigma1.5 (20261035) | 0.2% [0.2; 0.2] | 40.8% [37.8; 43.9] | 93.0% [91.2; 94.4] | 9.5% [7.8; 11.5] | `ForaDoSuporte` |
| pareto_alpha1.5_var_infinita (20261036) | 0.2% [0.2; 0.2] | 58.5% [55.4; 61.5] | 93.7% [92.0; 95.0] | 22.6% [20.1; 25.3] | `ForaDoSuporte` |

### 3d. Contraprova: outcome com atraso (conversão chega D ~ Geom(média 200 passos) depois; janela W=1000)

| p (seed) | estratégia | erro uniforme (vs p_W) | decide 'p_W > μ0' até T | t mediano de calendário até decidir |
|---|---|---|---|---|
| 0.05 (20261045) | oraculo | 1.6% [1.0; 2.6] | 0.1% [0.0; 0.6] | > 10000 |
| 0.05 (20261045) | janela_fechada | 1.6% [1.0; 2.6] | 0.1% [0.0; 0.6] | > 11000 |
| 0.05 (20261045) | lag_ingenuo | 100.0% [99.6; 100.0] | 0.0% [0.0; 0.4] | > 10050 |
| 0.075 (20261046) | oraculo | 2.1% [1.4; 3.2] | 100.0% [99.6; 100.0] | 1.46e+03 |
| 0.075 (20261046) | janela_fechada | 2.1% [1.4; 3.2] | 100.0% [99.6; 100.0] | 2.46e+03 |
| 0.075 (20261046) | lag_ingenuo | 100.0% [99.6; 100.0] | 0.0% [0.0; 0.4] | > 10050 |

## 4. FDR (500 réplicas por cenário; m=1000 células, CVR base 0.03, lift verdadeiro +30%, q=0.05)

BH própria vs `statsmodels.multipletests(fdr_bh)`: 3000 casos (seed 20261015), 0 divergências fora da fronteira, 1 em empate exato p = q·k/m (ponto flutuante; a regra BH rejeita, a implementação própria usa tolerância relativa 1e-12).

| cenário (seed) | olhadas | método | FDR realizado | poder | falsas descobertas/réplica | falsos vencedores/réplica | FWER |
|---|---|---|---|---|---|---|---|
| nulo_global_10_olhadas (20261515) | 10 | bh | 25.8% [22.0; 29.6] | — | 0.30 [0.25; 0.35] | 0.14 [0.10; 0.17] | 25.8% [22.2; 29.8] |
| nulo_global_10_olhadas (20261515) | 10 | bonferroni | 25.4% [21.6; 29.2] | — | 0.28 [0.24; 0.33] | 0.13 [0.10; 0.16] | 25.4% [21.8; 29.4] |
| nulo_global_10_olhadas (20261515) | 10 | nenhuma | 100.0% [100.0; 100.0] | — | 192.98 [191.90; 194.05] | 96.84 [96.06; 97.63] | 100.0% [99.2; 100.0] |
| nulo_global_uma_olhada (20261415) | 1 | bh | 5.0% [3.1; 6.9] | — | 0.05 [0.03; 0.08] | 0.03 [0.02; 0.04] | 5.0% [3.4; 7.3] |
| nulo_global_uma_olhada (20261415) | 1 | bonferroni | 5.0% [3.1; 6.9] | — | 0.05 [0.03; 0.07] | 0.03 [0.02; 0.04] | 5.0% [3.4; 7.3] |
| nulo_global_uma_olhada (20261415) | 1 | nenhuma | 100.0% [100.0; 100.0] | — | 50.01 [49.39; 50.64] | 25.28 [24.84; 25.73] | 100.0% [99.2; 100.0] |
| pi1_20pct_n20000_uma_olhada (20261615) | 1 | bh | 4.0% [3.8; 4.1] | 99.1% [99.1; 99.2] | 8.22 [7.96; 8.49] | 4.20 [4.01; 4.38] | 100.0% [99.2; 100.0] |
| pi1_20pct_n20000_uma_olhada (20261615) | 1 | bonferroni | 0.0% [0.0; 0.0] | 81.2% [80.9; 81.4] | 0.04 [0.02; 0.06] | 0.02 [9.13e-03; 0.03] | 3.6% [2.3; 5.6] |
| pi1_20pct_n20000_uma_olhada (20261615) | 1 | nenhuma | 16.5% [16.3; 16.8] | 99.9% [99.8; 99.9] | 39.58 [39.02; 40.14] | 20.13 [19.71; 20.54] | 100.0% [99.2; 100.0] |
| pi1_5pct_n5000_10_olhadas (20261215) | 10 | bh | 9.2% [8.2; 10.2] | 16.4% [15.7; 17.1] | 0.87 [0.78; 0.96] | 0.42 [0.36; 0.48] | 54.6% [50.2; 58.9] |
| pi1_5pct_n5000_10_olhadas (20261215) | 10 | bonferroni | 6.5% [5.2; 7.7] | 7.4% [7.1; 7.7] | 0.25 [0.21; 0.29] | 0.12 [0.09; 0.15] | 22.8% [19.3; 26.7] |
| pi1_5pct_n5000_10_olhadas (20261215) | 10 | nenhuma | 82.5% [82.2; 82.7] | 78.9% [78.4; 79.4] | 183.49 [182.42; 184.57] | 91.86 [91.04; 92.68] | 100.0% [99.2; 100.0] |
| pi1_5pct_n5000_50_olhadas (20261315) | 50 | bh | 13.8% [12.8; 14.9] | 18.8% [18.1; 19.5] | 1.55 [1.43; 1.68] | 0.82 [0.74; 0.90] | 74.8% [70.8; 78.4] |
| pi1_5pct_n5000_50_olhadas (20261315) | 50 | bonferroni | 10.9% [9.5; 12.3] | 8.9% [8.5; 9.2] | 0.52 [0.46; 0.59] | 0.27 [0.22; 0.31] | 41.8% [37.6; 46.2] |
| pi1_5pct_n5000_50_olhadas (20261315) | 50 | nenhuma | 87.9% [87.8; 88.1] | 84.3% [83.9; 84.8] | 303.96 [302.68; 305.23] | 152.12 [151.15; 153.09] | 100.0% [99.2; 100.0] |
| pi1_5pct_n5000_uma_olhada (20261115) | 1 | bh | 4.9% [4.0; 5.8] | 13.7% [13.0; 14.4] | 0.41 [0.35; 0.48] | 0.20 [0.16; 0.24] | 30.4% [26.5; 34.6] |
| pi1_5pct_n5000_uma_olhada (20261115) | 1 | bonferroni | 1.6% [0.8; 2.5] | 5.2% [4.9; 5.5] | 0.05 [0.03; 0.07] | 0.02 [6.52e-03; 0.03] | 4.0% [2.6; 6.1] |
| pi1_5pct_n5000_uma_olhada (20261115) | 1 | nenhuma | 57.8% [57.3; 58.3] | 69.6% [69.1; 70.2] | 47.49 [46.89; 48.10] | 23.52 [23.11; 23.94] | 100.0% [99.2; 100.0] |

## 5. Conclusões (rótulos: demonstrado em simulação / refutado / inadequado para outcome X / não testado)

Nada aqui é "validado": tudo é simulação com seed e distribuições escolhidas por nós.

### Maturação
- **demonstrado em simulação**: com atraso estável, o fator de coortes maduras é quase sem viés agregado (|viés| ≤ 1% fora da idade 0 em `receita_estavel`) e o erro cai com a idade (MAPE 70% → 39% → 22% → 11% → 5% → 1%).
- **demonstrado em simulação**: o guarda converte o trecho explosivo (m(0) ≈ 0,02–0,08; APE máx 5–17×) em `insuficiente` em vez de número; reporte D+1 → m(0) = 0 exato → sem guarda inf/NaN, com guarda 100% `insuficiente`.
- **demonstrado em simulação (resultado negativo)**: o guarda NÃO elimina o erro logo acima do limiar (MAPE ~34–39% em 1–2 dias) e induz viés de seleção quando m(a) estimado oscila em torno do limiar (D+1, idade 1–2: −11%; centavo, idade 0: −10%), porque só passam os mundos cujo fator saiu alto.
- **refutado**: bootstrap só do fator como intervalo preditivo — cobre ~15–30% para 90% nominal nas idades < 30 d (ignora o ruído de processo da parte ainda não reportada). O intervalo por razão empírica cobre ~80–95% (subcobertura leve, pior nas idades baixas) e é indefinido quando obs = 0 (contado, não imputado).
- **refutado sob mudança de regime** (método degrada e não avisa): atraso 2,5× mais lento nas 30 coortes recentes → viés −69% (1–2 d), −53% (3–6 d), −35% (7–13 d), −15% (14–29 d), cobertura IC90 29–45%; atraso 2× mais rápido → +70% (1–2 d), +35% (3–6 d), cobertura 42–49%. Link-ratio reage parcialmente (viés +13% vs +70% no regime rápido; −31% vs −53% no lento em 3–6 d), mas no regime lento o fator vai a ~0,02 na idade 0 (APE máx 14×) e o guarda bloqueia 1–2 d. Detecção de regime: não testada.
- **demonstrado em simulação**: granularidade de centavo (receita diária p5–p95 ≈ US$0,02–1,08, D-1 mudando até D+3; forma dos fatos reais, não parâmetro) não quebra o fator; o problema dominante é a idade 0 (obs = 0 frequente → intervalo indefinido; ~25% `insuficiente`; MAPE ~72%).

### Shrinkage
- **demonstrado em simulação**: Beta-Binomial EB (momentos ou MLE) reduz MSE para ~28% do cru, calibra (inclinação ≈ 1,0 vs 0,33 do cru) e reduz a fração do top-k com n baixo de ~57% para ~8%; mas vencedores por sorte caem só de 7,0 para 5,9 em 10: o ranking continua majoritariamente ruído com n mediano 50 e CVR 3%.
- **demonstrado em simulação (contraprovas)**: (a) vencedores reais raros (prior bimodal): EB sub-cobre justamente os melhores (cobertura top-10% verdadeiro ≈ 57% vs 92% do cru; no unimodal já é 68%); (b) n informativo (orçamento já seguiu a CVR): cobertura 79% (momentos) / 85% (MLE); (c) sem heterogeneidade: EB plug-in colapsa no pooling e sub-cobre (momentos 54%, MLE 85%; Gamma quase homogênea 67–69%) porque ignora a incerteza do hiperparâmetro — e a "calibração" fica indefinida (var(est) ≈ 0); (d) n grande: ganho ~1% (inofensivo).
- **inadequado para receita monetária**: Gamma-Poisson aplicado a dinheiro praticamente não encolhe (peso do prior ~0,0003–0,002 em R$; ~0,000002–0,00001 em centavos), o resultado depende da unidade monetária e a cobertura dos intervalos é 0,2–10%. A implementação recusa valor não inteiro (`ValueError`).
- **demonstrado em simulação**: hurdle (Beta-Binomial × valor lognormal EB) e normal-normal EB com variância empírica agrupada são invariantes a escala; hurdle: MSE 8–27% do cru, cobertura 88–89%, inclusive com valor Pareto(1,8) mal especificado. Normal-normal: **refutado** com cauda pesada (σ_log = 2): cobertura 44% e top-k pior que o cru (regret 0,61 vs 0,50).
- **não testado**: lucro (valores negativos), hiperprior hierárquico completo, intervalos EB com correção para incerteza do hiperparâmetro.

### Confidence sequences
- **demonstrado em simulação**: PrPl-EB mantém erro uniforme ≤ alpha (0,8–1,9% para alpha = 5%) olhando em todo t; Wald recalculado a cada passo erra em 59–79% das trajetórias (32–34% mesmo contando só t ≥ 1000), embora em uma olhada fixa em T cubra (erro 4,5–5,6%).
- **demonstrado em simulação (custo)**: a CS é ~2× mais larga que Wald em T e tem muito menos poder: p = 0,06 vs μ0 = 0,05 com T = 10.000 → CS decide em 53%, Wald de horizonte fixo (válido, uma olhada) em 99%. Sob H0, Wald-peeking "decide" em 16% (vs 2,4% numa olhada). A CS paga a validade com tempo/amostra.
- **inadequado para outcome monetário ilimitado**: normalizar por limite estimado (máximo de piloto de 500) e recortar quebra a cobertura (erro 41% lognormal; 58% Pareto α = 1,5) apesar de só ~0,2% das observações passarem do limite; sem recorte a CS recusa a entrada (`ForaDoSuporte`). Wald também falha (93–94% com peeking; 10–23% numa olhada só).
- **demonstrado em simulação**: atraso de outcome tratado como 0 (lag fixo de 50) → erro 100% (estima p·P(D ≤ L)); esperar a janela fechar (W = 1000) preserva a validade e só atrasa a decisão em W no calendário (mediana 1.463 → 2.463 para p = 0,075).
- **não testado**: CS para diferença entre braços (A/B), versão betting/hedged (mais estreita), CS com atraso sem esperar a janela; comparação numérica com a lib `confseq` (não instalável).

### FDR
- **demonstrado em simulação**: BH numa olhada controla FDR (4,9% para q = 5%; 4,0% com 20% de células verdadeiras); sem correção, FDR 58% e ~24 falsos vencedores por rodada em 1000 células; Bonferroni controla FWER (4%) com poder ~1/3 do BH.
- **demonstrado em simulação**: peeking com BH a cada olhada infla o FDR (10 olhadas ≈ 9%; 50 olhadas ≈ 14%); sob nulo global, BH com 10 olhadas declara algo em ~26% das rodadas (vs 5%). Bonferroni também infla (6,5% / 11%).
- **demonstrado em simulação (limite de dados)**: CVR 3%, lift +30% e 5000 cliques/braço → poder do BH ~14%; o dado típico não sustenta "vencedor" por célula.
- **demonstrado**: BH própria = statsmodels exceto em empate exato p = q·k/m (ponto flutuante; 1 em 3000 casos com p arredondados).
- **não testado**: e-BH com e-valores das CS (válido sob peeking), dependência entre células (mesmo dia/campanha), testes unilaterais.

## 6. Relação com a pesquisa sintética anterior (pesquisa-B, run google-engine-nucleo-20261014-01)

Lida em modo somente leitura (`RELATORIO-B.md`, `experimentos/e1_*`, `e2_*`).

- **Confirma**: Beta-Binomial EB > cru e > média do grupo; o "vencedor" do cru está inflado (B: viés top-5% +0,31..+0,51; aqui 6–7 de 10 do top-k cru são vencedores por sorte). Gamma-Poisson não serve para receita/lucro monetário (B17 refutado lá; aqui mostrado pela dependência da unidade e cobertura ~1–10%). Intervalo do chain-ladder sub-cobre levemente (B: 84–87% para 90%; aqui razão empírica 80–95%). Drift de reporte degrada o fator de coortes maduras (B: −16%, cobertura 75% com drift mais brando; aqui −15% a −69% conforme a idade, cobertura 29–45% com atraso 2,5×).
- **Complementa/contradiz em parte**: B concluiu M ótimo = κ (EB acerta); aqui mostramos onde o EB plug-in FALHA mesmo acertando a média: sub-cobertura sem heterogeneidade, nos vencedores raros reais e com n informativo. B usou lognormal só nos positivos para lucro e refutou; aqui o hurdle (P(conv) × valor|conv) não sofre desse defeito para receita ≥ 0 e foi razoável inclusive com valor Pareto — mas lucro negativo não foi testado.
- **Novo**: guarda de maturação como `ResultadoInsuficiente` + D+1 com fator zero exato; refutação do bootstrap só do fator; link-ratio vs coortes maduras sob regime; cenário de centavo/D+3; cobertura uniforme de CS vs peeking; contraprovas de cauda pesada e atraso para CS; FDR com peeking; sonda confseq.
- **Não refeito**: BF (B mostrou BF ≥ CL; aqui não testado), OPE e bandits.

