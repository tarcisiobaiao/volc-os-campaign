"""Parser da chave de campanha: valor de UTM/key-value → `campaign.id` do Google Ads.

O template vivo (Final URL suffix da campanha 24278665189, recibo
`043c77f5:.claude-ads/runs/google-ads-recovery-20261015T125729-0300/receipts/d-live-campaign-audit.json:37`)
põe `utm_campaign={campaignid}`. Logo, um valor só de dígitos É o id — desde que a fonte
não o tenha mutilado. O parser recusa explicitamente tudo o que não permite essa leitura,
com motivo tipado, em vez de "adivinhar" por nome.
"""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Optional

from .normalizacao import LIMITE_VALOR_UTM, MotivoDescarte, diagnosticar_utm_sensor_v3

_ID = re.compile(r"[0-9]{1,20}")
_MACRO = re.compile(r"^\{\{?[^{}]+\}?\}$")


class OrigemValor(str, enum.Enum):
    URL_CRUA = "url_crua"  # valor como chegou na URL (Ads ValueTrack expandido, GA4)
    SENSOR_V3 = "sensor_v3"  # payload.utm.campaign em raw_events (já normalizado)
    JOINADS = "joinads"  # custom_value com custom_key=utm_campaign
    GAM = "gam"  # gam_metrics.utm_campaign_value


class MotivoRecusa(str, enum.Enum):
    AUSENTE = "ausente"
    DESCARTADO_PELO_SENSOR = "descartado_pelo_sensor"  # número >= 10 dígitos vira '' no sensor
    MACRO_NAO_EXPANDIDA = "macro_nao_expandida"  # '{campaignid}', '{{campaign.id}}'
    CHAVE_TROCADA = "chave_trocada"  # JoinAds devolveu outra custom_key (land_uri '/')
    TEXTUAL_AMBIGUO = "textual_ambiguo"  # nome/slug: só resolve por mapa declarado e datado
    POSSIVELMENTE_TRUNCADO = "possivelmente_truncado"  # 40 unidades: pode colidir com outro nome
    ID_INVALIDO = "id_invalido"  # dígitos demais/zeros à esquerda


@dataclass(frozen=True)
class ChaveCampanha:
    """Resultado do parser. Ou `campaign_id` (texto de dígitos) ou `recusa` — nunca os dois."""

    valor_bruto: Optional[str]
    origem: OrigemValor
    campaign_id: Optional[str] = None
    recusa: Optional[MotivoRecusa] = None
    valor_textual: Optional[str] = None  # forma normalizada, útil para mapa declarado

    def __post_init__(self) -> None:
        if (self.campaign_id is None) == (self.recusa is None):
            raise ValueError("ChaveCampanha precisa de exatamente um: campaign_id ou recusa")

    @property
    def resolvida(self) -> bool:
        return self.campaign_id is not None


def interpretar_chave_campanha(
    valor: Optional[str],
    origem: OrigemValor,
    *,
    custom_key: Optional[str] = None,
    custom_key_pedida: str = "utm_campaign",
) -> ChaveCampanha:
    """Interpreta um valor de `utm_campaign` vindo de `origem`.

    Regras (em ordem): chave trocada (JoinAds) → ausente → macro literal → dígitos = id →
    texto (ambíguo; truncamento sinalizado). Para `URL_CRUA`, aplica antes o filtro do sensor
    só para DIAGNÓSTICO (o id cru continua válido; a perda acontece depois, no sensor).
    """
    if custom_key is not None and custom_key.strip() != custom_key_pedida:
        return ChaveCampanha(valor, origem, recusa=MotivoRecusa.CHAVE_TROCADA)
    bruto = None if valor is None else str(valor).strip()
    if not bruto or bruto.lower() == "null":
        return ChaveCampanha(valor, origem, recusa=MotivoRecusa.AUSENTE)
    if _MACRO.match(bruto):
        return ChaveCampanha(valor, origem, recusa=MotivoRecusa.MACRO_NAO_EXPANDIDA)
    if bruto.isascii() and bruto.isdigit():
        if not _ID.fullmatch(bruto) or (len(bruto) > 1 and bruto.startswith("0")):
            return ChaveCampanha(valor, origem, recusa=MotivoRecusa.ID_INVALIDO)
        return ChaveCampanha(valor, origem, campaign_id=bruto)
    if bruto.startswith("/") or "://" in bruto:
        return ChaveCampanha(valor, origem, recusa=MotivoRecusa.CHAVE_TROCADA)
    textual = diagnosticar_utm_sensor_v3(bruto)[0] if origem is not OrigemValor.SENSOR_V3 else bruto
    if len(textual.encode("utf-16-le")) // 2 >= LIMITE_VALOR_UTM:
        return ChaveCampanha(valor, origem, recusa=MotivoRecusa.POSSIVELMENTE_TRUNCADO,
                             valor_textual=textual or None)
    return ChaveCampanha(valor, origem, recusa=MotivoRecusa.TEXTUAL_AMBIGUO,
                         valor_textual=textual or None)


def sobrevive_ao_sensor(valor_url: Optional[str]) -> tuple[bool, MotivoDescarte]:
    """O valor cru da URL chega a `raw_events.payload.utm.campaign`?"""
    v, motivo = diagnosticar_utm_sensor_v3(valor_url)
    return bool(v), motivo


def interpretar_campanha_da_sessao(
    campaign: Optional[str], *, paid: int, source: Optional[str], medium: Optional[str]
) -> ChaveCampanha:
    """Chave de campanha de uma sessão do sensor, distinguindo 'sem UTM' de 'UTM perdida'.

    Sessão paga do Google (`paid=1` ou google/cpc) sem `campaign` é perda conhecida do sensor
    (regex de PII), não tráfego orgânico — e é registrada como tal.
    """
    if not campaign:
        google_pago = paid == 1 or ((source or "") == "google" and (medium or "") == "cpc")
        motivo = MotivoRecusa.DESCARTADO_PELO_SENSOR if google_pago else MotivoRecusa.AUSENTE
        return ChaveCampanha(campaign, OrigemValor.SENSOR_V3, recusa=motivo)
    return interpretar_chave_campanha(campaign, OrigemValor.SENSOR_V3)
