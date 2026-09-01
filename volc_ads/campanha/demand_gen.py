"""Builder seguro da primeira onda de Google Ads Demand Gen.

Esta onda monta somente ``DemandGenMultiAssetAdInfo``. Carrossel, vídeo
responsivo e produto são formatos diferentes, com contratos e imutáveis
próprios; escolher um deles por semelhança seria transformar hipótese em API.

O grafo inteiro entra em um ``GoogleAdsService.Mutate`` atômico:

    budget → campanha PAUSED → ad group PAUSED → critérios confirmados
           → assets de imagem → anúncio multi-asset PAUSED

IDs temporários reutilizam as faixas de ``comum.py``. ``partial_failure`` não
é uma opção do builder. Criação real continua proibida em ``subir.py``; este
módulo serve à montagem offline e à prova ``validate_only`` explicitamente
habilitada pelo servidor.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, replace
from importlib import import_module

from ..gads.client import cliente, validar_mutacoes
from . import comum, conteudo, plano, taxonomia, validacao
from .brief import (
    AssetRemotoDemandGen,
    CANAIS_SELECIONAVEIS_DEMAND_GEN,
    Brief,
    ImagemParaSubir,
    ImagensDemandGen,
    conferir_asset_demand_gen,
)

CANAL = "DEMAND_GEN"
TIPO_DE_ANUNCIO = "DEMAND_GEN_MULTI_ASSET_AD"
LANCES_PERMITIDOS: tuple[str, ...] = ("MAXIMIZE_CONVERSIONS",)
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
    pol = conteudo.abrir_portao(brief, r)

    headlines = conteudo.forma(
        brief.copy.headlines,
        "headline_demandgen",
        r,
        explicacao_dki=_EXPLICACAO_DKI,
    )
    descriptions = conteudo.forma(
        brief.copy.descriptions,
        "description_dgen",
        r,
        explicacao_dki=_EXPLICACAO_DKI,
    )
    nomes = conteudo.forma([brief.copy.business_name], "business_name", r)
    if not brief.copy.business_name.strip():
        r.erro(
            "business_name",
            "",
            "o anúncio multi-asset de Demand Gen exige o nome da empresa "
            "(até 25 de largura de exibição)",
        )

    conteudo.politica(pol, headlines, "headline_demandgen", r)
    conteudo.politica(pol, descriptions, "description_dgen", r)
    conteudo.politica(pol, nomes, "business_name", r)

    imagens = _checar_imagens(cid, brief, r)

    if not r.ok or cfg is None:
        return [], r

    c = cliente(login_customer_id)
    ops = [
        comum.op_budget(c, cid, brief, f"Budget_{ts}"),
        comum.op_campanha(c, cid, brief, base, CANAL),
    ]

    # Com upgraded_targeting=False, geo e idioma são critérios da campanha.
    # Com True, o campo imutável move ambos para o ad group.
    if not cfg.upgraded_targeting:
        ops.extend((comum.op_geo(c, cid, brief), comum.op_idioma(c, cid, brief)))

    ops.append(_op_ad_group(c, cid, base, cfg))

    if cfg.upgraded_targeting:
        ops.extend(
            (_op_geo_ad_group(c, cid, brief), _op_idioma_ad_group(c, cid, brief))
        )

    for rn in cfg.audiencias or ():
        ops.append(_op_audiencia(c, cid, rn))

    ad_op, asset_ops = _op_anuncio(
        c,
        cid,
        brief,
        imagens,
        headlines=headlines,
        descriptions=descriptions,
        business_name=nomes[0],
    )
    ops.extend(asset_ops)
    ops.append(ad_op)
    return ops, r


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
            "a matriz v25 confirma `audience` e o campo imutável `negative`, "
            "mas não confirma nesta versão a combinação como exclusão Demand "
            "Gen. A prova falha fechada até a fonte/SDK local cobrirem o caso",
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

    if brief.estrategia_lance not in LANCES_PERMITIDOS:
        r.erro(
            "estrategia_lance",
            brief.estrategia_lance,
            "esta onda implementa somente MAXIMIZE_CONVERSIONS; Target CPA, "
            "Target ROAS, Maximize Clicks e Target CPC exigem contratos "
            "próprios e Target CPC ainda diverge entre fontes oficiais",
        )
    if brief.tcpa is not None:
        r.erro(
            "tcpa",
            str(brief.tcpa),
            "tCPA preenchido mudaria a estratégia efetiva; esta onda escolhe "
            "Maximize Conversions sem meta numérica e preserva ausência",
        )

    # Estes três domínios não têm campo no anúncio multi-asset. Recusar é mais
    # seguro do que fingir que uma keyword virou intenção ou exclusão.
    if brief.keywords or brief.sub_intencoes or brief.criterios:
        r.erro(
            "keywords",
            "preenchido",
            "Demand Gen não opera keywords. Use `audiencias`, `intencoes` e "
            "`exclusoes_de_audiencia` nos campos separados do contrato",
        )
    if brief.copy.long_headlines:
        r.erro(
            "copy.long_headlines",
            f"{len(brief.copy.long_headlines)}",
            "long headline pertence ao formato de vídeo responsivo, não ao "
            "DemandGenMultiAssetAdInfo escolhido nesta onda",
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
            "vídeo exige DemandGenVideoResponsiveAdInfo, outro tipo de anúncio; "
            "esta onda não mistura contratos criativos",
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


def _checar_imagens(cid: str, brief: Brief, r: validacao.Resultado) -> ImagensDemandGen:
    imagens = brief.imagens_demand_gen
    if imagens is None:
        r.erro(
            "imagens_demand_gen",
            "ausente",
            "o anúncio multi-asset exige ImagensDemandGen com ao menos uma "
            "imagem horizontal ou quadrada e um logo quadrado aprovado",
        )
        return ImagensDemandGen()

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
                )
                if canonico is None:
                    continue
                identidade = f"remoto-sem-recibo:{canonico}"
            else:
                r.erro(
                    f"imagens_demand_gen.{papel}",
                    type(item).__name__,
                    "forma de asset desconhecida; ausência de tipo não autoriza reuso",
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


def _op_ad_group(c, cid: str, nome_base: str, cfg):
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
        for canal in CANAIS_SELECIONAVEIS_DEMAND_GEN:
            if canal in escolha.selected_channels:
                setattr(controles.selected_channels, canal, True)
    else:
        controles.channel_strategy = getattr(
            c.enums.DemandGenChannelStrategyEnum, escolha.estrategia
        )
    # `channel_config` é output-only e nunca é escrito.
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
    *,
    headlines: list[str],
    descriptions: list[str],
    business_name: str,
):
    o = c.get_type("MutateOperation")
    ada = o.ad_group_ad_operation.create
    ada.ad_group = comum.temp_adgroup(cid, 0)
    ada.status = c.enums.AdGroupAdStatusEnum.PAUSED
    ada.ad.final_urls.append(comum.url_destino(brief))
    info = ada.ad.demand_gen_multi_asset_ad

    for texto in headlines:
        asset = c.get_type("AdTextAsset")
        asset.text = texto
        info.headlines.append(asset)
    for texto in descriptions:
        asset = c.get_type("AdTextAsset")
        asset.text = texto
        info.descriptions.append(asset)
    info.business_name = business_name

    asset_ops: list = []
    for papel, campo in PAPEIS_DE_IMAGEM:
        destino = getattr(info, campo)
        for item in getattr(imagens, papel):
            if isinstance(item, ImagemParaSubir):
                rn = comum.temp_imagem(cid, len(asset_ops))
                oa = c.get_type("MutateOperation")
                cria = oa.asset_operation.create
                cria.resource_name = rn
                cria.name = item.nome
                cria.type_ = c.enums.AssetTypeEnum.IMAGE
                cria.image_asset.data = item.dados
                asset_ops.append(oa)
            elif isinstance(item, AssetRemotoDemandGen):
                # Os bytes viajaram só para a reconferência offline. Um asset
                # remoto é referenciado; nunca é reenviado ou recriado.
                rn = item.resource_name
            else:  # guarda de profundidade; _checar_imagens barra antes
                raise TypeError(
                    f"asset Demand Gen sem forma tipada no papel {papel}: "
                    f"{type(item).__name__}"
                )
            imagem = c.get_type("AdImageAsset")
            imagem.asset = rn
            destino.append(imagem)
    return o, asset_ops


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
    "subir: a primeira onda só monta e prova por validate_only. O único "
    "executor recusa criação real mesmo com selo válido.",
    "formatos carrossel, vídeo responsivo e produto não entram: cada um "
    "tem outro contrato de assets e imutáveis.",
    "intenção textual e exclusão de audiência ficam separadas, mas não "
    "viram operação até a documentação/SDK local confirmarem o caminho.",
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
            if (cfg is not None and cfg.audiencias)
            else ("audiência: nenhum critério de audiência foi declarado — o "
                  "ad group recebe o inventário que os channel controls "
                  "permitirem, sem restrição de público.",)
        ),
        nivel_geo_idioma=nivel,
    )
