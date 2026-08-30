"""Inbox do Roadmap: fila anterior à fonte editorial.

O snapshot vive em INBOX-ROADMAP.json. Cada mutação:
1. valida o documento;
2. grava o snapshot atomicamente (tmp + fsync + rename);
3. acrescenta um recibo em INBOX-ROADMAP.receipts.jsonl.

Entradas capturadas nunca entram no percentual do ROADMAP-VIVO.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ORIGENS = {"usuario", "claude", "codex", "grok", "adk", "documento", "grafo", "sistema"}
_TRIAGEM = {"capturada", "em_triagem", "promovida", "duplicada", "descartada"}
_URGENCIA = {"baixa", "media", "alta"}
_ID = re.compile(r"^INB-\d{8}-\d{3,}$")
_LIMITES = {
    "title": 240,
    "original": 20_000,
    "explanation": 20_000,
    "origin_ref": 2_000,
    "author": 320,
    "suggested_cluster": 160,
}


def agora_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(bruto: bytes) -> str:
    return hashlib.sha256(bruto).hexdigest()


def _atomic_write(caminho: Path, bruto: bytes) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(f".{caminho.name}.tmp")
    with tmp.open("wb") as handle:
        handle.write(bruto)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, caminho)


def _append_line(caminho: Path, linha: dict[str, Any]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(linha, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def travar_arquivo(caminho: Path):
    """Serializa read-modify-write entre processos locais.

    A escrita atômica evita arquivo parcial; esta trava evita duas versões
    completas competindo e a última apagar a primeira.
    """
    lock = caminho.with_name(f".{caminho.name}.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _validar_limite(nome: str, valor: Any) -> None:
    if valor in (None, ""):
        return
    limite = _LIMITES[nome]
    if len(str(valor)) > limite:
        raise ValueError(f"{nome} excede o limite de {limite} caracteres.")


def documento_vazio() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": agora_utc(),
        "purpose": "Fila anterior ao Roadmap Vivo. Capturada não conta no percentual.",
        "entries": [],
    }


def validar_entrada(entrada: Any) -> dict[str, Any]:
    if not isinstance(entrada, dict):
        raise ValueError("entrada inválida.")
    entrada_id = str(entrada.get("id") or "").strip()
    titulo = str(entrada.get("title") or "").strip()
    original = str(entrada.get("original") or "").strip()
    origem = str(entrada.get("origin") or "").strip()
    triagem = str(entrada.get("triage") or "").strip()
    if not _ID.match(entrada_id):
        raise ValueError(f"id de inbox inválido: {entrada_id or 'vazio'}.")
    if len(titulo) < 3:
        raise ValueError(f"{entrada_id} não possui título.")
    if not original:
        raise ValueError(f"{entrada_id} não possui descrição original.")
    if origem not in _ORIGENS:
        raise ValueError(f"{entrada_id} possui origem desconhecida.")
    if triagem not in _TRIAGEM:
        raise ValueError(f"{entrada_id} possui triagem desconhecida.")
    for campo in _LIMITES:
        _validar_limite(campo, entrada.get(campo))
    urgencia = entrada.get("suggested_urgency")
    if urgencia not in (None, "") and urgencia not in _URGENCIA:
        raise ValueError(f"{entrada_id} possui urgência desconhecida.")
    if triagem == "promovida" and not str(entrada.get("promoted_task_id") or "").strip():
        raise ValueError(f"{entrada_id} promovida sem tarefa vinculada.")
    if triagem == "duplicada" and not str(entrada.get("possible_duplicate_of") or "").strip():
        raise ValueError(f"{entrada_id} marcada duplicada sem referência.")
    if triagem == "descartada" and not str(entrada.get("justification") or "").strip():
        raise ValueError(f"{entrada_id} descartada sem motivo.")
    auditoria = entrada.get("audit") or []
    if not isinstance(auditoria, list) or not auditoria:
        raise ValueError(f"{entrada_id} não possui trilha de auditoria.")
    return entrada


def validar_documento(documento: Any) -> dict[str, Any]:
    if not isinstance(documento, dict):
        raise ValueError("o inbox não é um objeto JSON.")
    if documento.get("schema_version") != 1:
        raise ValueError("versão de schema do inbox não reconhecida.")
    entradas = documento.get("entries")
    if not isinstance(entradas, list):
        raise ValueError("lista de entradas ausente.")
    vistos: set[str] = set()
    for entrada in entradas:
        validada = validar_entrada(entrada)
        entrada_id = validada["id"]
        if entrada_id in vistos:
            raise ValueError(f"id de inbox duplicado: {entrada_id}.")
        vistos.add(entrada_id)
    return documento


def ler_ou_criar(caminho: Path) -> tuple[dict[str, Any], str]:
    if not caminho.exists():
        documento = documento_vazio()
        bruto = json.dumps(documento, ensure_ascii=False, indent=2).encode("utf-8")
        _atomic_write(caminho, bruto)
        return documento, sha256_bytes(bruto)
    bruto = caminho.read_bytes()
    try:
        documento = json.loads(bruto)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("o JSON do inbox está inválido.") from exc
    return validar_documento(documento), sha256_bytes(bruto)


def proximo_id(entradas: list[dict[str, Any]], momento: str | None = None) -> str:
    dia = (momento or agora_utc())[:10].replace("-", "")
    prefixo = f"INB-{dia}-"
    usados = [
        int(item["id"].rsplit("-", 1)[1])
        for item in entradas
        if str(item.get("id") or "").startswith(prefixo)
    ]
    return f"{prefixo}{max(usados, default=0) + 1:03d}"


def capturar(
    snapshot: Path,
    recibos: Path,
    *,
    titulo: str,
    original: str,
    actor: str,
    origin: str = "usuario",
    origin_ref: str | None = None,
    explanation: str | None = None,
    author: str | None = None,
    cluster: str | None = None,
    urgency: str | None = None,
) -> dict[str, Any]:
    with travar_arquivo(snapshot):
        return _capturar_sem_trava(
            snapshot,
            recibos,
            titulo=titulo,
            original=original,
            actor=actor,
            origin=origin,
            origin_ref=origin_ref,
            explanation=explanation,
            author=author,
            cluster=cluster,
            urgency=urgency,
        )


def _capturar_sem_trava(
    snapshot: Path,
    recibos: Path,
    *,
    titulo: str,
    original: str,
    actor: str,
    origin: str = "usuario",
    origin_ref: str | None = None,
    explanation: str | None = None,
    author: str | None = None,
    cluster: str | None = None,
    urgency: str | None = None,
) -> dict[str, Any]:
    documento, antes = ler_ou_criar(snapshot)
    momento = agora_utc()
    entrada_id = proximo_id(documento["entries"], momento)
    entrada = {
        "id": entrada_id,
        "title": titulo.strip(),
        "original": original.strip(),
        "explanation": (explanation or "").strip() or None,
        "origin": origin,
        "origin_ref": origin_ref,
        "author": (author or actor).strip(),
        "captured_at": momento,
        "suggested_cluster": cluster,
        "suggested_urgency": urgency or "media",
        "triage": "capturada",
        "promoted_task_id": None,
        "possible_duplicate_of": None,
        "decision": None,
        "justification": None,
        "audit": [{
            "at": momento,
            "actor": actor,
            "action": "capturada",
            "detail": "Captura explícita. Ainda não pertence ao roadmap.",
        }],
    }
    validar_entrada(entrada)
    documento["entries"].append(entrada)
    documento["updated_at"] = momento
    validar_documento(documento)
    bruto = json.dumps(documento, ensure_ascii=False, indent=2).encode("utf-8")
    depois = sha256_bytes(bruto)
    _atomic_write(snapshot, bruto)
    _append_line(recibos, {
        "at": momento,
        "actor": actor,
        "action": "capturada",
        "entry_id": entrada_id,
        "before_sha256": antes,
        "after_sha256": depois,
        "detail": "Entrada capturada; não adicionada ao roadmap.",
    })
    return {
        "entry": entrada,
        "receipt": {
            "id": entrada_id,
            "captured_at": momento,
            "origin": origin,
            "triage": "capturada",
            "source_path": "volc-os-workbook/INBOX-ROADMAP.json",
            "sha256": depois,
        },
    }


def triar(
    snapshot: Path,
    recibos: Path,
    *,
    entry_id: str,
    actor: str,
    triage: str,
    justification: str | None = None,
    promoted_task_id: str | None = None,
    possible_duplicate_of: str | None = None,
    task_ids: set[str] | None = None,
) -> dict[str, Any]:
    with travar_arquivo(snapshot):
        return _triar_sem_trava(
            snapshot,
            recibos,
            entry_id=entry_id,
            actor=actor,
            triage=triage,
            justification=justification,
            promoted_task_id=promoted_task_id,
            possible_duplicate_of=possible_duplicate_of,
            task_ids=task_ids,
        )


def _triar_sem_trava(
    snapshot: Path,
    recibos: Path,
    *,
    entry_id: str,
    actor: str,
    triage: str,
    justification: str | None = None,
    promoted_task_id: str | None = None,
    possible_duplicate_of: str | None = None,
    task_ids: set[str] | None = None,
) -> dict[str, Any]:
    if triage not in _TRIAGEM or triage == "capturada":
        raise ValueError("triagem inválida.")
    documento, antes = ler_ou_criar(snapshot)
    alvo = next((item for item in documento["entries"] if item["id"] == entry_id), None)
    if alvo is None:
        raise KeyError(entry_id)
    momento = agora_utc()
    # Uma nova decisão não pode carregar campos de uma decisão anterior.
    alvo["promoted_task_id"] = None
    alvo["possible_duplicate_of"] = None
    alvo["decision"] = None
    alvo["justification"] = None
    if triage == "promovida":
        tarefa = str(promoted_task_id or "").strip()
        if not tarefa:
            raise ValueError("promoção exige task_id existente.")
        if task_ids is not None and tarefa not in task_ids:
            raise ValueError("a tarefa promovida não existe no Roadmap Vivo.")
        alvo["promoted_task_id"] = tarefa
        alvo["decision"] = "promovida"
    if triage == "duplicada":
        alvo["possible_duplicate_of"] = str(possible_duplicate_of or "").strip()
        alvo["decision"] = "duplicada"
    if triage == "descartada":
        alvo["justification"] = str(justification or "").strip()
        alvo["decision"] = "descartada"
    if triage == "em_triagem":
        alvo["decision"] = "em_triagem"
    alvo["triage"] = triage
    if justification:
        alvo["justification"] = justification.strip()
    alvo["audit"].append({
        "at": momento,
        "actor": actor,
        "action": triage,
        "detail": justification or f"Estado alterado para {triage}.",
    })
    validar_entrada(alvo)
    documento["updated_at"] = momento
    validar_documento(documento)
    bruto = json.dumps(documento, ensure_ascii=False, indent=2).encode("utf-8")
    depois = sha256_bytes(bruto)
    _atomic_write(snapshot, bruto)
    _append_line(recibos, {
        "at": momento,
        "actor": actor,
        "action": triage,
        "entry_id": entry_id,
        "before_sha256": antes,
        "after_sha256": depois,
        "detail": justification or triage,
        "promoted_task_id": alvo.get("promoted_task_id"),
    })
    return {"entry": alvo, "sha256": depois}


def cobertura(caminho: Path) -> dict[str, Any] | None:
    if not caminho.exists():
        return None
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def resumo(entradas: list[dict[str, Any]]) -> dict[str, int]:
    contagens = {estado: 0 for estado in sorted(_TRIAGEM)}
    for entrada in entradas:
        estado = str(entrada.get("triage") or "")
        if estado in contagens:
            contagens[estado] += 1
    return {
        "total": len(entradas),
        "capturadas": contagens["capturada"],
        "em_triagem": contagens["em_triagem"],
        "promovidas": contagens["promovida"],
        "duplicadas": contagens["duplicada"],
        "descartadas": contagens["descartada"],
        "aguardando_triagem": contagens["capturada"] + contagens["em_triagem"],
        "possiveis_duplicatas": sum(
            1
            for entrada in entradas
            if entrada.get("possible_duplicate_of") or entrada.get("triage") == "duplicada"
        ),
    }
