"""Agregação anulável, identidade estrita e rótulo econômico.

- Soma vazia é AUSENTE, não zero.
- Um membro sem valor torna o agregado sem valor (pior estado vence), salvo quando o
  chamador aceita explicitamente cobertura parcial — e então o agregado diz PARCIAL.
- Moedas diferentes e value_kinds diferentes não se somam.
- Custo e receita só se juntam com a MESMA identidade, janela e timezone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from .money import Dinheiro, MoedasDiferentes
from .observation import ChaveUnidade, ContratoViolado, Observacao
from .vocab import (
    COM_VALOR,
    GRAVIDADE,
    METRICAS_CONTAGEM,
    RECEITA_CONTABIL,
    ROTULO_ECONOMICO,
    Cobertura,
    EstadoMedida,
    Maturidade,
    Metrica,
    ValueKind,
)


class ValueKindsMisturados(ContratoViolado):
    """Soma de classes epistemológicas diferentes (ex.: estimada + reconciliada)."""


class IdentidadeIncompativel(ContratoViolado):
    """Tentativa de relacionar fatos de identidades, janelas ou timezones diferentes."""


class Circularidade(ContratoViolado):
    """Feature e rótulo compartilham a mesma origem: o modelo aprenderia a si mesmo."""


@dataclass(frozen=True)
class Agregado:
    valor: Optional[object]
    estado: EstadoMedida
    cobertura: Cobertura
    n: int
    n_sem_valor: int
    moeda: Optional[str] = None
    value_kind: Optional[ValueKind] = None
    motivos: tuple[str, ...] = field(default_factory=tuple)

    @property
    def tem_valor(self) -> bool:
        return self.valor is not None


def _pior(estados: Iterable[EstadoMedida]) -> EstadoMedida:
    presentes = set(estados)
    for e in GRAVIDADE:
        if e in presentes:
            return e
    return EstadoMedida.AUSENTE


def agregar(observacoes: Sequence[Observacao], *, aceitar_parcial: bool = False) -> Agregado:
    if not observacoes:
        return Agregado(None, EstadoMedida.AUSENTE, Cobertura.DESCONHECIDA, 0, 0, motivos=("nenhuma observação",))
    metricas = {o.metrica for o in observacoes}
    if len(metricas) != 1:
        raise ContratoViolado(f"agregação mistura métricas: {sorted(m.value for m in metricas)}")
    metrica = metricas.pop()
    kinds = {o.value_kind for o in observacoes}
    if len(kinds) != 1:
        raise ValueKindsMisturados(f"value_kinds diferentes: {sorted(str(k.value) if k else 'None' for k in kinds)}")
    kind = kinds.pop()
    moedas = {o.moeda for o in observacoes if o.moeda}
    if len(moedas) > 1:
        raise MoedasDiferentes(" × ".join(sorted(moedas)))
    moeda = moedas.pop() if moedas else None

    com = [o for o in observacoes if o.estado in COM_VALOR]
    sem = [o for o in observacoes if o.estado not in COM_VALOR]
    motivos = tuple(sorted({o.motivo or o.estado.value for o in sem}))
    cobertura_membros = {o.cobertura for o in observacoes}
    if sem and not aceitar_parcial:
        return Agregado(None, _pior(o.estado for o in sem), Cobertura.PARCIAL, len(observacoes), len(sem), moeda, kind, motivos)
    if not com:
        return Agregado(None, _pior(o.estado for o in sem), Cobertura.DESCONHECIDA, len(observacoes), len(sem), moeda, kind, motivos)

    if metrica in (Metrica.CUSTO, Metrica.RECEITA) or isinstance(com[0].valor, Dinheiro):
        total = com[0].valor
        for o in com[1:]:
            total = total + o.valor  # type: ignore[operator]
    elif metrica in METRICAS_CONTAGEM:
        total = sum(int(o.valor) for o in com)  # type: ignore[arg-type]
    else:
        raise ContratoViolado(f"métrica {metrica.value} não é somável")

    if sem:
        cobertura = Cobertura.PARCIAL
    elif cobertura_membros == {Cobertura.COMPLETA}:
        cobertura = Cobertura.COMPLETA
    elif Cobertura.DESCONHECIDA in cobertura_membros:
        cobertura = Cobertura.DESCONHECIDA
    else:
        cobertura = Cobertura.PARCIAL
    zero = total.eh_zero() if isinstance(total, Dinheiro) else total == 0
    estado = EstadoMedida.ZERO_CONFIRMADO if zero else EstadoMedida.MEDIDO
    return Agregado(total, estado, cobertura, len(observacoes), len(sem), moeda, kind, motivos)


def exigir_mesma_identidade(a: Observacao, b: Observacao) -> None:
    if a.unidade != b.unidade:
        raise IdentidadeIncompativel(f"identidades diferentes: {a.unidade.para_json()} × {b.unidade.para_json()}")
    if (a.janela_inicio, a.janela_fim) != (b.janela_inicio, b.janela_fim):
        raise IdentidadeIncompativel("janelas diferentes")
    if a.timezone != b.timezone:
        raise IdentidadeIncompativel(f"timezones diferentes: {a.timezone} × {b.timezone}")


@dataclass(frozen=True)
class Contribuicao:
    unidade: ChaveUnidade
    valor: Optional[Dinheiro]
    motivo: Optional[str]


def contribuicao(custo: Observacao, receita: Observacao) -> Contribuicao:
    """Receita contábil − custo na MESMA identidade/janela. Sem valor quando não é defensável."""
    if custo.metrica is not Metrica.CUSTO or receita.metrica is not Metrica.RECEITA:
        raise ContratoViolado("contribuicao(custo, receita) recebeu métricas trocadas")
    exigir_mesma_identidade(custo, receita)
    if receita.value_kind not in RECEITA_CONTABIL:
        return Contribuicao(custo.unidade, None, f"receita {receita.value_kind.value if receita.value_kind else None} não é contábil")
    if custo.estado not in COM_VALOR or receita.estado not in COM_VALOR:
        return Contribuicao(custo.unidade, None, "custo ou receita sem valor (null != 0)")
    return Contribuicao(custo.unidade, receita.valor - custo.valor, None)  # type: ignore[operator]


def rotulo_economico(o: Observacao) -> tuple[Optional[Dinheiro], Optional[str]]:
    """Rótulo aceitável para surrogate/avaliação: reconciliado, maduro, completo, com valor."""
    if o.metrica is not Metrica.RECEITA:
        return None, "não é receita"
    if o.value_kind not in ROTULO_ECONOMICO:
        return None, f"value_kind {o.value_kind.value if o.value_kind else None} não é rótulo econômico"
    if o.maturidade is Maturidade.PRELIMINAR:
        return None, "outcome preliminar, não fechado"
    if o.cobertura is not Cobertura.COMPLETA:
        return None, "cobertura incompleta"
    if o.estado not in COM_VALOR:
        return None, f"sem valor: {o.estado.value}"
    return o.valor, None  # type: ignore[return-value]


def verificar_nao_circular(features: Sequence[Observacao], rotulo: Observacao) -> None:
    """Feature que vem da mesma coleta/linhagem do rótulo é vazamento de alvo."""
    origem_rotulo = {rotulo.coleta_id, *rotulo.linhagem}
    for f in features:
        origem = {f.coleta_id, *f.linhagem}
        if origem & origem_rotulo:
            raise Circularidade(f"feature {f.metrica.value}/{f.fonte} compartilha origem com o rótulo: {sorted(origem & origem_rotulo)}")
        if f.metrica is Metrica.RECEITA and f.unidade == rotulo.unidade and f.janela_fim > rotulo.janela_inicio:
            raise Circularidade("feature é receita da mesma unidade sobrepondo a janela do rótulo")
