"""Uma cotação coletada: o que a fonte publicou, para qual dia e quando.

As invariantes espelham os CHECKs da v23_01 em `exchange_rate_history`, para a
recusa acontecer antes da rede e com mensagem que diz o porquê. O banco
continua sendo a última palavra (a guarda carimba `coletado_em` e recusa
duplicata, as_of no futuro e escrita fora da service_role).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Mapping

#: Fonte reservada às linhas manuais de antes da v23_01. Coleta nunca a usa.
FONTE_LEGADA = "legado_manual"
#: Fonte que a guarda da v23_01 dá a toda linha manual nova (as_of do servidor).
FONTE_MANUAL = "manual"

_PAR = re.compile(r"^[A-Z]{3}/[A-Z]{3}$")
_FONTE = re.compile(r"^[a-z0-9_.:-]{3,64}$")
#: Mesma folga de relógio que a guarda do banco aceita.
_FOLGA_FUTURO = timedelta(minutes=5)


class CotacaoInvalida(ValueError):
    """A cotação não pode virar versão: falta dado ou ele é impossível."""


@dataclass(frozen=True)
class Cotacao:
    par: str
    data_referencia: date
    taxa: Decimal
    fonte: str
    #: Instante em que a FONTE publicou o valor (não quando nós lemos).
    as_of: datetime
    proveniencia: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _PAR.match(self.par or ""):
            raise CotacaoInvalida(f"par {self.par!r} fora do formato AAA/BBB")
        if not _FONTE.match(self.fonte or "") or self.fonte in (FONTE_LEGADA, FONTE_MANUAL):
            raise CotacaoInvalida(f"fonte {self.fonte!r} inválida para coleta")
        if not isinstance(self.taxa, Decimal) or not self.taxa.is_finite() or self.taxa <= 0:
            raise CotacaoInvalida(f"taxa {self.taxa!r} precisa ser Decimal finito > 0")
        if self.as_of.tzinfo is None:
            raise CotacaoInvalida("as_of sem fuso: o instante da fonte fica ambíguo")
        if type(self.data_referencia) is not date:
            raise CotacaoInvalida("data_referencia precisa ser date")

    def validar_contra(self, agora: datetime) -> None:
        if self.as_of > agora + _FOLGA_FUTURO:
            raise CotacaoInvalida(f"as_of {self.as_of.isoformat()} está no futuro")

    def como_linha(self) -> Dict[str, Any]:
        """Linha de `exchange_rate_history`. `coletado_em` fica de fora: é do banco."""
        return {
            "par": self.par,
            "effective_date": self.data_referencia.isoformat(),
            "rate": str(self.taxa),
            "fonte": self.fonte,
            "as_of": self.as_of.astimezone(timezone.utc).isoformat(),
            "proveniencia": dict(self.proveniencia),
        }
