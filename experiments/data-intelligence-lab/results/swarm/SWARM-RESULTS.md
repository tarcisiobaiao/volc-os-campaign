# Swarm Lab — resultados (worker E, Fase 5)

**Natureza:** simulação sintética com seed. Nenhuma célula é campanha real, nenhum
parâmetro vem de dado real (os dados reais só deram forma ao gerador), nada aqui é
"validado". O código não tem caminho para rede, Google Ads, Supabase ou mutação
(teste `test_modulo_swarm_nao_tem_caminho_para_rede_ou_mutacao_real`).

## Veredito

> **"ASHA/SH supera random, equal e greedy sem aumentar falsos vencedores ou drawdown?" → NÃO.**

Pela regra pré-registrada (`PRE-REGISTRO.md`, escrito antes dos grids; o sha256
está no manifesto de cada JSON), nenhum dos quatro candidatos (`sh_parcial`,
`sh_madura`, `asha_parcial`, `asha_madura`) supera o melhor baseline simples em
nenhum dos 12 cenários do grid principal, nos 48 cenários do grid de
sensibilidade, nem em nenhuma das 28 variantes de eta/degrau/unidade/n_final. Em
todos os casos o melhor baseline foi o **greedy conservador com receita parcial**.

Única ressalva (fora da regra pré-registrada, que exige ICs marginais sem
sobreposição): no cenário **ideal** — sem saturação de escala, sem atraso e com
ruído baixo — o SH tem regret menor que o greedy na diferença **pareada** por seed
(−R$539 [−611; −467] com n_final=4; até −R$2.029 com degraus de 20 cliques), ou
seja 1,5–5% do regret. Os ICs marginais se cruzam, então não conta como "supera".
E nesse mesmo cenário o Thompson (extensão) é melhor que os dois.

Resumo: **SH só ganha (marginalmente, no pareado) quando o problema é
"identificação do melhor braço" puro — estacionário, independente, sem atraso,
sem saturação. Cada desvio dessas condições que o dado real do VOLC tem (receita
com atraso, saturação, não estacionariedade, interferência) piora SH/ASHA mais do
que piora o greedy.**

## Arquivos

| arquivo | o quê |
|---|---|
| `src/volc_dil/swarm/cenario.py` | gerador de cenários (seed → cenário determinístico) |
| `src/volc_dil/swarm/simulador.py` | ciclos, validação de orçamento, receita reportada (maturação), métricas por execução |
| `src/volc_dil/swarm/politicas.py` | equal, greedy, SH (+random com o mesmo cronograma), ASHA, Thompson top-n, oráculo MILP |
| `src/volc_dil/swarm/experimento.py` | Monte Carlo pareado, IC, critério pré-registrado |
| `src/volc_dil/swarm/diagnostico.py` | premissas do ASHA (correlação baixa→alta fidelidade) |
| `src/volc_dil/swarm/regras.py` | regra de parada por rung igual à do Optuna (conferida 60/60) |
| `scripts/swarm_grid.py` | grids `principal`, `parametros`, `sensibilidade --bloco ...`, `diagnostico` |
| `scripts/swarm_tabelas.py` | imprime as tabelas deste relatório a partir dos JSON |
| `scripts/swarm_crosscheck_optuna.py` | sonda isolada contra o Optuna (não roda no venv do lab) |
| `results/swarm/PRE-REGISTRO.md` | critério e hipóteses escritos antes dos grids |
| `results/swarm/swarm_{principal,parametros,diagnostico,sensibilidade_*}.json` | resultados determinísticos com manifesto (seed, parâmetros, versões, sha256 das fontes e do pré-registro, fingerprint) |
| `results/swarm/swarm_custo_*.json` | tempo de parede (não determinístico, separado de propósito) |
| `results/swarm/swarm_crosscheck_optuna.json` | conferência contra optuna 5.0.0 |
| `tests/data-intelligence/test_swarm.py` | 24 contraprovas, 2,5 s |

Comandos (da raiz do repo, `OMP_NUM_THREADS=2`, um processo por vez):

```bash
PY=experiments/data-intelligence-lab/.venv/bin/python
$PY experiments/data-intelligence-lab/scripts/swarm_grid.py --grid principal        # ~97 s
$PY experiments/data-intelligence-lab/scripts/swarm_grid.py --grid parametros       # ~123 s
$PY experiments/data-intelligence-lab/scripts/swarm_grid.py --grid diagnostico      # ~7 s
$PY experiments/data-intelligence-lab/scripts/swarm_grid.py --grid sensibilidade --bloco estacionario      # ~140 s
$PY experiments/data-intelligence-lab/scripts/swarm_grid.py --grid sensibilidade --bloco nao_estacionario  # ~159 s
$PY experiments/data-intelligence-lab/scripts/swarm_tabelas.py principal|parametros|sensibilidade|diagnostico
$PY -m pytest tests/data-intelligence/test_swarm.py -q
```

Seeds dos grids: `1_000_000 .. 1_000_199` (200 por cenário), disjuntas do piloto
de depuração (0..39), divulgado no pré-registro.

## Modelo (resumo; detalhes nas docstrings)

- K=16 células sintéticas (rótulos canal × ângulo × objetivo × device), T=30 ciclos,
  orçamento fixo R$960/ciclo, mínimo R$10 por célula ativa (ou 0 = podada).
- Valor verdadeiro `v_k` = receita por R$ (margem = v−1), log-t com cauda: maioria
  < 1, ~25% vencedoras. Saturação: acima de `cap_k` cada R$ rende só 25%.
- Receita realizada: Poisson de eventos monetizados × Gamma, arredondada ao
  **centavo** (zero-inflada em gasto baixo). Ruído por números aleatórios comuns
  (mesmo acaso para todas as políticas na mesma seed).
- Maturação: do ciclo t, na idade a, reporta-se `phi0 + (1−phi0)·min(1, a/D)` da
  receita final. `uniforme` (phi0=0,5 para todas), `por_canal` (metade dos canais
  phi0=0,1) e `vencedoras_lentas` (vencedoras phi0=0,1 — o caso adversarial).
- Não estacionariedade: em T/2 a melhor cai para 0,6× e uma perdedora assume o
  valor antigo da melhor. Interferência: receita × (1 − rho·gasto das outras do
  mesmo canal / B).
- Oráculo: MILP exato por regime (scipy HiGHS), conferido contra busca exaustiva;
  com interferência é aproximado (ignora canibalização) — documentado.
- **Fronteira de dinheiro**: alocação, gasto, receita final e reportada são
  `np.int64` em micros; o validador rejeita float, soma ≠ orçamento, valor
  negativo e célula ativa abaixo do mínimo. Valor esperado (float64) é só métrica
  de simulação (regret), nunca registro.

Políticas (n_final/n_top = 4, degraus (60, 180) cliques, eta=2, ASHA 8 slots):
`equal`; `random_sh` (cronograma do SH, promoção aleatória — isola o valor da
informação); `greedy_{parcial,madura}` (janela 3 ciclos, depois move 30% por ciclo
rumo às top-4 estimadas — o teto de variação); `sh_{parcial,madura}`;
`asha_{parcial,madura}` (variante de promoção do artigo; produção = n_final
melhores entre n_final·eta que completam o último rung); `thompson_{parcial,madura}`
(extensão, top-n gaussiano); `oraculo`. `madura` usa só linhas com idade ≥ D.

## Tabela principal — regret (R$, soma de 30 ciclos; média [IC95 MC], n=200)

| cenário | melhor baseline (regret) | sh_parcial | sh_madura | asha_parcial | asha_madura | thompson_parcial (ext.) | Δ pareado sh_parcial − baseline |
|---|---|---|---|---|---|---|---|
| base (D=3 uniforme) | greedy_parcial: 7556 [6887; 8226] | 9123 [8458; 9788] | 10213 [9411; 11016] | 10164 [9273; 11056] | 12090 [11137; 13043] | 6072 [5520; 6624] | 1567 [1382; 1752] |
| sem_atraso | greedy_parcial: 7736 [7069; 8404] | 9050 [8382; 9719] | 9050 [8382; 9719] | 9947 [9049; 10845] | 9947 [9049; 10845] | 5961 [5424; 6499] | 1314 [1141; 1487] |
| atraso_6 | greedy_parcial: 7461 [6792; 8130] | 9036 [8364; 9708] | 11449 [10538; 12360] | 10003 [9111; 10895] | 13818 [12810; 14826] | 6086 [5531; 6642] | 1575 [1391; 1759] |
| vencedoras_lentas_D3 | greedy_parcial: 7630 [6963; 8297] | 10504 [9794; 11215] | 10213 [9411; 11016] | 14098 [13021; 15175] | 12090 [11137; 13043] | 6907 [6306; 7508] | 2874 [2590; 3159] |
| vencedoras_lentas_D6 | greedy_parcial: 7742 [7072; 8412] | 12170 [11432; 12907] | 11449 [10538; 12360] | 15076 [13992; 16160] | 13818 [12810; 14826] | 7322 [6710; 7934] | 4428 [4091; 4765] |
| maturacao_por_canal_D3 | greedy_parcial: 7512 [6842; 8183] | 9591 [8899; 10282] | 10213 [9411; 11016] | 11367 [10499; 12236] | 12090 [11137; 13043] | 6477 [5888; 7065] | 2078 [1842; 2314] |
| ruido_baixo | greedy_parcial: 7011 [6341; 7682] | 8476 [7808; 9145] | 9742 [8943; 10542] | 9396 [8540; 10251] | 11393 [10479; 12307] | 5499 [4943; 6055] | 1465 [1296; 1633] |
| ruido_alto | greedy_parcial: 8673 [7993; 9353] | 10632 [9891; 11373] | 11573 [10746; 12401] | 11532 [10656; 12408] | 13254 [12325; 14184] | 7375 [6798; 7951] | 1959 [1710; 2208] |
| nao_estacionario | greedy_parcial: 11714 [10631; 12798] | 13414 [12368; 14460] | 14634 [13441; 15826] | 14045 [12858; 15232] | 16189 [14894; 17484] | 7815 [7196; 8434] | 1700 [1444; 1956] |
| interferencia (rho=0,5) | greedy_parcial: 7498 [6478; 8518] | 8845 [7796; 9894] | 10083 [8942; 11224] | 9469 [8352; 10586] | 11138 [9882; 12394] | 6196 [5276; 7116] | 1347 [1126; 1568] |
| ideal_sem_saturacao | greedy_parcial: 36360 [31976; 40745] | 35821 [31469; 40174] | 35821 [31469; 40174] | 37696 [33106; 42286] | 37696 [33106; 42286] | 33106 [28950; 37263] | **−539 [−611; −467]** |
| adverso | greedy_parcial: 11617 [10425; 12810] | 14944 [13628; 16260] | 15337 [13827; 16847] | 16161 [14710; 17612] | 16376 [14879; 17872] | 9511 [8626; 10395] | 3327 [2838; 3815] |

Referências: `equal` regret ≈ 18.259 (base); `random_sh` ≈ 23.583 (pior que equal:
concentrar em células escolhidas ao acaso estoura a saturação). No cenário ideal o
regret absoluto é alto para todos porque n_final=4 enquanto o oráculo concentra
tudo na melhor (HHI=1); com n_final=1 o SH cai para 9.035 e o greedy para 9.321
(ICs se cruzam; pareado −286 [−429; −144]); Thompson 2.162.

### Falsos vencedores, drawdown, poda (média [IC95])

| cenário | política | orç. em perdedoras (5 últimos ciclos) | drawdown R$ | top-k podadas | falso venc./promovida |
|---|---|---|---|---|---|
| base | greedy_parcial | 0.23 [0.20; 0.27] | 1760 [1395; 2124] | 0.15 [0.10; 0.21] | 0.33 [0.29; 0.36] |
| base | sh_parcial | 0.25 [0.21; 0.29] | 2410 [1937; 2883] | 0.49 [0.41; 0.58] | 0.30 [0.27; 0.34] |
| base | sh_madura | 0.24 [0.20; 0.28] | 2545 [2100; 2989] | 0.46 [0.37; 0.54] | 0.29 [0.26; 0.33] |
| base | asha_parcial | 0.29 [0.25; 0.32] | 2635 [2166; 3104] | 0.69 [0.59; 0.79] | 0.35 [0.32; 0.39] |
| base | asha_madura | 0.29 [0.25; 0.33] | 3806 [3338; 4273] | 0.69 [0.59; 0.79] | 0.35 [0.32; 0.39] |
| vencedoras_lentas_D6 | greedy_parcial | 0.25 [0.21; 0.28] | 1841 [1482; 2199] | 0.09 [0.05; 0.13] | 0.34 [0.31; 0.37] |
| vencedoras_lentas_D6 | sh_parcial | **0.58** [0.55; 0.61] | 3658 [3066; 4250] | **1.67** [1.55; 1.78] | 0.60 [0.57; 0.63] |
| vencedoras_lentas_D6 | sh_madura | 0.25 [0.21; 0.28] | 2886 [2433; 3338] | 0.51 [0.43; 0.59] | 0.31 [0.28; 0.34] |
| vencedoras_lentas_D6 | asha_parcial | **0.71** [0.67; 0.74] | 5072 [4415; 5728] | **2.17** [2.05; 2.30] | 0.72 [0.70; 0.75] |
| vencedoras_lentas_D6 | asha_madura | 0.28 [0.25; 0.32] | 4343 [3856; 4830] | 0.64 [0.54; 0.73] | 0.34 [0.31; 0.37] |
| nao_estacionario | greedy_parcial | 0.26 [0.22; 0.30] | 2152 [1741; 2564] | 0.94 [0.87; 1.00] | 0.44 [0.41; 0.47] |
| nao_estacionario | sh_parcial | 0.30 [0.25; 0.34] | 3049 [2516; 3582] | 1.25 [1.18; 1.33] | 0.43 [0.40; 0.47] |
| nao_estacionario | asha_madura | 0.33 [0.29; 0.37] | 4330 [3813; 4847] | 1.36 [1.27; 1.46] | 0.46 [0.43; 0.49] |

Leitura: no base, o SH não aumenta o orçamento em perdedoras (dentro do IC do
greedy), mas **aumenta o drawdown** e poda 3× mais células do top-k. O ASHA falha
nas três condições. HHI (concentração) médio: greedy 0,19, SH 0,22, ASHA 0,22–0,27,
oráculo 0,30; turnover: SH 0,034, greedy 0,07, Thompson 0,12, asha_madura 0,26.

## Efeito da decisão com receita madura vs parcial (pareado, Δ = parcial − madura)

| cenário | SH Δregret | SH Δpodadas top-k | ASHA Δregret | ASHA Δpodadas |
|---|---|---|---|---|
| base (uniforme D=3) | −1090 [−1345; −836] | 0.04 [−0.02; 0.10] | −1925 [−2381; −1469] | 0.00 [−0.10; 0.10] |
| atraso_6 (uniforme) | −2413 [−2788; −2038] | −0.02 [−0.08; 0.04] | −3815 [−4318; −3312] | −0.01 [−0.10; 0.08] |
| maturacao_por_canal_D3 | −623 [−920; −326] | 0.18 [0.10; 0.27] | −722 [−1260; −185] | 0.30 [0.19; 0.42] |
| vencedoras_lentas_D3 | 291 [−42; 625] | **0.65 [0.56; 0.73]** | 2008 [1202; 2814] | **1.13 [1.00; 1.26]** |
| vencedoras_lentas_D6 | 721 [242; 1200] | **1.16 [1.05; 1.26]** | 1258 [495; 2021] | **1.54 [1.42; 1.66]** |

- Com maturação **uniforme**, decidir com receita parcial é *melhor* (H2 confirmada):
  todas as vivas gastaram nos mesmos ciclos, o fator de maturação é comum e a
  ordenação se preserva; esperar a receita madura só custa tempo de exploração.
  Mas o nível absoluto engana: no rung de 2 ciclos a receita parcial é 58% da
  madura (diagnóstico) — qualquer regra com limiar absoluto (ex.: "contribuição
  ≤ 0 → corta") seria enganada mesmo com maturação uniforme.
- Com maturação **heterogênea** (vencedoras lentas), a decisão parcial poda
  vencedoras (H1 confirmada) e o efeito cresce com D; o ASHA sofre mais (H3
  confirmada só no caso heterogêneo; com maturação uniforme não há diferença de
  poda no ASHA).
- O greedy é quase imune ao atraso (Δpodadas ≤ 0 em todos), porque usa o
  acumulado, em que as linhas imaturas são minoria.

## Sensibilidade (48 cenários, 200 seeds; regret médio R$)

Grade D ∈ {0,1,3,6} × maturação {uniforme, vencedoras_lentas} × ruído
(valor/evento R$2/8/30) × não estacionariedade {não, sim}. **Nenhum candidato supera
em nenhum dos 48.** Recortes (estacionário, ruído R$8):

| D | maturação | equal | greedy_p | sh_p | sh_m | asha_p | asha_m | Δpodadas SH p−m |
|---|---|---|---|---|---|---|---|---|
| 0 | — | 18259 | 7736 | 9050 | 9050 | 9947 | 9947 | 0 |
| 1 | uniforme | 18259 | 7622 | 9037 | 9385 | 10751 | 9665 | 0.01 [−0.04; 0.07] |
| 1 | vencedoras_lentas | 18259 | 7602 | 9579 | 9385 | 14073 | 9665 | 0.23 [0.16; 0.31] |
| 3 | uniforme | 18259 | 7556 | 9123 | 10213 | 10164 | 12090 | 0.04 [−0.02; 0.10] |
| 3 | vencedoras_lentas | 18259 | 7630 | 10504 | 10213 | 14098 | 12090 | 0.65 [0.56; 0.73] |
| 6 | uniforme | 18259 | 7461 | 9036 | 11449 | 10003 | 13818 | −0.02 [−0.08; 0.04] |
| 6 | vencedoras_lentas | 18259 | 7742 | 12170 | 11449 | 15076 | 13818 | 1.16 [1.05; 1.26] |

Ruído alto (R$30/evento) aumenta o regret de todos (~+15–20%) sem mudar a ordem;
não estacionariedade soma ~R$3–5 mil a todas as políticas que comprometem, e o
SH/ASHA (que encerram a exploração cedo e não revisitam) não se recuperam melhor
que o greedy. Tabela completa: `swarm_tabelas.py sensibilidade`.

## Grid de parâmetros de SH/ASHA (base, vencedoras_lentas_D3, ideal)

eta ∈ {2,3} × primeiro degrau ∈ {20, 60, 150} cliques × {parcial, madura}, mais
unidade gasto (R$120/R$360) e n_final ∈ {1,2,4}: **nenhuma das 28 variantes supera**
em nenhum dos 3 cenários. Melhor SH no base: `sh_e3_r60_cliques_parcial` 9.044
[8.357; 9.732] vs greedy 7.556 [6.887; 8.226]. Degrau curto (20 cliques) com
receita parcial e vencedoras lentas é o pior caso (SH 14.838–16.307; ASHA até
19.162, pior que equal). Diferença pareada favorável ao SH/ASHA aparece **apenas**
no cenário ideal (16 variantes, −R$539 a −R$2.029), nunca nos outros dois.

## Validade do mapeamento ASHA ("célula = trial, gasto = fidelidade")

ASHA assume (a) avaliação intermediária informativa e monotônica sobre o valor
final e (b) trials independentes e estacionários. Medido (`swarm_diagnostico.json`,
alocação equal, Spearman sobre 16 células, 200 seeds):

| cenário | rung | ρ(parcial, v) | ρ(madura, v) | ρ(madura, valor em escala) | parcial/madura (lentas) |
|---|---|---|---|---|---|
| ideal | 2 ciclos | 0.89 | 0.89 | 0.89 | — |
| base | 2 ciclos | 0.74 | 0.74 | 0.67 | — (rápidas 0.58) |
| base | 6 ciclos | 0.86 | 0.87 | 0.78 | — |
| vencedoras_lentas_D3 | 2 ciclos | **0.45** | 0.74 | 0.67 | 0.25 |
| vencedoras_lentas_D6 | 2 ciclos | **0.33** | 0.74 | 0.67 | 0.18 |
| interferencia | 2 ciclos | 0.71 | 0.71 | 0.65 | — |

Conclusão sobre o mapeamento — **válido só em parte**:

1. **Válido** como identificação do melhor braço sob amostragem i.i.d. (SH vem de
   Karnin et al. 2013 para bandits): sem atraso, sem saturação e estacionário, mais
   gasto = mais amostras da mesma quantidade, a correlação sobe com a fidelidade
   (0,89 → 0,95) e o SH funciona (acha a melhor com ruído zero; teste).
2. **Quebra com receita que matura com atraso**: a "curva de aprendizado" deixa de
   ser monotônica no tempo — o mesmo dado vale mais depois (fator 0,58 → 1). Com
   maturação heterogênea, o rung baixo ordena errado (ρ 0,74 → 0,33). Esperar a
   maturação restaura a ordenação, mas cada rung passa a custar +D ciclos, e no
   ASHA o trial fica pendente sem orçamento — a assincronia não paga a espera.
3. **Quebra com saturação**: a baixa fidelidade (gasto pequeno) mede v, mas o que
   importa na produção é o valor por R$ na escala (ρ 0,74 com v vs 0,67 com
   escala; ρ(v, escala)=0,86). Promover e escalar estoura capacidade; por isso
   `random_sh` é pior que `equal`.
4. **Quebra com interferência**: o valor de um trial depende de quem roda junto
   (mesmo canal); a premissa de independência falha (ρ cai, e o oráculo vira
   aproximado).
5. **Quebra com não estacionariedade**: o ASHA compara trials avaliados em
   regimes diferentes; SH/ASHA encerram a exploração e não revisitam.
6. A regra de corte por rung foi conferida contra `optuna.pruners.SuccessiveHalvingPruner`
   (optuna 5.0.0): 60/60 sequências idênticas. Nota: o Optuna implementa a variante de
   **parada** (decide na chegada ao rung, sem retomar); a política `ASHA` deste lab usa a
   variante de **promoção** do artigo. Hyperband não foi implementado como política
   separada — o seu papel (proteger contra escolha ruim do primeiro degrau) foi coberto
   pelo grid de degraus, e nenhum degrau salvou o SH/ASHA.

## Contraprovas (tests/data-intelligence/test_swarm.py — 24 passam em 2,5 s)

- mesma seed → mesmo cenário e mesmas métricas (todas as políticas); seed diferente → outro cenário;
- oráculo tem regret 0; sem interferência nenhuma política bate o oráculo (regret ≥ −1e−3);
  MILP do oráculo ≥ busca exaustiva em grade de R$10 (K=4);
- nenhuma política aloca acima/abaixo do orçamento total nem abaixo do mínimo (5 cenários
  × 3 seeds × 10 políticas, incluindo K=32 e mínimo R$25); validador rejeita float, soma
  errada, negativo, abaixo do mínimo; `inteirizar` em 300 casos aleatórios;
- dinheiro: orçamento float é rejeitado; receita é múltiplo de centavo em int64; reportada ≤ final;
- SH com eta e degraus conhecidos poda o número certo (16→8→4→2; 16→6→2; 16→8→4; 16→4→1);
- sem ruído e sem atraso o SH acha a melhor (≥19/20, nunca >1% abaixo);
- **atraso forte (D=6) + vencedoras lentas: SH parcial poda mais top-k que SH madura (IC > 0)**;
- controle inverso: maturação uniforme → efeito ausente (IC inclui ≤ 0);
- D=0 → parcial ≡ madura (SH, ASHA, greedy); random usa o mesmo cronograma do SH;
- ASHA respeita slots e entrega ≤ n_final; sem ruído acha a melhor em ≥12/20 (promove
  com poucos concluídos — erra mesmo sem ruído);
- regra de parada = Optuna em caso feito à mão; módulo sem import de rede/subprocess.

## Custo computacional

Um processo, `OMP_NUM_THREADS=2`, Mac compartilhado. Por simulação de 30 ciclos:
SH/random ~2,4–2,7 ms, ASHA ~2,8–3,2 ms, equal/greedy ~3,0–3,3 ms (dominado pelo
simulador), Thompson ~4,5–4,9 ms, oráculo MILP ~6–11 ms. Parede total dos grids:
~526 s (≈ 154 mil simulações). Testes: 2,5 s. Custo de decisão é irrelevante perto
do custo de informação (ciclos de gasto).

## Separação de afirmações

**Demonstrado (em simulação, com estas premissas):**
- SH/ASHA não superam o greedy conservador em nenhum dos 12 + 48 cenários nem nas
  28 variantes de parâmetros, pela regra pré-registrada;
- decidir com receita parcial, quando as vencedoras maturam mais devagar, faz o SH
  podar 0,65 (D=3) a 1,16 (D=6) célula a mais do top-4 e o ASHA 1,13 a 1,54;
- com maturação uniforme, receita parcial não piora a ordenação do SH e esperar a
  madura custa R$1–2,4 mil de regret;
- `random_sh` é pior que `equal`: concentrar sem informação é pior que não concentrar;
- Thompson top-n (extensão) teve o menor regret de todas as políticas não-oráculo em
  todos os 12 cenários do grid principal.

**Inferido:**
- a vantagem do greedy vem de não comprometer: ele continua realocando com o acumulado
  (que é majoritariamente maduro), enquanto SH/ASHA cortam cedo e não revisitam;
- num ambiente com atraso D+3 e decisão diária (cooldown de 24 h), SH em degraus
  intra-dia (15 min/2 h) estaria no regime D ≫ duração do rung, onde a receita
  parcial é quase só o fator de maturação — pior que os casos testados.

**Hipótese (não testada aqui):**
- Thompson/LinTS bem calibrado poderia ser o candidato a estudar; mas o ganho depende
  de prior e variância que não estimamos sobre dado real, e o ledger do VOLC não grava
  probabilidade de ação (não há OPE possível hoje — relatório B, 14/10).

**Não testado:**
- `atraso_assumido` mal especificado (madura com D errado); maturação estocástica por
  célula (restatement com sinal negativo); custo variável (CPC muda com o gasto);
- K > 32, horizontes diferentes de 30 ciclos, Hyperband como política;
- interferência com oráculo exato (o oráculo ignora canibalização → regret pode ser < 0
  nesses cenários; não ocorreu em média);
- shrinkage/EB nas estimativas do SH/greedy (outra frente — statlab);
- qualquer dado real: nada aqui autoriza uso operacional.
