"""Review-only reproductions. No account, socket, credential or official DB access."""
import os
import socket
for key in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
    os.environ[key] = ""
_connect = socket.socket.connect
def _no_network(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        raise AssertionError("NETWORK DISALLOWED IN REVIEW")
    return _connect(self, address)
socket.socket.connect = _no_network

import asyncio
from datetime import datetime, timedelta, timezone
import pytest
import test_meta_criacao_pausada_rotas as h

@pytest.fixture(autouse=True)
def reset():
    h.CENARIO.reiniciar()
    yield
    h.CENARIO.reiniciar()

def setup(monkeypatch, ledger=None, plan=None):
    ledger = ledger or h._LedgerEmMemoria()
    h._abrir(monkeypatch, ledger)
    client = h._cliente()
    response = asyncio.run(h._aprovar(client, ledger, plan or h._plano_para_envio()))
    assert response.status_code == 200, response.text
    approval = response.json()["aprovacao"]
    return ledger, client, approval

def create(client, approval):
    return client.post("/api/trafego/meta/local/criacao/criar-pausada", json={
        "approval_id": approval["approval_id"],
        "plano_sha256_esperado": approval["plano_sha256"],
    })

def test_readback_persistence_failure_still_reports_success(monkeypatch):
    class BrokenReadback(h._LedgerEmMemoria):
        async def registrar_readback(self, **kwargs):
            raise RuntimeError("synthetic storage unavailable for read-back")
    ledger, client, approval = setup(monkeypatch, BrokenReadback())
    response = create(client, approval)
    assert response.status_code == 200, response.text
    assert response.json()["desfecho"] == "CREATED_PAUSED"
    assert len(ledger.passos) == 4
    assert all(p.get("readback_evidencia") is None for p in ledger.passos.values())
    print("REPRODUCED: 4 mock objects created, read-back writes all fail, HTTP 200 CREATED_PAUSED, 0 durable read-backs")

def test_known_created_id_is_not_read_by_recovery(monkeypatch):
    ledger, client, approval = setup(monkeypatch)
    aid = approval["approval_id"]
    ledger.passos["passo-campaign"] = {
        "approval_id": aid, "nome": "campaign", "ordinal": 1,
        "state": "CREATED", "id_externo": h.IDS_CRIADOS["campaign"],
        "codigo": None, "readback": None, "prepared_at": h.PREPARADO_EM,
    }
    h.CENARIO.gets.clear()
    response = client.post("/api/trafego/meta/local/criacao/reconciliar", json={"approval_id": aid})
    assert response.status_code == 200, response.text
    assert response.json()["passos_ambiguos"] == 0
    assert h.CENARIO.gets == []
    receipt = response.json()["recibo"]
    assert receipt["operations_expected"] == 4 and len(receipt["steps"]) == 1
    assert all(p["state"] == "CREATED" and not p["readback_error"] for p in receipt["steps"])
    print("REPRODUCED: Campaign ID known, no read-back, 1/4 steps; recovery returns 0 ambiguous and performs 0 GETs")

def test_supply_expiry_does_not_close_new_dispatch(monkeypatch):
    plan = h._plano_para_envio()
    confirmed = datetime.now(timezone.utc) - timedelta(minutes=59)
    plan["asset_policy_confirmed_at"] = confirmed.isoformat()
    for variation in plan["variations"]:
        variation["asset_policy_confirmed_at"] = confirmed.isoformat()
    ledger, client, approval = setup(monkeypatch, plan=plan)
    from app.trafego.meta_execucao import contrato
    future = datetime.now(timezone.utc) + timedelta(minutes=2)
    class FutureDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return future.astimezone(tz) if tz else future.replace(tzinfo=None)
    monkeypatch.setattr(contrato, "datetime", FutureDatetime)
    frozen = ledger.aprovacoes[approval["approval_id"]]["plano_congelado"]
    assert all(datetime.fromisoformat(item["policy_expires_at"]) < future for item in frozen["asset_supply"])
    assert ledger.aprovacoes[approval["approval_id"]]["expires_at"] > future
    response = create(client, approval)
    assert response.status_code == 200, response.text
    assert len(h.CENARIO.criados) == 4
    print("REPRODUCED: policy receipt expired, approval still valid; 4 mock create POSTs accepted")

def test_late_worker_posts_after_claim_was_reclaimed(monkeypatch):
    class PausedWorker(h._LedgerEmMemoria):
        async def preparar_passo(self, **kwargs):
            result = await super().preparar_passo(**kwargs)
            if kwargs["nome"] == "campaign":
                # A claim reply is held while another process reclaims the old
                # IN_FLIGHT row; then the first worker resumes with its old reply.
                self.passos[result.passo_ref]["prepared_at"] = h.PREPARADO_EM
                await self.reclamar_orfao(passo_ref=result.passo_ref, idade_minima_s=300)
                assert self.passos[result.passo_ref]["state"] == "AMBIGUOUS"
            return result
    ledger, client, approval = setup(monkeypatch, PausedWorker())
    response = create(client, approval)
    assert response.status_code == 200, response.text
    assert ("reclamar", "passo-campaign") in ledger.eventos
    assert len(h.CENARIO.criados) == 4
    print("REPRODUCED: worker resumes with old claim reply after reclaim; 4 mock POSTs, no fencing/revalidation of claim")
