# PRÉ-REGISTRO — Model Lab da Fundação Data Intelligence (worker F, 2026-10-16)

Escrito e commitado **antes** de qualquer execução dos scripts `fundacao_modelos_*.py`. Nenhum
resultado deste diretório existia quando este arquivo foi escrito. Mudança posterior deste
arquivo invalida o critério; resultados exploratórios ou pós-registro são marcados como tal no
JSON e no `08-MODEL-LAB.md`.

Regras comuns (valem para todos os itens):

- **Simulação não é eficácia.** O teto de estado de qualquer item aqui é "testado com sintético".
- Mundo = `volc_dil.fundacao.simulador` (versão 1.0.0, catálogo 1.0.0). Consumidores leem só
  registros cortados por `available_at` (mesma semântica de `visao_as_of`); a verdade (`Mundo`,
  `gabarito`) só entra como rótulo de avaliação.
- Baseline simples **sempre** lado a lado. Comparações por diferença **pareada** entre métodos no
  mesmo mundo (CRN), IC95 por bootstrap de seeds (B = 2000, seed do bootstrap fixa) ou t entre seeds.
- "Supera" = diferença pareada com IC95 que exclui zero na direção favorável. Ganho pontual sem IC
  não é ganho.
- Todo limiar operacional citado pela missão (15 min, 2 h, 20/50/150 cliques, +40%, PMax após 150
  cliques) **não** é usado como política; qualquer número abaixo é parâmetro de experimento.
- Seeds: lista fixa por experimento, gravada no JSON. Mínimo 12 seeds por comparação (exceções
  declaradas no JSON com motivo de CPU).
- `OMP_NUM_THREADS=2`, um experimento de cada vez.

## M1 — Maturação (chain-ladder herdado × Bornhuetter-Ferguson × fator fixo) e regime

Caso de uso: nowcast da receita JoinAds e do custo D0 antes de fechar.

- **H1a (receita, mundo estável):** no `estavel` (JoinAds default), com corte diário às 12:00 local,
  BF tem MAPE menor que o chain-ladder herdado (`statlab.maturacao`, coortes maduras) na idade 0
  (o E2 de 14/10 sugeria BF melhor em idades curtas). Critério: diferença pareada de MAPE
  (BF − CL) na idade 0 com IC95 < 0. Fator fixo e "observado como final" (anti-baseline) reportados.
- **H1b (custo intradiário D0, `custo_d0_multiversao`):** o nowcast por razão de somas por hora do
  D0 (fração do custo final conhecida em cada passada) tem MAPE < 50% do MAPE de "D0 é o final"
  para passadas até 18h. Critério: razão de MAPE agregada (IC95 por seed) < 0,5.
- **H1c (regime):** com mudança de regime de maturação (simulador: `estavel` → observador de
  `atraso_receita_longo` a partir de um dia; Stat Lab herdado: atraso 2,5× mais lento),
  o fator fixo e o chain-ladder têm viés relativo |viés| > 10% nas idades 0–2 nas coortes pós-mudança
  enquanto a janela ainda contém o regime antigo; o monitor de razão de ligação (link ratio) por CUSUM
  detecta a mudança em ≥ 80% dos mundos com ≤ 5% de alarme falso em mundos sem mudança (janela de
  30 coortes), e, com o monitor ligado, a fração de números publicados cujo intervalo cobre a verdade
  sobe para ≥ 80% (herdado: 29–45%). Critério: as três condições.

## M2 — Empirical Bayes em campanha nova (`campanha_nova_aprendendo`)

- **H2:** para campanhas novas no dia k ∈ {1, 3, 7} após o lançamento, o EB Beta-Binomial herdado
  (CTR = cliques/impressões) e o EB normal herdado (RPM por pageview, `eb_normal_media`) têm MSE
  menor que a taxa crua contra a taxa realizada nos 14 dias seguintes; e menos "vencedores por sorte"
  (selecionados no top 20% que não estão no top 20% verdadeiro). Critério: razão de MSE (EB/cru) com
  IC95 < 1 em k = 1 e k = 3; vencedores por sorte: diferença pareada com IC95 < 0 em k = 1.

## M3 — Detecção de mudança (CUSUM, BOCPD mínimo) × média móvel (`quebra_regime_rpm`)

- Série: log RPM diário por campanha a partir da receita JoinAds **madura** e pageviews, disponível
  com atraso de maturação (3 dias); detector online.
- Limiares de cada método calibrados em seeds de calibração do `estavel` para a MESMA taxa de alarme
  falso alvo (0,02 alarmes por campanha-semana — parâmetro); avaliação em seeds disjuntas.
- **H3:** CUSUM e BOCPD têm poder (detectar em até 14 dias após a quebra, contando o atraso de
  maturação) maior que a média móvel com a mesma taxa de alarme falso. Critério: diferença pareada de
  poder com IC95 > 0. Reportar atraso mediano e alarmes falsos/semana realizados (calibração vs teste).

## M4 — Testes sequenciais e FDR

- **H4a:** e-BH (Wang & Ramdas) sobre e-processos de aposta para média limitada controla FDR ≤ q
  numa olhada e com peeking (10 e 50 olhadas, rejeição cumulativa — controle empírico, a garantia
  teórica com rejeição cumulativa não é reivindicada); BH com peeking infla (herdado). Critério:
  FDR e-BH ≤ q + 2 EP de Monte Carlo em todos os regimes; poder reportado (esperado menor que BH).
- **H4b:** a CS PrPl-EB herdada sobre a taxa de sessões que chegam ao destino (outcome limitado
  derivado do simulador) tem erro uniforme ≤ α; sobre receita por sessão normalizada por um limite
  estimado numa janela inicial, a garantia quebra (recusa `ForaDoSuporte` ou erro > α quando
  recortada). Critério: as duas condições.

## M5 — Diagnóstico causal (`mudanca_orcamento`)

- Verdade: contrafactual pareado (CRN) re-simulando o mesmo mundo sem as mudanças de orçamento.
- **H5a (atribuição aleatória do simulador):** DiD com placebo e teste de tendências paralelas
  estima o efeito de dobrar o orçamento sobre custo e lucro com viés cujo IC95 contém 0; a
  comparação ingênua antes/depois nos tratados tem |viés| maior que o DiD (IC95 pareado).
- **H5b (seleção pelo resultado):** quando o orçamento é dobrado para as campanhas de maior ROAS
  observado recente (seleção pelo resultado, como um humano faria), o DiD do lucro fica enviesado
  (IC95 do viés exclui 0) e o antes/depois ingênuo mais ainda. Controle sintético mínimo: reportado,
  sem hipótese direcional.

## M6 — Surrogate

- **H6:** o simulador não muda o veredito herdado (`dados_insuficientes` no volume real), mas mostra
  qual premissa muda: a força do sinal pageviews→receita no mundo sintético e a perda de
  identificabilidade no grão campanha quando o sensor descarta a campanha (R2). Sem critério de
  ganho; é verificação de premissa.

## M7 — Bandits contextuais e OPE

- Ambiente: recompensas horárias de lucro por campanha tiradas da verdade do simulador; contexto =
  bloco horário × fim de semana.
- **H7a:** LinUCB e Thompson linear têm regret menor que `equal` (aleatório uniforme) e que guloso
  em `estavel`. Critério: diferença pareada com IC95 < 0 para os dois.
- **H7b:** com propensão logada correta, IPS é não-viesado (|média − V| ≤ 3 EP de Monte Carlo sobre
  ≥ 200 seeds de logging); SNIPS e DR têm variância menor que IPS; propensão inventada (uniforme
  assumida quando o logger não era uniforme) gera viés fora do IC; sem propensão a função recusa.

## M8 — Predição conformal

- **H8a:** split conformal (resíduo escalado) do lucro diário maduro por campanha tem cobertura
  empírica ≥ nominal − 0,02 no `estavel` (90% nominal).
- **H8b:** em `quebra_regime_rpm`, a cobertura do split com calibração fixa cai abaixo de
  nominal − 0,05 nas campanhas quebradas após a quebra; ACI (Gibbs & Candès) recupera cobertura de
  longo prazo dentro de nominal ± 0,03. Critério: as duas condições.

## M9 — Anomalias

- **H9a (`outlier_bot`):** mediana/MAD e sazonal robusto sobre a razão cliques/sessões têm F1 maior
  que z-score com os limiares padrão (robusto 3,5; z 3,0). Critério: diferença pareada de F1 com IC95 > 0.
- **H9b (`fonte_fora_do_ar`):** ausência é classificada como lacuna, nunca anomalia de valor (0
  anomalias de valor em pontos sem valor); um detector ingênuo null→0 dispara ≥ 1 falso alarme por
  janela de indisponibilidade.
- **H9c (`zero_falso`):** o detector de zero implausível tem recall ≥ 0,8 e precisão ≥ 0,9 contra a
  marca `zero_falso` do gabarito (o detector não lê o gabarito).

## M10 — Alocação de orçamento

- Avaliação: re-simulação do mesmo mundo (CRN) com o orçamento de cada política nos 15 dias pós-
  decisão; oráculo = melhor alocação numa grade de orçamentos por campanha (MILP, mesmas restrições).
- **H10a (`mudanca_orcamento`, há variação histórica de orçamento):** o alocador sob resposta côncava
  estimada (com redução por incerteza) tem regret menor que `equal` e que `proporcional` herdado.
  Critério: diferença pareada de regret com IC95 < 0 para os dois.
- **H10b (`estavel`, sem variação de orçamento):** a curva não é identificável; o alocador cai no
  prior e **não** supera `equal` (esperado). Critério: diferença pareada com IC95 contendo 0 ou
  desfavorável — se supera, investigar vazamento antes de aceitar.
- Restrições (mínimo, máximo, passo máximo, total) verificadas por teste em toda política.

## M12 — Modelos tabulares

- **H12:** Ridge e HistGradientBoosting com features `as_of` e validação rolling-origin não superam
  a baseline "média dos 7 últimos dias maduros" em mais de 2% de MAE (herança: sinal fraco). Critério
  de "supera": MAE relativo pareado com IC95 < −2%. Vazamento: feature do futuro injetada é detectada
  pela checagem de disponibilidade (100%) e pela checagem empírica de skill implausível.

## Itens sem experimento novo (só referência)

M11 SH/ASHA (herança 0/360 e 0/440), M13 DuckDB/Polars (benchmark herdado e de B), M14 bibliotecas.
