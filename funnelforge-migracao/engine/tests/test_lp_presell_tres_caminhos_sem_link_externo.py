"""LP com os 3 caminhos no herói mobile e LP/pré-sell sem link para outro site.

Decisão do operador (15/10/2026): 98% do tráfego é mobile; a LP oferece três
caminhos internos distintos (pré-sell, solução 1, solução 2) acima da dobra; LP
e pré-sell não têm link editorial externo; fonte e canal oficial clicáveis só
nas soluções. A regra de link é classificação objetiva de URL por papel da
página, não leitura de sentido: nenhum teste aqui exige palavra de CTA.
"""
import copy
import json

import pytest

from funnelforge.pipeline.editorial_safety import (
    href_externo, links_externos_por_papel, links_no_texto_da_lp, sem_ancoras,
)
from funnelforge.pipeline.lp_template import (
    _BUTTON_HREF, _SLOT_MAP, _fillable, load_lp_template, render_lp, validate_lp_content,
)
from funnelforge.pipeline.retry_policy import classe_da_issue
from funnelforge.pipeline.validators.checks import run_validators

SITE = "https://creditoup.com.br"
HREFS = [f"{SITE}/rec/por-onde-comecar-senac-pr", f"{SITE}/rec/tipos-de-curso-senac-p1",
         f"{SITE}/rec/bolsas-de-estudo-senac-p2"]
CONTENT = {
    "hero_title": "Cursos gratuitos no Senac",
    "hero_subtitle": "Renda de até 2 salários mínimos por pessoa.",
    "article_title": "Como funciona", "intro": "<p>Resposta curta.</p>",
    "sections": [{"title": f"S{i}", "body": f"<p>Corpo {i}.</p>"} for i in range(4)],
    "faq": [{"q": "Pergunta?", "a": "Resposta."}], "faq_title": "Dúvidas",
    "transition": "<p>Escolha o seu caminho.</p>",
    "cta_texts": ["Caminho A", "Caminho B", "Caminho C"],
}


def _herois(cont):
    mobile = next(n for n in cont if (n.get("settings") or {}).get("hide_desktop") == "hidden-desktop")
    desktop = next(n for n in cont if (n.get("settings") or {}).get("hide_mobile") == "hidden-mobile")
    return mobile, desktop


def _botoes(no):
    return [w for w in _fillable([no]) if w.get("widgetType") == "button"]


@pytest.mark.parametrize("rapido", [False, True])
def test_heroi_mobile_tem_os_tres_caminhos_na_ordem_pre_sell_s1_s2(rapido):
    cont, _ = render_lp(load_lp_template(), CONTENT, HREFS, id_seed="x",
                        hero_image_url=f"{SITE}/wp-content/uploads/hero.webp",
                        site_domain=SITE, copy_rapida=rapido)
    mobile, desktop = _herois(cont)
    for heroi in (mobile, desktop):
        botoes = _botoes(heroi)
        assert [b["settings"]["link"]["url"] for b in botoes] == HREFS
        assert [b["settings"]["text"] for b in botoes] == CONTENT["cta_texts"]
        assert len({b["settings"]["text"] for b in botoes}) == 3      # rótulos distintos


def test_rotulo_e_destino_usam_o_mesmo_indice_em_todo_botao():
    """O índice do rótulo (`_SLOT_MAP`) e o do destino (`_BUTTON_HREF`) são o
    mesmo para cada botão: rótulo e href nunca se trocam entre breakpoints."""
    rotulos = [ref for _i, (kind, ref) in sorted(_SLOT_MAP.items()) if kind == "button"]
    assert rotulos == [_BUTTON_HREF[n] for n in range(len(rotulos))]
    assert rotulos[:6] == [0, 1, 2, 0, 1, 2]


def test_heroi_mobile_ocupa_a_tela_com_o_conteudo_no_fim():
    """Decisão do operador (15/10/2026): o herói mobile tem a altura do celular
    (100vh), com título, subtítulo e botões no fim, sobre a foto com overlay."""
    mobile, _ = _herois(load_lp_template()["content"])
    s = mobile["settings"]
    assert s["min_height_mobile"] == {"unit": "vh", "size": 100, "sizes": []}
    assert s["flex_justify_content_mobile"] == "flex-end"
    assert s.get("background_overlay_background") == "classic"       # contraste na foto
    assert not any(n.get("widgetType") == "divider"
                   for n in mobile["elements"][0]["elements"])
    for b in _botoes(mobile):
        pad = b["settings"]["text_padding_mobile"]
        fonte = b["settings"]["typography_line_height_mobile"]["size"]
        assert int(pad["top"]) + int(pad["bottom"]) + fonte >= 44     # alvo de toque


def test_corpo_da_lp_em_montserrat_16_escuro_com_ritmo_de_lista():
    _, _ = _herois(load_lp_template()["content"])
    textos = [w for w in _fillable(load_lp_template()["content"][2:])
              if w.get("widgetType") == "text-editor"]
    assert textos
    for w in textos:
        s = w["settings"]
        assert s["typography_font_family"] == "Montserrat"
        assert s["typography_font_size_mobile"]["size"] == 16 and s["text_color"] == "#313131"
        assert "selector ul, selector ol" in s["custom_css"]


def test_aviso_de_identidade_do_motor_vai_para_o_fim_da_lp():
    cont, _ = render_lp(load_lp_template(), CONTENT, HREFS, site_domain=SITE, copy_rapida=True)
    marca = "sem vínculo com as instituições citadas"
    assert marca in json.dumps(cont[-1], ensure_ascii=False)
    assert marca not in json.dumps(cont[0], ensure_ascii=False)


def test_lp_com_link_externo_no_texto_e_recusada_estruturalmente():
    ruim = copy.deepcopy(CONTENT)
    ruim["sections"][1]["body"] = '<p>Veja no <a href="https://orango.senac.br/">Orango</a>.</p>'
    issues = validate_lp_content(ruim, technical_only=True)
    assert [i.code for i in issues] == ["link_no_texto_da_lp"]
    assert classe_da_issue(issues[0]) == "estrutural"


def test_lp_com_link_interno_no_texto_tambem_e_recusada():
    ruim = copy.deepcopy(CONTENT)
    ruim["intro"] = f'<p>Veja a <a href="{HREFS[1]}">conta</a>.</p>'
    assert [i.code for i in validate_lp_content(ruim, technical_only=True)] == ["link_no_texto_da_lp"]


def test_lp_sem_links_no_texto_continua_aceita():
    assert validate_lp_content(CONTENT, technical_only=True) == []


def test_renderer_recusa_botao_da_lp_para_outro_site():
    with pytest.raises(ValueError, match="outro site"):
        render_lp(load_lp_template(), CONTENT, [HREFS[0], "https://www.senac.br/", HREFS[2]],
                  site_domain=SITE)


def _ctx(papel):
    return {"role": papel, "domain": SITE, "editorial_v2": True}


def test_presell_com_link_externo_e_recusada_estruturalmente():
    corpo = ('<!-- wp:paragraph --><p>Segundo o <a href="https://www.planalto.gov.br/x">decreto</a>.'
             f'</p><!-- /wp:paragraph --><p><a href="{HREFS[1]}">curso</a></p>')
    issues = run_validators(["links_por_papel"], corpo, _ctx("PRESELL"))
    assert [i.code for i in issues] == ["link_externo_na_presell"]
    assert classe_da_issue(issues[0]) == "estrutural"


def test_presell_so_com_links_internos_e_aceita():
    corpo = f'<p><a href="{HREFS[1]}">curso</a> <a href="/rec/x">relativo</a> <a href="#topo">topo</a></p>'
    assert run_validators(["links_por_papel"], corpo, _ctx("PRESELL")) == []


def test_solucao_com_link_oficial_verificado_continua_aceita():
    corpo = '<p>Abra o <a href="https://www.sp.senac.br/bolsas-de-estudo">site do Senac SP</a>.</p>'
    assert run_validators(["links_por_papel"], corpo, _ctx("SOLUTION")) == []
    # papel ausente: nada é presumido (uma solução sem papel não perde o canal)
    assert run_validators(["links_por_papel"], corpo, {"domain": SITE}) == []


def test_nome_de_instituicao_em_prosa_nao_e_link():
    """Só href conta: citar 'gov.br' ou 'Senac' em texto não é link (sem lista de palavras)."""
    prosa = "<p>Segundo o gov.br e o site do Senac, o limite é de 2 salários mínimos.</p>"
    assert links_externos_por_papel(prosa, papel="PRESELL", dominio=SITE) == []
    assert links_no_texto_da_lp([prosa]) == []


def test_subdominio_do_proprio_site_nao_e_externo():
    assert not href_externo("https://www.creditoup.com.br/rec/a", SITE)
    assert not href_externo("https://cdn.creditoup.com.br/a.webp", SITE)
    assert href_externo("https://creditoup.com.br.golpe.com/a", SITE)


def test_sem_ancoras_preserva_o_texto():
    assert sem_ancoras('<p>Veja o <a href="https://x.com">site do X</a>.</p>') == \
        ("<p>Veja o site do X.</p>", 1)


def test_fonte_continua_no_pacote_mesmo_sem_link_no_html():
    """O redator da LP/pré-sell vê o NOME da fonte; a URL fica no pacote congelado."""
    from funnelforge.pipeline.inteligencia import _visao_sem_url_do_redator
    pacote = {"factual": {"fatos": [{"id": "f_000000000001", "afirmacao": "Limite de 2 SM",
                                     "fonte": "https://www.senac.br/psg"}],
                          "urls_oficiais": ["https://www.senac.br/psg"]},
              "jornada": {"dossie": {"fatos": [{"id": "f_000000000001",
                                                "fonte": "https://www.senac.br/psg"}]}}}
    original = copy.deepcopy(pacote)
    visao = _visao_sem_url_do_redator(copy.deepcopy(pacote))
    assert "https://www.senac.br/psg" not in json.dumps(visao)
    assert visao["factual"]["fatos"][0]["citar_como"]
    assert original["factual"]["fatos"][0]["fonte"] == "https://www.senac.br/psg"


def test_os_codigos_novos_sao_de_url_e_papel_nao_de_palavra():
    """Nenhum validador semântico novo: os códigos novos nascem só de href."""
    from funnelforge.pipeline.retry_policy import CODIGOS_PATCHAVEIS
    for code in ("link_externo_na_lp", "link_externo_na_presell", "link_no_texto_da_lp"):
        assert code not in CODIGOS_PATCHAVEIS


def _contraste(a, b):
    def lum(h):
        c = [int(h.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("rapido", [False, True])
def test_botoes_dos_herois_tem_contraste_aa_para_texto_de_15px(rapido):
    cont, _ = render_lp(load_lp_template(), CONTENT, HREFS, id_seed="x", site_domain=SITE,
                        hero_image_url=f"{SITE}/h.webp", copy_rapida=rapido)
    for heroi in _herois(cont):
        for b in _botoes(heroi):
            s = b["settings"]
            assert _contraste(s["background_color"], s["button_text_color"]) >= 4.5, s["text"]
