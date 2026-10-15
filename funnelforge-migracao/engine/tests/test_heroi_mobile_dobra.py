"""Herói da LP: chamada de toque só no celular, registro honesto do template e a
régua da prova de dobra (`scripts/prova_dobra_lp.py`).

A prova do layout é geométrica e renderizada (Elementor no WordPress descartável,
ou a prévia com `FF_VISUAL_BROWSER=1`); aqui ficam as partes determinísticas.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from funnelforge.pipeline.lp_template import (
    CHAMADA_DO_HEROI_MOBILE,
    _fillable,
    load_lp_template,
    render_lp,
    transformacoes_do_template,
)

SITE = "https://creditoup.com.br"
HREFS = [f"{SITE}/rec/a-pr", f"{SITE}/rec/a-p1", f"{SITE}/rec/a-p2"]
BASE = {
    "hero_title": "Cursos gratuitos no Senac", "article_title": "Como funciona",
    "intro": "<p>Curta.</p>",
    "sections": [{"title": f"S{i}", "body": f"<p>C{i}.</p>"} for i in range(4)],
    "faq": [{"q": "P?", "a": "R."}], "faq_title": "Dúvidas", "transition": "<p>T.</p>",
    "cta_texts": ["Caminho A »", "Caminho B >>", "Caminho C"],
}


def _subtitulos(cont):
    mobile = next(n for n in cont if (n.get("settings") or {}).get("hide_desktop"))
    desktop = next(n for n in cont if (n.get("settings") or {}).get("hide_mobile"))
    pega = lambda no: [w for w in _fillable([no]) if w.get("widgetType") == "heading"][1]
    return pega(mobile)["settings"]["title"], pega(desktop)["settings"]["title"]


@pytest.mark.parametrize("subtitulo", [
    "Para quem tem renda de até 2 salários mínimos.",
    "Para quem tem renda de até 2 salários mínimos. Toque abaixo!",   # rascunho de 78c13d94
    "Para quem tem renda de até 2 salários mínimos, toque abaixo 👇",
])
def test_toque_abaixo_so_no_celular_e_uma_vez(subtitulo):
    cont, _ = render_lp(load_lp_template(), {**BASE, "hero_subtitle": subtitulo}, HREFS,
                        site_domain=SITE, copy_rapida=True, footer_disclosure=True)
    mobile, desktop = _subtitulos(cont)
    assert mobile.endswith(CHAMADA_DO_HEROI_MOBILE)
    assert mobile.lower().count("toque abaixo") == 1
    assert "toque abaixo" not in desktop.lower()
    assert desktop.startswith("Para quem tem renda")


def test_lp_v1_mantem_os_subtitulos_do_redator():
    conteudo = {**BASE, "hero_subtitle": "Toque abaixo e veja", "hero_subtitle_desktop": "Veja"}
    cont, _ = render_lp(load_lp_template(), conteudo, HREFS, site_domain=SITE)
    assert _subtitulos(cont) == ("Toque abaixo e veja", "Veja")


def test_rotulo_igual_nos_dois_herois_sem_seta_final():
    cont, _ = render_lp(load_lp_template(), {**BASE, "hero_subtitle": "S."}, HREFS,
                        site_domain=SITE, copy_rapida=True)
    rotulos = [w["settings"]["text"] for w in _fillable(cont) if w.get("widgetType") == "button"]
    assert rotulos[:3] == rotulos[3:6] == ["Caminho A", "Caminho B", "Caminho C"]


@pytest.mark.parametrize("rodape,etapa", [(True, "aviso_identidade_no_rodape_do_tema"),
                                          (False, "aviso_identidade_no_fim")])
def test_registro_do_template_diz_onde_o_aviso_ficou(rodape, etapa):
    conteudo = {**BASE, "hero_subtitle": "S."}
    tipos = {t["tipo"] for t in transformacoes_do_template(
        conteudo, copy_rapida=True, footer_disclosure=rodape)}
    assert etapa in tipos and "aviso_identidade_no_topo" not in tipos
    assert "chamada_de_toque_no_heroi_mobile" in tipos
    cont, _ = render_lp(load_lp_template(), conteudo, HREFS, site_domain=SITE,
                        copy_rapida=True, footer_disclosure=rodape)
    tem_aviso = "sem vínculo" in str(cont[-1])
    assert tem_aviso is (not rodape)


def test_prompts_da_dobra_nao_se_contradizem():
    from funnelforge.prompts import render
    raiz = Path(__file__).resolve().parents[1] / "src" / "funnelforge" / "prompts"
    ctas = (raiz / "ctas_do_funil.jinja").read_text(encoding="utf-8")
    redator = (raiz / "redator_p1_v2.jinja").read_text(encoding="utf-8")
    assert "terminando com uma chamada" not in ctas + redator
    assert "não a escreva" in ctas
    assert "o 1º à pré-sell, o 2º e o 3º" not in redator
    assert render  # o módulo de prompts continua importável


# ------------------------------------------------- régua da prova de dobra ---
def _prova():
    caminho = Path(__file__).resolve().parents[1] / "scripts" / "prova_dobra_lp.py"
    spec = importlib.util.spec_from_file_location("prova_dobra_lp", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _caixa(top, bottom, left=12, right=348, **extra):
    return {"top": top, "bottom": bottom, "left": left, "right": right,
            "width": right - left, "height": bottom - top, **extra}


def _medidas(botao3_bottom, scroll=360, cmp_top=387):
    return {"viewport": {"width": 360, "height": 800}, "scroll_width": scroll,
            "client_width": 360,
            "h1": _caixa(91, 141, texto="T", fonte_px=22), "subtitulo": _caixa(145, 179, texto="S"),
            "botoes": [_caixa(187, 231, recebe_toque=True), _caixa(235, 279, recebe_toque=True),
                       _caixa(283, botao3_bottom, recebe_toque=True)],
            "cmp": _caixa(cmp_top, 788)}


def test_regua_aprova_herois_acima_da_cmp():
    decisao = _prova().avaliar(_medidas(327), mobile=True)
    assert decisao["ok"] and decisao["folga_ate_a_cmp_px"] == 60


def test_regua_reprova_terceiro_botao_parcialmente_sob_a_cmp():
    decisao = _prova().avaliar(_medidas(423), mobile=True)
    assert not decisao["terceiro_botao_acessivel"] and not decisao["zero_sobreposicao"]
    assert not decisao["ok"]


def test_regua_reprova_rolagem_horizontal():
    assert not _prova().avaliar(_medidas(327, scroll=374), mobile=True)["ok"]


@pytest.mark.skipif(os.environ.get("FF_VISUAL_BROWSER") != "1",
                    reason="execute FF_VISUAL_BROWSER=1 com Chromium permitido")
def test_previa_estatica_da_dobra_com_cmp(tmp_path):
    """Prévia aproximada (adapters.preview), sem cabeçalho do tema. A prova fiel é
    o Elementor no WordPress descartável (recibo no handoff)."""
    prova = _prova()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=True)
        pagina = navegador.new_page()
        for nome, conteudo in prova.CONTEUDOS.items():
            r = prova.medir(pagina, prova.html_da_previa(conteudo, None), tmp_path, nome,
                            set_content=True)
            assert r["360x800"]["decisao"]["ok"], (nome, r["360x800"]["decisao"])
            assert r["1366x900"]["decisao"]["ok"], (nome, r["1366x900"]["decisao"])
        navegador.close()
