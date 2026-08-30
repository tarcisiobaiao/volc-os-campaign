"""Duas execuções no mesmo input são byte-idênticas."""

from __future__ import annotations

from services.orakul_predictive.hashes import hash_canonico
from services.orakul_predictive.constantes import MODELO_LAGGED_LINEAR
from services.orakul_predictive.fixtures_sinteticas import CAMPANHA_A, procedencia_sintetica, serie_sintetica_a
from services.orakul_predictive.motor import prever
from services.orakul_predictive.replay import walk_forward

from .helpers import agora, request_naive


def test_previsao_naive_byte_identica():
    serie = serie_sintetica_a()
    req = request_naive("2026-07-08")
    a = [p.serializar() for p in prever(req, serie)]
    b = [p.serializar() for p in prever(req, serie)]
    assert hash_canonico(a) == hash_canonico(b)


def test_walk_forward_byte_identico():
    kwargs = dict(
        serie=serie_sintetica_a(),
        campanha_id=CAMPANHA_A,
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
        versao_modelo=MODELO_LAGGED_LINEAR,
        n_minimo_treino=14,
    )
    r1 = walk_forward(**kwargs)
    r2 = walk_forward(**kwargs)
    assert hash_canonico(r1.serializar()) == hash_canonico(r2.serializar())
