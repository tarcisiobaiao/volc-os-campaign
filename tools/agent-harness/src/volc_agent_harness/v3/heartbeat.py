"""Heartbeat compacto: evento estruturado, não despejo de log.

Os logs da rodada anterior chegaram a centenas de KB sem oferecer resumo
proporcional. O terminal recebia tudo e o operador não conseguia dizer, de
relance, se o writer estava produzindo ou travado.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HeartbeatEvent:
    lane: str
    phase: str                      # compile | baseline | writer | gate | review
    status: str                     # active | alive_without_output | completed | failed
    active_seconds: int
    seconds_since_event: int
    current_file: str | None = None
    current_gate: int | None = None
    stdout_kib: int = 0
    last_material_event: str = ""
    next: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def linha_humana(self) -> str:
        """Uma linha. É o que o terminal recebe."""

        alvo = self.current_file or (f"gate {self.current_gate}" if self.current_gate else "-")
        return (
            f"[{self.lane}] {self.phase}/{self.status} "
            f"{self.active_seconds}s ativo, {self.seconds_since_event}s sem evento "
            f"| {alvo} | {self.last_material_event or '—'} → {self.next or '—'}"
        )


@dataclass
class HeartbeatSink:
    """Grava tudo em artefato; devolve ao terminal só o que muda de fase."""

    artifact: Path
    resumo_a_cada_segundos: int = 900
    _ultimo_resumo: int = field(default=0, init=False)
    _ultima_fase: str = field(default="", init=False)

    def emit(self, evento: HeartbeatEvent) -> str | None:
        self.artifact.parent.mkdir(parents=True, exist_ok=True)
        with self.artifact.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(evento.as_dict(), ensure_ascii=False) + "\n")

        mudou_de_fase = evento.phase != self._ultima_fase
        venceu_o_intervalo = (
            evento.active_seconds - self._ultimo_resumo >= self.resumo_a_cada_segundos
        )
        terminal = evento.status in {"completed", "failed"}
        if mudou_de_fase or venceu_o_intervalo or terminal:
            self._ultima_fase = evento.phase
            self._ultimo_resumo = evento.active_seconds
            return evento.linha_humana()
        return None


def alive_without_output_e_falha(*, seconds_since_event: int, limite: int) -> bool:
    """Silêncio não é falha. Só o timeout declarado encerra.

    Antes de qualquer kill: inspecionar processo, gate corrente e subprocessos.
    """

    return False
