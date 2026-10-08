"""`ConfiguracaoResolvida` → `MutateOperation`. Só tradução: quem julga é
`display_config.py`, quem ordena o grafo é `display.py`.

## Faixas de id temporário PRÓPRIAS de Display

`comum.py` aloca até -399 (asset groups). Display abre duas famílias que só
ele usa, abaixo disso, com vão entre elas:

    -400            lista de exclusão nova (SharedSet NEGATIVE_PLACEMENTS)
    -450 .. -454    assets de VÍDEO do YouTube criados por id (teto 5 do RDA)

Um id temporário é único no request inteiro, mesmo entre tipos — por isso a
faixa de vídeo não reaproveita a de imagem (-200…): um RDA com 20 imagens e 5
vídeos teria dois recursos disputando o mesmo número.
"""

from __future__ import annotations

from typing import Any

from . import comum
from .display_config import (
    MINUTOS,
    VIDEOS_MAX,
    AnuncioDisplay,
    ConfiguracaoResolvida,
    LanceResolvido,
)

T_LISTA_EXCLUSAO = -400
T_VIDEO_BASE = -450
#: Teto do nome de `Asset` aceito pela API (o nome da campanha aceita 255; o
#: do asset, não — medido com TOO_LONG num nome de ~140).
NOME_DE_ASSET_MAX = 128


def temp_video(cid: str, indice: int) -> str:
    if not 0 <= indice < VIDEOS_MAX:
        raise ValueError(f"vídeo nº {indice} fora da faixa de Display "
                         f"({T_VIDEO_BASE} a {T_VIDEO_BASE - VIDEOS_MAX + 1})")
    return comum.temp(cid, "assets", T_VIDEO_BASE - indice)


def temp_lista_exclusao(cid: str) -> str:
    return comum.temp(cid, "sharedSets", T_LISTA_EXCLUSAO)


def _selecionar(msg: Any) -> None:
    """Escolhe o ramo do oneof SEM inventar valor — "sem meta" nunca vira 0."""
    getattr(msg, "_pb", msg).SetInParent()


# ── campanha ───────────────────────────────────────────────────────────────


def aplicar_lance(c: Any, camp: Any, ag: Any, lance: LanceResolvido) -> None:
    """Reescreve o oneof de lance da campanha e o lance do grupo.

    `comum.op_campanha()` escreve `maximize_conversions.target_cpa_micros`
    para DISPLAY (0 sem meta; a meta com tCPA). A segunda forma a API RECUSA
    em Display — ver `display_config.ESTRATEGIAS`. Limpar o oneof e escrever
    de novo é a única forma de corrigir sem tocar no bloco compartilhado.
    """
    pb = getattr(camp, "_pb", camp)
    ramo = pb.WhichOneof("campaign_bidding_strategy")
    if ramo:
        pb.ClearField(ramo)

    forma = lance.forma_na_api
    if forma == "maximize_conversions":
        _selecionar(camp.maximize_conversions)
    elif forma == "target_cpa":
        camp.target_cpa.target_cpa_micros = lance.tcpa_micros
    elif forma == "maximize_conversion_value":
        if lance.target_roas:
            camp.maximize_conversion_value.target_roas = lance.target_roas
        else:
            _selecionar(camp.maximize_conversion_value)
    elif forma == "target_spend":
        if lance.teto_cpc_micros:
            camp.target_spend.cpc_bid_ceiling_micros = lance.teto_cpc_micros
        else:
            _selecionar(camp.target_spend)
    elif forma == "manual_cpc":
        # eCPC FALSE: quem escolheu manual quer o controle (mesma regra de Search).
        camp.manual_cpc.enhanced_cpc_enabled = False
    elif forma == "manual_cpm":
        _selecionar(camp.manual_cpm)
    else:  # pragma: no cover — `resolver_lance` fecha a lista
        raise ValueError(f"forma de lance desconhecida: {forma}")

    agpb = getattr(ag, "_pb", ag)
    if forma == "manual_cpm":
        # Sob vCPM o lance do grupo é por mil impressões visíveis; o CPC que
        # `comum.op_adgroup()` escreveu seria um segundo lance sem efeito.
        agpb.ClearField("cpc_bid_micros")
        ag.cpm_bid_micros = lance.cpm_micros
    elif forma == "manual_cpc":
        ag.cpc_bid_micros = lance.cpc_micros


def aplicar_campanha(c: Any, camp: Any, res: ConfiguracaoResolvida) -> None:
    """Frequência e tipo de geo — campos da própria `Campaign`."""
    E = c.enums
    for f in res.frequencia:
        cap = c.get_type("FrequencyCapEntry")
        cap.key.level = getattr(E.FrequencyCapLevelEnum, f.nivel.upper())
        cap.key.event_type = E.FrequencyCapEventTypeEnum.IMPRESSION
        cap.key.time_unit = getattr(E.FrequencyCapTimeUnitEnum, f.unidade.upper())
        cap.key.time_length = 1
        cap.cap = f.impressoes
        camp.frequency_caps.append(cap)
    camp.geo_target_type_setting.positive_geo_target_type = getattr(
        E.PositiveGeoTargetTypeEnum, res.presenca_geo)
    camp.geo_target_type_setting.negative_geo_target_type = (
        E.NegativeGeoTargetTypeEnum.PRESENCE)


def _cc(c: Any, cid: str, *, negativo: bool | None = None):
    o = c.get_type("MutateOperation")
    cr = o.campaign_criterion_operation.create
    cr.campaign = comum.temp(cid, "campaigns", comum.T_CAMPANHA)
    if negativo is not None:
        cr.negative = negativo
    return o, cr


def ops_criterios_de_campanha(c: Any, cid: str, res: ConfiguracaoResolvida) -> list:
    """Exclusões, dispositivos e agenda — `CampaignCriterion`."""
    E = c.enums
    ops = []
    for url in res.neg_placements:
        o, cr = _cc(c, cid, negativo=True); cr.placement.url = url; ops.append(o)
    for app in res.neg_apps:
        o, cr = _cc(c, cid, negativo=True); cr.mobile_application.app_id = app; ops.append(o)
    for cat in res.neg_categorias_de_app:
        o, cr = _cc(c, cid, negativo=True)
        cr.mobile_app_category.mobile_app_category_constant = cat; ops.append(o)
    for rot in res.neg_rotulos:
        o, cr = _cc(c, cid, negativo=True)
        cr.content_label.type_ = getattr(E.ContentLabelTypeEnum, rot); ops.append(o)
    for t in res.neg_topicos:
        o, cr = _cc(c, cid, negativo=True); cr.topic.topic_constant = t; ops.append(o)
    for d in res.dispositivos_excluidos:
        # -100% é o único ajuste de dispositivo que Smart Bidding respeita.
        o, cr = _cc(c, cid); cr.device.type_ = getattr(E.DeviceEnum, d)
        cr.bid_modifier = 0.0; ops.append(o)
    for j in res.agenda:
        o, cr = _cc(c, cid)
        s = cr.ad_schedule
        s.day_of_week = getattr(E.DayOfWeekEnum, j.dia.upper())
        s.start_hour, s.end_hour = j.inicio_hora, j.fim_hora
        s.start_minute = getattr(E.MinuteOfHourEnum, MINUTOS[j.inicio_minuto])
        s.end_minute = getattr(E.MinuteOfHourEnum, MINUTOS[j.fim_minuto])
        ops.append(o)
    return ops


def ops_listas_de_exclusao(c: Any, cid: str, res: ConfiguracaoResolvida) -> list:
    """Lista nova (SharedSet + SharedCriterion) e o vínculo de TODAS à campanha.

    Ordem: o SharedSet antes dos membros, e os dois antes do
    `campaign_shared_set` — id temporário só resolve depois de definido.
    """
    E = c.enums
    ops = []
    vinculos = list(res.listas_existentes)
    nova = res.lista_nova
    if nova is not None:
        rn = temp_lista_exclusao(cid)
        o = c.get_type("MutateOperation")
        ss = o.shared_set_operation.create
        ss.resource_name = rn
        ss.name = nova.nome
        ss.type_ = E.SharedSetTypeEnum.NEGATIVE_PLACEMENTS
        ops.append(o)
        for campo, valores in (("placement", nova.placements), ("mobile_application", nova.apps),
                               ("mobile_app_category", nova.categorias_de_app)):
            for v in valores:
                o = c.get_type("MutateOperation")
                sc = o.shared_criterion_operation.create
                sc.shared_set = rn
                if campo == "placement":
                    sc.placement.url = v
                elif campo == "mobile_application":
                    sc.mobile_application.app_id = v
                else:
                    sc.mobile_app_category.mobile_app_category_constant = v
                ops.append(o)
        vinculos.append(rn)
    for rn in vinculos:
        o = c.get_type("MutateOperation")
        css = o.campaign_shared_set_operation.create
        css.campaign = comum.temp(cid, "campaigns", comum.T_CAMPANHA)
        css.shared_set = rn
        ops.append(o)
    return ops


# ── ad group ───────────────────────────────────────────────────────────────


def aplicar_adgroup(c: Any, ag: Any, res: ConfiguracaoResolvida) -> None:
    """Optimized targeting e o modo dos públicos — sempre escritos, nunca default."""
    ag.optimized_targeting_enabled = res.segmentacao_otimizada
    tr = c.get_type("TargetRestriction")
    tr.targeting_dimension = c.enums.TargetingDimensionEnum.AUDIENCE
    tr.bid_only = res.publicos_em_observacao
    ag.targeting_setting.target_restrictions.append(tr)


def ops_criterios_de_adgroup(c: Any, cid: str, res: ConfiguracaoResolvida) -> list:
    ag_rn = comum.temp_adgroup(cid, 0)
    E = c.enums
    ops = []

    def novo():
        o = c.get_type("MutateOperation")
        cr = o.ad_group_criterion_operation.create
        cr.ad_group = ag_rn
        ops.append(o)
        return cr

    for v in res.listas_de_usuarios:
        novo().user_list.user_list = v
    for v in res.publicos_personalizados:
        novo().custom_audience.custom_audience = v
    for v in res.publicos_combinados:
        novo().combined_audience.combined_audience = v
    for v in res.interesses:
        novo().user_interest.user_interest_category = v
    for v in res.topicos:
        novo().topic.topic_constant = v
    for v in res.placements:
        novo().placement.url = v
    for v in res.palavras_chave:
        cr = novo()
        cr.keyword.text = v
        cr.keyword.match_type = E.KeywordMatchTypeEnum.BROAD
    return ops


# ── anúncio ────────────────────────────────────────────────────────────────


def ops_videos(c: Any, cid: str, ids: tuple[str, ...], nome_base: str) -> tuple[list, list[str]]:
    """`YoutubeVideoAsset` por id, no mesmo mutate. Devolve (ops, resource names)."""
    ops, rns = [], []
    for i, vid in enumerate(ids):
        rn = temp_video(cid, i)
        o = c.get_type("MutateOperation")
        a = o.asset_operation.create
        a.resource_name = rn
        # ⚠️ Cortado no teto do `Asset.name`: com a marca do canário no nome
        # da campanha, `nome_base` passa de 120 caracteres e a API recusa o
        # mutate inteiro (`string_length_error.TOO_LONG @asset_operation.
        # create.name`, validate_only na Crédito Up, 08/10/2026). O id do
        # vídeo fica — é ele que torna o nome único.
        sufixo = f" video {vid}"
        a.name = f"{nome_base[:NOME_DE_ASSET_MAX - len(sufixo)]}{sufixo}"
        a.type_ = c.enums.AssetTypeEnum.YOUTUBE_VIDEO
        a.youtube_video_asset.youtube_video_id = vid
        ops.append(o)
        rns.append(rn)
    return ops, rns


def aplicar_rda(c: Any, rda: Any, a: AnuncioDisplay) -> None:
    if a.chamada_para_acao:
        rda.call_to_action_text = a.chamada_para_acao.strip()
    if a.cor_principal and a.cor_destaque:
        rda.main_color = a.cor_principal.upper()
        rda.accent_color = a.cor_destaque.upper()
    rda.allow_flexible_color = bool(a.cores_flexiveis)
    rda.format_setting = getattr(c.enums.DisplayAdFormatSettingEnum, a.formato.upper())
    rda.control_spec.enable_asset_enhancements = bool(a.melhorias_de_asset)
    rda.control_spec.enable_autogen_video = bool(a.video_automatico)
