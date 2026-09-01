# Pacote de aplicação — v12_02 (plano de mensuração)

**Estado:** a migration **NÃO foi aplicada** em produção nesta missão, e nenhuma
escrita foi feita no Supabase oficial. Este documento é o roteiro para quem
tiver autorização de dono para aplicá-la.

> ⚠️ **Nenhuma credencial aparece aqui.** Onde o comando precisa de segredo, ele
> lê do `.env` vivo do servidor ou de `~/.ssh/volc-supabase-live.env`.

---

## 0. Identidade do que vai ser aplicado

| arquivo | linhas | sha256 |
|---|---|---|
| `supabase/migrations/v12_02_plano_de_mensuracao.sql` | 581 | `6ea4da6283bb74529ebbb9e8b2ce540f89813c47160a8620daa9440a75715276` |
| `supabase/migrations/v12_02_rollback.sql` | 91 | `f95da19eef129570432d5b226707893a5ecaa319b4cccc37f492e7cb94b5b79d` |

Confira antes de qualquer coisa, na máquina de onde vai aplicar:

```bash
shasum -a 256 supabase/migrations/v12_02_plano_de_mensuracao.sql
# precisa bater com a linha da tabela acima. Não bateu: PARE.
```

Se o hash divergir, o arquivo não é o que este pacote descreve, e nada abaixo
vale — as contraprovas foram escritas contra ESTE conteúdo.

---

## 1. Preflight

```bash
# 1.1 — a autoridade operacional é o self-hosted, e só ele
python3 scripts/verificar_autoridade_supabase.py
# esperado: ✓ Supabase oficial: https://database.agenciavolc.com.br

# 1.2 — o ciclo inteiro num Postgres DESCARTÁVEL, que nasce e morre no comando
bash scripts/provar-ciclo-v12_02.sh
# esperado: "passaram 55 · falharam 0" e
#           "CICLO v12_02 COMPLETO: aplicar → operar → reverter → reaplicar"
```

⚠️ **O 1.2 não fala com produção.** Ele sobe um cluster em `$TMPDIR`, aplica a
v9_01 (a v12_02 tem FK para `trafego_campanha`), aplica a v12_02, roda as 38+
provas de comportamento, reverte, reaplica e confere que uma terceira aplicação
é recusada com nome. Um rollback que nunca rodou é um rollback que ninguém tem.

```bash
# 1.3 — a v9_01 precisa existir no banco de destino (é a FK)
ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
  "docker exec -i supabase-db psql -U postgres -At -c \
   \"select to_regclass('public.trafego_campanha') is not null\""
# esperado: t   — se vier f, a v12_02 vai abortar com 55000 dizendo isso.

# 1.4 — a v12_02 ainda NÃO está aplicada
ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
  "docker exec -i supabase-db psql -U postgres -At -c \
   \"select to_regclass('public.trafego_campanha_plano_de_mensuracao') is null\""
# esperado: t   — se vier f, ela já está lá e reaplicar é recusado com 42P07.
```

---

## 2. Backup — antes, e conferido

```bash
ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
  "mkdir -p /root/backups && \
   docker exec supabase-db pg_dump -U postgres -Fc postgres \
     > /root/backups/pre-v12_02-\$(date +%Y%m%d-%H%M%S).dump && \
   ls -lh /root/backups/ | tail -3"
```

⚠️ **Confira o TAMANHO do arquivo.** Um dump de zero byte é o desfecho normal de
um `pg_dump` que falhou com o stdout já aberto, e ele parece um backup.

---

## 3. O comando exato

```bash
cat supabase/migrations/v12_02_plano_de_mensuracao.sql \
  | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
    "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
```

Saída esperada, na última linha antes do COMMIT:

```
NOTICE:  v12_02 OK: 1 tabela, RLS forcada, 0 policies, 1 gatilho, 28 CHECKs, escrita so por funcao.
```

⚠️ `ON_ERROR_STOP=1` não é opcional. Sem ele o `psql` segue depois de um erro e
o `commit` no fim do arquivo grava um estado pela metade.

⚠️ Rode como `postgres` ou `supabase_admin`. A própria migration recusa outro
papel na primeira guarda — é por isso que o comando entra por `docker exec` e
não pelo PostgREST.

---

## 4. Contraprovas PÓS-APLICAÇÃO

Rode todas. Cada uma tem um esperado literal; qualquer divergência é motivo de
rollback, não de investigação com a tabela em produção.

```bash
Q() { ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
      "docker exec -i supabase-db psql -U postgres -At -c \"$1\""; }

# 4.1 a tabela existe
Q "select count(*) from pg_tables where schemaname='public'
   and tablename='trafego_campanha_plano_de_mensuracao'"                    # 1

# 4.2 RLS FORÇADA (não só ligada) e ZERO policies
Q "select c.relrowsecurity and c.relforcerowsecurity from pg_class c
   join pg_namespace n on n.oid=c.relnamespace
   where n.nspname='public'
     and c.relname='trafego_campanha_plano_de_mensuracao'"                  # t
Q "select count(*) from pg_policies where schemaname='public'
   and tablename='trafego_campanha_plano_de_mensuracao'"                    # 0

# 4.3 anon/authenticated/PUBLIC sem privilégio nenhum
Q "select count(*) from information_schema.role_table_grants
   where table_schema='public'
     and table_name='trafego_campanha_plano_de_mensuracao'
     and grantee in ('anon','authenticated','PUBLIC')"                      # 0

# 4.4 service_role LÊ e NÃO ESCREVE direto — a escrita é só pela função
Q "select has_table_privilege('service_role',
     'public.trafego_campanha_plano_de_mensuracao','SELECT')"               # t
Q "select count(*) from information_schema.role_table_grants
   where table_schema='public'
     and table_name='trafego_campanha_plano_de_mensuracao'
     and grantee='service_role'
     and privilege_type in ('INSERT','UPDATE','DELETE','TRUNCATE')"         # 0

# 4.5 a função de escrita existe e anon NÃO a executa
Q "select has_function_privilege('anon',
     'public.volc_registrar_plano_de_mensuracao(jsonb)','EXECUTE')"         # f
Q "select has_function_privilege('service_role',
     'public.volc_registrar_plano_de_mensuracao(jsonb)','EXECUTE')"         # t

# 4.6 append-only: UPDATE e DELETE recusados pelo gatilho
Q "select count(*) from pg_trigger
   where tgname='trafego_plano_append_only_tg'"                             # 1

# 4.7 os 28 CHECKs sobreviveram
Q "select count(*) from pg_constraint
   where conrelid='public.trafego_campanha_plano_de_mensuracao'::regclass
     and contype='c'"                                                       # 28

# 4.8 a tabela nasce VAZIA — nenhuma linha foi fabricada pela aplicação
Q "select count(*) from public.trafego_campanha_plano_de_mensuracao"        # 0
```

⚠️ **Não faça um INSERT de teste em produção.** As invariantes de comportamento
já foram provadas 55 vezes no cluster descartável do passo 1.2, e a tabela é
append-only: uma linha de teste não sai mais.

### 4.9 O gate de aplicação do lado da aplicação

Depois da migration, o backend passa a conseguir gravar. Confira que a rota
deixou de recusar por migration ausente:

```bash
# do processo do backend, com o Supabase configurado:
#   POST /api/trafego/provar  →  prontidao.plano_persistido.persistido == false
#   (continua false: /provar não escreve — quem grava é /subir)
```

Se `/subir` responder **503 com "aplique supabase/migrations/v12_02..."**, a
migration não chegou ao banco que o processo está usando.

---

## 5. Rollback

```bash
cat supabase/migrations/v12_02_rollback.sql \
  | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
    "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
```

Contraprovas do rollback:

```bash
Q "select count(*) from pg_tables where schemaname='public'
   and tablename='trafego_campanha_plano_de_mensuracao'"                    # 0
Q "select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace
   where n.nspname='public' and p.proname in
     ('trafego_plano_append_only','volc_registrar_plano_de_mensuracao')"    # 0
Q "select count(*) from pg_tables where schemaname='public'
   and tablename='trafego_campanha'"                                        # 1
```

⚠️ **O rollback APAGA a tabela, e ela não é reconstruível.** Cada linha é a
fotografia de uma leitura num instante que não volta. Depois que o sistema
começar a gravar planos, reverter custa o histórico inteiro — restaure do dump
do passo 2 em vez de reverter, se já houver linhas.

---

## 6. Hard stops

Pare e devolva a decisão ao dono se:

1. o **sha256** do arquivo divergir da tabela do passo 0;
2. o passo **1.2** não terminar em `passaram 55 · falharam 0`;
3. `to_regclass('public.trafego_campanha')` vier **f** (falta a v9_01);
4. a tabela **já existir** (`42P07`) — reaplicar não é idempotente aqui, e a
   recusa é o comportamento correto;
5. o backup do passo 2 tiver **tamanho zero** ou o `ls` não listar o arquivo;
6. qualquer contraprova do passo 4 divergir do esperado literal;
7. o `NOTICE` final não aparecer, mesmo com o comando saindo 0;
8. o `kong.yml` tiver sido tocado no mesmo dia — ver a armadilha do Kong no
   `CLAUDE.md`: um `origins: - "*"` sem escape derruba o site no próximo reboot,
   e diagnosticar as duas coisas juntas é como se perde o dia.

---

## 7. O que este pacote NÃO autoriza

- nenhuma escrita no Supabase oficial além desta migration;
- nenhum `mutate` no Google Ads, na Data Manager ou no GTM;
- nenhuma ativação de campanha;
- nenhuma alteração de meta ou de ação de conversão;
- nenhum deploy, push ou merge.
