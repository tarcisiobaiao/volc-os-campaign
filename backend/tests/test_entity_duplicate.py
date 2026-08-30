"""
Duplicar card de entidade já minerada (v7_12).

Motivação: a mesma entidade roda em SITES diferentes, e cada site precisa do seu
funil e da sua task no ClickUp. O banco impõe 1 oportunidade por entidade
(`uq_pautador_entity_opportunities_entity`), então a cópia é uma entidade nova
com slug próprio, levando as dores e seed queries já mineradas.

Cobre:
  - a cópia nasce em 'mining', com insights VAZIO, sem funil e sem ClickUp;
  - métricas da mineração preservadas; dores e seed queries clonadas;
  - slug da cópia é único e incrementa (-v2, -v3, ...);
  - `display_title` diferencia as cópias e entra no título da task do ClickUp;
  - migração v7_12 ausente => duplica mesmo assim, com warning (nunca 502).

Run:  cd backend && pytest tests/test_entity_duplicate.py -v
"""
from __future__ import annotations

import os
import sys

# offline/mock ANTES de importar o app (padrão dos demais testes)
for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "PERPLEXITY_API_KEY", "PAUTADOR_API_KEY", "CLICKUP_API_TOKEN"):
    os.environ[_k] = ""
os.environ["PAUTADOR_ENGINE"] = "mock"
os.environ["PAUTADOR_KW_ENGINE"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

get_settings.cache_clear()
client = TestClient(app)


class _UnknownColumn(Exception):
    """Simula o PGRST204 do PostgREST quando a migração v7_12 não rodou."""

    def __init__(self, column: str):
        super().__init__(
            f"Could not find the '{column}' column of "
            "'pautador_entity_opportunities' in the schema cache"
        )


class _FakeSupa:
    """Supabase em memória, só com o que o endpoint de duplicação usa."""

    enabled = True
    # quando setado, insert_entity_opportunity rejeita essa coluna (migração ausente)
    reject_column: Optional[str] = None
    store: Dict[str, List[Dict[str, Any]]] = {}

    def __init__(self, settings=None):
        pass

    @classmethod
    def reset(cls, reject_column: Optional[str] = None):
        cls.reject_column = reject_column
        cls.store = {"entities": [], "opps": [], "pains": [], "queries": [], "funnels": [], "seq": [100]}
        ent = {
            "id": 1, "run_id": 7, "country_code": "BR", "country": "Brasil",
            "canonical_name": "CadÚnico", "full_name": "Cadastro Único",
            "slug": "cadunico", "entity_type": "benefit_program",
            "entity_category": "assistencia", "vertical": "gov_beneficios",
            "official_source": "MDS", "related_systems": ["Bolsa Família"],
            "aliases": ["cadastro unico"], "description": "Cadastro de programas sociais.",
            "language": "pt-BR", "status": "ready", "source": "agent", "niche_slug": "beneficios_sociais",
        }
        opp = {
            "id": 2, "entity_id": 1, "run_id": 7, "country_code": "BR",
            "status": "ready", "kanban_stage": "ready",
            "gold_tier": "S", "strategic_stage": "S1 · Ponte", "score": 140.6,
            "estimated_volume": 90000, "ecpm_band": "premium", "roi_signal": 3.2,
            "cpc_min": 0.1, "cpc_max": 0.9, "cpc_currency": "BRL",
            "volume_level": "Alto", "rpm_level": "Muito alto", "competition_level": "Baixa",
            "confidence_level": "Alta", "temporal_window": "Perene",
            "concrete_pain": "Não sabe consultar o benefício.", "gold_reason": "Volume alto, CPC baixo.",
            "insights": "Direcionamento do site A: focar em quem foi bloqueado.",
            "clickup_task_id": "abc123", "clickup_task_url": "https://app.clickup.com/t/abc123",
            "funnel_completed": True, "funnel_architecture": {"pages": [{"page_number": 1}]},
            "display_title": None,
        }
        cls.store["entities"].append(ent)
        cls.store["opps"].append(opp)
        cls.store["pains"].append(
            {"id": 3, "entity_id": 1, "opportunity_id": 2, "pain_name": "Benefício bloqueado",
             "pain_description": "Não sabe o motivo do bloqueio.", "user_goal": "Desbloquear",
             "intent": "informational", "severity": "alta"}
        )
        cls.store["queries"].append(
            {"id": 4, "entity_id": 1, "opportunity_id": 2, "query": "cadunico consulta",
             "query_type": "seed", "intent": "informational", "score": 9.1, "source": "agent"}
        )

    def _id(self):
        self.store["seq"][0] += 1
        return self.store["seq"][0]

    async def get_entity_opportunity(self, opp_id):
        return next((o for o in self.store["opps"] if o["id"] == opp_id), None)

    async def get_entity(self, entity_id):
        return next((e for e in self.store["entities"] if e["id"] == entity_id), None)

    async def get_entity_by_slug(self, code, slug):
        return next(
            (e for e in self.store["entities"] if e.get("country_code") == code and e.get("slug") == slug),
            None,
        )

    async def insert_entity(self, row):
        r = {**row, "id": self._id()}
        self.store["entities"].append(r)
        return r

    async def insert_entity_opportunity(self, row):
        if self.reject_column and self.reject_column in row:
            raise _UnknownColumn(self.reject_column)
        r = {**row, "id": self._id()}
        self.store["opps"].append(r)
        return r

    async def insert_pains(self, rows):
        self.store["pains"].extend(rows)
        return rows

    async def insert_seed_queries(self, rows):
        self.store["queries"].extend(rows)
        return rows

    async def list_entity_cards(self, code):
        out = []
        for o in self.store["opps"]:
            if o.get("country_code") != code:
                continue
            ent = next((e for e in self.store["entities"] if e["id"] == o["entity_id"]), {})
            out.append({
                **o, "entity": ent,
                "pains": [p for p in self.store["pains"] if p.get("entity_id") == o["entity_id"]],
                "seed_queries": [q for q in self.store["queries"] if q.get("entity_id") == o["entity_id"]],
                "funnel_hypotheses": [],
            })
        return out


def _duplicate(payload=None, opp_id: int = 2):
    return client.post(f"/api/pautador/entity-opportunities/{opp_id}/duplicate", json=payload or {})


# ---------------------------------------------------------------------------
# clone
# ---------------------------------------------------------------------------

def test_copia_nasce_em_mineracao_limpa_e_com_a_mineracao_preservada(monkeypatch):
    _FakeSupa.reset()
    monkeypatch.setattr("app.routers.entities.SupabaseService", _FakeSupa)

    resp = _duplicate({"display_title": "Site XPTO"})
    assert resp.status_code == 200, resp.text
    card = resp.json()["card"]

    # (a) estágio e limpeza — a cópia precisa refazer funil e ClickUp por site
    assert card["status"] == "mining"
    assert card["kanban_stage"] == "mining"
    assert not card.get("insights")
    assert not card.get("clickup_task_url")
    assert card.get("funnel_completed") is False
    assert card.get("funnel_hypotheses") == []

    # (b) o token da mineração é o que se aproveita
    assert card["score"] == 140.6
    assert card["gold_tier"] == "S"
    assert card["estimated_volume"] == 90000
    assert card["concrete_pain"] == "Não sabe consultar o benefício."
    assert [p["pain_name"] for p in card["pains"]] == ["Benefício bloqueado"]
    assert [q["query"] for q in card["seed_queries"]] == ["cadunico consulta"]

    # (c) identidade: nome de exibição é do card, a entidade fica intacta
    assert card["display_title"] == "Site XPTO"
    assert card["entity"]["canonical_name"] == "CadÚnico"
    assert card["entity"]["slug"] == "cadunico-v2"

    # (d) é um card NOVO, não uma mutação do original
    assert card["id"] != 2
    original = next(o for o in _FakeSupa.store["opps"] if o["id"] == 2)
    assert original["status"] == "ready"
    assert original["insights"].startswith("Direcionamento do site A")


def test_slug_incrementa_a_cada_copia(monkeypatch):
    _FakeSupa.reset()
    monkeypatch.setattr("app.routers.entities.SupabaseService", _FakeSupa)

    assert _duplicate({"display_title": "Site B"}).json()["card"]["entity"]["slug"] == "cadunico-v2"
    assert _duplicate({"display_title": "Site C"}).json()["card"]["entity"]["slug"] == "cadunico-v3"


def test_sem_nome_de_exibicao_funciona(monkeypatch):
    _FakeSupa.reset()
    monkeypatch.setattr("app.routers.entities.SupabaseService", _FakeSupa)

    card = _duplicate({}).json()["card"]
    assert card["display_title"] in (None, "")
    assert card["status"] == "mining"


def test_card_inexistente_da_404(monkeypatch):
    _FakeSupa.reset()
    monkeypatch.setattr("app.routers.entities.SupabaseService", _FakeSupa)
    assert _duplicate({}, opp_id=999).status_code == 404


def test_sem_migracao_v7_12_duplica_com_warning(monkeypatch):
    """Ambiente onde a v7_12 não rodou: a duplicação é útil demais pra falhar por
    causa do rótulo. Duplica sem o nome e avisa."""
    _FakeSupa.reset(reject_column="display_title")
    monkeypatch.setattr("app.routers.entities.SupabaseService", _FakeSupa)

    resp = _duplicate({"display_title": "Site XPTO"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["card"]["status"] == "mining"
    assert any("v7_12" in w for w in body["warnings"])


# ---------------------------------------------------------------------------
# ClickUp
# ---------------------------------------------------------------------------



def test_falha_ao_criar_o_card_nao_deixa_entidade_orfa(monkeypatch):
    """A entidade é criada ANTES do card. Se o card não nascer, a entidade órfã
    ficaria invisível no Kanban mas viva no dedup e na exclusão da descoberta —
    envenenando runs futuras com uma entidade que ninguém vê."""
    _FakeSupa.reset()

    class _BoomSupa(_FakeSupa):
        deleted: List[int] = []

        async def insert_entity_opportunity(self, row):
            raise RuntimeError("boom: coluna inesperada")

        async def delete_entity(self, entity_id):
            _BoomSupa.deleted.append(entity_id)
            _FakeSupa.store["entities"] = [
                e for e in _FakeSupa.store["entities"] if e["id"] != entity_id
            ]

    _BoomSupa.deleted = []
    monkeypatch.setattr("app.routers.entities.SupabaseService", _BoomSupa)

    assert _duplicate({"display_title": "Site B"}).status_code == 502
    # a entidade recém-criada foi removida: sobra só a original
    assert _BoomSupa.deleted, "entidade órfã não foi removida"
    assert [e["id"] for e in _FakeSupa.store["entities"]] == [1]
