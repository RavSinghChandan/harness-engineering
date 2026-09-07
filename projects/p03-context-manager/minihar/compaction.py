"""Compaction: replace old detail with a summary that keeps what matters.

Truncation silently deletes the brief and looks like the model getting dumber.
Compaction is lossy too, but it loses the right things on purpose.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .context import rough_tokens

COMPACT_PROMPT = """Summarise this portion of an agent's working session.

You MUST preserve, in full:
- the original task and every constraint given
- decisions made and the reason for each
- facts discovered, with their source
- what was tried and failed, and why
- questions still open

You may compress: full file contents, tool output detail, and reasoning that
led to a stated conclusion.

Write plain prose, third person, under 500 words. Add nothing that is not in
the transcript."""


@dataclass
class Compactor:
    """Compacts the middle of a transcript, protecting both ends."""

    model: Callable[[list[dict]], str]
    count_tokens: Callable[[str], int] = rough_tokens
    keep_recent: int = 4          # newest turns stay verbatim
    keep_head: int = 2            # system prompt + original task, never touched
    trigger_ratio: float = 0.75   # compact before the window is full
    compactions: int = 0
    log: list[dict] = field(default_factory=list)

    def needs_compaction(self, messages: list[dict], usable: int) -> bool:
        """Trigger early: compaction itself needs room to run."""
        return self._size(messages) > usable * self.trigger_ratio

    def compact(self, messages: list[dict]) -> list[dict]:
        head = messages[: self.keep_head]
        recent = messages[-self.keep_recent :] if self.keep_recent else []
        middle = messages[self.keep_head : len(messages) - len(recent)]

        if len(middle) < 3:
            return messages           # not enough to be worth a model call

        before = self._size(messages)
        transcript = "\n\n".join(f"[{m['role']}] {m['content']}" for m in middle)
        summary = self.model([
            {"role": "system", "content": COMPACT_PROMPT},
            {"role": "user", "content": transcript},
        ])

        compacted = [
            *head,
            {
                "role": "system",
                "content": f"Summary of earlier work in this session:\n{summary}",
            },
            *recent,
        ]

        self.compactions += 1
        self.log.append({
            "compaction": self.compactions,
            "messages_before": len(messages),
            "messages_after": len(compacted),
            "tokens_before": before,
            "tokens_after": self._size(compacted),
            "summary": summary,          # keep it: needed when the agent "forgets"
        })
        return compacted

    def _size(self, messages: list[dict]) -> int:
        return sum(self.count_tokens(m["content"]) for m in messages)
