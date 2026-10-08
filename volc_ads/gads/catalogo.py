"""O que o SERVIDOR aceita no SELECT de uma GAQL, conferido sem rede.

A fonte é `google_ads_api/catalogo_gaql_v25.json`, gerado do
`GoogleAdsFieldService` por `google_ads_api/atualizar_catalogo_gaql.py`.

⚠️ O descriptor do SDK não serve para isso. Medido em 08/10/2026 com
`validate_only`: `asset_group_asset.primary_status_details` é ACEITO e
`asset_group_asset.primary_status_details.status` é RECUSADO
(UNRECOGNIZED_FIELD), embora os dois existam no proto. Em GAQL, campo de tipo
mensagem só se seleciona inteiro. Um campo recusado não custa o campo: derruba
a consulta inteira.
"""
from __future__ import annotations

import ast
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterator

ARQUIVO = Path(__file__).resolve().parents[1] / "google_ads_api" / "catalogo_gaql_v25.json"

_SELECT = re.compile(r"\bSELECT\s+(.*?)\s+FROM\s+([a-z_]+)", re.S | re.I)


@lru_cache(maxsize=1)
def carregar() -> dict:
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))


def campos_do_select(gaql: str) -> tuple[str, ...]:
    """Os campos do SELECT, na ordem. Vazio se não houver SELECT … FROM."""
    m = _SELECT.search(gaql or "")
    if not m:
        return ()
    return tuple(c.strip() for c in m.group(1).split(",") if c.strip())


def invalidos(gaql: str) -> tuple[str, ...]:
    """Campos do SELECT que o servidor v25 não aceita selecionar."""
    campos = carregar()["campos"]
    return tuple(c for c in campos_do_select(gaql)
                 if c not in campos or not campos[c][1])


def exigir_valida(gaql: str) -> str:
    """Devolve a própria GAQL, ou levanta antes de ela sair da máquina."""
    ruins = invalidos(gaql)
    if ruins:
        raise ValueError(f"GAQL com campos não selecionáveis na v25: {list(ruins)}")
    return gaql


INTERP = "__interpolado__"


def _texto(no: ast.AST) -> str | None:
    if isinstance(no, ast.Constant) and isinstance(no.value, str):
        return no.value
    if isinstance(no, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else INTERP for v in no.values)
    return None


def varrer_gaqls(raiz: Path, pastas: tuple[str, ...] = ("volc_ads", "backend/app")
                 ) -> Iterator[tuple[str, str]]:
    """(onde, texto) de toda string `SELECT … FROM <resource GAQL>` literal.

    SQL do Supabase fica de fora porque o FROM não é resource do catálogo.
    Trechos de f-string interpolados viram `INTERP`. Testes e scripts de
    teste são ignorados.
    """
    recursos = {n for n, c in carregar()["campos"].items() if c[0] == "RESOURCE"}
    for pasta in pastas:
        for arq in sorted((raiz / pasta).rglob("*.py")):
            rel = arq.relative_to(raiz).as_posix()
            if "/testes_" in rel or "/tests/" in rel or "__pycache__" in rel:
                continue
            for no in ast.walk(ast.parse(arq.read_text(encoding="utf-8"))):
                texto = _texto(no)
                if not texto or "SELECT" not in texto.upper():
                    continue
                m = _SELECT.search(texto)
                if m and m.group(2) in recursos:
                    yield f"{rel}:{no.lineno}", texto
