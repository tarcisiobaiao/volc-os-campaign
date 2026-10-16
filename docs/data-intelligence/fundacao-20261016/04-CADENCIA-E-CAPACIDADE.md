# 04 — Cadência e capacidade (frente B)

Estado: modelo **construído e testado hermeticamente** (43 testes de capacidade + 17 do coletor);
bytes **medidos** num PostgreSQL 16 descartável com dados **sintéticos**; contagens de linhas e perfil
horário **calibrados com dado real versionado no repositório** (recibos de 15/10). Nada aqui foi
lido de produção. Abreviações de evidência como em `05-ARQUITETURA-COLETORES.md` (J, M, MS, P, EA).

Artefatos (gerados, não editar à mão):

- `benchmarks/capacidade/pg_medicoes.json` — medição PG (script `fundacao_capacidade_pg.py`);
- `benchmarks/capacidade/horas_campanha_d30.json` — perfil horário real (script `fundacao_capacidade_horas.py`);
- `benchmarks/capacidade/modelo.json` + `MODELO.md` — grade completa do modelo com manifesto
  (seed `20261016`, versões, sha256 de código/entradas/resultado; script `fundacao_capacidade_modelo.py`).

## 1. Os oito números

| # | Número | Fonte |
|---|---|---|
| 1 | **95,7%** das linhas que o coletor de termos lê por dia são repetição (13.368 lidas → 579 distintas); D0 de campanha: 75,6% | modelo calibrado (`MODELO.md` §2); 2.242 linhas/run = J:docs/audits/GOOGLE-ADS-COLETA-CANONICA-2026-10-15.md:93-100 |
| 2 | A réplica do schema v21 ocupa **851 B por linha lida** (630 heap + 220 índices); a mesma linha tipada em colunas ocupa **286 B** (3,0×) | `pg_medicoes.json`, 1e6 linhas |
| 3 | Por valor de métrica: largo tipado **36 B**, largo JSONB 64 B, v21 106 B, longo tipado **258 B**, longo com texto 348 B | idem |
| 4 | Payload GAQL de campanha (448 B de JSON): **718 B** gravado linha a linha (abaixo do limiar do TOAST, não comprime) × **75 B/linha** dentro de um lote jsonb de 200 linhas (pglz; termos: 1.109 × 172 B, lz4 130 B) | idem, 20.000 linhas |
| 5 | Hoje (1 conta, agenda documentada): **13,7 MB/dia** no desenho v21 → 5,3 GB em 13 meses, 14,6 GB em 3 anos; com a política recomendada **0,53 MB/dia** → 0,20 GB / 0,28 GB | `MODELO.md` §3 |
| 6 | A **×100, vertical completa, horária 24 h**: v21 1,38 GB/dia → **548 GB em 13 m e 1,5 TB em 3 a**; recomendada 0,07 GB/dia → **26 GB e 34 GB** | `MODELO.md` §4 |
| 7 | Quota Google Ads: agenda atual = **32 operações/dia por conta** → cabem **468 contas** no nível Basic (15.000/dia); com D0 a cada 10 min, 158/conta → **94 contas** | quotas documentadas em J:docs/growth-engine/matriz-api/comum.md:173-181 |
| 8 | `as_of` por chave: p50 **0,027 ms** (1e6) e **0,27 ms** (1e7); ingestão de lote de 1.000 linhas com commit: p50 **5–6,5 ms** (≈150–190 mil linhas/s) em 1e5–1e7 | `pg_medicoes.json` |

Leitura: **o problema de volume do VOLC não é o banco, é regravar o que não mudou.** A ingestão
tem folga de três ordens de grandeza; o armazenamento cresce 20–40× mais que o necessário porque
cada execução regrava a janela inteira (v21 tem `UNIQUE (run_id, observation_key)`,
J:supabase/migrations/v21_01_google_ads_coleta_canonica.sql:130) em linhas largas de texto+JSONB com
quatro índices secundários, dois deles GIN.

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
| Google Ads campanha D0 | `7 6-23 * * *` (confirmado, J:P/collector-inventory.json:109) | **manter horária 06–23**; ad group D0 na mesma agenda | p(mudou) ≈ 1 por hora na campanha ativa; ninguém decide em < 1 h; cobre 92–95% da entrega antes de 23:07 (§4) | 18 operações, 90 linhas lidas, 22 distintas | estender a 24 h quando existir ator noturno (alerta com plantão ou automação aprovada) ou se o teste do §4 mostrar noite > limiar |
| Google Ads campanha D-1 | `17 6,14 * * *` (confirmado, :134) | **manter** | 2ª passada absorve conversão atrasada (J:P/canonical-collection-plan.json:19) | 2 operações | 3ª passada (D-2) se o teste de atraso (handoff) mostrar revisão > 5% após 14h |
| Google Ads termos + keywords | `23 */4 * * *`, janela D-7..D-1 (confirmado) | **1×/dia** (ex.: `23 7 * * *`) para D-7..D-1; se termos virarem insumo intraday, um job **separado** só de D0 | janela é toda de dias fechados: 6 leituras/dia de 7 dias = 42 leituras de cada termo-dia; 95,7% redundante; 13.452 → 2.242 linhas lidas/dia | 12 → 2 operações; 13,4 mil → 2,2 mil linhas | voltar a 4 h só com consumidor intraday real; o próprio plano pede "reduzir após revisão medida" (:20) — esta é a revisão de volume (quota é irrelevante a 1 conta) |
| Ad group / anúncio D-1; hora, dispositivo, geo D-1 | não coletado (J:docs/audits/GOOGLE-ADS-COLETA-CANONICA-2026-10-15.md:11) | **1×/dia** às 06:37 (hora/dispositivo/geo) e junto do D-1 (grupo/anúncio) | plano canônico: "D-1 daily, hourly dimension once daily" (J:P/canonical-collection-plan.json:25); hora como segmento intraday é desperdício (J:P/coverage-matrix.json:220-229) | +25 operações na vertical completa (57 total) | — |
| JoinAds intraday v2 | `15 6-22/2 * * *` (confirmado, J:n8n/joinads_v2_intraday.json:10) | **manter 2 h** | receita do parceiro é sinal lento e pequeno (US$ 0,32–1,31/dia, J:docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md:91-97); frescor do parceiro não documentado | 81 chamadas (premissa 9 endpoints × 9 execuções) | 1 h só se o frescor medido do parceiro for < 1 h |
| JoinAds fechado | `20 6 * * *`, D-7..D-1 (confirmado) | **manter** | restatement de receita; repetição 58101 não duplicou (idempotência determinística) | 64 chamadas | estender janela se houver revisão após D-7 |
| Goal health / conversion health / políticas | **não existe coletor** (J:P/coverage-matrix.json:196,205); missão: 30–60 min (não confirmado) | **diário + sob demanda antes de revisão**, e **60 min só para contas com gasto ativo** e só `conversion_action.status` + resumo de política | o plano canônico pede "daily plus on-demand" (J:P/canonical-collection-plan.json:21); 60 min custa 24 operações/conta: 2.400 a ×100 (16% do Basic) | 1 → 24 operações | 30 min só em modo incidente |
| Modo incidente | não existe; missão: 10–15 min temporário | **10 min no D0 da conta afetada, por no máximo 6 h, disparado por regra** | 10 min = 5 operações/h a mais que a horária por conta; 6 h ≈ 30 operações extras; teto: (15.000 − uso base)/30 incidentes de 6 h por dia | +5 operações/h | desligar automaticamente no fim da janela |
| GTM (sensor v3) | evento; lote **10 s ou 20 eventos** (confirmado, MS:measurement/gtm/volc-sensor-v3.html:31-32; servidor MAX_BATCH 20 e 64 KB, MS:supabase/functions/volc-ingest/index.ts:6-7) | **manter** | não há cadência: o navegador empurra; volume atual 115 eventos em ~30 dias (J:EA/schema-inventory.json:116) | ~4 eventos/dia hoje; 218/dia se cada clique pago virar sessão de 8 eventos | só se o corpo de 64 KB estourar (não ocorre com 20 eventos) |

**Quanto custa encurtar a cadência intraday** (escala atual, `MODELO.md` §3 e `modelo.json`):

| Cadência D0/JoinAds intraday | Ops Google Ads/dia/conta | Contas no Basic | Versões distintas por campanha-dia (D0) | Redundância D0 |
|---|---:|---:|---:|---:|
| atual (06–23 h, JoinAds 2 h) | 32 | 468 | 4,4 | 75,6% |
| horária 24 h | 38 | 394 | 5,5 | 77,1% |
| 15 min | 110 | 136 | 17,3 | 82,0% |
| 10 min | 158 | 94 | 23,9 | 83,4% |

A cadência de 10 min produz ~115 versões/dia da campanha ativa (vs ~18 na horária): é dado novo de
verdade, mas é a mesma curva acumulada amostrada mais fino. Ela só vale se uma decisão de 10 min
existir — hoje não existe. Com termos 1×/dia a conta cai para 22 operações/dia (681 contas no Basic).

## 4. Janela D0 06–23 deve cobrir 24 h?

**O que dá para afirmar** (dado real, `horas_campanha_d30.json`, D30 agregado por hora da campanha
24278665189; "ad_schedule: none configured; observed delivery spans hours 0-23",
J:P/receipts/d-live-campaign-audit.json:1034):

| Fatia do dia | Impressões | Cliques | Custo | Conversões (plataforma) |
|---|---:|---:|---:|---:|
| 00:00–05:59 | 5,0% | 6,5% | 6,1% | 6,5% |
| hora 23 | 1,3% | 2,1% | 1,7% | 0,4% |
| fora da última leitura do D0 (00–06 + 23:07–23:59, aprox.) | 6,1% | 8,3% | **7,6%** | 6,9% |

1. **Não há perda de dado**: a janela D0 é acumulada do dia; a execução das 06:07 já vê a
   madrugada, e o trecho 23:07–23:59 aparece no D-1 das 06:17.
2. **Há perda de frescor**: o maior buraco sem leitura é de 7 h (23:07 → 06:07), que concentra ~7,6% do
   gasto diário (≈ R$ 1,76/dia ao gasto atual de R$ 23/dia). Um incidente noturno é visto até 7 h depois.
3. **Custo de cobrir 24 h**: +6 operações/dia/conta (32 → 38; Basic de 468 → 394 contas) e +6 leituras
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

Ambiente: PostgreSQL 16.11 (Homebrew, arm64), cluster temporário em
`experiments/data-intelligence-lab/artifacts/fundacao_capacidade_pg/` (gitignored), socket unix
próprio em `/private/tmp/pgfb-*` (caminho curto exigido pelo limite de 104 caracteres do socket),
`listen_addresses=''`, porta 54931, `fsync=on`, `synchronous_commit=on`, `wal_level=minimal`,
`shared_buffers=256MB`, `autovacuum=off`, TOAST `pglz`. Duração 288 s. **Pico do diretório do
cluster 4,08 GiB** (levemente acima do teto combinado de ~4 GB; a guarda checava o previsto, não o
WAL); disco livre nunca abaixo de ~14 GiB; **cluster e socket apagados no fim** (`cluster_apagado: true`).
Dados sintéticos determinísticos (sem `random()`): 10 contas × N entidades × 90 dias, 10% das chaves
com 2ª versão.

DDL de medição (**aproximação própria**: o SQL candidato do worker A não existia quando a medição
rodou) — cinco variantes da tabela de observação:

| Variante | Desenho | Índices |
|---|---|---|
| `longo` | 1 linha por métrica; ids `bigint`/`smallint`, `valor bigint`, `payload_sha256 bytea` | PK `id`; único `(conta, nível, entidade, segmento, dia, métrica, disponivel_em desc)` = índice `as_of`; BRIN `disponivel_em` |
| `texto` | igual, ids e códigos em `text`, valor `numeric`, sha em hex | idem |
| `largo` | 1 linha por entidade×leitura, 8 métricas `bigint` (2 nulas) | PK; único `as_of` sem métrica; BRIN |
| `jsonb` | igual ao largo, métricas num `jsonb` | idem |
| `v21` | **réplica** de `google_ads_observation` (J:supabase/migrations/v21_01_google_ads_coleta_canonica.sql:94-145): `uuid`, ids `text`, `dimensions/metrics/attributes jsonb` | PK uuid; `UNIQUE (run_id, observation_key)`; 2 btree compostos; 2 GIN `jsonb_path_ops` |

### 5.1 Tamanho (1e6 linhas; 1e5 e 1e7 iguais a ±1% por linha)

| Variante | heap B/linha | índices B/linha | total B/linha | B por valor de métrica |
|---|---:|---:|---:|---:|
| longo | 167,3 | 90,3 | 257,6 | 257,6 |
| longo particionado (4 meses) | 167,3 | 99,6 | 267,0 | 267,0 |
| texto | 230,4 | 118,0 | 348,4 | 348,4 |
| largo | 204,9 | 81,5 | 286,4 | 35,8 |
| jsonb | 431,3 | 81,5 | 512,8 | 64,1 |
| v21 (réplica) | 630,4 | 220,3 | 850,7 | 106,3 |

Índices da réplica v21 em 1e6: PK uuid 31,6 MB, único (run, key) 67,9 MB, 2 btree 66,5 MB, 2 GIN 54,4 MB.
Partição: +3,5% no total em 1e7 (a PK passa a ser `(id, dia)`: 315 vs 225 MB).

Payload bruto (20.000 linhas GAQL sintéticas, tabela `sha256 bytea pk, fonte, primeiro_visto_em, payload jsonb`):

| Tipo | JSON B/linha | jsonb por linha | jsonb em lote de 200 (pglz) | idem (lz4) |
|---|---:|---:|---:|---:|
| campanha | 448 | 718 | 75 | 75 |
| termo de busca | 782 | 1.109 | 172 | 130 |

O lote sintético repete strings mais que o real (nomes de campanha); a razão real de compressão
deve ser menor — por isso o modelo usa a medição como está e o handoff pede a medição real.

### 5.2 Latência

| Medida (sem partição → com partição) | 1e5 | 1e6 | 1e7 |
|---|---:|---:|---:|
| `as_of` por chave, p50 (ms) | 0,022 → 0,032 | 0,027 → 0,038 | 0,274 → 0,401 |
| `as_of` por chave, p99 (ms) | 0,062 → 0,308 | 0,339 → 0,452 | 2,31 → 3,39 |
| snapshot conta×dia (`DISTINCT ON`), p50 (ms) | 0,23 → 0,11 (100 chaves) | 2,13 → 0,71 (1.010) | 23,5 → 8,6 (10.100) |
| ingestão lote 1.000 + commit, p50 (ms) — cru / com checagem de dedup | 8,3 / 7,2 | 5,3 / 6,8 | 6,5 / 6,5 |
| ingestão lote 5.000 + commit, p50 (ms) — cru / dedup | 42 / 41 | 31 / 33 | 41 / 34 |
| `as_of` na réplica v21 (via `campaign_ix`), p50 (ms) | 0,023 | 0,145 | – |

A ingestão usa o formato da RPC real (lote `jsonb` → `jsonb_to_recordset`, `on conflict do nothing`);
a checagem de dedup (`NOT EXISTS` contra a última versão da chave) custa de 0 a 25% no p50. Mede o
servidor, sem rede nem serialização do cliente. Índices foram construídos **depois** da carga
(compactos); inserção incremental com PK uuid aleatória deixaria os índices ~30% maiores (não medido).

### 5.3 DuckDB / Polars (só leitura analítica de snapshot)

Snapshot `as_of` completo (última versão ≤ corte para TODAS as chaves):

| Linhas | PostgreSQL (`DISTINCT ON`, índice) | DuckDB (Parquet) | Polars (Parquet) | resultados iguais |
|---:|---:|---:|---:|---|
| 1e5 | 0,049 s | 0,008 s | 0,010 s | sim |
| 1e6 | 0,534 s | 0,049 s | 0,074 s | sim |
| 1e7 | não medido | 0,518 s | 1,703 s | sim |

DuckDB é ~10× mais rápido que o Postgres para reconstruir um snapshot inteiro; para o replay v0
(≤ 13 mil observações por snapshot, `results/bench/BENCH-RESULTS.md`) isso é irrelevante. Uso
recomendado: exportar partições frias para Parquet e ler com DuckDB em replays históricos grandes,
não trocar o banco operacional. (O tamanho do Parquet sintético — < 1 B/linha — não é representativo:
as chaves sequenciais comprimem demais.)

## 6. Recomendações (com números)

1. **Dedup de observação é a alavanca principal** (−93% das linhas de observação na vertical
   completa ×100 horária: 1,46 M → 103 mil/dia). Gravar só a versão que mudou (chave lógica + valor),
   com o recibo do run registrando "li N, igual M" para provar cobertura (o run prova que a leitura
   aconteceu; a ausência de linha nova não é ausência de leitura).
2. **Payload bruto: hash por linha, linhas novas gravadas juntas num lote jsonb** ("linha em lote").
   Dedup por lote inteiro quase nunca acontece em janela grande (um termo que muda torna o lote
   novo: no coletor de termos 100% dos lotes continuam "novos"; somando todos os jobs da vertical ×100 horária, 82%); dedup linha a linha sem lote paga 718–1.109 B
   por linha. Linha-em-lote: 75–172 B + ~56 B de índice por linha. Na vertical ×100 horária:
   payload sem dedup 0,23 GB/dia vs 0,026 GB/dia em linha-em-lote (−89%).
3. **Colunas tipadas, não JSONB, para as métricas da observação**: largo tipado 36 B/valor vs JSONB
   64 B e v21 106 B. JSONB fica para o bruto (comprimido em lote) e atributos raros. Formato **longo**
   (uma linha por métrica) custa **7,2×** o largo por valor (258 vs 36 B): só usar se o contrato
   exigir estado por métrica que não caiba em `NULL` + bitmask de estado — decisão a alinhar com o
   contrato da frente A.
4. **Índices**: na réplica v21 os índices são 26% do total; os dois GIN `jsonb_path_ops` (54 B/linha)
   só servem consultas de contenção `@>` — inúteis para `as_of` e faixa numérica. Remover o GIN de
   `metrics` é candidato direto, após confirmar `idx_scan = 0` (consulta no handoff). Para `as_of`
   basta um btree único `(chave lógica, disponivel_em desc)` — que também é a trava de
   "duas versões no mesmo instante".
5. **Partição mensal**: +3,5% de espaço, `as_of` pontual +46% no p50 (0,27 → 0,40 ms em 1e7), snapshot de um
   dia 2,7× mais rápido (23,5 → 8,6 ms) e retenção por `DROP PARTITION` sem bloat. Ligar quando a tabela
   passar de ~10 GB ou quando a retenção começar (≈ ×10 no desenho atual; nunca no desenho
   recomendado antes de ×100). Desenhar já com a chave de partição na PK.
6. **Retenção + rollup**: bruto quente 13 meses; partições mais velhas exportadas para Parquet zstd
   (frio) e removidas; rollup diário (1 linha larga por entidade-dia, ~286 B) para sempre. Na vertical
   ×100 horária, 3 anos: 1,5 TB (v21) → 137 GB (dedup por linha) → 58 GB (linha em lote) → **34 GB**
   (recomendada, com rollup de 12 MB/dia).
7. **Termos 1×/dia** antes de qualquer outra otimização: é 95% do volume lido hoje.
8. **Não otimizar ingestão**: 150–190 mil linhas/s por conexão; a vertical completa ×1000 a 10 min
   lê ~18,9 M linhas/dia ≈ 220 linhas/s em média.

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
Os números do modelo são **piso**: sem retries que chegam ao serviço, sem consultas ad hoc.
JoinAds: 145 chamadas/dia por conta hoje (premissa de 9 endpoints no intraday), 1.360 a 10 min;
sem limite conhecido, qualquer cadência abaixo de 2 h é risco não quantificado.

## 8. Limitações

- Bytes vêm de dados sintéticos com DDL aproximado; a réplica v21 segue o DDL real mas não o
  conteúdo real de `dimensions/attributes`. Compressão do payload real será pior.
- λ, fração mutável e p de revisão são premissas calibradas por um único agregado D30 de uma conta;
  a sensibilidade (`MODELO.md` §5) mostra que GB/dia da política recomendada varia só ±5% em
  λ ×0,25–4 e p ×0,25–3, porque o rollup e o payload dominam — mas a contagem de observações varia 2,5×.
- JoinAds: consultas por execução intraday (9) é premissa; endpoints reais são 10 (J:docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md:33-42).
- GTM: bytes por evento (600 B) são premissa; `raw_events` não foi medido.
- Crescimento modelado como "mais contas iguais"; contas maiores (mais campanhas) aumentam linhas
  mas não operações.
