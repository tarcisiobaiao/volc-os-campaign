#!/usr/bin/env python3
"""CLI do coletor persistente Google Ads. Saida nunca inclui credenciais.

Tres modos, deliberadamente separados:

* varredura continua — ``--modo``, opcionalmente restrita por ``--customer-id``.
  Alcanca somente campanhas SEARCH ENABLED, que e a agenda comandada pelo n8n.
* alvo explicito — ``--customer-id`` + ``--volc-campaign-id`` + ``--campaign-id``.
  Uma execucao, uma campanha, em qualquer estado externo (inclusive PAUSED).
* alvo Performance Max — os mesmos tres campos mais ``--pmax``. Le a estrutura
  interna da campanha (grupos de recursos, assets, sinais, desempenho por grupo
  e a recomendacao oficial de forca) e recusa qualquer canal que nao seja
  PERFORMANCE_MAX antes da primeira consulta.

O alvo exige a identidade COMPLETA. Meia identidade e recusada antes de sair da
maquina: sem os tres campos nao ha como provar que o ID externo pertence a conta
que o pediu, e coletar a campanha errada e pior que nao coletar.

⚠️ A saida do modo PMax e um RESUMO. Itens e metricas carregam texto de anuncio,
URL final e nome de campanha — dado do cliente. Eles ficam no banco, atras da
service_role; o terminal ve estado, contagem e recibo.
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

from volc_ads.inteligencia_google import (  # noqa: E402
    executar_coleta, executar_coleta_alvo, executar_coleta_pmax,
)
from volc_ads.inteligencia_google.pmax import (  # noqa: E402
    ErroCanalNaoPMax, resumo_sanitizado,
)


def main(argv: list[str] | None = None) -> int:
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
    parser.add_argument(
        "--pmax", action="store_true",
        help=("le a observabilidade de Performance Max do alvo; exige a "
              "identidade completa e recusa canal diferente de PERFORMANCE_MAX"),
    )
    args = parser.parse_args(argv)

    pedidos_de_alvo = (args.volc_campaign_id, args.campaign_id, args.pmax)
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
        if args.pmax:
            # Canal incompativel, identidade divergente e falha da API sao tres
            # saidas diferentes de zero — nunca um stacktrace cru nem um zero
            # silencioso. O detalhe vai para stderr; stdout guarda so o resumo.
            try:
                bruto = executar_coleta_pmax(
                    customer_id=args.customer_id,
                    volc_campaign_id=args.volc_campaign_id,
                    campaign_id=args.campaign_id,
                    modo=args.modo,
                )
            except ErroCanalNaoPMax as erro:
                print(f"coleta PMax recusada: {erro}", file=sys.stderr)
                return 3
            except Exception as erro:  # noqa: BLE001 - a classe vira codigo de saida
                print(
                    f"coleta PMax falhou: {type(erro).__name__}: {erro}",
                    file=sys.stderr,
                )
                return 4
            saida = resumo_sanitizado(bruto)
        else:
            saida = executar_coleta_alvo(
                customer_id=args.customer_id,
                volc_campaign_id=args.volc_campaign_id,
                campaign_id=args.campaign_id,
                modo=args.modo,
            )
    else:
        saida = executar_coleta(modo=args.modo, customer_id=args.customer_id)

    print(json.dumps(saida, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
