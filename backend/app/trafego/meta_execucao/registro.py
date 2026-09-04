"""Durable saga boundary required before any Meta create request."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Mapping, Protocol

import httpx

from app.services.supabase_service import SupabaseService

from .contrato import ErroDeNascimentoMeta


EstadoPassoMeta = Literal["DESPACHAR", "CRIADO", "AMBIGUO"]


@dataclass(frozen=True)
class PassoPreparadoMeta:
    passo_ref: str
    estado: EstadoPassoMeta
    id_externo: str | None = None

    def __post_init__(self) -> None:
        if not self.passo_ref.strip():
            raise ValueError("passo_ref vazio")
        if self.estado == "CRIADO":
            if not str(self.id_externo or "").isdigit():
                raise ValueError("passo CRIADO precisa de id externo")
        elif self.id_externo is not None:
            raise ValueError("id externo so pertence a passo CRIADO")


class RegistroSagaMeta(Protocol):
    async def preparar_passo(
        self,
        *,
        plano_sha256: str,
        approval_id: str,
        ator: str,
        nome: str,
        payload_sha256: str,
    ) -> PassoPreparadoMeta:
        """Persist and COMMIT the in-flight receipt before returning."""
        ...

    async def fechar_passo(self, *, passo_ref: str, id_externo: str) -> None: ...

    async def marcar_ambiguo(self, *, passo_ref: str) -> None: ...

    async def falhar_passo(self, *, passo_ref: str, codigo: str) -> None: ...


class RegistroSagaMetaSupabase:
    """Translate the saga protocol to transactional, service-role-only RPCs."""

    def __init__(self, servico: SupabaseService) -> None:
        self._servico = servico

    def _exigir_escrita(self) -> None:
        if os.environ.get("META_CREATE_LEDGER_WRITE_ENABLED") != "1":
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_WRITE_BLOCKED",
                "o ledger de criacao Meta permanece fechado neste servidor",
            )
        if not self._servico.enabled:
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_UNAVAILABLE",
                "o Supabase operacional nao esta configurado neste backend",
            )

    async def _rpc(self, funcao: str, argumentos: Mapping[str, Any]) -> Mapping[str, Any]:
        self._exigir_escrita()
        try:
            resposta = await self._servico.rpc(funcao, dict(argumentos))
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else 500
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_REJECTED",
                f"a autoridade persistente recusou a operacao (HTTP {status})",
            ) from None
        except httpx.HTTPError:
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_UNAVAILABLE",
                "a autoridade persistente nao respondeu",
            ) from None
        if not isinstance(resposta, Mapping):
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_INVALID_RESPONSE",
                "a autoridade persistente devolveu resposta invalida",
            )
        return resposta

    async def aprovar(
        self,
        *,
        plano_sha256: str,
        account_ref: str,
        ator: str,
        daily_budget_minor: int,
        expires_at: datetime,
    ) -> Mapping[str, Any]:
        return await self._rpc("trafego_meta_create_approve", {
            "p_plan_sha256": plano_sha256,
            "p_account_ref": account_ref,
            "p_actor_id": ator,
            "p_daily_budget_minor": daily_budget_minor,
            "p_expires_at": expires_at.isoformat(),
        })

    async def preparar_passo(
        self,
        *,
        plano_sha256: str,
        approval_id: str,
        ator: str,
        nome: str,
        payload_sha256: str,
    ) -> PassoPreparadoMeta:
        resposta = await self._rpc("trafego_meta_create_prepare_step", {
            "p_plan_sha256": plano_sha256,
            "p_approval_id": approval_id,
            "p_actor_id": ator,
            "p_step_name": nome,
            "p_payload_sha256": payload_sha256,
        })
        return PassoPreparadoMeta(
            passo_ref=str(resposta.get("step_ref") or ""),
            estado=str(resposta.get("state") or ""),  # type: ignore[arg-type]
            id_externo=(str(resposta["external_object_id"])
                        if resposta.get("external_object_id") is not None else None),
        )

    async def fechar_passo(self, *, passo_ref: str, id_externo: str) -> None:
        await self._rpc("trafego_meta_create_close_step", {
            "p_step_ref": passo_ref, "p_external_object_id": id_externo,
        })

    async def marcar_ambiguo(self, *, passo_ref: str) -> None:
        await self._rpc("trafego_meta_create_mark_ambiguous", {"p_step_ref": passo_ref})

    async def falhar_passo(self, *, passo_ref: str, codigo: str) -> None:
        await self._rpc("trafego_meta_create_fail_step", {
            "p_step_ref": passo_ref, "p_error_code": codigo,
        })

    async def recibo(self, approval_id: str) -> Mapping[str, Any]:
        return await self._rpc(
            "trafego_meta_create_receipt", {"p_approval_id": approval_id})
