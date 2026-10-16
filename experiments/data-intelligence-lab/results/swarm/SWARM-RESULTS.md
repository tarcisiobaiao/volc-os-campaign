# Swarm Lab — resultados (worker E, Fase 5) — revisão pós-F2

**Natureza:** simulação sintética com seed. Nenhuma célula é campanha real, nenhum
parâmetro vem de dado real (os dados reais só deram forma ao gerador), nada aqui é
"validado". Sem caminho para rede, Google Ads, Supabase ou mutação real (teste AST
`test_modulo_swarm_nao_tem_caminho_para_rede_ou_mutacao_real`).

Números deste texto foram copiados de `SWARM-TABELAS.md`, que é **gerado** dos JSON
por `scripts/swarm_tabelas.py tudo` (não editar à mão). Em caso de divergência, vale
o arquivo gerado.

Seções marcadas **PÓS-REGISTRO / EXPLORATÓRIO** foram acrescentadas depois da revisão
adversarial F2 e **não** fazem parte do critério pré-registrado.

## Veredito

> **"ASHA/SH supera random, equal e greedy sem aumentar falsos vencedores ou drawdown?" → NÃO** (em simulação).

- **Pré-registrado** (`PRE-REGISTRO.md`, sha256 `453e0aff…`, no manifesto de cada JSON):
  0 de 48 comparações no grid principal (12 cenários × 4 candidatos), 0 de 192 na
  sensibilidade, 0 de 120 no grid de parâmetros. O melhor baseline foi sempre o
  `greedy_parcial`.
- **Pós-registro, com a métrica de falsos vencedores relativa ao oráculo** (F2-01):
  continua 0 em todas as comparações (48 + 192 + 120 + 80 do varrimento de saturação).
  O veredito não depende do defeito da métrica pré-registrada, porque o que falha
  é sempre a condição de regret.
- Ressalva: na diferença **pareada** por seed, que não é a regra pré-registrada, o SH
  ganha do greedy por pouco quando **não há saturação** e a maturação é uniforme.
  São −R$539 [−611; −467] no cenário ideal (D=0, ruído baixo, n_final=4) e
  −R$227 [−360; −95] sem saturação com D=3. Os ICs marginais se cruzam. Nesses
  cenários o Thompson (extensão) é melhor que os dois.

### Atribuição causal (reescrita — a versão anterior foi refutada pela revisão F2-02)

A versão anterior dizia que *cada* desvio (atraso, saturação, não estacionariedade,
interferência) piorava SH/ASHA mais que o greedy. **Isso estava errado para
interferência e não estacionariedade.** A diferença-em-diferenças pareada abaixo é
pós-registro, com 200 seeds comuns, Δ = regret(candidato) − regret(greedy_parcial),
DiD = Δ(alvo) − Δ(referência), e DiD > 0 quer dizer que o fator prejudica o
candidato mais que o greedy. Ela mostra:

| fator isolado | sh_parcial | sh_madura | asha_parcial | asha_madura |
|---|---|---|---|---|
| **saturação** (cap×2,5 vs ×100, D=3) | **+1794 [1620; 1968]** | −78 [−262; 107] | +651 [321; 980] | **+2310 [2051; 2568]** |
| saturação (D=0, ruído baixo) | **+1739 [1590; 1888]** | +1739 | +655 [389; 920] | +655 |
| **maturação heterogênea** (vencedoras lentas, D=3) | **+1308 [1034; 1581]** | −74 [−122; −26] | **+3860 [3068; 4651]** | −74 |
| atraso D=3, maturação uniforme | +253 [112; 393] | **+1343 [1105; 1582]** | +398 [195; 600] | **+2323 [1873; 2773]** |
| ruído alto | +392 [123; 662] | +243 [16; 471] | +251 [−124; 626] | +48 [−257; 353] |
| ruído base vs baixo | +102 [−57; 261] | −74 [−202; 54] | +224 [−24; 473] | +152 [−37; 341] |
| não estacionariedade | +133 [−50; 316] (n.s.) | +262 [138; 386] | −278 [−614; 58] (n.s.) | −59 [−319; 201] (n.s.) |
| **interferência** (rho=0,5) | **−220 [−429; −10]** | −72 [−247; 103] | **−637 [−948; −325]** | **−893 [−1147; −639]** |

Leitura correta:
- **O fator dominante é a saturação de escala** para `sh_parcial` e para o ASHA. SH
  promove e concentra, o que estoura a capacidade das células. No varrimento de
  `cap_mult_mediana`, o Δ(sh_parcial − greedy) com D=3 e maturação uniforme cai
  monotonicamente: 1567 (×2,5), 652 (×4), 57 (×6, n.s.), −184 (×10) e −227 (×100).
  Com beta=0,6 (saturação branda) o gap já é 524 em ×2,5.
- **Maturação heterogênea** (vencedoras que maturam devagar) é o segundo fator para
  quem decide com receita parcial. O efeito é enorme no ASHA.
- **Atraso com maturação uniforme** custa sobretudo às variantes `madura`, pelo
  tempo de espera, e não pela ordenação.
- **Interferência favorece SH/ASHA** em relação ao greedy. Não estacionariedade não
  tem efeito diferencial significativo sobre sh_parcial ou ASHA; tem um efeito
  pequeno sobre sh_madura (+262).
- Mesmo sem saturação, o SH nunca satisfaz a regra pré-registrada. Com vencedoras
  lentas, sem saturação, ele perde de novo (+1347).

## Arquivos

| arquivo | o quê |
|---|---|
| `src/volc_dil/swarm/cenario.py` | gerador de cenários (seed → cenário determinístico) |
| `src/volc_dil/swarm/simulador.py` | ciclos, validação de orçamento, receita reportada (maturação), métricas (inclui `excesso_perdedoras_vs_oraculo_*`, pós-registro) |
| `src/volc_dil/swarm/politicas.py` | equal, greedy, SH (+random com o mesmo cronograma), ASHA, Thompson top-n, oráculo MILP |
| `src/volc_dil/swarm/experimento.py` | Monte Carlo pareado, IC, `avaliar_criterio` (pré-registrado) e `avaliar_criterio_exploratorio` |
| `src/volc_dil/swarm/diagnostico.py` | premissas do ASHA (correlação baixa→alta fidelidade) |
| `src/volc_dil/swarm/regras.py` | regra de parada por rung no estilo Optuna (só referência; nenhuma política a usa) |
| `scripts/swarm_grid.py` | grids `principal`, `parametros`, `sensibilidade`, `diagnostico`, `pos_registro --bloco did|saturacao` |
| `scripts/swarm_tabelas.py` | gera `SWARM-TABELAS.md` a partir dos JSON (`tudo`) |
| `scripts/swarm_mutantes.py` | teste de mutação (copia para diretório temporário; não toca o repo) |
| `scripts/swarm_crosscheck_optuna.py` | sonda isolada contra o Optuna (não roda no venv do lab) |
| `results/swarm/PRE-REGISTRO.md` | critério e hipóteses escritos antes dos grids (não alterado) |
| `results/swarm/SWARM-TABELAS.md` | todas as tabelas, geradas |
| `results/swarm/swarm_{principal,parametros,diagnostico,sensibilidade_*}.json` | grids pré-registrados (+ bloco `pos_registro` por cenário) |
| `results/swarm/swarm_pos_registro_{did,saturacao}.json` | análises exploratórias F2-02 |
| `results/swarm/swarm_mutantes.json` | 11/11 mutantes mortos |
| `results/swarm/swarm_custo_*.json` | tempo de parede (não determinístico, separado de propósito) |
| `tests/data-intelligence/test_swarm.py` | 35 testes, ~4 s |

Comandos (da raiz do repo, `OMP_NUM_THREADS=2`, um processo por vez):

```bash
PY=experiments/data-intelligence-lab/.venv/bin/python; G=experiments/data-intelligence-lab/scripts/swarm_grid.py
$PY $G --grid principal                       # ~103 s
$PY $G --grid parametros                      # ~141 s
$PY $G --grid sensibilidade --bloco estacionario      # ~146 s
$PY $G --grid sensibilidade --bloco nao_estacionario  # ~164 s
$PY $G --grid diagnostico                     # ~6 s
$PY $G --grid pos_registro --bloco did        # ~43 s   (exploratório)
$PY $G --grid pos_registro --bloco saturacao  # ~125 s  (exploratório)
$PY experiments/data-intelligence-lab/scripts/swarm_tabelas.py tudo
$PY experiments/data-intelligence-lab/scripts/swarm_mutantes.py
$PY -m pytest tests/data-intelligence/test_swarm.py -q
```

Seeds dos grids: `1_000_000 .. 1_000_199` (200 por cenário). São disjuntas do piloto
de depuração (0..39), que está divulgado no pré-registro. Os JSON foram regenerados
com o código final. Comparei campo a campo todas as métricas, critérios e pares
pré-registrados contra a primeira geração: **0 diferenças**. Mudaram só o hash das
fontes no manifesto e os blocos novos `pos_registro`.

### Precedência do pré-registro (F2-13)

A evidência é só o filesystem; não há commit, porque commitar é tarefa do coordenador.
Birth time e mtime do `PRE-REGISTRO.md` são `2026-10-16T00:08:58`. Os grids da
primeira geração saíram em `swarm_principal.json` 00:15:23, `swarm_parametros.json`
00:17:31 e `swarm_sensibilidade_*` 00:20:06 / 00:22:46. Uma tentativa anterior do
grid principal, por volta de 00:13, abortou por tamanho do JSON e não gravou nada.
Isso não prova a ordem contra um adversário: o mtime é editável. O commit `fc05316a`
(2026-10-16 00:26:15) fixa o **conteúdo**: o sha256 `453e0aff…` é o mesmo dos
manifestos, e o arquivo não foi alterado desde então. Mas esse commit é **posterior**
aos grids, então a precedência continua apoiada só no mtime (limitação aceita).

## Modelo (resumo; detalhes nas docstrings)

- K=16 células sintéticas (rótulos canal × ângulo × objetivo × device), T=30 ciclos,
  orçamento fixo de R$960/ciclo, mínimo de R$10 por célula ativa (ou 0 = podada).
- Valor verdadeiro `v_k` = receita por R$ (margem = v−1). Segue uma log-t com cauda:
  a maioria fica abaixo de 1 e ~25% são vencedoras. Saturação: acima de `cap_k`
  cada R$ rende só `beta` (0,25 no grid pré-registrado; o varrimento pós-registro
  vai de ×2,5 a ×100 e beta de 0,25 a 0,6).
- Receita realizada: Poisson de eventos × Gamma, arredondada ao **centavo**
  (zero-inflada). Ruído com números aleatórios comuns (CRN).
- Maturação: na idade a, reporta-se `phi0 + (1−phi0)·min(1, a/D)` da receita final.
  Modos: `uniforme`, `por_canal` e `vencedoras_lentas`.
- Não estacionariedade: em T/2 a melhor célula cai para 0,6× e uma perdedora assume
  o valor antigo dela. Interferência: receita × (1 − rho·gasto das outras do mesmo
  canal / B).
- Oráculo: MILP exato por regime, conferido contra busca exaustiva. Com interferência
  ele é aproximado (ignora a canibalização).
- **Fronteira de dinheiro**: alocação, gasto e receita são `np.int64` em micros. O
  validador rejeita float, soma ≠ orçamento, valor negativo e célula ativa abaixo do
  mínimo. O valor esperado (float64) é só métrica de regret.

Políticas: n_final/n_top = 4, degraus (60, 180) cliques, eta=2, ASHA com 8 slots e
greedy com janela de 3 ciclos e passo de 30%. São elas: `equal`, `random_sh`,
`greedy_{parcial,madura}`, `sh_{parcial,madura}`, `asha_{parcial,madura}` (variante de
promoção do artigo), `thompson_{parcial,madura}` (extensão) e `oraculo`.

## Tabela principal — regret (R$, soma de 30 ciclos; média [IC95 MC], n=200)

O oráculo tem regret 0 por definição em todos os cenários. O critério pré-registrado
compara com o melhor baseline:

| cenário | melhor baseline | sh_parcial | sh_madura | asha_parcial | asha_madura | thompson_parcial (ext.) | Δ pareado sh_parcial − baseline |
|---|---|---|---|---|---|---|---|
| base (D=3 uniforme) | greedy_parcial: 7556 [6887; 8226] | 9123 [8458; 9788] | 10213 [9411; 11016] | 10164 [9273; 11056] | 12090 [11137; 13043] | 6072 [5520; 6624] | 1567 [1382; 1752] |
| sem_atraso | greedy_parcial: 7736 [7069; 8404] | 9050 [8382; 9719] | 9050 | 9947 [9049; 10845] | 9947 | 5961 [5424; 6499] | 1314 [1141; 1487] |
| atraso_6 | greedy_parcial: 7461 [6792; 8130] | 9036 [8364; 9708] | 11449 [10538; 12360] | 10003 [9111; 10895] | 13818 [12810; 14826] | 6086 [5531; 6642] | 1575 [1391; 1759] |
| vencedoras_lentas_D3 | greedy_parcial: 7630 [6963; 8297] | 10504 [9794; 11215] | 10213 [9411; 11016] | 14098 [13021; 15175] | 12090 [11137; 13043] | 6907 [6306; 7508] | 2874 [2590; 3159] |
| vencedoras_lentas_D6 | greedy_parcial: 7742 [7072; 8412] | 12170 [11432; 12907] | 11449 [10538; 12360] | 15076 [13992; 16160] | 13818 [12810; 14826] | 7322 [6710; 7934] | 4428 [4091; 4765] |
| maturacao_por_canal_D3 | greedy_parcial: 7512 [6842; 8183] | 9591 [8899; 10282] | 10213 [9411; 11016] | 11367 [10499; 12236] | 12090 [11137; 13043] | 6477 [5888; 7065] | 2078 [1842; 2314] |
| ruido_baixo | greedy_parcial: 7011 [6341; 7682] | 8476 [7808; 9145] | 9742 [8943; 10542] | 9396 [8540; 10251] | 11393 [10479; 12307] | 5499 [4943; 6055] | 1465 [1296; 1633] |
| ruido_alto | greedy_parcial: 8673 [7993; 9353] | 10632 [9891; 11373] | 11573 [10746; 12401] | 11532 [10656; 12408] | 13254 [12325; 14184] | 7375 [6798; 7951] | 1959 [1710; 2208] |
| nao_estacionario | greedy_parcial: 11714 [10631; 12798] | 13414 [12368; 14460] | 14634 [13441; 15826] | 14045 [12858; 15232] | 16189 [14894; 17484] | 7815 [7196; 8434] | 1700 [1444; 1956] |
| interferencia (rho=0,5) | greedy_parcial: 7498 [6478; 8518] | 8845 [7796; 9894] | 10083 [8942; 11224] | 9469 [8352; 10586] | 11138 [9882; 12394] | 6196 [5276; 7116] | 1347 [1126; 1568] |
| ideal_sem_saturacao | greedy_parcial: 36360 [31976; 40745] | 35821 [31469; 40174] | 35821 | 37696 [33106; 42286] | 37696 | 33106 [28950; 37263] | **−539 [−611; −467]** |
| adverso | greedy_parcial: 11617 [10425; 12810] | 14944 [13628; 16260] | 15337 [13827; 16847] | 16161 [14710; 17612] | 16376 [14879; 17872] | 9511 [8626; 10395] | 3327 [2838; 3815] |

Referências no base: `equal` 18.259 e `random_sh` 23.583. O random_sh fica pior que
equal porque concentrar ao acaso estoura a saturação.

### Falsos vencedores, drawdown e poda, com a linha do oráculo (média [IC95])

| cenário | política | orç. em perdedoras (fim) — **pré-reg.** | excesso vs oráculo (fim) — **pós-reg.** | drawdown R$ | top-k podadas | falso venc./promovida |
|---|---|---|---|---|---|---|
| base | **oraculo** | 0.281 [0.240; 0.321] | 0.000 | 513 [325; 700] | 0.24 [0.15; 0.33] | 0.35 [0.32; 0.39] |
| base | greedy_parcial | 0.235 [0.200; 0.270] | 0.101 [0.083; 0.120] | 1760 [1395; 2124] | 0.15 [0.10; 0.21] | 0.33 [0.29; 0.36] |
| base | sh_parcial | 0.250 [0.214; 0.286] | 0.161 [0.137; 0.184] | 2410 [1937; 2883] | 0.49 [0.41; 0.58] | 0.30 [0.27; 0.34] |
| base | sh_madura | 0.240 [0.204; 0.276] | 0.149 [0.125; 0.173] | 2545 [2100; 2989] | 0.46 [0.37; 0.54] | 0.29 [0.26; 0.33] |
| base | asha_parcial | 0.287 [0.251; 0.324] | 0.186 [0.159; 0.213] | 2635 [2166; 3104] | 0.69 [0.59; 0.79] | 0.35 [0.32; 0.39] |
| base | asha_madura | 0.291 [0.254; 0.328] | 0.180 [0.154; 0.205] | 3806 [3338; 4273] | 0.69 [0.59; 0.79] | 0.35 [0.32; 0.39] |
| vencedoras_lentas_D6 | **oraculo** | 0.281 [0.240; 0.321] | 0.000 | 513 [325; 700] | 0.24 [0.15; 0.33] | 0.35 [0.32; 0.39] |
| vencedoras_lentas_D6 | greedy_parcial | 0.246 [0.211; 0.280] | 0.102 [0.084; 0.120] | 1841 [1482; 2199] | 0.09 [0.05; 0.13] | 0.34 [0.31; 0.37] |
| vencedoras_lentas_D6 | sh_parcial | **0.581** [0.549; 0.614] | 0.430 [0.404; 0.456] | 3658 [3066; 4250] | **1.67** [1.55; 1.78] | 0.60 [0.57; 0.63] |
| vencedoras_lentas_D6 | sh_madura | 0.249 [0.213; 0.285] | 0.160 [0.135; 0.185] | 2886 [2433; 3338] | 0.51 [0.43; 0.59] | 0.31 [0.28; 0.34] |
| vencedoras_lentas_D6 | asha_parcial | **0.706** [0.675; 0.738] | 0.543 [0.514; 0.572] | 5072 [4415; 5728] | **2.17** [2.05; 2.30] | 0.72 [0.70; 0.75] |
| vencedoras_lentas_D6 | asha_madura | 0.284 [0.247; 0.320] | 0.182 [0.157; 0.206] | 4343 [3856; 4830] | 0.64 [0.54; 0.73] | 0.34 [0.31; 0.37] |
| ideal_sem_saturacao | **oraculo** | 0.015 [−0.002; 0.032] | 0.000 | 44 [−4; 92] | 2.29 [2.16; 2.42] | 0.01 [−0.00; 0.03] |
| ideal_sem_saturacao | greedy_parcial | 0.189 [0.155; 0.224] | 0.186 [0.152; 0.219] | 705 [565; 846] | 0.14 [0.10; 0.19] | 0.23 [0.19; 0.26] |
| ideal_sem_saturacao | sh_parcial | 0.199 [0.164; 0.234] | 0.195 [0.161; 0.229] | 663 [526; 801] | 0.23 [0.17; 0.29] | 0.24 [0.21; 0.27] |

**F2-01, defeito da métrica pré-registrada (aceito e exposto, sem alterar o pré-registro).**
`frac_orcamento_perdedoras_final` pune o ótimo. Com orçamento forçado (Σ=B) e
saturação, o oráculo põe ~28% do orçamento em células v≤1, mais que o greedy (23%).
Aplicando o critério pré-registrado ao próprio oráculo, ele "não supera" em
**8/12** cenários do grid principal (base, sem_atraso, atraso_6, vencedoras_lentas_D3/D6,
maturacao_por_canal_D3, ruido_baixo, interferencia). A métrica pós-registro
`excesso_perdedoras_vs_oraculo_final` mede só o gasto em perdedoras **além** do que
o oráculo poria; o oráculo tem 0 por construção. Com ela o greedy também lidera
(0,10 vs SH 0,15–0,16 no base), e o veredito se mantém, porque a condição que falha
é sempre o regret. "Top-k podadas" e "falso venc./promovida" também não são erros
para o oráculo (que concentra no ideal); a linha do oráculo é o piso de referência.

## Efeito da decisão com receita madura vs parcial (pareado, Δ = parcial − madura)

| cenário | SH Δregret | SH Δpodadas top-k | ASHA Δregret | ASHA Δpodadas |
|---|---|---|---|---|
| base (uniforme D=3) | −1090 [−1345; −836] | 0.04 [−0.02; 0.10] | −1925 [−2381; −1469] | 0.00 [−0.10; 0.10] |
| atraso_6 (uniforme) | −2413 [−2788; −2038] | −0.02 [−0.08; 0.04] | −3815 [−4318; −3312] | −0.01 [−0.10; 0.08] |
| maturacao_por_canal_D3 | −623 [−920; −326] | 0.18 [0.10; 0.27] | −722 [−1260; −185] | 0.30 [0.19; 0.42] |
| vencedoras_lentas_D3 | 291 [−42; 625] | **0.65 [0.56; 0.73]** | 2008 [1202; 2814] | **1.13 [1.00; 1.26]** |
| vencedoras_lentas_D6 | 721 [242; 1200] | **1.16 [1.05; 1.26]** | 1258 [495; 2021] | **1.54 [1.42; 1.66]** |

Hipóteses pré-registradas:
- **H1 confirmada**: com vencedoras lentas e D ≥ 3, sh_parcial poda mais top-k que
  sh_madura.
- **H2 confirmada**: com maturação uniforme, receita parcial não piora a ordenação
  do SH e esperar custa regret. O nível absoluto, porém, engana: no rung de 2 ciclos
  a receita parcial é 58% da madura. Uma regra de limiar absoluto seria enganada.
- **H3 refutada como formulada** (F2-12). O pré-registro dizia, sem condição, que
  "ASHA é mais sensível que SH ao atraso parcial". Com maturação uniforme não há
  diferença de poda no ASHA (Δ 0,00 / −0,01). O efeito maior no ASHA só aparece com
  maturação heterogênea, e isso é **achado pós-hoc**, não confirmação da H3.
- **H4 confirmada (efeito modesto)**: ver diagnóstico.

O greedy é quase imune ao atraso, porque usa o acumulado, que é majoritariamente
maduro.

## Sensibilidade (grade pré-registrada, 200 seeds)

A grade é D ∈ {0,1,3,6} × maturação {uniforme, vencedoras_lentas} × ruído
(R$2/8/30) × não estacionariedade {não, sim}. São **48 combinações, mas 42 cenários
distintos** (F2-11): com D=0 a maturação não tem efeito, então as 6 combinações
D=0 × vencedoras_lentas repetem as de D=0 × uniforme. A tabela gerada marca as
duplicatas com "=". **Nenhum candidato supera em nenhum dos 42** (nem com a métrica
pós-registro). Recorte estacionário, ruído R$8:

| D | maturação | equal | greedy_p | sh_p | sh_m | asha_p | asha_m | Δpodadas SH p−m |
|---|---|---|---|---|---|---|---|---|
| 0 | (qualquer) | 18259 | 7736 | 9050 | 9050 | 9947 | 9947 | 0 |
| 1 | uniforme | 18259 | 7622 | 9037 | 9385 | 10751 | 9665 | 0.01 [−0.04; 0.07] |
| 1 | vencedoras_lentas | 18259 | 7602 | 9579 | 9385 | 14073 | 9665 | 0.23 [0.16; 0.31] |
| 3 | uniforme | 18259 | 7556 | 9123 | 10213 | 10164 | 12090 | 0.04 [−0.02; 0.10] |
| 3 | vencedoras_lentas | 18259 | 7630 | 10504 | 10213 | 14098 | 12090 | 0.65 [0.56; 0.73] |
| 6 | uniforme | 18259 | 7461 | 9036 | 11449 | 10003 | 13818 | −0.02 [−0.08; 0.04] |
| 6 | vencedoras_lentas | 18259 | 7742 | 12170 | 11449 | 15076 | 13818 | 1.16 [1.05; 1.26] |

### PÓS-REGISTRO / EXPLORATÓRIO — saturação (F2-02)

A grade pré-registrada nunca variava `cap_mult_mediana` nem `beta_saturacao`. O
varrimento exploratório usou cap ∈ {2,5; 4; 6; 10; 100} × beta ∈ {0,25; 0,6} ×
maturação {uniforme, vencedoras_lentas}, com D=3 e 200 seeds. São 20 combinações;
com cap ×100 o beta não tem efeito, então há 18 cenários distintos. **0 de 80
comparações superam**, tanto pela regra pré-registrada quanto pela pós-registro.
Δ pareado (sh_parcial − greedy_parcial), maturação uniforme, beta=0,25:
×2,5 1567 [1382; 1752]; ×4 652 [481; 823]; ×6 57 [−89; 203]; ×10 −184 [−318; −50];
×100 −227 [−360; −95]. Com vencedoras lentas o Δ fica positivo em todos os caps
(+1347 a +2874).

## Grid de parâmetros de SH/ASHA (base, vencedoras_lentas_D3, ideal)

A grade foi eta ∈ {2,3} × primeiro degrau ∈ {20, 60, 150} cliques × {parcial, madura},
mais unidade gasto (R$120/R$360) e n_final ∈ {1,2,4}. **Nenhuma das 120 comparações
supera.**

Melhores variantes, por menor regret médio (correção F2-09; texto gerado de
`swarm_tabelas.py fatos`):
- base: SH `sh_e2_r120brl_gasto_parcial` 8.997 [8.327; 9.667]; ASHA
  `asha_e3_r20_cliques_parcial` 9.013 [8.333; 9.693]. Greedy: 7.556 [6.887; 8.226].
- vencedoras_lentas_D3: SH `sh_e3_r150_cliques_parcial` 9.976; ASHA
  `asha_e2_r120brl_gasto_madura` 10.029. Greedy: 7.630.
- ideal: SH `sh_e3_r20_cliques_madura` 34.332; ASHA `asha_e3_r20_cliques_madura`
  34.732. Greedy: 36.360. O Δ pareado é < 0 em 16 de 28 variantes, mas os ICs
  marginais se cruzam.
- Δ pareado < 0 aparece **só** no cenário ideal (0 de 28 no base e no vencedoras_lentas_D3).
- Pior caso: degrau curto (20 cliques) com receita parcial e vencedoras lentas.
  `asha_e3_r20_cliques_parcial` chega a 19.162, pior que equal.

## Validade do mapeamento ASHA ("célula = trial, gasto = fidelidade")

Correlação de Spearman (16 células, 200 seeds, alocação equal; `swarm_diagnostico.json`):

| cenário | rung | ρ(parcial, v) | ρ(madura, v) | ρ(madura, valor em escala) | parcial/madura (lentas) |
|---|---|---|---|---|---|
| ideal | 2 ciclos | 0.89 | 0.89 | 0.89 | — |
| base | 2 ciclos | 0.74 | 0.74 | 0.67 | — (rápidas 0.58) |
| base | 6 ciclos | 0.86 | 0.87 | 0.78 | — |
| vencedoras_lentas_D3 | 2 ciclos | **0.45** | 0.74 | 0.67 | 0.25 |
| vencedoras_lentas_D6 | 2 ciclos | **0.33** | 0.74 | 0.67 | 0.18 |
| interferencia | 2 ciclos | 0.71 | 0.71 | 0.65 | — |

O mapeamento é **válido só em parte**:
1. **Válido** como identificação do melhor braço com amostras i.i.d., que é a origem
   do SH em Karnin et al. 2013. Sem atraso, sem saturação e estacionário, o SH
   encontra a melhor célula (teste com ruído zero).
2. **Quebra com atraso de maturação heterogêneo**: o rung baixo ordena errado
   (ρ 0,74 → 0,33). Esperar a maturação restaura a ordem, mas custa +D ciclos por
   rung (DiD +1343 no sh_madura).
3. **Quebra com saturação**, o efeito dominante pelo DiD: a baixa fidelidade mede v,
   mas na produção o que vale é o valor por R$ na escala.
4. **Interferência**: viola a independência entre trials (ρ cai um pouco), mas o
   DiD mostra que ela **não** prejudica o SH/ASHA mais que o greedy; o sinal é o
   oposto. A frase anterior "quebra com interferência" ficou restrita ao diagnóstico
   de premissa e não vale como causa do resultado.
5. **Não estacionariedade**: sem efeito diferencial significativo sobre sh_parcial
   ou ASHA. A afirmação anterior foi retirada.
6. **Referência externa (correção F2-14)**: a conferência 60/60 contra
   `optuna.pruners.SuccessiveHalvingPruner` (optuna 5.0.0) valida
   `regras.asha_parada_na_chegada`, uma reimplementação da variante de **parada**
   que **nenhuma política do experimento usa**. A política `ASHA` simulada usa a
   variante de **promoção** do artigo (Li et al. 2018) e **não tem referência
   externa**. A correção dela repousa só nos testes próprios: slots respeitados,
   n_final e acerto sem ruído em ≥12/20. Hyperband não foi implementado.

## Contraprovas e mutação

`tests/data-intelligence/test_swarm.py` tem **35 testes** que passam em ~4 s. A suíte
inteira do lab também passa.
- **Reprodutibilidade:** mesma seed → mesmo resultado.
- **Oráculo:**
  - tem regret 0 e ninguém o bate sem interferência;
  - o MILP é ≥ busca exaustiva.
- **Orçamento:**
  - nunca acima do total nem abaixo do mínimo (5 cenários × 10 políticas);
  - o validador rejeita float, soma errada, valor negativo e célula abaixo do mínimo;
  - `inteirizar` passa em 300 casos aleatórios.
- **Dinheiro:** int64, múltiplo de centavo.
- **SH:**
  - poda o número certo (4 configurações);
  - acha a melhor sem ruído;
  - **atraso forte + vencedoras lentas: parcial poda mais que madura**, e o controle
    inverso com maturação uniforme não mostra o efeito;
  - com D=0, parcial ≡ madura;
  - random usa o mesmo cronograma.
- **ASHA:** slots respeitados e n_final entregue.
- **Novos (F2-03):**
  - unidade de `avaliar_criterio` com acum sintético. Cobre: supera quando as três
    condições valem; usa ICs **marginais**, não o pareado; escolhe o baseline de
    **menor** regret; exige as condições de falsos vencedores e de drawdown; a versão
    exploratória lê a métrica relativa ao oráculo;
  - `drawdown_maximo` com valor conhecido;
  - perdedora = v ≤ 1;
  - a madura decide exatamente D ciclos depois da parcial;
  - **regressão do veredito** em 6 seeds fixas (500..505), que fixa regret,
    perdedoras e drawdown de 10 políticas e o veredito ("não supera", melhor
    baseline greedy_parcial);
  - o oráculo tem excesso 0, mas a fração absoluta > 0.
- **F2-18:** o detector anti-rede agora usa AST, então pega imports dentro de
  função. Também procura por texto `__import__`, `importlib`, `subprocess`,
  `socket`, `os.system`, `eval(`, `exec(`, `urlopen` e hosts reais. Cobre
  `swarm/*.py` e `scripts/swarm_*.py`, e tem uma contraprova do próprio detector.
  Há uma exceção explícita: `swarm_mutantes.py` (subprocess para rodar pytest local).
  O crosscheck deixou de usar `importlib`.
- **Mutação** (`swarm_mutantes.py`): **11/11 mortos**. São os SW1–SW7 da revisão F2
  com o mesmo texto, mais SW8 (import de socket dentro de função), SW9 (excesso vira
  fração absoluta), SW10 (critério exploratório lê a métrica errada) e SW11 (random
  vira SH).

## Custo computacional

Um processo, `OMP_NUM_THREADS=2`, Mac compartilhado. Por simulação de 30 ciclos:
SH ~2,4–2,7 ms, ASHA ~2,8–3,2 ms, equal/greedy ~3,0–3,3 ms, Thompson ~4,5–4,9 ms,
oráculo MILP ~6–11 ms. Regeneração completa pós-F2: ~728 s de parede em 7 execuções
sequenciais, a maior com 164 s. Testes: ~4 s. Mutação: ~35 s.

## Separação de afirmações

**Demonstrado (em simulação, com estas premissas):**
- Nenhum candidato SH/ASHA supera o greedy conservador pela regra pré-registrada
  (0/360 comparações) nem pela métrica pós-registro (0/440).
- O fator dominante do gap sh_parcial − greedy é a saturação (DiD +1794). O gap
  desaparece ou inverte levemente sem saturação (Δ −227 com cap ×100, D=3).
- Receita parcial com vencedoras lentas faz o SH podar +0,65 (D=3) a +1,16 (D=6)
  células do top-4, e o ASHA +1,13 a +1,54.
- Interferência favorece SH/ASHA relativamente ao greedy. Não estacionariedade não
  tem efeito diferencial significativo sobre sh_parcial.
- A métrica pré-registrada de falsos vencedores pune o ótimo (oráculo "falha" em 8/12).
- Thompson top-n (extensão) teve o menor regret entre as políticas não-oráculo nos
  12 cenários principais.

**Inferido:**
- A vantagem do greedy vem de não se comprometer e de realocar com o acumulado
  maduro, sem estourar a capacidade.
- Degraus intra-dia com atraso de D+3 dias cairiam no regime de maturação parcial
  forte.

**Hipótese (não testada):**
- Thompson/LinTS calibrado como candidato. O ganho depende de prior e variância
  nunca estimados em dado real, e não há OPE possível sem a probabilidade da ação
  no ledger.

**Não testado / limitações aceitas:**
- `atraso_assumido` mal especificado; restatement com sinal negativo; CPC que varia
  com o gasto.
- K > 32; outros horizontes; Hyperband.
- Política ASHA (promoção) sem referência externa.
- Oráculo exato com interferência.
- Shrinkage/EB no SH/greedy.
- Precedência do pré-registro só por mtime até o commit do coordenador.
- Qualquer dado real.
