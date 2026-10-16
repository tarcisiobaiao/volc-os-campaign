"""Stat Lab — mesma seed -> mesmo JSON (byte a byte); seed diferente -> JSON diferente."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from volc_dil.statlab.base import envelope, para_json

SCRIPTS = Path(__file__).resolve().parents[2] / "experiments" / "data-intelligence-lab" / "scripts"

CASOS = {
    "statlab_fdr.py": ["--n-replicas", "6"],
    "statlab_cs.py": ["--n-traj", "20", "--T", "300"],
    "statlab_maturacao.py": ["--n-mundos", "3"],
    "statlab_shrinkage.py": ["--n-replicas", "3"],
}


def _rodar(script: str, args: list[str], saida: Path, seed: int) -> bytes:
    subprocess.run([sys.executable, str(SCRIPTS / script), *args, "--seed", str(seed), "--saida", str(saida)],
                   check=True, capture_output=True, timeout=120,
                   env={"OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "PATH": "/usr/bin:/bin"})
    return saida.read_bytes()


@pytest.mark.parametrize("script", sorted(CASOS))
def test_mesma_seed_mesmo_json(script, tmp_path):
    a = _rodar(script, CASOS[script], tmp_path / "a.json", 123)
    b = _rodar(script, CASOS[script], tmp_path / "b.json", 123)
    c = _rodar(script, CASOS[script], tmp_path / "c.json", 124)
    assert a == b
    assert a != c
    d = json.loads(a)
    assert d["seed"] == 123 and d["n_simulacoes"] > 0
    assert d["natureza"] == "simulacao_com_seed_sem_dado_real"
    for k in ("numpy", "scipy", "statsmodels", "python", "statlab"):
        assert d["versoes"][k]


def test_json_nan_vira_null_e_sem_timestamp():
    env = envelope("x", 1, 1, {}, {"a": float("nan"), "b": float("inf")})
    texto = para_json(env)
    d = json.loads(texto)
    assert d["resultados"]["a"] is None
    assert d["resultados"]["b"] == "+inf"
    assert "timestamp" not in texto and "gerado_em" not in texto
