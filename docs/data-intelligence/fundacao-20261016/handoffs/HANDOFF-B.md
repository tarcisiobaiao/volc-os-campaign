# HANDOFF-B — Coleta, cadência e capacidade

Worker B, branch `lab/dil-fundacao-20261016-b` (worktree esparso
`worktrees/dil-fundacao-20261016-b`, base `b6e85974`; após a R1, merge local de
`lab/data-foundation-20261016` em `e8a27bdb`). Nada fora do ownership foi escrito; esta frente não leu
produção (os três números reais usados vêm do recibo read-only do integrador); nenhuma rede.
**A resposta à revisão adversarial R1 está na §8.**

## 1. Arquivos

| Arquivo | O que é |
|---|---|
| `experiments/data-intelligence-lab/src/volc_dil/fundacao/capacidade/__init__.py` | pacote (o `fundacao/` segue namespace package — não criei `fundacao/__init__.py`) |
| `…/capacidade/cron.py` | leitor de cron diário (execuções/dia, intervalos, cobertura) |
| `…/capacidade/volume.py` | modelo puro: linhas lidas × versões distintas, dedup (nenhum/lote/linha/linha-em-lote), índices, partição, retenção+rollup, GTM |
| `…/capacidade/cenarios.py` | escala medida, jobs atuais (agenda confirmada) e vertical completa (proposta), cadências, políticas, perfil horário real |
| `…/capacidade/quotas.py` | limites de API com fonte e estado de confirmação; operações/dia vs Basic/Explorer |
| `…/capacidade/coletor.py` | contrato `run_coleta` + executor seguro (trava por capacidade, `dry_run` nulo, timeout daemon, gravação pelo `Registro` da frente A com D1/D2, `observed_at` = carimbo real da leitura) |
| `experiments/data-intelligence-lab/scripts/fundacao_capacidade_pg.py` | medição em PostgreSQL 16 descartável (sobe, mede, derruba e apaga) |
| `…/scripts/fundacao_capacidade_horas.py` | extrai o perfil horário real D30 por `git show` (só leitura) |
| `…/scripts/fundacao_capacidade_modelo.py` | roda a grade do modelo e gera `modelo.json` + `MODELO.md` com manifesto |
| `tests/data-intelligence/fundacao/test_capacidade_{cron,volume,cenarios,coletor}.py` | 73 testes (16 + 24 + 7 + 26) |
| `docs/data-intelligence/fundacao-20261016/04-CADENCIA-E-CAPACIDADE.md` | política de cadência, números, recomendações |
| `docs/data-intelligence/fundacao-20261016/05-ARQUITETURA-COLETORES.md` | inventário, matriz n8n × Python, arquitetura híbrida, contrato `run_coleta` |
| `docs/data-intelligence/fundacao-20261016/benchmarks/capacidade/{pg_medicoes.json,pg_medicoes_dil_obs.json,horas_campanha_d30.json,modelo.json,MODELO.md,MEDICOES.md}` | resultados gerados (`MEDICOES.md` = todas as medições, sem seleção) |

## 2. Provas

```bash
cd worktrees/dil-fundacao-20261016-b
PY=../data-intelligence-overnight-20261015/experiments/data-intelligence-lab/.venv/bin/python
OMP_NUM_THREADS=2 $PY -m pytest tests/data-intelligence/fundacao -q -k capacidade   # 69 passed, ~4 s
OMP_NUM_THREADS=2 $PY -m pytest tests/data-intelligence -q                   # suíte inteira (ver §8.4)
OMP_NUM_THREADS=2 $PY -I experiments/data-intelligence-lab/scripts/fundacao_capacidade_pg.py \
    --escalas 1e5,1e6,1e7 --payload-linhas 20000 \
    --saida docs/data-intelligence/fundacao-20261016/benchmarks/capacidade/pg_medicoes.json   # 1.643 s (máquina disputada)
OMP_NUM_THREADS=2 $PY -I experiments/data-intelligence-lab/scripts/fundacao_capacidade_pg.py \
    --escalas 1e5,1e6 --apenas-dil-obs \
    --saida docs/data-intelligence/fundacao-20261016/benchmarks/capacidade/pg_medicoes_dil_obs.json   # 878 s
$PY -I experiments/data-intelligence-lab/scripts/fundacao_capacidade_horas.py \
    --repo ../data-intelligence-overnight-20261015 --saida docs/.../benchmarks/capacidade/horas_campanha_d30.json
OMP_NUM_THREADS=2 $PY -I experiments/data-intelligence-lab/scripts/fundacao_capacidade_modelo.py   # imprime o fingerprint
```

- **Suíte (1ª entrega)**: **232 verdes** (172 herdados + 60 novos), 23,2 s. **Após a R1**: 659 verdes em
  107 s no worktree com o merge de `lab/data-foundation-20261016` (§8.4). Durante a 1ª execução, 3 testes de
  `test_surrogate.py` falharam com `FileNotFoundError` porque o CSV
  `backend/app/trafego/shadow_experimentos/senac-shadow-20261015/transformacao.csv` estava fora do
  sparse checkout; depois alguém (não esta frente) acrescentou esse caminho e `backend/tests/goldens/`
  ao sparse set do worktree, e a suíte inteira passou. Nenhum arquivo herdado foi alterado
  (`git diff --name-only b6e85974 HEAD` só lista o ownership de B).
- **Calibração**: o modelo reproduz exatamente as contagens reais por execução — D0 5 linhas,
  termos+keywords 2.242 linhas em 2 lotes, JoinAds D1 209 linhas em 64 lotes
  (`test_modelo_reproduz_contagens_reais_por_execucao`).
- **Postgres descartável**: cluster em `experiments/data-intelligence-lab/artifacts/fundacao_capacidade_pg/`
  (gitignored), socket em `/private/tmp/pgfb-*`, `listen_addresses=''`, porta 54931; 1e5/1e6 com 5
  variantes, 1e7 com a variante longa com e sem partição; **pico 4,08 GiB** (levemente acima do teto
  de ~4 GB — a guarda estimava as tabelas, não o WAL); `cluster_apagado: true`; `artifacts/` vazio e
  nenhum `/private/tmp/pgfb-*` restante ao fim (verificado).
- **Manifesto do modelo**: `modelo.json → manifesto` com seed, versões (python, numpy, scipy,
  duckdb, polars…), sha256 do código de `capacidade/*.py` + script, sha256 das duas entradas e do
  resultado; `MODELO.md` repete os prefixos.

## 3. Resultados principais

Ver `04-CADENCIA-E-CAPACIDADE.md` §1 (oito números, corrigidos na R1). Em uma linha: termos têm
**89,4%** de redundância medida com 21 h de vida e **97,1%** esperados em regime; a linha real da v21 custa
**1.140 B** vs **286 B** tipada; **1,9 TB em 3 anos** (v21 real, ×100, vertical completa, horária) vira
**30 GB** com dedup + payload por linha em lote + rollup; a agenda atual cabe em **162 contas** no Basic
(24 com D0 a 10 min); `as_of` pontual p50 **0,22 ms** em 1e7; a função `observacao_as_of` da frente A
leva **8,5–17,5 s** em 1e6 linhas (inline: 0,18–0,32 s); a madrugada é **7,6%** do gasto e o D0 06–23
não perde dado, só frescor.

## 4. Limitações

- Bytes de dados sintéticos; réplica v21 e `dil_obs_0001` seguem DDLs reais, não o conteúdo real; só a
  linha da v21 (1.140 B) é real. A compressão do payload sintético é otimista.
- A redundância de termos medida é de um coletor com 21 h de vida (H5); a de regime é modelada.
- λ, fração mutável, p de revisão, consultas JoinAds por execução, geos/campanha e bytes/evento GTM
  são premissas (listadas em `modelo.json → premissas`); λ é calibrado por um agregado D30 de uma conta.
- Perfil horário é D30 agregado por hora, não data × hora: não mede variância noturna dia a dia.
- O coletor seguro só foi exercitado com fakes; não há adaptador real nem sink Postgres.
- Na 1ª rodada o pico de disco passou ~2% do teto combinado (4,08 GiB); nas rodadas da R1, com
  amostrador de disco a cada 0,5 s e folga de WAL na guarda, os picos foram 3,20 e 2,33 GiB.
- As latências da rodada da R1 foram medidas com a máquina disputada por outros workers (piores que a 1ª rodada).

## 5. Riscos

1. **Re-execução duplica no v21**: chave do run = `workflow_id:execution_id`
   (J:P/collector-inventory.json:120) + `UNIQUE (run_id, observation_key)`; um retry manual do mesmo
   slot gera cópia integral. Leitor que soma sem escolher versão infla custo.
2. **Quota compartilhada**: o Basic é por developer token, somando MCP, scripts e sincronizador; o
   nível do token da VOLC **não está confirmado**. Encurtar cadência sem conhecer o nível pode
   derrubar toda a coleta com `RESOURCE_EXHAUSTED`.
3. **Co-autoridade**: D0/D-1 e JoinAds têm legado latest-wins e canônico append-only escrevendo o mesmo fato.
4. **Sem error workflow/dead letter**: falha antes do 1º lote é invisível no banco.
5. **Formato longo da frente A**: o `dil_obs_0001` custa 1.084 B por valor (30× o largo tipado); com ele a
   política recomendada a ×100 vai de 30 GB para 217 GB em 3 anos. E `observacao_as_of`/`observacao_latest`
   não são inlinadas (48–55× mais lentas que a consulta equivalente) — §8.3.

## 6. Leituras externas read-only que confirmariam as premissas

Executar só por caminho autorizado, sem imprimir credencial. `grain`/`resource_type` devem ser
ajustados aos valores reais (ler 1 linha antes).

```sql
-- (a) redundância real e p(mudou) por hora no D0 canônico (calibra λ e fração mutável)
with o as (
  select campaign_id, metric_date, collected_at, metrics,
         lag(metrics) over (partition by campaign_id, metric_date order by collected_at) as prev
  from google_ads_observation
  where resource_type = 'campaign' and metric_date >= current_date - 7)
select extract(hour from collected_at at time zone 'America/Sao_Paulo') as hora,
       count(*) as leituras, avg((metrics is distinct from prev)::int) as p_mudou
from o where prev is not null group by 1 order by 1;

-- (b) redundância real do coletor de termos (95,7% previsto)
select count(*) as lidas, count(distinct (observation_key, metrics)) as distintas
from google_ads_observation
where resource_type = 'search_term_view' and collected_at > now() - interval '7 days';

-- (c) revisão de dia fechado entre as passadas do D-1 (p de revisão, previsto 0,3)
select metric_date, count(distinct metrics) as versoes
from google_ads_observation
where resource_type = 'campaign' and grain like '%d1%' and metric_date >= current_date - 14
group by 1 order by 1;

-- (d) tamanho real por linha e uso dos índices (GIN de metrics candidato a remoção)
select relname, n_live_tup, pg_total_relation_size(relid) / greatest(n_live_tup, 1) as bytes_por_linha
from pg_stat_user_tables where relname in ('google_ads_observation', 'google_ads_raw_batch', 'joinads_observation', 'joinads_raw_batch', 'raw_events');
select indexrelname, idx_scan, pg_relation_size(indexrelid) as bytes
from pg_stat_user_indexes where relname in ('google_ads_observation', 'joinads_observation') order by idx_scan;

-- (e) compressão real do payload bruto
select avg(pg_column_size(payload)) as bytes_armazenados, avg(octet_length(payload::text)) as bytes_json,
       avg(row_count) as linhas_por_lote
from google_ads_raw_batch where collected_at > now() - interval '7 days';
```

GAQL (1 operação por conta) para a decisão 06–23 × 24 h — consulta e regra pré-registrada em
`04-…` §4. Nível de acesso do developer token: consultar o Google Ads API Center da conta MCC
(leitura humana; não está no repositório).

## 7. Delta de curadoria proposto (só proposta; aplica o integrador)

| Tarefa | Estado proposto | Evidência nova | Lacunas que continuam |
|---|---|---|---|
| **P06-T02** Consolidar ingestão de custo por data e conta | manter `partial` | modelo + medição mostram que a consolidação deve gravar só versões que mudaram e uma linha larga tipada (286 B vs 851 B da réplica v21); política de cadência D0/D-1 justificada | consumidores de `daily_campaign_metrics` não inventariados; co-autoridade D0/D-1 ativa |
| **P06-T08** Ledger canônico de coleta Google Ads | manter `partial` | idempotência por execução (não por slot) identificada como risco de duplicação; medição da réplica v21 (índices 26%, GIN de metrics sem uso para `as_of`); proposta de chave `coletor:conta:janela:slot` | aceite exige migration/rollback e canário — nada aplicado aqui |
| **P09-T14** Operacionalizar a coleta contínua | manter `partial` | política de frequência por fonte com custo em operações/dia e quota (468 contas no Basic na agenda atual); termos 4 h → 1×/dia (−83% de operações e leituras do job); contrato `run_coleta` com heartbeat, recibo e dead letter testado | autoridade de agenda única não decidida; alerta por atraso inexistente; nível do token não confirmado |
| **P10-T04** Heartbeat e deadman | manter `partial` | executor registra heartbeat em início/retry/fim e recibo terminal (testado com relógio injetável); proposta de watchdog = 2× intervalo da agenda | estados saudável/atrasado/falhou/nunca/desabilitado/indeterminado não modelados nesta frente; nenhum alerta |
| **P10-T16** Workflows n8n ao ledger e autoridade de agenda | manter `partial` | matriz n8n × Python por critério e arquitetura híbrida (n8n agenda e credencial; Python contrato e gravação; um autor por verdade) | ADR não escrito; dependência Meta (hierarquia adset) intocada |

Nós do grafo afetados (proposta): coletores `Ps9yLfQkHeaAbyZZ`, `7yxs1aOlzWkkkSf9`,
`TFlmThr4930oPneE`, `cpb6tNxt211UkAn2`, `jDX397ViVcRQft4A`; tabelas `google_ads_observation`,
`google_ads_raw_batch`; novo nó de código `volc_dil.fundacao.capacidade` (lab, não operacional).
Nenhum estado deve ir a `done`: tudo aqui é `construído`/`testado hermeticamente`/`testado com sintético`.


## 8. Resposta à revisão adversarial R1

Base: merge local `git merge --no-ff lab/data-foundation-20261016` (a ponta já estava em `e8a27bdb`,
que contém `413395a5`; sem push). Provas do revisor relidas em `/private/tmp/claude-502/r1-scratch/py/`
(`t_coletor.py`, `t_par.py`, `t_hang.py`).

### 8.1 Achados de B

| # | Veredito | O que mudou | Prova |
|---|---|---|---|
| **F7** quota ~3× subestimada | **aceito** (com ajuste de 1 consulta fixa) | `Job` ganhou `consultas_fixas_por_execucao` (listagem `customer_client` do MCC, não escala com contas) e `lotes_por_execucao`; D0/D-1 = 1 fixa + **4 GAQL por conta**, termos = 1 + listagem de contas (J:P/collector-inventory.json:111-117,136-142,161-168); `quotas.contas_maximas` com operações = a·contas + b. Agenda atual: **92 por conta + 26 fixas → 162 contas** no Basic (revisor: 163, sem a parte fixa); D0 10 min: **24** (revisor: 25); termos 1×/dia: 182. `MODELO.md`, 04 §1/§3/§7 regenerados | `test_quota_basic_documentada_e_consumo_atual`, `test_consultas_fixas_nao_escalam_com_contas`, `test_modelo_reproduz_contagens_reais_por_execucao` (D0 = 5 chamadas/execução) |
| **F10** A→B→A perdido; equivalência só aparente | **aceito** | o executor não tem mais dedup próprio: cada linha vira payload endereçado por conteúdo, normalizado por `volc_dil.fundacao.observacao.normalizar` e registrado pelo `Registro` da frente A (INSERIDO/NOOP/REAFIRMADO); `available_at` = relógio monotônico do sink na gravação; em lote a leitura pode ser paralela mas a **gravação é serial e ordenada por (slot, conta, coletor)** — sem isso, a regra 2b do `Registro` (reentrega fora de ordem é NOOP) também perderia o A final | `test_a_b_a_e_preservado_como_reafirmacao` (as_of 10→20→10); `test_equivalencia_serial_paralelo_compara_as_of_em_todos_os_cortes` (18 cortes, 8 rodadas paralelas, pedidos embaralhados); mutante "gravar na ordem de chegada" **morto** |
| **F11** dry_run grava; trava por nome | **aceito** | dry_run usa sink nulo: nada é gravado (nem heartbeat, recibo, dead letter). Trava por capacidade: o adaptador recebe a cada leitura um `ClienteLeitura` imutável cuja única operação é `consultar(ConsultaLeitura)` (só GAQL `SELECT` único ou HTTP `GET` https); o transporte vai para o executor, não para o adaptador; `gravar` só aceita `SinkMemoria` de tipo exato. Limite declarado: Python não impede código hostil de abrir a própria conexão | `test_dry_run_e_padrao_e_nao_toca_o_sink_nem_em_falha`, `test_consulta_so_admite_leitura` (5), `test_adaptador_nao_alcanca_o_transporte…`, `test_trava_recusa_destino…` (4) |
| **F12** fonte presa impede saída | **aceito** | prazo restante propagado ao transporte (timeout no cliente) + leitura numa thread *daemon*; tentativa estourada é abandonada | `test_fonte_presa_nao_impede_o_processo_de_sair`: subprocesso com fonte presa 60 s e timeout 0,2 s sai em < 10 s (antes: 20 s no `t_hang.py`) |
| **F13** 851 B vs 1.140 B; 89,4% vs 95,7% "2,4× em distintas" | **bytes: aceito; razão de distintas: contestado com prova** | perfil `v21_real` (1.140 B) ao lado da réplica em toda a grade; razão de distintas real **10,6%** × prevista **4,3%** (p = 0,02) reportada. Contestação: o coletor tinha ~21 h e 13 execuções (recibo :69). Com p = 0 e as janelas reais (10 execuções lendo 08–14/10, 3 lendo 09–15/10), o modelo prevê **2.546 distintas** — real **2.525** (−0,8%); com p = 0,02 preveria > 2.900. A diferença é idade do coletor (H5), não premissa errada; o recibo é compatível com p ≈ 0. p de termos recalibrado de 0,02 para **0,005** (limite superior). Efeito na recomendada (×100, vertical horária, 3 anos): p = 0 → 28,9 GB; 0,005 → 30,2; 0,02 → 34,0; 0,084 (calibração ingênua pelos 10,6%) → 50,2 GB | `test_redundancia_de_coletor_jovem_reproduz_o_recibo_real_com_p_zero`; `MODELO.md` §4b |
| **F26** amostra fina, corte seletivo, as_of global não medido | **aceito** | n: `as_of` 2.000 → 5.000, snapshot 30 → 60, ingestão 15 → 60; percentis mín/p50/p95/p99/máx/média/desvio; **todas** as medições em `MEDICOES.md`; amostrador de disco; DDL **real** `dil_obs_0001` medido com `as_of` global (`observacao_as_of`, `observacao_latest` e consulta inline) | `pg_medicoes.json`, `pg_medicoes_dil_obs.json`, `MEDICOES.md` |
| **F25 parte B** dados reais versionados | **aceito** | `cenarios.py`: perfil horário só em fatias (1/100.000), sem customer_id, id de campanha nem nome da conta; `horas_campanha_d30.json` sanitizado (só fatias e taxa de impressões); 04/05: sem id de campanha, sem container GTM, sem valores em R$/US$. Mantidos: IDs de workflow n8n (identificadores internos necessários para auditar o inventário — o integrador decide) e contagens agregadas não monetárias (impressões/h, 115 eventos, 819 cliques) | `test_cenarios_nao_versionam_identificador_real`; varredura `rg` por `\b\d{10,11}\b`, `R$`, `GTM-`, nome da conta: 0 ocorrências nos arquivos de B |
| **H5** janela de 7 dias × vida do coletor | **aceito** (confirmado pelo integrador, recibo :69) | 04 §3 diz que nem 89,4% nem 97,1% são medida de regime e pede repetir a consulta (b) após ≥ 7 dias contínuos | `redundancia_observada` |

### 8.2 Números corrigidos

| Número | 1ª entrega | Após R1 |
|---|---|---|
| Operações Google Ads/dia por conta (agenda atual) | 32 | 92 + 26 fixas |
| Contas no Basic (agenda atual / D0 10 min) | 468 / 94 | **162 / 24** |
| Bytes da linha v21 | 851 (réplica) | **1.140 (real)**; réplica 851 mantida |
| v21, ×100, vertical horária, 3 anos | 1,5 TB | **1,9 TB** (real) |
| Recomendada, idem | 34 GB | **30 GB** (p de termos 0,005; dedup linha em lote) |
| Redundância de termos | 95,7% modelada | 89,4% medida (21 h) · 97,1% modelada em regime |
| `as_of` pontual p50 1e7 | 0,27 ms (n = 2.000) | 0,22 ms (n = 5.000), p99 1,25 ms |
| Ingestão 1.000 linhas p50 | 5–6,5 ms (n = 15) | 11–21 ms (n = 60, máquina disputada) |
| `as_of` global 1e6 (DDL da frente A) | não medido | função 8,5–17,5 s; inline 0,18–0,32 s; `latest` 19 s |

### 8.3 Achados novos para outras frentes (prova em `MEDICOES.md`)

- **Frente A — `observacao_as_of` não é inlinada**: a função tem `SET search_path = ''`, o que impede o
  inlining; o resultado inteiro é materializado. 1e6 linhas: 8,5 s (meio) e 17,5 s (fim) contra 0,18 s e
  0,32 s da mesma consulta inline com linha inteira (48–55×); `observacao_latest` 19 s (máx 38,8 s).
- **Frente A — custo do formato longo**: `dil_obs_0001` = 1.084 B por valor (630 heap + 453 índices); três
  índices sobre texto hex de 64 caracteres somam 370 B/linha, e `ix_obs_chave_base` duplica
  `uq_obs_chave_idempotencia` em toda linha `leitura`. A política recomendada a ×100 vai de 30 GB (largo
  tipado) para 217 GB (DDL atual) em 3 anos.
- **Frente A — granularidade de versão**: o `Registro` versiona por leitura; se a linha muda, todas as
  métricas da linha ganham versão (superado por D2: agora toda releitura é versão — §8.6).

### 8.4 Suíte e limpeza

- Suíte inteira: **659 verdes** em 107 s (`tests/data-intelligence`, inclui todas as frentes após o merge);
  capacidade: 69 testes (60 antes da R1; +9 líquidos, coletor reescrito de 17 para 23).
- Clusters das duas rodadas apagados (`cluster_apagado: true`), `artifacts/` vazio, nenhum socket
  `/private/tmp/pgfb-*` restante; picos de disco 3,20 e 2,33 GiB.

### 8.5 Delta de curadoria (atualiza §7, só proposta)

Sem mudança de estado (todas `partial`). Evidência nova a anexar: P09-T14 — capacidade real de 162
contas no Basic com a agenda atual e custo de cada cadência (04 §3); P10-T04 — dry_run nulo e heartbeat só
em `gravar`; P06-T08 — 1.140 B/linha real, GIN com 0 scans, `observacao_as_of` não inlinada (insumo para a
frente A antes de qualquer migration).

### 8.6 Integração com D1/D2 da frente A (merge de `ff1ea21d` + `d62bf0c0` do integrador)

Regras novas da frente A (`HANDOFF-A.md` §7.1): **D1** — a versão vigente é a de maior `observed_at`
(empate → maior `available_at`); **D2** — `observed_at` entra na chave da leitura: retry é NOOP, releitura
em outra hora é versão nova; não existe mais reafirmação. O integrador já tinha adaptado o coletor
(`reafirmadas` removido; A→B→A esperando (3,0),(3,0),(3,0)). Restavam duas falhas, resolvidas assim:

| Teste | Decisão | Por quê |
|---|---|---|
| releitura igual às 07:00 | **asserção ajustada**: `inseridas == 9`, `noop == 0`, 18 observações, **3 payloads** (o bruto continua deduplicado por conteúdo); novo teste `test_retry_da_mesma_leitura_e_noop` (mesmo carimbo = mesma leitura = NOOP) | é a semântica de D2; o custo está documentado (abaixo) |
| equivalência serial × paralelo | **semântica nova: mesmas leituras ⇒ mesma história.** `observed_at` = carimbo do transporte (`RespostaLeitura.observado_em`), ou o fim da leitura se o transporte não carimbar; validado ≤ `available_at` (senão dead letter `observado_em_invalido`). O teste usa um transporte que carimba cada pedido de forma determinística e compara o conjunto de versões (chave, status, valor, `observed_at`), o `as_of` nos 18 cortes e os instantes de gravação, em 8 rodadas paralelas | sob D1 o que ordena é `observed_at`; leituras feitas em instantes diferentes SÃO leituras diferentes, então exigir igualdade sem fixar o instante seria exigir o falso |

**Por que não `observed_at` = slot.** Uma execução atrasada (fila, retry com backoff, backfill, n8n
parado) lê o estado da fonte no instante em que roda. Carimbar com o slot antigo afirmaria que o estado das
09h era o das 06h; sob D1, essa leitura nova (mas carimbada como velha) perderia para uma leitura de fato
mais antiga, ou sobrescreveria o histórico daquele horário — retroatividade do mesmo tipo de F1. O slot
continua sendo a chave de execução (idempotência do run); o instante da medição é outra coisa.
Mutante "ignorar o carimbo e usar só o fim da leitura": 4 testes falham.

Novo teste de D1: `test_d1_gravacao_fora_de_ordem_nao_desfaz_a_leitura_mais_recente` — gravar 06→07→08 ou
08→07→06 dá as mesmas versões e o mesmo estado final (A); no invertido, o conhecimento intermediário nunca
mostra B (a leitura das 07h chega depois da das 08h e não a desfaz).

**Custo de D2 (histórico — superado pelo D2' na §8.7; política `registro_d2`, payload ainda deduplicado).** A dedup de observação que eu
recomendava (−94%) deixa de acontecer no `Registro`/`dil_obs`: toda releitura vira linha.

| Cenário | v21 real | recomendada (largo, dedup) | D2 sobre largo tipado | **D2 sobre DDL longo da frente A** |
|---|---:|---:|---:|---:|
| hoje, 1 conta, MB/dia | 17,5 | 0,43 | 4,0 | **70,7** |
| ×100, vertical horária, 13 meses | 704 GB | 22 GB | 163 GB | **2,9 TB** |
| ×100, vertical horária, 3 anos | 1,9 TB | 30 GB | 450 GB | **7,9 TB** |

DDL pós-D2 medido (1e5; disco livre caiu para ~6 GiB com outro worker rodando PostgreSQL, por isso não
repeti 1e6): **1.043 B por valor** (antes 1.084); `observacao_as_of` continua não inlinada (0,65 s × 0,045 s
inline em 1e5). Proposta para a frente A/integrador: manter D1/D2 para a ordem do `as_of` e a passagem de
`partial` a fechada, mas registrar releitura idêntica numa tabela estreita de leituras (ou só no recibo do
run) em vez de uma linha completa por métrica.

Testes: capacidade **72** (coletor 26). Suíte inteira após o merge de `ff1ea21d`: **798 verdes** em 104 s.

### 8.7 DDL final da frente A e D2' (merge de `962b868c`)

A frente A entregou o `dil_obs_0001` final (HANDOFF-A §7.2): `observacao_as_of` inlinável, chaves `bytea` de
32 bytes, sem índice em `lote_id`, e **D2'** — versão só quando o estado muda; releitura igual vira
**confirmação** estreita em `dil_obs.confirmacao`; retry continua NOOP. O coletor já tinha sido adaptado
pela A (`ReciboRun.confirmadas`); aqui só renomeei o teste de releitura para
`…_e_confirmacao_d2_linha` e ajustei comentários. A política `registro_d2` saiu do modelo e entrou
`registro_d2_linha` (versões quando muda + uma confirmação por observação relida sem mudança), com
`PerfilBytes.confirmacao_por_observacao` medido; e `registro_d2_linha_13m` (com partição, bruto 13 meses e
rollup) como mitigação.

**Medição** (cluster único, teto 3 GiB, pico amostrado 1,25 GiB, 155 s, cluster apagado;
`pg_medicoes_dil_obs.json` substituído; o arquivo pós-D2 intermediário foi removido):

| 1e6 | heap B/linha | índices B/linha | total B |
|---|---:|---:|---:|
| `dil_obs.observacao` final | 500,1 | 322,9 | **823,1 por valor** (A: 787; antes 1.043–1.084) |
| `dil_obs.confirmacao` | 126,1 | 100,3 | **226,4 por confirmação** (A: 211) |

`as_of` com o DDL final em 1e6: função 0,164 / 0,363 s (meio / fim), à mão 0,189 / 0,290 s, `latest`
0,399 s, ponto p50 0,020 ms — a não inlinação foi resolvida pela A. A diferença de 787 × 823 B é do gerador
sintético (textos de `conta`/`entidade_id` e distribuição de versões), não do DDL.

**Tabela final** (modelo; "hoje" = 1 conta, agenda atual; ×100 = vertical completa, horária 24 h):

| Política | hoje | ×100, 13 meses | ×100, 3 anos |
|---|---:|---:|---:|
| v21 real (1.140 B/linha, sem dedup) | 17,5 MB/dia (6,8 GB em 13 m) | 704 GB | 1,95 TB |
| recomendada (largo tipado, dedup, rollup, 13 m) | 0,43 MB/dia (0,17 GB em 13 m) | 22 GB | 30 GB |
| **D2' sobre `dil_obs` final** | **17,3 MB/dia** (6,7 GB em 13 m) | **734 GB** | **2,03 TB** |
| D2' + termos 1×/dia | 5,1 MB/dia | 259 GB | 717 GB |
| D2' + partição, bruto 13 m + rollup | 17,5 MB/dia | 743 GB | 751 GB |

Leitura: o D2' resolve a explosão do D2 (7,9 TB → 2,0 TB) e empata com a v21 real em bytes, mas com
`as_of` correto, confirmação de frescor e reparo independente de ordem. As confirmações são ~79% dos bytes
(1,47 de 1,85 GB/dia a ×100). O modelo é conservador (mudança contada por linha; o D2' decide por
observação — no teste A→B→A, 1 versão e 2 confirmações por leitura). A estimativa proporcional da A (~17
MB/dia e ~1,9 TB em 3 anos) bate com o modelo (17,3 MB/dia e 2,03 TB). Alavancas restantes: termos 1×/dia
(−65%), referências inteiras de run/lote na confirmação, retenção curta só das confirmações.

Testes: capacidade **73** (volume 24: +1 de D2'). Suíte inteira após o merge de `962b868c`: **879 verdes, 1 skip** (o skip é a medição grande da frente A) em 130 s.
