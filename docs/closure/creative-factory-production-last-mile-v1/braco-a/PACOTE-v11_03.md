# Pacote de aplicação da `v11_03` — execução criativa

**Estado em 02/09/2026: NADA FOI APLICADO.** Este documento é o roteiro; ele não
foi executado contra nenhum banco real. Cada passo abaixo é um gesto humano.

> ⚠️ **Não há credencial neste arquivo, e não deve haver.** Host, usuário e senha
> entram por `~/.pgpass` (chmod 600) ou por variável de ambiente na hora de
> executar. Onde aparece `USUARIO@HOST:PORTA/BANCO`, substitua na sua sessão —
> não edite este arquivo para gravar o valor.

---

## 0. O que vai ser aplicado, e a sua identidade

Confira que os arquivos na sua cópia são estes, **antes** de qualquer outra coisa.
Se um sha256 divergir, pare: você está prestes a aplicar um arquivo diferente do
que foi provado.

```bash
cd <raiz-do-repo>
shasum -a 256 supabase/migrations/v11_03_execucao_criativa.sql \
              supabase/migrations/v11_03_rollback.sql \
              scripts/preflight-v11_03.sh \
              scripts/provar-ciclo-v11_03.sh \
              scripts/provas-v11_03.sql \
              scripts/provas-papeis-v11_03.sql \
              scripts/v11_03-provar-preflight.sh \
              scripts/v11_03-provar-plano.sh
```

| Arquivo | Linhas | sha256 |
|---|---|---|
| `supabase/migrations/v11_03_execucao_criativa.sql` | 876 | `33b55c527b5214fb56a61ec1c056d62e5716fcf17c119f303ab4660831f53a67` |
| `supabase/migrations/v11_03_rollback.sql` | 209 | `861ead45e024ccb8aa1fbd5bdec420b5fbaf9563bbfbee289a583c20399da07b` |

Apoio (não são aplicados no banco, mas fazem parte do pacote):

| Arquivo | Linhas | sha256 |
|---|---|---|
| `scripts/preflight-v11_03.sh` | 358 | `8d6d4d1f7c3b146f03df44a17e71e2f5b9fbd7f5b9489edd15d3c834ba767539` |
| `scripts/provar-ciclo-v11_03.sh` | 303 | `9b09a94fd9f59470e9d183317b5caf30206a03e2e5cb6a034af4c54a0d2377dc` |
| `scripts/provas-v11_03.sql` | 580 | `7a48fbea5226070b80b55f03933bb998ea3bd4a3b0d5c4d5043dabe086f42ba4` |
| `scripts/provas-papeis-v11_03.sql` | 347 | `4ebaa7066a4400b61ad38b53ad717c6e1916693ac1859f2db3be569941a15f02` |
| `scripts/v11_03-provar-preflight.sh` | 165 | `e431a4a89c0dd89ada12098093f8b46daeeb501dd73458a09a96394fded57271` |
| `scripts/v11_03-provar-plano.sh` | 76 | `64fb5291785288598d7b45071af4c9e98fa48ad30e2d12e6a3c92e7f8d7a0245` |

> ⚠️ **`scripts/provas-papeis-v11_03.sql` faltava nesta lista** (achado A4-i), e
> não é um arquivo qualquer: o DEGRAU 2b do ciclo o **executa**, e são dele as
> 34 provas que exercem select/insert/update/delete/truncate sob `anon`,
> `authenticated`, o papel com `BYPASSRLS` e um papel com o mesmo grant sem
> bypass, conferindo SQLSTATE em cada recusa. Um passo 0 que manda "pare se algum
> sha divergir" e omite justamente o arquivo das provas de segurança dá garantia
> onde não conferiu nada. Ele está incluído agora, com o sha256 conferido.

**O que ela cria** (medido em cluster descartável): 5 tabelas `criativo_render_*`,
9 funções, 7 gatilhos, 14 índices, 27 `CHECK`. Não altera nem apaga nada das
v11_01/v11_02. É transacional: aborta inteira ou entra inteira.

---

## 1. Provar o ciclo de novo, na sua máquina

Antes de tocar em banco real, reproduza a prova. Não usa Docker, não fala com
produção, cria e destrói o próprio Postgres.

```bash
bash scripts/provar-ciclo-v11_03.sh
bash scripts/v11_03-provar-preflight.sh
bash scripts/v11_03-provar-plano.sh
```

Esperado, literalmente:

```
  passaram 166 · falharam 0
  CICLO v11_03 COMPLETO: aplicar → operar → reverter → reaplicar
```
```
  passaram 30 · falharam 0
  PREFLIGHT v11_03 PROVADO: acusa quando há o que acusar, e não aplica nada
```
```
  passaram 12 · falharam 0
  PLANO v11_03 descreve a v11_03 que existe
```

**Critério de parada:** qualquer `falharam` diferente de 0 encerra o pacote aqui.

---

## 2. Backup — e a prova de que ele restaura

### 2.1 Tirar o backup

```bash
export STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
pg_dump --format=custom --no-owner --no-privileges --verbose \
        --file="v11_03-pre-$STAMP.dump" \
        "postgresql://USUARIO@HOST:PORTA/BANCO"

shasum -a 256 "v11_03-pre-$STAMP.dump" | tee "v11_03-pre-$STAMP.dump.sha256"
ls -l "v11_03-pre-$STAMP.dump"
```

> No Supabase self-hosted em container, o equivalente é
> `docker exec supabase-db pg_dump --format=custom --no-owner --no-privileges -U postgres postgres > v11_03-pre-$STAMP.dump`.
> Confira que o arquivo do lado de fora tem tamanho plausível: um `docker exec`
> que falha ainda cria um arquivo — vazio.

### 2.2 CONFERIR que ele restaura

⚠️ **Arquivo com data recente não é prova de backup.** Um dump truncado, um dump
de outro banco e um dump de zero byte têm todos data recente. A única prova é
restaurar e contar. Isto abaixo restaura num Postgres descartável, que nasce e
morre no comando, e **não toca em nada**:

```bash
set -euo pipefail
export LC_ALL=C LANG=C                 # sem isto o Postgres do Homebrew não sobe no macOS
DUMP="v11_03-pre-$STAMP.dump"
D="$(mktemp -d)"; mkdir -p "$D/s"
initdb -D "$D/d" -U postgres --encoding=UTF8 --locale=C >/dev/null
pg_ctl -D "$D/d" -l "$D/pg.log" -o "-k $D/s -h ''" -w start >/dev/null
export PGHOST="$D/s" PGUSER=postgres PGDATABASE=postgres

pg_restore --no-owner --no-privileges --dbname=postgres "$DUMP" 2>"$D/restore.err"
echo "--- erros de restauração (esperado: só avisos de papel/extensão) ---"
cat "$D/restore.err"

echo "--- contagem no BACKUP RESTAURADO ---"
psql -X -At -c "select count(*) from pg_tables where schemaname='public'"
psql -X -At -c "select tablename, (xpath('/row/c/text()',
    query_to_xml(format('select count(*) c from public.%I', tablename), false, true, '')))[1]::text::bigint
  from pg_tables where schemaname='public' and tablename like 'criativo_%' order by 1"

pg_ctl -D "$D/d" -m immediate stop >/dev/null; rm -rf "$D"
```

Agora rode as **mesmas duas consultas** contra o banco real (são somente leitura)
e compare linha a linha:

```bash
psql "postgresql://USUARIO@HOST:PORTA/BANCO" -X -At \
  -c "select count(*) from pg_tables where schemaname='public'"
```

**Critério:** as contagens de tabelas e de linhas por tabela têm de bater. Se não
baterem, **o backup não serve** — refaça antes de seguir. Guarde a saída deste
passo junto do `.dump`: é ela, e não o arquivo, que prova o backup.

---

## 3. Preflight (não aplica nada)

```bash
bash scripts/preflight-v11_03.sh "postgresql://USUARIO@HOST:PORTA/BANCO"
echo "exit=$?"
```

Ele põe a própria sessão em `default_transaction_read_only=on` (por `SET`, já
conectado — ver a conferência 8) e confere:

| # | Conferência | Por que ela existe |
|---|---|---|
| 1 | os 5 **nomes** `criativo_render_*` estão livres — lidos em `pg_class`, não em `pg_tables` | `pg_tables` só enxerga relkind `r`/`p`: uma VIEW, MATERIALIZED VIEW, FOREIGN TABLE ou SEQUENCE homônima era invisível, o preflight dizia APTO e a migration morria em `cannot create index on relation` (achado A1). Nome ocupado por qualquer relação é BLOQUEIO, e a mensagem diz por qual tipo |
| 2 | as 21 tabelas da v11_01/v11_02 existem, **por nome e como tabela** | a base tem de ser a que se supõe; contagem não distingue troca de tabela, e `pg_tables` não distinguia "não existe" de "existe como VIEW" |
| 3 | `service_role` existe e tem `BYPASSRLS` | com RLS forçada e zero policies, sem bypass o papel operacional lê zero linhas — a migration aplica limpa e o produto para em silêncio |
| 4 | nenhuma das 9 funções preexiste com **outra assinatura** | `create or replace` com argumentos diferentes cria **sobrecarga**, e o rollback dropa por assinatura: não alcançaria a intrusa |
| 5 | nenhum gatilho `criativo_render_*` homônimo | mesma família de problema |
| 6 | versão do servidor Postgres, banco e usuário conectado | a v11_03 aborta fora de `postgres`/`supabase_admin` |
| 7 | sha256 e contagem de linhas dos dois arquivos | o que está prestes a rodar é o que foi provado? |
| 8 | a própria sessão responde `default_transaction_read_only=on` | afirmar "abro em read-only" não é estar em read-only. O read-only agora é aplicado por `SET` **depois de conectar**, e não por `PGOPTIONS` — que um `options=` dentro do DSN sobrepõe por inteiro (achado A3). Resposta diferente de `on` é BLOQUEIO |

> ⚠️ Fronteira real da garantia de somente-leitura: ela protege contra ENGANO,
> não contra sabotagem. Quem tem privilégio e escreve
> `set default_transaction_read_only = off` de propósito escreve no banco. O que
> não acontece mais é a guarda cair sozinha por causa de um `options=` no DSN.

**Fail-closed.** O que ele não conseguiu conferir sai como `NAO CONFERIDO` e
reprova. Códigos de saída:

- `0` → todas APTO. É o **único** estado em que aplicar é defensável.
- `1` → há BLOQUEIO. Resolva e rode de novo.
- `2` → falta DSN, ou há `NAO CONFERIDO`. "Não deu erro" não é evidência.

---

## 4. Aplicar

Só depois de: ciclo verde (passo 1), backup **restaurado e conferido** (passo 2)
e preflight com `exit=0` (passo 3).

```bash
psql "postgresql://USUARIO@HOST:PORTA/BANCO" \
     -X -v ON_ERROR_STOP=1 \
     -f supabase/migrations/v11_03_execucao_criativa.sql
echo "exit=$?"
```

No Supabase self-hosted em container, o equivalente é o pipe por SSH — o arquivo
não precisa ser copiado para o servidor:

```bash
cat supabase/migrations/v11_03_execucao_criativa.sql | ssh <destino> \
  "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
```

A migration é **transacional** e tem verificação embutida. A última linha da
saída, em caso de sucesso, é exatamente:

```
NOTICE:  v11_03 OK: 5 tabelas, RLS forcada, 0 policies, 7 gatilhos, 4 medidas de audio.
```

Se essa `NOTICE` não aparecer, **a migration não entrou** — o `begin/commit`
garante que ela abortou inteira. Não tente "continuar do meio".

---

## 5. Conferir depois

Somente leitura, contra o banco real:

```bash
psql "postgresql://USUARIO@HOST:PORTA/BANCO" -X -At <<'SQL'
select 'tabelas=' || count(*) from pg_tables
 where schemaname='public' and tablename like 'criativo_render_%';
select 'rls_forcada=' || count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace
 where n.nspname='public' and c.relname like 'criativo_render_%'
   and c.relkind='r' and c.relrowsecurity and c.relforcerowsecurity;
select 'policies=' || count(*) from pg_policies
 where schemaname='public' and tablename like 'criativo_render_%';
select 'funcoes=' || count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace
 where n.nspname='public'
   and (p.proname like 'criativo_render_%' or p.proname like 'criativo_storage_chave%');
select 'gatilhos=' || count(*) from pg_trigger t join pg_class c on c.oid=t.tgrelid
 join pg_namespace n on n.oid=c.relnamespace
 where n.nspname='public' and c.relname like 'criativo_render_%' and not t.tgisinternal;
select 'medidas_audio=' || count(*) from information_schema.columns
 where table_schema='public' and table_name='criativo_render_recibo'
   and column_name in ('lufs_integrado','true_peak_dbtp','alvo_lufs','tolerancia_lufs');
select 'privilegio_publico=' || count(*) from information_schema.role_table_grants
 where table_schema='public' and table_name like 'criativo_render_%'
   and grantee in ('anon','authenticated','PUBLIC');
select 'delete_do_service_role=' || count(*) from information_schema.role_table_grants
 where table_schema='public' and table_name like 'criativo_render_%'
   and grantee='service_role' and privilege_type in ('DELETE','TRUNCATE');
select 'v11_01_02_intactas=' || count(*) from pg_tables
 where schemaname='public' and tablename like 'criativo_%'
   and tablename not like 'criativo_render_%';
SQL
```

Esperado, exatamente:

```
tabelas=5
rls_forcada=5
policies=0
funcoes=9
gatilhos=7
medidas_audio=4
privilegio_publico=0
delete_do_service_role=0
v11_01_02_intactas=21
```

Rode também o preflight de novo: ele deve agora sair `1`, acusando as 5 tabelas
e os 7 gatilhos como preexistentes. Se ele ainda sair `0`, a migration não entrou.

---

## 6. Reverter

```bash
psql "postgresql://USUARIO@HOST:PORTA/BANCO" \
     -X -v ON_ERROR_STOP=1 \
     -f supabase/migrations/v11_03_rollback.sql
```

⚠️ **Exporte antes se houver linha.** Logo depois de aplicar não há; se algum job
já rodou, a trilha e os recibos **não são reconstruíveis**:

```bash
psql "postgresql://USUARIO@HOST:PORTA/BANCO" -X <<'SQL'
\copy public.criativo_render_transicao TO 'transicao.csv' CSV HEADER
\copy public.criativo_render_recibo    TO 'recibo.csv'    CSV HEADER
\copy public.criativo_render_artefato  TO 'artefato.csv'  CSV HEADER
\copy public.criativo_render_validacao TO 'validacao.csv' CSV HEADER
\copy public.criativo_render_job       TO 'job.csv'       CSV HEADER
SQL
```

O rollback é transacional e verifica, ao final, que sobrou zero tabela, zero das
**nove** funções, e que **as 21 tabelas da v11_01/02 continuam existindo por
nome**. Sucesso é esta linha:

```
NOTICE:  v11_03_rollback OK: execucao removida, as 21 tabelas da v11_01/02 intactas (por nome).
```

Se ele **abortar**, nada foi revertido — é `begin/commit`, não meia-reversão.
Leia a mensagem: ela diz qual função sobrou ou qual tabela da v11_01/02 sumiu.

### 6.1 Se a base encolheu DE PROPÓSITO (achado A2)

A conferência das 21 tabelas é um **canário**, não um pré-requisito: medido em
cluster descartável por três caminhos independentes — `pg_constraint` (FK),
`pg_depend` e `pg_proc.prosrc` —, **nenhum** objeto da v11_03 depende de tabela
da v11_01/02. O rollback dropa 5 tabelas, 9 funções e 7 gatilhos que são todos
dele.

Consequência prática: se uma `v11_04` futura **aposentar** legitimamente uma das
21 (`drop table public.criativo_pacote cascade`), o rollback aborta com

```
ERROR:  v11_03_rollback: tabela(s) da v11_01/02 sumiram: criativo_pacote. ...
```

e sem escape a v11_03 ficaria **irreversível** justamente quando reverter é o que
se precisa. O escape é explícito, tem um único token e fica no log:

```bash
psql "postgresql://USUARIO@HOST:PORTA/BANCO" \
     -X -v ON_ERROR_STOP=1 \
     -v v11_03_base_encolhida=confirmo \
     -f supabase/migrations/v11_03_rollback.sql
```

Saída esperada (o `WARNING` é o registro de auditoria do gesto):

```
WARNING:  v11_03_rollback: ESCAPE ACIONADO (-v v11_03_base_encolhida=confirmo). Tabela(s) da v11_01/02 ausente(s): criativo_pacote. ...
NOTICE:  v11_03_rollback OK: execucao removida; 1 das 21 tabelas da v11_01/02 estavam ausentes e o escape foi aceito.
```

⚠️ **Use isto só quando você sabe por que a tabela sumiu.** Qualquer token
diferente de `confirmo` (um `-v v11_03_base_encolhida=1` às pressas, por exemplo)
**aborta** dizendo o token esperado — um typo não é consentimento. E se você não
aposentou nada de propósito, o canário está certo: **esta é a base errada, ou um
restore parcial.** Não force; descubra qual banco é esse.

---

## 7. Critério de decisão para reverter

**Reverta imediatamente se:**

- a `NOTICE` de sucesso da aplicação não apareceu — não tente corrigir por cima;
- qualquer número do passo 5 divergir do esperado;
- o `service_role` não consegue ler ou escrever nas 5 tabelas (sintoma clássico
  de `BYPASSRLS` ausente: `select` devolve zero linhas **sem erro**);
- algum consumidor existente das v11_01/v11_02 quebrou — a v11_03 não deveria
  poder causar isso, e se causou, a premissa estava errada;
- apareceu `policy` em qualquer `criativo_render_*` (alguém aplicou outra coisa
  junto).

**NÃO reverta por:**

- fila vazia ou nenhum job aparecendo: a v11_03 é schema, não é executor. Sem
  worker escrevendo, tabela vazia é o estado correto;
- lentidão de consulta nas tabelas novas com zero linha.

**Ordem em caso de reversão:** exportar CSVs (passo 6) → rodar o rollback →
conferir os números do passo 5 outra vez (deve dar `tabelas=0`, `funcoes=0`,
`v11_01_02_intactas=21`) → só então decidir se restaura o backup. **O backup do
passo 2 é a última linha de defesa, não a primeira:** restaurá-lo desfaz também
tudo que aconteceu no banco depois da aplicação.

---

## 8. O que este pacote não cobre

- **Janela e comunicação.** A migration não pega lock de escrita em tabela
  povoada (as 5 são novas), mas isso não substitui avisar quem opera.
- **O executor.** A v11_03 dá dono, prazo e recibo ao render; ela não resolve o
  gap G4 (execução fire-and-forget em função serverless). Aplicar a v11_03 não
  faz nada começar a rodar.
- **Aplicação.** Nada aqui foi rodado contra banco real; o pacote inteiro é
  roteiro, e cada passo continua sendo um gesto humano.

Fora do escopo já **não** está o README: a tabela de estado da série v11_03 em
`supabase/migrations/README.md` dizia "129 provas" e foi corrigida nesta rodada
para os números medidos em 02/09/2026 — **166** no ciclo, **30** no
`v11_03-provar-preflight.sh`, **12** no `v11_03-provar-plano.sh` (achado A4-ii).
