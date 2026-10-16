"""Registro append-only em memória: as mesmas regras de `dil_obs.registrar_observacao`.

Serve de oráculo para o banco (teste de equivalência) e de armazenamento para replay/
simulação hermética. Nada é atualizado nem apagado: `registrar` só acrescenta ou não faz nada.

Regras (iguais às do SQL):

1. `chave_base` nova → INSERIDO. Se já existe outra leitura do mesmo fato com o MESMO `available_at`
   → `VersaoAmbigua` (espelho do UNIQUE (chave_natural, available_at)).
2. `chave_base` já existe (a MESMA leitura: mesmo payload, coletor, esquema e `observed_at`):
   a. conteúdo (status, valor, unidade, moeda, cobertura) diferente → `ConflitoIdempotencia`
      (coletor não determinístico: a mesma leitura não pode dar dois números);
   b. senão → NOOP (retry, reentrega, reentrega fora de ordem). Reentrega nunca antecipa conhecimento.

`observed_at` faz parte da chave da leitura (D1/D2): o cron que relê o mesmo payload em outra hora é uma
leitura NOVA e vira versão — é o que mantém exata a ordem do `as_of` (maior `observed_at` vence) e o que
permite a mesma janela passar de `partial` a fechada, ou mudar de cobertura, sem conflito. A antiga
"reafirmação" (A→B→A com chave derivada) deixou de existir: a volta de A já é uma leitura nova.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from ...contracts.observation import ContratoViolado
from ...contracts.snapshot import VersaoAmbigua
from . import chaves
from .modelo import Observacao


def ordem_versao(o: Observacao) -> tuple:
    """Ordem de versão de um mesmo fato (D1): a leitura MAIS RECENTE da fonte vence (`observed_at`); entre
    leituras do mesmo instante, a conhecida por último (`available_at`). Uma leitura antiga que chega atrasada
    (observed_at menor, available_at maior) não desfaz a mais nova."""
    return (o.observed_at, o.available_at)


class ConflitoIdempotencia(ContratoViolado):
    """A mesma leitura (mesma chave de idempotência) chegou com conteúdo diferente."""


class ResultadoRegistro(str, enum.Enum):
    INSERIDO = "inserido"
    NOOP = "noop"


@dataclass(frozen=True)
class VersaoRegistrada:
    observacao: Observacao
    chave_idempotencia: str
    chave_natural: str


class Registro:
    """Armazenamento append-only. `versoes` é uma tupla nova a cada leitura (o chamador não muta o estado)."""

    def __init__(self, observacoes: Iterable[Observacao] = ()) -> None:
        self._versoes: list[VersaoRegistrada] = []
        self._por_chave: dict[str, VersaoRegistrada] = {}
        self._por_natural: dict[str, list[VersaoRegistrada]] = {}
        for o in observacoes:
            self.registrar(o)

    @property
    def versoes(self) -> tuple[VersaoRegistrada, ...]:
        return tuple(self._versoes)

    @property
    def observacoes(self) -> tuple[Observacao, ...]:
        return tuple(v.observacao for v in self._versoes)

    def __len__(self) -> int:
        return len(self._versoes)

    def vigente(self, chave_natural: str) -> Optional[VersaoRegistrada]:
        """Versão vigente HOJE (todas as registradas), na ordem do `as_of`."""
        vs = self._por_natural.get(chave_natural)
        if not vs:
            return None
        return max(vs, key=lambda v: ordem_versao(v.observacao))

    def registrar(self, obs: Observacao) -> ResultadoRegistro:
        if not isinstance(obs, Observacao):
            raise ContratoViolado("registrar recebe Observacao")
        nat, base = obs.chave_natural, obs.chave_base
        existente = self._por_chave.get(base)
        if existente is not None:
            if existente.observacao.conteudo != obs.conteudo:
                raise ConflitoIdempotencia(
                    f"mesma leitura com conteúdo diferente: {existente.observacao.conteudo} × {obs.conteudo}"
                )
            return ResultadoRegistro.NOOP
        for v in self._por_natural.get(nat, ()):
            if v.observacao.available_at == obs.available_at:
                raise VersaoAmbigua(
                    f"duas leituras do mesmo fato com o mesmo available_at ({chaves.instante_canonico(obs.available_at)})"
                )
        reg = VersaoRegistrada(obs, base, nat)
        self._versoes.append(reg)
        self._por_chave[base] = reg
        self._por_natural.setdefault(nat, []).append(reg)
        return ResultadoRegistro.INSERIDO

    def registrar_todas(self, observacoes: Iterable[Observacao]) -> list[ResultadoRegistro]:
        return [self.registrar(o) for o in observacoes]

    def historico(self, chave_natural: str) -> tuple[VersaoRegistrada, ...]:
        """Todas as versões do fato, em ordem de chegada ao conhecimento (`available_at`). Nada some."""
        return tuple(sorted(self._por_natural.get(chave_natural, ()), key=lambda v: v.observacao.available_at))

    def as_of(self, t: datetime):
        from .asof import as_of

        return as_of(self.observacoes, t)
