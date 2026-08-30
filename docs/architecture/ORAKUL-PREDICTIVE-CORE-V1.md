# ORAKUL Predictive Core V1

Status desta entrega isolada: **partial / offline**. O núcleo Python é
testável, reproduzível e não muta campanha. Não há migration, frontend,
Supabase oficial, shadow real nem autonomia. Métricas desta branch são
**sintéticas e inelegíveis para afirmação de qualidade preditiva real**.

Autoridade de estado: curadoria + Roadmap Vivo (somente leitura nesta branch),
tarefa `P14-T10`. A CLI, `graphify-out/graph.json` e
`graphify-out/UPDATE_STATUS.json` não existem nesta worktree; foi consultado o
fallback gerado `docs/volc-os-graph/volc-os-graph.json`. Portanto esta entrega
não afirma frescor do grafo híbrido e deixa rebuild/curadoria ao integrador.

## 1. O que o legado realmente tentava prever

Não é um oráculo genérico. Os dois workflows (`bola-de-cristal-preditivo` /
`Python predict flow final`, id `i21UFesZCR3nkMfN`; `orakul-predictive-integrado-v1`,
id `pLVASdJ8TaUSNFp0`) tentam, no grão campanha-dia e horizonte D+1:

1. **spend** de amanhã;
2. **receita** (`revenue_converted_revshare`) de amanhã, condicional ao spend
   estimado ou a um `planned_spend` nunca chamado;
3. **ROAS derivado** (receita/spend), usado no integrado para *veto* de lance
   se ROAS previsto &lt; 1,30.

A tese de produto é antecipar o lado direito de `SPREAD = RPC − CPC`. A
implementação n8n não é utilizável: leakage de alvo, validação no dia errado,
intervalo in-sample, boost_factor invertido, zero persistência, campanha e
Supabase hospedado hardcoded. Extração literal e tabela fato/hipótese/regra/
risco/destino: `services/orakul_predictive/legado_forense.py`.

Joias preservadas: dois estágios (spend = decisão/cenário, receita = resposta);
gancho `planned_spend`; intervalo que deveria crescer com residual e
discordância (recalibrar fora da amostra); vocabulário `prediction_available` +
data-alvo.

Dívida descartada: 12 features contemporâneas de spend; `boost_factor`; XGBoost
em dezenas de linhas; `is_payday` como lei; teto `min(..., budget_amount)`;
três rotas duplicadas; `fillna(0)`.

## 2. Arquitetura implementada

Território isolado: `services/orakul_predictive/**` +
`backend/tests/orakul_predictive/**`. Sem `src/`, routers, criativo, campanha,
migrations, n8n, Roadmap, curadoria, graphify, `.env`, QG/Tráfego/Redator.

```text
ObservacaoDiaria (BRL micros, America/Sao_Paulo)
  -> última revisão com civil_date <= origin E lido_em <= cutoff UTC
  -> FeatureSnapshot + SourceReceipt + estados + hash_inputs completo
  -> naive_persistence | naive_weekday | lagged_linear_ridge (stdlib)
  -> Prediction D+1 (pair_id, alvo/artefato, cenário, ponto/bruto, intervalo OOF)
  -> PredictionLedger append-only; repetição igual é idempotente, payload divergente conflita
  -> ObservedOutcome D+1 fechado, no mesmo pair_id
  -> walk_forward temporal e população pareada (nunca aleatório)
  -> BacktestResult (candidato × naive nos mesmos pair_ids; sintético)
  -> DriftSignal (amostra pequena = insuficiente, não vitória)
  -> ChampionChallengerDecision (proposta ou preservar; rollback proposto)
```

Nenhum LLM no cálculo. Nenhuma dependência ML nova: Ridge via álgebra stdlib.
XGBoost do legado não foi portado.

### Contratos (todo registro)

Identidade interna inclui conta + campanha + data de origem + target D+1 + alvo
+ cenário + versão. `pair_id` exclui deliberadamente o modelo para reconciliar
champion, challenger e actual sobre a mesma unidade. Todo registro carrega cutoff
`observado_em`, janela, versão, hash dos inputs, procedência (`SourceReceipt`),
estado semântico e chave de idempotência. `mutacao_campanha` é sempre `false`.

IDs e chaves não concatenam campos ambíguos. Conta e cenário participam da
identidade. O payload participa do hash integral, mas não da chave lógica: se a
mesma chave reaparecer com payload diferente, o adapter levanta
`ConflitoDeIdempotencia` em vez de devolver o primeiro valor.

Estados semânticos distintos: `ausente`, `zero_medido`, `medido`, `falha`,
`nao_aplicavel`, `antigo` e `hipotese`. Ausência nunca vira 0. Contradições são
erro de contrato: `ZERO_MEDIDO` exige exatamente 0; `MEDIDO` observado não
aceita `None` ou zero; `fonte_falhou=true` exige `FALHA` sem valor. Frescor
maior que 36 h vira `ANTIGO`; FALHA/ANTIGO chegam à Prediction, não são
reclassificados como AUSENTE.

Unidade canônica: `BRL` + `micros` + fuso `America/Sao_Paulo`. ROAS derivado
usa `fracao_x_1e6`, não mistura moeda.

### Features honestas (`orakul-features-asof-lagged/v1`)

`spend_lag0/lag6`, `revenue_lag0/lag6`, MA7 apenas com revisões conhecidas no
cutoff (mín. 3 valores medidos), dummies do weekday **calendário** do D+1,
`campaign_age_days`, `planned_spend_scenario` opcional e marcado `hipotese`.
Cada feature guarda o instante `feature_as_of` e a data civil de origem.
Nomes contemporâneos do legado
(`budget_utilization`, zscore, ewma inclusivos do alvo) levantam
`VazamentoDeFuturo`.

`spend_lag0` é persistência honesta (gasto já observado no origin), não o
defeito n8n de treinar `y=spend_t` com `spend_t` no X.

`planned_spend_scenario` não entra nas features do Ridge de receita e nunca é
substituído silenciosamente por `spend_lag0`. No cenário planejado, o spend é
emitido como hipótese explícita; receita e ROAS ficam `nao_aplicavel` com motivo
`efeito_causal_de_planned_spend_nao_identificado`. O Core não possui desenho
causal que autorize uma curva spend→receita.

### Replay

Walk-forward: treina só em pares cujo `target_date ≤ origin` atual. Uma lacuna
civil não pode transformar D+2 em D+1. Split aleatório é recusado.
`VazamentoDeFuturo` aborta o backtest (fail-closed); outras exceções viram
`falhas_parciais`. Um `BacktestResult` completo implica
`leakage_detectado=False` — leakage não devolve resultado.

Candidato e baseline são avaliados somente na interseção dos mesmos `pair_id`
por alvo. O resultado conserva `pair_ids_por_alvo` e `population_hash`.
`n_total` é o menor tamanho de população avaliável por alvo, nunca a soma de
spend + revenue. Champion/challenger exige igualdade exata de conta, campanha,
janela, horizonte, cenário, natureza do dataset, `population_hash` e pair_ids;
divergência levanta `PopulacaoIncompativel` antes de olhar qualquer métrica.

Métricas do alvo observado (dinheiro), não R²: MAE, WAPE, RMSE, bias
(`yhat − y`), cobertura, largura e Winkler. `n_intervalos` explicita o
denominador das métricas intervalares. Dataset sintético força
`entra_em_contagens_reais=False`; a própria `ObservacaoDiaria` carrega
`dataset_kind`, então trocar apenas o recibo para “real” é recusado.

### Ridge, artefato e intervalo

O Ridge padroniza com estatísticas do treino e não penaliza o intercepto. Prova
exata: para `X=[[1],[1],[1]]`, `y=[2,4,6]` e `alpha=1e9`, o coeficiente continua
`4`, a média — não é puxado para zero.

O `artifact_hash` cobre coeficientes, nomes, médias, desvios, alpha, resíduos,
n de treino, feature set, code hash, training hash, definição do alvo, política
do intercepto e cenários suportados. O motor recusa artefato de revenue usado
como spend, versão/código divergente e artefato ausente; não cai silenciosamente
no naive. Cada Prediction inclui o hash do artefato e o hash combinado de
request + snapshot + artefato.

Intervalos só existem com resíduos fora da amostra. O quantil split-conformal
usa rank finito `ceil((n+1)×nominal)`, método `higher`: com resíduos absolutos
`1..10` e nominal 90%, a margem é `10`; com `1..20`, é `19`. Menos de sete
resíduos não produz intervalo. Intervalo in-sample não recebe rótulo de 90%.

Exemplo métrico exato, em BRL: `y=[10,20,30]`, `yhat=[12,18,33]`, intervalos
`[11,13]`, `[17,19]`, `[30,36]`. Resultado: `n=3`, MAE `7/3`, RMSE
`sqrt(17/3)`, bias `1`, WAPE `7/60`, cobertura `1/3`, largura média `10/3` e
Winkler 90% `50/3`.

### Champion/challenger (`orakul-cc-policy/v1`)

Challenger nunca se promove sozinho. Exige população idêntica, n≥21, janela completa, WAPE de
receita **e** MAE de spend. Regressão crítica de MAE spend &gt;10% veta.
Melhoria mínima de WAPE 5%. Empate ou evidência insuficiente preserva o
champion. Promoção é `proposta`. Rollback é `rollback_proposto` e só altera
papel no registry in-memory se `humano_confirmou=True`.

### Portas (sem produção)

`FeatureRepository`, `PredictionLedger`, `OutcomeRepository`, `ModelRegistry`,
`EvaluationRepository`. Adapters: `InMemory*`. Contrato de uma migration única
futura (não aplicada): `schema_migracao.py` — tabelas `forecast_*` distintas de
`trafego_previsao` (SPEC §5, amarrada a proposta).

## 3. Como provar

O conftest pai de `backend/tests/` importa FastAPI. Nesta worktree não existe
`backend/.venv/bin/python`; o interpreter local que possui pytest é
`/usr/local/bin/python3`. Gate hermético executado:

```bash
PYTHONPATH=. \
  /usr/local/bin/python3 -m pytest \
  backend/tests/orakul_predictive -q -p no:randomly \
  --confcutdir=backend/tests/orakul_predictive
```

Gates cobertos: contratos; colisão idempotente; ausência≠zero; FALHA/ANTIGO;
cutoff intraday com revisão futura; leakage deliberado; D+1/pair_id; população
pareada; n_total; walk-forward; dataset insuficiente; drift;
champion/challenger; rollback; byte-idêntico; Ridge/intercepto; hash integral do
artefato; quantil/intervalo/métricas exatas; isolamento AST (sem
httpx/requests/socket/supabase/dotenv); mutantes de fuso, moeda, alvo, artefato,
payload, cenário e fixture sintética como real.

## 4. Real versus sintético

| Artefato | Natureza |
|---|---|
| Algoritmo n8n, URLs, campanhas hardcoded, fórmulas | Fato extraído do inventário gitignored (não copiado para a branch) |
| Medições de R², cobertura 60–64%, MAE vs baseline no 05-PREDITIVO | Evidência histórica do inventário; **não reexecutada** aqui |
| Série `camp-sintetica-a` / `camp-sintetica-curta` | Fixture `SYNTHETIC_FIXTURE`; observações e recibo dizem `dataset_kind=sintetico` |
| MAE/WAPE/cobertura desta suíte | **Provas aritméticas, não performance real** |
| Google Ads / Supabase oficial | Não consultados |
| `txvvzpstquqmbhljudfn.supabase.co` | Legado; fora de autoridade |

## 5. Lacunas para Supabase e front

- Nenhuma tabela `forecast_*` no banco oficial (P14-T06).
- Sem writer, RLS, service_role, watermark, heartbeat.
- Sem tela de previsão/baseline/intervalo (P14-T09 depende disto).
- Sem `GoogleAdsRow` real atravessando a fronteira (P14-T02 continua partial).
- Sem ligar previsão a `trafego_proposta` — e não deve, até haver governança.
- `planned_spend` no Core é cenário tipado; não é simulador de cockpit.

## 6. Handoff de curadoria (NÃO APLICAR NESTA BRANCH)

Não editar `ROADMAP-VIVO.json`, `curadoria-operacional.json` ou saídas geradas
nesta branch. Proposta para o curador único, depois da integração:

- tarefa: `P14-T10`;
- nós: `cap_forecast`, `concept:forecast_lifecycle`;
- estado proposto: **partial** (não `done`);
- prova: suíte offline com contraprovas de cutoff intraday, semântica, D+1,
  pair_id, população, idempotência, artefato, Ridge e aritmética exata;
- lacunas: zero dado real, zero ledger persistente/migration, zero previsão shadow
  persistida, zero calibração real, zero aprovação/promoção e grafo sem status de
  frescor nesta worktree.

## 7. Riscos e próxima fatia mínima

Riscos remanescentes: registry/ledger são somente in-memory; o caller ainda é a
fonte do `planned_spend` hipotético; o conjunto sintético é pequeno; cobertura
OOF real não foi medida; clip de ponto negativo preserva o bruto mas ainda exige
monitoramento futuro. Nenhum desses riscos é reclassificado como qualidade.

Próxima fatia mínima (não esta branch): somente após autorização própria, uma
persistência append-only no oficial e um job as-of que grave previsão D+1 **sem
executor**, seguido de actual fechado e shadow naive × lagged_linear na mesma
população real. Zero autonomia. Zero UI até o ledger existir.
