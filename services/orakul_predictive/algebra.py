"""Álgebra linear mínima em stdlib. Sem numpy/sklearn — determinística."""

from __future__ import annotations


def transposta(a: list[list[float]]) -> list[list[float]]:
    return [list(col) for col in zip(*a)]


def matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    bt = transposta(b)
    return [[sum(x * y for x, y in zip(row, col)) for col in bt] for row in a]


def matvec(a: list[list[float]], v: list[float]) -> list[float]:
    return [sum(x * y for x, y in zip(row, v)) for row in a]


def identidade(n: int) -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def somar(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[x + y for x, y in zip(ra, rb)] for ra, rb in zip(a, b)]


def escalar(a: list[list[float]], k: float) -> list[list[float]]:
    return [[x * k for x in row] for row in a]


def resolver(a: list[list[float]], b: list[float]) -> list[float]:
    """Eliminação gaussiana com pivotamento parcial."""

    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            m[piv][col] = 1e-12
        m[col], m[piv] = m[piv], m[col]
        div = m[col][col]
        for j in range(col, n + 1):
            m[col][j] /= div
        for row in range(n):
            if row == col:
                continue
            fator = m[row][col]
            for j in range(col, n + 1):
                m[row][j] -= fator * m[col][j]
    return [m[i][n] for i in range(n)]


def ridge(
    x: list[list[float]],
    y: list[float],
    alpha: float = 1.0,
    *,
    penalizar_intercepto: bool = False,
) -> list[float]:
    """Resolve Ridge; por padrão o primeiro coeficiente é o intercepto livre."""

    xt = transposta(x)
    xtx = matmul(xt, x)
    n = len(xtx)
    penalidade = escalar(identidade(n), alpha)
    if n and not penalizar_intercepto:
        penalidade[0][0] = 0.0
    xtx_reg = somar(xtx, penalidade)
    xty = matvec(xt, y)
    return resolver(xtx_reg, xty)
