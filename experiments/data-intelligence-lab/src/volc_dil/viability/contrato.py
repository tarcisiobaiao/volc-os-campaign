"""Contrato tipado de entrada do kernel de viabilidade.

Regras que o contrato impõe por construção (não por convenção):
- ausência nunca vira zero: `valor=None` ⇔ evidência sem valor (`absent`, `unknown`, `invalid`);
- custo e receita brutos nunca são negativos; contagens nunca são negativas;
- toda medida carrega `disponivel_em` e nenhuma pode ser posterior ao `as_of` da entrada
  (nem `observado_em` posterior ao próprio `disponivel_em`);
- dinheiro é `Dinheiro` (micros inteiros + moeda ISO); razões são `Decimal`;
- moeda atestada é um estado distinto de moeda observada e nunca é promovida aqui;
- câmbio, revshare e imposto são parâmetros VERSIONADOS (effective_at, disponivel_em, versao, hash)
  e nenhum vale antes de `effective_at` nem é conhecido antes de `disponivel_em`;
- a tolerância de perda do owner é um valor fornecido, nunca derivado, e só existe com uma
  `Autorizacao` versionada (id, versão, emissor com identidade, vigência, hash sha256).

O sha256 prova integridade e reprodutibilidade do que foi declarado; NÃO prova identidade nem
autoria (isso exige assinatura, que o laboratório não tem).
"""
from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass
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

_SHA256_HEX = 64
# Papéis "nus" que não identificam ninguém: um emissor precisa de identidade ("owner:tarcisio@…", "owner:lab-fixture").
_PAPEIS_SEM_IDENTIDADE = frozenset({"owner", "bia", "agente", "chat", ""})


def json_canonico(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256_canonico(obj: Any) -> str:
    return hashlib.sha256(json_canonico(obj).encode("utf-8")).hexdigest()


def _instante(nome: str, v: Optional[datetime]) -> datetime:
    if v is None:
        raise ContratoViabilidadeViolado(f"{nome} é obrigatório")
    if not isinstance(v, datetime):
        raise ContratoViabilidadeViolado(f"{nome} precisa ser datetime")
    if v.tzinfo is None or v.utcoffset() is None:
        raise ContratoViabilidadeViolado(f"{nome} sem timezone")
    return v


def _instante_opcional(nome: str, v: Optional[datetime]) -> Optional[datetime]:
    return None if v is None else _instante(nome, v)


def _iso(v: Optional[datetime]) -> Optional[str]:
    return None if v is None else v.isoformat()


def _de_iso(v: Optional[str]) -> Optional[datetime]:
    return None if v is None else datetime.fromisoformat(v)


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


def _flags(v: Any) -> tuple[str, ...]:
    if isinstance(v, str):
        raise ContratoViabilidadeViolado("flags_qualidade precisa ser sequência de strings, não string")
    return tuple(sorted(set(str(x) for x in v)))


def _verificar_hash(nome: str, declarado: str, calculado: str) -> str:
    if declarado == "":
        return calculado
    if not isinstance(declarado, str) or len(declarado) != _SHA256_HEX or declarado != calculado:
        raise ContratoViabilidadeViolado(f"{nome}.hash não confere com o conteúdo declarado")
    return declarado


# --------------------------------------------------------------------------- autorização
@dataclass(frozen=True)
class Autorizacao:
    """Autorização versionada do owner para uma tolerância de perda. O hash é o sha256 do JSON canônico de
    {authorization_id, version, issuer, effective_at, expires_at}; prova integridade, não autoria."""
    authorization_id: str
    version: str
    hash: str
    issuer: str
    effective_at: datetime
    expires_at: Optional[datetime]
    disponivel_em: datetime

    @staticmethod
    def hash_canonico(authorization_id: str, version: str, issuer: str, effective_at: datetime, expires_at: Optional[datetime]) -> str:
        return _sha256_canonico({"authorization_id": authorization_id, "version": version, "issuer": issuer,
                                 "effective_at": _iso(effective_at), "expires_at": _iso(expires_at)})

    @classmethod
    def emitir(cls, *, authorization_id: str, version: str, issuer: str, effective_at: datetime, expires_at: Optional[datetime],
               disponivel_em: datetime) -> "Autorizacao":
        """Constrói com o hash calculado (uso em fixtures/testes e no lado VOLC que registra a autorização)."""
        return cls(authorization_id=authorization_id, version=version, issuer=issuer, effective_at=effective_at, expires_at=expires_at,
                   disponivel_em=disponivel_em, hash=cls.hash_canonico(authorization_id, version, issuer, effective_at, expires_at))

    def __post_init__(self) -> None:
        for n in ("authorization_id", "version"):
            if not isinstance(getattr(self, n), str) or not getattr(self, n):
                raise ContratoViabilidadeViolado(f"autorizacao.{n} obrigatório")
        if not isinstance(self.issuer, str):
            raise ContratoViabilidadeViolado("autorizacao.issuer precisa ser string")
        limpo = self.issuer.strip()
        papel, sep, identidade = limpo.partition(":")
        # aceito: '<papel>:<identidade>' com ambos não vazios, OU uma identidade endereçável nua (contém '@').
        # recusado: papel nu (owner/bia/agente/chat/vazio), 'papel:' sem identidade, ':identidade' sem papel, texto livre sem '@'.
        sem_identidade = (limpo.lower() in _PAPEIS_SEM_IDENTIDADE
                          or (sep and (not papel.strip() or not identidade.strip()))
                          or (not sep and "@" not in limpo))
        if sem_identidade:
            raise ContratoViabilidadeViolado("autorizacao.issuer sem identidade: use '<papel>:<identidade>' (ex.: 'owner:tarcisio@…') ou uma identidade endereçável")
        _instante("autorizacao.effective_at", self.effective_at)
        _instante("autorizacao.disponivel_em", self.disponivel_em)
        _instante_opcional("autorizacao.expires_at", self.expires_at)
        if self.effective_at > self.disponivel_em:
            raise ContratoViabilidadeViolado("autorizacao.effective_at posterior ao disponivel_em")
        if self.expires_at is not None and self.expires_at <= self.effective_at:
            raise ContratoViabilidadeViolado("autorizacao.expires_at precisa ser posterior ao effective_at")
        esperado = self.hash_canonico(self.authorization_id, self.version, self.issuer, self.effective_at, self.expires_at)
        if not isinstance(self.hash, str) or len(self.hash) != _SHA256_HEX or self.hash != esperado:
            raise ContratoViabilidadeViolado("autorizacao.hash não confere com o sha256 do conteúdo canônico")

    def vigente_em(self, as_of: datetime) -> bool:
        return self.effective_at <= as_of and (self.expires_at is None or as_of < self.expires_at)

    def para_json(self) -> dict:
        return {"authorization_id": self.authorization_id, "version": self.version, "hash": self.hash, "issuer": self.issuer,
                "effective_at": self.effective_at.isoformat(), "expires_at": _iso(self.expires_at), "disponivel_em": self.disponivel_em.isoformat()}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "Autorizacao":
        return cls(authorization_id=d["authorization_id"], version=d["version"], hash=d["hash"], issuer=d["issuer"],
                   effective_at=datetime.fromisoformat(d["effective_at"]), expires_at=_de_iso(d.get("expires_at")),
                   disponivel_em=datetime.fromisoformat(d["disponivel_em"]))


# --------------------------------------------------------------------------- medidas
@dataclass(frozen=True)
class MedidaMonetaria:
    valor: Optional[Dinheiro]
    evidencia: Evidencia
    moeda_evidencia: Evidencia
    disponivel_em: datetime
    fonte: str = ""
    observado_em: Optional[datetime] = None
    flags_qualidade: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _instante("disponivel_em", self.disponivel_em)
        if self.evidencia in SEM_VALOR and self.valor is not None:
            raise ContratoViabilidadeViolado(f"evidência {self.evidencia.value} não pode carregar valor (ausência não é zero)")
        if self.evidencia in COM_VALOR and self.valor is None:
            raise ContratoViabilidadeViolado(f"evidência {self.evidencia.value} exige valor")
        if self.valor is not None and not isinstance(self.valor, Dinheiro):
            raise ContratoViabilidadeViolado("valor monetário precisa ser Dinheiro (micros)")
        if self.valor is not None and self.valor.micros < 0:
            raise ContratoViabilidadeViolado("custo/receita brutos nunca negativos")
        if _instante_opcional("observado_em", self.observado_em) is not None and self.observado_em > self.disponivel_em:
            raise ContratoViabilidadeViolado("observado_em posterior ao disponivel_em")
        object.__setattr__(self, "flags_qualidade", _flags(self.flags_qualidade))

    def tem_valor(self) -> bool:
        return self.valor is not None

    def para_json(self) -> dict:
        return {"valor": None if self.valor is None else self.valor.para_json(), "evidencia": self.evidencia.value,
                "moeda_evidencia": self.moeda_evidencia.value, "disponivel_em": self.disponivel_em.isoformat(), "fonte": self.fonte,
                "observado_em": _iso(self.observado_em), "flags_qualidade": list(self.flags_qualidade)}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "MedidaMonetaria":
        return cls(valor=None if d.get("valor") is None else Dinheiro.de_json(d["valor"]), evidencia=Evidencia(d["evidencia"]),
                   moeda_evidencia=Evidencia(d["moeda_evidencia"]), disponivel_em=datetime.fromisoformat(d["disponivel_em"]), fonte=d.get("fonte", ""),
                   observado_em=_de_iso(d.get("observado_em")), flags_qualidade=tuple(d.get("flags_qualidade", ())))


@dataclass(frozen=True)
class MedidaContagem:
    valor: Optional[int]
    evidencia: Evidencia
    disponivel_em: datetime
    fonte: str = ""
    observado_em: Optional[datetime] = None
    flags_qualidade: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _instante("disponivel_em", self.disponivel_em)
        if self.evidencia in SEM_VALOR and self.valor is not None:
            raise ContratoViabilidadeViolado("contagem ausente não pode carregar valor")
        if self.evidencia in COM_VALOR and self.valor is None:
            raise ContratoViabilidadeViolado("contagem com evidência exige valor")
        if self.valor is not None and (not isinstance(self.valor, int) or isinstance(self.valor, bool) or self.valor < 0):
            raise ContratoViabilidadeViolado("contagem precisa ser int >= 0")
        if _instante_opcional("observado_em", self.observado_em) is not None and self.observado_em > self.disponivel_em:
            raise ContratoViabilidadeViolado("observado_em posterior ao disponivel_em")
        object.__setattr__(self, "flags_qualidade", _flags(self.flags_qualidade))

    def tem_valor(self) -> bool:
        return self.valor is not None

    def para_json(self) -> dict:
        return {"valor": self.valor, "evidencia": self.evidencia.value, "disponivel_em": self.disponivel_em.isoformat(), "fonte": self.fonte,
                "observado_em": _iso(self.observado_em), "flags_qualidade": list(self.flags_qualidade)}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "MedidaContagem":
        return cls(valor=d.get("valor"), evidencia=Evidencia(d["evidencia"]), disponivel_em=datetime.fromisoformat(d["disponivel_em"]), fonte=d.get("fonte", ""),
                   observado_em=_de_iso(d.get("observado_em")), flags_qualidade=tuple(d.get("flags_qualidade", ())))


# --------------------------------------------------------------------------- parâmetros versionados
@dataclass(frozen=True)
class Cambio:
    """Taxa de câmbio com proveniência e versão. `evidencia`: observed (PTAX datado), attested, estimated (literal), unknown/absent.
    Com taxa presente, `effective_at` (desde quando vale) e `disponivel_em` (desde quando se sabe) são obrigatórios.
    `hash` = sha256 do canônico de {taxa, de, para, proveniencia, evidencia, effective_at, versao}: calculado quando vazio, verificado quando dado."""
    taxa: Optional[Decimal]
    de: str
    para: str
    proveniencia: str
    evidencia: Evidencia
    effective_at: Optional[datetime] = None
    disponivel_em: Optional[datetime] = None
    versao: str = ""
    hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "taxa", _decimal("cambio.taxa", self.taxa, permitir_none=True))
        if self.evidencia in SEM_VALOR and self.taxa is not None:
            raise ContratoViabilidadeViolado("câmbio ausente não pode carregar taxa")
        if self.evidencia in COM_VALOR and (self.taxa is None or self.taxa <= 0):
            raise ContratoViabilidadeViolado("câmbio com evidência exige taxa > 0")
        _instante_opcional("cambio.effective_at", self.effective_at)
        _instante_opcional("cambio.disponivel_em", self.disponivel_em)
        if self.taxa is not None:
            if self.effective_at is None:
                raise ContratoViabilidadeViolado("cambio.effective_at é obrigatório quando há taxa")
            if self.disponivel_em is None:
                raise ContratoViabilidadeViolado("cambio.disponivel_em é obrigatório quando há taxa")
        object.__setattr__(self, "hash", _verificar_hash("cambio", self.hash, self._hash_canonico()))

    def _hash_canonico(self) -> str:
        return _sha256_canonico({"taxa": None if self.taxa is None else str(self.taxa), "de": self.de, "para": self.para, "proveniencia": self.proveniencia,
                                 "evidencia": self.evidencia.value, "effective_at": _iso(self.effective_at), "versao": self.versao})

    def para_json(self) -> dict:
        return {"taxa": None if self.taxa is None else str(self.taxa), "de": self.de, "para": self.para, "proveniencia": self.proveniencia,
                "evidencia": self.evidencia.value, "effective_at": _iso(self.effective_at), "disponivel_em": _iso(self.disponivel_em),
                "versao": self.versao, "hash": self.hash}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "Cambio":
        return cls(taxa=None if d.get("taxa") is None else Decimal(d["taxa"]), de=d["de"], para=d["para"], proveniencia=d.get("proveniencia", ""),
                   evidencia=Evidencia(d["evidencia"]), effective_at=_de_iso(d.get("effective_at")), disponivel_em=_de_iso(d.get("disponivel_em")),
                   versao=d.get("versao", ""), hash=d.get("hash", ""))


@dataclass(frozen=True)
class Taxa:
    """Fração 0..1 (revshare líquido ao publisher, imposto) com proveniência e versão. Mesmo padrão de `Cambio`:
    com valor presente, `effective_at` e `disponivel_em` são obrigatórios; `hash` calculado/verificado."""
    valor: Optional[Decimal]
    evidencia: Evidencia
    proveniencia: str
    effective_at: Optional[datetime] = None
    disponivel_em: Optional[datetime] = None
    versao: str = ""
    hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "valor", _decimal("taxa.valor", self.valor, permitir_none=True))
        if self.evidencia in SEM_VALOR and self.valor is not None:
            raise ContratoViabilidadeViolado("taxa ausente não pode carregar valor")
        if self.valor is not None and not (Decimal(0) <= self.valor <= Decimal(1)):
            raise ContratoViabilidadeViolado("taxa precisa estar em [0, 1]")
        _instante_opcional("taxa.effective_at", self.effective_at)
        _instante_opcional("taxa.disponivel_em", self.disponivel_em)
        if self.valor is not None:
            if self.effective_at is None:
                raise ContratoViabilidadeViolado("taxa.effective_at é obrigatório quando há valor")
            if self.disponivel_em is None:
                raise ContratoViabilidadeViolado("taxa.disponivel_em é obrigatório quando há valor")
        object.__setattr__(self, "hash", _verificar_hash("taxa", self.hash, self._hash_canonico()))

    def _hash_canonico(self) -> str:
        return _sha256_canonico({"valor": None if self.valor is None else str(self.valor), "evidencia": self.evidencia.value, "proveniencia": self.proveniencia,
                                 "effective_at": _iso(self.effective_at), "versao": self.versao})

    def para_json(self) -> dict:
        return {"valor": None if self.valor is None else str(self.valor), "evidencia": self.evidencia.value, "proveniencia": self.proveniencia,
                "effective_at": _iso(self.effective_at), "disponivel_em": _iso(self.disponivel_em), "versao": self.versao, "hash": self.hash}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "Taxa":
        return cls(valor=None if d.get("valor") is None else Decimal(d["valor"]), evidencia=Evidencia(d["evidencia"]), proveniencia=d.get("proveniencia", ""),
                   effective_at=_de_iso(d.get("effective_at")), disponivel_em=_de_iso(d.get("disponivel_em")), versao=d.get("versao", ""), hash=d.get("hash", ""))


@dataclass(frozen=True)
class PerdaMaxima:
    """Tolerância financeira do owner. NUNCA derivada: `valor=None` significa 'não informada'.
    Um valor só existe acompanhado de uma `Autorizacao` versionada; `informada()` exige valor, horizonte e autorização."""
    valor: Optional[Dinheiro]
    horizonte_dias: Optional[int]
    autorizacao: Optional[Autorizacao]

    def __post_init__(self) -> None:
        if self.valor is not None and not isinstance(self.valor, Dinheiro):
            raise ContratoViabilidadeViolado("perda_maxima.valor precisa ser Dinheiro")
        if self.valor is not None and self.valor.micros <= 0:
            raise ContratoViabilidadeViolado("perda_maxima precisa ser > 0 quando informada")
        if self.horizonte_dias is not None and (not isinstance(self.horizonte_dias, int) or isinstance(self.horizonte_dias, bool) or self.horizonte_dias <= 0):
            raise ContratoViabilidadeViolado("horizonte_dias precisa ser int > 0")
        if self.autorizacao is not None and not isinstance(self.autorizacao, Autorizacao):
            raise ContratoViabilidadeViolado("perda_maxima.autorizacao precisa ser Autorizacao")
        if (self.valor is not None or self.horizonte_dias is not None) and self.autorizacao is None:
            raise ContratoViabilidadeViolado("perda_maxima sem autorização versionada")

    def informada(self) -> bool:
        return self.valor is not None and self.horizonte_dias is not None and self.autorizacao is not None

    def vigente_em(self, as_of: datetime) -> bool:
        return self.informada() and self.autorizacao.vigente_em(as_of)  # type: ignore[union-attr]

    def para_json(self) -> dict:
        return {"valor": None if self.valor is None else self.valor.para_json(), "horizonte_dias": self.horizonte_dias,
                "autorizacao": None if self.autorizacao is None else self.autorizacao.para_json()}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "PerdaMaxima":
        if "proveniencia" in d and d.get("autorizacao") is None:
            raise ContratoViabilidadeViolado("perda_maxima sem autorização versionada (`proveniencia` não substitui `autorizacao`)")
        return cls(valor=None if d.get("valor") is None else Dinheiro.de_json(d["valor"]), horizonte_dias=d.get("horizonte_dias"),
                   autorizacao=None if d.get("autorizacao") is None else Autorizacao.de_json(d["autorizacao"]))


# --------------------------------------------------------------------------- janela
@dataclass(frozen=True)
class JanelaObservada:
    """Janela da observação. `dias_maduros` = dias maduros com custo (o grão em que a economia é comparável);
    `cobertura_receita_ppm` = dias_receita_madura / dias_custo_maduro em partes por milhão (None = não se sabe)."""
    inicio: str  # ISO date
    fim: str
    dias_maduros: int
    dias_imaturos: int = 0
    dias_custo_maduro: Optional[int] = None
    dias_receita_madura: Optional[int] = None
    dias_custo_sem_receita: int = 0
    cobertura_receita_ppm: Optional[int] = None

    def __post_init__(self) -> None:
        for n in ("dias_maduros", "dias_imaturos", "dias_custo_sem_receita"):
            v = getattr(self, n)
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise ContratoViabilidadeViolado(f"{n} precisa ser int >= 0")
        for n in ("dias_custo_maduro", "dias_receita_madura", "cobertura_receita_ppm"):
            v = getattr(self, n)
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 0):
                raise ContratoViabilidadeViolado(f"{n} precisa ser int >= 0 ou None")
        if self.dias_custo_maduro is not None and self.dias_custo_maduro != self.dias_maduros:
            raise ContratoViabilidadeViolado("dias_custo_maduro difere de dias_maduros")
        if self.cobertura_receita_ppm is not None and not (0 <= self.cobertura_receita_ppm <= 1_000_000):
            raise ContratoViabilidadeViolado("cobertura_receita_ppm fora de 0..1_000_000")
        if self.inicio > self.fim:
            raise ContratoViabilidadeViolado("janela: inicio > fim")

    def para_json(self) -> dict:
        return {"inicio": self.inicio, "fim": self.fim, "dias_maduros": self.dias_maduros, "dias_imaturos": self.dias_imaturos,
                "dias_custo_maduro": self.dias_custo_maduro, "dias_receita_madura": self.dias_receita_madura,
                "dias_custo_sem_receita": self.dias_custo_sem_receita, "cobertura_receita_ppm": self.cobertura_receita_ppm}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "JanelaObservada":
        # só as chaves presentes: ausência cai no default do dataclass (None = não se sabe), nunca num literal aqui
        extras = {k: d[k] for k in ("dias_imaturos", "dias_custo_maduro", "dias_receita_madura", "dias_custo_sem_receita", "cobertura_receita_ppm") if k in d}
        return cls(inicio=d["inicio"], fim=d["fim"], dias_maduros=int(d["dias_maduros"]), **extras)


# --------------------------------------------------------------------------- simulação
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
    estrategia_lance: str = ""
    canal: str = ""
    cambio: Optional[Cambio] = None  # quando a moeda da simulação difere da moeda do custo

    def __post_init__(self) -> None:
        _instante("simulacao.disponivel_em", self.disponivel_em)
        if self.cambio is not None and not isinstance(self.cambio, Cambio):
            raise ContratoViabilidadeViolado("simulacao.cambio precisa ser Cambio")

    def para_json(self) -> dict:
        return {"tipo": self.tipo, "moeda": self.moeda, "pontos": [p.para_json() for p in self.pontos], "disponivel_em": self.disponivel_em.isoformat(),
                "estrategia_lance": self.estrategia_lance, "canal": self.canal, "cambio": None if self.cambio is None else self.cambio.para_json()}

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "SimulacaoEntrada":
        return cls(tipo=d["tipo"], moeda=d["moeda"], pontos=tuple(PontoSimulacao.de_json(p) for p in d.get("pontos", [])),
                   disponivel_em=datetime.fromisoformat(d["disponivel_em"]), estrategia_lance=d.get("estrategia_lance", ""), canal=d.get("canal", ""),
                   cambio=None if d.get("cambio") is None else Cambio.de_json(d["cambio"]))


# --------------------------------------------------------------------------- entrada
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
    visitas: Optional[MedidaContagem] = None  # 0 é válido; None = não medido
    cpc_intervalo: Optional[tuple[Dinheiro, Dinheiro]] = None  # pesquisa (Keyword Planner etc.): nunca verba
    rpc_intervalo: Optional[tuple[Dinheiro, Dinheiro]] = None
    simulacao: Optional[SimulacaoEntrada] = None
    volume_diario_possivel: Optional[int] = None  # cliques/dia plausíveis (owner/pesquisa)
    flags_qualidade: tuple[str, ...] = ()
    freshness_sla_dias: int = 7  # idade máxima aceitável da observação (as_of - disponivel_em) antes de o gate degradar

    def __post_init__(self) -> None:
        if not self.candidato_id or not isinstance(self.candidato_id, str):
            raise ContratoViabilidadeViolado("candidato_id obrigatório")
        as_of = _instante("as_of", self.as_of)
        if not isinstance(self.freshness_sla_dias, int) or isinstance(self.freshness_sla_dias, bool) or self.freshness_sla_dias < 0:
            raise ContratoViabilidadeViolado("freshness_sla_dias precisa ser int >= 0")
        disponiveis = [("cliques", self.cliques), ("custo", self.custo), ("receita", self.receita), ("visitas", self.visitas),
                       ("simulacao", self.simulacao), ("cambio", self.cambio), ("revshare", self.revshare), ("imposto", self.imposto),
                       ("perda_maxima.autorizacao", self.perda_maxima.autorizacao)]
        if self.simulacao is not None and self.simulacao.cambio is not None:
            disponiveis.append(("simulacao.cambio", self.simulacao.cambio))
        for nome, m in disponiveis:
            if m is not None and m.disponivel_em is not None and m.disponivel_em > as_of:
                raise ContratoViabilidadeViolado(f"{nome}.disponivel_em posterior ao as_of (lookahead)")
        for nome, m in disponiveis:
            ef = getattr(m, "effective_at", None)
            if ef is not None and ef > as_of:
                raise ContratoViabilidadeViolado(f"{nome}.effective_at posterior ao as_of (parâmetro ainda não vale)")
        if self.perda_maxima.informada() and not self.perda_maxima.vigente_em(as_of):
            raise ContratoViabilidadeViolado("perda_maxima.autorizacao não vigente no as_of (expirada)")
        if self.volume_diario_possivel is not None and (not isinstance(self.volume_diario_possivel, int) or self.volume_diario_possivel <= 0):
            raise ContratoViabilidadeViolado("volume_diario_possivel precisa ser int > 0")
        object.__setattr__(self, "flags_qualidade", _flags(self.flags_qualidade))

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
            "freshness_sla_dias": self.freshness_sla_dias,
        }

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "EntradaViabilidade":
        def par(p):
            return None if p is None else (Dinheiro.de_json(p[0]), Dinheiro.de_json(p[1]))
        if "freshness" in d:
            raise ContratoViabilidadeViolado("campo `freshness` não existe mais; use `freshness_sla_dias`")
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
            freshness_sla_dias=int(d.get("freshness_sla_dias", 7)),
        )


def hash_entrada(entrada: EntradaViabilidade) -> str:
    return hashlib.sha256(json_canonico(entrada.para_json()).encode("utf-8")).hexdigest()
