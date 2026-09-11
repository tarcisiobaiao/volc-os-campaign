# Meta ADK Review v2

Harness local para revisão e implementação focal do módulo Meta Ads. Ele não integra
patches automaticamente e não possui ferramentas para Meta, Supabase, deploy, Git,
shell livre ou ativação de campanhas.

## Topologia real

Cada lane usa o `Workflow`/graph API atual do ADK 2.x:

1. O lead converte achados comprovados em tickets de `tasks.py`, com aceite, arquivos e teste.
2. Pesquisador usa Google Search; recebe só a pergunta pública, nunca o código.
3. Executor recebe fontes atuais sanitizadas e devolve `PatchProposal` estruturado.
4. `FunctionNode` valida hashes/âncoras, aplica via `apply_patch` e executa o teste obrigatório e `git diff --check`.
5. Crítico recebe diff REAL e gates, não apenas a narrativa do executor.
6. A aresta `revise` fecha o ciclo por até duas rodadas; o lead integra somente candidatos verificados.

Tickets independentes rodam simultaneamente, cada um em branch/worktree própria.
As quatro áreas de cobertura continuam definidas em `config.py`, mas não são missões
executáveis genéricas. Inicialmente: `copy_retry` e `flexible_focus`.
O caminho legado de exploração com function calling fica disponível em `run_lane.py`
sem `--task`, mas não é disparado pelo orquestrador: ele consumiu orçamento sem editar.
Tickets atuais não compartilham arquivos de escrita. O lead revisa cada diff
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
  --tasks copy_retry flexible_focus \
  --rounds 2 --max-calls 6 --max-tokens 100000 --timeout 900
```

O orquestrador faz um probe pago; se modelo ou grounding divergirem, nenhuma lane
começa. Em seguida cria uma branch `sprint/meta-adk-v2-*` por ticket e dispara processos
paralelos. O teto de tokens é observado entre respostas: uma resposta em voo pode
ultrapassá-lo. Não existe retry pago automático. `--prepare-only` não faz chamada paga.

Cada root em `/private/tmp/volc-meta-adk-v2-<timestamp>/` guarda `MANIFEST.json`,
`PROBE.json`, logs por lane, `events.jsonl`, `REPORT.json` e `candidate.diff`.
O custo monetário permanece `null` quando o provider não devolve valor faturado;
tokens de entrada, saída, pensamento e total ficam registrados.

O executor estruturado não fica escolhendo ferramentas: deve entregar código e
testes na resposta. O host recusa relatório sem patch e não aceita âncoras inexistentes.
No caminho legado, chamadas iguais só são recusadas na MESMA revisão; depois de editar,
reler e repetir o teste são permitidos. Testes novos entram no diff sem staging.
O harness não força patch: se a hipótese grounded contradiz o código, o resultado
correto é `partial_no_progress`/`blocked`, nunca uma mudança fabricada.

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

- https://adk.dev/workflows/graph-routes/
- https://github.com/google/adk-python/blob/main/docs/guides/workflow/function_node/index.md
- https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash
- https://ai.google.dev/gemini-api/docs/google-search
