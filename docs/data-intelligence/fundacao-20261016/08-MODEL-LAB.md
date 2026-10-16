# 08 — Model Lab e "ouros" quantitativos (worker F, Fundação Data Intelligence, 2026-10-16)

Estado-teto de tudo aqui (taxonomia do manifesto §7): **testado com sintético**. Nenhum número
abaixo é eficácia operacional, calibração com dado real ou política. Os limiares citados pela missão
(15 min, 2 h, 20/50/150 cliques, +40%, PMax após 150 cliques) não aparecem como regra em lugar
nenhum: todo limiar é parâmetro de experimento, declarado no JSON.

- Código: `experiments/data-intelligence-lab/src/volc_dil/fundacao/modelos/` (funções puras, API em `__init__.py`).
- Testes: `tests/data-intelligence/fundacao/test_modelos_*.py`.
- Experimentos: `experiments/data-intelligence-lab/scripts/fundacao_modelos_*.py` (cada um com `--rapido` que não grava).
- Resultados: `experiments/data-intelligence-lab/results/fundacao/modelos/` — `PRE-REGISTRO.md` (commit
  `eda4f041`, anterior a qualquer resultado), `m*.json` (manifesto: seeds, versões, sha256 do código,
  versão do simulador/catálogo), `RESUMO.md` (gerado dos JSONs por `fundacao_modelos_relatorio.py`; um
  teste exige regeneração byte a byte).
- Mundo: `volc_dil.fundacao.simulador` 1.0.0 / catálogo 1.0.0. Consumidores leem registros cortados por
  `available_at` (painel `TabelaVersoes`, provado equivalente a `visao_as_of`); verdade (`Mundo`,
  `gabarito`) só como rótulo.

Reuso (sem duplicar): `statlab.maturacao` (chain-ladder, guarda única, razão empírica),
`statlab.shrinkage` (Beta-Binomial, normal-normal), `statlab.sequencias_confianca` (PrPl-EB),
`statlab.fdr` (BH), `replay.politicas` (`alocar_com_piso`, regra proporcional), `surrogate.feasibility`
(portão), `simulador` (mundo, observador, CRN para contrafactual).

Leitura dos números: `x [a; b]` = média entre seeds com IC95 por bootstrap de seeds; "supera" = diferença
pareada (mesmo mundo, CRN) com IC95 que exclui zero no sentido favorável. Detalhe completo de cada
número em `RESUMO.md` e no JSON correspondente.

Replay: "replay `as_of` em sintético" = cortes por `available_at` sobre os registros do simulador
(`TabelaVersoes`), feito em M1 (triângulos e D0 intradiário), M9 (lacunas/zero na leitura D-1) e M12
(features e rótulos por corte); M3, M5, M8 e M10 usam o valor maduro com o atraso de maturação explícito
(3 dias) ou a verdade diária, que coincide com o último valor observado (conservação testada no
simulador). **Replay com dado real: nenhum** — a exportação de snapshot foi negada (recibo de leituras);
ver DAT-01 em `10-BACKLOG-OUROS.md`.

## 0. Veredito em uma tela

O resultado é misto, e a maior parte dele é negativa ou parcial — o que é útil. **Duas** técnicas
passaram todos os seus critérios pré-registrados em simulação **e** resolvem um problema concreto do VOLC;
uma terceira passou só em parte. Viram candidatas a shadow (não a política). (Errata R2, 2026-10-16: a
versão anterior contava M10 como aprovada, mas H10b foi refutada — ver §16.)

1. **Nowcast intradiário do custo D0** (M1-B): a razão de somas por hora reduz o erro sobre o custo
   final para ~15% do erro de "D0 é o final" (wMAPE 6–11% contra 40–70% até 18h).
2. **e-BH/e-processos para testes múltiplos com outcome limitado** (M4): FDR ≤ q mesmo com 50 olhadas,
   onde o BH com peeking vai a 0,28 (q = 0,10).
3. **Alocação sob resposta côncava estimada** (M10) — **parcial**: H10a suportada (regret 11–23× menor
   que `equal`/`proporcional` herdado, com histórico de decisão lido do painel `as_of` maduro), mas **H10b
   refutada**: supera mesmo sem variação exógena, porque o ganho vem quase todo de **cortar campanhas com
   ROAS < 1** (primeira ordem), não da curvatura — a elasticidade fica no teto (b = 0,95) em 30–40% das campanhas.

Duas são infraestrutura de método que já se pagam: **OPE só com propensão logada** (IPS não-viesado;
propensão inventada depois do fato erra por 2,1 unidades de escala; sem propensão a função recusa) e
**checagem de vazamento por `disponivel_em`** (100% das features do futuro injetadas detectadas).

O resto não superou o baseline simples sob o critério pré-registrado: BF perde do chain-ladder; o
monitor de regime de maturação pré-registrado não calibra (alarme falso 25–52% por mundo); CUSUM ganha
da média móvel por pouco e BOCPD perde; EB só ajuda no CTR do 1º dia; ACI recupera cobertura mas o split
nem degrada tanto; detectores robustos de bot têm recall ~0,2; o detector de zero implausível tem
precisão 0,76; Ridge/HGB não batem a média dos dias maduros; o surrogate continua `dados_insuficientes`
mesmo no mundo sintético com 50×90.

## 1. Maturação (custo D0 intradiário; receita JoinAds com atraso; regime)

- **Hipótese.** (H1a) BF tem MAPE menor que o chain-ladder herdado na idade 0; (H1b) a razão de somas
  intradiária reduz o erro do custo D0 a < 50% do "D0 é o final"; (H1c) um monitor de link ratio corrige o
  "degrada sem avisar" herdado (detecção ≥ 80%, alarme falso ≤ 5%, cobertura dos números publicados ≥ 80%).
- **Caso de uso.** Decidir no meio do dia com custo D0 de 14–17 versões/dia (recibo L10: 14 valores
  distintos em 16 runs num dia de produção; o cenário `custo_d0_multiversao` dá 17) e com receita JoinAds
  que só fecha em D+3 (ou D+6, se a cadência mudar).
- **Baseline.** "Observado é o final" (anti-baseline), fator fixo congelado (o que uma regra codificada
  faria, ex.: "D0 vale x% do final"), chain-ladder herdado por coortes maduras.
- **Implementação.** `modelos/maturacao.py`: `triangulo_de_tabela` (triângulo montado com cortes `as_of`
  reais sobre os registros), `nowcast`/`maturar` (chain-ladder herdado, BF, fixo, observado — todos com a
  guarda única herdada), `curva_intradiaria`/`nowcast_intradiario`, `monitor_maturacao` (CUSUM bilateral
  em log link ratio, ponto de mudança por MLE de dois segmentos) e `regime_vigente` (segmentação sem
  estado: a mesma chamada amanhã reencontra a mudança; coortes do regime antigo seguem com o fator
  antigo, as do novo recebem `insuficiente` com motivo `regime_de_maturacao_mudou` até haver base).
- **Teste sintético.**
  - A (`estavel`, 40×60, 12 seeds, corte 12:00): MAPE na idade 0 — CL 4,8% [4,4; 5,1], fixo 4,9%,
    BF 6,3% [5,7; 7,0], observado 82,3%. **H1a refutada**: BF − CL = +1,47 p.p. [+0,86; +2,12]. O
    intervalo de razão empírica do CL (nominal 80%) cobre 70–75%.
  - B (`custo_d0_multiversao`, 40×30): wMAPE CL intradiário 11,2% (8h) → 3,8% (22h) contra 70,2% → 18,2%
    do "D0 como final". **H1b suportada**: razão 0,151 [0,145; 0,156].
  - C1 (cenário de regime do Stat Lab herdado, 100 mundos): reproduz a herança (atraso 2,5× → viés −68,3%
    em 1–2 d; herança −68,5%). Monitor pré-registrado (k = 0,5, escala MAD): **não calibra** — alarme falso
    por mundo de 0,52 mesmo com h = 20 (grade pré-registrada), e com ele ligado nada melhora.
  - C2 (simulador: o observador JoinAds troca de `estavel` para `atraso_receita_longo` no dia 30): CL
    −35,0% na idade 1, fixo −41,9%. Monitor pré-registrado detecta 100% em 3,2 dias, mas com alarme falso
    de 25% por mundo — não calibrado. **H1c refutada** como pré-registrada.
  - Pós-registro (exploratório, marcado no JSON): monitor conservador (k = 1, escala = max(MAD, dp), grade
    até 60) calibra (FA ≤ 5% com h = 16). C2: detecção 92% em 15 dias, atraso 4,6 [3,2; 6,3] dias, viés
    dos números publicados na idade 1 cai de −35,0% para −19,7% [−28,6; −9,9], ao custo de recusar ~48%.
    C1 (ruidoso: 30 eventos/dia, valor lognormal σ = 1,2): detecção 47% (atraso 2,5×) e 3% (metade) — fraco.
- **Replay.** Não há dado real (exportação de snapshot negada no recibo de leituras). O triângulo é
  montado por `as_of` sobre os registros do simulador; o mesmo código roda sobre `TabelaVersoes` de dado
  real assim que houver snapshot.
- **Limites.** BF depende do prior; aqui o prior é a média dos finais da janela (uma escolha fraca — com
  um prior de plano, ex. orçamento × ROAS esperado, o resultado pode mudar). O monitor só vê o que já
  maturou um degrau (link ratio idade → idade+1): entre a mudança e a detecção, publica com fator velho.
  A recusa é a "correção" honesta: o regime novo não é estimável antes de amadurecer.
- **Custo operacional.** Trivial (numpy; < 1 s por corte). Dado mínimo: ≥ 14 coortes diárias maduras
  para o fator diário; ≥ 10 dias de backfill para a curva intradiária.
- **Promoção.** (B) Replay `as_of` com o ledger v21 real (L10) mostrando wMAPE < 50% do naive em ≥ 4
  semanas → shadow no cockpit como "custo projetado do dia" com intervalo. (A) CL com guarda é o baseline
  de shadow da receita. (C) monitor só com FA medido em ≥ 8 semanas reais.
- **Descarte/espera.** BF descartado por enquanto (reabrir com prior de plano). Monitor pré-registrado
  descartado; o conservador espera dado real.
- **Estado.** CL/fixo/BF/intradiário: **testado com sintético**. Monitor: **construído · testado
  hermeticamente**; eficácia **ainda não demonstrada** (pré-registrado falhou; pós-registro parcial).

## 2. Empirical Bayes / shrinkage (`campanha_nova_aprendendo`)

- **Hipótese (H2).** No dia k após o lançamento, o EB Beta-Binomial (CTR) e o EB normal (RPM) herdados
  reduzem o MSE contra a taxa dos 14 dias seguintes e reduzem "vencedores por sorte" no top 20%.
- **Caso de uso.** Ranquear campanhas novas antes de ter volume (P05-T09, guardião das 72 h).
- **Baseline.** Taxa crua x/n.
- **Implementação.** `modelos/eb.py` (fachada fina: `encolher_taxa`, `encolher_media`,
  `vencedores_por_sorte`); toda a matemática é a herdada.
- **Teste sintético (60×60, 16 seeds, ~29 campanhas novas por mundo).** CTR: razão de MSE EB/cru 0,70
  [0,58; 0,84] no dia 1; 1,02 [1,00; 1,05] no dia 3; 1,02 [1,01; 1,03] no dia 7 (levemente pior). RPM:
  dia 1 **insuficiente** (variância intra-campanha não identificável com 1 dia); dia 3 0,84 [0,73; 0,95];
  dia 7 0,97 [0,89; 1,05]. Vencedores por sorte: nenhuma diferença (EB − cru = 0,12 [−0,12; 0,38] no
  dia 1; 0 nos demais). O CTR cru do dia 1 subestima o futuro em −19,3% [−22,9; −15,5] (curva de
  aprendizado do simulador) — e o EB não corrige isso, porque encolhe para a média das próprias novas.
- **Replay.** Não aplicável sem dado real de lançamentos.
- **Limites.** O encolhimento só importa quando n é pequeno; com milhares de impressões no dia 3 ele some.
  Um prior que conheça a curva de aprendizado (backlog EB-03) seria o ganho real.
- **Custo.** Trivial. Dado mínimo: ≥ ~10 campanhas comparáveis no mesmo estágio para estimar o prior.
- **Promoção.** Ganho em dado real no dia 1–2 com rótulo de 14 dias, ≥ 20 lançamentos.
- **Descarte/espera.** Dia ≥ 3: sem ganho (espera). "Vencedores por sorte": refutado nesta configuração.
- **Estado.** **testado com sintético** (H2 refutada como um todo; parcial no CTR dia 1 e RPM dia 3).

## 3. Detecção de mudança (CUSUM, BOCPD mínimo × média móvel; `quebra_regime_rpm`)

- **Hipótese (H3).** Com limiares calibrados para a mesma taxa de alarme falso (0,02/campanha-semana em
  10 seeds do `estavel`), CUSUM e BOCPD têm mais poder (≤ 14 dias após a quebra, contando 3 dias de
  maturação) que a média móvel.
- **Caso de uso.** Avisar que o RPM de uma campanha mudou de regime (o que invalida modelos e fatores).
- **Baseline.** Média móvel de 5 dias contra a referência (14 dias), mesma padronização robusta.
- **Implementação.** `modelos/mudanca.py`: `media_movel`, `cusum`, `bocpd` (Adams & MacKay, Normal-Gama,
  hazard constante, ~60 linhas), `detectar_quebra(serie, metodo=...)`, `calibrar_limiar` (escolhe o limiar
  pela FA medida — sem isso a comparação é inválida).
- **Teste sintético (50×60; calibração 10 seeds `estavel`; teste 16 seeds).** Poder: CUSUM 0,93 [0,91;
  0,96], média móvel 0,91 [0,88; 0,94], BOCPD 0,81 [0,77; 0,85]. FA realizada no teste 0,015–0,017/semana
  (a calibração transfere). Atraso mediano até a ação: BOCPD 4,2 dias, média móvel 5,7, CUSUM 6,6.
  CUSUM − média móvel: +0,023 [+0,005; +0,040] (supera, por pouco); BOCPD − média móvel: −0,10 [−0,14;
  −0,06]. **H3 refutada** (exigia os dois). Trade-off real: BOCPD avisa ~1,5 dia antes, com menos poder.
- **Replay.** Não há série real de RPM maduro por campanha com quebra conhecida.
- **Limites.** Quebra grande (−40%) num RPM diário com ruído moderado: qualquer método detecta. A
  referência curta (14 pontos) é estimada com erro — o alarme falso depende disso (testado).
- **Custo.** Trivial. Dado mínimo: 14 dias maduros de referência por campanha + atraso de maturação.
- **Promoção.** Em dado real: calibrar FA em ≥ 8 semanas sem mudança conhecida e mostrar poder em quebras
  anotadas (ex.: troca de rede de anúncios). Até lá, média móvel calibrada é suficiente.
- **Estado.** **testado com sintético** (CUSUM ≈ média móvel; BOCPD pior em poder).

## 4. Testes sequenciais e FDR

- **Hipótese.** (H4a) e-BH sobre e-processos de aposta controla FDR ≤ q numa olhada e com peeking; BH com
  peeking infla. (H4b) A CS herdada cobre a taxa de sessões que chegam ao destino (limitada); para
  receita por sessão (ilimitada) a garantia quebra.
- **Caso de uso.** Muitos testes simultâneos campanha × página × variante olhados todo dia (P08-T08,
  P05-T10), sem inflar falsos vencedores.
- **Baseline.** BH herdado (uma olhada e cumulativo com peeking); Wald da herança.
- **Implementação.** `modelos/sequencial.py`: `eprocesso_media_limitada` (capital com aposta previsível
  limitada a c/μ0), `e_bh` (Wang & Ramdas), `p_binomial_unilateral`, `normalizar_por_limite` (recusa se o
  "limite" for furado); reusa `cs_prpl_eb` e `bh` herdados.
- **Teste sintético.** m = 50 hipóteses, 10 alternativas (μ = 1,25·μ0), n = 2000, μ0 = 0,235 (taxa de
  destino derivada do simulador), 400 repetições: FDR BH 0,073 (uma olhada) → 0,215 (10 olhadas) → 0,277
  (50 olhadas); e-BH 0,002 → 0,005 → 0,009, poder 0,99 (BH 1,00). **H4a suportada** (a garantia com
  rejeição cumulativa é empírica, não teórica).
  Descritivo não pré-registrado (efeito fraco, lift 1,10, 200 repetições): o custo aparece — poder do e-BH
  0,06–0,09 contra 0,55–0,66 do BH, que por sua vez vai de FDR 0,08 a 0,21 com 50 olhadas.
  CS na taxa de destino (225 trajetórias): erro uniforme 0,004 [0,001; 0,025] ≤ α = 0,05. Receita por sessão
  dividida pelo máximo da janela inicial (200 sessões) em `outlier_bot`: o limite é furado em 70%
  [64; 76] das trajetórias (recusa explícita); recortando no limite, o erro uniforme ficou 1,3% —
  o recorte não quebrou a cobertura da média recortada aqui, mas mede outra coisa (receita truncada).
  **H4b suportada.**
- **Limites.** μ0 é conhecido (teste contra referência); comparação A/B de duas taxas exige o e-processo
  de duas amostras (backlog SEQ-04). O custo de poder do e-BH só aparece com efeito fraco.
- **Custo.** Trivial. Dado mínimo: outcome em [0, 1] por unidade (sessão monetizada, chegada ao destino).
- **Promoção.** Usar como regra de leitura de qualquer experimento com olhadas diárias (shadow), quando
  existir experimento real com outcome limitado logado.
- **Estado.** **testado com sintético**.

## 5. Diagnóstico causal (`mudanca_orcamento`, verdade por contrafactual CRN)

- **Hipótese.** (H5a) Com tratamento aleatório (o cenário escolhe ao acaso quem dobra), DiD tem viés com
  IC contendo 0 para custo e lucro e menor que o antes/depois; (H5b) com seleção pelo resultado (dobrar o
  top 30% de ROAS dos 7 dias anteriores), o DiD do lucro fica enviesado.
- **Caso de uso.** "Dobrei o orçamento, o lucro subiu?" — a pergunta que o cockpit responde hoje por
  antes/depois.
- **Baseline.** Antes/depois nos tratados; corte transversal tratado × controle no pós.
- **Implementação.** `modelos/causal.py`: `did_painel` (IC por bootstrap de unidades), `tendencias_paralelas`,
  `placebo_temporal`, `placebo_unidades`, `controle_sintetico` (SLSQP, pesos ≥ 0 somando 1, opção com
  intercepto) e `controle_sintetico_placebo`.
- **Teste sintético (50×30, 20 seeds; R$ por campanha-dia).**
  - H5a: ATT verdadeiro custo +8,91, lucro −1,91. Viés do DiD: custo −0,13 [−2,10; +1,80] ✓; lucro −0,67
    [−1,37; −0,02] ✗ (exclui 0 por pouco). Antes/depois: custo +3,80 (pior que DiD), lucro −0,72 (igual
    ao DiD). Controle sintético: custo +2,31 [+0,72; +3,85] (enviesado). **H5a refutada** como formulada.
  - H5b: ATT custo +6,55, lucro +1,15. Viés DiD: custo −3,99, receita −3,21, lucro +0,78 [+0,01; +1,69]
    (condição 1 ✓). Antes/depois no lucro: +0,42 [−0,20; +1,34] — **menos** enviesado que o DiD
    (|antes/depois| − |DiD| = −0,38 [−0,71; −0,09]; condição 2 ✗) → **H5b refutada** (errata R2/G9: a
    versão anterior testava só a condição 1 e declarava "suportada"). Corte transversal: lucro +15,65 (atribui à verba o que é seleção). Controle sintético
    com intercepto foi o menos enviesado em H5b (custo −0,26 [−0,93; +0,39]). Os diagnósticos **não
    pegam** a seleção: tendências paralelas passam em 70–95% e o placebo em 85–95% dos mundos enviesados.
- **Quando a atribuição observacional erra (resumo).** (i) Comparar campeões escolhidos contra o resto
  (corte transversal) erra por uma ordem de grandeza; (ii) antes/depois erra no custo porque o mercado
  muda; (iii) DiD erra quando a escolha usou o próprio resultado recente (regressão à média) — e os
  testes de pré-tendência não avisam; nesse caso o antes/depois do lucro errou menos que o DiD, o que
  não o torna confiável (no custo ele erra +0,88 e na receita +1,30).
- **Limites.** 15 tratados por mundo; o ruído do lucro é grande frente ao efeito. O simulador não tem
  interferência entre campanhas (DiD favorecido).
- **Custo.** Trivial (bootstrap). Dado mínimo: log de decisão (quem mudou, quando, por quê) + painel
  maduro balanceado.
- **Promoção.** Mudanças de orçamento **aleatorizadas** (ou com regra de seleção registrada) — P15-T09.
- **Estado.** **testado com sintético**.

## 6. Surrogate (portão herdado reaberto)

- **Hipótese (H6).** O simulador não muda o veredito herdado (`dados_insuficientes` no volume real); mostra
  qual premissa muda (força do sinal; R2).
- **Caso de uso.** Antecipar a receita madura (D+3) com sinais de D+1 (sessões, chegadas ao destino).
- **Baseline.** Média da campanha no treino (skill = 1 − MAE_modelo/MAE_baseline fora do tempo).
- **Implementação.** Nenhum código novo de modelo: `scripts/fundacao_modelos_surrogate.py` monta
  `LinhaRotulada` do portão herdado com features **no valor conhecido às 20h de D+1** (não o final — usar
  o valor final com a disponibilidade da 1ª versão foi um vazamento do primeiro rascunho do adaptador,
  pego antes do resultado final e corrigido).
- **Teste sintético.** Portão: 50×30 → `dados_insuficientes`; **50×90 → `dados_insuficientes`** (4455
  linhas maduras < 4500; 21 campanhas com profundidade < 50: o mínimo herdado exige o painel sem nenhuma
  lacuna); 50×100 e 60×100 → `viavel_para_teste`. Skill de Ridge (sessões + cliques de D+1, efeito fixo de
  campanha): 0,301 [0,285; 0,319] no `estavel` — sinal forte **por construção do gerador** (receita ≈
  pageviews × RPM), não evidência. Com R2 (`sensor_sem_campanha`), a feature de sessão existe em só 1,9%
  das linhas no grão campanha e o skill não é estimável — **mas o portão continua `viavel_para_teste`**
  (60×100), porque não mede cobertura de feature.
- **Premissas que mudam.** (i) O gatilho de volume real precisa de folga sobre 50×90 (≈ 50×100 com as
  taxas de lacuna do simulador); (ii) a hipótese de "sinal fraco" da herança é pessimista frente ao gerador —
  irrelevante enquanto R2 existir; (iii) o portão deveria exigir cobertura mínima de feature por linha.
  O veredito para o VOLC real **não muda**: dados insuficientes e, hoje, não identificável no grão campanha
  (R2).
- **Custo.** Barato (portão + Ridge). Dado mínimo: ≥ 50 campanhas × ~100 dias maduros com feature não
  circular conhecida em D+1 **no grão campanha**.
- **Promoção / espera.** Espera R2 corrigido (DAT-07) e volume. Não reaberto como ganho.
- **Estado.** hold (portão testado com sintético).

## 7. Bandits contextuais e OPE

- **Hipótese.** (H7a) LinUCB e Thompson linear têm regret menor que `equal` e que guloso; (H7b) com
  propensão logada IPS é não-viesado, SNIPS/DR têm menor variância, propensão inventada enviesa e sem
  propensão não há OPE.
- **Caso de uso.** Decidir qual campanha recebe a próxima fatia de verba por hora/contexto e, antes
  disso, avaliar offline uma política nova com o log da atual.
- **Baseline.** `equal` (uniforme), guloso por contexto, ε-guloso.
- **Implementação.** `modelos/bandits.py`: `Uniforme`, `Gulosa`, `LinUCB` (disjunto, contexto one-hot),
  `ThompsonLinear` (propensão estimada por Monte Carlo — não tem forma fechada), `rodar` (loga propensão),
  `ips`, `snips`, `dr` (q̂ tabular com cross-fitting) e `PropensaoAusente`.
- **Teste sintético.** Ambiente semi-sintético: 5 campanhas maduras, rodada = hora (1440), recompensa =
  lucro horário verdadeiro escalado pelo dp do 1º dia, contexto = bloco de 6 h × fim de semana; 16 seeds.
  `estavel`: regret LinUCB 134 [106; 163], ε-guloso 203, Thompson 218, guloso 237, equal 687. LinUCB supera
  equal (−553) e guloso (−103 [−168; −52]); Thompson supera equal mas não guloso (−19 [−81; +47]) →
  **H7a refutada** (exigia os dois). Em `quebra_regime_rpm`, Thompson fica pior que guloso (+56 [+6; +109]).
  OPE (logger ε-guloso 0,2; 200 logs num mundo): IPS viés 0,000 ± 0,006 (alvo oráculo) e 0,002 ± 0,002
  (uniforme); propensão inventada (supor uniforme) erra +2,13 ± 0,02 e +0,40 ± 0,004. SNIPS/DR reduzem a
  variância para o alvo oráculo (dp 0,083/0,085 contra 0,088), mas não para o alvo uniforme no `estavel`
  (0,024 contra 0,023). Pelo pré-registro (sem escolher o alvo favorável depois), **H7b
  refutada** na parte de variância; as partes de viés (IPS não-viesado; inventada enviesada) e de recusa
  sem propensão passam nos dois alvos. Sem propensão: `PropensaoAusente`.
- **Limites.** A escolha não altera o mundo (supervisionado→bandit); no VOLC a verba muda leilão e
  saturação. Contexto categórico pequeno. Propensão do Thompson é aproximada.
- **Custo.** Barato. Dado mínimo para OPE: **propensão logada em cada decisão** (o VOLC não loga).
- **Promoção.** Logar propensão (P09-T01/T02) → ≥ 10⁴ decisões contextuais → OPE offline → shadow.
- **Estado.** **testado com sintético**; OPE real **impossível hoje** (sem propensão).

## 8. Predição conformal (lucro diário maduro por campanha)

- **Hipótese.** (H8a) Split conformal com escore escalado cobre ≥ 88% (nominal 90%) no `estavel`; (H8b) na
  quebra de RPM o split cai abaixo de 85% nas campanhas quebradas e ACI recupera 90% ± 3 p.p.
- **Caso de uso.** Intervalo honesto para "lucro de amanhã" (P14-T08: o intervalo herdado do Bola de
  Cristal não cobre o que diz).
- **Baseline.** O próprio split com calibração fixa (e a herança: intervalo histórico não calibrado).
- **Implementação.** `modelos/conformal.py`: `quantil_conformal` (correção de amostra finita),
  `intervalo_conformal`, `escores_escalados`, `aci` (Gibbs & Candès, com atraso de rótulo); bug achado
  pelos testes e corrigido: intervalo infinito não atualizava α (ficava preso).
- **Teste sintético (50×60, 12 seeds; previsão = média dos 7 últimos dias maduros, escala = MAD).**
  `estavel`: split 0,895 [0,886; 0,903], ACI 0,899 → **H8a suportada**. `quebra_regime_rpm`: split 0,877
  no total e 0,866 [0,854; 0,877] nas campanhas quebradas pós-quebra (não caiu abaixo de 0,85, porque a
  previsão por média móvel já se adapta); ACI 0,901 [0,899; 0,904] no total e 0,892 nas quebradas →
  **H8b refutada** na parte da degradação; ACI cumpre a parte da recuperação. Largura mediana ~R$ 14–15.
- **Limites.** Cobertura marginal (não condicional por campanha); o ACI compartilha α entre campanhas.
- **Custo.** Trivial. Dado mínimo: ~15 dias × campanhas de escores maduros.
- **Promoção.** Em dado real: cobertura empírica ≥ nominal − 2 p.p. em ≥ 8 semanas de previsões imutáveis
  gravadas antes do realizado (P14-T06/T08).
- **Estado.** **testado com sintético**.

## 9. Anomalias (valor × lacuna × zero implausível)

- **Hipótese.** (H9a) mediana/MAD e sazonal robusto têm F1 maior que z-score na razão cliques/sessões
  (`outlier_bot`); (H9b) ausência vira lacuna, nunca anomalia de valor, e o null→0 dispara ≥ 1 falso
  alarme por janela fora do ar; (H9c) zero implausível tem recall ≥ 0,8 e precisão ≥ 0,9.
- **Caso de uso.** Separar "fonte caiu" (G/observabilidade) de "valor estranho" (bot, pico) e do "zero
  falso" (Google Ads MCP 0.0.4, coletor R3).
- **Baseline.** z-score com janela móvel; anti-baseline null→0.
- **Implementação.** `modelos/anomalia.py`: `detectar_anomalias` (lacuna explícita + escore só com
  histórico anterior), `escores` (z, MAD, sazonal), `zero_implausivel` (Poisson na mediana recente),
  `nulo_como_zero` (anti-baseline), `precisao_recall`.
- **Teste sintético (12 seeds).** Bot (~240 dias com bot por mundo de 50×60): z precisão 0,75 / recall
  0,20 / F1 0,31; MAD 0,66 / 0,24 / 0,35; sazonal 0,62 / 0,13 / 0,22. MAD − z = +0,04 [+0,02; +0,05];
  sazonal − z = −0,09 → **H9a refutada**; o recall baixo mostra que a rajada horária de bot some no
  agregado diário. Fora do ar: 2936 lacunas classificadas, **0** anomalias de valor em lacuna; o null→0
  dispara 382 alarmes falsos (31,8 por janela) → **H9b suportada**. Zero falso: precisão 0,76 [0,72; 0,80],
  recall 0,87 [0,79; 0,93] → **H9c refutada** (precisão).
- **Limites.** Em produção o sensor perde a campanha (R2): a razão cliques/sessões por campanha não é
  calculável hoje; só por conta. Detecção de bot pede grão horário.
- **Custo.** Trivial. Dado mínimo: série diária com status por fonte.
- **Promoção.** Lacuna ≠ anomalia: regra de contrato, já pronta para G. Detectores de valor: só com rótulo
  real de incidente.
- **Estado.** Lacuna/zero: **testado com sintético** (regra); detectores de bot: **testado com sintético**, fracos.

## 10. Alocação de orçamento (resposta côncava estimada com incerteza)

- **Hipótese.** (H10a) Com variação histórica de orçamento (`mudanca_orcamento`) o alocador côncavo com
  redução por incerteza tem regret menor que `equal` e que o `proporcional` herdado; (H10b) sem variação
  exógena (`estavel`) a curva não é identificável e ele não supera `equal`.
- **Caso de uso.** P09-T11 (allocator em replay offline): quanto de verba por campanha no próximo ciclo.
- **Baseline.** status quo, `equal`, guloso por ROAS (só onde ROAS > 1), `proporcional` herdado (regra do
  `replay.politicas.Proporcional` via `alocar_com_piso`). Todas sob as mesmas restrições.
- **Implementação.** `modelos/alocacao.py`: `ajustar_resposta` (log-log com prior em b, incerteza na
  extrapolação), `alocar_orcamento` (KKT exato por bisseção; igual ao SLSQP no teste), `limites` (mínimo,
  máximo, passo máximo), `projetar`, `verificar_restricoes` (0 violações em todas as políticas e seeds).
- **Teste sintético (40 campanhas, 16 seeds; decisão no dia 30, 12h, para os dias 30–44; avaliação por
  re-simulação CRN; oráculo = MILP na grade 0,5–1,5×).** Histórico de decisão = registros observados lidos
  como painel `as_of` no instante da decisão, só dias com custo **e** receita em maturidade `final`
  (último dia maduro: 27; 86–92% das células do histórico maduras; o resto NaN). `mudanca_orcamento`:
  regret côncava 116 [84; 151], côncava sem aversão 85, guloso 370, proporcional 1385, equal 1865, status
  quo 2064 (R$ em 15 dias) → **H10a suportada** (côncava − equal −1749 [−1968; −1529]; − proporcional −1270
  [−1547; −1005]; − guloso −255 [−380; −136]). `estavel`: côncava 92 contra equal 2141 → **H10b
  refutada**: supera mesmo sem variação exógena. A variação natural de gasto (choques de demanda) já passa
  o critério de identificabilidade (desvio de log gasto ~0,17), b mediano 0,86–0,91 e b no teto (0,95) em
  0,30 (`mudanca_orcamento`) e 0,40 (`estavel`) das campanhas — o alocador degenera em "ordenar por ROAS e
  cortar quem tem ROAS < 1", que é onde está o dinheiro. A aversão à incerteza não mostrou ganho (côncava sem
  aversão teve regret pontual menor, 85 × 116, sem teste pareado). (Errata R2/G10: a versão anterior usava a
  verdade diária do mundo, inclusive os dias ainda imaturos no instante da decisão; com o painel maduro os
  números mudam pouco — 120 → 116 — e os vereditos não mudam.)
- **Limites.** Grade do oráculo é discreta; 15 dias; campanhas independentes; sem interferência de
  leilão entre campanhas; curvatura não identificada (o ganho é de primeira ordem). O `proporcional`
  herdado gasta o total inclusive em campanhas que perdem dinheiro — confirma a herança (pior que
  `equal` em parte dos cenários do replay v0).
- **Custo.** Trivial (KKT). Dado mínimo: ≥ 4 dias com gasto e receita maduros por campanha; para curvatura,
  variação exógena de orçamento.
- **Promoção.** Replay offline com dado real (P09-T11) mostrando regret menor que guloso com IC; depois
  shadow com propostas T1 (P09-T13). Curvatura só com variação de orçamento aleatorizada (backlog ALO-02).
- **Estado.** **testado com sintético**.

## 11. Successive halving / ASHA (só referência)

Herança: 0/360 (pré-registrado) e 0/440 (exploratório) — nenhum candidato superou o melhor baseline
(`greedy_parcial`); saturação (+1794 [1620; 1968]) e maturação heterogênea (+1308) explicam; interferência
favorece SH/ASHA (−220). **Premissa que mudou com o simulador novo:** nenhuma que favoreça SH/ASHA. O
simulador novo tem saturação por orçamento (θ e corte 2×) e maturação heterogênea por fonte (D0 vs
releituras JoinAds) — exatamente as duas causas da derrota — e não tem interferência entre campanhas
(o único fator que favorecia SH/ASHA). Não reaberto. **Estado:** resultado negativo preservado.

## 12. Modelos tabulares (Ridge × HistGradientBoosting, rolling origin, features `as_of`)

- **Hipótese (H12).** Ridge e HGB com features `as_of` e rolling origin não superam a média dos últimos
  dias maduros por mais de 2% de MAE; feature do futuro injetada é detectada por metadado e por ganho
  implausível.
- **Caso de uso.** P14-T07: baseline preditivo do lucro de amanhã sem vazamento ("amanhã = hoje" lado a
  lado; o Bola de Cristal usava features derivadas do alvo).
- **Baseline.** "Último dia maduro" e "média dos dias maduros" (7).
- **Implementação.** `modelos/tabular.py`: `features_no_corte` (só painéis do próprio corte, preliminar com
  indicador de maturidade), `imputar` (média de treino + indicador; nada vira 0 silencioso), `ajustar` /
  `ModeloAjustado` (RidgeCV escalonado; HGB do scikit-learn), `FeatureMeta` + `checar_vazamento`,
  `vazamento_empirico`. Rótulo de treino só entra se custo **e** receita do dia-alvo estavam com maturidade
  `final` no corte de treino.
- **Teste sintético (50×60, 10 seeds, origens 30–58, retreino a cada 5).** `estavel`: MAE média dos maduros
  4,20; Ridge 1,006× [0,989; 1,022]; HGB 1,027× [1,010; 1,043] (pior); último maduro 1,31×.
  `quebra_regime_rpm`: Ridge 1,009×; HGB 1,097× [1,047; 1,157]; último maduro 1,086×. **H12 suportada**
  (nenhum modelo supera a média dos maduros). Vazamento: feature = alvo + ruído (10% do dp) reduz o MAE em
  0,63 [0,57; 0,68]; detectada em 100% das origens pelo metadado e em 100% dos mundos pela checagem
  empírica (limiar de ganho 0,30), com 0% de alarme falso no modelo honesto.
- **Limites.** Horizonte de 1 dia; sem features exógenas (calendário de campanha, leilão); sinal fraco por
  construção do gerador para lucro diário. A checagem empírica é heurística: um ganho grande e legítimo
  também dispara.
- **Custo.** Ridge trivial; HGB segundos por retreino. Dado mínimo: ≥ 30 dias maduros por campanha.
- **Promoção.** Em dado real: ganho fora do tempo com IC < −2% sobre a média dos maduros, previsões
  gravadas imutáveis antes do realizado (P14-T06). Até lá, a média dos maduros é o baseline oficial de
  shadow.
- **Estado.** **testado com sintético** (resultado negativo para modelos; positivo para a checagem de vazamento).

## 13. DuckDB / Polars (só referência)

Herança (`results/bench/BENCH-RESULTS.md`): no replay v0 (≤ ~13 mil obs/corte) não compensam (import
custa 15–45× o replay); em 1e6, Polars 5,1× e DuckDB 4,2× sobre Python puro; corte com dados em tuplas
entre 1e4 e 1e5 obs. Worker B (04 §5.3): snapshot `as_of` completo — DuckDB/Parquet ~10× o PostgreSQL
(1e6: 0,049 s × 0,534 s); 1e7: DuckDB 0,52 s, Polars 1,70 s. **Onde entram:** replay histórico grande
sobre partições frias exportadas para Parquet (≥ 1e5–1e6 observações por corte, ex.: termos/keywords com
~24 mil linhas/semana, ou rolling-origin de meses). **Onde não:** no Model Lab desta missão (o painel
`TabelaVersoes` em numpy faz o corte `as_of` de ~100 mil registros em milissegundos), no kernel e no banco
operacional. Nenhum script deste worker importa DuckDB/Polars.

## 14. Bibliotecas (matriz herdada: só o que mudou)

| item | herança | agora | motivo |
|---|---|---|---|
| CVXPY | adiar (verificador) | **adiar, sem demanda** | o alocador côncavo separável tem solução exata por KKT/bisseção (igual ao SLSQP do scipy em teste) e o oráculo é MILP do scipy (HiGHS) |
| OBP | rejeitar dep.; referência | **mantido; referência cumprida** | IPS/SNIPS/DR implementados em ~40 linhas e testados (IPS não-viesado; DR exato com q̂ perfeito) |
| MABWiser / VW | referência/adiar | **mantido** | LinUCB e Thompson em numpy bastaram; VW só com ≥ 10⁴ decisões contextuais logadas com propensão |
| ruptures (change point) | não avaliado | **adiar: não necessário** | CUSUM e BOCPD mínimos implementados; o gargalo é calibrar FA, não algoritmo |
| MAPIE (conformal) | não avaliado | **adiar: não necessário** | split e ACI em ~60 linhas, cobertura testada |
| LightGBM / CatBoost | adiar | **mantido** | HGB do scikit-learn já não supera a média dos maduros (M12); boosting externo só com volume e sinal |
| ConfSeq | referência | **mantido** | e-processo e CS em numpy cobrem o uso |

Nenhuma dependência nova pedida.

## 15. Tabela-resumo

| # | técnica | veredito (pré-registro) | estado | gatilho de promoção | backlog |
|---|---|---|---|---|---|
| 1a | Chain-ladder diário com guarda (receita) | baseline de shadow; IC80 cobre 70–75% | testado com sintético | replay real com viés IC ∋ 0 | MAT-02, MAT-05 |
| 1a | Bornhuetter-Ferguson (prior histórico) | **refutado** (pior que CL na idade 0) | testado com sintético | prior de plano + replay | MAT-03 |
| 1b | Nowcast intradiário do custo D0 | **suportado** (wMAPE 15% do naive) | testado com sintético | replay v21 ≥ 4 semanas | MAT-01 |
| 1c | Monitor de regime de maturação | **refutado** pré-registrado (não calibra); pós-registro parcial | construído · testado hermeticamente | FA medida em dado real | MAT-04 |
| 2 | EB (CTR, RPM) em campanha nova | **refutado** como um todo; ganha só CTR dia 1 e RPM dia 3 | testado com sintético | ≥ 20 lançamentos reais | EB-01..04 |
| 3 | CUSUM / BOCPD × média móvel | **refutado** (CUSUM +2 p.p.; BOCPD pior, mais rápido) | testado com sintético | quebras anotadas em dado real | CP-01..03 |
| 4 | e-BH / CS em outcome limitado | **suportado** (FDR ≤ q com 50 olhadas; CS cobre; receita recusada) | testado com sintético | experimento real com outcome limitado | SEQ-01..04 |
| 5 | DiD / controle sintético | H5a **refutada** por pouco (lucro); H5b **refutada** (errata R2: DiD enviesado ✓, mas antes/depois menos enviesado ✗); seleção engana DiD e diagnósticos | testado com sintético | mudanças aleatorizadas | CAU-01..04 |
| 6 | Surrogate (portão) | veredito não muda: `dados_insuficientes` (50×90 ainda insuficiente; 50×100 viável no sintético); R2 invisível ao portão | hold | ≥ 50×~100 maduros com feature no grão campanha (R2 corrigido) | SUR-01, SUR-02 |
| 7 | Bandits + OPE | H7a **refutada** (LinUCB supera; Thompson não supera guloso); H7b **refutada** na variância (SNIPS/DR não reduzem para alvo uniforme); viés e recusa ✓ | testado com sintético; OPE real impossível | propensão logada + ≥ 10⁴ decisões | BAN-01..04 |
| 8 | Conformal split / ACI | H8a **suportada**; H8b **refutada** na degradação (ACI recupera) | testado com sintético | previsões imutáveis + 8 semanas | CNF-01, CNF-02 |
| 9 | Anomalia / lacuna / zero | H9a **refutada**; H9b **suportada**; H9c **refutada** (precisão 0,76) | testado com sintético | rótulo real de incidente | ANO-01..04 |
| 10 | Alocação côncava com incerteza | **parcial**: H10a **suportada**; H10b **refutada** (ganho é de primeira ordem: cortar ROAS < 1); histórico as_of maduro (errata R2) | testado com sintético | replay real vs guloso | ALO-01..04 |
| 11 | SH/ASHA | não reaberto; nenhuma premissa mudou a favor | resultado negativo preservado | dado novo sem saturação/maturação heterogênea | SWM-01..04 |
| 12 | Ridge × HGB (rolling origin) + vazamento | H12 **suportada** (Ridge ≈ média dos maduros; HGB pior); vazamento detectado 100%, 0 falso alarme | testado com sintético | ganho fora do tempo com IC em dado real | TAB-01..03 |
| 13 | DuckDB / Polars | só referência (B: ~10× PG em snapshot grande) | adotar no lab, provisório | replay ≥ 1e5–1e6 obs/corte | DAT-02, DAT-03 |
| 14 | Bibliotecas | nenhuma dependência nova | decisão proposta | técnica que scipy/sklearn não cubram | LIB-01 |

## 16. Errata — 2026-10-16 (revisão adversarial R2, `handoffs/REVISAO-ADVERSARIAL-R2.md`)

O pré-registro não foi alterado. Os resultados antigos estão preservados em
`results/fundacao/modelos/errata_20261016/` (`m5_causal_pre_errata.json`, `m10_alocacao_pre_errata.json`);
a tabela "antes × depois" é gerada no fim do `RESUMO.md`.

| achado | correção | veredito antes | veredito depois |
|---|---|---|---|
| G9 | `fundacao_modelos_causal.py` passa a exigir as **duas** condições pré-registradas de H5b (DiD do lucro com IC excluindo 0 **e** antes/depois mais enviesado que o DiD, por diferença pareada de \|viés\|) e o veredito sai do critério (`H5b_criterios`) | H5b suportada | **H5b refutada** (cond. 1 ✓; cond. 2 ✗: −0,38 [−0,71; −0,09]) |
| G10 | `fundacao_modelos_alocacao.py` alimenta as políticas com o painel `as_of` maduro observado no instante da decisão (dias com custo e receita `final`; atraso declarado ~3 dias), não com a verdade diária; §0 deixou de contar M10 como aprovada | H10a sim; H10b não; §0 "três aprovadas" | H10a sim (côncava 116 vs equal 1865); H10b não; §0: duas aprovadas + M10 parcial |
| G13 (parte F, mutante F4) | dois testes de comportamento em `test_modelos_dados.py`: preliminar medida antes e entregue depois da final não a substitui (caso hermético) e equivalência com `visao_as_of` num cenário com coletas atrasadas; ambos falham com o painel ordenado por chegada | mutante sobrevivia (só a guarda de hash o pegava) | mutante morto pelos dois testes |
