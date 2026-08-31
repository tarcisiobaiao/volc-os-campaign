#!/usr/bin/env python3
"""Testes focais do frontend de lançamento.

A suíte inteira (`npm test`) carrega 3 falhas e 8 arquivos sem coleta, todos
herdados — medidos com a árvore limpa, idênticos antes e depois desta entrega.
Como gate absoluto ela nasceria vermelha e o harness recusaria a missão.

Este gate cobre a SUPERFÍCIE DE LANÇAMENTO, que é o que a entrega tocou, e ela é
verde. Não substitui a suíte inteira: declara o recorte e o motivo dele.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ALVOS = ["src/lib/trafego"]


def main() -> int:
    vitest = RAIZ / "node_modules" / ".bin" / "vitest"
    if not vitest.is_file():
        print(f"gate: vitest ausente em {vitest}", file=sys.stderr)
        return 78
    return subprocess.run(
        # ⚠️ sem `--reporter=basic`: essa opção não existe nesta versão e o
        # vitest morre em `loadCustomReporterModule` ANTES de coletar teste
        # nenhum — um gate vermelho que não fala de teste, e sim de flag.
        [str(vitest), "run", *ALVOS, "--reporter=dot"],
        cwd=str(RAIZ), check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
