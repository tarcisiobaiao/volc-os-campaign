"""Invariantes do kernel (as 15 obrigatórias) + testes mutacionais/adversariais.

Os mutantes são injetados por monkeypatch e DEVEM ser detectados pelo verificador de invariantes
ou pelos testes de comportamento; se um mutante passar despercebido, o teste falha.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction

import pytest

from volc_dil.contracts import Dinheiro
from volc_dil.viability import contrato as C
from volc_dil.viability import economia as E
from volc_dil.viability import gate as G
from volc_dil.viability.contrato import Evidencia, PontoSimulacao, SimulacaoEntrada
from volc_dil.viability.gate import Confianca, Veredito, avaliar
from volc_dil.viability.invariantes import InvarianteViolada, verificar_invariantes
from volc_dil.viability.simulacao import analisar_simulacao

from _entradas import AS_OF, entrada


def _com(e, **kw):
    return e.__class__(**{**e.__dict__, **kw})


# ------------------------------------------------------------------ 1 e 2: monotonia de CPC e receita
def test_inv1_aumento_de_cpc_nunca_melhora_contribuicao_em_grade():
    rnd = random.Random(7)
    for _ in range(40):
        custo = Decimal(rnd.randint(100, 2000))
        r1 = avaliar(entrada(custo=str(custo), receita="400", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14))
        r2 = avaliar(entrada(custo=str(custo + 50), receita="400", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14))
        assert r2.contribution_observed.micros <= r1.contribution_observed.micros
        assert r2.contribution_conservative.micros <= r1.contribution_conservative.micros
        assert Veredito.ordem(r2.verdict) <= Veredito.ordem(r1.verdict)


def test_inv2_aumento_de_receita_reconciliada_nunca_piora():
    rnd = random.Random(11)
    for _ in range(40):
        rec = Decimal(rnd.randint(10, 1500))
        r1 = avaliar(entrada(receita=str(rec), moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14))
        r2 = avaliar(entrada(receita=str(rec + 40), moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14))
        assert r2.contribution_observed.micros >= r1.contribution_observed.micros
        assert Veredito.ordem(r2.verdict) >= Veredito.ordem(r1.verdict)


# ------------------------------------------------------------------ 3: evidência mais fraca nunca mais permissiva
@pytest.mark.parametrize("fraca", [Evidencia.ATTESTED, Evidencia.UNKNOWN])
def test_inv3_moeda_mais_fraca_nunca_mais_permissiva(fraca):
    for rec in ("50", "600", "900"):
        forte = avaliar(entrada(receita=rec, moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14))
        fr = avaliar(entrada(receita=rec, moeda_receita="BRL", taxa=None, moeda_rec_ev=fraca, perda="300", horizonte=14))
        assert Veredito.ordem(fr.verdict) <= Veredito.ordem(forte.verdict)
        assert fr.confidence_class.ordem() <= forte.confidence_class.ordem()


def test_inv3_receita_projetada_nunca_mais_permissiva_que_reconciliada():
    forte = avaliar(entrada(receita="900", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14))
    fr = avaliar(entrada(receita="900", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.PROJECTED, perda="300", horizonte=14))
    assert Veredito.ordem(fr.verdict) < Veredito.ordem(forte.verdict)


# ------------------------------------------------------------------ 4: moeda inválida / conversão não comprovada
def test_inv4_moeda_invalida_nao_vira_viable():
    r = avaliar(entrada(receita="900", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.INVALID, perda="300", horizonte=14))
    assert r.verdict is Veredito.INSUFFICIENT_EVIDENCE and "moeda_receita_invalid" in r.invalid_evidence


def test_inv4_cambio_estimado_nao_vira_viable_nem_already():
    r = avaliar(entrada(receita="300", moeda_receita="USD", taxa="5.25", cambio_ev=Evidencia.ESTIMATED, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14))
    assert r.verdict not in (Veredito.VIABLE_CANDIDATE, Veredito.ALREADY_PROFITABLE)


# ------------------------------------------------------------------ 5: ausência ≠ zero
def test_inv5_ausente_e_zero_produzem_vereditos_diferentes():
    ausente = avaliar(entrada(receita_none=True))
    zero = avaliar(entrada(receita="0", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED))
    assert ausente.verdict is Veredito.INSUFFICIENT_EVIDENCE and zero.verdict is Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS
    assert ausente.contribution_observed is None and zero.contribution_observed is not None


# ------------------------------------------------------------------ 6 e 7: imaturo e projetado
def test_inv6_imatura_nao_decide():
    assert avaliar(entrada(receita="900", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.IMMATURE, perda="300", horizonte=14)).verdict is Veredito.INSUFFICIENT_EVIDENCE


def test_inv7_projetada_nao_e_realizada():
    r = avaliar(entrada(receita="900", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.PROJECTED, perda="300", horizonte=14))
    assert r.verdict is Veredito.TEST_WITH_CAP and r.confidence_class is Confianca.LOW


# ------------------------------------------------------------------ 8 e 9: teto
def test_inv8_sem_limite_de_perda_nao_ha_teto():
    r = avaliar(entrada(receita="600", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda=None, horizonte=None))
    assert r.max_experiment_spend is None and r.max_experiment_clicks is None


def test_inv9_teto_menor_nunca_aumenta_spend_cap():
    prev = None
    for perda in ("1000", "500", "250", "100"):
        r = avaliar(entrada(receita="600", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda=perda, horizonte=14))
        if prev is not None:
            assert r.max_experiment_spend.micros <= prev
        prev = r.max_experiment_spend.micros


# ------------------------------------------------------------------ 10: curva não monotônica
def test_inv10_nao_monotonica_recusada_ou_normalizada_com_recibo():
    s = SimulacaoEntrada("CPC_BID", "BRL", (PontoSimulacao(100_000, 1000, 80_000_000), PontoSimulacao(150_000, 900, 120_000_000), PontoSimulacao(200_000, 1300, 160_000_000)), AS_OF)
    assert analisar_simulacao(s, Fraction(140_000)).motivo == "curva_nao_monotonica"
    fm = analisar_simulacao(s, Fraction(140_000), normalizar_nao_monotonica=True)
    assert fm.normalizacao.pontos_removidos == (150_000,)


# ------------------------------------------------------------------ 11: nada posterior ao as_of
def test_inv11_lookahead_e_recusado_em_toda_medida():
    depois = datetime(2026, 10, 16, 0, 0, tzinfo=timezone.utc)
    e = entrada()
    for campo in ("cliques", "custo", "receita"):
        m = getattr(e, campo)
        with pytest.raises(C.ContratoViabilidadeViolado, match="as_of"):
            _com(e, **{campo: m.__class__(**{**m.__dict__, "disponivel_em": depois})})
    sim = SimulacaoEntrada("CPC_BID", "BRL", (PontoSimulacao(1, 1, 1), PontoSimulacao(2, 2, 2)), depois)
    with pytest.raises(C.ContratoViabilidadeViolado, match="as_of"):
        _com(e, simulacao=sim)


# ------------------------------------------------------------------ 12: reprodutibilidade
def test_inv12_reprocessar_gera_hash_identico():
    hs = {avaliar(entrada(perda="300", horizonte=14)).result_hash for _ in range(5)}
    assert len(hs) == 1


# ------------------------------------------------------------------ 13: nenhuma ação externa
def test_inv13_resultado_declara_zero_acoes_externas_e_nao_importa_rede():
    import importlib, sys
    r = avaliar(entrada(perda="300", horizonte=14))
    assert r.para_json()["external_actions"] == 0
    for mod in ("volc_dil.viability.gate", "volc_dil.viability.economia", "volc_dil.viability.simulacao", "volc_dil.viability.teto"):
        src = open(importlib.import_module(mod).__file__, encoding="utf-8").read()
        for proibido in ("requests", "urllib", "socket", "httpx", "google.ads", "psycopg", "duckdb"):
            assert proibido not in src, f"{mod} referencia {proibido}"


# ------------------------------------------------------------------ 14: Senac não hardcoded
def test_inv14_nenhum_numero_da_senac_hardcoded_no_kernel():
    import importlib
    for mod in ("volc_dil.viability.gate", "volc_dil.viability.economia", "volc_dil.viability.simulacao", "volc_dil.viability.teto", "volc_dil.viability.contrato"):
        src = open(importlib.import_module(mod).__file__, encoding="utf-8").read()
        for n in ("554.75", "40.79", "634", "0.0735", "senac", "Senac"):
            assert n not in src, f"{mod} contém {n}"
        import re as _re
        assert _re.search(r"\b\d{10,12}\b", src) is None, f"{mod} contém id bruto"


# ------------------------------------------------------------------ 15: veredito muda com economia favorável
def test_inv15_veredito_muda_com_economia_favoravel():
    assert avaliar(entrada(perda="300", horizonte=14)).verdict is Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS
    assert avaliar(entrada(receita="900", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14)).verdict is Veredito.ALREADY_PROFITABLE


# ================================================================== verificador de invariantes (runtime)
def test_verificador_aceita_resultado_honesto():
    verificar_invariantes(entrada(perda="300", horizonte=14), avaliar(entrada(perda="300", horizonte=14)))


# ================================================================== mutantes
def test_mutante_absent_vira_zero_e_detectado(monkeypatch):
    """Mutante: receita ausente tratada como zero. Deve ser pego pelo verificador."""
    original = E.calcular_economia

    def mutante(e):
        if e.receita.valor is None:
            e2 = _com(e, receita=C.MedidaMonetaria(valor=Dinheiro(0, e.custo.valor.moeda), evidencia=Evidencia.OBSERVED, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=e.receita.disponivel_em))
            return original(e2)
        return original(e)

    monkeypatch.setattr(E, "calcular_economia", mutante)
    monkeypatch.setattr(G, "envelope_conservador", lambda e: E.envelope_conservador(e))
    e = entrada(receita_none=True)
    r = avaliar(e)
    with pytest.raises(InvarianteViolada):
        verificar_invariantes(e, r)


def test_mutante_cpc_medio_no_lugar_do_marginal_e_detectado():
    """Se o kernel usasse CPC médio, o segmento do ADR seria 'sustentável'. O marginal diz que não."""
    s = SimulacaoEntrada("CPC_BID", "BRL", (PontoSimulacao(100_000, 1000, 80_000_000), PontoSimulacao(150_000, 1200, 120_000_000)), AS_OF)
    fm = analisar_simulacao(s, Fraction(140_000))
    seg, ponto = fm.segmentos[0], fm.pontos[1]
    assert ponto.cpc_medio <= Fraction(140_000)      # a média aprovaria
    assert seg.sustentavel is False                   # o marginal recusa
    assert seg.cpc_marginal != ponto.cpc_medio


def test_mutante_projected_como_realizado_e_detectado(monkeypatch):
    """Mutante: PROJECTED entra em REALIZADA no envelope. Duas redes o seguram: a governança do gate
    (evidência projetada nunca sustenta veredito positivo) e, se ela também caísse, o verificador."""
    monkeypatch.setattr(E, "REALIZADA", frozenset({Evidencia.OBSERVED, Evidencia.RECONCILED, Evidencia.PROJECTED}))
    e = entrada(receita="900", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.PROJECTED, perda="300", horizonte=14)
    r = avaliar(e)
    assert r.verdict not in (Veredito.ALREADY_PROFITABLE, Veredito.VIABLE_CANDIDATE)   # a governança segura o mutante
    verificar_invariantes(e, r)
    # se a governança também fosse mutada, o resultado positivo seria pego pelo verificador
    positivo = G.ResultadoViabilidade(**{**r.__dict__, "verdict": Veredito.ALREADY_PROFITABLE})
    positivo = G.ResultadoViabilidade(**{**positivo.__dict__, "result_hash": G._hash_resultado(positivo.para_json(com_hash=False))})
    with pytest.raises(InvarianteViolada):
        verificar_invariantes(e, positivo)


def test_mutante_governanca_ignorada_e_pego_pelo_verificador():
    """Mutante no gate que devolvesse already_profitable com receita projetada: o verificador recusa."""
    e = entrada(receita="900", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.PROJECTED, perda="300", horizonte=14)
    r = avaliar(e)
    mutado = G.ResultadoViabilidade(**{**r.__dict__, "verdict": Veredito.VIABLE_CANDIDATE})
    mutado = G.ResultadoViabilidade(**{**mutado.__dict__, "result_hash": G._hash_resultado(mutado.para_json(com_hash=False))})
    with pytest.raises(InvarianteViolada):
        verificar_invariantes(e, mutado)


# ------------------------------------------------------------------ V2: governança em grade (fix 9)
def test_inv_governanca_stale_e_invalid_nunca_positivos_em_grade():
    from datetime import timedelta
    fav = dict(receita="900", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14)
    assert avaliar(entrada(**fav)).verdict is Veredito.ALREADY_PROFITABLE
    for campo in ("custo", "cliques", "receita"):
        r = avaliar(entrada(observado_em={campo: AS_OF - timedelta(days=30)}, **fav))
        assert r.verdict is Veredito.INSUFFICIENT_EVIDENCE and r.max_experiment_spend is None
        r = avaliar(entrada(flags_medidas={campo: ("invalid_x",)}, **fav))
        assert r.verdict is Veredito.INSUFFICIENT_EVIDENCE and f"{campo}:invalid_x" in r.invalid_evidence
    for ppm in (None, 0, 999_999):
        r = avaliar(entrada(cobertura_ppm=ppm, **fav))
        assert Veredito.ordem(r.verdict) <= Veredito.ordem(Veredito.TEST_WITH_CAP) and r.confidence_class is not Confianca.HIGH


def test_inv_viable_candidate_fica_entre_test_with_cap_e_already_profitable():
    fav = dict(receita="900", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, perda="300", horizonte=14)
    cand = avaliar(entrada(cliques=300, custo="250", **fav))
    assert cand.verdict is Veredito.VIABLE_CANDIDATE
    assert Veredito.ordem(Veredito.TEST_WITH_CAP) < Veredito.ordem(cand.verdict) < Veredito.ordem(Veredito.ALREADY_PROFITABLE)
    verificar_invariantes(entrada(cliques=300, custo="250", **fav), cand)


def test_mutante_remover_as_of_e_detectado():
    j = entrada().para_json()
    del j["as_of"]
    with pytest.raises(C.ContratoViabilidadeViolado):
        C.EntradaViabilidade.de_json(j)


def test_mutante_hash_adulterado_e_detectado():
    e = entrada(perda="300", horizonte=14)
    r = avaliar(e)
    adulterado = G.ResultadoViabilidade(**{**r.__dict__, "result_hash": "0" * 64})
    with pytest.raises(InvarianteViolada):
        verificar_invariantes(e, adulterado)
