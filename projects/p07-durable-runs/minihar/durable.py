"""Surviving a restart.

A long agent run WILL be interrupted -- a deploy, an OOM, a timeout. The two
questions are whether it can continue, and whether the interruption left the
world half-changed.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Checkpoint:
    """Enough state to continue a run that stopped mid-flight."""

    run_id: str
    task: str
    turn: int
    messages: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0
    cost_usd: float = 0.0
    completed_actions: list[str] = field(default_factory=list)
    stop_reason: str = ""
    saved_at: float = field(default_factory=time.time)

    @property
    def resumable(self) -> bool:
        """A finished run is not resumable, whatever its outcome."""
        return self.stop_reason in ("", "interrupted")


@dataclass
class RunStore:
    """Persists checkpoints. A directory here; a table in production."""

    directory: Path

    def __post_init__(self) -> None:
        self.directory = Path(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, checkpoint: Checkpoint) -> Path:
        path = self.directory / f"{checkpoint.run_id}.json"
        # Write to a temporary file then rename: a crash mid-write must not
        # leave a corrupt checkpoint, which would lose the whole run.
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(checkpoint), indent=2, default=str))
        temp.replace(path)
        return path

    def load(self, run_id: str) -> Checkpoint | None:
        path = self.directory / f"{run_id}.json"
        if not path.exists():
            return None
        return Checkpoint(**json.loads(path.read_text()))

    def resumable_runs(self) -> list[str]:
        out = []
        for path in self.directory.glob("*.json"):
            checkpoint = Checkpoint(**json.loads(path.read_text()))
            if checkpoint.resumable:
                out.append(checkpoint.run_id)
        return sorted(out)


@dataclass
class IdempotencyLedger:
    """Stops a resumed run repeating a side effect.

    The dangerous case is a run that issued a refund, died, and resumed. Without
    a ledger it issues the refund again -- F11, partial-write damage.
    """

    _done: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def key(tool: str, arguments: dict[str, Any]) -> str:
        """Same tool plus same arguments is the same action."""
        payload = json.dumps({"tool": tool, "args": arguments}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def already_done(self, tool: str, arguments: dict[str, Any]) -> bool:
        return self.key(tool, arguments) in self._done

    def result_of(self, tool: str, arguments: dict[str, Any]) -> Any:
        return self._done.get(self.key(tool, arguments))

    def record(self, tool: str, arguments: dict[str, Any], result: Any) -> None:
        self._done[self.key(tool, arguments)] = result

    def run_once(self, tool: str, arguments: dict[str, Any], fn) -> Any:
        """Run fn, or return the previous result if this action already ran."""
        if self.already_done(tool, arguments):
            return self.result_of(tool, arguments)
        result = fn(**arguments)
        self.record(tool, arguments, result)
        return result

    @property
    def actions(self) -> list[str]:
        return sorted(self._done)
