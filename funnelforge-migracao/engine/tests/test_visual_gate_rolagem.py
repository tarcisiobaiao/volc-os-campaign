"""edge_padding mede o contêiner de rolagem, não as células que rolam dentro dele."""
import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from funnelforge.visual_gate import CHECKS

BASE = ("<html><body style='margin:0'><main style='padding:16px'>{}</main></body></html>")
TABELA = ("<figure style='overflow-x:auto;margin:0'><table style='min-width:36em'><tr>"
          "<td>Cemig</td><td>Atende Web</td><td>Confira a área</td></tr></table></figure>")
COLADO = "<p style='margin:0 -16px'>texto encostado na borda da tela do celular</p>"


def _checks(corpo):
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium indisponível: {exc}")
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.set_content(BASE.format(corpo))
        r = page.evaluate(CHECKS)
        browser.close()
        return r["checks"]


def test_tabela_larga_que_rola_no_bloco_passa():
    assert _checks("<p>Texto curto.</p>" + TABELA)["edge_padding"]


def test_elemento_colado_na_borda_continua_reprovando():
    assert not _checks(COLADO)["edge_padding"]
