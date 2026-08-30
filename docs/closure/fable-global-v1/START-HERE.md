# START HERE — operador humano do fechamento VOLC O.S.

*2026-08-29 · base histórica `e858651` · pacote completo em `docs/closure/fable-global-v1/`*

> **Atualização operacional:** leia primeiro `ADDENDUM-V1.2.md`. A fila já
> avançou numa branch única de integração; o fast-forward, a preservação da
> colheita e três revisões independentes descritas abaixo não estão mais
> pendentes.

## O que está acontecendo, em 30 segundos

O VOLC O.S. tem muito mais coisa pronta do que integrada. O trabalho de 29/08
(ORAKUL Predictive, Demand Gen, fronteira criativa, correções do harness,
dois candidatos Gemini com gates verdes) está preso em branches e worktrees.
Dois defeitos do harness que travavam tudo **já foram corrigidos em branch** —
o principal chega na main com um único fast-forward. Existe um plano com fila
serial pronta; nada foi executado e nada externo foi tocado.

## Os 3 números que importam

1. **411 commits sem backup remoto.** Se este disco morrer, fev–ago/2026 morre
   junto. Decisão D9: me dê a URL de um repositório privado SEU (nunca o
   webgo) e autorize o push. Custa 10 minutos.
2. **1 fast-forward** (`git merge --ff-only bdf9e1c`) entrega Predictive +
   Demand Gen + fronteira criativa + o fix do harness, sem conflito.
3. **3 decisões** (D1: aplicar v10 · D4+D10: janela de segurança/webhook)
   separam o sistema de "Search lançável". Todo o resto anda sem você.

## O que fazer agora (você, humano)

1. **Responda D9** (backup) — desbloqueia o RQ-11.
2. **Clique os vínculos** (H1): UI autenticada → confirmar Maquininha→funil 74
   e FGTS→funil 65. Cinco minutos, fecha uma tarefa inteira do roadmap.
3. **Agende a sessão de decisões** com `OPEN-DECISIONS.md` como pauta
   (D1–D13). Uma hora dessa reunião destrava a onda 3 inteira.
4. **Entregue ao Codex/Opus integrador**: `RECOVERY-QUEUE.json` (a fila) +
   `ADDENDUM-V1.1.md` (o que mudou desde o snapshot). Ele executa RQ-01..RQ-10
   sem decidir arquitetura — está tudo decidido.

## O que NÃO deixar ninguém fazer

- `git clean` ou remover worktrees **antes do RQ-03** — a colheita dos 4
  writers autônomos é trabalho NÃO-COMMITADO (11+31+5+1 arquivos); limpar
  destrói.
- Merge de candidato "porque os testes focais estão verdes" — todo candidato
  passa por revisão substituta (os revisores automáticos crasharam; verde
  focal ≠ revisado).
- Aplicar migração (v10/v11_03/v13), tocar n8n/Supabase/Google Ads, ou push
  sem D9 — tudo isso tem janela própria com você presente.
- Promover tarefa no Roadmap sem a prova exigida — o `DEFINITION-OF-DONE.md`
  é binário de propósito.

## Onde está cada coisa

| Pergunta | Arquivo |
|---|---|
| O que é fato, o que é alegação? | `FACT-MATRIX.json` (42 fatos) + `ADDENDUM-V1.2.md` (execução factual mais recente) |
| Qual a ordem exata de execução? | `RECOVERY-QUEUE.json` (RQ-01..11, serial) |
| O que sai nas próximas 12h? | `NEXT-12-HOURS.md` |
| O que só você decide? | `OPEN-DECISIONS.md` (D1–D13 + H1) |
| O que está preso em cada branch? | `INTEGRATION-LEDGER.md` |
| Prompts prontos por missão | `prompts/*.md` (15) · specs: `missions/*.json` (8, validadas) |
| Plano completo | `MASTER-CLOSURE-PLAN.md` · ondas: `EXECUTION-WAVES.md` |

## Estado honesto do progresso

36,3% pela fórmula oficial do próprio roadmap (33 done + 36×0,5 partial +
1×0,25 risk sobre 141 tarefas com peso). Se as ondas 1–3 provarem todos os
aceites, a projeção mecânica chega a ~46%. Nenhum desses números é promessa —
cada ponto exige a prova listada.

*Primeiro valor visível: o diagnóstico Search real na tela da campanha
(missão M-W2-01) — não depende de nenhuma decisão sua e usa os 10 recibos
reais que já estão no banco.*
