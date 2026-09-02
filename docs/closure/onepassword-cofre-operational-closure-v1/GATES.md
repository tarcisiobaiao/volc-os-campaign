# GATES — onepassword-cofre-operational-closure-v1

**Estado deste documento:** PARCIAL. Fecha as fases 0–3. As fases 2 (prova real
do 1Password), 4 (engines em produção), 5 (página real) e 6 (API/frontend) estão
BLOQUEADAS aguardando o operador e uma permissão de escrita. Nada aqui foi
promovido a `done` por existir código.

- **Branch:** `sprint/onepassword-cofre-operational-closure-v1`
- **Base:** `origin/volc-os-v2 @ 45430e4f705d84ebd1d09f6c140e3f7d85c1b139`
- **Worktree:** `/private/tmp/volc-onepassword-cofre-operational-closure-v1`
- **Medido em:** 2026-09-01/02 (America/Sao_Paulo / UTC)

## Ambiente medido, não presumido

| O que | Medida |
|---|---|
| 1Password.app | 8.12.34, `/Applications/1Password.app` |
| Assinatura do app | `Developer ID Application: AgileBits Inc. (2BUA8C4S2C)`, notarizado (`spctl: accepted`) |
| `op` CLI | 2.39.0, `/opt/homebrew/bin/op`, mesma Team ID |
| Binário MCP | `/Applications/1Password.app/Contents/MacOS/1password-mcp` — **dentro do bundle, não no PATH** |
| Servidor MCP | `rmcp` 1.1.0, protocolo `2024-11-05` |
| Supabase oficial | `database.agenciavolc.com.br` → 178.156.196.149, PostgreSQL **15.8** |
| Homebrew | `1password-cli` é **cask**, não fórmula (`api/formula/1password-cli.json` → 404) |

## Gates verdes

| Gate | Comando | Resultado |
|---|---|---|
| Ciclo descartável v13_01 | `./scripts/provar-ciclo-v13_01.sh` | **92 provas**, PostgreSQL 15.19 |
| Testes backend do Cofre | `pytest backend/tests/test_cofre_ativos.py` | **67 passed** |
| Suíte backend inteira | `pytest backend/tests` | **2333 passed, 53 skipped** |
| Testes frontend do Cofre | `vitest run src/features/asset-vault` | **24 passed** (2 arquivos) |
| TypeScript | `tsc --noEmit -p tsconfig.app.json` | **76 erros** — o baseline herdado do webgo; **0 na autoria desta entrega** |
| Build | `npm run build` | ✓ em 8.03s |
| Autoteste do smoke CLI | `onepassword-smoke/run.py --autoteste` | **8 provas, 0 falhas** (eram 6) |
| Autoteste do importador | `importar_engines_no_cofre.py --autoteste` | **248 asserções ok, 0 falhas**; 7 payloads |
| Autoteste do onboarding | `onboarding_pagina_facebook.py --autoteste` | **56/56** |

⚠️ **`npx tsc --noEmit` puro não vale.** O `tsconfig.json` da raiz é solution-style;
sem `-p tsconfig.app.json` o compilador roda sobre zero arquivos e sai 0. Numa
primeira execução desta missão, numa worktree sem `node_modules`, o gate reportou
`TSC_ERROS=0` — falso verde, porque o `tsc` sequer estava instalado. O número
real (76) só apareceu depois de ligar `node_modules`.

## Smokes reais — o que o 1Password responde hoje

| Instrumento | Estado | Exit | Leitura honesta |
|---|---|---|---|
| `onepassword-smoke` | `blocked/sem_sessao` | 12 | **Avançou** de `blocked/cli_ausente`/10. `op` no PATH ✓, app presente ✓; falta o operador entrar. |
| `onepassword-mcp-smoke` | `blocked/nao_autenticado` | 12 | Handshake ✓, as 8 ferramentas documentadas existem ✓; `authenticate` recusado porque não há sessão. |

Ambos são o resultado **correto** para uma máquina onde o app está instalado e
ninguém entrou ainda. Nenhum dos dois é falha do instrumento.

## Supabase oficial — backup e migration

**Backup antes de qualquer escrita:**

| Campo | Valor |
|---|---|
| Caminho | `/root/backups/pre-v13_01-20260902T003721Z.dump` |
| Bytes | 2.387.295 (2.3M) |
| sha256 | `60db1793de0c9d134acfa88079c37a08636b0ed7a02ad317916fb8560145b0d5` |
| `pg_dump` exit | 0 |
| `pg_restore -l` | exit 0, legível, **2.257 itens** (TOC 2.264) |
| Origem | `Dumped from database version: 15.8` |

**Estado antes:** `tabelas=0 funcoes=0 tipos=0` com prefixo `cofre` — sem
aplicação parcial. Autoridade reconfirmada imediatamente antes.

**Aplicada:** `supabase/migrations/v13_01_cofre_de_ativos.sql`
(sha256 `786d71f134cc89c553709243ff0fc66a6ac54a70e140d08b792850ae4d7575e1`,
109.824 bytes), via `psql -v ON_ERROR_STOP=1`. Nenhuma outra migration.
**v13_99 não foi executada.**

**NÃO aplicada:** `v13_02` — o classificador de permissão recusou a escrita.

## Contraprovas pós-migration — medidas, não presumidas

Estrutura (catálogo do próprio Postgres, não a NOTICE da migration):

| Contraprova | Esperado | Medido |
|---|---|---|
| Tabelas `cofre_*` | 9 | **9** |
| RLS habilitada / forçada | 9 / 9 | **9 / 9** |
| Policies | 0 | **0** |
| Grants de tabela a `PUBLIC`/`anon`/`authenticated`/`service_role` | 0 | **0** |
| Quem tem privilégio de tabela | só `postgres` | **só `postgres`** (63) |
| Funções `cofre_*` | — | **28** (15 DEFINER, 13 INVOKER) |
| Funções sem `search_path` | 0 | **0** (as 28 com `search_path=""`) |
| `SECURITY DEFINER` sem `search_path` | 0 | **0** |
| `EXECUTE` para `PUBLIC` | 0 | **0** |
| `EXECUTE` para `service_role` | só RPC governada | **12** funções |
| Gatilhos append-only / anti-segredo | — | **8** |
| Sementes | gaveta 7, tipo 28 | **7 / 28** |

Comportamento (transacional, `ROLLBACK` ao fim):

- escrita direta por `service_role` recusada — `42501`
- leitura direta por `service_role` recusada — `42501`
- `anon` e `authenticated` não executam `cofre_listar_ativos`
- RPC governada aceita payload sanitizado
- **sete tipos de segredo recusados sem eco**: `password` (22023), `accessToken`,
  `cookie`, `private_key`, `totp`, `codigo_recuperacao`, `localizador op://`
  (23001) — a prova confere que a mensagem de recusa **não repete o valor**
- trilha append-only: `UPDATE` e `DELETE` recusados (23001)
- idempotência: mesma chave não duplica; **outro autor** é recusado (23505)
- **prova central:** as 5 funções de leitura de `service_role` não devolvem `op://`
- **não vácua:** o localizador está persistido enquanto a prova roda
- **zero resíduo:** `ativos=0 credenciais=0 operacoes=0` depois do `ROLLBACK`

## Defeitos reproduzidos e corrigidos nesta missão

| # | Onde | Defeito | Prova |
|---|---|---|---|
| 1 | `scripts/provar-ciclo-v13_01.sh` | A espera largava no servidor **temporário do `initdb`**; o primeiro `psql` caía no intervalo entre os dois servidores. Exit 2 antes da primeira prova. | 92 provas passam |
| 2 | `tools/onepassword-smoke/run.py` | O veredito de eco era avaliado **antes** da classificação por rc. Qualquer falha do `op run` casa "saída suspeita" ⇒ estados 12 e 13 eram código morto e **travar o 1Password saía como `falha/vazamento`**. | Prova g + **teste mutante**: com a condição antiga, g falha com `falha/vazamento`/20 |
| 3 | `cofre_referenciar_credencial` (v13_01) | Ficha sem `owner_nome` deixa a NOT NULL disparar e anexar `DETAIL: Failing row contains (…, op://…)`. | Reproduzido em produção, transacional. Corrigido por `v13_02` (gatilho BEFORE INSERT), provado em cluster descartável |

**Alcance honesto do #3:** `backend/app/asset_vault/infraestrutura.py:94` já
descarta mensagem do banco contendo `DETAIL:`/`Failing row contains`/`op://`.
Pela API isto **não** chegava ao browser. O que sobra — e que a peneira em Python
não alcança — é o log do servidor Postgres e qualquer consumidor futuro que fale
com o banco sem passar por aquele adapter.

## Melhoria de superfície

`--referencia-arquivo`: o localizador `op://` era passado por `--referencia`, ou
seja, ficava visível em `ps` durante a prova. O repositório trata o localizador
como sensível em todo lugar menos ali. Agora o argv carrega um **caminho**, e o
endereço mora num arquivo `0600` que o smoke recusa se estiver legível por grupo
ou outros. O recibo passa a trazer `origem_da_referencia`.

## O que NÃO foi feito

- v13_02 **não aplicada** em produção (permissão recusada)
- 1Password: sem conta, sem sessão, sem Environment, sem aprovação — **sem prova
  de lock/revogação**
- engines **não** importados em produção
- página Facebook e perfil AdsPower **não** cadastrados: não há dado real
- API/frontend não exercitados contra o Cofre povoado
- sem deploy, sem merge em `main`, sem force push
- Roadmap e curadoria **não** editados nesta branch
