#!/usr/bin/env python3
"""Falha fechado se surgir um segundo cliente da AdsPower Local API.

Autoridade canônica única de P03-T11: ``tools/adspower-broker/``.

O único consumidor VOLC permitido fora dessa árvore é
``backend/app/visual_proof/infraestrutura.py``, e somente como cliente do
broker VOLC (``VOLC_BROKER_URL`` + ``POST /v1/operacoes``). Ele não fala com a
Local API do AdsPower.

Uso::

    python3 scripts/verificar_autoridade_unica_adspower.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]

AUTORIDADE = "tools/adspower-broker"
CLIENTE_VOLC = "backend/app/visual_proof/infraestrutura.py"
PACOTE_REMOVIDO = "backend/app/asset_vault/broker"
TESTE_REMOVIDO = "backend/tests/test_cofre_broker.py"
PACOTE_HERMES = "docs/closure/hermes-asset-vault-organic-access-v1"

RAIZES_DE_VARREDURA = ("backend", "src", "tools", "scripts", "deploy")
IGNORAR_DIR = {
    ".git",
    "node_modules",
    "dist",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "evidence",
    "coverage",
}
EXTENSOES_CODIGO = {".py", ".ts", ".tsx", ".mjs", ".js", ".cjs", ".sh"}

MARCADORES_LOCAL_API = (
    "/api/v1/browser/",
    "/api/v1/user/list",
    "/api/v1/group/list",
    "local.adspower.net",
)
CATALOGO_CONCORRENTE = (
    "inventario_perfis",
    "inventario_grupos",
    "cofre-broker-adspower",
)
IMPORT_REMOVIDO = (
    "app.asset_vault.broker",
    "app/asset_vault/broker",
)
CLI_CONCORRENTE = (
    "python3 -m app.asset_vault.broker",
    "python -m app.asset_vault.broker",
    "-m app.asset_vault.broker",
)
DECLARACAO_TAREFA = re.compile(r"""TAREFA\s*=\s*['"]P03-T11['"]""")
RESOLUCAO_SEGREDO = re.compile(
    r"""(?:\bop\s+read\b|\bop\s+run\b|subprocess[^\n]{0,80}\bop\b)""",
    re.IGNORECASE,
)
BEARER = re.compile(r"\bBearer\b")
SIDECAR_DIR = re.compile(r"(?:adspower.*broker|broker.*adspower)", re.IGNORECASE)
TOKENS_SUPERSESSAO = (
    "CANDIDATO NÃO INTEGRADO",
    "CANDIDATO NAO INTEGRADO",
    "SUPERADO",
)


def _posix(caminho: Path, raiz: Path) -> str:
    return caminho.resolve().relative_to(raiz.resolve()).as_posix()


def _permitido_para_marcadores(rel: str) -> bool:
    if rel == AUTORIDADE or rel.startswith(AUTORIDADE + "/"):
        return True
    if rel == "backend/app/visual_proof/dominio.py":
        return True
    if rel.startswith("backend/tests/test_adspower_broker"):
        return True
    if rel.startswith("backend/tests/test_visual_proof_"):
        return True
    if rel == "scripts/provar_visual_proof_hermetico.py":
        return True
    if rel == "scripts/verificar_autoridade_unica_adspower.py":
        return True
    if rel == "scripts/tests/test_autoridade_unica_adspower.py":
        return True
    if rel.startswith("docs/"):
        return True
    return False


def _permitido_para_import_removido(rel: str) -> bool:
    return rel in {
        "scripts/verificar_autoridade_unica_adspower.py",
        "scripts/tests/test_autoridade_unica_adspower.py",
    } or rel.startswith("docs/")


def _iterar_arquivos(raiz: Path):
    for nome in RAIZES_DE_VARREDURA:
        base = raiz / nome
        if not base.exists():
            continue
        for caminho in base.rglob("*"):
            if not caminho.is_file():
                continue
            if any(parte in IGNORAR_DIR for parte in caminho.parts):
                continue
            yield caminho


def _ler(caminho: Path) -> str:
    try:
        return caminho.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _conferir_existencia(raiz: Path) -> list[str]:
    erros: list[str] = []
    if (raiz / PACOTE_REMOVIDO).exists():
        erros.append(
            f"{PACOTE_REMOVIDO}: segundo candidato de autoridade AdsPower "
            "presente; foi removido na adjudicação"
        )
    if (raiz / TESTE_REMOVIDO).exists():
        erros.append(
            f"{TESTE_REMOVIDO}: teste exclusivo do candidato removido ainda existe"
        )
    if not (raiz / AUTORIDADE).is_dir():
        erros.append(
            f"{AUTORIDADE}: autoridade canônica de P03-T11 ausente"
        )
    return erros


def _conferir_sidecars(raiz: Path) -> list[str]:
    erros: list[str] = []
    tools = raiz / "tools"
    if tools.is_dir():
        for filho in tools.iterdir():
            if not filho.is_dir():
                continue
            rel = _posix(filho, raiz)
            if rel == AUTORIDADE:
                continue
            if SIDECAR_DIR.search(filho.name):
                erros.append(
                    f"{rel}: sidecar/CLI concorrente da AdsPower fora de {AUTORIDADE}/"
                )
    return erros


def _conferir_cliente_volc(raiz: Path) -> list[str]:
    erros: list[str] = []
    caminho = raiz / CLIENTE_VOLC
    if not caminho.is_file():
        return erros
    texto = _ler(caminho)
    if "VOLC_BROKER_URL" not in texto or "/v1/operacoes" not in texto:
        erros.append(
            f"{CLIENTE_VOLC}: cliente VOLC deve falar com o broker "
            "(VOLC_BROKER_URL + POST /v1/operacoes)"
        )
    for marcador in MARCADORES_LOCAL_API:
        if marcador in texto:
            erros.append(
                f"{CLIENTE_VOLC}: cliente VOLC não pode falar com a Local API "
                f"({marcador})"
            )
    return erros


def _conferir_codigo(raiz: Path) -> list[str]:
    erros: list[str] = []
    for caminho in _iterar_arquivos(raiz):
        if caminho.suffix not in EXTENSOES_CODIGO:
            continue
        rel = _posix(caminho, raiz)
        texto = _ler(caminho)
        if not texto:
            continue

        if not _permitido_para_import_removido(rel):
            for padrao in IMPORT_REMOVIDO + CLI_CONCORRENTE:
                if padrao in texto:
                    erros.append(
                        f"{rel}: referência ao pacote removido ({padrao})"
                    )

        if DECLARACAO_TAREFA.search(texto) and not rel.startswith(AUTORIDADE + "/"):
            erros.append(
                f"{rel}: declaração TAREFA/P03-T11 fora de {AUTORIDADE}/"
            )

        if _permitido_para_marcadores(rel):
            continue

        for marcador in MARCADORES_LOCAL_API + CATALOGO_CONCORRENTE:
            if marcador in texto:
                erros.append(
                    f"{rel}: cliente/catálogo AdsPower fora da fronteira "
                    f"autorizada ({marcador})"
                )

        if BEARER.search(texto) and any(m in texto for m in MARCADORES_LOCAL_API):
            erros.append(
                f"{rel}: Bearer combinado com endpoint da Local API fora de "
                f"{AUTORIDADE}/"
            )

        if RESOLUCAO_SEGREDO.search(texto) and any(
            m in texto for m in MARCADORES_LOCAL_API
        ):
            erros.append(
                f"{rel}: resolução/consumo de segredo junto da Local API fora de "
                f"{AUTORIDADE}/broker/segredo.py"
            )
    return erros


def _conferir_hermes(raiz: Path) -> list[str]:
    erros: list[str] = []
    pasta = raiz / PACOTE_HERMES
    if not pasta.is_dir():
        return erros
    for caminho in pasta.rglob("*"):
        if not caminho.is_file():
            continue
        texto = _ler(caminho)
        if PACOTE_REMOVIDO not in texto and "app.asset_vault.broker" not in texto:
            continue
        if not any(token in texto for token in TOKENS_SUPERSESSAO):
            rel = _posix(caminho, raiz)
            erros.append(
                f"{rel}: cita o candidato removido sem nota inequívoca de "
                "supersessão (CANDIDATO NÃO INTEGRADO/SUPERADO)"
            )
    return erros


def conferir(raiz: Path | None = None) -> list[str]:
    alvo = raiz or RAIZ
    erros: list[str] = []
    erros.extend(_conferir_existencia(alvo))
    erros.extend(_conferir_sidecars(alvo))
    erros.extend(_conferir_cliente_volc(alvo))
    erros.extend(_conferir_codigo(alvo))
    erros.extend(_conferir_hermes(alvo))
    # Determinístico: primeira ocorrência de cada mensagem.
    vistos: set[str] = set()
    unicos: list[str] = []
    for erro in erros:
        if erro not in vistos:
            vistos.add(erro)
            unicos.append(erro)
    return unicos


def main() -> int:
    erros = conferir()
    if erros:
        print("ERRO: autoridade AdsPower duplicada ou fronteira violada:", file=sys.stderr)
        for erro in erros:
            print(f"- {erro}", file=sys.stderr)
        print(
            f"Autoridade exigida: {AUTORIDADE}/ "
            f"(cliente VOLC: {CLIENTE_VOLC})",
            file=sys.stderr,
        )
        return 1
    print(
        f"✓ autoridade AdsPower única: {AUTORIDADE}/ "
        f"(cliente VOLC: {CLIENTE_VOLC})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
