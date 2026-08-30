"""Ponto de entrada do motor de pautas.

    python -m motor_pautas.cli --espaco     pontua termos declarados
    python -m motor_pautas.cli --grafo      resumo do grafo
    python -m motor_pautas.cli --prescrever prescrição do dia
    python -m motor_pautas.cli --eixos      lista eixos e níveis válidos
"""

from __future__ import annotations

import argparse
import datetime
import json

from . import cli_espaco
from .espaco import FAMILIAS, PRIORES, PORTOES
from .grafo.construir import construir
from .grafo.prescrever import prescrever


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="motor_pautas")
    ap.add_argument("--espaco", action="store_true", help="smoke test do espaço")
    ap.add_argument("--grafo", action="store_true", help="resumo do grafo")
    ap.add_argument("--prescrever", action="store_true", help="prescrição do dia")
    ap.add_argument("--eixos", action="store_true")
    ap.add_argument("--hoje", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.eixos:
        return cli_espaco.main(["--eixos"])
    if a.espaco:
        return cli_espaco.main(["--smoke"])

    if a.grafo:
        g = construir()
        print(json.dumps(g.resumo(), ensure_ascii=False, indent=1))
        print(f"\ncélulas vazias em arquétipos provados em 2+ países: "
              f"{len(g.celulas_vazias())}")
        return 0

    if a.prescrever:
        hoje = datetime.date.fromisoformat(a.hoje) if a.hoje else datetime.date.today()
        r = prescrever(construir(), hoje)
        if a.json:
            print(json.dumps({
                "data": r["data"],
                "transpor": [{"arquetipo": p.arquetipo, "pais": p.pais,
                              "indice": p.indice, "perfil": p.perfil,
                              "pergunta": p.pergunta, "porque": p.porque,
                              "falta": p.falta_descobrir} for p in r["transpor"]],
                "ativar": [{"entidade": p.entidade, "arquetipo": p.arquetipo,
                            "pais": p.pais, "indice": p.indice, "perfil": p.perfil,
                            "evento": p.evento, "porque": p.porque} for p in r["ativar"]],
                "retidos": r["retidos"],
            }, ensure_ascii=False, indent=1))
            return 0
        print(f"PRESCRIÇÃO · {r['data']}   ({r['celulas_vazias_total']} células vazias)")
        for acao in ("ativar", "transpor"):
            print(f"\n▸ {acao.upper()}   (+{r['retidos'][acao]} retidos pelo teto)")
            for p in r[acao]:
                alvo = p.entidade or p.arquetipo
                print(f"  {p.indice or 0:5.3f}  {p.pais:<5} {alvo[:34]:<34} {p.perfil}")
                for x in p.porque[:2]:
                    print(f"         · {x[:84]}")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
