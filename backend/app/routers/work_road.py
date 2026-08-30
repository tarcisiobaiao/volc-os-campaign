"""Leitura autenticada da fonte viva do Work Road.

O arquivo editorial continua sendo a fonte. Esta rota apenas valida, calcula o
resumo e o entrega ao QG Agêntico. Ela não mantém uma segunda cópia no banco e
não oferece escrita sem trilha de auditoria.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response

from app.seguranca.identidade import exigir_admin, exigir_usuario
from app.work_road import export_doc, inbox_store


router = APIRouter(
    prefix="/api/work-road",
    tags=["work-road"],
    dependencies=[Depends(exigir_usuario)],
)

_RAIZ = Path(__file__).resolve().parents[3]
_ROADMAP = _RAIZ / "volc-os-workbook" / "ROADMAP-VIVO.json"
_INBOX = _RAIZ / "volc-os-workbook" / "INBOX-ROADMAP.json"
_INBOX_RECIBOS = _RAIZ / "volc-os-workbook" / "INBOX-ROADMAP.receipts.jsonl"
_COBERTURA = _RAIZ / "volc-os-workbook" / "INBOX-COVERAGE.json"
_GRAFO_STATUS = _RAIZ / "graphify-out" / "UPDATE_STATUS.json"
_HARNESS_RUNS = _RAIZ / "tools" / "agent-harness" / "runs"
_WORKTREE_ROOTS = (
    _RAIZ / ".claude" / "worktrees",
    _RAIZ / ".agent-worktrees",
)
_ESTADOS = {"done", "partial", "risk", "todo", "reserved"}
_PID_DA_TRAVA = re.compile(r"\bpid\s+(\d+)\b")


def _falha(motivo: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=f"Fonte viva do Work Road indisponível: {motivo}",
    )


def _validar(documento: Any) -> dict[str, Any]:
    if not isinstance(documento, dict):
        raise _falha("o documento não é um objeto JSON.")
    if documento.get("schema_version") != 1:
        raise _falha("versão de schema não reconhecida.")

    iniciativas = documento.get("initiatives")
    if not isinstance(iniciativas, list) or not iniciativas:
        raise _falha("nenhuma iniciativa válida foi encontrada.")

    ids_iniciativas: set[str] = set()
    ids_tarefas: set[str] = set()
    tarefas: list[dict[str, Any]] = []
    for indice, iniciativa in enumerate(iniciativas, start=1):
        if not isinstance(iniciativa, dict):
            raise _falha(f"a iniciativa {indice} não é um objeto.")
        iniciativa_id = str(iniciativa.get("id") or "").strip()
        if not iniciativa_id or iniciativa_id in ids_iniciativas:
            raise _falha(f"id de iniciativa ausente ou duplicado: {iniciativa_id or indice}.")
        ids_iniciativas.add(iniciativa_id)

        lista = iniciativa.get("tasks")
        if not isinstance(lista, list) or not lista:
            raise _falha(f"{iniciativa_id} não possui tarefas.")
        for tarefa in lista:
            if not isinstance(tarefa, dict):
                raise _falha(f"{iniciativa_id} possui uma tarefa inválida.")
            tarefa_id = str(tarefa.get("id") or "").strip()
            estado = str(tarefa.get("status") or "").strip()
            titulo = str(tarefa.get("title") or "").strip()
            if not tarefa_id or tarefa_id in ids_tarefas:
                raise _falha(f"id de tarefa ausente ou duplicado: {tarefa_id or iniciativa_id}.")
            if estado not in _ESTADOS:
                raise _falha(f"{tarefa_id} possui estado desconhecido: {estado or 'vazio'}.")
            if not titulo:
                raise _falha(f"{tarefa_id} não possui título.")
            ids_tarefas.add(tarefa_id)
            tarefas.append(tarefa)

    pesos = documento.get("status_weights")
    if not isinstance(pesos, dict):
        raise _falha("pesos editoriais ausentes.")

    contagens = Counter(str(tarefa["status"]) for tarefa in tarefas)
    aceitas = [tarefa for tarefa in tarefas if tarefa["status"] != "reserved"]
    peso_total = sum(float(pesos[tarefa["status"]]) for tarefa in aceitas)
    percentual = round((peso_total / len(aceitas)) * 100, 1) if aceitas else 0.0

    documento["summary"] = {
        "initiatives": len(iniciativas),
        "tasks": len(tarefas),
        "accepted_tasks": len(aceitas),
        "progress_percent": percentual,
        "counts": {estado: contagens.get(estado, 0) for estado in sorted(_ESTADOS)},
    }
    return documento


def ler_roadmap(caminho: Path | None = None) -> tuple[dict[str, Any], str]:
    origem = caminho or _ROADMAP
    try:
        bruto = origem.read_bytes()
    except OSError as exc:
        raise _falha("o arquivo não pôde ser lido.") from exc
    try:
        documento = json.loads(bruto)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _falha("o JSON está inválido.") from exc

    validado = _validar(documento)
    validado["source"] = {
        "path": "volc-os-workbook/ROADMAP-VIVO.json",
        "sha256": hashlib.sha256(bruto).hexdigest(),
        "read_at": datetime.now(timezone.utc).isoformat(),
    }
    return validado, hashlib.sha256(bruto).hexdigest()


@router.get("")
async def work_road() -> JSONResponse:
    documento, etag = ler_roadmap()
    return JSONResponse(
        documento,
        headers={
            "Cache-Control": "no-store",
            "ETag": f'"{etag}"',
        },
    )


def _git(argumentos: list[str], cwd: Path = _RAIZ) -> str:
    """Executa somente consultas Git com argumentos definidos pelo servidor.

    Nenhum valor vindo da requisição entra neste comando. A rota é um visor
    local do QG, não uma passagem genérica para shell.
    """
    resultado = subprocess.run(
        ["git", *argumentos],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
    )
    return resultado.stdout


def _parse_worktrees(bruto: str) -> list[dict[str, str]]:
    blocos: list[dict[str, str]] = []
    atual: dict[str, str] = {}
    for linha in [*bruto.splitlines(), ""]:
        if not linha.strip():
            if atual:
                blocos.append(atual)
                atual = {}
            continue
        chave, _, valor = linha.partition(" ")
        atual[chave] = valor.strip()
    return blocos


def _esta_na_pasta_de_agentes(caminho: Path) -> bool:
    for raiz in _WORKTREE_ROOTS:
        try:
            caminho.resolve().relative_to(raiz.resolve())
            return True
        except (OSError, ValueError):
            continue
    return False


def _processo_ativo(texto_da_trava: str) -> bool:
    encontrado = _PID_DA_TRAVA.search(texto_da_trava)
    if not encontrado:
        return False
    try:
        os.kill(int(encontrado.group(1)), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _tarefas_por_id(caminho: Path) -> dict[str, dict[str, Any]]:
    try:
        documento = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return {
        str(tarefa.get("id")): tarefa
        for iniciativa in documento.get("initiatives", [])
        if isinstance(iniciativa, dict)
        for tarefa in iniciativa.get("tasks", [])
        if isinstance(tarefa, dict) and tarefa.get("id")
    }


def _mudancas_do_roadmap(caminho_da_worktree: Path) -> list[dict[str, Any]]:
    oficiais = _tarefas_por_id(_ROADMAP)
    propostas = _tarefas_por_id(
        caminho_da_worktree / "volc-os-workbook" / "ROADMAP-VIVO.json"
    )
    mudancas: list[dict[str, Any]] = []
    for tarefa_id in sorted(oficiais.keys() | propostas.keys()):
        antes = oficiais.get(tarefa_id)
        depois = propostas.get(tarefa_id)
        if antes == depois:
            continue
        mudancas.append({
            "task_id": tarefa_id,
            "title": str((depois or antes or {}).get("title") or tarefa_id),
            "before_status": antes.get("status") if antes else None,
            "after_status": depois.get("status") if depois else None,
            "proof_changed": bool(antes and depois and antes.get("proof") != depois.get("proof")),
        })
    return mudancas[:30]


def _json_local(caminho: Path) -> dict[str, Any]:
    try:
        valor = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return valor if isinstance(valor, dict) else {}


def _ultimo_heartbeat(caminho_do_run: Path) -> dict[str, Any]:
    mais_recente: dict[str, Any] = {}
    for caminho in caminho_do_run.glob("workers/*/heartbeat.jsonl"):
        try:
            linhas = caminho.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for linha in reversed(linhas):
            try:
                evento = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if not isinstance(evento, dict) or not evento.get("at"):
                continue
            if str(evento["at"]) > str(mais_recente.get("at") or ""):
                mais_recente = evento
            break
    return mais_recente


def _heartbeat_recente(evento: dict[str, Any], agora: datetime) -> bool:
    if evento.get("state") not in {"started", "active"}:
        return False
    try:
        instante = datetime.fromisoformat(str(evento["at"]))
    except (KeyError, TypeError, ValueError):
        return False
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    try:
        intervalo = int(evento.get("expected_interval_seconds") or 30)
    except (TypeError, ValueError):
        intervalo = 30
    # Duas janelas completas mais uma tolerância de agendamento. Missões antigas,
    # que não registravam o intervalo, preservam o limite histórico de 90 s.
    limite = max(90, min(630, intervalo * 2 + 30))
    return 0 <= (agora - instante).total_seconds() <= limite


def _execucoes_do_harness() -> tuple[list[dict[str, Any]], set[Path]]:
    """Projeta recibos reais do harness; não infere tarefa pelo diff editorial."""
    agora = datetime.now(timezone.utc)
    execucoes: list[dict[str, Any]] = []
    worktrees_representadas: set[Path] = set()
    try:
        runs = sorted(
            (item for item in _HARNESS_RUNS.iterdir() if item.is_dir()),
            key=lambda item: item.name,
            reverse=True,
        )
    except OSError:
        return [], set()
    for caminho_do_run in runs[:100]:
        metadata = _json_local(caminho_do_run / "metadata.json")
        if not metadata.get("run_id"):
            continue
        resultado = _json_local(caminho_do_run / "mission-result.json")
        heartbeat = _ultimo_heartbeat(caminho_do_run)
        worktrees = resultado.get("worktrees") or {}
        if isinstance(worktrees, dict):
            for info in worktrees.values():
                if isinstance(info, dict) and info.get("path"):
                    worktrees_representadas.add(Path(str(info["path"])).resolve())
        workers = metadata.get("workers") or []
        writer = next(
            (
                worker
                for worker in workers
                if isinstance(worker, dict) and worker.get("role") == "writer"
            ),
            workers[0] if workers and isinstance(workers[0], dict) else {},
        )
        task_ids = metadata.get("task_ids") or []
        if not task_ids:
            handoff = resultado.get("curation_handoff") or {}
            task_ids = handoff.get("task_ids") or [] if isinstance(handoff, dict) else []
        writer_commit = str(resultado.get("writer_commit") or "")
        terminal = bool(resultado.get("finished_at"))
        execucoes.append({
            "id": str(metadata["run_id"]),
            "name": str(metadata.get("title") or metadata["run_id"]),
            "branch": "",
            "head": (writer_commit or str(metadata.get("base_sha") or ""))[:7],
            "session_active": not terminal and _heartbeat_recente(heartbeat, agora),
            "worktree_locked": False,
            "dirty_files": 0,
            "commits_ahead": 1 if writer_commit else 0,
            "commits": [],
            "roadmap_changes": [],
            "task_ids": [str(item) for item in task_ids if item],
            "worktree": next(iter(worktrees.values()), {}).get("path")
            if isinstance(worktrees, dict) and worktrees else None,
            "agent": writer.get("id") or writer.get("worker_id"),
            "provider": writer.get("provider"),
            "mission": metadata.get("mission_id"),
            "heartbeat_at": heartbeat.get("at"),
            "failed": resultado.get("ok") is False,
            "candidate_status": resultado.get("candidate_status"),
            "run_dir": str(caminho_do_run),
        })
    return execucoes, worktrees_representadas


def ler_execucoes() -> dict[str, Any]:
    """Fotografa worktrees Claude/ADK sem ler prompt, transcript ou credencial."""
    agora = datetime.now(timezone.utc).isoformat()
    try:
        principal = _git(["rev-parse", "--short", "HEAD"]).strip()
        blocos = _parse_worktrees(_git(["worktree", "list", "--porcelain"]))
    except (OSError, subprocess.SubprocessError):
        return {
            "schema_version": 1,
            "available": False,
            "read_at": agora,
            "main_head": None,
            "executions": [],
            "reason": "O monitor local de worktrees não está disponível neste ambiente.",
        }

    execucoes, worktrees_representadas = _execucoes_do_harness()
    for bloco in blocos:
        caminho = Path(bloco.get("worktree") or "")
        if not caminho or not _esta_na_pasta_de_agentes(caminho):
            continue
        if caminho.resolve() in worktrees_representadas:
            continue
        nome = caminho.name
        head = bloco.get("HEAD") or ""
        branch = (bloco.get("branch") or "").removeprefix("refs/heads/")
        trava = bloco.get("locked") or ""
        try:
            base = _git(["merge-base", "main", head], cwd=caminho).strip()
            quantidade = int(_git(["rev-list", "--count", f"{base}..{head}"], cwd=caminho).strip() or "0")
            status = _git(["status", "--porcelain"], cwd=caminho)
            log = _git([
                "log", "-8", "--format=%h%x1f%s%x1f%cI", f"{base}..{head}",
            ], cwd=caminho)
        except (OSError, ValueError, subprocess.SubprocessError):
            quantidade, status, log = 0, "", ""

        commits = []
        for linha in log.splitlines():
            partes = linha.split("\x1f", 2)
            if len(partes) == 3:
                commits.append({"sha": partes[0], "subject": partes[1], "committed_at": partes[2]})

        mudancas = _mudancas_do_roadmap(caminho)
        task_ids = sorted({
            str(item.get("task_id"))
            for item in mudancas
            if item.get("task_id")
        })
        execucoes.append({
            "id": nome,
            "name": nome.replace("-", " "),
            "branch": branch,
            "head": head[:7],
            "session_active": bool(trava and _processo_ativo(trava)),
            "worktree_locked": bool(trava),
            "dirty_files": len([linha for linha in status.splitlines() if linha.strip()]),
            "commits_ahead": quantidade,
            "commits": commits,
            "roadmap_changes": mudancas,
            "task_ids": task_ids,
        })

    execucoes.sort(key=lambda item: (not item["session_active"], item["name"]))
    return {
        "schema_version": 1,
        "available": True,
        "read_at": agora,
        "main_head": principal,
        "executions": execucoes,
        "reason": None,
    }


@router.get("/executions")
async def execucoes_do_qg() -> JSONResponse:
    return JSONResponse(
        ler_execucoes(),
        headers={"Cache-Control": "no-store"},
    )


def _ids_de_tarefa(documento: dict[str, Any]) -> set[str]:
    return {
        str(tarefa.get("id"))
        for iniciativa in documento.get("initiatives") or []
        for tarefa in iniciativa.get("tasks") or []
        if tarefa.get("id")
    }


def _ator(identidade: Any) -> str:
    email = str(getattr(identidade, "email", "") or "").strip()
    sub = str(getattr(identidade, "sub", "") or "").strip()
    return email or sub or "usuario"


@router.get("/inbox")
async def ler_inbox() -> JSONResponse:
    try:
        documento, etag = inbox_store.ler_ou_criar(_INBOX)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"Inbox indisponível: {exc}") from exc
    cobertura = inbox_store.cobertura(_COBERTURA)
    return JSONResponse(
        {
            **documento,
            "summary": inbox_store.resumo(documento.get("entries") or []),
            "coverage": cobertura,
            "source": {
                "path": "volc-os-workbook/INBOX-ROADMAP.json",
                "sha256": etag,
                "read_at": datetime.now(timezone.utc).isoformat(),
            },
            "disclaimer": "Conversa não vira tarefa sozinha. Capturada não pertence ao percentual do roadmap.",
        },
        headers={"Cache-Control": "no-store", "ETag": f'"{etag}"'},
    )


@router.post("/inbox")
async def capturar_ideia(payload: dict[str, Any], identidade: Any = Depends(exigir_usuario)) -> JSONResponse:
    titulo = str(payload.get("title") or "").strip()
    original = str(payload.get("original") or payload.get("description") or "").strip()
    if len(titulo) < 3 or not original:
        raise HTTPException(status_code=422, detail="Informe título e a descrição original da ideia.")
    origem = str(payload.get("origin") or "usuario").strip()
    try:
        resultado = inbox_store.capturar(
            _INBOX,
            _INBOX_RECIBOS,
            titulo=titulo,
            original=original,
            actor=_ator(identidade),
            origin=origem,
            origin_ref=payload.get("origin_ref"),
            explanation=payload.get("explanation"),
            author=payload.get("author"),
            cluster=payload.get("suggested_cluster"),
            urgency=payload.get("suggested_urgency"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(resultado, status_code=201, headers={"Cache-Control": "no-store"})


@router.post("/inbox/{entry_id}/triage")
async def triar_entrada(
    entry_id: str,
    payload: dict[str, Any],
    identidade: Any = Depends(exigir_admin),
) -> JSONResponse:
    documento, _ = ler_roadmap()
    try:
        resultado = inbox_store.triar(
            _INBOX,
            _INBOX_RECIBOS,
            entry_id=entry_id,
            actor=_ator(identidade),
            triage=str(payload.get("triage") or ""),
            justification=payload.get("justification"),
            promoted_task_id=payload.get("promoted_task_id"),
            possible_duplicate_of=payload.get("possible_duplicate_of"),
            task_ids=_ids_de_tarefa(documento),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Entrada de inbox não encontrada.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(resultado, headers={"Cache-Control": "no-store"})


@router.get("/tasks/{task_id}")
async def uma_tarefa(task_id: str) -> JSONResponse:
    documento, etag = ler_roadmap()
    for iniciativa in documento.get("initiatives") or []:
        for indice, tarefa in enumerate(iniciativa.get("tasks") or []):
            if str(tarefa.get("id")) == task_id:
                return JSONResponse(
                    {
                        "task": tarefa,
                        "initiative": {chave: iniciativa[chave] for chave in iniciativa if chave != "tasks"},
                        "index_in_initiative": indice,
                        "source": documento.get("source"),
                    },
                    headers={"Cache-Control": "no-store", "ETag": f'"{etag}"'},
                )
    raise HTTPException(status_code=404, detail=f"Tarefa {task_id} não existe na fonte viva.")


def _gravar_roadmap(documento: dict[str, Any], *, esperado: str) -> str:
    clone = dict(documento)
    clone.pop("summary", None)
    clone.pop("source", None)
    clone["updated_at"] = datetime.now(timezone.utc).date().isoformat()
    bruto = (json.dumps(clone, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    atual = hashlib.sha256(_ROADMAP.read_bytes()).hexdigest()
    if atual != esperado:
        raise ValueError("O Roadmap Vivo mudou desde a leitura; recarregue antes de reordenar.")
    tmp = _ROADMAP.with_name(".ROADMAP-VIVO.json.tmp")
    with tmp.open("wb") as handle:
        handle.write(bruto)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, _ROADMAP)
    return hashlib.sha256(bruto).hexdigest()


@router.post("/reorder")
async def reordenar(payload: dict[str, Any], identidade: Any = Depends(exigir_admin)) -> JSONResponse:
    iniciativa_id = str(payload.get("initiative_id") or "").strip()
    pedidos = [str(item).strip() for item in (payload.get("task_ids") or []) if str(item).strip()]
    if not iniciativa_id or not pedidos:
        raise HTTPException(status_code=422, detail="Informe initiative_id e a lista completa de task_ids.")
    esperado = str(payload.get("expected_sha256") or "").strip()
    if not esperado:
        raise HTTPException(status_code=422, detail="Informe expected_sha256 da fonte que está sendo reordenada.")
    with inbox_store.travar_arquivo(_ROADMAP):
        documento, antes = ler_roadmap()
        if antes != esperado:
            raise HTTPException(status_code=409, detail="O Roadmap Vivo mudou; recarregue antes de reordenar.")
        alvo = next((item for item in documento["initiatives"] if item.get("id") == iniciativa_id), None)
        if alvo is None:
            raise HTTPException(status_code=404, detail="Iniciativa não encontrada.")
        atuais = [str(tarefa.get("id")) for tarefa in alvo.get("tasks") or []]
        if sorted(atuais) != sorted(pedidos) or len(set(pedidos)) != len(pedidos):
            raise HTTPException(
                status_code=422,
                detail="A nova ordem precisa ser uma permutação exata das tarefas da iniciativa.",
            )
        por_id = {str(tarefa.get("id")): tarefa for tarefa in alvo["tasks"]}
        alvo["tasks"] = [por_id[tarefa_id] for tarefa_id in pedidos]
        for indice, tarefa in enumerate(alvo["tasks"], start=1):
            tarefa["order"] = indice
        try:
            depois = _gravar_roadmap(documento, esperado=antes)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        recibo = {
            "at": datetime.now(timezone.utc).isoformat(),
            "actor": _ator(identidade),
            "initiative_id": iniciativa_id,
            "before": atuais,
            "after": pedidos,
            "before_sha256": antes,
            "after_sha256": depois,
        }
        inbox_store._append_line(_INBOX_RECIBOS, {**recibo, "action": "reorder"})
    relido, _ = ler_roadmap()
    return JSONResponse({"roadmap": relido, "receipt": recibo}, headers={"Cache-Control": "no-store"})


@router.get("/graph-status")
async def status_do_grafo() -> JSONResponse:
    try:
        head = _git(["rev-parse", "HEAD"]).strip()
        head_short = _git(["rev-parse", "--short", "HEAD"]).strip()
    except (OSError, subprocess.SubprocessError):
        head, head_short = None, None
    if not _GRAFO_STATUS.exists():
        return JSONResponse(
            {
                "available": False,
                "stale": True,
                "head": head,
                "head_short": head_short,
                "graph_commit": None,
                "generated_at": None,
                "reason": "O grafo técnico não está neste worktree. Não é verdade operacional atual.",
                "authority": "docs/volc-os-graph/curadoria-operacional.json",
            },
            headers={"Cache-Control": "no-store"},
        )
    try:
        status = json.loads(_GRAFO_STATUS.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="Não foi possível ler o frescor do grafo.") from exc
    commit = str(status.get("built_at_commit") or status.get("commit") or status.get("git_commit") or "")
    current = status.get("current")
    commit_diverge = bool(head is not None and commit and commit != head)
    stale = (current is False) or (not commit) or commit_diverge
    if current is False:
        motivo = str(status.get("reason") or "Os insumos do grafo estão defasados.")
    elif commit_diverge:
        motivo = "O snapshot foi gerado em outro commit; confirme os insumos antes de tratá-lo como atual."
    elif not commit:
        motivo = "O status não informa o commit usado na geração."
    else:
        motivo = None
    return JSONResponse(
        {
            "available": True,
            "stale": stale,
            "head": head,
            "head_short": head_short,
            "graph_commit": commit or None,
            "generated_at": status.get("generated_at") or status.get("updated_at"),
            "reason": motivo,
            "authority": "docs/volc-os-graph/curadoria-operacional.json",
            "raw": {chave: status[chave] for chave in status if chave in {"built_at_commit", "commit", "generated_at", "updated_at", "current", "reason"}},
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/export")
async def exportar(
    format: str = "json",
    scope: str = "full",
    iniciativa: str = "",
    onda: str = "",
    status: str = "",
    busca: str = "",
) -> Response:
    if scope not in export_doc.SCOPES:
        raise HTTPException(status_code=422, detail="Escopo de exportação desconhecido.")
    documento, _ = ler_roadmap()
    recorte = export_doc.recortar(
        documento,
        scope,
        {"iniciativa": iniciativa, "onda": onda, "status": status, "busca": busca},
    )
    gerado = export_doc.gerado_em()
    aviso = None
    if not recorte.get("initiatives"):
        aviso = "O recorte pedido não contém tarefas. Ausência não é zero."
    if format == "json":
        return JSONResponse(
            {"generated_at": gerado, "scope": scope, "roadmap": recorte, "warning": aviso},
            headers={"Cache-Control": "no-store"},
        )
    texto = export_doc.texto(recorte, gerado_em=gerado, aviso=aviso)
    if format == "html":
        corpo = export_doc.html_documento(recorte, gerado_em=gerado, aviso=aviso)
        return Response(
            corpo,
            media_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="workbook-volc-os.html"'},
        )
    if format == "pdf":
        return Response(
            export_doc.pdf_bytes(texto),
            media_type="application/pdf",
            headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="workbook-volc-os.pdf"'},
        )
    if format == "txt":
        return Response(
            texto.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="workbook-volc-os.txt"'},
        )
    if format == "docx":
        candidatos = [
            _RAIZ / "entregaveis" / "Workbook_VOLC_OS_Livro_Vivo_v1.0.docx",
            _RAIZ / "volc-os-workbook" / "Workbook_VOLC_OS_Livro_Vivo_v1.0.docx",
        ]
        for caminho in candidatos:
            if caminho.is_file():
                return Response(
                    caminho.read_bytes(),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={
                        "Cache-Control": "no-store",
                        "Content-Disposition": 'attachment; filename="Workbook_VOLC_OS_Livro_Vivo_v1.0.docx"',
                    },
                )
        raise HTTPException(
            status_code=404,
            detail="DOCX existente nao esta neste worktree. Use HTML/PDF ou rode volc-os-workbook/build.py.",
        )
    raise HTTPException(status_code=422, detail="Formato de exportacao desconhecido.")
