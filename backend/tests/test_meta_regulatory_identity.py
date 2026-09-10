from dataclasses import replace

import httpx
import pytest

from app.trafego.meta_execucao import identidades_regulatorias as reg
from app.trafego.meta_execucao.compilador import compilar_plano_v2
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta
from app.trafego.meta.credenciais import SegredoEfemero
from test_meta_contrato_v2 import _conjunto, _plano_v2, _referencias
from test_meta_v2_readback import _readback_case
from app.trafego.meta_execucao.executor import ExecutorMetaPausado, ErroRemotoMeta


def test_explicit_selection_required_and_hash_bound():
    ref = reg.reference("111", "222", "333")
    original = compilar_plano_v2(_plano_v2(), _referencias())
    assert all("regional_regulation_identities" not in op.payload for op in original.operacoes)
    plan = _plano_v2(conjuntos=(replace(_conjunto(), regulatory_identity_ref=ref),))
    with pytest.raises(ErroDeNascimentoMeta, match="anunciante"):
        compilar_plano_v2(plan, _referencias())
    compiled = compilar_plano_v2(plan, _referencias(), regulatory={ref: {
        "category": "BRAZIL_REGULATION", "identities": {"universal_beneficiary": "222", "universal_payer": "333"}}})
    assert compiled.plano_sha256 != original.plano_sha256
    assert compiled.operacoes[0].payload == original.operacoes[0].payload
    adset = next(op for op in compiled.operacoes if op.tipo_objeto == "adset")
    assert adset.payload["regional_regulated_categories"] == ["BRAZIL_REGULATION"]
    assert adset.payload["regional_regulation_identities"]["universal_payer"] == "333"
    assert adset.payload["status"] == "PAUSED"


def test_draft_keeps_identity_intent_without_launch_approval():
    from app.trafego.meta.draft_storage import Adset
    schema = Adset.model_json_schema()
    assert 'regulatoryIdentityRef' in schema['properties']
    assert 'regulatoryIdentityRef' not in schema['required']


def test_reference_is_account_bound_and_raw_ids_rejected():
    assert reg.reference("111", "222", "333") != reg.reference("999", "222", "333")
    with pytest.raises(ErroDeNascimentoMeta):
        replace(_conjunto(), regulatory_identity_ref="222")
    current = _conjunto()
    foreign = replace(current.publico, geografia=replace(current.publico.geografia, countries=("US",)))
    with pytest.raises(ErroDeNascimentoMeta):
        replace(current, publico=foreign, regulatory_identity_ref=reg.reference("111", "222", "333"))


@pytest.mark.parametrize("field", ["universal_beneficiary", "universal_payer"])
def test_readback_refuses_changed_regulatory_identity(field):
    payload, data = _readback_case()
    payload["regional_regulated_categories"] = ["BRAZIL_REGULATION"]
    payload["regional_regulation_identities"] = {"universal_beneficiary": "222", "universal_payer": "333"}
    data["regional_regulated_categories"] = ["BRAZIL_REGULATION"]
    data["regional_regulation_identities"] = dict(payload["regional_regulation_identities"], **{field: "999"})
    with pytest.raises(ErroRemotoMeta, match="divergiu"):
        ExecutorMetaPausado._validar_read_back("adset", data, payload=payload,
            identificador="1002", ids={"campaign": "1001"}, conta_externa="1234567890")


@pytest.mark.asyncio
async def test_catalog_dedup_pagination_no_ids_or_next_url(monkeypatch):
    async def account(*args):
        return "111"
    monkeypatch.setattr(reg, "_conta_externa", account)
    calls = []
    row = {"name": "Existing", "regional_regulated_categories": ["BRAZIL_REGULATION"],
           "regional_regulation_identities": {"universal_beneficiary": "222", "universal_payer": "333"}}
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [row], **({"paging": {"next": "https://evil.example", "cursors": {"after": "cursor"}}} if len(calls) == 1 else {})})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await reg.catalogo(client, "metaacct_test", SegredoEfemero("test-only-token"))
    public = reg.publico(result)
    assert len(public["items"]) == 1
    assert public["complete"] is True
    assert "identities" not in public["items"][0]
    assert "source_names" not in public["items"][0]
    assert "Existing" not in str(public)
    assert all(request.url.host == "graph.facebook.com" for request in calls)
    assert calls[1].url.params["after"] == "cursor"


@pytest.mark.asyncio
async def test_incomplete_catalog_refuses_instead_of_partial_selection(monkeypatch):
    async def account(*args): return "111"
    monkeypatch.setattr(reg, "_conta_externa", account)
    def handler(request):
        return httpx.Response(200, json={"data": [], "paging": {"next": "next", "cursors": {"after": "same"}}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ErroDeNascimentoMeta, match="não chegou"):
            await reg.catalogo(client, "metaacct_test", SegredoEfemero("test-only-token"))


@pytest.mark.asyncio
async def test_public_names_come_from_identity_not_campaign_or_business(monkeypatch):
    async def account(*args): return "111"
    monkeypatch.setattr(reg, "_conta_externa", account)
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/adsets'):
            return httpx.Response(200, json={"data": [{"name": "Unrelated campaign name",
                "regional_regulated_categories": ["BRAZIL_REGULATION"],
                "regional_regulation_identities": {"universal_beneficiary": "222", "universal_payer": "333"}}]})
        return httpx.Response(200, json={"name": "Advertiser" if request.url.path.endswith('/222') else "Payer"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await reg.consultar_publico(client, 'metaacct_test', SegredoEfemero('test-only-token'))
    item = result['items'][0]
    assert item['beneficiary_name'] == 'Advertiser'
    assert item['payer_name'] == 'Payer'
    assert item['names_available'] is True
    assert 'Unrelated campaign' not in str(result)
    assert 'identities' not in item and 'source_names' not in item
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_name_unavailable_does_not_fabricate_verified_business(monkeypatch):
    ref = reg.reference('111', '222', '222')
    async def catalog(*args): return {ref: {'category': 'BRAZIL_REGULATION',
        'identities': {'universal_beneficiary': '222', 'universal_payer': '222'}, 'source_names': ['Private']}}
    monkeypatch.setattr(reg, 'catalogo', catalog)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(403, json={'error': {'message': 'private error'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await reg.consultar_publico(client, 'metaacct_test', SegredoEfemero('test-only-token'))
    assert len(calls) == 1
    assert result['items'][0]['beneficiary_name'] is None
    assert result['items'][0]['names_available'] is False
    assert 'private' not in str(result).lower()
