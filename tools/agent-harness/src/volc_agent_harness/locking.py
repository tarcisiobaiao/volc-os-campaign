"""Trava local de escritor por repositório e missão."""

from __future__ import annotations

import fcntl
import hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO


@contextmanager
def writer_lock(repo: Path, mission_id: str) -> Iterator[None]:
    repo_key = hashlib.sha256(str(repo.resolve()).encode("utf-8")).hexdigest()[:16]
    lock_dir = Path("/private/tmp/volc-agent-harness-locks") / repo_key
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{mission_id}.lock"
    handle: TextIO = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                f"já existe um writer ativo para a missão {mission_id}"
            ) from error
        handle.seek(0)
        handle.truncate()
        handle.write(str(Path.cwd()))
        handle.flush()
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
