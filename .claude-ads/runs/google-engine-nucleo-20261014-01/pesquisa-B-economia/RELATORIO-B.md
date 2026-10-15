# Relatório B — economia e estatística (14/10/2026)

Pesquisador B, run `google-engine-nucleo-20261014-01`. Sem acesso a banco,
Google ou n8n vivo: auditoria só no código e nas migrations. Todo número de
experimento é **SINTÉTICO** (seed 20261014) e prova mecânica, não parâmetro
operacional nem ganho real.

Arquivos: `resultados.json` (B01–B36 + B37–B40 novos), `AUDITORIA-DADOS.md`
(respostas 1–5 com arquivo:linha), `experimentos/` (E1–E5 + instalação E4).

## 1. O que a auditoria de dados decide antes de qualquer modelo

1. **Não há as-of de receita nem de custo.** JoinAds/GAM fazem upsert por
   `(date, utm_campaign_value, domínio)` e guardam o último valor; o intraday
   (06/12/18/23) sobrescreve o anterior e o D-1 reescreve 3 dias. O ledger de
   coleta guarda só o **hash** do payload. `updated_at` é `timestamp` sem fuso.
   As tabelas de fotografia/previsão/realizado estão só desenhadas no SPEC.
   → B19/B20 (curva de maturação, 65/90/95%) **não têm parâmetro possível hoje**.
2. **Grão da ligação = campanha × dia por UTM** (`utm_campaign_value = campaign_id`).
   gclid não chega ao lado da receita. Receita por placement e por hora é NULL
   por desenho na v17_04; não existe receita por grupo nem por anúncio.
   O contrato de URL manda `utm_content={adgroupid}` e a JoinAds aceita
   `custom_key=utm_content` → **grupo é ingerível; anúncio não** (`vc_creative`
   não é chave aceita).
3. **Logs de decisão não servem para OPE**: há contexto, ação, regra/versão,
   timestamps; faltam ações elegíveis, **probabilidade da ação**, e recompensa
   econômica (`trafego_acompanhamento` não tem receita). Todo decisor é humano
   (`NIVEIS_QUE_APLICAM_SEM_HUMANO = frozenset()`).
4. **O VOLC não é DSP.** Ações: status, orçamento diário, alvo tCPA/tROAS,
   estratégia, negativas, exclusões (placement/IP), programação, ajustes de
   dispositivo/horário, recomendações — com aprovação e cooldown de 24 h.
   Lance por leilão, RTB, PID horário e bandit por clique não têm atuador.
5. **Definições existem e são boas na v17_04** (lucro/ROAS/receita por clique só
   com `reconciliada_fonte_unica`). No front, o "ROAS %" legado é **excedente**
   ((receita/gasto − 1)×100) e as cores (≥80/≥40/≥0) e o `status_roi` (≥20)
   são limiares pontuais sem amostra; `useDisplayROI` transforma ausência em 0.
6. **Câmbio**: "GAM 5,50 × JoinAds 5,20" é **refutado para produção pelo próprio
   repo** (medido no espelho; produção usa a mesma função, 5,25). O defeito vivo
   é o câmbio congelado desde 18/02/2026 e 5,50/5,35 embutidos no front; o SQL
   legado recalcula o histórico inteiro com a cotação atual.
7. **Dois furos na v17_04 (não aplicada)**: "reconciliada" exige janela fechada
   do **custo**, mas a receita do D-1 ainda muda até D+3; e a junção por data
   não confere o fuso da conta contra o da janela JoinAds (`America/Sao_Paulo`).

## 2. Experimentos (sintéticos)

**E1 — shrinkage** (`e1_shrinkage.py`, 3.000 entidades Zipf(1,6), 40 réplicas por κ):
- Beta-Binomial EB por máxima verossimilhança recupera a dispersão (κ=20 → 20,6;
  κ=500 → 497) e fica a ≤2% do oráculo em todos os cenários.
- **M ótimo = κ** (2,04 / 4,96 / 20,6 / 102 / 506). M=20 custa +34% de MSE
  quando κ=2 e +147% quando κ=500. "M=20" não é universal.
- Mínimo de cliques (10/30/100) perde para EB em todos os κ (κ=2: 146–160 vs 96).
- Maldição do vencedor: os 5% "melhores" pela taxa bruta estão +0,31..+0,51
  acima da verdade; com EB, ≈0.
- Decidir "lucrativo" por estimativa pontual segue errando 18–70% das vezes
  conforme κ, com ou sem shrinkage: a decisão precisa de P(p > limiar), não do ponto.
- 57% das entidades têm ≤2 cliques, mas somam 0,9% dos cliques.
- RPC/lucro: 59% das entidades com lucro observado ≤ 0 e 16% com receita 0.
  Lognormal é indefinida nesses casos; ajustada só nos positivos estima lucro
  médio 28× maior que o verdadeiro. Gamma-Poisson serve para a **contagem**
  (pageviews/clique), e o lucro é derivado depois (λ·RPM − CPC): MSE 45 vs 84.

**E2 — nowcasting** (`e2_nowcasting.py`; 3 campanhas, 240 dias, snapshots de 6 h até 168 h,
drift de reporte no dia 150; f(idade) = Σobs/Σfinal só de coortes maduras
**disponíveis no instante**):

| idade | ingênuo (erro / viés) | chain-ladder | Bornhuetter-Ferguson | só prior | IC90 CL |
|---|---|---|---|---|---|
| 6–12 h | 0,76 / −0,76 | 0,17 | **0,11** | 0,14 | 84% |
| 18–24 h | 0,49 / −0,49 | 0,13 | **0,09** | 0,14 | 85% |
| 54–96 h | 0,11 / −0,10 | 0,06 | **0,06** | 0,13 | 87% |

- Drift: nos 35 dias seguintes à mudança o CL fica com viés −16% e o IC90 cobre
  só 75%; volta ao normal depois que a janela de 28 dias se renova.
- Vazamento: o mesmo backtest usando o "final" sobrescrito de coortes ainda
  imaturas parece melhor (erro até 13% menor, viés até ~35% menor depois do
  drift) — é o otimismo que um backtest feito sobre a tabela atual teria.
- Fator ≈ 0 (estresse, f(6 h)=0,08): com a guarda F_MIN=0,15 o CL fica "não
  apurado" em 70% dos casos; BF segue com erro 0,13 (0,24 na campanha pequena).
- Campanha pequena (15 cliques/dia): BF ≈ CL ≈ 0,10–0,11; só prior 0,25.
- **65%/90%/95% do blueprint são exemplos**; aqui a curva foi escolhida por nós.
  O Google documenta SLO de 1 h para custo/cliques e métricas competitivas
  atualizadas 1×/dia, não "95% do custo em 3 h".

**E3 — OPE** (`e3_ope.py`, 3 ações de orçamento, 300 réplicas; `e3b`: obp 0.4.1 = numpy, diferença 0,0):

| cenário | IPS viés | DR viés | cobertura IC95 DR |
|---|---|---|---|
| A sobreposição boa, n=5000 | +0,003 | +0,003 | 96% |
| B n=200 | −0,004 (RMSE 0,11) | −0,005 (RMSE 0,11) | 94% |
| C sem suporte em 12% do log | −0,015 | **+0,051** | **25%** |
| D propensão inventada (uniforme) | **+0,447** | +0,019 | 99,7% (IPS: 0%) |

A diferença real entre a política de log e a alvo é 0,17: com n=200 o RMSE é
0,11. Sem suporte o DR fica viesado sem que o dado avise, e uma propensão
inventada **dobra** o valor estimado pelo IPS. Nada disso é ganho real.

**E4 — instalação**: VW 9.11.9 e MABWiser 2.7.4 instalam limpo em 3.13 e 3.14
(smoke ok). **obp 0.5.7 exige Python <3.11**; em 3.13/3.14 o pip recua em
silêncio para obp 0.4.1 (2021), passando por sdists com versão inconsistente.

**E5 — relatório de funis** (`e5_funis.py`): com 3 campanhas o Wilson95 vai de
0,10 a 0,91. O modelo com p verdadeira 0,55 apareceu com 42% observado e o de
0,40 com 50%: ordenar por % observada inverteu a ordem. ±10 pp exigem ≈97 campanhas avaliadas.

## 3. Vereditos (detalhe em resultados.json)

- **Refutadas (13)**: B01 VW "ouro da AdTech" para o VOLC; B02 "92% de confiança
  em 50 ms"; B11 LightweightMMM (arquivado); B17 Gamma-Poisson/lognormal para
  RPC/lucro; B18 M=20; B22 PID horário; B23 Mean-CVaR; B24 "degrau de segundo
  preço"; B25 RL de RTB; B27 inflar valor; B28 matriz de alavancagem;
  B29 scalper de 15 min; B32 decisão horária VW+EB.
- **Confirmadas (7)**: B12 Meridian é o sucessor ativo (mas não se aplica); B16
  Beta-Binomial para taxas; B20 as-of é pré-requisito; B37 chain-ladder/BF;
  B38 Wilson; B39 furos da v17_04; B40 defeito de câmbio (o real, não o 5,50×5,20).
- **Parciais (20)**: as outras bibliotecas são legítimas e mantidas
  (catboost, cvxpy, optuna, ortools, prophet, pymc-marketing, Riskfolio, VW), mas
  falta o dado; obp/mabwiser têm manutenção baixa (último push 06/2024 e 09/2024).
- Decisões: rejeitar 16 · adiar por pré-requisito 14 · extrair padrão 5 ·
  reutilizar existente 4 · integrar agora 1 (Wilson).

### Google Ads (B24, B27–B30), conferido na documentação oficial
- `segments.hour` é selecionável com `search_impression_share`,
  `search_top_impression_share`, `top_impression_percentage` e `average_cpc` (v25,
  lista "Selectable with"). Mas as métricas competitivas são atualizadas 1×/dia
  (answer/2544985), e a família `hora_dispositivo` do VOLC não coleta IS.
- O leilão não é de segundo preço puro: o anunciante paga o mínimo para superar
  o Ad Rank do concorrente abaixo e os limiares, ou o preço de reserva
  (answer/6297), e "quanto maior a diferença de Ad Rank, maior pode ser o CPC
  pela certeza de ganhar" (answer/1722122). O "degrau" de B24 não existe como
  objeto estável, e o "40% de desconto" não tem fonte.
- Value rules são o mecanismo oficial para valor diferente por local,
  dispositivo ou público (ADD/MULTIPLY/SET), e o Smart Bidding otimiza para o
  valor ajustado (answer/10518330; doc da API). Multiplicar o valor porque "a
  margem explodiu" (B27) ou alavancar uma previsão (B28) é fabricar o sinal que
  o próprio lance persegue, e isso contamina o relatório de conversão (fato ≠ previsão).
- RESTATE muda só o valor e afeta só as estratégias de valor/ROAS; RETRACT
  remove a conversão (answer/7686447). A janela de 7 dias para o autobidding
  aparece explicitamente para Hotel Ads. B30 (enviar previsão e corrigir
  depois) só é defensável como ação de conversão **declarada** de valor
  previsto, com `previsao_id` e restatement obrigatório, depois de medir o erro.

## 4. Deltas acionáveis para o integrador (≤ 5)

Todas são funções puras ou emendas pequenas, sem dependência nova.

1. **`wilson(k, n)` e `classificar_campanha(lucro_diario, dias_minimos, receita_reconciliada)`**
   (código pronto em `experimentos/e5_funis.py`, só stdlib).
   Alvo: novo `volc_ads/inteligencia_decisao/estatistica.py` (domínio puro).
   Teste sugerido (`backend/tests/test_inteligencia_decisao_estatistica.py`): Wilson(1,2)=[0,0945; 0,9055],
   Wilson(0,n) começa em 0, n=0 → None, k>n → ValueError; a classificação devolve
   `nao_elegivel` com receita não reconciliada ou dias < mínimo; `None` não vira 0;
   `indeterminada` quando o IC cruza 0.
2. **`beta_binomial_eb(k[], n[]) -> (a, b)` + `posterior_prob_acima(k, n, a, b, limiar)`**
   (MLE em `e1_shrinkage.py:beta_binom_mle`; para stdlib usar `math.lgamma`).
   Mesmo alvo. Entra como **evidência** nas propostas de termo/keyword
   (`search_negativa_bidirecional`), não como regra.
   Teste: com dado sintético de κ conhecido recupera κ±15%; P é monotônica em k;
   n=0 devolve o prior.
3. **Emenda na v17_04 antes de aplicá-la** (`supabase/migrations/v17_04_arbitragem_reconciliada.sql:88-106`):
   (a) status `receita_imatura` quando `metric_date > current_date - 3` (o lookback
   do D-1 JoinAds), avaliado antes de `reconciliada_fonte_unica`; (b) status
   `nao_reconciliada_fuso` quando o fuso da conta (`customer.time_zone`, a gravar
   ou ler) ≠ `America/Sao_Paulo`. Teste: dois cenários novos em
   `scripts/provas-v17_04.sql` (D-1 recém-coletado → imatura; conta em outro fuso → não reconciliada).
4. **`projetar_receita_bf(obs, f, prior, f_min=0.15) -> {valor, tipo:'previsao', metodo, f}`**
   (lógica em `e2_nowcasting.py`, BF + guarda). Alvo: o mesmo `estatistica.py`,
   **sem consumidor** até existir as-of (delta 5 da instrumentação). Teste: f=1
   devolve obs; f<f_min no CL devolve "não apurado"; a saída nunca tem
   `tipo='fato'`.
5. **Rótulos de métrica no contrato**: registrar em
   `docs/closure/traffic-operational-closure-v2/METRIC-CONTRACT.json` que
   RPC = receita/clique pago, RPM = receita/mil impressões ou pageviews e EPC
   não é métrica do VOLC, e que o "ROAS %" do legado é excedente. Teste:
   `src/pages/__tests__/campaign-metric-semantics.test.tsx` já cobre os nomes
   novos; acrescentar um caso RPC × RPM com denominadores distintos.

## 5. Instrumentação mínima futura

**Nowcasting (desbloqueia B14/B19/B20/B37)**
- `receita_snapshot` append-only: `fonte`, `date`, `chave` (utm_campaign_value ou
  utm_content), `dominio`, `revenue` bruto, `moeda`, `revenue_converted`,
  `cotacao_id`, `lido_em timestamptz`, `execucao_id`, `payload_sha256`. Uma
  linha por execução do n8n (06/12/18/23 e D-1), **além** do upsert atual.
  Sem UPDATE/DELETE (gatilho igual a `google_ads_append_only`).
- Custo: guardar no ledger as linhas lidas (ou `google_ads_campanha_dia_snapshot`
  com `colhida_em`) em vez de só o hash.
- `lido_em` com fuso, e o fuso da conta gravado no fato campanha-dia.
- Depois de 4–6 semanas: estimar f(idade) por fonte com razão de somas, janela
  móvel, backtest as-of e guarda F_MIN; publicar só como `previsao`.

**OPE (desbloqueia B26; condição para B01/B04/B13)**
- Em `trafego_proposta`, ou numa tabela de log de decisão ligada a ela:
  `fotografia_id` (as-of do contexto), `acoes_elegiveis jsonb` (todas as ações
  consideradas, com parâmetros), `acao_escolhida`,
  `propensao numeric NOT NULL` (probabilidade da ação sob a política que
  decidiu), `politica_id` + versão, `decisor` (regra/humano),
  `aleatorizacao_semente`.
- Recompensa: `trafego_realizado` com lucro **reconciliado e maduro** na janela
  pós-ação (`lido_em`, horizonte, `receita_status`).
- Enquanto o decisor for humano sem aleatorização, a propensão é desconhecida
  e o OPE fica **declarado impossível**: nunca imputar 1/K. Exploração
  randomizada (por exemplo, sortear entre propostas equivalentes) é decisão do
  dono, com teto financeiro.

## 6. Impedimentos de dados (não de modelo)

- Sem as-of de receita e de custo: não há curva de maturação nem backtest honesto.
- Sem receita abaixo de campanha-dia: não há ROAS por grupo/anúncio/placement/hora,
  e ratear pelo custo não é atribuição (B36).
- Sem propensão nem recompensa econômica no ledger: não há OPE.
- Sem versão formal do modelo de funil: o prefixo de URL (/r, /wg) é diretório,
  não versão, e o vínculo campanha→funil só existe quando confirmado por humano.
- Câmbio congelado e embutido: todo RPC em BRL de hoje é suspeito até existir
  um fx versionado pela data do fato.
