"""Stat Lab — relatório sincronizado com os JSONs, sonda derivada do log, conferência BH com poder,
PMF de atraso sem massa perdida."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from volc_dil.statlab.fdr import bh_propria, bh_statsmodels
from volc_dil.statlab.maturacao import pmf_atraso_lognormal

LAB = Path(__file__).resolve().parents[2] / "experiments" / "data-intelligence-lab"
SCRIPTS = LAB / "scripts"
RES = LAB / "results" / "statlab"


def _modulo(nome: str):
    spec = importlib.util.spec_from_file_location(nome, SCRIPTS / f"{nome}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_relatorio_md_e_regenerado_exatamente_dos_json(tmp_path):
    """F2-08: todo número do MD vem dos JSONs. Se alguém editar o MD à mão ou mudar um JSON sem
    regenerar, este teste falha."""
    saida = tmp_path / "STATLAB-RESULTS.md"
    subprocess.run([sys.executable, str(SCRIPTS / "statlab_relatorio.py"), "--res", str(RES), "--saida", str(saida)],
                   check=True, capture_output=True, timeout=60)
    assert saida.read_text() == (RES / "STATLAB-RESULTS.md").read_text()
    texto = saida.read_text().lower()
    assert "validado" not in texto.replace("nada aqui é 'validado'", "")


def test_sonda_deriva_status_do_log(tmp_path):
    sonda = _modulo("statlab_sonda_confseq")
    ok = tmp_path / "ok.log"
    ok.write_text("Resolved 3 packages\nInstalled 3 packages in 20ms\n + confseq==0.0.11\n + numpy==2.5.3\n")
    falha = tmp_path / "falha.log"
    falha.write_text("   Building confseq==0.0.11\nerror: Failed to build `confseq==0.0.11`\n"
                     "-- Could NOT find Boost (missing: Boost_INCLUDE_DIR)\n")
    assert sonda._status_instalacao(ok) == {"resultado": "SUCESSO", "versao": "0.0.11"}
    r = sonda._status_instalacao(falha)
    assert r["resultado"] == "FALHOU" and r["boost_ausente"] and r["versao_tentada"] == "0.0.11"
    assert sonda._status_instalacao(tmp_path / "nao_existe.log")["resultado"] == "NAO_EXECUTADA"


def test_conferencia_bh_so_absolve_empate_no_corte():
    fdr_script = _modulo("statlab_fdr")
    # empate exato no corte: p_(7) == 0.2 * 7 / 10
    p = np.array([0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.14, 0.9, 0.9, 0.9])
    a = bh_propria(p, 0.2)
    assert a.sum() == 7
    b = p <= 0.06  # outra implementação para no k = 6 por ponto flutuante
    assert fdr_script._divergencia_no_corte_exato(p, 0.2, a, b)
    # mesmo tamanho de divergência, mas conjunto que não é prefixo: não é absolvido
    c = b.copy()
    c[0], c[6] = False, True
    assert not fdr_script._divergencia_no_corte_exato(p, 0.2, a, c)
    # divergência real (mutante sem step-up) NÃO é absolvida, mesmo com p na fronteira em outro lugar
    rng = np.random.default_rng(0)
    absolvidas = falsas = 0
    for _ in range(300):
        p = np.round(rng.beta(0.3, 1.0, int(rng.integers(5, 200))), 2)
        for q in (0.05, 0.2):
            a, b = fdr_script.bh_mutante_pontual(p, q), bh_statsmodels(p, q)
            if not np.array_equal(a, b):
                falsas += 1
                absolvidas += fdr_script._divergencia_no_corte_exato(p, q, a, b)
    # o mutante só pode ser absolvido onde coincide com o step-up E diverge por ponto flutuante no
    # corte (ex.: m=86, q=0.2, p_(43)=0.1 == 0.2*43/86); a regra antiga absolvia ~47% dos casos
    assert falsas > 100 and absolvidas <= 0.02 * falsas


def test_pmf_lognormal_inclui_floor_igual_ao_maximo():
    mx = 5
    pmf = pmf_atraso_lognormal(4.0, 1.0, mx)
    F = stats.lognorm.cdf(np.arange(0, mx + 2), s=1.0, scale=4.0)
    esperado = np.diff(F) / F[-1]          # P(k <= D < k+1 | D < mx+1), k = 0..mx
    np.testing.assert_allclose(pmf, esperado, rtol=1e-12)
    assert pmf[-1] > 0 and pmf.size == mx + 1 and pmf.sum() == pytest.approx(1.0)
