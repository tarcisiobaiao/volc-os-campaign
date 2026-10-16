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
    MetodoAtribuicao,
    ValueKind,
)

METODOS_NAO_RECONCILIADOS = frozenset(
    {MetodoAtribuicao.INFERRED, MetodoAtribuicao.UNRECONCILED, MetodoAtribuicao.NOT_IDENTIFIABLE}
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
    chaves = [o.chave_logica for o in observacoes]
    if len(set(chaves)) != len(chaves):
        # duas versões do mesmo fato (ou reentrega duplicada) não se somam (F1-02/F1-03)
        raise ContratoViolado("agregação recebeu o mesmo fato mais de uma vez (chave lógica repetida)")
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
    """Lucro contábil de UMA identidade/janela, com a qualidade dos insumos explícita (F1-08)."""

    unidade: ChaveUnidade
    valor: Optional[Dinheiro]
    motivo: Optional[str]
    maturidade_receita: Optional[Maturidade] = None
    maturidade_custo: Optional[Maturidade] = None
    metodo_receita: Optional[MetodoAtribuicao] = None
    value_kind_receita: Optional[ValueKind] = None
    cobertura_completa: Optional[bool] = None

    @property
    def preliminar(self) -> bool:
        return Maturidade.PRELIMINAR in (self.maturidade_receita, self.maturidade_custo)


def contribuicao(custo: Observacao, receita: Observacao, *, aceitar_parcial: bool = False) -> Contribuicao:
    """Receita contábil − custo na MESMA identidade/janela. Sem valor quando não é defensável.

    Cobertura parcial só produz número com `aceitar_parcial=True`, e o resultado sai marcado
    (`cobertura_completa=False`); preliminar sempre sai marcado (`preliminar=True`).
    """
    if custo.metrica is not Metrica.CUSTO or receita.metrica is not Metrica.RECEITA:
        raise ContratoViolado("contribuicao(custo, receita) recebeu métricas trocadas")
    exigir_mesma_identidade(custo, receita)
    completa = custo.cobertura is Cobertura.COMPLETA and receita.cobertura is Cobertura.COMPLETA
    marcas = dict(maturidade_receita=receita.maturidade, maturidade_custo=custo.maturidade,
                  metodo_receita=receita.metodo, value_kind_receita=receita.value_kind,
                  cobertura_completa=completa)
    if receita.value_kind not in RECEITA_CONTABIL:
        return Contribuicao(custo.unidade, None, f"receita {receita.value_kind.value if receita.value_kind else None} não é contábil", **marcas)
    if receita.metodo in METODOS_NAO_RECONCILIADOS:
        return Contribuicao(custo.unidade, None, f"método de atribuição {receita.metodo.value} não sustenta lucro", **marcas)
    if custo.estado not in COM_VALOR or receita.estado not in COM_VALOR:
        return Contribuicao(custo.unidade, None, "custo ou receita sem valor (null != 0)", **marcas)
    if not completa and not aceitar_parcial:
        return Contribuicao(custo.unidade, None, "cobertura incompleta de custo ou receita", **marcas)
    # preliminar é permitido, mas sai MARCADO (`preliminar=True`), nunca como lucro fechado
    return Contribuicao(custo.unidade, receita.valor - custo.valor, None, **marcas)  # type: ignore[operator]


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


# Vocabulário FECHADO de famílias de fonte. "JoinAds", "joinads:v2" e "joinads " são a mesma
# família; origem desconhecida é erro, não "não circular" (F1-04).
FAMILIAS_DE_FONTE = frozenset({
    "google_ads", "google_ads_conversion", "meta", "gam", "joinads", "adsense", "publisher_report",
    "browser", "browser_beacon", "ga4", "sintetico",
})
# Famílias que medem a MESMA receita publisher (receita ≈ impressões × eCPM da mesma fonte).
_MESMA_RECEITA = ({"gam", "joinads", "adsense", "publisher_report"},)


def familia_de_fonte(origem: str) -> str:
    base = str(origem).strip().lower().split(":", 1)[0].split("/", 1)[0].strip()
    if base not in FAMILIAS_DE_FONTE:
        raise ContratoViolado(f"origem fora do vocabulário de fontes: {origem!r}")
    return base


def origens_circulares(origem_feature: str, origem_rotulo: str) -> bool:
    """Regra única de circularidade por fonte: mesma família, ou famílias que medem a mesma receita."""
    a, b = familia_de_fonte(origem_feature), familia_de_fonte(origem_rotulo)
    return a == b or any(a in g and b in g for g in _MESMA_RECEITA)


def verificar_nao_circular(features: Sequence[Observacao], rotulo: Observacao) -> None:
    """Feature circular: mesma coleta/linhagem, mesma família de fonte, ou receita da mesma entidade
    (qualquer grão/dimensão) cuja janela intersecta a do rótulo (F1-04)."""
    origem_rotulo = {rotulo.coleta_id, *rotulo.linhagem}
    ent_rotulo = (rotulo.unidade.conta, rotulo.unidade.tipo_entidade, rotulo.unidade.entidade_id)
    for f in features:
        origem = {f.coleta_id, *f.linhagem}
        if origem & origem_rotulo:
            raise Circularidade(f"feature {f.metrica.value}/{f.fonte} compartilha origem com o rótulo: {sorted(origem & origem_rotulo)}")
        if origens_circulares(f.fonte, rotulo.fonte):
            raise Circularidade(f"feature {f.metrica.value} vem da mesma família de fonte do rótulo ({f.fonte} × {rotulo.fonte})")
        ent = (f.unidade.conta, f.unidade.tipo_entidade, f.unidade.entidade_id)
        intersecta = f.janela_inicio < rotulo.janela_fim and rotulo.janela_inicio < f.janela_fim
        if f.metrica is Metrica.RECEITA and ent == ent_rotulo and intersecta:
            raise Circularidade("feature é receita da mesma entidade com janela que intersecta a do rótulo")
