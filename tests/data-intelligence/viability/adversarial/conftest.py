"""Suíte RED (time vermelho) do kernel de viabilidade.

Põe o diretório pai (`tests/data-intelligence/viability/`) no path para reusar `_entradas.entrada`
e oferece dois utilitários como fixtures: `sobrescrever` (cópia de dataclass congelada com campos
trocados, inclusive campos que só existem na V2) e `autorizacao_v2` (constrói uma `Autorizacao`
válida pela especificação V2, com hash canônico; na V1 falha explicitamente por construção).
"""
from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import pytest

PAI = Path(__file__).resolve().parents[1]
if str(PAI) not in sys.path:
    sys.path.insert(0, str(PAI))

AS_OF_RED = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def _sobrescrever(obj: Any, **campos: Any) -> Any:
    """Reconstrói `obj` (dataclass congelada) com `campos` trocados. Quando um campo não existe na
    versão em teste (ex.: `observado_em` na V1), falha com mensagem explícita: é uma falha POR
    CONSTRUÇÃO, não uma falha econômica, e o relatório distingue as duas."""
    try:
        return obj.__class__(**{**obj.__dict__, **campos})
    except TypeError as exc:
        pytest.fail(f"falha por construção: {obj.__class__.__name__} não aceita {sorted(campos)} nesta versão ({exc})")


@pytest.fixture
def sobrescrever() -> Callable[..., Any]:
    return _sobrescrever


@pytest.fixture
def autorizacao_v2() -> Callable[..., Any]:
    """Fábrica de `Autorizacao` V2. hash = sha256 do JSON canônico de
    {authorization_id, version, issuer, effective_at iso, expires_at iso|None}."""
    from volc_dil.viability import contrato

    def fabrica(*, issuer: str = "tarcisio@agenciavolc.com.br", effective_at: Optional[datetime] = None,
                expires_at: Optional[datetime] = None, disponivel_em: Optional[datetime] = None,
                authorization_id: str = "aut-red-0001", version: int = 1, hash_errado: bool = False) -> Any:
        A = getattr(contrato, "Autorizacao", None)
        if A is None:
            pytest.fail("falha por construção: a V1 não tem `Autorizacao` (perda_maxima só carrega proveniência textual)")
        eff = effective_at or (AS_OF_RED - timedelta(days=1))
        canon = {"authorization_id": authorization_id, "version": version, "issuer": issuer,
                 "effective_at": eff.isoformat(), "expires_at": None if expires_at is None else expires_at.isoformat()}
        h = hashlib.sha256(contrato.json_canonico(canon).encode("utf-8")).hexdigest()
        if hash_errado:
            h = ("0" if h[0] != "0" else "1") + h[1:]
        return A(authorization_id=authorization_id, version=version, hash=h, issuer=issuer, effective_at=eff,
                 expires_at=expires_at, disponivel_em=disponivel_em or eff)

    return fabrica
