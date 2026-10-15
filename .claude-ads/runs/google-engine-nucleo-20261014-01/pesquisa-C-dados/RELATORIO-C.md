# Pesquisador C: dados, criativos e operação

Run `google-engine-nucleo-20261014-01` · verificação em 14/10/2026 · escopo: C01–C50 do inventário-semente, mais C51–C60 (itens novos encontrados na varredura da org `google-marketing-solutions`).

Neste trabalho não houve escrita no código VOLC, no `backend/.venv`, em credenciais, em chamadas autenticadas a Ads/Gemini/Supabase, em mutações ou em infraestrutura. Todo código de terceiros foi clonado em `scratchpad/C/clones/<repo>` (`--depth 1`, SHA em `experimentos/clones_sha_2026-10-14.txt`). Esse código só foi lido como texto. As únicas execuções de terceiros foram as bibliotecas do PyPI, em venvs isolados (`venv-gaarf`, `venv-sem`, `venv-compat`), rodando com `HOME` vazio e `-I`.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `resultados.json` | 60 itens com todos os campos pedidos |
| `queries/*-extraidas.sql` | GAQL verbatim, com origem `org/repo@SHA:arquivo:linhas` |
| `queries/conferencia_catalogo_v25.json` | 214 campos conferidos contra `volc_ads/google_ads_api/catalogo_gaql_v25.json`; **0 fora** |
| `queries/propostas-delta-volc.sql` e `queries/conferencia_propostas.json` | GAQL propostas para o VOLC, conferidas com `volc_ads.gads.catalogo.invalidos()`; **0 inválidos** |
| `experimentos/` | Scripts, saídas, logs de instalação, metadados de GitHub/PyPI, matriz de dry-run (`compat/`) |

Uma limitação vale para tudo o que segue: o catálogo v25 do VOLC diz se um campo é selecionável e filtrável, mas não traz `selectable_with`. A compatibilidade entre campo e recurso do FROM, para cada proposta, ainda precisa de `validate_only`, que fica com o pesquisador A.

## Resultado em uma tela

- Decisões: rejeitar 35, extrair padrão 12, reutilizar o existente 6, adiar por pré-requisito 3, sandbox dev 2, não verificável 2.
- Vereditos: 26 confirmadas, 12 parciais, 12 refutadas, 10 não verificáveis.
- O VOLC já tem quase tudo o que os blueprints propõem para dados. Coletor com catálogo, famílias e ledger; QS histórico; placements nas três views; ação de exclusão de placement; governança de negativas; leitura de política com `APPROVED_LIMITED` e `ELIGIBLE_MAY_SERVE`. As lacunas reais são **pontuais e baratas** (deltas abaixo). Nenhuma delas pede uma biblioteca nova.

## Achados de maior impacto

1. **gaarf/garf violaria o contrato NULL≠0 do coletor (provado).** Numa `GoogleAdsRow` v25 fabricada, sem `quality_score` e sem `impressions`, o parser do garf devolve `[0, 0, 0]`. O VOLC exige `None` (`contrato.py`; `keyword.py`: "0 não é nota"). Arquivo: `experimentos/exp_gaarf_null_vs_zero.out.json`.
2. **O pacote vivo não é `google-ads-api-report-fetcher`.** O último release dele é 1.18.3, de 04/02/2026. O código migrou para o monorepo `google/garf`, que publica `garf-core`, `-io`, `-executors` e `-google-ads`. O namespace `garf_google_ads` já emite `DeprecationWarning` e foi substituído por `garf.community.google.ads`. O `main` do garf ganhou **actors de mutação** (`Excluder`, `BudgetChanger`, `StatusChanger`), que ainda não estão no 1.2.1 do PyPI. Adotar o garf traria, a médio prazo, um **segundo caminho de escrita** paralelo a `volc_ads/gestao`.
3. **O consumidor de placements está desligado da coleta nova.** `volc_ads/coleta/familias/placement.py` grava detail, group e pmax em `google_ads_fato_granular_placement`, e a ação `ExcluirPlacements` existe. Mesmo assim, a sugestão de negativação da UI (`src/hooks/usePlacementNegation.ts` → `src/sql/get_placement_negation_suggestions.sql`) lê `vw_display_roi`, uma reconstrução do WEBGO que o próprio cabeçalho declara **sem pipeline de ingestão** (tabelas vazias). Nada lê os fatos coletados.
4. **Política: o VOLC lê o estado do anúncio, mas joga fora o porquê.** A GAQL de `estado.py` já seleciona `policy_topic_entries` inteiro. O normalizador `_topicos`, porém, guarda só `topic` e `type`, e descarta `constraints` (país, certificado, revendedor) e `evidences` (`destination_not_working` com HTTP/DNS, `destination_mismatch`, `text_list`). Isso custa zero de API. O extrator dessas estruturas já existe em `volc_ads/scripts/extrair_corpus_politica.py:152-200`.
5. **O dataset oficial do Transparency Center não cobre o Brasil.** Fonte: README oficial em `storage.googleapis.com/ads-transparency-center/api-data/README.txt`. As `region_stats` cobrem só "European Economic Area and Turkey", e o removed cobre só a EEA. Por isso a alegação C50 está refutada para o VOLC. Scraping, por sua vez, esbarra nos Termos do Google, que proíbem "automated means … in violation of the machine-readable instructions".
6. **"Negativar a intenção inteira" via embeddings está refutada no experimento.** Em 200 termos PT-BR rotulados, todo método produziu clusters que misturam termos "manter" e "negativar". O HDBSCAN sobre embeddings colapsou: ARI 0,005 no sklearn; no pacote, 53% dos termos ficaram como ruído. O 1-NN semi-supervisionado acertou 61% e marcou 9 de 176 termos valiosos como negativar. O projeto da própria Google para isso (`ml_toast`) está **arquivado**.
7. **Edge lander por clique (C20/C32) é risco de suspensão sem aviso.** As políticas aplicáveis são "Circumventing systems" (suspensão "upon detection and without prior warning"), "Destination requirements" ("Tracking template or expanded URL that don't lead to the same content", "primary purpose of showing ads") e AdSense ("pages published specifically for the purpose of showing ads").
8. **Conflitos de dependência concretos** (dry-run contra o freeze do backend): prefect 3.8.8 exige `fastapi>=0.139` (o backend tem 0.115.6); dagster 1.13.26 exige `protobuf<7` (o google-ads 33 usa 7.35.1); feast 0.67 exige `tenacity<9` (temos 9.1.4); bytewax não tem wheel para Python 3.13 nem 3.14 e o último release é de 11/2024. O LiteLLM teve as versões 1.82.7/1.82.8 comprometidas no PyPI em 24/03/2026 (fontes secundárias: Sonatype e OX Security).
9. O `topic-mine` está oficialmente **descontinuado** (o README diz "no longer actively maintained … No Security Updates"). O `ads-relevance-factory`/`arf` **não existe**: 404 nos dois nomes e nada equivalente nos 152 repositórios da org. O mais próximo é o ARBA.
10. Há um bug no `ads-monitor` (`collector_definitions/disapprovals.yaml:42,76`): `review_status` está mapeado para o campo `approval_status`. Não copie esse trecho.

## Refutado ou corrigido

| ID | Alegação | O que a fonte primária mostra |
|---|---|---|
| C05/C49 | ClickHouse + GAQL a cada 15–30 min | Supabase é a autoridade única; existe gate de agenda única; o volume é de milhares de linhas por dia (3.605 linhas no D-1 de 1 conta, registro de 08/10) |
| C07/C10 | Redis/Ray para "lance por minuto em milhares de contas" | Não há lance por chamada (Smart Bidding); o motor opera 1 conta |
| C11 | Bytewax | Sem wheel para cp313/cp314; parado desde 11/2024 |
| C16 | Negativar o cluster inteiro | Experimento: clusters mistos em todas as variantes |
| C17 | "Nasce pré-otimizada" | Não há receita por criativo nem por termo (v17_04: receita não atribuída a placement) |
| C20/C32 | Edge lander dinâmico | Cloaking/mismatch; suspensão egregious |
| C25 | gaarf "direto para Polars/DuckDB/ClickHouse" | Writers: CSV/JSON/BQ/SQL/Sheets (+ `duckdb_executor` no garf-executors); pacote em migração para garf |
| C27 | ads-relevance-factory | Não existe |
| C31 | Feeds System1/Tonic/Sedo/AFD | Não fazem parte do VOLC; o AFD foi removido da rede de parceiros, segundo fontes secundárias |
| C39 | topic-mine | Descontinuado |
| C50 | Dataset oficial como alternativa | Só EEA/Turquia |

## Policy (2b): o que o VOLC lê e o que falta

O que o VOLC já lê:
- `ad_group_ad`: `policy_summary.{approval_status, review_status, policy_topic_entries}` e `primary_status(_reasons)`, sem janela de data. Isso é melhor que o ads-policy-monitor, que usa `segments.date DURING LAST_30_DAYS` junto com métricas e corre o risco de omitir reprovados sem impressão. A confirmação desse risco fica com A.
- `asset_group_asset`: `policy_summary.*` e primary status.
- `keyword`: `approval_status` e primary status.
- `campaign_asset`: só primary status.
- PMax: `asset.policy_summary.approval_status` e `topic_entries` (`observabilidade_pmax/queries.py`).
- Sentinela e diagnóstico tratam `APPROVED_LIMITED` como não verde, e `REVIEW_IN_PROGRESS`, `UNDER_APPEAL` e `ELIGIBLE_MAY_SERVE` como "em revisão".

Campos que o VOLC **não lê hoje**. Todos estão no catálogo v25 e são selecionáveis.

| Campo | Melhora a detecção de |
|---|---|
| `policy_topic_entries[].constraints` (já vem; o normalizador descarta) | Aprovado-limitado: em quais países e por qual certificado |
| `policy_topic_entries[].evidences` (já vem; o normalizador descarta) | Reprovação por destino: `destination_not_working` (lander fora do ar), `destination_mismatch`, texto apontado |
| `asset.policy_summary.{approval_status, review_status, policy_topic_entries}` via `campaign_asset` | Problemas de assets de campanha (sitelink, callout, imagem) em Search/Display/DG |
| `ad_group_ad_asset_view.policy_summary` | Título ou descrição reprovada dentro de RSA, RDA ou Demand Gen (deixa o anúncio limitado). Hoje a família `asset` só vê asset com impressão > 0 |
| `ad_group_asset.*` e `customer_asset.*` (`primary_status`, `_reasons`, `_details`) + `asset.policy_summary.*` | Assets de grupo e de conta |
| `campaign_asset.primary_status_details` | Motivo detalhado (PMax já lê em `observabilidade_pmax`; a coleta `estado` não) |
| `ad_group_criterion.disapproval_reasons`, `ad_group_criterion.system_serving_status` | Keyword reprovada (motivo) e `RARELY_SERVED` |
| `asset_group_signal.approval_status`, `asset_group_signal.disapproval_reasons` | Tema de pesquisa ou sinal PMax reprovado |
| `asset.field_type_policy_summaries` | Política por tipo de campo de um asset reaproveitado (não usado por nenhum projeto Google lido; prioridade baixa) |

Isto é política **observada no Google**. Nenhuma proposta cria proibição por palavra.

## Placements (2d): o que existe e a lacuna

O que já existe:
- Coleta diária de `detail_placement_view`, `group_placement_view` e `performance_max_placement_view`. A view PMax tem só impressões, como medido em 08/10 e confirmado pelo pMaximizer.
- Partição `google_ads_fato_granular_placement`.
- View `vw_gads_arbitragem_placement_dia`, com custo por domínio e receita **NULL** por desenho.
- Ação `ExcluirPlacements` (campanha ou conta; site, app, canal e vídeo do YouTube) e listas `NEGATIVE_PLACEMENTS` em `volc_ads/gestao/acoes.py`.
- Nota de PMax: exclusão de campanha é recusada (`campanha/pmax_config.py:31`).

Lacunas:
1. Nenhum leitor dos fatos coletados. A UI lê a view legada vazia.
2. Falta `campaign.advertising_channel_type` na linha. Dá para resolver por junção com o inventário, sem custo de API.
3. Faltam métricas de vídeo para canais do YouTube (`video_trueview_views`, quartis), como no video-exclusion-toolbox.
4. Faltam as guardas do Ads Placement Guardian:
   - `youtube.com`, `mail.google.com` e `adsenseformobileapps.com` não são excluíveis;
   - PMax só aceita exclusão na conta;
   - `mobileapp::2-com.x` precisa virar `2-com.x`. O regex de app em `acoes.py` recusaria o formato cru coletado.
5. Content suitability views (`group_`/`detail_content_suitability_placement_view`) existem no catálogo e não são coletadas. A conferência via API fica com A.
6. Não existe receita por placement de origem, então a regra "ROAS negativo" não tem dado no VOLC. A regra possível hoje é custo/conversão do Google sem receita.

Queries Google de referência: `queries/placements-extraidas.sql` (APG, VET, pMaximizer).

## Deltas acionáveis para o integrador

São no máximo 6, todos somente leitura, sem dependência nova. Cada GAQL passa antes por `validate_only` (A).

**D1. Preservar `constraints` e `evidences` dos tópicos de política.**
- Alvo: `volc_ads/coleta/familias/estado.py:_topicos` (linhas 107-108).
- Fazer: reaproveitar `_evidencia` e `_restricao` de `volc_ads/scripts/extrair_corpus_politica.py:152-200`.
- Custo: zero de API e sem migration (`topicos_politica` é jsonb array; CHECK só exige array).
- Efeito colateral: muda o `estado_hash` (v17_01:464-468) e gera uma reinserção única das linhas com tópico.
- Consumidores que ganham: `backend/app/trafego/sentinela.py` e `diagnostico_persistido.py` (alarme de lander fora do ar por `destination_not_working`; país do limitado).

**D2. Política do asset em `campaign_asset`.**
- Alvo: `estado.py` `GAQLS["campaign_asset"]` + `normalizar`.
- Fazer: acrescentar `asset.policy_summary.{approval_status, review_status, policy_topic_entries}` e `campaign_asset.primary_status_details`, e preencher `aprovacao`, `revisao` e `topicos` (hoje ficam `None` para `campaign_asset`).
- Sem migration: o `entidade_tipo` já é permitido.
- GAQL pronta: `queries/propostas-delta-volc.sql` P3. Padrão Google: `ads-policy-monitor@7d313aea:…/campaign_asset.sql:14-34`.

**D3. Leitor de placements sobre a coleta nova, com guardas do APG.**
- Alvos: (a) função de proposta, somente leitura, sobre `google_ads_fato_granular_placement` em `backend/app/trafego/` (ou reapontar `src/sql/get_placement_negation_suggestions.sql`, hoje preso a `vw_display_roi` vazia); (b) guardas em `volc_ads/gestao/acoes.py`.
- Guardas: lista não-excluível, `escopo="campanha"` recusado para PMax antes de ir à API, normalização `mobileapp::` para `[12]-`.
- Fontes: `ads_placement_guardian@294c4c37:…/entities.py:44-72` e `placement_excluder.py:143,420-430,670-685`. Recorte YouTube: `video-exclusion-toolbox@97d54487:src/gads_channel_report_fetcher/main.py:86-110`.
- Limite: a proposta não executa exclusão; mutação não está autorizada.

**D4. Novas entidades de política: precisam de migration.**
- Entidades: `ad_group_ad_asset_view.policy_summary` (asset dentro de RSA/DG), `ad_group_asset`, `customer_asset`, `asset_group_signal` (`approval_status`, `disapproval_reasons`), mais `ad_group_criterion.disapproval_reasons` e `system_serving_status`.
- Bloqueio: o CHECK `google_ads_estado_tipo` (v17_01:259-260) só aceita 7 tipos, e `system_serving_status` não tem coluna. Migration **não autorizada** nesta missão, então isto fica como item de roadmap com GAQL pronta (`propostas-delta-volc.sql` P1, P2, P4, P5).
- Padrão Google sem `segments.date`: `ads-monitor@5e483028:…/disapprovals.yaml:28-52`.

**D5. Negativas de lista compartilhada na governança.**
- Alvo: `volc_ads/inteligencia_search/governanca.py:_mesmo_escopo`/`conflitos_de_negativa` e o montador de `observacao["negatives"]` em `volc_ads/inteligencia_decisao/pipeline.py:343`.
- Fazer: aceitar o nível `SHARED_SET` resolvido por `campaign_shared_set`.
- Hoje só `CAMPAIGN` e `AD_GROUP` entram, então uma negativa de lista que bloqueia termo valioso passa despercebida.
- Query de referência: `negative_keyword_cleaner@e3443326:src/utils/gaarf_queries.py:155-172`.

**D6. Não promover gaarf, garf nem bibliotecas de dados ou semântica.**
- Registrar no inventário: garf é extrair padrão; Polars, DuckDB, ClickHouse, Prefect, Dagster, Ray, Bytewax, Feast, LiteLLM, BERTopic, sentence-transformers e Qdrant são rejeitados.
- Motivos: cada um quebra NULL≠0, a agenda única, a autoridade do Supabase ou o resolver (ver a matriz).
- Únicas adições aceitáveis, e só em dev: `respx` e `schemathesis` (sandbox).

## Matriz de compatibilidade

Método: `pip install --dry-run --ignore-installed -c backend_freeze.txt <pacote>` em venv Python 3.14.6 separado, ou seja, sem mudar nenhum pin atual. Os pins incluem google-ads 33.0.0, protobuf 7.35.1, grpcio 1.83.0, pydantic 2.13.4, httpx 0.28.1, websockets 16.1.1, fastapi 0.115.6 e tenacity 9.1.4. Detalhe em `experimentos/compat/`.

| Candidato (versão PyPI 14/10) | Resolver com o freeze | Pacotes novos | Observação |
|---|---|---|---|
| google-ads-api-report-fetcher 1.18.3 | OK | 31 | otel, redis, typer, psutil, jwt |
| garf-google-ads 1.2.1 | OK | 18 | traz pandas 3.0.6 + numpy 2.5.4 |
| garf-core 1.3.3 / io 1.5.1 / executors 1.7.0.post1 | OK | 9 / 15 / 30 | `redis` é dependência obrigatória do core |
| polars 2.0.0 | OK | 2 | meta-pacote + polars-runtime-32 |
| duckdb 1.5.6 | OK | 1 | wheel cp314 |
| clickhouse-connect 1.10.1 | OK | 2 | precisa de servidor |
| feast 0.67.0 | **FALHA** | — | `tenacity<9` vs 9.1.4; fallback tenta build de pyarrow e quebra |
| redis 8.1.0 | OK | 1 | precisa de servidor |
| prefect 3.8.8 | **FALHA** | — | `fastapi>=0.139.0` vs 0.115.6 (sem pin cai para prefect 1.4.1) |
| dagster 1.13.26 | **FALHA** | — | `protobuf<7` vs 7.35.1 (sem pin cai para 1.5.13 com sdist) |
| ray 2.59.0 | OK | 8 | — |
| bytewax 0.21.1 | **FALHA** | — | sem wheel cp313/cp314 |
| sentence-transformers 6.1.0 | OK | 30 | torch 2.14.1, transformers 5.19 |
| bertopic 0.17.4 | OK | 40 | torch, numba, umap, plotly |
| hdbscan 0.8.44 | OK | 8 | desnecessário: `sklearn.cluster.HDBSCAN` |
| fastembed 0.9.0 | OK | 13 | onnxruntime 1.31; venv 357 MB; modelo 240 MB |
| qdrant-client 1.19.1 | OK | 6 | precisa de servidor |
| litellm 1.105.1 | OK | 37 | histórico de supply-chain (1.82.7/8) |
| crawlee 1.10.4 / playwright 1.64.0 | OK | 15 / 3 | navegadores baixados à parte |
| ipinfo 5.6.0 / geoip2 5.3.0 | OK | 10 / 10 | aiohttp |
| schemathesis 4.31.1 | OK | 11 | dev |
| respx 0.23.1 | OK | 1 | dev |
| opentelemetry-sdk 1.45.1 | OK | 3 | sem coletor |
| facebook-business 26.0.2 | OK | 13 | licença própria da Meta |
| pandas 3.0.6 | OK | 4 | — |
| fastapi 0.143.1 / websockets 17.2 / pydantic 2.14.1 | conflito com pin | — | upgrade, não adição; fora de escopo |

Outras verificações de ambiente:
- `backend/.venv/bin/python -I -m pip check`: "No broken requirements found".
- O `backend/requirements-dev.txt` declara `psycopg[binary]>=3.1`, mas o freeze do `backend/.venv` **não tem psycopg**. O venv está fora de sincronia com o arquivo de requisitos, e o `pip check` não pega isso (ver o comentário do próprio arquivo sobre os 37 testes que somem).

## Experimentos (reprodutíveis)

1. **`exp_gaarf_parse_sem_credencial.py`** (`venv-gaarf`, 24 s de instalação, 365 MB).
   - Faz o parse da query de política com `{{ today }}` e `:topic` e da query de placement com macro `:YYYYMMDD-7`, gerando GAQL final, colunas e customizers.
   - Os 11 campos estão no catálogo v25.
   - Uma linha fabricada com `APPROVED_LIMITED` e `constraint` foi parseada para `['TRADEMARKS_IN_AD_TEXT']`, ou seja, perdeu `type` e `constraint`.
   - O cliente nunca foi criado; `HOME` estava vazio.
2. **`exp_gaarf_null_vs_zero.py`**: campos ausentes viram `0` (achado 1).
3. **`exp_semantica_fastembed_hdbscan.py`** (`venv-sem`, 13 s de instalação, 357 MB; modelo 240 MB baixado do HF Hub sem token).
   - Saída em `.out.json`; achado 6.
   - Baseline TF-IDF char + HDBSCAN: ARI 0,237, 37% de ruído, 2 clusters mistos.
4. **`extrair_queries.py`**: extração verbatim e conferência (214 campos, 0 ausentes).
5. Os experimentos de Polars e DuckDB com 1M de linhas **não foram feitos**: não há uso concreto, e a autoridade é o Postgres.

## Fontes primárias consultadas

- GitHub API (metadados: `experimentos/github_metadados_2026-10-14.jsonl`).
- PyPI JSON (`experimentos/pypi_metadados_2026-10-14.txt`).
- Clones nos SHAs registrados.
- Políticas Google: support.google.com/adspolicy/answer/6020954 e answer/6368661; support.google.com/adsense/answer/48182; policies.google.com/terms.
- README oficial do dataset do Transparency Center.
- ipinfo.io/lite; maxmind.com/en/geolite2/eula.

Fontes secundárias, sinalizadas como tal nos itens: incidente do LiteLLM (Sonatype, OX Security); AFD e RSOC (ppc.land, searchengineland, domainnamewire).
