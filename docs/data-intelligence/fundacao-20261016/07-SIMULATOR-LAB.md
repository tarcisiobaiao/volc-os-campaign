# 07 — Simulator Lab (worker E, Fundação Data Intelligence, 2026-10-16)

Estado (taxonomia do manifesto §7): **construído · testado hermeticamente · testado com sintético**.
Nada aqui é "calibrado com dado real" nem prova de eficácia operacional. O simulador existe para
que contrato, replay/shadow (D), Model Lab (F) e observabilidade (G) sejam exercitados contra
armadilhas **conhecidas**, com gabarito.

Código: `experiments/data-intelligence-lab/src/volc_dil/fundacao/simulador/` (versão `1.0.0`,
catálogo `1.0.0`, `catalogo_sha256 = d449d43f…1600`). Pacote: `experiments/data-intelligence-lab/results/fundacao/simulador/`.
Testes: `tests/data-intelligence/fundacao/test_simulador_*.py` (113).

## 1. Arquitetura

```text
ParametrosMundo ──► gerar_mundo(params, seed[, orcamento_diario_micros]) ──► Mundo (VERDADE, C×T×K)
                                                                              │
ParametrosObservador ─────────────────► observar(mundo, params, cenario) ──► Leituras
                                                                              ├─ registros  (o que consumidores veem)
                                                                              ├─ gabarito   (verdade por obs_id; só avaliação)
                                                                              └─ execucoes  (livro de runs de coleta)
EspecCenario = mundo + observador + exercita + armadilhas + evidencia ──► simular(nome|espec, seed, …)
```

A verdade e a observação são **processos separados**: o mundo não sabe nada de coleta; o
observador só lê a verdade para decidir o que cada fonte entregaria e quando. Nenhum registro
carrega seed, nome de cenário legível como atalho para o mundo, nem parâmetro latente (lição F1-01).

Relação com o código herdado (reuso por composição, sem duplicar):

| Herdado | Uso aqui |
|---|---|
| `volc_dil.contracts.fingerprint` | JSON canônico, sha256, `versoes()`, `sha256_codigo` no manifesto do pacote |
| `volc_dil.contracts.Observacao` | alvo do `adaptador_contrato.para_observacao_contrato` (prova de que o registro cabe no contrato herdado) |
| `volc_dil.swarm.simulador` | técnica de números aleatórios comuns por CDF inversa (aqui generalizada para Poisson/Binomial/Gamma horários) |
| `volc_dil.replay.cenario` | separação verdade × emissão, preliminar × revisada, `nao_coletado`/`falha`; aqui a emissão vira um observador completo por fonte e por hora |

O swarm (célula × ciclo) e o replay v0 (campanha × dia, malha fechada, receita α·gasto^b) seguem
intactos e com seus resultados. Este simulador é campanha × hora × dispositivo, com leilão,
orçamento, funil e monetização; o replay/shadow novo pode fechar a malha re-simulando com
`orcamento_diario_micros` (CRN ⇒ contrafactual pareado).

## 2. Modelo generativo (verdade)

Índices: campanha `c`, hora local `t` (dia `d(t)`, hora `h(t)`, dia da semana), dispositivo `k ∈ {mobile, desktop, tablet}`.
Fuso: `America/Sao_Paulo` (instantes calculados por `zoneinfo`; sem DST desde 2019, mas o código é geral).

**Atributos da campanha** (sorteados uma vez):

```text
país_c ~ Cat(0.85 BR, 0.10 PT, 0.05 US)          conta_c = c mod n_contas
nova_c ~ Bern(frac_novas); lançamento: dia ~ U[0, 0.5·D), hora ~ U{0..23}; madura: idade U[30, 365] dias
Q_c   = 4000 · exp(0.8 z₀)            impressões elegíveis/dia
ctr_c ~ Beta(μκ, (1−μ)κ), μ=0.04, κ=150
rpm_c = 60 · mult_país · exp(0.35 z₁)  (R$ por 1000 pageviews)
q_c ~ U[0.55, 0.80] (continuação do funil); land_c ~ U[0.85, 0.97] (aterrissagem)
ROAS*_c = 1.0 · exp(0.32 z₂)          (alvo latente; forma calibrada, §5)
cpc_c = (1−ι) · land_c · E[pv/sessão] · rpm_c · mix_rpm / 1000 / (ROAS*_c · mix_cpc)   (derivado)
B_c   = round_centavo( U[0.6, 1.6] · E[custo diário irrestrito] )                       (orçamento, micros)
```

**Ciclo de vida e maturação** (idade `a` em horas desde o lançamento; madura ⇒ `a` grande):

```text
existe(c,t) = a ≥ 0 ;  ativo = existe ∧ ¬pausada_dia (p_pausa_dia = 0.01)
m_vol(a) = 1 − (1 − 0.15)·e^{−a/72}         m_cpc(a) = 1 + 0.6·e^{−a/120}
m_ctr(a) = 1 − 0.3·e^{−a/120}               m_ruído(a) = 1 + 1.5·e^{−a/120}
```

**Sazonalidade e choques**:

```text
s_dia(h) ∝ max(0.05, 1 + 0.55 cos(2π(h−21)/24) + 0.15 cos(4π(h−12)/24)),  média 1
s_sem(d) = 0.90 no fim de semana (volume);  rpm_sem(d) = 0.92;  rpm_hora(h) = 1 + 0.12 cos(2π(h−20)/24)
share_k(h): mobile = 0.78 + 0.08 cos(2π(h−23)/24), demais na proporção base
z_{c,d} = 0.6 z_{c,d−1} + √(1−0.6²)·0.15·ε   (AR(1) em log, estacionário)
```

**Leilão, pacing e saturação**:

```text
λ_{c,t,k}  = Q_c/24 · s_dia · s_sem · share_k · m_vol · exp(z·m_ruído − σ²/2) · ativo
CTR_{c,t,k} = clip(ctr_c · mult_ctr_k · m_ctr · ruído_ctr_dia, 1e−6, 0.5)
cpc̄_{c,t,k} = cpc_c · mult_cpc_k · m_cpc · fator_quebra_cpc(c,t)
C0_{c,t}   = Σ_k λ·CTR·cpc̄                         (custo esperado irrestrito)
w_{c,t}    = C0_{c,t} / Σ_{t'∈dia} C0_{c,t'}        (peso horário do pacing)
θ_{c,t}    = min(1, (κ·B_c(t)·w / C0)^{1/(1+η)}),  κ=1, η=0.3   (fração servida; CPC sobe com θ)
impressões ~ Poisson(λ·θ·G),  G ~ Gamma(1/φ, φ), φ=0.05     (heterocedástico: Var = λ + φλ²)
cliques    ~ Binom(impressões, CTR);  inválidos ~ Binom(cliques, ι=0.02)
CPC_t      = cpc̄ · θ^η · exp(σ_cpc·m_ruído·n − ½σ²),  σ_cpc = 0.15
corte rígido: o dia para de servir quando o gasto acumulado passaria de 2× o orçamento do dia
```

`B_c(t)` é o orçamento diário em vigor na hora `t` (mudanças intradiárias de cenário) ou o
`orcamento_diario_micros` (C, D) passado por quem fecha a malha.

**Tráfego inválido e outliers**: rajada de bot em (c,t) com `p_bot_hora`: `n_bot ~ Poisson(20·E[cliques_h] + 20)`,
70% desktop, cobrado no ato, `Binom(n_bot, 0.6)` detectado e creditado depois; aterrissagem 0.3,
RPM × 0.02. Pico de RPM com `p_pico_rpm_hora`, fator U[3, 8].

**Site e monetização**:

```text
sessões  ~ Binom(cliques − inválidos, land_c) ;  S₁ = sessões, S_j ~ Binom(S_{j−1}, q_c), j=2..5
pageviews = Σ_j S_j ;  destino = S_5   (entrada → páginas → destino)
RPM_{c,t,k} = rpm_c · mult_rpm_k · rpm_hora · rpm_sem · fator_quebra_rpm · fator_pico
receita = pv·RPM/1000 · G_r,  G_r ~ Gamma(pv/4, 4/pv)  (média 1, CV = √(4/pv): heterocedástico)
        + pv_bot · RPM/1000 · 0.02
custo_bruto = round(cliques·CPC·10⁶);  crédito = round((inválidos + bot_detectado)·CPC·10⁶);  custo_final = bruto − crédito
```

Dinheiro: `np.int64` em micros; custo em BRL; receita em BRL ou USD nativo por campanha
(`frac_campanhas_receita_usd`; a verdade USD é o BRL gerado ÷ `cambio_brl_por_usd`, arbitrário).

**Quebras de regime**: `QuebraRegime(alvo ∈ {rpm, cpc}, frac_campanhas, em_frac_periodo, hora, fator)`.
**Mudanças de orçamento**: `MudancaOrcamento(frac_campanhas, em_frac_periodo, hora, fator)`.

**Determinismo e CRN.** Cada fluxo aleatório é `default_rng(SeedSequence([seed, crc32(nome)]))`
com forma fixa; contagens e receita saem por CDF inversa de uniformes fixos. Consequências testadas:
mesma seed ⇒ mesmos bytes; cenários que só diferem nos parâmetros injetados compartilham o mesmo
acaso (mundos pareados); re-simular com outro orçamento muda o resultado coerentemente.

## 3. Processo de observação

### 3.1 Fontes e cadências (default)

| Fonte | Métricas | Leituras | Semântica |
|---|---|---|---|
| `google_ads` | `cost` (micros BRL), `clicks`, `impressions` | D0 às 06/12/18/23 (cobre até h−3), D-1 em D+1 04:00, backfill em D+3 05:00 | D0 `partial` inclui inválidos não creditados; D-1 aplica 50% do crédito (`maturidade=preliminar`); backfill = custo faturado verdadeiro (`final`) |
| `joinads` | `revenue` (micros, moeda da campanha, 2 casas), `pageviews` | intradiária 06/12/18/23 (até h−2), releituras D+1..D+3 07:00 | estimativa `f(a)=1−(1−0.85)e^{−a/18h}` com ruído que some ao fechar; a 3ª releitura fecha no verdadeiro quantizado |
| `site_analytics` | `sessions` (inclui bots), `pageviews` (sensor), `destino` | D+1 03:00 | exato (salvo R2/R4) |
| `legado_daily_metrics` (opcional) | `revenue`, `cost` | espelha a JoinAds + 5 min | efeito do gatilho legado (R5) |

Coletas depois do fim do período também são emitidas (o mundo inteiro acaba observado).

### 3.2 Defeitos e armadilhas

| Fenômeno | Como aparece | Parâmetro |
|---|---|---|
| Atraso / restatement | D0 → D-1 → backfill; `gabarito.restatement_pendente = valor − final` | `gads_*`, `join_*` |
| Intradiária estimada | `partial` + `maturidade=intradiaria`, `cobertura_ate` | `join_f0`, `join_sigma_estimativa` |
| Fonte fora do ar | `unavailable`, valor `None`, run `failed` | `janelas_fora_do_ar`, `p_execucao_indisponivel` |
| Linha ausente | `missing`, valor `None` | `p_ausente` |
| Payload inválido | `invalid`, valor `None`, motivo | `p_payload_invalido` |
| Dimensão não suportada | `unsupported` (receita × dispositivo, por conta/dia) | `join_consulta_dispositivo` |
| Zero confirmado | `zero_confirmed` = 0 (pausa, dia sem tráfego, 0,00 quantizado) | `p_pausa_dia` |
| Coleta atrasada | `late`, `available_previsto < available_at` | `p_atraso`, `atraso_*_h` |
| Recuperação | leitura final perdida é recoletada depois como `late` (armadilha `recuperacao_tardia`) | — |
| Duplicação | mesma `leitura_id`, `run_id`, `payload_sha256`, outro `ingested_at` | `p_duplicata` |
| Troca de `custom_key` | `custom_key_efetiva=id_post_wp ≠ solicitada`, entidade = post | `join_p_troca_chave_*` |
| Zero falso (MCP) | `observed`/`partial` com 0, sem motivo, onde a verdade é ausência | `p_zero_falso` |
| Retrodatado | `observed_at = janela_fim` em leitura não intradiária | `p_retrodatar` |
| R2 sensor sem campanha | sessões agregadas em `entidade="google/cpc"`, `entidade_tipo=utm_source_medium` | `site_descarta_utm_campaign_numerica` |
| R3 zero sintetizado | linha ausente e campanhas listadas sem métrica saem `zero_confirmed` | `gads_zero_sintetizado`, `gads_razao_campanhas_sem_metrica` |
| R4 dedup por segundo | `pageviews` do sensor < verdade (colisão 3% humano, 50% bot) | `site_dedup_por_segundo` |
| R5 gatilho legado | receita do último de 3 domínios; custo 0 até a sincronização | `emitir_legado_daily_metrics` |
| D0 multiversão | 16 runs D0/dia ⇒ até ~16 versões de `cost_micros` | `gads_horas_d0` |
| Run preso | run `running` sem `concluido_em`, sem registros | `p_execucao_presa` |

### 3.3 Invariantes garantidos (testados)

- `valor is None` ⇔ `status ∈ {missing, unavailable, unsupported, invalid}`; todo `None` tem `motivo`.
- `zero_confirmed` ⇒ `valor == 0`; `partial/observed/late` ⇒ `int ≥ 0`.
- `unidade="micros"` ⇒ métrica monetária e `moeda ∈ {BRL, USD}`; contagem ⇒ `moeda is None`.
- `observed_at ≤ available_at ≤ ingested_at`; `observed_at ≥ janela_inicio`.
- `available_at < janela_fim` só em leitura `intradia` e nunca com `observed`/`zero_confirmed`/`late`.
- Atrasos declarados respeitados (ex.: D-1 Google ≥ janela_fim + 4 h; releitura JoinAds ≥ janela_fim + 31 h).
- Registros em ordem de `available_at`; todo registro tem run no livro e as contagens batem.
- Conservação: o último valor conhecido (consumidor correto) de cada campanha × métrica × dia é a
  verdade (custo/contagens exatos; receita ± ½ centavo), em 8 cenários; a única lacuna é receita
  JoinAds com chave trocada em dia sem dado (forma real da API). Em `zero_falso` a conservação
  quebra **exatamente** nos registros marcados.

### 3.4 Registro e mapeamento para o contrato

`RegistroObservacao` (frozen, slots). Os 17 campos do contrato da missão, com grafia ASCII:

| Contrato da missão | Campo do registro | Observação |
|---|---|---|
| fonte, conta, entidade | `fonte`, `conta`, `entidade` | entidade = campaign.id sintético (11 dígitos), post, conta ou `google/cpc` |
| grão | `grao` | tupla ordenada (`["campaign","day"]`, `["day","url"]`, `["account","day"]`, `["account","day","device"]`) |
| métrica | `metrica` | `cost, clicks, impressions, revenue, pageviews, sessions, destino` |
| valor micros ou None | `valor` + `unidade` | `unidade="micros"` para dinheiro, `"contagem"` para contagens |
| moeda | `moeda` | ISO-4217 ou `None` |
| janela início/fim | `janela_inicio`, `janela_fim` | instantes UTC canônicos do dia civil local |
| timezone | `timezone` | `America/Sao_Paulo` |
| observed_at / available_at / ingested_at | idem | UTC, segundo, formato fixo ordenável como texto |
| run_id, payload_sha256 | idem | sha256 do payload sintético (compartilhado pelas métricas do mesmo payload) |
| status | `status` | os 8 valores da missão |
| motivo | `motivo` | obrigatório quando `valor is None` |

Extras (descartáveis pelo integrador): `obs_id, leitura_id, tipo_leitura, maturidade, cobertura_ate,
entidade_tipo, custom_key_solicitada, custom_key_efetiva, dimensoes, available_previsto, cenario, natureza`.
`RegistroObservacao.contrato()` devolve só os 17. `para_observacao_contrato` converte para o contrato
herdado (`partial` → `MEDIDO`+`PARCIAL`+`PRELIMINAR`; receita intradiária → `ESTIMATED_REVENUE`;
`pageviews` sem `Metrica` → `None`; `late`/`custom_key` vão para `motivo`). O módulo do worker A
(`volc_dil.fundacao.observacao`) não é importado.

## 4. Catálogo de cenários (versão 1.0.0; tamanho 50 campanhas × 30 dias × 24 h)

| Cenário | Tipo | O que injeta |
|---|---|---|
| `estavel` | base | só maduras, sem quebra/outlier; defeitos de coleta em taxas baixas |
| `campanha_nova_aprendendo` | mundo | 50% novas lançando até 60% do período (rampa, CPC +60%, CTR −30%, ruído ×2,5 no início) |
| `atraso_receita_longo` | observação | JoinAds sem intradiária, 1ª leitura D+1 10h, fecha na 6ª releitura, f0=0,5; 10% de coletas atrasadas |
| `restatement_custo` | ambos | inválidos 12%, bots, crédito D-1 de 20%, backfill em D+7 |
| `fonte_fora_do_ar` | observação | JoinAds fora 60 h (40% do período), Google 14 h (70%), 1% de runs falhos |
| `outlier_bot` | mundo | rajadas de bot (p=0,004/h, ×20) e picos de RPM |
| `quebra_regime_rpm` | mundo | RPM ×0,6 em 70% das campanhas no meio; CPC ×1,4 em 30% aos 65% |
| `mudanca_orcamento` | mundo | orçamentos 0,5–1,0× do irrestrito; 30% dobram (1/3, 14h), 30% cortam à metade (2/3, 9h) |
| `sazonal_fim_de_semana` | mundo | fim de semana com 60% do volume e 80% do RPM; ciclo diário mais forte |
| `escala_10x` | tamanho | 500 campanhas em 10 contas |
| `vazamento_tentado` | adversarial | 100% das leituras não intradiárias com `observed_at` retrodatado |
| `zero_falso` | adversarial | ausente/indisponível vira 0 `observed` (forma do Google Ads MCP 0.0.4) |
| `moeda_misturada` | adversarial | 50% das campanhas com receita USD |
| `identidade_trocada` | adversarial | troca de `custom_key` em 5% das linhas com dado e em todas sem dado; ids de post colidem com ids de campanha; pausas 5% |
| `sensor_sem_campanha` | produção (R2) | sensor anula `utm_campaign` numérico; 2% preservado |
| `zero_sintetizado_coletor` | produção (R3) | 4 campanhas sem métrica por ativa + linha ausente ⇒ zero indistinguível do confirmado (~80% zerados) |
| `dedup_por_segundo` | produção (R4) | colapso por segundo no sensor, com bots |
| `gatilho_legado_joinads` | produção (R5) | fonte `legado_daily_metrics`: último domínio vence, custo 0 inserido |
| `custo_d0_multiversao` | produção | 16 runs D0/dia (7h–22h), atraso 1 h |
| `execucao_presa` | produção | 5% dos runs presos em `running` |

Os seis últimos vêm do recibo `receipts/leituras-externas/RECIBO-LEITURAS-20261016.md` (L2, L3, L4,
L9, L10, L11) e do inventário §10 (R2–R5), com a evidência gravada em `EspecCenario.evidencia`.

## 5. Calibrado × arbitrário

Origem de cada parâmetro: `calibracao.FONTES_PARAMETROS` (classes `forma_real`, `documentacao_fonte`,
`literatura_nao_verificada`, `arbitrario`). Resumo:

- **Forma real (n minúsculo, só dispersão/forma):** ROAS campanha-dia do golden Meta×GAM
  (84 linhas com gasto e receita; p10≈0,48, p50≈0,99, p90≈1,47 ⇒ mediana 1, σ_log≈0,32; é tráfego
  Meta, não Search); quantização da receita a 2 casas e dias 0,00 ambíguos (JoinAds/shadow de 15/10); receita
  em USD (JoinAds). O mundo default mede ROAS p10/p50/p90 ≈ 0,64/1,06/1,71 (3 seeds), dentro das
  faixas de forma de `FAIXAS_FORMA` (teste). Nenhum valor monetário de cliente é parâmetro.
- **Documentação da fonte:** cadências D0 (4 passadas/dia), D-1, intraday JoinAds 06/12/18/23 + relê 3 dias,
  troca calada de `custom_key`, dimensões aceitas, fuso — `DATA-CAPABILITY-MATRIX.md`; zero falso do
  MCP — `LIBRARY-DECISIONS.md`; as seis armadilhas de produção — recibo do integrador.
- **Literatura, não reverificada (sem rede):** CTR médio de Search ~3–6% (benchmarks WordStream/LocaliQ);
  período de aprendizado de lances automáticos até ~7 dias e limite de 2× o orçamento diário (Ajuda do Google Ads).
- **Arbitrário:** RPM e seus multiplicadores, funil, perfis diário/semanal, dispositivos, países,
  elasticidade do CPC, taxas de inválidos/bots, maturação e ruído da estimativa JoinAds, frações de
  crédito do custo, taxas de defeito de coleta, câmbio sintético. Não há curva real de maturação de
  custo nem de receita no repositório (o recibo L10 mostra que ela começa a existir em produção:
  é o próximo insumo de calibração).

O CPC resultante (≈ R$ 0,20–0,26 médio) fica na mesma ordem de grandeza do shadow Google versionado; não foi ajustado a ele.

## 6. API pública (estável)

```python
from volc_dil.fundacao.simulador import (
    simular, Simulacao, cenario, CATALOGO, NOMES, ADVERSARIAIS, VERSAO_SIMULADOR, VERSAO_CATALOGO, catalogo_sha256,
    gerar_mundo, Mundo, observar, Leituras, RegistroObservacao, Gabarito,
    ParametrosMundo, ParametrosObservador, EspecCenario, MudancaOrcamento, QuebraRegime, JanelaForaDoAr,
    CAMPOS_CONTRATO, CAMPOS_EXTRAS, STATUS, STATUS_COM_VALOR, STATUS_SEM_VALOR,
    visao_as_of, somar_por_moeda, soma_ingenua, chave_fato, para_observacao_contrato, registros_contrato,
    verificar_forma, medir_forma, FONTES_PARAMETROS, FAIXAS_FORMA, iso,
)

simular(espec: str | EspecCenario, seed: int, *, n_campanhas: int | None = None, n_dias: int | None = None,
        orcamento_diario_micros: np.ndarray | None = None) -> Simulacao      # .espec .seed .mundo .leituras
gerar_mundo(params: ParametrosMundo, seed: int, orcamento_diario_micros: np.ndarray | None = None) -> Mundo
observar(mundo: Mundo, po: ParametrosObservador, *, cenario: str = "ad_hoc") -> Leituras
cenario(nome: str) -> EspecCenario;  EspecCenario.reduzir(*, n_campanhas=None, n_dias=None) -> EspecCenario
Mundo.horario(m) -> (C,T,K) · por_hora(m) -> (C,T) · por_dia_hora(m) -> (C,D,24) · diario(m) -> (C,D)
Mundo.tabela_diaria() / tabela_horaria() / tabela_campanhas() -> list[dict]; Mundo.flags: theta, ativo, existe, bot_hora, …
Leituras.registros: list[RegistroObservacao] · gabarito: dict[obs_id, Gabarito] · execucoes: list[dict]
visao_as_of(registros, as_of_iso_utc, *, relogio="available_at", exigir_custom_key=True) -> dict[chave, RegistroObservacao]
para_observacao_contrato(r) -> volc_dil.contracts.Observacao | None
pacote.gerar_pacote(destino, seed, nomes=None) -> manifesto; pacote.conteudo_cenario(nome, seed, tamanho=None) -> dict[arquivo, bytes]
```

Métricas horárias do mundo: `impressoes, cliques, cliques_invalidos, cliques_bot, cliques_bot_detectados,
custo_bruto_micros, credito_micros, custo_final_micros, sessoes, sessoes_bot, pageviews, pageviews_bot, destino, receita_micros`.

Mudança de semântica de qualquer parâmetro de cenário sobe `VERSAO_CATALOGO`; mudança de campo do
registro ou de equação sobe `VERSAO_SIMULADOR`.

## 7. Pacote de datasets

`python -I experiments/data-intelligence-lab/scripts/fundacao_simulador_pacote.py [--seed N] [--verificar]`
(seed padrão 20261016). 20 cenários em 4 campanhas × 7 dias (escala: 40 × 3), 32,2 MB, manifesto
`6898d28a…e8965`, `codigo_sha256 a1e5cfde…4fd1`. Por cenário: `cenario.json`, `observacoes.jsonl`
(entrada), `execucoes.jsonl` (entrada), `gabarito.jsonl`, `verdade_diaria.csv`, `verdade_horaria.csv`,
`verdade_campanhas.csv` (avaliação), `resumo.json`. `--verificar` regenera em memória e compara sha256
(passou). O pacote é fixture pequena: para estatística, gere pela API no tamanho que precisar (é determinístico).

Performance (`PERFORMANCE.json`, 10 CPUs, `OMP_NUM_THREADS=2`): 50 × 30 × 24 (108 mil células,
53 mil registros) ≈ 0,24 s mundo + 0,96 s observador = **1,2 s** (mediana de 3); 500 × 30 × 24
(1,08 milhão de células, 505 mil registros) = **16,6 s** (3,1 s + 13,5 s). Orçamento de teste: 15 s para 50 × 30.

## 8. Como D, F e G devem usar

**Regra comum:** consumidor lê só `observacoes.jsonl`/`execucoes.jsonl` (ou `Leituras.registros`/`execucoes`);
`gabarito`, `verdade_*` e `Mundo` são **só para medir erro**. Cortar por `available_at`, nunca por
`observed_at`/`janela_fim`. Versão de um fato = `observed_at` mais recente entre os disponíveis.

- **D (replay/shadow):** rodar o shadow em `estavel` e nos adversariais; o critério de sucesso é
  reproduzir a decisão de `visao_as_of` e **falhar ruidosamente** (ou recusar) em `vazamento_tentado`
  (retrodatado), `zero_falso`, `zero_sintetizado_coletor`, `identidade_trocada`, `moeda_misturada`,
  `gatilho_legado_joinads` (não ler a fonte legado). Malha fechada: re-simular dia a dia com
  `orcamento_diario_micros` decidido pela política (CRN mantém o mesmo acaso). `soma_ingenua` é a
  anti-baseline obrigatória.
- **F (Model Lab):** treinar/avaliar em mundos gerados pela API (≥ 50 × 90 para qualquer pergunta de
  surrogate, herança do Lab), com split temporal por `available_at`; usar `quebra_regime_rpm` e
  `campanha_nova_aprendendo` para medir degradação sem aviso; usar a verdade só como rótulo de avaliação.
  Nenhum resultado em simulação vira "eficaz".
- **G (observabilidade/DQ):** cada armadilha tem marca no gabarito (`zero_falso`, `zero_sintetizado`,
  `campanha_sem_linha`, `custom_key_trocada`, `id_colide_com_campanha`, `duplicata`, `retrodatado`,
  `moeda_nao_brl`, `coleta_atrasada`, `recuperacao_tardia`, `campanha_descartada_sensor`,
  `dedup_por_segundo`, `ultimo_dominio_vence`, `custo_zero_inserido`); D0 multiversão e run preso são
  verificáveis por propriedade (versões por campanha-dia; runs `running` sem registros). Medir
  precisão/recall dos detectores contra essas marcas; o detector **não** pode ler o gabarito.

## 9. Limites (o que o simulador não prova)

- Simulação não prova eficácia operacional de nenhuma política, modelo ou alerta.
- Os números são parâmetros; só a forma de ROAS, quantização, moeda e cadências tem ancoragem, com n minúsculo.
- Simplificações declaradas: troca de `custom_key` por linha (na API real é por chamada); um run por
  (fonte, conta, slot, dia de referência) (a JoinAds real relê 3 dias numa chamada); receita só de
  tráfego pago; sessão não carrega receita (receita agregada, como na realidade); câmbio fixo
  sintético; sem conversões/CAPI; sem Prebid/sinal de leilão; sem DST ativo no período.
- Robustez a seed: as propriedades dos testes de cenário/conservação/tempo/status/determinismo foram
  conferidas em 5 seeds; a de mudança de orçamento vale em 7 de 8 seeds (uma seed tem só uma campanha
  dobrada quase irrestrita). Os testes rodam numa seed fixa.
- A curva real de maturação intradiária de custo (recibo L10) ainda não foi usada: quando a thread D/F
  tiver as leituras v21 agregadas, `gads_horas_d0`/`gads_frac_credito_d1`/`join_f0`/`join_tau_maturacao_h`
  devem ser recalibrados na forma, e o catálogo sobe de versão.
