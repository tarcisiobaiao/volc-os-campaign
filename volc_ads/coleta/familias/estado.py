"""Família `estado`: status, status primário, motivos e política por entidade.

É o estado ATUAL (sem `segments.date`): a janela do contexto não entra na GAQL.
O banco só grava linha nova quando o `estado_hash` muda, então rodar várias
vezes ao dia custa leitura, não linha.
"""
from __future__ import annotations

from typing import Any

from ..contrato import Contexto, enum_nome

# Uma consulta por entidade. A ordem importa para `normalizar`: as linhas não
# dizem de qual GAQL vieram, e a entidade é deduzida pelo recurso mais
# específico presente (ad_group_ad também traz ad_group e campaign).
GAQLS = {
    "keyword": (
        "SELECT ad_group_criterion.resource_name, ad_group_criterion.criterion_id, "
        "ad_group_criterion.status, ad_group_criterion.primary_status, "
        "ad_group_criterion.primary_status_reasons, ad_group_criterion.approval_status, "
        "ad_group.id, campaign.id "
        "FROM ad_group_criterion "
        "WHERE ad_group_criterion.type = 'KEYWORD' "
        "AND ad_group_criterion.status != 'REMOVED' "
        "AND ad_group.status != 'REMOVED' AND campaign.status != 'REMOVED'"
    ),
    "asset_group_asset": (
        "SELECT asset_group_asset.resource_name, asset_group_asset.status, "
        "asset_group_asset.primary_status, asset_group_asset.primary_status_reasons, "
        "asset_group_asset.policy_summary.approval_status, "
        "asset_group_asset.policy_summary.review_status, "
        "asset_group_asset.policy_summary.policy_topic_entries, "
        "asset_group.id, campaign.id "
        "FROM asset_group_asset "
        "WHERE asset_group_asset.status != 'REMOVED' "
        "AND asset_group.status != 'REMOVED' AND campaign.status != 'REMOVED'"
    ),
    "campaign_asset": (
        "SELECT campaign_asset.resource_name, campaign_asset.status, "
        "campaign_asset.primary_status, campaign_asset.primary_status_reasons, "
        # A política do ASSET vinculado (sitelink, callout, imagem…). Sem ela a
        # família dizia "status do vínculo" e calava a reprovação do texto.
        # Lido contra a conta real em 14/10/2026: 71 linhas, sem erro de FROM.
        "asset.policy_summary.approval_status, asset.policy_summary.review_status, "
        "asset.policy_summary.policy_topic_entries, campaign.id, "
        # Só aqui a API exige o campo do filtro no SELECT (EXPECTED_REFERENCED_FIELD_IN_SELECT_CLAUSE).
        "campaign.status "
        "FROM campaign_asset "
        "WHERE campaign_asset.status != 'REMOVED' AND campaign.status != 'REMOVED'"
    ),
    "ad_group_ad": (
        "SELECT ad_group_ad.resource_name, ad_group_ad.status, ad_group_ad.primary_status, "
        "ad_group_ad.primary_status_reasons, ad_group_ad.policy_summary.approval_status, "
        "ad_group_ad.policy_summary.review_status, "
        "ad_group_ad.policy_summary.policy_topic_entries, ad_group.id, campaign.id "
        "FROM ad_group_ad "
        "WHERE ad_group_ad.status != 'REMOVED' "
        "AND ad_group.status != 'REMOVED' AND campaign.status != 'REMOVED'"
    ),
    "asset_group": (
        "SELECT asset_group.id, asset_group.status, asset_group.primary_status, "
        "asset_group.primary_status_reasons, campaign.id "
        "FROM asset_group "
        "WHERE asset_group.status != 'REMOVED' AND campaign.status != 'REMOVED'"
    ),
    "ad_group": (
        "SELECT ad_group.id, ad_group.status, ad_group.primary_status, "
        "ad_group.primary_status_reasons, campaign.id "
        "FROM ad_group "
        "WHERE ad_group.status != 'REMOVED' AND campaign.status != 'REMOVED'"
    ),
    "campaign": (
        "SELECT campaign.id, campaign.status, campaign.primary_status, "
        "campaign.primary_status_reasons "
        "FROM campaign "
        "WHERE campaign.status != 'REMOVED'"
    ),
}

# Recurso da GoogleAdsRow que identifica cada entidade, do mais específico ao
# mais genérico.
_RECURSO = {
    "keyword": "ad_group_criterion",
    "asset_group_asset": "asset_group_asset",
    "campaign_asset": "campaign_asset",
    "ad_group_ad": "ad_group_ad",
    "asset_group": "asset_group",
    "ad_group": "ad_group",
    "campaign": "campaign",
}


def _entidade(row: Any) -> str | None:
    for tipo, recurso in _RECURSO.items():
        if recurso in row:
            return tipo
    return None


def _sufixo(resource_name: str) -> str | None:
    # O último segmento do resource name é o id composto estável
    # (`{ad_group_id}~{criterion_id}`, `{asset_group_id}~{asset_id}~{field_type}`…).
    if not resource_name:
        return None
    return resource_name.rsplit("/", 1)[-1] or None


def _motivos(repetido: Any) -> list[str]:
    return [enum_nome(m) for m in repetido]


def _evidencia(ev: Any) -> dict:
    """O PORQUÊ do tópico, como a API mandou. Só as formas presentes."""
    d: dict = {}
    if ev.text_list.texts:
        d["text_list"] = list(ev.text_list.texts)
    if ev.website_list.websites:
        d["website_list"] = list(ev.website_list.websites)
    if ev.destination_text_list.destination_texts:
        d["destination_text_list"] = list(ev.destination_text_list.destination_texts)
    if ev.destination_mismatch.url_types:
        d["destination_mismatch_url_types"] = [enum_nome(t) for t in ev.destination_mismatch.url_types]
    dnw = ev.destination_not_working
    if dnw.expanded_url or dnw.http_error_code or dnw.last_checked_date_time:
        d["destination_not_working"] = {
            "expanded_url": dnw.expanded_url or None,
            "device": enum_nome(dnw.device),
            "http_error_code": dnw.http_error_code or None,
            "dns_error_type": enum_nome(dnw.dns_error_type),
            "last_checked": dnw.last_checked_date_time or None,
        }
    if ev.language_code:
        d["language_code"] = ev.language_code
    return d


def _restricao(c: Any) -> dict:
    """ONDE o tópico limita (país, certificado, revenda). Só o que veio."""
    d: dict = {}
    for campo in ("country_constraint_list", "certificate_missing_in_country_list",
                  "certificate_domain_mismatch_in_country_list"):
        lista = getattr(c, campo)
        if lista.countries:
            d[campo] = {"total_alvo": lista.total_targeted_countries or None,
                        "paises": [p.country_criterion for p in lista.countries]}
    if "reseller_constraint" in c:
        d["reseller_constraint"] = True
    return d


def _topicos(politica: Any) -> list[dict]:
    """Tópico, tipo e — quando a API manda — evidências e restrições.

    Até 14/10/2026 só `topic` e `type` eram guardados: o motivo (texto ou URL
    que violou, destino quebrado, país restrito) vinha de graça na mesma linha
    e era jogado fora. Medido na conta real: um anúncio FULLY_LIMITED em
    GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES com uma restrição declarada.
    Chaves só aparecem quando há conteúdo, então tópico sem evidência mantém
    exatamente a forma (e o `estado_hash`) de antes.
    """
    saida = []
    for t in politica.policy_topic_entries:
        item: dict = {"topic": t.topic, "type": enum_nome(t.type_)}
        evidencias = [e for e in (_evidencia(ev) for ev in t.evidences) if e]
        restricoes = [r for r in (_restricao(c) for c in t.constraints) if r]
        if evidencias:
            item["evidences"] = evidencias
        if restricoes:
            item["constraints"] = restricoes
        if len(t.constraints) > len(restricoes):
            # Medido em 14/10/2026: FULLY_LIMITED com uma restrição VAZIA (nenhum
            # campo preenchido). Não há país a guardar, mas a API disse que há
            # restrição — o fato fica, sem inventar o conteúdo.
            item["constraints_sem_detalhe"] = len(t.constraints) - len(restricoes)
        saida.append(item)
    return saida


def _id_texto(valor: int) -> str | None:
    return str(valor) if valor else None


class _Estado:
    nome = "estado"
    rpc = "volc_registrar_gads_fatos"

    def gaql(self, ctx: Contexto) -> list[str]:
        return list(GAQLS.values())

    def normalizar(self, row: Any, ctx: Contexto) -> dict | None:
        tipo = _entidade(row)
        if tipo is None:
            return None
        msg = getattr(row, _RECURSO[tipo])
        if tipo in ("campaign", "ad_group", "asset_group"):
            entidade_id = _id_texto(msg.id)
        else:
            entidade_id = _sufixo(msg.resource_name)
        if entidade_id is None:
            return None

        aprovacao = revisao = None
        topicos: list[dict] = []
        if tipo in ("ad_group_ad", "asset_group_asset"):
            aprovacao = enum_nome(msg.policy_summary.approval_status)
            revisao = enum_nome(msg.policy_summary.review_status)
            topicos = _topicos(msg.policy_summary)
        elif tipo == "campaign_asset":
            aprovacao = enum_nome(row.asset.policy_summary.approval_status)
            revisao = enum_nome(row.asset.policy_summary.review_status)
            topicos = _topicos(row.asset.policy_summary)
        elif tipo == "keyword":
            aprovacao = enum_nome(msg.approval_status)

        return {
            "entidade_tipo": tipo,
            "entidade_id": entidade_id,
            "campaign_id": _id_texto(row.campaign.id),
            "status": enum_nome(msg.status),
            "primary_status": enum_nome(msg.primary_status),
            "primary_status_reasons": _motivos(msg.primary_status_reasons),
            "aprovacao": aprovacao,
            "revisao": revisao,
            "topicos_politica": topicos,
            "observado_em": ctx.colhida_iso,
        }


FAMILIA = _Estado()
