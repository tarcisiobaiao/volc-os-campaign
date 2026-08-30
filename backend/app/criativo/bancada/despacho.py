"""Onde o trabalho roda — e a recusa honesta quando não há onde.

## Por que esta porta existe

A rodada anterior tirou `asyncio.create_task` do caminho de produção e chamou o
resultado de "fila durável". **Isso era falso**, e a revisão pegou: a bancada usa
SQLite no sistema de arquivos local, e na Vercel o disco de uma função não
sobrevive à requisição. Trocar `create_task` por render síncrono dentro do
request troca um defeito por outros — timeout da função, limite de memória,
cancelamento pelo cliente, retry que duplica produção, processo morto no meio.

`DESPACHO.md` tem a matriz por ambiente. Este módulo é a fronteira que a torna
executável: cada implementação declara o que ela **é**, e a seleção é
**fail-closed** — em produção, ausência de despachante durável **recusa a
criação**, em vez de cair em silêncio no SQLite ou no render longo.
"""

from __future__ import annotations

import os
from typing import Any, Protocol


class DespachoIndisponivel(RuntimeError):
    """Não há onde executar. Recusa explícita, não fallback silencioso."""

    def __init__(self, ambiente: str, motivo: str) -> None:
        super().__init__(motivo)
        self.ambiente = ambiente
        self.motivo = motivo


class DespachanteCriativo(Protocol):
    """A porta. Trocar a implementação não toca contrato, recibo nem motor."""

    #: Nome curto para log e para a tela dizer o que está acontecendo.
    nome: str
    #: `True` só quando o trabalho sobrevive à morte do processo que o criou.
    duravel: bool
    #: `True` quando o request espera o fim; `False` quando ele só recebe o id.
    sincrono: bool

    def despachar_job_do_estudio(self, job_id: str, executor: Any) -> None: ...


class DespachoSincronoLocal:
    """Executa no mesmo processo, esperando o fim.

    ⚠️ **NÃO é durável e não se apresenta como tal.** Serve a desenvolvimento e
    a teste, onde o processo vive enquanto o operador estiver olhando. Se o
    processo morrer no meio, o job fica em `running` no banco — visível e
    retomável, o que já é melhor que a task congelada de antes, mas ninguém o
    retoma sozinho sem um reaper rodando.
    """

    nome = "sincrono-local"
    duravel = False
    sincrono = True

    def despachar_job_do_estudio(self, job_id: str, executor: Any) -> None:
        import anyio  # noqa: PLC0415

        anyio.from_thread.run(executor._executar_protegido, job_id)  # noqa: SLF001


def ambiente_atual() -> str:
    """Onde este processo está rodando, segundo o próprio ambiente.

    `VERCEL` é definida pela plataforma; `CRIATIVO_AMBIENTE` permite declarar
    explicitamente em qualquer outro lugar.
    """
    declarado = (os.environ.get("CRIATIVO_AMBIENTE") or "").strip().lower()
    if declarado:
        return declarado
    if os.environ.get("VERCEL"):
        return "vercel"
    return "local"


#: Ambientes em que executar dentro do request é inaceitável.
#:
#: ⚠️ A lista é de ambientes SEM PROCESSO DE VIDA LONGA. Não é preferência: numa
#: função serverless, render longo dentro do request encontra o teto de tempo, e
#: um retry do cliente vira segunda produção paga.
_SEM_PROCESSO_LONGO = frozenset({"vercel", "lambda", "cloudflare"})


def escolher_despachante() -> DespachanteCriativo:
    """Fail-closed. Sem despachante durável em ambiente que exige um, RECUSA.

    Hoje só existe a implementação síncrona local. Em `vercel` isso significa que
    a criação de job é recusada com motivo — e é o comportamento certo: um 201
    sobre trabalho que a plataforma vai congelar é a mentira que esta fronteira
    existe para impedir.
    """
    amb = ambiente_atual()
    if amb in _SEM_PROCESSO_LONGO:
        raise DespachoIndisponivel(
            amb,
            "Este ambiente não tem processo de vida longa e ainda não há worker "
            "durável configurado. A produção seria congelada no meio.",
        )
    return DespachoSincronoLocal()
