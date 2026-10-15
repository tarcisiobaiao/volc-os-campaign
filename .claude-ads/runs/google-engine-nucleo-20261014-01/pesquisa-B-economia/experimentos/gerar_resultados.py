"""Gera pesquisa-B-economia/resultados.json (Pesquisador B). Rodar com -I."""
import json
import sys

DATA = "2026-10-14"
INV = json.load(open(sys.argv[1], encoding="utf-8"))
ALEG = {x["id"]: x["alegacao"] for x in INV["itens"] if x.get("pesquisador") == "B"}
EXP = ".claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-B-economia/experimentos/"
AUD = "pesquisa-B-economia/AUDITORIA-DADOS.md"
PYPI = "https://pypi.org/project/{}/"

itens = []


def item(id, *, fonte, versao, licenca, finalidade, equivalente, requisitos, compat, teste, resultado,
         classe, veredito, correcao, decisao, justificativa, integracao, prereq, alegacao=None):
    itens.append({
        "id": id, "alegacao": alegacao or ALEG[id], "fonte_primaria": fonte, "versao_ou_commit": versao,
        "data_verificacao": DATA, "licenca": licenca, "finalidade_real": finalidade,
        "equivalente_volc": equivalente, "requisitos_dados_acesso": requisitos, "compatibilidade": compat,
        "teste_executado": teste, "resultado_teste": resultado, "classe_prova": classe,
        "veredito_alegacao": veredito, "correcao": correcao, "recomendacao_decisao": decisao,
        "justificativa": justificativa, "possivel_integracao": integracao, "prerequisito_reconsiderar": prereq,
    })


SEM_GRAO = "Receita só existe em campanha×dia (JoinAds/GAM por utm_campaign), sobrescrita, sem as-of (AUDITORIA §1-2)."

item("B01",
     fonte=["https://github.com/VowpalWabbit/vowpal_wabbit", PYPI.format("vowpalwabbit"),
            "https://github.com/VowpalWabbit/vowpal_wabbit/wiki/Contextual-Bandit-algorithms"],
     versao="vowpalwabbit 9.11.9 (PyPI 2026-09-27; GitHub não arquivado, push 2026-09-28)", licenca="BSD-3-Clause (PyPI; GitHub mostra NOASSERTION)",
     finalidade="Aprendizado online (regressão/classificação) e contextual bandits com exploração (--cb_explore_adf) que registra a pmf da ação escolhida.",
     equivalente="Nenhum. O VOLC decide por regras versionadas com aprovação humana (volc_ads/inteligencia_decisao/politicas.py; autonomia.py:32 frozenset()).",
     requisitos="Contexto por decisão, ação, custo/recompensa no mesmo grão e logo após a ação, probabilidade logada. Nada disso existe no ledger v10_02 (AUDITORIA §3).",
     compat="Wheels cp310–cp314; instalou limpo em 3.13 e 3.14 (e4_instalacao.json).",
     teste="E4 smoke: e4_smoke_bandits.py vw (cb_explore_adf, 2000 iterações, contexto único, SINTÉTICO).",
     resultado="Funciona; pmf final [0.867,0.067,0.067] (epsilon 0.2). Smoke, não avaliação.",
     classe="experimento_sintetico", veredito="refutada",
     correcao="VW é ferramenta de bandit/aprendizado online de propósito geral; 'O OURO da AdTech' e 'aprende a cada clique' pressupõem controle por impressão/clique (DSP). O VOLC age em campanha-dia via API de gestão, com recompensa atrasada e reescrita.",
     decisao="rejeitar",
     justificativa="Sem grão de ação compatível, sem recompensa econômica tempestiva e sem propensão logada; autonomia sem humano é proibida hoje.",
     integracao="Só o PADRÃO de logar pmf/probabilidade da ação (ver instrumentação mínima).",
     prereq="Receita reconciliada por grupo/anúncio quase em tempo real + decisões automáticas em volume (milhares/semana) + aprovação do dono para exploração randomizada.")

item("B02",
     fonte=["https://github.com/lightgbm-org/LightGBM (redireciona de microsoft/LightGBM)", PYPI.format("lightgbm")],
     versao="lightgbm 4.7.0 (PyPI 2026-07-18; push 2026-10-14)", licenca="MIT",
     finalidade="Gradient boosting tabular (classificação/regressão).",
     equivalente="Nenhum modelo de CTR/CVR/RPC em produção; o preditivo D+1 do n8n (Ridge/XGBoost) foi rejeitado por target leakage e validação in-sample (SPEC-ORAKUL-DECISION-INTELLIGENCE-V1.md:124).",
     requisitos="Rótulo de receita por clique/grupo maduro e as-of; features disponíveis no momento da previsão. Não existe (AUDITORIA §1-2).",
     compat="Wheels py3 por plataforma (macOS arm64, manylinux), classifiers até 3.14.",
     teste="Nenhum (sem dado real; sintético não testaria a alegação de 92%).", resultado="—",
     classe="doc", veredito="refutada",
     correcao="'Prever valor do clique em 50 ms com 92% de confiança' não tem fonte; 92% não é métrica definida (acurácia? cobertura?). A biblioteca é legítima; a alegação de desempenho não é verificável.",
     decisao="adiar_prerequisito",
     justificativa="Modelo sem rótulo maduro e sem tabela previsão×realizado repete o defeito do preditivo n8n.",
     integracao="Depois de trafego_previsao/realizado: baseline simples (EB/razão) antes de qualquer GBM.",
     prereq="≥ 8 semanas de receita reconciliada por grupo com as-of + tabela de previsões com erro medido fora da amostra.")

item("B03",
     fonte=["https://github.com/catboost/catboost", PYPI.format("catboost")],
     versao="catboost 1.2.10 (PyPI 2026-02-18; push 2026-10-14)", licenca="Apache-2.0",
     finalidade="Boosting com tratamento ordenado de categóricas (target statistics).",
     equivalente="Nenhum.", requisitos="Mesmos de B02 + categóricas com receita no grão (placement/geo/device). Receita por placement/hora é NULL por desenho (v17_04:137-169).",
     compat="Wheels cp38–cp314.", teste="Nenhum.", resultado="—", classe="doc", veredito="parcial",
     correcao="CatBoost de fato lida bem com alta cardinalidade; mas Placement_URL/Geo/Device não têm receita atribuída no VOLC — o modelo não teria rótulo.",
     decisao="adiar_prerequisito", justificativa="Sem receita no grão das categóricas.",
     integracao="—", prereq="Ingestão de receita por land_uri/utm_content (JoinAds) ou placement de origem com atribuição comprovada.")

item("B04",
     fonte=["https://github.com/fidelity/mabwiser", PYPI.format("mabwiser"), "https://doi.org/10.1142/S0218213021500214"],
     versao="mabwiser 2.7.4 (PyPI 2024-08-30; último push 2024-09-05)", licenca="Apache-2.0",
     finalidade="Biblioteca de bandits (TS, UCB, eps-greedy, contextuais) para simulação e produção em lote.",
     equivalente="Nenhum.", requisitos="Recompensa por braço (grupo) observada e comparável; ex.: receita reconciliada por grupo. Não existe (AUDITORIA §2).",
     compat="Wheel py3; instalou em 3.13 e 3.14 (puxa pandas, scikit-learn, seaborn).",
     teste="E4 smoke: e4_smoke_bandits.py mabwiser (TS, 3 braços Bernoulli sintéticos).", resultado="Instala e prediz; escolhe o braço de maior taxa (1.0 em 200 previsões). Smoke.",
     classe="experimento_sintetico", veredito="parcial",
     correcao="TS 'pausa perdedores matematicamente' só com recompensa observável por grupo; manutenção baixa (sem release desde 08/2024). Pausar é ação de gestão aprovada por humano.",
     decisao="rejeitar",
     justificativa="Dependência nova para algo que, quando houver dado, cabe em poucas linhas (Beta-Bernoulli/EB de E1) e entraria como proposta, não ação.",
     integracao="Padrão: probabilidade posterior P(grupo melhor) como evidência na proposta.",
     prereq="Receita por grupo (utm_content) reconciliada + volume.")

item("B05",
     fonte=["https://github.com/sebp/scikit-survival", PYPI.format("scikit-survival")],
     versao="scikit-survival 0.28.0 (PyPI 2026-07-05)", licenca="GPL-3.0-or-later",
     finalidade="Análise de sobrevivência (Cox, RSF, Kaplan-Meier) para tempo-até-evento com censura.",
     equivalente="Gate de maturidade por atraso fixo em intencao.py:704-714 (atraso_conversao_dias); no lab = 0 (politicas.py:62).",
     requisitos="Tempo até a receita ser reportada por coorte = as-of snapshots. Não existe.",
     compat="Wheels cp311–cp314.", teste="Não (E2 cobre a mecânica sem survival).", resultado="—",
     classe="doc", veredito="parcial",
     correcao="Receita de publisher não é evento individual censurado por clique: é soma revisada por coorte (pode até cair). Curva de maturação por razão de somas (chain-ladder/BF) é mais adequada e não exige dependência. Licença GPL-3 contamina distribuição.",
     decisao="rejeitar", justificativa="Modelo errado para o dado + GPL + sem as-of.",
     integracao="—", prereq="Se um dia houver evento individual (conversão offline por gclid) com tempo até evento.")

item("B06",
     fonte=["https://github.com/facebook/prophet", PYPI.format("prophet")],
     versao="prophet 1.5.0 (PyPI 2026-10-05)", licenca="MIT",
     finalidade="Séries temporais aditivas com sazonalidades e feriados (Stan via cmdstanpy).",
     equivalente="SPEC-ORAKUL §6 exige baseline por dia-da-semana antes de usar cost_spike (SPEC:178).",
     requisitos="Série longa e estável de CPC/RPM; RPM horário inexistente (hourly_stats vazia, sem moeda).",
     compat="Wheels py3 por plataforma até 3.14; puxa cmdstanpy.", teste="Nenhum.", resultado="—",
     classe="doc", veredito="parcial",
     correcao="Sazonalidade semanal de CPC é modelável com baseline por dia-da-semana (mediana por DOW); 'intradiária de RPM' não tem dado.",
     decisao="adiar_prerequisito", justificativa="Baseline DOW simples resolve o falso positivo documentado sem dependência pesada.",
     integracao="Baseline DOW como função pura no kernel.", prereq="≥ 8 semanas de série por conta + receita horária com moeda.")

item("B07",
     fonte=["https://github.com/google/or-tools", PYPI.format("ortools"), "https://doi.org/10.1287/opre.27.3.503"],
     versao="ortools 9.15.6755 (PyPI 2026-01-14)", licenca="Apache-2.0",
     finalidade="Programação linear/inteira, CP-SAT, roteamento.",
     equivalente="Nenhum alocador; orçamento é proposta individual com limite % (v17_02 proposta) e sem teto acumulado (GADS-AUTONOMIA-ESTADO.md:13-15).",
     requisitos="Curva de lucro marginal por campanha × nível de verba (resposta à verba). Não há experimento nem histórico de verba variada.",
     compat="Wheels cp39–cp314.", teste="Nenhum.", resultado="—", classe="doc", veredito="parcial",
     correcao="O solver é o menor problema; 'milhares de campanhas maximizando ROAS' exige curvas de resposta identificadas, que não existem. Maximizar ROAS ≠ maximizar lucro.",
     decisao="adiar_prerequisito", justificativa="Sem curva de resposta, o otimizador otimiza ruído.",
     integracao="—", prereq="Experimentos de verba (Google Experiments) ou variação histórica registrada com lucro reconciliado.")

item("B08",
     fonte=["https://github.com/cvxpy/cvxpy", PYPI.format("cvxpy")],
     versao="cvxpy 1.9.3 (PyPI 2026-09-19)", licenca="Apache-2.0",
     finalidade="Modelagem de otimização convexa.", equivalente="Nenhum.",
     requisitos="Mesmo de B07 (curvas côncavas de resposta).", compat="Wheels cp311–cp314.",
     teste="Nenhum.", resultado="—", classe="doc", veredito="parcial",
     correcao="Ferramenta válida; 'portfólio de campanhas' exige retornos e covariâncias estimados — não há.",
     decisao="adiar_prerequisito", justificativa="Idem B07.", integracao="—", prereq="Idem B07.")

item("B09",
     fonte=["https://github.com/optuna/optuna", PYPI.format("optuna")],
     versao="optuna 5.0.0 (PyPI 2026-09-07)", licenca="MIT",
     finalidade="Busca de hiperparâmetros (TPE etc.).",
     equivalente="Limiares do lab são 'calibração sintética' com dono e versão (politicas.py:1-26).",
     requisitos="Função objetivo medida fora da amostra (backtest as-of). Sem as-of, calibrar regras é sobreajuste ao histórico sobrescrito.",
     compat="Wheel py3 até 3.14.", teste="Nenhum.", resultado="—", classe="doc", veredito="parcial",
     correcao="Calibrar limiares por otimização sobre poucos dias reais é sobreajuste; números de regra são do dono (AUTONOMIA-ESTADO.md:28-29).",
     decisao="rejeitar", justificativa="Problema é dado/governança, não busca.", integracao="—",
     prereq="Backtest as-of com centenas de decisões rotuladas.")

item("B10",
     fonte=["https://github.com/pymc-labs/pymc-marketing", PYPI.format("pymc-marketing")],
     versao="pymc-marketing 1.2.0 (PyPI 2026-09-29)", licenca="Apache-2.0",
     finalidade="MMM bayesiano (adstock, saturação Hill/logística), CLV.",
     equivalente="Nenhum.", requisitos="Séries agregadas longas (semanas/meses) de investimento por canal e resultado de negócio.",
     compat="Requer Python ≥3.12; puxa PyMC 6.x/arviz.", teste="Nenhum.", resultado="—", classe="doc", veredito="parcial",
     correcao="Saturação/adstock é ferramenta de MMM agregado (canais × semanas). Para arbitragem em que receita é atribuída por UTM na mesma campanha-dia, o 'ponto de retornos decrescentes' por campanha vem de experimentos de verba, não de MMM.",
     decisao="rejeitar", justificativa="Granularidade e pergunta erradas para o VOLC.", integracao="—",
     prereq="Se o VOLC passar a gerir orçamento de marca multicanal sem atribuição direta.")

item("B11",
     fonte=["https://github.com/google/lightweight_mmm", PYPI.format("lightweight_mmm")],
     versao="lightweight_mmm 0.1.9 (PyPI 2023-05-23); repositório ARQUIVADO no GitHub", licenca="Apache-2.0",
     finalidade="MMM bayesiano leve (numpyro).", equivalente="Nenhum.", requisitos="Idem B10.",
     compat="Pinos antigos (matplotlib==3.6.1, seaborn==0.11.1, tensorflow) — sem chance prática em 3.13/3.14.",
     teste="Nenhum.", resultado="—", classe="doc", veredito="refutada",
     correcao="Projeto arquivado pelo Google; o sucessor é o Meridian (B12).", decisao="rejeitar",
     justificativa="Arquivado + pergunta errada.", integracao="—", prereq="—")

item("B12",
     fonte=["https://github.com/google/meridian", PYPI.format("google-meridian")],
     versao="google-meridian 2.1.0 (PyPI 2026-09-25)", licenca="Apache-2.0",
     finalidade="MMM bayesiano agregado do Google (geo-nível, JAX).", equivalente="Nenhum.",
     requisitos="Idem B10; geo×semana.", compat="Wheel py3; pina numpy<2.4 e arviz<0.20 (conflita com stack numpy 2.5).",
     teste="Nenhum.", resultado="—", classe="doc", veredito="confirmada",
     correcao="Confirmado como sucessor ativo; não se aplica ao problema de arbitragem campanha-dia.",
     decisao="rejeitar", justificativa="Pergunta errada para o VOLC.", integracao="—", prereq="Idem B10.")

item("B13",
     fonte=["https://arxiv.org/abs/1103.4601", "https://doi.org/10.1142/S0218213021500214"],
     versao="algoritmo", licenca="n/a",
     finalidade="Thompson Sampling: escolhe ação amostrando da posterior; exploração proporcional à incerteza.",
     equivalente="Nenhum.", requisitos="Recompensa por keyword/grupo (ROAS) observada; o VOLC não pode dar 'lances' por keyword sob Smart Bidding e não tem receita por keyword.",
     compat="n/a", teste="E1 mostra que a posterior Beta/EB existe e é barata; TS sobre ela não foi testado em dado real.",
     resultado="Ver E1: incerteza por entidade é estimável em dados sintéticos.", classe="experimento_sintetico",
     veredito="parcial",
     correcao="Modelar incerteza do ROAS é correto; 'lances exploratórios' por keyword não é ação disponível (só tCPA/tROAS/orçamento/estratégia).",
     decisao="adiar_prerequisito", justificativa="Falta recompensa no grão e ação no grão.",
     integracao="Usar P(lucro>0) posterior como evidência em propostas.", prereq="Receita por grupo + política de exploração aprovada pelo dono.")

item("B14",
     fonte=["https://doi.org/10.1145/2623330.2623634", "https://arxiv.org/abs/1907.06558"],
     versao="algoritmo (Chapelle 2014; Ktena et al. 2019)", licenca="n/a",
     finalidade="Modelar distribuição do atraso da conversão e corrigir rótulos imaturos (importance sampling) em treino contínuo.",
     equivalente="Gate de maturidade com atraso fixo (intencao.py:704-714).",
     requisitos="Timestamp de clique e de conversão por evento, ou snapshots as-of por coorte.",
     compat="n/a", teste="E2 (mecânica de maturação por coorte, sintético).",
     resultado="Projeção corrigida reduz erro relativo vs ingênuo de 0,49→0,13 (18-24 h) no sintético; depende de as-of.",
     classe="experimento_sintetico", veredito="parcial",
     correcao="Os papers tratam conversão individual em display; receita de publisher é agregada e revisada. O análogo útil é o fator de maturação por idade (E2) — sem as-of não há parâmetro.",
     decisao="adiar_prerequisito", justificativa=SEM_GRAO, integracao="Função pura de projeção BF com guarda (E2).",
     prereq="Tabela append-only de snapshots de receita (ver instrumentação).")

item("B15",
     fonte=["https://doi.org/10.1017/CBO9780511761362 (Efron, Large-Scale Inference)", EXP + "e1_resultado.json"],
     versao="algoritmo", licenca="n/a",
     finalidade="Empréstimo de força entre entidades (keyword→grupo→conta) via prior estimado dos dados.",
     equivalente="Regras com amostra_minima_cliques (intencao.py:215-217; politicas.py:72-74) — corte duro, não shrinkage.",
     requisitos="Contagens por entidade e um nível de agrupamento; para receita, receita no grão (não existe abaixo de campanha).",
     compat="numpy/scipy", teste="E1 (Zipf(1.6), 3.000 entidades, 40 réplicas por κ, SINTÉTICO).",
     resultado="EB ≈ oráculo em todos os κ (ex. κ=2: MSE 96,2 vs oráculo 96,0 vs bruto 183,4 vs mínimo-10-cliques 146,2, ×1e-4). 57% das entidades têm ≤2 cliques mas somam 0,9% dos cliques.",
     classe="experimento_sintetico", veredito="parcial",
     correcao="EB funciona e é barato. '90% das keywords têm 1-2 cliques' não foi medido no VOLC; no sintético, a cauda tem muitas entidades e pouco gasto — o impacto econômico está nas entidades com volume.",
     decisao="extrair_padrao", justificativa="Função pura pequena, sem dependência nova, melhor que corte por mínimo de cliques.",
     integracao="volc_ads/inteligencia_decisao: estimador Beta-Binomial EB para taxas (CTR, IS-like); para receita só quando houver grão.",
     prereq="Para receita: grão grupo/termo com receita reconciliada.")

item("B16",
     fonte=[EXP + "e1_shrinkage.py", "https://en.wikipedia.org/wiki/Beta-binomial_distribution"],
     versao="algoritmo", licenca="n/a",
     finalidade="Shrinkage conjugado para taxas binomiais (cliques/impressões, conversões/cliques).",
     equivalente="Nenhum (há só limiar de amostra).", requisitos="Contagens k/n por entidade (existem para CTR no fato granular keyword/termo).",
     compat="scipy.special.betaln (ou stdlib lgamma)", teste="E1.",
     resultado="MLE de (a,b) recupera κ (κ=20→20,6; κ=500→497). Viés dos 5% 'melhores': bruto +0,31..+0,51; EB ≈ 0.",
     classe="experimento_sintetico", veredito="confirmada",
     correcao="Confirmado para TAXAS. Decisão por estimativa pontual continua errando: use P(p > limiar | dados), não o ponto.",
     decisao="extrair_padrao", justificativa="Elimina maldição do vencedor no ranking de termos/keywords.",
     integracao="Função pura `beta_binomial_eb(k, n)` + `prob_acima(limiar)` em volc_ads/inteligencia_decisao; teste com dados sintéticos de E1.",
     prereq="—")

item("B17",
     fonte=[EXP + "e1_resultado.json"],
     versao="algoritmo", licenca="n/a",
     finalidade="Gamma-Poisson: shrinkage de taxas de CONTAGEM (eventos por exposição). Lognormal: valores estritamente positivos.",
     equivalente="Nenhum.", requisitos="Contagens (pageviews monetizadas/clique) por entidade — não ingeridas por clique.",
     compat="numpy", teste="E1 rpc_lucro (5.000 entidades sintéticas).",
     resultado="59% das entidades com lucro observado ≤ 0 e 16% com receita 0: lognormal é indefinida; ajustada só nos positivos dá lucro médio 0,0181 vs verdadeiro 0,00064 (28×). Gamma-Poisson nas pageviews, lucro derivado: MSE 45,3 vs 83,7 bruto (×1e-6).",
     classe="experimento_sintetico", veredito="refutada",
     correcao="Gamma-Poisson é para contagem, não para RPC/ROAS diretamente; lognormal não representa lucro ≤ 0 nem receita zero. Encolher a contagem e derivar lucro = λ·RPM − CPC; ou normal-normal (James-Stein) sobre médias com variância.",
     decisao="extrair_padrao", justificativa="Evita modelo que apaga o prejuízo.",
     integracao="Documentar no contrato de métricas: lucro nunca modelado em log.", prereq="Contagem de pageviews/sessões por campanha-dia (JoinAds tem impressions; pageviews não).")

item("B18",
     fonte=[EXP + "e1_resultado.json"],
     versao="fórmula", licenca="n/a",
     finalidade="(N·Obs + M·Prior)/(N+M) é a média posterior Beta-Binomial com M = a+b.",
     equivalente="Nenhum.", requisitos="—", compat="—", teste="E1: grade de M em 45 pontos para κ ∈ {2,5,20,100,500}.",
     resultado="M ótimo = κ verdadeiro (2,04; 4,96; 20,6; 102; 506). M=20 custa +34% MSE em κ=2 (132,6 vs 99,2) e +147% em κ=500 (2,40 vs 0,97). Com M=20 a taxa de 'falso lucrativo' segue 37–66% conforme κ.",
     classe="experimento_sintetico", veredito="refutada",
     correcao="M=20 só é ótimo se a dispersão real for κ≈20; M deve ser estimado (EB) por métrica e nível. Não 'impede matematicamente' decisões precipitadas: só reduz variância; a decisão precisa de probabilidade posterior e custo do erro.",
     decisao="rejeitar", justificativa="Constante mágica; EB custa o mesmo e se adapta.",
     integracao="Substituir por EB (B16).", prereq="—")

item("B19",
     fonte=["https://support.google.com/google-ads/answer/2544985", EXP + "e2_resultado.json"],
     versao="algoritmo", licenca="n/a",
     finalidade="Projetar o final de uma coorte imatura: obs / f(idade), f estimado em coortes maduras disponíveis no instante.",
     equivalente="Nenhum. v17_04 marca D0 como 'janela_aberta' e não projeta (v17_04:103-104).",
     requisitos="Snapshots as-of de receita por coorte e idade (não existem: joinads upsert sobrescreve, AUDITORIA §1).",
     compat="numpy", teste="E2 (3 campanhas sintéticas, 240 dias, snapshots 6 h até 168 h, drift no dia 150, backtest só com informação disponível).",
     resultado="18-24 h: ingênuo erro 0,49 (viés −0,49); chain-ladder 0,13; Bornhuetter-Ferguson 0,094. IC90 empírico cobre 84-88% (subcobre); após drift cai a 75%. Backtest com vazamento parece melhor (erro até 13% menor, viés ~35% menor pós-drift). Fator ≈0 (f(6 h)=0,08): CL com guarda deixa 70% 'não apurado'; BF segue com erro 0,13.",
     classe="experimento_sintetico", veredito="parcial",
     correcao="A mecânica é válida; 65%/90%/95% são exemplos. Google documenta SLO de 1 h para custo/cliques e 'competitive metrics' 1×/dia — o '95% do custo em 3 h' não é número oficial. Receita (JoinAds/GAM) não tem curva medida.",
     decisao="adiar_prerequisito", justificativa="Sem as-of não há parâmetro; o resto é barato quando houver.",
     integracao="Função pura projetar_bf(obs, f, prior) com guarda F_MIN e rótulo 'previsto' (nunca fato).",
     prereq="≥ 4-6 semanas de snapshots append-only de receita por campanha-dia.")

item("B20",
     fonte=["docs/architecture/SPEC-ORAKUL-DECISION-INTELLIGENCE-V1.md:139-141", EXP + "e2_nowcasting.py"],
     versao="desenho", licenca="n/a",
     finalidade="Guardar 'o que se sabia às X horas' para estimar maturação e fazer replay honesto.",
     equivalente="trafego_fotografia/previsao/realizado DESENHADAS no SPEC, sem DDL (grep 0). Ledger guarda só hash (v12_04:134).",
     requisitos="Escrita append-only a cada coleta (custo e receita) com lido_em.",
     compat="SQL", teste="E2 usa exatamente essa estrutura no sintético.", resultado="Sem ela, E2 não seria executável.",
     classe="leitura_codigo", veredito="confirmada",
     correcao="Confirmado: é pré-requisito real e é a lacuna nº 1.",
     decisao="adiar_prerequisito", justificativa="Exige migration (decisão do dono).",
     integracao="Tabela receita_snapshot(fonte, date, utm_campaign_value, dominio, revenue, moeda, lido_em, execucao_id) append-only + mesma coisa para custo via ledger com payload.",
     prereq="Migration autorizada.")

item("B21",
     fonte=["https://doi.org/10.1287/opre.27.3.503", "https://developers.google.com/optimization"],
     versao="algoritmo", licenca="n/a",
     finalidade="Escolher um nível de verba por campanha sob orçamento total.",
     equivalente="Nenhum.", requisitos="Lucro esperado por (campanha, nível de verba) com incerteza.",
     compat="ortools", teste="Nenhum.", resultado="—", classe="doc", veredito="parcial",
     correcao="MCKP é correto como formulação; 'regressão log-linear de lucro' é inviável (lucro negativo) e a curva por nível não é identificada sem variação experimental.",
     decisao="adiar_prerequisito", justificativa="Idem B07.", integracao="—", prereq="Idem B07.")

item("B22",
     fonte=["https://arxiv.org/abs/1603.01055", "https://support.google.com/google-ads/answer/2544985"],
     versao="algoritmo", licenca="n/a",
     finalidade="Controle por realimentação de pacing (PID) em RTB.",
     equivalente="Nenhum; ações de lance.alvo com cooldown 24 h (politicas.py:64-66).",
     requisitos="Sinal de erro tempestivo (receita/hora com moeda) e atuador rápido.",
     compat="n/a", teste="Nenhum.", resultado="—", classe="doc", veredito="refutada",
     correcao="PID horário em tROAS/MaxCPC briga com o aprendizado do Smart Bidding (que define lance por leilão); receita horária não existe (hourly_stats vazia, sem moeda); IS é atualizado 1×/dia.",
     decisao="rejeitar", justificativa="Atuador e sinal incompatíveis; risco financeiro.", integracao="—",
     prereq="Nenhum previsível com Smart Bidding.")

item("B23",
     fonte=["https://github.com/dcajasn/Riskfolio-Lib", PYPI.format("Riskfolio-Lib")],
     versao="Riskfolio-Lib 7.4.0 (PyPI 2026-10-04)", licenca="BSD-3-Clause",
     finalidade="Otimização de portfólio (Mean-CVaR etc.).", equivalente="Nenhum.",
     requisitos="Séries de retorno por campanha estacionárias e longas.", compat="Wheels cp310–cp314.",
     teste="Nenhum.", resultado="—", classe="doc", veredito="refutada",
     correcao="Campanha não é ativo líquido com retorno exógeno: verba altera o retorno (leilão) e há poucos dias. Tail risk diário é melhor contido por teto acumulado (que falta: AUTONOMIA-ESTADO.md:13-15, 29).",
     decisao="rejeitar", justificativa="Premissas de finanças não valem.", integracao="Teto acumulado diário (P0 do dono).", prereq="—")

item("B24",
     fonte=["https://developers.google.com/google-ads/api/fields/v25/segments", "https://support.google.com/google-ads/answer/6297",
            "https://support.google.com/google-ads/answer/1722122", "https://support.google.com/google-ads/answer/2544985"],
     versao="Google Ads API v25 (página de campos baixada em 2026-10-14)", licenca="n/a",
     finalidade="GPR para achar 'degrau' de preço no leilão.",
     equivalente="campanha_dia coleta IS diário (volc_ads/coleta/familias/campanha_dia.py:32-38); família hora NÃO coleta IS (hora_dispositivo.py:14-19).",
     requisitos="IS/top_impression_percentage/average_cpc por hora.", compat="—",
     teste="Leitura da lista 'Selectable with' de segments.hour e de metrics.search_impression_share (v25).",
     resultado="search_impression_share, search_top_impression_share, top_impression_percentage, average_cpc são selecionáveis com segments.hour (campaign). Mas 'competitive metrics' são atualizadas 1×/dia; o leilão cobra o mínimo para superar Ad Rank/limiares e 'maior diferença de Ad Rank pode custar mais CPC' — não é segundo preço puro.",
     classe="doc", veredito="refutada",
     correcao="As métricas horárias existem na API; o 'degrau de segundo preço' não existe como objeto estável (Ad Rank com qualidade e contexto por leilão, limiares, Smart Bidding). '40% de desconto mantendo RPM' sem fonte.",
     decisao="rejeitar", justificativa="Mecanismo de leilão alegado é falso; dados horários são médias de milhares de leilões.",
     integracao="Opcional: adicionar IS por hora à família hora como observação, não como controle.", prereq="—")

item("B25",
     fonte=["https://arxiv.org/abs/1701.02490", "https://arxiv.org/abs/1802.08365"],
     versao="papers (WSDM 2017; CIKM 2018)", licenca="n/a",
     finalidade="RL para lance por impressão em RTB (display), com o anunciante controlando o lance.",
     equivalente="Nenhum.", requisitos="Logs por impressão/leilão e controle de lance por requisição.", compat="n/a",
     teste="Nenhum.", resultado="—", classe="doc", veredito="refutada",
     correcao="Os trabalhos existem, mas modelam o DSP; o VOLC compra Google Ads via metas agregadas. tCPA/tROAS como MDP diário não tem dados (dezenas de transições).",
     decisao="rejeitar", justificativa="Problema de outro agente.", integracao="—", prereq="—")

item("B26",
     fonte=["https://github.com/st-tech/zr-obp", PYPI.format("obp"), "https://arxiv.org/abs/2008.07146", "https://arxiv.org/abs/1103.4601"],
     versao="obp 0.5.7 (PyPI 2023-04-14; último push 2024-06-03); requires-python <3.11", licenca="Apache-2.0",
     finalidade="Avaliação off-policy (IPS, SNIPS, DM, DR) sobre logs com propensão.",
     equivalente="Nenhum; ledger sem propensão nem recompensa econômica (AUDITORIA §3).",
     requisitos="Contexto, ação, recompensa, PROBABILIDADE logada da ação, suporte da política de log.",
     compat="0.5.7 recusa Python ≥3.11; em 3.13/3.14 o pip recua em silêncio para 0.4.1 (2021) — e4_instalacao.json.",
     teste="E3 (4 cenários × 300 réplicas, SINTÉTICO) + E3b obp 0.4.1 vs numpy (diferença 0,0).",
     resultado="Boa sobreposição n=5000: IPS viés +0,003, DR +0,003 (cob. 96%). n=200: RMSE 0,11 contra ganho verdadeiro 0,17. Sem suporte (12% do log): DR viés +0,05 com cobertura 25%. Propensão inventada (uniforme): IPS viés +0,45 (dobra o valor), cobertura 0%.",
     classe="experimento_sintetico", veredito="parcial",
     correcao="'Qual teria sido meu ROAS' só se o log tiver propensão real e suporte. Com aprovação humana a propensão é desconhecida; inventá-la produz número falso com cara de ciência.",
     decisao="adiar_prerequisito", justificativa="Mecânica cabe em ~20 linhas; falta o dado.",
     integracao="Logar pmf/elegíveis nas propostas (instrumentação mínima).", prereq="Propensão logada + recompensa econômica + exploração autorizada.")

item("B27",
     fonte=["https://support.google.com/google-ads/answer/10518330?hl=en", "https://developers.google.com/google-ads/api/docs/conversions/conversion-value-rules",
            "backend/app/trafego/perfil_de_mensuracao.py:142-203"],
     versao="doc Google 2026-10-14", licenca="n/a",
     finalidade="Value rules oficiais: ajustar valor por local/dispositivo/público (ADD/MULTIPLY/SET) para refletir valor de negócio diferente.",
     equivalente="RegraDeValor sem_valor/fixo/por_evento, montada e não enviada (perfil_de_mensuracao.py:145-149; data_manager.py).",
     requisitos="Conversão com valor real; margem medida por segmento.", compat="—", teste="Leitura de doc.",
     resultado="Google: Smart Bidding otimiza para os valores ajustados e os relatórios mostram os valores ajustados.",
     classe="doc", veredito="refutada",
     correcao="Multiplicar valor 'quando a margem explode' para forçar o lance é manipular o próprio objetivo: o Smart Bidding passa a perseguir receita inexistente e o relatório de conversão deixa de ser fato. O caminho legítimo é value rule que reflita valor/margem medidos, declarado como regra de valor versionada.",
     decisao="rejeitar", justificativa="Viola fatos ≠ previsões/ajustes e contamina a medição.",
     integracao="Se houver margem medida por segmento: value rule declarada, versionada e auditável.", prereq="Margem por geo/dispositivo reconciliada.")

item("B28",
     fonte=["https://support.google.com/google-ads/answer/10518330?hl=en"],
     versao="ideia", licenca="n/a",
     finalidade="Valor enviado = receita prevista × margem^α × fator de qualidade.",
     equivalente="Nenhum (receita prevista não existe).", requisitos="Receita prevista calibrada + margem por ASN/OS/cidade (não há receita nesse grão).",
     compat="—", teste="Nenhum.", resultado="—", classe="doc", veredito="refutada",
     correcao="α e 'fator de qualidade' são alavancas arbitrárias sobre um valor que já é previsão; o Google não suporta ASN como condição de value rule (local, dispositivo, público).",
     decisao="rejeitar", justificativa="Previsão alavancada enviada como valor = sinal fabricado.", integracao="—", prereq="—")

item("B29",
     fonte=["https://support.google.com/google-ads/answer/2544985", "https://developers.google.com/google-ads/api/fields/v25/segments"],
     versao="ideia", licenca="n/a",
     finalidade="Coletar a cada 15 min e explorar spread EPC intradiário.",
     equivalente="Coleta D0 a cada 6 h planejada (GADS-FATOS-GRANULARES-v17.md:92-94); JoinAds 4×/dia.",
     requisitos="Receita intradiária por geo/device (inexistente) e custo com SLO melhor que 1 h.",
     compat="—", teste="Leitura de doc.", resultado="Custo/cliques: SLO de frescor 1 h; métricas competitivas 1×/dia; receita JoinAds 4×/dia sobrescrita.",
     classe="doc", veredito="refutada",
     correcao="'Anunciantes da ponta B esgotam orçamento às 18h' não é observável pelo VOLC; coletar a cada 15 min não melhora dado com SLO de 1 h e gasta cota. EPC não é métrica do VOLC (AUDITORIA §5).",
     decisao="rejeitar", justificativa="Sem sinal, sem atuador rápido.", integracao="ajuste.horario existe (acoes.py:1587) para decisões semanais com dado maduro.",
     prereq="Receita por hora com moeda e atribuição.")

item("B30",
     fonte=["https://support.google.com/google-ads/answer/7686447?hl=en", "https://developers.google.com/google-ads/api/docs/conversions/upload-adjustments"],
     versao="doc Google 2026-10-14", licenca="n/a",
     finalidade="Ajustes de conversão: RESTATE muda valor (afeta só estratégias de valor/ROAS), RETRACT remove.",
     equivalente="Data Manager monta e não envia (data_manager.py:1-45).",
     requisitos="Conversão por gclid e valor real posterior.", compat="—", teste="Leitura de doc.",
     resultado="Restatement existe; a janela de 7 dias para leitura do autobidding aparece explicitamente para Hotel Ads (55 dias no total); para Search não verifiquei janela equivalente.",
     classe="doc", veredito="parcial",
     correcao="O mecanismo previsão→restatement existe, mas o '$1,85 com 92% de confiança' não tem fonte e enviar previsão como conversão viola a regra fatos ≠ previsões do VOLC, salvo se for uma ação de conversão DECLARADA como valor previsto, com restatement obrigatório e auditoria previsto×realizado.",
     decisao="adiar_prerequisito", justificativa="Sem gclid→receita, sem previsão calibrada e sem autorização de envio.",
     integracao="Contrato: conversão 'valor_previsto' separada do fato, com previsao_id.", prereq="trafego_previsao/realizado + envio autorizado + erro de previsão medido.")

item("B31",
     fonte=["docs/architecture/GADS-AUTONOMIA-ESTADO.md:13-15,29", "supabase/migrations/v17_02_autonomia_gestao.PROPOSTA.sql"],
     versao="ideia", licenca="n/a",
     finalidade="Limites rígidos por ação e por período.",
     equivalente="limite_alteracao_pct=20 por ação (politicas.py:75); v17_02 limita cada ação; NÃO existe teto acumulado.",
     requisitos="Soma de deltas aplicados no dia por campanha/conta.", compat="SQL", teste="Leitura de código.",
     resultado="Por ação existe; acumulado não (5×20% = +149%).", classe="leitura_codigo", veredito="parcial",
     correcao="+30% por vez é número do dono; 'pausar se prejuízo > $X/hora' depende de prejuízo horário que não existe (receita horária NULL).",
     decisao="reutilizar_existente", justificativa="Usar o guardrail existente e implementar o teto acumulado diário já especificado.",
     integracao="Teto acumulado (migration+gatilho) — P0 do dono.", prereq="—")

item("B32",
     fonte=["volc_ads/gestao/acoes.py", "backend/app/trafego/gestao/application/autonomia.py:32"],
     versao="ideia", licenca="n/a",
     finalidade="Sugerir tROAS/MaxCPC/orçamento a cada hora.", equivalente="Propostas tipadas com expira_em e cooldown 24 h.",
     requisitos="Sinal horário de receita; autonomia T2/T3.", compat="—", teste="Leitura de código.",
     resultado="Autonomia vazia por desenho; cooldown 24 h.", classe="leitura_codigo", veredito="refutada",
     correcao="Decisão horária sobre Smart Bidding é ruído e reinicia aprendizado; VW+EB não tem recompensa no grão.",
     decisao="rejeitar", justificativa="Ver B01/B22.", integracao="—", prereq="—")

item("B33",
     fonte=["supabase/migrations/v17_04_arbitragem_reconciliada.sql:84-86", "backend/app/trafego/data_manager.py:1-30"],
     versao="ideia", licenca="n/a",
     finalidade="Join custo×receita e features.",
     equivalente="v17_04 junta por utm_campaign_value=campaign_id e data; gclid não chega à receita.",
     requisitos="gclid no lado da receita (não existe); UTM por campanha (existe).", compat="—",
     teste="Leitura de código.", resultado="Join por gclid impossível; por UTM/campanha-dia existe e já tem status de reconciliação.",
     classe="leitura_codigo", veredito="parcial",
     correcao="Polars/DuckDB são indiferentes; o gargalo é a chave. Para grupo: ingerir utm_content (custom_key aceita).",
     decisao="reutilizar_existente", justificativa="v17_04 já é o join certo e honesto.", integracao="Aplicar v17_04 + ingestão por utm_content.", prereq="—")

item("B34",
     fonte=[AUD + " §5"],
     versao="alegação", licenca="n/a",
     finalidade="Objetivo de arbitragem.", equivalente="Lucro/ROAS/receita por clique só reconciliados (v17_04:128-134).",
     requisitos="RPC = receita/clique pago; RPM = receita/mil impressões ou pageviews.", compat="—",
     teste="Leitura de código.", resultado="Spread CPC×RPM tem denominadores diferentes; a ponte é pageviews por clique (não ingerida).",
     classe="leitura_codigo", veredito="parcial",
     correcao="Objetivo correto é LUCRO reconciliado e maduro (receita − custo), não spread 'em tempo quase real' (receita reescrita por 3 dias). Comparar CPC com RPC (mesmo denominador), não com RPM.",
     decisao="reutilizar_existente", justificativa="v17_04 já define lucro/RPC corretamente.", integracao="Rotular RPC vs RPM no contrato de métricas.", prereq="—")

item("B35",
     fonte=[EXP + "e5_funis.py", "src/utils/roasCalculations.ts:152-155", "src/hooks/useDisplayROI.ts:71-78"],
     versao="operacional", licenca="n/a",
     finalidade="Proporção de campanhas lucrativas por modelo de funil/diretório.",
     equivalente="Faixas de cor sobre excedente% pontual (≥80/≥40/≥0) e status_roi (≥20) sem amostra; vínculo campanha→funnel_run_id em trafego_vinculo (v9_01:838-873).",
     requisitos="campanha→funil (trafego_vinculo.funnel_run_id, só confirmado), versão formal do modelo (NÃO existe), URL final (fato_granular url), lucro diário reconciliado (v17_04), início/fim de vida (proxy: 1º/último dia com custo).",
     compat="stdlib", teste="E5 (5 modelos sintéticos, 3 a 150 campanhas).",
     resultado="Com 3 campanhas Wilson95 = [0,10; 0,91]; o modelo com p verdadeira 0,55 aparece com 42% observado e o de p=0,40 com 50%: ordenar por % observada inverte. n≈97 campanhas para ±10 pp.",
     classe="experimento_sintetico", veredito="parcial",
     correcao="Relatório útil se: classes com intervalo (lucrativa/prejuízo/indeterminada/não elegível), coorte por janela de lançamento e vida mínima, Wilson por modelo com n, sem limiar de vencedor; prefixo de URL (/r, /wg) é diretório, não versão.",
     decisao="extrair_padrao", justificativa="Funções puras pequenas (wilson, classificar_campanha).",
     integracao="volc_ads ou backend/app/trafego (domínio puro) + view somente leitura sobre v17_04.",
     prereq="Versão formal do modelo de funil no vínculo; v17_04 aplicada.")

item("B36",
     fonte=["volc_ads/campanha/marcacao.py:146-161", "n8n/gerar_flows_joinads.py:393-396", "supabase/migrations/v17_01_gads_fatos_granulares.sql:55-117"],
     versao="operacional", licenca="n/a",
     finalidade="ROAS por grupo/anúncio.",
     equivalente="Custo por keyword/termo/asset existe; custo por anúncio não é família; receita só campanha-dia.",
     requisitos="Receita por utm_content (=adgroupid) via JoinAds custom_key; anúncio exigiria chave aceita pela fonte (vc_creative não está na lista).",
     compat="—", teste="Leitura de código.", resultado="Não há atribuição observada abaixo de campanha. Grupo é tecnicamente ingerível; anúncio não pela JoinAds.",
     classe="leitura_codigo", veredito="parcial",
     correcao="'Anúncio caro pode ser o mais lucrativo' é verdade conceitual, mas hoje não é observável; rateio por custo/cliques é suposição (receita/clique igual entre grupos), não atribuição.",
     decisao="adiar_prerequisito", justificativa="Rateio produziria ROAS por grupo idêntico ao da campanha — zero informação.",
     integracao="Segundo pedido /key-value com custom_key=utm_content → tabela por (date, utm_content); reconciliar soma dos grupos com o total da campanha.",
     prereq="utm_content={adgroupid} confirmado nas campanhas vivas + ingestão + reconciliação soma = campanha.")

# Itens novos
item("B37", alegacao="(novo, origem: E2) Chain-ladder / Bornhuetter-Ferguson como forma correta do 'fator de maturação'.",
     fonte=["https://doi.org/10.2143/AST.23.2.2005092 (Mack 1993)", EXP + "e2_resultado.json"],
     versao="algoritmo atuarial", licenca="n/a",
     finalidade="f(idade)=Σobs/Σfinal em coortes maduras (razão das somas); BF = obs + (1−f)·prior estável quando f≈0 e para coortes pequenas.",
     equivalente="Nenhum.", requisitos="As-of snapshots.", compat="stdlib", teste="E2.",
     resultado="BF ≤ CL em quase todas as idades; em f≈0 BF mantém erro 0,13 onde CL vira 'não apurado' em 70%.",
     classe="experimento_sintetico", veredito="confirmada", correcao="—", decisao="extrair_padrao",
     justificativa="Função pura de 10 linhas; resolve f≈0 e coorte pequena.",
     integracao="projetar_receita_bf() rotulada como previsão.", prereq="As-of snapshots.")

item("B38", alegacao="(novo, origem: E5) Intervalo de Wilson para proporções de campanhas lucrativas.",
     fonte=["https://doi.org/10.1080/01621459.1927.10502953"], versao="Wilson 1927", licenca="n/a",
     finalidade="IC de proporção com boa cobertura em n pequeno.", equivalente="Nenhum.", requisitos="k, n.",
     compat="stdlib (math)", teste="E5.", resultado="1/2 → [0,09; 0,91]; 20/50 → [0,28; 0,54].",
     classe="experimento_sintetico", veredito="confirmada", correcao="—", decisao="integrar_agora",
     justificativa="Função pura, sem dependência, evita ranking por acaso.",
     integracao="Relatório de funis e qualquer % de sucesso exibida.", prereq="—")

item("B39", alegacao="(novo, origem: auditoria) A v17_04 chama de 'reconciliada' receita ainda reescrita e junta datas sem checar fuso.",
     fonte=["supabase/migrations/v17_04_arbitragem_reconciliada.sql:84-86,103-105", "n8n/gerar_flows_joinads.py:590-600"],
     versao="v17_04 (não aplicada em produção segundo GADS-FATOS-GRANULARES-v17.md:48-49)", licenca="n/a",
     finalidade="Gate de maturidade e fuso na view de arbitragem.", equivalente="janela_fechada só do custo.",
     requisitos="receita_atualizada_em já existe na view; fuso da conta (customer.time_zone).", compat="SQL",
     teste="Leitura de código.", resultado="'reconciliada_fonte_unica' pode sair com receita do D-1 que ainda será revisada até D+3; contas fora de America/Sao_Paulo deslocam receita.",
     classe="leitura_codigo", veredito="confirmada", correcao="—", decisao="reutilizar_existente",
     justificativa="Ajuste pequeno antes de aplicar a v17_04: status 'receita_imatura' quando metric_date > hoje−3 (ou idade < N do lookback) e 'nao_reconciliada_fuso' quando fuso ≠ America/Sao_Paulo.",
     integracao="Emenda na v17_04 (integrador decide).", prereq="—")

item("B40", alegacao="(novo, origem: auditoria) Câmbio: congelado 5,25 + 5,50/5,35 no front + recálculo retroativo no SQL legado.",
     fonte=["docs/growth-engine/legado-n8n/conflitos.md:252,261-266", "src/sql/add_revenue_converted_column.sql:16,33-60", "docs/closure/traffic-operational-closure-v2/METRIC-CONTRACT.json:103-108"],
     versao="estado do repo 2026-10-14", licenca="n/a", finalidade="Moeda da receita.",
     equivalente="Requisito já escrito: fx_rate(effective_date, rate, source, fetched_at) pela data do fato (METRIC-CONTRACT.json:107).",
     requisitos="Tabela de câmbio versionada.", compat="SQL", teste="Leitura de código.",
     resultado="'GAM 5,50 × JoinAds 5,20' foi refutado pelo próprio repo para produção (mesma função, 5,25); o defeito vivo é câmbio congelado e embutido.",
     classe="leitura_codigo", veredito="confirmada", correcao="A divergência 5,50×5,20 é do espelho, não de produção.",
     decisao="adiar_prerequisito", justificativa="Migration e decisão de produto.", integracao="—", prereq="Tabela fx versionada aplicada.")

json.dump(itens, open(sys.argv[2], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(len(itens), "itens")
