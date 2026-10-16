# EXPERIMENT-RESULTS — VOLC Data Intelligence Lab (2026-10-15/16)

Consolidação do integrador, **atualizada após a revisão adversarial** (`ADVERSARIAL-REVIEW.md`). Todo número abaixo vem de um JSON versionado com manifesto
(seed, hashes de entrada, versões e, quando aplicável, hash de código e de resultado). Tudo é
**sintético** ou **n minúsculo real**: nenhum resultado é validação real. Detalhes em
`experiments/data-intelligence-lab/results/<frente>/`.

Legenda: **D** demonstrado (código + teste/execução reproduzível) · **I** inferido · **H** hipótese · **NT** não testado.

## Q1 — Contrato mínimo de dado econômico confiável

**D.** `volc_dil.contracts` + `CONTRATO-DADO-ECONOMICO.md`: identidade (conta, tipo, id, grão, dimensões), micros+moeda, `null≠0` com estado e motivo, três relógios (janela, `observado_em`, `disponivel_em`), fonte/versão/coleta/linhagem, cobertura, maturidade, método de atribuição, `value_kind` (5 classes), snapshot `as_of` com versões e fingerprint, rótulo econômico e detector de circularidade. Endurecido após F1 (UTC canônico, grão como conjunto, duplicata recusada, contribuição marcada, enums coagidos, manifesto imutável, regra única de circularidade); contraprovas em `test_contracts.py` e fixture reproduzida byte a byte. Lado da fonte (o que a coleta precisa emitir): `DATA-CAPABILITY-MATRIX.md` §6(a).

## Q2 — Dados existentes, faltantes e grão relacionável

**D** (auditoria A, `DATA-CAPABILITY-MATRIX.md`, `CATALOG-CLASSIFICATION.md`):

- Base real não tem as-of: custo e receita são latest-wins/upsert; JoinAds legado com `revenue DEFAULT 0` e gatilho que sobrescreve receita campanha-dia e insere custo 0 (anti-padrão X08 vivo).
- Núcleo econômico, ledger Google Ads v21 (com colisão de numeração) e JoinAds v2 append-only existem só em `wip/*`.
- Grão relacionável sem inventar identidade: **campanha × dia** via `utm_campaign_value = campaign.id`. Sessão/clique: **não relacionável** (sensor sem click id; receita agregada).
- Dados reais versionados com rótulo: Senac (1 campanha, 16 dias maduros) e golden Meta×GAM (62 campanha-dias, 7 campanhas; conjunto/dia é rateio).
- Arquivo sensível versionado fora do namespace: `docs/growth-engine/diagnostico/evidencia.json` (inclui `billing_setup.payments_account`) — não usado; ver handoff.

## Q3 — DuckDB + Polars melhoram o replay atual?

**D** (frente C, `results/bench/BENCH-RESULTS.md`):

| Pergunta | Resposta |
|---|---|
| Replay atual (`inteligencia_decisao/replay.py`, 8 cenários) | **Não.** Executa em 2,7 ms; só `import duckdb` custa 35–120 ms (+100 MB) e `import polars` ~50 ms (+60 MB). Ele também não é replay temporal (um `as_of` fixo, compara 4 campos categóricos). |
| Replay econômico em volume | **Depende do volume.** Mesma operação, mesma linha de resultado entre contrato/python/duckdb/polars inclusive com duplicata exata, moeda nula e linha malformada (após F1-03). Em 1e6, sobre Python puro: Polars (Parquet) 5,1×, DuckDB 4,2×, Polars partindo de tuplas (com conversão) 2,5×; pico de RSS do Polars 1,8–2,0 GB. Com os dados já em tuplas (caso do replay), o corte fica entre 1e4 e 1e5 obs. Snapshots do replay v0: ≤ ~13 mil obs → **ainda não compensa**. |
| Gargalo real | `Snapshot.construir` (80–84% do tempo do replay; `sha256_de` 41%, `para_json` 27%). Otimizado pelo integrador (`7fd5a029`: 501 unidades, 217 → 142 ms por decisão); contrato ainda 12× mais lento que tuplas em 1e5. |
| Riscos | `SUM` de DuckDB/Polars ignora NULL e Polars devolve 0 em grupo todo nulo (pego pelo teste de hash); DuckDB não lê frame Polars sem pyarrow (troca por Parquet); Freedom Lab usa polars 2.0.0 (tempos não transferíveis). |

**Decisão:** DuckDB/Polars ficam como **adotar no laboratório, provisório**; não entram no kernel nem no replay atual.

## Q4 — Replay `as_of` sem futuro, preservando null, moeda, frescor e linhagem

**D** (frente C, `results/replay/REPLAY-RESULTS.md`, 17 testes): políticas recebem só o `Snapshot` com `politica_futuro="falhar"`; contraprovas de futuro, null-como-zero (auditoria metamórfica), moeda misturada, identidade trocada, restatement (decide com a versão preliminar conhecida em t) e determinismo byte a byte. Baselines (30 seeds, diferença pareada vs `equal`, IC95): `greedy_conservador` melhor só no estacionário (−91 bps [−172; −9]); `proportional` significativamente **pior** no estacionário (+516 [+172; +861], cauda pesada) e com lacunas altas (+587); na quebra de regime e no preliminar otimista **nenhuma política supera `equal`**; `static` é pior em todos. A anti-baseline null→0 tem a pior média em todos os cenários e a auditoria (perturbação de uma unidade) a marca em 100% dos casos do reprodutor do revisor. Uso de preliminar é **medido** pelo efeito (reexecução sem preliminares), não autodeclarado.
**Limite aceito:** o isolamento política×simulador é por regra de código (AST), não criptográfico.

## Q5 — Baselines estatísticos simples

**D em simulação** (frente D, `results/statlab/STATLAB-RESULTS.md`):

| Método | Resultado |
|---|---|
| Maturação chain-ladder com guarda | MAPE 0,70 na idade 0, 0,22 em 3–6 d, 0,047 em 14–29 d; com fator ~0 ou reporte D+1, 100% vira `insuficiente` (sem guarda: inf/NaN). Mudança de regime (atraso 2,5× mais lento): viés −69% em 1–2 d e cobertura 29–45% — **degrada sem avisar**. Viés com IC por mundo (após F2-04): estável 1–2 d +1,0% [−4,3; +6,3] (sem viés detectável, não demonstra viés pequeno); D+1 com guarda −11,0% [−18,9; −2,4] (viés de seleção do guarda se sustenta); centavo idade 0 **não demonstrado**. |
| Intervalo por bootstrap só do fator | cobertura 15–30% → **refutado** (razão empírica: 80–95%). |
| EB Beta-Binomial | MSE 0,28 do cru, vencedores por sorte 7,0 → 5,9 em 10; cobertura do top-10% cai a 54–57% em casos adversos. |
| Gamma-Poisson em dinheiro | **inadequado** (depende da escala; cobertura 0,2–10%). Hurdle (Beta-Binomial × lognormal EB): MSE 0,08–0,27 do cru, cobertura 88–89%. |

## Q6 — Confidence sequences mantêm cobertura?

**D em simulação:** CS PrPl-EB (Waudby-Smith & Ramdas 2024) em NumPy, outcome em [0,1]: erro uniforme 0,8–1,9% (α=5%) vs Wald recalculado a cada passo 59–79%. Custo: decide em 53% dos casos vs 99% do Wald de horizonte fixo; ~2× mais larga.
**Inadequada** para receita ilimitada normalizada por limite errado (erro 41% lognormal, 58% Pareto) e quando atraso é tratado como 0 (erro 100%). Válida se esperar a janela fechar (decide W passos depois). Lib `confseq`: **não instala** em Py3.13 arm64 (só sdist; exige Boost) — registrado, não forçado.
FDR: BH controla 4,9% numa olhada; peeking infla para 9,2% (10 olhadas) e 13,8% (50); poder ~14% no cenário CVR 3%/+30%/5.000 cliques.

## Q7 — ASHA/SH supera random, equal e greedy?

**D em simulação: NÃO** (frente E, `results/swarm/SWARM-RESULTS.md`, critério pré-registrado em `PRE-REGISTRO.md`, intacto): nenhum candidato supera o melhor baseline em 12 cenários principais, 42 cenários de sensibilidade distintos e 28 variantes (0/360 pela regra pré-registrada; 0/440 pela regra exploratória com falsos vencedores relativos ao oráculo); o melhor baseline foi sempre `greedy_parcial`. Base D3 (regret R$, n=200): greedy 7.556 [6.887; 8.226] vs SH parcial 9.123, SH madura 10.213, ASHA parcial 10.164; SH aumenta drawdown (2.410 vs 1.760) e poda 3× mais top-k. Ganho só pareado e marginal no cenário ideal (estacionário, sem atraso, sem saturação). Atribuição (DiD pós-registro): saturação (+1.794 [1.620; 1.968]) e maturação heterogênea (+1.308) pioram SH frente ao greedy; interferência **favorece** SH/ASHA (−220 [−429; −10]); não estacionariedade n.s.; sem saturação o SH ganha no pareado (−227) mas não supera por nenhuma regra. Mapeamento ASHA **parcialmente válido**: avaliação intermediária não monotônica com atraso heterogêneo (correlação de rung 0,74 → 0,33) e sob saturação. A política ASHA simulada não tem referência externa (o 60/60 vs Optuna valida outra regra). Thompson top-n (extensão) teve o menor regret — **H** para estudo, sem log de propensão não há OPE.

## Q8 — Base identificável para surrogate?

**D:** `dados insuficientes` em campanha × dia; `não identificável` em sessão (`results/surrogate/SURROGATE-RESULTS.md`). Features GAM (impressões/cliques da mesma fonte da receita) são circulares e são removidas. Sintético: feature circular dá R² ≈ 0,95 (falso surrogate); vazamento temporal triplica a skill; critério calibrado contra sinal nulo (P(skill>1%) ≥ 0,8) só é atingido com ≥ **50 campanhas × 90 dias**, com ganho ~2% de MAE; em volumes como o real, sinal nulo e fraco são indistinguíveis; HistGradientBoosting perde do RidgeCV com sinal fraco. Zeros 0,00 da fonte com DEFAULT 0 saem do rótulo como ambíguos.

## Q9 — Bibliotecas e repositórios

**D/I** (`LIBRARY-DECISIONS.md`): nenhuma dependência nova nesta execução. Adotar no lab: numpy, scipy, statsmodels, scikit-learn; DuckDB/Polars provisórios. Referência: Optuna (oráculo; regra de rung conferida 60/60), ConfSeq, MABWiser, GAARF, Developer Assistant, Tightlock, ads-policy-monitor, ADSTA, IFTTA. Adiar: VW, LightGBM, CatBoost, PyMC Marketing, OR-Tools/CVXPY (scipy HiGHS resolve o LP de teste igual), Google Ads MCP, pgvector, redis, BigQuery, Riskfolio, sentence-transformers. Rejeitar: OBP como dependência, Meridian, Marketing Analytics Jumpstart, BERTopic, Feast, Prefect, Dagster, Airflow, Ray, ClickHouse, Bytewax, scikit-survival (GPL-3.0), Prophet. Achado: **Google Ads MCP 0.0.4 devolve 0 para métrica ausente** (viola `null≠0`), como o GAARF.

## Q10 — Menor próximo passo para shadow real

Ver `FINAL-REPORT.md` §Próximo passo.

## Resultados negativos preservados

Bootstrap só do fator; fator de maturação sob mudança de regime; "viés ≤ 1%" da maturação estável; leitura "proportional vence com quebra de regime" (artefato de 5 seeds); métrica pré-registrada de falsos vencedores; H3 do swarm como formulada; política trapaceira que reconstruía o oráculo pela linhagem (corrigido); Gamma-Poisson em dinheiro; normal-normal EB com cauda pesada; CS em receita ilimitada; Wald com peeking; BH com peeking; SH/ASHA vs greedy; ASHA com receita parcial e maturação heterogênea (pior que equal num degrau curto); HistGradientBoosting vs RidgeCV com sinal fraco; DuckDB/Polars no replay atual; `proportional` usa dado preliminar em 58/59 decisões com turnover ~20%/dia.
