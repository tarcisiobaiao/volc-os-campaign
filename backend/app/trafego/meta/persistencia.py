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
    "trafego_meta_campaign",
    "trafego_meta_adset",
    "trafego_meta_ad",
    "trafego_meta_creative",
    "trafego_meta_ad_creative_binding",
    "trafego_meta_sync_run",
)


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

    async def sucesso_por_chave(self, chave: str) -> dom.ReciboDeSync | None:
        return next((copy.deepcopy(r) for r in reversed(self.recibos)
                     if r.chave_de_idempotencia == chave and r.resultado == "ok"), None)

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
