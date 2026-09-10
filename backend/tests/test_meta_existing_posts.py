from copy import deepcopy
from dataclasses import replace
import json

import httpx
import pytest

from app.trafego.meta import dominio as dom
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao import posts_existentes as posts
from app.trafego.meta_execucao.compilador import compilar_plano_v2, descongelar_plano, TRACKING_GAM_ADSET_ID
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta
from app.trafego.meta_execucao.executor import ExecutorMetaPausado, ErroRemotoMeta
from test_meta_contrato_v2 import _plano_v2, _variacao, _referencias, c2
from test_meta_paused_birth import RegistroEmMemoria, autorizacao, formulario

ACCOUNT = "1234567890"
PAGE = "9876543210"
PAGE_REF = dom.referencia_opaca_objeto(ACCOUNT, "page", PAGE)


def row():
    return {"name":"ABO Descoberta", "creative": {
        "id":"123", "name":"Criativo Descoberta", "effective_object_story_id":PAGE+"_111",
        "image_url":"https://example.com/image.jpg", "object_story_spec": {
            "page_id":PAGE, "link_data": {"image_hash":"hash_da_peca_01", "link":"https://focogenial.com/",
                "message":"mensagem do anuncio", "name":"titulo", "description":"descricao", "call_to_action":{"type":"LEARN_MORE"}}}}}


def flexible_row(*, video=False, links=None):
    feed = {
        "images": [
            {"hash": "hash_feed_quadrado"},
            {"hash": "hash_feed_retrato"},
            {"hash": "hash_feed_story"},
        ],
        "bodies": [{"text": "texto A"}, {"text": "texto B"}],
        "titles": [{"text": "titulo A"}, {"text": "titulo B"}],
        "descriptions": [{"text": "descricao"}],
        "link_urls": [{"website_url": link} for link in (links or ["https://focogenial.com/"])],
        "call_to_action_types": ["LEARN_MORE"],
    }
    if video:
        feed.pop("images")
        feed["videos"] = [{"video_id": "123456789"}]
    return {"name": "ABO Flexível", "creative": {
        "id": "456", "name": "Criativo flexível", "effective_object_story_id": PAGE + "_222",
        "object_story_spec": {"page_id": PAGE}, "asset_feed_spec": feed,
    }}


def compiled_case(**changed):
    variation = _variacao()
    source = posts.normalize(row(), ACCOUNT, PAGE_REF)
    source["asset_ref"] = variation.asset_ref
    variation = replace(variation, existing_post_ref=source["post_ref"], **changed)
    base = _plano_v2()
    plan = replace(base, anuncios=(c2.AnuncioMeta(variacao=variation, adset_key=base.conjuntos[0].adset_key),))
    return plan, source


def test_same_post_is_compiled_with_fresh_tracking_and_correct_adset():
    plan, source = compiled_case()
    compiled = compilar_plano_v2(plan, _referencias(), existing_posts={source["post_ref"]:source})
    creative = next(op for op in compiled.operacoes if op.tipo_objeto == "creative")
    ad = next(op for op in compiled.operacoes if op.tipo_objeto == "ad")
    assert creative.payload["object_story_id"] == PAGE+"_111"
    assert "object_story_spec" not in creative.payload
    assert creative.payload["url_tags"] == TRACKING_GAM_ADSET_ID
    assert ad.payload["adset_id"] == "$adset:"+plan.conjuntos[0].adset_key+".id"
    assert ad.payload["status"] == "PAUSED"
    assert compiled.destino_website_provado
    assert descongelar_plano(compiled.congelar()).plano_sha256 == compiled.plano_sha256


@pytest.mark.parametrize("change", ["missing", "page", "image", "url", "copy"])
def test_unresolved_or_changed_post_cannot_compile(change):
    plan, source = compiled_case(message="edited" if change == "copy" else "mensagem do anuncio")
    if change == "page": source["_page_id"] = "99"
    if change == "image": source["_image_hash"] = "other_hash"
    if change == "url": source["destination_url"] = "https://other.example/"
    catalog = {} if change == "missing" else {source["post_ref"]:source}
    with pytest.raises(ErroDeNascimentoMeta):
        compilar_plano_v2(plan, _referencias(), existing_posts=catalog)


def test_catalog_scopes_page_and_removes_provider_identifiers():
    source = posts.normalize(row(), ACCOUNT, PAGE_REF)
    assert source
    assert posts.normalize(row(), ACCOUNT, "wrong_page") is None
    public = posts.publico({source["post_ref"]:source}, "abo")
    assert public["total"] == 1
    assert not any(key.startswith("_") for key in public["items"][0])
    assert posts.publico({source["post_ref"]:source}, "missing")["total"] == 0
    assert posts.publico({source["post_ref"]:source}, offset=1)["items"] == []


def test_flexible_image_post_is_discoverable_without_flat_link_data():
    source = posts.normalize(flexible_row(), ACCOUNT, PAGE_REF)
    assert source
    assert source["post_ref"] == posts.reference(ACCOUNT, PAGE + "_222")
    assert source["asset_ref"] == posts._image_ref(ACCOUNT, "hash_feed_quadrado")
    assert source["destination_url"] == "https://focogenial.com/"
    assert source["is_flexible"] is True
    assert source["reuse_supported"] is False
    assert source["preview_only"] is True
    assert source["copy_variants"]["messages"] == ["texto A", "texto B"]
    assert source["image_variants"] == 3
    assert source["text_variants"] == 2
    assert source["message"] == "texto A"
    assert source["headline"] == "titulo A"
    assert source["description"] == "descricao"


def test_flexible_discovery_cannot_silently_compile_as_single_post():
    plan, source = compiled_case()
    source["is_flexible"] = True
    with pytest.raises(ErroDeNascimentoMeta) as error:
        compilar_plano_v2(plan, _referencias(), existing_posts={source["post_ref"]:source})
    assert error.value.codigo == "META_FLEXIBLE_POST_REUSE_UNPROVEN"


def test_flexible_post_rejects_video_or_ambiguous_destination():
    assert posts.normalize(flexible_row(video=True), ACCOUNT, PAGE_REF) is None
    assert posts.normalize(flexible_row(links=["https://one.example/", "https://two.example/"]), ACCOUNT, PAGE_REF) is None


@pytest.mark.anyio
async def test_catalog_pages_fixed_graph_host_and_deduplicates_posts(monkeypatch):
    async def account(*args): return ACCOUNT
    monkeypatch.setattr(posts, "_conta_externa", account)
    calls = []
    def graph(request):
        calls.append(request)
        assert request.url.host == "graph.facebook.com"
        if not request.url.params.get("after"):
            return httpx.Response(200, json={"data":[row()], "paging":{"next":"https://evil.example/token", "cursors":{"after":"next"}}})
        item = row(); item["name"] = "CBO Escala"
        return httpx.Response(200, json={"data":[item]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as client:
        catalog = await posts.catalogo(client, "account_ref", PAGE_REF, SegredoEfemero("fake-token"))
    assert len(calls) == 2 and len(catalog) == 1
    assert posts.publico(catalog, "escala")["total"] == 1


@pytest.mark.anyio
async def test_incomplete_catalog_is_not_reported_as_empty(monkeypatch):
    async def account(*args): return ACCOUNT
    monkeypatch.setattr(posts, "_conta_externa", account)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"data":[], "paging":{"next":"more"}}))) as client:
        with pytest.raises(ErroDeNascimentoMeta, match="não terminou"):
            await posts.catalogo(client, "account_ref", PAGE_REF, SegredoEfemero("fake-token"))


def test_readback_requires_original_post_identity():
    payload = {"name":"Creative", "object_story_id":PAGE+"_111"}
    data = {"id":"555", "account_id":ACCOUNT, "name":"Creative", "status":"ACTIVE", "effective_object_story_id":PAGE+"_222"}
    with pytest.raises(ErroRemotoMeta, match="object_story_id"):
        ExecutorMetaPausado._validar_read_back("creative",data,payload=payload,identificador="555",ids={},conta_externa=ACCOUNT)
    data["effective_object_story_id"] = PAGE+"_111"
    ExecutorMetaPausado._validar_read_back("creative",data,payload=payload,identificador="555",ids={},conta_externa=ACCOUNT)


@pytest.mark.anyio
async def test_existing_post_completes_ledger_saga_without_media_upload():
    plan, source = compiled_case()
    compiled = compilar_plano_v2(plan, _referencias(), existing_posts={source["post_ref"]:source})
    objects = {}
    paths = []
    def graph(request):
        if request.method == "GET":
            return httpx.Response(200, json=objects[request.url.path.rsplit("/",1)[-1]])
        paths.append(request.url.path)
        raw = formulario(request)
        if "execution_options" in raw:
            return httpx.Response(200,json={"success":True})
        payload = {}
        for key,value in raw.items():
            try: payload[key] = json.loads(value)
            except ValueError: payload[key] = value
        identifier = str(1000+len(objects))
        payload.update(id=identifier, account_id=ACCOUNT)
        if request.url.path.endswith("/adcreatives"):
            assert "object_story_spec" not in payload
            payload["status"] = "ACTIVE"
            payload["effective_object_story_id"] = payload["object_story_id"]
        if request.url.path.endswith("/ads"):
            payload["campaign_id"] = "1000"
            payload["creative"] = {"id":str(payload["creative"]["creative_id"])}
        objects[identifier] = payload
        return httpx.Response(200,json={"id":identifier})
    ledger = RegistroEmMemoria()
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as client:
        result = await ExecutorMetaPausado(client,registro=ledger).criar_pausada(
            compiled,SegredoEfemero("fake-token"),autorizacao(compiled.plano_sha256))
    assert result.desfecho == "CREATED_PAUSED"
    assert len(objects) == 4
    assert not any("adimages" in path for path in paths)
    assert sum(event == "readback" for event,_ in ledger.eventos) == 4


@pytest.mark.anyio
async def test_search_cache_is_owner_and_credential_bound(monkeypatch):
    calls = []
    async def catalog(*args):
        calls.append(1)
        return {}
    monkeypatch.setattr(posts,"catalogo",catalog)
    monkeypatch.setattr(posts,"_cache",{})
    await posts.catalogo_cached(None,"account","page",SegredoEfemero("one"),owner="owner1")
    await posts.catalogo_cached(None,"account","page",SegredoEfemero("one"),owner="owner1")
    assert len(calls) == 1
    await posts.catalogo_cached(None,"account","page",SegredoEfemero("two"),owner="owner1")
    await posts.catalogo_cached(None,"account","page",SegredoEfemero("one"),owner="owner2")
    assert len(calls) == 3
