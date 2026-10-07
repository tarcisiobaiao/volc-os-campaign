"""O redator, o juiz e o briefing RECEBEM a jornada; o funil pronto passa por
UMA revisão global localizada; o contrato de medição sai junto do relatório.

Tudo hermético: o cenário do ramo editorial (LLM roteirizado, sem rede).
"""
from __future__ import annotations

import copy
import json

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.domain.models import PageDraft, RunState
from funnelforge.pipeline.jornada import revisar_funil_pronto
from funnelforge.pipeline.routing import build_funnel_routes
from tests.cenario_editorial import (
    congelar_data,
    prompts_do_run,
    responder_v2,
    rodar_cenario,
    settings_do_cenario,
)
from tests.test_jornada_senac import SLUG, arquitetura

DOMINIO = "https://site.exemplo.com.br"


def _href(slug: str) -> str:
    return f"{DOMINIO}/rec/{slug}"


def test_redator_e_juiz_recebem_pergunta_promessa_estado_e_proxima_acao(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    settings = settings_do_cenario(tmp_path)
    state, deps, _ = rodar_cenario(tmp_path, arquitetura(), settings)
    prompts = prompts_do_run(deps.runner.runs_dir, state.run_id)
    estado = next(p for p in state.plan.pages if p.slug == SLUG["estado"])
    escrita = prompts[f"write_p{estado.page_number}"]
    assert "<jornada_do_leitor>" in escrita
    assert "Pergunta principal desta página: Onde fica o Senac do meu estado?" in escrita
    assert "Cada estado tem a própria regional do Senac" in escrita          # promessa
    assert '"Minha renda se enquadra no Programa Senac de Gratuidade?"' in escrita  # já resolvido
    assert 'Próxima dúvida ainda aberta: "Como faço a inscrição no Senac?"' in escrita
    assert f"destino {SLUG['inscricao']} [PRINCIPAL]" in escrita
    assert "Saída para a fonte oficial: boa" in escrita
    juiz = prompts[f"judge_p{estado.page_number}"]
    assert "<jornada_do_leitor>" in juiz and "Avalie também contra a jornada" in juiz
    lp = prompts["write_p1"]
    assert "O Programa Senac de Gratuidade reserva vagas" in lp


def test_briefing_do_ramo_novo_recebe_a_jornada(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    settings = settings_do_cenario(tmp_path, editorial_v2=True, passos_v2=True)
    state, deps, _ = rodar_cenario(tmp_path, arquitetura(), settings, responder=responder_v2)
    prompts = prompts_do_run(deps.runner.runs_dir, state.run_id)
    curso = next(p for p in state.plan.pages if p.slug == SLUG["curso"])
    briefing = prompts[f"briefing_p{curso.page_number}"]
    assert "<jornada_do_leitor>" in briefing
    assert "Saída para a fonte oficial: prematura" in briefing
    assert "Coloque-a depois do CTA da próxima dúvida" in briefing


def test_run_com_jornada_emite_revisao_global_e_contrato_de_medicao(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    settings = settings_do_cenario(tmp_path)
    state, deps, _ = rodar_cenario(tmp_path, arquitetura(), settings)
    assert state.step_status["revisao_esqueleto"].status.value == "OK"
    assert state.revisao_global["versao"] == "revisao-global-v1"
    assert state.revisao_global["microajustes_aplicados"] == 0
    pasta = deps.runner.runs_dir / state.run_id
    medicao = json.loads((pasta / "medicao.json").read_text(encoding="utf-8"))
    assert medicao["versao"] == "medicao-jornada-v1"
    assert medicao["leituras"] == []
    assert medicao["proposta"]["requer_aprovacao_humana"] is True
    assert medicao["proposta"]["publicacao_automatica"] is False
    assert (pasta / "revisao_global.json").exists()
    assert "## Jornada do leitor" in (pasta / "report.md").read_text(encoding="utf-8")


def test_run_sem_jornada_nao_ganha_artefato_nem_passo_novo(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    arq = arquitetura()
    del arq["funnel_strategy"]["jornada"]
    for job in arq["writing_jobs"]:
        del job["writer_briefing"]["jornada"]
    settings = settings_do_cenario(tmp_path)
    state, deps, _ = rodar_cenario(tmp_path, arq, settings)
    assert "revisao_esqueleto" not in state.step_status
    assert "revisao_global" not in state.step_status
    pasta = deps.runner.runs_dir / state.run_id
    assert not (pasta / "medicao.json").exists()
    assert all("<jornada_do_leitor>" not in t for t in prompts_do_run(
        deps.runner.runs_dir, state.run_id).values())


# ---------------------------------------------------------------------------
# revisão global: achados localizados, nenhum texto alterado
# ---------------------------------------------------------------------------

def _html(*paragrafos: str) -> str:
    return "\n\n".join(f"<!-- wp:paragraph -->\n<p>{p}</p>\n<!-- /wp:paragraph -->"
                       for p in paragrafos)


def _estado_pronto(tmp_path) -> tuple[RunState, object]:
    settings = settings_do_cenario(tmp_path)
    plano = plano_do_funnel_architecture(copy.deepcopy(arquitetura()))
    build_funnel_routes(plano, settings)
    state = RunState(run_id="r", plan=plano)
    n = {p.slug: p.page_number for p in plano.pages}
    lp = {"hero_title": "Curso gratuito no Senac",
          "hero_subtitle": "Renda de até dois salários mínimos por pessoa e inscrição na regional",
          "intro": "<p>O Programa Senac de Gratuidade reserva vagas.</p>"}
    state.drafts[1] = PageDraft(page_number=1, page_type="LANDING PAGE", format="lp_json",
                                content=json.dumps(lp, ensure_ascii=False))
    corpos = {
        "renda": _html("Some a renda bruta da família e divida pelo número de moradores.",
                       f'<a href="{_href(SLUG["curso"])}">Ver como achar o meu curso</a> '
                       f'<a href="{_href(SLUG["estado"])}">Achar o Senac do meu estado</a>'),
        # promessa fora da 1ª dobra + oficial antes do CTA da próxima dúvida
        "curso": _html("Bem-vindo! Antes de tudo, veja nossa lista de dicas.",
                       '<a href="https://www.senac.br/cursos">Cursos do Senac</a>',
                       f'<a href="{_href(SLUG["estado"])}">Achar o Senac do meu estado</a>'),
        # CTA de renda depois de a renda estar resolvida
        "estado": _html("Cada estado tem a própria regional do Senac com as vagas gratuitas.",
                        f'<a href="{_href(SLUG["inscricao"])}">Ver o passo a passo</a> '
                        f'<a href="{_href(SLUG["renda"])}">Fazer a conta da renda</a>',
                        '<a href="https://www.sp.senac.br/psg">Senac SP</a>'),
        "inscricao": _html("A inscrição gratuita é feita no site da regional do seu estado.",
                           '<a href="https://www.sp.senac.br/inscricao">Inscrição</a>'),
    }
    for duvida, corpo in corpos.items():
        num = n[SLUG[duvida]]
        state.drafts[num] = PageDraft(page_number=num, page_type="SOLUTION",
                                      format="gutenberg", content=corpo)
    return state, settings


def test_revisao_global_aponta_falhas_localizadas_sem_reescrever(tmp_path):
    state, settings = _estado_pronto(tmp_path)
    antes = {k: v.content for k, v in state.drafts.items()}
    rev = revisar_funil_pronto(state, settings)
    regras = {(a["duvida_id"], a["regra"]) for a in rev["achados"]}
    assert ("estado", "cta_repetido_apos_resolvido") in regras
    assert ("curso", "resposta_fora_da_primeira_dobra") in regras
    assert ("curso", "saida_oficial_antes_da_proxima_duvida") in regras
    assert ("estado", "loop_sem_ganho") in regras or ("renda", "loop_sem_ganho") in regras
    assert rev["decisao"] == "revisao_humana"
    assert rev["microajustes_aplicados"] == 0
    assert all(a["localizador"] and a["proposta"] for a in rev["achados"])
    assert {k: v.content for k, v in state.drafts.items()} == antes


def test_revisao_global_do_funil_coerente_nao_tem_achado_material(tmp_path):
    state, settings = _estado_pronto(tmp_path)
    n = {p.slug: p.page_number for p in state.plan.pages}
    state.drafts[n[SLUG["curso"]]] = PageDraft(
        page_number=n[SLUG["curso"]], page_type="SOLUTION", format="gutenberg",
        content=_html("O Senac oferece cursos livres, técnicos e de qualificação, presenciais e EAD.",
                      f'<a href="{_href(SLUG["estado"])}">Achar o Senac do meu estado</a>',
                      '<a href="https://www.senac.br/cursos">Cursos do Senac</a>'))
    state.drafts[n[SLUG["estado"]]] = PageDraft(
        page_number=n[SLUG["estado"]], page_type="SOLUTION", format="gutenberg",
        content=_html("Cada estado tem a própria regional do Senac com as vagas gratuitas.",
                      f'<a href="{_href(SLUG["inscricao"])}">Ver o passo a passo</a>',
                      '<a href="https://www.sp.senac.br/psg">Senac SP</a>'))
    rev = revisar_funil_pronto(state, settings)
    materiais = [a for a in rev["achados"] if a["severidade"] == "material"]
    assert materiais == [], materiais
    assert rev["decisao"] == "sem_achados"
