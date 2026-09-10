"""Concorrência real em threads, sem provider pago ou banco externo."""

import asyncio
import threading
from collections import Counter

import pytest

from test_criativo_execucao import MotorFalso, PEDIDO, _executor


class MotorComBarreira(MotorFalso):
    def __init__(self, falhar_em=None):
        super().__init__(falhar_em)
        self.lock = threading.Lock()
        self.ativos = 0
        self.maximo = 0
        self.entrou_tres = threading.Event()
        self.portas = {slot: threading.Event() for slot in (*PEDIDO["slots"], "1.91x1")}

    def solicitar_geracao(self, pedido):
        slot = pedido.referencia.split("/")[-1]
        with self.lock:
            self.ativos += 1
            self.maximo = max(self.maximo, self.ativos)
            if self.ativos == 3:
                self.entrou_tres.set()
        try:
            assert self.portas[slot].wait(5), "executor não chegou a três chamadas simultâneas"
            return super().solicitar_geracao(pedido)
        finally:
            with self.lock:
                self.ativos -= 1

    def liberar(self):
        for porta in self.portas.values():
            porta.set()


async def esperar(condicao):
    async with asyncio.timeout(4):
        while not condicao():
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_tres_paralelas_snapshot_incremental_falha_isolada_retry_so_buraco(tmp_path):
    motor = MotorComBarreira({"4x5"})
    ex = _executor(tmp_path, motor)
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    jid = job["id"]
    tarefa = asyncio.create_task(ex._executar_protegido(jid))
    try:
        assert await asyncio.to_thread(motor.entrou_tres.wait, 3)
        assert motor.maximo == 3
        motor.portas["1x1"].set()
        await esperar(lambda: ex.repo.renditions[jid, "1x1"]["estado"] == "pronta")
        assert ex.repo.jobs[jid]["estado"] == "running"
        assert ex.repo.renditions[jid, "4x5"]["estado"] == "gerando"
        assert len(ex.repo.masters) == 1
        assert any(e["fase"] == "peca_pronta" for e in ex.repo.eventos)
    finally:
        motor.liberar()
        await tarefa
    assert ex.repo.jobs[jid]["estado"] == "partial"
    assert len(ex.repo.masters) == 2
    motor.falhar_em.clear()
    # Exercita o retry público, incluindo o despachante no loop de fundo.
    await ex.retentar(jid, criado_por="u1")
    assert ex.repo.jobs[jid]["estado"] == "succeeded"
    assert Counter(motor.chamadas) == {"1x1": 1, "4x5": 2, "9x16": 1}
    assert len(ex.repo.masters) == 3


@pytest.mark.asyncio
async def test_limite_global_entre_executores_e_loops_do_despacho(tmp_path):
    motor = MotorComBarreira()
    a = _executor(tmp_path / "a", motor)
    b = _executor(tmp_path / "b", motor)
    ja, _ = await a.criar_job_de_imagem(dict(PEDIDO), "u1")
    jb, _ = await b.criar_job_de_imagem(dict(PEDIDO), "u2")
    tarefas = [asyncio.create_task(a._executar_protegido(ja["id"])),
               asyncio.create_task(asyncio.to_thread(b.disparar, jb["id"]))]
    try:
        assert await asyncio.to_thread(motor.entrou_tres.wait, 3)
        await asyncio.sleep(0.1)
        assert motor.ativos == motor.maximo == 3
        estados = [r["estado"] for ex in (a, b) for r in ex.repo.renditions.values()]
        assert estados.count("gerando") == 3
        assert estados.count("pendente") == 3
    finally:
        motor.liberar()
        await asyncio.gather(*tarefas)
    assert motor.maximo == 3
    assert len(motor.chamadas) == 6
    assert a.repo.jobs[ja["id"]]["estado"] == b.repo.jobs[jb["id"]]["estado"] == "succeeded"


@pytest.mark.asyncio
async def test_cancelar_pula_a_fila_mas_preserva_tres_pecas_em_voo(tmp_path):
    motor = MotorComBarreira()
    ex = _executor(tmp_path, motor)
    job, _ = await ex.criar_job_de_imagem({**PEDIDO, "slots": [*PEDIDO["slots"], "1.91x1"]}, "u1")
    jid = job["id"]
    tarefa = asyncio.create_task(ex._executar_protegido(jid))
    try:
        assert await asyncio.to_thread(motor.entrou_tres.wait, 3)
        aguardando = next(r["slot"] for r in ex.repo.renditions.values() if r["estado"] == "pendente")
        await ex.cancelar(jid, criado_por="u1")
        assert not ex.repo.jobs[jid].get("cancelado_em")
    finally:
        motor.liberar()
        await tarefa
    assert ex.repo.renditions[jid, aguardando]["estado"] == "cancelada"
    assert aguardando not in motor.chamadas
    assert len(ex.repo.masters) == 3
    assert ex.repo.jobs[jid]["cancelado_em"]


@pytest.mark.asyncio
async def test_cancelar_await_nao_solta_vagas_nem_reexecuta_job_pago(tmp_path):
    motor = MotorComBarreira()
    ex = _executor(tmp_path, motor)
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    jid = job["id"]
    tarefa = asyncio.create_task(ex._executar_protegido(jid))
    try:
        assert await asyncio.to_thread(motor.entrou_tres.wait, 3)
        tarefa.cancel()
        await asyncio.sleep(0.05)
        assert jid in ex._em_voo
        await ex._executar_protegido(jid)
        assert motor.ativos == 3
        assert ex.repo.jobs[jid]["estado"] == "running"
    finally:
        motor.liberar()
        with pytest.raises(asyncio.CancelledError):
            await tarefa
    assert len(motor.chamadas) == len(ex.repo.masters) == 3
    assert jid not in ex._em_voo
    assert ex.repo.jobs[jid]["estado"] == "succeeded"
