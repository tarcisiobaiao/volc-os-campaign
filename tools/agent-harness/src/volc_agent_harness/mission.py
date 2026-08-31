"""Workflows ADK para investigação paralela e implementação isolada."""

from __future__ import annotations

import contextlib

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
from .gates import (
    project_node_modules_overlay,
    project_venv_overlay,
    resolve_gate_argv,
)
from .locking import writer_lock
from .models import MissionSpec, WorkerSpec
from .security import redact, sanitized_environment
from .v3.failures import FailureClass, HarnessFailure, classify_gate_exit
from .v3.gate_compiler import ProducedPath, assert_pytest_collects, compile_gate_plan
from .v3.two_phase import postwriter_compile
from .v3.workspace import (
    assert_gate_executable_is_allowed,
    assert_no_destructive_intent,
)
from .worktrees import WorktreeInfo, WorktreeManager


def _registry_do_repo(repo: Path):
    """Registry compartilhado. Toda worktree nasce com claim transacional."""

    from .v3.registry import WorktreeRegistry

    return WorktreeRegistry(
        repo / "tools" / "agent-harness" / "worktree-registry.sqlite"
    )


def _ambiente_de_gate() -> dict[str, str]:
    """Ambiente dos gates, sem bytecode.

    Sem isto, o pytest deixa ``__pycache__`` na worktree e a guarda que impede
    artefato de teste de entrar no commit dispara — corretamente, mas por um
    motivo que não é do candidato. Toda missão batia nisso.
    """

    env = sanitized_environment()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


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
            microrepair=(
                worker.microrepair.model_dump(mode="json")
                if worker.microrepair is not None
                else None
            ),
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
                "error": redact(f"{type(error).__name__}: {error}"),
            }

    # IDs de tarefa usam hífen para legibilidade, mas o ADK exige que nomes de
    # nós sejam identificadores Python válidos.
    node_name = worker.id.replace("-", "_")
    return FunctionNode(
        func=execute_worker,
        name=node_name,
        timeout=mission.timeout_seconds + 30,
    )


def _compilar_missao(
    *,
    mission: MissionSpec,
    tree: Path,
    base_sha: str,
    run_dir: Path,
    writable_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Compilação obrigatória, comum a read_only e implementation.

    Nenhum adapter — investigador, reviewer ou writer — roda antes disto. Antes,
    só o caminho de implementação compilava, e "o writer está protegido" virava
    autoridade única do runtime.
    """

    for gate in mission.gates:
        assert_gate_executable_is_allowed(gate.argv)
        assert_no_destructive_intent(gate.argv)

    produced = [ProducedPath(p.path, p.required) for p in mission.produced_paths]
    gate_plan = compile_gate_plan(gates=mission.gates, tree=tree, produced=produced)
    (run_dir / "gate-plan.json").write_text(
        json.dumps(gate_plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    proposta: dict[str, Any] | None = None
    if mission.mission_schema_version >= 3:
        from .v3.ownership import build_proposal

        proposta = build_proposal(
            tree=tree,
            acceptance_ids=mission.acceptance_ids,
            symbols=mission.ownership_symbols,
            search_roots=mission.ownership_search_roots or mission.ownership_envelope,
            envelope=mission.ownership_envelope,
            declared_writable=writable_paths or [],
            produced_paths=[p.model_dump() for p in mission.produced_paths],
        )
        (run_dir / "ownership-proposal.json").write_text(
            json.dumps(proposta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if writable_paths is not None and proposta["requires_new_authorization"]:
            raise HarnessFailure(
                FailureClass.OWNERSHIP_ERROR,
                "call site material fora do envelope autorizado",
                detalhe=", ".join(proposta["outside_envelope"][:6]),
                reproducao="revise ownership_envelope ou reduza o escopo do aceite",
            )

    # `allowed_paths` efetivos: read_only precisa saber o que cada worker lê.
    leitura_efetiva = sorted({
        caminho for worker in mission.workers for caminho in worker.allowed_paths
    })
    compilada = {
        "mission_id": mission.mission_id,
        "mission_schema_version": mission.mission_schema_version,
        "mode": mission.mode,
        "base_sha": base_sha,
        "lineage_root": mission.lineage_root_sha,
        "acceptance_ids": mission.acceptance_ids,
        "ownership_envelope": mission.ownership_envelope,
        "read_paths": leitura_efetiva,
        "writable_paths": writable_paths or [],
        "suggested_writable_paths": (proposta or {}).get("suggested_writable_paths", []),
        "produced_paths": [p.model_dump() for p in mission.produced_paths],
        "gate_plan": gate_plan,
        "gates_runnable_before_writer": gate_plan["runnable_before_writer"],
        "gates_depending_on_produced": gate_plan["depends_on_produced"],
        "routed_models": {w.id: f"{w.provider}/{w.model}" for w in mission.workers},
        "privacy_class": "local_code_only",
        "write_authority": "single_writer" if writable_paths else "read_only",
        "integration_policy": "human_merge_only",
    }
    (run_dir / "compiled-mission.json").write_text(
        json.dumps(compilada, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return compilada


def _registrar_evidencia(run_dir: Path, entradas: list[dict[str, Any]]) -> None:
    (run_dir / "evidence.json").write_text(
        json.dumps(entradas, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _registrar_falha(run_dir: Path, exc: BaseException) -> dict[str, Any]:
    from .v3.failures import classify_exception

    if isinstance(exc, HarnessFailure):
        registro = exc.as_dict()
    else:
        registro = HarnessFailure(classify_exception(exc), str(exc)[:300]).as_dict()
    (run_dir / "failure.json").write_text(
        json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return registro


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

    # Compilação obrigatória também no read_only. Investigadores e reviewers
    # gastam modelo igual; não há razão para eles escaparem do compilador.
    try:
        _compilar_missao(
            mission=mission, tree=repo, base_sha=base_sha, run_dir=run_dir,
        )
    except BaseException as exc:
        _registrar_falha(run_dir, exc)
        raise

    worktrees = {
        worker.id: manager.create(run_id, worker.id, base_sha, registry=_registry_do_repo(repo), mission_id=mission.mission_id)
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

    writer_worktree = manager.create(run_id, writer.id, base_sha, registry=_registry_do_repo(repo), mission_id=mission.mission_id)
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
        microrepair=(
            writer.microrepair.model_dump(mode="json")
            if writer.microrepair is not None
            else None
        ),
    )
    # ------------------------------------------------------------------
    # FASE 1 DO PIPELINE V3 — antes de qualquer chamada de modelo.
    #
    # Foi aqui que faltou a proteção: o writer era chamado e só depois os gates
    # rodavam, virando RuntimeError genérico. Um gate que cita arquivo
    # inexistente agora recusa a missão em milissegundos, com classe tipada.
    # ------------------------------------------------------------------
    # Toda falha da fase pré-writer também vira failure.json. Antes, um baseline
    # vermelho ou um gate inválido escapava sem artefato, e o operador ficava com
    # traceback em vez de classe tipada.
    try:
        compilada = _compilar_missao(
            mission=mission,
            tree=writer_worktree.path,
            base_sha=base_sha,
            run_dir=run_dir,
            writable_paths=list(writer.effective_writable_paths),
        )
        produced = [ProducedPath(p.path, p.required) for p in mission.produced_paths]

        # BASELINE antes do writer: gate que já era vermelho no base não pode ser
        # cobrado do candidato, e comportamento já provado tem precedência.
        from .v3.baseline import assert_baseline_is_green, measure

        baseline_records = []
        # O overlay de node só entra se algum gate for de frontend. Exigir lockfile
        # numa missão puramente Python transformava infraestrutura ausente em erro
        # de missão.
        precisa_node = any(
            g["kind"] in {"vitest", "tsc", "vite"}
            for g in compilada["gate_plan"]["gates"]
        )
        node_ctx = (
            project_node_modules_overlay(worktree=writer_worktree.path)
            if precisa_node else contextlib.nullcontext()
        )
        with project_venv_overlay(repo=repo, worktree=writer_worktree.path), node_ctx:
            for compilado in compilada["gate_plan"]["gates"]:
                if compilado["index"] not in compilada["gates_runnable_before_writer"]:
                    continue
                resolvido = resolve_gate_argv(
                    compilado["argv"], repo=repo, worktree=writer_worktree.path
                )
                baseline_records.append(measure(
                    gate_index=compilado["index"],
                    argv=resolvido.argv,
                    tree=writer_worktree.path,
                    timeout=compilado["timeout_seconds"],
                    env=_ambiente_de_gate(),
                ))
        (run_dir / "baseline.json").write_text(
            json.dumps([r.as_dict() for r in baseline_records], ensure_ascii=False,
                       indent=2),
            encoding="utf-8",
        )
        assert_baseline_is_green(baseline_records)

        for compilado in compilada["gate_plan"]["gates"]:
            if compilado["kind"] == "pytest" and compilado["runnable_before_writer"]:
                from .v3.gate_compiler import CompiledGate

                assert_pytest_collects(
                    CompiledGate(**{
                        k: v for k, v in compilado.items()
                        if k in CompiledGate.__dataclass_fields__
                    }),
                    tree=writer_worktree.path,
                    env=_ambiente_de_gate(),
                )
    except BaseException as exc:
        _registrar_falha(run_dir, exc)
        raise

    writer_started = _utc_now()
    try:
        writer_result = await adapter_for(writer.provider).run(writer_request)
        manager.assert_head_unchanged(writer_worktree.path, base_sha)
        changed_paths = manager.assert_only_allowed(
            writer_worktree.path, writer.effective_writable_paths
        )
        # --------------------------------------------------------------
        # FASE 2 DO PIPELINE V3 — depois do writer, ANTES de qualquer gate.
        #
        # `changed_paths` vem do diff real da worktree, não de declaração. Se um
        # produced obrigatório não nasceu, ou se o writer escreveu fora do
        # ownership, isso é SPEC_ERROR/OWNERSHIP_ERROR agora — não um gate caro
        # falhando de um jeito difícil de ler dez minutos depois.
        # --------------------------------------------------------------
        postwriter = postwriter_compile(
            tree=writer_worktree.path,
            produced=produced,
            changed_paths=changed_paths,
            writable_paths=writer.effective_writable_paths,
            gates=mission.gates,
            env=_ambiente_de_gate(),
            collect=True,
        )
        (run_dir / "postwriter-report.json").write_text(
            json.dumps(postwriter.as_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        gate_results = []
        gate_overlay_provenance: dict[str, object] | None = None
        gates_node = any(
            g["kind"] in {"vitest", "tsc", "vite"}
            for g in compilada["gate_plan"]["gates"]
        )
        node_ctx_gates = (
            project_node_modules_overlay(worktree=writer_worktree.path)
            if gates_node else contextlib.nullcontext()
        )
        with project_venv_overlay(repo=repo, worktree=writer_worktree.path), \
                node_ctx_gates as node_overlay:
            if node_overlay is not None:
                gate_overlay_provenance = node_overlay
            for index, gate in enumerate(mission.gates, start=1):
                resolved_gate = resolve_gate_argv(
                    gate.argv,
                    repo=repo,
                    worktree=writer_worktree.path,
                )
                completed = subprocess.run(
                    resolved_gate.argv,
                    cwd=writer_worktree.path,
                    env=_ambiente_de_gate(),
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
                    classe = classify_gate_exit(
                        exit_code=completed.returncode,
                        argv=resolved_gate.argv,
                        stdout=completed.stdout,
                        stderr=completed.stderr,
                    )
                    raise HarnessFailure(
                        classe,
                        f"gate {index} falhou com exit={completed.returncode}",
                        detalhe=(completed.stderr or completed.stdout).strip()[-300:],
                        reproducao=" ".join(resolved_gate.argv),
                        evidencia={"gate_index": index, "exit": completed.returncode},
                    )
        manager.assert_head_unchanged(writer_worktree.path, base_sha)
        changed_paths_after_gates = manager.assert_only_allowed(
            writer_worktree.path, writer.effective_writable_paths
        )
        if changed_paths_after_gates != changed_paths:
            novos = sorted(set(changed_paths_after_gates) - set(changed_paths))
            sumidos = sorted(set(changed_paths) - set(changed_paths_after_gates))
            raise HarnessFailure(
                FailureClass.INFRASTRUCTURE_ERROR,
                "os gates alteraram a árvore; artefatos de teste não podem entrar no commit",
                detalhe=f"surgiram: {novos or '—'} | sumiram: {sumidos or '—'}",
                reproducao="acrescente -p no:cacheprovider e PYTHONDONTWRITEBYTECODE=1 ao gate",
            )
        # Ledger REAL: grava e consulta pelo caminho de produção, com o
        # contexto material completo. Antes, ledger.record só existia em
        # pipeline.py sem ctx_digest, e lookup só em teste.
        from .v3.ledger import EvidenceLedger, context_digest, digest_files, env_fingerprint

        ledger = EvidenceLedger(
            repo / "tools" / "agent-harness" / "evidence-ledger.sqlite"
        )
        prod_digest = digest_files(writer_worktree.path, changed_paths)
        ctx = context_digest(
            acceptance_text="|".join(mission.acceptance_ids),
            base_sha=base_sha,
            candidate_sha=None,
            lineage_root=mission.lineage_root_sha,
            toolchain={"harness": "v3"},
            manifests={},
        )
        fp = env_fingerprint(_ambiente_de_gate())
        entradas_evidencia = []
        for g in gate_results:
            comando = " ".join(g["argv"])
            consulta = ledger.lookup(
                acceptance_id=(mission.acceptance_ids or ["sem-aceite"])[0],
                kind=f"gate_{g['index']}", command=comando,
                production_digest=prod_digest, test_digest=prod_digest,
                cwd=str(writer_worktree.path), env_fp=fp, ctx_digest=ctx,
            )
            ledger.record(
                acceptance_id=(mission.acceptance_ids or ["sem-aceite"])[0],
                kind=f"gate_{g['index']}", base_sha=base_sha,
                run_id=run_id, command=comando, cwd=str(writer_worktree.path),
                env_fp=fp, ctx_digest=ctx, production_digest=prod_digest,
                test_digest=prod_digest, exit_code=g["returncode"],
                counts={"returncode": g["returncode"]},
            )
            entradas_evidencia.append({
                "acceptance_ids": mission.acceptance_ids,
                "kind": f"gate_{g['index']}",
                "command": comando,
                "exit_code": g["returncode"],
                "base_sha": base_sha,
                "context_digest": ctx,
                "env_fingerprint": fp,
                "status": consulta["status"],
                "status_reason": consulta["reason"],
            })
        _registrar_evidencia(run_dir, entradas_evidencia)
        writer_sha = manager.commit_writer(
            writer_worktree.path,
            mission.commit_message or mission.title,
            changed_paths,
        )
        manager.assert_clean(writer_worktree.path)
        (run_dir / "harvest.json").write_text(
            json.dumps({
                "sha": writer_sha,
                "branch": writer_worktree.branch,
                "files": changed_paths,
                "ownership_respected": True,
                "green_gates": [g["index"] for g in gate_results
                                if g["returncode"] == 0],
                "red_gate": None,
                "failure_class": "",
                "findings": [],
                "next_minimal_step": "revisão adversarial",
                "supersedes": [],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
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
        # failure.json tipado, e NENHUM harvest falso: colheita só nasce de
        # trabalho realmente commitado.
        _registrar_falha(run_dir, error)
        writer_record = {
            "worker_id": writer.id,
            "provider": writer.provider,
            "role": writer.role,
            "model": writer.model,
            "effort": writer.effort,
            "ok": False,
            "started_at": writer_started,
            "finished_at": _utc_now(),
            "error": redact(f"{type(error).__name__}: {error}"),
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
        reviewer.id: manager.create(run_id, reviewer.id, writer_sha,
                           registry=_registry_do_repo(repo),
                           mission_id=mission.mission_id)
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
        # Adjudicação V3: contraprova executável vence checklist. A força vem
        # da presença de reprodução e de findings confirmados, não do provider.
        from .v3.adjudication import Forca, Parecer, adjudicar

        pareceres = []
        for record in review_records:
            resultado = record.get("result", {}) or {}
            veredito = resultado.get("verdict") or (
                "accept" if record.get("ok") else "blocked"
            )
            achados = resultado.get("confirmed_findings", []) or []
            tem_reproducao = any(
                f.get("evidence") or f.get("reproduction") for f in achados
            )
            if tem_reproducao:
                forca = Forca.CONTRAPROVA_EXECUTAVEL
            elif achados:
                forca = Forca.EVIDENCIA_FILE_LINE
            elif record.get("ok"):
                forca = Forca.REVISAO_SEM_EXECUCAO
            else:
                forca = Forca.CHECKLIST
            pareceres.append(Parecer(
                reviewer=record.get("worker_id", "?"),
                provider=record.get("provider", "?"),
                veredito=veredito if veredito in {"accept", "changes_requested", "blocked"}
                else "changes_requested",
                forca=forca,
                resumo=str(resultado.get("summary", ""))[:200],
                reproducao=str((achados[0].get("evidence") if achados else "") or "")[:200],
            ))
        adjudicacao = adjudicar(pareceres) if pareceres else {
            "veredito": "BLOQUEADO", "motivo": "nenhum parecer", "pareceres": []
        }
        (run_dir / "adjudication.json").write_text(
            json.dumps(adjudicacao, ensure_ascii=False, indent=2), encoding="utf-8"
        )

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
            "adjudication": adjudicacao,
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


def _exigir_missao_compilavel(mission: MissionSpec) -> None:
    """Pré-condição única. Nenhum adapter é alcançável sem isto.

    O revisor provou que `run_mission` despachava direto: read_only nunca
    compilava, e o writer só tinha o preflight local de gates. Agora a guarda
    está no ponto por onde TODOS os modos passam.
    """

    from .v3.schema_version import assert_compilable

    assert_compilable(mission.model_dump(mode="json"))


async def run_mission(repo: Path, mission: MissionSpec) -> tuple[Path, dict[str, Any]]:
    _exigir_missao_compilavel(mission)
    if mission.mode == "implementation":
        return await _run_implementation_mission(repo, mission)
    return await _run_read_only_mission(repo, mission)


def run(repo: Path, mission: MissionSpec) -> tuple[Path, dict[str, Any]]:
    resolved = repo.resolve()
    if mission.mode == "implementation":
        with writer_lock(resolved, mission.mission_id):
            return asyncio.run(run_mission(resolved, mission))
    return asyncio.run(run_mission(resolved, mission))
