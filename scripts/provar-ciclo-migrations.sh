#!/usr/bin/env bash
#
# O ciclo completo da série v9 num Postgres descartável — aplicar, reverter,
# reaplicar — com prova negativa em cada degrau.
#
# ## Por que um script, e não um comando anotado
#
# Um rollback só existe se alguém o executa. O da v9_03 estava documentado como
# "reaplique a v9_02" e **abortava** — `cannot drop columns from view` —, e isso
# só apareceu quando a auditoria adversarial tentou. Rollback documentado e nunca
# rodado é rollback que ninguém tem.
#
# Este script roda o ciclo inteiro do zero, a cada execução, num cluster que
# nasce e morre aqui. Ele não toca em nada fora de /tmp.
#
# ## O que ele prova, em cada degrau
#
#   · a migration aplica sem erro;
#   · as colunas/funções que ela promete existem (ou sumiram, no rollback);
#   · `service_role` mantém SELECT na view;
#   · `anon` e `authenticated` continuam SEM acesso;
#   · `security_invoker` continua ligado — sem ele a view roda com o privilégio
#     do dono e o RLS das tabelas de baixo deixa de valer;
#   · as duas guardas do gatilho (número sem carimbo, leitura retroativa)
#     sobrevivem a toda ida e volta.
#
# Uso:  ./scripts/provar-ciclo-migrations.sh

set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
M="$RAIZ/supabase/migrations"

for b in initdb pg_ctl psql; do
    command -v "$b" >/dev/null 2>&1 || { echo "falta $b — brew install postgresql@16"; exit 2; }
done

# ⚠️ /tmp e não o scratchpad: o socket unix tem teto de 103 bytes no caminho, e
# um diretório fundo estoura com uma mensagem que não fala de tamanho.
D=$(mktemp -d /tmp/volcciclXXXX)
export LC_ALL=C LANG=C
limpar() { pg_ctl -D "$D/d" -m immediate stop >/dev/null 2>&1; rm -rf "$D"; }
trap limpar EXIT

initdb -D "$D/d" -U postgres --encoding=UTF8 --locale=C >/dev/null 2>&1
mkdir -p "$D/s"
pg_ctl -D "$D/d" -l "$D/pg.log" -o "-k $D/s -h ''" -w start >/dev/null 2>&1

P() { psql -h "$D/s" -U postgres -X -q -A -t "$@"; }

# Os papéis do Supabase, INCLUSIVE o default ACL quebrado de `public` — sem
# reproduzir o defeito, a prova de que a migration fecha a tabela mediria um
# ambiente mais seguro que o real.
P -c "CREATE ROLE anon NOLOGIN NOINHERIT;
      CREATE ROLE authenticated NOLOGIN NOINHERIT;
      CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
      GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
      ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT ALL ON TABLES TO anon, authenticated, service_role;" >/dev/null

FALHAS=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
nao()  { printf '  \033[31m✗\033[0m %s\n' "$1"; FALHAS=$((FALHAS+1)); }
cmp_() { [ "$1" = "$2" ] && ok "$3" || nao "$3 (esperado=$2 obtido=$1)"; }

aplicar() {
    if psql -h "$D/s" -U postgres -q -v ON_ERROR_STOP=1 -f "$M/$1.sql" >"$D/out" 2>&1; then
        ok "aplicou $1"
    else
        nao "aplicou $1"; tail -3 "$D/out" | sed 's/^/      /'
    fi
}

# ── as provas, reunidas ─────────────────────────────────────────────────────
colunas()  { P -c "SELECT count(*) FROM pg_attribute WHERE attrelid='public.trafego_inventario_campanha'::regclass AND attname IN ('historico','ordem_operacional') AND NOT attisdropped;"; }
preserva() { P -c "SELECT CASE WHEN position('NEW.url_final' IN prosrc)>0 THEN 'sim' ELSE 'nao' END FROM pg_proc WHERE proname='trafego_espelho_preserva_ultima_boa';"; }
invoker()  { P -c "SELECT CASE WHEN array_to_string(reloptions,',') LIKE '%security_invoker=true%' THEN 'sim' ELSE 'nao' END FROM pg_class WHERE oid='public.trafego_inventario_campanha'::regclass;"; }
acesso()   { P -c "SELECT has_table_privilege('$1','public.trafego_inventario_campanha','$2')::text;"; }
guardas()  { P -c "SELECT (position('entrega com numero e sem carimbo' IN prosrc)>0 AND position('Varredura atrasada' IN prosrc)>0)::text FROM pg_proc WHERE proname='trafego_espelho_preserva_ultima_boa';"; }

seguranca() {
    cmp_ "$(invoker)"  "sim"   "$1 · security_invoker ligado"
    cmp_ "$(acesso service_role SELECT)" "true"  "$1 · service_role LÊ"
    for papel in anon authenticated; do
        for priv in SELECT INSERT UPDATE DELETE; do
            [ "$(acesso $papel $priv)" = "false" ] || { nao "$1 · $papel alcança $priv"; return; }
        done
    done
    ok "$1 · anon e authenticated SEM acesso (4 privilégios × 2 papéis)"
    # service_role só com o necessário: lê a view, e não escreve nela.
    for priv in INSERT UPDATE DELETE; do
        [ "$(acesso service_role $priv)" = "false" ] || { nao "$1 · service_role tem $priv na view"; return; }
    done
    ok "$1 · service_role SÓ com SELECT na view"
    cmp_ "$(guardas)" "true" "$1 · as duas guardas do gatilho vivas"
}

echo "════ 1 · aplicar até a v9_04 ════"
for m in v9_01_trafego_inventario v9_02_atencao_sem_removida \
         v9_03_historico_e_ordem_operacional v9_04_url_final_preservada; do
    aplicar "$m"
done
cmp_ "$(colunas)"  "2"   "v9_03 · historico e ordem_operacional publicadas"
cmp_ "$(preserva)" "sim" "v9_04 · url_final preservada"
seguranca "aplicado"

echo
echo "════ 2 · reverter v9_04 ════"
aplicar "v9_04_rollback"
cmp_ "$(preserva)" "nao" "v9_04 · url_final NÃO é mais preservada"
cmp_ "$(colunas)"  "2"   "v9_03 · intacta (as duas não se tocam)"
seguranca "pós-rollback v9_04"

echo
echo "════ 3 · reverter v9_03 ════"
aplicar "v9_03_rollback"
cmp_ "$(colunas)" "0" "v9_03 · as duas colunas sumiram"
cmp_ "$(P -c "SELECT count(*) FROM pg_attribute WHERE attrelid='public.trafego_inventario_campanha'::regclass AND attname='atencao' AND NOT attisdropped;")" "1" \
     "v9_02 · atencao sobreviveu ao rollback"
seguranca "pós-rollback v9_03"

echo
echo "════ 4 · reaplicar v9_03 ════"
aplicar "v9_03_historico_e_ordem_operacional"
cmp_ "$(colunas)" "2" "v9_03 · reaplicada"
seguranca "reaplicado v9_03"

echo
echo "════ 5 · reaplicar v9_04 ════"
aplicar "v9_04_url_final_preservada"
cmp_ "$(preserva)" "sim" "v9_04 · reaplicada"
seguranca "reaplicado v9_04"

echo
echo "════ 6 · as guardas funcionam de verdade ════"
P -c "SET ROLE service_role;
      INSERT INTO trafego_campanha (volc_campaign_id, customer_id, campaign_id, criada_por)
        VALUES ('k','8017851692','9','prova');
      INSERT INTO trafego_campanha_espelho
        (volc_campaign_id, lido_em, impressoes, cliques, custo_micros, entrega_lida_em, url_final)
        VALUES ('k','2026-08-25T10:00:00Z',10,1,5,'2026-08-25T10:00:00Z','https://x/lp');" >/dev/null 2>&1

# ⚠️ "Deu erro" NÃO prova que a guarda funcionou.
#
# A versão anterior destas duas provas era `if psql …; then nao; else ok` — e
# nesse desenho tabela renomeada, coluna com typo, sintaxe torta e permissão
# faltando são TODAS lidas como "a guarda recusou". Medido em 26/08/2026 contra
# um Postgres limpo: os quatro casos passavam como ✓.
#
# Isso importa mais aqui do que na série v10, porque a v9 **já está aplicada em
# produção**: um rename futuro deixaria estas duas provas verdes com a guarda
# ausente, e o modo de falha de um harness que mente é pior que o de um que some.
#
# A separação é por CLASSE de SQLSTATE, e as duas classes não se tocam:
#   P0001 / 23xxx  → a guarda disparou (RAISE EXCEPTION, CHECK, restrict, FK…)
#   42xxx / 3F000  → a PROVA está quebrada
GUARDA='^(P0001|23[0-9A-Z]{3})$'
QUEBRADA='^(42[0-9A-Z]{3}|3F000|22P02)$'

guarda_recusa() {
    local rotulo="$1"; shift
    local saida estado
    saida=$(printf '\\set VERBOSITY verbose\nSET ROLE service_role;\n%s\n' "$*" \
            | psql -h "$D/s" -U postgres -X -A -t 2>&1)
    estado=$(printf '%s' "$saida" | grep -oE '^ERROR:  [0-9A-Z]{5}:' | head -1 | awk '{print $2}' | tr -d ':')
    if printf '%s' "$estado" | grep -qE "$GUARDA"; then
        ok "$rotulo — RECUSADO ($estado)"
    elif printf '%s' "$estado" | grep -qE "$QUEBRADA"; then
        nao "$rotulo — a PROVA está quebrada ($estado), não o código"
    elif printf '%s' "$saida" | grep -qE '^UPDATE 0$'; then
        nao "$rotulo — não tocou linha nenhuma: a prova mediria o vazio"
    elif [ -n "$estado" ]; then
        ok "$rotulo — RECUSADO ($estado, não catalogado)"
    else
        nao "$rotulo — PASSOU, e não deveria"
    fi
}

guarda_recusa "número sem carimbo" \
  "UPDATE trafego_campanha_espelho SET lido_em='2026-08-25T11:00:00Z', impressoes=99, entrega_lida_em=NULL WHERE volc_campaign_id='k';"

guarda_recusa "leitura retroativa" \
  "UPDATE trafego_campanha_espelho SET lido_em='2026-08-24T10:00:00Z' WHERE volc_campaign_id='k';"

P -c "SET ROLE service_role; UPDATE trafego_campanha_espelho SET lido_em='2026-08-25T12:00:00Z', url_final=NULL WHERE volc_campaign_id='k';" >/dev/null 2>&1
cmp_ "$(P -c "SELECT coalesce(url_final,'(nula)') FROM trafego_campanha_espelho WHERE volc_campaign_id='k';")" \
     "https://x/lp" "url_final sobreviveu a uma leitura que não a trouxe"

echo
echo "════════════════════════════════════════════════"
if [ "$FALHAS" = 0 ]; then
    echo "  CICLO COMPLETO VERDE — aplicar, reverter, reaplicar"
    exit 0
else
    echo "  $FALHAS FALHA(S)"
    exit 1
fi
