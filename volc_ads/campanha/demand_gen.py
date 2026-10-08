"""Builder seguro de Google Ads Demand Gen (API v25.2).

Três formatos de anúncio, cada um com o seu contrato de assets e imutáveis:

    MULTI_ASSET        ``DemandGenMultiAssetAdInfo``     (default; a 1ª onda)
    VIDEO_RESPONSIVO   ``DemandGenVideoResponsiveAdInfo`` (vídeo do YouTube por
                       id, criado como Asset no MESMO mutate)
    CARROSSEL          ``DemandGenCarouselAdInfo``        (cartões
                       ``DemandGenCarouselCardAsset`` com imagem REMOTA)

Produto (``DemandGenProductAdInfo``) fica fora: exige Merchant Center. Vídeo
NÃO é canal próprio nesta casa — vive aqui e em PMax.

O grafo inteiro entra em um ``GoogleAdsService.Mutate`` atômico:

    budget → campanha PAUSED → [agenda] → ad group PAUSED → geo/idioma
           → [lookalikes → Audience composta] → critérios de audiência
           → assets (imagem | vídeo | CTA | cartão) → anúncio PAUSED

Quem decide o formato e o resto do v25.2 é ``demand_gen_config.
ConfiguracaoDemandGenV25``, que viaja no próprio ``Brief.demand_gen``. Com a
``ConfiguracaoDemandGen`` antiga o payload é o de sempre. ``partial_failure``
não é opção. Criação real continua proibida em ``subir.py``; este módulo serve
à montagem offline e à prova ``validate_only``.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, replace
from importlib import import_module

from .. import automacoes
from ..gads.client import cliente, validar_mutacoes
from ..policy import spec as policy
from . import comum, conteudo, demand_gen_ops, plano, taxonomia, validacao
from .brief import (
    AssetRemotoDemandGen,
    CANAIS_SELECIONAVEIS_DEMAND_GEN,
    Brief,
    ImagemParaSubir,
    ImagensDemandGen,
    conferir_asset_demand_gen,
)
from .demand_gen_config import (
    AUTOMACOES_POR_FORMATO,
    ESTRATEGIAS_DEPENDENTES_DE_CONVERSAO,
    LIMITES_DE_TEXTO,
    ConfiguracaoDemandGenV25,
    mesmo_host,
)

CANAL = "DEMAND_GEN"

#: As automações de criativo que a receita Demand Gen recusa, em ordem estável.
#:
#: ⚠️ REFERÊNCIA, e não declaração (06/09/2026). A lista mora em
#: `volc_ads/automacoes.py`, stdlib pura, porque a tela do Hub precisa mostrar
#: cada uma como fato travado e o backend não pode importar este módulo no boot.
#:
#: Ordem estável porque o selo do plano cobre a lista: duas provas
#: semanticamente iguais não podem gerar protobufs diferentes.
AUTOMACOES_DEMAND_GEN_RECUSADAS: tuple[str, ...] = (
    automacoes.AUTOMACOES_DEMAND_GEN_RECUSADAS)
TIPO_DE_ANUNCIO = "DEMAND_GEN_MULTI_ASSET_AD"
#: Tipo de anúncio por formato (`AdTypeEnum` v25).
TIPO_DE_ANUNCIO_POR_FORMATO: dict[str, str] = {
    "MULTI_ASSET": "DEMAND_GEN_MULTI_ASSET_AD",
    "VIDEO_RESPONSIVO": "DEMAND_GEN_VIDEO_RESPONSIVE_AD",
    "CARROSSEL": "DEMAND_GEN_CAROUSEL_AD",
}
#: O que `Brief.estrategia_lance` pode trazer SEM `ConfiguracaoDemandGenV25.
#: lance`. Lances novos (tCPA, MaxConvValue/tROAS, TARGET_SPEND, TARGET_CPC)
#: entram por `LanceDemandGen` — ver `demand_gen_config.ESTRATEGIAS`.
# Literal (o backend lê por árvore sintática); espelha demand_gen_config.ESTRATEGIAS
# — `teste_lances_permitidos_espelham_a_configuracao` cobra a igualdade.
LANCES_PERMITIDOS: tuple[str, ...] = (
    "MAXIMIZE_CONVERSIONS",
    "MAXIMIZE_CONVERSION_VALUE",
    "TARGET_SPEND",
    "TARGET_CPC",
)

# A ordem legada das três automações de multi-asset é a ordem do selo. As duas
# listas precisam continuar a mesma tupla, senão o payload antigo muda de bytes.
assert (AUTOMACOES_POR_FORMATO["MULTI_ASSET"]
        == tuple(automacoes.AUTOMACOES_DEMAND_GEN_RECUSADAS)), (
    "automacoes.py e demand_gen_config divergiram na lista de multi-asset")
OPCOES: frozenset[str] = frozenset()

_CAMPO_DO_PROTO: dict[str, str] = {
    "marketing": "marketing_images",
    "marketing_quadrada": "square_marketing_images",
    "marketing_retrato": "portrait_marketing_images",
    "marketing_retrato_alto": "tall_portrait_marketing_images",
    "logo_quadrado": "logo_images",
}

PAPEIS_DE_IMAGEM: tuple[tuple[str, str], ...] = tuple(
    (papel, _CAMPO_DO_PROTO[papel]) for papel in ImagensDemandGen.PAPEIS
)

_RESOURCE_ASSET = re.compile(r"^customers/(\d+)/assets/(-?\d+)$")
_RESOURCE_AUDIENCE = re.compile(r"^customers/(\d+)/audiences/(-?\d+)$")

_EXPLICACAO_DKI = (
    "Demand Gen não casa keyword; {KeyWord:…} não tem intenção de busca para "
    "resolver. Escreva o texto final sem DKI"
)


@dataclass(frozen=True)
class SuporteProtoV25:
    """Resultado da prova local do namespace/campos usados pelo builder."""

    disponivel: bool
    motivo: str
    objetos_serializados: tuple[str, ...] = ()


def _classe_enum(modulo, nome: str):
    wrapper = getattr(modulo, nome)
    for atributo in dir(wrapper):
        valor = getattr(wrapper, atributo)
        if isinstance(valor, enum.EnumMeta):
            return valor
    raise AttributeError(f"{nome} não contém enum concreto")


def _exigir_campos(classe, *campos: str) -> None:
    existentes = {campo.name for campo in classe.pb().DESCRIPTOR.fields}
    faltantes = sorted(set(campos) - existentes)
    if faltantes:
        raise AttributeError(
            f"{classe.__module__}.{classe.__name__} sem campos {faltantes}"
        )


def _serializar_proto(objeto) -> bytes:
    alvo = getattr(objeto, "_pb", objeto)
    return alvo.SerializeToString(deterministic=True)


def sondar_proto_v25() -> SuporteProtoV25:
    """Instancia e serializa, sem credencial, os protos usados nesta onda.

    Importar ``google-ads`` não prova que a versão nem os campos existem. Esta
    sonda usa os namespaces gerados de v25 diretamente e monta uma operação de
    cada tipo emitido pelo builder. Qualquer ausência rebaixa a capacidade; não
    há fallback para outra versão nem dublê que finja o campo.
    """
    try:
        servicos = import_module(
            "google.ads.googleads.v25.services.types.google_ads_service"
        )
        campanhas = import_module(
            "google.ads.googleads.v25.resources.types.campaign"
        )
        budgets = import_module(
            "google.ads.googleads.v25.resources.types.campaign_budget"
        )
        criterios_campanha = import_module(
            "google.ads.googleads.v25.resources.types.campaign_criterion"
        )
        grupos = import_module(
            "google.ads.googleads.v25.resources.types.ad_group"
        )
        criterios_grupo = import_module(
            "google.ads.googleads.v25.resources.types.ad_group_criterion"
        )
        anuncios_grupo = import_module(
            "google.ads.googleads.v25.resources.types.ad_group_ad"
        )
        anuncios = import_module("google.ads.googleads.v25.resources.types.ad")
        assets = import_module("google.ads.googleads.v25.resources.types.asset")
        infos = import_module(
            "google.ads.googleads.v25.common.types.ad_type_infos"
        )
        ad_assets = import_module("google.ads.googleads.v25.common.types.ad_asset")
        enums = import_module("google.ads.googleads.v25.enums")

        MutateOperation = getattr(servicos, "MutateOperation")
        Campaign = getattr(campanhas, "Campaign")
        CampaignBudget = getattr(budgets, "CampaignBudget")
        CampaignCriterion = getattr(criterios_campanha, "CampaignCriterion")
        AdGroup = getattr(grupos, "AdGroup")
        AdGroupCriterion = getattr(criterios_grupo, "AdGroupCriterion")
        AdGroupAd = getattr(anuncios_grupo, "AdGroupAd")
        Ad = getattr(anuncios, "Ad")
        Asset = getattr(assets, "Asset")
        DemandGenInfo = getattr(infos, "DemandGenMultiAssetAdInfo")
        AdImageAsset = getattr(ad_assets, "AdImageAsset")
        AdTextAsset = getattr(ad_assets, "AdTextAsset")

        _exigir_campos(
            MutateOperation,
            "campaign_budget_operation",
            "campaign_operation",
            "campaign_criterion_operation",
            "ad_group_operation",
            "ad_group_criterion_operation",
            "asset_operation",
            "ad_group_ad_operation",
        )
        _exigir_campos(
            Campaign,
            "advertising_channel_type",
            "demand_gen_campaign_settings",
            "maximize_conversions",
            "status",
        )
        _exigir_campos(AdGroup, "demand_gen_ad_group_settings", "status")
        _exigir_campos(AdGroupCriterion, "audience", "location", "language")
        _exigir_campos(Ad, "demand_gen_multi_asset_ad", "final_urls")
        _exigir_campos(Asset, "image_asset", "type_")
        _exigir_campos(
            DemandGenInfo,
            "marketing_images",
            "square_marketing_images",
            "portrait_marketing_images",
            "tall_portrait_marketing_images",
            "logo_images",
            "headlines",
            "descriptions",
            "business_name",
        )
        _exigir_campos(AdImageAsset, "asset")
        _exigir_campos(AdTextAsset, "text")

        # ── v25.2: o que os formatos e decisões novas emitem ────────────────
        _exigir_campos(
            MutateOperation, "user_list_operation", "audience_operation")
        _exigir_campos(
            Campaign, "target_cpa", "target_roas", "target_spend",
            "target_cpc", "maximize_conversion_value")
        _exigir_campos(AdGroup, "audience_setting",
                       "optimized_targeting_enabled")
        _exigir_campos(
            Ad, "name", "demand_gen_video_responsive_ad", "demand_gen_carousel_ad")
        _exigir_campos(
            Asset, "youtube_video_asset", "call_to_action_asset",
            "demand_gen_carousel_card_asset")
        _exigir_campos(
            getattr(infos, "DemandGenVideoResponsiveAdInfo"),
            "headlines", "long_headlines", "descriptions", "videos",
            "logo_images", "business_name", "call_to_actions", "breadcrumb1",
            "breadcrumb2")
        _exigir_campos(
            getattr(infos, "DemandGenCarouselAdInfo"),
            "business_name", "logo_image", "headline", "description",
            "call_to_action_text", "carousel_cards")
        _exigir_campos(DemandGenInfo, "call_to_action_text")
        _exigir_campos(AdGroupAd, "ad_group_ad_asset_automation_settings")
        automacao = _classe_enum(enums, "AssetAutomationTypeEnum")
        for formato_tipos in AUTOMACOES_POR_FORMATO.values():
            for tipo in formato_tipos:
                getattr(automacao, tipo)

        canal_enum = _classe_enum(enums, "AdvertisingChannelTypeEnum")
        status_campanha = _classe_enum(enums, "CampaignStatusEnum")
        status_grupo = _classe_enum(enums, "AdGroupStatusEnum")
        status_anuncio = _classe_enum(enums, "AdGroupAdStatusEnum")
        estrategia_canal = _classe_enum(enums, "DemandGenChannelStrategyEnum")
        tipo_asset = _classe_enum(enums, "AssetTypeEnum")

        cid = "customers/1"
        budget = CampaignBudget(
            resource_name=f"{cid}/campaignBudgets/-1", name="probe-budget"
        )
        campanha = Campaign(
            resource_name=f"{cid}/campaigns/-2",
            name="probe-demand-gen",
            campaign_budget=f"{cid}/campaignBudgets/-1",
            advertising_channel_type=canal_enum.DEMAND_GEN,
            status=status_campanha.PAUSED,
        )
        campanha.demand_gen_campaign_settings.upgraded_targeting = True
        selecionar = getattr(
            getattr(
                campanha.maximize_conversions,
                "_pb",
                campanha.maximize_conversions,
            ),
            "SetInParent",
        )
        selecionar()

        criterio_campanha = CampaignCriterion(campaign=f"{cid}/campaigns/-2")
        criterio_campanha.location.geo_target_constant = "geoTargetConstants/2076"

        grupo = AdGroup(
            resource_name=f"{cid}/adGroups/-3",
            campaign=f"{cid}/campaigns/-2",
            name="probe-grupo",
            status=status_grupo.PAUSED,
        )
        controles = grupo.demand_gen_ad_group_settings.channel_controls
        _exigir_campos(
            type(controles),
            "channel_config",
            "channel_strategy",
            "selected_channels",
        )
        _exigir_campos(
            type(controles.selected_channels), *CANAIS_SELECIONAVEIS_DEMAND_GEN
        )
        controles.channel_strategy = estrategia_canal.ALL_CHANNELS

        criterio_grupo = AdGroupCriterion(ad_group=f"{cid}/adGroups/-3")
        criterio_grupo.audience.audience = f"{cid}/audiences/1"

        asset = Asset(
            resource_name=f"{cid}/assets/-200",
            name="probe-imagem",
            type_=tipo_asset.IMAGE,
        )
        asset.image_asset.data = b"probe"

        info = DemandGenInfo(
            business_name="VOLC",
            headlines=[AdTextAsset(text="Probe")],
            descriptions=[AdTextAsset(text="Prova offline")],
            marketing_images=[AdImageAsset(asset=f"{cid}/assets/-200")],
            logo_images=[AdImageAsset(asset=f"{cid}/assets/-201")],
        )
        ad = Ad(final_urls=["https://example.invalid/"])
        ad.demand_gen_multi_asset_ad = info
        anuncio = AdGroupAd(
            ad_group=f"{cid}/adGroups/-3",
            status=status_anuncio.PAUSED,
            ad=ad,
        )

        criacoes = (
            ("campaign_budget_operation", budget),
            ("campaign_operation", campanha),
            ("campaign_criterion_operation", criterio_campanha),
            ("ad_group_operation", grupo),
            ("ad_group_criterion_operation", criterio_grupo),
            ("asset_operation", asset),
            ("ad_group_ad_operation", anuncio),
        )
        serializados: list[str] = []
        for campo, criado in criacoes:
            op = MutateOperation()
            getattr(op, campo).create = criado
            bruto = _serializar_proto(op)
            if not bruto:
                raise ValueError(f"{campo} serializou vazio")
            serializados.append(campo)

        # Também serializa os objetos de folha que o builder instancia por nome.
        for nome, objeto in (
            ("DemandGenMultiAssetAdInfo", info),
            ("AdImageAsset", AdImageAsset(asset=f"{cid}/assets/-200")),
            ("AdTextAsset", AdTextAsset(text="Probe")),
        ):
            if not _serializar_proto(objeto):
                raise ValueError(f"{nome} serializou vazio")
            serializados.append(nome)
        return SuporteProtoV25(
            True,
            "protos v25 instanciados e serializados",
            tuple(serializados),
        )
    except Exception as exc:  # noqa: BLE001 — ausência/mudança de SDK é capacidade
        return SuporteProtoV25(
            False,
            f"SDK Google Ads v25 incompatível: {type(exc).__name__}: {exc}",
        )


def _v25(brief: Brief) -> ConfiguracaoDemandGenV25 | None:
    """A configuração v25.2, quando o chamador a entregou. None = legado."""
    cfg = brief.demand_gen
    return cfg if isinstance(cfg, ConfiguracaoDemandGenV25) else None


def formato_de(brief: Brief) -> str:
    v25 = _v25(brief)
    return v25.formato if v25 is not None else "MULTI_ASSET"


def construir(cid: str, brief: Brief, *, login_customer_id: str):
    """Monta o grafo Demand Gen sem executar chamada externa."""
    r = validacao.Resultado()
    suporte = sondar_proto_v25()
    if not suporte.disponivel:
        r.erro(
            "sdk.google_ads.v25",
            "indisponível",
            suporte.motivo + "; capacidade Demand Gen rebaixada sem fallback",
        )
        return [], r
    ts = comum.carimbo()
    base = conteudo.nome_da_campanha(brief, ts, marcador=taxonomia.MODIFICADOR[CANAL])

    cfg = _checar_contrato(cid, brief, r)
    v25 = _v25(brief)
    formato = formato_de(brief)
    pol = conteudo.abrir_portao(brief, r)
    textos = _checar_textos(brief, formato, pol, r)
    imagens = _checar_imagens(cid, brief, r, formato=formato)
    cartoes = (
        _checar_cartoes(cid, brief, v25, pol, r) if formato == "CARROSSEL" else []
    )
    publico = _checar_publico(cid, v25, r) if v25 is not None else None

    if not r.ok or cfg is None:
        return [], r

    c = cliente(login_customer_id)
    camp_op = comum.op_campanha(c, cid, brief, base, CANAL)
    if v25 is not None and v25.lance is not None:
        demand_gen_ops.aplicar_lance(
            camp_op.campaign_operation.create, v25.lance, brief.micros)
    ops = [comum.op_budget(c, cid, brief, f"Budget_{ts}"), camp_op]

    # Com upgraded_targeting=False, geo e idioma são critérios da campanha.
    # Com True, o campo imutável move ambos para o ad group.
    if not cfg.upgraded_targeting:
        ops.extend((comum.op_geo(c, cid, brief), comum.op_idioma(c, cid, brief)))

    # A agenda é critério de CAMPANHA nos dois modos de targeting (medido).
    for faixa in (v25.agenda if v25 is not None else ()):
        ops.append(demand_gen_ops.op_agenda(c, cid, faixa))

    tem_audiencia = bool(cfg.audiencias) or publico is not None
    ops.append(_op_ad_group(c, cid, base, cfg, v25, agrupar=tem_audiencia))

    if cfg.upgraded_targeting:
        ops.extend(
            (_op_geo_ad_group(c, cid, brief), _op_idioma_ad_group(c, cid, brief))
        )

    for rn in cfg.audiencias or ():
        ops.append(_op_audiencia(c, cid, rn))

    if publico is not None:
        lookalikes_rn = []
        for i, lal in enumerate(publico.lookalikes):
            ops.append(demand_gen_ops.op_lookalike(c, cid, i, lal))
            lookalikes_rn.append(demand_gen_ops.temp_user_list(cid, i))
        ops.append(demand_gen_ops.op_audiencia(c, cid, 0, publico, lookalikes_rn))
        ops.append(_op_audiencia(c, cid, demand_gen_ops.temp_audiencia(cid, 0)))

    ad_op, asset_ops = _op_anuncio(
        c, cid, brief, imagens, textos, formato=formato, v25=v25,
        cartoes=cartoes, nome_base=base,
    )
    ops.extend(asset_ops)
    ops.append(ad_op)
    return ops, r


def _forma(
    itens: list[str],
    chave: str,
    r: validacao.Resultado,
    *,
    excedente_e_erro: bool = False,
) -> list[str]:
    """`conteudo.forma` com os limites de `demand_gen_config.LIMITES_DE_TEXTO`.

    Mesma régua (largura resolvendo DKI, DKI recusado, duplicata removida com
    aviso). A diferença: em campo SINGULAR do proto (carrossel), excedente é
    ERRO — cortar escolheria por ordem qual texto aprovado vai ao ar.
    """
    lim = LIMITES_DE_TEXTO[chave]
    aprovados: list[str] = []
    for texto in itens:
        texto = (texto or "").strip()
        if not texto:
            r.erro(chave, texto, "texto vazio")
            continue
        if not validacao.dki_integro(texto) or policy.resolver_dki(texto) != texto:
            r.erro(chave, texto, f"DKI não é permitido neste campo — {_EXPLICACAO_DKI}")
            continue
        if len(texto) > lim["max_chars"]:
            r.erro(chave, texto, f"{len(texto)} chars > limite {lim['max_chars']}")
            continue
        aprovados.append(texto)
    vistos, unicos = set(), []
    for t in aprovados:
        k = conteudo.chave(t)
        if k in vistos:
            r.aviso(chave, t, "duplicado — removido")
            continue
        vistos.add(k)
        unicos.append(t)
    if len(unicos) < lim["min_itens"]:
        r.erro(chave, f"{len(unicos)} itens", f"mínimo é {lim['min_itens']}")
    if len(unicos) > lim["max_itens"]:
        excedente = unicos[lim["max_itens"]:]
        motivo = (f"{len(excedente)} texto(s) além do teto {lim['max_itens']}: "
                  + " · ".join(t[:32] for t in excedente[:6]))
        if excedente_e_erro:
            r.erro(chave, f"{len(unicos)} itens",
                   motivo + "; o campo do proto é singular — escolha um")
        else:
            r.aviso(chave, f"{len(unicos)} itens", motivo + " (não sobem)")
    return unicos[: lim["max_itens"]]


def _politica(pol, textos: list[str], campo: str, r: validacao.Resultado) -> None:
    for v in pol.checar_lista([t for t in textos if t], campo):
        conteudo.registrar(v, r)


def _checar_textos(brief: Brief, formato: str, pol, r: validacao.Resultado) -> dict:
    """Textos por formato. Multi-asset mantém exatamente a régua legada."""
    nomes = conteudo.forma([brief.copy.business_name], "business_name", r)
    if not brief.copy.business_name.strip():
        r.erro(
            "business_name",
            "",
            "o anúncio de Demand Gen exige o nome da empresa "
            "(até 25 de largura de exibição)",
        )
    conteudo.politica(pol, nomes, "business_name", r)
    saida = {"business_name": nomes[0] if nomes else ""}

    if formato == "MULTI_ASSET":
        headlines = conteudo.forma(
            brief.copy.headlines, "headline_demandgen", r,
            explicacao_dki=_EXPLICACAO_DKI)
        descriptions = conteudo.forma(
            brief.copy.descriptions, "description_dgen", r,
            explicacao_dki=_EXPLICACAO_DKI)
        conteudo.politica(pol, headlines, "headline_demandgen", r)
        conteudo.politica(pol, descriptions, "description_dgen", r)
        saida.update(headlines=headlines, descriptions=descriptions)
    elif formato == "VIDEO_RESPONSIVO":
        headlines = _forma(brief.copy.headlines, "headline_video", r)
        longs = _forma(brief.copy.long_headlines, "long_headline_video", r)
        descriptions = _forma(brief.copy.descriptions, "description_video", r)
        _politica(pol, headlines, "headline", r)
        _politica(pol, longs, "long_headline", r)
        _politica(pol, descriptions, "description", r)
        saida.update(headlines=headlines, long_headlines=longs,
                     descriptions=descriptions)
    else:  # CARROSSEL
        headlines = _forma(brief.copy.headlines, "headline_carrossel", r,
                           excedente_e_erro=True)
        descriptions = _forma(brief.copy.descriptions, "description_carrossel",
                              r, excedente_e_erro=True)
        _politica(pol, headlines, "headline", r)
        _politica(pol, descriptions, "description", r)
        saida.update(headlines=headlines, descriptions=descriptions)
    return saida


def _checar_contrato(cid: str, brief: Brief, r: validacao.Resultado):
    cfg = brief.demand_gen
    if cfg is None:
        r.erro(
            "demand_gen",
            "ausente",
            "Demand Gen exige configuração explícita de targeting, channel "
            "controls, audiência, intenção e exclusões",
        )
        return None

    if cfg.upgraded_targeting is None:
        r.erro(
            "demand_gen.upgraded_targeting",
            "ausente",
            "campo imutável: escolha True (geo/idioma no ad group) ou False "
            "(geo/idioma na campanha) antes de montar",
        )
    if cfg.controles_de_canal is None:
        r.erro(
            "demand_gen.controles_de_canal",
            "ausente",
            "o default remoto ALL_CHANNELS é perigoso e não decide pelo "
            "operador; declare a estratégia explicitamente",
        )

    for campo in ("audiencias", "intencoes", "exclusoes_de_audiencia"):
        if getattr(cfg, campo) is None:
            r.erro(
                f"demand_gen.{campo}",
                "ausente",
                "ausência não é lista vazia confirmada; envie [] para declarar "
                "que esta prova não carrega itens nessa superfície",
            )

    if cfg.intencoes:
        r.erro(
            "demand_gen.intencoes",
            f"{len(cfg.intencoes)} intenção(ões)",
            "texto de intenção não é AdGroupCriterion. Materialize-o numa "
            "Audience aprovada e passe o resource name em `audiencias`; esta "
            "onda não cria CustomAudience por analogia",
        )
    if cfg.exclusoes_de_audiencia:
        r.erro(
            "demand_gen.exclusoes_de_audiencia",
            f"{len(cfg.exclusoes_de_audiencia)} exclusão(ões)",
            "Audience não é excluível em Demand Gen v25: com "
            "`use_audience_grouped` o critério negativo direto é recusado "
            "(CANNOT_ADD_AUDIENCE_SEGMENT_CRITERION_WHEN_AUDIENCE_GROUPED_IS_SET,"
            " medido). Exclusão é por USER LIST dentro da Audience composta: "
            "use `ConfiguracaoDemandGenV25.publico.exclusoes_user_list`",
        )

    audiencias_canonicas: list[str] = []
    vistas: set[str] = set()
    if not cfg.audiencias:
        r.aviso(
            "demand_gen.audiencias",
            "0 confirmado",
            "nenhuma Audience será anexada; isto é vazio confirmado, não "
            "ausência nem intenção convertida em audiência",
        )
    else:
        for rn in cfg.audiencias:
            canonico = _checar_resource_name(
                cid, rn, _RESOURCE_AUDIENCE, "audiences", r
            )
            if canonico is None:
                continue
            if canonico in vistas:
                r.erro(
                    "demand_gen.audiencias",
                    canonico,
                    "Audience duplicada depois da canonização; duplicata não "
                    "vira duas operações nem é descartada silenciosamente",
                )
                continue
            vistas.add(canonico)
            audiencias_canonicas.append(canonico)
        cfg = replace(cfg, audiencias=tuple(audiencias_canonicas))

    _checar_lance(brief, r)

    # Estes três domínios não têm campo no anúncio multi-asset. Recusar é mais
    # seguro do que fingir que uma keyword virou intenção ou exclusão.
    if brief.keywords or brief.sub_intencoes or brief.criterios:
        r.erro(
            "keywords",
            "preenchido",
            "Demand Gen não opera keywords. Use `audiencias`, `intencoes` e "
            "`exclusoes_de_audiencia` nos campos separados do contrato",
        )
    formato = formato_de(brief)
    if brief.copy.long_headlines and formato != "VIDEO_RESPONSIVO":
        r.erro(
            "copy.long_headlines",
            f"{len(brief.copy.long_headlines)}",
            f"long headline pertence ao formato VIDEO_RESPONSIVO, não ao "
            f"{formato} escolhido; preencher e omitir seria aprovar copy que "
            "não chega ao payload",
        )
    if brief.copy.sitelinks:
        r.erro(
            "copy.sitelinks",
            f"{len(brief.copy.sitelinks)}",
            "esta onda não emite CampaignAsset de sitelink em Demand Gen; "
            "preencher e omitir seria aprovar copy que não chega ao payload",
        )
    if brief.copy.callouts:
        r.erro(
            "copy.callouts",
            f"{len(brief.copy.callouts)}",
            "esta onda não emite CampaignAsset de callout em Demand Gen; o "
            "campo preenchido é recusado, nunca descartado",
        )
    if brief.copy.snippet is not None:
        r.erro(
            "copy.snippet",
            "preenchido",
            "esta onda não emite structured snippet em Demand Gen; ausência "
            "de operação não pode parecer copy aplicada",
        )
    if brief.videos:
        r.erro(
            "videos",
            f"{len(brief.videos)}",
            "`brief.videos` é lista solta de resource names sem recibo. O "
            "vídeo de Demand Gen entra por `ConfiguracaoDemandGenV25(formato="
            "'VIDEO_RESPONSIVO', video=VideoDemandGen(youtube_ids=...))`, que "
            "cria o asset YOUTUBE_VIDEO no mesmo mutate",
        )
    if brief.imagens or brief.imagens_display is not None:
        r.erro(
            "imagens",
            "contrato de outro canal",
            "use `imagens_demand_gen`; lista chapada e ImagensDisplay não "
            "representam as orientações 4:5/9:16 de Demand Gen",
        )
    if brief.conversao:
        r.erro(
            "conversao",
            brief.conversao,
            "o builder Demand Gen ainda não emite selective_optimization; "
            "meta preenchida não pode ser transportada só no rótulo",
        )
    if brief.ai_max:
        r.erro(
            "ai_max",
            "True",
            "AI Max é opção de Search e não é operada por este builder Demand Gen",
        )
    if brief.match_type != "PHRASE":
        r.erro(
            "match_type",
            brief.match_type,
            "Demand Gen não casa keywords; match_type preenchido fora do default "
            "legado seria descartado",
        )
    if brief.cpc_inicial != 0.12:
        r.erro(
            "cpc_inicial",
            str(brief.cpc_inicial),
            "Demand Gen não opera CPC inicial. Valor diferente do default legado "
            "indica decisão do operador e é recusado, não omitido",
        )

    r.aviso(
        "budget_diario",
        str(brief.budget_diario),
        "o contrato não conhece a moeda da conta e por isso não inventa nem "
        "converte o mínimo diário publicado; o validate_only é o juiz desse "
        "requisito nesta prova",
    )
    if brief.cpc_inicial == 0.12:
        r.aviso(
            "cpc_inicial",
            str(brief.cpc_inicial),
            "o default legado do Brief não vira lance, meta ou operação em "
            "Demand Gen; a fronteira HTTP recusa o campo quando ele é enviado "
            "explicitamente",
        )
    if brief.match_type == "PHRASE":
        r.aviso(
            "match_type",
            brief.match_type,
            "o default legado do Brief não vira critério em Demand Gen; a "
            "fronteira HTTP recusa escolha explícita de match type",
        )
    return cfg


def _checar_lance(brief: Brief, r: validacao.Resultado) -> None:
    """Uma fonte de verdade para o lance: o brief (legado) OU `LanceDemandGen`."""
    v25 = _v25(brief)
    lance = v25.lance if v25 is not None else None
    if lance is None:
        if brief.estrategia_lance not in LANCES_PERMITIDOS:
            r.erro(
                "estrategia_lance",
                brief.estrategia_lance,
                "pelo brief, Demand Gen monta só MAXIMIZE_CONVERSIONS sem meta. "
                "tCPA, MaxConvValue/tROAS, TARGET_SPEND e TARGET_CPC entram por "
                "`ConfiguracaoDemandGenV25.lance` (LanceDemandGen)",
            )
        if brief.tcpa is not None:
            r.erro(
                "tcpa",
                str(brief.tcpa),
                "tCPA no brief mudaria a estratégia efetiva sem declaração: em "
                "Demand Gen ele vira `target_cpa` avulso, não meta dentro de "
                "MaxConv (recusada pela API). Declare "
                "`LanceDemandGen('MAXIMIZE_CONVERSIONS', target_cpa=...)`",
            )
        return

    for campo in ("tcpa", "target_roas"):
        valor = getattr(brief, campo)
        if valor is not None:
            r.erro(
                campo,
                str(valor),
                "com `LanceDemandGen` declarado a meta mora nele; o mesmo número "
                "em dois lugares seria precedência silenciosa",
            )
    # MANUAL_CPC é o DEFAULT do brief — indistinguível de "ninguém escolheu".
    if brief.estrategia_lance not in ("MANUAL_CPC", lance.estrategia):
        r.erro(
            "estrategia_lance",
            brief.estrategia_lance,
            f"diverge de `LanceDemandGen.estrategia={lance.estrategia}`; duas "
            "estratégias declaradas não escolhem uma em silêncio",
        )
    if (lance.estrategia in ESTRATEGIAS_DEPENDENTES_DE_CONVERSAO
            or lance.target_roas is not None):
        r.aviso(
            "demand_gen.lance",
            lance.estrategia,
            "estratégia de VALOR exige histórico de valor de conversão na "
            "conta; sem ele a API devolve campaign_error.NOT_ENOUGH_CONVERSIONS "
            "(medido na Crédito Up em 08/10/2026)",
        )


def _checar_imagens(
    cid: str, brief: Brief, r: validacao.Resultado, *, formato: str = "MULTI_ASSET"
) -> ImagensDemandGen:
    imagens = brief.imagens_demand_gen
    if imagens is None:
        r.erro(
            "imagens_demand_gen",
            "ausente",
            "o anúncio multi-asset exige ImagensDemandGen com ao menos uma "
            "imagem horizontal ou quadrada e um logo quadrado aprovado"
            if formato == "MULTI_ASSET" else
            f"o formato {formato} exige ImagensDemandGen com exatamente um "
            "logo quadrado aprovado",
        )
        return ImagensDemandGen()

    if formato != "MULTI_ASSET":
        # Vídeo e carrossel têm UM logo (vídeo: 2 → TOO_MANY; carrossel: campo
        # singular) e nenhum campo para as quatro orientações de marketing.
        for papel in ImagensDemandGen.PAPEIS:
            if papel == "logo_quadrado":
                continue
            if getattr(imagens, papel):
                r.erro(
                    f"imagens_demand_gen.{papel}",
                    f"{len(getattr(imagens, papel))}",
                    f"o formato {formato} não tem campo para {papel}; imagem "
                    "preenchida e omitida seria peça aprovada que não sobe"
                    + (" — imagem de cartão vai em `carrossel.cartoes`"
                       if formato == "CARROSSEL" else ""),
                )
        if len(imagens.logo_quadrado) != 1:
            r.erro(
                "imagens_demand_gen.logo_quadrado",
                str(len(imagens.logo_quadrado)),
                f"o formato {formato} exige exatamente 1 logo quadrado",
            )
        return _normalizar_imagens(cid, imagens, r)

    lim = conteudo.LIM["demand_gen_asset"]
    total_marketing = sum(
        len(getattr(imagens, papel))
        for papel in ImagensDemandGen.PAPEIS
        if papel != "logo_quadrado"
    )
    par_base = len(imagens.marketing) + len(imagens.marketing_quadrada)
    if par_base < lim["marketing_pair_min"]:
        r.erro(
            "imagens_demand_gen",
            f"{par_base} horizontal/quadrada",
            "o proto exige marketing_images quando square_marketing_images "
            "estiver ausente, ou vice-versa; retratos sozinhos não satisfazem",
        )
    if total_marketing > lim["marketing_total_max"]:
        r.erro(
            "imagens_demand_gen",
            f"{total_marketing} imagens de marketing",
            f"o teto combinado das quatro orientações é {lim['marketing_total_max']}",
        )
    logos = len(imagens.logo_quadrado)
    if not lim["logo_min"] <= logos <= lim["logo_max"]:
        r.erro(
            "imagens_demand_gen.logo_quadrado",
            str(logos),
            f"o anúncio multi-asset exige {lim['logo_min']}..{lim['logo_max']} "
            "logos quadrados",
        )
    return _normalizar_imagens(cid, imagens, r)


def _normalizar_imagens(
    cid: str, imagens: ImagensDemandGen, r: validacao.Resultado
) -> ImagensDemandGen:
    """Recibo, conta, forma canônica e duplicata — item a item, por papel."""
    normalizadas = ImagensDemandGen()
    conteudos_vistos_por_papel: dict[str, set[str]] = {
        papel: set() for papel in ImagensDemandGen.PAPEIS
    }
    recursos_vistos_por_papel: dict[str, set[str]] = {
        papel: set() for papel in ImagensDemandGen.PAPEIS
    }
    for papel, _campo in PAPEIS_DE_IMAGEM:
        for item in getattr(imagens, papel):
            if isinstance(item, (ImagemParaSubir, AssetRemotoDemandGen)):
                for motivo in conferir_asset_demand_gen(
                    item, papel=papel, customer_id=str(cid)
                ):
                    r.erro(
                        f"imagens_demand_gen.{papel}",
                        item.nome,
                        motivo,
                    )
                if isinstance(item, AssetRemotoDemandGen):
                    canonico = _checar_resource_name(
                        cid, item.resource_name, _RESOURCE_ASSET, "assets", r
                    )
                    if canonico is None:
                        continue
                    if canonico in recursos_vistos_por_papel[papel]:
                        r.erro(
                            f"imagens_demand_gen.{papel}",
                            canonico,
                            "resource name remoto duplicado na forma canônica; "
                            "a segunda ocorrência não é descartada silenciosamente",
                        )
                    recursos_vistos_por_papel[papel].add(canonico)
                    identidade = f"conteudo:{item.recibo.conteudo_hash}"
                else:
                    recibo = item.recibo_aprovacao
                    identidade = (
                        f"conteudo:{recibo.conteudo_hash}"
                        if recibo is not None
                        else f"novo-sem-recibo:{item.nome}"
                    )
            elif isinstance(item, str):
                canonico = _checar_resource_name(
                    cid, item, _RESOURCE_ASSET, "assets", r
                )
                r.erro(
                    f"imagens_demand_gen.{papel}",
                    item,
                    "asset remoto em `str` não carrega recibo tipado de "
                    "catálogo/aprovação nem bytes para reconferência. Use "
                    "AssetRemotoDemandGen emitido por `criativo_ponte`",
                    plano.ASSET_SEM_RECIBO,
                )
                if canonico is None:
                    continue
                identidade = f"remoto-sem-recibo:{canonico}"
            else:
                r.erro(
                    f"imagens_demand_gen.{papel}",
                    type(item).__name__,
                    "forma de asset desconhecida; ausência de tipo não autoriza reuso",
                    plano.ASSET_SEM_RECIBO,
                )
                continue

            if identidade in conteudos_vistos_por_papel[papel]:
                r.erro(
                    f"imagens_demand_gen.{papel}",
                    identidade,
                    "asset duplicado na forma canônica pelo conteúdo; duas "
                    "ocorrências não viram duas vagas nem são deduplicadas em "
                    "silêncio",
                )
                continue
            conteudos_vistos_por_papel[papel].add(identidade)
            # Só formas tipadas seguem para a cópia normalizada. Strings remotas
            # já produziram recusa acima e nunca chegam perto do proto.
            if isinstance(item, (ImagemParaSubir, AssetRemotoDemandGen)):
                getattr(normalizadas, papel).append(item)
    return normalizadas


def _checar_cartoes(
    cid: str, brief: Brief, v25: ConfiguracaoDemandGenV25, pol,
    r: validacao.Resultado,
) -> list[tuple]:
    """Cartões do carrossel → [(cartão, {papel: resource name}, url, headline)].

    ⚠️ Imagem de cartão só como asset REMOTO: `DemandGenCarouselCardAsset`
    não resolve id temporário de imagem criada no mesmo mutate (medido:
    RESOURCE_NOT_FOUND no campo do cartão). Aceitar `ImagemParaSubir` aqui
    seria montar um payload que a API recusa inteiro.
    """
    saida: list[tuple] = []
    recursos_vistos: set[str] = set()
    conteudos_vistos: set[str] = set()
    for i, cartao in enumerate(v25.carrossel.cartoes):
        rotulo = f"carrossel.cartoes[{i}]"
        imagens_rn: dict[str, str] = {}
        for papel in cartao.papeis:
            item = getattr(cartao, papel)
            if isinstance(item, ImagemParaSubir):
                r.erro(
                    f"{rotulo}.{papel}",
                    item.nome,
                    "imagem de cartão precisa já existir na conta "
                    "(AssetRemotoAprovado): o cartão não resolve id temporário "
                    "do mesmo mutate (RESOURCE_NOT_FOUND, medido). Suba a imagem "
                    "antes e passe o recibo remoto",
                    plano.ASSET_SEM_RECIBO,
                )
                continue
            if not isinstance(item, AssetRemotoDemandGen):
                r.erro(f"{rotulo}.{papel}", type(item).__name__,
                       "forma de asset desconhecida; ausência de tipo não "
                       "autoriza reuso", plano.ASSET_SEM_RECIBO)
                continue
            for motivo in conferir_asset_demand_gen(
                    item, papel=papel, customer_id=str(cid)):
                r.erro(f"{rotulo}.{papel}", item.nome, motivo)
            canonico = _checar_resource_name(
                cid, item.resource_name, _RESOURCE_ASSET, "assets", r)
            if canonico is None:
                continue
            identidade = f"conteudo:{item.recibo.conteudo_hash}"
            if canonico in recursos_vistos or identidade in conteudos_vistos:
                r.erro(
                    f"{rotulo}.{papel}",
                    canonico,
                    "a mesma imagem em dois cartões é recusada pela API "
                    "(DUPLICATE_IMAGE_ACROSS_CAROUSEL_CARDS, medido)",
                )
                continue
            recursos_vistos.add(canonico)
            conteudos_vistos.add(identidade)
            imagens_rn[papel] = canonico

        headlines = _forma([cartao.headline], "headline_cartao", r)
        url = cartao.url_final or comum.url_destino(brief)
        if cartao.url_final is not None:
            if not mesmo_host(cartao.url_final, brief.url_final):
                r.erro(
                    f"{rotulo}.url_final",
                    cartao.url_final,
                    "destino do cartão fora do domínio da LP aprovada; o portão "
                    "de política só olhou `brief.url_final`",
                )
            elif cartao.url_final != brief.url_final:
                r.aviso(
                    f"{rotulo}.url_final",
                    cartao.url_final,
                    "cartão com destino próprio no mesmo domínio; o portão de "
                    "política da LP avaliou só `brief.url_final`",
                )
        saida.append((cartao, imagens_rn, url, headlines[0] if headlines else ""))
    _politica(pol, [c[3] for c in saida if c[3]], "headline", r)
    return saida


_RESOURCE_USER_LIST = re.compile(r"^customers/(\d+)/userLists/(-?\d+)$")


def _checar_publico(cid: str, v25: ConfiguracaoDemandGenV25, r: validacao.Resultado):
    publico = v25.publico
    if publico is None:
        return None
    for campo in ("user_lists", "exclusoes_user_list"):
        for rn in getattr(publico, campo):
            _checar_resource_name(cid, rn, _RESOURCE_USER_LIST, "userLists", r)
    if publico.lookalikes:
        r.aviso(
            "demand_gen.publico.lookalikes",
            f"{len(publico.lookalikes)}",
            "lookalike nasce como UserList da CONTA (sobrevive à campanha) e só "
            "serve com ≥100 membros ativos somados nas sementes; o "
            "validate_only não confere esse piso",
        )
    r.aviso(
        "demand_gen.publico",
        publico.nome,
        "a Audience composta é recurso da CONTA (reutilizável e persistente), "
        "criada no mesmo mutate da campanha",
    )
    return publico


def _checar_resource_name(
    cid: str, rn: str, padrao, colecao: str, r: validacao.Resultado
) -> str | None:
    bruto = str(rn or "")
    limpo = bruto.strip()
    m = padrao.fullmatch(limpo)
    if m is None:
        r.erro(
            colecao,
            rn,
            f"resource name inválido; esperado `customers/{cid}/{colecao}/<id>`",
        )
        return None
    conta, ident = m.group(1), int(m.group(2))
    cid_bruto = str(cid)
    if not cid_bruto.isdigit() or int(cid_bruto) <= 0:
        r.erro(
            colecao,
            cid_bruto,
            "customer_id precisa estar na forma canônica só-dígitos",
        )
        return None
    cid_canonico = str(int(cid_bruto))
    if cid_bruto != cid_canonico:
        r.erro(
            colecao,
            cid_bruto,
            f"customer_id fora da forma canônica; use {cid_canonico!r}",
        )
    if conta != cid_canonico:
        r.erro(colecao, rn, f"o recurso é da conta {conta}, não da conta {cid}")
    if ident <= 0:
        r.erro(
            colecao,
            rn,
            "id precisa ser remoto e positivo; ids negativos são temporários "
            "e só podem ser emitidos pelo builder no mesmo mutate",
        )
        return None
    canonico = f"customers/{int(conta)}/{colecao}/{ident}"
    if bruto != canonico:
        r.erro(
            colecao,
            bruto,
            f"resource name fora da forma canônica; use exatamente {canonico!r}",
        )
    return canonico


def _op_ad_group(c, cid: str, nome_base: str, cfg, v25=None, *, agrupar: bool = False):
    o = c.get_type("MutateOperation")
    ag = o.ad_group_operation.create
    ag.resource_name = comum.temp_adgroup(cid, 0)
    ag.name = f"{nome_base} / Grupo"
    ag.campaign = comum.temp(cid, "campaigns", comum.T_CAMPANHA)
    ag.status = c.enums.AdGroupStatusEnum.PAUSED
    # `type_` não é setado: a documentação oficial pede explicitamente um ad
    # group sem tipo para Demand Gen.
    controles = ag.demand_gen_ad_group_settings.channel_controls
    escolha = cfg.controles_de_canal
    if escolha.estrategia == "SELECTED_CHANNELS":
        # Os sete booleanos são o conjunto INTEIRO de `DemandGenSelectedChannels`
        # na v25.2 (conferido no proto e por validate_only com os sete). Os não
        # escolhidos ficam false — que em proto3 sem presença é a ausência.
        for canal in CANAIS_SELECIONAVEIS_DEMAND_GEN:
            if canal in escolha.selected_channels:
                setattr(controles.selected_channels, canal, True)
    else:
        controles.channel_strategy = getattr(
            c.enums.DemandGenChannelStrategyEnum, escolha.estrategia
        )
    # `channel_config` é output-only e nunca é escrito.

    # ⚠️ Audiência em Demand Gen exige o grupo nascer com
    # `audience_setting.use_audience_grouped = true` (guia "audience-targeting":
    # "When creating the target AdGroup, set audience_setting.use_audience_
    # grouped to true"). É IMUTÁVEL: esquecer aqui não tem conserto depois.
    # Só é emitido quando há critério de audiência — grupo sem audiência mantém
    # o payload de antes.
    if agrupar:
        ag.audience_setting.use_audience_grouped = True
    if v25 is not None and v25.segmentacao_otimizada is not None:
        ag.optimized_targeting_enabled = v25.segmentacao_otimizada
    return o


def _op_geo_ad_group(c, cid: str, brief: Brief):
    o = c.get_type("MutateOperation")
    cr = o.ad_group_criterion_operation.create
    cr.ad_group = comum.temp_adgroup(cid, 0)
    cr.location.geo_target_constant = f"geoTargetConstants/{brief.geo_id}"
    return o


def _op_idioma_ad_group(c, cid: str, brief: Brief):
    o = c.get_type("MutateOperation")
    cr = o.ad_group_criterion_operation.create
    cr.ad_group = comum.temp_adgroup(cid, 0)
    cr.language.language_constant = f"languageConstants/{brief.idioma_id}"
    return o


def _op_audiencia(c, cid: str, resource_name: str):
    o = c.get_type("MutateOperation")
    cr = o.ad_group_criterion_operation.create
    cr.ad_group = comum.temp_adgroup(cid, 0)
    cr.audience.audience = resource_name
    return o


def _op_anuncio(
    c,
    cid: str,
    brief: Brief,
    imagens: ImagensDemandGen,
    textos: dict,
    *,
    formato: str = "MULTI_ASSET",
    v25: ConfiguracaoDemandGenV25 | None = None,
    cartoes: list[tuple] = (),
    nome_base: str = "",
):
    o = c.get_type("MutateOperation")
    ada = o.ad_group_ad_operation.create
    ada.ad_group = comum.temp_adgroup(cid, 0)
    ada.status = c.enums.AdGroupAdStatusEnum.PAUSED
    ada.ad.final_urls.append(comum.url_destino(brief))

    # ── automações de criativo: TODAS as aplicáveis ao formato, explícitas ──
    #
    # ⚠️ Vivem no AD GROUP AD — não na campanha, como as de PMax — e nascem
    # LIGADAS quando ninguém fala (guia "asset-automation-settings", tabela
    # ad-level). Omiti-las deixa o Google gerar peça nova a partir dos assets
    # aprovados: no multi-asset, versões de design, vídeo montado e imagem
    # animada; no vídeo, prévia/texto da landing page e cortes curtos/verticais.
    # O que veicula deixaria de ser o que passou pelo portão de política e
    # entrou no `supply_sha256` do plano.
    #
    # Default OPTED_OUT; OPTED_IN só por `ConfiguracaoDemandGenV25.automacoes`.
    # Tipo de outro formato é recusado pela API (ENUM_VALUE_NOT_PERMITTED,
    # medido) — por isso a lista é por formato. Carrossel não tem nenhuma.
    demand_gen_ops.declarar_automacoes(c, ada, formato, v25)

    asset_ops: list = []
    if formato == "MULTI_ASSET":
        info = ada.ad.demand_gen_multi_asset_ad
        for texto in textos["headlines"]:
            asset = c.get_type("AdTextAsset")
            asset.text = texto
            info.headlines.append(asset)
        for texto in textos["descriptions"]:
            asset = c.get_type("AdTextAsset")
            asset.text = texto
            info.descriptions.append(asset)
        info.business_name = textos["business_name"]
        if v25 is not None and v25.call_to_action is not None:
            info.call_to_action_text = v25.call_to_action
        for papel, campo in PAPEIS_DE_IMAGEM:
            destino = getattr(info, campo)
            for item in getattr(imagens, papel):
                imagem = c.get_type("AdImageAsset")
                imagem.asset = _rn_da_imagem(c, cid, item, papel, asset_ops)
                destino.append(imagem)
        return o, asset_ops

    logo_rn = _rn_da_imagem(c, cid, imagens.logo_quadrado[0], "logo_quadrado",
                            asset_ops)
    if formato == "VIDEO_RESPONSIVO":
        video = v25.video
        n = 0
        videos_rn = []
        for youtube_id in video.youtube_ids:
            asset_ops.append(demand_gen_ops.op_asset_youtube(c, cid, n, youtube_id))
            videos_rn.append(demand_gen_ops.temp_asset_dg(cid, n))
            n += 1
        cta_rn = None
        if video.call_to_action is not None:
            asset_ops.append(
                demand_gen_ops.op_asset_cta(c, cid, n, video.call_to_action))
            cta_rn = demand_gen_ops.temp_asset_dg(cid, n)
            n += 1
        demand_gen_ops.preencher_video(
            c, ada,
            nome=f"{nome_base} / Vídeo",
            headlines=textos["headlines"],
            long_headlines=textos["long_headlines"],
            descriptions=textos["descriptions"],
            business_name=textos["business_name"],
            logo_rn=logo_rn,
            videos_rn=videos_rn,
            cta_rn=cta_rn,
            breadcrumb1=video.breadcrumb1,
            breadcrumb2=video.breadcrumb2,
        )
        return o, asset_ops

    # CARROSSEL
    cartoes_rn = []
    for i, (cartao, imagens_rn, url, headline) in enumerate(cartoes):
        cartao_limpo = cartao if headline == cartao.headline else replace(
            cartao, headline=headline)
        asset_ops.append(demand_gen_ops.op_asset_cartao(
            c, cid, i, cartao_limpo, imagens_rn, url))
        cartoes_rn.append(demand_gen_ops.temp_asset_dg(cid, i))
    demand_gen_ops.preencher_carrossel(
        c, ada,
        headline=textos["headlines"][0],
        description=textos["descriptions"][0],
        business_name=textos["business_name"],
        logo_rn=logo_rn,
        cartoes_rn=cartoes_rn,
        call_to_action=v25.call_to_action,
    )
    return o, asset_ops


def _rn_da_imagem(c, cid: str, item, papel: str, asset_ops: list) -> str:
    """Imagem nova vira asset no mesmo mutate; remota só é referenciada."""
    if isinstance(item, ImagemParaSubir):
        rn = comum.temp_imagem(cid, len(asset_ops))
        oa = c.get_type("MutateOperation")
        cria = oa.asset_operation.create
        cria.resource_name = rn
        cria.name = item.nome
        cria.type_ = c.enums.AssetTypeEnum.IMAGE
        cria.image_asset.data = item.dados
        asset_ops.append(oa)
        return rn
    if isinstance(item, AssetRemotoDemandGen):
        # Os bytes viajaram só para a reconferência offline. Um asset remoto
        # é referenciado; nunca é reenviado ou recriado.
        return item.resource_name
    # guarda de profundidade; _checar_imagens barra antes
    raise TypeError(
        f"asset Demand Gen sem forma tipada no papel {papel}: "
        f"{type(item).__name__}"
    )


def validar(cid: str, brief: Brief, *, login_customer_id: str):
    """Validação local + ``validate_only``; nunca cria recurso."""
    ops, r = construir(cid, brief, login_customer_id=login_customer_id)
    if not r.ok:
        return r, None, 0
    falha = validar_mutacoes(cid, ops, login_customer_id=login_customer_id)
    return r, falha, len(ops)


# ── o plano, para quem não pode importar protobuf ──────────────────────────

#: Ausências DECLARADAS de Demand Gen — a MESMA tupla que
#: `campanha/perfil.py` publica como `DEMAND_GEN.acoes_indisponiveis`.
NAO_OPERADO: tuple[str, ...] = (
    "subir: o engine monta e prova por validate_only, mas a mutação real "
    "permanece fechada até o contrato HTTP e o canário aceitarem o mesmo "
    "payload de assets sem reconstrução divergente.",
    "formato produto (DemandGenProductAdInfo) não entra: exige Merchant "
    "Center vinculado.",
    "frequency cap não existe em Demand Gen na v25: Campaign.frequency_caps é "
    "recusado em qualquer nível (OPERATION_NOT_PERMITTED_FOR_CONTEXT, medido).",
    "teto/piso de CPC (cpc_bid_ceiling/floor) não entra: recusado em "
    "MaxConv e TargetSpend de Demand Gen (medido).",
    "carrossel só com imagem REMOTA nos cartões: o cartão não resolve id "
    "temporário do mesmo mutate (RESOURCE_NOT_FOUND, medido).",
    "companion banner do vídeo e classic_display_images do multi-asset não "
    "entram: exigem tamanhos de display (ex.: 300x60) que o Estúdio não "
    "produz.",
    "intenção textual não vira operação (CustomAudience não é criada por "
    "analogia); exclusão de Audience inteira não existe — exclusão é por user "
    "list dentro da Audience composta.",
)


def planejar(cid: str, brief: Brief, *, login_customer_id: str) -> plano.PlanoDeCanal:
    """Monta offline e projeta o payload em plano serializável.

    `pode_criar` é `False` por ESTRUTURA e não por opinião deste arquivo:
    `volc_ads/subir.py` tem dois registros — `CONSTRUTORES_POR_CANAL`
    (SEARCH, DISPLAY) e `PROVADORES_POR_CANAL` (SEARCH, DISPLAY, DEMAND_GEN) —
    e Demand Gen só aparece no segundo. É esse par de dicionários, e não uma
    checagem aqui, que faz "a rota produtiva permanecer recusada".
    """
    ops, r = construir(cid, brief, login_customer_id=login_customer_id)
    monta = bool(ops) and r.ok
    cfg = brief.demand_gen
    nivel = ("ad_group" if (cfg is not None and cfg.upgraded_targeting)
             else "campanha")
    return plano.projetar(
        canal=CANAL,
        customer_id=cid,
        login_customer_id=login_customer_id,
        operacoes=ops,
        resultado=r,
        prontidao=plano.Prontidao(
            monta=monta,
            # O BUILDER sabe provar. A rota HTTP acrescenta um portão de
            # ambiente (`VOLC_DEMAND_GEN_VALIDATE_ONLY`) que não é fato deste
            # módulo — e afirmá-lo aqui seria este arquivo declarar uma coisa
            # que quem o lê não pode verificar.
            pode_provar=True,
            pode_criar=False,
            motivo_nao_monta=(
                "" if monta
                else "o brief não passou na validação local; veja bloqueios"),
            motivo_nao_cria=(
                "Demand Gen prova e não cria, por estrutura: "
                "`volc_ads/subir.py` lista o canal em PROVADORES_POR_CANAL e "
                "NÃO em CONSTRUTORES_POR_CANAL, e uma guarda de import derruba "
                "o módulo se as duas vistas divergirem de `perfil.py`. O único "
                "executor recusa a criação mesmo com selo de validate_only "
                "válido"),
        ),
        nao_operado=NAO_OPERADO,
        aberto_por_ausencia=(
            ()
            if (cfg is not None and (cfg.audiencias or getattr(cfg, "publico", None)))
            else ("audiência: nenhum critério de audiência foi declarado — o "
                  "ad group recebe o inventário que os channel controls "
                  "permitirem, sem restrição de público.",)
        ),
        nivel_geo_idioma=nivel,
    )
