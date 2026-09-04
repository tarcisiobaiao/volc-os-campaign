"""Pure contracts for the first Meta website-traffic canary."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlparse


class ErroDeNascimentoMeta(ValueError):
    def __init__(self, codigo: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.codigo = codigo


_CATEGORIAS = {
    "CREDIT", "EMPLOYMENT", "FINANCIAL_PRODUCTS_SERVICES", "HOUSING",
    "ISSUES_ELECTIONS_POLITICS", "ONLINE_GAMBLING_AND_GAMING",
}
_CTA = {"LEARN_MORE", "APPLY_NOW", "SIGN_UP", "GET_QUOTE", "CONTACT_US"}


def _texto(valor: str, campo: str, *, maximo: int) -> str:
    saida = str(valor or "").strip()
    if not saida or len(saida) > maximo:
        raise ErroDeNascimentoMeta(
            "META_BLUEPRINT_INVALID", f"{campo} precisa ter entre 1 e {maximo} caracteres")
    return saida


def _referencia(valor: str, campo: str) -> str:
    saida = _texto(valor, campo, maximo=180)
    if not re.fullmatch(r"[A-Za-z0-9:_-]+", saida):
        raise ErroDeNascimentoMeta(
            "META_REFERENCE_INVALID", f"{campo} nao e uma referencia opaca valida")
    return saida


def _url_https(valor: str) -> str:
    saida = _texto(valor, "destination_url", maximo=2000)
    partes = urlparse(saida)
    if partes.scheme != "https" or not partes.hostname or partes.username or partes.password:
        raise ErroDeNascimentoMeta(
            "META_DESTINATION_INVALID", "o destino Meta precisa ser uma URL HTTPS publica")
    return saida


@dataclass(frozen=True)
class PlanoMetaPausado:
    """Operator-approved, account-opaque blueprint for the P0 recipe.

    The P0 recipe is deliberately narrow. Broader objectives, custom
    conversions, manual placements and Advantage components need their own
    proven recipes rather than silently changing this payload.
    """

    account_ref: str
    campaign_name: str
    adset_name: str
    creative_name: str
    ad_name: str
    destination_url: str
    page_ref: str
    asset_ref: str
    message: str
    headline: str
    description: str
    daily_budget_minor: int
    start_time: datetime
    special_ad_categories: tuple[str, ...]
    special_categories_confirmed: bool
    instagram_actor_ref: str | None = None
    call_to_action_type: str = "LEARN_MORE"
    objective: str = "OUTCOME_TRAFFIC"
    optimization_goal: str = "LANDING_PAGE_VIEWS"
    billing_event: str = "IMPRESSIONS"
    bid_strategy: str = "LOWEST_COST_WITHOUT_CAP"
    destination_type: str = "WEBSITE"
    budget_scope: str = "ADSET"
    placements_mode: str = "AUTOMATIC"
    countries: tuple[str, ...] = ("BR",)
    age_min: int = 18
    age_max: int = 65
    currency: str = "BRL"
    promoted_object: Mapping[str, Any] | None = None
    advantage_audience: bool | None = None

    def __post_init__(self) -> None:
        for campo, limite in (
            ("campaign_name", 400), ("adset_name", 400),
            ("creative_name", 400), ("ad_name", 400),
            ("message", 2200), ("headline", 255), ("description", 255),
        ):
            object.__setattr__(self, campo, _texto(getattr(self, campo), campo, maximo=limite))
        object.__setattr__(self, "account_ref", _referencia(self.account_ref, "account_ref"))
        object.__setattr__(self, "page_ref", _referencia(self.page_ref, "page_ref"))
        object.__setattr__(self, "asset_ref", _referencia(self.asset_ref, "asset_ref"))
        if self.instagram_actor_ref is not None:
            object.__setattr__(self, "instagram_actor_ref", _referencia(
                self.instagram_actor_ref, "instagram_actor_ref"))
        object.__setattr__(self, "destination_url", _url_https(self.destination_url))
        if self.objective != "OUTCOME_TRAFFIC" or self.optimization_goal != "LANDING_PAGE_VIEWS":
            raise ErroDeNascimentoMeta(
                "META_RECIPE_NOT_PROVEN", "o P0 aceita apenas OUTCOME_TRAFFIC/LANDING_PAGE_VIEWS")
        if self.billing_event != "IMPRESSIONS" or self.bid_strategy != "LOWEST_COST_WITHOUT_CAP":
            raise ErroDeNascimentoMeta(
                "META_RECIPE_NOT_PROVEN", "billing event ou bid strategy fora da receita P0")
        if self.destination_type != "WEBSITE" or self.budget_scope != "ADSET":
            raise ErroDeNascimentoMeta(
                "META_RECIPE_NOT_PROVEN", "o P0 aceita destino WEBSITE e budget no AdSet")
        if self.placements_mode != "AUTOMATIC":
            raise ErroDeNascimentoMeta(
                "META_PLACEMENT_RECIPE_UNPROVEN", "placements manuais nao pertencem ao P0")
        if self.promoted_object:
            raise ErroDeNascimentoMeta(
                "META_MEASUREMENT_RECIPE_UNPROVEN",
                "promoted_object nao e necessario para o canario de trafego e exige receita propria")
        if self.advantage_audience is not None:
            raise ErroDeNascimentoMeta(
                "META_ADVANTAGE_AUDIENCE_UNPROVEN",
                "Advantage Audience precisa de receita e read-back proprios")
        if not isinstance(self.daily_budget_minor, int) or isinstance(self.daily_budget_minor, bool) or self.daily_budget_minor <= 0:
            raise ErroDeNascimentoMeta(
                "META_BUDGET_INVALID", "daily_budget_minor precisa ser inteiro positivo")
        if self.currency != "BRL":
            raise ErroDeNascimentoMeta(
                "META_CURRENCY_UNSUPPORTED", "a primeira receita esta limitada a contas BRL")
        if not self.special_categories_confirmed:
            raise ErroDeNascimentoMeta(
                "META_SPECIAL_CATEGORY_NOT_CONFIRMED",
                "o operador precisa confirmar explicitamente as categorias especiais")
        categorias = tuple(dict.fromkeys(self.special_ad_categories))
        if any(c not in _CATEGORIAS for c in categorias):
            raise ErroDeNascimentoMeta(
                "META_SPECIAL_CATEGORY_INVALID", "categoria especial fora da allowlist")
        object.__setattr__(self, "special_ad_categories", categorias)
        if self.call_to_action_type not in _CTA:
            raise ErroDeNascimentoMeta("META_CTA_INVALID", "CTA fora da allowlist P0")
        if not self.countries or any(not re.fullmatch(r"[A-Z]{2}", c) for c in self.countries):
            raise ErroDeNascimentoMeta("META_TARGETING_INVALID", "countries invalido")
        if self.age_min < 18 or self.age_max > 65 or self.age_min > self.age_max:
            raise ErroDeNascimentoMeta("META_TARGETING_INVALID", "faixa etaria invalida")
        inicio = self.start_time
        if inicio.tzinfo is None or inicio.utcoffset() is None:
            raise ErroDeNascimentoMeta("META_SCHEDULE_INVALID", "start_time precisa ter timezone")


@dataclass(frozen=True, repr=False)
class ReferenciasMetaResolvidas:
    """Raw provider references that exist only inside the backend process."""

    account_id: str
    page_id: str
    image_hash: str
    instagram_actor_id: str | None = None

    def __post_init__(self) -> None:
        for campo in ("account_id", "page_id"):
            valor = str(getattr(self, campo) or "").removeprefix("act_").strip()
            if not valor.isdigit():
                raise ErroDeNascimentoMeta("META_RESOLVED_REFERENCE_INVALID", f"{campo} invalido")
            object.__setattr__(self, campo, valor)
        if self.instagram_actor_id is not None:
            valor = str(self.instagram_actor_id).strip()
            if not valor.isdigit():
                raise ErroDeNascimentoMeta(
                    "META_RESOLVED_REFERENCE_INVALID", "instagram_actor_id invalido")
            object.__setattr__(self, "instagram_actor_id", valor)
        imagem = str(self.image_hash or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,160}", imagem):
            raise ErroDeNascimentoMeta("META_RESOLVED_REFERENCE_INVALID", "image_hash invalido")
        object.__setattr__(self, "image_hash", imagem)

    def __repr__(self) -> str:
        return "ReferenciasMetaResolvidas(<ocultas>)"


@dataclass(frozen=True)
class AutorizacaoMeta:
    plano_sha256: str
    ator: str
    approval_id: str
    permitir_validate_only: bool = False
    permitir_criar_pausada: bool = False

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-f0-9]{64}", self.plano_sha256):
            raise ErroDeNascimentoMeta("META_APPROVAL_INVALID", "hash de aprovacao invalido")
        _texto(self.ator, "ator", maximo=200)
        _referencia(self.approval_id, "approval_id")

    def exigir(self, *, plano_sha256: str, ato: str) -> None:
        if plano_sha256 != self.plano_sha256:
            raise ErroDeNascimentoMeta(
                "META_APPROVED_PLAN_DIVERGED", "o payload atual difere do plano aprovado")
        permitido = (
            self.permitir_validate_only if ato == "validate_only"
            else self.permitir_criar_pausada if ato == "create_paused"
            else False
        )
        if not permitido:
            raise ErroDeNascimentoMeta(
                "META_ACTION_NOT_AUTHORIZED", f"o ato {ato} nao foi autorizado")
