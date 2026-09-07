"""Contrato V2 do plano Meta: campanha + conjuntos[] + anúncios[].

## O que muda em relação ao V1, e por que ele continua vivo

`contrato.PlanoMetaPausado` descreve UMA campanha com UM conjunto, orçamento
diário no conjunto, Brasil inteiro, Facebook-only. Ele não é um rascunho: é a
receita que a Meta aceitou em 05/09/2026, e o snapshot de qualquer aprovação
já emitida foi congelado a partir dele. Reescrevê-lo apagaria a única forma de
descongelar aquelas aprovações.

Então o V1 fica INTACTO, e o V2 nasce ao lado. Um plano V1 continua sendo
decodificado e compilado exatamente pelo mesmo caminho de antes; um plano V2
tem contrato próprio, compilador próprio e — provado em
`backend/tests/test_meta_contrato_v2.py` — produz operação por operação, e o
MESMO `plano_sha256`, quando descreve a mesma campanha que o V1 descrevia.
Essa igualdade é o que autoriza os dois a coexistirem sem que a versão nova
mude o payload de uma aprovação passada.

## O que o V2 acrescenta

- orçamento como UNIÃO DISCRIMINADA: no conjunto (ABO) ou na campanha (CBO),
  diário ou total, nunca nos dois níveis (`F04`);
- N conjuntos com `adset_key` estável, cada um com público, programação e
  posicionamentos próprios (`F10`);
- N anúncios, cada um apontando explicitamente para um `adset_key` (`F34`);
- público de verdade: geografia com inclusões E exclusões, raio, públicos
  personalizados/semelhantes EXISTENTES, idade, idiomas (`F11`..`F19`);
- mensuração com propósito declarado: relatar ou otimizar (`F22`..`F25`).

## O que ele deliberadamente NÃO faz

Não cria público, não envia lista de pessoas, não define conversão nova, não
envia evento CAPI e não inventa enum. Toda referência a objeto da conta é uma
REFERÊNCIA OPACA que só o backend resolve.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

from .contrato import (
    ErroDeNascimentoMeta,
    VariacaoEstaticaMeta,
    _referencia,
    _texto,
    _url_https,
)
from . import receitas


#: Limites OPERACIONAIS do produto, não limites da Meta. Estão aqui para que um
#: erro de laço não vire quarenta POSTs numa conta real.
MAX_CONJUNTOS = 10
MAX_ANUNCIOS_POR_CONJUNTO = 10
MAX_ANUNCIOS_TOTAL = 50

#: Unidades de raio que a Graph documenta para `custom_locations`.
UNIDADES_DE_RAIO: frozenset[str] = frozenset({"mile", "kilometer"})

#: Modos de público. `BROAD` não é "sem targeting": é geografia + idade, sem
#: público personalizado e sem segmentação detalhada.
PUBLICO_AMPLO = "BROAD"
PUBLICO_MANUAL = "MANUAL"
PUBLICO_PERSONALIZADO = "EXISTING_CUSTOM"
PUBLICO_SEMELHANTE = "EXISTING_LOOKALIKE"
MODOS_DE_PUBLICO: frozenset[str] = frozenset({
    PUBLICO_AMPLO, PUBLICO_MANUAL, PUBLICO_PERSONALIZADO, PUBLICO_SEMELHANTE})

#: Posicionamentos. `FACEBOOK_ONLY` é o único com prova nesta lane; `MANUAL`
#: exige lista explícita e identidade compatível por plataforma.
POSICIONAMENTO_FACEBOOK = "FACEBOOK_ONLY"
POSICIONAMENTO_MANUAL = "MANUAL"
MODOS_DE_POSICIONAMENTO: frozenset[str] = frozenset({
    POSICIONAMENTO_FACEBOOK, POSICIONAMENTO_MANUAL})

#: Plataformas que a Graph aceita em `publisher_platforms`. Transcritas do
#: catálogo do SDK v26.0.0; nenhuma foi inventada.
PLATAFORMAS_CONHECIDAS: frozenset[str] = frozenset({
    "facebook", "instagram", "audience_network", "messenger", "threads"})

#: Tipos de fonte de mensuração. `PIXEL` e `DATASET` são coisas DIFERENTES na
#: Meta, e tratá-las como sinônimo faria o backend resolver a referência errada.
FONTE_PIXEL = "PIXEL"
FONTE_DATASET = "DATASET"
TIPOS_DE_FONTE: frozenset[str] = frozenset({FONTE_PIXEL, FONTE_DATASET})

#: Faixa etária que ESTA receita aceita. Não é o limite da Meta (que documenta
#: 13 como mínimo): é o limite do produto, e ampliá-lo em silêncio ampliaria o
#: alcance de campanhas já aprovadas. Mudá-lo exige decisão explícita.
IDADE_MINIMA = 18
IDADE_MAXIMA = 65


def _chave_estavel(valor: str, campo: str) -> str:
    chave = str(valor or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", chave):
        raise ErroDeNascimentoMeta(
            "META_STABLE_KEY_INVALID",
            f"{campo} precisa ser uma chave curta, estavel e opaca",
        )
    return chave


def _inteiro_positivo(valor: Any, campo: str, codigo: str) -> int:
    if not isinstance(valor, int) or isinstance(valor, bool) or valor <= 0:
        raise ErroDeNascimentoMeta(codigo, f"{campo} precisa ser inteiro positivo")
    return valor


@dataclass(frozen=True)
class OrcamentoMeta:
    """Verba autoritativa de UM objeto. Diário OU total, nunca os dois (`F06`).

    ⚠️ `amount_minor` é a unidade menor da moeda REAL — centavos para BRL. Um
    float de reais aqui faria R$10,00 virar 10 centavos, e o erro só apareceria
    na fatura.
    """

    nivel: str
    periodo: str
    amount_minor: int
    currency: str = "BRL"

    def __post_init__(self) -> None:
        if self.nivel not in receitas.NIVEIS_DE_ORCAMENTO:
            raise ErroDeNascimentoMeta(
                "META_BUDGET_LEVEL_INVALID",
                "o orcamento precisa ser do conjunto (ABO) ou da campanha (CBO)",
            )
        if self.periodo not in receitas.PERIODOS_DE_ORCAMENTO:
            raise ErroDeNascimentoMeta(
                "META_BUDGET_PERIOD_INVALID",
                "o orcamento precisa ser diario (DAILY) ou total (LIFETIME)",
            )
        _inteiro_positivo(self.amount_minor, "amount_minor", "META_BUDGET_INVALID")
        if self.currency != "BRL":
            raise ErroDeNascimentoMeta(
                "META_CURRENCY_UNSUPPORTED", "a receita atual esta limitada a contas BRL")

    @property
    def campo_da_graph(self) -> str:
        return "daily_budget" if self.periodo == receitas.PERIODO_DIARIO else "lifetime_budget"


@dataclass(frozen=True)
class ProgramacaoMeta:
    """Início e fim do conjunto, no relógio com fuso (`F09`)."""

    start_time: datetime
    end_time: datetime | None = None

    def __post_init__(self) -> None:
        for campo in ("start_time", "end_time"):
            valor = getattr(self, campo)
            if valor is None:
                continue
            if valor.tzinfo is None or valor.utcoffset() is None:
                raise ErroDeNascimentoMeta(
                    "META_SCHEDULE_INVALID", f"{campo} precisa ter timezone")
        if self.end_time is not None and self.end_time <= self.start_time:
            raise ErroDeNascimentoMeta(
                "META_SCHEDULE_INVALID", "o fim precisa ser depois do inicio")


@dataclass(frozen=True)
class LocalizacaoPorRaio:
    """Ponto + raio, quando a receita e a categoria permitem (`F17`)."""

    latitude: float
    longitude: float
    radius: int
    distance_unit: str = "kilometer"

    def __post_init__(self) -> None:
        for campo, limite in (("latitude", 90.0), ("longitude", 180.0)):
            valor = getattr(self, campo)
            if not isinstance(valor, (int, float)) or isinstance(valor, bool):
                raise ErroDeNascimentoMeta(
                    "META_GEO_RADIUS_INVALID", f"{campo} precisa ser numero")
            if valor != valor or abs(float(valor)) > limite:  # NaN falha no !=
                raise ErroDeNascimentoMeta(
                    "META_GEO_RADIUS_INVALID", f"{campo} fora do intervalo valido")
        _inteiro_positivo(self.radius, "radius", "META_GEO_RADIUS_INVALID")
        if self.distance_unit not in UNIDADES_DE_RAIO:
            raise ErroDeNascimentoMeta(
                "META_GEO_RADIUS_INVALID",
                "a unidade do raio precisa ser mile ou kilometer",
            )

    def payload(self) -> dict[str, Any]:
        return {
            "latitude": float(self.latitude),
            "longitude": float(self.longitude),
            "radius": self.radius,
            "distance_unit": self.distance_unit,
        }


@dataclass(frozen=True)
class GeografiaMeta:
    """Inclusões e exclusões geográficas (`F15`, `F16`, `F17`).

    ⚠️ As chaves de região/cidade/CEP vêm do CATÁLOGO da Meta, resolvidas pelo
    backend. Texto livre nunca vira chave: um "São Paulo" digitado que virasse
    id seria uma segmentação inventada com cara de escolha do operador.
    """

    countries: tuple[str, ...] = ()
    region_keys: tuple[str, ...] = ()
    city_keys: tuple[str, ...] = ()
    zip_keys: tuple[str, ...] = ()
    custom_locations: tuple[LocalizacaoPorRaio, ...] = ()
    excluded_countries: tuple[str, ...] = ()
    excluded_region_keys: tuple[str, ...] = ()
    excluded_city_keys: tuple[str, ...] = ()
    excluded_zip_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for campo in ("countries", "excluded_countries"):
            valores = tuple(dict.fromkeys(getattr(self, campo)))
            if any(not re.fullmatch(r"[A-Z]{2}", str(item)) for item in valores):
                raise ErroDeNascimentoMeta(
                    "META_TARGETING_INVALID", f"{campo} tem codigo de pais invalido")
            object.__setattr__(self, campo, valores)
        for campo in (
            "region_keys", "city_keys", "zip_keys",
            "excluded_region_keys", "excluded_city_keys", "excluded_zip_keys",
        ):
            valores = tuple(dict.fromkeys(str(item) for item in getattr(self, campo)))
            for item in valores:
                # Chave de catálogo da Meta: dígitos, ou dígitos com sufixo de
                # país/estado (ex.: "US:94025"). Nunca texto livre.
                if not re.fullmatch(r"[A-Za-z0-9:_-]{1,64}", item):
                    raise ErroDeNascimentoMeta(
                        "META_GEO_KEY_INVALID",
                        f"{campo} contem chave que nao veio do catalogo",
                    )
            object.__setattr__(self, campo, valores)
        object.__setattr__(
            self, "custom_locations", tuple(self.custom_locations))
        if any(not isinstance(item, LocalizacaoPorRaio) for item in self.custom_locations):
            raise ErroDeNascimentoMeta(
                "META_GEO_RADIUS_INVALID", "localizacao por raio invalida")
        if not self.tem_inclusao:
            raise ErroDeNascimentoMeta(
                "META_GEO_INCLUDE_REQUIRED",
                "escolha ao menos um lugar para alcancar",
            )
        # Excluir exatamente o que se incluiu não é "quase nada": é um conjunto
        # que a Meta recusaria depois do despacho, ou que entregaria zero sem
        # ninguém entender por quê.
        for incluidos, excluidos, nome in (
            (self.countries, self.excluded_countries, "pais"),
            (self.region_keys, self.excluded_region_keys, "regiao"),
            (self.city_keys, self.excluded_city_keys, "cidade"),
            (self.zip_keys, self.excluded_zip_keys, "CEP"),
        ):
            colisao = set(incluidos) & set(excluidos)
            if colisao:
                raise ErroDeNascimentoMeta(
                    "META_GEO_INCLUDE_EXCLUDE_CONFLICT",
                    f"o mesmo {nome} esta incluido e excluido ao mesmo tempo",
                )

    @property
    def tem_inclusao(self) -> bool:
        return bool(
            self.countries or self.region_keys or self.city_keys
            or self.zip_keys or self.custom_locations)

    @property
    def tem_exclusao(self) -> bool:
        return bool(
            self.excluded_countries or self.excluded_region_keys
            or self.excluded_city_keys or self.excluded_zip_keys)

    def _bloco(
        self, paises: Sequence[str], regioes: Sequence[str],
        cidades: Sequence[str], ceps: Sequence[str],
        raios: Sequence[LocalizacaoPorRaio] = (),
    ) -> dict[str, Any]:
        bloco: dict[str, Any] = {}
        if paises:
            bloco["countries"] = list(paises)
        if regioes:
            bloco["regions"] = [{"key": item} for item in regioes]
        if cidades:
            bloco["cities"] = [{"key": item} for item in cidades]
        if ceps:
            bloco["zips"] = [{"key": item} for item in ceps]
        if raios:
            bloco["custom_locations"] = [item.payload() for item in raios]
        return bloco

    def geo_locations(self) -> dict[str, Any]:
        return self._bloco(
            self.countries, self.region_keys, self.city_keys, self.zip_keys,
            self.custom_locations)

    def excluded_geo_locations(self) -> dict[str, Any] | None:
        bloco = self._bloco(
            self.excluded_countries, self.excluded_region_keys,
            self.excluded_city_keys, self.excluded_zip_keys)
        return bloco or None


@dataclass(frozen=True)
class PublicoMeta:
    """O público de UM conjunto (`F11`..`F20`).

    ⚠️ `expansao_advantage` é obrigatoriamente explícito. Desde a v23.0 a
    ausência de `targeting_automation.advantage_audience` faz a Meta assumir 1
    — quer dizer, omitir LIGA a expansão. O contrato não admite omissão.
    """

    modo: str
    geografia: GeografiaMeta
    idade_min: int = IDADE_MINIMA
    idade_max: int = IDADE_MAXIMA
    locale_refs: tuple[str, ...] = ()
    incluir_custom_refs: tuple[str, ...] = ()
    excluir_custom_refs: tuple[str, ...] = ()
    lookalike_refs: tuple[str, ...] = ()
    interesse_refs: tuple[str, ...] = ()
    expansao_advantage: bool = False

    def __post_init__(self) -> None:
        if self.modo not in MODOS_DE_PUBLICO:
            raise ErroDeNascimentoMeta(
                "META_AUDIENCE_MODE_INVALID", "modo de publico desconhecido")
        if not isinstance(self.geografia, GeografiaMeta):
            raise ErroDeNascimentoMeta(
                "META_TARGETING_INVALID", "a geografia do publico e invalida")
        if not isinstance(self.expansao_advantage, bool):
            raise ErroDeNascimentoMeta(
                "META_ADVANTAGE_AUDIENCE_INVALID",
                "a expansao Advantage+ precisa ser True ou False; a omissao a liga",
            )
        for campo in ("idade_min", "idade_max"):
            _inteiro_positivo(getattr(self, campo), campo, "META_TARGETING_INVALID")
        if (self.idade_min < IDADE_MINIMA or self.idade_max > IDADE_MAXIMA
                or self.idade_min > self.idade_max):
            raise ErroDeNascimentoMeta(
                "META_TARGETING_INVALID",
                f"a faixa etaria aceita nesta receita vai de {IDADE_MINIMA} a {IDADE_MAXIMA}",
            )
        for campo in (
            "locale_refs", "incluir_custom_refs", "excluir_custom_refs",
            "lookalike_refs", "interesse_refs",
        ):
            valores = tuple(dict.fromkeys(
                _referencia(str(item), campo) for item in getattr(self, campo)))
            object.__setattr__(self, campo, valores)
        # Um público não pode ser incluído e excluído ao mesmo tempo: a Meta
        # aceitaria, e a entrega seria vazia sem ninguém entender por quê.
        colisao = set(self.incluir_custom_refs + self.lookalike_refs) & set(
            self.excluir_custom_refs)
        if colisao:
            raise ErroDeNascimentoMeta(
                "META_AUDIENCE_INCLUDE_EXCLUDE_CONFLICT",
                "o mesmo publico esta incluido e excluido no mesmo conjunto",
            )
        usa_personalizado = bool(
            self.incluir_custom_refs or self.lookalike_refs or self.excluir_custom_refs)
        if self.modo == PUBLICO_AMPLO and (usa_personalizado or self.interesse_refs):
            raise ErroDeNascimentoMeta(
                "META_AUDIENCE_MODE_CONFLICT",
                "publico amplo nao aceita publicos personalizados nem segmentacao detalhada",
            )
        if self.modo in {PUBLICO_PERSONALIZADO, PUBLICO_SEMELHANTE} and not (
                self.incluir_custom_refs or self.lookalike_refs):
            raise ErroDeNascimentoMeta(
                "META_AUDIENCE_SELECTION_REQUIRED",
                "escolha ao menos um publico existente para este modo",
            )

    @property
    def promete_alcance_exclusivo(self) -> bool:
        """Se a UI pode dizer que só quem está no público será alcançado.

        ⚠️ Com a expansão Advantage+ ligada, NÃO pode. A Meta trata o público
        selecionado como SUGESTÃO e alcança fora dele. Chamar isso de
        remarketing exclusivo seria a tela prometendo o que o provedor não
        garante — exatamente o que `A16` proíbe.
        """
        return bool(self.incluir_custom_refs or self.lookalike_refs) and not self.expansao_advantage

    def targeting(self) -> dict[str, Any]:
        alvo: dict[str, Any] = {
            "geo_locations": self.geografia.geo_locations(),
            "age_min": self.idade_min,
            "age_max": self.idade_max,
        }
        excluidos = self.geografia.excluded_geo_locations()
        if excluidos:
            alvo["excluded_geo_locations"] = excluidos
        if self.locale_refs:
            # Resolvido para inteiros pelo backend; aqui viaja a referência
            # opaca, e o compilador exige a resolução antes de emitir.
            alvo["locales"] = list(self.locale_refs)
        if self.incluir_custom_refs or self.lookalike_refs:
            alvo["custom_audiences"] = [
                {"id": ref} for ref in (self.incluir_custom_refs + self.lookalike_refs)]
        if self.excluir_custom_refs:
            alvo["excluded_custom_audiences"] = [
                {"id": ref} for ref in self.excluir_custom_refs]
        if self.interesse_refs:
            alvo["flexible_spec"] = [
                {"interests": [{"id": ref} for ref in self.interesse_refs]}]
        alvo["targeting_automation"] = {
            "advantage_audience": 1 if self.expansao_advantage else 0}
        return alvo


@dataclass(frozen=True)
class PosicionamentosMeta:
    """Onde o anúncio pode aparecer (`F21`)."""

    modo: str = POSICIONAMENTO_FACEBOOK
    plataformas: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.modo not in MODOS_DE_POSICIONAMENTO:
            raise ErroDeNascimentoMeta(
                "META_PLACEMENT_MODE_INVALID", "modo de posicionamento desconhecido")
        if self.modo == POSICIONAMENTO_FACEBOOK:
            object.__setattr__(self, "plataformas", ("facebook",))
            return
        valores = tuple(dict.fromkeys(str(item).lower() for item in self.plataformas))
        if not valores:
            raise ErroDeNascimentoMeta(
                "META_PLACEMENT_SELECTION_REQUIRED",
                "posicionamento manual exige escolher ao menos uma plataforma",
            )
        desconhecidas = set(valores) - PLATAFORMAS_CONHECIDAS
        if desconhecidas:
            raise ErroDeNascimentoMeta(
                "META_PLACEMENT_PLATFORM_UNKNOWN",
                "plataforma de posicionamento fora do vocabulario da v26",
            )
        object.__setattr__(self, "plataformas", valores)

    @property
    def exige_identidade_instagram(self) -> bool:
        return "instagram" in self.plataformas


@dataclass(frozen=True)
class MensuracaoMeta:
    """Pixel/dataset, evento e conversão personalizada (`F22`..`F26`).

    ⚠️ `proposito` é a distinção que a spec cobra: `REPORT_ONLY` NÃO toca o
    payload do conjunto — é preferência de leitura. `OPTIMIZE` emite
    `promoted_object` e exige que a receita admita otimização por conversão.
    """

    proposito: str = receitas.MENSURACAO_RELATORIO
    source_kind: str | None = None
    source_ref: str | None = None
    custom_conversion_ref: str | None = None
    standard_event: str | None = None
    attribution_spec: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.proposito not in receitas.PROPOSITOS_DE_MENSURACAO:
            raise ErroDeNascimentoMeta(
                "META_MEASUREMENT_PURPOSE_INVALID",
                "o proposito da mensuracao precisa ser REPORT_ONLY ou OPTIMIZE",
            )
        if self.source_kind is not None and self.source_kind not in TIPOS_DE_FONTE:
            raise ErroDeNascimentoMeta(
                "META_MEASUREMENT_SOURCE_KIND_INVALID",
                "a fonte de mensuracao precisa ser PIXEL ou DATASET",
            )
        for campo in ("source_ref", "custom_conversion_ref"):
            valor = getattr(self, campo)
            if valor is not None:
                object.__setattr__(self, campo, _referencia(str(valor), campo))
        if self.source_ref is not None and self.source_kind is None:
            raise ErroDeNascimentoMeta(
                "META_MEASUREMENT_SOURCE_KIND_REQUIRED",
                "informe se a fonte escolhida e um pixel ou um dataset",
            )
        if self.standard_event is not None:
            evento = str(self.standard_event).strip()
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,49}", evento):
                raise ErroDeNascimentoMeta(
                    "META_MEASUREMENT_EVENT_INVALID",
                    "o evento padrao precisa ser um enum da Meta em maiusculas",
                )
            object.__setattr__(self, "standard_event", evento)
        if self.proposito == receitas.MENSURACAO_OTIMIZACAO:
            if self.source_ref is None:
                raise ErroDeNascimentoMeta(
                    "META_MEASUREMENT_SOURCE_REQUIRED",
                    "otimizar por conversao exige escolher o pixel ou dataset da conta",
                )
            if self.custom_conversion_ref is None and self.standard_event is None:
                raise ErroDeNascimentoMeta(
                    "META_MEASUREMENT_EVENT_REQUIRED",
                    "otimizar por conversao exige um evento padrao ou uma conversao personalizada",
                )
            if self.custom_conversion_ref is not None and self.standard_event is not None:
                # A Meta trata `custom_conversion_id` e `custom_event_type`
                # como caminhos distintos; mandar os dois é pedir para o
                # provedor escolher, e a escolha dele não é a do operador.
                raise ErroDeNascimentoMeta(
                    "META_MEASUREMENT_EVENT_AMBIGUOUS",
                    "escolha um evento padrao OU uma conversao personalizada, nao os dois",
                )

    @property
    def altera_payload(self) -> bool:
        return self.proposito == receitas.MENSURACAO_OTIMIZACAO


@dataclass(frozen=True)
class ConjuntoMeta:
    """Um Ad Set com identidade estável (`F10`)."""

    adset_key: str
    nome: str
    programacao: ProgramacaoMeta
    publico: PublicoMeta
    posicionamentos: PosicionamentosMeta = field(default_factory=PosicionamentosMeta)
    mensuracao: MensuracaoMeta = field(default_factory=MensuracaoMeta)
    #: Presente somente em ABO. Em CBO ele é obrigatoriamente `None`, e a
    #: conferência acontece no plano — que é quem conhece os dois níveis.
    orcamento: OrcamentoMeta | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "adset_key", _chave_estavel(self.adset_key, "adset_key"))
        object.__setattr__(self, "nome", _texto(self.nome, "adset_name", maximo=400))
        for campo, tipo in (
            ("programacao", ProgramacaoMeta), ("publico", PublicoMeta),
            ("posicionamentos", PosicionamentosMeta), ("mensuracao", MensuracaoMeta),
        ):
            if not isinstance(getattr(self, campo), tipo):
                raise ErroDeNascimentoMeta(
                    "META_ADSET_INVALID", f"{campo} do conjunto e invalido")
        if self.orcamento is not None:
            if not isinstance(self.orcamento, OrcamentoMeta):
                raise ErroDeNascimentoMeta(
                    "META_BUDGET_INVALID", "o orcamento do conjunto e invalido")
            if self.orcamento.nivel != receitas.ORCAMENTO_NO_CONJUNTO:
                raise ErroDeNascimentoMeta(
                    "META_BUDGET_LEVEL_MISMATCH",
                    "o orcamento anexado ao conjunto precisa ser de nivel ADSET",
                )
        if (self.orcamento is not None
                and self.orcamento.periodo == receitas.PERIODO_TOTAL
                and self.programacao.end_time is None):
            raise ErroDeNascimentoMeta(
                "META_SCHEDULE_END_REQUIRED",
                "orcamento total exige uma data de termino no conjunto",
            )

    @property
    def chave_de_operacao(self) -> str:
        return f"adset:{self.adset_key}"


@dataclass(frozen=True)
class AnuncioMeta:
    """Um par Creative+Ad, ligado explicitamente a um conjunto (`F34`)."""

    variacao: VariacaoEstaticaMeta
    adset_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.variacao, VariacaoEstaticaMeta):
            raise ErroDeNascimentoMeta(
                "META_STATIC_BATCH_INVALID", "variacao do anuncio invalida")
        object.__setattr__(self, "adset_key", _chave_estavel(self.adset_key, "adset_key"))

    @property
    def variation_key(self) -> str:
        return self.variacao.variation_key


@dataclass(frozen=True)
class PlanoMetaV2:
    """O plano completo: uma campanha, N conjuntos, N anúncios."""

    recipe_id: str
    account_ref: str
    page_ref: str
    campaign_name: str
    destination_url: str
    conjuntos: tuple[ConjuntoMeta, ...]
    anuncios: tuple[AnuncioMeta, ...]
    special_categories_confirmed: bool
    special_ad_categories: tuple[str, ...] = ()
    #: Presente somente em CBO.
    orcamento_campanha: OrcamentoMeta | None = None
    is_adset_budget_sharing_enabled: bool = False
    instagram_actor_ref: str | None = None

    def __post_init__(self) -> None:
        receita = receitas.receita(self.recipe_id)
        object.__setattr__(self, "recipe_id", receita.id)
        object.__setattr__(
            self, "campaign_name", _texto(self.campaign_name, "campaign_name", maximo=400))
        object.__setattr__(self, "account_ref", _referencia(self.account_ref, "account_ref"))
        object.__setattr__(self, "page_ref", _referencia(self.page_ref, "page_ref"))
        object.__setattr__(self, "destination_url", _url_https(self.destination_url))
        if self.instagram_actor_ref is not None:
            object.__setattr__(self, "instagram_actor_ref", _referencia(
                self.instagram_actor_ref, "instagram_actor_ref"))

        conjuntos = tuple(self.conjuntos)
        anuncios = tuple(self.anuncios)
        if not conjuntos:
            raise ErroDeNascimentoMeta(
                "META_ADSET_REQUIRED", "o plano precisa de ao menos um conjunto")
        if len(conjuntos) > MAX_CONJUNTOS:
            raise ErroDeNascimentoMeta(
                "META_ADSET_LIMIT_EXCEEDED",
                f"o plano aceita no maximo {MAX_CONJUNTOS} conjuntos",
            )
        chaves = [item.adset_key for item in conjuntos]
        if len(set(chaves)) != len(chaves):
            raise ErroDeNascimentoMeta(
                "META_ADSET_DUPLICATE_KEY", "adset_key precisa ser unica no plano")
        if len(set(item.nome for item in conjuntos)) != len(conjuntos):
            raise ErroDeNascimentoMeta(
                "META_ADSET_DUPLICATE_NAME", "nomes de conjuntos precisam ser unicos")
        object.__setattr__(self, "conjuntos", conjuntos)

        if not anuncios:
            raise ErroDeNascimentoMeta(
                "META_AD_REQUIRED", "o plano precisa de ao menos um anuncio")
        if len(anuncios) > MAX_ANUNCIOS_TOTAL:
            raise ErroDeNascimentoMeta(
                "META_AD_LIMIT_EXCEEDED",
                f"o plano aceita no maximo {MAX_ANUNCIOS_TOTAL} anuncios",
            )
        variacoes = [item.variation_key for item in anuncios]
        if len(set(variacoes)) != len(variacoes):
            raise ErroDeNascimentoMeta(
                "META_STATIC_BATCH_DUPLICATE_KEY", "variation_key precisa ser unica no plano")
        if len(set(item.variacao.creative_name for item in anuncios)) != len(anuncios):
            raise ErroDeNascimentoMeta(
                "META_STATIC_BATCH_DUPLICATE_NAME", "nomes de criativos precisam ser unicos")
        if len(set(item.variacao.ad_name for item in anuncios)) != len(anuncios):
            raise ErroDeNascimentoMeta(
                "META_STATIC_BATCH_DUPLICATE_NAME", "nomes de anuncios precisam ser unicos")
        conhecidas = set(chaves)
        por_conjunto: dict[str, int] = {}
        for anuncio in anuncios:
            if anuncio.adset_key not in conhecidas:
                raise ErroDeNascimentoMeta(
                    "META_AD_ADSET_UNKNOWN",
                    "um anuncio aponta para um conjunto que nao existe no plano",
                )
            por_conjunto[anuncio.adset_key] = por_conjunto.get(anuncio.adset_key, 0) + 1
        excedidos = [k for k, n in por_conjunto.items() if n > MAX_ANUNCIOS_POR_CONJUNTO]
        if excedidos:
            raise ErroDeNascimentoMeta(
                "META_AD_PER_ADSET_LIMIT_EXCEEDED",
                f"cada conjunto aceita no maximo {MAX_ANUNCIOS_POR_CONJUNTO} anuncios",
            )
        # Um conjunto sem anúncio nasceria vazio e gastaria zero — mas também
        # esconderia um erro de mapeamento do lote. É recusado com nome próprio.
        orfaos = conhecidas - set(por_conjunto)
        if orfaos:
            raise ErroDeNascimentoMeta(
                "META_ADSET_WITHOUT_AD",
                "todo conjunto do plano precisa de ao menos um anuncio",
            )
        object.__setattr__(self, "anuncios", anuncios)

        # ── Orçamento: a união discriminada, cobrada aqui (`F04`) ────────────
        com_orcamento = [item for item in conjuntos if item.orcamento is not None]
        if self.orcamento_campanha is not None:
            if not isinstance(self.orcamento_campanha, OrcamentoMeta):
                raise ErroDeNascimentoMeta(
                    "META_BUDGET_INVALID", "o orcamento da campanha e invalido")
            if self.orcamento_campanha.nivel != receitas.ORCAMENTO_NA_CAMPANHA:
                raise ErroDeNascimentoMeta(
                    "META_BUDGET_LEVEL_MISMATCH",
                    "o orcamento anexado a campanha precisa ser de nivel CAMPAIGN",
                )
            if com_orcamento:
                raise ErroDeNascimentoMeta(
                    "META_BUDGET_DUPLICATED",
                    "com orcamento na campanha (CBO) nenhum conjunto pode ter verba propria",
                )
            if (self.orcamento_campanha.periodo == receitas.PERIODO_TOTAL
                    and any(item.programacao.end_time is None for item in conjuntos)):
                raise ErroDeNascimentoMeta(
                    "META_SCHEDULE_END_REQUIRED",
                    "orcamento total na campanha exige data de termino em todos os conjuntos",
                )
        else:
            if len(com_orcamento) != len(conjuntos):
                raise ErroDeNascimentoMeta(
                    "META_BUDGET_REQUIRED",
                    "sem orcamento na campanha (ABO), cada conjunto precisa do seu",
                )
        receita.modo_de_orcamento(self.nivel_de_orcamento, self.periodo_de_orcamento)

        if not isinstance(self.is_adset_budget_sharing_enabled, bool):
            raise ErroDeNascimentoMeta(
                "META_BUDGET_SHARING_INVALID",
                "is_adset_budget_sharing_enabled precisa ser True ou False",
            )
        # ⚠️ CBO NÃO É COMPARTILHAMENTO. `is_adset_budget_sharing_enabled` é um
        # campo separado, com semântica própria e receita própria; ligá-lo por
        # causa do CBO seria mudar a entrega sem o operador pedir.
        if self.is_adset_budget_sharing_enabled:
            raise ErroDeNascimentoMeta(
                "META_BUDGET_SHARING_REQUIRES_PROVEN_RECIPE",
                "o compartilhamento de verba entre conjuntos exige receita propria "
                "comprovada; CBO nao o liga",
            )

        if not self.special_categories_confirmed:
            raise ErroDeNascimentoMeta(
                "META_SPECIAL_CATEGORY_NOT_CONFIRMED",
                "o operador precisa confirmar explicitamente as categorias especiais",
            )
        categorias = tuple(dict.fromkeys(self.special_ad_categories))
        if categorias:
            raise ErroDeNascimentoMeta(
                "META_SPECIAL_CATEGORY_RECIPE_UNPROVEN",
                "categorias especiais exigem receita, targeting e read-back proprios",
            )
        object.__setattr__(self, "special_ad_categories", categorias)

        # ── Mensuração x receita ────────────────────────────────────────────
        for conjunto in conjuntos:
            receita.exigir_proposito(conjunto.mensuracao.proposito)
            if receita.exige_promoted_object and not conjunto.mensuracao.altera_payload:
                raise ErroDeNascimentoMeta(
                    "META_MEASUREMENT_REQUIRED_BY_RECIPE",
                    f"a receita {receita.id} exige otimizar por uma conversao existente",
                )
            if conjunto.posicionamentos.exige_identidade_instagram and not self.instagram_actor_ref:
                raise ErroDeNascimentoMeta(
                    "META_INSTAGRAM_IDENTITY_REQUIRED",
                    "posicionamento no Instagram exige uma identidade validada",
                )

    # ── Projeções ───────────────────────────────────────────────────────────

    @property
    def receita(self) -> receitas.Receita:
        return receitas.REGISTRO[self.recipe_id]

    @property
    def orcamento_e_da_campanha(self) -> bool:
        return self.orcamento_campanha is not None

    @property
    def nivel_de_orcamento(self) -> str:
        return (
            receitas.ORCAMENTO_NA_CAMPANHA if self.orcamento_e_da_campanha
            else receitas.ORCAMENTO_NO_CONJUNTO)

    @property
    def periodo_de_orcamento(self) -> str:
        if self.orcamento_campanha is not None:
            return self.orcamento_campanha.periodo
        periodos = {item.orcamento.periodo for item in self.conjuntos if item.orcamento}
        if len(periodos) != 1:
            raise ErroDeNascimentoMeta(
                "META_BUDGET_PERIOD_MIXED",
                "todos os conjuntos precisam usar o mesmo tipo de orcamento",
            )
        return periodos.pop()

    @property
    def modo_de_orcamento(self) -> receitas.ModoDeOrcamento:
        return self.receita.modo_de_orcamento(
            self.nivel_de_orcamento, self.periodo_de_orcamento)

    def anuncios_do_conjunto(self, adset_key: str) -> tuple[AnuncioMeta, ...]:
        return tuple(item for item in self.anuncios if item.adset_key == adset_key)

    @property
    def asset_refs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.variacao.asset_ref for item in self.anuncios))

    def bloqueios_para_criar(self) -> tuple[str, ...]:
        """As provas que faltam para este plano poder NASCER.

        ⚠️ Não bloqueia compilar nem validar. É `validate_only` que produz a
        prova ausente, e fechá-lo aqui tornaria a lacuna permanente.
        """
        faltando: list[str] = []
        if not self.receita.emissivel_para_criar:
            faltando.append(
                self.receita.motivo_sem_prova
                or f"a receita {self.receita.id} ainda nao foi aceita pela Meta nesta conta")
        modo = self.modo_de_orcamento
        if not modo.emissivel_para_criar:
            faltando.append(
                f"o modo de orcamento {modo.id} ainda nao foi validado nesta conta: {modo.fonte}")
        return tuple(faltando)


@dataclass(frozen=True, repr=False)
class ReferenciasDePublicoResolvidas:
    """Os IDs reais por trás das referências opacas de público e mensuração.

    ⚠️ Existe separado de `ReferenciasMetaResolvidas` de propósito. Aquele
    resolve conta, Página e bytes de peça — coisas que TODA receita precisa.
    Este resolve o que só existe no V2, e resolvê-lo é um ato de LEITURA da
    conta escolhida: um id que não estiver aqui não é adivinhado, é recusado.

    ⚠️ `__repr__` é fechado como no irmão: um traceback não pode despejar ids
    de público de uma conta real num log.
    """

    custom_audience_ids: Mapping[str, str] = field(default_factory=dict)
    locale_ids: Mapping[str, int] = field(default_factory=dict)
    interest_ids: Mapping[str, str] = field(default_factory=dict)
    measurement_source_ids: Mapping[str, str] = field(default_factory=dict)
    custom_conversion_ids: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for campo in (
            "custom_audience_ids", "interest_ids",
            "measurement_source_ids", "custom_conversion_ids",
        ):
            resolvido: dict[str, str] = {}
            for referencia, identificador in dict(getattr(self, campo)).items():
                ref = _referencia(str(referencia), campo)
                valor = str(identificador or "").strip()
                if not valor.isdigit():
                    raise ErroDeNascimentoMeta(
                        "META_RESOLVED_REFERENCE_INVALID",
                        f"{campo} tem identificador de provedor invalido",
                    )
                resolvido[ref] = valor
            object.__setattr__(self, campo, resolvido)
        locales: dict[str, int] = {}
        for referencia, identificador in dict(self.locale_ids).items():
            ref = _referencia(str(referencia), "locale_ids")
            if not isinstance(identificador, int) or isinstance(identificador, bool) or identificador <= 0:
                raise ErroDeNascimentoMeta(
                    "META_RESOLVED_REFERENCE_INVALID",
                    "locale precisa ser o inteiro do catalogo da Meta",
                )
            locales[ref] = identificador
        object.__setattr__(self, "locale_ids", locales)

    def _resolver(self, mapa: Mapping[str, Any], referencia: str, o_que: str) -> Any:
        try:
            return mapa[referencia]
        except KeyError:
            raise ErroDeNascimentoMeta(
                "META_AUDIENCE_REFERENCE_UNRESOLVED",
                f"{o_que} nao foi resolvido pelo backend para esta conta",
            ) from None

    def publico(self, referencia: str) -> str:
        return self._resolver(self.custom_audience_ids, referencia, "um publico selecionado")

    def locale(self, referencia: str) -> int:
        return self._resolver(self.locale_ids, referencia, "um idioma selecionado")

    def interesse(self, referencia: str) -> str:
        return self._resolver(self.interest_ids, referencia, "um interesse selecionado")

    def fonte(self, referencia: str) -> str:
        return self._resolver(
            self.measurement_source_ids, referencia, "a fonte de mensuracao")

    def conversao(self, referencia: str) -> str:
        return self._resolver(
            self.custom_conversion_ids, referencia, "a conversao personalizada")

    def __repr__(self) -> str:
        return "ReferenciasDePublicoResolvidas(<ocultas>)"


# ═════════════════════════════════════════════════════════════════════════════
# A ficha do canário (T12) — um pedido de autorização, nunca uma execução
# ═════════════════════════════════════════════════════════════════════════════

#: As quatro camadas de prova do tracking, e o que cada uma NÃO prova.
#:
#: ⚠️ Elas existem separadas porque a confusão entre elas é o defeito que a
#: spec chama pelo nome: "roots não prova expansão das macros nem receita".
#: `validate_only` das raízes independentes diz que a Meta aceitou o FORMATO do
#: criativo — não que `{{campaign.id}}` virou um número, não que o parâmetro
#: sobreviveu ao redirect da LP, e não que a receita chegou ao GAM.
CAMADAS_DE_PROVA_DE_TRACKING: tuple[Mapping[str, str], ...] = (
    {
        "id": "COMPILADO_LOCAL",
        "prova": "o template está no payload, entra no hash e é lido de volta do plano",
        "nao_prova": "que a Meta aceita este criativo",
    },
    {
        "id": "ROOTS_REMOTO",
        "prova": "a Meta aceitou campanha e criativo sob validate_only",
        "nao_prova": (
            "que o conjunto e o anúncio seriam aceitos, que a macro expande, "
            "e que existe receita"
        ),
    },
    {
        "id": "EXPANSAO_REAL",
        "prova": "a macro virou um campaign.id real e sobreviveu aos redirects até a LP",
        "nao_prova": "que o valor chegou à dimensão financeira",
        "exige": "uma campanha ENTREGANDO — autorização separada",
    },
    {
        "id": "RECEITA_NO_GAM",
        "prova": "utm_campaign_value bateu com campaign_id no join financeiro",
        "nao_prova": "nada além do período e do escopo medidos",
        "exige": "entrega real e janela de coleta — autorização separada",
    },
)


def ficha_de_canario(
    plano: PlanoMetaV2,
    compilado: Any,
    *,
    prova_de_validacao: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Monta a FICHA de autorização do primeiro canário.

    ⚠️ Ela não executa, não agenda e não guarda autorização. É um documento
    para uma pessoa ler e decidir — e por isso ele precisa listar exatamente o
    que ainda NÃO foi provado, e não só o que foi.

    ⚠️ Nenhum identificador real do provedor entra aqui: conta, Página e peça
    viajam como referências opacas. Uma ficha é feita para ser copiada para um
    chat ou um ticket, e é justamente aí que um `act_<id>` vazaria.
    """
    conjuntos = plano.conjuntos
    total_anuncios = len(plano.anuncios)
    faltando: list[str] = list(plano.bloqueios_para_criar())

    if prova_de_validacao is None or not prova_de_validacao.get("registrada"):
        faltando.append(
            "não existe recibo durável de validate_only para este hash; valide o "
            "plano atual por clique antes de pedir autorização"
        )

    # O primeiro canário do contrato é UMA campanha, UM conjunto, UM anúncio
    # estático. Um plano maior não é inválido — ele só não é o CANÁRIO, e
    # deixar isso implícito seria pedir autorização para outra coisa.
    if len(conjuntos) != 1 or total_anuncios != 1:
        faltando.append(
            f"o primeiro canário é uma campanha, um conjunto e um anúncio; este "
            f"plano tem {len(conjuntos)} conjunto(s) e {total_anuncios} anúncio(s)"
        )

    orcamento = (
        plano.orcamento_campanha if plano.orcamento_e_da_campanha
        else conjuntos[0].orcamento
    )
    return {
        "documento": "CANARY_AUTHORIZATION_REQUEST",
        "estado": "CANARY_AUTHORIZATION_REQUIRED",
        # ⚠️ Dito com todas as letras, no corpo do documento: gerar a ficha não
        # autoriza nada, e nada foi criado ao gerá-la.
        "efeito_desta_ficha": "NENHUM",
        "objetos_criados": 0,
        "pedido": {
            "conta_ref": plano.account_ref,
            "pagina_ref": plano.page_ref,
            "receita": plano.receita.id,
            "objetivo": plano.receita.objective,
            "otimizacao": plano.receita.optimization_goal,
            "destino_url": plano.destination_url,
            "peca_refs": list(plano.asset_refs),
            "orcamento": None if orcamento is None else {
                "nivel": orcamento.nivel,
                "periodo": orcamento.periodo,
                "amount_minor": orcamento.amount_minor,
                "currency": orcamento.currency,
            },
            "conjuntos": len(conjuntos),
            "anuncios": total_anuncios,
            "estado_ao_nascer": "PAUSED",
            "plano_sha256": getattr(compilado, "plano_sha256", None),
        },
        "tracking": {
            "template": None,
            "camadas": [dict(camada) for camada in CAMADAS_DE_PROVA_DE_TRACKING],
        },
        "provas_faltantes": faltando,
        "autorizado": False,
        "proximo_ato": (
            "uma pessoa autoriza nominalmente a criação PAUSED deste hash exato; "
            "sem essa autorização nada é criado"
        ),
    }
