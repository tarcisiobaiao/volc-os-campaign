"""`ValorMonetario`: todo número que vira verba ou lance diz de onde veio.

Sem isto, `AlterarOrcamento(…, 35_000_000)` não distinguia um valor digitado
pelo operador de um CPC de SERP, de uma ideia do Keyword Planner ou de uma
estimativa de modelo — e qualquer um deles autorizaria verba.

A regra (C-google.md, 15/10): só duas origens LIBERAM dinheiro.

  operador         um humano digitou ou aprovou o número.
                   evidência: `operador:<quem>@<quando>`
  medido_na_conta  o número foi LIDO na própria conta Google Ads.
                   evidência: a GAQL que o leu (com o campo de dinheiro)

Qualquer outra origem (serp, keyword_planner, dataforseo, ferramenta_externa,
estimativa_modelo, nao_informada) é ANOTAÇÃO: o valor pode existir, ser
mostrado e ser gravado, mas `autoriza()` levanta. As ações de gestão chamam
`autoriza()` dentro de `operacoes()` — a função que monta a `MutateOperation`
—, então a recusa vem antes de existir requisição, no `validate_only` também.

`micros=None` é ausência, nunca zero, e também não autoriza nada.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


Origem = Literal["operador", "medido_na_conta", "serp", "keyword_planner", "dataforseo",
                 "ferramenta_externa", "estimativa_modelo", "nao_informada"]
ORIGENS: frozenset[str] = frozenset(Origem.__args__)  # type: ignore[attr-defined]
ORIGENS_QUE_AUTORIZAM: frozenset[str] = frozenset({"operador", "medido_na_conta"})

_EVIDENCIA_OPERADOR = re.compile(r"operador:\S+@\S+")
#: Campos de dinheiro que a conta devolve. A evidência de `medido_na_conta`
#: precisa ser uma GAQL que lê um deles — "medi na conta" sem a consulta é
#: só uma frase.
CAMPOS_MEDIDOS: tuple[str, ...] = (
    "campaign_budget.amount_micros",
    "campaign.target_spend.cpc_bid_ceiling_micros",
    "campaign.maximize_conversions.target_cpa_micros",
    "campaign.target_cpa.target_cpa_micros",
    "metrics.average_cpc",
    "metrics.cost_micros",
)


class AcaoRecusada(ValueError):
    """A ação não sai da máquina: inválida em si, ou incompatível com o "antes".

    Mora aqui (e `acoes.py` a reexporta) para `ValorSemAutoridade` ser uma
    recusa de ação sem import circular.
    """


class ValorSemAutoridade(AcaoRecusada):
    """O número existe, mas a origem dele não libera verba nem lance."""


@dataclass(frozen=True)
class ValorMonetario:
    micros: int | None
    origem: str
    evidencia: str

    def __post_init__(self):
        if self.origem not in ORIGENS:
            raise AcaoRecusada(
                f"origem de valor desconhecida: {self.origem!r} (válidas: {sorted(ORIGENS)})")
        if self.micros is not None and (isinstance(self.micros, bool)
                                        or not isinstance(self.micros, int)):
            raise AcaoRecusada(f"micros tem de ser inteiro ou None: {self.micros!r}")
        if not isinstance(self.evidencia, str) or not self.evidencia.strip():
            raise AcaoRecusada(f"valor de origem {self.origem!r} sem evidência")

    def autoriza(self) -> int:
        """O único jeito de um número virar verba ou lance. Estimativa nunca passa."""
        if self.origem not in ORIGENS_QUE_AUTORIZAM:
            raise ValorSemAutoridade(
                f"origem {self.origem!r} é anotação, não autoriza verba nem lance "
                f"(só {sorted(ORIGENS_QUE_AUTORIZAM)})")
        if self.micros is None:
            raise ValorSemAutoridade("valor ausente não autoriza nada")
        if self.origem == "operador" and not _EVIDENCIA_OPERADOR.fullmatch(self.evidencia):
            raise ValorSemAutoridade(
                f"origem operador exige evidência `operador:<quem>@<quando>`: {self.evidencia!r}")
        if self.origem == "medido_na_conta":
            gaql = self.evidencia.upper()
            if ("SELECT" not in gaql or " FROM " not in gaql
                    or not any(c in self.evidencia for c in CAMPOS_MEDIDOS)):
                raise ValorSemAutoridade(
                    "origem medido_na_conta exige a GAQL que leu o valor, com um de "
                    f"{list(CAMPOS_MEDIDOS)}: {self.evidencia[:200]!r}")
        return self.micros

    def json(self) -> dict:
        """O que vai para `valor_proposto.origem_valor` (o número já está ao lado)."""
        return {"origem": self.origem, "evidencia": self.evidencia}


def operador(micros: int, quem: str, quando: str) -> ValorMonetario:
    return ValorMonetario(micros, "operador", f"operador:{quem}@{quando}")


def medido_na_conta(micros: int, gaql: str) -> ValorMonetario:
    return ValorMonetario(micros, "medido_na_conta", gaql)
