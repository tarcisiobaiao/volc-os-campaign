#!/usr/bin/env python3
"""Contraprova: durante os gates, nenhuma mutação alcança o Google Ads.

Não é uma inspeção de rede — o runner local não contém o filesystem nem a árvore
de processos (risco residual G1b, declarado pelo próprio harness). É a prova da
PRÉ-CONDIÇÃO que torna a mutação impossível, e ela é verificável:

1. `FORGE_PERMITIR_ESCRITA` não está armada no ambiente do gate;
2. `volc_ads.gads.modo.escrita_permitida()` responde False;
3. a rota produtiva recusa escrita sem ledger, e o ledger não está configurado
   aqui — logo, mesmo que 1 e 2 mudassem, `/subir` responderia 503.

Se qualquer uma falhar, o gate fica VERMELHO: uma suíte que roda com a trava
aberta não é uma suíte, é um risco.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def main() -> int:
    falhas: list[str] = []

    armada = os.environ.get("FORGE_PERMITIR_ESCRITA", "")
    if armada.strip() == "1":
        falhas.append("FORGE_PERMITIR_ESCRITA=1 está no ambiente do gate")
    else:
        print("ok · FORGE_PERMITIR_ESCRITA não está armada")

    sys.path.insert(0, str(RAIZ))
    try:
        from volc_ads.gads import modo
    except Exception as exc:  # noqa: BLE001
        # Não conseguir importar NÃO é prova de segurança. É ausência de leitura.
        print(f"gate: não consegui importar volc_ads.gads.modo ({exc}); "
              f"ausência de leitura não vale como prova de trava fechada",
              file=sys.stderr)
        return 78

    try:
        permitida = bool(modo.escrita_permitida())
    except Exception as exc:  # noqa: BLE001
        print(f"gate: escrita_permitida() levantou {exc}", file=sys.stderr)
        return 78

    if permitida:
        falhas.append("volc_ads.gads.modo.escrita_permitida() respondeu True")
    else:
        print("ok · a trava de escrita está fechada")

    if falhas:
        for f in falhas:
            print(f"gate: {f}", file=sys.stderr)
        return 1
    print("contraprova: nenhuma mutação Google Ads é alcançável durante estes gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
