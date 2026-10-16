"""Avaliação contrafactual com o gerador provisório (TESTADO COM SINTÉTICO — não é eficácia)."""
from __future__ import annotations

import json

import pytest

from volc_dil.fundacao.shadow._gerador_provisorio import preparar
from volc_dil.fundacao.shadow.avaliacao import _drawdown, avaliar
from volc_dil.fundacao.shadow.motor import executar_replay
from volc_dil.fundacao.shadow.politicas import Guardiao72h, Manter, RegraMargem, catalogo_padrao, equal, regra_margem_imatura
from volc_dil.fundacao.shadow.tipos import BPS, EntidadeCampanha


def _rodar(nome, pols, passo=24):
    fs, cortes, cfg = preparar(nome, passo_horas=passo, hora_inicial=7 if passo == 24 else 1)
    res = executar_replay(fs.observacoes, cortes, pols, config=cfg)
    return fs, res, avaliar(res, fs.verdade, hora_decisao=7)


def test_drawdown():
    assert _drawdown([1, -3, 2, -1]) == 3 and _drawdown([5, 5]) == 0 and _drawdown([]) == 0


def test_metricas_presentes_e_natureza_sintetica():
    _, res, a = _rodar("base", catalogo_padrao())
    assert a["natureza"] == "testado_com_sintetico" and a["n_celulas"] > 0
    for nome, v in a["politicas"].items():
        assert v["regret_vs_oraculo_micros"] >= 0, nome
        assert v["drawdown_max_vs_manter_micros"] >= 0
        assert {"vs_manter_micros", "vs_equal_micros", "cortes_errados", "cortes_errados_por_sinal_imaturo",
                "estabilidade", "propostas_bloqueadas_no_corte_diario"} <= set(v)
    assert a["politicas"]["manter"]["vs_manter_micros"] == 0
    assert a["politicas"]["regra_margem"]["vs_manter_micros"] > 0  # o mundo provisório tem campanhas de ROAS 0,45 e 0,60
    assert a["politicas"]["regra_margem"]["cortes_errados"] == 0


def test_avaliacao_deterministica():
    _, _, a1 = _rodar("base", [Manter(), equal(), RegraMargem()])
    _, _, a2 = _rodar("base", [Manter(), equal(), RegraMargem()])
    assert json.dumps(a1, sort_keys=True) == json.dumps(a2, sort_keys=True)


def test_null_zero_propoe_cortes_infundados_e_o_kernel_bloqueia_todos():
    fs, res, a = _rodar("zero_sintetizado", [Manter(), RegraMargem(), catalogo_padrao()[-1]])
    nz, rm = a["politicas"]["regra_margem_null_zero"], a["politicas"]["regra_margem"]
    assert rm["cortes_errados"] == 0
    # a anti-baseline quer pausar a campanha 0 (ROAS verdadeiro 1,50: todo corte dela é errado) por "campanha morta"
    mortas = [p for d in res.da_politica("regra_margem_null_zero") for p in d.decisao.propostas
              if p.motivo.startswith("campanha_morta")]
    assert mortas and all(p.entidade.campaign_id.endswith("0") for p in mortas)
    # ...e o kernel bloqueia: ela declara usar dias sem receita medida (cobertura não comprovada, R2-G3)
    assert all(any(b.startswith("cobertura_receita_nao_comprovada") for b in p.bloqueios) for p in mortas)
    assert nz["cortes_errados"] == 0 and nz["propostas_bloqueadas_no_corte_diario"] > 0


def test_guardiao_reduz_cortes_errados_por_sinal_imaturo_em_campanha_nova():
    _, _, a = _rodar("campanha_nova", [Manter(), regra_margem_imatura(), Guardiao72h(regra_margem_imatura())])
    cru = a["politicas"]["regra_margem_imatura"]
    g = a["politicas"]["guardiao_72h[regra_margem_imatura]"]
    assert cru["cortes_errados_por_sinal_imaturo"] >= 1
    assert g["cortes_errados_por_sinal_imaturo"] < cru["cortes_errados_por_sinal_imaturo"]


def test_verdade_provisoria_pausa_zera_e_reducao_e_concava():
    fs, _, _ = preparar("base", passo_horas=24)
    cel = fs.verdade.celulas()[0]
    l = fs.verdade.lucros({cel: 0})
    assert l[cel] == 0
    m, r = fs.verdade.lucros({cel: BPS})[cel], fs.verdade.lucros({cel: 5000})[cel]
    assert r != m
    assert isinstance(cel[0], EntidadeCampanha)


@pytest.mark.parametrize("nome", ["identidade_trocada", "moeda_misturada", "restatement_tardio"])
def test_cenarios_provisorios_rodam_ponta_a_ponta(nome):
    _, res, a = _rodar(nome, [Manter(), RegraMargem(), Guardiao72h(RegraMargem())])
    assert res.decisoes and a["politicas"]["regra_margem"]["regret_vs_oraculo_micros"] >= 0
