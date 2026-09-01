#!/usr/bin/env python3
"""CLI do coletor persistente Google Ads. Saida nunca inclui credenciais.

Dois modos, deliberadamente separados:

* varredura continua — ``--modo``, opcionalmente restrita por ``--customer-id``.
  Alcanca somente campanhas SEARCH ENABLED, que e a agenda comandada pelo n8n.
* alvo explicito — ``--customer-id`` + ``--volc-campaign-id`` + ``--campaign-id``.
  Uma execucao, uma campanha, em qualquer estado externo (inclusive PAUSED).

O alvo exige a identidade COMPLETA. Meia identidade e recusada antes de sair da
maquina: sem os tres campos nao ha como provar que o ID externo pertence a conta
que o pediu, e coletar a campanha errada e pior que nao coletar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# `deploy/google-intelligence/run.sh` exporta PYTHONPATH; invocado direto da
# arvore o script tambem precisa achar `volc_ads` — mesma convencao dos demais
# scripts do repositorio.
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from volc_ads.inteligencia_google import executar_coleta, executar_coleta_alvo  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--modo", choices=("frequente", "completa"), default="completa")
    parser.add_argument("--customer-id")
    parser.add_argument(
        "--volc-campaign-id",
        help="identidade canonica interna da campanha (exige --campaign-id e --customer-id)",
    )
    parser.add_argument(
        "--campaign-id",
        help="ID externo Google Ads da campanha (exige --volc-campaign-id e --customer-id)",
    )
    args = parser.parse_args()

    pedidos_de_alvo = (args.volc_campaign_id, args.campaign_id)
    if any(pedidos_de_alvo):
        faltando = [
            nome for nome, valor in (
                ("--customer-id", args.customer_id),
                ("--volc-campaign-id", args.volc_campaign_id),
                ("--campaign-id", args.campaign_id),
            ) if not valor
        ]
        if faltando:
            parser.error(
                "identidade incompleta para coleta por alvo; faltam: "
                + ", ".join(faltando)
            )
        saida = executar_coleta_alvo(
            customer_id=args.customer_id,
            volc_campaign_id=args.volc_campaign_id,
            campaign_id=args.campaign_id,
            modo=args.modo,
        )
    else:
        saida = executar_coleta(modo=args.modo, customer_id=args.customer_id)

    print(json.dumps(saida, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
