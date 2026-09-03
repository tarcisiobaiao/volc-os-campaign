#!/usr/bin/env bash
# =============================================================================
# v11_03-provar-plano.sh — o PLANO tem de descrever a v11_03 que EXISTE
# =============================================================================
# Um documento não tem teste unitário, mas tem afirmações conferíveis contra o
# arquivo ao lado. Este gate confere as que importam. Ele lê um PLANO passado por
# argumento (padrão: o versionado), então dá para rodá-lo contra uma versão
# antiga e ver a contraprova ficar vermelha:
#
#   git show HEAD:supabase/migrations/PLANO-v11_03.md > /tmp/plano-antigo.md
#   bash scripts/v11_03-provar-plano.sh /tmp/plano-antigo.md
set -uo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
SQL="$RAIZ/supabase/migrations/v11_03_execucao_criativa.sql"
PLANO="${1:-$RAIZ/supabase/migrations/PLANO-v11_03.md}"
[ -f "$PLANO" ] || { echo "não achei o plano: $PLANO"; exit 2; }
[ -f "$SQL" ]   || { echo "não achei a migration: $SQL"; exit 2; }

ok=0; falhou=0
tem()    { if grep -qiF "$2" "$PLANO"; then echo "  ok   $1"; ok=$((ok+1)); else echo "  FALHOU  $1"; falhou=$((falhou+1)); fi; }
naotem() { if grep -qiF "$2" "$PLANO"; then echo "  FALHOU  $1 (achei \"$2\")"; falhou=$((falhou+1)); else echo "  ok   $1"; ok=$((ok+1)); fi; }

echo "conferindo $PLANO contra $(basename "$SQL") ($(wc -l < "$SQL" | tr -d ' ') linhas)"
echo
echo "1. o plano não pode se declarar não-escrito com o .sql pronto ao lado"
# ⚠️ Conferir por ocorrência solta não serve: um plano honesto CITA a frase
# antiga para explicar o que corrigiu, e um grep cru puniria justamente a
# correção. O que vale é a LINHA DE ESTADO — a primeira que começa com
# `**Estado:`, que é onde o documento afirma o que ele é.
ESTADO="$(grep -m1 '^\*\*Estado:' "$PLANO" || true)"
if [ -z "$ESTADO" ]; then
    echo "  FALHOU  o plano não tem linha de estado (\`**Estado:\`)"; falhou=$((falhou+1))
else
    echo "  info   linha de estado: $ESTADO"
    if printf '%s' "$ESTADO" | grep -qiF "NÃO ESCRITA COMO SQL"; then
        echo "  FALHOU  a linha de estado declara 'NÃO ESCRITA COMO SQL' com o .sql pronto ao lado"; falhou=$((falhou+1))
    elif printf '%s' "$ESTADO" | grep -qiF "ESCRITA COMO SQL"; then
        echo "  ok   a linha de estado afirma que a migration foi escrita como SQL"; ok=$((ok+1))
    else
        echo "  FALHOU  a linha de estado não diz se a migration existe como SQL"; falhou=$((falhou+1))
    fi
fi
naotem "não afirma que não existe .sql de propósito" "Não existe \`.sql\` correspondente de propósito"

echo
echo "2. o plano nomeia as 5 tabelas que a migration realmente cria"
for t in criativo_render_job criativo_render_transicao criativo_render_recibo \
         criativo_render_artefato criativo_render_validacao; do
    grep -q "create table if not exists public.$t" "$SQL" || { echo "  FALHOU  $t não está no .sql — este gate está errado"; falhou=$((falhou+1)); continue; }
    tem "cita $t" "$t"
done

echo
echo "3. a proposta que não virou SQL fica marcada como NÃO IMPLEMENTADA"
if grep -qiF "criativo_template" "$PLANO"; then
    tem "há seção NÃO IMPLEMENTADA para a proposta" "NÃO IMPLEMENTADA"
    if grep -qiF "criativo_template" "$SQL"; then
        echo "  FALHOU  criativo_template está no .sql: a marcação está errada"; falhou=$((falhou+1))
    else
        echo "  ok   criativo_template de fato não existe no .sql"; ok=$((ok+1))
    fi
else
    echo "  ok   o plano não menciona a proposta (nada a marcar)"; ok=$((ok+1))
fi

echo
echo "4. o plano declara o estado honesto de aplicação"
tem "diz que não foi aplicada em produção" "NÃO APLICADA EM PRODUÇÃO"
tem "aponta o script que executa o ciclo" "provar-ciclo-v11_03.sh"
tem "aponta o rollback pareado" "v11_03_rollback.sql"

echo
echo "════════════════════════════════════════════════════════"
echo "  passaram $ok · falharam $falhou"
[ "$falhou" -eq 0 ] || exit 1
echo "  PLANO v11_03 descreve a v11_03 que existe"
