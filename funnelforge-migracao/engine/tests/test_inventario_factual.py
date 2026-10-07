"""INVENTÁRIO FACTUAL e os contextos que a ponte leva ao plano (B4, itens 4 e 8).

O inventário é uma função PURA sobre o estado: fatos tipados (com a regra de
legado para `state.json` antigo), fontes com o selo de "resolveu ao vivo",
canais oficiais escolhidos na pesquisa, termos de busca em três estados, a
leitura (PAA + tensão) e o anúncio que traz o leitor à LP. Ausência é dita,
nunca preenchida por suposição.
"""
from __future__ import annotations

import json
from pathlib import Path

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.domain.models import (
    FunnelPlan, Page, PageRole, ResearchFacts, RunState, VerifiedFact,
)
from funnelforge.pipeline.inventario import montar_inventario
from tests.cenario_editorial import arquitetura_base

FIXTURE_220001 = Path(__file__).parent / "fixtures" / "state_run_220001.json"


def _termos(estado: str = "presente", termos=None, **extra) -> dict:
    base = {
        "estado": estado,
        "janela": {"inicio": "2026-09-21", "fim": "2026-09-30", "fuso": "America/Sao_Paulo"},
        "coletado_em": "2026-09-30T08:20:00-03:00",
        "fonte": "search_term_view",
        "termos": termos if termos is not None else [],
        "motivo_ausencia": None,
    }
    return {**base, **extra}


# ---------------------------------------------------------------------------
# a ponte (`briefing_volc`) leva os contextos novos ao plano
# ---------------------------------------------------------------------------

def test_ponte_leva_leitura_busca_anuncio_e_flag_ao_plano():
    arq = arquitetura_base()
    arq["contexto_de_leitura"] = {
        "perguntas_paa": ["Quem tem direito a tarifa social?", "Como pedir o desconto?"],
        "tensao": {"frase": "Acha que precisa pagar alguem para pedir", "evidencia": "validacao:7/10"},
    }
    arq["contexto_de_busca"] = _termos(termos=[
        {"termo": "tarifa social como pedir", "impressoes": 120, "cliques": 9, "custo": 3.1}])
    arq["contexto_de_anuncio"] = {"estado": "presente", "titulos": ["Tarifa Social: Guia"],
                                  "descricoes": ["Veja quem tem direito."], "fonte": "copy:77"}
    arq["editorial_v2"] = True
    plano = plano_do_funnel_architecture(arq)
    assert plano.editorial_v2 is True
    assert plano.contexto_de_leitura.perguntas_paa[1] == "Como pedir o desconto?"
    assert plano.contexto_de_leitura.tensao.frase.startswith("Acha que precisa")
    assert plano.contexto_de_busca.estado == "presente"
    assert plano.contexto_de_busca.termos[0].cliques == 9
    assert plano.contexto_de_anuncio.titulos == ["Tarifa Social: Guia"]
    # o que já existia continua: tom e avatar do arquiteto
    assert plano.tone_voice and plano.avatar_summary


def test_ponte_sem_contextos_deixa_none_e_nao_inventa_nada():
    plano = plano_do_funnel_architecture(arquitetura_base())
    assert plano.contexto_de_leitura is None
    assert plano.contexto_de_busca is None
    assert plano.contexto_de_anuncio is None


def test_termos_ausente_nunca_vira_lista():
    """`ausente` com termos é contrato quebrado: vira `ausente` SEM a lista,
    com o motivo escrito — nunca uma lista que ninguém coletou de verdade."""
    arq = arquitetura_base()
    arq["contexto_de_busca"] = _termos(estado="ausente", termos=[
        {"termo": "inventado", "impressoes": 1, "cliques": 1, "custo": None}])
    plano = plano_do_funnel_architecture(arq)
    assert plano.contexto_de_busca.estado == "ausente"
    assert plano.contexto_de_busca.termos == []
    assert "inválido" in (plano.contexto_de_busca.motivo_ausencia or "")


def test_termos_presente_sem_janela_e_recusado_como_ausente():
    arq = arquitetura_base()
    arq["contexto_de_busca"] = _termos(janela=None, termos=[
        {"termo": "x", "impressoes": 1, "cliques": 0, "custo": None}])
    plano = plano_do_funnel_architecture(arq)
    assert plano.contexto_de_busca.estado == "ausente"
    assert plano.contexto_de_busca.termos == []


def test_anuncio_invalido_vira_ausente_com_motivo():
    arq = arquitetura_base()
    arq["contexto_de_anuncio"] = {"estado": "presente", "titulos": [], "descricoes": [],
                                  "fonte": "copy:1"}
    plano = plano_do_funnel_architecture(arq)
    assert plano.contexto_de_anuncio.estado == "ausente"
    assert plano.contexto_de_anuncio.titulos == []
    assert plano.contexto_de_anuncio.motivo_ausencia


def test_pagina_sem_editorial_do_arquiteto_de_fallback_continua_valida():
    plano = plano_do_funnel_architecture(arquitetura_base(editorial=False))
    assert all(p.editorial is None for p in plano.pages)


# ---------------------------------------------------------------------------
# o inventário
# ---------------------------------------------------------------------------

def _estado_do_220001() -> RunState:
    return RunState.from_json(FIXTURE_220001.read_text(encoding="utf-8"))


def test_inventario_do_run_senac_tipa_os_7_fatos_pela_regra_de_legado():
    """O caso real (run 220001, p1): sem tipo na pesquisa. A regra de legado
    olha SÓ a `unidade` (nunca o `dispositivo`, que cita decreto nos 4 fatos):
    só o n4 ('número do Decreto-Lei') é `fonte_legal`; os demais números ficam
    `numero`; os 3 dados qualitativos viram `contexto`. Nenhum fato se perde."""
    state = _estado_do_220001()
    page = state.plan.pages[0]
    inv = montar_inventario(state, page)
    tipos = {f.id: f.tipo for f in inv.fatos}
    assert tipos == {"f1": "contexto", "f2": "contexto", "f3": "contexto",
                     "n1": "numero", "n2": "numero", "n3": "numero", "n4": "fonte_legal"}
    assert {f.tipo_origem for f in inv.fatos} == {"regra_legado"}
    n2 = next(f for f in inv.fatos if f.id == "n2")
    # valor e unidade SEPARADOS por espaço (o defeito V8 era "2salários")
    assert n2.texto.startswith("2 salários mínimos")


def test_inventario_usa_o_tipo_da_pesquisa_quando_existe():
    facts = ResearchFacts(
        fontes=["https://a.exemplo.gov.br/x"],
        fontes_resolvidas=["https://a.exemplo.gov.br/x"],
        dados_validados=[{"fato": "Quem pede e a distribuidora.", "fonte": "https://a.exemplo.gov.br/x",
                          "tipo": "orgao", "escopo": "nacional"}],
        fatos_verificados=[VerifiedFact(
            valor="2", unidade="salarios minimos per capita", tipo="condicao",
            escopo="regional:SP", citavel=True, fonte_primaria="https://a.exemplo.gov.br/x",
            dispositivo="Decreto de exemplo", vigente_desde="2008-11-05",
            verificado_em="2026-09-29")],
    )
    page = Page(page_number=3, page_type="SOLUTION", slug="x-p1", h1_title="X",
                role=PageRole.SOLUTION)
    state = RunState(run_id="r", plan=FunnelPlan(pages=[page]), facts={3: facts},
                     official_links={3: ["https://a.exemplo.gov.br/x"]})
    inv = montar_inventario(state, page)
    f1, n1 = inv.fatos
    assert (f1.id, f1.tipo, f1.escopo, f1.tipo_origem) == ("f1", "orgao", "nacional", "pesquisa")
    assert (n1.id, n1.tipo, n1.escopo, n1.citavel) == ("n1", "condicao", "regional:SP", True)
    assert n1.verificada_ao_vivo is True and f1.verificada_ao_vivo is False
    assert inv.canais_oficiais == ["https://a.exemplo.gov.br/x"]
    fonte = inv.fontes[0]
    assert (fonte.papel, fonte.resolvida) == ("oficial", True)


def test_termos_ausentes_quando_o_card_nao_mandou():
    state = RunState(run_id="r", plan=FunnelPlan(pages=[]))
    page = Page(page_number=1, page_type="LANDING PAGE", slug="x", h1_title="X")
    inv = montar_inventario(state, page)
    assert inv.termos_de_busca.estado == "ausente"
    assert inv.termos_de_busca.amostra == []
    assert "contexto_de_busca" in inv.termos_de_busca.motivo_ausencia
    assert inv.leitura.estado == "ausente"
    assert inv.anuncio.estado == "ausente"


def test_termos_presentes_passam_pelo_filtro_de_dado_pessoal_e_pelo_corte():
    arq = arquitetura_base()
    termos = [{"termo": f"tarifa social termo {i}", "impressoes": 100 - i, "cliques": i % 7,
               "custo": None} for i in range(40)]
    termos += [
        {"termo": "tarifa social 123.456.789-09", "impressoes": 999, "cliques": 50, "custo": None},
        {"termo": "fulano@exemplo.com tarifa", "impressoes": 999, "cliques": 49, "custo": None},
        {"termo": "tarifa social 11987654321", "impressoes": 999, "cliques": 48, "custo": None},
    ]
    arq["contexto_de_busca"] = _termos(termos=termos)
    plano = plano_do_funnel_architecture(arq)
    state = RunState(run_id="r", plan=plano)
    inv = montar_inventario(state, plano.pages[0])
    tb = inv.termos_de_busca
    assert tb.estado == "presente"
    assert tb.descartados_por_dado_pessoal == 3
    assert tb.total_na_fonte == 43
    assert len(tb.amostra) == 25
    fonte = {t["termo"] for t in termos}
    assert set(tb.amostra) <= fonte              # termos enviados ⊆ termos da fonte
    assert not any("@" in t or "123.456" in t or "11987654321" in t for t in tb.amostra)
    # o mais clicado primeiro
    assert tb.amostra[0] == "tarifa social termo 6"


def test_vazio_confirmado_e_diferente_de_ausente():
    arq = arquitetura_base()
    arq["contexto_de_busca"] = _termos(estado="vazio_confirmado")
    plano = plano_do_funnel_architecture(arq)
    inv = montar_inventario(RunState(run_id="r", plan=plano), plano.pages[0])
    assert inv.termos_de_busca.estado == "vazio_confirmado"
    assert inv.termos_de_busca.amostra == []
    assert inv.termos_de_busca.janela.startswith("2026-09-21")


def test_leitura_e_anuncio_do_card_entram_e_o_anuncio_so_na_lp():
    arq = arquitetura_base()
    arq["contexto_de_leitura"] = {"perguntas_paa": ["Quem tem direito?"],
                                  "tensao": {"frase": "Medo de pagar taxa", "evidencia": "validacao:6/10"}}
    arq["contexto_de_anuncio"] = {"estado": "presente", "titulos": ["Tarifa Social: Guia"],
                                  "descricoes": [], "fonte": "gads:825"}
    plano = plano_do_funnel_architecture(arq)
    state = RunState(run_id="r", plan=plano)
    lp = montar_inventario(state, plano.pages[0])
    interna = montar_inventario(state, plano.pages[2])
    assert lp.leitura.estado == "presente" and lp.leitura.perguntas_paa == ["Quem tem direito?"]
    assert lp.leitura.tensao["frase"] == "Medo de pagar taxa"
    assert lp.anuncio.estado == "presente" and lp.anuncio.titulos == ["Tarifa Social: Guia"]
    assert interna.leitura.estado == "presente"
    assert interna.anuncio.estado == "ausente"
    assert "interna" in interna.anuncio.motivo_ausencia


def test_inventario_e_serializavel_para_o_artefato_do_run():
    state = _estado_do_220001()
    inv = montar_inventario(state, state.plan.pages[2])
    dados = json.loads(inv.model_dump_json())
    assert dados["pagina"] == 3
    assert dados["canais_oficiais"] == ["https://www.sp.senac.br"]
