"""Versão do código que produz snapshots e decisões: sha256 do conteúdo dos arquivos-fonte.

Chave = caminho relativo a `volc_dil/` (não o basename: há vários `__init__.py`), então o hash
independe da máquina e do diretório do checkout. Entra no fingerprint de todo corte: mudar o
código que lê o fluxo ou decide muda o fingerprint, e o ledger mostra isso.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from volc_dil.contracts.fingerprint import sha256_de

_RAIZ = Path(__file__).resolve().parents[2]  # .../src/volc_dil

# o que pode mudar uma decisão shadow: o próprio pacote, o contrato de observação, a junção
# de identidade e as políticas herdadas que as baselines reaproveitam
_FONTES = (
    "fundacao/shadow",
    "fundacao/observacao",
    "fundacao/identidade",
    "replay/politicas.py",
    "replay/motor.py",
    "contracts",
)


def _arquivos() -> list[Path]:
    saida: list[Path] = []
    for rel in _FONTES:
        p = _RAIZ / rel
        if p.is_file():
            saida.append(p)
        else:
            saida.extend(sorted(q for q in p.rglob("*.py") if "__pycache__" not in q.parts))
    return saida


@lru_cache(maxsize=1)
def versao_codigo() -> str:
    mapa = {}
    for p in _arquivos():
        mapa[p.relative_to(_RAIZ).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return sha256_de(mapa)
