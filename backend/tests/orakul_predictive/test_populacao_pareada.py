"""Champion/challenger só compara a mesma população D+1, sem inflar n_total."""

from __future__ import annotations

from dataclasses import replace

import pytest

from services.orakul_predictive.champion_challenger import decidir_champion_challenger
from services.orakul_predictive.constantes import CENARIO_OBSERVADO, DEFINICOES_ALVO
from services.orakul_predictive.excecoes import ContratoInvalido, PopulacaoIncompativel
from services.orakul_predictive.fixtures_sinteticas import CAMPANHA_A, CONTA, procedencia_sintetica, serie_sintetica_a
from services.orakul_predictive.hashes import pair_id_d1
from services.orakul_predictive.replay import origens_possiveis, walk_forward

from .helpers import agora, backtest_fake


@pytest.mark.parametrize(
    "challenger",
    [
        backtest_fake("lagged_linear_ridge/v1", conta_id="outra-conta"),
        backtest_fake("lagged_linear_ridge/v1", fim="2026-07-02"),
        backtest_fake("lagged_linear_ridge/v1", pair_origin_offset=1),
    ],
)
def test_cc_recusa_conta_janela_ou_pair_ids_diferentes(challenger):
    champion = backtest_fake("naive_persistence/v1")
    with pytest.raises(PopulacaoIncompativel):
        decidir_champion_challenger(
            champion=champion,
            challenger=challenger,
            procedencia=procedencia_sintetica(),
            observado_em=agora(),
        )


def test_n_total_e_unidades_pareadas_nao_soma_dois_alvos():
    resultado = walk_forward(
        serie_sintetica_a(),
        campanha_id=CAMPANHA_A,
        conta_id=CONTA,
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
    )
    tamanhos = [len(ids) for ids in resultado.pair_ids_por_alvo.values()]
    assert resultado.n_total == min(tamanhos)
    assert resultado.janela.n_pares == resultado.n_total
    assert resultado.n_total != sum(tamanhos)

    with pytest.raises(ContratoInvalido, match="janela.n_pares"):
        replace(resultado, n_total=sum(tamanhos))


def test_pair_id_e_origens_recusam_d2_disfarcado_de_d1():
    with pytest.raises(ContratoInvalido, match=r"target D\+1"):
        pair_id_d1(
            conta_id=CONTA,
            campanha_id=CAMPANHA_A,
            origin_date="2026-06-15",
            target_date="2026-06-17",
            alvo="spend",
            cenario=CENARIO_OBSERVADO,
            target_definition=DEFINICOES_ALVO["spend"],
        )

    # A fixture não tem 16/06: 15/06 não pode usar 17/06 como se fosse D+1.
    origens = origens_possiveis(serie_sintetica_a(), CAMPANHA_A, 1, conta_id=CONTA)
    assert "2026-06-15" not in origens
