"""Tipos do shadow engine: proposta, diagnóstico, decisão. Imutáveis e serializáveis sem float.

Regra dura: `PropostaShadow.executavel` é SEMPRE `False`. Construir uma proposta com qualquer
outro valor levanta `ExecucaoProibida`. Uma proposta é um REGISTRO do que a política teria
proposto naquele corte; não existe, neste pacote, caminho que a transforme em mutação de verba,
lance ou campanha.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from typing import Any, Mapping, Optional

BPS = 10_000  # 100% em pontos-base: fator de verba 10_000 = manter


class ExecucaoProibida(RuntimeError):
    """Tentativa de marcar proposta shadow como executável (ou de executá-la)."""


class Acao(str, enum.Enum):
    MANTER = "manter"
    PAUSAR = "pausar"
    REDUZIR_VERBA = "reduzir_verba"
    AUMENTAR_VERBA = "aumentar_verba"
    ALERTA = "alerta"  # sinal para humano; nunca muda verba
    INSUFICIENTE = "insuficiente"  # dado não sustenta decisão (cobertura/maturidade/identidade)


ACOES_DE_CORTE = frozenset({Acao.PAUSAR, Acao.REDUZIR_VERBA})
ACOES_QUE_MUDAM_VERBA = frozenset({Acao.PAUSAR, Acao.REDUZIR_VERBA, Acao.AUMENTAR_VERBA})


class Confianca(str, enum.Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"
    NENHUMA = "nenhuma"


class Severidade(str, enum.Enum):
    INFO = "info"
    AVISO = "aviso"
    CRITICO = "critico"


@dataclass(frozen=True, order=True)
class EntidadeCampanha:
    customer_id: str
    campaign_id: str

    def __post_init__(self) -> None:
        for nome in ("customer_id", "campaign_id"):
            v = getattr(self, nome)
            if not isinstance(v, str) or not v or v != v.strip():
                raise ValueError(f"EntidadeCampanha.{nome} inválido: {v!r}")

    def rotulo(self) -> str:
        return f"{self.customer_id}/{self.campaign_id}"


# --------------------------------------------------------------------------- congelamento JSON-seguro
class DictCongelado(tuple):
    """Tupla de pares (chave, valor) ordenados por chave: um dict imutável, picklável e hasheável."""

    __slots__ = ()

    def como_dict(self) -> dict:
        return dict(self)


def congelar(valor: Any) -> Any:
    """dict → tupla de pares ordenados; list/tuple → tupla. Recusa float (dinheiro não é float)."""
    if isinstance(valor, float):
        raise TypeError("float proibido em evidência shadow; use int (micros/bps) ou Fraction")
    if isinstance(valor, Mapping):
        return DictCongelado(sorted((str(k), congelar(v)) for k, v in valor.items()))
    if isinstance(valor, (list, tuple)):
        return tuple(congelar(v) for v in valor)
    if isinstance(valor, (str, int, bool, type(None), Fraction, date)):
        return valor
    if isinstance(valor, enum.Enum):
        return valor.value
    raise TypeError(f"tipo não aceito em evidência shadow: {type(valor).__name__}")


def para_json_seguro(valor: Any) -> Any:
    """Inverso de `congelar` para serialização: pares → dict; Fraction → 'n/d'; date → ISO."""
    if isinstance(valor, DictCongelado):
        return {k: para_json_seguro(v) for k, v in valor}
    if isinstance(valor, tuple):
        return [para_json_seguro(v) for v in valor]
    if isinstance(valor, Fraction):
        return f"{valor.numerator}/{valor.denominator}"
    if isinstance(valor, date):
        return valor.isoformat()
    return valor


def _evidencia(e: Any) -> "DictCongelado":
    if isinstance(e, DictCongelado):
        return e
    return congelar(dict(e or {}))


# --------------------------------------------------------------------------- proposta e diagnóstico
_FATOR_POR_ACAO = {
    Acao.MANTER: lambda f: f == BPS,
    Acao.ALERTA: lambda f: f == BPS,
    Acao.INSUFICIENTE: lambda f: f == BPS,
    Acao.PAUSAR: lambda f: f == 0,
    Acao.REDUZIR_VERBA: lambda f: 0 < f < BPS,
    Acao.AUMENTAR_VERBA: lambda f: f > BPS,
}


@dataclass(frozen=True)
class PropostaShadow:
    """O que a política TERIA proposto no corte `as_of`. Registro, nunca comando."""

    politica: str
    versao_politica: str
    as_of: str  # instante canônico UTC do corte
    fingerprint_corte: str
    entidade: EntidadeCampanha
    acao: Acao
    fator_bps: int  # verba proposta como fração da atual (10_000 = manter, 0 = pausar)
    confianca: Confianca
    motivo: str
    evidencia: Any = ()
    bloqueios: tuple[str, ...] = ()
    executavel: bool = False

    def __post_init__(self) -> None:
        if self.executavel is not False:
            raise ExecucaoProibida("proposta shadow nunca é executável")
        object.__setattr__(self, "acao", Acao(self.acao))
        object.__setattr__(self, "confianca", Confianca(self.confianca))
        if not isinstance(self.fator_bps, int) or isinstance(self.fator_bps, bool):
            raise TypeError("fator_bps precisa ser int")
        if not _FATOR_POR_ACAO[self.acao](self.fator_bps):
            raise ValueError(f"fator_bps {self.fator_bps} incoerente com ação {self.acao.value}")
        if not isinstance(self.entidade, EntidadeCampanha):
            raise TypeError("entidade precisa ser EntidadeCampanha")
        object.__setattr__(self, "evidencia", _evidencia(self.evidencia))
        object.__setattr__(self, "bloqueios", tuple(sorted(set(self.bloqueios))))

    @property
    def bloqueada(self) -> bool:
        return bool(self.bloqueios)

    @property
    def fator_efetivo_bps(self) -> int:
        """Fator usado na AVALIAÇÃO: proposta bloqueada pelo kernel conta como manter."""
        if self.bloqueada or self.acao not in ACOES_QUE_MUDAM_VERBA:
            return BPS
        return self.fator_bps

    def evidencia_dict(self) -> dict:
        return para_json_seguro(self.evidencia)

    def com_bloqueios(self, novos: tuple[str, ...]) -> "PropostaShadow":
        if not novos:
            return self
        return PropostaShadow(self.politica, self.versao_politica, self.as_of, self.fingerprint_corte, self.entidade,
                              self.acao, self.fator_bps, self.confianca, self.motivo, self.evidencia,
                              tuple(self.bloqueios) + tuple(novos))

    def assinatura(self) -> tuple:
        """Conteúdo de decisão (sem corte/fingerprint): para comparar decisões entre cortes."""
        return (self.entidade.customer_id, self.entidade.campaign_id, self.acao.value, self.fator_bps,
                self.bloqueada)

    def para_json(self) -> dict:
        return {
            "politica": self.politica, "versao_politica": self.versao_politica, "as_of": self.as_of,
            "fingerprint_corte": self.fingerprint_corte,
            "entidade": {"customer_id": self.entidade.customer_id, "campaign_id": self.entidade.campaign_id},
            "acao": self.acao.value, "fator_bps": self.fator_bps, "confianca": self.confianca.value,
            "motivo": self.motivo, "evidencia": self.evidencia_dict(), "bloqueios": list(self.bloqueios),
            "executavel": False,
        }


@dataclass(frozen=True)
class Diagnostico:
    """Constatação sem ação: estado do dado, maturidade, identidade, coleta."""

    politica: str
    as_of: str
    fingerprint_corte: str
    codigo: str
    severidade: Severidade
    detalhe: str
    entidade: Optional[EntidadeCampanha] = None
    evidencia: Any = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "severidade", Severidade(self.severidade))
        object.__setattr__(self, "evidencia", _evidencia(self.evidencia))

    def para_json(self) -> dict:
        return {
            "politica": self.politica, "as_of": self.as_of, "fingerprint_corte": self.fingerprint_corte,
            "codigo": self.codigo, "severidade": self.severidade.value, "detalhe": self.detalhe,
            "entidade": None if self.entidade is None else {"customer_id": self.entidade.customer_id,
                                                           "campaign_id": self.entidade.campaign_id},
            "evidencia": para_json_seguro(self.evidencia),
        }


@dataclass(frozen=True)
class DecisaoShadow:
    propostas: tuple[PropostaShadow, ...] = field(default_factory=tuple)
    diagnosticos: tuple[Diagnostico, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "propostas", tuple(sorted(self.propostas, key=lambda p: p.entidade)))
        object.__setattr__(self, "diagnosticos", tuple(sorted(
            self.diagnosticos, key=lambda d: (d.codigo, d.entidade or EntidadeCampanha("~", "~"), d.detalhe))))
        for p in self.propostas:
            if p.executavel is not False:
                raise ExecucaoProibida("decisão shadow com proposta executável")

    def para_json(self) -> dict:
        return {"propostas": [p.para_json() for p in self.propostas],
                "diagnosticos": [d.para_json() for d in self.diagnosticos]}

    def assinatura(self) -> tuple:
        return tuple(p.assinatura() for p in self.propostas)
