"""Record a run, then replay it without a network.

You do not need the model to be deterministic. You need to replay the harness
with the model's decisions held fixed -- then the loop, budgets, permissions and
compaction become ordinary testable code.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


class ReplayExhausted(RuntimeError):
    """The harness under test asked for more turns than the recording holds.

    Not a nuisance -- a finding. Your change made the agent do more work.
    """


@dataclass
class Recording:
    """Everything needed to reconstruct a session offline."""

    run_id: str
    task: str
    model_replies: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[str] = field(default_factory=list)
    stop_reason: str = ""
    harness_version: str = ""     # when a replay behaves oddly, ask what changed

    def save(self, directory: str | Path = "recordings", label: str = "") -> Path:
        # Name it for what it proves, not just for its id.
        stem = f"{label}_{self.run_id}" if label else self.run_id
        path = Path(directory) / f"{stem}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, default=str))
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Recording":
        return cls(**json.loads(Path(path).read_text()))


@dataclass
class RecordingModel:
    """Wraps a real model and captures what it says."""

    inner: Callable[[list[dict]], dict]
    recording: Recording

    def __call__(self, messages: list[dict]) -> dict:
        reply = self.inner(messages)
        self.recording.model_replies.append(reply)
        return reply


@dataclass
class ReplayModel:
    """Replays captured replies in order. No network, fully deterministic."""

    recording: Recording
    index: int = 0

    def __call__(self, messages: list[dict]) -> dict:
        if self.index >= len(self.recording.model_replies):
            raise ReplayExhausted(
                f"Replay ran out after {self.index} model calls. The harness "
                "under test is making more calls than the recording holds."
            )
        reply = self.recording.model_replies[self.index]
        self.index += 1
        return reply

    @property
    def exhausted(self) -> bool:
        return self.index >= len(self.recording.model_replies)
