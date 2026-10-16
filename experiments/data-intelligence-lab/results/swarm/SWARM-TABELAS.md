# Swarm Lab — tabelas GERADAS de results/swarm/*.json (não editar à mão)

Gerado por `scripts/swarm_tabelas.py tudo`. Regret em R$ (soma de 30 ciclos), média [IC95 de Monte Carlo], n=200 seeds.

## fatos


### Fatos extraídos dos JSON (gerados, não digitados)

- veredito pré-registrado: **nao**; cenários em que supera: {'asha_madura': [], 'asha_parcial': [], 'sh_madura': [], 'sh_parcial': []}
- PÓS-REGISTRO: o oráculo NÃO supera pelo critério pré-registrado em 8/12 cenários: ['base', 'sem_atraso', 'atraso_6', 'vencedoras_lentas_D3', 'vencedoras_lentas_D6', 'maturacao_por_canal_D3', 'ruido_baixo', 'interferencia']
- PÓS-REGISTRO: com a métrica excesso vs oráculo, cenários em que supera: {'asha_madura': [], 'asha_parcial': [], 'sh_madura': [], 'sh_parcial': []}
- política não-oráculo de menor regret médio por cenário: {'adverso': 'thompson_parcial', 'atraso_6': 'thompson_parcial', 'base': 'thompson_parcial', 'ideal_sem_saturacao': 'thompson_madura', 'interferencia': 'thompson_parcial', 'maturacao_por_canal_D3': 'thompson_parcial', 'nao_estacionario': 'thompson_parcial', 'ruido_alto': 'thompson_parcial', 'ruido_baixo': 'thompson_parcial', 'sem_atraso': 'thompson_madura', 'vencedoras_lentas_D3': 'thompson_parcial', 'vencedoras_lentas_D6': 'thompson_parcial'}
- degraus__base: melhor sh = sh_e2_r120brl_gasto_parcial 8997 [8327; 9667]; greedy_parcial 7556 [6887; 8226]
- degraus__base: melhor asha = asha_e3_r20_cliques_parcial 9013 [8333; 9693]; greedy_parcial 7556 [6887; 8226]
  - variantes com Δ pareado < 0 vs melhor baseline: 0 de 28
  - variantes que superam (pré-reg.): nenhuma
- degraus__ideal_sem_saturacao: melhor sh = sh_e3_r20_cliques_madura 34332 [30114; 38549]; greedy_parcial 36360 [31976; 40745]
- degraus__ideal_sem_saturacao: melhor asha = asha_e3_r20_cliques_madura 34732 [30453; 39011]; greedy_parcial 36360 [31976; 40745]
  - variantes com Δ pareado < 0 vs melhor baseline: 16 de 28
  - variantes que superam (pré-reg.): nenhuma
- degraus__vencedoras_lentas_D3: melhor sh = sh_e3_r150_cliques_parcial 9976 [9192; 10760]; greedy_parcial 7630 [6963; 8297]
- degraus__vencedoras_lentas_D3: melhor asha = asha_e2_r120brl_gasto_madura 10029 [9309; 10749]; greedy_parcial 7630 [6963; 8297]
  - variantes com Δ pareado < 0 vs melhor baseline: 0 de 28
  - variantes que superam (pré-reg.): nenhuma

## principal

veredito (regra pré-registrada): nao
cenários em que supera: {'asha_madura': [], 'asha_parcial': [], 'sh_madura': [], 'sh_parcial': []}


#### adverso

| política | regret R$ [IC95] | orç. em perdedoras (fim) | excesso vs oráculo (fim, pós-reg.) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |
|---|---|---|---|---|---|---|---|---|
| oraculo | 0 [0; 0] | 0.228 [0.188; 0.267] | 0.000 [0.000; 0.000] | 2068 [1663; 2474] | 0.14 [0.08; 0.20] | 0.34 [0.31; 0.37] | 0.28 | 0.008 |
| equal | 17410 [15645; 19175] | 0.705 [0.687; 0.722] | 0.606 [0.595; 0.618] | 8678 [8088; 9269] | 0.00 [0.00; 0.00] | 0.78 [0.77; 0.79] | 0.06 | 0.000 |
| random_sh | 21024 [19074; 22973] | 0.696 [0.665; 0.727] | 0.642 [0.613; 0.671] | 12427 [11712; 13142] | 2.59 [2.46; 2.72] | 0.77 [0.74; 0.79] | 0.22 | 0.034 |
| greedy_parcial | 11617 [10425; 12810] | 0.319 [0.279; 0.359] | 0.214 [0.188; 0.240] | 5684 [5042; 6326] | 1.11 [1.02; 1.20] | 0.46 [0.43; 0.50] | 0.18 | 0.074 |
| greedy_madura | 13390 [12023; 14757] | 0.332 [0.292; 0.372] | 0.227 [0.200; 0.253] | 6543 [5918; 7168] | 1.14 [1.04; 1.24] | 0.47 [0.44; 0.51] | 0.17 | 0.061 |
| sh_parcial | 14944 [13628; 16260] | 0.583 [0.549; 0.616] | 0.493 [0.466; 0.520] | 7950 [7189; 8710] | 2.04 [1.93; 2.16] | 0.63 [0.60; 0.66] | 0.22 | 0.034 |
| sh_madura | 15337 [13827; 16847] | 0.386 [0.345; 0.427] | 0.297 [0.266; 0.327] | 7648 [6974; 8321] | 1.56 [1.46; 1.66] | 0.51 [0.48; 0.54] | 0.18 | 0.034 |
| asha_parcial | 16161 [14710; 17612] | 0.627 [0.591; 0.664] | 0.528 [0.498; 0.559] | 8684 [7918; 9450] | 2.27 [2.14; 2.39] | 0.69 [0.66; 0.72] | 0.22 | 0.058 |
| asha_madura | 16376 [14879; 17872] | 0.398 [0.356; 0.439] | 0.312 [0.281; 0.343] | 8867 [8217; 9518] | 1.57 [1.47; 1.68] | 0.51 [0.48; 0.55] | 0.26 | 0.266 |
| thompson_parcial | 9511 [8626; 10395] | 0.321 [0.286; 0.356] | 0.203 [0.185; 0.220] | 5130 [4526; 5734] | 0.09 [0.05; 0.13] | 0.36 [0.33; 0.40] | 0.14 | 0.137 |
| thompson_madura | 12068 [10863; 13273] | 0.350 [0.314; 0.387] | 0.233 [0.212; 0.254] | 6030 [5430; 6629] | 0.34 [0.27; 0.42] | 0.44 [0.40; 0.47] | 0.14 | 0.111 |

critério: asha_madura: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 4758 [4243; 5274]); asha_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 4544 [3916; 5171]); sh_madura: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 3719 [3236; 4203]); sh_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 3327 [2838; 3815])

asha_parcial_menos_asha_madura: Δregret -215 [-865; 435]; Δpodadas 0.69 [0.58; 0.80]

greedy_parcial_menos_greedy_madura: Δregret -1773 [-2067; -1479]; Δpodadas -0.03 [-0.10; 0.04]

sh_parcial_menos_sh_madura: Δregret -393 [-975; 190]; Δpodadas 0.48 [0.38; 0.59]

thompson_parcial_menos_thompson_madura: Δregret -2557 [-2964; -2150]; Δpodadas -0.26 [-0.32; -0.19]

PÓS-REGISTRO — critério pré-registrado aplicado ao ORÁCULO: supera (vs greedy_parcial; perdedoras ok, drawdown ok)
PÓS-REGISTRO — critério com excesso vs oráculo: asha_madura: não (regret x, excesso x, drawdown x); asha_parcial: não (regret x, excesso x, drawdown x); sh_madura: não (regret x, excesso x, drawdown x); sh_parcial: não (regret x, excesso x, drawdown x)

#### atraso_6

| política | regret R$ [IC95] | orç. em perdedoras (fim) | excesso vs oráculo (fim, pós-reg.) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |
|---|---|---|---|---|---|---|---|---|
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 0.000 [0.000; 0.000] | 513 [325; 700] | 0.24 [0.15; 0.33] | 0.35 [0.32; 0.39] | 0.30 | 0.000 |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 0.632 [0.619; 0.644] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] | 0.80 [0.79; 0.80] | 0.06 | 0.000 |
| random_sh | 23583 [21681; 25484] | 0.746 [0.717; 0.776] | 0.682 [0.655; 0.710] | 9977 [9237; 10717] | 2.47 [2.33; 2.61] | 0.80 [0.77; 0.82] | 0.22 | 0.034 |
| greedy_parcial | 7461 [6792; 8130] | 0.235 [0.200; 0.269] | 0.097 [0.080; 0.115] | 1717 [1362; 2073] | 0.12 [0.07; 0.17] | 0.33 [0.30; 0.37] | 0.18 | 0.073 |
| greedy_madura | 9876 [9073; 10678] | 0.258 [0.224; 0.293] | 0.131 [0.112; 0.150] | 2426 [2018; 2833] | 0.35 [0.28; 0.42] | 0.36 [0.32; 0.39] | 0.17 | 0.052 |
| sh_parcial | 9036 [8364; 9708] | 0.250 [0.215; 0.285] | 0.163 [0.139; 0.187] | 2359 [1890; 2828] | 0.49 [0.41; 0.57] | 0.30 [0.27; 0.34] | 0.22 | 0.034 |
| sh_madura | 11449 [10538; 12360] | 0.249 [0.213; 0.285] | 0.160 [0.135; 0.185] | 2886 [2433; 3338] | 0.51 [0.43; 0.59] | 0.31 [0.28; 0.34] | 0.18 | 0.034 |
| asha_parcial | 10003 [9111; 10895] | 0.281 [0.244; 0.318] | 0.178 [0.152; 0.205] | 2593 [2124; 3063] | 0.62 [0.53; 0.72] | 0.34 [0.30; 0.37] | 0.22 | 0.058 |
| asha_madura | 13818 [12810; 14826] | 0.284 [0.247; 0.320] | 0.182 [0.157; 0.206] | 4343 [3856; 4830] | 0.64 [0.54; 0.73] | 0.34 [0.31; 0.37] | 0.26 | 0.267 |
| thompson_parcial | 6086 [5531; 6642] | 0.262 [0.230; 0.295] | 0.121 [0.106; 0.136] | 1346 [1018; 1674] | 0.01 [-0.00; 0.01] | 0.32 [0.29; 0.35] | 0.17 | 0.121 |
| thompson_madura | 8777 [8047; 9507] | 0.279 [0.246; 0.312] | 0.135 [0.118; 0.151] | 2164 [1799; 2530] | 0.07 [0.03; 0.11] | 0.36 [0.33; 0.39] | 0.16 | 0.087 |

critério: asha_madura: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 6357 [5868; 6847]); asha_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 2542 [2102; 2983]); sh_madura: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 3988 [3671; 4305]); sh_parcial: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 1575 [1391; 1759])

asha_parcial_menos_asha_madura: Δregret -3815 [-4318; -3312]; Δpodadas -0.01 [-0.10; 0.08]

greedy_parcial_menos_greedy_madura: Δregret -2414 [-2598; -2231]; Δpodadas -0.23 [-0.30; -0.16]

sh_parcial_menos_sh_madura: Δregret -2413 [-2788; -2038]; Δpodadas -0.02 [-0.08; 0.04]

thompson_parcial_menos_thompson_madura: Δregret -2690 [-2934; -2447]; Δpodadas -0.07 [-0.10; -0.03]

PÓS-REGISTRO — critério pré-registrado aplicado ao ORÁCULO: NÃO supera (vs greedy_parcial; perdedoras x, drawdown ok)
PÓS-REGISTRO — critério com excesso vs oráculo: asha_madura: não (regret x, excesso x, drawdown x); asha_parcial: não (regret x, excesso x, drawdown x); sh_madura: não (regret x, excesso x, drawdown x); sh_parcial: não (regret x, excesso x, drawdown x)

#### base

| política | regret R$ [IC95] | orç. em perdedoras (fim) | excesso vs oráculo (fim, pós-reg.) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |
|---|---|---|---|---|---|---|---|---|
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 0.000 [0.000; 0.000] | 513 [325; 700] | 0.24 [0.15; 0.33] | 0.35 [0.32; 0.39] | 0.30 | 0.000 |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 0.632 [0.619; 0.644] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] | 0.80 [0.79; 0.80] | 0.06 | 0.000 |
| random_sh | 23583 [21681; 25484] | 0.746 [0.717; 0.776] | 0.682 [0.655; 0.710] | 9977 [9237; 10717] | 2.47 [2.33; 2.61] | 0.80 [0.77; 0.82] | 0.22 | 0.034 |
| greedy_parcial | 7556 [6887; 8226] | 0.235 [0.200; 0.270] | 0.101 [0.083; 0.120] | 1760 [1395; 2124] | 0.15 [0.10; 0.21] | 0.33 [0.29; 0.36] | 0.19 | 0.068 |
| greedy_madura | 8498 [7796; 9199] | 0.250 [0.214; 0.285] | 0.127 [0.107; 0.146] | 2051 [1659; 2443] | 0.33 [0.25; 0.40] | 0.33 [0.30; 0.37] | 0.19 | 0.057 |
| sh_parcial | 9123 [8458; 9788] | 0.250 [0.214; 0.286] | 0.161 [0.137; 0.184] | 2410 [1937; 2883] | 0.49 [0.41; 0.58] | 0.30 [0.27; 0.34] | 0.22 | 0.034 |
| sh_madura | 10213 [9411; 11016] | 0.240 [0.204; 0.276] | 0.149 [0.125; 0.173] | 2545 [2100; 2989] | 0.46 [0.37; 0.54] | 0.29 [0.26; 0.33] | 0.20 | 0.034 |
| asha_parcial | 10164 [9273; 11056] | 0.287 [0.251; 0.324] | 0.186 [0.159; 0.213] | 2635 [2166; 3104] | 0.69 [0.59; 0.79] | 0.35 [0.32; 0.39] | 0.22 | 0.058 |
| asha_madura | 12090 [11137; 13043] | 0.291 [0.254; 0.328] | 0.180 [0.154; 0.205] | 3806 [3338; 4273] | 0.69 [0.59; 0.79] | 0.35 [0.32; 0.39] | 0.27 | 0.255 |
| thompson_parcial | 6072 [5520; 6624] | 0.256 [0.224; 0.289] | 0.114 [0.099; 0.129] | 1345 [1018; 1672] | 0.01 [-0.00; 0.02] | 0.32 [0.29; 0.36] | 0.17 | 0.118 |
| thompson_madura | 7311 [6682; 7940] | 0.257 [0.224; 0.290] | 0.115 [0.100; 0.131] | 1764 [1421; 2107] | 0.04 [0.01; 0.07] | 0.33 [0.30; 0.37] | 0.17 | 0.098 |

critério: asha_madura: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 4534 [4150; 4917]); asha_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 2608 [2160; 3056]); sh_madura: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 2657 [2454; 2861]); sh_parcial: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 1567 [1382; 1752])

asha_parcial_menos_asha_madura: Δregret -1925 [-2381; -1469]; Δpodadas 0.00 [-0.10; 0.10]

greedy_parcial_menos_greedy_madura: Δregret -941 [-1018; -865]; Δpodadas -0.17 [-0.24; -0.10]

sh_parcial_menos_sh_madura: Δregret -1090 [-1345; -836]; Δpodadas 0.04 [-0.02; 0.10]

thompson_parcial_menos_thompson_madura: Δregret -1239 [-1360; -1119]; Δpodadas -0.03 [-0.06; -0.00]

PÓS-REGISTRO — critério pré-registrado aplicado ao ORÁCULO: NÃO supera (vs greedy_parcial; perdedoras x, drawdown ok)
PÓS-REGISTRO — critério com excesso vs oráculo: asha_madura: não (regret x, excesso x, drawdown x); asha_parcial: não (regret x, excesso x, drawdown x); sh_madura: não (regret x, excesso x, drawdown x); sh_parcial: não (regret x, excesso x, drawdown x)

#### ideal_sem_saturacao

| política | regret R$ [IC95] | orç. em perdedoras (fim) | excesso vs oráculo (fim, pós-reg.) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |
|---|---|---|---|---|---|---|---|---|
| oraculo | 0 [0; 0] | 0.015 [-0.002; 0.032] | 0.000 [0.000; 0.000] | 44 [-4; 92] | 2.29 [2.16; 2.42] | 0.01 [-0.00; 0.03] | 1.00 | 0.000 |
| equal | 56051 [50384; 61718] | 0.751 [0.735; 0.766] | 0.750 [0.734; 0.765] | 4524 [3996; 5052] | 0.00 [0.00; 0.00] | 0.80 [0.79; 0.80] | 0.06 | 0.000 |
| random_sh | 55777 [50010; 61545] | 0.746 [0.717; 0.776] | 0.746 [0.717; 0.776] | 5716 [5070; 6362] | 2.47 [2.33; 2.61] | 0.80 [0.77; 0.82] | 0.22 | 0.034 |
| greedy_parcial | 36360 [31976; 40745] | 0.189 [0.155; 0.224] | 0.186 [0.152; 0.219] | 705 [565; 846] | 0.14 [0.10; 0.19] | 0.23 [0.19; 0.26] | 0.21 | 0.034 |
| greedy_madura | 36360 [31976; 40745] | 0.189 [0.155; 0.224] | 0.186 [0.152; 0.219] | 705 [565; 846] | 0.14 [0.10; 0.19] | 0.23 [0.19; 0.26] | 0.21 | 0.034 |
| sh_parcial | 35821 [31469; 40174] | 0.199 [0.164; 0.234] | 0.195 [0.161; 0.229] | 663 [526; 801] | 0.23 [0.17; 0.29] | 0.24 [0.21; 0.27] | 0.22 | 0.034 |
| sh_madura | 35821 [31469; 40174] | 0.199 [0.164; 0.234] | 0.195 [0.161; 0.229] | 663 [526; 801] | 0.23 [0.17; 0.29] | 0.24 [0.21; 0.27] | 0.22 | 0.034 |
| asha_parcial | 37696 [33106; 42286] | 0.217 [0.183; 0.252] | 0.214 [0.180; 0.247] | 714 [566; 861] | 0.34 [0.27; 0.42] | 0.27 [0.24; 0.30] | 0.22 | 0.059 |
| asha_madura | 37696 [33106; 42286] | 0.217 [0.183; 0.252] | 0.214 [0.180; 0.247] | 714 [566; 861] | 0.34 [0.27; 0.42] | 0.27 [0.24; 0.30] | 0.22 | 0.059 |
| thompson_parcial | 33106 [28950; 37263] | 0.183 [0.150; 0.217] | 0.180 [0.148; 0.211] | 320 [205; 435] | 0.03 [0.00; 0.05] | 0.24 [0.20; 0.27] | 0.22 | 0.072 |
| thompson_madura | 33106 [28950; 37263] | 0.183 [0.150; 0.217] | 0.180 [0.148; 0.211] | 320 [205; 435] | 0.03 [0.00; 0.05] | 0.24 [0.20; 0.27] | 0.22 | 0.072 |

critério: asha_madura: não (vs greedy_parcial; regret x, perdedoras ok, drawdown ok; Δpareado 1336 [773; 1898]); asha_parcial: não (vs greedy_parcial; regret x, perdedoras ok, drawdown ok; Δpareado 1336 [773; 1898]); sh_madura: não (vs greedy_parcial; regret x, perdedoras ok, drawdown ok; Δpareado -539 [-611; -467]); sh_parcial: não (vs greedy_parcial; regret x, perdedoras ok, drawdown ok; Δpareado -539 [-611; -467])

asha_parcial_menos_asha_madura: Δregret 0 [0; 0]; Δpodadas 0.00 [0.00; 0.00]

greedy_parcial_menos_greedy_madura: Δregret 0 [0; 0]; Δpodadas 0.00 [0.00; 0.00]

sh_parcial_menos_sh_madura: Δregret 0 [0; 0]; Δpodadas 0.00 [0.00; 0.00]

thompson_parcial_menos_thompson_madura: Δregret 0 [0; 0]; Δpodadas 0.00 [0.00; 0.00]

PÓS-REGISTRO — critério pré-registrado aplicado ao ORÁCULO: supera (vs greedy_parcial; perdedoras ok, drawdown ok)
PÓS-REGISTRO — critério com excesso vs oráculo: asha_madura: não (regret x, excesso ok, drawdown ok); asha_parcial: não (regret x, excesso ok, drawdown ok); sh_madura: não (regret x, excesso ok, drawdown ok); sh_parcial: não (regret x, excesso ok, drawdown ok)

#### interferencia

| política | regret R$ [IC95] | orç. em perdedoras (fim) | excesso vs oráculo (fim, pós-reg.) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |
|---|---|---|---|---|---|---|---|---|
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 0.000 [0.000; 0.000] | 1963 [1532; 2394] | 0.24 [0.15; 0.33] | 0.35 [0.32; 0.39] | 0.30 | 0.000 |
| equal | 17045 [15260; 18829] | 0.751 [0.735; 0.766] | 0.632 [0.619; 0.644] | 9224 [8662; 9787] | 0.00 [0.00; 0.00] | 0.80 [0.79; 0.80] | 0.06 | 0.000 |
| random_sh | 20519 [18545; 22493] | 0.746 [0.717; 0.776] | 0.682 [0.655; 0.710] | 12931 [12200; 13663] | 2.47 [2.33; 2.61] | 0.80 [0.77; 0.82] | 0.22 | 0.034 |
| greedy_parcial | 7498 [6478; 8518] | 0.244 [0.209; 0.278] | 0.120 [0.100; 0.140] | 4092 [3538; 4646] | 0.23 [0.16; 0.29] | 0.33 [0.29; 0.36] | 0.19 | 0.064 |
| greedy_madura | 8221 [7182; 9261] | 0.253 [0.218; 0.289] | 0.135 [0.114; 0.155] | 4524 [3957; 5092] | 0.39 [0.31; 0.46] | 0.33 [0.30; 0.36] | 0.19 | 0.057 |
| sh_parcial | 8845 [7796; 9894] | 0.264 [0.228; 0.299] | 0.180 [0.155; 0.205] | 4880 [4228; 5531] | 0.55 [0.46; 0.64] | 0.32 [0.29; 0.35] | 0.22 | 0.034 |
| sh_madura | 10083 [8942; 11224] | 0.259 [0.222; 0.295] | 0.168 [0.143; 0.193] | 5528 [4898; 6157] | 0.55 [0.46; 0.63] | 0.32 [0.29; 0.35] | 0.20 | 0.034 |
| asha_parcial | 9469 [8352; 10586] | 0.286 [0.250; 0.323] | 0.192 [0.165; 0.218] | 5133 [4492; 5774] | 0.69 [0.60; 0.79] | 0.35 [0.32; 0.39] | 0.22 | 0.058 |
| asha_madura | 11138 [9882; 12394] | 0.305 [0.269; 0.341] | 0.196 [0.170; 0.222] | 6367 [5758; 6976] | 0.71 [0.61; 0.82] | 0.36 [0.33; 0.39] | 0.27 | 0.255 |
| thompson_parcial | 6196 [5276; 7116] | 0.262 [0.229; 0.294] | 0.127 [0.111; 0.142] | 3462 [2923; 4002] | 0.02 [0.00; 0.04] | 0.32 [0.29; 0.35] | 0.17 | 0.117 |
| thompson_madura | 7272 [6294; 8250] | 0.262 [0.229; 0.294] | 0.128 [0.112; 0.144] | 4094 [3557; 4632] | 0.03 [0.00; 0.05] | 0.32 [0.29; 0.36] | 0.17 | 0.100 |

critério: asha_madura: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 3640 [3264; 4017]); asha_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 1971 [1593; 2350]); sh_madura: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 2586 [2360; 2811]); sh_parcial: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 1347 [1126; 1568])

asha_parcial_menos_asha_madura: Δregret -1669 [-2133; -1205]; Δpodadas -0.02 [-0.12; 0.08]

greedy_parcial_menos_greedy_madura: Δregret -724 [-795; -652]; Δpodadas -0.16 [-0.22; -0.10]

sh_parcial_menos_sh_madura: Δregret -1238 [-1514; -963]; Δpodadas 0.01 [-0.06; 0.07]

thompson_parcial_menos_thompson_madura: Δregret -1076 [-1184; -969]; Δpodadas -0.01 [-0.03; 0.02]

PÓS-REGISTRO — critério pré-registrado aplicado ao ORÁCULO: NÃO supera (vs greedy_parcial; perdedoras x, drawdown ok)
PÓS-REGISTRO — critério com excesso vs oráculo: asha_madura: não (regret x, excesso x, drawdown x); asha_parcial: não (regret x, excesso x, drawdown x); sh_madura: não (regret x, excesso x, drawdown x); sh_parcial: não (regret x, excesso x, drawdown x)

#### maturacao_por_canal_D3

| política | regret R$ [IC95] | orç. em perdedoras (fim) | excesso vs oráculo (fim, pós-reg.) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |
|---|---|---|---|---|---|---|---|---|
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 0.000 [0.000; 0.000] | 513 [325; 700] | 0.24 [0.15; 0.33] | 0.35 [0.32; 0.39] | 0.30 | 0.000 |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 0.632 [0.619; 0.644] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] | 0.80 [0.79; 0.80] | 0.06 | 0.000 |
| random_sh | 23583 [21681; 25484] | 0.746 [0.717; 0.776] | 0.682 [0.655; 0.710] | 9977 [9237; 10717] | 2.47 [2.33; 2.61] | 0.80 [0.77; 0.82] | 0.22 | 0.034 |
| greedy_parcial | 7512 [6842; 8183] | 0.233 [0.198; 0.268] | 0.096 [0.078; 0.113] | 1728 [1371; 2084] | 0.12 [0.08; 0.17] | 0.34 [0.30; 0.37] | 0.18 | 0.073 |
| greedy_madura | 8498 [7796; 9199] | 0.250 [0.214; 0.285] | 0.127 [0.107; 0.146] | 2051 [1659; 2443] | 0.33 [0.25; 0.40] | 0.33 [0.30; 0.37] | 0.19 | 0.057 |
| sh_parcial | 9591 [8899; 10282] | 0.284 [0.248; 0.320] | 0.192 [0.167; 0.218] | 2592 [2094; 3090] | 0.64 [0.55; 0.73] | 0.34 [0.31; 0.37] | 0.22 | 0.034 |
| sh_madura | 10213 [9411; 11016] | 0.240 [0.204; 0.276] | 0.149 [0.125; 0.173] | 2545 [2100; 2989] | 0.46 [0.37; 0.54] | 0.29 [0.26; 0.33] | 0.20 | 0.034 |
| asha_parcial | 11367 [10499; 12236] | 0.354 [0.313; 0.394] | 0.244 [0.214; 0.274] | 3225 [2689; 3761] | 0.99 [0.88; 1.11] | 0.43 [0.40; 0.46] | 0.22 | 0.058 |
| asha_madura | 12090 [11137; 13043] | 0.291 [0.254; 0.328] | 0.180 [0.154; 0.205] | 3806 [3338; 4273] | 0.69 [0.59; 0.79] | 0.35 [0.32; 0.39] | 0.27 | 0.255 |
| thompson_parcial | 6477 [5888; 7065] | 0.263 [0.230; 0.295] | 0.119 [0.104; 0.135] | 1447 [1121; 1773] | 0.01 [-0.00; 0.01] | 0.32 [0.29; 0.36] | 0.16 | 0.121 |
| thompson_madura | 7311 [6682; 7940] | 0.257 [0.224; 0.290] | 0.115 [0.100; 0.131] | 1764 [1421; 2107] | 0.04 [0.01; 0.07] | 0.33 [0.30; 0.37] | 0.17 | 0.098 |

critério: asha_madura: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 4577 [4196; 4958]); asha_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 3855 [3388; 4322]); sh_madura: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 2701 [2494; 2908]); sh_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 2078 [1842; 2314])

asha_parcial_menos_asha_madura: Δregret -722 [-1260; -185]; Δpodadas 0.30 [0.19; 0.42]

greedy_parcial_menos_greedy_madura: Δregret -985 [-1059; -911]; Δpodadas -0.20 [-0.27; -0.13]

sh_parcial_menos_sh_madura: Δregret -623 [-920; -326]; Δpodadas 0.18 [0.10; 0.27]

thompson_parcial_menos_thompson_madura: Δregret -835 [-940; -729]; Δpodadas -0.04 [-0.06; -0.01]

PÓS-REGISTRO — critério pré-registrado aplicado ao ORÁCULO: NÃO supera (vs greedy_parcial; perdedoras x, drawdown ok)
PÓS-REGISTRO — critério com excesso vs oráculo: asha_madura: não (regret x, excesso x, drawdown x); asha_parcial: não (regret x, excesso x, drawdown x); sh_madura: não (regret x, excesso x, drawdown x); sh_parcial: não (regret x, excesso x, drawdown x)

#### nao_estacionario

| política | regret R$ [IC95] | orç. em perdedoras (fim) | excesso vs oráculo (fim, pós-reg.) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |
|---|---|---|---|---|---|---|---|---|
| oraculo | 0 [0; 0] | 0.228 [0.188; 0.267] | 0.000 [0.000; 0.000] | 493 [310; 677] | 0.14 [0.08; 0.20] | 0.34 [0.31; 0.37] | 0.28 | 0.008 |
| equal | 18930 [17214; 20646] | 0.705 [0.687; 0.722] | 0.606 [0.595; 0.618] | 4261 [3741; 4781] | 0.00 [0.00; 0.00] | 0.78 [0.77; 0.79] | 0.06 | 0.000 |
| random_sh | 24492 [22522; 26462] | 0.696 [0.665; 0.727] | 0.642 [0.613; 0.671] | 9454 [8753; 10155] | 2.59 [2.46; 2.72] | 0.77 [0.74; 0.79] | 0.22 | 0.034 |
| greedy_parcial | 11714 [10631; 12798] | 0.262 [0.222; 0.302] | 0.134 [0.113; 0.155] | 2152 [1741; 2564] | 0.94 [0.87; 1.00] | 0.44 [0.41; 0.47] | 0.19 | 0.067 |
| greedy_madura | 12579 [11483; 13676] | 0.275 [0.235; 0.314] | 0.156 [0.135; 0.178] | 2478 [2037; 2919] | 1.03 [0.95; 1.12] | 0.43 [0.40; 0.46] | 0.19 | 0.057 |
| sh_parcial | 13414 [12368; 14460] | 0.296 [0.255; 0.338] | 0.202 [0.175; 0.229] | 3049 [2516; 3582] | 1.25 [1.18; 1.33] | 0.43 [0.40; 0.47] | 0.22 | 0.034 |
| sh_madura | 14634 [13441; 15826] | 0.292 [0.251; 0.334] | 0.194 [0.167; 0.222] | 3209 [2700; 3719] | 1.24 [1.16; 1.31] | 0.43 [0.40; 0.46] | 0.20 | 0.034 |
| asha_parcial | 14045 [12858; 15232] | 0.319 [0.277; 0.360] | 0.220 [0.190; 0.250] | 3196 [2682; 3710] | 1.36 [1.27; 1.45] | 0.46 [0.43; 0.49] | 0.22 | 0.058 |
| asha_madura | 16189 [14894; 17484] | 0.328 [0.286; 0.369] | 0.222 [0.194; 0.250] | 4330 [3813; 4847] | 1.36 [1.27; 1.46] | 0.46 [0.43; 0.49] | 0.27 | 0.255 |
| thompson_parcial | 7815 [7196; 8434] | 0.237 [0.201; 0.272] | 0.111 [0.096; 0.126] | 1518 [1172; 1864] | 0.20 [0.15; 0.26] | 0.32 [0.28; 0.35] | 0.17 | 0.121 |
| thompson_madura | 10164 [9309; 11019] | 0.263 [0.227; 0.299] | 0.134 [0.117; 0.150] | 2007 [1634; 2380] | 0.36 [0.30; 0.43] | 0.36 [0.33; 0.40] | 0.17 | 0.101 |

critério: asha_madura: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 4474 [4038; 4911]); asha_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 2331 [1884; 2777]); sh_madura: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 2919 [2685; 3153]); sh_parcial: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 1700 [1444; 1956])

asha_parcial_menos_asha_madura: Δregret -2144 [-2528; -1759]; Δpodadas -0.01 [-0.09; 0.08]

greedy_parcial_menos_greedy_madura: Δregret -865 [-1027; -703]; Δpodadas -0.10 [-0.17; -0.03]

sh_parcial_menos_sh_madura: Δregret -1220 [-1512; -928]; Δpodadas 0.02 [-0.03; 0.07]

thompson_parcial_menos_thompson_madura: Δregret -2350 [-2716; -1983]; Δpodadas -0.16 [-0.22; -0.10]

PÓS-REGISTRO — critério pré-registrado aplicado ao ORÁCULO: supera (vs greedy_parcial; perdedoras ok, drawdown ok)
PÓS-REGISTRO — critério com excesso vs oráculo: asha_madura: não (regret x, excesso x, drawdown x); asha_parcial: não (regret x, excesso x, drawdown x); sh_madura: não (regret x, excesso x, drawdown x); sh_parcial: não (regret x, excesso x, drawdown x)

#### ruido_alto

| política | regret R$ [IC95] | orç. em perdedoras (fim) | excesso vs oráculo (fim, pós-reg.) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |
|---|---|---|---|---|---|---|---|---|
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 0.000 [0.000; 0.000] | 707 [513; 902] | 0.24 [0.15; 0.33] | 0.35 [0.32; 0.39] | 0.30 | 0.000 |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 0.632 [0.619; 0.644] | 4856 [4349; 5363] | 0.00 [0.00; 0.00] | 0.80 [0.79; 0.80] | 0.06 | 0.000 |
| random_sh | 23583 [21681; 25484] | 0.746 [0.717; 0.776] | 0.682 [0.655; 0.710] | 10068 [9328; 10807] | 2.47 [2.33; 2.61] | 0.80 [0.77; 0.82] | 0.22 | 0.034 |
| greedy_parcial | 8673 [7993; 9353] | 0.274 [0.238; 0.310] | 0.158 [0.135; 0.180] | 2373 [1945; 2801] | 0.43 [0.35; 0.52] | 0.36 [0.33; 0.40] | 0.19 | 0.065 |
| greedy_madura | 9478 [8770; 10185] | 0.295 [0.258; 0.332] | 0.181 [0.157; 0.204] | 2654 [2209; 3098] | 0.48 [0.39; 0.57] | 0.38 [0.34; 0.41] | 0.18 | 0.065 |
| sh_parcial | 10632 [9891; 11373] | 0.347 [0.311; 0.384] | 0.260 [0.232; 0.288] | 3099 [2573; 3625] | 0.92 [0.82; 1.02] | 0.41 [0.38; 0.44] | 0.22 | 0.034 |
| sh_madura | 11573 [10746; 12401] | 0.325 [0.287; 0.363] | 0.241 [0.213; 0.269] | 3334 [2834; 3834] | 0.85 [0.76; 0.95] | 0.40 [0.36; 0.43] | 0.20 | 0.034 |
| asha_parcial | 11532 [10656; 12408] | 0.378 [0.340; 0.415] | 0.281 [0.251; 0.312] | 3474 [2928; 4020] | 1.06 [0.95; 1.18] | 0.45 [0.42; 0.48] | 0.22 | 0.058 |
| asha_madura | 13254 [12325; 14184] | 0.360 [0.324; 0.396] | 0.269 [0.242; 0.296] | 4509 [3990; 5027] | 0.94 [0.83; 1.06] | 0.42 [0.39; 0.45] | 0.27 | 0.255 |
| thompson_parcial | 7375 [6798; 7951] | 0.327 [0.297; 0.358] | 0.196 [0.178; 0.213] | 1911 [1544; 2278] | 0.01 [-0.00; 0.02] | 0.37 [0.33; 0.40] | 0.15 | 0.134 |
| thompson_madura | 8384 [7739; 9030] | 0.322 [0.291; 0.354] | 0.192 [0.174; 0.210] | 2312 [1926; 2698] | 0.04 [0.01; 0.07] | 0.37 [0.34; 0.40] | 0.15 | 0.122 |

critério: asha_madura: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 4582 [4185; 4978]); asha_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 2859 [2388; 3330]); sh_madura: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 2900 [2630; 3171]); sh_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 1959 [1710; 2208])

asha_parcial_menos_asha_madura: Δregret -1723 [-2234; -1212]; Δpodadas 0.12 [0.02; 0.22]

greedy_parcial_menos_greedy_madura: Δregret -805 [-913; -697]; Δpodadas -0.04 [-0.11; 0.02]

sh_parcial_menos_sh_madura: Δregret -942 [-1214; -670]; Δpodadas 0.07 [-0.01; 0.14]

thompson_parcial_menos_thompson_madura: Δregret -1010 [-1136; -883]; Δpodadas -0.03 [-0.06; -0.00]

PÓS-REGISTRO — critério pré-registrado aplicado ao ORÁCULO: supera (vs greedy_parcial; perdedoras ok, drawdown ok)
PÓS-REGISTRO — critério com excesso vs oráculo: asha_madura: não (regret x, excesso x, drawdown x); asha_parcial: não (regret x, excesso x, drawdown x); sh_madura: não (regret x, excesso x, drawdown x); sh_parcial: não (regret x, excesso x, drawdown x)

#### ruido_baixo

| política | regret R$ [IC95] | orç. em perdedoras (fim) | excesso vs oráculo (fim, pós-reg.) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |
|---|---|---|---|---|---|---|---|---|
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 0.000 [0.000; 0.000] | 457 [272; 642] | 0.24 [0.15; 0.33] | 0.35 [0.32; 0.39] | 0.30 | 0.000 |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 0.632 [0.619; 0.644] | 4597 [4066; 5129] | 0.00 [0.00; 0.00] | 0.80 [0.79; 0.80] | 0.06 | 0.000 |
| random_sh | 23583 [21681; 25484] | 0.746 [0.717; 0.776] | 0.682 [0.655; 0.710] | 9950 [9210; 10690] | 2.47 [2.33; 2.61] | 0.80 [0.77; 0.82] | 0.22 | 0.034 |
| greedy_parcial | 7011 [6341; 7682] | 0.221 [0.186; 0.256] | 0.068 [0.053; 0.082] | 1512 [1179; 1844] | 0.04 [0.01; 0.06] | 0.31 [0.28; 0.35] | 0.18 | 0.070 |
| greedy_madura | 8078 [7374; 8782] | 0.235 [0.200; 0.270] | 0.099 [0.081; 0.116] | 1825 [1458; 2191] | 0.27 [0.20; 0.33] | 0.31 [0.28; 0.35] | 0.19 | 0.052 |
| sh_parcial | 8476 [7808; 9145] | 0.204 [0.169; 0.239] | 0.102 [0.082; 0.122] | 2026 [1592; 2460] | 0.27 [0.20; 0.34] | 0.25 [0.22; 0.28] | 0.22 | 0.034 |
| sh_madura | 9742 [8943; 10542] | 0.198 [0.162; 0.233] | 0.097 [0.077; 0.117] | 2277 [1858; 2695] | 0.24 [0.18; 0.31] | 0.24 [0.21; 0.28] | 0.20 | 0.034 |
| asha_parcial | 9396 [8540; 10251] | 0.241 [0.206; 0.277] | 0.130 [0.109; 0.152] | 2196 [1766; 2625] | 0.52 [0.43; 0.61] | 0.31 [0.28; 0.34] | 0.22 | 0.058 |
| asha_madura | 11393 [10479; 12307] | 0.261 [0.224; 0.299] | 0.140 [0.118; 0.163] | 3482 [3046; 3918] | 0.55 [0.45; 0.64] | 0.32 [0.28; 0.35] | 0.27 | 0.256 |
| thompson_parcial | 5499 [4943; 6055] | 0.231 [0.197; 0.265] | 0.078 [0.063; 0.092] | 1137 [832; 1441] | 0.01 [-0.00; 0.01] | 0.32 [0.28; 0.35] | 0.18 | 0.104 |
| thompson_madura | 6933 [6297; 7569] | 0.237 [0.202; 0.272] | 0.083 [0.068; 0.097] | 1595 [1263; 1926] | 0.11 [0.06; 0.16] | 0.33 [0.30; 0.37] | 0.19 | 0.077 |

critério: asha_madura: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 4382 [4043; 4720]); asha_parcial: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 2384 [1983; 2785]); sh_madura: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 2731 [2538; 2923]); sh_parcial: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 1465 [1296; 1633])

asha_parcial_menos_asha_madura: Δregret -1997 [-2368; -1626]; Δpodadas -0.03 [-0.11; 0.06]

greedy_parcial_menos_greedy_madura: Δregret -1067 [-1135; -999]; Δpodadas -0.23 [-0.29; -0.17]

sh_parcial_menos_sh_madura: Δregret -1266 [-1481; -1051]; Δpodadas 0.03 [-0.02; 0.07]

thompson_parcial_menos_thompson_madura: Δregret -1434 [-1562; -1306]; Δpodadas -0.10 [-0.15; -0.06]

PÓS-REGISTRO — critério pré-registrado aplicado ao ORÁCULO: NÃO supera (vs greedy_parcial; perdedoras x, drawdown ok)
PÓS-REGISTRO — critério com excesso vs oráculo: asha_madura: não (regret x, excesso x, drawdown x); asha_parcial: não (regret x, excesso x, drawdown x); sh_madura: não (regret x, excesso x, drawdown x); sh_parcial: não (regret x, excesso x, drawdown x)

#### sem_atraso

| política | regret R$ [IC95] | orç. em perdedoras (fim) | excesso vs oráculo (fim, pós-reg.) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |
|---|---|---|---|---|---|---|---|---|
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 0.000 [0.000; 0.000] | 513 [325; 700] | 0.24 [0.15; 0.33] | 0.35 [0.32; 0.39] | 0.30 | 0.000 |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 0.632 [0.619; 0.644] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] | 0.80 [0.79; 0.80] | 0.06 | 0.000 |
| random_sh | 23583 [21681; 25484] | 0.746 [0.717; 0.776] | 0.682 [0.655; 0.710] | 9977 [9237; 10717] | 2.47 [2.33; 2.61] | 0.80 [0.77; 0.82] | 0.22 | 0.034 |
| greedy_parcial | 7736 [7069; 8404] | 0.233 [0.198; 0.268] | 0.110 [0.091; 0.129] | 1818 [1442; 2194] | 0.23 [0.16; 0.29] | 0.31 [0.28; 0.35] | 0.19 | 0.058 |
| greedy_madura | 7736 [7069; 8404] | 0.233 [0.198; 0.268] | 0.110 [0.091; 0.129] | 1818 [1442; 2194] | 0.23 [0.16; 0.29] | 0.31 [0.28; 0.35] | 0.19 | 0.058 |
| sh_parcial | 9050 [8382; 9719] | 0.255 [0.219; 0.291] | 0.165 [0.141; 0.189] | 2368 [1894; 2842] | 0.51 [0.42; 0.60] | 0.31 [0.28; 0.34] | 0.22 | 0.034 |
| sh_madura | 9050 [8382; 9719] | 0.255 [0.219; 0.291] | 0.165 [0.141; 0.189] | 2368 [1894; 2842] | 0.51 [0.42; 0.60] | 0.31 [0.28; 0.34] | 0.22 | 0.034 |
| asha_parcial | 9947 [9049; 10845] | 0.274 [0.238; 0.310] | 0.172 [0.146; 0.197] | 2516 [2058; 2974] | 0.62 [0.52; 0.72] | 0.34 [0.30; 0.37] | 0.22 | 0.059 |
| asha_madura | 9947 [9049; 10845] | 0.274 [0.238; 0.310] | 0.172 [0.146; 0.197] | 2516 [2058; 2974] | 0.62 [0.52; 0.72] | 0.34 [0.30; 0.37] | 0.22 | 0.059 |
| thompson_parcial | 5961 [5424; 6499] | 0.253 [0.220; 0.285] | 0.113 [0.098; 0.128] | 1358 [1024; 1692] | 0.04 [0.01; 0.07] | 0.32 [0.28; 0.35] | 0.18 | 0.126 |
| thompson_madura | 5961 [5424; 6499] | 0.253 [0.220; 0.285] | 0.113 [0.098; 0.128] | 1358 [1024; 1692] | 0.04 [0.01; 0.07] | 0.32 [0.28; 0.35] | 0.18 | 0.126 |

critério: asha_madura: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 2211 [1760; 2662]); asha_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 2211 [1760; 2662]); sh_madura: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 1314 [1141; 1487]); sh_parcial: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 1314 [1141; 1487])

asha_parcial_menos_asha_madura: Δregret 0 [0; 0]; Δpodadas 0.00 [0.00; 0.00]

greedy_parcial_menos_greedy_madura: Δregret 0 [0; 0]; Δpodadas 0.00 [0.00; 0.00]

sh_parcial_menos_sh_madura: Δregret 0 [0; 0]; Δpodadas 0.00 [0.00; 0.00]

thompson_parcial_menos_thompson_madura: Δregret 0 [0; 0]; Δpodadas 0.00 [0.00; 0.00]

PÓS-REGISTRO — critério pré-registrado aplicado ao ORÁCULO: NÃO supera (vs greedy_parcial; perdedoras x, drawdown ok)
PÓS-REGISTRO — critério com excesso vs oráculo: asha_madura: não (regret x, excesso x, drawdown x); asha_parcial: não (regret x, excesso x, drawdown x); sh_madura: não (regret x, excesso x, drawdown x); sh_parcial: não (regret x, excesso x, drawdown x)

#### vencedoras_lentas_D3

| política | regret R$ [IC95] | orç. em perdedoras (fim) | excesso vs oráculo (fim, pós-reg.) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |
|---|---|---|---|---|---|---|---|---|
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 0.000 [0.000; 0.000] | 513 [325; 700] | 0.24 [0.15; 0.33] | 0.35 [0.32; 0.39] | 0.30 | 0.000 |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 0.632 [0.619; 0.644] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] | 0.80 [0.79; 0.80] | 0.06 | 0.000 |
| random_sh | 23583 [21681; 25484] | 0.746 [0.717; 0.776] | 0.682 [0.655; 0.710] | 9977 [9237; 10717] | 2.47 [2.33; 2.61] | 0.80 [0.77; 0.82] | 0.22 | 0.034 |
| greedy_parcial | 7630 [6963; 8297] | 0.238 [0.203; 0.273] | 0.102 [0.084; 0.121] | 1801 [1437; 2165] | 0.12 [0.08; 0.17] | 0.33 [0.30; 0.36] | 0.18 | 0.075 |
| greedy_madura | 8498 [7796; 9199] | 0.250 [0.214; 0.285] | 0.127 [0.107; 0.146] | 2051 [1659; 2443] | 0.33 [0.25; 0.40] | 0.33 [0.30; 0.37] | 0.19 | 0.057 |
| sh_parcial | 10504 [9794; 11215] | 0.416 [0.380; 0.453] | 0.289 [0.263; 0.316] | 2922 [2390; 3455] | 1.10 [0.99; 1.21] | 0.46 [0.42; 0.49] | 0.22 | 0.034 |
| sh_madura | 10213 [9411; 11016] | 0.240 [0.204; 0.276] | 0.149 [0.125; 0.173] | 2545 [2100; 2989] | 0.46 [0.37; 0.54] | 0.29 [0.26; 0.33] | 0.20 | 0.034 |
| asha_parcial | 14098 [13021; 15175] | 0.596 [0.559; 0.633] | 0.448 [0.416; 0.480] | 4608 [3978; 5239] | 1.82 [1.69; 1.95] | 0.64 [0.60; 0.67] | 0.22 | 0.057 |
| asha_madura | 12090 [11137; 13043] | 0.291 [0.254; 0.328] | 0.180 [0.154; 0.205] | 3806 [3338; 4273] | 0.69 [0.59; 0.79] | 0.35 [0.32; 0.39] | 0.27 | 0.255 |
| thompson_parcial | 6907 [6306; 7508] | 0.269 [0.236; 0.301] | 0.122 [0.106; 0.138] | 1619 [1295; 1943] | 0.00 [0.00; 0.00] | 0.33 [0.30; 0.36] | 0.16 | 0.124 |
| thompson_madura | 7311 [6682; 7940] | 0.257 [0.224; 0.290] | 0.115 [0.100; 0.131] | 1764 [1421; 2107] | 0.04 [0.01; 0.07] | 0.33 [0.30; 0.37] | 0.17 | 0.098 |

critério: asha_madura: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 4460 [4070; 4849]); asha_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 6468 [5698; 7238]); sh_madura: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 2583 [2374; 2792]); sh_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 2874 [2590; 3159])

asha_parcial_menos_asha_madura: Δregret 2008 [1202; 2814]; Δpodadas 1.13 [1.00; 1.26]

greedy_parcial_menos_greedy_madura: Δregret -868 [-950; -785]; Δpodadas -0.20 [-0.27; -0.13]

sh_parcial_menos_sh_madura: Δregret 291 [-42; 625]; Δpodadas 0.65 [0.56; 0.73]

thompson_parcial_menos_thompson_madura: Δregret -404 [-495; -314]; Δpodadas -0.04 [-0.07; -0.01]

PÓS-REGISTRO — critério pré-registrado aplicado ao ORÁCULO: NÃO supera (vs greedy_parcial; perdedoras x, drawdown ok)
PÓS-REGISTRO — critério com excesso vs oráculo: asha_madura: não (regret x, excesso x, drawdown x); asha_parcial: não (regret x, excesso x, drawdown x); sh_madura: não (regret x, excesso x, drawdown x); sh_parcial: não (regret x, excesso x, drawdown x)

#### vencedoras_lentas_D6

| política | regret R$ [IC95] | orç. em perdedoras (fim) | excesso vs oráculo (fim, pós-reg.) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |
|---|---|---|---|---|---|---|---|---|
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 0.000 [0.000; 0.000] | 513 [325; 700] | 0.24 [0.15; 0.33] | 0.35 [0.32; 0.39] | 0.30 | 0.000 |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 0.632 [0.619; 0.644] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] | 0.80 [0.79; 0.80] | 0.06 | 0.000 |
| random_sh | 23583 [21681; 25484] | 0.746 [0.717; 0.776] | 0.682 [0.655; 0.710] | 9977 [9237; 10717] | 2.47 [2.33; 2.61] | 0.80 [0.77; 0.82] | 0.22 | 0.034 |
| greedy_parcial | 7742 [7072; 8412] | 0.246 [0.211; 0.280] | 0.102 [0.084; 0.120] | 1841 [1482; 2199] | 0.09 [0.05; 0.13] | 0.34 [0.31; 0.37] | 0.17 | 0.085 |
| greedy_madura | 9876 [9073; 10678] | 0.258 [0.224; 0.293] | 0.131 [0.112; 0.150] | 2426 [2018; 2833] | 0.35 [0.28; 0.42] | 0.36 [0.32; 0.39] | 0.17 | 0.052 |
| sh_parcial | 12170 [11432; 12907] | 0.581 [0.549; 0.614] | 0.430 [0.404; 0.456] | 3658 [3066; 4250] | 1.67 [1.55; 1.78] | 0.60 [0.57; 0.63] | 0.22 | 0.034 |
| sh_madura | 11449 [10538; 12360] | 0.249 [0.213; 0.285] | 0.160 [0.135; 0.185] | 2886 [2433; 3338] | 0.51 [0.43; 0.59] | 0.31 [0.28; 0.34] | 0.18 | 0.034 |
| asha_parcial | 15076 [13992; 16160] | 0.706 [0.675; 0.738] | 0.543 [0.514; 0.572] | 5072 [4415; 5728] | 2.17 [2.05; 2.30] | 0.72 [0.70; 0.75] | 0.22 | 0.058 |
| asha_madura | 13818 [12810; 14826] | 0.284 [0.247; 0.320] | 0.182 [0.157; 0.206] | 4343 [3856; 4830] | 0.64 [0.54; 0.73] | 0.34 [0.31; 0.37] | 0.26 | 0.267 |
| thompson_parcial | 7322 [6710; 7934] | 0.295 [0.263; 0.327] | 0.142 [0.126; 0.159] | 1711 [1384; 2038] | 0.00 [0.00; 0.00] | 0.35 [0.32; 0.38] | 0.15 | 0.126 |
| thompson_madura | 8777 [8047; 9507] | 0.279 [0.246; 0.312] | 0.135 [0.118; 0.151] | 2164 [1799; 2530] | 0.07 [0.03; 0.11] | 0.36 [0.33; 0.39] | 0.16 | 0.087 |

critério: asha_madura: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 6076 [5582; 6570]); asha_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 7334 [6564; 8105]); sh_madura: não (vs greedy_parcial; regret x, perdedoras ok, drawdown x; Δpareado 3707 [3386; 4028]); sh_parcial: não (vs greedy_parcial; regret x, perdedoras x, drawdown x; Δpareado 4428 [4091; 4765])

asha_parcial_menos_asha_madura: Δregret 1258 [495; 2021]; Δpodadas 1.54 [1.42; 1.66]

greedy_parcial_menos_greedy_madura: Δregret -2134 [-2322; -1945]; Δpodadas -0.26 [-0.33; -0.19]

sh_parcial_menos_sh_madura: Δregret 721 [242; 1200]; Δpodadas 1.16 [1.05; 1.26]

thompson_parcial_menos_thompson_madura: Δregret -1454 [-1642; -1267]; Δpodadas -0.07 [-0.11; -0.03]

PÓS-REGISTRO — critério pré-registrado aplicado ao ORÁCULO: NÃO supera (vs greedy_parcial; perdedoras x, drawdown ok)
PÓS-REGISTRO — critério com excesso vs oráculo: asha_madura: não (regret x, excesso x, drawdown x); asha_parcial: não (regret x, excesso x, drawdown x); sh_madura: não (regret x, excesso x, drawdown x); sh_parcial: não (regret x, excesso x, drawdown x)

## parametros


#### degraus__base

| política | regret R$ [IC95] | perdedoras | drawdown R$ | podadas | supera? |
|---|---|---|---|---|---|
| asha_e2_r120brl_gasto_madura | 10029 [9309; 10749] | 0.268 [0.230; 0.305] | 2708 [2243; 3173] | 0.55 [0.45; 0.64] | não (vs greedy_parcial) |
| asha_e2_r120brl_gasto_parcial | 10060 [9185; 10934] | 0.294 [0.256; 0.331] | 2744 [2243; 3245] | 0.71 [0.61; 0.81] | não (vs greedy_parcial) |
| asha_e2_r150_cliques_madura | 12529 [11541; 13518] | 0.254 [0.218; 0.289] | 3549 [3101; 3997] | 0.56 [0.47; 0.65] | não (vs greedy_parcial) |
| asha_e2_r150_cliques_parcial | 11298 [10169; 12428] | 0.249 [0.212; 0.286] | 2686 [2258; 3114] | 0.52 [0.43; 0.60] | não (vs greedy_parcial) |
| asha_e2_r20_cliques_madura | 10591 [9852; 11330] | 0.319 [0.283; 0.355] | 2996 [2489; 3504] | 0.76 [0.66; 0.86] | não (vs greedy_parcial) |
| asha_e2_r20_cliques_parcial | 9229 [8560; 9899] | 0.291 [0.255; 0.328] | 2531 [2038; 3024] | 0.69 [0.59; 0.79] | não (vs greedy_parcial) |
| asha_e2_r60_cliques_madura | 12090 [11137; 13043] | 0.291 [0.254; 0.328] | 3806 [3338; 4273] | 0.69 [0.59; 0.79] | não (vs greedy_parcial) |
| asha_e2_r60_cliques_parcial | 10164 [9273; 11056] | 0.287 [0.251; 0.324] | 2635 [2166; 3104] | 0.69 [0.59; 0.79] | não (vs greedy_parcial) |
| asha_e3_r150_cliques_madura | 12865 [11951; 13780] | 0.259 [0.223; 0.295] | 4037 [3551; 4524] | 0.57 [0.48; 0.66] | não (vs greedy_parcial) |
| asha_e3_r150_cliques_parcial | 9480 [8713; 10248] | 0.246 [0.211; 0.281] | 2426 [2005; 2846] | 0.49 [0.40; 0.59] | não (vs greedy_parcial) |
| asha_e3_r20_cliques_madura | 10681 [9955; 11407] | 0.319 [0.282; 0.356] | 3078 [2566; 3589] | 0.79 [0.68; 0.89] | não (vs greedy_parcial) |
| asha_e3_r20_cliques_parcial | 9013 [8333; 9693] | 0.310 [0.273; 0.347] | 2462 [1961; 2963] | 0.77 [0.66; 0.87] | não (vs greedy_parcial) |
| asha_e3_r60_cliques_madura | 12258 [11428; 13089] | 0.295 [0.261; 0.329] | 4001 [3503; 4498] | 0.70 [0.59; 0.81] | não (vs greedy_parcial) |
| asha_e3_r60_cliques_parcial | 9129 [8434; 9824] | 0.286 [0.250; 0.322] | 2396 [1926; 2866] | 0.69 [0.58; 0.79] | não (vs greedy_parcial) |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] |  |
| greedy_madura | 8498 [7796; 9199] | 0.250 [0.214; 0.285] | 2051 [1659; 2443] | 0.33 [0.25; 0.40] |  |
| greedy_parcial | 7556 [6887; 8226] | 0.235 [0.200; 0.270] | 1760 [1395; 2124] | 0.15 [0.10; 0.21] |  |
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 513 [325; 700] | 0.24 [0.15; 0.33] |  |
| random_sh | 23583 [21681; 25484] | 0.746 [0.717; 0.776] | 9977 [9237; 10717] | 2.47 [2.33; 2.61] |  |
| sh_e2_r120brl_gasto_madura | 10051 [9308; 10795] | 0.246 [0.209; 0.283] | 2583 [2108; 3057] | 0.47 [0.39; 0.55] | não (vs greedy_parcial) |
| sh_e2_r120brl_gasto_parcial | 8997 [8327; 9667] | 0.266 [0.230; 0.302] | 2439 [1938; 2941] | 0.58 [0.50; 0.67] | não (vs greedy_parcial) |
| sh_e2_r150_cliques_madura | 11237 [10262; 12213] | 0.229 [0.194; 0.264] | 2660 [2245; 3075] | 0.39 [0.31; 0.47] | não (vs greedy_parcial) |
| sh_e2_r150_cliques_parcial | 9968 [9134; 10801] | 0.224 [0.189; 0.259] | 2360 [1948; 2772] | 0.37 [0.29; 0.45] | não (vs greedy_parcial) |
| sh_e2_r20_cliques_madura | 10611 [9879; 11343] | 0.296 [0.259; 0.333] | 2921 [2397; 3444] | 0.74 [0.65; 0.83] | não (vs greedy_parcial) |
| sh_e2_r20_cliques_parcial | 9403 [8747; 10060] | 0.297 [0.259; 0.336] | 2666 [2120; 3212] | 0.72 [0.62; 0.82] | não (vs greedy_parcial) |
| sh_e2_r60_cliques_madura | 10213 [9411; 11016] | 0.240 [0.204; 0.276] | 2545 [2100; 2989] | 0.46 [0.37; 0.54] | não (vs greedy_parcial) |
| sh_e2_r60_cliques_parcial | 9123 [8458; 9788] | 0.250 [0.214; 0.286] | 2410 [1937; 2883] | 0.49 [0.41; 0.58] | não (vs greedy_parcial) |
| sh_e3_r150_cliques_madura | 10743 [9844; 11641] | 0.231 [0.196; 0.267] | 2631 [2211; 3051] | 0.40 [0.32; 0.47] | não (vs greedy_parcial) |
| sh_e3_r150_cliques_parcial | 9635 [8865; 10404] | 0.235 [0.199; 0.271] | 2417 [1980; 2854] | 0.43 [0.35; 0.52] | não (vs greedy_parcial) |
| sh_e3_r20_cliques_madura | 10675 [9946; 11404] | 0.311 [0.273; 0.349] | 3050 [2504; 3597] | 0.81 [0.70; 0.91] | não (vs greedy_parcial) |
| sh_e3_r20_cliques_parcial | 9371 [8707; 10035] | 0.315 [0.277; 0.353] | 2726 [2165; 3288] | 0.82 [0.72; 0.93] | não (vs greedy_parcial) |
| sh_e3_r60_cliques_madura | 10110 [9345; 10874] | 0.246 [0.210; 0.282] | 2608 [2151; 3066] | 0.50 [0.42; 0.58] | não (vs greedy_parcial) |
| sh_e3_r60_cliques_parcial | 9044 [8357; 9732] | 0.260 [0.225; 0.295] | 2424 [1940; 2908] | 0.52 [0.43; 0.60] | não (vs greedy_parcial) |

#### degraus__ideal_sem_saturacao

| política | regret R$ [IC95] | perdedoras | drawdown R$ | podadas | supera? |
|---|---|---|---|---|---|
| asha_e2_r120brl_gasto_madura | 37577 [32972; 42182] | 0.225 [0.188; 0.262] | 684 [528; 841] | 0.39 [0.30; 0.47] | não (vs greedy_parcial) |
| asha_e2_r120brl_gasto_parcial | 37577 [32972; 42182] | 0.225 [0.188; 0.262] | 684 [528; 841] | 0.39 [0.30; 0.47] | não (vs greedy_parcial) |
| asha_e2_r150_cliques_madura | 42380 [37461; 47299] | 0.207 [0.172; 0.243] | 1330 [1106; 1553] | 0.28 [0.22; 0.35] | não (vs greedy_parcial) |
| asha_e2_r150_cliques_parcial | 42380 [37461; 47299] | 0.207 [0.172; 0.243] | 1330 [1106; 1553] | 0.28 [0.22; 0.35] | não (vs greedy_parcial) |
| asha_e2_r20_cliques_madura | 35323 [31009; 39637] | 0.206 [0.172; 0.241] | 536 [402; 670] | 0.32 [0.24; 0.39] | não (vs greedy_parcial) |
| asha_e2_r20_cliques_parcial | 35323 [31009; 39637] | 0.206 [0.172; 0.241] | 536 [402; 670] | 0.32 [0.24; 0.39] | não (vs greedy_parcial) |
| asha_e2_r60_cliques_madura | 37696 [33106; 42286] | 0.217 [0.183; 0.252] | 714 [566; 861] | 0.34 [0.27; 0.42] | não (vs greedy_parcial) |
| asha_e2_r60_cliques_parcial | 37696 [33106; 42286] | 0.217 [0.183; 0.252] | 714 [566; 861] | 0.34 [0.27; 0.42] | não (vs greedy_parcial) |
| asha_e3_r150_cliques_madura | 38157 [33610; 42704] | 0.189 [0.154; 0.223] | 978 [815; 1141] | 0.19 [0.13; 0.25] | não (vs greedy_parcial) |
| asha_e3_r150_cliques_parcial | 38157 [33610; 42704] | 0.189 [0.154; 0.223] | 978 [815; 1141] | 0.19 [0.13; 0.25] | não (vs greedy_parcial) |
| asha_e3_r20_cliques_madura | 34732 [30453; 39011] | 0.215 [0.180; 0.250] | 455 [330; 580] | 0.34 [0.26; 0.41] | não (vs greedy_parcial) |
| asha_e3_r20_cliques_parcial | 34732 [30453; 39011] | 0.215 [0.180; 0.250] | 455 [330; 580] | 0.34 [0.26; 0.41] | não (vs greedy_parcial) |
| asha_e3_r60_cliques_madura | 35595 [31244; 39945] | 0.203 [0.168; 0.237] | 583 [448; 718] | 0.26 [0.19; 0.33] | não (vs greedy_parcial) |
| asha_e3_r60_cliques_parcial | 35595 [31244; 39945] | 0.203 [0.168; 0.237] | 583 [448; 718] | 0.26 [0.19; 0.33] | não (vs greedy_parcial) |
| equal | 56051 [50384; 61718] | 0.751 [0.735; 0.766] | 4524 [3996; 5052] | 0.00 [0.00; 0.00] |  |
| greedy_madura | 36360 [31976; 40745] | 0.189 [0.155; 0.224] | 705 [565; 846] | 0.14 [0.10; 0.19] |  |
| greedy_parcial | 36360 [31976; 40745] | 0.189 [0.155; 0.224] | 705 [565; 846] | 0.14 [0.10; 0.19] |  |
| oraculo | 0 [0; 0] | 0.015 [-0.002; 0.032] | 44 [-4; 92] | 2.29 [2.16; 2.42] |  |
| random_sh | 55777 [50010; 61545] | 0.746 [0.717; 0.776] | 5716 [5070; 6362] | 2.47 [2.33; 2.61] |  |
| sh_e2_r120brl_gasto_madura | 35027 [30720; 39334] | 0.203 [0.168; 0.237] | 523 [395; 651] | 0.25 [0.19; 0.31] | não (vs greedy_parcial) |
| sh_e2_r120brl_gasto_parcial | 35027 [30720; 39334] | 0.203 [0.168; 0.237] | 523 [395; 651] | 0.25 [0.19; 0.31] | não (vs greedy_parcial) |
| sh_e2_r150_cliques_madura | 39499 [34883; 44114] | 0.188 [0.153; 0.222] | 1171 [989; 1353] | 0.18 [0.12; 0.24] | não (vs greedy_parcial) |
| sh_e2_r150_cliques_parcial | 39499 [34883; 44114] | 0.188 [0.153; 0.222] | 1171 [989; 1353] | 0.18 [0.12; 0.24] | não (vs greedy_parcial) |
| sh_e2_r20_cliques_madura | 34396 [30152; 38640] | 0.212 [0.177; 0.248] | 419 [295; 543] | 0.36 [0.29; 0.44] | não (vs greedy_parcial) |
| sh_e2_r20_cliques_parcial | 34396 [30152; 38640] | 0.212 [0.177; 0.248] | 419 [295; 543] | 0.36 [0.29; 0.44] | não (vs greedy_parcial) |
| sh_e2_r60_cliques_madura | 35821 [31469; 40174] | 0.199 [0.164; 0.234] | 663 [526; 801] | 0.23 [0.17; 0.29] | não (vs greedy_parcial) |
| sh_e2_r60_cliques_parcial | 35821 [31469; 40174] | 0.199 [0.164; 0.234] | 663 [526; 801] | 0.23 [0.17; 0.29] | não (vs greedy_parcial) |
| sh_e3_r150_cliques_madura | 38303 [33774; 42832] | 0.188 [0.153; 0.222] | 1094 [927; 1261] | 0.17 [0.11; 0.22] | não (vs greedy_parcial) |
| sh_e3_r150_cliques_parcial | 38303 [33774; 42832] | 0.188 [0.153; 0.222] | 1094 [927; 1261] | 0.17 [0.11; 0.22] | não (vs greedy_parcial) |
| sh_e3_r20_cliques_madura | 34332 [30114; 38549] | 0.219 [0.183; 0.254] | 420 [288; 552] | 0.38 [0.30; 0.46] | não (vs greedy_parcial) |
| sh_e3_r20_cliques_parcial | 34332 [30114; 38549] | 0.219 [0.183; 0.254] | 420 [288; 552] | 0.38 [0.30; 0.46] | não (vs greedy_parcial) |
| sh_e3_r60_cliques_madura | 35494 [31164; 39824] | 0.199 [0.164; 0.234] | 632 [497; 767] | 0.24 [0.17; 0.31] | não (vs greedy_parcial) |
| sh_e3_r60_cliques_parcial | 35494 [31164; 39824] | 0.199 [0.164; 0.234] | 632 [497; 767] | 0.24 [0.17; 0.31] | não (vs greedy_parcial) |

#### degraus__vencedoras_lentas_D3

| política | regret R$ [IC95] | perdedoras | drawdown R$ | podadas | supera? |
|---|---|---|---|---|---|
| asha_e2_r120brl_gasto_madura | 10029 [9309; 10749] | 0.268 [0.230; 0.305] | 2708 [2243; 3173] | 0.55 [0.45; 0.64] | não (vs greedy_parcial) |
| asha_e2_r120brl_gasto_parcial | 15514 [14519; 16509] | 0.726 [0.694; 0.759] | 5561 [4853; 6269] | 2.24 [2.11; 2.37] | não (vs greedy_parcial) |
| asha_e2_r150_cliques_madura | 12529 [11541; 13518] | 0.254 [0.218; 0.289] | 3549 [3101; 3997] | 0.56 [0.47; 0.65] | não (vs greedy_parcial) |
| asha_e2_r150_cliques_parcial | 12049 [10905; 13193] | 0.349 [0.311; 0.387] | 2986 [2535; 3438] | 0.88 [0.76; 0.99] | não (vs greedy_parcial) |
| asha_e2_r20_cliques_madura | 10591 [9852; 11330] | 0.319 [0.283; 0.355] | 2996 [2489; 3504] | 0.76 [0.66; 0.86] | não (vs greedy_parcial) |
| asha_e2_r20_cliques_parcial | 16138 [15251; 17026] | 0.780 [0.753; 0.807] | 6132 [5390; 6875] | 2.40 [2.28; 2.53] | não (vs greedy_parcial) |
| asha_e2_r60_cliques_madura | 12090 [11137; 13043] | 0.291 [0.254; 0.328] | 3806 [3338; 4273] | 0.69 [0.59; 0.79] | não (vs greedy_parcial) |
| asha_e2_r60_cliques_parcial | 14098 [13021; 15175] | 0.596 [0.559; 0.633] | 4608 [3978; 5239] | 1.82 [1.69; 1.95] | não (vs greedy_parcial) |
| asha_e3_r150_cliques_madura | 12865 [11951; 13780] | 0.259 [0.223; 0.295] | 4037 [3551; 4524] | 0.57 [0.48; 0.66] | não (vs greedy_parcial) |
| asha_e3_r150_cliques_parcial | 11310 [10476; 12144] | 0.465 [0.429; 0.501] | 3010 [2542; 3477] | 1.29 [1.16; 1.43] | não (vs greedy_parcial) |
| asha_e3_r20_cliques_madura | 10681 [9955; 11407] | 0.319 [0.282; 0.356] | 3078 [2566; 3589] | 0.79 [0.68; 0.89] | não (vs greedy_parcial) |
| asha_e3_r20_cliques_parcial | 19162 [17987; 20337] | 0.894 [0.872; 0.915] | 8210 [7424; 8996] | 2.85 [2.71; 2.99] | não (vs greedy_parcial) |
| asha_e3_r60_cliques_madura | 12258 [11428; 13089] | 0.295 [0.261; 0.329] | 4001 [3503; 4498] | 0.70 [0.59; 0.81] | não (vs greedy_parcial) |
| asha_e3_r60_cliques_parcial | 15526 [14561; 16491] | 0.726 [0.694; 0.758] | 5646 [4945; 6346] | 2.25 [2.11; 2.39] | não (vs greedy_parcial) |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] |  |
| greedy_madura | 8498 [7796; 9199] | 0.250 [0.214; 0.285] | 2051 [1659; 2443] | 0.33 [0.25; 0.40] |  |
| greedy_parcial | 7630 [6963; 8297] | 0.238 [0.203; 0.273] | 1801 [1437; 2165] | 0.12 [0.08; 0.17] |  |
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 513 [325; 700] | 0.24 [0.15; 0.33] |  |
| random_sh | 23583 [21681; 25484] | 0.746 [0.717; 0.776] | 9977 [9237; 10717] | 2.47 [2.33; 2.61] |  |
| sh_e2_r120brl_gasto_madura | 10051 [9308; 10795] | 0.246 [0.209; 0.283] | 2583 [2108; 3057] | 0.47 [0.39; 0.55] | não (vs greedy_parcial) |
| sh_e2_r120brl_gasto_parcial | 11408 [10714; 12101] | 0.511 [0.476; 0.547] | 3374 [2780; 3968] | 1.47 [1.35; 1.59] | não (vs greedy_parcial) |
| sh_e2_r150_cliques_madura | 11237 [10262; 12213] | 0.229 [0.194; 0.264] | 2660 [2245; 3075] | 0.39 [0.31; 0.47] | não (vs greedy_parcial) |
| sh_e2_r150_cliques_parcial | 10142 [9309; 10974] | 0.265 [0.229; 0.301] | 2445 [2026; 2864] | 0.50 [0.41; 0.59] | não (vs greedy_parcial) |
| sh_e2_r20_cliques_madura | 10611 [9879; 11343] | 0.296 [0.259; 0.333] | 2921 [2397; 3444] | 0.74 [0.65; 0.83] | não (vs greedy_parcial) |
| sh_e2_r20_cliques_parcial | 14838 [14014; 15661] | 0.714 [0.681; 0.746] | 5621 [4830; 6413] | 2.18 [2.04; 2.32] | não (vs greedy_parcial) |
| sh_e2_r60_cliques_madura | 10213 [9411; 11016] | 0.240 [0.204; 0.276] | 2545 [2100; 2989] | 0.46 [0.37; 0.54] | não (vs greedy_parcial) |
| sh_e2_r60_cliques_parcial | 10504 [9794; 11215] | 0.416 [0.380; 0.453] | 2922 [2390; 3455] | 1.10 [0.99; 1.21] | não (vs greedy_parcial) |
| sh_e3_r150_cliques_madura | 10743 [9844; 11641] | 0.231 [0.196; 0.267] | 2631 [2211; 3051] | 0.40 [0.32; 0.47] | não (vs greedy_parcial) |
| sh_e3_r150_cliques_parcial | 9976 [9192; 10760] | 0.297 [0.259; 0.336] | 2544 [2099; 2988] | 0.64 [0.54; 0.73] | não (vs greedy_parcial) |
| sh_e3_r20_cliques_madura | 10675 [9946; 11404] | 0.311 [0.273; 0.349] | 3050 [2504; 3597] | 0.81 [0.70; 0.91] | não (vs greedy_parcial) |
| sh_e3_r20_cliques_parcial | 16307 [15326; 17289] | 0.765 [0.734; 0.796] | 6476 [5654; 7299] | 2.38 [2.24; 2.53] | não (vs greedy_parcial) |
| sh_e3_r60_cliques_madura | 10110 [9345; 10874] | 0.246 [0.210; 0.282] | 2608 [2151; 3066] | 0.50 [0.42; 0.58] | não (vs greedy_parcial) |
| sh_e3_r60_cliques_parcial | 10807 [10088; 11526] | 0.461 [0.425; 0.498] | 3125 [2571; 3678] | 1.26 [1.15; 1.37] | não (vs greedy_parcial) |

#### n_final_1__base

| política | regret R$ [IC95] | perdedoras | drawdown R$ | podadas | supera? |
|---|---|---|---|---|---|
| asha_madura | 23077 [21078; 25076] | 0.275 [0.213; 0.337] | 10542 [9735; 11348] | 2.60 [2.46; 2.74] | não (vs greedy_parcial) |
| asha_parcial | 22697 [20694; 24700] | 0.300 [0.236; 0.364] | 11020 [10019; 12021] | 2.62 [2.49; 2.75] | não (vs greedy_parcial) |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] |  |
| greedy_madura | 11639 [11112; 12167] | 0.168 [0.127; 0.209] | 4522 [3861; 5183] | 1.74 [1.60; 1.87] |  |
| greedy_parcial | 8234 [7870; 8599] | 0.089 [0.059; 0.118] | 2643 [2163; 3123] | 1.28 [1.14; 1.42] |  |
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 513 [325; 700] | 0.24 [0.15; 0.33] |  |
| random_sh | 30861 [28627; 33095] | 0.755 [0.695; 0.815] | 16981 [16235; 17727] | 3.09 [2.95; 3.23] |  |
| sh_madura | 13552 [12745; 14359] | 0.035 [0.009; 0.061] | 5094 [4390; 5799] | 2.32 [2.19; 2.45] | não (vs greedy_parcial) |
| sh_parcial | 13060 [12206; 13914] | 0.045 [0.016; 0.074] | 5550 [4746; 6355] | 2.33 [2.20; 2.46] | não (vs greedy_parcial) |
| thompson_madura | 10680 [10111; 11248] | 0.217 [0.180; 0.254] | 3901 [3334; 4468] | 1.29 [1.15; 1.43] |  |
| thompson_parcial | 6583 [6267; 6900] | 0.145 [0.115; 0.175] | 2037 [1650; 2425] | 0.54 [0.42; 0.65] |  |

#### n_final_1__ideal_sem_saturacao

| política | regret R$ [IC95] | perdedoras | drawdown R$ | podadas | supera? |
|---|---|---|---|---|---|
| asha_madura | 30833 [25320; 36346] | 0.215 [0.158; 0.272] | 1323 [972; 1675] | 2.53 [2.40; 2.66] | não (vs greedy_parcial) |
| asha_parcial | 30833 [25320; 36346] | 0.215 [0.158; 0.272] | 1323 [972; 1675] | 2.53 [2.40; 2.66] | não (vs greedy_parcial) |
| equal | 56051 [50384; 61718] | 0.751 [0.735; 0.766] | 4524 [3996; 5052] | 0.00 [0.00; 0.00] |  |
| greedy_madura | 9321 [8397; 10246] | 0.015 [-0.002; 0.032] | 544 [454; 635] | 2.27 [2.14; 2.40] |  |
| greedy_parcial | 9321 [8397; 10246] | 0.015 [-0.002; 0.032] | 544 [454; 635] | 2.27 [2.14; 2.40] |  |
| oraculo | 0 [0; 0] | 0.015 [-0.002; 0.032] | 44 [-4; 92] | 2.29 [2.16; 2.42] |  |
| random_sh | 55358 [49114; 61603] | 0.755 [0.695; 0.815] | 7956 [7095; 8817] | 3.09 [2.95; 3.23] |  |
| sh_madura | 9035 [8106; 9964] | 0.015 [-0.002; 0.032] | 562 [469; 655] | 2.29 [2.16; 2.42] | não (vs greedy_parcial) |
| sh_parcial | 9035 [8106; 9964] | 0.015 [-0.002; 0.032] | 562 [469; 655] | 2.29 [2.16; 2.42] | não (vs greedy_parcial) |
| thompson_madura | 2162 [1999; 2324] | 0.017 [-0.000; 0.033] | 216 [146; 286] | 2.12 [1.98; 2.27] |  |
| thompson_parcial | 2162 [1999; 2324] | 0.017 [-0.000; 0.033] | 216 [146; 286] | 2.12 [1.98; 2.27] |  |

#### n_final_1__vencedoras_lentas_D3

| política | regret R$ [IC95] | perdedoras | drawdown R$ | podadas | supera? |
|---|---|---|---|---|---|
| asha_madura | 23077 [21078; 25076] | 0.275 [0.213; 0.337] | 10542 [9735; 11348] | 2.60 [2.46; 2.74] | não (vs greedy_parcial) |
| asha_parcial | 26139 [24065; 28212] | 0.605 [0.537; 0.673] | 13786 [12778; 14793] | 2.90 [2.77; 3.04] | não (vs greedy_parcial) |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] |  |
| greedy_madura | 11639 [11112; 12167] | 0.168 [0.127; 0.209] | 4522 [3861; 5183] | 1.74 [1.60; 1.87] |  |
| greedy_parcial | 8066 [7715; 8418] | 0.083 [0.054; 0.112] | 2575 [2104; 3047] | 1.21 [1.06; 1.35] |  |
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 513 [325; 700] | 0.24 [0.15; 0.33] |  |
| random_sh | 30861 [28627; 33095] | 0.755 [0.695; 0.815] | 16981 [16235; 17727] | 3.09 [2.95; 3.23] |  |
| sh_madura | 13552 [12745; 14359] | 0.035 [0.009; 0.061] | 5094 [4390; 5799] | 2.32 [2.19; 2.45] | não (vs greedy_parcial) |
| sh_parcial | 13797 [12910; 14684] | 0.135 [0.088; 0.182] | 6247 [5339; 7156] | 2.42 [2.29; 2.54] | não (vs greedy_parcial) |
| thompson_madura | 10680 [10111; 11248] | 0.217 [0.180; 0.254] | 3901 [3334; 4468] | 1.29 [1.15; 1.43] |  |
| thompson_parcial | 7217 [6895; 7539] | 0.137 [0.107; 0.167] | 2308 [1934; 2681] | 0.42 [0.31; 0.53] |  |

#### n_final_2__base

| política | regret R$ [IC95] | perdedoras | drawdown R$ | podadas | supera? |
|---|---|---|---|---|---|
| asha_madura | 18373 [16864; 19882] | 0.265 [0.217; 0.313] | 7035 [6325; 7745] | 1.90 [1.78; 2.02] | não (vs greedy_parcial) |
| asha_parcial | 18757 [17086; 20428] | 0.305 [0.255; 0.355] | 7451 [6622; 8281] | 2.00 [1.87; 2.12] | não (vs greedy_parcial) |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] |  |
| greedy_madura | 9701 [9283; 10118] | 0.174 [0.140; 0.207] | 2980 [2467; 3492] | 1.12 [1.01; 1.23] |  |
| greedy_parcial | 7622 [7255; 7989] | 0.117 [0.086; 0.147] | 2178 [1756; 2600] | 0.60 [0.50; 0.70] |  |
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 513 [325; 700] | 0.24 [0.15; 0.33] |  |
| random_sh | 28401 [26419; 30383] | 0.740 [0.697; 0.783] | 14417 [13646; 15187] | 2.88 [2.73; 3.02] |  |
| sh_madura | 12216 [11637; 12794] | 0.092 [0.061; 0.124] | 3958 [3344; 4571] | 1.48 [1.37; 1.59] | não (vs greedy_parcial) |
| sh_parcial | 11509 [11038; 11979] | 0.100 [0.068; 0.132] | 4110 [3434; 4786] | 1.52 [1.41; 1.63] | não (vs greedy_parcial) |
| thompson_madura | 8295 [7935; 8656] | 0.189 [0.157; 0.221] | 2521 [2075; 2966] | 0.47 [0.39; 0.56] |  |
| thompson_parcial | 6040 [5762; 6318] | 0.161 [0.131; 0.191] | 1668 [1309; 2027] | 0.17 [0.11; 0.22] |  |

#### n_final_2__ideal_sem_saturacao

| política | regret R$ [IC95] | perdedoras | drawdown R$ | podadas | supera? |
|---|---|---|---|---|---|
| asha_madura | 35912 [30826; 40998] | 0.215 [0.170; 0.260] | 983 [720; 1245] | 1.79 [1.68; 1.91] | não (vs greedy_parcial) |
| asha_parcial | 35912 [30826; 40998] | 0.215 [0.170; 0.260] | 983 [720; 1245] | 1.79 [1.68; 1.91] | não (vs greedy_parcial) |
| equal | 56051 [50384; 61718] | 0.751 [0.735; 0.766] | 4524 [3996; 5052] | 0.00 [0.00; 0.00] |  |
| greedy_madura | 23468 [20411; 26525] | 0.048 [0.024; 0.071] | 585 [480; 691] | 1.36 [1.25; 1.47] |  |
| greedy_parcial | 23468 [20411; 26525] | 0.048 [0.024; 0.071] | 585 [480; 691] | 1.36 [1.25; 1.47] |  |
| oraculo | 0 [0; 0] | 0.015 [-0.002; 0.032] | 44 [-4; 92] | 2.29 [2.16; 2.42] |  |
| random_sh | 55993 [50134; 61853] | 0.740 [0.697; 0.783] | 6969 [6195; 7744] | 2.88 [2.73; 3.02] |  |
| sh_madura | 22964 [19919; 26009] | 0.055 [0.030; 0.080] | 587 [480; 693] | 1.39 [1.27; 1.50] | não (vs greedy_parcial) |
| sh_parcial | 22964 [19919; 26009] | 0.055 [0.030; 0.080] | 587 [480; 693] | 1.39 [1.27; 1.50] | não (vs greedy_parcial) |
| thompson_madura | 18391 [15728; 21054] | 0.049 [0.026; 0.071] | 236 [157; 315] | 0.97 [0.85; 1.09] |  |
| thompson_parcial | 18391 [15728; 21054] | 0.049 [0.026; 0.071] | 236 [157; 315] | 0.97 [0.85; 1.09] |  |

#### n_final_2__vencedoras_lentas_D3

| política | regret R$ [IC95] | perdedoras | drawdown R$ | podadas | supera? |
|---|---|---|---|---|---|
| asha_madura | 18373 [16864; 19882] | 0.265 [0.217; 0.313] | 7035 [6325; 7745] | 1.90 [1.78; 2.02] | não (vs greedy_parcial) |
| asha_parcial | 21957 [20201; 23714] | 0.623 [0.574; 0.671] | 10049 [9124; 10973] | 2.58 [2.44; 2.71] | não (vs greedy_parcial) |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] |  |
| greedy_madura | 9701 [9283; 10118] | 0.174 [0.140; 0.207] | 2980 [2467; 3492] | 1.12 [1.01; 1.23] |  |
| greedy_parcial | 7546 [7189; 7903] | 0.119 [0.088; 0.149] | 2157 [1741; 2572] | 0.53 [0.43; 0.62] |  |
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 513 [325; 700] | 0.24 [0.15; 0.33] |  |
| random_sh | 28401 [26419; 30383] | 0.740 [0.697; 0.783] | 14417 [13646; 15187] | 2.88 [2.73; 3.02] |  |
| sh_madura | 12216 [11637; 12794] | 0.092 [0.061; 0.124] | 3958 [3344; 4571] | 1.48 [1.37; 1.59] | não (vs greedy_parcial) |
| sh_parcial | 12407 [11887; 12928] | 0.233 [0.188; 0.277] | 4756 [4012; 5500] | 1.77 [1.66; 1.89] | não (vs greedy_parcial) |
| thompson_madura | 8295 [7935; 8656] | 0.189 [0.157; 0.221] | 2521 [2075; 2966] | 0.47 [0.39; 0.56] |  |
| thompson_parcial | 6704 [6378; 7030] | 0.160 [0.130; 0.190] | 1945 [1592; 2298] | 0.11 [0.06; 0.16] |  |

#### n_final_4__base

| política | regret R$ [IC95] | perdedoras | drawdown R$ | podadas | supera? |
|---|---|---|---|---|---|
| asha_madura | 12090 [11137; 13043] | 0.291 [0.254; 0.328] | 3806 [3338; 4273] | 0.69 [0.59; 0.79] | não (vs greedy_parcial) |
| asha_parcial | 10164 [9273; 11056] | 0.287 [0.251; 0.324] | 2635 [2166; 3104] | 0.69 [0.59; 0.79] | não (vs greedy_parcial) |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] |  |
| greedy_madura | 8498 [7796; 9199] | 0.250 [0.214; 0.285] | 2051 [1659; 2443] | 0.33 [0.25; 0.40] |  |
| greedy_parcial | 7556 [6887; 8226] | 0.235 [0.200; 0.270] | 1760 [1395; 2124] | 0.15 [0.10; 0.21] |  |
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 513 [325; 700] | 0.24 [0.15; 0.33] |  |
| random_sh | 23583 [21681; 25484] | 0.746 [0.717; 0.776] | 9977 [9237; 10717] | 2.47 [2.33; 2.61] |  |
| sh_madura | 10213 [9411; 11016] | 0.240 [0.204; 0.276] | 2545 [2100; 2989] | 0.46 [0.37; 0.54] | não (vs greedy_parcial) |
| sh_parcial | 9123 [8458; 9788] | 0.250 [0.214; 0.286] | 2410 [1937; 2883] | 0.49 [0.41; 0.58] | não (vs greedy_parcial) |
| thompson_madura | 7311 [6682; 7940] | 0.257 [0.224; 0.290] | 1764 [1421; 2107] | 0.04 [0.01; 0.07] |  |
| thompson_parcial | 6072 [5520; 6624] | 0.256 [0.224; 0.289] | 1345 [1018; 1672] | 0.01 [-0.00; 0.02] |  |

#### n_final_4__ideal_sem_saturacao

| política | regret R$ [IC95] | perdedoras | drawdown R$ | podadas | supera? |
|---|---|---|---|---|---|
| asha_madura | 37696 [33106; 42286] | 0.217 [0.183; 0.252] | 714 [566; 861] | 0.34 [0.27; 0.42] | não (vs greedy_parcial) |
| asha_parcial | 37696 [33106; 42286] | 0.217 [0.183; 0.252] | 714 [566; 861] | 0.34 [0.27; 0.42] | não (vs greedy_parcial) |
| equal | 56051 [50384; 61718] | 0.751 [0.735; 0.766] | 4524 [3996; 5052] | 0.00 [0.00; 0.00] |  |
| greedy_madura | 36360 [31976; 40745] | 0.189 [0.155; 0.224] | 705 [565; 846] | 0.14 [0.10; 0.19] |  |
| greedy_parcial | 36360 [31976; 40745] | 0.189 [0.155; 0.224] | 705 [565; 846] | 0.14 [0.10; 0.19] |  |
| oraculo | 0 [0; 0] | 0.015 [-0.002; 0.032] | 44 [-4; 92] | 2.29 [2.16; 2.42] |  |
| random_sh | 55777 [50010; 61545] | 0.746 [0.717; 0.776] | 5716 [5070; 6362] | 2.47 [2.33; 2.61] |  |
| sh_madura | 35821 [31469; 40174] | 0.199 [0.164; 0.234] | 663 [526; 801] | 0.23 [0.17; 0.29] | não (vs greedy_parcial) |
| sh_parcial | 35821 [31469; 40174] | 0.199 [0.164; 0.234] | 663 [526; 801] | 0.23 [0.17; 0.29] | não (vs greedy_parcial) |
| thompson_madura | 33106 [28950; 37263] | 0.183 [0.150; 0.217] | 320 [205; 435] | 0.03 [0.00; 0.05] |  |
| thompson_parcial | 33106 [28950; 37263] | 0.183 [0.150; 0.217] | 320 [205; 435] | 0.03 [0.00; 0.05] |  |

#### n_final_4__vencedoras_lentas_D3

| política | regret R$ [IC95] | perdedoras | drawdown R$ | podadas | supera? |
|---|---|---|---|---|---|
| asha_madura | 12090 [11137; 13043] | 0.291 [0.254; 0.328] | 3806 [3338; 4273] | 0.69 [0.59; 0.79] | não (vs greedy_parcial) |
| asha_parcial | 14098 [13021; 15175] | 0.596 [0.559; 0.633] | 4608 [3978; 5239] | 1.82 [1.69; 1.95] | não (vs greedy_parcial) |
| equal | 18259 [16605; 19912] | 0.751 [0.735; 0.766] | 4657 [4133; 5181] | 0.00 [0.00; 0.00] |  |
| greedy_madura | 8498 [7796; 9199] | 0.250 [0.214; 0.285] | 2051 [1659; 2443] | 0.33 [0.25; 0.40] |  |
| greedy_parcial | 7630 [6963; 8297] | 0.238 [0.203; 0.273] | 1801 [1437; 2165] | 0.12 [0.08; 0.17] |  |
| oraculo | 0 [0; 0] | 0.281 [0.240; 0.321] | 513 [325; 700] | 0.24 [0.15; 0.33] |  |
| random_sh | 23583 [21681; 25484] | 0.746 [0.717; 0.776] | 9977 [9237; 10717] | 2.47 [2.33; 2.61] |  |
| sh_madura | 10213 [9411; 11016] | 0.240 [0.204; 0.276] | 2545 [2100; 2989] | 0.46 [0.37; 0.54] | não (vs greedy_parcial) |
| sh_parcial | 10504 [9794; 11215] | 0.416 [0.380; 0.453] | 2922 [2390; 3455] | 1.10 [0.99; 1.21] | não (vs greedy_parcial) |
| thompson_madura | 7311 [6682; 7940] | 0.257 [0.224; 0.290] | 1764 [1421; 2107] | 0.04 [0.01; 0.07] |  |
| thompson_parcial | 6907 [6306; 7508] | 0.269 [0.236; 0.301] | 1619 [1295; 1943] | 0.00 [0.00; 0.00] |  |

## sensibilidade


#### bloco estacionario: 24 combinações, 21 cenários distintos (com D=0 a maturação não tem efeito; duplicatas marcadas com =)

| cenário | equal | greedy_p | sh_p | sh_m | asha_p | asha_m | Δpodadas sh p−m | supera? |
|---|---|---|---|---|---|---|---|---|
| D0__uniforme__ruido2 | 18259 | 7224 | 8424 | 8424 | 9214 | 9214 | 0.00 [0.00; 0.00] | — |
| D0__uniforme__ruido30 | 18259 | 8809 | 10497 | 10497 | 11496 | 11496 | 0.00 [0.00; 0.00] | — |
| D0__uniforme__ruido8 | 18259 | 7736 | 9050 | 9050 | 9947 | 9947 | 0.00 [0.00; 0.00] | — |
| D0__vencedoras_lentas__ruido2 | = D0__uniforme__ruido2 | | | | | | | |
| D0__vencedoras_lentas__ruido30 | = D0__uniforme__ruido30 | | | | | | | |
| D0__vencedoras_lentas__ruido8 | = D0__uniforme__ruido8 | | | | | | | |
| D1__uniforme__ruido2 | 18259 | 7075 | 8484 | 8896 | 9906 | 9084 | 0.02 [-0.03; 0.07] | — |
| D1__uniforme__ruido30 | 18259 | 8746 | 10659 | 10845 | 11748 | 11417 | 0.07 [0.01; 0.14] | — |
| D1__uniforme__ruido8 | 18259 | 7622 | 9037 | 9385 | 10751 | 9665 | 0.01 [-0.04; 0.07] | — |
| D1__vencedoras_lentas__ruido2 | 18259 | 7068 | 8550 | 8896 | 13998 | 9084 | 0.20 [0.13; 0.27] | — |
| D1__vencedoras_lentas__ruido30 | 18259 | 8759 | 11294 | 10845 | 14226 | 11417 | 0.27 [0.19; 0.35] | — |
| D1__vencedoras_lentas__ruido8 | 18259 | 7602 | 9579 | 9385 | 14073 | 9665 | 0.23 [0.16; 0.31] | — |
| D3__uniforme__ruido2 | 18259 | 7011 | 8476 | 9742 | 9396 | 11393 | 0.03 [-0.02; 0.07] | — |
| D3__uniforme__ruido30 | 18259 | 8673 | 10632 | 11573 | 11532 | 13254 | 0.07 [-0.01; 0.14] | — |
| D3__uniforme__ruido8 | 18259 | 7556 | 9123 | 10213 | 10164 | 12090 | 0.04 [-0.02; 0.10] | — |
| D3__vencedoras_lentas__ruido2 | 18259 | 7082 | 9476 | 9742 | 13727 | 11393 | 0.69 [0.59; 0.79] | — |
| D3__vencedoras_lentas__ruido30 | 18259 | 8841 | 12171 | 11573 | 14483 | 13254 | 0.52 [0.42; 0.61] | — |
| D3__vencedoras_lentas__ruido8 | 18259 | 7630 | 10504 | 10213 | 14098 | 12090 | 0.65 [0.56; 0.73] | — |
| D6__uniforme__ruido2 | 18259 | 6988 | 8452 | 10986 | 9240 | 13266 | 0.06 [0.00; 0.11] | — |
| D6__uniforme__ruido30 | 18259 | 8591 | 10577 | 12554 | 11492 | 15027 | 0.05 [-0.02; 0.12] | — |
| D6__uniforme__ruido8 | 18259 | 7461 | 9036 | 11449 | 10003 | 13818 | -0.02 [-0.08; 0.04] | — |
| D6__vencedoras_lentas__ruido2 | 18259 | 7243 | 11498 | 10986 | 15012 | 13266 | 1.41 [1.29; 1.53] | — |
| D6__vencedoras_lentas__ruido30 | 18259 | 8930 | 13501 | 12554 | 15530 | 15027 | 0.89 [0.78; 0.99] | — |
| D6__vencedoras_lentas__ruido8 | 18259 | 7742 | 12170 | 11449 | 15076 | 13818 | 1.16 [1.05; 1.26] | — |

#### bloco nao_estacionario: 24 combinações, 21 cenários distintos (com D=0 a maturação não tem efeito; duplicatas marcadas com =)

| cenário | equal | greedy_p | sh_p | sh_m | asha_p | asha_m | Δpodadas sh p−m | supera? |
|---|---|---|---|---|---|---|---|---|
| D0__uniforme__ruido2 | 18930 | 11316 | 12896 | 12896 | 13242 | 13242 | 0.00 [0.00; 0.00] | — |
| D0__uniforme__ruido30 | 18930 | 12687 | 14650 | 14650 | 15441 | 15441 | 0.00 [0.00; 0.00] | — |
| D0__uniforme__ruido8 | 18930 | 11787 | 13321 | 13321 | 13881 | 13881 | 0.00 [0.00; 0.00] | — |
| D0__vencedoras_lentas__ruido2 | = D0__uniforme__ruido2 | | | | | | | |
| D0__vencedoras_lentas__ruido30 | = D0__uniforme__ruido30 | | | | | | | |
| D0__vencedoras_lentas__ruido8 | = D0__uniforme__ruido8 | | | | | | | |
| D1__uniforme__ruido2 | 18930 | 11136 | 12994 | 13292 | 13840 | 13108 | 0.04 [-0.01; 0.09] | — |
| D1__uniforme__ruido30 | 18930 | 12653 | 14838 | 15123 | 15557 | 15282 | 0.03 [-0.03; 0.08] | — |
| D1__uniforme__ruido8 | 18930 | 11667 | 13312 | 13713 | 14667 | 13798 | 0.01 [-0.04; 0.06] | — |
| D1__vencedoras_lentas__ruido2 | 18930 | 11102 | 12870 | 13292 | 16889 | 13108 | 0.12 [0.06; 0.18] | — |
| D1__vencedoras_lentas__ruido30 | 18930 | 12682 | 15360 | 15123 | 17546 | 15282 | 0.16 [0.09; 0.23] | — |
| D1__vencedoras_lentas__ruido8 | 18930 | 11712 | 13781 | 13713 | 17303 | 13798 | 0.12 [0.06; 0.18] | — |
| D3__uniforme__ruido2 | 18930 | 10979 | 12957 | 14182 | 13511 | 15528 | 0.03 [-0.02; 0.07] | — |
| D3__uniforme__ruido30 | 18930 | 12579 | 14783 | 15932 | 15443 | 17336 | 0.02 [-0.04; 0.08] | — |
| D3__uniforme__ruido8 | 18930 | 11714 | 13414 | 14634 | 14045 | 16189 | 0.02 [-0.03; 0.07] | — |
| D3__vencedoras_lentas__ruido2 | 18930 | 11023 | 13511 | 14182 | 16520 | 15528 | 0.39 [0.30; 0.48] | — |
| D3__vencedoras_lentas__ruido30 | 18930 | 12711 | 16076 | 15932 | 17637 | 17336 | 0.29 [0.21; 0.37] | — |
| D3__vencedoras_lentas__ruido8 | 18930 | 11515 | 14393 | 14634 | 17069 | 16189 | 0.38 [0.30; 0.45] | — |
| D6__uniforme__ruido2 | 18930 | 10941 | 12933 | 15436 | 13325 | 17259 | 0.04 [-0.00; 0.08] | — |
| D6__uniforme__ruido30 | 18930 | 12402 | 14699 | 16882 | 15430 | 18909 | 0.01 [-0.05; 0.08] | — |
| D6__uniforme__ruido8 | 18930 | 11419 | 13284 | 15867 | 13961 | 17715 | -0.04 [-0.09; 0.02] | — |
| D6__vencedoras_lentas__ruido2 | 18930 | 10925 | 15140 | 15436 | 17273 | 17259 | 0.86 [0.76; 0.97] | — |
| D6__vencedoras_lentas__ruido30 | 18930 | 12637 | 16955 | 16882 | 18419 | 18909 | 0.55 [0.45; 0.64] | — |
| D6__vencedoras_lentas__ruido8 | 18930 | 11583 | 15737 | 15867 | 17593 | 17715 | 0.69 [0.60; 0.78] | — |

## diagnostico

| cenário | rung | ρ(parcial,v) | ρ(madura,v) | ρ(parcial,escala) | ρ(madura,escala) | parcial/madura rápidas | lentas | ρ(v,escala) |
|---|---|---|---|---|---|---|---|---|
| atraso_6 | rung_2ciclos | 0.74 [0.72; 0.76] | 0.74 [0.72; 0.76] | 0.67 [0.65; 0.69] | 0.67 [0.65; 0.70] | 0.54 [0.54; 0.54] | — | 0.86 [0.85; 0.87] |
| atraso_6 | rung_6ciclos | 0.86 [0.85; 0.88] | 0.87 [0.86; 0.88] | 0.78 [0.76; 0.80] | 0.78 [0.77; 0.80] | 0.71 [0.71; 0.71] | — | 0.86 [0.85; 0.87] |
| base | rung_2ciclos | 0.74 [0.72; 0.76] | 0.74 [0.72; 0.76] | 0.67 [0.64; 0.69] | 0.67 [0.65; 0.70] | 0.58 [0.58; 0.59] | — | 0.86 [0.85; 0.87] |
| base | rung_6ciclos | 0.86 [0.85; 0.88] | 0.87 [0.86; 0.88] | 0.78 [0.76; 0.80] | 0.78 [0.77; 0.80] | 0.83 [0.83; 0.84] | — | 0.86 [0.85; 0.87] |
| ideal_sem_saturacao | rung_2ciclos | 0.89 [0.88; 0.90] | 0.89 [0.88; 0.90] | 0.89 [0.88; 0.90] | 0.89 [0.88; 0.90] | 1.00 [1.00; 1.00] | — | 1.00 [1.00; 1.00] |
| ideal_sem_saturacao | rung_6ciclos | 0.95 [0.94; 0.95] | 0.95 [0.94; 0.95] | 0.95 [0.94; 0.95] | 0.95 [0.94; 0.95] | 1.00 [1.00; 1.00] | — | 1.00 [1.00; 1.00] |
| interferencia | rung_2ciclos | 0.71 [0.69; 0.73] | 0.71 [0.69; 0.73] | 0.65 [0.62; 0.67] | 0.65 [0.62; 0.67] | 0.58 [0.58; 0.59] | — | 0.86 [0.85; 0.87] |
| interferencia | rung_6ciclos | 0.84 [0.83; 0.86] | 0.85 [0.83; 0.86] | 0.76 [0.74; 0.78] | 0.76 [0.75; 0.78] | 0.83 [0.83; 0.84] | — | 0.86 [0.85; 0.87] |
| ruido_baixo | rung_2ciclos | 0.89 [0.88; 0.90] | 0.89 [0.88; 0.90] | 0.79 [0.78; 0.81] | 0.80 [0.78; 0.81] | 0.58 [0.58; 0.58] | — | 0.86 [0.85; 0.87] |
| ruido_baixo | rung_6ciclos | 0.95 [0.94; 0.95] | 0.95 [0.94; 0.95] | 0.84 [0.83; 0.85] | 0.84 [0.83; 0.86] | 0.83 [0.83; 0.83] | — | 0.86 [0.85; 0.87] |
| sem_atraso | rung_2ciclos | 0.74 [0.72; 0.76] | 0.74 [0.72; 0.76] | 0.67 [0.65; 0.70] | 0.67 [0.65; 0.70] | 1.00 [1.00; 1.00] | — | 0.86 [0.85; 0.87] |
| sem_atraso | rung_6ciclos | 0.87 [0.86; 0.88] | 0.87 [0.86; 0.88] | 0.78 [0.77; 0.80] | 0.78 [0.77; 0.80] | 1.00 [1.00; 1.00] | — | 0.86 [0.85; 0.87] |
| vencedoras_lentas_D3 | rung_2ciclos | 0.45 [0.42; 0.48] | 0.74 [0.72; 0.76] | 0.42 [0.39; 0.45] | 0.67 [0.65; 0.70] | 0.58 [0.58; 0.59] | 0.25 [0.25; 0.25] | 0.86 [0.85; 0.87] |
| vencedoras_lentas_D3 | rung_6ciclos | 0.84 [0.82; 0.85] | 0.87 [0.86; 0.88] | 0.76 [0.74; 0.78] | 0.78 [0.77; 0.80] | 0.83 [0.83; 0.84] | 0.70 [0.69; 0.70] | 0.86 [0.85; 0.87] |
| vencedoras_lentas_D6 | rung_2ciclos | 0.33 [0.29; 0.37] | 0.74 [0.72; 0.76] | 0.32 [0.28; 0.35] | 0.67 [0.65; 0.70] | 0.54 [0.54; 0.54] | 0.18 [0.17; 0.18] | 0.86 [0.85; 0.87] |
| vencedoras_lentas_D6 | rung_6ciclos | 0.78 [0.76; 0.80] | 0.87 [0.86; 0.88] | 0.71 [0.69; 0.73] | 0.78 [0.77; 0.80] | 0.71 [0.71; 0.71] | 0.47 [0.47; 0.48] | 0.86 [0.85; 0.87] |

## pos_registro


### PÓS-REGISTRO / EXPLORATÓRIO — diferença-em-diferenças pareada (Δ = candidato − greedy_parcial)

| cenário | sh_parcial | sh_madura | asha_parcial | asha_madura |
|---|---|---|---|---|
| base | 1567 [1382; 1752] | 2657 [2454; 2861] | 2608 [2160; 3056] | 4534 [4150; 4917] |
| ideal_sem_saturacao | -539 [-611; -467] | -539 [-611; -467] | 1336 [773; 1898] | 1336 [773; 1898] |
| interferencia | 1347 [1126; 1568] | 2586 [2360; 2811] | 1971 [1593; 2350] | 3640 [3264; 4017] |
| nao_estacionario | 1700 [1444; 1956] | 2919 [2685; 3153] | 2331 [1884; 2777] | 4474 [4038; 4911] |
| ruido_alto | 1959 [1710; 2208] | 2900 [2630; 3171] | 2859 [2388; 3330] | 4582 [4185; 4978] |
| ruido_baixo | 1465 [1296; 1633] | 2731 [2538; 2923] | 2384 [1983; 2785] | 4382 [4043; 4720] |
| ruido_baixo_sem_atraso | 1200 [1050; 1350] | 1200 [1050; 1350] | 1990 [1603; 2377] | 1990 [1603; 2377] |
| sem_atraso | 1314 [1141; 1487] | 1314 [1141; 1487] | 2211 [1760; 2662] | 2211 [1760; 2662] |
| sem_saturacao_D3 | -227 [-360; -95] | 2735 [2505; 2965] | 1958 [1298; 2617] | 2224 [1846; 2602] |
| vencedoras_lentas_D3 | 2874 [2590; 3159] | 2583 [2374; 2792] | 6468 [5698; 7238] | 4460 [4070; 4849] |

| DiD (alvo − ref) | fator | sh_parcial | sh_madura | asha_parcial | asha_madura |
|---|---|---|---|---|---|
| base__menos__ruido_baixo | ruído base vs baixo | 102 [-57; 261] | -74 [-202; 54] | 224 [-24; 473] | 152 [-37; 341] |
| base__menos__sem_atraso | atraso D=3 (uniforme) | 253 [112; 393] | 1343 [1105; 1582] | 398 [195; 600] | 2323 [1873; 2773] |
| base__menos__sem_saturacao_D3 | saturação (cap×2,5 vs ×100), D=3 | 1794 [1620; 1968] | -78 [-262; 107] | 651 [321; 980] | 2310 [2051; 2568] |
| interferencia__menos__base | interferência rho=0,5 | -220 [-429; -10] | -72 [-247; 103] | -637 [-948; -325] | -893 [-1147; -639] |
| nao_estacionario__menos__base | não estacionariedade | 133 [-50; 316] | 262 [138; 386] | -278 [-614; 58] | -59 [-319; 201] |
| ruido_alto__menos__base | ruído alto | 392 [123; 662] | 243 [16; 471] | 251 [-124; 626] | 48 [-257; 353] |
| ruido_baixo_sem_atraso__menos__ideal_sem_saturacao | saturação, D=0 ruído baixo | 1739 [1590; 1888] | 1739 [1590; 1888] | 655 [389; 920] | 655 [389; 920] |
| vencedoras_lentas_D3__menos__base | maturação heterogênea (vencedoras lentas) | 1308 [1034; 1581] | -74 [-122; -26] | 3860 [3068; 4651] | -74 [-122; -26] |

DiD > 0: o fator piora o candidato MAIS que o greedy; < 0: favorece o candidato.

### PÓS-REGISTRO / EXPLORATÓRIO — saturação (cap × beta × maturação, D=3, 200 seeds)

| cenário | melhor baseline | greedy_p | sh_p | asha_p | Δpareado sh_p − baseline | supera (pré-reg.) | supera (excesso vs oráculo) |
|---|---|---|---|---|---|---|---|
| cap100__beta0.25__uniforme__D3 | greedy_parcial | 36826 | 36599 | 38784 | -227 [-360; -95] | — | — |
| cap100__beta0.25__vencedoras_lentas__D3 | greedy_parcial | 37238 | 38586 | 43994 | 1347 [1084; 1610] | — | — |
| cap100__beta0.6__uniforme__D3 | greedy_parcial | 36826 | 36599 | 38784 | -227 [-360; -95] | — | — |
| cap100__beta0.6__vencedoras_lentas__D3 | greedy_parcial | 37238 | 38586 | 43994 | 1347 [1084; 1610] | — | — |
| cap10__beta0.25__uniforme__D3 | greedy_parcial | 25144 | 24960 | 27126 | -184 [-318; -50] | — | — |
| cap10__beta0.25__vencedoras_lentas__D3 | greedy_parcial | 25550 | 26923 | 32276 | 1373 [1109; 1637] | — | — |
| cap10__beta0.6__uniforme__D3 | greedy_parcial | 27900 | 27693 | 29868 | -207 [-339; -75] | — | — |
| cap10__beta0.6__vencedoras_lentas__D3 | greedy_parcial | 28308 | 29668 | 35045 | 1359 [1096; 1622] | — | — |
| cap2.5__beta0.25__uniforme__D3 | greedy_parcial | 7556 | 9123 | 10164 | 1567 [1382; 1752] | — | — |
| cap2.5__beta0.25__vencedoras_lentas__D3 | greedy_parcial | 7630 | 10504 | 14098 | 2874 [2590; 3159] | — | — |
| cap2.5__beta0.6__uniforme__D3 | greedy_parcial | 17170 | 17693 | 19349 | 524 [385; 662] | — | — |
| cap2.5__beta0.6__vencedoras_lentas__D3 | greedy_parcial | 17372 | 19316 | 23846 | 1944 [1691; 2198] | — | — |
| cap4__beta0.25__uniforme__D3 | greedy_parcial | 10634 | 11286 | 12892 | 652 [481; 823] | — | — |
| cap4__beta0.25__vencedoras_lentas__D3 | greedy_parcial | 10866 | 13035 | 17424 | 2169 [1896; 2443] | — | — |
| cap4__beta0.6__uniforme__D3 | greedy_parcial | 18515 | 18650 | 20547 | 135 [-3; 273] | — | — |
| cap4__beta0.6__vencedoras_lentas__D3 | greedy_parcial | 18816 | 20504 | 25427 | 1688 [1433; 1944] | — | — |
| cap6__beta0.25__uniforme__D3 | greedy_parcial | 16112 | 16169 | 18175 | 57 [-89; 203] | — | — |
| cap6__beta0.25__vencedoras_lentas__D3 | greedy_parcial | 16468 | 18056 | 23155 | 1588 [1322; 1854] | — | — |
| cap6__beta0.6__uniforme__D3 | greedy_parcial | 21878 | 21775 | 23862 | -104 [-237; 30] | — | — |
| cap6__beta0.6__vencedoras_lentas__D3 | greedy_parcial | 22257 | 23710 | 28950 | 1453 [1193; 1713] | — | — |
