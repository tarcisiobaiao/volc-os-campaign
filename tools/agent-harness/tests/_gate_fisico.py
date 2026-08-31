"""Marcador de execução FÍSICA de gate, visível entre processos.

Contar execuções por atributo de objeto só funciona dentro de um processo. A
refutação de G5 precisa de uma contagem que sobreviva ao ``spawn``: cada
execução real cria um arquivo próprio num diretório, e o número de arquivos é o
número de processos que de fato rodaram.

A trava é um arquivo IRMÃO do diretório de marcadores, e não um argumento: o
argv entra no digest da identidade lógica, então segurar o processo por
argumento mudaria a identidade e a prova de retomada compararia duas coisas
diferentes.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

LIMITE_DE_TRAVA_S = 120.0


def main() -> int:
    destino = Path(sys.argv[1])
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"{os.getpid()}-{uuid.uuid4().hex}").write_text(str(time.time()))

    trava = destino.parent / "TRAVA"
    limite = time.monotonic() + LIMITE_DE_TRAVA_S
    while trava.exists() and time.monotonic() < limite:
        time.sleep(0.05)

    atraso = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    if atraso:
        time.sleep(atraso)
    return int(sys.argv[3]) if len(sys.argv) > 3 else 0


if __name__ == "__main__":
    raise SystemExit(main())
