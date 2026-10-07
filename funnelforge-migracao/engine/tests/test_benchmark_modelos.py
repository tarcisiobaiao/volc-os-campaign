"""Benchmark de modelos: pontua recibos salvos e prepara a rodada real SEM gastar."""
from __future__ import annotations

from pathlib import Path

import yaml

from funnelforge import benchmark as bm
from funnelforge.domain.models import RunState

ESTADO = Path(__file__).parent / "fixtures" / "state_run_220001.json"


def _estado() -> RunState:
    return RunState.from_json(ESTADO.read_text(encoding="utf-8"))


def test_tabela_oficial_e_datada_e_tem_fonte():
    precos = bm.carregar_precos()
    assert precos["consultado_em"] == "2026-10-07"
    assert set(precos["fontes"]) == {"google", "openai"}
    assert all(m["fonte"] in precos["fontes"] for m in precos["modelos"].values())


def test_pontua_o_run_real_senac_a_partir_do_recibo():
    placar = bm.pontuar_estado(_estado(), bm.carregar_precos())
    assert placar["paginas"] == placar["paginas_prontas"] == 5
    assert placar["retentativas"] == 5 and placar["fallbacks"] == []
    assert abs(placar["custo_ledger_usd"] - 1.551578) < 1e-6
    assert placar["custo_tabela_oficial_usd"] > 0
    assert placar["por_tipo"]["write"]["tentativas"] == 10


def test_nome_de_modelo_normaliza_para_a_tabela():
    assert bm.modelo_base("gemini/gemini-3.5-flash") == "gemini-3.5-flash"
    assert bm.modelo_base("gpt-4.1-2025-04-14") == "gpt-4.1"


def test_estimativa_cobre_toda_a_matriz_e_se_declara_estimativa():
    config = yaml.safe_load((bm.RAIZ / "config.yaml").read_text(encoding="utf-8"))
    matriz = yaml.safe_load(bm.MATRIZ_PADRAO.read_text(encoding="utf-8"))
    est = bm.estimar_matriz(_estado(), matriz, bm.carregar_precos(), config)
    assert "atual" in est and set(est) == set(matriz["configuracoes"])
    assert all("estimativa" in v["natureza"] for v in est.values())


def test_preparar_escreve_configs_sem_publicar_e_nao_executa(tmp_path):
    config = yaml.safe_load((bm.RAIZ / "config.yaml").read_text(encoding="utf-8"))
    matriz = yaml.safe_load(bm.MATRIZ_PADRAO.read_text(encoding="utf-8"))
    comandos = bm.preparar(tmp_path, matriz, config)
    assert len(comandos) == len(matriz["configuracoes"]) * matriz["repeticoes"]
    gerado = yaml.safe_load((tmp_path / "redacao_flash_3_8" / "config.yaml").read_text())
    assert gerado["run"]["publish"] is False
    assert gerado["steps"]["write_page"]["model"] == "gemini/gemini-3.8-flash"
    # o resto do passo veio do config real (validadores preservados)
    assert "pagespec" in gerado["steps"]["write_page"]["validators"]
    assert not list(tmp_path.rglob("state.json"))      # nada rodou
