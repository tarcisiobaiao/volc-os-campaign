"""Kernel de custo marginal sobre pontos de campaign_simulation (offline, sem API)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction

from volc_dil.viability.contrato import PontoSimulacao, SimulacaoEntrada
from volc_dil.viability.simulacao import CurvaIndisponivel, FronteiraMarginal, analisar_simulacao

AS_OF = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def sim(pontos, tipo="CPC_BID", estrategia="MANUAL_CPC", moeda="BRL"):
    return SimulacaoEntrada(tipo=tipo, moeda=moeda, pontos=tuple(PontoSimulacao(*p) for p in pontos), disponivel_em=AS_OF, estrategia_lance=estrategia)


# exemplo do ADR: lance 0,10 → 1000 cliques @ 80; lance 0,15 → 1200 cliques @ 120 (200 cliques extras a 0,20)
ADR = [(100_000, 1000, 80_000_000), (150_000, 1200, 120_000_000)]
RPC = Fraction(140_000)  # 0,14 por clique


def test_cpc_marginal_difere_do_cpc_medio_exemplo_do_adr():
    fm = analisar_simulacao(sim(ADR), RPC)
    assert isinstance(fm, FronteiraMarginal)
    seg = fm.segmentos[0]
    assert seg.cliques_incrementais == 200 and seg.custo_incremental_micros == 40_000_000
    assert seg.cpc_marginal == Fraction(200_000)            # 0,20 marginal
    assert fm.pontos[1].cpc_medio == Fraction(100_000)       # 0,10 médio no mesmo ponto
    assert seg.contribuicao_marginal_micros == 200 * 140_000 - 40_000_000  # −12,00


def test_identifica_ultimo_ponto_sustentavel_e_primeiro_destrutivo():
    pontos = [(50_000, 500, 20_000_000), (100_000, 1000, 80_000_000), (150_000, 1200, 120_000_000), (200_000, 1300, 160_000_000)]
    fm = analisar_simulacao(sim(pontos), RPC)
    # seg0: 500 cliques por 60 → 0,12 ≤ 0,14 ok; seg1: 200 por 40 → 0,20 destrutivo; seg2: 100 por 40 → 0,40
    assert fm.ultimo_ponto_sustentavel.modificacao_micros == 100_000
    assert fm.primeiro_ponto_destrutivo.modificacao_micros == 150_000
    assert fm.expansao_aceitavel_ate_modificacao == 100_000
    assert [s.sustentavel for s in fm.segmentos] == [True, False, False]


def test_ultimos_20pct_dos_cliques_destroem_contribuicao_mesmo_com_roas_medio_bom():
    # ROAS médio no último ponto: receita 1300×0,14=182 vs custo 160 → 1,14 (parece bom); marginal destrói
    pontos = [(50_000, 500, 20_000_000), (100_000, 1000, 80_000_000), (200_000, 1300, 160_000_000)]
    fm = analisar_simulacao(sim(pontos), RPC)
    ultimo = fm.pontos[-1]
    assert ultimo.contribuicao_media_micros > 0            # média engana
    assert fm.segmentos[-1].contribuicao_marginal_micros < 0  # marginal destrói
    assert fm.primeiro_ponto_destrutivo.modificacao_micros == 200_000


def test_curva_insuficiente_com_menos_de_dois_pontos():
    r = analisar_simulacao(sim([(100_000, 1000, 80_000_000)]), RPC)
    assert isinstance(r, CurvaIndisponivel) and r.motivo == "curva_insuficiente"


def test_simulacao_inexistente_e_diagnostico_nao_erro():
    r = analisar_simulacao(None, RPC)
    assert isinstance(r, CurvaIndisponivel) and r.motivo == "simulacao_ausente"


def test_tipo_nao_interpretavel_e_indisponivel_com_motivo():
    r = analisar_simulacao(sim(ADR, tipo="TARGET_ROAS", estrategia="TARGET_ROAS"), RPC)
    assert isinstance(r, CurvaIndisponivel) and r.motivo == "tipo_nao_suportado"


def test_pontos_duplicados_sao_recusados():
    r = analisar_simulacao(sim([(100_000, 1000, 80_000_000), (100_000, 1000, 80_000_000), (150_000, 1200, 120_000_000)]), RPC)
    assert isinstance(r, CurvaIndisponivel) and r.motivo == "pontos_duplicados"


def test_curva_nao_monotonica_e_recusada_por_padrao():
    r = analisar_simulacao(sim([(100_000, 1000, 80_000_000), (150_000, 900, 120_000_000)]), RPC)
    assert isinstance(r, CurvaIndisponivel) and r.motivo == "curva_nao_monotonica"


def test_curva_nao_monotonica_normalizada_so_com_recibo_explicito():
    pontos = [(50_000, 500, 20_000_000), (100_000, 1000, 80_000_000), (150_000, 900, 120_000_000), (200_000, 1300, 160_000_000)]
    fm = analisar_simulacao(sim(pontos), RPC, normalizar_nao_monotonica=True)
    assert isinstance(fm, FronteiraMarginal)
    assert fm.normalizacao is not None and fm.normalizacao.pontos_removidos == (150_000,)


def test_campos_ausentes_sao_recusados():
    r = analisar_simulacao(sim([(100_000, None, 80_000_000), (150_000, 1200, 120_000_000)]), RPC)
    assert isinstance(r, CurvaIndisponivel) and r.motivo == "campos_ausentes"


def test_ordem_e_normalizada_e_nao_interpola_fora_da_faixa():
    fm = analisar_simulacao(sim(list(reversed(ADR))), RPC)
    assert [p.modificacao_micros for p in fm.pontos] == [100_000, 150_000]
    assert fm.faixa_observada == (100_000, 150_000)
    assert fm.extrapolacao_permitida is False


def test_conversoes_incrementais_quando_presentes():
    pontos = [PontoSimulacao(100_000, 1000, 80_000_000, None, Decimal("10")), PontoSimulacao(150_000, 1200, 120_000_000, None, Decimal("11.5"))]
    s = SimulacaoEntrada("CPC_BID", "BRL", tuple(pontos), AS_OF, "MANUAL_CPC")
    fm = analisar_simulacao(s, RPC)
    assert str(fm.segmentos[0].conversoes_incrementais) == "1.5"


def test_budget_simulation_e_interpretada_como_curva_de_orcamento():
    fm = analisar_simulacao(sim(ADR, tipo="BUDGET", estrategia="TARGET_SPEND"), RPC)
    assert isinstance(fm, FronteiraMarginal) and fm.tipo == "BUDGET"


def test_fronteira_eficiente_e_auditavel_e_deterministica():
    a = analisar_simulacao(sim(ADR), RPC)
    b = analisar_simulacao(sim(ADR), RPC)
    assert a.para_json() == b.para_json()
    assert "segmentos" in a.para_json() and "rpc_conservador_micros" in a.para_json()
