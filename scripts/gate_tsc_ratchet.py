#!/usr/bin/env python3
"""`tsc --noEmit` como RATCHET, não como gate absoluto.

## Por que ratchet

O repositório carrega 76 erros de tipo herdados do webgo (ver CLAUDE.md). Um gate
absoluto sobre `tsc` nasceria vermelho, e o harness recusa começar uma missão
sobre baseline vermelho (`assert_baseline_is_green`, v3/baseline.py:130) — o gate
nunca rodaria, e a superfície de tipos ficaria sem cobertura nenhuma.

O ratchet mede e compara: passa enquanto o número não PIORA. Ele não afirma que o
código está limpo; afirma que esta entrega não sujou mais.

## O número não é uma meta

`BASELINE_ERROS` é uma MEDIÇÃO registrada, não um alvo. Baixá-lo quando alguém
consertar erros é manutenção legítima; subi-lo para fazer um gate vermelho passar
é desligar o gate com passos extras.

⚠️ `-p tsconfig.app.json` é obrigatório: o tsconfig da raiz é solution-style
(`files: []` + references), então `tsc --noEmit` puro roda sobre ZERO arquivos e
sai 0 — um gate que sempre passa.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BASELINE_ERROS = 76
PROJETO = "tsconfig.app.json"


def main() -> int:
    tsc = RAIZ / "node_modules" / ".bin" / "tsc"
    if not tsc.is_file():
        print(f"gate: tsc ausente em {tsc}", file=sys.stderr)
        return 78
    saida = subprocess.run(
        [str(tsc), "--noEmit", "-p", PROJETO],
        cwd=str(RAIZ), capture_output=True, text=True, check=False,
    )
    texto = (saida.stdout or "") + (saida.stderr or "")

    # ⚠️ TS2688 para a checagem ANTES da fase semântica e esconde todo erro real
    # do src/. Um contador ingênuo veria "poucos erros" e ficaria verde.
    if "error TS2688" in texto:
        print("gate: TS2688 presente — a checagem semântica NÃO rodou. "
              "Apague as pastas duplicadas em node_modules/@types/ (nome com espaço) "
              "antes de acreditar em qualquer contagem.", file=sys.stderr)
        return 1

    erros = len(re.findall(r"error TS\d+", texto))
    print(f"tsc -p {PROJETO}: {erros} erro(s) · baseline registrado: {BASELINE_ERROS}")
    if erros > BASELINE_ERROS:
        print(f"gate: os tipos PIORARAM ({erros} > {BASELINE_ERROS})", file=sys.stderr)
        for linha in texto.splitlines():
            if "error TS" in linha:
                print("   " + linha, file=sys.stderr)
        return 1
    if erros < BASELINE_ERROS:
        print(f"nota: {BASELINE_ERROS - erros} erro(s) a menos que o baseline. "
              f"Se for permanente, baixe BASELINE_ERROS para travar o ganho.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
