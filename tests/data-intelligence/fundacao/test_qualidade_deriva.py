"""Detector de deriva: falso alarme MEDIDO em dado estacionário e poder em quebra injetada (seeds fixas).

Números de referência (seed 20261016/20261017, 28 dias de base × 7 recentes, alfa = 1%, efeito >= 0,5)
estão no doc 09; aqui ficam as garantias que o doc cita.
"""
from __future__ import annotations

import math

from volc_dil.fundacao.qualidade.deriva import checar_deriva, detectar_deriva, medir_falso_alarme, medir_poder


def test_falso_alarme_iid_estacionario_ate_2pct():
    r = medir_falso_alarme(n_series=2000, phi=0.0)
    assert r["taxa"] <= 0.02, r


def test_falso_alarme_com_autocorrelacao_controlado_pela_correcao():
    for phi in (0.3, 0.6):
        r = medir_falso_alarme(n_series=1500, phi=phi)
        assert r["taxa"] <= 0.02, r


def test_ks_cru_infla_com_autocorrelacao_limite_conhecido():
    """Contraprova que mantém o doc honesto: sem a correção, AR(1) phi=0,6 passa de 5%."""
    r = medir_falso_alarme(n_series=1500, phi=0.6, corrigir_autocorrelacao=False)
    assert r["taxa"] > 0.05, r


def test_poder_em_quebra_grosseira():
    assert medir_poder(multiplicador=0.1, n_series=500)["poder"] >= 0.9  # custo despenca (coleta quebrada)
    assert medir_poder(multiplicador=3.0, n_series=500)["poder"] >= 0.6
    assert medir_poder(multiplicador=3.0, n_series=500, corrigir_autocorrelacao=False)["poder"] >= 0.75


def test_poder_baixo_em_mudanca_pequena_e_limite_documentado():
    """7 pontos não detectam ×1,3 de forma confiável: o detector é de quebra, não de tendência de negócio."""
    assert medir_poder(multiplicador=1.3, n_series=500)["poder"] < 0.3


def test_null_nao_e_zero_e_amostra_insuficiente():
    base = [100.0 + (i % 5) for i in range(28)]
    r = detectar_deriva(base, [None] * 7)
    assert r.motivo == "amostra_insuficiente" and r.descartados_nulos == 7 and not r.deriva
    r = detectar_deriva(base, [0.0] * 7)  # zeros de verdade são dado e derivam
    assert r.deriva


def test_base_constante_mediana_mudou_tem_efeito_infinito():
    r = detectar_deriva([5.0] * 28, [9.0] * 7)
    assert math.isinf(r.efeito_robusto) and r.deriva
    r = detectar_deriva([5.0] * 28, [5.0] * 7)
    assert r.efeito_robusto == 0.0 and not r.deriva


def test_checar_deriva_emite_achado_com_evidencia():
    estavel = [100.0 + (i * 7) % 13 for i in range(35)]
    quebrada = estavel[:28] + [1.0] * 7
    ach = checar_deriva({"c:1": estavel, "c:2": quebrada})
    assert [a.chave for a in ach] == ["c:2"]
    ev = ach[0].evidencia
    assert ev["n_base"] == 28 and ev["n_recente"] == 7 and ev["falsos_alarmes_esperados"] == 0.02
