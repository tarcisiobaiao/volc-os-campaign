import json
from types import SimpleNamespace

from funnelforge.config.settings import load_settings
from funnelforge.domain.models import Page, PageDraft, RunState
from funnelforge.pipeline.steps import step_publish

from tests.lp_conforme import conteudo_da_lp


class _FakePublisher:
    """Captures the status/args step_publish sends, and serves a hosted URL
    from upload_media so the hero-rewrite path can be asserted."""

    def __init__(self):
        self.page_call = None
        self.post_call = None
        self.uploaded = []

    def create_elementor_page(self, title, slug, elementor, status, post_type="pages",
                              page_settings=None):
        self.page_call = {"status": status, "elementor": elementor, "slug": slug,
                          "post_type": post_type, "page_settings": page_settings}
        return {"id": 1}

    def create_post(self, title, content, slug, status, post_type, featured_media=None):
        self.post_call = {"status": status, "post_type": post_type, "slug": slug,
                          "featured_media": featured_media, "content": content}
        return {"id": 2}

    def upload_media(self, data, filename, mime, alt=""):
        self.uploaded.append(filename)
        return {"id": 99, "source_url": "https://creditoup.com.br/wp-content/uploads/hero.webp",
                "alt_text": alt}

    def set_yoast(self, post_id, post_type, fields, status=None):
        self.yoast_call = {"post_type": post_type, "fields": fields, "status": status}
        return {}

    def set_status(self, post_id, post_type, status):
        self.status_pin = {"post_id": post_id, "post_type": post_type, "status": status}
        return {}


def _deps(tmp_path, config_files, publisher, publish_status=None):
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    if publish_status is not None:
        settings.run.publish_status = publish_status
    runner = SimpleNamespace(runs_dir=tmp_path / "runs")
    return SimpleNamespace(publisher=publisher, settings=settings, runner=runner)


def test_publish_status_defaults_to_draft_for_interior_post(tmp_path, config_files):
    """Default run.publish_status is 'draft' -> an interior page is created as
    a WordPress draft, not published live (the n8n-style review flow)."""
    pub = _FakePublisher()
    deps = _deps(tmp_path, config_files, pub)
    assert deps.settings.run.publish_status == "draft"
    state = RunState(run_id="r1")
    state.drafts[2] = PageDraft(page_number=2, page_type="SOLUTION",
                                format="gutenberg", content="<p>x</p>")
    page = Page(page_number=2, page_type="SOLUTION", h1_title="T", slug="quem-tem-direito-pr")
    step_publish(state, page, deps)
    assert pub.post_call is not None and pub.post_call["status"] == "draft"


def test_publish_status_publish_when_configured(tmp_path, config_files):
    """Setting run.publish_status='publish' opts into an automated go-live."""
    pub = _FakePublisher()
    deps = _deps(tmp_path, config_files, pub, publish_status="publish")
    state = RunState(run_id="r1")
    state.drafts[2] = PageDraft(page_number=2, page_type="SOLUTION",
                                format="gutenberg", content="<p>x</p>")
    page = Page(page_number=2, page_type="SOLUTION", h1_title="T", slug="x-pr")
    step_publish(state, page, deps)
    assert pub.post_call["status"] == "publish"


def test_interior_post_gets_featured_image_and_midcontent(tmp_path, config_files):
    """When an image was generated for an interior /rec post, publish uploads
    it, sets it as featured_media (the thumbnail), and injects a mid-content
    wp:image right after the first heading -- the n8n-style flow."""
    pub = _FakePublisher()
    deps = _deps(tmp_path, config_files, pub)
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    img = run_dir / "p2.webp"
    img.write_bytes(b"fake-webp")
    state = RunState(run_id="r1")
    content = ('<!-- wp:heading --><h2>Intro</h2><!-- /wp:heading -->\n'
               '<!-- wp:paragraph --><p>corpo</p><!-- /wp:paragraph -->')
    state.drafts[2] = PageDraft(page_number=2, page_type="SOLUTION",
                                format="gutenberg", content=content)
    state.images[2] = str(img)
    state.seo[2] = {"seotitle": "Titulo", "keywordfocus": "consultar fgts"}
    page = Page(page_number=2, page_type="SOLUTION", h1_title="T", slug="x-p1")
    step_publish(state, page, deps)
    assert pub.uploaded == ["p2.webp"]
    assert pub.post_call["featured_media"] == 99
    body = pub.post_call["content"]
    assert "wp:image" in body
    assert "wp-content/uploads/hero.webp" in body
    # inserted AFTER the first heading, not before it
    assert body.index("wp:image") > body.index("Intro")


def test_midcontent_image_wrapped_in_spacers():
    """The mid-content image gets a spacer above and below so it never sits
    flush against the heading or a CTA stack (AdSense-safe spacing)."""
    from funnelforge.pipeline.steps import _insert_midcontent_image
    html = ('<!-- wp:heading --><h2>Intro</h2><!-- /wp:heading -->'
            '<!-- wp:buttons --><div class="wp-block-buttons"></div><!-- /wp:buttons -->')
    out = _insert_midcontent_image(html, "https://creditoup.com.br/i.webp", "alt")
    img_i = out.index("wp:image")
    assert "wp:spacer" in out[:img_i][out[:img_i].rindex("/wp:heading"):]
    assert "wp:spacer" in out[out.index("/wp:image"):]


def test_interior_post_without_image_stays_textonly(tmp_path, config_files):
    """No generated image -> no upload, featured_media stays None, and content
    is unchanged (a text-only post still publishes)."""
    pub = _FakePublisher()
    deps = _deps(tmp_path, config_files, pub)
    state = RunState(run_id="r1")
    content = '<!-- wp:heading --><h2>Intro</h2><!-- /wp:heading --><p>x</p>'
    state.drafts[2] = PageDraft(page_number=2, page_type="SOLUTION",
                                format="gutenberg", content=content)
    page = Page(page_number=2, page_type="SOLUTION", h1_title="T", slug="x-p1")
    step_publish(state, page, deps)
    assert pub.uploaded == []
    assert pub.post_call["featured_media"] is None
    assert "wp:image" not in pub.post_call["content"]


def test_lp_published_as_draft_with_hero_uploaded_and_rewritten(tmp_path, config_files):
    """The LP is created as a draft AND its local hero .webp is uploaded to WP
    media, with the Elementor image URL rewritten to the hosted URL (so the
    draft isn't left pointing at a meaningless local path)."""
    pub = _FakePublisher()
    deps = _deps(tmp_path, config_files, pub)
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    elementor = [{"elType": "container", "elements": [
        {"widgetType": "image", "settings": {"image": {"url": "runs/r1/p1.webp"}}}]}]
    (run_dir / "p1.elementor.json").write_text(json.dumps(elementor), encoding="utf-8")
    (run_dir / "p1.page_settings.json").write_text(
        json.dumps({"hide_title": "yes"}), encoding="utf-8")
    hero = run_dir / "p1.webp"
    hero.write_bytes(b"fake-webp-bytes")
    state = RunState(run_id="r1")
    # ⚠️ ARTEFATO CONFORME, e não mais `content="markers"`.
    #
    # A LP deixou de ser isenta do portão de conteúdo: `step_publish` roda o
    # portão do destino pago ANTES de qualquer `upload_media`. Um rascunho de
    # brinquedo agora reprova por conteúdo insuficiente e nunca chega à mecânica
    # de herói/status que este teste mede -- que é exatamente o efeito
    # pretendido, e o motivo de a fixture precisar ser uma LP de verdade.
    state.drafts[1] = PageDraft(page_number=1, page_type="LANDING PAGE",
                                format="lp_json",
                                content=json.dumps(conteudo_da_lp(), ensure_ascii=False))
    state.images[1] = str(hero)
    page = Page(page_number=1, page_type="LANDING PAGE", h1_title="T", slug="antecipacao")
    step_publish(state, page, deps)
    assert pub.page_call["status"] == "draft"
    assert pub.uploaded == ["p1.webp"]
    img_url = pub.page_call["elementor"][0]["elements"][0]["settings"]["image"]["url"]
    assert img_url == "https://creditoup.com.br/wp-content/uploads/hero.webp"
    # the LAST write pins the status (guards against meta-write publish flips)
    assert pub.status_pin["status"] == "draft"
    assert pub.status_pin["post_type"] == deps.settings.site.lp_post_type
    # page settings (hide_title etc.) are forwarded to the publisher
    assert pub.page_call["page_settings"] == {"hide_title": "yes"}


def test_lp_publish_survives_missing_hero(tmp_path, config_files):
    """Hero upload is non-fatal: with no local image recorded, the LP still
    publishes (as a draft) without raising or calling upload_media."""
    pub = _FakePublisher()
    deps = _deps(tmp_path, config_files, pub)
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    elementor = [{"elType": "container", "elements": []}]
    (run_dir / "p1.elementor.json").write_text(json.dumps(elementor), encoding="utf-8")
    state = RunState(run_id="r1")
    # ⚠️ ARTEFATO CONFORME, e não mais `content="markers"`.
    #
    # A LP deixou de ser isenta do portão de conteúdo: `step_publish` roda o
    # portão do destino pago ANTES de qualquer `upload_media`. Um rascunho de
    # brinquedo agora reprova por conteúdo insuficiente e nunca chega à mecânica
    # de herói/status que este teste mede -- que é exatamente o efeito
    # pretendido, e o motivo de a fixture precisar ser uma LP de verdade.
    state.drafts[1] = PageDraft(page_number=1, page_type="LANDING PAGE",
                                format="lp_json",
                                content=json.dumps(conteudo_da_lp(), ensure_ascii=False))
    page = Page(page_number=1, page_type="LANDING PAGE", h1_title="T", slug="antecipacao")
    step_publish(state, page, deps)
    assert pub.page_call["status"] == "draft"
    assert pub.uploaded == []
