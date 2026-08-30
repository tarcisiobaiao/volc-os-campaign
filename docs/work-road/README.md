# VOLC Work Road

Fonte estruturada da futura Sala de Comando do VOLC O.S.

## Papel de cada camada

| Camada | Responsabilidade |
|---|---|
| Work Road | Operar, priorizar, atribuir, acompanhar e validar |
| Grafo | Explicar relações, dependências e impacto |
| Second Brain | Preservar estratégia e conhecimento histórico |
| Workbook | Explicar o sistema e registrar o plano mestre |
| ClickUp | Receber, opcionalmente, tarefas aprovadas que precisem sair do VOLC |

## Estado da v0

A rota `/settings/qd-agentico` é um protótipo frontend. O snapshot vive em
`src/features/work-road/seed.ts` e os checks são persistidos apenas no
`localStorage` do navegador.

Essa limitação é exibida na própria tela. A v0 não escreve no Supabase, no
grafo, no workbook ou no ClickUp.

## Invariantes

1. Produto, trabalho, ambiente, veredito e risco são dimensões diferentes.
2. Um agente pode entregar uma iniciativa, mas não encerra sozinho o próprio trabalho.
3. Toda conclusão exige evidência consultável.
4. Ownership inclui escopo de arquivos, branch e próximo handoff.
5. O grafo recebe uma projeção do trabalho; ele não é banco transacional de tarefas.
6. ClickUp não é uma segunda fonte de verdade.

## Evolução prevista

Depois de validar o vocabulário da v0:

1. mover definições estáveis para arquivos por iniciativa;
2. criar eventos e evidências append-only;
3. adicionar claims com prazo e ownership de paths;
4. projetar estado operacional por API;
5. gerar grafo e workbook a partir da mesma fonte;
6. oferecer publicação unidirecional opcional para ClickUp.

O schema inicial está em `schema/work-road.schema.json`.

