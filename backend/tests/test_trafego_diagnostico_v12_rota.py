from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.routers.trafego_diagnostico import obter_repositorio_diagnostico
from app.seguranca.identidade import Identidade, exigir_usuario
from app.trafego.diagnostico_persistido import ServicoIndisponivelError

pytestmark = pytest.mark.identidade_real


class Repo:
    def __init__(self, *, existe: bool = True, coleta: Optional[Dict[str, Any]] = None,
                 falhar: bool = False) -> None:
        self.existe = existe
        self._coleta = coleta
        self.falhar = falhar

    async def campanha(self, volc_campaign_id: str):
        if self.falhar:
            raise ServicoIndisponivelError("db offline")
        if not self.existe:
            return None
        return {
            "volc_campaign_id": volc_campaign_id,
            "customer_id": "customer-test",
            "campaign_id": "external-test",
            "nome": "Search teste",
            "moeda": None,
        }

    async def coleta(self, _id: str):
        if self.falhar:
            raise ServicoIndisponivelError("db offline")
        return self._coleta

    async def itens(self, _id: str) -> List[Dict[str, Any]]:
        return []

    async def metricas(self, _id: str) -> List[Dict[str, Any]]:
        return []


@pytest.fixture
def cliente():
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.pop(obter_repositorio_diagnostico, None)
    app.dependency_overrides.pop(exigir_usuario, None)


def _autorizar(repo: Repo) -> None:
    app.dependency_overrides[exigir_usuario] = lambda: Identidade(
        sub="00000000-0000-0000-0000-000000000001",
        email="operador@volc.test", papel="VIEWER", origem="sessao",
    )
    app.dependency_overrides[obter_repositorio_diagnostico] = lambda: repo


def test_contraprova_rota_exige_usuario(cliente, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://supabase.invalid", raising=False)
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-role-test", raising=False)
    resposta = cliente.get("/api/trafego/campanhas/cmp.search:01/diagnostico")
    assert resposta.status_code == 401


def test_contraprova_rota_entrega_envelope_exato(cliente):
    _autorizar(Repo())
    resposta = cliente.get("/api/trafego/campanhas/cmp.search:01/diagnostico")
    assert resposta.status_code == 200
    assert set(resposta.json()) == {"versao", "diagnostico", "propostas"}
    assert set(resposta.json()["diagnostico"]) == {
        "versao", "volc_campaign_id", "customer_id", "nome_campanha", "moeda",
        "estado_coleta", "frescor", "janela", "leitura", "degraus", "parcial",
    }
    assert resposta.json()["diagnostico"]["estado_coleta"] is None
    assert resposta.json()["diagnostico"]["frescor"] == "nao_apurado"
    assert resposta.json()["diagnostico"]["janela"] == "coleta ainda não executada"


def test_contraprova_id_invalido_e_id_externo_nao_abrem_fallback(cliente):
    _autorizar(Repo(existe=False))
    invalido = cliente.get("/api/trafego/campanhas/id%2Fcom%2Fbarra/diagnostico")
    externo = cliente.get("/api/trafego/campanhas/24156373085/diagnostico")
    assert invalido.status_code == 404
    assert externo.status_code == 404


def test_contraprova_falha_db_retorna_503_e_nao_404(cliente):
    _autorizar(Repo(falhar=True))
    resposta = cliente.get("/api/trafego/campanhas/cmp.search:01/diagnostico")
    assert resposta.status_code == 503
    assert resposta.status_code != 404


def test_contraprova_campanha_inexistente_retorna_404(cliente):
    _autorizar(Repo(existe=False))
    resposta = cliente.get("/api/trafego/campanhas/cmp.search:01/diagnostico")
    assert resposta.status_code == 404


def test_contraprova_falhou_permanece_explicito_na_rota(cliente):
    _autorizar(Repo(coleta={
        "coleta_id": "coleta-01",
        "estado": "falhou",
        "customer_id": "customer-test",
        "volc_campaign_id": "cmp.search:01",
        "campaign_id": "external-test",
        "coletada_em": "2026-08-29T10:00:00Z",
        "janela_inicio": "2026-08-28",
        "janela_fim": "2026-08-29",
        "erro_codigo": "GAQL_ERROR",
        "erro_classe": None,
    }))
    resposta = cliente.get("/api/trafego/campanhas/cmp.search:01/diagnostico")
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["diagnostico"]["estado_coleta"] == "falhou"
    assert dados["diagnostico"]["frescor"] == "nao_apurado"
    assert dados["propostas"]["leitura"] is None
    assert "terminou em falhou" in dados["diagnostico"]["degraus"][0]["impedimento"]
