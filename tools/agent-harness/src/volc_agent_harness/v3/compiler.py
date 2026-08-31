"""Mission Compiler: nenhum modelo é chamado antes de a missão compilar.

```text
mission source → schema → base/lineage → ownership discovery
  → gate compilation → baseline preflight → compiled mission → writer
```

Cada etapa pode recusar. Uma recusa aqui custa milissegundos; a mesma recusa
depois do writer custou 39 minutos na lane B3.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .failures import FailureClass, HarnessFailure
from .gate_compiler import ProducedPath, compile_gate_plan
from .gate_resolution import build_toolchain, resolve_mission_gates
from .ownership import build_proposal


@dataclass
class AcceptanceRef:
    """Aceite atômico. É a unidade de trabalho, não a tarefa inteira."""

    acceptance_id: str          # P04-T09-A2
    task_id: str                # P04-T09
    index: int                  # 2
    text: str
    already_proven: bool = False

    @staticmethod
    def parse(acceptance_id: str) -> tuple[str, int]:
        if "-A" not in acceptance_id:
            raise HarnessFailure(
                FailureClass.SPEC_ERROR,
                "acceptance_id fora do formato <TAREFA>-A<n>",
                detalhe=acceptance_id,
            )
        task, _, sufixo = acceptance_id.rpartition("-A")
        if not sufixo.isdigit():
            raise HarnessFailure(
                FailureClass.SPEC_ERROR,
                "índice do aceite não é numérico",
                detalhe=acceptance_id,
            )
        return task, int(sufixo)


def load_acceptances(
    roadmap: Mapping[str, Any], acceptance_ids: Sequence[str], *, proven: Sequence[str] = ()
) -> list[AcceptanceRef]:
    """Resolve cada acceptance_id contra o Roadmap. Aceite inexistente recusa a missão."""

    def acha(no: Any, alvo: str) -> Mapping[str, Any] | None:
        if isinstance(no, Mapping):
            if no.get("id") == alvo:
                return no
            for v in no.values():
                r = acha(v, alvo)
                if r is not None:
                    return r
        elif isinstance(no, list):
            for v in no:
                r = acha(v, alvo)
                if r is not None:
                    return r
        return None

    provados = set(proven)
    refs: list[AcceptanceRef] = []
    for aid in acceptance_ids:
        task_id, indice = AcceptanceRef.parse(aid)
        tarefa = acha(roadmap, task_id)
        if tarefa is None:
            raise HarnessFailure(
                FailureClass.SPEC_ERROR, "tarefa inexistente no Roadmap", detalhe=task_id
            )
        criterios = tarefa.get("acceptance") or []
        if not 1 <= indice <= len(criterios):
            raise HarnessFailure(
                FailureClass.SPEC_ERROR,
                f"aceite {indice} não existe em {task_id} (a tarefa tem {len(criterios)})",
                detalhe=aid,
            )
        refs.append(
            AcceptanceRef(
                acceptance_id=aid,
                task_id=task_id,
                index=indice,
                text=criterios[indice - 1],
                already_proven=aid in provados,
            )
        )
    return refs


@dataclass
class CompiledMission:
    mission_id: str
    base_sha: str
    lineage_root: str | None
    acceptance_ids: list[str]
    regression_acceptance_ids: list[str]
    existing_files: list[str]
    read_paths: list[str]
    ownership_envelope: list[str]
    writable_paths: list[str]
    optional_writable_paths: list[str]
    produced_paths: list[dict[str, Any]]
    gate_plan: dict[str, Any]
    gates_runnable_before_writer: list[int]
    gates_depending_on_produced: list[int]
    reused_evidence: list[dict[str, Any]] = field(default_factory=list)
    invalidated_evidence: list[dict[str, Any]] = field(default_factory=list)
    routed_models: dict[str, str] = field(default_factory=dict)
    privacy_class: str = "local_code_only"
    write_authority: str = "single_writer"
    retry_policy: dict[str, Any] = field(default_factory=dict)
    integration_policy: str = "human_merge_only"

    def as_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "base_sha": self.base_sha,
            "lineage_root": self.lineage_root,
            "acceptance_ids": self.acceptance_ids,
            "regression_acceptance_ids": self.regression_acceptance_ids,
            "existing_files": self.existing_files,
            "read_paths": self.read_paths,
            "ownership_envelope": self.ownership_envelope,
            "writable_paths": self.writable_paths,
            "optional_writable_paths": self.optional_writable_paths,
            "produced_paths": self.produced_paths,
            "gate_plan": self.gate_plan,
            "gates_runnable_before_writer": self.gates_runnable_before_writer,
            "gates_depending_on_produced": self.gates_depending_on_produced,
            "reused_evidence": self.reused_evidence,
            "invalidated_evidence": self.invalidated_evidence,
            "routed_models": self.routed_models,
            "privacy_class": self.privacy_class,
            "write_authority": self.write_authority,
            "retry_policy": self.retry_policy,
            "integration_policy": self.integration_policy,
        }


def compile_mission(
    *,
    mission: Any,
    tree: Path,
    roadmap: Mapping[str, Any],
    acceptance_ids: Sequence[str],
    symbols: Sequence[str] = (),
    search_roots: Sequence[str] = (),
    ownership_envelope: Sequence[str] = (),
    produced_paths: Sequence[Mapping[str, Any]] = (),
    proven_acceptances: Sequence[str] = (),
    other_lane_paths: Sequence[str] = (),
) -> CompiledMission:
    """Compila a missão. Levanta ``HarnessFailure`` em vez de gastar writer."""

    if not acceptance_ids:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "missão sem acceptance_ids: não dá para saber o que ela fecha",
            detalhe=getattr(mission, "mission_id", "?"),
        )

    aceites = load_acceptances(roadmap, acceptance_ids, proven=proven_acceptances)

    ja_provados = [a.acceptance_id for a in aceites if a.already_proven]
    if ja_provados:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "missão reabre aceite já provado sem declarar regressão",
            detalhe=", ".join(ja_provados),
            reproducao="declare-o em regression_acceptance_ids ou remova-o de acceptance_ids",
        )

    writer = next(
        (w for w in getattr(mission, "workers", []) if getattr(w, "role", "") == "writer"),
        None,
    )
    declarados = list(getattr(writer, "writable_paths", []) or []) if writer else []

    proposta = build_proposal(
        tree=tree,
        acceptance_ids=acceptance_ids,
        symbols=symbols,
        search_roots=search_roots,
        envelope=ownership_envelope,
        declared_writable=declarados,
        produced_paths=list(produced_paths),
        other_lane_paths=other_lane_paths,
    )
    if proposta["blocks_writer"]:
        raise HarnessFailure(
            FailureClass.OWNERSHIP_ERROR,
            "call site material fora do envelope autorizado",
            detalhe=", ".join(proposta["outside_envelope"][:6]),
            reproducao="revise ownership_envelope ou reduza o escopo do aceite",
            evidencia={"proposal": proposta},
        )

    produzidos = [ProducedPath(path=p["path"], required=bool(p.get("required", True)))
                  for p in produced_paths]
    # `volc-harness compile` é entrypoint produtivo: ele resolve pelo compilador
    # TIPADO, igual ao runtime. Manter aqui a compilação por argv livre daria ao
    # operador um "compila" que não prova o que o `run` vai fazer.
    resolvidos = resolve_mission_gates(
        gates=getattr(mission, "gates", []),
        tree=tree,
        toolchain=build_toolchain(repo=tree, worktree=tree),
        produced_paths=list(produced_paths),
    )
    plano = {
        "total": len(resolvidos),
        "runnable_before_writer": [g.index for g in resolvidos
                                   if g.runnable_before_writer],
        "depends_on_produced": [g.index for g in resolvidos
                                if not g.runnable_before_writer],
        "produced_paths": [{"path": p.path, "required": p.required} for p in produzidos],
        "gates": [g.as_dict() for g in resolvidos],
    }

    # Aceites já provados desta tarefa viram regressões obrigatórias.
    tarefas = {a.task_id for a in aceites}
    regressoes = sorted(
        aid for aid in proven_acceptances
        if any(aid.startswith(t + "-A") for t in tarefas)
    )

    return CompiledMission(
        mission_id=getattr(mission, "mission_id", "?"),
        base_sha=getattr(mission, "base_ref", ""),
        lineage_root=getattr(mission, "lineage_root_sha", None),
        acceptance_ids=list(acceptance_ids),
        regression_acceptance_ids=regressoes,
        existing_files=sorted(proposta["writable_paths"]),
        read_paths=proposta["read_paths"],
        ownership_envelope=list(ownership_envelope),
        writable_paths=proposta["writable_paths"],
        optional_writable_paths=proposta["optional_writable_paths"],
        produced_paths=[{"path": p.path, "required": p.required} for p in produzidos],
        gate_plan=plano,
        gates_runnable_before_writer=plano["runnable_before_writer"],
        gates_depending_on_produced=plano["depends_on_produced"],
        routed_models={
            w.id: f"{w.provider}/{getattr(w, 'model', '?')}"
            for w in getattr(mission, "workers", [])
        },
        retry_policy={
            "SPEC_ERROR": 0, "OWNERSHIP_ERROR": 0, "INFRASTRUCTURE_ERROR": 0,
            "BASELINE_ERROR": 0, "AUTHORIZATION_BLOCK": 0,
            "MERIT_FAILURE": 2, "REVIEW_FINDING": 2,
            "TIMEOUT": 1, "TRANSIENT_PROVIDER_ERROR": 1,
        },
    )
