"""Fingerprint canônico (sha256 de JSON ordenado) e manifesto de execução."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from importlib import metadata
from typing import Any, Iterable

PACOTES_RASTREADOS = ("numpy", "scipy", "statsmodels", "scikit-learn", "duckdb", "polars", "pandas")


def json_canonico(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_de(obj: Any) -> str:
    return hashlib.sha256(json_canonico(obj).encode("utf-8")).hexdigest()


def sha256_arquivo(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 16), b""):
            h.update(bloco)
    return h.hexdigest()


def versoes(pacotes: Iterable[str] = PACOTES_RASTREADOS) -> dict[str, str | None]:
    saida: dict[str, str | None] = {"python": sys.version.split()[0], "plataforma": platform.platform()}
    for p in pacotes:
        try:
            saida[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            saida[p] = None
    return saida


def sha256_codigo(caminhos: Iterable[str]) -> str:
    """Hash do código que produziu um resultado. Chave = nome do arquivo (independe da máquina)."""
    import os

    return sha256_de({os.path.basename(c): sha256_arquivo(c) for c in sorted(caminhos)})


def manifesto_execucao(
    *,
    nome: str,
    seed: int | None,
    entradas: dict[str, str],
    parametros: dict,
    codigo_sha256: str | None = None,
    resultado: Any = None,
) -> dict:
    """Manifesto mínimo exigido de todo resultado: sem seed+fingerprint+versões, resultado é inválido.

    O fingerprint cobre seed, entradas, parâmetros e — quando informados — o hash do código e
    o hash do resultado; assim, mudar o código ou o número muda o fingerprint.
    """
    corpo = {
        "nome": nome,
        "seed": seed,
        "entradas_sha256": dict(sorted(entradas.items())),
        "parametros": parametros,
        "codigo_sha256": codigo_sha256,
        "resultado_sha256": sha256_de(resultado) if resultado is not None else None,
        "versoes": versoes(),
    }
    corpo["fingerprint"] = sha256_de({k: v for k, v in corpo.items() if k != "versoes"})
    return corpo
