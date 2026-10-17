"""Gate pré-campanha: avaliação tipada, sem mutação. Vereditos, confiança, recomendação, razões."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from fractions import Fraction

from volc_dil.contracts import Dinheiro
from volc_dil.viability.contrato import Evidencia, PontoSimulacao, SimulacaoEntrada
from volc_dil.viability.gate import Confianca, Recomendacao, ResultadoViabilidade, Veredito, avaliar

from _entradas import AS_OF, entrada, v2


def _com(e, **kw):
    return e.__class__(**{**e.__dict__, **kw})


def test_senac_like_e_estruturalmente_inviavel_mesmo_sob_estresse():
    r = avaliar(entrada(perda="300", horizonte=14))
    assert isinstance(r, ResultadoViabilidade)
    assert r.verdict is Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS
    assert r.recomendacao is Recomendacao.REJEITAR_TESE_ECONOMICA
    assert r.confidence_class in (Confianca.MEDIUM, Confianca.HIGH)
    assert r.required_rpc_multiplier is not None and r.required_rpc_multiplier > 10
    assert any(m.codigo == "inviavel_sob_estresse" for m in r.reasons)
    assert r.max_experiment_spend is None  # não propõe teste para tese rejeitada


def test_campanha_favoravel_com_moeda_observada_e_viavel():
    e = entrada(receita="800", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14)
    r = avaliar(e)
    assert r.verdict is Veredito.ALREADY_PROFITABLE
    assert r.recomendacao is Recomendacao.CONTINUAR_CAMPANHA_EXISTENTE
    assert r.contribution_observed.micros > 0


def test_campanha_favoravel_com_moeda_so_atestada_nao_vira_viable_candidate():
    e = entrada(receita="200", moeda_receita="USD", taxa="5.25", cambio_ev=Evidencia.ESTIMATED, moeda_rec_ev=Evidencia.ATTESTED, perda="300", horizonte=14)
    r = avaliar(e)
    assert r.verdict is Veredito.TEST_WITH_CAP
    assert r.verdict not in (Veredito.VIABLE_CANDIDATE, Veredito.ALREADY_PROFITABLE)
    assert any(m.codigo in ("moeda_receita_attested", "cambio_estimated") for m in r.reasons)
    assert r.max_experiment_spend is not None


def test_proximo_do_equilibrio_vira_teste_com_teto():
    # rpc ≈ cpc: 634 cliques, custo 554.75, receita 600 BRL observada
    e = entrada(receita="600", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14)
    r = avaliar(e)
    assert r.verdict in (Veredito.TEST_WITH_CAP, Veredito.VIABLE_CANDIDATE)
    assert r.max_experiment_spend is not None and r.stop_loss is not None


def test_moeda_desconhecida_e_insufficient():
    e = entrada(moeda_rec_ev=Evidencia.UNKNOWN, taxa=None)
    r = avaliar(e)
    assert r.verdict is Veredito.INSUFFICIENT_EVIDENCE
    assert "cambio_ausente" in r.missing_evidence or "receita_moeda_unknown" in r.missing_evidence
    assert r.recomendacao is Recomendacao.COLETAR_EVIDENCIA


def test_cambio_ausente_e_insufficient():
    r = avaliar(entrada(taxa=None))
    assert r.verdict is Veredito.INSUFFICIENT_EVIDENCE and "cambio_ausente" in r.missing_evidence


def test_custo_ausente_e_insufficient():
    r = avaliar(entrada(custo_none=True))
    assert r.verdict is Veredito.INSUFFICIENT_EVIDENCE and "custo_absent" in r.missing_evidence


def test_receita_ausente_e_insufficient_nunca_zero():
    r = avaliar(entrada(receita_none=True))
    assert r.verdict is Veredito.INSUFFICIENT_EVIDENCE and "receita_absent" in r.missing_evidence
    assert r.contribution_observed is None


def test_receita_zero_observada_e_inviavel_nao_insuficiente():
    r = avaliar(entrada(receita="0", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED))
    assert r.verdict is Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS


def test_receita_imatura_pede_maturacao_e_nao_decide():
    r = avaliar(entrada(receita_ev=Evidencia.IMMATURE, dias_maduros=0))
    assert r.verdict is Veredito.INSUFFICIENT_EVIDENCE
    assert r.recomendacao is Recomendacao.AGUARDAR_MATURACAO
    assert r.maturity_wait is not None and r.maturity_wait >= 3


def test_receita_projetada_nao_e_realizada():
    e = entrada(receita="800", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.PROJECTED, perda="300", horizonte=14)
    r = avaliar(e)
    assert r.verdict not in (Veredito.ALREADY_PROFITABLE, Veredito.VIABLE_CANDIDATE)
    assert "receita_projected" in r.invalid_evidence or any(m.codigo == "receita_projected" for m in r.reasons)


def test_limite_financeiro_ausente_impede_teto_mas_nao_o_diagnostico():
    r = avaliar(entrada(perda=None, horizonte=None))
    assert r.verdict is Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS   # Senac-like continua inviável
    assert r.max_experiment_spend is None and "perda_maxima_ausente" in r.missing_evidence
    e = entrada(receita="600", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda=None, horizonte=None)
    r2 = avaliar(e)
    assert r2.verdict is Veredito.INSUFFICIENT_EVIDENCE and "perda_maxima_ausente" in r2.missing_evidence


def test_campanha_nova_sem_historico_so_com_pesquisa_e_tolerancia_prepara_pausada():
    e = entrada(receita_none=True, custo_none=True, cliques=None, perda="300", horizonte=14)
    e = _com(e, cpc_intervalo=(Dinheiro.de_decimal("0.30", "BRL"), Dinheiro.de_decimal("0.60", "BRL")),
             rpc_intervalo=(Dinheiro.de_decimal("0.70", "BRL"), Dinheiro.de_decimal("1.10", "BRL")))
    r = avaliar(e)
    assert r.verdict is Veredito.TEST_WITH_CAP
    assert r.recomendacao is Recomendacao.PREPARAR_CAMPANHA_PAUSADA
    assert r.confidence_class is Confianca.LOW
    assert r.max_experiment_spend == Dinheiro.de_decimal("300", "BRL")


def test_stop_loss_dispara_quando_gasto_madura_acima_do_teto_com_contribuicao_negativa():
    e = entrada(receita="300", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="100", horizonte=14)
    r = avaliar(e)
    # custo 554.75 já supera a tolerância de 100 e a contribuição madura é negativa
    assert r.recomendacao is Recomendacao.PARAR_POR_STOP_LOSS


def test_simulacao_entra_na_saida_e_marginal_destrutivo_aparece_nas_razoes():
    pontos = (PontoSimulacao(50_000, 500, 20_000_000), PontoSimulacao(100_000, 1000, 80_000_000), PontoSimulacao(200_000, 1300, 160_000_000))
    sim = SimulacaoEntrada("CPC_BID", "BRL", pontos, AS_OF, "MANUAL_CPC")
    # economia favorável (rpc≈0,16) mas último segmento destrutivo (0,40 marginal)
    e = entrada(cliques=1000, custo="80.00", receita="160.00", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14)
    r = avaliar(_com(e, simulacao=sim))
    assert r.simulacao is not None and r.simulacao["disponivel"] is True
    assert any(m.codigo == "expansao_marginal_destrutiva" for m in r.reasons)


def test_saida_tem_hashes_trace_proibicoes_e_proximas_leituras():
    r = avaliar(entrada(perda="300", horizonte=14))
    assert len(r.input_hash) == 64 and r.trace and r.prohibited_actions and r.next_read_only_actions
    assert all("mutate" not in a.lower() for a in r.next_read_only_actions)
    assert r.para_json()["verdict"] == "unviable_under_declared_scenarios"


def test_mesma_entrada_mesmo_resultado_e_hash():
    a, b = avaliar(entrada(perda="300", horizonte=14)), avaliar(entrada(perda="300", horizonte=14))
    assert a.para_json() == b.para_json() and a.result_hash == b.result_hash


def test_veredito_muda_quando_a_mesma_fixture_recebe_economia_favoravel():
    base = avaliar(entrada(perda="300", horizonte=14))
    fav = avaliar(entrada(receita="900", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14))
    assert base.verdict is Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS and fav.verdict is Veredito.ALREADY_PROFITABLE


def test_evidencia_mais_fraca_nunca_e_mais_permissiva():
    forte = avaliar(entrada(receita="800", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14))
    fraca = avaliar(entrada(receita="800", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.ATTESTED, perda="300", horizonte=14))
    assert Veredito.ordem(fraca.verdict) <= Veredito.ordem(forte.verdict)
    assert fraca.confidence_class.ordem() <= forte.confidence_class.ordem()


# ---------------------------------------------------------------- V2: grão por clique na saída (fix 1)
def test_saida_expoe_rpc_por_clique_e_rpc_por_visita_separados():
    r = avaliar(entrada(cliques=100, custo="100", receita="75", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, visitas=50, perda="300", horizonte=14))
    assert r.observed_cpc == Fraction(1_000_000)
    assert r.observed_rpc == Fraction(750_000)            # por clique: é o grão do break-even
    assert r.break_even_cpc == Fraction(750_000)
    assert r.observed_rpc_per_visit == Fraction(1_500_000)
    assert r.contribution_observed == Dinheiro(-25_000_000, "BRL")
    j = r.para_json()
    assert j["observed_rpc_micros"] == "750000" and j["observed_rpc_per_visit_micros"] == "1500000"


def test_saida_com_visitas_zero_nao_usa_cliques_como_visitas():
    r = avaliar(entrada(cliques=100, custo="100", receita="75", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, visitas=0, perda="300", horizonte=14))
    assert r.observed_rpc == Fraction(750_000) and r.observed_rpc_per_visit is None
    assert r.para_json()["observed_rpc_per_visit_unavailable"] == "visitas_zero"


# ---------------------------------------------------------------- V2: stop-loss compara perda LÍQUIDA, nunca gasto bruto (fix 2)
def test_stop_loss_nao_dispara_quando_a_perda_liquida_cabe_na_tolerancia():
    # gasto 1000 > tolerância 100, mas receita 950 observada na mesma moeda: perda líquida 50 <= 100
    e = entrada(custo="1000", receita="950", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED, perda="100", horizonte=14)
    r = avaliar(e)
    assert r.recomendacao is not Recomendacao.PARAR_POR_STOP_LOSS
    assert not any(m.codigo == "stop_loss" for m in r.reasons)
    assert r.max_loss == Dinheiro.de_decimal("100", "BRL")
    assert r.net_loss_observed == Dinheiro.de_decimal("50", "BRL")
    assert r.contribution_observed == Dinheiro.de_decimal("-50", "BRL")
    assert r.spend_cap is not None and r.spend_cap == r.max_experiment_spend
    j = r.para_json()
    assert {"max_loss", "spend_cap", "net_loss_observed", "net_loss_conservative", "contribution_observed", "contribution_conservative"} <= set(j)
    assert j["max_loss"] != j["spend_cap"]


def test_stop_loss_dispara_quando_a_perda_liquida_observada_excede_a_tolerancia():
    e = entrada(custo="1000", receita="850", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED, perda="100", horizonte=14)
    r = avaliar(e)
    assert r.recomendacao is Recomendacao.PARAR_POR_STOP_LOSS
    assert r.net_loss_observed == Dinheiro.de_decimal("150", "BRL")
    motivo = next(m for m in r.reasons if m.codigo == "stop_loss")
    assert "líquida" in motivo.detalhe and "1000" not in motivo.detalhe.split("perda")[0]


def test_stop_loss_nunca_usa_gasto_bruto_mesmo_com_contribuicao_negativa_minima():
    e = entrada(custo="1000", receita="999", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED, perda="100", horizonte=14)
    r = avaliar(e)
    assert r.contribution_observed.micros < 0
    assert r.recomendacao is not Recomendacao.PARAR_POR_STOP_LOSS


def test_perda_liquida_conservadora_acima_da_tolerancia_e_aviso_nao_stop_loss():
    e = entrada(custo="1000", receita="950", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED, perda="100", horizonte=14)
    r = avaliar(e)
    assert r.net_loss_conservative.micros > r.max_loss.micros       # 1050 − 855 = 195 > 100
    assert any(m.codigo == "perda_conservadora_acima_da_tolerancia" and m.severidade == "aviso" for m in r.reasons)
    assert r.recomendacao is not Recomendacao.PARAR_POR_STOP_LOSS


# ---------------------------------------------------------------- V2: moeda da simulação (fix 3)
def test_simulacao_em_moeda_diferente_sem_cambio_e_indisponivel_no_gate():
    pontos = (PontoSimulacao(50_000, 500, 20_000_000), PontoSimulacao(100_000, 1000, 80_000_000))
    sim = SimulacaoEntrada("CPC_BID", "USD", pontos, AS_OF, "MANUAL_CPC")
    e = entrada(cliques=1000, custo="80.00", receita="160.00", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14)
    r = avaliar(_com(e, simulacao=sim))
    assert r.simulacao["disponivel"] is False and r.simulacao["motivo"] == "moeda_incompativel"
    assert "simulacao_moeda_incompativel" in r.missing_evidence


# ---------------------------------------------------------------- V2: veredito renomeado (fix 7)
def test_veredito_inviavel_e_sob_os_cenarios_declarados():
    assert Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS.value == "unviable_under_declared_scenarios"
    assert "structurally_unviable" not in {v.value for v in Veredito}
    r = avaliar(entrada(perda="300", horizonte=14))
    assert r.verdict is Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS
    assert r.recomendacao is Recomendacao.REJEITAR_TESE_ECONOMICA
    assert any(m.codigo == "inviavel_sob_estresse" and "sob os cenários declarados" in m.detalhe for m in r.reasons)
    assert Veredito.ordem(Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS) == 0


# ---------------------------------------------------------------- V2: VIABLE_CANDIDATE alcançável (fix 8)
FAV = dict(receita="800", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14)


def test_already_profitable_exige_500_cliques_e_7_dias_e_cobertura_completa():
    r = avaliar(entrada(cliques=634, dias_maduros=16, **FAV))
    assert r.verdict is Veredito.ALREADY_PROFITABLE and r.confidence_class is Confianca.HIGH


def test_favoravel_com_poucos_cliques_para_alta_confianca_e_viable_candidate():
    r = avaliar(entrada(cliques=300, custo="200", dias_maduros=16, **FAV))   # 200 <= 300 < 500
    assert r.verdict is Veredito.VIABLE_CANDIDATE
    assert r.confidence_class.ordem() <= Confianca.MEDIUM.ordem()
    assert r.recomendacao is Recomendacao.PROPOR_TESTE_LIMITADO
    assert r.max_experiment_spend is not None


def test_favoravel_com_poucos_dias_maduros_e_viable_candidate():
    r = avaliar(entrada(cliques=634, dias_maduros=5, **FAV))   # 3 <= 5 < 7
    assert r.verdict is Veredito.VIABLE_CANDIDATE
    assert r.verdict is not Veredito.ALREADY_PROFITABLE


def test_viable_candidate_exige_moeda_provada_e_receita_realizada():
    assert avaliar(entrada(cliques=300, custo="200", moeda_rec_ev=Evidencia.ATTESTED, **{k: v for k, v in FAV.items() if k != "moeda_rec_ev"})).verdict is Veredito.TEST_WITH_CAP
    assert avaliar(entrada(cliques=300, custo="200", receita_ev=Evidencia.ATTESTED, **FAV)).verdict is Veredito.TEST_WITH_CAP


def test_cobertura_de_receita_desconhecida_nao_vira_viable_nem_already():
    r = avaliar(entrada(cliques=634, dias_maduros=16, cobertura_ppm=None, **FAV))
    assert r.verdict is Veredito.TEST_WITH_CAP
    assert any(m.codigo == "cobertura_receita_incompleta" for m in r.reasons)
    r2 = avaliar(entrada(cliques=300, custo="200", cobertura_ppm=None, **FAV))
    assert r2.verdict is Veredito.TEST_WITH_CAP


# ---------------------------------------------------------------- V2: governança de evidência (fix 9)
def test_custo_projetado_com_numeros_favoraveis_nao_e_already_profitable():
    r = avaliar(entrada(custo_ev=Evidencia.PROJECTED, **FAV))
    assert r.verdict not in (Veredito.ALREADY_PROFITABLE, Veredito.VIABLE_CANDIDATE)
    assert r.confidence_class.ordem() <= Confianca.MEDIUM.ordem()
    assert any(m.codigo == "custo_projected" for m in r.reasons)


def test_cliques_estimados_com_numeros_favoraveis_nao_e_positivo():
    r = avaliar(entrada(cliques_ev=Evidencia.ESTIMATED, **FAV))
    assert r.verdict not in (Veredito.ALREADY_PROFITABLE, Veredito.VIABLE_CANDIDATE)
    assert r.confidence_class is not Confianca.HIGH


def test_receita_com_flag_invalid_nao_e_positiva():
    r = avaliar(entrada(flags_medidas={"receita": ("invalid_schema",)}, **FAV))
    assert r.verdict not in (Veredito.ALREADY_PROFITABLE, Veredito.VIABLE_CANDIDATE)
    assert r.confidence_class is not Confianca.HIGH
    assert "receita:invalid_schema" in r.invalid_evidence


def test_medida_mais_velha_que_o_sla_e_stale_e_nao_e_positiva():
    velha = AS_OF - timedelta(days=8)
    r = avaliar(entrada(observado_em={"receita": velha}, **FAV))
    assert r.verdict not in (Veredito.ALREADY_PROFITABLE, Veredito.VIABLE_CANDIDATE)
    assert any(m.codigo == "stale" and "receita" in m.detalhe for m in r.reasons)
    assert r.confidence_class is not Confianca.HIGH
    fresca = avaliar(entrada(observado_em={"receita": AS_OF - timedelta(days=6)}, **FAV))
    assert fresca.verdict is Veredito.ALREADY_PROFITABLE
    sla_curto = avaliar(entrada(observado_em={"receita": AS_OF - timedelta(days=6)}, sla_dias=5, **FAV))
    assert sla_curto.verdict is not Veredito.ALREADY_PROFITABLE


def test_cobertura_parcial_com_totais_favoraveis_e_no_maximo_test_with_cap():
    r = avaliar(entrada(cobertura_ppm=750_000, dias_custo_sem_receita=3, **FAV))
    assert Veredito.ordem(r.verdict) <= Veredito.ordem(Veredito.TEST_WITH_CAP)
    assert any(m.codigo == "cobertura_receita_incompleta" for m in r.reasons)
    assert any(m.codigo == "dias_custo_sem_receita=3" for m in r.reasons)
    assert r.confidence_class is not Confianca.HIGH


def test_governanca_evidencia_de_custo_mais_fraca_nunca_e_mais_permissiva():
    forte = avaliar(entrada(**FAV))
    for ev in (Evidencia.ATTESTED, Evidencia.ESTIMATED, Evidencia.PROJECTED, Evidencia.IMMATURE):
        fraca = avaliar(entrada(custo_ev=ev, **FAV))
        assert Veredito.ordem(fraca.verdict) <= Veredito.ordem(forte.verdict)
        assert fraca.confidence_class.ordem() <= forte.confidence_class.ordem()


# ---------------------------------------------------------------- R1 (red team V2): moeda do CUSTO também precisa ser provada
def test_r1_moeda_do_custo_atestada_nunca_e_veredito_positivo_nem_high():
    from volc_dil.viability.invariantes import verificar_invariantes
    e = entrada(receita="800", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14)
    e = _com(e, custo=_com(e.custo, moeda_evidencia=Evidencia.ATTESTED))
    r = avaliar(e)
    assert r.verdict not in (Veredito.ALREADY_PROFITABLE, Veredito.VIABLE_CANDIDATE)
    assert r.confidence_class is not Confianca.HIGH
    assert any(m.codigo == "moeda_custo_attested" for m in r.reasons)
    verificar_invariantes(e, r)  # o gate e o verificador concordam
