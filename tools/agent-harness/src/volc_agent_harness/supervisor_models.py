"""Contratos explícitos do supervisor contínuo.

O supervisor nunca transforma título, ordem editorial ou proximidade visual em
uma missão executável. Cada job aponta para uma missão versionada e para uma
tarefa existente no Roadmap Vivo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SupervisorJobSpec(BaseModel):
    job_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    task_id: str = Field(pattern=r"^P[0-9]{2}-T[0-9]{2}$")
    mission_path: str = Field(min_length=1)
    priority: int = Field(default=100, ge=1, le=10_000)
    dependencies: list[str] = Field(default_factory=list)
    risk_class: Literal["local_code_only"] = "local_code_only"
    enabled: bool = True
    max_attempts: int = Field(default=1, ge=1, le=3)

    @field_validator("mission_path")
    @classmethod
    def mission_path_is_safe(cls, value: str) -> str:
        path = Path(value)
        if ".." in path.parts or path.suffix != ".json":
            raise ValueError("mission_path precisa apontar para JSON seguro")
        if path.is_absolute() and not path.is_relative_to(Path("/private/tmp")):
            raise ValueError(
                "mission_path absoluto só é aceito no scratchpad /private/tmp"
            )
        return value

    @field_validator("dependencies")
    @classmethod
    def dependencies_are_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("dependencies não aceita duplicatas")
        return values


class SupervisorQueueSpec(BaseModel):
    supervisor_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    roadmap_path: str = "volc-os-workbook/ROADMAP-VIVO.json"
    jobs: list[SupervisorJobSpec] = Field(min_length=1)
    poll_seconds: int = Field(default=30, ge=5, le=3600)
    lease_seconds: int = Field(default=14_400, ge=60, le=86_400)
    max_writer_concurrency: Literal[1] = 1

    @model_validator(mode="after")
    def jobs_are_unique(self) -> "SupervisorQueueSpec":
        job_ids = [job.job_id for job in self.jobs]
        task_ids = [job.task_id for job in self.jobs]
        if len(job_ids) != len(set(job_ids)):
            raise ValueError("jobs precisam ter job_id único")
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("uma fila não pode duplicar task_id")
        return self
