# Protocolo de fechamento de agentes VOLC

## Objetivo

Impedir que Codex, Claude, Grok ou um worker ADK entregue código enquanto o QG,
o Roadmap Vivo e o grafo continuam contando outra história.

## Regra central

Uma entrega material possui dois atos distintos:

1. **entrega técnica isolada:** código, testes e evidências na branch/worktree;
2. **convergência operacional:** integração, aceite, Roadmap, curadoria e rebuild.

Somente o segundo ato pode alterar o percentual do QG ou declarar uma tarefa
concluída.

## Contrato de saída mínimo

Todo agente que tocar produto, backend, schema, workflow, integração ou decisão
arquitetural deve informar:

- tarefas afetadas ou a necessidade de uma tarefa nova;
- capacidades e conceitos afetados no grafo;
- prova reproduzível do que passou;
- lacunas, riscos e dependências que permaneceram;
- arquivos e commit/worktree onde a entrega vive;
- proposta de estado: `todo`, `partial`, `risk`, `done` ou equivalente.

## Escritor único da memória operacional

Roadmap e curadoria são arquivos de alta contenção. Em missões paralelas:

- workers não os editam;
- o resultado da missão preserva o handoff;
- o integrador confere a entrega e o aceite;
- um único curador atualiza as fontes;
- o grafo é reconstruído uma vez, depois da integração.

Isso não é uma exceção ao dever de atualizar. É o mecanismo que evita três
agentes produzirem três versões incompatíveis da verdade.

## Gate de conclusão

Uma tarefa só pode virar `done` quando:

1. a mudança está integrada na linha de desenvolvimento usada pelo produto;
2. os critérios de aceite estão provados;
3. o QG consegue alcançar a tarefa e sua evidência pela fonte viva;
4. a curadoria não contradiz o Roadmap;
5. `python3 scripts/atualizar_grafo_volc_os.py --check` retorna atual.

Se qualquer item faltar, o estado permanece `partial`, `risk` ou `todo`, com a
causa explicitada.
