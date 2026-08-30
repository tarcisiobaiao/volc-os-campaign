# Prompt — M-W2-07 · Lançador do Demand Gen pós-merge (harness implementation)

```text
PINO DE ARMAR: o base_ref da missão está propositalmente inválido
('SUBSTITUIR-PELO-SHA-DA-MAIN-POS-M-W1-03'). Antes de rodar:

1. Confirme M-W1-03 concluída; git rev-parse main → SHA-40.
2. Edite docs/closure/fable-global-v1/missions/m-w2-07-demand-gen-pos-merge.json:
   base_ref = esse SHA. Se a M-W2-06 listou hunks aprovados de demand-gen,
   cole a lista no fim do briefing (seção 'COLHEITA APROVADA: ...').
3. Copie para tools/agent-harness/missions/ e rode com volc-agent-run.
4. Na revisão do candidato, o integrador confere: criação sempre PAUSED,
   zero rede possível, testes_subir atualizado com prova (não com remoção),
   contagem volc_ads ≥ baseline pós-FF.
5. Prova final: pytest volc_ads/campanha/testes_demand_gen.py -q verde na
   main após o merge.

Delta de curadoria proposto: a tarefa Demand Gen da expansão (provável
P04-T09) ganha evidência de canal registrado e provado offline; validate_only
REAL na conta continua atrás de D5 — não promova a done.
```
