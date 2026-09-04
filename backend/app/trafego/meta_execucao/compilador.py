"""Deterministic compiler for one Meta PAUSED website-traffic recipe."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from .contrato import (
    PLACEHOLDER_DE_DEPENDENCIA,
    ErroDeNascimentoMeta,
    PlanoMetaPausado,
    ReferenciasMetaResolvidas,
    VariacaoEstaticaMeta,
)


_CAMPAIGN = "$campaign.id"
_ADSET = "$adset.id"


def _canonico(valor: Any) -> str:
    return json.dumps(valor, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class OperacaoMeta:
    nome: str
    endpoint: str
    payload: Mapping[str, Any]
    depende_de: tuple[str, ...] = ()
    validavel_sem_criar_pai: bool = False
    tipo: str | None = None

    @property
    def chave(self) -> str:
        return self.nome

    @property
    def tipo_objeto(self) -> str:
        return self.tipo or self.nome.split(":", 1)[0]


@dataclass(frozen=True)
class PlanoCompiladoMeta:
    account_ref: str
    destination_url: str
    operacoes: tuple[OperacaoMeta, ...]
    plano_sha256: str
    estado_ao_nascer: str = "PAUSED"
    api_version: str = "v26.0"

    @property
    def conta_externa(self) -> str:
        """Conta resolvida, derivada do endpoint. Nunca sai em resposta pública."""
        return self.operacoes[0].endpoint.split("/act_", 1)[1].split("/", 1)[0]

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
                    "chave": op.chave,
                    "tipo": op.tipo_objeto,
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
        "is_adset_budget_sharing_enabled": plano.is_adset_budget_sharing_enabled,
        "status": "PAUSED",
    }
    targeting: dict[str, Any] = {
        "geo_locations": {"countries": list(plano.countries)},
        "age_min": plano.age_min,
        "age_max": plano.age_max,
        # A ausência deste campo não é neutra desde a v23.0: a Meta assume 1 e
        # liga o Advantage+ Audience sozinha. A escolha do operador viaja
        # sempre explícita, como 1 ou 0.
        "targeting_automation": {
            "advantage_audience": 1 if plano.advantage_audience else 0,
        },
    }
    adset = {
        "name": plano.adset_name,
        "campaign_id": _CAMPAIGN,
        "daily_budget": plano.daily_budget_minor,
        "billing_event": plano.billing_event,
        "optimization_goal": plano.optimization_goal,
        "bid_strategy": plano.bid_strategy,
        # `destination_type` não entra: para OUTCOME_TRAFFIC a tabela oficial
        # aceita apenas UNDEFINED, MESSENGER, WHATSAPP e PHONE_CALL. O campo é
        # opcional e o tráfego para site é o comportamento padrão do objetivo.
        "start_time": plano.start_time.isoformat(),
        "targeting": targeting,
        "status": "PAUSED",
    }
    operacoes_base = (
        OperacaoMeta("campaign", f"/act_{conta}/campaigns", campaign,
                     validavel_sem_criar_pai=True, tipo="campaign"),
        OperacaoMeta("adset", f"/act_{conta}/adsets", adset,
                     depende_de=("campaign",), tipo="adset"),
    )
    variacoes = plano.variacoes_estaticas or (
        VariacaoEstaticaMeta(
            variation_key="legacy",
            creative_name=plano.creative_name,
            ad_name=plano.ad_name,
            asset_ref=plano.asset_ref,
            message=plano.message,
            headline=plano.headline,
            description=plano.description,
            call_to_action_type=plano.call_to_action_type,
        ),
    )
    lote_explicito = bool(plano.variacoes_estaticas)
    operacoes_variacoes: list[OperacaoMeta] = []
    for variacao in variacoes:
        sufixo = f":{variacao.variation_key}" if lote_explicito else ""
        chave_criativo = f"creative{sufixo}"
        chave_anuncio = f"ad{sufixo}"
        story: dict[str, Any] = {
            "page_id": referencias.page_id,
            "link_data": {
                "image_hash": referencias.image_hash_for(
                    variacao.asset_ref, fallback_ref=plano.asset_ref),
                "link": plano.destination_url,
                "message": variacao.message,
                "name": variacao.headline,
                "description": variacao.description,
                "call_to_action": {
                    "type": variacao.call_to_action_type,
                    "value": {"link": plano.destination_url},
                },
            },
        }
        if referencias.instagram_actor_id is not None:
            story["instagram_actor_id"] = referencias.instagram_actor_id
        creative = {"name": variacao.creative_name, "object_story_spec": story}
        ad = {
            "name": variacao.ad_name,
            "adset_id": _ADSET,
            "creative": {"creative_id": f"${chave_criativo}.id"},
            "status": "PAUSED",
        }
        operacoes_variacoes.extend((
            OperacaoMeta(
                chave_criativo,
                f"/act_{conta}/adcreatives",
                creative,
                validavel_sem_criar_pai=True,
                tipo="creative",
            ),
            OperacaoMeta(
                chave_anuncio,
                f"/act_{conta}/ads",
                ad,
                depende_de=("adset", chave_criativo),
                tipo="ad",
            ),
        ))
    operacoes = operacoes_base + tuple(operacoes_variacoes)
    materia = {
        "api_version": "v26.0",
        "account_ref": plano.account_ref,
        "destination_url": plano.destination_url,
        "operations": [
            {
                "key": op.chave,
                "type": op.tipo_objeto,
                "endpoint": op.endpoint,
                "payload": op.payload,
            }
            for op in operacoes
        ],
    }
    return PlanoCompiladoMeta(
        account_ref=plano.account_ref,
        destination_url=plano.destination_url,
        operacoes=operacoes,
        plano_sha256=hashlib.sha256(_canonico(materia).encode("utf-8")).hexdigest(),
    )


# Os únicos lugares estruturais onde o compilador escreve um marcador. Resolver
# apenas aqui impede que um texto do operador com a mesma sintaxe — um nome de
# conjunto igual a "$campaign.id", por exemplo — seja trocado por um ID real
# depois de o plano já ter sido aprovado e hasheado.
CAMINHOS_DE_DEPENDENCIA: tuple[tuple[str, ...], ...] = (
    ("campaign_id",),
    ("adset_id",),
    ("creative", "creative_id"),
)


def _copia_simples(valor: Any) -> Any:
    if isinstance(valor, Mapping):
        return {str(chave): _copia_simples(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_copia_simples(item) for item in valor]
    return valor


def _exigir_sem_marcador(valor: Any) -> None:
    if isinstance(valor, str):
        if PLACEHOLDER_DE_DEPENDENCIA.fullmatch(valor):
            raise ErroDeNascimentoMeta(
                "META_UNRESOLVED_DEPENDENCY",
                "o payload ainda contém um marcador de dependência não resolvido",
            )
        return
    if isinstance(valor, Mapping):
        for item in valor.values():
            _exigir_sem_marcador(item)
        return
    if isinstance(valor, (list, tuple)):
        for item in valor:
            _exigir_sem_marcador(item)


def resolver_dependencias(payload: Mapping[str, Any], ids: Mapping[str, str]) -> dict[str, Any]:
    """Resolve compiler-owned placeholders at their structural paths only."""
    saida = _copia_simples(payload)
    for caminho in CAMINHOS_DE_DEPENDENCIA:
        alvo: Any = saida
        for chave in caminho[:-1]:
            alvo = alvo.get(chave) if isinstance(alvo, dict) else None
        if not isinstance(alvo, dict):
            continue
        folha = caminho[-1]
        bruto = alvo.get(folha)
        if not isinstance(bruto, str) or not PLACEHOLDER_DE_DEPENDENCIA.fullmatch(bruto):
            continue
        referencia = bruto[1:-3]
        if referencia not in ids:
            raise KeyError(referencia)
        alvo[folha] = ids[referencia]
    _exigir_sem_marcador(saida)
    return saida
