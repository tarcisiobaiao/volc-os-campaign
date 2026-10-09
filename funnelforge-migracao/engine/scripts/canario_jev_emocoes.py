#!/usr/bin/env python3
"""Canário read-only do perfil emocional JEV: uma chamada, nenhum retry."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE / "src"))

from funnelforge.adapters.decisao_intencao import JevDeIntencao  # noqa: E402
from funnelforge.domain.dossie import sha256_canonico  # noqa: E402
from funnelforge.pipeline.inteligencia import chave_da_pergunta  # noqa: E402


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tema", required=True)
    parser.add_argument("--pais", required=True)
    parser.add_argument("--idioma", default="pt-BR")
    parser.add_argument(
        "--pergunta",
        action="append",
        required=True,
        help="Repita para cada pergunta real de busca/PAA.",
    )
    parser.add_argument("--saida", type=Path)
    return parser.parse_args()


def main() -> int:
    args = argumentos()
    if not (os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY")):
        print(
            "ERRO: exporte TYPESAFE_API_KEY na sessão; nenhum arquivo de segredo é lido.",
            file=sys.stderr,
        )
        return 2
    inicio = time.perf_counter()
    provedor = JevDeIntencao(enabled=True, timeout=30.0)
    duvida_ids = ["q_" + sha256_canonico(chave_da_pergunta(q))[:12] for q in args.pergunta]
    resultado = provedor.classificar(
        args.pergunta,
        contexto={
            "tema": args.tema,
            "pais": args.pais,
            "idioma": args.idioma,
            "duvida_ids": duvida_ids,
        },
    )
    recibo = {
        "tema": args.tema,
        "pais": args.pais,
        "idioma": args.idioma,
        "latencia_ms": round((time.perf_counter() - inicio) * 1000),
        "chamadas": provedor.chamadas,
        "resultado": resultado,
    }
    texto = json.dumps(recibo, ensure_ascii=False, indent=2)
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(texto + "\n", encoding="utf-8")
    print(texto)
    perfil = resultado.get("perfil_emocional") or {}
    if resultado.get("fallback") or perfil.get("estado") != "presente":
        print("ERRO: JEV não produziu um perfil real; o fallback foi preservado.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
