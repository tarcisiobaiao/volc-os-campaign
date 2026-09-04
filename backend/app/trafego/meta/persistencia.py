"""Hermetic reference repository and strict row mapping for Meta read facts.

No PostgREST client lives here yet.  The in-memory implementation makes the
transaction contract executable without a Supabase connection; a later host
adapter must implement the same single-operation commit against reviewed SQL.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from . import dominio as dom

TABELAS_META = (
    "trafego_meta_business",
    "trafego_meta_ad_account",
    "trafego_meta_campaign",
    "trafego_meta_adset",
    "trafego_meta_ad",
    "trafego_meta_creative",
    "trafego_meta_ad_creative_binding",
    "trafego_meta_sync_run",
)


def linhas_de_contas(
    contas: list[dom.ContaMetaDescoberta] | tuple[dom.ContaMetaDescoberta, ...],
    observado_em: datetime,
    *,
    credencial_ativo_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """Prepare business/ad-account rows for one transaction, without raw payloads."""
    dom.instante_utc(observado_em, campo="observado_em")
    if not credencial_ativo_id.strip():
        raise dom.ContratoMetaInvalido("ativo de credencial Meta vazio")
    saida = {"trafego_meta_business": [], "trafego_meta_ad_account": []}
    vistos_business: set[str] = set()
    for conta in contas:
        business_ativo_id = None
        if conta.business is not None:
            business_ativo_id = "meta_business_" + dom.id_interno(
                conta_externa=conta.id_externo,
                tipo="campaign",
                id_externo_meta=conta.business.id_externo,
            )
            if business_ativo_id not in vistos_business:
                saida["trafego_meta_business"].append({
                    "cofre_ativo_id": business_ativo_id,
                    "business_external_id": conta.business.id_externo,
                    "nome_observado": conta.business.nome,
                    "observado_em": observado_em,
                })
                vistos_business.add(business_ativo_id)
        saida["trafego_meta_ad_account"].append({
            "cofre_ativo_id": "meta_account_" + conta.referencia_opaca,
            "business_ativo_id": business_ativo_id,
            "credential_ativo_id": credencial_ativo_id,
            "account_external_id": conta.id_externo,
            "nome_observado": conta.nome,
            "moeda": conta.moeda,
            "timezone_name": conta.fuso,
            "account_status": conta.status,
            "readiness_state": conta.prontidao_leitura,
            "observado_em": observado_em,
        })
    return saida


def linhas_da_leitura(
    leitura: dom.LeituraDaHierarquia,
    observado_em: datetime,
    *,
    conta_ativo_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """Translate typed objects through a table allowlist; never persist raw JSON."""
    dom.instante_utc(observado_em, campo="observado_em")
    if not conta_ativo_id.strip():
        raise dom.ContratoMetaInvalido("ativo da conta Meta vazio")
    conta = leitura.conta_externa
    campanhas = {
        x.id_externo: dom.id_interno(
            conta_externa=conta, tipo="campaign", id_externo_meta=x.id_externo)
        for x in leitura.campanhas
    }
    conjuntos = {
        x.id_externo: dom.id_interno(
            conta_externa=conta, tipo="adset", id_externo_meta=x.id_externo)
        for x in leitura.conjuntos
    }
    criativos = {
        x.id_externo: dom.id_interno(
            conta_externa=conta, tipo="creative", id_externo_meta=x.id_externo)
        for x in leitura.criativos
    }

    saida: dict[str, list[dict[str, Any]]] = {nome: [] for nome in TABELAS_META}
    for x in leitura.campanhas:
        saida["trafego_meta_campaign"].append({
            "meta_campaign_id": campanhas[x.id_externo],
            "ad_account_ativo_id": conta_ativo_id,
            "external_id": x.id_externo,
            "nome": x.nome,
            "status": x.status,
            "effective_status": x.effective_status,
            "objetivo": x.objetivo,
            "observado_em": observado_em,
            "ultima_vez_visto_em": observado_em,
        })
    for x in leitura.conjuntos:
        if x.parent_id_externo not in campanhas:
            raise dom.ContratoMetaInvalido("adset aponta para campanha fora da leitura")
        saida["trafego_meta_adset"].append({
            "meta_adset_id": conjuntos[x.id_externo],
            "meta_campaign_id": campanhas[x.parent_id_externo],
            "external_id": x.id_externo,
            "nome": x.nome,
            "status": x.status,
            "effective_status": x.effective_status,
            "optimization_goal": x.optimization_goal,
            "observado_em": observado_em,
            "ultima_vez_visto_em": observado_em,
        })
    for x in leitura.anuncios:
        if x.parent_id_externo not in conjuntos:
            raise dom.ContratoMetaInvalido("ad aponta para adset fora da leitura")
        meta_ad_id = dom.id_interno(
            conta_externa=conta, tipo="ad", id_externo_meta=x.id_externo)
        saida["trafego_meta_ad"].append({
            "meta_ad_id": meta_ad_id,
            "meta_adset_id": conjuntos[x.parent_id_externo],
            "external_id": x.id_externo,
            "nome": x.nome,
            "status": x.status,
            "effective_status": x.effective_status,
            "observado_em": observado_em,
            "ultima_vez_visto_em": observado_em,
        })
        if x.creative_id_externo is not None:
            if x.creative_id_externo not in criativos:
                raise dom.ContratoMetaInvalido(
                    "ad aponta para creative fora da leitura")
            saida["trafego_meta_ad_creative_binding"].append({
                "meta_ad_id": meta_ad_id,
                "meta_creative_id": criativos[x.creative_id_externo],
                "observado_em": observado_em,
            })
    for x in leitura.criativos:
        saida["trafego_meta_creative"].append({
            "meta_creative_id": criativos[x.id_externo],
            "ad_account_ativo_id": conta_ativo_id,
            "external_id": x.id_externo,
            "nome": x.nome,
            "object_story_id": x.object_story_id,
            "observado_em": observado_em,
            "ultima_vez_visto_em": observado_em,
        })
    return saida


def linhas_de_insights(
    insights: list[dom.InsightMeta] | tuple[dom.InsightMeta, ...],
    *,
    conta_ativo_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """Map insight facts/actions without flattening actions or converting NULL to zero."""
    if not conta_ativo_id.strip():
        raise dom.ContratoMetaInvalido("ativo da conta Meta vazio")
    saida = {"trafego_meta_insight_daily": [], "trafego_meta_insight_action": []}
    for idx, insight in enumerate(insights):
        fato_id = dom.id_interno(
            conta_externa=insight.conta_externa,
            tipo="campaign" if insight.nivel == "account" else "campaign" if insight.nivel == "campaign" else "adset" if insight.nivel == "adset" else "ad",
            id_externo_meta=insight.objeto_externo if insight.nivel != "account" else insight.conta_externa,
        ) + f":{insight.periodo_inicio}:{insight.periodo_fim}:{insight.nivel}:{idx}"
        saida["trafego_meta_insight_daily"].append({
            "meta_insight_daily_id": fato_id,
            "ad_account_ativo_id": conta_ativo_id,
            "provider": insight.provider,
            "conta_externa": insight.conta_externa,
            "nivel": insight.nivel,
            "objeto_externo": insight.objeto_externo,
            "periodo_inicio": insight.periodo_inicio,
            "periodo_fim": insight.periodo_fim,
            "janela_atribuicao": insight.janela_atribuicao,
            "breakdown": insight.breakdown,
            "observado_em": insight.observado_em,
            "spend": insight.spend,
            "impressions": insight.impressions,
            "reach": insight.reach,
            "frequency": insight.frequency,
            "clicks": insight.clicks,
            "inline_link_clicks": insight.inline_link_clicks,
            "landing_page_views": insight.landing_page_views,
            "cpm": insight.cpm,
            "cpc": insight.cpc,
            "ctr": insight.ctr,
        })
        for pos, action in enumerate(insight.actions):
            saida["trafego_meta_insight_action"].append({
                "meta_insight_daily_id": fato_id,
                "ordem": pos,
                "action_type": action.action_type,
                "value": action.value,
                "attribution_window": action.attribution_window,
                "object_level": action.object_level,
                "date_start": action.date_start,
                "date_stop": action.date_stop,
            })
    return saida


@dataclass
class EstadoDaConta:
    leitura: dom.LeituraDaHierarquia
    observado_em: datetime


class RepositorioMetaEmMemoria:
    """Strict fake: complete reads replace projection; failures never do."""
    def __init__(self) -> None:
        self.projecoes: dict[str, EstadoDaConta] = {}
        self.objetos: dict[tuple[str, str, str], dom.ObjetoMeta] = {}
        self.ausentes: set[tuple[str, str, str]] = set()
        self.recibos: list[dom.ReciboDeSync] = []
        self.insights: list[dom.InsightMeta] = []

    async def sucesso_por_chave(self, chave: str) -> dom.ReciboDeSync | None:
        return next((copy.deepcopy(r) for r in reversed(self.recibos)
                     if r.chave_de_idempotencia == chave and r.resultado == "ok"), None)

    async def ultimo_recibo(self) -> dom.ReciboDeSync | None:
        return copy.deepcopy(self.recibos[-1]) if self.recibos else None

    async def aplicar_leitura_completa(
        self,
        *,
        run_id: str,
        conta_ativo_id: str,
        leitura: dom.LeituraDaHierarquia,
        chave: str,
        iniciado_em: datetime,
        concluido_em: datetime,
    ) -> dom.ReciboDeSync:
        linhas_da_leitura(
            leitura, concluido_em, conta_ativo_id=conta_ativo_id,
        )  # validates hierarchy before commit
        recibo = dom.ReciboDeSync(
            run_id=run_id,
            chave_de_idempotencia=chave,
            conta_externa=leitura.conta_externa,
            resultado="ok",
            iniciado_em=iniciado_em,
            concluido_em=concluido_em,
            contagens=leitura.contagens,
            paginas_lidas=leitura.paginas_lidas,
        )
        atuais = {
            (leitura.conta_externa, obj.tipo, obj.id_externo)
            for obj in leitura.objetos
        }
        anteriores = {
            chave for chave in self.objetos if chave[0] == leitura.conta_externa
        }
        self.ausentes.update(anteriores - atuais)
        self.ausentes.difference_update(atuais)
        for obj in leitura.objetos:
            self.objetos[(leitura.conta_externa, obj.tipo, obj.id_externo)] = copy.deepcopy(obj)
        self.projecoes[leitura.conta_externa] = EstadoDaConta(
            copy.deepcopy(leitura), concluido_em)
        self.recibos.append(recibo)
        return copy.deepcopy(recibo)

    async def registrar_falha(
        self,
        *,
        run_id: str,
        conta_ativo_id: str,
        conta_externa: str,
        chave: str,
        iniciado_em: datetime,
        concluido_em: datetime,
        codigo: str,
        mensagem_segura: str,
    ) -> dom.ReciboDeSync:
        del conta_ativo_id
        recibo = dom.ReciboDeSync(
            run_id=run_id,
            chave_de_idempotencia=chave,
            conta_externa=conta_externa,
            resultado="falhou",
            iniciado_em=iniciado_em,
            concluido_em=concluido_em,
            contagens={},
            paginas_lidas=0,
            erro_codigo=codigo,
            erro_mensagem=mensagem_segura[:500],
        )
        self.recibos.append(recibo)
        return copy.deepcopy(recibo)
