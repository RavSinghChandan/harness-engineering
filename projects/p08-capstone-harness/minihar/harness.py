"""The complete harness.

Nine steps per turn, eight of them ours:

    assemble -> budget -> call -> DECIDE -> validate -> authorise
             -> execute -> observe -> loop
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .policy import Effect, Mode, Policy
from .tools import ToolRegistry
from .tracing import EventType, Tracer


class StopReason(str, Enum):
    COMPLETED = "completed"
    TURN_BUDGET = "turn_budget"
    TIME_BUDGET = "time_budget"
    TOKEN_BUDGET = "token_budget"
    COST_BUDGET = "cost_budget"
    NO_PROGRESS = "no_progress"
    CANCELLED = "cancelled"


@dataclass
class RunResult:
    output: str
    stop_reason: StopReason
    turns: int
    messages: list[dict[str, Any]]
    tracer: Tracer
    cost_usd: float = 0.0
    tokens: int = 0

    @property
    def ok(self) -> bool:
        """Only completion is success. Never claim a budget stop worked."""
        return self.stop_reason is StopReason.COMPLETED


@dataclass
class Harness:
    """Every guard from P01-P07 in one loop."""

    model: Callable[[list[dict]], dict]
    tools: ToolRegistry
    system_prompt: str = "You are a careful assistant."

    max_turns: int = 15
    max_seconds: float = 180.0
    max_tokens: int = 100_000
    max_cost_usd: float = 1.00
    repeat_limit: int = 3

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    cancelled: bool = False

    def run(self, task: str) -> RunResult:
        tracer = Tracer(run_id=self.run_id)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},   # cacheable prefix
            {"role": "user", "content": task},
        ]
        started = time.monotonic()
        turn = tokens = 0
        cost = 0.0
        seen: dict[str, int] = {}

        tracer.record(0, EventType.RUN_START, name="run", input=task)

        while True:
            stop = self._should_stop(turn, started, tokens, cost)
            if stop:
                return self._finish(stop, turn, messages, tracer, cost, tokens)

            turn += 1
            began = time.monotonic()
            reply = self.model(messages)
            messages.append(reply)

            used = int(reply.get("tokens", 0))
            spent = float(reply.get("cost_usd", 0.0))
            tokens += used
            cost += spent
            tracer.record(
                turn, EventType.MODEL_CALL, name=reply.get("model", "model"),
                tokens=used, cost_usd=spent,
                duration_ms=int((time.monotonic() - began) * 1000),
            )

            calls = reply.get("tool_calls") or []
            if not calls:                                  # the natural exit
                return self._finish(
                    StopReason.COMPLETED, turn, messages, tracer, cost, tokens,
                    output=reply.get("content", ""),
                )

            signature = repr(sorted(
                (c["name"], repr(c.get("arguments"))) for c in calls
            ))
            seen[signature] = seen.get(signature, 0) + 1
            if seen[signature] >= self.repeat_limit:
                return self._finish(
                    StopReason.NO_PROGRESS, turn, messages, tracer, cost, tokens
                )

            for call in calls:
                began = time.monotonic()
                result = self.tools.execute(call["name"], call.get("arguments"))
                kind = (
                    EventType.DENIED if result.startswith("Denied:")
                    else EventType.TOOL_CALL
                )
                tracer.record(
                    turn, kind, name=call["name"],
                    input=str(call.get("arguments", "")),
                    output=result,
                    error=result if result.startswith("Error") else "",
                    duration_ms=int((time.monotonic() - began) * 1000),
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "name": call["name"],
                    "content": result,
                })

    def _should_stop(
        self, turn: int, started: float, tokens: int, cost: float
    ) -> StopReason | None:
        """Every guard in one place. Scattered guards grow a path that skips one."""
        if self.cancelled:                                  # checked BEFORE the call
            return StopReason.CANCELLED
        if turn >= self.max_turns:
            return StopReason.TURN_BUDGET
        if time.monotonic() - started > self.max_seconds:
            return StopReason.TIME_BUDGET
        if tokens >= self.max_tokens:
            return StopReason.TOKEN_BUDGET
        if cost >= self.max_cost_usd:
            return StopReason.COST_BUDGET
        return None

    def _finish(
        self, reason: StopReason, turn: int, messages: list[dict],
        tracer: Tracer, cost: float, tokens: int, output: str = "",
    ) -> RunResult:
        if not output:
            output = f"Stopped early: {reason.value}."
        tracer.record(turn, EventType.RUN_END, name=reason.value, output=output)
        return RunResult(
            output=output, stop_reason=reason, turns=turn,
            messages=messages, tracer=tracer, cost_usd=round(cost, 6),
            tokens=tokens,
        )
