"""The agent turn loop.

The loop is the heart of a harness: call the model, run whatever tools it asks
for, feed the results back, repeat -- and stop, always, for a reason you can
name.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol


class StopReason(str, Enum):
    """Why a run ended. Every run ends with exactly one of these."""

    COMPLETED = "completed"          # the model answered with no tool calls
    TURN_BUDGET = "turn_budget"      # too many turns
    TIME_BUDGET = "time_budget"      # wall clock exceeded
    NO_PROGRESS = "no_progress"      # the model repeated itself


class Model(Protocol):
    """Anything that maps a message list to an assistant message."""

    def __call__(self, messages: list[dict[str, Any]]) -> dict[str, Any]: ...


@dataclass
class TurnResult:
    """What a finished run leaves behind."""

    output: str
    stop_reason: StopReason
    turns: int
    messages: list[dict[str, Any]]
    elapsed_s: float

    @property
    def ok(self) -> bool:
        return self.stop_reason is StopReason.COMPLETED


@dataclass
class Harness:
    """A loop that always terminates.

    The budgets are not optimisations. They are the difference between a bug
    that costs a retry and a bug that costs a weekend of API spend.
    """

    model: Model
    tools: dict[str, Callable[..., Any]] = field(default_factory=dict)
    max_turns: int = 12
    max_seconds: float = 120.0
    repeat_limit: int = 3

    def run(self, task: str) -> TurnResult:
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
        started = time.monotonic()
        seen: dict[str, int] = {}

        for turn in range(1, self.max_turns + 1):
            if time.monotonic() - started > self.max_seconds:
                return self._stop(StopReason.TIME_BUDGET, turn - 1, messages, started)

            reply = self.model(messages)
            messages.append(reply)

            calls = reply.get("tool_calls") or []
            if not calls:
                return TurnResult(
                    output=reply.get("content", ""),
                    stop_reason=StopReason.COMPLETED,
                    turns=turn,
                    messages=messages,
                    elapsed_s=time.monotonic() - started,
                )

            # A model that asks for the same thing over and over is stuck. Catch
            # it here rather than letting it burn the whole turn budget.
            signature = repr(sorted((c["name"], repr(c.get("arguments"))) for c in calls))
            seen[signature] = seen.get(signature, 0) + 1
            if seen[signature] >= self.repeat_limit:
                return self._stop(StopReason.NO_PROGRESS, turn, messages, started)

            for call in calls:
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "name": call["name"],
                    "content": self._invoke(call),
                })

        return self._stop(StopReason.TURN_BUDGET, self.max_turns, messages, started)

    def _invoke(self, call: dict[str, Any]) -> str:
        """Run one tool. Never raises -- errors come back as text the model reads."""
        fn = self.tools.get(call["name"])
        if fn is None:
            available = ", ".join(sorted(self.tools)) or "none"
            return f"Error: unknown tool {call['name']!r}. Available: {available}."
        try:
            return str(fn(**(call.get("arguments") or {})))
        except TypeError as exc:
            return f"Error: wrong arguments for {call['name']!r}: {exc}"
        except Exception as exc:
            return f"Error: {type(exc).__name__}: {exc}"

    def _stop(
        self,
        reason: StopReason,
        turns: int,
        messages: list[dict[str, Any]],
        started: float,
    ) -> TurnResult:
        return TurnResult(
            output=f"Stopped early: {reason.value}.",
            stop_reason=reason,
            turns=turns,
            messages=messages,
            elapsed_s=time.monotonic() - started,
        )
