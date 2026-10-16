# Classificação do catálogo na base real — VOLC Data Intelligence Lab

**Worker:** A (auditor de arquitetura e dados, somente leitura no código)
**Data:** 2026-10-15 (noite) · **Worktree:** `worktrees/data-intelligence-overnight-20261015`
**Base auditada:** branch `lab/data-intelligence-overnight-20261015`; base de produto `104bb0d0` (o lab acrescentou `bef4c0da` e `c1903d5f`, só no namespace do lab).
**Catálogo:** `~/Downloads/CATALOGO-DATA-INTELLIGENCE-ENGINES-VOLC-20261015.md` (D01–D53, X01–X10), lido inteiro.
**Produção acessada:** não. Nenhum `.env`, SSH, Supabase, n8n ou API externa.

## 0. Como ler

Classes (estado **na base desta worktree**, não no catálogo):

| Classe | Significado |
|---|---|
| `existente` | código/artefato presente nesta base com alguma prova |
| `parcial` | há componentes nesta base (código, pesquisa, fixture), mas falta integração, dado real ou prova |
| `novo` | nada equivalente nesta base |
| `outra frente` | pertence a uma task/missão de outro dono (Roadmap ou branch `wip/*`); o lab não duplica |
| `hold` | pesquisar/referência; não implementar agora |
| `rejeitado` | rejeitado nesta fase |

Coluna "Lab?": `sim` (o lab desta missão faz algo, sempre hermético/sintético salvo nota), `não`, `só handoff` (o lab só registra contrato/lacuna para o curador).

Fontes de autoridade consultadas, nesta ordem: `docs/volc-os-graph/curadoria-operacional.json` (autoridade 1), `docs/volc-os-graph/volc-os-graph.json` (snapshot gerado, `curadoria_atualizada_em: 2026-10-15`), `volc-os-workbook/ROADMAP-VIVO.json` (`updated_at: 2026-10-15`), depois código/SQL/docs.

**Limite do grafo (demonstrado):** `graphify-out/` e `.graphify-cache/` **não existem nesta worktree** (são gitignored, `.gitignore:86`), portanto `graphify-out/graph.json` não pôde ser consultado; usei o snapshot operacional versionado `docs/volc-os-graph/volc-os-graph.json` (496 nós, 757 arestas). `scripts/atualizar_grafo_volc_os.py --check` deu `current: true` na baseline (input `9e9ecd08…`); rodado de novo agora (somente `--check`) deu `current: false`, `current_commit c1903d5f`, `input_file_count 2615` (eram 2603): a mudança são os arquivos do próprio lab, não da base de produto. Rebuild fica com o integrador.

## 1. Tabela-resumo

| ID | Capacidade | Catálogo | **Base real** | Roadmap (estado atual) | Lab? |
|---|---|---|---|---|---|
| D01 | Ledger canônico Google Ads | P / Outra frente | **outra frente** (base tem v12_04+v17_01; o "v21" do catálogo só existe em `wip/*`) | P06-T08 partial · P09-T14 partial · P10-T16 partial | não |
| D02 | Cobertura máxima Google Ads API | P / Outra frente | **outra frente** | P05-T07 partial · P05-T08 partial · P09-T14 partial | não |
| D03 | Ledger publisher/JoinAds | P / Outra frente | **outra frente** (base só tem o legado upsert; v2 canônico só em `wip/historico-joinads-20261015`) | P06-T03 partial · P06-T05 partial | só handoff |
| D04 | Núcleo econômico determinístico | E/P | **outra frente — ausente na base** (`volc_ads/economia/` só em `wip/*`, 043c77f5) | P06-T02/T03/T04 partial; P06-T09 **não existe** no Roadmap desta base | só handoff |
| D05 | `value_kind` universal | N | **novo** (precedente de 3 valores em SPEC-DATA-MANAGER) | P06-T03/T04 partial · P09-T10 todo · P14-T02 partial | sim (já no contrato do lab) |
| D06 | Identidade campanha→funil→URL→jornada | P / Outra frente | **outra frente** (parcial na base) | P08-T02 partial · P08-T07 partial · P08-T03 todo | só handoff |
| D07 | Snapshot econômico `as_of` | N | **parcial** (as-of existe em `services/orakul_predictive` e no normalizador, sintético) | P09-T09 todo · P09-T10 todo · P14-T02 partial | sim |
| D08 | Reconciliação e restatement | P | **parcial** (v17_04 escrita, v23_01 PROPOSTA; nenhuma aplicada segundo o Roadmap) | P06-T03/T04/T05 partial | sim (só cenários) |
| D09 | Data-quality e deadman | P / Outra frente | **outra frente** (deadman Google existe) | P06-T05/T06 partial · P10-T16 partial | não |
| D10 | Lineage/registry de pipelines | P | **outra frente** | P10-T06 partial · P10-T01 done | não |
| D11 | DuckDB | N | **parcial** (já no Freedom Lab e usado no shadow Senac) | P14-T02 partial · P10-T24 partial | sim (bancada) |
| D12 | Polars | N | **parcial** (no lock do Freedom Lab, sem consumidor; versão diverge do lab) | idem | sim (bancada) |
| D13 | Replay `as_of` realista | P | **parcial** (3 replays distintos, nenhum econômico temporal com dado real) | P09-T09 todo · P14-T02 partial | sim |
| D14 | Maturação/nowcasting | N | **parcial** (só pesquisa sintética prévia: E2 chain-ladder/BF) | P06-T03 partial · P09-T10 todo | sim (reusar E2 como baseline) |
| D15 | Shrinkage/Empirical Bayes | N | **parcial** (E1 sintético; prior encolhido em `familias_rpm.json`, não decisório) | P09-T10/T11 todo | sim |
| D16 | Confidence sequences | N/H | **novo** | P05-T09 partial · P09-T09 todo | sim (sintético) |
| D17 | FDR / múltiplas comparações | N | **novo** | P09-T09 todo | sim (sintético) |
| D18 | Curvas marginais | N/H | **novo**; com dado real **não identificável** hoje | P09-T10/T11 todo | sim (só sintético) |
| D19 | Risco/downside | N/H | **novo** (Mean-CVaR como objetivo já refutado em pesquisa) | P09-T10/T11 todo | sim (só métricas de replay) |
| D20 | Causalidade/incrementalidade | H | **hold / outra frente** (trilha P15/Meridian) | P15-T09 todo · P15-T01 done | não |
| D21 | Successive Halving/ASHA | N | **novo** | P05-T09 partial · P09-T11 todo · P14-T02 partial | sim (sintético) |
| D22 | Surrogate index | N/H | **novo**; real = **não identificável** (sessão) / **dados insuficientes** (campanha×dia) | P06-T03 · P08-T07 partial · P09-T10 todo | sim (viabilidade + sintético) |
| D23 | Gradient boosting | H | **hold** | — | não |
| D24 | Contextual/factorial bandit | N/H | **parcial** (só pesquisa: OPE E3, smoke E4) | P09-T11/T13 todo | sim (sintético) |
| D25 | Budget-ROI Allocator | Especificado | **novo** (só SPEC) | P09-T10..T13 todo | sim (A0/A1 sintético) |
| D26 | Otimização com restrições | H | **hold** (OR-Tools já no lock do Freedom Lab) | P09-T10..T12 todo | não |
| D27 | Swarm experimental design | N/H | **novo** | P05-T09 · P09-T09 · P14-T02 | sim (schema + gerador) |
| D28 | Três relógios de decisão | N/H | **novo** (os relógios de coleta existem, o modelo não) | P06-T05 · P09-T14 · P14-T02 | sim (só modelagem) |
| D29 | ExperimentService/ortogonais | H | **hold / outra frente** | P05-T10 partial · P09-T09 todo | não |
| D30 | PMax como onda posterior | H | **hold** (observabilidade PMax existe) | P05-T07 · P09-T09 | não |
| D31 | Diagnóstico de não entrega | P / Outra frente | **outra frente** | P05-T07 partial | não |
| D32 | Search terms/negativas | P / Outra frente | **outra frente** | P05-T08 partial | não |
| D33 | Clustering semântico | N/H | **hold** (pesquisa prévia refutou "negativar o cluster") | P05-T08 partial | não |
| D34 | pgvector | H | **hold** | — | não |
| D35 | Guardião das 72h | N/P | **outra frente** (parcial na base) | P05-T09 partial | não |
| D36 | Evolução RSA | P / Outra frente | **outra frente** | P05-T10 partial | não |
| D37 | Policy monitor | N/H | **outra frente** (parcial: família `estado` coleta política) | P05-T07 · P05-T10 · P06-T06 | não |
| D38 | Cliente oficial Google Ads | E | **existente** | — | não |
| D39 | GAARF | H | **hold** (como substituto: **rejeitado** por prova prévia) | P06-T08 · P09-T14 | não |
| D40 | Developer Assistant | H | **hold** | — | não |
| D41 | Google Ads MCP | H | **hold** | P10-T12 · P10-T13 | não |
| D42 | Analista agêntico read-only | N | **outra frente** | P10-T12 partial | não |
| D43 | Ledger/eval de agentes | N | **outra frente** | P10-T13 todo | não |
| D44 | Model routing benchmark | N/H | **outra frente** (parcial: `MODEL_ROUTING.json`) | P10-T13 todo · P10-T14 todo | não |
| D45 | ADSTA/IFTTA referências | H | **hold** | P09-T08 todo · P10-T12 | não |
| D46 | Tightlock/first-party | H | **hold / outra frente** | P06-T07 partial · P09-T03 partial | não |
| D47 | Supabase/Postgres autoridade | E | **existente** | cap_source_truth (decision) | respeitar |
| D48 | Parquet no lab | N | **novo** (pyarrow já no Freedom Lab) | P14-T02 | sim |
| D49 | BigQuery | H | **hold** | — | não |
| D50 | ClickHouse | H | **hold** | — | não |
| D51 | Feast | H | **hold** | — | não |
| D52 | Prefect/Dagster/Airflow | H | **hold** | P10-T16 partial | não |
| D53 | Redis/Ray | H | **hold** | — | não |
| X01 | Centroide das 10–25 conversões | R | **rejeitado** | — | não |
| X02 | Sinal de leilão = receita da sessão | R | **rejeitado** (o contrato do lab já recusa) | — | sim (contraprova) |
| X03 | Enviar surrogate ao Google | R | **rejeitado** | — | não |
| X04 | Pausar/escalar automático | R | **rejeitado** (`NIVEIS_QUE_APLICAM_SEM_HUMANO` vazio) | P14-T02 | não |
| X05 | Bloquear ASN/IP por RTT/scroll | R | **rejeitado** | — | não |
| X06 | Regras fixas universais | R | **rejeitado** (ainda há constantes no código) | P05-T09 | sim (como parâmetros) |
| X07 | 5 células reais + PMax | R | **rejeitado** | — | não |
| X08 | Upsert diário por `campaign_id` | R | **rejeitado** — **mas o anti-padrão vive na base legada** | P06-T02 partial | só handoff |
| X09 | LLM decide lucro/budget/mutate | R | **rejeitado** | — | não |
| X10 | Instalar libs "WOW" no ambiente principal | R | **rejeitado** (já há dois ambientes isolados divergentes) | P10-T24 partial | só handoff |

Totais na base real (classe principal, D01–D53): existente 2 · parcial 8 · novo 11 · outra frente 15 · hold 17 (D20, D29 e D46 também tocam outra frente; D39 é "rejeitado como substituto") · e X01–X10 rejeitados (10). O lab faz algo em 19 itens D (D05, D07, D08, D11–D19, D21, D22, D24, D25, D27, D28, D48) e em X02/X06 como contraprova/parâmetro, sempre hermético; "só handoff" em D03, D04, D06, X08, X10.

## 2. Divergências estruturais entre o catálogo e esta base (demonstrado)

Caminhos que o catálogo cita e **não existem** nesta base (`test -e`):

| Caminho citado | Onde vive de fato | Consequência |
|---|---|---|
| `volc_ads/economia/` (D04, D07, D08) | `wip/original-worktree-pre-qg-real-20261007` @ `043c77f5` (46 arquivos: `nucleo.py`, `reconciliacao.py`, migration `20261015163636_economia_atribuicao_campanha_dia.sql`, run `.claude-ads/runs/economic-attribution-20261015T1310-0300/`) | O "núcleo que é a autoridade do laboratório" não pode ser importado; o lab usa contrato autocontido (`docs/data-intelligence/CONTRATO-DADO-ECONOMICO.md`). |
| `supabase/migrations/v21_01_*`, `v21_02_*`, `v21_03_*` como ledger Google Ads (D01) | `0f0bb287` (só em branches `wip/historico-*`): `v21_01_google_ads_coleta_canonica.sql`, `v21_02_google_ads_hash_no_servidor.sql`, `v21_03_google_ads_finalizacao_run.sql` | **Colisão de numeração:** nesta base `v21_01` é `v21_01_meta_capi_sites_privilegios.sql` e `v21_02` é `v21_02_v6_rbac_privilegios.sql`. Integrar o ledger v21 da wip exige renumerar. |
| `supabase/migrations/20261015163704_*`, `n8n/joinads_v2_*`, `docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md` (D03) | `wip/historico-joinads-20261015` @ `192bc065` ("preservação, não integração: nada aqui foi revisado ou provado") | O ledger JoinAds append-only não está na base; a base só tem `joinads_metrics` com upsert. |
| `docs/operations/google-ads-coleta-canonica.md` (D01, D09) | `0f0bb287` (wip) | Sem o runbook canônico nesta base. |
| `measurement/gtm/` (fontes do catálogo) | `wip/historico-measurement-20261015` @ `918e9571` (sensor v3, WEBS wrapper, `volc-ingest`) | Telemetria de sessão (`raw_events`) não tem schema nem coletor nesta base. |
| `graphify-out/graph.json` | não gerado nesta worktree | Consulta feita no snapshot operacional versionado. |
| P06-T09 (economia por visita) | só no `ROADMAP-VIVO.json` da commit `043c77f5` | A base não registra a task; o integrador precisa trazê-la junto com o código. |

Trabalho prévio **na base** que o catálogo não cita e que se sobrepõe ao pacote da noite (demonstrado):

1. `services/orakul_predictive/` (4.304 linhas; testes em `backend/tests/orakul_predictive/`, 19 arquivos): walk-forward temporal (`replay.py:1`), relógio com fuso explícito (`relogio.py`), `SourceReceipt`/`FeatureSnapshot` com `feature_as_of`, `cutoff_em`, `max_instante_usado` (`contratos.py:47-57`, `127-154`), estados `ausente ≠ zero_medido` (`semantica.py:10-17`), champion/challenger, drift, incerteza. Só sintético (`fixtures_sinteticas.py`); P14-T10 partial ("spike 8e58cae rejeitado por duas revisões"). **É um terceiro vocabulário de estado** (orakul `EstadoSemantico`, economia `Estado` na wip, lab `EstadoMedida`).
2. `.claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-B-economia/` (14/10): E1 shrinkage Beta-Binomial EB, E2 nowcasting chain-ladder/Bornhuetter-Ferguson com as-of e drift, E3 OPE IPS/SNIPS/DR (+ cross-check obp), E4 instalação VW/MABWiser, E5 Wilson por funil — **todos sintéticos** (`RELATORIO-B.md:47-100`), e uma auditoria de dados (`AUDITORIA-DADOS.md:10-60`) com conclusões que este documento confirma na base.
3. `.claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-C-dados/`: GAARF viola `null≠0` e traz atores de mutação; clustering semântico de termos refutado (ARI 0,005) (`RELATORIO-C.md:27-32`).
4. `tools/freedom-lab/` (P10-T24 partial): `uv.lock` com duckdb 1.5.6, polars **2.0.0**, pyarrow, ortools, scikit-learn, scipy (`DEPENDENCIAS.json`); contrato de experimento (`contracts/experimento.schema.json`); o único experimento econômico com dado real (`experimentos/senac-shadow-20261015/`), projetado no backend (`backend/app/trafego/shadow_experimentos/`, lido por `recomendacao_shadow.py`).

## 3. Detalhe por item

Formato: **evidência** · **catálogo × base** · **lab**.

### Fundação: dados, identidade e verdade econômica

**D01 — Ledger canônico Google Ads → outra frente.**
Evidência: `supabase/migrations/v12_04_gads_fato_canonico_dia.sql:89` (`trafego_coleta_execucao`), `:259` (`google_ads_campanha_dia`), `:849-888` (UPSERT com precedência D0<D-1<backfill); `v17_01_gads_fatos_granulares.sql:55,121-136,183-189,210-240` (fatos granulares particionados, `google_ads_mudanca`/`google_ads_estado` append-only); `volc_ads/coleta/` (10 famílias, `contrato.py:1-30`: ausente = `None`, micros, enum como nome); grafo `gads-fato-campanha-dia` partial, `cap_cost_ingestion` partial. Roadmap P06-T08 partial (v17_01 aplicada em 08/10 segundo o proof; credencial e dono de agenda pendentes).
Catálogo × base: o catálogo aponta v21_01..03, que nesta base são outras migrations (colisão). O ledger da base guarda só **hash** do payload por execução e mantém **último valor** por chave (sem histórico de valores) — ver D08.
Lab: não. Só lê contratos.

**D02 — Cobertura máxima da API → outra frente.**
Evidência: `volc_ads/inteligencia_google/{coletor,pmax,saude,releitura}.py` (3.734 linhas), `volc_ads/google_ads_api/MATRIZ-COBERTURA-V25.md`, `catalogo_gaql_v25.json`, `supabase/migrations/v12_01_google_inteligencia_coletas.sql`. P05-T07/T08 e P09-T14 partial.
Lab: não.

**D03 — Ledger publisher/JoinAds → outra frente.**
Evidência na base: `src/sql/joinads/01_joinads_metrics.sql:21-45` (chave única `date, utm_campaign_value, joinads_domain`, `revenue NOT NULL DEFAULT 0` em `:30`), `n8n/gerar_flows_joinads.py:12-31` (uma requisição por dia porque a API agrega intervalos), `:394-396` (uma `custom_key` por chamada), `n8n/joinads_report_{intraday,day_before}.json`. Fora da base: v2 append-only (`joinads_collection_run/raw_batch/observation`) em `192bc065`, declarada pela própria auditoria wip como "ativa em shadow" e ainda não autoridade. Grafo: `db:joinads_metrics` = 0 linhas no snapshot de 22/08 (defasado frente ao proof de P06-T03, que diz que JoinAds é a única receita viva).
Lab: só handoff (grão e contrato documentados em `DATA-CAPABILITY-MATRIX.md`).

**D04 — Núcleo econômico → outra frente (ausente na base).**
Evidência: `git show 043c77f5 --stat` (wip); `volc_ads/economia/nucleo.py` lá define `Dinheiro(micros, moeda)`, recusa float e tz ausente; `reconciliacao.py` R1–R6 (custo Google × JoinAds por `utm_campaign_value = campaign.id`, dia fechado só após D-3, sem rateio). Migration `20261015163636` provada em PGlite, **não aplicada** (manifest wip: "leitura/escrita no Supabase oficial recusada").
Catálogo × base: o catálogo marca "E/P" e "autoridade do laboratório"; nesta base é **inexistente**. Precedentes parciais na base: `backend/app/trafego/custo_canonico.py:1-30` (dia sem coleta = `None`), `services/orakul_predictive/semantica.py:10-17`, `v17_04` (lucro só com `reconciliada_fonte_unica`).
Itens que dependem dele e mudam por isso: D05, D07, D08, D13, D14, D22, D25 (passam a consumir o contrato autocontido do lab; encaixe vira handoff).
Lab: só handoff (o contrato do lab declara-se 1:1 com o vocabulário do núcleo, `CONTRATO-DADO-ECONOMICO.md` §7).

**D05 — `value_kind` → novo.**
Evidência: `rg value_kind` fora do lab só acha `docs/architecture/SPEC-DATA-MANAGER-E-COPILOTO-GOOGLE-ADS.md:62-71` (`value_kind: observed | estimated | unknown`, para evento de conversão). Caso real que o justifica: `conversions_value` do Google é R$ 10 fixos por `adViewInterstitial`, "não receita" (`backend/app/trafego/shadow_experimentos/senac-shadow-20261015/resultado.json`, lacunas; wip P06-T09: R$ 0,168 medidos × R$ 10 configurados).
Catálogo × base: concordam que não existe; **conflito de vocabulário** a resolver no handoff: 3 valores (SPEC Data Manager) × 5 valores (catálogo/lab).
Lab: sim — já implementado em `experiments/data-intelligence-lab/src/volc_dil/contracts/` (COORD).

**D06 — Identidade campanha→funil→URL→jornada → outra frente (parcial na base).**
Evidência: `backend/app/trafego/reconciliacao.py:1-40` (sugestão por URL normalizada, vínculo só por confirmação humana em `trafego_vinculo`); grafo `concept:reconciliation` ("trafego_vinculo permanece vazia"), `cap_attribution` ("1 de 4 campanhas tem funnel_run_id"); `v17_04_arbitragem_reconciliada.sql:68-70` usa `trafego_vinculo`. Fora da base: `identity-gap-matrix.json` (wip 043c77f5): sem click id em `raw_events`, `utm_campaign` só no evento `sensor_ready`, junção receita só campanha×dia.
Lab: só handoff (mapa de chaves em `DATA-CAPABILITY-MATRIX.md` §2).

**D07 — Snapshot econômico `as_of` → parcial.**
Evidência: `services/orakul_predictive/contratos.py:127-154` (`feature_as_of`, `cutoff_em`, `max_instante_usado`); `volc_ads/inteligencia_decisao/normalizacao_google_ads.py:257-276,805-840` (`DATA_APOS_AS_OF`, `DATA_FUTURA`, `AS_OF_INVALIDO`); `tools/freedom-lab/contracts/experimento.schema.json` + `experimento.json` (`input_snapshot.sha256`, `captured_at`); lab `src/volc_dil/contracts/snapshot.py` (c1903d5f).
Catálogo × base: "N" no catálogo; na base há três implementações parciais, todas sintéticas ou de um único instante de conhecimento.
Lab: sim — reconciliar com `orakul_predictive` no handoff (evitar quarta noção de as-of).

**D08 — Reconciliação e restatement → parcial.**
Evidência: `v17_04_arbitragem_reconciliada.sql:6-33` (5 defeitos da v17_01), `:88-106` (status `reconciliada_fonte_unica`, `nao_reconciliada_*`, `janela_aberta`), `:140-167` (placement e hora sempre não reconciliados, `utilizavel_para_otimizacao=false`); `v23_01_receita_datada_cambio.sql:3` ("PROPOSTA: não aplicada"), `:32` (`receita_observacao` append-only); Google: latest-wins por precedência (`v17_01:429-446`). Roadmap P06-T03: v17_04 "NÃO aplicada em produção". Pesquisa B achou dois furos na v17_04 (receita D-1 muda até D+3; fuso não conferido) — `RELATORIO-B.md:41-46`.
Catálogo × base: o catálogo cita `volc_ads/economia/reconciliacao.py` (ausente). Nenhum histórico de revisão de valor é guardado hoje nas tabelas da base.
Lab: sim — cenários de teste sintéticos (preliminar × revisado, D-1 que muda até D+3, fuso divergente), sem afirmar receita por sessão.

**D09 — Data-quality e deadman → outra frente.**
Evidência: `backend/app/trafego/deadman_coleta.py:1-40` (adapter puro, "não agenda nada"), `volc_ads/inteligencia_google/saude.py` (`projetar_saude_coletor`), `docs/contracts/HEALTH-DEADMAN-GOOGLE-INTELLIGENCE.md`. JoinAds não tem deadman na base. Lab: não.

**D10 — Lineage/registry → outra frente.**
Evidência: P10-T06 partial ("falta contrato comum de source, job, run…"), P10-T01 done (`docs/volc-os-graph/inventario-n8n-sanitizado.json`). Lab: não.

### Laboratório econômico, replay e estatística

**D11 — DuckDB → parcial.** `tools/freedom-lab/DEPENDENCIAS.json` (duckdb 1.5.6, direta, "manter"); usado em `tools/freedom-lab/src/volc_lab/prova_vertical.py` para o join custo×receita do shadow Senac (`experimento.json` → `method.description`). Lab: sim (bancada, mesma versão 1.5.6).

**D12 — Polars → parcial.** No lock do Freedom Lab como 2.0.0, sem consumidor encontrado (`rg "import polars"` vazio fora do lab); o lab travou 1.44.2 por `exclude-newer` (`RUN-MANIFESTO.md` §4). Divergência de versão é risco de equivalência entre os dois ambientes. Lab: sim (bancada).

**D13 — Replay `as_of` → parcial.** Três "replays" que não são o mesmo objeto: (a) `volc_ads/inteligencia_decisao/replay.py:61-62,101-127` — um `as_of` fixo do dataset, 12 cenários sintéticos, sem série temporal; (b) `services/orakul_predictive/replay.py` — walk-forward com revisões, sintético; (c) shadow Senac — dado real, mas um único instante de conhecimento ("receita sem histórico as-of (upsert do último valor)", lacunas do `resultado.json`). Roadmap P09-T09 todo ("nenhum GoogleAdsRow real atravessou essa fronteira"). Lab: sim (replay econômico v0 sintético).

**D14 — Maturação/nowcasting → parcial (só pesquisa).** `pesquisa-B-economia/experimentos/e2_nowcasting.py` + `e2_resultado.json` (sintético; BF melhor nas idades curtas; drift degrada IC90 a 75%). Regras fixas em uso: 3 dias imaturos (`resultado.json` `parametros.dias_imaturos`), D-3 (wip). Sem dado real de revisão não há curva estimável (`AUDITORIA-DADOS.md:10-48`). Lab: sim — reusar E2 como baseline declarado, não refazer.

**D15 — Shrinkage → parcial.** E1 (`e1_shrinkage.py`, `e1_resultado.json`: EB a ≤2% do oráculo; "M=20 não é universal"); `backend/app/motor_pautas/dados/familias_rpm.json` aplica encolhimento (`roi_encolhido`, `prior_temas: 5`) sobre 296 temas WEBGO, e `backend/tests/test_webgo_priors_nao_decisorios.py` prova que esses priors não decidem. Lab: sim (comparar com E1; usar `familias_rpm.json` só como distribuição empírica de prior, nunca como verdade VOLC).

**D16 — Confidence sequences → novo.** Nada na base. Lab: sim, cobertura por simulação.

**D17 — FDR → novo.** Nada na base. Lab: sim, como relatório de avaliação.

**D18 — Curvas marginais → novo.** Com dado real é **não identificável hoje**: a única série econômica real tem gasto ~R$ 60/dia com teto aparente (`transformacao.csv`, 07–11/10) e nenhuma variação de orçamento controlada; a SPEC exige excluir underdelivery (`SPEC-BUDGET-ROI-ALLOCATOR-VOLC.md:127`). Lab: sim, só sintético.

**D19 — Risco/downside → novo.** Pesquisa B refutou Mean-CVaR como objetivo (B23, `RELATORIO-B.md:107-111`). Lab: só como métricas de replay (drawdown, quantis), separadas do objetivo.

**D20 — Causalidade → hold / outra frente.** `cap_incrementality_mmm` todo, `concept:mmm_weekly_dataset` todo, `docs/architecture/SPEC-MERIDIAN-MMM-VOLC.md`, P15-T01 done, P15-T09 todo. Lab: não.

### Otimização, swarm e experimentos

**D21 — SH/ASHA → novo.** Nada na base. Lab: sim, células sintéticas.

**D22 — Surrogate index → novo; real não identificável/insuficiente.** Ver `DATA-CAPABILITY-MATRIX.md` §5. Rótulo econômico reconciliado só existe em campanha×dia, para **uma** campanha Google (16 dias maduros) e um golden Meta (64 linhas campanha/dia). Sinais de sessão (wip) não se ligam à receita. Lab: sim — matriz de viabilidade + RidgeCV em sintético; com dado real a conclusão honesta hoje é `dados insuficientes`.

**D23 — Gradient boosting → hold.** Lab: não.

**D24 — Bandit → parcial (só pesquisa).** E3 OPE (`e3_ope.py`; propensão inventada dobra o IPS), E4 smoke VW/MABWiser; Freedom Lab adiou mabwiser/VW e rejeitou obp (`DEPENDENCIAS.json` `rejeitadas`). OPE real é impossível: decisões humanas sem propensão (`RELATORIO-B.md:25-28`). Lab: sim, simulação LinTS/Thompson × random/greedy.

**D25 — Allocator → novo (especificado).** `SPEC-BUDGET-ROI-ALLOCATOR-VOLC.md:98-172` (unidade, contrato mínimo, A0–A4); P09-T11 proof: "nenhum allocator foi implementado". Lab: sim, A0/A1 sintético.

**D26 — OR-Tools/CVXPY → hold.** OR-Tools 9.15 já no lock do Freedom Lab (e é a razão de `google-ads` ter sido rejeitado lá, conflito de protobuf). Lab: não agora.

**D27 — Swarm design → novo.** Lab: sim (schema + gerador; parâmetros, não regras — X06).

**D28 — Três relógios → novo.** Relógios reais existentes que o modelo deve declarar: D0 (4 passadas/dia, `v12_04:404`), D-1, JoinAds intraday legado 06/12/18/23 e D-1 que relê 3 dias (`AUDITORIA-DADOS.md:17-21`), JoinAds v2 a cada 2 h e D-7..D-1 (wip). Lab: sim, só modelagem.

**D29 — ExperimentService → hold / outra frente.** Só documentação v25 (`volc_ads/google_ads_api/api_reference_v25.md`). P05-T10. Lab: não.

**D30 — PMax → hold.** `volc_ads/observabilidade_pmax/`, `v12_03_pmax_observability_ledger.sql`. Lab: não.

### Diagnóstico, Search e semântica

**D31 → outra frente.** `backend/app/trafego/sentinela.py`, `volc_ads/inteligencia_google/saude.py`; P05-T07 partial. Lab: não.
**D32 → outra frente.** `volc_ads/inteligencia_search/governanca.py` (79 linhas); P05-T08 partial. Lab: não.
**D33 → hold.** Pesquisa C: HDBSCAN sobre embeddings ARI 0,005; 1-NN marcou 9/176 termos valiosos como negativar (`RELATORIO-C.md:32`). Refazer seria duplicação. Lab: não.
**D34 → hold.** Nenhuma migration com `vector`. Lab: não.
**D35 → outra frente.** `volc_ads/inteligencia_decisao/politicas.py:23-28` (`onboarding_max_age_hours: 72.0`, `nexus_guardiao_72h`) — constante herdada no código, que é exatamente o que X06 proíbe promover; P05-T09 partial (janelas nascimento/24h/24–72h/72h+). Lab: não.
**D36 → outra frente.** P05-T10 partial. Lab: não.
**D37 → outra frente.** `volc_ads/coleta/familias/estado.py`, `google_ads_estado` (`v17_01:240`); leitura real de política (734 linhas) no run `google-engine-nucleo-20261014-01` (`RELATORIO.md` §1). Lab: não.

### Agentes, ferramentas e operação

**D38 → existente.** `volc_ads/gads/client.py:26` (`VERSAO_API = "v25"`); `backend/requirements-dev.txt:29` (`google-ads>=33.0.0,<34`); a matriz v25 cita 31.3.0 instalado (divergência de documentação). Freedom Lab rejeita `google-ads` (protobuf). Lab: não (sem SDK; dado entra por snapshot).
**D39 → hold (rejeitado como substituto).** Pesquisa C: `garf` devolve `0` para métrica ausente (viola `null≠0`), e o `main` traz atores de mutação (`RELATORIO-C.md:27-28`). Lab: não.
**D40 → hold.** `volc_ads/google_ads_api/assistant_for_devs_gads_api.md`, `instalar_assistente_desenvolvedor.md`. Lab: não.
**D41 → hold.** `volc_ads/google_ads_api/mcp_google_ads.md` (MCP oficial só leitura). Lab: não.
**D42 → outra frente.** P10-T12 partial (Sentinel determinística, ainda não agêntica). Lab: não.
**D43 → outra frente.** P10-T13 todo; `tools/agent-harness/contracts/`. Lab: não.
**D44 → outra frente (parcial).** `tools/agent-harness/MODEL_ROUTING.json` (roteamento por papel já versionado). Lab: não.
**D45 → hold.** Grafo `system:google-if-this-then-ad-reference`; `.research/` (citado em P14-T02) não existe nesta worktree. Lab: não.
**D46 → hold / outra frente.** `backend/app/trafego/data_manager.py` ("monta, valida e NÃO envia"), `backend/app/trafego/conversao_offline/`, `v25_01_conversao_offline_ledger.sql`. Lab: não.

### Plataforma de dados

**D47 → existente.** `docs/architecture/ADR-SUPABASE-AUTORIDADE-OPERACIONAL.md`; grafo `cap_source_truth` (decision). Observação: a receita JoinAds do shadow Senac foi lida "via sessão humana (RLS)" porque o broker Supabase de leitura (v18_01) não está aplicado (`experimento.json` limitations).
**D48 → novo.** pyarrow 25.0.1 no Freedom Lab. Lab: sim.
**D49, D50, D51, D53 → hold.** Nada na base; concordo com o catálogo.
**D52 → hold.** Há tensão de autoridade na base: `docs/closure/hermes-p10-t16-n8n-ledger-v12-v1/ADR-N8N-AUTORIDADE-DE-AGENDA.md` diz n8n é o dono; o proof de P06-T08 ainda pede "escolher n8n OU systemd". Não adicionar um terceiro orquestrador.

### Ideias congeladas (X01–X10)

| ID | Base real | Nota |
|---|---|---|
| X01 | rejeitado | nenhum código assume centroide; manter como hipótese de experimento. |
| X02 | rejeitado | o contrato do lab recusa `revenue` com `observed_auction_signal` (`CONTRATO-DADO-ECONOMICO.md` §1). Sinais de GPT/viewability só existem na telemetria wip. |
| X03 | rejeitado | coerente com `SPEC-DATA-MANAGER…:62-71` e com B27/B28 refutados (`RELATORIO-B.md:132-140`). |
| X04 | rejeitado | `backend/app/trafego/gestao/application/autonomia.py:32` `NIVEIS_QUE_APLICAM_SEM_HUMANO = frozenset()`. |
| X05 | rejeitado | — |
| X06 | rejeitado como policy | constantes ainda vivem no código (`politicas.py:23` 72 h; parâmetros do shadow Senac `roas_aumentar 1.5`, `min_cliques_maduros 200`). Lab trata como parâmetros. |
| X07 | rejeitado | — |
| X08 | rejeitado — **anti-padrão presente na base legada** | `src/sql/joinads/01_joinads_metrics.sql:89-118`: o gatilho `sync_joinads_revenue_to_daily_metrics` faz `UPDATE daily_campaign_metrics SET revenue = NEW.revenue WHERE campaign_id = … AND date = …` por **linha de domínio** (a chave da origem inclui `joinads_domain`): com dois domínios na mesma campanha-dia, o último escritor vence; e no `INSERT` grava `spend/clicks/… = 0` (ausência vira zero). P06-T02 já registra que `daily_campaign_metrics` não tem conta. O lab não deve ler `daily_campaign_metrics` como fonte. |
| X09 | rejeitado | grafo `concept:decision_intelligence_lab`: "a crítica LLM não altera a decisão". |
| X10 | rejeitado | já existem **dois** ambientes isolados com lock próprio e versões diferentes (Freedom Lab polars 2.0.0; lab polars 1.44.2). Handoff: decidir um ambiente de experimentação ou declarar a divergência. |

## 4. Overlaps e exclusões (o que o lab NÃO deve fazer)

Pertence a outra frente e fica excluído desta missão: D01, D02, D03, D04, D06, D09, D10, D31, D32, D35, D36, D37, D42, D43, D44, D46 (e D20/D29 na trilha P15/P05-T10).

Overlaps que o lab deve **reusar ou comparar**, não reinventar:

| Item do lab | Já existe | Como tratar |
|---|---|---|
| contrato/snapshot as-of (1.1) | `services/orakul_predictive/{contratos,semantica,relogio}.py`; `normalizacao_google_ads.py` | mapear campo a campo no handoff; não criar quarta semântica de ausência |
| maturação (4.1) | `pesquisa-B/e2_nowcasting.py` | importar resultado como baseline declarado |
| shrinkage (4.1) | `pesquisa-B/e1_shrinkage.py`; `familias_rpm.json` | idem; prior empírico rotulado "WEBGO, não VOLC" |
| bandit/OPE (5.1) | `pesquisa-B/e3_ope.py`, `e4_smoke_bandits.py` | não repetir OPE; focar em simulação online |
| bancada DuckDB (2.1) | `tools/freedom-lab/src/volc_lab/prova_vertical.py` | comparar com o mesmo join do shadow Senac |
| clustering (D33) | `pesquisa-C/exp_semantica_fastembed_hdbscan.py` | fora do escopo |

## 5. Não verificado

- Estado real de aplicação em produção de v12_04, v17_01, v17_04, v23_01 e das migrations JoinAds v2: as fontes divergem (grafo `gads-fato-campanha-dia`: "v12_04 não aplicada oficialmente"; P06-T08: "v17_01 aplicada em produção em 08/10"; auditoria wip JoinAds: "aplicadas"). Não acessei produção.
- Se o código em `services/orakul_predictive/` é a versão rejeitada (8e58cae) ou uma posterior: o Roadmap diz que o spike foi rejeitado; a linha oficial (`48a3ad5f`) contém o diretório.
- Conteúdo do grafo híbrido `graphify-out/graph.json` (ausente nesta worktree).
