"""CTAs do funil: uma chamada, antes da redação, com o código conferindo só o objetivo."""
import copy
import json
import re

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.domain.models import RunState, StepStatus
from funnelforge.pipeline.inteligencia import congelar_pacotes, pacote_conferido, prompt_do_pacote
from funnelforge.pipeline.pipeline import _populate_routes
from tests.cenario_editorial import montar_deps, responder_v2, settings_do_cenario
from tests.test_dossie_factual import FATOS_COMPLETOS, _compilar, _Pesquisa, arquitetura
from tests.test_inteligencia_pre_redacao import brief

_BOTAO_RE = re.compile(r"^- (b\d+): da página (\d+) para a página (\d+)", re.M)
_QUALQUER_BOTAO_RE = re.compile(r"^- (b\d+): da página \d+ para (a página|a saída)", re.M)
_SNIPER = "Você escreve os rótulos dos botões"
LETRAS = "abcdefghijklmnopqrstuvwxyz"


def roteiro(rotulo=lambda i, b: f"Abrir o caminho {LETRAS[i]}", falhar=False):
    def responder(model, messages):
        prompt = messages[-1]["content"]
        if _SNIPER in prompt:
            if falhar:
                raise RuntimeError("sniper fora do ar")
            ids = [b for b, _tipo in _QUALQUER_BOTAO_RE.findall(prompt)]
            return json.dumps({"botoes": [{"id": b, "rotulo": rotulo(i, b),
                                           "justificativa": "o leitor encontra isto"}
                                          for i, b in enumerate(ids)]})
        if "Você prepara as peças interativas" in prompt:
            return json.dumps({"widgets": []})
        return responder_v2(model, messages)
    return responder


def estado(tmp_path, responder):
    s = settings_do_cenario(tmp_path, editorial_v2=True, passos_v2=True)
    llm, deps = montar_deps(tmp_path, s, responder)
    state = RunState(run_id="ctas", plan=plano_do_funnel_architecture(arquitetura()),
                     brief_pre_arquitetura=brief())
    state.dossie = _compilar(state, _Pesquisa(FATOS_COMPLETOS)).model_dump(mode="json")
    _populate_routes(state, deps)
    return state, deps, llm


def chamadas_do_sniper(llm):
    return [c["messages"][-1]["content"] for c in llm.calls
            if _SNIPER in c["messages"][-1]["content"]]


def test_uma_chamada_rotula_todos_os_botoes_antes_do_hash(tmp_path):
    state, deps, llm = estado(tmp_path, roteiro())
    destinos_antes = {p.page_number: [(r.kind, r.target) for r in p.routes if r.kind == "funnel"]
                      for p in state.plan.pages}

    congelar_pacotes(state, deps)

    assert len(chamadas_do_sniper(llm)) == 1
    for p in state.plan.pages:
        funil = [r for r in p.routes if r.kind == "funnel"]
        assert [(r.kind, r.target) for r in funil] == destinos_antes[p.page_number]
        assert all(r.anchor.startswith("Abrir o caminho") for r in funil)
        pacote = pacote_conferido(state, p)          # o hash fecha com os rótulos novos
        rotulos = {lk["anchor"] for lk in pacote["links"] if lk["kind"] == "funnel"}
        assert rotulos == {r.anchor for r in funil}
        assert not any(lk.get("reformular_cta") for lk in pacote["links"])
        if funil:
            assert funil[0].anchor in prompt_do_pacote(state, p)
    registro = json.loads((tmp_path / "runs" / "ctas" / "ctas_do_funil.json").read_text())
    assert registro["pedidos"] == len(registro["botoes"]) and not registro["recusas"]
    assert all(b["justificativa"] for b in registro["botoes"])


def test_rotulo_que_o_codigo_recusa_fica_o_do_plano(tmp_path):
    ruins = {0: "Ver em https://golpe.com", 1: "x" * 70, 2: "Ver as 999 opções de curso"}
    state, deps, _ = estado(tmp_path, roteiro(
        lambda i, b: ruins.get(i, f"Abrir o caminho {LETRAS[i]}")))
    plano = copy.deepcopy(state.plan)

    congelar_pacotes(state, deps)

    recusas = state.ctas_do_funil["recusas"]
    assert set(recusas) == {"b1", "b2", "b3"}
    assert "URL" in recusas["b1"] and "caracteres" in recusas["b2"] and "número" in recusas["b3"]
    rotulos_antigos = {(p.page_number, r.target): r.anchor for p in plano.pages for r in p.routes}
    recusados = {(b["origem"], b["destino"]) for b in state.ctas_do_funil["botoes"]}
    for p in state.plan.pages:
        for r in p.routes:
            if r.kind == "funnel" and (p.page_number, r.target) not in recusados:
                assert r.anchor == rotulos_antigos[(p.page_number, r.target)]


def test_destinos_diferentes_com_o_mesmo_rotulo_nao_passam(tmp_path):
    state, deps, _ = estado(tmp_path, roteiro(lambda i, b: "Abrir o guia"))
    congelar_pacotes(state, deps)
    aplicados = state.ctas_do_funil["botoes"]
    for origem in {b["origem"] for b in aplicados}:
        assert len([b for b in aplicados if b["origem"] == origem]) == 1
    assert any("mesmo rótulo" in m for m in state.ctas_do_funil["recusas"].values())


def test_nova_congelada_so_pergunta_o_que_mudou_no_destino(tmp_path):
    state, deps, llm = estado(tmp_path, roteiro())
    congelar_pacotes(state, deps)
    destino = next(p for p in state.plan.pages
                   if not p.jornada.ativos and any(r.kind == "funnel" and r.target == p.slug
                                                   for o in state.plan.pages for r in o.routes))
    arestas = sum(1 for o in state.plan.pages for r in o.routes
                  if r.kind == "funnel" and r.target == destino.slug)
    state.pacotes = {}
    destino.jornada.resposta_imediata = "Nova entrega confirmada do destino."

    congelar_pacotes(state, deps)

    segunda = chamadas_do_sniper(llm)[-1]
    assert len(chamadas_do_sniper(llm)) == 2
    assert len(_BOTAO_RE.findall(segunda)) == arestas
    assert all(int(d) == destino.page_number for _b, _o, d in _BOTAO_RE.findall(segunda))
    assert state.ctas_do_funil["reaproveitados"] > 0


def test_sniper_fora_do_ar_mantem_os_rotulos_do_plano(tmp_path):
    state, deps, _ = estado(tmp_path, roteiro(falhar=True))
    antes = {(p.page_number, r.target): r.anchor for p in state.plan.pages for r in p.routes}

    congelar_pacotes(state, deps)

    assert state.step_status["ctas_do_funil"].status is StepStatus.FAILED
    assert {(p.page_number, r.target): r.anchor for p in state.plan.pages
            for r in p.routes if r.kind == "funnel"} == {
        k: v for k, v in antes.items() if any(
            r.kind == "funnel" and (p.page_number, r.target) == k
            for p in state.plan.pages for r in p.routes)}
    assert state.pacotes and all(pacote_conferido(state, p) for p in state.plan.pages)
