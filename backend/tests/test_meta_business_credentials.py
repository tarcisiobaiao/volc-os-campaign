from types import SimpleNamespace
from uuid import uuid4
from copy import deepcopy
import pytest
import httpx
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.routers import meta_business as api
from app.seguranca.identidade import exigir_admin, Identidade
from app.trafego.meta import business_credentials as store

OWNER = str(uuid4())
TOKEN = 'fixture-only-not-a-real-meta-token'
BUSINESS = '123456789'


class Repo:
    def __init__(self): self.rows = []; self.selection = []
    async def select(self, table, params):
        rows = self.selection if table == store.SELECTION else self.rows
        return [deepcopy(r) for r in rows if all(str(r.get(k)) == v[3:] for k, v in params.items() if isinstance(v, str) and v.startswith('eq.'))]
    async def _request(self, method, table, **kwargs):
        row = deepcopy(kwargs['json'])
        if table == store.SELECTION: self.selection = [row]
        else:
            row['id'] = str(uuid4()); self.rows.append(row)
    def _headers(self, *args): return {}
    async def patch(self, table, match, values):
        for row in self.rows:
            if all(str(row.get(k)) == v[3:] for k, v in match.items()): row.update(values)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('VOLC_SEGREDO_KEY', Fernet.generate_key().decode())
    repo = Repo(); app = FastAPI(); app.include_router(api.router)
    app.dependency_overrides[exigir_admin] = lambda: Identidade(sub=OWNER, email='', papel='ADMIN', origem='sessao')
    app.dependency_overrides[api.repo_dependency] = lambda: repo
    async def verify(token, business): assert token == TOKEN and business == BUSINESS
    monkeypatch.setattr(api, 'verify', verify)
    return TestClient(app), repo, app


def save(client):
    return client.post('/api/trafego/meta/business', json={'name': 'Test BM', 'business_id': BUSINESS, 'token': TOKEN})


def test_save_encrypts_and_list_never_returns_secret(setup):
    client, repo, _ = setup
    assert save(client).status_code == 200
    assert TOKEN not in str(repo.rows)
    assert store.unseal(repo.rows[0], OWNER) == TOKEN
    response = client.get('/api/trafego/meta/business')
    assert response.status_code == 200 and 'ciphertext' not in response.text and TOKEN not in response.text
    assert response.json()['selected_id'] is None


def test_invalid_request_does_not_echo_token(setup):
    client, _, _ = setup
    response = client.post('/api/trafego/meta/business', json={'name': 'test', 'business_id': TOKEN, 'token': TOKEN, 'extra': TOKEN})
    assert response.status_code == 422 and TOKEN not in response.text


def test_verification_failure_never_saves(setup, monkeypatch):
    client, repo, _ = setup
    async def fail(*args): raise HTTPException(422, 'No proof')
    monkeypatch.setattr(api, 'verify', fail)
    assert save(client).status_code == 422 and not repo.rows


@pytest.mark.parametrize('tamper', ['owner_id', 'business_id', 'ciphertext', 'enabled'])
def test_ciphertext_is_bound_and_disabled_fails(setup, tamper):
    client, repo, _ = setup; save(client); row = deepcopy(repo.rows[0])
    row[tamper] = False if tamper == 'enabled' else 'tampered'
    with pytest.raises(HTTPException): store.unseal(row, OWNER)


def test_other_owner_cannot_select_or_disable(setup):
    client, repo, _ = setup; save(client); repo.rows[0]['owner_id'] = str(uuid4())
    for operation in ['select', 'disable']:
        assert client.post(f"/api/trafego/meta/business/{repo.rows[0]['id']}/{operation}").status_code == 404


def test_no_admin_no_access(setup):
    client, _, app = setup
    def denied(): raise HTTPException(403, 'Denied')
    app.dependency_overrides[exigir_admin] = denied
    assert save(client).status_code == 403
    assert client.get('/api/trafego/meta/business').status_code == 403


async def test_resolver_selected_connection_no_silent_fallback(setup, monkeypatch):
    client, repo, _ = setup; save(client)
    monkeypatch.setattr(store, 'get_settings', lambda: SimpleNamespace(meta_business_credentials_enabled=True))
    monkeypatch.setattr(store, 'repository', lambda: repo)
    def forbidden(*args): pytest.fail('Keychain fallback')
    identity = SimpleNamespace(sub=OWNER)
    with pytest.raises(HTTPException): await store.credencial_operacional(identity, legado=forbidden)
    ref = repo.rows[0]['id']
    assert client.post(f'/api/trafego/meta/business/{ref}/select').status_code == 200
    assert (await store.credencial_operacional(identity, legado=forbidden)).token == TOKEN
    client.post(f'/api/trafego/meta/business/{ref}/disable')
    with pytest.raises(HTTPException): await store.credencial_operacional(identity, legado=forbidden)


async def test_real_verifier_pagination_does_not_follow_untrusted_next(monkeypatch):
    real_client = httpx.AsyncClient
    calls = []
    def handler(request):
        calls.append(str(request.url))
        assert request.headers['authorization'] == f'Bearer {TOKEN}'
        assert TOKEN not in str(request.url)
        if request.url.path.endswith('/me'): return httpx.Response(200, json={'id': 'system-user'})
        if request.url.params.get('after') == 'next': return httpx.Response(200, json={'data': [{'id': 'system-user'}]})
        return httpx.Response(200, json={'data': [], 'paging': {'next': 'https://evil.invalid/steal', 'cursors': {'after': 'next'}}})
    monkeypatch.setattr(api.httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    await api.verify(TOKEN, BUSINESS)
    assert len(calls) == 3 and all(x.startswith(api.GRAPH) for x in calls)


async def test_real_verifier_does_not_echo_provider_error(monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(api.httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(lambda _: httpx.Response(400, json={'error': TOKEN})), **kw))
    with pytest.raises(HTTPException) as exc: await api.verify(TOKEN, BUSINESS)
    assert TOKEN not in exc.value.detail
