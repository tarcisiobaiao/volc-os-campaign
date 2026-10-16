"""Snapshot econômico `as_of`: imutável, versionado e com fingerprint.

Duas políticas para dados posteriores ao corte:

- `excluir` (padrão do construtor de snapshot): observações com `disponivel_em > as_of`
  ficam de fora e são CONTADAS no manifesto — o leitor vê quanto futuro foi cortado;
- `falhar` (usada por consumidores que recebem dados já cortados, como o replay e
  as features): qualquer observação posterior ao corte levanta `VazamentoDeFuturo`.

Revisões (restatement) compartilham a `chave_logica`; o snapshot escolhe a versão mais
recente CONHECIDA no `as_of`, nunca a versão final do mundo.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Literal, Optional

from .fingerprint import sha256_de
from .observation import ContratoViolado, Observacao
from .vocab import Cobertura, Metrica

ESQUEMA_SNAPSHOT = "volc-dil.snapshot.v1"


class VazamentoDeFuturo(RuntimeError):
    """Informação posterior ao `as_of` chegou a quem decide no `as_of`."""


class VersaoAmbigua(ContratoViolado):
    """Duas versões do mesmo fato, conhecidas no mesmo instante, com conteúdos diferentes."""


def _exigir_tz(as_of: datetime) -> None:
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ContratoViolado("as_of precisa ser datetime com timezone")


def verificar_sem_futuro(observacoes: Iterable[Observacao], as_of: datetime) -> None:
    _exigir_tz(as_of)
    for o in observacoes:
        if o.disponivel_em > as_of:
            raise VazamentoDeFuturo(
                f"observação disponível em {o.disponivel_em.isoformat()} usada no as_of {as_of.isoformat()} "
                f"({o.unidade.entidade_id}/{o.metrica.value}/{o.fonte})"
            )


@dataclass(frozen=True)
class Snapshot:
    as_of: datetime
    observacoes: tuple[Observacao, ...]
    manifesto: dict

    @property
    def fingerprint(self) -> str:
        return self.manifesto["fingerprint"]

    @classmethod
    def construir(
        cls,
        observacoes: Iterable[Observacao],
        as_of: datetime,
        *,
        politica_futuro: Literal["excluir", "falhar"] = "excluir",
        rotulo: str = "",
    ) -> "Snapshot":
        _exigir_tz(as_of)
        todas = list(observacoes)
        if politica_futuro == "falhar":
            verificar_sem_futuro(todas, as_of)
        conhecidas = [o for o in todas if o.disponivel_em <= as_of]
        futuras = len(todas) - len(conhecidas)

        for o in conhecidas:
            if o.janela_fim > as_of and o.cobertura is Cobertura.COMPLETA:
                raise ContratoViolado(
                    "cobertura completa para janela ainda aberta no as_of: indício de dado do futuro "
                    f"({o.unidade.entidade_id}/{o.metrica.value})"
                )

        por_chave: dict[tuple, list[Observacao]] = {}
        for o in conhecidas:
            por_chave.setdefault(o.chave_logica, []).append(o)
        escolhidas: list[Observacao] = []
        substituidas = 0
        for chave, versoes in por_chave.items():
            versoes.sort(key=lambda x: x.disponivel_em)
            ultima = versoes[-1]
            empatadas = [v for v in versoes if v.disponivel_em == ultima.disponivel_em]
            # só serializa/hasheia quando há empate (perfil da bancada: ~90% do tempo era aqui)
            if len(empatadas) > 1 and len({sha256_de(v.para_json()) for v in empatadas}) > 1:
                raise VersaoAmbigua(f"versões conflitantes do mesmo fato no mesmo instante: {chave[0].entidade_id}/{chave[1]}")
            escolhidas.append(ultima)
            substituidas += len(versoes) - len(empatadas)

        pares = sorted(((sha256_de(j), j, o) for o in escolhidas for j in (o.para_json(),)), key=lambda x: x[0])
        escolhidas = [o for _, _, o in pares]
        corpo = [j for _, j, _ in pares]
        moedas = Counter(o.moeda for o in escolhidas if o.moeda)
        manifesto = {
            "esquema": ESQUEMA_SNAPSHOT,
            "rotulo": rotulo,
            "as_of": as_of.isoformat(),
            "n_entrada": len(todas),
            "n_incluidas": len(escolhidas),
            "n_futuras_excluidas": futuras,
            "n_versoes_substituidas": substituidas,
            "fontes": sorted({o.fonte for o in escolhidas}),
            "moedas": dict(sorted(moedas.items())),
            "value_kinds": dict(sorted(Counter(o.value_kind.value for o in escolhidas if o.value_kind).items())),
            "cobertura": dict(sorted(Counter(o.cobertura.value for o in escolhidas).items())),
            "maturidade": dict(sorted(Counter(o.maturidade.value for o in escolhidas).items())),
            "estados": dict(sorted(Counter(o.estado.value for o in escolhidas).items())),
            "fingerprint": sha256_de({"as_of": as_of.isoformat(), "observacoes": corpo}),
        }
        return cls(as_of=as_of, observacoes=tuple(escolhidas), manifesto=manifesto)

    def filtrar(self, *, metrica: Optional[Metrica] = None, entidade_id: Optional[str] = None) -> list[Observacao]:
        return [
            o
            for o in self.observacoes
            if (metrica is None or o.metrica is metrica)
            and (entidade_id is None or o.unidade.entidade_id == entidade_id)
        ]

    def verificar_integridade(self) -> None:
        """Recalcula o fingerprint e garante que nada posterior ao corte entrou."""
        verificar_sem_futuro(self.observacoes, self.as_of)
        corpo = [o.para_json() for o in self.observacoes]
        if sha256_de({"as_of": self.as_of.isoformat(), "observacoes": corpo}) != self.fingerprint:
            raise ContratoViolado("fingerprint do snapshot não confere")
