"""OrchestratorAgent — coordinates the full creative generation pipeline.

Flow:
  1. BrandGuardianAgent   — validates logo
  2. prepare_variations() — builds N VariationContext objects
  3. CreativeStrategistAgent × N (concurrent) — blueprints via GPT
  4. ImageGeneratorAgent × N (parallel, bounded concurrency) — images
  5. QualityReviewAgent — inline per image; filters broken results

Two entry points share ONE pipeline (`_generate`):
  - `run_events()`  → async generator of ProgressEvent for the SSE endpoint
  - `run()`         → returns the ordered ImageResults for the classic /generate
"""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from app.agents.brand_guardian import BrandGuardianAgent
from app.agents.creative_strategist import CreativeStrategistAgent
from app.agents.image_generator import ImageGeneratorAgent
from app.agents.quality_review import QualityReviewAgent
from app.config import settings
from app.errors import PipelineError, is_fatal, is_retryable, to_pipeline_error
from app.progress import (
    DoneEvent,
    ErrorEvent,
    ImageDoneEvent,
    ImageFailedEvent,
    ImageStartEvent,
    PhaseEvent,
    ProgressEvent,
    image_data_url,
)
from app.providers.base import ImageResult
from app.schemas import GenerateRequest, LogoPayload, VariationContext

# Backoff delays (seconds) for transient, retryable image errors (rate limit / conn).
_RETRY_BACKOFF: tuple[float, ...] = (2.0, 4.0)

EmitFn = Callable[[ProgressEvent], Awaitable[None]]

_ASSETS_DIR = Path(__file__).parent.parent / "assets"
_PRESET_LOGOS: dict[str, Path] = {
    "aprova-main": _ASSETS_DIR / "aprova-main.png",
}

_DIMENSIONS_MAP: dict[str, str] = {
    "1:1":  "1080x1080",
    "1:4":  "540x2160",
    "2:3":  "1080x1620",
    "3:2":  "1620x1080",
    "3:4":  "1080x1440",
    "4:1":  "2160x540",
    "4:3":  "1440x1080",
    "4:5":  "1080x1350",
    "5:4":  "1350x1080",
    "9:16": "1080x1920",
    "16:9": "1920x1080",
    "21:9": "2520x1080",
}

log = logging.getLogger(__name__)


def _resolve_logo(logo: LogoPayload) -> tuple[str, str]:
    if logo.variant in _PRESET_LOGOS and not logo.data:
        path = _PRESET_LOGOS[logo.variant]
        b64 = base64.b64encode(path.read_bytes()).decode()
        return b64, "image/png"
    return logo.data, logo.mimeType


def _detect_format(aspect_ratio: str, dimensions: str = "") -> str:
    # Prefer exact pixels — always concrete and decimal-free (the ratio string can be
    # non-integer like "1.91:1", which int() would reject and mislabel as vertical).
    if "x" in dimensions.lower():
        try:
            w, h = (int(p) for p in dimensions.lower().split("x", 1))
        except ValueError:
            w = h = 0
        if w and h:
            if w == h:
                return "quadrado"
            return "vertical" if w < h else "horizontal"
    parts = aspect_ratio.split(":")
    try:
        w, h = float(parts[0]), float(parts[1])  # float handles "1.91"
    except (IndexError, ValueError):
        return "vertical"
    if w == h:
        return "quadrado"
    return "vertical" if w < h else "horizontal"


def prepare_variations(
    request: GenerateRequest, research_brief: str = ""
) -> list[VariationContext]:
    # Prefer the exact target pixels sent by the frontend; fall back to the ratio map.
    dimensoes = request.dimensions or _DIMENSIONS_MAP.get(request.aspect_ratio, "1080x1350")
    formato = _detect_format(request.aspect_ratio, dimensoes)
    logo_b64, logo_mime = _resolve_logo(request.logo)
    return [
        VariationContext(
            content_type=request.content_type,
            objetivo_campanha=request.objective,
            formato=formato,
            dimensoes=dimensoes,
            aspect_ratio=request.aspect_ratio,
            variacao_numero=i,
            total_variacoes=request.quantity,
            logo_base64=logo_b64,
            logo_mime_type=logo_mime,
            research_brief=research_brief,
        )
        for i in range(1, request.quantity + 1)
    ]


class OrchestratorAgent:
    def __init__(
        self,
        brand_guardian: BrandGuardianAgent,
        creative_strategist: CreativeStrategistAgent,
        image_generator: ImageGeneratorAgent,
        quality_reviewer: QualityReviewAgent,
    ) -> None:
        self._brand_guardian = brand_guardian
        self._creative_strategist = creative_strategist
        self._image_generator = image_generator
        self._quality_reviewer = quality_reviewer

    # ── Public entry points ─────────────────────────────────────────────────

    async def run(self, request: GenerateRequest) -> list[tuple[int, ImageResult]]:
        """Classic path: run the pipeline and return ordered (n, ImageResult).

        Raises ``PipelineError`` on fatal failure (translated for the caller).
        """
        async def _noop(_: ProgressEvent) -> None:
            return None

        return await self._generate(request, _noop)

    async def run_events(self, request: GenerateRequest) -> AsyncIterator[ProgressEvent]:
        """Streaming path: yield ProgressEvents as the pipeline progresses.

        Terminal failures arrive as a final ``ErrorEvent`` (not an exception) so
        the SSE endpoint can simply write whatever is yielded.
        """
        queue: asyncio.Queue[ProgressEvent | object] = asyncio.Queue()
        sentinel = object()

        async def emit(ev: ProgressEvent) -> None:
            await queue.put(ev)

        async def driver() -> None:
            try:
                await self._generate(request, emit)
            except PipelineError as perr:
                log.error("Orchestrator: pipeline error [%s] — %s", perr.code, perr.raw)
                await queue.put(ErrorEvent(perr.code, perr.user_message))
            except Exception as exc:  # noqa: BLE001 - translate anything unexpected
                perr = to_pipeline_error(exc)
                log.exception("Orchestrator: unhandled pipeline error — %s", exc)
                await queue.put(ErrorEvent(perr.code, perr.user_message))
            finally:
                await queue.put(sentinel)

        task = asyncio.create_task(driver())
        try:
            while True:
                ev = await queue.get()
                if ev is sentinel:
                    break
                yield ev  # type: ignore[misc]
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    # ── Shared pipeline ─────────────────────────────────────────────────────

    async def _generate(
        self, request: GenerateRequest, emit: EmitFn
    ) -> list[tuple[int, ImageResult]]:
        self._brand_guardian.validate(request.logo)
        total = request.quantity

        # One web-search research pass per request; the brief is shared by all variations.
        await emit(PhaseEvent("research"))
        research_brief = await self._creative_strategist.research_context(
            request.content_type, request.objective
        )

        variations = prepare_variations(request, research_brief)
        log.info(
            "Orchestrator: starting pipeline — %d variations, format=%s, dims=%s, type=%s, brief=%dch, concurrency=%d",
            len(variations),
            variations[0].formato if variations else "?",
            variations[0].dimensoes if variations else "?",
            request.content_type,
            len(research_brief),
            settings.image_concurrency,
        )

        await emit(PhaseEvent("blueprints"))
        try:
            blueprints: list[str] = await asyncio.gather(
                *[self._creative_strategist.generate_blueprint(v) for v in variations]
            )
        except Exception as exc:  # noqa: BLE001 - blueprint step is essential
            raise to_pipeline_error(exc) from exc

        # ── Parallel image generation (rolling, bounded concurrency) ──────────
        sem = asyncio.Semaphore(max(1, settings.image_concurrency))
        results: dict[int, ImageResult] = {}
        fatal: list[PipelineError] = []
        cancel = asyncio.Event()

        async def worker(variation: VariationContext, blueprint: str) -> None:
            n = variation.variacao_numero
            started = False
            attempt = 0
            while True:
                if cancel.is_set():
                    return
                retry_after: float | None = None
                async with sem:
                    if cancel.is_set():
                        return
                    if not started:
                        await emit(ImageStartEvent(n, total))
                        started = True
                    try:
                        img = await self._image_generator.generate(variation, blueprint)
                        # Another worker may have hit a fatal error while we rendered —
                        # don't emit a success that will be discarded by `raise fatal`.
                        if cancel.is_set():
                            return
                        if not self._quality_reviewer.is_valid(img):
                            await emit(ImageFailedEvent(
                                n, total, "Imagem reprovada no controle de qualidade."
                            ))
                            return
                        results[n] = img
                        await emit(ImageDoneEvent(
                            n, total, f"aprova-ad-{n}.png",
                            image_data_url(img.data, img.mime_type),
                        ))
                        return
                    except Exception as exc:  # noqa: BLE001 - classify and decide
                        perr = to_pipeline_error(exc)
                        if is_fatal(perr.code):
                            if not fatal:
                                fatal.append(perr)
                            cancel.set()  # stop not-yet-started workers
                            return
                        if is_retryable(perr.code) and attempt < len(_RETRY_BACKOFF):
                            retry_after = _RETRY_BACKOFF[attempt]
                            attempt += 1
                        else:
                            log.error("Orchestrator: variation %d failed [%s] — %s", n, perr.code, perr.raw)
                            await emit(ImageFailedEvent(n, total, perr.user_message))
                            return
                # Semaphore released — back off OUTSIDE the slot so a rate-limited
                # variation doesn't starve the others while it waits.
                if retry_after is not None:
                    await asyncio.sleep(retry_after)

        await asyncio.gather(
            *[worker(v, b) for v, b in zip(variations, blueprints)]
        )

        if fatal:
            raise fatal[0]

        delivered = len(results)
        log.info(
            "Orchestrator: done — %d/%d images passed quality review", delivered, total
        )
        if delivered == 0:
            raise PipelineError(
                "no_images",
                "Nenhuma imagem foi gerada. Tente novamente.",
            )

        await emit(PhaseEvent("packaging"))
        ordered = [(n, results[n]) for n in sorted(results)]
        await emit(DoneEvent(total=total, delivered=delivered))
        return ordered
