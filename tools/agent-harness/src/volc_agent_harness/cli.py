"""CLI para executar investigação ou implementação isolada com revisão."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .mission import run
from .models import MissionSpec


def compile_only(argv: Sequence[str] | None = None) -> int:
    """`volc-harness compile` — a fase 1 do pipeline V3, sem chamar modelo.

    Existe para que o operador (e o CI) possam provar que a missão compila antes
    de gastar um writer. Uma missão que não compila sai com o código da classe de
    falha, não com um traceback genérico.
    """

    from .v3.failures import HarnessFailure
    from .v3.pipeline import PipelineArtifacts, prewriter_phase

    parser = argparse.ArgumentParser(description=compile_only.__doc__)
    parser.add_argument("--mission", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--roadmap", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    bruto = json.loads(args.mission.read_text(encoding="utf-8"))
    roadmap_path = args.roadmap or (args.repo / "volc-os-workbook" / "ROADMAP-VIVO.json")
    roadmap = json.loads(roadmap_path.read_text(encoding="utf-8")) if roadmap_path.exists() else {}
    runs = (args.repo / "tools" / "agent-harness" / "runs").resolve()
    run_dir = (args.out.resolve() if args.out else runs / "compile-check")
    if runs not in run_dir.parents and run_dir != runs:
        # Artefato de runtime fora de runs/ escapa do .gitignore e acaba
        # versionado. O destino é restrito, não sugerido.
        print("[SPEC_ERROR] --out precisa ficar sob tools/agent-harness/runs")
        print(f"  detalhe: {run_dir}")
        return 3

    from pydantic import ValidationError

    from .v3.schema_version import assert_compilable

    try:
        # O schema vem ANTES da validação do MissionSpec: uma missão V2 precisa
        # receber a orientação de migração, não um traceback de pydantic.
        assert_compilable(bruto)
        mission = MissionSpec.model_validate(bruto)
        compilada, art = prewriter_phase(
            mission_dict=bruto, mission_obj=mission, tree=args.repo,
            roadmap=roadmap, run_dir=run_dir,
        )
    except ValidationError as erro:
        primeira = erro.errors()[0] if erro.errors() else {}
        print("[SPEC_ERROR] missão não valida contra o MissionSpec")
        print(f"  detalhe: {'.'.join(str(x) for x in primeira.get('loc', ()))}: "
              f"{primeira.get('msg', '')}")
        print("  destino: mission_compiler | writer relançado: False")
        return 3
    except HarnessFailure as falha:
        print(f"[{falha.classe.value}] {falha.resumo}")
        if falha.detalhe:
            print(f"  detalhe: {falha.detalhe}")
        if falha.reproducao:
            print(f"  reproduza: {falha.reproducao}")
        print(f"  destino: {falha.destino or 'decisão humana'} | writer relançado: {falha.permite_retry}")
        return 3
    print(f"missão compila: {compilada.mission_id}")
    print(f"  aceites: {', '.join(compilada.acceptance_ids)}")
    print(f"  regressões obrigatórias: {', '.join(compilada.regression_acceptance_ids) or '—'}")
    print(f"  gates antes do writer: {compilada.gates_runnable_before_writer}")
    print(f"  gates que dependem de produced: {compilada.gates_depending_on_produced}")
    print(f"  artefatos: {art.run_dir}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entrypoint único. Uma missão V3 não chega ao writer sem compilar.

    Antes existiam dois caminhos: `run` ia direto para `mission.run`, e o
    compilador V3 vivia numa biblioteca que ninguém consumia. O revisor resumiu
    assim: "o runtime não chama o compilador V3 antes do writer".
    """

    from pydantic import ValidationError

    from .v3.failures import HarnessFailure
    from .v3.schema_version import assert_compilable

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    bruto = json.loads(args.mission.read_text(encoding="utf-8"))
    versao = int(bruto.get("mission_schema_version", 2))

    if versao < 3:
        # Nunca fallback silencioso: ou migra, ou pede o comando depreciado.
        print("[SPEC_ERROR] missão no schema 2 não passa pelo compilador V3")
        print(f"  detalhe: {bruto.get('mission_id', '?')} precisa declarar "
              "mission_schema_version=3, acceptance_ids e ownership_envelope")
        print('  reproduza: adicione "mission_schema_version": 3 e os campos exigidos')
        print("  destino: mission_compiler | writer relançado: False")
        return 3

    try:
        assert_compilable(bruto)
        mission = MissionSpec.model_validate(bruto)
    except ValidationError as erro:
        primeira = erro.errors()[0] if erro.errors() else {}
        print("[SPEC_ERROR] missão não valida contra o MissionSpec")
        print(f"  detalhe: {'.'.join(str(x) for x in primeira.get('loc', ()))}: "
              f"{primeira.get('msg', '')}")
        return 3
    except HarnessFailure as falha:
        print(f"[{falha.classe.value}] {falha.resumo}")
        if falha.detalhe:
            print(f"  detalhe: {falha.detalhe}")
        if falha.reproducao:
            print(f"  reproduza: {falha.reproducao}")
        return 3

    try:
        run_dir, result = run(args.repo, mission)
    except HarnessFailure as falha:
        # HarnessFailure PRIMEIRO: ela é uma Exception, e um `except Exception`
        # antes dela engoliria toda falha tipada do pipeline.
        print(f"[{falha.classe.value}] {falha.resumo}")
        if falha.detalhe:
            print(f"  detalhe: {falha.detalhe}")
        if falha.reproducao:
            print(f"  reproduza: {falha.reproducao}")
        print(f"  destino: {falha.destino or 'decisão humana'} | "
              f"writer relançado: {falha.permite_retry}")
        return 3
    except Exception as erro:
        # Falha de boot ou upgrade — registry, ledger, overlay — nunca sai como
        # traceback nu nem como "missão executada sem resultado".
        from .v3.failures import classify_exception

        classe = classify_exception(erro)
        print(f"[{classe.value}] falha de inicialização do harness")
        print(f"  detalhe: {type(erro).__name__}: {str(erro)[:200]}")
        print("  destino: gatekeeper | writer relançado: False")
        return 4

    print(f"run: {result['run_id']}")
    print(f"base: {result['base_sha']}")
    print(f"resultado: {'ok' if result['ok'] else 'com falhas'}")
    if result.get("writer_commit"):
        print(f"commit do writer: {result['writer_commit']}")
    if result.get("candidate_status"):
        print(f"candidato: {result['candidate_status']}")
    for worker in result["workers"]:
        print(
            f"- {worker['worker_id']} ({worker['provider']} / "
            f"{worker.get('model') or 'default'} / {worker.get('effort', 'default')}): "
            f"{'ok' if worker['ok'] else worker.get('error', 'falhou')}"
        )
    print(f"artefatos: {run_dir}")
    accepted = result["ok"] and result.get("candidate_status") not in {
        "changes_requested",
        "blocked",
    }
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
