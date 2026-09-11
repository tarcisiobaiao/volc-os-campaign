# ADR — harness ADK v2 para refino Meta

Estado: aceito para execução local controlada em 11/09/2026; integração de patches
continua dependente do lead.

## Contexto

O piloto de 10/09 provou o modelo e uma correção, mas duas rodadas amplas consumiram
mais de um milhão de tokens sem patch. Ele também usava os workflow agents legados,
que o ADK 2.8 marca como depreciados, e fazia pesquisa genérica de formato flexível
em todas as rodadas. O harness foi removido e reconstruído; os recibos históricos
foram preservados em `docs/closure/meta-adk-loop-20260910/`.

## Decisão

Usar Google ADK 2.8.0 e o SDK unificado google-genai 2.22.0 em runtime isolado.
O modelo é exclusivamente `gemini-3.8-flash`, thinking `HIGH`, sem sampling legado,
fallback ou retry pago do provider. Um probe anterior às lanes exige nome efetivo
idêntico e grounding com queries e chunks reais.

Cada lane usa o graph `Workflow` do ADK 2.x:

1. `START` dispara em paralelo pesquisador oficial e cartógrafo do código;
2. `JoinNode` forma a barreira;
3. executor e crítico rodam em sequência;
4. `FunctionNode` encerra ou roteia de volta ao executor dentro do teto de rodadas.

As quatro lanes — jornada, criativos, publicação e mensuração — rodam em processos,
branches e worktrees separados. Essa segunda camada de paralelismo impede escrita
concorrente no mesmo arquivo. O lead compara e integra cada candidato manualmente.

O host lê somente fonte rastreada e exclui segredos, dados pessoais, artefatos,
grafo e configurações. Escrita é limitada por lane, usa SHA + substituição exata via
`apply_patch`, e arquivo novo só pode ser teste. Gates recebem um path elegível, nunca
um comando, e executam em sandbox sem rede. Não existem ferramentas de shell livre,
Git, Meta, Supabase, deploy ou ativação.

## Condições de candidato

Parecer `candidate_requires_lead_review` exige simultaneamente patch não vazio,
grounding verificado, teste focal verde executado depois da última edição e todos os
gates verdes. Isso não prova browser autenticado, banco vivo, aceite remoto, qualidade
visual, melhoria de CTR ou produção.

O plano final continua exigindo aprovação humana e qualquer efeito Meta continua fora
do harness. Todos os objetos externos permanecem exclusivamente PAUSED.

## Limites e operação

Há limites por agente, lane, chamadas, tokens observados, edições, rodadas e tempo.
Uma resposta em voo pode ultrapassar o teto observado; a API não devolve faturamento
em dólares, portanto o recibo registra tokens e custo monetário `null`. Eventos são
gravados antes do despacho e cada lane produz diff e relatório próprios.

O runtime fica em `/private/tmp` e não entra nas dependências do backend. Worktrees e
relatórios também ficam fora do checkout operacional. Interrupção preserva o que já
foi escrito; retomada automática e merge automático não existem nesta versão.

## Referências

- [Workflow agents e depreciação](https://google.github.io/adk-docs/agents/workflow-agents/)
- [Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
- [Grounding com Google Search](https://ai.google.dev/gemini-api/docs/google-search)
- [Harness executável](../../tools/meta-adk-review/README.md)
- [Histórico do piloto](../closure/meta-adk-loop-20260910/HANDOFF.md)
