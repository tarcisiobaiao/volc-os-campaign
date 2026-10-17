"""CLI local, fixtures versionadas, replay reproduzível e recibos verificáveis.

O recibo prova integridade e reprodutibilidade (sha256 de código, ambiente, entrada, resultado, relatório),
NÃO identidade nem autoria: isso exigiria assinatura, que o laboratório não tem."""
from __future__ import annotations

import hashlib
import json
import re
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
# O veredito "structurally_unviable" (V1) vira "unviable_under_declared_scenarios" no gate v2 (subagente A).
# O teste aceita o valor NOVO; o antigo fica só até o integrador juntar as duas branches.
VEREDITO_INVIAVEL = {"unviable_under_declared_scenarios"}
CAMPOS_RECIBO = {"kernel_version", "codigo_sha256", "source_commit", "ambiente", "entrada", "input_hash", "result_hash",
                 "resultado_arquivo", "resultado_sha256", "relatorio_arquivo", "relatorio_sha256", "external_actions"}


def cli(*args, cwd=None):
    return subprocess.run([sys.executable, "-I", str(CLI), *args], capture_output=True, text=True, cwd=str(cwd or LAB))


def _recibo(d: Path) -> dict:
    return json.loads((d / "recibo.json").read_text())


def _grava(d: Path, rec: dict) -> None:
    (d / "recibo.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1, sort_keys=True))


# --------------------------------------------------------------------------- fixtures
def test_fixtures_minimas_existem_com_manifesto_integro():
    nomes = {p.stem for p in FIX.glob("*.json") if p.name != "MANIFEST.json"}
    assert FIXTURES_MINIMAS <= nomes, FIXTURES_MINIMAS - nomes
    man = json.loads((FIX / "MANIFEST.json").read_text())
    assert set(man["sha256"]) == {f"{n}.json" for n in nomes}
    for nome, sha in man["sha256"].items():
        assert hashlib.sha256((FIX / nome).read_bytes()).hexdigest() == sha, nome


def test_fixture_senac_nao_tem_identificador_real():
    txt = (FIX / "senac_sanitizada.json").read_text()
    assert re.search(r"\b\d{10,12}\b", txt) is None  # nenhum id de campanha/conta bruto
    assert "senac" not in txt.lower()


def test_fixtures_seguem_o_contrato_v2():
    for p in sorted(FIX.glob("*.json")):
        if p.name == "MANIFEST.json":
            continue
        e = json.loads(p.read_text())["entrada"]
        assert "freshness" not in e and e["freshness_sla_dias"] == 7, p.name
        pm = e["perda_maxima"]
        assert "proveniencia" not in pm, p.name
        if pm["valor"] is not None:
            a = pm["autorizacao"]
            assert a["authorization_id"] == "AUTH-LAB-0001" and a["issuer"] == "owner:lab-fixture" and len(a["hash"]) == 64, p.name
            assert a["effective_at"] <= e["as_of"] and a["disponivel_em"] <= e["as_of"], p.name
        for nome in ("cambio", "revshare", "imposto"):
            par = e[nome]
            assert len(par["hash"]) == 64, (p.name, nome)
            if par.get("taxa", par.get("valor")) is not None:
                assert par["effective_at"] <= e["as_of"] and par["disponivel_em"] <= e["as_of"] and par["versao"], (p.name, nome)


# --------------------------------------------------------------------------- evaluate / recibo
def test_evaluate_conclusivo_exit_0_e_gera_json_relatorio_recibo(tmp_path):
    r = cli("evaluate", str(FIX / "campanha_favoravel.json"), "--saida", str(tmp_path))
    assert r.returncode == 0, r.stderr
    out = json.loads((tmp_path / "resultado.json").read_text())
    assert out["verdict"] == "already_profitable"
    assert (tmp_path / "relatorio.md").exists() and (tmp_path / "recibo.json").exists()
    rec = _recibo(tmp_path)
    assert CAMPOS_RECIBO <= set(rec)
    assert rec["input_hash"] == out["input_hash"] and rec["result_hash"] == out["result_hash"] and len(rec["codigo_sha256"]) == 64
    assert rec["external_actions"] == 0 and rec["resultado_arquivo"] == "resultado.json" and rec["relatorio_arquivo"] == "relatorio.md"
    assert rec["resultado_sha256"] == hashlib.sha256((tmp_path / "resultado.json").read_bytes()).hexdigest()
    assert rec["relatorio_sha256"] == hashlib.sha256((tmp_path / "relatorio.md").read_bytes()).hexdigest()
    assert set(rec["ambiente"]) == {"python", "plataforma", "uv_lock_sha256"}
    assert rec["ambiente"]["uv_lock_sha256"] == hashlib.sha256((LAB / "uv.lock").read_bytes()).hexdigest()
    assert rec["source_commit"] == "indisponivel" or re.fullmatch(r"[0-9a-f]{40}", rec["source_commit"])


def test_evaluate_insuficiente_exit_3(tmp_path):
    r = cli("evaluate", str(FIX / "receita_ausente.json"), "--saida", str(tmp_path))
    assert r.returncode == 3
    assert json.loads((tmp_path / "resultado.json").read_text())["verdict"] == "insufficient_evidence"


def test_evaluate_entrada_invalida_exit_2(tmp_path):
    ruim = tmp_path / "ruim.json"
    ruim.write_text(json.dumps({"candidato_id": "x"}))
    r = cli("evaluate", str(ruim), "--saida", str(tmp_path / "o"))
    assert r.returncode == 2 and "entrada inválida" in (r.stderr + r.stdout).lower()


def test_evaluate_recusa_perda_maxima_sem_autorizacao_exit_2(tmp_path):
    doc = json.loads((FIX / "campanha_favoravel.json").read_text())
    doc["entrada"]["perda_maxima"] = {"valor": {"micros": 1, "moeda": "BRL"}, "horizonte_dias": 1, "proveniencia": "owner"}
    (tmp_path / "sem_aut.json").write_text(json.dumps(doc))
    r = cli("evaluate", str(tmp_path / "sem_aut.json"), "--saida", str(tmp_path / "o"))
    assert r.returncode == 2 and "autoriza" in r.stderr.lower()


# --------------------------------------------------------------------------- verify
def test_verify_recibo_integro_exit_0(tmp_path):
    cli("evaluate", str(FIX / "senac_sanitizada.json"), "--saida", str(tmp_path))
    r = cli("verify", str(tmp_path / "recibo.json"))
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("arquivo", ["resultado.json", "relatorio.md"])
def test_verify_sem_resultado_ou_relatorio_exit_4(tmp_path, arquivo):
    cli("evaluate", str(FIX / "senac_sanitizada.json"), "--saida", str(tmp_path))
    (tmp_path / arquivo).unlink()
    r = cli("verify", str(tmp_path / "recibo.json"))
    assert r.returncode == 4 and arquivo in r.stderr


@pytest.mark.parametrize("campo,valor", [
    ("result_hash", "0" * 64), ("input_hash", "0" * 64), ("codigo_sha256", "0" * 64), ("resultado_sha256", "0" * 64),
    ("relatorio_sha256", "0" * 64), ("external_actions", 1),
])
def test_verify_recibo_adulterado_exit_4(tmp_path, campo, valor):
    cli("evaluate", str(FIX / "senac_sanitizada.json"), "--saida", str(tmp_path))
    rec = _recibo(tmp_path)
    rec[campo] = valor
    _grava(tmp_path, rec)
    r = cli("verify", str(tmp_path / "recibo.json"))
    assert r.returncode == 4 and campo in r.stderr, r.stderr


def test_verify_ambiente_uv_lock_diferente_exit_4(tmp_path):
    cli("evaluate", str(FIX / "senac_sanitizada.json"), "--saida", str(tmp_path))
    rec = _recibo(tmp_path)
    rec["ambiente"]["uv_lock_sha256"] = "0" * 64
    _grava(tmp_path, rec)
    r = cli("verify", str(tmp_path / "recibo.json"))
    assert r.returncode == 4 and "uv_lock_sha256" in r.stderr


def test_verify_entrada_adulterada_no_recibo_exit_4(tmp_path):
    cli("evaluate", str(FIX / "senac_sanitizada.json"), "--saida", str(tmp_path))
    rec = _recibo(tmp_path)
    rec["entrada"]["cliques"]["valor"] += 1
    _grava(tmp_path, rec)
    r = cli("verify", str(tmp_path / "recibo.json"))
    assert r.returncode == 4 and "input_hash" in r.stderr


def test_verify_resultado_reescrito_exit_4(tmp_path):
    cli("evaluate", str(FIX / "senac_sanitizada.json"), "--saida", str(tmp_path))
    (tmp_path / "resultado.json").write_text("{}\n")
    r = cli("verify", str(tmp_path / "recibo.json"))
    assert r.returncode == 4 and "resultado_sha256" in r.stderr


# --------------------------------------------------------------------------- frontier / simulation
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


# --------------------------------------------------------------------------- replay
def test_replay_reproduzivel_e_compara_com_baselines(tmp_path):
    a = cli("replay", str(FIX), "--saida", str(tmp_path / "a"))
    b = cli("replay", str(FIX), "--saida", str(tmp_path / "b"))
    assert a.returncode == 0 and b.returncode == 0, a.stderr + b.stderr
    ra = json.loads((tmp_path / "a" / "replay.json").read_text())
    rb = json.loads((tmp_path / "b" / "replay.json").read_text())
    assert ra["replay_hash"] == rb["replay_hash"]
    casos = {c["fixture"]: c for c in ra["casos"]}
    assert casos["senac_sanitizada"]["verdict"] in VEREDITO_INVIAVEL
    assert casos["roas_medio_bom_marginal_destroi"]["baselines"]["cpc_medio"] != casos["roas_medio_bom_marginal_destroi"]["kernel_marginal"]
    assert set(casos["senac_sanitizada"]["baselines"]) == {"manter", "nao_lancar", "alocacao_igual", "cpc_medio", "rpc_medio"}
    assert ra["declaracao"]["superioridade_declarada"] is False
    assert (tmp_path / "a" / "replay.md").exists()


def test_replay_emite_recibo_verificavel_com_replay_hash(tmp_path):
    assert cli("replay", str(FIX), "--saida", str(tmp_path)).returncode == 0
    rec = _recibo(tmp_path)
    assert rec["replay_hash"] == json.loads((tmp_path / "replay.json").read_text())["replay_hash"]
    assert rec["resultado_arquivo"] == "replay.json" and rec["relatorio_arquivo"] == "replay.md" and rec["external_actions"] == 0
    assert rec["resultado_sha256"] == hashlib.sha256((tmp_path / "replay.json").read_bytes()).hexdigest()
    assert set(rec["ambiente"]) == {"python", "plataforma", "uv_lock_sha256"} and rec["fixtures_dir"] == str(FIX)
    assert cli("verify", str(tmp_path / "recibo.json")).returncode == 0
    rec["replay_hash"] = "0" * 64
    _grava(tmp_path, rec)
    r = cli("verify", str(tmp_path / "recibo.json"))
    assert r.returncode == 4 and "replay_hash" in r.stderr
    rec = _recibo(tmp_path)  # recibo adulterado acima; regrava com replay_hash certo e relatório faltando
    rec["replay_hash"] = json.loads((tmp_path / "replay.json").read_text())["replay_hash"]
    _grava(tmp_path, rec)
    (tmp_path / "replay.md").unlink()
    assert cli("verify", str(tmp_path / "recibo.json")).returncode == 4
