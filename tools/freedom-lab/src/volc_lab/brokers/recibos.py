"""Recibos sanitizados, append-only, em JSONL no diretório da rodada."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

# Padrões que nunca podem aparecer num recibo. Se aparecerem, o recibo não é gravado.
_PROIBIDOS = [
    re.compile(r"ya29\.[0-9A-Za-z_\-]+"),            # access token Google
    re.compile(r"1//[0-9A-Za-z_\-]{20,}"),           # refresh token Google
    re.compile(r"GOCSPX-[0-9A-Za-z_\-]+"),           # client secret Google
    re.compile(r"eyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}"),  # JWT (anon/service_role)
    re.compile(r"(?i)(refresh_token|client_secret|password|senha)(\\\\?\")?\s*[:=]"),
]


class ReciboInseguro(ValueError):
    pass


def mascarar(identificador: Any) -> str:
    s = re.sub(r"[^0-9A-Za-z]", "", str(identificador))
    return f"{s[:3]}****{s[-3:]}" if len(s) >= 7 else "****"


def agora_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def exigir_sanitizado(texto: str) -> None:
    for p in _PROIBIDOS:
        if p.search(texto):
            raise ReciboInseguro(f"recibo contém material proibido ({p.pattern[:20]}…); nada gravado")


def gravar(recibo: dict[str, Any], destino: Path) -> dict[str, Any]:
    linha = json.dumps(recibo, ensure_ascii=False, sort_keys=True, default=str)
    exigir_sanitizado(linha)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("a", encoding="utf-8") as f:
        f.write(linha + "\n")
    return recibo
