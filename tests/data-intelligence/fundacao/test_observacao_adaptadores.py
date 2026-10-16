"""Adaptadores puros v21 (Google Ads) e JoinAds v2 → Observacao, com linhas SINTÉTICAS no formato das tabelas.

Os formatos seguem o DDL de `043c77f5:supabase/migrations/v21_01_google_ads_coleta_canonica.sql` e de
`wip/historico-joinads-20261015:supabase/migrations/20261015163704_joinads_collection_canonical.sql`.
Nenhum valor aqui veio de produção.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from volc_dil.contracts import EstadoMedida
from volc_dil.fundacao.observacao import (
    AdaptacaoImpossivel,
    Registro,
    ResultadoRegistro,
    StatusObservacao,
    adaptar_google_ads_v21,
    adaptar_joinads_v2,
    agregar_observacoes,
    para_contrato_economico,
)

BRT = timezone(timedelta(hours=-3))


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def v21(**kw):
    linha = dict(
        observation_id="00000000-0000-0000-0000-000000000001", run_id="11111111-1111-1111-1111-111111111111",
        batch_id="22222222-2222-2222-2222-222222222222", observation_key="1234567890:23100000001:2026-10-14",
        customer_id="1234567890", campaign_id="23100000001", ad_group_id=None, criterion_id=None,
        resource_type="campaign", resource_id="23100000001", grain="campaign_day", metric_date=date(2026, 10, 14),
        metric_hour=None, currency_code="BRL", dimensions={"campaign_name": "sintética", "status": "ENABLED"},
        metrics={"cost_micros": 1_234_567, "impressions": 0, "clicks": 3, "conversions": Decimal("1")},
        collected_at=datetime(2026, 10, 15, 6, 0, tzinfo=BRT), created_at=datetime(2026, 10, 15, 6, 0, 2, tzinfo=BRT),
        batch_payload_sha256=_sha("lote-1"), batch_request_id="req-1",
        batch_payload={"campaign": {"campaign": {"id": "23100000001"}}, "metrics": {"metrics": {"costMicros": "1234567", "clicks": "3"}}},
        run_collector="n8n-google-ads-d1", run_collector_version=1, run_api_version="v25", run_timezone="America/Sao_Paulo",
    )
    linha.update(kw)
    return linha


def joinads(**kw):
    linha = dict(
        observation_key="ja-1", run_key="run-ja-1", batch_key="lote-ja-1", endpoint="key_value_campaign_adunit",
        grain="campaign_day", metric_date="2026-10-14", metric_hour=None, domain="exemplo.com.br",
        campaign_id="23100000001", custom_key="utm_campaign", custom_value="23100000001", post_id=None, land_uri=None,
        ad_unit_name=None, country_iso=None, currency_code="USD", revenue_client=Decimal("0.123456"),
        revenue_gross=Decimal("0.200000"), impressions=8, clicks=0, data_status="observed",
        collected_at="2026-10-15T06:00:00-03:00", created_at="2026-10-15T06:00:01-03:00",
        batch_payload_sha256=_sha("ja-lote-1"), batch_request_meta={"custom_key": "utm_campaign"},
        run_collector="n8n_joinads_v2", run_collector_version=4, run_timezone="America/Sao_Paulo",
    )
    linha.update(kw)
    return linha


def _m(obs):
    return {o.metrica.value: o for o in obs}


# ============================================================== Google Ads v21
def test_v21_campanha_dia_com_prova_de_linha():
    m = _m(adaptar_google_ads_v21(v21()))
    assert (m["cost"].status, m["cost"].valor, m["cost"].moeda) == (StatusObservacao.OBSERVED, 1_234_567, "BRL")
    assert m["impressions"].status is StatusObservacao.ZERO_CONFIRMED  # linha de métrica existe: campo omitido = 0 da API
    assert m["clicks"].valor == 3 and m["conversions"].valor == 1
    c = m["cost"]
    assert (c.fonte, c.conta, c.entidade.tipo, c.entidade.id, c.grao) == ("google_ads", "1234567890", "campaign", "23100000001", ("campaign", "day"))
    assert c.janela_inicio == datetime(2026, 10, 14, tzinfo=BRT) and c.janela_fim == datetime(2026, 10, 15, tzinfo=BRT)
    assert c.observed_at == datetime(2026, 10, 15, 6, 0, tzinfo=BRT)
    assert c.available_at == c.ingested_at == datetime(2026, 10, 15, 6, 0, 2, tzinfo=BRT)  # max(collected, created)
    assert c.payload_ref.endswith(c.payload_sha256) and c.lote_id == "22222222-2222-2222-2222-222222222222"
    assert (c.coletor.nome, c.coletor.versao, c.schema_version) == ("n8n-google-ads-d1", "1", "google_ads.v21.campaign.campaign_day.api_v25")


def test_v21_zero_sintetizado_sem_linha_de_metrica_vira_missing():
    """R3/L11: 88 de 110 campanha-dia têm cost=0 e impressions=0 porque o Code node sintetiza 0 sem linha."""
    linha = v21(metrics={"cost_micros": 0, "impressions": 0, "clicks": 0, "conversions": 0},
                batch_payload={"campaign": {"campaign": {"id": "23100000001"}}, "metrics": {}, "budget": {}, "goal": {}})
    obs = adaptar_google_ads_v21(linha)
    assert {o.status for o in obs} == {StatusObservacao.MISSING}
    assert {o.motivo for o in obs} == {"zero_sem_linha_de_metrica"}
    assert all(o.valor is None for o in obs)
    ag = agregar_observacoes([o for o in obs if o.metrica.value == "cost"])
    assert ag.valor is None and ag.agregado.estado is EstadoMedida.AUSENTE  # nunca soma como 0


def test_v21_sem_payload_na_juncao_zero_nao_tem_prova_mas_valor_nao_zero_vale():
    linha = v21(metrics={"cost_micros": 0, "impressions": 15, "clicks": 0, "conversions": 0}, batch_payload=None)
    m = _m(adaptar_google_ads_v21(linha))
    assert (m["cost"].status, m["cost"].motivo) == (StatusObservacao.MISSING, "zero_sem_prova_de_linha")
    assert (m["impressions"].status, m["impressions"].valor) == (StatusObservacao.OBSERVED, 15)


def test_v21_intradiario_vira_partial_com_cobertura():
    linha = v21(collected_at=datetime(2026, 10, 14, 12, 0, tzinfo=BRT), created_at=datetime(2026, 10, 14, 12, 0, tzinfo=BRT))
    c = _m(adaptar_google_ads_v21(linha))["cost"]
    assert (c.status, c.valor, c.cobertura_ppm, c.motivo) == (StatusObservacao.PARTIAL, 1_234_567, 500_000, "janela_aberta")


def test_v21_relogio_do_n8n_adiantado_nao_antecipa_conhecimento():
    linha = v21(collected_at=datetime(2026, 10, 15, 6, 5, tzinfo=BRT), created_at=datetime(2026, 10, 15, 6, 0, tzinfo=BRT))
    c = _m(adaptar_google_ads_v21(linha))["cost"]
    assert c.available_at == datetime(2026, 10, 15, 6, 5, tzinfo=BRT)


@pytest.mark.parametrize(
    "kw, metrica, status, motivo",
    [
        (dict(metrics={"cost_micros": 1.5e6, "impressions": 1, "clicks": 1, "conversions": 1}), "cost", "invalid", "float_recusado:cost_micros"),
        (dict(metrics={"cost_micros": 10, "impressions": 1, "clicks": 1, "conversions": Decimal("1.5")}), "conversions", "invalid", "valor_fracionario:conversions"),
        (dict(currency_code=None), "cost", "invalid", "moeda_nao_declarada"),
        (dict(metrics={"impressions": 1, "clicks": 1, "conversions": 1}), "cost", "missing", "metrica_ausente_no_registro:cost_micros"),
        (dict(metrics={"cost_micros": None, "impressions": 1, "clicks": 1, "conversions": 1}), "cost", "missing", "valor_nulo_na_fonte:cost_micros"),
        (dict(metrics={"cost_micros": 5, "impressions": -1, "clicks": 1, "conversions": 1}), "impressions", "invalid", "contagem_negativa:impressions"),
    ],
)
def test_v21_valores_problematicos(kw, metrica, status, motivo):
    o = _m(adaptar_google_ads_v21(v21(**kw)))[metrica]
    assert (o.status.value, o.valor, o.motivo) == (status, None, motivo)


def test_v21_keyword_dia_identidade_inclui_grupo_e_campanha():
    a = adaptar_google_ads_v21(v21(resource_type="keyword", grain="keyword_day", ad_group_id="555", criterion_id="777"))
    b = adaptar_google_ads_v21(v21(resource_type="keyword", grain="keyword_day", ad_group_id="556", criterion_id="777"))
    assert a[0].entidade.tipo == "keyword" and a[0].grao == ("day", "keyword")
    assert dict(a[0].dimensoes) == {"ad_group_id": "555", "campaign_id": "23100000001"}
    assert a[0].chave_natural != b[0].chave_natural  # criterion_id só é único dentro do grupo


@pytest.mark.parametrize(
    "kw, trecho",
    [(dict(grain="asset_day"), "sem mapeamento"), (dict(customer_id=None), "customer_id"),
     (dict(metric_date=None), "metric_date"), (dict(campaign_id=None), "id da entidade"),
     (dict(batch_payload_sha256=None), "batch_payload_sha256"), (dict(collected_at=datetime(2026, 10, 15)), "timezone")],
)
def test_v21_sem_identidade_e_adaptacao_impossivel(kw, trecho):
    with pytest.raises(AdaptacaoImpossivel, match=trecho):
        adaptar_google_ads_v21(v21(**kw))


def test_v21_maturacao_intradiaria_vira_versoes_e_releitura_e_noop():
    """L10: o mesmo campanha-dia relido por vários runs com custo diferente = versões; mesmo lote = no-op."""
    r = Registro()
    leituras = []
    for i, (custo, hora) in enumerate([(900_000, 7), (1_100_000, 13), (1_234_567, 23)]):
        t = datetime(2026, 10, 15, hora, tzinfo=BRT)
        leituras.append(v21(run_id=f"run-{i}", batch_id=f"lote-{i}", batch_payload_sha256=_sha(f"lote-{i}"),
                            metrics={"cost_micros": custo, "impressions": 10, "clicks": 1, "conversions": 0},
                            collected_at=t, created_at=t))
    resultados = [r.registrar(_m(adaptar_google_ads_v21(x))["cost"]) for x in leituras + [leituras[1]]]
    assert resultados == [ResultadoRegistro.INSERIDO] * 3 + [ResultadoRegistro.NOOP]
    nat = _m(adaptar_google_ads_v21(leituras[0]))["cost"].chave_natural
    assert r.as_of(datetime(2026, 10, 15, 14, tzinfo=BRT))[nat].valor == 1_100_000
    assert [v.observacao.valor for v in r.historico(nat)] == [900_000, 1_100_000, 1_234_567]


def test_v21_ponte_para_contrato_herdado():
    for o in adaptar_google_ads_v21(v21()):
        e = para_contrato_economico(o)
        assert e.disponivel_em == o.available_at and e.fonte == "google_ads"


# ============================================================== JoinAds v2
def test_joinads_campanha_dia_receitas_client_e_gross_sao_fatos_distintos():
    obs = adaptar_joinads_v2(joinads())
    rec = [o for o in obs if o.metrica.value == "revenue"]
    por_base = {dict(o.dimensoes)["revenue_basis"]: o for o in rec}
    assert por_base["client"].valor == 123_456 and por_base["client"].moeda == "USD"
    assert por_base["gross"].valor == 200_000
    assert por_base["client"].chave_natural != por_base["gross"].chave_natural
    assert all(o.value_kind.value == "reported_revenue" for o in rec)
    m = {o.metrica.value: o for o in obs if o.metrica.value != "revenue"}
    assert (m["impressions"].valor, m["clicks"].status) == (8, StatusObservacao.ZERO_CONFIRMED)  # linha explícita da fonte
    c = rec[0]
    assert (c.fonte, c.conta, c.entidade.tipo, c.entidade.id, c.grao) == ("joinads", "exemplo.com.br", "campaign", "23100000001", ("campaign", "day"))
    assert dict(c.dimensoes)["joinads_endpoint"] == "key_value_campaign_adunit"


def test_joinads_chave_substituida_vira_invalid():
    obs = adaptar_joinads_v2(joinads(custom_key="land_uri", custom_value="/", campaign_id=None))
    assert {o.status for o in obs} == {StatusObservacao.INVALID}
    assert {o.motivo for o in obs} == {"chave_substituida:utm_campaign->land_uri"}
    assert {o.valor for o in obs} == {None}


@pytest.mark.parametrize(
    "kw, status, motivo",
    [
        (dict(data_status="unavailable", revenue_client=None, revenue_gross=None, impressions=None, clicks=None), "unavailable", "joinads_data_status:unavailable"),
        (dict(data_status="unsupported"), "unsupported", "joinads_data_status:unsupported"),
        (dict(batch_payload_sha256="0" * 64), "invalid", "payload_sem_hash"),
    ],
)
def test_joinads_status_de_linha(kw, status, motivo):
    obs = adaptar_joinads_v2(joinads(**kw))
    assert {(o.status.value, o.motivo) for o in obs} == {(status, motivo)}


def test_joinads_valores_problematicos():
    m = {(o.metrica.value, dict(o.dimensoes).get("revenue_basis")): o for o in adaptar_joinads_v2(
        joinads(revenue_client=Decimal("0.1234567"), clicks=None, data_status="observed"))}
    assert (m[("revenue", "client")].status, m[("revenue", "client")].motivo) == (StatusObservacao.INVALID, "precisao_acima_de_micros:revenue_client")
    assert (m[("clicks", None)].status, m[("clicks", None)].motivo) == (StatusObservacao.MISSING, "valor_nulo_na_fonte:clicks")
    z = {o.metrica.value: o for o in adaptar_joinads_v2(joinads(data_status="zero_confirmed", revenue_client=0, revenue_gross=0, impressions=3, clicks=0))}
    assert z["impressions"].motivo == "zero_confirmed_com_valor:impressions"


def test_joinads_entidades_por_grao():
    post = adaptar_joinads_v2(joinads(campaign_id=None, custom_key="id_post_wp", custom_value="991", post_id="991",
                                       batch_request_meta={"custom_key": "id_post_wp"}, grain="post_day"))[0]
    assert (post.entidade.tipo, post.entidade.id, post.grao) == ("post", "991", ("day", "url"))
    dom = adaptar_joinads_v2(joinads(campaign_id=None, custom_key=None, custom_value=None, batch_request_meta={},
                                      endpoint="earnings", grain="domain_day", ad_unit_name="topo", country_iso="BR"))[0]
    assert (dom.entidade.tipo, dom.grao) == ("domain", ("account", "ad_unit", "country", "day"))
    hora = adaptar_joinads_v2(joinads(metric_hour=13, collected_at="2026-10-14T13:30:00-03:00", created_at="2026-10-14T13:30:00-03:00"))[0]
    assert hora.grao == ("campaign", "hour") and hora.status is StatusObservacao.PARTIAL and hora.cobertura_ppm == 500_000


def test_joinads_sem_dominio_e_adaptacao_impossivel():
    with pytest.raises(AdaptacaoImpossivel, match="domain"):
        adaptar_joinads_v2(joinads(domain=None))
