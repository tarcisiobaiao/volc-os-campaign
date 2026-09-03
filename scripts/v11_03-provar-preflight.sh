#!/usr/bin/env bash
# =============================================================================
# v11_03-provar-preflight.sh — o preflight se provando num cluster descartável
# =============================================================================
# `scripts/preflight-v11_03.sh` só vale se ele acusar quando há o que acusar.
# Este script cria um Postgres do zero em mktemp -d, leva-o por cinco estados e
# confere o VEREDITO e o código de saída em cada um. Não fala com banco nenhum
# de produção e não recebe DSN de fora.
#
# ⚠️ Duas conferências do preflight nasceram QUEBRADAS e foi este arranjo que as
# pegou: um `order by 1, 2` inválido e um `rolbypassrls::text` comparado com 't'
# quando o Postgres devolve 'true'. Ambas saíram como NAO CONFERIDO — que é
# exatamente o que fail-closed deve fazer com a própria falha.
set -uo pipefail
for b in initdb pg_ctl psql; do
  command -v "$b" >/dev/null || { echo "falta $b no PATH"; exit 2; }
done
export LC_ALL=C LANG=C
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
# O preflight sob prova vem por argumento (padrão: o versionado). É assim que a
# contraprova vermelha se faz sem editar o arquivo bom:
#
#   E="$(mktemp -d)"; mkdir -p "$E/scripts"
#   ln -s "$PWD/supabase" "$E/supabase"          # o preflight lê ../supabase/migrations
#   cp preflight-antigo.sh "$E/scripts/pf.sh"
#   bash scripts/v11_03-provar-preflight.sh "$E/scripts/pf.sh"
#
# ⚠️ O espelho não é capricho: o preflight deriva a raiz do repositório de
# `dirname $0/..`, então uma cópia solta em /tmp acha que a raiz é /tmp, não
# encontra os .sql do passo 0 e sai 2 em TODOS os estados — o que faria a
# contraprova parecer vermelha por outro motivo e não provaria nada.
#
# Medido nesta rodada, contra duas variantes que diferem do arquivo bom só na
# correção sob teste:
#   • sem a correção A1 → 23 passaram · 7 falharam, TODAS na seção F2, e a falha
#     é literalmente "VIEW ocupando o nome: esperava exit=1, veio 0";
#   • sem a correção A3 → 28 passaram · 2 falharam, ambas na seção D2.
PF="${1:-$RAIZ/scripts/preflight-v11_03.sh}"
[ -f "$PF" ] || { echo "não achei o preflight: $PF"; exit 2; }
echo "preflight sob prova: $PF"
D="$(mktemp -d "${TMPDIR:-/tmp}/pf1103.XXXXXX")"
trap 'pg_ctl -D "$D/d" -m immediate stop >/dev/null 2>&1; rm -rf "$D"' EXIT
mkdir -p "$D/s"
initdb -D "$D/d" -U postgres --encoding=UTF8 --locale=C >/dev/null 2>&1
pg_ctl -D "$D/d" -l "$D/pg.log" -o "-k $D/s -h ''" -w start >/dev/null 2>&1
DSN="postgresql://postgres@/postgres?host=$D/s"
p() { psql "$DSN" -X -q -v ON_ERROR_STOP=1 "$@" >/dev/null 2>&1; }

ok=0; falhou=0
espera() { # rótulo, saída-esperada, [argumento do preflight]
  local rot="$1" esp="$2"; shift 2
  bash "$PF" "$@" >"$D/saida.txt" 2>&1; local st=$?
  if [ "$st" = "$esp" ]; then echo "  ok   $rot (exit=$st)"; ok=$((ok+1));
  else echo "  FALHOU  $rot: esperava exit=$esp, veio $st"; sed 's/^/        /' "$D/saida.txt"; falhou=$((falhou+1)); fi
}
contem() { # rótulo, trecho
  if grep -qF "$2" "$D/saida.txt"; then echo "  ok   $1"; ok=$((ok+1));
  else echo "  FALHOU  $1: não achei \"$2\" na saída"; falhou=$((falhou+1)); fi
}

echo "A. sem DSN o preflight não adivinha alvo"
espera "sem argumento: sai 2 e explica" 2

echo; echo "B. DSN inalcançável: fail-closed, nunca sucesso"
espera "conexão recusada: sai 2" 2 "postgresql://postgres@127.0.0.1:59999/postgres"
contem "conexão recusada vira NAO CONFERIDO" "NAO CONFERIDO conexão"

echo; echo "C. banco cru, sem v11_01/02 e sem service_role"
espera "base ausente: sai != 0" 1 "$DSN"
contem "acusa as 21 tabelas ausentes" "faltam tabelas da v11_01/02"
contem "acusa service_role ausente" "o papel service_role NÃO EXISTE"

echo; echo "D. base pronta: o único estado em que APLICAR é defensável"
p -c "create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls"
p -f "$RAIZ/supabase/migrations/v11_01_estudio_criativo.sql"
p -f "$RAIZ/supabase/migrations/v11_02_parque_criativo.sql"
espera "premissas conferidas: sai 0" 0 "$DSN"
contem "veredito positivo" "VEREDITO: premissas conferidas"
contem "nada em aberto" "nao_conferido=0"

echo; echo "D2. ACHADO A3 — o read-only não pode depender do PGOPTIONS"
# O DSN pode trazer o seu próprio `options=`, e libpq então IGNORA o PGOPTIONS
# inteiro. Enquanto o read-only vinha só de PGOPTIONS, um DSN assim desligava a
# guarda em silêncio. Primeiro provamos que o DSN REALMENTE sobrepõe (senão o
# teste seguinte não mediria nada), depois que o preflight continua read-only.
DSN_OPT="$DSN&options=-c%20statement_timeout%3D1000"
medido="$(PGOPTIONS='-c default_transaction_read_only=on' \
          psql "$DSN_OPT" -X -At -c 'show default_transaction_read_only' 2>/dev/null)"
if [ "$medido" = "off" ]; then
  echo "  ok   o 'options=' do DSN de fato sobrepõe o PGOPTIONS (medido: off) — o teste abaixo não é vazio"; ok=$((ok+1))
else
  echo "  FALHOU  esperava 'off' com options= no DSN, veio '$medido': a premissa do A3 não se reproduz aqui"; falhou=$((falhou+1))
fi
espera "com options= no DSN, o preflight ainda conclui" 0 "$DSN_OPT"
contem "e a sessão continua read-only apesar do options=" "default_transaction_read_only=on (aplicado por SET"
# E a prova de que a garantia é da SESSÃO, não do ambiente: sem PGOPTIONS nenhum,
# uma escrita pelo mesmo caminho do preflight tem de ser recusada.
if env -u PGOPTIONS psql "$DSN_OPT" -X -q -v ON_ERROR_STOP=1 \
     -c 'set session characteristics as transaction read only' \
     -c 'create table public.escrita_que_nao_devia_passar (i int)' >/dev/null 2>&1; then
  echo "  FALHOU  o SET de sessão não impediu a escrita"; falhou=$((falhou+1))
  p -c "drop table if exists public.escrita_que_nao_devia_passar"
else
  echo "  ok   o SET de sessão recusa escrita mesmo com options= no DSN e sem PGOPTIONS"; ok=$((ok+1))
fi

echo; echo "E. função homônima com OUTRA assinatura"
p -c "create function public.criativo_storage_chave(text, text) returns text language sql immutable as \$f\$ select 'intrusa' \$f\$"
espera "sobrecarga intrusa: sai 1" 1 "$DSN"
contem "acusa a sobrecarga por assinatura" "função homônima com OUTRA assinatura: criativo_storage_chave(text, text)"
p -c "drop function public.criativo_storage_chave(text, text)"

echo; echo "F. service_role sem BYPASSRLS"
p -c "alter role service_role nobypassrls"
espera "papel sem bypass: sai 1" 1 "$DSN"
contem "acusa o papel sem BYPASSRLS" "service_role existe SEM BYPASSRLS"
p -c "alter role service_role bypassrls"

echo; echo "F2. ACHADO A1 — nome ocupado por relação que NÃO é tabela"
# ⚠️ CONTRAPROVA VERMELHA. Contra o preflight antigo esta seção falha inteira:
# ele perguntava a `pg_tables`, que só enxerga relkind 'r'/'p', e respondia
# "APTO  criativo_render_job não existe" com exit 0 — para em seguida a migration
# morrer em `ERROR: cannot create index on relation "criativo_render_job"`.
p -c "create view public.criativo_render_job as select 1 as id"
espera "VIEW ocupando o nome: sai 1" 1 "$DSN"
contem "acusa o nome ocupado, e diz que é VIEW" "criativo_render_job: o NOME está ocupado por uma VIEW"
p -c "drop view public.criativo_render_job"

p -c "create materialized view public.criativo_render_recibo as select 1 as id"
espera "MATERIALIZED VIEW ocupando o nome: sai 1" 1 "$DSN"
contem "acusa e diz que é MATERIALIZED VIEW" "criativo_render_recibo: o NOME está ocupado por uma MATERIALIZED VIEW"
p -c "drop materialized view public.criativo_render_recibo"

p -c "create sequence public.criativo_render_artefato"
espera "SEQUENCE ocupando o nome: sai 1" 1 "$DSN"
contem "acusa e diz que é SEQUENCE" "criativo_render_artefato: o NOME está ocupado por uma SEQUENCE"
p -c "drop sequence public.criativo_render_artefato"

# O mesmo buraco existia do lado das 21 tabelas da base: um nome da v11_01/02
# ocupado por VIEW era relatado como "faltam tabelas", que manda aplicar a
# v11_01/02 de novo — conselho errado para o defeito real.
p -c "alter table public.criativo_pacote rename to criativo_pacote_guardada"
p -c "create view public.criativo_pacote as select 1 as id"
espera "nome da v11_01/02 ocupado por VIEW: sai 1" 1 "$DSN"
contem "separa 'não é tabela' de 'não existe'" "nome da v11_01/02 ocupado por relação que NÃO é tabela: criativo_pacote(VIEW)"
p -c "drop view public.criativo_pacote"
p -c "alter table public.criativo_pacote_guardada rename to criativo_pacote"
espera "base recomposta: volta a sair 0" 0 "$DSN"

echo; echo "G. com a v11_03 já aplicada, aplicar de novo é bloqueado"
p -f "$RAIZ/supabase/migrations/v11_03_execucao_criativa.sql"
espera "v11_03 já presente: sai 1" 1 "$DSN"
contem "acusa tabela preexistente" "criativo_render_job JÁ EXISTE"
contem "acusa gatilhos preexistentes" "gatilhos criativo_render_* já existem"

echo; echo "H. e o preflight não escreveu nada em lugar nenhum"
n="$(psql "$DSN" -X -At -c "select count(*) from public.criativo_render_job" 2>/dev/null)"
if [ "$n" = "0" ]; then echo "  ok   criativo_render_job continua com 0 linhas"; ok=$((ok+1));
else echo "  FALHOU  criativo_render_job tem $n linha(s)"; falhou=$((falhou+1)); fi

echo
echo "════════════════════════════════════════════════════════"
echo "  passaram $ok · falharam $falhou"
[ "$falhou" -eq 0 ] || exit 1
echo "  PREFLIGHT v11_03 PROVADO: acusa quando há o que acusar, e não aplica nada"
