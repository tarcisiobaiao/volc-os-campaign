"""Print oficial: o controle residual de cookies não é banner obstrutivo.

Regressão do run real da Tarifa Social (09/10/2026): depois do consentimento o
gov.br mantém o botão flutuante "Redefinir Cookies" (3,1% da tela) e o detector
descartava a captura útil da ANEEL.
"""
import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from funnelforge.adapters.screenshot_playwright import _OVERLAY_SCAN_JS

RESIDUAL = """<body style="margin:0"><main style="height:2000px">Tarifa social</main>
<div class="lgpd-reset-cookies" style="position:fixed;bottom:16px;left:16px;width:150px;
height:60px;background:#1351b4;color:#fff">Redefinir Cookies</div></body>"""
BANNER = """<body style="margin:0"><main style="height:2000px">Tarifa social</main>
<div class="cookie-banner" style="position:fixed;bottom:0;left:0;right:0;height:180px;
background:#fff">Usamos cookies para melhorar sua experiência. Ao continuar você concorda
com a política de privacidade. <button>Aceitar</button></div></body>"""


def _scan(html):
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium indisponível: {exc}")
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.set_content(html)
        achados = page.evaluate(_OVERLAY_SCAN_JS)
        browser.close()
        return achados


def test_controle_residual_de_cookies_nao_descarta_o_print():
    assert _scan(RESIDUAL) == []


FAIXA = """<body style="margin:0"><main style="height:2000px">Luz do Povo</main>
<div class="lgpd-reset-cookies" style="position:fixed;bottom:0;left:0;right:0;height:24px">
<button>Redefinir Cookies</button></div></body>"""


def test_faixa_fina_de_redefinir_cookies_nao_descarta_o_print():
    """Caso medido no gov.br/mme: faixa da largura toda, 3,1% de área."""
    assert _scan(FAIXA) == []


def test_banner_de_cookies_continua_obstrutivo():
    assert _scan(BANNER)
