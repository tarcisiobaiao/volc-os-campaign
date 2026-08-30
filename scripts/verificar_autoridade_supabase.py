#!/usr/bin/env python3
"""Falha fechado quando o VOLC O.S. aponta para um Supabase não oficial.

O gate lê somente as duas URLs públicas de configuração. Chaves e demais
segredos não são carregados nem impressos.
"""

from __future__ import annotations

import sys
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
URL_OFICIAL = "https://database.agenciavolc.com.br"
TEMPLATES = {
    RAIZ / ".env.example": ("VITE_SUPABASE_URL",),
    RAIZ / ".env.server.example": ("SUPABASE_URL",),
    RAIZ / "backend/.env.example": ("SUPABASE_URL",),
}
AMBIENTES_LOCAIS = {
    RAIZ / ".env": ("VITE_SUPABASE_URL", "SUPABASE_URL"),
    RAIZ / ".env.local": ("VITE_SUPABASE_URL", "SUPABASE_URL"),
    RAIZ / ".env.server": ("SUPABASE_URL",),
    RAIZ / "backend/.env": ("SUPABASE_URL",),
    RAIZ / "backend/.env.local": ("SUPABASE_URL",),
}


def _valor(linha: str, nome: str) -> str | None:
    limpa = linha.strip()
    if not limpa or limpa.startswith("#") or "=" not in limpa:
        return None
    chave, bruto = limpa.split("=", 1)
    if chave.strip() != nome:
        return None
    return bruto.strip().strip('"\'').rstrip("/")


def ler_variavel(caminho: Path, nome: str) -> str | None:
    try:
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for linha in linhas:
        encontrado = _valor(linha, nome)
        if encontrado is not None:
            return encontrado
    return None


def conferir() -> list[str]:
    erros: list[str] = []
    for caminho, nomes in TEMPLATES.items():
        for nome in nomes:
            valor = ler_variavel(caminho, nome)
            if valor != URL_OFICIAL:
                relativo = caminho.relative_to(RAIZ)
                erros.append(f"{relativo}: {nome} deve apontar para o Supabase oficial")

    for caminho, nomes in AMBIENTES_LOCAIS.items():
        if not caminho.exists():
            continue
        for nome in nomes:
            valor = ler_variavel(caminho, nome)
            if valor is not None and valor != URL_OFICIAL:
                relativo = caminho.relative_to(RAIZ)
                erros.append(f"{relativo}: {nome} aponta para outro Supabase")
    return erros


def main() -> int:
    erros = conferir()
    if erros:
        print("ERRO: autoridade de dados divergente:", file=sys.stderr)
        for erro in erros:
            print(f"- {erro}", file=sys.stderr)
        print(f"Autoridade exigida: {URL_OFICIAL}", file=sys.stderr)
        return 1
    print(f"✓ Supabase oficial: {URL_OFICIAL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
