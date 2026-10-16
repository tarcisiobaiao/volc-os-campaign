"""Conftest do laboratório: põe `src/` no path e bloqueia rede por padrão."""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

RAIZ_REPO = Path(__file__).resolve().parents[2]
SRC_LAB = RAIZ_REPO / "experiments" / "data-intelligence-lab" / "src"
if str(SRC_LAB) not in sys.path:
    sys.path.insert(0, str(SRC_LAB))


class RedeBloqueada(RuntimeError):
    """Qualquer tentativa de conexão de rede durante os testes do lab."""


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    def _negar(*_a, **_k):
        raise RedeBloqueada("teste do Data Intelligence Lab tentou abrir conexão de rede")

    monkeypatch.setattr(socket.socket, "connect", _negar)
    monkeypatch.setattr(socket.socket, "connect_ex", _negar)
    monkeypatch.setattr(socket, "create_connection", _negar)
    yield
