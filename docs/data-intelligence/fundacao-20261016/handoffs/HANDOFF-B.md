# HANDOFF-B — Coleta, cadência e capacidade

Worker B, branch `lab/dil-fundacao-20261016-b` (worktree esparso
`worktrees/dil-fundacao-20261016-b`, base `b6e85974`). Nada fora do ownership foi escrito; nada
foi lido de produção; nenhuma rede.

## 1. Arquivos

| Arquivo | O que é |
|---|---|
| `experiments/data-intelligence-lab/src/volc_dil/fundacao/capacidade/__init__.py` | pacote (o `fundacao/` segue namespace package — não criei `fundacao/__init__.py`) |
| `…/capacidade/cron.py` | leitor de cron diário (execuções/dia, intervalos, cobertura) |
| `…/capacidade/volume.py` | modelo puro: linhas lidas × versões distintas, dedup (nenhum/lote/linha/linha-em-lote), índices, partição, retenção+rollup, GTM |
| `…/capacidade/cenarios.py` | escala medida, jobs atuais (agenda confirmada) e vertical completa (proposta), cadências, políticas, perfil horário real |
| `…/capacidade/quotas.py` | limites de API com fonte e estado de confirmação; operações/dia vs Basic/Explorer |
| `…/capacidade/coletor.py` | contrato `run_coleta` + executor seguro (trava read-only, `dry_run` padrão) |
| `experiments/data-intelligence-lab/scripts/fundacao_capacidade_pg.py` | medição em PostgreSQL 16 descartável (sobe, mede, derruba e apaga) |
| `…/scripts/fundacao_capacidade_horas.py` | extrai o perfil horário real D30 por `git show` (só leitura) |
| `…/scripts/fundacao_capacidade_modelo.py` | roda a grade do modelo e gera `modelo.json` + `MODELO.md` com manifesto |
| `tests/data-intelligence/fundacao/test_capacidade_{cron,volume,cenarios,coletor}.py` | 60 testes |
| `docs/data-intelligence/fundacao-20261016/04-CADENCIA-E-CAPACIDADE.md` | política de cadência, números, recomendações |
| `docs/data-intelligence/fundacao-20261016/05-ARQUITETURA-COLETORES.md` | inventário, matriz n8n × Python, arquitetura híbrida, contrato `run_coleta` |
| `docs/data-intelligence/fundacao-20261016/benchmarks/capacidade/{pg_medicoes.json,horas_campanha_d30.json,modelo.json,MODELO.md}` | resultados gerados |

## 2. Provas

```bash
cd worktrees/dil-fundacao-20261016-b
PY=../data-intelligence-overnight-20261015/experiments/data-intelligence-lab/.venv/bin/python
OMP_NUM_THREADS=2 $PY -m pytest tests/data-intelligence/fundacao -q          # 60 passed, ~0,8 s
OMP_NUM_THREADS=2 $PY -m pytest tests/data-intelligence -q                   # 232 passed, ~23 s
OMP_NUM_THREADS=2 $PY -I experiments/data-intelligence-lab/scripts/fundacao_capacidade_pg.py \
    --escalas 1e5,1e6,1e7 --payload-linhas 20000 \
    --saida docs/data-intelligence/fundacao-20261016/benchmarks/capacidade/pg_medicoes.json   # 288 s
$PY -I experiments/data-intelligence-lab/scripts/fundacao_capacidade_horas.py \
    --repo ../data-intelligence-overnight-20261015 --saida docs/.../benchmarks/capacidade/horas_campanha_d30.json
OMP_NUM_THREADS=2 $PY -I experiments/data-intelligence-lab/scripts/fundacao_capacidade_modelo.py   # imprime o fingerprint
```

- **Suíte**: **232 verdes** (172 herdados + 60 novos), 23,2 s. Durante a execução, 3 testes de
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

Ver `04-CADENCIA-E-CAPACIDADE.md` §1 (oito números). Em uma linha: **95,7%** do que o coletor de
termos lê é repetição; a réplica v21 custa **851 B/linha** vs **286 B** tipada; **1,5 TB em 3 anos**
(v21, ×100, vertical completa, horária) vira **34 GB** com dedup de observação + payload por linha em
lote + rollup; a agenda atual cabe em **468 contas** no Basic (94 com D0 a 10 min); `as_of` p50
**0,27 ms** em 1e7; ingestão **150–190 mil linhas/s**; a madrugada é **7,6%** do gasto e o D0 06–23
não perde dado, só frescor.

## 4. Limitações

- Bytes de dados sintéticos com DDL de medição próprio (o SQL do worker A não existia); a réplica v21
  segue o DDL real, não o conteúdo real. A compressão do payload sintético é otimista.
- λ, fração mutável, p de revisão, consultas JoinAds por execução, geos/campanha e bytes/evento GTM
  são premissas (listadas em `modelo.json → premissas`); λ é calibrado por um agregado D30 de uma conta.
- Perfil horário é D30 agregado por hora, não data × hora: não mede variância noturna dia a dia.
- O coletor seguro só foi exercitado com fakes; não há adaptador real nem sink Postgres.
- O pico de disco passou ~2% do teto combinado.

## 5. Riscos

1. **Re-execução duplica no v21**: chave do run = `workflow_id:execution_id`
   (J:P/collector-inventory.json:120) + `UNIQUE (run_id, observation_key)`; um retry manual do mesmo
   slot gera cópia integral. Leitor que soma sem escolher versão infla custo.
2. **Quota compartilhada**: o Basic é por developer token, somando MCP, scripts e sincronizador; o
   nível do token da VOLC **não está confirmado**. Encurtar cadência sem conhecer o nível pode
   derrubar toda a coleta com `RESOURCE_EXHAUSTED`.
3. **Co-autoridade**: D0/D-1 e JoinAds têm legado latest-wins e canônico append-only escrevendo o mesmo fato.
4. **Sem error workflow/dead letter**: falha antes do 1º lote é invisível no banco.
5. **Formato longo**: se o contrato da frente A adotar uma linha por métrica, o custo por valor é
   7,2× o do formato largo (258 vs 36 B).

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
