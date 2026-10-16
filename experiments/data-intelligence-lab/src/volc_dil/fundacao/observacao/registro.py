"""Registro append-only em memória: as mesmas regras de `dil_obs.registrar_observacao`.

Serve de oráculo para o banco (teste de equivalência) e de armazenamento para replay/
simulação hermética. Nada é atualizado nem apagado: `registrar` só acrescenta ou não faz nada.

Regras (iguais às do SQL):

1. `chave_base` nova → INSERIDO (tipo `leitura`).
   Se já existe outra versão da mesma chave natural com o MESMO `available_at` → `VersaoAmbigua`.
2. `chave_base` já existe:
   a. conteúdo (status, valor, unidade, moeda, cobertura) diferente → `ConflitoIdempotencia`
      (coletor não determinístico: a mesma leitura não pode dar dois números);
   b. a versão vigente (maior `available_at`) é desta mesma leitura, ou o novo `available_at`
      não é posterior à vigente → NOOP (retry, releitura, reentrega fora de ordem);
   c. senão → REAFIRMADO: a leitura voltou a ser verdade depois de outra versão (A→B→A).
      Registra-se uma versão nova com chave derivada de (chave_base, available_at).

A regra 2b é conservadora: reentrega fora de ordem nunca antecipa conhecimento, só pode atrasá-lo.
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


class ConflitoIdempotencia(ContratoViolado):
    """A mesma leitura (mesma chave de idempotência) chegou com conteúdo diferente."""


class ResultadoRegistro(str, enum.Enum):
    INSERIDO = "inserido"
    NOOP = "noop"
    REAFIRMADO = "reafirmado"


class TipoRegistro(str, enum.Enum):
    LEITURA = "leitura"
    REAFIRMACAO = "reafirmacao"


@dataclass(frozen=True)
class VersaoRegistrada:
    observacao: Observacao
    chave_idempotencia: str
    chave_base: str
    chave_natural: str
    tipo: TipoRegistro


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
        vs = self._por_natural.get(chave_natural)
        if not vs:
            return None
        return max(vs, key=lambda v: v.observacao.available_at)

    def _gravar(self, obs: Observacao, chave: str, base: str, nat: str, tipo: TipoRegistro) -> None:
        for v in self._por_natural.get(nat, ()):
            if v.observacao.available_at == obs.available_at:
                raise VersaoAmbigua(
                    f"duas versões do mesmo fato com o mesmo available_at ({chaves.instante_canonico(obs.available_at)})"
                )
        reg = VersaoRegistrada(obs, chave, base, nat, tipo)
        self._versoes.append(reg)
        self._por_chave[chave] = reg
        self._por_natural.setdefault(nat, []).append(reg)

    def registrar(self, obs: Observacao) -> ResultadoRegistro:
        if not isinstance(obs, Observacao):
            raise ContratoViolado("registrar recebe Observacao")
        nat, base = obs.chave_natural, obs.chave_base
        existente = self._por_chave.get(base)
        if existente is None:
            self._gravar(obs, base, base, nat, TipoRegistro.LEITURA)
            return ResultadoRegistro.INSERIDO
        if existente.observacao.conteudo != obs.conteudo:
            raise ConflitoIdempotencia(
                f"mesma leitura com conteúdo diferente: {existente.observacao.conteudo} × {obs.conteudo}"
            )
        vig = self.vigente(nat)
        assert vig is not None
        if vig.chave_base == base or obs.available_at <= vig.observacao.available_at:
            return ResultadoRegistro.NOOP
        chave = chaves.chave_reafirmacao(chave_base_hex=base, available_at=obs.available_at)
        if chave in self._por_chave:
            return ResultadoRegistro.NOOP
        self._gravar(obs, chave, base, nat, TipoRegistro.REAFIRMACAO)
        return ResultadoRegistro.REAFIRMADO

    def registrar_todas(self, observacoes: Iterable[Observacao]) -> list[ResultadoRegistro]:
        return [self.registrar(o) for o in observacoes]

    def historico(self, chave_natural: str) -> tuple[VersaoRegistrada, ...]:
        """Todas as versões do fato, em ordem de `available_at`. Nada some."""
        return tuple(sorted(self._por_natural.get(chave_natural, ()), key=lambda v: v.observacao.available_at))

    def as_of(self, t: datetime):
        from .asof import as_of

        return as_of(self.observacoes, t)
