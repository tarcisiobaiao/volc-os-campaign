"""Painéis ``as_of`` vetorizados a partir de registros de observação (campanha × dia).

Mesma semântica do consumidor de referência ``simulador.visao_as_of`` (testado por equivalência):
- corte pelo relógio de conhecimento (``available_at`` por default; ``observed_at`` só existe
  para DEMONSTRAR vazamento);
- só registros com valor (``STATUS_COM_VALOR``) e, por default, ``custom_key_efetiva ==
  custom_key_solicitada``;
- versão vigente = medição mais recente (``observed_at``), empate → chegada (``available_at``,
  ``ingested_at``, ``obs_id``);
- célula sem versão conhecida fica ``NaN`` (ausência ≠ 0).

A diferença para ``visao_as_of`` é só desempenho: os registros são indexados uma vez e cada
corte é uma operação numpy, o que viabiliza rolling-origin com dezenas de cortes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, Sequence

import numpy as np

from volc_dil.fundacao.simulador.registro import STATUS_COM_VALOR, RegistroObservacao

GRAO_CAMPANHA_DIA = ("campaign", "day")
MATURIDADES = ("intradiaria", "preliminar", "final", "nao_aplicavel")
RELOGIOS = ("available_at", "observed_at")


def epoch(iso: str) -> int:
    """ISO UTC canônico → segundos desde a época (int)."""
    return int(datetime.fromisoformat(iso).timestamp())


@dataclass
class TabelaVersoes:
    """Todas as versões com valor de uma (fonte, métrica) no grão campanha × dia, indexadas."""

    fonte: str
    metrica: str
    entidades: tuple[str, ...]
    dias: tuple[str, ...]            # janela_inicio ISO de cada dia, em ordem
    ent: np.ndarray                  # índice da entidade por versão
    dia: np.ndarray                  # índice do dia por versão
    available: np.ndarray            # epoch s
    observed: np.ndarray             # epoch s
    valor: np.ndarray                # float (micros ou contagem)
    maturidade: np.ndarray           # índice em MATURIDADES
    tipo_leitura: np.ndarray         # str
    n_sem_valor: int                 # registros do recorte sem valor (missing/unavailable/...)

    @classmethod
    def de_registros(cls, registros: Iterable[RegistroObservacao], *, fonte: str, metrica: str,
                     entidades: Optional[Sequence[str]] = None, dias: Optional[Sequence[str]] = None,
                     exigir_custom_key: bool = True, relogio_ordem: str = "observed_at") -> "TabelaVersoes":
        sel = [r for r in registros if r.fonte == fonte and r.metrica == metrica
               and r.entidade_tipo == "campaign" and tuple(r.grao) == GRAO_CAMPANHA_DIA and not r.dimensoes]
        n_sem = sum(1 for r in sel if r.status not in STATUS_COM_VALOR)
        cand = [r for r in sel if r.status in STATUS_COM_VALOR
                and (not exigir_custom_key or r.custom_key_efetiva == r.custom_key_solicitada)]
        ents = tuple(entidades) if entidades is not None else tuple(sorted({r.entidade for r in cand}))
        ds = tuple(dias) if dias is not None else tuple(sorted({r.janela_inicio for r in cand}))
        ie = {e: i for i, e in enumerate(ents)}
        idd = {d: i for i, d in enumerate(ds)}
        cand = [r for r in cand if r.entidade in ie and r.janela_inicio in idd]
        # ordem: fato, depois versão (observed, available, ingested, obs_id) — como _versao do consumidor
        chave = [(ie[r.entidade], idd[r.janela_inicio], r.observed_at, r.available_at, r.ingested_at, r.obs_id)
                 for r in cand]
        ordem = sorted(range(len(cand)), key=chave.__getitem__)
        cand = [cand[i] for i in ordem]
        mi = {m: i for i, m in enumerate(MATURIDADES)}
        return cls(
            fonte=fonte, metrica=metrica, entidades=ents, dias=ds,
            ent=np.array([ie[r.entidade] for r in cand], dtype=np.int64),
            dia=np.array([idd[r.janela_inicio] for r in cand], dtype=np.int64),
            available=np.array([epoch(r.available_at) for r in cand], dtype=np.int64),
            observed=np.array([epoch(r.observed_at) for r in cand], dtype=np.int64),
            valor=np.array([float(r.valor) for r in cand], dtype=float),
            maturidade=np.array([mi.get(r.maturidade, 3) for r in cand], dtype=np.int64),
            tipo_leitura=np.array([r.tipo_leitura for r in cand], dtype=object),
            n_sem_valor=n_sem,
        )

    @property
    def forma(self) -> tuple[int, int]:
        return len(self.entidades), len(self.dias)

    def _escolher(self, as_of: int, relogio: str) -> np.ndarray:
        if relogio not in RELOGIOS:
            raise ValueError(f"relógio desconhecido: {relogio!r}")
        rel = self.available if relogio == "available_at" else self.observed
        idx = np.nonzero(rel <= as_of)[0]
        if idx.size == 0:
            return idx
        fato = self.ent[idx] * len(self.dias) + self.dia[idx]
        # ordenado por fato e versão: o último de cada fato é a versão vigente
        ultimo = np.r_[fato[1:] != fato[:-1], True]
        return idx[ultimo]

    def painel(self, as_of: int, *, relogio: str = "available_at") -> np.ndarray:
        """(E, D) valor vigente em ``as_of`` (epoch s); NaN onde nada com valor era conhecido."""
        out = np.full(self.forma, np.nan)
        esc = self._escolher(as_of, relogio)
        out[self.ent[esc], self.dia[esc]] = self.valor[esc]
        return out

    def painel_maturidade(self, as_of: int, *, relogio: str = "available_at") -> np.ndarray:
        """(E, D) índice em ``MATURIDADES`` da versão vigente; -1 onde não há versão."""
        out = np.full(self.forma, -1, dtype=np.int64)
        esc = self._escolher(as_of, relogio)
        out[self.ent[esc], self.dia[esc]] = self.maturidade[esc]
        return out

    def final(self) -> np.ndarray:
        """Última versão de todas (o mundo inteiro acaba observado). Avaliação/treino tardio apenas."""
        return self.painel(np.iinfo(np.int64).max)

    def n_versoes_distintas(self) -> np.ndarray:
        """(E, D) número de valores distintos já emitidos por fato (ex.: D0 multiversão)."""
        out = np.zeros(self.forma, dtype=np.int64)
        fato = self.ent * len(self.dias) + self.dia
        pares = np.unique(np.stack([fato, self.valor.view(np.int64)]), axis=1)
        f, n = np.unique(pares[0], return_counts=True)
        out.ravel()[f] = n
        return out


def instante_local(mundo_ou_calendario, dia_idx: int, hora: float) -> int:
    """Epoch s de ``dia_idx`` + ``hora`` no calendário local do mundo (só calendário, não verdade)."""
    return int(mundo_ou_calendario.instante_local(dia_idx, hora).timestamp())


def dias_iso(mundo) -> tuple[str, ...]:
    """``janela_inicio`` ISO de cada dia do calendário (mesmo formato do observador)."""
    from volc_dil.fundacao.simulador import iso

    return tuple(iso(mundo.instante_local(i, 0)) for i in range(mundo.D))


def ids_campanhas(mundo) -> tuple[str, ...]:
    return tuple(c.id for c in mundo.campanhas)


__all__ = ["GRAO_CAMPANHA_DIA", "MATURIDADES", "RELOGIOS", "TabelaVersoes", "dias_iso", "epoch", "ids_campanhas",
           "instante_local"]
