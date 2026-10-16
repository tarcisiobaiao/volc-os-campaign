# 10 — Backlog de "ouros" (worker F, Fundação Data Intelligence, 2026-10-16)

Toda ideia futura, PS, hipótese, item não promovido, dependente de escala ou descartado por enquanto —
desta missão (Model Lab, `08-MODEL-LAB.md`) e herdada (1ª execução do Lab: `FINAL-REPORT.md`,
`EXPERIMENT-RESULTS.md`, `LIBRARY-DECISIONS.md`, `ADVERSARIAL-REVIEW.md`, `CATALOG-CLASSIFICATION.md`,
que classifica o catálogo `CATALOGO-DATA-INTELLIGENCE-ENGINES-VOLC-20261015` D01–D53/X01–X10). Uma
entrada por item. Nada aqui é decisão de roadmap: é insumo para o integrador (thread I).

Convenções:
- **Estado honesto** usa a taxonomia do manifesto §7 (`construído` → `testado hermeticamente` →
  `testado com sintético` → `testado em replay` → `rodando em shadow` → `calibrado com dado real` →
  `operacional`; `ainda não demonstrado`), mais `rejeitado`/`hold` quando for o caso.
- **Roadmap mais próximo** = id real de `volc-os-workbook/ROADMAP-VIVO.json` lido no worktree do
  integrador em 2026-10-16 (P06-T09 não existe nesse arquivo; existe só na wip).
- Evidências com caminho relativo à raiz do repositório. `R/` = `experiments/data-intelligence-lab/results/`.
- Pré-requisito transversal a quase tudo: **DAT-01** (snapshot read-only do dado append-only real).

Índice: [Maturação](#maturação) · [EB](#empirical-bayes) · [Mudança](#detecção-de-mudança) ·
[Sequencial](#sequencial-e-fdr) · [Causal](#causal) · [Surrogate](#surrogate) · [Bandits/OPE](#bandits-e-ope) ·
[Conformal](#conformal) · [Anomalia](#anomalia-e-qualidade) · [Alocação](#alocação) · [Tabular](#tabular-e-preditivo) ·
[Swarm/SH](#swarm-sh-asha) · [Dados/infra](#dados-e-infraestrutura) · [Simulador](#simulador) ·
[Bibliotecas](#bibliotecas) · [Catálogo herdado](#catálogo-herdado-d01d53-e-x01x10)

---

## Maturação

### MAT-01 — Custo projetado do dia (nowcast intradiário do D0)
- **Descrição:** dividir o custo D0 lido às h horas pela fração típica do custo final conhecida àquela hora (razão de somas sobre campanha-dias já fechados).
- **Hipótese:** com 14–17 versões D0/dia, o "custo do dia" projetado erra < 50% do que erra usar o D0 como final.
- **Benefício:** decisões intradiárias (pausar/escalar sugerido) deixam de comparar custo parcial com receita de dia cheio.
- **Dependências:** ledger D0 append-only com várias versões por dia (v21 em produção), backfill D+3.
- **Dado mínimo:** ≥ 10 dias com backfill fechado por conta; leituras D0 com `available_at`.
- **Prova possível agora:** replay `as_of` com o snapshot v21 (L10: 14 valores distintos em 16 runs/dia) — bloqueado por DAT-01.
- **Gatilho de promoção:** wMAPE real < 50% do naive em ≥ 4 semanas de replay → shadow com intervalo.
- **Estado honesto:** testado com sintético (H1b suportada: razão 0,151 [0,145; 0,156]).
- **Riscos:** curva real pode depender do pacing e do dia da semana; crédito de inválidos muda o "final".
- **Evidência:** `R/fundacao/modelos/m1_maturacao.json` (B), `modelos/maturacao.py`, `test_modelos_maturacao.py`.
- **Relação:** MAT-05 (intervalo), DAT-01, shadow (D), cockpit de custo.
- **Roadmap mais próximo:** P06-T02 (ingestão de custo por data e conta) · P14-T02 · P09-T09.

### MAT-02 — Chain-ladder diário com guarda como baseline de receita em shadow
- **Descrição:** nowcast da receita JoinAds/GAM por coorte diária usando o fator de coortes maduras (herdado) sobre triângulos montados por `as_of` real.
- **Hipótese:** com cadência estável, erro de ~5% na idade 0 e ~2% na idade 1 (simulação); com cadência alterada, viés grande (MAT-04).
- **Benefício:** ROAS do dia corrente com número e recusa explícita (`insuficiente`) em vez de receita parcial tratada como final.
- **Dependências:** JoinAds v2 append-only com releituras; mesma regra de corte diário.
- **Dado mínimo:** ≥ 14 coortes maduras (D+3 ou mais) por fonte.
- **Prova possível agora:** replay sobre snapshot JoinAds v2 (DAT-01).
- **Gatilho de promoção:** viés com IC contendo 0 e cobertura do intervalo ≥ nominal − 5 p.p. em replay real.
- **Estado honesto:** testado com sintético (herança + `m1` A).
- **Riscos:** intervalo de razão empírica subcobre (IC80 cobre 70–75%); mudança de cadência invisível.
- **Evidência:** `R/statlab/STATLAB-RESULTS.md`, `R/fundacao/modelos/m1_maturacao.json` (A).
- **Relação:** MAT-04, MAT-05, CNF-01.
- **Roadmap mais próximo:** P06-T03 · P09-T10.

### MAT-03 — Bornhuetter-Ferguson com prior de plano
- **Descrição:** estimar o final como observado + (1 − m(a)) × prior, com prior vindo do plano (orçamento × ROAS esperado) em vez da média histórica.
- **Hipótese:** BF só ganha do chain-ladder nas idades curtas se o prior carregar informação que o observado ainda não tem.
- **Benefício:** menos ruído no nowcast do dia 0.
- **Dependências:** plano/meta por campanha versionado; MAT-02.
- **Dado mínimo:** planos registrados antes do dia, ≥ 4 semanas.
- **Prova possível agora:** no simulador com prior "oráculo ruidoso" (não feito).
- **Gatilho de promoção:** MAPE idade 0 menor que CL com IC pareado em replay.
- **Estado honesto:** BF com prior histórico **descartado por enquanto** (H1a refutada: +1,47 p.p. [+0,86; +2,12] pior que CL).
- **Riscos:** prior otimista vira viés sistemático.
- **Evidência:** `R/fundacao/modelos/m1_maturacao.json` (A); E2 de 14/10 (`.claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-B-economia/`, wip).
- **Relação:** MAT-02, ALO-01 (o plano é a alocação).
- **Roadmap mais próximo:** P09-T10.

### MAT-04 — Monitor de regime de maturação (link ratio + CUSUM)
- **Descrição:** comparar a razão de ligação idade→idade+1 das coortes recentes com a das coortes que geram o fator; ao detectar mudança, usar só o regime vigente e recusar até haver base.
- **Hipótese:** corrige o "degrada sem avisar" herdado (viés −68% sob atraso 2,5×).
- **Benefício:** número enviesado vira `insuficiente` com motivo `regime_de_maturacao_mudou`.
- **Dependências:** MAT-02; FA calibrada em dado real.
- **Dado mínimo:** ≥ 30 coortes de referência; ≥ 8 semanas sem mudança conhecida para calibrar FA.
- **Prova possível agora:** calibração de FA em replay real (DAT-01).
- **Gatilho de promoção:** FA ≤ 5%/janela e detecção ≥ 80% em mudanças anotadas (ex.: troca de cadência do coletor JoinAds).
- **Estado honesto:** construído · testado hermeticamente; versão pré-registrada **falhou** (FA 25–52% por mundo); versão conservadora pós-registro calibra no simulador e corta o viés da idade 1 de −35% para −20%, com 48% de recusa — eficácia ainda não demonstrada.
- **Riscos:** cauda pesada da razão; segmentação que erra cedo contamina o fator.
- **Evidência:** `R/fundacao/modelos/m1_maturacao.json` (C), `m1_maturacao_pos_registro.json`.
- **Relação:** CP-01 (mesma família de detector), P14-T08 (drift).
- **Roadmap mais próximo:** P14-T08 · P06-T05.

### MAT-05 — Intervalo calibrado de maturação
- **Descrição:** substituir o intervalo de razão empírica (subcobre) por conformal/ACI sobre os resíduos de maturação.
- **Hipótese:** cobertura ≥ nominal − 2 p.p. com largura parecida.
- **Benefício:** "ROAS do dia entre a e b" com cobertura verdadeira.
- **Dependências:** MAT-02, CNF-01.
- **Dado mínimo:** ≥ 15 coortes maduras de resíduos.
- **Prova possível agora:** no simulador (não feito nesta missão).
- **Gatilho de promoção:** cobertura empírica em replay real.
- **Estado honesto:** ainda não demonstrado.
- **Riscos:** coortes correlacionadas (mesmo fator) → cobertura otimista.
- **Evidência:** cobertura 70–75% do IC80 em `m1` A; F2-04 da revisão adversarial herdada.
- **Relação:** CNF-01, CNF-02.
- **Roadmap mais próximo:** P14-T08.

### MAT-06 — Maturação hierárquica por campanha
- **Descrição:** fator de maturação por campanha encolhido (EB) para o fator da conta/fonte.
- **Hipótese:** campanhas com mix de país/dispositivo diferente maturam diferente; o fator agregado erra por campanha.
- **Benefício:** nowcast por campanha (não só total do dia).
- **Dependências:** MAT-02, EB-01.
- **Dado mínimo:** ≥ 50 campanha-dias maduros por campanha.
- **Prova possível agora:** simulador com heterogeneidade de maturação por campanha (o observador atual usa a mesma curva para todas).
- **Gatilho de promoção:** MAPE por campanha menor que o fator agregado em replay.
- **Estado honesto:** ainda não demonstrado (hipótese).
- **Riscos:** pouco dado por campanha → prior domina.
- **Evidência:** —
- **Relação:** SIM-02.
- **Roadmap mais próximo:** P06-T03.

### MAT-07 — Moeda e câmbio no nowcast (JoinAds em USD)
- **Descrição:** maturar em moeda nativa e converter depois com câmbio datado.
- **Hipótese:** misturar câmbio do dia com receita imatura cria viés que parece maturação.
- **Benefício:** ROAS em BRL sem artefato cambial.
- **Dependências:** `exchange_rate_history`/câmbio datado (v23_01 proposta), P06-T04.
- **Dado mínimo:** série cambial diária.
- **Prova possível agora:** cenário `moeda_misturada` do simulador (câmbio fixo, então não testa variação).
- **Gatilho de promoção:** contrato de câmbio aplicado.
- **Estado honesto:** não testado (herança: "câmbio" não testado).
- **Riscos:** dupla conversão.
- **Evidência:** `FINAL-REPORT.md` (Não testado).
- **Relação:** DAT-05.
- **Roadmap mais próximo:** P06-T04.

## Empirical Bayes

### EB-01 — CTR encolhido no 1º dia de campanha nova
- **Descrição:** Beta-Binomial EB (herdado) para CTR de campanhas com 1 dia de dado.
- **Hipótese:** reduz MSE contra o CTR dos 14 dias seguintes.
- **Benefício:** ranking de novas menos ruidoso no guardião das primeiras horas.
- **Dependências:** coleta D0/D-1 por campanha; ≥ ~10 novas comparáveis.
- **Dado mínimo:** ≥ 20 lançamentos com 15 dias de histórico.
- **Prova possível agora:** replay de lançamentos reais (DAT-01).
- **Gatilho de promoção:** razão de MSE < 1 com IC em replay real.
- **Estado honesto:** testado com sintético (0,70 [0,58; 0,84] no dia 1; sem ganho no dia 3 e 7).
- **Riscos:** prior das novas herda o viés de aprendizado (−19% no dia 1).
- **Evidência:** `R/fundacao/modelos/m2_eb.json`.
- **Relação:** EB-03, P05-T09.
- **Roadmap mais próximo:** P05-T09.

### EB-02 — RPM encolhido (normal-normal) a partir do 2º dia
- **Descrição:** EB normal herdado sobre RPM diário por campanha nova.
- **Hipótese:** reduz MSE no dia 3; não existe no dia 1 (variância intra não identificável).
- **Benefício:** estimativa de RPM de novas sem esperar uma semana.
- **Dependências:** receita madura por campanha (JoinAds `utm_campaign`).
- **Dado mínimo:** ≥ 2 dias por campanha, ≥ 10 campanhas.
- **Prova possível agora:** replay real.
- **Gatilho de promoção:** razão de MSE < 1 com IC.
- **Estado honesto:** testado com sintético (0,84 [0,73; 0,95] no dia 3; 0,97 no dia 7; dia 1 insuficiente).
- **Riscos:** receita imatura no 2º dia (combinar com MAT-02).
- **Evidência:** `R/fundacao/modelos/m2_eb.json`.
- **Relação:** MAT-02.
- **Roadmap mais próximo:** P09-T10.

### EB-03 — Prior com curva de aprendizado
- **Descrição:** prior do EB que conhece a idade da campanha (CTR/CPC esperados por hora de vida, aprendidos de lançamentos passados).
- **Hipótese:** corrige o viés de −19% do CTR do 1º dia que o EB atual não corrige.
- **Benefício:** previsão de regime pós-aprendizado no dia 1.
- **Dependências:** ≥ dezenas de lançamentos com histórico.
- **Dado mínimo:** curva média de aprendizado por conta.
- **Prova possível agora:** simulador (`campanha_nova_aprendendo` tem a curva).
- **Gatilho de promoção:** MSE menor que EB-01 em replay.
- **Estado honesto:** ainda não demonstrado (hipótese desta missão).
- **Riscos:** curva muda com estratégia de lance.
- **Evidência:** viés em `m2_eb.json`.
- **Relação:** EB-01, P05-T09 (janelas nascimento/24 h/24–72 h).
- **Roadmap mais próximo:** P05-T09.

### EB-04 — "Vencedores por sorte" sob shrinkage
- **Descrição:** usar EB para reduzir campanhas promovidas por sorte.
- **Hipótese (herança):** EB reduz de 7,0 para 5,9 em 10.
- **Benefício:** menos escala em falsos campeões.
- **Dependências:** EB-01/02.
- **Dado mínimo:** rótulo de desempenho futuro.
- **Prova possível agora:** feita: no simulador com novas não houve diferença (0,12 [−0,12; 0,38] no dia 1).
- **Gatilho de promoção:** diferença com IC em dado real.
- **Estado honesto:** refutado nesta configuração (sintético); herança positiva em outro gerador.
- **Riscos:** depende de quanto ruído há no ranking.
- **Evidência:** `m2_eb.json`; `R/statlab/shrinkage.json`.
- **Relação:** SEQ-01 (FDR é a alternativa para "vencedor").
- **Roadmap mais próximo:** P09-T09.

## Detecção de mudança

### CP-01 — Alerta de mudança de regime de RPM por campanha
- **Descrição:** CUSUM (ou média móvel) sobre log RPM maduro com limiar calibrado por taxa de alarme falso.
- **Hipótese:** detecta quebra de −40% em ≤ 14 dias com FA ≤ 0,02/semana.
- **Benefício:** invalida fator/modelo da campanha a tempo; dispara revisão humana.
- **Dependências:** receita madura por campanha; MAT-02.
- **Dado mínimo:** 14 dias de referência + 3 de maturação.
- **Prova possível agora:** replay real com quebras anotadas (troca de rede GAM, P06-T03).
- **Gatilho de promoção:** poder ≥ 0,8 e FA ≤ alvo em replay real.
- **Estado honesto:** testado com sintético (CUSUM 0,93; média móvel 0,91; BOCPD 0,81; CUSUM − MM +0,023 [+0,005; +0,040]).
- **Riscos:** quebras pequenas e graduais (não testadas); sazonalidade.
- **Evidência:** `R/fundacao/modelos/m3_mudanca.json`.
- **Relação:** MAT-04, CNF-02, ANO-*.
- **Roadmap mais próximo:** P14-T08 · P06-T05.

### CP-02 — BOCPD como aviso antecipado
- **Descrição:** usar BOCPD quando avisar 1–2 dias antes vale mais que poder.
- **Hipótese:** atraso mediano menor (4,2 × 5,7 dias) com menos poder (0,81 × 0,91).
- **Benefício:** reação mais rápida em quebras grandes.
- **Dependências:** CP-01.
- **Dado mínimo:** idem.
- **Prova possível agora:** feita em sintético.
- **Gatilho de promoção:** custo de atraso medido > custo de alarme perdido.
- **Estado honesto:** testado com sintético (pior em poder).
- **Riscos:** hazard mal escolhido.
- **Evidência:** `m3_mudanca.json`.
- **Relação:** CP-01.
- **Roadmap mais próximo:** P14-T08.

### CP-03 — Calibração de limiar por FA (procedimento geral)
- **Descrição:** todo detector (mudança, anomalia, maturação) tem limiar escolhido por FA medida em dado sem evento, nunca por número mágico.
- **Hipótese:** sem isso, comparações de detectores são inválidas (a CUSUM com referência curta já tem FA não desprezível).
- **Benefício:** alertas com taxa de ruído conhecida.
- **Dependências:** histórico sem eventos.
- **Dado mínimo:** ≥ 8 semanas.
- **Prova possível agora:** `calibrar_limiar` pronto e testado.
- **Gatilho de promoção:** adoção pelo G (observabilidade).
- **Estado honesto:** construído · testado hermeticamente.
- **Riscos:** "sem evento" mal rotulado.
- **Evidência:** `modelos/mudanca.py`, `test_modelos_eb_mudanca.py`.
- **Relação:** G (09), MAT-04, ANO-04.
- **Roadmap mais próximo:** P06-T05 · P10-T04.

## Sequencial e FDR

### SEQ-01 — e-BH para muitos testes com olhada diária
- **Descrição:** e-processos de aposta por célula + e-BH para decidir vencedores com olhadas diárias.
- **Hipótese:** FDR ≤ q mesmo com 50 olhadas, onde BH vai a 0,28 (q = 0,10).
- **Benefício:** experimentos de página/CTA/RSA lidos todo dia sem inflar falsos vencedores.
- **Dependências:** outcome limitado por unidade (sessão chegou ao destino/monetizou), identidade sessão→variante.
- **Dado mínimo:** ~2000 sessões por célula para efeito de 25%; mais para efeitos menores.
- **Prova possível agora:** feita em sintético; real depende de experimento logado.
- **Gatilho de promoção:** primeiro experimento real com outcome limitado logado.
- **Estado honesto:** testado com sintético (H4a suportada).
- **Riscos:** custo de poder com efeito fraco; independência não é exigida, mas outcome tem de ser limitado.
- **Evidência:** `R/fundacao/modelos/m4_sequencial.json`, `modelos/sequencial.py`.
- **Relação:** SEQ-02, SEQ-03, CAU-02.
- **Roadmap mais próximo:** P08-T08 · P05-T10 · P08-T05.

### SEQ-02 — CS para receita só via transformação limitada
- **Descrição:** receita por sessão não tem limite; usar indicador limitado (sessão monetizada) ou esperar janela fechar.
- **Hipótese:** normalizar receita por um "limite" de janela inicial fura o limite (70% das trajetórias).
- **Benefício:** evita intervalo "anytime-valid" falso sobre dinheiro.
- **Dependências:** definição de outcome limitado no contrato.
- **Dado mínimo:** —
- **Prova possível agora:** feita (recusa explícita `ForaDoSuporte`).
- **Gatilho de promoção:** —
- **Estado honesto:** CS sobre receita ilimitada **rejeitada** (herança + `m4`).
- **Riscos:** recortar mede receita truncada, não receita.
- **Evidência:** `m4_sequencial.json`; `R/statlab/STATLAB-RESULTS.md`.
- **Relação:** SEQ-01.
- **Roadmap mais próximo:** P09-T09.

### SEQ-03 — Proibir BH/Wald com peeking
- **Descrição:** regra de leitura: com olhadas repetidas, só procedimento anytime-valid.
- **Hipótese:** BH cumulativo infla FDR para 0,22–0,28; Wald com peeking erra 59–79% (herança).
- **Benefício:** governança de experimento.
- **Dependências:** —
- **Dado mínimo:** —
- **Prova possível agora:** feita.
- **Gatilho de promoção:** adoção em guia de experimento.
- **Estado honesto:** testado com sintético.
- **Riscos:** —
- **Evidência:** `m4_sequencial.json`, `R/statlab/fdr.json`.
- **Relação:** SEQ-01.
- **Roadmap mais próximo:** P15-T09.

### SEQ-04 — e-processo de duas amostras (A/B sem μ0 conhecido)
- **Descrição:** teste de "B > A" por aposta sobre pares/diferenças.
- **Hipótese:** mantém validade com olhadas diárias.
- **Benefício:** A/B real (o M4 testou contra referência conhecida).
- **Dependências:** SEQ-01.
- **Dado mínimo:** idem.
- **Prova possível agora:** implementação + simulação (não feito).
- **Gatilho de promoção:** experimento real.
- **Estado honesto:** ainda não demonstrado.
- **Riscos:** construção errada perde validade.
- **Evidência:** —
- **Relação:** SEQ-01.
- **Roadmap mais próximo:** P08-T05.

## Causal

### CAU-01 — DiD com diagnósticos para mudanças registradas
- **Descrição:** estimar efeito de mudança de orçamento por DiD com IC por unidade, pré-tendência e placebo.
- **Hipótese:** com escolha aleatória, viés pequeno (custo −0,13 [−2,10; +1,80]); com escolha pelo resultado, enviesado e os diagnósticos não avisam.
- **Benefício:** substitui "antes/depois" e "campeões × resto" no cockpit.
- **Dependências:** log de decisão (quem, quando, por quê) e painel maduro balanceado.
- **Dado mínimo:** ≥ 10 tratados e ≥ 10 controles, ≥ 10 dias pré e pós.
- **Prova possível agora:** feita em sintético.
- **Gatilho de promoção:** mudanças com regra de seleção registrada (CAU-02).
- **Estado honesto:** testado com sintético (H5a refutada por pouco no lucro; H5b suportada).
- **Riscos:** seleção pelo resultado; interferência entre campanhas (não simulada).
- **Evidência:** `R/fundacao/modelos/m5_causal.json`, `modelos/causal.py`.
- **Relação:** CAU-02, CAU-03, ALO-02.
- **Roadmap mais próximo:** P15-T09.

### CAU-02 — Mudanças de orçamento aleatorizadas (Intervention Impact Lab)
- **Descrição:** sortear quais campanhas elegíveis mudam e quando (com MDE, janela, washout).
- **Hipótese:** é o único jeito de o DiD/controle sintético medir efeito sem viés de seleção.
- **Benefício:** curva marginal identificável; efeito com IC honesto.
- **Dependências:** governança de proposta/autorização (P09-T02/T03); nada de mutação automática.
- **Dado mínimo:** dezenas de campanhas elegíveis.
- **Prova possível agora:** desenho + simulação de MDE no simulador.
- **Gatilho de promoção:** aprovação humana de um primeiro experimento.
- **Estado honesto:** ainda não demonstrado.
- **Riscos:** custo de oportunidade; operação precisa respeitar o sorteio.
- **Evidência:** viés de H5b em `m5_causal.json`.
- **Relação:** ALO-02, SEQ-01, D20.
- **Roadmap mais próximo:** P15-T09 · P15-T06.

### CAU-03 — Controle sintético para mudança única
- **Descrição:** pesos convexos de campanhas-controle para uma campanha tratada.
- **Hipótese:** útil com poucos tratados; menos enviesado que DiD sob seleção em H5b (custo −0,26 [−0,93; +0,39]), mas enviesado em H5a (custo +2,31).
- **Benefício:** leitura de mudança pontual (ex.: troca de rede GAM numa campanha).
- **Dependências:** doadores com pré-período parecido.
- **Dado mínimo:** ≥ 10 dias pré, ≥ 10 doadores.
- **Prova possível agora:** feita.
- **Gatilho de promoção:** caso real com placebo em espaço.
- **Estado honesto:** testado com sintético (resultado misto).
- **Riscos:** ajuste pré ruim em campanhas extremas.
- **Evidência:** `m5_causal.json`.
- **Relação:** CAU-01.
- **Roadmap mais próximo:** P15-T09.

### CAU-04 — Registrar motivo e regra de seleção das decisões humanas
- **Descrição:** cada mudança proposta/aplicada grava a regra que a escolheu (ex.: "top ROAS 7d").
- **Hipótese:** sem isso, nenhuma atribuição observacional é corrigível.
- **Benefício:** permite ajustar viés de seleção depois.
- **Dependências:** objetos canônicos de proposta/autorização.
- **Dado mínimo:** —
- **Prova possível agora:** —
- **Gatilho de promoção:** P09-T02 fechado.
- **Estado honesto:** ainda não demonstrado (requisito).
- **Riscos:** campo livre vira texto inútil.
- **Evidência:** H5b em `m5_causal.json`.
- **Relação:** BAN-01 (mesmo log, com propensão).
- **Roadmap mais próximo:** P09-T01 · P09-T02.

## Surrogate

### SUR-01 — Surrogate index (receita antecipada por sinais de sessão)
- **Descrição:** prever receita madura por sinais disponíveis em D+1 (sessões, destino), não circulares.
- **Hipótese:** no mundo sintético o sinal é forte por construção (skill ~0,30); no real só se o sensor carregar a campanha.
- **Benefício:** decisão em D+1 em vez de D+3.
- **Dependências:** DAT-07 (sensor com campanha), JoinAds maduro, DAT-01.
- **Dado mínimo:** ver SUR-02 (volume com folga).
- **Prova possível agora:** nenhuma em dado real (R2 deixa ~2% das sessões com campanha).
- **Gatilho de promoção:** portão `viavel_para_teste` em dado real + ganho fora do tempo com IC.
- **Estado honesto:** hold (herança `dados_insuficientes`; simulador não muda o veredito).
- **Riscos:** circularidade (pageviews JoinAds), vazamento temporal.
- **Evidência:** `R/surrogate/SURROGATE-RESULTS.md`, `R/fundacao/modelos/m6_surrogate.json`.
- **Relação:** DAT-07, TAB-01.
- **Roadmap mais próximo:** P08-T07 · P09-T10.

### SUR-02 — Portão do surrogate: folga de volume e tolerância a lacunas
- **Descrição:** o mínimo calibrado (50 × 90, 4500 linhas) exige painel sem nenhuma lacuna (50×90 sintético → `dados_insuficientes`: 4455 linhas, 21 campanhas com profundidade); o portão não mede cobertura de feature (R2 com 1,9% de cobertura passa como `viavel_para_teste`); e, por leitura de código, uma única linha com `disponivel_em` além da tolerância remove a feature inteira.
- **Hipótese:** com dado real (lacunas, coletas atrasadas, sensor sem campanha) o portão erra para os dois lados: fecha no mínimo nominal e abre sem feature utilizável.
- **Benefício:** gatilho de volume realista (≈ 50×100) e veredito que exige cobertura mínima de feature por linha.
- **Dependências:** `volc_dil.surrogate.feasibility` (herdado; não é deste worker).
- **Dado mínimo:** —
- **Prova possível agora:** feita no simulador (`m6_surrogate.json`: 50×90 insuficiente, 50×100/60×100 viável, R2 viável com 1,9% de cobertura); a remoção global por uma linha tardia é inferência de código (`surrogate/feasibility.py`, laço de features), não demonstrada no resultado final.
- **Gatilho de promoção:** mudança no portão revisada adversarialmente.
- **Estado honesto:** achado desta missão (testado com sintético).
- **Riscos:** afrouxar o portão demais deixa entrar vazamento.
- **Evidência:** `m6_surrogate.json` (motivos do portão).
- **Relação:** SUR-01.
- **Roadmap mais próximo:** P09-T10.

## Bandits e OPE

### BAN-01 — Logar propensão em toda decisão de alocação
- **Descrição:** cada decisão (humana ou sugerida) grava a probabilidade com que a ação foi escolhida (1,0 se determinística, com exploração explícita quando houver).
- **Hipótese:** sem propensão não há OPE honesto; propensão inventada depois erra (+2,13 em escala no teste).
- **Benefício:** destrava avaliação offline de qualquer política nova.
- **Dependências:** ledger de eventos/propostas (P09-T01/T02).
- **Dado mínimo:** —
- **Prova possível agora:** `PropensaoAusente` e testes prontos.
- **Gatilho de promoção:** campo no schema de proposta.
- **Estado honesto:** construído · testado com sintético (a recusa).
- **Riscos:** decisões humanas determinísticas não permitem OPE de políticas que escolheriam outra ação (exige exploração).
- **Evidência:** `R/fundacao/modelos/m7_bandits.json`, `modelos/bandits.py`.
- **Relação:** CAU-04, BAN-02, BAN-03.
- **Roadmap mais próximo:** P09-T01 · P09-T02.

### BAN-02 — LinUCB/Thompson em shadow
- **Descrição:** política contextual (hora × fim de semana) sugerindo qual campanha recebe a próxima fatia de verba.
- **Hipótese:** LinUCB tem regret menor que guloso e `equal` (sintético); Thompson não supera guloso.
- **Benefício:** exploração controlada.
- **Dependências:** BAN-01, P09-T13.
- **Dado mínimo:** ≥ 10⁴ decisões contextuais.
- **Prova possível agora:** feita em semi-sintético.
- **Gatilho de promoção:** OPE (BAN-03) positiva com IC em log real.
- **Estado honesto:** testado com sintético (H7a refutada como um todo; LinUCB supera os dois).
- **Riscos:** a verba muda o leilão (não modelado); não estacionariedade (Thompson pior na quebra).
- **Evidência:** `m7_bandits.json`.
- **Relação:** ALO-01, D24.
- **Roadmap mais próximo:** P09-T13.

### BAN-03 — Avaliador off-policy (IPS/SNIPS/DR)
- **Descrição:** estimar o valor de uma política nova com o log da atual.
- **Hipótese:** IPS não-viesado com propensão correta; SNIPS/DR reduzem variância (nem sempre).
- **Benefício:** testar política sem rodá-la.
- **Dependências:** BAN-01.
- **Dado mínimo:** log com propensão > 0 para as ações da política-alvo.
- **Prova possível agora:** feita.
- **Gatilho de promoção:** primeiro log real com propensão.
- **Estado honesto:** testado com sintético.
- **Riscos:** suporte insuficiente (propensão ~0) explode variância.
- **Evidência:** `m7_bandits.json`; `test_modelos_bandits_conformal.py`.
- **Relação:** OBP (referência cumprida).
- **Roadmap mais próximo:** P14-T02 · P09-T11.

### BAN-04 — Vowpal Wabbit
- **Descrição:** contextual bandit industrial (`cb_explore_adf`).
- **Hipótese:** só vale com muito contexto e volume.
- **Benefício:** escala.
- **Dependências:** BAN-01, volume.
- **Dado mínimo:** ≥ 10⁴ decisões contextuais logadas com propensão (herança).
- **Prova possível agora:** —
- **Gatilho de promoção:** o gatilho acima.
- **Estado honesto:** adiar (herança, mantido).
- **Riscos:** opaco para auditoria.
- **Evidência:** `LIBRARY-DECISIONS.md` §2.4.
- **Relação:** BAN-02.
- **Roadmap mais próximo:** P09-T13.

## Conformal

### CNF-01 — Intervalo conformal do lucro diário por campanha
- **Descrição:** split conformal com escore escalado sobre previsão ingênua as_of.
- **Hipótese:** cobre ~90% no estável (0,895 [0,886; 0,903]).
- **Benefício:** substitui o intervalo histórico não calibrado (P14-T08).
- **Dependências:** previsões imutáveis gravadas antes do realizado (P14-T06).
- **Dado mínimo:** ~15 dias × campanhas de escores maduros.
- **Prova possível agora:** feita em sintético.
- **Gatilho de promoção:** cobertura real ≥ nominal − 2 p.p. em ≥ 8 semanas.
- **Estado honesto:** testado com sintético (H8a suportada).
- **Riscos:** cobertura só marginal.
- **Evidência:** `R/fundacao/modelos/m8_conformal.json`, `modelos/conformal.py`.
- **Relação:** CNF-02, MAT-05, TAB-01.
- **Roadmap mais próximo:** P14-T08.

### CNF-02 — ACI sob mudança de regime
- **Descrição:** α adaptativo com rótulo atrasado (maturação).
- **Hipótese:** recupera cobertura de longo prazo sob quebra (0,901 total; 0,892 nas quebradas).
- **Benefício:** intervalo que não envelhece em silêncio.
- **Dependências:** CNF-01.
- **Dado mínimo:** idem.
- **Prova possível agora:** feita.
- **Gatilho de promoção:** idem CNF-01.
- **Estado honesto:** testado com sintético (degradação do split menor que a hipótese: 0,866).
- **Riscos:** γ mal escolhido oscila.
- **Evidência:** `m8_conformal.json`.
- **Relação:** CP-01.
- **Roadmap mais próximo:** P14-T08.

## Anomalia e qualidade

### ANO-01 — Lacuna ≠ anomalia de valor (regra de contrato)
- **Descrição:** ponto sem valor vira `lacuna` e sai do histórico dos detectores; nunca vira 0.
- **Hipótese:** null→0 gera ~32 falsos alarmes por janela de fonte fora do ar.
- **Benefício:** alertas de dado separados de alertas de negócio.
- **Dependências:** status por observação (contrato A).
- **Dado mínimo:** —
- **Prova possível agora:** feita.
- **Gatilho de promoção:** adoção por G.
- **Estado honesto:** testado com sintético (H9b suportada).
- **Riscos:** —
- **Evidência:** `R/fundacao/modelos/m9_anomalia.json`, `modelos/anomalia.py`.
- **Relação:** G (09), P06-T05.
- **Roadmap mais próximo:** P06-T05 · P06-T06.

### ANO-02 — Zero implausível (zero falso de fonte)
- **Descrição:** zero "observado" onde a contagem típica torna o zero improvável (Poisson).
- **Hipótese:** pega o zero do Google Ads MCP 0.0.4 e do coletor R3 sem ler gabarito.
- **Benefício:** zero sintetizado não entra como medição.
- **Dependências:** série por campanha; status da campanha (pausa) para separar zero real.
- **Dado mínimo:** 7 dias anteriores.
- **Prova possível agora:** replay sobre as 110 linhas campaign_day reais (L11: 88 zeradas) — DAT-01.
- **Gatilho de promoção:** precisão ≥ 0,9 com status de campanha cruzado.
- **Estado honesto:** testado com sintético (precisão 0,76, recall 0,87; H9c refutada).
- **Riscos:** campanhas pequenas com zero real.
- **Evidência:** `m9_anomalia.json`; recibo L11.
- **Relação:** ANO-01, G.
- **Roadmap mais próximo:** P06-T08 · P06-T05.

### ANO-03 — Detector de bot por razão cliques/sessões
- **Descrição:** escore robusto sobre log(cliques/sessões) diário.
- **Hipótese:** bots inflam cliques sem sessões.
- **Benefício:** sinal de tráfego inválido antes do crédito do Google.
- **Dependências:** sessões por campanha (bloqueado por R2/DAT-07); grão horário.
- **Dado mínimo:** série horária por campanha.
- **Prova possível agora:** grão horário no simulador (não feito).
- **Gatilho de promoção:** recall ≥ 0,5 com precisão ≥ 0,8 em rótulo real (crédito de inválidos).
- **Estado honesto:** testado com sintético, fraco (F1 0,22–0,35; H9a refutada).
- **Riscos:** no diário a rajada some.
- **Evidência:** `m9_anomalia.json`.
- **Relação:** DAT-07, D35.
- **Roadmap mais próximo:** P06-T06 · P08-T07.

### ANO-04 — Sazonal robusto
- **Descrição:** resíduo contra a mesma fase dos ciclos anteriores.
- **Hipótese:** útil quando o ciclo semanal é forte.
- **Benefício:** menos falso alarme de fim de semana (teste hermético).
- **Dependências:** ≥ 4 ciclos.
- **Dado mínimo:** 28 dias.
- **Prova possível agora:** feita; pior que MAD no `outlier_bot` (−0,09 de F1).
- **Gatilho de promoção:** dado real com sazonalidade forte.
- **Estado honesto:** testado com sintético (sem ganho aqui).
- **Riscos:** histórico curto.
- **Evidência:** `m9_anomalia.json`, `test_modelos_anomalia_alocacao.py`.
- **Relação:** CP-03.
- **Roadmap mais próximo:** P06-T05.

## Alocação

### ALO-01 — Alocador côncavo/ordenação por ROAS em replay offline
- **Descrição:** escolher orçamento por campanha maximizando lucro estimado sob mínimo, máximo, passo e total.
- **Hipótese:** regret muito menor que `equal`/proporcional (sintético), mas o ganho vem de cortar ROAS < 1, não da curvatura.
- **Benefício:** primeiro allocator com restrições verificadas.
- **Dependências:** contrato econômico/snapshot (P09-T10); ROAS maduro por campanha.
- **Dado mínimo:** ≥ 4 dias maduros por campanha.
- **Prova possível agora:** replay offline real (DAT-01).
- **Gatilho de promoção:** regret menor que o guloso com IC em replay real → shadow T1 (P09-T13).
- **Estado honesto:** testado com sintético (H10a suportada; H10b refutada — supera sem variação).
- **Riscos:** campanhas sem consumo de orçamento violam a premissa (P09-T11); interferência de leilão.
- **Evidência:** `R/fundacao/modelos/m10_alocacao.json`, `modelos/alocacao.py`.
- **Relação:** ALO-02, BAN-02, MAT-02.
- **Roadmap mais próximo:** P09-T11 · P09-T12 · P09-T13.

### ALO-02 — Variação exógena de orçamento para identificar curvatura
- **Descrição:** "jitter" pré-registrado de orçamento (±x% sorteado) para medir retorno marginal.
- **Hipótese:** sem variação exógena a curvatura não é identificada (b no teto 0,95 em 32–40% das campanhas no sintético; a variação natural do gasto é endógena).
- **Benefício:** curva marginal de verdade (D18).
- **Dependências:** CAU-02, governança.
- **Dado mínimo:** semanas de jitter.
- **Prova possível agora:** simulação de MDE.
- **Gatilho de promoção:** aprovação humana.
- **Estado honesto:** ainda não demonstrado.
- **Riscos:** custo do jitter.
- **Evidência:** diagnóstico de b em `08` §10.
- **Relação:** CAU-02, D18.
- **Roadmap mais próximo:** P15-T09 · P09-T11.

### ALO-03 — OR-Tools / CVXPY como verificador
- **Descrição:** resolver o mesmo problema com outro solver para conferir.
- **Hipótese:** desnecessário enquanto o problema for separável (KKT exato).
- **Benefício:** restrições não separáveis (cotas por conta, CVaR).
- **Dependências:** dependência nova (pedido ao integrador).
- **Dado mínimo:** —
- **Prova possível agora:** —
- **Gatilho de promoção:** restrição que o scipy (HiGHS/SLSQP) não expressa.
- **Estado honesto:** adiar (herança, mantido).
- **Riscos:** conflito de protobuf (OR-Tools).
- **Evidência:** `LIBRARY-DECISIONS.md` §2.8.
- **Relação:** D26.
- **Roadmap mais próximo:** P09-T11.

### ALO-04 — Risco/downside como métrica, não objetivo
- **Descrição:** reportar drawdown e quantis do lucro por política; não otimizar Mean-CVaR.
- **Hipótese (herança):** Mean-CVaR como objetivo foi refutado (B23).
- **Benefício:** visibilidade de cauda.
- **Dependências:** replay.
- **Dado mínimo:** —
- **Prova possível agora:** adicionar ao relatório de M10 (não feito).
- **Gatilho de promoção:** —
- **Estado honesto:** hold.
- **Riscos:** —
- **Evidência:** `CATALOG-CLASSIFICATION.md` D19.
- **Relação:** D19.
- **Roadmap mais próximo:** P09-T11.

## Tabular e preditivo

### TAB-01 — Baseline preditivo "média dos dias maduros" + Ridge
- **Descrição:** prever lucro final de amanhã por campanha com features as_of e rolling origin.
- **Hipótese:** Ridge/HGB não superam a média dos maduros por > 2% (sinal fraco).
- **Benefício:** baseline honesto para P14-T07 ("amanhã = hoje" lado a lado).
- **Dependências:** P14-T06 (ledger de previsões).
- **Dado mínimo:** ≥ 30 dias maduros por campanha.
- **Prova possível agora:** feita em sintético (Ridge 1,006× [0,989; 1,022] e HGB 1,027× a média dos maduros no `estavel`); real depende de DAT-01.
- **Gatilho de promoção:** ganho fora do tempo com IC em replay real.
- **Estado honesto:** testado com sintético (H12 suportada: modelos não superam o baseline simples).
- **Riscos:** rótulo imaturo no treino; features do alvo.
- **Evidência:** `R/fundacao/modelos/m12_tabular.json`, `modelos/tabular.py`.
- **Relação:** CNF-01, TAB-02.
- **Roadmap mais próximo:** P14-T07.

### TAB-02 — Checagem de vazamento por `disponivel_em` no registry
- **Descrição:** toda feature registrada com o instante em que ficou disponível; treino recusa feature posterior à origem e rótulo imaturo.
- **Hipótese:** pega 100% das features do futuro injetadas; a checagem empírica (ganho implausível) é só complemento.
- **Benefício:** fecha o defeito do Bola de Cristal (features derivadas do alvo).
- **Dependências:** P14-T06.
- **Dado mínimo:** —
- **Prova possível agora:** pronta (`checar_vazamento`, `vazamento_empirico`).
- **Gatilho de promoção:** schema de feature com `disponivel_em` no registry.
- **Estado honesto:** testado com sintético.
- **Riscos:** metadado preenchido errado.
- **Evidência:** `m12_tabular.json`, `test_modelos_tabular_isolamento.py`.
- **Relação:** surrogate (mesma regra), D07.
- **Roadmap mais próximo:** P14-T06 · P14-T10.

### TAB-03 — LightGBM / CatBoost
- **Descrição:** boosting externo.
- **Hipótese:** sem sinal e volume, não ganha do HGB/Ridge.
- **Benefício:** —
- **Dependências:** label econômico, baseline calibrado, ≥ ~5000 linhas fora do tempo, ganho com IC (herança).
- **Dado mínimo:** idem.
- **Prova possível agora:** —
- **Gatilho de promoção:** critérios da herança.
- **Estado honesto:** adiar (mantido).
- **Riscos:** libomp do Homebrew (não hermético).
- **Evidência:** `LIBRARY-DECISIONS.md` §2.6.
- **Relação:** D23.
- **Roadmap mais próximo:** P14-T07.

## Swarm, SH, ASHA

### SWM-01 — SH/ASHA como política de corte de células
- **Descrição:** successive halving sobre células de teste.
- **Hipótese:** perde do guloso sob saturação e maturação heterogênea.
- **Benefício:** —
- **Dependências:** —
- **Dado mínimo:** —
- **Prova possível agora:** —
- **Gatilho de promoção:** só com dado novo que mude a premissa (sem saturação e com maturação homogênea, ou com interferência forte).
- **Estado honesto:** rejeitado como ganho (0/360; 0/440). O simulador novo reforça as duas causas.
- **Riscos:** —
- **Evidência:** `R/swarm/SWARM-RESULTS.md`, `PRE-REGISTRO.md` (swarm).
- **Relação:** D21, D27.
- **Roadmap mais próximo:** P05-T09 · P14-T02.

### SWM-02 — Hyperband como política
- **Descrição:** várias rodadas de SH com orçamentos diferentes.
- **Hipótese:** herda os problemas do SH.
- **Benefício:** —
- **Dependências:** —
- **Dado mínimo:** —
- **Prova possível agora:** simulação (não feita).
- **Gatilho de promoção:** idem SWM-01.
- **Estado honesto:** não testado (herança).
- **Riscos:** —
- **Evidência:** `FINAL-REPORT.md` (Não testado).
- **Relação:** SWM-01.
- **Roadmap mais próximo:** P14-T02.

### SWM-03 — H-01: SH sob valor heterogêneo por evento
- **Descrição:** hipótese da revisão adversarial herdada.
- **Hipótese:** a conclusão H2 do swarm muda se cada evento tiver valor diferente.
- **Benefício:** robustez do veredito.
- **Dependências:** —
- **Dado mínimo:** —
- **Prova possível agora:** simulação.
- **Gatilho de promoção:** —
- **Estado honesto:** não testado.
- **Riscos:** —
- **Evidência:** `ADVERSARIAL-REVIEW.md` §3 (H-01).
- **Relação:** SWM-01.
- **Roadmap mais próximo:** P14-T02.

### SWM-04 — Swarm experimental design (D27)
- **Descrição:** gerador de células e schema de experimento.
- **Hipótese:** útil como desenho, não como otimizador.
- **Benefício:** experimentos com parâmetros explícitos (X06).
- **Dependências:** CAU-02.
- **Dado mínimo:** —
- **Prova possível agora:** herança construída.
- **Gatilho de promoção:** experimento real aprovado.
- **Estado honesto:** construído (sintético).
- **Riscos:** —
- **Evidência:** `R/swarm/`.
- **Relação:** CAU-02.
- **Roadmap mais próximo:** P15-T09.

## Dados e infraestrutura

### DAT-01 — Snapshot read-only sanitizado do append-only real (v21 + JoinAds v2)
- **Descrição:** exportar `google_ads_observation` campaign_day, runs e subconjunto JoinAds v2 para fora do Git, só leitura, para replay `as_of`.
- **Hipótese:** destrava "testado em replay" para MAT-01/02/04, EB-01/02, ANO-02, ALO-01, TAB-01, CNF-01.
- **Benefício:** o maior desbloqueio isolado desta missão.
- **Dependências:** autorização explícita do operador (a exportação foi negada pelo classificador de permissões).
- **Dado mínimo:** 110 linhas campaign_day já existentes (L10/L11) bastam para MAT-01 e ANO-02.
- **Prova possível agora:** nenhuma sem autorização.
- **Gatilho de promoção:** autorização.
- **Estado honesto:** bloqueado.
- **Riscos:** dado sensível; manter fora do Git.
- **Evidência:** `receipts/leituras-externas/RECIBO-LEITURAS-20261016.md` (Ação negada).
- **Relação:** quase todos.
- **Roadmap mais próximo:** P14-T02 · P10-T24.

### DAT-02 — DuckDB/Parquet para replay histórico grande
- **Descrição:** partições frias em Parquet lidas por DuckDB para cortes `as_of` grandes.
- **Hipótese:** ~10× o PostgreSQL em snapshot completo (B); só compensa ≥ 1e5–1e6 obs/corte.
- **Benefício:** rolling-origin de meses e termos/keywords.
- **Dependências:** DAT-01; volume.
- **Dado mínimo:** ≥ 1e5 observações por corte.
- **Prova possível agora:** benchmark de B (feito).
- **Gatilho de promoção:** replay real acima do corte.
- **Estado honesto:** adotar no lab, provisório (herança + B).
- **Riscos:** autoload de extensões (rede); SUM ignora NULL.
- **Evidência:** `R/bench/BENCH-RESULTS.md`; `04-CADENCIA-E-CAPACIDADE.md` §5.3.
- **Relação:** D11, D48.
- **Roadmap mais próximo:** P14-T02 · P10-T24.

### DAT-03 — Polars 2.0 e divergência de ambientes
- **Descrição:** lab trava polars 1.44.2; Freedom Lab usa 2.0.0.
- **Hipótese:** tempos e semântica não transferíveis.
- **Benefício:** um ambiente de experimentação.
- **Dependências:** decisão do integrador (X10).
- **Dado mínimo:** —
- **Prova possível agora:** benchmark 2.0 (não feito).
- **Gatilho de promoção:** decisão de ambiente único.
- **Estado honesto:** não testado (herança H3).
- **Riscos:** breaking changes.
- **Evidência:** `ADVERSARIAL-REVIEW.md` (H3), `CATALOG-CLASSIFICATION.md` D12.
- **Relação:** D12, X10.
- **Roadmap mais próximo:** P10-T24.

### DAT-04 — Determinismo entre plataformas
- **Descrição:** mesmos bytes de resultado em outra máquina/versão de numpy/scipy.
- **Hipótese:** não garantido (versões gravadas no manifesto).
- **Benefício:** reprodutibilidade de auditoria.
- **Dependências:** CI.
- **Dado mínimo:** —
- **Prova possível agora:** rodar em Linux (não feito).
- **Gatilho de promoção:** —
- **Estado honesto:** não testado (herança + E).
- **Riscos:** —
- **Evidência:** `FINAL-REPORT.md`; `07-SIMULATOR-LAB.md` §9.
- **Relação:** todos os resultados.
- **Roadmap mais próximo:** P10-T24.

### DAT-05 — Preliminar enviesado correlacionado à eficiência
- **Descrição:** o preliminar (D0/D-1, intradiária JoinAds) erra mais justamente nas campanhas melhores/piores.
- **Hipótese:** políticas que usam preliminar escolhem errado de forma sistemática.
- **Benefício:** saber quando esperar maturar.
- **Dependências:** DAT-01.
- **Dado mínimo:** pares preliminar × final por campanha.
- **Prova possível agora:** cenário dedicado no simulador (não existe).
- **Gatilho de promoção:** —
- **Estado honesto:** não testado (herança).
- **Riscos:** —
- **Evidência:** `FINAL-REPORT.md` (Não testado).
- **Relação:** MAT-02, ALO-01.
- **Roadmap mais próximo:** P09-T09.

### DAT-06 — pandas
- **Descrição:** não usado no lab.
- **Hipótese:** —
- **Benefício:** —
- **Dependências:** —
- **Dado mínimo:** —
- **Prova possível agora:** —
- **Gatilho de promoção:** —
- **Estado honesto:** não testado (herança; sem necessidade).
- **Riscos:** —
- **Evidência:** `FINAL-REPORT.md`.
- **Relação:** DAT-02.
- **Roadmap mais próximo:** P10-T24.

### DAT-07 — Sensor com campanha (R2) como habilitador de modelos
- **Descrição:** o filtro de PII do Sensor v3/WEBS Wrapper anula `utm_campaign` numérico; sessões não juntam com campanha.
- **Hipótese:** com a campanha preservada, SUR-01, ANO-03 e funil por campanha ficam identificáveis.
- **Benefício:** destrava o grão sessão→campanha.
- **Dependências:** correção do filtro (publicação de GTM proibida nesta missão).
- **Dado mínimo:** —
- **Prova possível agora:** no simulador (`sensor_sem_campanha`: cobertura de sessão no grão campanha ~2%).
- **Gatilho de promoção:** correção publicada e relida.
- **Estado honesto:** confirmado em produção (L4); fora do escopo de F.
- **Riscos:** PII.
- **Evidência:** `01-INVENTARIO-ATUAL.md` §2.4; recibo L4; `m6_surrogate.json`.
- **Relação:** SUR-01, ANO-03.
- **Roadmap mais próximo:** P08-T07 · P06-T07.

## Simulador

### SIM-01 — Recalibrar maturação do simulador com a curva real (L10)
- **Descrição:** ajustar `gads_horas_d0`, crédito D-1, `join_f0`, `join_tau_maturacao_h` à forma real.
- **Hipótese:** muda os números de MAT-01/02, não o veredito qualitativo.
- **Benefício:** sintético mais próximo do real.
- **Dependências:** DAT-01.
- **Dado mínimo:** ≥ 2 semanas de versões D0 e releituras.
- **Prova possível agora:** —
- **Gatilho de promoção:** catálogo sobe de versão.
- **Estado honesto:** pendente (E §9).
- **Riscos:** sobreajuste a poucas campanhas.
- **Evidência:** `07-SIMULATOR-LAB.md` §5/§9.
- **Relação:** MAT-*.
- **Roadmap mais próximo:** P14-T09.

### SIM-02 — Heterogeneidade de maturação, interferência e grão horário no observador
- **Descrição:** maturação por campanha, interferência de leilão entre campanhas da mesma conta, leitura horária.
- **Hipótese:** necessário para testar MAT-06, ALO com interferência e ANO-03 horário.
- **Benefício:** testes mais duros.
- **Dependências:** worker E.
- **Dado mínimo:** —
- **Prova possível agora:** extensão do simulador.
- **Gatilho de promoção:** pedido ao integrador.
- **Estado honesto:** ainda não demonstrado.
- **Riscos:** complexidade.
- **Evidência:** limites declarados em `07-SIMULATOR-LAB.md` §9 e em 08.
- **Relação:** MAT-06, ALO-01, ANO-03.
- **Roadmap mais próximo:** P14-T09.

### SIM-03 — Simulador read-only de `planned_spend`
- **Descrição:** expor o grid gasto→lucro contrafactual (CRN) como ferramenta de cenário.
- **Hipótese:** útil só com modelo calibrado em dado real.
- **Benefício:** "e se eu dobrar?" com intervalo.
- **Dependências:** P14-T08, ALO-01, calibração.
- **Dado mínimo:** —
- **Prova possível agora:** o grid do oráculo de M10 já existe em laboratório.
- **Gatilho de promoção:** modelo aceito.
- **Estado honesto:** construído em laboratório (sintético).
- **Riscos:** confundir simulação com previsão.
- **Evidência:** `scripts/fundacao_modelos_alocacao.py` (oráculo de grade); HANDOFF-E §7.
- **Relação:** ALO-01, P15-T08.
- **Roadmap mais próximo:** P14-T09 · P15-T08.

## Bibliotecas

### LIB-01 — Matriz atualizada (só mudanças)
- **Descrição:** CVXPY sem demanda (KKT exato); OBP: referência cumprida; ruptures/MAPIE: não necessários; LightGBM/CatBoost/VW: mantidos em adiar.
- **Hipótese:** o lab não precisa de dependência nova para nenhuma técnica desta missão.
- **Benefício:** superfície de supply chain menor.
- **Dependências:** —
- **Dado mínimo:** —
- **Prova possível agora:** feita (tudo em numpy/scipy/sklearn).
- **Gatilho de promoção:** técnica que exija o que scipy/sklearn não fazem.
- **Estado honesto:** decisão proposta.
- **Riscos:** —
- **Evidência:** `08-MODEL-LAB.md` §14; `LIBRARY-DECISIONS.md`.
- **Relação:** X10.
- **Roadmap mais próximo:** P10-T24.

## Catálogo herdado (D01–D53 e X01–X10)

Itens do catálogo de motores (classificação na base em `CATALOG-CLASSIFICATION.md`). Os que o Model
Lab cobriu acima apontam para a entrada correspondente; os de outra frente ficam registrados para não se
perderem, com o mínimo de campos (prova possível no Model Lab: nenhuma).

| id | descrição | hipótese | benefício | dependências | dado mínimo | prova possível agora | gatilho | estado honesto | riscos | evidência | relação | roadmap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| D01 | ledger canônico Google Ads | append-only resolve as-of de custo | replay real | v21 renumerado | runs v21 | leitura L1/L9 feita | autoridade de ledger decidida | outra frente (v21 em produção, código em wip) | duas gerações de ledger | 01 §4.1; recibo L1 | DAT-01 | P06-T08 · P10-T16 |
| D02 | cobertura máxima API Google Ads | mais grãos ajudam diagnóstico | explicar não-entrega | credencial/agenda | — | — | P09-T14 | outra frente | escopo | CATALOG D02 | D31 | P05-T07 · P09-T14 |
| D03 | ledger JoinAds | append-only de receita | maturação real | JoinAds v2 | releituras | L5 feita | v2 autoridade | outra frente (v2 em produção) | legado ativo | 01 §2.2 | MAT-02 | P06-T03 · P06-T05 |
| D04 | núcleo econômico | regra única de lucro | contrato | wip | — | — | integração | outra frente (só wip) | 4º vocabulário | CATALOG D04 | P09-T10 | P06-T02..T04 |
| D05 | `value_kind` | 5 classes evitam receita falsa | honestidade | contrato A | — | — | — | parcial (contrato do lab) | 3 × 5 valores | CATALOG D05 | contrato A | P06-T03 · P14-T02 |
| D06 | identidade campanha→funil | junção sessão↔campanha | funil por campanha | DAT-07 | — | — | sensor corrigido | outra frente | PII | CATALOG D06 | DAT-07 | P08-T02 · P08-T07 |
| D07 | snapshot econômico as_of | decisão só com o que se sabia | replay | contrato A | — | `TabelaVersoes` (feito) | P14-T02 | parcial | 3 noções de as-of | 08 §0 | TAB-02 | P09-T09 · P14-T02 |
| D08 | reconciliação/restatement | preliminar ≠ final | lucro honesto | D01/D03 | — | cenários do simulador | — | parcial | — | CATALOG D08 | MAT-02 | P06-T03..T05 |
| D09 | data-quality/deadman | rotina parada visível | confiança | G | — | ANO-01/02 | — | outra frente | — | CATALOG D09 | ANO-* | P06-T05 · P10-T04 |
| D10 | lineage/registry | job → run → dado | auditoria | — | — | — | — | outra frente | — | CATALOG D10 | — | P10-T06 |
| D11 | DuckDB | analítico em processo | replay grande | — | 1e5 obs | B | DAT-02 | parcial/provisório | rede | DAT-02 | DAT-02 | P14-T02 |
| D12 | Polars | DataFrame lazy | idem | — | idem | — | DAT-03 | parcial/provisório | versão | DAT-03 | DAT-03 | P10-T24 |
| D13 | replay as_of realista | política só vê o snapshot | prova antes de shadow | DAT-01 | — | replay v0 (herança) | D (06) | parcial | — | `R/replay/` | D | P09-T09 · P14-T02 |
| D14 | maturação/nowcasting | ver MAT-01..07 | — | — | — | feito | — | testado com sintético | — | MAT-* | MAT-* | P06-T03 · P09-T10 |
| D15 | shrinkage/EB | ver EB-01..04 | — | — | — | feito | — | testado com sintético | — | EB-* | EB-* | P09-T10 · P09-T11 |
| D16 | confidence sequences | ver SEQ-02/03 | — | — | — | feito | — | testado com sintético (limitado) | — | SEQ-* | SEQ-* | P05-T09 · P09-T09 |
| D17 | FDR | ver SEQ-01/03 | — | — | — | feito | — | testado com sintético | — | SEQ-* | SEQ-* | P09-T09 |
| D18 | curvas marginais | ver ALO-02 | — | — | — | — | jitter | não identificável hoje | — | ALO-02 | ALO-* | P09-T10 · P09-T11 |
| D19 | risco/downside | ver ALO-04 | — | — | — | — | — | hold | — | ALO-04 | ALO-04 | P09-T11 |
| D20 | causalidade/MMM | incrementalidade semanal | orçamento entre canais | 2 anos semanais | — | CAU-* (pontual) | P15 | hold/outra frente | uso intradiário indevido | CATALOG D20 | CAU-02 | P15-T02 · P15-T09 |
| D21 | SH/ASHA | ver SWM-01 | — | — | — | — | — | rejeitado como ganho | — | SWM-01 | SWM-* | P05-T09 |
| D22 | surrogate index | ver SUR-01/02 | — | — | — | — | — | hold | — | SUR-* | SUR-* | P09-T10 |
| D23 | gradient boosting | ver TAB-03 | — | — | — | — | — | hold | — | TAB-03 | TAB-* | P14-T07 |
| D24 | bandit contextual | ver BAN-02 | — | — | — | — | — | testado com sintético | — | BAN-* | BAN-* | P09-T11 · P09-T13 |
| D25 | Budget-ROI Allocator | ver ALO-01 | — | — | — | — | — | testado com sintético | — | ALO-01 | ALO-* | P09-T10..T13 |
| D26 | otimização com restrições | ver ALO-03 | — | — | — | — | — | adiar | — | ALO-03 | ALO-03 | P09-T11 |
| D27 | swarm experimental design | ver SWM-04 | — | — | — | — | — | construído | — | SWM-04 | CAU-02 | P15-T09 |
| D28 | três relógios de decisão | janela/observado/disponível | as-of correto | contrato A | — | feito (simulador + TabelaVersoes) | — | testado com sintético | — | 07, 08 | D07 | P06-T05 · P14-T02 |
| D29 | ExperimentService Google | experimento nativo | A/B oficial | API | — | — | — | hold/outra frente | mutação | CATALOG D29 | CAU-02 | P05-T10 |
| D30 | PMax como onda posterior | depois de Search estável | — | Search | — | — | parâmetro, não "150 cliques" | hold | regra fixa | CATALOG D30 | X06 | P05-T07 |
| D31 | diagnóstico de não entrega | — | — | — | — | — | — | outra frente | — | CATALOG D31 | — | P05-T07 |
| D32 | termos/negativas | — | — | — | — | — | — | outra frente | — | CATALOG D32 | — | P05-T08 |
| D33 | clustering semântico | negativar cluster | — | — | — | — | — | hold (refutado, ARI 0,005) | overblocking | CATALOG D33 | — | P05-T08 |
| D34 | pgvector | busca vetorial | — | D33 | — | — | — | hold | migration | CATALOG D34 | — | — |
| D35 | guardião 72 h | janelas de vida | — | — | — | EB-01/03 | — | outra frente (72 h é constante herdada, não regra) | X06 | CATALOG D35 | EB-* | P05-T09 |
| D36 | evolução RSA | experimento controlado | — | — | — | SEQ-01 | — | outra frente | — | CATALOG D36 | SEQ-01 | P05-T10 |
| D37 | policy monitor | — | — | — | — | — | — | outra frente | — | CATALOG D37 | — | P05-T07 · P06-T06 |
| D38 | cliente oficial Google Ads | — | — | — | — | — | — | existente (fora do lab) | — | CATALOG D38 | — | — |
| D39 | GAARF | — | — | — | — | — | — | hold; rejeitado como substituto (NULL→0) | NULL→0 | LIBRARY §2.9 | ANO-02 | P06-T08 |
| D40 | Developer Assistant | — | — | — | — | — | — | hold | executa código | LIBRARY §2.9 | — | — |
| D41 | Google Ads MCP | — | — | — | — | — | release ≥ 1.0 sem NULL→0 | hold (devolve 0 para ausente) | escopo OAuth | LIBRARY §2.9 | ANO-02 | P10-T12 |
| D42 | analista agêntico read-only | — | — | — | — | — | — | outra frente | — | CATALOG D42 | — | P10-T12 |
| D43 | ledger/eval de agentes | — | — | — | — | — | — | outra frente | — | CATALOG D43 | — | P10-T13 |
| D44 | model routing benchmark | — | — | — | — | — | — | outra frente | — | CATALOG D44 | — | P10-T13 |
| D45 | ADSTA/IFTTA | — | — | — | — | — | — | hold (referência) | runtime mutador | CATALOG D45 | — | P09-T08 |
| D46 | Tightlock/first-party | — | — | — | — | — | — | hold/outra frente | upload de valor | CATALOG D46 | — | P06-T07 |
| D47 | Supabase autoridade | — | — | — | — | — | — | existente (respeitar) | — | ADR | — | — |
| D48 | Parquet no lab | — | replay grande | — | — | B | DAT-02 | novo/provisório | — | DAT-02 | DAT-02 | P14-T02 |
| D49 | BigQuery | — | — | — | — | — | ADH/clean room | hold | 2ª autoridade | LIBRARY §2.11 | — | — |
| D50 | ClickHouse | — | — | — | — | — | — | rejeitado agora | 2ª autoridade | LIBRARY §2.11 | — | — |
| D51 | Feast | — | — | — | — | — | — | rejeitado agora | conflito tenacity | LIBRARY §2.11 | — | — |
| D52 | Prefect/Dagster/Airflow | — | — | — | — | — | — | rejeitado (n8n é a agenda) | conflitos | LIBRARY §2.11 | — | P10-T16 |
| D53 | Redis/Ray | — | — | — | — | — | — | redis adiar; Ray rejeitar | — | LIBRARY §2.11 | — | — |
| X01 | centroide das 10–25 conversões | — | — | — | — | — | — | rejeitado | — | CATALOG §3 | — | — |
| X02 | sinal de leilão = receita | — | — | — | — | contrato recusa | — | rejeitado | receita falsa | CATALOG §3 | D05 | — |
| X03 | enviar surrogate ao Google | — | — | — | — | — | — | rejeitado | — | CATALOG §3 | SUR-01 | — |
| X04 | pausar/escalar automático | — | — | — | — | — | — | rejeitado (`NIVEIS_QUE_APLICAM_SEM_HUMANO` vazio) | mutação | CATALOG §3 | ALO-01 | P14-T02 |
| X05 | bloquear ASN/IP por RTT | — | — | — | — | — | — | rejeitado | — | CATALOG §3 | ANO-03 | — |
| X06 | regras fixas universais | números viram parâmetros | — | — | — | todo limiar deste worker é parâmetro | — | rejeitado como política | constantes no código | CATALOG §3 | todos | P05-T09 |
| X07 | 5 células reais + PMax | — | — | — | — | — | — | rejeitado | — | CATALOG §3 | — | — |
| X08 | upsert diário por campaign_id | — | — | — | — | cenário R5 | — | rejeitado (anti-padrão vivo em produção, L2) | sobrescrita | CATALOG §3; recibo L2 | ANO-01 | P06-T02 |
| X09 | LLM decide lucro/budget | — | — | — | — | — | — | rejeitado | — | CATALOG §3 | — | — |
| X10 | libs "WOW" no ambiente principal | — | — | — | — | — | — | rejeitado (dois ambientes divergentes) | supply chain | CATALOG §3 | LIB-01 | P10-T24 |
