"""LP e pré-sell sem fonte externa clicável nem URL escrita no corpo.

Regra do dono (09/10): a pesquisa continua (fontes, datas e evidência ficam no
dossiê), mas o corpo da LP e da pré-sell não leva link externo, URL nem
"fonte: https://...". A solução pode linkar a saída oficial onde ela serve à
tarefa, uma vez por fonte. Evidência que motivou: run
`tarifa-social-energia-eletrica-20261009-validacao-real` — LP com
"(fonte: https://www.gov.br/aneel/...)" em texto e pré-sell com 13 `<a>` para o
mesmo endereço ("orientação da ANEEL, em site externo").
"""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

from funnelforge.domain.models import PageRole, ResearchFacts
from funnelforge.pipeline import inteligencia
from funnelforge.pipeline.base_factual import base_para_o_redator
from funnelforge.pipeline.steps import _sem_fontes_externas_no_corpo
from funnelforge.pipeline.validators.checks import _source_is_cited
from funnelforge.prompts import render

SITE = "https://creditoup.com.br"
ANEEL = "https://www.gov.br/aneel/pt-br/assuntos/tarifas/tarifa-social"
INTERNO = "https://creditoup.com.br/rec/como-obter-tarifa-social-p1"


# ----------------------------------------------------------------- sanitizador
def test_lp_remove_citacao_de_url_em_texto():
    obj = {
        "intro": ("<p>Os primeiros <strong>80 kWh mensais são gratuitos</strong> "
                  "(fonte: https://x.gov.br/a). Entenda a regra.</p>"),
        "sections": [{"title": "Quem tem direito", "body": (
            f"<p>Renda de até meio salário-mínimo. Fonte: {ANEEL}</p>"
            f"<p>Veja em {ANEEL}.</p>"
            f'<p>Continue no <a href="{INTERNO}">guia do pedido</a>.</p>')}],
        "faq": [{"q": "Quem paga?", "a": "A distribuidora aplica o desconto (fontes: https://a.gov.br/x; https://b.gov.br/y)."}],
    }
    out, total = _sem_fontes_externas_no_corpo(obj, SITE)
    texto = json.dumps(out, ensure_ascii=False)
    assert total == 4
    assert "http" not in texto.replace(INTERNO, "")
    assert "fonte" not in texto.lower()
    assert out["intro"] == ("<p>Os primeiros <strong>80 kWh mensais são gratuitos</strong>. "
                            "Entenda a regra.</p>")
    assert "<p>Renda de até meio salário-mínimo.</p>" in out["sections"][0]["body"]
    assert "<p>Veja em.</p>" in out["sections"][0]["body"]   # a URL nua sai, a frase fica
    assert f'<a href="{INTERNO}">guia do pedido</a>' in out["sections"][0]["body"]
    assert out["faq"][0]["a"] == "A distribuidora aplica o desconto."


def test_presell_gutenberg_desembrulha_link_externo_e_preserva_botao_do_funil():
    html = (
        "<!-- wp:paragraph --><p>Renda de até meio salário-mínimo por pessoa, conforme a "
        f'<a href="{ANEEL}">orientação da ANEEL, em site externo</a>.</p><!-- /wp:paragraph -->'
        f'<!-- wp:paragraph --><p>Segundo a <a href="{ANEEL}">ANEEL</a>, em site externo, '
        "o desconto é automático.</p><!-- /wp:paragraph -->"
        '<!-- wp:buttons --><div class="wp-block-buttons"><!-- wp:button -->'
        '<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" '
        f'href="{INTERNO}">Entender como obter o desconto</a></div>'
        "<!-- /wp:button --></div><!-- /wp:buttons -->"
        '<!-- wp:buttons --><div class="wp-block-buttons"><!-- wp:button -->'
        '<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" '
        f'href="{ANEEL}">Ver no site da ANEEL</a></div>'
        "<!-- /wp:button --></div><!-- /wp:buttons -->"
    )
    out, total = _sem_fontes_externas_no_corpo(html, SITE)
    assert total == 3
    assert ANEEL not in out
    assert "site externo" not in out
    assert "conforme a orientação da ANEEL.</p>" in out
    assert "<p>Segundo a ANEEL, o desconto é automático.</p>" in out
    # botão do funil intacto; botão para fora do site sai inteiro (sem wrapper vazio)
    assert f'href="{INTERNO}">Entender como obter o desconto</a>' in out
    assert "Ver no site da ANEEL" not in out
    assert out.count("<!-- wp:buttons -->") == 1


def test_sanitizador_nao_mexe_em_atributo_nem_em_link_relativo_do_funil():
    html = ('<!-- wp:image {"url":"https://cdn.exemplo.com/a.webp"} --><figure>'
            '<img src="https://cdn.exemplo.com/a.webp" alt=""/></figure><!-- /wp:image -->'
            '<p><a href="/rec/pedir-p2">pedir</a></p>')
    out, total = _sem_fontes_externas_no_corpo(html, SITE)
    assert (out, total) == (html, 0)


_HTML_COM_FONTE = (
    "<!-- wp:paragraph --><p>Renda de até meio salário-mínimo, conforme a "
    f'<a href="{ANEEL}">ANEEL, em site externo</a> (fonte: {ANEEL}).</p><!-- /wp:paragraph -->'
    "<!-- wp:paragraph --><p>Segundo parágrafo.</p><!-- /wp:paragraph -->"
)


def _escrever_v2(config_files, monkeypatch, slug):
    """`step_write` do ramo novo com redação fixa (sem LLM, sem briefing real)."""
    from funnelforge.config.settings import load_settings
    from funnelforge.domain.models import FunnelPlan, Page, RunState, StepResult, StepStatus
    from funnelforge.pipeline import steps as st
    from funnelforge.pipeline.pipeline import Deps
    from funnelforge.pipeline.routing import build_funnel_routes

    plan = FunnelPlan(total_pages=3, pages=[
        Page(page_number=1, page_type="LANDING PAGE", h1_title="Tarifa social", slug="a"),
        Page(page_number=2, page_type="HUB", h1_title="Quem tem direito", slug="a-pr1",
             role=PageRole.PRESELL),
        Page(page_number=3, page_type="SOLUTION", h1_title="Como pedir o desconto",
             slug="a-p1", ordinal=1),
    ])
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    build_funnel_routes(plan, settings)
    page = next(p for p in plan.pages if p.slug == slug)

    class _Runner:
        def run_llm_step(self, *a, **k):
            return _HTML_COM_FONTE, StepResult(step="write", status=StepStatus.OK)

    deps = Deps(llm=None, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=None, settings=settings, runner=_Runner())
    for nome, valor in {"briefing_para_o_redator": lambda b: "BRIEFING",
                        "passos_por_destino": lambda b: {},
                        "plano_visual_da_pagina": lambda p, b: [],
                        "exigencia_visual_da_pagina": lambda p, b: [],
                        "preflight_issues": lambda *a: []}.items():
        monkeypatch.setattr(st, nome, valor)
    state = RunState(run_id="a-20261009-120000", plan=plan, editorial_v2=True,
                     briefings={page.page_number: {}},
                     facts={page.page_number: ResearchFacts(fontes_resolvidas=[ANEEL])})
    st.step_write(state, page, deps)
    return state.drafts[page.page_number].content, state.normalizacoes.get(page.page_number, [])


def test_step_write_da_presell_sai_sem_fonte_externa(config_files, monkeypatch):
    content, normalizacoes = _escrever_v2(config_files, monkeypatch, "a-pr1")
    assert ANEEL not in content and "site externo" not in content
    assert "conforme a ANEEL.</p>" in content
    recibo = [n for n in normalizacoes if n["etapa"] == "fontes_externas_da_presell_em_prosa"]
    assert recibo and recibo[0]["quantidade"] == 2


def test_step_write_da_solucao_nao_passa_pelo_sanitizador(config_files, monkeypatch):
    content, normalizacoes = _escrever_v2(config_files, monkeypatch, "a-p1")
    assert f'<a href="{ANEEL}">ANEEL, em site externo</a>' in content
    assert not any(n["etapa"].startswith("fontes_externas") for n in normalizacoes)


def test_presell_sem_url_cita_pelo_host_como_a_lp():
    corpo = "<p>Segundo o site gov.br, são 65 anos.</p>"
    for papel in (PageRole.LP, PageRole.PRESELL):
        assert _source_is_cited(corpo, ANEEL, {"role": papel})
    assert not _source_is_cited(corpo, ANEEL, {"role": PageRole.SOLUTION})


# ------------------------------------------------------------------- prompts
_JORNADA = {
    "pergunta": "Quem tem direito?", "trabalho": "", "resposta_imediata": "Renda até meio SM",
    "coortes": [], "entrada_direta": "", "resolvido_em_todo_caminho": [], "talvez_resolvido": [],
    "proxima_duvida": "", "tensao_residual": "", "condicao_terminal": "", "destinos": [],
    "saida_oficial": {"classificacao": "boa", "condicao": ""},
    "monetizacao": {"papel": "neutro", "restricoes": []}, "valor": {}, "plano_visual": [],
    "ativos": [], "papel": "LP",
    "dossie": {"sha256": "a" * 64, "degradacoes": [], "vinculos": [
        {"ativo": "calc", "papel": "regra", "fact_id": "f_1", "url": ANEEL, "nivel": "federal",
         "jurisdicao": "", "vigente_desde": "", "abrangencia": "nacional"}],
        "fatos": [{"id": "f_1", "afirmacao": "Gratuidade até 80 kWh.", "valor": "80",
                   "unidade": "kWh", "derivacao": "", "premissas": [], "fonte": ANEEL,
                   "emissor": "", "abrangencia": "", "vigente_desde": "2025-07-05"}]},
}
_COMUM = dict(
    headline="Tarifa social", objective="Confirmar o direito", skeleton="- a", keywords="tarifa",
    cta_text="Ver", today="09/10/2026", domain=SITE, briefing_texto="BRIEFING",
    author_name="Equipe", author_credential="", cnpj="", escrita_natural=True,
)
_FATOS = ResearchFacts(
    dados_validados=[{"tipo": "condicao", "fato": "Renda de até meio salário-mínimo.",
                      "fonte": ANEEL, "citavel": True}],
    fontes_resolvidas=[ANEEL])
_ROTAS = [{"kind": "funnel", "anchor": "Como pedir", "href": INTERNO, "reason": "r"}]


def _render(nome, papel, **extra):
    jornada = dict(_JORNADA, papel=papel)
    return render(nome, jornada=jornada, routes=_ROTAS, official_links=[ANEEL],
                  role=papel, **dict(_COMUM, **extra))


def test_prompt_da_lp_e_da_presell_sem_url_de_fato_e_sem_mesma_frase_do_link():
    lp = _render("redator_p1_v2", "LP", lp_destinations=[],
                 facts=base_para_o_redator(_FATOS, destino_pago=True))
    presell = _render("redator_presell_v2", "PRESELL",
                      facts=base_para_o_redator(_FATOS, destino_pago=True))
    for out in (lp, presell):
        assert ANEEL not in out
        assert "mesma frase que o link" not in out
        assert "MESMA frase, o link" not in out
        assert "inclua este link" not in out
        assert '<a href="https://...">' not in out
        assert "[f_1] Gratuidade até 80 kWh." in out     # o fato e o id continuam
        assert "citar como: gov.br" in out               # pelo NOME, sem URL
        assert "em site externo" not in out
    assert "Links externos são identificados como externos" not in presell
    assert "Não há link externo nesta página." in presell


def test_prompt_da_solucao_linka_uma_vez_por_fonte():
    out = _render("redator_pages_v2", "SOLUTION",
                  facts=base_para_o_redator(_FATOS, link_unico=True))
    assert f"fonte: {ANEEL}" in out                     # a solução pode linkar
    assert "mesma frase que o link" not in out
    assert "inclua este link na MESMA frase" not in out
    assert "no máximo UMA vez por fonte" in out
    assert "uma vez, no ponto em que o leitor age ou confere" in out
    assert "não acrescente \"em site externo\" a cada menção" in out


def test_pacote_da_presell_chega_ao_redator_sem_url_e_sem_mutar_o_pacote(monkeypatch):
    pacote = {
        "pagina": {"page_type": "HUB", "role": "PRESELL", "h1_title": "Quem tem direito",
                   "emotional_objective": "o", "main_content_structure": [],
                   "target_keywords": [], "hook_to_next_page": "h", "page_number": 2,
                   "engajamento": "", "editorial": {"links": []}},
        "jornada": copy.deepcopy(_JORNADA) | {"papel": "PRESELL", "condicao_terminal": ""},
        "destinos": [], "links": [{"kind": "funnel", "href": INTERNO, "anchor": "Como pedir"}],
        "factual": {"fatos": [{"id": "f_1", "afirmacao": "Gratuidade até 80 kWh.",
                               "fonte": ANEEL}], "urls_oficiais": [ANEEL]},
        "total_pages": 6, "dominio": SITE, "autor": "Equipe", "credencial": "", "cnpj": "",
        "data": "09/10/2026", "sha256": "x",
    }
    original = copy.deepcopy(pacote)
    monkeypatch.setattr(inteligencia, "pacote_conferido", lambda *a: copy.deepcopy(pacote))
    prompt = inteligencia.prompt_do_pacote(None, SimpleNamespace(page_number=2))
    assert ANEEL not in prompt
    # O fato vai uma vez, na lista do DOSSIÊ da jornada, com o nome a citar.
    assert "citar como: gov.br" in prompt
    assert "sem hyperlink externo no corpo" in prompt
    assert pacote == original                            # o dossiê guarda a fonte


def test_patch_do_revisor_na_presell_nao_reintroduz_fonte_externa(config_files, monkeypatch):
    """O revisor roda depois do saneador: um patch com link externo muda os
    hrefs no `normalizar` e a rodada o recusa (`estrutura_alterada`)."""
    from types import SimpleNamespace as NS
    from funnelforge.pipeline import steps as st

    capturado = {}
    original = st.ContextoDaRevisao

    def contexto(**kw):
        capturado.update(kw)
        return original(**kw)

    for nome, valor in {"montar_inventario": lambda s, p: NS(
            fatos=[], fontes=[], termos_de_busca=NS(amostra=[], estado="ausente", janela="",
                                                     motivo_ausencia=""),
            anuncio=NS(titulos=[], descricoes=[], estado="ausente", model_dump=lambda: {}),
            leitura=NS(perguntas_paa=[])),
                        "inventario_para_o_briefing": lambda inv, **kw: "",
                        "destinos_da_pagina": lambda s, p: [],
                        "_issues_da_pagina": lambda *a: [],
                        "contexto_de_jornada": lambda *a: None,
                        "ContextoDaRevisao": contexto}.items():
        monkeypatch.setattr(st, nome, valor, raising=False)
    _escrever_v2(config_files, monkeypatch, "a-pr1")
    from funnelforge.config.settings import load_settings
    from funnelforge.domain.models import FunnelPlan, Page, RunState
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    page = Page(page_number=2, page_type="HUB", h1_title="Quem tem direito", slug="a-pr1",
                role=PageRole.PRESELL)
    state = RunState(run_id="r", plan=FunnelPlan(total_pages=1, pages=[page]), editorial_v2=True)
    deps = NS(settings=settings)
    doc = NS(formato="gutenberg", corpo=f'<p>Segundo a <a href="{ANEEL}">ANEEL</a>.</p>')
    try:
        st._contexto_da_revisao(state, page, deps, doc)
    except Exception:  # noqa: BLE001 - só o normalizar interessa aqui
        pass
    normalizar = capturado.get("normalizar")
    assert normalizar is not None
    monkeypatch.setattr(st, "_substituir", lambda d, corpo: NS(formato=d.formato, corpo=corpo))
    novo, _ = normalizar(doc)
    assert ANEEL not in novo.corpo


def test_presell_cita_pelo_nome_da_instituicao_da_fonte():
    """Run real 09/10: "65 anos, segundo a ANEEL" reprovava 3 vezes porque o
    portão só aceitava o host "gov.br" escrito, contra a regra de não escrever
    endereço no corpo."""
    corpo = "<p>A modalidade do BPC exige pelo menos 65 anos, segundo a ANEEL.</p>"
    for papel in (PageRole.LP, PageRole.PRESELL):
        assert _source_is_cited(corpo, ANEEL, {"role": papel})
    assert not _source_is_cited(corpo, ANEEL, {"role": PageRole.SOLUTION})
    caixa = "https://www.caixa.gov.br/beneficios-trabalhador/pis"
    assert _source_is_cited("<p>Segundo a Caixa, o saque…</p>", caixa, {"role": PageRole.LP})
    # um rótulo genérico ou outra instituição não substitui o emissor
    assert not _source_is_cited("<p>Segundo o governo (gov), …</p>", ANEEL, {"role": PageRole.LP})
    assert not _source_is_cited("<p>Segundo o MDS, …</p>", ANEEL, {"role": PageRole.PRESELL})
