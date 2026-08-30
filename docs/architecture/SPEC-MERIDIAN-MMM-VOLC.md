# SPEC — Meridian MMM no VOLC O.S.

**Estado:** decisão arquitetural aceita; capacidade ainda não implementada  
**Data:** 2026-08-27  
**Papel:** transformar histórico agregado em leitura de incrementalidade, saturação e cenários de orçamento. Não operar campanhas em tempo real.

## 1. Decisão

O VOLC O.S. adotará o Google Meridian como candidato oficial para sua camada de Marketing Mix Modeling (MMM).

Essa camada responderá perguntas estratégicas:

- quanto cada canal contribuiu incrementalmente para receita ou outro KPI;
- como ROI e ROI marginal variam por canal;
- onde a resposta começa a saturar;
- como comparar cenários de alocação de orçamento;
- quanto do resultado pode ser explicado por mídia, tendência e controles observados.

Ela **não** responderá sozinha se uma campanha deve ser pausada agora, qual CPC deve ser aplicado hoje ou qual criativo deve ser trocado. Essas decisões permanecem no motor operacional, sob frescor, evidência, autorização e recibo.

## 2. Por que Meridian cabe no VOLC

Meridian é o framework MMM open-source do Google, baseado em inferência causal Bayesiana. Trabalha com dados agregados, não depende de cookies ou identidade individual, aceita modelos nacionais ou geográficos, suporta calibração por experimentos e produz curvas de resposta e cenários de orçamento.

O encaixe no VOLC é forte porque a economia da arbitragem precisa relacionar:

```text
investimento em mídia
        ↓
exposição e tráfego incremental
        ↓
consumo e monetização
        ↓
receita incremental
        ↓
margem incremental depois dos custos
```

O modelo não substitui atribuição por campanha. Ele é uma segunda lente, agregada e estratégica, para confrontar atribuição observacional, ruído de curto prazo e saturação.

## 3. Correções ao primeiro rascunho

### 3.1 Não há regra universal de “12 meses”

Mais histórico costuma ajudar, mas a suficiência depende de número de geos, períodos, canais, controles e parâmetros. O gate será o relatório EDA, a razão dados/parâmetros, convergência e largura dos intervalos de credibilidade — não um número mágico de meses.

### 3.2 O primeiro KPI não será `gross_profit`

Usar `receita - media_spend` como variável resposta e, ao mesmo tempo, usar `media_spend` como tratamento cria uma relação mecânica dentro do próprio alvo. O modelo inicial deve explicar uma variável de resultado que não contenha o custo de mídia, por exemplo:

- `publisher_revenue` agregado e conciliado; ou
- sessões monetizadas/conversões, com `revenue_per_kpi` comprovado.

O VOLC calculará **lucro incremental** depois do modelo:

```text
lucro incremental = receita incremental estimada
                    - investimento em mídia
                    - custos variáveis atribuíveis
```

### 3.3 Meridian opera no nível de canal

O framework é focado em canais. País, região e tempo podem aumentar a informação disponível, mas campanha, nicho, geo e formato não serão abertos simultaneamente sem prova de suficiência. Canais pequenos poderão precisar ser combinados.

## 4. Contrato do painel histórico

O primeiro produto da iniciativa não é um modelo; é um painel histórico reprodutível.

### Grão candidato

```text
semana × geo × canal
```

O modelo nacional será permitido quando não houver dimensão geográfica confiável. Quando houver dados mutuamente exclusivos e suficientes, o modelo geográfico será preferido.

### Entradas de mídia paga

- investimento;
- impressões, cliques ou outra exposição somável;
- alcance e frequência quando disponíveis e confiáveis;
- canal canônico: Google Search, Display, Demand Gen, Performance Max, Meta e outros efetivamente operados.

### Mídia orgânica

- alcance, impressões, visualizações ou cliques orgânicos somáveis;
- publicações e distribuição sem custo direto, sem inventar custo de mídia.

### KPI

- receita publisher reconciliada como primeira preferência; ou
- KPI somável com conversão econômica explícita e versionada.

CTR, RPM, CPC e margens percentuais não entram como KPI direto porque não são somáveis. Podem ser derivados ou usados em diagnósticos fora do modelo.

### Controles candidatos

Somente variáveis justificadas por um grafo causal e com série histórica:

- tendência e sazonalidade;
- feriados e eventos relevantes;
- Google Query Volume ou proxy de demanda de busca;
- mudanças de tracking e monetização;
- alterações de produto, preço ou inventário publicitário;
- variáveis que influenciaram simultaneamente planejamento de mídia e resultado.

Controles não serão adicionados como catálogo decorativo: cada um terá hipótese causal, fonte, cobertura e política de ausência.

## 5. Arquitetura

```text
Google Ads / Meta / outras fontes de custo
GAM / AdSense / JoinAds / receita reconciliada
Orgânico / calendário / controles
                 ↓
        camada de ingestão VOLC
                 ↓
   mart semanal versionado e imutável
                 ↓
         EDA + gate de prontidão
                 ↓
 runner Meridian isolado (Python/GPU opcional)
                 ↓
 modelo + diagnóstico + intervalos + curvas
                 ↓
 cenários de orçamento e ROI marginal
                 ↓
 QG / Cockpit estratégico / Bia read-only
                 ↓
 shadow mode → decisão humana → plano aprovado
```

Meridian ficará em um ambiente analítico isolado, e não dentro do bundle Vite nem do backend transacional. Cada execução terá:

- hash do dataset;
- janela temporal;
- configuração do modelo e priors;
- versão da biblioteca;
- seed;
- diagnósticos de convergência;
- artefatos e relatórios;
- estado `exploratorio`, `aceito`, `rejeitado` ou `substituido`;
- owner e instante da decisão.

## 6. Tabelas/contratos candidatos

Nomes finais dependem da revisão de schema:

- `mmm_dataset_snapshots` — identidade, corte, hash, cobertura e procedência;
- `mmm_weekly_facts` — painel semanal por geo/canal;
- `mmm_model_runs` — configuração, versão, estado e diagnóstico;
- `mmm_channel_effects` — contribuição, ROI, ROI marginal e intervalos;
- `mmm_response_curves` — curvas de resposta e saturação;
- `mmm_budget_scenarios` — restrições, cenário e resultado projetado;
- `mmm_calibrations` — experimento/prior usado e janela;
- `mmm_recommendations` — recomendação em shadow mode, nunca ação direta.

Ausência observacional não será convertida silenciosamente em zero. Zero só representa canal comprovadamente inativo no período. KPI e controles ausentes exigem imputação explícita, versionada e auditável.

## 7. Produto

### QG — Inteligência de investimento

- prontidão do dataset;
- canais e geos cobertos;
- janela e frescor;
- contribuição incremental com intervalo;
- ROI e ROI marginal;
- curva de saturação;
- cenário base e cenários alternativos;
- limitações e sinais ausentes.

### Bia

A Bia poderá responder:

- “Esse canal parece rentável por atribuição, mas também é incremental?”
- “Qual canal está mais próximo da saturação?”
- “O que o modelo sugere se mantivermos o orçamento total?”
- “Quais limitações impedem confiar neste cenário?”

Ela sempre exibirá versão, janela, intervalo de credibilidade e estado do modelo. Não transformará um cenário em comando operacional.

## 8. Gates de promoção

1. **Dataset pronto:** série completa, dimensões coerentes, moeda normalizada e procedência.
2. **EDA aceita:** inconsistências, canais pequenos, colinearidade e razão dados/parâmetros revisados.
3. **Modelo válido:** convergência e posterior predictive checks aceitáveis; intervalos apresentados.
4. **Calibração:** experimentos ou priors externos entram quando compatíveis, nunca para forçar uma resposta desejada.
5. **Shadow mode:** cenários são comparados com decisões e resultados posteriores, sem comandar mídia.
6. **Uso decisório:** somente modelos aceitos podem informar a Bia e o cockpit estratégico.
7. **Ação:** continua sujeita ao portão normal do VOLC; Meridian nunca ganha permissão direta de mutação.

## 9. Sequência de entrega

- M0 — escopo oficial e posição arquitetural;
- M1 — contrato causal, KPI e taxonomia de canais/geos;
- M2 — mart semanal e linhagem;
- M3 — relatório EDA e score de prontidão;
- M4 — baseline nacional ou geo em ambiente isolado;
- M5 — calibração e comparação de especificações;
- M6 — persistência de resultados e cockpit;
- M7 — scenario planner e Bia read-only;
- M8 — shadow mode com retrospectiva periódica.

## 10. Fontes oficiais consultadas em 2026-08-27

- [Google Meridian no GitHub](https://github.com/google/meridian)
- [Coletar e organizar dados](https://developers.google.com/meridian/docs/pre-modeling/collect-data)
- [Quantidade de dados necessária](https://developers.google.com/meridian/docs/pre-modeling/amount-data-needed)
- [Modelagem geográfica](https://developers.google.com/meridian/docs/pre-modeling/geo-selection-national-data)
- [EDA do Meridian](https://developers.google.com/meridian/docs/pre-modeling/perform-eda)
- [Scenario Planner](https://developers.google.com/meridian/docs/scenario-planning/meridian-scenario-planner)

