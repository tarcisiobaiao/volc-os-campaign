#!/usr/bin/env python3
"""Gera o manifesto n8n sanitizado, rastreado e reproduzível.

Motivo de existir: ``gerar_grafo_volc_os.py`` montava os nós ``n8n:*`` lendo
``inventario-n8n/flows/*.meta.json`` — diretório **gitignored**, ausente de
qualquer worktree limpa e da branch oficial. O build ficava dependente de uma
máquina específica e as 19 arestas da curadoria pendiam no vazio.

Este script tem UMA operação local e explícita (``--source-dir``) que produz um
manifesto rastreado. O build canônico do grafo lê **somente** o manifesto; não há
fallback para o diretório local.

A seleção é por ALLOWLIST. Campo desconhecido faz a geração falhar, em vez de
vazar por omissão.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = 1
SOURCE_KIND = "n8n_legacy_metadata"

# Campos que o .meta.json pode trazer. Desconhecido => erro.
CAMPOS_CONHECIDOS = {
    "id", "nome", "slug", "camada", "ativo", "nos",
    "atualizado_em", "gatilhos", "tipos_de_no", "nos_com_codigo", "linhas_de_codigo",
}

# Allowlist do manifesto: o que efetivamente é serializado.
CAMPOS_PERMITIDOS = {
    "slug", "nome", "camada", "ativo", "nos", "linhas_de_codigo",
    "atualizado_em", "tipos_de_no", "gatilhos_tipos", "source_sha256", "source_kind",
}

# Recusados por conterem identificador, segredo ou lógica proprietária.
CAMPOS_RECUSADOS = {
    "id": "ID real do workflow n8n; identificador operacional sensível e desnecessário ao grafo",
    "gatilhos": "carrega o caminho do webhook (UUID); só o TIPO do gatilho é preservado",
    "nos_com_codigo": "nomes de nós e volume por nó revelam lógica proprietária; só o agregado é preservado",
}

PADROES_DE_SEGREDO = [
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "UUID"),
    (re.compile(r"https?://", re.I), "URL"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{20,}"), "JWT"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "e-mail"),
    (re.compile(r"(?:api[_-]?key|token|secret|password|senha|bearer)\s*[:=]", re.I), "credencial"),
    (re.compile(r"\b(?=[A-Za-z0-9]{16,17}\b)(?=[^\s]*[a-z])(?=[^\s]*[A-Z])(?=[^\s]*[0-9])[A-Za-z0-9]+\b"), "ID de workflow n8n"),
    (re.compile(r"(?:^|[\s\"'])/(?:Users|home|root|private)/", re.I), "caminho absoluto"),
]

# Gatilhos são "tipo:detalhe"; só o tipo sobrevive.
# Enumerados a partir do inventário real; qualquer tipo novo faz a geração falhar,
# forçando decisão explícita em vez de vazamento por omissão.
TIPOS_DE_GATILHO = {
    "webhook", "schedule", "manualtrigger", "formtrigger",
    "clickuptrigger", "executeworkflowtrigger",
}


class ManifestoInvalido(RuntimeError):
    """A geração falha fechado em vez de emitir manifesto suspeito."""


def _tipo_de_gatilho(bruto: str) -> str:
    tipo = str(bruto).split(":", 1)[0].strip().lower()
    if tipo not in TIPOS_DE_GATILHO:
        raise ManifestoInvalido(f"tipo de gatilho não previsto: {tipo!r}")
    return tipo


def sanitizar(meta: dict, *, origem: Path) -> dict:
    desconhecidos = set(meta) - CAMPOS_CONHECIDOS
    if desconhecidos:
        raise ManifestoInvalido(
            f"{origem.name}: campo fora do schema conhecido: {sorted(desconhecidos)}. "
            "Atualize a allowlist deliberadamente em vez de deixar passar."
        )
    for obrigatorio in ("slug", "nome", "camada"):
        if not meta.get(obrigatorio):
            raise ManifestoInvalido(f"{origem.name}: campo obrigatório ausente: {obrigatorio}")
    registro = {
        "slug": str(meta["slug"]),
        "nome": str(meta["nome"]),
        "camada": str(meta["camada"]),
        "ativo": bool(meta.get("ativo", False)),
        "nos": int(meta.get("nos", 0)),
        "linhas_de_codigo": int(meta.get("linhas_de_codigo", 0)),
        "atualizado_em": str(meta.get("atualizado_em", "")),
        "tipos_de_no": sorted({str(t) for t in (meta.get("tipos_de_no") or [])}),
        "gatilhos_tipos": sorted({_tipo_de_gatilho(g) for g in (meta.get("gatilhos") or [])}),
        "source_sha256": hashlib.sha256(origem.read_bytes()).hexdigest(),
        "source_kind": SOURCE_KIND,
    }
    extra = set(registro) - CAMPOS_PERMITIDOS
    if extra:
        raise ManifestoInvalido(f"registro produziu campo fora da allowlist: {sorted(extra)}")
    return registro


def auditar_segredos(registro: dict) -> None:
    """Recusa a geração, em vez de redigir silenciosamente."""

    for campo, valor in registro.items():
        if campo == "source_sha256":
            continue  # hash é determinístico e não secreto
        texto = json.dumps(valor, ensure_ascii=False)
        for padrao, rotulo in PADROES_DE_SEGREDO:
            if padrao.search(texto):
                raise ManifestoInvalido(
                    f"{registro.get('slug')}: padrão sensível ({rotulo}) em {campo!r}; geração recusada"
                )


def construir(source_dir: Path) -> dict:
    if not source_dir.is_dir():
        raise ManifestoInvalido(f"--source-dir inexistente: {source_dir}")
    arquivos = sorted(source_dir.glob("*.meta.json"), key=lambda p: p.name)
    if not arquivos:
        raise ManifestoInvalido(f"nenhum *.meta.json em {source_dir}")
    registros, vistos = [], {}
    for arq in arquivos:
        r = sanitizar(json.loads(arq.read_text()), origem=arq)
        auditar_segredos(r)
        if r["slug"] in vistos:
            raise ManifestoInvalido(f"slug duplicado: {r['slug']} ({vistos[r['slug']]} e {arq.name})")
        vistos[r["slug"]] = arq.name
        registros.append(r)
    registros.sort(key=lambda r: r["slug"])  # ordem estável, independente da ordem do disco
    return {
        "$schema_version": SCHEMA_VERSION,
        "source_kind": SOURCE_KIND,
        "campos_permitidos": sorted(CAMPOS_PERMITIDOS),
        "campos_recusados": CAMPOS_RECUSADOS,
        "total": len(registros),
        "workflows": registros,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-dir", required=True, type=Path,
                   help="diretório com os *.meta.json autorizados; nunca descoberto no disco")
    p.add_argument("--out", type=Path,
                   default=Path("docs/volc-os-graph/inventario-n8n-sanitizado.json"))
    p.add_argument("--check", action="store_true",
                   help="não escreve; falha se o manifesto no disco divergir do que seria gerado")
    a = p.parse_args()
    try:
        manifesto = construir(a.source_dir)
    except ManifestoInvalido as exc:
        print(f"recusado: {exc}", file=sys.stderr)
        return 2
    texto = json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if a.check:
        atual = a.out.read_text() if a.out.exists() else ""
        if atual != texto:
            print("manifesto no disco diverge da geração determinística", file=sys.stderr)
            return 1
        print(f"manifesto atual: {manifesto['total']} workflows")
        return 0
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(texto)
    print(f"manifesto gerado: {a.out} ({manifesto['total']} workflows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
