"""Prova hermética da fronteira raw Google Ads → contrato do Lab."""

from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from volc_ads.inteligencia_decisao import (
    ErroNormalizacaoGoogleAds,
    executar_pipeline,
    normalizar_linhas_google_ads,
)

AGORA = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
FIXTURE = (
    Path(__file__).parents[2]
    / "volc_ads"
    / "inteligencia_decisao"
    / "dados"
    / "linhas_google_ads_sinteticas.json"
)
MANIFESTO = (
    Path(__file__).parents[2]
    / "docs"
    / "architecture"
    / "VOLC-DECISION-LAB-RAW-MAPPING.json"
)

FAMILIAS_IDENTIDADE = (
    ("customer", "campaign_day", "customer.id"),
    ("campaign", "campaign_window", "campaign.id"),
    ("ad_group", "search_term_view", "ad_group.id"),
    (
        "campaign_criterion",
        "campaign_negative",
        "campaign_criterion.criterion_id",
    ),
    (
        "ad_group_criterion_positive",
        "keyword_criterion",
        "ad_group_criterion.criterion_id",
    ),
    (
        "ad_group_criterion_negative",
        "ad_group_negative",
        "ad_group_criterion.criterion_id",
    ),
)


def _dados() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _linhas() -> list[dict]:
    return deepcopy(_dados()["google_ads_rows"])


def _por_grao(linhas: list[dict], grao: str) -> dict:
    return next(linha for linha in linhas if linha["raw_grain"] == grao)


def _normalizado(
    linhas: list[dict] | None = None,
    *,
    coverage_receipt: dict | None = None,
    as_of_date: str | None = None,
    calendar_timezone: str | None = None,
    agora: datetime = AGORA,
) -> dict:
    fixture = _dados()
    return normalizar_linhas_google_ads(
        _linhas() if linhas is None else linhas,
        agora=agora,
        as_of_date=as_of_date or fixture["as_of_date"],
        calendar_timezone=calendar_timezone or fixture["calendar_timezone"],
        coverage_receipt=coverage_receipt or deepcopy(fixture["coverage_receipt"]),
    )


def _recibo_para(linhas: list[dict], **estados: str) -> dict:
    recibo = deepcopy(_dados()["coverage_receipt"])
    for grao, item in recibo["grains"].items():
        contagem = sum(linha["raw_grain"] == grao for linha in linhas)
        item["linhas_recebidas"] = contagem
        item["estado"] = estados.get(
            grao,
            "completo" if contagem else "vazio_confirmado",
        )
    return recibo


def _observacao_para_kernel() -> dict:
    fixture = _dados()
    google = _normalizado(fixture["google_ads_rows"])
    assert google["decision_eligible"] is True
    contexto = deepcopy(fixture["observation_context"])
    campanha = {**contexto.pop("campaign"), **google["campaign"]}
    return {
        **contexto,
        **google,
        "scenario_id": fixture["scenario_id"],
        "label": fixture["label"],
        "campaign": campanha,
        # Receita é anexada pelo chamador. Ela não entra na fronteira Google.
        "external_revenue": deepcopy(fixture["external_revenue"]),
    }


def test_normaliza_os_seis_graos_com_identidade_e_linhagem_explicitas():
    resultado = _normalizado()

    assert resultado["campaign"] == {
        "customer_id": "9990000001",
        "campaign_id": "88000000001",
        "resource_name": "customers/9990000001/campaigns/88000000001",
        "currency": "BRL",
        "status": "ENABLED",
        "serving_status": "SERVING",
    }
    assert resultado["raw_row_counts"] == {
        "campaign_day": 3,
        "campaign_window": 1,
        "keyword_criterion": 1,
        "search_term_view": 1,
        "campaign_negative": 1,
        "ad_group_negative": 1,
    }
    assert resultado["coverage_receipt"]["customer_time_zone"] == "America/Sao_Paulo"
    assert resultado["coverage_receipt"]["query_window"] == {
        "inicio": "2026-08-25",
        "fim": "2026-08-27",
    }
    assert resultado["coverage_receipt"]["adapter_conversions"] == {}
    for grao, recibo in resultado["coverage_receipt"]["grains"].items():
        assert recibo["selected_fields"]
        assert len(recibo["selected_fields"]) == len(set(recibo["selected_fields"]))
    linhas_normalizadas = [
        *resultado["daily_metrics"],
        resultado["window_metrics"],
        *resultado["quality"],
        *resultado["search_terms"],
        *resultado["negatives"],
    ]
    assert {linha["raw_grain"] for linha in linhas_normalizadas} == {
        "campaign_day",
        "campaign_window",
        "keyword_criterion",
        "search_term_view",
        "campaign_negative",
        "ad_group_negative",
    }
    for linha in linhas_normalizadas:
        assert linha["janela"] == {"inicio": "2026-08-25", "fim": "2026-08-27"}
        assert linha["lido_em"] == "2026-08-28T11:00:00Z"
        assert linha["as_of_date"] == "2026-08-27"
        assert linha["calendar_timezone"] == "America/Sao_Paulo"
        assert linha["fields"]
        assert all(set(item) == {"target_field", "source_field"} for item in linha["fields"])


def test_converte_valor_decimal_para_micros_sem_confundir_null_e_zero():
    resultado = _normalizado()
    dias = {linha["date"]: linha for linha in resultado["daily_metrics"]}
    termo = resultado["search_terms"][0]

    assert dias["2026-08-25"]["conversion_value_micros"] == 15_000_000
    assert dias["2026-08-27"]["conversion_value_micros"] == 17_000_000
    assert termo["cost_micros"] == 0
    assert termo["conversions"] == 0
    assert resultado["daily_metrics"][0]["conversions"] == 5


def test_preserva_quality_score_componentes_e_negativas_por_nivel():
    resultado = _normalizado()
    qualidade = resultado["quality"][0]
    negativas = {linha["level"]: linha for linha in resultado["negatives"]}

    assert qualidade["quality_score"] == 8
    assert qualidade["ad_relevance"] == "ABOVE_AVERAGE"
    assert qualidade["landing_page_experience"] == "AVERAGE"
    assert qualidade["expected_ctr"] == "ABOVE_AVERAGE"
    assert qualidade["criterion_id"] == "771001"
    assert qualidade["resource_name"].endswith("/770001~771001")

    assert negativas["CAMPAIGN"]["ad_group_id"] is None
    assert negativas["CAMPAIGN"]["criterion_id"] == "8801"
    assert negativas["CAMPAIGN"]["match_type"] == "BROAD"
    assert negativas["CAMPAIGN"]["keyword_match_type"] == "BROAD"
    assert negativas["CAMPAIGN"]["negative"] is True
    assert negativas["AD_GROUP"]["ad_group_id"] == "770001"
    assert negativas["AD_GROUP"]["criterion_id"] == "8802"
    assert negativas["AD_GROUP"]["match_type"] == "EXACT"
    assert negativas["AD_GROUP"]["system_serving_status"] == "ELIGIBLE"


def test_campaign_window_nao_tem_segments_date_nem_media_de_percentuais_diarios():
    resultado = _normalizado()
    janela = resultado["window_metrics"]

    assert janela["raw_grain"] == "campaign_window"
    assert janela["source_grain"] == "campaign_window_without_segments_date"
    assert janela["search_budget_lost_impression_share"] == 0.29
    assert all(item["source_field"] != "segments.date" for item in janela["fields"])


def test_fingerprint_e_saida_independem_da_ordem_das_linhas_raw():
    linhas = _linhas()
    direto = _normalizado(linhas)
    reverso = _normalizado(list(reversed(linhas)))

    assert direto["normalization_fingerprint"] == reverso["normalization_fingerprint"]
    assert direto == reverso


def test_normalizador_nao_muta_as_linhas_de_entrada():
    linhas = _linhas()
    antes = deepcopy(linhas)

    _normalizado(linhas)

    assert linhas == antes


def test_saida_atravessa_kernel_atual_e_reproduz_diagnostico_e_proposta():
    fixture = _dados()
    resultado = executar_pipeline(_observacao_para_kernel(), agora=AGORA)

    assert resultado["estado_da_leitura"] == fixture["expected"]["estado_da_leitura"]
    assert resultado["veredito"]["tipo"] == fixture["expected"]["veredito"]
    assert len(resultado["propostas_tipadas"]) == fixture["expected"]["propostas"]
    assert resultado["propostas_tipadas"][0]["operacao"] == fixture["expected"]["operacao"]
    assert resultado["propostas_tipadas"][0]["aprovacao"] == "nao_submetida"
    assert resultado["propostas_tipadas"][0]["aplicacao"] == "nao_executada"
    assert resultado["execucao"]["mutacoes_executadas"] == fixture["expected"]["mutacoes_executadas"]


def test_receita_externa_permanece_fora_do_normalizador_google():
    fixture = _dados()
    resultado = _normalizado(fixture["google_ads_rows"])

    assert fixture["external_revenue"]
    assert "external_revenue" not in resultado
    assert not any(
        "revenue" in source_field
        for linha in fixture["google_ads_rows"]
        for source_field in linha["source_fields"]
    )


def test_manifesto_reflete_os_campos_exatos_da_fixture_e_da_saida():
    manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    fixture = _dados()
    saida = _normalizado(fixture["google_ads_rows"])
    mapeamentos = {item["raw_grain"]: item for item in manifesto["mappings"]}

    assert set(mapeamentos) == set(saida["normalization_manifest"]["raw_grains"])
    for linha in fixture["google_ads_rows"]:
        mapeamento = mapeamentos[linha["raw_grain"]]
        assert set(linha["source_fields"]) == set(mapeamento["required_source_fields"]) | set(
            mapeamento.get("optional_nullable_source_fields", [])
        )
    assert set(saida) == set(manifesto["batch_output"]["top_level_fields"])
    assert set(saida["campaign"]) == set(manifesto["batch_output"]["campaign_fields"])
    assert manifesto["batch_output"]["external_revenue"].startswith("absent")
    assert manifesto["schema_version"] == 4
    assert manifesto["status"] == "synthetic_hermetic_contract_hardening_proven_only"
    assert "flattened after MessageToDict" in manifesto["scope"]["input"]
    assert "zero-fill is forbidden" in manifesto["raw_row_envelope"][
        "projection_between_message_to_dict_and_boundary"
    ]["omitted_no_presence_defaults"]
    assert "lido_em.date()" in manifesto["temporal_authority"]["kernel"]
    assert "naive datetimes fall back to UTC" in manifesto["temporal_authority"]["kernel"]
    assert "binary-double noise" in mapeamentos["campaign_day"]["rule"]
    assert "Google Ads collection or a production GoogleAdsRow adapter" in manifesto[
        "not_proven_here"
    ]
    assert (
        "real protobuf scalar presence or an adapter that proves omission versus observed zero"
        in manifesto["not_proven_here"]
    )


def test_recusa_identidade_misturada_sem_produzir_resultado():
    linhas = _linhas()
    dia = _por_grao(linhas, "campaign_day")
    dia["source_fields"]["campaign.id"] = "88000000002"
    dia["source_fields"]["campaign.resource_name"] = (
        "customers/9990000001/campaigns/88000000002"
    )

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "IDENTIDADE_MISTURADA"


@pytest.mark.parametrize("familia,grao,campo", FAMILIAS_IDENTIDADE)
def test_recusa_identidade_omitida_por_familia(
    familia: str,
    grao: str,
    campo: str,
):
    linhas = _linhas()
    del _por_grao(linhas, grao)["source_fields"][campo]

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "CAMPO_AUSENTE", familia
    assert campo in erro.value.detalhe


@pytest.mark.parametrize("familia,grao,campo", FAMILIAS_IDENTIDADE)
@pytest.mark.parametrize("valor", ["0", "01", str(2**63)])
def test_recusa_identidade_zero_leading_zero_ou_overflow_antes_do_resource_name(
    familia: str,
    grao: str,
    campo: str,
    valor: str,
):
    linhas = _linhas()
    _por_grao(linhas, grao)["source_fields"][campo] = valor

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "IDENTIDADE_INVALIDA", familia
    assert campo in erro.value.detalhe


def test_recusa_moeda_misturada_ou_malformada():
    misturada = _linhas()
    _por_grao(misturada, "campaign_day")["source_fields"]["customer.currency_code"] = "USD"
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(misturada)
    assert erro.value.codigo == "MOEDA_MISTURADA"

    malformada = _linhas()
    _por_grao(malformada, "campaign_day")["source_fields"]["customer.currency_code"] = "brl"
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_moeda:
        _normalizado(malformada)
    assert erro_moeda.value.codigo == "MOEDA_INVALIDA"


def test_recusa_granularidade_misturada_e_segments_date_na_janela():
    linhas = _linhas()
    janela = _por_grao(linhas, "campaign_window")
    janela["source_fields"]["segments.date"] = "2026-08-27"

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "GRAO_MISTURADO"


@pytest.mark.parametrize("campo,valor", [("inicio", "2026-08-24"), ("fim", "2026-08-29")])
def test_recusa_janela_misturada_ou_futura(campo: str, valor: str):
    linhas = _linhas()
    keyword = _por_grao(linhas, "keyword_criterion")
    keyword["janela"][campo] = valor

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo in {"JANELA_MISTURADA", "DATA_APOS_AS_OF"}


def test_recusa_lido_em_misturado_ou_futuro():
    misturado = _linhas()
    _por_grao(misturado, "keyword_criterion")["lido_em"] = "2026-08-28T10:00:00Z"
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(misturado)
    assert erro.value.codigo == "LEITURA_MISTURADA"

    futuro = _linhas()
    _por_grao(futuro, "keyword_criterion")["lido_em"] = "2026-08-28T12:00:01Z"
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_futuro:
        _normalizado(futuro)
    assert erro_futuro.value.codigo == "DATA_FUTURA"


def test_recusa_data_futura_ou_fora_da_janela():
    for data in ("2026-08-24", "2026-08-29"):
        linhas = _linhas()
        _por_grao(linhas, "campaign_day")["source_fields"]["segments.date"] = data
        with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
            _normalizado(linhas)
        assert erro.value.codigo == "JANELA_MISTURADA"


@pytest.mark.parametrize("grao", ["campaign_day", "keyword_criterion", "search_term_view", "campaign_negative", "ad_group_negative"])
def test_recusa_duplicata_em_cada_grao(grao: str):
    linhas = _linhas()
    linhas.append(deepcopy(_por_grao(linhas, grao)))

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "DUPLICATA"


@pytest.mark.parametrize(
    "score,codigo",
    [
        (0, "RANGE_INVALIDO"),
        (11, "RANGE_INVALIDO"),
        ("8", "CODIFICACAO_ESCALAR_INVALIDA"),
        (True, "CODIFICACAO_ESCALAR_INVALIDA"),
        (7.5, "CODIFICACAO_ESCALAR_INVALIDA"),
    ],
)
def test_recusa_quality_score_fora_de_um_a_dez_ou_fora_do_protojson(score, codigo: str):
    linhas = _linhas()
    _por_grao(linhas, "keyword_criterion")["source_fields"][
        "ad_group_criterion.quality_info.quality_score"
    ] = score

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == codigo


def test_quality_score_int32_aceita_numero_e_string_so_com_conversao_declarada():
    resultado = _normalizado()
    assert resultado["quality"][0]["quality_score"] == 8

    string_sem_declaracao = _linhas()
    _por_grao(string_sem_declaracao, "keyword_criterion")["source_fields"][
        "ad_group_criterion.quality_info.quality_score"
    ] = "8"
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_sem_declaracao:
        _normalizado(string_sem_declaracao)
    assert erro_sem_declaracao.value.codigo == "CODIFICACAO_ESCALAR_INVALIDA"

    recibo = deepcopy(_dados()["coverage_receipt"])
    recibo["adapter_conversions"] = {
        "ad_group_criterion.quality_info.quality_score": (
            "int32_to_canonical_decimal_string"
        )
    }
    convertido = _normalizado(
        string_sem_declaracao,
        coverage_receipt=recibo,
    )
    assert convertido["quality"][0]["quality_score"] == 8

    string_nao_canonica = _linhas()
    _por_grao(string_nao_canonica, "keyword_criterion")["source_fields"][
        "ad_group_criterion.quality_info.quality_score"
    ] = "08"
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_nao_canonico:
        _normalizado(string_nao_canonica, coverage_receipt=recibo)
    assert erro_nao_canonico.value.codigo == "CODIFICACAO_ESCALAR_INVALIDA"


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("ad_group_criterion.quality_info.creative_quality_score", "UNKNOWN"),
        ("ad_group_criterion.quality_info.post_click_quality_score", ""),
        ("ad_group_criterion.quality_info.search_predicted_ctr", "HOTEL"),
    ],
)
def test_recusa_componentes_de_qualidade_fora_do_enum(campo: str, valor):
    linhas = _linhas()
    _por_grao(linhas, "keyword_criterion")["source_fields"][campo] = valor

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "ENUM_INVALIDO"


@pytest.mark.parametrize("valor", [-0.01, 1.01, True, "0.29"])
def test_recusa_percentual_fora_de_zero_a_um(valor):
    linhas = _linhas()
    _por_grao(linhas, "campaign_window")["source_fields"][
        "metrics.search_budget_lost_impression_share"
    ] = valor

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo in {"PERCENTUAL_INVALIDO", "RANGE_INVALIDO"}


@pytest.mark.parametrize(
    "grao,campo,valor",
    [
        ("campaign_day", "metrics.clicks", -1),
        ("campaign_day", "metrics.impressions", 1.5),
        ("search_term_view", "metrics.cost_micros", True),
        ("campaign_day", "metrics.conversions", "5"),
        ("campaign_day", "metrics.cost_micros", float("nan")),
        ("campaign_day", "metrics.conversions_value", "1.0000001"),
    ],
)
def test_recusa_ranges_e_precisao_invalidos(grao: str, campo: str, valor):
    linhas = _linhas()
    _por_grao(linhas, grao)["source_fields"][campo] = valor

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo in {
        "CODIFICACAO_ESCALAR_INVALIDA",
        "RANGE_INVALIDO",
        "PRECISAO_MONETARIA_INVALIDA",
    }


def test_recusa_ruido_de_double_monetario_fail_closed():
    linhas = _linhas()
    _por_grao(linhas, "campaign_day")["source_fields"][
        "metrics.conversions_value"
    ] = 0.30000000000000004

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "PRECISAO_MONETARIA_INVALIDA"


@pytest.mark.parametrize("grao,campo", [("campaign_negative", "campaign_criterion.keyword.match_type"), ("ad_group_negative", "ad_group_criterion.keyword.match_type")])
def test_recusa_match_type_invalido(grao: str, campo: str):
    linhas = _linhas()
    _por_grao(linhas, grao)["source_fields"][campo] = "HOTEL"

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "ENUM_INVALIDO"


def test_recusa_resource_name_incompativel_com_ids():
    linhas = _linhas()
    _por_grao(linhas, "keyword_criterion")["source_fields"][
        "ad_group_criterion.resource_name"
    ] = "customers/9990000001/adGroupCriteria/770001~999999"

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "RESOURCE_NAME_INVALIDO"


def test_recusa_grao_desconhecido_e_campo_extra():
    desconhecido = _linhas()
    _por_grao(desconhecido, "search_term_view")["raw_grain"] = "asset_group"
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(desconhecido)
    assert erro.value.codigo == "GRAO_INVALIDO"

    campo_extra = _linhas()
    _por_grao(campo_extra, "campaign_day")["source_fields"]["metrics.ctr"] = 0.1
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_extra:
        _normalizado(campo_extra)
    assert erro_extra.value.codigo == "GRAO_MISTURADO"


def test_recusa_sem_graos_obrigatorios():
    sem_dia = [linha for linha in _linhas() if linha["raw_grain"] != "campaign_day"]
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_dia:
        _normalizado(sem_dia, coverage_receipt=_recibo_para(sem_dia))
    assert erro_dia.value.codigo == "COBERTURA_INELEGIVEL"

    sem_janela = [linha for linha in _linhas() if linha["raw_grain"] != "campaign_window"]
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_janela:
        _normalizado(sem_janela, coverage_receipt=_recibo_para(sem_janela))
    assert erro_janela.value.codigo == "COBERTURA_INELEGIVEL"


def test_recibo_tipado_distingue_vazio_confirmado_e_quality_vazia_inelegivel():
    linhas = [
        linha
        for linha in _linhas()
        if linha["raw_grain"] in {"campaign_day", "campaign_window"}
    ]
    resultado = _normalizado(linhas, coverage_receipt=_recibo_para(linhas))

    recibo_dia = resultado["coverage_receipt"]["grains"]["campaign_day"]
    recibo_termo = resultado["coverage_receipt"]["grains"]["search_term_view"]
    assert recibo_dia["estado"] == "completo"
    assert recibo_dia["linhas_recebidas"] == 3
    assert "segments.date" in recibo_dia["selected_fields"]
    assert recibo_termo["estado"] == "vazio_confirmado"
    assert recibo_termo["linhas_recebidas"] == 0
    assert "segments.search_term_match_type" in recibo_termo["selected_fields"]
    assert resultado["quality"] == []
    assert resultado["search_terms"] == []
    assert resultado["negatives"] == []
    assert resultado["source"]["estado"] == "parcial"
    assert resultado["decision_eligible"] is False
    assert resultado["decision_blockers"] == ["quality ausente"]


@pytest.mark.parametrize("estado", ["nao_consultado", "falha", "parcial"])
def test_recusa_cobertura_incompleta_sem_promover_fonte(estado: str):
    linhas = [
        linha for linha in _linhas() if linha["raw_grain"] != "search_term_view"
    ]
    recibo = _recibo_para(linhas, search_term_view=estado)

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas, coverage_receipt=recibo)

    assert erro.value.codigo == "COBERTURA_INELEGIVEL"
    assert estado in erro.value.detalhe


def test_recusa_contagem_de_cobertura_incoerente():
    recibo = deepcopy(_dados()["coverage_receipt"])
    recibo["grains"]["campaign_day"]["linhas_recebidas"] = 2

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(coverage_receipt=recibo)

    assert erro.value.codigo == "COBERTURA_INCONSISTENTE"


def test_cobertura_e_calendario_participam_do_fingerprint():
    resultado = _normalizado()
    sem_hash = {
        chave: valor
        for chave, valor in resultado.items()
        if chave != "normalization_fingerprint"
    }
    bruto = json.dumps(
        sem_hash,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert resultado["normalization_fingerprint"] == hashlib.sha256(
        bruto.encode("utf-8")
    ).hexdigest()

    alterado = deepcopy(sem_hash)
    alterado["coverage_receipt"]["grains"]["search_term_view"]["estado"] = "parcial"
    bruto_alterado = json.dumps(
        alterado,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert hashlib.sha256(bruto_alterado.encode("utf-8")).hexdigest() != resultado[
        "normalization_fingerprint"
    ]
    assert resultado["as_of_date"] == "2026-08-27"
    assert resultado["calendar_timezone"] == "America/Sao_Paulo"


@pytest.mark.parametrize(
    "grao,campo",
    [
        ("campaign_negative", "campaign_criterion.negative"),
        ("ad_group_negative", "ad_group_criterion.negative"),
    ],
)
def test_recusa_negativa_com_polaridade_falsa(grao: str, campo: str):
    linhas = _linhas()
    _por_grao(linhas, grao)["source_fields"][campo] = False

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "POLARIDADE_INVALIDA"


@pytest.mark.parametrize(
    "grao,campo",
    [
        ("campaign_negative", "campaign_criterion.type"),
        ("ad_group_negative", "ad_group_criterion.type"),
    ],
)
def test_recusa_negativa_de_tipo_nao_keyword(grao: str, campo: str):
    linhas = _linhas()
    _por_grao(linhas, grao)["source_fields"][campo] = "PLACEMENT"

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "TIPO_CRITERIO_INVALIDO"


def test_recusa_keyword_positiva_marcada_como_negativa():
    linhas = _linhas()
    _por_grao(linhas, "keyword_criterion")["source_fields"][
        "ad_group_criterion.negative"
    ] = True

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "POLARIDADE_INVALIDA"


def test_recusa_reutilizacao_contraditoria_do_mesmo_criterio_entre_graos():
    linhas = _linhas()
    keyword = _por_grao(linhas, "keyword_criterion")["source_fields"]
    negativa = _por_grao(linhas, "ad_group_negative")["source_fields"]
    negativa["ad_group_criterion.criterion_id"] = keyword[
        "ad_group_criterion.criterion_id"
    ]
    negativa["ad_group_criterion.resource_name"] = keyword[
        "ad_group_criterion.resource_name"
    ]

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "CRITERIO_CONTRADITORIO"


def test_recusa_mesmo_criterion_positivo_negativo_com_representacao_diferente():
    linhas = _linhas()
    keyword = _por_grao(linhas, "keyword_criterion")["source_fields"]
    negativa = _por_grao(linhas, "ad_group_negative")["source_fields"]
    negativa["ad_group_criterion.criterion_id"] = (
        "0" + keyword["ad_group_criterion.criterion_id"]
    )
    negativa["ad_group_criterion.resource_name"] = keyword[
        "ad_group_criterion.resource_name"
    ].replace("~771001", "~0771001")

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "IDENTIDADE_INVALIDA"


def test_as_of_e_calendario_impedem_dia_ainda_aberto_na_leitura():
    linhas = _linhas()
    for linha in linhas:
        linha["lido_em"] = "2026-08-28T01:00:00Z"

    recibo_utc = deepcopy(_dados()["coverage_receipt"])
    recibo_utc["customer_time_zone"] = "UTC"
    utc = _normalizado(
        linhas,
        calendar_timezone="UTC",
        coverage_receipt=recibo_utc,
    )
    assert utc["decision_eligible"] is True

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas, calendar_timezone="America/Sao_Paulo")
    assert erro.value.codigo == "AS_OF_INVALIDO"


def test_recusa_janela_depois_do_as_of_e_timezone_desconhecido():
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_as_of:
        _normalizado(as_of_date="2026-08-26")
    assert erro_as_of.value.codigo == "DATA_APOS_AS_OF"

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_timezone:
        _normalizado(calendar_timezone="VOLC/Inventado")
    assert erro_timezone.value.codigo == "TIMEZONE_INVALIDO"


def test_quality_ausente_permanece_ausente_e_bloqueia_travessia_decisoria():
    linhas = _linhas()
    campos = _por_grao(linhas, "keyword_criterion")["source_fields"]
    del campos["ad_group_criterion.quality_info.quality_score"]
    del campos["ad_group_criterion.quality_info.creative_quality_score"]
    del campos["ad_group_criterion.quality_info.post_click_quality_score"]
    del campos["ad_group_criterion.quality_info.search_predicted_ctr"]

    resultado = _normalizado(linhas)
    qualidade = resultado["quality"][0]

    assert "quality_score" not in qualidade
    assert "ad_relevance" not in qualidade
    assert "landing_page_experience" not in qualidade
    assert "expected_ctr" not in qualidade
    assert resultado["source"]["estado"] == "parcial"
    assert resultado["decision_eligible"] is False
    assert len(resultado["decision_blockers"]) == 4


def test_canonicaliza_inteiros_doubles_decimal_e_zero_antes_do_hash():
    cinco = _linhas()
    _por_grao(cinco, "campaign_day")["source_fields"]["metrics.conversions"] = 5
    cinco_float = _linhas()
    _por_grao(cinco_float, "campaign_day")["source_fields"][
        "metrics.conversions"
    ] = 5.0
    assert _normalizado(cinco)["normalization_fingerprint"] == _normalizado(
        cinco_float
    )["normalization_fingerprint"]

    zero_negativo = _linhas()
    _por_grao(zero_negativo, "search_term_view")["source_fields"][
        "metrics.conversions"
    ] = -0.0
    zero_positivo = _linhas()
    _por_grao(zero_positivo, "search_term_view")["source_fields"][
        "metrics.conversions"
    ] = 0.0
    resultado_zero = _normalizado(zero_negativo)
    assert resultado_zero["normalization_fingerprint"] == _normalizado(zero_positivo)[
        "normalization_fingerprint"
    ]
    assert resultado_zero["search_terms"][0]["conversions"] == 0

    decimal_inteiro = _linhas()
    _por_grao(decimal_inteiro, "campaign_day")["source_fields"][
        "metrics.conversions_value"
    ] = 5
    decimal_double = _linhas()
    _por_grao(decimal_double, "campaign_day")["source_fields"][
        "metrics.conversions_value"
    ] = 5.0
    assert _normalizado(decimal_inteiro)["normalization_fingerprint"] == _normalizado(
        decimal_double
    )["normalization_fingerprint"]


def test_codificacao_escalar_explicita_alinha_messagetodict_e_saida_canonica():
    resultado = _normalizado()
    assert isinstance(_por_grao(_linhas(), "campaign_day")["source_fields"]["metrics.impressions"], str)
    assert resultado["daily_metrics"][0]["impressions"] == 700

    inteiro_json_incorreto = _linhas()
    _por_grao(inteiro_json_incorreto, "campaign_day")["source_fields"][
        "metrics.impressions"
    ] = 700
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_inteiro:
        _normalizado(inteiro_json_incorreto)
    assert erro_inteiro.value.codigo == "CODIFICACAO_ESCALAR_INVALIDA"

    double_json_incorreto = _linhas()
    _por_grao(double_json_incorreto, "campaign_day")["source_fields"][
        "metrics.conversions"
    ] = "5.0"
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_double:
        _normalizado(double_json_incorreto)
    assert erro_double.value.codigo == "RANGE_INVALIDO"


def test_separa_search_term_match_type_de_keyword_match_type():
    resultado = _normalizado()
    termo = resultado["search_terms"][0]
    negativa = resultado["negatives"][0]

    assert termo["search_term_match_type"] == "PHRASE"
    assert "keyword_match_type" not in termo
    assert "match_type" not in termo
    assert negativa["keyword_match_type"] in {"EXACT", "BROAD"}
    assert negativa["match_type"] == negativa["keyword_match_type"]

    linhas = _linhas()
    _por_grao(linhas, "search_term_view")["source_fields"][
        "segments.search_term_match_type"
    ] = "phrase"
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)
    assert erro.value.codigo == "ENUM_INVALIDO"


def test_preserva_status_e_serving_status_e_bloqueia_ausencia():
    resultado = _normalizado()
    assert resultado["campaign"]["status"] == "ENABLED"
    assert resultado["campaign"]["serving_status"] == "SERVING"
    assert resultado["quality"][0]["status"] == "ENABLED"
    assert resultado["quality"][0]["system_serving_status"] == "ELIGIBLE"
    assert resultado["search_terms"][0]["status"] == "NONE"

    linhas = _linhas()
    del _por_grao(linhas, "keyword_criterion")["source_fields"][
        "ad_group_criterion.system_serving_status"
    ]
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)
    assert erro.value.codigo == "CAMPO_AUSENTE"


def test_recusa_sufixo_base64_de_termo_incoerente_com_search_term():
    linhas = _linhas()
    _por_grao(linhas, "search_term_view")["source_fields"][
        "search_term_view.search_term"
    ] = "outro termo"

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "RESOURCE_NAME_INVALIDO"


def test_daily_metrics_sai_em_ordem_cronologica_independente_das_metricas():
    linhas = _linhas()
    dias = [linha for linha in linhas if linha["raw_grain"] == "campaign_day"]
    for linha, cliques in zip(dias, ("99", "1", "50")):
        linha["source_fields"]["metrics.clicks"] = cliques

    resultado = _normalizado(linhas)

    assert [linha["date"] for linha in resultado["daily_metrics"]] == [
        "2026-08-25",
        "2026-08-26",
        "2026-08-27",
    ]


def test_recusa_campaign_day_declarado_completo_com_apenas_um_de_tres_dias():
    linhas = [
        linha
        for linha in _linhas()
        if linha["raw_grain"] != "campaign_day"
        or linha["source_fields"]["segments.date"] == "2026-08-25"
    ]

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas, coverage_receipt=_recibo_para(linhas))

    assert erro.value.codigo == "COBERTURA_DATAS_INEXATA"
    assert "2026-08-26" in erro.value.detalhe
    assert "2026-08-27" in erro.value.detalhe


@pytest.mark.parametrize(
    "query_window",
    [
        {"inicio": "2026-08-26", "fim": "2026-08-27"},
        {"inicio": "2026-08-24", "fim": "2026-08-26"},
    ],
)
def test_recusa_query_window_do_recibo_truncada_ou_divergente(
    query_window: dict[str, str],
):
    recibo = deepcopy(_dados()["coverage_receipt"])
    recibo["query_window"] = query_window

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(coverage_receipt=recibo)

    assert erro.value.codigo == "JANELA_COBERTURA_DIVERGENTE"


def test_recusa_janela_das_linhas_truncada_diante_da_query_window_do_recibo():
    linhas = [
        linha
        for linha in _linhas()
        if linha["raw_grain"] != "campaign_day"
        or linha["source_fields"]["segments.date"] != "2026-08-25"
    ]
    for linha in linhas:
        linha["janela"] = {"inicio": "2026-08-26", "fim": "2026-08-27"}
    recibo = _recibo_para(linhas)

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas, coverage_receipt=recibo)

    assert erro.value.codigo == "JANELA_COBERTURA_DIVERGENTE"


def test_recusa_dia_extra_fora_da_janela_mesmo_com_recibo_completo():
    linhas = _linhas()
    _por_grao(linhas, "campaign_day")["source_fields"]["segments.date"] = "2026-08-28"

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "JANELA_MISTURADA"


def test_recusa_selected_fields_ausente_em_qualquer_grao():
    recibo = deepcopy(_dados()["coverage_receipt"])
    del recibo["grains"]["campaign_day"]["selected_fields"]

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(coverage_receipt=recibo)

    assert erro.value.codigo == "RECIBO_COBERTURA_INVALIDO"


def test_recusa_customer_time_zone_ausente_no_recibo_global():
    recibo = deepcopy(_dados()["coverage_receipt"])
    del recibo["customer_time_zone"]

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(coverage_receipt=recibo)

    assert erro.value.codigo == "RECIBO_COBERTURA_INVALIDO"


@pytest.mark.parametrize("campo", ["query_window", "adapter_conversions"])
def test_recusa_evidencia_global_ausente_no_recibo(campo: str):
    recibo = deepcopy(_dados()["coverage_receipt"])
    del recibo[campo]

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(coverage_receipt=recibo)

    assert erro.value.codigo == "RECIBO_COBERTURA_INVALIDO"


@pytest.mark.parametrize(
    "grao,campo,zero",
    [
        ("campaign_day", "metrics.impressions", "0"),
        ("campaign_day", "metrics.conversions", 0),
        ("campaign_day", "metrics.conversions_value", 0),
        ("campaign_window", "metrics.search_impression_share", 0),
    ],
)
def test_metrica_zero_explicita_e_aceita_mas_omitida_e_recusada(
    grao: str,
    campo: str,
    zero,
):
    explicita = _linhas()
    _por_grao(explicita, grao)["source_fields"][campo] = zero
    resultado = _normalizado(explicita)
    assert resultado["decision_eligible"] is True

    omitida = _linhas()
    del _por_grao(omitida, grao)["source_fields"][campo]
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(omitida)
    assert erro.value.codigo == "CAMPO_AUSENTE"
    assert campo in erro.value.detalhe


def test_campo_obrigatorio_nao_selecionado_permanece_ausencia_e_recusa():
    linhas = _linhas()
    for linha in linhas:
        if linha["raw_grain"] == "campaign_day":
            del linha["source_fields"]["metrics.impressions"]
    recibo = deepcopy(_dados()["coverage_receipt"])
    recibo["grains"]["campaign_day"]["selected_fields"].remove(
        "metrics.impressions"
    )

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas, coverage_receipt=recibo)

    assert erro.value.codigo == "CAMPO_NAO_SELECIONADO"


def test_quality_nao_selecionada_ou_null_fica_ausente_e_bloqueia():
    campo = "ad_group_criterion.quality_info.quality_score"

    nao_selecionada = _linhas()
    del _por_grao(nao_selecionada, "keyword_criterion")["source_fields"][campo]
    recibo = deepcopy(_dados()["coverage_receipt"])
    recibo["grains"]["keyword_criterion"]["selected_fields"].remove(campo)
    resultado_ausente = _normalizado(
        nao_selecionada,
        coverage_receipt=recibo,
    )
    assert "quality_score" not in resultado_ausente["quality"][0]
    assert resultado_ausente["decision_eligible"] is False

    origens_destinos = {
        "ad_group_criterion.quality_info.quality_score": "quality_score",
        "ad_group_criterion.quality_info.creative_quality_score": "ad_relevance",
        "ad_group_criterion.quality_info.post_click_quality_score": (
            "landing_page_experience"
        ),
        "ad_group_criterion.quality_info.search_predicted_ctr": "expected_ctr",
    }
    nula = _linhas()
    campos_nulos = _por_grao(nula, "keyword_criterion")["source_fields"]
    for origem in origens_destinos:
        campos_nulos[origem] = None
    resultado_nulo = _normalizado(nula)
    assert all(
        destino not in resultado_nulo["quality"][0]
        for destino in origens_destinos.values()
    )
    assert resultado_nulo["decision_eligible"] is False
    assert len(resultado_nulo["decision_blockers"]) == 4
    assert "quality[0].quality_score ausente" in resultado_nulo["decision_blockers"]


@pytest.mark.parametrize(
    "grao,campo",
    [
        ("keyword_criterion", "ad_group_criterion.negative"),
        ("campaign_negative", "campaign_criterion.negative"),
        ("ad_group_negative", "ad_group_criterion.negative"),
    ],
)
def test_booleano_omitido_nunca_materializa_false(grao: str, campo: str):
    linhas = _linhas()
    del _por_grao(linhas, grao)["source_fields"][campo]

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "CAMPO_AUSENTE"
    assert campo in erro.value.detalhe


@pytest.mark.parametrize(
    "graos,campo,token",
    [
        (("campaign_day", "campaign_window"), "campaign.status", "UNKNOWN"),
        (("keyword_criterion",), "ad_group_criterion.status", "UNSPECIFIED"),
        (("search_term_view",), "search_term_view.status", "UNKNOWN"),
        (
            ("campaign_day", "campaign_window"),
            "campaign.serving_status",
            "UNSPECIFIED",
        ),
        (
            ("ad_group_negative",),
            "ad_group_criterion.system_serving_status",
            "UNKNOWN",
        ),
        (("search_term_view",), "segments.search_term_match_type", "UNKNOWN"),
    ],
)
def test_recusa_unknown_unspecified_em_status_serving_e_match_type(
    graos: tuple[str, ...],
    campo: str,
    token: str,
):
    linhas = _linhas()
    for linha in linhas:
        if linha["raw_grain"] in graos:
            linha["source_fields"][campo] = token

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "ENUM_NAO_OBSERVADO"


@pytest.mark.parametrize(
    "grao,campo",
    [
        ("campaign_day", "metrics.impressions"),
        ("campaign_day", "metrics.conversions"),
        ("campaign_day", "metrics.conversions_value"),
        ("campaign_window", "metrics.search_impression_share"),
        ("search_term_view", "metrics.conversions"),
    ],
)
def test_recusa_null_em_toda_metrica_obrigatoria(grao: str, campo: str):
    linhas = _linhas()
    _por_grao(linhas, grao)["source_fields"][campo] = None

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "NULABILIDADE_INVALIDA"


def test_recusa_timezone_divergente_da_evidencia_observada_da_conta():
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(calendar_timezone="UTC")

    assert erro.value.codigo == "TIMEZONE_DIVERGENTE"


@pytest.mark.parametrize(
    "grao,campo",
    [
        ("campaign_day", "metrics.impressions"),
        ("campaign_day", "metrics.cost_micros"),
        ("search_term_view", "metrics.clicks"),
    ],
)
def test_recusa_overflow_int64_acima_de_2_63_menos_1(grao: str, campo: str):
    linhas = _linhas()
    _por_grao(linhas, grao)["source_fields"][campo] = str(2**63)

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "RANGE_INT64_INVALIDO"


def test_aceita_limite_superior_int64_inclusivo():
    linhas = _linhas()
    _por_grao(linhas, "campaign_day")["source_fields"][
        "metrics.impressions"
    ] = str((2**63) - 1)

    resultado = _normalizado(linhas)

    assert resultado["daily_metrics"][0]["impressions"] == (2**63) - 1


def test_recusa_int64_nao_canonico_e_overflow_lexical_sem_valueerror_cru():
    leading_zero = _linhas()
    _por_grao(leading_zero, "campaign_day")["source_fields"][
        "metrics.impressions"
    ] = "0700"
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_leading_zero:
        _normalizado(leading_zero)
    assert erro_leading_zero.value.codigo == "CODIFICACAO_ESCALAR_INVALIDA"

    overflow_metrica = _linhas()
    _por_grao(overflow_metrica, "campaign_day")["source_fields"][
        "metrics.impressions"
    ] = "9" * 5_000
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_metrica:
        _normalizado(overflow_metrica)
    assert erro_metrica.value.codigo == "RANGE_INT64_INVALIDO"

    overflow_identidade = _linhas()
    _por_grao(overflow_identidade, "campaign_day")["source_fields"][
        "campaign.id"
    ] = "9" * 5_000
    with pytest.raises(ErroNormalizacaoGoogleAds) as erro_identidade:
        _normalizado(overflow_identidade)
    assert erro_identidade.value.codigo == "IDENTIDADE_INVALIDA"


@pytest.mark.parametrize("data_nao_estendida", ["20260825", "2026-W35-1"])
def test_recusa_data_iso_nao_estendida(data_nao_estendida: str):
    linhas = _linhas()
    _por_grao(linhas, "campaign_day")["source_fields"][
        "segments.date"
    ] = data_nao_estendida

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "DATA_INVALIDA"


def test_recusa_valor_de_conversao_cujo_micros_excede_int64():
    linhas = _linhas()
    _por_grao(linhas, "campaign_day")["source_fields"][
        "metrics.conversions_value"
    ] = 10_000_000_000_000

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "RANGE_INT64_INVALIDO"


@pytest.mark.parametrize(
    "campo",
    ["metrics.conversions", "metrics.conversions_value"],
)
def test_recusa_double_int_gigante_com_erro_tipado(campo: str):
    linhas = _linhas()
    _por_grao(linhas, "campaign_day")["source_fields"][campo] = 10**5_000

    with pytest.raises(ErroNormalizacaoGoogleAds) as erro:
        _normalizado(linhas)

    assert erro.value.codigo == "RANGE_INVALIDO"


def test_termo_utf8_que_exige_padding_usa_sufixo_urlsafe_sem_padding():
    linhas = _linhas()
    termo = "café"
    codificado = base64.urlsafe_b64encode(termo.encode("utf-8")).decode("ascii")
    assert codificado.endswith("=")
    campos = _por_grao(linhas, "search_term_view")["source_fields"]
    campos["search_term_view.search_term"] = termo
    campos["search_term_view.resource_name"] = (
        "customers/9990000001/searchTermViews/"
        f"88000000001~770001~{codificado.rstrip('=')}"
    )

    resultado = _normalizado(linhas)
    recurso = resultado["search_terms"][0]["resource_name"]

    assert recurso.endswith("Y2Fmw6k")
    assert not recurso.endswith("=")
    assert "premise remains unverified" in resultado["normalization_manifest"][
        "search_term_resource_suffix"
    ]


def test_manifesto_declara_projecao_pos_messagetodict_sem_zero_fill():
    manifesto = _normalizado()["normalization_manifest"]

    assert "post-MessageToDict" in manifesto["scalar_encoding"][
        "flattening_projection"
    ]
    assert "zero-fill is forbidden" in manifesto["scalar_encoding"][
        "omitted_defaults"
    ]
    assert "selected_fields proves GAQL selection" in manifesto["scalar_encoding"][
        "presence_evidence"
    ]
    assert "customer_time_zone" in manifesto["calendar_authority"]
    assert "explicit agora argument" in manifesto["kernel_temporal_gate"]
    assert "lido_em.date()" in manifesto["kernel_temporal_gate"]
    assert "naive datetimes fall back to UTC" in manifesto["kernel_temporal_gate"]
    assert "fail-closed" in manifesto["kernel_temporal_gate"]
    assert "double noise" in manifesto["conversion_value"]["double_noise"]
    assert "premise remains unverified" in manifesto[
        "search_term_resource_suffix"
    ]
