# Prompt — M-W2-01 · Lançador do diagnóstico Search (harness implementation)

```text
Missão de harness já especificada — não replaneje. Execute:

1. Preflight: .venv-adk/bin/volc-agent-preflight --repo /Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign --json
2. Copie docs/closure/fable-global-v1/missions/m-w2-01-diagnostico-search-endpoint.json
   para tools/agent-harness/missions/ e rode com volc-agent-run.
   (base_ref e858651 é válido; se a onda 1 já mesclou, atualize para o SHA
   da main atual — implementation exige ancestral da main, e ancestral segue
   sendo; manter e858651 só faz a worktree nascer sem os merges novos.)
3. O run é implementation: exit 0 = candidate ready_for_human. Leia
   mission-result.json: candidate_status, writer_commit, changed_paths,
   curation_handoff, e os gate-N.json (contagens!).
4. Se ready_for_human: o integrador único revisa o diff do commit candidato
   (branch agent/<run>/codex-diagnostico-writer) e mescla na main com os
   gates de praxe (pytest backend, tsc 76, build).
5. Prova final OBRIGATÓRIA em localhost: ./start-dev.sh, abrir
   /trafego/campanhas/<id da Maquininha ou FGTS> e fotografar o diagnóstico
   REAL renderizado (fonte, janela, lido_em visíveis). Sem essa prova, a
   tarefa P05-T07 NÃO é promovida.
6. Se changes_requested/blocked: leia os confirmed_findings dos reviewers e
   relance como missão corretiva (sufixo -a2) com os findings no briefing.

Delta de curadoria proposto (aplicação é do integrador): P05-T07
partial→done SOMENTE com o item 5 provado; caso contrário permanece partial
com evidência nova.
```
