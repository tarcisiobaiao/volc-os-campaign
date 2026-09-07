"""SSE endpoint wiring — frames are serialized and streamed correctly.

Uses a canned event source (monkeypatched) so no OpenAI calls happen.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main
from app.progress import DoneEvent, ImageDoneEvent, PhaseEvent

_VALID_BODY = {
    "aspect_ratio": "4:5",
    "dimensions": "1080x1350",
    "objective": "Curso de teste",
    "quantity": 1,
    "logo": {"variant": "aprova-main", "assetLabel": "Aprova", "data": "", "mimeType": "image/png"},
    "content_type": "meta-ads",
}


def test_stream_endpoint_emits_sse_frames(monkeypatch):
    async def fake_events(_request):
        yield PhaseEvent("research")
        yield ImageDoneEvent(1, 1, "aprova-ad-1.png", "data:image/png;base64,AAAA")
        yield DoneEvent(total=1, delivered=1)

    monkeypatch.setattr(main._service, "generate_events", fake_events)

    client = TestClient(main.app)
    resp = client.post("/generate/stream", json=_VALID_BODY)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    assert "event: phase" in body
    assert '"phase": "research"' in body
    assert "event: image_done" in body
    assert '"dataUrl": "data:image/png;base64,AAAA"' in body
    assert "event: done" in body


def test_progress_event_to_sse_format():
    frame = PhaseEvent("blueprints").to_sse()
    assert frame == 'event: phase\ndata: {"phase": "blueprints"}\n\n'
