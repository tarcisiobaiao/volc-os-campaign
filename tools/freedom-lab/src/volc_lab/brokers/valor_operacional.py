"""Procedência de valores monetários: CPC de SERP ou de ferramenta externa nunca autoriza
verba, lance ou orçamento. Só `operador` e `medido_na_conta` autorizam, e mesmo assim
a recomendação shadow nunca é executada (o tipo nem admite executada=True).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ORIGENS_QUE_AUTORIZAM = frozenset({"operador", "medido_na_conta"})
ORIGENS = frozenset({"operador", "medido_na_conta", "serp", "keyword_planner",
                     "dataforseo", "estimativa_modelo"})
Direcao = Literal["manter", "reduzir", "aumentar", "pausar", "evidencia_insuficiente"]
DIRECOES = ("manter", "reduzir", "aumentar", "pausar", "evidencia_insuficiente")


class ValorSemAutoridade(ValueError):
    pass


@dataclass(frozen=True)
class ValorMonetario:
    micros: int | None  # None = ausência, nunca zero
    origem: str
    evidencia: str

    def __post_init__(self):
        if self.origem not in ORIGENS:
            raise ValorSemAutoridade(f"origem desconhecida {self.origem!r}")
        if self.origem == "medido_na_conta" and "gaql:" not in self.evidencia:
            raise ValorSemAutoridade("medido_na_conta exige evidência gaql:<consulta> lida pelo broker")

    def autoriza(self) -> int:
        if self.origem not in ORIGENS_QUE_AUTORIZAM:
            raise ValorSemAutoridade(f"origem {self.origem!r} é anotação, não autoriza verba")
        if self.micros is None:
            raise ValorSemAutoridade("valor ausente não autoriza nada")
        return self.micros


@dataclass(frozen=True)
class RecomendacaoShadow:
    campanha: str
    direcao: str
    motivos: tuple[str, ...]
    valor_sugerido: ValorMonetario | None = None
    lacunas: tuple[str, ...] = field(default_factory=tuple)
    executada: Literal[False] = False

    def __post_init__(self):
        if self.direcao not in DIRECOES:
            raise ValueError(f"direção inválida {self.direcao!r}")
        if self.executada is not False:
            raise ValueError("recomendação shadow não pode ser executada")
