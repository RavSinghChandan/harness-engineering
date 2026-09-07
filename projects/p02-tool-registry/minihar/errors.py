"""Errors written for a reader who will act on them.

In an agent an error is a turn in a conversation, not the end of one. The model
is still there holding the task; give it something it can use.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorKind(str, Enum):
    FIX_AND_RETRY = "fix_and_retry"      # the call was malformed; correct it
    WAIT_AND_RETRY = "wait_and_retry"    # transient; the same call may work
    TERMINAL = "terminal"                # do not retry; explain to the user


@dataclass(frozen=True)
class ToolError(Exception):
    """Four parts: what failed, why, what we got, what to do instead."""

    tool: str
    problem: str
    received: str = ""
    suggestion: str = ""
    kind: ErrorKind = ErrorKind.FIX_AND_RETRY

    def as_message(self) -> str:
        parts = [f"Error in {self.tool}: {self.problem}."]
        if self.received:
            parts.append(f"Received: {self.received}.")
        if self.suggestion:
            parts.append(self.suggestion)
        if self.kind is ErrorKind.TERMINAL:
            parts.append("Do not retry this call; explain the situation to the user.")
        elif self.kind is ErrorKind.WAIT_AND_RETRY:
            parts.append("This is temporary; the same call may succeed shortly.")
        return " ".join(parts)
