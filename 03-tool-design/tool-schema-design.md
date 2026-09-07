# Harness Engineering — Module 3
# Topic: Tool Schema Design

> **F3 — tool misuse — is the failure you will hit most often.** Nearly all of
> it is preventable at the schema, before a single line of retry logic.

---

## 1. Intuition

A tool schema is not documentation. It is the **only** thing the model sees.

It cannot read your implementation, your tests, or the comment explaining that
`date` must be ISO format. It reads a name, a description, and a parameter
shape, and from that it guesses.

So the schema is a user interface, and the user is a capable but literal-minded
stranger who will never ask a clarifying question. Design it the way you would
design a form for someone you cannot talk to.

---

## 2. Core Concept

### The rule

> **Make the wrong call impossible to express.**

Not "detect the wrong call and reject it" — that is a fallback. If a parameter
can only be one of four values, say so in the schema and the model cannot pick a
fifth.

### Bad and good, side by side

```python
# BAD — every field invites a guess.
{
  "name": "search",
  "description": "Search stuff",
  "parameters": {
    "q": {"type": "string"},
    "n": {"type": "integer"},
    "type": {"type": "string"},
    "date": {"type": "string"},
  }
}
```

What is `n`? Results, or pages? What values does `type` accept? What date
format? The model will guess, be wrong sometimes, and you will call it a model
problem.

```python
# GOOD — no guesses left to make.
{
  "name": "search_orders",
  "description": (
      "Search a customer's past orders. Use when the user asks about an order "
      "they cannot find. Returns at most 20 matches, newest first. "
      "For a specific known order ID, use get_order instead."
  ),
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Free-text search over product names, e.g. 'blue running shoes'"
      },
      "max_results": {
        "type": "integer",
        "description": "How many orders to return",
        "minimum": 1, "maximum": 20, "default": 5
      },
      "status": {
        "type": "string",
        "description": "Filter by order status. Omit for all statuses.",
        "enum": ["pending", "shipped", "delivered", "cancelled"]
      },
      "placed_after": {
        "type": "string",
        "description": "ISO 8601 date, e.g. '2026-01-15'. Omit for no lower bound.",
        "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
      }
    },
    "required": ["query"]
  }
}
```

Every improvement removes one guess:

| Change | Removes |
|---|---|
| `search` → `search_orders` | Ambiguity about what is searched |
| "when to use / when not to" | Choosing this tool over `get_order` |
| `n` → `max_results` + bounds | Pages vs results; absurd values |
| `type` → `status` with `enum` | Inventing a status that does not exist |
| `date` → pattern + example | Every date format on earth |
| `required` | Omitting the one thing that matters |

### The four levers

**1. Name the tool for the job, not the endpoint.** `search_orders` beats
`db_query`. The model matches on names heavily.

**2. Put *when to use* in the description.** Most tool-selection errors are
resolved by one sentence: *"Use this when X. For Y, use Z instead."*

**3. Constrain the type as far as it will go.** `enum` over string. `minimum`
and `maximum` over integer. A pattern over a free-form date. Every constraint is
a class of bug that cannot happen.

**4. Give an example in the description.** `e.g. '2026-01-15'` is worth more
than three sentences of prose about formats.

---

## 3. Minimal Implementation

Derive the schema from the Python signature so it cannot drift from the code:

```python
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, get_args, get_origin, get_type_hints
import inspect


@dataclass(frozen=True)
class Param:
    description: str
    minimum: int | None = None
    maximum: int | None = None
    pattern: str | None = None


def schema_for(fn: Callable, params: dict[str, Param]) -> dict[str, Any]:
    """Build a JSON schema from a function signature plus per-parameter notes.

    Reading the signature keeps schema and implementation honest: rename an
    argument and the schema follows, instead of silently lying to the model.
    """
    hints = get_type_hints(fn)
    sig = inspect.signature(fn)
    props: dict[str, Any] = {}
    required: list[str] = []

    for name, sig_param in sig.parameters.items():
        note = params.get(name)
        if note is None:
            raise ValueError(f"{fn.__name__}: parameter {name!r} has no description. "
                             "The model can only see what you write here.")

        annotation = hints.get(name, str)
        entry: dict[str, Any] = {"description": note.description}

        if get_origin(annotation) is Literal:          # Literal -> enum
            entry["type"] = "string"
            entry["enum"] = list(get_args(annotation))
        elif annotation is int:
            entry["type"] = "integer"
        elif annotation is bool:
            entry["type"] = "boolean"
        else:
            entry["type"] = "string"

        for key in ("minimum", "maximum", "pattern"):
            value = getattr(note, key)
            if value is not None:
                entry[key] = value

        if sig_param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            entry["default"] = sig_param.default

        props[name] = entry

    return {
        "name": fn.__name__,
        "description": inspect.getdoc(fn) or "",
        "parameters": {"type": "object", "properties": props, "required": required},
    }
```

Used like this — the docstring *is* the description the model reads:

```python
def search_orders(
    query: str,
    max_results: int = 5,
    status: Literal["pending", "shipped", "delivered", "cancelled"] = "pending",
) -> str:
    """Search a customer's past orders.

    Use when the user asks about an order they cannot find. For a specific
    known order ID, use get_order instead.
    """
    ...

schema = schema_for(search_orders, {
    "query":       Param("Free-text over product names, e.g. 'blue running shoes'"),
    "max_results": Param("How many orders to return", minimum=1, maximum=20),
    "status":      Param("Filter by order status"),
})
```

The `raise` on a missing description is deliberate. An undescribed parameter is
a guaranteed future bug, and it should fail at import time rather than in
production.

---

## 4. How Many Tools?

Model accuracy in tool selection degrades as the set grows. Rough guidance:

| Tools | What happens |
|---|---|
| 1–5 | Selection is essentially reliable |
| 6–15 | Good, if names and descriptions are distinct |
| 16–30 | Errors climb; overlapping tools get confused |
| 30+ | Needs routing — a first step that narrows the set |

If you are past twenty, do not write better descriptions. **Group them.** Give
the agent a `list_capabilities` tool, or route by task type before the main
loop, so any single decision faces a handful of options.

---

## 5. Trade-offs

**Granular vs. coarse.** Ten small tools are each easy to describe and give the
model ten chances to choose wrongly. One `do_everything(action=...)` tool is
always chosen correctly and pushes the ambiguity into a parameter. Neither
extreme is right; group by *user intent*, not by endpoint.

**Strict vs. permissive schemas.** A strict schema rejects more, which means
more retries. But a retry with a good error message is cheap, and a silently
accepted bad value is expensive.

**Long descriptions cost tokens.** Every schema is in context on every call. A
40-tool set with paragraph descriptions can be thousands of tokens per turn.
Be complete about *when to use*; be terse about everything else.

---

## 6. Production Notes

- **Log every validation failure with the tool name.** One tool producing most
  of your errors is a schema problem, not a model problem — fix the schema.
- **Version schemas.** Changing an enum silently breaks any cached prompt or
  saved transcript that referenced the old values.
- **Test schemas against a real model**, not just your validator. Ask it to
  perform ten realistic tasks and count the malformed calls. That number is your
  actual schema quality.
- **Never expose raw SQL or shell as a tool** unless you have thought hard about
  Module 5. `run_query(sql: str)` gives the model your entire database as one
  parameter.

---

## 7. What To Say Out Loud

> "I treat a tool schema as the only interface the model has — it cannot read
> my code, so anything not in the schema is a guess. The rule is to make the
> wrong call impossible to express: enums instead of free strings, bounds on
> integers, a pattern and an example for dates. I put 'when to use this, and
> what to use instead' in the description, because most tool-selection errors
> are resolved by one sentence. And I generate schemas from the function
> signature so they cannot drift from the implementation. If one tool dominates
> my validation errors, that is a schema bug, not a model bug."

---

## 8. Check Yourself

1. Why is `enum` better than validating a string after the fact?
2. Your agent keeps calling `search` when it should call `get_order`. First fix?
3. Why raise at import time on an undescribed parameter?
4. You have 40 tools and selection accuracy is poor. What do you do?

→ Next: [`errors-as-feedback.md`](errors-as-feedback.md)
