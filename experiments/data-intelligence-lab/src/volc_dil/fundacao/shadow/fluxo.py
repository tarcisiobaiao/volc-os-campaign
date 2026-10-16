"""Fluxo temporal de observações: índice por `available_at`, cortes T e `as_of(T)` barato.

`FluxoIndexado` calcula UMA vez por observação as chaves (natural e de idempotência, sha256 —
caras) e ordena o fluxo por `(available_at, chave_natural, chave_base)`. Cada corte T é um
prefixo do fluxo; `as_of(T)` aplica exatamente a regra de `volc_dil.fundacao.observacao.as_of`
(entre as visíveis, maior `observed_at`, depois maior `available_at`; ambiguidade no topo levanta) sobre esse prefixo — a
equivalência é provada em `test_shadow_corte.py` contra a função da thread A em todos os cortes.

Fingerprint dos visíveis: hash encadeado sobre o prefixo ordenado, pré-calculado. A ordem do
fluxo de entrada e reentregas idênticas (mesma leitura, mesmo `available_at`, mesmo conteúdo)
não mudam o fingerprint; qualquer observação visível nova muda. Observação futura (> T) não
entra — nem como contagem.
"""
from __future__ import annotations

import hashlib
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence

from volc_dil.contracts.observation import ContratoViolado
from volc_dil.contracts.snapshot import VersaoAmbigua

from ..observacao.chaves import instante_canonico
from ..observacao.modelo import Observacao
from ..observacao.asof import vigente_entre
from ..observacao.registro import ConflitoIdempotencia


def _exigir_tz(t: datetime) -> None:
    if not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None:
        raise ContratoViolado("corte precisa ser datetime com timezone")


@dataclass(frozen=True)
class ItemFluxo:
    obs: Observacao
    chave_natural: str
    chave_base: str
    available_at: datetime  # UTC
    assinatura: str


def _assinatura(o: Observacao, nat: str, base: str) -> str:
    return "|".join((nat, base, instante_canonico(o.available_at), o.status.value, "" if o.valor is None else str(o.valor),
                     o.moeda or "", "" if o.cobertura_ppm is None else str(o.cobertura_ppm)))


class FluxoIndexado:
    """Índice imutável de um fluxo append-only. Não guarda relógio: quem consulta diz o T."""

    def __init__(self, observacoes: Iterable[Observacao], *, ambiguidade: str = "falhar") -> None:
        """`ambiguidade="falhar"` (regra da A: `as_of` levanta `VersaoAmbigua`) ou `"quarentena"`: duas leituras
        DIFERENTES do mesmo fato com o mesmo `available_at` saem do índice (todas) e ficam em `quarentena`,
        para que o replay registre o defeito em vez de escolher uma versão ou parar."""
        if ambiguidade not in ("falhar", "quarentena"):
            raise ValueError(f"ambiguidade desconhecida: {ambiguidade!r}")
        vistos: dict[tuple[str, str], ItemFluxo] = {}
        for o in observacoes:
            if not isinstance(o, Observacao):
                raise ContratoViolado("o fluxo recebe volc_dil.fundacao.observacao.Observacao")
            nat, base = o.chave_natural, o.chave_base
            ts = o.available_at.astimezone(timezone.utc)
            chave = (base, instante_canonico(ts))
            atual = vistos.get(chave)
            if atual is not None:
                if atual.obs.conteudo != o.conteudo:
                    raise ConflitoIdempotencia("mesma leitura com conteúdo diferente no mesmo available_at")
                continue  # reentrega idêntica
            vistos[chave] = ItemFluxo(o, nat, base, ts, _assinatura(o, nat, base))
        self.ambiguidade = ambiguidade
        quarentena: list[ItemFluxo] = []
        if ambiguidade == "quarentena":
            grupos: dict[tuple[str, datetime], set[str]] = {}
            for i in vistos.values():
                grupos.setdefault((i.chave_natural, i.available_at), set()).add(i.chave_base)
            ambiguos = {k for k, bases in grupos.items() if len(bases) > 1}
            quarentena = [i for i in vistos.values() if (i.chave_natural, i.available_at) in ambiguos]
            vistos = {k: i for k, i in vistos.items() if (i.chave_natural, i.available_at) not in ambiguos}
        self._quarentena = tuple(sorted(quarentena, key=lambda i: (i.available_at, i.chave_natural, i.chave_base)))
        self._ts_quarentena = [i.available_at for i in self._quarentena]
        self._itens: tuple[ItemFluxo, ...] = tuple(sorted(vistos.values(), key=lambda i: (i.available_at, i.chave_natural, i.chave_base)))
        self._ts = [i.available_at for i in self._itens]
        acumulado = []
        h = hashlib.sha256(b"volc-dil.shadow.fluxo.v1").hexdigest()
        for i in self._itens:
            h = hashlib.sha256(f"{h}\x1f{i.assinatura}".encode()).hexdigest()
            acumulado.append(h)
        self._hashes = acumulado

    def __len__(self) -> int:
        return len(self._itens)

    @property
    def itens(self) -> tuple[ItemFluxo, ...]:
        return self._itens

    @property
    def quarentena(self) -> tuple[ItemFluxo, ...]:
        return self._quarentena

    @property
    def observacoes(self) -> tuple[Observacao, ...]:
        return tuple(i.obs for i in self._itens)

    def primeiro_available_at(self) -> Optional[datetime]:
        return self._ts[0] if self._ts else None

    def ultimo_available_at(self) -> Optional[datetime]:
        return self._ts[-1] if self._ts else None

    def _n(self, t: datetime) -> int:
        _exigir_tz(t)
        return bisect_right(self._ts, t.astimezone(timezone.utc))

    def quarentena_visivel(self, t: datetime) -> tuple[ItemFluxo, ...]:
        """Leituras ambíguas já conhecidas em t (fora do as_of, registradas no snapshot)."""
        _exigir_tz(t)
        return self._quarentena[: bisect_right(self._ts_quarentena, t.astimezone(timezone.utc))]

    def visiveis(self, t: datetime) -> tuple[ItemFluxo, ...]:
        return self._itens[: self._n(t)]

    def n_visiveis(self, t: datetime) -> int:
        return self._n(t)

    def fingerprint_visiveis(self, t: datetime) -> str:
        n = self._n(t)
        return self._hashes[n - 1] if n else hashlib.sha256(b"volc-dil.shadow.fluxo.v1").hexdigest()

    def as_of(self, t: datetime) -> dict[str, ItemFluxo]:
        """{chave_natural: item vigente em t}. Mesma regra de `observacao.as_of`.

        [thread A, D1/D3] a seleção delega a `observacao.vigente_entre` (regra única: maior observed_at,
        depois maior available_at; ambiguidade só no topo, independente da ordem)."""
        grupos: dict[str, list[ItemFluxo]] = {}
        for i in self.visiveis(t):
            grupos.setdefault(i.chave_natural, []).append(i)
        return {nat: vigente_entre(itens, obs=lambda x: x.obs, base=lambda x: x.chave_base)
                for nat, itens in grupos.items()}

    def n_versoes(self, t: datetime) -> dict[str, int]:
        """Quantas versões (leituras distintas) de cada fato eram conhecidas em t."""
        cont: dict[str, int] = {}
        for i in self.visiveis(t):
            cont[i.chave_natural] = cont.get(i.chave_natural, 0) + 1
        return cont


def cortes_regulares(inicio: datetime, fim: datetime, passo: timedelta = timedelta(hours=1)) -> tuple[datetime, ...]:
    """Cortes T em `[inicio, fim]` a cada `passo` (ex.: a cada hora de coleta)."""
    _exigir_tz(inicio)
    _exigir_tz(fim)
    if passo <= timedelta(0):
        raise ValueError("passo precisa ser positivo")
    saida, t = [], inicio
    while t <= fim:
        saida.append(t)
        t = t + passo
    return tuple(saida)


def acrescentar(fluxo: Sequence[Observacao], extras: Iterable[Observacao]) -> tuple[Observacao, ...]:
    """Fluxo append-only + observações novas (nada é removido nem trocado)."""
    return tuple(fluxo) + tuple(extras)
