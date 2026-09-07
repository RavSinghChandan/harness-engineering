"""Authority control.

Validation asks "is this well-formed?". Authorisation asks "is this allowed?".
They are different questions with different consequences, so they live apart:
a validation error should be retried, a denial should be explained.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class Effect(str, Enum):
    """What a tool does to the world. Policy keys off this, not off names."""

    READ = "read"              # safe, reversible, no side effects
    WRITE = "write"            # changes state, usually recoverable
    DESTRUCTIVE = "destroy"    # irreversible: delete, send, refund, deploy


class Mode(str, Enum):
    """How much the operator trusts this session."""

    READ_ONLY = "read_only"     # reads only
    ASK_FIRST = "ask_first"     # confirm every change (the sane default)
    AUTONOMOUS = "autonomous"   # writes flow; destruction still confirms


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: str = ""
    asked: bool = False        # did we put a question to a human?


# A confirmer receives the tool name and arguments and returns the human answer.
Confirmer = Callable[[str, dict], bool]


def _deny_everything(name: str, args: dict) -> bool:
    """Safe default: if no confirmer is wired up, nothing is confirmed."""
    return False


@dataclass
class Policy:
    """Default-deny authority control.

    Invariants worth stating out loud, because they are the whole point:

      * An unknown tool is denied, never permitted.
      * Reads are always allowed, which keeps strict modes usable.
      * DESTRUCTIVE always asks a human -- in every mode. There is no
        configuration in which this agent deletes silently.
    """

    mode: Mode = Mode.ASK_FIRST
    allowed_tools: frozenset[str] | None = None      # None => any registered tool
    confirm: Confirmer = _deny_everything
    denials: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.denials is None:
            self.denials = []

    def check(self, name: str, effect: Effect, args: dict | None = None) -> Verdict:
        args = args or {}
        verdict = self._decide(name, effect, args)
        if not verdict.allowed:
            self.denials.append(f"{name}: {verdict.reason}")
        return verdict

    def _decide(self, name: str, effect: Effect, args: dict) -> Verdict:
        # 1. Allow-list. Not named, not run.
        if self.allowed_tools is not None and name not in self.allowed_tools:
            return Verdict(False, f"Tool {name!r} is not permitted in this session.")

        # 2. Reads are free. Without this, strict modes get switched off.
        if effect is Effect.READ:
            return Verdict(True)

        # 3. Read-only sessions refuse every change.
        if self.mode is Mode.READ_ONLY:
            return Verdict(False, f"{name!r} changes state; this session is read-only.")

        # 4. Destruction always asks. Writes ask unless we are autonomous.
        must_ask = effect is Effect.DESTRUCTIVE or self.mode is Mode.ASK_FIRST
        if must_ask:
            if not self.confirm(name, args):
                return Verdict(False, "The user declined this action.", asked=True)
            return Verdict(True, asked=True)

        return Verdict(True)
