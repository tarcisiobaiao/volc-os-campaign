"""Ponte para o backend do Volc OS — um só lugar que mexe em `sys.path`.

`volc_ads` roda a partir da raiz do repositório (`python -m volc_ads....`) e o
backend roda com `cwd=backend` (`uvicorn app.main:app`), então `app.*` não está
no caminho de importação daqui. Este módulo resolve isso em um lugar só, de
forma greppável, em vez de espalhar `sys.path.insert` por cada consumidor.

O que atravessa a ponte, e por que cada coisa mora do outro lado:

  app.llm.json_defensivo   parser defensivo de saída de LLM. Nasceu de uma
                           falha real (um `]` a mais do Gemini descartando 19k
                           tokens em 2 de 3 chamadas). Cópia única.
  app.motor_pautas         o motor de pautas validado. `volc_ads/pautador/`
                           era a TERCEIRA cópia dele e foi apagada; sobrou
                           `pautador/prompts/classificador_eixos.md`, que é o
                           único arquivo que não existia lá.

Importar daqui é deliberado: se um dia `volc_ads` virar pacote instalável, é
este arquivo que muda, e só ele.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
BACKEND = RAIZ / "backend"
PROMPTS = Path(__file__).resolve().parent / "pautador" / "prompts"


def _garantir_caminho() -> None:
    for p in (RAIZ, BACKEND):
        alvo = str(p)
        if alvo not in sys.path:
            sys.path.insert(0, alvo)


_garantir_caminho()


def _carregar_por_caminho(nome: str, caminho: Path):
    """Importa um módulo pelo arquivo, SEM acionar o `__init__` do pacote.

    `import app.llm.json_defensivo` executaria `app/llm/__init__.py`, que
    importa `app.config` e portanto `pydantic_settings` — arrastando a pilha
    inteira do backend para dentro de um parser que é só stdlib. O ganho de
    ter uma cópia única morreria no custo de dependência.

    Carregar pelo arquivo mantém as duas propriedades ao mesmo tempo: o
    backend continua fazendo `from app.llm.base import extract_json`, e
    `volc_ads` continua sem depender de nada além da stdlib.
    """
    spec = importlib.util.spec_from_file_location(nome, caminho)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"não consegui carregar {caminho}")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(nome, modulo)
    spec.loader.exec_module(modulo)
    return modulo


_json_defensivo = _carregar_por_caminho(
    "volc_ads._json_defensivo", BACKEND / "app" / "llm" / "json_defensivo.py"
)

extract_json = _json_defensivo.extract_json
repair_json_delimiters = _json_defensivo.repair_json_delimiters

__all__ = ["RAIZ", "BACKEND", "PROMPTS", "extract_json", "repair_json_delimiters"]
