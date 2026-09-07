"""Error translation — every branch maps to a stable code + PT message."""

from __future__ import annotations

import httpx
import openai
import pytest

from app.errors import (
    PipelineError,
    is_fatal,
    is_retryable,
    translate_openai_error,
)

_REQ = httpx.Request("POST", "https://api.openai.com/v1/images/edits")


def _status_error(cls, status: int, code: str | None, message: str = "boom"):
    body = {"error": {"code": code, "message": message}} if code else None
    return cls(message, response=httpx.Response(status, request=_REQ), body=body)


def test_invalid_api_key():
    exc = _status_error(openai.AuthenticationError, 401, "invalid_api_key", "bad key")
    code, msg = translate_openai_error(exc)
    assert code == "invalid_api_key"
    assert "inválida" in msg.lower() or "revogada" in msg.lower()
    assert is_fatal(code)


def test_insufficient_quota_beats_generic_rate_limit():
    # insufficient_quota is itself a RateLimitError — must be matched first.
    exc = _status_error(openai.RateLimitError, 429, "insufficient_quota", "no funds")
    code, msg = translate_openai_error(exc)
    assert code == "insufficient_quota"
    assert "saldo" in msg.lower() or "crédito" in msg.lower()
    assert is_fatal(code)


def test_plain_rate_limit_is_retryable_not_fatal():
    exc = _status_error(openai.RateLimitError, 429, "rate_limit_exceeded", "slow down")
    code, _ = translate_openai_error(exc)
    assert code == "rate_limit"
    assert is_retryable(code)
    assert not is_fatal(code)


def test_content_policy_block():
    exc = _status_error(
        openai.BadRequestError,
        400,
        "content_policy_violation",
        "Your request was rejected by our safety system",
    )
    code, msg = translate_openai_error(exc)
    assert code == "content_policy"
    assert "política" in msg.lower()
    assert not is_fatal(code)  # one image blocked, others can still generate


def test_permission_denied_is_no_access_and_fatal():
    exc = _status_error(openai.PermissionDeniedError, 403, "model_not_found", "no access")
    code, _ = translate_openai_error(exc)
    assert code == "no_access"
    assert is_fatal(code)


def test_connection_error_is_retryable():
    exc = openai.APIConnectionError(request=_REQ)
    code, _ = translate_openai_error(exc)
    assert code == "connection"
    assert is_retryable(code)


def test_generic_openai_error():
    exc = openai.OpenAIError("something odd")
    code, msg = translate_openai_error(exc)
    assert code == "openai_error"
    assert "OpenAI" in msg


def test_non_openai_exception_falls_back():
    code, msg = translate_openai_error(ValueError("weird"))
    assert code == "error"
    assert "weird" in msg


def test_pipeline_error_passes_through():
    perr = PipelineError("insufficient_quota", "Sem saldo", raw="429")
    code, msg = translate_openai_error(perr)
    assert code == "insufficient_quota"
    assert msg == "Sem saldo"
