"""Compilação em duas fases.

Nem todo artefato existe antes do writer: testes novos, goldens e provas nascem
dele. Compilar tudo antes seria impossível; compilar tudo depois é o defeito que
custou 39 minutos na B3.

  * **prewriter** — base, lineage, autoridade, paths existentes e os gates que já
    dá para rodar. Nenhum modelo roda antes dela.
  * **postwriter** — artefatos produzidos, testes novos coletáveis e ownership
    efetivo. Nenhum gate caro roda antes dela.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .failures import FailureClass, HarnessFailure
from .gate_compiler import CompiledGate, ProducedPath, assert_pytest_collects, compile_gate


@dataclass
class PostWriterReport:
    produced_present: list[str] = field(default_factory=list)
    produced_missing: list[str] = field(default_factory=list)
    effective_paths: list[str] = field(default_factory=list)
    outside_ownership: list[str] = field(default_factory=list)
    collected_counts: dict[int, int] = field(default_factory=dict)
    gates_now_runnable: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "produced_present": self.produced_present,
            "produced_missing": self.produced_missing,
            "effective_paths": self.effective_paths,
            "outside_ownership": self.outside_ownership,
            "collected_counts": {str(k): v for k, v in self.collected_counts.items()},
            "gates_now_runnable": self.gates_now_runnable,
        }


def postwriter_compile(
    *,
    tree: Path,
    produced: Sequence[ProducedPath],
    changed_paths: Sequence[str],
    writable_paths: Sequence[str],
    gates: Sequence[Any],
    resolved: Sequence[Any] | None = None,
    env: dict[str, str] | None = None,
    collect: bool = True,
) -> PostWriterReport:
    """Segunda fase. Roda depois do writer e ANTES de qualquer gate caro.

    ``resolved`` é o caminho tipado: quando o chamador já resolveu os gates pelo
    compilador (o caso do runtime), recompilar por ``argv`` seria reintroduzir
    exatamente a resolução livre que G1a refutou. O parâmetro ``gates`` continua
    servindo o caminho legado de schema 2.
    """

    presentes, faltando = [], []
    for p in produced:
        if (tree / p.path).exists():
            presentes.append(p.path)
        elif p.required:
            faltando.append(p.path)
    if faltando:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "writer não produziu artefato declarado como obrigatório",
            detalhe=", ".join(faltando),
            reproducao=f"ls {faltando[0]}",
            evidencia={"produced_missing": faltando},
        )

    fora = [
        c for c in changed_paths
        if not any(c == w or c.startswith(w.rstrip("/") + "/") for w in writable_paths)
    ]
    if fora:
        raise HarnessFailure(
            FailureClass.OWNERSHIP_ERROR,
            "writer alterou caminho fora do ownership efetivo",
            detalhe=", ".join(fora[:6]),
            evidencia={"outside": fora},
        )

    recompilados = list(resolved) if resolved is not None else [
        compile_gate(
            index=i,
            argv=g.argv if hasattr(g, "argv") else g["argv"],
            timeout_seconds=getattr(g, "timeout_seconds", 600),
            tree=tree,
            produced=produced,
        )
        for i, g in enumerate(gates, start=1)
    ]
    contagens: dict[int, int] = {}
    if collect:
        for gate in recompilados:
            if gate.kind == "pytest":
                contagens[gate.index] = assert_pytest_collects(gate, tree=tree, env=env)

    return PostWriterReport(
        produced_present=presentes,
        produced_missing=[],
        effective_paths=list(changed_paths),
        outside_ownership=[],
        collected_counts=contagens,
        gates_now_runnable=[g.index for g in recompilados],
    )
