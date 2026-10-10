"""Com esqueleto aprovado, a primeira pesquisa parte das entregas das páginas."""
from types import SimpleNamespace as NS

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.adapters.pesquisa_plano import _prompt_da_pesquisa
from funnelforge.pipeline import inteligencia
from funnelforge.pipeline.dossie import REQUISITO_DO_CANAL_OFICIAL, especificacao_das_paginas
from tests.test_jornada_senac import arquitetura

CARD = {"main_keyword": "curso gratuito Senac", "country": "BR", "native_language": "pt-BR",
        "contexto_de_leitura": {"perguntas_paa": ["Quem tem direito ao curso gratuito?"]}}


def _deps(tmp_path):
    settings = NS(run=NS(jev_enabled=False), steps={"dossie": NS(fallbacks=[], model="m")})
    return NS(runner=NS(runs_dir=tmp_path), attention_matrix=None, settings=settings, bucket=None)


def test_plano_aprovado_dispensa_a_pesquisa_antecipada(tmp_path, monkeypatch):
    from funnelforge.adapters import research_perplexity as rp
    monkeypatch.setattr(rp, "pesquisar_funil", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("com esqueleto aprovado não há pesquisa guiada pelo PAA")))
    assert inteligencia.plano_aprovado_valido(arquitetura())
    assert not inteligencia.plano_aprovado_valido({"pages": [{"x": 1}]})
    state = NS(step_status={}, brief_pre_arquitetura=None, pesquisa_pre_arquitetura={})
    inteligencia.preparar_inteligencia(state, _deps(tmp_path), CARD, pesquisar=False)
    assert state.brief_pre_arquitetura.duvidas            # PAA continua no brief
    assert state.pesquisa_pre_arquitetura == {}           # a 1ª pesquisa é a do dossiê
    codigos = {i.code for i in state.step_status["inteligencia"].issues}
    assert "pesquisa_pelo_esqueleto_aprovado" in codigos


def test_especificacao_pede_requisitos_ferramentas_e_canal_da_tarefa():
    plano = plano_do_funnel_architecture(arquitetura())
    spec = {s["duvida_id"]: s for s in especificacao_das_paginas(
        [p for p in plano.pages if p.jornada is not None])}
    for p in plano.pages:
        ids = [r["id"] for r in spec[p.jornada.duvida_id]["requisitos"]]
        assert {r.id for r in p.jornada.requisitos} <= set(ids)
        for a in p.jornada.ativos:                       # dados das ferramentas
            assert a.rule_source_fact_id in ids
        saida = p.jornada.saida_oficial
        esperado = bool(saida and saida.esperada and saida.condicao.strip())
        assert (REQUISITO_DO_CANAL_OFICIAL in ids) is esperado
        if esperado:
            canal = next(r for r in spec[p.jornada.duvida_id]["requisitos"]
                         if r["id"] == REQUISITO_DO_CANAL_OFICIAL)
            assert saida.condicao.strip() in canal["descricao"]


def test_requisito_compartilhado_e_pedido_uma_vez():
    paginas = [{"duvida_id": "quanto_paga", "requisitos": [
                   {"id": "alcance", "descricao": "Limite e percentual do desconto"}]},
               {"duvida_id": "desconto_social", "requisitos": [
                   {"id": "alcance", "descricao": "Limite e percentual do desconto"},
                   {"id": "regra", "descricao": "Critérios do Desconto Social"}]}]
    prompt = _prompt_da_pesquisa("tarifa social", paginas, None, "10/10/2026")
    assert prompt.count("alcance: Limite e percentual do desconto") == 1
    assert "[quanto_paga, desconto_social] alcance" in prompt
    faltam = [{"duvida_id": "a", "requisito": "r", "descricao": "d"},
              {"duvida_id": "b", "requisito": "r", "descricao": "d"}]
    assert _prompt_da_pesquisa("t", [], faltam, "10/10/2026").count("r: d") == 1
