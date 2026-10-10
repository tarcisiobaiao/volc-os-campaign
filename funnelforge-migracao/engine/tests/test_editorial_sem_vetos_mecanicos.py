"""Diretriz do operador: liberdade editorial com revisão contextual real no fluxo.

LLMs e WordPress são dublês nestes testes; nenhuma chamada externa é feita.
"""
import json

import pytest

from funnelforge.pipeline import preflight
from funnelforge.pipeline.retry_policy import VALIDADORES_EDITORIAIS
from funnelforge.pipeline.validators import checks
from tests.cenario_editorial import arquitetura_base, briefing_valido, responder_v2
from tests.cenario_revisor import responder_fluxo, rodar_fluxo
from tests.test_editorial_v2_ramo_novo import _rodar
from tests.test_revisor_fluxo import _bloqueio_da_promessa, H3, PROMESSA, SLUG3, _interna, _p


def _proibido(*args, **kwargs):
    raise AssertionError("scanner editorial mecânico executado")


@pytest.mark.parametrize("flag", ["editorial_v2", "contextual_editorial"])
def test_scanners_editoriais_nao_sao_executados(flag, monkeypatch):
    for nome in VALIDADORES_EDITORIAIS:
        monkeypatch.setitem(checks.VALIDATORS, nome, _proibido)
    assert checks.run_validators(sorted(VALIDADORES_EDITORIAIS),
                                 '<p>Não perca: desconto de 70%.</p>', {flag: True}) == []
    for nome in preflight.PREFLIGHT:
        monkeypatch.setitem(preflight.PREFLIGHT, nome, _proibido)
    assert preflight.preflight_issues(list(preflight.PREFLIGHT), {flag: True}) == []


def test_fluxo_canonico_inteiro_nao_chama_scanners_de_copy(tmp_path, monkeypatch):
    from funnelforge.pipeline import steps
    from funnelforge.pipeline import copy_contract

    for nome in VALIDADORES_EDITORIAIS:
        monkeypatch.setitem(checks.VALIDATORS, nome, _proibido)
    monkeypatch.setattr(steps.lp_gate, "avaliar_plano_de_destino", _proibido)
    monkeypatch.setattr(copy_contract, "cta_issues", _proibido)
    monkeypatch.setattr(copy_contract, "disclosure_issues", _proibido)
    state, deps, llm, wp = rodar_fluxo(
        tmp_path, monkeypatch, arquitetura_base(), responder=responder_fluxo(), publish=True)
    assert len(state.recibos) == 5
    assert len(wp.posts) + len(wp.paginas) == 5  # Somente o WordPress falso.
    assert all(r["decisao"] == "aprovado" for r in state.recibos.values())
    assert all(r["attempts"] == 1 for r in (
        s.model_dump() for k, s in state.step_status.items() if k.startswith("write_")))


def test_revisor_llm_ainda_recusa_promessa_material_sem_blacklist(tmp_path, monkeypatch):
    for nome in VALIDADORES_EDITORIAIS:
        monkeypatch.setitem(checks.VALIDATORS, nome, _proibido)
    state, deps, llm, wp = rodar_fluxo(
        tmp_path, monkeypatch, arquitetura_base(),
        responder=responder_fluxo(internas={H3: _interna(extra=_p(PROMESSA))},
                                  revisores={3: _bloqueio_da_promessa}), publish=True)
    assert state.revisoes[3]["decisao"] == "revisao_humana"
    assert 3 not in state.recibos and SLUG3 not in wp.posts
    assert PROMESSA in state.drafts[3].content
    assert state.step_status["write_p3"].attempts == 1
    assert len(wp.posts) + len(wp.paginas) == 4


def test_briefing_semantico_avisa_mas_nao_reescreve_antes_do_writer(tmp_path, monkeypatch):
    def responder(model, messages):
        prompt = messages[-1]["content"]
        if "EDITOR DE BRIEFING" in prompt:
            dados = json.loads(briefing_valido(prompt))
            dados["intencao"]["intencao_real_da_busca"] = {
                "texto": "quer o desconto", "base": "fato", "ref": ["n1"]}
            dados["beneficios"] = [{"texto": "desconto garantido", "fatos": [], "limite": ""}]
            return json.dumps(dados)
        return responder_v2(model, messages)
    state, deps, llm = _rodar(tmp_path, monkeypatch, arquitetura_base(), responder=responder)
    for n in range(1, 6):
        assert state.step_status[f"briefing_p{n}"].attempts == 1
        assert state.step_status[f"write_p{n}"].attempts == 1


def test_html_quebrado_e_script_arbitrario_ainda_sao_recusados():
    ctx = {"editorial_v2": True}
    quebrado = '<!-- wp:paragraph --><p>Texto válido, bloco incompleto.</p>'
    assert checks.run_validators(["gutenberg_blocks"], quebrado, ctx)
    script = '<!-- wp:html --><script>alert(1)</script><!-- /wp:html -->'
    from funnelforge.pipeline.editorial_safety import html_issues
    assert html_issues(script)


def test_fato_inexistente_continua_sendo_referencia_quebrada(tmp_path, monkeypatch):
    def responder(model, messages):
        prompt = messages[-1]["content"]
        if "EDITOR DE BRIEFING" in prompt:
            dados = json.loads(briefing_valido(prompt))
            dados["beneficios"] = [{"texto": "desconto", "fatos": ["id_que_nao_existe"],
                                    "limite": "conforme o programa"}]
            return json.dumps(dados)
        return responder_v2(model, messages)
    state, deps, llm = _rodar(tmp_path, monkeypatch, arquitetura_base(), responder=responder)
    assert not any(k.startswith("seo_") for k in state.step_status)
    for n in range(1, 6):
        assert state.step_status[f"write_p{n}"].attempts == 0
        assert "ref_inexistente" in {i.code for i in state.step_status[f"briefing_p{n}"].issues}


def test_config_distribuida_usa_revisor_contextual_por_padrao():
    from pathlib import Path
    import yaml
    cfg = yaml.safe_load((Path(__file__).parents[1] / "config.yaml").read_text())
    assert cfg["run"]["editorial_v2"] is True
