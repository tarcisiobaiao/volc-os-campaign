"""A primitiva de leitura compartilhada, sozinha: sem Google, sem DataForSEO.

O que ela promete a quem a usa — e que as provas das engines assumem:

  * uma leitura por chave enquanto houver uma em voo;
  * a desistência de um consumidor não cancela a leitura dos outros;
  * só o valor aceitável é guardado, por TTL, com teto de entradas;
  * uma tarefa de outro laço de eventos nunca é aguardada daqui;
  * a chave é canônica e recusa o que não serializa de forma estável.
"""
from __future__ import annotations

import asyncio

import pytest

from app.services import leitura_compartilhada as lc


def _cache(**k):
    agora = [0.0]
    c = lc.LeituraCompartilhada("teste", max_entradas=k.pop("max_entradas", 8),
                                relogio=lambda: agora[0])
    return c, agora


def _sempre(_valor):
    return True


async def test_o_teto_de_entradas_descarta_a_mais_antiga():
    c, _ = _cache(max_entradas=2)
    lidos = []

    def leitor(v):
        async def _ler():
            lidos.append(v)
            return v
        return _ler

    for v in ("a", "b", "c"):
        await c.obter(v, leitor(v), ttl_s=60, aceitavel=_sempre)
    assert c.telemetria()["entradas"] == 2
    await c.obter("a", leitor("a"), ttl_s=60, aceitavel=_sempre)
    assert lidos == ["a", "b", "c", "a"], "a entrada mais antiga sobreviveu ao teto"
    valor, recibo = await c.obter("c", leitor("c"), ttl_s=60, aceitavel=_sempre)
    assert (valor, recibo.origem) == ("c", lc.HIT)


async def test_o_hit_informa_a_idade():
    c, agora = _cache()

    async def ler():
        return "v"

    await c.obter("k", ler, ttl_s=60, aceitavel=_sempre)
    agora[0] = 12.5
    _, recibo = await c.obter("k", ler, ttl_s=60, aceitavel=_sempre)
    assert recibo == lc.Recibo(lc.HIT, 12.5)


async def test_cancelar_um_consumidor_nao_cancela_a_leitura_compartilhada():
    c, _ = _cache()
    porta = asyncio.Event()
    lidos = []

    async def ler():
        lidos.append(1)
        await porta.wait()
        return "v"

    primeiro = asyncio.ensure_future(c.obter("k", ler, ttl_s=60, aceitavel=_sempre))
    await asyncio.sleep(0)
    segundo = asyncio.ensure_future(c.obter("k", ler, ttl_s=60, aceitavel=_sempre))
    await asyncio.sleep(0)
    primeiro.cancel()
    with pytest.raises(asyncio.CancelledError):
        await primeiro
    porta.set()
    valor, recibo = await segundo
    assert (valor, recibo.origem, lidos) == ("v", lc.COMPARTILHADA, [1])
    assert c.telemetria()["entradas"] == 1


async def test_ttl_zero_mantem_so_o_singleflight():
    c, _ = _cache()
    lidos = []

    async def ler():
        lidos.append(1)
        return "v"

    await c.obter("k", ler, ttl_s=0, aceitavel=_sempre)
    await c.obter("k", ler, ttl_s=0, aceitavel=_sempre)
    assert lidos == [1, 1]
    assert c.telemetria()["entradas"] == 0


def test_tarefa_de_outro_laco_vivo_nao_e_aguardada():
    """Um laço VIVO em outra thread tem uma leitura em voo para a mesma chave.

    Aguardar a tarefa dele daqui seria aguardar um futuro de outro laço — o
    asyncio recusa, e a rota viraria 500. A chamada daqui abre a própria.
    """
    import threading

    c, _ = _cache()
    iniciou, liberar = threading.Event(), threading.Event()
    lidos = []

    async def ler_no_outro_laco():
        lidos.append("outro")
        iniciou.set()
        await asyncio.to_thread(liberar.wait, 5)
        return "do-outro"

    outro = threading.Thread(target=lambda: asyncio.run(
        c.obter("k", ler_no_outro_laco, ttl_s=60, aceitavel=_sempre)))
    outro.start()
    try:
        assert iniciou.wait(5)
        assert c.telemetria()["em_voo"] == 1

        async def ler_aqui():
            lidos.append("aqui")
            return "daqui"

        valor, recibo = asyncio.run(
            c.obter("k", ler_aqui, ttl_s=60, aceitavel=_sempre))
    finally:
        liberar.set()
        outro.join(5)
    assert (valor, recibo.origem) == ("daqui", lc.MISS)
    assert lidos == ["outro", "aqui"]


def test_a_chave_e_canonica_e_recusa_o_que_nao_serializa():
    assert lc.chave_canonica("a", 1, None) == lc.chave_canonica("a", 1, None)
    assert lc.chave_canonica("a", 1) != lc.chave_canonica("a", "1")
    assert lc.chave_canonica({"y": 1, "x": 2}) == lc.chave_canonica({"x": 2, "y": 1})
    with pytest.raises(TypeError):
        lc.chave_canonica(object())


def test_limpar_todas_e_o_gancho_dos_testes():
    c, _ = _cache()

    async def ler():
        return "v"

    asyncio.run(c.obter("k", ler, ttl_s=60, aceitavel=_sempre))
    assert c.telemetria()["entradas"] == 1
    lc.limpar_todas()
    assert c.telemetria() == {"hit": 0, "miss": 0, "compartilhada": 0,
                              "fresca": 0, "guardada": 0, "descartada": 0,
                              "erro": 0, "entradas": 0, "em_voo": 0}
