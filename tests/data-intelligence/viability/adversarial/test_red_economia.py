"""RED — economia observada: break-even por clique vs por visita, visitas=0, valores negativos.

Achados 2 e 7 da missão V2.
"""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from volc_dil.contracts import Dinheiro
from volc_dil.viability.contrato import ContratoViabilidadeViolado, Evidencia, MedidaContagem, MedidaMonetaria
from volc_dil.viability.economia import Indisponivel, calcular_economia, fronteira
from volc_dil.viability.gate import avaliar

from _entradas import AS_OF, entrada


def _cem_cliques_cinquenta_visitas(visitas: int):
    e = entrada(cliques=100, custo="100", receita="75", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED)
    return replace(e, visitas=MedidaContagem(valor=visitas, evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF))


def test_red02_break_even_por_clique_usa_receita_sobre_cliques_nao_sobre_visitas():
    """Achado 2. 100 cliques, 50 visitas, custo 100 BRL, receita 75 BRL (observada).

    V1 está errada porque `rpc = receita / visitas` (1,50/visita) e `break_even_cpc = rpc`: o
    kernel compara um CPC pago POR CLIQUE (1,00) com uma receita POR VISITA (1,50) e conclui
    que há folga de 0,50 por clique — quando a campanha perde 0,25 por clique. Metade dos
    cliques pagos nunca virou visita; essa perda é da campanha, não do denominador.

    V2 deve manter contribuição = −25 BRL (V1 acerta isso), usar receita/cliques (0,75) como
    break-even e só REPORTAR receita/visita, sem usá-la na decisão.
    """
    e = _cem_cliques_cinquenta_visitas(50)
    eco = calcular_economia(e)
    assert not isinstance(eco, Indisponivel)
    assert eco.contribuicao == Dinheiro(-25_000_000, "BRL"), "contribuição nunca é zero quando custo > receita"
    assert eco.break_even_cpc == Fraction(75_000_000, 100), f"V1 usa receita/visita como break-even: {eco.break_even_cpc}"
    r = avaliar(e)
    assert r.contribution_observed == Dinheiro(-25_000_000, "BRL")
    assert r.break_even_cpc == Fraction(750_000)
    assert r.break_even_cpc < r.observed_cpc, "economia é desfavorável: break-even (0,75) < CPC (1,00)"
    fr = fronteira(e)
    assert not isinstance(fr, Indisponivel) and fr.distancia_economica > 0, "distância econômica positiva = desfavorável"


def test_red02b_zero_visitas_nao_cai_para_cliques():
    """Achado 2 (variante). Mesmos números com `visitas=0` observado.

    V1 está errada porque `visitas = e.visitas.valor if (... and e.visitas.valor) else e.cliques.valor`
    trata 0 como "não informado" e usa os cliques — zero observado vira ausência, e ausência vira
    outro número. V2 deve aceitar visitas=0 como valor válido, deixar a receita por visita
    indisponível e nunca recair nos cliques.
    """
    e = _cem_cliques_cinquenta_visitas(0)
    eco = calcular_economia(e)
    assert not isinstance(eco, Indisponivel)
    rpv = getattr(eco, "rpc_por_visita", None)
    assert rpv is None or isinstance(rpv, Indisponivel), f"receita por visita precisa ficar indisponível com 0 visitas: {rpv}"
    assert getattr(eco, "visitas_elegiveis", 0) == 0, "V1 substitui visitas=0 por cliques=100"
    assert eco.break_even_cpc == Fraction(750_000)


@pytest.mark.parametrize("campo", ["custo", "receita"])
def test_red07_valor_bruto_negativo_e_recusado_na_construcao(campo):
    """Achado 7. Custo ou receita bruta negativa (−1 BRL) com evidência observada.

    V1 está errada porque `MedidaMonetaria` aceita qualquer `Dinheiro`, inclusive micros
    negativos: um ajuste contábil ou estorno vira "custo negativo" e melhora a contribuição.

    V2 deve recusar na construção (ContratoViabilidadeViolado) qualquer valor bruto < 0;
    o sinal negativo só é legítimo na CONTRIBUIÇÃO (receita − custo).
    """
    with pytest.raises(ContratoViabilidadeViolado):
        MedidaMonetaria(valor=Dinheiro(-1_000_000, "BRL"), evidencia=Evidencia.OBSERVED, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF, fonte=campo)
    with pytest.raises(ContratoViabilidadeViolado):
        MedidaMonetaria.de_json({"valor": {"micros": -1, "moeda": "BRL"}, "evidencia": "observed", "moeda_evidencia": "observed", "disponivel_em": AS_OF.isoformat()})


def test_red07_controle_contribuicao_pode_ser_negativa():
    """Controle do achado 7 (deve passar na V1 e na V2): a contribuição observada pode e deve
    ser negativa quando custo > receita; a proibição é só sobre valores brutos."""
    r = avaliar(entrada(cliques=100, custo="100", receita="75", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED))
    assert r.contribution_observed is not None and r.contribution_observed.micros < 0
