"""`ConfiguracaoDisplay` — o que Display decide além do brief multicanal.

Stdlib pura DE PROPÓSITO: a rota HTTP e o contrato de canais precisam montar e
validar esta configuração sem importar `google.ads.googleads` no boot. Quem
traduz em protobuf é `display_ops.py`; quem orquestra é `display.py`.

## A regra de compatibilidade

`display.construir(..., configuracao=None)` monta EXATAMENTE o grafo de antes
(budget → campanha → geo → idioma → ad group → RDA). Passar uma
`ConfiguracaoDisplay()` vazia já muda o nascimento: as exclusões de
`ExclusoesDisplay` têm default LIGADO, porque em Display (42% do gasto, compra
de clique barato monetizado por GAM) inventário aberto sem exclusão é o
desperdício nº 1. Ou seja: `None` é compatibilidade; a instância é a doutrina.

## O que foi MEDIDO, e onde

Cada lista fechada abaixo foi provada por `validate_only` na Crédito Up
(547-809-6539, MCC 490-407-4301) em 08/10/2026, lib google-ads 33.0.0 (v25).
O que a API recusou está declarado com o erro que ela devolveu — recusa local
antecipa a remota, com a mesma causa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from typing import Any, Iterable

# ── códigos de plano (espelhados como string para não importar `plano`) ─────
_LANCE = "LANCE_NAO_PERMITIDO"
_RN = "RESOURCE_NAME_INVALIDO"
_AUSENTE = "CONFIGURACAO_AUSENTE"
_TETO = "ASSET_ACIMA_DO_TETO"

# ═══════════════════════════════════════════════════════════════════════════
# LANCE
# ═══════════════════════════════════════════════════════════════════════════

#: Estratégias que o construtor de Display EMITE. Nomes do
#: `BiddingStrategyTypeEnum` da v25 — um nome só por estratégia, sem apelido.
#:
#:   MAXIMIZE_CONVERSIONS       sem meta: `maximize_conversions` vazio
#:                              com `brief.tcpa`: `target_cpa` (ver ⚠️ abaixo)
#:   MAXIMIZE_CONVERSION_VALUE  `maximize_conversion_value` (+ `target_roas`)
#:   TARGET_SPEND               "Maximizar cliques" (+ teto de CPC opcional)
#:   MANUAL_CPC                 CPC manual, eCPC desligado; lance = cpc_inicial
#:   MANUAL_CPM                 em Display é o vCPM (CPM visível); lance no grupo
#:
#: ⚠️ `maximize_conversions.target_cpa_micros` em campanha DISPLAY é RECUSADO:
#: `context_error.OPERATION_NOT_PERMITTED_FOR_CONTEXT @campaign_operation.
#: create.maximize_conversions.target_cpa_micros` (validate_only 08/10/2026).
#: Era exatamente o que `comum.op_campanha()` emitia para Display com tCPA — o
#: canal nunca subiu com meta. A forma aceita é `target_cpa` na campanha.
#:
#: Fora, com o erro medido: TARGET_CPM e TARGET_CPC
#: (`OPERATION_NOT_PERMITTED_FOR_CONTEXT`). `TARGET_CPA`/`TARGET_ROAS` avulsos
#: são aceitos, mas não são nomes de entrada: eles são a FORMA que
#: MAXIMIZE_CONVERSIONS+meta assume no payload.
ESTRATEGIAS: tuple[str, ...] = (
    "MAXIMIZE_CONVERSIONS",
    "MAXIMIZE_CONVERSION_VALUE",
    "TARGET_SPEND",
    "MANUAL_CPC",
    "MANUAL_CPM",
)

#: O que Display monta a partir de `Brief.estrategia_lance` SEM `LanceDisplay`.
#: Desde 08/10/2026 o brief conhece TARGET_SPEND pelo nome da API, e ela entra
#: aqui porque não tem parâmetro obrigatório (o teto de CPC é opcional e mora
#: em `LanceDisplay`). MANUAL_CPC fica de fora porque é o DEFAULT do brief —
#: vindo dali, é indistinguível de "ninguém escolheu" — e MANUAL_CPM porque
#: exige o lance vCPM, que só `LanceDisplay.cpm_visivel` carrega.
ESTRATEGIAS_PELO_BRIEF: tuple[str, ...] = (
    "MAXIMIZE_CONVERSIONS",
    "MAXIMIZE_CONVERSION_VALUE",
    "TARGET_SPEND",
)

_RECUSADAS_PELA_API = {
    "TARGET_CPM": "context_error.OPERATION_NOT_PERMITTED_FOR_CONTEXT em "
                  "campaign.target_cpm (validate_only 08/10/2026). O CPM de "
                  "Display é MANUAL_CPM (vCPM)",
    "TARGET_CPC": "context_error.OPERATION_NOT_PERMITTED_FOR_CONTEXT em "
                  "campaign.target_cpc (validate_only 08/10/2026)",
    "MAXIMIZE_CLICKS": "o nome da API é TARGET_SPEND — use-o",
    "TARGET_CPA": "declare MAXIMIZE_CONVERSIONS com `brief.tcpa`; o payload "
                  "vira `target_cpa` sozinho",
    "TARGET_ROAS": "declare MAXIMIZE_CONVERSION_VALUE com `brief.target_roas`",
}


@dataclass(frozen=True)
class LanceDisplay:
    """A estratégia de Display, quando ela não cabe em `brief.estrategia_lance`.

    As METAS continuam no brief (`tcpa`, `target_roas`, `cpc_inicial`) — uma
    segunda cópia aqui criaria precedência silenciosa. Este objeto só carrega
    o que o brief não tem.
    """

    estrategia: str
    #: TARGET_SPEND: `cpc_bid_ceiling_micros`, em moeda da conta. `None` = sem teto.
    teto_cpc: float | None = None
    #: MANUAL_CPM: `ad_group.cpm_bid_micros` (vCPM), em moeda da conta. Obrigatório ali.
    cpm_visivel: float | None = None


@dataclass(frozen=True)
class LanceResolvido:
    """O lance que vai ao payload, já em micros. `None` é ausência, nunca 0."""

    estrategia: str
    forma_na_api: str               # o ramo do oneof `campaign_bidding_strategy`
    tcpa_micros: int | None = None
    target_roas: float | None = None
    teto_cpc_micros: int | None = None
    cpm_micros: int | None = None
    cpc_micros: int | None = None


def _micros(valor: float) -> int:
    return int(round(float(valor) * 1_000_000))


def resolver_lance(brief: Any, cfg: "ConfiguracaoDisplay | None", r: Any) -> LanceResolvido | None:
    """Uma estratégia, uma fonte, metas coerentes com ela. `None` se reprovado."""
    declarado = cfg.lance if cfg is not None else None
    do_brief = str(getattr(brief, "estrategia_lance", "") or "").strip().upper()

    if declarado is None:
        estrategia = do_brief
        if estrategia not in ESTRATEGIAS_PELO_BRIEF:
            r.erro("estrategia_lance", estrategia,
                   f"Display não aceita {estrategia} vindo do brief. "
                   + ("MANUAL_CPC é o DEFAULT do brief, então ali ele não "
                      "distingue escolha de omissão — declare "
                      "`ConfiguracaoDisplay.lance=LanceDisplay('MANUAL_CPC')` "
                      "para CPC manual de propósito, ou "
                      "estrategia_lance='MAXIMIZE_CONVERSIONS' no brief "
                      "(com `tcpa` vira tCPA). " if estrategia == "MANUAL_CPC" else "")
                   + f"Pelo brief: {', '.join(ESTRATEGIAS_PELO_BRIEF)}; pela "
                   f"configuração: {', '.join(ESTRATEGIAS)}", _LANCE)
            return None
    else:
        estrategia = str(declarado.estrategia or "").strip().upper()
        if estrategia not in ESTRATEGIAS:
            causa = _RECUSADAS_PELA_API.get(estrategia, "não é estratégia de Display")
            r.erro("estrategia_lance", estrategia,
                   f"{estrategia}: {causa}. Aceitas: {', '.join(ESTRATEGIAS)}", _LANCE)
            return None
        # Duas fontes só convivem se disserem o mesmo — ou se o brief estiver
        # no default (MANUAL_CPC), que não é escolha de ninguém.
        if do_brief not in ("MANUAL_CPC", estrategia):
            r.erro("estrategia_lance", f"{do_brief} × {estrategia}",
                   "o brief declara uma estratégia e `ConfiguracaoDisplay.lance` "
                   "outra. Duas fontes com precedência silenciosa é o defeito "
                   "que este contrato existe para não ter — alinhe as duas", _LANCE)
            return None

    tcpa = getattr(brief, "tcpa", None)
    troas = getattr(brief, "target_roas", None)
    ok = True
    if tcpa is not None and estrategia != "MAXIMIZE_CONVERSIONS":
        r.erro("tcpa", str(tcpa),
               f"tCPA só existe em MAXIMIZE_CONVERSIONS; sob {estrategia} ele "
               f"seria descartado em silêncio. Zere `brief.tcpa` (None)", _LANCE)
        ok = False
    if troas is not None and estrategia != "MAXIMIZE_CONVERSION_VALUE":
        r.erro("target_roas", str(troas),
               f"tROAS só existe em MAXIMIZE_CONVERSION_VALUE; sob {estrategia} "
               f"ele seria descartado em silêncio", _LANCE)
        ok = False
    if tcpa is not None and tcpa <= 0:
        r.erro("tcpa", str(tcpa), "meta ausente é None; zero ou negativo não é meta", _LANCE)
        ok = False
    if troas is not None and troas <= 0:
        r.erro("target_roas", str(troas),
               "tROAS é razão (4.0 = 400%); ausente é None, nunca 0", _LANCE)
        ok = False

    teto = declarado.teto_cpc if declarado else None
    cpm = declarado.cpm_visivel if declarado else None
    if teto is not None and (estrategia != "TARGET_SPEND" or teto <= 0):
        r.erro("lance.teto_cpc", str(teto),
               "teto de CPC só em TARGET_SPEND e precisa ser positivo", _LANCE)
        ok = False
    if estrategia == "MANUAL_CPM" and (cpm is None or cpm <= 0):
        r.erro("lance.cpm_visivel", str(cpm),
               "MANUAL_CPM (vCPM) exige o lance por mil impressões visíveis no "
               "grupo — sem ele o grupo nasce sem lance", _AUSENTE)
        ok = False
    if cpm is not None and estrategia != "MANUAL_CPM":
        r.erro("lance.cpm_visivel", str(cpm),
               f"CPM visível só em MANUAL_CPM; sob {estrategia} seria decoração", _LANCE)
        ok = False
    cpc = getattr(brief, "cpc_inicial", None)
    if estrategia == "MANUAL_CPC" and not (cpc and cpc > 0):
        r.erro("cpc_inicial", str(cpc), "MANUAL_CPC usa `brief.cpc_inicial` como "
               "lance do grupo e ele precisa ser positivo", _LANCE)
        ok = False
    if not ok:
        return None

    forma = {
        "MAXIMIZE_CONVERSIONS": "target_cpa" if tcpa else "maximize_conversions",
        "MAXIMIZE_CONVERSION_VALUE": "maximize_conversion_value",
        "TARGET_SPEND": "target_spend",
        "MANUAL_CPC": "manual_cpc",
        "MANUAL_CPM": "manual_cpm",
    }[estrategia]
    return LanceResolvido(
        estrategia=estrategia,
        forma_na_api=forma,
        tcpa_micros=_micros(tcpa) if tcpa else None,
        target_roas=float(troas) if troas else None,
        teto_cpc_micros=_micros(teto) if teto else None,
        cpm_micros=_micros(cpm) if cpm else None,
        cpc_micros=_micros(cpc) if estrategia == "MANUAL_CPC" else None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# SEGMENTAÇÃO — positivos do ad group
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SegmentacaoDisplay:
    """Critérios POSITIVOS do ad group. Vazio = inventário aberto (e avisado).

    Cada item aceita o id numérico ("369") ou o resource name completo. Todos
    os tipos foram aceitos por `validate_only` em 08/10/2026; custom e combined
    audience foram aceitos na FORMA (a API respondeu "não encontrado"/"id
    inválido" para um id inventado, não "campo não permitido") — a Crédito Up
    não tem nenhum dos dois para prova positiva.
    """

    #: `customers/<cid>/userLists/<id>` — remarketing (AdGroupCriterion.user_list).
    listas_de_usuarios: tuple[str, ...] = ()
    #: `customers/<cid>/customAudiences/<id>` (AdGroupCriterion.custom_audience).
    publicos_personalizados: tuple[str, ...] = ()
    #: `customers/<cid>/combinedAudiences/<id>` (AdGroupCriterion.combined_audience).
    publicos_combinados: tuple[str, ...] = ()
    #: Afinidade e in-market: `customers/<cid>/userInterests/<id>`
    #: (AdGroupCriterion.user_interest). Ex.: 92000 "Avid News Readers"
    #: (AFFINITY), 80226 "Education" (IN_MARKET).
    interesses: tuple[str, ...] = ()
    #: `topicConstants/<id>` (TopicInfo). Ex.: 369 "Vocational & Continuing Education".
    topicos: tuple[str, ...] = ()
    #: Site onde o anúncio PODE aparecer (PlacementInfo.url, positivo). A
    #: contradição das duas fontes oficiais foi resolvida pela API: aceito.
    placements: tuple[str, ...] = ()
    #: Palavras-chave de CONTEÚDO (KeywordInfo, BROAD — Display não casa termo
    #: de busca; o match type não tem efeito de consulta aqui).
    palavras_chave: tuple[str, ...] = ()
    #: `True` = públicos em OBSERVAÇÃO (bid_only, não restringem); `False` =
    #: SEGMENTAÇÃO (restringem). `ad_group.targeting_setting` AUDIENCE.
    publicos_em_observacao: bool = False
    #: `ad_group.optimized_targeting_enabled`. ⚠️ Default DESLIGADO e escrito
    #: sempre: ligado, o Google expande para além dos critérios acima, que é o
    #: oposto do controle de inventário que a arbitragem precisa.
    segmentacao_otimizada: bool = False

    def __post_init__(self) -> None:
        _tuplas(self)

    @property
    def tem_positivo(self) -> bool:
        return any((self.listas_de_usuarios, self.publicos_personalizados,
                    self.publicos_combinados, self.interesses, self.topicos,
                    self.placements, self.palavras_chave))

    @property
    def tem_publico(self) -> bool:
        return any((self.listas_de_usuarios, self.publicos_personalizados,
                    self.publicos_combinados, self.interesses))


# ═══════════════════════════════════════════════════════════════════════════
# EXCLUSÕES — o padrão de nascimento
# ═══════════════════════════════════════════════════════════════════════════

#: Rótulos de conteúdo que a API ACEITA excluir em campanha Display (medido).
ROTULOS_ACEITOS: tuple[str, ...] = (
    "SEXUALLY_SUGGESTIVE", "BELOW_THE_FOLD", "PARKED_DOMAIN", "JUVENILE",
    "PROFANITY", "TRAGEDY", "VIDEO", "VIDEO_RATING_DV_G", "VIDEO_RATING_DV_PG",
    "VIDEO_RATING_DV_T", "VIDEO_RATING_DV_MA", "VIDEO_NOT_YET_RATED",
    "EMBEDDED_VIDEO", "LIVE_STREAMING_VIDEO", "SOCIAL_ISSUES",
    "BRAND_SUITABILITY_CONTENT_FOR_FAMILIES",
)

#: Os demais BRAND_SUITABILITY_* existem no enum e a API recusa em Display:
#: `criterion_error.CANNOT_EXCLUDE_CRITERION` (validate_only 08/10/2026).
ROTULOS_RECUSADOS: tuple[str, ...] = (
    "BRAND_SUITABILITY_GAMES_FIGHTING", "BRAND_SUITABILITY_GAMES_MATURE",
    "BRAND_SUITABILITY_HEALTH_SENSITIVE",
    "BRAND_SUITABILITY_HEALTH_SOURCE_UNDETERMINED",
    "BRAND_SUITABILITY_NEWS_RECENT", "BRAND_SUITABILITY_NEWS_SENSITIVE",
    "BRAND_SUITABILITY_NEWS_SOURCE_NOT_FEATURED", "BRAND_SUITABILITY_POLITICS",
    "BRAND_SUITABILITY_RELIGION",
)

#: Brand safety de nascimento. Critério: conteúdo onde o clique comprado não
#: vira sessão monetizável (domínio estacionado), ou onde anúncio de portal de
#: utilidade pública vira risco de marca/política (sexual, palavrão, tragédia,
#: questão social, juvenil). BELOW_THE_FOLD e os de vídeo ficam de fora do
#: default porque cortam alcance de forma que só o operador pode julgar.
ROTULOS_PADRAO: tuple[str, ...] = (
    "PARKED_DOMAIN", "SEXUALLY_SUGGESTIVE", "PROFANITY", "TRAGEDY",
    "SOCIAL_ISSUES", "JUVENILE",
)

#: `mobileAppCategoryConstants/69500` — "All Apps" (lido de
#: `mobile_app_category_constant` na conta, 08/10/2026). Excluir esta categoria
#: tira o anúncio de TODO inventário in-app.
CATEGORIA_TODOS_OS_APPS = "mobileAppCategoryConstants/69500"


@dataclass(frozen=True)
class ListaDeExclusaoNova:
    """`SharedSet` NEGATIVE_PLACEMENTS criado no MESMO mutate e ligado à campanha."""

    nome: str
    placements: tuple[str, ...] = ()
    apps: tuple[str, ...] = ()
    categorias_de_app: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _tuplas(self)


@dataclass(frozen=True)
class ExclusoesDisplay:
    """Exclusões de campanha. Os defaults SÃO o padrão de nascimento."""

    #: Sites (CampaignCriterion.placement, negative=True).
    placements: tuple[str, ...] = ()
    #: Apps: "1-<id App Store>" ou "2-<pacote Android>" (mobile_application).
    apps: tuple[str, ...] = ()
    #: `mobileAppCategoryConstants/<id>` (mobile_app_category, negativo).
    categorias_de_app: tuple[str, ...] = ()
    #: ⚠️ Default LIGADO: clique em app é acidental demais e a sessão não cai
    #: no portal monetizado. Exclui `CATEGORIA_TODOS_OS_APPS`.
    excluir_todos_os_apps: bool = True
    #: `content_label` negativos. Default = `ROTULOS_PADRAO`.
    rotulos_de_conteudo: tuple[str, ...] = ROTULOS_PADRAO
    #: Tópicos negativos (`topicConstants/<id>`).
    topicos: tuple[str, ...] = ()
    #: Listas NEGATIVE_PLACEMENTS já existentes: `customers/<cid>/sharedSets/<id>`.
    listas_existentes: tuple[str, ...] = ()
    #: Lista nova, criada no mesmo mutate atômico.
    lista_nova: ListaDeExclusaoNova | None = None

    def __post_init__(self) -> None:
        _tuplas(self)


# ═══════════════════════════════════════════════════════════════════════════
# CAMPANHA — frequência, agenda, dispositivo, geo
# ═══════════════════════════════════════════════════════════════════════════

NIVEIS_DE_FREQUENCIA = ("AD_GROUP_AD", "AD_GROUP", "CAMPAIGN")
UNIDADES_DE_FREQUENCIA = ("DAY", "WEEK", "MONTH")
DIAS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
MINUTOS = {0: "ZERO", 15: "FIFTEEN", 30: "THIRTY", 45: "FORTY_FIVE"}
#: Excluíveis por bid modifier 0 (-100%). TABLET medido; os três são o mesmo
#: `DeviceInfo.type`.
DISPOSITIVOS = ("MOBILE", "TABLET", "DESKTOP")
#: SEARCH_INTEREST é de Search; em Display só presença ou presença+interesse.
PRESENCAS_GEO = ("PRESENCE", "PRESENCE_OR_INTEREST")
FORMATOS = ("ALL_FORMATS", "NATIVE", "NON_NATIVE")
#: `ResponsiveDisplayAdInfo.youtube_videos`: "A maximum of 5 videos".
VIDEOS_MAX = 5


@dataclass(frozen=True)
class FrequenciaMaxima:
    """`campaign.frequency_caps[]` — evento IMPRESSION, `time_length` 1."""

    impressoes: int
    unidade: str = "DAY"
    nivel: str = "AD_GROUP_AD"


@dataclass(frozen=True)
class JanelaDeVeiculacao:
    """`CampaignCriterion.ad_schedule`. Fim exclusivo; 24:00 é o fim do dia."""

    dia: str
    inicio_hora: int
    fim_hora: int
    inicio_minuto: int = 0
    fim_minuto: int = 0


@dataclass(frozen=True)
class AnuncioDisplay:
    """Campos do RDA além de texto e imagem."""

    #: `call_to_action_text`, largura máxima 30.
    chamada_para_acao: str | None = None
    #: `main_color`/`accent_color` "#RRGGBB" — os dois ou nenhum (field_error.REQUIRED medido).
    cor_principal: str | None = None
    cor_destaque: str | None = None
    #: `allow_flexible_color`. Precisa ser True quando não há cores.
    cores_flexiveis: bool = True
    #: `format_setting`: ALL_FORMATS | NATIVE | NON_NATIVE.
    formato: str = "ALL_FORMATS"
    #: IDs do YouTube (11 chars). Viram `YoutubeVideoAsset` no MESMO mutate.
    videos_youtube: tuple[str, ...] = ()
    #: `control_spec.enable_asset_enhancements` — default DESLIGADO (peça aprovada = peça servida).
    melhorias_de_asset: bool = False
    #: `control_spec.enable_autogen_video` — default DESLIGADO.
    video_automatico: bool = False

    def __post_init__(self) -> None:
        _tuplas(self)


@dataclass(frozen=True)
class ConfiguracaoDisplay:
    """Tudo o que Display decide além do brief. Ver docstring do módulo."""

    lance: LanceDisplay | None = None
    segmentacao: SegmentacaoDisplay = field(default_factory=SegmentacaoDisplay)
    exclusoes: ExclusoesDisplay = field(default_factory=ExclusoesDisplay)
    frequencia: tuple[FrequenciaMaxima, ...] = ()
    agenda: tuple[JanelaDeVeiculacao, ...] = ()
    dispositivos_excluidos: tuple[str, ...] = ()
    #: `geo_target_type_setting.positive_geo_target_type`. ⚠️ Default PRESENCE:
    #: o RPM do GAM é por país, e "interesse no local" compra clique de fora.
    #: O negativo é sempre PRESENCE.
    presenca_geo: str = "PRESENCE"
    anuncio: AnuncioDisplay = field(default_factory=AnuncioDisplay)

    def __post_init__(self) -> None:
        _tuplas(self)

    @classmethod
    def de_dict(cls, d: dict | None, caminho: str = "configuracao") -> "ConfiguracaoDisplay":
        """JSON da rota → configuração. Chave desconhecida é ERRO, não descarte.

        ⚠️ Delegado a `config_json.de_dict` desde 08/10/2026. A versão local
        montava os aninhados por uma tabela à mão (`_ANINHADOS`) e não julgava
        tipo nenhum: `"impressoes": "3"` atravessava como texto e só quebrava
        no proto. Agora a forma é lida das anotações deste módulo — a mesma
        régua dos outros três canais —, e o erro carrega o caminho do campo.
        """
        from . import config_json

        return config_json.de_dict(cls, d or {}, caminho)

    def para_json(self) -> dict:
        from . import config_json

        return config_json.para_json(self)


# ═══════════════════════════════════════════════════════════════════════════
# RESOLUÇÃO + VALIDAÇÃO LOCAL
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ConfiguracaoResolvida:
    """A configuração já em resource names/enums, pronta para virar proto."""

    lance: LanceResolvido
    listas_de_usuarios: tuple[str, ...] = ()
    publicos_personalizados: tuple[str, ...] = ()
    publicos_combinados: tuple[str, ...] = ()
    interesses: tuple[str, ...] = ()
    topicos: tuple[str, ...] = ()
    placements: tuple[str, ...] = ()
    palavras_chave: tuple[str, ...] = ()
    publicos_em_observacao: bool = False
    segmentacao_otimizada: bool = False
    neg_placements: tuple[str, ...] = ()
    neg_apps: tuple[str, ...] = ()
    neg_categorias_de_app: tuple[str, ...] = ()
    neg_rotulos: tuple[str, ...] = ()
    neg_topicos: tuple[str, ...] = ()
    listas_existentes: tuple[str, ...] = ()
    lista_nova: ListaDeExclusaoNova | None = None
    frequencia: tuple[FrequenciaMaxima, ...] = ()
    agenda: tuple[JanelaDeVeiculacao, ...] = ()
    dispositivos_excluidos: tuple[str, ...] = ()
    presenca_geo: str | None = None
    anuncio: AnuncioDisplay | None = None
    #: `False` quando a configuração não veio: o construtor mantém o grafo antigo.
    declarada: bool = False


_MODELOS = {
    "user_list": ("customers/{cid}/userLists/{id}", r"^customers/(\d+)/userLists/(-?\d+)$"),
    "custom_audience": ("customers/{cid}/customAudiences/{id}", r"^customers/(\d+)/customAudiences/(-?\d+)$"),
    "combined_audience": ("customers/{cid}/combinedAudiences/{id}", r"^customers/(\d+)/combinedAudiences/(-?\d+)$"),
    "user_interest": ("customers/{cid}/userInterests/{id}", r"^customers/(\d+)/userInterests/(-?\d+)$"),
    "topic": ("topicConstants/{id}", r"^topicConstants/(-?\d+)$"),
    "app_category": ("mobileAppCategoryConstants/{id}", r"^mobileAppCategoryConstants/(-?\d+)$"),
    "shared_set": ("customers/{cid}/sharedSets/{id}", r"^customers/(\d+)/sharedSets/(-?\d+)$"),
}

_DOMINIO = re.compile(r"^(?=.{4,255}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+(?:/\S*)?$")
_APP = re.compile(r"^(?:1-\d+|2-[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)$")
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_COR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _rn(valor: str, tipo: str, cid: str, campo: str, r: Any) -> str | None:
    modelo, padrao = _MODELOS[tipo]
    v = str(valor or "").strip()
    if v.isdigit():
        v = modelo.format(cid=cid, id=v)
    m = re.match(padrao, v)
    if m is None:
        r.erro(campo, valor, f"não é id numérico nem resource name de {tipo} "
               f"(`{modelo.format(cid=cid, id='<id>')}`)", _RN)
        return None
    grupos = m.groups()
    if len(grupos) == 2 and grupos[0] != str(cid):
        r.erro(campo, valor, f"é da conta {grupos[0]} e o mutate é na {cid} — "
               f"critério não atravessa conta", _RN)
        return None
    if int(grupos[-1]) <= 0:
        r.erro(campo, valor, "id temporário (negativo) não referencia recurso "
               "existente; só a lista nova nasce neste mutate", _RN)
        return None
    return v


def _lista_rn(valores: Iterable[str], tipo: str, cid: str, campo: str, r: Any) -> tuple[str, ...]:
    return _sem_duplicata(
        [x for x in (_rn(v, tipo, cid, campo, r) for v in valores) if x], campo, r)


def _placement(valor: str, campo: str, r: Any) -> str | None:
    v = str(valor or "").strip()
    v = re.sub(r"^https?://", "", v, flags=re.I)
    host, barra, resto = v.partition("/")
    v = host.lower().removeprefix("www.") + (barra + resto if barra else "")
    v = v.rstrip("/")
    if not _DOMINIO.match(v):
        r.erro(campo, valor, "placement é um site (`exemplo.com.br` ou "
               "`exemplo.com.br/secao`); app vai em `apps`", _RN)
        return None
    return v


def _sem_duplicata(itens: list[str], campo: str, r: Any) -> tuple[str, ...]:
    vistos: set[str] = set()
    for i in itens:
        chave = i.casefold()
        if chave in vistos:
            r.erro(campo, i, "duplicado: a API recusa o mutate inteiro com "
                   "critério repetido — deixe uma vez só")
        vistos.add(chave)
    return tuple(dict.fromkeys(itens))


def _apps(valores: Iterable[str], campo: str, r: Any) -> tuple[str, ...]:
    saida = []
    for v in valores:
        s = str(v or "").strip()
        if not _APP.match(s):
            r.erro(campo, v, "app é `1-<id numérico da App Store>` ou "
                   "`2-<pacote Android>` (ex.: 2-com.exemplo.jogo)", _RN)
            continue
        saida.append(s)
    return _sem_duplicata(saida, campo, r)


def resolver(cid: str, brief: Any, cfg: ConfiguracaoDisplay | None, r: Any) -> ConfiguracaoResolvida | None:
    """Valida e normaliza. `None` quando o lance não resolveu (o resto vira achado)."""
    lance = resolver_lance(brief, cfg, r)
    if cfg is None:
        return ConfiguracaoResolvida(lance=lance) if lance else None

    s, e, a = cfg.segmentacao, cfg.exclusoes, cfg.anuncio
    seg = dict(
        listas_de_usuarios=_lista_rn(s.listas_de_usuarios, "user_list", cid, "segmentacao.listas_de_usuarios", r),
        publicos_personalizados=_lista_rn(s.publicos_personalizados, "custom_audience", cid, "segmentacao.publicos_personalizados", r),
        publicos_combinados=_lista_rn(s.publicos_combinados, "combined_audience", cid, "segmentacao.publicos_combinados", r),
        interesses=_lista_rn(s.interesses, "user_interest", cid, "segmentacao.interesses", r),
        topicos=_lista_rn(s.topicos, "topic", cid, "segmentacao.topicos", r),
        placements=_sem_duplicata([x for x in (_placement(p, "segmentacao.placements", r) for p in s.placements) if x], "segmentacao.placements", r),
    )
    kws = []
    for k in s.palavras_chave:
        t = " ".join(str(k or "").split())
        if not t or len(t) > 80 or len(t.split()) > 10:
            r.erro("segmentacao.palavras_chave", k, "palavra-chave de conteúdo "
                   "tem de 1 a 80 caracteres e até 10 palavras")
            continue
        kws.append(t.lower())
    seg["palavras_chave"] = _sem_duplicata(kws, "segmentacao.palavras_chave", r)

    neg_placements = _sem_duplicata(
        [x for x in (_placement(p, "exclusoes.placements", r) for p in e.placements) if x],
        "exclusoes.placements", r)
    neg_apps = _apps(e.apps, "exclusoes.apps", r)
    cats = list(_lista_rn(e.categorias_de_app, "app_category", cid, "exclusoes.categorias_de_app", r))
    if e.excluir_todos_os_apps:
        if cats or neg_apps:
            r.aviso("exclusoes.apps", f"{len(cats) + len(neg_apps)}",
                    "`excluir_todos_os_apps` já tira o anúncio de todo app; as "
                    "exclusões individuais de app ficam redundantes (entram mesmo assim)")
        if CATEGORIA_TODOS_OS_APPS not in cats:
            cats.append(CATEGORIA_TODOS_OS_APPS)
    rotulos = []
    for rot in e.rotulos_de_conteudo:
        x = str(rot or "").strip().upper()
        if x in ROTULOS_RECUSADOS:
            r.erro("exclusoes.rotulos_de_conteudo", x,
                   "a API recusa este rótulo em Display com "
                   "criterion_error.CANNOT_EXCLUDE_CRITERION (validate_only 08/10/2026)")
        elif x not in ROTULOS_ACEITOS:
            r.erro("exclusoes.rotulos_de_conteudo", x,
                   f"rótulo desconhecido. Aceitos em Display: {', '.join(ROTULOS_ACEITOS)}")
        else:
            rotulos.append(x)
    neg_topicos = _lista_rn(e.topicos, "topic", cid, "exclusoes.topicos", r)
    listas = _lista_rn(e.listas_existentes, "shared_set", cid, "exclusoes.listas_existentes", r)

    for pos, neg, nome in ((seg["placements"], neg_placements, "placements"),
                           (seg["topicos"], neg_topicos, "topicos")):
        for x in set(pos) & set(neg):
            r.erro(f"exclusoes.{nome}", x, "o mesmo critério está como positivo "
                   "no grupo e negativo na campanha — a exclusão vence e o grupo "
                   "fica sem o inventário que pediu")

    nova = e.lista_nova
    if nova is not None:
        if not str(nova.nome or "").strip():
            r.erro("exclusoes.lista_nova.nome", "", "lista compartilhada sem nome "
                   "é impossível de reencontrar na biblioteca da conta", _AUSENTE)
        np_ = _sem_duplicata([x for x in (_placement(p, "exclusoes.lista_nova.placements", r) for p in nova.placements) if x], "exclusoes.lista_nova.placements", r)
        na = _apps(nova.apps, "exclusoes.lista_nova.apps", r)
        nc = _lista_rn(nova.categorias_de_app, "app_category", cid, "exclusoes.lista_nova.categorias_de_app", r)
        if not (np_ or na or nc):
            r.erro("exclusoes.lista_nova", nova.nome, "lista de exclusão nova sem "
                   "nenhum membro — ou preencha, ou não crie", _AUSENTE)
        nova = ListaDeExclusaoNova(nome=str(nova.nome).strip(), placements=np_, apps=na, categorias_de_app=nc)

    _checar_frequencia(cfg.frequencia, r)
    _checar_agenda(cfg.agenda, r)
    disp = tuple(str(d).strip().upper() for d in cfg.dispositivos_excluidos)
    for d in disp:
        if d not in DISPOSITIVOS:
            r.erro("dispositivos_excluidos", d, f"use {', '.join(DISPOSITIVOS)}")
    if set(DISPOSITIVOS) <= set(disp):
        r.erro("dispositivos_excluidos", ",".join(disp),
               "excluir os três dispositivos é uma campanha que não veicula")
    disp = _sem_duplicata(list(disp), "dispositivos_excluidos", r)
    geo = str(cfg.presenca_geo or "").strip().upper()
    if geo not in PRESENCAS_GEO:
        r.erro("presenca_geo", geo, f"em Display: {', '.join(PRESENCAS_GEO)} "
               "(SEARCH_INTEREST é de Search)")
    _checar_anuncio(a, r)

    if lance is None:
        return None
    return ConfiguracaoResolvida(
        lance=lance, **seg,
        publicos_em_observacao=bool(s.publicos_em_observacao),
        segmentacao_otimizada=bool(s.segmentacao_otimizada),
        neg_placements=neg_placements, neg_apps=neg_apps,
        neg_categorias_de_app=tuple(cats), neg_rotulos=tuple(dict.fromkeys(rotulos)),
        neg_topicos=neg_topicos, listas_existentes=listas, lista_nova=nova,
        frequencia=tuple(cfg.frequencia), agenda=tuple(cfg.agenda),
        dispositivos_excluidos=disp, presenca_geo=geo, anuncio=a, declarada=True,
    )


def _checar_frequencia(caps: tuple[FrequenciaMaxima, ...], r: Any) -> None:
    vistos: set[tuple[str, str]] = set()
    for f in caps:
        nivel, unidade = str(f.nivel).upper(), str(f.unidade).upper()
        if nivel not in NIVEIS_DE_FREQUENCIA or unidade not in UNIDADES_DE_FREQUENCIA:
            r.erro("frequencia", f"{nivel}/{unidade}",
                   f"nível ∈ {NIVEIS_DE_FREQUENCIA}, unidade ∈ {UNIDADES_DE_FREQUENCIA}")
        if not isinstance(f.impressoes, int) or f.impressoes < 1:
            r.erro("frequencia", str(f.impressoes), "teto de impressões é inteiro ≥ 1")
        if (nivel, unidade) in vistos:
            r.erro("frequencia", f"{nivel}/{unidade}", "dois tetos para o mesmo nível e unidade")
        vistos.add((nivel, unidade))


def _checar_agenda(janelas: tuple[JanelaDeVeiculacao, ...], r: Any) -> None:
    por_dia: dict[str, list[tuple[int, int]]] = {}
    for j in janelas:
        dia = str(j.dia).upper()
        ini = j.inicio_hora * 60 + j.inicio_minuto
        fim = j.fim_hora * 60 + j.fim_minuto
        rot = f"{dia} {j.inicio_hora:02d}:{j.inicio_minuto:02d}-{j.fim_hora:02d}:{j.fim_minuto:02d}"
        if (dia not in DIAS or j.inicio_minuto not in MINUTOS or j.fim_minuto not in MINUTOS
                or not 0 <= j.inicio_hora <= 23 or not 0 <= j.fim_hora <= 24
                or (j.fim_hora == 24 and j.fim_minuto) or fim <= ini):
            r.erro("agenda", rot, "dia em inglês (MONDAY…), hora 0–23 no início "
                   "e 0–24 no fim, minuto ∈ 0/15/30/45, fim depois do início")
            continue
        por_dia.setdefault(dia, []).append((ini, fim))
    for dia, faixas in por_dia.items():
        if len(faixas) > 6:
            r.erro("agenda", dia, "no máximo 6 janelas por dia")
        faixas.sort()
        for (a0, a1), (b0, _b1) in zip(faixas, faixas[1:]):
            if b0 < a1:
                r.erro("agenda", dia, "janelas sobrepostas no mesmo dia — a API recusa")


def _checar_anuncio(a: AnuncioDisplay, r: Any) -> None:
    if a.chamada_para_acao is not None:
        t = a.chamada_para_acao.strip()
        if not t or len(t) > 30:
            r.erro("anuncio.chamada_para_acao", a.chamada_para_acao,
                   "call_to_action_text tem largura máxima 30 (proto v25)")
    cores = (a.cor_principal, a.cor_destaque)
    if any(cores) and not all(cores):
        r.erro("anuncio.cores", str(cores), "main_color e accent_color: os dois "
               "ou nenhum (field_error.REQUIRED medido em 08/10/2026)")
    for c in cores:
        if c and not _COR.match(c):
            r.erro("anuncio.cores", c, "cor em hexadecimal #RRGGBB")
    if not any(cores) and not a.cores_flexiveis:
        r.erro("anuncio.cores_flexiveis", "False", "o proto exige "
               "allow_flexible_color=True quando não há cores declaradas")
    if str(a.formato).upper() not in FORMATOS:
        r.erro("anuncio.formato", a.formato, f"use {', '.join(FORMATOS)}")
    for v in a.videos_youtube:
        if not _VIDEO_ID.match(str(v or "").strip()):
            r.erro("videos", v, "id do YouTube tem 11 caracteres "
                   "(o `v=` da URL), não a URL inteira")
    _sem_duplicata([str(v).strip() for v in a.videos_youtube], "videos", r)


# ═══════════════════════════════════════════════════════════════════════════
# utilitários de forma
# ═══════════════════════════════════════════════════════════════════════════


def _tuplas(obj: Any) -> None:
    """Lista vinda de JSON vira tupla — o objeto é frozen e hashável."""
    for f in fields(obj):
        v = getattr(obj, f.name)
        if isinstance(v, list):
            object.__setattr__(obj, f.name, tuple(v))


# ═══════════════════════════════════════════════════════════════════════════
# FRONTEIRA JSON — vocabulário do esquema que a tela lê
# ═══════════════════════════════════════════════════════════════════════════
#
# Cada `enum` referencia a tupla fechada deste módulo (nada copiado), e cada
# limite referencia a régua que `resolver()` aplica. O esquema em si é derivado
# das anotações (`config_json.esquema`).

_RN_OU_ID = r"^(\d+|customers/\d+/{colecao}/\d+)$"

ESQUEMA_JSON: dict[str, dict] = {
    "LanceDisplay.estrategia": {"enum": list(ESTRATEGIAS)},
    "LanceDisplay.teto_cpc": {"exclusiveMinimum": 0},
    "LanceDisplay.cpm_visivel": {"exclusiveMinimum": 0,
                                 "description": "lance vCPM do grupo; obrigatório em MANUAL_CPM"},
    "SegmentacaoDisplay.listas_de_usuarios": {"items": {"pattern": _RN_OU_ID.format(colecao="userLists")}},
    "SegmentacaoDisplay.publicos_personalizados": {"items": {"pattern": _RN_OU_ID.format(colecao="customAudiences")}},
    "SegmentacaoDisplay.publicos_combinados": {"items": {"pattern": _RN_OU_ID.format(colecao="combinedAudiences")}},
    "SegmentacaoDisplay.interesses": {"items": {"pattern": _RN_OU_ID.format(colecao="userInterests")}},
    "SegmentacaoDisplay.topicos": {"items": {"pattern": r"^(\d+|topicConstants/\d+)$"}},
    "SegmentacaoDisplay.palavras_chave": {"items": {"minLength": 1, "maxLength": 80}},
    "ExclusoesDisplay.rotulos_de_conteudo": {"items": {"enum": list(ROTULOS_ACEITOS)}},
    "ExclusoesDisplay.apps": {"items": {"pattern": _APP.pattern}},
    "ExclusoesDisplay.categorias_de_app": {"items": {"pattern": r"^(\d+|mobileAppCategoryConstants/\d+)$"}},
    "ExclusoesDisplay.topicos": {"items": {"pattern": r"^(\d+|topicConstants/\d+)$"}},
    "ExclusoesDisplay.listas_existentes": {"items": {"pattern": _RN_OU_ID.format(colecao="sharedSets")}},
    "ListaDeExclusaoNova.nome": {"minLength": 1},
    "ListaDeExclusaoNova.apps": {"items": {"pattern": _APP.pattern}},
    "FrequenciaMaxima.impressoes": {"minimum": 1},
    "FrequenciaMaxima.unidade": {"enum": list(UNIDADES_DE_FREQUENCIA)},
    "FrequenciaMaxima.nivel": {"enum": list(NIVEIS_DE_FREQUENCIA)},
    "JanelaDeVeiculacao.dia": {"enum": list(DIAS)},
    "JanelaDeVeiculacao.inicio_hora": {"minimum": 0, "maximum": 23},
    "JanelaDeVeiculacao.fim_hora": {"minimum": 0, "maximum": 24},
    "JanelaDeVeiculacao.inicio_minuto": {"enum": sorted(MINUTOS)},
    "JanelaDeVeiculacao.fim_minuto": {"enum": sorted(MINUTOS)},
    "ConfiguracaoDisplay.agenda": {"description": "até 6 janelas por dia, sem sobreposição"},
    "ConfiguracaoDisplay.dispositivos_excluidos": {"items": {"enum": list(DISPOSITIVOS)}},
    "ConfiguracaoDisplay.presenca_geo": {"enum": list(PRESENCAS_GEO)},
    "AnuncioDisplay.chamada_para_acao": {"maxLength": 30},
    "AnuncioDisplay.cor_principal": {"pattern": _COR.pattern},
    "AnuncioDisplay.cor_destaque": {"pattern": _COR.pattern},
    "AnuncioDisplay.formato": {"enum": list(FORMATOS)},
    "AnuncioDisplay.videos_youtube": {"maxItems": VIDEOS_MAX,
                                      "items": {"pattern": _VIDEO_ID.pattern}},
}


def de_json(dados: dict, caminho: str = "configuracao_display") -> ConfiguracaoDisplay:
    """JSON da rota → `ConfiguracaoDisplay` (mesmo caminho de `de_dict`)."""
    return ConfiguracaoDisplay.de_dict(dados, caminho)


def esquema_json() -> dict:
    from . import config_json

    return config_json.esquema(ConfiguracaoDisplay, metadados=ESQUEMA_JSON,
                               titulo="ConfiguracaoDisplay")
