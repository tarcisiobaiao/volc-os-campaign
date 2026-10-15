# Incidente da chave anon — pacote de aplicação (W4, 15/10/2026)

**Estado: `ready_for_human`. Nada foi aplicado em produção.** Decisão e janela
são do Tarcísio. Ensaio: schema de produção de 15/10 restaurado num Postgres
descartável (`supabase/postgres:15.8.1.085`, sem rede) via `tools/freedom-lab/lab.sh`,
**79/79 verificações verdes** (recibo no handoff W4).

## O problema, medido em produção (sonda read-only de 15/10 ~10:55Z)

- A chave anon vai no bundle do browser. Com ela, sem login: **SELECT, INSERT,
  UPDATE, DELETE e TRUNCATE em 62 relações de `public`, 39 sem RLS**. SELECT real
  devolve linha em 23, inclusive `users` (com `password_hash` e tokens),
  `projects`, `campaigns`, `system_settings`, `raw_events`, `tax_history`.
- O default ACL de `public` faz toda tabela, sequência e função nova nascer
  aberta a anon, para os dois donos (`postgres` e `supabase_admin`).
- A correção v8_03–v8_06 (de 24/08) cobre só `users` e nunca foi aplicada.

## O que o pacote faz

| # | Arquivo | Papel | sha256 | Efeito |
|---|---|---|---|---|
| 1 | `v19_00_users_gatilho_papel_real.sql` | supabase_admin | `115b5aee43010fa5e6bcd5ea458fc0725d5a299774e86c72a0cea3635f4d0a67` | corrige o gatilho de `users`: hoje ele **nunca barra** autopromoção (SECURITY DEFINER faz `current_user` ser sempre `supabase_admin`) |
| 2 | `v8_03_users_rls_policies.sql` | supabase_admin | `e7af8372de3b25ee9811c2f0302052d7546f492e4261be72b2aded3bdc6b84ec` | RLS em `users`: cada um vê a própria linha, ADMIN vê todas; gatilhos ligados |
| 3 | `v19_01_anon_fecha_public.sql` | supabase_admin | `55790e5efa52ae7781c8ac05b5798ea482e6a353a1db1d40129eefa60852b7c4` | **anon perde tudo em `public`**; authenticated perde TRUNCATE/REFERENCES/TRIGGER; `users` só escreve colunas de perfil; fotografa a ACL anterior para o rollback |
| 4 | `v8_05_users_safe_view.sql` | postgres | `7fb3d2de616404bc3c68f8aee8e2f70b9525bad102f2a17c885b4c54a5434f68` | view `users_safe` sem colunas sensíveis |
| 5 | `v19_02_default_acl_public_sem_anon.sql` | supabase_admin | `3f2f16fef7c7245f0b8d444c5fed7c8d5629f1dc6ad88d47dde2bfae049d46bb` | objeto novo em `public` nasce sem anon (substitui a v8_07) |
| — | `v8_06_users_sensitive_columns_revoke.sql` | supabase_admin | `0010e0874cfe518218eb483223fa5d42b00e40f3138f203b5ca0423efa381554` | **passo 2**: browser deixa de ler `password_hash`/`token_*` — só depois do frontend novo no ar |
| ↩ | `v19_99_rollback.sql` | supabase_admin | `21eb455080b946fc5016f71eacbf59aecafbddfdb35eeedf7f87b6cbb6e3e48f` | desfaz 1–5 e a v8_06; devolve o fingerprint exato anterior |

**Não aplicar** `v8_02` nem `v8_04`: a v19_01 cobre o que a v8_04 fazia, e a
guarda da v8_04 exige a v8_02, que muda a autoridade de ADMIN do Pautador sem
necessidade para este incidente.

## Comando exato (só com autorização nominal)

```bash
scripts/aplicar-incidente-anon-w4.sh --so-checar
```
Preflight read-only: confere sha256, papel superusuário, `auth.uid()` lendo
`request.jwt.claims`, estado anterior, ADMINs sem papel em `app_auth`, e-mails
duplicados, superfície de anon (esperado 62).

```bash
scripts/aplicar-incidente-anon-w4.sh --passo1
```
Pede `APLICAR`, faz `pg_dump -Fc -n public -n app_auth` em `/root/backups/`,
sonda antes, aplica 1→5 (cada arquivo na própria transação, `ON_ERROR_STOP`),
`NOTIFY pgrst`, sonda depois. Esperado: `anon VE_LINHAS=0`.

```bash
scripts/aplicar-incidente-anon-w4.sh --passo2
```
Só depois que o frontend com `src/hooks/useUserProfile.ts` corrigido estiver em produção.

## Antes da janela (o que o ensaio não alcança)

1. **Credencial "VOLC Oficial" do n8n** (joinads, gads, meta): confirmar que é a
   `service_role`. Se for a anon, essas gravações param no passo 1.
2. **Algum site/landing externo usa a anon key?** No repositório não há
   (`public/`, `api/`, `server/`, edge functions, n8n: nenhum). Conferir nos logs
   do Kong/PostgREST se há tráfego com a anon key fora do app.
3. **ADMINs em `app_auth`**: o preflight P4 conta ADMIN de `public.users` sem
   papel ativo. Quem estiver nessa conta passa a ver só a própria linha na tela
   de usuários. Corrigir antes: `SELECT public.volc_grant_role('<auth.users.id>','ADMIN','pre-W4');`
4. **Cadastro público no GoTrue**: com `DISABLE_SIGNUP` desligado, qualquer
   pessoa cria login e vira `authenticated`, que continua lendo e escrevendo as
   ~30 tabelas do app. Conferir a flag no `.env` do servidor (sem imprimir o resto).

## Janela recomendada

Fora do horário de uso do painel (noite), com o Tarcísio logado no app para o
teste de fumaça logo depois: login, dashboard geral, lista de usuários (como
ADMIN), troca de câmbio, uma tela de campanha. Duração esperada: segundos de
DDL + o tempo do `pg_dump`. Os arquivos não reescrevem tabela (sem lock longo):
só ACL, policies, um índice único em `users` (1–2 linhas) e uma view.

## Riscos para o frontend

| Risco | Probabilidade | Sintoma | Conserto |
|---|---|---|---|
| Admin sem papel em `app_auth` | média (só 1 semeado em 24/08) | lista de usuários mostra só a própria linha | `volc_grant_role` (item 3) |
| Fluxo externo com anon key | baixa (nada no repo) | gravação some sem erro na UI | `GRANT INSERT ON public.<x> TO anon` pontual |
| v8_06 antes do frontend | só se a ordem for invertida | 42501 em `useUserProfile` | `GRANT SELECT ON TABLE public.users TO authenticated;` |
| Operador tentando mudar a própria role/comissão | intencional | erro `exige ADMIN` | — |
| TRUNCATE pelo browser | nenhum uso no código | 42501 | — |

## Rollback

```bash
scripts/aplicar-incidente-anon-w4.sh --rollback
```
Devolve **o estado inseguro** (anon volta a ler e escrever). Prefira os
rollbacks parciais no fim de `v19_99_rollback.sql`. Último recurso: o
`pg_dump` feito pelo `--passo1`.

## O que continua aberto depois do pacote

- `authenticated` lê e escreve as tabelas do app sem policy por escopo
  (operador vê todos os projetos). É trabalho de produto, não de contenção.
- Funções novas em `public` seguem executáveis por PUBLIC (default embutido do
  Postgres). Função INVOKER chamada por anon falha na tabela; DEFINER nova
  precisa de REVOKE nominal, como as migrations já fazem.
- `storage`, `realtime`, `supabase_functions`: grants da imagem, não tocados.
- `supabase_read_only_user` com BYPASSRLS e `pg_read_all_data`: decisão
  separada (handoff B, item 5).
- Achado colateral: **v17_03 e v17_04 não estão aplicadas em produção**. As 7
  funções da v17_03 não existem no dump de produção de 15/10, e as views de
  arbitragem batem (md5) com a definição da v17_01, não com a da v17_04.
