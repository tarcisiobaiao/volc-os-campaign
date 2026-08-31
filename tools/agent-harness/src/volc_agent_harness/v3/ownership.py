"""Descoberta de ownership por call site real, não por inferência de nome.

A lane A1 falhou porque a missão declarou ``volc_ads/subir.py`` como writable,
mas o builder Demand Gen vive em ``volc_ads/campanha/``. A A2 falhou porque
``backend/app/trafego/projecao.py`` serializa o selo e ficou de fora. Nos dois
casos o writer produziu trabalho correto e a guarda recusou — o defeito estava
em quem escreveu a missão.

Aqui o ownership nasce de uma varredura determinística: quem importa, quem
chama, quem constrói e quem serializa os símbolos que o aceite cita.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence


@dataclass
class OwnershipEntry:
    symbol: str
    path: str
    relation: str
    access: str  # read_only | writable | optional_writable | produced
    justification: str
    evidence: str  # file:line
    confidence: float
    collides_with: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "path": self.path,
            "relation": self.relation,
            "access": self.access,
            "justification": self.justification,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "collides_with": self.collides_with,
        }


# Ordem = força. A relação MAIS FORTE encontrada no arquivo é a que vale: um
# `import` na linha 1 não pode esconder uma construção na linha 4 — foi
# exatamente esse tipo de leitura rasa que deixou volc_ads/campanha/ fora do
# ownership na lane A1.
_RELACOES = (
    ("definicao", r"^\s*(?:class|def|async def)\s+{sym}\b"),
    ("construcao", r"\b{sym}\s*\("),
    ("serializacao", r"\.{sym}\b"),
    ("anotacao", r":\s*{sym}\b"),
    ("import", r"^\s*(?:from|import)\b.*\b{sym}\b"),
)
_FORCA = {nome: len(_RELACOES) - i for i, (nome, _) in enumerate(_RELACOES)}


def discover(
    *,
    tree: Path,
    symbols: Sequence[str],
    search_roots: Sequence[str],
    envelope: Sequence[str],
    exclude_globs: Sequence[str] = (".agent-worktrees", "node_modules", "__pycache__", ".git"),
) -> list[OwnershipEntry]:
    """Varre ``search_roots`` procurando cada símbolo e classifica a relação."""

    entradas: list[OwnershipEntry] = []
    for simbolo in symbols:
        for raiz in search_roots:
            base = tree / raiz
            if not base.exists():
                continue
            alvos = [base] if base.is_file() else sorted(
                p for p in base.rglob("*")
                if p.is_file()
                and p.suffix in {".py", ".ts", ".tsx"}
                and not any(x in p.parts for x in exclude_globs)
            )
            for arquivo in alvos:
                try:
                    linhas = arquivo.read_text(encoding="utf-8", errors="ignore").splitlines()
                except OSError:
                    continue
                melhor: tuple[str, int] | None = None
                for numero, linha in enumerate(linhas, start=1):
                    for nome_rel, padrao in _RELACOES:
                        if re.search(padrao.format(sym=re.escape(simbolo)), linha):
                            if melhor is None or _FORCA[nome_rel] > _FORCA[melhor[0]]:
                                melhor = (nome_rel, numero)
                            break
                if melhor is None:
                    continue
                nome_rel, numero = melhor
                rel_path = arquivo.relative_to(tree).as_posix()
                dentro = any(
                    rel_path == e or rel_path.startswith(e.rstrip("/") + "/")
                    for e in envelope
                )
                entradas.append(
                    OwnershipEntry(
                        symbol=simbolo,
                        path=rel_path,
                        relation=nome_rel,
                        access="writable" if dentro else "read_only",
                        justification=(
                            f"{nome_rel} de {simbolo}"
                            + ("" if dentro else " (fora do envelope autorizado)")
                        ),
                        evidence=f"{rel_path}:{numero}",
                        confidence=0.9 if nome_rel in {"definicao", "construcao"} else 0.6,
                    )
                )
    return entradas


def build_proposal(
    *,
    tree: Path,
    acceptance_ids: Sequence[str],
    symbols: Sequence[str],
    search_roots: Sequence[str],
    envelope: Sequence[str],
    declared_writable: Sequence[str] = (),
    produced_paths: Sequence[dict[str, Any]] = (),
    other_lane_paths: Sequence[str] = (),
) -> dict[str, Any]:
    """Produz o ``ownership-proposal.json``.

    Um caminho descoberto DENTRO do envelope autorizado é compilado sem nova
    confirmação humana. FORA do envelope, a missão para antes do writer — é
    exatamente a fronteira que separa "eu esqueci um arquivo" de "estou
    ampliando escopo por conta própria".
    """

    entradas = discover(
        tree=tree, symbols=symbols, search_roots=search_roots, envelope=envelope
    )
    for e in entradas:
        e.collides_with = [o for o in other_lane_paths if e.path == o or e.path.startswith(o.rstrip("/") + "/")]

    descobertos_writable = sorted({e.path for e in entradas if e.access == "writable"})
    fora_do_envelope = sorted({e.path for e in entradas if e.access == "read_only"})
    declarados = sorted(set(declared_writable))
    faltantes = [p for p in descobertos_writable if p not in declarados]

    # GUARDA: descoberta SUGERE, nunca concede escrita.
    #
    # `writable_paths` continua sendo exatamente o que a missão declarou. O que a
    # varredura encontrou dentro do envelope vai para `suggested_writable_paths`,
    # e só entra em `effective_writable_paths` quando o compilador recebe
    # `auto_accept_envelope=True` — decisão explícita, registrada no artefato.
    # Call site material fora do declarado bloqueia com código próprio.
    material_fora_do_declarado = [
        p for p in (descobertos_writable + fora_do_envelope)
        if p not in declarados and _e_material(entradas, p)
    ]
    fora_do_envelope_material = [
        p for p in fora_do_envelope if p not in declarados and _e_material(entradas, p)
    ]
    return {
        "acceptance_ids": list(acceptance_ids),
        "symbols": list(symbols),
        "ownership_envelope": list(envelope),
        "read_paths": fora_do_envelope,
        "declared_writable_paths": declarados,
        "writable_paths": declarados,
        "suggested_writable_paths": faltantes,
        "optional_writable_paths": faltantes,
        "produced_paths": list(produced_paths),
        "missing_from_declaration": faltantes,
        "outside_envelope": fora_do_envelope,
        "material_outside_declared": sorted(set(material_fora_do_declarado)),
        "requires_new_authorization": bool(fora_do_envelope_material),
        "blocks_writer": bool(fora_do_envelope_material),
        "collisions": sorted({c for e in entradas for c in e.collides_with}),
        "entries": [e.as_dict() for e in entradas],
    }


def _e_material(entradas: Iterable[OwnershipEntry], path: str) -> bool:
    """Uma anotação de tipo não bloqueia; definição e construção bloqueiam."""

    return any(
        e.path == path and e.relation in {"definicao", "construcao", "serializacao"}
        for e in entradas
    )
