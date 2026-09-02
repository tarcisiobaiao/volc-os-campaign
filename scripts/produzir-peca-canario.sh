#!/usr/bin/env bash
# Produz UMA peca de imagem e UMA peca de video pela espinha produtiva inteira,
# num diretorio descartavel, e escreve a evidencia tecnica em JSON.
#
# Nao publica, nao sobe para storage remoto, nao chama provider pago e nao toca
# em Supabase. O armazenamento e o adaptador LOCAL, num diretorio de `mktemp`.
#
# Uso: bash scripts/produzir-peca-canario.sh [destino-do-json]
set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAIDA="${1:-$RAIZ/docs/closure/creative-factory-production-last-mile-v1/contraprovas/PECA-CANARIO.json}"
PY="${CRIATIVO_PYTHON:-$RAIZ/.venv-lastmile/bin/python}"
[ -x "$PY" ] || PY="python3"
mkdir -p "$(dirname "$SAIDA")"
CRIATIVO_CANARIO_SAIDA="$SAIDA" "$PY" "$RAIZ/scripts/produzir_peca_canario.py"
