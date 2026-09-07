# Harness Engineering — Module 1
# Topic: What Is a Harness

---

## 1. Intuition

You have an LLM API key. You write a script that sends a prompt and prints the
reply. That is not a product — it is a demo.

The distance between that demo and something you would let a customer touch is
almost entirely **non-model code**: deciding when to call the model again,
giving it tools, stopping it when it loops, keeping its context inside the
window, refusing the dangerous action, and recording what happened.

That code is the harness. In a mature agent product it is 90% of the codebase
and 100% of the incidents.

---

## 2. Core Concept

### The three layers

```
┌─────────────────────────────────────────────┐
│  PROMPT          what you say in one call   │  ← prompt engineering
├─────────────────────────────────────────────┤
│  CONTEXT         what the model can see     │  ← context engineering
├─────────────────────────────────────────────┤
│  HARNESS         everything around the call │  ← harness engineering
│                                             │
│   loop · tools · permissions · memory       │
│   budgets · retries · traces · state        │
└─────────────────────────────────────────────┘
```

Each layer assumes the one above it is solved. A perfect prompt inside a broken
loop still burns $400 overnight.

### Formal definition

> A **harness** is the deterministic system that surrounds a non-deterministic
> model: it decides *when* the model runs, *what* it can see, *what* it can do,
> *when it must stop*, and *what evidence remains afterwards*.

The key word is **deterministic**. The model is a sampler; you cannot make it
reliable. You can make everything around it reliable, and constrain the model
until the combined system is trustworthy.

### The minimum viable harness

Five responsibilities. Anything less is a script:

1. **Loop control** — call the model, act, call again, and *stop*
2. **Tool dispatch** — map a model's request to real code, safely
3. **Context management** — keep the input inside the window and relevant
4. **Authority control** — bound what the agent may do without asking
5. **Observability** — leave a trace you can read tomorrow

---

## 3. Minimal Implementation

The whole idea in 40 lines. Everything else in this repo is hardening this.

```python
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class Harness:
    model: Callable[[list[dict]], dict]      # your LLM call
    tools: dict[str, Callable[..., Any]]     # name -> python function
    max_turns: int = 12                      # (1) loop control
    messages: list[dict] = field(default_factory=list)

    def run(self, task: str) -> str:
        self.messages.append({"role": "user", "content": task})

        for turn in range(self.max_turns):
            reply = self.model(self.messages)          # ask the model
            self.messages.append(reply)

            calls = reply.get("tool_calls")
            if not calls:                              # (1) termination
                return reply.get("content", "")

            for call in calls:                         # (2) tool dispatch
                result = self._invoke(call)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,
                })

        return "Stopped: turn budget exhausted."       # (1) always terminates

    def _invoke(self, call: dict) -> str:
        fn = self.tools.get(call["name"])
        if fn is None:
            return f"Error: no tool named {call['name']}."   # (5) errors are data
        try:
            return str(fn(**call["arguments"]))
        except Exception as exc:                        # never crash the loop
            return f"Error: {type(exc).__name__}: {exc}"
```

Read that again and notice what it is **not** doing: no context trimming, no
permission check, no retry, no trace, no persistence. Each of those is a later
module, and each exists because this version fails in production.

---

## 4. Why Each Piece Exists

| Line | Guards against |
|---|---|
| `max_turns` | Infinite loop — the single most expensive agent bug |
| `if not calls: return` | Never terminating when the work is actually done |
| `if fn is None: return error` | Model hallucinating a tool that does not exist |
| `except Exception: return str` | One bad tool call killing the entire run |
| returning errors as **messages** | The model can *see* the failure and correct it |

That last one is the subtle one. A raised exception ends the run. An error
returned as a tool result becomes context the model can reason about — it will
often fix its own mistake on the next turn.

---

## 5. Trade-offs

**Framework vs. hand-rolled.** LangGraph, the OpenAI Agents SDK and the Claude
Agent SDK all give you a harness. They also give you their opinions about state,
persistence and control flow. Adopt one when your problem matches theirs; write
your own when it does not, or when you need to understand the failure modes
deeply. Module 09 covers this decision properly.

**More autonomy vs. more control.** Every guard you add makes the agent less
capable and more predictable. There is no universally right point on that line —
a coding agent on your laptop and an agent that issues refunds sit in very
different places.

---

## 6. Production Notes

- The turn budget should be **per run**, not per user. A single runaway run is
  the incident; a busy user is not.
- Log the *entire* message list on failure. Reproducing an agent bug without the
  exact context is close to impossible.
- Tool errors should be **specific and actionable**: `"Error: order_id must
  match ORD-XXXXXXXX, got 'abc'"` beats `"Error: invalid input"` because the
  model can act on the first one.

---

## 7. What To Say Out Loud

> "A harness is the deterministic system around a non-deterministic model. It
> owns five things: the loop and its termination, tool dispatch, context
> assembly, authority, and observability. The model decides *what* to do; the
> harness decides what is *permitted*, what is *visible*, and when to *stop*.
> Most agent incidents I have seen were harness bugs, not model bugs — an
> unbounded loop or a tool with more authority than the task required."

---

## 8. Check Yourself

1. Name the five responsibilities of a minimum viable harness.
2. Why return tool errors as messages rather than raising?
3. Your agent costs $200 in one night. Which harness layer failed?
4. When is a plain script the right answer instead of an agent?

→ Next: [`model-vs-harness-boundary.md`](model-vs-harness-boundary.md)
