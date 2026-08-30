# funnel-forge/tests/test_step_screenshot.py
"""CARD-0005: real screenshots of the official destination pages on SOLUTION
pages. A Playwright/Chromium adapter captures each `official_link` (mobile
viewport, above the fold), deterministic crop + webp compression, and at publish
the image is uploaded to WP media and embedded right after the paragraph that
links to that official URL, with a reproduction caption -- all best-effort, and
NEVER able to fail a good page.

No network / no playwright here: a FakeScreenshotProvider serves fixed PNG bytes
and the adapter's https guard is exercised before its lazy playwright import (so
this whole suite is green in an environment without playwright).

NÃO EXISTE MAIS ALLOWLIST DE HOSTS. Quem autoriza uma URL externa é a PESQUISA
daquela página: `registrar_canais_oficiais` decide uma vez (proveniência +
verificação no Chromium + sonda anti-anúncio) e guarda em `state.official_links`
-- é dali que o print sai. O adapter, por consequência, exige só https."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from funnelforge.adapters.images_pillow import PillowImageProcessor
from funnelforge.config.settings import (
    RunConfig,
    Secrets,
    Settings,
    SiteConfig,
    load_settings,
)
from funnelforge.domain.models import (
    FunnelPlan,
    Page,
    PageDraft,
    PageRole,
    ResearchFacts,
    RunState,
    StepResult,
    StepStatus,
)
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.pipeline import Deps, run_pipeline
from funnelforge.pipeline.runner import Runner
from tests.fakes import FakeLLM, FakeScreenshotProvider, png_bytes


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _settings(*, official_screenshots: bool = True, cap: int = 2) -> Settings:
    # `site` não carrega mais lista de hosts autorizados: o canal oficial é um
    # fato da pesquisa de cada página, não da configuração da instalação.
    return Settings(
        secrets=Secrets(),
        run=RunConfig(official_screenshots=official_screenshots,
                      screenshots_max_per_page=cap),
        site=SiteConfig(domain="https://creditoup.com.br"),
        steps={},
    )


def _solution_page(ordinal: int = 1) -> Page:
    return Page(page_number=3, page_type="SOLUTION", h1_title="Atualizar cadastro",
                slug="atualizar-cadastro-p1", ordinal=ordinal, role=PageRole.SOLUTION)


def _deps(tmp_path: Path, settings: Settings, provider) -> Deps:
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    return Deps(llm=runner.llm, research=None, image_gen=None,
                image_proc=PillowImageProcessor(), publisher=None, loader=None,
                settings=settings, runner=runner, screenshot=provider)


# --------------------------------------------------------------------------- #
# step_screenshot: capture, naming, state
# --------------------------------------------------------------------------- #
def test_step_screenshot_captures_names_and_records(tmp_path: Path) -> None:
    deps = _deps(tmp_path, _settings(), FakeScreenshotProvider())
    state = RunState(run_id="atualizar-cadastro-p1-20260720")
    state.facts[3] = ResearchFacts(fontes=[
        "https://meu.inss.gov.br/atualizacao-cadastral",
        "https://www.gov.br/inss/pt-br/servico",
    ])

    st.step_screenshot(state, _solution_page(), deps)

    assert state.step_status["screenshot_p3"].status is StepStatus.OK
    shots = state.screenshots[3]
    assert [s["url"] for s in shots] == [
        "https://meu.inss.gov.br/atualizacao-cadastral",
        "https://www.gov.br/inss/pt-br/servico",
    ]
    # p{n}-oficial-{host-sem-pontos}-{k}.webp, in the run dir, really written
    assert [Path(s["path"]).name for s in shots] == [
        "p3-oficial-meuinssgovbr-1.webp",
        "p3-oficial-wwwgovbr-2.webp",
    ]
    for s in shots:
        assert Path(s["path"]).exists()
    assert deps.screenshot.captured == [
        "https://meu.inss.gov.br/atualizacao-cadastral",
        "https://www.gov.br/inss/pt-br/servico",
    ]


def test_step_screenshot_caps_per_page(tmp_path: Path) -> None:
    deps = _deps(tmp_path, _settings(cap=1), FakeScreenshotProvider())
    state = RunState(run_id="r")
    state.facts[3] = ResearchFacts(fontes=[
        "https://meu.inss.gov.br/a",
        "https://www.gov.br/b",
        "https://www.caixa.gov.br/c",
    ])

    st.step_screenshot(state, _solution_page(), deps)

    assert len(deps.screenshot.captured) == 1
    assert len(state.screenshots[3]) == 1


# --------------------------------------------------------------------------- #
# step_screenshot: gating (flag / role / provider) -> silent no-op
# --------------------------------------------------------------------------- #
def test_step_screenshot_noop_when_flag_off(tmp_path: Path) -> None:
    deps = _deps(tmp_path, _settings(official_screenshots=False), FakeScreenshotProvider())
    state = RunState(run_id="r")
    state.facts[3] = ResearchFacts(fontes=["https://meu.inss.gov.br/x"])

    st.step_screenshot(state, _solution_page(), deps)

    assert deps.screenshot.captured == []
    assert 3 not in state.screenshots
    assert "screenshot_p3" not in state.step_status  # gated -> nothing recorded


def test_step_screenshot_noop_for_non_solution_role(tmp_path: Path) -> None:
    deps = _deps(tmp_path, _settings(), FakeScreenshotProvider())
    state = RunState(run_id="r")
    presell = Page(page_number=2, page_type="PRESELL", h1_title="Quem tem direito",
                   slug="quem-tem-direito-pr", role=PageRole.PRESELL)
    state.facts[2] = ResearchFacts(fontes=["https://meu.inss.gov.br/x"])

    st.step_screenshot(state, presell, deps)

    assert deps.screenshot.captured == []
    assert 2 not in state.screenshots
    assert "screenshot_p2" not in state.step_status


def test_step_screenshot_noop_when_provider_none(tmp_path: Path) -> None:
    """Flag on but no provider wired (playwright absent) -> pure no-op."""
    deps = _deps(tmp_path, _settings(), provider=None)
    state = RunState(run_id="r")
    state.facts[3] = ResearchFacts(fontes=["https://meu.inss.gov.br/x"])

    st.step_screenshot(state, _solution_page(), deps)

    assert 3 not in state.screenshots
    assert "screenshot_p3" not in state.step_status


# --------------------------------------------------------------------------- #
# step_screenshot: best-effort failure + origem da autorização (a pesquisa)
# --------------------------------------------------------------------------- #
def test_step_screenshot_provider_failure_is_skipped_never_fatal(tmp_path: Path) -> None:
    """A provider that raises must not propagate: the step is SKIPPED (never
    FAILED), no screenshots are recorded, and the page proceeds to build/
    publish (same contract as step_image)."""
    deps = _deps(tmp_path, _settings(), FakeScreenshotProvider(fail=True))
    state = RunState(run_id="r")
    state.facts[3] = ResearchFacts(fontes=["https://meu.inss.gov.br/x"])

    st.step_screenshot(state, _solution_page(), deps)  # must not raise

    res = state.step_status["screenshot_p3"]
    assert res.status is StepStatus.SKIPPED
    assert res.status is not StepStatus.FAILED
    assert any(i.code == "screenshot_skipped" for i in res.issues)
    assert 3 not in state.screenshots


def test_step_screenshot_so_captura_canal_escolhido(tmp_path: Path) -> None:
    """O print sai de `state.official_links` -- a escolha que a PESQUISA daquela
    página fez (`registrar_canais_oficiais`: proveniência + Chromium + sonda
    anti-anúncio) -- e de mais nada. Uma URL que a pesquisa citou mas que NÃO
    entrou nessa escolha (aqui, o portal concorrente reprovado pela sonda) nunca
    vira print, mesmo estando em `facts.fontes`.

    Repare no host escolhido: `entregador.ifood.com.br` jamais estaria numa
    allowlist de tema governamental -- é exatamente o funil que a lista quebrava.
    """
    deps = _deps(tmp_path, _settings(), FakeScreenshotProvider())
    state = RunState(run_id="r")
    state.facts[3] = ResearchFacts(fontes=[
        "https://entregador.ifood.com.br/cadastro",
        "https://portal-concorrente.example.com/fgts",
    ])
    state.official_links[3] = ["https://entregador.ifood.com.br/cadastro"]

    st.step_screenshot(state, _solution_page(), deps)

    assert deps.screenshot.captured == ["https://entregador.ifood.com.br/cadastro"]
    assert [s["url"] for s in state.screenshots[3]] == [
        "https://entregador.ifood.com.br/cadastro"]
    assert all("portal-concorrente" not in s["url"] for s in state.screenshots[3])


# --------------------------------------------------------------------------- #
# B3: validity guards (status/error) + blank/under-render guard + retry 1x
# --------------------------------------------------------------------------- #
def test_step_screenshot_rejects_non_200_status(tmp_path: Path) -> None:
    """A capture whose navigation returned a non-200 status is rejected: the URL
    yields no embedded print (nothing recorded for that page) and the step never
    fails a good page."""
    deps = _deps(tmp_path, _settings(cap=1), FakeScreenshotProvider(status=500))
    state = RunState(run_id="r")
    state.facts[3] = ResearchFacts(fontes=["https://meu.inss.gov.br/x"])

    st.step_screenshot(state, _solution_page(), deps)

    assert 3 not in state.screenshots
    assert state.step_status["screenshot_p3"].status is not StepStatus.FAILED


def test_step_screenshot_rejects_error_page(tmp_path: Path) -> None:
    """A capture flagged as an error/404 page (is_error_page) is rejected even
    when the HTTP status is 200 (soft-404s)."""
    deps = _deps(tmp_path, _settings(cap=1),
                 FakeScreenshotProvider(is_error_page=True))
    state = RunState(run_id="r")
    state.facts[3] = ResearchFacts(fontes=["https://meu.inss.gov.br/x"])

    st.step_screenshot(state, _solution_page(), deps)

    assert 3 not in state.screenshots


def test_step_screenshot_rejects_blank_capture_after_retry(tmp_path: Path) -> None:
    """A blank/under-rendered capture (huge flat band) is rejected. The step
    retries once; if the retry is ALSO blank the print is skipped (fail-open)."""
    from tests.fakes import blank_png

    deps = _deps(tmp_path, _settings(cap=1),
                 FakeScreenshotProvider(data=blank_png()))
    state = RunState(run_id="r")
    state.facts[3] = ResearchFacts(fontes=["https://meu.inss.gov.br/x"])

    st.step_screenshot(state, _solution_page(), deps)

    assert 3 not in state.screenshots
    # original attempt + exactly one retry, both blank
    assert deps.screenshot.captured == [
        "https://meu.inss.gov.br/x", "https://meu.inss.gov.br/x"]
    # The retry is a MATERIALLY DIFFERENT capture (B3 "scroll + settle maior"):
    # first pass is a plain capture, the retry asks for scroll + a larger settle.
    assert deps.screenshot.calls[0]["scroll"] is False
    assert deps.screenshot.calls[1]["scroll"] is True
    assert deps.screenshot.calls[1]["settle_ms"] > deps.screenshot.calls[0]["settle_ms"]


def test_step_screenshot_retry_recovers_blank(tmp_path: Path) -> None:
    """First capture is blank, the single retry renders content -> the recovered
    print is accepted and embedded (one shot, exactly one retry). The retry is a
    materially different capture: it asks the provider to scroll (kick lazy-
    loaders) and wait a larger settle (B3 "Retry 1x (scroll + settle maior)")."""
    from funnelforge.ports.services import CaptureResult
    from tests.fakes import blank_png, content_png

    provider = FakeScreenshotProvider(results=[
        CaptureResult(png=blank_png(), status=200, is_error_page=False),
        CaptureResult(png=content_png(), status=200, is_error_page=False),
    ])
    deps = _deps(tmp_path, _settings(cap=1), provider)
    state = RunState(run_id="r")
    state.facts[3] = ResearchFacts(fontes=["https://meu.inss.gov.br/x"])

    st.step_screenshot(state, _solution_page(), deps)

    assert len(state.screenshots[3]) == 1
    assert state.screenshots[3][0]["url"] == "https://meu.inss.gov.br/x"
    assert len(provider.captured) == 2  # retried once, then recovered
    # First pass: plain capture. Retry: scroll=True + a bigger settle than the
    # first pass -- proving the retry deliberately attacks the blank, not a
    # byte-identical re-shoot.
    first, retry = provider.calls
    assert first["scroll"] is False
    assert retry["scroll"] is True
    assert retry["settle_ms"] > first["settle_ms"]


def test_step_screenshot_accepts_content_capture_without_retry(tmp_path: Path) -> None:
    """A well-rendered (non-blank) capture passes both guards on the first try:
    it is saved and no retry happens."""
    from tests.fakes import content_png

    provider = FakeScreenshotProvider(data=content_png())
    deps = _deps(tmp_path, _settings(cap=1), provider)
    state = RunState(run_id="r")
    state.facts[3] = ResearchFacts(fontes=["https://meu.inss.gov.br/x"])

    st.step_screenshot(state, _solution_page(), deps)

    assert len(state.screenshots[3]) == 1
    assert provider.captured == ["https://meu.inss.gov.br/x"]  # no retry


# --------------------------------------------------------------------------- #
# adapter guards (no playwright needed -- checks run before the lazy import)
# --------------------------------------------------------------------------- #
def test_adapter_capture_exige_https_e_nao_tem_mais_lista() -> None:
    """O único guard do adapter é https. O construtor não recebe mais lista
    nenhuma -- quem autoriza é o chamador, com a evidência da pesquisa daquela
    página (`state.official_links`), fronteira por página e não por instalação."""
    from funnelforge.adapters.screenshot_playwright import PlaywrightScreenshotProvider

    provider = PlaywrightScreenshotProvider()
    with pytest.raises(ValueError):
        provider.capture("http://meu.inss.gov.br/x")          # não é https


# --------------------------------------------------------------------------- #
# B1: desktop capture mode + CaptureResult contract (playwright mocked)
# --------------------------------------------------------------------------- #
def _fake_sync_playwright(rec: dict, *, status: int | None = 200,
                          title: str = "Bem-vindo", body: str = "conteudo",
                          png: bytes = b"PNGDATA"):
    """Minimal in-memory stand-in for playwright.sync_api.sync_playwright so the
    adapter's real navigation/return logic runs with no browser and no network."""
    class FakePage:
        def goto(self, url, wait_until=None, timeout=None):
            rec.setdefault("goto", []).append((url, wait_until))
            return SimpleNamespace(status=status)

        def wait_for_timeout(self, ms):  # noqa: ANN001
            rec.setdefault("waits", []).append(ms)

        def evaluate(self, script):  # noqa: ANN001 - records the scroll kick
            rec.setdefault("evaluate", []).append(script)

        def get_by_role(self, *a, **k):  # cookie banner: none present
            return SimpleNamespace(count=lambda: 0)

        def title(self):
            return title

        def query_selector(self, sel):  # noqa: ANN001
            return object()

        def inner_text(self, sel):  # noqa: ANN001
            return body

        def screenshot(self, full_page=False, type="png"):  # noqa: A002
            rec.setdefault("screenshot", []).append((full_page, type))
            return png

    class FakeContext:
        def new_page(self):
            return FakePage()

    class FakeBrowser:
        def new_context(self, **kwargs):
            rec.setdefault("context", []).append(kwargs)
            return FakeContext()

        def close(self):
            rec["closed"] = True

    class FakeChromium:
        def launch(self, headless=True):
            return FakeBrowser()

    class FakePW:
        chromium = FakeChromium()

    class FakeCtxMgr:
        def __enter__(self):
            return FakePW()

        def __exit__(self, *a):
            return False

    def sync_playwright():
        return FakeCtxMgr()

    return sync_playwright


def _install_fake_playwright(monkeypatch, rec: dict, **kw) -> None:
    import sys
    import types

    mod = types.ModuleType("playwright.sync_api")
    mod.sync_playwright = _fake_sync_playwright(rec, **kw)
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", mod)


def test_capture_desktop_mode_returns_captureresult(monkeypatch) -> None:
    from funnelforge.adapters.screenshot_playwright import (
        _DESKTOP_UA,
        PlaywrightScreenshotProvider,
    )
    from funnelforge.ports.services import CaptureResult

    rec: dict = {}
    _install_fake_playwright(monkeypatch, rec, status=200, png=b"IMG")
    provider = PlaywrightScreenshotProvider()

    res = provider.capture("https://meu.inss.gov.br/x")  # default mode == desktop

    assert isinstance(res, CaptureResult)
    assert res.png == b"IMG"
    assert res.status == 200
    assert res.is_error_page is False
    ctx = rec["context"][0]
    assert ctx["viewport"] == {"width": 1366, "height": 768}
    assert ctx["device_scale_factor"] == 2
    assert ctx["user_agent"] == _DESKTOP_UA


def test_capture_mobile_mode_uses_mobile_viewport_and_ua(monkeypatch) -> None:
    from funnelforge.adapters.screenshot_playwright import (
        _MOBILE_UA,
        PlaywrightScreenshotProvider,
    )
    from funnelforge.ports.services import CaptureResult

    rec: dict = {}
    _install_fake_playwright(monkeypatch, rec, status=200)
    provider = PlaywrightScreenshotProvider()

    res = provider.capture("https://meu.inss.gov.br/x", mode="mobile")

    assert isinstance(res, CaptureResult)
    ctx = rec["context"][0]
    assert ctx["viewport"] == {"width": 390, "height": 844}
    assert ctx["user_agent"] == _MOBILE_UA


def test_capture_flags_error_page(monkeypatch) -> None:
    from funnelforge.adapters.screenshot_playwright import PlaywrightScreenshotProvider

    rec: dict = {}
    _install_fake_playwright(monkeypatch, rec, status=404,
                             title="Página não encontrada", body="erro 404")
    provider = PlaywrightScreenshotProvider()

    res = provider.capture("https://meu.inss.gov.br/missing")

    assert res.status == 404
    assert res.is_error_page is True


def test_capture_default_settle_no_scroll(monkeypatch) -> None:
    """A first-pass capture waits the default 1500ms settle and does NOT scroll:
    the scroll kick is reserved for the blank retry."""
    from funnelforge.adapters.screenshot_playwright import PlaywrightScreenshotProvider

    rec: dict = {}
    _install_fake_playwright(monkeypatch, rec, status=200)
    provider = PlaywrightScreenshotProvider()

    provider.capture("https://meu.inss.gov.br/x")

    assert 1500 in rec["waits"]
    assert "evaluate" not in rec  # no scroll kick on the first pass


def test_capture_retry_scrolls_and_uses_larger_settle(monkeypatch) -> None:
    """The B3 retry (scroll=True, settle_ms=bigger) actually SCROLLS the page
    (kick lazy-loaders via page.evaluate) and waits the larger settle it was
    given -- proving the retry is a materially different capture, not a re-shoot."""
    from funnelforge.adapters.screenshot_playwright import PlaywrightScreenshotProvider

    rec: dict = {}
    _install_fake_playwright(monkeypatch, rec, status=200)
    provider = PlaywrightScreenshotProvider()

    provider.capture("https://meu.inss.gov.br/x", scroll=True, settle_ms=4000)

    assert rec.get("evaluate")  # the scroll kick ran
    assert "scrollTo" in rec["evaluate"][0]
    assert 4000 in rec["waits"]  # honored the larger settle


def test_capture_guard_https_roda_antes_do_browser(monkeypatch) -> None:
    """O guard de https continua levantando ANTES de qualquer trabalho de
    browser: com o playwright falso instalado, uma URL http recusada não abre
    contexto nem navega (o registro do fake fica vazio)."""
    from funnelforge.adapters.screenshot_playwright import PlaywrightScreenshotProvider

    rec: dict = {}
    _install_fake_playwright(monkeypatch, rec, status=200)
    provider = PlaywrightScreenshotProvider()

    with pytest.raises(ValueError):
        provider.capture("http://meu.inss.gov.br/x", mode="desktop")

    assert rec == {}  # nenhum contexto, nenhum goto: barrou antes do browser


def test_capture_aceita_host_qualquer_em_https(monkeypatch) -> None:
    """O efeito colateral que a allowlist causava: o print do canal oficial de um
    funil NÃO governamental era recusado no guard. Sem lista, o cadastro de
    entregador do iFood é capturado normalmente -- é o chamador (a pesquisa
    daquela página) que já decidiu que esta URL é o canal oficial."""
    from funnelforge.adapters.screenshot_playwright import PlaywrightScreenshotProvider

    rec: dict = {}
    _install_fake_playwright(monkeypatch, rec, status=200, png=b"IFOOD")

    res = PlaywrightScreenshotProvider().capture(
        "https://entregador.ifood.com.br/cadastro")

    assert res.png == b"IFOOD"
    assert res.status == 200
    assert rec["goto"][0][0] == "https://entregador.ifood.com.br/cadastro"


# --------------------------------------------------------------------------- #
# image processing (deterministic crop + resize + webp)
# --------------------------------------------------------------------------- #
def test_screenshot_to_webp_crops_and_resizes(tmp_path: Path) -> None:
    from PIL import Image

    out = PillowImageProcessor().screenshot_to_webp(
        png_bytes(1600, 2000), tmp_path / "shot.webp")

    img = Image.open(out)
    assert img.width == 800            # 1600 downscaled to the 800px width cap
    assert img.height == 600           # 2000 cropped to 1200, then 1200*800/1600
    assert out.suffix == ".webp"


def test_screenshot_to_webp_leaves_small_image_dims_untouched(tmp_path: Path) -> None:
    from PIL import Image

    out = PillowImageProcessor().screenshot_to_webp(
        png_bytes(400, 300), tmp_path / "s.webp")

    img = Image.open(out)
    assert (img.width, img.height) == (400, 300)  # below both caps -> no crop/resize


def test_screenshot_to_webp_desktop_profile_downscales_width_keeps_fold(
    tmp_path: Path,
) -> None:
    """B2: desktop profile just downscales to ~1200px wide -- it must NOT crop
    to the mobile 1200px-height fold (a 1366x768 desktop capture is already
    landscape; squashing it to max_height=1200 would be a no-op crop-wise but
    the point is no height crop happens at all, only a width-preserving-aspect
    resize)."""
    from PIL import Image

    out = PillowImageProcessor().screenshot_to_webp(
        png_bytes(2732, 1536), tmp_path / "shot.webp", profile="desktop")

    img = Image.open(out)
    assert img.width == 1200                  # downscaled to the 1200px width cap
    assert img.height == round(1536 * 1200 / 2732)  # aspect preserved, no crop
    assert out.suffix == ".webp"


def test_screenshot_to_webp_desktop_profile_leaves_narrow_image_untouched(
    tmp_path: Path,
) -> None:
    from PIL import Image

    out = PillowImageProcessor().screenshot_to_webp(
        png_bytes(900, 2000), tmp_path / "s.webp", profile="desktop")

    img = Image.open(out)
    # below the 1200px width cap -> no resize AND no mobile-style height crop
    assert (img.width, img.height) == (900, 2000)


def test_screenshot_to_webp_mobile_profile_is_the_default_legacy_crop(
    tmp_path: Path,
) -> None:
    """profile="mobile" (the default) keeps the original crop-then-resize
    behaviour untouched -- same numbers as the pre-existing crop test."""
    from PIL import Image

    out = PillowImageProcessor().screenshot_to_webp(
        png_bytes(1600, 2000), tmp_path / "shot.webp", profile="mobile")

    img = Image.open(out)
    assert img.width == 800
    assert img.height == 600


# --------------------------------------------------------------------------- #
# publish-side insertion (synthetic HTML)
# --------------------------------------------------------------------------- #
def test_insert_official_screenshot_after_href_block() -> None:
    html = (
        '<!-- wp:heading --><h2>Como atualizar</h2><!-- /wp:heading -->\n'
        '<!-- wp:paragraph --><p>Acesse o '
        '<a href="https://meu.inss.gov.br/x">Meu INSS</a>.</p><!-- /wp:paragraph -->\n'
        '<!-- wp:paragraph --><p>Depois confirme os dados.</p><!-- /wp:paragraph -->'
    )

    out = st._insert_official_screenshot(
        html, "https://cdn.example/shot.webp", "https://meu.inss.gov.br/x",
        "meu.inss.gov.br", "Reprodução: meu.inss.gov.br — tela oficial de x")

    assert 'src="https://cdn.example/shot.webp"' in out
    assert "Reprodução: site oficial (meu.inss.gov.br)" in out
    href_i = out.index('href="https://meu.inss.gov.br/x"')
    img_i = out.index("wp:image")
    next_i = out.index("Depois confirme")
    assert href_i < img_i < next_i          # after the link's whole block, before next para
    assert out.count("wp:spacer") >= 2       # AdSense-safe spacer above + below


def test_insert_official_screenshot_fallback_after_second_heading() -> None:
    html = (
        '<!-- wp:heading --><h2>Primeiro</h2><!-- /wp:heading -->'
        '<!-- wp:paragraph --><p>a</p><!-- /wp:paragraph -->'
        '<!-- wp:heading --><h2>Segundo</h2><!-- /wp:heading -->'
        '<!-- wp:paragraph --><p>corpo final</p><!-- /wp:paragraph -->'
    )

    # href absent from the body -> fallback anchor is after the 2nd heading
    out = st._insert_official_screenshot(
        html, "https://cdn/shot.webp", "https://meu.inss.gov.br/missing",
        "meu.inss.gov.br", "alt")

    img_i = out.index("wp:image")
    assert out.index("Segundo") < img_i < out.index("corpo final")


def test_insert_official_screenshot_noop_without_anchor_or_url() -> None:
    html = '<!-- wp:paragraph --><p>sem heading e sem link</p><!-- /wp:paragraph -->'
    # href missing AND fewer than two headings -> nothing inserted
    assert st._insert_official_screenshot(
        html, "https://cdn/shot.webp", "https://meu.inss.gov.br/x",
        "meu.inss.gov.br", "alt") == html
    # empty image url -> no-op regardless of anchors
    assert st._insert_official_screenshot(html, "", "https://meu.inss.gov.br/x",
                                          "meu.inss.gov.br", "alt") == html


# --------------------------------------------------------------------------- #
# publish integration (fake publisher)
# --------------------------------------------------------------------------- #
class _FakePublisher:
    def __init__(self) -> None:
        self.uploaded: list[dict] = []
        self.post_call: dict | None = None

    def upload_media(self, data, filename, mime, alt=""):
        self.uploaded.append({"filename": filename, "mime": mime, "alt": alt})
        return {"id": 55,
                "source_url": "https://creditoup.com.br/wp-content/uploads/shot.webp"}

    def create_post(self, title, content, slug, status, post_type, featured_media=None):
        self.post_call = {"content": content, "status": status,
                          "featured_media": featured_media}
        return {"id": 2}

    def set_yoast(self, post_id, post_type, fields, status=None):
        return {}

    def set_status(self, post_id, post_type, status):
        return {}

    def create_elementor_page(self, *a, **k):
        return {"id": 1}


def test_publish_uploads_and_embeds_official_screenshot(tmp_path: Path, config_files) -> None:
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    pub = _FakePublisher()
    deps = SimpleNamespace(publisher=pub, settings=settings,
                           runner=SimpleNamespace(runs_dir=tmp_path / "runs"))
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    shot = run_dir / "p2-oficial-meuinssgovbr-1.webp"
    shot.write_bytes(png_bytes())

    state = RunState(run_id="r1")
    content = (
        '<!-- wp:heading --><h2>Como atualizar</h2><!-- /wp:heading -->\n'
        '<!-- wp:paragraph --><p>Entre no '
        '<a href="https://meu.inss.gov.br/atualizacao">Meu INSS</a>.</p><!-- /wp:paragraph -->'
    )
    state.drafts[2] = PageDraft(page_number=2, page_type="SOLUTION",
                                format="gutenberg", content=content)
    state.facts[2] = ResearchFacts(fontes=["https://meu.inss.gov.br/atualizacao"])
    state.screenshots[2] = [{"url": "https://meu.inss.gov.br/atualizacao", "path": str(shot)}]
    page = Page(page_number=2, page_type="SOLUTION", h1_title="T",
                slug="atualizar-cadastro-p1")

    st.step_publish(state, page, deps)

    assert pub.uploaded, "screenshot should be uploaded to WP media"
    up = pub.uploaded[-1]
    assert up["filename"] == "p2-oficial-meuinssgovbr-1.webp"
    assert up["mime"] == "image/webp"
    assert up["alt"].startswith("Reprodução: meu.inss.gov.br — tela oficial de")
    body = pub.post_call["content"]
    assert "wp:image" in body
    assert "Reprodução: site oficial (meu.inss.gov.br)" in body
    assert body.index("meu.inss.gov.br/atualizacao") < body.index("wp:image")


def test_publish_survives_screenshot_upload_failure(tmp_path: Path, config_files) -> None:
    """A failed screenshot upload is swallowed (best-effort/non-fatal): the post
    still publishes text-only and no exception escapes step_publish."""
    settings = load_settings(config_files / ".env", config_files / "config.yaml")

    class _BoomUploadPublisher(_FakePublisher):
        def upload_media(self, data, filename, mime, alt=""):
            raise RuntimeError("WP media 500")

    pub = _BoomUploadPublisher()
    deps = SimpleNamespace(publisher=pub, settings=settings,
                           runner=SimpleNamespace(runs_dir=tmp_path / "runs"))
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    shot = run_dir / "p2-oficial-meuinssgovbr-1.webp"
    shot.write_bytes(png_bytes())
    state = RunState(run_id="r1")
    content = (
        '<!-- wp:heading --><h2>Como</h2><!-- /wp:heading -->\n'
        '<!-- wp:paragraph --><p>'
        '<a href="https://meu.inss.gov.br/atualizacao">Meu INSS</a></p><!-- /wp:paragraph -->'
    )
    state.drafts[2] = PageDraft(page_number=2, page_type="SOLUTION",
                                format="gutenberg", content=content)
    state.facts[2] = ResearchFacts(fontes=["https://meu.inss.gov.br/atualizacao"])
    state.screenshots[2] = [{"url": "https://meu.inss.gov.br/atualizacao", "path": str(shot)}]
    page = Page(page_number=2, page_type="SOLUTION", h1_title="T", slug="x-p1")

    st.step_publish(state, page, deps)  # must not raise

    assert pub.post_call is not None                       # post still created
    assert "wp:image" not in pub.post_call["content"]      # no screenshot embedded


def test_publish_without_screenshots_is_unchanged(tmp_path: Path, config_files) -> None:
    """No captured screenshots -> no upload, body carries no reproduction image
    (a text-only SOLUTION post still publishes)."""
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    pub = _FakePublisher()
    deps = SimpleNamespace(publisher=pub, settings=settings,
                           runner=SimpleNamespace(runs_dir=tmp_path / "runs"))
    (tmp_path / "runs" / "r1").mkdir(parents=True)
    state = RunState(run_id="r1")
    content = '<!-- wp:heading --><h2>Intro</h2><!-- /wp:heading --><p>corpo</p>'
    state.drafts[2] = PageDraft(page_number=2, page_type="SOLUTION",
                                format="gutenberg", content=content)
    page = Page(page_number=2, page_type="SOLUTION", h1_title="T", slug="x-p1")

    st.step_publish(state, page, deps)

    assert pub.uploaded == []
    assert "Reprodução: site oficial" not in pub.post_call["content"]


# --------------------------------------------------------------------------- #
# pipeline wiring: step runs in sequence for a SOLUTION page
# --------------------------------------------------------------------------- #
def test_pipeline_runs_screenshot_step_for_solution(tmp_path: Path, config_files) -> None:
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    settings.run.official_screenshots = True
    settings.run.featured_image = False  # keep the image path out of the way
    plan = FunnelPlan(total_pages=1, pages=[
        Page(page_number=3, page_type="SOLUTION", h1_title="Atualizar cadastro",
             slug="atualizar-cadastro-p1", ordinal=1, role=PageRole.SOLUTION,
             main_content_structure=["H2: Como"], next_page_slug="")])
    state = RunState(run_id="atualizar-cadastro-p1-20260720")
    state.plan = plan
    state.facts[3] = ResearchFacts(fontes=["https://meu.inss.gov.br/x"])
    # Estado como um checkpoint real deixa depois da pesquisa: o canal oficial
    # já ESCOLHIDO por `registrar_canais_oficiais` (research_p3 está OK abaixo,
    # então a etapa não roda de novo). É daqui que o print sai.
    state.official_links[3] = ["https://meu.inss.gov.br/x"]
    state.drafts[3] = PageDraft(
        page_number=3, page_type="SOLUTION", format="gutenberg",
        content='<!-- wp:heading --><h2>x</h2><!-- /wp:heading -->'
                '<!-- wp:paragraph --><p>y</p><!-- /wp:paragraph -->')
    for k in ("research_p3", "write_p3", "seo_p3"):
        state.step_status[k] = StepResult(step=k, status=StepStatus.OK)

    provider = FakeScreenshotProvider()
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=None, image_gen=None,
                image_proc=PillowImageProcessor(), publisher=None, loader=None,
                settings=settings, runner=runner, screenshot=provider)

    out = run_pipeline(None, deps, publish=False, resume_state=state)

    assert out.step_status["screenshot_p3"].status is StepStatus.OK
    assert provider.captured == ["https://meu.inss.gov.br/x"]
    assert out.screenshots[3][0]["url"] == "https://meu.inss.gov.br/x"


# --------------------------------------------------------------------------- #
# Task 9 (B5): config-driven wiring -- screenshot.mode + crop_profile + limiares
# --------------------------------------------------------------------------- #
def test_screenshot_config_defaults_and_real_config_are_desktop() -> None:
    """The new `screenshot:` config block (B5) exists with desktop defaults, and
    the project's real config.yaml opts into desktop mode + crop_profile with the
    guard thresholds surfaced from config (limiares)."""
    from funnelforge.config.settings import ScreenshotConfig

    default = ScreenshotConfig()
    assert default.mode == "desktop"
    assert default.crop_profile == "desktop"

    settings = load_settings(
        Path("/nonexistent.env"), Path(__file__).resolve().parents[1] / "config.yaml"
    )
    assert settings.screenshot.mode == "desktop"
    assert settings.screenshot.crop_profile == "desktop"
    assert settings.screenshot.blank_frac_max > 0
    assert settings.screenshot.blank_contig_max > 0
    assert settings.screenshot.retry_settle_ms > 1500


def test_step_screenshot_wires_desktop_mode_and_crop_profile(tmp_path: Path) -> None:
    """B5 wiring: step_screenshot drives the provider capture `mode` and the
    image crop `profile` from `settings.screenshot`, so a desktop-config run
    captures with mode='desktop' AND crops with the desktop profile (no mobile
    800x1200 squeeze). Proven with a spy image processor recording the profile."""
    from funnelforge.config.settings import ScreenshotConfig

    class _SpyImageProc:
        def __init__(self) -> None:
            self.profiles: list[str] = []

        def screenshot_to_webp(self, data, out_path, *, profile="mobile", **kw):
            self.profiles.append(profile)
            out = Path(out_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"webp")
            return out

    settings = _settings()
    settings.screenshot = ScreenshotConfig(mode="desktop", crop_profile="desktop")
    provider = FakeScreenshotProvider()
    spy = _SpyImageProc()
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=None, image_gen=None, image_proc=spy,
                publisher=None, loader=None, settings=settings, runner=runner,
                screenshot=provider)
    state = RunState(run_id="r")
    state.facts[3] = ResearchFacts(fontes=["https://meu.inss.gov.br/x"])

    st.step_screenshot(state, _solution_page(), deps)

    assert provider.calls[0]["mode"] == "desktop"
    assert spy.profiles == ["desktop"]


def test_step_screenshot_blank_retry_settle_comes_from_config(tmp_path: Path) -> None:
    """The blank/under-render retry settle (B3 'settle maior') is taken from
    `settings.screenshot.retry_settle_ms`, not a hardcoded constant."""
    from tests.fakes import blank_png

    settings = _settings(cap=1)
    settings.screenshot = __import__(
        "funnelforge.config.settings", fromlist=["ScreenshotConfig"]
    ).ScreenshotConfig(retry_settle_ms=5500)
    provider = FakeScreenshotProvider(data=blank_png())
    deps = _deps(tmp_path, settings, provider)
    state = RunState(run_id="r")
    state.facts[3] = ResearchFacts(fontes=["https://meu.inss.gov.br/x"])

    st.step_screenshot(state, _solution_page(), deps)

    assert provider.calls[1]["scroll"] is True
    assert provider.calls[1]["settle_ms"] == 5500


def test_pipeline_skips_screenshot_when_provider_none(tmp_path: Path, config_files) -> None:
    """The default wiring (no screenshot provider) behaves exactly as before:
    the step never runs and no screenshot status is recorded."""
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    settings.run.featured_image = False
    plan = FunnelPlan(total_pages=1, pages=[
        Page(page_number=3, page_type="SOLUTION", h1_title="T",
             slug="atualizar-cadastro-p1", ordinal=1, role=PageRole.SOLUTION)])
    state = RunState(run_id="atualizar-cadastro-p1-20260720")
    state.plan = plan
    state.facts[3] = ResearchFacts(fontes=["https://meu.inss.gov.br/x"])
    state.drafts[3] = PageDraft(page_number=3, page_type="SOLUTION",
                                format="gutenberg", content="<p>y</p>")
    for k in ("research_p3", "write_p3", "seo_p3"):
        state.step_status[k] = StepResult(step=k, status=StepStatus.OK)

    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=None, image_gen=None,
                image_proc=PillowImageProcessor(), publisher=None, loader=None,
                settings=settings, runner=runner, screenshot=None)

    out = run_pipeline(None, deps, publish=False, resume_state=state)

    assert "screenshot_p3" not in out.step_status
    assert 3 not in out.screenshots
