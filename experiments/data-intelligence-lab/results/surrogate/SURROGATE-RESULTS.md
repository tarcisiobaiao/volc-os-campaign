# Surrogate index — viabilidade (Fase 6)

**Veredito:** `dados insuficientes` no grão campanha × dia; `não identificável` no grão sessão/clique.
Nenhum modelo foi promovido. Fonte numérica: `surrogate_results.json` (seed 20261015; o manifesto
traz fingerprint, `codigo_sha256` e `resultado_sha256`; runs repetidos produzem hashes idênticos).
Tempo: ~83 s, 2 threads. Revisado após a revisão adversarial F1 (ver `docs/data-intelligence/ADVERSARIAL-REVIEW.md`, F1-04/05/10/11/16/17).

## 1. Portão sobre os dados reais versionados (somente leitura, só contagens)

| Conjunto | Grão do rótulo | Linhas maduras | Unidades (com profundidade) | Features circulares | Veredito |
|---|---|---:|---|---|---|
| Senac shadow (`transformacao.csv`) | campanha × dia | 14 | 1 (0) | — | `dados_insuficientes` |
| Golden Meta×GAM (campanha/dia; conjunto/dia é rateio) | campanha × dia | 62 | 7 (0) | `gam_impressions`, `gam_clicks` | `dados_insuficientes` |
| Golden Meta×GAM, alvo `session` | campanha × dia | — | — | — | `não_identificavel` (não derivável por soma) |

- Senac: 2 dias com receita 0,00 "reconciliada" saem do rótulo como **ambíguos** — a fonte JoinAds legada tem `revenue DEFAULT 0` e o próprio `resultado.json` da fonte avisa que 0,00 pode ser default (F1-11). Por isso 14, não 16.
- Disponibilidade das features reais é **declarada** (relatório diário de mídia em D+1), não medida.
- Mínimos usados: 50 unidades com ≥ 63 períodos de treino e ≥ 27 de teste, ≥ 4.500 linhas maduras (calibrados na §3; parâmetros, não regra).

**Tentativa descritiva no golden Meta:** existe no JSON (`meta_descritivo_*`), mas tem **3 pontos de teste** — um bootstrap de n=3 tem só 10 reamostras distintas. Marcada `interpretavel=false`; **não sustenta nenhuma conclusão**, nem sobre inflação por circularidade (F1-10).

## 2. Contraprovas sintéticas (100 seeds, força de sinal 0,25)

| Caso | 7 × 17 skill [IC95] | 7 × 17 R² OOT | 50 × 90 skill [IC95] | 50 × 90 R² OOT |
|---|---|---|---|---|
| features válidas | 0,002 [−0,012; 0,017] | −0,04 | 0,021 [0,019; 0,022] | 0,18 |
| + feature circular (impressões da fonte da receita) | 0,796 [0,787; 0,805] | 0,94 | 0,816 [0,815; 0,818] | 0,96 |
| + vazamento (receita de t+1, choque AR(1) ρ=0,6) | 0,018 [−0,001; 0,038] | −0,04 | 0,061 [0,058; 0,064] | 0,23 |

Uma feature circular produz R² ≈ 0,95 — pareceria "surrogate excelente" e é a receita medida por outro nome. O portão a remove pela **regra única** do contrato (`origens_circulares`, vocabulário fechado de famílias de fonte; variantes como `JoinAds`, `joinads:v2`, `gam`, `adsense` caem na mesma família). Feature sem `disponivel_em` ou disponível depois do horizonte (D+1) sai como vazamento/não verificável.

## 3. Poder: quando RidgeCV supera a média por unidade fora do tempo (200 seeds)

Skill = 1 − MAE_modelo / MAE_média-por-unidade. Critério de relevância: **P(skill > 1%) ≥ 0,8** — "IC > 0" não serve, porque com sinal **nulo** e n grande a skill média é ~0,0005 com IC > 0 (F1-10).

| Unidades × períodos | P(skill>1%) sinal nulo | P(skill>1%) sinal fraco 0,25 | skill média fraco | P(skill>1%) moderado 0,5 | HGB skill (fraco) |
|---|---|---|---|---|---|
| 1 × 16 | 0,16 | 0,22 | −0,092 | 0,33 | — |
| 7 × 17 | 0,36 | 0,47 | 0,003 | 0,67 | — |
| 10 × 30 | 0,32 | 0,61 | 0,017 | 0,80 | — |
| 20 × 60 | 0,06 | 0,79 | 0,022 | 0,96 | −0,092 |
| 50 × 90 | 0,00 | 0,92 | 0,021 | 1,00 | −0,025 |
| 100 × 120 | 0,00 | 1,00 | 0,022 | 1,00 | −0,011 |

- Em volumes pequenos, sinal nulo e sinal fraco são indistinguíveis (0,36 vs 0,47 em 7 × 17): **não há como dizer, com o dado real atual, se micro-sinais têm valor**.
- Menor volume que atinge o critério com sinal fraco: **50 campanhas × 90 dias**; ganho então ~2% de MAE.
- HistGradientBoosting (50 seeds onde o treino ≥ 500 linhas) **perde** para RidgeCV com sinal fraco em todos os tamanhos; só ganha do ingênuo com sinal moderado e ≥ 50 × 90. Sofisticado que não supera o simples: rejeitado nesta fase.
- O intervalo de 80% por quantil de resíduo sub-cobre em amostra pequena (0,53 em 1 × 16; 0,73 em 7 × 17).

## 4. Demonstrado / inferido / não testado

- **Demonstrado (código + teste):** portão recusa grão não derivável (inclui `url_day`→`keyword_day`), grãos misturados, só-circular, origem fora do vocabulário, feature sem as-of, painel desbalanceado (1×1200 + 19×1) e volume pequeno; campo vazio do CSV real vira `None` (contagem igual à de células vazias); zero 0,00 da fonte com DEFAULT 0 não vira rótulo; feature circular infla R²; mundo sintético determinístico; sinal nulo quase nunca passa do efeito mínimo.
- **Inferido:** as features Meta são de fonte distinta da receita GAM, mas compartilham o clique — podem carregar viés de composição.
- **Não testado:** LightGBM/CatBoost (adiados); validação por grupo/funil/país (sem dado); calibração isotônica; dados reais fora do repositório.
