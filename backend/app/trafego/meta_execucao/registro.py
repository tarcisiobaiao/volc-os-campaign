"""Durable saga boundary required before any Meta create request.

The production adapter is intentionally not implemented in this isolated
candidate. Its contract makes it impossible to expose real creation without a
store that commits the in-flight receipt before returning ``DESPACHAR``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


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
        nome: str,
        payload_sha256: str,
    ) -> PassoPreparadoMeta:
        """Persist and COMMIT the in-flight receipt before returning."""
        ...

    async def fechar_passo(self, *, passo_ref: str, id_externo: str) -> None: ...

    async def marcar_ambiguo(self, *, passo_ref: str) -> None: ...

    async def falhar_passo(self, *, passo_ref: str, codigo: str) -> None: ...
