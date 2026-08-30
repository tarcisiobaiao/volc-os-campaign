"""Provas numéricas exatas: Ridge, artefato, quantil, intervalo e métricas."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from math import sqrt

import pytest

from services.orakul_predictive.algebra import ridge
from services.orakul_predictive.avaliacao import avaliar_pares, outcome_de_observacao
from services.orakul_predictive.constantes import (
    ALVO_REVENUE,
    ALVO_SPEND,
    DEFINICOES_ALVO,
    MODELO_LAGGED_LINEAR,
)
from services.orakul_predictive.excecoes import DefinicaoDeAlvoIncompativel, PopulacaoIncompativel
from services.orakul_predictive.features import montar_snapshot
from services.orakul_predictive.fixtures_sinteticas import (
    CAMPANHA_A,
    CONTA,
    procedencia_sintetica,
    serie_sintetica_a,
)
from services.orakul_predictive.hashes import chave_idempotencia, hash_canonico, id_canonico
from services.orakul_predictive.incerteza import intervalo_de_ponto, margem_quantil
from services.orakul_predictive.modelos import treinar_linear
from services.orakul_predictive.motor import codigo_hash_motor, prever
from services.orakul_predictive.relogio import iso_civil, parse_civil
from services.orakul_predictive.semantica import EstadoSemantico, valor_numerico_ou_nulo

from .helpers import agora, request_naive


def _artefato(alvo: str):
    serie = serie_sintetica_a()
    proc = procedencia_sintetica()
    por_data = {o.civil_date: o for o in serie}
    pares = []
    for obs in serie:
        target = iso_civil(parse_civil(obs.civil_date) + timedelta(days=1))
        futuro = por_data.get(target)
        if futuro is None:
            continue
        micros = (
            valor_numerico_ou_nulo(futuro.spend_estado, futuro.spend_micros)
            if alvo == ALVO_SPEND
            else valor_numerico_ou_nulo(futuro.revenue_estado, futuro.revenue_micros)
        )
        if micros is None:
            continue
        snap = montar_snapshot(
            serie,
            campanha_id=CAMPANHA_A,
            conta_id=CONTA,
            origin=obs.civil_date,
            horizonte_dias=1,
            versao_modelo=MODELO_LAGGED_LINEAR,
            procedencia=proc,
            codigo_hash=codigo_hash_motor(),
            alvo=alvo,
            observado_em=agora(),
        )
        pares.append((snap, micros))
    return treinar_linear(pares, alvo, n_minimo=3)


def test_ridge_nao_penaliza_intercepto_exemplo_exato():
    # Com apenas o intercepto, alpha enorme não pode puxar a média 4 para zero.
    coef = ridge([[1.0], [1.0], [1.0]], [2.0, 4.0, 6.0], alpha=1_000_000_000.0)
    assert coef == pytest.approx([4.0], abs=1e-12)


def test_hash_do_artefato_cobre_scaler_residuos_treino_e_definicao_do_alvo():
    artefato = _artefato(ALVO_REVENUE)
    medias = list(artefato.medias)
    medias[1] += 0.125
    residuos = list(artefato.residuos_abs)
    residuos[0] += 0.125

    assert replace(artefato, medias=tuple(medias)).artifact_hash != artefato.artifact_hash
    assert replace(artefato, residuos_abs=tuple(residuos)).artifact_hash != artefato.artifact_hash
    assert replace(artefato, training_hash="f" * 64).artifact_hash != artefato.artifact_hash
    assert artefato.artifact_id == f"artifact:{artefato.artifact_hash}"

    with pytest.raises(DefinicaoDeAlvoIncompativel):
        replace(artefato, target_definition=DEFINICOES_ALVO[ALVO_SPEND])


def test_motor_recusa_artefato_de_revenue_na_chave_spend():
    base = request_naive("2026-07-08", alvos=(ALVO_SPEND,))
    payload = {"base": base.hash_inputs, "modelo": MODELO_LAGGED_LINEAR}
    req = replace(
        base,
        request_id=id_canonico("request", **payload),
        versao_modelo=MODELO_LAGGED_LINEAR,
        hash_inputs=hash_canonico(payload),
        chave_idempotencia=chave_idempotencia(
            kind="request",
            conta_id=base.conta_id,
            campanha_id=base.campanha_id,
            janela_fim=base.janela_fim,
            versao_modelo=MODELO_LAGGED_LINEAR,
            cenario=base.cenario,
        ),
    )
    with pytest.raises(DefinicaoDeAlvoIncompativel, match="artefato"):
        prever(req, serie_sintetica_a(), artefatos={ALVO_SPEND: _artefato(ALVO_REVENUE)})


def test_quantil_split_conformal_usa_rank_finito_exato():
    assert margem_quantil([1, 2, 3, 4, 5, 6], nominal=0.90, minimo=7) is None
    assert margem_quantil(list(range(1, 11)), nominal=0.90) == 10.0
    assert margem_quantil(list(range(1, 21)), nominal=0.90) == 19.0


def test_metricas_intervalo_e_winkler_com_exemplo_exato():
    proc = procedencia_sintetica()
    origins = ("2026-07-05", "2026-07-06", "2026-07-07")
    yhats = (12_000_000, 18_000_000, 33_000_000)
    ys = (10_000_000, 20_000_000, 30_000_000)
    margens = (1.0, 1.0, 3.0)
    pares = []
    for origin, yhat, y, margem in zip(origins, yhats, ys, margens):
        pred_base = prever(request_naive(origin, alvos=(ALVO_SPEND,)), serie_sintetica_a())[0]
        intervalo = intervalo_de_ponto(
            previsao_id=pred_base.previsao_id,
            campanha_id=pred_base.campanha_id,
            alvo=pred_base.alvo,
            ponto_micros=yhat,
            margem_brl=margem,
            observado_em=pred_base.observado_em,
            janela_inicio=pred_base.janela_inicio,
            janela_fim=pred_base.janela_fim,
            horizonte_dias=1,
            versao_modelo=pred_base.versao_modelo,
            hash_inputs=pred_base.hash_inputs,
            procedencia=proc,
            n_calibracao=10,
            fora_da_amostra=True,
            conta_id=CONTA,
            pair_id=pred_base.pair_id,
            cenario=pred_base.cenario,
            artifact_hash=pred_base.artifact_hash,
        )
        pred = replace(
            pred_base,
            ponto_micros=yhat,
            ponto_bruto_micros=yhat,
            intervalo=intervalo,
        )
        out = outcome_de_observacao(
            campanha_id=CAMPANHA_A,
            conta_id=CONTA,
            origin_date=origin,
            target_date=pred.target_date,
            alvo=ALVO_SPEND,
            micros=y,
            estado=EstadoSemantico.MEDIDO,
            procedencia=proc,
            observado_em=agora(),
        )
        pares.append((pred, out))

    m = avaliar_pares(pares, dataset_kind="sintetico", n_minimo=3)
    assert m.n == 3
    assert m.n_intervalos == 3
    assert m.mae == pytest.approx(7 / 3)
    assert m.rmse == pytest.approx(sqrt(17 / 3))
    assert m.bias == pytest.approx(1.0)
    assert m.wape == pytest.approx(7 / 60)
    assert m.cobertura == pytest.approx(1 / 3)
    assert m.largura_media == pytest.approx(10 / 3)
    assert m.winkler == pytest.approx(50 / 3)

    with pytest.raises(PopulacaoIncompativel, match="duplicado"):
        avaliar_pares([pares[0], pares[0]], dataset_kind="sintetico", n_minimo=1)


def test_residuo_in_sample_nao_emite_intervalo_nominal():
    pred = prever(
        request_naive("2026-07-08", alvos=(ALVO_SPEND,)),
        serie_sintetica_a(),
    )[0]
    assert intervalo_de_ponto(
        previsao_id=pred.previsao_id,
        campanha_id=pred.campanha_id,
        alvo=pred.alvo,
        ponto_micros=pred.ponto_micros,
        margem_brl=10.0,
        observado_em=pred.observado_em,
        janela_inicio=pred.janela_inicio,
        janela_fim=pred.janela_fim,
        horizonte_dias=1,
        versao_modelo=pred.versao_modelo,
        hash_inputs=pred.hash_inputs,
        procedencia=pred.procedencia,
        n_calibracao=100,
        fora_da_amostra=False,
        conta_id=CONTA,
        pair_id=pred.pair_id,
        cenario=pred.cenario,
        artifact_hash=pred.artifact_hash,
    ) is None
