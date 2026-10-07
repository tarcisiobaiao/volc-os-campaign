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
    assert set(precos["fontes"]) == {"google", "openai", "openai_deprecacoes"}
    assert precos["deprecados"]["gpt-5.1"] == "2027-04-01"
    assert all(m["fonte"] in precos["fontes"] for m in precos["modelos"].values())


def test_pontua_o_run_real_senac_a_partir_do_recibo():
    placar = bm.pontuar_estado(_estado(), bm.carregar_precos())
    assert placar["paginas"] == placar["paginas_prontas"] == 5
    assert placar["retentativas"] == 5 and placar["fallbacks"] == []
    assert abs(placar["custo_ledger_usd"] - 1.551578) < 1e-6
    assert placar["custo_tabela_oficial_usd"] > 0
    # LP e internas separadas: 1 tentativa na LP, 9 nas quatro internas
    assert placar["por_tipo"]["write_lp"]["tentativas"] == 1
    assert placar["por_tipo"]["write_page"]["tentativas"] == 9
    assert placar["funil_aprovado"] is True
    assert placar["arquiteto_medido"] is False          # o recibo antigo não tinha
    assert set(placar["retentativas_por_passo"]) == {"write_p2", "write_p3", "write_p4", "write_p5"}


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


def test_pontua_arquiteto_causas_e_pedido_x_servido_a_partir_dos_artefatos(tmp_path):
    """O custo do arquiteto vem da telemetria gravada no card; a causa da
    retentativa vem do log; o pedido x servido vem do estado."""
    import json
    estado = _estado()
    res = estado.step_status["write_p2"]
    estado.step_status["write_p2"] = res.model_copy(update={
        "model_requested": "gemini/gemini-3.5-flash", "model_used": "gpt-4.1"})
    (tmp_path / "funnel_architecture.json").write_text(json.dumps({"revisao_arquitetura": {
        "telemetria": [{"etapa": "arquiteto", "modelo_solicitado": "gemini-3.5-flash",
                        "modelo_servido": "gemini-3.5-flash", "entrada": 10000,
                        "saida": 20000, "latencia_ms": 30000},
                       {"etapa": "revisor_do_arquiteto", "modelo_solicitado": "gemini-3.5-flash",
                        "modelo_servido": None, "entrada": 12000, "saida": 15000,
                        "latencia_ms": 25000}]}}), encoding="utf-8")
    (tmp_path / "log.jsonl").write_text(
        json.dumps({"step": "write_p2", "attempt": 1, "causas": ["pagespec", "cta_style"]})
        + "\n", encoding="utf-8")
    placar = bm.pontuar_estado(estado, bm.carregar_precos(), tmp_path)
    assert placar["arquiteto_medido"] is True
    # (10k*1.50 + 20k*9.00 + 12k*1.50 + 15k*9.00) / 1e6
    assert abs(placar["custo_arquiteto_usd"] - 0.348) < 1e-6
    assert placar["custo_total_usd"] > placar["custo_tabela_oficial_usd"]
    assert placar["retentativas_por_passo"]["write_p2"]["causas"] == ["pagespec", "cta_style"]
    assert placar["modelo_pedido_x_servido"]["write_p2"] == {
        "pedido": "gemini/gemini-3.5-flash", "servido": "gpt-4.1"}


def test_matriz_nao_usa_modelo_deprecado_e_traz_condicoes_de_parada():
    matriz = yaml.safe_load(bm.MATRIZ_PADRAO.read_text(encoding="utf-8"))
    deprecados = set(bm.carregar_precos()["deprecados"])
    usados = {cfg["model"] for conf in matriz["configuracoes"].values()
              for cfg in (conf or {}).values()}
    assert not ({bm.modelo_base(m) for m in usados} & deprecados)
    assert matriz["orcamento"]["max_usd_total"] > 0 and matriz["editorial_v2"] is True
