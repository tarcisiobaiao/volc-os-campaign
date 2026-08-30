"""Lane DeepSeek para propostas de microcorreção, sem ferramentas ou escrita.

O coordenador fornece o texto em memória. Este módulo nunca abre arquivos,
nunca executa shell e nunca aplica a substituição. O provedor recebe apenas o
span, uma janela de contexto sanitizada e uma allowlist fechada. A proposta
aceita fica vinculada ao hash do texto original para impedir aplicação sobre
uma versão diferente.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping, Sequence

from .security import redact


MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
MAX_SPAN_CHARS = 240
MAX_REPLACEMENT_CHARS = 240
MAX_CONTEXT_CHARS = 1_200
MAX_REASON_CHARS = 500
MAX_RESPONSE_BYTES = 32_768

_PROTECTED_PARTS = {
    ".git",
    ".env",
    ".venv",
    ".venv-adk",
    ".venv-graphify",
    "node_modules",
}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class DeepSeekProposalError(RuntimeError):
    """A proposta não pôde ser produzida ou não passou pelas guardas."""


@dataclass(frozen=True)
class ProposalRequest:
    """Entrada local; ``source_text`` nunca é enviado inteiro ao provedor."""

    task_id: str
    target_path: str
    source_text: str
    span: str
    allowed_replacements: tuple[str, ...]
    writable_paths: tuple[str, ...]
    instruction: str = "Escolha a menor substituição semanticamente correta."


@dataclass(frozen=True)
class ValidatedProposal:
    """Proposta inerte. Não contém método de aplicação nem texto já alterado."""

    task_id: str
    target_path: str
    observed_span: str
    replacement: str
    reason: str
    confidence: float
    source_sha256: str
    occurrence_count: int
    external_writes: int = 0
    applied: bool = False


Transport = Callable[[str, str, Mapping[str, Any], float], Mapping[str, Any]]


def _normalize_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or value.endswith("/"):
        raise DeepSeekProposalError("target_path precisa ser um arquivo relativo seguro")
    if any(part in _PROTECTED_PARTS or part.startswith(".env") for part in path.parts):
        raise DeepSeekProposalError("target_path aponta para caminho protegido")
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise DeepSeekProposalError("target_path não pode ser a raiz")
    return normalized


def _owned(target_path: str, writable_paths: Sequence[str]) -> bool:
    for raw_prefix in writable_paths:
        prefix = _normalize_relative_path(raw_prefix).rstrip("/")
        if target_path == prefix or target_path.startswith(prefix + "/"):
            return True
    return False


def _clean_text(value: str, *, limit: int, field: str) -> str:
    cleaned = redact(_CONTROL.sub("", value)).strip()
    if not cleaned:
        raise DeepSeekProposalError(f"{field} vazio depois da sanitização")
    if len(cleaned) > limit:
        raise DeepSeekProposalError(f"{field} excede {limit} caracteres")
    return cleaned


def _bounded_context(source_text: str, span: str) -> str:
    start = source_text.find(span)
    if start < 0:
        raise DeepSeekProposalError("span não ocorre no texto original")
    budget = MAX_CONTEXT_CHARS - len(span)
    before = source_text[max(0, start - budget // 2):start]
    after_start = start + len(span)
    after = source_text[after_start:after_start + (budget - len(before))]
    context = f"{before}<VOLC_SPAN>{span}</VOLC_SPAN>{after}"
    return _clean_text(context, limit=MAX_CONTEXT_CHARS + 32, field="context")


def build_remote_payload(request: ProposalRequest) -> dict[str, Any]:
    """Monta o único conteúdo que pode cruzar a fronteira do provedor."""

    target = _normalize_relative_path(request.target_path)
    if not _owned(target, request.writable_paths):
        raise DeepSeekProposalError("target_path fora do ownership de escrita")
    span = _clean_text(request.span, limit=MAX_SPAN_CHARS, field="span")
    if request.source_text.count(request.span) != 1:
        raise DeepSeekProposalError("span precisa ocorrer exatamente uma vez")
    if not request.allowed_replacements:
        raise DeepSeekProposalError("allowed_replacements não pode ser vazio")
    replacements = tuple(
        _clean_text(item, limit=MAX_REPLACEMENT_CHARS, field="replacement permitido")
        for item in request.allowed_replacements
    )
    if len(set(replacements)) != len(replacements):
        raise DeepSeekProposalError("allowed_replacements contém duplicatas")
    instruction = _clean_text(request.instruction, limit=500, field="instruction")
    return {
        "span": span,
        "allowed_replacements": list(replacements),
        "context": _bounded_context(request.source_text, request.span),
        "instruction": instruction,
    }


def _system_prompt() -> str:
    return (
        "Você é um sniper de microcorreções proposal-only. Não possui ferramentas, "
        "filesystem ou shell. Escolha exatamente um item de allowed_replacements. "
        "Não altere prefixo ou sufixo. Responda apenas JSON com observed_span, "
        "replacement, reason, confidence e external_writes. external_writes deve ser 0."
    )


def _extract_content(response: Mapping[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekProposalError("resposta DeepSeek sem final_response") from exc
    if not isinstance(content, str) or not content.strip():
        raise DeepSeekProposalError("resposta DeepSeek vazia")
    if len(content.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise DeepSeekProposalError("resposta DeepSeek excede o limite")
    return content


def validate_proposal(
    request: ProposalRequest,
    raw_response: Mapping[str, Any] | str,
) -> ValidatedProposal:
    """Valida estrutura, ownership, ocorrência e precondição sem aplicar nada."""

    remote = build_remote_payload(request)
    if isinstance(raw_response, str):
        try:
            payload = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise DeepSeekProposalError("resposta não é JSON válido") from exc
    else:
        payload = dict(raw_response)
    expected_fields = {
        "observed_span", "replacement", "reason", "confidence", "external_writes"
    }
    if set(payload) != expected_fields:
        raise DeepSeekProposalError("campos da proposta divergem do contrato")
    if payload["observed_span"] != remote["span"]:
        raise DeepSeekProposalError("observed_span diverge do span autorizado")
    replacement = payload["replacement"]
    if not isinstance(replacement, str) or replacement not in remote["allowed_replacements"]:
        raise DeepSeekProposalError("replacement fora da allowlist")
    if replacement == request.span:
        raise DeepSeekProposalError("replacement não altera o span")
    reason = payload["reason"]
    if not isinstance(reason, str):
        raise DeepSeekProposalError("reason precisa ser texto")
    reason = _clean_text(reason, limit=MAX_REASON_CHARS, field="reason")
    confidence = payload["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise DeepSeekProposalError("confidence precisa ser número")
    confidence = float(confidence)
    if not 0 <= confidence <= 1:
        raise DeepSeekProposalError("confidence fora do intervalo 0..1")
    if payload["external_writes"] != 0:
        raise DeepSeekProposalError("external_writes precisa ser zero")
    target = _normalize_relative_path(request.target_path)
    occurrence_count = request.source_text.count(request.span)
    if occurrence_count != 1 or not _owned(target, request.writable_paths):
        raise DeepSeekProposalError("precondição local deixou de ser válida")
    return ValidatedProposal(
        task_id=request.task_id,
        target_path=target,
        observed_span=request.span,
        replacement=replacement,
        reason=reason,
        confidence=confidence,
        source_sha256=hashlib.sha256(request.source_text.encode("utf-8")).hexdigest(),
        occurrence_count=occurrence_count,
    )


def _https_transport(
    api_key: str,
    base_url: str,
    payload: Mapping[str, Any],
    timeout_seconds: float,
) -> Mapping[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise DeepSeekProposalError(f"chamada DeepSeek falhou: {type(exc).__name__}") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise DeepSeekProposalError("resposta HTTP DeepSeek excede o limite")
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeepSeekProposalError("resposta HTTP DeepSeek não é JSON") from exc
    if not isinstance(decoded, dict):
        raise DeepSeekProposalError("resposta HTTP DeepSeek não é objeto")
    return decoded


class DeepSeekProposalWorker:
    """Cliente sem ferramentas; a chave existe apenas durante a chamada HTTP."""

    def __init__(
        self,
        *,
        transport: Transport = _https_transport,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 60,
    ) -> None:
        self._transport = transport
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds

    def propose(self, request: ProposalRequest) -> ValidatedProposal:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise DeepSeekProposalError("DEEPSEEK_API_KEY ausente")
        remote = build_remote_payload(request)
        api_payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": json.dumps(remote, ensure_ascii=False)},
            ],
            "stream": False,
            "max_tokens": 1_024,
            "reasoning_effort": "low",
            "response_format": {"type": "json_object"},
            "thinking": {"type": "enabled"},
            "tools": [],
        }
        response = self._transport(
            api_key,
            self._base_url,
            api_payload,
            self._timeout_seconds,
        )
        # reasoning_content, se existir, nunca é lido ou persistido.
        return validate_proposal(request, _extract_content(response))

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(model={MODEL!r}, "
            f"base_url={self._base_url!r}, proposal_only=True)"
        )
