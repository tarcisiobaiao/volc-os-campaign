"""O worker só dispara um motor que IMPORTA — e dá a ele o caminho do código.

## O defeito que isto fecha (pista P2, reproduzida em 30/09/2026)

O venv do motor tem as entradas de `site-packages` marcadas com a flag `hidden`
do macOS, e o `site.py` do CPython 3.14 pula `.pth` oculto. O `.pth` do
`pip install -e` é justamente o que põe `engine/src` no caminho. Resultado:

    engine/.venv/bin/python -c 'import funnelforge'
    ModuleNotFoundError: No module named 'funnelforge'

Todo disparo pelo backend morria assim, com o card mostrando só "failed" e o
fim da saída do processo. Duas defesas, as duas provadas aqui:

1. o processo do motor recebe `PYTHONPATH=<motor>/src` (defesa em profundidade:
   não depende do `.pth`);
2. `_executavel()` prova a importação UMA vez, com o mesmo ambiente do disparo,
   e recusa com `MotorIndisponivel` contendo a CAUSA — antes de qualquer gasto.

Tudo com subprocesso FALSO: nenhum destes testes roda o motor de verdade.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from app.redator import worker


# ── dublês ─────────────────────────────────────────────────────────────────

class _SupaFalso:
    def __init__(self) -> None:
        self.patches: list[dict] = []

    async def patch(self, tabela, match, valores):
        self.patches.append({"tabela": tabela, "match": match, **valores})
        return []

    async def select(self, tabela, params):
        return []

    @property
    def status_gravados(self) -> list[str]:
        return [p["status"] for p in self.patches if "status" in p]


class _ProvaFalsa:
    """Substitui `subprocess.run` da prova de importação e registra a chamada."""

    def __init__(self, codigo: int = 0, stderr: str = "") -> None:
        self.codigo = codigo
        self.stderr = stderr
        self.chamadas: list[dict] = []

    def __call__(self, cmd, **kwargs):
        self.chamadas.append({"cmd": list(cmd), **kwargs})
        return subprocess.CompletedProcess(cmd, self.codigo, stdout="", stderr=self.stderr)


class _ProcessoFalso:
    """O que `asyncio.create_subprocess_exec` devolveria: sai 0 sem escrever nada."""

    pid = 424242

    def __init__(self) -> None:
        self.returncode = 0

    async def communicate(self):
        return b"", None

    def kill(self):  # pragma: no cover — só existe para o contrato
        pass


ERRO_REAL = (
    "Traceback (most recent call last):\n"
    '  File "<string>", line 1, in <module>\n'
    "    import funnelforge\n"
    "ModuleNotFoundError: No module named 'funnelforge'\n"
)

PERFIL = {
    "site": {"domain": "https://exemplo.com.br", "post_type": "rec", "lp_post_type": "r"},
    "wordpress": {"url": "https://exemplo.com.br", "user": "u", "app_token": "SENHA-XYZ"},
    "tema": {"termos": ["a"], "official_preference": []},
}
ARQ = {"pages": [{"role": "landing", "position": 1}]}


@pytest.fixture
def motor_falso(tmp_path: Path, monkeypatch) -> Path:
    """Uma raiz de motor com os arquivos que `_executavel` confere."""
    raiz = tmp_path / "engine"
    (raiz / ".venv" / "bin").mkdir(parents=True)
    (raiz / "src" / "funnelforge").mkdir(parents=True)
    for nome in ("funnelforge", "python"):
        exe = raiz / ".venv" / "bin" / nome
        exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        exe.chmod(0o755)
    (raiz / "config.yaml").write_text("run:\n  publish_status: draft\n", encoding="utf-8")
    monkeypatch.setattr(worker, "raiz_do_motor", lambda: raiz)
    # A prova vale "uma vez" por processo: cada teste começa sem memória.
    worker._IMPORTACAO_PROVADA.clear()
    yield raiz
    worker._IMPORTACAO_PROVADA.clear()


# ── o ambiente do processo do motor ────────────────────────────────────────

def test_env_do_motor_poe_o_src_do_motor_na_frente(motor_falso: Path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/algum/caminho/do/backend")
    env = worker._env_do_motor(motor_falso)

    partes = env["PYTHONPATH"].split(os.pathsep)
    assert partes[0] == str(motor_falso / "src")
    # o que já existia continua, atrás: não é trocar um defeito por outro
    assert "/algum/caminho/do/backend" in partes
    assert env["PYTHONUNBUFFERED"] == "1"


def test_env_do_motor_sem_pythonpath_previo(motor_falso: Path, monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    env = worker._env_do_motor(motor_falso)
    assert env["PYTHONPATH"] == str(motor_falso / "src")


# ── a prova de importação ──────────────────────────────────────────────────

def test_motor_que_nao_importa_e_recusado_com_a_causa(motor_falso: Path, monkeypatch):
    prova = _ProvaFalsa(codigo=1, stderr=ERRO_REAL)
    monkeypatch.setattr(worker.subprocess, "run", prova)

    with pytest.raises(worker.MotorIndisponivel) as exc:
        worker._executavel()

    msg = str(exc.value)
    # a CAUSA, não "falhou"
    assert "No module named 'funnelforge'" in msg
    assert "import funnelforge" in msg
    # e o que fazer — sem o worker tentar consertar sozinho
    assert "chflags" in msg or "venv" in msg


def test_a_prova_roda_com_o_mesmo_ambiente_do_disparo(motor_falso: Path, monkeypatch):
    prova = _ProvaFalsa(codigo=0)
    monkeypatch.setattr(worker.subprocess, "run", prova)

    exe = worker._executavel()

    assert exe == motor_falso / ".venv" / "bin" / "funnelforge"
    assert len(prova.chamadas) == 1
    chamada = prova.chamadas[0]
    assert chamada["cmd"] == [str(motor_falso / ".venv" / "bin" / "python"),
                              "-c", "import funnelforge"]
    assert chamada["cwd"] == str(motor_falso)
    assert chamada["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(motor_falso / "src")
    # prova com teto de tempo: um interpretador pendurado não trava o disparo
    assert chamada.get("timeout")


def test_a_prova_acontece_uma_vez_so(motor_falso: Path, monkeypatch):
    prova = _ProvaFalsa(codigo=0)
    monkeypatch.setattr(worker.subprocess, "run", prova)

    worker._executavel()
    worker._executavel()
    worker._executavel()

    assert len(prova.chamadas) == 1


def test_falha_nao_fica_em_cache(motor_falso: Path, monkeypatch):
    """Consertado o venv, o próximo disparo tem de passar sem reiniciar a API."""
    monkeypatch.setattr(worker.subprocess, "run", _ProvaFalsa(codigo=1, stderr=ERRO_REAL))
    with pytest.raises(worker.MotorIndisponivel):
        worker._executavel()

    ok = _ProvaFalsa(codigo=0)
    monkeypatch.setattr(worker.subprocess, "run", ok)
    assert worker._executavel() == motor_falso / ".venv" / "bin" / "funnelforge"
    assert len(ok.chamadas) == 1


def test_interpretador_pendurado_vira_motor_indisponivel(motor_falso: Path, monkeypatch):
    def pendura(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 1)

    monkeypatch.setattr(worker.subprocess, "run", pendura)
    with pytest.raises(worker.MotorIndisponivel) as exc:
        worker._executavel()
    assert "import funnelforge" in str(exc.value)


# ── o disparo ──────────────────────────────────────────────────────────────

def test_disparo_com_motor_nao_importavel_falha_antes_de_gastar(motor_falso: Path, monkeypatch):
    """A linha vira `failed` com a causa, e o processo do motor NUNCA sobe."""
    monkeypatch.setattr(worker.subprocess, "run", _ProvaFalsa(codigo=1, stderr=ERRO_REAL))

    async def nao_pode_subir(*a, **k):
        raise AssertionError("o motor não podia ter sido disparado")

    monkeypatch.setattr(worker.asyncio, "create_subprocess_exec", nao_pode_subir)
    supa = _SupaFalso()

    asyncio.run(worker.executar(supa=supa, run_row_id=31, arquitetura=ARQ, perfil=PERFIL))

    assert supa.status_gravados == ["failed"]          # nunca passou por "running"
    erro = [p for p in supa.patches if p.get("erro")][-1]["erro"]
    assert "No module named 'funnelforge'" in erro


def test_o_processo_do_motor_recebe_o_pythonpath_do_motor(motor_falso: Path, monkeypatch):
    monkeypatch.setattr(worker.subprocess, "run", _ProvaFalsa(codigo=0))
    monkeypatch.setenv("PYTHONPATH", "/caminho/do/backend")
    visto: dict = {}

    async def sobe(*cmd, **kwargs):
        visto["cmd"] = cmd
        visto.update(kwargs)
        return _ProcessoFalso()

    monkeypatch.setattr(worker.asyncio, "create_subprocess_exec", sobe)
    supa = _SupaFalso()

    asyncio.run(worker.executar(supa=supa, run_row_id=32, arquitetura=ARQ, perfil=PERFIL))

    assert visto, "o motor nem foi disparado"
    assert visto["cwd"] == str(motor_falso)
    partes = visto["env"]["PYTHONPATH"].split(os.pathsep)
    assert partes[0] == str(motor_falso / "src")
    assert "/caminho/do/backend" in partes
    assert visto["env"]["PYTHONUNBUFFERED"] == "1"
    assert supa.status_gravados[-1] == "done"


def test_publicar_pagina_tambem_leva_o_pythonpath(motor_falso: Path, monkeypatch):
    monkeypatch.setattr(worker.subprocess, "run", _ProvaFalsa(codigo=0))
    visto: dict = {}

    async def sobe(*cmd, **kwargs):
        visto.update(kwargs)
        return _ProcessoFalso()

    monkeypatch.setattr(worker.asyncio, "create_subprocess_exec", sobe)

    r = asyncio.run(worker.publicar_pagina(
        supa=_SupaFalso(), run_row_id=33, run_id="funil-20260930-101010",
        page_number=2, perfil=PERFIL))

    assert visto["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(motor_falso / "src")
    # sem state.json no disco, o desfecho é honesto: não publicou
    assert r["ok"] is False


def test_publicar_pagina_recusa_motor_que_nao_importa(motor_falso: Path, monkeypatch):
    monkeypatch.setattr(worker.subprocess, "run", _ProvaFalsa(codigo=1, stderr=ERRO_REAL))

    async def nao_pode_subir(*a, **k):
        raise AssertionError("o motor não podia ter sido disparado")

    monkeypatch.setattr(worker.asyncio, "create_subprocess_exec", nao_pode_subir)

    r = asyncio.run(worker.publicar_pagina(
        supa=_SupaFalso(), run_row_id=34, run_id="funil-20260930-101010",
        page_number=2, perfil=PERFIL))

    assert r["ok"] is False
    assert "No module named 'funnelforge'" in r["erro"]
