"""Rollback para o champion anterior. Exige confirmação humana no registry in-memory."""

from __future__ import annotations

import pytest

from services.orakul_predictive.adapters_memoria import InMemoryModelRegistry
from services.orakul_predictive.champion_challenger import propor_rollback
from services.orakul_predictive.excecoes import IsolamentoViolado
from services.orakul_predictive.fixtures_sinteticas import CAMPANHA_A, CONTA, procedencia_sintetica

from .helpers import agora, versao_modelo


def test_rollback_proposto_restaura_champion_anterior():
    reg = InMemoryModelRegistry(permitir_sintetico=True)
    a = reg.registrar(versao_modelo("naive_persistence/v1", "champion"))
    b = reg.registrar(versao_modelo("lagged_linear_ridge/v1", "challenger"))
    from services.orakul_predictive.champion_challenger import decidir_champion_challenger
    from .helpers import backtest_fake

    d = decidir_champion_challenger(
        champion=backtest_fake(a.version_id, n=30, wape_rev=0.25, mae_spend=5.0),
        challenger=backtest_fake(b.version_id, n=30, wape_rev=0.18, mae_spend=4.5),
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
    )
    with pytest.raises(IsolamentoViolado):
        reg.aplicar_proposta(d, humano_confirmou=False)
    novo = reg.aplicar_proposta(d, humano_confirmou=True)
    assert novo.papel == "champion"
    assert novo.version_id == b.version_id
    assert reg.obter(a.version_id).papel == "retired"

    rb = propor_rollback(
        champion_atual=b.version_id,
        champion_anterior=a.version_id,
        motivo="erro residual subiu após promoção",
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
        campanha_id=CAMPANHA_A,
        conta_id=CONTA,
    )
    assert rb.veredito == "propor_rollback"
    assert rb.promocao == "rollback_proposto"
    restaurado = reg.aplicar_proposta(rb, humano_confirmou=True)
    assert restaurado.version_id == a.version_id
    assert restaurado.papel == "champion"
    assert a.version_id in reg.historico_champion()


def test_registry_padrao_recusa_champion_sintetico_como_se_fosse_real():
    reg = InMemoryModelRegistry()
    with pytest.raises(IsolamentoViolado, match="sintético"):
        reg.registrar(versao_modelo("naive_persistence/v1", "champion"))


def test_registry_de_laboratorio_isola_champion_sintetico_explicitamente():
    reg = InMemoryModelRegistry(permitir_sintetico=True)
    versao = reg.registrar(versao_modelo("naive_persistence/v1", "champion"))
    assert reg.champion(versao.alvo) == versao
