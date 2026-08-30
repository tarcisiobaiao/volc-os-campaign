"""Walk-forward temporal, baseline vs candidato, falha parcial."""

from __future__ import annotations

from dataclasses import replace

from services.orakul_predictive.constantes import ALVO_REVENUE, ALVO_SPEND, MODELO_LAGGED_LINEAR
from services.orakul_predictive.fixtures_sinteticas import CAMPANHA_A, procedencia_sintetica, serie_sintetica_a
from services.orakul_predictive.replay import walk_forward

from .helpers import agora


def test_walk_forward_produz_metricas_e_naive_lado_a_lado():
    resultado = walk_forward(
        serie_sintetica_a(),
        campanha_id=CAMPANHA_A,
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
        versao_modelo=MODELO_LAGGED_LINEAR,
        n_minimo_treino=14,
    )
    assert resultado.dataset_kind == "sintetico"
    assert resultado.entra_em_contagens_reais is False
    assert resultado.leakage_detectado is False
    assert resultado.janela.split == "walk_forward_temporal"
    for alvo in (ALVO_SPEND, ALVO_REVENUE):
        m = resultado.metricas_por_alvo[alvo]
        n = resultado.naive_por_alvo[alvo]
        assert m.n > 0 and n.n > 0
        assert n.n == m.n  # comparação só na interseção pareada
        assert n.pair_ids == m.pair_ids
        assert m.mae is not None
        assert m.wape is not None
        assert m.rmse is not None
        assert n.mae is not None
    assert resultado.n_total == min(m.n for m in resultado.metricas_por_alvo.values())
    assert resultado.n_total < sum(m.n for m in resultado.metricas_por_alvo.values())


def test_replay_exclui_revisao_posterior_as_origens_em_vez_de_reescrever_o_passado():
    base = serie_sintetica_a()
    observacao = next(o for o in base if o.civil_date == "2026-07-08")
    revisao_retrospectiva = replace(
        observacao,
        spend_micros=observacao.spend_micros + 999_000_000,
        revenue_micros=observacao.revenue_micros + 999_000_000,
        # Conhecida antes da execução final, mas depois de todas as origens da fixture.
        lido_em="2026-07-31T12:00:00Z",
    )
    kwargs = dict(
        campanha_id=CAMPANHA_A,
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
        versao_modelo=MODELO_LAGGED_LINEAR,
        n_minimo_treino=14,
    )
    limpo = walk_forward(base, **kwargs)
    contaminado = walk_forward(base + (revisao_retrospectiva,), **kwargs)
    assert contaminado.hash_inputs == limpo.hash_inputs
    assert contaminado.population_hash == limpo.population_hash
