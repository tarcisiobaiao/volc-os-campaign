# Recibo — rodada autorizada (itens 1, 2 e 9), 16–17/10/2026

Autoridade: mensagem do Tarcisio de 2026-10-16 19:00 UTC na thread "Fundação Data Intelligence: missão
multiagente" (autoriza 1, 2 e 9; proíbe 3–8). Executada uma vez por esta sessão, entre 2026-10-17 01:55 e
~03:00 UTC. Nada aqui é dado bruto: só consultas sanitizadas, contagens, intervalos, hashes e horários.

## 0. Baseline

| Item | Valor |
|---|---|
| Worktree | `worktrees/data-intelligence-overnight-20261015` |
| Branch | `lab/data-foundation-20261016` (local, sem push) |
| HEAD inicial | `a6e54d1a` — árvore limpa |
| Outras sessões nesta worktree | nenhuma (só o processo desta sessão tinha `cwd` aqui; a sessão anterior da Fundação estava inativa desde 21:41 UTC) |
| Disco | 55 GiB livres |
| Grafo | `--check` → `current: false` ("código, SQL ou fonte operacional mudou"), construído em `6124c550` |
| Autoridade Supabase | `verificar_autoridade_supabase.py` → `https://database.agenciavolc.com.br` |

## 1. Item 1 — snapshot read-only e replay

**Transação.** Todas as leituras de banco: SSH → `docker exec supabase-db psql` com
`PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=…`, dentro de
`BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY … ROLLBACK`. A exportação gravou a prova no `meta.json`
(`transaction_isolation = repeatable read`, `transaction_read_only = on`, `snapshot_at = 2026-10-16T23:00:43-03:00`);
o pseudonimizador recusa a saída se isso não vier.

**Consultas** (todas nesta pasta): `export_snapshot.sql` (exportação); `meta.sql`, `meta2.sql` (schema, contagens e
nomes de chaves de payload, sem valores); `zstat.sql` (status declarado × linha de métrica, agregado);
`re_meta.sql`, `re_agg.sql` (catálogo de `raw_events` e contagem de sessões pagas por versão do sensor — insumo do
ponto 5, só agregados).

**Colunas.** v21 `campaign_day` com as colunas da junção de 02 §9.1, sem `dimensions` (traz nome de campanha),
`attributes`, `receipt`, payload bruto, termos ou keywords; do payload só saem "linha de métrica presente" e o
conjunto de moedas declaradas. JoinAds v2: só `earnings` e `key_value_campaign_adunit`. Nenhuma das tabelas
exportadas tem e-mail, IP, user agent, click id, token ou URL.

**Pseudonimização.** `pseudonimizar_export.py` lê o fluxo do SSH em memória (nada cru vai a disco) e troca 709
identificadores por HMAC-SHA256 com chave aleatória local; ids numéricos viram 12 dígitos no mesmo espaço
"campaign" para Google e JoinAds (a junção sobrevive: 1 de 1 valor kv casa com uma campanha Google). Verificação
final: 0 identificador cru na saída, 0 colisão.

| Arquivo (fora do Git) | Linhas | sha256 |
|---|---:|---|
| `v21.jsonl` | 175 | `8282aacfd9860ed5f0619085756d0509840c58ee6ebe4e5a24c4a708a42438e3` |
| `v21_run.jsonl` | 51 | `af51334aef46652df6406ae17fa9b1c019d65c96c6aa009ca046503008fc5da9` |
| `joinads.jsonl` | 200 | `fff3c19ac288827a4e52c37de50c3a6211bf88114fc9a129b8d4a7f5937a937c` |
| `joinads_run.jsonl` | 21 | `f1d90430b5c16d9ad04dbf1a15d1def1fe27eb9c56d5b1152a03178524a826db` |

Intervalos: v21 `campaign_day` 14–16/10 (coletas 15/10 11:41 → 16/10 22:08 BRT); JoinAds 08–16/10 (coletas
15/10 13:42 → 16/10 22:15 BRT).

**Artefatos.** `experiments/data-intelligence-lab/artifacts/real-20261017/`, diretório `drwx------`, arquivos
`-rw-------`. `git check-ignore -v` antes e depois: `experiments/data-intelligence-lab/.gitignore:6:artifacts/`.
`git status --porcelain` vazio antes da exportação (após o commit dos scripts) e depois da remoção. Nenhum
arquivo do diretório foi lido por LLM: os scripts imprimem só agregados. **Removido ao fim da rodada** (ver §5).

**Replay** (`rodar_replay_real.py`): 36 cortes horários (15/10 12:00 → 16/10 23:00 BRT), 6 políticas, três
variantes sobre o mesmo snapshot — E (estrito, contrato como está), H (moeda atestada BRL/USD e câmbio 27/5 como
**parâmetro de simulação**, não cotação) e H sem as linhas dos runs presos. 216 decisões por variante, cadeia de
hash do ledger íntegra, 9–23 ms por corte. Decisões: E `a8590ca8…`, H `796b2f54…`, H sem presos `796b2f54…`.
Resumo agregado completo: `item1_resumo_agregado.json`.

## 2. Item 9 — metadados (L6, L7, L8, L13)

`ler_metadados_item9.py`. GTM: só `GET versions/35`, `versions/36`, `versions:live` (token OAuth renovado em
memória; nenhum `create_version`/`publish`). n8n: só `GET /workflows` e `GET /executions?includeData=false`
(credenciais e parâmetros descartados em memória). Host: `ls -l`, `sha256sum` da pasta do `volc-ingest` e
`docker inspect` de estado (sem `.env`, sem restart). Saída sanitizada: `item9_metadados.json`.

## 3. Item 2 — delta de roadmap/curadoria

1. `handoffs/reconciliar_delta_20261017.py` gerou `CURADORIA-DELTA-20261017-RECONCILIADO.json` (39 trocas
   explícitas, cada uma casando uma única vez; 4 guardas recalculadas sobre a base de `db65a78a`; P08-T12 removida;
   P14-T11 todo → partial). Commit `f0985946`.
2. Os 5 campos da frente de medição (P06-T07, P08-T01, P08-T07, `cap_behavior`, `concept:tracking_control_plane`)
   importados idênticos de `origin/fix/measurement-control-plane-20261016 @ db65a78a`, em commit próprio
   (`de1a3073`); a diferença entre os dois arquivos e a base desta branch era só esses campos.
3. `aplicar_curadoria_delta.py` aplicou o delta reconciliado com a guarda de sha: **passou sem force**. 212
   tarefas, 44 tocadas, 16 novas, 159 conceitos, 445 arestas. Commit `8c50097d`. Nada virou `done`; mudanças de
   estado em tarefas existentes: P06-T08 partial → risk, P14-T07 todo → partial. Nos 5 campos da frente de medição
   o texto anterior é prefixo preservado do novo.
4. Grafo reconstruído pelo pipeline oficial (`atualizar_grafo_volc_os.py`, graphify 0.9.48) e `--check`: ver §4.
   **Corrente só em relação a esta branch**; não vale para o grafo global nem para o `main`.

## 4. Grafo

Pipeline oficial `python3 scripts/atualizar_grafo_volc_os.py` com `GRAPHIFY_PYTHON` apontando para o
`.venv-graphify` da worktree de medição (graphify 0.9.48). A primeira tentativa, com o venv do checkout oficial,
travou lendo um `.pyc` despejado pelo iCloud (66 arquivos `dataless` nesse venv) e foi encerrada por esta sessão; o
venv usado tem 0 arquivos `dataless`. O gerador validou a curadoria: 507 nós e 785 arestas no snapshot operacional,
266 curados; o grafo híbrido tem 50.357 nós e 120.497 arestas. Rebuild final com a árvore limpa, commits `45a2eb41` e
`add7b22d`. `--check` → `current: true`, "insumos idênticos", `input_sha256 62491b79…`, 2.854 arquivos.
**Corrente só em relação a esta branch.** Também regenerados pelo mesmo pipeline:
`docs/architecture/REPOSITORY-INVENTORY.md` e `repository-inventory.json`.

## 5. Prova de zero escrita em produção e zero efeito externo

| Alvo | O que foi feito | Escrita? |
|---|---|---|
| Postgres oficial | 6 sessões psql (meta, meta2, exportação, zstat, re_meta, re_agg), todas RR READ ONLY + ROLLBACK com `default_transaction_read_only=on` | não |
| Host Supabase (SSH) | `ls`, `sha256sum`, `docker inspect` | não; nenhum restart |
| GTM API | GET de versões; renovação de access token OAuth | não; nenhuma versão criada ou publicada |
| n8n API | GET de workflows e execuções | não; nenhum workflow alterado, ativado ou executado |
| Google Ads, JoinAds, WordPress, Vercel | nenhum acesso | — |
| Git | commits locais na branch do lab | nenhum push, merge ou rebase; `main` intocado |

Migration aplicada: nenhuma. Segredo impresso: nenhum (tokens e chaves só em memória dos scripts). Os únicos
arquivos fora do namespace do lab alterados são os que a autorização do item 2 cobre: `ROADMAP-VIVO.json`,
`curadoria-operacional.json` e as saídas geradas pelo pipeline do grafo.

## 6. Limpeza

Diretório de artefatos removido em 2026-10-17 02:24 UTC, depois do replay. Manifesto do que foi apagado:
`chave.hmac`, `v21.jsonl`, `v21_run.jsonl`, `joinads.jsonl`, `joinads_run.jsonl`, `meta.json`,
`resumo_replay.json` e os três `ledger_*/ledger.jsonl`. O resumo agregado versionado é a cópia de
`resumo_replay.json`, que só tem agregados. Depois da remoção: `git status --porcelain` vazio e
`artifacts/` só com `bench/`, que já existia.
