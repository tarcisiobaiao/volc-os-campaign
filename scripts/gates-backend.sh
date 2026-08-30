#!/usr/bin/env bash
#
# O gate do backend, reproduzível — e a declaração honesta do que ele não cobre.
#
# ## Por que este script existe
#
# O número "699 testes passando" não significa nada sem o comando que o produziu.
# Rodar `pytest` do jeito errado neste repositório dá três resultados diferentes,
# e nenhum deles avisa:
#
#   `pytest` sem PYTHONPATH   → `ModuleNotFoundError: volc_ads`, porque o engine
#                               mora na RAIZ e o backend roda com `cwd=backend`;
#   `pytest` sem -p no:randomly → a suíte usa `pytest-randomly`, e duas falhas
#                               herdadas ficam intermitentes conforme a ordem;
#   venv errado                → 716/744: dois módulos não coletam e três testes
#                               falham, por falta do SDK do Google.
#
# ## O ambiente real, medido em 26/08/2026
#
#   backend/.venv/bin/python   3.14.6 · pytest, fastapi, httpx E google-ads  ← ESTE
#   .venv/bin/python           3.14.6 · só google-ads
#   /usr/local/bin/python3     3.13.0 · pytest, fastapi, httpx · SEM google-ads
#
# ## A dependência que ninguém declarou, e o que ela custou
#
# `google-ads` não estava em requirements nenhum, e TRÊS coisas dependem dele:
# dois módulos de teste que não coletam sem ele, e o engine inteiro.
#
# Com o interpretador errado a suíte roda 716 de 744 e reporta três falhas. Eu as
# chamei de "herdadas" por duas rodadas — não eram: era este script começando
# pelo venv sem fastapi e caindo no que não tem o SDK. Com `backend/.venv` a
# suíte passa INTEIRA.
#
# Um teste que não coleta e some da contagem é pior que um que falha: a contagem
# verde afirma uma cobertura que não existe.
#
# Uso:
#     ./scripts/gates-backend.sh            roda o gate
#     ./scripts/gates-backend.sh --tudo     tenta incluir os dois excluídos

set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

# ── 1. achar um interpretador que sirva ─────────────────────────────────────
#
# Em ordem de preferência, e cada um é conferido de verdade — `command -v` só
# diz que o arquivo existe, não que ele tem o que precisamos.
# ⚠️ `backend/.venv` PRIMEIRO, e a ordem é o conserto.
#
# Ele é o venv que serve a API em :8010 e o único com o SDK do Google. As
# versões anteriores deste script começavam por `$RAIZ/.venv` (sem fastapi) e
# caíam em `/usr/local/bin/python3` (com pytest e fastapi, SEM google-ads) — e
# aí dois módulos não coletavam e três testes falhavam.
#
# Eu reportei esses três como "falhas herdadas" por duas rodadas. Não eram: era
# este script escolhendo o interpretador errado. Com o venv certo a suíte passa
# INTEIRA, sem exclusão nenhuma.
#
# A checagem inclui `google.ads.googleads` de propósito — um interpretador que
# roda 716 dos 744 testes não serve como gate, porque a contagem verde some com
# os 28 que faltaram.
PY=""
for candidato in \
    "$RAIZ/backend/.venv/bin/python" \
    "$RAIZ/.venv/bin/python" \
    /usr/local/bin/python3 \
    /opt/homebrew/bin/python3 \
    python3
do
    caminho="$(command -v "$candidato" 2>/dev/null)" || continue
    if "$caminho" -c "import pytest, fastapi, httpx, google.ads.googleads" >/dev/null 2>&1; then
        PY="$caminho"; break
    fi
done

# Recuo: se nenhum tiver o SDK, aceita um sem ele — e o script DIZ o que isso
# custa, logo abaixo.
if [ -z "$PY" ]; then
    for candidato in \
        "$RAIZ/backend/.venv/bin/python" \
        "$RAIZ/.venv/bin/python" \
        /usr/local/bin/python3 \
        /opt/homebrew/bin/python3 \
        python3
    do
        caminho="$(command -v "$candidato" 2>/dev/null)" || continue
        if "$caminho" -c "import pytest, fastapi, httpx" >/dev/null 2>&1; then
            PY="$caminho"; break
        fi
    done
fi

if [ -z "$PY" ]; then
    cat >&2 <<'FIM'
Nenhum interpretador com pytest + fastapi + httpx.

Para criar um:
    python3 -m venv .venv-backend
    .venv-backend/bin/pip install -r backend/requirements-dev.txt

⚠️ `backend/requirements-dev.txt` NÃO declara `google-ads`, e a suíte precisa
dele para dois módulos. Instale também:
    .venv-backend/bin/pip install google-ads
FIM
    exit 2
fi

# ── 2. dizer o que temos, antes de rodar ────────────────────────────────────
echo "interpretador ....... $PY"
echo "python .............. $("$PY" -c 'import sys;print(sys.version.split()[0])')"
echo "pytest .............. $("$PY" -c 'import pytest;print(pytest.__version__)')"

TEM_GADS=1
"$PY" -c "import google.ads.googleads" >/dev/null 2>&1 || TEM_GADS=0
echo "google-ads .......... $([ "$TEM_GADS" = 1 ] && echo presente || echo AUSENTE)"

TEM_PG=1
for b in initdb pg_ctl psql; do command -v "$b" >/dev/null 2>&1 || TEM_PG=0; done
echo "postgres local ...... $([ "$TEM_PG" = 1 ] && echo presente || echo 'AUSENTE — os testes de persistência PULAM')"
echo

EXCLUI=()
if [ "$TEM_GADS" = 0 ] && [ "${1:-}" != "--tudo" ]; then
    EXCLUI=(--ignore=tests/test_notificacoes.py
            --ignore=tests/test_trafego_canal_de_criacao.py)
    cat <<'FIM'
⚠️ SEM `google-ads`. Dois módulos NÃO entram nesta rodada:

    tests/test_notificacoes.py
    tests/test_trafego_canal_de_criacao.py

E três testes falham por dependerem do engine em tempo de execução:

    test_seguranca_hub.py::test_a_trava_esta_fechada_e_recusa_escrita
    test_seguranca_hub.py::test_nem_um_admin_autenticado_abre_a_trava
    test_trafego.py::test_o_selo_e_pre_requisito_de_subir

Os três provam que a TRAVA DE ESCRITA está fechada. Eles não estão verdes aqui,
e isso é ambiente — não conserto. Rodá-los exige o SDK instalado.

FIM
fi

# ── 3. o comando ────────────────────────────────────────────────────────────
#
# `PYTHONPATH=$RAIZ` porque `volc_ads` mora na raiz e o pytest roda em `backend`.
# `-p no:randomly` porque a ordem aleatória torna duas falhas herdadas
# intermitentes, e um gate que muda de resultado sem o código mudar não é gate.
cd "$RAIZ/backend"
echo "→ PYTHONPATH=$RAIZ $PY -m pytest tests/ -q -p no:randomly ${EXCLUI[*]:-}"
echo
PYTHONPATH="$RAIZ" "$PY" -m pytest tests/ -q -p no:randomly ${EXCLUI[@]+"${EXCLUI[@]}"}
CODIGO=$?

echo
if [ "$TEM_GADS" = 0 ]; then
    echo "⚠️ Resultado PARCIAL: sem google-ads, 2 módulos fora e 3 testes vermelhos."
fi
exit "$CODIGO"
