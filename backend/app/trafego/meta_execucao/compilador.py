"""Deterministic compiler for one Meta PAUSED website-traffic recipe."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from .contrato import PlanoMetaPausado, ReferenciasMetaResolvidas


_CAMPAIGN = "$campaign.id"
_ADSET = "$adset.id"
_CREATIVE = "$creative.id"


def _canonico(valor: Any) -> str:
    return json.dumps(valor, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class OperacaoMeta:
    nome: str
    endpoint: str
    payload: Mapping[str, Any]
    depende_de: tuple[str, ...] = ()
    validavel_sem_criar_pai: bool = False


@dataclass(frozen=True)
class PlanoCompiladoMeta:
    account_ref: str
    destination_url: str
    operacoes: tuple[OperacaoMeta, ...]
    plano_sha256: str
    estado_ao_nascer: str = "PAUSED"
    api_version: str = "v26.0"

    def publico(self) -> Mapping[str, Any]:
        return {
            "account_ref": self.account_ref,
            "destination_url": self.destination_url,
            "api_version": self.api_version,
            "plano_sha256": self.plano_sha256,
            "estado_ao_nascer": self.estado_ao_nascer,
            "operacoes": [
                {
                    "nome": op.nome,
                    "endpoint": (
                        f"/act_<conta>/{op.endpoint.rsplit('/', 1)[-1]}"
                        if op.endpoint.startswith("/act_") else op.endpoint
                    ),
                    "depende_de": list(op.depende_de),
                    "validavel_sem_criar_pai": op.validavel_sem_criar_pai,
                    "status": op.payload.get("status"),
                }
                for op in self.operacoes
            ],
        }


def compilar_plano_pausado(
    plano: PlanoMetaPausado,
    referencias: ReferenciasMetaResolvidas,
) -> PlanoCompiladoMeta:
    conta = referencias.account_id
    campaign = {
        "name": plano.campaign_name,
        "objective": plano.objective,
        "buying_type": "AUCTION",
        "special_ad_categories": list(plano.special_ad_categories),
        "status": "PAUSED",
    }
    targeting: dict[str, Any] = {
        "geo_locations": {"countries": list(plano.countries)},
        "age_min": plano.age_min,
        "age_max": plano.age_max,
    }
    adset = {
        "name": plano.adset_name,
        "campaign_id": _CAMPAIGN,
        "daily_budget": plano.daily_budget_minor,
        "billing_event": plano.billing_event,
        "optimization_goal": plano.optimization_goal,
        "bid_strategy": plano.bid_strategy,
        "destination_type": plano.destination_type,
        "start_time": plano.start_time.isoformat(),
        "targeting": targeting,
        "status": "PAUSED",
    }
    story: dict[str, Any] = {
        "page_id": referencias.page_id,
        "link_data": {
            "image_hash": referencias.image_hash,
            "link": plano.destination_url,
            "message": plano.message,
            "name": plano.headline,
            "description": plano.description,
            "call_to_action": {
                "type": plano.call_to_action_type,
                "value": {"link": plano.destination_url},
            },
        },
    }
    if referencias.instagram_actor_id is not None:
        story["instagram_actor_id"] = referencias.instagram_actor_id
    creative = {"name": plano.creative_name, "object_story_spec": story}
    ad = {
        "name": plano.ad_name,
        "adset_id": _ADSET,
        "creative": {"creative_id": _CREATIVE},
        "status": "PAUSED",
    }
    operacoes = (
        OperacaoMeta("campaign", f"/act_{conta}/campaigns", campaign,
                     validavel_sem_criar_pai=True),
        OperacaoMeta("adset", f"/act_{conta}/adsets", adset,
                     depende_de=("campaign",)),
        OperacaoMeta("creative", f"/act_{conta}/adcreatives", creative,
                     validavel_sem_criar_pai=True),
        OperacaoMeta("ad", f"/act_{conta}/ads", ad,
                     depende_de=("adset", "creative")),
    )
    materia = {
        "api_version": "v26.0",
        "account_ref": plano.account_ref,
        "destination_url": plano.destination_url,
        "operations": [
            {"name": op.nome, "endpoint": op.endpoint, "payload": op.payload}
            for op in operacoes
        ],
    }
    return PlanoCompiladoMeta(
        account_ref=plano.account_ref,
        destination_url=plano.destination_url,
        operacoes=operacoes,
        plano_sha256=hashlib.sha256(_canonico(materia).encode("utf-8")).hexdigest(),
    )


def resolver_dependencias(payload: Mapping[str, Any], ids: Mapping[str, str]) -> dict[str, Any]:
    """Resolve only compiler-owned placeholders, recursively and without eval."""
    def visitar(valor: Any) -> Any:
        if valor == _CAMPAIGN:
            return ids["campaign"]
        if valor == _ADSET:
            return ids["adset"]
        if valor == _CREATIVE:
            return ids["creative"]
        if isinstance(valor, Mapping):
            return {str(k): visitar(v) for k, v in valor.items()}
        if isinstance(valor, (list, tuple)):
            return [visitar(v) for v in valor]
        return valor
    return visitar(payload)
