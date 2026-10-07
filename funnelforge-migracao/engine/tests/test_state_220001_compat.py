"""`state.json` ANTIGO (run Senac 220001, de 17/09/2026) carrega e retoma.

É o estado real de um run publicado como rascunho, anterior a toda a reforma:
sem `tipo` nos fatos, sem `editorial_v2`, sem `briefings`, sem os contextos
novos no plano. Os campos novos são aditivos; nada que existia se perde, e a
retomada não refaz o que já foi feito — nem com a flag ligada: o ramo novo só
gera briefing para página AINDA NÃO escrita.
"""
from __future__ import annotations

import json
from pathlib import Path

from funnelforge.domain.models import RunState, StepStatus
from tests.cenario_editorial import (
    SEO_JSON,
    congelar_data,
    montar_deps,
    settings_do_cenario,
    texto_da_mensagem,
)
from funnelforge.pipeline.pipeline import run_pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "state_run_220001.json"


def _carregar() -> RunState:
    return RunState.from_json(FIXTURE.read_text(encoding="utf-8"))


def _nenhuma_chamada(model, messages):
    raise AssertionError("a retomada de um run pronto não pode chamar o modelo: "
                         + texto_da_mensagem(messages[-1])[:120])


def test_carrega_com_os_campos_novos_nos_padroes():
    state = _carregar()
    assert state.run_id == "guia-cursos-senac-20260917-220001"
    assert state.editorial_v2 is False and state.briefings == {}
    assert state.plan.editorial_v2 is False
    assert state.plan.contexto_de_busca is None and state.plan.contexto_de_leitura is None
    fatos = [f for facts in state.facts.values() for f in facts.fatos_verificados]
    assert fatos and all(f.tipo is None and f.escopo is None and f.citavel is None
                         for f in fatos)


def test_ida_e_volta_pelo_checkpoint_nao_perde_nada_do_que_existia():
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    de_volta = json.loads(RunState.from_json(_carregar().to_json()).to_json())
    for chave in ("run_id", "briefing_text", "drafts", "seo", "images", "image_reviews",
                  "screenshots", "official_links", "published", "step_status"):
        assert de_volta[chave] == original[chave], chave
    assert [p["slug"] for p in de_volta["plan"]["pages"]] == [
        p["slug"] for p in original["plan"]["pages"]]
    for n, facts in original["facts"].items():
        for i, fato in enumerate(facts["fatos_verificados"]):
            novo = de_volta["facts"][n]["fatos_verificados"][i]
            assert {k: novo[k] for k in fato} == fato     # os campos antigos intactos
            assert (novo["tipo"], novo["escopo"], novo["citavel"]) == (None, None, None)
        assert de_volta["facts"][n]["dados_validados"] == facts["dados_validados"]


def _retomar(tmp_path: Path, monkeypatch, state: RunState, *, editorial_v2: bool,
             responder=_nenhuma_chamada):
    congelar_data(monkeypatch)
    settings = settings_do_cenario(tmp_path, editorial_v2=editorial_v2, passos_v2=True)
    llm, deps = montar_deps(tmp_path, settings, responder)
    final = run_pipeline(None, deps, only=None, publish=False, resume_state=state)
    return final, deps, llm


def test_retoma_um_run_pronto_sem_chamar_o_modelo(tmp_path: Path, monkeypatch):
    antes = {k: v.status for k, v in _carregar().step_status.items()}
    final, deps, llm = _retomar(tmp_path, monkeypatch, _carregar(), editorial_v2=False)
    assert llm.calls == []
    assert {k: v.status for k, v in final.step_status.items()} == antes
    assert final.editorial_v2 is False
    assert (deps.runner.runs_dir / final.run_id / "report.md").exists()


def test_retoma_com_a_flag_ligada_sem_reescrever_o_que_ja_existe(tmp_path: Path, monkeypatch):
    antes = {k: v.status for k, v in _carregar().step_status.items()}
    final, _deps, llm = _retomar(tmp_path, monkeypatch, _carregar(), editorial_v2=True)
    assert llm.calls == []                      # nenhum briefing para página já escrita
    assert final.briefings == {}
    assert {k: v.status for k, v in final.step_status.items()} == antes
    assert final.editorial_v2 is True           # o run passa a ser do ramo novo daqui em diante


def _responder_seo(model, messages):
    prompt = texto_da_mensagem(messages[-1])
    if "YOAST SEO" in prompt or "Você escreve o TÍTULO SEO" in prompt:
        return SEO_JSON
    return _nenhuma_chamada(model, messages)


def test_retoma_passo_pendente_com_o_prompt_de_cada_ramo(tmp_path: Path, monkeypatch):
    """Um passo pendente (o SEO da p2) é refeito: com a flag desligada pelo
    prompt antigo; com a flag ligada pelo SEO v2 (sem ano, sem 'curiosidade')."""
    for ligado, marca in ((False, "YOAST SEO"), (True, "Você escreve o TÍTULO SEO")):
        state = _carregar()
        del state.step_status["seo_p2"]
        final, _deps, llm = _retomar(tmp_path / str(ligado), monkeypatch, state,
                                     editorial_v2=ligado, responder=_responder_seo)
        assert len(llm.calls) == 1
        assert marca in texto_da_mensagem(llm.calls[0]["messages"][-1])
        assert final.step_status["seo_p2"].status is StepStatus.OK
