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
| `…/capacidade/coletor.py` | contrato `run_coleta` + executor seguro (trava por capacidade, `dry_run` nulo, timeout daemon, gravação pelo `Registro` da frente A) |
| `experiments/data-intelligence-lab/scripts/fundacao_capacidade_pg.py` | medição em PostgreSQL 16 descartável (sobe, mede, derruba e apaga) |
| `…/scripts/fundacao_capacidade_horas.py` | extrai o perfil horário real D30 por `git show` (só leitura) |
| `…/scripts/fundacao_capacidade_modelo.py` | roda a grade do modelo e gera `modelo.json` + `MODELO.md` com manifesto |
| `tests/data-intelligence/fundacao/test_capacidade_{cron,volume,cenarios,coletor}.py` | 69 testes (16 + 23 + 7 + 23) |
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
- **Frente A — granularidade de versão**: o `Registro` versiona por payload; se a linha muda, todas as
  métricas da linha ganham versão (com o coletor por linha, isso é o esperado; com payload de lote inteiro,
  qualquer mudança no lote versionaria todas as observações do lote).

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
