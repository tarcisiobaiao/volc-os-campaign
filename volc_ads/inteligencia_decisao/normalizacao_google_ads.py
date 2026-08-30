"""Fronteira hermética de linhas Google Ads para o contrato do laboratório.

O módulo recebe somente a projeção dotted-path achatada por um adaptador depois
de MessageToDict, no mesmo grão dos recursos Google Ads. Não conhece SDK,
consulta, arquivo, relógio implícito ou destino de persistência. Qualquer
ambiguidade de presença, identidade, grão, janela ou domínio interrompe o lote
inteiro antes de produzir uma fotografia.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

VERSAO_NORMALIZADOR_GOOGLE_ADS = 4
VERSAO_RECIBO_COBERTURA_GOOGLE_ADS = 3
GRAOS_SUPORTADOS = (
    "campaign_day",
    "campaign_window",
    "keyword_criterion",
    "search_term_view",
    "campaign_negative",
    "ad_group_negative",
)

_CAMPANHA = (
    "customer.id",
    "campaign.id",
    "campaign.resource_name",
    "campaign.status",
    "campaign.serving_status",
)
_CAMPANHA_DIA = _CAMPANHA + (
    "customer.currency_code",
    "segments.date",
    "metrics.impressions",
    "metrics.clicks",
    "metrics.cost_micros",
    "metrics.conversions",
    "metrics.conversions_value",
)
_CAMPANHA_JANELA = _CAMPANHA + (
    "metrics.search_impression_share",
    "metrics.search_budget_lost_impression_share",
    "metrics.search_rank_lost_impression_share",
)
_KEYWORD = (
    "customer.id",
    "campaign.id",
    "ad_group.id",
    "ad_group_criterion.criterion_id",
    "ad_group_criterion.resource_name",
    "ad_group_criterion.type",
    "ad_group_criterion.status",
    "ad_group_criterion.system_serving_status",
    "ad_group_criterion.negative",
    "ad_group_criterion.keyword.text",
    "ad_group_criterion.keyword.match_type",
    "ad_group_criterion.quality_info.quality_score",
    "ad_group_criterion.quality_info.creative_quality_score",
    "ad_group_criterion.quality_info.post_click_quality_score",
    "ad_group_criterion.quality_info.search_predicted_ctr",
)
_TERMO = (
    "customer.id",
    "campaign.id",
    "ad_group.id",
    "search_term_view.resource_name",
    "search_term_view.search_term",
    "search_term_view.status",
    "segments.search_term_match_type",
    "metrics.impressions",
    "metrics.clicks",
    "metrics.cost_micros",
    "metrics.conversions",
)
_NEGATIVA_CAMPANHA = (
    "customer.id",
    "campaign.id",
    "campaign_criterion.criterion_id",
    "campaign_criterion.resource_name",
    "campaign_criterion.type",
    "campaign_criterion.status",
    "campaign_criterion.negative",
    "campaign_criterion.keyword.text",
    "campaign_criterion.keyword.match_type",
)
_NEGATIVA_GRUPO = (
    "customer.id",
    "campaign.id",
    "ad_group.id",
    "ad_group_criterion.criterion_id",
    "ad_group_criterion.resource_name",
    "ad_group_criterion.type",
    "ad_group_criterion.status",
    "ad_group_criterion.system_serving_status",
    "ad_group_criterion.negative",
    "ad_group_criterion.keyword.text",
    "ad_group_criterion.keyword.match_type",
)
_CAMPOS_POR_GRAO = {
    "campaign_day": _CAMPANHA_DIA,
    "campaign_window": _CAMPANHA_JANELA,
    "keyword_criterion": _KEYWORD,
    "search_term_view": _TERMO,
    "campaign_negative": _NEGATIVA_CAMPANHA,
    "ad_group_negative": _NEGATIVA_GRUPO,
}
_CAMPOS_NULAVEIS_OMISSIVEIS_POR_GRAO = {
    "keyword_criterion": {
        "ad_group_criterion.quality_info.quality_score",
        "ad_group_criterion.quality_info.creative_quality_score",
        "ad_group_criterion.quality_info.post_click_quality_score",
        "ad_group_criterion.quality_info.search_predicted_ctr",
    }
}

_INT64_MAX = (1 << 63) - 1
_INT64_MAX_TEXTO = str(_INT64_MAX)
_CAMPOS_OBRIGATORIOS_POR_GRAO = {
    grao: set(campos) - _CAMPOS_NULAVEIS_OMISSIVEIS_POR_GRAO.get(grao, set())
    for grao, campos in _CAMPOS_POR_GRAO.items()
}

_COMPONENTES_QUALIDADE = {"ABOVE_AVERAGE", "AVERAGE", "BELOW_AVERAGE"}
_KEYWORD_MATCH_TYPES = {"EXACT", "PHRASE", "BROAD"}
_METRICAS_INTEIRAS = {"metrics.impressions", "metrics.clicks", "metrics.cost_micros"}
_TOKEN_ENUM = re.compile(r"^[A-Z][A-Z0-9_]*$")
_ID_PROTOJSON_CANONICO = re.compile(r"^[1-9][0-9]*$")
_INT64_PROTOJSON_CANONICO = re.compile(r"^(?:0|[1-9][0-9]*)$")
_DATA_ISO_ESTENDIDA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_QUALITY_SCORE_PROTOJSON_CANONICO = re.compile(r"^(?:[1-9]|10)$")
_CAMPO_QUALITY_SCORE = "ad_group_criterion.quality_info.quality_score"
_CONVERSAO_QUALITY_SCORE_STRING = "int32_to_canonical_decimal_string"
_CONVERSOES_ADAPTADOR_PERMITIDAS = {
    _CAMPO_QUALITY_SCORE: _CONVERSAO_QUALITY_SCORE_STRING,
}


class EstadoCoberturaGoogleAds(str, Enum):
    """Estado explícito de uma consulta materializada por grão."""

    COMPLETO = "completo"
    NAO_CONSULTADO = "nao_consultado"
    FALHA = "falha"
    PARCIAL = "parcial"
    VAZIO_CONFIRMADO = "vazio_confirmado"


@dataclass(frozen=True)
class CoberturaGraoGoogleAds:
    """Contagem e estado observados para exatamente um grão raw."""

    estado: EstadoCoberturaGoogleAds
    linhas_recebidas: int
    selected_fields: tuple[str, ...]

    def serializar(self) -> dict[str, Any]:
        return {
            "estado": self.estado.value,
            "linhas_recebidas": self.linhas_recebidas,
            "selected_fields": list(self.selected_fields),
        }


@dataclass(frozen=True)
class ReciboCoberturaGoogleAds:
    """Recibo fechado: nenhum grão ausente é inferido como vazio ou sucesso."""

    schema_version: int
    customer_time_zone: str
    query_window: Mapping[str, str]
    adapter_conversions: Mapping[str, str]
    grains: Mapping[str, CoberturaGraoGoogleAds]

    def serializar(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "customer_time_zone": self.customer_time_zone,
            "query_window": dict(self.query_window),
            "adapter_conversions": {
                campo: self.adapter_conversions[campo]
                for campo in sorted(self.adapter_conversions)
            },
            "grains": {
                grao: self.grains[grao].serializar()
                for grao in GRAOS_SUPORTADOS
            },
        }


class ErroNormalizacaoGoogleAds(ValueError):
    """Recusa tipada da fronteira raw; nunca representa leitura parcial."""

    def __init__(self, codigo: str, detalhe: str) -> None:
        self.codigo = codigo
        self.detalhe = detalhe
        super().__init__(f"{codigo}: {detalhe}")


def _recusar(codigo: str, detalhe: str) -> None:
    raise ErroNormalizacaoGoogleAds(codigo, detalhe)


def _data(valor: object, campo: str) -> date:
    if not isinstance(valor, str) or _DATA_ISO_ESTENDIDA.fullmatch(valor) is None:
        _recusar("DATA_INVALIDA", f"{campo} precisa ser data ISO estendida YYYY-MM-DD")
    try:
        return date.fromisoformat(valor)
    except ValueError:
        _recusar("DATA_INVALIDA", f"{campo} precisa ser data ISO estendida YYYY-MM-DD")


def _instante(valor: object, campo: str) -> datetime:
    if not isinstance(valor, str) or not valor:
        _recusar("INSTANTE_INVALIDO", f"{campo} precisa ser instante ISO com fuso")
    try:
        instante = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        _recusar("INSTANTE_INVALIDO", f"{campo} precisa ser instante ISO com fuso")
    if instante.tzinfo is None or instante.utcoffset() is None:
        _recusar("INSTANTE_INVALIDO", f"{campo} precisa declarar fuso")
    return instante.astimezone(timezone.utc)


def _iso_utc(instante: datetime) -> str:
    return instante.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timezone_calendario(valor: object) -> tuple[str, ZoneInfo]:
    if not isinstance(valor, str) or not valor or valor != valor.strip():
        _recusar(
            "TIMEZONE_INVALIDO",
            "calendar_timezone precisa ser nome IANA não vazio",
        )
    try:
        calendario = ZoneInfo(valor)
    except (ZoneInfoNotFoundError, ValueError):
        _recusar(
            "TIMEZONE_INVALIDO",
            "calendar_timezone precisa ser nome IANA reconhecido",
        )
    return valor, calendario


def _janela(
    valor: object,
    *,
    as_of_date: date,
    data_leitura: date,
) -> tuple[dict[str, str], date, date]:
    if not isinstance(valor, Mapping) or set(valor) != {"inicio", "fim"}:
        _recusar("JANELA_INVALIDA", "janela precisa conter somente inicio e fim")
    inicio = _data(valor.get("inicio"), "janela.inicio")
    fim = _data(valor.get("fim"), "janela.fim")
    if inicio > fim:
        _recusar("JANELA_INVALIDA", "janela está invertida")
    if fim > as_of_date:
        _recusar("DATA_APOS_AS_OF", "janela termina depois de as_of_date")
    if fim >= data_leitura:
        _recusar(
            "DADO_APOS_LEITURA",
            "janela precisa estar encerrada no calendário antes de lido_em",
        )
    return {"inicio": inicio.isoformat(), "fim": fim.isoformat()}, inicio, fim


def _id(valor: object, campo: str) -> str:
    if not isinstance(valor, str) or _ID_PROTOJSON_CANONICO.fullmatch(valor) is None:
        _recusar(
            "IDENTIDADE_INVALIDA",
            f"{campo} precisa ser decimal ProtoJSON canônico entre 1 e 2^63-1",
        )
    if len(valor) > len(_INT64_MAX_TEXTO) or (
        len(valor) == len(_INT64_MAX_TEXTO) and valor > _INT64_MAX_TEXTO
    ):
        _recusar(
            "IDENTIDADE_INVALIDA",
            f"{campo} precisa ser decimal ProtoJSON canônico entre 1 e 2^63-1",
        )
    return valor


def _texto(valor: object, campo: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        _recusar("CAMPO_INVALIDO", f"{campo} precisa ser texto não vazio")
    return valor


def _moeda(valor: object) -> str:
    if (
        not isinstance(valor, str)
        or len(valor) != 3
        or not valor.isascii()
        or not valor.isalpha()
        or valor != valor.upper()
    ):
        _recusar(
            "MOEDA_INVALIDA",
            "customer.currency_code precisa ser código ASCII maiúsculo de 3 letras",
        )
    return valor


def _canonicalizar_double(valor: float) -> int | float:
    if valor == 0:
        return 0
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    return valor


def _double_nao_negativo(valor: object, campo: str) -> int | float:
    if valor is None:
        _recusar("NULABILIDADE_INVALIDA", f"{campo} é métrica obrigatória e não aceita null")
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        _recusar("RANGE_INVALIDO", f"{campo} precisa ser número não negativo")
    if isinstance(valor, float) and not math.isfinite(valor):
        _recusar("RANGE_INVALIDO", f"{campo} precisa ser número finito não negativo")
    if isinstance(valor, int):
        try:
            representacao_double = float(valor)
        except OverflowError:
            _recusar("RANGE_INVALIDO", f"{campo} precisa caber em double finito não negativo")
        if not math.isfinite(representacao_double):
            _recusar("RANGE_INVALIDO", f"{campo} precisa caber em double finito não negativo")
    if valor < 0:
        _recusar("RANGE_INVALIDO", f"{campo} precisa ser número não negativo")
    return _canonicalizar_double(valor)


def _inteiro_int64_proto(valor: object, campo: str) -> int:
    """Valida a string decimal int64 emitida pelo ProtoJSON/MessageToDict."""

    if (
        not isinstance(valor, str)
        or _INT64_PROTOJSON_CANONICO.fullmatch(valor) is None
    ):
        _recusar(
            "CODIFICACAO_ESCALAR_INVALIDA",
            f"{campo} precisa ser string decimal int64 produzida por MessageToDict",
        )
    if len(valor) > len(_INT64_MAX_TEXTO) or (
        len(valor) == len(_INT64_MAX_TEXTO) and valor > _INT64_MAX_TEXTO
    ):
        _recusar(
            "RANGE_INT64_INVALIDO",
            f"{campo} precisa estar entre 0 e 2^63-1",
        )
    return int(valor)


def _inteiro_proto_nao_negativo(valor: object, campo: str) -> int:
    """Converte int64 ProtoJSON validado para inteiro canônico."""

    if valor is None:
        _recusar("NULABILIDADE_INVALIDA", f"{campo} é métrica obrigatória e não aceita null")
    return _inteiro_int64_proto(valor, campo)


def _percentual(valor: object, campo: str) -> int | float:
    numero = _double_nao_negativo(valor, campo)
    if numero > 1:
        _recusar("PERCENTUAL_INVALIDO", f"{campo} precisa estar entre 0 e 1")
    return numero


def _micros_de_unidade_monetaria(valor: object) -> int:
    if valor is None:
        _recusar(
            "NULABILIDADE_INVALIDA",
            "metrics.conversions_value é métrica obrigatória e não aceita null",
        )
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        _recusar(
            "RANGE_INVALIDO",
            "metrics.conversions_value precisa ser decimal não negativo",
        )
    if isinstance(valor, int):
        try:
            representacao_double = float(valor)
        except OverflowError:
            _recusar(
                "RANGE_INVALIDO",
                "metrics.conversions_value precisa caber em double finito não negativo",
            )
        if not math.isfinite(representacao_double):
            _recusar(
                "RANGE_INVALIDO",
                "metrics.conversions_value precisa caber em double finito não negativo",
            )
    try:
        decimal = Decimal(str(valor))
    except InvalidOperation:
        _recusar(
            "RANGE_INVALIDO",
            "metrics.conversions_value precisa ser decimal não negativo",
        )
    if not decimal.is_finite() or decimal < 0:
        _recusar(
            "RANGE_INVALIDO",
            "metrics.conversions_value precisa ser decimal finito não negativo",
        )
    micros = decimal * Decimal(1_000_000)
    if micros != micros.to_integral_value():
        _recusar(
            "PRECISAO_MONETARIA_INVALIDA",
            "metrics.conversions_value possui fração menor que um micro",
        )
    micros_inteiros = int(micros)
    if micros_inteiros > _INT64_MAX:
        _recusar(
            "RANGE_INT64_INVALIDO",
            "metrics.conversions_value em micros precisa estar entre 0 e 2^63-1",
        )
    return micros_inteiros


def _enum(valor: object, campo: str, permitidos: set[str]) -> str:
    if not isinstance(valor, str) or valor not in permitidos:
        _recusar("ENUM_INVALIDO", f"{campo} fora do domínio provado")
    return valor


def _token_enum_materializado(valor: object, campo: str) -> str:
    """Preserva um enum do proto sem fingir enumerar o domínio Google inteiro."""

    if not isinstance(valor, str) or _TOKEN_ENUM.fullmatch(valor) is None:
        _recusar(
            "ENUM_INVALIDO",
            f"{campo} precisa ser token enum materializado pelo MessageToDict",
        )
    return valor


def _enum_observado(valor: object, campo: str) -> str:
    """Recusa sentinelas do proto que não constituem estado observado."""

    token = _token_enum_materializado(valor, campo)
    if token in {"UNKNOWN", "UNSPECIFIED"} or token.endswith(
        ("_UNKNOWN", "_UNSPECIFIED")
    ):
        _recusar(
            "ENUM_NAO_OBSERVADO",
            f"{campo} não pode usar UNKNOWN/UNSPECIFIED como evidência elegível",
        )
    return token


def _booleano_exato(valor: object, campo: str, *, esperado: bool) -> bool:
    if not isinstance(valor, bool) or valor is not esperado:
        _recusar(
            "POLARIDADE_INVALIDA",
            f"{campo} precisa ser {str(esperado).lower()}",
        )
    return valor


def _tipo_keyword(valor: object, campo: str) -> str:
    if valor != "KEYWORD":
        _recusar("TIPO_CRITERIO_INVALIDO", f"{campo} precisa ser KEYWORD")
    return "KEYWORD"


def _quality_score(
    valor: object,
    *,
    aceita_string_convertida: bool,
) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        _recusar(
            "CODIFICACAO_ESCALAR_INVALIDA",
            "Quality Score precisa ser número inteiro int32",
        )
    if isinstance(valor, int):
        score = valor
    elif isinstance(valor, str) and aceita_string_convertida:
        if _QUALITY_SCORE_PROTOJSON_CANONICO.fullmatch(valor) is None:
            _recusar(
                "CODIFICACAO_ESCALAR_INVALIDA",
                "Quality Score convertido precisa ser string decimal canônica",
            )
        score = int(valor)
    else:
        _recusar(
            "CODIFICACAO_ESCALAR_INVALIDA",
            "Quality Score precisa ser número inteiro int32; string exige conversão declarada pelo adaptador",
        )
    if not 1 <= score <= 10:
        _recusar("RANGE_INVALIDO", "Quality Score precisa ser ausente ou inteiro entre 1 e 10")
    return score


def _componente_qualidade(valor: object, campo: str) -> str | None:
    if valor is None:
        return None
    return _enum(valor, campo, _COMPONENTES_QUALIDADE)


def _selected_fields(valor: object, grao: str) -> tuple[str, ...]:
    if isinstance(valor, (str, bytes)) or not isinstance(valor, Sequence):
        _recusar(
            "RECIBO_COBERTURA_INVALIDO",
            f"coverage_receipt.grains.{grao}.selected_fields precisa ser lista",
        )
    campos = list(valor)
    if any(not isinstance(campo, str) for campo in campos) or len(campos) != len(
        set(campos)
    ):
        _recusar(
            "RECIBO_COBERTURA_INVALIDO",
            f"coverage_receipt.grains.{grao}.selected_fields precisa conter nomes únicos",
        )
    permitidos = set(_CAMPOS_POR_GRAO[grao])
    selecionados = set(campos)
    extras = sorted(selecionados - permitidos)
    ausentes = sorted(_CAMPOS_OBRIGATORIOS_POR_GRAO[grao] - selecionados)
    if extras or ausentes:
        _recusar(
            "CAMPO_NAO_SELECIONADO",
            f"{grao}: seleção não prova o contrato; obrigatórios_ausentes={ausentes}; extras={extras}",
        )
    return tuple(campo for campo in _CAMPOS_POR_GRAO[grao] if campo in selecionados)


def _query_window_recibo(valor: object) -> dict[str, str]:
    if not isinstance(valor, Mapping) or set(valor) != {"inicio", "fim"}:
        _recusar(
            "RECIBO_COBERTURA_INVALIDO",
            "coverage_receipt.query_window precisa conter somente inicio e fim",
        )
    inicio = _data(valor.get("inicio"), "coverage_receipt.query_window.inicio")
    fim = _data(valor.get("fim"), "coverage_receipt.query_window.fim")
    if inicio > fim:
        _recusar(
            "RECIBO_COBERTURA_INVALIDO",
            "coverage_receipt.query_window está invertida",
        )
    return {"inicio": inicio.isoformat(), "fim": fim.isoformat()}


def _conversoes_adaptador(
    valor: object,
    *,
    selected_fields_keyword: Sequence[str],
) -> dict[str, str]:
    if not isinstance(valor, Mapping):
        _recusar(
            "RECIBO_COBERTURA_INVALIDO",
            "coverage_receipt.adapter_conversions precisa ser objeto",
        )
    conversoes: dict[str, str] = {}
    for campo, conversao in valor.items():
        if (
            not isinstance(campo, str)
            or not isinstance(conversao, str)
            or _CONVERSOES_ADAPTADOR_PERMITIDAS.get(campo) != conversao
        ):
            _recusar(
                "RECIBO_COBERTURA_INVALIDO",
                "coverage_receipt.adapter_conversions contém conversão desconhecida",
            )
        if campo not in selected_fields_keyword:
            _recusar(
                "RECIBO_COBERTURA_INVALIDO",
                f"conversão de {campo} foi declarada sem o campo estar selecionado",
            )
        conversoes[campo] = conversao
    return conversoes


def _recibo_cobertura(valor: object) -> ReciboCoberturaGoogleAds:
    if not isinstance(valor, Mapping) or set(valor) != {
        "schema_version",
        "customer_time_zone",
        "query_window",
        "adapter_conversions",
        "grains",
    }:
        _recusar(
            "RECIBO_COBERTURA_INVALIDO",
            "coverage_receipt precisa conter somente schema_version, customer_time_zone, query_window, adapter_conversions e grains",
        )
    if valor.get("schema_version") != VERSAO_RECIBO_COBERTURA_GOOGLE_ADS:
        _recusar(
            "RECIBO_COBERTURA_INVALIDO",
            "coverage_receipt.schema_version desconhecida",
        )
    graos_crus = valor.get("grains")
    if not isinstance(graos_crus, Mapping) or set(graos_crus) != set(GRAOS_SUPORTADOS):
        _recusar(
            "RECIBO_COBERTURA_INVALIDO",
            "coverage_receipt.grains precisa declarar exatamente todos os grãos",
        )
    graos: dict[str, CoberturaGraoGoogleAds] = {}
    for grao in GRAOS_SUPORTADOS:
        item = graos_crus.get(grao)
        if not isinstance(item, Mapping) or set(item) != {
            "estado",
            "linhas_recebidas",
            "selected_fields",
        }:
            _recusar(
                "RECIBO_COBERTURA_INVALIDO",
                f"coverage_receipt.grains.{grao} possui forma inválida",
            )
        try:
            estado = EstadoCoberturaGoogleAds(item.get("estado"))
        except (TypeError, ValueError):
            _recusar(
                "RECIBO_COBERTURA_INVALIDO",
                f"coverage_receipt.grains.{grao}.estado desconhecido",
            )
        contagem = item.get("linhas_recebidas")
        if isinstance(contagem, bool) or not isinstance(contagem, int) or contagem < 0:
            _recusar(
                "RECIBO_COBERTURA_INVALIDO",
                f"coverage_receipt.grains.{grao}.linhas_recebidas precisa ser inteiro não negativo",
            )
        graos[grao] = CoberturaGraoGoogleAds(
            estado=estado,
            linhas_recebidas=contagem,
            selected_fields=_selected_fields(item.get("selected_fields"), grao),
        )
    customer_time_zone = valor.get("customer_time_zone")
    if not isinstance(customer_time_zone, str) or not customer_time_zone:
        _recusar(
            "RECIBO_COBERTURA_INVALIDO",
            "coverage_receipt.customer_time_zone precisa ser evidência textual não vazia",
        )
    query_window = _query_window_recibo(valor.get("query_window"))
    adapter_conversions = _conversoes_adaptador(
        valor.get("adapter_conversions"),
        selected_fields_keyword=graos["keyword_criterion"].selected_fields,
    )
    return ReciboCoberturaGoogleAds(
        schema_version=VERSAO_RECIBO_COBERTURA_GOOGLE_ADS,
        customer_time_zone=customer_time_zone,
        query_window=query_window,
        adapter_conversions=adapter_conversions,
        grains=graos,
    )


def _projetar_campos_achatados(
    grao: str,
    campos: Mapping[str, Any],
    selected_fields: Sequence[str],
) -> dict[str, Any]:
    """Fecha a projeção dotted-key posterior a MessageToDict sem zero-fill."""

    esperados = set(_CAMPOS_POR_GRAO[grao])
    selecionados = set(selected_fields)
    recebidos = set(campos)
    extras = sorted(recebidos - esperados)
    nao_selecionados = sorted(recebidos - selecionados)
    if extras or nao_selecionados:
        _recusar(
            "GRAO_MISTURADO",
            f"{grao}: projeção achatada inválida; extras={extras}; não_selecionados={nao_selecionados}",
        )

    projetados: dict[str, Any] = {}
    anulaveis = _CAMPOS_NULAVEIS_OMISSIVEIS_POR_GRAO.get(grao, set())
    for campo in _CAMPOS_POR_GRAO[grao]:
        if campo not in selecionados:
            continue
        if campo not in campos:
            if campo not in anulaveis:
                _recusar(
                    "CAMPO_AUSENTE",
                    f"{grao}: {campo} foi selecionado mas não foi medido/materializado",
                )
            continue
        valor = campos[campo]
        if valor is None:
            if campo in anulaveis:
                continue
            _recusar(
                "NULABILIDADE_INVALIDA",
                f"{grao}: {campo} é obrigatório e não aceita null",
            )
        projetados[campo] = valor
    return projetados


def _validar_cobertura(
    recibo: ReciboCoberturaGoogleAds,
    contagens: Mapping[str, int],
) -> None:
    for grao in GRAOS_SUPORTADOS:
        cobertura = recibo.grains[grao]
        recebidas = contagens[grao]
        if cobertura.linhas_recebidas != recebidas:
            _recusar(
                "COBERTURA_INCONSISTENTE",
                f"{grao}: recibo declara {cobertura.linhas_recebidas}, lote contém {recebidas}",
            )
        if cobertura.estado in {
            EstadoCoberturaGoogleAds.NAO_CONSULTADO,
            EstadoCoberturaGoogleAds.FALHA,
            EstadoCoberturaGoogleAds.PARCIAL,
        }:
            _recusar(
                "COBERTURA_INELEGIVEL",
                f"{grao}: estado {cobertura.estado.value} não autoriza fonte completa/atual",
            )
        if cobertura.estado is EstadoCoberturaGoogleAds.COMPLETO and recebidas == 0:
            _recusar(
                "COBERTURA_INCONSISTENTE",
                f"{grao}: completo exige pelo menos uma linha",
            )
        if cobertura.estado is EstadoCoberturaGoogleAds.VAZIO_CONFIRMADO and recebidas != 0:
            _recusar(
                "COBERTURA_INCONSISTENTE",
                f"{grao}: vazio_confirmado exige zero linhas",
            )
    for grao in ("campaign_day", "campaign_window"):
        if recibo.grains[grao].estado is not EstadoCoberturaGoogleAds.COMPLETO:
            _recusar(
                "COBERTURA_INELEGIVEL",
                f"{grao}: fotografia decisória exige cobertura completa",
            )


def _linhagem(
    *,
    grao: str,
    janela: Mapping[str, str],
    lido_em: str,
    as_of_date: str,
    calendar_timezone: str,
    mapeamento: Sequence[tuple[str, str]],
) -> dict[str, Any]:
    return {
        "raw_grain": grao,
        "janela": dict(janela),
        "lido_em": lido_em,
        "as_of_date": as_of_date,
        "calendar_timezone": calendar_timezone,
        "fields": [
            {"target_field": destino, "source_field": origem}
            for destino, origem in mapeamento
        ],
    }


def _recurso_campanha(customer_id: str, campaign_id: str, valor: object) -> str:
    esperado = f"customers/{customer_id}/campaigns/{campaign_id}"
    recurso = _texto(valor, "campaign.resource_name")
    if recurso != esperado:
        _recusar("RESOURCE_NAME_INVALIDO", "campaign.resource_name não corresponde à identidade")
    return recurso


def _recurso_criterio(
    customer_id: str,
    ad_group_id: str,
    criterion_id: str,
    valor: object,
) -> str:
    esperado = f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{criterion_id}"
    recurso = _texto(valor, "ad_group_criterion.resource_name")
    if recurso != esperado:
        _recusar("RESOURCE_NAME_INVALIDO", "resource_name do critério não corresponde à identidade")
    return recurso


def _recurso_termo_de_busca(
    customer_id: str,
    campaign_id: str,
    ad_group_id: str,
    search_term: str,
    valor: object,
) -> str:
    sufixo = base64.urlsafe_b64encode(search_term.encode("utf-8")).decode("ascii").rstrip("=")
    esperado = (
        f"customers/{customer_id}/searchTermViews/"
        f"{campaign_id}~{ad_group_id}~{sufixo}"
    )
    recurso = _texto(valor, "search_term_view.resource_name")
    if recurso != esperado:
        _recusar(
            "RESOURCE_NAME_INVALIDO",
            "sufixo URL-base64 de search_term_view.resource_name não corresponde a search_term UTF-8",
        )
    return recurso


def _base_linha(
    linha: Mapping[str, Any],
    *,
    agora: datetime,
    as_of_date: date,
    calendario: ZoneInfo,
    selected_fields_por_grao: Mapping[str, Sequence[str]],
) -> tuple[str, Mapping[str, Any], dict[str, str], date, date, str]:
    if set(linha) != {"raw_grain", "janela", "lido_em", "source_fields"}:
        _recusar("LINHA_INVALIDA", "linha raw precisa conter somente raw_grain, janela, lido_em e source_fields")
    grao = linha.get("raw_grain")
    if grao not in GRAOS_SUPORTADOS:
        _recusar("GRAO_INVALIDO", f"raw_grain {grao!r} não é suportado")
    campos_crus = linha.get("source_fields")
    if not isinstance(campos_crus, Mapping):
        _recusar("LINHA_INVALIDA", "source_fields precisa ser objeto")
    campos = _projetar_campos_achatados(
        str(grao),
        campos_crus,
        selected_fields_por_grao[str(grao)],
    )
    lido = _instante(linha.get("lido_em"), "lido_em")
    if lido > agora:
        _recusar("DATA_FUTURA", "lido_em está no futuro")
    data_leitura = lido.astimezone(calendario).date()
    if as_of_date >= data_leitura:
        _recusar(
            "AS_OF_INVALIDO",
            "as_of_date precisa estar encerrada antes de lido_em no calendário declarado",
        )
    janela, inicio, fim = _janela(
        linha.get("janela"),
        as_of_date=as_of_date,
        data_leitura=data_leitura,
    )
    return str(grao), campos, janela, inicio, fim, _iso_utc(lido)


def _normalizar_campaign_day(
    campos: Mapping[str, Any],
    janela: Mapping[str, str],
    inicio: date,
    fim: date,
    lido_em: str,
    as_of_date: str,
    calendar_timezone: str,
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    customer_id = _id(campos["customer.id"], "customer.id")
    campaign_id = _id(campos["campaign.id"], "campaign.id")
    resource_name = _recurso_campanha(customer_id, campaign_id, campos["campaign.resource_name"])
    dia = _data(campos["segments.date"], "segments.date")
    if not inicio <= dia <= fim:
        _recusar("JANELA_MISTURADA", "segments.date está fora da janela declarada")
    metricas: dict[str, int | float | None] = {}
    for origem, destino in (
        ("metrics.impressions", "impressions"),
        ("metrics.clicks", "clicks"),
        ("metrics.cost_micros", "cost_micros"),
        ("metrics.conversions", "conversions"),
    ):
        if origem in _METRICAS_INTEIRAS:
            metricas[destino] = _inteiro_proto_nao_negativo(campos[origem], origem)
        else:
            metricas[destino] = _double_nao_negativo(campos[origem], origem)
    metricas["conversion_value_micros"] = _micros_de_unidade_monetaria(
        campos["metrics.conversions_value"]
    )
    mapeamento = (
        ("customer_id", "customer.id"),
        ("campaign_id", "campaign.id"),
        ("resource_name", "campaign.resource_name"),
        ("status", "campaign.status"),
        ("serving_status", "campaign.serving_status"),
        ("currency", "customer.currency_code"),
        ("date", "segments.date"),
        ("impressions", "metrics.impressions"),
        ("clicks", "metrics.clicks"),
        ("cost_micros", "metrics.cost_micros"),
        ("conversions", "metrics.conversions"),
        ("conversion_value_micros", "metrics.conversions_value"),
    )
    normalizada = {
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "resource_name": resource_name,
        "status": _enum_observado(campos["campaign.status"], "campaign.status"),
        "serving_status": _enum_observado(
            campos["campaign.serving_status"], "campaign.serving_status"
        ),
        "currency": _moeda(campos["customer.currency_code"]),
        "date": dia.isoformat(),
        **metricas,
        **_linhagem(
            grao="campaign_day",
            janela=janela,
            lido_em=lido_em,
            as_of_date=as_of_date,
            calendar_timezone=calendar_timezone,
            mapeamento=mapeamento,
        ),
    }
    return normalizada, ("campaign_day", customer_id, campaign_id, dia.isoformat())


def _normalizar_campaign_window(
    campos: Mapping[str, Any],
    janela: Mapping[str, str],
    lido_em: str,
    as_of_date: str,
    calendar_timezone: str,
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    customer_id = _id(campos["customer.id"], "customer.id")
    campaign_id = _id(campos["campaign.id"], "campaign.id")
    resource_name = _recurso_campanha(customer_id, campaign_id, campos["campaign.resource_name"])
    metricas = {
        "search_impression_share": _percentual(
            campos["metrics.search_impression_share"], "metrics.search_impression_share"
        ),
        "search_budget_lost_impression_share": _percentual(
            campos["metrics.search_budget_lost_impression_share"],
            "metrics.search_budget_lost_impression_share",
        ),
        "search_rank_lost_impression_share": _percentual(
            campos["metrics.search_rank_lost_impression_share"],
            "metrics.search_rank_lost_impression_share",
        ),
    }
    mapeamento = (
        ("customer_id", "customer.id"),
        ("campaign_id", "campaign.id"),
        ("resource_name", "campaign.resource_name"),
        ("status", "campaign.status"),
        ("serving_status", "campaign.serving_status"),
        ("search_impression_share", "metrics.search_impression_share"),
        (
            "search_budget_lost_impression_share",
            "metrics.search_budget_lost_impression_share",
        ),
        ("search_rank_lost_impression_share", "metrics.search_rank_lost_impression_share"),
    )
    normalizada = {
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "resource_name": resource_name,
        "status": _enum_observado(campos["campaign.status"], "campaign.status"),
        "serving_status": _enum_observado(
            campos["campaign.serving_status"], "campaign.serving_status"
        ),
        **metricas,
        "source_grain": "campaign_window_without_segments_date",
        **_linhagem(
            grao="campaign_window",
            janela=janela,
            lido_em=lido_em,
            as_of_date=as_of_date,
            calendar_timezone=calendar_timezone,
            mapeamento=mapeamento,
        ),
    }
    return normalizada, (
        "campaign_window",
        customer_id,
        campaign_id,
        janela["inicio"],
        janela["fim"],
    )


def _normalizar_keyword(
    campos: Mapping[str, Any],
    janela: Mapping[str, str],
    lido_em: str,
    as_of_date: str,
    calendar_timezone: str,
    *,
    aceita_quality_score_string_convertida: bool,
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    customer_id = _id(campos["customer.id"], "customer.id")
    campaign_id = _id(campos["campaign.id"], "campaign.id")
    ad_group_id = _id(campos["ad_group.id"], "ad_group.id")
    criterion_id = _id(campos["ad_group_criterion.criterion_id"], "ad_group_criterion.criterion_id")
    resource_name = _recurso_criterio(
        customer_id, ad_group_id, criterion_id, campos["ad_group_criterion.resource_name"]
    )
    normalizada = {
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "ad_group_id": ad_group_id,
        "criterion_id": criterion_id,
        "resource_name": resource_name,
        "criterion_type": _tipo_keyword(
            campos["ad_group_criterion.type"], "ad_group_criterion.type"
        ),
        "negative": _booleano_exato(
            campos["ad_group_criterion.negative"],
            "ad_group_criterion.negative",
            esperado=False,
        ),
        "status": _enum_observado(
            campos["ad_group_criterion.status"], "ad_group_criterion.status"
        ),
        "system_serving_status": _enum_observado(
            campos["ad_group_criterion.system_serving_status"],
            "ad_group_criterion.system_serving_status",
        ),
        "keyword_text": _texto(
            campos["ad_group_criterion.keyword.text"], "ad_group_criterion.keyword.text"
        ),
        "keyword_match_type": _enum(
            campos["ad_group_criterion.keyword.match_type"],
            "ad_group_criterion.keyword.match_type",
            _KEYWORD_MATCH_TYPES,
        ),
    }
    campos_qualidade = (
        (
            "ad_group_criterion.quality_info.quality_score",
            "quality_score",
            lambda valor: _quality_score(
                valor,
                aceita_string_convertida=aceita_quality_score_string_convertida,
            ),
        ),
        (
            "ad_group_criterion.quality_info.creative_quality_score",
            "ad_relevance",
            lambda valor: _componente_qualidade(
                valor,
                "ad_group_criterion.quality_info.creative_quality_score",
            ),
        ),
        (
            "ad_group_criterion.quality_info.post_click_quality_score",
            "landing_page_experience",
            lambda valor: _componente_qualidade(
                valor,
                "ad_group_criterion.quality_info.post_click_quality_score",
            ),
        ),
        (
            "ad_group_criterion.quality_info.search_predicted_ctr",
            "expected_ctr",
            lambda valor: _componente_qualidade(
                valor,
                "ad_group_criterion.quality_info.search_predicted_ctr",
            ),
        ),
    )
    for origem, destino, normalizar in campos_qualidade:
        if origem in campos:
            normalizada[destino] = normalizar(campos[origem])
    mapeamento = tuple(
        (destino, origem)
        for destino, origem in (
            ("customer_id", "customer.id"),
            ("campaign_id", "campaign.id"),
            ("ad_group_id", "ad_group.id"),
            ("criterion_id", "ad_group_criterion.criterion_id"),
            ("resource_name", "ad_group_criterion.resource_name"),
            ("criterion_type", "ad_group_criterion.type"),
            ("negative", "ad_group_criterion.negative"),
            ("status", "ad_group_criterion.status"),
            ("system_serving_status", "ad_group_criterion.system_serving_status"),
            ("keyword_text", "ad_group_criterion.keyword.text"),
            ("keyword_match_type", "ad_group_criterion.keyword.match_type"),
            ("quality_score", "ad_group_criterion.quality_info.quality_score"),
            ("ad_relevance", "ad_group_criterion.quality_info.creative_quality_score"),
            (
                "landing_page_experience",
                "ad_group_criterion.quality_info.post_click_quality_score",
            ),
            ("expected_ctr", "ad_group_criterion.quality_info.search_predicted_ctr"),
        )
        if origem in campos
    )
    normalizada.update(
        _linhagem(
            grao="keyword_criterion",
            janela=janela,
            lido_em=lido_em,
            as_of_date=as_of_date,
            calendar_timezone=calendar_timezone,
            mapeamento=mapeamento,
        )
    )
    return normalizada, (
        "keyword_criterion",
        customer_id,
        campaign_id,
        ad_group_id,
        criterion_id,
        resource_name,
    )


def _normalizar_termo(
    campos: Mapping[str, Any],
    janela: Mapping[str, str],
    lido_em: str,
    as_of_date: str,
    calendar_timezone: str,
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    customer_id = _id(campos["customer.id"], "customer.id")
    campaign_id = _id(campos["campaign.id"], "campaign.id")
    ad_group_id = _id(campos["ad_group.id"], "ad_group.id")
    search_term = _texto(
        campos["search_term_view.search_term"], "search_term_view.search_term"
    )
    resource_name = _recurso_termo_de_busca(
        customer_id,
        campaign_id,
        ad_group_id,
        search_term,
        campos["search_term_view.resource_name"],
    )
    normalizada = {
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "ad_group_id": ad_group_id,
        "resource_name": resource_name,
        "search_term": search_term,
        "status": _enum_observado(
            campos["search_term_view.status"], "search_term_view.status"
        ),
        "search_term_match_type": _enum_observado(
            campos["segments.search_term_match_type"],
            "segments.search_term_match_type",
        ),
    }
    for origem, destino in (
        ("metrics.impressions", "impressions"),
        ("metrics.clicks", "clicks"),
        ("metrics.cost_micros", "cost_micros"),
        ("metrics.conversions", "conversions"),
    ):
        if origem in _METRICAS_INTEIRAS:
            normalizada[destino] = _inteiro_proto_nao_negativo(campos[origem], origem)
        else:
            normalizada[destino] = _double_nao_negativo(campos[origem], origem)
    mapeamento = (
        ("customer_id", "customer.id"),
        ("campaign_id", "campaign.id"),
        ("ad_group_id", "ad_group.id"),
        ("resource_name", "search_term_view.resource_name"),
        ("search_term", "search_term_view.search_term"),
        ("status", "search_term_view.status"),
        ("search_term_match_type", "segments.search_term_match_type"),
        ("impressions", "metrics.impressions"),
        ("clicks", "metrics.clicks"),
        ("cost_micros", "metrics.cost_micros"),
        ("conversions", "metrics.conversions"),
    )
    normalizada.update(
        _linhagem(
            grao="search_term_view",
            janela=janela,
            lido_em=lido_em,
            as_of_date=as_of_date,
            calendar_timezone=calendar_timezone,
            mapeamento=mapeamento,
        )
    )
    return normalizada, (
        "search_term_view",
        customer_id,
        campaign_id,
        ad_group_id,
        resource_name,
    )


def _normalizar_negativa(
    grao: str,
    campos: Mapping[str, Any],
    janela: Mapping[str, str],
    lido_em: str,
    as_of_date: str,
    calendar_timezone: str,
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    customer_id = _id(campos["customer.id"], "customer.id")
    campaign_id = _id(campos["campaign.id"], "campaign.id")
    if grao == "campaign_negative":
        ad_group_id = None
        prefixo = "campaign_criterion"
        criterion_id = _id(campos[f"{prefixo}.criterion_id"], f"{prefixo}.criterion_id")
        resource_name = _texto(campos[f"{prefixo}.resource_name"], f"{prefixo}.resource_name")
        esperado = f"customers/{customer_id}/campaignCriteria/{campaign_id}~{criterion_id}"
        nivel = "CAMPAIGN"
    else:
        ad_group_id = _id(campos["ad_group.id"], "ad_group.id")
        prefixo = "ad_group_criterion"
        criterion_id = _id(campos[f"{prefixo}.criterion_id"], f"{prefixo}.criterion_id")
        resource_name = _recurso_criterio(
            customer_id, ad_group_id, criterion_id, campos[f"{prefixo}.resource_name"]
        )
        esperado = resource_name
        nivel = "AD_GROUP"
    if resource_name != esperado:
        _recusar("RESOURCE_NAME_INVALIDO", "resource_name da negativa não corresponde à identidade")
    keyword_match_type = _enum(
        campos[f"{prefixo}.keyword.match_type"],
        f"{prefixo}.keyword.match_type",
        _KEYWORD_MATCH_TYPES,
    )
    normalizada = {
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "ad_group_id": ad_group_id,
        "criterion_id": criterion_id,
        "resource_name": resource_name,
        "criterion_type": _tipo_keyword(campos[f"{prefixo}.type"], f"{prefixo}.type"),
        "negative": _booleano_exato(
            campos[f"{prefixo}.negative"],
            f"{prefixo}.negative",
            esperado=True,
        ),
        "status": _enum_observado(
            campos[f"{prefixo}.status"], f"{prefixo}.status"
        ),
        "keyword_text": _texto(campos[f"{prefixo}.keyword.text"], f"{prefixo}.keyword.text"),
        "level": nivel,
        "keyword_match_type": keyword_match_type,
        # Alias do contrato do kernel atual; continua sendo KeywordMatchType.
        "match_type": keyword_match_type,
    }
    if prefixo == "ad_group_criterion":
        normalizada["system_serving_status"] = _enum_observado(
            campos["ad_group_criterion.system_serving_status"],
            "ad_group_criterion.system_serving_status",
        )
    pares: list[tuple[str, str]] = [
        ("customer_id", "customer.id"),
        ("campaign_id", "campaign.id"),
    ]
    if ad_group_id is not None:
        pares.append(("ad_group_id", "ad_group.id"))
    pares.extend(
        (
            ("criterion_id", f"{prefixo}.criterion_id"),
            ("resource_name", f"{prefixo}.resource_name"),
            ("criterion_type", f"{prefixo}.type"),
            ("negative", f"{prefixo}.negative"),
            ("status", f"{prefixo}.status"),
            ("keyword_text", f"{prefixo}.keyword.text"),
            ("keyword_match_type", f"{prefixo}.keyword.match_type"),
            ("match_type", f"{prefixo}.keyword.match_type"),
        )
    )
    if prefixo == "ad_group_criterion":
        pares.append(
            ("system_serving_status", "ad_group_criterion.system_serving_status")
        )
    normalizada.update(
        _linhagem(
            grao=grao,
            janela=janela,
            lido_em=lido_em,
            as_of_date=as_of_date,
            calendar_timezone=calendar_timezone,
            mapeamento=pares,
        )
    )
    return normalizada, (
        grao,
        customer_id,
        campaign_id,
        ad_group_id,
        criterion_id,
        resource_name,
    )


def _chave_ordenacao(linha: Mapping[str, Any]) -> str:
    return json.dumps(
        _canonicalizar_para_hash(linha),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _canonicalizar_para_hash(valor: Any) -> Any:
    if isinstance(valor, Mapping):
        return {str(chave): _canonicalizar_para_hash(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_canonicalizar_para_hash(item) for item in valor]
    if isinstance(valor, bool) or valor is None or isinstance(valor, str):
        return valor
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        if not math.isfinite(valor):
            _recusar("RANGE_INVALIDO", "fingerprint não aceita número não finito")
        return _canonicalizar_double(valor)
    if isinstance(valor, Decimal):
        if not valor.is_finite():
            _recusar("RANGE_INVALIDO", "fingerprint não aceita decimal não finito")
        if valor == 0:
            return 0
        if valor == valor.to_integral_value():
            return int(valor)
        return format(valor.normalize(), "f")
    _recusar("TIPO_NAO_CANONICO", f"fingerprint não aceita {type(valor).__name__}")


def _fingerprint(valor: Mapping[str, Any]) -> str:
    bruto = json.dumps(
        _canonicalizar_para_hash(valor),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def normalizar_linhas_google_ads(
    linhas: Sequence[Mapping[str, Any]],
    *,
    agora: datetime,
    as_of_date: str,
    calendar_timezone: str,
    coverage_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Normaliza um lote de uma campanha ou recusa o lote inteiro.

    ``agora``, ``as_of_date``, calendário e recibo são obrigatórios. Assim, uma
    coleção omitida não vira vazio/sucesso e um dia ainda aberto não vira dado
    completo. Receita e política permanecem fora da fronteira Google.
    """

    if agora.tzinfo is None or agora.utcoffset() is None:
        _recusar("INSTANTE_INVALIDO", "agora precisa declarar fuso")
    agora = agora.astimezone(timezone.utc)
    as_of = _data(as_of_date, "as_of_date")
    nome_calendario, calendario = _timezone_calendario(calendar_timezone)
    if as_of > agora.astimezone(calendario).date():
        _recusar("DATA_APOS_AS_OF", "as_of_date está no futuro do calendário declarado")
    recibo = _recibo_cobertura(coverage_receipt)
    if recibo.customer_time_zone != nome_calendario:
        _recusar(
            "TIMEZONE_DIVERGENTE",
            "calendar_timezone precisa casar exatamente com coverage_receipt.customer_time_zone observado",
        )
    if isinstance(linhas, (str, bytes)) or not isinstance(linhas, Sequence) or not linhas:
        _recusar("LOTE_INVALIDO", "linhas precisa ser sequência não vazia")

    selected_fields_por_grao = {
        grao: recibo.grains[grao].selected_fields for grao in GRAOS_SUPORTADOS
    }

    colecoes: dict[str, list[dict[str, Any]]] = {
        "daily_metrics": [],
        "quality": [],
        "search_terms": [],
        "negatives": [],
    }
    window_metrics: dict[str, Any] | None = None
    identidades: set[tuple[str, str]] = set()
    janelas: set[tuple[str, str]] = set()
    leituras: set[str] = set()
    recursos_campanha: set[str] = set()
    moedas: set[str] = set()
    estados_campanha: set[tuple[str, str]] = set()
    duplicatas: set[tuple[Any, ...]] = set()
    criterios_por_identidade: dict[tuple[Any, ...], tuple[Any, ...]] = {}
    criterios_por_recurso: dict[str, tuple[Any, ...]] = {}
    contagens = {grao: 0 for grao in GRAOS_SUPORTADOS}

    for indice, linha_original in enumerate(linhas):
        if not isinstance(linha_original, Mapping):
            _recusar("LINHA_INVALIDA", f"linha {indice} não é objeto")
        linha = deepcopy(dict(linha_original))
        grao, campos, janela, inicio, fim, lido_em = _base_linha(
            linha,
            agora=agora,
            as_of_date=as_of,
            calendario=calendario,
            selected_fields_por_grao=selected_fields_por_grao,
        )
        customer_id = _id(campos["customer.id"], "customer.id")
        campaign_id = _id(campos["campaign.id"], "campaign.id")
        identidades.add((customer_id, campaign_id))
        janelas.add((janela["inicio"], janela["fim"]))
        leituras.add(lido_em)
        contagens[grao] += 1

        if grao == "campaign_day":
            normalizada, chave = _normalizar_campaign_day(
                campos,
                janela,
                inicio,
                fim,
                lido_em,
                as_of.isoformat(),
                nome_calendario,
            )
            colecoes["daily_metrics"].append(normalizada)
            recursos_campanha.add(normalizada["resource_name"])
            moedas.add(normalizada["currency"])
            estados_campanha.add((normalizada["status"], normalizada["serving_status"]))
        elif grao == "campaign_window":
            normalizada, chave = _normalizar_campaign_window(
                campos,
                janela,
                lido_em,
                as_of.isoformat(),
                nome_calendario,
            )
            if window_metrics is not None:
                _recusar("DUPLICATA", "mais de uma linha campaign_window no lote")
            window_metrics = normalizada
            recursos_campanha.add(normalizada["resource_name"])
            estados_campanha.add((normalizada["status"], normalizada["serving_status"]))
        elif grao == "keyword_criterion":
            normalizada, chave = _normalizar_keyword(
                campos,
                janela,
                lido_em,
                as_of.isoformat(),
                nome_calendario,
                aceita_quality_score_string_convertida=(
                    recibo.adapter_conversions.get(_CAMPO_QUALITY_SCORE)
                    == _CONVERSAO_QUALITY_SCORE_STRING
                ),
            )
            colecoes["quality"].append(normalizada)
        elif grao == "search_term_view":
            normalizada, chave = _normalizar_termo(
                campos,
                janela,
                lido_em,
                as_of.isoformat(),
                nome_calendario,
            )
            colecoes["search_terms"].append(normalizada)
        else:
            normalizada, chave = _normalizar_negativa(
                grao,
                campos,
                janela,
                lido_em,
                as_of.isoformat(),
                nome_calendario,
            )
            colecoes["negatives"].append(normalizada)

        if grao in {"keyword_criterion", "campaign_negative", "ad_group_negative"}:
            if grao == "campaign_negative":
                identidade_criterio = (
                    "CAMPAIGN",
                    normalizada["customer_id"],
                    normalizada["campaign_id"],
                    normalizada["criterion_id"],
                )
            else:
                identidade_criterio = (
                    "AD_GROUP",
                    normalizada["customer_id"],
                    normalizada["ad_group_id"],
                    normalizada["criterion_id"],
                )
            assinatura = (
                grao,
                normalizada["resource_name"],
                normalizada["criterion_type"],
                normalizada["negative"],
            )
            anterior = criterios_por_identidade.get(identidade_criterio)
            anterior_recurso = criterios_por_recurso.get(normalizada["resource_name"])
            if (anterior is not None and anterior != assinatura) or (
                anterior_recurso is not None and anterior_recurso != assinatura
            ):
                _recusar(
                    "CRITERIO_CONTRADITORIO",
                    "o mesmo resource_name/criterion foi reutilizado com grão ou polaridade diferente",
                )
            criterios_por_identidade[identidade_criterio] = assinatura
            criterios_por_recurso[normalizada["resource_name"]] = assinatura

        if chave in duplicatas:
            _recusar("DUPLICATA", f"linha duplicada no grão {grao}")
        duplicatas.add(chave)

    _validar_cobertura(recibo, contagens)
    if len(identidades) != 1:
        _recusar("IDENTIDADE_MISTURADA", "o lote mistura customer_id ou campaign_id")
    if len(janelas) != 1:
        _recusar("JANELA_MISTURADA", "o lote mistura janelas")
    janela_lote = next(iter(janelas))
    janela_recibo = (
        recibo.query_window["inicio"],
        recibo.query_window["fim"],
    )
    if janela_lote != janela_recibo:
        _recusar(
            "JANELA_COBERTURA_DIVERGENTE",
            "coverage_receipt.query_window precisa ser exatamente igual à janela de todas as linhas",
        )
    if len(leituras) != 1:
        _recusar("LEITURA_MISTURADA", "o lote mistura lido_em")
    if not colecoes["daily_metrics"]:
        _recusar("GRAO_AUSENTE", "campaign_day é obrigatório")
    if window_metrics is None:
        _recusar("GRAO_AUSENTE", "campaign_window é obrigatório")
    if len(recursos_campanha) != 1:
        _recusar("IDENTIDADE_MISTURADA", "resource_name da campanha diverge entre os grãos")
    if len(moedas) != 1:
        _recusar("MOEDA_MISTURADA", "campaign_day mistura customer.currency_code")
    if len(estados_campanha) != 1:
        _recusar(
            "STATUS_MISTURADO",
            "campaign.status ou campaign.serving_status diverge entre os grãos",
        )

    customer_id, campaign_id = next(iter(identidades))
    inicio, fim = janela_recibo
    lido_em = next(iter(leituras))
    inicio_data = date.fromisoformat(inicio)
    fim_data = date.fromisoformat(fim)
    datas_esperadas = {
        (inicio_data + timedelta(days=deslocamento)).isoformat()
        for deslocamento in range((fim_data - inicio_data).days + 1)
    }
    datas_recebidas = {linha["date"] for linha in colecoes["daily_metrics"]}
    if datas_recebidas != datas_esperadas:
        _recusar(
            "COBERTURA_DATAS_INEXATA",
            "campaign_day completo precisa cobrir cada data inclusiva exatamente uma vez; "
            f"faltantes={sorted(datas_esperadas - datas_recebidas)}; "
            f"extras={sorted(datas_recebidas - datas_esperadas)}",
        )
    colecoes["daily_metrics"].sort(key=lambda linha: linha["date"])
    for nome, valores in colecoes.items():
        if nome == "daily_metrics":
            continue
        valores.sort(key=_chave_ordenacao)
    status, serving_status = next(iter(estados_campanha))
    bloqueios_decisorios: list[str] = []
    if not colecoes["quality"]:
        bloqueios_decisorios.append("quality ausente")
    for indice, qualidade in enumerate(colecoes["quality"]):
        for campo in (
            "quality_score",
            "ad_relevance",
            "landing_page_experience",
            "expected_ctr",
        ):
            if campo not in qualidade:
                bloqueios_decisorios.append(f"quality[{indice}].{campo} ausente")
    elegivel_para_decisao = not bloqueios_decisorios
    manifesto = {
        "schema_version": VERSAO_NORMALIZADOR_GOOGLE_ADS,
        "conversion_value": {
            "source_field": "metrics.conversions_value",
            "source_unit": "protobuf_double_json_number",
            "currency_source_field": "customer.currency_code",
            "target_field": "conversion_value_micros",
            "target_unit": "currency_micros",
            "conversion": "Decimal(str(source)) * 1000000; exact integer micros required",
            "double_noise": "any binary-double noise that does not yield exact integer micros is rejected fail-closed",
        },
        "scalar_encoding": {
            "capture": "explicit flattened dotted projection produced after MessageToDict(preserving_proto_field_name=True, always_print_fields_with_no_presence=False)",
            "flattening_projection": "post-MessageToDict ProtoJSON -> explicit dotted source_fields constrained by per-grain selected_fields",
            "presence_evidence": "selected_fields proves GAQL selection, not measurement or live protobuf presence; the synthetic fixture does not prove real presence semantics",
            "omitted_defaults": "zero-fill is forbidden: omitted required scalar rejects; omitted nullable Quality Info remains absent",
            "identity_int64": "canonical decimal ProtoJSON string in 1..2^63-1, without leading zero",
        "metric_int64": "canonical decimal ProtoJSON string in 0..2^63-1, without leading zero -> canonical integer",
            "quality_score_int32": "JSON integer 1..10; canonical decimal string only when coverage_receipt.adapter_conversions explicitly declares it",
            "double": "JSON number -> canonical integer when mathematically integral; negative zero -> zero",
            "enum": "proto enum name string; SearchTermMatchType is preserved separately from KeywordMatchType",
        },
        "coverage": "receipt query_window equals every row window; all six grains declare selected_fields; campaign_day completo covers every inclusive query_window date exactly once",
        "calendar_authority": "coverage_receipt.customer_time_zone is observed account IANA evidence and must exactly equal calendar_timezone",
        "kernel_temporal_gate": "the kernel uses the timezone carried by its explicit agora argument for replay as-of and future-read checks; window closure compares lido_em.date() in lido_em's normalized offset, naive datetimes fall back to UTC in _dt, and every ambiguity remains fail-closed",
        "search_term_resource_suffix": "URL-safe base64 without padding over exact UTF-8 bytes; premise remains unverified against a live GoogleAdsRow",
        "raw_grains": list(GRAOS_SUPORTADOS),
        "fingerprint": "sha256 of canonical normalized contract including coverage and temporal calendar",
    }
    saida: dict[str, Any] = {
        "observation_version": 1,
        "api_namespace": "v25",
        "release_baseline": "v25.1",
        "source": {
            "nome": "google_ads_rows_flattened_after_messagetodict",
            "tipo": "normalizacao_hermetica_com_recibo",
            "estado": "completa" if elegivel_para_decisao else "parcial",
        },
        "lido_em": lido_em,
        "as_of_date": as_of.isoformat(),
        "calendar_timezone": nome_calendario,
        "janela": {"inicio": inicio, "fim": fim},
        "campaign": {
            "customer_id": customer_id,
            "campaign_id": campaign_id,
            "resource_name": next(iter(recursos_campanha)),
            "currency": next(iter(moedas)),
            "status": status,
            "serving_status": serving_status,
        },
        "daily_metrics": colecoes["daily_metrics"],
        "window_metrics": window_metrics,
        "quality": colecoes["quality"],
        "search_terms": colecoes["search_terms"],
        "negatives": colecoes["negatives"],
        "normalization_manifest": manifesto,
        "raw_row_counts": contagens,
        "coverage_receipt": recibo.serializar(),
        "decision_eligible": elegivel_para_decisao,
        "decision_blockers": bloqueios_decisorios,
    }
    saida["normalization_fingerprint"] = _fingerprint(saida)
    return saida


__all__ = [
    "GRAOS_SUPORTADOS",
    "VERSAO_NORMALIZADOR_GOOGLE_ADS",
    "VERSAO_RECIBO_COBERTURA_GOOGLE_ADS",
    "CoberturaGraoGoogleAds",
    "ErroNormalizacaoGoogleAds",
    "EstadoCoberturaGoogleAds",
    "ReciboCoberturaGoogleAds",
    "normalizar_linhas_google_ads",
]
