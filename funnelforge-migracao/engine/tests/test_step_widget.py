# funnel-forge/tests/test_step_widget.py
"""CARD-0013: the interactive-widget subsystem for SOLUTION pages.

A gated (`run.widgets_enabled`, default OFF), 100%-fail-safe step calls a
generator prompt that returns EXACTLY ONE self-contained `<!-- wp:html -->`
block (or the literal string NONE). A hard Python sanitization battery
(allowlist + blockers, NO real JS parse -- see test_validators.py) decides
inject-or-reject; the injector places the block before the 3rd H2 (fallbacks:
before the FAQ heading, else the end). ANY failure -- NONE, LLM error,
sanitization rejection, exception -- leaves the article INTACT, records a
non-blocking SKIPPED `widget_p{n}` with `widget_rejected` + a machine-readable
`widget_error` label, and NEVER fails a good page. With the flag OFF the step
never runs and the pipeline is byte-for-byte the current one.

No network: a FakeLLM serves fixed widget text and the sanitizer/injector are
pure functions.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from funnelforge.config.settings import (
    RunConfig,
    Secrets,
    Settings,
    SiteConfig,
    StepConfig,
    load_settings,
)
from funnelforge.domain.models import (
    FunnelPlan,
    Page,
    PageDraft,
    PageRole,
    RunState,
    StepResult,
    StepStatus,
)
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.pipeline import Deps, run_pipeline
from funnelforge.pipeline.runner import Runner
from funnelforge.prompts import render
from tests.fakes import FakeLLM

# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #

# ⚠️ O MODELO NÃO DEVOLVE MAIS HTML.
#
# Até 19/08/2026 este arquivo carregava um bloco `wp:html` completo como
# resposta da LLM, e catorze mutações dele — uma por rótulo do sanitizador
# (`ampersand_in_script`, `tag_not_allowed`, `attribute_not_allowed`, …).
# Aquelas catorze falhas eram REAIS e caras: uma delas, um único `&`, derrubou
# a p3 do run #4 e levou junto US$ 0,79 de artigo pronto.
#
# Elas não são mais possíveis. O modelo devolve JSON de conteúdo e
# `funnelforge/widgets/render.py` imprime o HTML — sempre o mesmo, sempre com
# as mesmas tags. Que o gabarito passa no sanitizador é provado sobre os quatro
# arquétipos em `tests/test_widgets.py::test_todo_arquetipo_passa_no_sanitizador`.
#
# O que sobra de falível aqui embaixo é só o CONTEÚDO.
_JSON_VALIDO = """{
  "arquetipo": "diagnostico",
  "titulo": "O que travou o seu saque",
  "subtitulo": "Escolha o que aconteceu.",
  "controles": [{"id": "sintoma", "rotulo": "O que aconteceu?", "opcoes": [
    {"valor": "negado", "texto": "Negaram o meu pedido"},
    {"valor": "analise", "texto": "Esta em analise"}]}],
  "cenarios": [
    {"quando": {"sintoma": "negado"}, "chip": "conta bloqueada", "tom": "risco",
     "titulo": "O pedido so avanca com a conta ativa", "corpo": "A conta precisa estar ativa."},
    {"quando": {"sintoma": "analise"}, "chip": "prazo normal", "tom": "atencao",
     "titulo": "A analise segue no prazo", "corpo": "Ha conferencia antes do credito."}
  ],
  "rodape": "Fonte: canais oficiais citados no texto."
}"""


def _jsons_ruins() -> dict[str, str]:
    """Um JSON inválido por modo de falha que AINDA existe.

    Todos caem no mesmo rótulo `widget_conteudo_invalido`, e a diferença está
    na frase que volta para o modelo — é ela que a retentativa usa.
    """
    return {
        "cenario_em_branco": _JSON_VALIDO.replace(
            '"corpo": "A conta precisa estar ativa."', '"corpo": ""', 1).replace(
            '"corpo": "Ha conferencia antes do credito."', '"corpo": ""', 1),
        "combinacao_descoberta": _JSON_VALIDO.replace('"sintoma": "analise"',
                                                      '"sintoma": "negado"', 1),
        "um_cenario_so": _JSON_VALIDO.replace(
            ',\n    {"quando": {"sintoma": "analise"}, "chip": "prazo normal", '
            '"tom": "atencao",\n     "titulo": "A analise segue no prazo", '
            '"corpo": "Ha conferencia antes do credito."}', "", 1),
        "opcao_unica": _JSON_VALIDO.replace(
            ',\n    {"valor": "analise", "texto": "Esta em analise"}', "", 1),
        "arquetipo_inexistente": _JSON_VALIDO.replace('"diagnostico"', '"calculadora"', 1),
        "json_malformado": '{"arquetipo": "diagnostico", }',
    }


def _h2(text: str) -> str:
    return f"<!-- wp:heading --><h2>{text}</h2><!-- /wp:heading -->"


def _p(text: str) -> str:
    return f"<!-- wp:paragraph --><p>{text}</p><!-- /wp:paragraph -->"


_FAQ = "<!-- wp:heading --><h2>Perguntas Frequentes</h2><!-- /wp:heading -->"


def _article_4h2() -> str:
    return "\n".join([
        _h2("Introducao ao tema"), _p("Abertura direta."),
        _h2("Passo dois do guia"), _p("Corpo dois."),
        _h2("Passo tres do guia"), _p("Corpo tres."),
        _h2("Passo quatro do guia"), _p("Corpo quatro."),
    ])


def _settings(*, widgets_enabled: bool = True, model: str = "widget-model") -> Settings:
    return Settings(
        secrets=Secrets(),
        run=RunConfig(widgets_enabled=widgets_enabled),
        site=SiteConfig(domain="https://creditoup.com.br"),
        steps={"widget": StepConfig(model=model, fallbacks=[], temperature=0.5, validators=[])},
    )


def _deps(tmp_path: Path, settings: Settings, llm: FakeLLM) -> Deps:
    runner = Runner(llm=llm, max_retries=0, runs_dir=tmp_path / "runs")
    return Deps(llm=llm, research=None, image_gen=None, image_proc=None,
                publisher=None, loader=None, settings=settings, runner=runner)


def _solution_page(n: int = 3) -> Page:
    return Page(page_number=n, page_type="SOLUTION", h1_title="Saque FGTS apos demissao",
                slug=f"saque-fgts-p{n}", ordinal=1, role=PageRole.SOLUTION)


def _errors(res: StepResult) -> list[str]:
    """The machine-readable widget_error label(s): every issue code except the
    `widget_rejected` marker."""
    return [i.code for i in res.issues if i.code != "widget_rejected"]


def _rejected(res: StepResult) -> bool:
    return any(i.code == "widget_rejected" for i in res.issues)


# =========================================================================== #
# AC4: injector -- before the 3rd H2, fallbacks FAQ / end, \n\n fencing
# =========================================================================== #
_BLOCK = '<!-- wp:html -->\n<div id="wg-z"></div>\n<!-- /wp:html -->'


def test_inject_before_third_h2_with_four_h2():
    out = st.inject_widget(_article_4h2(), _BLOCK)
    w = out.index("<!-- wp:html -->")
    assert out.index("Passo dois do guia") < w < out.index("Passo tres do guia")
    assert "\n\n<!-- wp:html -->" in out          # blank line before
    assert "<!-- /wp:html -->\n\n" in out          # blank line after


def test_inject_fallback_before_faq_when_under_three_h2():
    content = _h2("Introducao") + _p("a") + _h2("Passo dois") + _p("b") + _FAQ + _p("resposta")
    out = st.inject_widget(content, _BLOCK)
    w = out.index("<!-- wp:html -->")
    assert out.index("Passo dois") < w < out.index("Perguntas Frequentes")


def test_inject_before_last_h2_when_one_or_two_h2_and_no_faq():
    """Defense in depth (p2/celular fix): with 1-2 content H2 and no FAQ, the
    widget anchors BEFORE the LAST content H2 -- inside the article, never
    dumped at the decontextualized tail."""
    content = _h2("Introducao") + _p("a") + _h2("Passo dois") + _p("b")
    out = st.inject_widget(content, _BLOCK)
    w = out.index("<!-- wp:html -->")
    assert out.index("Introducao") < w < out.index("Passo dois")
    assert not out.rstrip().endswith("<!-- /wp:html -->")


def test_inject_appends_to_end_only_when_no_heading_at_all():
    content = _p("a") + _p("b")  # zero headings -> nothing to anchor before
    out = st.inject_widget(content, _BLOCK)
    assert out.rstrip().endswith("<!-- /wp:html -->")
    assert "\n\n<!-- wp:html -->" in out


def test_inject_does_not_count_faq_heading_toward_the_three_h2():
    """A FAQ heading is reserved for its own fallback, never counted as one of the
    3 content H2 -- so `2 content H2 + FAQ` takes the FAQ branch (before FAQ),
    NOT the 3rd-H2 branch."""
    content = (_h2("Um") + _p("a") + _h2("Dois") + _p("b") + _FAQ + _p("c"))
    out = st.inject_widget(content, _BLOCK)
    assert out.index("<!-- wp:html -->") < out.index("Perguntas Frequentes")


# =========================================================================== #
# AC1: gating -> silent no-op (flag off byte-identical; non-SOLUTION role)
# =========================================================================== #
def test_step_widget_noop_when_flag_off(tmp_path: Path):
    llm = FakeLLM(responses=[_JSON_VALIDO])
    deps = _deps(tmp_path, _settings(widgets_enabled=False), llm)
    state = RunState(run_id="r")
    original = _article_4h2()
    state.drafts[3] = PageDraft(page_number=3, page_type="SOLUTION",
                                format="gutenberg", content=original)

    st.step_widget(state, _solution_page(), deps)

    assert state.drafts[3].content == original     # byte-identical, no injection
    assert "widget_p3" not in state.step_status     # gated -> nothing recorded
    assert llm.calls == []                           # no LLM call at all


def test_step_widget_noop_for_non_solution_role(tmp_path: Path):
    llm = FakeLLM(responses=[_JSON_VALIDO])
    deps = _deps(tmp_path, _settings(), llm)
    state = RunState(run_id="r")
    original = _article_4h2()
    for n, role, slug in ((2, PageRole.PRESELL, "quem-tem-direito-pr"),
                          (1, PageRole.LP, "saque-fgts")):
        state.drafts[n] = PageDraft(page_number=n, page_type=role.value,
                                    format="gutenberg", content=original)
        page = Page(page_number=n, page_type=role.value, h1_title="T", slug=slug, role=role)
        st.step_widget(state, page, deps)
        assert state.drafts[n].content == original
        assert f"widget_p{n}" not in state.step_status
    assert llm.calls == []


# =========================================================================== #
# AC1: NONE / empty -> no injection, non-blocking SKIPPED, article intact
# =========================================================================== #
def test_step_widget_none_response_leaves_article_intact(tmp_path: Path):
    llm = FakeLLM(responses=["NONE"])
    deps = _deps(tmp_path, _settings(), llm)
    state = RunState(run_id="r")
    original = _article_4h2()
    state.drafts[3] = PageDraft(page_number=3, page_type="SOLUTION",
                                format="gutenberg", content=original)

    st.step_widget(state, _solution_page(), deps)

    assert state.drafts[3].content == original     # no injection
    res = state.step_status["widget_p3"]
    assert res.status is StepStatus.SKIPPED and res.status is not StepStatus.FAILED
    assert _rejected(res) and "widget_none" in _errors(res)   # benign, no error/exception


def test_step_widget_empty_response_is_skipped(tmp_path: Path):
    llm = FakeLLM(responses=["   \n  "])
    deps = _deps(tmp_path, _settings(), llm)
    state = RunState(run_id="r")
    original = _article_4h2()
    state.drafts[3] = PageDraft(page_number=3, page_type="SOLUTION",
                                format="gutenberg", content=original)

    st.step_widget(state, _solution_page(), deps)

    assert state.drafts[3].content == original
    assert state.step_status["widget_p3"].status is StepStatus.SKIPPED
    assert "widget_empty" in _errors(state.step_status["widget_p3"])


def test_step_widget_non_wp_html_output_is_skipped(tmp_path: Path):
    prosa = "Claro! Aqui vai um widget: <div>oi</div>"
    llm = FakeLLM(responses=[prosa, prosa])   # o passo retenta uma vez
    deps = _deps(tmp_path, _settings(), llm)
    state = RunState(run_id="r")
    original = _article_4h2()
    state.drafts[3] = PageDraft(page_number=3, page_type="SOLUTION",
                                format="gutenberg", content=original)

    st.step_widget(state, _solution_page(), deps)

    assert state.drafts[3].content == original
    # Antes o rótulo era `widget_no_block` ("a saída não é UM bloco wp:html").
    # Não há mais bloco para contar: prosa sem JSON é conteúdo inválido.
    assert "widget_conteudo_invalido" in _errors(state.step_status["widget_p3"])


# =========================================================================== #
# AC1/AC4: a VALID widget is sanitized and injected before the 3rd H2
# =========================================================================== #
def test_step_widget_injects_valid_widget_before_third_h2(tmp_path: Path):
    llm = FakeLLM(responses=[_JSON_VALIDO])
    deps = _deps(tmp_path, _settings(), llm)
    state = RunState(run_id="r")
    state.drafts[3] = PageDraft(page_number=3, page_type="SOLUTION",
                                format="gutenberg", content=_article_4h2())

    st.step_widget(state, _solution_page(), deps)

    body = state.drafts[3].content
    assert "<!-- wp:html -->" in body                       # injected
    assert 'class="vw"' in body                             # é o gabarito da casa
    assert "O pedido so avanca com a conta ativa" in body            # o conteúdo chegou
    w = body.index("<!-- wp:html -->")
    assert body.index("Passo dois do guia") < w < body.index("Passo tres do guia")
    res = state.step_status["widget_p3"]
    assert res.status is StepStatus.OK
    assert llm.calls and llm.calls[0]["model"] == "widget-model"


# =========================================================================== #
# AC1/AC3: one rejection case per sanitization label -> widget_rejected +
# correct widget_error label + article INTACT (never FAILED, never blocking)
# =========================================================================== #
#: O que a recusa tem de DIZER em cada caso. O rótulo é sempre o mesmo
#: (`widget_conteudo_invalido`); o que muda — e o que a retentativa usa — é a
#: frase. "Inválido" sozinho não conserta nada.
_FRASE_DA_RECUSA = {
    "cenario_em_branco": "resultado em branco",
    "combinacao_descoberta": "sintoma=analise",
    "um_cenario_so": "o mínimo é 2",
    "opcao_unica": "mínimo é 2",
    "arquetipo_inexistente": "arquetipo",
    "json_malformado": "JSON malformado",
}


@pytest.mark.parametrize("caso,cru", list(_jsons_ruins().items()))
def test_step_widget_rejects_each_label_and_keeps_article(tmp_path: Path, caso: str, cru: str):
    # DUAS respostas iguais: o passo RETENTA uma vez, com o motivo apontado no
    # prompt. Devolver o mesmo JSON ruim nas duas prova o que este teste existe
    # para provar — que o contrato recusa, e que a retentativa NÃO o afrouxa.
    llm = FakeLLM(responses=[cru, cru])
    deps = _deps(tmp_path, _settings(), llm)
    state = RunState(run_id="r")
    original = _article_4h2()
    state.drafts[3] = PageDraft(page_number=3, page_type="SOLUTION",
                                format="gutenberg", content=original)

    st.step_widget(state, _solution_page(), deps)

    assert state.drafts[3].content == original             # artigo intacto, sem widget
    res = state.step_status["widget_p3"]
    assert res.status is StepStatus.SKIPPED
    assert res.status is not StepStatus.FAILED
    assert _rejected(res)
    assert "widget_conteudo_invalido" in _errors(res)
    # A recusa nomeia O QUE faltou — é isso que volta para o modelo.
    ditos = " ".join(i.message for i in res.issues)
    assert _FRASE_DA_RECUSA[caso] in ditos, ditos


# =========================================================================== #
# AC1: an LLM exception is swallowed -> SKIPPED (never FAILED), article intact
# =========================================================================== #
def test_step_widget_llm_exception_is_skipped_never_fatal(tmp_path: Path):
    def _boom(model, messages):
        raise RuntimeError("provider down")

    llm = FakeLLM(responses=_boom)
    deps = _deps(tmp_path, _settings(), llm)
    state = RunState(run_id="r")
    original = _article_4h2()
    state.drafts[3] = PageDraft(page_number=3, page_type="SOLUTION",
                                format="gutenberg", content=original)

    st.step_widget(state, _solution_page(), deps)          # must NOT raise

    assert state.drafts[3].content == original
    res = state.step_status["widget_p3"]
    assert res.status is StepStatus.SKIPPED
    assert res.status is not StepStatus.FAILED
    assert _rejected(res)


def test_step_widget_llm_failed_result_is_skipped(tmp_path: Path):
    """A FAILED LLM StepResult (validators/retries exhausted) is treated as a
    non-blocking widget skip, article intact."""
    # widget cfg has a validator that always fails -> run_llm_step returns FAILED
    settings = _settings()
    settings.steps["widget"] = StepConfig(model="widget-model", fallbacks=[],
                                          temperature=0.5, validators=["gutenberg_blocks"])
    llm = FakeLLM(responses=["<!-- wp:html --><div><script>x</script></div><!-- /wp:html -->"])
    deps = _deps(tmp_path, settings, llm)
    state = RunState(run_id="r")
    original = _article_4h2()
    state.drafts[3] = PageDraft(page_number=3, page_type="SOLUTION",
                                format="gutenberg", content=original)

    st.step_widget(state, _solution_page(), deps)

    assert state.drafts[3].content == original
    res = state.step_status["widget_p3"]
    assert res.status is StepStatus.SKIPPED
    assert "widget_llm_error" in _errors(res)


# =========================================================================== #
# AC5: redator_widget.jinja generator prompt contract
# =========================================================================== #
def test_widget_prompt_contract_and_guardrails():
    p = render("redator_widget", country="Brasil", year=2026,
               title="Saque FGTS apos demissao", article="<p>CORPO-DO-ARTIGO-AQUI</p>",
               arquetipo="roteador", facts="n1: 3 saques por ano")

    # A saída é JSON. `NONE` continua sendo a fuga honesta quando a peça não
    # agrega — tirá-la faria o modelo inventar widget onde não cabe.
    assert "NONE" in p
    assert "objeto JSON" in p
    # o artigo entra como DADO, com a anti-injeção em volta
    assert "CORPO-DO-ARTIGO-AQUI" in p
    low = p.lower()
    assert "dado" in low and ("ignore" in low or "ignorar" in low)
    # a base factual viaja: o widget é o único componente que escrevia texto
    # publicado sem saber quais números são permitidos
    assert "3 saques por ano" in p
    assert "FATOS AUTORIZADOS" in p
    # salvaguardas de tom que sobrevivem à troca de arquitetura
    assert "urg" in low                                     # sem urgência fabricada
    assert "não agregar" in low or "nao agregar" in low
    # contexto na superfície
    assert "Brasil" in p and "2026" in p and "Saque FGTS apos demissao" in p


# =========================================================================== #
# AC2: pipeline wiring -- step runs AFTER build, BEFORE publish; fail-safe; and
# with the flag OFF the pipeline is byte-for-byte the current one.
# =========================================================================== #
class _FakePublisher:
    def __init__(self) -> None:
        self.post_call: dict | None = None

    def create_post(self, title, content, slug, status, post_type, featured_media=None):
        self.post_call = {"content": content, "status": status}
        return {"id": 7}

    def set_yoast(self, post_id, post_type, fields, status=None):
        return {}

    def set_status(self, post_id, post_type, status):
        return {}


def _wiring_state() -> RunState:
    plan = FunnelPlan(total_pages=1, pages=[_solution_page()])
    state = RunState(run_id="saque-fgts-p3-20260721")
    state.plan = plan
    state.seo[3] = {}
    state.drafts[3] = PageDraft(page_number=3, page_type="SOLUTION",
                                format="gutenberg", content=_article_4h2())
    for k in ("research_p3", "write_p3", "seo_p3"):
        state.step_status[k] = StepResult(step=k, status=StepStatus.OK)
    return state


def _wiring_deps(tmp_path: Path, config_files: Path, *, widgets_enabled: bool,
                 llm: FakeLLM, publisher) -> Deps:
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    settings.run.widgets_enabled = widgets_enabled
    settings.run.featured_image = False
    settings.steps["widget"] = StepConfig(model="widget-model", fallbacks=[],
                                           temperature=0.5, validators=[])
    runner = Runner(llm=llm, max_retries=0, runs_dir=tmp_path / "runs")
    return Deps(llm=llm, research=None, image_gen=None,
                image_proc=None, publisher=publisher, loader=None,
                settings=settings, runner=runner)


def test_pipeline_injects_widget_between_build_and_publish(tmp_path: Path, config_files: Path):
    pub = _FakePublisher()
    llm = FakeLLM(responses=[_JSON_VALIDO])
    deps = _wiring_deps(tmp_path, config_files, widgets_enabled=True, llm=llm, publisher=pub)

    out = run_pipeline(None, deps, publish=True, resume_state=_wiring_state())

    assert out.step_status["build_p3"].status is StepStatus.OK
    assert out.step_status["widget_p3"].status is StepStatus.OK
    assert out.step_status["publish_p3"].status is StepStatus.OK
    # the widget reached the PUBLISHED body -> it ran after build, before publish
    body = pub.post_call["content"]
    assert "<!-- wp:html -->" in body and 'class="vw"' in body
    assert body.index("Passo dois do guia") < body.index("<!-- wp:html -->") \
        < body.index("Passo tres do guia")


def test_pipeline_flag_off_is_byte_identical(tmp_path: Path, config_files: Path):
    pub = _FakePublisher()
    llm = FakeLLM(responses=[_JSON_VALIDO])
    deps = _wiring_deps(tmp_path, config_files, widgets_enabled=False, llm=llm, publisher=pub)

    out = run_pipeline(None, deps, publish=True, resume_state=_wiring_state())

    assert "widget_p3" not in out.step_status         # step never ran
    assert llm.calls == []                             # no widget LLM call
    assert "wp:html" not in pub.post_call["content"]   # published body unchanged


def test_pipeline_widget_none_still_publishes_intact(tmp_path: Path, config_files: Path):
    pub = _FakePublisher()
    llm = FakeLLM(responses=["NONE"])
    deps = _wiring_deps(tmp_path, config_files, widgets_enabled=True, llm=llm, publisher=pub)

    out = run_pipeline(None, deps, publish=True, resume_state=_wiring_state())

    assert out.step_status["widget_p3"].status is StepStatus.SKIPPED
    # ⚠️ A política VIROU em 19/08/2026: NONE não derruba mais a página.
    assert out.step_status["content_gate_p3"].status is StepStatus.OK
    assert out.step_status["publish_p3"].status is StepStatus.OK
    assert "wp:html" not in pub.post_call["content"]     # publicada, sem widget


def test_pipeline_falha_de_widget_nao_impede_mais_a_publicacao(tmp_path: Path, config_files: Path):
    def _boom(model, messages):
        raise RuntimeError("provider down")

    pub = _FakePublisher()
    deps = _wiring_deps(tmp_path, config_files, widgets_enabled=True,
                        llm=FakeLLM(responses=_boom), publisher=pub)

    out = run_pipeline(None, deps, publish=True, resume_state=_wiring_state())

    assert out.step_status["widget_p3"].status is StepStatus.SKIPPED
    assert out.step_status["widget_p3"].status is not StepStatus.FAILED
    # O provedor caiu e a página foi publicada assim mesmo — sem widget.
    assert out.step_status["content_gate_p3"].status is StepStatus.OK
    assert out.step_status["publish_p3"].status is StepStatus.OK
    # e a ausência fica REGISTRADA, para o operador ver e decidir
    ausente = out.step_status["widget_ausente_p3"]
    assert [i.code for i in ausente.issues] == ["widget_ausente_publicado_assim_mesmo"]


def test_pipeline_widget_recusado_publica_o_artigo_assim_mesmo(
        tmp_path: Path, config_files: Path):
    """A recusa por CONTEÚDO — a única que ainda existe depois de o gabarito
    passar a imprimir o HTML — deixa o artigo intacto e publica assim mesmo.

    ⚠️ A política virou em 19/08/2026. Antes esta recusa emitia
    `required_widget_missing` no gate final e derrubava a página inteira; foi
    assim que p3 e p4 da run 9 morreram, com o artigo pronto no disco."""
    pub = _FakePublisher()
    bad = _jsons_ruins()["cenario_em_branco"]
    # duas vezes o MESMO JSON ruim: o passo retenta uma vez com o motivo
    # apontado, e o teste prova que nem assim ele afrouxa
    deps = _wiring_deps(tmp_path, config_files, widgets_enabled=True,
                        llm=FakeLLM(responses=[bad, bad]), publisher=pub)

    out = run_pipeline(None, deps, publish=True, resume_state=_wiring_state())

    res = out.step_status["widget_p3"]
    assert res.status is StepStatus.SKIPPED
    assert _rejected(res) and "widget_conteudo_invalido" in _errors(res)
    assert out.step_status["content_gate_p3"].status is StepStatus.OK
    assert out.step_status["publish_p3"].status is StepStatus.OK
    assert "wp:html" not in pub.post_call["content"]


def test_widget_retenta_com_o_erro_apontado_e_salva_a_pagina(tmp_path: Path):
    """A retentativa que nasceu de um `&` custar uma página inteira.

    Run #4, 17/08/2026, página 3: o widget foi rejeitado por UM caractere `&`
    no script. O `content_gate` então emitiu `required_widget_missing` e a
    página caiu — já escrita, julgada, com SEO, imagem, print e build prontos.
    US$ 0,79 de trabalho perdidos por US$ 0,14 de widget.

    O prompt JÁ proibia o `&` explicitamente. Instrução sozinha não bastou; o
    que basta é devolver o erro e pedir de novo.
    """
    ruim = _jsons_ruins()["cenario_em_branco"]
    bom = _JSON_VALIDO
    llm = FakeLLM(responses=[ruim, bom])
    deps = _deps(tmp_path, _settings(), llm)
    state = RunState(run_id="r")
    state.drafts[3] = PageDraft(page_number=3, page_type="SOLUTION",
                                format="gutenberg", content=_article_4h2())

    st.step_widget(state, _solution_page(), deps)

    res = state.step_status["widget_p3"]
    assert res.status is StepStatus.OK, "a segunda tentativa devia ter salvado a página"
    assert "wp:html" in state.drafts[3].content, "o widget bom não foi injetado"

    # e a correção foi ENTREGUE ao modelo: a segunda chamada carrega o rótulo
    segunda = llm.calls[-1]["messages"][-1]["content"]
    assert "A TENTATIVA ANTERIOR FOI RECUSADA" in segunda
    # e o motivo é NOMEADO: a retentativa precisa saber o que faltou
    assert "resultado em branco" in segunda
    # ⚠️ A asserção que morava aqui — que a correção ensinasse a trocar
    # `a && b` por `if` aninhado — não faz mais sentido: o modelo não escreve
    # JavaScript. O `&&` deixou de ser um risco em vez de ser bem instruído.


# =========================================================================== #
# CARD-0014 · the 8-archetype creative taxonomy
# =========================================================================== #
# The canonical order is the CONTRACT shared by steps.WIDGET_ARCHETYPES (the
# draw indexes into it) and redator_widget.jinja's catalog.
_ARQUETIPOS_ESPERADOS = (
    "Roteador de Elegibilidade",
    "Termômetro de Prontidão",
    "Detector de Sinais de Golpe",
    "Comparador de Rotas",
    "Navegador de Jornada",
    "Quiz Mito ou Verdade",
    "Tradutor de Termos",
    "Priorizador de Próximos Passos",
    # 9º: cobre a forma de pergunta `diagnostico` do eixo `engajamento`.
    "Diagnóstico de Recusa",
)


def _plan_with_solutions(*ordinals: int) -> FunnelPlan:
    """A FunnelPlan of SOLUTION pages with the given ordinals (slug `tema-pN`)."""
    pages = [
        Page(page_number=10 + o, page_type="SOLUTION", h1_title=f"Solucao {o}",
             slug=f"tema-p{o}", ordinal=o, role=PageRole.SOLUTION)
        for o in ordinals
    ]
    return FunnelPlan(total_pages=len(pages), pages=pages)


def _state_with(run_id: str, plan: FunnelPlan) -> RunState:
    s = RunState(run_id=run_id)
    s.plan = plan
    return s


# --------------------------------------------------------------------------- #
# AC2: deterministic, content-derived archetype selection
# --------------------------------------------------------------------------- #
def test_widget_archetype_is_deterministic_by_run_id():
    """Same run_id + same page -> same archetype on every call (no random/Date)."""
    plan = _plan_with_solutions(1, 2, 3)
    page = plan.pages[1]
    a = st.widget_archetype_for(_state_with("run-xyz", plan), page)
    b = st.widget_archetype_for(_state_with("run-xyz", plan), page)
    assert a == b
    assert a in st.WIDGET_ARCHETYPES


def test_widget_archetype_does_not_depend_on_run_id():
    plan = _plan_with_solutions(1, 2, 3)
    first = plan.pages[0]  # ordinal 1 -> position 0
    assert st.widget_archetype_for(_state_with("run-a", plan), first) \
        == st.widget_archetype_for(_state_with("run-b", plan), first) \
        == "Navegador de Jornada"


def test_widget_archetype_same_question_shape_gets_same_tool():
    plan = _plan_with_solutions(1, 2, 3)
    state = _state_with("run-xyz", plan)
    got = [st.widget_archetype_for(state, p) for p in plan.pages]
    assert got == ["Navegador de Jornada"] * 3


def test_widget_archetype_never_uses_catalog_as_lottery():
    plan = _plan_with_solutions(*range(1, len(st.WIDGET_ARCHETYPES) + 1))
    state = _state_with("seed-8", plan)
    got = [st.widget_archetype_for(state, p) for p in plan.pages]
    assert got == ["Navegador de Jornada"] * len(plan.pages)


def test_widget_archetype_stable_under_resume():
    """Resume re-derives the SAME assignment: a brand-new RunState with the same
    run_id + plan (as a resumed run rebuilds) yields the identical per-sibling
    archetype -- nothing depends on wall-clock or call order."""
    plan = _plan_with_solutions(1, 2, 3)
    first_pass = [st.widget_archetype_for(_state_with("resume-1", plan), p) for p in plan.pages]
    second_pass = [st.widget_archetype_for(_state_with("resume-1", plan), p) for p in plan.pages]
    assert first_pass == second_pass


def test_widget_archetype_does_not_depend_on_ordinal_or_list_order():
    plan = _plan_with_solutions(3, 1, 2)  # listed out of order
    state = _state_with("ord-test", plan)
    by_slug = {p.slug: st.widget_archetype_for(state, p) for p in plan.pages}
    assert set(by_slug.values()) == {"Navegador de Jornada"}


def test_widget_archetype_survives_missing_plan():
    """Fail-safe: with no plan/solution list (e.g. a bare state) the draw still
    returns a valid archetype instead of raising -- the step must never crash."""
    got = st.widget_archetype_for(RunState(run_id="bare"), _solution_page())
    assert got in st.WIDGET_ARCHETYPES


def test_step_widget_passes_drawn_archetype_to_prompt(tmp_path: Path):
    """step_widget threads the DRAWN archetype into the redator_widget render
    (the prompt the writer sees names it inside <ARQUETIPO_DESTA_PECA>)."""
    llm = FakeLLM(responses=[_JSON_VALIDO])
    deps = _deps(tmp_path, _settings(), llm)
    plan = _plan_with_solutions(1, 2, 3)
    state = _state_with("draw-run", plan)
    page = plan.pages[0]
    state.drafts[page.page_number] = PageDraft(
        page_number=page.page_number, page_type="SOLUTION",
        format="gutenberg", content=_article_4h2())

    st.step_widget(state, page, deps)

    # Não há mais bloco <ARQUETIPO_DESTA_PECA>: o prompt é RENDERIZADO já com
    # um arquétipo só, então o arquétipo derivado tem de estar nele — e os
    # outros três, fora.
    sent = llm.calls[0]["messages"][0]["content"]
    assert "Navegador de Jornada" in sent
    for outro in ("Comparador de Rotas", "Diagnóstico de Recusa",
                  "Roteador de Elegibilidade"):
        assert outro not in sent


# --------------------------------------------------------------------------- #
# O prompt pede CONTEÚDO, não código.
#
# ⚠️ Os quatro testes que viviam aqui provavam o contrato ANTERIOR: que o prompt
# listava os nove arquétipos do catálogo, que `<ARQUETIPO_DESTA_PECA>`
# selecionava o sorteado, e que TODA regra do sanitizador aparecia espelhada em
# linguagem natural (`iframe`, `localStorage`, `addEventListener`, `innerHTML`,
# o veto ao `&`).
#
# Espelhar regra de motor em prosa era a única defesa que havia, e ela falhou de
# forma medida: o prompt proibia o `&` com todas as letras e o modelo o escreveu
# assim mesmo, derrubando a p3 do run #4. Agora essas regras não são pedidas —
# são propriedade do gabarito, provadas em `tests/test_widgets.py`.
#
# E dos nove arquétipos, só QUATRO eram alcançáveis: `ENGAJAMENTO_PARA_ARQUETIPO`
# nunca emitiu os outros cinco. Descrevê-los custava token em toda chamada.
# --------------------------------------------------------------------------- #
def test_o_prompt_descreve_so_o_arquetipo_desta_pagina():
    from funnelforge.widgets import ARQUETIPOS

    p = render("redator_widget", country="Brasil", year=2026, title="T",
               article="<p>x</p>", arquetipo="comparador", facts="")
    assert ARQUETIPOS["comparador"]["nome"] in p
    for outro in ("Diagnóstico de Recusa", "Navegador de Jornada",
                  "Roteador de Elegibilidade"):
        assert outro not in p, f"{outro} viajou de carona e ninguém pode escolhê-lo"


def test_o_prompt_proibe_escrever_codigo():
    p = render("redator_widget", country="Brasil", year=2026, title="T",
               article="<p>x</p>", arquetipo="roteador", facts="")
    assert "NÃO escreve HTML" in p
    assert "objeto JSON" in p


def test_o_prompt_carrega_o_esqueleto_do_json():
    """O modelo precisa VER o formato — descrevê-lo em prosa produz variação."""
    p = render("redator_widget", country="Brasil", year=2026, title="T",
               article="<p>x</p>", arquetipo="navegador", facts="")
    for campo in ('"arquetipo"', '"controles"', '"cenarios"', '"quando"',
                  '"chip"', '"tom"', '"padrao"'):
        assert campo in p, f"{campo} não aparece no esqueleto"


def test_o_prompt_mantem_a_anti_injecao_e_o_artigo_como_dado():
    p = render("redator_widget", country="Brasil", year=2026, title="T",
               article="<p>CORPO-DO-ARTIGO-AQUI</p>", arquetipo="roteador", facts="")
    assert "CORPO-DO-ARTIGO-AQUI" in p
    low = p.lower()
    assert "anti-injeção" in low
    assert "ignore" in low


def test_o_prompt_veta_forca_legal_sem_dispositivo():
    """A causa exata da queda da p3 na run 9: uma carência de 25 meses que
    nenhum fato sustentava."""
    p = render("redator_widget", country="Brasil", year=2026, title="T",
               article="<p>x</p>", arquetipo="diagnostico", facts="")
    assert "força legal" in p
    assert "25 meses" in p          # o caso concreto, para o modelo reconhecê-lo


def test_o_prompt_ensina_a_nao_culpar_o_leitor():
    p = render("redator_widget", country="Brasil", year=2026, title="T",
               article="<p>x</p>", arquetipo="diagnostico", facts="")
    assert "Nunca culpe o leitor" in p


# --------------------------------------------------------------------------- #
# AC3: judge structure rubric rewards a USEFUL widget, never 'calculadora' as a
# bonus, never penalizes widget absence -- cutoffs/schema/EXISTENTIAL/CARD-0011
# backstop all intact.
# --------------------------------------------------------------------------- #
def _render_judge(page_type: str = "SOLUTION") -> str:
    return render("judge", content="c", page_type=page_type,
                  domain="https://creditoup.com.br", cta_link="/x",
                  keywords="k", facts="{}")


def test_judge_widget_rubric_rewards_useful_diverse_widget():
    out = _render_judge().lower()
    assert "widget interativo útil" in out
    for kind in ("roteador", "golpe", "comparador", "quiz", "glossário", "planejador"):
        assert kind in out, f"rubrica não cita o tipo útil: {kind}"


def test_judge_never_bonuses_calculadora():
    """Insight-4 root cause: a rubric privileging 'calculadora/verificador'. The
    new rubric must NOT mention 'calculadora' as a bonus (in any page type)."""
    for pt in ("SOLUTION", "HUB", "LANDING PAGE"):
        assert "calculadora" not in _render_judge(pt).lower()


def test_judge_absence_of_widget_not_penalized():
    out = _render_judge().lower()
    assert "ausência de widget não penaliza" in out


def test_judge_widget_signal_is_advisory_not_scored():
    """Advisory: NO new score key -> the JSON schema (7 scores) is untouched."""
    out = _render_judge()
    assert '"widget"' not in out
    scores_block = out[out.index('"scores"'):out.index('"feedback"')]
    assert "widget" not in scores_block.lower()


def test_judge_card0011_backstop_and_cutoffs_and_schema_intact():
    """CARD-0014 must NOT touch the CARD-0011 congruence backstop, the cut-off
    wording, the existential set, or the 7-key scores schema."""
    out = _render_judge("SOLUTION")
    assert "BACKSTOP DE CONGRUÊNCIA DE DESTINO (CARD-0011)" in out
    assert "nota < 7" in out
    assert "compliance, cta_discipline" in out
    for score in ("tone_e_e_a_t", "cta_discipline", "proof_and_authority",
                  "faq_resolution", "compliance", "single_destination",
                  "authorship_signal"):
        assert f'"{score}"' in out


# ===========================================================================
# A PONTE: a FORMA DA PERGUNTA escolhe a FERRAMENTA
#
# Antes disto o arquétipo saía de `sha1(run_id) % N` -- determinístico e
# diverso, mas ARBITRÁRIO em relação ao conteúdo: uma página sobre "quais
# bancos antecipam FGTS" podia receber um Detector de Sinais de Golpe, e uma
# sobre "como identificar boleto falso" um Comparador de Rotas. Trocados.
#
# O eixo `engajamento` do motor de pautas classifica a forma da pergunta, e é
# essa classificação que passa a mandar. O sorteio vira fallback.
# ===========================================================================


@pytest.mark.parametrize("eixo,esperado", [
    ("condicional", "Roteador de Elegibilidade"),
    ("sequencial",  "Navegador de Jornada"),
    ("comparativo", "Comparador de Rotas"),
    ("diagnostico", "Diagnóstico de Recusa"),
])
def test_arquetipo_deriva_do_engajamento(eixo: str, esperado: str) -> None:
    plan = _plan_with_solutions(1, 2, 3)
    for p in plan.pages:
        p.engajamento = eixo
    state = _state_with("qualquer-seed", plan)
    # todas as irmãs recebem o MESMO arquétipo: a forma da pergunta manda,
    # não a diversidade -- diversidade era um paliativo para a falta de sinal.
    assert [st.widget_archetype_for(state, p) for p in plan.pages] == [esperado] * 3


def test_dado_unico_nao_gera_widget() -> None:
    """`dado_unico` = a resposta da página é um número. Widget ali é enfeite, e
    enfeite ao lado de anúncio custa viewability. Devolve None."""
    plan = _plan_with_solutions(1)
    plan.pages[0].engajamento = "dado_unico"
    assert st.widget_archetype_for(_state_with("s", plan), plan.pages[0]) is None


@pytest.mark.parametrize("eixo", ["", "   ", "vocabulario_desconhecido"])
def test_sem_eixo_cai_na_inferencia_semantica(eixo: str) -> None:
    """Eixo ausente/desconhecido usa conteúdo, nunca hash/posição."""
    plan = _plan_with_solutions(1, 2, 3)
    for p in plan.pages:
        p.engajamento = eixo
    state = _state_with("seed-fallback", plan)
    got = [st.widget_archetype_for(state, p) for p in plan.pages]
    assert got == ["Navegador de Jornada"] * 3


def test_eixo_e_case_insensitive_e_tolera_espaco() -> None:
    plan = _plan_with_solutions(1)
    plan.pages[0].engajamento = "  Condicional  "
    assert st.widget_archetype_for(_state_with("s", plan), plan.pages[0]) \
        == "Roteador de Elegibilidade"


def test_todo_arquetipo_do_mapa_existe_na_taxonomia() -> None:
    """O mapa não pode apontar para um arquétipo que o catálogo do prompt não
    conhece -- seria um widget pedido e nunca descrito."""
    for arq in st.ENGAJAMENTO_PARA_ARQUETIPO.values():
        if arq is not None:
            assert arq in st.WIDGET_ARCHETYPES, arq


# --------------------------------------------------------------------------- #
# ⚠️ AS DUAS CAUSAS DA QUEDA DA p3 NA RUN 9 (19/08/2026)
#
# Elas não eram alucinação do modelo. O motor estava brigando consigo mesmo.
# --------------------------------------------------------------------------- #
def test_o_prompt_nao_ensina_a_frase_que_o_validador_recusa():
    """O prompt antigo mandava, com todas as letras, escrever "o sistema exige
    X, e por isso Y" na regra do Diagnóstico de Recusa. Essa expressão está
    dentro de `_LEGAL_FORCE_RE`: o motor pedia ao modelo a frase que outro
    pedaço do motor reprova, e a página inteira caía junto com o widget."""
    from funnelforge.pipeline.validators.checks import _LEGAL_FORCE_RE

    p = render("redator_widget", country="Brasil", year=2026, title="T",
               article="<p>x</p>", arquetipo="diagnostico", facts="")
    # o prompt PODE citar as expressões — desde que seja para proibi-las
    exemplos = p.split("Diga a mesma coisa sem elas")[-1]
    certas = [l.split("✅", 1)[1] for l in exemplos.splitlines() if "✅" in l]
    assert certas, "o prompt perdeu os exemplos de reescrita"
    for certa in certas:
        assert not _LEGAL_FORCE_RE.search(certa), (
            f"o prompt oferece como CERTA uma frase que o validador recusa: {certa!r}")


def test_o_widget_e_julgado_com_a_mesma_regua_do_gate_final():
    """`state.facts.get(n)` devolve `None` quando a página não tem fatos, e com
    `None` o `critical_fact_grounding` aprova tudo. O `content_gate` usa
    `_write_ctx`, que preenche com `ResearchFacts(sparse=True)` e reprova.

    O widget passava na própria checagem e morria no portão seguinte — sem
    retentativa, levando a página junto. As duas chamadas têm de usar o mesmo
    preenchimento."""
    import inspect

    fonte = inspect.getsource(st.step_widget)
    assert "ResearchFacts(sparse=True)" in fonte, (
        "o laço do widget voltou a julgar com régua mais frouxa que o gate final")


def test_pagina_condenada_pelo_content_gate_pode_ser_retomada(tmp_path: Path,
                                                              config_files: Path):
    """⚠️ O NÓ CEGO da retomada, medido na run 9 em 19/08/2026.

    `_page_blocked` era consultado ANTES do build já contando o `content_gate`.
    Uma página reprovada por `required_widget_missing` dava True, o laço fazia
    `continue`, e o widget — o passo que apagaria exatamente aquela reprovação —
    nunca rodava. O comando saía com status 0 e `state.json` ficava byte a byte
    igual: p3 e p4 estavam presas sem caminho de volta, com 10.922 e 13.201
    caracteres de artigo pronto no disco.
    """
    from funnelforge.domain.models import Issue

    pub = _FakePublisher()
    llm = FakeLLM(responses=[_JSON_VALIDO])
    deps = _wiring_deps(tmp_path, config_files, widgets_enabled=True, llm=llm, publisher=pub)

    state = _wiring_state()
    # o estado como a run 9 o deixou: portão reprovado por falta de widget
    state.step_status["content_gate_p3"] = StepResult(
        step="content_gate_p3", status=StepStatus.FAILED,
        issues=[Issue(code="required_widget_missing", message="…")])
    state.step_status["blocked_p3"] = StepResult(
        step="blocked_p3", status=StepStatus.FAILED,
        issues=[Issue(code="fail_closed", message="…")])

    out = run_pipeline(None, deps, publish=True, resume_state=state)

    assert llm.calls, "o widget nem chegou a ser tentado — o nó cego voltou"
    assert out.step_status["widget_p3"].status is StepStatus.OK
    assert out.step_status["content_gate_p3"].status is StepStatus.OK
    assert out.step_status["publish_p3"].status is StepStatus.OK
    assert 'class="vw"' in pub.post_call["content"]


def test_condenacao_antiga_sai_do_estado_quando_a_pagina_passa(tmp_path: Path,
                                                               config_files: Path):
    """`blocked_pN` só era escrito, nunca apagado.

    Depois da retomada de 19/08/2026 a p3 estava com `widget_p3: OK` e
    `content_gate_p3: OK` — e ainda carregava `blocked_p3: FAILED` da rodada
    anterior. O relatório lê o estado e diria "bloqueada" sobre uma página
    pronta para publicar. Estado que guarda veredito vencido mente para quem o
    lê depois, e é a partir dele que o operador decide.
    """
    from funnelforge.domain.models import Issue

    pub = _FakePublisher()
    llm = FakeLLM(responses=[_JSON_VALIDO])
    deps = _wiring_deps(tmp_path, config_files, widgets_enabled=True, llm=llm, publisher=pub)

    state = _wiring_state()
    state.step_status["blocked_p3"] = StepResult(
        step="blocked_p3", status=StepStatus.FAILED,
        issues=[Issue(code="fail_closed", message="da rodada anterior")])

    out = run_pipeline(None, deps, publish=True, resume_state=state)

    assert out.step_status["publish_p3"].status is StepStatus.OK
    assert "blocked_p3" not in out.step_status, (
        "a condenação vencida ficou no estado de uma página publicada")
