"""Performance Max v25.2 — as operações novas do grafo, uma função por recurso.

Cada função devolve `MutateOperation` (ou, na fase 2, a operação do serviço
próprio) e não decide nada: quem decide é `pmax_config.checar` e o construtor
em `pmax.py`. Separar "o que pode" de "como se escreve" é o que permite testar a
régua sem cliente e o proto sem régua.

## As faixas de id temporário que este canal acrescenta

`comum.py` declara -1 .. -399 (orçamento, campanha, ad groups, texto, imagem,
asset group). PMax v25 precisa de mais duas famílias, e elas ficam AQUI, abaixo
de tudo que `comum` reserva, até `comum` as adotar:

    -400 .. -499   assets de VÍDEO do YouTube criados no mutate
    -500 .. -509   shared sets (lista de marcas excluídas criada no mutate)

Id temporário é único no request inteiro mesmo entre tipos — por isso a faixa,
e não um contador solto.
"""

from __future__ import annotations

from . import comum
from .pmax_config import (
    AUTOMACOES_PMAX_V25,
    ConfiguracaoPMaxV25,
    ExclusaoDeUrl,
    MarcaExcluida,
    MetaClienteNovo,
    MetaDeConversao,
    NegativaPMax,
    VideoYouTube,
)

T_VIDEO_BASE, T_VIDEO_MAX = -400, 100
T_SHARED_SET_BASE, T_SHARED_SET_MAX = -500, 10


def temp_video(cid: str, indice: int) -> str:
    if not 0 <= indice < T_VIDEO_MAX:
        raise ValueError(
            f"vídeo nº {indice} fora da faixa reservada ({T_VIDEO_MAX} vídeos, "
            f"ids {T_VIDEO_BASE} a {T_VIDEO_BASE - T_VIDEO_MAX + 1}); o próximo "
            f"invadiria a faixa de shared set")
    return comum.temp(cid, "assets", T_VIDEO_BASE - indice)


def temp_shared_set(cid: str, indice: int) -> str:
    if not 0 <= indice < T_SHARED_SET_MAX:
        raise ValueError(f"shared set nº {indice} fora da faixa reservada")
    return comum.temp(cid, "sharedSets", T_SHARED_SET_BASE - indice)


def _campanha(cid: str) -> str:
    return comum.temp(cid, "campaigns", comum.T_CAMPANHA)


# ═══════════════════════════════════════════════════════════════════════════
# CAMPANHA — o que `comum.op_campanha` emite e PMax v25 precisa corrigir
# ═══════════════════════════════════════════════════════════════════════════


def ajustar_campanha(c, camp, cfg: ConfiguracaoPMaxV25) -> None:
    """Reescreve, na campanha já montada por `comum`, o que é de PMax v25.2.

    1. `excluded_parent_asset_set_types` SAI. `comum` emite `[PAGE_FEED]` e a
       API recusa o mutate inteiro: `CampaignError.INVALID_EXCLUDED_PARENT_
       ASSET_SET_TYPE` ("The asset set type is invalid to be set in
       excluded_parent_asset_set_types field"), medido em validate_only na
       Crédito Up em 08/10/2026. O payload de PMax nunca tinha passado por
       validate_only em conta real — e a trava que isso pretendia (o clique não
       sair da LP) continua garantida por FINAL_URL_EXPANSION OPTED_OUT, que é
       a única coisa que consome page feed em PMax.
    2. `asset_automation_settings` é REDECLARADA inteira: as sete aplicáveis a
       PMax na v25.2, OPTED_OUT, exceto as que o dono optou. Omitir não é
       neutro — quatro delas nascem ligadas quando ninguém fala.
    3. `text_guidelines` e `brand_guidelines` quando declarados.
    """
    del camp.excluded_parent_asset_set_types[:]
    del camp.asset_automation_settings[:]

    optadas = set(cfg.automacoes_optadas)
    for tipo in AUTOMACOES_PMAX_V25:
        ligada = tipo in optadas
        item = {
            "asset_automation_type": getattr(c.enums.AssetAutomationTypeEnum, tipo),
            "asset_automation_status": (
                c.enums.AssetAutomationStatusEnum.OPTED_IN if ligada
                else c.enums.AssetAutomationStatusEnum.OPTED_OUT),
        }
        if tipo == "AUTOMATED_VIDEO_CRAWL" and ligada:
            item["automated_video_crawl_setting"] = {
                "automated_video_crawl_infos": [
                    {
                        "url": f.url,
                        "source_platform": getattr(
                            c.enums.VideoCrawlSourcePlatformEnum, f.plataforma),
                        "enabled": bool(f.habilitada),
                    }
                    for f in cfg.video_crawl
                ],
            }
        camp.asset_automation_settings.append(item)

    if cfg.termos_excluidos:
        camp.text_guidelines.term_exclusions.extend(cfg.termos_excluidos)
    for texto in cfg.restricoes_de_mensagem:
        camp.text_guidelines.messaging_restrictions.append({
            "restriction_text": texto,
            "restriction_type": (c.enums.MessagingRestrictionTypeEnum
                                 .RESTRICTION_BASED_EXCLUSION),
        })

    d = cfg.diretrizes_de_marca
    if d is not None:
        if d.cor_principal:
            camp.brand_guidelines.main_color = d.cor_principal
            camp.brand_guidelines.accent_color = d.cor_destaque
        if d.fonte:
            camp.brand_guidelines.predefined_font_family = d.fonte


# ═══════════════════════════════════════════════════════════════════════════
# CRITÉRIOS DE CAMPANHA E LISTAS
# ═══════════════════════════════════════════════════════════════════════════


def op_negativa(c, cid: str, negativa: NegativaPMax):
    o = c.get_type("MutateOperation")
    cr = o.campaign_criterion_operation.create
    cr.campaign = _campanha(cid)
    cr.negative = True
    cr.keyword.text = negativa.texto.strip()
    cr.keyword.match_type = getattr(c.enums.KeywordMatchTypeEnum, negativa.match_type)
    return o


def op_exclusao_de_url(c, cid: str, e: ExclusaoDeUrl):
    o = c.get_type("MutateOperation")
    cr = o.campaign_criterion_operation.create
    cr.campaign = _campanha(cid)
    cr.negative = True
    cr.webpage.criterion_name = e.nome
    cr.webpage.conditions.append({
        "operand": getattr(c.enums.WebpageConditionOperandEnum, e.operando),
        "operator": getattr(c.enums.WebpageConditionOperatorEnum, e.operador),
        "argument": e.argumento,
    })
    return o


def op_anexar_lista(c, cid: str, shared_set: str):
    """`CampaignSharedSet` — lista de negativas JÁ existente na conta."""
    o = c.get_type("MutateOperation")
    cs = o.campaign_shared_set_operation.create
    cs.campaign = _campanha(cid)
    cs.shared_set = shared_set
    return o


def ops_lista_de_marcas(c, cid: str, nome: str,
                        marcas: tuple[MarcaExcluida, ...]) -> tuple[str, list]:
    """SharedSet BRANDS + um SharedCriterion por marca, no MESMO mutate.

    Devolve `(resource_name temporário, operações)`. A lista nasce com o nome
    da campanha porque `SharedSet.name` é único na CONTA: um nome fixo faria a
    segunda campanha colidir com a primeira.
    """
    rn = temp_shared_set(cid, 0)
    o = c.get_type("MutateOperation")
    ss = o.shared_set_operation.create
    ss.resource_name = rn
    ss.name = nome
    ss.type_ = c.enums.SharedSetTypeEnum.BRANDS
    ops = [o]
    for m in marcas:
        oc = c.get_type("MutateOperation")
        sc = oc.shared_criterion_operation.create
        sc.shared_set = rn
        sc.brand.entity_id = m.entity_id
        ops.append(oc)
    return rn, ops


def op_exclusao_de_marcas(c, cid: str, shared_set: str):
    """`CampaignCriterion.brand_list` NEGATIVO. Positivo é recusado em PMax
    (`ONLY_EXCLUSION_BRAND_LIST_ALLOWED_FOR_CAMPAIGN_TYPE`, medido)."""
    o = c.get_type("MutateOperation")
    cr = o.campaign_criterion_operation.create
    cr.campaign = _campanha(cid)
    cr.negative = True
    cr.brand_list.shared_set = shared_set
    return o


def op_meta_de_conversao(c, cid: str, meta: MetaDeConversao):
    """`CampaignConversionGoal` — UPDATE, porque a API cria um por par
    (categoria, origem) da conta junto com a campanha. O id temporário da
    campanha resolve dentro do mesmo mutate (medido)."""
    o = c.get_type("MutateOperation")
    op = o.campaign_conversion_goal_operation
    g = op.update
    g.resource_name = comum.temp(
        cid, "campaignConversionGoals",
        f"{comum.T_CAMPANHA}~{meta.categoria}~{meta.origem}")
    g.biddable = bool(meta.biddable)
    op.update_mask.paths.append("biddable")
    return o


# ═══════════════════════════════════════════════════════════════════════════
# ASSET GROUP E VÍDEO
# ═══════════════════════════════════════════════════════════════════════════


def op_video(c, cid: str, rn: str, video: VideoYouTube, nome_padrao: str):
    o = c.get_type("MutateOperation")
    a = o.asset_operation.create
    a.resource_name = rn
    a.name = video.nome or nome_padrao
    a.type_ = c.enums.AssetTypeEnum.YOUTUBE_VIDEO
    a.youtube_video_asset.youtube_video_id = video.video_id
    return o


def op_asset_group(c, cid: str, rn: str, nome: str, url: str, *,
                   path1: str = "", path2: str = "", sufixo: str = "",
                   tracking_url_template: str = "",
                   parametros: tuple[tuple[str, str], ...] = ()):
    o = c.get_type("MutateOperation")
    ag = o.asset_group_operation.create
    ag.resource_name = rn
    ag.name = nome
    ag.campaign = _campanha(cid)
    ag.final_urls.append(url)
    # PAUSED como a campanha: despausar é um ato só, explícito.
    ag.status = c.enums.AssetGroupStatusEnum.PAUSED
    if path1:
        ag.path1 = path1
    if path2:
        ag.path2 = path2
    if sufixo:
        ag.final_url_suffix = sufixo
    if tracking_url_template:
        ag.tracking_url_template = tracking_url_template
    for chave, valor in parametros:
        ag.url_custom_parameters.append({"key": chave, "value": valor})
    return o


# ═══════════════════════════════════════════════════════════════════════════
# FASE 2 — o que não cabe no mutate atômico
# ═══════════════════════════════════════════════════════════════════════════


def operacoes_pos_criacao(c, cid: str, campanha_rn: str,
                          cfg: ConfiguracaoPMaxV25) -> list:
    """`CampaignGoalConfigOperation` para a meta de cliente novo.

    Só existe com o resource name REAL da campanha: `CampaignGoalConfig` não
    está em `MutateOperation` e o serviço próprio não resolve id temporário de
    outro request. Lista vazia quando não há meta declarada.
    """
    nc: MetaClienteNovo | None = cfg.meta_cliente_novo
    if nc is None:
        return []
    op = c.get_type("CampaignGoalConfigOperation")
    g = op.create
    g.campaign = campanha_rn
    g.goal = nc.goal
    ajustes = g.campaign_new_customer_acquisition_settings
    ajustes.target_option = getattr(
        c.enums.CustomerLifecycleOptimizationModeEnum, nc.modo)
    if nc.valor_adicional is not None:
        ajustes.value_settings_override.additional_value = float(nc.valor_adicional)
    elif nc.multiplicador_de_valor is not None:
        ajustes.value_settings_override.value_multiplier = float(
            nc.multiplicador_de_valor)
    return [op]
