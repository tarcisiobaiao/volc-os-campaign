"""Contrato tipado de entrada do kernel de viabilidade.

Regras que o contrato impõe por construção (não por convenção):
- ausência nunca vira zero: `valor=None` ⇔ evidência sem valor (`absent`, `unknown`, `invalid`);
- toda medida carrega `disponivel_em` e nenhuma pode ser posterior ao `as_of` da entrada;
- dinheiro é `Dinheiro` (micros inteiros + moeda ISO); razões são `Decimal`;
- moeda atestada é um estado distinto de moeda observada e nunca é promovida aqui;
- a tolerância de perda do owner é um valor fornecido, nunca derivado.
"""
from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional

from volc_dil.contracts import Dinheiro


class ContratoViabilidadeViolado(ValueError):
    """Entrada que não respeita o contrato de viabilidade."""


class Evidencia(str, enum.Enum):
    OBSERVED = "observed"      # a fonte reportou e a janela fechou
    ATTESTED = "attested"      # afirmado pelo owner/parceiro, não observado na fonte
    RECONCILED = "reconciled"  # reconciliado no grão em que a fonte prova
    ESTIMATED = "estimated"    # estimativa/nowcast/literal assumido
    PROJECTED = "projected"    # projeção para frente; nunca realizado
    ABSENT = "absent"          # a fonte respondeu e não há valor
    UNKNOWN = "unknown"        # não se sabe (não coletado, não informado)
    INVALID = "invalid"        # a fonte respondeu algo que viola o contrato
    IMMATURE = "immature"      # valor existe mas a janela ainda não maturou


COM_VALOR = frozenset({Evidencia.OBSERVED, Evidencia.ATTESTED, Evidencia.RECONCILED, Evidencia.ESTIMATED, Evidencia.PROJECTED, Evidencia.IMMATURE})
SEM_VALOR = frozenset({Evidencia.ABSENT, Evidencia.UNKNOWN, Evidencia.INVALID})
# Evidência que pode compor um fato REALIZADO (nunca estimativa/projeção/imaturo).
REALIZADA = frozenset({Evidencia.OBSERVED, Evidencia.RECONCILED})
# Força relativa, do mais forte para o mais fraco (para a invariante "evidência mais fraca nunca é mais permissiva").
FORCA = {
    Evidencia.RECONCILED: 6, Evidencia.OBSERVED: 5, Evidencia.ATTESTED: 4, Evidencia.IMMATURE: 3,
    Evidencia.ESTIMATED: 2, Evidencia.PROJECTED: 1, Evidencia.UNKNOWN: 0, Evidencia.ABSENT: 0, Evidencia.INVALID: -1,
}


def _instante(nome: str, v: Optional[datetime]) -> datetime:
    if v is None:
        raise ContratoViabilidadeViolado(f"{nome} é obrigatório")
    if not isinstance(v, datetime):
        raise ContratoViabilidadeViolado(f"{nome} precisa ser datetime")
    if v.tzinfo is None or v.utcoffset() is None:
        raise ContratoViabilidadeViolado(f"{nome} sem timezone")
    return v


def _decimal(nome: str, v: Any, permitir_none: bool = False) -> Optional[Decimal]:
    if v is None:
        if permitir_none:
            return None
        raise ContratoViabilidadeViolado(f"{nome} é obrigatório")
    if isinstance(v, float):
        raise ContratoViabilidadeViolado(f"{nome} não entra como float")
    try:
        return Decimal(str(v)) if not isinstance(v, Decimal) else v
    except InvalidOperation as e:  # pragma: no cover
        raise ContratoViabilidadeViolado(f"{nome} inválido: {v!r}") from e


@dataclass(frozen=True)
class MedidaMonetaria:
    valor: Optional[Dinheiro]
    evidencia: Evidencia
    moeda_evidencia: Evidencia
    disponivel_em: datetime
    fonte: str = ""

    def __post_init__(self) -> None:
        _instante("disponivel_em", self.disponivel_em)
        if self.evidencia in SEM_VALOR and self.valor is not None:
            raise ContratoViabilidadeViolado(f"evidência {self.evidencia.value} não pode carregar valor (ausência não é zero)")
        if self.evidencia in COM_VALOR and self.valor is None:
            raise ContratoViabilidadeViolado(f"evidência {self.evidencia.value} exige valor")
        if self.valor is not None and not isinstance(self.valor, Dinheiro):
            raise ContratoViabilidadeViolado("valor monetário precisa ser Dinheiro (micros)")

    def tem_valor(self) -> bool:
        return self.valor is not None

    def para_json(self) -> dict:
        return {"valor": None if self.valor is None else self.valor.para_json(), "evidencia": self.evidencia.value,
                "moeda_evidencia": self.moeda_evidencia.value, "disponivel_em": self.disponivel_em.isoformat(), "fonte": self.fonte}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "MedidaMonetaria":
        return cls(valor=None if d.get("valor") is None else Dinheiro.de_json(d["valor"]), evidencia=Evidencia(d["evidencia"]),
                   moeda_evidencia=Evidencia(d["moeda_evidencia"]), disponivel_em=datetime.fromisoformat(d["disponivel_em"]), fonte=d.get("fonte", ""))


@dataclass(frozen=True)
class MedidaContagem:
    valor: Optional[int]
    evidencia: Evidencia
    disponivel_em: datetime
    fonte: str = ""

    def __post_init__(self) -> None:
        _instante("disponivel_em", self.disponivel_em)
        if self.evidencia in SEM_VALOR and self.valor is not None:
            raise ContratoViabilidadeViolado("contagem ausente não pode carregar valor")
        if self.evidencia in COM_VALOR and self.valor is None:
            raise ContratoViabilidadeViolado("contagem com evidência exige valor")
        if self.valor is not None and (not isinstance(self.valor, int) or isinstance(self.valor, bool) or self.valor < 0):
            raise ContratoViabilidadeViolado("contagem precisa ser int >= 0")

    def tem_valor(self) -> bool:
        return self.valor is not None

    def para_json(self) -> dict:
        return {"valor": self.valor, "evidencia": self.evidencia.value, "disponivel_em": self.disponivel_em.isoformat(), "fonte": self.fonte}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "MedidaContagem":
        return cls(valor=d.get("valor"), evidencia=Evidencia(d["evidencia"]), disponivel_em=datetime.fromisoformat(d["disponivel_em"]), fonte=d.get("fonte", ""))


@dataclass(frozen=True)
class Cambio:
    """Taxa de câmbio com proveniência. `evidencia`: observed (PTAX datado), attested, estimated (literal), unknown/absent."""
    taxa: Optional[Decimal]
    de: str
    para: str
    proveniencia: str
    evidencia: Evidencia

    def __post_init__(self) -> None:
        object.__setattr__(self, "taxa", _decimal("cambio.taxa", self.taxa, permitir_none=True))
        if self.evidencia in SEM_VALOR and self.taxa is not None:
            raise ContratoViabilidadeViolado("câmbio ausente não pode carregar taxa")
        if self.evidencia in COM_VALOR and (self.taxa is None or self.taxa <= 0):
            raise ContratoViabilidadeViolado("câmbio com evidência exige taxa > 0")

    def para_json(self) -> dict:
        return {"taxa": None if self.taxa is None else str(self.taxa), "de": self.de, "para": self.para, "proveniencia": self.proveniencia, "evidencia": self.evidencia.value}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "Cambio":
        return cls(taxa=None if d.get("taxa") is None else Decimal(d["taxa"]), de=d["de"], para=d["para"], proveniencia=d.get("proveniencia", ""), evidencia=Evidencia(d["evidencia"]))


@dataclass(frozen=True)
class Taxa:
    """Fração 0..1 (revshare líquido ao publisher, imposto) com proveniência."""
    valor: Optional[Decimal]
    evidencia: Evidencia
    proveniencia: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "valor", _decimal("taxa.valor", self.valor, permitir_none=True))
        if self.evidencia in SEM_VALOR and self.valor is not None:
            raise ContratoViabilidadeViolado("taxa ausente não pode carregar valor")
        if self.valor is not None and not (Decimal(0) <= self.valor <= Decimal(1)):
            raise ContratoViabilidadeViolado("taxa precisa estar em [0, 1]")

    def para_json(self) -> dict:
        return {"valor": None if self.valor is None else str(self.valor), "evidencia": self.evidencia.value, "proveniencia": self.proveniencia}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "Taxa":
        return cls(valor=None if d.get("valor") is None else Decimal(d["valor"]), evidencia=Evidencia(d["evidencia"]), proveniencia=d.get("proveniencia", ""))


@dataclass(frozen=True)
class PerdaMaxima:
    """Tolerância financeira do owner. NUNCA derivada: `valor=None` significa 'não informada'."""
    valor: Optional[Dinheiro]
    horizonte_dias: Optional[int]
    proveniencia: str

    def __post_init__(self) -> None:
        if self.valor is not None and not isinstance(self.valor, Dinheiro):
            raise ContratoViabilidadeViolado("perda_maxima.valor precisa ser Dinheiro")
        if self.valor is not None and self.valor.micros <= 0:
            raise ContratoViabilidadeViolado("perda_maxima precisa ser > 0 quando informada")
        if self.horizonte_dias is not None and (not isinstance(self.horizonte_dias, int) or self.horizonte_dias <= 0):
            raise ContratoViabilidadeViolado("horizonte_dias precisa ser int > 0")

    def informada(self) -> bool:
        return self.valor is not None and self.horizonte_dias is not None

    def para_json(self) -> dict:
        return {"valor": None if self.valor is None else self.valor.para_json(), "horizonte_dias": self.horizonte_dias, "proveniencia": self.proveniencia}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "PerdaMaxima":
        return cls(valor=None if d.get("valor") is None else Dinheiro.de_json(d["valor"]), horizonte_dias=d.get("horizonte_dias"), proveniencia=d.get("proveniencia", ""))


@dataclass(frozen=True)
class JanelaObservada:
    inicio: str  # ISO date
    fim: str
    dias_maduros: int
    dias_imaturos: int = 0

    def __post_init__(self) -> None:
        for n in ("dias_maduros", "dias_imaturos"):
            v = getattr(self, n)
            if not isinstance(v, int) or v < 0:
                raise ContratoViabilidadeViolado(f"{n} precisa ser int >= 0")
        if self.inicio > self.fim:
            raise ContratoViabilidadeViolado("janela: inicio > fim")

    def para_json(self) -> dict:
        return {"inicio": self.inicio, "fim": self.fim, "dias_maduros": self.dias_maduros, "dias_imaturos": self.dias_imaturos}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "JanelaObservada":
        return cls(inicio=d["inicio"], fim=d["fim"], dias_maduros=int(d["dias_maduros"]), dias_imaturos=int(d.get("dias_imaturos", 0)))


@dataclass(frozen=True)
class PontoSimulacao:
    """Um ponto de `campaign_simulation` (CPC_BID ou BUDGET). Valores em micros/contagens."""
    modificacao_micros: int  # cpc_bid_micros ou budget_amount_micros
    cliques: Optional[int]
    custo_micros: Optional[int]
    impressoes: Optional[int] = None
    conversoes: Optional[Decimal] = None

    def para_json(self) -> dict:
        return {"modificacao_micros": self.modificacao_micros, "cliques": self.cliques, "custo_micros": self.custo_micros,
                "impressoes": self.impressoes, "conversoes": None if self.conversoes is None else str(self.conversoes)}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "PontoSimulacao":
        return cls(modificacao_micros=int(d["modificacao_micros"]), cliques=d.get("cliques"), custo_micros=d.get("custo_micros"),
                   impressoes=d.get("impressoes"), conversoes=None if d.get("conversoes") is None else Decimal(str(d["conversoes"])))


@dataclass(frozen=True)
class SimulacaoEntrada:
    tipo: str  # "CPC_BID" | "BUDGET" | "TARGET_ROAS" | ... (só CPC_BID/BUDGET são interpretados)
    moeda: str
    pontos: tuple[PontoSimulacao, ...]
    disponivel_em: datetime
    estrategia_lance: str = ""  # MANUAL_CPC, TARGET_SPEND, MAXIMIZE_CONVERSIONS...
    canal: str = ""

    def __post_init__(self) -> None:
        _instante("simulacao.disponivel_em", self.disponivel_em)

    def para_json(self) -> dict:
        return {"tipo": self.tipo, "moeda": self.moeda, "pontos": [p.para_json() for p in self.pontos], "disponivel_em": self.disponivel_em.isoformat(),
                "estrategia_lance": self.estrategia_lance, "canal": self.canal}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "SimulacaoEntrada":
        return cls(tipo=d["tipo"], moeda=d["moeda"], pontos=tuple(PontoSimulacao.de_json(p) for p in d.get("pontos", [])),
                   disponivel_em=datetime.fromisoformat(d["disponivel_em"]), estrategia_lance=d.get("estrategia_lance", ""), canal=d.get("canal", ""))


@dataclass(frozen=True)
class EntradaViabilidade:
    candidato_id: str
    vertical: str
    pais: str
    fonte_custo: str
    fonte_receita: str
    as_of: datetime
    janela: JanelaObservada
    cliques: MedidaContagem
    custo: MedidaMonetaria
    receita: MedidaMonetaria
    cambio: Cambio
    revshare: Taxa
    imposto: Taxa
    perda_maxima: PerdaMaxima
    visitas: Optional[MedidaContagem] = None
    cpc_intervalo: Optional[tuple[Dinheiro, Dinheiro]] = None  # pesquisa (Keyword Planner etc.): nunca verba
    rpc_intervalo: Optional[tuple[Dinheiro, Dinheiro]] = None
    simulacao: Optional[SimulacaoEntrada] = None
    volume_diario_possivel: Optional[int] = None  # cliques/dia plausíveis (owner/pesquisa)
    flags_qualidade: tuple[str, ...] = ()
    freshness: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.candidato_id or not isinstance(self.candidato_id, str):
            raise ContratoViabilidadeViolado("candidato_id obrigatório")
        as_of = _instante("as_of", self.as_of)
        for nome in ("cliques", "custo", "receita", "visitas", "simulacao"):
            m = getattr(self, nome)
            if m is not None and m.disponivel_em > as_of:
                raise ContratoViabilidadeViolado(f"{nome}.disponivel_em posterior ao as_of (lookahead)")
        if self.volume_diario_possivel is not None and (not isinstance(self.volume_diario_possivel, int) or self.volume_diario_possivel <= 0):
            raise ContratoViabilidadeViolado("volume_diario_possivel precisa ser int > 0")
        object.__setattr__(self, "flags_qualidade", tuple(sorted(self.flags_qualidade)))
        object.__setattr__(self, "freshness", dict(sorted(dict(self.freshness).items())))

    def para_json(self) -> dict:
        def par(p):
            return None if p is None else [p[0].para_json(), p[1].para_json()]
        return {
            "candidato_id": self.candidato_id, "vertical": self.vertical, "pais": self.pais,
            "fonte_custo": self.fonte_custo, "fonte_receita": self.fonte_receita, "as_of": self.as_of.isoformat(),
            "janela": self.janela.para_json(), "cliques": self.cliques.para_json(), "custo": self.custo.para_json(),
            "receita": self.receita.para_json(), "cambio": self.cambio.para_json(), "revshare": self.revshare.para_json(),
            "imposto": self.imposto.para_json(), "perda_maxima": self.perda_maxima.para_json(),
            "visitas": None if self.visitas is None else self.visitas.para_json(),
            "cpc_intervalo": par(self.cpc_intervalo), "rpc_intervalo": par(self.rpc_intervalo),
            "simulacao": None if self.simulacao is None else self.simulacao.para_json(),
            "volume_diario_possivel": self.volume_diario_possivel, "flags_qualidade": list(self.flags_qualidade),
            "freshness": dict(self.freshness),
        }

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "EntradaViabilidade":
        def par(p):
            return None if p is None else (Dinheiro.de_json(p[0]), Dinheiro.de_json(p[1]))
        return cls(
            candidato_id=d["candidato_id"], vertical=d.get("vertical", ""), pais=d.get("pais", ""),
            fonte_custo=d.get("fonte_custo", ""), fonte_receita=d.get("fonte_receita", ""),
            as_of=datetime.fromisoformat(d["as_of"]) if d.get("as_of") else None,  # type: ignore[arg-type]
            janela=JanelaObservada.de_json(d["janela"]), cliques=MedidaContagem.de_json(d["cliques"]),
            custo=MedidaMonetaria.de_json(d["custo"]), receita=MedidaMonetaria.de_json(d["receita"]),
            cambio=Cambio.de_json(d["cambio"]), revshare=Taxa.de_json(d["revshare"]), imposto=Taxa.de_json(d["imposto"]),
            perda_maxima=PerdaMaxima.de_json(d["perda_maxima"]),
            visitas=None if d.get("visitas") is None else MedidaContagem.de_json(d["visitas"]),
            cpc_intervalo=par(d.get("cpc_intervalo")), rpc_intervalo=par(d.get("rpc_intervalo")),
            simulacao=None if d.get("simulacao") is None else SimulacaoEntrada.de_json(d["simulacao"]),
            volume_diario_possivel=d.get("volume_diario_possivel"), flags_qualidade=tuple(d.get("flags_qualidade", ())),
            freshness=d.get("freshness", {}),
        )


def json_canonico(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def hash_entrada(entrada: EntradaViabilidade) -> str:
    return hashlib.sha256(json_canonico(entrada.para_json()).encode("utf-8")).hexdigest()
