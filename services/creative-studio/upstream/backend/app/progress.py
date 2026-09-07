"""Progress events for the streaming pipeline.

Each event serializes to a Server-Sent Events frame:

    event: image_done
    data: {"n": 3, "total": 4, ...}

The orchestrator yields these as it works; the SSE endpoint writes ``to_sse()``
straight to the response stream.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field


def image_data_url(data: bytes, mime_type: str = "image/png") -> str:
    """Encode raw image bytes as a ``data:`` URL for inline streaming."""
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


@dataclass
class ProgressEvent:
    """Base class — subclasses set ``event`` and provide a ``data`` payload."""

    event: str = field(init=False, default="message")

    def payload(self) -> dict:  # pragma: no cover - overridden
        return {}

    def to_sse(self) -> str:
        return f"event: {self.event}\ndata: {json.dumps(self.payload(), ensure_ascii=False)}\n\n"


@dataclass
class PhaseEvent(ProgressEvent):
    phase: str  # "research" | "blueprints" | "packaging"

    def __post_init__(self) -> None:
        self.event = "phase"

    def payload(self) -> dict:
        return {"phase": self.phase}


@dataclass
class ImageStartEvent(ProgressEvent):
    n: int
    total: int

    def __post_init__(self) -> None:
        self.event = "image_start"

    def payload(self) -> dict:
        return {"n": self.n, "total": self.total}


@dataclass
class ImageDoneEvent(ProgressEvent):
    n: int
    total: int
    name: str
    data_url: str

    def __post_init__(self) -> None:
        self.event = "image_done"

    def payload(self) -> dict:
        return {"n": self.n, "total": self.total, "name": self.name, "dataUrl": self.data_url}


@dataclass
class ImageFailedEvent(ProgressEvent):
    n: int
    total: int
    message: str

    def __post_init__(self) -> None:
        self.event = "image_failed"

    def payload(self) -> dict:
        return {"n": self.n, "total": self.total, "message": self.message}


@dataclass
class DoneEvent(ProgressEvent):
    total: int
    delivered: int

    def __post_init__(self) -> None:
        self.event = "done"

    def payload(self) -> dict:
        return {"total": self.total, "delivered": self.delivered}


@dataclass
class ErrorEvent(ProgressEvent):
    code: str
    message: str

    def __post_init__(self) -> None:
        self.event = "error"

    def payload(self) -> dict:
        return {"code": self.code, "message": self.message}
