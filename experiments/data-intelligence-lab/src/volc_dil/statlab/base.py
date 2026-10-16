"""Utilidades comuns do Stat Lab: versões, IC de Monte Carlo, JSON determinístico.

Convenções:
- ausência é ``None``/NaN tratada explicitamente — nunca vira 0;
- todo resultado de Monte Carlo carrega seed, n de simulações e IC de Monte Carlo;
- o JSON gravado não tem timestamp nem tempo de parede: mesma seed -> mesmo JSON.
"""

from __future__ import annotations

import json
import math
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

VERSAO_STATLAB = "0.1.0"

_Z95 = 1.959963984540054


@dataclass(frozen=True)
class ResultadoInsuficiente:
    """Retorno explícito quando não há base para um número.

    Substitui um número inventado (0, inf, fator explodido) por um status auditável.
    """

    motivo: str
    detalhes: dict[str, Any] = field(default_factory=dict)
    status: str = "insuficiente"

    def como_dict(self) -> dict[str, Any]:
        return {"status": self.status, "motivo": self.motivo, "detalhes": self.detalhes}


def versoes() -> dict[str, str]:
    """Versões de runtime registradas em todo JSON de resultado."""
    import scipy
    import statsmodels

    return {
        "statlab": VERSAO_STATLAB,
        "python": sys.version.split()[0],
        "implementacao": platform.python_implementation(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "statsmodels": statsmodels.__version__,
    }


def ic_proporcao(sucessos: int, n: int) -> dict[str, Any]:
    """Proporção com IC de Wilson 95% (IC de Monte Carlo para taxas de cobertura/erro)."""
    if n <= 0:
        return {"estimativa": None, "ic95": [None, None], "n": int(n)}
    p = sucessos / n
    den = 1 + _Z95**2 / n
    centro = (p + _Z95**2 / (2 * n)) / den
    meia = _Z95 * math.sqrt(p * (1 - p) / n + _Z95**2 / (4 * n * n)) / den
    return {
        "estimativa": p,
        "ic95": [max(0.0, centro - meia), min(1.0, centro + meia)],
        "n": int(n),
    }


def ic_media(valores: Any) -> dict[str, Any]:
    """Média com IC normal 95% de Monte Carlo. NaN são EXCLUÍDOS e contados (não viram 0)."""
    v = np.asarray(valores, dtype=float).ravel()
    finitos = v[np.isfinite(v)]
    n_excluidos = int(v.size - finitos.size)
    n = int(finitos.size)
    if n == 0:
        return {"estimativa": None, "ic95": [None, None], "n": 0, "n_excluidos_nao_finitos": n_excluidos}
    m = float(finitos.mean())
    if n == 1:
        return {"estimativa": m, "ic95": [None, None], "n": 1, "n_excluidos_nao_finitos": n_excluidos}
    ep = float(finitos.std(ddof=1) / math.sqrt(n))
    return {
        "estimativa": m,
        "ic95": [m - _Z95 * ep, m + _Z95 * ep],
        "n": n,
        "n_excluidos_nao_finitos": n_excluidos,
    }


def ic_mediana(valores: Any) -> dict[str, Any]:
    """Mediana com IC 95% por estatística de ordem (binomial). NaN excluídos e contados."""
    v = np.sort(np.asarray(valores, dtype=float).ravel())
    finitos = v[np.isfinite(v)]
    n = int(finitos.size)
    base = {"n": n, "n_excluidos_nao_finitos": int(v.size - n)}
    if n == 0:
        return {"estimativa": None, "ic95": [None, None], **base}
    med = float(np.median(finitos))
    if n < 6:
        return {"estimativa": med, "ic95": [None, None], **base}
    meia = _Z95 * math.sqrt(n) / 2
    lo = int(max(0, math.floor(n / 2 - meia)))
    hi = int(min(n - 1, math.ceil(n / 2 + meia)))
    return {"estimativa": med, "ic95": [float(finitos[lo]), float(finitos[hi])], **base}


def _sanear(obj: Any, casas: int) -> Any:
    if isinstance(obj, dict):
        return {str(k): _sanear(v, casas) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanear(v, casas) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_sanear(v, casas) for v in obj.tolist()]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        if not math.isfinite(f):
            # NaN/inf não são números publicáveis: viram null com marcador textual
            return None if math.isnan(f) else ("+inf" if f > 0 else "-inf")
        if f == 0.0:
            return 0.0
        return float(f"{f:.{casas}g}")
    return obj


def para_json(obj: Any, casas: int = 6) -> str:
    """Serialização determinística: chaves ordenadas, floats com ``casas`` dígitos significativos,
    NaN -> null, inf -> string. Sem timestamp."""
    return json.dumps(_sanear(obj, casas), sort_keys=True, ensure_ascii=False, indent=1, allow_nan=False)


def envelope(experimento: str, seed: int, n_simulacoes: int, parametros: dict[str, Any],
             resultados: Any, conclusoes: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Envelope padrão de resultado: experimento, seed, n de simulações, versões, parâmetros."""
    return {
        "schema": f"volc_dil.statlab.{experimento}/v1",
        "natureza": "simulacao_com_seed_sem_dado_real",
        "seed": int(seed),
        "n_simulacoes": int(n_simulacoes),
        "versoes": versoes(),
        "parametros": parametros,
        "resultados": resultados,
        "conclusoes": conclusoes or [],
    }


def gravar_json(caminho: str | Path, obj: dict[str, Any], limite_bytes: int = 300_000) -> int:
    texto = para_json(obj)
    dados = texto.encode("utf-8")
    if len(dados) > limite_bytes:
        raise ValueError(f"resultado {caminho} tem {len(dados)} bytes > limite {limite_bytes}")
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(dados + b"\n")
    return len(dados)


def rngs(seed: int, n: int) -> list[np.random.Generator]:
    """Geradores independentes e reprodutíveis por réplica (SeedSequence.spawn)."""
    return [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(n)]
