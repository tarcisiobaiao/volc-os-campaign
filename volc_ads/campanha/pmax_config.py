"""Performance Max v25.2 — as decisões novas, tipadas, e a régua de cada uma.

## Por que um módulo à parte, e não campos novos em `brief.py`

`ConfiguracaoPMax` mora em `brief.py`, que este canal não edita. A extensão é
uma SUBCLASSE (`ConfiguracaoPMaxV25`) com todos os campos novos defaultados: um
chamador antigo que entrega `ConfiguracaoPMax` continua recebendo o payload de
sempre, e `estender()` o promove para a forma nova sem inventar decisão.

Este arquivo é **stdlib + brief**: não importa `google.ads`. Os nomes de enum
que ele aceita são tuplas escritas aqui, e `testes_pmax.py` as confere contra o
proto v25 instalado — para a tela (que não pode arrastar o SDK no boot) poder
ler o mesmo vocabulário sem segunda lista.

## O que foi MEDIDO, e não lido (validate_only na Crédito Up, 08/10/2026)

Cada decisão abaixo que cita "medido" tem um `request_id` no relatório da onda:

  * `AssetGroup.tracking_url_template`/`final_url_suffix`/`url_custom_parameters`
    e `path1`/`path2`: aceitos.
  * `AUTOMATED_VIDEO_CRAWL`: aceito OPTED_OUT sem fontes e OPTED_IN com
    LANDING_PAGE + YOUTUBE + SOCIAL. ⚠️ Também aceito OPTED_IN SEM fonte nenhuma
    — por isso a recusa local abaixo: "ligado e vazio" é escolha sem conteúdo.
  * `FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION` OPTED_IN com
    `TEXT_ASSET_AUTOMATION` OPTED_OUT: RECUSADO
    (`DYNAMIC_TEXT_ASSET_CANNOT_OPT_OUT_WITH_FINAL_URL_EXPANSION_OPT_IN`).
  * keyword negativa EXACT e PHRASE em PMax: aceitas (o BROAD fixo era opinião).
  * exclusão de marca por `brand_list` criada NO MESMO mutate: aceita.
    Inclusão (positiva): RECUSADA (`ONLY_EXCLUSION_BRAND_LIST_ALLOWED_FOR_CAMPAIGN_TYPE`).
  * exclusão de URL (`webpage` negativo): aceita. Inclusão positiva: recusada.
  * placement negativo de campanha e `campaign_shared_set` NEGATIVE_PLACEMENTS:
    RECUSADOS (`OPERATION_NOT_PERMITTED_FOR_CONTEXT`). Não há campo para isso.
  * `campaign_shared_set` NEGATIVE_KEYWORDS: aceito.
  * `CampaignConversionGoal` atualizado com o id TEMPORÁRIO da campanha: aceito.
  * `GENERATE_DESIGN_VERSIONS_FOR_IMAGES` OPTED_OUT em PMax: aceito (o guia não
    o lista para PMax). Os outros cinco tipos de Demand Gen/vídeo:
    `ENUM_VALUE_NOT_PERMITTED`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Mapping
from urllib.parse import urlparse

from .brief import ConfiguracaoPMax, ImagensPMax, SinalDeAudiencia

# ═══════════════════════════════════════════════════════════════════════════
# VOCABULÁRIO (conferido contra o proto v25 em testes_pmax.py)
# ═══════════════════════════════════════════════════════════════════════════

#: As automações de nível de campanha que a API ACEITA em PMax na v25.2, na
#: ordem em que viajam. As cinco primeiras são `automacoes.AUTOMACOES_PMAX_RECUSADAS`
#: na mesma ordem — o selo do plano cobre a lista, e reordenar mudaria a
#: impressão de um payload já aprovado. As duas novas entram NO FIM.
#:
#:   AUTOMATED_VIDEO_CRAWL               v25.2: busca vídeo nas URLs declaradas
#:                                       (LP, rede social, canal do YouTube).
#:   GENERATE_DESIGN_VERSIONS_FOR_IMAGES aceito pela API em PMax (validate_only),
#:                                       embora o guia só o cite em Demand Gen.
#:                                       Declarar OPTED_OUT é a única forma de
#:                                       afirmar que ele não decide em silêncio.
AUTOMACOES_PMAX_V25: tuple[str, ...] = (
    "FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION",
    "TEXT_ASSET_AUTOMATION",
    "GENERATE_IMAGE_ENHANCEMENT",
    "GENERATE_ENHANCED_YOUTUBE_VIDEOS",
    "GENERATE_IMAGE_EXTRACTION",
    "AUTOMATED_VIDEO_CRAWL",
    "GENERATE_DESIGN_VERSIONS_FOR_IMAGES",
)

#: Os tipos que a API recusa em campanha PMax (`ENUM_VALUE_NOT_PERMITTED`,
#: medido). Pedir um deles é erro local, com a mesma causa que a remota daria.
AUTOMACOES_RECUSADAS_PELA_API_EM_PMAX: tuple[str, ...] = (
    "GENERATE_VERTICAL_YOUTUBE_VIDEOS",
    "GENERATE_SHORTER_YOUTUBE_VIDEOS",
    "GENERATE_LANDING_PAGE_PREVIEW",
    "GENERATE_LANDING_PAGE_TEXT",
    "GENERATE_VIDEOS_FROM_OTHER_ASSETS",
    "GENERATE_ANIMATED_IMAGES_FROM_OTHER_ASSETS",
)

PLATAFORMAS_DE_VIDEO_CRAWL: tuple[str, ...] = ("LANDING_PAGE", "SOCIAL", "YOUTUBE")
MATCH_TYPES_NEGATIVOS: tuple[str, ...] = ("BROAD", "PHRASE", "EXACT")
OPERANDOS_DE_URL: tuple[str, ...] = ("URL", "PAGE_TITLE", "PAGE_CONTENT")
OPERADORES_DE_URL: tuple[str, ...] = ("CONTAINS", "EQUALS")
MODOS_CLIENTE_NOVO: tuple[str, ...] = ("TARGET_ALL", "TARGET_SPECIFIC")

#: `ConversionActionCategory` e `ConversionOrigin` sem UNSPECIFIED/UNKNOWN.
CATEGORIAS_DE_CONVERSAO: tuple[str, ...] = (
    "DEFAULT", "PAGE_VIEW", "PURCHASE", "SIGNUP", "DOWNLOAD", "ADD_TO_CART",
    "BEGIN_CHECKOUT", "SUBSCRIBE_PAID", "PHONE_CALL_LEAD", "IMPORTED_LEAD",
    "SUBMIT_LEAD_FORM", "BOOK_APPOINTMENT", "REQUEST_QUOTE", "GET_DIRECTIONS",
    "OUTBOUND_CLICK", "CONTACT", "ENGAGEMENT", "STORE_VISIT", "STORE_SALE",
    "QUALIFIED_LEAD", "CONVERTED_LEAD", "YOUTUBE_FOLLOW_ON_VIEWS",
    "IN_APP_AD_REVENUE",
)
ORIGENS_DE_CONVERSAO: tuple[str, ...] = (
    "WEBSITE", "GOOGLE_HOSTED", "APP", "CALL_FROM_ADS", "STORE",
    "YOUTUBE_HOSTED", "LOCAL_SERVICES_ADS",
)

#: `Campaign.BrandGuidelines.predefined_font_family` — lista FECHADA do proto.
FONTES_DE_MARCA: tuple[str, ...] = (
    "Open Sans", "Roboto", "Montserrat", "Poppins", "Lato", "Oswald",
    "Playfair Display", "Roboto Slab",
)

# ── tetos (fonte: proto v25 / system limits; nenhum inventado) ──────────────
PATH_MAX_CHARS = 15                    # AssetGroup.path1/path2
TERMOS_EXCLUIDOS_MAX, TERMO_EXCLUIDO_MAX_CHARS = 25, 30        # TextGuidelines
RESTRICOES_MAX, RESTRICAO_MAX_CHARS = 40, 300                  # TextGuidelines
PARAMETROS_PERSONALIZADOS_MAX = 8      # CustomParameter por entidade
CHAVE_PERSONALIZADA = re.compile(r"^[A-Za-z0-9]{1,16}$")
VALOR_PERSONALIZADO_MAX_CHARS = 250
VIDEOS_POR_GRUPO_MAX = 15              # YOUTUBE_VIDEO 0..15 (PMAX_FIELD_REQUIREMENTS)
TEMAS_DE_BUSCA_POR_GRUPO_MAX = 50      # search themes por asset group (medido: 51 recusa)

_ID_YOUTUBE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ENTIDADE_DE_MARCA = re.compile(r"^/[gm]/[A-Za-z0-9_]+$")
_SHARED_SET = re.compile(r"^customers/(\d+)/sharedSets/(\d+)$")
_GOAL = re.compile(r"^customers/(\d+)/goals/(\d+)$")
_COR_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_MACRO_PERSONALIZADA = re.compile(r"\{_([A-Za-z0-9]+)\}")


# ═══════════════════════════════════════════════════════════════════════════
# OS TIPOS
# ═══════════════════════════════════════════════════════════════════════════


def _tupla(dono: str, campo: str, valor, tipo=None) -> None:
    if not isinstance(valor, tuple):
        raise TypeError(f"{dono}.{campo} precisa ser tupla — lista mutável "
                        "deixaria trocar a escolha depois do selo")
    if tipo is not None:
        for item in valor:
            if not isinstance(item, tipo):
                raise TypeError(f"{dono}.{campo} exige {tipo.__name__} tipado, "
                                f"recebeu {type(item).__name__}")


@dataclass(frozen=True)
class OpcoesDeUrl:
    """URL options do ASSET GROUP (v25.2) — a marcação por grupo sem duplicar campanha.

    ⚠️ `final_url_suffix` do grupo SUBSTITUI o da campanha (o nível mais
    específico vence). Se o grupo declarasse um sufixo livre, o `vc_*` que fecha
    o join custo × receita sumiria só nele. Por isso o sufixo do grupo é SEMPRE
    `marcacao.montar(...)` da campanha + `sufixo_extra`: o grupo acrescenta,
    nunca troca.
    """

    #: Pares (chave, valor) acrescentados ao sufixo da campanha neste grupo.
    sufixo_extra: tuple[tuple[str, str], ...] = ()
    #: Template de tracking (parallel tracking). Vazio = herda a conta/campanha.
    tracking_url_template: str = ""
    #: `url_custom_parameters` — pares (chave, valor) usados como `{_chave}`.
    parametros_personalizados: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _tupla("OpcoesDeUrl", "sufixo_extra", self.sufixo_extra, tuple)
        _tupla("OpcoesDeUrl", "parametros_personalizados",
               self.parametros_personalizados, tuple)


@dataclass(frozen=True)
class VideoYouTube:
    """`YOUTUBE_VIDEO` CRIADO no mesmo mutate a partir do id público do vídeo.

    Diferente de `ImagensPMax.videos_youtube` (resource name de asset que já
    existe), aqui nasce um `Asset` do tipo `YOUTUBE_VIDEO` com
    `youtube_video_asset.youtube_video_id` — sem round-trip, dentro da mesma
    atomicidade do resto do grafo.
    """

    video_id: str
    nome: str = ""

    def __post_init__(self) -> None:
        if not _ID_YOUTUBE.fullmatch(str(self.video_id or "")):
            raise ValueError(
                f"id de vídeo do YouTube {self.video_id!r} inválido: são 11 "
                "caracteres [A-Za-z0-9_-], o trecho depois de `v=` na URL")


@dataclass(frozen=True)
class TextosPMax:
    headlines: tuple[str, ...]
    long_headlines: tuple[str, ...]
    descriptions: tuple[str, ...]

    def __post_init__(self) -> None:
        for campo in ("headlines", "long_headlines", "descriptions"):
            _tupla("TextosPMax", campo, getattr(self, campo), str)


@dataclass(frozen=True)
class AssetGroupPMax:
    """Um asset group ADICIONAL, com tudo que é dele — e nada herdado.

    O primeiro asset group continua nascendo do brief (`copy`, `imagens_pmax`,
    `url_final`, `pmax.sinais`), exatamente como antes. Os adicionais não
    herdam nada: herança silenciosa repetiria o criativo do grupo 0 e repartiria
    a verba por sorteio, que é o motivo pelo qual este builder emitia um só.
    """

    nome: str
    url_final: str
    textos: TextosPMax
    imagens: ImagensPMax
    #: `()` é "sem dica"; `None` é ninguém ter escolhido — e isso é recusa.
    sinais: tuple[SinalDeAudiencia, ...] | None
    videos: tuple[VideoYouTube, ...] = ()
    path1: str = ""
    path2: str = ""
    opcoes_de_url: OpcoesDeUrl | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.textos, TextosPMax):
            raise TypeError("AssetGroupPMax.textos exige TextosPMax")
        if not isinstance(self.imagens, ImagensPMax):
            raise TypeError("AssetGroupPMax.imagens exige ImagensPMax")
        if self.sinais is not None:
            _tupla("AssetGroupPMax", "sinais", self.sinais, SinalDeAudiencia)
        _tupla("AssetGroupPMax", "videos", self.videos, VideoYouTube)
        if self.opcoes_de_url is not None and not isinstance(
                self.opcoes_de_url, OpcoesDeUrl):
            raise TypeError("AssetGroupPMax.opcoes_de_url exige OpcoesDeUrl")


@dataclass(frozen=True)
class FonteDeVideoCrawl:
    """`AutomatedVideoCrawlInfo` (v25.2): uma URL onde o Google pode buscar vídeo."""

    url: str
    plataforma: str
    habilitada: bool = True


@dataclass(frozen=True)
class ExclusaoDeUrl:
    """`CampaignCriterion.webpage` NEGATIVO — só morde com a expansão de URL ligada."""

    nome: str
    argumento: str
    operando: str = "URL"
    operador: str = "CONTAINS"


@dataclass(frozen=True)
class NegativaPMax:
    texto: str
    match_type: str = "BROAD"


@dataclass(frozen=True)
class MarcaExcluida:
    """Uma marca do catálogo do Google (`BrandSuggestionService`), por entidade."""

    entity_id: str
    nome: str = ""


@dataclass(frozen=True)
class MetaDeConversao:
    """`CampaignConversionGoal` — sobrescreve, NESTA campanha, o biddable da conta."""

    categoria: str
    origem: str
    biddable: bool


@dataclass(frozen=True)
class MetaClienteNovo:
    """Aquisição de cliente novo no esquema UNIFICADO da v25.

    ⚠️ `CampaignLifecycleGoal` e `CustomerAcquisitionGoalSettings` foram
    REMOVIDOS na v25.0. O mecanismo agora é `Goal` (conta, tipo
    NEW_CUSTOMER_ACQUISITION, via `GoalService`) + `CampaignGoalConfig`
    (campanha → goal, via `CampaignGoalConfigService`). Nenhum dos dois existe
    em `MutateOperation`: a meta NÃO cabe no mutate atômico e é aplicada numa
    segunda chamada, com o id REAL da campanha (`pmax_grafo.operacoes_pos_criacao`).
    """

    #: `customers/<cid>/goals/<id>` — o Goal NEW_CUSTOMER_ACQUISITION da conta.
    goal: str
    #: TARGET_ALL = todos, com ajuste de valor para cliente novo;
    #: TARGET_SPECIFIC = só cliente novo.
    modo: str
    valor_adicional: float | None = None
    multiplicador_de_valor: float | None = None


@dataclass(frozen=True)
class DiretrizesDeMarca:
    """`Campaign.brand_guidelines` — só com `brand_guidelines_enabled=True`."""

    cor_principal: str = ""
    cor_destaque: str = ""
    fonte: str = ""


@dataclass(frozen=True)
class ConfiguracaoPMaxV25(ConfiguracaoPMax):
    """`ConfiguracaoPMax` + as decisões da v25.2. Todo campo novo tem default
    que reproduz o payload de antes (exceto as correções medidas, ver pmax.py).
    """

    # ── grupo 0 (o que nasce do brief) ──────────────────────────────────────
    path1: str = ""
    path2: str = ""
    opcoes_de_url: OpcoesDeUrl | None = None
    videos: tuple[VideoYouTube, ...] = ()
    # ── grupos 1..N ─────────────────────────────────────────────────────────
    grupos_adicionais: tuple[AssetGroupPMax, ...] = ()
    # ── automações: tudo OPTED_OUT, exceto o que o dono optar ──────────────
    automacoes_optadas: tuple[str, ...] = ()
    video_crawl: tuple[FonteDeVideoCrawl, ...] = ()
    video_crawl_direitos_declarados: bool = False
    exclusoes_de_url: tuple[ExclusaoDeUrl, ...] = ()
    termos_excluidos: tuple[str, ...] = ()
    restricoes_de_mensagem: tuple[str, ...] = ()
    diretrizes_de_marca: DiretrizesDeMarca | None = None
    # ── negativas e marcas ─────────────────────────────────────────────────
    negativas_tipadas: tuple[NegativaPMax, ...] = ()
    listas_de_negativas: tuple[str, ...] = ()
    marcas_excluidas: tuple[MarcaExcluida, ...] = ()
    listas_de_marcas_excluidas: tuple[str, ...] = ()
    # ── metas ──────────────────────────────────────────────────────────────
    metas_de_conversao: tuple[MetaDeConversao, ...] = ()
    meta_cliente_novo: MetaClienteNovo | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        dono = "ConfiguracaoPMaxV25"
        _tupla(dono, "videos", self.videos, VideoYouTube)
        _tupla(dono, "grupos_adicionais", self.grupos_adicionais, AssetGroupPMax)
        _tupla(dono, "automacoes_optadas", self.automacoes_optadas, str)
        _tupla(dono, "video_crawl", self.video_crawl, FonteDeVideoCrawl)
        _tupla(dono, "exclusoes_de_url", self.exclusoes_de_url, ExclusaoDeUrl)
        _tupla(dono, "termos_excluidos", self.termos_excluidos, str)
        _tupla(dono, "restricoes_de_mensagem", self.restricoes_de_mensagem, str)
        _tupla(dono, "negativas_tipadas", self.negativas_tipadas, NegativaPMax)
        _tupla(dono, "listas_de_negativas", self.listas_de_negativas, str)
        _tupla(dono, "marcas_excluidas", self.marcas_excluidas, MarcaExcluida)
        _tupla(dono, "listas_de_marcas_excluidas",
               self.listas_de_marcas_excluidas, str)
        _tupla(dono, "metas_de_conversao", self.metas_de_conversao, MetaDeConversao)
        if not isinstance(self.video_crawl_direitos_declarados, bool):
            raise TypeError("video_crawl_direitos_declarados precisa ser bool")


def estender(cfg: ConfiguracaoPMax) -> ConfiguracaoPMaxV25:
    """`ConfiguracaoPMax` antiga → V25 com todos os defaults. Sem decisão inventada."""
    if isinstance(cfg, ConfiguracaoPMaxV25):
        return cfg
    base = {f.name: getattr(cfg, f.name) for f in fields(ConfiguracaoPMax)}
    return ConfiguracaoPMaxV25(**base)


# ═══════════════════════════════════════════════════════════════════════════
# A RÉGUA — tudo que a API recusaria, ou aceitaria e não deveria
# ═══════════════════════════════════════════════════════════════════════════


def _https(url: str) -> bool:
    p = urlparse(str(url or ""))
    return p.scheme == "https" and bool(p.netloc)


def checar_caminho(path1: str, path2: str, onde: str, r, codigo: str) -> None:
    for nome, valor in (("path1", path1), ("path2", path2)):
        if len(valor) > PATH_MAX_CHARS:
            r.erro(f"{onde}.{nome}", valor,
                   f"`AssetGroup.{nome}` aceita até {PATH_MAX_CHARS} caracteres",
                   codigo)
        if valor and ("/" in valor or " " in valor.strip()):
            r.erro(f"{onde}.{nome}", valor,
                   "caminho de exibição é UM segmento: sem barra e sem espaço",
                   codigo)
    if path2 and not path1:
        r.erro(f"{onde}.path2", path2,
               "`path2` sem `path1` — a API só exibe o segundo segmento depois "
               "do primeiro", codigo)


def checar_opcoes_de_url(op: OpcoesDeUrl | None, onde: str, r, codigo: str) -> None:
    if op is None:
        return
    declarados: set[str] = set()
    if len(op.parametros_personalizados) > PARAMETROS_PERSONALIZADOS_MAX:
        r.erro(f"{onde}.parametros_personalizados",
               f"{len(op.parametros_personalizados)} pares",
               f"no máximo {PARAMETROS_PERSONALIZADOS_MAX} parâmetros "
               "personalizados por entidade", codigo)
    for par in op.parametros_personalizados:
        if len(par) != 2:
            r.erro(f"{onde}.parametros_personalizados", par,
                   "cada parâmetro é um par (chave, valor)", codigo)
            continue
        chave, valor = par
        if not CHAVE_PERSONALIZADA.fullmatch(str(chave)):
            r.erro(f"{onde}.parametros_personalizados", chave,
                   "chave de `url_custom_parameters` é alfanumérica, 1 a 16 "
                   "caracteres, sem o `_` (a macro `{_chave}` o acrescenta)",
                   codigo)
        if not str(valor) or len(str(valor)) > VALOR_PERSONALIZADO_MAX_CHARS:
            r.erro(f"{onde}.parametros_personalizados", chave,
                   f"valor vazio ou acima de {VALOR_PERSONALIZADO_MAX_CHARS} "
                   "caracteres", codigo)
        if chave in declarados:
            r.erro(f"{onde}.parametros_personalizados", chave,
                   "chave duplicada — a última venceria em silêncio", codigo)
        declarados.add(chave)

    t = op.tracking_url_template.strip()
    if t:
        if "{lpurl" not in t and "{unescapedlpurl" not in t and "{escapedlpurl" not in t:
            r.erro(f"{onde}.tracking_url_template", t,
                   "o template precisa carregar a URL final ({lpurl} ou "
                   "variante): sem ela o clique perde o destino aprovado",
                   codigo)
        if not (t.startswith("{") or _https(t)):
            r.erro(f"{onde}.tracking_url_template", t,
                   "o template começa com {lpurl} ou com https://", codigo)

    usados = set(_MACRO_PERSONALIZADA.findall(t))
    for chave, valor in op.sufixo_extra:
        usados |= set(_MACRO_PERSONALIZADA.findall(str(valor)))
    for faltante in sorted(usados - declarados):
        r.erro(f"{onde}", f"{{_{faltante}}}",
               "macro personalizada sem `parametros_personalizados` "
               "correspondente — a API aceita e o valor chega vazio", codigo)


def checar(cfg: ConfiguracaoPMaxV25, *, cid: str,
           brand_guidelines_enabled: bool | None, r, codigos: Mapping[str, str]) -> None:
    """As decisões v25 que não dependem de cliente nem de rede.

    `codigos` traz os códigos de `plano` (este módulo não o importa, para não
    arrastar a cadeia de `plano` para quem só quer o vocabulário).
    """
    ausente = codigos["CONFIGURACAO_AUSENTE"]
    nao_operado = codigos["CAMPO_NAO_OPERADO"]
    teto = codigos["ASSET_ACIMA_DO_TETO"]
    rn_invalido = codigos["RESOURCE_NAME_INVALIDO"]

    # ── automações ─────────────────────────────────────────────────────────
    optadas = set(cfg.automacoes_optadas)
    if len(optadas) != len(cfg.automacoes_optadas):
        r.erro("pmax.automacoes_optadas", cfg.automacoes_optadas,
               "automação repetida", ausente)
    for nome in cfg.automacoes_optadas:
        if nome in AUTOMACOES_RECUSADAS_PELA_API_EM_PMAX:
            r.erro("pmax.automacoes_optadas", nome,
                   "a API responde ENUM_VALUE_NOT_PERMITTED para este tipo em "
                   "campanha PMax (medido em validate_only) — ele é de Demand Gen",
                   nao_operado)
        elif nome not in AUTOMACOES_PMAX_V25:
            r.erro("pmax.automacoes_optadas", nome,
                   f"automação desconhecida em PMax v25.2; as aplicáveis são "
                   f"{', '.join(AUTOMACOES_PMAX_V25)}", nao_operado)
    if ("FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION" in optadas
            and "TEXT_ASSET_AUTOMATION" not in optadas):
        r.erro("pmax.automacoes_optadas", "FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION",
               "expansão de URL final exige TEXT_ASSET_AUTOMATION também "
               "optada — a API recusa com DYNAMIC_TEXT_ASSET_CANNOT_OPT_OUT_"
               "WITH_FINAL_URL_EXPANSION_OPT_IN. Opte as duas, ou nenhuma",
               ausente)

    crawl = "AUTOMATED_VIDEO_CRAWL" in optadas
    if cfg.video_crawl and not crawl:
        r.erro("pmax.video_crawl", f"{len(cfg.video_crawl)} fontes",
               "fontes de video crawl declaradas com AUTOMATED_VIDEO_CRAWL "
               "fora de `automacoes_optadas` — elas não viajariam, e o plano "
               "diria uma coisa enquanto o payload faz outra", ausente)
    if crawl:
        if not any(f.habilitada for f in cfg.video_crawl):
            r.erro("pmax.video_crawl", "vazio",
                   "AUTOMATED_VIDEO_CRAWL optado sem nenhuma fonte habilitada. "
                   "A API ACEITA (medido) e o resultado é uma escolha sem "
                   "conteúdo — declare ao menos uma URL", ausente)
        if not cfg.video_crawl_direitos_declarados:
            r.erro("pmax.video_crawl_direitos_declarados", False,
                   "ao ligar o crawl o anunciante declara ter os direitos "
                   "sobre os vídeos encontrados (guia de asset automation). "
                   "Essa declaração é do dono, explícita, e não um default",
                   ausente)
    vistas: set[tuple[str, str]] = set()
    for f in cfg.video_crawl:
        if f.plataforma not in PLATAFORMAS_DE_VIDEO_CRAWL:
            r.erro("pmax.video_crawl", f.plataforma,
                   f"plataforma fora de {', '.join(PLATAFORMAS_DE_VIDEO_CRAWL)}",
                   ausente)
        if not _https(f.url):
            r.erro("pmax.video_crawl", f.url, "fonte de crawl precisa ser https",
                   ausente)
        elif f.plataforma == "YOUTUBE" and not urlparse(f.url).netloc.endswith(
                ("youtube.com", "youtu.be")):
            r.erro("pmax.video_crawl", f.url,
                   "fonte YOUTUBE fora de youtube.com", ausente)
        if (f.url, f.plataforma) in vistas:
            r.erro("pmax.video_crawl", f.url, "fonte repetida", ausente)
        vistas.add((f.url, f.plataforma))

    if cfg.exclusoes_de_url and "FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION" not in optadas:
        r.aviso("pmax.exclusoes_de_url", f"{len(cfg.exclusoes_de_url)} regras",
                "exclusão de URL só restringe a EXPANSÃO de URL final, que está "
                "OPTED_OUT. A API aceita; a regra fica dormente até a expansão "
                "ser ligada", nao_operado)
    nomes_exclusao: set[str] = set()
    for e in cfg.exclusoes_de_url:
        if not e.nome.strip() or not e.argumento.strip():
            r.erro("pmax.exclusoes_de_url", e.nome,
                   "exclusão de URL sem nome ou sem argumento — "
                   "`criterion_name` e a condição são obrigatórios", ausente)
        if e.operando not in OPERANDOS_DE_URL or e.operador not in OPERADORES_DE_URL:
            r.erro("pmax.exclusoes_de_url", f"{e.operando}/{e.operador}",
                   f"operando ∈ {OPERANDOS_DE_URL}, operador ∈ {OPERADORES_DE_URL}",
                   ausente)
        if e.nome in nomes_exclusao:
            r.erro("pmax.exclusoes_de_url", e.nome, "nome repetido", ausente)
        nomes_exclusao.add(e.nome)

    # ── guias de texto e de marca ──────────────────────────────────────────
    if len(cfg.termos_excluidos) > TERMOS_EXCLUIDOS_MAX:
        r.erro("pmax.termos_excluidos", len(cfg.termos_excluidos),
               f"`text_guidelines.term_exclusions` aceita até {TERMOS_EXCLUIDOS_MAX}",
               teto)
    for t in cfg.termos_excluidos:
        if not t.strip() or len(t) > TERMO_EXCLUIDO_MAX_CHARS:
            r.erro("pmax.termos_excluidos", t,
                   f"termo vazio ou acima de {TERMO_EXCLUIDO_MAX_CHARS} caracteres",
                   teto)
    if len(cfg.restricoes_de_mensagem) > RESTRICOES_MAX:
        r.erro("pmax.restricoes_de_mensagem", len(cfg.restricoes_de_mensagem),
               f"`text_guidelines.messaging_restrictions` aceita até {RESTRICOES_MAX}",
               teto)
    for t in cfg.restricoes_de_mensagem:
        if not t.strip() or len(t) > RESTRICAO_MAX_CHARS:
            r.erro("pmax.restricoes_de_mensagem", t[:40],
                   f"restrição vazia ou acima de {RESTRICAO_MAX_CHARS} caracteres",
                   teto)

    d = cfg.diretrizes_de_marca
    if d is not None:
        if brand_guidelines_enabled is not True:
            r.erro("pmax.diretrizes_de_marca", "declaradas",
                   "`campaign.brand_guidelines` só vale com "
                   "brand_guidelines_enabled=True (proto v25)", nao_operado)
        if bool(d.cor_principal) != bool(d.cor_destaque):
            r.erro("pmax.diretrizes_de_marca", "cores",
                   "cor principal e cor de destaque andam juntas (proto v25)",
                   ausente)
        for cor in (d.cor_principal, d.cor_destaque):
            if cor and not _COR_HEX.fullmatch(cor):
                r.erro("pmax.diretrizes_de_marca", cor, "cor em hex #RRGGBB",
                       ausente)
        if d.fonte and d.fonte not in FONTES_DE_MARCA:
            r.erro("pmax.diretrizes_de_marca", d.fonte,
                   f"fonte fora da lista fechada do proto: {', '.join(FONTES_DE_MARCA)}",
                   ausente)

    # ── negativas ──────────────────────────────────────────────────────────
    vistos_neg: set[tuple[str, str]] = {
        (t.strip().casefold(), "BROAD") for t in (cfg.negativas or ())}
    for n in cfg.negativas_tipadas:
        if n.match_type not in MATCH_TYPES_NEGATIVOS:
            r.erro("pmax.negativas_tipadas", n.match_type,
                   f"match type ∈ {MATCH_TYPES_NEGATIVOS} (os três medidos em "
                   "validate_only)", ausente)
        if not n.texto.strip():
            r.erro("pmax.negativas_tipadas", "", "negativa vazia", ausente)
        chave = (n.texto.strip().casefold(), n.match_type)
        if chave in vistos_neg:
            r.erro("pmax.negativas_tipadas", n.texto,
                   f"negativa repetida ({n.match_type})", ausente)
        vistos_neg.add(chave)

    for campo, lista in (("listas_de_negativas", cfg.listas_de_negativas),
                         ("listas_de_marcas_excluidas", cfg.listas_de_marcas_excluidas)):
        for rn in lista:
            m = _SHARED_SET.fullmatch(rn)
            if not m:
                r.erro(f"pmax.{campo}", rn,
                       "forma canônica `customers/<cid>/sharedSets/<id>`",
                       rn_invalido)
            elif m.group(1) != str(cid):
                r.erro(f"pmax.{campo}", rn, f"lista de outra conta que não {cid}",
                       rn_invalido)
        if len(set(lista)) != len(lista):
            r.erro(f"pmax.{campo}", "repetida", "lista anexada duas vezes",
                   rn_invalido)

    entidades: set[str] = set()
    for m in cfg.marcas_excluidas:
        if not _ENTIDADE_DE_MARCA.fullmatch(m.entity_id):
            r.erro("pmax.marcas_excluidas", m.entity_id,
                   "entity_id do catálogo de marcas (`/g/…` ou `/m/…`, "
                   "de BrandSuggestionService)", rn_invalido)
        if m.entity_id in entidades:
            r.erro("pmax.marcas_excluidas", m.entity_id, "marca repetida",
                   rn_invalido)
        entidades.add(m.entity_id)

    # ── metas ──────────────────────────────────────────────────────────────
    pares: set[tuple[str, str]] = set()
    for g in cfg.metas_de_conversao:
        if g.categoria not in CATEGORIAS_DE_CONVERSAO:
            r.erro("pmax.metas_de_conversao", g.categoria,
                   "categoria fora de ConversionActionCategory", ausente)
        if g.origem not in ORIGENS_DE_CONVERSAO:
            r.erro("pmax.metas_de_conversao", g.origem,
                   "origem fora de ConversionOrigin", ausente)
        if not isinstance(g.biddable, bool):
            r.erro("pmax.metas_de_conversao", g.biddable,
                   "biddable precisa ser bool explícito", ausente)
        if (g.categoria, g.origem) in pares:
            r.erro("pmax.metas_de_conversao", f"{g.categoria}~{g.origem}",
                   "meta repetida", ausente)
        pares.add((g.categoria, g.origem))
    if cfg.metas_de_conversao and not any(g.biddable for g in cfg.metas_de_conversao):
        r.aviso("pmax.metas_de_conversao", "nenhuma biddable",
                "todas as metas declaradas estão biddable=False; o lance só "
                "otimiza pelas metas herdadas da conta que não foram tocadas",
                ausente)

    nc = cfg.meta_cliente_novo
    if nc is not None:
        m = _GOAL.fullmatch(nc.goal or "")
        if not m:
            r.erro("pmax.meta_cliente_novo.goal", nc.goal,
                   "forma canônica `customers/<cid>/goals/<id>` — o Goal "
                   "NEW_CUSTOMER_ACQUISITION da conta (GoalService)", rn_invalido)
        elif m.group(1) != str(cid):
            r.erro("pmax.meta_cliente_novo.goal", nc.goal,
                   f"goal de outra conta que não {cid}", rn_invalido)
        if nc.modo not in MODOS_CLIENTE_NOVO:
            r.erro("pmax.meta_cliente_novo.modo", nc.modo,
                   f"modo ∈ {MODOS_CLIENTE_NOVO} (CustomerLifecycleOptimizationMode v25)",
                   ausente)
        if nc.valor_adicional is not None and nc.multiplicador_de_valor is not None:
            r.erro("pmax.meta_cliente_novo", "valor",
                   "`additional_value` e `value_multiplier` são o mesmo oneof "
                   "(`value_adjustment`): escolha um", ausente)
        for nome, v in (("valor_adicional", nc.valor_adicional),
                        ("multiplicador_de_valor", nc.multiplicador_de_valor)):
            if v is not None and not v > 0:
                r.erro(f"pmax.meta_cliente_novo.{nome}", v, "precisa ser > 0",
                       ausente)
        r.aviso("pmax.meta_cliente_novo", nc.modo,
                "a meta de cliente novo é `CampaignGoalConfig`, que NÃO existe "
                "em MutateOperation: ela é aplicada numa segunda chamada "
                "(CampaignGoalConfigService) com o id REAL da campanha, depois "
                "do mutate atômico. Ela não está no validate_only deste grafo",
                nao_operado)
