"""Teto e congruência do DONO entram na mineração Python, com fonte.

Medido em 09/10/2026: o orquestrador chamava `funnel_factory` sem teto e sem
congruência, então TODO conjunto minerado em Python nascia com
`teto_economico_desconhecido` e `congruencia_nao_avaliada` — e nenhuma rota os
resolvia depois. Nenhum conjunto podia ser aprovado.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.mining.funnel_factory import funnel_factory_com_conjuntos
from app.schemas import MineRequest
from tests.test_pautador_paid_keyword_counterproofs import BPC_LOAS, HOJE

FONTE = "declarado por teste: teto do canário, conferido contra a LP"


def test_sem_entrada_do_dono_o_conjunto_continua_bloqueado():
    _, conjuntos = funnel_factory_com_conjuntos(BPC_LOAS, today=HOJE)
    assert {"teto_economico_desconhecido", "congruencia_nao_avaliada"} <= set(conjuntos[0].blockers)


def test_com_teto_e_congruencia_os_bloqueadores_saem_e_a_fonte_fica():
    _, conjuntos = funnel_factory_com_conjuntos(
        BPC_LOAS, today=HOJE, teto_do_dono=1.0, congruencia="congruente",
        evidencia={"teto_fonte": FONTE, "congruencia_fonte": FONTE})
    c = conjuntos[0]
    assert "teto_economico_desconhecido" not in c.blockers
    assert "congruencia_nao_avaliada" not in c.blockers
    assert c.owner_ceiling == 1.0
    assert c.evidence_snapshot["congruencia_fonte"] == FONTE
    # o teto MUDA decisão: CPC medido acima dele não entra na seleção
    assert all(d.cpc.valor <= 1.0 for d in c.selected_keywords if d.cpc.tem_numero)


def test_incongruente_rejeita_os_termos():
    _, conjuntos = funnel_factory_com_conjuntos(
        BPC_LOAS, today=HOJE, teto_do_dono=1.0, congruencia="incongruente",
        evidencia={"congruencia_fonte": FONTE})
    assert conjuntos[0].selected_keywords == []


@pytest.mark.parametrize("campos", [
    {"teto_cpc_do_dono": 1.0},
    {"congruencia": "congruente", "congruencia_fonte": "curta"},
    {"teto_cpc_do_dono": 0},
])
def test_entrada_do_dono_sem_fonte_ou_invalida_e_recusada(campos):
    with pytest.raises(ValidationError):
        MineRequest(**campos)


# ── reavaliação pós-mineração (rota) ───────────────────────────────────────

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seguranca.identidade import Identidade, exigir_admin, exigir_usuario  # noqa: E402
from app.agents.mining.funnel_factory import funnel_factory  # noqa: E402

_ADMIN = Identidade(sub="teste-admin", email="", papel="ADMIN", origem="servico")


@pytest.fixture(autouse=True)
def _overrides_preservados():
    """Restaura as substituições do conftest: `clear()` apagaria a identidade
    que os outros módulos da sessão esperam."""
    antes = dict(app.dependency_overrides)
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(antes)


def _cliente_com(cluster, gravados):
    class FakeSupa:
        enabled = True

        def __init__(self, settings):
            pass

        async def get_latest_cluster(self, opp_id):
            return cluster

        async def insert_cluster(self, row):
            gravados.append(row)
            return {**row, "id": 999}

    app.dependency_overrides[exigir_usuario] = lambda: _ADMIN
    app.dependency_overrides[exigir_admin] = lambda: _ADMIN
    return FakeSupa


def _corpo(mapa):
    return {"teto_cpc_do_dono": 2.0, "teto_fonte": FONTE, "destino_url": "https://exemplo.com.br/lp/",
            "congruencia_por_termo": mapa, "congruencia_fonte": FONTE}


def _termos_do_bpc():
    return [k["keyword"] for s in BPC_LOAS["funis_sugeridos"][0]["sub_intencoes"] for k in s["keywords"]]


def test_reavaliar_com_veredito_para_todos_tira_os_bloqueadores(monkeypatch):
    gravados = []
    cluster = {"id": 7, "opportunity_id": 106, "run_id": None, "engine": "live",
               "funis_sugeridos": BPC_LOAS["funis_sugeridos"],
               "factory_output": funnel_factory(BPC_LOAS, today=HOJE)}
    monkeypatch.setattr("app.routers.pautador.SupabaseService", _cliente_com(cluster, gravados))
    mapa = {t: "congruente" for t in _termos_do_bpc()}
    mapa["meu inss login"] = "incongruente"
    r = TestClient(app).post("/api/pautador/opportunities/106/conjunto-pago/reavaliar", json=_corpo(mapa))
    assert r.status_code == 200, r.text
    f = r.json()["funis"][0]
    assert f["bloqueadores"] == [] and f["sem_veredito"] == []
    cp = gravados[0]["factory_output"][0]["keywords_campanha"]["conjunto_pago"]
    assert "meu inss login" not in [d["termo"] for d in cp["selected_keywords"]]
    assert cp["evidence_snapshot"]["reavaliado_de_cluster"] == 7
    assert r.json()["cluster_novo"] == 999


def test_reavaliar_sem_veredito_de_algum_termo_mantem_o_bloqueio(monkeypatch):
    gravados = []
    cluster = {"id": 7, "opportunity_id": 106, "funis_sugeridos": BPC_LOAS["funis_sugeridos"],
               "factory_output": funnel_factory(BPC_LOAS, today=HOJE)}
    monkeypatch.setattr("app.routers.pautador.SupabaseService", _cliente_com(cluster, gravados))
    r = TestClient(app).post("/api/pautador/opportunities/106/conjunto-pago/reavaliar",
                             json=_corpo({"bpc loas quem tem direito": "congruente"}))
    assert r.status_code == 200, r.text
    assert "congruencia_nao_avaliada" in r.json()["funis"][0]["bloqueadores"]


def test_reavaliar_recusa_cluster_do_n8n(monkeypatch):
    cluster = {"id": 4, "opportunity_id": 73, "funis_sugeridos": BPC_LOAS["funis_sugeridos"],
               "factory_output": [{"keywords_campanha": {"lista_google_ads": ["x"]}}]}
    monkeypatch.setattr("app.routers.pautador.SupabaseService", _cliente_com(cluster, []))
    r = TestClient(app).post("/api/pautador/opportunities/73/conjunto-pago/reavaliar",
                             json=_corpo({"x": "congruente"}))
    assert r.status_code == 409
