"""Entrada de processo do broker.

    python3 -m broker --allowlist ~/.volc/adspower-perfis.json

O token vem de `VOLC_BROKER_TOKEN` e NUNCA de `--token`: um token no `argv` fica
visível em `ps` para qualquer usuário do host. É o mesmo defeito que
`tools/onepassword-smoke` corrigiu ao trocar `--referencia` por
`--referencia-arquivo`.

⚠️ Este processo, com as opções padrão, usa `NavegadorNaoImplementado` — ele
abre e fecha perfis pela Local API, e RECUSA capturar. A captura real é
checkpoint externo. Não existe flag aqui que a habilite.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from broker import adspower as ads
from broker import configuracao as cfg
from broker import segredo as seg
from broker.execucao import ExecutorDoBroker
from broker.servidor import ServidorDoBroker


def principal(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="broker",
        description="Broker local entre 1Password e a Local API do AdsPower (P03-T11).")
    parser.add_argument("--allowlist", required=True, type=Path,
                        help="JSON 0600 com os perfis autorizados")
    parser.add_argument("--porta", type=int, default=None,
                        help="porta de loopback; 0 escolhe uma livre")
    parser.add_argument("--preflight", action="store_true",
                        help="roda só as recusas de preflight e sai")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    try:
        config = cfg.carregar(allowlist=args.allowlist, bind_porta=args.porta)
    except cfg.PreflightRecusado as exc:
        print(f"preflight recusado: {exc}", file=sys.stderr)
        return 2

    if args.preflight:
        print("preflight ok — bind em loopback, token presente, verificação de API exigida.")
        return 0

    executor = ExecutorDoBroker(
        config=config,
        resolvedor=seg.ResolvedorOpCli(),
        cliente=ads.ClienteDoAdsPower(
            config.adspower_base,
            intervalo_minimo_s=config.intervalo_minimo_entre_chamadas_s),
        navegador=ads.NavegadorNaoImplementado(),
    )
    servidor = ServidorDoBroker(config, executor)
    print(f"broker ouvindo em {servidor.base} (loopback)")
    try:
        servidor.servir_para_sempre()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.parar()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(principal())
