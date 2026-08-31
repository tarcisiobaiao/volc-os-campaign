"""Observables medidos, não declarados.

O baseline aceitava um dicionário ``observable`` fornecido pelo caller. Nada
garantia que aquele 403 tinha sido observado — podia ser digitado. Um ratchet que
confia no valor que o interessado declara não protege nada.

Aqui todo observable nasce de um extrator tipado, com proveniência e digest da
saída de onde ele foi lido.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .failures import FailureClass, HarnessFailure


@dataclass(frozen=True)
class Observed:
    dimension: str
    value: Any
    extractor: str
    provenance: str          # de onde saiu: gate stdout, arquivo, resposta HTTP
    source_digest: str       # digest da saída medida

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "extractor": self.extractor,
            "provenance": self.provenance,
            "source_digest": self.source_digest,
        }


def _digest(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


def http_status_extractor(dimension: str, padrao: str) -> Callable[[str, str], Observed | None]:
    """Extrai um status HTTP da saída de um gate, por regex declarada."""

    compilado = re.compile(padrao)

    def extrair(saida: str, provenance: str) -> Observed | None:
        m = compilado.search(saida)
        if m is None:
            return None
        bruto = m.group(1) if m.groups() else m.group(0)
        return Observed(
            dimension=dimension,
            value=int(bruto) if bruto.isdigit() else bruto,
            extractor=f"regex({padrao})",
            provenance=provenance,
            source_digest=_digest(saida),
        )

    return extrair


def measure_observables(
    *,
    saida: str,
    provenance: str,
    extractors: Mapping[str, Callable[[str, str], Observed | None]],
) -> dict[str, Observed]:
    """Roda cada extrator sobre a saída real do gate."""

    medidos: dict[str, Observed] = {}
    for nome, extrator in extractors.items():
        obs = extrator(saida, provenance)
        if obs is not None:
            medidos[nome] = obs
    return medidos


def assert_measured(
    observables: Mapping[str, Any], *, dimension: str
) -> Observed:
    """Recusa observable sem proveniência. Valor declarado à mão não vale."""

    valor = observables.get(dimension)
    if valor is None:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            f"dimensão '{dimension}' não foi medida",
            detalhe="o ratchet exige observable com extrator e proveniência",
        )
    if not isinstance(valor, Observed):
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            f"dimensão '{dimension}' foi declarada, não medida",
            detalhe=f"tipo recebido: {type(valor).__name__}; esperado Observed",
            reproducao="use measure_observables() com um extrator tipado",
        )
    return valor
