"""Registro append-only em memória: as mesmas regras de `dil_obs.registrar_observacao`.

Serve de oráculo para o banco (teste de equivalência) e de armazenamento para replay/
simulação hermética. Nada é atualizado nem apagado: `registrar` só acrescenta ou não faz nada.

Regras (iguais às do SQL; D1 + D2'):

1. A MESMA leitura (mesma `chave_base`: payload, coletor, esquema e `observed_at`) já registrada — como
   versão ou como confirmação → NOOP; com conteúdo diferente → `ConflitoIdempotencia`.
2. Leitura nova cujo estado de negócio (`estado_negocio`) é IGUAL ao da versão vigente no instante dela —
   e continua igual a toda versão que vença antes dela nos instantes seguintes — é REDUNDANTE: vira
   CONFIRMADO (registro estreito: "ainda é verdade em `observed_at`"), não versão. Retry continua NOOP.
3. Senão → INSERIDO (versão). Mesmo `available_at` de outra versão do fato → `VersaoAmbigua`.
4. Ao inserir uma versão X, para todo corte T >= X.available_at, o estado do vigente entre as VERSÕES
   tem de ser o do vigente entre versões + confirmações (como se toda leitura fosse versão). Onde divergir,
   a confirmação que vence ali é MATERIALIZADA como versão (a própria leitura, com seus relógios): uma
   leitura antiga e diferente chegando atrasada não passa à frente de uma confirmação mais nova. É o que
   torna o estado em qualquer corte independente da ordem de chegada (teste de propriedade com permutações).

Ordem de versão (D1): maior `observed_at`, depois maior `available_at`. A→B→A e o fechamento da janela
com o mesmo payload continuam gerando versão (o estado muda); releitura idêntica de hora em hora vira
confirmação (custo medido no HANDOFF-A §7.2).
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
    CONFIRMADO = "confirmado"


@dataclass(frozen=True)
class VersaoRegistrada:
    observacao: Observacao
    chave_idempotencia: str
    chave_natural: str


@dataclass(frozen=True)
class Confirmacao:
    """Releitura redundante: só chave, instantes, linhagem e a versão cujo estado ela repetiu.
    (Em memória guardamos a leitura inteira para poder materializá-la; no banco a linha é estreita.)"""

    chave_idempotencia: str
    chave_natural: str
    observed_at: datetime
    available_at: datetime
    run_id: str
    lote_id: str
    confirmada: VersaoRegistrada
    leitura: Observacao


def _redundante(r: Observacao, versoes: list[VersaoRegistrada]) -> Optional[VersaoRegistrada]:
    """Versão confirmada se `r` não muda o estado em nenhum corte >= r.available_at; senão None."""
    abaixo = [v for v in versoes if ordem_versao(v.observacao) < ordem_versao(r)]
    visiveis = [v for v in abaixo if v.observacao.available_at <= r.available_at]
    if not visiveis:
        return None
    atual = max(visiveis, key=lambda v: ordem_versao(v.observacao))
    if atual.observacao.estado_negocio != r.estado_negocio:
        return None
    confirmada = atual
    for x in sorted((v for v in abaixo if v.observacao.available_at > r.available_at),
                    key=lambda v: v.observacao.available_at):
        if ordem_versao(x.observacao) > ordem_versao(atual.observacao):
            if x.observacao.estado_negocio != r.estado_negocio:
                return None
            atual = x
    return confirmada


class Registro:
    """Armazenamento append-only. `versoes` é uma tupla nova a cada leitura (o chamador não muta o estado)."""

    def __init__(self, observacoes: Iterable[Observacao] = ()) -> None:
        self._versoes: list[VersaoRegistrada] = []
        self._por_chave: dict[str, VersaoRegistrada] = {}
        self._por_natural: dict[str, list[VersaoRegistrada]] = {}
        self._confirmacoes: dict[tuple, Confirmacao] = {}  # (chave_natural, observed_at, available_at)
        self._conf_por_natural: dict[str, list[Confirmacao]] = {}
        for o in observacoes:
            self.registrar(o)

    @property
    def versoes(self) -> tuple[VersaoRegistrada, ...]:
        return tuple(self._versoes)

    @property
    def observacoes(self) -> tuple[Observacao, ...]:
        return tuple(v.observacao for v in self._versoes)

    @property
    def confirmacoes(self) -> tuple[Confirmacao, ...]:
        return tuple(self._confirmacoes.values())

    def __len__(self) -> int:
        return len(self._versoes)

    def vigente(self, chave_natural: str) -> Optional[VersaoRegistrada]:
        """Versão vigente HOJE (todas as registradas), na ordem do `as_of`."""
        vs = self._por_natural.get(chave_natural)
        if not vs:
            return None
        return max(vs, key=lambda v: ordem_versao(v.observacao))

    def ultima_confirmacao(self, chave_natural: str) -> Optional[datetime]:
        """Frescor: o `observed_at` mais recente em que o estado vigente foi lido de novo (ou None)."""
        cs = self._conf_por_natural.get(chave_natural)
        return max((c.observed_at for c in cs), default=None) if cs else None

    def _inserir(self, obs: Observacao, base: str, nat: str) -> None:
        for v in self._por_natural.get(nat, ()):
            if v.observacao.available_at == obs.available_at:
                raise VersaoAmbigua(
                    f"duas leituras do mesmo fato com o mesmo available_at ({chaves.instante_canonico(obs.available_at)})"
                )
        reg = VersaoRegistrada(obs, base, nat)
        self._versoes.append(reg)
        self._por_chave[base] = reg
        self._por_natural.setdefault(nat, []).append(reg)

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
        for c in self._conf_por_natural.get(nat, ()):
            if c.chave_idempotencia == base:  # R2-G4: a MESMA leitura já guardada como confirmação
                if c.leitura.conteudo != obs.conteudo:
                    raise ConflitoIdempotencia("mesma leitura (já confirmada) com conteúdo diferente")
                return ResultadoRegistro.NOOP
        for c in self._conf_por_natural.get(nat, ()):
            # já confirmado neste instante e conhecido no máximo agora (retry); reentrega que traz conhecimento
            # MAIS CEDO não é descartada: vira outra confirmação (a ordem de chegada não muda o estado)
            if (c.observed_at == obs.observed_at and c.available_at <= obs.available_at
                    and c.confirmada.observacao.estado_negocio == obs.estado_negocio):
                return ResultadoRegistro.NOOP
        versoes = self._por_natural.get(nat, [])
        confirmada = _redundante(obs, versoes)
        if confirmada is not None:
            c = Confirmacao(base, nat, obs.observed_at, obs.available_at, obs.run_id, obs.lote_id, confirmada, obs)
            k = (nat, obs.observed_at, obs.available_at)  # espelho da PK no banco
            if k in self._confirmacoes:
                raise VersaoAmbigua("duas confirmações do mesmo fato no mesmo (observed_at, available_at)")
            self._confirmacoes[k] = c
            self._conf_por_natural.setdefault(nat, []).append(c)
            return ResultadoRegistro.CONFIRMADO
        self._inserir(obs, base, nat)
        self._reparar(obs, nat)
        return ResultadoRegistro.INSERIDO

    def _reparar(self, x: Observacao, nat: str) -> None:
        """Materializa confirmações que, depois da versão `x`, voltariam a vencer com outro estado (regra 4)."""
        confs = [c for c in self._conf_por_natural.get(nat, ()) if c.chave_idempotencia not in self._por_chave]
        if not confs:
            return
        instantes = sorted({x.available_at} | {c.available_at for c in confs if c.available_at > x.available_at}
                           | {v.observacao.available_at for v in self._por_natural[nat]
                              if v.observacao.available_at > x.available_at})
        for t in instantes:
            versoes = [v.observacao for v in self._por_natural[nat] if v.observacao.available_at <= t]
            pendentes = [c for c in confs if c.available_at <= t and c.chave_idempotencia not in self._por_chave]
            if not versoes or not pendentes:
                continue
            g = max(versoes, key=ordem_versao)
            c = max(pendentes, key=lambda c: (c.observed_at, c.available_at))
            if (c.observed_at, c.available_at) > ordem_versao(g) and c.leitura.estado_negocio != g.estado_negocio:
                self._inserir(c.leitura, c.chave_idempotencia, nat)

    def registrar_todas(self, observacoes: Iterable[Observacao]) -> list[ResultadoRegistro]:
        return [self.registrar(o) for o in observacoes]

    def historico(self, chave_natural: str) -> tuple[VersaoRegistrada, ...]:
        """Todas as versões do fato, em ordem de chegada ao conhecimento (`available_at`). Nada some."""
        return tuple(sorted(self._por_natural.get(chave_natural, ()), key=lambda v: v.observacao.available_at))

    def as_of(self, t: datetime):
        from .asof import as_of

        return as_of(self.observacoes, t)
