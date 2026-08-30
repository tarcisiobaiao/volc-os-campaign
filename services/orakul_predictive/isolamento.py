"""Guarda de isolamento: o Core V1 é offline, sem .env, sem rede, sem mutate."""

from __future__ import annotations

import ast
from pathlib import Path

from .excecoes import IsolamentoViolado

IMPORTS_PROIBIDOS = frozenset({
    "httpx",
    "requests",
    "urllib",
    "urllib.request",
    "urllib3",
    "aiohttp",
    "socket",
    "supabase",
    "dotenv",
    "python_dotenv",
    "google.ads",
    "openai",
    "anthropic",
})

ARQUIVOS_ENV_PROIBIDOS = (".env", ".env.server", ".env.local", ".env.n8n.local")


def auditar_fonte_pacote(raiz: Path | None = None) -> None:
    pasta = Path(raiz) if raiz else Path(__file__).resolve().parent
    ofensores: list[str] = []
    for caminho in sorted(pasta.glob("*.py")):
        arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                for alias in no.names:
                    raiz_mod = alias.name.split(".")[0]
                    if alias.name in IMPORTS_PROIBIDOS or raiz_mod in IMPORTS_PROIBIDOS:
                        ofensores.append(f"{caminho.name}: import {alias.name}")
            elif isinstance(no, ast.ImportFrom) and no.module:
                raiz_mod = no.module.split(".")[0]
                if no.module in IMPORTS_PROIBIDOS or raiz_mod in IMPORTS_PROIBIDOS:
                    ofensores.append(f"{caminho.name}: from {no.module}")
            elif isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "open":
                if no.args and isinstance(no.args[0], ast.Constant) and isinstance(no.args[0].value, str):
                    nome = no.args[0].value
                    if any(nome.endswith(env) or nome == env for env in ARQUIVOS_ENV_PROIBIDOS):
                        ofensores.append(f"{caminho.name}: open({nome})")
    if ofensores:
        raise IsolamentoViolado("; ".join(ofensores))


def recusar_mutacao_externa(mutacao_campanha: bool) -> None:
    if mutacao_campanha:
        raise IsolamentoViolado("núcleo preditivo recusa mutação de campanha")
