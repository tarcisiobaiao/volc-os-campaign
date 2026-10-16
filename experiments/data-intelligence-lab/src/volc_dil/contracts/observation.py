"""Observação econômica: a menor unidade de fato que o laboratório aceita.

Uma observação é (identidade × métrica × janela de evento × versão de conhecimento).
Ela separa três relógios:

- `janela_inicio`/`janela_fim`: o período do mundo que o número descreve (event time);
- `observado_em`: quando a fonte afirma ter medido;
- `disponivel_em`: quando o VOLC passou a conhecer o número (knowledge time).

Replay `as_of` só pode usar observações com `disponivel_em <= as_of`. Uma revisão
posterior (restatement) é OUTRA observação, com `disponivel_em` posterior e a mesma
chave lógica; nunca sobrescreve a anterior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Optional, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .money import Dinheiro
from .vocab import (
    COM_VALOR,
    METRICAS_CONTAGEM,
    Cobertura,
    EstadoMedida,
    Maturidade,
    Metrica,
    MetodoAtribuicao,
    ValueKind,
)

ValorObs = Union[Dinheiro, int, Decimal, None]

GRAOS_CONHECIDOS = frozenset(
    {
        "account",
        "campaign",
        "ad_group",
        "keyword",
        "funnel",
        "url",
        "ad_unit",
        "country",
        "device",
        "day",
        "hour",
        "session",
        "click",
        "cell",
    }
)


class ContratoViolado(ValueError):
    """Observação que não respeita o contrato econômico mínimo."""


def _instante(nome: str, v: Optional[datetime], obrigatorio: bool = True) -> None:
    if v is None:
        if obrigatorio:
            raise ContratoViolado(f"{nome} é obrigatório")
        return
    if not isinstance(v, datetime):
        raise ContratoViolado(f"{nome} precisa ser datetime")
    if v.tzinfo is None or v.utcoffset() is None:
        raise ContratoViolado(f"{nome} sem timezone")


@dataclass(frozen=True, order=True)
class ChaveUnidade:
    """Identidade verificável. Nada de casar por nome: conta + tipo + id + grão + dimensões."""

    conta: str
    tipo_entidade: str
    entidade_id: str
    grao: tuple[str, ...]
    dimensoes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for nome in ("conta", "tipo_entidade", "entidade_id"):
            v = getattr(self, nome)
            if not isinstance(v, str) or not v.strip():
                raise ContratoViolado(f"identidade: {nome} vazio")
        if not self.grao:
            raise ContratoViolado("identidade: grão vazio")
        desconhecidos = set(self.grao) - GRAOS_CONHECIDOS
        if desconhecidos:
            raise ContratoViolado(f"grão desconhecido: {sorted(desconhecidos)}")
        nomes_dim = [d[0] for d in self.dimensoes]
        if nomes_dim != sorted(nomes_dim) or len(set(nomes_dim)) != len(nomes_dim):
            raise ContratoViolado("dimensões precisam vir ordenadas e sem repetição")

    def para_json(self) -> dict:
        return {
            "conta": self.conta,
            "tipo_entidade": self.tipo_entidade,
            "entidade_id": self.entidade_id,
            "grao": list(self.grao),
            "dimensoes": [list(d) for d in self.dimensoes],
        }

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "ChaveUnidade":
        return cls(
            conta=d["conta"],
            tipo_entidade=d["tipo_entidade"],
            entidade_id=d["entidade_id"],
            grao=tuple(d["grao"]),
            dimensoes=tuple(tuple(x) for x in d.get("dimensoes", ())),  # type: ignore[misc]
        )


@dataclass(frozen=True)
class Observacao:
    unidade: ChaveUnidade
    metrica: Metrica
    valor: ValorObs
    estado: EstadoMedida
    janela_inicio: datetime
    janela_fim: datetime
    timezone: str
    observado_em: datetime
    disponivel_em: datetime
    fonte: str
    versao_fonte: str
    coleta_id: str
    cobertura: Cobertura
    maturidade: Maturidade
    metodo: MetodoAtribuicao
    value_kind: Optional[ValueKind] = None
    atraso_conhecido_s: Optional[int] = None
    motivo: Optional[str] = None
    linhagem: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _instante("janela_inicio", self.janela_inicio)
        _instante("janela_fim", self.janela_fim)
        _instante("observado_em", self.observado_em)
        _instante("disponivel_em", self.disponivel_em)
        if self.janela_fim <= self.janela_inicio:
            raise ContratoViolado("janela vazia ou invertida")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise ContratoViolado(f"timezone inválido: {self.timezone!r}") from exc
        if self.disponivel_em < self.observado_em:
            raise ContratoViolado("disponivel_em anterior a observado_em")
        if self.observado_em < self.janela_inicio:
            raise ContratoViolado("observado_em anterior ao início da janela")
        if not self.fonte or not self.versao_fonte or not self.coleta_id:
            raise ContratoViolado("fonte, versao_fonte e coleta_id são obrigatórios (linhagem)")
        self._validar_valor()

    def _validar_valor(self) -> None:
        v, m, k = self.valor, self.metrica, self.value_kind
        if self.estado in COM_VALOR:
            if v is None:
                raise ContratoViolado(f"estado {self.estado.value} exige valor")
        else:
            if v is not None:
                raise ContratoViolado(f"estado {self.estado.value} não carrega valor (null != 0)")
            if not self.motivo:
                raise ContratoViolado("valor ausente precisa de motivo")
        if isinstance(v, float):
            raise ContratoViolado("float proibido no contrato; use Dinheiro, int ou Decimal")
        if self.estado is EstadoMedida.ZERO_CONFIRMADO:
            zero = v.eh_zero() if isinstance(v, Dinheiro) else v == 0
            if not zero:
                raise ContratoViolado("zero_confirmado com valor diferente de zero")
        if m is Metrica.CUSTO:
            if v is not None and not isinstance(v, Dinheiro):
                raise ContratoViolado("custo precisa ser Dinheiro")
            if k is not None:
                raise ContratoViolado("custo não tem value_kind (value_kind classifica valor/receita)")
        elif m is Metrica.RECEITA:
            if v is not None and not isinstance(v, Dinheiro):
                raise ContratoViolado("receita precisa ser Dinheiro")
            if k is None:
                raise ContratoViolado("receita exige value_kind explícito")
            if k is ValueKind.OBSERVED_AUCTION_SIGNAL:
                raise ContratoViolado("sinal de leilão não é receita (X02)")
            if k is ValueKind.RECONCILED_REVENUE and self.metodo in (
                MetodoAtribuicao.INFERRED,
                MetodoAtribuicao.UNRECONCILED,
                MetodoAtribuicao.NOT_IDENTIFIABLE,
            ):
                raise ContratoViolado("receita reconciliada exige método de atribuição determinístico ou agregado declarado")
            if k is ValueKind.RECONCILED_REVENUE and "session" in self.unidade.grao and self.metodo is MetodoAtribuicao.AGGREGATE_CAMPAIGN_DATE:
                raise ContratoViolado("receita agregada não vira receita reconciliada por sessão")
        elif m in METRICAS_CONTAGEM:
            if v is not None and (not isinstance(v, int) or isinstance(v, bool)):
                raise ContratoViolado(f"{m.value} precisa ser int")
            if v is not None and v < 0:
                raise ContratoViolado(f"{m.value} negativo")
            if k is not None:
                raise ContratoViolado(f"{m.value} não tem value_kind")
        elif m is Metrica.SINAL:
            if isinstance(v, Dinheiro) and k is not ValueKind.OBSERVED_AUCTION_SIGNAL:
                raise ContratoViolado("sinal monetário só pode ser observed_auction_signal")
            if not isinstance(v, Dinheiro) and k is not None:
                raise ContratoViolado("sinal não monetário não tem value_kind")

    @property
    def moeda(self) -> Optional[str]:
        return self.valor.moeda if isinstance(self.valor, Dinheiro) else None

    @property
    def chave_logica(self) -> tuple:
        """Identifica 'o mesmo fato' entre versões: revisões compartilham a chave lógica."""
        return (
            self.unidade,
            self.metrica.value,
            self.janela_inicio.isoformat(),
            self.janela_fim.isoformat(),
            self.timezone,
            self.fonte,
            self.value_kind.value if self.value_kind else None,
        )

    def para_json(self) -> dict:
        v = self.valor
        if isinstance(v, Dinheiro):
            valor: Any = {"dinheiro": v.para_json()}
        elif isinstance(v, Decimal):
            valor = {"decimal": str(v)}
        elif v is None:
            valor = None
        else:
            valor = {"int": v}
        return {
            "unidade": self.unidade.para_json(),
            "metrica": self.metrica.value,
            "valor": valor,
            "estado": self.estado.value,
            "janela_inicio": self.janela_inicio.isoformat(),
            "janela_fim": self.janela_fim.isoformat(),
            "timezone": self.timezone,
            "observado_em": self.observado_em.isoformat(),
            "disponivel_em": self.disponivel_em.isoformat(),
            "fonte": self.fonte,
            "versao_fonte": self.versao_fonte,
            "coleta_id": self.coleta_id,
            "cobertura": self.cobertura.value,
            "maturidade": self.maturidade.value,
            "metodo": self.metodo.value,
            "value_kind": self.value_kind.value if self.value_kind else None,
            "atraso_conhecido_s": self.atraso_conhecido_s,
            "motivo": self.motivo,
            "linhagem": list(self.linhagem),
        }

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "Observacao":
        bruto = d.get("valor")
        valor: ValorObs
        if bruto is None:
            valor = None
        elif not isinstance(bruto, Mapping) or len(bruto) != 1:
            raise ContratoViolado("valor precisa ser null ou {dinheiro|decimal|int: ...}")
        elif "dinheiro" in bruto:
            valor = Dinheiro.de_json(bruto["dinheiro"])
        elif "decimal" in bruto:
            if not isinstance(bruto["decimal"], str):
                raise ContratoViolado("decimal precisa vir como string")
            valor = Decimal(bruto["decimal"])
        elif "int" in bruto:
            valor = bruto["int"]
        else:
            raise ContratoViolado(f"tipo de valor desconhecido: {list(bruto)}")

        def ts(nome: str) -> datetime:
            try:
                return datetime.fromisoformat(d[nome])
            except (KeyError, TypeError, ValueError) as exc:
                raise ContratoViolado(f"{nome} inválido") from exc

        try:
            return cls(
                unidade=ChaveUnidade.de_json(d["unidade"]),
                metrica=Metrica(d["metrica"]),
                valor=valor,
                estado=EstadoMedida(d["estado"]),
                janela_inicio=ts("janela_inicio"),
                janela_fim=ts("janela_fim"),
                timezone=d["timezone"],
                observado_em=ts("observado_em"),
                disponivel_em=ts("disponivel_em"),
                fonte=d["fonte"],
                versao_fonte=d["versao_fonte"],
                coleta_id=d["coleta_id"],
                cobertura=Cobertura(d["cobertura"]),
                maturidade=Maturidade(d["maturidade"]),
                metodo=MetodoAtribuicao(d["metodo"]),
                value_kind=ValueKind(d["value_kind"]) if d.get("value_kind") else None,
                atraso_conhecido_s=d.get("atraso_conhecido_s"),
                motivo=d.get("motivo"),
                linhagem=tuple(d.get("linhagem", ())),
            )
        except KeyError as exc:
            raise ContratoViolado(f"campo obrigatório ausente: {exc.args[0]}") from exc
