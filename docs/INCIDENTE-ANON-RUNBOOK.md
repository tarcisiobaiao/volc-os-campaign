# Incidente da chave anon — pacote de aplicação (W4, 15/10/2026)

**Estado: pacote provado em laboratório; aplicação bloqueada até o inventário
de consumidores da anon em produção. Nada foi aplicado em produção.** Decisão e
janela são do Tarcísio. Ensaio: schema de produção de 15/10 restaurado num Postgres
descartável (`supabase/postgres:15.8.1.085`, sem rede) por
`tools/freedom-lab/lab.sh recriar-prod` com a suíte
`tools/freedom-lab/db/suites/v19_incidente_anon.sh` (comando no cabeçalho dela;
recibo no handoff W4).

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
| 3 | `v19_01_anon_fecha_public.sql` | supabase_admin | `e7b0c9ba20fa96e7190a740d6f713fa8eac4cbd4b13a446d433c83378e4f858c` | **anon perde tudo em `public`**; authenticated perde TRUNCATE/REFERENCES/TRIGGER; `users` só escreve colunas de perfil; fotografa a ACL anterior para o rollback |
| 4 | `v8_05_users_safe_view.sql` | postgres | `7fb3d2de616404bc3c68f8aee8e2f70b9525bad102f2a17c885b4c54a5434f68` | view `users_safe` sem colunas sensíveis |
| 5 | `v19_02_default_acl_public_sem_anon.sql` | supabase_admin | `8919245ed846060f690e4baa47d3c07d35caf65a6171f859f2b92f3b5b23b671` | tabela e sequência novas em `public` nascem sem anon (substitui a v8_07); função nova segue com EXECUTE por PUBLIC |
| — | `v8_06_users_sensitive_columns_revoke.sql` | supabase_admin | `0010e0874cfe518218eb483223fa5d42b00e40f3138f203b5ca0423efa381554` | **passo 2**: browser deixa de ler `password_hash`/`token_*` — só depois do frontend novo no ar |
| ↩ | `v19_99_rollback.sql` | supabase_admin | `3abff0a814e1db384daaaa9181cbefb8865047ea98025393e4f4fe22293c8fdd` | desfaz 1–5 e a v8_06 só onde o pacote mexeu; aborta se a ACL mudou depois |

**Não aplicar** `v8_02` nem `v8_04`: a v19_01 cobre o que a v8_04 fazia, e a
guarda da v8_04 exige a v8_02, que muda a autoridade de ADMIN do Pautador sem
necessidade para este incidente.

## Estado da decisão

**Bloqueado até o inventário de produção.** O pacote está provado em
laboratório; falta saber quem, fora do app, ainda usa a anon. O `--passo1`
**recusa** sem um inventário assinado (abaixo). A leitura de produção para
preenchê-lo depende de autorização do Tarcísio.

## Ordem com o ledger v20

O pacote v19 vai **antes** do ledger v20 e **fora** dele (decisão do
coordenador, 15/10): a v20 nunca foi aplicada em produção, o incidente é a
prioridade, e o protocolo da v20 (`scripts/migracao-protocolo.sh`) roda como
`postgres` dentro de `BEGIN…COMMIT`, enquanto os v19 exigem superusuário e têm
transação própria. Para o ledger importar depois, cada execução do script grava
`docs/closure/incidente-anon-w4/RECEIPT-<carimbo>.json` com os campos de
`volc_ops.migracao_evento` por arquivo, o fingerprint de `public+app_auth` antes
e depois (mesma SQL da âncora, `tools/freedom-lab/db/fingerprint_schema.sql`) e
o carimbo de tempo. O que a v20 precisa mudar está no handoff W4.

## Comandos (só com autorização nominal: operação, hashes e aprovador)

1. Leitura de produção para o inventário — **preparada, não executada**:
   ```bash
   VOLC_AUTORIZA_LEITURA=inventario-anon-w4 scripts/inventario-anon-producao.sh docs/closure/incidente-anon-w4/leitura
   ```
   Só leitura: edge function `volc-ingest` (filtrada por grep, nunca impressa
   inteira), flags booleanas do GoTrue, contagem de chamadas no Kong, contagens e
   datas no banco em `BEGIN READ ONLY`, e o que o papel anon executou
   (`pg_stat_statements`). Saída bruta em `~/.config/volc/inventario-anon/` (700),
   só a cópia passada por `scripts/mascarar-segredos.sh` vai para o diretório
   dado (fora do repo). Feita em 15/10 13:35Z com autorização do Tarcísio. GTM e credenciais do n8n são passos
   manuais listados na saída (anotar só o claim `role`).
2. Preencher `docs/closure/incidente-anon-w4/INVENTARIO-ANON.json` a partir de
   `docs/INCIDENTE-ANON-INVENTARIO.modelo.json`: cada consumidor com
   confirmação, evidência e decisão (`nao_usa_anon`, `aceita_quebra`,
   `migrado_antes`, `desativado`), assinado, `bloqueia_passo1: false`. Os 8
   consumidores e as decisões válidas são fixos em
   `scripts/validar-inventario-anon-w4.py` (o JSON não os define); rascunho
   preenchido com a leitura de 15/10 em `docs/closure/incidente-anon-w4/INVENTARIO-ANON.json`.
3. ```bash
   scripts/aplicar-incidente-anon-w4.sh --so-checar
   ```
   Preflight como `supabase_read_only_user` (read-only; `item|valor|bloqueia`,
   qualquer `t` recusa o passo 1) e verificação **como anon de verdade**
   (`postgres` read-only + `SET ROLE anon`).
4. ```bash
   scripts/aplicar-incidente-anon-w4.sh --passo1 --aprovador "<nome>" --inventario docs/closure/incidente-anon-w4/INVENTARIO-ANON.json --sha-inventario <sha256>
   ```
   Recusa sem inventário válido, com preflight bloqueando, ou se a verificação
   não vir o buraco antes. Pede `APLICAR`; `pg_dump -Fc -n public -n app_auth`;
   fingerprint antes; aplica 1→5 (cada arquivo atômico; se um falhar, o script
   para, diz quais ficaram e grava o recibo como `falhou`); `NOTIFY pgrst`; exige
   **FECHADO** (V1, V2, V3 e V4 = 0); fingerprint depois; recibo JSON.
5. ```bash
   scripts/aplicar-incidente-anon-w4.sh --passo2 --aprovador "<nome>"
   ```
   Só depois que o frontend com `src/hooks/useUserProfile.ts` corrigido estiver em produção.

O próprio script foi ensaiado contra um container do `lab.sh` com o schema de
produção (`W4_ALVO_LAB=<container>`; recusa qualquer container fora do lab ou com
rede): recusas, passo 1, recibo JSON e rollback com fingerprint de volta ao de antes.

## Antes da janela — inventário dos consumidores da anon

Pelo repositório (15/10): o app logado, o backend Node/FastAPI, volc_ads e a
edge function `capi-router` não usam a anon. **Fora do app há consumidores**:

| # | Consumidor | O que faz com a anon | Estado conhecido | Precisa de produção para confirmar |
|---|---|---|---|---|
| 1 | GTM **GTM-N4KS27ZV** (creditoup), tag 35 | POST `/rest/v1/site_visits` com JWT anon | pausada (18/09), ainda na versão publicada 34 | versão viva do container |
| 2 | GTM-N4KS27ZV, tag 28 | GET `/rest/v1/niche_conversion_mappings` com JWT anon | pausada (29/09) | idem |
| 3 | GTM-N4KS27ZV, tag 39 "VOLC Sensor v1.4" | POST `/functions/v1/volc-ingest`, **sem** chave | pausada (18/09) | código e chave da edge function `volc-ingest` (fonte fora do repo) |
| 4 | GTM-KJK7QQK9 | desconhecido (sem export) | aparece em LPs públicas | container vivo |
| 5 | n8n `gads-campaign-search` | upsert/PATCH em `niche_conversion_mappings` com apikey escrita à mão | ativo, quebrado desde 24/02 | qual chave (anon ou service_role) |
| 6 | n8n `comportamento-gtm-scroll-funil` | RPCs `compute_page_daily`, `compute_funnel_daily`, … com apikey à mão | inativo | qual chave |
| 7 | n8n credencial "VOLC Oficial" | gravações de joinads, gads, meta | runbook JWT diz service_role | conferir |
| 8 | Logs Kong/PostgREST | tráfego com role anon de origem fora do app | — | leitura dos logs |

Também: `docs/VOLC-DELTA.md:278-282` usa a anon num curl para ler o OpenAPI —
depois do passo 1 ele deixa de listar tabelas. A anon segue gravada no histórico
de versões do GTM: fechar os grants não a tira de circulação.

E ainda:
- **ADMINs em `app_auth`**: P4 bloqueia se houver ADMIN do cadastro sem papel.
  Conceder antes: `SELECT public.volc_grant_role('<auth.users.id>','ADMIN','pre-W4');`.
  Se escapar, as telas de admin agora mostram o erro (`src/v6/services/visaoDeAdmin.ts`)
  em vez de uma lista silenciosamente incompleta ou de um falso "último administrador".
- **Cadastro público no GoTrue — medido aberto em 15/10**: `DISABLE_SIGNUP=false`,
  `ENABLE_PHONE_SIGNUP=true`, `ENABLE_PHONE_AUTOCONFIRM=true`. Qualquer pessoa
  pode virar `authenticated`, que segue lendo e escrevendo 61 relações. Fechar
  antes ou na janela: `scripts/fechar-cadastro-gotrue.sh` (`--checar`, `--aplicar`,
  `--reverter`; pós-check sem criar conta).
- **Senha**: 1 SELECT de `users` com `password_hash` pela anon desde 05/08.
  Trocar a senha do único usuário e revogar sessões logo depois do passo 1.

## Janela recomendada

Fora do horário de uso do painel (noite), com o Tarcísio logado no app para o
teste de fumaça logo depois: login, dashboard geral, lista de usuários (como
ADMIN), troca de câmbio, uma tela de campanha. Duração esperada: segundos de
DDL + o tempo do `pg_dump`. Os arquivos não reescrevem tabela (sem lock longo):
só ACL, policies, um índice único em `users` (1–2 linhas) e uma view.

## Riscos para o frontend

| Risco | Probabilidade | Sintoma | Conserto |
|---|---|---|---|
| Admin sem papel em `app_auth` | média (só 1 semeado em 24/08); P4 bloqueia | tela de admin mostra erro de papel | `volc_grant_role` |
| Fluxo externo com anon key | **real** (tabela do inventário) | gravação some sem erro na UI | `GRANT INSERT ON public.<x> TO anon` pontual |
| v8_06 antes do frontend | só se a ordem for invertida | 42501 em `useUserProfile` | `GRANT SELECT ON TABLE public.users TO authenticated;` |
| Operador tentando mudar a própria role/comissão | intencional | erro `exige ADMIN` | — |
| TRUNCATE pelo browser | nenhum uso no código | 42501 | — |

## Rollback

```bash
scripts/aplicar-incidente-anon-w4.sh --rollback --aprovador "<nome>"
```
Devolve **o estado inseguro** (anon volta a ler e escrever), e só nas ACLs que
a v19_01 mudou. **Aborta sem desfazer nada** se alguma delas foi alterada de
novo depois da aplicação (um endurecimento posterior não some calado). Nomes
gravados com schema e `search_path` fixo: nada fora de `public` é tocado.
Prefira os rollbacks parciais no fim de `v19_99_rollback.sql`. Último recurso:
o `pg_dump` feito pelo `--passo1`.

## O que continua aberto depois do pacote

- `authenticated` lê e escreve as tabelas do app sem policy por escopo
  (operador vê todos os projetos). É trabalho de produto, não de contenção.
- Funções novas em `public` seguem executáveis por PUBLIC (default embutido do
  Postgres; a v19_02 não muda isso, e o título dela diz). Função INVOKER chamada
  por anon falha na tabela; uma SECURITY DEFINER nova sem REVOKE explícito lê
  com o privilégio do dono. O `REVOKE EXECUTE … FROM PUBLIC` global foi
  recusado: vale para todos os schemas desses donos.
- `storage`, `realtime`, `supabase_functions`: grants da imagem, não tocados.
- `supabase_read_only_user` com BYPASSRLS e `pg_read_all_data`: decisão
  separada (handoff B, item 5).
- Achado colateral: **v17_03 e v17_04 não estão aplicadas em produção**. As 7
  funções da v17_03 não existem no dump de produção de 15/10, e as views de
  arbitragem batem (md5) com a definição da v17_01, não com a da v17_04.
