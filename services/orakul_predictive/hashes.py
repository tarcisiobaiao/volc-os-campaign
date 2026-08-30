"""Hashes canônicos e chaves de idempotência. Determinísticos, sem relógio oculto."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def hash_canonico(valor: object) -> str:
    def canonico(item: object) -> object:
        if isinstance(item, Mapping):
            return {str(k): canonico(v) for k, v in sorted(item.items(), key=lambda par: str(par[0]))}
        if isinstance(item, (list, tuple)):
            return [canonico(v) for v in item]
        if isinstance(item, bool):
            return item
        if item is None:
            return None
        if isinstance(item, (int, float)):
            return item
        return str(item)

    bruto = json.dumps(
        canonico(valor),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def chave_idempotencia(**partes: Any) -> str:
    return hash_canonico(partes)


def id_canonico(kind: str, **partes: Any) -> str:
    """ID opaco e estável; nenhuma concatenação ambígua entre contas/cenários."""

    return f"{kind}:{hash_canonico({'kind': kind, **partes})}"


def pair_id_d1(
    *,
    conta_id: str,
    campanha_id: str,
    origin_date: str,
    target_date: str,
    alvo: str,
    cenario: str,
    target_definition: str,
) -> str:
    """Identidade do par previsão/realizado, deliberadamente sem modelo."""

    from .excecoes import ContratoInvalido
    from .relogio import exigir_target_d1

    if not conta_id or not campanha_id or not alvo or not cenario or not target_definition:
        raise ContratoInvalido("pair_id sem identidade completa")
    exigir_target_d1(origin_date, target_date, 1)

    return id_canonico(
        "pair",
        conta_id=conta_id,
        campanha_id=campanha_id,
        origin_date=origin_date,
        target_date=target_date,
        alvo=alvo,
        cenario=cenario,
        target_definition=target_definition,
        horizonte_dias=1,
    )


def hash_codigo_pacote(textos: Mapping[str, str]) -> str:
    return hash_canonico(dict(sorted(textos.items())))
