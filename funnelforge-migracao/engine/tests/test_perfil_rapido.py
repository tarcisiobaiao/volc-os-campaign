"""Perfil RÁPIDO de produção: uma chamada de redação por página, o mecânico por
código e UMA revisão global do funil com patch mínimo."""
from __future__ import annotations

import json
import re

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.pipeline.pipeline import run_pipeline
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


def test_uma_chamada_de_redacao_por_pagina_e_uma_revisao_global(tmp_path, monkeypatch):
    state, pasta, passos = _rodar(tmp_path, monkeypatch, _revisor(_todos_pass))
    tipos = [re.sub(r"_p\d+$", "", p) for p in passos]
    assert set(tipos) <= {"write", "revisao_global_rapida"}, tipos      # nada de briefing/juiz/seo
    assert tipos.count("revisao_global_rapida") == 1
    escritas = [p for p in passos if p.startswith("write_p")]
    assert len(set(escritas)) == 5                                        # as 5 páginas
    assert state.editorial_v2 is False
    for n in range(1, 6):
        assert state.seo[n]["origem"] == "deterministico" and len(state.seo[n]["seotitle"]) <= 60
        assert len(state.seo[n]["metadescription"]) <= 155
    pacotes = json.loads((pasta / "pacotes.json").read_text())
    assert [p["page_number"] for p in pacotes] == [1, 2, 3, 4, 5]
    assert {"titulo", "subtitulos", "cta_principal", "seo", "plano_gutenberg", "schema",
            "screenshot_oficial", "ativo", "fatos_usados", "links", "canais_oficiais"} <= set(pacotes[1])
    revisao = json.loads((pasta / "revisao_global_rapida.json").read_text())
    assert revisao["revisao_humana"] == []


def test_titulo_seo_deterministico_nao_termina_em_conectivo():
    from funnelforge.pipeline.steps import _cortar

    assert _cortar(
        "Quem Tem Direito ao Gás do Povo e Como Fazer a Consulta por CPF", 60
    ) == "Quem Tem Direito ao Gás do Povo e Como Fazer a Consulta"
    assert _cortar(
        "Onde Retirar o Gás do Povo: Revendedoras Credenciadas e Regras", 60
    ) == "Onde Retirar o Gás do Povo: Revendedoras Credenciadas"


def test_humanizacao_vai_no_prompt_do_redator_so_no_perfil_rapido(tmp_path, monkeypatch):
    _, pasta, _ = _rodar(tmp_path, monkeypatch, _revisor(_todos_pass))
    prompt = (pasta / "prompts" / "write_p2.txt").read_text()
    assert "<escrita_natural>" in prompt
    from funnelforge.prompts import render
    assert "<escrita_natural>" not in render("reader_contract", editorial={})


def test_patch_de_block_aplicado_uma_vez_libera_a_pagina_e_aviso_nao_vai_para_humano(
        tmp_path, monkeypatch):
    def vereditos(prompt):
        texto2 = prompt.split("=== PÁGINA 2")[1].split("=== PÁGINA 3")[0].split("TEXTO:\n")[1]
        frase = next(l.strip() for l in texto2.splitlines() if len(l.strip()) > 30
                     and not l.startswith("#") and "[" not in l)
        trecho = frase[:40]
        return [
            {"page_number": 1, "veredito": "pass", "achados": [], "patches": []},
            {"page_number": 2, "veredito": "block",
             "achados": [{"categoria": "fato", "severidade": "block", "motivo": "sem lastro"}],
             "patches": [{"trecho_original": trecho, "trecho_novo": "Texto corrigido.",
                          "motivo": "remove afirmação sem lastro"}]},
            {"page_number": 3, "veredito": "warning",
             "achados": [{"categoria": "estilo", "severidade": "warning", "motivo": "repetição"}],
             "patches": []},
            {"page_number": 4, "veredito": "block",
             "achados": [{"categoria": "cta", "severidade": "block", "motivo": "destino quebrado"}],
             "patches": [{"trecho_original": "TRECHO-QUE-NAO-EXISTE", "trecho_novo": "x"}]},
            {"page_number": 5, "veredito": "pass", "achados": [], "patches": []}]

    state, pasta, passos = _rodar(tmp_path, monkeypatch, _revisor(vereditos))
    revisao = json.loads((pasta / "revisao_global_rapida.json").read_text())
    por = {p["page_number"]: p for p in revisao["paginas"]}
    assert por[2]["veredito"] == "warning" and len(por[2]["patches_aplicados"]) == 1
    assert "Texto corrigido." in state.drafts[2].content
    assert por[3]["veredito"] == "warning"                               # aviso não vai a humano
    bloqueio3 = state.step_status.get("blocked_p3")
    assert bloqueio3 is None or bloqueio3.issues[0].code != "revisao_global_block"
    assert [p["page_number"] for p in revisao["revisao_humana"]] == [4]    # UMA revisão
    assert state.step_status["blocked_p4"].issues[0].code == "revisao_global_block"
    assert sum(1 for p in passos if p == "revisao_global_rapida") == 1     # sem 2ª chamada


def test_patch_do_texto_visivel_consegue_corrigir_link_e_negrito_no_gutenberg():
    from types import SimpleNamespace
    from funnelforge.pipeline.revisao_rapida import _substituir
    draft=SimpleNamespace(format='gutenberg', content=(
        '<!-- wp:paragraph --><p>Para <strong>consultar</strong>, acesse a '
        '<a href="https://oficial.example/servico">página oficial</a>.</p>'
        '<!-- /wp:paragraph -->'))
    original='Para consultar , acesse a [página oficial](https://oficial.example/servico).'
    assert _substituir(draft, original, 'Procure o órgão responsável pelo nome.')
    assert 'Procure o órgão responsável pelo nome.' in draft.content
    assert 'https://oficial.example/servico' not in draft.content


def test_no_perfil_rapido_lacuna_de_evidencia_nao_manda_pagina_para_humano(tmp_path, monkeypatch):
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
    assert not any(k.startswith("evidencia_p") for k in state.step_status)
    revisao = json.loads((deps.runner.runs_dir / state.run_id / "revisao_global_rapida.json")
                         .read_text())
    assert revisao["revisao_humana"] == []


def test_perfil_rapido_complementa_todas_as_paginas_em_um_unico_lote(tmp_path, monkeypatch):
    """Várias lacunas viram uma rodada consolidada, não uma por página."""
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
    assert len(pesquisa.pedidos) == 2                    # global + UM lote
    assert pesquisa.pedidos[0] is None
    assert len(pesquisa.pedidos[1]) >= len(state.plan.pages)
    assert "dossie_complemento_lote" in state.step_status
    assert not any(k.startswith("dossie_complemento_p") for k in state.step_status)
    assert all(p.page_number in state.drafts for p in state.plan.pages)
