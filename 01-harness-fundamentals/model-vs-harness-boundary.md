# Harness Engineering — Module 1
# Topic: The Model / Harness Boundary

---

## 1. Intuition

Imagine hiring a brilliant contractor who has no memory, no keys to the
building, and no idea what happened yesterday. Every morning you brief them,
hand them exactly the tools they need, and check their work before it ships.

The contractor is the model. Everything else is you — the harness.

The single most useful habit in this field is asking, for any behaviour you
want: **is this the model's job or mine?** Get that boundary wrong and you will
spend weeks tuning prompts to fix something a five-line `if` statement solves.

---

## 2. Core Concept

### What the model is genuinely good at

- Understanding messy natural language
- Choosing which tool fits a goal
- Writing and transforming text and code
- Summarising, extracting, classifying
- Recovering when you tell it what went wrong

### What the model is structurally bad at

- **Remembering.** It has no memory between calls. None.
- **Counting.** Tokens, retries, elapsed time — it cannot track these.
- **Guaranteeing.** It will do a thing *usually*, never *always*.
- **Refusing reliably.** Instructions are suggestions, not locks.
- **Knowing the time**, its own cost, or what other runs are doing.

That list is not a criticism. It is the specification for your harness.

### The boundary rule

> If a wrong answer is *expensive or irreversible*, the harness must enforce it.
> If a wrong answer is *merely unhelpful*, the model can own it.

Deleting a file is expensive. Choosing a slightly odd word is not.

### Worked examples

| Requirement | Owner | Why |
|---|---|---|
| "Answer in a friendly tone" | Model | Wrong answer is just unhelpful |
| "Never spend over $5 per run" | Harness | Model cannot count tokens |
| "Pick the right tool for the job" | Model | This is exactly its strength |
| "Never delete without confirmation" | **Harness** | Irreversible |
| "Stop after 20 turns" | Harness | Model cannot count turns |
| "Summarise this document" | Model | Language work |
| "Do not read files outside /workspace" | **Harness** | Security boundary |
| "Explain your reasoning" | Model | Presentation |
| "Retry a failed API call twice" | Harness | Needs reliable counting |

Notice the pattern: everything the harness owns involves **counting, memory, or
authority** — the three things a model provably cannot do.

---

## 3. The Anti-Pattern: Prompt-as-Control

This is the most common and most expensive mistake in the field.

```python
# WRONG — this is a wish, not a control.
SYSTEM = """You are a helpful assistant.
NEVER delete files without asking the user first.
NEVER spend more than 10 API calls.
ALWAYS stop if you are unsure."""
```

Every line is a suggestion. The model will follow them most of the time, which
is worse than never — you will trust it, and the one time it does not follow
them will be in production with a real customer's data.

```python
# RIGHT — the same rules, as code.
class Harness:
    def _invoke(self, call):
        tool = self.tools[call["name"]]

        if tool.destructive and not self.confirm(call):   # cannot be talked out of
            return "Error: user declined this action."

        if self.calls_made >= self.max_calls:             # cannot be miscounted
            return "Error: call budget exhausted."

        return tool.run(**call["arguments"])
```

You keep the prompt too — it helps the model *cooperate* with the rules and
produces better behaviour. But the prompt is the guidance and the code is the
guarantee. Never confuse the two.

---

## 4. Minimal Implementation

A boundary made explicit in the type system:

```python
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class Tool:
    """A capability. The flags are harness concerns, not model concerns."""
    name: str
    run: Callable[..., str]
    destructive: bool = False     # harness decides whether to confirm
    max_calls_per_run: int = 50   # harness counts; the model cannot

@dataclass
class Boundary:
    """Everything the model is not allowed to decide for itself."""
    turn_budget: int = 12
    token_budget: int = 100_000
    allowed_paths: tuple[str, ...] = ("/workspace",)
    require_confirmation_for_destructive: bool = True

    def permits_path(self, path: str) -> bool:
        return any(path.startswith(root) for root in self.allowed_paths)
```

Anything in `Boundary` is a promise you can keep. Anything in the system prompt
is a promise you hope for.

---

## 5. Trade-offs

**Too much harness.** Guard everything and you get a rigid workflow with an
expensive language model bolted on. If your agent has no real decisions to make,
you did not need an agent — see `when-not-to-use-an-agent.md`.

**Too little harness.** Trust the model with authority and counting and you get
demos that dazzle and production incidents that do not.

**The honest middle.** Start by guarding only the irreversible things. Add
guards as you observe real failures. Do not pre-build a permission system for
a tool that only reads.

---

## 6. Production Notes

- Write the boundary down. A one-page table of "model decides / harness decides"
  resolves most design arguments in a team.
- When a bug appears, first ask **which side of the boundary failed**. Model-side
  bugs are fixed with prompts, examples or a better model. Harness-side bugs are
  fixed with code, and no prompt will ever fix them.
- Beware the phrase *"we'll just tell it not to."* That sentence is how F6
  (excess authority) gets into production.

---

## 7. What To Say Out Loud

> "I draw a hard line between what the model decides and what the harness
> enforces. The model is good at language and tool selection; it is structurally
> incapable of counting, remembering, or reliably refusing. So anything
> involving budgets, authority or irreversibility lives in code. I still put
> those rules in the system prompt, because it makes the model cooperate — but
> the prompt is guidance and the code is the guarantee. Treating a prompt as a
> control is the most expensive mistake I see."

---

## 8. Check Yourself

1. "Never email a customer without approval." Model or harness? Why?
2. Why is "the model follows the rule most of the time" worse than never?
3. Give an example where too *much* harness makes a system worse.

→ Next: [`anatomy-of-an-agent-turn.md`](anatomy-of-an-agent-turn.md)
