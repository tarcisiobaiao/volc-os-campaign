"""RED — moeda sem câmbio em intervalos de pesquisa e em simulação.

Achados 4 e 5 da missão V2.
"""
from __future__ import annotations

from dataclasses import replace

from volc_dil.contracts import Dinheiro
from volc_dil.viability.contrato import Evidencia, PontoSimulacao, SimulacaoEntrada
from volc_dil.viability.economia import Indisponivel
from volc_dil.viability.gate import Veredito, avaliar
from volc_dil.viability.teto import calcular_teto

from _entradas import AS_OF, entrada


def test_red04_intervalos_de_pesquisa_em_usd_com_perda_maxima_em_brl_sem_cambio_nao_geram_teto():
    """Achado 4. Campanha nova sem histórico: CPC [0,30; 0,60] USD e RPC [0,70; 1,10] USD de
    pesquisa; tolerância do owner 300 BRL; nenhum câmbio.

    V1 está errada porque `_cpc_rpc_conservadores` lê só `.micros` dos intervalos e
    `calcular_teto` compara a moeda da perda com a do CUSTO — que não existe (campanha nova),
    então a checagem compara a perda com ela mesma. Resultado: teto em "BRL" calculado com
    micros de USD e veredito `test_with_cap` (preparar campanha pausada).

    V2 deve recusar: sem câmbio não há teto (`Indisponivel`/`moeda_incompativel`), veredito
    `insufficient_evidence`, `max_experiment_spend=None`.
    """
    e = entrada(receita_none=True, custo_none=True, cliques=None, perda="300", horizonte=14)
    e = replace(e, cpc_intervalo=(Dinheiro.de_decimal("0.30", "USD"), Dinheiro.de_decimal("0.60", "USD")),
                rpc_intervalo=(Dinheiro.de_decimal("0.70", "USD"), Dinheiro.de_decimal("1.10", "USD")))
    teto = calcular_teto(e)
    assert isinstance(teto, Indisponivel), f"V1 calcula teto misturando USD e BRL: {teto}"
    r = avaliar(e)
    assert r.max_experiment_spend is None and r.max_experiment_clicks is None
    assert r.verdict is not Veredito.TEST_WITH_CAP
    assert any("moeda" in x for x in (*r.missing_evidence, *(m.codigo for m in r.reasons))), (r.missing_evidence, [m.codigo for m in r.reasons])


def test_red05_simulacao_em_usd_com_economia_em_brl_sem_cambio_nao_e_analisada():
    """Achado 5. Economia favorável em BRL (1000 cliques, custo 80, receita 160) e
    `campaign_simulation` CPC_BID com `moeda="USD"`, sem câmbio na simulação.

    V1 está errada porque `analisar_simulacao` recebe só `rpc_conservador` e nunca olha
    `SimulacaoEntrada.moeda`: compara CPC marginal em USD com RPC em BRL e declara pontos
    "sustentáveis". Com USD/BRL ≈ 5, um segmento 5× mais caro do que parece passa como expansão
    aceitável.

    V2 deve devolver `CurvaIndisponivel("moeda_incompativel")` (não analisada) e nenhuma razão
    de expansão sustentável/destrutiva derivada da curva.
    """
    pontos = (PontoSimulacao(50_000, 500, 20_000_000), PontoSimulacao(100_000, 1000, 80_000_000), PontoSimulacao(200_000, 1300, 160_000_000))
    sim = SimulacaoEntrada("CPC_BID", "USD", pontos, AS_OF, "MANUAL_CPC")
    e = entrada(cliques=1000, custo="80.00", receita="160.00", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED,
                receita_ev=Evidencia.OBSERVED, perda="300", horizonte=14)
    r = avaliar(replace(e, simulacao=sim))
    assert r.simulacao is not None
    assert r.simulacao.get("disponivel") is False, f"V1 analisa a curva em USD contra RPC em BRL: {r.simulacao}"
    assert "moeda" in str(r.simulacao.get("motivo", "")), r.simulacao
    assert not any(m.codigo == "expansao_marginal_destrutiva" for m in r.reasons)
    assert not any(a.startswith("expansao_aceitavel_ate_modificacao") for a in r.assumptions)
