# supabase/migrations — Sprint 1A / Frente 2 (banco)

Arquivos de migration da **contenção de segurança** do VOLC O.S.

## Estado de aplicação

| Arquivo | Estado | Quando | Ambiente | Executor |
|---|---|---|---|---|
| `v8_01_app_auth_schema_and_roles.sql` | **APLICADA** | 2026-08-24 14:48:00-03 | produção — `database.agenciavolc.com.br`, banco `postgres` | `supabase_admin` |
| `v8_02` … `v8_06` | **não aplicadas** | — | — | — |
| `v8_07` (opcional) | **não aplicada** | — | — | — |

> **A série v9 não está nesta tabela.** Ela tem assunto próprio (o domínio do Hub
> de Tráfego, e não a contenção de segurança) e tabela própria, mais abaixo —
> com sha256, dependência e rollback de cada arquivo. Duas tabelas descrevendo os
> mesmos arquivos foi exatamente como este README passou a se contradizer.

⚠️ **Só v8_01 está aplicada.** Enquanto v8_03–v8_06 não forem aplicadas,
`public.users` continua em produção com **RLS desligada**, **zero policies** e
`anon` com `SELECT/INSERT/UPDATE/DELETE`. v8_01 não conserta isso e não promete
consertar: ela cria a fonte de autorização (`app_auth` + `public.volc_role_of`),
que é o que o portão do FastAPI consulta. O risco B/C do quadro de medição
abaixo **permanece aberto**.

### Evidência da aplicação de v9_02

**sha256 do arquivo:** `f5329bd3d580fdf30d11f7f0fc0903410cd4a3b01039d94772c265ee9e7a3f0e`
(194 linhas)

⚠️ **Foi aplicada duas vezes, de propósito.** A primeira aplicação usou
`3f15e0809fa03d79…`; depois corrigi um comentário do cabeçalho e o hash mudou.
Reapliquei para que o arquivo versionado e o estado do banco tenham **um hash
só** — a alternativa era registrar duas verdades e deixar quem auditasse
descobrir qual valia. `CREATE OR REPLACE VIEW` é idempotente, e a contagem de
atenção ficou igual nas duas execuções.

**O que ela faz:** substitui a expressão de UMA view. Não cria nem altera
tabela, não move dado, não toca em RLS nem em grant.

**Preflight:** guarda embutida na própria migration — aborta com mensagem
explícita se `public.trafego_inventario_campanha` não existir (ou seja, se
`v9_01` não tiver sido aplicada antes). Não há outro pré-requisito: a migration
não depende de estado de dado.

**Postflight, medido em produção:**

| prova | resultado |
|---|---|
| `security_invoker` nas duas views | `{security_invoker=true}` — **preservado** |
| ACL das duas views | `postgres=arwdDxt` + `service_role=r` — **preservada** |
| a expressão nova está na view | `pg_get_viewdef(...) LIKE '%removida%'` → `t` |
| as 6 tabelas | 6 com RLS, 6 com RLS **forçada** — intactas |
| policies em `trafego_*` | **0** |
| grants para `anon` / `authenticated` | **0** |
| `anon` em `trafego_inventario_campanha` | **HTTP 401** |
| `anon` em `trafego_inventario_conta` | **HTTP 401** |
| condições de atenção | **2 de 84** (eram 81) |

`NOTIFY pgrst, 'reload schema'` executado após cada aplicação.

**Rollback:** aplicável e **não executado**. Reverter é reaplicar o bloco
`CREATE OR REPLACE VIEW` de `v9_01` (linhas 1153–1288), que restaura o `CASE`
anterior. Não há `v9_99` próprio porque não há o que desfazer além da
expressão: nenhuma estrutura foi criada.

⚠️ Reverter sozinho **quebra a concordância** com `dominio.pede_atencao()`, e há
teste que compara os dois linha a linha. Os dois mudam juntos, sempre.

### Evidência da aplicação de v9_01

**sha256 do arquivo:** `7c55ebff4ee41ba5c83c513a9afc5f1928790498583bff55bc2b1cba9b396773`
(1471 linhas) · **rollback:** `v9_99`, `aadafc5091ccda4b…`, 148 linhas, **não executado**

**Preflight** rodado antes: os 15 itens `ABORTA` no valor esperado. Duas
divergências informativas, que não bloqueiam e reforçam a decisão de revogar
nominalmente: o default ACL de `public` concede a `anon` em **6** casos (a nota
esperava 2) e há **2** gatilhos legados ativos (esperava 1).

**Aplicação:** transação única, `ON_ERROR_STOP=1`, zero erros, `COMMIT`.
Os dois NOTICE da própria migration confirmaram na saída:
*"6 tabelas com RLS forcada + 2 views security_invoker, zero policies,
anon/authenticated revogados nominalmente"* e *"verificacao interna passou"*.

**Postflight:**

| prova | resultado |
|---|---|
| 6 tabelas | RLS ligada **e forçada** nas seis |
| ACL das tabelas | só o dono + `service_role` com `arw` |
| `trafego_evento` | `ar` apenas — sem UPDATE, sem DELETE |
| 2 views | `security_invoker=true`, `service_role` com `r` |
| policies | **zero** |
| `anon` / `authenticated` | nenhum grant |

**PostgREST real** (não shim), em `https://database.agenciavolc.com.br/rest/v1`:

| prova | resultado |
|---|---|
| `trafego_inventario_conta` / `_campanha` com `service_role` | HTTP 200 |
| filtros `eq`, `in`, `is.null`, `neq` | HTTP 200 |
| `order` composto e `count` por HEAD | HTTP 200 |
| projeção de atenção (`atencao=is.true`) | HTTP 200 |
| as cinco tabelas/views com `anon` | **HTTP 401 · 42501 permission denied** |

`NOTIFY pgrst, 'reload schema'` executado após o COMMIT.

### Evidência da aplicação de v8_01

| prova | resultado |
|---|---|
| `to_regprocedure('public.volc_role_of(uuid)')` | `volc_role_of(uuid)` (não é mais NULL) |
| ADMIN ativos em `app_auth.user_roles` | exatamente **1** |
| esse ADMIN casa com o `sub` de `auth.users` | sim — `app_auth.user_roles.auth_user_id = auth.users.id` |
| `public.volc_role_of(sub)` | `ADMIN` |
| RPC via `service_role` (REST) | `HTTP 200` → `"ADMIN"` |
| RPC via `anon` (REST) | `HTTP 401` — `permission denied for function volc_role_of` |
| `volc_grant_role` via `anon` (REST) | `HTTP 401` — `permission denied` |
| tabela de `app_auth` via REST com `service_role` | `HTTP 404` — schema não exposto |
| `USAGE` em `app_auth` para anon/authenticated/service_role | `false` nos três |
| linha de auditoria da semeadura | 1, `source = seed v8_01`, ator `supabase_admin` |
| `PGRST_DB_SCHEMAS` | `public,storage,graphql_public` — `app_auth` fora |

⚠️ **v8_01 exige `supabase_admin`, não `postgres`.** A primeira tentativa, como
`postgres`, abortou com `must be owner of function public.get_current_user_role`
e fez **rollback completo** (nada persistiu — verificado). A função legada é
propriedade de `supabase_admin`, e `postgres` não é membro dele
(`pg_has_role('postgres','supabase_admin','MEMBER')` = `f`). A guarda da própria
migration aceita os dois papéis, mas só `supabase_admin` completa.

## Convenção de numeração

Este diretório estava vazio. A numeração segue a convenção que o repositório já
usa em `src/sql/` — `vN_MM_nome.sql`, sequencial e topológica — cuja última
entrada é `src/sql/v7_18_trafego_copy.sql`. A Frente 2 abre a série **v8**.
O sufixo `.OPCIONAL.sql` segue o precedente de
`src/sql/volc-sync/04_monthly_exchange_rate.BLOQUEADO.sql`: arquivo fora da
ordem obrigatória, que exige decisão antes de rodar.

## Ordem de aplicação — topológica, não inverta

| # | Arquivo | Papel do banco | O que faz | Quebra algo? |
|---|---|---|---|---|
| 1 | `v8_01_app_auth_schema_and_roles.sql` | `supabase_admin` ⚠️ | schema privado `app_auth`, tabela de papéis ligada a `auth.users.id`, auditoria, funções de portão, seed a partir de `public.users` | não |
| 2 | `v8_02_pautador_policies_rewire.sql` | `postgres` | reescreve as 23 policies do Pautador para o portão novo | muda autoridade de papel (ver abaixo) |
| 3 | `v8_03_users_rls_policies.sql` | `supabase_admin` | liga RLS em `public.users`, 6 policies por operação, 2 gatilhos, índice e constraint | não, se houver ADMIN semeado |
| 4 | `v8_04_users_grants.sql` | `supabase_admin` | zera `anon`; grants mínimos por coluna para `authenticated` | não |
| 5 | `v8_05_users_safe_view.sql` | `postgres` | `public.users_safe` — DTO sem colunas sensíveis | não |
| 6 | `v8_06_users_sensitive_columns_revoke.sql` | `supabase_admin` | tira o `SELECT` de `password_hash`, `token_primeiro_acesso`, `token_expiracao` | **SIM — ver pré-condição** |
| — | `v8_07_default_privileges_hardening.OPCIONAL.sql` | `postgres` **e** `supabase_admin` | tabela nova em `public` deixa de nascer aberta a `anon` | mudança de plataforma |
| — | `v8_99_rollback.sql` | ambos | rollback completo e parcial | — |

**Por que dois papéis.** `public.users` é propriedade de `supabase_admin`;
`postgres` **não** é membro de `supabase_admin` (`pg_has_role` = f) e seus grants
na tabela têm `is_grantable = NO`. Logo `ENABLE RLS`, `CREATE POLICY`,
`CREATE TRIGGER`, `GRANT` e `REVOKE` sobre `public.users` exigem
`supabase_admin`. As tabelas `pautador_*` são de `postgres`. Cada arquivo tem
uma guarda que aborta com a mensagem certa se rodar com o papel errado.

⚠️ **v8_01 também exige `supabase_admin`**, ao contrário do que este README e o
cabeçalho da própria migration diziam. Ela toca
`public.get_current_user_role()` (REVOKE + COMMENT), que é propriedade de
`supabase_admin` — e `COMMENT ON FUNCTION` exige ser dono, não basta ter
privilégio. Medido em produção em 24/08/2026: aplicar como `postgres` aborta a
transação inteira no fim do arquivo.

```bash
# exemplo — arquivo de postgres
-- (comando de aplicacao: ver runbook privado de infraestrutura)
  -- (comando de aplicacao: ver runbook privado de infraestrutura)

# exemplo — arquivo de supabase_admin
-- (comando de aplicacao: ver runbook privado de infraestrutura)
  -- (comando de aplicacao: ver runbook privado de infraestrutura)
```

## O que foi medido antes de escrever (2026-08-24, só `SELECT`)

| # | Achado | Evidência |
|---|---|---|
| A | `public.users` com RLS **desligada** e **zero** policies | `pg_class.relrowsecurity = f`; `pg_policies` = 0 linhas |
| B | `anon` e `authenticated` com os **7** privilégios em `public.users` | `information_schema.role_table_grants` = 28 linhas |
| C | `password_hash`, `token_primeiro_acesso`, `token_expiracao` e `role` com `SELECT/INSERT/UPDATE/REFERENCES` para `anon` | `information_schema.column_privileges` |
| D | **Não existe** tabela de papel em nenhum schema de aplicação | busca `~* 'role\|perm\|grant\|acl\|auth\|admin\|member'` → só `auth.oauth_*` |
| E | `public.users.id` **não é** `auth.users.id` | JOIN por `id` = 0 linhas; por `lower(email)` = 1 linha |
| F | `get_current_user_role()` lê `app.current_user_role`, que ninguém define; e **nenhum** código a chama | `pg_proc.prosrc`; `grep` em `src/ server/ api/ backend/` = 0 |
| G | 23 policies do Pautador autorizam por `public.users.role` — a coluna que `authenticated` podia escrever | `pg_policies` em 12 tabelas `pautador_*` |
| H | `pg_default_acl` de `public` dá `arwdDxt` a `anon` em **toda tabela nova** e `EXECUTE` em **toda função nova** | `pg_default_acl`, 2 donos (`postgres`, `supabase_admin`) |
| I | `service_role` tem `rolbypassrls = t` | `pg_roles` |
| J | 1 usuário, `ADMIN`; as 3 colunas sensíveis 100% `NULL` | `count(coluna)` = 0 |
| K | `PGRST_DB_SCHEMAS=public,storage,graphql_public` | `/root/supabase/docker/.env` |

## Decisão do item 1 — schema privado, não tabela em `public`

Escolhido `app_auth` (schema privado). Justificativa completa no cabeçalho de
`v8_01`. Resumo: por **H**, uma tabela em `public` nasce escrita por `anon` e a
proteção passa a depender de lembrar de revogar; por **K**, `app_auth` não tem
rota no PostgREST para papel nenhum — nem `service_role` — então
`api/supabase/query.js:34`, que aceita nome de tabela arbitrário do request com
a service key, **não alcança** a fonte de papel; e por **I**, RLS em tabela de
`public` não protegeria contra a service key de qualquer forma.

## Sequenciamento — os dois pontos onde a ordem importa

**1. `v8_02` antes de `v8_04`.** Expressão de policy roda com os privilégios de
quem consulta. As 23 policies do Pautador leem `public.users` na expressão;
revogar o grant sem reescrevê-las derruba as 12 telas com
`permission denied for table users`. `v8_04` tem guarda que aborta se sobrar
qualquer policy nessa condição.

**2. `v8_06` só depois da Frente 1/3.** `select('*')` com grant por coluna
devolve `42501 permission denied for column password_hash`. Ocorrências medidas:
`src/hooks/useUserProfile.ts:62` e `src/hooks/useUserProfile.ts:72`. Devem
migrar para `public.users_safe` (entregue em `v8_05`) ou para lista nominal de
colunas. Nenhuma guarda SQL consegue verificar isso — é decisão humana.
Se aplicar cedo, o conserto é uma linha:
`GRANT SELECT ON TABLE public.users TO authenticated;`

## Mudança operacional que a Frente 1/3 precisa absorver

A partir de `v8_02`, **ADMIN** deixa de significar "linha em `public.users` com
`role='ADMIN'`" e passa a significar "linha ativa em `app_auth.user_roles` para
o `sub` do JWT". Um admin criado pelo caminho legado
(`api/users/create.js:82` insere em `public.users`) **não recebe papel**.

Caminho suportado, com `EXECUTE` apenas para `service_role`:

```sql
SELECT public.volc_grant_role('<auth.users.id>', 'ADMIN', 'motivo');
SELECT public.volc_revoke_role('<auth.users.id>');
SELECT public.volc_is_admin('<auth.users.id>');   -- backend, por sub do JWT
SELECT public.volc_current_admin();               -- browser, sobre o próprio JWT
```

**Não existe** trigger espelhando `public.users.role` → `app_auth`, de
propósito: `server/index.js:251` (`/api/supabase/update`) escreve em qualquer
tabela com a service key e sem autenticação; o espelho reabriria a escalada que
esta frente fecha.

## O que esta frente **não** contém — dito sem rodeio

- **`service_role`**. `rolbypassrls = t` (**I**). Nenhuma policy ou grant deste
  conjunto limita `api/supabase/{query,insert,update,rpc}.js`,
  `server/index.js:165-403`, `api/users/query.js:34` ou `api/users/create.js:63`.
  Quem fecha isso é a Frente 1/3 (`requireUser`/`requireAdmin`/
  `requireServiceIdentity`). O banco não tem como distinguir "backend legítimo"
  de "quem achou a chave".
- **`backend/app/deps.py:20-21`** — `if not expected: return` faz o portão do
  Pautador **falhar aberto** quando `PAUTADOR_API_KEY` não está setada, e a mesma
  chave vai ao browser via `VITE_PAUTADOR_API_KEY` (`src/lib/pautadorApi.ts:37`).
  Fora desta frente.
- **`public.user_campaigns` e `public.user_projects`** — RLS desligada e os
  mesmos 7 privilégios para `anon`. São a fonte de escopo do OPERATOR; contê-las
  exige desenhar as policies de escopo junto, senão as telas de operador
  esvaziam. **Sprint 1B.**
- **Tabelas `pautador_*` sem policy** — `pautador_entity_axes`,
  `pautador_question_choices`, `pautador_validation_runs` estão com RLS
  desligada. (`pautador_trafego_copy` e `project_wordpress` estão com RLS ligada
  e zero policies, ou seja, já negam tudo.) **Sprint 1B.**
- **As outras 33 tabelas de `public` com RLS desligada.** Inventário, não
  exclusão em massa.
- **Superfície de RPC.** `public` tem **108** funções; praticamente todas com
  `EXECUTE` para `anon` (herança do achado **H**). Entre elas há funções que
  reescrevem base financeira em massa — `update_all_revenue_conversions`,
  `recalculate_all_operator_commissions`, `merge_duplicate_projects`,
  `cleanup_old_events`, `refresh_campaign_highlights`. Combinadas com
  `api/supabase/rpc.js:34`, que aceita `functionName` arbitrário do request,
  são a superfície mais larga que sobrou. Fechá-la exige uma lista de
  permissão de RPC (Frente 1/3) **e** uma revisão função a função dos grants —
  não cabe nesta frente e não deve ser feita às cegas. **Sprint 1B.**
- **`public.delete_auth_user_on_user_delete()`** — `SECURITY DEFINER`, apaga de
  `auth.users`, com `EXECUTE` para `anon`, e **não está ligada a trigger
  nenhum** (o único trigger de `public.users` é
  `trigger_user_commission_update`). Não é chamável por RPC (o Postgres recusa
  chamada direta de função de trigger), mas é código órfão com privilégio
  máximo. Classificar antes de remover, conforme o protocolo de legado do
  `CLAUDE.md`.

## Proposta, não executada — migração dos campos sensíveis

`v8_06` **contém o acesso**; não move nem apaga nada. `password_hash`,
`token_primeiro_acesso` e `token_expiracao` continuam em `public.users`, com o
conteúdo intacto (hoje: 100% `NULL`, achado **J**).

Proposta para um sprint seguinte, a decidir:

1. `password_hash` é resíduo de autenticação própria. Quem autentica hoje é o
   GoTrue (`auth.users.encrypted_password`); `src/contexts/AuthContext.tsx:132`
   usa `supabase.auth.signInWithPassword`. A coluna provavelmente é legado morto
   — mas isso precisa ser **provado** (n8n, SQL ad hoc, scripts em `sql/`
   como `sql/fix_marliseac_password_final.sql`) antes de qualquer `DROP`.
2. `token_primeiro_acesso` / `token_expiracao` são credenciais de uso único.
   Lugar natural: tabela própria em `app_auth`, com TTL e expurgo, nunca em uma
   tabela que a UI lê.
3. Enquanto não houver decisão, o estado de `v8_06` é suficiente: as colunas
   existem, o dado está preservado, e nenhum papel do PostgREST as enxerga.

## Rollback

`v8_99_rollback.sql`. Cobre o rollback completo e traz uma seção de **rollback
parcial por sintoma** — que é o que quase sempre se quer. O arquivo detecta o
papel e pula as seções que não pode executar, então pode ser rodado inteiro
duas vezes (uma como `postgres`, outra como `supabase_admin`). Não usa
`BEGIN/COMMIT` global de propósito: cada seção é um `DO` atômico independente,
para que um rollback parcial não seja tudo-ou-nada.

Rodá-lo **reabre** `public.users` para `anon`. Trate como incidente até
reaplicar a contenção. Ele **não** apaga nenhuma linha de `public.users`; apaga
o schema `app_auth` (papéis e trilha de auditoria) — há comandos `\copy` no
cabeçalho para exportar antes.

## Nota de manutenção

As funções de portão são `SECURITY DEFINER` com `search_path = ''` e todos os
nomes qualificados. Elas dependem de o **dono** ter `BYPASSRLS` para ler
`app_auth.user_roles` (que tem `FORCE ROW LEVEL SECURITY` e zero policies) e
`public.users`. Se alguém trocar o dono dessas funções para um papel sem
`BYPASSRLS`, o portão passa a devolver `false` para todo mundo — falha fechada,
mas trava o sistema. Confira com:

```sql
SELECT p.proname, pg_get_userbyid(p.proowner) AS dono, p.prosecdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public' AND p.proname LIKE 'volc\_%';
```

---

# Série v9 — inventário operacional de Tráfego (Fase 1B / Frente 1)

Tudo acima é a **contenção de segurança** (Sprint 1A / Frente 2). Daqui para
baixo é outra frente, com outro assunto: o domínio novo do Hub de Tráfego.

## Estado da série v9 — a tabela única

⚠️ **Esta tabela contradizia a do topo deste arquivo.** Ela dizia `v9_01` **não
aplicada**; a do topo dizia **APLICADA** em 25/08. A do topo estava certa: esta
foi escrita antes da aplicação e nunca atualizada, e ficou meses afirmando o
contrário do que o banco mostrava.

Conferido contra a produção em 26/08/2026, somente leitura: as 8 relações da
v9_01 existem, a expressão de `atencao` da v9_02 está na view, e nem `historico`
nem `ordem_operacional` estão publicadas.

**Duas contagens diferentes registradas como verdade é pior que nenhuma:** a que
alguém ler primeiro vence, e a outra não denuncia nada. Daqui para a frente, a
série v9 tem **uma** tabela, e é esta.

| Arquivo | Estado | Quando | Ambiente | Executor | sha256 | Depende de | Rollback |
|---|---|---|---|---|---|---|---|
| `v9_01_trafego_inventario.sql` | **APLICADA** | 2026-08-25 07:26:41-03 | produção — `database.agenciavolc.com.br`, banco `postgres` | `postgres` | `7c55ebff4ee41ba5c83c513a9afc5f1928790498583bff55bc2b1cba9b396773` | — | `v9_99_trafego_inventario_rollback.sql` |
| `v9_02_atencao_sem_removida.sql` | **APLICADA** | 2026-08-25 07:57-03 (reaplicada 08:04-03) | produção — idem | `postgres` | `f5329bd3d580fdf30d11f7f0fc0903410cd4a3b01039d94772c265ee9e7a3f0e` | v9_01 | reaplicar a definição da view como está na v9_01 (§8) |
| `v9_03_historico_e_ordem_operacional.sql` | **APLICADA** | 2026-08-26 14:35-03 | produção — idem | `postgres` | `80855e5e89aae483d93a4073bac6fb3a6ced5226eabffb78a250f7a758a1f1bf` | v9_01, **v9_02** | **`v9_03_rollback.sql`** |
| `v9_04_url_final_preservada.sql` | **APLICADA** | 2026-08-26 14:36-03 | produção — idem | `postgres` | `7076ba97d48edb68f3eef39e4b8c5d5323030dc15152aa38f8148b0160a2eeba` | v9_01 | **`v9_04_rollback.sql`** |
| `v9_03_rollback.sql` | não executada | — | ciclo completo provado | — | `08d3d9c2ff001681e6c212bb82e80f1ccf91792ad0b69afffb1c7b99b5dfdd50` | v9_03 aplicada | — |
| `v9_04_rollback.sql` | não executada | — | ciclo completo provado | — | `edf442248610a378c6924c7cdb07c2d916c42d1884de24469970fb0ea70832eb` | v9_04 aplicada | — |
| `v9_99_trafego_inventario_rollback.sql` | não executada | — | — | — | `aadafc5091ccda4be1cec56442e2fdb2a86833fadeb9499723c1483350c2ce72` | v9_01 aplicada | — |

### ✅ APLICADAS em 26/08/2026 — a janela

Autorizadas nominalmente pelo dono, aplicadas por `postgres` em
`database.agenciavolc.com.br` / banco `postgres`, Postgres 15.8.

**Preflight**, tudo verde antes da primeira escrita: os quatro hashes conferidos
contra os autorizados · host, banco e executor confirmados · v9_01 8/8 relações e
v9_02 na view · v9_03 e v9_04 ausentes · view, função, ACLs, RLS e contagem de
colunas preservados em `/root/janela-v9_03_04-20260826-1734` (700/600) ·
**backup verificado com `pg_restore --list`: 1.847 objetos legíveis**.

**Postflight de cada uma:**

| prova | v9_03 | v9_04 |
|---|---|---|
| COMMIT sem erro | ✓ | ✓ |
| colunas / função | 2/2 publicadas | `url_final` preservada |
| `security_invoker` | ligado | ligado |
| `service_role` SELECT | true | true |
| `service_role` INSERT/UPDATE/DELETE | false, false, false | — |
| `anon` (4 privilégios) | todos false | — |
| `authenticated` (4 privilégios) | todos false | — |
| RLS forçada | 6/6 tabelas | 6/6 |
| guarda "nº sem carimbo" | — | **viva** |
| guarda leitura retroativa | — | **viva** |

E as guardas foram provadas **funcionando**, não só presentes — em transação
abortada, sem deixar linha: número sem carimbo **recusado**, leitura retroativa
**recusada**, `url_final` **sobreviveu** a uma leitura que não a trouxe.

**Varredura somente leitura** logo após, com `FORGE_PERMITIR_ESCRITA` ausente:

| conta | resultado | campanhas | duração | consultas |
|---|---|---:|---:|---:|
| PMUNDO+ · 3849678045 | ok | 74 | 6.966 ms | 3 |
| Portal Mundo Mais · 5478096539 | ok | 5 | 6.054 ms | 3 |
| Crédito Up · 8017851692 | ok | 5 | 5.766 ms | 3 |

Zero falhas. **`url_final` passou a ser preenchida**: 40 de 84 no total, e **5 de
5 nas operacionais**. A regra forte da reconciliação (`url_final_da_conta`)
passou a disparar — antes só a URL do nome casava.

### O pacote (histórico da preparação)

`v9_03` e `v9_04` estão escritas, com rollback executável cada uma, e o ciclo
completo foi provado em Postgres descartável:

```
v9_01 → v9_02 → v9_03 → v9_04
      → rollback v9_04 → rollback v9_03
      → reaplicar v9_03 → reaplicar v9_04
```

Rode você mesmo: **`./scripts/provar-ciclo-migrations.sh`**. O cluster nasce e
morre no script; nada fora de `/tmp` é tocado.

Em **cada** degrau do ciclo ele confere: `security_invoker` ligado ·
`service_role` com SELECT e **sem** INSERT/UPDATE/DELETE na view · `anon` e
`authenticated` sem nenhum dos quatro privilégios · as duas guardas do gatilho
vivas. E, no fim, prova que as guardas **funcionam**: número sem carimbo é
recusado, leitura retroativa é recusada, e `url_final` sobrevive a uma leitura
que não a trouxe.

⚠️ **Nada disso foi aplicado em produção.** A aplicação exige autorização
própria, como sempre exigiu.

### Sobre o incidente de credenciais

O `JWT_SECRET` da instância é o segredo público de demonstração, e mais 12
segredos críticos também
([`docs/INCIDENTE-JWT-SECRET.md`](../../docs/INCIDENTE-JWT-SECRET.md)). O dono
**aceitou o risco temporariamente** em 26/08/2026, com prazo até o gate de
pré-lançamento e seis gatilhos de reavaliação imediata.

O incidente **não bloqueia mais** a preparação nem o desenvolvimento. Ele
continua aberto, e continua sendo gate obrigatório antes de qualquer operação
externa.

### Dependências, e por que a ordem importa

`v9_03` exige a **v9_02**, e a própria migration se recusa a aplicar sem ela.
Não é formalidade: sem a v9_02, `atencao` ainda marca `removida`, e
`ordem_operacional` poria as 79 campanhas removidas no degrau 0 — à frente das
5 que existem. A lista sairia **exatamente invertida**, e nada no resultado
denunciaria.

### O rollback "óbvio" da v9_03 não funciona

Reaplicar a `v9_02` **não** reverte a `v9_03`. Medido em Postgres 16
descartável, com v9_01..v9_04 aplicadas:

```
psql -f v9_02_atencao_sem_removida.sql
ERROR:  cannot drop columns from view
```

`CREATE OR REPLACE VIEW` sabe trocar a expressão de uma coluna e sabe
acrescentar colunas no fim. Não sabe **remover** — e a v9_03 acrescentou duas.
Um rollback documentado que aborta é descoberto no único momento em que alguém
precisa dele.

`v9_03_rollback.sql` faz `DROP` + `CREATE` + os grants que o `DROP` leva junto.
O ciclo aplicar → reverter → reaplicar foi provado ponta a ponta.

⚠️ **Reverter o schema exige reverter o código junto.** A U0 filtra por
`historico` e ordena por `ordem_operacional`; sem as colunas, toda leitura do
inventário responde erro do PostgREST.

### `v9_04_rollback.sql` — e por que o corpo dele foi **extraído**, não redigitado

A nota antiga mandava "reaplicar a definição da função como está na v9_01". Isso
é **instrução manual**, não rollback — e a própria v9_04 nasceu de um erro desse
tipo: reescrevi a função a partir do texto e apaguei oito linhas sem perceber,
entre elas a guarda "nenhum número sem carimbo", que é a regra A do schema. A
migration reportou sucesso.

`CREATE OR REPLACE FUNCTION` substitui o **corpo inteiro**. Quem reescreve a
função à mão apaga tudo o que não copiar de volta, em silêncio.

Por isso o corpo do rollback foi **extraído** do `v9_01`, e há prova de que ele é
byte a byte o mesmo. E o próprio rollback se recusa a terminar se qualquer uma
das duas guardas sumir — as mesmas verificações que a v9_04 faz, pela mesma
razão: um rollback pode apagar uma regra tão facilmente quanto a migration que
ele reverte.

⚠️ **Reverter a v9_04 exige reverter `adaptador_search.py` junto.** O adaptador
passou a colher `url_final` e OMITE a chave quando a leitura falha — sem a
preservação **e** sem a omissão, uma leitura de anúncio que falhe apaga a URL da
conta inteira, e a reconciliação volta a responder `sem_campanha`, que **libera**
a montagem de uma segunda campanha para o mesmo termo.

**Ordem de reversão:** v9_04 antes de v9_03. Elas não se tocam (uma é função de
gatilho, a outra é view), mas a ordem inversa da aplicação mantém o par
consistente em qualquer ponto.


As duas foram provadas em um PostgreSQL **descartável**, criado e destruído por
`scripts/testar_migration_descartavel.sh`: **146 provas**, incluindo acesso
negativo real com `SET ROLE` para `anon` e `authenticated`, e mais **26 testes
da camada de acesso** (`backend/tests/test_trafego_persistencia.py`) rodando
contra um cluster com esta mesma migration aplicada. Nada foi executado em
produção.

**Cada prova de recusa exige o motivo certo.** O ajudante `_prova_recusa` do
script pedia só que o banco recusasse — e um erro de digitação no próprio teste
contava como prova. Agora ele confere o `SQLSTATE` (23514 CHECK, 23505 unique,
23503 FK, 23001 `restrict_violation`) **e** o nome da constraint ou o trecho da
mensagem do gatilho. A primeira execução com a regra nova reprovou uma prova que
vinha passando havia semanas, e o achado era real: o gatilho de identidade tinha
um ramo de código morto (`customer_id nao pode voltar a NULL`) que nunca chegou
a executar, porque o ramo anterior já cobria o caso.

## Série v10 — ciclo de criação e autogestão T1 · **v10_01, v10_03 e v10_04 APLICADAS**

> Janela autorizada em 31/08/2026: **v10_01, v10_03 e v10_04**. A `v10_02`
> ficou deliberadamente de fora — é autogestão T1 e não participa do caminho
> `/subir`. Nem a v10_03 nem a v10_04 dependem dela.

| Arquivo | sha256 | Linhas | Estado | Rollback |
|---|---|---|---|---|
| `v10_01_intencao_e_lote.sql` | `827e8caae24b088f…` | 1950 | **APLICADA** 2026-09-01 00:17-03 | `v10_01_rollback.sql` (`b75eb90b09447493…`) |
| `v10_02_autogestao.sql` | `124eac489c9d3bb8…` | 1722 | **não aplicada** (fora da janela) | `v10_02_rollback.sql` (`37a0f0e560a940c1…`) |
| `v10_03_recibo_atomico.sql` | `bdb26eed7da08b64…` | 992 | **APLICADA** 2026-09-01 00:17-03 | `v10_03_rollback.sql` (`b1c9d6598bd0bf52…`) |
| `v10_04_saida_do_indeterminado.sql` | `9122135ac98de62e…` | 384 | **APLICADA** 2026-09-01 00:17-03 | `v10_04_rollback.sql` (`eb93e200b66cf6df…`) |

### Recibo da aplicação — 2026-09-01, produção `database.agenciavolc.com.br`

Ambiente: `ubuntu-4gb-ash-1` (178.156.196.149), container `supabase-db`,
PostgreSQL 15.8. Executor: `postgres`, via
`docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1`.
Autorizado nominalmente pelo dono, com a v10_02 explicitamente fora da janela.

**Backup pré-migration:** `/root/backups/pre-v10-search-2026-09-01-001700.dump`
· 2.229.154 bytes (2,2 MB) · `pg_dump -Fc` exit 0 ·
sha256 `b1631c8c6d206ea4236622182537c92004c9ac427069adfc8208d75fc00f88d1` ·
`pg_restore -l` lista 2081 itens (o arquivo é um archive legível, não um truncado).

**Estado medido ANTES:** zero tabelas da v10, zero funções `trafego_ledger_*`,
`trafego_campanha` e `trafego_linhagem` presentes (v9_01 aplicada), os três papéis
nominais existentes. Nenhum objeto inesperado, nenhuma aplicação parcial.

**Contraprova DEPOIS (todas verdes):**

| Query | Esperado | Medido |
|---|---|---|
| 5.1 tabelas da v10 | 10 | **10** |
| 5.2 vazamento para `anon`/`authenticated` | 0 | **0** |
| 5.3 execução do ledger | só `service_role` nas 4 funções | **12 linhas: `f`/`f`/`t` nas 4** |
| 5.4 camada 4 (`trafego_recibo_um_voo_por_item`) | 1 | **1** |
| 5.5 RLS forçada sem policy | 0 sem RLS · 0 policies | **0 · 0** |
| 5.6 v10_04 entrou **e** guardas da v10_01 sobreviveram | 5×`t` | **t t t t t** |
| 5.7 reconciliação confere posse | `t` | **t** |
| 5.8 `SECURITY DEFINER` no ledger | 0 | **0** |
| v10_02 fora da janela | 0 tabelas | **0** |

⚠️ A 5.6 confere as **duas** metades de propósito. `CREATE OR REPLACE FUNCTION`
substitui o corpo inteiro, e uma versão anterior da v10_04 acrescentou a transição
nova apagando quatro guardas da v10_01 em silêncio. Conferir só a transição
deixaria passar exatamente isso.

### v10_04 — a saída do indeterminado, que não existia (31/08/2026)

A v10_03 entregou `trafego_ledger_reconciliar` como única saída de um item
`indeterminado`. Ela **nunca poderia ter funcionado** no caminho para o qual foi
escrita, e isso passou por três revisões sem ser visto:

1. a chamada de criação não responde;
2. `trafego_ledger_fechar(...,'sem_resposta')` põe o item em `indeterminado` **e o
   lote em `interrompido`**;
3. a reconciliação tenta `UPDATE trafego_lote SET estado='concluido' WHERE ...
   estado IN ('executando','interrompido')`;
4. `trafego_lote_estado_valido` (v10_01) recusa: `interrompido->concluido` não
   está na lista de transições permitidas;
5. a exceção **aborta a transação inteira** — nem a verificação fica gravada.

Duas migrations discordavam sobre a máquina de estados, e a discordância só
aparecia no único caminho que importa. Todo item indeterminado ficava travado
sem saída que não fosse `UPDATE` à mão — exatamente o que o comentário da própria
função diz que não pode existir.

A prova `provar-ledger-v10-03.sh` não pegava porque o bloco J reconciliava um item
cujo lote ainda estava `executando`: o caso fácil, que nunca acontece depois de
uma indeterminação. Os blocos **J2** (reproduz o defeito com a v10_03 sozinha),
**J3** (aplica a v10_04 e prova a saída), **J4** (posse), **J5** (as guardas da
v10_01 sobreviveram) e **J6** (lote com irmão em aberto não conclui) fecham isso.

A v10_04 traz três coisas, e nada além delas:

- `interrompido->concluido` na máquina de estados — **uma** transição, não duas:
  `interrompido->concluido_com_falhas` foi cogitada e removida por não ter
  chamador nenhum;
- a verificação passa a apontar para o recibo do item mesmo quando ele já fechou,
  sem o qual a auditoria perde o fio entre "não respondeu" e "conferi e estava lá";
  um recibo já fechado **continua fechado** — ele diz o que era verdade na hora;
- a reconciliação confere que o item pertence à conta informada, e `achou=true`
  passa a **exigir** `p_customer_id` (antes a guarda se desligava sozinha quando o
  campo era omitido).

⚠️ **O que quase deu errado nela.** A primeira versão reescreveu
`trafego_lote_estado_valido` com `CREATE OR REPLACE` copiando só a lista de
transições e parando no `RETURN NEW` — apagando em silêncio a imutabilidade da
aprovação, a identidade do lote, a monotonicidade da leitura de quota e o carimbo
de `atualizado_em`. A verificação escrita junto não pegava, porque procurava a
substring da transição nova e a encontrava. Uma migration que acrescenta uma linha
e apaga quatro guardas não é incremental; é uma reescrita disfarçada. O arquivo
hoje carrega o corpo completo, a verificação exige as quatro guardas pelo texto, e
o bloco J5 prova cada uma contra o banco.

⚠️ **Os hashes mudaram em 26/08/2026**, depois da auditoria adversarial. Quinze
achados foram confirmados por céticos independentes e corrigidos; cinco deles são
de gravidade alta e três abriam caminho para a segunda campanha no mesmo leilão.
As migrations **não foram aplicadas em produção em nenhum momento**, então não há
divergência entre arquivo e banco — o hash antigo nunca existiu em lugar nenhum.

**Assunto:** 19 tabelas para `intenção → blueprint → lote → itens → validação →
`validate_only` → aprovação → criação PAUSADA → recibo → verificação → canário →
ativação → rollback`, e a autogestão em nível **T1** (a automação recomenda, o
humano aplica).

**Dependência:** a v10_01 precisa da v9_01 (referencia `trafego_campanha`). A
v10_02 precisa da v10_01. **As duas são independentes entre si no rollback:**
reverter a v10_02 deixa a v10_01 intacta, e reverter a v10_01 deixa a série v9
intacta — as duas coisas são provadas, não afirmadas.

### v10_03 — a fronteira atômica, e o furo que ela fecha (31/08/2026)

A v10_01 escreveu três camadas de defesa contra "timeout mas criou". **Todas as
três vivem dentro de `IF NEW.estado IS DISTINCT FROM OLD.estado`**, no gatilho
`trafego_item_estado_valido`: elas guardam `-> falhou` e `indeterminado ->
criando`. Abrir um recibo não passava por gatilho nenhum — e abrir o recibo é o
ato que precede a chamada à plataforma.

Reproduzido em cluster descartável, com v9_01..v9_04 + v10_01 + v10_02:

```text
item em `criando`, recibo tentativa=1 `em_voo` (a chamada 1 não respondeu)
INSERT trafego_recibo tentativa=2 'em_voo'  → ACEITO
recibos em voo simultâneos para o mesmo item: 2
```

Duas chamadas de criação em voo para o mesmo plano, na mesma conta. Como
`trafego_recibo_sucesso_unico_ux` só impede registrar **dois sucessos**, se as
duas criarem a segunda campanha existe na conta e fica **invisível** para o
sistema, disputando o mesmo leilão. O dano não é duplicar; é duplicar e perder
o rastro da duplicata.

A v10_03 traz:

1. **Camada 4** — gatilho `BEFORE INSERT` em `trafego_recibo`: não se abre
   recibo para item que já tem recibo sem desfecho na mesma operação. Vale mesmo
   quando nenhuma transição de estado acontece, que era exatamente o caso que
   passava.
2. **A aprovação com identidade e vínculo** — `plano_impressao`,
   `aprovado_por`, `aprovado_por_sub`, `aprovado_em` e `aprovacao_impressao` no
   item, com uma **constraint** (não uma convenção) exigindo
   `aprovacao_impressao = plano_impressao`: autorização não atravessa de payload
   para payload.
3. **Quatro funções transacionais** — `trafego_ledger_abrir_lancamento`,
   `_despachar`, `_fechar` e `_reconciliar`. `SECURITY INVOKER`, `EXECUTE` só
   para `service_role`, `search_path` fixado.

**Por que função, e não disciplina de chamador.** Sobre PostgREST cada
requisição HTTP é uma transação própria; "conferir se há recibo aberto" e "abrir
o recibo novo" ficam em transações diferentes, e a janela não está no chamador —
está *entre* as transações. `FOR UPDATE` dentro de uma função a fecha; nenhuma
disciplina de aplicação fecha.

**O que a v10_03 deliberadamente NÃO faz:** não substitui nenhuma função da
v10_01 (os gatilhos são novos — um rollback que precisa redigitar o corpo de uma
regra apaga tanto quanto a migration que ele desfaz, que é o defeito registrado
acima sobre a v9_03); e **não reabre reenvio depois de `sem_resposta`**. Um
recibo `sem_resposta` é permanente e a camada 3 conta esses recibos, então o item
não volta para `criando`. Isso é *fail-closed* e continua assim: **reconciliar é
o caminho, reenviar não é**. Afrouxar essa regra é decisão do dono.

**Reentrada legítima:** `erro` é resposta (a plataforma disse que não criou), o
item vira `falhou`, e `falhou -> criando` é permitido — a intenção não é
queimada por uma recusa. `sem_resposta` é ignorância, e dali só se sai
verificando na conta.

⚠️ **Convenção de nome.** Este diretório usa `vNN_MM_nome.sql` + `vNN_MM_rollback.sql`,
não o `<timestamp>_nome.sql` da CLI do Supabase — e não há `supabase/config.toml`
aqui. A v10_03 segue a convenção do repositório, não a da CLI; mudar de convenção
no meio de uma série quebraria a ordem topológica documentada acima.

### A prova, e como reproduzi-la

```bash
./scripts/provar-ciclo-v10.sh        # v10_01 + v10_02: aplicar → reverter → reaplicar
./scripts/provar-ledger-v10-03.sh    # a fronteira atômica: 52 provas
```

Ele sobe um cluster efêmero em `/tmp`, recria os papéis do Supabase **incluindo o
`ALTER DEFAULT PRIVILEGES` quebrado de `public`** — sem reproduzir o defeito, a
prova mediria um ambiente mais seguro que o real — e roda **aplicar → reverter →
reaplicar** com 100 verificações. Em cada degrau, seis eixos de segurança:
`anon`/`authenticated` sem nenhum dos 4 privilégios · RLS ligada **e forçada** em
toda tabela · **zero policies** (a negação é por ausência, não por regra que
alguém possa afrouxar) · `DELETE` não concedido a ninguém · `security_invoker` em
toda view · `service_role` só com `SELECT` nas views.

⚠️ **Rode-o antes de pedir autorização.** O rollback da v9_03 estava documentado
como "reaplique a v9_02" e **abortava** com `cannot drop columns from view` — e
isso só apareceu quando alguém tentou. Rollback documentado e nunca executado é
rollback que ninguém tem.

### As guardas que o banco impõe, e por que elas moram lá

Não são validações de conveniência: cada uma recusa uma transação, e existem
porque a alternativa era confiar em revisão de código.

| a guarda recusa | por quê |
|---|---|
| item declarado `falhou` com recibo **em voo** | `falhou` convida à retomada, e retomar é como nasce a segunda campanha |
| segundo `sucesso` para a mesma `(idempotency_key, operação)` | se um executor com defeito criar duas vezes, o lote **para** em vez de o sistema ser dono de duas campanhas sem saber |
| proposta sobre evidência **insuficiente** | uma recomendação sem amostra tem a mesma voz de uma com amostra |
| proposta cujo "antes" foi lido faz tempo | o diff aprovado precisa descrever o estado que ainda vale |
| proposta acima do teto declarado | o teto é da intenção, e a proposta não o renegocia |
| regra em nível **T2** | ADR-11 e ADR-26 pressupõem T1. A recusa é do banco, não da revisão |
| proposta apontando para **campanha diferente** da que a evidência mediu | uma medição só autoriza mudança no que ela mediu — e o painel mostra a explicação do diagnóstico ao lado do alvo da proposta |
| proposta citando **regra diferente** da regra do diagnóstico | os limites são da regra; escolher a regra depois do diagnóstico é escolher o próprio teto |
| proposta **sem delta** contra regra que declara limite de alteração | teto furado por omissão é pior que teto ausente: o registro afirma que ele foi conferido |
| `indeterminado → criando` **sem verificação que concluiu** que a campanha não existe | reenviar sem essa prova é apostar, e a aposta errada cria a segunda campanha |
| item declarado `falhou` com recibo em voo **ou `sem_resposta`** | `sem_resposta` não é um desfecho conhecido: é a ignorância carimbada |
| lote declarando **conta diferente** da intenção, ou **canal diferente** do blueprint | o teto de gasto mora na intenção; um lote que aponta para outra conta gasta sob autorização que não é dele |
| acompanhamento com **métrica e sem a janela** que ela mede | número sem o período que ele mede não é medida, é um número |

**`T2` não existe no vocabulário do schema.** A ausência *é* o registro da
decisão — um `CHECK` que aceitasse T2 e um código que nunca o usasse seria a
abstração sem consumidor que o ADR-19 proíbe.

### O que a série v10 NÃO faz

- **Não escreve no Google Ads.** Ela guarda intenção, plano, recibo e verificação;
  quem fala com a API é o engine, atrás da trava de dois fatores.
- **Não publica nenhuma regra de otimização.** As 19 herdadas do n8n entram em
  `estado: proposta`, e **zero são publicáveis** — faltam campos que o legado
  nunca declarou. O mais revelador: **nenhuma regra do n8n declarava idade máxima
  do dado**.
- **Não resolve a autoridade paralela.** Enquanto existir caminho de escrita fora
  do VOLC O.S., a `idempotency_key` protege contra *este* sistema criar duas
  vezes — não contra dois sistemas criarem uma vez cada.

## O que a v9_01 cria, e o que ela deliberadamente não faz

Seis tabelas em `public`, todas com prefixo `trafego_`: `trafego_linhagem`,
`trafego_campanha`, `trafego_campanha_espelho`, `trafego_snapshot_conta`,
`trafego_vinculo`, `trafego_evento`. Mais seis funções de gatilho e **duas views
de leitura** (seção 12): `trafego_inventario_campanha` e
`trafego_inventario_conta`.

### As views, e por que elas existem

A listagem do Hub precisa de identidade, espelho, vínculo ativo e frescor da
conta na MESMA linha — quatro tabelas. Montado no cliente isso vira uma consulta
por campanha, e o pior do N+1 não é a lentidão: é que ele **some do plano de
consulta**. Um `EXPLAIN` na consulta principal mostra um plano barato e honesto,
e as outras cinquenta requisições não aparecem em lugar nenhum.

As duas são `security_invoker = true`. Sem isso uma view roda com os privilégios
do **dono** e vira um túnel: quem tivesse `SELECT` nela leria as seis tabelas por
cima de toda a RLS. É por causa disso que a guarda da migration exige
**PostgreSQL 15** (`security_invoker` não existe antes); produção medida é 15.8.

A única coisa calculada nas views é o booleano `atencao`, e ele é a tradução
literal de `backend/app/trafego/dominio.py:pede_atencao()`. **Duas definições de
`atencao` seriam o defeito, não a solução** — o sino conta no banco (senão
contaria só a página corrente) e a aba decide em Python; se discordarem, os dois
mostram números diferentes para a mesma pergunta e não há como saber qual está
certo. `test_trafego_persistencia.py` compara as duas linha a linha contra um
banco real.

### Três decisões de modelagem que valem a leitura

| Decisão | Por quê |
|---|---|
| `volc_campaign_id` é `text` **sem DEFAULT** | A identidade é DERIVADA do par (conta, campanha) pelo domínio, para a varredura ser idempotente sem uma ida ao banco por campanha. Um `uuid` sorteado exigiria essa ida; um `uuid` v5 colocaria a regra de derivação em dois lugares. Sem DEFAULT, o banco nunca sorteia endereço de campanha |
| `tentativa_resultado` aceita `parcial` | Se `parcial` tivesse de virar `ok`, `frescor_da_conta()` responderia `recente` para uma conta que não entregou metade do que foi pedido — frescor desconhecido degradando para o melhor caso possível |
| `moeda` saiu do grupo da entrega | Moeda é **unidade**, não medida: ela denomina `lance_micros` e `verba_diaria_micros`, que têm o carimbo da camada comum. Dentro do grupo, a CHECK obrigava a apagá-la sempre que a entrega falhava, e a verba aparecia na tela sem dizer em que moeda |

### O gatilho do espelho preserva RÓTULO, nunca NÚMERO

A pergunta que decide cada coluna é uma só: **o nulo aqui pode ser um fato
medido?** Se pode, preservar inventa — a tela mostraria como atual um valor que a
conta já não tem. Se não pode (a API sempre responde algo), o nulo só significa
"esta varredura não mediu isto", e aceitá-lo apaga dado bom.

| Coluna | Preservada? | Por quê |
|---|---|---|
| `nome`, `estado_externo`, `veiculacao`, `canal`, `canal_bruto` | **sim** | a API nunca responde campanha sem nome nem sem status; o canal ainda é imutável na campanha. Sem isso, uma leitura parcial deixava a linha **sem nome na tela** |
| `moeda` | **sim** | a conta sempre tem moeda; é unidade, não medida |
| `impressoes`, `cliques`, `custo_micros` | **sim, com o carimbo junto** | preservar número sem preservar `entrega_lida_em` seria pior que apagar: dado velho passando por novo |
| `presenca` | **não** | o NULO **é** o fato "presente, sem ressalva". Preservar deixaria `removida` colada para sempre numa campanha reativada |
| `estrategia`, `estrategia_bruta` | **não** | a estratégia MUDA na vida da campanha e `estrategia_canonica()` devolve NULL para valor fora do vocabulário — o nulo PODE ser medição. Preservada, mostraria `MANUAL_CPC` numa campanha já em `TARGET_ROAS`, e `teto_de_cliques()` calcularia um teto que não existe |
| `lance_micros`, `verba_diaria_micros`, `url_final` | **não** | ausência legítima (lance automático não tem lance manual), e são NÚMERO: o carimbo deles é `lido_em`, que acabou de avançar |

**Ela não escreve uma única linha de dado.** Não faz backfill de `campaigns`,
não importa as quatro linhas medidas em 24/08, não altera nenhuma tabela
existente e não cria FK para nenhuma delas. ADR-10 é explícito: a investigação
precede o backfill, porque backfillar antes de entender o mecanismo pode ser
sobrescrito por ele.

**Por que tabelas novas em vez de colunas em `campaigns`.** O gatilho
`sync_status_from_google_ads` é `BEFORE INSERT/UPDATE` em `campaigns` e executa
`NEW.status_source = 'auto'` sempre que `google_ads_status` não é nulo — e a
porta de criação sempre envia esse campo ([E-08](../../docs/EVIDENCIAS-TRAFEGO.md#e-08)).
Declarar procedência ali seria escrever num campo que um gatilho reescreve no
mesmo comando.

## Preflight — rode ANTES de autorizar a aplicação

Somente leitura: `to_regclass`, `SELECT` em catálogo e uma contagem em
`campaigns`. Não há `CREATE`, `ALTER`, `GRANT` nem escrita de qualquer espécie,
então pode ser colado direto no banco de produção.

```sql
-- ============================================================================
-- PREFLIGHT v9_01 — somente leitura. Nada aqui escreve.
-- ============================================================================
WITH deve_existir AS (
  SELECT 'papel anon'                AS item,
         (SELECT count(*) = 1 FROM pg_roles WHERE rolname = 'anon')::text          AS valor,
         'true'   AS esperado, 'ABORTA' AS se_divergir
  UNION ALL SELECT 'papel authenticated',
         (SELECT count(*) = 1 FROM pg_roles WHERE rolname = 'authenticated')::text,
         'true',   'ABORTA'
  UNION ALL SELECT 'papel service_role',
         (SELECT count(*) = 1 FROM pg_roles WHERE rolname = 'service_role')::text,
         'true',   'ABORTA'
  UNION ALL SELECT 'PostgreSQL >= 15 (security_invoker em VIEW)',
         (current_setting('server_version_num')::int >= 150000)::text,
         'true',   'ABORTA'
  UNION ALL SELECT 'papel de aplicacao correto',
         (current_user IN ('postgres','supabase_admin'))::text,
         'true',   'ABORTA'
  UNION ALL SELECT 'CREATE no schema public',
         has_schema_privilege(current_user, 'public', 'CREATE')::text,
         'true',   'ABORTA'
),
nao_deve_existir AS (
  SELECT 'tabela ' || t AS item,
         coalesce(to_regclass('public.' || t)::text, '(ausente)') AS valor,
         '(ausente)' AS esperado, 'ABORTA' AS se_divergir
    FROM unnest(ARRAY['trafego_linhagem','trafego_campanha','trafego_campanha_espelho',
                      'trafego_snapshot_conta','trafego_vinculo','trafego_evento',
                      'trafego_inventario_campanha','trafego_inventario_conta']) AS t
  UNION ALL
  SELECT 'funcoes trafego_* preexistentes',
         (SELECT count(*)::text FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
           WHERE n.nspname = 'public' AND p.proname LIKE 'trafego\_%'),
         '0', 'ABORTA'
),
contexto AS (
  -- Nao aborta nada. Existe para o dono ver o terreno antes de autorizar.
  SELECT 'default ACL de public concede a anon (achado H)' AS item,
         (SELECT count(*)::text FROM pg_default_acl
           WHERE defaclnamespace = 'public'::regnamespace
             AND array_to_string(defaclacl, ',') LIKE '%anon=%') AS valor,
         '2 (e por isso a migration REVOGA nominalmente)' AS esperado,
         'informativo' AS se_divergir
  UNION ALL SELECT 'gatilho legado sync_status_from_google_ads ainda ativo',
         (SELECT count(*)::text FROM pg_trigger
           WHERE NOT tgisinternal AND tgrelid = 'public.campaigns'::regclass
             AND tgname LIKE '%sync_status%'),
         '1 (motivo de o dominio novo ser separado)', 'informativo'
  UNION ALL SELECT 'linhas em campaigns com customer_id vazio',
         (SELECT count(*)::text FROM public.campaigns WHERE coalesce(customer_id,'') = ''),
         '4 em 24/08 — a v9_01 NAO as importa', 'informativo'
  UNION ALL SELECT 'tabelas e views trafego_* existentes hoje',
         (SELECT count(*)::text FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname='public' AND c.relkind IN ('r','v') AND c.relname LIKE 'trafego\_%'),
         '0', 'informativo'
)
SELECT * FROM deve_existir
UNION ALL SELECT * FROM nao_deve_existir
UNION ALL SELECT * FROM contexto;
```

### Como ler o resultado

| linha | valor esperado | o que fazer se divergir |
|---|---|---|
| `papel anon` / `authenticated` / `service_role` | `true` | **não aplique.** A migration aborta de propósito: sem os três papéis, o `REVOKE` nominal não acontece e as tabelas nascem abertas ao navegador |
| `PostgreSQL >= 15` | `true` | **não aplique.** `security_invoker` em VIEW só existe a partir do 15, e sem ele as duas views da seção 12 leriam as seis tabelas com os privilégios do dono. Produção medida: 15.8 |
| `papel de aplicacao correto` | `true` | reconecte como `postgres` (ou `supabase_admin`) |
| `CREATE no schema public` | `true` | o papel não pode criar tabela; troque de papel |
| `tabela trafego_*` (oito linhas: seis tabelas + duas views) | `(ausente)` | **não aplique.** Alguma parte já foi aplicada; rode a `v9_99` antes |
| `funcoes trafego_* preexistentes` | `0` | idem |
| `default ACL … (achado H)` | `2` | informativo. Se vier `0`, a `v8_07` já foi aplicada e os `REVOKE` da v9_01 viram redundância inofensiva |
| `gatilho legado … ativo` | `1` | informativo. Se vier `0`, alguém removeu o gatilho de `campaigns` — o motivo da separação mudou e vale reabrir ADR-10 |
| `linhas em campaigns com customer_id vazio` | `4` | informativo. **A v9_01 não as importa**; quem as reconcilia é a fase seguinte |

**Regra:** qualquer linha marcada `ABORTA` fora do esperado significa **não
autorizar**. A migration tem as mesmas guardas e falharia sozinha, mas descobrir
isso pelo preflight custa um `SELECT`, e descobrir pela migration custa uma
transação abortada em produção.

### Depois de aplicar

```sql
-- 1. As seis tabelas, com RLS ligada E forcada, e sem ACL para anon.
SELECT c.relname,
       c.relrowsecurity      AS rls,
       c.relforcerowsecurity AS forcada,
       coalesce(array_to_string(c.relacl, ' | '), '(sem acl)') AS acl
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname LIKE 'trafego\_%'
 ORDER BY 1;
-- esperado: 6 linhas, rls=t, forcada=t, e NENHUM 'anon=' na coluna acl

-- 1b. As duas views: RLS nao se liga em view, entao a conferencia e outra —
--     `security_invoker` ligado, e SELECT so para service_role.
SELECT c.relname,
       array_to_string(c.reloptions, ',')                      AS opcoes,
       coalesce(array_to_string(c.relacl, ' | '), '(sem acl)') AS acl
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind = 'v' AND c.relname LIKE 'trafego\_%'
 ORDER BY 1;
-- esperado: 2 linhas, opcoes com security_invoker=true, acl so com service_role=r

-- 2. Zero policies — a negacao aqui e por AUSENCIA de policy, nao por policy.
SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename LIKE 'trafego\_%';
-- esperado: 0

-- 3. Nenhum DELETE concedido a ninguem alem do dono.
SELECT grantee, table_name, privilege_type
  FROM information_schema.role_table_grants
 WHERE table_schema='public' AND table_name LIKE 'trafego\_%'
   AND privilege_type IN ('DELETE','TRUNCATE');
-- esperado: 0 linhas (ou so o dono)

-- 4. O PostgREST precisa reler o schema para o backend enxergar as tabelas.
NOTIFY pgrst, 'reload schema';
```

### O que este conjunto NÃO protege

`service_role` tem `rolbypassrls = t` (achado **I** da medição de 24/08). RLS
não contém os endpoints que carregam a service key sem autenticação —
`api/supabase/{query,insert,update,rpc}.js` e `server/index.js:165-403` aceitam
nome de tabela arbitrário do request. Enquanto a **Frente 1/3** não fechar isso,
as seis tabelas novas estão tão expostas por esse caminho quanto as outras 64 de
`public`.

O que esta migration reduz nesse caminho: **nenhuma delas concede `DELETE` a
papel nenhum**, e `trafego_evento` não concede nem `UPDATE`. Um endpoint aberto
de escrita genérica não consegue destruir o inventário nem a trilha de auditoria
— só acrescentar linhas, que o gatilho de append-only preserva.

A proteção forte de verdade seria um schema privado fora de `PGRST_DB_SCHEMAS`,
como a `v8_01` fez com `app_auth`. Ela não foi adotada aqui porque o backend
fala com o Supabase por **PostgREST** (`backend/app/services/supabase_service.py:54`),
e um schema fora daquela lista fica inalcançável também para ele. Trocar para
schema privado exige mexer em `/root/supabase/docker/.env` e reiniciar o Kong —
decisão do dono, registrada aqui e não tomada por conta própria.

## Série v11 — Estúdio Criativo

**APLICADA EM PRODUÇÃO em 2026-08-2814:01:40-03**, com autorização explícita do dono, contra
`database.agenciavolc.com.br` (banco `postgres`), como `postgres`.

Backup tomado ANTES, no servidor, e conferido (1.847 entradas no índice do dump):

    /root/backups/pre-v11-completo-20260828-164831.dump   (2,0 MB, pg_dump -Fc)
    /root/backups/pre-v11-schema-20260828-164831.sql      (720 KB, --schema-only)

| Arquivo | Estado | sha256 | Dependência | Rollback |
|---|---|---|---|---|
| `v11_01_estudio_criativo.sql` | **APLICADA** | `62e0789a4ff6136b…` | nenhuma | `v11_01_rollback.sql` |
| `v11_02_parque_criativo.sql` | **APLICADA** | `22ab35f47016c56a…` | v11_01 | `v11_02_rollback.sql` |
| `v11_01_rollback.sql` | não executada em produção | `6565d0882de13631…` | v11_01 aplicada | — |
| `v11_02_rollback.sql` | não executada em produção | `69cc5cc071272892…` | v11_02 aplicada | — |

Os dois rollbacks são **transacionais** (`begin`/`commit`) e são **rodados** a
cada execução de `scripts/provar-ciclo-v11.sh`, no ciclo aplicar → provar →
reverter → reaplicar. A razão é um defeito medido nesta própria série: o rollback
da v11_01 nasceu sem transação e, com uma FK externa apontando para
`criativo_master`, ele apagava as aprovações humanas ANTES de "abortar em
segurança". Um rollback documentado e nunca rodado só é descoberto no pior momento.

### O que a v11 põe no banco

**v11_01 — o ciclo.** Dez tabelas: `criativo_brand_pack`, `criativo_projeto`,
`criativo_briefing`, `criativo_job`, `criativo_job_evento`, `criativo_master`,
`criativo_rendition`, `criativo_aprovacao`, `criativo_pacote`, `criativo_entrega`.
Idempotência em três camadas, falha parcial por peça, versão imutável de master,
evento append-only.

**v11_02 — o parque.** Onze tabelas de domínio, que transformam em dado o que
antes vivia em quatro cópias sem árbitro (manifesto, YAML, Python, TypeScript):
`criativo_motor`, `criativo_modo_de_producao`, `criativo_formato`,
`criativo_finalidade`, `criativo_exigencia_de_canal`, `criativo_teto_combinado`,
`criativo_skin`, `criativo_voz`, `criativo_gate`, `criativo_master_gate`,
`criativo_master_direito`.

Semeado na aplicação: 3 motores, 7 modos, 7 formatos, 9 finalidades, 15 skins,
14 vozes, 28 gates e 18 exigências de canal, cada linha com a `fonte` de onde o
valor saiu.

`criativo_motor.cofre_asset_id` costura com o Cofre de Ativos
(`asset:engine:image-volc`, `asset:engine:video-volc`). É `text` e não FK porque
o Cofre ainda não tem tabela; o id declarado hoje faz o join existir no dia em
que ele persistir, e impede que alguém invente uma segunda identidade de motor.

### Verificação pós-aplicação, medida em produção

    21 tabelas criativo_*        RLS ligada E forçada em todas
    0 policies                   0 privilégios para anon/authenticated
    service_role: SELECT, INSERT, UPDATE   (sem DELETE, sem TRUNCATE)
    6 gatilhos                   anon barrado no PostgREST com 401

Seis guardas foram exercitadas contra o banco real, dentro de uma transação
revertida: chave de idempotência duplicada, `storage_chave` fora do prefixo,
medida zero, rendition pronta sem arquivo, job observado declarando custo próprio
e motor com id de Cofre malformado. As seis recusaram; produção ficou com
0 jobs e 0 projetos.

⚠️ **O bucket de storage NÃO foi criado.** `select count(*) from storage.buckets`
continua `0`. Os arquivos seguem no armazenamento local do backend até essa
decisão ser tomada em separado.


---

## Série v11_03 — execução criativa

**Estado: ESCRITA E PROVADA. NÃO APLICADA EM PRODUÇÃO.**

| Arquivo | Estado | Ambiente onde rodou |
|---|---|---|
| `v11_03_execucao_criativa.sql` | **não aplicada** | cluster descartável, ciclo completo |
| `v11_03_rollback.sql` | **não executada em produção** | idem, executada a cada rodada |
| `scripts/provas-v11_03.sql` | — | 42 provas de comportamento |
| `scripts/provar-ciclo-v11_03.sh` | — | **53 provas, 0 falhas** |

### O que ela persiste

Cinco tabelas: `criativo_render_job`, `criativo_render_transicao` (append-only),
`criativo_render_recibo`, `criativo_render_artefato`, `criativo_render_validacao`.

Ela **não inventa campo**: cada coluna corresponde a um comportamento que as 79
provas da bancada local já exerciam, com 95,2% de mutation score. O SQLite da
bancada continua sendo a fila **local** do worker; isto é a autoridade do domínio.

### Rodar o ciclo

```bash
./scripts/provar-ciclo-v11_03.sh
```

Sobe um Postgres do zero, aplica v11_01 + v11_02 + v11_03, roda as provas de
comportamento, reverte, confere que as 21 tabelas anteriores continuam de pé, e
reaplica. Não toca em nada fora de `/tmp` e nunca fala com produção.

⚠️ **`LC_ALL=C` é obrigatório** e está no script. Sem ela, o Postgres 16 do
Homebrew no macOS morre no arranque com *"postmaster became multithreaded during
startup"* — a dica está no próprio log, e sem isso o script não sobe cluster nenhum.

### Dois defeitos que o ciclo pegou, e que a leitura não pegaria

1. **O gatilho de transição retornava cedo quando o estado não mudava.** Um
   `update ... set owner='outro'` sem mudar estado passava sem nenhuma guarda —
   roubo de trabalho no meio da execução. A conferência de dono agora vem **antes**
   do atalho.
2. **As provas de comportamento nasceram em bash**, dentro de `eval` com aspas em
   três níveis. A primeira inserção falhava por quoting e **todas** as seguintes
   cascateavam, produzindo um relatório cheio de "ok" que não media nada. Foram
   reescritas em SQL puro.

### As sete invariantes

1. **Lease não é renovado por transição** — renovar é trabalho do batimento, que
   confere dono. A versão local disto ressuscitava lease vencido ao passar de
   `claimed` para `running`.
2. **Só o dono bate o coração.**
3. **`rendered` exige recibo e é terminal.**
4. **`failed` só volta por gesto explícito e auditável** — nasce job novo com
   `retry_of` e `retry_n`, e a trilha `criativo_render_transicao` registra.
5. **Artefato é imutável depois de `rendered`**; `bytes` e `sha256` são NOT NULL,
   com forma conferida.
6. **Tenant entra na identidade** — a chave única é `(tenant_id, idempotency_key)`.
7. **Mensagem de erro não persiste caminho, stack nem drive** — há CHECK, porque
   documentação não impede ninguém de gravar `/var/folders/...` num campo de texto.

### Segurança

RLS **habilitada e forçada** nas 5, zero policies, `REVOKE` de `public`, `anon`,
`authenticated` **e `service_role`** antes do `GRANT` mínimo — o ACL padrão
quebrado de `public` concede `arwdDxt` a todos em toda tabela nova, e isso é real
e está ativo em produção. `service_role` fica com `SELECT/INSERT/UPDATE`; sem
`DELETE`, porque apagar job é apagar auditoria. A trilha não é atualizável nem
por ele.

### Antes de aplicar em produção

1. Backup conferido, como na v11_01/v11_02.
2. Decidir se `tenant_id` é o `sub` do usuário (como a bancada faz hoje) ou uma
   conta — a chave de idempotência carrega o valor, então mudar depois separa
   trabalhos antigos dos novos.
3. Os 13 índices de FK pendentes das v11_01/v11_02 continuam pendentes.

---

## Série v12_01 — inteligência oficial Google Ads

**Estado: APLICADA NO SUPABASE OFICIAL EM 29/08/2026.**

| Arquivo | Estado | SHA-256 |
|---|---|---|
| `v12_01_google_inteligencia_coletas.sql` | **aplicada** em `database.agenciavolc.com.br` | `0cbd3f2c23dddb33f8e7be88b2189ab556eff89a8859e3aaedc813014bc42161` |
| `v12_01_rollback.sql` | não executada em produção | `66089b477ffc21441fa2b9165526f1e93a435886bab2c0b0b4d293518882eb92` |

### Preflight e evidência

- executor: `postgres`; banco `postgres`; PostgreSQL 15.8;
- backup: `/root/backups/pre-v12-google-inteligencia-20260829.dump`, modo 600;
- `pg_restore --list` conferiu **2.029 objetos**;
- migration provada antes em banco temporário e aplicada depois no banco oficial;
- três tabelas com RLS habilitada e forçada;
- `anon` e `authenticated` sem privilégios;
- `service_role` com `SELECT` e execução da RPC, sem `INSERT`, `UPDATE` ou `DELETE` direto;
- RPC `volc_registrar_google_inteligencia(jsonb)` é `SECURITY DEFINER`, com `search_path` fixo, e grava recibo, itens e métricas atomicamente.

### Contrato semântico

Uma chamada válida sem itens é `vazio_confirmado` com quantidade zero. Uma falha
é `falhou` com quantidade nula e erro sanitizado. Métrica medida pode valer zero;
ausência, não aplicabilidade e falha não carregam valor. Gatilhos tornam recibos,
itens e métricas append-only.

### Postflight funcional

O coletor v3 executou o modo completo na conta Crédito Up e persistiu 10 recibos
reais sem falhas: diagnóstico de 12/83 itens, forecast de 4/3 cenários e
recomendações/simulações vazias confirmadas para Maquininha/FGTS. A versão 1 teve
três falhas de integração e elas continuam preservadas como falha, não como vazio.
A versão 3 também impede que o recibo de uma falha esconda um retry posterior
bem-sucedido no mesmo intervalo.

O agendamento systemd está versionado em `deploy/google-intelligence/`, mas ainda
não foi instalado: a cópia da credencial OAuth e a ativação persistente no servidor
exigem autorização explícita do dono.

---

## Série v12_04 — fato canônico Google Ads campanha-dia

**Estado: ESCRITA E PROVADA EM DESCARTÁVEL — NÃO APLICADA.**

| Arquivo | Estado | SHA-256 |
|---|---|---|
| `v12_04_gads_fato_canonico_dia.sql` | **não aplicada** em produção | `f19ed662c596f863806a05047b67808fe2b10660f2ed286866ec88816ccda713` |
| `v12_04_rollback.sql` | executado só no descartável | `583a2f7189db739feeed944cb3bd51e4a333a878cadbaa366ec9511cb95cbee3` |
| `../../scripts/provas-v12_04.sql` | 65 provas de comportamento | `ab2a12ef7d3649166bd019eb01e2c707d3120a6b35ca8c5da5a8d85d2a7ccf83` |
| `../../scripts/provar-ciclo-v12_04.sh` | ciclo completo | `e1f27d04471a94bcad5f7a06f15930b662fc29e0dcbb61511ea79a8816f89689` |

### Por que v12_04 e não v13_01

O prompt M-W2-02 (`docs/closure/fable-global-v1/prompts/m-w2-02-migration-d0-d1.md`)
reserva `v13_01_gads_fato_canonico.sql` a uma sessão interativa em branch própria,
e a v12_03 está reservada à ampliação de `tipo_sinal` do PMax. A entrega P10-T16
não podia tocar nenhuma das duas, e o objeto é o mesmo que aquele prompt descreve.

A escolha não fica no ar: o preflight da v12_04 **aborta com mensagem nomeada** se
`trafego_coleta_execucao` ou `google_ads_campanha_dia` já existirem. Se as duas
lanes existirem, o integrador escolhe UMA — aplicar as duas por engano é
mecanicamente impossível.

### O que ela cria

- `trafego_coleta_execucao` — ledger append-only, uma linha por lote; o
  fechamento (ordinal 0) reconcilia contra o que o banco persistiu;
- `google_ads_campanha_dia` — fato com chave
  `(customer_id, campaign_id, metric_date, segments_hash)`, **nenhuma métrica com
  DEFAULT**, dinheiro em micros com moeda, precedência `D0 < D-1 < backfill`;
- `volc_registrar_gads_campanha_dia(jsonb)` — a única porta de ingestão,
  `SECURITY DEFINER` com `search_path` fixo;
- `volc_gads_projetar_daily_compat(uuid)` — projeção de compatibilidade,
  fault-isolated, restrita a 16 colunas de entrega de `daily_campaign_metrics`;
- `volc_gads_uuid_da_chave(text)` — identidade derivada, não sorteada;
- `trafego_coleta_execucao_saude` — view read-only para o deadman.

RLS **habilitada e forçada** nas duas tabelas, zero policies, `REVOKE` de
`public`, `anon`, `authenticated` **e `service_role`** antes do `GRANT` mínimo.
`service_role` fica com `SELECT` e `EXECUTE` da RPC; sem escrita direta.

### Prova

```bash
bash scripts/provar-ciclo-v12_04.sh
# passaram 107 · falharam 0
# CICLO v12_04 COMPLETO: aplicar → operar → reverter → reaplicar

bash scripts/provar-ponta-a-ponta-gads.sh
# passaram 12 · falharam 0
# PONTA A PONTA COMPLETA — documentos do n8n aceitos pela RPC v12_04
```

⚠️ Estes scripts usam **docker** (`postgres:16-alpine`), e não `initdb`/`pg_ctl`
como as séries v10/v11/v12_02: a máquina desta lane não tem binários Postgres
locais. O contrato da prova é o mesmo — cluster efêmero, papéis de produção
reproduzidos (inclusive o ACL padrão quebrado e o `BYPASSRLS` do `service_role`),
ciclo completo, e nunca uma linha enviada a `database.agenciavolc.com.br`.

### O que a v12_04 deliberadamente não faz

Não altera `daily_campaign_metrics` — nem coluna, nem constraint, nem trigger. A
projeção **escreve** em 16 colunas de entrega dessa tabela e nunca encosta em
receita, `revenue_converted`, revshare, GAM, comissão, orientação ou otimização;
quando o fato canônico é NULL, ela grava NULL — nunca zero. E ela **não cria
linha nova** na legada: criar exigiria decidir receita e projeto sem dado.

### O portão que falta

Aplicação depende de autorização de banco e da sequência de
`docs/closure/hermes-p10-t16-n8n-ledger-v12-v1/AUTORIZACAO-ATIVACAO.md` —
conferência da agenda viva, backup conferido, canário D-1 e D0 reconciliados,
repetição idempotente e projeção conferida antes de qualquer agenda.

⚠️ O rollback **recusa perda silenciosa**: com dado gravado, ele aborta dizendo
quantos fatos e recibos morreriam. Para seguir é preciso declarar na sessão
`SET volc.rollback_v12_04_apagar_fatos = 'sim';`. E ele **não desfaz** o que a
projeção escreveu na legada — o valor anterior não foi guardado, e inventar um
seria pior do que declarar a lacuna.
