# 01-INVENTARIO-ATUAL — inventário e verdades iniciais (thread A-inv)

**Missão:** Fundação Data Intelligence (2026-10-16) · **Worker:** A-inv · **Escrita:** branch `lab/dil-fundacao-20261016-inv`
**Leitura:** worktree do integrador (`lab/data-foundation-20261016` @ `3b22477d`) + refs locais + checkout oficial `volc-os-campaign/` em modo leitura.
**Produção:** não acessada (nenhum Supabase, SSH, n8n, Google Ads, GTM, JoinAds, `.env*`, `~/.ssh`).
**Grafo:** `python3 scripts/atualizar_grafo_volc_os.py --check` no worktree do integrador → `current: false` ("código, SQL ou fonte operacional mudou"; `built_at_commit 6124c550`, `input_file_count 2670`). O `graphify-out/graph.json` do checkout oficial (gerado 2026-10-15 13:54 -03, 19.602 nós) foi lido só por `json.load`, sem rodar `graphify` lá; ele contém nós das migrations v21 / JoinAds v2 / `volc_ads/economia`, mas descreve o checkout sujo, não `main`.

Recibos desta thread: `receipts/inventario/01-refs-e-ids.txt` (refs, ancestralidade, contagem de IDs por ref, presença de caminhos), `02-prova-filtro-pii-utm.mjs` + `.saida.txt` (prova hermética do filtro de PII), `03-roadmap-tarefas.tsv` (tarefas, estado e linha em `main` e na wip).

## 0. Legenda

Classificação de existência (por item):

| Rótulo | Significado |
|---|---|
| `existe em main` | presente em `main` `104bb0d0` |
| `só em wip/<branch>` | presente em ref `wip/*` (linha `0f0bb287 → 043c77f5 → wip/historico-*`), ausente em `main` |
| `só em arquivo sujo` | só no working tree do checkout oficial, sem commit em ref alguma |
| `documentado sem código` | afirmado em doc/relatório/roadmap, sem código/DDL que o realize em ref alguma |
| `não encontrado` | não achado em nenhuma ref local nem no checkout sujo |

Grau de prova: **[D]** demonstrado (ref + caminho + linha, ou execução reproduzível), **[I]** inferido de código/doc, **[H]** hipótese a confirmar por leitura externa. "Afirmado por relatório" = o repositório diz que aconteceu em produção; isso não é prova de estado vivo hoje.

Abreviações de refs: `M` = `main` `104bb0d0`; `W0` = `0f0bb287` ("ativa coleta canonica shadow", 15/10 12:23); `W` = `043c77f5` (`wip/original-worktree-pre-qg-real-20261007`, 15/10 13:53); `WJ` = `192bc065` (`wip/historico-joinads-20261015`); `WM` = `918e9571` (`wip/historico-measurement-20261015`); `WF` = `4be92dfc` (`wip/historico-fontes-de-verdade-20261015`); `WD` = `992ff362` (`wip/historico-desconhecido-20261015`).

## 1. Mapa das três verdades (demonstrado)

| Fato | Prova |
|---|---|
| `main` e `W` não têm ancestral comum | `git merge-base main 043c77f5` → vazio [D] `receipts/inventario/01-refs-e-ids.txt` |
| `W0` é ancestral de `W`; `W` é ancestral de `WJ`, `WM`, `WF`, `WD` (cada `wip/historico-*` = `W` + 1 commit de preservação, 15/10 15:40) | `git merge-base --is-ancestor` [D] recibo 01 |
| Os arquivos sujos relevantes do checkout oficial são **byte a byte iguais** às preservações `wip/historico-*`: `n8n/gerar_flows_joinads_v2.py`, `joinads_v2_{d1,intraday}.json`, `joinads_v2_normalize.js`, `testes_joinads_v2.py`, `src/sql/joinads/04_rollback_*`, `supabase/migrations/20261015163704_*`, `20261015170000_*` (= `WJ`); `measurement/gtm/*`, `supabase/functions/volc-ingest/index.ts`, `20261015153301_*`, `scripts/autorizar-google.py` (= `WM`); `volc_ads/inteligencia_google/{coletor,modelo}.py` (= `WD`); `ROADMAP-VIVO.json` e `curadoria-operacional.json` (= `WF`) | `cmp` entre `git show <ref>:<p>` e o arquivo do checkout [D]; sha256 do sensor `cb018224…41e4` igual nos dois |
| Consequência | para o escopo desta missão, **"só em arquivo sujo" colapsa em "só em wip/historico-*"**: nenhum artefato de dados relevante achado existe só no working tree. O checkout tem 854 entradas em `git status --porcelain -uall` (o manifesto conta 302 por diretório) |
| `main` tem o desenho **v12_04/v17_01** (Python `volc_ads/coleta` + timers systemd não instalados + flows n8n v12 inativos); `W` tem o desenho **v21** (n8n canônico ativo, segundo relatório). Os dois desenhos de coleta Google Ads são **mutuamente ausentes**: `v12_04`, `v17_01`, `v17_04`, `v23_01`, `volc_ads/coleta/`, `deploy/gads-coleta/`, `n8n/volc_gads_campanha_dia_d*.json` só em `M`; `v21_01..03` Google, `scripts/instalar_coleta_*`, `volc_ads/economia/`, `20261015163636_*` só em `W`+ | `git cat-file -e` [D] recibo 01 (tabela "presença de caminhos-chave") |
| Colisão de numeração: em `M`, `v21_01` = `v21_01_meta_capi_sites_privilegios.sql` e `v21_02` = `v21_02_v6_rbac_privilegios.sql`; em `W`, `v21_01..03` = ledger Google Ads | `git ls-tree` [D] |

Nota de conduta: uma única execução de `git status --porcelain` no checkout oficial foi feita **sem** `--no-optional-locks` (pode ter atualizado o cache de stat do índice; nenhum conteúdo foi alterado). As leituras seguintes usaram `git --no-optional-locks`.

## 2. Verdades iniciais — vereditos

Uma linha por fato. "Classe" = onde existe. Estado de produção é sempre **[H]** até leitura externa (seção 8).

### 2.1 Google Ads

| # | Fato | Veredito | Classe | Prova |
|---|---|---|---|---|
| G1 | D0 workflow `Ps9yLfQkHeaAbyZZ`, cron `7 6-23 * * *` | **confirmado** (repo) | só em wip (`W0`,`W`+) | `W:docs/operations/google-ads-coleta-canonica.md:7`; `W:docs/audits/GOOGLE-ADS-COLETA-CANONICA-2026-10-15.md:51`; instalador `W:scripts/instalar_coleta_canonica_google_ads_n8n.py:261-262` (`"7 6-23 * * *" if role == "d0"`); inventário vivo lido em 15/10 13:12 `W:.claude-ads/runs/google-ads-recovery-20261015T125729-0300/collector-inventory.json` (`active: true`). 0 ocorrências em `M` [D] |
| G2 | D-1 `7yxs1aOlzWkkkSf9`, cron `17 6,14 * * *` | **confirmado** (repo) | só em wip | mesmas fontes, `…coleta-canonica.md:8`, audit `:52`, instalador `:262` [D] |
| G3 | termos/keywords `TFlmThr4930oPneE`, cron `23 */4 * * *` | **confirmado** (repo) | só em wip | `…coleta-canonica.md:9`, audit `:53`, `W:scripts/instalar_coleta_termos_keywords_n8n.py:193`; janela `LAST_7_DAYS` `:166-167` [D] |
| G4 | API v25 | **confirmado** | só em wip (instaladores) / existe em main (catálogo) | `api_version: 'v25'` em `W:scripts/instalar_coleta_canonica_google_ads_n8n.py:186,230` e `…termos_keywords_n8n.py:136,153`; audit `:57`; `M:volc_ads/google_ads_api/MATRIZ-COBERTURA-V25.md`; legado D0/D-1 também v25 `M:docs/architecture/GADS-REPORT-D0-D1-E-CONTRATO-DE-DADOS.md:22` [D] |
| G5 | Armazenamento canônico append-only desenhado | **confirmado** (desenho) / aplicação em prod **[H]** | só em wip | `W:supabase/migrations/v21_01_google_ads_coleta_canonica.sql`: `google_ads_raw_batch` `:64-92` (payload + sha256, `UNIQUE(run_id,batch_key)`), `google_ads_observation` `:94-131` (métricas `jsonb`, sem `DEFAULT 0`, `UNIQUE(run_id,observation_key)`), gatilhos `BEFORE UPDATE OR DELETE` → exceção `:147-163`, replay idempotente por hash `:211-222`, `google_ads_campaign_day_latest` `:286-293` (DISTINCT ON … `collected_at DESC`), `google_ads_collection_health` `:295-302`, RLS forçada `:304-309`; v21_02 hash no servidor `:3-21`; v21_03 finalização explícita `:21-28`. "Aplicadas no PostgreSQL 15.8 de produção" é **afirmado** em `W:docs/audits/GOOGLE-ADS-COLETA-CANONICA-2026-10-15.md:17-21` [D desenho; H prod] |
| G6 | Verticais faltantes: ad groups, ads/assets, conversion actions/goal health, change events, hora/dispositivo/geo, placements, recommendations, error workflow | **parcial** | — | **Faltam na vertical canônica v21** (audit `W:…GOOGLE-ADS-COLETA-CANONICA-2026-10-15.md:10-13`; error workflow ausente `:137-139` e `RELATORIO.md:48` "Nenhum canônico aponta para settings.errorWorkflow"; `collector-inventory.json` `canonical_with_error_workflow: 0`) [D]. **Mas o desenho existe em `main`, não agendado:** `M:supabase/migrations/v17_01_gads_fatos_granulares.sql:181-189` (partições `hora_dispositivo`, `url`, `geo`, `placement`, `termo`, `keyword`, `asset`), `:210-240` (`google_ads_mudanca` = change_event, `google_ads_estado` append-only), coletores `M:volc_ads/coleta/familias/{hora_dispositivo,geo,placement,asset,mudanca,estado}.py`, recomendações/conversion goals em `M:volc_ads/inteligencia_google/coletor.py:168,239`; agenda systemd "preparada, não instalada" `M:deploy/gads-coleta/README.md:1,5` [D]. Logo: faltam **na coleta ativa**; existem como código em outra história, sem agenda |

### 2.2 JoinAds

| # | Fato | Veredito | Classe | Prova |
|---|---|---|---|---|
| J1 | intraday `cpb6tNxt211UkAn2`, cron `15 6-22/2 * * *` | **confirmado** (repo) | só em `wip/historico-joinads` (= arquivo sujo) | `WJ:docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md:17`; gerador `WJ:n8n/gerar_flows_joinads_v2.py:319-320` (`cron="15 6-22/2 * * *"`, offset 0, lookback 0) [D]. Único arquivo com o ID; ausente em `M` e `W` |
| J2 | D-1 `jDX397ViVcRQft4A`, cron `20 6 * * *`, reprocessa D-7..D-1 | **confirmado** (repo) | só em wip | audit `:18`; gerador `:323-324` (`offset=1, lookback=6, max_days=7` ⇒ fim = D-1, início = D-7 por `:26-33`) [D] |
| J3 | Granularidades: domínio/dia, campanha/ad unit, post WP, landing URI, campanha/país/ad unit, top URLs, top países, pageviews (domínio e campanha), políticas | **confirmado** | só em wip | audit `:31-42`; endpoints `WJ:n8n/gerar_flows_joinads_v2.py:216-244` (`custom_key` `utm_campaign` `:223,230`, `id_post_wp` `:226`, `land_uri` `:228`, `top-url` `:232`, `pageview/report` `:238`, `report-all-many` `:242`, `policies` `:244`). `price-rules` e `super-filter` fora (lacunas explícitas, audit `:48-50`) [D] |
| J4 | Agregação de intervalos pela API (start≠end vira um total) | **confirmado** | existe em main + wip | `M:n8n/gerar_flows_joinads.py:12-31` (prova real de 11/08 citada); v2 emite uma janela por dia `WJ:…v2.py:32-33` [D] |
| J5 | Substituição silenciosa de `custom_key` pela API | **confirmado** | existe em main + wip | legado descarta a linha trocada `M:n8n/gerar_flows_joinads.py:221-227` ("pedimos custom_key=utm_campaign e voltou custom_key=land_uri"); v2 registra `warning custom_key_substituted` e não grava a observação `WJ:n8n/joinads_v2_normalize.js:166-178`; `M:src/sql/joinads/README.md:114-119` [D] |
| J6 | Workflows legados ainda ativos | **parcial** — afirmado em 15/10, não verificável no repo | documentado sem código (estado) | legado `U0jEfGt30HqbUq1o` (intraday) e `RpxB9ppefxZWujEV` (D-1) "continuam ativos" `WJ:docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md:24-27`; definição versionada em `M:n8n/joinads_report_intraday.json:10` (cron `0 6,12,18,23 * * *`) e `M:n8n/joinads_report_day_before.json:10` (`0 6 * * *`, `lookback_days=2` ⇒ 3 dias, `M:n8n/gerar_flows_joinads.py:595-597`), upsert `resolution=merge-duplicates` em `joinads_metrics` e `daily_project_metrics`; mapeamento ID→arquivo `M:n8n/patch_flows_joinads_vivos.py:13-16`. Além disso, P06-T03 (`M` linha 915) cita "quatro workflows ativos de receita" GAM; inventário sanitizado de 30/08 lista `GAM REPORT - CAMPAIGN ID`, `GAM + ADSENSE - PROJECTS REVENUE`, `FORCE UPDATE GAM`, `GAM - ECPM HOURLY`… como ativos (`M:docs/volc-os-graph/inventario-n8n-sanitizado.json`, sem IDs) [D doc; H prod] |

### 2.3 GTM, Sensor v3, wrapper

| # | Fato | Veredito | Classe | Prova |
|---|---|---|---|---|
| T1 | `GTM-N4KS27ZV` versão 35 | **confirmado** (afirmado) / vivo **[H]** | só em wip (`WM`) para v35; o ID existe em main | `WM:docs/operations/VOLC-MEASUREMENT-V3-2026-10-15.md:16,18,36` ("GTM live relido como versão 35"; rollback = v34); `WM:measurement/gtm/README.md:14-15`. Em `M`, o ID aparece só no contexto do incidente anon (tags 28/35/39 pausadas, "versão publicada 34") `M:docs/INCIDENTE-ANON-RUNBOOK.md:106-108` [D] |
| T2 | Fluxo GTM → `volc-ingest` → `raw_events` | **confirmado** (código) | só em wip (`WM`) | `WM:measurement/gtm/volc-sensor-v3.html:26` (endpoint `…/functions/v1/volc-ingest`); `WM:supabase/functions/volc-ingest/index.ts:161-164` (`db.from("raw_events").upsert`); hardening `WM:supabase/migrations/20261015153301_harden_volc_measurement.sql:7-16`. DDL de `raw_events` **não existe em ref alguma** (só no dump de produção citado em `W:.claude-ads/runs/economic-attribution-20261015T1310-0300/schema-inventory.json:21`) [D] |
| T3a | Sensor captura UTMs | **confirmado** (5 chaves) | só em wip | `volc-sensor-v3.html:121` (`utm_source, utm_medium, utm_campaign, utm_content, utm_term`) [D] |
| T3b | normalização/limite | **confirmado** | só em wip | `utmValue` `:107-112`: lower, sem acento, remove `"'=!+#*~;^()<>[],`, espaço→`_`, corte 40; valor que o filtro de PII altera é **descartado inteiro** `:109` [D] |
| T3c | sessionStorage | **confirmado** | só em wip | `volc_sid` `:88-94`; `volc_utm` `:117,128-131` [D] |
| T3d | lote 10 s / 20 eventos | **confirmado** | só em wip | `flushMs: 10000`, `maxBatch: 20`, `maxBytes: 60000` `:31-33`; flush também em `pagehide`/`visibilitychange` `:194-198`; edge corta em 20 `index.ts:7,124` [D] |
| T3e | sem valores de gclid/gbraid/wbraid | **confirmado** | só em wip | só `f.paid = 1` `:125`; `volc-ingest` não tem campo para click id `index.ts:16-27` [D] |
| T3f | "só `paid=1`" | **parcial** | só em wip | o sensor envia `paid: 1` **ou `paid: 0`** (`o.paid = o.paid ? 1 : 0` `:133`), e só no evento `volc_sensor_ready` (`:403-405`) [D] |
| T4 | Wrapper GPT envia `utm_source/medium/campaign`, não content/term, sem click IDs/PII | **parcial** | só em wip | default `['utm_source','utm_medium','utm_campaign']` `WM:measurement/gtm/webs-wrapper-v2.html:8,28`; bloqueio de chaves de clique/PII `:33`; valores com padrão de PII viram `''` `:34-39,74-80`. **Acréscimos:** envia também a key `pg` (slug do último segmento do path) `:9-10,29,84,109`; e o mesmo filtro **anula `utm_campaign` numérico ≥ 10 dígitos** (ver §3) [D] |
| T5 | JoinAds usa principalmente `utm_campaign` | **confirmado** (com ressalva) | existe em main + wip | legado `CUSTOM_KEY = utm_campaign` `M:n8n/gerar_flows_joinads.py:394-396`; v2 usa `utm_campaign` em 2 endpoints de receita (`:223,230`) e também `id_post_wp`, `land_uri` (`:226,228`). Que o valor de `utm_campaign` na JoinAds venha do WEBS wrapper é **[I]** (`W:.claude-ads/runs/economic-attribution-20261015T1310-0300/workers/a/handoff.md:12`) — ver H1 em §3 [D/I] |

### 2.4 Evidência do roadmap "Sensor v3 descarta `utm_campaign`"

| Item | Valor |
|---|---|
| Onde está | `volc-os-workbook/ROADMAP-VIVO.json`, tarefa **P06-T09** ("Reconciliar lucro por visita comprada no grão campanha-dia", `partial`), campo **`proof`**: "…sessão, página e ad view não se ligam à campanha (**sensor v3 descarta utm_campaign**; sem click id). Evidência: .claude-ads/runs/economic-attribution-20261015T1310-0300/." |
| Refs | `W` linha 625 (`id`) / 628 (`proof`); `WF` e arquivo sujo linha 730/733. **Não existe em `main`** (P06-T09 ausente em `M`) [D] |
| Origem | `W:.claude-ads/runs/economic-attribution-20261015T1310-0300/RELATORIO.md:9` e `canary-result.json:312,327,…` ("utm_campaign descartado pelo filtro de PII do sensor v3") [D] |
| Contradição interna da própria evidência | `W:…/identity-gap-matrix.json:17` diz "UTMs chegam a raw_events: SIM … source/medium/campaign/content/term" — leitura do allowlist, sem testar o valor real [D] |
| Código atual | `WM:measurement/gtm/volc-sensor-v3.html` (sha256 `cb018224…41e4`, idêntico ao arquivo sujo). `utmValue` (`:107-112`) devolve `''` quando `clean()` altera o valor; `clean` aplica o regex de telefone/sequência longa `/\+?\d[\d\s().-]{8,}\d/g` (`:73`), que casa qualquer sequência de **≥ 10 dígitos** |
| Prova executável | `receipts/inventario/02-prova-filtro-pii-utm.mjs` extrai as funções do próprio arquivo versionado e as executa: `"24278665189"` (campaign.id real da campanha Senac) → sensor `""`, wrapper `""`; `"1234567890"` → `""`; `"123456789"` → preservado; `"senac-caruaru"` → preservado [D] |
| **Veredito** | **confirmado, com mecanismo corrigido**: o sensor não "descarta `utm_campaign`" em geral — ele descarta **todo valor de UTM com ≥ 10 dígitos consecutivos**, o que inclui o `campaign.id` do Google Ads (10–11 dígitos) quando o template de URL usa `utm_campaign={campaignid}`. Nomes textuais passam. O WEBS Wrapper v2 tem o mesmo defeito (`webs-wrapper-v2.html:38,77`) |
| Delta proposto (não aplicado) | P06-T09 `proof`: substituir "sensor v3 descarta utm_campaign" por "o filtro de PII do Sensor v3 (`measurement/gtm/volc-sensor-v3.html:73,109`) e do WEBS Wrapper v2 (`webs-wrapper-v2.html:38,77`) anula valores de UTM com ≥ 10 dígitos, incluindo o campaign.id numérico; prova hermética em `docs/data-intelligence/fundacao-20261016/receipts/inventario/02-prova-filtro-pii-utm.mjs`". Acrescentar lacuna: "a correção exige permitir ID numérico em `utm_campaign`/`utm_content` (allowlist por chave) — publicação de GTM proibida nesta missão". Estado continua `partial` |

## 3. Hipótese de alto impacto derivada do §2.4 (exige leitura externa)

**H1 [H].** Se a key-value GPT `utm_campaign` que a JoinAds devolve vier do WEBS Wrapper (inferência do worker A da execução 043c77f5), então, a partir da publicação do GTM v35 (15/10/2026), o wrapper v2 passou a **não setar `utm_campaign` para campaign.id numérico**, e a receita JoinAds por campanha (`custom_key=utm_campaign`) deveria cair para perto de zero a partir de 15–16/10, enquanto `earnings` por domínio continua. A cobertura medida na v2 (97–100% em 08–14/10, `WJ:docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md:89-100`) é **anterior** ao v35. Leituras L5/L6 (seção 8) decidem. Se confirmada, a única ponte custo×receita do VOLC (campanha × dia por `utm_campaign_value = campaign.id`) está quebrada desde 15/10 — risco econômico maior do que qualquer item de modelagem desta missão.

## 4. Inventário de tabelas, views e funções

Colunas: **Esc.** = semântica de escrita (`append` = insert-only com gatilho que recusa UPDATE/DELETE; `latest-wins` = UPSERT/merge que destrói a versão anterior; `idem.` = idempotente por chave sem sobrescrever); **DEFAULT 0** = default numérico que confunde ausência com zero; **Gatilho** = trigger que sobrescreve outra tabela.

### 4.1 Custo Google Ads

| Objeto | Classe | Esc. | DEFAULT 0 / zero inventado | Gatilho que sobrescreve | Prova |
|---|---|---|---|---|---|
| `trafego_coleta_execucao` (ledger de lote, guarda hash do payload, não valores) | existe em main | append (`:416-430`) | `projecao_linhas DEFAULT 0` (contador, inócuo) | — | `M:supabase/migrations/v12_04_gads_fato_canonico_dia.sql:89,402,416-430` [D] |
| `google_ads_campanha_dia` | existe em main | **latest-wins** por precedência D0<D-1<backfill e `colhida_em` (`ON CONFLICT … DO UPDATE` `:849-850`) | métricas nulas permitidas (`:289-292`) | `volc_gads_projetar_daily_compat` projeta em `daily_campaign_metrics` (`:483`) | `M:…v12_04…:259,576,805,849-850` [D]; aplicação em prod: **não aplicada** segundo `M` ROADMAP P10-T04 (linha 1463: "a view que ele lê depende da v12_04, ainda não aplicada no Supabase oficial") [D doc] |
| `trafego_coleta_execucao_saude` (view) | existe em main | — | — | — | `M:…v12_04…:1201` [D] |
| `google_ads_fato_granular` (+7 partições) | existe em main | **latest-wins** `ON CONFLICT (familia,…,dimensao_hash) DO UPDATE` | — | — | `M:…v17_01_gads_fatos_granulares.sql:55,181-189,429` [D]; "aplicada em produção em 08/10" só afirmado (P06-T08 `M`) [H] |
| `google_ads_mudanca`, `google_ads_estado` | existe em main | append (`:270-278`; mudança `ON CONFLICT DO NOTHING` `:459`) | — | — | `M:…v17_01…:210-240,270-278,459` [D] |
| `vw_gads_campanha_dia`, `vw_gads_arbitragem_{campanha_dia,placement_dia,hora}` | existe em main | view | — | — | `M:…v17_01…:541,555,592,618`; redefinidas em `M:…v17_04_arbitragem_reconciliada.sql:49,140,157` ("NÃO aplicada", P06-T03 `M`) [D] |
| `trafego_google_inteligencia_{coleta,item,metrica}` (inteligência, não fato de custo) | existe em main | append | "quantidade nula nunca vira zero" `:160` | — | `M:supabase/migrations/v12_01_google_inteligencia_coletas.sql:24,99,114,160,166-186` [D] |
| `google_ads_collection_run` | só em wip (`W0`+) | idem. por `idempotency_key` (`ON CONFLICT DO UPDATE` só de `workflow_execution_id`) | contadores `DEFAULT 0` (inócuos) | — | `W:supabase/migrations/v21_01_google_ads_coleta_canonica.sql:16-62,206-209` [D] |
| `google_ads_raw_batch` | só em wip | **append** + idempotente por hash | — | — | `W:…v21_01…:64-92,158-160,211-222` [D] |
| `google_ads_observation` | só em wip | **append** | métricas em `jsonb` sem default numérico; **porém o coletor n8n escreve 0** quando falta a linha de métrica (ver §5, risco R3) | — | `W:…v21_01…:94-131,161-163,328` [D] |
| `google_ads_campaign_day_latest` (view, DISTINCT ON por `collected_at DESC`) | só em wip | view latest | — | — | `W:…v21_01…:286-293` [D] |
| `google_ads_collection_health` (view: último run, falhas 24 h) | só em wip | view | — | — | `W:…v21_01…:295-302` [D] |
| `volc_ingest_google_ads_batch(jsonb)`, `_auto(jsonb)`, `volc_finish_google_ads_run(jsonb)` | só em wip | fronteira única de escrita, `SECURITY DEFINER`, `service_role` | — | — | `W:…v21_01…:165-284,316,323`; `v21_02…:3-26`; `v21_03…:3-28` [D] |
| `daily_campaign_metrics` (legado, alvo de 3 gatilhos/projeções) | DDL **não versionado** em ref alguma | latest-wins | recebe `spend = 0, clicks = 0, …` inseridos pelo gatilho JoinAds | sim | `W:…/schema-inventory.json:21` (tabelas centrais sem CREATE versionado) [D] |

### 4.2 Receita (JoinAds, GAM, AdSense, câmbio)

| Objeto | Classe | Esc. | DEFAULT 0 | Gatilho que sobrescreve | Prova |
|---|---|---|---|---|---|
| `joinads_metrics` | existe em main | **latest-wins** (`UNIQUE(date, utm_campaign_value, joinads_domain)` alvo de `on_conflict`, `merge-duplicates`) | **`revenue NOT NULL DEFAULT 0`** `:30`; `revenue_converted`, `impressions`, `clicks`, `ctr`, `ecpm`, `viewable_impressions DEFAULT 0` `:31-37`; `created_at/updated_at timestamp` sem fuso `:39-40` | `trg_joinads_sync_daily` → `sync_joinads_revenue_to_daily_metrics()` faz `UPDATE daily_campaign_metrics SET revenue = NEW.revenue … WHERE campaign_id = NEW.utm_campaign_value AND date = NEW.date` (**último domínio vence**: a chave da origem tem domínio, a do destino não) e, se não acha, **insere a linha com `spend, clicks, impressions, conversions, … = 0`** `:89-120,144-146`; `trg_joinads_revenue_converted` (câmbio por data) `:138-141` | `M:src/sql/joinads/01_joinads_metrics.sql` [D] |
| `daily_project_metrics` (receita por domínio-dia) | DDL fora de migration (`M:src/sql/restructure_daily_project_metrics.sql`) | latest-wins (n8n `merge-duplicates`) | não verificado | — | `M:n8n/joinads_report_intraday.json` nó "Upsert daily_project_metrics" [D] |
| `joinads_collection_run` | só em wip (`WJ`) | idem. por `run_key` (`ignore-duplicates`), guarda de UPDATE `joinads_guard_run_update` | contadores `DEFAULT 0` (inócuos) | — | `WJ:supabase/migrations/20261015163704_joinads_collection_canonical.sql:10-51,218-241` [D] |
| `joinads_raw_batch` | só em wip | **append** (gatilho `:211-213`); hash calculado por gatilho `:161-198` | `payload_sha256 DEFAULT repeat('0',64)` substituído pelo gatilho | — | `WJ:…20261015163704…:53-76` [D] |
| `joinads_observation` | só em wip | **append** (`:214-216`); PK `observation_key` | receitas `numeric` **nulas** permitidas `:100-101`; `currency_code DEFAULT 'USD'` `:99`; `data_status ∈ {observed, zero_confirmed, unavailable, unsupported}` `:140`. RLS `ENABLE` sem `FORCE` `:262-264` | — | `WJ:…20261015163704…:78-141` [D] |
| `joinads_observation_latest` (view) | só em wip | view latest restrita à maior `collector_version` bem-sucedida | — | — | `WJ:…20261015170000_joinads_latest_collector_version_guard.sql:10-37` [D] |
| `gam_metrics` | DDL **não versionado** (só `M:src/sql/add_gam_metrics_columns.sql`) | latest-wins | não verificado | `sync_gam_revenue_to_daily_metrics()` reescrita pelo roteador de grão (Meta adset × Google campanha) `M:supabase/migrations/20260910143000_gam_attribution_grain_router.sql:309,344,392`; view `vw_gam_attribution_route` `:83` | [D] |
| `adsense_metrics` | DDL não versionado | — | — | `calculate_adsense_campaign_revenue` por URL exata (`W:…/identity-gap-matrix.json:18`) | [I] |
| `exchange_rate_history` + `receita_observacao` (append) + `receita_releitura` | existe em main, **PROPOSTA não aplicada** | `receita_observacao` append-only alimentada por gatilho AFTER nas tabelas latest-wins `:32,277,316-328`; `receita_releitura` latest-wins `:341,433` | `confirmacoes DEFAULT 0` (contador) | — | `M:supabase/migrations/v23_01_receita_datada_cambio.sql:3` ("PROPOSTA: não aplicada em produção") [D] |

### 4.3 `raw_events`, sessões, funil

| Objeto | Classe | Esc. | Observação | Prova |
|---|---|---|---|---|
| `raw_events` | DDL **não encontrado** em ref alguma; hardening só em wip | insert-only nominal (`service_role` só `SELECT, INSERT`) | **Índice único `raw_events_dedup(sid, pid, event_name, ts_sec)`** alvo do `upsert … ignoreDuplicates` ⇒ dois eventos de mesmo nome na mesma pageview e no mesmo segundo **colapsam em um** (ex.: dois `volc_ad_view` de slots diferentes, `volc_scroll_mark` 25 e 50 no mesmo segundo) — perda silenciosa [I, a partir do índice declarado no dump] | `WM:supabase/functions/volc-ingest/index.ts:161-164`; índice: `W:…/schema-inventory.json:96-98` (dump de produção de 15/10 08:41, anterior ao hardening); `WM:supabase/migrations/20261015153301_harden_volc_measurement.sql:7-16` [D] |
| `fact_page_daily` (`UNIQUE(report_date,path,host)`), `compute_page_daily()` | DDL **não versionado** | latest-wins (inferido do UNIQUE) | host vazio e zero ad views para rotas atuais (`W:…google-ads-recovery…/RELATORIO.md:88`) | `W:…/schema-inventory.json:381-388` [D doc] |
| `fact_funnel_daily`, agregador do funil (flow `GHMVIgFAv6oytKuj`) | DDL não versionado; flow inativo | — | P08-T07 `M` linha 1084: "flow GHMVIgFAv6oytKuj está inativo, duplica orquestração e ainda contém datas fixas" | [D doc] |
| `site_visits` (legado com `gclid/gbraid/wbraid`) | DDL não versionado | — | "sem escrita desde 12/08/2026"; tag GTM 35 que escrevia com JWT anon pausada | `M:docs/INCIDENTE-ANON-RUNBOOK.md:106`; `W:…/identity-gap-matrix.json:16` [D doc] |

### 4.4 Ledger de coleta (v12 / v21) e núcleo econômico

| Objeto | Classe | Esc. | Prova |
|---|---|---|---|
| Ledger v12 (`trafego_coleta_execucao` + `google_ads_campanha_dia` + `volc_registrar_gads_campanha_dia`) | existe em main; prod: não aplicada (P10-T04 `M`) | append (recibo) + latest-wins (fato) | §4.1 [D] |
| Ledger v21 (`google_ads_collection_run/raw_batch/observation`) | só em wip; prod: afirmado aplicado 15/10 | append | §4.1 [D/H] |
| Ledger de migrations `volc_ops.migracao_evento` | existe em main (v20_01/v20_02) | append | `M:supabase/migrations/v20_01_ledger_migrations.sql`; P10-T27 `M` linha 1981 [D]. O Postgres vivo "não possui `supabase_migrations.schema_migrations`" (`WJ:docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md:67-71`) [D doc] |
| Núcleo econômico: schema privado `economia` (`pagina_funil`, `execucao`, `campanha_dia` append, `receita_nao_reconciliada` append, `qualidade_conversao` append, `candidato_acao` append, `gravar_execucao(jsonb)`, views `ultima_execucao`, `funnel_economics_daily`, `conversion_quality`, `action_candidates`, `page_journey_leakage`) | só em wip (`W`+), **não aplicado** (PGlite 29/29) | append por execução | `W:supabase/migrations/20261015163636_economia_atribuicao_campanha_dia.sql:6-14,95,142,206,247-268,273,375-424`; P06-T09 `proof` (`WF` linha 733) [D] |
| `volc_ads/economia/{nucleo,reconciliacao,fontes,job,persistencia,qualidade_conversao,canario}.py` | só em wip | — | lê custo de `google_ads_observation` (último por campanha-dia, runs `completed`) e receita de **`joinads_metrics` legado (latest-wins)**, não da v2 append `W:volc_ads/economia/job.py:13-15,34-57`; via SSH+psql `:69-81`; `ATRASO_CUSTO = 26 h` `reconciliacao.py:38`; 7 estados `nucleo.py:80-87` [D] |
| Precedentes em main | existe em main | — | `backend/app/trafego/custo_canonico.py` (dia sem coleta = `None`), `services/orakul_predictive/semantica.py:10-17` (7 estados, outro vocabulário) [D] |

## 5. Inventário de coletores

| Coletor | Classe | Cadência (America/Sao_Paulo) | Autor da verdade / destino | Idempotência | Heartbeat | Retry / error workflow | Quem lê | Prova |
|---|---|---|---|---|---|---|---|---|
| n8n Google Ads canônico D0 `Ps9yLfQkHeaAbyZZ` | só em wip (instalador); estado vivo [H] | `7 6-23 * * *` | Google Ads API v25 → `volc_ingest_google_ads_batch_auto` (v21) | run por `idempotency_key`, lote por `(run_id,batch_key)` + hash | `google_ads_collection_health`; run `running` > 30 min suspeito | retries "incompletos" (só termos tem retry explícito na RPC: `canonical_with_explicit_rpc_retry: 1`); **sem errorWorkflow**; falha antes do 1º lote não gera recibo | `volc_ads/economia/job.py` (wip) | `W:scripts/instalar_coleta_canonica_google_ads_n8n.py:21-24` (clona os legados `hN15qFAVOqH0135q`/`tKUItcd0AoD9mozV`), `:261-262,345`; `W:docs/operations/google-ads-coleta-canonica.md:55-60`; `W:…/RELATORIO.md:48` [D] |
| n8n Google Ads canônico D-1 `7yxs1aOlzWkkkSf9` | só em wip | `17 6,14 * * *` | idem | idem | idem | idem | idem | idem [D] |
| n8n termos/keywords `TFlmThr4930oPneE` | só em wip | `23 */4 * * *`, `LAST_7_DAYS` | `search_term_view`, `keyword_view` → v21 | idem; lote por conta×recurso | idem; 3 execuções ficaram `running` no ledger | `retryOnFail, maxTries 3` `:184`; sem errorWorkflow | ninguém versionado | `W:scripts/instalar_coleta_termos_keywords_n8n.py:166-167,184,193` [D] |
| n8n legado `hN15qFAVOqH0135q` (D0) / `tKUItcd0AoD9mozV` (D-1) | definição fora do repo; estado contraditório | `0 6,12,18,23 * * *` / diário 6h (15/10) | `daily_campaign_metrics` legado | — | — | sem errorWorkflow | front/legado | **Contradição temporal:** `M:docs/architecture/GADS-REPORT-D0-D1-E-CONTRATO-DE-DADOS.md:14-15` (28/08: "atualizado, inativo") × `W:…/collector-inventory.json` (15/10 13:12: `active: true`, `legacy_d0_coauthority`) [D] |
| n8n v12 `volc_gads_campanha_dia_{d0,d1}.json` | existe em main, `active: false` | `0 6,12,18,23` / `0 6` | RPC v12 | sim | "Alerta de rotina parada" | retry 3 por nó | — | `M:n8n/volc_gads_campanha_dia_d0.json:10,1059`; `…_d1.json:10,1059` [D] |
| Python `volc_ads/coleta` (10 famílias) + timers `volc-gads-coleta-{d0,d1,recoleta}` | existe em main, **não instalado** | D0 `06,12,18,23:05`; D-1 `06:30`; recoleta 7 dias `07:15` | RPCs v12_04/v17_01 | passo `--agenda` pula famílias já concluídas | `deadman_coleta.py` (sem consumidor de prod) | — | — | `M:volc_ads/coleta/__main__.py:1-17`; `M:deploy/gads-coleta/README.md:1,5`; `*.timer:5` [D] |
| Python `volc_ads/inteligencia_google` (recommendation, conversion goals, ad_group_ad, PMax) | existe em main (+ alteração suja = `WD`) | one-shot; `deploy/google-intelligence` não instalado | v12_01 (append) | sim | `saude.py` | — | — | `M:volc_ads/inteligencia_google/coletor.py:168,239,321`; P09-T14 `M` linha 1341 [D] |
| n8n JoinAds v2 intraday `cpb6tNxt211UkAn2` | só em wip (= sujo); estado vivo [H] | `15 6-22/2 * * *`, D0 | API JoinAds (office + pageview) → PostgREST `joinads_collection_run/raw_batch/observation` | `run_key` = versão:modo:janela:gatilho:**hora UTC** ⇒ reexecução na mesma hora não duplica nem captura mudança; `ignore-duplicates` | `joinads_collection_run` (sem view de saúde) | `retryOnFail, maxTries 3` em HTTP e Supabase; **sem errorWorkflow** (`settings` sem a chave) | ninguém versionado (economia lê o legado) | `WJ:n8n/gerar_flows_joinads_v2.py:107-187,319-320`; `WJ:n8n/joinads_v2_normalize.js:13-17`; `WJ:n8n/joinads_v2_intraday.json` settings [D] |
| n8n JoinAds v2 D-1 `jDX397ViVcRQft4A` | só em wip | `20 6 * * *`, D-7..D-1 (cada dia relido 7 vezes ⇒ curva de maturação D+1..D+7 se acumulada) | idem | idem | idem | idem | idem | `…v2.py:323-324` [D] |
| n8n JoinAds legado `U0jEfGt30HqbUq1o` / `RpxB9ppefxZWujEV` | existe em main (JSON gerado); ativos segundo 15/10 [H] | `0 6,12,18,23 * * *` / `0 6 * * *` (D-3..D-1) | `joinads_metrics` + `daily_project_metrics` (latest-wins) → gatilho → `daily_campaign_metrics` | upsert (idempotente, destrói histórico) | nós "Marca joinads_last_update" / "Registra falha" | retry 3 | `volc_ads/economia/job.py`, front, `v17_04` | `M:n8n/joinads_report_{intraday,day_before}.json:10`; `M:n8n/gerar_flows_joinads.py:585-597`; `M:n8n/patch_flows_joinads_vivos.py:13-16` [D] |
| n8n GAM/AdSense (≥ 4 flows de receita) | documentado sem código no repo (sem JSON versionado) | "atual e D-1" | `gam_metrics` (0 linhas), `daily_project_metrics` | — | — | — | — | P06-T03 `M` linha 915; `M:docs/volc-os-graph/inventario-n8n-sanitizado.json` (30/08) [D doc] |
| GTM `GTM-N4KS27ZV` v35 → Sensor v3 + WEBS Wrapper v2 → `volc-ingest` | só em wip (fonte); vivo [H] | contínuo (navegador), lote 10 s/20 | `raw_events` | `ignoreDuplicates` em `(sid,pid,event_name,ts_sec)` | nenhum | — | `fact_page_daily` (função não versionada) | §2.3 [D] |
| Job `volc_ads/economia/job.py` (reconciliação custo×receita) | só em wip | manual (CLI), sem agenda | `economia.*` (não aplicado) | `idempotency_key` em `gravar_execucao` | `economia.execucao` | — | views gold (sem consumidor) | `W:volc_ads/economia/job.py:1-20` [D] |

Risco de zero inventado na coleta canônica Google (**R3**): o Code node do instalador usa `basic = … ? Number(obj[key]) : 0` (`W:scripts/instalar_coleta_canonica_google_ads_n8n.py:127`) e `const metricRow = metricMap.get(id) || {}` (`:133`): uma campanha listada **sem linha de métrica** (sem atividade **ou** consulta de métricas falha/incompleta) é gravada com `cost_micros = 0, clicks = 0, conversions = 0…` (`:149-167`), contrariando o `COMMENT` da tabela ("métricas ausentes não recebem zero inventado", `v21_01:328`). Para campo omitido dentro de linha existente o 0 é correto (o JSON da API omite zeros) [I]; para linha ausente é ambíguo. O `raw_source` e o `raw_batch` preservam o payload, então é recuperável a posteriori [D]. Idem em termos/keywords (`…termos_keywords_n8n.py:56`).

## 6. O que o Lab herdado cobre vs o que a missão pede

Lab: `experiments/data-intelligence-lab/src/volc_dil/` (5.641 linhas, existe só nas branches `lab/*`, não em `main`). 172 testes (`tests/data-intelligence/`).

| Pedido da missão (seção 2) | Coberto pelo Lab herdado | Estado (taxonomia do manifesto §7) | Lacuna para a fundação |
|---|---|---|---|
| Observação **append-only** | contrato `Observacao` imutável com 3 relógios, linhagem, fingerprint (`contracts/observation.py:123-330`, `fingerprint.py`) — mas **em memória**; nenhuma tabela/migration | testado com sintético | schema PostgreSQL append-only candidato (thread A); adaptadores das fontes reais v21/JoinAds v2 → `Observacao` |
| **8 estados de dado** | 7 estados `EstadoMedida` (`contracts/vocab.py:29-36`: medido, zero_confirmado, ausente, nao_coletado, falha, nao_atribuivel, nao_aplicavel) + `Maturidade` (3) + `Cobertura` (3) | testado hermeticamente | a definição dos "8 estados" **não foi encontrada no repositório**; três vocabulários concorrentes: lab (7), `volc_ads/economia/nucleo.py:80-87` (os mesmos 7, wip), `services/orakul_predictive/semantica.py:10-17` (7 diferentes: inclui `antigo`, `hipotese`), JoinAds v2 `data_status` (4). Thread A precisa fixar o 8º e o mapeamento |
| União custo × tráfego × funil × receita | só custo × receita em campanha × dia (`contracts/aggregate.py`); sessões como contagem (`Metrica.SESSOES`) | testado com sintético | tráfego/funil sem chave de campanha (§2.4, §4.3); receita por sessão impossível (`DATA-CAPABILITY-MATRIX.md:55`) |
| Replay `as_of` | `contracts/snapshot.py` (`verificar_sem_futuro`, `Snapshot.construir`), `replay/motor.py:37-161` (corte `as_of`, 4 baselines, contraprovas) | testado com sintético | dado real com versões de conhecimento: só v21 e JoinAds v2 (wip) o permitem; `economia/job.py` usa "último", sem `collected_at <= as_of` |
| Shadow | nenhum motor de shadow; só o shadow Senac (1 instante, `backend/app/trafego/shadow_experimentos/`) | ainda não demonstrado | thread D |
| Simulador | `swarm/simulador.py`, `swarm/cenario.py`, `replay/cenario.py` (mundos sintéticos de alocação/maturação) | testado com sintético (resultado negativo) | simulador de coleta/ausência/revisão com as falhas reais deste inventário (R1–R7) — thread E |
| Observabilidade | nada no lab; no produto: `google_ads_collection_health` (wip), `trafego_coleta_execucao_saude` (main), `deadman_coleta.py` (main, sem consumidor) | ainda não demonstrado | thread G: frescor, cobertura earnings×campanhas, colapso de dedup, zero inventado, legado×canônico |
| Estatística/maturação | `statlab/maturacao.py`, `shrinkage.py`, `sequencias_confianca.py`, `fdr.py` | testado com sintético | calibrar com leituras reais D+1..D+7 da JoinAds v2 (se acumuladas) |

## 7. Tarefas do roadmap relacionadas

Fonte completa: `receipts/inventario/03-roadmap-tarefas.tsv` (estado e linha em `M` e em `WF` = arquivo sujo). Resumo das divergências que importam:

| ID | Título | `main` | wip/sujo | Observação |
|---|---|---|---|---|
| P06-T02 | Consolidar ingestão de custo por data e conta | partial | partial | — |
| P06-T03 | Reativar e reconciliar fontes de receita | partial (l.915) | partial (l.679) | `M` tem `latest_evidence` 14/10 (upsert sem as-of); nenhum dos dois cita a JoinAds v2 nem H1 |
| P06-T04 | Unificar moeda, câmbio, impostos e revshare | partial | partial | v23_01 PROPOSTA |
| P06-T05 | Recibos e alertas de rotina parada | partial | partial | — |
| P06-T07 | Tracking Control Plane em modo leitura | partial (l.948) | partial (l.707) | só wip registra GTM v35/Sensor v3 |
| P06-T08 | Ledger canônico de coleta Google Ads | partial (l.954) | partial (l.713) | `M` descreve v12_01/v12_04; wip descreve v21 aplicada — **duas narrativas incompatíveis** |
| P06-T09 | Lucro por visita comprada campanha-dia | **ausente** | partial (l.730) | contém a evidência do §2.4 |
| P07-T02 | Evento e valor elegíveis para envio | todo | todo | conversão `adViewInterstitial` R$ 10 fixos |
| P08-T02 | Vínculo campanha → funil → URLs | partial | partial | — |
| P08-T03 | Host/path vazios e identidade de página | **todo** | **partial** | divergência de estado |
| P08-T07 | Versionar telemetria e agregador do funil | partial (l.1084) | partial (l.850) | sensor versionado só em `WM` |
| P09-T01 | Eventos operacionais e recomendações versionadas | partial | partial | — |
| P09-T09 | ORAKUL em shadow | todo | todo | — |
| P09-T10 / T11 / T13 | Allocator: contrato, replay, shadow | todo | todo | bloqueados por dado append-only |
| P09-T14 | Coleta contínua de inteligência Google Ads | partial (l.1341) | partial (l.1079) | wip: "n8n confirmado como autoridade de agenda" |
| P10-T04 | Heartbeat e deadman | partial (l.1463) | partial (l.1134) | `M`: v12_04 não aplicada |
| P10-T06 | Data Pipeline Registry | partial | partial | — |
| P10-T16 | Workflows n8n ao ledger v12 e autoridade de agenda | partial (l.1616) | partial (l.1285) | wip: v21 substitui v12 na prática |
| P10-T24 | Freedom Lab | partial | **ausente** | — |
| P10-T27 | Ledger de migrations por hash | partial | **ausente** | prod sem `schema_migrations` |
| P14-T02 | Replay e shadow antes de autonomia | partial (l.2446) | partial (l.1715) | — |
| P14-T06..T09 | Preditivo: ledger, baseline, calibração, simulador | todo | todo | — |
| P14-T10 | Validade científica do Predictive Core | partial | **ausente** | — |
| P15-T03 | Painel semanal com linhagem | todo | todo | — |
| P16-T05 | GTM/GA4 e contrato de medição | reserved | reserved | — |
| P05-T07 / T08 | Search não escala / termos e negativas | partial | partial | — |
| P05-T09 | Guardião 72 h | **partial** | **todo** | divergência de estado |

## 8. Leituras externas necessárias (somente leitura; o integrador decide e executa)

Todas exigem caminho autorizado sem imprimir credencial. Nenhuma escreve. Risco = o que pode dar errado ao executar.

| # | Consulta exata | Alvo | Motivo | Risco |
|---|---|---|---|---|
| L1 | `SELECT table_name, table_type FROM information_schema.tables WHERE table_schema IN ('public','economia') AND table_name IN ('google_ads_collection_run','google_ads_raw_batch','google_ads_observation','google_ads_campaign_day_latest','google_ads_collection_health','trafego_coleta_execucao','google_ads_campanha_dia','google_ads_fato_granular','google_ads_mudanca','google_ads_estado','joinads_metrics','joinads_collection_run','joinads_raw_batch','joinads_observation','joinads_observation_latest','receita_observacao','raw_events','fact_page_daily','fact_funnel_daily','daily_campaign_metrics','gam_metrics','campanha_dia') ORDER BY 1;` | Postgres oficial (`database.agenciavolc.com.br`), papel read-only | decidir v12_04 × v17_01 × v21 × v23_01 × economia: o que está aplicado | baixo (catálogo) |
| L2 | `SELECT tgrelid::regclass, tgname, pg_get_triggerdef(oid) FROM pg_trigger WHERE NOT tgisinternal AND tgrelid::regclass::text IN ('joinads_metrics','gam_metrics','google_ads_observation','google_ads_raw_batch','joinads_observation','joinads_raw_batch','raw_events','daily_campaign_metrics');` | idem | confirmar gatilho `sync_joinads_revenue_to_daily_metrics` vivo (último domínio vence; custo 0 inserido) e gatilhos append-only | baixo |
| L3 | `SELECT indexrelid::regclass, pg_get_indexdef(indexrelid) FROM pg_index WHERE indrelid = 'public.raw_events'::regclass;` e `SELECT event_name, count(*) FROM (SELECT sid,pid,event_name,ts_sec FROM public.raw_events WHERE ts >= now()-interval '7 days') s GROUP BY 1;` | idem | confirmar `raw_events_dedup(sid,pid,event_name,ts_sec)` e dimensionar o colapso (R4) | baixo; a 2ª é varredura de 7 dias — usar `statement_timeout` |
| L4 | `SELECT payload->'utm'->>'campaign' IS NOT NULL AS tem_campanha, (payload->'utm'->>'paid')::int AS paid, count(*) FROM public.raw_events WHERE event_name='volc_sensor_ready' AND ts >= '2026-10-15' GROUP BY 1,2;` | idem | prova viva do §2.4 (utm.campaign ausente em sessões pagas) | baixo; não selecionar `sid`/valores |
| L5 | `SELECT o.metric_date, sum(o.revenue_client) FILTER (WHERE o.grain='domain_day') AS earnings, sum(o.revenue_client) FILTER (WHERE o.custom_key='utm_campaign' AND o.campaign_id IS NOT NULL) AS campanhas, count(*) FILTER (WHERE o.custom_key='utm_campaign') AS n_obs_campanha FROM public.joinads_observation_latest o WHERE o.metric_date BETWEEN '2026-10-08' AND current_date GROUP BY 1 ORDER BY 1;` (ajustar `grain` aos valores reais de `SELECT DISTINCT endpoint, grain FROM public.joinads_observation`) | idem | **H1**: a receita por campanha caiu após o GTM v35 (15/10)? | baixo |
| L6 | GTM API: `GET tagmanager/v2/accounts/{a}/containers/{c}/versions/34` e `/versions/35` (escopo `tagmanager.readonly`), comparar o HTML das tags WEBS Wrapper e Sensor com `measurement/gtm/*` (sha256) | Google Tag Manager `GTM-N4KS27ZV` | confirmar v35 vivo, se o wrapper v34 setava `utm_campaign` numérico e se o v35 é idêntico ao versionado | baixo (read-only); **nunca** `publish`/`create_version` |
| L7 | n8n API: `GET /api/v1/workflows/{id}` para `Ps9yLfQkHeaAbyZZ`, `7yxs1aOlzWkkkSf9`, `TFlmThr4930oPneE`, `cpb6tNxt211UkAn2`, `jDX397ViVcRQft4A`, `U0jEfGt30HqbUq1o`, `RpxB9ppefxZWujEV`, `hN15qFAVOqH0135q`, `tKUItcd0AoD9mozV`, `svJWqv5r1NSxB8MO`, `Q6IunKtTI0gY0KgX` — extrair só `active`, `settings.errorWorkflow`, `settings.timezone`, `nodes[type=scheduleTrigger].parameters.rule`, `updatedAt` (descartar `credentials` e `parameters` de Set antes de gravar recibo) | n8n de produção | estado ativo, cron e error workflow de todos os coletores; resolver a contradição 28/08 × 15/10 dos legados | médio: o GET devolve o workflow inteiro (pode conter config sensível) — filtrar na origem, não persistir o bruto |
| L8 | n8n API: `GET /api/v1/executions?workflowId={id}&limit=20&includeData=false` para os 5 canônicos | n8n | frescor real e falhas desde 15/10 | baixo |
| L9 | `SELECT collector, last_started_at, last_finished_at, last_status, failures_24h FROM public.google_ads_collection_health;` e `SELECT collector, collector_version, status, count(*), max(started_at) FROM public.joinads_collection_run GROUP BY 1,2,3;` e `SELECT status, count(*) FROM public.google_ads_collection_run WHERE status='running' AND started_at < now()-interval '30 minutes' GROUP BY 1;` | Postgres | heartbeat, runs presos em `running` | baixo |
| L10 | `SELECT o.metric_date, count(*) AS leituras, count(DISTINCT (o.metrics->>'cost_micros')) AS valores_distintos FROM public.google_ads_observation o WHERE o.resource_type='campaign' AND o.grain='campaign_day' GROUP BY 1 ORDER BY 1 DESC LIMIT 14;` | Postgres | existe curva de maturação de custo real (D0 horário + D-1 2×/dia)? quantas versões por dia | baixo |
| L11 | `SELECT count(*) FROM public.google_ads_observation o WHERE o.grain='campaign_day' AND (o.metrics->>'cost_micros')::bigint = 0 AND (o.attributes->'raw_source'->'metrics') = '{}'::jsonb;` (ajustar ao caminho real do `raw_source`) | Postgres | dimensionar R3 (zero gravado sem linha de métrica) | baixo |
| L12 | `SELECT to_regclass('supabase_migrations.schema_migrations'), to_regclass('volc_ops.migracao_evento');` e `SELECT * FROM volc_ops.migracao_evento ORDER BY 1 DESC LIMIT 20;` | Postgres | qual ledger de migrations vale; v20_01 aplicada? | baixo |
| L13 | Edge Function: `ls -la` + `sha256sum` de `volumes/functions/volc-ingest/index.ts` no host (sem `cat` de `.env`) | host Supabase (SSH) | código vivo = `WM:supabase/functions/volc-ingest/index.ts`? | médio (SSH em produção; só leitura de hash) |

## 9. Delta de curadoria proposto (não aplicado; para o integrador)

1. **P06-T09** (`proof`): corrigir o mecanismo conforme §2.4 e anexar o recibo `02-prova-filtro-pii-utm.mjs`; manter `partial`. Trazer a tarefa para `main` junto com o código de `volc_ads/economia` quando houver integração.
2. **P06-T03** (`latest_evidence`): "16/10 (A-inv, só repo): JoinAds v2 append-only (`joinads_collection_run/raw_batch/observation`, intraday `15 6-22/2`, D-1 relendo D-7..D-1) existe só em `wip/historico-joinads-20261015`; o núcleo econômico wip lê o legado `joinads_metrics`; hipótese H1 — filtro de PII do WEBS Wrapper v2 anula `utm_campaign` numérico desde o GTM v35 (15/10); pendente leitura L5/L6". Manter `partial`; **se L5 confirmar, promover a `risk`**.
3. **P06-T07** / **P16-T05**: registrar o defeito de filtro (sensor + wrapper) como lacuna do contrato de medição; correção depende de publicação GTM autorizada.
4. **P08-T07**: lacuna nova "índice `raw_events_dedup(sid,pid,event_name,ts_sec)` + `ignoreDuplicates` colapsa eventos de mesmo nome no mesmo segundo (ad views de slots distintos)"; DDL de `raw_events`, `fact_page_daily`, `compute_page_daily` não versionados.
5. **P06-T08** / **P10-T16** / **P09-T14**: registrar que `main` e a wip descrevem ledgers diferentes (v12_04/v17_01 vs v21) sem história comum; a decisão de autoridade precisa de L1/L7; o Code node canônico grava 0 para campanha sem linha de métrica (R3).
6. **P10-T04**: heartbeat JoinAds v2 inexistente (sem view de saúde) e nenhum coletor canônico com error workflow.
7. Curadoria (nós/arestas sugeridos, sem IDs sensíveis): `cap_revenue_ingestion` — acrescentar evidência "v2 append-only em wip, não integrada"; `concept:tracking_control_plane` — aresta de risco para `cap_attribution` ("filtro de PII anula campaign.id"); `volc::db:raw_events` — nota de dedup por segundo; `concept:google_ads_collection_ledger` — "duas implementações em históricos disjuntos".

## 10. Riscos registrados

| ID | Risco | Grau |
|---|---|---|
| R1 | Histórias disjuntas: integrar v21/JoinAds v2/economia em `main` exige renumerar `v21_*` e reconciliar dois ledgers Google | [D] |
| R2 | Filtro de PII anula `utm_campaign` numérico no sensor e no wrapper (§2.4) | [D] código; [H] efeito vivo |
| R3 | Zero inventado no coletor canônico Google para campanha sem linha de métrica | [I] |
| R4 | Dedup de `raw_events` por segundo colapsa eventos | [I] |
| R5 | Gatilho legado JoinAds: último domínio vence e custo 0 inserido em `daily_campaign_metrics` | [D] código; prod [H] |
| R6 | Núcleo econômico (wip) lê receita latest-wins, não a v2 append-only — replay `as_of` de receita impossível por ele | [D] |
| R7 | Nenhum coletor canônico com error workflow; falha pré-lote invisível no ledger | [D] doc |
| R8 | DDL de `raw_events`, `daily_campaign_metrics`, `gam_metrics`, `fact_page_daily` fora de qualquer ref: o schema real só é conhecível por leitura externa | [D] |
| R9 | Produção sem `supabase_migrations.schema_migrations`; "aplicada" é afirmação por inspeção | [D] doc |
