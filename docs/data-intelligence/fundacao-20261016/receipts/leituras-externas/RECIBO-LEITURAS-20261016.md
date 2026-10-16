# Recibo — leituras externas read-only (integrador, 2026-10-16 ~12:30 UTC)

Alvo: Postgres oficial `database.agenciavolc.com.br` (container `supabase-db`), via SSH com chave dedicada.
Trava: `PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=20000'`; primeira consulta
confirmou `default_transaction_read_only = on`. Nenhuma escrita, nenhum segredo lido ou impresso
(nenhum `.env` aberto). Consultas exatas nos `.sql` desta pasta. Saídas brutas ficaram no scratchpad da
sessão; aqui só agregados. Valores monetários absolutos omitidos de propósito (só razões).

Não executadas: L6 (GTM API), L7/L8 (n8n API) e L13 (hash da Edge Function) — exigem credencial de API
que esta frente não lê; ficam como pendência de leitura.

## Resultados

| Leitura | Resultado | Implicação |
|---|---|---|
| L1 catálogo | Aplicados ao mesmo tempo: v21 (`google_ads_observation`, `google_ads_raw_batch`, `google_ads_collection_run`, view `google_ads_collection_health`, `google_ads_campaign_day_latest`), v12/v17 (`trafego_coleta_execucao`, `google_ads_campanha_dia`, `google_ads_fato_granular`, `google_ads_mudanca`, `google_ads_estado`), JoinAds v2 (`joinads_collection_run`, `joinads_raw_batch`, `joinads_observation`, view `joinads_observation_latest`) e legados (`joinads_metrics`, `gam_metrics`, `daily_campaign_metrics`, `raw_events`, `fact_page_daily`, `fact_funnel_daily`). `economia.*`/`receita_observacao`/`campanha_dia` não existem. | Fonte append-only **existe em produção** para Google Ads (v21) e JoinAds (v2), apesar de o código só estar em wip. Duas gerações de ledger Google coexistem (decisão de autoridade pendente). |
| L12 ledger | `supabase_migrations.schema_migrations` ausente; `volc_ops.migracao_evento` existe com 1 linha (v27_01_agente_bia). | Não há registro de quando v21/JoinAds v2 foram aplicadas. |
| L2 gatilhos | Append-only ativos: `google_ads_raw_batch_append_only`, `google_ads_observation_append_only`, `joinads_raw_batch_append_only`, `joinads_observation_append_only`, `joinads_raw_batch_hash`, `joinads_collection_run_guard`. Legados ativos: `trg_joinads_sync_daily` (joinads_metrics→daily_campaign_metrics), `sync_revenue_to_daily_metrics` (gam_metrics→daily), 4 gatilhos de cálculo em `daily_campaign_metrics`. | R5 (gatilho legado sobrescreve) segue vivo; append-only dos canônicos confirmado por gatilho. |
| L3 índice | `raw_events_dedup UNIQUE (sid, pid, event_name, ts_sec)` existe. | R4 confirmado (colapso por segundo); dimensionamento não feito. |
| L5 / H1 | JoinAds v2, 08–16/10: receita do endpoint `key_value_campaign_adunit` com `custom_value` numérico ≥ 10 dígitos = **97–100% do earnings de domínio todos os dias, inclusive 15/10 (97%) e 16/10 (100%)**. Todas as linhas kv de 13–16/10 têm valor numérico. | **H1 refutada**: a ponte custo×receita campanha × dia via JoinAds **não** quebrou com o GTM v35. A key-value numérica chega à JoinAds por um caminho que o filtro do wrapper não anula (mecanismo não identificado sem L6). |
| L4 sensor | `volc_sensor_ready`, 15–16/10: 28 sessões `paid=1`, **todas com `utm.source` e nenhuma com `utm.campaign`**; chaves de `utm` em 3 dias: paid 53, source 29, medium 29, term 28, campaign 1. | Confirma em produção o efeito do filtro de PII do Sensor v3 (§2.4 do inventário): `raw_events` perde o `campaign.id` numérico. Navegação/funil do sensor **não junta com campanha** hoje; só a JoinAds carrega a campanha. |
| L9 saúde | `google_ads_collection_health`: d0, d1 e terms-keywords concluídos em 16/10 (terms com 3 falhas/24 h). `google_ads_collection_run`: 29 completed, 3 failed, **3 presos em `running` desde 15/10 11:48**. JoinAds v2: 14 runs (v2 partial 1, v3 2, v4 11), último 16/10 08:15. | Coletores canônicos vivos; runs órfãos em `running` sem reaper (insumo para thread G). |
| L10 maturação | `google_ads_observation` campaign_day: 15/10 = 80 leituras, 14 valores distintos de `cost_micros`, 16 runs; 16/10 = 20 leituras/5 valores/4 runs; 14/10 = 10/2/2. Grãos: campaign_day 110, keyword_day 140, search_term_day 23.891. | Existe curva real de maturação intradiária de custo (pequena) — insumo real para replay `as_of` (thread D) e Stat Lab. |
| L11 zero | 88 de 110 observações campaign_day têm `cost_micros = 0` **e** `impressions = 0`. | Coerente com R3 (zero sintetizado para campanha sem linha de métrica). O dado não distingue "zero confirmado" de "sem linha"; o contrato deve tratar como `missing`/`zero_confirmed` só com prova (status da campanha). |

## Segunda rodada (premissas da thread B, `lb.sql`)

| Leitura | Resultado | Implicação |
|---|---|---|
| (a) p(mudou) por hora, D0 canônico, 7 dias | 5 campanhas × 1 leitura/h; `p_mudou` = 0,20 em toda hora 06–23 (0,10 às 11 h e 14 h, que têm leitura dupla D0+D-1) | Só 1 das 5 campanhas muda por hora; ~80% das leituras D0 repetem a anterior (B previu 75,6%). |
| (b) redundância de termos, 7 dias | 23.891 lidas, 2.525 distintas (observation_key, metrics) = **89,4% repetição** | Confirma a ordem de grandeza do modelo B (95,7% previsto); sustenta termos 1×/dia + dedup. |
| (d) bytes/linha reais | `google_ads_observation` 1.140 B (24.141 linhas); `google_ads_raw_batch` 1.689 B; `joinads_observation` 1.082 B; `joinads_raw_batch` 1.586 B; `raw_events` 285 linhas vivas | Linha real v21 > réplica B (851 B): GIN extras pesam. |
| (d) uso de índices | `google_ads_obs_metrics_gin` (0,7 MB), `google_ads_obs_dimensions_gin` (0,4 MB), `google_ads_obs_campaign_ix`, pkey: **0 scans**; `google_ads_obs_unique` 3; `joinads_observation_pkey` 1.286 | GIN de `metrics` e `dimensions` candidatos a remoção (proposta, não aplicada). |
| (c), (e) | não executadas nesta rodada (D-1 não é distinguível por `grain`; precisa de join com `google_ads_collection_run.collector`) | pendente |

## Ação negada (registro honesto)

A exportação de um snapshot read-only sanitizado (campaign_day v21, runs, subconjunto JoinAds v2) para
`experiments/data-intelligence-lab/artifacts/` (fora do Git) foi **bloqueada pelo classificador de
permissões da sessão (manipulação de dados)**. Não houve tentativa de contorno. Consequência: o replay
`as_of` desta missão fica em sintético + fixtures no formato real; "testado em replay com dado real"
exige autorização explícita do operador (item na lista de autorizações).
