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
_SNIPER = "os textos de clique de um funil editorial inteiro"
LETRAS = "abcdefghijklmnopqrstuvwxyz"


_AJUSTE_RE = re.compile(r"^- página (\d+): promessa original", re.M)
DOBRA = {"titulo": "Curso gratuito no Senac pela renda",
         "subtitulo": "Famílias de baixa renda podem estudar sem pagar mensalidade; veja a "
                      "regra de renda e o caminho da inscrição.",
         "justificativa": "benefício e escopo antes da navegação"}


def roteiro(rotulo=lambda i, b: f"Abrir o caminho {LETRAS[i]}", falhar=False, dobra=None,
            entrega=lambda n: "A página mostra a regra que está confirmada e indica onde "
                              "conferir o restante na fonte oficial."):
    def responder(model, messages):
        prompt = messages[-1]["content"]
        if _SNIPER in prompt:
            if falhar:
                raise RuntimeError("sniper fora do ar")
            ids = [b for b, _tipo in _QUALQUER_BOTAO_RE.findall(prompt)]
            saida = {"botoes": [{"id": b, "rotulo": rotulo(i, b),
                                 "justificativa": "o leitor encontra isto"}
                                for i, b in enumerate(ids)]}
            if "# PRIMEIRA DOBRA DA LANDING PAGE" in prompt:
                saida["primeira_dobra"] = dobra if dobra is not None else DOBRA
            ajustes = [int(n) for n in _AJUSTE_RE.findall(prompt)]
            if ajustes:
                saida["entregas_ajustadas"] = [{"pagina": n, "entrega": entrega(n),
                                                "o_que_sai": "a regra sem fonte"}
                                               for n in ajustes]
            return json.dumps(saida)
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
    assert registro["primeira_dobra"]["titulo"] == DOBRA["titulo"]


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


def test_primeira_dobra_com_numero_inventado_ou_navegacao_longa_e_recusada(tmp_path):
    ruim = {"titulo": "Curso gratuito: 99% de aprovação", "subtitulo": DOBRA["subtitulo"]}
    state, deps, _ = estado(tmp_path, roteiro(dobra=ruim))
    congelar_pacotes(state, deps)
    assert state.ctas_do_funil["primeira_dobra"] == {}
    assert "número" in state.ctas_do_funil["recusas"]["primeira_dobra"]


def test_promessa_sem_lastro_ganha_entrega_ajustada_e_delta_registrado(tmp_path):
    state, deps, llm = estado(tmp_path, roteiro())
    pagina = next(p for p in state.dossie["paginas"] if p["page_number"] == 4)
    pagina["cobertura"]["requisitos"].append(
        {"requisito_id": "regra.sem_fonte", "coberto": False, "fatos": [], "motivo": "x",
         "estado": "unsupported", "central": True, "risco": "alto"})
    plano_antes = state.plan.pages[3].model_dump(mode="json")
    congelar_pacotes(state, deps)
    prompt = chamadas_do_sniper(llm)[0]
    assert "- página 4: promessa original" in prompt
    ajuste = state.ctas_do_funil["entregas_ajustadas"][0]
    assert ajuste["pagina"] == 4 and ajuste["requisitos_sem_lastro"] == ["regra.sem_fonte"]
    pacote = state.pacotes[4]
    assert pacote["jornada"]["resposta_imediata"] == ajuste["entrega"]
    assert pacote["entrega_confirmada"]["substituiu_promessa"] is True
    assert "entrega_ajustada" in {i.code for i in state.step_status["delta_de_entrega"].issues}
    # O plano aprovado não muda em silêncio: a página do plano fica como estava.
    original = plano_antes["jornada"]["resposta_imediata"]
    assert state.plan.pages[3].jornada.resposta_imediata == original


def test_recongelar_so_a_pagina_cuja_saida_oficial_mudou(tmp_path):
    from funnelforge.pipeline.inteligencia import recongelar_paginas
    state, deps, llm = estado(tmp_path, roteiro())
    congelar_pacotes(state, deps)
    n = next(p.page_number for p in state.plan.pages
             if any(r.kind == "external_official" for r in p.routes))
    antes = copy.deepcopy(state.pacotes)
    nova = "https://www.senac.br/servico-exato-da-tarefa"
    state.official_links[n] = [nova, *state.official_links[n]]

    recongelar_paginas(state, deps, [n])

    assert len(chamadas_do_sniper(llm)) == 2
    segunda = chamadas_do_sniper(llm)[-1]
    assert len(_QUALQUER_BOTAO_RE.findall(segunda)) == 1          # só a aresta que mudou
    pagina = next(p for p in state.plan.pages if p.page_number == n)
    assert next(r.target for r in pagina.routes if r.kind == "external_official") == nova
    assert all(state.pacotes[k] == antes[k] for k in antes if k != n)
    assert state.pacotes[n]["sha256"] != antes[n]["sha256"]


def test_primeira_dobra_longa_demais_para_o_celular_e_recusada(tmp_path):
    longa = dict(DOBRA, titulo="Curso gratuito no Senac para famílias de baixa renda em 2026")
    state, deps, _ = estado(tmp_path, roteiro(dobra=longa))
    congelar_pacotes(state, deps)
    assert state.ctas_do_funil["primeira_dobra"] == {}
    assert "caracteres" in state.ctas_do_funil["recusas"]["primeira_dobra"]
