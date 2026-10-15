"""Correção de 15/10/2026 sobre 4e43c9b2/78c13d94 (revisão local, veredito CORRIGIR).

1. A âncora no texto da LP V2 sai DENTRO do runner, antes de `lp_json_contract`:
   uma LP com link é aprovada na 1ª chamada, sem retentativa paga.
2. Saneador e portão leem âncora com o MESMO parser (`editorial_safety._Ancoras`).
3. As regras novas de link valem só para página V2: LP e pré-sell V1 que
   passavam antes continuam passando, inclusive na revalidação da publicação.
4. LP montada com template antigo não vira falha silenciosa nem é aceita: o
   portão diz `lp_template_desatualizado` e o rebuild explícito resolve.

Todos sem rede e sem modelo: o "LLM" é `tests.fakes.FakeLLM`.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from funnelforge.domain.models import (
    FunnelPlan,
    Page,
    PageRole,
    ResearchFacts,
    RunState,
    StepStatus,
)
from funnelforge.pipeline.editorial_safety import (
    hrefs_do_html,
    links_externos_por_papel,
    links_no_texto_da_lp,
    sem_ancoras,
)
from funnelforge.pipeline.lp_template import validate_lp_content
from funnelforge.pipeline.runner import Runner
from funnelforge.pipeline.validators.checks import run_validators
from tests.fakes import FakeLLM

SITE = "https://creditoup.com.br"
GOV = "https://www.gov.br/fgts"
LP = {
    "hero_title": "Saque-aniversário do FGTS",
    "hero_subtitle": "Quem pode adiantar parcelas e o que continua descontado.",
    "article_title": "Como funciona o saque-aniversário",
    "intro": "<p>Resposta curta para quem quer decidir hoje.</p>",
    "sections": [{"title": f"Seção {i}", "body": f"<p>Corpo da seção {i}.</p>"}
                 for i in range(4)],
    "faq": [{"q": "Quem pode pedir?", "a": "Quem optou pelo saque-aniversário."}],
    "faq_title": "Dúvidas",
    "transition": "<p>Escolha o caminho do seu caso.</p>",
    "cta_texts": ["Ver se o meu caso permite", "Entender o desconto anual",
                  "Comparar as opções de saque"],
}


def _lp_com_links() -> dict:
    """Externa com aspas, externa SEM aspas, interna em maiúsculas: as três formas
    que o portão enxerga como âncora."""
    lp = copy.deepcopy(LP)
    lp["intro"] = f'<p>Segundo o <a href="{GOV}">portal do FGTS</a>, o saque é anual.</p>'
    lp["sections"][1]["body"] = f"<p>Confira na <a href={GOV}/regras>página de regras</a>.</p>"
    lp["sections"][2]["body"] = (f'<p>Veja o <A HREF="{SITE}/rec/fgts-p1">guia do pedido</A>.'
                                 "</p>")
    return lp


# --------------------------------------------------------------- 1. runner ---
def _plano(settings):
    from funnelforge.pipeline.routing import build_funnel_routes
    plan = FunnelPlan(total_pages=4, pages=[
        Page(page_number=1, page_type="LANDING PAGE", h1_title="Saque FGTS", slug="fgts"),
        Page(page_number=2, page_type="HUB", h1_title="Por onde começar", slug="fgts-pr1",
             role=PageRole.PRESELL),
        Page(page_number=3, page_type="SOLUTION", h1_title="Como pedir", slug="fgts-p1",
             ordinal=1),
        Page(page_number=4, page_type="SOLUTION", h1_title="Como comparar", slug="fgts-p2",
             ordinal=2),
    ])
    build_funnel_routes(plan, settings)
    return plan


def _escrever_lp_v2(config_files, monkeypatch, tmp_path, respostas):
    from funnelforge.config.settings import load_settings
    from funnelforge.pipeline import steps as st
    from funnelforge.pipeline.pipeline import Deps

    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    plan = _plano(settings)
    llm = FakeLLM(responses=respostas)
    runner = Runner(llm=llm, max_retries=2, runs_dir=tmp_path / "runs")
    deps = Deps(llm=llm, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=None, settings=settings, runner=runner)
    for nome, valor in {"briefing_para_o_redator": lambda b: "BRIEFING",
                        "passos_por_destino": lambda b: {},
                        "preflight_issues": lambda *a: []}.items():
        monkeypatch.setattr(st, nome, valor)
    state = RunState(run_id="fgts-20261015-120000", plan=plan, editorial_v2=True,
                     briefings={1: {}}, facts={1: ResearchFacts(fontes_resolvidas=[GOV])})
    st.step_write(state, plan.pages[0], deps)
    return state, llm


def test_lp_v2_com_link_e_saneada_e_aprovada_em_uma_unica_chamada(
        config_files, monkeypatch, tmp_path):
    """No pai (78c13d94) o contrato recusava a âncora antes do saneador: 2+
    chamadas (RETRIED) ou FAILED se o modelo repetisse o link."""
    state, llm = _escrever_lp_v2(config_files, monkeypatch, tmp_path,
                                 [json.dumps(_lp_com_links(), ensure_ascii=False)] * 3)
    res = state.step_status["write_p1"]
    assert len(llm.calls) == 1, [i.code for i in res.issues]
    assert res.status is StepStatus.OK and res.attempts == 1
    rascunho = json.loads(state.drafts[1].content)
    assert hrefs_do_html(json.dumps(rascunho, ensure_ascii=False)) == []
    assert "portal do FGTS" in rascunho["intro"]            # o texto da âncora fica
    assert "página de regras" in rascunho["sections"][1]["body"]
    assert "guia do pedido" in rascunho["sections"][2]["body"]
    etapas = {n["etapa"]: n for n in state.normalizacoes.get(1, [])}
    assert etapas["fontes_externas_da_lp_em_prosa"]["quantidade"] == 2
    assert etapas["links_no_texto_da_lp"]["quantidade"] == 1


def test_lp_v2_saneamento_conta_so_a_tentativa_aceita(config_files, monkeypatch, tmp_path):
    """Retentativa por OUTRO motivo (JSON quebrado na 1ª) não duplica o recibo."""
    state, llm = _escrever_lp_v2(
        config_files, monkeypatch, tmp_path,
        ["{nao e json", json.dumps(_lp_com_links(), ensure_ascii=False)])
    assert len(llm.calls) == 2
    assert state.step_status["write_p1"].status is StepStatus.RETRIED
    etapas = [n["etapa"] for n in state.normalizacoes.get(1, [])]
    assert etapas.count("links_no_texto_da_lp") == 1


def test_runner_sem_saneador_nao_muda_o_texto(tmp_path):
    """V1 (e todo passo que não passa `saneador`) segue byte a byte como antes."""
    from funnelforge.config.settings import StepConfig
    bruto = json.dumps(_lp_com_links(), ensure_ascii=False)
    runner = Runner(llm=FakeLLM(responses=[bruto]), max_retries=0, runs_dir=tmp_path)
    cfg = StepConfig(model="m", fallbacks=[], temperature=0.0, validators=[])
    texto, _ = runner.run_llm_step("write_p1", cfg, [{"role": "user", "content": "x"}],
                                   ctx={}, run_id="r-20261015-000000")
    assert texto == bruto


def test_saneador_que_explode_nao_derruba_o_passo(tmp_path):
    from funnelforge.config.settings import StepConfig
    runner = Runner(llm=FakeLLM(responses=["ok"]), max_retries=0, runs_dir=tmp_path)
    cfg = StepConfig(model="m", fallbacks=[], temperature=0.0, validators=[])

    def explode(_texto):
        raise ValueError("boom")

    texto, res = runner.run_llm_step("x", cfg, [{"role": "user", "content": "x"}], ctx={},
                                     run_id="r-20261015-000000", saneador=explode)
    assert (texto, res.status) == ("ok", StepStatus.OK)


# ---------------------------------------------------------- 2. mesmo parser ---
CORPUS = [
    f'<p>a <a href="{GOV}">x</a> b</p>',
    f"<p>a <a href={GOV}>sem aspas</a> b</p>",
    f'<p>a <A HREF="{GOV}">MAIÚSCULA</A> b</p>',
    f"<p>a <a href='{GOV}'>aspas simples</a> b</p>",
    f'<p>a <a\n  href="{GOV}"\n>quebra de linha</a> b</p>',
    f'<p>&amp; <a href="{GOV}?a=1&amp;b=2">entidade</a> &eacute;</p>',
    f'<p>sem fechar <a href="{GOV}">texto</p>',
    f'<p>autofechada <a href="{GOV}"/> fim</p>',
    '<p>a <a href="//evil.example/x">protocolo relativo</a> b</p>',
    '<p>a <a href="https://creditoup.com.br.golpe.example/x">sufixo falso</a></p>',
    f'<p>a <a title="x" href="{GOV}" target="_blank" rel="noopener">atributos</a></p>',
]


@pytest.mark.parametrize("html", CORPUS)
def test_saneador_da_lp_tira_tudo_que_o_portao_ve(html):
    limpo, n = sem_ancoras(html)
    assert n == len(hrefs_do_html(html)) >= 1
    assert links_no_texto_da_lp([limpo]) == []


@pytest.mark.parametrize("html", CORPUS)
def test_saneador_da_presell_tira_tudo_que_o_portao_ve(html):
    from funnelforge.pipeline.steps import _sem_fontes_externas_no_corpo
    assert links_externos_por_papel(html, papel="PRESELL", dominio=SITE)
    limpo, n = _sem_fontes_externas_no_corpo(html, SITE)
    assert n >= 1
    assert links_externos_por_papel(limpo, papel="PRESELL", dominio=SITE) == []


def test_saneador_da_presell_preserva_link_interno_e_tira_o_sufixo():
    from funnelforge.pipeline.steps import _sem_fontes_externas_no_corpo
    html = (f'<p>Veja o <a href={SITE}/rec/x-p1>guia</a> e a <a href={GOV}>CAIXA</a>, '
            "em site externo.</p>")
    limpo, n = _sem_fontes_externas_no_corpo(html, SITE)
    assert n == 1
    assert limpo == f"<p>Veja o <a href={SITE}/rec/x-p1>guia</a> e a CAIXA.</p>"


# ------------------------------------------------------------ 3. V1 intacto ---
def test_lp_v1_com_fonte_linkada_passa_no_contrato_como_antes():
    """O prompt V1 (`redator_p1.jinja`) pede o link da fonte na frase do fato."""
    lp = copy.deepcopy(LP)
    lp["intro"] = f'<p>Segundo a <a href="{GOV}">CAIXA</a>, o saque é anual.</p>'
    assert "link_no_texto_da_lp" not in {i.code for i in validate_lp_content(lp)}
    ctx_v1 = {"editorial_v2": False, "pagina_v2": False, "contextual_editorial": True}
    codigos = {i.code for i in run_validators(
        ["lp_json_contract"], json.dumps(lp, ensure_ascii=False), ctx_v1)}
    assert "link_no_texto_da_lp" not in codigos


def test_lp_v2_com_link_restante_continua_recusada_pelo_contrato():
    ctx_v2 = {"editorial_v2": True, "pagina_v2": True}
    codigos = [i.code for i in run_validators(
        ["lp_json_contract"], json.dumps(_lp_com_links(), ensure_ascii=False), ctx_v2)]
    assert codigos == ["link_no_texto_da_lp"]


def test_presell_v1_com_fonte_linkada_nao_reprova_no_portao_final():
    corpo = f'<!-- wp:paragraph --><p>Segundo o <a href="{GOV}">portal</a>.</p>' \
            "<!-- /wp:paragraph -->"
    assert run_validators(["links_por_papel"], corpo,
                          {"role": PageRole.PRESELL, "domain": SITE,
                           "editorial_v2": True, "pagina_v2": False}) == []
    assert [i.code for i in run_validators(
        ["links_por_papel"], corpo,
        {"role": PageRole.PRESELL, "domain": SITE, "pagina_v2": True})] \
        == ["link_externo_na_presell"]


def _responder_v1_com_fontes(model, messages):
    """Smoke V1 do motor, com a fonte linkada que o prompt V1 pede na pré-sell e
    na LP. No pai: `content_gate_p<pré-sell> FAILED [link_externo_na_presell]`
    depois de pagar redação, juiz e SEO; LP V1 recusada por `link_no_texto_da_lp`."""
    import tests.test_smoke_e2e as smoke
    conteudo = messages[-1]["content"]
    resposta = smoke._responder(model, messages)
    if "PÁGINA PRÉ-SELL" in conteudo:
        return smoke._page_html_for(conteudo).replace(
            "<p>Conteúdo de utilidade pública",
            f'<p>Segundo o <a href="{GOV}">portal do FGTS</a>, conteúdo de utilidade pública',
            1)
    try:
        lp = json.loads(resposta)
    except (ValueError, TypeError):
        return resposta
    if isinstance(lp, dict) and "hero_title" in lp and isinstance(lp.get("intro"), str):
        lp["intro"] = lp["intro"].replace(
            "<p>", f'<p>Segundo a <a href="{GOV}">CAIXA</a>, ', 1)
        return json.dumps(lp, ensure_ascii=False)
    return resposta


def test_funil_v1_com_fontes_linkadas_passa_nos_portoes_como_antes(tmp_path, config_files):
    from funnelforge.adapters.briefing_docx import DocxBriefingLoader
    from funnelforge.config.settings import load_settings
    from funnelforge.domain.models import effective_role
    from funnelforge.pipeline.pipeline import Deps, run_pipeline

    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    assert not settings.run.editorial_v2
    llm = FakeLLM(responses=_responder_v1_com_fontes)
    runner = Runner(llm=llm, max_retries=settings.run.max_retries, runs_dir=tmp_path / "runs")
    deps = Deps(llm=llm, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=DocxBriefingLoader(), settings=settings, runner=runner)
    briefing = tmp_path / "b.txt"
    briefing.write_text("Briefing completo do funil FGTS Saque-Aniversário.", encoding="utf-8")
    state = run_pipeline(briefing, deps, only=None, publish=False)

    presell = next(p for p in state.plan.pages if effective_role(p) is PageRole.PRESELL)
    assert GOV in state.drafts[presell.page_number].content          # V1 mantém a fonte
    gate = state.step_status[f"content_gate_p{presell.page_number}"]
    assert gate.status is StepStatus.OK, [i.code for i in gate.issues]
    novos = {"link_no_texto_da_lp", "link_externo_na_lp", "link_externo_na_presell"}
    for chave, resultado in state.step_status.items():
        assert not novos & {i.code for i in resultado.issues}, chave
    assert GOV in state.drafts[1].content                             # LP V1 idem


# ------------------------------------------------------ 4. LP histórica ---
def _build_lp(config_files, tmp_path, *, v2: bool):
    from funnelforge.config.settings import load_settings
    from funnelforge.pipeline import steps as st
    from funnelforge.pipeline.pipeline import Deps
    from funnelforge.domain.models import PageDraft

    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    plan = _plano(settings)
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=None, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=None, settings=settings, runner=runner)
    state = RunState(run_id="fgts-20261015-130000", plan=plan, editorial_v2=v2,
                     briefings={1: {}} if v2 else {},
                     images={1: f"{SITE}/wp-content/uploads/hero.webp"})
    state.drafts[1] = PageDraft(page_number=1, page_type="LANDING PAGE", format="lp_json",
                                content=json.dumps(LP, ensure_ascii=False), word_count=10)
    st.step_build(state, plan.pages[0], deps)
    return state, deps, plan.pages[0], tmp_path / "runs" / state.run_id


@pytest.mark.parametrize("v2", [False, True])
def test_lp_recem_montada_passa_e_registra_o_template(config_files, tmp_path, v2):
    from funnelforge.pipeline import steps as st
    from funnelforge.pipeline.lp_template import assinatura_do_template
    state, deps, page, run_dir = _build_lp(config_files, tmp_path, v2=v2)
    registro = json.loads((run_dir / "p1.template.json").read_text(encoding="utf-8"))
    assert registro["assinatura"] == assinatura_do_template()
    codigos = {i.code for i in st._lp_final_issues(state, page, deps)}
    assert not codigos & {"lp_template_desatualizado", "lp_artifact_mismatch"}, codigos


@pytest.mark.parametrize("v2", [False, True])
def test_lp_montada_com_template_antigo_e_bloqueada_explicitamente_e_o_rebuild_resolve(
        config_files, tmp_path, v2):
    """Simula o build de antes de 15/10: Elementor de outro template e sem
    `p1.template.json`. O portão não relaxa nem reconstrói sozinho; diz o
    porquê e o comando. O rebuild explícito (sem modelo) resolve."""
    from funnelforge.pipeline import steps as st
    state, deps, page, run_dir = _build_lp(config_files, tmp_path, v2=v2)
    antigo = json.loads((run_dir / "p1.elementor.json").read_text(encoding="utf-8"))
    antigo[0]["settings"]["min_height_mobile"] = {"unit": "vh", "size": 100, "sizes": []}
    (run_dir / "p1.elementor.json").write_text(json.dumps(antigo), encoding="utf-8")
    (run_dir / "p1.template.json").unlink()

    issues = st._lp_final_issues(state, page, deps)
    desatualizado = [i for i in issues if i.code == "lp_template_desatualizado"]
    assert desatualizado and "reconstruir-lp fgts-20261015-130000" in desatualizado[0].message
    assert "lp_artifact_mismatch" not in {i.code for i in issues}

    resultado = st.reconstruir_build_da_lp(state, deps)
    assert resultado.status is StepStatus.OK
    codigos = {i.code for i in st._lp_final_issues(state, page, deps)}
    assert not codigos & {"lp_template_desatualizado", "lp_artifact_mismatch"}, codigos


def test_artefato_alterado_depois_do_build_continua_mismatch(config_files, tmp_path):
    from funnelforge.pipeline import steps as st
    state, deps, page, run_dir = _build_lp(config_files, tmp_path, v2=True)
    alterado = json.loads((run_dir / "p1.elementor.json").read_text(encoding="utf-8"))
    alterado[0]["settings"]["background_color"] = "#000000"
    (run_dir / "p1.elementor.json").write_text(json.dumps(alterado), encoding="utf-8")
    codigos = {i.code for i in st._lp_final_issues(state, page, deps)}
    assert "lp_artifact_mismatch" in codigos
    assert "lp_template_desatualizado" not in codigos


def test_rebuild_sem_rascunho_falha_fechado(config_files, tmp_path):
    from funnelforge.pipeline import steps as st
    state, deps, _page, _ = _build_lp(config_files, tmp_path, v2=True)
    state.drafts.clear()
    assert st.reconstruir_build_da_lp(state, deps).status is StepStatus.FAILED


def test_inventario_de_lps_historicas_e_somente_leitura(config_files, tmp_path):
    import importlib.util
    _state, _deps, _page, run_dir = _build_lp(config_files, tmp_path, v2=True)
    antigo = tmp_path / "runs" / "antigo-20261001-000000"
    antigo.mkdir()
    (antigo / "p1.elementor.json").write_text("[]", encoding="utf-8")
    caminho = Path(__file__).resolve().parents[1] / "scripts" / "inventario_lps_historicas.py"
    spec = importlib.util.spec_from_file_location("inventario_lps_historicas", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    antes = {p: p.stat().st_mtime_ns for p in (tmp_path / "runs").rglob("*")}
    from funnelforge.pipeline.lp_template import assinatura_do_template
    atual = assinatura_do_template()
    assert modulo.classificar(run_dir, atual)["situacao"] == "atual"
    assert modulo.classificar(antigo, atual)["situacao"].startswith("sem_registro")
    assert antes == {p: p.stat().st_mtime_ns for p in (tmp_path / "runs").rglob("*")}
