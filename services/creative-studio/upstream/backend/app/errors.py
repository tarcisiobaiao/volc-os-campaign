"""Error translation — turns raw OpenAI/pipeline exceptions into a stable (code,
user_message) pair so the frontend can show the user the EXACT cause (sem saldo,
chave inválida, rate limit, conteúdo bloqueado) while the full technical error is
still logged on the backend.

Single source of truth: both the streaming endpoint and the classic JSON endpoint
translate through here.
"""

from __future__ import annotations

import openai

# Codes that mean "no point continuing — every remaining image will fail too".
# These abort the whole pipeline immediately instead of burning N more calls.
FATAL_CODES = frozenset(
    {"invalid_api_key", "insufficient_quota", "billing", "no_access"}
)
# Codes worth a bounded retry with backoff (transient).
RETRYABLE_CODES = frozenset({"rate_limit", "connection"})


class PipelineError(Exception):
    """A generation failure already translated to a user-facing message.

    Carries a stable ``code`` (for the frontend to branch on), a friendly
    ``user_message`` in PT-BR, and the ``raw`` technical detail for logs.
    """

    def __init__(self, code: str, user_message: str, raw: str = "") -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.raw = raw or user_message


def _extract(exc: Exception) -> tuple[str | None, str]:
    """Pull the OpenAI error ``code`` and a human message out of an exception."""
    code = getattr(exc, "code", None)
    if not code:
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict):
                code = err.get("code")
    message = getattr(exc, "message", None) or str(exc)
    return (code if isinstance(code, str) else None), message


def translate_openai_error(exc: Exception) -> tuple[str, str]:
    """Map any exception to ``(code, pt_message)``.

    Order matters: ``insufficient_quota`` is itself a ``RateLimitError`` subclass,
    so it must be matched by code BEFORE the generic rate-limit branch.
    """
    if isinstance(exc, PipelineError):
        return exc.code, exc.user_message

    code, raw = _extract(exc)

    if isinstance(exc, openai.AuthenticationError) or code == "invalid_api_key":
        return (
            "invalid_api_key",
            "Chave da OpenAI inválida ou revogada. Verifique a OPENAI_API_KEY no backend/.env.",
        )
    if code == "insufficient_quota":
        return (
            "insufficient_quota",
            "Sua conta OpenAI está sem saldo/crédito (insufficient_quota). "
            "Adicione créditos para continuar.",
        )
    if code in ("billing_hard_limit_reached", "billing_not_active"):
        return (
            "billing",
            "Cobrança da OpenAI bloqueada (limite/faturamento). Verifique o billing da conta.",
        )
    if isinstance(exc, openai.PermissionDeniedError) or code in (
        "model_not_found",
        "model_not_supported",
    ):
        return (
            "no_access",
            "Sua chave não tem acesso a este modelo da OpenAI. Verifique o projeto/organização.",
        )
    if isinstance(exc, openai.RateLimitError) or code == "rate_limit_exceeded":
        return (
            "rate_limit",
            "Limite de requisições da OpenAI atingido. Aguarde alguns segundos e tente novamente.",
        )
    if isinstance(exc, openai.BadRequestError):
        low = (raw or "").lower()
        if any(k in low for k in ("content", "policy", "moderation", "safety", "rejected", "blocked")):
            return (
                "content_policy",
                "Conteúdo bloqueado pela política da OpenAI. Ajuste o objetivo/contexto e tente novamente.",
            )
        return "bad_request", f"Requisição inválida para a OpenAI: {raw}"
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return (
            "connection",
            "Falha de conexão com a OpenAI. Verifique sua internet e tente novamente.",
        )
    if isinstance(exc, openai.OpenAIError):
        return "openai_error", f"Erro da OpenAI: {raw}"

    return "error", (raw or "Erro inesperado ao gerar criativos.")


def to_pipeline_error(exc: Exception) -> PipelineError:
    """Wrap any exception into a translated :class:`PipelineError`."""
    if isinstance(exc, PipelineError):
        return exc
    code, message = translate_openai_error(exc)
    return PipelineError(code=code, user_message=message, raw=str(exc))


def is_fatal(code: str) -> bool:
    """Whether this error should abort the whole pipeline (account-level)."""
    return code in FATAL_CODES


def is_retryable(code: str) -> bool:
    """Whether a single failed image is worth retrying with backoff."""
    return code in RETRYABLE_CODES
