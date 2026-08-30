"""Workflows ADK para investigação paralela e implementação isolada."""

from __future__ import annotations

import asyncio
import json
import secrets
import subprocess
from contextlib import aclosing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.adk.runners import InMemoryRunner
from google.adk.workflow import FunctionNode, JoinNode, START, Workflow
from google.genai import types

from .adapters import AdapterRequest, adapter_for
from .gates import project_venv_overlay, resolve_gate_argv
from .locking import writer_lock
from .models import MissionSpec, WorkerSpec
from .security import redact, sanitized_environment
from .worktrees import WorktreeInfo, WorktreeManager


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id(mission_id: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"{stamp}-{mission_id}-{secrets.token_hex(3)}"


def _source_linkage(mission: MissionSpec) -> dict[str, Any]:
    return {
        "task_ids": mission.task_ids,
        "inbox_ids": mission.inbox_ids,
        "parent_run_id": mission.parent_run_id,
        "attempt": mission.attempt,
    }


def _worker_prompt(
    mission: MissionSpec,
    worker: WorkerSpec,
    base_sha: str,
) -> str:
    paths = "\n".join(f"- {path}" for path in worker.allowed_paths)
    return f"""Você é um investigador read-only do desenvolvimento VOLC.

MISSÃO
{mission.title}

BASE IMUTÁVEL
Commit: {base_sha}
Esta worktree não contém mudanças não commitadas da árvore principal.

BRIEFING
{mission.briefing}

SUA LENTE
{worker.lens}

ESCOPO DE LEITURA PRIORITÁRIO
{paths}

REGRAS OBRIGATÓRIAS
- Não edite, crie, remova ou formate arquivo algum.
- Não faça chamadas de rede e não leia arquivos .env ou credenciais.
- Diferencie fato observado, inferência, risco e limitação.
- Cite caminhos e símbolos concretos na evidência.
- Faça buscas progressivas e específicas. Nunca varra o repositório inteiro com
  uma expressão ampla quando os caminhos prioritários já estão listados.
- Toda listagem ou busca de shell deve limitar a saída a no máximo 200 linhas.
  Se a consulta ainda for grande, refine-a em vez de despejar mais resultados.
- Leia arquivos longos em fatias de no máximo 250 linhas, somente nos trechos
  relevantes. Execute uma ferramenta por vez; não dispare leituras paralelas.
- Não leia dependências, caches, ambientes virtuais, arquivos gerados ou
  snapshots grandes salvo quando a missão os nomear explicitamente.
- Não atualize Roadmap, curadoria ou grafo.
- Responda somente no JSON exigido pelo schema fornecido pela CLI.
"""


def _writer_prompt(
    mission: MissionSpec,
    worker: WorkerSpec,
    base_sha: str,
) -> str:
    paths = "\n".join(f"- {path}" for path in worker.allowed_paths)
    return f"""Você é o único escritor autorizado desta rodada do VOLC OS.

MISSÃO
{mission.title}

BASE IMUTÁVEL
Commit: {base_sha}
Você está numa branch e worktree exclusivas, criadas a partir deste commit.

BRIEFING
{mission.briefing}

SUA RESPONSABILIDADE
{worker.lens}

OWNERSHIP DE ESCRITA — NÃO ULTRAPASSE
{paths}

REGRAS OBRIGATÓRIAS
- Implemente uma única fatia vertical coerente e utilizável; não crie um sistema
  paralelo ao que já existe.
- Leia primeiro AGENTS.md, CLAUDE.md, a curadoria operacional e o grafo atual.
- Reuse contratos, identidades, portas, componentes, migrations e testes já
  existentes sempre que forem autoridades válidas.
- Pode ler outros caminhos para entender dependências, mas só pode editar os
  caminhos de ownership listados acima.
- Não leia .env, credenciais, tokens ou arquivos de configuração local.
- Não use rede, não faça push, merge, deploy, rotação ou chamada externa.
- Não aplique migrations no Supabase oficial e não faça mutate/validate_only no
  Google Ads. A trava de escrita permanece fechada.
- Não edite Roadmap Vivo, curadoria humana, saídas do grafo ou documentação
  gerada. Isso pertence ao curador após integração.
- Preencha obrigatoriamente `curation_handoff` no resultado: IDs das tarefas,
  nós do grafo, estado proposto, provas e lacunas. `done` só é válido quando os
  critérios de aceite foram demonstrados; branch isolada normalmente permanece
  `partial` até integração e curadoria.
- Ausência é ausência: nunca transforme dado ausente em zero, sucesso, vazio ou
  autorização.
- Frontend não chama Google Ads, não carrega segredo e não recalcula decisão
  cuja autoridade pertence ao backend.
- Toda futura ação mutável deve nascer como proposta tipada, idempotente,
  auditável e dependente de aprovação explícita; nesta rodada, não a execute.
- Rode testes proporcionais ao que mudou. Não esconda falha preexistente nem
  reclassifique falha nova como baseline.
- Não faça git add ou git commit. O harness valida ownership, segredos e diff e
  cria o commit isolado depois que você terminar.
- Responda somente no JSON exigido pelo schema fornecido pela CLI.
"""


def _reviewer_prompt(
    mission: MissionSpec,
    worker: WorkerSpec,
    writer_sha: str,
    changed_paths: list[str],
) -> str:
    paths = "\n".join(f"- {path}" for path in worker.allowed_paths)
    changed = "\n".join(f"- {path}" for path in changed_paths)
    network_rule = (
        "- Se precisar validar documentação instável, consulte somente fontes "
        "oficiais em developers.google.com. Não acesse outros domínios."
        if worker.network_access
        else "- Não faça chamadas externas nem use rede."
    )
    return f"""Você é um revisor adversarial read-only do VOLC OS.

MISSÃO ORIGINAL
{mission.title}

COMMIT DO ESCRITOR A REVISAR
{writer_sha}

BRIEFING
{mission.briefing}

SUA LENTE
{worker.lens}

ARQUIVOS ALTERADOS PELO ESCRITOR
{changed}

ESCOPO PRIORITÁRIO PARA CONFERÊNCIA
{paths}

REGRAS OBRIGATÓRIAS
- Não edite, crie, remova ou formate arquivo algum.
- Inspecione o diff e execute somente provas read-only/localmente seguras.
- Tente refutar a entrega com evidência concreta, inclusive integração com
  contratos existentes, autoridade do Supabase, Google Ads API, frontend,
  idempotência, ausência, autenticação e segurança.
- Google Recommendations e IA são sinais, nunca autoridade de mutação.
{network_rule}
- Não leia .env e não atualize Roadmap ou grafo.
- Diferencie fato, inferência, risco e limitação.
- Responda somente no JSON exigido pelo schema fornecido pela CLI.
"""


def _worker_node(
    mission: MissionSpec,
    worker: WorkerSpec,
    worktree: WorktreeInfo,
    schema_path: Path,
    run_dir: Path,
    *,
    prompt: str | None = None,
    mode: str = "read_only",
) -> FunctionNode:
    async def execute_worker() -> dict[str, Any]:
        started_at = _utc_now()
        worker_dir = run_dir / "workers" / worker.id
        request = AdapterRequest(
            worker_id=worker.id,
            worktree=worktree.path,
            prompt=prompt or _worker_prompt(mission, worker, worktree.base_sha),
            schema_path=schema_path,
            run_dir=worker_dir,
            timeout_seconds=mission.timeout_seconds,
            heartbeat_seconds=mission.heartbeat_seconds,
            mode=mode,
            model=worker.model,
            effort=worker.effort,
            network_access=worker.network_access,
            allowed_paths=tuple(worker.allowed_paths),
            writable_paths=tuple(worker.effective_writable_paths),
        )
        try:
            result = await adapter_for(worker.provider).run(request)
            return {
                "worker_id": worker.id,
                "provider": worker.provider,
                "role": worker.role,
                "model": worker.model,
                "effort": worker.effort,
                "ok": True,
                "started_at": started_at,
                "finished_at": _utc_now(),
                "result": result,
            }
        except Exception as error:  # resultado de worker, não falha do coordenador
            return {
                "worker_id": worker.id,
                "provider": worker.provider,
                "role": worker.role,
                "model": worker.model,
                "effort": worker.effort,
                "ok": False,
                "started_at": started_at,
                "finished_at": _utc_now(),
                "error": f"{type(error).__name__}: {error}",
            }

    # IDs de tarefa usam hífen para legibilidade, mas o ADK exige que nomes de
    # nós sejam identificadores Python válidos.
    node_name = worker.id.replace("-", "_")
    return FunctionNode(
        func=execute_worker,
        name=node_name,
        timeout=mission.timeout_seconds + 30,
    )


async def _run_read_only_mission(
    repo: Path, mission: MissionSpec
) -> tuple[Path, dict[str, Any]]:
    manager = WorktreeManager(repo)
    base_sha = manager.resolve_base(mission.base_ref)
    run_id = _run_id(mission.mission_id)
    run_dir = repo / "tools" / "agent-harness" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    metadata = {
        "run_id": run_id,
        "mission_id": mission.mission_id,
        "title": mission.title,
        "base_sha": base_sha,
        "started_at": _utc_now(),
        "mode": "read_only",
        **_source_linkage(mission),
        "workers": [
            {
                "id": worker.id,
                "provider": worker.provider,
                "role": worker.role,
                "model": worker.model,
                "effort": worker.effort,
            }
            for worker in mission.workers
        ],
    }
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    worktrees = {
        worker.id: manager.create(run_id, worker.id, base_sha)
        for worker in mission.workers
    }
    schema_path = Path(__file__).parent / "schemas" / "worker-result.schema.json"
    worker_nodes = tuple(
        _worker_node(
            mission,
            worker,
            worktrees[worker.id],
            schema_path,
            run_dir,
        )
        for worker in mission.workers
    )
    join = JoinNode(name="join_workers")
    aggregate_result: dict[str, Any] = {}

    async def aggregate(node_input: dict[str, Any]) -> dict[str, Any]:
        nonlocal aggregate_result
        workers = [node_input[key] for key in sorted(node_input)]
        aggregate_result = {
            **metadata,
            "finished_at": _utc_now(),
            "ok": all(worker.get("ok") for worker in workers),
            "workers": workers,
            "worktrees": {
                worker_id: {
                    "path": str(info.path),
                    "branch": info.branch,
                    "base_sha": info.base_sha,
                }
                for worker_id, info in worktrees.items()
            },
        }
        (run_dir / "mission-result.json").write_text(
            json.dumps(aggregate_result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return aggregate_result

    aggregate_node = FunctionNode(func=aggregate, name="aggregate")
    workflow = Workflow(
        name="volc_parallel_mission",
        edges=[(START, worker_nodes, join, aggregate_node)],
        max_concurrency=len(worker_nodes),
    )
    runner = InMemoryRunner(node=workflow, app_name="volc_agent_harness")
    session_id = run_id.replace("_", "-")
    await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id="volc-local",
        session_id=session_id,
    )
    message = types.Content(
        role="user", parts=[types.Part(text=f"execute {mission.mission_id}")]
    )
    try:
        async with aclosing(
            runner.run_async(
                user_id="volc-local",
                session_id=session_id,
                new_message=message,
            )
        ) as stream:
            async for _event in stream:
                pass
    finally:
        await runner.close()

    for worktree in worktrees.values():
        manager.assert_clean(worktree.path)
    if not aggregate_result:
        raise RuntimeError("workflow terminou sem agregação")
    return run_dir, aggregate_result


async def _run_implementation_mission(
    repo: Path, mission: MissionSpec
) -> tuple[Path, dict[str, Any]]:
    manager = WorktreeManager(repo)
    base_sha = manager.resolve_implementation_base(
        mission.base_ref, mission.lineage_root_sha
    )
    run_id = _run_id(mission.mission_id)
    run_dir = repo / "tools" / "agent-harness" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    writer = next(worker for worker in mission.workers if worker.role == "writer")
    reviewers = [worker for worker in mission.workers if worker.role == "reviewer"]
    metadata = {
        "run_id": run_id,
        "mission_id": mission.mission_id,
        "title": mission.title,
        "base_sha": base_sha,
        "started_at": _utc_now(),
        "mode": "implementation",
        **_source_linkage(mission),
        "workers": [
            {
                "id": worker.id,
                "provider": worker.provider,
                "role": worker.role,
                "model": worker.model,
                "effort": worker.effort,
            }
            for worker in mission.workers
        ],
    }
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    writer_worktree = manager.create(run_id, writer.id, base_sha)
    writer_schema = (
        Path(__file__).parent / "schemas" / "writer-result.schema.json"
    )
    writer_request = AdapterRequest(
        worker_id=writer.id,
        worktree=writer_worktree.path,
        prompt=_writer_prompt(mission, writer, base_sha),
        schema_path=writer_schema,
        run_dir=run_dir / "workers" / writer.id,
        timeout_seconds=mission.timeout_seconds,
        heartbeat_seconds=mission.heartbeat_seconds,
        mode="workspace_write",
        model=writer.model,
        effort=writer.effort,
        network_access=False,
        allowed_paths=tuple(writer.allowed_paths),
        writable_paths=tuple(writer.effective_writable_paths),
    )
    writer_started = _utc_now()
    try:
        writer_result = await adapter_for(writer.provider).run(writer_request)
        manager.assert_head_unchanged(writer_worktree.path, base_sha)
        changed_paths = manager.assert_only_allowed(
            writer_worktree.path, writer.effective_writable_paths
        )
        gate_results = []
        with project_venv_overlay(repo=repo, worktree=writer_worktree.path):
            for index, gate in enumerate(mission.gates, start=1):
                resolved_gate = resolve_gate_argv(
                    gate.argv,
                    repo=repo,
                    worktree=writer_worktree.path,
                )
                completed = subprocess.run(
                    resolved_gate.argv,
                    cwd=writer_worktree.path,
                    env=sanitized_environment(),
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=gate.timeout_seconds,
                )
                gate_record = {
                    "index": index,
                    "argv": gate.argv,
                    "resolved_executable": resolved_gate.resolved_executable,
                    "returncode": completed.returncode,
                    "stdout": redact(completed.stdout[-20_000:]),
                    "stderr": redact(completed.stderr[-20_000:]),
                }
                gate_results.append(gate_record)
                (run_dir / f"gate-{index}.json").write_text(
                    json.dumps(gate_record, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                if completed.returncode != 0:
                    raise RuntimeError(
                        f"gate {index} falhou com exit={completed.returncode}"
                    )
        manager.assert_head_unchanged(writer_worktree.path, base_sha)
        changed_paths_after_gates = manager.assert_only_allowed(
            writer_worktree.path, writer.effective_writable_paths
        )
        if changed_paths_after_gates != changed_paths:
            raise RuntimeError(
                "os gates alteraram a árvore; artefatos de teste não podem entrar no commit"
            )
        writer_sha = manager.commit_writer(
            writer_worktree.path,
            mission.commit_message or mission.title,
            changed_paths,
        )
        manager.assert_clean(writer_worktree.path)
        writer_record: dict[str, Any] = {
            "worker_id": writer.id,
            "provider": writer.provider,
            "role": writer.role,
            "model": writer.model,
            "effort": writer.effort,
            "ok": True,
            "started_at": writer_started,
            "finished_at": _utc_now(),
            "commit": writer_sha,
            "changed_paths": changed_paths,
            "gates": gate_results,
            "result": writer_result,
        }
    except Exception as error:
        writer_record = {
            "worker_id": writer.id,
            "provider": writer.provider,
            "role": writer.role,
            "model": writer.model,
            "effort": writer.effort,
            "ok": False,
            "started_at": writer_started,
            "finished_at": _utc_now(),
            "error": f"{type(error).__name__}: {error}",
        }
        result = {
            **metadata,
            "finished_at": _utc_now(),
            "ok": False,
            "workers": [writer_record],
            "worktrees": {
                writer.id: {
                    "path": str(writer_worktree.path),
                    "branch": writer_worktree.branch,
                    "base_sha": writer_worktree.base_sha,
                }
            },
        }
        (run_dir / "mission-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return run_dir, result

    reviewer_worktrees = {
        reviewer.id: manager.create(run_id, reviewer.id, writer_sha)
        for reviewer in reviewers
    }
    review_schema = Path(__file__).parent / "schemas" / "review-result.schema.json"
    reviewer_nodes = tuple(
        _worker_node(
            mission,
            reviewer,
            reviewer_worktrees[reviewer.id],
            review_schema,
            run_dir,
            prompt=_reviewer_prompt(
                mission, reviewer, writer_sha, changed_paths
            ),
        )
        for reviewer in reviewers
    )
    join = JoinNode(name="join_reviewers")
    aggregate_result: dict[str, Any] = {}

    async def aggregate_reviews(node_input: dict[str, Any]) -> dict[str, Any]:
        nonlocal aggregate_result
        review_records = [node_input[key] for key in sorted(node_input)]
        all_records = [writer_record, *review_records]
        all_worktrees = {writer.id: writer_worktree, **reviewer_worktrees}
        verdicts = [
            record.get("result", {}).get("verdict")
            for record in review_records
            if record.get("ok")
        ]
        severe_findings = [
            finding
            for record in review_records
            if record.get("ok")
            for finding in record.get("result", {}).get("confirmed_findings", [])
            if finding.get("severity") in {"critical", "high"}
        ]
        if any(not record.get("ok") for record in review_records) or "blocked" in verdicts:
            candidate_status = "blocked"
        elif "changes_requested" in verdicts or severe_findings:
            candidate_status = "changes_requested"
        else:
            candidate_status = "ready_for_human"
        aggregate_result = {
            **metadata,
            "finished_at": _utc_now(),
            "ok": all(record.get("ok") for record in all_records),
            "writer_commit": writer_sha,
            "candidate_status": candidate_status,
            "changed_paths": changed_paths,
            "governance_status": "pending_single_curator",
            "curation_handoff": writer_result.get("curation_handoff"),
            "workers": all_records,
            "worktrees": {
                worker_id: {
                    "path": str(info.path),
                    "branch": info.branch,
                    "base_sha": info.base_sha,
                }
                for worker_id, info in all_worktrees.items()
            },
        }
        (run_dir / "mission-result.json").write_text(
            json.dumps(aggregate_result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return aggregate_result

    aggregate_node = FunctionNode(func=aggregate_reviews, name="aggregate_reviews")
    workflow = Workflow(
        name="volc_implementation_review",
        edges=[(START, reviewer_nodes, join, aggregate_node)],
        max_concurrency=len(reviewer_nodes),
    )
    runner = InMemoryRunner(node=workflow, app_name="volc_agent_harness")
    session_id = f"{run_id}-review".replace("_", "-")
    await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id="volc-local",
        session_id=session_id,
    )
    message = types.Content(
        role="user", parts=[types.Part(text=f"review {mission.mission_id}")]
    )
    try:
        async with aclosing(
            runner.run_async(
                user_id="volc-local",
                session_id=session_id,
                new_message=message,
            )
        ) as stream:
            async for _event in stream:
                pass
    finally:
        await runner.close()

    for worktree in reviewer_worktrees.values():
        manager.assert_clean(worktree.path)
    if not aggregate_result:
        raise RuntimeError("workflow de revisão terminou sem agregação")
    return run_dir, aggregate_result


async def run_mission(repo: Path, mission: MissionSpec) -> tuple[Path, dict[str, Any]]:
    if mission.mode == "implementation":
        return await _run_implementation_mission(repo, mission)
    return await _run_read_only_mission(repo, mission)


def run(repo: Path, mission: MissionSpec) -> tuple[Path, dict[str, Any]]:
    resolved = repo.resolve()
    if mission.mode == "implementation":
        with writer_lock(resolved, mission.mission_id):
            return asyncio.run(run_mission(resolved, mission))
    return asyncio.run(run_mission(resolved, mission))
