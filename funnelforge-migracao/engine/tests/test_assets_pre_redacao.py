"""PAA reaproveitado, pesquisa ultranichada, cálculo real e promessa efetiva."""
import copy
import json
from decimal import Decimal

import pytest

from funnelforge.adapters.attention_matrix import perguntas
from funnelforge.domain.models import CalculoDoAtivo, PageDraft
from funnelforge.pipeline.dossie import CompiladorDeDossie
from funnelforge.pipeline.inteligencia import congelar_pacotes, prompt_do_pacote
from funnelforge.pipeline.pipeline import _populate_routes
from funnelforge.pipeline.steps import step_widget, ensure_top_navigation_cta
from funnelforge.pipeline.validators.checks import sanitize_widget_block
from funnelforge.widgets.calculos import calcular, renderizar_calculo, validar
from tests.cenario_editorial import settings_do_cenario, montar_deps, responder_v2
from tests.test_dossie_factual import (
    _estado, _n, _compilar, _Pesquisa, _Deps, _registrar_canais, _ler,
    FATOS_COMPLETOS, HOJE, RENDA,
)
from tests.test_inteligencia_pre_redacao import brief


def calculo(op="divisao"):
    casos = {
        "divisao": [(["3000", "3"], "1000"), (["1", "8"], "0.13")],
        "multiplicacao": [(["2", "1621"], "3242"), (["0.10", "0.15"], "0.02")],
        "percentual": [(["100", "15"], "15"), (["1", "0.50"], "0.01")],
    }
    return CalculoDoAtivo(operacao=op, rotulos=["Valor", "Fator"],
        rotulo_resultado="Resultado informativo",
        casos=[{"entradas": a, "resultado": b} for a, b in casos[op]])


def test_paa_do_pautador_nao_consulta_serp(tmp_path):
    class Proibido:
        def chamar(self, *args):
            raise AssertionError("Coleta já feita pelo Pautador")
    resultado = perguntas({"main_keyword": "tema", "location_code": 2076,
        "language_code": "pt", "contexto_de_leitura": {
            "perguntas_paa": ["Como calcular?", "Como calcular?"]}}, tmp_path, cliente=Proibido())
    assert resultado["perguntas"] == ["Como calcular?"]
    assert resultado["origem"] == "pautador.contexto_de_leitura"


@pytest.mark.parametrize("op", ["divisao", "multiplicacao", "percentual"])
def test_calculo_conferido_e_markup_sanitizado(op):
    c = calculo(op)
    assert all(r["ok"] for r in validar(c))
    bloco = renderizar_calculo(c, titulo='Minha conta <script>', identidade="p3")
    assert sanitize_widget_block(bloco) == []
    assert '&lt;script&gt;' in bloco
    assert bloco == renderizar_calculo(c, titulo='Minha conta <script>', identidade="p3")


# "1.234,56" saiu daqui em 10/10: o formato brasileiro passou a ser aceito
# (ver test_calculadora_inteiros); o americano continua ambíguo.
@pytest.mark.parametrize("a,b", [("NaN", "2"), ("Infinity", "2"), ("-1", "2"),
    ("1,234.56", "2"), ("1e3", "2"), ("1", "0"), ("1000000000001", "2")])
def test_calculo_recusa_entradas_ambiguas_ou_invalidas(a, b):
    with pytest.raises(ValueError):
        calcular("divisao", a, b)


def test_exemplo_errado_nao_e_aceito_como_prova():
    c = calculo()
    c.casos[0].resultado = "999"
    with pytest.raises(ValueError, match="não corresponde"):
        validar(c)
    assert calcular("divisao", "1", "8") == Decimal("0.13")


def compilador(pesquisa):
    state = _estado()
    for p in state.plan.pages:
        for a in p.jornada.ativos:
            a.current_value_source_fact_id = "renda.valor_vigente"
    vivo = CompiladorDeDossie(state, _Deps(), pesquisa, registrar_canais=_registrar_canais,
        hoje=HOJE, ler_documento=_ler)
    vivo.compilar(complementos=0)
    return state, vivo


def test_uma_rodada_agrupada_leva_conteudo_e_ferramenta_juntos():
    """Antes: lote sem as ferramentas + até duas buscas só delas. Agora a única
    complementação já pede a regra e o valor vigente da calculadora."""
    sem_ferramenta = [f for f in FATOS_COMPLETOS if not set(f["requisitos"]) & {
        RENDA, "renda.valor_vigente", "salario_minimo.vigente"}]
    resto = [f for f in FATOS_COMPLETOS if f not in sem_ferramenta]
    pesquisa = _Pesquisa(sem_ferramenta, resto)
    state, vivo = compilador(pesquisa)
    resumo = vivo.complementar_lote(state.plan.pages, state)
    assert resumo["pesquisadas"] >= 2 and len(pesquisa.pedidos) == 2
    pedidos = {f["requisito"] for f in pesquisa.pedidos[1]}
    assert {RENDA, "renda.valor_vigente"} <= pedidos
    # A lacuna já pesquisada não volta numa segunda chamada.
    vivo.complementar_lote(state.plan.pages, state)
    assert len(pesquisa.pedidos) == 2


def test_rodada_agrupada_com_defeito_nao_e_repetida():
    from funnelforge.pipeline.dossie import RespostaDaPesquisa
    consultas = []

    def pesquisar(assunto, spec, faltantes):
        consultas.append(faltantes)
        if faltantes is None:
            return RespostaDaPesquisa(dados={"fatos": []}, citacoes=[])
        return RespostaDaPesquisa(dados={"fatos": []}, citacoes=[], defeito="timeout")
    state, vivo = compilador(pesquisar)
    assert vivo.complementar_lote(state.plan.pages, state)["defeito"] == "timeout"
    vivo.complementar_lote(state.plan.pages, state)
    assert len(consultas) == 2


def pacote(tmp_path, *, ruim=False, sem_fonte=False):
    s = settings_do_cenario(tmp_path, editorial_v2=True, passos_v2=True)
    s.run.widgets_enabled = True
    _, deps = montar_deps(tmp_path, s, responder_v2)
    state = _estado()
    p = next(p for p in state.plan.pages if p.jornada.ativos)
    p.jornada.ativos[0].calculo = calculo()
    if ruim:
        p.jornada.ativos[0].calculo.casos[0].resultado = "999"
    state.brief_pre_arquitetura = brief()
    fatos = [] if sem_fonte else FATOS_COMPLETOS
    d = _compilar(state, _Pesquisa(fatos), complementos=0)
    state.dossie = d.model_dump(mode="json")
    _populate_routes(state, deps)
    original = copy.deepcopy([p.jornada.model_dump(mode="json") for p in state.plan.pages])
    congelar_pacotes(state, deps)
    assert original == [p.jornada.model_dump(mode="json") for p in state.plan.pages]
    return state, p, deps


def test_ferramenta_pre_validada_injetada_sem_chamada_llm(tmp_path):
    state, p, deps = pacote(tmp_path)
    ferramentas = state.pacotes[p.page_number]["ferramenta"]
    assert ferramentas["estado"] == "pronta"
    state.drafts[p.page_number] = PageDraft(page_number=p.page_number, page_type=p.page_type, format="gutenberg",
        content='<!-- wp:paragraph --><p>Texto original.</p><!-- /wp:paragraph -->')
    antes = len(deps.llm.calls)
    step_widget(state, p, deps)
    assert len(deps.llm.calls) == antes
    assert "data-vc-operation" in state.drafts[p.page_number].content
    assert state.step_status[f"widget_p{p.page_number}"].attempts == 0
    prompt = prompt_do_pacote(state, p)
    assert "BigInt" not in prompt
    assert "<style>" not in prompt
    assert "sem consulta de cadastro" in prompt
    assert "bloco" in ferramentas["itens"][0]  # contexto enxuto não muda o pacote
    injetado = state.drafts[p.page_number].content
    step_widget(state, p, deps)
    assert state.drafts[p.page_number].content == injetado
    assert len(deps.llm.calls) == antes


def test_navegacao_nao_reintroduz_copy_da_ferramenta_retirada(tmp_path):
    # ferramenta retirada por gabarito que não bate com o código (sem fonte, a
    # calculadora de operação fixa continua pronta desde 10/10/2026)
    state, p, deps = pacote(tmp_path, ruim=True)
    corpo = ("<!-- wp:paragraph --><p>Informação verificável.</p><!-- /wp:paragraph -->\n" * 3
             + "<!-- wp:heading --><h2>Próximo passo</h2><!-- /wp:heading -->")
    assert ensure_top_navigation_cta(state, p, deps, corpo) == corpo


def test_calculadora_de_operacao_fixa_fica_pronta_sem_lastro_do_limite(tmp_path):
    """10/10/2026: renda ÷ moradores não depende do salário-mínimo. Sem fonte da
    regra ou do valor vigente, a conta segue disponível e o texto é proibido de
    afirmar o limite ou concluir direito (degradação no dossiê)."""
    state, p, deps = pacote(tmp_path, sem_fonte=True)
    assert state.pacotes[p.page_number]["ferramenta"]["estado"] == "pronta"
    degradacoes = (state.dossie.get("paginas") or {}) if isinstance(state.dossie, dict) else {}
    texto = json.dumps(state.dossie, ensure_ascii=False)
    assert "não afirme o limite em reais" in texto, degradacoes


@pytest.mark.parametrize("ruim,sem_fonte", [(True, False)])
def test_fallback_fecha_promessa_e_cta_antes_da_redacao(tmp_path, ruim, sem_fonte):
    state, p, deps = pacote(tmp_path, ruim=ruim, sem_fonte=sem_fonte)
    pac = state.pacotes[p.page_number]
    assert pac["ferramenta"]["estado"] == "fallback_sem_js"
    assert pac["entrega_confirmada"]["substituiu_promessa"]
    assert pac["jornada"]["resposta_imediata"] == p.jornada.ativos[0].fallback_sem_js
    assert any(l.get("reformular_cta") for l in pac["links"])
    assert "reformular_cta=true" in prompt_do_pacote(state, p)
    state.drafts[p.page_number] = PageDraft(page_number=p.page_number,
        page_type=p.page_type, format="gutenberg", content="Texto preservado")
    antes = len(deps.llm.calls)
    step_widget(state, p, deps)
    assert len(deps.llm.calls) == antes
    assert state.drafts[p.page_number].content == "Texto preservado"


def test_chromium_resultados_reais_e_sem_overflow():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for op in ("divisao", "multiplicacao", "percentual"):
                c = calculo(op)
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.set_content(renderizar_calculo(c, titulo="Teste", identidade=op))
                for caso in c.casos:
                    for i, v in enumerate(caso.entradas):
                        page.locator("input").nth(i).fill(v)
                    assert page.locator("[data-vc-out]").inner_text() == str(
                        calcular(op, *caso.entradas)).replace(".", ",")
                    assert page.locator("[data-vc-out]").get_attribute("data-vc-status") == "ok"
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.locator("input").nth(1).fill("0")
                if op == "divisao":
                    assert page.locator("[data-vc-out]").get_attribute("data-vc-status") == "invalid"
                page.close()
        finally:
            browser.close()


def test_ferramenta_pronta_nao_apaga_rotulos_nem_troca_a_promessa(tmp_path):
    """Run real 09/10: a calculadora pronta da pré-sell apagou os três botões
    dela e o da LP que chegava nela; o redator reescreveu e saíram mornos."""
    state, p, deps = pacote(tmp_path)
    assert state.pacotes[p.page_number]["ferramenta"]["estado"] == "pronta"
    for pacote_ in state.pacotes.values():
        assert not any(l.get("reformular_cta") for l in pacote_["links"])
    assert state.pacotes[p.page_number]["jornada"]["resposta_imediata"] == \
        p.jornada.resposta_imediata
