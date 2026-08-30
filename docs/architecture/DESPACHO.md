# Onde o trabalho criativo roda — a verdade por ambiente

**Data:** 29/08/2026. Escrito porque eu afirmei "fila durável" sobre um SQLite
local, e a revisão pegou. Esta tabela existe para que a afirmação não se repita.

## A matriz

| | Desenvolvimento local | Teste em worktree | **Vercel (hoje)** | Worker persistente (proposto) | Postgres oficial pós-v11_03 (proposto) |
|---|---|---|---|---|---|
| Onde a fila vive | SQLite em `~/.volc-os/bancada` | SQLite em `tmp_path` | **nenhuma** | Postgres | `criativo_render_job` |
| Quem reivindica | o próprio processo | o próprio teste | — | worker, com `SKIP LOCKED` | idem |
| Quem renova lease | `Batimento`, em thread | idem | — | worker | idem |
| Quem recupera abandonado | `Reaper`, se ligado | o teste | **ninguém** | `Reaper` no worker | idem |
| Limite de execução | nenhum | nenhum | **teto da função** | do container | do container |
| Sobrevive à morte do processo | fila sim, execução não | irrelevante | **não** | sim | sim |
| O request espera? | **sim** | sim | — | não: recebe o id | não |
| Já existe? | **sim** | **sim** | — | **proposta** | **proposta** |

## O que é durável hoje, sem eufemismo

**A fila é durável no disco de uma máquina que continue existindo.** Isso vale em
desenvolvimento e em teste. **Não vale na Vercel**, onde o disco da função não
sobrevive à requisição — e é por isso que `escolher_despachante()` **recusa** ali,
em vez de gravar num SQLite que vai evaporar.

**A execução não é durável em lugar nenhum ainda.** O despachante local é
síncrono: se o processo morrer no meio, o job fica em `running` no banco. Isso já
é melhor que a task congelada de antes — o estado é visível e retomável — mas
ninguém o retoma sozinho sem um `Reaper` ligado, e ligar o `Reaper` é decisão de
quem sobe o processo.

## O que o render dentro do request custa

Trocar `asyncio.create_task` por execução síncrona resolveu **um** defeito (a task
congelada) e deixou os outros de pé:

- **teto de tempo da função** — o render longo não cabe;
- **limite de memória** — o container da função é pequeno;
- **cancelamento do cliente** — o browser desiste e o servidor não sabe;
- **retry do cliente** — segunda chamada, e a idempotência salva o dinheiro mas
  não a latência;
- **duas execuções concorrentes** — a trava `_em_voo` é por processo;
- **processo morto no meio** — `running` sem quem recupere.

Nenhum deles é resolvido por esta rodada. Todos são resolvidos pelo worker
persistente, que é proposta.

## A fronteira

`backend/app/criativo/bancada/despacho.py`:

- `DespachanteCriativo` — a porta, com `duravel` e `sincrono` declarados;
- `DespachoSincronoLocal` — a única implementação hoje, marcada `duravel = False`;
- `escolher_despachante()` — **fail-closed**: em ambiente sem processo de vida
  longa, levanta `DespachoIndisponivel` com motivo.

Quando o worker existir, ele entra aqui. `Encomenda`, `Recibo` e `MotorDeProducao`
não mudam uma linha.
