# Pautador Pro — Extração dos workflows n8n (KW Mining + Funnel Builder)

Relatório de engenharia reversa dos dois workflows n8n e do mapeamento 1:1 para
o backend FastAPI/Python multiagent. **A porta de entrada deixou de ser o ClickUp**
— agora é o card do Pautador Pro (Supabase + UI). Todos os nós ClickUp foram
**ignorados** (eram apenas leitura/escrita de tarefa).

Fontes:
- `n8n-peneirador-kw.json` → Minerador de Palavras (Fase 2)
- `n8n-funnel-builder.json` → Construtor de Funis (Fase 3)

Endpoints conectados aos botões da UI:
- `POST /api/pautador/opportunities/{id}/mine`   → botão **Minerar**
- `POST /api/pautador/opportunities/{id}/funnel`  → botão **Funil**

---

## 1. Peneirador / KW Research (`n8n-peneirador-kw.json`)

### 1.1 Sequência dos nós úteis (ClickUp ignorado)

| # | Nó n8n | Papel | Implementação Python |
|---|--------|-------|----------------------|
| — | `Get a task4`, `Set a custom Field…`, `Get a task5` | **ClickUp — IGNORADO** (porta de entrada) | — (entrada = card do Pautador) |
| 1 | `Geo + Language Mapper1` | país → geo_target / language_code / language_constant | `app/agents/mining/geo.py` (`GeoLanguageMapper`, `GEO_MAPPING_BY_NAME`) |
| 2 | `⚙️ Config Global1` | monta config (nicho, geo, idioma, max_loops, min_volume_gold) | montado em `MiningOrchestrator.run` |
| 3 | `🧠 AI Seed Optimizer1` + `Gemini 2.5 Flash1` + `Structured Output Parser1` | LLM gera 3–5 seeds | prompt em `app/n8n_prompts/kw_seed_optimizer.py`; chamada em `MiningOrchestrator._seed_optimizer` |
| 4 | `🌱 Seed Queue Builder1` | parse/dedup/rank das seeds | `app/agents/mining/seed_queue.py` (`parse_seed_optimizer_output`) |
| 5 | `🔁 Loop Seeds1` + `🔍 Keyword Planner API1` | loop por seed chamando Google Ads | `app/services/google_ads.py` + `MiningOrchestrator._keyword_planner` |
| 6 | `⛏️ Gold Extractor1` | extrai métricas, atualiza master_bank, decide próximo seed | `app/agents/mining/gold_extractor.py` (`extract_gold`, `normalize_seed`) |
| 7 | `🔄 Mais Ouro?1` + `🔄 Prep Next Loop1` + `⏳ Sleep 15s` | controle do loop | embutido no loop de `_keyword_planner` (sleep só no modo `live`) |
| 8 | `🏆 Final Classifier1` | consolida master_banks → build_queue + validation_keywords | `app/agents/mining/merger.py` (`final_classifier`) |
| 9 | `🪄 Prepare Validation Seeds` | monta validation_queue | passthrough no orchestrator |
| 10 | `🔮 Google Autocomplete2` + `Extract Autocomplete2` | DataForSEO autocomplete | `app/services/dataforseo.py` (`DataForSeoClient.autocomplete`, `extract_autocomplete`) |
| 11 | `🧠 Related Keywords Labs2` + `Extract Related KW2` | DataForSEO related keywords | `DataForSeoClient.related_keywords`, `extract_related` |
| 12 | `🔀 Merge All Sources2` + `🔥 Mega Merger2` | merge das 3 fontes | `app/agents/mining/merger.py` (`mega_merge`) |
| 13 | `Code in JavaScript6` (🏆 GOLD MINER V11) | classifica em ADS + CONTEÚDO (time-warp, trend, sazonal) | `app/agents/mining/classifier.py` (`gold_miner_classify`) |
| 14 | `VOLC Funnel Prospector v2` + `Google Gemini Chat Model3` | LLM agrupa em temas-pai (funis) | prompt em `app/n8n_prompts/kw_funnel_prospector.py`; `MiningOrchestrator._funnel_prospector` |
| 15 | `🏭 FUNNEL FACTORY` | fila de produção por funil (normalização de datas, dedup) | `app/agents/mining/funnel_factory.py` (`funnel_factory`) |

> **Melhoria intencional sobre a fiação literal do n8n:** no n8n o Gold Miner classifica
> apenas o Mega Merge (autocomplete + related), descartando o `build_queue` do Google Ads.
> O orchestrator **une** o `build_queue` às keywords classificadas
> (`MiningOrchestrator._union_keywords`) para não perder a fonte primária (Keyword Planner).

### 1.2 Modelos / serviços externos

- Gemini: **`models/gemini-3.1-pro-preview`** (seed optimizer + funnel prospector) — env `PAUTADOR_KW_GEMINI_MODEL`.
- Perplexity `sonar-pro`: era *tool* opcional dos agentes; disponível via `app/llm/perplexity.py` (não chamado ativamente na mineração).
- Google Ads Keyword Planner API (`generateKeywordIdeas`, v21).
- DataForSEO: `serp/google/autocomplete/live/advanced` + `dataforseo_labs/google/related_keywords/live`.

### 1.3 Credenciais hardcoded migradas para `.env` (NUNCA copiadas para código)

O JSON do n8n continha **segredos hardcoded** — todos migrados para variáveis de ambiente,
deixados **vazios** em `.env`/`.env.example` para o operador preencher:

| Origem no n8n | Variável `.env` |
|---|---|
| `developer_token` / `mcc_id` / `customer_id` (Config Global) | `GOOGLE_ADS_DEVELOPER_TOKEN` / `GOOGLE_ADS_LOGIN_CUSTOMER_ID` / `GOOGLE_ADS_CUSTOMER_ID` |
| OAuth Google Ads | `GOOGLE_ADS_CLIENT_ID` / `GOOGLE_ADS_CLIENT_SECRET` / `GOOGLE_ADS_REFRESH_TOKEN` |
| Header `Authorization: Basic …` (DataForSEO) | `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` |

Sem essas credenciais, o pipeline roda em **MOCK determinístico** (`app/agents/mining/mocks.py`),
de ponta a ponta, claramente sinalizado em `services_used` (`google_ads:mock`, `dataforseo:mock`).

### 1.4 Schema de saída (rota `/mine`)

```jsonc
{
  "opportunity_id": 0,
  "cluster": { "cluster_name", "main_keyword", "intent", "keywords": [...], "total_volume", "avg_cpc_local", "currency" },
  "summary": { "ads_approved", "content_ideas", "breakdown", "year_context" },
  "production_ads_queue": [ { "keyword", "volume", "cpc", "competition", "tags", "reason" } ],
  "content_seo_queue":   [ { "keyword", ... } ],
  "funis_sugeridos":     [ { "rank", "nome_funil", "keyword_ancora", "sub_intencoes", "metricas" } ],
  "factory_output":      [ { "project_name", "funnel_context", "keywords_campanha", ... } ],
  "metrics", "services_used", "engine", "persisted", "warnings"
}
```

---

## 2. Funnel Builder (`n8n-funnel-builder.json`)

### 2.1 Sequência dos nós úteis

| # | Nó n8n | Papel | Implementação Python |
|---|--------|-------|----------------------|
| 1 | `AI Agent1` + `Google Gemini Chat Model1` + `Think1` + `Message a model in Perplexity1` | Arquiteto-chefe gera `{funnel_strategy, pages}` | prompt em `app/n8n_prompts/funnel_builder.py`; `FunnelProOrchestrator.run` |
| 2 | `Code in JavaScript` (🏭 PAGE FACTORY V4) | gera `writingJobs` (briefing por página) | `app/agents/funnel_pro/page_factory.py` (`page_factory`) |

- Modelo: **`models/gemini-3.1-pro-preview`** — env `PAUTADOR_FUNNEL_GEMINI_MODEL`.
- Perplexity `sonar-pro`: tool opcional (não obrigatório).
- Sem Gemini configurado → **fallback determinístico** de 5 páginas (`FunnelProOrchestrator._fallback_architect`).

### 2.2 Entrada / Guard "minere antes"

A rota `/funnel` exige **supporting_data** (keywords mineradas):
- card persistido (DB): exige cluster prévio; sem cluster → **HTTP 409** "Minere a oportunidade antes de gerar o funil".
- card efêmero (dry): aceita o cluster inline no corpo (`cluster`), ou cai para os dados da própria oportunidade.

### 2.3 Schema de saída (rota `/funnel`)

```jsonc
{
  "opportunity_id": 0,
  "funnel": { "funnel_name", "pages": [ { "position", "page_title", "avatar", "stage", "emotional_goal", "subtitles", "internal_links" } ] },
  "funnel_strategy": { "avatar_summary", "tone_voice", "total_pages" },
  "writing_jobs": [ { "job_id", "page_type", "writer_briefing": { "headline", "skeleton", "cta_link", "keywords", ... } } ],
  "services_used", "persisted", "warnings"
}
```

---

## 3. Prompts preservados (ipsis litteris)

| Prompt | Arquivo | Origem n8n |
|---|---|---|
| Seed Optimizer (system + schema) | `app/n8n_prompts/kw_seed_optimizer.py` | `🧠 AI Seed Optimizer1` + `Structured Output Parser1` |
| VOLC Funnel Prospector (system + user) | `app/n8n_prompts/kw_funnel_prospector.py` | `VOLC Funnel Prospector v2` |
| Funnel Architect (system + mission + output_rules) | `app/n8n_prompts/funnel_builder.py` | `AI Agent1` |

Adaptações: apenas as expressões n8n (`{{ $json.* }}`, `{{ $('Config Global1')… }}`) foram
trocadas por placeholders `__TOKEN__` injetados pelos helpers `build_*`. O corpo semântico é
verbatim (apenas espaços de quebra-de-linha markdown cosméticos foram normalizados).

> O prompt de descoberta (Fase 1, `GOD_MODE`) continua em `app/prompts.py` — **intocado**.
> Os prompts novos vivem no pacote separado `app/n8n_prompts/` para evitar colisão de nome
> e não arriscar a descoberta que já funciona.

---

## 4. Tabelas Supabase afetadas

Migração incremental: `src/sql/v7_02_pautador_kw_funnel_outputs.sql` (aditiva, idempotente).

- `pautador_keyword_clusters` (+ colunas JSONB): `raw_keywords`, `production_ads_queue`,
  `content_seo_queue`, `funis_sugeridos`, `factory_output`, `summary`, `metrics`,
  `services_used`, `warnings`, `engine`. A coluna `keywords` (v7_01) segue sendo o cluster compacto.
- `pautador_funnels` (+ colunas JSONB, denormalizadas por página): `strategy`, `pages`,
  `writing_jobs`, `raw_output`, `services_used`, `warnings`.

---

## 5. Variáveis de ambiente (resumo)

```env
PAUTADOR_KW_GEMINI_MODEL=models/gemini-3.1-pro-preview
PAUTADOR_FUNNEL_GEMINI_MODEL=models/gemini-3.1-pro-preview
PAUTADOR_KW_ENGINE=auto            # auto|mock|live
PAUTADOR_KW_MAX_LOOPS=5
PAUTADOR_KW_MIN_VOLUME_GOLD=10
PERPLEXITY_API_KEY=                # opcional
DATAFORSEO_LOGIN=                  # vazio => mock
DATAFORSEO_PASSWORD=

# Google Ads — DOIS modos de auth (service_account | oauth_refresh_token | auto)
GOOGLE_ADS_AUTH_MODE=auto
GOOGLE_ADS_DEVELOPER_TOKEN=        # comum aos 2 modos (obrigatório)
GOOGLE_ADS_LOGIN_CUSTOMER_ID=      # comum (obrigatório)
GOOGLE_ADS_CUSTOMER_ID=            # comum (obrigatório)
# modo oauth_refresh_token:
GOOGLE_ADS_CLIENT_ID=
GOOGLE_ADS_CLIENT_SECRET=
GOOGLE_ADS_REFRESH_TOKEN=
# modo service_account (JSON inline OU caminho; se setado, refresh token NÃO é exigido):
GOOGLE_ADS_SERVICE_ACCOUNT_JSON=
GOOGLE_ADS_JSON_KEY_FILE_PATH=
GOOGLE_ADS_IMPERSONATED_EMAIL=     # opcional (domain-wide delegation)
```

**Auth Google Ads (dual)** — `Settings.google_ads_auth_status()` resolve o modo e a prontidão
sem expor segredos (`{mode, ready, missing[]}`), exposto em `GET /api/pautador/health`.
`service_account` assina um JWT RS256 (`app/services/google_ads.py`, via `cryptography`) e troca
por access token; `oauth_refresh_token` usa o refresh flow. Sem modo completo → **mock + warning**
claro (modo + chaves faltantes). `cryptography` só é importado no modo service_account.

Todas server-side. **Nada de Gemini/Perplexity/DataForSEO/Google Ads/service-role no frontend.**

---

## 6. Mapa de arquivos

```
backend/app/n8n_prompts/        kw_seed_optimizer.py, kw_funnel_prospector.py, funnel_builder.py (+ __init__)
backend/app/services/           dataforseo.py, google_ads.py
backend/app/agents/mining/      geo.py, seed_queue.py, gold_extractor.py, merger.py,
                                classifier.py, funnel_factory.py, mocks.py, orchestrator.py
backend/app/agents/funnel_pro/  page_factory.py, orchestrator.py
backend/tests/                  test_mining_pipeline.py, test_api_kw_funnel.py
src/sql/                        v7_02_pautador_kw_funnel_outputs.sql
```
