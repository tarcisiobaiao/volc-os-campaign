"""RED — vocabulário de vereditos V2 e alcance de `viable_candidate`.

A V1 chama de "structurally_unviable" uma conclusão que depende de premissas declaradas
(receita ×2, câmbio ×1,5, maturação ×1,3) — não de estrutura. A V2 renomeia para
`unviable_under_declared_scenarios`. E `VIABLE_CANDIDATE` existe no enum da V1 mas nenhum
ramo do gate o produz: favorável + provado + < 500 cliques vira `already_profitable`.
"""
from __future__ import annotations

from volc_dil.viability.contrato import Evidencia
from volc_dil.viability.gate import Veredito, avaliar

from _entradas import entrada


def test_red13a_vocabulario_de_vereditos_v2():
    """Vocabulário V2: insufficient_evidence | unviable_under_declared_scenarios | test_with_cap |
    viable_candidate | already_profitable. `structurally_unviable` deixa de existir."""
    valores = {v.value for v in Veredito}
    assert "unviable_under_declared_scenarios" in valores, valores
    assert "structurally_unviable" not in valores, valores
    assert valores == {"insufficient_evidence", "unviable_under_declared_scenarios", "test_with_cap", "viable_candidate", "already_profitable"}


def test_red13b_viable_candidate_e_alcancavel_com_menos_de_500_cliques():
    """Economia favorável (300 cliques, custo 300 BRL, receita 600 BRL observada, moeda provada,
    16 dias maduros, cobertura completa, tolerância informada) mas abaixo de 500 cliques.

    V1 está errada porque o ramo 3 do gate (`contribuicao_conservadora >= 0 and realizada and
    moeda_provada and not poucos`) usa `poucos = cliques < 200`: com 300 cliques o kernel já
    declara `already_profitable`, e `viable_candidate` é um valor do enum que nenhum caminho
    produz — a classe intermediária "candidata, ainda não comprovada" não existe na prática.

    V2 deve devolver `viable_candidate` aqui e reservar `already_profitable` para >= 500 cliques.
    """
    e = entrada(cliques=300, custo="300", receita="600", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED,
                receita_ev=Evidencia.OBSERVED, perda="300", horizonte=14)
    r = avaliar(e)
    assert r.verdict.value == "viable_candidate", f"V1 devolve {r.verdict.value} com 300 cliques"


def test_red13c_controle_already_profitable_continua_alcancavel_com_634_cliques():
    """Controle (passa na V1 e na V2): a mesma economia com 634 cliques continua `already_profitable`."""
    e = entrada(receita="800", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED, perda="300", horizonte=14)
    assert avaliar(e).verdict is Veredito.ALREADY_PROFITABLE
