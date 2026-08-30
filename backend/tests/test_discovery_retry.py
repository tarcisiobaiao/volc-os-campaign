"""
Descoberta: 2ª chance antes de cair no mock.

Cenário real (BR, nichos benefícios+governo, evergreen): o modelo às vezes
devolve algo fora do contrato. Antes, a run inteira ia pro fallback mock — que
produz entidades genéricas, derrubadas pelos filtros de nicho, e o operador via
"a descoberta trouxe 1". Como o modelo roda a temperature 0.9, a 2ª tentativa
normalmente sai correta.

Run:  cd backend && pytest tests/test_discovery_retry.py -v
"""
from __future__ import annotations

import os
import sys

for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "PERPLEXITY_API_KEY", "PAUTADOR_API_KEY"):
    os.environ[_k] = ""
os.environ["PAUTADOR_ENGINE"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from typing import Any, Dict, List

from app.agents.base import AgentContext
from app.config import Settings, get_settings
from app.entities.orchestrator import EntityDiscoveryOrchestrator, _usable_entities, _validation_summary
from app.entities.schemas import EntityDiscoveryItem
from app.llm.mock import MockEngine

get_settings.cache_clear()


def _ctx() -> AgentContext:
    s = Settings(gemini_api_key="fake-key", supabase_url=None, supabase_service_role_key=None)
    return AgentContext(settings=s, engine=MockEngine(), grounding=None)


def _item(nome: str) -> Dict[str, Any]:
    return {
        "entity": {"canonical_name": nome, "entity_type": "agency", "country": "Brasil"},
        "opportunity": {
            "volume_level": "Alto", "rpm_level": "Alto", "competition_level": "Baixa",
            "confidence_level": "Alta", "gold_tier": "A",
        },
        "pains": [{"pain_name": "dor 1"}, {"pain_name": "dor 2"}],
        "seed_queries": [{"query": "q1"}, {"query": "q2"}, {"query": "q3"}],
    }


# nomes bem distintos de propósito: nomes quase iguais colapsariam no mesmo slug
# e o dedup em lote (correto) fundiria os itens, mascarando a contagem.
NOMES = ["Cadastro Alfa", "Programa Beta", "Certidão Gama"]


def _good(n: int = 3) -> Dict[str, Any]:
    return {"meta": {"country_code": "BR"}, "entities": [_item(NOMES[i]) for i in range(n)]}


FORA_DO_CONTRATO = {"meta": {}, "entities": [{"nome": "sem entity/opportunity"}]}


class _FakeClient:
    """Devolve as respostas da fila, uma por chamada."""

    def __init__(self, respostas: List[Any]):
        self.respostas = list(respostas)
        self.chamadas = 0
        self.model = "fake"

    async def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        self.chamadas += 1
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _run(monkeypatch, respostas: List[Any]) -> tuple[Dict[str, Any], _FakeClient]:
    client = _FakeClient(respostas)
    monkeypatch.setattr("app.entities.orchestrator._gemini", lambda settings, model=None: client)
    out = asyncio.run(EntityDiscoveryOrchestrator(_ctx()).run("Brasil", "BR", "pt-BR", 3))
    return out, client


# ---------------------------------------------------------------------------

def test_primeira_resposta_boa_nao_gasta_segunda_chamada(monkeypatch):
    out, client = _run(monkeypatch, [_good()])
    assert client.chamadas == 1
    assert out["engine"] == "gemini"
    assert len(out["entities"]) == 3


def test_resposta_fora_do_contrato_dispara_segunda_tentativa(monkeypatch):
    out, client = _run(monkeypatch, [FORA_DO_CONTRATO, _good()])
    assert client.chamadas == 2
    assert out["engine"] == "gemini", "a 2ª resposta boa tem que ser usada, não o mock"
    assert len(out["entities"]) == 3
    assert any("2ª foi usada" in w for w in out["warnings"])


def test_erro_de_chamada_tambem_tem_segunda_chance(monkeypatch):
    out, client = _run(monkeypatch, [RuntimeError("Could not parse JSON object from model output"), _good()])
    assert client.chamadas == 2
    assert out["engine"] == "gemini"
    assert len(out["entities"]) == 3


def test_duas_falhas_caem_no_mock_com_aviso(monkeypatch):
    out, client = _run(monkeypatch, [FORA_DO_CONTRATO, RuntimeError("boom")])
    assert client.chamadas == 2
    assert out["engine"] == "mock"
    assert any("usando mock" in w for w in out["warnings"])


# ---------------------------------------------------------------------------

def test_usable_entities():
    assert _usable_entities(_good()) is True
    assert _usable_entities(FORA_DO_CONTRATO) is False
    assert _usable_entities({"entities": []}) is False
    assert _usable_entities({}) is False
    assert _usable_entities("não é dict") is False
    # a MAIORIA precisa prestar: uma válida no meio de lixo não salva a run,
    # entrega 1 card e parece sucesso (era o sintoma relatado)
    assert _usable_entities({"entities": [{"x": 1}, _item("Boa")]}) is False
    assert _usable_entities({"entities": [_item("Boa"), _item("Outra"), {"x": 1}]}) is True


def test_validation_summary_diz_o_campo_que_faltou():
    try:
        EntityDiscoveryItem(**{"pains": []})
    except Exception as exc:
        resumo = _validation_summary(exc)
        assert "entity" in resumo and "Field required" in resumo
        assert "\n" not in resumo, "tem que caber numa linha do toast"
    else:
        raise AssertionError("deveria ter falhado")


# ---------------------------------------------------------------------------
# anti-falha: maioria inválida, oversample e mock nunca persistido
# ---------------------------------------------------------------------------

def _mixed(validos: int, invalidos: int) -> Dict[str, Any]:
    itens = [_item(n) for n in NOMES[:validos]] + [{"lixo": i} for i in range(invalidos)]
    return {"meta": {"country_code": "BR"}, "entities": itens}


def test_resposta_majoritariamente_invalida_dispara_retry(monkeypatch):
    """20 itens com 1 válido é tão ruim quanto zero — e antes passava batido."""
    assert _usable_entities(_mixed(1, 19)) is False
    out, client = _run(monkeypatch, [_mixed(1, 19), _good()])
    assert client.chamadas == 2
    assert out["engine"] == "gemini"
    assert len(out["entities"]) == 3


def test_maioria_valida_e_aproveitada_sem_gastar_outra_chamada(monkeypatch):
    assert _usable_entities(_mixed(3, 1)) is True
    out, client = _run(monkeypatch, [_mixed(3, 1)])
    assert client.chamadas == 1
    assert len(out["entities"]) == 3






# ---------------------------------------------------------------------------
# o resultado do mock NUNCA vira card no board
# ---------------------------------------------------------------------------

def test_endpoint_nao_persiste_fallback_mock(monkeypatch):
    """Se havia chave de LLM e mesmo assim voltou mock, o agente falhou duas
    vezes: são entidades de exemplo. Persistir plantaria card falso no board — e
    ele ainda entraria na lista de exclusão das próximas descobertas."""
    from fastapi.testclient import TestClient

    import app.routers.entities as router_mod
    from app.main import app as fastapi_app

    settings_com_chave = Settings(
        gemini_api_key="fake-key", supabase_url="https://x.supabase.co",
        supabase_service_role_key="k",
    )
    monkeypatch.setattr(router_mod, "get_settings", lambda: settings_com_chave)

    persistidos: List[Any] = []

    class _Supa:
        enabled = True

        def __init__(self, settings=None):
            pass

        async def list_entities(self, code):
            return []

        async def create_run(self, payload):
            return {"id": 1}

        async def update_run(self, run_id, values):
            persistidos.append(("run", values))
            return {"id": run_id, **values}

        async def insert_entity(self, row):  # pragma: no cover — não pode ser chamado
            persistidos.append(("entity", row))
            return {**row, "id": 99}

    class _MockOrchestrator:
        def __init__(self, ctx):
            pass

        async def run(self, *a, **kw):
            return {
                "meta": {"country_code": "BR", "native_language": "pt-BR"},
                "entities": [_norm_like()], "engine": "mock", "model": "mock",
                "warnings": ["Entity discovery (LLM) falhou, usando mock: boom"],
                "cultural_intelligence": {}, "personas": [], "insights": {},
            }

    def _norm_like():
        return {
            "entity": {"canonical_name": "Bolsa Família", "slug": "bolsa-familia",
                       "aliases": [], "related_systems": []},
            "opportunity": {"gold_tier": "A"}, "pains": [], "seed_queries": [],
            "funnel_hypotheses": [],
        }

    monkeypatch.setattr(router_mod, "SupabaseService", _Supa)
    monkeypatch.setattr(router_mod, "EntityDiscoveryOrchestrator", _MockOrchestrator)

    resp = TestClient(fastapi_app).post(
        "/api/pautador/entities/discovery",
        json={"country": "Brasil", "country_code": "BR", "count": 20, "persist": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["persisted"] is False
    assert body["items"] == []
    assert body["created_count"] == 0
    assert any("NÃO foi salvo no board" in w for w in body["warnings"])
    # nenhuma entidade escrita; a run fica marcada como falha
    assert not [p for p in persistidos if p[0] == "entity"]
    assert any(p[0] == "run" and p[1].get("status") == "failed" for p in persistidos)
