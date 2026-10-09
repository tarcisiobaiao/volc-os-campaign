"""`POST /api/trafego/copy` recusa ANTES de gravar a linha e de gastar token
quando a LP não chegou ao briefing (card 106, 09/10/2026)."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.routers import trafego


class _Ponte:
    def __init__(self, origem):
        self._origem = origem

    def carregar(self, opportunity_id, run_id=None):
        return object()

    def montar_cockpit(self, linhas):
        return SimpleNamespace(origem=self._origem)


def _pedido():
    return {"opportunity_id": 106, "run_id": 28, "keywords": ["gás do povo"], "vertical": "informativo"}


def test_sem_texto_da_lp_recusa_sem_gravar_nem_gastar(monkeypatch):
    origem = SimpleNamespace(texto_da_lp="", promessa_da_lp={"estado": "ausente",
                                                             "motivo_ausencia": "state.json fora do disco"})
    monkeypatch.setattr(trafego, "_ponte", lambda: (_Ponte(origem), None))
    monkeypatch.setattr(trafego, "_supa", lambda: (_ for _ in ()).throw(AssertionError("gravou linha")))
    r = TestClient(app).post("/api/trafego/copy", json=_pedido())
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["codigo"] == "LP_FORA_DO_BRIEFING" and d["nada_foi_gasto"] is True
    assert len(d["faltas"]) == 2 and "state.json fora do disco" in d["faltas"][1]
