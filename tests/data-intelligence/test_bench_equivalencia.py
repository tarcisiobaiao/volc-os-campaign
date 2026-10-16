"""Equivalência da bancada: contrato == Python puro == DuckDB == Polars (dados SINTÉTICOS).

Cada teste tenta quebrar um invariante: null != 0, moedas não somadas, identidade exata,
empate de versão detectado, e que uma engine "ingênua" (SUM ignorando NULL) é pega pelo hash.
"""
from __future__ import annotations

import random

import pytest

pl = pytest.importorskip("polars")
duckdb = pytest.importorskip("duckdb")

from volc_dil.bench import dados  # noqa: E402
from volc_dil.bench import engines as E  # noqa: E402

AS_OF = dados.as_of_padrao_us()


@pytest.fixture(scope="module")
def linhas():
    return dados.gerar(3000, seed=11)


def _todas(linhas, tmp_path, *, ingenuo=False):
    pq = tmp_path / "obs.parquet"
    dados.para_polars(linhas).write_parquet(pq)
    con = E.conectar_duckdb(2)
    con.execute(f"CREATE TABLE obs AS SELECT * FROM read_parquet('{pq}')")
    emp_d = E.op_duckdb(con, AS_OF, ingenuo=ingenuo)
    r_d = E.exportar_duckdb(con)
    nat, emp_p = E.op_polars(pl.scan_parquet(pq), AS_OF, ingenuo=ingenuo)
    r_p = E.exportar_polars(nat)
    return {"duckdb": (r_d, emp_d), "polars": (r_p, emp_p)}


def test_quatro_implementacoes_dao_o_mesmo_hash(linhas, tmp_path):
    r_py, e_py = E.op_python(linhas, AS_OF)
    r_ct, e_ct = E.op_contrato(E.para_observacoes(linhas), AS_OF)
    outras = _todas(linhas, tmp_path)
    h = {E.hash_resultado(r_py, e_py), E.hash_resultado(r_ct, e_ct)} | {E.hash_resultado(*v) for v in outras.values()}
    assert len(h) == 1
    assert e_py == 0 and len(r_py) > 100


def test_dataset_exercita_as_armadilhas(linhas):
    r, _ = E.op_python(linhas, AS_OF)
    motivos = {x[14] for x in r}
    estados = {x[4] for x in r} | {x[9] for x in r}
    assert {"sem_custo", "sem_receita", "sem_valor"} <= motivos
    assert {"nao_coletado", "moedas_misturadas", "medido"} <= estados
    assert any(x[0] == "acc-B" for x in r)  # receita sob outra conta nunca pareia
    assert all(x[14] == "sem_custo" for x in r if x[0] == "acc-B")


def test_sum_ingenuo_que_ignora_null_e_detectado(linhas, tmp_path):
    certo = _todas(linhas, tmp_path)
    ingenuo = _todas(linhas, tmp_path, ingenuo=True)
    for engine in ("duckdb", "polars"):
        assert E.hash_resultado(*certo[engine]) != E.hash_resultado(*ingenuo[engine])
        pares = list(zip(sorted(certo[engine][0], key=lambda x: x[:3]), sorted(ingenuo[engine][0], key=lambda x: x[:3])))
        # existe grupo onde o certo diz "sem valor" e o ingênuo inventou um número
        assert any(c[8] is None and i[8] is not None and c[12] and c[12] > 0 for c, i in pares)


def test_semantica_crua_das_engines_e_o_risco_documentado():
    """SUM de DuckDB e sum() de Polars IGNORAM NULL — por isso o plano não usa a soma crua."""
    con = E.conectar_duckdb(1)
    assert con.execute("SELECT sum(x) FROM (VALUES (1), (NULL), (2)) t(x)").fetchone()[0] == 3
    assert con.execute("SELECT sum(x) FROM (VALUES (NULL::BIGINT)) t(x)").fetchone()[0] is None
    assert pl.Series([1, None, 2], dtype=pl.Int64).sum() == 3
    assert pl.Series([None, None], dtype=pl.Int64).sum() == 0  # Polars: tudo nulo vira 0!


def test_grupo_com_membro_nulo_fica_sem_valor_em_todas(tmp_path):
    base = ("acc-A", "cmp-x", None, "2026-08-02", "cost", "google_ads", None, AS_OF - 10, None, "BRL",
            "medido", "mature", "complete")
    linhas = [
        base[:2] + ("desktop",) + base[3:8] + (5_000_000,) + base[9:],
        base[:2] + ("mobile",) + base[3:8] + (None, None, "falha", "preliminary", "unknown"),
        base[:2] + ("tablet",) + base[3:8] + (None, None, "nao_coletado", "preliminary", "unknown"),
    ]
    r_py, _ = E.op_python(linhas, AS_OF)
    assert r_py[0][3] is None and r_py[0][4] == "falha" and r_py[0][7] == 2  # pior estado vence; null != 0
    outras = _todas(linhas, tmp_path)
    for v in outras.values():
        assert E.hash_resultado(*v) == E.hash_resultado(r_py, 0)


def test_moedas_nunca_somadas(tmp_path):
    l1 = ("acc-A", "cmp-y", "desktop", "2026-08-02", "revenue", "publisher", "reported_revenue", AS_OF - 5, 7, "BRL",
          "medido", "revised", "complete")
    l2 = ("acc-A", "cmp-y", "mobile", "2026-08-02", "revenue", "publisher", "reported_revenue", AS_OF - 5, 9, "USD",
          "medido", "revised", "complete")
    r_py, _ = E.op_python([l1, l2], AS_OF)
    assert r_py[0][8] is None and r_py[0][9] == "moedas_misturadas" and r_py[0][10] is None
    for v in _todas([l1, l2], tmp_path).values():
        assert E.hash_resultado(*v) == E.hash_resultado(r_py, 0)
    r_ct, _ = E.op_contrato(E.para_observacoes([l1, l2]), AS_OF)
    assert r_ct == r_py


def test_empate_de_versao_e_contado_e_contrato_recusa(linhas, tmp_path):
    alvo = next(x for x in linhas if x[dados.I_MICROS] is not None and x[dados.I_DISP] <= AS_OF)
    gemeo = alvo[:dados.I_MICROS] + (alvo[dados.I_MICROS] + 1,) + alvo[dados.I_MICROS + 1:]
    com_empate = linhas + [gemeo]
    _, e_py = E.op_python(com_empate, AS_OF)
    outras = _todas(com_empate, tmp_path)
    assert e_py >= 1
    assert outras["duckdb"][1] == e_py and outras["polars"][1] == e_py
    with pytest.raises(E.EmpateDeVersao):
        E.op_contrato(E.para_observacoes(com_empate), AS_OF)


def test_ordem_de_chegada_nao_importa(linhas):
    embaralhadas = list(linhas)
    random.Random(1).shuffle(embaralhadas)
    assert E.hash_resultado(*E.op_python(linhas, AS_OF)) == E.hash_resultado(*E.op_python(embaralhadas, AS_OF))


def test_corte_as_of_exclui_revisoes_futuras(linhas):
    futuras = [x for x in linhas if x[dados.I_DISP] > AS_OF]
    assert futuras  # o corte realmente remove algo
    r_tudo, _ = E.op_python(linhas, 2**62)
    r_corte, _ = E.op_python(linhas, AS_OF)
    assert E.hash_resultado(r_tudo, 0) != E.hash_resultado(r_corte, 0)


def test_duckdb_sem_autoload_nem_autoinstall():
    con = E.conectar_duckdb(1)
    cfg = dict(con.execute("SELECT name, value FROM duckdb_settings() WHERE name IN "
                           "('autoinstall_known_extensions','autoload_known_extensions')").fetchall())
    assert cfg == {"autoinstall_known_extensions": "false", "autoload_known_extensions": "false"}
