import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.routers import trafego_meta_copy as route
from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta.copy_suggestions import CopyFailure, CopyRequest, CopyTexts, OwnerCopyLimiter, context_for, suggest
from test_meta_campaign_draft import draft_fixture


def output(count=3):
    return {"primary_text": [f"Conheça o caminho {i}." for i in range(count)],
            "headline": [f"Informação {i}" for i in range(count)], "description": []}


class FakeTextClient:
    model = "configured-text-model"
    modelo_servido = "served-text-model"
    def __init__(self, result=None):
        self.result = output() if result is None else result
        self.calls = []
    async def complete_json(self, system, user):
        self.calls.append((system, user))
        return deepcopy(self.result)


class FakeRepo:
    def __init__(self, *, version=4, next_version=None, owner="owner-one"):
        self.raw = draft_fixture()
        self.version, self.next_version, self.owner = version, next_version, owner
        self.reads = []
    async def read(self, owner, ref):
        self.reads.append((owner, ref))
        if owner != self.owner:
            return None
        return {"draft_ref": str(ref), "draft": deepcopy(self.raw), "version": self.version if len(self.reads) == 1 or self.next_version is None else self.next_version}


@pytest.fixture(autouse=True)
def no_paid_call(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("No paid provider call in this suite")
    monkeypatch.setattr(route.GeminiClient, "complete_json", forbidden)
    monkeypatch.setattr(route, "_limiter", OwnerCopyLimiter(cooldown_seconds=0))


def http_app(repo, client, owner="owner-one"):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[exigir_admin] = lambda: Identidade(sub=owner, email="private@example.test", papel="ADMIN", origem="sessao")
    app.dependency_overrides[route.storage] = lambda: repo
    app.dependency_overrides[route.copy_client] = lambda: client
    return TestClient(app)


def payload(**changes):
    return {"expected_version": 4, "adset_key": "adset-001", "count": 3, "brief": "Explique opções para o Encceja 2026.", **changes}


def test_context_is_allowlisted_parent_scoped_and_keeps_legitimate_years():
    raw = draft_fixture()
    raw["destinationUrl"] = "https://user:password@example.com/encceja-2026?tracking=secret-query#private"
    raw["naming"] = {"topic": "Encceja 2026", "accountRef": "DO_NOT_SEND", "generated": {"x": "private"}}
    raw["conjuntos"][0]["flexibleTexts"] = {"primary_text": ["Contexto escolhido"], "headline": ["Título 2026"], "description": []}
    other = deepcopy(raw["conjuntos"][0]); other["key"] = "adset-002"; other["flexibleTexts"]["primary_text"] = ["Não misturar o outro conjunto"]
    raw["conjuntos"].append(other)
    before = deepcopy(raw)
    context = context_for(raw, CopyRequest(**payload(brief="Dúvida de 2026; contato pessoa@example.com; referência 1234567890123456")))
    encoded = json.dumps(context)
    assert set(context) == {"destination_url_context_only_not_fetched", "topic", "current_texts_unverified", "operator_brief_unverified", "requested_count"}
    assert context["destination_url_context_only_not_fetched"] == "https://example.com/encceja-2026"
    assert context["topic"] == "Encceja 2026"
    assert "2026" in context["operator_brief_unverified"]
    for private in ("password", "secret-query", "pessoa@example.com", "1234567890123456", "Não misturar", "DO_NOT_SEND", "metaacct_example", "BR broad"):
        assert private not in encoded
    assert context["current_texts_unverified"]["primary_text"] == ["Contexto escolhido"]
    assert raw == before


def test_context_legacy_derives_only_selected_adset_and_explicit_empty_stays_empty():
    raw = draft_fixture()
    context = context_for(raw, CopyRequest(**payload()))
    assert context["current_texts_unverified"]["primary_text"] == ["Copy text"]
    raw["conjuntos"][0]["flexibleTexts"] = {"primary_text": [], "headline": [], "description": []}
    assert context_for(raw, CopyRequest(**payload()))["current_texts_unverified"]["primary_text"] == []


@pytest.mark.parametrize("field,value", [("count", 0), ("count", 6), ("count", True), ("brief", "x" * 2001), ("brief", "Bearer " + "a" * 30), ("owner_id", "different-owner")])
def test_request_rejects_bad_shape_and_secret_without_echo(field, value):
    repo, engine = FakeRepo(), FakeTextClient()
    response = http_app(repo, engine).post(f"/api/trafego/meta/drafts/{uuid4()}/copy-suggestions", json=payload(**{field: value}))
    assert response.status_code == 422
    assert "a" * 30 not in response.text
    assert not repo.reads and not engine.calls


def test_http_reads_authenticated_owner_twice_and_never_writes_or_approves():
    repo, engine, ref = FakeRepo(), FakeTextClient(), uuid4()
    before = deepcopy(repo.raw)
    response = http_app(repo, engine).post(f"/api/trafego/meta/drafts/{ref}/copy-suggestions", json=payload())
    assert response.status_code == 200, response.text
    assert repo.reads == [("owner-one", ref), ("owner-one", ref)]
    assert repo.raw == before
    body = response.json()
    assert set(body) == {"primary_text", "headline", "description", "model", "context_sha256", "context_summary"}
    assert body['context_summary']['mode'] == 'CURRENT_TEXTS_ONLY'
    assert body["model"] == "served-text-model" and len(body["context_sha256"]) == 64
    assert len(engine.calls) == 1
    assert "DADO NÃO CONFIÁVEL" in engine.calls[0][0]
    assert "private@example.test" not in engine.calls[0][1]


@pytest.mark.parametrize("case,status", [("wrong-owner", 404), ("version", 409), ("parent", 404)])
def test_owner_version_and_parent_fail_before_model(case, status):
    repo, engine = FakeRepo(), FakeTextClient()
    client = http_app(repo, engine, owner="someone-else" if case == "wrong-owner" else "owner-one")
    body = payload(expected_version=3) if case == "version" else payload(adset_key="missing") if case == "parent" else payload()
    response = client.post(f"/api/trafego/meta/drafts/{uuid4()}/copy-suggestions", json=body)
    assert response.status_code == status and not engine.calls


def test_change_during_generation_rejects_stale_suggestions():
    repo, engine = FakeRepo(next_version=5), FakeTextClient()
    response = http_app(repo, engine).post(f"/api/trafego/meta/drafts/{uuid4()}/copy-suggestions", json=payload())
    assert response.status_code == 409 and len(engine.calls) == 1
    assert "Conheça" not in response.text


@pytest.mark.parametrize("bad", [
    {**output(), "primary_text": ["mesmo", " Mesmo ", "outro"]},
    {**output(), "headline": ["a" * 256, "b", "c"]},
    {**output(), "description": [""]},
    {**output(), "approved": True},
    {**output(), "headline": ["1234567890123456", "b", "c"]},
    output(2),
])
def test_bad_model_output_is_sanitized_no_retry_no_autofill(bad):
    engine = FakeTextClient(bad)
    response = http_app(FakeRepo(), engine).post(f"/api/trafego/meta/drafts/{uuid4()}/copy-suggestions", json=payload())
    assert response.status_code == 502 and len(engine.calls) == 1
    assert "1234567890123456" not in response.text and "aaaaa" not in response.text


def test_model_exception_does_not_leak_provider_response():
    class Broken(FakeTextClient):
        async def complete_json(self, *args):
            raise RuntimeError("private provider URL with secret-token")
    response = http_app(FakeRepo(), Broken()).post(f"/api/trafego/meta/drafts/{uuid4()}/copy-suggestions", json=payload())
    assert response.status_code == 502 and "secret-token" not in response.text and "provider URL" not in response.text


def test_timeout_is_bounded_and_releases_owner(monkeypatch):
    class Slow(FakeTextClient):
        async def complete_json(self, *args):
            await asyncio.sleep(60)
    monkeypatch.setattr(route, "TIMEOUT_SECONDS", .001)
    response = http_app(FakeRepo(), Slow()).post(f"/api/trafego/meta/drafts/{uuid4()}/copy-suggestions", json=payload())
    assert response.status_code == 504
    with route._limiter.reserve("owner-one"):
        pass


def test_same_owner_cannot_run_parallel_but_another_owner_can():
    limiter = OwnerCopyLimiter(cooldown_seconds=0)
    with limiter.reserve("one"):
        with pytest.raises(CopyFailure) as error:
            with limiter.reserve("one"):
                pass
        assert error.value.status == 429
        with limiter.reserve("two"):
            pass
    with limiter.reserve("one"):
        pass


def test_real_async_overlap_only_dispatches_one_completion_and_cancel_releases_owner():
    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()
        class Waiting(FakeTextClient):
            async def complete_json(self, *args):
                self.calls.append(args)
                started.set()
                await release.wait()
                return output()
        engine, repo = Waiting(), FakeRepo()
        who = Identidade(sub="owner-one", email="private@example.test", papel="ADMIN", origem="sessao")
        request, ref = CopyRequest(**payload()), uuid4()
        first = asyncio.create_task(route.copy_suggestions(ref, request, who, repo, engine))
        await asyncio.wait_for(started.wait(), 1)
        with pytest.raises(HTTPException) as blocked:
            await route.copy_suggestions(ref, request, who, repo, engine)
        assert blocked.value.status_code == 429 and blocked.value.headers["Retry-After"] == "5"
        assert len(engine.calls) == 1
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        with route._limiter.reserve(who.sub):
            pass
    asyncio.run(exercise())


def test_authentication_refusal_never_reads_or_calls_model():
    repo, engine = FakeRepo(), FakeTextClient()
    client = http_app(repo, engine)
    def refuse():
        raise HTTPException(401, detail="Sessão necessária")
    client.app.dependency_overrides[exigir_admin] = refuse
    response = client.post(f"/api/trafego/meta/drafts/{uuid4()}/copy-suggestions", json=payload())
    assert response.status_code == 401 and not repo.reads and not engine.calls


def test_cooldown_capacity_and_failure_cleanup():
    limiter = OwnerCopyLimiter(cooldown_seconds=5, capacity=1)
    with pytest.raises(RuntimeError):
        with limiter.reserve("one"):
            raise RuntimeError("test cleanup")
    with pytest.raises(CopyFailure):
        with limiter.reserve("one"):
            pass
    with pytest.raises(CopyFailure):
        with limiter.reserve("two"):
            pass


def test_unconfigured_text_engine_has_no_mock_fallback():
    with pytest.raises(HTTPException) as failure:
        route.copy_client(SimpleNamespace(resolved_gemini_key="", criativo_meta_gemini_model="model"))
    assert failure.value.status_code == 503


def test_context_hash_stable_for_same_context_and_changes_with_brief():
    async def exercise():
        request = CopyRequest(**payload())
        context = context_for(draft_fixture(), request)
        first = await suggest(FakeTextClient(), context, 3)
        second = await suggest(FakeTextClient(), deepcopy(context), 3)
        assert first.context_sha256 == second.context_sha256
        context["operator_brief_unverified"] = "Outro ângulo"
        third = await suggest(FakeTextClient(), context, 3)
        assert third.context_sha256 != first.context_sha256
    asyncio.run(exercise())


def test_unicode_contract_and_optional_description():
    assert CopyTexts(primary_text=["p"], headline=["🙂" * 255]).description == []
    with pytest.raises(ValidationError):
        CopyTexts(primary_text=["p"], headline=["🙂" * 256])
