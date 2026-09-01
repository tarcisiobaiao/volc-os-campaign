# Cofre de Ativos + 1Password — pacote de fechamento

> ## ⚠️ Os números deste documento envelheceram, e isso tem conserto
>
> Este pacote foi escrito enquanto a branch ainda andava. Uma revisão de contrato
> em 01/09/2026 encontrou **nove números errados** aqui — "75 provas" quando eram
> 92, "47 testes" quando eram 67, contagens de linha e um HEAD anteriores.
> Nenhum era mentira: eram verdadeiros no minuto em que foram escritos.
>
> O conserto não é "revisar melhor". É não digitar número nenhum:
> **[`GATES.md`](GATES.md) é a fonte corrente**, gerada por
> `./scripts/medir-gates-cofre.sh`. Onde este texto divergir dela, vale ela —
> e a divergência é sinal de que alguém precisa rodar o script de novo.

Missão `asset-vault-onepassword-production-v1`.
Tudo neste pacote foi medido em **01/09/2026**, nesta worktree, rodando os gates.
Onde um número não pôde ser medido, está escrito que não pôde — ausência é
ausência explícita, não zero.

## Coordenadas

| | |
|---|---|
| Worktree | `/private/tmp/volc-asset-vault-1p-v1` |
| Branch | `sprint/asset-vault-onepassword-production-v1` |
| Base SHA | `36bec04` |
| HEAD medido | `664272f39f88ecbcb110da662245a101e1f89ee4` |
| Commits | 7 |
| Diff | 21 arquivos, +9776 −475 |
| Mesclada na `main`? | **Não.** |

Os sete commits, do mais antigo para o mais novo:

| SHA | Assunto |
|---|---|
| `2c4a6b6` | schema privado do Cofre, com a fronteira do segredo escrita como gramática |
| `beeb9e7` | API administrativa, e o 422 do FastAPI que devolvia a senha recusada |
| `dc2208e` | a CHECK de URL nunca era avaliada, e por isso o Cofre não guardava nenhum site |
| `1ddccf0` | a tela deixa de ler a fixture e passa a distinguir vazio de indisponível |
| `4c213de` | o handoff responde para produção e publicação — e não entrega o endereço |
| `aea3b3c` | conferir uma credencial marcava TODAS as referências do ativo |
| `664272f` | revisão pela tela — e ela manda só o que mudou |

⚠️ **O HEAD se moveu enquanto este pacote era escrito.** A primeira rodada de
gates mediu `1ddccf0`; três commits novos entraram (`4c213de`, `aea3b3c`,
`664272f`) e **todos os gates foram rerodados** contra `664272f`. Os números
deste pacote são os da segunda rodada. Se o HEAD tiver avançado de novo quando
você ler isto, rode os gates outra vez antes de confiar em qualquer contagem.

⚠️ **A missão continuou produzindo depois da medição.** Ao fechar o pacote,
`git status --short` já mostrava nove arquivos rastreados modificados e não
commitados (`dominio.py`, `infraestrutura.py`, `rotas.py`, `provar-ciclo-v13_01.sh`,
`AssetVaultContent.tsx`, `cofreApi.ts`, `contract.ts`, `v13_01`, `v13_99`), mais
`scripts/onboarding_pagina_facebook.py` não rastreado. **Nada disso está medido
nem avaliado aqui.** Este pacote descreve `664272f` e só ele.

⚠️ **Este diretório tem mais arquivos do que este pacote.** Enquanto o pacote
era montado, o agente irmão criou aqui `PEDIDO-AO-OPERADOR.md` e
`FICHA-PAGINA-MODELO.json` — a metade humana do onboarding da página, que
`scripts/onboarding_pagina_facebook.py` consome. Eles **não são deste pacote**,
não foram medidos nem avaliados aqui, e as afirmações do índice abaixo valem
apenas para os quatro arquivos que esta missão criou.

⚠️ **A branch não foi mesclada.** É por isso que nenhuma proposta de estado
neste pacote pede `done` na fonte compartilhada. Trabalho que só existe numa
worktree não pode marcar `ROADMAP-VIVO.json` como concluído — está no CLAUDE.md
("Trabalho que só existe numa branch/worktree não pode marcar a fonte
compartilhada como concluída") e é o motivo de `DELTA-CURADORIA.json` ser um
delta **proposto**, aplicado por um integrador e não por esta missão.

## Índice

| Arquivo | O que tem dentro |
|---|---|
| `EVIDENCIAS.md` | Os doze defeitos desta missão. Para cada um: contraprova com saída literal, correção em `arquivo:linha`, e o nome do teste que impede a volta. Mais a saída literal dos nove gates. |
| `DELTA-CURADORIA.json` | Proposta de mudança de estado para 7 tarefas do roadmap, com prova e lacunas restantes. **Não aplicado.** |
| `BACKLOG-NOMEADO.md` | O que esta missão não resolveu, e por quê. |
| `README.md` | Este índice. |

Os outros dois arquivos do diretório — `PEDIDO-AO-OPERADOR.md` e
`FICHA-PAGINA-MODELO.json` — são do agente irmão, e não deste pacote.

## Os números, num lugar só

| Gate | Resultado |
|---|---|
| `./scripts/provar-ciclo-v13_01.sh` | **81 provas**, exit 0, PostgreSQL 15.19 |
| `pytest backend/tests/test_cofre_ativos.py` | **54 passed** |
| `npx vitest run src/features/asset-vault` | **21 passed**, 2 arquivos |
| `tsc -p tsconfig.app.json` | **76 erros herdados**, **0** em asset-vault |
| `npm run build` | ✓ built in 7.95s |
| `importar_engines_no_cofre.py --autoteste` | **248 asserções ok, 0 falhas** |
| `onepassword-smoke/run.py --autoteste` | **0 falhas** |
| `onepassword-smoke/run.py` | `blocked/cli_ausente`, **exit 10** — o resultado correto |

## O que a missão entregou

**Schema privado** (`supabase/migrations/v13_01_cofre_de_ativos.sql`, 2259 linhas).
Nove tabelas `cofre_*` em `public`, `ALL` revogado nominalmente de `PUBLIC`,
`anon`, `authenticated` **e** `service_role`, RLS forçada nas nove e zero
policies. Escrita só por `SECURITY DEFINER` com allowlist de campo e blocklist
de chave normalizada. Rollback em `v13_99_cofre_de_ativos_rollback.sql`.

**Harness de prova** (`scripts/provar-ciclo-v13_01.sh`).
Aplica → opera → reverte → reaplica num Postgres descartável em Docker.
**81 provas**, PostgreSQL 15.19 — mesma major da produção, medida em 15.8 nesta
sessão.

**API administrativa** (`backend/app/asset_vault/`, 4 camadas, 1368 linhas).
**13 rotas** sob `/api/cofre`, todas com `exigir_admin` no nível do router.
54 testes herméticos.

**Handoff para produção e publicação** (`GET /api/cofre/ativos/{id}/handoff`).
Responde e não executa; traz provider e nome lógico, nunca o localizador.
Contrato em `docs/architecture/COFRE-HANDOFF-PRODUCAO-E-PUBLICACAO.md`.

**Tela** (`src/features/asset-vault/`). A fonte passou a ser `/api/cofre`; a
fixture deixou de ser a única fonte e **não** virou fallback. Seis estados
distinguidos. Cadastro, revisão, relação, verificação, aposentadoria e
reativação pela interface. 21 testes.

**Importador de engines** (`scripts/importar_engines_no_cofre.py`, 1047 linhas).
Lê os manifestos versionados e emite 7 payloads para `cofre_cadastrar_ativo`.
Não escreve no banco e não faz rede. 248 asserções no autoteste.

**Smoke do 1Password** (`tools/onepassword-smoke/`, 907 linhas).
Nove estados tipados com exit code próprio. Nesta máquina o resultado real é
`blocked/cli_ausente`, exit 10 — que é o resultado correto, e não uma falha.

## O que a missão explicitamente NÃO fez

1. **Não aplicou a v13_01 em produção.** Consulta somente leitura em
   `database.agenciavolc.com.br` nesta sessão: `0` tabelas com prefixo `cofre_`.
   Aplicar exige autorização separada.
2. **Não instalou nem autorizou o 1Password.** Não há app, CLI `op`,
   `1password-mcp`, variável `OP_*` nem MCP configurado nesta máquina — os cinco
   verificados nesta sessão. O smoke prova a lógica com um dublê atrás de flag
   explícita (`--duple`), nunca em silêncio. E ele cobre o **CLI**, não o MCP.
3. **Não consertou o vazamento de `input` no 422 dos outros routers.** Cinco
   routers e 114 rotas do backend continuam com o handler padrão do FastAPI.
   Consertar mudaria o contrato de erro de rotas fora desta missão.
4. **Não cadastrou a página real do Facebook nem perfis AdsPower.** O schema
   aceita os dois (tipo `facebook_page`, tipo `browser_profile`); nenhum ativo
   real foi cadastrado.
5. **Não ligou a tela ao grafo.** A segunda metade do título de P03-T06 continua
   inteira em aberto: nenhuma correspondência é escrita, lida ou proposta.
6. **Não editou `ROADMAP-VIVO.json` nem `curadoria-operacional.json`, e não
   reconstruiu o Mapa Vivo.** Esta missão entrega delta; o integrador aplica e
   reconstrói uma vez após o merge.
7. **Não mediu a baseline do vitest no SHA base.** Verificar exigiria um
   checkout, que esta missão não pode fazer.
