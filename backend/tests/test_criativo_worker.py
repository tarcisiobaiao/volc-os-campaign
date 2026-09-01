"""O worker como PROCESSO: reivindica, renova, mede, assina e pode ser morto.

O aceite do P17-T05 diz: "Worker isolado reivindica jobs, renova lease, mede
artefato no disco/storage, registra custo e recibo e pode ser interrompido sem
perder ou duplicar trabalho."

"Isolado" e a palavra que estas provas levam a serio. Um teste que chama
`rodar()` no mesmo interpretador prova o LACO, nao o isolamento — e o defeito
que esta tarefa fecha e exatamente producao acontecendo dentro do processo web.
Por isso as provas centrais sobem um processo de verdade, com `subprocess`, e
afirmam sobre o disco e o banco que sobraram depois que ele morreu.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from app.criativo.bancada.contrato import Encomenda, EstadoDoTrabalho, SaidaPedida
from app.criativo.bancada.deposito import DepositoDeTrabalhos

RAIZ = Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "backend"


def encomenda(*, seed: int = 1, titulo: str = "peca") -> Encomenda:
    return Encomenda(
        receita_id="receita-worker",
        tenant_id="tenant-worker",
        motor_slug="png-local",
        modo_slug="typography_only",
        finalidade_slug="google_display",
        seed=seed,
        saidas=(SaidaPedida("1x1", 64, 64, "imagem", "image/png"),),
        # `insumo` e o parametro que `MotorPngLocal` exige: sem ele o pixel seria
        # o mesmo para qualquer briefing, e o motor recusa — corretamente.
        parametros={"insumo": titulo, "titulo": titulo, "apoio": ""},
    )


def _ambiente(raiz: Path) -> dict[str, str]:
    """Ambiente de um worker: sem `.env`, com a bancada dentro do tmp do teste."""
    return {
        **os.environ,
        "PYTHONPATH": f"{RAIZ}{os.pathsep}{BACKEND}{os.pathsep}{raiz}",
        "CRIATIVO_BANCADA_DIR": str(raiz),
        "CRIATIVO_STORAGE_DIR": str(raiz / "storage"),
        "CRIATIVO_URL_SECRET": "segredo-de-teste-com-tamanho-suficiente",
        "CRIATIVO_WORKER_LOG": "WARNING",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _subir_worker(raiz: Path, *args: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "app.criativo.bancada.worker", *args],
        cwd=str(RAIZ), env=_ambiente(raiz),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,
    )


def _esperar(condicao, prazo_s: float = 20.0, passo: float = 0.05) -> bool:
    limite = time.monotonic() + prazo_s
    while time.monotonic() < limite:
        if condicao():
            return True
        time.sleep(passo)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 1. o worker e um processo, e ele produz
# ─────────────────────────────────────────────────────────────────────────────


def test_o_worker_e_outro_processo_e_conclui_o_trabalho(tmp_path: Path) -> None:
    """A prova central do P17-T05: NENHUM processo web participa.

    O teste enfileira, sai de cena, e um `python -m ...` separado produz. O que
    sobra no depósito depois que esse processo morreu é toda a evidência.
    """
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    trabalho, criado = deposito.enfileirar(encomenda())
    assert criado is True
    assert deposito.por_id(trabalho.id).estado is EstadoDoTrabalho.QUEUED

    p = _subir_worker(tmp_path, "--uma-vez", "--nome", "worker-de-prova")
    saida, erro = p.communicate(timeout=90)
    assert p.returncode == 0, f"o worker morreu: {erro[-2000:]}"

    final = deposito.por_id(trabalho.id)
    assert final.estado is EstadoDoTrabalho.RENDERED, (
        f"o worker externo não concluiu: {final.estado.value} · {final.falha} · {erro[-800:]}"
    )
    # Recibo com artefato REAL: bytes e sha256 conferidos contra o disco pelo
    # operário, não declarados pelo motor.
    assert final.recibo is not None
    (artefato,) = final.recibo["artefatos"]
    caminho = Path(artefato["caminho"])
    assert caminho.is_file(), "o recibo aponta para arquivo que não existe"
    assert caminho.stat().st_size == artefato["bytes_"]
    import hashlib

    assert hashlib.sha256(caminho.read_bytes()).hexdigest() == artefato["sha256"]
    # E o artefato ficou DENTRO da raiz do worker, não espalhado pelo disco.
    assert caminho.resolve().is_relative_to(tmp_path.resolve())
    # Quem produziu fica registrado; o lease, não — ele some no terminal.
    assert final.recibo["produzido_por"] == "worker-de-prova"
    assert final.operario is None and final.lease_ate is None
    assert final.terminado_em is not None


def test_o_worker_registra_custo_como_nao_apurado_e_nao_como_zero(tmp_path: Path) -> None:
    """Motor local gratuito não é motor de custo zero: é motor não apurado.

    ⚠️ A diferença tem consequência: quando entrar um motor pago, um campo que
    já nasce `0.0` some no meio dos gratuitos, e ninguém percebe que a apuração
    nunca foi ligada. `None` aparece.
    """
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    trabalho, _ = deposito.enfileirar(encomenda(seed=77))
    p = _subir_worker(tmp_path, "--uma-vez")
    _, erro = p.communicate(timeout=90)
    assert p.returncode == 0, erro[-2000:]

    recibo = deposito.por_id(trabalho.id).recibo
    assert recibo["custo_real_usd"] is None, "custo zero é uma afirmação; ninguém apurou"
    assert recibo["custo_estimado_usd"] is None
    assert "assinatura_determinista" in recibo


# ─────────────────────────────────────────────────────────────────────────────
# 2. dois workers nao duplicam
# ─────────────────────────────────────────────────────────────────────────────


def test_dois_workers_na_mesma_fila_nao_produzem_a_mesma_peca_duas_vezes(
    tmp_path: Path,
) -> None:
    """"Sem duplicar" é sobre dinheiro: dois renders do mesmo pedido são dois
    gastos. Quem arbitra é o depósito, não a boa vontade dos workers."""
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    ids = [deposito.enfileirar(encomenda(seed=n))[0].id for n in range(6)]

    ps = [_subir_worker(tmp_path, "--ate-esvaziar", "--nome", f"w{n}") for n in range(3)]
    for p in ps:
        _, erro = p.communicate(timeout=120)
        assert p.returncode == 0, erro[-1500:]

    donos: dict[str, str] = {}
    for i in ids:
        t = deposito.por_id(i)
        assert t.estado is EstadoDoTrabalho.RENDERED, f"{i} ficou {t.estado.value}"
        donos[i] = t.recibo["produzido_por"]
        # Uma tentativa por trabalho: ninguém refez o que já estava feito.
        assert t.tentativa == 1, f"{i} foi tentado {t.tentativa} vezes"
    assert len(donos) == len(ids)
    # E a trilha não tem dois claims para o mesmo trabalho.
    for i in ids:
        claims = [p for p in deposito.trilha(i) if p["para"] == "claimed"]
        assert len(claims) == 1, f"{i} foi reivindicado {len(claims)} vezes: {claims}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. interromper sem perder
# ─────────────────────────────────────────────────────────────────────────────


def _motor_lento(raiz: Path, segundos: float) -> Path:
    """Um motor de teste em arquivo, para o processo do worker poder importá-lo."""
    modulo = raiz / "motor_lento_de_prova.py"
    modulo.write_text(textwrap.dedent(f"""
        import hashlib, time
        from pathlib import Path
        from app.criativo.bancada.contrato import Artefato

        class MotorLentoDeProva:
            slug, versao = "png-local", "lento-de-prova"
            def versoes_congeladas(self): return {{"motor": "lento-de-prova"}}
            def produzir(self, encomenda, dir_trabalho):
                d = Path(dir_trabalho)
                (d / "COMECOU").write_text("sim")
                time.sleep({segundos})
                dados = b"\\x89PNG\\r\\n\\x1a\\n" + b"w" * 64
                p = d / "1x1.png"
                p.write_bytes(dados)
                return (Artefato("1x1", str(p), "image/png", len(dados),
                                 hashlib.sha256(dados).hexdigest(), 64, 64),)
    """), encoding="utf-8")
    return modulo


def test_sigterm_deixa_o_trabalho_atual_terminar(tmp_path: Path) -> None:
    """"Sem perder" tem mecanismo: o sinal levanta bandeira, não mata o render.

    ⚠️ Se o handler chamasse `sys.exit`, o processo morreria NO MEIO da produção
    — que é exatamente o "perder trabalho" que o aceite proíbe.
    """
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    _motor_lento(tmp_path, 3.0)
    trabalho, _ = deposito.enfileirar(encomenda(seed=5))

    env = _ambiente(tmp_path)
    p = subprocess.Popen(
        [sys.executable, "-m", "app.criativo.bancada.worker", "--lease", "30",
         "--motor", "motor_lento_de_prova:MotorLentoDeProva"],
        cwd=str(RAIZ), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        assert _esperar(
            lambda: deposito.por_id(trabalho.id).estado
            in {EstadoDoTrabalho.CLAIMED, EstadoDoTrabalho.RUNNING},
            prazo_s=30,
        ), "o worker nem reivindicou"
        # O sinal chega COM o render em voo.
        p.send_signal(signal.SIGTERM)
        saida, erro = p.communicate(timeout=90)
        assert p.returncode == 0, f"o worker não saiu limpo: {erro[-1500:]}"
    finally:
        if p.poll() is None:
            p.kill()

    final = deposito.por_id(trabalho.id)
    assert final.estado is EstadoDoTrabalho.RENDERED, (
        f"o SIGTERM abandonou o trabalho em {final.estado.value} — isso é perder"
    )


def test_morte_dura_no_meio_devolve_o_trabalho_sem_marcar_falha(tmp_path: Path) -> None:
    """Um operário que morreu não torna o pedido inválido.

    SIGKILL não deixa o worker fazer nada: nem transicionar, nem limpar. O que
    devolve o trabalho é o VENCIMENTO DO LEASE, decisão do depósito. E ele volta
    para a fila, não para `failed` — e um segundo worker o refaz sem duplicar
    recibo, porque o primeiro nunca chegou a gravar um.
    """
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    _motor_lento(tmp_path, 30.0)
    trabalho, _ = deposito.enfileirar(encomenda(seed=9))

    env = _ambiente(tmp_path)
    p = subprocess.Popen(
        [sys.executable, "-m", "app.criativo.bancada.worker", "--lease", "2",
         "--motor", "motor_lento_de_prova:MotorLentoDeProva"],
        cwd=str(RAIZ), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    assert _esperar(
        lambda: deposito.por_id(trabalho.id).estado is EstadoDoTrabalho.RUNNING,
        prazo_s=30,
    ), "o worker nem começou a produzir"
    os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    p.wait(timeout=30)

    preso = deposito.por_id(trabalho.id)
    assert preso.estado is EstadoDoTrabalho.RUNNING
    assert preso.recibo is None

    # Ninguém marcou falha. O lease vence e o trabalho volta.
    assert _esperar(lambda: deposito.devolver_vencidos() > 0, prazo_s=20)
    devolvido = deposito.por_id(trabalho.id)
    assert devolvido.estado is EstadoDoTrabalho.QUEUED, "morte virou falha"
    assert devolvido.falha is None
    assert devolvido.operario is None
    # A trilha guarda a história: alguém pegou, morreu, e o lease venceu.
    motivos = [p["motivo"] for p in deposito.trilha(trabalho.id)]
    assert "lease_vencido" in motivos, f"a devolução não ficou registrada: {motivos}"

    # E um worker novo refaz — uma vez só, com o motor normal.
    (tmp_path / "motor_lento_de_prova.py").unlink()
    p2 = _subir_worker(tmp_path, "--uma-vez")
    _, erro = p2.communicate(timeout=90)
    assert p2.returncode == 0, erro[-1500:]
    refeito = deposito.por_id(trabalho.id)
    assert refeito.estado is EstadoDoTrabalho.RENDERED
    assert refeito.tentativa == 2, "a segunda tentativa não foi contada"
    assert refeito.recibo is not None


# ─────────────────────────────────────────────────────────────────────────────
# 4. o recolhedor roda no worker, nao no processo web
# ─────────────────────────────────────────────────────────────────────────────


def test_o_worker_roda_o_recolhedor_sozinho(tmp_path: Path) -> None:
    """`iniciar_reaper` tinha ZERO chamadores em todo o repositório.

    A promessa "o trabalho volta para a fila" era verdadeira no depósito e falsa
    na operação: um trabalho abandonado só voltava se, por acaso, outro pedido
    chegasse. Aqui ninguém manda outro pedido — o worker recolhe sozinho.
    """
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    trabalho, _ = deposito.enfileirar(encomenda(seed=13))
    # Um "operário morto": reivindicou com lease que já nasceu vencido.
    abandonado = deposito.reivindicar("op-fantasma", lease_s=-1)
    assert abandonado.id == trabalho.id

    p = _subir_worker(tmp_path, "--ate-esvaziar", "--lease", "3", "--nome", "recolhedor-de-prova")
    _, erro = p.communicate(timeout=90)
    assert p.returncode == 0, erro[-1500:]

    final = deposito.por_id(trabalho.id)
    assert final.estado is EstadoDoTrabalho.RENDERED, (
        f"o abandonado nunca voltou para a fila: {final.estado.value}"
    )
    assert final.recibo["produzido_por"] == "recolhedor-de-prova"


# ─────────────────────────────────────────────────────────────────────────────
# 5. a fronteira do processo web
# ─────────────────────────────────────────────────────────────────────────────


def test_o_modo_fila_nao_executa_no_processo_que_recebe_o_pedido(monkeypatch) -> None:
    from app.criativo.bancada.despacho import DespachoDeFila, escolher_despachante

    monkeypatch.setenv("CRIATIVO_DESPACHO", "fila")
    monkeypatch.setenv("CRIATIVO_AMBIENTE", "vercel")
    escolhido = escolher_despachante()
    assert isinstance(escolhido, DespachoDeFila)
    assert escolhido.duravel is True
    assert escolhido.sincrono is False, (
        "um despachante que o request espera não é fila"
    )


def test_o_modo_inline_e_recusado_em_ambiente_sem_processo_longo(monkeypatch) -> None:
    """Fail-closed: 503, não 201 sobre produção que a plataforma vai congelar."""
    from app.criativo.bancada.despacho import DespachoIndisponivel, escolher_despachante

    monkeypatch.setenv("CRIATIVO_DESPACHO", "inline")
    for ambiente in ("vercel", "lambda", "cloudflare"):
        monkeypatch.setenv("CRIATIVO_AMBIENTE", ambiente)
        with pytest.raises(DespachoIndisponivel):
            escolher_despachante()


def test_despachar_de_dentro_do_event_loop_nao_estoura() -> None:
    """Contraprova dos dois defeitos críticos, pela função real.

    Antes: `anyio.from_thread.run` levantava `NoEventLoopError` e o fallback
    `anyio.run` levantava `Already running asyncio in this thread`. Os dois eram
    chamados da thread do event loop, que é de onde a rota `async def` chama.
    """
    import asyncio

    from app.criativo.bancada.despacho import (
        DespachoSincronoLocal,
        _rodar_corrotina_em_thread,
    )

    class ExecutorFalso:
        def __init__(self) -> None:
            self.vistos: list[str] = []

        async def _executar_protegido(self, job_id: str) -> None:
            self.vistos.append(job_id)

    async def dentro_do_loop() -> ExecutorFalso:
        ex = ExecutorFalso()
        DespachoSincronoLocal().despachar_job_do_estudio("job-1", ex)
        return ex

    assert asyncio.run(dentro_do_loop()).vistos == ["job-1"]

    async def a_excecao_sobe() -> str:
        async def explode() -> None:
            raise ValueError("o motor recusou")

        try:
            _rodar_corrotina_em_thread(explode)
        except ValueError as e:
            return str(e)
        return "engoliu"

    assert asyncio.run(a_excecao_sobe()) == "o motor recusou", (
        "a exceção engolida faria a rota responder 201 sobre produção que falhou"
    )


def test_dois_despachos_concorrentes_nao_penduram_no_lock_do_executor() -> None:
    """Um loop POR CHAMADA consertava os dois estouros e criava um terceiro.

    ⚠️ `Executor.__init__` cria `self._trava = asyncio.Lock()`, e o executor é
    reusado entre requisições. Desde o 3.10 o `Lock` não se liga a loop nenhum na
    construção: ele se liga na PRIMEIRA DISPUTA, e a aquisição sem disputa passa
    por um atalho que nem consulta o loop. Por isso a medição com um uso de cada
    vez dava tudo verde. Com dois despachos concorrentes, cada um no seu loop, o
    segundo esperava num future que pertence ao loop do primeiro — e ninguém o
    acordava. Medido: o processo de prova ficou vivo depois de imprimir o
    resultado e precisou de `pkill`, porque a thread era `daemon=False`.

    Esta prova exige as duas coisas: que a ordem seja respeitada (A pega, A
    solta, B pega) e que nenhuma thread NÃO-daemon fique para trás.
    """
    import asyncio
    import threading

    from app.criativo.bancada.despacho import _rodar_corrotina_em_thread

    trava = asyncio.Lock()
    ordem: list[str] = []
    erros: list[str] = []
    segurando = threading.Event()

    async def segurar() -> None:
        async with trava:
            ordem.append("A pegou")
            segurando.set()
            await asyncio.sleep(0.4)
            ordem.append("A soltou")

    async def tentar() -> None:
        async with trava:
            ordem.append("B pegou")

    def alvo(fn) -> None:
        try:
            _rodar_corrotina_em_thread(fn)
        except BaseException as e:  # noqa: BLE001
            erros.append(f"{type(e).__name__}: {e}")

    a = threading.Thread(target=alvo, args=(segurar,))
    a.start()
    assert segurando.wait(5), "o primeiro despacho nem pegou a trava"
    b = threading.Thread(target=alvo, args=(tentar,))
    b.start()
    a.join(20)
    b.join(20)

    assert not erros, f"o despacho concorrente estourou: {erros}"
    assert ordem == ["A pegou", "A soltou", "B pegou"], (
        f"a trava não foi respeitada entre loops: {ordem}"
    )
    assert not a.is_alive() and not b.is_alive(), "um despacho ficou pendurado"
    nao_daemon = [
        t.name for t in threading.enumerate()
        if t.is_alive() and not t.daemon and t is not threading.current_thread()
        and t.name.startswith("despacho")
    ]
    assert not nao_daemon, (
        f"thread não-daemon de despacho impediria o processo de sair: {nao_daemon}"
    )
