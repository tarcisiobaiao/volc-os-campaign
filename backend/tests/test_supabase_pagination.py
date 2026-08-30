"""
select_all — paginação obrigatória contra o teto do PostgREST.

O Supabase corta TODA resposta em `db-max-rows` (1000 neste projeto) e IGNORA um
`limit` maior: `limit=5000` devolve 1000 linhas, sem erro. Isso truncava em
silêncio as dores/seed queries dos cards mais recentes de um país (BR já passa de
1300 seed queries) — inclusive as de um card recém-duplicado.

Run:  cd backend && pytest tests/test_supabase_pagination.py -v
"""
from __future__ import annotations

import os
import sys

for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "PERPLEXITY_API_KEY", "PAUTADOR_API_KEY"):
    os.environ[_k] = ""

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from typing import Any, Dict, List

from app.config import Settings
from app.services.supabase_service import SupabaseService

MAX_ROWS = 1000  # o teto do servidor, que o `limit` do cliente não vence


def _service_with_rows(total: int):
    """SupabaseService cujo `select` finge ser o PostgREST: respeita offset e
    NUNCA devolve mais que MAX_ROWS, por maior que seja o limit pedido."""
    svc = SupabaseService(Settings(supabase_url="https://x.supabase.co", supabase_service_role_key="k"))
    calls: List[Dict[str, Any]] = []
    rows = [{"id": i} for i in range(total)]

    async def fake_select(table: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        calls.append(params)
        offset = int(params.get("offset") or 0)
        limit = min(int(params.get("limit") or MAX_ROWS), MAX_ROWS)
        return rows[offset:offset + limit]

    svc.select = fake_select  # type: ignore[assignment]
    return svc, calls


def test_select_all_pagina_ate_o_fim():
    svc, calls = _service_with_rows(2350)
    out = asyncio.run(svc.select_all("t", {"country_code": "eq.BR"}))
    assert [r["id"] for r in out] == list(range(2350))
    assert len(calls) == 3  # 1000 + 1000 + 350
    assert [c["offset"] for c in calls] == [0, 1000, 2000]


def test_select_all_uma_pagina_so_quando_cabe():
    svc, calls = _service_with_rows(42)
    out = asyncio.run(svc.select_all("t", {}))
    assert len(out) == 42
    assert len(calls) == 1  # página incompleta encerra o laço


def test_select_all_ordena_de_forma_estavel_e_respeita_a_ordem_do_caller():
    """Offset sem ORDER BY estável pode repetir/pular linha entre páginas."""
    svc, calls = _service_with_rows(1)
    asyncio.run(svc.select_all("t", {}))
    assert calls[0]["order"] == "id.asc"

    svc2, calls2 = _service_with_rows(1)
    asyncio.run(svc2.select_all("t", {"order": "score.desc.nullslast,id.asc"}))
    assert calls2[0]["order"] == "score.desc.nullslast,id.asc"


def test_select_all_ignora_limit_do_caller():
    """Um `limit` do caller daria falsa sensação de teto: quem chama select_all
    quer TUDO, e o limit real por página é o do servidor."""
    svc, calls = _service_with_rows(1500)
    out = asyncio.run(svc.select_all("t", {"limit": 5000}))
    assert len(out) == 1500
    assert all(c["limit"] == SupabaseService.PAGE_SIZE for c in calls)
