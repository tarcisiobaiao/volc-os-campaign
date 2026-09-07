"""Provider-specific facts for the first, read-only Meta Ads slice.

The v9 traffic inventory uses Google ``customer_id`` and ``campaign_id`` as its
physical identity.  These types intentionally do not inherit from it: sharing
reliability rules is useful, pretending the storage identity is neutral is not.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.asset_vault.dominio import PayloadRecusado, recusar_chave_sensivel

META_ADS = "META_ADS"
TIPOS_DE_OBJETO = ("campaign", "adset", "ad", "creative")
TIPOS_DE_IDENTIDADE = TIPOS_DE_OBJETO + ("business", "account", "insight")
NIVEIS_DE_INSIGHT = ("account", "campaign", "adset", "ad")

# ---------------------------------------------------------------------------
# CONTRATO DO PEDIDO DE INSIGHTS (T05)
# ---------------------------------------------------------------------------
# O que a Meta devolve depende inteiramente do que foi PEDIDO: o grao do dia,
# o fuso da conta, o instante da atribuicao e a janela. Sem registrar o pedido,
# um numero guardado nao tem significado — e dois numeros de pedidos diferentes
# viram uma soma silenciosamente errada. Por isso o pedido e tipado, e o que foi
# efetivamente ENVIADO viaja junto do fato.

#: `time_increment=1` e o unico que produz uma serie diaria. `all_days` devolve
#: UMA linha agregada do periodo inteiro — util, mas nunca comparavel com a
#: serie diaria nem somavel com ela.
INCREMENTOS_DE_TEMPO = ("1", "7", "28", "monthly", "all_days")

#: Quando a conversao e contada: no instante do anuncio (`impression`) ou no
#: instante da conversao (`conversion`). Trocar isto MOVE gasto e resultado
#: entre dias. `mixed` usa impression para gasto e conversion para acoes.
INSTANTES_DE_RELATORIO = ("impression", "conversion", "mixed")

#: Janelas suportadas pela v26 da Graph. `default` significa "nao pedi janela
#: nenhuma e aceito a da conta" — e por isso NAO pode ser carimbada como se
#: fosse uma janela explicita.
JANELAS_DE_ATRIBUICAO = (
    "1d_click", "7d_click", "28d_click",
    "1d_view", "7d_view", "28d_view",
    "1d_ev", "7d_ev", "28d_ev",
)
JANELA_PADRAO_DA_CONTA = "default"

#: Breakdowns liberados. A lista e curta de proposito: cada breakdown muda o
#: grao da linha, e um breakdown novo sem coluna correspondente produz linhas
#: que colidem na chave e se sobrescrevem.
BREAKDOWNS_PERMITIDOS = (
    "none",
    "publisher_platform",
    "platform_position",
    "impression_device",
    "device_platform",
    "country",
    "region",
)

#: Combinacoes recusadas antes de qualquer chamada. A Meta rejeita algumas
#: delas com erro generico; recusar aqui produz uma mensagem util e nao gasta
#: cota da conta para descobrir.
_COMBINACOES_PROIBIDAS = {
    # `region` so faz sentido a partir de campanha; no nivel da conta a Meta
    # devolve a agregacao do anunciante inteiro e o join por objeto se perde.
    ("account", "region"),
    ("account", "platform_position"),
}

#: Metricas que NAO podem ser somadas entre dias, objetos ou breakdowns.
#: `reach` conta PESSOAS unicas: somar o alcance de sete dias nao produz o
#: alcance da semana, produz um numero maior que a populacao alcancada. As
#: taxas precisam ser recalculadas a partir dos denominadores, nunca somadas.
METRICAS_NAO_ADITIVAS = ("reach", "frequency", "cpm", "cpc", "ctr")

#: Metricas que podem ser somadas dentro do MESMO pedido (mesmo nivel, mesma
#: janela, mesmo breakdown, mesmo instante de relatorio).
METRICAS_ADITIVAS = (
    "spend", "impressions", "clicks", "inline_link_clicks", "landing_page_views",
)

#: O unico action_type que a Meta documenta como visualizacao da pagina de
#: destino. ViewContent e um evento de pixel do site, com outra definicao e
#: outro dono — nunca entra nesta conta.
ACTION_TYPE_LPV = "landing_page_view"
ACTION_TYPE_VIEW_CONTENT = "offsite_conversion.fb_pixel_view_content"

ESTADOS_DE_PRONTIDAO = (
    "CONFIG_MISSING",
    "REFERENCE_PRESENT",
    "RESOLUTION_UNTESTED",
    "RESOLUTION_FAILED",
    "PERMISSIONS_INSUFFICIENT",
    "ACCOUNT_INACCESSIBLE",
    "READY_FOR_READ",
    "READY_FOR_VALIDATION",
    "READY_FOR_CREATE_PAUSED",
    "READY_FOR_ACTIVATION",
)
ESTADOS_DE_SYNC = ("ok", "falhou")

_ID_EXTERNO = re.compile(r"^[0-9]{1,40}$")
_NAMESPACE_META = uuid.UUID("bd4f9787-f6ea-4cf8-9f7e-847984945f19")


class ContratoMetaInvalido(ValueError):
    """Input cannot cross the Meta read boundary."""


#: Teto LOCAL de dias por pedido, por incremento. Politica desta base, revisavel;
#: NAO e uma constante publicada pela Meta e nao deve ser citada como tal.
MAX_DIAS_POR_PEDIDO = {"1": 92, "7": 366, "28": 731, "monthly": 731, "all_days": 731}


class CombinacaoDeInsightRecusada(ContratoMetaInvalido):
    """Level/breakdown/attribution-window combination outside the allowlist."""


def conta_canonica(valor: str) -> str:
    """Return a Meta ad-account id without the transport-only ``act_`` prefix."""
    texto = str(valor or "").strip()
    if texto.startswith("act_"):
        texto = texto[4:]
    if not _ID_EXTERNO.fullmatch(texto):
        raise ContratoMetaInvalido("conta Meta deve conter apenas o id numerico")
    return texto


def id_externo(valor: Any, *, campo: str = "id_externo") -> str:
    texto = str(valor or "").strip()
    if not _ID_EXTERNO.fullmatch(texto):
        raise ContratoMetaInvalido(f"{campo} Meta deve conter apenas digitos")
    return texto


def id_interno(*, conta_externa: str, tipo: str, id_externo_meta: str) -> str:
    """Derive identity from provider, account, object type and external id.

    Names are deliberately absent: renaming an object must not create another
    local identity.  Including the object type also prevents an accidental
    collision between two different Meta namespaces.
    """
    conta = conta_canonica(conta_externa)
    if tipo not in TIPOS_DE_IDENTIDADE:
        raise ContratoMetaInvalido(f"tipo Meta desconhecido: {tipo!r}")
    externo = id_externo(id_externo_meta)
    return str(uuid.uuid5(_NAMESPACE_META, f"{META_ADS}:{conta}:{tipo}:{externo}"))


def referencia_opaca_conta(conta_externa: str) -> str:
    """Stable non-secret account handle safe for the browser.

    The handle is deterministic so the UI can hold a reference, but it is not a
    reversible account-id map kept in the browser. The backend must re-read the
    accessible accounts and resolve this handle internally on every operation.
    """
    conta = conta_canonica(conta_externa)
    digest = hashlib.sha256(f"{META_ADS}:account:{conta}".encode("utf-8")).hexdigest()[:24]
    return f"metaacct_{digest}"


def referencia_opaca_objeto(conta_externa: str, tipo: str, id_externo_meta: str) -> str:
    """Opaque browser handle scoped by provider, account and object kind."""
    conta = conta_canonica(conta_externa)
    externo = id_externo(id_externo_meta)
    tipo_limpo = str(tipo or "").strip().lower()
    if not re.fullmatch(r"[a-z_]{2,40}", tipo_limpo):
        raise ContratoMetaInvalido("tipo de referencia Meta invalido")
    digest = hashlib.sha256(
        f"{META_ADS}:{conta}:{tipo_limpo}:{externo}".encode("utf-8")
    ).hexdigest()[:24]
    return f"metaobj_{digest}"


def mascarar_id(valor: Any) -> str | None:
    texto = str(valor or "").removeprefix("act_").strip()
    if not texto:
        return None
    return f"••••{texto[-4:]}"


def instante_utc(valor: datetime, *, campo: str) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ContratoMetaInvalido(f"{campo} precisa de timezone")
    return valor


def texto_opcional(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def booleano_opcional(valor: Any, *, campo: str = "flag") -> bool | None:
    """Tri-state honesto para uma flag da Graph: AUSENTE nao e ``False``.

    ## O defeito que isto conserta (A12)

    ``adaptador.py`` classificava disponibilidade com ``bool(linha.get(...))``.
    ``dict.get`` devolve ``None`` tanto para a chave AUSENTE quanto para o valor
    ``null``, e ``bool(None)`` e ``False``. Ou seja: quando a Meta NAO devolvia
    ``is_archived`` — por permissao insuficiente, por mascara de campos, por
    mudanca de versao do node — o codigo lia "nao esta arquivada" e o item caia
    em ``AVAILABLE_*``. "Nao sei" era APRESENTADO ao operador como "disponivel",
    que e a pior das tres respostas possiveis: e a unica que autoriza uma acao.

    ``None`` != ``False``:

    * ``False`` e uma AFIRMACAO do provedor ("li a flag; ela e falsa").
    * ``None`` e a AUSENCIA de afirmacao ("a flag nao veio; nao posso concluir").

    Por isso nao existe default para ``False`` aqui, e nao existe coercao
    silenciosa: o que nao for booleano de verdade nem uma das strings que a
    Graph documenta e RECUSADO. Um ``2``, um ``"talvez"`` ou um ``"yes"``
    significam que o contrato mudou — e um contrato mudado deve parar a leitura,
    nao virar um palpite.
    """
    if valor is None:
        return None
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        texto = valor.strip().lower()
        if texto in ("true", "1"):
            return True
        if texto in ("false", "0"):
            return False
    raise ContratoMetaInvalido(
        f"{campo} Meta precisa ser booleano ou 'true'/'false'/'1'/'0'"
    )


def decimal_opcional(valor: Any, *, campo: str) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor))
    except Exception as exc:  # pragma: no cover - branch defensive
        raise ContratoMetaInvalido(f"{campo} precisa ser decimal") from exc


# ---------------------------------------------------------------------------
# CATALOGOS SELECIONAVEIS (T04): TRI-STATE, FRESCOR E VOCABULARIO FECHADO
# ---------------------------------------------------------------------------
# O criador precisa ESCOLHER de listas reais — publicos existentes, fontes de
# mensuracao, localidades. Escolher errado custa dinheiro, e a fonte mais barata
# de escolha errada e um estado otimista: um item que a Meta nao soube descrever
# aparecendo como "disponivel". Todo o vocabulario abaixo existe para separar
# tres respostas que o codigo antigo achatava em duas: SIM, NAO e NAO SEI.

#: Estado de um item cuja disponibilidade NAO pode ser concluida da resposta.
#: E deliberadamente distinto de qualquer ``AVAILABLE_*``: um item UNKNOWN pode
#: ser exibido, mas nao pode ser tratado como elegivel para otimizacao.
ESTADO_DESCONHECIDO = "UNKNOWN"

#: Item cujo CONTRATO quebrou (id ilegivel, documento que nao e dict). Nos
#: catalogos novos ele vira uma LINHA com este estado em vez de derrubar a
#: pagina inteira — mas e contado a parte no envelope, para que "li tudo" nunca
#: se confunda com "li o que deu".
ESTADO_INVALIDO = "INVALID"

#: Disponivel e ja disparou: a Meta devolveu ``last_fired_time`` com valor.
ESTADO_DISPONIVEL_COM_DISPARO = "AVAILABLE_FIRED"
#: Disponivel e nunca disparou: ver ``classificar_frescor`` para a prova.
ESTADO_DISPONIVEL_SEM_DISPARO = "AVAILABLE_NEVER_FIRED"
#: Disponivel, mas o carimbo de ultimo disparo NAO veio e ha evidencia de que
#: houve disparo. Nao e "nunca disparou": e "nao sei quando foi a ultima vez".
ESTADO_FRESCOR_DESCONHECIDO = "UNKNOWN_FRESHNESS"
ESTADO_ARQUIVADO = "ARCHIVED"
ESTADO_INDISPONIVEL = "UNAVAILABLE"
ESTADO_DISPONIVEL = "AVAILABLE"

ESTADOS_DE_CONVERSAO = (
    ESTADO_DISPONIVEL_COM_DISPARO, ESTADO_DISPONIVEL_SEM_DISPARO,
    ESTADO_FRESCOR_DESCONHECIDO, ESTADO_ARQUIVADO, ESTADO_INDISPONIVEL,
    ESTADO_DESCONHECIDO, ESTADO_INVALIDO,
)
ESTADOS_DE_FONTE_DE_MENSURACAO = ESTADOS_DE_CONVERSAO
ESTADOS_DE_PUBLICO = (
    ESTADO_DISPONIVEL, ESTADO_INDISPONIVEL, ESTADO_DESCONHECIDO, ESTADO_INVALIDO,
)
ESTADOS_DE_GEOLOCALIZACAO = (ESTADO_DISPONIVEL, ESTADO_INVALIDO)

#: Vocabulario FECHADO da razao do desconhecimento. Um motivo livre viraria
#: prosa que ninguem consegue contar nem agregar; um motivo fechado permite
#: dizer "37 itens UNKNOWN, todos por IS_ARCHIVED_AUSENTE" — que e um pedido de
#: permissao, nao um misterio.
MOTIVO_IS_ARCHIVED_AUSENTE = "IS_ARCHIVED_AUSENTE"
MOTIVO_IS_UNAVAILABLE_AUSENTE = "IS_UNAVAILABLE_AUSENTE"
MOTIVO_LAST_FIRED_AUSENTE = "LAST_FIRED_TIME_AUSENTE"
MOTIVO_DELIVERY_STATUS_AUSENTE = "DELIVERY_STATUS_AUSENTE"
MOTIVO_SOURCE_KIND_INDISTINGUIVEL = "SOURCE_KIND_INDISTINGUIVEL"
MOTIVO_SOURCE_KIND_NAO_RECONHECIDO = "SOURCE_KIND_NAO_RECONHECIDO"
MOTIVO_CONTRATO_DO_ITEM_INVALIDO = "CONTRATO_DO_ITEM_INVALIDO"
MOTIVOS_DE_DESCONHECIMENTO = (
    MOTIVO_IS_ARCHIVED_AUSENTE, MOTIVO_IS_UNAVAILABLE_AUSENTE,
    MOTIVO_LAST_FIRED_AUSENTE, MOTIVO_DELIVERY_STATUS_AUSENTE,
    MOTIVO_SOURCE_KIND_INDISTINGUIVEL, MOTIVO_SOURCE_KIND_NAO_RECONHECIDO,
    MOTIVO_CONTRATO_DO_ITEM_INVALIDO,
)

#: PIXEL e DATASET sao tipos DIFERENTES de fonte de mensuracao, nao sinonimos.
#: A edge ``act_{id}/adspixels`` da v26 devolve o node AdsPixel sem discriminador
#: — por isso o kind honesto, na ausencia de um campo que o diga, e UNKNOWN.
#: Achatar os dois no rotulo "pixel" faria o operador escolher uma fonte que a
#: receita de conversao pode nao aceitar.
KIND_PIXEL = "PIXEL"
KIND_DATASET = "DATASET"
KINDS_DE_FONTE_DE_MENSURACAO = (KIND_PIXEL, KIND_DATASET, ESTADO_DESCONHECIDO)

#: ``location_types`` aceitos no pedido de busca geografica. A lista e curta e
#: fechada de proposito: um tipo nao registrado aqui produz uma chave que o
#: compilador nao sabe posicionar em ``targeting.geo_locations``.
TIPOS_DE_GEOLOCALIZACAO = (
    "country", "region", "city", "zip", "geo_market", "electoral_district",
    "country_group", "neighborhood", "subneighborhood", "subcity",
    "metro_area", "large_geo_area", "medium_geo_area", "small_geo_area",
)

#: Tipos cuja referencia opaca o servidor sabe RE-derivar a partir do catalogo
#: da conta. Fora desta lista nao existe edge conhecida — e adivinhar uma edge
#: e como adivinhar um id.
TIPOS_RESOLVIVEIS_POR_REFERENCIA = ("custom_audience", "pixel", "custom_conversion")

#: Frescor e DADO, nao cache. Ver ``frescor_do_catalogo``.
CATALOGO_VIGENTE = "VIGENTE"
CATALOGO_OBSOLETO = "OBSOLETO"
ESTADOS_DO_CATALOGO = (CATALOGO_VIGENTE, CATALOGO_OBSOLETO)
#: TTL LOCAL, politica desta base — nao e um numero publicado pela Meta.
TTL_PADRAO_DO_CATALOGO_S = 300
#: Geografia muda em escala de meses; publico e pixel mudam em escala de horas.
TTL_PADRAO_DO_CATALOGO_GEO_S = 86_400


def motivo_de_desconhecimento(motivo: str) -> str:
    """Guarda do vocabulario fechado: motivo nao registrado e erro de contrato."""
    if motivo not in MOTIVOS_DE_DESCONHECIMENTO:
        raise ContratoMetaInvalido(f"motivo de desconhecimento nao registrado: {motivo!r}")
    return motivo


def classificar_disponibilidade(
    *,
    arquivada: bool | None,
    indisponivel: bool | None,
    is_archived_esperado: bool = True,
) -> tuple[str, str | None]:
    """Disponibilidade tri-state a partir de flags que podem NAO ter vindo.

    Devolve ``(estado, motivo_desconhecido)``.

    ## A invariante

    ``AVAILABLE`` exige DUAS afirmacoes explicitas do provedor: arquivada e
    ``False`` E indisponivel e ``False``. Falta uma? O estado e ``UNKNOWN``.
    Nenhuma combinacao com flag ausente pode produzir ``AVAILABLE_*``.

    ## A ordem, e por que ela nao e a ordem literal do enunciado

    A evidencia POSITIVA e decisiva e checada primeiro: se a Meta disse
    ``is_archived=true``, o item esta arquivado — nao saber ``is_unavailable``
    nao torna esse fato menos verdadeiro, e degradar para ``UNKNOWN`` apagaria
    do operador a unica informacao util da linha. A invariante que importa
    ("ausencia nunca vira disponivel") continua valida: ``UNAVAILABLE`` e
    ``ARCHIVED`` sao MAIS restritivos que ``UNKNOWN``, nunca menos.

    ## ``is_archived_esperado``

    O node ``AdsPixel`` da v26 nao possui ``is_archived`` (so ``is_unavailable``).
    Exigir um campo que o node nao tem marcaria TODO pixel como ``UNKNOWN`` —
    ruido que ensina o operador a ignorar o estado. Ausencia so e ignorancia
    quando o campo era ESPERADO; por isso o chamador declara o que esperava.
    """
    if arquivada is True:
        return ESTADO_ARQUIVADO, None
    if indisponivel is True:
        return ESTADO_INDISPONIVEL, None
    if is_archived_esperado and arquivada is None:
        return ESTADO_DESCONHECIDO, motivo_de_desconhecimento(MOTIVO_IS_ARCHIVED_AUSENTE)
    if indisponivel is None:
        return ESTADO_DESCONHECIDO, motivo_de_desconhecimento(MOTIVO_IS_UNAVAILABLE_AUSENTE)
    return ESTADO_DISPONIVEL, None


def classificar_frescor(
    *,
    ultimo_presente: bool,
    ultimo: str | None,
    primeiro: str | None,
    corroborador_disponivel: bool = True,
) -> tuple[str, str | None]:
    """"Nunca disparou" e "nao sei quando disparou" sao respostas diferentes.

    Devolve ``(estado, motivo_desconhecido)``.

    ``adaptador.py:264`` decidia com ``elif ultimo is None:`` — e ``None`` ali
    cobria os dois casos, porque ``dict.get`` nao distingue chave ausente de
    valor nulo. Um item cujo ``last_fired_time`` a Meta simplesmente nao
    devolveu era apresentado como ``AVAILABLE_NEVER_FIRED``, isto e, como uma
    AFIRMACAO sobre o historico do pixel que ninguem tinha feito.

    ## Como a ausencia e desambiguada aqui

    A Graph OMITE do corpo o campo cujo valor e nulo, mesmo quando ele foi
    pedido em ``fields``. Logo, para um objeto que nunca disparou, ``first`` e
    ``last`` somem JUNTOS — essa e a assinatura coerente de "nunca disparou".
    Ja um corpo com ``first_fired_time`` presente e ``last_fired_time`` ausente
    e uma CONTRADICAO: o objeto comprovadamente disparou ao menos uma vez, e
    dizer "nunca disparou" seria mentir. Esse caso, e so ele, vira
    ``UNKNOWN_FRESHNESS``.

    Quando o campo VEM no corpo com valor vazio/nulo explicito, a resposta e do
    provedor e nao precisa de corroboracao: ``AVAILABLE_NEVER_FIRED``.

    ``corroborador_disponivel=False`` desliga essa desambiguacao para nodes que
    NAO possuem o campo corroborador — e ai toda ausencia vira
    ``UNKNOWN_FRESHNESS``, porque nao ha nada com que cruzar.
    """
    if ultimo is not None:
        return ESTADO_DISPONIVEL_COM_DISPARO, None
    if ultimo_presente:
        return ESTADO_DISPONIVEL_SEM_DISPARO, None
    if not corroborador_disponivel:
        # Sem campo corroborador no node (caso do `AdsPixel`, que nao tem
        # `first_fired_time`), a ausencia e simplesmente indecifravel. Aqui
        # nao ha assinatura coerente para invocar: a resposta honesta e "nao
        # sei", e nunca "nunca disparou".
        return ESTADO_FRESCOR_DESCONHECIDO, motivo_de_desconhecimento(
            MOTIVO_LAST_FIRED_AUSENTE)
    if primeiro is not None:
        return ESTADO_FRESCOR_DESCONHECIDO, motivo_de_desconhecimento(
            MOTIVO_LAST_FIRED_AUSENTE)
    return ESTADO_DISPONIVEL_SEM_DISPARO, None


def estado_do_catalogo(
    observado_em: datetime, ttl_s: int, *, agora: datetime | None = None,
) -> str:
    """VIGENTE enquanto dentro do TTL; OBSOLETO fora dele. Nunca "quase"."""
    momento = instante_utc(observado_em, campo="observado_em")
    if ttl_s < 0:
        raise ContratoMetaInvalido("ttl_s do catalogo nao pode ser negativo")
    referencia = agora or datetime.now(timezone.utc)
    referencia = instante_utc(referencia, campo="agora")
    decorrido = (referencia - momento).total_seconds()
    return CATALOGO_VIGENTE if decorrido <= ttl_s else CATALOGO_OBSOLETO


def frescor_do_catalogo(
    observado_em: datetime, ttl_s: int, *, agora: datetime | None = None,
) -> dict[str, Any]:
    """Frescor como DADO no envelope — nao como cache invisivel.

    Esta lane nao tem cache nem TTL de armazenamento, e este bloco NAO cria um.
    Um cache invisivel resolve o custo da chamada e cria um problema pior: o
    operador ve uma lista sem saber de QUANDO ela e, e uma re-busca silenciosa
    troca a lista debaixo de uma selecao ja feita. Aqui o instante da observacao
    e o prazo de validade viajam junto dos itens, e uma leitura fora do prazo
    aparece MARCADA como ``OBSOLETO`` — visivel, com os itens ainda a vista,
    nunca escondida e nunca re-buscada em silencio.
    """
    momento = instante_utc(observado_em, campo="observado_em")
    return {
        "observado_em": momento.isoformat(),
        "ttl_s": int(ttl_s),
        "expira_em": (momento + timedelta(seconds=int(ttl_s))).isoformat(),
        "estado_do_catalogo": estado_do_catalogo(momento, ttl_s, agora=agora),
    }


def reavaliar_frescor(
    envelope: Mapping[str, Any], *, agora: datetime | None = None,
) -> dict[str, Any]:
    """Re-carimba ``estado_do_catalogo`` de um envelope JA lido, sem rede.

    E o unico caminho legitimo para um envelope virar ``OBSOLETO``: recalcular a
    partir do instante que ele proprio carrega. Os itens permanecem intactos —
    marcar e diferente de esconder, e diferente de buscar de novo.
    """
    observado = envelope.get("observado_em")
    ttl = envelope.get("ttl_s")
    if not isinstance(observado, str) or not isinstance(ttl, int):
        raise ContratoMetaInvalido("envelope de catalogo sem observado_em/ttl_s")
    try:
        momento = datetime.fromisoformat(observado)
    except ValueError:
        raise ContratoMetaInvalido("observado_em do catalogo nao e ISO-8601") from None
    novo = dict(envelope)
    novo["estado_do_catalogo"] = estado_do_catalogo(momento, ttl, agora=agora)
    return novo


@dataclass(frozen=True)
class BusinessMeta:
    id_externo: str
    nome: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id_externo", id_externo(self.id_externo, campo="business.id"))
        object.__setattr__(self, "nome", texto_opcional(self.nome))

    def publico(self) -> Mapping[str, Any]:
        return {"id_mascarado": mascarar_id(self.id_externo), "nome": self.nome}


@dataclass(frozen=True)
class ContaMetaDescoberta:
    id_externo: str
    nome: str | None
    status: str | None
    moeda: str | None
    fuso: str | None
    business: BusinessMeta | None = None

    def __post_init__(self) -> None:
        conta = conta_canonica(self.id_externo)
        object.__setattr__(self, "id_externo", conta)
        object.__setattr__(self, "nome", texto_opcional(self.nome))
        object.__setattr__(self, "status", texto_opcional(self.status))
        moeda = texto_opcional(self.moeda)
        if moeda is not None and not re.fullmatch(r"[A-Z]{3}", moeda):
            raise ContratoMetaInvalido("moeda Meta precisa ser ISO-4217")
        object.__setattr__(self, "moeda", moeda)
        object.__setattr__(self, "fuso", texto_opcional(self.fuso))

    @property
    def referencia_opaca(self) -> str:
        return referencia_opaca_conta(self.id_externo)

    @property
    def prontidao_leitura(self) -> str:
        return "READY_FOR_READ"

    def publico(self) -> Mapping[str, Any]:
        return {
            "referencia_opaca": self.referencia_opaca,
            "nome": self.nome or "Conta sem nome",
            "id_mascarado": mascarar_id(self.id_externo),
            "status": self.status,
            "moeda": self.moeda,
            "fuso": self.fuso,
            "business": self.business.publico() if self.business else None,
            "prontidao_leitura": self.prontidao_leitura,
        }


@dataclass(frozen=True)
class ObjetoMeta:
    tipo: str
    id_externo: str
    nome: str | None
    status: str | None
    effective_status: str | None
    parent_id_externo: str | None = None
    objetivo: str | None = None
    optimization_goal: str | None = None
    object_story_id: str | None = None
    creative_id_externo: str | None = None

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS_DE_OBJETO:
            raise ContratoMetaInvalido(f"tipo Meta desconhecido: {self.tipo!r}")
        object.__setattr__(self, "id_externo", id_externo(self.id_externo))
        if self.parent_id_externo is not None:
            object.__setattr__(self, "parent_id_externo", id_externo(
                self.parent_id_externo, campo="parent_id_externo"))
        if self.creative_id_externo is not None:
            object.__setattr__(self, "creative_id_externo", id_externo(
                self.creative_id_externo, campo="creative_id_externo"))


@dataclass(frozen=True)
class LeituraDaHierarquia:
    conta_externa: str
    campanhas: tuple[ObjetoMeta, ...]
    conjuntos: tuple[ObjetoMeta, ...]
    anuncios: tuple[ObjetoMeta, ...]
    criativos: tuple[ObjetoMeta, ...]
    paginas_lidas: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "conta_externa", conta_canonica(self.conta_externa))
        if self.paginas_lidas < 4:
            raise ContratoMetaInvalido(
                "hierarquia completa exige ao menos uma pagina por edge")
        esperados = (
            ("campaign", self.campanhas),
            ("adset", self.conjuntos),
            ("ad", self.anuncios),
            ("creative", self.criativos),
        )
        for tipo, objetos in esperados:
            if any(obj.tipo != tipo for obj in objetos):
                raise ContratoMetaInvalido(f"edge {tipo} recebeu objeto de outro tipo")

    @property
    def contagens(self) -> Mapping[str, int]:
        return {
            "campaign": len(self.campanhas),
            "adset": len(self.conjuntos),
            "ad": len(self.anuncios),
            "creative": len(self.criativos),
        }

    @property
    def objetos(self) -> tuple[ObjetoMeta, ...]:
        return self.campanhas + self.conjuntos + self.anuncios + self.criativos


def hoje_na_conta(fuso: str | None, *, agora: datetime | None = None) -> date:
    """Today as the AD ACCOUNT sees it, never as this host sees it.

    ``date.today()`` answers a question about the machine running the backend.
    An account reporting in ``America/Sao_Paulo`` read from a host in UTC gets
    the wrong day for three hours every night: the collector asks for a day the
    account has not started, receives an empty series, and the dashboard shows a
    measured zero for a day that simply did not exist yet.
    """
    instante = agora or datetime.now(timezone.utc)
    instante_utc(instante, campo="agora")
    nome = texto_opcional(fuso)
    if nome is None:
        raise ContratoMetaInvalido(
            "periodo Meta exige o fuso da conta; nao existe hoje sem fuso")
    try:
        zona = ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ContratoMetaInvalido(f"fuso da conta Meta desconhecido: {nome}") from exc
    return instante.astimezone(zona).date()


def validar_combinacao_de_insight(
    *, nivel: str, breakdown: str, janelas: Sequence[str],
) -> None:
    """Refuse an unsupported level/breakdown/window combination before the call."""
    if nivel not in NIVEIS_DE_INSIGHT:
        raise CombinacaoDeInsightRecusada(f"nivel de insight desconhecido: {nivel!r}")
    if breakdown not in BREAKDOWNS_PERMITIDOS:
        raise CombinacaoDeInsightRecusada(
            f"breakdown fora da allowlist Meta: {breakdown!r}")
    if (nivel, breakdown) in _COMBINACOES_PROIBIDAS:
        raise CombinacaoDeInsightRecusada(
            f"breakdown {breakdown!r} nao e correlacionavel no nivel {nivel!r}")
    for janela in janelas:
        if janela not in JANELAS_DE_ATRIBUICAO:
            raise CombinacaoDeInsightRecusada(
                f"janela de atribuicao fora da allowlist: {janela!r}")
    if len(set(janelas)) != len(tuple(janelas)):
        raise CombinacaoDeInsightRecusada("janela de atribuicao repetida no pedido")


@dataclass(frozen=True)
class PedidoDeInsights:
    """Everything that gives a Meta metric its meaning, decided before the call.

    Two numbers only compare when these fields match.  The request travels with
    the fact precisely so that a later reader can refuse to add two rows that
    were never asked the same question.
    """
    conta_externa: str
    nivel: str
    periodo_inicio: date
    periodo_fim: date
    fuso_da_conta: str
    time_increment: str = "1"
    breakdown: str = "none"
    action_report_time: str = "impression"
    #: Vazio significa "nao pedi janela": a conta decide, e o fato registra
    #: `default`.  NUNCA carimbar uma janela nominal que nao foi solicitada.
    janelas_de_atribuicao: tuple[str, ...] = ()
    limite_por_pagina: int = 100

    def __post_init__(self) -> None:
        object.__setattr__(self, "conta_externa", conta_canonica(self.conta_externa))
        if self.time_increment not in INCREMENTOS_DE_TEMPO:
            raise ContratoMetaInvalido(
                f"time_increment Meta desconhecido: {self.time_increment!r}")
        if self.action_report_time not in INSTANTES_DE_RELATORIO:
            raise ContratoMetaInvalido(
                f"action_report_time desconhecido: {self.action_report_time!r}")
        janelas = tuple(self.janelas_de_atribuicao)
        object.__setattr__(self, "janelas_de_atribuicao", janelas)
        validar_combinacao_de_insight(
            nivel=self.nivel, breakdown=self.breakdown, janelas=janelas)
        if self.periodo_fim < self.periodo_inicio:
            raise ContratoMetaInvalido("periodo de insight invalido")
        fuso = texto_opcional(self.fuso_da_conta)
        if fuso is None:
            raise ContratoMetaInvalido("pedido de insight exige o fuso da conta")
        object.__setattr__(self, "fuso_da_conta", fuso)
        if self.limite_por_pagina < 1 or self.limite_por_pagina > 500:
            raise ContratoMetaInvalido("limite de pagina de insight fora da faixa")
        # Teto LOCAL de seguranca, nao um limite documentado da Meta. Existe para
        # que um periodo digitado errado ("2020-01-01 ate hoje") falhe aqui com
        # uma mensagem util, em vez de virar um HTTP 400 opaco da Graph depois de
        # gastar cota da conta — ou, pior, uma coleta diaria de milhares de
        # linhas disparada sem querer.
        dias = (self.periodo_fim - self.periodo_inicio).days + 1
        teto = MAX_DIAS_POR_PEDIDO.get(self.time_increment, MAX_DIAS_POR_PEDIDO["1"])
        if dias > teto:
            raise ContratoMetaInvalido(
                f"periodo de {dias} dias excede o teto local de {teto} para "
                f"time_increment={self.time_increment}; divida a janela"
            )

    @property
    def janela_declarada(self) -> str:
        """The window label the fact carries.

        With no requested window the label is ``default``: honest about the fact
        that the account decided.  With several, the label is the sorted join —
        two windows are a different grain from either one alone.
        """
        if not self.janelas_de_atribuicao:
            return JANELA_PADRAO_DA_CONTA
        return "+".join(sorted(self.janelas_de_atribuicao))

    def parametros_graph(self) -> dict[str, Any]:
        """Exactly what goes on the wire — this is also what gets recorded."""
        params: dict[str, Any] = {
            "level": self.nivel,
            "time_range": json.dumps(
                {"since": self.periodo_inicio.isoformat(),
                 "until": self.periodo_fim.isoformat()},
                separators=(",", ":"),
            ),
            "time_increment": self.time_increment,
            "action_report_time": self.action_report_time,
            "fields": CAMPOS_DE_INSIGHT,
            "limit": self.limite_por_pagina,
        }
        if self.breakdown != "none":
            params["breakdowns"] = self.breakdown
        if self.janelas_de_atribuicao:
            params["action_attribution_windows"] = json.dumps(
                list(self.janelas_de_atribuicao), separators=(",", ":"))
        return params

    def registro_do_pedido(self) -> dict[str, Any]:
        """Sanitized description of the request, safe to persist and to show."""
        return {
            "nivel": self.nivel,
            "periodo_inicio": self.periodo_inicio.isoformat(),
            "periodo_fim": self.periodo_fim.isoformat(),
            "fuso_da_conta": self.fuso_da_conta,
            "time_increment": self.time_increment,
            "breakdown": self.breakdown,
            "action_report_time": self.action_report_time,
            "janelas_solicitadas": list(self.janelas_de_atribuicao),
            "janela_declarada": self.janela_declarada,
        }


#: Campos pedidos a Graph.  `action_values` e irmao de `actions` e NAO pode ser
#: derivado dele: `actions` conta eventos, `action_values` soma dinheiro.
CAMPOS_DE_INSIGHT = (
    "account_id,campaign_id,adset_id,ad_id,date_start,date_stop,"
    "spend,impressions,reach,frequency,clicks,inline_link_clicks,"
    "cpm,cpc,ctr,actions,action_values"
)


#: `actions` conta EVENTOS; `action_values` soma DINHEIRO do mesmo evento. Sao
#: duas medidas com unidades diferentes: somar as duas, ou tratar uma como a
#: outra, inventa receita. A coluna guarda qual das duas a linha carrega.
MEDIDAS_DE_ACTION = ("count", "value")


@dataclass(frozen=True)
class AcaoInsightMeta:
    action_type: str
    value: Decimal | int | str | None
    attribution_window: str
    object_level: str
    date_start: date
    date_stop: date
    #: "count" para `actions`, "value" para `action_values`.
    medida: str = "count"

    def __post_init__(self) -> None:
        if not self.action_type.strip() or not self.attribution_window.strip():
            raise ContratoMetaInvalido("acao de insight incompleta")
        if self.object_level not in NIVEIS_DE_INSIGHT:
            raise ContratoMetaInvalido("nivel de insight desconhecido")
        if self.medida not in MEDIDAS_DE_ACTION:
            raise ContratoMetaInvalido(f"medida de action desconhecida: {self.medida!r}")
        if self.date_stop < self.date_start:
            raise ContratoMetaInvalido("periodo de action invalido")
        if self.value is not None:
            object.__setattr__(self, "value", decimal_opcional(self.value, campo="action.value"))


@dataclass(frozen=True)
class InsightMeta:
    provider: str
    conta_externa: str
    nivel: str
    objeto_externo: str
    periodo_inicio: date
    periodo_fim: date
    janela_atribuicao: str
    breakdown: str
    observado_em: datetime
    spend: Decimal | int | str | None = None
    impressions: int | None = None
    reach: int | None = None
    frequency: Decimal | int | str | None = None
    clicks: int | None = None
    inline_link_clicks: int | None = None
    landing_page_views: int | None = None
    cpm: Decimal | int | str | None = None
    cpc: Decimal | int | str | None = None
    ctr: Decimal | int | str | None = None
    actions: tuple[AcaoInsightMeta, ...] = ()
    #: Valores monetarios por action_type, separados de `actions` de proposito.
    action_values: tuple[AcaoInsightMeta, ...] = ()
    # --- grao do pedido, sem o qual a metrica nao tem significado (T05) ------
    time_increment: str = "1"
    action_report_time: str = "impression"
    fuso_da_conta: str | None = None
    #: Janelas efetivamente SOLICITADAS. Vazio significa "a conta decidiu", e
    #: nesse caso `janela_atribuicao` vale `default`.
    janelas_solicitadas: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.provider != META_ADS:
            raise ContratoMetaInvalido("provider de insight precisa ser META_ADS")
        if self.time_increment not in INCREMENTOS_DE_TEMPO:
            raise ContratoMetaInvalido(
                f"time_increment de insight desconhecido: {self.time_increment!r}")
        if self.action_report_time not in INSTANTES_DE_RELATORIO:
            raise ContratoMetaInvalido(
                f"action_report_time de insight desconhecido: {self.action_report_time!r}")
        object.__setattr__(self, "janelas_solicitadas", tuple(self.janelas_solicitadas))
        for janela in self.janelas_solicitadas:
            if janela not in JANELAS_DE_ATRIBUICAO:
                raise ContratoMetaInvalido(
                    f"janela solicitada fora da allowlist: {janela!r}")
        # A etiqueta nao pode prometer uma janela que nao foi pedida.
        esperada = ("+".join(sorted(self.janelas_solicitadas))
                    if self.janelas_solicitadas else JANELA_PADRAO_DA_CONTA)
        if self.janela_atribuicao != esperada:
            raise ContratoMetaInvalido(
                "janela_atribuicao precisa refletir as janelas solicitadas: "
                f"{self.janela_atribuicao!r} != {esperada!r}")
        object.__setattr__(self, "conta_externa", conta_canonica(self.conta_externa))
        if self.nivel not in NIVEIS_DE_INSIGHT:
            raise ContratoMetaInvalido("nivel de insight desconhecido")
        if self.nivel != "account":
            object.__setattr__(self, "objeto_externo", id_externo(self.objeto_externo, campo="objeto_externo"))
        elif not str(self.objeto_externo).strip():
            raise ContratoMetaInvalido("objeto account vazio")
        if self.periodo_fim < self.periodo_inicio:
            raise ContratoMetaInvalido("periodo de insight invalido")
        instante_utc(self.observado_em, campo="observado_em")
        for campo in ("spend", "frequency", "cpm", "cpc", "ctr"):
            object.__setattr__(self, campo, decimal_opcional(getattr(self, campo), campo=campo))
        for campo in ("impressions", "reach", "clicks", "inline_link_clicks", "landing_page_views"):
            valor = getattr(self, campo)
            if valor is not None and int(valor) < 0:
                raise ContratoMetaInvalido(f"{campo} nao pode ser negativo")
        if any(a.medida != "count" for a in self.actions):
            raise ContratoMetaInvalido("actions so aceita medida de contagem")
        if any(a.medida != "value" for a in self.action_values):
            raise ContratoMetaInvalido("action_values so aceita medida de valor")

    @property
    def grao(self) -> tuple[Any, ...]:
        """The identity two rows must share before anyone may compare them."""
        return (
            self.provider, self.conta_externa, self.nivel, self.objeto_externo,
            self.periodo_inicio, self.periodo_fim, self.janela_atribuicao,
            self.breakdown, self.time_increment, self.action_report_time,
            self.fuso_da_conta,
        )


@dataclass(frozen=True)
class ResultadoDeInsights:
    """A collection result that knows whether it is complete.

    A truncated page and an account with nothing to report produce the same
    empty-ish shape unless completeness is carried explicitly.  ``completo``
    exists so a watermark never advances over a window that was only partly
    read, and so a dashboard can say "partial" instead of drawing a zero.
    """
    pedido: PedidoDeInsights
    insights: tuple[InsightMeta, ...]
    paginas_lidas: int
    completo: bool = True
    motivo_incompleto: str | None = None

    def __post_init__(self) -> None:
        if self.paginas_lidas < 0:
            raise ContratoMetaInvalido("paginas lidas nao pode ser negativa")
        if self.completo and self.motivo_incompleto:
            raise ContratoMetaInvalido("resultado completo nao carrega motivo")
        if not self.completo and not self.motivo_incompleto:
            raise ContratoMetaInvalido("resultado incompleto precisa de motivo")
        for insight in self.insights:
            if insight.grao[2] != self.pedido.nivel:
                raise ContratoMetaInvalido(
                    "resultado mistura nivel diferente do pedido")


@dataclass(frozen=True)
class ReciboDeSync:
    run_id: str
    chave_de_idempotencia: str
    conta_externa: str
    resultado: str
    iniciado_em: datetime
    concluido_em: datetime
    contagens: Mapping[str, int]
    paginas_lidas: int
    erro_codigo: str | None = None
    erro_mensagem: str | None = None
    repetido: bool = False

    def __post_init__(self) -> None:
        uuid.UUID(self.run_id)
        conta_canonica(self.conta_externa)
        instante_utc(self.iniciado_em, campo="iniciado_em")
        instante_utc(self.concluido_em, campo="concluido_em")
        if self.resultado not in ESTADOS_DE_SYNC:
            raise ContratoMetaInvalido("resultado de sync desconhecido")
        if self.concluido_em < self.iniciado_em:
            raise ContratoMetaInvalido("sync terminou antes de comecar")
        if self.paginas_lidas < 0 or any(v < 0 for v in self.contagens.values()):
            raise ContratoMetaInvalido("contagem de sync nao pode ser negativa")
        if self.resultado == "ok" and (self.erro_codigo or self.erro_mensagem):
            raise ContratoMetaInvalido("sync ok nao carrega erro")
        if self.resultado == "falhou" and not self.erro_codigo:
            raise ContratoMetaInvalido("sync falho precisa de codigo seguro")


def validar_documento_seguro(documento: Mapping[str, Any] | Sequence[Any]) -> None:
    """Use the Cofre's recursive key blocklist at the Meta boundary."""
    try:
        recusar_chave_sensivel(documento, "meta")
    except PayloadRecusado as exc:
        raise ContratoMetaInvalido(str(exc)) from None
