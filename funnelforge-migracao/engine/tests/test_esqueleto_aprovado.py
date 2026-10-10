"""O card enriquece com pesquisa, mas não troca o esqueleto aprovado em silêncio.

Run real de 09/10/2026: a arquitetura aprovada (6 páginas) virou só referência e
o motor rearquitetou para 7 páginas, com slugs diferentes.
"""
import copy
import json

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.config.settings import StepConfig
from funnelforge.domain.models import FunnelPlan, Page, RunState, StepStatus
from funnelforge.pipeline.pipeline import run_pipeline
from funnelforge.pipeline.steps import _registrar_delta_de_arquitetura
from tests.cenario_editorial import REVISOR_APROVA, montar_deps, responder_v2, settings_do_cenario
from tests.test_dossie_factual import FATOS_COMPLETOS, _ligar_pesquisa, _Pesquisa, arquitetura
from tests.test_inteligencia_pre_redacao import CARD


def _rodar(tmp_path, monkeypatch, aprovada):
    _ligar_pesquisa(monkeypatch, _Pesquisa([], FATOS_COMPLETOS))
    s = settings_do_cenario(tmp_path, editorial_v2=True, passos_v2=True)
    s.run.dossie_factual = True
    s.run.page_workers = 3
    s.run.imagens_habilitadas = False
    s.run.max_retries = 0
    s.steps["dossie"] = StepConfig(model="gemini/gemini-3.8-flash", web_search=True)
    s.steps["extract"] = StepConfig(model="gpt-4.1")
    chamadas_do_arquiteto = []

    def responder(model, messages):
        text = messages[-1]["content"]
        if "REVISOR GLOBAL" in text:
            return json.dumps({"paginas": [{"page_number": n, "revisao": json.loads(REVISOR_APROVA)}
                                           for n in range(1, 6)]})
        if len(messages) == 2 and "brief_pre_arquitetura" in text:
            chamadas_do_arquiteto.append(text)
            raise AssertionError("o arquiteto não deveria ser chamado")
        return responder_v2(model, messages)

    llm, deps = montar_deps(tmp_path, s, responder)
    card = dict(CARD, historico={"arquitetura_referencia": aprovada})
    state = run_pipeline(None, deps, card_pre_arquitetura=card, publish=False,
                         timestamp="hermetico")
    return state, chamadas_do_arquiteto


def test_plano_aprovado_e_preservado_sem_chamar_o_arquiteto(tmp_path, monkeypatch):
    aprovada = arquitetura()
    esperado = [p.slug for p in plano_do_funnel_architecture(copy.deepcopy(aprovada)).pages]
    state, chamadas = _rodar(tmp_path, monkeypatch, aprovada)
    assert chamadas == []
    assert [p.slug for p in state.plan.pages] == esperado
    codigos = [i.code for i in state.step_status["extract"].issues]
    assert "arquitetura_aprovada_preservada" in codigos
    assert state.brief_pre_arquitetura is not None and state.pacotes
    assert "delta_arquitetura" not in state.step_status


def test_plano_refeito_registra_delta_e_suspende_publicacao():
    state = RunState(run_id="r")
    aprovada = {"pages": [{"slug": "guia"}, {"slug": "guia-pr"}, {"slug": "como-pedir-p1"}]}
    plan = FunnelPlan(pages=[Page(page_number=1, page_type="LANDING PAGE", h1_title="h",
                                  slug="guia"),
                             Page(page_number=2, page_type="SOLUTION", h1_title="h",
                                  slug="outro-p1")])
    _registrar_delta_de_arquitetura(state, aprovada, plan)
    delta = state.step_status["delta_arquitetura"]
    assert delta.status is StepStatus.FAILED
    corpo = json.loads(delta.issues[0].message)
    assert corpo["removidas"] == ["guia-pr", "como-pedir-p1"] and corpo["novas"] == ["outro-p1"]
    assert "publicação suspensa" in corpo["acao"]


def test_plano_igual_ao_aprovado_nao_registra_delta():
    state = RunState(run_id="r")
    plan = FunnelPlan(pages=[Page(page_number=1, page_type="LANDING PAGE", h1_title="h",
                                  slug="guia")])
    _registrar_delta_de_arquitetura(state, {"pages": [{"slug": "guia"}]}, plan)
    assert "delta_arquitetura" not in state.step_status


def test_calculadora_pronta_chega_a_pagina_no_caminho_com_pacotes(tmp_path, monkeypatch):
    """Run real 09/10: no caminho com pacotes o widget era pulado antes da
    revisão e depois do build; ferramenta pronta nunca entrava na página."""
    aprovada = arquitetura()
    for job in aprovada["writing_jobs"]:
        jornada = job["writer_briefing"].get("jornada") or {}
        for ativo in jornada.get("ativos") or []:
            ativo["calculo"] = {"operacao": "divisao",
                                "rotulos": ["Renda da casa", "Moradores"],
                                "rotulo_resultado": "Renda por pessoa",
                                "casos": [{"entradas": ["3000", "3"], "resultado": "1000"},
                                          {"entradas": ["1", "8"], "resultado": "0.13"}]}
    state, _ = _rodar(tmp_path, monkeypatch, aprovada)
    com_ativo = [p.page_number for p in state.plan.pages if p.jornada and p.jornada.ativos]
    assert com_ativo
    for n in com_ativo:
        assert state.pacotes[n]["ferramenta"]["estado"] == "pronta"
        assert state.step_status[f"widget_p{n}"].status is StepStatus.OK
        assert "data-vc-operation" in state.drafts[n].content
