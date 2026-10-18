# VOLC Viability & Marginal Economics Kernel v1 — registro de decisão (17/10/2026)

Branch `lab/fable-viability-kernel-20261017`, base `8838f4a9c50d1ffd5ce8a792c4026e76a7599d7a` (lab/data-foundation-20261016, congelado às 22:28:47Z; a branch de origem continuou andando e **não foi acompanhada**).
Código: `experiments/data-intelligence-lab/src/volc_dil/viability/`. Testes: `tests/data-intelligence/viability/`. CLI: `experiments/data-intelligence-lab/scripts/viability_cli.py`. Fixtures: `experiments/data-intelligence-lab/fixtures/viability/`. Replay: `experiments/data-intelligence-lab/results/viability/`.

Estado: **offline/shadow**. Nenhuma integração externa, UI, migration, chamada de rede, LLM ou ação sobre Google Ads, GTM, WordPress, n8n ou Supabase. O kernel não tem autoridade para gastar.

## 1. Pre-flight: o que existia e a decisão de não duplicar

| Existente (SHA-base) | Uso aqui | Decisão |
|---|---|---|
| `volc_dil.contracts.money.Dinheiro` (micros inteiros, sem float, sem câmbio implícito) | toda quantia do kernel | **reusado** sem alteração |
| `volc_dil.contracts.vocab` (`ValueKind`, `EstadoMedida`, `Maturidade`) e `fundacao.observacao.vocab.StatusObservacao` | vocabulário de referência; adapters mapeiam `StatusObservacao` → `Evidencia` | **reusado por mapeamento**; o kernel precisa de 9 estados (inclui `attested`, `projected`, `immature`) que o contrato de observação não distingue, por isso há um enum próprio e um mapa explícito |
| `fundacao.shadow.politicas` (`RegraMargem`, `Guardiao72h`, anti-baseline null→0) | referência de regras de decisão por campanha×dia | **não duplicado**: o shadow decide "manter/pausar" sobre fatos; o kernel responde "existe fronteira econômica e qual é o teto" antes de gastar. São perguntas diferentes; o kernel pode alimentar uma política futura |
| `backend/app/trafego/recomendacao_shadow.py` (main) | só lê um experimento gravado; não calcula | nada a reusar |
| `backend/app/motor_pautas/espaco.py` (main) | score de temas por priores; não calcula viabilidade econômica | nada a reusar; o kernel é o complemento econômico do espaço |
| `volc_ads/inteligencia_google/coletor.py` (main) | coleta `campaign_simulation` (GAQL); não interpreta | o adapter `de_campaign_simulation_gaql` mapeia a linha; o kernel interpreta |
| `statlab.maturacao` (chain-ladder/nowcast) | maturação como estimativa | **não usado**: o kernel trata maturidade como propriedade declarada da entrada (`immature`), não a estima; MAT-01 pode alimentar `Evidencia.ESTIMATED` no futuro |
| `tools/freedom-lab/experimentos/senac-shadow-20261015/resultado.json` | fonte da fixture "Senac sanitizada" (agregados da janela madura; id pseudonimizado) | **reusado** como snapshot sanitizado |

Conclusão: não havia implementação equivalente. O kernel estende o contrato de dinheiro e o vocabulário do laboratório; não cria outro store nem outra política de shadow.

## 2. Algoritmos implementados

- **Economia observada** (`economia.calcular_economia`): CPC = custo/cliques; RPC = receita líquida comparável/visitas elegíveis; contribuição = receita líquida − custo; break-even CPC = RPC. Receita comparável aplica câmbio, revshare e imposto **somente quando informados**, cada um com proveniência; desconhecido não vira 1 nem 0, vira limitação declarada.
- **Envelope de incerteza** (`envelope_conservador`): fatores declarados em `PREMISSAS` (−10% receita realizada; −15% moeda atestada; −15% câmbio estimado; −30% imatura e não realizada; −50% projetada e não realizada; +5% custo; +20% otimista). Produz intervalo, nunca ponto.
- **Fronteira** (`fronteira`): RPC necessário, multiplicador, queda de CPC necessária, folga, distância econômica, pares (CPC, RPC) de contribuição zero.
- **Estresse** (`estresse`): cenários separados para receita ×2, câmbio ×1,5 (só se converte), revshare 0,7, maturação ×1,3 e combinado favorável.
- **Teto** (`teto.calcular_teto`): só com `perda_maxima` do owner. `click_cap = perda / (cpc_cons − rpc_cons)`; spend, day cap, maturação, condições de parada/continuidade/inconclusão tipadas. Sem economia observada usa CPC de pesquisa (limite superior) e RPC desconhecido = perda total.
- **Custo marginal** (`simulacao.analisar_simulacao`): valida tipo (CPC_BID/BUDGET), unidade, duplicados, campos ausentes, monotonicidade; Δcusto/Δcliques entre pontos adjacentes; contribuição marginal sob RPC conservador; último ponto sustentável, primeiro destrutivo; sem extrapolação; normalização só explícita e com recibo.
- **Gate** (`gate.avaliar`): combina tudo em veredito (5), classe de confiança (4), recomendação (7), razões tipadas, evidência faltante/inválida, premissas, próximas leituras, proibições, trace e hashes. Ordem de decisão: imaturo → inviável sob estresse (só com receita realizada e volume mínimo) → stop-loss → lucrativa com evidência forte → favorável com evidência fraca → perto do equilíbrio.
- **Invariantes em runtime** (`invariantes.verificar_invariantes`): rede contra mutantes; exit 4 na CLI.
- **Adapters** (`adaptadores`): ledger campanha×dia, `campaign_simulation` GAQL, Keyword Planner/DataForSEO, JoinAds, card do Pautador, pedido da Bia (qualquer campo financeiro é recusado).

## 3. Algoritmos rejeitados e por quê

- **Modelos (LightGBM, bandits, MMM, ORAKUL)**: fora do escopo por instrução e porque o Model Lab já mostrou que perdem para a baseline sem dado real.
- **Probabilidade de break-even**: não emitida. Com n=1 campanha e premissas declaradas, só um intervalo por premissa é defensável (`break_even_interval`), rotulado como "não é probabilidade".
- **Interpolação (PCHIP) entre pontos de simulação**: rejeitada nesta versão; o kernel só avalia segmentos adjacentes observados. Interpolar inventa pontos.
- **Receita por sessão / viewability como receita**: proibidas pelo contrato (grão campanha×dia; receita só reconciliada/observada).
- **Derivar tolerância do owner** (ex.: "10% do custo"): proibido; sem valor não há teto.
- **Float em decisão**: nenhum; `Fraction` e `Decimal`/micros.

## 4. Testes e invariantes

106 testes em `tests/data-intelligence/viability/` (contrato, economia, teto, simulação, gate, invariantes+mutantes, adapters, CLI+replay). As 15 invariantes obrigatórias estão em `test_invariantes.py` (inv1..inv15) e no verificador em runtime. Mutantes detectados: ausente→zero, CPC médio no lugar do marginal, projected→realizado, remoção do `as_of`, hash adulterado. Suíte completa do laboratório: 1049 passed, 3 skipped (109 s) no SHA final.

## 5. Replay (fixtures sintéticas + snapshot sanitizado)

`results/viability/replay.{json,md}` — 18 casos, `replay_hash` reproduzível, invariantes ok em todos. Pontos relevantes:

- **Senac sanitizada** (derivada do experimento shadow de 15/10, id pseudonimizado): `unviable_under_declared_scenarios` (V2; V1 dizia `structurally_unviable`), confiança `medium` (moeda atestada + câmbio literal), multiplicador de RPC ≈ 18× sob premissas conservadoras; nenhum cenário de estresse chega a zero. Coincide com a direção "pausar" do experimento original por um caminho independente.
- **ROAS médio bom, marginal destrói**: veredito `already_profitable` (a campanha como está paga), mas `kernel_marginal = expandir_ate_100000` enquanto a baseline `cpc_medio` diz `expandir`. É exatamente o exemplo do ADR do ciclo econômico §2.
- **Evidência insuficiente** (receita ausente, câmbio ausente, moeda desconhecida, custo ausente, imaturo, sem limite financeiro): o kernel recusa decidir e diz o que falta.
- **Baselines**: registradas no mesmo vocabulário; nenhuma é avaliada por acerto porque não há resultado maduro. **Nenhuma superioridade é declarada.**

## 6. Limitações honestas

- Os fatores de `PREMISSAS` são declarações, não calibrações. Mudá-los muda vereditos nas margens; a fixture `proximo_do_equilibrio` é sensível a eles.
- `MIN_CLIQUES_MADUROS=200`, `MIN_DIAS_MADUROS=3`, `MATURITY_WAIT_DIAS=7` são limiares de laboratório, não política do owner.
- O kernel não estima maturação; depende de a entrada rotular `immature`. Integração com MAT-01 fica para depois.
- Só um candidato por avaliação; alocação entre candidatos (portfólio) não está implementada.
- Simulação: só CPC_BID e BUDGET; TARGET_ROAS/TARGET_CPA devolvem `tipo_nao_suportado`.
- O replay usou um único snapshot real sanitizado (agregados da Senac). Nenhum replay contra o export v21/JoinAds v2 (o export fica fora do repositório por decisão da DIL).
- Confiança `high` nunca é "estatística"; é uma classe por força de evidência e volume.

## 7. Conflito esperado com a Data Intelligence

- Nenhum arquivo existente da DIL foi modificado. Só arquivos novos sob `volc_dil/viability/`, `tests/data-intelligence/viability/`, `fixtures/viability/`, `results/viability/`, dois scripts e este doc.
- Risco de conflito: baixo (adições). Se a DIL criar um módulo com o mesmo nome ou mudar `contracts.money`/`contracts.vocab`, o kernel precisa de reconciliação.
- A branch de origem andou depois do SHA-base (item 5 em andamento). O merge deve ser feito sobre o HEAD atual da DIL, reexecutando a suíte.

## 8. Plano mínimo de integração (não executado)

1. Revisão read-only do SHA final por outra sessão; nenhum merge sem recibo.
2. Reaplicar sobre o HEAD da DIL; rodar `tests/data-intelligence` inteiro.
3. Consumidores futuros, nesta ordem e sempre read-only: Pautador (card → `de_pautador_card` → `avaliar`), Decision Lab (fixtures → replay), Hub de Tráfego (ledger campanha×dia → `de_ledger_campanha_dia`), Bia (`requisicao_bia` → `avaliar`; nunca define financeiro, nunca executa).
4. Tolerância do owner, revshare, imposto e câmbio entram por configuração versionada do lado VOLC, nunca pelo pedido.
5. Só depois de 8 semanas de shadow com resultado maduro faz sentido revisar `PREMISSAS` e limiares.

## 9. Como rodar

```bash
cd experiments/data-intelligence-lab
.venv/bin/python -I scripts/viability_gerar_fixtures.py
.venv/bin/python -I scripts/viability_cli.py evaluate fixtures/viability/senac_sanitizada.json --saida /tmp/vk
.venv/bin/python -I scripts/viability_cli.py replay fixtures/viability --saida results/viability
.venv/bin/python -I scripts/viability_cli.py verify /tmp/vk/recibo.json
cd ../.. && experiments/data-intelligence-lab/.venv/bin/python -m pytest tests/data-intelligence/viability -q
```


---

## 10. V2 (17/10, 23:00–23:40Z) — candidata após revisão adversarial

Branch `lab/fable-viability-kernel-v2-20261017` a partir de 2e982a82 (V1 preservada). Três subagentes em worktrees próprias com ownership disjunta (A: economia/teto/simulacao/gate; B: contrato/adaptadores/CLI/fixtures; C: suíte RED, sem tocar código), integrados por um único integrador que só reconciliou `_entradas.py`, `invariantes.py`, o alias do veredito, a cobertura das fixtures sintéticas, a regra de `issuer` e os testes de A sob o contrato V2.

Correções (todas com teste RED antes): grão por clique (RPC por visita só reportado; visitas=0 válido); stop-loss por perda líquida realizada vs max_loss (perda conservadora vira aviso), com `max_loss`, `spend_cap` e contribuição separados; moedas incompatíveis recusadas em teto e simulação (conversão só explícita e registrada); custo/receita/cliques brutos ≥ 0 no contrato e no kernel; `micros_de_fracao` inteiro half-even; veredito `unviable_under_declared_scenarios`; `viable_candidate` alcançável; governança de evidência (custo/cliques/receita projetados, stale por SLA, flags `invalid*`, cobertura de receita, moeda do custo) bloqueia vereditos positivos e confiança `high`; adapter soma todo custo maduro e mede cobertura própria da receita, recusa moedas heterogêneas, deduplica datas com flag, preserva a evidência mais fraca por linha; parâmetros versionados (effective_at/disponivel_em/versao/hash) com `disponivel_em <= as_of`; `PerdaMaxima` só com `Autorizacao` (id, versão, hash, issuer com identidade, vigência); Bia/Pautador recebem referência de autorização e não podem passar nenhum campo financeiro; recibo com commit, ambiente (uv.lock), hashes de entrada/resultado/relatório, `external_actions` e `replay_hash`, e `verify` falha em artefato ausente ou campo adulterado.

Contagens na candidata após a segunda rodada adversarial: suíte RED 104/104 (58 da V2 original + 46 para R4/R5/R7/R8), kernel 332/332 e replay reproduzível em duas execuções. A contagem da Data Intelligence completa é registrada novamente no recibo da integração, porque a branch-base continuou avançando. Limitações remanescentes: `PREMISSAS` e limiares seguem declarações de laboratório; a fixture Senac mantém cobertura de receita desconhecida (honesto: o experimento de origem não a estrutura), por isso é inviável mas nunca poderia ser positiva; `verify` prova integridade e reprodutibilidade, não autoria; sem replay contra export v21/JoinAds v2; um candidato por avaliação.

Fechamento das condições do veredito independente (RED-TEAM-V2-VERDICT.md): **R1** — o gate agora exige `custo.moeda_evidencia == observed` para `moeda_provada` (razão `moeda_custo_<evidencia>`), alinhado ao verificador; **R2** — `VERSAO_KERNEL = viability-kernel@2.0.0` (todos os hashes de resultado/replay mudam; replay regenerado). **R3** registrado: `Autorizacao` prova integridade e formato de identidade do `issuer`, não autoria; é uma REFERÊNCIA a uma autorização externa versionada, cuja autenticidade deve ser provada fora do kernel (assinatura/ledger do lado VOLC). A segunda rodada fechou **R4, R5, R7 e R8**; **R6** permanece uma escolha de política documentada.
