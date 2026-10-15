# Auditoria de dados — economia e estatística (Pesquisador B, 14/10/2026)

Fonte: só código, SQL e migrations do checkout `volc-os-campaign-qg-real-20261007`
(sem acesso a banco, Google ou n8n vivo). "Existe no repo" ≠ "aplicado em
produção": quando o próprio repo declara o estado de produção, cito o documento.
Caminhos relativos à raiz do checkout.

## 1. Snapshots as-of de receita e de custo

**Resposta curta: não há as-of de receita nem de custo. Há só o último valor,
sobrescrito, com um carimbo do último escritor.** A curva de maturação não é
reconstruível a partir do banco.

Receita
- `joinads_metrics`: chave única `(date, utm_campaign_value, joinads_domain)`
  (`src/sql/joinads/01_joinads_metrics.sql:44-45`); o n8n grava por PostgREST
  com `Prefer: resolution=merge-duplicates` (`n8n/gerar_flows_joinads.py:450-458`)
  = UPSERT que substitui a linha. Intraday roda 06/12/18/23 com janela "hoje"
  (`n8n/gerar_flows_joinads.py:580-589`, cron `0 6,12,18,23`); o D-1 relê 3 dias "para reabsorver
  revisão retroativa da Join" (`:590-600`, comentário em `:29-31`). Cada execução
  apaga o valor anterior: o "quanto havia às 12h" deixa de existir às 18h.
- Carimbos: `created_at`/`updated_at` são `timestamp` **sem fuso**
  (`01_joinads_metrics.sql:39-40`) e `updated_at` é reescrito a cada upsert
  (`:76`, `:101`). Só dizem quando foi a ÚLTIMA escrita.
- `gam_metrics`: mesmo padrão (colunas em `docs/volc-os-graph/supabase-snapshot-2026-08-22.json`,
  `updated_at` único); a v17_04 só usa `max(updated_at)` como "receita_atualizada_em"
  (`supabase/migrations/v17_04_arbitragem_reconciliada.sql:60-62, 118`) — informativo, não é curva.
- O trigger de fan-out copia `revenue` para `daily_campaign_metrics` sobrescrevendo
  (`01_joinads_metrics.sql:94-103`): a tabela que o painel lê também é "último valor".
- Câmbio: o legado `update_all_revenue_conversions()` recalcula **todo o histórico**
  com a cotação ATUAL quando `system_settings.dollar_exchange_rate` muda
  (`src/sql/add_revenue_converted_column.sql:33-60, 63-80`). Mesmo se houvesse
  snapshot da receita em moeda original, o BRL histórico seria reescrito. Produção,
  segundo o repo, usa `calculate_revenue_converted_by_date` (cotação da data)
  (`docs/architecture/GADS-FATOS-GRANULARES-v17.md:82-86`) — função **sem DDL no repo**
  (só a chamada em `01_joinads_metrics.sql:141`).

Custo
- `google_ads_campanha_dia` e `google_ads_fato_granular` têm `colhida_em`
  (`v12_04_gads_fato_canonico_dia.sql:281`; `v17_01_gads_fatos_granulares.sql:101`),
  mas o UPSERT substitui métricas quando a precedência é maior ou a leitura é mais
  nova (`v17_01:429-446`; `v12_04:849-888`). D0 é sobrescrito pelo D-1/backfill.
- O ledger `trafego_coleta_execucao` guarda o recibo de cada execução, mas só o
  **hash** do payload (`v12_04:89, 134`; `v17_01:504-527`), não os números.
  Prova que houve leitura; não permite reconstruir o valor lido.
- O laboratório tem disciplina as-of correta em memória (`as_of_date` < dia de
  `lido_em`, janela fechada antes da leitura:
  `volc_ads/inteligencia_decisao/normalizacao_google_ads.py:257-276, 805-840`),
  mas sobre linhas sintéticas (`volc_ads/inteligencia_decisao/dados/`).
- A tabela as-of foi **desenhada e não existe**: `trafego_fotografia`,
  `trafego_previsao`, `trafego_realizado` (`docs/architecture/SPEC-ORAKUL-DECISION-INTELLIGENCE-V1.md:139-141`);
  `grep` em `supabase/`, `src/sql/`, `backend/`, `volc_ads/` não as encontra.

Consequência: B19/B20 (fator de maturação, "65% em 1h / 90% em 3h / 95%") não
têm parâmetro operacional possível hoje. É impedimento de dados, não de modelo.

## 2. Grão, chave de ligação, moeda e fuso

| lado | grão | chave para o custo | moeda | fuso |
|---|---|---|---|---|
| Custo Google | campanha×dia×`segments_hash` (`v12_04:259-283`); granular: hora×dispositivo×rede, URL, geo, placement, termo, keyword (grupo×critério), asset (`v17_01:55-117`, desenho em `GADS-FATOS-GRANULARES-v17.md:18-33`). **Não há anúncio×dia de custo** (só asset). | — | `currency_code` por linha, micros (`v12_04:283`) | conta (`customer.time_zone`): `fuso` só na família hora (`v17_01:66-69, 206-207`); `google_ads_campanha_dia` não guarda fuso |
| JoinAds | dia × `utm_campaign_value` × domínio (`01_joinads_metrics.sql:21-45`), via `/key-value` com `custom_key=utm_campaign` (`gerar_flows_joinads.py:393-396, 417-431`) | `utm_campaign_value = campaign_id` (`v17_04:84-86`) | `revenue` bruto + `revenue_converted` BRL (`01_joinads_metrics.sql:28-31`) | janela pedida em `America/Sao_Paulo` (`gerar_flows_joinads.py:34, 391`); fuso interno da Join não verificado |
| GAM | dia × `utm_campaign_value` (key-value) × conta GAM; roteador separa campanha Google de adset Meta (`supabase/migrations/20260910143000_gam_attribution_grain_router.sql:1-22`); `hourly_stats` por `hour_bucket` sem moeda (`v17_04:24-26, 154-169`) | só rota `GOOGLE_CAMPAIGN` (`v17_04:53-59`) | `revenue_converted` BRL | sem fuso declarado |
| AdSense | URL × dia (`adsense_metrics`: `url`, `date`; snapshot 22/08) | nenhuma junção com custo | BRL convertido | — |

- **gclid: não liga custo a receita.** O lado da receita não tem clique; gclid só
  aparece na fronteira de conversão offline/Data Manager, que monta e **não envia**
  (`backend/app/trafego/data_manager.py:1-45`; `conversion_queue` com 0 linhas e
  sem DDL no repo, `:4-25`). O contrato de URL declara `{gclid}` redundante com
  auto-tagging (`volc_ads/campanha/marcacao.py:52-57`). A ligação é **UTM/campanha-dia**.
- Grupo/anúncio na URL: o contrato envia `utm_content={adgroupid}` e
  `vc_creative={creative}` (`marcacao.py:146-161`). A JoinAds aceita
  `custom_key ∈ {utm_campaign, id_post_wp, id_post, utm_source, utm_medium, utm_content, land_uri}`
  (`gerar_flows_joinads.py:393-395`): **grupo seria ingerível** (utm_content),
  **anúncio não** (`vc_creative` não é chave aceita). Hoje só `utm_campaign` é pedido (`:396`).
- **Cotação divergente "GAM 5,50 × JoinAds 5,20": refutada para produção pelo
  próprio repo** — medida no espelho sem `system_settings`; em produção as duas
  convertem pela mesma função, 5,25 (`GADS-FATOS-GRANULARES-v17.md:82-86`). O
  defeito real é outro: câmbio **congelado** em 5,25 desde 18/02/2026 alimentando
  6 triggers (`docs/growth-engine/legado-n8n/conflitos.md:252, 261-266`) e
  **5,50/5,35 embutidos no front** (`src/utils/currencyUtils.ts:55,61,74`;
  `src/services/supabaseDataService.ts:201`; registrado em
  `docs/closure/traffic-operational-closure-v2/METRIC-CONTRACT.json:103-108`), com
  fallback 5,50 no SQL legado (`src/sql/add_revenue_converted_column.sql:16,25`).
- Fuso: a v17_04 casa custo e receita por `metric_date = date` (`v17_04:84-86`)
  sem checar que o fuso da conta é o da janela da Join. Para contas fora de
  `America/Sao_Paulo` (multi-país) a junção desloca horas de receita entre dias.
- Maturidade: `reconciliada_fonte_unica` exige janela fechada **do custo**
  (`v17_04:103-105`), mas a receita do D-1 ainda é reescrita por 3 dias
  (`gerar_flows_joinads.py:590-600`). "Reconciliada" ≠ "madura".

## 3. Logs de decisão: dá para OPE/IPS/DR?

**Não.** O ciclo v10_02 registra contexto, ação tomada, aprovação e efeito
operacional, mas não o conjunto elegível, a política como distribuição, a
**probabilidade da ação tomada**, nem a recompensa econômica.

| requisito OPE | existe? | onde |
|---|---|---|
| contexto | parcial: impressões, cliques, custo, conversões, valor de conversão, `colhida_em`, janela | `trafego_evidencia` (`v10_02_autogestao.sql:356-380`) |
| ação tomada | sim: `operacao`, `valor_atual`, `valor_proposto`, delta | `trafego_proposta` (`:497-545`, colunas `:514-518`) |
| política/versão | sim: `regra_id` versionada | `:503`; regras em `volc_ads/inteligencia_decisao/politicas.py:82-133` |
| timestamp | sim: `criada_em`, `valor_atual_lido_em`, `expira_em` | `:517, 528-535` |
| ações elegíveis (não tomadas) | **não** | — |
| probabilidade da ação | **não** — `confianca` do diagnóstico é confiança da causa, 0..1, anulável (`:463`), e `PropostaTipada.confianca` é texto (`volc_ads/inteligencia_decisao/contratos.py:46-66`) | — |
| recompensa econômica | **não**: `trafego_acompanhamento` tem impressões/cliques/custo/conversões, sem receita nem lucro (`:695-740`; `grep receita` no arquivo: 0) | — |
| decisor | humano aprova toda proposta; `NIVEIS_QUE_APLICAM_SEM_HUMANO = frozenset()` (`backend/app/trafego/gestao/application/autonomia.py:32`) | política de log humana = propensão desconhecida |

Instrumentação mínima futura: ver RELATORIO-B.md §"Instrumentação mínima futura".

## 4. O que o VOLC pode decidir pela API (e onde bandit/RTB/VW não se aplicam)

Ações tipadas existentes (`volc_ads/gestao/acoes.py`): `status` (ENABLED/PAUSED, `:196`),
`orcamento.diario` (`:287`), `lance.alvo` (tCPA/tROAS, `:450`), `lance.estrategia` (`:571`),
`negativa.keyword` (`:802`), listas de negativas (`:913, :979, :1045`),
`exclusao.placement` (`:1101`), `exclusao.ip` (`:1205`), `programacao.anuncios` (`:1380`),
`ajuste.dispositivo` (`:1558`), `ajuste.horario` (`:1587`), `recomendacao.aplicar/dispensar`
(`:1741, :1759`). REMOVED fica fora (`:30-35`). Tudo com aprovação humana
(`autonomia.py:32`; `docs/architecture/GADS-AUTONOMIA-ESTADO.md:10-20`).

Não se aplicam:
- **RTB / lance por impressão** (B25, B32 "decisão horária", B24 "degrau"): o VOLC
  não participa do leilão. Com Smart Bidding o Google define o lance por leilão; o
  VOLC só muda metas, orçamentos e estrutura, com cooldown de horas/dias
  (`politicas.py:64-66`, `cooldown_horas=24`).
- **Bandit online por clique (VW)**: a "ação" do VOLC é campanha-dia; a recompensa
  chega atrasada e reescrita (§1); dezenas de decisões por mês, não milhões.
- **Thompson por grupo para "pausar perdedores"** (B04/B13): aplicável só como
  ranqueador de propostas com recompensa bem definida (receita reconciliada no
  grão do grupo, que não existe — §2) e com aprovação humana.
- O leilão do Google não é de segundo preço puro: paga-se o mínimo para superar o
  Ad Rank do concorrente abaixo e os limiares, e "quanto maior a diferença de Ad
  Rank, maior pode ser o CPC pela certeza de ganhar" (support.google.com/google-ads/answer/6297 e /1722122).

## 5. Definições (e onde estão no código)

| conceito | definição | onde |
|---|---|---|
| custo observado | `custo_micros/1e6` na moeda da conta, NULL ≠ 0 | `v12_04:281-300`; view `v17_04:115` |
| receita observada | `revenue` bruto da fonte; `revenue_converted` em BRL (revshare descontado só no consumidor) | `01_joinads_metrics.sql:28-31` |
| receita reconciliada | receita de UMA fonte atribuída, projeto coerente, BRL, custo de janela fechada | `v17_04:88-106, 124-126` |
| receita prevista | **não existe** no código de produção (só desenho `trafego_previsao`, SPEC:140) | — |
| valor enviado para otimização | regra declarada `sem_valor`/`fixo`/`por_evento` com moeda, montada e não enviada | `backend/app/trafego/perfil_de_mensuracao.py:142-203`; `data_manager.py:1-45` |
| lucro | receita reconciliada − custo, só `reconciliada_fonte_unica` | `v17_04:128-129` |
| ROAS | receita/custo (razão) | `v17_04:130-131`; `src/utils/roasCalculations.ts:35-38` (`roasRatio`) |
| "ROAS %" legado | (receita/gasto − 1)×100 = **excedente**, não ROAS; cores ≥80 verde, ≥40 amarelo, ≥0 laranja | `roasCalculations.ts:125, 152-155` |
| ROI líquido | lucro líquido (impostos/taxas/revshare) / investimento; `null` sem regra fiscal versionada | `roasCalculations.ts:39, 100` |
| "status_roi" de Display | excedente% ≥20 LUCRATIVO, ≥0 NEUTRO, <0 PREJUÍZO; ausência vira 0 | `src/hooks/useDisplayROI.ts:71-78` |
| CPC | custo / cliques Google | `v17_04:116` |
| RPC (receita por clique) | receita reconciliada / cliques **Google** | `v17_04:132-133` |
| EPC | não definido no código (grep `\bepc\b`: 0). Se usado: receita / cliques **de saída** do afiliado — outro denominador | — |
| RPM | receita / mil **pageviews ou impressões de anúncio** do publisher (JoinAds `ecpm` por impressão de anúncio, `01_joinads_metrics.sql:33-37`) | — |

Denominadores: CPC e RPC usam clique pago; RPM usa mil impressões/pageviews do
publisher; EPC usa clique de saída. "Spread CPC × RPM" (B34) só fecha com a ponte
pageviews/clique: RPC = RPM × (pageviews monetizadas por clique)/1000.
