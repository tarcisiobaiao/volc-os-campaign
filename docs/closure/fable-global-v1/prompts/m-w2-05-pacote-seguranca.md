# Prompt — M-W2-05 · Lançador do pacote de segurança (harness implementation)

```text
Missão de harness já especificada — não replaneje. Execute:

1. Preflight; copie docs/closure/fable-global-v1/missions/m-w2-05-pacote-seguranca-executavel.json
   para tools/agent-harness/missions/ e rode.
   Nota: o gate 3 (node --test server/tests/) pressupõe que o writer criou
   testes do Express; se o repo não tiver node --test viável, o writer deve
   usar o runner de teste já presente no package.json e o integrador ajusta o
   gate na missão ANTES de rodar (registre o ajuste).
2. Revisão do integrador com lupa dupla:
   - ZERO segredo em qualquer arquivo novo (rode a varredura de segredo no
     diff completo);
   - nenhum script conecta a produção (grep por database.agenciavolc.com.br
     nos scripts novos → só pode aparecer como variável documentada, nunca
     hardcoded com credencial);
   - cada REVOKE tem rollback par; o smoke falharia se a escrita anônima
     estivesse aberta (teste do teste).
3. Após o merge: o RUNBOOK.md de scripts/seguranca/ é a pauta da janela
   D4+D10 — apresente-o ao dono junto com OPEN-DECISIONS.md.

Delta de curadoria proposto: P02-T05 permanece 'risk' (o risco só fecha na
janela real), mas ganha evidência 'pacote executável pronto e provado em
descartável'.
```
