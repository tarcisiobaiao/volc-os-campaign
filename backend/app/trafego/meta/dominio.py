"""Provider-specific facts for the first, read-only Meta Ads slice.

The v9 traffic inventory uses Google ``customer_id`` and ``campaign_id`` as its
physical identity.  These types intentionally do not inherit from it: sharing
reliability rules is useful, pretending the storage identity is neutral is not.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from app.asset_vault.dominio import PayloadRecusado, recusar_chave_sensivel

META_ADS = "META_ADS"
TIPOS_DE_OBJETO = ("campaign", "adset", "ad", "creative")
NIVEIS_DE_INSIGHT = ("account", "campaign", "adset", "ad")
ESTADOS_DE_PRONTIDAO = (
    "CONFIG_MISSING",
    "REFERENCE_PRESENT",
    "RESOLUTION_UNTESTED",
    "RESOLUTION_FAILED",
    "PERMISSIONS_INSUFFICIENT",
    "ACCOUNT_INACCESSIBLE",
    "READY_FOR_READ",
    "READY_FOR_VALIDATION",
    "READY_FOR_CREATE_PAUSED",
    "READY_FOR_ACTIVATION",
)
ESTADOS_DE_SYNC = ("ok", "falhou")

_ID_EXTERNO = re.compile(r"^[0-9]{1,40}$")
_NAMESPACE_META = uuid.UUID("bd4f9787-f6ea-4cf8-9f7e-847984945f19")


class ContratoMetaInvalido(ValueError):
    """Input cannot cross the Meta read boundary."""


def conta_canonica(valor: str) -> str:
    """Return a Meta ad-account id without the transport-only ``act_`` prefix."""
    texto = str(valor or "").strip()
    if texto.startswith("act_"):
        texto = texto[4:]
    if not _ID_EXTERNO.fullmatch(texto):
        raise ContratoMetaInvalido("conta Meta deve conter apenas o id numerico")
    return texto


def id_externo(valor: Any, *, campo: str = "id_externo") -> str:
    texto = str(valor or "").strip()
    if not _ID_EXTERNO.fullmatch(texto):
        raise ContratoMetaInvalido(f"{campo} Meta deve conter apenas digitos")
    return texto


def id_interno(*, conta_externa: str, tipo: str, id_externo_meta: str) -> str:
    """Derive identity from provider, account, object type and external id.

    Names are deliberately absent: renaming an object must not create another
    local identity.  Including the object type also prevents an accidental
    collision between two different Meta namespaces.
    """
    conta = conta_canonica(conta_externa)
    if tipo not in TIPOS_DE_OBJETO:
        raise ContratoMetaInvalido(f"tipo Meta desconhecido: {tipo!r}")
    externo = id_externo(id_externo_meta)
    return str(uuid.uuid5(_NAMESPACE_META, f"{META_ADS}:{conta}:{tipo}:{externo}"))


def referencia_opaca_conta(conta_externa: str) -> str:
    """Stable non-secret account handle safe for the browser.

    The handle is deterministic so the UI can hold a reference, but it is not a
    reversible account-id map kept in the browser. The backend must re-read the
    accessible accounts and resolve this handle internally on every operation.
    """
    conta = conta_canonica(conta_externa)
    digest = hashlib.sha256(f"{META_ADS}:account:{conta}".encode("utf-8")).hexdigest()[:24]
    return f"metaacct_{digest}"


def mascarar_id(valor: Any) -> str | None:
    texto = str(valor or "").removeprefix("act_").strip()
    if not texto:
        return None
    return f"••••{texto[-4:]}"


def instante_utc(valor: datetime, *, campo: str) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ContratoMetaInvalido(f"{campo} precisa de timezone")
    return valor


def texto_opcional(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def decimal_opcional(valor: Any, *, campo: str) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor))
    except Exception as exc:  # pragma: no cover - branch defensive
        raise ContratoMetaInvalido(f"{campo} precisa ser decimal") from exc


@dataclass(frozen=True)
class BusinessMeta:
    id_externo: str
    nome: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id_externo", id_externo(self.id_externo, campo="business.id"))
        object.__setattr__(self, "nome", texto_opcional(self.nome))

    def publico(self) -> Mapping[str, Any]:
        return {"id_mascarado": mascarar_id(self.id_externo), "nome": self.nome}


@dataclass(frozen=True)
class ContaMetaDescoberta:
    id_externo: str
    nome: str | None
    status: str | None
    moeda: str | None
    fuso: str | None
    business: BusinessMeta | None = None

    def __post_init__(self) -> None:
        conta = conta_canonica(self.id_externo)
        object.__setattr__(self, "id_externo", conta)
        object.__setattr__(self, "nome", texto_opcional(self.nome))
        object.__setattr__(self, "status", texto_opcional(self.status))
        moeda = texto_opcional(self.moeda)
        if moeda is not None and not re.fullmatch(r"[A-Z]{3}", moeda):
            raise ContratoMetaInvalido("moeda Meta precisa ser ISO-4217")
        object.__setattr__(self, "moeda", moeda)
        object.__setattr__(self, "fuso", texto_opcional(self.fuso))

    @property
    def referencia_opaca(self) -> str:
        return referencia_opaca_conta(self.id_externo)

    @property
    def prontidao_leitura(self) -> str:
        return "READY_FOR_READ"

    def publico(self) -> Mapping[str, Any]:
        return {
            "referencia_opaca": self.referencia_opaca,
            "nome": self.nome or "Conta sem nome",
            "id_mascarado": mascarar_id(self.id_externo),
            "status": self.status,
            "moeda": self.moeda,
            "fuso": self.fuso,
            "business": self.business.publico() if self.business else None,
            "prontidao_leitura": self.prontidao_leitura,
        }


@dataclass(frozen=True)
class ObjetoMeta:
    tipo: str
    id_externo: str
    nome: str | None
    status: str | None
    effective_status: str | None
    parent_id_externo: str | None = None
    objetivo: str | None = None
    optimization_goal: str | None = None
    object_story_id: str | None = None
    creative_id_externo: str | None = None

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS_DE_OBJETO:
            raise ContratoMetaInvalido(f"tipo Meta desconhecido: {self.tipo!r}")
        object.__setattr__(self, "id_externo", id_externo(self.id_externo))
        if self.parent_id_externo is not None:
            object.__setattr__(self, "parent_id_externo", id_externo(
                self.parent_id_externo, campo="parent_id_externo"))
        if self.creative_id_externo is not None:
            object.__setattr__(self, "creative_id_externo", id_externo(
                self.creative_id_externo, campo="creative_id_externo"))


@dataclass(frozen=True)
class LeituraDaHierarquia:
    conta_externa: str
    campanhas: tuple[ObjetoMeta, ...]
    conjuntos: tuple[ObjetoMeta, ...]
    anuncios: tuple[ObjetoMeta, ...]
    criativos: tuple[ObjetoMeta, ...]
    paginas_lidas: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "conta_externa", conta_canonica(self.conta_externa))
        if self.paginas_lidas < 4:
            raise ContratoMetaInvalido(
                "hierarquia completa exige ao menos uma pagina por edge")
        esperados = (
            ("campaign", self.campanhas),
            ("adset", self.conjuntos),
            ("ad", self.anuncios),
            ("creative", self.criativos),
        )
        for tipo, objetos in esperados:
            if any(obj.tipo != tipo for obj in objetos):
                raise ContratoMetaInvalido(f"edge {tipo} recebeu objeto de outro tipo")

    @property
    def contagens(self) -> Mapping[str, int]:
        return {
            "campaign": len(self.campanhas),
            "adset": len(self.conjuntos),
            "ad": len(self.anuncios),
            "creative": len(self.criativos),
        }

    @property
    def objetos(self) -> tuple[ObjetoMeta, ...]:
        return self.campanhas + self.conjuntos + self.anuncios + self.criativos


@dataclass(frozen=True)
class AcaoInsightMeta:
    action_type: str
    value: Decimal | int | str | None
    attribution_window: str
    object_level: str
    date_start: date
    date_stop: date

    def __post_init__(self) -> None:
        if not self.action_type.strip() or not self.attribution_window.strip():
            raise ContratoMetaInvalido("acao de insight incompleta")
        if self.object_level not in NIVEIS_DE_INSIGHT:
            raise ContratoMetaInvalido("nivel de insight desconhecido")
        if self.date_stop < self.date_start:
            raise ContratoMetaInvalido("periodo de action invalido")
        if self.value is not None:
            object.__setattr__(self, "value", decimal_opcional(self.value, campo="action.value"))


@dataclass(frozen=True)
class InsightMeta:
    provider: str
    conta_externa: str
    nivel: str
    objeto_externo: str
    periodo_inicio: date
    periodo_fim: date
    janela_atribuicao: str
    breakdown: str
    observado_em: datetime
    spend: Decimal | int | str | None = None
    impressions: int | None = None
    reach: int | None = None
    frequency: Decimal | int | str | None = None
    clicks: int | None = None
    inline_link_clicks: int | None = None
    landing_page_views: int | None = None
    cpm: Decimal | int | str | None = None
    cpc: Decimal | int | str | None = None
    ctr: Decimal | int | str | None = None
    actions: tuple[AcaoInsightMeta, ...] = ()

    def __post_init__(self) -> None:
        if self.provider != META_ADS:
            raise ContratoMetaInvalido("provider de insight precisa ser META_ADS")
        object.__setattr__(self, "conta_externa", conta_canonica(self.conta_externa))
        if self.nivel not in NIVEIS_DE_INSIGHT:
            raise ContratoMetaInvalido("nivel de insight desconhecido")
        if self.nivel != "account":
            object.__setattr__(self, "objeto_externo", id_externo(self.objeto_externo, campo="objeto_externo"))
        elif not str(self.objeto_externo).strip():
            raise ContratoMetaInvalido("objeto account vazio")
        if self.periodo_fim < self.periodo_inicio:
            raise ContratoMetaInvalido("periodo de insight invalido")
        instante_utc(self.observado_em, campo="observado_em")
        for campo in ("spend", "frequency", "cpm", "cpc", "ctr"):
            object.__setattr__(self, campo, decimal_opcional(getattr(self, campo), campo=campo))
        for campo in ("impressions", "reach", "clicks", "inline_link_clicks", "landing_page_views"):
            valor = getattr(self, campo)
            if valor is not None and int(valor) < 0:
                raise ContratoMetaInvalido(f"{campo} nao pode ser negativo")


@dataclass(frozen=True)
class ReciboDeSync:
    run_id: str
    chave_de_idempotencia: str
    conta_externa: str
    resultado: str
    iniciado_em: datetime
    concluido_em: datetime
    contagens: Mapping[str, int]
    paginas_lidas: int
    erro_codigo: str | None = None
    erro_mensagem: str | None = None
    repetido: bool = False

    def __post_init__(self) -> None:
        uuid.UUID(self.run_id)
        conta_canonica(self.conta_externa)
        instante_utc(self.iniciado_em, campo="iniciado_em")
        instante_utc(self.concluido_em, campo="concluido_em")
        if self.resultado not in ESTADOS_DE_SYNC:
            raise ContratoMetaInvalido("resultado de sync desconhecido")
        if self.concluido_em < self.iniciado_em:
            raise ContratoMetaInvalido("sync terminou antes de comecar")
        if self.paginas_lidas < 0 or any(v < 0 for v in self.contagens.values()):
            raise ContratoMetaInvalido("contagem de sync nao pode ser negativa")
        if self.resultado == "ok" and (self.erro_codigo or self.erro_mensagem):
            raise ContratoMetaInvalido("sync ok nao carrega erro")
        if self.resultado == "falhou" and not self.erro_codigo:
            raise ContratoMetaInvalido("sync falho precisa de codigo seguro")


def validar_documento_seguro(documento: Mapping[str, Any] | Sequence[Any]) -> None:
    """Use the Cofre's recursive key blocklist at the Meta boundary."""
    try:
        recusar_chave_sensivel(documento, "meta")
    except PayloadRecusado as exc:
        raise ContratoMetaInvalido(str(exc)) from None
