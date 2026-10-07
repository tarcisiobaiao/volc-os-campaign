#!/usr/bin/env bash
# Sem comandos livres; nao faz source de arquivos .env.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -x "$repo_dir/backend/.venv/bin/python" ]]; then
  echo 'ERRO: ambiente backend/.venv ausente; nenhuma conexao realizada.' >&2
  exit 1
fi
exec "$repo_dir/backend/.venv/bin/python" "$repo_dir/scripts/creditoup_ssh_check.py" "$@"
