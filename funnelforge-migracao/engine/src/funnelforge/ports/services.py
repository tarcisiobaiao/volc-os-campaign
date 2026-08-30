from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from funnelforge.domain.models import ResearchFacts


@dataclass
class CaptureResult:
    """Outcome of a single ScreenshotProvider.capture: the raw PNG bytes plus
    the cheap validity signals the step_screenshot guards act on. `status` is the
    HTTP status of the navigation (None when playwright yields no response), and
    `is_error_page` flags an error/404 page detected from its title/body text."""
    png: bytes
    status: int | None
    is_error_page: bool


class ResearchProvider(Protocol):
    def research(self, topic: str, structure: str) -> ResearchFacts: ...


class ImageGenerator(Protocol):
    """Gera a imagem e devolve os bytes.

    TELEMETRIA (contrato OPCIONAL, e é assim que a imagem entra no ledger): uma
    implementação PAGA deve expor, depois de cada `generate`, o atributo
    `last_usage` com um `adapters.image_pricing.ImageUsage` (custo, fonte do
    preço, latência, modelo/tamanho/qualidade, tokens). `step_image` lê esse
    atributo com `getattr` — mesmo contrato opcional do `ResearchProvider`
    (`last_cost_usd` e amigos, ver `step_research`) — para que fakes de teste e
    adapters gratuitos sigam válidos sem implementá-lo."""
    def generate(self, prompt: str, size: str = "1536x1024") -> bytes: ...


class UrlVerifier(Protocol):
    """"Essa URL é uma página viva?" — a verificação que o gate factual usa.

    É um port PRÓPRIO porque isso é uma pergunta de HTTP, não de renderização.
    Antes era resolvida por `getattr(deps.screenshot, "verify_url")`: um método
    que NUNCA esteve neste arquivo, num provider que só é instanciado quando
    `run.official_screenshots` está ligado. Duas consequências, ambas medidas:
    desligar os prints (flag cosmética) reprovava toda página com fato numérico,
    e um provider 100% conforme ao `ScreenshotProvider` — sem o método extra —
    reprovava também.

    Contrato: fail-CLOSED. Qualquer dúvida (timeout, bloqueio antibot, esquema
    não-https, erro de rede) devolve False. Link que não deu para confirmar não
    é publicado."""
    def verify_url(self, url: str) -> bool: ...


class ImageProcessor(Protocol):
    def to_webp(self, data: bytes, out_path: Path, quality: int = 80) -> Path: ...
    def screenshot_to_webp(self, data: bytes, out_path: Path, *,
                           max_height: int = 1200, max_width: int = 800,
                           quality: int = 80, profile: str = "mobile",
                           desktop_max_width: int = 1200) -> Path: ...


class ScreenshotProvider(Protocol):
    """Captures a STATIC screenshot of a whitelisted official destination URL
    (a SOLUTION page's `official_link`), above the fold. `mode` picks the
    viewport/UA: ``desktop`` (default, 1366x768, honest desktop-Chrome UA) serves
    the full desktop layout of responsive gov sites; ``mobile`` keeps the legacy
    390x844 mobile capture. Read-only: it navigates and shoots a picture -- never
    submits a form, logs in, types data, or executes third-party JS INTO the
    published funnel (the result is a flat image). Returns a `CaptureResult`
    (png bytes + status + is_error_page). Mirrors the ImageGenerator/
    ImageProcessor port shape.

    `settle_ms` is how long the adapter waits after navigation for late render
    (fonts/hero/lazy-loaders) before shooting; `scroll=True` asks it to scroll
    the whole page (then return to the top) to actively KICK lazy-loaders/
    intersection-observers into rendering. Both exist so the blank/under-render
    RETRY (B3) is a materially DIFFERENT capture -- a bigger settle plus a
    deliberate scroll to attack the cause of the blank -- not a byte-identical
    re-shoot that only recovers by luck of timing."""
    def capture(self, url: str, *, mode: str = "desktop",
                full_page: bool = False, timeout_s: int = 30,
                scroll: bool = False, settle_ms: int = 1500) -> CaptureResult: ...


class Publisher(Protocol):
    def upload_media(self, data: bytes, filename: str, mime: str,
                     alt: str = "") -> dict: ...
    def create_post(self, title: str, content: str, slug: str, status: str,
                    post_type: str, featured_media: int | None = None) -> dict: ...
    def set_yoast(self, post_id: int, post_type: str, fields: dict,
                  status: str | None = None) -> dict: ...
    def set_status(self, post_id: int, post_type: str, status: str) -> dict: ...
    def create_elementor_page(self, title: str, slug: str, elementor: list,
                              status: str, post_type: str = "pages",
                              page_settings: dict | None = None) -> dict: ...


class BriefingLoader(Protocol):
    def load(self, path: Path) -> str: ...


class SitemapProvider(Protocol):
    """Supplies REAL same-domain URLs (from the site's sitemap) to use as the
    terminal SOLUTION's cross-funnel exit -- a related-but-DIVERSE guide, never
    an invented slug. Returns absolute URLs, best pick first; empty if none."""
    def cross_funnel_targets(self, *, theme: str, exclude_slugs: list[str]) -> list[str]: ...
