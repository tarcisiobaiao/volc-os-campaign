"""Dataset pequeno é insuficiente, não vitória."""

from __future__ import annotations

import pytest

from services.orakul_predictive.excecoes import DatasetInsuficiente
from services.orakul_predictive.fixtures_sinteticas import CAMPANHA_B, procedencia_sintetica, serie_sintetica_curta
from services.orakul_predictive.replay import walk_forward

from .helpers import agora


def test_serie_curta_nao_vira_backtest_vencedor():
    with pytest.raises(DatasetInsuficiente):
        walk_forward(
            serie_sintetica_curta(),
            campanha_id=CAMPANHA_B,
            procedencia=procedencia_sintetica(),
            observado_em=agora(),
            n_minimo_treino=14,
        )
