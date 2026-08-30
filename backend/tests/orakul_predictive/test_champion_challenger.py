"""Champion/challenger: nunca promove por uma métrica; amostra pequena preserva."""

from __future__ import annotations

from services.orakul_predictive.champion_challenger import decidir_champion_challenger
from services.orakul_predictive.fixtures_sinteticas import procedencia_sintetica

from .helpers import agora, backtest_fake


def test_amostra_pequena_preserva_champion():
    champ = backtest_fake("naive_persistence/v1", n=5, wape_rev=0.25, mae_spend=6.0)
    chal = backtest_fake("lagged_linear_ridge/v1", n=5, wape_rev=0.01, mae_spend=0.1)
    d = decidir_champion_challenger(
        champion=champ,
        challenger=chal,
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
    )
    assert d.veredito == "evidencia_insuficiente"
    assert d.promocao == "preservar"
    assert d.mutacao_campanha is False


def test_uma_metrica_boa_com_regressao_critica_nao_promove():
    champ = backtest_fake("naive_persistence/v1", n=30, wape_rev=0.20, mae_spend=5.0)
    chal = backtest_fake("lagged_linear_ridge/v1", n=30, wape_rev=0.05, mae_spend=9.0)
    d = decidir_champion_challenger(
        champion=champ,
        challenger=chal,
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
    )
    assert d.veredito == "regressao_critica"
    assert d.promocao == "preservar"
    assert len(d.metricas_consideradas) >= 2


def test_melhoria_no_pacote_vira_proposta_nunca_acao():
    champ = backtest_fake("naive_persistence/v1", n=30, wape_rev=0.25, mae_spend=5.0)
    chal = backtest_fake("lagged_linear_ridge/v1", n=30, wape_rev=0.18, mae_spend=4.8)
    d = decidir_champion_challenger(
        champion=champ,
        challenger=chal,
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
    )
    assert d.veredito == "propor_promocao"
    assert d.promocao == "proposta"
    assert d.explicacao


def test_empate_preserva_champion():
    champ = backtest_fake("naive_persistence/v1", n=30, wape_rev=0.20, mae_spend=5.0)
    chal = backtest_fake("lagged_linear_ridge/v1", n=30, wape_rev=0.20, mae_spend=5.0)
    d = decidir_champion_challenger(
        champion=champ,
        challenger=chal,
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
    )
    assert d.veredito in ("empate", "preservar_champion")
    assert d.promocao == "preservar"


def test_champion_wape_zero_e_challenger_positivo_nao_sao_empate():
    champ = backtest_fake("naive_persistence/v1", n=30, wape_rev=0.0, mae_spend=5.0)
    chal = backtest_fake("lagged_linear_ridge/v1", n=30, wape_rev=0.01, mae_spend=5.0)
    d = decidir_champion_challenger(
        champion=champ,
        challenger=chal,
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
    )
    assert d.veredito == "preservar_champion"
    assert d.promocao == "preservar"
    assert "WAPE zero" in " ".join(d.explicacao)


def test_sem_champion_ainda_e_proposta():
    chal = backtest_fake("naive_persistence/v1", n=30, wape_rev=0.20, mae_spend=5.0)
    d = decidir_champion_challenger(
        champion=None,
        challenger=chal,
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
    )
    assert d.veredito == "champion_inicial_proposto"
    assert d.promocao == "proposta"
