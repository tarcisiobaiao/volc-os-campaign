# Surrogate index — viabilidade (Fase 6)

**Veredito:** `dados insuficientes` no grão campanha × dia; `não identificável` no grão sessão/clique.
Nenhum modelo foi promovido. Fonte numérica: `surrogate_results.json` (seed 20261015,
fingerprint `5cecd6d3…62a2`, `resultado_sha256 8d30e324…`, `codigo_sha256 320985bb…`; dois runs
seguidos produziram hashes idênticos). Tempo: ~85 s, 2 threads.

## 1. Portão sobre os dados reais versionados (somente leitura, só contagens)

| Conjunto | Grão do rótulo | Linhas maduras | Unidades | Períodos treino/teste OOT | Features circulares | Veredito |
|---|---|---:|---:|---|---|---|
| Senac shadow (`transformacao.csv`) | campanha × dia | 16 | 1 | 11 / 5 | — | `dados_insuficientes` |
| Golden Meta×GAM (campanha/dia; conjunto/dia é rateio) | campanha × dia | 62 | 7 | 12 / 5 | `gam_impressions`, `gam_clicks` (mesma fonte da receita) | `dados_insuficientes` |
| Golden Meta×GAM com alvo `session` | campanha × dia | — | — | — | — | `não_identificavel` (exigiria ratear receita agregada) |

Mínimos usados (parâmetros, não regra): 20 unidades, 42 períodos de treino, 18 de teste, 1.200 linhas maduras — calibrados na §3.

**Tentativa descritiva no golden Meta (não é evidência):** RidgeCV com features Meta (gasto, impressões, cliques) vs média por campanha teve skill 0,68 com IC bootstrap [0,27; 0,85] — mas sobre **3 pontos de teste** (só 3 campanha-dias do último terço têm a mesma campanha no treino). O resultado é marcado `interpretavel=false`. Incluir as features GAM (circulares) sobe a skill para 0,88: o padrão de inflação por circularidade aparece até em n minúsculo.

## 2. Contraprovas sintéticas (100 seeds, força de sinal 0,25)

| Caso | 7 × 17 skill [IC95] | 7 × 17 R² OOT | 50 × 90 skill | 50 × 90 R² OOT |
|---|---|---|---|---|
| features válidas | 0,002 [−0,012; 0,017] | −0,04 | 0,021 [0,019; 0,022] | 0,18 |
| + feature circular (impressões da fonte da receita) | 0,796 | 0,94 | 0,816 | 0,96 |
| + vazamento (receita de t+1, choque AR(1) ρ=0,6) | 0,018 [−0,001; 0,038] | −0,04 | 0,061 [0,058; 0,064] | 0,23 |

Leitura: uma feature circular produz R² ≈ 0,95 — número que pareceria "surrogate excelente" e é apenas a receita medida por outro nome. O portão a remove pela origem (`verificar_nao_circular` no contrato e `features_circulares` no portão). O vazamento temporal triplica a skill em volume; só o `as_of` das features o impede.

## 3. Poder: quando RidgeCV supera a média por unidade fora do tempo (200 seeds)

Skill = 1 − MAE_modelo / MAE_média-por-unidade (positivo = melhor que o ingênuo).

| Unidades × períodos | Sinal nulo | Sinal fraco (0,25) | P(skill>0) fraco | Sinal moderado (0,5) | Cobertura do IC80 (fraco) |
|---|---|---|---|---|---|
| 1 × 16 | −0,088 | −0,092 | 0,50 | −0,063 | 0,53 |
| 7 × 17 | −0,012 | 0,003 [−0,008; 0,013] | 0,52 | 0,044 | 0,73 |
| 10 × 30 | −0,002 | 0,017 | 0,69 | 0,054 | 0,77 |
| 20 × 60 | −0,000 | 0,022 [0,020; 0,025] | 0,92 | 0,063 | 0,79 |
| 50 × 90 | 0,000 | 0,021 | 1,00 | 0,062 | 0,79 |
| 100 × 120 | 0,001 | 0,022 | 1,00 | 0,062 | 0,79 |

HistGradientBoosting (50 seeds onde o treino tem ≥ 500 linhas) **perde** para RidgeCV em todos os tamanhos com sinal fraco (skill −0,09 a −0,01) e só passa a ganhar do ingênuo com sinal moderado e ≥ 50 × 90. Sofisticado que não supera o simples: rejeitado nesta fase.

Conclusões:

1. Com o volume real de hoje (1–7 campanhas, ~17 dias), nem um sinal moderado é distinguível do ingênuo com segurança; o intervalo de 80% por quantil de resíduo sub-cobre (53–73%).
2. O menor volume que atinge o critério pré-definido (P(skill>0) ≥ 0,8 e IC inferior > 0, sinal fraco) é **20 campanhas × 60 dias (1.200 linhas maduras)** — e o ganho então é ~2% de MAE. Um surrogate só vale o custo se o sinal real for bem mais forte que isso; isso é uma hipótese a medir, não um fato.
3. O portão do laboratório foi ajustado a esses mínimos; eles são parâmetros dependentes do mundo sintético e devem ser recalibrados com dado real append-only.

## 4. Demonstrado / inferido / não testado

- **Demonstrado (código + teste):** portão recusa grão mais fino, grãos misturados, só-circular e volume pequeno; `null` no CSV real vira `None`; feature circular infla R² e é removida; mundo sintético determinístico; sinal nulo não bate o ingênuo.
- **Inferido:** as features Meta são não circulares em relação à receita GAM (fontes distintas), mas compartilham o mesmo clique — podem carregar viés de composição; não testado.
- **Não testado:** LightGBM/CatBoost (adiados por decisão de biblioteca); validação por grupo/funil/país (sem dado); calibração isotônica; dados reais fora do repositório.
