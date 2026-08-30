"""Leakage deliberado precisa falhar. Split aleatório também."""

from __future__ import annotations

import pytest

from services.orakul_predictive.contratos import recibo_sintetico
from services.orakul_predictive.excecoes import VazamentoDeFuturo
from services.orakul_predictive.features import FEATURES_PROIBIDAS_MESMO_DIA, detectar_leakage_de_alvo, montar_snapshot
from services.orakul_predictive.fixtures_sinteticas import CAMPANHA_A, procedencia_sintetica, serie_sintetica_a
from services.orakul_predictive.motor import codigo_hash_motor
from services.orakul_predictive.replay import origens_possiveis, walk_forward
from services.orakul_predictive.relogio import parse_civil, parse_instante

from .helpers import agora


def test_feature_historica_contemporanea_e_recusada():
    with pytest.raises(VazamentoDeFuturo):
        detectar_leakage_de_alvo({"budget_utilization": 0.8, "spend_lag0": 40.0}, None)


def test_injetar_feature_do_dia_alvo_falha():
    with pytest.raises(VazamentoDeFuturo):
        montar_snapshot(
            serie_sintetica_a(),
            campanha_id=CAMPANHA_A,
            origin="2026-06-20",
            horizonte_dias=1,
            versao_modelo="naive_persistence/v1",
            procedencia=recibo_sintetico("leak", agora()),
            codigo_hash=codigo_hash_motor(),
            alvo="spend",
            observado_em=agora(),
            injetar_feature_futura={"future_spend": 99.0},
        )


def test_walk_forward_recusa_split_aleatorio():
    with pytest.raises(VazamentoDeFuturo):
        walk_forward(
            serie_sintetica_a(),
            campanha_id=CAMPANHA_A,
            procedencia=procedencia_sintetica(),
            observado_em=agora(),
            split_aleatorio=True,
        )


def test_feature_as_of_nunca_posterior_ao_origin():
    snap = montar_snapshot(
        serie_sintetica_a(),
        campanha_id=CAMPANHA_A,
        origin="2026-07-01",
        horizonte_dias=1,
        versao_modelo="naive_persistence/v1",
        procedencia=recibo_sintetico("asof", agora()),
        codigo_hash=codigo_hash_motor(),
        alvo="spend",
        observado_em=agora(),
    )
    for nome, quando in snap.feature_as_of.items():
        if quando:
            assert parse_instante(quando) <= parse_instante(snap.cutoff_em), nome
    for nome, quando in snap.feature_civil_dates.items():
        if quando:
            assert parse_civil(quando) <= parse_civil(snap.origin_date), nome
    assert parse_civil(snap.max_data_usada) <= parse_civil(snap.origin_date)
    assert parse_instante(snap.max_instante_usado) <= parse_instante(snap.cutoff_em)


def test_snapshot_de_producao_nao_emite_feature_proibida():
    snap = montar_snapshot(
        serie_sintetica_a(),
        campanha_id=CAMPANHA_A,
        origin="2026-07-01",
        horizonte_dias=1,
        versao_modelo="naive_persistence/v1",
        procedencia=recibo_sintetico("prod", agora()),
        codigo_hash=codigo_hash_motor(),
        alvo="spend",
        observado_em=agora(),
    )
    assert FEATURES_PROIBIDAS_MESMO_DIA.isdisjoint(snap.features)


def test_origens_walk_forward_sao_estritamente_cronologicas():
    origens = origens_possiveis(serie_sintetica_a(), CAMPANHA_A, 1)
    assert origens
    assert tuple(origens) == tuple(sorted(origens))
    for a, b in zip(origens, origens[1:]):
        assert a < b
