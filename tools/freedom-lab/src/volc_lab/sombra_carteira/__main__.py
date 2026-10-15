"""CLI do motor shadow da carteira.

    # gerar a partir de snapshots exportados (replay, nuvem, testes)
    PYTHONPATH=tools/freedom-lab/src python -m volc_lab.sombra_carteira gerar \\
        --conta 1234567890 --custo custo.json --receita receita.json --cambio cambio.json \\
        --destino tools/freedom-lab/experimentos --base-ref $(git rev-parse HEAD)

    # gerar lendo o Supabase oficial (só no servidor; service_role vem do ambiente)
    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... python -m volc_lab.sombra_carteira gerar \\
        --conta 1234567890 --postgrest --destino /var/lib/volc-sombra-carteira/experimentos --base-ref ...

    # conferir um experimento gravado: recalcula do próprio recorte e compara bytes
    python -m volc_lab.sombra_carteira replay <pasta-do-experimento>

Saída 0: lote gravado ou já idêntico. 2: lote recusado (nada escrito).
3: contrato de entrada quebrado. 1: replay divergente.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from volc_lab.sombra_carteira import adaptadores, aplicacao
from volc_lab.sombra_carteira.portas import ContratoQuebrado

# Parâmetros que a agenda pode sobrescrever sem mexer em código.
_PARAMETROS = ("janela_dias", "dias_imaturos", "min_cliques_maduros", "max_custo_sem_receita",
               "max_defasagem_cambio_dias")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="volc_lab.sombra_carteira")
    sub = ap.add_subparsers(dest="acao", required=True)
    g = sub.add_parser("gerar")
    g.add_argument("--conta", required=True)
    g.add_argument("--destino", required=True, type=Path)
    g.add_argument("--base-ref", required=True)
    g.add_argument("--custo", type=Path)
    g.add_argument("--receita", type=Path)
    g.add_argument("--cambio", type=Path, help="respostas de cambio_resolver exportadas (snapshot)")
    g.add_argument("--postgrest", action="store_true")
    for nome in _PARAMETROS:
        g.add_argument(f"--{nome.replace('_', '-')}", type=float)
    r = sub.add_parser("replay")
    r.add_argument("pasta", type=Path)
    a = ap.parse_args(argv)

    if a.acao == "replay":
        saida = aplicacao.replay(a.pasta)
        print(json.dumps(saida, ensure_ascii=False))
        return 0 if saida["identico"] else 1

    if a.postgrest == bool(a.custo or a.receita or a.cambio):
        ap.error("use --postgrest OU --custo, --receita e --cambio")
    if a.postgrest:
        leitor = adaptadores.PostgrestSoLeitura(os.environ.get("SUPABASE_URL", ""),
                                                os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))
        fonte_custo, fonte_receita, fonte_cambio = leitor, leitor, leitor
    else:
        if not (a.custo and a.receita and a.cambio):
            ap.error("--custo, --receita e --cambio andam juntos")
        fonte_custo = adaptadores.SnapshotCusto(a.custo)
        fonte_receita = adaptadores.SnapshotReceita(a.receita)
        fonte_cambio = adaptadores.SnapshotCambio(a.cambio)
    parametros = {n: getattr(a, n) for n in _PARAMETROS if getattr(a, n) is not None}
    try:
        saida = aplicacao.gerar_lote(
            a.conta.replace("-", ""), fonte_custo, fonte_receita, fonte_cambio, a.destino,
            base_ref=a.base_ref, hoje=datetime.now(ZoneInfo("America/Sao_Paulo")).date(),
            parametros=parametros,
        )
    except aplicacao.LoteRecusado as exc:
        print(f"LOTE RECUSADO: {exc}", file=sys.stderr)
        return 2
    except ContratoQuebrado as exc:
        print(f"CONTRATO QUEBRADO: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(saida, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
