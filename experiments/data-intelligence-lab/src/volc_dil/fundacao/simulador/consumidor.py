"""Consumidores de REFERÊNCIA (mínimos) para demonstrar as armadilhas. Não é o replay/shadow.

``visao_as_of`` é o consumidor correto mínimo: corta por ``available_at`` (o que se sabia em
``as_of``), escolhe a versão pela medição mais recente (``observed_at``; empate → chegada),
ignora status sem valor, deduplica por fato e exige ``custom_key_efetiva == custom_key_solicitada``.
``soma_ingenua`` é a anti-referência (como ``proporcional_ingenua`` do replay herdado): soma
tudo que tem número, sem moeda, sem dedupe, sem chave — serve de contraprova nos testes.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .registro import STATUS_COM_VALOR, RegistroObservacao

RELOGIOS = ("available_at", "observed_at", "ingested_at", "janela_fim")


def chave_fato(r: RegistroObservacao) -> tuple:
    return (r.fonte, r.conta, r.entidade_tipo, r.entidade, r.metrica, r.janela_inicio, r.janela_fim, r.dimensoes)


def _versao(r: RegistroObservacao) -> tuple:
    return (r.observed_at, r.available_at, r.ingested_at, r.obs_id)


def visao_as_of(registros: Iterable[RegistroObservacao], as_of: str, *, relogio: str = "available_at",
                exigir_custom_key: bool = True) -> dict[tuple, RegistroObservacao]:
    """Último registro com valor conhecido por fato até ``as_of`` (ISO UTC canônico)."""
    if relogio not in RELOGIOS:
        raise ValueError(f"relógio desconhecido: {relogio!r}")
    melhor: dict[tuple, RegistroObservacao] = {}
    for r in registros:
        if getattr(r, relogio) > as_of or r.status not in STATUS_COM_VALOR:
            continue
        if exigir_custom_key and r.custom_key_efetiva != r.custom_key_solicitada:
            continue
        k = chave_fato(r)
        atual = melhor.get(k)
        # versão mais recente = medida mais recente (observed_at); empate → a que chegou depois.
        # Uma preliminar ATRASADA que chega depois da final não a substitui.
        if atual is None or _versao(r) > _versao(atual):
            melhor[k] = r
    return melhor


def somar_por_moeda(visao: dict[tuple, RegistroObservacao], metrica: str) -> dict[Optional[str], int]:
    out: dict[Optional[str], int] = {}
    for r in visao.values():
        if r.metrica == metrica and r.valor is not None:
            out[r.moeda] = out.get(r.moeda, 0) + r.valor
    return dict(sorted(out.items(), key=lambda kv: (kv[0] is None, kv[0] or "")))


def soma_ingenua(registros: Iterable[RegistroObservacao], metrica: str, *, ate: Optional[str] = None,
                 relogio: str = "observed_at") -> int:
    """ANTI-REFERÊNCIA: soma o último valor por (entidade, dia) ignorando moeda, chave e available_at."""
    ult: dict[tuple, RegistroObservacao] = {}
    for r in registros:
        if r.metrica != metrica or r.valor is None:
            continue
        if ate is not None and getattr(r, relogio) > ate:
            continue
        k = (r.fonte, r.entidade, r.janela_inicio)
        if k not in ult or getattr(r, relogio) >= getattr(ult[k], relogio):
            ult[k] = r
    return sum(r.valor for r in ult.values())
