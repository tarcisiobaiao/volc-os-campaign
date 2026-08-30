# CL-08 · ORAKUL Predictive

**Horizonte**: B · **Resultado**: previsão com features as-of, baseline
honesto, intervalos calibrados e champion/challenger — persistida antes do
realizado, sem vazamento de futuro.

## Estado factual (F005, F010)

- `services/orakul_predictive/` (22 módulos: motor, features, drift,
  champion_challenger, walk-forward) + 15 arquivos de teste existem na
  autonomous-closure; entram na main com M-W1-03.
- O supervisor tentou reparo científico (attempt 2 rodando às 23:21Z de
  29/08) — colheita em M-W2-06.
- Ledger preditivo (P14-T06) não existe: zero tabelas de model version,
  prediction, evaluation, drift no oficial.
- Preditivo legado (Bola de Cristal) vetado: target leakage + validação
  in-sample; o órfão `b1fa53e` (paridade L2/L3) aguarda decisão (M-W1-08).

## Missões

| ID | O quê | Onda | Portão |
|---|---|---|---|
| M-W1-03 / M-W2-06 | (compartilhadas) integração + colheita | 1-2 | — |
| M-W4-07 | Ledger preditivo (migration escrita + provas; aplicar sob autorização) | 4 | banco |
| M-W4-08 | Baseline sem vazamento (features lagged, time split, amanhã=hoje lado a lado) | 4 | após W4-07 |
| M-W4-09 | Calibração de intervalos + champion/challenger + drift | 4 | após W4-08 |
| M-W4-10 | Simulador read-only de planned_spend no cockpit | 4 | após W4-09 |

## Regra dura

Previsão imutável antes do actual; challenger sempre shadow; drift suspende
influência e usa baseline/indisponível, nunca zero.
