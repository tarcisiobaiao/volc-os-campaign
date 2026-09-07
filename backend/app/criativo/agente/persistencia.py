"""Persistência confinada por owner_id; service role nunca decide autorização."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.supabase_service import SupabaseService


class NaoEncontrado(LookupError):
    pass


class RepositorioAgenteCriativo:
    def __init__(self, supabase: SupabaseService):
        if not supabase.enabled:
            raise RuntimeError("banco do Assistente de Criativos não configurado")
        self.db = supabase

    async def criar_operacao(self, row: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("criativo_agente_operacao", [row])
        if not rows:
            raise RuntimeError("o banco não devolveu a operação criada")
        return rows[0]

    async def obter_operacao(self, project_ref: str, owner_id: str) -> dict[str, Any]:
        rows = await self.db.select(
            "criativo_agente_operacao",
            {
                "project_ref": f"eq.{project_ref}",
                "owner_id": f"eq.{owner_id}",
                "limit": 1,
            },
        )
        if not rows:
            raise NaoEncontrado(project_ref)
        return rows[0]

    async def criar_run(self, row: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("criativo_agente_run", [row])
        if not rows:
            raise RuntimeError("o banco não devolveu a run criada")
        return rows[0]

    async def concluir_run(
        self,
        run_ref: str,
        owner_id: str,
        *,
        output: dict[str, Any],
        model: str,
        tentativas: int,
        request_sha256: str,
        knowledge_sha256: str,
    ) -> dict[str, Any]:
        rows = await self.db.patch(
            "criativo_agente_run",
            {"run_ref": f"eq.{run_ref}", "owner_id": f"eq.{owner_id}"},
            {
                "status": "COMPLETED",
                "output": output,
                "model": model,
                "tentativas": tentativas,
                "request_sha256": request_sha256,
                "knowledge_sha256": knowledge_sha256,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
            },
        )
        if not rows:
            raise NaoEncontrado(run_ref)
        await self.db.patch(
            "criativo_agente_operacao",
            {
                "project_ref": f"eq.{rows[0]['project_ref']}",
                "owner_id": f"eq.{owner_id}",
            },
            {
                "status": "READY_FOR_REVIEW",
                "latest_run_ref": run_ref,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return rows[0]

    async def falhar_run(
        self, run_ref: str, owner_id: str, *, error: dict[str, Any]
    ) -> None:
        rows = await self.db.patch(
            "criativo_agente_run",
            {"run_ref": f"eq.{run_ref}", "owner_id": f"eq.{owner_id}"},
            {
                "status": "FAILED",
                "error": error,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        if rows:
            await self.db.patch(
                "criativo_agente_operacao",
                {
                    "project_ref": f"eq.{rows[0]['project_ref']}",
                    "owner_id": f"eq.{owner_id}",
                },
                {
                    "status": "FAILED",
                    "latest_run_ref": run_ref,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

    async def obter_run(self, run_ref: str, owner_id: str) -> dict[str, Any]:
        rows = await self.db.select(
            "criativo_agente_run",
            {"run_ref": f"eq.{run_ref}", "owner_id": f"eq.{owner_id}", "limit": 1},
        )
        if not rows:
            raise NaoEncontrado(run_ref)
        return rows[0]

    async def listar_runs(self, project_ref: str, owner_id: str) -> list[dict[str, Any]]:
        return await self.db.select(
            "criativo_agente_run",
            {
                "project_ref": f"eq.{project_ref}",
                "owner_id": f"eq.{owner_id}",
                "order": "created_at.desc",
                "limit": 100,
            },
        )
    async def registrar_decisao(self, row: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("criativo_agente_decisao", [row])
        if not rows:
            raise RuntimeError("o banco não devolveu a decisão criada")
        return rows[0]

    async def listar_decisoes(self, project_ref: str, owner_id: str) -> list[dict[str, Any]]:
        return await self.db.select(
            "criativo_agente_decisao",
            {
                "project_ref": f"eq.{project_ref}",
                "owner_id": f"eq.{owner_id}",
                "order": "created_at.asc",
                "limit": 1000,
            },
        )
