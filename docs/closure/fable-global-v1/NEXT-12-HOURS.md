# NEXT 12 HOURS — o caminho mais curto para cada resultado

Pressupõe a fila `RECOVERY-QUEUE.json` (RQ-01..11) executada em ordem pelo
integrador único. Tempos são de execução ativa, não de relógio de parede.

> **Nota de atualização:** este arquivo preserva o plano original. Para o
> ponto exato já alcançado e a fila restante, a autoridade desta janela é
> `ADDENDUM-V1.2.md`.

## 1. Diagnóstico Search consumindo os recibos v12 (o primeiro valor visível)

`RQ-01 → RQ-02 (FF bdf9e1c) → rodar M-W2-01 no harness (base_ref = main nova)`
— a missão já está validada contra o MissionSpec; o frontend já trata tudo.
**Prova de valor**: `./start-dev.sh`, abrir `/trafego/campanhas/<Maquininha|FGTS>`
e ver o diagnóstico real com fonte/janela/lido_em. Sem isso, P05-T07 não sobe.
*Não depende de nenhuma decisão do dono.*

## 2. Search lançável com segurança

Curto prazo (nesta janela): `H1` (clique dos vínculos, 5 min) + M-W2-05
(pacote de segurança) rodando no harness em paralelo.
Destrave real: sessão de decisões — **D1** (v10) → writer+caller → canário
reconciliado; **D4+D10** (janela de segurança com o RUNBOOK do M-W2-05).
O código do canário já está na main; nada disso é implementação nova grande.

## 3. Demand Gen validável

`RQ-02` entrega o builder na main → `RQ-03/RQ-08` cotejam o patch sujo do
fix-writer (11 arquivos) → `M-W2-07` (base_ref = main nova, pino de armar
destravado) registra o canal e prova pelos gates. validate_only REAL fica
atrás de **D5** — validável ≠ validado na conta.

## 4. Estúdio Criativo integrado

Já está integrado no runtime local (v11_01/02 + bancada SQLite provada).
Nesta janela: `RQ-03` preserva o patch creative-s0 (5 arquivos) e `RQ-08` o
confronta com a fronteira S0 que o FF trouxe (`d4e656d`/`1791af1`). A
promoção a produção (v11_03/worker/storage) é onda 4, atrás de **D6** — não
force nesta janela.

## 5. ORAKUL Predictive como shadow experimental

`RQ-02` traz `services/orakul_predictive/` + 15 arquivos de teste para a main;
gate dedicado `pytest backend/tests/orakul_predictive -q` no próprio RQ-02.
`RQ-03/RQ-08` avaliam o patch científico do fix-writer (31 arquivos — o maior
da colheita). **Mantém-se experimental**: zero persistência, zero agenda, zero
influência em decisão; o ledger preditivo (P14-T06) continua todo e nenhuma
promoção de status acontece. Rotular no QG como shadow experimental é parte
do RQ-10.

## 6. QG refletindo o estado real

Uma única passada, no fim: `RQ-10` = aplicar as linhas PROVADAS do
`ROADMAP-CURATION-PROPOSAL.json` (o FF já traz a expansão P04-T09/P14-T10/
P17-T09/P01-T10 no próprio roadmap), reconciliar os nós done↔decision,
rebuild pelo pipeline, `--check` verde, poda com vereditos de M-W1-06/M-W1-08.
Nada de editar fonte compartilhada antes disso — é o que evita a terceira
história divergente.

## Ordem consolidada da janela

```text
RQ-01 ─ RQ-03 (preservar colheita — ANTES de qualquer limpeza)
  └─ RQ-02 (FF bdf9e1c + gates)
       ├─ M-W2-01 (diagnóstico) ─ prova em localhost   ← valor nº1
       ├─ M-W1-06 / M-W1-08 / M-W2-05 (harness, paralelo)
       ├─ RQ-04 → RQ-05 → RQ-06 (harness são na main, serial)
       ├─ RQ-07 (candidatos Gemini com revisão substituta)
       └─ RQ-08 (portar colheita via missões) → RQ-09 (gates finais)
            └─ RQ-10 (Roadmap/curadoria/grafo, uma vez) → RQ-11 (push, se D9)
Paralelo humano: H1 (vínculos) + sessão de decisões D1/D4/D10 (destrava onda 3)
```
