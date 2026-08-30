# CL-13 · QG, workbook e grafo (memória estrutural)

**Horizonte**: transversal · **Resultado**: a fonte compartilhada reflete a
realidade em até um ciclo de integração; o gate de curadoria fecha sozinho.

## Estado factual (F015, F027, F028, F003)

- QG V3 done (53 testes) lendo arquivos do monorepo; fonte limpa de duplicatas.
- Contradições done↔decision (P12-T07, P03-T08) e defasagem grafo↔roadmap ~2h.
- Supervisores citam task_ids que não existem na main (expansão presa na
  branch de integração).
- 149/152 tarefas sem updated_at → staleness imensurável.
- Nós do legado n8n dependem de meta.json ignorados pelo Git — worktree limpa
  nasce sem eles (dependência estrutural declarada na Convergência).

## Missões

| ID | O quê | Onda |
|---|---|---|
| M-W1-09 | (compartilhada) curadoria + rebuild + reconciliação pós-integração | 1 |
| M-W3-15 | Curador único automatizado (P10-T15): consumir curation_handoff do harness após merge e publicar recibo no QG | 3 |
| M-W3-16 | Versionar manifesto sanitizado mínimo dos meta.json n8n (worktree limpa rebuilda) | 3 |
| M-W4-15 | updated_at por tarefa no schema do roadmap + QG exibe staleness | 4 |

## Regra dura

Workers paralelos nunca editam Roadmap/curadoria (entregam delta); rebuild
sempre pelo pipeline oficial; `graphify update .` continua proibido.
