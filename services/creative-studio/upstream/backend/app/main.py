"""FastAPI application — Aprova Ad Studio backend.

Endpoints:
  GET  /health          → liveness check
  POST /generate        → accepts GenerateRequest JSON, returns ZIP binary
  POST /generate/stream → same input, streams SSE progress + inline images
"""

from __future__ import annotations

# Import quarantine: prevents unauthenticated generation/config routes and key loading.
raise RuntimeError("UPSTREAM_REFERENCE_ONLY: integrate through the authenticated VOLC adapter; do not launch this app.")

import logging
import logging.config

import httpx
import openai
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from app import runtime_config
from app.config import settings
from app.errors import PipelineError, translate_openai_error
from app.schemas import GenerateRequest
from app.services.generation import GenerationService

# ── Structured logging ────────────────────────────────────────────────────────

logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "format": '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)r}',
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
            }
        },
        "root": {"level": "INFO", "handlers": ["console"]},
        "loggers": {
            "app": {"level": "DEBUG", "propagate": True},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {"level": "WARNING"},
        },
    }
)

log = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Aprova Ad Studio API",
    description="Multi-agent backend for Aprova Concursos creative generation.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Apply any UI-saved key overrides BEFORE building the service (providers read the
# keys at construction), then build. Rebuilt when keys change via /config.
runtime_config.load_into_settings()
_service = GenerationService()


def _rebuild_service() -> None:
    """Recreate the service so agents/providers pick up new API keys."""
    global _service
    _service = GenerationService()


# ── Error handling ────────────────────────────────────────────────────────────

@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(PipelineError)
async def pipeline_error_handler(_: Request, exc: PipelineError) -> JSONResponse:
    # Already translated — surface the exact cause + stable code to the frontend.
    log.error("PipelineError [%s]: %s", exc.code, exc.raw)
    return JSONResponse(
        status_code=502,
        content={"detail": exc.user_message, "code": exc.code},
    )


@app.exception_handler(openai.OpenAIError)
async def openai_error_handler(_: Request, exc: openai.OpenAIError) -> JSONResponse:
    # Safety net: translate any raw OpenAI error that escaped the pipeline.
    code, message = translate_openai_error(exc)
    log.error("OpenAIError [%s]: %s", code, exc)
    return JSONResponse(status_code=502, content={"detail": message, "code": code})


@app.exception_handler(Exception)
async def generic_error_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Check backend logs."},
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Meta"])
async def health() -> dict:
    return {
        "status": "ok",
        "provider": settings.image_provider,
        "openai_model": settings.openai_model,
        "gemini_model": settings.gemini_model,
        "blueprint_models": {
            "meta-ads": settings.blueprint_model_for("meta-ads"),
            "news": settings.blueprint_model_for("news"),
            "pinterest": settings.blueprint_model_for("pinterest"),
        },
    }


# ── Config: runtime API keys (managed from the frontend) ───────────────────────

class ConfigUpdate(BaseModel):
    openai_api_key: str | None = None
    gemini_api_key: str | None = None


@app.get("/config", tags=["Config"])
async def get_config() -> dict:
    """Masked view of which API keys are configured and from where (env vs UI)."""
    return runtime_config.status()


@app.post("/config", tags=["Config"])
async def set_config(update: ConfigUpdate) -> dict:
    """Persist new API keys (overriding the .env defaults) and rebuild the service."""
    changed = runtime_config.update(update.model_dump(exclude_none=True))
    if changed:
        _rebuild_service()
        log.info("Config: API keys updated via UI: %s", changed)
    return {"updated": changed, **runtime_config.status()}


async def _probe_openai(key: str) -> dict:
    if not key:
        return {"ok": False, "code": "missing", "message": "Nenhuma chave OpenAI configurada."}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )
        if r.status_code == 200:
            return {"ok": True, "code": "ok", "message": "Chave OpenAI válida."}
        if r.status_code == 401:
            return {"ok": False, "code": "invalid_api_key", "message": "Chave OpenAI inválida ou revogada."}
        if r.status_code == 429:
            return {"ok": False, "code": "rate_limit", "message": "OpenAI: limite/saldo atingido (429). Verifique os créditos da conta."}
        return {"ok": False, "code": f"http_{r.status_code}", "message": f"OpenAI respondeu {r.status_code}."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": "connection", "message": f"Falha ao contatar a OpenAI: {exc}"}


async def _probe_gemini(key: str) -> dict:
    if not key:
        return {"ok": False, "code": "missing", "message": "Nenhuma chave Gemini configurada."}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
            )
        if r.status_code == 200:
            return {"ok": True, "code": "ok", "message": "Chave Gemini válida."}
        if r.status_code in (400, 403):
            return {"ok": False, "code": "invalid_api_key", "message": "Chave Gemini inválida ou sem permissão."}
        return {"ok": False, "code": f"http_{r.status_code}", "message": f"Gemini respondeu {r.status_code}."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": "connection", "message": f"Falha ao contatar o Gemini: {exc}"}


@app.post("/config/test", tags=["Config"])
async def test_config(update: ConfigUpdate) -> dict:
    """Validate keys (provided ones, else the active ones) against the live APIs.

    Note: this detects an invalid/revoked key reliably; an empty-balance
    (insufficient_quota) only surfaces on a real generation call.
    """
    payload = update.model_dump(exclude_none=True)
    openai_key = payload.get("openai_api_key") or settings.openai_api_key
    gemini_key = payload.get("gemini_api_key") or settings.gemini_api_key
    return {
        "openai": await _probe_openai(openai_key),
        "gemini": await _probe_gemini(gemini_key),
    }


@app.post("/generate", tags=["Generation"])
async def generate(request: GenerateRequest) -> Response:
    """Generate creatives and return a ZIP archive.

    Accepts JSON payload from the frontend.
    Returns a binary ZIP containing PNG/JPG images named aprova-ad-{n}.png.
    """
    log.info(
        "POST /generate — ratio=%s quantity=%d objective=%r",
        request.aspect_ratio,
        request.quantity,
        request.objective[:80],
    )

    zip_bytes = await _service.generate_zip(request)

    if not zip_bytes:
        raise HTTPException(
            status_code=500,
            detail="No images were generated. Check provider logs.",
        )

    log.info("POST /generate — returning ZIP (%d bytes)", len(zip_bytes))
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="aprova-ads.zip"',
            "Content-Length": str(len(zip_bytes)),
        },
    )


@app.post("/generate/stream", tags=["Generation"])
async def generate_stream(request: GenerateRequest) -> StreamingResponse:
    """Generate creatives, streaming real progress as Server-Sent Events.

    Emits `phase`, `image_start`, `image_done` (with the image inline as a data
    URL), `image_failed`, `done`, and `error` events. Errors (sem saldo, chave
    inválida, rate limit, conteúdo bloqueado) arrive as a final `error` event with
    a stable code + a user-facing PT message — the exact technical cause is logged.
    """
    log.info(
        "POST /generate/stream — ratio=%s quantity=%d objective=%r",
        request.aspect_ratio,
        request.quantity,
        request.objective[:80],
    )

    async def event_source():
        async for event in _service.generate_events(request):
            yield event.to_sse()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # don't let a proxy buffer the stream
        },
    )
