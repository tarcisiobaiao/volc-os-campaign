"""Simulator Lab — conservação: o valor fechado observado bate com a verdade (± declarado)."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pytest

from volc_dil.fundacao.simulador import iso, simular, visao_as_of

SEED = 20261016
FIM = "9999-12-31T00:00:00+00:00"
METRICA_VERDADE = {
    ("google_ads", "cost"): "custo_final_micros", ("google_ads", "impressions"): "impressoes",
    ("joinads", "revenue"): "receita_micros", ("joinads", "pageviews"): "pageviews",
    ("site_analytics", "sessions"): "sessoes", ("site_analytics", "destino"): "destino",
    ("site_analytics", "pageviews"): "pageviews",
}


@lru_cache(maxsize=None)
def _sim(nome: str):
    return simular(nome, SEED, n_campanhas=8, n_dias=14)


def _verdade(sim, fonte, metrica):
    m = sim.mundo
    if (fonte, metrica) == ("google_ads", "clicks"):
        return m.diario("cliques") - m.diario("cliques_invalidos") - m.diario("cliques_bot_detectados")
    return m.diario(METRICA_VERDADE[(fonte, metrica)])


def _fechados(sim):
    """Último valor conhecido por fato de campanha (consumidor correto), indexado por (fonte, métrica, c, dia)."""
    m = sim.mundo
    idx = {c.id: c.idx for c in m.campanhas}
    dia = {iso(m.instante_local(i, 0)): i for i in range(m.D)}
    out = {}
    for r in visao_as_of(sim.leituras.registros, FIM).values():
        if r.entidade_tipo == "campaign" and r.entidade in idx:
            out[(r.fonte, r.metrica, idx[r.entidade], dia[r.janela_inicio])] = r
    return out


@pytest.mark.parametrize("nome", ["estavel", "restatement_custo", "fonte_fora_do_ar", "atraso_receita_longo",
                                  "moeda_misturada", "execucao_presa", "campanha_nova_aprendendo", "outlier_bot"])
def test_valor_fechado_igual_a_verdade(nome):
    sim = _sim(nome)
    m = sim.mundo
    fech = _fechados(sim)
    existe = m.existe_dia()
    q = sim.espec.observador.join_quantum_micros
    faltando = []
    for (fonte, metrica) in list(METRICA_VERDADE) + [("google_ads", "clicks")]:
        verdade = _verdade(sim, fonte, metrica)
        for c in range(m.C):
            for i in range(m.D):
                if not existe[c, i]:
                    assert (fonte, metrica, c, i) not in fech  # sem registro antes de existir (não é zero)
                    continue
                r = fech.get((fonte, metrica, c, i))
                if r is None:
                    faltando.append((fonte, metrica, c, i))
                    continue
                assert r.maturidade == "final", (nome, fonte, metrica, c, i, r.tipo_leitura)
                tol = q // 2 if metrica == "revenue" else 0
                assert abs(r.valor - int(verdade[c, i])) <= tol, (nome, fonte, metrica, c, i, r.valor, int(verdade[c, i]))
    # a única lacuna permitida é receita/pageviews JoinAds sem dado com chave trocada (forma real da API)
    for fonte, metrica, c, i in faltando:
        assert fonte == "joinads", (fonte, metrica, c, i)
        assert int(m.diario("receita_micros")[c, i]) == 0 or sim.espec.observador.join_p_troca_chave_com_dado > 0


def test_restatement_declarado_explica_a_diferenca():
    sim = _sim("restatement_custo")
    pend = []
    for r in sim.leituras.registros:
        g = sim.leituras.gabarito[r.obs_id]
        if r.fonte == "google_ads" and r.metrica == "cost" and r.tipo_leitura == "d1" and r.valor is not None:
            assert g.restatement_pendente == r.valor - g.valor_verdade_final
            assert g.restatement_pendente >= 0  # D-1 nunca abaixo do faturado (crédito só reduz)
            pend.append((g.restatement_pendente, g.valor_verdade_final))
    tot_pend = sum(p for p, _ in pend)
    tot = sum(v for _, v in pend)
    assert tot_pend > 0.05 * tot  # o cenário realmente produz restatement material


def test_custo_d0_inclui_credito_pendente():
    sim = _sim("restatement_custo")
    m = sim.mundo
    bruto, final = m.diario("custo_bruto_micros").sum(), m.diario("custo_final_micros").sum()
    assert bruto > final
    assert m.diario("credito_micros").sum() == bruto - final


def test_zero_falso_quebra_a_conservacao_exatamente_onde_ha_armadilha():
    sim = _sim("zero_falso")
    m = sim.mundo
    fech = _fechados(sim)
    quebras = 0
    for (fonte, metrica, c, i), r in fech.items():
        if (fonte, metrica) not in METRICA_VERDADE:
            continue
        g = sim.leituras.gabarito[r.obs_id]
        v = int(_verdade(sim, fonte, metrica)[c, i])
        tol = sim.espec.observador.join_quantum_micros // 2 if metrica == "revenue" else 0
        if abs(r.valor - v) > tol:
            assert "zero_falso" in g.armadilhas, (fonte, metrica, c, i)
            assert r.valor == 0 and r.status == "observed"
            quebras += 1
    assert quebras > 0
