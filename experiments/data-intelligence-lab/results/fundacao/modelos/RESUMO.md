# RESUMO — Model Lab (worker F) · gerado de `m*.json` por `scripts/fundacao_modelos_relatorio.py`

> Tudo é **simulação com seed** (teto: "testado com sintético"). IC95 por bootstrap de seeds entre colchetes.
> Hipóteses e critérios: `PRE-REGISTRO.md`. Itens pós-registro estão marcados.

## M1 — Maturação

### A. Receita JoinAds (`estavel`), MAPE do total diário por idade (dias)

| método | idade 0 | idade 1 | idade 2 |
|---|---|---|---|
| bornhuetter_ferguson | 6.3% [5.7%; 7.0%] | 2.0% [1.7%; 2.3%] | 0.6% [0.5%; 0.7%] |
| chain_ladder | 4.8% [4.4%; 5.1%] | 1.8% [1.5%; 2.3%] | 0.5% [0.5%; 0.6%] |
| fator_fixo | 4.9% [4.5%; 5.2%] | 1.8% [1.5%; 2.1%] | 0.5% [0.5%; 0.6%] |
| observado | 82.3% [82.2%; 82.4%] | 10.8% [10.6%; 10.9%] | 2.9% [2.8%; 2.9%] |

- H1a (BF − CL, MAPE idade 0): 1.47% [0.86%; 2.12%] → suportada: não
- Cobertura do IC80 do chain-ladder (razão empírica): idade 0: 75.2% [71.4%; 78.8%], idade 1: 69.8% [67.1%; 72.4%], idade 2: 71.4% [69.0%; 74.0%]

### B. Custo D0 intradiário (`custo_d0_multiversao`), wMAPE do final por hora da leitura

| hora | m(h) médio | chain-ladder intradiário | D0 como final |
|---|---|---|---|
| 10h | 0.330 | 10.2% [9.8%; 10.7%] | 66.9% [66.7%; 67.0%] |
| 12h | 0.371 | 9.4% [9.0%; 9.8%] | 62.7% [62.5%; 62.8%] |
| 14h | 0.431 | 8.2% [7.9%; 8.5%] | 56.7% [56.5%; 56.8%] |
| 16h | 0.507 | 7.1% [6.8%; 7.3%] | 49.0% [48.9%; 49.2%] |
| 18h | 0.596 | 6.1% [5.9%; 6.3%] | 40.2% [40.0%; 40.3%] |
| 20h | 0.697 | 5.0% [4.8%; 5.2%] | 30.1% [29.9%; 30.3%] |
| 22h | 0.816 | 3.8% [3.6%; 4.0%] | 18.2% [18.1%; 18.4%] |
| 8h | 0.296 | 11.2% [10.7%; 11.6%] | 70.2% [70.1%; 70.4%] |

- H1b razão wMAPE (CL/naive) até 18h: 0.151 [0.145; 0.156] → suportada: sim
- versões distintas de custo por campanha-dia (mediana): 17.1 [17.0; 17.2]

### C. Regime de maturação — monitor pré-registrado (k=0,5, escala MAD)

- C1 (Stat Lab herdado) calibração FA/mundo: h=6: 0.95, h=8: 0.92, h=10: 0.82, h=12: 0.68, h=15: 0.60, h=20: 0.52 → h=20, calibrou: não

| cenário C1 | detecção | viés 1–2 d CL | viés 1–2 d CL+monitor | insuf. 1–2 d CL+monitor | cobertura 3–6 d CL | cobertura 3–6 d CL+monitor |
|---|---|---|---|---|---|---|
| atraso_metade | 0.23 | 69.2% [61.0%; 76.8%] | 69.0% [59.5%; 77.7%] | 61.5% [57.5%; 66.0%] | 42.8% [37.5%; 47.8%] | 45.8% [40.3%; 51.9%] |
| atraso_x2_5 | 0.89 | -68.3% [-73.5%; -62.4%] | -72.2% [-92.6%; -49.2%] | 94.5% [91.5%; 97.5%] | 24.1% [20.1%; 28.6%] | 23.8% [13.1%; 36.3%] |
| receita_estavel | 0.42 | 2.0% [-5.9%; 10.4%] | 6.6% [-4.8%; 18.1%] | 70.5% [65.5%; 75.0%] | 86.2% [83.0%; 89.2%] | 86.4% [81.8%; 90.7%] |

- C2 (simulador, JoinAds troca de observador no dia 30): calibração h=4: 0.92, h=6: 0.92, h=8: 0.75, h=10: 0.58, h=12: 0.58, h=15: 0.42, h=20: 0.25 → h=20, calibrou: não; detecção em 15 dias: 1.00; atraso: 3.2 [2.5; 4.1] dias

| idade | viés CL | viés fator fixo | viés CL+monitor (publicados) | insuf. CL+monitor |
|---|---|---|---|---|
| 1 | -35.0% [-37.2%; -33.1%] | -41.9% [-44.2%; -39.8%] | -12.7% [-20.6%; -3.7%] | 57.8% [53.3%; 61.7%] |
| 2 | -22.4% [-22.8%; -21.9%] | -27.8% [-28.4%; -27.2%] | -5.7% [-9.5%; -1.9%] | 60.1% [56.0%; 63.7%] |
| 3 | -15.3% [-15.4%; -15.1%] | -19.6% [-19.8%; -19.4%] | -3.6% [-6.2%; -1.1%] | 59.6% [56.4%; 61.5%] |
| 4 | -10.0% [-10.2%; -9.8%] | -13.3% [-13.5%; -13.1%] | -1.9% [-3.8%; -0.3%] | 57.6% [56.2%; 58.3%] |
| 5 | -6.5% [-6.7%; -6.3%] | -9.0% [-9.2%; -8.8%] | -1.1% [-2.3%; -0.1%] | 54.5% [54.5%; 54.5%] |
| 6 | -0.7% [-0.9%; -0.4%] | -0.9% [-1.2%; -0.6%] | -0.4% [-0.8%; 0.0%] | 50.0% [50.0%; 50.0%] |

### C. Regime de maturação — monitor PÓS-REGISTRO exploratório (k=1, escala max(MAD, dp))

- C1 (Stat Lab herdado) calibração FA/mundo: h=8: 0.32, h=12: 0.15, h=16: 0.05, h=20: 0.00, h=25: 0.00, h=30: 0.00, h=40: 0.00, h=60: 0.00 → h=16, calibrou: sim

| cenário C1 | detecção | viés 1–2 d CL | viés 1–2 d CL+monitor | insuf. 1–2 d CL+monitor | cobertura 3–6 d CL | cobertura 3–6 d CL+monitor |
|---|---|---|---|---|---|---|
| atraso_metade | 0.03 | 69.2% [61.0%; 76.8%] | 67.7% [59.2%; 75.6%] | 50.5% [48.5%; 53.0%] | 42.8% [37.5%; 47.8%] | 43.3% [38.1%; 48.5%] |
| atraso_x2_5 | 0.47 | -68.3% [-73.5%; -62.4%] | -69.3% [-76.6%; -61.0%] | 73.0% [68.0%; 78.0%] | 24.1% [20.1%; 28.6%] | 26.5% [20.6%; 32.6%] |
| receita_estavel | 0.02 | 2.0% [-5.9%; 10.4%] | 2.3% [-5.9%; 11.1%] | 49.0% [46.5%; 51.5%] | 86.2% [83.0%; 89.2%] | 86.2% [82.9%; 89.3%] |

- C2 (simulador, JoinAds troca de observador no dia 30): calibração h=8: 0.25, h=12: 0.08, h=16: 0.00, h=20: 0.00, h=25: 0.00, h=30: 0.00, h=40: 0.00, h=60: 0.00 → h=16, calibrou: sim; detecção em 15 dias: 0.92; atraso: 4.6 [3.2; 6.3] dias

| idade | viés CL | viés fator fixo | viés CL+monitor (publicados) | insuf. CL+monitor |
|---|---|---|---|---|
| 1 | -35.0% [-37.2%; -33.1%] | -41.9% [-44.2%; -39.8%] | -19.7% [-28.6%; -9.9%] | 48.3% [38.9%; 56.1%] |
| 2 | -22.4% [-22.8%; -21.9%] | -27.8% [-28.4%; -27.2%] | -10.7% [-16.0%; -5.6%] | 49.4% [37.5%; 58.9%] |
| 3 | -15.3% [-15.4%; -15.1%] | -19.6% [-19.8%; -19.4%] | -7.1% [-11.0%; -3.5%] | 49.4% [37.2%; 58.3%] |
| 4 | -10.0% [-10.2%; -9.8%] | -13.3% [-13.5%; -13.1%] | -3.8% [-6.5%; -1.5%] | 48.6% [36.8%; 56.9%] |
| 5 | -6.5% [-6.7%; -6.3%] | -9.0% [-9.2%; -8.8%] | -2.4% [-4.2%; -0.8%] | 46.2% [34.8%; 54.5%] |
| 6 | -0.7% [-0.9%; -0.4%] | -0.9% [-1.2%; -0.6%] | -0.4% [-0.8%; 0.1%] | 42.5% [30.8%; 50.0%] |

## M2 — Empirical Bayes em campanha nova

| k (dias) | alvo | razão MSE EB/cru | vencedores por sorte cru | EB | EB − cru |
|---|---|---|---|---|---|
| 1 | ctr | 0.696 [0.579; 0.836] | 2.56 [2.31; 2.81] | 2.69 [2.44; 2.88] | 0.12 [-0.12; 0.38] |
| 1 | rpm | insuficiente (variância intra-campanha não identificável com 1 dia) | — | — | — |
| 3 | ctr | 1.023 [1.000; 1.052] | 1.69 [1.19; 2.25] | 1.69 [1.19; 2.25] | 0.00 [0.00; 0.00] |
| 3 | rpm | 0.835 [0.734; 0.954] | 1.19 [0.81; 1.56] | 1.19 [0.81; 1.56] | 0.00 [0.00; 0.00] |
| 7 | ctr | 1.020 [1.008; 1.033] | 0.69 [0.44; 1.00] | 0.69 [0.44; 1.00] | 0.00 [0.00; 0.00] |
| 7 | rpm | 0.970 [0.894; 1.051] | 0.94 [0.62; 1.25] | 0.94 [0.62; 1.25] | 0.00 [0.00; 0.00] |

- viés relativo do CTR cru (k=1) contra os 14 dias seguintes: -19.3% [-22.9%; -15.5%]
- H2 critérios: {'mse_ctr_k1': True, 'mse_ctr_k3': False, 'mse_rpm_k3': True, 'sorte_ctr_k1': False} → suportada: não

## M3 — Detecção de mudança (log RPM maduro)

Limiares calibrados (FA alvo 0,02/campanha-semana): {'bocpd': 0.5, 'cusum': 15.0, 'media_movel': 2.25}

| método | poder (≤14 d) | alarmes falsos/semana (teste) | atraso mediano (dias) |
|---|---|---|---|
| bocpd | 0.81 [0.77; 0.85] | 0.017 [0.012; 0.022] | 4.2 [4.0; 4.3] |
| cusum | 0.93 [0.91; 0.96] | 0.015 [0.011; 0.021] | 6.6 [6.3; 6.9] |
| media_movel | 0.91 [0.88; 0.94] | 0.016 [0.010; 0.022] | 5.7 [5.5; 5.9] |

- CUSUM − média móvel (poder): 0.023 [0.005; 0.040]; BOCPD − média móvel: -0.100 [-0.142; -0.060] (CUSUM supera: sim; BOCPD supera: não) → H3 suportada: não

## M4 — Sequencial e FDR

μ0 (taxa de destino derivada do simulador) = 0.235

| regime | FDR BH | poder BH | FDR e-BH | poder e-BH |
|---|---|---|---|---|
| uma_olhada | 0.073 ± 0.004 | 1.000 | 0.002 ± 0.001 | 0.994 |
| olhadas_10 | 0.215 ± 0.005 | 1.000 | 0.005 ± 0.001 | 0.995 |
| olhadas_50 | 0.277 ± 0.005 | 1.000 | 0.009 ± 0.001 | 0.996 |

Descritivo adicional (efeito fraco, lift 1,10; não é hipótese pré-registrada):

| regime | FDR BH | poder BH | FDR e-BH | poder e-BH |
|---|---|---|---|---|
| uma_olhada | 0.077 ± 0.008 | 0.551 | 0.000 ± 0.000 | 0.062 |
| olhadas_10 | 0.159 ± 0.009 | 0.620 | 0.005 ± 0.005 | 0.075 |
| olhadas_50 | 0.209 ± 0.009 | 0.657 | 0.005 ± 0.005 | 0.094 |

- CS PrPl-EB na taxa de destino: erro uniforme 0.004 [0.001; 0.025] (α = 0.05, 225 trajetórias)
- receita/sessão normalizada por limite da janela inicial: recusa (`ForaDoSuporte`) em 0.702 [0.639; 0.758]; recortada: erro uniforme 0.013 [0.005; 0.038]
- H4a (e-BH controla): sim; BH infla com peeking: sim; H4b: sim

## M5 — Causal (`mudanca_orcamento`)

### H5a: dobra aleatória do cenário

| desfecho | ATT verdadeiro (R$/camp-dia) | viés antes/depois | viés corte transversal | viés DiD | viés controle sintético | IC DiD cobre verdade | tendências paralelas passou | placebo passou |
|---|---|---|---|---|---|---|---|---|
| custo | 8.91 [7.36; 10.56] | 3.80 [2.56; 5.10] | -3.11 [-9.08; 3.34] | -0.13 [-2.10; 1.80] | 2.31 [0.72; 3.85] | 1.00 | 0.75 | 0.70 |
| lucro | -1.91 [-2.66; -1.21] | -0.72 [-1.29; -0.18] | 0.35 [-2.03; 2.68] | -0.67 [-1.37; -0.02] | -0.72 [-1.35; -0.10] | 0.95 | 1.00 | 0.90 |
| receita | 7.01 [5.86; 8.22] | 3.08 [1.99; 4.19] | -2.77 [-8.91; 3.87] | -0.80 [-2.89; 1.10] | 1.35 [-0.08; 2.77] | 0.90 | 0.90 | 0.90 |

### H5b: dobra para o top 30% de ROAS recente

| desfecho | ATT verdadeiro (R$/camp-dia) | viés antes/depois | viés corte transversal | viés DiD | viés controle sintético | IC DiD cobre verdade | tendências paralelas passou | placebo passou |
|---|---|---|---|---|---|---|---|---|
| custo | 6.55 [5.35; 7.80] | 0.88 [0.37; 1.52] | -14.29 [-18.73; -10.13] | -3.99 [-5.27; -2.75] | -0.26 [-0.93; 0.39] | 0.85 | 0.70 | 0.85 |
| lucro | 1.15 [0.66; 1.76] | 0.42 [-0.20; 1.34] | 15.65 [12.91; 18.83] | 0.78 [0.01; 1.69] | 0.49 [-0.43; 1.58] | 1.00 | 0.80 | 0.85 |
| receita | 7.71 [6.20; 9.42] | 1.30 [0.25; 2.77] | 1.36 [-4.53; 7.57] | -3.21 [-4.71; -1.55] | -0.72 [-1.73; 0.41] | 0.85 | 0.95 | 0.95 |

- |viés antes/depois| − |viés DiD| no lucro (H5b, cond. 2): -0.38 [-0.71; -0.09]
- H5b critérios: {'antes_depois_mais_enviesado_que_did': False, 'did_lucro_enviesado_ic_exclui_0': True}
- H5a: não; H5b: não

## M6 — Surrogate (portão herdado reaberto com o simulador)

| caso | veredito | cobertura da feature de sessão no grão campanha |
|---|---|---|
| estavel_50x100 | viavel_para_teste | 0.985 |
| estavel_50x30 | dados_insuficientes | 0.975 |
| estavel_50x90 | dados_insuficientes | 0.989 |
| estavel_60x100 | viavel_para_teste | 0.985 |
| sensor_sem_campanha_60x100 | viavel_para_teste | 0.019 |

| cenário | skill fora do tempo (Ridge sessões+cliques vs média da campanha) | cobertura |
|---|---|---|
| estavel | 0.301 [0.285; 0.319] | 0.989 [0.984; 0.994] |
| sensor_sem_campanha | — | 0.018 [0.016; 0.019] |

## M7 — Bandits e OPE

### estavel

| política | pseudo-regret (escala do 1º dia) |
|---|---|
| eps_greedy_0.1 | 202.9 [163.7; 249.3] |
| equal | 687.0 [572.7; 806.2] |
| greedy | 237.1 [174.9; 310.8] |
| linucb | 134.0 [106.3; 162.9] |
| thompson | 218.2 [179.9; 267.2] |

- LinUCB − equal -553.1 [-663.3; -439.5]; LinUCB − greedy -103.1 [-168.2; -52.1]; Thompson − equal -468.8 [-573.2; -359.8]; Thompson − greedy -18.8 [-80.6; 47.0] → H7a: não
- OPE alvo `oraculo` (mundo 1, 200 logs): viés IPS 0.000 ± 0.006, SNIPS 0.004 (dp 0.083 vs IPS 0.088), DR -0.002 (dp 0.085), propensão inventada 2.134 ± 0.021
- OPE alvo `uniforme` (mundo 1, 200 logs): viés IPS 0.002 ± 0.002, SNIPS 0.002 (dp 0.024 vs IPS 0.023), DR 0.001 (dp 0.024), propensão inventada 0.403 ± 0.004

### quebra_regime_rpm

| política | pseudo-regret (escala do 1º dia) |
|---|---|
| eps_greedy_0.1 | 210.1 [164.3; 261.3] |
| equal | 631.3 [545.1; 716.7] |
| greedy | 184.9 [116.0; 263.6] |
| linucb | 136.6 [95.2; 186.0] |
| thompson | 240.6 [181.9; 311.7] |

- LinUCB − equal -494.7 [-608.2; -376.2]; LinUCB − greedy -48.3 [-104.7; 1.9]; Thompson − equal -390.7 [-510.5; -266.6]; Thompson − greedy 55.7 [6.4; 108.6] → H7a: não
- OPE alvo `oraculo` (mundo 1, 200 logs): viés IPS 0.001 ± 0.003, SNIPS -0.000 (dp 0.038 vs IPS 0.042), DR -0.002 (dp 0.039), propensão inventada 0.357 ± 0.009
- OPE alvo `uniforme` (mundo 1, 200 logs): viés IPS 0.004 ± 0.005, SNIPS 0.002 (dp 0.060 vs IPS 0.065), DR -0.005 (dp 0.058), propensão inventada 0.429 ± 0.002

- Sem propensão: recusado: log sem propensão: decisões sem probabilidade registrada não admitem OPE honesto
- H7b por alvo: {'oraculo': {'inventada_viesada_mundo1': True, 'ips_nao_viesado_mundo1': True, 'snips_dr_variancia_menor': True}, 'uniforme': {'inventada_viesada_mundo1': True, 'ips_nao_viesado_mundo1': True, 'snips_dr_variancia_menor': False}}
- H7b: não

## M8 — Conformal (90% nominal, lucro diário maduro)

| cenário | método | cobertura teste | cobertura campanhas quebradas pós-quebra | não quebradas | largura mediana (R$) |
|---|---|---|---|---|---|
| estavel | split | 0.895 [0.886; 0.903] | — | 0.895 [0.886; 0.903] | 14.6 [13.4; 16.0] |
| estavel | aci | 0.899 [0.895; 0.902] | — | 0.899 [0.895; 0.902] | 15.2 [13.8; 16.5] |
| quebra_regime_rpm | split | 0.877 [0.866; 0.887] | 0.866 [0.854; 0.877] | 0.905 [0.893; 0.915] | 14.2 [12.9; 15.6] |
| quebra_regime_rpm | aci | 0.901 [0.899; 0.904] | 0.892 [0.888; 0.897] | 0.930 [0.923; 0.936] | 14.5 [13.3; 15.7] |

- H8a: sim; H8b: não

## M9 — Anomalias

| detector (`outlier_bot`, razão cliques/sessões) | precisão | recall | F1 |
|---|---|---|---|
| robusto_mad | 0.66 [0.64; 0.69] | 0.24 [0.22; 0.25] | 0.35 [0.33; 0.36] |
| sazonal_robusto | 0.62 [0.57; 0.67] | 0.13 [0.12; 0.15] | 0.22 [0.20; 0.24] |
| zscore | 0.75 [0.72; 0.78] | 0.20 [0.18; 0.21] | 0.31 [0.30; 0.33] |

- dias com bot por mundo: 240.0; MAD − z (F1) 0.04 [0.02; 0.05]; sazonal − z -0.09 [-0.11; -0.08] → H9a: não
- `fonte_fora_do_ar`: {'alarmes_nulo_como_zero_em_lacuna': 382, 'alarmes_nulo_como_zero_por_janela': 31.8333, 'anomalias_de_valor_em_lacuna': 0, 'lacunas_classificadas': 2936, 'registros_unavailable_d1': 1824} → H9b: sim
- `zero_falso` (zero implausível): precisão 0.76 [0.72; 0.80], recall 0.87 [0.79; 0.93] → H9c: não

## M10 — Alocação de orçamento (regret em R$ nos 15 dias, contra oráculo de grade)

### mudanca_orcamento

curvas identificáveis: 0.86 [0.83; 0.89]; desvio de log gasto mediano: 0.168 [0.161; 0.177]; b mediano: 0.86 [0.83; 0.88]; fração de b no teto (0,95): 0.30 [0.25; 0.34]; violações de restrição: 0; histórico as_of: último dia maduro (mediana) 27.0, células maduras 0.86 [0.85; 0.87]

| política | regret |
|---|---|
| concava | 116 [84; 151] |
| concava_sem_aversao | 85 [62; 110] |
| equal | 1865 [1626; 2110] |
| greedy | 370 [261; 488] |
| proporcional_herdado | 1385 [1103; 1670] |
| status_quo | 2064 [1729; 2444] |

- côncava − equal: -1749 [-1968; -1529]; proporcional_herdado: -1270 [-1547; -1005]; greedy: -255 [-380; -136]; status_quo: -1948 [-2304; -1631]

### estavel

curvas identificáveis: 0.90 [0.88; 0.91]; desvio de log gasto mediano: 0.176 [0.170; 0.182]; b mediano: 0.91 [0.90; 0.93]; fração de b no teto (0,95): 0.40 [0.36; 0.44]; violações de restrição: 0; histórico as_of: último dia maduro (mediana) 27.0, células maduras 0.92 [0.92; 0.93]

| política | regret |
|---|---|
| concava | 92 [66; 118] |
| concava_sem_aversao | 86 [65; 108] |
| equal | 2141 [1829; 2472] |
| greedy | 310 [211; 423] |
| proporcional_herdado | 1656 [1377; 1962] |
| status_quo | 2291 [1978; 2605] |

- côncava − equal: -2049 [-2374; -1737]; proporcional_herdado: -1564 [-1882; -1276]; greedy: -218 [-336; -114]; status_quo: -2198 [-2515; -1886]

- H10a: sim; H10b (não supera equal sem variação): não

## M12 — Tabular (lucro final de amanhã, rolling origin)

| cenário | modelo | MAE (R$) | MAE relativo à média dos maduros |
|---|---|---|---|
| estavel | hgb | 4.31 [3.85; 4.77] | 1.027 [1.010; 1.043] |
| estavel | media_maduros | 4.20 [3.77; 4.65] | — |
| estavel | ridge | 4.22 [3.75; 4.71] | 1.006 [0.989; 1.022] |
| estavel | ridge_com_vazamento | 1.60 [1.27; 1.99] | — |
| estavel | ultimo_maduro | 5.50 [4.93; 6.08] | 1.310 [1.292; 1.330] |
| quebra_regime_rpm | hgb | 6.09 [5.34; 6.79] | 1.097 [1.047; 1.157] |
| quebra_regime_rpm | media_maduros | 5.56 [4.97; 6.08] | — |
| quebra_regime_rpm | ridge | 5.61 [4.93; 6.18] | 1.009 [0.978; 1.048] |
| quebra_regime_rpm | ridge_com_vazamento | 2.20 [1.81; 2.64] | — |
| quebra_regime_rpm | ultimo_maduro | 6.04 [5.40; 6.61] | 1.086 [1.070; 1.103] |
- estavel: vazamento detectado por metadado 1.00, empírico 1.00 (ganho de MAE com a feature do futuro 0.63 [0.57; 0.68]); alarme falso empírico no modelo honesto 0.00
- quebra_regime_rpm: vazamento detectado por metadado 1.00, empírico 1.00 (ganho de MAE com a feature do futuro 0.61 [0.56; 0.65]); alarme falso empírico no modelo honesto 0.00
- H12: sim

## Errata 2026-10-16 (revisão adversarial R2) — resultado antigo preservado em `errata_20261016/`

| achado | o que estava errado | antes | depois |
|---|---|---|---|
| G9 (M5/H5b) | o script testava só a condição 1 do pré-registro (DiD enviesado); faltava a condição 2 (antes/depois mais enviesado que o DiD) | H5b suportada: sim | H5b suportada: não (critérios {'antes_depois_mais_enviesado_que_did': False, 'did_lucro_enviesado_ic_exclui_0': True}) |
| G10 (M10) | histórico de decisão era a verdade diária do mundo, inclusive dias imaturos | `mudanca_orcamento`: regret côncava 120 [84; 158], equal 1865 [1626; 2110]; H10a sim, H10b não | painel as_of maduro: regret côncava 116 [84; 151], equal 1865 [1626; 2110]; H10a sim, H10b não |
| G13-F4 | `TabelaVersoes` ordenada pela chegada (regra pré-D1) sobrevivia aos testes de comportamento | — | testes `test_preliminar_atrasada_nao_substitui_a_final_r2_g13_f4` e `test_equivalencia_com_coletas_atrasadas_e_recuperacao_tardia` matam o mutante |

