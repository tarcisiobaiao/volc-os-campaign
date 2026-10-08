"""Contrato das decisões de Search que o `Brief` ainda não carrega.

## Por que este módulo existe, e por que fora de `brief.py`

O `Brief` é de todos os canais e tem outros donos em paralelo. As decisões
abaixo só existem em Search — estratégia de lance além de MANUAL/MaxConv,
rede com Display expansion, AI Max inteiro, fixação de RSA, programação,
dispositivo, tipo de geo, meta de conversão — e cada uma muda o payload. Elas
viajam como argumento OPCIONAL de `search.construir(configuracao=…)`:

  - `configuracao=None` é o chamador antigo, e o payload dele não muda (há
    teste comparando byte a byte com `comum.op_campanha`).
  - `configuracao` declarada é o chamador novo, e aí NÃO existe default
    escondido: a rede, por exemplo, deixa de herdar `REDE_LEGADA_SEARCH` e
    passa a ser exigida (ver `resolver_rede`).

## Duas camadas de recusa

1. **Forma** — `__post_init__` levanta `ValueError`, como `RedeDePesquisa` e
   `ConfiguracaoDemandGen` já fazem. Combinação que nenhuma conta aceitaria
   (TIS sem teto, tROAS em MaxConv, path2 sem path1) não chega a existir.
2. **Contexto** — `checar()` precisa do brief (nomes de grupo, texto final das
   headlines, país, estratégia que o brief já declarou) e registra achado no
   `validacao.Resultado`, como o resto do construtor.

⚠️ **Stdlib pura, de propósito.** A rota HTTP monta isto a partir do JSON do
front e o backend não importa o SDK do Google no boot. Os enums da API viram
tuplas fechadas aqui, e `testes_search.py` prova que cada tupla é subconjunto
do enum real da v25 — se a API renomear um valor, o teste quebra antes do
mutate.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import TYPE_CHECKING, Sequence

from ..referencia import geo as _geo

if TYPE_CHECKING:  # pragma: no cover
    from . import validacao
    from .brief import Brief

# ═══════════════════════════════════════════════════════════════════════════
# VOCABULÁRIO FECHADO (espelho dos enums v25 — conferido em teste)
# ═══════════════════════════════════════════════════════════════════════════

#: Estratégias que Search sabe montar. `TARGET_SPEND` é o nome de tela; no
#: proto o ramo do oneof é `target_spend` (o Google nunca renomeou o campo).
ESTRATEGIAS: tuple[str, ...] = (
    "MANUAL_CPC",
    "TARGET_SPEND",
    "MAXIMIZE_CONVERSIONS",
    "MAXIMIZE_CONVERSION_VALUE",
    "TARGET_IMPRESSION_SHARE",
)

#: O que Search monta só com `Brief.estrategia_lance` (+ `tcpa`/`target_roas`
#: do brief), sem `LanceSearch`. TARGET_IMPRESSION_SHARE fica de fora porque
#: exige local, fração e teto — que só `LanceSearch` carrega.
ESTRATEGIAS_PELO_BRIEF: tuple[str, ...] = (
    "MANUAL_CPC",
    "TARGET_SPEND",
    "MAXIMIZE_CONVERSIONS",
    "MAXIMIZE_CONVERSION_VALUE",
)

#: Smart Bidding de verdade: o lance é decidido por conversão prevista. É o
#: único regime em que keyword larga (BROAD, ou AI Max com correspondência de
#: termos) tem sinal de leilão que filtre a consulta — a mesma doutrina de
#: `Brief.__post_init__`, estendida às estratégias novas. MaxClicks e TIS são
#: automáticos mas cegos para conversão: compram clique/posição, não resultado.
LANCE_POR_CONVERSAO: frozenset[str] = frozenset(
    {"MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE"})

#: Onde o ajuste de lance (horário, dispositivo ≠ exclusão) MORDE. Smart
#: Bidding ignora ajuste manual, exceto dispositivo em -100%; TIS também
#: decide sozinho. Aceitar o número nesses regimes seria uma caixa que o
#: operador preenche e que não faz nada.
LANCE_ACEITA_AJUSTE: frozenset[str] = frozenset({"MANUAL_CPC", "TARGET_SPEND"})

LOCAIS_DE_IMPRESSAO: tuple[str, ...] = (
    "ANYWHERE_ON_PAGE", "TOP_OF_PAGE", "ABSOLUTE_TOP_OF_PAGE")

GEO_POSITIVO: tuple[str, ...] = ("PRESENCE", "PRESENCE_OR_INTEREST", "SEARCH_INTEREST")
GEO_NEGATIVO: tuple[str, ...] = ("PRESENCE", "PRESENCE_OR_INTEREST")

DIAS: tuple[str, ...] = (
    "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
#: `MinuteOfHourEnum` só tem os quartos de hora.
MINUTOS: dict[int, str] = {0: "ZERO", 15: "FIFTEEN", 30: "THIRTY", 45: "FORTY_FIVE"}

DISPOSITIVOS: tuple[str, ...] = ("MOBILE", "TABLET", "DESKTOP")

POSICOES_TITULO: tuple[str, ...] = ("HEADLINE_1", "HEADLINE_2", "HEADLINE_3")
POSICOES_DESCRICAO: tuple[str, ...] = ("DESCRIPTION_1", "DESCRIPTION_2")

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

# ── limites da API (v25) ────────────────────────────────────────────────────
MAX_PATH = 15                  # ResponsiveSearchAdInfo.path1/path2
MAX_FAIXAS_POR_DIA = 6         # AdScheduleInfo: 6 por dia e por campanha
AJUSTE_MIN, AJUSTE_MAX = 0.1, 10.0   # bid_modifier: -90% a +900%
from .brief import ROAS_MAX, ROAS_MIN  # noqa: E402 — a faixa é dos 4 canais
MAX_TERMOS_EXCLUIDOS, MAX_CHARS_TERMO = 25, 30          # text_guidelines
MAX_RESTRICOES, MAX_CHARS_RESTRICAO = 40, 300

#: Id temporário da meta personalizada criada no mesmo mutate. Fica fora de
#: todas as faixas de `comum.py` (a última termina em -399). ⚠️ A tabela de
#: faixas mora lá e este módulo não pode editá-la nesta entrega; quem tocar
#: `comum.py` depois deve absorver esta linha na tabela, para continuar
#: existindo UM lugar que diz quem ocupa cada número.
T_META_PERSONALIZADA = -400

_RN_LISTA_DE_MARCA = re.compile(r"^customers/(\d+)/sharedSets/(-?\d+)$")
_RN_META = re.compile(r"^customers/(\d+)/customConversionGoals/(\d+)$")
_RN_ACAO = re.compile(r"^customers/(\d+)/conversionActions/(\d+)$")


def _exigir(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def _positivo(valor: float | None, nome: str) -> None:
    if valor is not None:
        _exigir(valor > 0, f"{nome} precisa ser positivo; ausência é None, nunca 0")


# ═══════════════════════════════════════════════════════════════════════════
# 1. LANCE
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class LanceSearch:
    """Estratégia de lance da campanha, com só os campos que ELA tem.

    Cada campo pertence a exatamente uma estratégia, e um campo preenchido na
    estratégia errada é recusado em vez de ignorado — o defeito que isso evita
    é o operador digitar um tCPA numa campanha MaxClicks e achar que ele vale.

        MANUAL_CPC                 nada (eCPC fica desligado — ver comum.py)
        TARGET_SPEND            teto_cpc opcional  → target_spend.cpc_bid_ceiling_micros
        MAXIMIZE_CONVERSIONS       target_cpa opcional → maximize_conversions.target_cpa_micros
        MAXIMIZE_CONVERSION_VALUE  target_roas opcional → maximize_conversion_value.target_roas
        TARGET_IMPRESSION_SHARE    local + fração + teto, os TRÊS obrigatórios
                                   → target_impression_share.{location,
                                     location_fraction_micros, cpc_bid_ceiling_micros}

    ⚠️ `teto_cpc` NÃO existe em MaxConv/MaxConvValue padrão: o proto diz
    "Mutable for portfolio bidding strategies only". Portfólio não é desta
    entrega, então o teto ali é recusado em vez de virar erro remoto.

    ⚠️ TIS sem teto foi provado no `validate_only` (08/10/2026):
    `field_error.REQUIRED @ target_impression_share.cpc_bid_ceiling_micros`.
    """

    estrategia: str
    target_cpa: float | None = None
    target_roas: float | None = None
    teto_cpc: float | None = None
    local_impressao: str | None = None
    fracao_impressao: float | None = None

    def __post_init__(self) -> None:
        e = self.estrategia
        _exigir(e in ESTRATEGIAS,
                f"estratégia {e!r} não existe em Search — use {', '.join(ESTRATEGIAS)}")
        _positivo(self.target_cpa, "target_cpa")
        _positivo(self.teto_cpc, "teto_cpc")
        if self.target_cpa is not None:
            _exigir(e == "MAXIMIZE_CONVERSIONS",
                    f"target_cpa só existe em MAXIMIZE_CONVERSIONS, não em {e}")
        if self.target_roas is not None:
            _exigir(e == "MAXIMIZE_CONVERSION_VALUE",
                    f"target_roas só existe em MAXIMIZE_CONVERSION_VALUE, não em {e}")
            _exigir(ROAS_MIN <= self.target_roas <= ROAS_MAX,
                    f"target_roas {self.target_roas} fora de [{ROAS_MIN}, {ROAS_MAX}] "
                    f"— a razão é 4.0 para 400%; ausência de meta é None")
        if self.teto_cpc is not None:
            _exigir(e in ("TARGET_SPEND", "TARGET_IMPRESSION_SHARE"),
                    f"teto_cpc não se aplica a {e}: em MaxConv/MaxConvValue o "
                    f"teto só é mutável em estratégia de portfólio")
        tis = e == "TARGET_IMPRESSION_SHARE"
        if tis:
            _exigir(self.local_impressao in LOCAIS_DE_IMPRESSAO,
                    f"TARGET_IMPRESSION_SHARE exige local_impressao em "
                    f"{LOCAIS_DE_IMPRESSAO}")
            _exigir(self.fracao_impressao is not None
                    and 0 < self.fracao_impressao <= 1,
                    "TARGET_IMPRESSION_SHARE exige fracao_impressao em (0, 1] — "
                    "0.6 é 60% das impressões possíveis")
            _exigir(self.teto_cpc is not None,
                    "TARGET_IMPRESSION_SHARE exige teto_cpc: a API recusa sem "
                    "cpc_bid_ceiling_micros, e sem teto a estratégia paga "
                    "qualquer CPC pela posição")
        else:
            _exigir(self.local_impressao is None and self.fracao_impressao is None,
                    f"local/fração de impressão só existem em "
                    f"TARGET_IMPRESSION_SHARE, não em {e}")

    @property
    def por_conversao(self) -> bool:
        return self.estrategia in LANCE_POR_CONVERSAO

    @property
    def fracao_micros(self) -> int | None:
        if self.fracao_impressao is None:
            return None
        return int(round(self.fracao_impressao * 1_000_000))


# ═══════════════════════════════════════════════════════════════════════════
# 2. REDE
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RedeSearch:
    """As três chaves de `network_settings`, todas sem default.

    Diferente de `brief.RedeDePesquisa`, esta aceita `display_expansion=True`
    — e a diferença é a razão de existir. Lá a expansão é proibida "enquanto
    ninguém tiver escrito o que ela significa para verba, lance e medição".
    Escrito aqui:

    - **verba**: o mesmo orçamento diário serve Search e Display; o Google
      só expande quando prevê que a pesquisa não gasta tudo.
    - **lance**: o mesmo; Display passa a receber o CPC da campanha.
    - **medição**: `segments.ad_network_type = CONTENT` separa no relatório;
      o RPM de quem chega por Display é outro e precisa ser lido à parte.

    Ligar continua sendo exceção: o construtor emite AVISO toda vez, para que
    a decisão apareça no plano aprovado.

    `target_partner_search_network` fica de fora: é inventário de parceiro
    Google restrito a contas habilitadas (`CANNOT_TARGET_PARTNER_SEARCH_NETWORK`).
    """

    google_search: bool
    parceiros: bool
    display_expansion: bool

    def __post_init__(self) -> None:
        _exigir(self.google_search is True,
                "uma campanha SEARCH sem google_search não é uma campanha Search")
        for nome in ("parceiros", "display_expansion"):
            _exigir(isinstance(getattr(self, nome), bool),
                    f"rede.{nome} precisa ser bool declarado, não {getattr(self, nome)!r}")


# ═══════════════════════════════════════════════════════════════════════════
# 3. AI MAX
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AiMaxSearch:
    """AI Max para Search, com cada automação declarada — nunca herdada.

    Presente = `campaign.ai_max_setting.enable_ai_max = True`. Ausente (com
    configuração declarada) = `False` explícito e as duas automações em
    `OPTED_OUT`, também explícitas.

    Campo a campo (guia "AI Max for Search — getting started", v25):

    - `correspondencia_de_termos` → `AdGroup.ai_max_ad_group_setting.
      disable_search_term_matching` (invertido), emitido em TODO ad group.
      Ligada, toda keyword vira broad na prática — por isso exige lance por
      conversão (`checar`). `grupos_sem_correspondencia` desliga só nos grupos
      citados, para manter um grupo de marca exato dentro da mesma campanha.
    - `personalizacao_de_texto` → `asset_automation_settings`
      `TEXT_ASSET_AUTOMATION` OPTED_IN/OUT (era "ACA").
    - `expansao_de_url_final` → `FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION`.
      A API exige texto em OPTED_IN junto (`OPERATION_NOT_PERMITTED_FOR_CONTEXT`).
      Para arbitragem é a automação mais perigosa: manda o clique para página
      sem anúncio GAM. Por isso `exclusoes_de_url` existe.
    - `exclusoes_de_url` → `CampaignCriterion.webpage`, `negative=True`, uma
      condição `URL CONTAINS` por item (ex.: "/blog/", "/contato").
    - `listas_de_marca_incluidas/excluidas` → `CampaignCriterion.brand_list.
      shared_set` (SharedSet tipo BRANDS), `negative` False/True. A API só
      anexa lista de marca em Search com AI Max ligado
      (`CANNOT_ATTACH_BRAND_LIST_TO_NON_QUALIFIED_SEARCH_CAMPAIGN`); aqui isso
      é estrutural, porque a lista só existe dentro deste objeto.
    - `termos_excluidos` / `restricoes_de_mensagem` → `campaign.text_guidelines`.
      Só guiam texto GERADO; sem personalização de texto não fazem nada e são
      recusados.
    """

    correspondencia_de_termos: bool
    personalizacao_de_texto: bool
    expansao_de_url_final: bool
    grupos_sem_correspondencia: tuple[str, ...] = ()
    exclusoes_de_url: tuple[str, ...] = ()
    listas_de_marca_incluidas: tuple[str, ...] = ()
    listas_de_marca_excluidas: tuple[str, ...] = ()
    termos_excluidos: tuple[str, ...] = ()
    restricoes_de_mensagem: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for nome in ("correspondencia_de_termos", "personalizacao_de_texto",
                     "expansao_de_url_final"):
            _exigir(isinstance(getattr(self, nome), bool),
                    f"ai_max.{nome} precisa ser bool declarado: o default da API "
                    f"não é decisão de ninguém")
        if self.expansao_de_url_final:
            _exigir(self.personalizacao_de_texto,
                    "expansão de URL final exige personalização de texto ligada — "
                    "a API recusa com OPERATION_NOT_PERMITTED_FOR_CONTEXT")
        if self.grupos_sem_correspondencia:
            _exigir(self.correspondencia_de_termos,
                    "grupos_sem_correspondencia só faz sentido com a "
                    "correspondência ligada na campanha")
        if self.exclusoes_de_url:
            _exigir(self.expansao_de_url_final,
                    "exclusão de URL sem expansão de URL final não exclui nada: "
                    "sem a expansão o clique só vai para a URL declarada")
            for u in self.exclusoes_de_url:
                _exigir(bool(u.strip()) and not any(ch.isspace() for ch in u),
                        f"exclusão de URL {u!r} vazia ou com espaço")
            _sem_repeticao(self.exclusoes_de_url, "exclusoes_de_url")
        for nome in ("listas_de_marca_incluidas", "listas_de_marca_excluidas"):
            for rn in getattr(self, nome):
                _exigir(bool(_RN_LISTA_DE_MARCA.match(rn)),
                        f"{nome}: {rn!r} não é resource name de SharedSet "
                        f"(customers/<cid>/sharedSets/<id>)")
            _sem_repeticao(getattr(self, nome), nome)
        cruz = set(self.listas_de_marca_incluidas) & set(self.listas_de_marca_excluidas)
        _exigir(not cruz, f"lista de marca incluída E excluída: {sorted(cruz)}")
        if self.termos_excluidos or self.restricoes_de_mensagem:
            _exigir(self.personalizacao_de_texto,
                    "termos excluídos/restrições de mensagem só guiam texto "
                    "gerado — sem personalização de texto não fazem nada")
        _exigir(len(self.termos_excluidos) <= MAX_TERMOS_EXCLUIDOS,
                f"no máximo {MAX_TERMOS_EXCLUIDOS} termos excluídos")
        for t in self.termos_excluidos:
            _exigir(0 < len(t.strip()) <= MAX_CHARS_TERMO,
                    f"termo excluído {t!r}: 1 a {MAX_CHARS_TERMO} caracteres")
        _sem_repeticao(self.termos_excluidos, "termos_excluidos")
        _exigir(len(self.restricoes_de_mensagem) <= MAX_RESTRICOES,
                f"no máximo {MAX_RESTRICOES} restrições de mensagem")
        for t in self.restricoes_de_mensagem:
            _exigir(0 < len(t.strip()) <= MAX_CHARS_RESTRICAO,
                    f"restrição de mensagem: 1 a {MAX_CHARS_RESTRICAO} caracteres")
        _sem_repeticao(self.restricoes_de_mensagem, "restricoes_de_mensagem")

    def correspondencia_no_grupo(self, nome: str) -> bool:
        if not self.correspondencia_de_termos:
            return False
        fora = {g.strip().casefold() for g in self.grupos_sem_correspondencia}
        return nome.strip().casefold() not in fora


def _sem_repeticao(itens: Sequence[str], nome: str) -> None:
    vistos: set[str] = set()
    for i in itens:
        k = i.strip().casefold()
        _exigir(k not in vistos, f"{nome}: {i!r} repetido")
        vistos.add(k)


#: O que `ai_max=True` (flag antiga, sem configuração) significa — exatamente
#: o default da API ao ligar AI Max em Search: só a correspondência de termos,
#: as duas automações de asset desligadas. Agora com nome e emitido explícito.
AI_MAX_LEGADO = AiMaxSearch(
    correspondencia_de_termos=True,
    personalizacao_de_texto=False,
    expansao_de_url_final=False,
)


# ═══════════════════════════════════════════════════════════════════════════
# 4. RSA
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Fixacao:
    """Um texto da copy preso a uma posição (`AdTextAsset.pinned_field`).

    Por TEXTO e não por índice: `conteudo.forma` pode descartar um item da
    copy antes do payload, e um índice passaria a apontar para o vizinho.
    """

    texto: str
    posicao: str

    def __post_init__(self) -> None:
        _exigir(self.posicao in POSICOES_TITULO + POSICOES_DESCRICAO,
                f"posição {self.posicao!r} inválida — use "
                f"{', '.join(POSICOES_TITULO + POSICOES_DESCRICAO)}")
        _exigir(bool(self.texto.strip()), "fixação sem texto")

    @property
    def de_titulo(self) -> bool:
        return self.posicao in POSICOES_TITULO


@dataclass(frozen=True)
class AnuncioSearch:
    """Caminho exibido e fixações do RSA.

    `path2` sem `path1` é recusado: o Google exibe `dominio/path1/path2` e o
    segundo segmento sozinho não tem onde aparecer.
    """

    path1: str = ""
    path2: str = ""
    fixacoes: tuple[Fixacao, ...] = ()

    def __post_init__(self) -> None:
        for nome in ("path1", "path2"):
            v = getattr(self, nome)
            _exigir(len(v) <= MAX_PATH, f"{nome} {v!r}: máximo {MAX_PATH} caracteres")
            _exigir(v == v.strip() and "/" not in v and "\n" not in v,
                    f"{nome} {v!r}: sem barra, quebra ou espaço nas pontas")
        _exigir(not self.path2 or bool(self.path1), "path2 exige path1")
        _sem_repeticao([f.texto for f in self.fixacoes], "fixacoes")


# ═══════════════════════════════════════════════════════════════════════════
# 5. PROGRAMAÇÃO E DISPOSITIVO
# ═══════════════════════════════════════════════════════════════════════════


def _hora(valor: str, *, fim: bool) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{2}):(\d{2})", valor or "")
    _exigir(m is not None, f"horário {valor!r} fora do formato HH:MM")
    h, mi = int(m.group(1)), int(m.group(2))
    _exigir(mi in MINUTOS, f"horário {valor!r}: minutos só em 00, 15, 30 ou 45")
    teto = 24 if fim else 23
    _exigir(0 <= h <= teto, f"horário {valor!r}: hora de 0 a {teto}")
    _exigir(not (h == 24 and mi), f"horário {valor!r}: 24 só como 24:00")
    return h, mi


@dataclass(frozen=True)
class FaixaDeHorario:
    """Um `AdScheduleInfo`: dia, início, fim e ajuste opcional de lance.

    `ajuste` é o `bid_modifier` (1.2 = +20%). Só morde em MANUAL_CPC e
    TARGET_SPEND — `checar()` recusa nos outros regimes.
    """

    dia: str
    inicio: str
    fim: str
    ajuste: float | None = None

    def __post_init__(self) -> None:
        _exigir(self.dia in DIAS, f"dia {self.dia!r} inválido — use {DIAS}")
        _exigir(self.minutos_inicio < self.minutos_fim,
                f"faixa {self.dia} {self.inicio}–{self.fim}: início precisa vir antes do fim")
        if self.ajuste is not None:
            _exigir(AJUSTE_MIN <= self.ajuste <= AJUSTE_MAX,
                    f"ajuste {self.ajuste} fora de [{AJUSTE_MIN}, {AJUSTE_MAX}]")

    @property
    def minutos_inicio(self) -> int:
        h, m = _hora(self.inicio, fim=False)
        return h * 60 + m

    @property
    def minutos_fim(self) -> int:
        h, m = _hora(self.fim, fim=True)
        return h * 60 + m


def _checar_programacao(faixas: Sequence[FaixaDeHorario]) -> None:
    por_dia: dict[str, list[FaixaDeHorario]] = {}
    for f in faixas:
        por_dia.setdefault(f.dia, []).append(f)
    for dia, lista in por_dia.items():
        _exigir(len(lista) <= MAX_FAIXAS_POR_DIA,
                f"{dia}: {len(lista)} faixas — a API aceita no máximo "
                f"{MAX_FAIXAS_POR_DIA} por dia")
        lista = sorted(lista, key=lambda f: f.minutos_inicio)
        for a, b in zip(lista, lista[1:]):
            _exigir(a.minutos_fim <= b.minutos_inicio,
                    f"{dia}: faixas {a.inicio}–{a.fim} e {b.inicio}–{b.fim} se sobrepõem")


@dataclass(frozen=True)
class AjusteDeDispositivo:
    """`CampaignCriterion.device` + `bid_modifier`. `fator=0` exclui o dispositivo."""

    dispositivo: str
    fator: float

    def __post_init__(self) -> None:
        _exigir(self.dispositivo in DISPOSITIVOS,
                f"dispositivo {self.dispositivo!r} inválido — use {DISPOSITIVOS}")
        _exigir(self.fator == 0 or AJUSTE_MIN <= self.fator <= AJUSTE_MAX,
                f"fator {self.fator}: 0 (exclui) ou entre {AJUSTE_MIN} e {AJUSTE_MAX}")


# ═══════════════════════════════════════════════════════════════════════════
# 6. GEO, IDIOMA E DATAS
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SegmentacaoGeo:
    """`geo_target_type_setting` + locais e idiomas múltiplos.

    Os dois tipos são OBRIGATÓRIOS porque o default da API é
    `PRESENCE_OR_INTEREST` — e para portal de utilidade pública no Brasil isso
    é pagar clique de quem está fora do país "interessado" no Brasil, com RPM
    de outro país. Quem quer interesse escreve interesse.

    `locais` vazio = o país do brief (`brief.geo_id`). Preenchido, SUBSTITUI o
    país — e todo local precisa pertencer ao país do brief (`checar`): o portão
    país × vertical da política roda por `brief.pais`, e um local de outro país
    passaria por ele sem ser julgado. Multi-país continua sendo N campanhas.

    `idiomas` vazio = o idioma do brief. Preenchido, precisa CONTER o idioma do
    brief: é nele que a copy foi escrita e julgada.
    """

    tipo_positivo: str
    tipo_negativo: str
    locais: tuple[int, ...] = ()
    locais_excluidos: tuple[int, ...] = ()
    idiomas: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _exigir(self.tipo_positivo in GEO_POSITIVO,
                f"tipo_positivo {self.tipo_positivo!r} — use {GEO_POSITIVO}")
        _exigir(self.tipo_negativo in GEO_NEGATIVO,
                f"tipo_negativo {self.tipo_negativo!r} — use {GEO_NEGATIVO}")
        for nome in ("locais", "locais_excluidos"):
            ids = getattr(self, nome)
            _exigir(all(isinstance(i, int) and i > 0 for i in ids),
                    f"{nome}: ids de geoTargetConstant positivos")
            _exigir(len(set(ids)) == len(ids), f"{nome}: id repetido")
        cruz = set(self.locais) & set(self.locais_excluidos)
        _exigir(not cruz, f"local incluído E excluído: {sorted(cruz)}")
        _exigir(len(set(self.idiomas)) == len(self.idiomas), "idioma repetido")


@lru_cache(maxsize=1)
def _geotargets() -> dict[int, tuple[str, str, str, str]]:
    """id → (país, tipo, status, nome canônico), do MESMO CSV de `referencia.geo`."""
    out: dict[int, tuple[str, str, str, str]] = {}
    with zipfile.ZipFile(_geo._GEOTARGETS) as z:
        with z.open(z.namelist()[0]) as fh:
            for linha in csv.DictReader(io.TextIOWrapper(fh, "utf-8")):
                out[int(linha["Criteria ID"])] = (
                    linha["Country Code"].strip().upper(), linha["Target Type"],
                    linha["Status"], linha["Canonical Name"])
    return out


def _data(valor: str, nome: str) -> date:
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{nome} {valor!r} fora do formato AAAA-MM-DD") from None


# ═══════════════════════════════════════════════════════════════════════════
# 7. META DE CONVERSÃO
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class MetaDeCategoria:
    """Um `CampaignConversionGoal` (categoria × origem) e se ele entra no lance."""

    categoria: str
    origem: str
    lance: bool

    def __post_init__(self) -> None:
        _exigir(self.categoria in CATEGORIAS_DE_CONVERSAO,
                f"categoria {self.categoria!r} não existe em ConversionActionCategory")
        _exigir(self.origem in ORIGENS_DE_CONVERSAO,
                f"origem {self.origem!r} não existe em ConversionOrigin")
        _exigir(isinstance(self.lance, bool), "lance precisa ser bool declarado")


@dataclass(frozen=True)
class MetaDeConversao:
    """Para qual conversão ESTA campanha otimiza — o mecanismo certo da v25.

    Conferido no guia `conversions/goals/campaign-goals` e no proto:

    - **Ação específica** = `CustomConversionGoal` (lista de
      `conversion_actions`) aplicada pelo `ConversionGoalCampaignConfig.
      custom_conversion_goal`. É o único caminho que escolhe AÇÃO, e não
      categoria × origem; e vale "regardless of primary_for_goal".
      `meta_personalizada` reaproveita uma meta existente;
      `acoes_de_conversao` cria uma nova no mesmo mutate (id temporário
      `T_META_PERSONALIZADA`).
    - **Categoria × origem** = `CampaignConversionGoal.biddable`, um update por
      par em `categorias`. É o que tira do lance as metas herdadas da conta.

    ⚠️ A meta personalizada SOMA às metas de categoria que continuam biddable.
    Otimizar SÓ pela ação escolhida exige declarar `lance=False` nas categorias
    herdadas — o construtor avisa quando isso não foi feito.

    ⚠️ `selective_optimization` NÃO é isto: é campo de campanha de App.

    Os dois recursos de campanha (`conversionGoalCampaignConfigs/{campanha}` e
    `campaignConversionGoals/{campanha}~{cat}~{origem}`) são endereçados pelo
    id TEMPORÁRIO da campanha no mesmo mutate. O `validate_only` aceitou
    (08/10/2026); a criação real com esse endereçamento ainda não foi provada.
    """

    meta_personalizada: str | None = None
    acoes_de_conversao: tuple[str, ...] = ()
    categorias: tuple[MetaDeCategoria, ...] = ()

    def __post_init__(self) -> None:
        _exigir(bool(self.meta_personalizada or self.acoes_de_conversao
                     or self.categorias),
                "meta de conversão vazia: declare meta_personalizada, "
                "acoes_de_conversao ou categorias — ou não declare a meta")
        _exigir(not (self.meta_personalizada and self.acoes_de_conversao),
                "meta_personalizada OU acoes_de_conversao: as duas juntas "
                "seriam duas metas para o mesmo slot da campanha")
        if self.meta_personalizada:
            _exigir(bool(_RN_META.match(self.meta_personalizada)),
                    f"{self.meta_personalizada!r} não é resource name de "
                    f"CustomConversionGoal")
        for a in self.acoes_de_conversao:
            _exigir(bool(_RN_ACAO.match(a)),
                    f"{a!r} não é resource name de ConversionAction")
        _sem_repeticao(self.acoes_de_conversao, "acoes_de_conversao")
        _sem_repeticao([f"{c.categoria}~{c.origem}" for c in self.categorias],
                       "categorias")

    @property
    def usa_meta_personalizada(self) -> bool:
        return bool(self.meta_personalizada or self.acoes_de_conversao)


# ═══════════════════════════════════════════════════════════════════════════
# A CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ConfiguracaoSearch:
    """Tudo que Search decide além do `Brief`. Cada campo `None`/vazio preserva
    o comportamento de antes desta entrega — exceto a rede, que deixa de ter
    default quando a configuração existe (`resolver_rede`).
    """

    lance: LanceSearch | None = None
    rede: RedeSearch | None = None
    ai_max: AiMaxSearch | None = None
    anuncio: AnuncioSearch | None = None
    programacao: tuple[FaixaDeHorario, ...] = ()
    dispositivos: tuple[AjusteDeDispositivo, ...] = ()
    geo: SegmentacaoGeo | None = None
    inicio: str | None = None
    fim: str | None = None
    meta_de_conversao: MetaDeConversao | None = None

    def __post_init__(self) -> None:
        _checar_programacao(self.programacao)
        vistos = [d.dispositivo for d in self.dispositivos]
        _exigir(len(set(vistos)) == len(vistos), "dispositivo declarado duas vezes")
        _exigir(not (set(vistos) == set(DISPOSITIVOS)
                     and all(d.fator == 0 for d in self.dispositivos)),
                "todos os dispositivos excluídos: a campanha não veicularia em lugar nenhum")
        ini = _data(self.inicio, "inicio") if self.inicio else None
        fim = _data(self.fim, "fim") if self.fim else None
        if ini and fim:
            _exigir(fim >= ini, f"fim {self.fim} antes do início {self.inicio}")

    @property
    def start_date_time(self) -> str | None:
        return f"{self.inicio} 00:00:00" if self.inicio else None

    @property
    def end_date_time(self) -> str | None:
        return f"{self.fim} 23:59:59" if self.fim else None


# ═══════════════════════════════════════════════════════════════════════════
# RESOLUÇÃO E CHECAGEM DE CONTEXTO
# ═══════════════════════════════════════════════════════════════════════════


def resolver_lance(brief: "Brief", cfg: ConfiguracaoSearch | None,
                   r: "validacao.Resultado") -> LanceSearch | None:
    """A estratégia efetiva — do brief (chamador antigo) ou da configuração.

    Com as duas declaradas, divergência é ERRO: precedência silenciosa é o
    defeito que `Brief` já barra em keywords × sub-intenções. `MANUAL_CPC` no
    brief não conta como declaração porque é o default do campo — não há
    como distinguir "escolheu manual" de "não escolheu".
    """
    if cfg is None or cfg.lance is None:
        est = brief.estrategia_lance
        try:
            return LanceSearch(
                estrategia=est,
                target_cpa=(brief.tcpa or None) if est == "MAXIMIZE_CONVERSIONS" else None,
                target_roas=(brief.target_roas or None)
                if est == "MAXIMIZE_CONVERSION_VALUE" else None,
            )
        except ValueError as exc:
            r.erro("estrategia_lance", est, str(exc))
            return None
    lance = cfg.lance
    if brief.estrategia_lance not in ("MANUAL_CPC", lance.estrategia):
        r.erro("estrategia_lance", brief.estrategia_lance,
               f"brief declara {brief.estrategia_lance} e a configuração "
               f"{lance.estrategia} — escolha um lugar só")
    if brief.target_roas and lance.estrategia == "MAXIMIZE_CONVERSION_VALUE" \
            and lance.target_roas != brief.target_roas:
        r.erro("target_roas", brief.target_roas,
               f"brief e configuração divergem no tROAS "
               f"({brief.target_roas} × {lance.target_roas})")
    if brief.tcpa and lance.estrategia == "MAXIMIZE_CONVERSIONS" \
            and lance.target_cpa != brief.tcpa:
        r.erro("tcpa", brief.tcpa,
               f"brief e configuração divergem no tCPA "
               f"({brief.tcpa} × {lance.target_cpa})")
    return lance


def resolver_rede(brief: "Brief", cfg: ConfiguracaoSearch | None,
                  r: "validacao.Resultado") -> RedeSearch | None:
    """`None` = caminho antigo (comum.py aplica brief.rede ou o legado nomeado).

    Com configuração, a rede é OBRIGATÓRIA — dela ou do brief — e as duas
    declaradas precisam concordar.
    """
    if cfg is None:
        # `brief.RedeDePesquisa` aceita a expansão desde 08/10/2026; o aviso
        # vale nos dois caminhos, para a decisão aparecer no plano aprovado.
        if brief.rede is not None and brief.rede.display_expansion:
            r.aviso("rede", "display_expansion", _AVISO_DISPLAY_EXPANSION)
        return None
    do_brief = None
    if brief.rede is not None:
        do_brief = RedeSearch(google_search=brief.rede.google_search,
                              parceiros=brief.rede.search_partners,
                              display_expansion=brief.rede.display_expansion)
    if cfg.rede is None and do_brief is None:
        r.erro("rede", "ausente",
               "com configuração de Search a rede é decisão obrigatória: "
               "declare google_search, parceiros e display_expansion — o "
               "legado com parceiros ligados não vale para chamador novo")
        return None
    if cfg.rede is not None and do_brief is not None and cfg.rede != do_brief:
        r.erro("rede", "divergente",
               f"brief.rede {do_brief} × configuracao.rede {cfg.rede} — "
               f"escolha um lugar só")
        return None
    rede = cfg.rede or do_brief
    if rede.display_expansion:
        r.aviso("rede", "display_expansion", _AVISO_DISPLAY_EXPANSION)
    return rede


_AVISO_DISPLAY_EXPANSION = (
    "Display expansion LIGADA: a mesma verba e o mesmo CPC passam a "
    "comprar inventário de Display. Leia o RPM por "
    "ad_network_type=CONTENT à parte.")


def resolver_ai_max(brief: "Brief", cfg: ConfiguracaoSearch | None,
                    flag: bool, r: "validacao.Resultado") -> AiMaxSearch | None:
    """AI Max efetiva. A flag antiga (`ai_max=True` ou `brief.ai_max`) vira
    `AI_MAX_LEGADO` — o mesmo que a API faria, agora declarado.
    """
    pedida = flag or bool(getattr(brief, "ai_max", False))
    if cfg is not None and cfg.ai_max is not None:
        return cfg.ai_max
    if pedida and cfg is not None:
        r.erro("ai_max", True,
               "com configuração de Search, AI Max se declara em "
               "configuracao.ai_max, com cada automação escolhida — a flag "
               "solta deixaria personalização e expansão de URL no default")
        return None
    return AI_MAX_LEGADO if pedida else None


def checar(
    cfg: ConfiguracaoSearch | None,
    brief: "Brief",
    r: "validacao.Resultado",
    *,
    lance: LanceSearch | None,
    ai_max: AiMaxSearch | None,
    customer_id: str,
    hoje: date | None = None,
) -> None:
    """As recusas que dependem do brief. Não olha a copy — isso é `checar_rsa`."""
    nomes = {s.nome.strip().casefold() for s in brief.grupos()}
    estrategia = lance.estrategia if lance else brief.estrategia_lance

    # tCPA de grupo só existe sob MaxConv. MANUAL_CPC fica de fora de
    # propósito: o payload antigo já levava `target_cpa_micros` no grupo e
    # mudar isso sem configuração quebraria a identidade do selo.
    if lance and estrategia not in ("MAXIMIZE_CONVERSIONS", "MANUAL_CPC"):
        com_tcpa = [s.nome for s in brief.grupos() if s.tcpa] + (
            ["(brief)"] if brief.tcpa else [])
        if com_tcpa:
            r.erro("tcpa", ", ".join(com_tcpa),
                   f"tCPA não existe em {estrategia}: ele iria para o ad group "
                   f"e seria ignorado (ou recusado) pela API")

    # A doutrina do leilão estendida: keyword larga só com lance por conversão.
    if lance and not lance.por_conversao:
        largas = [c.texto for c in brief.criterios
                  if not c.negativa and c.match_type == "BROAD"]
        if largas:
            r.erro("match_type", largas[0],
                   f"{len(largas)} keyword(s) BROAD sob {estrategia}: broad só "
                   f"tem sinal de leilão com lance por conversão")
    if ai_max is not None:
        desconhecidos = [g for g in ai_max.grupos_sem_correspondencia
                         if g.strip().casefold() not in nomes]
        if desconhecidos:
            r.erro("ai_max.grupos_sem_correspondencia", desconhecidos[0],
                   f"grupo inexistente no brief (grupos: {sorted(nomes)})")
        ligada = any(ai_max.correspondencia_no_grupo(s.nome) for s in brief.grupos())
        if ligada and (lance is None or not lance.por_conversao):
            r.erro("ai_max.correspondencia_de_termos", estrategia,
                   f"correspondência de termos da AI Max trata toda keyword "
                   f"como BROAD; sob {estrategia} isso é broad com lance cego. "
                   f"Use MAXIMIZE_CONVERSIONS/VALUE ou desligue a "
                   f"correspondência nos grupos")
        for rn in ai_max.listas_de_marca_incluidas + ai_max.listas_de_marca_excluidas:
            dono = _RN_LISTA_DE_MARCA.match(rn).group(1)
            if dono != customer_id:
                r.erro("ai_max.listas_de_marca", rn,
                       f"lista de marca de outra conta ({dono}); o mutate é em {customer_id}")

    if lance and lance.estrategia == "MAXIMIZE_CONVERSION_VALUE":
        r.aviso("estrategia_lance", "MAXIMIZE_CONVERSION_VALUE",
                "exige ação de conversão primária COM valor; a leitura da conta "
                "(ReciboDeMensuracao) é quem prova — sem valor o lance otimiza zero")

    if cfg is None:
        return

    # ── ajustes que só mordem em lance manual/MaxClicks ─────────────────────
    if estrategia not in LANCE_ACEITA_AJUSTE:
        for f in cfg.programacao:
            if f.ajuste is not None:
                r.erro("programacao.ajuste", f"{f.dia} {f.inicio}",
                       f"ajuste de lance por horário é ignorado em {estrategia}; "
                       f"declare a faixa sem ajuste")
        for d in cfg.dispositivos:
            if d.fator != 0:
                r.erro("dispositivos", d.dispositivo,
                       f"em {estrategia} só a exclusão (fator 0) do dispositivo "
                       f"vale; o ajuste {d.fator} seria ignorado")

    # ── geo e idioma ────────────────────────────────────────────────────────
    if cfg.geo is not None:
        tabela = _geotargets()
        for nome in ("locais", "locais_excluidos"):
            for gid in getattr(cfg.geo, nome):
                linha = tabela.get(gid)
                if linha is None:
                    r.erro(f"geo.{nome}", gid, "id fora da tabela oficial de geotargets")
                    continue
                pais, _tipo, status, canon = linha
                if pais != brief.pais.upper():
                    r.erro(f"geo.{nome}", gid,
                           f"{canon} é de {pais}, e o brief é de {brief.pais}: o "
                           f"portão país × vertical só julgou {brief.pais}")
                elif status != "Active":
                    r.erro(f"geo.{nome}", gid, f"{canon}: status {status}")
        if cfg.geo.idiomas:
            todos = _geo.idiomas()
            for cod in cfg.geo.idiomas:
                i = todos.get(cod)
                if i is None:
                    r.erro("geo.idiomas", cod, "idioma inexistente na API")
                elif not i.segmentavel:
                    r.erro("geo.idiomas", cod, f"{i.nome} não é segmentável")
            if brief.idioma not in cfg.geo.idiomas:
                r.erro("geo.idiomas", brief.idioma,
                       "a lista precisa conter o idioma do brief — é nele que "
                       "a copy foi escrita e julgada")

    # ── datas ───────────────────────────────────────────────────────────────
    hoje = hoje or date.today()
    if cfg.inicio and date.fromisoformat(cfg.inicio) < hoje:
        r.erro("inicio", cfg.inicio, "data de início no passado")
    if cfg.fim and date.fromisoformat(cfg.fim) < hoje:
        r.erro("fim", cfg.fim, "data de fim no passado")

    # ── meta de conversão ───────────────────────────────────────────────────
    meta = cfg.meta_de_conversao
    if meta is not None:
        for rn in ((meta.meta_personalizada,) if meta.meta_personalizada else ()) \
                + meta.acoes_de_conversao:
            dono = rn.split("/")[1]
            if dono != customer_id:
                r.erro("meta_de_conversao", rn,
                       f"recurso da conta {dono}, mutate em {customer_id}: com "
                       f"conversão entre contas, a meta personalizada mora na "
                       f"conta de conversão e não cabe neste mutate")
        if meta.usa_meta_personalizada and not any(
                not c.lance for c in meta.categorias):
            r.aviso("meta_de_conversao", "categorias",
                    "a meta personalizada SOMA às categorias herdadas da conta; "
                    "para otimizar só por ela, declare lance=False nelas")
        if estrategia not in LANCE_POR_CONVERSAO:
            r.aviso("meta_de_conversao", estrategia,
                    f"em {estrategia} a meta só muda a coluna de conversões, não o lance")


def checar_rsa(anuncio: AnuncioSearch | None, headlines: Sequence[str],
               descriptions: Sequence[str], r: "validacao.Resultado") -> dict[str, str]:
    """Liga cada fixação ao texto que de fato vai no payload.

    Devolve texto → posição. Recusa fixação de texto que não sobreviveu à
    forma, e fixação que deixe uma posição obrigatória (título 1 e 2,
    descrição 1) sem candidato — o RSA precisa conseguir montar o anúncio.
    """
    if anuncio is None or not anuncio.fixacoes:
        return {}
    saida: dict[str, str] = {}
    for f in anuncio.fixacoes:
        alvo = headlines if f.de_titulo else descriptions
        if f.texto.strip() not in [t.strip() for t in alvo]:
            r.erro("anuncio.fixacoes", f.texto,
                   "texto fixado não está entre os "
                   f"{'títulos' if f.de_titulo else 'descrições'} do payload")
            continue
        saida[f.texto.strip()] = f.posicao
    for alvo, obrigatorias in ((headlines, POSICOES_TITULO[:2]),
                               (descriptions, POSICOES_DESCRICAO[:1])):
        livres = sum(1 for t in alvo if t.strip() not in saida)
        sem_pino = [p for p in obrigatorias if p not in saida.values()]
        if len(sem_pino) > livres:
            r.erro("anuncio.fixacoes", ", ".join(sem_pino),
                   "posição obrigatória sem texto que possa ocupá-la — todos "
                   "os textos foram fixados em outras posições")
    if saida:
        r.aviso("anuncio.fixacoes", len(saida),
                "fixação reduz as combinações do RSA e a força do anúncio; "
                "fixe só o que é exigência legal ou de marca")
    return saida


# ═══════════════════════════════════════════════════════════════════════════
# FRONTEIRA JSON — a forma que a rota HTTP aceita e o esquema que a tela lê
# ═══════════════════════════════════════════════════════════════════════════
#
# O vocabulário abaixo não é uma segunda lista: cada `enum` REFERENCIA a tupla
# fechada deste módulo, e cada limite referencia a constante. O esquema é
# derivado das anotações de tipo dos dataclasses (`config_json.esquema`); estas
# entradas só acrescentam o que a anotação não carrega.

_HORARIO = r"^([01]\d|2[0-4]):(00|15|30|45)$"

ESQUEMA_JSON: dict[str, dict] = {
    "LanceSearch.estrategia": {"enum": list(ESTRATEGIAS)},
    "LanceSearch.target_cpa": {"exclusiveMinimum": 0,
                               "description": "tCPA em moeda da conta; só em MAXIMIZE_CONVERSIONS"},
    "LanceSearch.target_roas": {"minimum": ROAS_MIN, "maximum": ROAS_MAX,
                                "description": "razão (4.0 = 400%); só em MAXIMIZE_CONVERSION_VALUE"},
    "LanceSearch.teto_cpc": {"exclusiveMinimum": 0,
                             "description": "teto de CPC em moeda da conta; TARGET_SPEND (opcional) e TARGET_IMPRESSION_SHARE (obrigatório)"},
    "LanceSearch.local_impressao": {"enum": list(LOCAIS_DE_IMPRESSAO),
                                    "description": "obrigatório em TARGET_IMPRESSION_SHARE"},
    "LanceSearch.fracao_impressao": {"exclusiveMinimum": 0, "maximum": 1,
                                     "description": "obrigatório em TARGET_IMPRESSION_SHARE (0.6 = 60%)"},
    "RedeSearch.google_search": {"const": True},
    "AiMaxSearch.exclusoes_de_url": {"items": {"minLength": 1, "pattern": r"^\S+$"}},
    "AiMaxSearch.listas_de_marca_incluidas": {"items": {"pattern": _RN_LISTA_DE_MARCA.pattern}},
    "AiMaxSearch.listas_de_marca_excluidas": {"items": {"pattern": _RN_LISTA_DE_MARCA.pattern}},
    "AiMaxSearch.termos_excluidos": {"maxItems": MAX_TERMOS_EXCLUIDOS,
                                     "items": {"minLength": 1, "maxLength": MAX_CHARS_TERMO}},
    "AiMaxSearch.restricoes_de_mensagem": {"maxItems": MAX_RESTRICOES,
                                           "items": {"minLength": 1, "maxLength": MAX_CHARS_RESTRICAO}},
    "Fixacao.posicao": {"enum": list(POSICOES_TITULO + POSICOES_DESCRICAO)},
    "Fixacao.texto": {"minLength": 1},
    "AnuncioSearch.path1": {"maxLength": MAX_PATH, "pattern": r"^[^/\n]*$"},
    "AnuncioSearch.path2": {"maxLength": MAX_PATH, "pattern": r"^[^/\n]*$",
                            "description": "exige path1"},
    "FaixaDeHorario.dia": {"enum": list(DIAS)},
    "FaixaDeHorario.inicio": {"pattern": _HORARIO, "description": "HH:MM, minutos 00/15/30/45"},
    "FaixaDeHorario.fim": {"pattern": _HORARIO, "description": "HH:MM (24:00 = fim do dia)"},
    "FaixaDeHorario.ajuste": {"minimum": AJUSTE_MIN, "maximum": AJUSTE_MAX,
                              "description": "bid_modifier (1.2 = +20%); só em MANUAL_CPC/TARGET_SPEND"},
    "AjusteDeDispositivo.dispositivo": {"enum": list(DISPOSITIVOS)},
    "AjusteDeDispositivo.fator": {"minimum": 0, "maximum": AJUSTE_MAX,
                                  "description": f"0 exclui o dispositivo; senão entre {AJUSTE_MIN} e {AJUSTE_MAX}"},
    "SegmentacaoGeo.tipo_positivo": {"enum": list(GEO_POSITIVO)},
    "SegmentacaoGeo.tipo_negativo": {"enum": list(GEO_NEGATIVO)},
    "SegmentacaoGeo.locais": {"items": {"minimum": 1},
                              "description": "ids de geoTargetConstant do país do brief; vazio = o país"},
    "SegmentacaoGeo.locais_excluidos": {"items": {"minimum": 1}},
    "SegmentacaoGeo.idiomas": {"description": "códigos de idioma; precisa conter o idioma do brief"},
    "ConfiguracaoSearch.programacao": {"description": f"até {MAX_FAIXAS_POR_DIA} faixas por dia, sem sobreposição"},
    "ConfiguracaoSearch.inicio": {"format": "date"},
    "ConfiguracaoSearch.fim": {"format": "date"},
    "MetaDeCategoria.categoria": {"enum": list(CATEGORIAS_DE_CONVERSAO)},
    "MetaDeCategoria.origem": {"enum": list(ORIGENS_DE_CONVERSAO)},
    "MetaDeConversao.meta_personalizada": {"pattern": _RN_META.pattern},
    "MetaDeConversao.acoes_de_conversao": {"items": {"pattern": _RN_ACAO.pattern}},
}


def de_json(dados: dict, caminho: str = "configuracao_search") -> ConfiguracaoSearch:
    """JSON da rota → `ConfiguracaoSearch`. Forma julgada pelo próprio dataclass."""
    from . import config_json

    return config_json.de_dict(ConfiguracaoSearch, dados, caminho)


def esquema_json() -> dict:
    from . import config_json

    return config_json.esquema(ConfiguracaoSearch, metadados=ESQUEMA_JSON,
                               titulo="ConfiguracaoSearch")
