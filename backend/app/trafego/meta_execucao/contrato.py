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


_CTA = {"LEARN_MORE", "APPLY_NOW", "SIGN_UP", "GET_QUOTE", "CONTACT_US"}

# Gramática dos marcadores que o compilador resolve para IDs reais entre os
# passos da saga. Texto do operador nunca pode assumir essa forma: o payload
# aprovado e hasheado ficaria diferente do payload efetivamente enviado.
PLACEHOLDER_DE_DEPENDENCIA = re.compile(
    r"\$(?:campaign|adset|creative|ad)(?::[a-z0-9][a-z0-9_-]{0,31})?\.id")


def _texto(valor: str, campo: str, *, maximo: int) -> str:
    saida = str(valor or "").strip()
    if not saida or len(saida) > maximo:
        raise ErroDeNascimentoMeta(
            "META_BLUEPRINT_INVALID", f"{campo} precisa ter entre 1 e {maximo} caracteres")
    if PLACEHOLDER_DE_DEPENDENCIA.fullmatch(saida):
        raise ErroDeNascimentoMeta(
            "META_PLACEHOLDER_SYNTAX_RESERVED",
            f"{campo} não pode ser exatamente um marcador de dependência do compilador",
        )
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
class VariacaoEstaticaMeta:
    """One independently named static creative/ad pair in a controlled batch."""

    variation_key: str
    creative_name: str
    ad_name: str
    asset_ref: str
    message: str
    headline: str
    description: str
    call_to_action_type: str = "LEARN_MORE"

    def __post_init__(self) -> None:
        chave = str(self.variation_key or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", chave):
            raise ErroDeNascimentoMeta(
                "META_STATIC_VARIATION_KEY_INVALID",
                "variation_key precisa ser uma chave curta, estavel e opaca",
            )
        object.__setattr__(self, "variation_key", chave)
        for campo, limite in (
            ("creative_name", 400), ("ad_name", 400),
            ("message", 2200), ("headline", 255), ("description", 255),
        ):
            object.__setattr__(self, campo, _texto(getattr(self, campo), campo, maximo=limite))
        object.__setattr__(self, "asset_ref", _referencia(self.asset_ref, "asset_ref"))
        if self.call_to_action_type not in _CTA:
            raise ErroDeNascimentoMeta("META_CTA_INVALID", "CTA fora da allowlist P0")


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
    is_adset_budget_sharing_enabled: bool
    instagram_actor_ref: str | None = None
    call_to_action_type: str = "LEARN_MORE"
    objective: str = "OUTCOME_TRAFFIC"
    optimization_goal: str = "LANDING_PAGE_VIEWS"
    billing_event: str = "IMPRESSIONS"
    bid_strategy: str = "LOWEST_COST_WITHOUT_CAP"
    # Rótulo VOLC da receita, NÃO um campo de payload. A tabela oficial de
    # destination_type lista, para OUTCOME_TRAFFIC, apenas UNDEFINED, MESSENGER,
    # WHATSAPP e PHONE_CALL — WEBSITE pertence a AWARENESS, LEADS e SALES. O
    # compilador por isso não envia destination_type para esta receita.
    # https://developers.facebook.com/docs/marketing-api/adset/destination_type/
    destination_type: str = "WEBSITE"
    budget_scope: str = "ADSET"
    placements_mode: str = "AUTOMATIC"
    countries: tuple[str, ...] = ("BR",)
    age_min: int = 18
    age_max: int = 65
    currency: str = "BRL"
    promoted_object: Mapping[str, Any] | None = None
    # Desde a v23.0 a ausência NÃO é neutra: `advantage_audience` assume 1 ao
    # criar um Ad Set novo. Omitir ligaria o Advantage+ Audience em silêncio,
    # então a receita exige um booleano explícito, como o compartilhamento de
    # orçamento. O padrão compatível é a recusa (0).
    # https://developers.facebook.com/docs/marketing-api/audiences/reference/targeting-expansion/advantage-audience/
    advantage_audience: bool = False
    variacoes_estaticas: tuple[VariacaoEstaticaMeta, ...] = ()

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
        if not isinstance(self.advantage_audience, bool):
            raise ErroDeNascimentoMeta(
                "META_ADVANTAGE_AUDIENCE_INVALID",
                "advantage_audience precisa ser True ou False; a omissão liga o Advantage+",
            )
        if not isinstance(self.daily_budget_minor, int) or isinstance(self.daily_budget_minor, bool) or self.daily_budget_minor <= 0:
            raise ErroDeNascimentoMeta(
                "META_BUDGET_INVALID", "daily_budget_minor precisa ser inteiro positivo")
        if self.currency != "BRL":
            raise ErroDeNascimentoMeta(
                "META_CURRENCY_UNSUPPORTED", "a primeira receita esta limitada a contas BRL")
        if not isinstance(self.is_adset_budget_sharing_enabled, bool):
            raise ErroDeNascimentoMeta(
                "META_BUDGET_SHARING_INVALID",
                "is_adset_budget_sharing_enabled precisa ser True ou False",
            )
        # ⚠️ MEDIDO NA META, não inferido. Em 05/09/2026 o validate_only real
        # recusou a campanha com código 100 / subcódigo 4005: "Não é possível
        # usar o compartilhamento do orçamento do conjunto de anúncios sem uma
        # estratégia de lance."
        #
        # A receita P0 tem UM conjunto, com orçamento e `bid_strategy` no
        # AdSet e nenhuma estratégia no Campaign. Com um único conjunto,
        # compartilhar orçamento não produz benefício operacional — e a
        # correção que a Meta aceitaria (mover uma estratégia de lance para o
        # Campaign) mudaria a semântica da receita aprovada. Então a receita
        # fixa o compartilhamento em False, e o pedido de True é recusado AQUI,
        # antes de qualquer chamada à Meta.
        #
        # A recusa é explícita de propósito: converter True em False em
        # silêncio faria o payload divergir da intenção que o operador
        # aprovou, e o hash do plano deixaria de descrever o que ele pediu.
        if self.is_adset_budget_sharing_enabled:
            raise ErroDeNascimentoMeta(
                "META_BUDGET_SHARING_REQUIRES_MULTI_ADSET_RECIPE",
                "esta receita tem um unico conjunto: a Meta exige estrategia de lance "
                "no Campaign para compartilhar orcamento (codigo 100/4005), e adiciona-la "
                "mudaria a receita aprovada",
            )
        if not self.special_categories_confirmed:
            raise ErroDeNascimentoMeta(
                "META_SPECIAL_CATEGORY_NOT_CONFIRMED",
                "o operador precisa confirmar explicitamente as categorias especiais")
        categorias = tuple(dict.fromkeys(self.special_ad_categories))
        if categorias:
            raise ErroDeNascimentoMeta(
                "META_SPECIAL_CATEGORY_RECIPE_UNPROVEN",
                "categorias especiais exigem receita, targeting e read-back proprios",
            )
        object.__setattr__(self, "special_ad_categories", categorias)
        if self.call_to_action_type not in _CTA:
            raise ErroDeNascimentoMeta("META_CTA_INVALID", "CTA fora da allowlist P0")
        variacoes = tuple(self.variacoes_estaticas)
        if len(variacoes) > 10:
            raise ErroDeNascimentoMeta(
                "META_STATIC_BATCH_LIMIT_EXCEEDED",
                "o lote Meta aceita no maximo 10 variacoes estaticas",
            )
        if any(not isinstance(item, VariacaoEstaticaMeta) for item in variacoes):
            raise ErroDeNascimentoMeta(
                "META_STATIC_BATCH_INVALID", "variacoes_estaticas contem item invalido")
        nomes_criativos = [item.creative_name for item in variacoes]
        nomes_anuncios = [item.ad_name for item in variacoes]
        chaves = [item.variation_key for item in variacoes]
        if len(set(chaves)) != len(chaves):
            raise ErroDeNascimentoMeta(
                "META_STATIC_BATCH_DUPLICATE_KEY", "variation_key precisa ser unica no lote")
        if len(set(nomes_criativos)) != len(nomes_criativos):
            raise ErroDeNascimentoMeta(
                "META_STATIC_BATCH_DUPLICATE_NAME", "nomes de criativos precisam ser unicos")
        if len(set(nomes_anuncios)) != len(nomes_anuncios):
            raise ErroDeNascimentoMeta(
                "META_STATIC_BATCH_DUPLICATE_NAME", "nomes de anuncios precisam ser unicos")
        object.__setattr__(self, "variacoes_estaticas", variacoes)
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
    image_hashes_by_ref: Mapping[str, str] = field(default_factory=dict)

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
        hashes: dict[str, str] = {}
        for referencia, hash_imagem in self.image_hashes_by_ref.items():
            ref = _referencia(str(referencia), "asset_ref")
            valor = str(hash_imagem or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{6,160}", valor):
                raise ErroDeNascimentoMeta(
                    "META_RESOLVED_REFERENCE_INVALID", "image_hash do lote invalido")
            hashes[ref] = valor
        object.__setattr__(self, "image_hashes_by_ref", hashes)

    def image_hash_for(self, asset_ref: str, *, fallback_ref: str) -> str:
        if asset_ref == fallback_ref:
            return self.image_hashes_by_ref.get(asset_ref, self.image_hash)
        try:
            return self.image_hashes_by_ref[asset_ref]
        except KeyError:
            raise ErroDeNascimentoMeta(
                "META_ASSET_REFERENCE_UNRESOLVED",
                "uma imagem do lote nao foi resolvida pelo backend",
            ) from None

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
