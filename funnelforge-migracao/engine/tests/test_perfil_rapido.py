"""Compatibilidade do antigo rótulo ``rapido`` com o motor canônico.

O rótulo pode existir em runs salvos, mas não desliga qualidade. Velocidade é
somente concorrência entre páginas e cache.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.domain.models import Page, PageDraft, PageRole, Route, RunState, StepStatus
from funnelforge.pipeline.pipeline import run_pipeline
from funnelforge.pipeline import steps as st
from tests.cenario_editorial import congelar_data, montar_deps, responder_v1, texto_da_mensagem
from tests.test_dossie_factual import (
    FATOS_COMPLETOS,
    _arq_com_requisito_de_renda,
    _ligar_pesquisa,
    _Pesquisa,
    _settings_com_dossie,
)


def _revisor(vereditos):
    def responder(model, messages):
        prompt = texto_da_mensagem(messages[-1])
        if "REVISOR GLOBAL" in prompt:
            return json.dumps({"paginas": vereditos(prompt), "resumo": "ok"})
        return responder_v1(model, messages)
    return responder


def _rodar(tmp_path, monkeypatch, responder):
    congelar_data(monkeypatch)
    _ligar_pesquisa(monkeypatch, _Pesquisa(FATOS_COMPLETOS))
    settings = _settings_com_dossie(tmp_path)
    settings.run.perfil = "rapido"
    settings.run.page_workers = 3
    # Estes testes isolam copy/revisão. O preset real liga a imagem e o teste
    # específico do build cobre o fail-closed do hero ausente.
    settings.run.imagens_habilitadas = False
    llm, deps = montar_deps(tmp_path, settings, responder)
    state = run_pipeline(None, deps, only=None, publish=False,
                         plan=plano_do_funnel_architecture(_arq_com_requisito_de_renda()),
                         timestamp="20261007-120000")
    pasta = deps.runner.runs_dir / state.run_id
    passos = [json.loads(l)["step"] for l in (pasta / "log.jsonl").read_text().splitlines()
              if '"attempt"' in l]
    return state, pasta, passos


def _todos_pass(prompt):
    return [{"page_number": n, "veredito": "pass", "achados": [], "patches": []}
            for n in range(1, 6)]


def test_rotulo_rapido_nao_reduz_etapas_do_motor(tmp_path, monkeypatch):
    state, pasta, passos = _rodar(tmp_path, monkeypatch, _revisor(_todos_pass))
    tipos = [re.sub(r"_p\d+$", "", p) for p in passos]
    assert {"write", "judge", "seo", "widget"} <= set(tipos), tipos
    assert "revisao_global_rapida" not in tipos
    escritas = [p for p in passos if p.startswith("write_p")]
    assert len(set(escritas)) == 5                                        # as 5 páginas
    assert state.editorial_v2 is False
    assert not (pasta / "pacotes.json").exists()
    assert not (pasta / "revisao_global_rapida.json").exists()


def test_titulo_seo_deterministico_nao_termina_em_conectivo():
    from funnelforge.pipeline.steps import _cortar

    assert _cortar(
        "Quem Tem Direito ao Gás do Povo e Como Fazer a Consulta por CPF", 60
    ) == "Quem Tem Direito ao Gás do Povo e Como Fazer a Consulta"
    assert _cortar(
        "Onde Retirar o Gás do Povo: Revendedoras Credenciadas e Regras", 60
    ) == "Onde Retirar o Gás do Povo: Revendedoras Credenciadas"


def test_cta_de_navegacao_vai_ao_topo_depois_dos_tres_paragrafos():
    href = "https://creditoup.com.br/rec/proxima-solucao"
    bloco = (
        '<!-- wp:buttons --><div class="wp-block-buttons"><!-- wp:button -->'
        f'<div class="wp-block-button"><a href="{href}" '
        'class="wp-block-button__link wp-element-button">Resolver a próxima dúvida</a></div>'
        '<!-- /wp:button --></div><!-- /wp:buttons -->'
    )
    paragrafos = "\n".join(
        f"<!-- wp:paragraph --><p>Introdução {n}</p><!-- /wp:paragraph -->"
        for n in range(1, 4)
    )
    html = paragrafos + "\n<!-- wp:heading --><h2>Resposta</h2><!-- /wp:heading -->\n" + bloco
    page = Page(
        page_number=2, page_type="PRESELL", role=PageRole.PRESELL,
        slug="presell", h1_title="Presell",
        routes=[Route(placement="hero", kind="funnel", target="proxima-solucao",
                      anchor="Resolver a próxima dúvida")],
    )
    state = RunState(run_id="cta-topo")
    deps = SimpleNamespace(settings=SimpleNamespace(site=SimpleNamespace(
        domain="https://creditoup.com.br", post_type="rec")))

    saida = st.ensure_top_navigation_cta(state, page, deps, html)
    assert saida.count(bloco) == 2
    assert saida.index(bloco) < saida.index("<!-- wp:heading")
    assert saida.index(bloco) > saida.index("Introdução 3")


def test_motor_canonico_recusa_lp_sem_imagem_mesmo_com_rotulo_legado(tmp_path):
    settings = _settings_com_dossie(tmp_path)
    settings.run.perfil = "rapido"
    settings.run.imagens_habilitadas = True
    settings.run.hero_image = True
    _, deps = montar_deps(tmp_path, settings, responder_v1)
    page = Page(
        page_number=1, page_type="LANDING PAGE", role=PageRole.LP,
        slug="gas-do-povo", h1_title="Gás do Povo",
        routes=[Route(placement="hero", kind="funnel", target="proxima-pagina",
                      anchor="Ver a próxima página")],
    )
    state = RunState(run_id="gas-do-povo-sem-imagem")
    state.editorial_v2 = True
    state.briefings[1] = {"contrato": "v2"}
    state.drafts[1] = PageDraft(
        page_number=1, page_type="LANDING PAGE", format="lp_json",
        content="{}", word_count=0)

    st.step_build(state, page, deps)

    resultado = state.step_status["build_p1"]
    assert resultado.status is StepStatus.FAILED
    assert {i.code for i in resultado.issues} == {"lp_hero_obrigatorio"}


def test_rotulo_legado_nao_ativa_prompt_alternativo(tmp_path, monkeypatch):
    _, pasta, _ = _rodar(tmp_path, monkeypatch, _revisor(_todos_pass))
    prompt = (pasta / "prompts" / "write_p2.txt").read_text()
    assert "<escrita_natural>" not in prompt
    from funnelforge.prompts import render
    assert "<escrita_natural>" not in render("reader_contract", editorial={})


def test_rotulo_rapido_nao_afrouxa_revisao_de_evidencia(tmp_path, monkeypatch):
    from tests.test_dossie_factual import RENDA
    congelar_data(monkeypatch)
    _ligar_pesquisa(monkeypatch, _Pesquisa([f for f in FATOS_COMPLETOS
                                            if RENDA not in f["requisitos"]], []))
    settings = _settings_com_dossie(tmp_path)
    settings.run.perfil = "rapido"
    llm, deps = montar_deps(tmp_path, settings, _revisor(_todos_pass))
    state = run_pipeline(None, deps, only=None, publish=False,
                         plan=plano_do_funnel_architecture(_arq_com_requisito_de_renda()),
                         timestamp="20261007-120000")
    assert any(k.startswith("evidencia_p") for k in state.step_status)
    assert not (deps.runner.runs_dir / state.run_id / "revisao_global_rapida.json").exists()


def test_rotulo_rapido_preserva_complemento_tipado_por_pagina(tmp_path, monkeypatch):
    """O alias legado não troca a pesquisa precisa por um lote reduzido."""
    congelar_data(monkeypatch)
    pesquisa = _Pesquisa([], FATOS_COMPLETOS)
    _ligar_pesquisa(monkeypatch, pesquisa)
    settings = _settings_com_dossie(tmp_path)
    settings.run.perfil = "rapido"
    settings.run.page_workers = 3
    llm, deps = montar_deps(tmp_path, settings, _revisor(_todos_pass))
    state = run_pipeline(None, deps, only=None, publish=False,
                         plan=plano_do_funnel_architecture(_arq_com_requisito_de_renda()),
                         timestamp="20261007-120000")
    assert len(pesquisa.pedidos) >= 2
    assert pesquisa.pedidos[0] is None
    assert "dossie_complemento_lote" not in state.step_status
    assert any(k.startswith("dossie_complemento_p") for k in state.step_status)
    assert all(p.page_number in state.drafts for p in state.plan.pages)
