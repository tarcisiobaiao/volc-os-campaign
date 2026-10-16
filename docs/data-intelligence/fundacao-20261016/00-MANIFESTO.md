# 00-MANIFESTO — Fundação Data Intelligence (missão multiagente, 2026-10-16)

Missão: construir e validar, em código, testes, simulação, replay e shadow, a fundação de
Data Intelligence do VOLC (observação append-only, contrato de tempo e ausência, atribuição
honesta, replay `as_of`, shadow engine, simulador, Model Lab, observabilidade, cadência e
capacidade). Pedido original: mensagem do Tarcisio de 2026-10-16 11:32 UTC na thread
"Fundação Data Intelligence: missão multiagente".

## 1. Baseline (registrado antes de qualquer escrita)

| Item | Valor |
|---|---|
| Worktree do integrador (thread I) | `/Users/mac/Desktop/VOLC-OS-CAMPAIGN/worktrees/data-intelligence-overnight-20261015` |
| Branch da missão | `lab/data-foundation-20261016` (criada de `b6e85974`) |
| Base herdada | `b6e85974` = `main` `104bb0d0` + 16 commits da 1ª execução do Lab |
| `main` oficial | `104bb0d0` (2026-10-15 22:02 -0300), sem commits novos desde a 1ª execução |
| Checkout "oficial" `volc-os-campaign/` | branch `wip/original-worktree-pre-qg-real-20261007` em `043c77f5`, **302 arquivos sujos**, **sem merge-base com `main`** (históricos desconexos). Lido só em modo leitura |
| Árvore inicial | limpa |
| Disco | 14–16 GiB livres de 926 GiB (apertado) |
| Máquina | 10 CPUs, 16 GiB RAM, macOS (Darwin 24.6) |
| Python do lab | `experiments/data-intelligence-lab/.venv` (CPython 3.13.0, `uv.lock` com `exclude-newer=2026-10-01`) |
| PostgreSQL descartável | `postgres`/`initdb`/`pg_ctl` 16.11 (Homebrew), clusters temporários em diretório da missão |
| DuckDB/Polars | já no lock do lab (provisórios) |
| Suíte herdada | 172 testes verdes em 29,6 s (`tests/data-intelligence`) |
| Grafo | `--check` → `current: false` ("código, SQL ou fonte operacional mudou"); autoridade `docs/volc-os-graph/BUILD-STATUS.json` construída em `6124c550`. Rebuild só pela thread I no fechamento |
| Autoridade Supabase | `scripts/verificar_autoridade_supabase.py` → `https://database.agenciavolc.com.br` ✓ |
| `graphify-out/wiki/index.md` | não existe |

## 2. Herança da 1ª execução (reaproveitada, não refeita)

Fonte: `docs/data-intelligence/FINAL-REPORT.md`, `PROOF-RECEIPT.json`, `CURATION-HANDOFF.json`.

| Herdado | Estado | Uso nesta missão |
|---|---|---|
| `volc_dil.contracts` (observação econômica, snapshot `as_of`, `value_kind`, fingerprint) | testado hermeticamente + sintético | base do contrato de observação ampliado (thread A) |
| `volc_dil.replay` (replay v0, 4 baselines, contraprovas futuro/null→0/moeda/identidade) | testado em sintético | base do replay/shadow (thread D) |
| `volc_dil.statlab` (maturação, EB, CS, FDR) | testado em sintético | base do Model Lab (thread F) |
| `volc_dil.swarm`, `volc_dil.surrogate` | resultado negativo preservado | não reabrir sem dado novo |
| `volc_dil.bench` | DuckDB/Polars **não** ajudam o replay atual | reusar só em capacidade (thread B) |
| Achado | `volc_ads/economia/` não existe em `main`; núcleo econômico, ledger v21, JoinAds v2 e coleta canônica Google Ads vivem em `wip/*` | inventário (thread A-inv) |
| Bloqueio | nenhuma fonte append-only em `main` | é o centro desta missão |

## 3. Achado de bootstrap que muda o inventário

A "fonte de verdade" está fragmentada em três lugares que não compartilham histórico:

- `main` (`104bb0d0`): não contém os IDs documentados dos workflows Google Ads
  (`Ps9yLfQkHeaAbyZZ`, `7yxs1aOlzWkkkSf9`, `TFlmThr4930oPneE`) nem JoinAds
  (`cpb6tNxt211UkAn2`, `jDX397ViVcRQft4A`); contém `<container-gtm>` em 3 arquivos.
- `043c77f5` (checkout oficial, wip): contém os três workflows Google Ads (18 arquivos) e o GTM (16).
- Branches `wip/historico-*-20261015` e os 302 arquivos sujos do checkout oficial: contratos
  de atribuição econômica e, provavelmente, os IDs JoinAds (a confirmar pela thread A-inv).

Consequência: toda afirmação de inventário cita **ref + caminho + linha**. Nada é dado como
existente só porque está documentado.

## 4. Threads, ownership e escrita

Cada escritor tem branch e worktree **esparsa** própria (só o namespace do lab, ~3 MB, porque um
worktree completo custa ~2 GB e o disco tem ~14 GiB). Leitura do restante do repositório pelo
caminho absoluto do worktree do integrador. Só a thread I integra, edita roadmap/curadoria e
reconstrói o grafo.

| Thread | Branch / worktree | Escreve somente em | Onda |
|---|---|---|---|
| A-inv Inventário e verdades da seção 3 | `lab/dil-fundacao-20261016-inv` / `worktrees/dil-fundacao-20261016-inv` | `docs/data-intelligence/fundacao-20261016/01-INVENTARIO-ATUAL.md`, `.../receipts/inventario/` | 1 |
| A Contrato de dados e schema | `-a` | `src/volc_dil/fundacao/observacao/`, `experiments/data-intelligence-lab/migrations_candidatas/`, `tests/data-intelligence/fundacao/test_observacao_*`, `test_schema_pg_*`, doc `02-` | 1 |
| B Coleta, cadência e capacidade | `-b` | `src/volc_dil/fundacao/capacidade/`, `benchmarks/` da missão, `tests/.../test_capacidade_*`, docs `04-`, `05-` | 1 |
| C Identidade e atribuição | `-c` | `src/volc_dil/fundacao/identidade/`, `tests/.../test_identidade_*`, doc `03-` | 1 |
| E Simulator Lab | `-e` | `src/volc_dil/fundacao/simulador/`, `tests/.../test_simulador_*`, doc `07-` | 1 |
| D Replay e shadow | `-d` (onda 2) | `src/volc_dil/fundacao/shadow/`, `tests/.../test_shadow_*`, doc `06-` | 2 (depende de A, E) |
| F Model Lab e ouros | `-f` (onda 2) | `src/volc_dil/fundacao/modelos/`, `tests/.../test_modelos_*`, docs `08-`, `10-` | 2 (depende de E) |
| G Observabilidade e DQ | `-g` (onda 2) | `src/volc_dil/fundacao/qualidade/`, views candidatas em `migrations_candidatas/views_qualidade/`, `tests/.../test_qualidade_*`, doc `09-` | 2 (depende de A) |
| R Revisor independente | somente leitura | `.../handoffs/REVISAO-ADVERSARIAL-*.md` (entregue ao integrador) | após cada onda |
| I Integrador e curador | `lab/data-foundation-20261016` (este worktree) | manifesto, `11-`, `12-`, `FINAL-REPORT.md`, roadmap, curadoria, grafo (pelo script oficial) | contínua |

Regras: nenhum worker edita `pyproject.toml`/`uv.lock` (pedido de dependência vai ao integrador);
nenhum worker toca `ROADMAP-VIVO.json`, `curadoria-operacional.json`, `graphify-out/`, `main`;
cada worker devolve arquivos, provas, resultados, falhas, riscos e um handoff de curadoria.

## 5. Concorrência

Máximo de quatro trabalhos pesados simultâneos no Mac. Onda 1: A, B, E pesados; A-inv e C
majoritariamente leitura. Suítes pesadas (PostgreSQL descartável, simulações longas) rodam uma
de cada vez quando competem por CPU. `OMP_NUM_THREADS=2` em toda suíte.

## 6. Proibições (seção 9 da missão, mantidas mesmo com liberdade de execução)

Nada de push, merge no `main`, deploy, migration aplicada no Supabase operacional, escrita em
produção, ativação/publicação de n8n, publicação de GTM, alteração de Google Ads (verba, lance,
campanha, keyword, negativa), alteração de JoinAds ou WordPress, exposição de segredo.
Leituras de fontes externas: somente read-only, e somente quando houver caminho autorizado sem
imprimir credencial; caso contrário, a lacuna é registrada.

## 7. Taxonomia de estado usada em todos os documentos

`construído` → `testado hermeticamente` → `testado com sintético` → `testado em replay` →
`rodando em shadow` → `calibrado com dado real` → `operacional`; e `ainda não demonstrado`.
Fixture ou simulação nunca vira "validação real".

## 8. Mapa de entregáveis

`docs/data-intelligence/fundacao-20261016/`: `00`–`12`, `FINAL-REPORT.md`, `receipts/`,
`benchmarks/`, `handoffs/`. Código em `experiments/data-intelligence-lab/src/volc_dil/fundacao/`,
migrations candidatas e rollbacks em `experiments/data-intelligence-lab/migrations_candidatas/`,
testes em `tests/data-intelligence/fundacao/`.

## 9. Log de integração

| Quando (UTC) | Evento |
|---|---|
| 2026-10-16 ~12:00 | bootstrap, branch da missão, worktrees esparsos `-a -b -c -e -inv` criados de `b6e85974` |
