from __future__ import annotations

from urllib.parse import urlparse

from funnelforge.ports.services import CaptureResult

# Assinaturas de rede/DOM de ad tech de display. Não é lista de domínios
# proibidos: é o SINAL ESTRUTURAL de que a página se sustenta vendendo a
# atenção do visitante -- ou seja, de que ela disputa a MESMA sessão que você
# comprou no Google Ads. Canal oficial (gov.br, cadastro do iFood, Serasa) não
# tem isso; portal de arbitragem concorrente tem.
# ⚠️ MEDIÇÃO, NÃO ANALYTICS. Estas requisições usam domínios de ad tech mas são
# de ANÁLISE, não de veiculação de anúncio — e são conferidas ANTES das marcas
# abaixo, senão elas dominam o resultado.
#
# O caso que expôs o defeito (run #5, 17/08/2026): `bcb.gov.br` — o Banco
# Central — foi classificado como "vive de anúncio" porque carrega
# `stats.g.doubleclick.net/g/collect?v=2&tid=G-...`, que é o endpoint de
# medição do Google Analytics 4. Praticamente todo site sério do mundo o
# carrega, inclusive os do governo. Com isso, a sonda reprovava o canal oficial
# de qualquer página e a página morria no gate de densidade — com fontes boas
# na mão.
_MEDICAO_NAO_E_ANUNCIO = (
    "stats.g.doubleclick.net",          # GA4 measurement
    "google-analytics.com",
    "analytics.google.com",
    "googletagmanager.com",             # o contêiner do GTM, não o anúncio
)

# Veiculação de anúncio DE VERDADE: servidor de display, exchange, rede de
# recomendação paga. Um portal que roda isto monetiza a MESMA sessão que você
# comprou — é concorrente, não canal oficial.
_MARCAS_DE_ANUNCIO = (
    "googlesyndication.com",            # AdSense
    "securepubads.g.doubleclick.net",   # Google Publisher Tag (GAM)
    "googletagservices.com",
    "adservice.google.",
    "adsbygoogle",
    "adnxs.com", "criteo.", "taboola.com", "outbrain.com",
    "mgid.com", "pubmatic.com", "rubiconproject.com",
)

# An HONEST, current Chrome-on-Android user agent -- no impersonation of a real
# person, just a truthful mobile-Chrome identity so official sites serve their
# mobile layout for the above-the-fold capture.
_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36"
)

# An HONEST desktop-Chrome-on-Windows user agent -- again no person impersonation,
# just a truthful desktop identity so responsive gov sites serve their FULL
# desktop layout (which frames far better for an above-the-fold official print).
_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# Per-mode viewport (width, height). Desktop is the default for official prints.
_VIEWPORTS = {"desktop": (1366, 768), "mobile": (390, 844)}

# Lowercase substrings that, in a page title/body, mark an error/404 page.
_ERROR_MARKERS = (
    "não existe", "nao existe", "não encontrada", "nao encontrada",
    "not found", "erro 404", "página não", "pagina nao",
)

# Common pt-BR cookie/consent banner button labels. Dismissing the banner is
# STRICTLY best-effort: any failure is swallowed and never blocks the capture.
_COOKIE_BUTTON_TEXTS = ("Aceitar", "Aceito", "Concordo", "Continuar", "Entendi", "OK")


class PlaywrightScreenshotProvider:
    """ScreenshotProvider sobre Playwright/Chromium (API síncrona), headless.

    SEM LISTA DE DOMÍNIO. O adapter exige apenas HTTPS antes de abrir o browser.
    Quem autoriza é o chamador, e a autorização dele é POR PÁGINA: só chegam
    aqui URLs que a pesquisa daquela página trouxe e que o Chromium confirmou
    (ver steps.build_official_links). Essa fronteira é estritamente mais forte
    do que a allowlist global que existia antes -- que, além de fraca, recusava
    o print do canal oficial de qualquer funil não-governamental (um funil de
    entregador do iFood não conseguia mostrar a página de cadastro do iFood).

    Nunca envia formulário, faz login ou digita dado: navega e tira uma foto
    estática. Se a URL redireciona para uma tela de login, aquela tela É o ponto
    de entrada oficial e o print dela é aceitável.

    ``playwright`` é dependência OPCIONAL (extra ``screenshots``), importada
    PREGUIÇOSAMENTE dentro de cada método -- e só depois do guard -- para o
    módulo importar (e o guard continuar testável) sem playwright instalado."""

    def capture(self, url: str, *, mode: str = "desktop",
                full_page: bool = False, timeout_s: int = 30,
                scroll: bool = False, settle_ms: int = 1500) -> CaptureResult:
        # O guard roda ANTES do import do playwright: testável sem browser, e
        # nenhuma janela é aberta para uma URL recusada.
        if urlparse(url).scheme != "https":
            raise ValueError(f"screenshot exige https, recusado: {url!r}")

        from playwright.sync_api import sync_playwright

        width, height = _VIEWPORTS.get(mode, _VIEWPORTS["desktop"])
        user_agent = _MOBILE_UA if mode == "mobile" else _DESKTOP_UA
        timeout_ms = timeout_s * 1000
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=2,
                    locale="pt-BR",
                    user_agent=user_agent,
                )
                page = context.new_page()
                status: int | None = None
                try:
                    resp = page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                    status = resp.status if resp else None
                except Exception:  # noqa: BLE001 - networkidle can time out; fall back
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    status = resp.status if resp else None
                # On the B3 retry (scroll=True), actively KICK lazy-loaders by
                # scrolling the whole page before settling -- this is what makes
                # the retry a materially different capture, not a re-shoot.
                if scroll:
                    self._scroll_to_kick_lazyload(page)
                # Settle for late render (fonts/hero/lazy content) -- the retry
                # passes a larger settle_ms -- then best-effort dismiss a
                # cookie/consent banner so it doesn't cover the fold.
                page.wait_for_timeout(settle_ms)
                self._dismiss_cookies(page)
                is_error = self._looks_like_error_page(page)
                png = page.screenshot(full_page=full_page, type="png")
                return CaptureResult(png=png, status=status, is_error_page=is_error)
            finally:
                browser.close()

    # ⚠️ `verify_url` FOI DAQUI PARA `adapters/url_verifier_http.py`.
    #
    # Verificar se uma URL existe é pergunta de HTTP, não de browser. Enquanto
    # morou aqui, ela só existia quando `official_screenshots` estava ligada — e
    # como o gate factual depende dela, desligar uma flag de IMAGEM reprovava
    # toda página com fato numérico. A flag voltou a ser cosmética.
    #
    # A sonda abaixo fica: ela precisa de DOM e de rede para decidir se a página
    # é um portal de anúncio, então browser é requisito real, não acidente.

    def is_ad_monetized(self, url: str, *, timeout_s: int = 20,
                        settle_ms: int = 1500) -> bool | None:
        """A página de destino vive de anúncio display?

        É a proteção que substitui a allowlist contra "linkar concorrente que
        rouba o clique comprado": um portal de arbitragem monetiza a MESMA
        sessão que você pagou; um canal oficial (gov.br, cadastro do iFood,
        Serasa) não. O sinal é medido ao vivo -- requisições de ad tech durante
        a navegação, mais os contêineres de anúncio no DOM -- e não depende de
        ninguém manter lista nenhuma atualizada.

        Devolve True (detectou), False (carregou e não tem) ou **None** quando
        não deu para saber (sem playwright, navegação falhou). `None` NUNCA
        reprova: um falso positivo da sonda não pode derrubar a única URL
        oficial que a pesquisa achou. Só navega, não clica nem digita.
        """
        if urlparse(url).scheme != "https":
            return None
        try:
            from playwright.sync_api import sync_playwright
        except Exception:  # noqa: BLE001 - playwright opcional; sem sonda = não sei
            return None
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        viewport={"width": 1366, "height": 768},
                        locale="pt-BR", user_agent=_DESKTOP_UA)
                    page = context.new_page()
                    pedidos: list[str] = []
                    try:
                        page.on("request", lambda req: pedidos.append(req.url))
                    except Exception:  # noqa: BLE001 - sniffing é best-effort
                        pass
                    try:
                        resp = page.goto(url, wait_until="domcontentloaded",
                                         timeout=timeout_s * 1000)
                    except Exception:  # noqa: BLE001 - navegação falhou = não sei
                        return None
                    if resp is None:
                        return None
                    page.wait_for_timeout(settle_ms)
                    # A ordem importa: descarta o que é MEDIÇÃO antes de
                    # procurar veiculação. Sem isto, o `doubleclick.net` do GA4
                    # casa em todo site que usa Analytics.
                    de_anuncio = [
                        p for p in pedidos
                        if not any(ok in p.lower() for ok in _MEDICAO_NAO_E_ANUNCIO)
                    ]
                    if any(m in p.lower() for p in de_anuncio
                           for m in _MARCAS_DE_ANUNCIO):
                        return True
                    try:
                        marcado = page.query_selector(
                            "ins.adsbygoogle, [id^='div-gpt-ad'], [class*='adsbygoogle']")
                    except Exception:  # noqa: BLE001 - leitura do DOM é best-effort
                        marcado = None
                    return marcado is not None
                finally:
                    browser.close()
        except Exception:  # noqa: BLE001 - falha de launch = não sei (não reprova)
            return None

    @staticmethod
    def _scroll_to_kick_lazyload(page: object) -> None:
        """Best-effort: scroll from top to bottom (in viewport-sized steps) and
        back to the top, so lazy-loaders / intersection-observers that only fire
        on scroll actually render their content BEFORE the settle + screenshot.
        This is the deliberate action that gives the blank/under-render retry a
        real chance of recovering, instead of re-shooting the same empty frame.
        NEVER fatal -- any failure leaves the page where it is and the capture
        proceeds."""
        try:
            page.evaluate(  # type: ignore[attr-defined]
                "async () => {"
                "  const step = window.innerHeight || 800;"
                "  const height = () => document.body ? document.body.scrollHeight : 0;"
                "  for (let y = 0; y <= height(); y += step) {"
                "    window.scrollTo(0, y);"
                "    await new Promise(r => setTimeout(r, 150));"
                "  }"
                "  window.scrollTo(0, 0);"
                "}"
            )
        except Exception:  # noqa: BLE001 - scroll is best-effort, never fatal
            return

    @staticmethod
    def _looks_like_error_page(page: object) -> bool:
        """Cheap, no-OCR error/404 detection from the page's title/body text.
        Best-effort: any failure reading the DOM means 'not an error page'."""
        try:
            title = (page.title() or "").lower()  # type: ignore[attr-defined]
            body = ""
            if page.query_selector("body"):  # type: ignore[attr-defined]
                body = (page.inner_text("body") or "")[:400].lower()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - error detection is best-effort, never fatal
            return False
        return any(m in title or m in body for m in _ERROR_MARKERS)

    @staticmethod
    def _dismiss_cookies(page: object) -> None:
        """Best-effort: click a visible consent-banner button if there is one.
        NEVER fatal -- any exception is swallowed and the capture proceeds."""
        for label in _COOKIE_BUTTON_TEXTS:
            try:
                button = page.get_by_role("button", name=label, exact=False)  # type: ignore[attr-defined]
                if button.count() and button.first.is_visible():
                    button.first.click(timeout=1500)
                    page.wait_for_timeout(400)  # type: ignore[attr-defined]
                    return
            except Exception:  # noqa: BLE001 - cookie dismissal is best-effort, never fatal
                continue
