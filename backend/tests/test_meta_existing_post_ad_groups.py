"""Hermetic discovery regressions: Ad-level groups must never become static reuse."""
from copy import deepcopy

import httpx
import pytest

from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao import posts_existentes as posts
from app.trafego.meta_execucao.compilador import compilar_plano_v2
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta
from test_meta_existing_posts import row, flexible_row, ACCOUNT, PAGE_REF, compiled_case, _referencias


def grouped_row():
    value = row()
    value["name"] = "Flexível com opções"
    value["creative_asset_groups_spec"] = {"groups": [{
        "images": [{"hash": "hash_da_peca_01"}, {"hash": "hash_da_peca_02"}],
        "texts": [{"text_type": "primary_text", "text": "Mensagem A"},
                  {"text_type": "primary_text", "text": "Mensagem B"},
                  {"text_type": "headline", "text": "Título A"},
                  {"text_type": "headline", "text": "Título B"}],
        "call_to_action": {"type": "LEARN_MORE", "value": {"link": "https://focogenial.com/"}},
    }]}
    return value


def test_ad_groups_are_flexible_preview_not_reusable_fallback():
    source = posts.normalize(grouped_row(), ACCOUNT, PAGE_REF)
    assert source["is_flexible"] and source["preview_only"]
    assert source["reuse_supported"] is False
    assert source["image_variants"] == 2
    assert source["copy_variants"] == {
        "messages": ["Mensagem A", "Mensagem B"],
        "headlines": ["Título A", "Título B"], "descriptions": []}
    assert source["description"] == ""
    plan, _ = compiled_case()
    with pytest.raises(ErroDeNascimentoMeta) as error:
        compilar_plano_v2(plan, _referencias(), existing_posts={source["post_ref"]: source})
    assert error.value.codigo == "META_FLEXIBLE_POST_REUSE_UNPROVEN"


def test_legacy_flexible_without_description_remains_discoverable():
    value = flexible_row()
    del value["creative"]["asset_feed_spec"]["descriptions"]
    source = posts.normalize(value, ACCOUNT, PAGE_REF)
    assert source["description"] == ""
    assert source["copy_variants"]["descriptions"] == []
    assert source["reuse_supported"] is False


def test_compiler_output_round_trips_into_flexible_discovery():
    from test_meta_flexible_images import compile_case
    compiled = compile_case()
    creative = next(op for op in compiled.operacoes if op.tipo_objeto == "creative")
    ad = next(op for op in compiled.operacoes if op.tipo_objeto == "ad")
    value = row()
    value["creative"]["object_story_spec"] = deepcopy(creative.payload["object_story_spec"])
    value["creative_asset_groups_spec"] = deepcopy(ad.payload["creative_asset_groups_spec"])
    source = posts.normalize(value, ACCOUNT, PAGE_REF)
    assert source and source["is_flexible"] and not source["reuse_supported"]
    assert source["copy_variants"]["messages"] == ["Texto 0", "Texto 1", "Texto 2"]


@pytest.mark.parametrize("story", ["malformed", ["malformed"], 1, True])
def test_malformed_story_is_excluded_not_server_error(story):
    value = row()
    value["creative"]["object_story_spec"] = story
    assert posts.normalize(value, ACCOUNT, PAGE_REF) is None


@pytest.mark.parametrize("change", ["video", "bad_image", "bad_text", "bad_type", "no_link", "multi_link", "bad_group", "bad_spec"])
def test_unsupported_groups_never_fall_back_to_static(change):
    value = grouped_row()
    groups = value["creative_asset_groups_spec"]["groups"]
    group = groups[0]
    if change == "video": group["videos"] = [{"video_id": "synthetic"}]
    if change == "bad_image": group["images"] = ["bad"]
    if change == "bad_text": group["texts"] = ["bad"]
    if change == "bad_type": group["texts"][0]["text_type"] = {}
    if change == "no_link": group["call_to_action"]["value"] = {}
    if change == "multi_link":
        groups.append(deepcopy(group))
        groups[1]["call_to_action"]["value"]["link"] = "https://other.example/"
    if change == "bad_group": groups.append("bad")
    if change == "bad_spec": value["creative_asset_groups_spec"] = "bad"
    assert posts.normalize(value, ACCOUNT, PAGE_REF) is None


@pytest.mark.anyio
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("unsupported", [False, True])
async def test_shared_post_dedup_is_conservative_across_pages(monkeypatch, reverse, unsupported):
    async def account(*args): return ACCOUNT
    monkeypatch.setattr(posts, "_conta_externa", account)
    flexible = grouped_row()
    if unsupported:
        flexible["creative_asset_groups_spec"]["groups"][0]["videos"] = [{"video_id": "synthetic"}]
    rows = [row(), flexible]
    if reverse: rows.reverse()
    def handler(request):
        assert "creative_asset_groups_spec" in request.url.params["fields"].split(",creative{")[0]
        if request.url.params.get("after"):
            return httpx.Response(200, json={"data": [rows[1]]})
        return httpx.Response(200, json={"data": [rows[0]], "paging": {
            "next": "https://do-not-follow.example/", "cursors": {"after": "page-two"}}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await posts.catalogo(client, "account_ref", PAGE_REF, SegredoEfemero("test-only"))
    if unsupported:
        assert result == {}
    else:
        assert len(result) == 1
        source = next(iter(result.values()))
        assert source["is_flexible"] and not source["reuse_supported"]
        assert set(source["source_ad_names"]) == {"ABO Descoberta", "Flexível com opções"}
        public = posts.publico(result)["items"][0]
        assert not any(key.startswith("_") for key in public)


def test_page_isolation_and_static_social_proof_unchanged():
    assert posts.normalize(grouped_row(), ACCOUNT, "wrong_page") is None
    source = posts.normalize(row(), ACCOUNT, PAGE_REF)
    assert source["reuse_supported"] and not source["is_flexible"]
    assert source["_post_id"].endswith("_111")


def test_malformed_static_cta_is_excluded_not_server_error():
    value = row()
    value["creative"]["object_story_spec"]["link_data"]["call_to_action"]["type"] = {}
    assert posts.normalize(value, ACCOUNT, PAGE_REF) is None
