# Prova de revogação pelo lock — P03-T09

**Medido em:** 2026-09-01, 22:18–22:28 (America/Sao_Paulo) · máquina do operador
**Instrumentos:** `tools/onepassword-smoke` (CLI) e `tools/onepassword-mcp-smoke` (MCP)
**Condição:** cache do `op` **desligado** em todas as invocações (`--cache=false`)

## O ciclo

| # | Estado do 1Password | CLI | MCP |
|---|---|---|---|
| 1 | destrancado, aprovado | `ok` / 0 | `ok` / 0 |
| 2 | **trancado** | `blocked/sem_sessao` / **12** | `blocked/aprovacao_negada` / **13** |
| 3 | destrancado, reautorizado | `ok` / 0 | `ok` / 0 |

O acesso **cai** quando o cofre tranca e **volta** só depois de nova autorização.
Nenhum dos dois instrumentos devolveu `ok` com o cofre trancado e sem aprovação.

## Duas correções sem as quais esta prova não existiria

### 1. O estado 13 era código morto (`02a27f6`)

O veredito de vazamento era avaliado **antes** da classificação por rc, e
`varrer_saida_filho` marca como suspeita qualquer saída fora da linha canônica —
o que inclui, sempre, o caso em que o `op run` falhou e o filho nem rodou.

Consequência: `blocked/sem_sessao` (12) e `blocked/aprovacao_negada` (13) eram
inalcançáveis, e **trancar o 1Password saía como `falha/vazamento` (20)** — um
alarme de vazamento onde não houve vazamento, no único sinal que ninguém pode
aprender a ignorar. Teste mutante: com a condição antiga, a prova g falha com
`falha/vazamento`/20.

### 2. Cache quente satisfazia a prova (`0e71807`)

Medido com o cofre trancado:

    op vault list                 -> respondeu, sem pedir nada
    op --cache=false vault list   -> "authorization prompt dismissed"

`--cache` vem ligado por padrão em UNIX. Os degraus de listagem podiam responder
do cache **depois** de o cofre ter sido trancado.

**Alcance honesto:** o segredo nunca veio do cache — `op run` falhou com e sem
ele. O que vinha era metadado: nomes de cofre e de item. Ainda assim bastava para
a prova medir a coisa errada. Desligar o cache não endurece o 1Password; endurece
a medição.

## Um episódio que vale registrar

Na primeira medição após o lock, os dois instrumentos devolveram `ok`. A leitura
inicial deste agente foi "cache silencioso" — e estava **errada**. O operador
corrigiu: o app exibiu o pedido de autorização e ele aprovou com Touch ID, sem
saber que era um teste em curso.

Isso não é falha da revogação; é a revogação funcionando. O critério de aceite de
P03-T09 e a missão dizem "falha fechada **ou exige nova aprovação**". O prompt ter
aparecido é a segunda metade do critério. O que não pode acontecer — acesso
continuar sem prompt e sem aprovação — era exatamente o que o cache permitia, e
está fechado.

## O que estes instrumentos continuam NÃO provando

- **corretude do valor injetado** — o smoke não lê o segredo, de propósito
- **comprimento e hash** — proibidos: vazam entropia e confirmam palpite
- **durabilidade da aprovação além do lock** — a documentação diz "até o
  1Password travar"; foi isso que se mediu, não mais que isso
- a CLI 2.39.0 **não conhece Environments**: não há `op environment` e
  `op run --environment` responde "unknown flag". A variável do Environment é
  provada pelo MCP; a injeção da CLI usa um item de cofre descartável
