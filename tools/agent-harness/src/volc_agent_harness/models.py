"""Contratos internos do harness."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
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


class MicroRepairSpec(BaseModel):
    target_path: str = Field(min_length=1)
    observed_span: str = Field(min_length=1, max_length=240)
    allowed_replacements: list[str] = Field(min_length=1, max_length=8)
    instruction: str = Field(
        default="Escolha a menor substituição semanticamente correta.",
        min_length=1,
        max_length=500,
    )

    @field_validator("target_path")
    @classmethod
    def target_is_safe(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or value in {"", "."}:
            raise ValueError("target_path precisa ser relativo e seguro")
        if any(part.startswith(".env") or part == ".git" for part in path.parts):
            raise ValueError("target_path aponta para caminho protegido")
        return path.as_posix()

    @field_validator("allowed_replacements")
    @classmethod
    def replacements_are_closed(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("allowed_replacements não aceita duplicatas")
        if any(not value or len(value) > 240 for value in values):
            raise ValueError("replacement precisa ter entre 1 e 240 caracteres")
        return values


class WorkerSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]+$")
    provider: Literal["claude", "codex", "gemini", "deepseek"]
    role: Literal["investigator", "writer", "reviewer"] = "investigator"
    model: str | None = Field(default=None, min_length=1)
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    network_access: bool = False
    lens: str = Field(min_length=1)
    allowed_paths: list[str] = Field(min_length=1)
    writable_paths: list[str] = Field(default_factory=list)
    microrepair: MicroRepairSpec | None = None

    @field_validator("allowed_paths", "writable_paths")
    @classmethod
    def paths_are_relative(cls, paths: list[str]) -> list[str]:
        for path in paths:
            if (
                path in {"", "."}
                or path.startswith("/")
                or ".." in path.split("/")
            ):
                raise ValueError("allowed_paths aceita apenas caminhos relativos seguros")
        if len(paths) != len(set(paths)):
            raise ValueError("allowed_paths não pode conter duplicatas")
        return paths

    @model_validator(mode="after")
    def provider_contract_is_exact(self) -> "WorkerSpec":
        if self.provider == "codex":
            if self.model is None:
                self.model = "gpt-5.6-sol"
            if self.model not in {"gpt-5.6-sol", "gpt-5.5"}:
                raise ValueError("Codex exige gpt-5.6-sol ou gpt-5.5")
            if self.effort == "max":
                raise ValueError("Codex não aceita effort max neste harness")
        elif self.provider == "claude":
            if self.model is None:
                self.model = "opus"
            if self.model not in {"opus", "fable"}:
                raise ValueError("Claude exige modelo opus ou fable")
        elif self.provider == "gemini":
            if self.model != "gemini-3.7-flash":
                raise ValueError("Gemini exige model='gemini-3.7-flash'")
            if self.effort not in {"low", "medium", "high"}:
                raise ValueError("Gemini aceita effort low, medium ou high")
            if self.network_access:
                raise ValueError("Gemini não recebe navegação externa")
        elif self.provider == "deepseek":
            if self.model != "deepseek-v4-flash":
                raise ValueError("DeepSeek exige model='deepseek-v4-flash'")
            if self.effort != "low":
                raise ValueError("DeepSeek microrepair exige effort low")
            if self.role != "writer" or self.microrepair is None:
                raise ValueError("DeepSeek exige writer com microrepair explícito")
            if self.network_access:
                raise ValueError("DeepSeek não recebe ferramentas ou navegação")
        if self.provider != "deepseek" and self.microrepair is not None:
            raise ValueError("microrepair é exclusivo do executor DeepSeek")
        return self

    @model_validator(mode="after")
    def writes_are_a_subset_of_authorized_reads(self) -> "WorkerSpec":
        if self.role != "writer" and self.writable_paths:
            raise ValueError("somente writer pode declarar writable_paths")
        for writable in self.writable_paths:
            if not any(
                writable == allowed
                or writable.startswith(f"{allowed.rstrip('/')}/")
                for allowed in self.allowed_paths
            ):
                raise ValueError(
                    "writable_paths precisa ser subconjunto de allowed_paths"
                )
        if self.microrepair is not None:
            target = self.microrepair.target_path
            if not any(
                target == writable
                or target.startswith(f"{writable.rstrip('/')}/")
                for writable in self.writable_paths
            ):
                raise ValueError("target_path do microrepair precisa estar no ownership")
        return self

    @property
    def effective_writable_paths(self) -> list[str]:
        if self.role != "writer":
            return []
        return self.writable_paths


class RatchetSpec(BaseModel):
    enabled: bool = False
    max_writer_attempts: int = Field(default=3, ge=1, le=3)
    max_review_rounds: int = Field(default=3, ge=1, le=3)
    max_wall_seconds: int = Field(default=10_800, ge=60, le=43_200)
    no_progress_limit: int = Field(default=2, ge=1, le=3)


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
    # A ligação editorial é explícita. Missões legadas podem continuar sem
    # task_ids quando executadas diretamente, mas o supervisor contínuo recusa
    # qualquer implementação órfã.
    task_ids: list[str] = Field(default_factory=list)
    inbox_ids: list[str] = Field(default_factory=list)
    parent_run_id: str | None = None
    attempt: int = Field(default=1, ge=1)
    lineage_root_sha: str | None = None
    ratchet: RatchetSpec = Field(default_factory=RatchetSpec)
    authorized_external_providers: list[
        Literal["google_gemini", "anthropic", "deepseek"]
    ] = Field(default_factory=list)

    @field_validator("lineage_root_sha")
    @classmethod
    def lineage_root_is_full_sha(cls, value: str | None) -> str | None:
        if value is not None and not _FULL_SHA.fullmatch(value):
            raise ValueError("lineage_root_sha precisa ser SHA completo")
        return value

    @field_validator("task_ids", "inbox_ids")
    @classmethod
    def source_ids_are_unique(cls, ids: list[str]) -> list[str]:
        if any(not item.strip() for item in ids):
            raise ValueError("identificadores de origem não aceitam valor vazio")
        if len(ids) != len(set(ids)):
            raise ValueError("identificadores de origem não aceitam duplicatas")
        return ids

    @model_validator(mode="after")
    def worker_ids_are_unique(self) -> "MissionSpec":
        ids = [worker.id for worker in self.workers]
        if len(ids) != len(set(ids)):
            raise ValueError("workers precisam ter ids únicos")
        destination_for = {
            "gemini": "google_gemini",
            "claude": "anthropic",
            "deepseek": "deepseek",
        }
        missing_authorizations = sorted({
            destination
            for worker in self.workers
            if (destination := destination_for.get(worker.provider))
            and destination not in self.authorized_external_providers
        })
        if missing_authorizations:
            raise ValueError(
                "missão não declara autorização externa para: "
                + ", ".join(missing_authorizations)
            )
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
            if not writers[0].writable_paths:
                raise ValueError(
                    "missão implementation exige writable_paths explícito no writer"
                )
            if writers[0].provider not in {"codex", "gemini", "claude", "deepseek"}:
                raise ValueError(
                    "writer exige Codex, Gemini, Claude isolado ou DeepSeek microrepair"
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
