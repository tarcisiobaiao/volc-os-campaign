#!/usr/bin/env python3
"""Executa a prova da fronteira atômica do ledger como gate do harness.

## Por que este arquivo existe, e por que ele é fino

`scripts/provar-ledger-v10-03.sh` é a prova executável da v10_03: ela sobe um
cluster Postgres descartável, reproduz o defeito ANTES da migration, mostra a
recusa DEPOIS, e cobre corrida real, rollback e contrato Python↔SQL.

O gate `tracked_script` do harness resolve o script pelo catálogo, confere que
ele é rastreado pelo Git, mede o digest e monta a linha de comando como
`[interpretador_python, script, *args]` — ou seja, **só executa Python**. Um
`.sh` não tem como ser gate direto.

Este arquivo é a ponte mínima: ele não reimplementa nenhuma prova, não
interpreta o resultado e não filtra saída. Ele executa o script e propaga o
código de saída. Qualquer lógica aqui seria uma segunda opinião sobre um
resultado que já é binário — e a segunda opinião é exatamente como um gate passa
a mentir.

Uso: python3 scripts/gate_provar_ledger_v10_03.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PROVA = RAIZ / "scripts" / "provar-ledger-v10-03.sh"


def main() -> int:
    if not PROVA.is_file():
        print(f"gate: prova ausente em {PROVA}", file=sys.stderr)
        return 78
    if not os.access(PROVA, os.X_OK):
        print(f"gate: prova sem bit de execução: {PROVA}", file=sys.stderr)
        return 78
    # `cwd=RAIZ` e não o diretório do gate: o script resolve a própria raiz pelo
    # BASH_SOURCE, mas as migrations são lidas por caminho relativo à raiz.
    concluido = subprocess.run(
        ["/bin/bash", str(PROVA)], cwd=str(RAIZ), check=False,
    )
    return concluido.returncode


if __name__ == "__main__":
    raise SystemExit(main())
