"""Registro das famílias de coleta. Cada módulo deste pacote exporta `FAMILIA`.

Descoberta automática por módulo: adicionar uma família é adicionar um arquivo,
sem editar este registro (duas famílias novas nunca disputam a mesma linha).
"""
from __future__ import annotations

import importlib
import pkgutil


def todas() -> dict:
    out = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_") or info.name.startswith("testes_"):
            continue
        mod = importlib.import_module(f"{__name__}.{info.name}")
        fam = getattr(mod, "FAMILIA", None)
        if fam is not None:
            out[fam.nome] = fam
    return out
