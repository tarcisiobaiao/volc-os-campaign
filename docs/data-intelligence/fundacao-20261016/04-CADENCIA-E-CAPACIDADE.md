# 04 — Cadência e capacidade (frente B)

Estado: modelo **construído e testado hermeticamente** (46 testes de capacidade + 23 do coletor);
bytes **medidos** num PostgreSQL 16 descartável com dados **sintéticos**, mais **três números reais**
lidos read-only pelo integrador (1.140 B/linha da `google_ads_observation`, redundância real de termos,
GIN sem uso — `receipts/leituras-externas/RECIBO-LEITURAS-20261016.md:30-33,69`). Contagens de linhas e
perfil horário calibrados com dado real versionado no repositório (recibos de 15/10). **Revisado após a
revisão adversarial R1** (F7, F13, F25, F26, H5 — resposta em `handoffs/HANDOFF-B.md` §8).
Abreviações de evidência como em `05-ARQUITETURA-COLETORES.md` (J, M, MS, P, EA). Identificadores de
conta/campanha e valores monetários reais foram retirados (R1 F25): onde importa, só razões.

Artefatos (gerados, não editar à mão):

- `benchmarks/capacidade/pg_medicoes.json` (+ `pg_medicoes_dil_obs.json`, rodada do DDL da frente A) —
  script `fundacao_capacidade_pg.py`; **todas** as medições em `benchmarks/capacidade/MEDICOES.md`;
- `benchmarks/capacidade/horas_campanha_d30.json` — perfil horário real, só fatias (script `fundacao_capacidade_horas.py`);
- `benchmarks/capacidade/modelo.json` + `MODELO.md` — grade do modelo com manifesto
  (seed `20261016`, versões, sha256 de código/entradas/resultado; script `fundacao_capacidade_modelo.py`).

## 1. Os oito números (corrigidos na R1)

| # | Número | Fonte |
|---|---|---|
| 1 | Termos: **89,4%** de redundância **medida** (23.891 lidas → 2.525 distintas) com ~21 h de vida do coletor; em regime estacionário (42 leituras por termo-dia) o esperado é **97,1%** (p de revisão 0,005). O modelo com p = 0 e as 13 execuções reais prevê 2.546 distintas (real 2.525, −0,8%): a diferença 10,6% × 4,3% apontada na R1 é idade do coletor (H5), não premissa errada | recibo :31,:69; `MODELO.md` §4b; `test_redundancia_de_coletor_jovem…` |
| 2 | Linha **real** da v21: **1.140 B** (recibo, 24.141 linhas); réplica sintética **851 B** (subestimava 25%); a mesma linha tipada em colunas: **286 B** (4,0× menor que a real) | recibo :32; `MEDICOES.md` |
| 3 | Por valor de métrica: largo tipado **36 B**, largo JSONB 64 B, réplica v21 106 B, longo tipado 258 B, longo com texto 348 B e **DDL real da frente A (`dil_obs_0001`, longo) 1.084 B** | `MEDICOES.md`, 1e6 linhas |
| 4 | Payload GAQL de campanha (448 B de JSON): **718 B** gravado linha a linha (abaixo do limiar do TOAST) × **75 B/linha** em lote jsonb de 200 (termos: 1.109 × 172 B; lz4 130 B) — payload sintético, compressão real será pior | `MEDICOES.md` |
| 5 | Hoje (1 conta, agenda documentada): v21 com bytes reais **≈17 MB/dia** → 6,8 GB em 13 meses, 18,8 GB em 3 anos; política recomendada **0,43 MB/dia** → 0,17 GB / 0,24 GB | `MODELO.md` §3 |
| 6 | ×100, vertical completa, horária 24 h: v21 real **1,78 GB/dia → 704 GB em 13 m e 1,9 TB em 3 a**; recomendada (largo tipado) **0,06 GB/dia → 22 GB e 30 GB**; a mesma política sobre o DDL longo da frente A: 209 GB e 217 GB | `MODELO.md` §4 |
| 7 | Quota Google Ads (R1 F7): a agenda atual faz **92 operações/dia por conta + 26 fixas** (D0/D-1: `customer_client` + 4 GAQL por conta) → cabem **162 contas** no Basic (15.000/dia), 31 no Explorer; com D0 a cada 10 min, **24 contas**; com termos 1×/dia, 182 | J:P/collector-inventory.json:111-117,136-142,161-168; comum.md:173-181 |
| 8 | `as_of` por chave (EXECUTE, planejamento incluído, n = 5.000): p50 **0,058 ms** (1e6) e **0,216 ms** (1e7), p99 0,24 / 1,25 ms; ingestão de lote de 1.000 + commit: p50 **11–21 ms** (n = 60; ≈48–91 mil linhas/s nesta rodada, com a máquina disputada). `as_of` **global** na função real `dil_obs.observacao_as_of`: **10–27 s** em 1e6 linhas (consulta inline equivalente: 0,2–0,3 s) | `MEDICOES.md` |

Leitura: **o problema de volume do VOLC não é a ingestão, é regravar o que não mudou** em linhas
largas de texto+JSONB com índices que ninguém usa (GIN de `metrics` e `dimensions`: 0 scans em
produção, recibo :33). E um achado novo para a frente A: a função `observacao_as_of` do DDL candidato
não é inlinada (tem `SET search_path`) e materializa a linha inteira de cada chave — §5.4.

## 2. Fórmula da cadência útil

`cadência útil = min( frescor real da fonte , tempo até a decisão possível )`, restrita por
`custo(volume × bytes) + quota + atraso de atribuição`. Em termos do modelo:

- **Frescor da fonte**: quanto tempo até a API mostrar um valor novo. Para Google Ads o repositório
  diz só "estatísticas de Ads atualizam com atraso" e recusa 15–30 min por isso
  (M:.claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-C-dados/resultados.json:1017,1029);
  **o atraso em horas não está no repositório** (não confirmado). JoinAds: não documentado.
- **Probabilidade de dado novo** entre duas leituras: `p = f_mutável·(1 − e^{−∫λ})`. Calibração real:
  a campanha ativa teve **17,3 impressões/h** em média (pico 30,9 às 12h, vale 1,7 às 04h; D30,
  J:P/receipts/d-live-campaign-audit.json:667-1020). Logo, para a campanha ativa, quase toda leitura
  horária traz número diferente — mas a diferença é de poucas impressões; das 5 campanhas da conta,
  4 não mudam nunca (`fração mutável` 0,2).
- **Tempo até decisão**: nenhuma decisão automática existe (mutation gate; J:docs/audits/GOOGLE-ADS-COLETA-CANONICA-2026-10-15.md,
  "Limites"). Revisão de lance/orçamento é diária. Logo, o que justifica intraday é **detecção de
  incidente** (gasto descontrolado, conversão quebrada), não otimização.
- **Atraso de atribuição**: conversões chegam depois do clique; "não medido" (J:P/reconciliation.json:1013).
  Por isso D-1 tem segunda passada e JoinAds reprocessa D-7..D-1.

## 3. Política de frequência por fonte

"Confirmado" = agenda lida no repositório com ref+caminho+linha. "Missão" = parâmetro do baseline
da missão sem confirmação no repositório.

| Fonte / granularidade | Atual | Proposta | Justificativa (com número) | Custo/dia por conta | Quando mudar |
|---|---|---|---|---|---|
| Google Ads campanha D0 | `7 6-23 * * *` (confirmado, J:P/collector-inventory.json:109) | **manter horária 06–23**; ad group D0 na mesma agenda | p(mudou) ≈ 1 por hora na campanha ativa; ninguém decide em < 1 h; cobre 92–95% da entrega antes de 23:07 (§4) | 18 execuções × (1 `customer_client` + 4 GAQL) = 72 operações por conta + 18 fixas; 90 linhas lidas, 22 distintas | estender a 24 h quando existir ator noturno (alerta com plantão ou automação aprovada) ou se o teste do §4 mostrar noite > limiar |
| Google Ads campanha D-1 | `17 6,14 * * *` (confirmado, :134) | **manter** | 2ª passada absorve conversão atrasada (J:P/canonical-collection-plan.json:19) | 8 operações por conta + 2 fixas | 3ª passada (D-2) se o teste de atraso (handoff) mostrar revisão > 5% após 14h |
| Google Ads termos + keywords | `23 */4 * * *`, janela D-7..D-1 (confirmado) | **1×/dia** (ex.: `23 7 * * *`) para D-7..D-1; se termos virarem insumo intraday, um job **separado** só de D0 | janela é toda de dias fechados: 6 leituras/dia de 7 dias = 42 leituras de cada termo-dia; 97,1% redundante em regime (89,4% medido com ~21 h de vida — ver H5 abaixo); 13.452 → 2.242 linhas lidas/dia | 12 → 2 operações por conta (+6 → 1 fixa); 13,4 mil → 2,2 mil linhas | voltar a 4 h só com consumidor intraday real; o próprio plano pede "reduzir após revisão medida" (:20) — esta é a revisão de volume (quota é irrelevante a 1 conta) |
| Ad group / anúncio D-1; hora, dispositivo, geo D-1 | não coletado (J:docs/audits/GOOGLE-ADS-COLETA-CANONICA-2026-10-15.md:11) | **1×/dia** às 06:37 (hora/dispositivo/geo) e junto do D-1 (grupo/anúncio) | plano canônico: "D-1 daily, hourly dimension once daily" (J:P/canonical-collection-plan.json:25); hora como segmento intraday é desperdício (J:P/coverage-matrix.json:220-229) | +25 operações por conta na vertical completa (117 por conta + 26 fixas) | — |
| JoinAds intraday v2 | `15 6-22/2 * * *` (confirmado, J:n8n/joinads_v2_intraday.json:10) | **manter 2 h** | receita do parceiro é sinal lento e pequeno (ordem de grandeza de 1 dólar/dia na conta atual, J:docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md:91-97; valor omitido); frescor do parceiro não documentado | 81 chamadas (premissa 9 endpoints × 9 execuções) | 1 h só se o frescor medido do parceiro for < 1 h |
| JoinAds fechado | `20 6 * * *`, D-7..D-1 (confirmado) | **manter** | restatement de receita; repetição 58101 não duplicou (idempotência determinística) | 64 chamadas | estender janela se houver revisão após D-7 |
| Goal health / conversion health / políticas | **não existe coletor** (J:P/coverage-matrix.json:196,205); missão: 30–60 min (não confirmado) | **diário + sob demanda antes de revisão**, e **60 min só para contas com gasto ativo** e só `conversion_action.status` + resumo de política | o plano canônico pede "daily plus on-demand" (J:P/canonical-collection-plan.json:21); 60 min custa 24 operações/conta: 2.400 a ×100 (16% do Basic; somado à agenda atual de 9.226 a ×100, chega a 77%) | 1 → 24 operações | 30 min só em modo incidente |
| Modo incidente | não existe; missão: 10–15 min temporário | **10 min no D0 da conta afetada, por no máximo 6 h, disparado por regra** | 10 min = 5 operações/h a mais que a horária por conta; 6 h ≈ 30 operações extras; teto: (15.000 − uso base)/30 incidentes de 6 h por dia | +5 operações/h | desligar automaticamente no fim da janela |
| GTM (sensor v3) | evento; lote **10 s ou 20 eventos** (confirmado, MS:measurement/gtm/volc-sensor-v3.html:31-32; servidor MAX_BATCH 20 e 64 KB, MS:supabase/functions/volc-ingest/index.ts:6-7) | **manter** | não há cadência: o navegador empurra; volume atual 115 eventos em ~30 dias (J:EA/schema-inventory.json:116) | ~4 eventos/dia hoje; 218/dia se cada clique pago virar sessão de 8 eventos | só se o corpo de 64 KB estourar (não ocorre com 20 eventos) |

**Quanto custa encurtar a cadência intraday** (escala atual, `MODELO.md` §3; operações = a·contas + b):

| Cadência D0/JoinAds intraday | Ops Google Ads/dia: por conta (a) + fixas (b) | Contas no Basic | Contas no Explorer | Versões distintas por campanha-dia (D0) | Redundância D0 |
|---|---:|---:|---:|---:|---:|
| atual (06–23 h, JoinAds 2 h) | 92 + 26 | 162 | 31 | 4,4 | 75,6% |
| horária 24 h | 116 + 32 | 129 | 24 | 5,5 | 77,1% |
| 15 min | 404 + 104 | 36 | 6 | 17,3 | 82,0% |
| 10 min | 596 + 152 | 24 | 4 | 23,9 | 83,4% |

A 1ª versão contava 1 consulta por conta por execução (32 operações/dia, 468 contas): o coletor real
faz 5 consultas por execução no D0/D-1 (R1 F7). Recibo de produção confirma a parte de mudança: no D0,
`p(mudou)` = 0,20 em toda hora de 06 a 23 (1 de 5 campanhas muda; recibo :30) — o modelo usa fração
mutável 0,2 e prevê 0,2 × (1 − e^{−λΔt}) ≈ 0,20. A cadência de 10 min produz ~115 versões/dia da
campanha ativa (vs ~18 na horária): é dado novo, mas é a mesma curva acumulada amostrada mais fino; só
vale com decisão de 10 min — hoje não existe.

**H5 — a janela de 7 dias pode não ser regime estável.** A redundância de 89,4% foi medida com o
coletor de termos com ~21 h de vida (13 execuções; recibo :69): cada termo-dia tinha sido lido ~9 vezes,
não 42. Em regime, com p ≈ 0, a redundância tende a 41/42 = 97,6%. Até existir uma semana completa de
execuções (≥ 42 leituras do termo-dia mais antigo), **nenhuma das duas razões é medida de regime**: a
consulta (b) do handoff deve ser repetida após 7 dias de coletor contínuo, e a razão de distintas por
termo-dia (`count(distinct metrics) / count(distinct observation_key)`) é o número a acompanhar.

## 4. Janela D0 06–23 deve cobrir 24 h?

**O que dá para afirmar** (dado real, `horas_campanha_d30.json`, D30 agregado por hora da campanha
ativa da conta; "ad_schedule: none configured; observed delivery spans hours 0-23",
J:P/receipts/d-live-campaign-audit.json:1034):

| Fatia do dia | Impressões | Cliques | Custo | Conversões (plataforma) |
|---|---:|---:|---:|---:|
| 00:00–05:59 | 5,0% | 6,5% | 6,1% | 6,5% |
| hora 23 | 1,3% | 2,1% | 1,7% | 0,4% |
| fora da última leitura do D0 (00–06 + 23:07–23:59, aprox.) | 6,1% | 8,3% | **7,6%** | 6,9% |

1. **Não há perda de dado**: a janela D0 é acumulada do dia; a execução das 06:07 já vê a
   madrugada, e o trecho 23:07–23:59 aparece no D-1 das 06:17.
2. **Há perda de frescor**: o maior buraco sem leitura é de 7 h (23:07 → 06:07), que concentra ~7,6% do
   gasto diário. Um incidente noturno é visto até 7 h depois.
3. **Custo de cobrir 24 h**: +24 operações/dia por conta e +6 fixas (92 + 26 → 116 + 32; Basic de 162 → 129 contas) e +6 leituras
   da campanha por dia. Em armazenamento, irrelevante.
4. **Não dá para afirmar** a variabilidade dia a dia da madrugada: o repositório só tem o agregado de
   30 dias por hora, não data × hora (as 65 linhas data×hora×dispositivo de 14/10 só têm a contagem
   registrada, J:P/gaql-catalog.json:28).

**Recomendação**: manter 06–23 enquanto não existir ator noturno (o valor da leitura noturna é ~0
sem alguém para agir). Ao ligar alertas com plantão ou automação aprovada, passar a `7 * * * *`.

**Teste read-only que decide** (uma consulta GAQL por conta, 1 operação; executar só por caminho
autorizado, sem imprimir credencial):

```sql
SELECT campaign.id, segments.date, segments.hour,
       metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
FROM campaign
WHERE segments.date BETWEEN '2026-07-18' AND '2026-10-15'
  AND metrics.impressions > 0
```

Regra de decisão pré-registrada: estender para 24 h se, em 90 dias, o **p95 da fração diária do
custo entre 23:00 e 05:59** passar de 15%, **ou** se algum dia tiver gasto noturno > 30% do
orçamento diário, **ou** se existir ator noturno. Para receita, o mesmo com o GAM `hourly_stats`
(único coletor horário 24 h, J:EA/writer-reader-map.json:251-254; schema a ler antes da consulta).

## 5. Medições no PostgreSQL descartável

**Todas** as medições, com n, mín, p50, p95, p99, máx, média e desvio, estão em
`benchmarks/capacidade/MEDICOES.md` (gerado do JSON; nenhuma linha omitida — R1 F26). Aqui, o resumo.

Ambiente: PostgreSQL 16.11 (Homebrew, arm64), cluster temporário em
`experiments/data-intelligence-lab/artifacts/fundacao_capacidade_pg/` (gitignored), socket unix próprio em
`/private/tmp/pgfb-*` (caminho curto por causa do limite de 104 caracteres), `listen_addresses=''`, porta 54931,
`fsync=on`, `synchronous_commit=on`, `wal_level=minimal`, `max_wal_size=256MB`, `shared_buffers=256MB`,
`autovacuum=off`, TOAST `pglz`. Duas rodadas: principal (1.643 s, pico amostrado do diretório 3,20 GiB) e
dedicada ao DDL da frente A (878 s, pico 2,33 GiB); **cluster e socket apagados nas duas**. A máquina estava
disputada com outros workers: as latências desta rodada são piores que as da 1ª (ingestão p50 11–21 ms
contra 5–6,5 ms) — publicadas como estão. Amostras: `as_of` pontual n = 5.000; snapshot e ingestão n = 60;
consultas globais 5 repetições após 1 aquecimento (todas as repetições no JSON). Dados sintéticos
determinísticos: 10 contas × N entidades × 90 dias, 10% das chaves com 2ª versão.

Variantes da tabela de observação:

| Variante | Desenho | Índices |
|---|---|---|
| `longo` | 1 linha por métrica; ids `bigint`/`smallint`, `valor bigint`, `payload_sha256 bytea` | PK `id`; único `(chave lógica, disponivel_em desc)` = `as_of`; BRIN `disponivel_em` |
| `texto` | igual, ids e códigos em `text`, valor `numeric`, sha em hex | idem |
| `largo` | 1 linha por entidade×leitura, 8 métricas `bigint` (2 nulas) | PK; único `as_of` sem métrica; BRIN |
| `jsonb` | igual ao largo, métricas num `jsonb` | idem |
| `v21` | réplica de `google_ads_observation` (J:supabase/migrations/v21_01_google_ads_coleta_canonica.sql:94-145) | PK uuid; `UNIQUE (run_id, observation_key)`; 2 btree; 2 GIN `jsonb_path_ops` |
| `dil_obs_0001` | **DDL real candidato da frente A** (`migrations_candidatas/dil_obs_0001_schema_observacao.sql`), formato longo, chaves sha256 em hex, inserção direta como superusuário (sem a RPC) | PK; `uq_obs_chave_idempotencia`; `uq_obs_versao (chave_natural, available_at desc)`; `ix_obs_chave_base`, `ix_obs_entidade`, `ix_obs_lote`, `ix_obs_run` |

### 5.1 Tamanho (1e6 linhas; 1e5 e 1e7 iguais a ±1% por linha)

| Variante | heap B/linha | índices B/linha | total B/linha | B por valor de métrica |
|---|---:|---:|---:|---:|
| longo | 167,3 | 90,3 | 257,6 | 257,6 |
| longo particionado (4 meses) | 167,3 | 99,6 | 267,0 | 267,0 |
| texto | 230,4 | 118,0 | 348,4 | 348,4 |
| largo | 204,9 | 81,5 | 286,4 | 35,8 |
| jsonb | 431,3 | 81,5 | 512,8 | 64,1 |
| v21 (réplica) | 630,4 | 220,3 | 850,7 | 106,3 |
| **v21 real (produção, recibo :32)** | – | – | **1.140** | ~143 (8 métricas) |
| **dil_obs_0001 (frente A)** | 630,4 | 453,3 | **1.083,7** | **1.083,7** |

No DDL da frente A, os três índices sobre texto hex de 64 caracteres (`uq_obs_chave_idempotencia`,
`ix_obs_chave_base`, `uq_obs_versao`) somam 370 MB em 1e6 linhas (370 B/linha); `ix_obs_chave_base` duplica
`uq_obs_chave_idempotencia` em todas as linhas de tipo `leitura` (as duas chaves são iguais por CHECK).

Payload bruto (20.000 linhas GAQL sintéticas): campanha 448 B de JSON → 718 B por linha jsonb ×
75 B/linha em lote de 200 (pglz); termo 782 → 1.109 × 172 B (lz4 130 B). O sintético repete strings mais
que o real; o real do lote v21 é 1.689 B por linha de `google_ads_raw_batch` (recibo :32, nº de linhas da
API por lote não lido).

### 5.2 Latência por chamada (p50 / p99, ms)

| Medida (sem partição → com partição) | 1e5 | 1e6 | 1e7 |
|---|---:|---:|---:|
| `as_of` por chave, longo | 0,036 / 0,29 → 0,075 / 1,47 | 0,058 / 0,24 → 0,051 / 0,87 | 0,216 / 1,25 → 0,187 / 1,33 |
| `as_of` por chave, `dil_obs_0001` | 0,018 / 0,19 | 0,069 / 2,04 | – |
| `as_of` por chave, réplica v21 (`campaign_ix`) | 0,048 / 0,33 | 0,061 / 3,17 | – |
| snapshot conta×dia (`DISTINCT ON`), longo | 0,56 → 0,18 | 4,8 → 2,0 | 34,4 → 14,7 |
| ingestão 1.000 + commit, longo — cru / dedup | 13,2 / 16,3 | 14,6 / 20,7 | 13,2 / 11,0 |
| ingestão 5.000 + commit, longo — cru / dedup | 67 / 104 | 95 / 126 | 55 / 69 |

Leitura honesta: com n maior e a máquina disputada, a cauda (p99, máx) é 5–20× a mediana; `as_of`
pontual fica abaixo de 1 ms no p50 em todas as escalas e abaixo de 3,2 ms no p99. A ingestão continua
com folga (≥ 48 mil linhas/s por conexão no p50, pior caso: dedup em 1e6). A partição melhora o snapshot de um dia (2,3–3×) e
deixa o pontual igual ou pior na cauda.

### 5.3 `as_of` GLOBAL (todas as chaves; R1 F26) — s, mediana de 5 após 1 aquecimento

| Consulta | 1e5 (meio / fim) | 1e6 (meio / fim) |
|---|---:|---:|
| `dil_obs.observacao_as_of(t)` (função real da frente A) | 0,12 / 0,99 | **8,5 / 17,5** |
| mesma consulta inline, linha inteira (`DISTINCT ON … o.*`) | 0,10 / 0,07 | **0,18 / 0,32** |
| inline só a chave (index-only scan em `uq_obs_versao`) | 0,035 / 0,021 | 0,12 / 0,18 |
| `dil_obs.observacao_latest` (= `as_of(now())`) | 0,86 | **19,0** (máx 38,8) |
| longo sintético, `DISTINCT ON` total (snapshot) | 0,071 | 0,69 |
| Parquet: DuckDB / Polars | 0,009 / 0,013 | 0,071 / 0,112 (1e7: 0,92 / 1,54) |

### 5.4 Achado para a frente A (não corrigido aqui; fora do ownership de B)

A função `dil_obs.observacao_as_of` é `LANGUAGE sql STABLE … SET search_path = ''`. Funções com
cláusula `SET` não são inlinadas pelo planejador: o conjunto inteiro (linha completa de cada chave) é
materializado antes do `count`/filtro de quem chama. Resultado medido: **48–55× mais lenta** que a mesma
consulta inline em 1e6 linhas (8,5 s × 0,18 s; 17,5 s × 0,32 s), e a view `observacao_latest` herda o
custo (19 s). Opções para a frente A, a medir: view `security_invoker` com o `DISTINCT ON` direto
(inlinável), ou função `SECURITY INVOKER` sem `SET` com nomes totalmente qualificados. Também: o formato
longo do DDL custa **1.084 B por valor**, 30× o largo tipado e ~7,6× a linha real da v21 por valor.

### 5.5 DuckDB / Polars (só leitura analítica de snapshot)

DuckDB sobre Parquet reconstrói um snapshot inteiro ~10× mais rápido que o Postgres (0,071 × 0,69 s em
1e6); útil para replays históricos grandes sobre partições frias exportadas, irrelevante para o replay v0
(≤ 13 mil observações por snapshot). O tamanho do Parquet sintético (< 1 B/linha) não é representativo.

## 6. Recomendações (com números)

1. **Gravar só o que mudou** (−94% das observações na vertical completa ×100 horária: 1,46 M → 83 mil
   linhas/dia, com p de revisão de termos 0,005), mantendo no recibo do run "li N, igual M" para provar
   cobertura. O coletor seguro já faz isso pelo `Registro` da frente A (05 §3.2).
2. **Payload bruto: hash por linha, linhas novas gravadas juntas num lote jsonb** ("linha em lote"):
   dedup por lote inteiro quase nunca acontece em janela grande (100% dos lotes de termos continuam
   "novos"); dedup linha a linha sem lote paga 718–1.109 B/linha. Na vertical ×100 horária o payload cai
   de ~0,23 para ~0,02 GB/dia.
3. **Colunas tipadas, não JSONB nem formato longo, para as métricas**: largo tipado 36 B/valor; JSONB 64;
   réplica v21 106; v21 real ~143; longo tipado 258; DDL longo da frente A 1.084. Se o contrato exigir
   estado por métrica, `NULL` + bitmask de estado cabe no largo. Decisão a alinhar com a frente A: com o
   DDL longo atual, a política recomendada a ×100 vai de 30 GB para 217 GB em 3 anos.
4. **Índices**: em produção, os GIN de `metrics` e `dimensions` e o `campaign_ix` têm **0 scans** e a pkey
   também (recibo :33) — remover os GIN é candidato direto (proposta, não aplicada). Para `as_of` basta um
   btree único `(chave lógica, disponivel_em desc)`.
5. **Partição mensal**: +3,5% de espaço, snapshot de um dia 2,3–3× mais rápido, `as_of` pontual igual no
   p50, retenção por `DROP PARTITION`. Ligar quando a tabela passar de ~10 GB (≈ ×10 no desenho v21
   real; não antes de ×100 no recomendado). Desenhar já com a chave de partição na PK.
6. **Retenção + rollup**: bruto quente 13 meses; partições velhas em Parquet zstd; rollup diário largo
   (~286 B por entidade-dia) para sempre. Vertical ×100 horária, 3 anos: 1,9 TB (v21 real) → 109 GB
   (dedup por linha) → 48 GB (linha em lote) → **30 GB** (recomendada).
7. **Termos 1×/dia** antes de qualquer outra otimização: 95% do volume lido hoje e 12 → 2 operações/dia por conta.
8. **Não otimizar ingestão**: ≥ 48 mil linhas/s por conexão no p50 mesmo com a máquina disputada; a vertical
   completa ×1000 a 10 min lê ~18,9 M linhas/dia ≈ 220 linhas/s em média.

## 7. Quotas e chamadas

Limites com fonte (`quotas.py`, `quotas.LIMITES`):

| Fonte | Limite | Valor | Estado | Evidência |
|---|---|---:|---|---|
| Google Ads | operações/dia por developer token, Basic | 15.000 | documentado no repo com fonte oficial citada | J:docs/growth-engine/matriz-api/comum.md:174 |
| Google Ads | idem, Explorer em produção | 2.880 | idem | :173 |
| Google Ads | Standard | – | não confirmado | :175 |
| Google Ads | **nível do token da VOLC** | – | **não confirmado** (não está no repo) | — |
| Google Ads | Search/SearchStream | 1 operação por requisição; páginas com token válido não contam | documentado | :179-181 |
| Google Ads | resposta gRPC | 64 MB | documentado | :189 |
| Google Ads | `page_size` | removido da API; canônicos usam searchStream | observado no repo | J:backend/app/trafego/sincronizador.py:594-599 |
| Google Ads | QPS | token bucket por CID e por token, não publicado | documentado | :197-198 |
| JoinAds | rate limit / paginação | – | não confirmado | não encontrado no repo |
| JoinAds | `limit` de top-url/top-country | 250 | parâmetro do coletor | J:n8n/gerar_flows_joinads_v2.py:234,237 |
| GTM | lote no navegador / corpo no servidor | 20 eventos ou 10 s / 64 KB | observado no repo | MS:measurement/gtm/volc-sensor-v3.html:31-33 |

A quota é **por developer token**, compartilhada com tudo que usa o mesmo token (MCP, scripts,
sincronizador; "a quota do Google Ads é por credencial", J:backend/app/trafego/sincronizador.py:1092-1094).
Os números do modelo são **piso**: sem retries que chegam ao serviço, sem consultas ad hoc. Com as
consultas reais do coletor v21 (R1 F7), a agenda atual consome 92 operações/dia por conta + 26 fixas:
**162 contas** no Basic e **31** no Explorer (se o token for Explorer, 1 conta já usa 4% do teto e o D0 a 15 min cabe em no
máximo 6 contas).
JoinAds: 145 chamadas/dia por conta hoje (premissa de 9 endpoints no intraday), 1.360 a 10 min;
sem limite conhecido, qualquer cadência abaixo de 2 h é risco não quantificado.

## 8. Limitações

- Bytes vêm de dados sintéticos; a réplica v21 e o `dil_obs_0001` seguem DDLs reais, mas não o conteúdo
  real. Só a linha da v21 (1.140 B) é medida em produção. Compressão do payload real será pior.
- A redundância de termos medida (89,4%) não é de regime (H5, §3); a de regime (97,1%) é modelada.
- λ, fração mutável e p de revisão são premissas calibradas por um agregado D30 de uma conta e pelo
  recibo de produção; a sensibilidade (`MODELO.md` §5) mostra que o acumulado de 3 anos da política
  recomendada varia de 26,5 a 33,8 GB (−12% / +12%) com λ ×0,25–4 e p ×0,25–3, porque rollup e payload
  dominam — mas a contagem de observações varia 1,7×.
- JoinAds: consultas por execução intraday (9) é premissa; endpoints reais são 10 (J:docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md:33-42).
- GTM: bytes por evento (600 B) são premissa; `raw_events` não foi medido.
- Crescimento modelado como "mais contas iguais"; contas maiores (mais campanhas) aumentam linhas
  mas não operações.
