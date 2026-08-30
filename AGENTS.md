## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For questions about architecture, roadmap, impact, data flow or existing VOLC capabilities, first query `graphify-out/graph.json`. Use `.venv-graphify/bin/graphify query "<question>"`, `path "<A>" "<B>"`, `explain "<concept>"` or `affected "<concept>"`. If the project venv is unavailable, read `graphify-out/README.md` and use the JSON directly before falling back to raw source browsing.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- For the high-level operational truth, consult the human curation at `docs/volc-os-graph/curadoria-operacional.json`; it records states, priorities and evidence that AST extraction cannot infer safely, and it is the only file in this chain edited by hand. `docs/volc-os-graph/volc-os-graph.json` is the generated snapshot of that curation: read it, never edit it — edits there are lost on the next build.
- Never run `graphify update .` directly in this repository: it would replace the hybrid graph with a code-only graph. After material code, schema or roadmap changes, run `scripts/atualizar_grafo_volc_os.py` (use `--reuse-technical` only when the code layer did not change).
- Before treating the graph as current, check `graphify-out/UPDATE_STATUS.json`. If its commit differs from `git rev-parse HEAD` or the status says inputs are stale, disclose that limitation.
- Save useful, corrected or dead-end graph answers with `graphify save-result`, so `graphify reflect` can turn repeated feedback into durable lessons without silently rewriting factual nodes.

### VOLC source-of-truth order

1. `docs/volc-os-graph/curadoria-operacional.json` — human operational curation, **hand-editable**; the generator only reads and validates it (schema, clusters, states, duplicate ids, broken references) and never writes to it: a hash guard (`_guarda_fonte_humana`) fails the build if the file is touched.
2. `docs/volc-os-graph/volc-os-graph.json` — **generated** operational snapshot of that curation, combined with the live snapshots; read-only, never hand-edited.
3. `.graphify-cache/code/graphify-out/graph.json` — regenerable technical extraction; never a business authority.
4. `graphify-out/graph.json` — canonical hybrid graph for traversal, paths, impact and agent queries.
5. `graphify-out/obsidian-volc-os/`, `graphify-out/graph.graphml`, `graphify-out/cypher.txt` and `entregaveis/Explorador_Neural_VOLC_OS.html` — generated views/exports, never edited as sources.

### Mandatory completion protocol

Material work is not complete when code alone is finished. Before reporting a
feature, schema, workflow, integration, architectural decision or roadmap item
as complete, reconcile the operational memory:

1. Identify the affected task in `volc-os-workbook/ROADMAP-VIVO.json`. If no
   task represents the work, create or refine one before claiming completion.
2. Record factual proof, remaining gaps and the honest state (`todo`,
   `partial`, `risk`, `done`, etc.). Never promote a task only because code was
   written; its acceptance criteria must be proven.
3. Update `docs/volc-os-graph/curadoria-operacional.json` only when business
   state, evidence or relationships materially changed. Never place secrets,
   raw identifiers or credentials there.
4. Rebuild through `scripts/atualizar_grafo_volc_os.py` after material code,
   schema or roadmap changes, then run its `--check` mode.
5. Report the Roadmap task IDs, graph nodes and freshness result in the final
   handoff.

Parallel workers must not all edit these shared authorities. They emit a
curation handoff; the single integrating/curating agent performs steps 1–5 once
after integration. A branch or worktree that has not been integrated cannot
mark the shared roadmap as done.

## Supabase — autoridade operacional única

- O único Supabase operacional deste projeto é o self-hosted em `https://database.agenciavolc.com.br`.
- Referências `*.supabase.co` são permitidas apenas em fixtures herméticas, documentação arquivada ou inventário de consumidores legados a migrar/aposentar. Nunca as trate como fallback, réplica ou destino válido para funcionalidade nova.
- Não migre um consumidor legado por substituição cega de URL. Confira antes schema, funções, identidade, RLS, idempotência e efeitos; depois registre owner, heartbeat e recibo.
- Antes de iniciar o ambiente ou alterar configuração Supabase, execute `python3 scripts/verificar_autoridade_supabase.py`.
- Decisão completa: `docs/architecture/ADR-SUPABASE-AUTORIDADE-OPERACIONAL.md`.
