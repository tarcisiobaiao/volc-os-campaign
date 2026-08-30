import httpx
from funnelforge.adapters.wordpress import WordPressPublisher


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_set_yoast_maps_to_yoast_meta_keys(mocker):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        import json
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"id": 7})

    pub = WordPressPublisher("https://creditoup.com.br", "admin", "tok", client=_client(handler))
    pub.set_yoast(7, "rec", {"title": "T SEO", "metadesc": "desc", "focuskw": "kw"})
    assert seen["url"].endswith("/wp-json/wp/v2/rec/7")
    meta = seen["body"]["meta"]
    assert meta["_yoast_wpseo_title"] == "T SEO"
    assert meta["_yoast_wpseo_metadesc"] == "desc"
    assert meta["_yoast_wpseo_focuskw"] == "kw"
    # the legacy/wrong flat keys are NOT sent
    assert "title" not in meta and "metadesc" not in meta


def test_set_yoast_reasserts_status(mocker):
    """A registered-meta write can flip a draft to publish on some setups, so
    set_yoast pins the status back when given."""
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        import json
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    pub = WordPressPublisher("https://creditoup.com.br", "admin", "tok", client=_client(handler))
    pub.set_yoast(7, "rec", {"metadesc": "d"}, status="draft")
    assert seen["body"]["status"] == "draft"
    assert seen["body"]["meta"]["_yoast_wpseo_metadesc"] == "d"


def test_set_yoast_skips_empty_fields_and_noops(mocker):
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        import json
        calls["n"] += 1
        calls["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    pub = WordPressPublisher("https://creditoup.com.br", "admin", "tok", client=_client(handler))
    # empty values are skipped (never blank an existing Yoast field)
    pub.set_yoast(7, "rec", {"title": "só titulo", "metadesc": "", "focuskw": ""})
    assert calls["body"]["meta"] == {"_yoast_wpseo_title": "só titulo"}
    # all-empty -> no request at all
    pub.set_yoast(7, "rec", {"title": "", "metadesc": "", "focuskw": ""})
    assert calls["n"] == 1


def test_create_post_hits_post_type_endpoint(mocker):
    seen = {}
    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        import json
        seen["body"] = json.loads(req.content)
        return httpx.Response(201, json={"id": 99})
    pub = WordPressPublisher("https://creditoup.com.br", "admin", "tok", client=_client(handler))
    out = pub.create_post("T", "<p>x</p>", "meu-slug", "draft", "rec")
    assert out["id"] == 99
    assert seen["url"].endswith("/wp-json/wp/v2/rec")
    assert seen["body"]["status"] == "draft" and seen["body"]["slug"] == "meu-slug"


def test_create_elementor_page_two_step_and_sanitizes(mocker):
    """Elementor page is written in TWO steps (bare create, then meta update),
    and 4-byte emojis are stripped from `_elementor_data` so a utf8 (non-mb4)
    postmeta column doesn't 500."""
    reqs = []
    def handler(req):
        import json
        body = json.loads(req.content) if req.content else {}
        reqs.append((str(req.url), body))
        return httpx.Response(201, json={"id": 7})
    pub = WordPressPublisher("https://creditoup.com.br", "admin", "tok", client=_client(handler))
    out = pub.create_elementor_page(
        "T", "lp", [{"elType": "container", "settings": {"t": "veja 👉 aqui 👇"}}], "draft",
        page_settings={"hide_title": "yes"})
    assert out["id"] == 7
    # (1) page created BARE -- no protected meta during the INSERT
    assert reqs[0][0].endswith("/pages")
    assert "meta" not in reqs[0][1]
    assert reqs[0][1]["status"] == "draft" and reqs[0][1]["slug"] == "lp"
    # (2) _elementor_data written as an UPDATE on /pages/7
    data_writes = [b for (u, b) in reqs
                   if u.endswith("/pages/7") and "_elementor_data" in b.get("meta", {})]
    assert data_writes, "elementor data was never written as an update"
    written = data_writes[-1]["meta"]["_elementor_data"]
    assert "container" in written
    # (3) 4-byte emojis stripped (utf8 postmeta safety)
    assert "👉" not in written and "👇" not in written
    # (4) edit_mode=builder set somewhere in the sequence
    assert any(b.get("meta", {}).get("_elementor_edit_mode") == "builder" for (u, b) in reqs)
    # (5) Canvas layout requested (no theme header/footer/title)
    assert any(b.get("template") == "elementor_canvas" for (u, b) in reqs)
    # (6) page settings written with hide_title (as an object meta)
    ps_writes = [b["meta"]["_elementor_page_settings"] for (u, b) in reqs
                 if "_elementor_page_settings" in b.get("meta", {})]
    assert ps_writes and ps_writes[-1].get("hide_title") == "yes"
