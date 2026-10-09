"""Hero da LP: situação do leitor, não natureza-morta de símbolos.

Regressão do run real da Tarifa Social (09/10/2026): o briefing só tinha H1,
objetivo e keywords, proibia âncoras do nicho e dizia "People are optional";
saiu lâmpada + tomada + calculadora, e o revisor aprovou porque só checava risco.
"""
from funnelforge.prompts import render


def _prompt(**extra):
    return render("image_prompt_lp_v2", headline="Tarifa Social de Energia Elétrica",
                  objective="Alívio de saber por onde começar", keywords=["tarifa social"],
                  page_number=1, previous_scenes=[], **extra)


def test_briefing_do_hero_leva_a_situacao_e_o_ganho_do_leitor():
    texto = _prompt(reader_question="Minha família tem direito ao desconto na conta de luz?",
                    reader_problem="Conta de luz pesando no orçamento",
                    reader_gain="Saber se atende aos critérios e o que fazer",
                    avatar="Famílias de baixa renda", dores=["conta de luz cara"])
    assert "Minha família tem direito ao desconto" in texto
    assert "Conta de luz pesando no orçamento" in texto
    assert "still life of generic symbols" in texto
    assert "People are optional" not in texto
    assert "never institutional trust anchors" not in texto


def test_revisor_do_hero_reprova_natureza_morta_so_no_hero():
    hero = render("image_review", headline="h", objective="o", keywords=[], hero=True,
                  no_generated_text=True)
    interna = render("image_review", headline="h", objective="o", keywords=[],
                     no_generated_text=True)
    assert "landing-page HERO" in hero
    assert "landing-page HERO" not in interna
