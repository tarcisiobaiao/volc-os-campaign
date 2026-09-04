"""Opaque credential-reference boundary for Meta Ads.

The existing Cofre API returns posture, not the locator.  Consequently this
module defines the host-only resolver seam but deliberately provides no live
implementation.  Tests inject a fake; production remains fail-closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Protocol

from .dominio import ESTADOS_DE_PRONTIDAO, ContratoMetaInvalido


class CredencialIndisponivel(RuntimeError):
    codigo = "META_CREDENTIAL_UNAVAILABLE"


@dataclass(frozen=True)
class ReferenciaDeCredencial:
    ativo_id: str
    provider: str
    nome_logico: str
    estado: str
    verificacao_estado: str
    verificado_em: datetime | None = None
    valido_ate: date | None = None

    def __post_init__(self) -> None:
        if not self.ativo_id.strip() or not self.nome_logico.strip():
            raise ContratoMetaInvalido("referencia de credencial incompleta")
        if self.provider not in {
            "1password", "bitwarden", "vaultwarden", "passbolt", "infisical"
        }:
            raise ContratoMetaInvalido("provider de credencial desconhecido")


@dataclass(frozen=True, repr=False)
class SegredoEfemero:
    """Secret value whose repr/str never reveals its material."""
    _valor: str

    def __post_init__(self) -> None:
        if not self._valor:
            raise CredencialIndisponivel("o resolvedor devolveu segredo vazio")

    def __repr__(self) -> str:
        return "SegredoEfemero(<oculto>)"

    def __str__(self) -> str:
        return "<segredo-efemero-oculto>"

    def cabecalho_bearer(self) -> str:
        return f"Bearer {self._valor}"


class ResolvedorDeSegredo(Protocol):
    async def resolver(self, referencia: ReferenciaDeCredencial) -> SegredoEfemero: ...


class ResolvedorNaoConfigurado:
    async def resolver(self, referencia: ReferenciaDeCredencial) -> SegredoEfemero:
        del referencia
        raise CredencialIndisponivel(
            "resolvedor host-only nao configurado; leitura Meta permanece bloqueada")


def prontidao_da_referencia(
    referencia: ReferenciaDeCredencial | None, *, hoje: date | None = None,
) -> str:
    """Map safe Cofre posture to the onboarding contract, without resolving it."""
    if referencia is None or referencia.estado in {"not_registered", "retired"}:
        return "CONFIG_MISSING"
    if referencia.estado not in {"referenced", "review_due"}:
        return "CONFIG_MISSING"
    if referencia.valido_ate and referencia.valido_ate < (hoje or date.today()):
        return "RESOLUTION_FAILED"
    if referencia.verificacao_estado == "verified":
        if referencia.verificado_em is None:
            raise ContratoMetaInvalido("credencial verificada sem carimbo")
        return "READY_FOR_READ"
    if referencia.verificacao_estado in {"failed", "expired", "blocked"}:
        return "RESOLUTION_FAILED"
    if referencia.verificacao_estado == "partial":
        return "RESOLUTION_UNTESTED"
    return "REFERENCE_PRESENT"


def exigir_pronta_para_leitura(referencia: ReferenciaDeCredencial) -> None:
    estado = prontidao_da_referencia(referencia, hoje=datetime.now(timezone.utc).date())
    if estado not in ESTADOS_DE_PRONTIDAO:
        raise ContratoMetaInvalido("estado de prontidao fora do contrato")
    if estado != "READY_FOR_READ":
        raise CredencialIndisponivel(f"credencial Meta nao esta pronta: {estado}")
