# Meta ADK Review v2

Harness local para revisão e implementação focal do módulo Meta Ads. Ele não integra
patches automaticamente e não possui ferramentas para Meta, Supabase, deploy, Git,
shell livre ou ativação de campanhas.

## Topologia real

Cada lane usa o `Workflow`/graph API atual do ADK 2.x:

1. `START` faz fan-out para pesquisador de API e cartógrafo do código.
2. `JoinNode` espera as duas branches paralelas.
3. executor → crítico → `FunctionNode` decide `revise` ou `done`.
4. a aresta `revise` fecha o ciclo por até duas rodadas controladas pelo host.

Quatro lanes rodam simultaneamente, cada uma em branch/worktree própria:
`wizard_ux`, `creative_system`, `publishing_contract` e `measurement_ops`.
Isso evita agentes concorrentes editando os mesmos arquivos. O lead revisa cada diff
e integra manualmente; nenhuma lane pode editar roadmap, grafo ou harness.

O modelo é fixo em `gemini-3.8-flash`; cada resposta confere `model_version` e falha
se houver substituição. Thinking é `HIGH`, sem parâmetros de sampling depreciados.
O probe exige grounding real (queries e chunks), não apenas ferramenta configurada.

## Runtime isolado

```sh
python3 -m venv /private/tmp/volc-meta-adk-v2-runtime
/private/tmp/volc-meta-adk-v2-runtime/bin/python -m pip install \
  -r tools/meta-adk-review/requirements.txt
```

## Prova local do harness

```sh
/private/tmp/volc-meta-adk-v2-runtime/bin/python -m unittest discover \
  -s tools/meta-adk-review -p 'test_harness.py' -v
```

## Run completa paralela

O harness precisa estar commitado porque as worktrees partem do `HEAD`:

```sh
/private/tmp/volc-meta-adk-v2-runtime/bin/python tools/meta-adk-review/orchestrate.py \
  --source /private/tmp/volc-os-operacao-80-20 \
  --runtime /private/tmp/volc-meta-adk-v2-runtime/bin/python \
  --rounds 2 --max-calls 26 --max-tokens 180000 --timeout 1800
```

O orquestrador faz um probe pago; se modelo ou grounding divergirem, nenhuma lane
começa. Em seguida cria quatro branches `sprint/meta-adk-v2-*` e dispara processos
paralelos. O teto de tokens é observado entre respostas: uma resposta em voo pode
ultrapassá-lo. Não existe retry pago automático.

Cada root em `/private/tmp/volc-meta-adk-v2-<timestamp>/` guarda `MANIFEST.json`,
`PROBE.json`, logs por lane, `events.jsonl`, `REPORT.json` e `candidate.diff`.
O custo monetário permanece `null` quando o provider não devolve valor faturado;
tokens de entrada, saída, pensamento e total ficam registrados.

Consultar sem consumir API:

```sh
/private/tmp/volc-meta-adk-v2-runtime/bin/python tools/meta-adk-review/status.py \
  /private/tmp/volc-meta-adk-v2-<timestamp>
```

## Critério de integração

`candidate_requires_lead_review` exige patch, grounding, teste focal executado após
a última edição e todos os gates verdes. Ainda não prova browser autenticado, banco
vivo, Meta real, melhoria de CTR ou produção. O lead reproduz o teste, inspeciona o
diff e somente então integra um lane por vez.

Referências:

- https://google.github.io/adk-docs/agents/workflow-agents/parallel-agents/
- https://google.github.io/adk-docs/agents/workflow-agents/loop-agents/
- https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash
- https://ai.google.dev/gemini-api/docs/google-search
