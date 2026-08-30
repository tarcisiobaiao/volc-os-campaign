# Prompt — M-W1-06 · Lançador da verificação "14 achados" (harness read_only)

```text
Missão de harness já especificada — não replaneje. Execute:

1. Preflight: .venv-adk/bin/volc-agent-preflight --repo /Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign --json
   (exige CLIs claude/codex autenticadas; se o preflight falhar, reporte e pare).
2. Copie docs/closure/fable-global-v1/missions/m-w1-06-verificacao-estudio-14-achados.json
   para tools/agent-harness/missions/ (mantenha o nome).
3. Rode: .venv-adk/bin/volc-agent-run --repo /Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign \
   --mission tools/agent-harness/missions/m-w1-06-verificacao-estudio-14-achados.json
4. Leia o mission-result.json do run dir e extraia: veredito por achado
   (presente_na_main | ausente_na_main | indeterminado) e a recomendação
   final (poda segura vs cherry-pick necessário).
5. Anexe o veredito ao INTEGRATION-LEDGER.md (seção 2, linha do Estúdio) —
   é a única edição permitida, e só na linha correspondente.

Se qualquer achado sair 'ausente_na_main': a poda das 5 refs do Estúdio fica
PROIBIDA até uma missão corretiva portar os hunks listados.
```
