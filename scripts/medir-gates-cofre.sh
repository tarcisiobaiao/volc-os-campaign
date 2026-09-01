#!/usr/bin/env bash
# =============================================================================
# medir-gates-cofre.sh — os numeros do Cofre, MEDIDOS e nao digitados.
# =============================================================================
#
# POR QUE ESTE SCRIPT EXISTE
#
# Uma revisao de contrato em 01/09/2026 encontrou nove numeros errados no
# pacote de fechamento desta missao: "75 provas" quando eram 81, "47 testes"
# quando eram 54, "19 testes de frontend" quando eram 21, contagens de linha e
# de commits de um HEAD anterior. Nenhum deles era mentira: eram numeros
# verdadeiros no minuto em que foram escritos, num trabalho onde a branch
# continuou andando.
#
# O conserto nao e "revisar melhor" — e nao digitar numero nenhum. Este script
# roda os gates e imprime o bloco em markdown; quem fecha a missao COLA a saida.
# Um numero que envelhece em silencio e pior que numero ausente, porque parece
# conferido.
#
#   ./scripts/medir-gates-cofre.sh            # bloco markdown no stdout
#   ./scripts/medir-gates-cofre.sh --rapido   # pula ciclo SQL e build
# =============================================================================
set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"
RAPIDO=0
[[ "${1:-}" == "--rapido" ]] && RAPIDO=1

n() { printf '%s' "${1:-?}"; }

echo "<!-- GERADO POR ./scripts/medir-gates-cofre.sh — NAO EDITE A MAO -->"
echo
echo "| Gate | Comando | Resultado |"
echo "|---|---|---|"

BASE="$(git merge-base HEAD origin/volc-os-v2 2>/dev/null || echo '?')"
echo "| base | \`git merge-base HEAD origin/volc-os-v2\` | \`${BASE:0:7}\` |"
echo "| HEAD | \`git rev-parse HEAD\` | \`$(git rev-parse --short HEAD)\` |"
echo "| commits | \`git rev-list --count ${BASE:0:7}..HEAD\` | $(git rev-list --count "$BASE"..HEAD 2>/dev/null || n) |"
DIFF=$(git diff --shortstat "$BASE"..HEAD 2>/dev/null | tr -d '\n')
echo "| diff | \`git diff --shortstat\` | ${DIFF:-?} |"
# ⚠️ A saida deste script costuma ser redirecionada para um arquivo VERSIONADO
# (docs/closure/.../GATES.md). Enquanto ele roda, esse arquivo esta modificado —
# e contar a si mesmo como arvore suja seria o script mentindo sobre o proprio
# efeito. A contagem exclui o GATES.md por isso, e diz que excluiu.
SUJOS=$(git status --short | grep -v 'closure/.*GATES\.md' || true)
# `printf | wc -l` conta QUEBRAS DE LINHA, e uma unica linha sem \n final conta
# zero — "SUJA: 0 caminho(s)" foi o que este script imprimiu antes deste conserto.
N_SUJOS=$(printf '%s\n' "$SUJOS" | grep -c . || true)
echo "| arvore (fora deste GATES.md) | \`git status --short\` | $( [ "$N_SUJOS" -eq 0 ] && echo 'limpa' || echo "SUJA: ${N_SUJOS} caminho(s): $(printf '%s\n' "$SUJOS" | awk '{print $NF}' | tr '\n' ' ')") |"
echo "| espaco em branco | \`git diff --check\` | $( git diff --check >/dev/null 2>&1 && echo 'limpo' || echo 'PROBLEMA') |"

if [[ $RAPIDO -eq 0 ]]; then
  CICLO=$(./scripts/provar-ciclo-v13_01.sh 2>&1)
  echo "| ciclo SQL | \`./scripts/provar-ciclo-v13_01.sh\` | $(printf '%s' "$CICLO" | grep -oE '[0-9]+ provas passaram' || echo 'FALHOU') · $(printf '%s' "$CICLO" | grep -oE 'PostgreSQL [0-9.]+' | head -1) |"
fi

PYT=$(PYTHONPATH="backend:$RAIZ" backend/.venv/bin/python -m pytest backend/tests/test_cofre_ativos.py -q -p no:warnings 2>&1 | tail -1)
echo "| testes backend do Cofre | \`pytest backend/tests/test_cofre_ativos.py\` | ${PYT} |"

PYTT=$(PYTHONPATH="backend:$RAIZ" backend/.venv/bin/python -m pytest backend/tests -q -p no:warnings 2>&1 | tail -1)
echo "| suite backend inteira | \`pytest backend/tests\` | ${PYTT} |"

VIT=$(npx vitest run src/features/asset-vault 2>&1 | grep -E "^ +Tests " | tail -1 | sed 's/^ *//')
echo "| testes frontend do Cofre | \`vitest run src/features/asset-vault\` | ${VIT:-?} |"

TSC=$(npx tsc --noEmit -p tsconfig.app.json 2>&1 | grep -c "error TS")
TSCV=$(npx tsc --noEmit -p tsconfig.app.json 2>&1 | grep "error TS" | grep -c "asset-vault")
echo "| TypeScript | \`tsc --noEmit -p tsconfig.app.json\` | ${TSC} erros herdados · ${TSCV} em asset-vault |"

if [[ $RAPIDO -eq 0 ]]; then
  npm run build >/dev/null 2>&1 && B=ok || B=FALHOU
  echo "| build | \`npm run build\` | ${B} |"
fi

ENG=$(python3 scripts/importar_engines_no_cofre.py --autoteste 2>&1 | grep -oE '[0-9]+ (asserções|assercoes) ok' | tail -1)
NENG=$(python3 scripts/importar_engines_no_cofre.py 2>/dev/null | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>/dev/null)
echo "| importador de engines | \`importar_engines_no_cofre.py --autoteste\` | ${ENG:-?} · ${NENG:-?} engines |"

SMK=$(python3 tools/onepassword-smoke/run.py --autoteste 2>&1 | grep -oE 'resultado: [0-9]+ falhas' | tail -1)
python3 tools/onepassword-smoke/run.py >/dev/null 2>&1; SMKE=$?
SMKS=$(python3 tools/onepassword-smoke/run.py --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["estado"])' 2>/dev/null)
echo "| smoke 1Password (duple) | \`onepassword-smoke/run.py --autoteste\` | ${SMK:-?} |"
echo "| smoke 1Password (real) | \`onepassword-smoke/run.py\` | \`${SMKS:-?}\`, exit ${SMKE} |"

ONB=$(python3 scripts/onboarding_pagina_facebook.py --autoteste 2>&1 | grep -oE '[0-9]+/[0-9]+ (verificações|verificacoes) passaram' | tail -1)
echo "| onboarding da pagina | \`onboarding_pagina_facebook.py --autoteste\` | ${ONB:-?} |"

ROTAS=$(PYTHONPATH="backend:$RAIZ" backend/.venv/bin/python -c "from app.asset_vault import rotas; print(len(rotas.router.routes))" 2>/dev/null)
echo "| rotas do Cofre | \`len(rotas.router.routes)\` | ${ROTAS:-?} |"

echo
echo "<!-- medido em $(date '+%Y-%m-%d %H:%M:%S %z') -->"
# ⚠️ Um arquivo gerado nao pode conhecer o hash do commit que o contem: quando
# este GATES.md e commitado JUNTO com a medicao, o HEAD acima e o commit
# ANTERIOR. Nao ha conserto — ha o aviso, que e o que impede alguem de ler a
# diferenca como erro.
echo "<!-- ⚠️ Se este arquivo foi commitado junto com a medicao, o HEAD acima e o"
echo "     commit ANTERIOR: um arquivo gerado nao conhece o hash do commit que o"
echo "     contem. Confira com \`git log --oneline -1\`. -->"
