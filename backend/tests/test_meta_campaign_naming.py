"""Naming intent and account-scoped history: no real token or Meta writes."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.trafego.meta import naming, dominio as dom
from app.trafego.meta.adaptador import AdaptadorMetaSomenteLeitura, ErroDeLeituraMeta
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta.draft_storage import CampaignDraft, NamingDraft
from app.routers import trafego_meta_naming as route
from app.seguranca.identidade import exigir_admin
from test_meta_campaign_draft import draft_fixture
from test_meta_real_read_model import ClienteGraphFake, pagina, TOKEN


def naming_fixture():
    return {'enabled': True, 'topic': 'Notícia', 'site': 'Portal', 'landingType': 'LP_R',
            'quiz': False, 'conversionLabel': 'ViewContent', 'adsetNumbers': {'set-1': 1},
            'adNumbers': {'set-1:ad-1': 1}, 'generated': {'campaign': '0001 - Notícia'}}


@pytest.mark.parametrize('text,expected', [('0001 - Tema', 1), ('CP0035_CJ001', 35), ('CP0008', 8),
    (' cp0022 | LP_R', 22), ('12345 — Tema', 12345), ('Tema CP1234', None),
    ('2026 notícias', None), ('Texto', None), ('CP123abc', None), ('0000 - Teste', 0)])
def test_historical_prefixes_are_anchored(text, expected):
    assert naming.number_from_name(text) == expected


def test_range_exhausted_not_ignored():
    with pytest.raises(ErroDeLeituraMeta, match='faixa'):
        naming.number_from_name('CP99999999999999999999999 - Tema')


def test_history_reads_all_pages_statuses_and_global_topics_without_export():
    fake = ClienteGraphFake({'campaigns': [pagina([
        {'id': '1', 'name': '0003 - Tema A'}, {'id': '2', 'name': 'Outro nome'}], after='next'),
        pagina([{'id': '3', 'name': 'CP0088_LP_R'}])]})
    result = asyncio.run(naming.read_campaign_history(AdaptadorMetaSomenteLeitura(fake), '123', SegredoEfemero(TOKEN)))
    assert (result.maximum, result.count, result.complete) == (88, 3, True)
    assert len(fake.chamadas) == 2
    assert all(c['params']['fields'] == 'id,name' for c in fake.chamadas)
    assert 'DELETED' in fake.chamadas[0]['params']['effective_status']
    assert fake.chamadas[1]['params']['after'] == 'next'
    assert not hasattr(result, 'names')


def test_partial_page_ceiling_never_provides_bootstrap_number():
    fake = ClienteGraphFake({'campaigns': [pagina([{'id': '1', 'name': '0003 - Tema A'}], after='next')]})
    with pytest.raises(ErroDeLeituraMeta, match='paginas'):
        asyncio.run(naming.read_campaign_history(AdaptadorMetaSomenteLeitura(fake, max_paginas_por_edge=1), '123', SegredoEfemero(TOKEN)))


@pytest.mark.parametrize('rows', [[{'id': '1', 'name': '0001 - A'}, {'id': '1', 'name': 'CP0002'}],
    [{'id': '1'}], [{'id': 'bad', 'name': '0001 - A'}]])
def test_malformed_or_duplicated_history_never_bootstraps(rows):
    fake = ClienteGraphFake({'campaigns': [pagina(rows)]})
    with pytest.raises(ErroDeLeituraMeta):
        asyncio.run(naming.read_campaign_history(AdaptadorMetaSomenteLeitura(fake), '123', SegredoEfemero(TOKEN)))


def test_account_resolver_denies_before_campaign_history():
    fake = ClienteGraphFake({'adaccounts': [pagina([{'id': '123', 'name': 'Account', 'currency': 'BRL', 'timezone_name': 'UTC'}])]})
    with pytest.raises(ErroDeLeituraMeta, match='conta'):
        asyncio.run(naming.resolved_history(dom.referencia_opaca_conta('999'), SegredoEfemero(TOKEN), client=fake))
    assert len(fake.chamadas) == 1 and fake.chamadas[0]['url'].endswith('/me/adaccounts')


def test_naming_draft_roundtrip_and_legacy_omission():
    raw = draft_fixture()
    assert 'naming' not in CampaignDraft.model_validate(raw).persisted()
    raw['naming'] = naming_fixture()
    saved = CampaignDraft.model_validate(raw).persisted()
    assert saved['naming'] == raw['naming']
    assert saved['categoryConfirmed'] is False
    assert CampaignDraft.model_validate(saved).persisted() == saved


@pytest.mark.parametrize('field,value', [('topic', 'x'*201), ('site', 'x'*81), ('landingType', 'x'*41),
    ('campaignNumber', 0), ('campaignNumber', True), ('accountRef', ''), ('enabled', 1),
    ('adNumbers', {'set-1:ad-1': 0}), ('adsetNumbers', {'bad key': 1}),
    ('generated', {'campaign': 'x'*401}), ('generated', {str(i): '' for i in range(101)})])
def test_naming_shape_limits(field, value):
    raw = naming_fixture()
    raw[field] = value
    with pytest.raises(ValidationError):
        NamingDraft.model_validate(raw)


def endpoint(monkeypatch, *, version=1, history_complete=True):
    account = '123'
    ref = uuid4()
    raw = draft_fixture()
    raw['accountRef'] = dom.referencia_opaca_conta(account)
    raw['variations'][0].pop('packOrigin')
    calls = []
    class Repo:
        service = None
        async def read(self, owner, draft):
            calls.append('read')
            assert owner == 'owner-one' and draft == ref
            return {'draft': deepcopy(raw), 'version': version}
        async def rpc(self, function, params):
            calls.append('reserve')
            assert function == 'trafego_meta_campaign_naming_reserve'
            assert params['p_owner_id'] == 'owner-one' and params['p_account_id'] == account
            return {'draft_ref': str(ref), 'campaign_number': 36, 'account_ref': raw['accountRef'],
                    'history_complete': True, 'history_count': 2}
    repo = Repo()
    repo.service = repo
    async def credential(*args, **kwargs):
        calls.append('credential')
        return SimpleNamespace(token=TOKEN)
    async def history(*args, **kwargs):
        calls.append('history')
        return SimpleNamespace(id_externo=account), naming.CampaignHistory(35, 2, history_complete)
    monkeypatch.setattr(route, 'credencial_operacional', credential)
    monkeypatch.setattr(route, 'resolved_history', history)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[exigir_admin] = lambda: SimpleNamespace(sub='owner-one')
    app.dependency_overrides[route.storage] = lambda: repo
    return TestClient(app), ref, calls


def test_reservation_endpoint_uses_stored_account_and_never_exposes_raw_id(monkeypatch):
    client, ref, calls = endpoint(monkeypatch)
    response = client.post(f'/api/trafego/meta/drafts/{ref}/naming-reservation', json={'expected_version': 1})
    assert response.status_code == 200 and response.json()['campaign_number'] == 36
    assert set(response.json()) == {'campaign_number','account_ref','draft_ref','history_complete','history_count'}
    assert calls == ['read', 'credential', 'history', 'reserve']


def test_stale_version_no_credentials_no_history_no_reservation(monkeypatch):
    client, ref, calls = endpoint(monkeypatch, version=2)
    response = client.post(f'/api/trafego/meta/drafts/{ref}/naming-reservation', json={'expected_version': 1})
    assert response.status_code == 409 and calls == ['read']


def test_partial_history_never_calls_reservation_rpc(monkeypatch):
    client, ref, calls = endpoint(monkeypatch, history_complete=False)
    response = client.post(f'/api/trafego/meta/drafts/{ref}/naming-reservation', json={'expected_version': 1})
    assert response.status_code == 409 and 'reserve' not in calls


def test_client_cannot_submit_account_id_or_desired_number(monkeypatch):
    client, ref, calls = endpoint(monkeypatch)
    response = client.post(f'/api/trafego/meta/drafts/{ref}/naming-reservation', json={
        'expected_version': 1, 'account_id': '999', 'campaign_number': 123})
    assert response.status_code == 422 and calls == []
