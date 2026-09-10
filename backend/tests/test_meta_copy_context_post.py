"""Authorized text-only integration. All model/DB operations are local doubles."""
import asyncio
from copy import deepcopy
import json
from uuid import uuid4

import pytest

from app.routers import trafego_meta_copy as route
from app.trafego.meta.copy_suggestions import CopyResponse, OwnerCopyLimiter
from test_meta_copy_context import GraphFixture
from test_meta_copy_suggestions import FakeTextClient, http_app, payload


class DraftRepo:
    def __init__(self, graph):
        self.service = graph
        self.reads = []
        self.deleted = False
        self.version = 4
    async def read(self, owner, ref):
        self.reads.append((owner, ref))
        if self.deleted or owner != 'owner-one': return None
        return {'draft_ref': str(ref), 'version': self.version, 'draft': deepcopy(self.service.draft)}


@pytest.fixture(autouse=True)
def no_real_provider(monkeypatch):
    async def forbidden(*args, **kwargs): raise AssertionError('No live provider permitted')
    monkeypatch.setattr(route.GeminiClient, 'complete_json', forbidden)
    monkeypatch.setattr(route, '_limiter', OwnerCopyLimiter(cooldown_seconds=0))


def test_post_uses_exact_saved_context_without_manual_brief_no_ids_or_private_records():
    graph, engine = GraphFixture(), FakeTextClient()
    repo = DraftRepo(graph)
    response = http_app(repo, engine).post(f'/api/trafego/meta/drafts/{uuid4()}/copy-suggestions', json=payload(brief=''))
    assert response.status_code == 200, response.text
    assert len(engine.calls) == 1
    context = json.loads(engine.calls[0][1])
    assert context['operator_brief_unverified'] == ''
    saved = context['saved_creative_context'][0]
    assert saved['topic'] == 'Encceja 2026'
    assert saved['facts_from_saved_briefing'] == ['O artigo explica as etapas do exame.']
    assert saved['motivations_hypotheses'][0]['tipo'] == 'desejo'
    assert saved['strategy_hypothesis']['angulo'] == 'Tirar dúvidas'
    assert response.json()['context_summary']['mode'] == 'SAVED_CREATIVE_CONTEXT'
    assert 'selection_stamp' not in context and 'selection_stamp' not in response.json()
    for private in (graph.project, graph.run, graph.pack_id, graph.master_id, 'PRIVATE AUDIENCE', 'UNSELECTED PIECE', 'imagehash123'):
        assert private not in engine.calls[0][1]
    assert 'snapshots textuais salvos' in engine.calls[0][0]
    assert '1–3 frases' in engine.calls[0][0]  # Existing editorial refinement preserved.
    assert len(repo.reads) == 2


@pytest.mark.parametrize('change', ['selection-version', 'selection-removed', 'master-archived', 'pack-revision', 'draft-version', 'draft-deleted'])
def test_post_rechecks_selection_independent_of_draft_version(change):
    graph = GraphFixture(); repo = DraftRepo(graph)
    class ChangeWhileGenerating(FakeTextClient):
        async def complete_json(self, system, user):
            output = await super().complete_json(system, user)
            if change == 'selection-version': graph.selection['version'] += 1
            elif change == 'selection-removed': graph.missing.add('trafego_meta_rascunho_pack')
            elif change == 'master-archived': graph.master['arquivado_em'] = '2026-09-10T00:00:00Z'
            elif change == 'pack-revision': graph.pack['manifest_sha256'] = 'd' * 64
            elif change == 'draft-version': repo.version = 5
            else: repo.deleted = True
            return output
    engine = ChangeWhileGenerating()
    response = http_app(repo, engine).post(f'/api/trafego/meta/drafts/{uuid4()}/copy-suggestions', json=payload())
    assert response.status_code == (404 if change == 'draft-deleted' else 409), response.text
    assert len(engine.calls) == 1
    assert 'Conheça o caminho' not in response.text


def test_wrong_owner_reads_no_context_and_calls_no_model():
    graph, engine = GraphFixture(), FakeTextClient()
    response = http_app(DraftRepo(graph), engine, owner='foreign-owner').post(
        f'/api/trafego/meta/drafts/{uuid4()}/copy-suggestions', json=payload())
    assert response.status_code == 404
    assert not graph.calls and not engine.calls


def test_destination_mismatch_falls_back_with_visible_source_label():
    graph, engine = GraphFixture(), FakeTextClient()
    graph.draft['destinationUrl'] = 'https://example.test/different/'
    response = http_app(DraftRepo(graph), engine).post(f'/api/trafego/meta/drafts/{uuid4()}/copy-suggestions', json=payload(brief=''))
    assert response.status_code == 200
    context = json.loads(engine.calls[0][1])
    assert 'saved_creative_context' not in context
    assert response.json()['context_summary']['mode'] == 'CURRENT_TEXTS_ONLY'
    assert any('destino' in warning for warning in response.json()['context_summary']['warnings'])


def test_entire_request_has_one_deadline_including_context_reads(monkeypatch):
    graph, engine = GraphFixture(), FakeTextClient()
    original = graph.select
    async def slow_read(*args, **kwargs):
        await asyncio.sleep(.05)
        return await original(*args, **kwargs)
    graph.select = slow_read
    monkeypatch.setattr(route, 'TIMEOUT_SECONDS', .01)
    response = http_app(DraftRepo(graph), engine).post(f'/api/trafego/meta/drafts/{uuid4()}/copy-suggestions', json=payload())
    assert response.status_code == 504 and not engine.calls
    with route._limiter.reserve('owner-one'): pass


def test_time_budget_reserves_recheck_and_does_not_retry_provider(monkeypatch):
    graph = GraphFixture()
    class Slow(FakeTextClient):
        async def complete_json(self, system, user):
            self.calls.append((system, user))
            await asyncio.sleep(.1)
    monkeypatch.setattr(route, 'TIMEOUT_SECONDS', .05)
    monkeypatch.setattr(route, 'RECHECK_BUDGET_SECONDS', .02)
    engine = Slow()
    response = http_app(DraftRepo(graph), engine).post(f'/api/trafego/meta/drafts/{uuid4()}/copy-suggestions', json=payload())
    assert response.status_code == 504 and len(engine.calls) == 1
    with route._limiter.reserve('owner-one'): pass


def test_copy_response_legacy_without_context_still_validates():
    assert CopyResponse.model_validate({'primary_text':['A'], 'headline':['B'], 'description':[],
        'model':'test-model', 'context_sha256':'a'*64}).context_summary is None
