"""CLI local, fixtures versionadas, replay reproduzível e recibos verificáveis."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
LAB = RAIZ / "experiments" / "data-intelligence-lab"
CLI = LAB / "scripts" / "viability_cli.py"
FIX = LAB / "fixtures" / "viability"

FIXTURES_MINIMAS = {
    "senac_sanitizada", "campanha_favoravel", "proximo_do_equilibrio", "moeda_desconhecida", "moeda_apenas_atestada",
    "cambio_ausente", "custo_ausente", "receita_ausente", "receita_zero_observada", "receita_atrasada", "dados_imaturos",
    "limite_financeiro_ausente", "simulacao_inexistente", "simulacao_pontos_duplicados", "simulacao_nao_monotonica",
    "curva_ultimos_20pct_destroem", "campanha_nova_sem_historico", "roas_medio_bom_marginal_destroi",
}


def cli(*args, cwd=None):
    return subprocess.run([sys.executable, "-I", str(CLI), *args], capture_output=True, text=True, cwd=str(cwd or LAB))


def test_fixtures_minimas_existem_com_manifesto_integro():
    nomes = {p.stem for p in FIX.glob("*.json") if p.name != "MANIFEST.json"}
    assert FIXTURES_MINIMAS <= nomes, FIXTURES_MINIMAS - nomes
    man = json.loads((FIX / "MANIFEST.json").read_text())
    for nome, sha in man["sha256"].items():
        assert hashlib.sha256((FIX / nome).read_bytes()).hexdigest() == sha, nome


def test_fixture_senac_nao_tem_identificador_real():
    txt = (FIX / "senac_sanitizada.json").read_text()
    assert "24278665189" not in txt and "senac" not in txt.lower()


def test_evaluate_conclusivo_exit_0_e_gera_json_relatorio_recibo(tmp_path):
    r = cli("evaluate", str(FIX / "campanha_favoravel.json"), "--saida", str(tmp_path))
    assert r.returncode == 0, r.stderr
    out = json.loads((tmp_path / "resultado.json").read_text())
    assert out["verdict"] == "already_profitable"
    assert (tmp_path / "relatorio.md").exists() and (tmp_path / "recibo.json").exists()
    rec = json.loads((tmp_path / "recibo.json").read_text())
    assert rec["input_hash"] == out["input_hash"] and rec["result_hash"] == out["result_hash"] and len(rec["codigo_sha256"]) == 64


def test_evaluate_insuficiente_exit_3(tmp_path):
    r = cli("evaluate", str(FIX / "receita_ausente.json"), "--saida", str(tmp_path))
    assert r.returncode == 3
    assert json.loads((tmp_path / "resultado.json").read_text())["verdict"] == "insufficient_evidence"


def test_evaluate_entrada_invalida_exit_2(tmp_path):
    ruim = tmp_path / "ruim.json"
    ruim.write_text(json.dumps({"candidato_id": "x"}))
    r = cli("evaluate", str(ruim), "--saida", str(tmp_path / "o"))
    assert r.returncode == 2 and "entrada inválida" in (r.stderr + r.stdout).lower()


def test_verify_recibo_integro_exit_0_e_adulterado_exit_4(tmp_path):
    cli("evaluate", str(FIX / "senac_sanitizada.json"), "--saida", str(tmp_path))
    assert cli("verify", str(tmp_path / "recibo.json")).returncode == 0
    rec = json.loads((tmp_path / "recibo.json").read_text())
    rec["result_hash"] = "0" * 64
    (tmp_path / "recibo.json").write_text(json.dumps(rec))
    assert cli("verify", str(tmp_path / "recibo.json")).returncode == 4


def test_frontier_e_simulation_subcomandos(tmp_path):
    assert cli("frontier", str(FIX / "senac_sanitizada.json"), "--saida", str(tmp_path / "f")).returncode == 0
    fr = json.loads((tmp_path / "f" / "fronteira.json").read_text())
    assert "required_rpc_multiplier" in fr
    r = cli("simulation", str(FIX / "curva_ultimos_20pct_destroem.json"), "--saida", str(tmp_path / "s"))
    assert r.returncode == 0
    sim = json.loads((tmp_path / "s" / "simulacao.json").read_text())
    assert sim["disponivel"] is True and sim["primeiro_ponto_destrutivo_micros"] is not None
    r2 = cli("simulation", str(FIX / "simulacao_inexistente.json"), "--saida", str(tmp_path / "s2"))
    assert r2.returncode == 3


def test_replay_reproduzivel_e_compara_com_baselines(tmp_path):
    a = cli("replay", str(FIX), "--saida", str(tmp_path / "a"))
    b = cli("replay", str(FIX), "--saida", str(tmp_path / "b"))
    assert a.returncode == 0 and b.returncode == 0, a.stderr + b.stderr
    ra = json.loads((tmp_path / "a" / "replay.json").read_text())
    rb = json.loads((tmp_path / "b" / "replay.json").read_text())
    assert ra["replay_hash"] == rb["replay_hash"]
    casos = {c["fixture"]: c for c in ra["casos"]}
    assert casos["senac_sanitizada"]["verdict"] == "structurally_unviable"
    assert casos["roas_medio_bom_marginal_destroi"]["baselines"]["cpc_medio"] != casos["roas_medio_bom_marginal_destroi"]["kernel_marginal"]
    assert set(casos["senac_sanitizada"]["baselines"]) == {"manter", "nao_lancar", "alocacao_igual", "cpc_medio", "rpc_medio"}
    assert ra["declaracao"]["superioridade_declarada"] is False
    assert (tmp_path / "a" / "replay.md").exists()
