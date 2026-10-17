"""RED — stop-loss compara PERDA líquida com a tolerância, não o gasto bruto.

Achado 6 da missão V2.

Nota sobre os números: o briefing cita gasto 1000 / receita 950 / tolerância 100. Com as
premissas conservadoras declaradas (custo ×1,05, receita ×0,9) a perda conservadora desse caso
é 1050 − 855 = 195 > 100, e um stop-loss conservador legítimo dispararia na V2. Para que o
teste prove APENAS o erro de comparar gasto bruto, uso 1000 / 999 / 200: perda observada 1,
perda conservadora 150,9 — ambas abaixo da tolerância — e gasto bruto 1000 acima dela.
"""
from __future__ import annotations

from volc_dil.viability.contrato import Evidencia
from volc_dil.viability.gate import Recomendacao, avaliar

from _entradas import entrada


def _caso(custo: str, receita: str, perda: str):
    return entrada(cliques=1000, custo=custo, receita=receita, moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED,
                   receita_ev=Evidencia.OBSERVED, perda=perda, horizonte=14)


def test_red06_gasto_bruto_acima_da_tolerancia_com_perda_liquida_abaixo_nao_e_stop_loss():
    """Achado 6. Gasto 1000 BRL, receita 999 BRL (observada, madura, mesma moeda), tolerância 200 BRL.

    V1 está errada porque o gatilho é `custo > perda_maxima and contribuicao < 0`: qualquer
    campanha que já gastou mais do que a tolerância e está 1 centavo negativa recebe
    `parar_por_stop_loss`, embora tenha perdido 1 BRL de uma tolerância de 200. A tolerância do
    owner é de PERDA, não de faturamento.

    V2 deve comparar `max(0, custo − receita)` (observado e conservador) com a tolerância e
    não disparar stop-loss aqui.
    """
    r = avaliar(_caso("1000", "999", "200"))
    assert r.recomendacao is not Recomendacao.PARAR_POR_STOP_LOSS, [m.para_json() for m in r.reasons]
    assert not any(m.codigo == "stop_loss" for m in r.reasons)


def test_red06_controle_perda_liquida_acima_da_tolerancia_dispara_stop_loss():
    """Controle (deve passar na V1 e na V2): gasto 1000, receita 500, tolerância 100.
    Perda observada 500 e conservadora 600 > 100: stop-loss legítimo."""
    r = avaliar(_caso("1000", "500", "100"))
    assert r.recomendacao is Recomendacao.PARAR_POR_STOP_LOSS
