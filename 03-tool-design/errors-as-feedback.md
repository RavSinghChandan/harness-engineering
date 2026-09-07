# Harness Engineering — Module 3
# Topic: Errors As Feedback

---

## 1. Intuition

In ordinary software, an error ends things. Something threw, the caller unwinds,
a human reads the stack trace tomorrow.

In an agent, an error is a **turn in a conversation**. The model is still there,
still holding the whole task, and it will read whatever you hand back. Give it a
stack trace and it learns nothing. Give it a sentence explaining what was wrong
and what to do instead, and it usually fixes itself on the next turn.

This is the single highest-leverage habit in tool design. It converts a class
of hard failures into self-healing ones, for the cost of writing better strings.

---

## 2. Core Concept

### The anatomy of a useful error

Four parts, in this order:

```
1. WHAT failed        "search_orders failed"
2. WHY                "'status' must be one of pending, shipped, delivered, cancelled"
3. WHAT WAS GIVEN     "got 'in-transit'"
4. WHAT TO DO         "Use 'shipped' for orders on their way."
```

Part 4 is the one people skip, and it is the one that makes the difference.

### Three grades of the same failure

```python
# GRADE F — the model learns nothing and will repeat the mistake.
"Error"
"Invalid input"
"KeyError: 'status'"

# GRADE C — it knows something is wrong, not what to do.
"Error: invalid status value 'in-transit'"

# GRADE A — it can fix this on the next turn without help.
"Error: search_orders: 'status' must be one of "
"['pending', 'shipped', 'delivered', 'cancelled']; got 'in-transit'. "
"Use 'shipped' for orders on their way to the customer."
```

The grade-A message costs you thirty seconds to write and saves an entire class
of retry loop.

### Retryable vs. terminal

Not every error should invite another attempt. Tell the model which is which:

| Kind | Example | Model should |
|---|---|---|
| **Retryable — fix the call** | Bad enum value, missing argument | Try again, corrected |
| **Retryable — transient** | Timeout, 503, rate limit | Wait and try again |
| **Terminal — no such thing** | Order ID does not exist | Stop; tell the user |
| **Terminal — refused** | Permission denied | Stop; explain why |

Getting this wrong is expensive in both directions. A terminal error the model
thinks is retryable produces a loop hammering a wall. A retryable error marked
terminal gives up on work that would have succeeded.

```python
"Error: order ORD-99 does not exist. Do not retry; "
"ask the user to confirm the order number."
```

That last clause — *do not retry* — is worth its tokens.

---

## 3. Minimal Implementation

```python
from dataclasses import dataclass
from enum import Enum


class ErrorKind(str, Enum):
    FIX_AND_RETRY = "fix_and_retry"     # the call was wrong; correct it
    WAIT_AND_RETRY = "wait_and_retry"   # transient; the same call may work
    TERMINAL = "terminal"               # do not retry; explain to the user


@dataclass(frozen=True)
class ToolError(Exception):
    """An error written for a reader who will act on it."""

    tool: str
    problem: str                 # what was wrong
    received: str = ""           # what we actually got
    suggestion: str = ""         # what to do instead
    kind: ErrorKind = ErrorKind.FIX_AND_RETRY

    def as_message(self) -> str:
        parts = [f"Error in {self.tool}: {self.problem}"]
        if self.received:
            parts.append(f"Received: {self.received}.")
        if self.suggestion:
            parts.append(self.suggestion)
        if self.kind is ErrorKind.TERMINAL:
            parts.append("Do not retry this call; explain the situation to the user.")
        elif self.kind is ErrorKind.WAIT_AND_RETRY:
            parts.append("This is temporary; the same call may succeed shortly.")
        return " ".join(parts)


VALID_STATUS = ("pending", "shipped", "delivered", "cancelled")


def search_orders(query: str, status: str = "pending") -> str:
    if status not in VALID_STATUS:
        raise ToolError(
            tool="search_orders",
            problem=f"'status' must be one of {list(VALID_STATUS)}",
            received=repr(status),
            suggestion="Use 'shipped' for orders on their way to the customer.",
            kind=ErrorKind.FIX_AND_RETRY,
        )
    ...
```

And in the loop — the error becomes a message, never an exception that escapes:

```python
try:
    result = tool.run(**args)
except ToolError as err:
    result = err.as_message()          # the model reads this and corrects
except Exception as exc:
    # Unexpected. Still do not crash the run, but log it loudly for a human.
    logger.exception("tool %s raised", name)
    result = f"Error in {name}: {type(exc).__name__}: {exc}"

messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
```

Note the two `except` clauses. `ToolError` is *expected* — a normal part of the
conversation. Anything else is a bug in your code, so it gets logged with a
stack trace for you, and a plain sentence for the model.

---

## 4. The Loop Risk

Helpful errors create a new failure: the model retries forever on something it
cannot fix.

Guard it in the harness, not the prompt:

```python
repeats = self._error_counts[(call.name, err.problem)] = (
    self._error_counts.get((call.name, err.problem), 0) + 1
)
if repeats >= 3:
    return (
        f"Error in {call.name}: {err.problem}. "
        "This has now failed three times with the same problem. "
        "Stop calling this tool and explain the situation to the user."
    )
```

Same error, three times, is not a retry — it is a loop. Say so explicitly.

---

## 5. Trade-offs

**Verbose errors cost tokens.** A long message on every failure adds up on a
long run. Worth it: one avoided retry pays for many characters.

**Too helpful leaks.** `"Error: user 4471 has no admin role"` tells the model —
and anything reading the transcript — about your permission model. Keep internal
detail out of messages that reach untrusted contexts.

**Suggestions can mislead.** A wrong suggestion is worse than none, because the
model will confidently follow it. Only suggest when you are sure.

---

## 6. Production Notes

- **Count errors by `(tool, problem)`.** The top row of that table is your next
  schema fix, every time.
- **Never leak stack traces to the model.** They are enormous, full of internal
  paths, and contain nothing the model can act on. Log them for yourself.
- **Test the error path.** Most teams test that tools succeed. Assert that a bad
  call produces a message containing the valid options — that is the behaviour
  you actually depend on.
- Keep messages **stable**. If your error text changes every release, cached
  prompts and saved transcripts drift.

---

## 7. What To Say Out Loud

> "In an agent, an error is a turn in a conversation, not the end of one. So
> every tool error says four things: what failed, why, what it received, and
> what to do instead. I also tag the error as fix-and-retry, wait-and-retry, or
> terminal, because a terminal error the model thinks is retryable turns into a
> loop hammering a wall. Errors go back as tool messages so the model can
> correct itself, and I count them by tool and problem — the most frequent pair
> is always my next schema fix. The one guard you need is a repeat limit, or
> helpful errors become an infinite retry."

---

## 8. Check Yourself

1. Why is `"Invalid input"` close to useless to a model?
2. What are the four parts of a good tool error?
3. What breaks if you mark a terminal error as retryable? And the reverse?
4. Why log stack traces but never send them to the model?

→ Next: [`tool-selection-and-routing.md`](tool-selection-and-routing.md)
