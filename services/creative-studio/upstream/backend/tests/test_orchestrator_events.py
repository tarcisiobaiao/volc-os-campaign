"""Orchestrator streaming — event sequence with a mock provider, parallelism,
and fatal-error surfacing.
"""

from __future__ import annotations

import pytest

from app.agents.brand_guardian import BrandGuardianAgent
from app.agents.image_generator import ImageGeneratorAgent
from app.agents.orchestrator import OrchestratorAgent
from app.agents.quality_review import QualityReviewAgent
from app.errors import PipelineError
from app.progress import (
    DoneEvent,
    ErrorEvent,
    ImageDoneEvent,
    ImageStartEvent,
    PhaseEvent,
)
from app.providers.base import ImageProvider, ImageResult
from app.providers.mock import MockImageProvider
from app.schemas import GenerateRequest, LogoPayload


class _FakeStrategist:
    """Stand-in for CreativeStrategistAgent — no OpenAI calls."""

    async def research_context(self, content_type: str, objetivo: str) -> str:
        return ""

    async def generate_blueprint(self, variation) -> str:
        return f"blueprint for variation {variation.variacao_numero}"


class _FatalProvider(ImageProvider):
    """Always raises a fatal (account-level) error."""

    async def generate(self, **kwargs) -> ImageResult:
        raise PipelineError("insufficient_quota", "Sem saldo", raw="429 insufficient_quota")


def _request(quantity: int) -> GenerateRequest:
    return GenerateRequest(
        aspect_ratio="4:5",
        dimensions="1080x1350",
        objective="Curso de teste",
        quantity=quantity,
        logo=LogoPayload(variant="aprova-main", assetLabel="Aprova", data="", mimeType="image/png"),
        content_type="meta-ads",
    )


def _orchestrator(provider: ImageProvider) -> OrchestratorAgent:
    return OrchestratorAgent(
        brand_guardian=BrandGuardianAgent(),
        creative_strategist=_FakeStrategist(),
        image_generator=ImageGeneratorAgent(provider),
        quality_reviewer=QualityReviewAgent(),
    )


async def _collect(orch: OrchestratorAgent, request: GenerateRequest):
    return [ev async for ev in orch.run_events(request)]


async def test_happy_path_event_sequence():
    orch = _orchestrator(MockImageProvider())
    events = await _collect(orch, _request(3))

    phases = [e.phase for e in events if isinstance(e, PhaseEvent)]
    assert phases[0] == "research"
    assert "blueprints" in phases
    assert phases[-1] == "packaging"

    starts = [e for e in events if isinstance(e, ImageStartEvent)]
    dones = [e for e in events if isinstance(e, ImageDoneEvent)]
    assert len(starts) == 3
    assert len(dones) == 3
    assert {e.n for e in dones} == {1, 2, 3}
    assert all(e.data_url.startswith("data:image/") for e in dones)

    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.total == 3 and done.delivered == 3

    # No image_done may appear before its own image_start.
    seen_start: set[int] = set()
    for e in events:
        if isinstance(e, ImageStartEvent):
            seen_start.add(e.n)
        if isinstance(e, ImageDoneEvent):
            assert e.n in seen_start


async def test_fatal_error_surfaces_as_error_event():
    orch = _orchestrator(_FatalProvider())
    events = await _collect(orch, _request(3))

    assert not any(isinstance(e, DoneEvent) for e in events)
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(errors) == 1
    assert errors[0].code == "insufficient_quota"
