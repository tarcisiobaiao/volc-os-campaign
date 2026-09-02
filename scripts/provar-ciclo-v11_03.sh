#!/usr/bin/env bash
# O ciclo da v11_03 num Postgres descartável: aplicar -> operar -> reverter ->
# reaplicar, com prova de ESTRUTURA, SEGURANÇA e COMPORTAMENTO.
#
# ## Por que um script
# Um rollback só existe se alguém o executa. Este roda o ciclo inteiro do zero, a
# cada execução, num cluster que nasce e morre aqui. Não toca em nada fora de
# /tmp e NUNCA fala com o banco de produção.
#
# ## O que ele prova
# As sete invariantes do contrato da bancada, agora no banco:
#   1. transições válidas passam, inválidas são recusadas;
#   2. lease NÃO é renovado por transição;
#   3. dono é obrigatório em execução e não troca no meio;
#   4. `rendered` exige recibo e é terminal;
#   5. só `failed`/`cancelled` são retomáveis, com retry_n em ordem;
#   6. tenant entra na identidade; retomada cruzada é recusada;
#   7. artefato imutável depois de `rendered`; bytes/hash NOT NULL e com forma;
#   8. mensagem de erro não persiste caminho, stack nem drive do Windows;
#   9. claim concorrente com FOR UPDATE SKIP LOCKED não entrega o mesmo job;
#  10. RLS forçada, zero policies, anon/authenticated sem privilégio;
#  11. a trilha de transições é append-only.
set -euo pipefail

for b in initdb pg_ctl psql pg_dump; do
  command -v "$b" >/dev/null || { echo "falta $b no PATH"; exit 2; }
done

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
D="$(mktemp -d "${TMPDIR:-/tmp}/v1103.XXXXXX")"
limpar() { pg_ctl -D "$D/d" -m immediate stop >/dev/null 2>&1 || true; rm -rf "$D"; }
trap limpar EXIT

# ⚠️ `LC_ALL=C` não é enfeite. Sem ela, o Postgres 16 do Homebrew no macOS morre
# no arranque com "postmaster became multithreaded during startup" — a própria
# dica do log manda definir a variável. Sem isto o script não sobe cluster nenhum.
export LC_ALL=C LANG=C

echo "cluster descartável em $D"
mkdir -p "$D/s"
initdb -D "$D/d" -U postgres --encoding=UTF8 --locale=C >/dev/null 2>&1
pg_ctl -D "$D/d" -l "$D/pg.log" -o "-k $D/s -h ''" -w start >/dev/null 2>&1
export PGHOST="$D/s" PGUSER=postgres PGDATABASE=postgres

q() { psql -v ON_ERROR_STOP=1 -X -q -At -c "$1"; }
f() { psql -v ON_ERROR_STOP=1 -X -q -f "$1" >/dev/null; }

# ── papéis e o ACL padrão QUEBRADO de produção, reproduzido ─────────────────
#
# ⚠️ ACHADO #10. `service_role` nascia aqui SEM `BYPASSRLS`, e isso fazia o
# cluster de prova ser mais seguro que o banco real: com RLS forçada e zero
# policies, o papel operacional ficava trancado, lia zero linhas e não conseguia
# inserir. As provas de segurança passavam contra um banco que não é o nosso.
#
# Medido no Supabase oficial em 2026-08-29, só no catálogo (`pg_roles`), sem
# tocar em dado e sem aplicar nada: anon=f, authenticated=f, service_role=t na
# coluna `rolbypassrls`. Reproduzimos essa premissa aqui.
q "create role anon nologin; create role authenticated nologin;" >/dev/null
q "create role service_role nologin bypassrls;" >/dev/null
# Mesmo GRANT do service_role, mas SEM bypassrls: é o papel que separa
# "a RLS bloqueou" (silencioso, zero linhas) de "o grant bloqueou" (42501).
q "create role prova_sem_bypass nologin;" >/dev/null
# ⚠️ Isto é o achado H, reproduzido de propósito: sem ele o teste de segurança
# passaria por sorte, testando um banco mais seguro que o real.
q "alter default privileges in schema public grant all on tables to anon, authenticated, service_role;" >/dev/null

ok=0; falhou=0
prova() { # nome, comando-que-deve-passar
  if eval "$2" >/dev/null 2>&1; then echo "  ok   $1"; ok=$((ok+1));
  else echo "  FALHOU  $1"; falhou=$((falhou+1)); fi
}
recusa() { # nome, comando-que-deve-FALHAR
  if eval "$2" >/dev/null 2>&1; then echo "  FALHOU  $1 (foi aceito e devia ser recusado)"; falhou=$((falhou+1));
  else echo "  ok   $1"; ok=$((ok+1)); fi
}

# ── as 21 tabelas anteriores, porque o rollback promete não tocá-las ────────
f "$RAIZ/supabase/migrations/v11_01_estudio_criativo.sql"
f "$RAIZ/supabase/migrations/v11_02_parque_criativo.sql"

echo; echo "DEGRAU 1 — aplicar a v11_03"
f "$RAIZ/supabase/migrations/v11_03_execucao_criativa.sql"
prova "5 tabelas criadas" "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_render_%'\")\" = 5 ]"
prova "RLS forçada nas 5" "[ \"\$(q \"select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname like 'criativo_render_%' and c.relkind='r' and c.relrowsecurity and c.relforcerowsecurity\")\" = 5 ]"
prova "zero policies" "[ \"\$(q \"select count(*) from pg_policies where schemaname='public' and tablename like 'criativo_render_%'\")\" = 0 ]"
prova "anon/authenticated sem privilégio" "[ \"\$(q \"select count(*) from information_schema.role_table_grants where table_schema='public' and table_name like 'criativo_render_%' and grantee in ('anon','authenticated','PUBLIC')\")\" = 0 ]"
prova "service_role sem DELETE" "[ \"\$(q \"select count(*) from information_schema.role_table_grants where table_schema='public' and table_name like 'criativo_render_%' and grantee='service_role' and privilege_type in ('DELETE','TRUNCATE')\")\" = 0 ]"
prova "trilha não é atualizável nem pelo service_role" "[ \"\$(q \"select count(*) from information_schema.role_table_grants where table_schema='public' and table_name='criativo_render_transicao' and grantee='service_role' and privilege_type='UPDATE'\")\" = 0 ]"

echo; echo "DEGRAU 2 — comportamento"
# ⚠️ Em SQL e não em bash. A primeira versão destas provas vivia dentro de `eval`
# com aspas em três níveis, a primeira inserção falhava por quoting e TODAS as
# seguintes cascateavam. Um arranjo de prova que falha por si mesmo não mede nada.
SAIDA="$(psql -X -q -v ON_ERROR_STOP=1 -f "$RAIZ/scripts/provas-v11_03.sql" 2>&1)"
echo "$SAIDA" | grep -vE '^\s*$'
ok=$((ok + $(echo "$SAIDA" | grep -c '^  ok' || true)))
falhou=$((falhou + $(echo "$SAIDA" | grep -c '^FALHOU' || true)))

echo; echo "DEGRAU 2b — segurança sob os PAPÉIS, executando de verdade"
# ⚠️ ACHADO #10. Os degraus de segurança acima leem catálogo: contam grants e
# conferem `relrowsecurity`. Isto aqui EXECUTA select/insert/update/delete/
# truncate sob anon, authenticated, o papel privilegiado com BYPASSRLS e um papel
# com o mesmo grant sem bypass — e confere SQLSTATE específico em cada recusa,
# separando "grant bloqueou" de "RLS bloqueou" de "gatilho recusou" de "a prova
# está quebrada".
q "grant select, insert, update on public.criativo_render_job to prova_sem_bypass" >/dev/null
PAPEIS="$(psql -X -q -v ON_ERROR_STOP=1 -f "$RAIZ/scripts/provas-papeis-v11_03.sql" 2>&1)"
echo "$PAPEIS" | grep -vE '^\s*$'
ok=$((ok + $(echo "$PAPEIS" | grep -c '^  ok' || true)))
falhou=$((falhou + $(echo "$PAPEIS" | grep -c '^FALHOU' || true)))

# claim concorrente: isto SÓ dá para provar com duas sessões de verdade.
q "insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed) values ('tenant-A','c1','{}'::jsonb,'m',7),('tenant-A','c2','{}'::jsonb,'m',7)" >/dev/null
CLAIM="update public.criativo_render_job set estado='claimed', owner='X', lease_ate=now()+interval '60s', batimento_em=now(), tentativa=1 where id = (select id from public.criativo_render_job where estado='queued' order by criado_em for update skip locked limit 1) returning idempotency_key"
A=$(psql -X -q -At -c "$CLAIM" 2>/dev/null | head -1)
B=$(psql -X -q -At -c "$CLAIM" 2>/dev/null | head -1)
if [ -n "$A" ] && [ -n "$B" ] && [ "$A" != "$B" ]; then
  echo "  ok   SKIP LOCKED: dois claims, dois jobs distintos ($A / $B)"; ok=$((ok+1))
else
  echo "FALHOU  SKIP LOCKED: A=$A B=$B"; falhou=$((falhou+1))
fi

echo; echo "DEGRAU 3 — reverter"
f "$RAIZ/supabase/migrations/v11_03_rollback.sql"
prova "as 5 tabelas sumiram" "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_render_%'\")\" = 0 ]"
prova "as 21 da v11_01/02 continuam de pé" "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_%' and tablename not like 'criativo_render_%'\")\" = 21 ]"

echo; echo "DEGRAU 4 — reaplicar"
f "$RAIZ/supabase/migrations/v11_03_execucao_criativa.sql"
prova "5 tabelas de novo" "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_render_%'\")\" = 5 ]"
prova "RLS forçada de novo" "[ \"\$(q \"select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname like 'criativo_render_%' and c.relkind='r' and c.relrowsecurity and c.relforcerowsecurity\")\" = 5 ]"

# ══════════════════════════════════════════════════════════════════════════
# DEGRAU 5 — contraprova do DEFEITO D2: a verificação embutida era frouxa
# ══════════════════════════════════════════════════════════════════════════
# A migration cria SETE gatilhos e a sua própria verificação aceitava `>= 6`,
# sozinha entre cinco conferências que usam igualdade exata. Um gatilho perdido
# numa edição futura sairia verde com a mensagem "v11_03 OK".
#
# Estas provas não leem o número no arquivo: elas EXTRAEM o bloco `do $verifica$`
# do .sql que acabou de ser aplicado e o executam contra o banco — primeiro
# íntegro, depois com um gatilho removido de propósito, depois recomposto.
# Contra o `n_trg < 6` antigo, a prova do meio FALHA: o bloco não acusa nada.

BLOCO="$D/verifica-migration.sql"
awk '/^do \$verifica\$$/,/^\$verifica\$;$/' \
    "$RAIZ/supabase/migrations/v11_03_execucao_criativa.sql" > "$BLOCO"
prova "o bloco de verificação foi extraído do .sql (não reescrito aqui)" \
      "[ \"\$(grep -c 'raise exception' \"\$BLOCO\")\" -ge 5 ]"

roda() { psql -v ON_ERROR_STOP=1 -X -q -f "$1" >/dev/null 2>&1; }

prova "a verificação da migration passa com os 7 gatilhos de pé" "roda \"\$BLOCO\""
q "drop trigger criativo_render_transicao_append_only_tg on public.criativo_render_transicao" >/dev/null
recusa "a verificação da migration ACUSA quando falta 1 dos 7 gatilhos" "roda \"\$BLOCO\""
q "create trigger criativo_render_transicao_append_only_tg before update or delete on public.criativo_render_transicao for each row execute function public.criativo_render_transicao_append_only()" >/dev/null
prova "gatilho recomposto, verificação verde outra vez" "roda \"\$BLOCO\""

# ══════════════════════════════════════════════════════════════════════════
# DEGRAU 6 — contraprova do DEFEITO D1: o rollback era cego a 2 das 9 funções
# ══════════════════════════════════════════════════════════════════════════
# A conferência final do rollback contava `pg_proc` por `proname like
# 'criativo_render_%'`. Duas das nove funções criadas pela v11_03 —
# `criativo_storage_chave` e `criativo_storage_chave_valida` — não casam com esse
# prefixo. Os DROPs delas existem, então o ciclo feliz nunca acusou nada; mas um
# leftover DELAS passaria como reversão bem-sucedida, e um leftover de função é
# exatamente o que faz a reaplicação seguinte encontrar assinatura antiga.
#
# Aqui um leftover é FABRICADO: uma sobrecarga de 5 argumentos de
# `criativo_storage_chave`, que o `drop function ...(text, uuid, text, text)` do
# rollback não alcança. Contra a contagem antiga o rollback sai verde com ela de
# pé — e é essa a contraprova vermelha.

ROLLBACK="$RAIZ/supabase/migrations/v11_03_rollback.sql"
q "create function public.criativo_storage_chave(text, uuid, text, text, text)
   returns text language sql immutable as \$f\$ select 'leftover' \$f\$" >/dev/null
prova "o leftover fabricado está de pé antes do rollback" \
  "[ \"\$(q \"select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname='criativo_storage_chave'\")\" = 2 ]"
recusa "o rollback ACUSA função sobrevivente fora do prefixo criativo_render_" "roda \"\$ROLLBACK\""
prova "rollback abortado é rollback atômico: as 5 tabelas continuam de pé" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_render_%'\")\" = 5 ]"
q "drop function public.criativo_storage_chave(text, uuid, text, text, text)" >/dev/null
prova "sem leftover, o rollback conclui" "roda \"\$ROLLBACK\""
prova "as NOVE funções da v11_03 sumiram, não só as sete do prefixo" \
  "[ \"\$(q \"select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and (p.proname like 'criativo_render_%' or p.proname like 'criativo_storage_chave%')\")\" = 0 ]"

# ══════════════════════════════════════════════════════════════════════════
# DEGRAU 7 — contraprova do DEFEITO D3: o rollback estava preso ao número 21
# ══════════════════════════════════════════════════════════════════════════
# `if n_v11 <> 21 then raise exception` acopla o rollback da v11_03 a uma
# contagem que qualquer migration POSTERIOR muda. O efeito é invertido: uma
# v11_04 legítima não quebraria a v11_03 — quebraria a capacidade de REVERTER a
# v11_03, justamente na hora em que reverter é o que se precisa. E o número não
# expressa a intenção: 21 tabelas com uma trocada por outra também dá 21.
#
# Duas contraprovas, vermelhas em direções opostas contra o código antigo:
#   (a) com uma tabela criativo_* a mais, o rollback DEVE concluir;
#   (b) com uma das 21 renomeada — contagem ainda 21 —, ele DEVE acusar.

f "$RAIZ/supabase/migrations/v11_03_execucao_criativa.sql"
q "create table public.criativo_futuro_v11_04 (id integer)" >/dev/null
prova "(a) uma v11_04 futura não impede reverter a v11_03" "roda \"\$ROLLBACK\""
prova "(a) e o rollback não encostou na tabela da v11_04" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename='criativo_futuro_v11_04'\")\" = 1 ]"
q "drop table public.criativo_futuro_v11_04" >/dev/null

f "$RAIZ/supabase/migrations/v11_03_execucao_criativa.sql"
q "alter table public.criativo_entrega rename to criativo_entrega_renomeada" >/dev/null
prova "(b) a contagem continua 21 mesmo com a tabela trocada" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_%' and tablename not like 'criativo_render_%'\")\" = 21 ]"
recusa "(b) o rollback ACUSA a v11_01/02 mutilada apesar da contagem bater" "roda \"\$ROLLBACK\""
q "alter table public.criativo_entrega_renomeada rename to criativo_entrega" >/dev/null
prova "(b) com as 21 de volta pelo NOME, o rollback conclui" "roda \"\$ROLLBACK\""

# ══════════════════════════════════════════════════════════════════════════
# DEGRAU 7b — ACHADO A2: a promessa do cabeçalho era meio-falsa
# ══════════════════════════════════════════════════════════════════════════
# O cabeçalho do rollback prometia "uma v11_04 futura não impede reverter esta".
# A contraprova (a) acima só exercita a v11_04 que ACRESCENTA tabela. Uma v11_04
# que APOSENTA uma das 21 — `drop table public.criativo_pacote cascade` — fazia o
# rollback abortar em "tabela(s) da v11_01/02 sumiram", tornando a v11_03
# IRREVERSÍVEL justamente quando reverter é o que se precisa.
#
# O fato que decide, medido neste mesmo cluster (ver o cabeçalho do .sql): o
# rollback não tem FK, nem pg_depend, nem citação em prosrc apontando para as 21.
# Ele não PRECISA delas. A conferência é canário, não pré-requisito — então o
# default continua abortando e existe uma chave explícita.
#
# Três contraprovas, e a do meio é a vermelha contra o rollback anterior:
#   (c) base encolhida, sem a chave → ABORTA (comportamento preservado);
#   (d) base encolhida, com a chave → CONCLUI (era impossível antes);
#   (e) chave com token errado → ABORTA (typo não é consentimento).
echo; echo "DEGRAU 7b — contraprova do ACHADO A2: v11_04 que APOSENTA uma tabela"
roda_v() { psql -v ON_ERROR_STOP=1 -v "$2" -X -q -f "$1" >/dev/null 2>&1; }

f "$RAIZ/supabase/migrations/v11_03_execucao_criativa.sql"
# O DDL exato da tabela é guardado antes, para recompor a base ao fim do degrau:
# um degrau de prova que deixa a bancada mutilada contamina os degraus seguintes.
pg_dump --schema-only --no-owner --no-privileges -t public.criativo_pacote > "$D/criativo_pacote.sql"
prova "(A2) o DDL de criativo_pacote foi capturado para recompor a base" \
  "[ \"\$(grep -c 'CREATE TABLE public.criativo_pacote' \"\$D/criativo_pacote.sql\")\" -ge 1 ]"
q "drop table public.criativo_pacote cascade" >/dev/null
prova "(A2) a v11_04 hipotética de fato aposentou criativo_pacote" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename='criativo_pacote'\")\" = 0 ]"

recusa "(c) sem a chave, a base encolhida ABORTA o rollback (default preservado)" "roda \"\$ROLLBACK\""
prova "(c) e o aborto é atômico: as 5 tabelas da v11_03 continuam de pé" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_render_%'\")\" = 5 ]"

recusa "(e) token errado não é consentimento: -v v11_03_base_encolhida=1 ABORTA" \
  "roda_v \"\$ROLLBACK\" v11_03_base_encolhida=1"
prova "(e) e continua atômico: as 5 tabelas seguem de pé" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_render_%'\")\" = 5 ]"

# ⚠️ ESTA é a linha vermelha contra o rollback anterior: lá ela abortava igual,
# porque não havia chave nenhuma, e a v11_03 ficava sem reversão possível.
#
# ⚠️ A saída vai para ARQUIVO, e o grep lê o arquivo. A primeira versão desta
# prova era `psql ... | grep -q`, e sob `pipefail` ela falhava por CORRIDA: o
# `grep -q` sai no primeiro casamento, fecha o cano, o psql toma SIGPIPE e o
# pipeline inteiro vira não-zero — o mesmo comando dando ok numa rodada e FALHOU
# na seguinte. Prova que depende de quem termina primeiro não mede nada.
# `set -e` está ligado: sem o `if`, um rollback que abortasse mataria o script
# em vez de virar a FALHA que esta prova existe para reportar.
if psql -X -q -v ON_ERROR_STOP=1 -v v11_03_base_encolhida=confirmo \
        -f "$ROLLBACK" > "$D/escape.txt" 2>&1; then saida_escape=0; else saida_escape=$?; fi
prova "(d) com a chave explícita, a v11_04 que aposenta NÃO impede reverter a v11_03" \
  "[ \"\$saida_escape\" = 0 ]"
prova "(d) o escape é AUDITÁVEL: o rollback grita WARNING nomeando a tabela ausente" \
  "grep -q 'ESCAPE ACIONADO' \"\$D/escape.txt\""
prova "(d) e o WARNING nomeia a tabela, não só o fato" \
  "grep -q 'ausente(s): criativo_pacote' \"\$D/escape.txt\""
prova "(d) e reverteu de verdade: zero tabelas criativo_render_*" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_render_%'\")\" = 0 ]"
prova "(d) e as NOVE funções sumiram junto" \
  "[ \"\$(q \"select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and (p.proname like 'criativo_render_%' or p.proname like 'criativo_storage_chave%')\")\" = 0 ]"

# a base volta inteira, para o DEGRAU 8 medir o que ele diz que mede
f "$D/criativo_pacote.sql"
prova "(A2) base recomposta: criativo_pacote de volta pelo DDL capturado" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename='criativo_pacote'\")\" = 1 ]"

# E o fato que justifica o escape, medido e não afirmado: nada da v11_03 depende
# das 21. Três leituras independentes, todas têm de dar zero.
f "$RAIZ/supabase/migrations/v11_03_execucao_criativa.sql"
prova "(A2) nenhuma FK sai da v11_03 para as tabelas da v11_01/02" \
  "[ \"\$(q \"select count(*) from pg_constraint con join pg_class cl on cl.oid=con.conrelid join pg_class cf on cf.oid=con.confrelid where con.contype='f' and cl.relname like 'criativo_render_%' and cf.relname not like 'criativo_render_%'\")\" = 0 ]"
prova "(A2) nenhum pg_depend liga objeto da v11_03 a tabela da v11_01/02" \
  "[ \"\$(q \"with v as (select c.oid from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname like 'criativo_render_%' union all select p.oid from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and (p.proname like 'criativo_render_%' or p.proname like 'criativo_storage_chave%')), b as (select c.oid from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r' and c.relname like 'criativo_%' and c.relname not like 'criativo_render_%') select count(*) from pg_depend d join b on b.oid=d.refobjid where d.objid in (select oid from v)\")\" = 0 ]"
prova "(A2) nenhum corpo das 9 funções cita uma das 21 tabelas" \
  "[ \"\$(q \"select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and (p.proname like 'criativo_render_%' or p.proname like 'criativo_storage_chave%') and exists (select 1 from pg_class c join pg_namespace n2 on n2.oid=c.relnamespace where n2.nspname='public' and c.relkind='r' and c.relname like 'criativo_%' and c.relname not like 'criativo_render_%' and p.prosrc ~ ('\\m' || c.relname || '\\M'))\")\" = 0 ]"
f "$ROLLBACK"

echo; echo "DEGRAU 8 — reaplicar, para o ciclo fechar aplicado"
f "$RAIZ/supabase/migrations/v11_03_execucao_criativa.sql"
prova "5 tabelas depois de todas as contraprovas" "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_render_%'\")\" = 5 ]"
prova "21 tabelas da v11_01/02 intactas depois de todas as contraprovas" "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_%' and tablename not like 'criativo_render_%'\")\" = 21 ]"

echo
echo "════════════════════════════════════════════════════════"
echo "  passaram $ok · falharam $falhou"
[ "$falhou" -eq 0 ] || exit 1
echo "  CICLO v11_03 COMPLETO: aplicar → operar → reverter → reaplicar"
