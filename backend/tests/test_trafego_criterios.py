"""A fronteira HTTP dos critérios de keyword — o que entra, e como sai tipado.

⚠️ O defeito que este arquivo existe para travar: `GrupoEscolhido.negativas`
estava no contrato desde sempre. O Pydantic aceitava, a tela podia mandar, e
NENHUM caminho lia — `Escolha` não tinha onde guardar. A negativa que o
operador declarava por sub-intenção morria na fronteira, a campanha subia sem
ela, e nada na resposta dizia isso.

Um campo aceito e ignorado é pior que um campo ausente: o ausente dá erro, o
ignorado dá a impressão de que funcionou.

Nada aqui fala com o Google. O que se prova é a CONVERSÃO — de JSON para
`Criterio` —, que é onde o defeito morava.
"""
from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi import HTTPException

from app.routers import trafego

RAIZ = pathlib.Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from volc_ads import pautador_ponte as pp  # noqa: E402


def _corpo(**troca):
    base = dict(
        opportunity_id=1,
        customer_id="8017851692",
        login_customer_id="8017851692",
        grupos=[trafego.GrupoEscolhido(tipo="ACESSO", keywords=["saque anual"])],
    )
    base.update(troca)
    return trafego.ProvarEntrada(**base)


def _mapa(crits):
    return {c.texto: c for c in crits}


# ── o campo que estava morto ────────────────────────────────────────────────


def test_negativa_de_grupo_do_http_vira_criterio_no_grupo():
    corpo = _corpo(grupos=[
        trafego.GrupoEscolhido(tipo="ACESSO", keywords=["saque anual"],
                               negativas=["simulador"]),
        trafego.GrupoEscolhido(tipo="VALOR", keywords=["valor do saque"]),
    ])
    crits = trafego._criterios_do_corpo(corpo, pp)
    c = _mapa(crits)["simulador"]
    assert c.negativa is True
    assert c.nivel == "AD_GROUP"
    assert c.grupo == "ACESSO", "a negativa perdeu o grupo em que foi declarada"


def test_negativa_de_grupo_nao_vira_negativa_de_campanha():
    """O nível errado é pior que o campo morto: bloqueia a campanha inteira."""
    corpo = _corpo(grupos=[
        trafego.GrupoEscolhido(tipo="ACESSO", keywords=["saque anual"],
                               negativas=["simulador"]),
    ])
    crits = trafego._criterios_do_corpo(corpo, pp)
    assert all(c.nivel == "AD_GROUP" for c in crits if c.negativa)


# ── as quatro fontes convergem numa lista só ────────────────────────────────


def test_as_quatro_fontes_de_negativa_entram_juntas():
    corpo = _corpo(
        grupos=[trafego.GrupoEscolhido(tipo="ACESSO", keywords=["saque anual"],
                                       negativas=["do grupo"])],
        negativas_campanha=["da campanha"],
        negativas_adgroup=["de todos os grupos"],
        criterios=[trafego.CriterioEntrada(
            texto="tipada", match_type="EXACT", negativa=True, nivel="CAMPAIGN")],
    )
    crits = trafego._criterios_do_corpo(corpo, pp)
    m = _mapa(crits)
    assert m["tipada"].match_type == "EXACT"
    assert m["tipada"].nivel == "CAMPAIGN"
    assert m["da campanha"].nivel == "CAMPAIGN"
    assert m["da campanha"].match_type == "BROAD"
    assert m["de todos os grupos"].nivel == "AD_GROUP"
    assert m["de todos os grupos"].grupo is None
    assert m["do grupo"].grupo == "ACESSO"


def test_sem_negativa_nenhuma_o_adaptador_devolve_vazio():
    """O caminho antigo continua intacto para quem não declara nada."""
    assert trafego._criterios_do_corpo(_corpo(), pp) == []


def test_o_tipado_vence_o_legado_na_mesma_identidade():
    """O operador revisou o tipado; o legado que repita não pode sobrescrever."""
    corpo = _corpo(
        negativas_campanha=["simulador"],
        criterios=[trafego.CriterioEntrada(
            texto="simulador", match_type="BROAD", negativa=True,
            nivel="CAMPAIGN", motivo="revisado na tela")],
    )
    crits = trafego._criterios_do_corpo(corpo, pp)
    assert len(crits) == 1
    assert crits[0].motivo == "revisado na tela"


# ── match type individual atravessa o HTTP ──────────────────────────────────


def test_match_type_individual_sobrevive_a_fronteira():
    corpo = _corpo(criterios=[
        trafego.CriterioEntrada(texto="um", match_type="EXACT", negativa=True),
        trafego.CriterioEntrada(texto="dois", match_type="PHRASE", negativa=True),
        trafego.CriterioEntrada(texto="tres", match_type="BROAD", negativa=True),
    ])
    m = _mapa(trafego._criterios_do_corpo(corpo, pp))
    assert (m["um"].match_type, m["dois"].match_type, m["tres"].match_type) == (
        "EXACT", "PHRASE", "BROAD")


# ── procedência e evidência ─────────────────────────────────────────────────


def test_evidencia_medida_atravessa_com_janela_e_metricas():
    corpo = _corpo(criterios=[trafego.CriterioEntrada(
        texto="simulador", match_type="PHRASE", negativa=True,
        origem="SEARCH_TERM", motivo="312 impressoes, 0 clique",
        evidencia=trafego.EvidenciaEntrada(
            tipo="MEDIDO", fonte="search_term_view",
            janela_inicio="2026-08-01", janela_fim="2026-08-27",
            metricas={"impressoes": 312, "cliques": 0}),
    )])
    c = trafego._criterios_do_corpo(corpo, pp)[0]
    assert c.medido is True
    assert c.evidencia.janela_inicio.isoformat() == "2026-08-01"
    assert c.evidencia.metricas["impressoes"] == 312


def test_search_term_sem_medicao_e_recusado_na_fronteira():
    """Hipótese com crachá de fato não passa nem pelo HTTP."""
    corpo = _corpo(criterios=[trafego.CriterioEntrada(
        texto="simulador", negativa=True, origem="SEARCH_TERM")])
    with pytest.raises(ValueError, match="SEARCH_TERM"):
        trafego._criterios_do_corpo(corpo, pp)


def test_ausencia_de_evidencia_continua_ausencia():
    corpo = _corpo(criterios=[trafego.CriterioEntrada(
        texto="simulador", negativa=True, origem="MANUAL")])
    c = trafego._criterios_do_corpo(corpo, pp)[0]
    assert c.evidencia is None
    assert c.motivo is None
    assert c.observado_em is None
    assert c.medido is False


def test_data_invalida_vira_422_e_nao_hoje():
    """Ausência é ausência; data quebrada é erro — nunca `date.today()`."""
    corpo = _corpo(criterios=[trafego.CriterioEntrada(
        texto="x", negativa=True,
        evidencia=trafego.EvidenciaEntrada(
            tipo="HIPOTESE", fonte="modelo", janela_inicio="ontem"))])
    with pytest.raises(HTTPException) as exc:
        trafego._criterios_do_corpo(corpo, pp)
    assert exc.value.status_code == 422


# ── o contrato antigo continua aceito ───────────────────────────────────────


def test_cliente_antigo_sem_criterios_continua_valido():
    corpo = _corpo(negativas_campanha=["emprestimo"], negativas_adgroup=["simulador"])
    crits = trafego._criterios_do_corpo(corpo, pp)
    assert {c.match_type for c in crits} == {"BROAD"}, \
        "mudar o default do legado alteraria o alcance de campanhas em produção"
    assert {c.origem for c in crits} == {"LEGADO"}
