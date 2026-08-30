# Prompt — M-W2-06 · Lançador da colheita dos fix-writers (harness read_only)

```text
PRÉ-CONDIÇÃO DURA: M-W1-03 concluída (951fe3f na main). Antes disso a
comparação mede a coisa errada.

1. Preflight; copie docs/closure/fable-global-v1/missions/m-w2-06-colheita-fix-writers.json
   para tools/agent-harness/missions/ e rode.
2. Do mission-result.json, monte a tabela: frente → veredito
   (ja_coberto | valor_novo | quebrado) → hunks a portar → missão destino.
3. Encaminhamento por veredito:
   - valor_novo em demand-gen → anexar hunks ao contexto da M-W2-07;
   - valor_novo em orakul → missão corretiva própria (onda 3, CL-08);
   - valor_novo em creative-s0/pytest → cotejar com M-W2-03 (pode já estar
     coberto) e registrar;
   - quebrado/ja_coberto → registrar no INTEGRATION-LEDGER e NÃO portar.
4. Lembrete de factualidade: os testes dos writers são AUTO-RELATADOS — a
   tabela deve dizer isso explicitamente; nada é 'verde' até rodar em gate
   próprio.
5. Só depois desta colheita (e com D13 respondida) as worktrees mortas do
   supervisor podem entrar na lista de limpeza — a limpeza em si é do
   integrador, com git worktree remove, nunca rm -rf.
```
