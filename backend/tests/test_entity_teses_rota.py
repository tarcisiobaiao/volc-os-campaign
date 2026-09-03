"""A rota de teses é leitura pura: não mede, não gasta, não some com card."""
from __future__ import annotations

from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient


def _resumo(cobertura=1.0, engajamento="sustenta", ramos=3, condicoes=3):
    return {
        "apto": True, "motivo": None, "indice": 0.72, "cobertura": cobertura,
        "perfil": "alvo", "portoes_disparados": [], "alertas": [],
        "eixos": {
            "volume": {"nivel": "alto", "proveniencia": "medido", "motivo_ausencia": None},
            "engajamento": {"nivel": engajamento, "proveniencia": "julgado", "motivo_ausencia": None},
            "ignorancia": {"nivel": "nao_sei_se_sirvo", "proveniencia": "julgado", "motivo_ausencia": None},
        },
        "ficha": {
            "share_dado_unico": 0.25, "n_perguntas": 2,
            "perguntas": [
                {"pergunta": "Quem tem direito?", "ramos": ramos, "condicoes": condicoes,
                 "decide_depois": True, "oficial_fecha_sozinho": False},
                {"pergunta": "Quando cai?", "ramos": 1, "condicoes": 0,
                 "decide_depois": False, "oficial_fecha_sozinho": True},
            ],
        },
    }


class SupaFake:
    enabled = True

    def __init__(self, linhas: List[Dict[str, Any]]):
        self.linhas = linhas
        self.chamadas: List[Any] = []

    async def select(self, tabela, filtro):
        self.chamadas.append((tabela, dict(filtro)))
        return self.linhas


@pytest.fixture
def cliente(monkeypatch):
    from app.main import app
    return TestClient(app)


def _monta(monkeypatch, linhas):
    supa = SupaFake(linhas)
    monkeypatch.setattr("app.routers.entities.SupabaseService", lambda *_a, **_k: supa)
    return supa


def test_rota_devolve_tese_sem_medir(cliente, monkeypatch):
    supa = _monta(monkeypatch, [
        {"id": 1, "validacao": _resumo(), "pautador_entities": {"canonical_name": "FGTS"}},
    ])
    r = cliente.post("/api/pautador/entity-opportunities/teses", json={"opportunity_ids": [1]})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["total"] == 1
    t = corpo["teses"][0]
    assert t["tema"] == "FGTS"
    assert t["decisao"] == "aprofundar"
    assert t["observaveis_do_formato"], "o formato precisa citar observáveis"
    # leitura pura: uma consulta, nenhuma escrita
    assert len(supa.chamadas) == 1


def test_card_sem_cobertura_nao_some_da_tela(cliente, monkeypatch):
    _monta(monkeypatch, [
        {"id": 1, "validacao": _resumo(cobertura=1.0), "pautador_entities": {"canonical_name": "boa"}},
        {"id": 2, "validacao": _resumo(cobertura=0.2), "pautador_entities": {"canonical_name": "magra"}},
    ])
    corpo = cliente.post("/api/pautador/entity-opportunities/teses",
                         json={"opportunity_ids": [1, 2]}).json()
    assert [t["tema"] for t in corpo["ranking"]] == ["boa"]
    assert [t["tema"] for t in corpo["fora_do_ranking"]] == ["magra"]
    assert corpo["fora_do_ranking"][0]["motivo_incomparavel"]
    # e o id sobrevive à separação
    assert corpo["fora_do_ranking"][0]["opportunity_id"] == 2


def test_card_sem_validacao_vira_lacuna_declarada(cliente, monkeypatch):
    _monta(monkeypatch, [
        {"id": 7, "validacao": None, "pautador_entities": {"canonical_name": "antigo"}},
    ])
    corpo = cliente.post("/api/pautador/entity-opportunities/teses",
                         json={"opportunity_ids": [7]}).json()
    t = corpo["teses"][0]
    assert t["decisao"] == "sem_validacao"
    assert t["comparavel"] is False
    assert corpo["ranking"] == []


def test_priors_desligados_por_padrao_e_nunca_movem_a_decisao(cliente, monkeypatch):
    linhas = [{"id": 1, "validacao": _resumo(), "pautador_entities": {"canonical_name": "x"}}]
    _monta(monkeypatch, linhas)
    sem = cliente.post("/api/pautador/entity-opportunities/teses",
                       json={"opportunity_ids": [1]}).json()["teses"][0]
    _monta(monkeypatch, linhas)
    com = cliente.post("/api/pautador/entity-opportunities/teses",
                       json={"opportunity_ids": [1], "aplicar_priors": True}).json()["teses"][0]
    assert sem["decisao"] == com["decisao"]
    assert not sem["hipoteses"]
    assert com["hipoteses"], "com priors ligados eles aparecem como hipótese"


def test_sem_selecao_nao_varre_a_base_inteira(cliente, monkeypatch):
    supa = _monta(monkeypatch, [])
    corpo = cliente.post("/api/pautador/entity-opportunities/teses", json={}).json()
    assert corpo["teses"] == [] and corpo["ranking"] == []
    assert supa.chamadas == [], "sem seleção a rota não pode consultar"
