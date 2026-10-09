"""Regra do operador (09/10/2026): CPC ESTIMADO não decide nada operacional.

Keyword Planner, DataForSEO, SERP: estimativa de pesquisa. Mantida a mesma
seleção e configuração do operador, alterar, remover ou multiplicar o CPC
estimado não pode mudar decisão, seleção, bloqueador, impressão aprovável,
nem exigir/dispensar parâmetro.
"""
from __future__ import annotations

import copy

import pytest
from fastapi import HTTPException

from app.agents.mining.funnel_factory import funnel_factory_com_conjuntos
from app.routers import trafego
from tests.test_pautador_paid_keyword_counterproofs import BPC_LOAS, HOJE, IPVA


def _com_cpc(ai: dict, f) -> dict:
    novo = copy.deepcopy(ai)
    for funil in novo["funis_sugeridos"]:
        for sub in funil["sub_intencoes"]:
            for kw in sub["keywords"]:
                v = f(kw.get("cpc"))
                if v is None:
                    kw.pop("cpc", None)
                else:
                    kw["cpc"] = v
    return novo


VARIACOES = {
    "original": lambda c: c,
    "removido": lambda c: None,
    "x10": lambda c: None if c is None else c * 10,
    "x0_01": lambda c: None if c is None else c * 0.01,
    "inventado_onde_faltava": lambda c: 7.77 if c is None else c,
}


def _decisao(ai, teto):
    _fila, (conjunto,) = funnel_factory_com_conjuntos(ai, today=HOJE, teto_do_dono=teto,
                                                      congruencia="congruente")
    return {
        "decisoes": sorted((d.termo, d.decisao, d.selecionada) for d in conjunto.candidates),
        "selecionadas": sorted(d.identidade() for d in conjunto.selected_keywords),
        "bloqueadores": sorted(conjunto.blockers),
        "impressao": conjunto.selected_set_sha256,
    }


@pytest.mark.parametrize("ai", [BPC_LOAS, IPVA], ids=["bpc_loas", "ipva"])
@pytest.mark.parametrize("teto", [None, 1.0, 0.01])
def test_cpc_estimado_nao_muda_decisao_selecao_nem_impressao(ai, teto):
    base = _decisao(ai, teto)
    for nome, f in VARIACOES.items():
        assert _decisao(_com_cpc(ai, f), teto) == base, nome


def test_o_teto_do_dono_tambem_nao_muda_a_selecao():
    """O teto só comparava com a estimativa; sem efeito operacional."""
    assert _decisao(BPC_LOAS, None) == _decisao(BPC_LOAS, 0.01) == _decisao(BPC_LOAS, 100.0)


def test_estimativa_continua_visivel_como_anotacao():
    _fila, (conjunto,) = funnel_factory_com_conjuntos(BPC_LOAS, today=HOJE, teto_do_dono=1.0,
                                                      congruencia="congruente")
    acima = [d for d in conjunto.selected_keywords if d.cpc.tem_numero and d.cpc.valor > 1.0]
    assert acima and all("cpc_estimado_acima_do_teto_declarado" in d.alertas for d in acima)


# ── fronteira HTTP: parâmetro ausente é pedido de volta, não preenchido ─────

def _body(**troca):
    base = dict(opportunity_id=1, customer_id="5478096539", login_customer_id="6016739364",
                canal="SEARCH")
    base.update(troca)
    return trafego.ProvarEntrada(**base)


def test_sem_orcamento_o_pedido_volta_com_o_que_falta():
    with pytest.raises(HTTPException) as e:
        trafego._exigir_parametros_do_operador(_body(cpc_inicial=0.5), "SEARCH")
    assert e.value.status_code == 422
    assert e.value.detail["codigo"] == "PARAMETRO_DO_OPERADOR_AUSENTE"
    assert any("budget_diario" in f for f in e.value.detail["faltam"])


def test_manual_cpc_sem_lance_o_pedido_volta():
    with pytest.raises(HTTPException) as e:
        trafego._exigir_parametros_do_operador(_body(budget_diario=10), "SEARCH")
    assert any("cpc_inicial" in f for f in e.value.detail["faltam"])


def test_lance_por_grupo_em_todos_os_grupos_dispensa_o_da_campanha():
    b = _body(budget_diario=10, grupos=[{"tipo": "A", "keywords": ["x"], "cpc_inicial": 0.3}])
    trafego._exigir_parametros_do_operador(b, "SEARCH")


def test_estrategia_automatica_nao_exige_lance_manual():
    b = _body(budget_diario=10, estrategia_lance="MAXIMIZE_CONVERSIONS")
    trafego._exigir_parametros_do_operador(b, "SEARCH")


def test_nao_ha_mais_valor_padrao_de_orcamento_ou_lance():
    b = _body()
    assert b.budget_diario is None and b.cpc_inicial is None
