"""Utilidades comuns dos experimentos do Model Lab (worker F). Não é experimento por si.

- caminho do ``src`` do lab no ``sys.path``;
- manifesto: versões, sha256 do código (``fundacao/modelos/*.py`` + script), versão do simulador e do
  catálogo, seeds e parâmetros — sem relógio de parede (mesmas entradas → mesmo JSON);
- comparação pareada com IC por bootstrap de seeds.
Rode os experimentos com ``OMP_NUM_THREADS=2`` (definido pelo chamador, não aqui).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

LAB = Path(__file__).resolve().parents[1]
if str(LAB / "src") not in sys.path:
    sys.path.insert(0, str(LAB / "src"))

import numpy as np  # noqa: E402

from volc_dil.fundacao.modelos.base import VERSAO_MODELOS, ic_bootstrap_media  # noqa: E402
from volc_dil.statlab.base import gravar_json, versoes  # noqa: E402

RESULTADOS = LAB / "results" / "fundacao" / "modelos"
PACOTE = LAB / "src" / "volc_dil" / "fundacao" / "modelos"


def sha256_codigo(script: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(PACOTE.glob("*.py")) + [Path(script)]:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def manifesto(script: str, *, seeds: list[int], parametros: dict[str, Any]) -> dict[str, Any]:
    from volc_dil.fundacao.simulador import VERSAO_CATALOGO, VERSAO_SIMULADOR, catalogo_sha256
    import sklearn

    return {
        "natureza": "simulacao_com_seed_sem_dado_real",
        "teto_de_estado": "testado com sintético",
        "script": Path(script).name,
        "sha256_codigo": sha256_codigo(Path(script)),
        "versoes": {**versoes(), "sklearn": sklearn.__version__, "modelos": VERSAO_MODELOS,
                    "simulador": VERSAO_SIMULADOR, "catalogo": VERSAO_CATALOGO},
        "catalogo_sha256": catalogo_sha256(),
        "seeds": [int(s) for s in seeds],
        "parametros": parametros,
        "pre_registro": "results/fundacao/modelos/PRE-REGISTRO.md",
    }


def pareado(a: Any, b: Any, *, seed: int = 0) -> dict[str, Any]:
    """Diferença pareada a − b por seed, IC95 bootstrap (B = 2000)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    return ic_bootstrap_media(a - b, seed=seed)


def razao_pareada(a: Any, b: Any, *, seed: int = 0) -> dict[str, Any]:
    """Razão de médias a/b com IC95 por bootstrap de seeds (reamostra os pares)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    out = {"estimativa": float(a.mean() / b.mean()) if b.mean() else None, "ic95": [None, None], "n": int(a.size)}
    if a.size >= 2:
        idx = np.random.default_rng(seed).integers(0, a.size, (2000, a.size))
        r = a[idx].mean(1) / b[idx].mean(1)
        out["ic95"] = [float(np.quantile(r, 0.025)), float(np.quantile(r, 0.975))]
    return out


def supera(dif: dict[str, Any], *, direcao: str) -> bool | None:
    """IC95 exclui zero na direção favorável (``menor`` ou ``maior``)."""
    lo, hi = dif["ic95"]
    if lo is None:
        return None
    return bool(hi < 0) if direcao == "menor" else bool(lo > 0)


def gravar(nome: str, obj: dict[str, Any], limite_bytes: int = 400_000) -> Path:
    caminho = RESULTADOS / nome
    gravar_json(caminho, obj, limite_bytes=limite_bytes)
    return caminho


def saida(nome: str, obj: dict[str, Any], *, rapido: bool) -> None:
    """Modo rápido (fumaça): imprime e NÃO grava em results/. Modo normal: grava e imprime o caminho."""
    from volc_dil.statlab.base import para_json

    if rapido:
        print(para_json(obj["resultados"])[:20000])
    else:
        print(gravar(nome, obj))


__all__ = ["LAB", "saida", "RESULTADOS", "gravar", "manifesto", "pareado", "razao_pareada", "supera"]
