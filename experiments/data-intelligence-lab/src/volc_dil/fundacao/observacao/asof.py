"""Leitura `as_of`, ponte para o contrato econômico herdado e agregação que não inventa zero.

- `as_of(obs, t)`: por chave natural, entre as versões com `available_at <= t`, a de maior
  `observed_at` (empate: maior `available_at`) — D1. O status é preservado (um `missing` vigente continua `missing`; não vira 0 nem some).
- `latest(obs, agora)`: é só `as_of(obs, agora)`. Não há relógio implícito: quem chama diz
  que horas são, e o histórico fica intacto.
- `para_contrato_economico(obs)`: adapta para `volc_dil.contracts.Observacao` (composição,
  não cópia). Assim `Snapshot`, `agregar`, `contribuicao` e `rotulo_economico` herdados
  continuam sendo a única regra econômica.
- `agregar_observacoes(obs)`: usa `volc_dil.contracts.agregar` e acrescenta a contagem por
  status fino, para que `missing`, `late` e `unavailable` não se fundam num só "sem valor".
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from ...contracts.aggregate import Agregado, agregar
from ...contracts.money import Dinheiro
from ...contracts.observation import ChaveUnidade, ContratoViolado
from ...contracts.observation import Observacao as ObservacaoEconomica
from ...contracts.snapshot import VersaoAmbigua
from ...contracts.vocab import Cobertura, EstadoMedida, Maturidade, MetodoAtribuicao
from .modelo import Observacao
from .chaves import instante_canonico
from .registro import ConflitoIdempotencia, ordem_versao
from .vocab import MAPA_ESTADO_HERDADO, StatusObservacao, Unidade


def _exigir_tz(t: datetime) -> None:
    if not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None:
        raise ContratoViolado("as_of precisa ser datetime com timezone")


def vigente_entre(itens: Iterable[Any], *, obs: Callable[[Any], Observacao] = lambda x: x,
                  base: Optional[Callable[[Any], str]] = None) -> Optional[Any]:
    """Versão vigente entre itens de UMA chave natural já visíveis no corte. Independe da ordem de entrada (D3).

    Vence a maior `ordem_versao` = (`observed_at`, `available_at`) (D1). Empate no topo entre leituras
    diferentes → `VersaoAmbigua`; mesma leitura com conteúdo diferente → `ConflitoIdempotencia`; cópias
    idênticas → uma só (representante determinístico). Empates em versões já SUPERADAS não importam para o
    estado em T e não levantam — antes a exceção dependia da ordem em que as versões chegavam.
    Não desempata leituras diferentes por hash: escolheria um valor ao acaso; a escrita (Registro e SQL,
    UNIQUE (chave_natural, available_at)) já recusa esse empate, então dado registrado nunca o tem.
    """
    lista = list(itens)
    if not lista:
        return None
    chave_de = base or (lambda x: obs(x).chave_base)
    topo = max(ordem_versao(obs(i)) for i in lista)
    empatados = [i for i in lista if ordem_versao(obs(i)) == topo]
    if len({chave_de(i) for i in empatados}) > 1:
        raise VersaoAmbigua("duas leituras diferentes do mesmo fato no topo da ordem de versão (observed_at, available_at)")
    if len({obs(i).conteudo for i in empatados}) > 1:
        raise ConflitoIdempotencia("mesma leitura com conteúdo diferente no topo da ordem de versão")
    return min(empatados, key=lambda i: (obs(i).run_id, obs(i).lote_id, instante_canonico(obs(i).ingested_at)))


def as_of(observacoes: Iterable[Observacao], t: datetime) -> Mapping[str, Observacao]:
    """Estado conhecido em `t`: {chave_natural: versão vigente}. Puro, independente da ordem de entrada.

    Visíveis: `available_at <= t`. Entre as visíveis de um fato, vence a de maior `observed_at`; empate →
    maior `available_at` (D1). Ambiguidade só no topo (ver `vigente_entre`).
    """
    _exigir_tz(t)
    grupos: dict[str, list[Observacao]] = {}
    for o in observacoes:
        if not isinstance(o, Observacao):
            raise ContratoViolado("as_of recebe Observacao")
        if o.available_at <= t:
            grupos.setdefault(o.chave_natural, []).append(o)
    return MappingProxyType({nat: vigente_entre(vs) for nat, vs in sorted(grupos.items())})


def latest(observacoes: Iterable[Observacao], agora: datetime) -> Mapping[str, Observacao]:
    """`latest` = `as_of(agora)`. Existe só para nomear a intenção; não descarta histórico."""
    return as_of(observacoes, agora)


# --------------------------------------------------------------------------- ponte herdada
def para_contrato_economico(
    o: Observacao,
    *,
    maturidade: Maturidade = Maturidade.PRELIMINAR,
    metodo: MetodoAtribuicao = MetodoAtribuicao.NAO_APLICAVEL,
) -> ObservacaoEconomica:
    """Converte para o contrato econômico herdado (`volc_dil.contracts.Observacao`).

    Mapeamento: status → `EstadoMedida` (`MAPA_ESTADO_HERDADO`); `partial` sem valor vira
    `NAO_COLETADO`; cobertura `complete` só para observed/zero_confirmed (janela fechada),
    `partial` para partial e `unknown` para os demais; `disponivel_em = available_at`;
    `coleta_id = run_id`; linhagem = (lote, payload_ref). Maturidade e método não vêm da fonte
    bruta: o chamador declara (padrão: preliminar, não aplicável).
    """
    st = o.status
    estado = MAPA_ESTADO_HERDADO[st]
    if st is StatusObservacao.PARTIAL and o.valor is None:
        estado = EstadoMedida.NAO_COLETADO
    if st in (StatusObservacao.OBSERVED, StatusObservacao.ZERO_CONFIRMED):
        cobertura = Cobertura.COMPLETA
    elif st is StatusObservacao.PARTIAL:
        cobertura = Cobertura.PARCIAL
    else:
        cobertura = Cobertura.DESCONHECIDA
    valor: object
    if o.valor is None:
        valor = None
    elif o.unidade is Unidade.MICROS:
        valor = Dinheiro(o.valor, o.moeda)  # type: ignore[arg-type]
    else:
        valor = o.valor
    motivo = None if estado in (EstadoMedida.MEDIDO, EstadoMedida.ZERO_CONFIRMADO) else f"{st.value}: {o.motivo}"
    return ObservacaoEconomica(
        unidade=ChaveUnidade(
            conta=o.conta,
            tipo_entidade=o.entidade.tipo,
            entidade_id=o.entidade.id,
            grao=o.grao,
            dimensoes=o.dimensoes,
        ),
        metrica=o.metrica,
        valor=valor,  # type: ignore[arg-type]
        estado=estado,
        janela_inicio=o.janela_inicio,
        janela_fim=o.janela_fim,
        timezone=o.timezone,
        observado_em=o.observed_at,
        disponivel_em=o.available_at,
        fonte=o.fonte,
        versao_fonte=f"{o.schema_version};{o.coletor.nome}@{o.coletor.versao}",
        coleta_id=o.run_id,
        cobertura=cobertura,
        maturidade=maturidade,
        metodo=metodo,
        value_kind=o.value_kind,
        motivo=motivo,
        linhagem=(f"lote:{o.lote_id}", o.payload_ref),
    )


@dataclass(frozen=True)
class AgregadoObservacao:
    """Agregado herdado + o que ele não sabe contar: quantos de cada status fino e a cobertura parcial.

    `cobertura_minima_ppm`: menor cobertura declarada entre os membros `partial` (None se não há partial
    com cobertura); `n_cobertura_desconhecida`: quantos `partial` não sabem a própria cobertura (R1-F16/F17).
    """

    agregado: Agregado
    por_status: Mapping[str, int]
    cobertura_minima_ppm: Optional[int] = None
    n_cobertura_desconhecida: int = 0

    @property
    def valor(self) -> Optional[object]:
        return self.agregado.valor

    @property
    def tem_valor(self) -> bool:
        return self.agregado.tem_valor


def agregar_observacoes(
    observacoes: Sequence[Observacao],
    *,
    aceitar_parcial: bool = False,
    maturidade: Maturidade = Maturidade.PRELIMINAR,
    metodo: MetodoAtribuicao = MetodoAtribuicao.NAO_APLICAVEL,
) -> AgregadoObservacao:
    """Soma por composição com `contracts.agregar`: vazio → ausente; qualquer membro sem valor →
    total sem valor (salvo `aceitar_parcial`, que marca cobertura parcial). Nunca devolve 0 inventado.

    `partial` fica FORA do total por padrão (R1-F16): um dia com 1% de cobertura não vira parcela de um
    total `medido`. Só com `aceitar_parcial=True` o valor parcial entra, e o agregado sai `partial`.
    """
    economicas = []
    for o in observacoes:
        e = para_contrato_economico(o, maturidade=maturidade, metodo=metodo)
        if o.status is StatusObservacao.PARTIAL and not aceitar_parcial and e.valor is not None:
            e = replace(e, valor=None, estado=EstadoMedida.NAO_COLETADO,
                        motivo=f"partial fora do total: {o.motivo}")
        economicas.append(e)
    ag = agregar(economicas, aceitar_parcial=aceitar_parcial)
    contagem = Counter(o.status.value for o in observacoes)
    parciais = [o for o in observacoes if o.status is StatusObservacao.PARTIAL]
    conhecidas = [o.cobertura_ppm for o in parciais if o.cobertura_ppm is not None]
    return AgregadoObservacao(
        ag, MappingProxyType(dict(sorted(contagem.items()))),
        cobertura_minima_ppm=min(conhecidas) if conhecidas else None,
        n_cobertura_desconhecida=len(parciais) - len(conhecidas),
    )
