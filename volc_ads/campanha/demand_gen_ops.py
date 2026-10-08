"""Tradução das decisões v25.2 de Demand Gen em `MutateOperation`.

Só monta protobuf; quem decide se pode montar é `demand_gen.py` (validação) e
quem descreve a decisão é `demand_gen_config.py` (stdlib). Nada aqui chama rede.

## Faixas de id temporário (próprias deste canal)

`comum.py` aloca até -399. Demand Gen ganha uma faixa própria, longe da de
Display (`display_ops.py` usa -400 e -450..-454) para que a leitura de um
payload nunca precise perguntar de qual canal o id veio:

    -500 .. -549   assets NÃO-imagem do anúncio: vídeos do YouTube (≤5),
                   CTA de vídeo (≤1) e cartões de carrossel (≤10)
    -550 .. -559   user lists lookalike criadas no mesmo mutate (≤10)
    -560 .. -569   Audience composta (hoje uma por grupo)

Id temporário é único no request inteiro, entre tipos — por isso a faixa é
declarada e a fronteira levanta antes de emitir.
"""

from __future__ import annotations

from . import comum
from .demand_gen_config import (
    AUTOMACOES_POR_FORMATO,
    FAIXAS_ETARIAS,
    MINUTOS,
    PAPEIS_DO_CARTAO,
    CartaoCarrosselDemandGen,
    ConfiguracaoDemandGenV25,
    FaixaDeAgendaDemandGen,
    LanceDemandGen,
    LookalikeDemandGen,
    PublicoDemandGen,
)

T_ASSET_DG_BASE, T_ASSET_DG_MAX = -500, 50
T_USER_LIST_BASE, T_USER_LIST_MAX = -550, 10
T_AUDIENCIA_BASE, T_AUDIENCIA_MAX = -560, 10


def _faixa(cid: str, colecao: str, base: int, teto: int, indice: int, rotulo: str) -> str:
    if not 0 <= indice < teto:
        raise ValueError(
            f"{rotulo} nº {indice} fora da faixa reservada ({teto} ids, "
            f"{base} a {base - teto + 1}); o próximo id invadiria outra faixa "
            "e a referência cruzada apontaria para o recurso errado")
    return comum.temp(cid, colecao, base - indice)


def temp_asset_dg(cid: str, indice: int) -> str:
    return _faixa(cid, "assets", T_ASSET_DG_BASE, T_ASSET_DG_MAX, indice,
                  "asset Demand Gen")


def temp_user_list(cid: str, indice: int) -> str:
    return _faixa(cid, "userLists", T_USER_LIST_BASE, T_USER_LIST_MAX, indice,
                  "user list")


def temp_audiencia(cid: str, indice: int) -> str:
    return _faixa(cid, "audiences", T_AUDIENCIA_BASE, T_AUDIENCIA_MAX, indice,
                  "audience")


# ── lance ───────────────────────────────────────────────────────────────────


def aplicar_lance(camp, lance: LanceDemandGen, micros) -> None:
    """Troca o ramo do oneof que `comum.op_campanha` selecionou (MaxConv vazio).

    `micros` é `Brief.micros`. A meta sempre vai na estratégia AVULSA: dentro de
    MaxConv/MaxConvValue a API recusa em Demand Gen (medido).
    """
    camp._pb.ClearField("maximize_conversions")
    campo = lance.campo_do_proto
    if campo == "maximize_conversions":
        comum._selecionar_ramo_vazio(camp.maximize_conversions, "MaximizeConversions")
    elif campo == "target_cpa":
        camp.target_cpa.target_cpa_micros = micros(lance.target_cpa)
    elif campo == "maximize_conversion_value":
        comum._selecionar_ramo_vazio(
            camp.maximize_conversion_value, "MaximizeConversionValue")
    elif campo == "target_roas":
        camp.target_roas.target_roas = float(lance.target_roas)
    elif campo == "target_spend":
        # Sem teto de CPC: `cpc_bid_ceiling_micros` é recusado em DG (medido).
        comum._selecionar_ramo_vazio(camp.target_spend, "TargetSpend")
    elif campo == "target_cpc":
        camp.target_cpc.target_cpc_micros = micros(lance.target_cpc)
    else:  # guarda de profundidade; LanceDemandGen não produz outro nome
        raise ValueError(f"ramo de lance desconhecido: {campo}")


# ── agenda ──────────────────────────────────────────────────────────────────


def op_agenda(c, cid: str, faixa: FaixaDeAgendaDemandGen):
    o = c.get_type("MutateOperation")
    cr = o.campaign_criterion_operation.create
    cr.campaign = comum.temp(cid, "campaigns", comum.T_CAMPANHA)
    hi, mi, hf, mf = faixa.partes()
    ag = cr.ad_schedule
    ag.day_of_week = getattr(c.enums.DayOfWeekEnum, faixa.dia)
    ag.start_hour = hi
    ag.start_minute = getattr(c.enums.MinuteOfHourEnum, MINUTOS[mi])
    ag.end_hour = hf
    ag.end_minute = getattr(c.enums.MinuteOfHourEnum, MINUTOS[mf])
    return o


# ── públicos ────────────────────────────────────────────────────────────────


def op_lookalike(c, cid: str, indice: int, lal: LookalikeDemandGen):
    o = c.get_type("MutateOperation")
    u = o.user_list_operation.create
    u.resource_name = temp_user_list(cid, indice)
    u.name = lal.nome
    info = u.lookalike_user_list
    info.seed_user_list_ids.extend(lal.sementes)
    info.expansion_level = getattr(c.enums.LookalikeExpansionLevelEnum, lal.expansao)
    info.country_codes.extend(lal.paises)
    return o


def op_audiencia(c, cid: str, indice: int, publico: PublicoDemandGen,
                 lookalikes_rn: list[str]):
    """A `Audience` composta. Ordem das dimensões estável (o selo cobre bytes)."""
    o = c.get_type("MutateOperation")
    a = o.audience_operation.create
    a.resource_name = temp_audiencia(cid, indice)
    a.name = publico.nome
    E = c.enums
    if publico.idades:
        faixas = []
        for rotulo in publico.idades:
            minimo, maximo = FAIXAS_ETARIAS[rotulo]
            faixa = {"min_age": minimo}
            if maximo is not None:
                faixa["max_age"] = maximo
            faixas.append(faixa)
        a.dimensions.append({"age": {
            "age_ranges": faixas,
            "include_undetermined": publico.incluir_idade_indeterminada}})
    if publico.generos:
        a.dimensions.append({"gender": {
            "genders": [getattr(E.GenderTypeEnum, g) for g in publico.generos],
            "include_undetermined": publico.incluir_genero_indeterminado}})
    if publico.rendas:
        a.dimensions.append({"household_income": {
            "income_ranges": [getattr(E.IncomeRangeTypeEnum, x)
                              for x in publico.rendas],
            "include_undetermined": publico.incluir_renda_indeterminada}})
    if publico.status_parentais:
        a.dimensions.append({"parental_status": {
            "parental_statuses": [getattr(E.ParentalStatusTypeEnum, x)
                                  for x in publico.status_parentais],
            "include_undetermined":
                publico.incluir_status_parental_indeterminado}})
    segmentos = [*publico.user_lists, *lookalikes_rn]
    if segmentos:
        a.dimensions.append({"audience_segments": {
            "segments": [{"user_list": {"user_list": rn}} for rn in segmentos]}})
    for rn in publico.exclusoes_user_list:
        a.exclusion_dimension.exclusions.append({"user_list": {"user_list": rn}})
    return o


# ── assets não-imagem ───────────────────────────────────────────────────────


def op_asset_youtube(c, cid: str, indice: int, youtube_id: str):
    """Asset YOUTUBE_VIDEO a partir do id, no mesmo mutate.

    Sem `name`: asset de vídeo é deduplicado pelo conteúdo, e um nome diferente
    de um asset igual já existente vira `DUPLICATE_ASSETS_WITH_DIFFERENT_FIELD_VALUE`.
    """
    o = c.get_type("MutateOperation")
    a = o.asset_operation.create
    a.resource_name = temp_asset_dg(cid, indice)
    a.type_ = c.enums.AssetTypeEnum.YOUTUBE_VIDEO
    a.youtube_video_asset.youtube_video_id = youtube_id
    return o


def op_asset_cta(c, cid: str, indice: int, tipo: str):
    o = c.get_type("MutateOperation")
    a = o.asset_operation.create
    a.resource_name = temp_asset_dg(cid, indice)
    a.type_ = c.enums.AssetTypeEnum.CALL_TO_ACTION
    a.call_to_action_asset.call_to_action = getattr(c.enums.CallToActionTypeEnum, tipo)
    return o


def op_asset_cartao(c, cid: str, indice: int, cartao: CartaoCarrosselDemandGen,
                    imagens_rn: dict[str, str], url_final: str):
    """Um `DemandGenCarouselCardAsset`. `imagens_rn` traz resource names REMOTOS."""
    o = c.get_type("MutateOperation")
    a = o.asset_operation.create
    a.resource_name = temp_asset_dg(cid, indice)
    a.type_ = c.enums.AssetTypeEnum.DEMAND_GEN_CAROUSEL_CARD
    a.final_urls.append(url_final)
    card = a.demand_gen_carousel_card_asset
    for papel, campo in PAPEIS_DO_CARTAO.items():
        if papel in imagens_rn:
            setattr(card, campo, imagens_rn[papel])
    card.headline = cartao.headline.strip()
    if cartao.call_to_action is not None:
        card.call_to_action_text = cartao.call_to_action
    return o


# ── anúncio ─────────────────────────────────────────────────────────────────


def declarar_automacoes(c, ada, formato: str, cfg: ConfiguracaoDemandGenV25 | None) -> None:
    """Todas as automações aplicáveis ao formato, explícitas. Default OPTED_OUT."""
    for tipo in AUTOMACOES_POR_FORMATO[formato]:
        status = cfg.status_da_automacao(tipo) if cfg is not None else "OPTED_OUT"
        ada.ad_group_ad_asset_automation_settings.append({
            "asset_automation_type": getattr(c.enums.AssetAutomationTypeEnum, tipo),
            "asset_automation_status": getattr(
                c.enums.AssetAutomationStatusEnum, status),
        })


def _textos(c, destino, textos: list[str]) -> None:
    for texto in textos:
        asset = c.get_type("AdTextAsset")
        asset.text = texto
        destino.append(asset)


def preencher_video(c, ada, *, nome: str, headlines, long_headlines,
                    descriptions, business_name: str, logo_rn: str,
                    videos_rn: list[str], cta_rn: str | None,
                    breadcrumb1: str | None, breadcrumb2: str | None) -> None:
    # `ad.name` é OBRIGATÓRIO no vídeo responsivo (field_error.REQUIRED, medido)
    # e não existe nos outros dois formatos — por isso nasce só aqui.
    ada.ad.name = nome
    info = ada.ad.demand_gen_video_responsive_ad
    _textos(c, info.headlines, headlines)
    _textos(c, info.long_headlines, long_headlines)
    _textos(c, info.descriptions, descriptions)
    info.business_name.text = business_name
    for rn in videos_rn:
        info.videos.append({"asset": rn})
    info.logo_images.append({"asset": logo_rn})
    if cta_rn is not None:
        info.call_to_actions.append({"asset": cta_rn})
    if breadcrumb1 is not None:
        info.breadcrumb1 = breadcrumb1.strip()
    if breadcrumb2 is not None:
        info.breadcrumb2 = breadcrumb2.strip()


def preencher_carrossel(c, ada, *, headline: str, description: str,
                        business_name: str, logo_rn: str, cartoes_rn: list[str],
                        call_to_action: str | None) -> None:
    info = ada.ad.demand_gen_carousel_ad
    info.business_name = business_name
    info.logo_image.asset = logo_rn
    info.headline.text = headline
    info.description.text = description
    if call_to_action is not None:
        info.call_to_action_text = call_to_action
    for rn in cartoes_rn:
        info.carousel_cards.append({"asset": rn})
