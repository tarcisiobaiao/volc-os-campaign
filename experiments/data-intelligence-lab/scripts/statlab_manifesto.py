"""Manifesto do Stat Lab: os JSONs do statlab trazem seed e versões, mas não fingerprint nem hash
de código. Este script (integrador) grava results/statlab/MANIFEST.json com sha256 de cada resultado,
hash do código que os produz, seed e versões. Rodar depois de regenerar os JSONs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "src"))

from volc_dil.contracts import manifesto_execucao, sha256_arquivo, sha256_codigo  # noqa: E402

res = LAB / "results" / "statlab"
jsons = sorted(p for p in res.glob("*.json") if p.name != "MANIFEST.json")
seeds = {p.name: json.loads(p.read_text(encoding="utf-8")).get("seed") for p in jsons}
codigo = sha256_codigo([str(p) for p in (LAB / "src" / "volc_dil" / "statlab").glob("*.py")]
                       + [str(p) for p in (LAB / "scripts").glob("statlab_*.py") if p.name != Path(__file__).name])
m = manifesto_execucao(nome="statlab_fase4", seed=None, entradas={}, parametros={"seeds_por_resultado": seeds},
                       codigo_sha256=codigo, resultado={p.name: sha256_arquivo(str(p)) for p in jsons})
m["resultados_sha256"] = {p.name: sha256_arquivo(str(p)) for p in jsons}
(res / "MANIFEST.json").write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
print(m["fingerprint"])
