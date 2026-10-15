"""`exchange_rate_history` pelo PostgREST, com service_role. Só transporte.

Reaproveita `persistencia._Cliente` (mesmos cabeçalhos e `raise_for_status`).
A idempotência é do banco: `on_conflict` no índice único da v23_01
(par, effective_date, fonte, as_of) com `resolution=ignore-duplicates`;
o que volta em `return=representation` são só as linhas novas.
"""
from __future__ import annotations

from typing import Sequence

from app.trafego.persistencia import _Cliente

from ..domain import Cotacao

TABELA = "exchange_rate_history"
CONFLITO = "par,effective_date,fonte,as_of"


class RepositorioCotacaoPostgrest:
    def __init__(self, cliente: _Cliente) -> None:
        self._cli = cliente

    async def gravar(self, cotacoes: Sequence[Cotacao]) -> int:
        if not cotacoes:
            return 0
        linhas = await self._cli._req(
            "POST", TABELA, params={"on_conflict": CONFLITO},
            headers=self._cli._headers("resolution=ignore-duplicates,return=representation"),
            json=[c.como_linha() for c in cotacoes])
        return len(linhas or [])
