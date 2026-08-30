# Prompt — M-W1-09 · Curadoria + rebuild do grafo + poda (Opus, integrador único, ÚLTIMA da onda)

> ⛓ Pré-condições: M-W1-02/03/04/05 mescladas; vereditos de M-W1-06 e M-W1-08
> registrados no INTEGRATION-LEDGER.md.

```text
Você fecha a onda 1 do plano docs/closure/fable-global-v1/. Missão em quatro
atos, na ordem, com prova a cada ato.

ATO 1 — Fonte compartilhada:
1. Commite o delta pendente do ROADMAP-VIVO.json (blocos acceptance de
   P04-T07/P10-T04) junto com as promoções de status PROVADAS pelas missões
   da onda (use ROADMAP-CURATION-PROPOSAL.json como base, mas só aplique
   linhas cujo gate foi registrado nos handoffs; o resto fica proposto).
2. Atualize docs/volc-os-graph/curadoria-operacional.json SOMENTE onde o
   estado de negócio mudou de fato: os nós concept:organic_publication_control_plane
   e concept:secret-reference-boundary saem de 'decision' (os ADRs de 28/08
   fecharam a decisão — FACT-MATRIX F028); registre evidência.

ATO 2 — Rebuild do grafo (pipeline oficial, NUNCA graphify update .):
3. python3 scripts/atualizar_grafo_volc_os.py
4. python3 scripts/atualizar_grafo_volc_os.py --check → exige current:true.

ATO 3 — Poda (só com os vereditos das M-W1-06/08 em mãos):
5. Delete as refs listadas na seção 3 do INTEGRATION-LEDGER.md (contidas na
   main) e as supersedidas pelo FF (lista do handoff do M-W1-03), usando
   git branch -d (o -d falha se não estiver contida — é a prova). Para as da
   seção 2, git branch -D SÓ se o veredito da M-W1-06 foi 'poda segura'.
6. Worktrees das refs podadas: git worktree remove <path> (nunca rm -rf).
   Em caso de erro 'locked/dirty', pule e liste — não force.
7. NÃO pode: as worktrees vivas dos supervisores, a linha do harness até o
   merge do M-W1-05, e qualquer ref com veredito pendente.

ATO 4 — Fechamento:
8. Atualize o INTEGRATION-LEDGER.md (estado final por linha) e commite tudo
   como lote de curadoria único.
9. Peça o push final ao M-W1-01.

Proibições: nenhuma edição em volc-os-graph.json ou graphify-out/ à mão;
nenhuma poda sem veredito; nenhum push direto.

Handoff: task IDs promovidos (com prova citada), nós de curadoria alterados,
resultado do --check, refs podadas (contagem), refs preservadas com motivo,
SHA final.
```
