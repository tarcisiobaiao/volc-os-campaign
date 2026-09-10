from copy import deepcopy
from uuid import UUID, uuid4
import pytest
from pydantic import ValidationError

from app.trafego.meta.draft_storage import CampaignDraft, SaveDraft


def draft_fixture():
    return {"recipeId":"TRAFFIC_WEBSITE_LPV_STATIC","accountRef":"metaacct_example","pageRef":"metapage_example",
        "instagramActorRef":"","campaignName":"ABO test","destinationUrl":"https://example.com/",
        "nivelDeOrcamento":"ADSET","periodoDeOrcamento":"DAILY","budgetBrl":"10,00","categoryConfirmed":True,
        "creativeMode":"batch","conjuntos":[{"key":"adset-001","nome":"BR broad","startTime":"2026-09-20T10:00",
          "endTime":"","orcamentoBrl":"10,00","publico":{"modo":"BROAD","geo":{"paisesTexto":"BR",
          "exclusoesTexto":"","pontos":[],"lugares":[]},"idadeMin":18,"idadeMax":65,"incluirRefs":[],"excluirRefs":[],
          "lookalikeRefs":[],"interesseRefs":[],"localeRefs":[],"expansao":False},"posicionamentoModo":"FACEBOOK_ONLY",
          "posicionamentoValores":[],"mensuracao":{"proposito":"REPORT_ONLY","fonteTipo":"","fonteRef":"","conversaoRef":"","eventoPadrao":""}}],
        "variations":[{"key":"variation-001","adsetKey":"adset-001","midia":"image","assetRef":"metaasset_example",
          "videoRef":"","creativeName":"A","adName":"A","message":"Copy text","headline":"Headline","description":"Description",
          "cta":"LEARN_MORE","assetRightsConfirmed":True,"thirdPartyIdentityCleared":True,"assetPolicyConfirmedAt":"2026-09-08T10:00:00Z",
          "packOrigin":{"packId":str(uuid4()),"masterRef":str(uuid4()),"manifestHash":"a"*64,"accountRef":"metaacct_example","selectionVersion":1}}]}


def test_persistence_retains_full_intent_but_clears_authority():
    raw=draft_fixture()
    saved=CampaignDraft.model_validate(raw).persisted()
    assert saved["conjuntos"]==raw["conjuntos"]
    assert saved["variations"][0]["packOrigin"]==raw["variations"][0]["packOrigin"]
    assert saved["variations"][0]["message"]=="Copy text"
    assert saved["categoryConfirmed"] is False
    assert saved["variations"][0]["assetRightsConfirmed"] is False
    assert saved["variations"][0]["assetPolicyConfirmedAt"]==""
    assert raw["categoryConfirmed"] is True


@pytest.mark.parametrize('selection',[None, ''])
def test_empty_or_cleared_regulatory_selection_is_omitted(selection):
    raw=draft_fixture()
    raw['conjuntos'][0]['regulatoryIdentityRef']=selection
    persisted=CampaignDraft.model_validate(raw).persisted()
    assert 'regulatoryIdentityRef' not in persisted['conjuntos'][0]
    assert persisted['conjuntos']==draft_fixture()['conjuntos']


@pytest.mark.parametrize("kind",["token","orphan","duplicate","foreign_pack","oversized","raw_account_id","nested_secret"])
def test_invalid_draft_is_rejected(kind):
    raw=draft_fixture()
    if kind=="token": raw["token"]="secret"
    elif kind=="orphan": raw["variations"][0]["adsetKey"]="missing"
    elif kind=="duplicate": raw["conjuntos"].append(deepcopy(raw["conjuntos"][0]))
    elif kind=="foreign_pack": raw["variations"][0]["packOrigin"]["accountRef"]="metaacct_other"
    elif kind=="oversized": raw["variations"][0]["message"]="x"*2201
    elif kind=="raw_account_id": raw["accountRef"]="1234567890123456"
    elif kind=="nested_secret": raw["variations"][0]["message"]="Bearer "+"a"*50
    with pytest.raises(ValidationError): CampaignDraft.model_validate(raw)


def test_http_rejects_secret_without_echoing_and_scope_comes_from_identity():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers import trafego_meta_drafts as route
    from app.seguranca.identidade import Identidade, exigir_admin
    app=FastAPI(); app.include_router(route.router)
    app.dependency_overrides[exigir_admin]=lambda:Identidade(sub="owner-one",email="a@example.com",papel="ADMIN",origem="sessao")
    seen=[]
    class Repo:
        async def save(self,owner,ref,request):
            seen.append(owner)
            return {"draft_ref":str(ref),"draft":request.draft.persisted(),"version":1,"updated_at":"now","scope":"DRAFT_ONLY","launch_authorized":False}
    app.dependency_overrides[route.storage]=Repo
    client=TestClient(app)
    body={"expected_version":0,"draft":draft_fixture()}
    ref=uuid4()
    response=client.put(f"/api/trafego/meta/drafts/{ref}",json=body)
    assert response.status_code==200,response.text
    assert seen==["owner-one"]
    body["draft"]["token"]="do-not-echo-this-value"
    response=client.put(f"/api/trafego/meta/drafts/{ref}",json=body)
    assert response.status_code==422
    assert "do-not-echo" not in response.text
    assert seen==["owner-one"]


def test_list_filters_owner_paginates_and_returns_only_summary():
    import asyncio
    from app.trafego.meta.draft_storage import DraftStorage
    class Service:
        async def rpc(self, function, params):
            assert function == "trafego_meta_campaign_draft_list"
            assert params == {"p_owner_id":"owner-one","p_offset":20}
            return [{"draft_ref":str(uuid4()), "version":1,"updated_at":"2026-09-09T01:00:00Z",
                     "campaign_name":"ABO test","adset_count":1,"ad_count":1} for _ in range(21)]
    result = asyncio.run(DraftStorage(Service()).list("owner-one",20))
    assert len(result["items"]) == 20 and result["next_offset"] == 40
    assert result["launch_authorized"] is False
    assert result["items"][0]["campaign_name"] == "ABO test"
    assert set(result["items"][0]) == {"draft_ref","version","updated_at","campaign_name","adset_count","ad_count"}


def test_archive_route_uses_session_owner_exact_ref_version_and_refuses_extra_authority():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers import trafego_meta_drafts as route
    from app.seguranca.identidade import Identidade, exigir_admin
    app=FastAPI(); app.include_router(route.router); calls=[]
    app.dependency_overrides[exigir_admin]=lambda:Identidade(sub='owner',email='test@example.com',papel='ADMIN',origem='sessao')
    class Repo:
        async def archive(self,owner,ref,version):
            calls.append((owner,ref,version))
            return {'archived':True,'draft_ref':str(ref),'version':version+1}
    app.dependency_overrides[route.storage]=Repo
    client=TestClient(app); ref=uuid4()
    response=client.request('DELETE',f'/api/trafego/meta/drafts/{ref}',json={'expected_version':4})
    assert response.status_code==200 and calls==[('owner',ref,4)]
    assert client.request('DELETE',f'/api/trafego/meta/drafts/{ref}',json={'expected_version':4,'owner':'someone'}).status_code==422
    assert len(calls)==1


def test_list_route_uses_session_owner_and_does_not_hide_failure_as_empty():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers import trafego_meta_drafts as route
    from app.seguranca.identidade import Identidade, exigir_admin
    import httpx
    app=FastAPI(); app.include_router(route.router)
    app.dependency_overrides[exigir_admin]=lambda:Identidade(sub="owner-one",email="a@example.com",papel="ADMIN",origem="sessao")
    class Repo:
        async def list(self, owner, offset):
            assert owner == "owner-one"
            if offset: raise httpx.ConnectError("private-detail")
            return {"items":[],"has_more":False,"next_offset":None,"scope":"DRAFT_ONLY","launch_authorized":False}
    app.dependency_overrides[route.storage]=Repo
    client=TestClient(app)
    response=client.get("/api/trafego/meta/drafts?owner_id=someone-else")
    assert response.status_code == 200 and response.json()["items"] == []
    assert response.headers["cache-control"] == "no-store"
    response=client.get("/api/trafego/meta/drafts?offset=20")
    assert response.status_code == 503 and "private-detail" not in response.text
    assert client.get("/api/trafego/meta/drafts?offset=-1").status_code == 422


@pytest.mark.parametrize('code',['META_DRAFT_INVALID','META_DRAFT_LINK_INVALID','META_DRAFT_SECRET_FORBIDDEN'])
def test_sql_validation_error_is_actionable_without_private_details(code):
    import asyncio
    import httpx
    from fastapi import HTTPException
    from app.routers.trafego_meta_drafts import reply
    async def failure():
        response=httpx.Response(400,json={'message':code,'details':'private-campaign-content'},
            request=httpx.Request('POST','https://database.agenciavolc.com.br/rest/v1/rpc/test'))
        response.raise_for_status()
    with pytest.raises(HTTPException) as raised:
        asyncio.run(reply(failure()))
    assert raised.value.status_code==422
    assert raised.value.detail['codigo']==code
    assert 'private-campaign-content' not in str(raised.value.detail)
