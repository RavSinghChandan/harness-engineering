"""Tracing an agent run.

A run is a tree, not a request. Recording only the final answer tells you
nothing about which of nineteen tool calls was the wrong one.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum


class EventType(str, Enum):
    RUN_START = "run_start"
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    DENIED = "denied"          # a permission refusal deserves its own type
    COMPACTION = "compaction"
    RUN_END = "run_end"


# Values that must never reach a trace, however the sink is configured.
_REDACT_KEYS = ("password", "token", "api_key", "secret", "authorization")


@dataclass
class Event:
    run_id: str
    turn: int
    type: EventType
    name: str = ""
    input: str = ""
    output: str = ""
    tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    error: str = ""
    at: float = field(default_factory=time.time)


@dataclass
class Tracer:
    """A flat event list. Flat ships to a log pipeline cleanly; the tree is
    reconstructed from turn numbers when a human needs to read it."""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    events: list[Event] = field(default_factory=list)
    truncate_at: int = 2_000

    def record(self, turn: int, type: EventType, **kwargs) -> Event:
        for key in ("input", "output", "error"):
            if key in kwargs:
                kwargs[key] = self._clip(_redact(str(kwargs[key])))
        event = Event(run_id=self.run_id, turn=turn, type=type, **kwargs)
        self.events.append(event)
        return event

    def _clip(self, text: str) -> str:
        """Keep head AND tail: the start says what a thing was, the end is
        usually where it failed."""
        if len(text) <= self.truncate_at:
            return text
        half = self.truncate_at // 2
        omitted = len(text) - self.truncate_at
        return f"{text[:half]}\n...[{omitted} chars omitted]...\n{text[-half:]}"

    # ── the summaries you actually look at ───────────────────────────────────

    def cost(self) -> float:
        return round(sum(e.cost_usd for e in self.events), 6)

    def tokens(self) -> int:
        return sum(e.tokens for e in self.events)

    def errors(self) -> list[Event]:
        return [e for e in self.events if e.error]

    def slowest(self, n: int = 3) -> list[Event]:
        return sorted(self.events, key=lambda e: -e.duration_ms)[:n]

    def tool_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.events:
            if e.type is EventType.TOOL_CALL:
                counts[e.name] = counts.get(e.name, 0) + 1
        return counts

    def cost_by_model(self) -> dict[str, float]:
        by: dict[str, float] = {}
        for e in self.events:
            if e.type is EventType.MODEL_CALL:
                by[e.name] = round(by.get(e.name, 0.0) + e.cost_usd, 6)
        return by

    def as_tree(self) -> str:
        """Human-readable. This is what you paste into a bug report."""
        lines = [f"run {self.run_id}  ${self.cost():.4f}  {self.tokens()} tokens"]
        seen_turn = None
        for e in self.events:
            if e.turn != seen_turn:
                seen_turn = e.turn
                lines.append(f"|-- turn {e.turn}")
            mark = "  <-- ERROR" if e.error else ""
            lines.append(
                f"|   |-- {e.type.value:<12} {e.name} "
                f"{e.tokens}tok {e.duration_ms}ms{mark}"
            )
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps([asdict(e) for e in self.events], indent=2, default=str)


def _redact(text: str) -> str:
    """Redact at the tracer, not at the sink -- sinks get misconfigured.

    Handles the shapes a tool call actually logs:

        {"password": "hunter2"}     JSON, space after the colon
        password=hunter2            form encoding
        Authorization: Bearer xyz   a header, value runs to end of line

    An earlier version scanned for the first delimiter after the key, which
    meant a space terminated the match before the value began -- so the key was
    masked and the secret printed anyway. Anything matching a secret key now
    consumes the whole value.
    """
    def mask(match: re.Match) -> str:
        return f"{match.group('key')}{match.group('sep')}[REDACTED]"

    pattern = re.compile(
        # The key, optionally closed by the quote of a JSON field name.
        r"(?P<key>(?:" + "|".join(_REDACT_KEYS) + r")[\"']?)"
        r"(?P<sep>\s*[:=]\s*)"
        # The value: a quoted string, or a bare run up to the next delimiter.
        r"(?P<value>\"[^\"]*\"|'[^']*'|[^,;}\n]+)",
        re.IGNORECASE,
    )
    return pattern.sub(mask, text)
