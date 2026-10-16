# FINAL-REPORT — VOLC Data Intelligence Lab (execução 2026-10-15/16)

## Veredito

A bancada local reproduzível existe e responde às dez perguntas com código, testes e recibo — **em simulação e com n minúsculo real; nada aqui é validação real**. O resultado principal é negativo e útil: **nenhum método sofisticado testado superou o baseline simples nas condições do VOLC**, e o gargalo para avançar não é algoritmo, é dado: a base oficial não tem as-of real (custo e receita são latest-wins/upsert) e só existe rótulo econômico em campanha × dia, em volume ~100× abaixo do necessário para um surrogate.

**Pode avançar para shadow real:** o contrato de dado econômico + snapshot `as_of` e o replay v0 com baselines simples, assim que existir uma fonte append-only. **Fica em hold:** SH/ASHA, surrogate, confidence sequences sobre receita, DuckDB/Polars no kernel, bandits. **Descartado nesta fase:** tudo listado em "Rejeitado".

## As dez perguntas

| # | Pergunta | Resposta | Evidência |
|---|---|---|---|
| 1 | Contrato mínimo de dado econômico confiável | Observação tipada com identidade estrita, micros+moeda, `null≠0` com estado e motivo, três relógios (janela/observado/disponível), linhagem, cobertura, maturidade, método, `value_kind` (5 classes) + snapshot `as_of` versionado com fingerprint | `CONTRATO-DADO-ECONOMICO.md`, `test_contracts.py` |
| 2 | O que existe, falta e em que grão relaciona | Relacionável sem inventar: **campanha × dia** (UTM = campaign.id). Sessão/clique: não. Núcleo econômico, ledger v21 e JoinAds v2 só em `wip/*`; JoinAds legado com `DEFAULT 0` e gatilho que sobrescreve receita | `DATA-CAPABILITY-MATRIX.md`, `CATALOG-CLASSIFICATION.md` |
| 3 | DuckDB + Polars melhoram o replay atual? | **Não** o replay atual (2,7–3,6 ms; import das engines custa 15–45×). Em volume, Polars 5,1× e DuckDB 4,2× em 1e6; com dados em tuplas o corte é 1e4–1e5 obs/corte — acima do replay v0 (≤ ~13 mil). Gargalo real: `Snapshot.construir` | `results/bench/BENCH-RESULTS.md` |
| 4 | Replay `as_of` sem futuro, null, moeda, frescor, linhagem | **Sim, em sintético**: política só vê o snapshot (`falhar` contra futuro), contraprovas de futuro, null→0, moeda, identidade, restatement, linhagem opaca, piso, uso de preliminar medido pelo efeito | `results/replay/REPLAY-RESULTS.md`, 23 testes |
| 5 | Baselines estatísticos simples | Chain-ladder com guarda `insuficiente` funciona em regime estável e **degrada sem avisar** sob mudança de regime; EB Beta-Binomial reduz MSE e vencedores por sorte; hurdle para dinheiro; Gamma-Poisson em dinheiro inadequado | `results/statlab/STATLAB-RESULTS.md` |
| 6 | Confidence sequences mantêm cobertura? | **Sim para outcome limitado em [0,1]** (erro uniforme 0,8–1,9% vs 59–79% do Wald com peeking), ao custo de decidir menos (53% vs 99%). **Inadequadas** para receita ilimitada e quando atraso vira 0. `confseq` não instala | idem |
| 7 | ASHA/SH superam random, equal, greedy? | **Não** (pré-registrado: 0/360; exploratório: 0/440). Saturação e maturação heterogênea explicam; interferência favorece SH/ASHA; sem saturação o SH só ganha no pareado | `results/swarm/SWARM-RESULTS.md`, `PRE-REGISTRO.md` |
| 8 | Base identificável para surrogate? | **Dados insuficientes** (campanha × dia: 14 e 62 linhas maduras vs ≥ 4.500 em 50 × 90) e **não identificável** em sessão. Features GAM circulares | `results/surrogate/SURROGATE-RESULTS.md` |
| 9 | Bibliotecas e repositórios | Nenhuma dependência nova. Adotar: numpy/scipy/statsmodels/sklearn; DuckDB/Polars provisórios no lab. Referência: Optuna, ConfSeq, MABWiser, GAARF… Rejeitar: OBP como dep., Meridian, Feast, orquestradores, Ray, ClickHouse, scikit-survival (GPL) … Google Ads MCP devolve 0 para métrica ausente | `LIBRARY-DECISIONS.md` |
| 10 | Menor próximo passo para shadow real | Ver abaixo | — |

## Demonstrado (código + teste ou execução reproduzível)

- Contrato e snapshot `as_of` com invariantes testados e endurecidos pela revisão adversarial.
- Replay econômico v0 determinístico com quatro baselines e anti-baseline null→0 detectada.
- Equivalência byte a byte do resultado entre contrato, Python, DuckDB e Polars, inclusive fora do caminho feliz.
- Validade uniforme da CS PrPl-EB para [0,1]; controle de FDR do BH numa olhada e sua inflação com peeking.
- Resultado negativo do swarm sob critério pré-registrado, com atribuição por DiD.
- Portão de viabilidade do surrogate (grão derivável, circularidade, as-of das features, profundidade) e veredito sobre os dados reais versionados.

## Rejeitado (resultado negativo preservado)

SH/ASHA como ganho sobre o greedy; ASHA com receita parcial e maturação heterogênea; HistGradientBoosting vs RidgeCV com sinal fraco; surrogate com volume atual; CS sobre receita ilimitada; Wald e BH com peeking; bootstrap só do fator de maturação; Gamma-Poisson e normal-normal EB para dinheiro com cauda; DuckDB/Polars no replay atual; `proportional` como política (significativamente pior que `equal` em 2 de 4 cenários, nunca significativamente melhor); "receita exata" de sinal Prebid (contrato recusa); circularidade por fonte de receita (portão recusa).

## Não testado

Dado real append-only (não existe na base); polars 2.0 do Freedom Lab; pandas; câmbio; preliminar enviesado correlacionado à eficiência; Bornhuetter-Ferguson e detecção de regime; Hyperband como política; Thompson/LinTS calibrado (hipótese: menor regret em todos os cenários, sem log de propensão não há OPE); LightGBM/CatBoost; determinismo entre plataformas.

## Arquivos e commits

16 commits pequenos em `lab/data-intelligence-overnight-20261015` (lista em `PROOF-RECEIPT.json`), todos dentro de `experiments/data-intelligence-lab/`, `docs/data-intelligence/`, `tests/data-intelligence/`, `research/data-intelligence/`. Entregáveis: `RUN-MANIFESTO.md`, `WORKBOARD.md`, `DATA-CAPABILITY-MATRIX.md`, `CATALOG-CLASSIFICATION.md`, `CONTRATO-DADO-ECONOMICO.md`, `LIBRARY-DECISIONS.md`, `EXPERIMENT-RESULTS.md`, `ADVERSARIAL-REVIEW.md`, `FINAL-REPORT.md`, `CURATION-HANDOFF.json`, `PROOF-RECEIPT.json`, `handoffs/HANDOFF-NUCLEO-ECONOMICO-VALUE-KIND.md`; `experiments/data-intelligence-lab/{pyproject.toml,uv.lock,README.md}`; 172 testes em `tests/data-intelligence/`.

## Provas

172 testes verdes (~14 s); mutantes mortos (Stat Lab 19/19, swarm 11/11, guardas do contrato cobertas); `git diff --check` limpo; nenhum arquivo fora do namespace; secret scan sem ocorrências; nenhum import de rede/produção no código do lab; produção, Supabase, APIs autenticadas, migrations, n8n/cron/GTM/WordPress, Google Ads, Roadmap/curadoria/grafo: **não tocados** (`PROOF-RECEIPT.json`).

## Limitações

Todas as conclusões quantitativas vêm de mundos sintéticos cujos parâmetros nós escolhemos (a forma veio do dado real, os números não). O isolamento política×simulador do replay é por regra de código. O pré-registro do swarm tem precedência só por mtime. O grafo ficou `current: false` porque os arquivos do lab entraram nos insumos; o rebuild é do integrador após merge.

## Menor próximo passo para shadow real (sem autonomia financeira)

1. **Integrar uma fonte append-only de uma campanha** (JoinAds v2 da wip, com o valor lido a cada coleta e sem `DEFAULT 0`) e o ledger de custo v21 renumerado — decisão do integrador, fora desta frente.
2. **Escrever o adaptador read-only** que converte essas linhas em `Observacao` do contrato (com `disponivel_em` = instante da coleta) e rodar o **replay v0 em shadow diário** com `equal` e `greedy_conservador`, gravando só a decisão simulada e o resultado maduro D+3, nunca propondo mutação.
3. Depois de ~8 semanas, medir as curvas reais de maturação de custo e receita (Stat Lab) e reabrir o portão do surrogate. SH/ASHA e bandits só voltam com log de propensão e experimento aprovado.

O handoff de curadoria (`CURATION-HANDOFF.json`) propõe estados para P14-T02, P09-T09, P09-T10, P09-T11, P06-T03, P06-T08, P06-T09, P14-T10, P05-T09 e seis nós do grafo, sem aplicar nada.
