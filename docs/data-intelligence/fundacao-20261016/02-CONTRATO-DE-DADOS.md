# 02 — Contrato de dados: observação canônica append-only

Thread A da missão "Fundação Data Intelligence" (2026-10-16). Branch `lab/dil-fundacao-20261016-a`.

| Peça | Caminho | Estado (taxonomia do manifesto §7) |
|---|---|---|
| Domínio puro | `experiments/data-intelligence-lab/src/volc_dil/fundacao/observacao/` | construído, **testado hermeticamente** |
| Adaptadores v21 / JoinAds v2 | `.../observacao/adaptadores.py` | testado hermeticamente, só com **linhas sintéticas** |
| Migration candidata | `experiments/data-intelligence-lab/migrations_candidatas/dil_obs_0001_*.sql` | testada em **PostgreSQL 16 descartável**; não aplicada em nenhum banco operacional |
| Particionamento (opcional) | `.../migrations_candidatas/dil_obs_0002_*.OPCIONAL*.sql` | testado em PG16 descartável |
| Testes | `tests/data-intelligence/fundacao/test_observacao_*.py`, `test_schema_pg_*.py` | 171 testes novos; suíte inteira 343 verdes |

Nada aqui foi validado em produção, rodado em shadow ou calibrado com dado real.

---

## 1. A unidade de fato

Uma `Observacao` é **um fato** (fonte × conta × entidade × grão × dimensões × métrica × janela)
em **uma versão de conhecimento** (`available_at`), com o caminho até o payload bruto que a prova.

| Campo | Tipo / regra | Por quê |
|---|---|---|
| `fonte` | slug `^[a-z][a-z0-9_]*$` (`google_ads`, `joinads`, `gtm_sensor`) | fonte-agnóstico, mas sem grafia livre |
| `conta` | texto sem controle nem espaço de borda | a mesma entidade em outra conta é outro fato |
| `entidade` | `EntidadeRef(tipo, id)` | identidade verificável; nunca casar por nome |
| `grao` | conjunto do vocabulário herdado (`GRAOS_CONHECIDOS` de `volc_dil.contracts`) | ordem não importa (`("day","campaign") ≡ ("campaign","day")`) |
| `dimensoes` | pares `(nome, valor)` ordenados, sem repetição | separa fatos de mesma métrica (ex.: `revenue_basis=client/gross`) |
| `metrica` | vocabulário herdado `Metrica` | — |
| `valor` | `int` (micros ou contagem) ou `None`; float/bool recusados; cabe em `bigint` | null ≠ 0; sem float |
| `unidade` | `micros` (com `moeda` ISO-4217) ou `contagem` (sem moeda, ≥ 0) | dinheiro sempre em micros + moeda |
| `value_kind` | obrigatório em receita (≠ sinal de leilão); `observed_auction_signal` em sinal monetário; proibido no resto | regra X02 herdada |
| `janela_inicio`/`janela_fim`, `timezone` | instantes com tz; IANA válido | event time explícito |
| `observed_at`, `source_updated_at?`, `available_at`, `ingested_at` | ver §3 | três relógios separados |
| `run_id`, `request_id?`, `lote_id` | linhagem | qual execução, qual pedido |
| `payload_sha256`, `payload_ref` | `payload_ref` **contém** o sha256 (endereçamento por conteúdo) | referência imutável |
| `schema_version`, `coletor(nome, versao)` | — | reprocessar com outro coletor é outra leitura |
| `status`, `motivo`, `cobertura_ppm` | ver §4 | ausência ≠ falha ≠ atraso |

## 2. Grãos

O grão é o conjunto de eixos que a janela e a entidade cobrem. Exemplos:

| Fonte | Fato | entidade | grão | dimensões |
|---|---|---|---|---|
| Google Ads | custo campanha-dia | `campaign:<id>` | `campaign, day` | — |
| Google Ads | custo keyword-dia | `keyword:<criterion_id>` | `day, keyword` | `campaign_id`, `ad_group_id` (criterion só é único dentro do grupo) |
| Google Ads | termo de busca-dia | `search_term:<texto>` | `ad_group, day` | `campaign_id`, `ad_group_id` |
| JoinAds | receita campanha-dia | `campaign:<id>` | `campaign, day` (+ `ad_unit`, `country` quando há) | `joinads_endpoint`, `joinads_grain`, `custom_key`, `revenue_basis` |
| JoinAds | receita post-dia | `post:<id>` | `day, url` | idem |
| GTM/Sensor | sessões pagas página-dia | `url:<path>` | `day, url` | `utm_source` (o `utm.campaign` é removido pelo filtro de PII do Sensor v3 — recibo L4) |

Lacuna: o vocabulário herdado de grão não tem `search_term` nem `post`; usei `ad_group×day` e `url×day`.
Proposta ao integrador: acrescentar ao vocabulário herdado antes de qualquer consumidor depender disso.

## 3. Relógios (ordem obrigatória)

```
janela_inicio < janela_fim
janela_inicio <= observed_at <= available_at <= ingested_at
source_updated_at <= available_at                (quando existe)
observed/zero_confirmed  ⇒  observed_at >= janela_fim     (janela aberta é partial)
```

- `observed_at`: quando a leitura foi feita na fonte.
- `available_at`: **o relógio do replay**. Instante em que o VOLC passou a ter o payload. Nunca
  retroativo: backfill feito hoje sobre um dia antigo tem `available_at` de hoje. No banco isso é
  forçado: `available_at >= lote.recebido_em` e `lote.recebido_em <= now()`.
- `ingested_at`: quando a linha foi escrita. No banco é `now()` da transação (o escritor não declara);
  como `ingested_at >= available_at` é CHECK, ninguém registra conhecimento do futuro.
- `source_updated_at`: o carimbo da própria fonte (opcional).

## 4. Status

| status | valor | motivo | cobertura | Semântica | Google Ads | JoinAds | GTM/Sensor |
|---|---|---|---|---|---|---|---|
| `observed` | não nulo, ≠ 0 | opcional | — | a fonte devolveu número, janela fechada | custo D-1 após o fechamento | receita D-1 do relatório | sessões D-1 |
| `zero_confirmed` | `0` | opcional | — | a fonte **afirmou** zero | linha GAQL presente com campo omitido (default proto3) | linha devolvida com `0` | contagem da tabela agregada com 0 explícito |
| `missing` | `None` | obrigatório | — | a fonte respondeu e **não há linha/valor** | campanha sem linha de métrica (zero sintetizado pelo Code node) | `custom_value` esperado ausente da resposta | página sem evento no dia |
| `late` | `None` | obrigatório | — | esperado e **ainda não publicado** | dia ainda sem dados às 04h | D-1 não publicado até 06h | lote do sensor atrasado |
| `unavailable` | `None` | obrigatório | — | a **coleta falhou** | quota/HTTP 5xx | HTTP 503, timeout | Edge Function fora |
| `unsupported` | `None` | obrigatório | — | a fonte **não mede** aquilo | receita | custo | custo |
| `invalid` | `None` (bruto só no payload) | obrigatório | — | respondeu, mas viola o contrato | conversão fracionária, float | `custom_key` substituído, intervalo de datas | evento sem identidade |
| `partial` | int ou `None` | obrigatório | `cobertura_ppm` 1..999 999 | cobertura parcial declarada | leitura intradiária (d0) | relatório INTRA DAY | dia em curso |

Regras: `observed` com `0` é recusado (zero afirmado é `zero_confirmed`); qualquer status sem valor
com `valor=0` é recusado; `cobertura_ppm` só existe em `partial`.

Mapeamento para o contrato herdado (`MAPA_ESTADO_HERDADO`): observed→`medido`, zero_confirmed→`zero_confirmado`,
missing→`ausente`, late→`nao_coletado`, unavailable→`falha`, unsupported→`nao_aplicavel`, invalid→`falha`,
partial com valor→`medido`+cobertura `partial`, partial sem valor→`nao_coletado`. A direção fina → grossa
perde informação de propósito; por isso `agregar_observacoes` devolve também a contagem por status fino.

## 5. Chaves

- **Chave natural** (`chave_natural`): sha256 de fonte, conta, entidade, grão, dimensões, métrica,
  value_kind, janela (UTC) e timezone. **Não** entram valor, status, moeda nem relógios de conhecimento —
  por isso `missing` e o `observed` posterior são versões do mesmo fato.
- **Chave de idempotência** (`chave_base`): sha256 de chave natural + `payload_sha256` + `schema_version`
  + coletor (nome, versão). É a identidade de uma **leitura**.
- **Chave de reafirmação**: sha256 de `chave_base` + `available_at` (caso A→B→A, §6).
- Serialização canônica **não é JSON** (o `jsonb::text` do Postgres difere do `json.dumps`): campos
  unidos por US (0x1F), pares de dimensão por RS (0x1E), nome/valor por GS (0x1D), grão ordenado por ponto
  de código, instantes `YYYY-MM-DDTHH:MM:SS.ffffffZ`. Caracteres de controle são proibidos nos campos.
  O banco recalcula as chaves (`dil_obs._chave_*`); o escritor não escolhe a chave. Igualdade Python × SQL
  provada em `test_chaves_python_iguais_as_do_postgres` (inclui acento, aspas, offset +05:30, microssegundos).

## 6. Registro e restatement

`Registro.registrar(obs)` (Python) e `dil_obs.registrar_observacao(jsonb)` (SQL) aplicam as **mesmas** regras:

| Situação | Resultado |
|---|---|
| `chave_base` nova | `inserido` (tipo `leitura`) |
| mesma `chave_base`, conteúdo (status, valor, unidade, moeda, cobertura) diferente | erro `conflito_idempotencia` (coletor não determinístico) |
| mesma `chave_base`, versão vigente é desta leitura **ou** `available_at` não posterior | `noop` (retry, cron que relê o mesmo dado, reentrega fora de ordem) |
| mesma `chave_base`, outra versão ficou vigente depois e o novo `available_at` é posterior | `reafirmado`: nova linha, chave de reafirmação (A→B→A: a fonte retrata e volta) |
| outra leitura do mesmo fato com o mesmo `available_at` | erro `versao_ambigua` (UNIQUE `(chave_natural, available_at)`) |

- Restatement é **sempre linha nova**. UPDATE/DELETE/TRUNCATE não existem (§10).
- Reentrega fora de ordem é conservadora: pode atrasar conhecimento, nunca antecipá-lo.
- Dedup entre execuções: a mesma leitura relida pelo cron seguinte é `noop` e o conhecimento continua
  datado da primeira leitura.

## 7. `as_of` e `latest`

- `as_of(obs, t)` (puro): por chave natural, a versão de **maior `available_at <= t`**; status preservado;
  independe da ordem de entrada; ambiguidade levanta erro em vez de escolher.
- `latest(obs, agora)` = `as_of(obs, agora)`; não há relógio implícito.
- SQL: `dil_obs.observacao_as_of(t)` (`DISTINCT ON (chave_natural) ... ORDER BY chave_natural, available_at DESC`,
  SECURITY INVOKER) e `dil_obs.observacao_latest` = `observacao_as_of(now())`. A view é derivada do
  histórico; o histórico não é tocado. Índice único `(chave_natural, available_at DESC)` serve o as_of.
- Equivalência: `test_equivalencia_as_of_sql_python` gera 8 sequências aleatórias (seed 1610, 8–30 leituras
  com retries, A→B→A e ausências), compara o resultado de cada registro e o as_of em 9 cortes; e exige que
  os três caminhos (`inserido`, `noop`, `reafirmado`) tenham sido exercitados.
- Atenção a consumidores SQL: `sum(valor)` ignora NULL. O total sem a contagem de `valor IS NULL` ao lado
  mente (ver `test_missing_unavailable_late_distintos_no_banco`). Em Python, `agregar_observacoes` compõe
  `volc_dil.contracts.agregar`: vazio → ausente; qualquer membro sem valor → total sem valor (salvo
  `aceitar_parcial`, que marca cobertura parcial).

## 8. Schema drift (`normalizar`)

`normalizar(PayloadBruto(schema_version, bytes), esquemas, ContextoLeitura)` → observações + rejeições:

| Caso | Saída |
|---|---|
| versão de esquema desconhecida | rejeição `schema_desconhecido` |
| corpo não-JSON / estrutura inesperada | entidades esperadas `invalid` (`payload_nao_json` / `estrutura_inesperada`) |
| campo de métrica obrigatório ausente | `invalid` `campo_obrigatorio_ausente:<campo>` |
| campo de identidade ausente | rejeição (vai para `dead_letter`); entidades esperadas ficam `invalid` `resposta_com_linhas_rejeitadas` (não `missing`) |
| campos extras | ignorados, listados em `campos_extras` |
| aliases (`custon_key`/`custom_key`) | aceitos |
| chave devolvida ≠ pedida (JoinAds) | linha rejeitada (nunca vira entidade falsa) e esperadas `invalid` `chave_substituida:<pedida>-><devolvida>` |
| valor nulo explícito | `missing` `valor_nulo_na_fonte:<campo>` |
| float / NaN / `"1,5"` / precisão abaixo de micro | `invalid` (sem arredondamento silencioso); JSON é lido com `parse_float=Decimal` |
| linha duplicada para a mesma entidade | `invalid` `linha_duplicada` |
| intervalo de datas no lugar do dia (JoinAds) | `invalid` `data_fora_da_janela` (validador do esquema) |
| janela aberta em `observed_at` | `partial` com `cobertura_ppm` proporcional ao tempo decorrido |

`observacoes_sem_dado(ctx, payload, campos, status, motivo)` emite `missing/late/unavailable/unsupported/invalid`
para as entidades esperadas (ex.: HTTP 503 → `unavailable`, com o corpo do erro como payload).

## 9. Tabelas vivas: Google Ads v21 e JoinAds v2 → `Observacao`

O recibo do integrador (`receipts/leituras-externas/RECIBO-LEITURAS-20261016.md`) mostrou que as tabelas
append-only canônicas **já existem em produção**: v21 (`google_ads_collection_run`, `google_ads_raw_batch`,
`google_ads_observation`) e JoinAds v2 (`joinads_collection_run`, `joinads_raw_batch`, `joinads_observation`).
DDL lido em `043c77f5:supabase/migrations/v21_01..03` e em
`wip/historico-joinads-20261015:supabase/migrations/20261015163704_joinads_collection_canonical.sql`.
Os adaptadores são puros e recebem a linha **juntada** com lote e execução:

```sql
-- v21 (somente leitura; os nomes com prefixo são os que o adaptador espera)
SELECT o.*, b.payload_sha256 AS batch_payload_sha256, b.request_id AS batch_request_id,
       b.payload AS batch_payload, r.collector AS run_collector, r.collector_version AS run_collector_version,
       r.api_version AS run_api_version, r.timezone AS run_timezone
  FROM google_ads_observation o
  JOIN google_ads_raw_batch b ON b.batch_id = o.batch_id
  JOIN google_ads_collection_run r ON r.run_id = o.run_id;
-- JoinAds v2
SELECT o.*, b.payload_sha256 AS batch_payload_sha256, b.request_meta AS batch_request_meta,
       r.collector AS run_collector, r.collector_version AS run_collector_version, r.timezone AS run_timezone
  FROM joinads_observation o
  JOIN joinads_raw_batch b ON b.batch_key = o.batch_key
  JOIN joinads_collection_run r ON r.run_key = o.run_key;
```

### 9.1 `adaptar_google_ads_v21(linha)` — uma `Observacao` por métrica

| Observacao | v21 | Regra |
|---|---|---|
| `fonte` | — | `google_ads` |
| `conta` | `customer_id` | obrigatório (senão `AdaptacaoImpossivel` → dead letter) |
| `entidade`, `grao`, `dimensoes` | `grain` + `campaign_id`/`ad_group_id`/`criterion_id`/`dimensions.search_term` | `campaign_day`→`campaign:<campaign_id>`, `campaign,day`; `keyword_day`→`keyword:<criterion_id>` + dims grupo/campanha; `search_term_day`→`search_term:<texto>`, `ad_group,day`; `campaign_hour`, `ad_group_day`. Grain desconhecido → `AdaptacaoImpossivel` |
| `metrica`/`unidade`/`valor` | `metrics.cost_micros` (já micros), `impressions`, `clicks`, `conversions` | inteiro estrito; `conversions` fracionária → `invalid` `valor_fracionario` (lacuna: conversão de atribuição data-driven é fracionária e o vocabulário herdado só tem contagem inteira) |
| não mapeadas | `conversions_value`, `all_conversions*`, `interactions`, `ctr`, `average_cpc_micros`, `cost_per_conversion_micros`, `*_share`, `*_percentage` | razões/derivadas não são observação somável; ficam no payload bruto |
| `moeda` | `currency_code` | ausente com valor monetário → `invalid` `moeda_nao_declarada` |
| `janela_inicio`/`fim` | `metric_date` (+ `metric_hour`) no `run_timezone` (padrão `America/Sao_Paulo`) | dia local com DST resolvido por `zoneinfo` |
| `observed_at` | `collected_at` | relógio do n8n |
| `available_at` = `ingested_at` | `max(collected_at, created_at)` | o VOLC só sabe quando a linha existe no banco; relógio adiantado do n8n não antecipa |
| `run_id`, `lote_id`, `request_id` | `run_id`, `batch_id`, `batch_request_id` | — |
| `payload_sha256`, `payload_ref` | `batch_payload_sha256`; `google_ads_raw_batch:<batch_id>:sha256:<hash>` | hash do v21 é de `jsonb::text` (canônico do banco), não dos bytes recebidos |
| `schema_version` | `google_ads.v21.<resource_type>.<grain>.api_<api_version>` | — |
| `coletor` | `run_collector`, `run_collector_version` | — |
| `status` | derivado | janela aberta em `collected_at` → `partial`; chave ausente em `metrics` → `missing` `metrica_ausente_no_registro`; valor `null` → `missing`; ≠ 0 → `observed`; **0 → ver abaixo** |

**Zero sem linha de métrica vira `missing` salvo prova.** O Code node do coletor v21 (`basic()` em
`043c77f5:scripts/instalar_coleta_canonica_google_ads_n8n.py:127-150`) devolve `0` quando a campanha não
tem linha de métrica — é por isso que 88 de 110 observações campanha-dia têm custo e impressões 0 (recibo L11).
O adaptador só aceita `zero_confirmed` campanha-dia com **prova**: o payload bruto do lote
(`raw_source.metrics`) tem a linha GAQL de métrica não vazia. Linha vazia → `missing`
`zero_sem_linha_de_metrica`; payload fora da junção → `missing` `zero_sem_prova_de_linha`. Valor ≠ 0 não
é sintetizável e vale sem prova. (O status da campanha, sugerido como prova alternativa, não prova zero:
campanha ENABLED pode ter zero impressões ou simplesmente não ter linha; ficou fora.)

### 9.2 `adaptar_joinads_v2(linha)` — uma `Observacao` por métrica

| Observacao | JoinAds v2 | Regra |
|---|---|---|
| `fonte`, `conta` | —, `domain` | `joinads`; domínio obrigatório |
| `entidade` | `campaign_id` → `campaign`; senão `post_id` → `post`; senão `land_uri` → `land_uri`; senão `custom_key/custom_value` → `kv:<custom_key>`; senão `domain` | — |
| `grao` | `campaign`/`url`/`cell`/`account` + `day` ou `hour` (+ `ad_unit`, `country` quando presentes) | — |
| `dimensoes` | `joinads_endpoint`, `joinads_grain`, `custom_key`, `custom_value`, `post_id`, `land_uri`, `ad_unit_name`, `country_iso` (menos a coluna que virou entidade) | espelha a chave do `joinads_observation_latest` |
| receita | `revenue_client` e `revenue_gross` | `reported_revenue`, micros por `Decimal` (precisão abaixo de micro → `invalid`); dois fatos distintos pela dimensão `revenue_basis=client/gross` |
| contagens | `impressions`, `clicks` | — |
| não mapeadas | `requests_served`, `unfilled`, `pageviews`, `unique_views`, `first_views`, `active_view`, `pmr`, `ctr`, `ecpm_*` | sem métrica no vocabulário (pageview **não** é sessão) ou razão |
| `moeda` | `currency_code` | ⚠️ a coluna tem `DEFAULT 'USD'`: moeda ausente vira USD no banco e o adaptador não consegue distinguir |
| relógios | `collected_at`, `created_at` | como no v21 |
| `run_id`, `lote_id` | `run_key`, `batch_key` | — |
| `payload_sha256` | `batch_payload_sha256` | `repeat('0',64)` (default sem o trigger) → todas as métricas `invalid` `payload_sem_hash` |
| `status` | `data_status` + valor | `unavailable`/`unsupported` → idem para todas as métricas; `null` → `missing`; `0` numa linha devolvida → `zero_confirmed` (a JoinAds devolve linha explícita); `data_status=zero_confirmed` com valor ≠ 0 → `invalid`; janela aberta → `partial` |
| chave substituída | `batch_request_meta.custom_key` ≠ `custom_key` | todas as métricas `invalid` `chave_substituida:<pedida>-><devolvida>` |

### 9.3 Decisão: `dil_obs` não substitui v21/v2

O schema genérico `dil_obs` **é redundante** com v21 e JoinAds v2 para Google Ads e JoinAds. Decisão:

1. **Não** escrever Google Ads ou JoinAds em `dil_obs` (escrita dupla criaria duas autoridades).
   Para essas fontes, a observação canônica é **um modelo de leitura**: v21/v2 → adaptadores → `Observacao`
   → `as_of`/replay (threads D, F, G consomem isso).
2. `dil_obs` fica como (a) destino candidato de fontes **sem** ledger append-only (GTM/Sensor agregados,
   GAM, AdSense); (b) armazenamento hermético de referência para replay/shadow/simulação; (c) especificação
   executável do que v21/v2 deveriam garantir se forem endurecidas.
3. O que v21/v2 não garantem e `dil_obs` garante (insumo para endurecer as tabelas vivas, não para trocá-las):

| Garantia | v21 | JoinAds v2 | dil_obs |
|---|---|---|---|
| status por métrica (null ≠ 0) | não (`metrics` jsonb; zero sintetizado no coletor) | `data_status` por linha, não por métrica | sim, CHECKs |
| TRUNCATE bloqueado | não (trigger só UPDATE/DELETE, por linha) | não | sim (trigger de statement) |
| RLS forçado | sim | não (só ENABLE) | sim |
| defaults que inventam valor | contadores `DEFAULT 0` na execução | `currency_code DEFAULT 'USD'`, `payload_sha256 DEFAULT '0'*64`, `data_status DEFAULT 'observed'` | nenhum DEFAULT em métrica ou moeda |
| idempotência entre execuções | não (UNIQUE `(run_id, observation_key)`: cada run regrava) | `observation_key` PK | `chave_base` (leitura) |
| relógio do latest | `collected_at` (n8n) | `collected_at`, e só runs `completed/partial` | `available_at` limitado pelo banco |
| hash | de `jsonb::text` (v21_02, no banco) | de `jsonb::text` (trigger) | dos bytes recebidos, conferido por CHECK |

Divergência a registrar: `joinads_observation_latest` exclui runs `running/failed`; o `as_of` do adaptador
não filtra por estado da execução (as linhas existem e foram conhecidas). Quem precisar do filtro aplica no
consumidor. Os 3 runs v21 presos em `running` (recibo L9) não mudam o status das observações.

## 10. Schema `dil_obs` (migration candidata 0001)

- Papéis: `dil_obs_dono` (NOLOGIN, sem superusuário, sem BYPASSRLS; dono de tudo), `dil_obs_escritor`
  (só EXECUTE em `registrar_run`, `finalizar_run`, `registrar_payload`, `registrar_lote`,
  `registrar_dead_letter`, `registrar_observacao`), `dil_obs_leitor` (só SELECT nas tabelas/view e EXECUTE em
  `observacao_as_of`). `anon`/`authenticated` sem nada, explicitamente, mesmo com o default ACL aberto do
  Supabase (simulado no cluster de teste). PUBLIC sem EXECUTE em função nenhuma.
- Tabelas: `run_coleta` (única com UPDATE: `running` → final, uma vez; contagens nulas até fechar),
  `payload_bruto` (`sha256` = `encode(sha256(corpo_bruto),'hex')` por CHECK; corpo não-JSON guardado com
  `corpo` nulo), `lote` (pedido + payload + `recebido_em`), `observacao` (PK surrogate, UNIQUE na chave de
  idempotência, UNIQUE `(chave_natural, available_at)`, 24 CHECKs de invariantes), `dead_letter`.
- Append-only: trigger de statement `BEFORE UPDATE OR DELETE OR TRUNCATE` em `observacao`, `payload_bruto`,
  `lote`, `dead_letter` — dispara mesmo sem linha casada e mesmo para superusuário. Limite honesto:
  superusuário pode desligar o trigger (`DISABLE TRIGGER`, `session_replication_role=replica`); isso é
  decisão de operador, não acidente.
- Funções de escrita: SECURITY DEFINER com `search_path = ''` (tudo qualificado); lock consultivo por chave
  natural; recusam campos desconhecidos, float, timezone inválido, dimensões fora de ordem, lote inexistente,
  payload diferente do lote, `available_at` anterior ao recebimento do lote, execução finalizada.
- RLS habilitado **e forçado** em todas as tabelas, policies explícitas só para SELECT (leitor, dono) e
  INSERT (dono); nenhuma policy de UPDATE/DELETE nas tabelas append-only.
- Rollback `0001.down.sql`: `DROP SCHEMA ... CASCADE` + papéis removidos só se não houver dependência em
  outro banco (NOTICE). Destrói o histórico (documentado no cabeçalho).
- Sintaxe compatível com PostgreSQL 15 (produção roda 15.8), mas testado só em 16.

**Particionamento (0002, opcional):** por mês UTC de `janela_inicio`; PK/UNIQUE incluem `janela_inicio`
(equivalente, pois ela está dentro do hash da chave natural); sequência explícita (IDENTITY em particionada
só no PG17); sem partição DEFAULT (linha fora falha alto; `garantir_particao_mensal(mes)` cria a partição);
append-only por trigger de statement no pai + trigger de linha clonado nas partições + TRUNCATE por partição.
Usar só quando volume ou retenção exigirem.

## 11. Relação com o contrato econômico herdado

Composição, não cópia: `para_contrato_economico(obs, maturidade=, metodo=)` produz
`volc_dil.contracts.Observacao`; `Snapshot`, `agregar`, `contribuicao`, `rotulo_economico` e
`verificar_nao_circular` continuam sendo a regra econômica. Mapeamento: `available_at`→`disponivel_em`,
`observed_at`→`observado_em`, `run_id`→`coleta_id`, `(lote, payload_ref)`→`linhagem`,
`schema_version;coletor@versao`→`versao_fonte`, status→`EstadoMedida` (§4), cobertura `complete` só para
observed/zero_confirmed. Maturidade e método de atribuição **não** vêm da fonte bruta: o chamador declara
(padrão `preliminary` e `nao_aplicavel`). Reaproveitados do herdado: `Metrica`, `ValueKind`,
`GRAOS_CONHECIDOS`, `ContratoViolado` (pai de `ObservacaoInvalida`), `VersaoAmbigua`, `MICROS`.

## 12. Decisões e alternativas rejeitadas

| Decisão | Alternativa rejeitada | Por quê |
|---|---|---|
| chave calculada pelo banco | chave enviada pelo coletor | o escritor não pode escolher a própria identidade |
| serialização US/RS/GS | JSON canônico | `jsonb::text` ≠ `json.dumps`; o banco não reproduziria |
| idempotência por leitura (payload + coletor) | por execução (`run_id`) | cron relê o mesmo dado; dedup entre execuções evita versões falsas |
| reafirmação A→B→A | `noop` sempre que a chave já existe | a retratação da fonte sumiria do as_of |
| `available_at` limitado por `lote.recebido_em` e `now()` | confiar no coletor | backfill retroativo vazaria futuro no replay |
| `observed` ≠ 0 | permitir `observed` 0 | zero afirmado e zero sintetizado precisam de nomes diferentes |
| float recusado | arredondar | dinheiro em float é bug silencioso |
| trigger de statement | trigger de linha (como v21/v2) | não pega TRUNCATE nem UPDATE sem linha |
| papel dono sem BYPASSRLS + FORCE RLS | dono `postgres` | SECURITY DEFINER como superusuário ignoraria RLS |
| sem partição DEFAULT | DEFAULT | DEFAULT com linhas impede criar a partição do mês |
| adaptadores sobre v21/v2 | migrar Google/JoinAds para `dil_obs` | duas autoridades; v21/v2 já estão vivas |
| `invalid` guarda bruto só no payload | coluna `valor_bruto` | um número inválido em coluna numérica acaba somado |

## 13. O que está provado e o que não

**Testado hermeticamente** (comandos e contagens no `handoffs/HANDOFF-A.md`):
validação de status × valor, relógios, unidade/moeda/value_kind; chaves estáveis a offset e ordem de grão;
igualdade de chaves Python × PostgreSQL; idempotência (reinserção = no-op, contagem igual) em Python e SQL;
restatement como versão nova; reafirmação; conflito; versão ambígua; reentrega fora de ordem; as_of antes/depois
de reprocessamento tardio; propriedade com seed fixa (150 sequências) para idempotência, as_of vs dado bruto,
independência de ordem e "não olha o futuro"; equivalência as_of SQL × Python (8 sequências); concordância
de validação Python × SQL em 25 mutações; 18 CHECKs disparando em inserção direta; append-only para
UPDATE/DELETE/TRUNCATE em 4 tabelas, até para superusuário; RLS/grants (leitor não escreve, escritor não lê
nem escreve direto, anon/authenticated/PUBLIC sem nada); hash do payload conferido pelo banco;
conhecimento retroativo e do futuro recusados; missing × unavailable × late distintos de ponta a ponta;
schema drift e chave substituída; adaptadores v21/v2 com linhas sintéticas (incluindo zero sintetizado →
missing e maturação intradiária → versões); rollback up → down → up com catálogo idêntico; particionamento
com as_of idêntico antes/depois e rollback exato; varredura de segredos com contraprova.

**Ainda não demonstrado:**
- adaptadores sobre linhas **reais** de v21/v2 (a leitura de produção é do integrador; nenhuma linha real foi
  usada aqui);
- se o JSON real de `raw_source.metrics` do v21 tem a forma assumida (linha GAQL ou `{}`);
- comportamento sob concorrência real (o lock consultivo existe, mas não há teste multi-sessão);
- desempenho do `DISTINCT ON` global em volume (thread B);
- aplicação em PostgreSQL 15 e no Supabase self-hosted (PostgREST não expõe `dil_obs`, o que é desejado);
- origem do `timezone` real de fechamento do dia da JoinAds (README JoinAds: em aberto);
- GTM/Sensor: só exemplos de semântica; não há adaptador.
