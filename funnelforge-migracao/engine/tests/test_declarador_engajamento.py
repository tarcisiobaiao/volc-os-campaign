"""O passo declarador: quem preenche `Page.engajamento`.

O rótulo decide qual ferramenta interativa a página recebe, então o que estes
testes travam é: (1) só o vocabulário fechado entra, (2) declaração humana
nunca é sobrescrita, e (3) NENHUMA falha do classificador derruba o funil --
o fallback usa a semântica do H1/outline, nunca um sorteio por run_id.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from funnelforge.config.settings import Settings, load_settings
from funnelforge.domain.models import FunnelPlan, Page, PageRole
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.pipeline import Deps
from funnelforge.pipeline.runner import Runner
from funnelforge.prompts import render
from tests.fakes import FakeLLM


def _plan() -> FunnelPlan:
    pages = [
        Page(page_number=1, page_type="LANDING PAGE", h1_title="LP", slug="tema"),
        Page(page_number=2, page_type="HUB", h1_title="Hub", slug="tema-pr",
             role=PageRole.PRESELL),
        Page(page_number=3, page_type="SOLUTION", h1_title="Quem tem direito",
             slug="tema-p1", ordinal=1, role=PageRole.SOLUTION,
             main_content_structure=["H2: Requisitos", "H2: Quem fica de fora"]),
        Page(page_number=4, page_type="SOLUTION", h1_title="Passo a passo no app",
             slug="tema-p2", ordinal=2, role=PageRole.SOLUTION,
             main_content_structure=["H2: Passo 1", "H2: Passo 2"]),
    ]
    return FunnelPlan(total_pages=len(pages), pages=pages)


def _deps(tmp_path: Path, settings: Settings, llm: FakeLLM) -> Deps:
    runner = Runner(llm=llm, max_retries=0, runs_dir=tmp_path / "runs")
    return Deps(llm=llm, research=None, image_gen=None, image_proc=None,
                publisher=None, loader=None, settings=settings, runner=runner)


def _state(plan: FunnelPlan) -> st.RunState:
    s = st.RunState(run_id="tema-20260810-120000")
    s.plan = plan
    return s


def _resposta(*pares: tuple[str, str]) -> str:
    return json.dumps({"paginas": [
        {"slug": s, "resposta_em_uma_frase": "...", "engajamento": e} for s, e in pares]})


def test_declara_apenas_as_solucoes(tmp_path: Path, config_files: Path) -> None:
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    settings.steps["engajamento"] = settings.steps["extract"]
    plan = _plan()
    llm = FakeLLM(responses=[_resposta(("tema-p1", "condicional"),
                                       ("tema-p2", "sequencial"))])
    state = _state(plan)
    st.declarar_engajamento(state, _deps(tmp_path, settings, llm))

    por_slug = {p.slug: p.engajamento for p in plan.pages}
    assert por_slug["tema-p1"] == "condicional"
    assert por_slug["tema-p2"] == "sequencial"
    # LP e hub não são classificados -- só solução recebe widget
    assert por_slug["tema"] == "" and por_slug["tema-pr"] == ""


def test_declaracao_humana_vence_o_passo(tmp_path: Path, config_files: Path) -> None:
    """Quem já veio preenchido do briefing NÃO é tocado -- e nem entra no
    prompt, então o passo nunca gasta token para reconfirmar o humano."""
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    settings.steps["engajamento"] = settings.steps["extract"]
    plan = _plan()
    plan.pages[2].engajamento = "diagnostico"          # declarado à mão
    llm = FakeLLM(responses=[_resposta(("tema-p1", "comparativo"),
                                       ("tema-p2", "sequencial"))])
    state = _state(plan)
    st.declarar_engajamento(state, _deps(tmp_path, settings, llm))

    assert plan.pages[2].engajamento == "diagnostico"  # NÃO foi sobrescrito
    assert plan.pages[3].engajamento == "sequencial"   # a lacuna foi preenchida


def test_rotulo_fora_do_vocabulario_e_recusado(tmp_path: Path, config_files: Path) -> None:
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    settings.steps["engajamento"] = settings.steps["extract"]
    plan = _plan()
    llm = FakeLLM(responses=[_resposta(("tema-p1", "muito_interessante"),
                                       ("tema-p2", "sequencial"))])
    state = _state(plan)
    st.declarar_engajamento(state, _deps(tmp_path, settings, llm))

    assert plan.pages[2].engajamento == "condicional"  # inventado -> fallback semântico
    assert plan.pages[3].engajamento == "sequencial"
    codes = {i.code for i in state.step_status["engajamento"].issues}
    assert "engajamento_fora_do_vocabulario" in codes


@pytest.mark.parametrize("resposta", ["", "isto não é json", '{"outra_coisa": 1}'])
def test_qualquer_lixo_aplica_fallback_semantico_sem_derrubar(
        tmp_path: Path, config_files: Path, resposta: str) -> None:
    """Um classificador inválido não derruba e também não aciona loteria."""
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    settings.steps["engajamento"] = settings.steps["extract"]
    plan = _plan()
    state = _state(plan)
    st.declarar_engajamento(state, _deps(tmp_path, settings, FakeLLM(responses=[resposta])))
    assert plan.pages[0].engajamento == "" and plan.pages[1].engajamento == ""
    assert plan.pages[2].engajamento == "condicional"
    assert plan.pages[3].engajamento == "sequencial"
    assert state.step_status["engajamento"].status is not st.StepStatus.FAILED


def test_sem_config_o_passo_e_silencioso(tmp_path: Path, config_files: Path) -> None:
    """Remover `steps.engajamento` desliga o passo: nenhuma chamada de LLM,
    nenhum status registrado, o pipeline se comporta como antes dele existir."""
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    settings.steps.pop("engajamento", None)
    plan = _plan()
    state = _state(plan)
    llm = FakeLLM(responses=[])                        # qualquer chamada estouraria
    st.declarar_engajamento(state, _deps(tmp_path, settings, llm))
    assert all(p.engajamento == "" for p in plan.pages)
    assert "engajamento" not in state.step_status


def test_plano_ausente_nao_levanta(tmp_path: Path, config_files: Path) -> None:
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    state = st.RunState(run_id="x")
    st.declarar_engajamento(state, _deps(tmp_path, settings, FakeLLM(responses=[])))


# --- a rubrica precisa estar NO PROMPT, não numa nota de rodapé -------------

def test_prompt_carrega_o_vocabulario_fechado_e_o_teste_literal() -> None:
    plan = _plan()
    out = render("declarador_engajamento", country="Brasil", pages=plan.pages[2:])
    for rotulo in st.ENGAJAMENTO_VOCABULARIO:
        assert rotulo in out, rotulo
    # o TESTE LITERAL é o que separou `sequencial` de `dado_unico` no caso
    # canônico -- sem ele a declaração vira ruído
    assert "resposta_em_uma_frase" in out
    assert "ANTES de rotular" in out
    # e as páginas entram como dado, com os H2 previstos
    assert "tema-p1" in out and "H2: Requisitos" in out


def test_prompt_avisa_contra_rotulo_uniforme() -> None:
    """Rótulo igual em todas as páginas costuma significar que o classificador
    olhou o tema do funil, não a pergunta de cada página."""
    out = render("declarador_engajamento", country="Brasil", pages=_plan().pages[2:])
    assert "mesmo rótulo" in out
