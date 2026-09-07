# Harness Engineering — Module 2
# Topic: Termination and Budgets

> **F1 — non-termination.** The most common agent bug and the most expensive.
> A loop with no budget is an open credit line.

---

## 1. Intuition

You ship an agent on Friday. On Monday the bill is $3,000. Nothing was hacked;
one run got stuck retrying a tool that always failed, at four calls a second,
all weekend.

Nobody writes a `while True` in ordinary backend code without an exit. Agents
tempt people to, because the exit *feels* like it exists — the model will decide
to stop. It usually does. "Usually" is not a control.

---

## 2. Core Concept

### The five budgets

You need all five. Each catches something the others miss.

| Budget | Catches | Typical |
|---|---|---|
| **Turns** | Endless tool-calling | 10–25 |
| **Wall clock** | Slow tools, hung network | 60–300 s |
| **Tokens** | Long context, expensive model | 50k–200k |
| **Cost** | The one the business cares about | $0.50–$5 / run |
| **No-progress** | Stuck repetition inside budget | 3 repeats |

Turns alone are not enough: twelve turns of a tool that takes forty seconds is
eight minutes of a held connection. Time alone is not enough: a fast loop burns
tokens long before the clock. Use all five.

### No-progress detection

The subtle one. The agent is inside every budget and getting nowhere:

```
turn 4:  search("refund policy") → no results
turn 5:  search("refund policy") → no results
turn 6:  search("refund policy") → no results
```

Nothing is technically wrong. It will burn the whole budget doing this.

```python
signature = (call.name, json.dumps(call.arguments, sort_keys=True))
self._seen[signature] = self._seen.get(signature, 0) + 1
if self._seen[signature] >= 3:
    return StopReason.NO_PROGRESS
```

Identical calls are the reliable signal. *Similar* calls are tempting to catch
too — resist it, because legitimate work often looks similar (reading twenty
files in a directory is twenty near-identical calls).

### Budgets are not a substitute for correctness

A budget stops the bleeding; it does not fix the wound. If your `NO_PROGRESS`
rate is 20%, the answer is better tools or clearer prompts, not a bigger budget.
Watch that number.

---

## 3. Minimal Implementation

```python
import json, time
from dataclasses import dataclass, field
from enum import Enum


class StopReason(str, Enum):
    COMPLETED = "completed"
    TURN_BUDGET = "turn_budget"
    TIME_BUDGET = "time_budget"
    TOKEN_BUDGET = "token_budget"
    COST_BUDGET = "cost_budget"
    NO_PROGRESS = "no_progress"
    CANCELLED = "cancelled"


@dataclass
class Budget:
    """Every limit in one object, so a run's ceiling is visible in one place."""

    max_turns: int = 15
    max_seconds: float = 180.0
    max_tokens: int = 100_000
    max_cost_usd: float = 1.00
    repeat_limit: int = 3

    turns: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    started_at: float = field(default_factory=time.monotonic)
    _seen: dict[str, int] = field(default_factory=dict)

    def check(self) -> StopReason | None:
        """Called at the top of every turn. Cheap, pure, one place."""
        if self.turns >= self.max_turns:
            return StopReason.TURN_BUDGET
        if time.monotonic() - self.started_at > self.max_seconds:
            return StopReason.TIME_BUDGET
        if self.tokens >= self.max_tokens:
            return StopReason.TOKEN_BUDGET
        if self.cost_usd >= self.max_cost_usd:
            return StopReason.COST_BUDGET
        return None

    def record_turn(self, tokens: int, cost_usd: float) -> None:
        self.turns += 1
        self.tokens += tokens
        self.cost_usd += cost_usd

    def note_calls(self, calls: list) -> StopReason | None:
        """Identical calls repeated is stuck, not working."""
        signature = json.dumps(
            sorted((c["name"], json.dumps(c.get("arguments", {}), sort_keys=True))
                   for c in calls)
        )
        self._seen[signature] = self._seen.get(signature, 0) + 1
        if self._seen[signature] >= self.repeat_limit:
            return StopReason.NO_PROGRESS
        return None

    @property
    def remaining_turns(self) -> int:
        return max(0, self.max_turns - self.turns)
```

### Telling the model it is running out

A budget the model knows about is a budget it can plan around:

```python
if budget.remaining_turns <= 2:
    messages.append(system(
        f"You have {budget.remaining_turns} turns left. "
        "Finish with your best answer now, and say what is still uncertain."
    ))
```

This measurably improves the quality of budget-exhausted runs — you get a
summary of findings instead of a hard cut mid-search.

---

## 4. What To Return When A Budget Trips

Not an exception. A labelled, partial result:

```python
return RunResult(
    output=last_useful_content(state) or "No answer was produced.",
    stop_reason=reason,
    complete=False,                     # never claim success
    partial_work=state.artefacts,
    turns=budget.turns,
    cost_usd=budget.cost_usd,
)
```

Three rules:

- **Never report success.** `complete=False` should be structural, not a comment.
- **Return what you have.** Half a research summary has value.
- **Say which budget tripped.** "Stopped after 15 turns" is actionable in a way
  that "an error occurred" is not.

---

## 5. Trade-offs

**Tight vs. loose budgets.** Tight budgets cut off legitimate long work and make
users distrust the agent. Loose budgets are expensive and slow to reveal bugs.
Set them from the *observed distribution* — if p95 is 6 turns, 15 is generous
and 100 is negligent.

**Cost budget accuracy.** Exact per-call cost needs a pricing table you must
maintain as models change. An approximation from token counts is usually fine —
you are catching runaway runs, not doing accounting.

**Hard stop vs. graceful wind-down.** The warning message above costs an extra
turn. Worth it for user-facing runs; skip it for batch jobs where nobody reads
the output immediately.

---

## 6. Production Notes

- **Alert on the `stop_reason` distribution, not on individual runs.** One
  budget stop is normal. Ten percent of runs stopping on budget is a bug.
- **Log the full transcript on any non-`COMPLETED` stop.** That is exactly when
  you need it, and exactly when it is easiest to forget.
- **Cancellation must be checked before the model call**, not after — otherwise
  clicking stop still costs a full call.
- **Budgets belong to the run, not the user.** Tie them to `run_id`.
- Keep `check()` **pure and fast**. It runs on every turn; a database call in
  there is a latency bug waiting to happen.

---

## 7. What To Say Out Loud

> "I run five budgets: turns, wall clock, tokens, cost, and no-progress
> detection. Each catches something the others miss — twelve turns of a
> forty-second tool blows the clock without touching the turn budget. The
> subtle one is no-progress: identical repeated calls mean the agent is stuck
> even though every budget is fine. When a budget trips I return partial work
> clearly labelled incomplete rather than raising, and I warn the model when it
> has two turns left, which turns a hard cut into a summary. And I watch the
> stop-reason distribution — if ten percent of runs are hitting budgets, that is
> a correctness problem, not a budget problem."

---

## 8. Check Yourself

1. Why are turn budgets alone insufficient?
2. What is no-progress detection, and why only *identical* calls?
3. Your `NO_PROGRESS` rate is 20%. Raise the budget or fix something else?
4. Why check cancellation before the model call rather than after?

→ Next: [`retry-backoff-and-idempotency.md`](retry-backoff-and-idempotency.md)
