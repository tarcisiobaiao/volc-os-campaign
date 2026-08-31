"""Integração real: o caminho de execução passa pelo V3, não ao lado dele.

Uma biblioteca V3 verde que nenhum launcher consome não protege nada. Este módulo
é o ponto único por onde uma missão atravessa compile → writer → postcompile →
gates → adjudicação → harvest, com o ledger registrando cada etapa e a taxonomia
classificando cada falha.

``volc-harness compile`` e ``volc-harness run --v3`` entram por aqui.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .baseline import BaselineRecord, assert_baseline_is_green, assert_no_regression, compare, measure
from .compiler import CompiledMission, compile_mission
from .failures import FailureClass, HarnessFailure, classify_exception, classify_gate_exit
from .gate_compiler import ProducedPath, assert_pytest_collects
from .harvest import Harvest, requires_writer, resume_base
from .heartbeat import HeartbeatEvent, HeartbeatSink
from .ledger import EvidenceLedger, digest_files, env_fingerprint
from .registry import WorktreeRegistry
from .schema_version import assert_compilable
from .two_phase import postwriter_compile
from .workspace import assert_no_destructive_intent, prepare


@dataclass
class PipelineArtifacts:
    run_dir: Path
    compiled_mission: dict[str, Any] | None = None
    gate_plan: dict[str, Any] | None = None
    ownership_proposal: dict[str, Any] | None = None
    baseline: list[dict[str, Any]] = field(default_factory=list)
    postwriter: dict[str, Any] | None = None
    gate_results: list[dict[str, Any]] = field(default_factory=list)
    adjudication: dict[str, Any] | None = None
    harvest: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def write(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        for nome, valor in (
            ("compiled-mission.json", self.compiled_mission),
            ("gate-plan.json", self.gate_plan),
            ("ownership-proposal.json", self.ownership_proposal),
            ("postwriter-report.json", self.postwriter),
            ("adjudication.json", self.adjudication),
            ("harvest.json", self.harvest),
            ("failure.json", self.failure),
        ):
            if valor is not None:
                (self.run_dir / nome).write_text(
                    json.dumps(valor, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        if self.baseline:
            (self.run_dir / "baseline.json").write_text(
                json.dumps(self.baseline, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        if self.evidence:
            (self.run_dir / "evidence.json").write_text(
                json.dumps(self.evidence, ensure_ascii=False, indent=2), encoding="utf-8"
            )


def prewriter_phase(
    *,
    mission_dict: Mapping[str, Any],
    mission_obj: Any,
    tree: Path,
    roadmap: Mapping[str, Any],
    run_dir: Path,
    ledger: EvidenceLedger | None = None,
    registry: WorktreeRegistry | None = None,
    sink: HeartbeatSink | None = None,
    proven_acceptances: Sequence[str] = (),
    auto_accept_envelope: bool = False,
) -> tuple[CompiledMission, PipelineArtifacts]:
    """Fase 1. Nenhum modelo roda antes desta função retornar."""

    art = PipelineArtifacts(run_dir=run_dir)
    if sink:
        sink.emit(HeartbeatEvent("pipeline", "compile", "active", 0, 0,
                                 last_material_event="iniciando compilação"))

    assert_compilable(mission_dict)

    for gate in mission_dict.get("gates", []):
        assert_no_destructive_intent(gate.get("argv", []))

    compilada = compile_mission(
        mission=mission_obj,
        tree=tree,
        roadmap=roadmap,
        acceptance_ids=mission_dict.get("acceptance_ids", []),
        symbols=mission_dict.get("ownership_symbols", []),
        search_roots=mission_dict.get("ownership_search_roots", []),
        ownership_envelope=mission_dict.get("ownership_envelope", []),
        produced_paths=mission_dict.get("produced_paths", []),
        proven_acceptances=proven_acceptances,
    )
    art.compiled_mission = compilada.as_dict()
    art.gate_plan = compilada.gate_plan
    art.write()
    return compilada, art


def run_baseline(
    *,
    compilada: CompiledMission,
    tree: Path,
    art: PipelineArtifacts,
    ledger: EvidenceLedger | None = None,
    env: dict[str, str] | None = None,
    runner: Callable[..., BaselineRecord] = measure,
) -> list[BaselineRecord]:
    """Mede os gates executáveis no base_ref. Baseline vermelho impede o início."""

    registros: list[BaselineRecord] = []
    for gate in art.gate_plan["gates"]:
        if gate["index"] not in compilada.gates_runnable_before_writer:
            continue
        registros.append(
            runner(gate_index=gate["index"], argv=gate["argv"], tree=tree, env=env)
        )
    art.baseline = [r.as_dict() for r in registros]
    art.write()
    assert_baseline_is_green(registros)
    if ledger is not None:
        for r in registros:
            ledger.record(
                acceptance_id=compilada.acceptance_ids[0],
                kind="baseline_gate",
                base_sha=compilada.base_sha,
                run_id=art.run_dir.name,
                command=" ".join(r.argv),
                cwd=str(tree),
                production_digest="baseline",
                test_digest="baseline",
                exit_code=r.exit_code,
                counts={"passed": r.passed, "failed": r.failed},
            )
    return registros


def postwriter_phase(
    *,
    compilada: CompiledMission,
    tree: Path,
    changed_paths: Sequence[str],
    art: PipelineArtifacts,
    gates: Sequence[Any],
    env: dict[str, str] | None = None,
    collect: bool = True,
) -> dict[str, Any]:
    """Fase 2. Nenhum gate caro roda antes desta função retornar."""

    relatorio = postwriter_compile(
        tree=tree,
        produced=[ProducedPath(p["path"], p.get("required", True))
                  for p in compilada.produced_paths],
        changed_paths=changed_paths,
        writable_paths=compilada.writable_paths,
        gates=gates,
        env=env,
        collect=collect,
    )
    art.postwriter = relatorio.as_dict()
    art.write()
    return art.postwriter


def classify_and_record(
    *, exc: BaseException, art: PipelineArtifacts, sink: HeartbeatSink | None = None
) -> dict[str, Any]:
    """Toda saída de erro do pipeline passa pela taxonomia."""

    if isinstance(exc, HarnessFailure):
        registro = exc.as_dict()
    else:
        classe = classify_exception(exc)
        registro = HarnessFailure(classe, str(exc)[:300]).as_dict()
    art.failure = registro
    art.write()
    if sink:
        sink.emit(HeartbeatEvent(
            "pipeline", "failed", "failed", 0, 0,
            last_material_event=f"{registro['classe']}: {registro['resumo'][:60]}",
            next=registro["destino"] or "decisão humana",
        ))
    return registro
