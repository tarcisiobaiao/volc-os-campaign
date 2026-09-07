"""Carrega a base derivada e verifica sua integridade antes de usar o LLM."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


ARQUIVO = Path(__file__).with_name("meta_regras.v1.json")


@lru_cache(maxsize=1)
def carregar_regras() -> dict[str, Any]:
    dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    regras = dados.get("rules")
    if dados.get("schema_version") != "1.0" or not isinstance(regras, list) or not regras:
        raise RuntimeError("base de conhecimento criativa inválida")
    ids = [str(r.get("id") or "") for r in regras]
    if len(ids) != len(set(ids)) or any(not i.startswith("META-CR-") for i in ids):
        raise RuntimeError("base de conhecimento criativa contém IDs inválidos")
    return dados


def hash_da_base() -> str:
    return hashlib.sha256(ARQUIVO.read_bytes()).hexdigest()


def regras_para_prompt() -> list[dict[str, str]]:
    return [
        {
            "id": r["id"],
            "authority": r["authority"],
            "scope": r["scope"],
            "text": r["text"],
        }
        for r in carregar_regras()["rules"]
    ]
