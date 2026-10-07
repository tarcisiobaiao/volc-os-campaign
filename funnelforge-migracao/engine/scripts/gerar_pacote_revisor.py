"""Gera `src/funnelforge/politicas/pacote_revisor.json` a partir do ledger da Frente A.

Uso (da pasta do motor, sem rede, sem LLM):

    PYTHONPATH=src .venv/bin/python scripts/gerar_pacote_revisor.py \
        --ledger ../../.claude-ads/runs/editorial-refactor-20260930/frente-a-politicas/ledger.json \
        --dono "operador VOLC (Frente A · políticas oficiais)"

Refresh: a cada 30 dias (o pacote declara `valido_ate`). Quem regenera consulta
de novo as páginas oficiais na Frente A, atualiza o ledger e roda este script.
O pacote nunca é editado à mão.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from funnelforge.politicas import CAMINHO_DO_PACOTE, gerar_pacote


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", type=Path, required=True)
    ap.add_argument("--dono", required=True)
    ap.add_argument("--gerado-em", default=date.today().isoformat())
    ap.add_argument("--saida", type=Path, default=CAMINHO_DO_PACOTE)
    ap.add_argument("--nome-da-fonte", default=None,
                    help="caminho declarado da fonte (padrão: o --ledger como veio)")
    args = ap.parse_args(argv)
    bruto = args.ledger.read_bytes()
    ledger = json.loads(bruto.decode("utf-8"))
    pacote = gerar_pacote(
        ledger, gerado_em=date.fromisoformat(args.gerado_em), dono=args.dono,
        fonte={"arquivo": args.nome_da_fonte or str(args.ledger),
               "sha256": hashlib.sha256(bruto).hexdigest()})
    args.saida.write_text(json.dumps(pacote, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")
    print(f"{args.saida}: {len(pacote['regras'])} regras A/B, {len(pacote['notas_c'])} notas C, "
          f"válido até {pacote['valido_ate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
