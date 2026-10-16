"""EB (fachada do Stat Lab) e detectores de mudança: casos conhecidos, propriedades, ausência recusada."""
from __future__ import annotations

import numpy as np
import pytest

from volc_dil.fundacao import modelos as M


# ── EB ────────────────────────────────────────────────────────────────────

def test_encolher_taxa_reduz_mse_e_marca_sem_dados():
    rng = np.random.default_rng(0)
    K = 200
    p = rng.beta(4, 96, K)
    n = rng.integers(5, 60, K)
    n[0] = 0
    x = rng.binomial(n, p)
    r = M.encolher_taxa(x, n, nivel=0.9)
    cru = np.where(n > 0, x / np.maximum(n, 1), np.nan)
    ok = n > 0
    assert np.mean((r["media"][ok] - p[ok]) ** 2) < 0.7 * np.mean((cru[ok] - p[ok]) ** 2)
    assert r["sem_dados"][0] and r["media"][0] == pytest.approx(r["prior"]["a"] / (r["prior"]["a"] + r["prior"]["b"]))


def test_encolher_recusa_ausencia():
    with pytest.raises(ValueError):
        M.encolher_taxa([1, np.nan], [10, 10], nivel=0.9)
    with pytest.raises(ValueError):
        M.encolher_media([1.0, np.nan], [1.0, 1.0], [2, 2], nivel=0.9)


def test_vencedores_por_sorte_analitico():
    est = np.array([10, 9, 8, 1, 0], float)
    ver = np.array([0, 9, 8, 10, 1], float)
    r = M.vencedores_por_sorte(est, ver, frac_top=0.4)
    assert r["selecionados"] == 2 and r["por_sorte"] == 1
    r2 = M.vencedores_por_sorte([1, np.nan, 3], [1, 2, 3], frac_top=0.5)
    assert r2["n_excluidos"] == 1


# ── mudança ───────────────────────────────────────────────────────────────

def _degrau(n=60, t0=30, delta=3.0, seed=0, sd=1.0):
    rng = np.random.default_rng(seed)
    x = rng.normal(0, sd, n)
    x[t0:] += delta
    return x


@pytest.mark.parametrize("metodo,params", [
    ("cusum", dict(n_ref=15, k=0.5, h=5.0)),
    ("bocpd", dict(n_ref=15, hazard=1 / 100, w=5, limiar=0.5)),
    ("media_movel", dict(n_ref=15, janela=5, limiar=1.5)),
])
def test_detecta_degrau_grande_logo_apos_a_quebra(metodo, params):
    a = M.detectar_quebra(_degrau(), metodo=metodo, **params)
    assert a.detectado and a.tipo == "quebra"
    assert 30 <= a.indice <= 36
    assert a.ponto_estimado is not None and 26 <= a.ponto_estimado <= a.indice


def test_cusum_estima_direcao_e_nao_dispara_em_serie_estavel_com_limiar_alto():
    a = M.cusum(-_degrau(delta=4.0), n_ref=15, k=0.5, h=5.0)
    assert a.detalhes["direcao"] == "queda"
    # referência curta (15 pontos) é estimada com erro: alarme falso existe e cai com o limiar
    def falsos(h):
        return sum(M.cusum(np.random.default_rng(s).normal(0, 1, 60), n_ref=15, k=1.0, h=h).detectado
                   for s in range(50))
    assert falsos(12.0) < falsos(4.0)
    assert falsos(12.0) <= 5


def test_bocpd_posterior_e_distribuicao():
    z = _degrau(n=40, t0=20, delta=5.0)
    R = M.bocpd_posterior(z, hazard=0.02)
    np.testing.assert_allclose(R.sum(axis=1), 1.0, atol=1e-9)
    assert np.argmax(R[30]) <= 12  # depois da quebra, run length curto é o mais provável


def test_online_decisao_em_t_nao_depende_do_futuro():
    x = _degrau(seed=3)
    a = M.cusum(x, n_ref=15, k=0.5, h=5.0)
    y = x.copy()
    y[a.indice + 1:] = 1e6  # futuro absurdo não muda a decisão já tomada
    b = M.cusum(y, n_ref=15, k=0.5, h=5.0)
    assert (a.indice, a.ponto_estimado) == (b.indice, b.ponto_estimado)


def test_recusa_ausencia_e_metodo_desconhecido():
    x = _degrau()
    x[40] = np.nan
    with pytest.raises(ValueError):
        M.cusum(x, n_ref=15, k=0.5, h=5.0)
    with pytest.raises(ValueError):
        M.detectar_quebra(_degrau(), metodo="prophet")


def test_calibrar_limiar_monotono_e_respeita_alvo():
    rng = np.random.default_rng(5)
    series = [rng.normal(0, 1, 60) for _ in range(30)]
    grade = np.array([2.0, 4.0, 6.0, 8.0, 12.0])
    r = M.calibrar_limiar(series, metodo="cusum", alvo_fa_por_unidade_tempo=0.05, unidade_tempo=7.0, grade=grade,
                          n_ref=15, k=0.5)
    taxas = [c["taxa_fa"] for c in r["curva"]]
    assert all(a >= b - 1e-12 for a, b in zip(taxas, taxas[1:]))
    assert r["limiar"] is not None
    escolhido = next(c for c in r["curva"] if c["limiar"] == r["limiar"])
    assert escolhido["taxa_fa"] <= 0.05
