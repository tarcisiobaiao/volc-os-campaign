"""Kernel de fronteira econômica: economia observada, envelope, fronteira e estresse. Sem float."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction

import pytest

from volc_dil.contracts import Dinheiro
from volc_dil.viability.contrato import (
    Cambio, EntradaViabilidade, Evidencia, JanelaObservada, MedidaContagem, MedidaMonetaria, PerdaMaxima, Taxa,
)
from volc_dil.viability.economia import (
    EconomiaObservada, Envelope, Fronteira, Indisponivel, calcular_economia, envelope_conservador, fronteira, estresse,
    receita_liquida_comparavel,
)

from _entradas import AS_OF, entrada  # noqa: E402


# ---------------------------------------------------------------- receita líquida comparável
def test_receita_liquida_converte_com_cambio_e_revshare_em_micros():
    e = entrada(receita="7.77", taxa="5.25", revshare="0.8")
    r = receita_liquida_comparavel(e)
    # 7.77 USD × 5.25 = 40.7925 BRL × 0.8 = 32.634 BRL
    assert r.valor == Dinheiro.de_decimal("32.634", "BRL")
    assert r.moeda_evidencia is Evidencia.ATTESTED  # a atestação não foi promovida
    assert r.cambio_evidencia is Evidencia.ESTIMATED


def test_receita_sem_cambio_quando_moedas_diferem_e_indisponivel():
    e = entrada(taxa=None)
    r = receita_liquida_comparavel(e)
    assert isinstance(r, Indisponivel) and r.motivo == "cambio_ausente"


def test_receita_na_mesma_moeda_nao_exige_cambio():
    e = entrada(receita="40.79", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED)
    r = receita_liquida_comparavel(e)
    assert r.valor == Dinheiro.de_decimal("40.79", "BRL")


def test_receita_ausente_nao_vira_zero():
    e = entrada(receita_none=True)
    r = receita_liquida_comparavel(e)
    assert isinstance(r, Indisponivel) and r.motivo == "receita_absent"


# ---------------------------------------------------------------- economia observada
def test_economia_observada_cpc_rpc_contribuicao_exatos():
    e = entrada()
    eco = calcular_economia(e)
    assert isinstance(eco, EconomiaObservada)
    assert eco.cpc == Fraction(554_750_000, 634)          # micros por clique, exato
    assert eco.rpc == Fraction(40_792_500, 634)           # 7.77 × 5.25 = 40.7925 BRL
    assert eco.contribuicao == Dinheiro(40_792_500 - 554_750_000, "BRL")
    assert eco.break_even_cpc == eco.rpc


def test_economia_sem_cliques_e_indisponivel():
    r = calcular_economia(entrada(cliques=None))
    assert isinstance(r, Indisponivel) and r.motivo == "cliques_absent"
    r0 = calcular_economia(entrada(cliques=0))
    assert isinstance(r0, Indisponivel) and r0.motivo == "cliques_zero"


def test_economia_sem_custo_e_indisponivel():
    r = calcular_economia(entrada(custo_none=True))
    assert isinstance(r, Indisponivel) and r.motivo == "custo_absent"


def test_receita_zero_observada_e_contribuicao_negativa_igual_ao_custo():
    eco = calcular_economia(entrada(receita="0", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED))
    assert eco.rpc == 0 and eco.contribuicao == Dinheiro(-554_750_000, "BRL")


# ---------------------------------------------------------------- envelope conservador
def test_envelope_conservador_reduz_receita_e_aumenta_custo_e_nunca_e_ponto():
    env = envelope_conservador(entrada())
    assert isinstance(env, Envelope)
    assert env.rpc_conservador < env.rpc_central <= env.rpc_otimista
    assert env.cpc_conservador >= env.cpc_central
    assert env.contribuicao_conservadora.micros < env.contribuicao_central.micros
    assert env.premissas  # lista explícita de fatores aplicados


def test_envelope_marca_receita_imatura_sem_promover():
    env = envelope_conservador(entrada(receita_ev=Evidencia.IMMATURE))
    assert env.receita_realizada is False
    assert "receita_imatura" in env.limitacoes


def test_envelope_marca_projecao_como_nao_realizada():
    env = envelope_conservador(entrada(receita_ev=Evidencia.PROJECTED))
    assert env.receita_realizada is False
    assert "receita_projected" in env.limitacoes


# ---------------------------------------------------------------- fronteira
def test_fronteira_distancia_e_multiplicadores():
    fr = fronteira(entrada())
    assert isinstance(fr, Fronteira)
    assert fr.required_rpc == fr.cpc_central
    assert fr.required_rpc_multiplier == fr.cpc_central / fr.rpc_conservador
    assert 0 < fr.queda_cpc_necessaria < 1
    assert fr.distancia_economica > Fraction(9, 10)  # Senac-like: 14× de distância
    assert all(c * Fraction(1) == r for c, r in fr.iso_contribuicao_zero)  # pontos onde cpc == rpc


def test_fronteira_campanha_favoravel_tem_folga():
    fr = fronteira(entrada(receita="800", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED))
    assert fr.queda_cpc_necessaria == 0 and fr.distancia_economica <= 0
    assert fr.folga_cpc > 0


# ---------------------------------------------------------------- estresse
def test_estresse_separa_cambio_revshare_receita_e_maturacao():
    s = estresse(entrada())
    nomes = {c.nome for c in s}
    assert {"base", "receita_x2", "cambio_x1.5", "revshare_0.7", "maturacao_uplift_1.3", "combinado_favoravel"} <= nomes
    base = next(c for c in s if c.nome == "base")
    comb = next(c for c in s if c.nome == "combinado_favoravel")
    assert comb.contribuicao.micros > base.contribuicao.micros
    assert all(c.contribuicao.moeda == "BRL" for c in s)


def test_estresse_nao_salva_senac_like():
    s = estresse(entrada())
    assert all(c.contribuicao.micros < 0 for c in s)


# ---------------------------------------------------------------- invariantes locais
def test_aumentar_cpc_nunca_melhora_contribuicao():
    a = calcular_economia(entrada(custo="554.75"))
    b = calcular_economia(entrada(custo="600.00"))
    assert b.contribuicao.micros < a.contribuicao.micros


def test_aumentar_receita_reconciliada_nunca_piora_contribuicao():
    a = calcular_economia(entrada(receita="7.77"))
    b = calcular_economia(entrada(receita="9.00"))
    assert b.contribuicao.micros > a.contribuicao.micros


# ---------------------------------------------------------------- V2: arredondamento exato Fraction→micros (fix 6)
def test_micros_de_fracao_empata_para_o_par_inclusive_negativo():
    from volc_dil.viability.economia import micros_de_fracao
    assert micros_de_fracao(Fraction(1, 2)) == 0
    assert micros_de_fracao(Fraction(3, 2)) == 2
    assert micros_de_fracao(Fraction(5, 2)) == 2
    assert micros_de_fracao(Fraction(7, 2)) == 4
    assert micros_de_fracao(Fraction(-1, 2)) == 0
    assert micros_de_fracao(Fraction(-3, 2)) == -2
    assert micros_de_fracao(Fraction(-5, 2)) == -2
    assert micros_de_fracao(Fraction(2, 3)) == 1 and micros_de_fracao(Fraction(-2, 3)) == -1
    assert micros_de_fracao(Fraction(1, 3)) == 0 and micros_de_fracao(Fraction(-1, 3)) == 0
    assert micros_de_fracao(Fraction(7)) == 7


def test_micros_de_fracao_nao_perde_precisao_em_numeradores_grandes():
    from volc_dil.viability.economia import micros_de_fracao
    n = 10 ** 40
    assert micros_de_fracao(Fraction(n, 3)) == n // 3            # 333...3 (resto 1/3 arredonda para baixo)
    assert micros_de_fracao(Fraction(2 * n, 3)) == (2 * n) // 3 + 1  # resto 2/3 arredonda para cima
    assert micros_de_fracao(Fraction(n + 1, 2)) == n // 2        # empate em (10^40+1)/2: 10^40/2 é par
    # o caminho antigo (Decimal com 28 dígitos) falharia aqui: o resultado precisa ser exato
    assert micros_de_fracao(Fraction(10 ** 40 + 7, 1)) == 10 ** 40 + 7


def test_micros_x_usa_aritmetica_inteira_e_aceita_decimal():
    from volc_dil.viability.economia import _micros_x
    assert _micros_x(5, Fraction(1, 2)) == 2          # 2,5 → 2 (par)
    assert _micros_x(7, Fraction(1, 2)) == 4          # 3,5 → 4 (par)
    assert _micros_x(10 ** 40, Decimal("0.3")) == 3 * 10 ** 39


# ---------------------------------------------------------------- V2: entradas negativas (fix 4)
def _negativo_bypass(e, campo, micros):
    """Contrato V2 recusa valor negativo na construção; este helper contorna o contrato (object.__setattr__)
    só para provar que o KERNEL também recusa, defensivamente."""
    import copy
    m = copy.copy(getattr(e, campo))
    object.__setattr__(m, "valor", Dinheiro(micros, m.valor.moeda))
    e2 = copy.copy(e)
    object.__setattr__(e2, campo, m)
    return e2


def test_custo_negativo_e_recusado_pelo_contrato_e_pelo_kernel():
    import pytest
    from volc_dil.viability.contrato import ContratoViabilidadeViolado
    base = entrada(receita="800", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED)
    with pytest.raises(ContratoViabilidadeViolado):
        base.__class__(**{**base.__dict__, "custo": base.custo.__class__(**{**base.custo.__dict__, "valor": Dinheiro(-1, "BRL")})})
    r = calcular_economia(_negativo_bypass(base, "custo", -1))
    assert isinstance(r, Indisponivel) and r.motivo == "valor_negativo" and "custo" in r.detalhe


def test_receita_negativa_e_recusada_pelo_contrato_e_pelo_kernel():
    import pytest
    from volc_dil.viability.contrato import ContratoViabilidadeViolado
    base = entrada(receita="800", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED)
    with pytest.raises(ContratoViabilidadeViolado):
        base.__class__(**{**base.__dict__, "receita": base.receita.__class__(**{**base.receita.__dict__, "valor": Dinheiro(-5, "BRL")})})
    e = _negativo_bypass(base, "receita", -5)
    r = calcular_economia(e)
    assert isinstance(r, Indisponivel) and r.motivo == "valor_negativo" and "receita" in r.detalhe
    assert isinstance(receita_liquida_comparavel(e), Indisponivel)


def test_contribuicao_pode_ser_negativa_embora_entradas_nao_possam():
    eco = calcular_economia(entrada(receita="0", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED))
    assert isinstance(eco, EconomiaObservada) and eco.contribuicao.micros < 0
    assert eco.custo.micros >= 0 and eco.receita_liquida.micros >= 0 and eco.cliques >= 0


# ---------------------------------------------------------------- V2: grão por clique; visitas só reportadas (fixes 1 e 5)
def test_break_even_e_por_clique_e_rpc_por_visita_e_so_reportado():
    # 100 cliques, 50 visitas, custo 100, receita 75 BRL observada
    eco = calcular_economia(entrada(cliques=100, custo="100", receita="75", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, visitas=50))
    assert isinstance(eco, EconomiaObservada)
    assert eco.cpc == Fraction(1_000_000)
    assert eco.rpc_por_clique == Fraction(750_000) and eco.rpc == eco.rpc_por_clique and eco.break_even_cpc == Fraction(750_000)
    assert eco.rpc_por_visita == Fraction(1_500_000)
    assert eco.visitas_elegiveis == 50
    assert eco.contribuicao == Dinheiro(-25_000_000, "BRL")   # nunca "prejuízo zero" por trocar o grão


def test_visitas_ausentes_nao_calcula_rpc_por_visita():
    eco = calcular_economia(entrada(cliques=100, custo="100", receita="75", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED))
    assert eco.rpc_por_visita is None and eco.visitas_elegiveis is None
    assert eco.rpc_por_visita_indisponivel == "visitas_ausente"
    assert eco.rpc_por_clique == Fraction(750_000)


def test_visitas_zero_e_valor_valido_e_nunca_cai_para_cliques():
    eco = calcular_economia(entrada(cliques=100, custo="100", receita="75", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, visitas=0))
    assert isinstance(eco, EconomiaObservada)
    assert eco.visitas_elegiveis == 0
    assert eco.rpc_por_visita is None and eco.rpc_por_visita_indisponivel == "visitas_zero"
    assert eco.rpc_por_clique == Fraction(750_000) and eco.break_even_cpc == Fraction(750_000)
    assert eco.contribuicao == Dinheiro(-25_000_000, "BRL")


def test_estresse_usa_o_grao_por_clique():
    s = estresse(entrada(cliques=100, custo="100", receita="75", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, visitas=50))
    base = next(c for c in s if c.nome == "base")
    assert base.rpc == Fraction(750_000) and base.contribuicao == Dinheiro(-25_000_000, "BRL")
