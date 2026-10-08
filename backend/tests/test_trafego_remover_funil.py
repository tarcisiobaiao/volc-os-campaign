"""`POST /api/trafego/remover` pelo funil: diário antes, `mutar()` no meio, diário depois.

Antes de 08/10/2026 a rota chamava `CampaignService.mutate_campaigns` direto e
não registrava nada. Estes testes trocam só o que fala com o Google
(`remocao.ler_campanha`, `remocao.remover`) e com o banco (o repositório de
eventos); escopo, rota e regra rodam de verdade.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import trafego as rota
from app.trafego import remocao

CID = "5478096539"
CAMP = "24183717006"
CORPO = {"customer_id": CID, "campaign_id": CAMP,
         "motivo": "campanha sem anúncio desde 28/08, resto de lançamento"}


class _Diario:
    def __init__(self, *, habilitado: bool = True, falhar_em: set[str] | None = None):
        self.habilitado = habilitado
        self.falhar_em = falhar_em or set()
        self.eventos: List[Dict[str, Any]] = []

    async def registrar_evento(self, ev: Dict[str, Any]) -> None:
        if ev["tipo"] in self.falhar_em:
            raise RuntimeError("PostgREST fora do ar")
        self.eventos.append(ev)


@pytest.fixture
def cenario(monkeypatch):
    estado: Dict[str, Any] = {"diario": _Diario(), "removeu": [],
                              "campanha": ("FGTS", "PAUSED"), "falha_mutate": None}

    monkeypatch.setattr(rota.escopo, "conta_da_casa", lambda cid: None)
    monkeypatch.setattr(rota, "_repositorio_de_eventos", lambda: estado["diario"])
    monkeypatch.setattr(remocao, "ler_campanha", lambda mid, cid, camp: estado["campanha"])

    def _remover(mid, cid, camp, motivo):
        if estado["falha_mutate"]:
            raise estado["falha_mutate"]
        estado["removeu"].append((mid, cid, camp, motivo))
        return f"customers/{cid}/campaigns/{camp}"

    monkeypatch.setattr(remocao, "remover", _remover)
    return estado


def _post(corpo=CORPO):
    return TestClient(app).post("/api/trafego/remover", json=corpo)


def test_remove_e_registra_intencao_e_desfecho(cenario):
    r = _post()
    assert r.status_code == 200, r.text
    assert r.json()["removida"] is True
    assert r.json()["resource_name"] == f"customers/{CID}/campaigns/{CAMP}"
    tipos = [e["tipo"] for e in cenario["diario"].eventos]
    assert tipos == [remocao.TIPO_PEDIDA, remocao.TIPO_REMOVIDA]
    chaves = {e["chave_de_agrupamento"] for e in cenario["diario"].eventos}
    assert len(chaves) == 1, "intenção e desfecho são da mesma tentativa"
    assert cenario["diario"].eventos[0]["carga"]["motivo"] == CORPO["motivo"]
    assert cenario["removeu"] == [(rota.escopo.MCC_DA_CASA, CID, CAMP, CORPO["motivo"])]


def test_sem_diario_nao_remove(cenario):
    cenario["diario"] = _Diario(habilitado=False)
    r = _post()
    assert r.status_code == 503
    assert cenario["removeu"] == []


def test_intencao_nao_gravada_nao_remove(cenario):
    cenario["diario"] = _Diario(falhar_em={remocao.TIPO_PEDIDA})
    r = _post()
    assert r.status_code == 503
    assert cenario["removeu"] == []


def test_falha_do_mutate_fica_no_diario(cenario):
    cenario["falha_mutate"] = RuntimeError("INTERNAL_ERROR")
    r = _post()
    assert r.status_code == 502
    tipos = [e["tipo"] for e in cenario["diario"].eventos]
    assert tipos == [remocao.TIPO_PEDIDA, remocao.TIPO_FALHOU]
    assert "INTERNAL_ERROR" in cenario["diario"].eventos[1]["carga"]["erro"]


def test_trava_fechada_vira_409_e_fica_no_diario(cenario):
    from volc_ads.gads.modo import EscritaBloqueada

    cenario["falha_mutate"] = EscritaBloqueada("trava fechada")
    r = _post()
    assert r.status_code == 409
    assert [e["tipo"] for e in cenario["diario"].eventos][-1] == remocao.TIPO_FALHOU


def test_desfecho_nao_gravado_devolve_a_remocao_com_aviso(cenario):
    cenario["diario"] = _Diario(falhar_em={remocao.TIPO_REMOVIDA})
    r = _post()
    assert r.status_code == 200
    assert r.json()["removida"] is True
    assert "aviso_registro" in r.json()


def test_campanha_ativa_sem_sinal_explicito_nao_remove_nem_registra(cenario):
    cenario["campanha"] = ("Senac", "ENABLED")
    r = _post()
    assert r.status_code == 409
    assert cenario["removeu"] == [] and cenario["diario"].eventos == []


def test_ja_removida_nao_chama_o_google(cenario):
    cenario["campanha"] = ("FGTS", "REMOVED")
    r = _post()
    assert r.status_code == 200 and r.json()["ja_removida"] is True
    assert cenario["removeu"] == []


def test_campanha_inexistente_e_404(cenario):
    cenario["campanha"] = ("", "")
    assert _post().status_code == 404


def test_operacao_de_remocao_contra_o_proto_v25():
    from google.ads.googleads.v25.services.types.google_ads_service import MutateOperation

    op = remocao.operacao_de_remocao(lambda nome: MutateOperation(), CID, CAMP)
    assert op.campaign_operation.remove == f"customers/{CID}/campaigns/{CAMP}"
    assert MutateOperation.pb(op).WhichOneof("operation") == "campaign_operation"
