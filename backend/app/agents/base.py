"""
Agent context + base class. The context carries the resolved engine, the
optional grounding client, settings, and an in-memory log sink that the
router persists to pautador_agent_logs.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.llm.base import DiscoveryEngine, GroundingClient


@dataclass
class LogEntry:
    agent: str
    phase: str
    level: str
    message: str
    step: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None


@dataclass
class AgentContext:
    settings: Settings
    engine: DiscoveryEngine
    grounding: Optional[GroundingClient] = None
    logs: List[LogEntry] = field(default_factory=list)

    def log(
        self,
        agent: str,
        phase: str,
        message: str,
        level: str = "info",
        step: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        self.logs.append(
            LogEntry(
                agent=agent,
                phase=phase,
                level=level,
                message=message,
                step=step,
                payload=payload,
                duration_ms=duration_ms,
            )
        )


class BaseAgent:
    name: str = "BaseAgent"
    phase: str = "discovery"

    def __init__(self, ctx: AgentContext):
        self.ctx = ctx

    def log(self, message: str, level: str = "info", **kwargs: Any) -> None:
        self.ctx.log(self.name, self.phase, message, level=level, **kwargs)

    @staticmethod
    def _timer() -> float:
        return time.monotonic()

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return int((time.monotonic() - start) * 1000)
