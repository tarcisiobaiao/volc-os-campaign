# Runbook de schema — perfil CREATE_ONLY

Tarefa T11 · checkpoint CP2 · pacote `docs/specs/traffic-operational-closure-v2/`.

Este runbook prepara uma janela curta. **Ele não é a autorização dela.** A
autorização de execução local que produziu este arquivo cobre um PostgreSQL
descartável e mais nada; o `apply` oficial exige um ato separado
(`EXPLICIT_OFFICIAL_SCHEMA_AND_CATALOG`).

O contrato exato — arquivos, ordem, hashes, dependências e o que nunca entra no
apply — está em [SCHEMA-DEPLOY-MANIFEST.json](SCHEMA-DEPLOY-MANIFEST.json). Este
documento é o procedimento; aquele é a fonte.

## O que este perfil é, e o que ele não é

`CREATE_ONLY` é a autoridade durável do nascimento Meta PAUSED: o recibo do
`validate_only`, a aprovação humana com o plano congelado, os passos da saga, a
recuperação por leitura e a cerca versionada do trabalhador. São três tabelas e
quatorze RPCs.

> ⚠️ **Ele tem CINCO arquivos, e a versão anterior deste runbook dizia três.**
> Esse era o achado `R0-A01`. O runtime já chamava a assinatura estendida de
> `trafego_meta_create_approve` e as RPCs de recuperação que só a quarta
> migration cria — e, depois da rodada corretiva, também as de cerca que só a
> quinta cria. Quem seguisse a lista de três aplicaria um schema que o código
> não consegue usar, e descobriria isso no primeiro despacho, com a janela já
> aberta.
>
> A lista canônica mora em `SCHEMA-DEPLOY-MANIFEST.json`. Este runbook, o
> verificador e a prova local leem **a mesma**; duas listas divergem, e foi
> exatamente assim que a divergência passou despercebida.

Ele **não** inclui o read model operacional de insights (`v15_02`) nem o ledger
PMax (`v12_03`). Nenhuma guarda do `CREATE_ONLY` cita esses arquivos, então
exigi-los antes do primeiro canário faria o nascimento esperar por um dashboard
— exatamente o que o `MASTER-SPEC.json` recusa em `releases.R0.note`.

## Antes de qualquer coisa

```bash
python3 scripts/verificar_autoridade_supabase.py
```

Saída esperada: `✓ Supabase oficial: https://database.agenciavolc.com.br`.
Qualquer outra coisa encerra a janela. O único Supabase operacional deste
projeto é o self-hosted; `*.supabase.co` nunca é fallback.

## ⚠️ Nunca aplique por glob

`supabase/migrations/` tem 50 arquivos. **20 deles são rollbacks** que dropam
tabelas e funções, e os dois restantes nem são SQL (`README.md`,
`PLANO-v11_03.md`). Um `for f in supabase/migrations/*.sql` executa apply e
rollback na mesma passada.

Além disso, todo arquivo abre com `\set ON_ERROR_STOP on` — meta-comando de
`psql`. Um driver que envie o arquivo como SQL puro ou falha na primeira linha
ou, pior, ignora o `ON_ERROR_STOP` e **continua depois de um erro**, deixando
metade do schema aplicado sem ninguém saber.

O executor é `psql`. A lista de arquivos é a do manifesto, explícita e ordenada.

## Ordem do apply

| # | Arquivo | Por que ele está aqui |
|---|---------|------------------------|
| 1 | `v13_01_cofre_de_ativos.sql` | A guarda de `v15_01` exige `public.cofre_ativo`. |
| 2 | `v15_01_meta_ads_read_model.sql` | A guarda do `CREATE_ONLY` exige `public.trafego_meta_ad_account`. |
| 3 | `20260904183418_meta_create_paused_executor.sql` | As tabelas e as RPCs base. |
| 4 | `20260907120000_meta_recovery_snapshot.sql` | O plano congelado e a recuperação. **Sem ele `approve` só resolve na aridade antiga e a aprovação para em `PGRST202`.** |
| 5 | `20260907190000_meta_worker_fencing.sql` | A cerca versionada. **Sem ele toda conclusão de passo falha: o runtime manda `claim_token`, e duas RPCs (`record_fenced_dispatch`, `conclude_by_recovery`) nem existem.** |

Não digite esta lista. Peça-a:

```bash
python3 scripts/verificar_perfil_schema_meta.py --lista-apply
```

Pré-condições que as próprias guardas cobram, e abortam se faltarem:

- `current_user` é `postgres` ou `supabase_admin`;
- `server_version_num >= 150000`;
- os papéis `anon`, `authenticated` e `service_role` existem;
- nenhuma tabela do perfil já existe.

Nenhuma extensão adicional é necessária: `gen_random_uuid()` e
`hashtextextended()` são nativos do PostgreSQL 13+. Medido no ciclo local, que
aplicou sem instalar nada.

## Conferir o perfil antes de rodar

Divergência **aborta a janela**. Uma chamada, e ela sai com código diferente de
zero em qualquer violação — checksum divergente, dependência fora de ordem,
rollback dentro da lista de apply, ou RPC que o runtime chama e o perfil não
declara:

```bash
python3 scripts/verificar_perfil_schema_meta.py
```

A última conferência é a que teria pego `R0-A01` sozinha, e ela é derivada do
CÓDIGO: o verificador lê `registro.py`, extrai toda RPC efetivamente chamada e
exige que o perfil a cubra. Uma lista escrita à mão envelhece em silêncio.


## Classificar o estado antes de decidir

> ⚠️ **Existência de tabela não classifica nada.** Uma instalação com o
> `CREATE_ONLY` antigo e uma com o perfil atual têm exatamente as mesmas três
> tabelas. O que as separa são COLUNAS, CONSTRAINTS, ASSINATURAS DE FUNÇÃO e
> GRANTS — e era essa confusão que a versão anterior deste runbook carregava.

Leia o catálogo e classifique com o verificador. Ele não conecta em banco
nenhum: quem escolhe a conexão é você.

```bash
psql "$CONEXAO" -Atq -f docs/closure/traffic-operational-closure-v2/ler-catalogo-meta.sql > /tmp/catalogo.json
python3 scripts/verificar_perfil_schema_meta.py --catalogo /tmp/catalogo.json
```

Os estados são **derivados da escada**, não enumerados à mão — uma sexta
migration acrescenta um degrau sozinha:

- **`NAO_APLICADO`** — nenhum degrau presente. Aplicar na ordem declarada.
- **`ESCADA_INCOMPLETA_ATE_<arquivo>`** — os degraus até ali estão completos e
  os seguintes não. É o caso do `CREATE_ONLY` antigo sem snapshot, e o caminho é
  **forward**: aplicar só os arquivos que faltam, na ordem. Nunca rollback.
- **`PERFIL_ATUAL`** — a escada inteira está aplicada e o contrato do runtime
  confere. Não aplicar; registrar em CP2 e seguir.
- **`PARCIAL_OU_DIVERGENTE`** — há degrau presente DEPOIS de um ausente, ou
  assinatura/grant fora do contrato. Alguém aplicou fora de ordem, reverteu pela
  metade, ou existe sobrecarga duplicada. **Parar e inventariar objeto a
  objeto.**

Um rollback usado como faxina dropa tabelas que podem já conter recibos reais —
e esses recibos são a única prova de que um objeto pode existir numa conta.

## A ORDEM da reversão, quando ela for legítima

Reverter fora de ordem é pior que não reverter. O rollback do snapshot com a
cerca ainda aplicada criaria uma **segunda sobrecarga viva** de
`trafego_meta_create_flag_readback` — e com duas visíveis o PostgREST não
consegue escolher, então **nenhuma** responde — além de dropar colunas que as
funções da cerca leem.

Os arquivos recusam isso sozinhos, e a ordem é a inversa do apply:

| # | Reverter | Recusa se |
|---|----------|-----------|
| 1 | `20260907190100_meta_worker_fencing_rollback.sql` | houver `external_object_id` ou `observed_external_ids` gravados |
| 2 | `20260907120100_meta_recovery_snapshot_rollback.sql` | a cerca (`claim_token`) ainda estiver aplicada |
| 3 | `20260904183514_meta_create_paused_executor_rollback.sql` | — |


## Backup e a única pergunta que decide o rollback

Tire ponto de recuperação/export do schema `public` antes da janela. O perfil só
cria objetos novos e não altera tabelas existentes, então o risco é colisão de
nome, não perda; o export é o que permite distinguir as duas coisas depois.

```sql
-- Diferente de 0 PROÍBE o rollback.
SELECT count(*) FILTER (WHERE external_object_id IS NOT NULL) AS objetos_reais
  FROM public.trafego_meta_create_step;
```

Rollback é permitido **apenas** quando o perfil acabou de ser aplicado, a janela
falhou e as tabelas estão provadamente vazias. Com qualquer linha de aprovação
ou qualquer `external_object_id` gravado, o conserto é para frente: fechar
`META_CREATE_PAUSED_ENABLED` e `META_CREATE_LEDGER_WRITE_ENABLED`, preservar as
linhas e corrigir por migration nova.

Apagar o ledger não apaga a campanha. Apaga só a prova dela.

## Aplicar schema não abre criação

As flags de runtime continuam fechadas depois da janela, e isso é o desenho:

| Flag | Depois do apply |
|------|-----------------|
| `META_CREATE_PAUSED_ENABLED` | fechada |
| `META_CREATE_LEDGER_WRITE_ENABLED` | fechada até autorização própria |
| `META_VALIDATE_ONLY_ENABLED` | irrelevante aqui; nunca reutilizar como licença de criar |

## O que o ciclo local provou — e o que ele não prova

Exercitado num PostgreSQL 17.9 descartável (`initdb` próprio, `127.0.0.1:55432`,
datadir no scratchpad da sessão, sem qualquer ligação com o oficial):

| Etapa | Resultado |
|-------|-----------|
| apply na ordem declarada | as **cinco** aplicaram |
| fronteira de autorização com os papéis **reais** | `anon` e `authenticated` recusados na função; `anon` sem `SELECT` na tabela; `service_role` **sem `INSERT` direto**; `service_role` passa o grant e para na regra (`META_APPROVAL_NOT_FOUND`) |
| uso | `record_validation` → `approve` → `prepare_step` = `DESPACHAR` |
| concorrência real, duas sessões `psql` simultâneas no mesmo passo | `worker1=DESPACHAR`, `worker2=AMBIGUO` — **conferido por asserção**, não impresso |
| repetição | reaplicar recusado — e a prova **falha** se ele for aceito |
| cerca: trabalhador com token vencido tenta concluir | `close_step` e `fail_step` recusam com `META_STEP_CLAIM_FENCED`; o id que ele viu fica em `observed_external_ids` e **não** vira identidade do passo |
| recuperação por leitura | conclui o passo e grava a confirmação no mesmo ato |
| reversão fora de ordem | recusada pela guarda, com a causa dita |
| rollback (tabelas vazias) | aplicado; as 3 tabelas sumiram e o read model `v15_01` foi **preservado** |
| reapply | aplicada |

A fronteira foi medida com `SET ROLE`, não como superusuário: um teste que roda
tudo como `postgres` não prova autorização nenhuma, porque `postgres` passa por
cima de qualquer `GRANT`.

**Este ciclo não prova**, e o recibo não pode dizer que prova:

- em que estado o catálogo oficial está — ele não foi lido;
- que o self-hosted tenha a mesma versão, os mesmos papéis ou as mesmas extensões;
- qualquer comportamento da Meta.

## O portão local, e o que ele passou a cobrar

```bash
bash docs/closure/traffic-operational-closure-v2/prova-sql-local.sh
```

⚠️ A versão anterior **imprimia** expectativas: dizia `(precisa ser false)` ao
lado de um valor, mostrava os dois workers sem compará-los, e escrevia
`FALHA (reaplicou)` **saindo com zero**. Um portão que imprime a própria
violação e devolve sucesso não é portão — é legenda.

Agora são 30 asserções, e qualquer uma que falhe termina o script com código
diferente de zero.


## O que fecha CP2

A janela oficial autorizada, executada por esta lista, com o estado do catálogo
classificado **antes** do apply e o `sha256` de cada arquivo conferido **no
momento** da janela — e o recibo dizendo, arquivo por arquivo, o que foi
efetivamente aplicado.
