# Fechamento Global VOLC O.S. — fable-global-v1

Pacote de planejamento produzido pela missão **Fable 5 — Arquiteto de
Fechamento Global** em 2026-08-29, a partir do HEAD
`e858651a5a0c46087bf10365ebf44f7b0e8c42e3` da `main`.

Este diretório é **documental**: nenhum arquivo funcional do produto foi
alterado. Ele transforma o estado real do repositório — código avançado,
~30 worktrees, dezenas de branches de agentes, engines provadas offline,
migrações aplicadas e não aplicadas, legado n8n e um Roadmap Vivo de 17
iniciativas — em um plano executável por modelos menores sem redescoberta.

## Como usar

1. **Comece por `FACT-MATRIX.json`** — cada afirmação sobre o sistema com
   classificação (`CONFIRMADO`, `INFERIDO`, `NÃO_CONFIRMADO`, `CONTRADIÇÃO`,
   `SUPERADO`, `DECISÃO_NECESSÁRIA`) e evidência. É a base de tudo; se um
   documento daqui conflitar com a matriz, a matriz vence.
2. **`MASTER-CLOSURE-PLAN.md/.json`** — visão completa: horizontes, clusters,
   ondas, caminho crítico, riscos e ordem recomendada.
3. **`EXECUTION-WAVES.md`** — as ondas com paralelismo seguro e ownership.
4. **`missions/<id>.json`** — specs prontas para o harness
   (`tools/agent-harness/`), no contrato real do harness.
5. **`prompts/<id>.md`** — prompt copiável por missão das ondas 1–2.
6. **`INTEGRATION-LEDGER.md`** — o que está preso em branch/worktree e a
   decisão de integração de cada item.
7. **`OPEN-DECISIONS.md`** — o que só o dono pode decidir; nada aqui avança
   sozinho.
8. **`ROADMAP-CURATION-PROPOSAL.json`** — proposta de atualização do Roadmap
   Vivo e da curadoria. **É proposta**: as fontes compartilhadas não foram
   tocadas por esta missão.

## Norte operacional

- **Horizonte A** — núcleo que gera caixa: lançar e diagnosticar campanha
  Search com segurança (criação pausada/validate_only), persistir evidência no
  Supabase oficial, mostrar decisão no frontend, confirmação humana antes de
  qualquer mutação sensível, operação observável.
- **Horizonte B** — VOLC O.S. completo: multicanal, Meta, Estúdio Criativo,
  orgânico, Cofre, ORAKUL (Auto Adjust e Predictive), inteligência oficial da
  API, Data Manager, n8n, Postiz/ChatPion, Hermes/Bia, agentes de
  microcorreção, QG/workbook/grafo.

O Horizonte B é organizado sem bloquear o A; nenhuma missão do B entra no
caminho crítico do A.

## Invariantes desta análise

- Autoridade factual na ordem: curadoria humana → snapshot gerado → extração
  técnica → grafo híbrido → exports (ver `CLAUDE.md`).
- `done` sem prova não é `done` — ver `DEFINITION-OF-DONE.md`.
- Trabalho preso em worktree/branch NÃO conta como entregue — ver
  `INTEGRATION-LEDGER.md`.
- Nenhuma mutação externa (Google Ads, Supabase, n8n, processos) foi executada
  ou recomendada "para testar".

## Estado do grafo no momento da análise

`graphify-out/UPDATE_STATUS.json`: `current: true` (motivo: "insumos
idênticos"), gerado em 2026-08-29T18:15:01-03:00 no commit `a539dbd` — um
commit atrás do HEAD `e858651`, com árvore suja no build
(`working_tree_dirty_at_build: true`). Como o digest de insumos é idêntico, o
grafo foi tratado como utilizável, com essa limitação registrada na matriz.
