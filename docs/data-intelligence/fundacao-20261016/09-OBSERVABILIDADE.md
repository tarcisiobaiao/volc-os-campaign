# 09-OBSERVABILIDADE — health contracts, checagens de qualidade e alertas (thread G)

**Missão:** Fundação Data Intelligence (2026-10-16) · **Worker:** G · **Branch:** `lab/dil-fundacao-20261016-g`
**Produção:** não acessada. Tudo aqui é `construído` + `testado hermeticamente` / `testado com sintético`
(taxonomia do manifesto §7). Nada foi aplicado em banco operacional; nenhum alerta é enviado.

Código: `experiments/data-intelligence-lab/src/volc_dil/fundacao/qualidade/` · Views candidatas:
`experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/` · Testes:
`tests/data-intelligence/fundacao/test_qualidade_*.py` · Handoff: `handoffs/HANDOFF-G.md`.

## 1. Princípios

1. **Ausência nunca vira zero.** `None`/métrica ausente/valor não numérico é `nulo`; zero só é prova com linha de
   métrica da API (ou `zero_confirmed` do contrato A). Em toda checagem há teste de borda "null não é zero".
2. **Atraso não é ausência.** `late` (ou `available_at` depois do prazo) é `atrasado`, nunca `ausente`.
3. **Declarado ≠ silencioso.** Run `failed` / `missing` declarado é uma classe; nenhum registro é outra (pior).
4. **Janela fora da agenda não é buraco.** Slots só existem nas horas do cron; um slot só "vence" depois de
   `slot + tolerância`; o coletor não é cobrado por horas anteriores ao seu primeiro run.
5. **Mesma regra em Python e SQL.** As views são o espelho das funções puras; a equivalência é testada no mesmo
   dataset (§6). Parâmetros (SLA e limiares) existem nos dois lados e um teste compara os valores.
6. **Alerta é contrato, não envio.** A decisão é uma função pura; o canal é um `sink` injetado (falso nos testes).

## 2. Health contracts (SLA = cadência esperada + tolerância)

Cadências tiradas do código versionado (wip), não de produção: Google `043c77f5:scripts/instalar_coleta_canonica_google_ads_n8n.py:261-262`,
termos `043c77f5:scripts/instalar_coleta_termos_keywords_n8n.py:193`, JoinAds `192bc065:n8n/gerar_flows_joinads_v2.py:319-324`.
Horário local `America/Sao_Paulo`. Folga de relógio: 10 min (um run que começa até 10 min antes do slot conta).

| Coletor lógico | Fonte / grão | Agenda | Tolerância | Timeout `running` | Mín. linhas |
|---|---|---|---|---|---|
| `n8n-google-ads-d0` | google_ads / campaign_day | `7 6-23 * * *` (D0 horário 06–23) | 30 min | 30 min | 1 |
| `n8n-google-ads-d1` | google_ads / campaign_day | `17 6,14 * * *` (D-1 2×/dia) | 60 min | 30 min | 1 |
| `n8n-google-ads-terms-keywords` | google_ads / search_term_day | `23 */4 * * *` (4 h, LAST_7_DAYS) | 60 min | 60 min | 1 |
| `n8n_joinads_v2:intraday` | joinads / campaign_adunit_day | `15 6-22/2 * * *` (2 h) | 45 min | 30 min | 1 |
| `n8n_joinads_v2:d1` | joinads / campaign_adunit_day | `20 6 * * *` (relê D-7..D-1) | 120 min | 30 min | 1 |

O JoinAds v2 grava `collector = 'n8n_joinads_v2'` nos dois workflows; o papel lógico sai da janela
(`window_end >= data local do início` → intraday; senão D-1). Mesma expressão no adaptador Python e em `dq_runs`.

Limiares (`LIMIARES_PADRAO` ≡ `dil_qualidade.dq_parametros_limiares`): frescor parado ≥ 3 slots; zero sintetizado
alto ≥ 50%; receita kv/earnings ok em [0,90; 1,02], alto < 0,50 ou > 1,02; custo D0×D-1 aviso > 5%, alto > 25%;
sensor ok ≥ 90%, alto < 50%, amostra mínima 10 sessões pagas; janelas de leitura/reconciliação 14 dias.

## 3. Catálogo de checagens

| Regra (prefixo) | O que detecta | Limiar / severidade | Por que existe | Falso positivo conhecido |
|---|---|---|---|---|
| `frescor_*` | último sucesso (`completed`/`partial`) vs slots vencidos | 0 perdidos ok; 1–2 `atrasado` aviso; ≥3 `parado` alto; nenhum sucesso `sem_registro` crítico | dado velho alimentando decisão | `partial` conta como sucesso (JoinAds marca `partial` por qualquer aviso); coletor desligado de propósito vira `sem_registro` |
| `completude_slots` | cada slot esperado: `ok`/`parcial`/`em_execucao`/`falha_declarada`/`ausente_silencioso`/`pendente` | por dia: ≥3 silenciosos alto; algum silencioso/falha aviso; só parcial/em execução info | buracos por hora/dia, separando falha registrada de silêncio | run manual fora do slot não cobre o slot; retry depois da tolerância conta como ausência |
| `completude_*` (grade) | entidade × dia × hora esperada vs observada (Python) | silencioso/inválido alto; declarado/sem valor aviso; atrasado/parcial info | campanha que some sem ninguém declarar | depende do conjunto esperado (o banco não sabe quais campanhas deveriam existir) |
| `run_orfao` | `running` além do timeout **e** sem sinal de vida no timeout | alto | 3 runs reais presos desde 15/10 11:48 (L9); não há reaper | coletor lento legítimo sem lotes intermediários (n8n JoinAds só grava no fim) |
| `falha_silenciosa_run_vazio` | run `completed`/`partial` com 0 linhas onde o contrato espera > 0 | alto | finish sem ingest (v21_03 cria o run no finalizador) | dia sem campanha ativa de fato; `NULL` não dispara |
| `duplicacao_conflito_no_run` | mesma chave, mesmo run, payload diferente | crítico | `joinads_observation_latest` desempata por `observation_key` (arbitrário) | API que devolve linhas legítimas que diferem só em dimensão não modelada |
| `duplicacao_duplicata_exata_no_run` | mesma chave e payload repetidos no run | aviso | caminho de ingestão duplicado | — |
| `duplicacao_reingestao_suspeita` | mesma leitura (`collected_at`) gravada sob ≥ 2 runs | aviso | replay manual que regrava a mesma coleta | replay deliberado de backfill |
| `duplicacao_releituras_esperadas` | releitura idêntica ou com revisão entre runs | info agregado | D0 horário, D-1 relendo D-7..D-1, termos LAST_7_DAYS — é maturação, não erro | — |
| `zero_sintetizado` | `cost=0 & impressions=0` sem linha de métrica no payload bruto (R3) | ≥ 50% alto; > 0 aviso; só zeros sem prova (payload ausente) info | 88/110 leituras campaign_day reais têm 0/0 (L11): o 0 do Code node não distingue "sem gasto" de "sem linha" | campanha pausada/sem entrega de fato também não tem linha — por isso é "sem prova", não "erro de custo" |
| `reconciliacao_receita_*` | por **domínio × dia** (latest): soma kv por campanha / earnings, só onde há earnings válido E kv (universo da junção da C; R2-G8). Fora dele: `earnings_indisponivel` (aviso), `kv_sem_earnings` (aviso), `earnings_sem_kv` (alto), `sem_base` (info) | §2; `moeda_mista` alto | ponte custo×receita depende de `utm_campaign` numérico na JoinAds (H1 refutada em L5: 97–100%); comparar universos iguais impede que um domínio a 60% seja mascarado pelo kv de um domínio sem earnings | dia corrente intraday (kv e earnings maturam em ritmos diferentes); `earnings_sem_kv` não distingue kv não coletado de kv vazio |
| `reconciliacao_custo_*` | último D0 bem-sucedido × D-1 fechado (lido em dia local > metric_date) | §2; D-1 = 0 com D0 ≠ 0 alto; métrica nula aviso | maturação de custo ou D0 errado | ajustes legítimos da plataforma (cliques inválidos) podem passar de 5% |
| `deriva_distribuicao` | KS 2 amostras (28 dias base × 7 recentes) + efeito robusto mediana/MAD ≥ 0,5, correção de autocorrelação | aviso | quebra de coleta que muda o nível (ex.: custo despenca) | ver §4: poder baixo para mudanças pequenas; sem correção múltipla (alfa por série) |
| `esquema_*` | campos novos (aviso) / ausentes (alto) por fonte × grão × versão; mudança com versão (info) | — | `schema_fingerprint` JoinAds muda sem troca de `collector_version` | campo opcional omitido quando nulo faz o fingerprint oscilar |
| `substituicao_*` | `custom_key` devolvido ≠ pedido (linha ou aviso do run), moeda trocada por conta, campanha em > 1 conta | alto | a fonte devolveu outra coisa que não a pedida | MCC que move campanha de conta de propósito; conta multimoeda real |
| `atribuicao_sensor_*` | sessões pagas com `utm_campaign` / sessões pagas (só agregado) | §2 | R2: o filtro de PII do Sensor v3 descarta `utm_campaign` (L4: 0/28) | evento `volc_sensor_ready` ≠ sessão exata; `paid` só aceita `1`/`true` |
| `obs_status` (A) | distribuição do estado VIGENTE `observacao_as_of(agora)` por fonte × métrica × dia × status/motivo (R2-G7) | invalid alto; missing/late/unavailable aviso; partial info | versões superadas não podem inflar a contagem | — |
| `latencia_*` (A) | p95 de `ingested_at − available_at` por fonte × coletor; relógio ausente | p95 > 1 h aviso | insumo sugerido por A | backfill legítimo |
| `dead_letter_*` (A) | por run finalizado, com a contagem REAL da tabela `dead_letter`: taxa > 5% (`dead_letter_taxa`); dead letters com `n_lidas` 0/nulo (`dead_letter_sem_linhas_lidas` — taxa indefinida não é ok); registrados depois do fechamento (`dead_letter_apos_fechamento`) (R2-G6) | alto | insumo sugerido por A | lote pequeno com 1 linha ruim |

## 4. Detector de deriva — falso alarme e poder medidos

Série sintética de custo diário: log-normal (σ = 0,5 no log), 5% de dias zerados, AR(1) no log com `phi`;
base 28 dias × 7 recentes; alfa = 1%; efeito mínimo 0,5. Seeds 20261016 (falso alarme, 2.000 séries) e 20261017
(poder, 1.000 séries). Reproduzir: `medir_falso_alarme(...)` / `medir_poder(...)` em `qualidade/deriva.py`.

| | `phi` = 0 | `phi` = 0,3 | `phi` = 0,6 |
|---|---|---|---|
| Falso alarme, **com** correção (padrão) | 0,4% | 0,8% | 1,2% |
| Falso alarme, KS cru | 0,6% | 2,85% | **9,2%** |

| Quebra injetada na janela recente | ×0,1 | ×0,5 | ×1,3 | ×1,5 | ×2 | ×3 |
|---|---|---|---|---|---|---|
| Poder com correção (`phi`=0) | 96,8% | 30,2% | 2,6% | 6,5% | 31,1% | 71,9% |
| Poder KS cru (`phi`=0) | 100% | 40,1% | 3,8% | 10,7% | 40,6% | 86,2% |
| Poder com correção (`phi`=0,3) | 76,6% | — | — | — | 20,6% | 47,2% |

Leitura honesta: com 7 pontos, o detector pega **quebra grosseira** (coleta que zera, custo que despenca ou
triplica), não mudança de negócio de ±30–50%. A correção de autocorrelação é o padrão porque custo diário é
persistente e o KS cru passa de 9% de falso alarme com `phi` = 0,6; ela custa poder. Os testes travam: falso alarme
≤ 2% com correção para `phi` ∈ {0; 0,3; 0,6}, KS cru > 5% em `phi` = 0,6 (contraprova), poder ≥ 90% em ×0,1 e
≥ 60% em ×3. Não há view SQL de deriva (teste estatístico fica em Python sobre série exportada).

## 5. Mapa checagem → fonte → view

| Checagem | Fonte (tabelas reais) | View candidata | Equivalência Python×SQL testada |
|---|---|---|---|
| frescor | `google_ads_collection_run`, `joinads_collection_run` (+ lotes para sinal de vida) | `dq_freshness` (sobre `dq_runs`, `dq_slots`) | sim |
| completude por slot | idem | `dq_completude_hora` | sim |
| runs órfãos | idem + `*_raw_batch.collected_at`, `joinads_collection_run.updated_at` | `dq_runs_orfaos` | sim |
| falha silenciosa | idem | `dq_falha_silenciosa` | sim |
| duplicação | `google_ads_observation`, `joinads_observation` | `dq_duplicacao` | sim |
| zero sintetizado | `google_ads_observation` ⋈ `google_ads_raw_batch` ⋈ run | `dq_zero_sintetizado` | sim (e caminho contrato A × direto) |
| reconciliação receita | `joinads_observation_latest` (view real) | `dq_reconciliacao_joinads` | sim |
| reconciliação custo | `google_ads_observation` ⋈ run | `dq_reconciliacao_custo_d0_d1` | sim |
| cobertura de atribuição | `raw_events` (`volc_sensor_ready`, só agregado) | `dq_cobertura_atribuicao_sensor` | sim |
| deriva de esquema | `joinads_raw_batch.schema_fingerprint` | `dq_esquema_joinads` | não (Python compara conjuntos de campos; SQL conta fingerprints) |
| substituição de fonte | `joinads_collection_run.receipt.warnings`, `google_ads_observation`, `joinads_observation` | `dq_substituicao_fonte` | não (dispara/não dispara testado) |
| deriva de distribuição | série exportada | — | n/a |
| latência, dead letter, status, órfãos (dil_obs) | `dil_obs.observacao`, `run_coleta`, `dead_letter`, `lote` (thread A) | `dq_obs_latencia_ingestao`, `dq_obs_dead_letter`, `dq_obs_status`, `dq_obs_runs_orfaos` (`dq_02`, depende de A) | não; dispara/não dispara testado |

Todas as views: `security_invoker = true`, só `SELECT` para `service_role` (dq_01) / `dil_obs_leitor` (dq_02),
nada para PUBLIC/anon/authenticated (revogado mesmo com o default ACL aberto do Supabase), nenhuma coluna
`sid`/`pid`. "Agora" = `dil_qualidade.agora()` (`now()`, ou o GUC de sessão `dil_qualidade.agora` só para teste).
Rollbacks: `dq_01_views_qualidade.down.sql`, `dq_02_views_dil_obs.down.sql` (o schema só cai quando vazio).
Para ler produção **sem criar nada**: `selects_somente_leitura.sql` (gerado das views: auxiliares viram CTEs,
`agora()` vira `now()`; um teste garante que o arquivo commitado é o gerado e que cada SELECT, numa transação
`READ ONLY`, devolve o mesmo que a view). Para o recibo com dado real: `export_recibo_somente_leitura.sql`
(um SELECT, sem payload bruto, sensor agregado).

## 6. Alertas propostos (canal a decidir pelo dono)

| Política | Severidade mínima | Quem acorda | Silêncio por chave | Canal |
|---|---|---|---|---|
| `imediato` | crítico (`frescor_sem_registro`, `duplicacao_conflito_no_run`) | responsável de dados do VOLC (hoje: Tarcisio), a qualquer hora | 1 h | a decidir |
| `horario_comercial` | alto (órfão, zero sintetizado ≥ 50%, receita fora da faixa, sensor < 50%, substituição, campo ausente) | responsável de dados, horário comercial | 4 h | a decidir |
| `digest_diario` | aviso | ninguém acorda; resumo diário | 24 h | a decidir |
| — | info | nunca alerta; fica no recibo | — | — |

`decidir_alertas(achados, agora, politicas, ultimo_envio) -> (alertas, novo_estado)` é pura (não muta a entrada,
deduplica por `(política, regra, fonte, grão, chave, janela)`); `despachar(alertas, sink)` só chama o sink
injetado. Um teste varre o AST do pacote e falha se houver import de `socket`, `urllib`, `http`, `requests`,
`smtplib`, `slack_sdk`, `psycopg` etc.

## 7. Recibo de saúde

`python -m volc_dil.fundacao.qualidade.recibo --cenario producao_conhecida --saida DIR` (sintético) ou
`--entrada export.json --agora <instante> --saida DIR` (dado exportado). Gera `health_receipt.json`
(`schema`, manifesto com seed, versões, `entrada_sha256`, `parametros_sha256`, `codigo_sha256`, contagens e estado;
resumo por severidade/regra; achados com a view equivalente; alertas **propostos, não enviados**; fingerprint que
cobre entrada+parâmetros+código+agora+resultado e exclui versões) e `health_receipt.md`. Mesma entrada + mesmo
código = mesmo fingerprint (testado).

Recibos sintéticos (seed 20261016, agora 2026-10-16T15:00Z, código `c4f24cb9c92984d3…`):

| Cenário | entrada | crítico | alto | aviso | info | alertas propostos |
|---|---|---|---|---|---|---|
| `limpo` | `d8c0a1584aaa942a…` | 0 | 0 | 0 | 5 | 0 |
| `producao_conhecida` | `550380cf6fa8dc90…` | 0 | 9 | 0 | 5 | 9 |
| `estressado` | `b805314e796b3d00…` | 2 | 16 | 11 | 5 | 29 |

## 8. Achados de produção já conhecidos — primeiros casos

Do recibo de leituras externas read-only de 16/10 (`receipts/leituras-externas/RECIBO-LEITURAS-20261016.md`).
Estes casos estão **reproduzidos em forma** no cenário sintético `producao_conhecida`. **Atualização do integrador
(16/10 ~13:04 UTC):** os SELECTs gerados das views rodaram uma vez, read-only e sob demanda, contra produção (3ª rodada
do recibo, `lg_selects_qualidade.sql`): 5 coletores frescos; 3 runs órfãos `alto`; zero sintetizado 80% `alto`;
reconciliação JoinAds 0,968–1,000 `ok`; cobertura de atribuição do sensor 0,0 `alto`. Nenhuma view foi criada em
produção e nada está agendado.

| Caso real | Leitura | Checagem / view que o pega | Severidade esperada |
|---|---|---|---|
| 3 runs `google_ads_collection_run` presos em `running` desde 15/10 11:48 (termos), sem reaper | L9 | `run_orfao` / `dq_runs_orfaos` | alto (×3) |
| 88 de 110 observações campaign_day com `cost_micros = 0` e `impressions = 0` | L11 | `zero_sintetizado` / `dq_zero_sintetizado` (a view separa sem linha / com linha / sem prova) | alto se ≥ 50% sem linha |
| 28 sessões pagas do sensor em 15–16/10, todas com `utm.source` e nenhuma com `utm.campaign` | L4 | `atribuicao_sensor_cobertura_baixa` / `dq_cobertura_atribuicao_sensor` | alto (cobertura 0) |
| termos/keywords com 3 falhas em 24 h | L9 | `completude_slots` (`falha_declarada`) | aviso |
| kv/earnings JoinAds 97–100% em 08–16/10 (H1 refutada) | L5 | `reconciliacao_receita_*` / `dq_reconciliacao_joinads` | ok — é a linha de base que o alerta protege |
| JoinAds v2 em 3 versões de coletor (v2/v3/v4) | L9 | `joinads_observation_latest` já filtra a maior; `dq_esquema_joinads` compara por versão | info |

## 9. Testado hermeticamente × ainda não demonstrado

**Testado hermeticamente / com sintético** (81 testes `test_qualidade_*`, PostgreSQL 16.11 descartável):
todas as checagens do §3 com caso positivo, negativo e de borda; as 15 views de `dq_01` aplicadas sobre o DDL
real (cópia byte a byte de `043c77f5` e `192bc065`, conferida com `git show`) e as 4 de `dq_02` sobre `dil_obs_0001`;
dispara/não dispara por view em três cenários; equivalência Python×SQL de frescor, completude, órfãos, falha
silenciosa, duplicação, zero sintetizado, reconciliações e sensor; parâmetros SQL = Python; grants e
`security_invoker`; rollback e reaplicação; SELECTs read-only = views; export minimizado reproduz os achados;
falso alarme e poder do detector de deriva; alertas sem envio; recibo reprodutível.

**Ainda não demonstrado:** views criadas ou agendadas em produção (só rodaram uma vez como SELECT read-only, ver §8); o DDL real de `raw_events` não
está versionado (a tabela de teste é mínima, R8); limiares não calibrados com dado real (são escolhas
iniciais justificadas acima); deriva só em série sintética; o export real não foi gerado; os workflows n8n não
têm error workflow (R7) — falha antes do primeiro lote continua invisível no ledger e só aparece como
`ausente_silencioso`; o canal de alerta não existe; PostgreSQL 15.8 de produção não testado (sintaxe usada
existe no 15: `security_invoker`, `make_interval`, `percentile_cont`).

## 10. Resposta à revisão adversarial R2

Revisão: `handoffs/REVISAO-ADVERSARIAL-R2.md` (branch da missão @ `2d403e19`). Todo item abaixo tem teste em
`tests/data-intelligence/fundacao/test_qualidade_r2.py` que **falhava antes** da correção (15/15 vermelhos no
código anterior, 15/15 verdes depois).

| Achado | Defeito | Correção | Prova |
|---|---|---|---|
| G8 | reconciliação JoinAds somava kv e earnings de domínios diferentes no dia: um domínio a 60% + kv de domínio sem earnings virava `ok` (98%); earnings indisponível ou kv não coletado de um domínio distorcia o outro | `agregar_receita_joinads`/`avaliar_reconciliacao_receita` e `dq_reconciliacao_joinads` passam a ser por **domínio × dia**, cobertura só com earnings válido (status com valor e receita não nula) E kv no mesmo domínio × dia — a regra da junção da C (R1-F19). Estados novos: `earnings_indisponivel`, `kv_sem_earnings`, `earnings_sem_kv` (substitui `sem_receita_campanha`) | 4 cenários (os 3 de `p_recon.py` com domínios explícitos + mascaramento 60%) em Python e no SQL sobre o DDL real, mesmos estados; equivalência Python×SQL dos 3 cenários sintéticos agora inclui o domínio. Nota: a sonda `p_recon.py` não preenche o domínio (todas as linhas caem no mesmo domínio `NULL`); com domínio nulo o resultado é conservador (`earnings_indisponivel` / cobertura do grupo) |
| G7 | `dq_obs_status` contava versões (o partial superado pelo fechamento contava junto) | a view lê `dil_obs.observacao_as_of(agora)` (estado vigente) | base com 5 versões e 4 fatos: a view devolve 1 observed, 1 missing (aviso), 1 invalid (alto), 1 partial (info) |
| G13 | mutantes G4 (invalid vira ok) e G7 (missing filtrado) sobreviviam aos testes de comportamento | teste aplica cada mutação na view, sobe o banco e exige que a checagem acuse (não depende da guarda do arquivo gerado) | `test_g13_mutantes_de_dq_obs_status_sao_mortos_por_comportamento` (2 mutantes mortos) |
| G6 (parte G) | run com `n_lidas = 0` e dead letters dava taxa NULL e `ok`; dead letter registrado depois do fechamento passava | `dq_obs_dead_letter` conta os dead letters registrados na tabela e classifica `so_dead_letter` / `dead_letter_apos_fechamento` / `taxa_alta` (todos alto); `checar_dead_letter` com a mesma regra | runs reais em `dil_obs` (só dead letters; dead letter tardio; limpo) — view e Python concordam |
| G23 | a ponte usava só `n_inseridas`: run só de confirmações (D2' de A) virava "0 linhas" (falha silenciosa falsa) | `runs_de_run_coleta`: linhas escritas = `n_inseridas + n_confirmadas` | run com 5 confirmações não dispara; run vazio dispara |
| G17 (parte G) | domínio real do cliente em `sintetico.py` | `DOMINIO = "site.exemplo"`; ids de campanha fictícios `9000000000x` | varredura do pacote, views e testes de G sem o domínio, `agenciavolc` ou `GTM-` |

`selects_somente_leitura.sql` regerado. Recibos sintéticos do §7 mudam de `entrada_sha256`/fingerprint (domínio e
ids fictícios) e de código; as contagens por severidade foram reconferidas pelos testes de recibo.
