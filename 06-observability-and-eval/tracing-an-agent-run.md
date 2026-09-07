# Harness Engineering — Module 6
# Topic: Tracing An Agent Run

> **F7 (silent failure) and F8 (non-reproducibility).** You cannot fix what you
> cannot see, and you cannot see an agent from its final answer.

---

## 1. Intuition

A user says "it gave me the wrong answer". You open your logs and find one line:

```
INFO  agent completed in 34s
```

That tells you nothing. The agent made eleven model calls and nineteen tool
calls. One of them was wrong. Which one?

Agent debugging is archaeology. You are reconstructing a decision sequence from
whatever you thought to record at the time. Record too little and the bug is
unfixable — not hard, **unfixable**, because you cannot reproduce it.

---

## 2. Core Concept

### The unit is the run, not the request

An ordinary web request is one span. An agent run is a **tree**:

```
run  a7f3
├── turn 1
│   ├── model call      1,240 tok    1.2s   $0.004
│   └── tool: search    "refund policy"  →  3 results   0.3s
├── turn 2
│   ├── model call      2,890 tok    2.1s   $0.009
│   ├── tool: read_doc  doc_17  →  4,200 chars          0.1s
│   └── tool: read_doc  doc_92  →  ERROR not found      0.1s   ← the bug
└── turn 3
    └── model call      3,100 tok    1.8s   $0.011  → final answer
```

Reading that tree, the bug is obvious in three seconds. Without it you are
guessing.

### What to record, per event

| Field | Why you will need it |
|---|---|
| `run_id` | Ties every line together. Non-negotiable. |
| `turn` | Where in the sequence |
| `type` | model call / tool call / decision / stop |
| `name` | Which tool, which model |
| `input` | Truncated, but present |
| `output` | Truncated, but present |
| `tokens`, `cost` | Where the money went |
| `duration_ms` | Where the time went |
| `error` | Full text, never swallowed |

### The one non-negotiable

**Persist the full message list on any non-successful run.** Not a summary — the
actual array. It is the only thing that makes a run reproducible, and it is the
thing everyone forgets until the first unfixable bug.

Storage is cheap. An unreproducible production bug is not.

---

## 3. Minimal Implementation

```python
import json, time, uuid
from dataclasses import dataclass, field, asdict
from enum import Enum


class EventType(str, Enum):
    RUN_START = "run_start"
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    DENIED = "denied"          # permission refusal -- always worth its own type
    COMPACTION = "compaction"
    RUN_END = "run_end"


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
    """Records a run as a flat event list. Flat, not nested: easier to ship to
    a log pipeline, and the tree can be reconstructed from turn numbers."""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    events: list[Event] = field(default_factory=list)
    truncate_at: int = 2_000

    def record(self, **kwargs) -> Event:
        for key in ("input", "output"):
            if key in kwargs:
                kwargs[key] = self._clip(str(kwargs[key]))
        event = Event(run_id=self.run_id, **kwargs)
        self.events.append(event)
        return event

    def _clip(self, text: str) -> str:
        if len(text) <= self.truncate_at:
            return text
        half = self.truncate_at // 2
        omitted = len(text) - self.truncate_at
        return f"{text[:half]}\n...[{omitted} chars omitted]...\n{text[-half:]}"

    # ── summaries you will actually look at ──────────────────────────────────

    def cost(self) -> float:
        return round(sum(e.cost_usd for e in self.events), 4)

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

    def as_tree(self) -> str:
        """Human-readable. This is what you paste into a bug report."""
        lines = [f"run {self.run_id}  ${self.cost():.4f}"]
        current = -1
        for e in self.events:
            if e.turn != current:
                current = e.turn
                lines.append(f"├── turn {e.turn}")
            mark = "  ← ERROR" if e.error else ""
            detail = f"{e.name} {e.tokens}tok {e.duration_ms}ms{mark}"
            lines.append(f"│   ├── {e.type.value:12} {detail}")
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps([asdict(e) for e in self.events], indent=2, default=str)
```

### Truncating from both ends

Note `_clip` keeps the **head and tail**. A file's first lines tell you what it
is; the last lines are usually where the error appeared. Cutting only the tail
throws away half the evidence.

---

## 4. Cost And Time Attribution

Two questions you will be asked, repeatedly:

**"Why did this run cost $2?"**

```python
by_model = {}
for e in tracer.events:
    if e.type is EventType.MODEL_CALL:
        by_model[e.name] = by_model.get(e.name, 0) + e.cost_usd
```

Usually one of two answers: too many turns, or context that grew and was never
compacted.

**"Why did it take 90 seconds?"**

```python
tracer.slowest(3)
```

Usually one slow tool called repeatedly. `tool_counts()` finds it in one line.

---

## 5. Trade-offs

**Verbosity vs. volume.** Recording every full message is complete and expensive
at scale. A sensible split: truncate in the hot path, persist the full
transcript only for runs that did not complete successfully.

**Sync vs. async writing.** Writing traces inline adds latency to every turn.
Buffer in memory, flush at run end — and flush on error too, or you lose exactly
the traces you need.

**Sampling.** Tracing 1% is standard for high-volume services. For agents, trace
**100% of failures and 1% of successes**. The failures are the whole point.

---

## 6. Production Notes

- **`run_id` in every log line.** One habit, enormous payoff. Generate it at
  turn zero and thread it everywhere, including into tool implementations.
- **Redact at the tracer**, not at the log sink. Passwords and tokens should
  never enter the event, because sinks get misconfigured.
- **Alert on distributions, not events.** "Cost per run p95 doubled" is a signal;
  "one run cost $2" is noise.
- **Keep traces for failed runs longer** than successful ones. Thirty days for
  failures, one day for successes, is a reasonable default.
- **Make the tree printable.** When a colleague asks what went wrong, pasting
  `as_tree()` into a message is worth more than a dashboard link.

---

## 7. What To Say Out Loud

> "An agent run is a tree, not a request, so I trace it as one: every model
> call, tool call, permission denial and compaction, each with tokens, cost and
> duration, all tied together by a run_id that appears in every log line. The
> non-negotiable is persisting the full message list on any run that did not
> complete — a summary is not enough, because without the exact context you
> cannot reproduce the bug, and an agent bug you cannot reproduce is effectively
> unfixable. I truncate long values from both ends, because the start tells you
> what a thing was and the end is usually where it failed. And I sample the
> inverse of a normal service: a hundred percent of failures, a small fraction
> of successes."

---

## 8. Check Yourself

1. Why is one log line at the end of a run useless?
2. What is the one thing you must persist on a failed run, and why?
3. Why truncate from both ends rather than just the tail?
4. Why trace 100% of failures but only 1% of successes?

→ Next: [`metrics-that-matter.md`](metrics-that-matter.md)
