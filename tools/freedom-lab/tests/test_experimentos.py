import copy
import hashlib
import json

import pytest

from volc_lab.experimentos import validar


def _base(tmp_path):
    art = tmp_path / "saida.json"
    art.write_text(json.dumps({"ok": True}), encoding="utf-8")
    return {
        "experiment_id": "exp-teste-001",
        "hypothesis": {
            "statement": "A regra X reduz custo sem perder qualidade",
            "falsified_if": "custo observado >= baseline ou qualidade < 0.9",
            "primary_metric": "custo", "direction": "decrease", "min_effect": 1,
        },
        "baseline": {"description": "regra atual", "values": {"custo": 10}},
        "input_snapshot": {
            "id": "snap-1", "source": "fixture sintética",
            "sha256": "0" * 64, "contains_pii": False,
        },
        "method": {"description": "replay", "seeds": [7], "replay_without_api": True,
                   "external_writes": 0, "external_calls": {"mode": "none", "count": 0},
                   "environment": {"base_ref": "c233031a", "lock_sha256": "1" * 64}},
        "dependencies": [{"package": "pandas", "version": "2.x"}],
        "metrics": {
            "time": {"unit": "s", "value": 1.2, "kind": "observed"},
            "cost": {"unit": "USD", "value": 0, "kind": "observed"},
            "quality": {"unit": "ratio", "value": 0.95, "kind": "observed"},
        },
        "result": {"observed": {"custo": {"baseline": 10, "candidate": 8}},
                   "estimated": {"custo_mensal": 240},
                   "hypothesis_outcome": "supported", "reproducible": "identical"},
        "limitations": ["amostra sintética"],
        "decision": "adopt",
        "rollback_or_cleanup": {"steps": ["apagar tmp"], "done": True},
        "artifacts": [{"path": "saida.json",
                       "sha256": hashlib.sha256(art.read_bytes()).hexdigest()}],
    }


def test_experimento_completo_passa(tmp_path):
    assert validar(_base(tmp_path), tmp_path) == []


@pytest.mark.parametrize("mutar,trecho", [
    (lambda e: e["hypothesis"].pop("falsified_if"), "falsified_if"),
    (lambda e: e["input_snapshot"].update(contains_pii=True), "contains_pii"),
    (lambda e: e["metrics"]["cost"].update(value=None), "ausência não é zero"),
    (lambda e: e["metrics"]["quality"].update(kind="not_measured", value=None), "not_measured_reason"),
    (lambda e: e["result"]["estimated"].update(custo=9), "observed e estimated"),
    (lambda e: e["result"].update(hypothesis_outcome="inconclusive"), "decision=adopt"),
    (lambda e: e["method"].pop("seeds"), "seeds"),
    (lambda e: e["method"].update(replay_without_api=False), "replay_not_possible_reason"),
    (lambda e: e["rollback_or_cleanup"].update(done=False), "done"),
    (lambda e: e["artifacts"][0].update(sha256="f" * 64), "SHA divergente"),
    (lambda e: e["method"].update(external_writes=1), "external_writes"),
    (lambda e: e["result"]["observed"]["custo"].update(candidate=9.5), "min_effect"),
    (lambda e: e["result"]["observed"]["custo"].update(baseline=None), "baseline e candidate"),
    (lambda e: e["result"].update(reproducible="not_reproduced"), "reproducible"),
    (lambda e: e["hypothesis"].pop("primary_metric"), "primary_metric"),
    (lambda e: e["method"]["external_calls"].update(mode="readonly", count=2), "replay_without_api=true"),
    (lambda e: e["method"].pop("environment"), "environment"),
    (lambda e: e["artifacts"][0].update(path="../../.env"), "path"),
    (lambda e: e["artifacts"][0].update(path="/etc/passwd"), "path"),
    (lambda e: e.update(decision="talvez"), "decision"),
    (lambda e: e["hypothesis"].update(min_effect=float("nan")), "min_effect"),
    (lambda e: e["result"]["observed"]["custo"].update(candidate=float("nan")), "finitos"),
    (lambda e: e["result"]["observed"]["custo"].update(baseline=True, candidate=False), "finitos"),
    (lambda e: e["hypothesis"].update(min_effect=0), "min_effect"),
    (lambda e: e["metrics"]["quality"].update(kind="not_measured", value=0, not_measured_reason="x"), "não pode ter value"),
    (lambda e: e.update(artifacts=[]), "artifacts"),
    (lambda e: e["artifacts"][0].update(path="sub/.ENV"), "path"),
])
def test_cada_violacao_e_recusada(tmp_path, mutar, trecho):
    exp = copy.deepcopy(_base(tmp_path))
    mutar(exp)
    erros = validar(exp, tmp_path)
    assert erros, "violação passou calada"
    assert any(trecho in e for e in erros), erros


def test_reject_com_hipotese_refutada_e_valido(tmp_path):
    exp = _base(tmp_path)
    exp["decision"] = "reject"
    exp["result"]["hypothesis_outcome"] = "refuted"
    assert validar(exp, tmp_path) == []


def test_traversal_por_symlink_e_recusado(tmp_path):
    fora = tmp_path.parent / "segredo-fora.txt"
    fora.write_text("x")
    exp = _base(tmp_path)
    (tmp_path / "link").symlink_to(fora)
    exp["artifacts"] = [{"path": "link", "sha256": hashlib.sha256(b"x").hexdigest()}]
    assert any("fora do diretório" in e for e in validar(exp, tmp_path))


def test_cli_recusa_nan_no_json(tmp_path):
    from volc_lab.experimentos import main
    f = tmp_path / "e.json"
    f.write_text('{"x": NaN}')
    assert main([str(f)]) == 1


def test_sem_base_artefatos_nao_conferidos(tmp_path):
    assert any("não conferidos" in e for e in validar(_base(tmp_path), None))
