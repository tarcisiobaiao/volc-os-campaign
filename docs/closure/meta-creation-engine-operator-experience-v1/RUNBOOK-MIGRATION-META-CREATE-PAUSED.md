# Runbook — migration da autoridade durável do nascimento Meta PAUSED

> **Esta migration NÃO foi aplicada em lugar nenhum.** Nem no Supabase oficial,
> nem em staging. O único ambiente onde ela já rodou é o PostgreSQL descartável
> de `scripts/provar-ciclo-meta-create-paused.sh`, que nasce e morre dentro do
> script. Este runbook descreve o que **seria preciso** para aplicá-la; ele não
> autoriza nem executa nada.

Escrito na missão de validação real Meta, com a árvore em
`execution/volc-os-operacao-80-20`.

---

## 1. Identidade dos arquivos

| Papel | Arquivo | sha256 | Linhas (`wc -l`) |
|---|---|---|---|
| Apply | `supabase/migrations/20260904183418_meta_create_paused_executor.sql` | `c5336b271ed7b2281fc959546d07cf6e83e32bdea9507af86ffbee498254f010` | 990 |
| Rollback | `supabase/migrations/20260904183514_meta_create_paused_executor_rollback.sql` | `f920257effcb4f525b2ff110ae95e3a14da87ba609988df7a834feac76c49c48` | 42 |

Blob git do apply nesta árvore: ver `git rev-parse HEAD:supabase/migrations/20260904183418_meta_create_paused_executor.sql`.

⚠️ **Os dois sha256 mudaram na missão do caminho governado `create_paused`.**
Valores anteriores, para quem tiver anotado:

| Papel | sha256 anterior | Missão |
|---|---|---|
| Apply | `26cb41d649dbe3e9b1ea95227dcf792025fc344444d742accbd03b18aefeec65` | validação real |
| Apply | `92495e90d70185a4b971450ed56bd96fc8358f7bef240e3bed0ededdbf538a99` | operator experience |
| Apply | `202399f9825ec701dc534fd5890adea8e369c717b442227cc8f65a35d7bc0891` | caminho governado, antes da rodada corretiva |
| Rollback | `30ccfb4fe72883b7b5dde986c0731aca7a5de5b1dca048dc2bb863da72501ecc` | validação real |
| Rollback | `c5e284dbd9a3ee6b9eb5504f4af631ccb4cc7f4c0de78d50d7dcda104d63dc26` | caminho governado, antes da rodada corretiva |

**A migration continua nunca aplicada em lugar nenhum**, então não existe banco
cujo estado corresponda a um hash antigo e não há reconciliação pendente. O
valor correto é sempre o da primeira tabela.

O que mudou, e por quê:

1. **`trafego_meta_validation_receipt` (tabela nova).** Antes, a prova de que a
   Meta aceitou o plano sob `validate_only` existia só no corpo da resposta HTTP
   — quer dizer, só no navegador. Uma aprovação que aceitasse essa palavra
   estaria confiando no cliente para dizer "eu fui validado". Agora quem grava é
   o servidor, e a aprovação referencia uma linha real.
2. **`trafego_meta_create_approve` mudou de assinatura**, de
   `(text,text,text,bigint,timestamptz,text[])` para
   `(text,text,text,bigint,text,timestamptz,text[],uuid,integer,boolean,jsonb)`.
   Ganhou moeda explícita, o `validation_id`, a janela de frescor da validação,
   a confirmação humana de nascimento PAUSED e o pedido do operador. **O
   rollback mudou junto**, porque o `DROP FUNCTION` cita a assinatura completa.
3. **Três colunas novas na aprovação** (`operations_expected`, `validation_id`
   com `UNIQUE`, `paused_birth_confirmed`, `plan_request`) e um teto de uma hora
   na expiração, no próprio `CHECK`.
4. **Quatro RPCs novas**: `trafego_meta_create_approval_manifest` (o manifesto
   do lado do servidor, com `step_ref`, `prepared_at` e o pedido do operador),
   `trafego_meta_create_resolve_absent` (o único caminho de `AMBIGUOUS` para
   `FAILED`, e só depois de a ausência ser provada por leitura),
   `trafego_meta_create_flag_readback` e
   `trafego_meta_create_validation_lookup`.
5. **A rodada corretiva da revisão adversarial** acrescentou, sobre o item
   anterior:
   - `trafego_meta_create_step_identidade_ix` e a sonda por **(conta, passo,
     payload)** dentro de `trafego_meta_create_prepare_step`. Sem ela, mudar a
     headline de um anúncio produzia outro `plan_sha256` com o payload da
     Campaign idêntico, e a mesma campanha nascia duas vezes na conta.
   - `readback_error` em `trafego_meta_create_step`, mais
     `trafego_meta_create_flag_readback`: o recibo fecha antes do read-back de
     propósito (o id precisa ser gravado antes de tudo), e agora uma
     divergência de leitura fica registrada em vez de sumir atrás de um
     `CREATED` limpo.
   - `p_idade_minima_s` em `trafego_meta_create_resolve_absent`: um passo vira
     ambíguo assim que alguém reentra nele, e isso pode acontecer com o
     despachante original ainda dentro do `await` do POST. Fechar como ausente
     nesse instante gravaria "não existe" sobre um objeto prestes a nascer.
   - `trafego_meta_create_validation_lookup`, para a rota recusar um recibo
     inutilizável **antes** de abrir o Keychain.

---

## 2. Pré-condições

A própria migration recusa se qualquer uma faltar — o bloco `$guarda$` roda
antes de qualquer DDL, dentro da mesma transação:

1. `current_user` é `postgres` ou `supabase_admin`. Qualquer outro papel aborta.
2. `server_version_num >= 150000` (PostgreSQL 15+).
3. `public.trafego_meta_ad_account` existe — ou seja, o read model Meta
   `v15_01_meta_ads_read_model.sql` já está aplicado. A migration **depende** de
   v15_01 mas não escreve nele: criação e observação são autoridades diferentes.
4. Os papéis `anon`, `authenticated` e `service_role` existem.
5. Nenhuma das **três** tabelas já existe. Se `trafego_meta_create_approval`,
   `trafego_meta_create_step` ou `trafego_meta_validation_receipt` estiverem lá,
   a migration aborta pedindo o rollback correspondente — ela **não** é
   idempotente, e isso é deliberado: não há um só `IF NOT EXISTS` no arquivo.

Pré-condições que a migration **não** consegue verificar sozinha e que o
proprietário precisa confirmar antes:

6. Que o `postgres` do Supabase alvo atravessa RLS (`rolsuper` ou `rolbypassrls`).
   As três tabelas nascem com `FORCE ROW LEVEL SECURITY` e **zero policies**; quem
   não atravessa RLS não lê nem escreve nelas, e as funções `SECURITY DEFINER`
   rodam como o dono da migration. A migration restringe o dono pelo **nome**
   (`postgres`/`supabase_admin`), não pelo atributo. O ciclo descartável não
   detecta uma regressão aqui porque roda como superusuário.
   Consulta para confirmar antes de aplicar:
   ```sql
   SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user;
   ```
7. Que existe janela para uma transação curta. O apply cria apenas objetos novos:
   nenhum `DROP`, `TRUNCATE`, `DELETE` ou `ALTER ... DROP COLUMN`, portanto
   nenhum lock sobre relação preexistente e nenhuma reescrita de tabela.

---

## 3. Backup / snapshot exigido

Como o apply só **cria** objetos, o risco de perda de dado no apply é nulo. O
snapshot é exigido pelo **rollback**, não pelo apply — ver secção 6.

Antes de aplicar, exigir do proprietário:

- Snapshot/PITR do banco Supabase oficial com timestamp anterior ao apply,
  registrado por escrito (data, hora, identificador do snapshot).
- Confirmação de que o snapshot é restaurável, não apenas agendado.

---

## 4. Apply

```bash
psql "$URL_DO_SUPABASE_OFICIAL" \
  -X -v ON_ERROR_STOP=1 \
  -f supabase/migrations/20260904183418_meta_create_paused_executor.sql
```

O arquivo abre `BEGIN;` e fecha `COMMIT;` sozinho: ou entra inteiro, ou não entra.

Antes de rodar, conferir que o arquivo em disco é o desta tabela:

```bash
shasum -a 256 supabase/migrations/20260904183418_meta_create_paused_executor.sql
# esperado: c5336b271ed7b2281fc959546d07cf6e83e32bdea9507af86ffbee498254f010
```

---

## 5. Probes — consultas de verificação pós-apply

**5.1 Forma: as três tabelas existem, com RLS forçada e zero policies**

```sql
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
       (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS policies
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public'
   AND c.relname IN ('trafego_meta_create_approval','trafego_meta_create_step',
                     'trafego_meta_validation_receipt');
-- esperado: 3 linhas, relrowsecurity=t, relforcerowsecurity=t, policies=0
```

**5.2 As doze funções existem, todas SECURITY DEFINER com search_path fixo**

```sql
SELECT p.proname, p.prosecdef, p.proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public' AND p.proname LIKE 'trafego_meta_%'
 ORDER BY p.proname;
-- esperado: 12 linhas, prosecdef=t, proconfig={search_path=pg_catalog, public}
-- (exigir_service_role, record_validation, approve, prepare_step, close_step,
--  mark_ambiguous, fail_step, resolve_absent, flag_readback,
--  validation_lookup, approval_manifest, receipt)
```

**5.3 Nenhum grant sobrou para anon/authenticated**

```sql
SELECT grantee, table_name, privilege_type
  FROM information_schema.role_table_grants
 WHERE table_schema = 'public'
   AND table_name IN ('trafego_meta_create_approval','trafego_meta_create_step',
                      'trafego_meta_validation_receipt')
   AND grantee IN ('anon','authenticated','PUBLIC');
-- esperado: zero linhas
```

**5.4 service_role tem SELECT nas tabelas e EXECUTE nas RPCs, e nada além**

```sql
SELECT table_name, privilege_type
  FROM information_schema.role_table_grants
 WHERE table_schema='public' AND grantee='service_role'
   AND table_name IN ('trafego_meta_create_approval','trafego_meta_create_step',
                      'trafego_meta_validation_receipt');
-- esperado: apenas SELECT em cada uma. INSERT/UPDATE/DELETE NÃO devem aparecer:
-- a única porta de escrita são as RPCs SECURITY DEFINER.
```

**5.5 O portão de autorização morde**

```sql
SET ROLE authenticated;
SELECT public.trafego_meta_create_approve(
  repeat('d',64), 'metaacct_probe', 'probe', 1000, 'BRL',
  clock_timestamp() + interval '15 minutes', ARRAY['campaign'],
  gen_random_uuid(), 1800, true, '{}'::jsonb);
-- esperado: ERRO 42501 "operacao Meta exige service_role"
-- Gravar recibo de validação também é privilégio de serviço:
SELECT public.trafego_meta_create_record_validation(
  repeat('d',64), 'metaacct_probe', 'probe', 'INDEPENDENT_ROOTS_ONLY',
  ARRAY['campaign'], ARRAY['adset'], 2, 0);
-- esperado: ERRO 42501
RESET ROLE;
```

**5.6 As tabelas nascem vazias**

```sql
SELECT (SELECT count(*) FROM public.trafego_meta_create_approval) AS aprovacoes,
       (SELECT count(*) FROM public.trafego_meta_create_step) AS passos,
       (SELECT count(*) FROM public.trafego_meta_validation_receipt) AS validacoes;
-- esperado: 0, 0, 0
```

---

## 6. Rollback

```bash
psql "$URL_DO_SUPABASE_OFICIAL" \
  -X -v ON_ERROR_STOP=1 \
  -f supabase/migrations/20260904183514_meta_create_paused_executor_rollback.sql
```

Derruba exatamente as 12 funções (por assinatura completa) e as 3 tabelas, na
ordem segura de FK (`step` antes de `approval`, `approval` antes de
`validation_receipt`). Índices e constraints vão junto com as tabelas. Não toca
em mais nada.

⚠️ A assinatura de `trafego_meta_create_approve` no `DROP FUNCTION` **precisa**
ser a nova, de 11 argumentos. A antiga, de 6, não existe mais, e um `DROP` por
nome só esconderia o dia em que houvesse duas sobrecargas.

⚠️ **O rollback é seguro apenas ANTES do primeiro uso real.** Ele é um
`DROP TABLE` sem guarda de tabela não-vazia. `trafego_meta_create_step.external_object_id`
é o único registro local que liga uma aprovação aos objetos que a Meta realmente
criou; derrubá-lo depois de uma saga real deixa os objetos vivos na conta sem
livro local, e uma saga em voo fica irretomável. (O read model Meta v15_01
continua enxergando os objetos pela conta, mas não a proveniência
aprovação→objeto.)

**Verificar antes de rodar o rollback:**

```sql
SELECT (SELECT count(*) FROM public.trafego_meta_create_approval) AS aprovacoes,
       (SELECT count(*) FROM public.trafego_meta_create_step) AS passos,
       (SELECT count(*) FROM public.trafego_meta_create_step
         WHERE state IN ('CREATED','AMBIGUOUS')) AS irreversiveis;
```

Se `irreversiveis > 0`, **parar**: existe objeto na Meta cuja proveniência
morreria com o DROP. Nesse caso o rollback exige decisão explícita do
proprietário, com o resultado das consultas anexado.

---

## 7. Reapply

O ciclo apply → usar → rollback → reapply está provado em PostgreSQL descartável
por `scripts/provar-ciclo-meta-create-paused.sh` (Gate 6 de `GATES.md`), que:

- sobe `postgres:15` em Docker com `--pull=never` (ou `initdb` local com `--local`);
- reproduz o ACL default quebrado do Supabase e um `service_role` `BYPASSRLS`;
- aplica v13_01 + v15_01 + a candidata;
- exercita a saga inteira pelas RPCs em **notação nomeada**, com os mesmos nomes
  de parâmetro que `backend/app/trafego/meta_execucao/registro.py` envia;
- prova o portão de aprovação única, inclusive **duas conexões simultâneas**
  disputando o mesmo `plan_sha256`;
- reverte, confere que não sobrou nada e que o read model v15_01 sobreviveu;
- reaplica.

```bash
bash scripts/provar-ciclo-meta-create-paused.sh          # Docker
bash scripts/provar-ciclo-meta-create-paused.sh --local  # initdb local
```

Nunca toca no Supabase oficial nem na Meta. Última execução nesta missão: verde.

---

## 8. O portão de aprovação única (novo nesta missão)

`trafego_meta_create_approve` agora recusa uma segunda aprovação **viva** do
mesmo `plan_sha256` com `META_APPROVAL_ALREADY_LIVE`.

Por que não é um `UNIQUE`: um UNIQUE em `plan_sha256` barraria para sempre; um
UNIQUE parcial `WHERE state = 'APPROVED'` barraria depois da expiração, porque
uma aprovação expirada continua `APPROVED`. O portão usa
`pg_advisory_xact_lock(hashtextextended(p_plan_sha256, 1602))` — transacional,
fechando a janela entre o `SELECT` e o `INSERT` — mais uma sonda explícita.

Predicado de "viva": `state = 'APPROVED'` **e** não expirada **e** sem nenhum
passo `FAILED`.

| Situação anterior do plano | Reaprovação |
|---|---|
| Aprovação viva, saga não começou | **recusada** |
| Aprovação viva, passos `IN_FLIGHT` | **recusada** |
| Aprovação viva, algum passo `AMBIGUOUS` | **recusada** — reconciliar primeiro |
| Aprovação expirada | permitida |
| Aprovação com passo `FAILED` | permitida |
| Aprovação `REVOKED` | permitida |
| Plano diferente | sempre permitida |

`AMBIGUOUS` prende de propósito: ambíguo significa que pode ter nascido objeto,
e reaprovar antes de reconciliar é exatamente a duplicação que o portão existe
para impedir.

Probe pós-apply:

```sql
SET ROLE service_role;
SELECT public.trafego_meta_create_approve(
  repeat('7',64), 'metaacct_probe', 'probe', 1000,
  clock_timestamp() + interval '1 hour', ARRAY['campaign','adset']);
SELECT public.trafego_meta_create_approve(
  repeat('7',64), 'metaacct_probe', 'probe', 1000,
  clock_timestamp() + interval '1 hour', ARRAY['campaign','adset']);
-- esperado: a primeira devolve approval_id; a segunda ERRA com
-- META_APPROVAL_ALREADY_LIVE.
RESET ROLE;
-- limpar o probe exige o rollback, ou um DELETE deliberado como dono.
```

---

## 9. Riscos

| # | Risco | Estado |
|---|---|---|
| 1 | `FORCE RLS` com zero policies depende de o dono atravessar RLS, garantido pelo **nome** do papel e não pelo atributo. O ciclo descartável roda como superusuário e não detecta regressão aqui. | aberto — mitigado pela pré-condição 6 |
| 2 | Rollback é `DROP TABLE` sem guarda de tabela não-vazia; destrói a proveniência aprovação→objeto. | aberto — mitigado pela verificação da secção 6 |
| 3 | `AMBIGUOUS` é estado terminal sem RPC de saída: nenhuma função move `AMBIGUOUS` para `CREATED`/`FAILED`, e não existe leitor que consulte a Meta para decidir. Sair exige SQL manual + inspeção na UI da Meta. | aberto |
| 4 | `RegistroSagaMetaSupabase.aprovar()` e `.recibo()` não têm chamador algum no código Python. Nenhuma aprovação pode ser emitida hoje; o script de ciclo é o único exercício dessas RPCs. | aberto — por construção, já que a criação não está montada |
| 5 | Duas aprovações **sequenciais** do mesmo plano continuam possíveis depois da expiração de uma saga totalmente `CREATED`. O portão trata concorrência e vida, não histórico. | aberto — decisão consciente |
| 6 | A migration não é idempotente. Rodar duas vezes aborta na guarda, sem efeito colateral. | fechado por design |

---

## 10. A ação que exige autorização do proprietário

Nada neste runbook foi executado contra banco oficial.

**Ação exata que exige autorização explícita do proprietário do dado:**

> Executar
> `psql "$URL_DO_SUPABASE_OFICIAL" -X -v ON_ERROR_STOP=1 -f supabase/migrations/20260904183418_meta_create_paused_executor.sql`
> contra `https://database.agenciavolc.com.br`, criando as tabelas
> `public.trafego_meta_create_approval` e `public.trafego_meta_create_step` e
> sete funções `SECURITY DEFINER`, com snapshot/PITR anterior registrado por
> escrito.

Autorizar essa aplicação **não** autoriza criar nada na Meta: a criação PAUSED
continua sem rota montada, e depende de decisões separadas listadas em
`REMAINING-RISKS.md`.
