#!/usr/bin/env python3
"""CLI do coletor persistente Google Ads. Saida nunca inclui credenciais."""

from __future__ import annotations

import argparse
import json

from volc_ads.inteligencia_google import executar_coleta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modo", choices=("frequente", "completa"), default="completa")
    parser.add_argument("--customer-id")
    args = parser.parse_args()
    print(json.dumps(
        executar_coleta(modo=args.modo, customer_id=args.customer_id),
        ensure_ascii=False, indent=2, sort_keys=True,
    ))


if __name__ == "__main__":
    main()
