"""Supervisor V1 multimodelo para missões explicitamente enfileiradas.

Seleciona por DAG/ownership, executa até quatro writers isolados e termina em
commits candidatos revisados. Nunca faz merge, push, deploy, migration,
curadoria ou promoção editorial.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence

from .mission import run as run_mission
from .v3.failures import FailureClass, HarnessFailure
from .v3.schema_version import assert_compilable
from .models import MissionSpec
from .supervisor_models import SupervisorJobSpec, SupervisorQueueSpec
from .supervisor_store import SupervisorStore, ownership_overlaps


TERMINAL_SUCCESS = {"done", "completed", "concluida", "concluída"}
OPEN_STATES = {"todo", "partial", "a_fazer", "parcial"}
PROVIDER_CREDENTIALS = {
    "gemini": "GEMINI_API_KEY",
    "claude": "VOLC_CLAUDE_CODE_OAUTH_TOKEN",
    "deepseek": "DEEPSEEK_API_KEY",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _load_roadmap(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    raw = path.read_bytes()
    document = json.loads(raw)
    tasks: dict[str, dict[str, Any]] = {}
    for initiative in document.get("initiatives", []):
        for task in initiative.get("tasks", []):
            task_id = task.get("id")
            if task_id:
                tasks[task_id] = task
    return tasks, hashlib.sha256(raw).hexdigest()


def _declared_dependencies(
    task: dict[str, Any], job: SupervisorJobSpec
) -> list[str]:
    values: list[str] = list(job.dependencies)
    for key in ("dependencies", "depends_on"):
        declared = task.get(key, [])
        if isinstance(declared, str):
            declared = [declared]
        if isinstance(declared, list):
            values.extend(item for item in declared if isinstance(item, str))
    return list(dict.fromkeys(values))


def _writer_ownership(mission: MissionSpec) -> list[str]:
    writer = next(worker for worker in mission.workers if worker.role == "writer")
    return writer.effective_writable_paths


def eligibility_reason(
    *,
    repo: Path,
    job: SupervisorJobSpec,
    tasks: dict[str, dict[str, Any]],
    mission: MissionSpec,
    base_sha: str,
) -> str | None:
    task = tasks.get(job.task_id)
    if task is None:
        return "task_id ausente no Roadmap Vivo"
    if task.get("status") not in OPEN_STATES:
        return f"estado editorial não elegível: {task.get('status')!r}"
    acceptance = task.get("acceptance")
    if not isinstance(acceptance, list) or not acceptance:
        return "critérios de aceite ausentes"
    if mission.mode != "implementation":
        return "supervisor V0 despacha somente implementação"
    missing = sorted({
        variable
        for worker in mission.workers
        if (variable := PROVIDER_CREDENTIALS.get(worker.provider))
        and not os.environ.get(variable)
    })
    if missing:
        return "credencial explícita ausente para provider: " + ", ".join(missing)
    if mission.base_ref != base_sha:
        return "base_ref da missão não é o HEAD imutável atual"
    if job.task_id not in mission.task_ids:
        return "missão não declara o task_id do job"
    unknown = [task_id for task_id in mission.task_ids if task_id not in tasks]
    if unknown:
        return f"missão referencia task_ids inexistentes: {unknown}"
    for dependency in _declared_dependencies(task, job):
        target = tasks.get(dependency)
        if target is None:
            return f"dependência declarada inexistente: {dependency}"
        if target.get("status") not in TERMINAL_SUCCESS:
            return f"dependência aberta: {dependency}"
    return None


def _atomic_snapshot(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(
        f".tmp-{os.getpid()}-{threading.get_ident()}"
    )
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)


def _write_snapshot(
    repo: Path,
    queue: SupervisorQueueSpec,
    store: SupervisorStore,
    blockers: list[dict[str, str]],
) -> None:
    _atomic_snapshot(
        repo / "tools" / "agent-harness" / "runs" / "supervisor-state.json",
        {
            "schema_version": 1,
            "supervisor_id": queue.supervisor_id,
            "claims": store.snapshot(),
            "blockers": blockers,
        },
    )


Runner = Callable[[Path, MissionSpec], tuple[Path, dict[str, Any]]]


def _contract_digest(
    mission: MissionSpec,
    task: dict[str, Any],
    job: SupervisorJobSpec,
) -> str:
    mission_contract = mission.model_dump(
        mode="json",
        exclude={"base_ref", "lineage_root_sha", "parent_run_id", "attempt"},
    )
    task_contract = {
        "id": task.get("id"),
        "acceptance": task.get("acceptance"),
        "dependencies": _declared_dependencies(task, job),
    }
    return _value_fingerprint(
        {"mission": mission_contract, "task": task_contract}
    ) or ""


def _tree_fingerprint(repo: Path, candidate_sha: str | None) -> str | None:
    if not candidate_sha or not re.fullmatch(r"[0-9a-f]{40}", candidate_sha):
        return None
    completed = subprocess.run(
        ["git", "rev-parse", f"{candidate_sha}^{{tree}}"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() or None


def _candidate_is_valid(
    repo: Path,
    candidate_sha: str | None,
    lineage_root_sha: str,
) -> bool:
    if _tree_fingerprint(repo, candidate_sha) is None:
        return False
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", lineage_root_sha, str(candidate_sha)],
        cwd=repo,
        check=False,
        capture_output=True,
        timeout=60,
    ).returncode == 0


def _run_with_lease(
    *,
    repo: Path,
    mission: MissionSpec,
    runner: Runner,
    store: SupervisorStore,
    key: str,
    owner_nonce: str,
    lease_seconds: int,
) -> tuple[Path, dict[str, Any]]:
    heartbeat = max(5, min(30, lease_seconds // 3))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(runner, repo, mission)
        while True:
            try:
                return future.result(timeout=heartbeat)
            except concurrent.futures.TimeoutError:
                if not store.renew(key, owner_nonce, lease_seconds):
                    raise RuntimeError("lease do supervisor foi perdido durante a execução")


def _value_fingerprint(value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    material = json.dumps(
        value, ensure_ascii=False, sort_keys=True, default=str
    ).encode()
    return hashlib.sha256(material).hexdigest()


def _correction_context(result: dict[str, Any]) -> str:
    findings: list[dict[str, Any]] = []
    required: list[str] = []
    worker_errors: list[dict[str, str]] = []
    for worker in result.get("workers") or []:
        if not isinstance(worker, dict):
            continue
        if worker.get("error"):
            worker_errors.append({
                "worker_id": str(worker.get("worker_id") or "unknown"),
                "role": str(worker.get("role") or "unknown"),
                "error": str(worker["error"])[:4_000],
            })
        if worker.get("role") != "reviewer":
            continue
        review = worker.get("result") or {}
        if not isinstance(review, dict):
            continue
        for finding in review.get("confirmed_findings") or []:
            if isinstance(finding, dict):
                findings.append({
                    "severity": finding.get("severity"),
                    "title": finding.get("title"),
                    "evidence": finding.get("evidence"),
                })
        required.extend(
            str(item) for item in review.get("required_changes") or [] if item
        )
    compact = json.dumps(
        {
            "confirmed_findings": findings,
            "required_changes": required,
            "worker_errors": worker_errors,
        },
        ensure_ascii=False,
        indent=2,
    )
    return compact[:16_000]


def _finding_fingerprint(result: dict[str, Any]) -> str | None:
    context = _correction_context(result)
    if context == (
        '{\n  "confirmed_findings": [],\n  "required_changes": [],'
        '\n  "worker_errors": []\n}'
    ):
        return None
    return _value_fingerprint(context)


def _has_correction_context(result: dict[str, Any]) -> bool:
    return _finding_fingerprint(result) is not None


def _result_from_run_dir(run_dir: str | None) -> dict[str, Any]:
    if not run_dir:
        return {}
    path = Path(run_dir) / "mission-result.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _corrective_mission(
    original: MissionSpec,
    *,
    candidate_sha: str,
    root_base_sha: str,
    previous_run_id: str,
    previous_result: dict[str, Any],
    attempt: int,
) -> MissionSpec:
    return original.model_copy(
        update={
            "mission_id": f"{original.mission_id}-a{attempt}",
            "base_ref": candidate_sha,
            "lineage_root_sha": root_base_sha,
            "parent_run_id": previous_run_id,
            "attempt": attempt,
            "briefing": (
                f"{original.briefing}\n\n"
                "TENTATIVA CORRETIVA DO RATCHET\n"
                "Corrija somente os achados confirmados abaixo, sem ampliar "
                "ownership ou reinterpretar ausência como autorização. Todos "
                "os gates serão executados novamente.\n"
                f"{_correction_context(previous_result)}"
            ),
        }
    )


def _run_serial_once(
    repo: Path,
    queue: SupervisorQueueSpec,
    *,
    store: SupervisorStore,
    runner: Runner = run_mission,
) -> dict[str, Any]:
    repo = repo.resolve()
    roadmap_path = repo / queue.roadmap_path
    tasks, roadmap_sha = _load_roadmap(roadmap_path)
    base_sha = _head(repo)
    blockers: list[dict[str, str]] = []

    for job in sorted(queue.jobs, key=lambda item: (item.priority, item.job_id)):
        if not job.enabled:
            blockers.append({"job_id": job.job_id, "reason": "job desabilitado"})
            continue
        declared_mission_path = Path(job.mission_path)
        mission_path = (
            declared_mission_path
            if declared_mission_path.is_absolute()
            else repo / declared_mission_path
        )
        if not mission_path.is_file():
            blockers.append(
                {"job_id": job.job_id, "reason": "manifesto da missão ausente"}
            )
            continue
        try:
            bruto = json.loads(mission_path.read_text(encoding="utf-8"))
            # O supervisor despacha SOMENTE missão compilada. Antes ele tinha um
            # caminho próprio que ignorava o compilador V3 inteiro.
            assert_compilable(bruto)
            mission = MissionSpec.model_validate(bruto)
        except HarnessFailure as falha:
            blockers.append({
                "job_id": job.job_id,
                "reason": f"[{falha.classe.value}] {falha.resumo}",
                "detalhe": falha.detalhe,
                "como_migrar": falha.reproducao,
            })
            continue
        except Exception as error:
            blockers.append(
                {
                    "job_id": job.job_id,
                    "reason": f"manifesto inválido: {type(error).__name__}",
                }
            )
            continue
        task = tasks.get(job.task_id)
        contract_digest = (
            _contract_digest(mission, task, job)
            if isinstance(task, dict)
            else "missing-task"
        )
        prior = store.latest(job.task_id, contract_digest)
        expected_initial_base = mission.base_ref if prior is not None else base_sha
        reason = eligibility_reason(
            repo=repo,
            job=job,
            tasks=tasks,
            mission=mission,
            base_sha=expected_initial_base,
        )
        if reason:
            blockers.append({"job_id": job.job_id, "reason": reason})
            continue

        active_mission = mission
        ratchet_started_at = time.monotonic()
        attempt_limit = min(
            mission.ratchet.max_writer_attempts,
            mission.ratchet.max_review_rounds,
            job.max_attempts,
        )
        if prior is not None:
            if (
                prior["state"] == "changes_requested"
                and mission.ratchet.enabled
                and int(prior["attempt"]) < attempt_limit
                and (prior.get("resume_base_sha") or prior.get("candidate_sha"))
            ):
                prior_result = _result_from_run_dir(prior.get("run_dir"))
                if (
                    not prior_result
                    or not _has_correction_context(prior_result)
                ):
                    blockers.append({
                        "job_id": job.job_id,
                        "reason": "recibo corretivo ausente, corrompido ou sem achados",
                    })
                    continue
                lineage_root = str(
                    prior.get("lineage_root_sha") or prior.get("base_sha") or ""
                )
                resume_base = str(
                    prior.get("resume_base_sha")
                    or prior.get("candidate_sha")
                    or ""
                )
                if not _candidate_is_valid(repo, resume_base, lineage_root):
                    blockers.append({
                        "job_id": job.job_id,
                        "reason": "candidato anterior escapou da linhagem autorizada",
                    })
                    continue
                active_mission = _corrective_mission(
                    mission,
                    candidate_sha=resume_base,
                    root_base_sha=lineage_root,
                    previous_run_id=Path(str(prior.get("run_dir") or "prior")).name,
                    previous_result=prior_result,
                    attempt=int(prior["attempt"]) + 1,
                )
            else:
                blockers.append({
                    "job_id": job.job_id,
                    "reason": f"tentativa anterior encerrou em {prior['state']}",
                })
                continue

        while True:
            remaining_wall = mission.ratchet.max_wall_seconds - int(
                time.monotonic() - ratchet_started_at
            )
            ownership = _writer_ownership(active_mission)
            claim = store.claim(
                supervisor_id=queue.supervisor_id,
                job_id=job.job_id,
                task_id=job.task_id,
                roadmap_sha=roadmap_sha,
                contract_digest=contract_digest,
                base_sha=active_mission.base_ref,
                lineage_root_sha=active_mission.lineage_root_sha or mission.base_ref,
                attempt=active_mission.attempt,
                ownership=ownership,
                lease_seconds=queue.lease_seconds,
                max_writer_concurrency=queue.max_writer_concurrency,
            )
            if claim is None:
                blockers.append({
                    "job_id": job.job_id,
                    "reason": "já reivindicado, concluído ou ownership ocupado",
                })
                break

            key = claim["idempotency_key"]
            store.transition(
                key,
                "running",
                payload={
                    "mission_id": active_mission.mission_id,
                    "base_sha": active_mission.base_ref,
                    "attempt": active_mission.attempt,
                },
            )
            _write_snapshot(repo, queue, store, blockers)
            if active_mission.ratchet.enabled and remaining_wall < 60:
                store.transition(
                    key,
                    "blocked",
                    payload={"terminal_reason": "wall_budget_exhausted"},
                )
                _write_snapshot(repo, queue, store, blockers)
                return {
                    "status": "blocked",
                    "reason": "orçamento de tempo do Ratchet esgotado",
                    "job_id": job.job_id,
                    "attempt": active_mission.attempt,
                }
            mission_for_run = active_mission
            if active_mission.ratchet.enabled:
                mission_for_run = active_mission.model_copy(
                    update={
                        "timeout_seconds": min(
                            active_mission.timeout_seconds,
                            remaining_wall,
                        )
                    }
                )
            try:
                run_dir, result = _run_with_lease(
                    repo=repo,
                    mission=mission_for_run,
                    runner=runner,
                    store=store,
                    key=key,
                    owner_nonce=claim["owner_nonce"],
                    lease_seconds=queue.lease_seconds,
                )
            except Exception as error:
                failure = _value_fingerprint(
                    {"type": type(error).__name__, "message": str(error)}
                )
                store.transition(
                    key,
                    "failed",
                    failure_fingerprint=failure,
                    error=f"{type(error).__name__}: {error}",
                )
                _write_snapshot(repo, queue, store, blockers)
                return {"status": "failed", "job_id": job.job_id, "error": str(error)}

            candidate = result.get("writer_commit")
            finding = _finding_fingerprint(result)
            failure = None if result.get("ok") else _value_fingerprint(result)
            candidate_status = result.get("candidate_status")
            lineage_root = active_mission.lineage_root_sha or mission.base_ref
            candidate_valid = _candidate_is_valid(repo, candidate, lineage_root)
            correction_base = (
                str(candidate)
                if candidate_valid
                else active_mission.base_ref
                if not result.get("ok") and finding is not None
                else None
            )
            tree = _tree_fingerprint(repo, correction_base)
            if (
                not result.get("ok")
                and active_mission.ratchet.enabled
                and finding is not None
                and correction_base is not None
            ):
                terminal = "changes_requested"
            elif not result.get("ok"):
                terminal = "failed"
            elif candidate_status == "ready_for_human" and candidate_valid:
                terminal = "ready_for_human"
            elif (
                candidate_status == "changes_requested"
                and candidate_valid
                and finding is not None
            ):
                terminal = "changes_requested"
            elif candidate_status == "blocked":
                terminal = "blocked"
            else:
                terminal = "blocked"
            wall_exhausted = (
                active_mission.ratchet.enabled
                and time.monotonic() - ratchet_started_at
                >= mission.ratchet.max_wall_seconds
            )
            if wall_exhausted:
                terminal = "blocked"
            history = store.history(job.task_id, contract_digest)
            previous_tree_occurrences = sum(
                1
                for item in history
                if tree is not None and item.get("tree_fingerprint") == tree
            )
            previous_finding_occurrences = sum(
                1
                for item in history
                if finding is not None
                and item.get("finding_fingerprint") == finding
            )
            no_progress = (
                terminal == "changes_requested"
                and (
                    (
                        tree is not None
                        and previous_tree_occurrences
                        >= mission.ratchet.no_progress_limit - 1
                    )
                    or (
                        finding is not None
                        and previous_finding_occurrences
                        >= mission.ratchet.no_progress_limit - 1
                    )
                )
            )
            if no_progress:
                terminal = "blocked"
            store.transition(
                key,
                terminal,
                run_dir=str(run_dir),
                candidate_sha=candidate,
                resume_base_sha=correction_base,
                tree_fingerprint=tree,
                finding_fingerprint=finding,
                failure_fingerprint=failure,
                payload={
                    "candidate_status": candidate_status,
                    "execution_ok": bool(result.get("ok")),
                    "attempt": active_mission.attempt,
                    "terminal_reason": (
                        "wall_budget_exhausted"
                        if wall_exhausted
                        else "no_progress" if no_progress else None
                    ),
                },
            )
            _write_snapshot(repo, queue, store, blockers)

            if no_progress:
                return {
                    "status": "blocked",
                    "reason": "sem progresso: árvore repetida",
                    "job_id": job.job_id,
                    "attempt": active_mission.attempt,
                }

            if wall_exhausted:
                return {
                    "status": "blocked",
                    "reason": "orçamento de tempo do Ratchet esgotado",
                    "job_id": job.job_id,
                    "attempt": active_mission.attempt,
                }

            if (
                terminal == "changes_requested"
                and active_mission.ratchet.enabled
                and active_mission.attempt < attempt_limit
                and correction_base
            ):
                prior = store.latest(job.task_id, contract_digest)
                active_mission = _corrective_mission(
                    mission,
                    candidate_sha=correction_base,
                    root_base_sha=base_sha,
                    previous_run_id=Path(str(run_dir)).name,
                    previous_result=result,
                    attempt=active_mission.attempt + 1,
                )
                continue
            return {
                "status": terminal,
                "job_id": job.job_id,
                "task_id": job.task_id,
                "attempt": active_mission.attempt,
                "run_dir": str(run_dir),
                "candidate_sha": candidate,
            }

    _write_snapshot(repo, queue, store, blockers)
    return {"status": "idle", "blockers": blockers}


def _select_concurrent_jobs(
    *,
    repo: Path,
    queue: SupervisorQueueSpec,
    store: SupervisorStore,
) -> tuple[list[SupervisorJobSpec], list[dict[str, str]]]:
    """Seleciona uma onda determinística sem transformar ordem em dependência.

    O ledger continua sendo a autoridade final do claim. Esta seleção evita
    iniciar threads que já sabemos disputar o mesmo ownership e limita cada
    chamada de ``run_once`` a uma única onda de até quatro writers.
    """

    tasks, _roadmap_sha = _load_roadmap(repo / queue.roadmap_path)
    base_sha = _head(repo)
    selected: list[SupervisorJobSpec] = []
    ownership_by_job: dict[str, list[str]] = {}
    blockers: list[dict[str, str]] = []

    for job in sorted(queue.jobs, key=lambda item: (item.priority, item.job_id)):
        if not job.enabled:
            blockers.append({"job_id": job.job_id, "reason": "job desabilitado"})
            continue
        declared = Path(job.mission_path)
        mission_path = declared if declared.is_absolute() else repo / declared
        if not mission_path.is_file():
            blockers.append({
                "job_id": job.job_id,
                "reason": "manifesto da missão ausente",
            })
            continue
        try:
            bruto = json.loads(mission_path.read_text(encoding="utf-8"))
            # O supervisor despacha SOMENTE missão compilada. Antes ele tinha um
            # caminho próprio que ignorava o compilador V3 inteiro.
            assert_compilable(bruto)
            mission = MissionSpec.model_validate(bruto)
        except HarnessFailure as falha:
            blockers.append({
                "job_id": job.job_id,
                "reason": f"[{falha.classe.value}] {falha.resumo}",
                "detalhe": falha.detalhe,
                "como_migrar": falha.reproducao,
            })
            continue
        except Exception as error:
            blockers.append({
                "job_id": job.job_id,
                "reason": f"manifesto inválido: {type(error).__name__}",
            })
            continue

        task = tasks.get(job.task_id)
        contract_digest = (
            _contract_digest(mission, task, job)
            if isinstance(task, dict)
            else "missing-task"
        )
        prior = store.latest(job.task_id, contract_digest)
        expected_base = mission.base_ref if prior is not None else base_sha
        reason = eligibility_reason(
            repo=repo,
            job=job,
            tasks=tasks,
            mission=mission,
            base_sha=expected_base,
        )
        if reason:
            blockers.append({"job_id": job.job_id, "reason": reason})
            continue

        ownership = _writer_ownership(mission)
        conflicting_job = next(
            (
                selected_job.job_id
                for selected_job in selected
                if ownership_overlaps(
                    ownership, ownership_by_job[selected_job.job_id]
                )
            ),
            None,
        )
        if conflicting_job is not None:
            blockers.append({
                "job_id": job.job_id,
                "reason": f"ownership sobreposto com {conflicting_job}",
            })
            continue
        if len(selected) >= queue.max_writer_concurrency:
            blockers.append({
                "job_id": job.job_id,
                "reason": "aguardando próxima onda por limite de concorrência",
            })
            continue
        selected.append(job)
        ownership_by_job[job.job_id] = ownership

    return selected, blockers


def run_once(
    repo: Path,
    queue: SupervisorQueueSpec,
    *,
    store: SupervisorStore,
    runner: Runner = run_mission,
) -> dict[str, Any]:
    """Executa uma onda concorrente, sem integrar candidatos automaticamente."""

    repo = repo.resolve()
    if queue.max_writer_concurrency == 1:
        return _run_serial_once(repo, queue, store=store, runner=runner)

    selected, scheduling_blockers = _select_concurrent_jobs(
        repo=repo,
        queue=queue,
        store=store,
    )
    if not selected:
        _write_snapshot(repo, queue, store, scheduling_blockers)
        return {"status": "idle", "blockers": scheduling_blockers}

    results_by_job: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(selected),
        thread_name_prefix="volc-supervisor-writer",
    ) as executor:
        futures = {
            executor.submit(
                _run_serial_once,
                repo,
                queue.model_copy(update={"jobs": [job]}),
                store=store,
                runner=runner,
            ): job
            for job in selected
        }
        for future in concurrent.futures.as_completed(futures):
            job = futures[future]
            try:
                results_by_job[job.job_id] = future.result()
            except Exception as error:
                results_by_job[job.job_id] = {
                    "status": "failed",
                    "job_id": job.job_id,
                    "error": f"{type(error).__name__}: {error}",
                }

    results = [results_by_job[job.job_id] for job in selected]
    failed = any(result.get("status") == "failed" for result in results)
    _write_snapshot(repo, queue, store, scheduling_blockers)
    return {
        "status": "failed" if failed else "batch",
        "results": results,
        "blockers": scheduling_blockers,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int)
    args = parser.parse_args(argv)

    if args.watch:
        parser.error(
            "--watch permanece desarmado até cancelamento em voo e retomada "
            "pós-crash terem contraprovas"
        )

    repo = args.repo.resolve()
    queue = SupervisorQueueSpec.model_validate_json(
        args.queue.read_text(encoding="utf-8")
    )
    database = repo / "tools" / "agent-harness" / "runs" / "supervisor.sqlite"
    store = SupervisorStore(database)
    stopping = False

    def stop(_signal: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    interval = args.interval or queue.poll_seconds
    while True:
        result = run_once(repo, queue, store=store)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if not args.watch or stopping:
            return 0 if result["status"] not in {"failed"} else 2
        for _ in range(interval):
            if stopping:
                return 0
            time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
