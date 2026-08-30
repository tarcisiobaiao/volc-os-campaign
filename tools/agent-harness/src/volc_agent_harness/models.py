"""Contratos internos do harness."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class GateSpec(BaseModel):
    argv: list[str] = Field(min_length=1)
    timeout_seconds: int = Field(default=600, ge=10, le=3600)

    @field_validator("argv")
    @classmethod
    def argv_has_no_empty_items(cls, argv: list[str]) -> list[str]:
        if any(not item for item in argv):
            raise ValueError("gate argv não aceita item vazio")
        return argv


class WorkerSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]+$")
    provider: Literal["claude", "codex"]
    role: Literal["investigator", "writer", "reviewer"] = "investigator"
    model: str | None = Field(default=None, min_length=1)
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    network_access: bool = False
    lens: str = Field(min_length=1)
    allowed_paths: list[str] = Field(min_length=1)

    @field_validator("allowed_paths")
    @classmethod
    def paths_are_relative(cls, paths: list[str]) -> list[str]:
        for path in paths:
            if path.startswith("/") or ".." in path.split("/"):
                raise ValueError("allowed_paths aceita apenas caminhos relativos seguros")
        if len(paths) != len(set(paths)):
            raise ValueError("allowed_paths não pode conter duplicatas")
        return paths


class MissionSpec(BaseModel):
    mission_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    title: str = Field(min_length=1)
    base_ref: str = Field(min_length=1)
    briefing: str = Field(min_length=1)
    mode: Literal["read_only", "implementation"] = "read_only"
    commit_message: str | None = Field(default=None, min_length=1)
    gates: list[GateSpec] = Field(default_factory=list)
    workers: list[WorkerSpec] = Field(min_length=2, max_length=4)
    timeout_seconds: int = Field(default=1200, ge=60, le=7200)
    heartbeat_seconds: int = Field(default=20, ge=5, le=300)

    @model_validator(mode="after")
    def worker_ids_are_unique(self) -> "MissionSpec":
        ids = [worker.id for worker in self.workers]
        if len(ids) != len(set(ids)):
            raise ValueError("workers precisam ter ids únicos")
        writers = [worker for worker in self.workers if worker.role == "writer"]
        if self.mode == "read_only" and writers:
            raise ValueError("missão read_only não aceita writer")
        if self.mode == "implementation":
            if not _FULL_SHA.fullmatch(self.base_ref):
                raise ValueError(
                    "missão implementation exige base_ref como SHA completo de 40 caracteres"
                )
            if len(writers) != 1:
                raise ValueError("missão implementation exige exatamente um writer")
            if writers[0].provider != "codex":
                raise ValueError(
                    "o writer automatizado precisa ser Codex para usar sandbox workspace-write"
                )
            reviewers = [
                worker for worker in self.workers if worker.role == "reviewer"
            ]
            if not reviewers:
                raise ValueError("missão implementation exige ao menos um reviewer")
            if not self.commit_message:
                raise ValueError("missão implementation exige commit_message")
            if not self.gates:
                raise ValueError("missão implementation exige ao menos um gate")
        return self
