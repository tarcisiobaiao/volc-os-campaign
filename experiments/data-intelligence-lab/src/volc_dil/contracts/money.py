"""Dinheiro em micros inteiros com moeda explícita. Sem float, sem câmbio implícito."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Union

MICROS = 1_000_000
_MOEDA = re.compile(r"^[A-Z]{3}$")


class MoedasDiferentes(ValueError):
    """Operação entre moedas diferentes: o laboratório não converte câmbio."""


@dataclass(frozen=True)
class Dinheiro:
    micros: int
    moeda: str

    def __post_init__(self) -> None:
        if not isinstance(self.micros, int) or isinstance(self.micros, bool):
            raise TypeError("micros precisa ser int (dinheiro não entra como float)")
        if not isinstance(self.moeda, str) or not _MOEDA.match(self.moeda):
            raise ValueError(f"moeda inválida: {self.moeda!r}")

    @classmethod
    def de_decimal(cls, valor: Union[Decimal, str, int], moeda: str) -> "Dinheiro":
        if isinstance(valor, float):
            raise TypeError("dinheiro não entra como float; use Decimal ou str")
        micros = (Decimal(valor) * MICROS).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
        return cls(int(micros), moeda)

    def decimal(self) -> Decimal:
        return Decimal(self.micros) / MICROS

    def _mesma(self, outro: object) -> "Dinheiro":
        if not isinstance(outro, Dinheiro):
            raise TypeError("operação de dinheiro com não-dinheiro")
        if outro.moeda != self.moeda:
            raise MoedasDiferentes(f"{self.moeda} × {outro.moeda}")
        return outro

    def __add__(self, outro: "Dinheiro") -> "Dinheiro":
        o = self._mesma(outro)
        return Dinheiro(self.micros + o.micros, self.moeda)

    def __sub__(self, outro: "Dinheiro") -> "Dinheiro":
        o = self._mesma(outro)
        return Dinheiro(self.micros - o.micros, self.moeda)

    def eh_zero(self) -> bool:
        return self.micros == 0

    def para_json(self) -> dict:
        return {"micros": self.micros, "moeda": self.moeda}

    @classmethod
    def de_json(cls, d: dict) -> "Dinheiro":
        # Sem coerção: `1.5` ou `"1500"` em micros é erro de contrato, não arredondamento.
        return cls(d["micros"], d["moeda"])
