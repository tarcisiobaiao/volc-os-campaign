# Cofre de Ativos + 1Password — pacote de fechamento

> ## Candidato aceito — este pacote descreve `2971c8c`
>
> `code_sha = 2971c8c5e47e7a89cd11650d09ca17c570bc589c`, **aceito e validado**
> pelo dono da missão. Os números comprovados estão congelados em
> **[`GATES.md`](GATES.md)**; este texto não repete contagem nenhuma que possa
> divergir dela.
>
> Enquanto a branch ainda andava, este pacote carregou números que envelheceram
> — uma revisão de contrato encontrou nove. Eles não eram mentira: eram
> verdadeiros no minuto em que foram escritos. O conserto foi parar de digitar
> número: `./scripts/medir-gates-cofre.sh` gera, e `GATES.md` congela o que o
> candidato aceito provou.

Missão `asset-vault-onepassword-production-v1`.
Tudo neste pacote foi medido em **01/09/2026**, nesta worktree, rodando os gates.
Onde um número não pôde ser medido, está escrito que não pôde — ausência é
ausência explícita, não zero.

## Coordenadas

| | |
|---|---|
| Worktree | `/private/tmp/volc-asset-vault-1p-v1` |
| Branch | `sprint/asset-vault-onepassword-production-v1` |
| Base SHA | `36bec04` (`origin/volc-os-v2`) |
| `code_sha` | `2971c8c5e47e7a89cd11650d09ca17c570bc589c` — **aceito e validado** |
| Commits de produto | **9**, até `2971c8c` |
| `closure_artifact_commit` | `self_unavailable` (ver [`GATES.md`](GATES.md)) |
| HEAD final da branch | reportado externamente, após o commit documental |
| Mesclada na `main`? | **Não.** |

Os nove commits de produto, do mais antigo para o mais novo:

| SHA | Assunto |
|---|---|
| `2c4a6b6` | schema privado do Cofre, com a fronteira do segredo escrita como gramática |
| `beeb9e7` | API administrativa, e o 422 do FastAPI que devolvia a senha recusada |
| `dc2208e` | a CHECK de URL nunca era avaliada, e por isso o Cofre não guardava nenhum site |
| `1ddccf0` | a tela deixa de ler a fixture e passa a distinguir vazio de indisponível |
| `4c213de` | o handoff responde para produção e publicação — e não entrega o endereço |
| `aea3b3c` | conferir uma credencial marcava TODAS as referências do ativo |
| `664272f` | revisão pela tela — e ela manda só o que mudou |
| `9dbebdf` | a revisão adversarial refutou 7 de 8 afirmações de segurança, e ela estava certa |
| `2971c8c` | os números do fechamento passam a ser gerados, e o gerador para de mentir sobre si |

⚠️ **O HEAD se moveu enquanto este pacote era escrito, e parou de se mover.**
As primeiras rodadas de gates mediram HEADs intermediários, e as contagens deste
texto envelheceram junto. O ciclo fechou: `2971c8c` foi medido, revisado
adversarialmente, corrigido e **aceito**. Os arquivos que estavam pendentes
quando o pacote foi montado — `onboarding_pagina_facebook.py`,
`PEDIDO-AO-OPERADOR.md`, `FICHA-PAGINA-MODELO.json`, e as correções da revisão —
**estão todos commitados até `2971c8c`**, e o onboarding foi avaliado: 56/56 no
autoteste, registrado em [`GATES.md`](GATES.md).

⚠️ **A árvore está limpa.** Não há trabalho intermediário fora de commit. O que
existe além de `2971c8c` é este próprio commit documental, que corrige
procedência e não toca código de produto, teste, migration nem contrato.

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
`FICHA-PAGINA-MODELO.json` fazem parte deste pacote e **foram avaliados**:
`onboarding_pagina_facebook.py --autoteste` passa 56/56, registrado em
[`GATES.md`](GATES.md).

## Os números, num lugar só

Eles estão em **[`GATES.md`](GATES.md)**, congelados no `code_sha` aceito, e não
são repetidos aqui. Duplicar contagem em dois arquivos é como este pacote
adquiriu nove números errados: cada cópia envelhece no seu próprio ritmo, e
quem lê não sabe qual vale.

Dois deles merecem a ressalva que `GATES.md` também carrega:

- **Suíte backend inteira:** `2187 passed, 53 skipped` em `2971c8c`. O delta
  contra o baseline é `baseline_delta_not_remeasured` — o baseline foi levantado
  por `--collect-only` (uma contagem de coleta) e nunca executado, então não há
  `passed`/`skipped` de origem com que comparar.
- **Vitest completo:** a comparação contra o baseline **não é afirmada** em
  `2971c8c`; ela foi feita uma vez, num HEAD intermediário. O que está provado
  aqui é o gate focal (24/24) e o build verde.

## O que a missão entregou

**Schema privado** (`supabase/migrations/v13_01_cofre_de_ativos.sql`).
Nove tabelas `cofre_*` em `public`, `ALL` revogado nominalmente de `PUBLIC`,
`anon`, `authenticated` **e** `service_role`, RLS forçada nas nove e zero
policies. Escrita só por `SECURITY DEFINER` com allowlist de campo e blocklist
de chave normalizada. Rollback em `v13_99_cofre_de_ativos_rollback.sql`.

**Harness de prova** (`scripts/provar-ciclo-v13_01.sh`).
Aplica → opera → reverte → reaplica num Postgres descartável em Docker.
Contagem e versão em [`GATES.md`](GATES.md). O Postgres é a mesma major da
produção, medida em 15.8 nesta sessão.

**API administrativa** (`backend/app/asset_vault/`, quatro camadas).
**13 rotas** sob `/api/cofre`, todas com `exigir_admin` no nível do router.
Testes herméticos: ver [`GATES.md`](GATES.md).

**Handoff para produção e publicação** (`GET /api/cofre/ativos/{id}/handoff`).
Responde e não executa; traz provider e nome lógico, nunca o localizador.
Contrato em `docs/architecture/COFRE-HANDOFF-PRODUCAO-E-PUBLICACAO.md`.

**Tela** (`src/features/asset-vault/`). A fonte passou a ser `/api/cofre`; a
fixture deixou de ser a única fonte e **não** virou fallback. Seis estados
distinguidos. Cadastro, revisão, relação, verificação, aposentadoria e
reativação pela interface. Testes: ver [`GATES.md`](GATES.md).

**Importador de engines** (`scripts/importar_engines_no_cofre.py`).
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
