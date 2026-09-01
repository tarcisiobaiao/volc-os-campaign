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
        """⚠️ DEFEITO CRITICO MEDIDO E FECHADO. Isto era
        `anyio.from_thread.run(...)`, que so funciona DENTRO de uma worker thread
        do anyio. Quem chama esta funcao e `execucao.disparar`, chamado por
        `criativos.py:386` de dentro de `async def criar_job` — ou seja, da
        THREAD DO EVENT LOOP. Reproduzido nesta rodada:

            NoEventLoopError: Not running inside an AnyIO worker thread

        A excecao subia sem tratamento, a rota devolvia 500, e o job — ja gravado
        como `queued` — nunca era executado por ninguem. Um pedido que a tela
        mostra na fila e que nao tem executor e pior que um erro: e um erro
        invisivel.

        `anyio.from_thread.run_sync`? Nao: o alvo e corrotina. `anyio.run`? Nao:
        de dentro de um loop ele levanta `Already running asyncio in this thread`
        — foi o segundo defeito, no fallback do fail-closed. A resposta e rodar
        a corrotina num loop PROPRIO, numa thread PROPRIA, e esperar por ela.
        Continua sincrono do ponto de vista de quem chama (o request espera),
        que e o contrato declarado desta implementacao — mas para de estourar.
        """
        _rodar_corrotina_em_thread(executor._executar_protegido, job_id)  # noqa: SLF001


def _rodar_corrotina_em_thread(corrotina: Any, *args: Any) -> None:
    """Roda uma corrotina ate o fim, funcione ou nao haja loop nesta thread.

    ⚠️ Existe porque `anyio.from_thread.run` e `anyio.run` falham nos DOIS lados
    da mesma moeda: o primeiro exige estar numa worker thread do anyio, o segundo
    exige NAO haver loop rodando. Chamado da thread do event loop, os dois
    estouram — e foi assim que dois defeitos criticos coexistiram nesta casa.

    Uma thread nova nunca tem loop, entao `anyio.run` ali sempre vale. A excecao
    do trabalho e re-levantada na thread chamadora: engoli-la faria a rota
    responder 201 sobre producao que falhou.
    """
    import threading  # noqa: PLC0415

    import anyio  # noqa: PLC0415

    caixa: dict[str, BaseException] = {}

    def alvo() -> None:
        try:
            anyio.run(corrotina, *args)
        except BaseException as e:  # noqa: BLE001 — devolvida a quem chamou
            caixa["erro"] = e

    t = threading.Thread(target=alvo, name="despacho-sincrono", daemon=False)
    t.start()
    t.join()
    if "erro" in caixa:
        raise caixa["erro"]


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


class DespachoDeFila:
    """Nao executa: deixa o trabalho na fila para o worker externo pegar.

    ⚠️ Este e o unico despachante que sobrevive a morte do processo web, e por
    isso o unico aceitavel em ambiente sem processo de vida longa. Ele nao e
    "nao fazer nada": o trabalho JA esta gravado e durável no deposito quando
    este despachante e chamado, e `python -m app.criativo.bancada.worker` o
    reivindica. A diferenca com o sincrono e onde o render acontece, nao se ele
    acontece.

    `sincrono = False` e o que a tela precisa saber: a resposta traz o id e o
    estado `queued`, e afirmar "pronto" ali seria mentira. Um 201 que diz
    `rendered` sem ter renderizado e o defeito que esta fronteira inteira existe
    para impedir.
    """

    nome = "fila"
    duravel = True
    sincrono = False

    def despachar_job_do_estudio(self, job_id: str, executor: Any) -> None:
        return None

    def despachar(self, trabalho_id: str) -> None:
        return None


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
    modo = modo_de_despacho()
    if modo == "fila":
        # A fila e durável em qualquer ambiente: o trabalho ja esta gravado e
        # quem o executa e um processo que nao e este.
        return DespachoDeFila()
    if amb in _SEM_PROCESSO_LONGO:
        raise DespachoIndisponivel(
            amb,
            "Este ambiente não tem processo de vida longa e ainda não há worker "
            "durável configurado. A produção seria congelada no meio.",
        )
    return DespachoSincronoLocal()


def modo_de_despacho() -> str:
    """`inline` ou `fila`. Ausência é `inline`, e a razão está declarada.

    ⚠️ O padrão é `inline` porque é o que a máquina de desenvolvimento consegue
    fazer sozinha: sem worker rodando, `fila` deixaria todo pedido em `queued`
    para sempre e pareceria travamento. Quem tem worker liga `fila`, e ai o
    request devolve o id sem esperar o render — que e o comportamento de
    produção.

    Não é fallback silencioso: `inline` continua sendo RECUSADO em ambiente sem
    processo de vida longa, pelo `escolher_despachante`.
    """
    escolha = (os.environ.get("CRIATIVO_DESPACHO") or "").strip().lower()
    return escolha if escolha in {"inline", "fila"} else "inline"
