"""Entrada de contagem (pessoas, meses) só aceita inteiro positivo.

Achado do revisor global no run real de 10/10/2026: a calculadora de renda por
integrante aceitava "1,5 integrante" porque as duas entradas usavam a mesma
validação monetária.
"""
import pytest

from funnelforge.domain.models import CalculoDoAtivo
from funnelforge.pipeline.validators.checks import sanitize_widget_block
from funnelforge.widgets.calculos import renderizar_calculo, validar

sync_api = pytest.importorskip("playwright.sync_api")


def _calculo(inteiros=(1,), casos=((["1500", "3"], "500"), (["1000", "6"], "166.67"))):
    return CalculoDoAtivo(operacao="divisao", rotulos=["Renda da casa, em R$", "Moradores"],
                          rotulo_resultado="Renda por pessoa, em R$", inteiros=list(inteiros),
                          casos=[{"entradas": e, "resultado": r} for e, r in casos])


def test_gabarito_com_contagem_fracionaria_e_recusado_por_codigo():
    with pytest.raises(ValueError, match="inteiro"):
        validar(_calculo(casos=((["1500", "1.5"], "1000"), (["1000", "6"], "166.67"))))


def test_bloco_passa_no_sanitizador_e_marca_o_campo_inteiro():
    bloco = renderizar_calculo(_calculo(), titulo="Renda por pessoa", identidade="t")
    assert not sanitize_widget_block(bloco)
    assert 'data-vc-inteiros="1"' in bloco and 'inputmode="numeric"' in bloco


def test_navegador_recusa_meio_integrante_e_calcula_inteiro():
    bloco = renderizar_calculo(_calculo(), titulo="Renda por pessoa", identidade="t")
    html = bloco.replace("<!-- wp:html -->", "").replace("<!-- /wp:html -->", "")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium indisponível: {exc}")
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.set_content(html)
        entradas = page.locator("input")
        saida = page.locator("[data-vc-out]")
        # com o script rodando, o aviso de fallback some da apresentação
        assert not page.locator("[data-vc-semjs]").is_visible()
        entradas.nth(0).fill("1500")
        entradas.nth(1).fill("1,5")
        assert saida.get_attribute("data-vc-status") == "invalid"
        assert "inteiro" in saida.inner_text()
        entradas.nth(1).fill("3")
        assert saida.get_attribute("data-vc-status") == "ok"
        assert saida.inner_text() == "500,00"
        browser.close()


def test_gate_final_aceita_a_calculadora_do_motor_e_so_ela():
    """Run final de 10/10: a pré-sell com a calculadora do motor caía no gate
    final por "campo de texto" e "JavaScript diferente"."""
    from funnelforge.domain.models import CalculoDoAtivo
    from funnelforge.pipeline.editorial_safety import html_issues
    from funnelforge.widgets.calculos import renderizar_calculo
    calc = CalculoDoAtivo(operacao="divisao", rotulos=["Renda total", "Pessoas"],
                          rotulo_resultado="Renda por pessoa", inteiros=[1],
                          casos=[{"entradas": ["3000", "3"], "resultado": "1000"},
                                 {"entradas": ["1000", "4"], "resultado": "250"}])
    bloco = renderizar_calculo(calc, titulo="Calcule a renda", identidade="p2")
    assert html_issues(bloco) == []
    adulterado = bloco.replace('var r=document', 'fetch("https://x.y");var r=document')
    assert any("JavaScript" in i.message for i in html_issues(adulterado))
    campo_solto = bloco.replace('<div class="vw-ctls">',
                                '<div class="vw-ctls"><input type="text" name="cpf">')
    assert any("dados pessoais" in i.message for i in html_issues(campo_solto))
