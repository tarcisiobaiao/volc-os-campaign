"""Smoke test de cada dependência direta do lab (ver DEPENDENCIAS.json). Sem rede."""


def test_numpy():
    import numpy as np
    assert np.linalg.solve(np.array([[2.0, 0], [0, 4.0]]), np.array([2.0, 8.0])).tolist() == [1.0, 2.0]


def test_pandas():
    import pandas as pd
    df = pd.DataFrame({"c": ["a", "a", "b"], "v": [1, 2, 3]})
    assert df.groupby("c")["v"].sum().to_dict() == {"a": 3, "b": 3}


def test_polars():
    import polars as pl
    df = pl.DataFrame({"c": ["a", "a", "b"], "v": [1, 2, 3]})
    assert dict(df.group_by("c").agg(pl.col("v").sum()).sort("c").iter_rows()) == {"a": 3, "b": 3}


def test_duckdb_e_pyarrow():
    import duckdb
    import pyarrow as pa
    t = pa.table({"v": [1, 2, 3]})
    assert duckdb.sql("select sum(v) from t").fetchone()[0] == 6


def test_scikit_learn():
    import numpy as np
    from sklearn.linear_model import LinearRegression
    x = np.arange(10).reshape(-1, 1)
    m = LinearRegression().fit(x, 3 * x.ravel() + 1)
    assert round(float(m.coef_[0]), 6) == 3.0


def test_ortools():
    from ortools.linear_solver import pywraplp
    s = pywraplp.Solver.CreateSolver("GLOP")
    a, b = s.NumVar(0, 10, "a"), s.NumVar(0, 10, "b")
    s.Add(a + b <= 10)
    s.Maximize(2 * a + b)
    assert s.Solve() == pywraplp.Solver.OPTIMAL and round(s.Objective().Value()) == 20


def test_psycopg_importa_sem_conectar():
    import psycopg
    assert psycopg.__version__.startswith("3.")


def test_jsonschema():
    import jsonschema
    jsonschema.validate({"a": 1}, {"type": "object", "required": ["a"]})


def test_scipy():
    from scipy.stats import binomtest
    assert 0 < binomtest(3, 10, 0.5).pvalue <= 1
