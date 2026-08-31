"""Integração real: o caminho de execução passa pelo V3, não ao lado dele.

Uma biblioteca V3 verde que nenhum launcher consome não protege nada. Este módulo
é o ponto único por onde uma missão atravessa compile → writer → postcompile →
gates → adjudicação → harvest, com o ledger registrando cada etapa e a taxonomia
classificando cada falha.

``volc-harness compile`` e ``volc-harness run --v3`` entram por aqui.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .baseline import BaselineRecord
from .compiler import CompiledMission, compile_mission
from .failures import FailureClass, HarnessFailure
from .heartbeat import HeartbeatEvent, HeartbeatSink
from .ledger import EvidenceLedger
from .registry import WorktreeRegistry
from .schema_version import assert_compilable
from .workspace import (
    assert_gate_executable_is_allowed, assert_no_destructive_intent,
)


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
    # A guarda roda sobre o argv REALMENTE CONSTRUÍDO, depois da compilação.
    #
    # Antes ela lia `gate.get("argv", [])` da missão — e com gate tipado isso
    # devolve `[]`. Uma guarda que recebe lista vazia é uma guarda que sempre
    # passa: proteção escrita que o caminho produtivo não atravessa, exatamente
    # o defeito que o Harness V3 existe para eliminar, reintroduzido no
    # entrypoint `volc-harness compile`.
    for compilado in compilada.gate_plan["gates"]:
        assert_gate_executable_is_allowed(compilado["argv"])
        assert_no_destructive_intent(compilado["argv"])

    art.compiled_mission = compilada.as_dict()
    art.gate_plan = compilada.gate_plan
    art.write()
    return compilada, art


def _desligada(nome: str, substituto: str) -> None:
    raise HarnessFailure(
        FailureClass.LEGACY_PATH_DISABLED,
        f"{nome} foi desligada",
        detalhe=f"o caminho vivo é {substituto}",
        reproducao="nenhum entrypoint alcançava esta função; não a reative sem decisão",
    )


def run_baseline(*_args: Any, **_kwargs: Any) -> list[BaselineRecord]:
    """DESLIGADA. Chamava ``baseline.measure`` — subprocesso sem claim."""

    _desligada("pipeline.run_baseline",
               "mission._run_implementation_mission, via run_gate_with_ledger")
    raise AssertionError("inalcançável")          # pragma: no cover


def postwriter_phase(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """DESLIGADA. Chamava ``postwriter_compile`` sem gates resolvidos."""

    _desligada("pipeline.postwriter_phase",
               "mission._run_implementation_mission, com resolved=")
    raise AssertionError("inalcançável")          # pragma: no cover


def classify_and_record(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """DESLIGADA. Duplicava a fronteira de erro que agora é única."""

    _desligada("pipeline.classify_and_record", "mission._falha_com_artefato")
    raise AssertionError("inalcançável")          # pragma: no cover
