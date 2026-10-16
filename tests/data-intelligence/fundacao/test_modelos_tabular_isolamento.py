"""Tabular: anti-vazamento (metadado e empírico), features só do passado; isolamento do pacote modelos."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np

from volc_dil.fundacao import modelos as M

RAIZ = Path(__file__).resolve().parents[3]
PACOTE = RAIZ / "experiments" / "data-intelligence-lab" / "src" / "volc_dil" / "fundacao" / "modelos"
SCRIPTS = sorted((RAIZ / "experiments" / "data-intelligence-lab" / "scripts").glob("fundacao_modelos*.py"))


def test_checar_vazamento_por_disponibilidade():
    metas = [M.FeatureMeta("lucro_lag1", 100), M.FeatureMeta("lucro_alvo_final", 500), M.FeatureMeta("dow", 0)]
    achados = M.checar_vazamento(metas, origem=200)
    assert [a.detalhes["feature"] for a in achados] == ["lucro_alvo_final"]
    assert all(a.tipo == "vazamento" for a in achados)


def _paineis(E=5, D=20, seed=0):
    rng = np.random.default_rng(seed)
    custo = rng.uniform(10, 20, (E, D))
    receita = custo * rng.uniform(0.8, 1.2, (E, D))
    mat = np.full((E, D), 2)
    return custo, receita, mat


def test_features_no_corte_nao_leem_o_futuro():
    custo, receita, mat = _paineis()
    X, nomes = M.features_no_corte(custo, receita, mat, mat, 10, n_lags=5, n_media=3, dia_semana_alvo=2)
    c2, r2 = custo.copy(), receita.copy()
    c2[:, 10:] = 1e9
    r2[:, 10:] = -1e9
    X2, _ = M.features_no_corte(c2, r2, mat, mat, 10, n_lags=5, n_media=3, dia_semana_alvo=2)
    np.testing.assert_array_equal(X, X2)
    assert len(nomes) == X.shape[1]


def test_lag_imaturo_nao_entra_como_maduro():
    custo, receita, mat = _paineis()
    mat = mat.copy()
    mat[:, 9] = 1  # dia o-1 ainda preliminar
    X, nomes = M.features_no_corte(custo, receita, mat, mat, 10, n_lags=5, n_media=3, dia_semana_alvo=0)
    i = nomes.index("ultimo_maduro")
    np.testing.assert_allclose(X[:, i], (receita - custo)[:, 8])


def test_vazamento_empirico_pega_feature_do_futuro():
    rng = np.random.default_rng(1)
    n = 600
    X = rng.normal(0, 1, (n, 4))
    y = X[:, 0] * 0.3 + rng.normal(0, 1, n)
    futuro = y + rng.normal(0, 0.1, n)  # feature = o próprio alvo com ruído
    tr, te = slice(0, 400), slice(400, n)
    sem = M.ajustar_e_prever("ridge", X[tr], y[tr], X[te])
    Xc = np.column_stack([X, futuro])
    com = M.ajustar_e_prever("ridge", Xc[tr], y[tr], Xc[te])
    mae = lambda p: float(np.mean(np.abs(p - y[te])))  # noqa: E731
    a = M.vazamento_empirico(mae(sem), mae(com), ganho_implausivel=0.3, nome="futuro")
    assert a.detectado and a.estatistica > 0.5
    honesta = np.column_stack([X, rng.normal(0, 1, n)])
    h = M.ajustar_e_prever("hgb", honesta[tr], y[tr], honesta[te])
    assert not M.vazamento_empirico(mae(sem), mae(h), ganho_implausivel=0.3, nome="ruido").detectado


def _imports(caminho: Path) -> set[str]:
    arv = ast.parse(caminho.read_text(encoding="utf-8"))
    nomes: set[str] = set()
    for no in ast.walk(arv):
        if isinstance(no, ast.Import):
            nomes |= {a.name.split(".")[0] for a in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            nomes.add(no.module.split(".")[0])
    return nomes


def test_isolamento_sem_rede_segredo_ou_subprocesso():
    proibidos = {"socket", "urllib", "http", "requests", "subprocess", "importlib", "httpx", "aiohttp", "psycopg",
                 "psycopg2", "supabase", "google"}
    arquivos = sorted(PACOTE.glob("*.py")) + SCRIPTS
    assert len(arquivos) >= 10
    for f in arquivos:
        texto = f.read_text(encoding="utf-8")
        assert not (_imports(f) & proibidos), f
        assert not re.search(r"\.env\b", texto), f
        for marca in ("os.environ", "eval(", "exec(", "__import__", "~/.ssh"):
            assert marca not in texto, (f, marca)
