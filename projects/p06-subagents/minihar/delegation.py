"""Delegation with contracts.

A subagent never asks a clarifying question. It proceeds confidently on its
interpretation, so the contract has to carry everything and the return shape has
to be too specific to fudge.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Contract:
    """A delegation written so it cannot be interpreted loosely."""

    goal: str
    context: str = ""
    constraints: tuple[str, ...] = ()
    returns: dict[str, str] = field(default_factory=dict)
    max_turns: int = 8
    tools: tuple[str, ...] = ()

    def as_prompt(self) -> str:
        parts = [f"GOAL: {self.goal}"]
        if self.context:
            parts.append(f"CONTEXT: {self.context}")
        if self.constraints:
            parts.append(
                "CONSTRAINTS:\n" + "\n".join(f"- {c}" for c in self.constraints)
            )
        if self.returns:
            parts.append(
                "RETURN exactly this JSON shape and nothing else:\n"
                + json.dumps(self.returns, indent=2)
            )
        parts.append(
            f"You have {self.max_turns} turns. If you cannot complete the goal, "
            'return the shape with confidence "low" and say what is missing.'
        )
        return "\n\n".join(parts)


@dataclass
class DelegationResult:
    """One consistent thing for the supervisor to check."""

    data: dict[str, Any]
    confidence: str = "high"
    error: str = ""
    raw: str = ""

    @property
    def usable(self) -> bool:
        return not self.error and self.confidence != "low"


@dataclass
class Delegator:
    """Spawns subagents under hard caps.

    A delegation loop without caps is F1 with a multiplier -- a fork bomb.
    """

    build_subagent: Callable[..., Any]
    max_subagents: int = 5
    max_depth: int = 2
    spawned: int = 0
    log: list[dict[str, Any]] = field(default_factory=list)

    def run(self, contract: Contract, depth: int = 0) -> DelegationResult:
        if depth >= self.max_depth:
            return DelegationResult({}, "low", "delegation depth limit reached")
        if self.spawned >= self.max_subagents:
            return DelegationResult({}, "low", "subagent limit reached")

        self.spawned += 1
        sub = self.build_subagent(
            tools=contract.tools,          # strictly fewer than the parent holds
            max_turns=contract.max_turns,
        )
        output = sub.run(contract.as_prompt())
        result = self._parse(str(output), contract)

        # Log both sides: drift is only visible when you can compare them.
        self.log.append({
            "goal": contract.goal,
            "returned": result.data,
            "confidence": result.confidence,
            "error": result.error,
        })
        return result

    def _parse(self, output: str, contract: Contract) -> DelegationResult:
        if not contract.returns:
            return DelegationResult({"output": output})

        try:
            start, end = output.index("{"), output.rindex("}") + 1
            parsed = json.loads(output[start:end])
        except (ValueError, json.JSONDecodeError):
            return DelegationResult(
                {}, "low", "subagent did not return the agreed shape", output[:500]
            )

        missing = sorted(set(contract.returns) - set(parsed))
        if missing:
            return DelegationResult(
                parsed, "low", f"missing keys: {missing}", output[:500]
            )

        return DelegationResult(parsed, str(parsed.get("confidence", "high")))
