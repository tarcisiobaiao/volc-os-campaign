# CL-14 · Harness e supervisores (capacidade de execução agêntica)

**Horizonte**: transversal (multiplicador) · **Resultado**: o harness roda
missões com gates que executam, reviewers que não crasham, supervisor
integrado e documentado — e os executores baratos (Gemini/DeepSeek) operam
dentro de envelopes provados.

## Estado factual (F010-F014, F033, F038, F041)

- Harness v1 na main sólido (contrato MissionSpec, ownership enforced, gates
  argv, nunca merge); v2 (supervisor, ratchet, gemini) só em /private/tmp.
- Defeito 1: gates com caminho de python inexistente mataram 6 tentativas sem
  rodar gate algum. Defeito 2: reviewers Gemini crasham por escopo de LEITURA.
- 91 branches agent/* órfãs; 7 run dirs sem resultado; sem comando de limpeza
  (candidato 6fc7923 de cancel/cleanup pronto, changes_requested).
- adk-smoke provado (5ª tentativa); DeepSeek sniper 4/4 código, 0/4 copy;
  promotion_gate de 10 repetições não cumprido.
- gemini_worker lê GEMINI_API_KEY de .env.local (tensão com a regra do README).

## Missões

| ID | O quê | Onda |
|---|---|---|
| M-W1-05 | Convergência do harness: integrar v2 (supervisor+gemini) na main, corrigir defeito 1 (validação fail-fast de gate argv) e defeito 2 (reviewer com leitura repo-wide), incorporar 6fc7923 revisado, mover API key para env do processo, documentar v2 no README, dar ambiente de teste executável ao harness | 1 |
| M-W2-06 | Colheita das worktrees dos fix-writers (demand-gen/orakul a2): o que existe além de 951fe3f? | 2 |
| M-W3-17 | Supervisor reativado sobre harness corrigido, com filas apontando para o repo principal e task_ids existentes | 3 |
| M-W4-16 | Escada DeepSeek: cumprir promotion_gate (10 repetições) antes de qualquer adapter no Redator (P10-T10→T11) | 4 |

## Regra dura

Supervisores e seus bancos NÃO são tocados por missões (só leitura);
intervenção nos processos vivos é decisão do operador (ver OPEN-DECISIONS
D13). Correções entram por branch nova, nunca editando as cópias de
/private/tmp.
