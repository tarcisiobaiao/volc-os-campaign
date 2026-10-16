"""Contrato da Observacao canônica: status × valor, relógios, unidade/moeda, chaves."""
from __future__ import annotations

from datetime import timedelta

import pytest

from volc_dil.contracts import ContratoViolado
from volc_dil.fundacao.observacao import (
    CAMPOS_JSON,
    Coletor,
    EntidadeRef,
    Observacao,
    ObservacaoInvalida,
    StatusObservacao,
)


def test_observacao_valida_e_imutavel(obs):
    o = obs()
    assert o.status is StatusObservacao.OBSERVED
    with pytest.raises(Exception):
        o.valor = 1  # type: ignore[misc]
    assert issubclass(ObservacaoInvalida, ContratoViolado)


# ---------------------------------------------------------------- status × valor (null != 0)
@pytest.mark.parametrize(
    "kw, trecho",
    [
        (dict(status="observed", valor=None), "observed exige valor"),
        (dict(status="observed", valor=0), "zero_confirmed"),
        (dict(status="zero_confirmed", valor=None), "zero_confirmed exige valor 0"),
        (dict(status="zero_confirmed", valor=10), "zero_confirmed exige valor 0"),
        (dict(status="missing", valor=0, motivo="sem linha"), "não carrega valor"),
        (dict(status="late", valor=0, motivo="D-1 não publicado"), "não carrega valor"),
        (dict(status="unavailable", valor=5, motivo="HTTP 503"), "não carrega valor"),
        (dict(status="unsupported", valor=0, motivo="fonte não mede"), "não carrega valor"),
        (dict(status="invalid", valor=7, motivo="drift"), "não carrega valor"),
        (dict(status="missing", valor=None), "exige motivo"),
        (dict(status="unavailable", valor=None, motivo="   "), "exige motivo"),
        (dict(status="partial", valor=10, motivo="janela_aberta"), "cobertura_ppm"),
        (dict(status="partial", valor=10, motivo="x", cobertura_ppm=0), "cobertura_ppm"),
        (dict(status="partial", valor=10, motivo="x", cobertura_ppm=1_000_000), "cobertura_ppm"),
        (dict(status="observed", cobertura_ppm=500_000), "cobertura_ppm só existe"),
        (dict(status="valido?"), "fora do vocabulário"),
        (dict(valor=1.5), "precisa ser int"),
        (dict(valor=True), "precisa ser int"),
        (dict(valor=2**63), "bigint"),
    ],
)
def test_status_valor_recusados(obs, kw, trecho):
    with pytest.raises(ObservacaoInvalida, match=trecho):
        obs(**kw)


@pytest.mark.parametrize(
    "kw",
    [
        dict(status="zero_confirmed", valor=0),
        dict(status="missing", valor=None, motivo="linha_ausente_na_resposta", moeda=None),
        dict(status="late", valor=None, motivo="D-1 ainda não publicado"),
        dict(status="unavailable", valor=None, motivo="HTTP 503"),
        dict(status="unsupported", valor=None, motivo="fonte não mede custo"),
        dict(status="invalid", valor=None, motivo="chave_substituida"),
        dict(status="partial", valor=10, motivo="janela_aberta", cobertura_ppm=500_000),
        dict(status="partial", valor=None, motivo="sem valor parcial", cobertura_ppm=1),
        dict(status="observed", valor=-3_000_000),  # estorno em dinheiro é permitido; contagem negativa não
    ],
)
def test_status_valor_aceitos(obs, kw):
    o = obs(**kw)
    assert o.status.value == kw["status"]


def test_janela_aberta_nao_pode_ser_observed(obs):
    d = obs().janela_inicio
    with pytest.raises(ObservacaoInvalida, match="use partial"):
        obs(observed_at=d + timedelta(hours=12), available_at=d + timedelta(hours=12), ingested_at=d + timedelta(hours=13))
    o = obs(status="partial", motivo="janela_aberta", cobertura_ppm=500_000,
            observed_at=d + timedelta(hours=12), available_at=d + timedelta(hours=12), ingested_at=d + timedelta(hours=13))
    assert o.cobertura_ppm == 500_000


# ---------------------------------------------------------------- relógios
@pytest.mark.parametrize(
    "deslocamentos, trecho",
    [
        (dict(janela_fim=0), "janela vazia"),
        (dict(observed_at=-1), "observed_at anterior"),
        (dict(available_at=24), "available_at anterior a observed_at"),  # available < observed (observed = +28h)
        (dict(ingested_at=27), "ingested_at anterior"),
        (dict(source_updated_at=40), "source_updated_at posterior"),
    ],
)
def test_relogios_incoerentes(obs, deslocamentos, trecho):
    d = obs().janela_inicio
    kw = {k: d + timedelta(hours=h) for k, h in deslocamentos.items()}
    if "available_at" in kw:
        kw["ingested_at"] = d + timedelta(hours=30)
    with pytest.raises(ObservacaoInvalida, match=trecho):
        obs(**kw)


def test_instantes_sem_timezone_e_timezone_invalido(obs):
    d = obs().janela_inicio
    with pytest.raises(ObservacaoInvalida, match="sem timezone"):
        obs(janela_inicio=d.replace(tzinfo=None))
    with pytest.raises(ObservacaoInvalida, match="timezone inválido"):
        obs(timezone="America/Sao_Paolo")


# ---------------------------------------------------------------- unidade, moeda, value_kind
@pytest.mark.parametrize(
    "kw, trecho",
    [
        (dict(moeda=None), "exige moeda"),
        (dict(moeda="brl"), "moeda inválida"),
        (dict(unidade="contagem"), "incompatível"),
        (dict(metrica="clicks", unidade="contagem", moeda="BRL", valor=3), "contagem não tem moeda"),
        (dict(metrica="clicks", unidade="contagem", moeda=None, valor=-1), "contagem negativa"),
        (dict(metrica="revenue"), "value_kind explícito"),
        (dict(metrica="revenue", value_kind="observed_auction_signal"), "X02"),
        (dict(value_kind="reported_revenue"), "não tem value_kind"),
        (dict(metrica="signal", value_kind="reported_revenue"), "observed_auction_signal"),
        (dict(fonte="Google Ads"), "slug"),
        (dict(conta=" 123"), "bordas"),
        (dict(entidade_id="1\x1f2"), "controle"),
        (dict(grao=("campaign", "semana")), "grão desconhecido"),
        (dict(dimensoes=(("b", "1"), ("a", "2"))), "ordenadas"),
        (dict(payload_ref="s3://bucket/ultimo.json"), "endereçamento por conteúdo"),
        (dict(payload_sha256="ABC"), "sha256"),
    ],
)
def test_unidade_moeda_identidade_recusadas(obs, kw, trecho):
    with pytest.raises(ObservacaoInvalida, match=trecho):
        obs(**kw)


# ---------------------------------------------------------------- chaves
def test_chave_natural_ignora_valor_status_relogios_e_offset(obs):
    a = obs()
    d = a.janela_inicio
    b = obs(status="missing", valor=None, moeda=None, motivo="sem linha", payload=b"[]",
            available_at=d + timedelta(days=3), ingested_at=d + timedelta(days=3), run_id="run-9", lote_id="lote-9")
    utc = obs(janela_inicio=a.janela_inicio.astimezone(__import__("datetime").timezone.utc),
              janela_fim=a.janela_fim.astimezone(__import__("datetime").timezone.utc))
    grao_invertido = obs(grao=("day", "campaign"))
    assert a.chave_natural == b.chave_natural == utc.chave_natural == grao_invertido.chave_natural
    assert a.chave_base != b.chave_base  # payload diferente → leitura diferente


@pytest.mark.parametrize(
    "kw",
    [
        dict(conta="999"), dict(entidade_id="222"), dict(fonte="joinads"), dict(metrica="clicks", unidade="contagem", moeda=None, valor=1),
        dict(timezone="UTC"), dict(dimensoes=(("joinads_domain", "x.com"),)), dict(entidade=EntidadeRef("ad_group", "111")),
    ],
)
def test_chave_natural_muda_com_identidade(obs, kw):
    assert obs(**kw).chave_natural != obs().chave_natural


def test_chave_base_inclui_coletor_e_esquema(obs):
    a = obs()
    assert obs(coletor=Coletor("coleta_canonica_google_ads", "1.0.1")).chave_base != a.chave_base
    assert obs(schema_version="google_ads.gaql.campaign_day.v2").chave_base != a.chave_base
    # o que não é identidade da leitura não muda a chave
    d = a.janela_inicio
    assert obs(run_id="outro", lote_id="outro", available_at=d + timedelta(days=2), ingested_at=d + timedelta(days=2)).chave_base == a.chave_base


def test_json_ida_e_volta(obs):
    o = obs(dimensoes=(("joinads_domain", "exemplo.com.br"),), request_id="req-1", status="partial", motivo="x",
            cobertura_ppm=10, observed_at=obs().janela_inicio + timedelta(hours=1))
    j = o.para_json()
    assert tuple(j) == CAMPOS_JSON
    assert Observacao.de_json(j) == o
    with pytest.raises(ObservacaoInvalida, match="desconhecidos"):
        Observacao.de_json({**j, "valor_bruto": "1,5"})
    sem = dict(j)
    del sem["lote_id"]
    with pytest.raises(ObservacaoInvalida, match="lote_id"):
        Observacao.de_json(sem)
