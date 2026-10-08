"""Demand Gen v25.2 — as decisões novas, tipadas, e a régua de cada uma.

## Por que um módulo à parte, e não campos novos em `brief.py`

`ConfiguracaoDemandGen` mora em `brief.py`, que este canal não edita. A extensão
é uma SUBCLASSE (`ConfiguracaoDemandGenV25`) com todos os campos novos
defaultados — o mesmo gesto de `pmax_config.ConfiguracaoPMaxV25`. Ela viaja
dentro do MESMO campo `Brief.demand_gen`, então nenhum campo novo de `Brief` é
necessário para o builder recebê-la:

  * chamador antigo entrega `ConfiguracaoDemandGen` → payload idêntico ao de
    antes (multi-asset, MaxConv sem meta, três automações OPTED_OUT);
  * chamador novo entrega `ConfiguracaoDemandGenV25` → as escolhas abaixo.

Vídeo NÃO é canal próprio nesta casa (decisão do dono, 08/10/2026): vídeo vive
dentro de Demand Gen e PMax. Por isso o vídeo responsivo de Demand Gen é
completo aqui — e não "a outra metade" de um canal Vídeo que não existe.

Este arquivo é **stdlib + brief**: não importa `google.ads`. Os nomes de enum
são tuplas escritas aqui, e `testes_demand_gen.py` as confere contra o proto v25
instalado — para a tela poder ler o mesmo vocabulário sem segunda lista.

## O que foi MEDIDO (validate_only na Crédito Up 547-809-6539, MCC 490-407-4301,
## 08/10/2026, google-ads 33.0.0 / v25)

Lance:
  * `maximize_conversions` vazio, `target_cpa` avulso, `target_spend` vazio e
    `target_cpc` (novo na v25): ACEITOS.
  * `maximize_conversions.target_cpa_micros`, `maximize_conversion_value.
    target_roas` e qualquer `cpc_bid_ceiling_micros` (MaxConv ou TargetSpend):
    `context_error.OPERATION_NOT_PERMITTED_FOR_CONTEXT`. tCPA/tROAS de Demand Gen
    são as estratégias AVULSAS `target_cpa`/`target_roas`.
  * `maximize_conversion_value` vazio e `target_roas` avulso:
    `campaign_error.NOT_ENOUGH_CONVERSIONS` — elegibilidade da CONTA, não recusa
    de contexto (a mesma requisição com tROAS dentro de MaxConvValue devolve o
    erro de contexto, então o servidor distingue as duas coisas).
Frequência e agenda:
  * `Campaign.frequency_caps` em DEMAND_GEN, em qualquer nível/evento/unidade:
    `OPERATION_NOT_PERMITTED_FOR_CONTEXT`. Não há frequency cap nesta versão.
  * `CampaignCriterion.ad_schedule`: ACEITO.
Públicos:
  * `Audience` criada NO MESMO mutate (id temporário) com idade, gênero, renda,
    status parental, segmentos de user list e `exclusion_dimension`: ACEITA, e
    o `AdGroupCriterion.audience` a referencia pelo id temporário.
  * `UserList.lookalike_user_list` criada no mesmo mutate e usada como segmento
    da Audience: ACEITA (o validate_only não confere o piso de 100 membros
    ativos das sementes; isso só aparece depois, como "Ineligible").
  * Com `ad_group.audience_setting.use_audience_grouped = true`, critério
    direto `age_range`/`user_list` (positivo ou negativo) no grupo:
    `CANNOT_ADD_AUDIENCE_SEGMENT_CRITERION_WHEN_AUDIENCE_GROUPED_IS_SET`.
    Demografia e exclusão moram DENTRO da Audience.
  * `optimized_targeting_enabled` true e false: ACEITOS.
Formatos:
  * Vídeo responsivo: `ad.name` OBRIGATÓRIO (`field_error.REQUIRED`); vídeo
    público de terceiro aceito (`M7lc1UVf-VE`); id inexistente →
    `youtube_video_registration_error.VIDEO_NOT_FOUND`; 6 vídeos, 6 headlines,
    2 logos, 2 CTAs → `TOO_MANY`; headline de 41 e breadcrumb de 16 →
    `TOO_LONG`; breadcrumb2 sem breadcrumb1 → `VALUE_MUST_BE_UNSET`; sem long
    headline e sem description → `TOO_FEW`; companion banner 600x314 →
    `DIMENSIONS_NOT_ALLOWED`.
  * Carrossel: 1 cartão → `TOO_FEW`; 11 → `TOO_MANY`; headline do anúncio de
    41 e description de 91 → `TOO_LONG` (40/90 passam; o Help Center diz 40
    para a description, a API aceita 90); headline do cartão de 41 → `TOO_LONG`;
    a mesma imagem em dois cartões → `DUPLICATE_IMAGE_ACROSS_CAROUSEL_CARDS`;
    cartão só com retrato → `REQUIRED marketing_image_asset`.
    ⚠️ A imagem do CARTÃO não resolve id temporário: referenciar um asset de
    imagem criado no mesmo mutate devolve `RESOURCE_NOT_FOUND` no campo do
    cartão (o logo do anúncio, no mesmo request, resolve). Imagem de cartão
    precisa ser asset REMOTO já existente.
  * `call_to_action_text` é uma lista fechada do servidor (ver
    `TEXTOS_DE_CTA_ACEITOS`): "Saiba mais" → `INVALID_CALL_TO_ACTION_TEXT`,
    "Saiba Mais" passa.
  * Automação de criativo é por TIPO DE ANÚNCIO: tipo de multi-asset num
    anúncio de vídeo → `enum_error.ENUM_VALUE_NOT_PERMITTED`. As quatro de
    vídeo aceitam OPTED_IN e OPTED_OUT.
  * Channel controls: ALL_CHANNELS, ALL_OWNED_AND_OPERATED_CHANNELS e
    SELECTED_CHANNELS com os 7 canais (incluindo `maps`): ACEITOS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Mapping
from urllib.parse import urlsplit

from .. import automacoes as _automacoes
from .brief import (
    ROAS_MAX,
    ROAS_MIN,
    AssetRemotoAprovado,
    ConfiguracaoDemandGen,
    ImagemParaSubir,
    faixa_de_roas_invalida,
)

# ═══════════════════════════════════════════════════════════════════════════
# FORMATO DO ANÚNCIO
# ═══════════════════════════════════════════════════════════════════════════

#: Os três formatos que este builder emite. Produto (`DemandGenProductAdInfo`)
#: fica FORA: exige Merchant Center vinculado, que a casa não tem.
FORMATOS: tuple[str, ...] = ("MULTI_ASSET", "VIDEO_RESPONSIVO", "CARROSSEL")

#: O campo do `Ad` que cada formato ocupa (oneof `ad_data`).
CAMPO_DO_FORMATO: Mapping[str, str] = {
    "MULTI_ASSET": "demand_gen_multi_asset_ad",
    "VIDEO_RESPONSIVO": "demand_gen_video_responsive_ad",
    "CARROSSEL": "demand_gen_carousel_ad",
}

# ═══════════════════════════════════════════════════════════════════════════
# LANCE
# ═══════════════════════════════════════════════════════════════════════════

#: Estratégias de ENTRADA (nomes do `BiddingStrategyTypeEnum`). A forma no
#: payload é decidida pela meta:
#:
#:   MAXIMIZE_CONVERSIONS        sem meta → `maximize_conversions` vazio
#:                               com `target_cpa` → `target_cpa` avulso
#:   MAXIMIZE_CONVERSION_VALUE   sem meta → `maximize_conversion_value` vazio
#:                               com `target_roas` → `target_roas` avulso
#:   TARGET_SPEND                "Maximizar cliques": `target_spend` vazio
#:   TARGET_CPC                  `target_cpc.target_cpc_micros` (obrigatório)
#:
#: ⚠️ A meta DENTRO de MaxConv/MaxConvValue é recusada pela API em Demand Gen
#: (medido); por isso a meta muda a mensagem emitida, não o nome de entrada.
ESTRATEGIAS: tuple[str, ...] = (
    "MAXIMIZE_CONVERSIONS",
    "MAXIMIZE_CONVERSION_VALUE",
    "TARGET_SPEND",
    "TARGET_CPC",
)

#: O que `Brief.estrategia_lance` monta SOZINHO, sem `LanceDemandGen`. Só
#: MaxConv sem meta: é o único ramo que `comum.op_campanha` emite para Demand
#: Gen. Qualquer outra estratégia vinda só do brief cairia nesse mesmo ramo em
#: silêncio — e desde 08/10/2026 o brief conhece TARGET_SPEND/TARGET_CPC pelo
#: nome, então a recusa deixou de ser garantida pelo portão de forma do brief.
ESTRATEGIAS_PELO_BRIEF: tuple[str, ...] = ("MAXIMIZE_CONVERSIONS",)

#: Estratégias cuja prova na Crédito Up parou na ELEGIBILIDADE da conta
#: (`NOT_ENOUGH_CONVERSIONS`), não no contrato. O builder as monta; o plano
#: avisa que a conta precisa de histórico de valor de conversão.
ESTRATEGIAS_DEPENDENTES_DE_CONVERSAO: tuple[str, ...] = (
    "MAXIMIZE_CONVERSION_VALUE",
)

# ═══════════════════════════════════════════════════════════════════════════
# AUTOMAÇÕES DE CRIATIVO — por tipo de anúncio, todas OPTED_OUT por default
# ═══════════════════════════════════════════════════════════════════════════

#: Fonte: guia "asset-automation-settings" (tabela ad-level, v25) + medição.
#: Multi-asset repete a ORDEM de `automacoes.AUTOMACOES_DEMAND_GEN_RECUSADAS`
#: para o payload legado não mudar de bytes. Carrossel não tem automação
#: ad-level na v25 — a tupla vazia é o contrato, não esquecimento.
AUTOMACOES_POR_FORMATO: Mapping[str, tuple[str, ...]] = {
    "MULTI_ASSET": (
        "GENERATE_DESIGN_VERSIONS_FOR_IMAGES",
        "GENERATE_VIDEOS_FROM_OTHER_ASSETS",
        "GENERATE_ANIMATED_IMAGES_FROM_OTHER_ASSETS",
    ),
    "VIDEO_RESPONSIVO": (
        "GENERATE_LANDING_PAGE_PREVIEW",
        "GENERATE_LANDING_PAGE_TEXT",
        "GENERATE_SHORTER_YOUTUBE_VIDEOS",
        "GENERATE_VERTICAL_YOUTUBE_VIDEOS",
    ),
    "CARROSSEL": (),
}

#: O que cada automação de VÍDEO faria ligada. A frase mora em
#: `automacoes.POR_QUE_RECUSADA` (stdlib, lida pela tela) desde 08/10/2026;
#: esta vista a REFERENCIA, para não haver duas redações divergindo.
POR_QUE_RECUSADA_VIDEO: Mapping[str, str] = {
    nome: _automacoes.POR_QUE_RECUSADA[nome]
    for nome in AUTOMACOES_POR_FORMATO["VIDEO_RESPONSIVO"]
}

STATUS_DE_AUTOMACAO: tuple[str, ...] = ("OPTED_IN", "OPTED_OUT")

# ═══════════════════════════════════════════════════════════════════════════
# CTA, TEXTOS, LIMITES
# ═══════════════════════════════════════════════════════════════════════════

#: `call_to_action_text` (multi-asset, carrossel e cartão) é uma lista FECHADA
#: do servidor, sensível a caixa em português. Estes 22 foram ACEITOS no
#: validate_only de 08/10/2026; recusados no mesmo lote, entre outros:
#: "Saiba mais", "Cadastre-se", "Candidate-se", "Baixar", "Compre agora",
#: "Install", "Buy now", "Watch now", "Get started". Lista local fechada porque
#: a alternativa — mandar texto livre — descobre o erro no lote inteiro.
TEXTOS_DE_CTA_ACEITOS: tuple[str, ...] = (
    "Saiba Mais", "Inscreva-se", "Inscrever-se", "Reservar", "Fale conosco",
    "Visitar site", "Comprar agora", "Ver mais",
    "Learn more", "Learn More", "Apply now", "Book now", "Contact us",
    "Download", "Visit site", "Shop now", "Sign up", "Get quote", "Subscribe",
    "See more", "Get offer", "Call now",
)

#: `CallToActionAsset.call_to_action` do vídeo responsivo (`CallToActionType`
#: v25, sem UNSPECIFIED/UNKNOWN). No vídeo o CTA é um ASSET tipado, não texto.
CTAS_DE_VIDEO: tuple[str, ...] = (
    "LEARN_MORE", "GET_QUOTE", "APPLY_NOW", "SIGN_UP", "CONTACT_US",
    "SUBSCRIBE", "DOWNLOAD", "BOOK_NOW", "SHOP_NOW", "BUY_NOW", "DONATE_NOW",
    "ORDER_NOW", "PLAY_NOW", "SEE_MORE", "START_NOW", "VISIT_SITE",
    "WATCH_NOW",
)

#: Limites medidos (largura de exibição, como `limites.yaml` mede). Chaves
#: PRÓPRIAS deste módulo porque `limites.yaml` só conhece o multi-asset (30) e
#: o vídeo/carrossel aceitam 40 — herdar o 30 recusaria texto válido.
LIMITES_DE_TEXTO: Mapping[str, Mapping[str, int]] = {
    # vídeo responsivo: 1..5 cada (6 → TOO_MANY); 40/90/90 (41 → TOO_LONG)
    "headline_video": {"max_chars": 40, "min_itens": 1, "max_itens": 5},
    "long_headline_video": {"max_chars": 90, "min_itens": 1, "max_itens": 5},
    "description_video": {"max_chars": 90, "min_itens": 1, "max_itens": 5},
    # carrossel: um de cada no anúncio (campos singulares do proto)
    "headline_carrossel": {"max_chars": 40, "min_itens": 1, "max_itens": 1},
    "description_carrossel": {"max_chars": 90, "min_itens": 1, "max_itens": 1},
    "headline_cartao": {"max_chars": 40, "min_itens": 1, "max_itens": 1},
}

BREADCRUMB_MAX_CHARS = 15        # 16 → TOO_LONG (medido)
VIDEOS_MIN, VIDEOS_MAX = 1, 5    # 6 → TOO_MANY (medido); Help: "1-5 videos"
CARTOES_MIN, CARTOES_MAX = 2, 10  # 1 → TOO_FEW, 11 → TOO_MANY (medido)
FAIXAS_DE_AGENDA_POR_DIA_MAX = 6  # teto da API para AdSchedule por dia
LOOKALIKES_MAX = 10
USER_LISTS_MAX = 20

#: Papéis de imagem do CARTÃO de carrossel → campo de
#: `DemandGenCarouselCardAsset`. Sem retrato alto: o cartão não tem o campo.
PAPEIS_DO_CARTAO: Mapping[str, str] = {
    "marketing": "marketing_image_asset",
    "marketing_quadrada": "square_marketing_image_asset",
    "marketing_retrato": "portrait_marketing_image_asset",
}

# ── públicos ────────────────────────────────────────────────────────────────

#: `AgeSegment` aceita só estes pares (min, max); `None` é "sem teto" (65+).
FAIXAS_ETARIAS: Mapping[str, tuple[int, int | None]] = {
    "18-24": (18, 24),
    "25-34": (25, 34),
    "35-44": (35, 44),
    "45-54": (45, 54),
    "55-64": (55, 64),
    "65+": (65, None),
}
GENEROS: tuple[str, ...] = ("MALE", "FEMALE")
FAIXAS_DE_RENDA: tuple[str, ...] = (
    "INCOME_RANGE_0_50", "INCOME_RANGE_50_60", "INCOME_RANGE_60_70",
    "INCOME_RANGE_70_80", "INCOME_RANGE_80_90", "INCOME_RANGE_90_UP",
)
STATUS_PARENTAIS: tuple[str, ...] = ("PARENT", "NOT_A_PARENT")
NIVEIS_DE_LOOKALIKE: tuple[str, ...] = ("NARROW", "BALANCED", "BROAD")

# ── agenda ──────────────────────────────────────────────────────────────────

DIAS_DA_SEMANA: tuple[str, ...] = (
    "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY",
    "SUNDAY",
)
#: `MinuteOfHour` só tem quatro valores; 08:10 não existe na API.
MINUTOS: Mapping[int, str] = {0: "ZERO", 15: "FIFTEEN", 30: "THIRTY",
                              45: "FORTY_FIVE"}

_ID_YOUTUBE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HORA = re.compile(r"^(\d{2}):(\d{2})$")
_USER_LIST = re.compile(r"^customers/(\d+)/userLists/(\d+)$")
_PAIS = re.compile(r"^[A-Z]{2}$")


def _tupla(dono: str, campo: str, valor) -> tuple:
    if isinstance(valor, (str, bytes)) or not isinstance(valor, (tuple, list, frozenset, set)):
        raise TypeError(f"{dono}.{campo} precisa ser sequência, não {type(valor).__name__}")
    return tuple(valor)


def _texto_opcional(dono: str, campo: str, valor) -> None:
    if valor is not None and (not isinstance(valor, str) or not valor.strip()):
        raise ValueError(
            f"{dono}.{campo}: ausência é None; texto vazio seria escolha sem "
            "conteúdo")


# ═══════════════════════════════════════════════════════════════════════════
# AS PEÇAS
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class LanceDemandGen:
    """A estratégia de lance, com a meta que a acompanha — e só ela.

    Metas em moeda da conta (não micros): `target_cpa` e `target_cpc` em
    unidade monetária; `target_roas` como razão (4.0 = 400%).
    """

    estrategia: str
    target_cpa: float | None = None
    target_roas: float | None = None
    target_cpc: float | None = None

    def __post_init__(self) -> None:
        if self.estrategia not in ESTRATEGIAS:
            raise ValueError(
                f"estratégia Demand Gen {self.estrategia!r} inválida; use "
                f"{', '.join(ESTRATEGIAS)}")
        for campo in ("target_cpa", "target_roas", "target_cpc"):
            valor = getattr(self, campo)
            if valor is not None and (isinstance(valor, bool) or valor <= 0):
                raise ValueError(
                    f"LanceDemandGen.{campo}={valor!r}: meta ausente é None, "
                    "nunca 0 ou negativa")
        # A MESMA faixa de tROAS dos outros três canais (razão, 4.0 = 400%).
        recusa_roas = faixa_de_roas_invalida(self.target_roas)
        if recusa_roas:
            raise ValueError(f"LanceDemandGen.{recusa_roas}")
        permitidas = {
            "MAXIMIZE_CONVERSIONS": {"target_cpa"},
            "MAXIMIZE_CONVERSION_VALUE": {"target_roas"},
            "TARGET_SPEND": set(),
            "TARGET_CPC": {"target_cpc"},
        }[self.estrategia]
        intrusas = sorted(
            c for c in ("target_cpa", "target_roas", "target_cpc")
            if getattr(self, c) is not None and c not in permitidas)
        if intrusas:
            raise ValueError(
                f"{self.estrategia} não carrega {intrusas}: meta de outra "
                "estratégia seria descartada em silêncio")
        if self.estrategia == "TARGET_CPC" and self.target_cpc is None:
            raise ValueError("TARGET_CPC exige `target_cpc`; a API não tem "
                             "Target CPC sem alvo")

    @property
    def campo_do_proto(self) -> str:
        """O membro do oneof `campaign_bidding_strategy` que será emitido."""
        if self.estrategia == "MAXIMIZE_CONVERSIONS":
            return "target_cpa" if self.target_cpa else "maximize_conversions"
        if self.estrategia == "MAXIMIZE_CONVERSION_VALUE":
            return ("target_roas" if self.target_roas
                    else "maximize_conversion_value")
        return {"TARGET_SPEND": "target_spend", "TARGET_CPC": "target_cpc"}[
            self.estrategia]


@dataclass(frozen=True)
class VideoDemandGen:
    """O que só o vídeo responsivo tem. Textos vêm de `brief.copy`.

    `brief.copy.headlines` (≤40, 1..5), `long_headlines` (≤90, 1..5),
    `descriptions` (≤90, 1..5) e `business_name`; o logo é
    `imagens_demand_gen.logo_quadrado` com EXATAMENTE um item.
    """

    youtube_ids: tuple[str, ...]
    call_to_action: str | None = None
    breadcrumb1: str | None = None
    breadcrumb2: str | None = None

    def __post_init__(self) -> None:
        ids = _tupla("VideoDemandGen", "youtube_ids", self.youtube_ids)
        object.__setattr__(self, "youtube_ids", ids)
        if not VIDEOS_MIN <= len(ids) <= VIDEOS_MAX:
            raise ValueError(
                f"vídeo responsivo aceita {VIDEOS_MIN}..{VIDEOS_MAX} vídeos; "
                f"vieram {len(ids)}")
        for vid in ids:
            if not isinstance(vid, str) or not _ID_YOUTUBE.fullmatch(vid):
                raise ValueError(
                    f"id de YouTube inválido {vid!r}: são 11 caracteres "
                    "[A-Za-z0-9_-], não URL")
        if len(set(ids)) != len(ids):
            raise ValueError("vídeo repetido não vira duas vagas; remova a "
                             "duplicata")
        if self.call_to_action is not None and self.call_to_action not in CTAS_DE_VIDEO:
            raise ValueError(
                f"CTA de vídeo {self.call_to_action!r} inválido; use "
                f"{', '.join(CTAS_DE_VIDEO)}")
        for campo in ("breadcrumb1", "breadcrumb2"):
            valor = getattr(self, campo)
            _texto_opcional("VideoDemandGen", campo, valor)
            if valor is not None and len(valor.strip()) > BREADCRUMB_MAX_CHARS:
                raise ValueError(
                    f"{campo} tem {len(valor.strip())} caracteres; o teto é "
                    f"{BREADCRUMB_MAX_CHARS}")
        if self.breadcrumb2 is not None and self.breadcrumb1 is None:
            raise ValueError(
                "breadcrumb2 sem breadcrumb1: a API devolve "
                "VALUE_MUST_BE_UNSET")


ImagemDoCartao = ImagemParaSubir | AssetRemotoAprovado


@dataclass(frozen=True)
class CartaoCarrosselDemandGen:
    """Um cartão. Imagens por papel; ao menos paisagem ou quadrada.

    ⚠️ As imagens precisam ser `AssetRemotoAprovado` (asset já na conta): o
    cartão NÃO resolve id temporário (medido). `ImagemParaSubir` é aceita na
    FORMA e recusada pelo builder com essa explicação — para a tela poder
    dizer "suba as imagens antes", em vez de o tipo esconder o motivo.
    """

    headline: str
    marketing: ImagemDoCartao | None = None
    marketing_quadrada: ImagemDoCartao | None = None
    marketing_retrato: ImagemDoCartao | None = None
    url_final: str | None = None
    call_to_action: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.headline, str) or not self.headline.strip():
            raise ValueError("cartão sem headline")
        if self.marketing is None and self.marketing_quadrada is None:
            raise ValueError(
                "cartão exige imagem paisagem ou quadrada; só retrato devolve "
                "REQUIRED marketing_image_asset (medido)")
        _texto_opcional("CartaoCarrosselDemandGen", "url_final", self.url_final)
        if self.url_final is not None and not self.url_final.startswith("https://"):
            raise ValueError("url_final do cartão precisa ser https")
        if (self.call_to_action is not None
                and self.call_to_action not in TEXTOS_DE_CTA_ACEITOS):
            raise ValueError(
                f"CTA {self.call_to_action!r} fora da lista aceita pela API")

    @property
    def papeis(self) -> tuple[str, ...]:
        return tuple(p for p in PAPEIS_DO_CARTAO if getattr(self, p) is not None)


@dataclass(frozen=True)
class CarrosselDemandGen:
    """2..10 cartões, mesmas orientações em todos (Help Center: proporção
    consistente). Headline/description do anúncio vêm de `brief.copy`, com
    EXATAMENTE um item cada; logo é `imagens_demand_gen.logo_quadrado` (1)."""

    cartoes: tuple[CartaoCarrosselDemandGen, ...]

    def __post_init__(self) -> None:
        cartoes = _tupla("CarrosselDemandGen", "cartoes", self.cartoes)
        object.__setattr__(self, "cartoes", cartoes)
        if not CARTOES_MIN <= len(cartoes) <= CARTOES_MAX:
            raise ValueError(
                f"carrossel aceita {CARTOES_MIN}..{CARTOES_MAX} cartões; "
                f"vieram {len(cartoes)}")
        if any(not isinstance(c, CartaoCarrosselDemandGen) for c in cartoes):
            raise TypeError("cartões precisam ser CartaoCarrosselDemandGen")
        papeis = {c.papeis for c in cartoes}
        if len(papeis) > 1:
            raise ValueError(
                "todos os cartões precisam das MESMAS orientações de imagem "
                f"(vieram {sorted(papeis)}); o Help Center exige proporção "
                "consistente entre cartões")


@dataclass(frozen=True)
class LookalikeDemandGen:
    """Segmento semelhante criado NO MESMO mutate (`UserList.lookalike_user_list`).

    Sementes são IDs numéricos de user list da conta (o proto pede `int64`,
    não resource name). O piso de 100 membros ativos somados NÃO é conferido
    pelo validate_only — a lista nasce e fica "Ineligible" até ter base.
    """

    nome: str
    sementes: tuple[int, ...]
    expansao: str
    paises: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.nome, str) or not self.nome.strip():
            raise ValueError("lookalike sem nome")
        sementes = _tupla("LookalikeDemandGen", "sementes", self.sementes)
        paises = _tupla("LookalikeDemandGen", "paises", self.paises)
        object.__setattr__(self, "sementes", sementes)
        object.__setattr__(self, "paises", paises)
        if not sementes:
            raise ValueError("lookalike exige ao menos uma user list semente")
        if any(isinstance(s, bool) or not isinstance(s, int) or s <= 0 for s in sementes):
            raise ValueError("semente de lookalike é id numérico positivo")
        if len(set(sementes)) != len(sementes):
            raise ValueError("semente repetida no lookalike")
        if self.expansao not in NIVEIS_DE_LOOKALIKE:
            raise ValueError(
                f"expansão {self.expansao!r} inválida; use "
                f"{', '.join(NIVEIS_DE_LOOKALIKE)}")
        if not paises or any(not isinstance(p, str) or not _PAIS.fullmatch(p) for p in paises):
            raise ValueError("países do lookalike: ISO 3166-1 alfa-2 em "
                             "maiúsculas, ao menos um")


@dataclass(frozen=True)
class PublicoDemandGen:
    """Uma `Audience` composta no mesmo mutate e anexada ao ad group.

    Dimensão vazia = dimensão NÃO emitida (todas as idades, todos os gêneros…).
    `incluir_*_indeterminado` só viaja quando a dimensão é emitida.
    Exclusão é por USER LIST, dentro da Audience (`exclusion_dimension`) — é o
    único tipo de segmento excluível na v25.
    """

    nome: str
    user_lists: tuple[str, ...] = ()
    lookalikes: tuple[LookalikeDemandGen, ...] = ()
    exclusoes_user_list: tuple[str, ...] = ()
    idades: tuple[str, ...] = ()
    incluir_idade_indeterminada: bool = True
    generos: tuple[str, ...] = ()
    incluir_genero_indeterminado: bool = True
    rendas: tuple[str, ...] = ()
    incluir_renda_indeterminada: bool = True
    status_parentais: tuple[str, ...] = ()
    incluir_status_parental_indeterminado: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.nome, str) or not self.nome.strip():
            raise ValueError("público sem nome; a Audience é recurso da conta "
                             "e precisa ser encontrável depois")
        for campo, universo in (
            ("idades", tuple(FAIXAS_ETARIAS)),
            ("generos", GENEROS),
            ("rendas", FAIXAS_DE_RENDA),
            ("status_parentais", STATUS_PARENTAIS),
        ):
            valor = _tupla("PublicoDemandGen", campo, getattr(self, campo))
            object.__setattr__(self, campo, valor)
            fora = sorted(set(valor) - set(universo))
            if fora:
                raise ValueError(f"{campo} desconhecidos {fora}; use "
                                 f"{', '.join(universo)}")
            if len(set(valor)) != len(valor):
                raise ValueError(f"{campo} com item repetido")
        for campo in ("user_lists", "exclusoes_user_list", "lookalikes"):
            object.__setattr__(
                self, campo,
                _tupla("PublicoDemandGen", campo, getattr(self, campo)))
        if len(self.lookalikes) > LOOKALIKES_MAX:
            raise ValueError(f"no máximo {LOOKALIKES_MAX} lookalikes")
        if any(not isinstance(x, LookalikeDemandGen) for x in self.lookalikes):
            raise TypeError("lookalikes precisam ser LookalikeDemandGen")
        for campo in ("user_lists", "exclusoes_user_list"):
            valor = getattr(self, campo)
            if len(valor) > USER_LISTS_MAX:
                raise ValueError(f"{campo}: no máximo {USER_LISTS_MAX}")
            for rn in valor:
                if not isinstance(rn, str) or not _USER_LIST.fullmatch(rn):
                    raise ValueError(
                        f"{campo}: {rn!r} não é `customers/<cid>/userLists/<id>`")
            if len(set(valor)) != len(valor):
                raise ValueError(f"{campo} com user list repetida")
        cruzadas = set(self.user_lists) & set(self.exclusoes_user_list)
        if cruzadas:
            raise ValueError(
                f"user list incluída E excluída no mesmo público: "
                f"{sorted(cruzadas)}")
        if not (self.user_lists or self.lookalikes or self.exclusoes_user_list
                or self.idades or self.generos or self.rendas
                or self.status_parentais):
            raise ValueError(
                "público sem dimensão nenhuma seria uma Audience vazia; use "
                "`publico=None` para não anexar público")


@dataclass(frozen=True)
class FaixaDeAgendaDemandGen:
    """Uma janela de veiculação: dia + "HH:MM" de início e fim (fuso da conta)."""

    dia: str
    inicio: str
    fim: str

    def __post_init__(self) -> None:
        if self.dia not in DIAS_DA_SEMANA:
            raise ValueError(f"dia {self.dia!r} inválido; use "
                             f"{', '.join(DIAS_DA_SEMANA)}")
        a, b = self.minutos()
        if not 0 <= a < b <= 24 * 60:
            raise ValueError(
                f"faixa {self.inicio}-{self.fim}: início precisa vir antes do "
                "fim, dentro de 00:00..24:00")

    @staticmethod
    def _ler(valor: str) -> tuple[int, int]:
        m = _HORA.fullmatch(str(valor))
        if m is None:
            raise ValueError(f"horário {valor!r} fora do formato HH:MM")
        hora, minuto = int(m.group(1)), int(m.group(2))
        if minuto not in MINUTOS or not 0 <= hora <= 24 or (hora == 24 and minuto):
            raise ValueError(
                f"horário {valor!r}: minutos só 00/15/30/45 (MinuteOfHour) e "
                "hora 0..24")
        return hora, minuto

    def partes(self) -> tuple[int, int, int, int]:
        hi, mi = self._ler(self.inicio)
        hf, mf = self._ler(self.fim)
        return hi, mi, hf, mf

    def minutos(self) -> tuple[int, int]:
        hi, mi, hf, mf = self.partes()
        return hi * 60 + mi, hf * 60 + mf


# ═══════════════════════════════════════════════════════════════════════════
# A CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ConfiguracaoDemandGenV25(ConfiguracaoDemandGen):
    """`ConfiguracaoDemandGen` + as decisões v25.2. Todo campo novo defaultado.

    Defaults = comportamento de antes: multi-asset, lance pelo brief
    (MaxConv sem meta), automações todas OPTED_OUT, sem público composto, sem
    agenda, `optimized_targeting_enabled` não emitido.
    """

    formato: str = "MULTI_ASSET"
    lance: LanceDemandGen | None = None
    #: `call_to_action_text` do multi-asset ou do carrossel (lista fechada).
    call_to_action: str | None = None
    video: VideoDemandGen | None = None
    carrossel: CarrosselDemandGen | None = None
    publico: PublicoDemandGen | None = None
    #: `AdGroup.optimized_targeting_enabled`. None = não emitido. ⚠️ É bool
    #: proto3 SEM presença: False e None viajam com os mesmos bytes e o servidor
    #: lê os dois como desligado. Só True muda o payload.
    segmentacao_otimizada: bool | None = None
    #: Escolha explícita por tipo: {"GENERATE_SHORTER_YOUTUBE_VIDEOS":
    #: "OPTED_IN"}. Tipo ausente viaja OPTED_OUT. Normalizado para tupla de
    #: pares ordenada (hashável e com ordem estável para o selo).
    automacoes: Mapping[str, str] | tuple[tuple[str, str], ...] = ()
    agenda: tuple[FaixaDeAgendaDemandGen, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.formato not in FORMATOS:
            raise ValueError(f"formato Demand Gen {self.formato!r} inválido; "
                             f"use {', '.join(FORMATOS)}")
        if self.formato == "VIDEO_RESPONSIVO" and self.video is None:
            raise ValueError("formato VIDEO_RESPONSIVO exige `video`")
        if self.formato != "VIDEO_RESPONSIVO" and self.video is not None:
            raise ValueError(
                f"`video` preenchido com formato {self.formato}: o bloco não "
                "chegaria ao payload")
        if self.formato == "CARROSSEL" and self.carrossel is None:
            raise ValueError("formato CARROSSEL exige `carrossel`")
        if self.formato != "CARROSSEL" and self.carrossel is not None:
            raise ValueError(
                f"`carrossel` preenchido com formato {self.formato}: o bloco "
                "não chegaria ao payload")
        if self.call_to_action is not None:
            if self.formato == "VIDEO_RESPONSIVO":
                raise ValueError(
                    "no vídeo o CTA é asset tipado: use `video.call_to_action`")
            if self.call_to_action not in TEXTOS_DE_CTA_ACEITOS:
                raise ValueError(
                    f"CTA {self.call_to_action!r} fora da lista aceita pela API "
                    f"({', '.join(TEXTOS_DE_CTA_ACEITOS)})")
        if self.segmentacao_otimizada is not None and not isinstance(
                self.segmentacao_otimizada, bool):
            raise TypeError("segmentacao_otimizada precisa ser bool ou None")
        object.__setattr__(self, "automacoes", self._normalizar_automacoes())
        agenda = _tupla("ConfiguracaoDemandGenV25", "agenda", self.agenda)
        object.__setattr__(self, "agenda", agenda)
        self._checar_agenda()

    def _normalizar_automacoes(self) -> tuple[tuple[str, str], ...]:
        bruto = self.automacoes
        pares = list(bruto.items()) if isinstance(bruto, Mapping) else list(bruto)
        aplicaveis = AUTOMACOES_POR_FORMATO[self.formato]
        vistos: dict[str, str] = {}
        for par in pares:
            tipo, status = par
            if tipo not in aplicaveis:
                raise ValueError(
                    f"automação {tipo!r} não se aplica ao formato "
                    f"{self.formato} (aplicáveis: {', '.join(aplicaveis) or 'nenhuma'}); "
                    "a API devolve ENUM_VALUE_NOT_PERMITTED")
            if status not in STATUS_DE_AUTOMACAO:
                raise ValueError(f"status {status!r} inválido; use OPTED_IN ou "
                                 "OPTED_OUT")
            if tipo in vistos:
                raise ValueError(f"automação {tipo!r} declarada duas vezes")
            vistos[tipo] = status
        return tuple(sorted(vistos.items()))

    def _checar_agenda(self) -> None:
        if any(not isinstance(f, FaixaDeAgendaDemandGen) for f in self.agenda):
            raise TypeError("agenda precisa de FaixaDeAgendaDemandGen")
        por_dia: dict[str, list[tuple[int, int]]] = {}
        for faixa in self.agenda:
            por_dia.setdefault(faixa.dia, []).append(faixa.minutos())
        for dia, faixas in por_dia.items():
            if len(faixas) > FAIXAS_DE_AGENDA_POR_DIA_MAX:
                raise ValueError(
                    f"{dia}: {len(faixas)} faixas; a API aceita até "
                    f"{FAIXAS_DE_AGENDA_POR_DIA_MAX} por dia")
            faixas.sort()
            for (a1, b1), (a2, _b2) in zip(faixas, faixas[1:]):
                if a2 < b1:
                    raise ValueError(f"{dia}: faixas de agenda sobrepostas")

    def status_da_automacao(self, tipo: str) -> str:
        """OPTED_IN só por escolha explícita; o resto é OPTED_OUT."""
        return dict(self.automacoes).get(tipo, "OPTED_OUT")


def estender(cfg: ConfiguracaoDemandGen | None, **novos) -> ConfiguracaoDemandGenV25 | None:
    """Promove uma `ConfiguracaoDemandGen` à forma V25 sem inventar decisão."""
    if cfg is None:
        return None
    base = {f.name: getattr(cfg, f.name) for f in fields(ConfiguracaoDemandGen)}
    if isinstance(cfg, ConfiguracaoDemandGenV25):
        base.update({f.name: getattr(cfg, f.name)
                     for f in fields(ConfiguracaoDemandGenV25)})
    base.update(novos)
    return ConfiguracaoDemandGenV25(**base)


def mesmo_host(url_a: str, url_b: str) -> bool:
    return urlsplit(url_a).hostname == urlsplit(url_b).hostname


# ═══════════════════════════════════════════════════════════════════════════
# FRONTEIRA JSON — só a parte V25; a base vem do objeto `demand_gen` da rota
# ═══════════════════════════════════════════════════════════════════════════
#
# A rota HTTP já transporta `ConfiguracaoDemandGen` (upgraded targeting,
# channel controls, audiências) no objeto `demand_gen`. O JSON
# `configuracao_demand_gen` carrega SÓ os campos que `ConfiguracaoDemandGenV25`
# acrescenta — duas fontes para o mesmo campo seriam precedência silenciosa.

_HORARIO = r"^([01]\d|2[0-4]):(00|15|30|45)$"

#: Todas as automações de criativo de Demand Gen, na ordem dos formatos.
_TODAS_AS_AUTOMACOES: tuple[str, ...] = tuple(
    dict.fromkeys(t for f in FORMATOS for t in AUTOMACOES_POR_FORMATO[f]))

ESQUEMA_JSON: dict[str, dict] = {
    "ConfiguracaoDemandGenV25.formato": {"enum": list(FORMATOS)},
    "ConfiguracaoDemandGenV25.call_to_action": {
        "enum": list(TEXTOS_DE_CTA_ACEITOS),
        "description": "multi-asset e carrossel; no vídeo o CTA é `video.call_to_action`"},
    "ConfiguracaoDemandGenV25.segmentacao_otimizada": {
        "description": "optimized targeting do ad group; null = não emitido"},
    "ConfiguracaoDemandGenV25.automacoes": {"$substituir": {
        "type": "object",
        "propertyNames": {"enum": list(_TODAS_AS_AUTOMACOES)},
        "additionalProperties": {"enum": list(STATUS_DE_AUTOMACAO)},
        "default": {},
        "description": (
            "tipo → OPTED_IN/OPTED_OUT; tipo ausente viaja OPTED_OUT. Só os "
            "tipos do formato escolhido: " + "; ".join(
                f"{f}: {', '.join(AUTOMACOES_POR_FORMATO[f]) or 'nenhuma'}"
                for f in FORMATOS)),
    }},
    "ConfiguracaoDemandGenV25.agenda": {
        "description": f"até {FAIXAS_DE_AGENDA_POR_DIA_MAX} faixas por dia, sem sobreposição"},
    "LanceDemandGen.estrategia": {"enum": list(ESTRATEGIAS)},
    "LanceDemandGen.target_cpa": {"exclusiveMinimum": 0,
                                  "description": "só em MAXIMIZE_CONVERSIONS (vira `target_cpa` avulso)"},
    "LanceDemandGen.target_roas": {"minimum": ROAS_MIN, "maximum": ROAS_MAX,
                                   "description": "razão (4.0 = 400%); só em MAXIMIZE_CONVERSION_VALUE (vira `target_roas` avulso)"},
    "LanceDemandGen.target_cpc": {"exclusiveMinimum": 0,
                                  "description": "obrigatório em TARGET_CPC"},
    "VideoDemandGen.youtube_ids": {"minItems": VIDEOS_MIN, "maxItems": VIDEOS_MAX,
                                   "items": {"pattern": _ID_YOUTUBE.pattern}},
    "VideoDemandGen.call_to_action": {"enum": list(CTAS_DE_VIDEO)},
    "VideoDemandGen.breadcrumb1": {"minLength": 1, "maxLength": BREADCRUMB_MAX_CHARS},
    "VideoDemandGen.breadcrumb2": {"minLength": 1, "maxLength": BREADCRUMB_MAX_CHARS,
                                   "description": "exige breadcrumb1"},
    "CarrosselDemandGen.cartoes": {"minItems": CARTOES_MIN, "maxItems": CARTOES_MAX},
    "CartaoCarrosselDemandGen.headline": {
        "minLength": 1, "maxLength": LIMITES_DE_TEXTO["headline_cartao"]["max_chars"]},
    "CartaoCarrosselDemandGen.url_final": {"pattern": r"^https://"},
    "CartaoCarrosselDemandGen.call_to_action": {"enum": list(TEXTOS_DE_CTA_ACEITOS)},
    "LookalikeDemandGen.nome": {"minLength": 1},
    "LookalikeDemandGen.sementes": {"minItems": 1, "items": {"minimum": 1}},
    "LookalikeDemandGen.expansao": {"enum": list(NIVEIS_DE_LOOKALIKE)},
    "LookalikeDemandGen.paises": {"minItems": 1, "items": {"pattern": _PAIS.pattern}},
    "PublicoDemandGen.nome": {"minLength": 1},
    "PublicoDemandGen.user_lists": {"maxItems": USER_LISTS_MAX,
                                    "items": {"pattern": _USER_LIST.pattern}},
    "PublicoDemandGen.exclusoes_user_list": {"maxItems": USER_LISTS_MAX,
                                             "items": {"pattern": _USER_LIST.pattern}},
    "PublicoDemandGen.lookalikes": {"maxItems": LOOKALIKES_MAX},
    "PublicoDemandGen.idades": {"items": {"enum": list(FAIXAS_ETARIAS)}},
    "PublicoDemandGen.generos": {"items": {"enum": list(GENEROS)}},
    "PublicoDemandGen.rendas": {"items": {"enum": list(FAIXAS_DE_RENDA)}},
    "PublicoDemandGen.status_parentais": {"items": {"enum": list(STATUS_PARENTAIS)}},
    "FaixaDeAgendaDemandGen.dia": {"enum": list(DIAS_DA_SEMANA)},
    "FaixaDeAgendaDemandGen.inicio": {"pattern": _HORARIO},
    "FaixaDeAgendaDemandGen.fim": {"pattern": _HORARIO},
}

#: A imagem do CARTÃO de carrossel precisa ser asset JÁ NA CONTA com recibo
#: (`AssetRemotoAprovado`) — o cartão não resolve id temporário (medido). Esse
#: recibo só nasce na ponte criativa, e a fronteira HTTP ainda não transporta
#: asset remoto aprovado. Recusar com o motivo é melhor que um 500 no proto.
_IMAGEM_DE_CARTAO_INDISPONIVEL = (
    "imagem de cartão de carrossel precisa ser asset JÁ NA CONTA com recibo de "
    "aprovação (o cartão não resolve id temporário — medido em validate_only). "
    "A fronteira HTTP ainda não transporta asset remoto aprovado; o carrossel "
    "fica disponível só para chamadores do motor")


def _recusar_imagem_de_cartao(_valor, caminho: str):
    from .config_json import ConfiguracaoInvalida

    raise ConfiguracaoInvalida(caminho, _IMAGEM_DE_CARTAO_INDISPONIVEL)


#: Os tipos que o JSON não representa, e o que a fronteira faz com eles.
RESOLVEDORES_JSON = {
    ImagemParaSubir: _recusar_imagem_de_cartao,
    AssetRemotoAprovado: _recusar_imagem_de_cartao,
}

_ESQUEMA_INDISPONIVEL = {
    "not": {},
    "description": _IMAGEM_DE_CARTAO_INDISPONIVEL,
    "x-volc-indisponivel-por-http": True,
}


def campos_v25() -> tuple[str, ...]:
    from . import config_json

    return config_json.campos_proprios(ConfiguracaoDemandGenV25, ConfiguracaoDemandGen)


def de_json(dados: dict, base: ConfiguracaoDemandGen,
            caminho: str = "configuracao_demand_gen") -> ConfiguracaoDemandGenV25:
    """JSON da parte V25 + a base já montada → `ConfiguracaoDemandGenV25`."""
    from dataclasses import fields as _f

    from . import config_json

    fixos = {f.name: getattr(base, f.name) for f in _f(ConfiguracaoDemandGen)}
    return config_json.de_dict(
        ConfiguracaoDemandGenV25, dados, caminho, apenas=campos_v25(),
        fixos=fixos, resolvedores=RESOLVEDORES_JSON)


def esquema_json() -> dict:
    from . import config_json

    return config_json.esquema(
        ConfiguracaoDemandGenV25, apenas=campos_v25(), metadados=ESQUEMA_JSON,
        sobrescritas={ImagemParaSubir: _ESQUEMA_INDISPONIVEL,
                      AssetRemotoAprovado: _ESQUEMA_INDISPONIVEL},
        titulo="ConfiguracaoDemandGenV25")
