"""Resolução efêmera de segredo — e o que este arquivo NÃO consegue prometer.

## O contrato

O broker recebe uma REFERÊNCIA (`op://…`) e precisa, por alguns milissegundos,
do valor para montar o header `Authorization: Bearer …` da Local API. Este
módulo é a única parte do broker que toca esse valor, e ele:

- resolve em PROCESSO FILHO, com timeout e grupo de processos próprio;
- guarda o resultado num `bytearray` que é zerado no descarte;
- devolve um objeto cujo `repr` e `str` são `<segredo:NOME>`, para que um
  `f"{segredo}"` distraído em log ou exceção não publique nada;
- exige `with segredo.usar() as valor:` para chegar ao texto, e recusa depois
  do descarte.

## O que ele NÃO promete — e isto precisa estar escrito

**CPython não permite apagar uma `str`.** Dentro de `usar()`, o valor existe
como `str` imutável; quando o bloco termina, aquele objeto vira lixo do
coletor, e o processo pode manter os bytes na heap até serem reutilizados. O
`bytearray` zerado cobre a cópia que ESTE módulo mantém, não a que o
interpretador criou. A defesa real continua sendo o processo curto, o escopo
estreito e o `descartar()` no `finally` — não uma promessa de erasure.

**Nem comprimento nem hash saem daqui.** Comprimento estreita o espaço de
busca; hash permite confirmar um palpite offline. É a mesma disciplina de
`tools/onepassword-smoke/run.py`, e ela vale igual aqui.

**`--no-masking` é proibida no preflight**, não aqui: recusar tarde seria
recusar depois de o processo já ter sido montado.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from contextlib import contextmanager
from typing import Iterator, Optional, Protocol, Sequence

from broker.configuracao import exigir_argumentos_do_resolvedor


class SegredoIndisponivel(RuntimeError):
    """Não deu para resolver. FECHADO: nunca vira string vazia nem `None`.

    Um broker que trata "cofre trancado" como "chave vazia" chama o AdsPower
    sem credencial e recebe uma recusa genérica — e o operador passa a
    investigar o AdsPower em vez do cofre.
    """


class SegredoJaDescartado(RuntimeError):
    pass


class SegredoEfemero:
    """O valor, com nome e com data de validade."""

    __slots__ = ("_buffer", "_nome", "_descartado")

    def __init__(self, valor: str, *, nome: str) -> None:
        if not valor:
            raise SegredoIndisponivel(
                f"o cofre devolveu vazio para {nome}. Vazio não é um segredo curto: "
                "é ausência, e ausência falha fechada.")
        self._buffer = bytearray(valor.encode("utf-8"))
        self._nome = nome
        self._descartado = False

    # `__str__`, `__repr__` e `__format__` cobrem os três jeitos de um valor
    # cair num log por distração: `print(s)`, `f"{s!r}"` e `f"{s}"`.
    def __str__(self) -> str:
        return f"<segredo:{self._nome}>"

    __repr__ = __str__

    def __format__(self, _spec: str) -> str:
        return str(self)

    @property
    def nome(self) -> str:
        return self._nome

    @property
    def descartado(self) -> bool:
        return self._descartado

    @contextmanager
    def usar(self) -> Iterator[str]:
        if self._descartado:
            raise SegredoJaDescartado(
                f"{self._nome} já foi descartado neste pedido. Resolver de novo é "
                "explícito, e é assim que a revogação do cofre continua valendo.")
        valor = self._buffer.decode("utf-8")
        try:
            yield valor
        finally:
            del valor

    def descartar(self) -> None:
        for i in range(len(self._buffer)):
            self._buffer[i] = 0
        self._buffer.clear()
        self._descartado = True


class ResolvedorDeSegredo(Protocol):
    """A porta. O broker nunca instancia um resolvedor concreto por conta."""

    def resolver(self, *, nome_logico: str, localizador: str) -> SegredoEfemero: ...


# ─────────────────────────────────────────────────────────────────────────────
# Execução isolada de processo filho
# ─────────────────────────────────────────────────────────────────────────────


class FilhoExpirou(RuntimeError):
    pass


def executar_isolado(
    argv: Sequence[str], *, timeout_s: float, ambiente: Optional[dict[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    """Roda o filho em SESSÃO PRÓPRIA e mata o GRUPO no timeout.

    ## Por que `start_new_session` e `killpg`, e não `proc.kill()`

    `op run -- <cmd>` cria pelo menos dois processos: o `op` e o comando
    injetado. `proc.kill()` mata só o primeiro; o neto continua vivo — e, no
    caso do `op run`, continua vivo COM O SEGREDO NO AMBIENTE. Um timeout que
    deixa descendente vivo transforma o limite de tempo num vazamento com
    prazo indeterminado.

    `start_new_session=True` põe o filho num grupo próprio; `os.killpg` alcança
    a árvore inteira. O `SIGKILL` depois do `SIGTERM` cobre o filho que ignora
    o primeiro sinal.
    """
    exigir_argumentos_do_resolvedor(argv)
    processo = subprocess.Popen(  # noqa: S603 - argv é lista, nunca shell
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env=ambiente,
        text=True,
        start_new_session=True,
    )
    try:
        saida, erro = processo.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _matar_grupo(processo)
        raise FilhoExpirou(
            f"o resolvedor de segredo passou de {timeout_s:g}s e o grupo de processos "
            "foi encerrado.") from None
    return subprocess.CompletedProcess(list(argv), processo.returncode, saida, erro)


def _matar_grupo(processo: "subprocess.Popen[str]") -> None:
    try:
        grupo = os.getpgid(processo.pid)
    except (ProcessLookupError, OSError):
        return
    for sinal, espera in ((signal.SIGTERM, 1.0), (signal.SIGKILL, 2.0)):
        try:
            os.killpg(grupo, sinal)
        except (ProcessLookupError, PermissionError, OSError):
            return
        fim = time.monotonic() + espera
        while time.monotonic() < fim:
            if processo.poll() is not None:
                try:
                    processo.communicate(timeout=0.1)
                except (subprocess.TimeoutExpired, ValueError):
                    pass
                return
            time.sleep(0.02)
    try:
        processo.communicate(timeout=0.1)
    except (subprocess.TimeoutExpired, ValueError):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Implementações
# ─────────────────────────────────────────────────────────────────────────────


class ResolvedorOpCli:
    """`op read <localizador>` num processo filho, com cache DESLIGADO.

    `--cache=false` não é zelo: medido em 01/09/2026 (ver
    `docs/closure/onepassword-cofre-operational-closure-v1/PROVA-REVOGACAO.md`),
    com o cache ligado o `op` respondia metadado DEPOIS de o cofre ter sido
    trancado. O cache não devolvia o segredo, mas era suficiente para uma prova
    de revogação medir a coisa errada. Aqui a revogação precisa valer no ato.

    ⚠️ Este caminho NÃO foi exercido nesta entrega: não há 1Password nesta
    máquina, e a missão proíbe usar segredo real. Ele existe escrito e testado
    apenas contra duplê. A execução contra o cofre real é checkpoint externo.
    """

    def __init__(self, *, binario: str = "op", timeout_s: float = 25.0,
                 ambiente: Optional[dict[str, str]] = None):
        self._binario = binario
        self._timeout = timeout_s
        self._ambiente = ambiente

    def resolver(self, *, nome_logico: str, localizador: str) -> SegredoEfemero:
        argv = [self._binario, "read", "--cache=false", "--no-newline", localizador]
        try:
            concluido = executar_isolado(argv, timeout_s=self._timeout, ambiente=self._ambiente)
        except FileNotFoundError:
            raise SegredoIndisponivel(
                "o binário `op` não está no PATH deste host. Sem cofre, o broker não "
                "inventa credencial.") from None
        except FilhoExpirou as exc:
            raise SegredoIndisponivel(str(exc)) from None
        if concluido.returncode != 0:
            # `stderr` do `op` pode conter nome de cofre e de item. Ele NÃO é
            # repassado: só a classe do erro.
            raise SegredoIndisponivel(
                f"o cofre recusou resolver {nome_logico} (código {concluido.returncode}). "
                "A mensagem do cofre não é repetida aqui de propósito.")
        return SegredoEfemero(concluido.stdout.strip(), nome=nome_logico)


class ResolvedorSentinela:
    """Duplê hermético: devolve uma SENTINELA sintética, nunca um segredo real.

    A sentinela é o instrumento central das provas de contenção: ela é longa,
    inconfundível e o repositório inteiro é varrido atrás dela. Se ela aparecer
    num recibo, num log, num JSON ou numa exceção, a contenção falhou — e é
    melhor descobrir isso com um valor sintético.
    """

    def __init__(self, *, valores: Optional[dict[str, str]] = None,
                 modo: str = "feliz") -> None:
        self._valores = dict(valores or {})
        self.modo = modo
        self.chamadas: list[str] = []

    def resolver(self, *, nome_logico: str, localizador: str) -> SegredoEfemero:
        self.chamadas.append(nome_logico)
        if self.modo == "cofre_trancado":
            raise SegredoIndisponivel(
                f"o cofre está trancado e não resolveu {nome_logico}. Nova aprovação "
                "é necessária.")
        if self.modo == "ausente":
            raise SegredoIndisponivel(
                f"não existe segredo registrado para {nome_logico}. Falha fechada.")
        if self.modo == "vazio":
            return SegredoEfemero("", nome=nome_logico)  # levanta SegredoIndisponivel
        try:
            return SegredoEfemero(self._valores[nome_logico], nome=nome_logico)
        except KeyError:
            raise SegredoIndisponivel(
                f"o duplê não conhece {nome_logico}.") from None


__all__ = [
    "FilhoExpirou", "ResolvedorDeSegredo", "ResolvedorOpCli", "ResolvedorSentinela",
    "SegredoEfemero", "SegredoIndisponivel", "SegredoJaDescartado", "executar_isolado",
]
