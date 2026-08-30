"""
ENTITY-FIRST tests: normalization/dedup, scoring, orchestrator (mock), API.
Run:  cd backend && pytest -q
"""
from __future__ import annotations

import os
import sys

# offline/mock BEFORE importing the app
for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "PERPLEXITY_API_KEY", "PAUTADOR_API_KEY"):
    os.environ[_k] = ""
os.environ["PAUTADOR_ENGINE"] = "mock"
os.environ["PAUTADOR_KW_ENGINE"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.agents.base import AgentContext
from app.entities.normalize import (
    canonical_acronym,
    entity_keys,
    entity_name_key,
    find_matching_entity,
    identity_keys,
    normalize_entity_slug,
    suggest_official_source,
)
from app.entities.orchestrator import EntityDiscoveryOrchestrator
from app.entities.scoring import compute_entity_score, normalize_level
from app.llm.mock import MockEngine

get_settings.cache_clear()


# --- normalization / dedup ----------------------------------------------------
@pytest.mark.parametrize("text,slug", [
    ("actualizar rut", "rut"),
    ("descargar rut", "rut"),
    ("rut dian", "rut"),
    ("como actualizar el rut por internet dian", "rut"),
    ("meu inss", "inss"),
    ("Bolsa Família", "bolsa-familia"),
    ("registro unico tributario", "registro-unico-tributario"),
])
def test_normalize_entity_slug(text, slug):
    assert normalize_entity_slug(text) == slug


def test_acronym_and_source():
    assert canonical_acronym("rut dian") == "RUT"
    assert suggest_official_source("como actualizar el rut por internet dian") == "DIAN"
    assert suggest_official_source("meu inss") is None  # INSS is the entity, not a separate source


@pytest.mark.parametrize("nome,chave", [
    # nome É a sigla -> a sigla é a identidade (igual ao normalize_entity_slug)
    ("INSS", "inss"),
    ("meu INSS", "inss"),
    # nome CONTÉM a sigla -> os demais tokens continuam na identidade
    # (normalize_entity_slug devolveria só 'inss'/'cpf'/'sus' e fundiria tudo)
    ("Pagamento do INSS", "pagamento-inss"),
    ("Aposentadoria pelo INSS", "aposentadoria-inss"),
    ("CPF Regularização", "cpf-regularizacao"),
    ("Meu SUS Digital", "sus-digital"),
    ("Bolsa Família", "bolsa-familia"),
])
def test_entity_name_key_preserva_o_que_distingue(nome, chave):
    assert entity_name_key(nome) == chave


def test_dedup_merges_synonyms_without_shared_tokens():
    """Sinônimos de IDENTIDADE continuam fundindo: sigla ↔ nome por extenso."""
    existing = [{"slug": "rut", "canonical_name": "RUT", "full_name": "Registro Único Tributario", "aliases": ["RUT DIAN"]}]
    for q in ["actualizar rut", "descargar rut", "registro unico tributario", "RUT"]:
        keys = entity_keys(q)
        m = find_matching_entity(keys, existing)
        assert m is not None and m["slug"] == "rut", q


def test_dedup_nao_funde_entidades_distintas_que_citam_a_mesma_sigla():
    """Regressão do bug que fazia a descoberta "trazer repetido".

    `normalize_entity_slug` colapsa qualquer texto na sigla que ele contém — regra
    certa pra query suja, desastrosa pra NOME de entidade: "Pagamento do INSS" e
    "Aposentadoria pelo INSS" viravam ambas a chave 'inss' e eram tratadas como a
    MESMA entidade. Na prática, cards novos (CIN, Sisreg, Baixa de MEI) eram
    absorvidos por registros sem relação, e os aliases deles gravados lá dentro.
    """
    existing = [
        {"slug": "pagamento-do-inss", "canonical_name": "Pagamento do INSS",
         "aliases": ["calendário do INSS", "meu inss login"]},
        {"slug": "regularizacao-cpf", "canonical_name": "CPF Regularização",
         "aliases": ["Regularizar CPF", "novo rg cin", "cpf"]},
        {"slug": "meu-sus-digital", "canonical_name": "Meu SUS Digital", "aliases": ["Conecte SUS", "sus"]},
        {"slug": "regularizacao-de-cnpj", "canonical_name": "Regularização de CNPJ", "aliases": ["cnpj inapto", "cnpj"]},
    ]

    # entidades DIFERENTES que só compartilham a sigla -> não podem fundir
    for nome, aliases in [
        ("Aposentadoria pelo INSS", ["aposentadoria por idade", "inss"]),
        ("Carteira de Identidade Nacional", ["novo rg cin", "agendar nova identidade"]),
        ("Sisreg", ["consulta fila sus", "sus"]),
        ("Baixa de MEI", ["dar baixa no mei", "cnpj"]),
        ("Certidão Negativa da Receita Federal", ["cnd receita federal", "cpf"]),
    ]:
        keys = entity_keys(nome, None, aliases)
        keys.add(normalize_entity_slug(nome))
        ident = identity_keys(nome, None, normalize_entity_slug(nome))
        assert find_matching_entity(keys, existing, candidate_identity_keys=ident) is None, nome

    # e a MESMA entidade continua sendo reconhecida
    keys = entity_keys("Pagamento do INSS", None, ["calendário do INSS"])
    ident = identity_keys("Pagamento do INSS", None, "pagamento-do-inss")
    m = find_matching_entity(keys, existing, candidate_identity_keys=ident)
    assert m is not None and m["slug"] == "pagamento-do-inss"


def test_dedup_ignora_casamento_so_por_alias():
    """alias ↔ alias não é prova de identidade (era o vetor do sequestro)."""
    existing = [{"slug": "implante-dentario", "canonical_name": "Implante Dentário Gratuito", "aliases": ["sus", "implante pelo sus"]}]
    keys = entity_keys("Cartão Nacional de Saúde", None, ["sus", "cartao sus"])
    ident = identity_keys("Cartão Nacional de Saúde", None, "cartao-nacional-de-saude")
    assert find_matching_entity(keys, existing, candidate_identity_keys=ident) is None


# --- scoring ------------------------------------------------------------------
def test_normalize_level_pt_es():
    assert normalize_level("Muito alto") == "very_high"
    assert normalize_level("Alto") == "high"
    assert normalize_level("Baixa") == "low"
    assert normalize_level("Médio") == "medium"


def test_compute_entity_score_matches_spec_example():
    # RUT example from the spec: Alto/Muito alto/Baixa/Muito alto + tier S -> 140.63
    opp = {"volume_level": "Alto", "rpm_level": "Muito alto", "competition_level": "Baixa",
           "confidence_level": "Muito alto", "gold_tier": "S"}
    score, roi, source = compute_entity_score(opp)
    assert score == 140.63 and source == "computed"


def test_compute_entity_score_falls_back_to_llm():
    opp = {"score": 99.5}  # no levels
    score, roi, source = compute_entity_score(opp)
    assert score == 99.5 and source == "llm"


# --- orchestrator (mock) ------------------------------------------------------
def _ctx() -> AgentContext:
    s = Settings(gemini_api_key=None, google_api_key=None, supabase_url=None, supabase_service_role_key=None)
    return AgentContext(settings=s, engine=MockEngine(), grounding=None)


def test_entity_discovery_orchestrator_mock():
    disc = asyncio.run(EntityDiscoveryOrchestrator(_ctx()).run("Colômbia", "CO", "es-CO", 5))
    assert disc["engine"] == "mock"
    assert len(disc["entities"]) == 5
    rut = disc["entities"][0]
    assert rut["entity"]["canonical_name"] == "RUT"
    assert rut["entity"]["slug"] == "rut"
    assert rut["entity"]["official_source"] == "DIAN"
    assert rut["opportunity"]["score"] == 140.63
    assert len(rut["pains"]) >= 2 and len(rut["seed_queries"]) >= 3
    assert disc["personas"] and disc["cultural_intelligence"]


# --- API (dry / mock) ---------------------------------------------------------
client = TestClient(__import__("app.main", fromlist=["app"]).app)


def test_api_entity_discovery_dry():
    r = client.post("/api/pautador/entities/discovery", json={"country": "Colômbia", "country_code": "CO", "count": 5})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["persisted"] is False and len(b["items"]) == 5
    card = b["items"][0]
    # criteria: card title = entity, NOT the long-tail keyword
    assert card["entity"]["canonical_name"] == "RUT"
    assert card["entity"]["full_name"] == "Registro Único Tributario"
    assert card["entity"]["official_source"] == "DIAN"
    # the old-style query lives in seed_queries, never as the title
    queries = [q["query"] for q in card["seed_queries"]]
    assert any("rut" in q for q in queries)
    assert card["entity"]["canonical_name"] not in queries
    # o funil NÃO nasce na descoberta — só na etapa "Funil"
    assert card["funnel_hypotheses"] == []


def test_api_entity_mine_and_funnel_dry():
    disc = client.post("/api/pautador/entities/discovery", json={"country": "México", "country_code": "MX", "count": 3}).json()
    ent = {**disc["items"][0]["entity"], "id": 0}
    rm = client.post("/api/pautador/entities/0/mine", json={"entity": ent})
    assert rm.status_code == 200 and len(rm.json()["pains"]) >= 2
    assert rm.json()["dispatched"] is False and rm.json()["mode"] == "internal"  # sem webhook = interno
    # Funil agora roda o ARQUITETO (FUNNEL.json) -> esqueleto de páginas + writingJobs
    rf = client.post("/api/pautador/entity-opportunities/0/funnel", json={"entity": ent})
    assert rf.status_code == 200, rf.text
    fr = rf.json()
    assert len(fr["pages"]) == 5 and len(fr["writing_jobs"]) == 5
    assert len(fr["funnel_hypotheses"]) >= 1
    assert fr["funnel_strategy"] is not None


def test_mine_dispatches_to_n8n_when_webhook_configured(monkeypatch):
    s = Settings(
        pautador_n8n_kw_webhook_url="https://n8n.example/webhook/pautador-kw-mining",
        supabase_url="https://x.supabase.co", supabase_service_role_key="svc",
        gemini_api_key=None, google_api_key=None,
    )
    monkeypatch.setattr("app.routers.entities.get_settings", lambda: s)

    class FakeSupa:
        enabled = True

        def __init__(self, settings):
            pass

        async def get_entity(self, eid):
            return {"id": eid, "run_id": 1, "country": "Colômbia", "country_code": "CO",
                    "canonical_name": "RUT", "full_name": "Registro Único Tributario",
                    "description": "x", "language": "es-CO"}

        async def get_opportunity_by_entity(self, eid):
            return {"id": 77}

        async def update_entity_opportunity(self, *a, **k):
            return {}

        async def update_entity(self, *a, **k):
            return {}

    monkeypatch.setattr("app.routers.entities.SupabaseService", FakeSupa)

    captured = {}

    async def _fake_dispatch(settings, entity, opp_id):
        captured["opp_id"] = opp_id
        captured["nicho"] = entity.get("canonical_name")
        return True, None

    monkeypatch.setattr("app.routers.entities._dispatch_n8n_kw", _fake_dispatch)

    r = client.post("/api/pautador/entities/5/mine", json={})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["dispatched"] is True and b["mode"] == "n8n"
    assert b["opportunity_id"] == 77 and b["services_used"] == ["n8n:webhook"]
    assert captured == {"opp_id": 77, "nicho": "RUT"}


def test_dispatch_n8n_payload_has_geo_from_dataset(monkeypatch):
    # _dispatch_n8n_kw monta o payload com geo do dataset 195 (GB -> 2826/1000)
    import app.routers.entities as ent_mod

    sent = {}

    class _Resp:
        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            sent["url"] = url
            sent["payload"] = json
            return _Resp()

    monkeypatch.setattr("httpx.AsyncClient", _Client)
    s = Settings(pautador_n8n_kw_webhook_url="https://n8n.example/hook", request_timeout_seconds=5)
    entity = {"id": 1, "country": "Reino Unido", "country_code": "GB", "canonical_name": "HMRC"}
    ok, warn = asyncio.run(ent_mod._dispatch_n8n_kw(s, entity, opp_id=9))
    assert ok is True and warn is None
    p = sent["payload"]
    assert p["geo_target"] == 2826 and p["language_constant"] == 1000
    assert p["country_code"] == "GB" and p["opportunity_id"] == 9 and p["nicho"] == "HMRC"


def test_api_entity_mine_missing_returns_404():
    r = client.post("/api/pautador/entities/999/mine", json={})
    assert r.status_code == 404


# --- persistence: runs ADD + dedup (no duplicate cards across runs) -----------
class _FakeSupa:
    """Minimal in-memory Supabase for the discovery persistence path."""
    enabled = True

    def __init__(self, settings=None):
        # shared store across instances (class-level) so two discovery calls share state
        pass

    store = {"entities": [], "opps": [], "pains": [], "queries": [], "funnels": [], "runs": [], "seq": [0]}

    @classmethod
    def reset(cls):
        cls.store = {"entities": [], "opps": [], "pains": [], "queries": [], "funnels": [], "runs": [], "seq": [0]}

    def _id(self):
        self.store["seq"][0] += 1
        return self.store["seq"][0]

    async def create_run(self, payload):
        row = {**payload, "id": self._id()}
        self.store["runs"].append(row)
        return row

    async def update_run(self, run_id, values):
        for r in self.store["runs"]:
            if r["id"] == run_id:
                r.update(values)
                return r
        return None

    async def list_entities(self, code):
        return [e for e in self.store["entities"] if e.get("country_code") == code]

    async def insert_entity(self, row):
        r = {**row, "id": self._id()}
        self.store["entities"].append(r)
        return r

    async def update_entity(self, eid, values):
        for e in self.store["entities"]:
            if e["id"] == eid:
                e.update(values)
                return e
        return None

    async def get_opportunity_by_entity(self, eid):
        return next((o for o in self.store["opps"] if o.get("entity_id") == eid), None)

    async def insert_entity_opportunity(self, row):
        r = {**row, "id": self._id()}
        self.store["opps"].append(r)
        return r

    async def get_entity_by_slug(self, code, slug):
        return next((e for e in self.store["entities"] if e.get("country_code") == code and e.get("slug") == slug), None)

    async def update_entity_opportunity(self, opp_id, values):
        for o in self.store["opps"]:
            if o["id"] == opp_id:
                o.update(values)
                return o
        return None

    async def existing_pain_set(self, eid):
        return {p["pain_name"].lower().strip() for p in self.store["pains"] if p.get("entity_id") == eid}

    async def existing_seed_query_set(self, eid):
        return {q["query"].lower().strip() for q in self.store["queries"] if q.get("entity_id") == eid}

    async def insert_pains(self, rows):
        self.store["pains"].extend(rows)
        return rows

    async def insert_seed_queries(self, rows):
        self.store["queries"].extend(rows)
        return rows

    async def insert_funnel_hypotheses(self, rows):
        self.store["funnels"].extend(rows)
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
                "funnel_hypotheses": [f for f in self.store["funnels"] if f.get("opportunity_id") == o["id"]],
            })
        return out


def test_discovery_persists_dedupes_and_runs_add(monkeypatch):
    _FakeSupa.reset()
    monkeypatch.setattr("app.routers.entities.SupabaseService", _FakeSupa)

    # Run 1
    r1 = client.post("/api/pautador/entities/discovery", json={"country": "Colômbia", "country_code": "CO", "count": 3}).json()
    assert r1["persisted"] is True
    assert r1["created_count"] == 3 and r1["merged_count"] == 0
    assert len(r1["items"]) == 3
    titles = [c["entity"]["canonical_name"] for c in r1["items"]]
    assert "RUT" in titles
    assert len(_FakeSupa.store["entities"]) == 3

    # Run 2 (same country) -> runs ADD but dedup: no new entities, all merged
    r2 = client.post("/api/pautador/entities/discovery", json={"country": "Colômbia", "country_code": "CO", "count": 3}).json()
    assert r2["created_count"] == 0 and r2["merged_count"] == 3
    assert len(_FakeSupa.store["entities"]) == 3  # NO duplicate cards
    assert len(r2["items"]) == 3                   # still 3 cards for the country
    # RUT card title is the entity, and the seed query is preserved (not the title)
    rut = next(c for c in r2["items"] if c["entity"]["canonical_name"] == "RUT")
    assert rut["entity"]["official_source"] == "DIAN"
    qs = [q["query"] for q in rut["seed_queries"]]
    assert qs and "RUT" not in qs


def test_discovery_persist_omits_niche_slug_when_absent(monkeypatch):
    """FIX 1: sem nicho selecionado (default `niches=[]`, comportamento
    diversificado), a entidade não tem `niche_slug` -> a row do insert NÃO deve
    trazer a chave (nem com valor None). Sem a v7_11 aplicada, PostgREST
    rejeitaria qualquer coluna desconhecida, e ISSO derrubaria (502) toda run
    persistida diversificada — inclusive as legadas."""
    _FakeSupa.reset()
    monkeypatch.setattr("app.routers.entities.SupabaseService", _FakeSupa)
    r = client.post("/api/pautador/entities/discovery", json={"country": "Colômbia", "country_code": "CO", "count": 3}).json()
    assert r["persisted"] is True
    assert _FakeSupa.store["entities"]
    for ent in _FakeSupa.store["entities"]:
        assert "niche_slug" not in ent


def test_discovery_persist_includes_niche_slug_when_set(monkeypatch):
    """FIX 1: run opt-in de nicho (niche_slug preenchido pelo mock/LLM) DEVE
    enviar `niche_slug` no insert (essa run exige a v7_11 aplicada, e isso é
    intencional/esperado)."""
    _FakeSupa.reset()
    monkeypatch.setattr("app.routers.entities.SupabaseService", _FakeSupa)
    r = client.post(
        "/api/pautador/entities/discovery",
        json={"country": "Colômbia", "country_code": "CO", "count": 6, "niches": ["financas"]},
    ).json()
    assert r["persisted"] is True
    assert _FakeSupa.store["entities"], "esperava ao menos 1 entidade de nicho financas persistida"
    for ent in _FakeSupa.store["entities"]:
        assert ent.get("niche_slug") == "financas"


def test_discovery_mission_includes_exclusions():
    from app.entities.prompts import build_entity_discovery_mission

    base = build_entity_discovery_mission("Colômbia", count=10)
    assert "NÃO REPITA" not in base  # sem exclusões, sem bloco

    m = build_entity_discovery_mission("Colômbia", count=10, exclude_entities=["RUT", "SOAT", "Mi Casa Ya"])
    assert "NÃO REPITA" in m
    for n in ("RUT", "SOAT", "Mi Casa Ya"):
        assert n in m


def test_manual_entity_creates_in_ready_without_clickup(monkeypatch):
    _FakeSupa.reset()
    monkeypatch.setattr("app.routers.entities.SupabaseService", _FakeSupa)

    resp = client.post("/api/pautador/entities/manual", json={
        "country": "Colômbia", "country_code": "CO", "canonical_name": "SOAT",
        "full_name": "Seguro Obligatorio", "official_source": "RUNT",
    })
    assert resp.status_code == 200
    body = resp.json()
    card = body["card"]
    assert body["already_existed"] is False
    assert card["status"] == "ready" and card["kanban_stage"] == "ready"
    assert card["entity"]["canonical_name"] == "SOAT"
    assert card["entity"]["slug"] == "soat"
    # entidade marcada como manual + status ready
    ent = _FakeSupa.store["entities"][0]
    assert ent["source"] == "manual" and ent["status"] == "ready"

    # criar de novo o mesmo -> dedup (não duplica, marca already_existed)
    resp2 = client.post("/api/pautador/entities/manual", json={
        "country": "Colômbia", "country_code": "CO", "canonical_name": "SOAT",
    })
    assert resp2.json()["already_existed"] is True
    assert len(_FakeSupa.store["entities"]) == 1 and len(_FakeSupa.store["opps"]) == 1


def test_discovery_items_have_estimated_volume(monkeypatch):
    _FakeSupa.reset()
    monkeypatch.setattr("app.routers.entities.SupabaseService", _FakeSupa)
    r = client.post("/api/pautador/entities/discovery", json={"country": "Colômbia", "country_code": "CO", "count": 3}).json()
    # F1: todo card de descoberta traz uma estimativa de volume (numérica) > 0
    assert r["items"]
    assert all(isinstance(c.get("estimated_volume"), int) and c["estimated_volume"] > 0 for c in r["items"])
    # V2 multi-vertical: cada card tem vertical + faixa de eCPM
    assert all(c["entity"].get("vertical") for c in r["items"])
    assert all(c.get("ecpm_band") in ("premium", "medio", "baixo") for c in r["items"])


def test_enrich_manual_entity_creates_discovered_card(monkeypatch):
    _FakeSupa.reset()
    monkeypatch.setattr("app.routers.entities.SupabaseService", _FakeSupa)
    r = client.post("/api/pautador/entities/enrich", json={
        "country": "Colômbia", "country_code": "CO", "canonical_name": "SOAT",
    })
    assert r.status_code == 200
    card = r.json()["card"]
    # F4: entra em 'discovered', já enriquecido pelo agente secundário
    assert card["status"] == "discovered" and card["kanban_stage"] == "discovered"
    assert card["entity"]["canonical_name"] == "SOAT" and card["entity"]["slug"] == "soat"
    assert isinstance(card["estimated_volume"], int) and card["estimated_volume"] > 0
    assert card["entity"].get("vertical") and card.get("ecpm_band")
    assert len(card["pains"]) >= 2 and len(card["seed_queries"]) >= 3
    assert _FakeSupa.store["entities"][0]["source"] == "manual"
