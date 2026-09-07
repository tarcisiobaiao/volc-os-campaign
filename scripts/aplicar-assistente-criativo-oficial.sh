#!/usr/bin/env bash
# Janela oficial do Assistente Criativo Meta: v11_05 + v11_06 + v11_07.
#
# NÃO é um aplicador genérico de migrations. Ele conhece TRÊS arquivos, confere
# o sha256 de cada um contra o manifesto antes de abrir transação, e recusa
# qualquer coisa fora dessa lista. `supabase db push` — ou um glob sobre
# supabase/migrations — aplicaria a fila inteira, que não é o que foi autorizado.
#
# ## Acesso
#
# Este script NÃO carrega credencial e NÃO lê .env. Ele exige `DATABASE_URL` no
# ambiente de quem executa:
#
#     export DATABASE_URL='postgresql://...'      # fora do repositório, fora do chat
#     ./scripts/aplicar-assistente-criativo-oficial.sh --conferir   # só leitura
#     ./scripts/aplicar-assistente-criativo-oficial.sh --aplicar
#
# O host oficial não publica 5432/6543 na internet; a conexão real depende do
# runbook privado de infraestrutura (túnel ou execução no próprio host). Isso é
# provisionamento do operador, nunca um segredo pedido no chat.
#
# ## O que ele nunca faz
#
# Não roda rollback, não faz backup/restore, não altera credencial, não aplica
# nada além dos três arquivos, e não imprime a URL de conexão em lugar nenhum.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIG="$RAIZ/supabase/migrations"
HOST_OFICIAL="database.agenciavolc.com.br"

# sha256 do manifesto CP3. Divergiu, para: o arquivo mudou depois de provado.
declare -a ORDEM=(
  "v11_05_criativo_agente_meta.sql:73bbe1f5f7ed1f6f83a11858b4ff6f195cf5784c897f9725b763f63de88130a9"
  "v11_06_criativo_agente_endurecimento.sql:cfddb4e8aa0f8d2286974c70b66a5e9b98877b455cca7054e5e7c9cfe773c233"
  "v11_07_criativo_agente_ponte_estudio.sql:594d7fa28e6d9ac9e105af8e53494788dce671115f63953f6bc5c6c6c01a192c"
)

MODO="${1:---conferir}"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERRO: DATABASE_URL não está no ambiente." >&2
  echo "Provisione o acesso SQL localmente e exporte a variável antes de rodar." >&2
  exit 2
fi

# A URL nunca é ecoada. Só o host, para provar que o destino é o oficial.
host_da_url() {
  DATABASE_URL="$DATABASE_URL" python3 - <<'PY'
import os, urllib.parse
print(urllib.parse.urlsplit(os.environ["DATABASE_URL"]).hostname or "")
PY
}

HOST="$(host_da_url)"
case "$HOST" in
  "$HOST_OFICIAL") : ;;
  localhost|127.0.0.1)
    echo "AVISO: destino local ($HOST). Use isto só para ensaiar o roteiro." >&2
    ;;
  *.supabase.co)
    echo "ERRO: *.supabase.co não é destino válido deste projeto." >&2
    exit 3
    ;;
  *)
    echo "ERRO: host '$HOST' não é o Supabase oficial nem um ensaio local." >&2
    exit 3
    ;;
esac

psql_() { psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -X -q "$@"; }

echo "── destino: $HOST"
echo "── 1. conferindo os hashes dos três arquivos"
for entrada in "${ORDEM[@]}"; do
  arquivo="${entrada%%:*}"
  esperado="${entrada##*:}"
  medido="$(shasum -a 256 "$MIG/$arquivo" | cut -d' ' -f1)"
  if [ "$medido" != "$esperado" ]; then
    echo "ERRO: $arquivo mudou desde a prova (sha256 $medido)." >&2
    exit 4
  fi
  echo "   OK  $arquivo"
done

echo "── 2. catálogo REAL antes de qualquer escrita"
psql_ -c "
select
  c.relname                                            as tabela,
  c.relrowsecurity                                     as rls,
  c.relforcerowsecurity                                as rls_forcada,
  (select count(*) from pg_policies p
     where p.schemaname='public' and p.tablename=c.relname) as policies,
  pg_catalog.array_to_string(c.relacl, E'\n')          as acl
from pg_class c
join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relkind='r'
  and c.relname in ('criativo_agente_operacao','criativo_agente_run',
                    'criativo_agente_decisao','criativo_agente_peca_job',
                    'criativo_job')
order by 1;
"

EXISTE_05="$(psql_ -tAc "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname in ('criativo_agente_operacao','criativo_agente_run','criativo_agente_decisao');")"
EXISTE_JOB="$(psql_ -tAc "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname='criativo_job';")"

# Quantas das CINCO invariantes da v11_06 já valem. É a mesma lista que a
# verificação embutida da própria migration levanta, e ela existe aqui porque
# reaplicar a v11_06 DEPOIS da v11_07 falha: a ponte cria FKs compostas que
# dependem das chaves únicas que a v11_06 derruba e recria, e o `drop` bate em
# "other objects depend on it". O ensaio em cluster descartável pegou isso.
V11_06_OK="$(psql_ -tAc "
select
  (select count(*) from information_schema.columns
     where table_schema='public' and table_name='criativo_agente_run' and column_name='claimed_at')
+ (select count(*) from pg_constraint
     where conrelid='public.criativo_agente_run'::regclass
       and conname='criativo_agente_run_status_ck'
       and pg_get_constraintdef(oid) like '%QUEUED%')
+ (select case when count(*)=0 then 1 else 0 end from pg_policies
     where schemaname='public' and tablename like 'criativo_agente%')
+ (select case when count(*)=0 then 1 else 0 end from information_schema.role_table_grants
     where table_schema='public' and table_name in
       ('criativo_agente_operacao','criativo_agente_run','criativo_agente_decisao')
       and grantee in ('anon','authenticated','PUBLIC'))
+ (select case when count(*)=3 then 1 else 0 end from pg_constraint
     where conname in ('criativo_agente_run_operacao_dono_fk',
                       'criativo_agente_decisao_operacao_dono_fk',
                       'criativo_agente_decisao_run_dono_fk'));
" 2>/dev/null || echo 0)"

EXISTE_07="$(psql_ -tAc "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname='criativo_agente_peca_job';")"

echo "── tabelas da v11_05 presentes: $EXISTE_05 de 3"
echo "── invariantes da v11_06 satisfeitas: $V11_06_OK de 5"
echo "── ponte da v11_07 presente: $EXISTE_07 de 1"
echo "── public.criativo_job (pré-requisito da v11_07): $EXISTE_JOB de 1"

if [ "$EXISTE_JOB" != "1" ]; then
  echo "ERRO: a v11_07 depende de public.criativo_job (v11_01) e ela não está lá." >&2
  exit 5
fi

if [ "$EXISTE_05" != "0" ] && [ "$EXISTE_05" != "3" ]; then
  echo "ERRO: estado parcial da v11_05 ($EXISTE_05 de 3). Pare e decida com o operador." >&2
  exit 5
fi

if [ "$EXISTE_05" = "3" ]; then
  LINHAS="$(psql_ -tAc "select coalesce((select count(*) from public.criativo_agente_operacao),0);")"
  echo "── a v11_05 já está aplicada; operações existentes: $LINHAS"
  echo "   (a v11_05 NÃO será reaplicada: o add constraint da linha 46 não tem guarda)"
fi

if [ "$MODO" != "--aplicar" ]; then
  echo
  echo "MODO CONFERIR: nada foi escrito. Rode com --aplicar para abrir a janela."
  exit 0
fi

if [ "$V11_06_OK" != "0" ] && [ "$V11_06_OK" != "5" ]; then
  echo "ERRO: a v11_06 está PELA METADE ($V11_06_OK de 5 invariantes)." >&2
  echo "A porta pode estar aberta. Pare e decida com o operador antes de escrever." >&2
  exit 5
fi

echo "── 3. aplicando"
# Cada arquivo abre e fecha a própria transação (`begin;`/`commit;`), então
# `psql -1` só produziria "there is already a transaction in progress".
if [ "$EXISTE_05" = "0" ]; then
  echo "   v11_05 (criação)"
  psql_ -f "$MIG/v11_05_criativo_agente_meta.sql"
else
  echo "   v11_05 PULADA (já aplicada; o add constraint da linha 46 não tem guarda)"
fi

# A v11_06 fecha a porta que a v11_05 abre. Entre uma e outra existe uma janela
# em que `authenticated` pode fabricar run/decisão via PostgREST — por isso, numa
# instalação nova, as duas rodam na mesma execução, sem pausa no meio.
if [ "$V11_06_OK" = "5" ]; then
  echo "   v11_06 PULADA (as 5 invariantes já valem)"
else
  echo "   v11_06 (endurecimento)"
  psql_ -f "$MIG/v11_06_criativo_agente_endurecimento.sql"
fi

echo "   v11_07 (ponte peça→job)"
psql_ -f "$MIG/v11_07_criativo_agente_ponte_estudio.sql"

echo "── 4. read-back do catálogo"
psql_ -c "
select c.relname, c.relrowsecurity as rls, c.relforcerowsecurity as forcada,
       (select count(*) from pg_policies p where p.schemaname='public' and p.tablename=c.relname) as policies,
       pg_catalog.array_to_string(c.relacl, E'\n') as acl
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relkind='r'
  and c.relname like 'criativo_agente%' order by 1;
"
psql_ -c "
select conrelid::regclass as tabela, conname, pg_get_constraintdef(oid) as definicao
from pg_constraint
where connamespace='public'::regnamespace
  and conrelid::regclass::text like 'criativo_agente%'
order by 1,2;
"
echo "── 5. a porta continua fechada para anon/authenticated?"
psql_ -c "
select grantee, table_name, string_agg(privilege_type, ',' order by privilege_type) as privilegios
from information_schema.role_table_grants
where table_schema='public' and table_name like 'criativo_agente%'
group by 1,2 order by 1,2;
"

echo "── 6. NOTIFY pgrst"
psql_ -c "notify pgrst, 'reload schema';"

echo
echo "JANELA CONCLUÍDA. Registre no ledger supabase/migrations/README.md:"
echo "  arquivo, sha256, quando, ambiente, executor e o read-back acima."
