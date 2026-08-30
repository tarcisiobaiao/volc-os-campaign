"""Phase 2 — Persona archaeology. Normalizes the engine's personas to schema."""
from __future__ import annotations

from typing import Any, Dict, List

from app.agents.base import BaseAgent

_LITERACY = {"high", "medium", "low"}


class PersonaArchaeologyAgent(BaseAgent):
    name = "PersonaArchaeologyAgent"
    phase = "discovery"

    def run(self, discovery_json: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = discovery_json.get("personas") or []
        out: List[Dict[str, Any]] = []
        for p in raw:
            if not isinstance(p, dict) or not p.get("name"):
                continue
            literacy = str(p.get("digital_literacy", "medium")).lower()
            out.append(
                {
                    "name": str(p.get("name")),
                    "demographics": p.get("demographics") or "",
                    "core_pain": p.get("core_pain") or "",
                    "digital_literacy": literacy if literacy in _LITERACY else "medium",
                    "typing_style": p.get("typing_style") or "",
                    "main_systems": [str(s) for s in (p.get("main_systems") or [])],
                }
            )
        self.log(f"{len(out)} personas normalizadas.", step="personas")
        return out
