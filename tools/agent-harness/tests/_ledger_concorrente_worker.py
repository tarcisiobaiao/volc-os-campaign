"""Consumidor de gate em processo separado. Precisa ser importável pelo spawn."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def argv_do_caso(caso: dict) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve().parent / "_gate_fisico.py"),
        str(caso["marcador"]),
        str(caso.get("atraso", 0.0)),
        str(caso.get("exit_code", 0)),
    ]


def consumidor(caso: dict, barreira=None) -> dict:
    from volc_agent_harness.v3.gate_runner import run_gate_with_ledger
    from volc_agent_harness.v3.ledger import EvidenceLedger

    ledger = EvidenceLedger(Path(caso["ledger"]))
    if barreira is not None:
        barreira.wait(timeout=30)
    saida = run_gate_with_ledger(
        gate_index=1,
        argv=argv_do_caso(caso),
        worktree=Path(caso["worktree"]),
        env={"PATH": caso.get("path", "/usr/bin:/bin")},
        timeout=caso.get("timeout", 60),
        ledger=ledger,
        acceptance_id=caso["acceptance_id"],
        base_sha="s",
        candidate_sha=None,
        context_digest=caso["ctx"],
        env_fingerprint=caso["fp"],
        production_digest=caso["prod"],
        test_digest=caso["test"],
        run_id=caso["run_id"],
        worker_id=caso["worker_id"],
        lease_seconds=caso.get("lease_seconds", 60),
        wait_seconds=caso.get("wait_seconds", 25.0),
    )
    return saida.as_dict()


def main() -> int:
    caso = json.loads(sys.argv[1])
    resultado = consumidor(caso)
    Path(caso["saida"]).write_text(json.dumps(resultado), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
